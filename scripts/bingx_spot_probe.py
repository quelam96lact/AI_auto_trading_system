"""Thăm dò dữ liệu nến Spot công khai trên BingX (Brief đợt 3 / Gói P).

- Không dùng API key. Không ghi vào DB hay sửa bảng bars_crypto.
- Rate limit >= 1.0s giữa các request.
- Báo cáo rõ ràng: có sẵn không, khung nào, nến sớm nhất, số nến.
- Bắt lỗi per-symbol, không crash script.
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from typing import Any

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SPOT_KLINE_URL = "https://open-api.bingx.com/openApi/spot/v1/market/kline"

DEFAULT_PERP_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT",
    "AAVE-USDT", "LDO-USDT", "ZEC-USDT", "KAS-USDT", "HYPE-USDT",
    "UNI-USDT", "DOGE-USDT", "STRK-USDT", "ARB-USDT", "1000PEPE-USDT",
    "ORDI-USDT", "TRX-USDT", "TAO-USDT", "CRV-USDT", "XAUT-USDT",
]


def fetch_spot_klines_chunk(
    session: requests.Session,
    symbol: str,
    interval: str = "1d",
    limit: int = 1440,
    start_time: int | None = None,
    end_time: int | None = None,
    rate_limit_delay: float = 1.1,
    max_retries: int = 3,
) -> tuple[int, str | None, list[list[Any]]]:
    """Gọi endpoint public BingX Spot kline với rate limiting và retry an toàn.
    Trả về (code, error_msg, list_bars).
    Mỗi nến dạng [time, open, high, low, close, volume, closeTime, quoteVolume].
    """
    params: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "limit": min(limit, 1440),
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    backoff = 2.0
    for attempt in range(max_retries):
        try:
            resp = session.get(SPOT_KLINE_URL, params=params, timeout=15)
            time.sleep(rate_limit_delay)

            if resp.status_code == 429:
                time.sleep(min(backoff, 60.0))
                backoff *= 2.0
                continue

            resp.raise_for_status()
            data = resp.json()
            code = data.get("code", 0)
            msg = data.get("msg")
            raw_bars = data.get("data") or []
            return code, msg, raw_bars

        except Exception as exc:
            if attempt == max_retries - 1:
                return -1, str(exc), []
            time.sleep(backoff)
            backoff *= 2.0

    return -1, "Max retries exceeded", []


def probe_symbol_spot(
    session: requests.Session,
    symbol: str,
    interval: str = "1d",
    rate_limit_delay: float = 1.1,
) -> dict:
    """Thăm dò 1 mã trên BingX Spot: kiểm tra tồn tại, lấy nến mới nhất và nến cũ nhất."""
    code, msg, latest_chunk = fetch_spot_klines_chunk(
        session, symbol, interval=interval, limit=1440, rate_limit_delay=rate_limit_delay
    )

    if code != 0 or not latest_chunk:
        return {
            "symbol": symbol,
            "interval": interval,
            "available": False,
            "code": code,
            "msg": msg or "Không có dữ liệu",
            "bars_count": 0,
            "earliest": None,
            "latest": None,
            "depth_days": 0.0,
            "calls": 1,
        }

    # BingX Spot klines trả về thứ tự giảm dần theo thời gian: latest_chunk[0] là mới nhất, latest_chunk[-1] là cũ nhất
    latest_ts = latest_chunk[0][0] / 1000.0
    oldest_ts_in_chunk = latest_chunk[-1][0] / 1000.0

    calls = 1
    total_bars = len(latest_chunk)
    earliest_ts = oldest_ts_in_chunk

    # Thử lùi thêm 1-2 trang để kiểm tra độ sâu lịch sử thực tế
    prev_oldest_ms = int(latest_chunk[-1][0])
    for _ in range(5):  # Lùi tối đa 5 chunks để kiểm tra độ sâu
        end_time = prev_oldest_ms - 1
        code_prev, _, prev_chunk = fetch_spot_klines_chunk(
            session, symbol, interval=interval, limit=1440, end_time=end_time, rate_limit_delay=rate_limit_delay
        )
        calls += 1
        if code_prev != 0 or not prev_chunk:
            break
        total_bars += len(prev_chunk)
        earliest_ts = prev_chunk[-1][0] / 1000.0
        cur_oldest_ms = int(prev_chunk[-1][0])
        if cur_oldest_ms >= prev_oldest_ms:
            break
        prev_oldest_ms = cur_oldest_ms

    earliest_dt = datetime.fromtimestamp(earliest_ts, tz=UTC)
    latest_dt = datetime.fromtimestamp(latest_ts, tz=UTC)
    depth_days = (latest_ts - earliest_ts) / 86400.0

    return {
        "symbol": symbol,
        "interval": interval,
        "available": True,
        "code": 0,
        "msg": "OK",
        "bars_count": total_bars,
        "earliest": earliest_dt.strftime("%Y-%m-%d %H:%M"),
        "latest": latest_dt.strftime("%Y-%m-%d %H:%M"),
        "depth_days": depth_days,
        "calls": calls,
    }


def probe_all_symbols(
    symbols: list[str],
    interval: str = "1d",
    rate_limit_delay: float = 1.1,
) -> list[dict]:
    """Thăm dò toàn bộ danh sách mã trên BingX Spot."""
    results = []
    session = requests.Session()
    session.headers.update({"User-Agent": "AI-Auto-Trading-System/SpotProbe"})

    for sym in symbols:
        res = probe_symbol_spot(session, sym, interval=interval, rate_limit_delay=rate_limit_delay)
        results.append(res)
    return results


def print_spot_probe_report(results: list[dict], interval: str) -> None:
    """In bảng báo cáo chi tiết thăm dò BingX Spot."""
    print("\n" + "=" * 105)
    print(f"BÁO CÁO THĂM DÒ DỮ LIỆU BINGX SPOT (Khung: {interval.upper()})")
    print("=" * 105)
    print(f"{'#':<3} {'Cặp giao dịch':<16} {'Trạng thái Spot':<18} {'Số nến mẫu':>10} {'Mốc đầu (Earliest)':<18} {'Mốc cuối (Latest)':<18} {'Độ sâu':>10}")
    print("-" * 105)

    available_count = 0
    for i, r in enumerate(results, 1):
        if r["available"]:
            available_count += 1
            status = "SẴN SÀNG"
            bars_s = f"{r['bars_count']:,}"
            earliest_s = r["earliest"] or "N/A"
            latest_s = r["latest"] or "N/A"
            depth_s = f"{r['depth_days']:,.1f} ngày"
        else:
            status = f"KHÔNG CÓ ({r['code']})"
            bars_s = "0"
            earliest_s = "-"
            latest_s = "-"
            depth_s = f"{r['msg']}"
        print(f"{i:<3} {r['symbol']:<16} {status:<18} {bars_s:>10} {earliest_s:<18} {latest_s:<18} {depth_s:>10}")

    print("=" * 105)
    print(f"TỔNG KẾT: {available_count}/{len(results)} cặp có dữ liệu trên BingX Spot (khung {interval.upper()}).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Thăm dò dữ liệu BingX Spot công khai")
    ap.add_argument("--interval", default="1d", choices=["1d", "1h", "both"])
    ap.add_argument("--symbols", default=None, help="Danh sách mã phân cách dấu phẩy")
    ap.add_argument("--delay", type=float, default=1.1, help="Độ trễ giữa các request (giây)")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else DEFAULT_PERP_SYMBOLS
    intervals = ["1d", "1h"] if args.interval == "both" else [args.interval]

    for itv in intervals:
        print(f"\nBắt đầu thăm dò {len(symbols)} mã trên BingX Spot (khung {itv})...")
        results = probe_all_symbols(symbols, interval=itv, rate_limit_delay=args.delay)
        print_spot_probe_report(results, itv)


if __name__ == "__main__":
    main()
