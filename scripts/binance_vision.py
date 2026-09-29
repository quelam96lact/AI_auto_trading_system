"""Tải và nạp dữ liệu nến 1h, funding rate, và metrics từ Binance Vision (Brief đợt 40).

- Nguồn: data.binance.vision (kho tĩnh công khai qua HTTPS, không cần API key).
- Ràng buộc mạng:
  - Chỉ gọi GET https://data.binance.vision/... và s3 storage liên quan.
  - Nghỉ tối thiểu 1.0s giữa các lượt tải. Exponential backoff trần 300s khi 429/5xx.
  - Tải file .CHECKSUM và đối chiếu SHA256 cho từng file .zip.
- Nạp UPSERT an toàn khi chạy lại nhiều lần (idempotent).
"""

import argparse
import csv
import hashlib
import io
import sys
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import psycopg
import requests

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_VISION_URL = "https://data.binance.vision"
MIN_RATE_LIMIT_SLEEP = 1.05
MAX_BACKOFF_SECONDS = 300.0
INITIAL_BACKOFF_SECONDS = 2.0

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def init_binance_schema(conn: psycopg.Connection) -> None:
    """Tạo 4 bảng binance nếu chưa có. Không đụng bảng cũ."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS binance_klines (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                open DOUBLE PRECISION NOT NULL,
                high DOUBLE PRECISION NOT NULL,
                low DOUBLE PRECISION NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                volume DOUBLE PRECISION NOT NULL,
                quote_volume DOUBLE PRECISION,
                trades BIGINT,
                taker_buy_volume DOUBLE PRECISION,
                taker_buy_quote_volume DOUBLE PRECISION,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, interval, ts)
            );

            CREATE TABLE IF NOT EXISTS binance_funding (
                symbol TEXT NOT NULL,
                funding_time TIMESTAMPTZ NOT NULL,
                funding_rate DOUBLE PRECISION NOT NULL,
                funding_interval_hours INT,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, funding_time)
            );

            CREATE TABLE IF NOT EXISTS binance_metrics (
                symbol TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                sum_open_interest DOUBLE PRECISION,
                sum_open_interest_value DOUBLE PRECISION,
                count_toptrader_long_short_ratio DOUBLE PRECISION,
                sum_toptrader_long_short_ratio DOUBLE PRECISION,
                count_long_short_ratio DOUBLE PRECISION,
                sum_taker_long_short_vol_ratio DOUBLE PRECISION,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, ts)
            );

            CREATE TABLE IF NOT EXISTS binance_orderflow_1h (
                symbol TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                taker_buy_volume DOUBLE PRECISION NOT NULL,
                taker_sell_volume DOUBLE PRECISION NOT NULL,
                delta DOUBLE PRECISION NOT NULL,
                buy_ratio DOUBLE PRECISION NOT NULL,
                trade_count BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, ts)
            );
            CREATE INDEX IF NOT EXISTS idx_binance_orderflow_1h_sym_ts
                ON binance_orderflow_1h (symbol, ts);
        """)
    conn.commit()


def fetch_url_bytes(
    url: str,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    rate_limit_sleep: float = MIN_RATE_LIMIT_SLEEP,
    max_retries: int = 5,
) -> bytes | None:
    """Tải bytes từ URL với retry và exponential backoff khi gặp 429/5xx/network error.

    Trả về None nếu HTTP 404 (file không tồn tại).
    """
    http = session or _HTTP_SESSION
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(max_retries):
        try:
            resp = http.get(url, timeout=30)
            if resp.status_code == 200:
                sleep_fn(rate_limit_sleep)
                return resp.content
            elif resp.status_code == 404:
                sleep_fn(rate_limit_sleep)
                return None
            elif resp.status_code == 429 or resp.status_code >= 500:
                sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
                print(f"[HTTP {resp.status_code}] Lùi {sleep_dur:.1f}s (lần {attempt + 1})...", file=sys.stderr)
                sleep_fn(sleep_dur)
                backoff *= 2.0
            else:
                print(f"[HTTP {resp.status_code}] {url}: {resp.text[:100]}", file=sys.stderr)
                sleep_fn(rate_limit_sleep)
                return None
        except requests.RequestException as e:
            sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
            print(f"[Network Error] {type(e).__name__}: {e}. Lùi {sleep_dur:.1f}s...", file=sys.stderr)
            sleep_fn(sleep_dur)
            backoff *= 2.0

    return None


def download_zip_with_checksum(
    zip_url: str,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    rate_limit_sleep: float = MIN_RATE_LIMIT_SLEEP,
) -> tuple[bytes | None, str | None]:
    """Tải tệp ZIP kèm tệp .CHECKSUM và đối chiếu SHA256.

    Nếu lệch checksum: thử tải lại 1 lần nữa.
    Trả về (zip_bytes, error_message).
    """
    checksum_url = f"{zip_url}.CHECKSUM"
    checksum_bytes = fetch_url_bytes(checksum_url, session=session, sleep_fn=sleep_fn, rate_limit_sleep=rate_limit_sleep)
    if checksum_bytes is None:
        return None, f"Không tìm thấy file checksum: {checksum_url}"

    checksum_text = checksum_bytes.decode("utf-8", errors="replace").strip()
    expected_sha256 = checksum_text.split()[0].lower()

    for attempt in range(2):
        zip_bytes = fetch_url_bytes(zip_url, session=session, sleep_fn=sleep_fn, rate_limit_sleep=rate_limit_sleep)
        if zip_bytes is None:
            return None, f"Không tải được file zip: {zip_url}"

        calc_sha256 = hashlib.sha256(zip_bytes).hexdigest().lower()
        if calc_sha256 == expected_sha256:
            return zip_bytes, None

        print(f"[CẢNH BÁO] Lệch checksum lần {attempt + 1} cho {zip_url} (calc={calc_sha256}, exp={expected_sha256})", file=sys.stderr)

    return None, f"Lệch SHA256 sau 2 lần thử (calc={calc_sha256}, exp={expected_sha256})"


def parse_klines_zip(zip_bytes: bytes, symbol: str, interval: str) -> list[dict]:
    """Parse nội dung CSV nến từ ZIP bytes."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            return []
        with z.open(csv_names[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            records = []
            for row in reader:
                if not row or row[0].strip() == "open_time" or not row[0].strip().isdigit():
                    continue
                open_time_ms = int(row[0])
                ts = datetime.fromtimestamp(open_time_ms / 1000.0, tz=UTC)
                records.append({
                    "symbol": symbol,
                    "interval": interval,
                    "ts": ts,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "quote_volume": float(row[7]) if len(row) > 7 and row[7] != "" else 0.0,
                    "trades": int(row[8]) if len(row) > 8 and row[8] != "" else 0,
                    "taker_buy_volume": float(row[9]) if len(row) > 9 and row[9] != "" else 0.0,
                    "taker_buy_quote_volume": float(row[10]) if len(row) > 10 and row[10] != "" else 0.0,
                })
            return records


def parse_funding_zip(zip_bytes: bytes, symbol: str) -> list[dict]:
    """Parse nội dung CSV funding rate từ ZIP bytes."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            return []
        with z.open(csv_names[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            records = []
            for row in reader:
                if not row or row[0].strip() == "calc_time" or not row[0].strip().isdigit():
                    continue
                calc_time_ms = int(row[0])
                funding_time = datetime.fromtimestamp(calc_time_ms / 1000.0, tz=UTC)
                if len(row) >= 3:
                    interval_hours = int(row[1]) if row[1] != "" else None
                    rate = float(row[2])
                else:
                    interval_hours = None
                    rate = float(row[1])
                records.append({
                    "symbol": symbol,
                    "funding_time": funding_time,
                    "funding_rate": rate,
                    "funding_interval_hours": interval_hours,
                })
            return records


def parse_metrics_zip(zip_bytes: bytes, symbol: str) -> list[dict]:
    """Parse nội dung CSV daily metrics từ ZIP bytes."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            return []
        with z.open(csv_names[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            records = []
            for row in reader:
                if not row or row[0].strip() == "create_time" or row[0].strip() == "symbol":
                    continue
                try:
                    ts = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                except ValueError:
                    continue

                records.append({
                    "symbol": symbol,
                    "ts": ts,
                    "sum_open_interest": float(row[2]) if len(row) > 2 and row[2] != "" else None,
                    "sum_open_interest_value": float(row[3]) if len(row) > 3 and row[3] != "" else None,
                    "count_toptrader_long_short_ratio": float(row[4]) if len(row) > 4 and row[4] != "" else None,
                    "sum_toptrader_long_short_ratio": float(row[5]) if len(row) > 5 and row[5] != "" else None,
                    "count_long_short_ratio": float(row[6]) if len(row) > 6 and row[6] != "" else None,
                    "sum_taker_long_short_vol_ratio": float(row[7]) if len(row) > 7 and row[7] != "" else None,
                })
            return records


def upsert_binance_klines(conn: psycopg.Connection, records: list[dict]) -> int:
    """UPSERT danh sách nến vào bảng binance_klines."""
    if not records:
        return 0
    sql = """
        INSERT INTO binance_klines (
            symbol, interval, ts, open, high, low, close, volume,
            quote_volume, trades, taker_buy_volume, taker_buy_quote_volume
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, interval, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            trades = EXCLUDED.trades,
            taker_buy_volume = EXCLUDED.taker_buy_volume,
            taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume;
    """
    rows = [
        (
            r["symbol"],
            r["interval"],
            r["ts"],
            r["open"],
            r["high"],
            r["low"],
            r["close"],
            r["volume"],
            r["quote_volume"],
            r["trades"],
            r["taker_buy_volume"],
            r["taker_buy_quote_volume"],
        )
        for r in records
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def upsert_binance_funding(conn: psycopg.Connection, records: list[dict]) -> int:
    """UPSERT danh sách funding rate vào bảng binance_funding."""
    if not records:
        return 0
    sql = """
        INSERT INTO binance_funding (
            symbol, funding_time, funding_rate, funding_interval_hours
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (symbol, funding_time) DO UPDATE SET
            funding_rate = EXCLUDED.funding_rate,
            funding_interval_hours = EXCLUDED.funding_interval_hours;
    """
    rows = [
        (
            r["symbol"],
            r["funding_time"],
            r["funding_rate"],
            r["funding_interval_hours"],
        )
        for r in records
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def upsert_binance_metrics(conn: psycopg.Connection, records: list[dict]) -> int:
    """UPSERT danh sách metrics vào bảng binance_metrics."""
    if not records:
        return 0
    sql = """
        INSERT INTO binance_metrics (
            symbol, ts, sum_open_interest, sum_open_interest_value,
            count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
            count_long_short_ratio, sum_taker_long_short_vol_ratio
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, ts) DO UPDATE SET
            sum_open_interest = EXCLUDED.sum_open_interest,
            sum_open_interest_value = EXCLUDED.sum_open_interest_value,
            count_toptrader_long_short_ratio = EXCLUDED.count_toptrader_long_short_ratio,
            sum_toptrader_long_short_ratio = EXCLUDED.sum_toptrader_long_short_ratio,
            count_long_short_ratio = EXCLUDED.count_long_short_ratio,
            sum_taker_long_short_vol_ratio = EXCLUDED.sum_taker_long_short_vol_ratio;
    """
    rows = [
        (
            r["symbol"],
            r["ts"],
            r["sum_open_interest"],
            r["sum_open_interest_value"],
            r["count_toptrader_long_short_ratio"],
            r["sum_toptrader_long_short_ratio"],
            r["count_long_short_ratio"],
            r["sum_taker_long_short_vol_ratio"],
        )
        for r in records
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def get_months_in_range(start_date: date, end_date: date) -> list[tuple[int, int]]:
    """Trả về danh sách (year, month) từ start_date tới end_date."""
    months = []
    curr = start_date.replace(day=1)
    end = end_date.replace(day=1)
    while curr <= end:
        months.append((curr.year, curr.month))
        if curr.month == 12:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)
    return months


def get_days_in_month(year: int, month: int) -> int:
    """Số ngày trong tháng."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def check_month_klines_loaded(conn: psycopg.Connection, symbol: str, interval: str, year: int, month: int) -> bool:
    """Kiểm tra tháng nến đã được nạp đủ chưa."""
    start_ts = datetime(year, month, 1, 0, 0, tzinfo=UTC)
    days = get_days_in_month(year, month)
    end_ts = start_ts + timedelta(days=days)
    expected_bars = days * 24

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM binance_klines WHERE symbol = %s AND interval = %s AND ts >= %s AND ts < %s",
            (symbol, interval, start_ts, end_ts),
        )
        count = cur.fetchone()[0]
    return count >= expected_bars


def check_month_funding_loaded(conn: psycopg.Connection, symbol: str, year: int, month: int) -> bool:
    """Kiểm tra tháng funding đã được nạp đủ chưa."""
    start_ts = datetime(year, month, 1, 0, 0, tzinfo=UTC)
    days = get_days_in_month(year, month)
    end_ts = start_ts + timedelta(days=days)
    expected_records = days * 3 - 2

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM binance_funding WHERE symbol = %s AND funding_time >= %s AND funding_time < %s",
            (symbol, start_ts, end_ts),
        )
        count = cur.fetchone()[0]
    return count >= expected_records


def check_day_metrics_loaded(conn: psycopg.Connection, symbol: str, day_date: date) -> bool:
    """Kiểm tra ngày metrics đã được nạp đủ chưa."""
    start_ts = datetime(day_date.year, day_date.month, day_date.day, 0, 0, tzinfo=UTC)
    end_ts = start_ts + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM binance_metrics WHERE symbol = %s AND ts >= %s AND ts < %s",
            (symbol, start_ts, end_ts),
        )
        count = cur.fetchone()[0]
    return count >= 288


def load_all_klines(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2026, 8, 31),
    force: bool = False,
    rate_limit_sleep: float = MIN_RATE_LIMIT_SLEEP,
) -> tuple[int, int]:
    """Tải và nạp nến 1h cho toàn bộ các tháng trong khoảng."""
    months = get_months_in_range(start_date, end_date)
    total_months = len(months)
    total_rows = 0
    loaded_months = 0

    print(f"=== [KLINES] Bắt đầu nạp {symbol} khung {interval}: {total_months} tháng ({start_date} -> {end_date}) ===")
    for idx, (y, m) in enumerate(months, 1):
        if not force and check_month_klines_loaded(conn, symbol, interval, y, m):
            print(f"[{idx}/{total_months}] Tháng {y}-{m:02d}: Đã có đủ trong DB -> Bỏ qua.")
            continue

        rel_path = f"data/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{y}-{m:02d}.zip"
        zip_url = f"{BASE_VISION_URL}/{rel_path}"

        zip_bytes, err = download_zip_with_checksum(zip_url, rate_limit_sleep=rate_limit_sleep)
        if err or not zip_bytes:
            print(f"[{idx}/{total_months}] Tháng {y}-{m:02d} LỖI: {err}", file=sys.stderr)
            continue

        records = parse_klines_zip(zip_bytes, symbol, interval)
        inserted = upsert_binance_klines(conn, records)
        total_rows += inserted
        loaded_months += 1
        print(f"[{idx}/{total_months}] Tháng {y}-{m:02d}: Nạp thành công {inserted} nến.")

    print(f"=== [KLINES] Hoàn thành: {loaded_months} tháng mới nạp, tổng cộng {total_rows} dòng ===")
    return loaded_months, total_rows


def load_all_funding(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2026, 8, 31),
    force: bool = False,
    rate_limit_sleep: float = MIN_RATE_LIMIT_SLEEP,
) -> tuple[int, int]:
    """Tải và nạp funding rate cho toàn bộ các tháng trong khoảng."""
    months = get_months_in_range(start_date, end_date)
    total_months = len(months)
    total_rows = 0
    loaded_months = 0

    print(f"=== [FUNDING] Bắt đầu nạp {symbol}: {total_months} tháng ({start_date} -> {end_date}) ===")
    for idx, (y, m) in enumerate(months, 1):
        if not force and check_month_funding_loaded(conn, symbol, y, m):
            print(f"[{idx}/{total_months}] Tháng {y}-{m:02d}: Đã có đủ trong DB -> Bỏ qua.")
            continue

        rel_path = f"data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{y}-{m:02d}.zip"
        zip_url = f"{BASE_VISION_URL}/{rel_path}"

        zip_bytes, err = download_zip_with_checksum(zip_url, rate_limit_sleep=rate_limit_sleep)
        if err or not zip_bytes:
            print(f"[{idx}/{total_months}] Tháng {y}-{m:02d} LỖI: {err}", file=sys.stderr)
            continue

        records = parse_funding_zip(zip_bytes, symbol)
        inserted = upsert_binance_funding(conn, records)
        total_rows += inserted
        loaded_months += 1
        print(f"[{idx}/{total_months}] Tháng {y}-{m:02d}: Nạp thành công {inserted} bản ghi.")

    print(f"=== [FUNDING] Hoàn thành: {loaded_months} tháng mới nạp, tổng cộng {total_rows} dòng ===")
    return loaded_months, total_rows


def load_all_metrics(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2026, 8, 31),
    force: bool = False,
    rate_limit_sleep: float = MIN_RATE_LIMIT_SLEEP,
) -> tuple[int, int]:
    """Tải và nạp metrics theo ngày cho toàn bộ các ngày trong khoảng."""
    total_days = (end_date - start_date).days + 1
    total_rows = 0
    loaded_days = 0

    print(f"=== [METRICS] Bắt đầu nạp {symbol}: {total_days} ngày ({start_date} -> {end_date}) ===")
    curr = start_date
    day_idx = 0

    while curr <= end_date:
        day_idx += 1
        if not force and check_day_metrics_loaded(conn, symbol, curr):
            if day_idx % 50 == 0 or day_idx == total_days:
                print(f"[{day_idx}/{total_days}] Ngày {curr}: Đã có đủ trong DB -> Bỏ qua (tiến độ {day_idx}/{total_days}).")
            curr += timedelta(days=1)
            continue

        rel_path = f"data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{curr.year}-{curr.month:02d}-{curr.day:02d}.zip"
        zip_url = f"{BASE_VISION_URL}/{rel_path}"

        zip_bytes, err = download_zip_with_checksum(zip_url, rate_limit_sleep=rate_limit_sleep)
        if err or not zip_bytes:
            print(f"[{day_idx}/{total_days}] Ngày {curr} LỖI: {err}", file=sys.stderr)
            curr += timedelta(days=1)
            continue

        records = parse_metrics_zip(zip_bytes, symbol)
        inserted = upsert_binance_metrics(conn, records)
        total_rows += inserted
        loaded_days += 1

        if day_idx % 25 == 0 or day_idx == total_days:
            print(f"[{day_idx}/{total_days}] Ngày {curr}: Nạp {inserted} dòng (tổng nạp: {total_rows} dòng, {loaded_days} ngày).")

        curr += timedelta(days=1)

    print(f"=== [METRICS] Hoàn thành: {loaded_days} ngày mới nạp, tổng cộng {total_rows} dòng ===")
    return loaded_days, total_rows


def cross_check_binance_bingx(
    conn: psycopg.Connection,
    binance_symbol: str = "BTCUSDT",
    bingx_symbol: str = "BTC-USDT",
    start_ts: str = "2026-08-01 00:00:00+00",
    end_ts: str = "2026-08-31 23:59:59+00",
) -> dict:
    """Đối chiếu chéo giá đóng cửa nến 1h giữa Binance và BingX."""
    sql = """
        SELECT
            b.ts,
            b.close AS binance_close,
            x.close AS bingx_close,
            ABS(b.close - x.close) / x.close * 100.0 AS diff_pct
        FROM binance_klines b
        JOIN bars_crypto x
          ON b.ts = x.ts
         AND x.symbol = %s
         AND x.interval = '1h'
        WHERE b.symbol = %s
          AND b.interval = '1h'
          AND b.ts >= %s
          AND b.ts <= %s
        ORDER BY b.ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (bingx_symbol, binance_symbol, start_ts, end_ts))
        rows = cur.fetchall()

    if not rows:
        return {"count": 0, "median_pct": 0.0, "p95_pct": 0.0, "max_pct": 0.0}

    diffs = sorted([float(r[3]) for r in rows])
    n = len(diffs)

    # Median
    if n % 2 == 1:
        med = diffs[n // 2]
    else:
        med = (diffs[n // 2 - 1] + diffs[n // 2]) / 2.0

    # p95
    p95_idx = int(n * 0.95)
    p95 = diffs[min(p95_idx, n - 1)]

    # Max
    max_diff = diffs[-1]

    return {
        "count": n,
        "median_pct": med,
        "p95_pct": p95,
        "max_pct": max_diff,
    }


def analyze_funding_intervals(conn: psycopg.Connection, symbol: str = "BTCUSDT") -> dict:
    """Phân tích khoảng cách giữa các lần settle funding rate liên tiếp."""
    sql = """
        SELECT funding_time, funding_interval_hours
        FROM binance_funding
        WHERE symbol = %s
        ORDER BY funding_time;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol,))
        rows = cur.fetchall()

    if len(rows) < 2:
        return {"total_records": len(rows), "interval_distribution": {}}

    interval_dist: dict[float, int] = {}
    for i in range(1, len(rows)):
        prev_t = rows[i - 1][0]
        curr_t = rows[i][0]
        diff_hours = round((curr_t - prev_t).total_seconds() / 3600.0, 2)
        interval_dist[diff_hours] = interval_dist.get(diff_hours, 0) + 1

    return {
        "total_records": len(rows),
        "interval_distribution": dict(sorted(interval_dist.items(), key=lambda x: -x[1])),
    }


def inspect_headers() -> dict[str, list[str]]:
    """In dòng tiêu đề nguyên văn của các loại tệp thật từ Binance Vision."""
    sample_urls = {
        "klines": f"{BASE_VISION_URL}/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip",
        "fundingRate": f"{BASE_VISION_URL}/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip",
        "metrics": f"{BASE_VISION_URL}/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-01.zip",
    }
    headers = {}
    for name, url in sample_urls.items():
        zip_bytes = fetch_url_bytes(url)
        if not zip_bytes:
            headers[name] = [f"LỖI: Không tải được {url}"]
            continue
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            csv_names = [n for n in z.namelist() if n.endswith(".csv")]
            if csv_names:
                with z.open(csv_names[0]) as f:
                    first_line = f.readline().decode("utf-8").strip()
                    headers[name] = [first_line]
    return headers


def main() -> None:
    parser = argparse.ArgumentParser(description="Tải và nạp dữ liệu Binance Vision vào DB.")
    parser.add_argument("--mode", choices=["all", "klines", "funding", "metrics", "cross_check", "inspect_headers", "stats"], default="all")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--from", dest="from_date", default="2024-01-01")
    parser.add_argument("--to", dest="to_date", default="2026-08-31")
    parser.add_argument("--force", action="store_true", help="Nạp lại kể cả khi DB đã có đủ dữ liệu")
    parser.add_argument("--rate-limit", type=float, default=MIN_RATE_LIMIT_SLEEP)
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    if args.mode == "inspect_headers":
        headers = inspect_headers()
        print("=== DÒNG TIÊU ĐỀ NGUYÊN VĂN CÁC TỆP BINANCE VISION ===")
        for k, v in headers.items():
            print(f"{k}: {v[0]}")
        return

    start_d = date.fromisoformat(args.from_date)
    end_d = date.fromisoformat(args.to_date)

    conn = psycopg.connect(resolve_dsn(args.dsn))
    init_binance_schema(conn)

    if args.mode in ("all", "klines"):
        load_all_klines(conn, symbol=args.symbol, interval=args.interval, start_date=start_d, end_date=end_d, force=args.force, rate_limit_sleep=args.rate_limit)

    if args.mode in ("all", "funding"):
        load_all_funding(conn, symbol=args.symbol, start_date=start_d, end_date=end_d, force=args.force, rate_limit_sleep=args.rate_limit)

    if args.mode in ("all", "metrics"):
        load_all_metrics(conn, symbol=args.symbol, start_date=start_d, end_date=end_d, force=args.force, rate_limit_sleep=args.rate_limit)

    if args.mode in ("all", "cross_check"):
        print("\n=== ĐỐI CHIẾU CHÉO BINANCE ↔ BINGX (NẾN 1H, 2026-08-01 -> 2026-08-31) ===")
        res = cross_check_binance_bingx(conn)
        print(f"Số nến đối chiếu: {res['count']}")
        print(f"Trung vị chênh lệch: {res['median_pct']:.4f}%")
        print(f"p95 chênh lệch     : {res['p95_pct']:.4f}%")
        print(f"Max chênh lệch     : {res['max_pct']:.4f}%")
        if res["median_pct"] > 0.5 or res["max_pct"] > 5.0:
            print("[CẢNH BÁO ĐỎ] Chênh lệch vượt ngưỡng an toàn! Cần kiểm tra lại đơn vị/múi giờ/cột.", file=sys.stderr)
        else:
            print("[ĐẠT] Chênh lệch nằm trong ngưỡng an toàn.")

        print("\n=== PHÂN BỐ KHOẢNG CÁCH FUNDING RATE ===")
        f_res = analyze_funding_intervals(conn, symbol=args.symbol)
        print(f"Tổng số bản ghi funding: {f_res['total_records']}")
        print("Phân bố khoảng cách (giờ):")
        for hours, cnt in f_res["interval_distribution"].items():
            print(f"  {hours}h: {cnt} lần ({cnt / (f_res['total_records'] - 1) * 100:.2f}%)")

    if args.mode in ("all", "stats"):
        print("\n=== THỐNG KÊ BẢNG DỮ LIỆU BINANCE ===")
        with conn.cursor() as cur:
            for tbl in ("binance_klines", "binance_funding", "binance_metrics", "binance_orderflow_1h"):
                cur.execute(f"SELECT COUNT(*), MIN(ts), MAX(ts) FROM {tbl}" if tbl != "binance_funding" else f"SELECT COUNT(*), MIN(funding_time), MAX(funding_time) FROM {tbl}")
                cnt, min_t, max_t = cur.fetchone()
                print(f"  {tbl}: {cnt} dòng | min: {min_t} | max: {max_t}")

    conn.close()


if __name__ == "__main__":
    main()
