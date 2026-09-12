"""Tải và gộp dữ liệu aggTrades theo luồng thành nến 1 giờ (Brief đợt 40).

- Phạm vi: Thí điểm 1 tháng (2026-01) cho BTCUSDT, rồi DỪNG và đo tốc độ ngoại suy.
- Nguyên tắc:
  - Đọc ZIP streaming, KHÔNG giải nén ra đĩa, KHÔNG nạp toàn bộ vào RAM.
  - Tải file .CHECKSUM và đối chiếu SHA256 trước khi gộp.
  - Quy ước Binance:
      taker_buy_volume  = tổng qty khi is_buyer_maker = false
      taker_sell_volume = tổng qty khi is_buyer_maker = true
      delta             = taker_buy_volume - taker_sell_volume
      buy_ratio         = taker_buy_volume / (taker_buy_volume + taker_sell_volume)
  - Mốc :00.000 thuộc giờ mới.
  - Ghi vào binance_orderflow_1h (UPSERT).
  - Xoá tệp zip thô ngay sau khi gộp xong.
"""

import argparse
import csv
import hashlib
import io
import os
import sys
import tempfile
import time
import zipfile
from collections.abc import Iterable
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

BASE_VISION_URL = "https://data.binance.vision"
MIN_RATE_LIMIT_SLEEP = 1.05
MAX_BACKOFF_SECONDS = 300.0
INITIAL_BACKOFF_SECONDS = 2.0


def download_file_to_path(
    url: str,
    dest_path: str,
    session: requests.Session | None = None,
    max_retries: int = 5,
) -> tuple[int, str | None]:
    """Tải file stream từ url xuống dest_path, trả về (bytes_written, error_message)."""
    http = session or requests.Session()
    http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(max_retries):
        try:
            with http.get(url, stream=True, timeout=60) as resp:
                if resp.status_code == 200:
                    total_bytes = 0
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                total_bytes += len(chunk)
                    return total_bytes, None
                elif resp.status_code == 404:
                    return 0, f"File không tồn tại (404): {url}"
                elif resp.status_code == 429 or resp.status_code >= 500:
                    sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
                    print(f"[HTTP {resp.status_code}] Lùi {sleep_dur:.1f}s (lần {attempt + 1})...", file=sys.stderr)
                    time.sleep(sleep_dur)
                    backoff *= 2.0
                else:
                    return 0, f"HTTP Error {resp.status_code}: {url}"
        except requests.RequestException as e:
            sleep_dur = min(backoff, MAX_BACKOFF_SECONDS)
            print(f"[Network Error] {type(e).__name__}: {e}. Lùi {sleep_dur:.1f}s...", file=sys.stderr)
            time.sleep(sleep_dur)
            backoff *= 2.0

    return 0, f"Thất bại sau {max_retries} lần thử: {url}"


def fetch_checksum_text(url: str, session: requests.Session | None = None) -> str | None:
    """Tải text nội dung file checksum."""
    http = session or requests.Session()
    http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        resp = http.get(url, timeout=30)
        if resp.status_code == 200:
            time.sleep(MIN_RATE_LIMIT_SLEEP)
            return resp.text.strip().split()[0].lower()
    except Exception as e:
        print(f"Lỗi tải checksum {url}: {e}", file=sys.stderr)
    return None


def calculate_file_sha256(file_path: str) -> str:
    """Tính SHA256 của file trên đĩa qua khối 1MB."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def aggregate_aggtrades_stream(
    row_iterator: Iterable[list[str]],
    symbol: str,
) -> tuple[list[dict], int]:
    """Gộp các dòng aggTrades thành các bucket 1 giờ.

    row_iterator: Iterable các dòng csv đã split thành mảng string.
    Header thật: agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker
    Index:
      2: quantity
      5: transact_time (ms)
      6: is_buyer_maker (boolean string)

    Trả về: (danh sách nến 1h đã gộp, tổng số trade đã xử lý).
    """
    buckets: dict[datetime, dict[str, float | int]] = {}
    trade_count = 0

    for row in row_iterator:
        if not row or not row[0].strip().isdigit():
            continue

        try:
            qty = float(row[2])
            ts_ms = int(row[5])
            is_buyer_maker = row[6].strip().lower() == "true"
        except (ValueError, IndexError):
            continue

        trade_count += 1
        # Chuyển ms thành timestamp UTC
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        # Bucket 1 giờ: :00.000 thuộc về đầu giờ mới này
        hour_ts = dt.replace(minute=0, second=0, microsecond=0)

        if hour_ts not in buckets:
            buckets[hour_ts] = {
                "taker_buy": 0.0,
                "taker_sell": 0.0,
                "count": 0,
            }

        b = buckets[hour_ts]
        b["count"] += 1
        if not is_buyer_maker:
            b["taker_buy"] += qty
        else:
            b["taker_sell"] += qty

    results = []
    for h_ts in sorted(buckets.keys()):
        b = buckets[h_ts]
        tb = float(b["taker_buy"])
        ts = float(b["taker_sell"])
        total_vol = tb + ts
        delta = tb - ts
        buy_ratio = tb / total_vol if total_vol > 0 else 0.5

        results.append({
            "symbol": symbol,
            "ts": h_ts,
            "taker_buy_volume": tb,
            "taker_sell_volume": ts,
            "delta": delta,
            "buy_ratio": buy_ratio,
            "trade_count": int(b["count"]),
        })

    return results, trade_count


def upsert_binance_orderflow(conn: psycopg.Connection, records: list[dict]) -> int:
    """UPSERT dữ liệu orderflow 1h vào bảng binance_orderflow_1h."""
    if not records:
        return 0
    sql = """
        INSERT INTO binance_orderflow_1h (
            symbol, ts, taker_buy_volume, taker_sell_volume, delta, buy_ratio, trade_count
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, ts) DO UPDATE SET
            taker_buy_volume = EXCLUDED.taker_buy_volume,
            taker_sell_volume = EXCLUDED.taker_sell_volume,
            delta = EXCLUDED.delta,
            buy_ratio = EXCLUDED.buy_ratio,
            trade_count = EXCLUDED.trade_count;
    """
    rows = [
        (
            r["symbol"],
            r["ts"],
            r["taker_buy_volume"],
            r["taker_sell_volume"],
            r["delta"],
            r["buy_ratio"],
            r["trade_count"],
        )
        for r in records
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def verify_orderflow_vs_klines(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    year: int = 2026,
    month: int = 1,
) -> dict:
    """Đối soát 2 phép kiểm giữa binance_orderflow_1h và binance_klines:

    1. (taker_buy_volume + taker_sell_volume) vs klines.volume
    2. taker_buy_volume vs klines.taker_buy_volume
    """
    start_ts = datetime(year, month, 1, 0, 0, tzinfo=UTC)
    # Tính ngày kết thúc
    if month == 12:
        end_ts = datetime(year + 1, 1, 1, 0, 0, tzinfo=UTC)
    else:
        end_ts = datetime(year, month + 1, 1, 0, 0, tzinfo=UTC)

    sql = """
        SELECT
            o.ts,
            o.taker_buy_volume,
            o.taker_sell_volume,
            (o.taker_buy_volume + o.taker_sell_volume) AS of_total_vol,
            k.volume AS klines_total_vol,
            k.taker_buy_volume AS klines_taker_buy,
            ABS((o.taker_buy_volume + o.taker_sell_volume) - k.volume) / NULLIF(k.volume, 0) * 100.0 AS diff_total_pct,
            ABS(o.taker_buy_volume - k.taker_buy_volume) / NULLIF(k.taker_buy_volume, 0) * 100.0 AS diff_tb_pct
        FROM binance_orderflow_1h o
        JOIN binance_klines k
          ON o.symbol = k.symbol
         AND o.ts = k.ts
         AND k.interval = '1h'
        WHERE o.symbol = %s
          AND o.ts >= %s
          AND o.ts < %s
        ORDER BY o.ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol, start_ts, end_ts))
        rows = cur.fetchall()

    if not rows:
        return {"error": "Không có dữ liệu đối soát"}

    n = len(rows)
    diffs_total = sorted([float(r[6]) for r in rows if r[6] is not None])
    diffs_tb = sorted([float(r[7]) for r in rows if r[7] is not None])

    def calc_stats(arr: list[float]) -> tuple[float, float, float]:
        if not arr:
            return 0.0, 0.0, 0.0
        m = len(arr)
        med = arr[m // 2] if m % 2 == 1 else (arr[m // 2 - 1] + arr[m // 2]) / 2.0
        p95 = arr[min(int(m * 0.95), m - 1)]
        return med, p95, arr[-1]

    med1, p95_1, max1 = calc_stats(diffs_total)
    med2, p95_2, max2 = calc_stats(diffs_tb)

    return {
        "bars_count": n,
        "check1_total_volume": {
            "median_diff_pct": med1,
            "p95_diff_pct": p95_1,
            "max_diff_pct": max1,
            "pass": med1 <= 0.5 and max1 <= 1.0,
        },
        "check2_taker_buy_volume": {
            "median_diff_pct": med2,
            "p95_diff_pct": p95_2,
            "max_diff_pct": max2,
            "pass": med2 <= 0.5 and max2 <= 1.0,
        },
    }


def run_pilot_month(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    year: int = 2026,
    month: int = 1,
) -> dict:
    """Thực hiện thí điểm 1 tháng aggTrades theo §2.1.

    1. Tải zip và checksum, đối chiếu SHA256.
    2. Gộp streaming trực tiếp từ ZIP.
    3. Ghi vào binance_orderflow_1h.
    4. Xoá zip thô ngay lập tức.
    5. Đối soát với binance_klines.
    6. Đo đạc tốc độ, kích thước và ngoại suy.
    """
    rel_path = f"data/futures/um/monthly/aggTrades/{symbol}/{symbol}-aggTrades-{year}-{month:02d}.zip"
    zip_url = f"{BASE_VISION_URL}/{rel_path}"
    checksum_url = f"{zip_url}.CHECKSUM"

    print(f"=== BẮT ĐẦU THÍ ĐIỂM ORDER FLOW: {symbol} THÁNG {year}-{month:02d} ===")
    print(f"URL: {zip_url}")

    # Bước 1: Tải Checksum
    expected_sha256 = fetch_checksum_text(checksum_url)
    if not expected_sha256:
        raise RuntimeError(f"Không lấy được checksum từ: {checksum_url}")
    print(f"SHA256 kỳ vọng: {expected_sha256}")

    # Bước 2: Tải file zip vào temp file
    temp_dir = tempfile.gettempdir()
    temp_zip_path = os.path.join(temp_dir, f"{symbol}-aggTrades-{year}-{month:02d}.zip")

    t_download_start = time.perf_counter()
    bytes_downloaded, err = download_file_to_path(zip_url, temp_zip_path)
    t_download_end = time.perf_counter()

    if err or bytes_downloaded == 0:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        raise RuntimeError(f"Lỗi tải ZIP: {err}")

    download_seconds = t_download_end - t_download_start
    zip_size_mb = bytes_downloaded / (1024 * 1024)
    peak_disk_mb = zip_size_mb
    print(f"Đã tải {zip_size_mb:.2f} MB trong {download_seconds:.2f}s ({zip_size_mb / max(download_seconds, 0.001):.2f} MB/s)")

    # Bước 3: Kiểm tra SHA256
    calc_sha256 = calculate_file_sha256(temp_zip_path)
    if calc_sha256 != expected_sha256:
        os.remove(temp_zip_path)
        raise RuntimeError(f"Lệch SHA256! (calc={calc_sha256}, exp={expected_sha256})")
    print("SHA256 khớp 100%!")

    # Bước 4: Stream gộp nến từ file ZIP
    t_agg_start = time.perf_counter()
    header_line = ""
    with zipfile.ZipFile(temp_zip_path) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            os.remove(temp_zip_path)
            raise RuntimeError("Không tìm thấy file CSV trong ZIP")

        with z.open(csv_names[0]) as raw_f:
            # Đọc dòng đầu tiên để lấy header nguyên văn
            text_wrapper = io.TextIOWrapper(raw_f, encoding="utf-8")
            reader = csv.reader(text_wrapper)
            first_row = next(reader)
            header_line = ",".join(first_row)
            print(f"Dòng tiêu đề nguyên văn: {header_line}")

            records, trade_count = aggregate_aggtrades_stream(reader, symbol)

    t_agg_end = time.perf_counter()
    aggregate_seconds = t_agg_end - t_agg_start
    print(f"Gộp xong {trade_count:,} trades thành {len(records)} nến 1h trong {aggregate_seconds:.2f}s")

    # Bước 5: Ghi vào DB
    inserted_bars = upsert_binance_orderflow(conn, records)
    print(f"Ghi thành công {inserted_bars} nến vào binance_orderflow_1h.")

    # Bước 6: Xoá file ZIP ngay lập tức!
    if os.path.exists(temp_zip_path):
        os.remove(temp_zip_path)
        print(f"Đã xoá tệp ZIP thô: {temp_zip_path}. Đĩa đã giải phóng về 0 MB phụ trội.")

    # Bước 7: Đối soát
    verification = verify_orderflow_vs_klines(conn, symbol, year, month)

    # Bước 8: Ngoại suy cho 32 tháng
    total_seconds_1_month = download_seconds + aggregate_seconds
    extrapolated_seconds_32_months = total_seconds_1_month * 32
    extrapolated_hours = extrapolated_seconds_32_months / 3600.0

    report = {
        "symbol": symbol,
        "month": f"{year}-{month:02d}",
        "header_line": header_line,
        "zip_size_mb": zip_size_mb,
        "download_seconds": download_seconds,
        "aggregate_seconds": aggregate_seconds,
        "total_seconds": total_seconds_1_month,
        "peak_disk_mb": peak_disk_mb,
        "trade_count": trade_count,
        "bars_count": len(records),
        "extrapolated_hours_32_months": extrapolated_hours,
        "verification": verification,
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Tải và gộp thí điểm aggTrades thành nến 1h (Brief đợt 40).")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    report = run_pilot_month(conn, symbol=args.symbol, year=args.year, month=args.month)

    print("\n================ BÁO CÁO THÍ ĐIỂM TASK 2 ================")
    print(f"Dòng tiêu đề nguyên văn : {report['header_line']}")
    print(f"Kích thước tệp ZIP      : {report['zip_size_mb']:.2f} MB")
    print(f"Thời gian tải           : {report['download_seconds']:.2f} s")
    print(f"Thời gian gộp           : {report['aggregate_seconds']:.2f} s")
    print(f"Tổng thời gian 1 tháng  : {report['total_seconds']:.2f} s")
    print(f"Đỉnh dung lượng đĩa dùng: {report['peak_disk_mb']:.2f} MB")
    print(f"Số dòng aggTrade đã đọc : {report['trade_count']:,}")
    print(f"Số nến 1h sinh ra       : {report['bars_count']} (kỳ vọng: 744)")
    print(f"Ngoại suy 32 tháng      : {report['extrapolated_hours_32_months']:.2f} giờ")

    v = report["verification"]
    print("\n--- KẾT QUẢ ĐỐI SOÁT ---")
    c1 = v["check1_total_volume"]
    print(f"Đối soát 1 (Tổng vol vs klines.volume): Trung vị lệch = {c1['median_diff_pct']:.6f}%, Max lệch = {c1['max_diff_pct']:.6f}% -> {'PASS' if c1['pass'] else 'FAIL'}")
    c2 = v["check2_taker_buy_volume"]
    print(f"Đối soát 2 (Taker buy vs klines.taker_buy): Trung vị lệch = {c2['median_diff_pct']:.6f}%, Max lệch = {c2['max_diff_pct']:.6f}% -> {'PASS' if c2['pass'] else 'FAIL'}")

    conn.close()


if __name__ == "__main__":
    main()
