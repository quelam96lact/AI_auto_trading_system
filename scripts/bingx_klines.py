"""Nạp dữ liệu nến lịch sử từ BingX API vào cơ sở dữ liệu (Brief đợt 12).

- Bảng đích: `bars_crypto` (độc lập hoàn toàn với `bars_daily` của chứng khoán VN).
- Endpoint: `https://open-api.bingx.com/openApi/swap/v3/quote/klines` (không cần API key).
- Giới hạn tần suất: sleep >= 1.1s giữa các request.
  Nếu gặp lỗi 100410 / HTTP 429: exponential backoff với trần 600s.
- Phân trang an toàn: chống lặp vô hạn nếu API không tiến lên.
- UPSERT an toàn khi chạy lại nhiều lần.
"""

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import psycopg
import requests

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://open-api.bingx.com"
MAX_BACKOFF_SECONDS = 600.0
INITIAL_BACKOFF_SECONDS = 2.0
RATE_LIMIT_SLEEP = 1.1

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def init_crypto_schema(conn: psycopg.Connection) -> None:
    """Tạo bảng bars_crypto nếu chưa có. Không đụng tới bảng cũ."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bars_crypto (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                open DOUBLE PRECISION NOT NULL,
                high DOUBLE PRECISION NOT NULL,
                low DOUBLE PRECISION NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                volume DOUBLE PRECISION NOT NULL,
                quote_volume DOUBLE PRECISION,
                trades INT,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, interval, ts)
            );
            CREATE INDEX IF NOT EXISTS idx_bars_crypto_sym_int_ts
                ON bars_crypto (symbol, interval, ts);
        """)
    conn.commit()


def parse_kline(raw: list | dict, symbol: str, interval: str) -> dict:
    """Parse 1 nến từ BingX API thành dict chuẩn để lưu DB.
    Hỗ trợ cả định dạng mảng:
      [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades]
    và định dạng dict:
      {'time': openTime, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, ...}
    """
    if isinstance(raw, (list, tuple)):
        open_time = int(raw[0])
        open_p = float(raw[1])
        high_p = float(raw[2])
        low_p = float(raw[3])
        close_p = float(raw[4])
        vol = float(raw[5])
        close_time = int(raw[6]) if len(raw) > 6 else open_time
        quote_vol = float(raw[7]) if len(raw) > 7 else 0.0
        trades_cnt = int(raw[8]) if len(raw) > 8 else 0
    elif isinstance(raw, dict):
        open_time = int(raw.get("time") or raw.get("openTime") or 0)
        open_p = float(raw["open"])
        high_p = float(raw["high"])
        low_p = float(raw["low"])
        close_p = float(raw["close"])
        vol = float(raw.get("volume", 0))
        close_time = int(raw.get("closeTime") or open_time)
        quote_vol = float(raw.get("quoteVolume", 0))
        trades_cnt = int(raw.get("trades", 0))
    else:
        raise TypeError(f"Unsupported kline format: {type(raw)}")

    ts = datetime.fromtimestamp(open_time / 1000.0, tz=UTC)
    return {
        "symbol": symbol,
        "interval": interval,
        "ts": ts,
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "volume": vol,
        "quote_volume": quote_vol,
        "trades": trades_cnt,
        "open_time_ms": open_time,
        "close_time_ms": close_time,
    }


def fetch_klines_http(
    symbol: str,
    interval: str,
    end_time_ms: int | None = None,
    start_time_ms: int | None = None,
    limit: int = 1000,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[dict | list]:
    """Gọi BingX API với retry và exponential backoff khi gặp rate limit (100410 / HTTP 429)."""
    http = session or _HTTP_SESSION
    params: dict[str, str | int] = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if end_time_ms is not None:
        params["endTime"] = end_time_ms
    if start_time_ms is not None:
        params["startTime"] = start_time_ms

    url = f"{BASE_URL}/openApi/swap/v3/quote/klines"
    backoff = INITIAL_BACKOFF_SECONDS
    max_retries = 10

    for attempt in range(max_retries):
        try:
            resp = http.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
                print(f"[HTTP 429] Lùi {sleep_dur:.1f}s (lần {attempt + 1})...", file=sys.stderr)
                sleep_fn(sleep_dur)
                backoff *= 2.0
                continue
            elif resp.status_code != 200:
                print(f"[HTTP Error {resp.status_code}] {resp.text[:200]}", file=sys.stderr)
                return []

            data = resp.json()
            code = data.get("code")
            if code == 0:
                return data.get("data", [])
            elif code == 100410 or "limit" in str(data.get("msg", "")).lower():
                sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
                print(f"[RateLimit 100410] Lùi {sleep_dur:.1f}s (lần {attempt + 1})...", file=sys.stderr)
                sleep_fn(sleep_dur)
                backoff *= 2.0
            else:
                print(f"[BingX API Error] Code {code}: {data.get('msg')}", file=sys.stderr)
                return []
        except requests.RequestException as e:
            sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
            print(f"[Network Error] {type(e).__name__}: {e}. Thử lại sau {sleep_dur:.1f}s...", file=sys.stderr)
            sleep_fn(sleep_dur)
            backoff *= 2.0

    return []


def collect_symbol_klines(
    symbol: str,
    interval: str,
    from_ts_ms: int | None = None,
    to_ts_ms: int | None = None,
    limit: int = 1000,
    fetch_fn: Callable = fetch_klines_http,
    sleep_fn: Callable[[float], None] = time.sleep,
    rate_limit_sleep: float = RATE_LIMIT_SLEEP,
) -> tuple[list[dict], int]:
    """Thu thập toàn bộ nến cho 1 mã qua phân trang ngược thời gian.
    Trả về: (danh sách nến đã parse xếp tăng dần thời gian, tổng số request đã gọi).
    """
    all_parsed: dict[int, dict] = {}
    current_end_ms = to_ts_ms
    prev_min_ms: int | None = None
    call_count = 0

    while True:
        call_count += 1
        raw_bars = fetch_fn(symbol, interval, end_time_ms=current_end_ms, limit=limit)
        if not raw_bars:
            break

        parsed_bars = [parse_kline(b, symbol, interval) for b in raw_bars]
        min_ms = min(b["open_time_ms"] for b in parsed_bars)

        # Chống lặp vô hạn: nếu nến cuối không tiến lên quá khứ
        if prev_min_ms is not None and min_ms >= prev_min_ms:
            break

        for b in parsed_bars:
            if from_ts_ms is not None and b["open_time_ms"] < from_ts_ms:
                continue
            all_parsed[b["open_time_ms"]] = b

        prev_min_ms = min_ms
        current_end_ms = min_ms - 1

        # Nếu đã đạt mốc from_ts_ms hoặc số nến trả về < limit (đã chạm đáy lịch sử)
        if from_ts_ms is not None and min_ms <= from_ts_ms:
            break
        # KHONG dung chi vi trang nay tra ve it hon `limit`.
        # BingX co the tra mot trang NGAN giua luc lich su van con (do 116:
        # NCFXEUR2USD-USDT 1h tra 724/1000 o trang dau nhung con du lieu lui ve
        # tan ngay niem yet). Dieu kien dung dung dan la trang khong con tien
        # ve qua khu nua, da kiem o tren bang `min_ms >= prev_min_ms`.

        if rate_limit_sleep > 0:
            sleep_fn(rate_limit_sleep)

    sorted_bars = [all_parsed[k] for k in sorted(all_parsed.keys())]
    return sorted_bars, call_count


def upsert_bars_crypto(conn: psycopg.Connection, bars: list[dict]) -> int:
    """UPSERT danh sách nến vào bảng bars_crypto."""
    if not bars:
        return 0
    sql = """
        INSERT INTO bars_crypto (
            symbol, interval, ts, open, high, low, close, volume, quote_volume, trades
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, interval, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            trades = EXCLUDED.trades;
    """
    records = [
        (
            b["symbol"],
            b["interval"],
            b["ts"],
            b["open"],
            b["high"],
            b["low"],
            b["close"],
            b["volume"],
            b["quote_volume"],
            b["trades"],
        )
        for b in bars
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, records)
    conn.commit()
    return len(records)


def get_top_crypto_symbols(limit: int = 20, session: requests.Session | None = None) -> list[str]:
    """Lấy danh sách top N cặp crypto USDT-M perpetual thanh khoản cao nhất từ BingX."""
    http = session or _HTTP_SESSION
    try:
        url_ticker = f"{BASE_URL}/openApi/swap/v2/quote/ticker"
        resp = http.get(url_ticker, timeout=10)
        tickers = resp.json().get("data", [])

        url_contracts = f"{BASE_URL}/openApi/swap/v2/quote/contracts"
        resp2 = http.get(url_contracts, timeout=10)
        contracts = {c["symbol"]: c for c in resp2.json().get("data", [])}

        valid_tickers = []
        for t in tickers:
            sym = t.get("symbol", "")
            if sym in contracts and contracts[sym].get("currency") == "USDT" and not sym.startswith("NC"):
                valid_tickers.append((sym, float(t.get("quoteVolume", 0))))

        valid_tickers.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in valid_tickers[:limit]]
    except Exception as e:
        print(f"[Warning] Không lấy được danh sách động: {e}. Dùng danh sách chuẩn bị sẵn.", file=sys.stderr)
        return [
            "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT",
            "AAVE-USDT", "LDO-USDT", "ZEC-USDT", "KAS-USDT", "HYPE-USDT",
            "UNI-USDT", "DOGE-USDT", "STRK-USDT", "ARB-USDT", "1000PEPE-USDT",
            "ORDI-USDT", "TRX-USDT", "TAO-USDT", "CRV-USDT", "CFX-USDT",
        ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Nạp nến lịch sử từ BingX vào DB")
    ap.add_argument("--symbols", default=None, help="Danh sách mã phân cách bởi dấu phẩy (VD: BTC-USDT,ETH-USDT)")
    ap.add_argument("--interval", default="1d", choices=["1d", "1h", "5m"])
    ap.add_argument("--from", dest="frm", default=None, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", default=None, help="YYYY-MM-DD")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--limit-symbols", type=int, default=20)
    args = ap.parse_args()

    dsn = resolve_dsn(args.dsn)
    with psycopg.connect(dsn) as conn:
        init_crypto_schema(conn)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else get_top_crypto_symbols(args.limit_symbols)

    from_ms = int(datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000) if args.frm else None
    to_ms = int(datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000) if args.to else None

    print(f"Bắt đầu nạp nến BingX cho {len(symbols)} cặp (khung {args.interval})...")
    print(f"Danh sách: {', '.join(symbols)}")

    results = []
    total_start = time.time()
    total_calls_all = 0

    with psycopg.connect(dsn) as conn:
        for i, sym in enumerate(symbols, 1):
            t0 = time.time()
            bars, calls = collect_symbol_klines(sym, args.interval, from_ts_ms=from_ms, to_ts_ms=to_ms)
            total_calls_all += calls
            n_saved = upsert_bars_crypto(conn, bars)
            dur = time.time() - t0

            earliest = bars[0]["ts"].strftime("%Y-%m-%d") if bars else "N/A"
            latest = bars[-1]["ts"].strftime("%Y-%m-%d") if bars else "N/A"

            results.append({
                "symbol": sym,
                "earliest": earliest,
                "latest": latest,
                "bars": n_saved,
                "calls": calls,
                "duration_s": dur,
            })
            print(f"[{i:2d}/{len(symbols)}] {sym:<15}: {n_saved:>5} nến ({earliest} -> {latest}) | {calls:>2} calls | {dur:>5.1f}s")

    total_dur = time.time() - total_start
    print("\n" + "=" * 78)
    print(f"TỔNG KẾT NẠP NẾN BINGX ({args.interval.upper()}): {sum(r['bars'] for r in results):,} nến | {total_calls_all} calls | {total_dur:.1f}s")
    print("=" * 78)


if __name__ == "__main__":
    main()
