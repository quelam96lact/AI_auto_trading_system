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


def check_month_orderflow_loaded(
    conn: psycopg.Connection,
    symbol: str,
    year: int,
    month: int,
) -> tuple[bool, int]:
    """Kiểm tra xem tháng orderflow đã có đủ số nến trong DB chưa."""
    import calendar

    days = calendar.monthrange(year, month)[1]
    expected_bars = days * 24
    start_ts = datetime(year, month, 1, 0, 0, tzinfo=UTC)
    end_ts = datetime(year + 1, 1, 1, 0, 0, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, 0, 0, tzinfo=UTC)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM binance_orderflow_1h WHERE symbol = %s AND ts >= %s AND ts < %s",
            (symbol, start_ts, end_ts),
        )
        count = cur.fetchone()[0]

    return count >= expected_bars, count


def parse_month_string(s: str) -> tuple[int, int]:
    """Parse chuỗi 'YYYY-MM' thành (year, month)."""
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Định dạng tháng không hợp lệ: '{s}'. Cần 'YYYY-MM'.")
    return int(parts[0]), int(parts[1])


def generate_months_between(start_ym: tuple[int, int], end_ym: tuple[int, int]) -> list[tuple[int, int]]:
    """Tạo danh sách (year, month) từ start_ym tới end_ym."""
    res = []
    y, m = start_ym
    ey, em = end_ym
    while (y < ey) or (y == ey and m <= em):
        res.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return res


def process_orderflow_month(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    year: int = 2026,
    month: int = 1,
) -> dict:
    """Tải, gộp streaming và nạp 1 tháng order flow (xoá zip thô ngay sau khi gộp)."""
    rel_path = f"data/futures/um/monthly/aggTrades/{symbol}/{symbol}-aggTrades-{year}-{month:02d}.zip"
    zip_url = f"{BASE_VISION_URL}/{rel_path}"
    checksum_url = f"{zip_url}.CHECKSUM"

    # Bước 1: Tải Checksum
    expected_sha256 = fetch_checksum_text(checksum_url)
    if not expected_sha256:
        raise RuntimeError(f"Không lấy được checksum từ: {checksum_url}")

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

    # Bước 3: Kiểm tra SHA256
    calc_sha256 = calculate_file_sha256(temp_zip_path)
    if calc_sha256 != expected_sha256:
        os.remove(temp_zip_path)
        raise RuntimeError(f"Lệch SHA256! (calc={calc_sha256}, exp={expected_sha256})")

    # Bước 4: Stream gộp nến từ file ZIP
    t_agg_start = time.perf_counter()
    header_line = ""
    with zipfile.ZipFile(temp_zip_path) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            os.remove(temp_zip_path)
            raise RuntimeError("Không tìm thấy file CSV trong ZIP")

        with z.open(csv_names[0]) as raw_f:
            text_wrapper = io.TextIOWrapper(raw_f, encoding="utf-8")
            reader = csv.reader(text_wrapper)
            first_row = next(reader)
            header_line = ",".join(first_row)

            records, trade_count = aggregate_aggtrades_stream(reader, symbol)

    t_agg_end = time.perf_counter()
    aggregate_seconds = t_agg_end - t_agg_start

    # Bước 5: Ghi vào DB
    inserted_bars = upsert_binance_orderflow(conn, records)

    # Bước 6: Xoá file ZIP ngay lập tức!
    if os.path.exists(temp_zip_path):
        os.remove(temp_zip_path)

    # Thống kê
    total_seconds = download_seconds + aggregate_seconds
    return {
        "symbol": symbol,
        "month": f"{year}-{month:02d}",
        "header_line": header_line,
        "zip_size_mb": zip_size_mb,
        "download_seconds": download_seconds,
        "aggregate_seconds": aggregate_seconds,
        "total_seconds": total_seconds,
        "trade_count": trade_count,
        "bars_count": inserted_bars,
    }


def run_orderflow_range(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    from_month: str = "2024-01",
    to_month: str = "2026-08",
    force: bool = False,
) -> list[dict]:
    """Chạy tuần tự từng tháng trong khoảng. Bỏ qua tháng đã nạp đủ."""
    start_ym = parse_month_string(from_month)
    end_ym = parse_month_string(to_month)
    months = generate_months_between(start_ym, end_ym)
    total_m = len(months)

    print(f"=== BẮT ĐẦU NẠP ORDER FLOW: {symbol} TỪ {from_month} ĐẾN {to_month} ({total_m} THÁNG) ===")
    results = []

    for idx, (y, m) in enumerate(months, 1):
        m_str = f"{y}-{m:02d}"
        is_loaded, current_cnt = check_month_orderflow_loaded(conn, symbol, y, m)

        if not force and is_loaded:
            print(f"[{idx}/{total_m}] Tháng {m_str}: Đã nạp đủ trong DB ({current_cnt} nến) -> Bỏ qua.")
            results.append({
                "month": m_str,
                "status": "SKIPPED_ALREADY_LOADED",
                "bars_count": current_cnt,
            })
            continue

        print(f"[{idx}/{total_m}] Tháng {m_str}: Đang tải và gộp...")
        res = process_orderflow_month(conn, symbol, y, m)
        print(
            f"[{idx}/{total_m}] Tháng {m_str}: Đã nạp {res['bars_count']} nến | "
            f"{res['zip_size_mb']:.2f} MB | Tải: {res['download_seconds']:.1f}s | "
            f"Gộp: {res['aggregate_seconds']:.1f}s ({res['trade_count']:,} trades)"
        )
        res["status"] = "LOADED"
        results.append(res)

    print(f"=== HOÀN THÀNH KHOẢNG {from_month} -> {to_month} ===")
    return results


def verify_orderflow_full_range(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
) -> dict:
    """Kiểm chứng toàn bộ dữ liệu order flow trong DB:

    1. Tổng số dòng, min ts, max ts
    2. Đối soát toàn bộ nến với binance_klines (taker_buy_volume và total volume)
    3. Tương quan delta và lợi suất cùng giờ (close - open) / open
    """
    sql = """
        SELECT
            o.ts,
            o.taker_buy_volume,
            o.taker_sell_volume,
            o.delta,
            k.open,
            k.close,
            k.volume,
            k.taker_buy_volume,
            ABS(o.taker_buy_volume - k.taker_buy_volume) / NULLIF(k.taker_buy_volume, 0) * 100.0 AS diff_tb_pct,
            ABS((o.taker_buy_volume + o.taker_sell_volume) - k.volume) / NULLIF(k.volume, 0) * 100.0 AS diff_vol_pct
        FROM binance_orderflow_1h o
        JOIN binance_klines k
          ON o.symbol = k.symbol
         AND o.ts = k.ts
         AND k.interval = '1h'
        WHERE o.symbol = %s
        ORDER BY o.ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol,))
        rows = cur.fetchall()

    if not rows:
        return {"error": "Không có dữ liệu đối soát"}

    n = len(rows)
    min_ts = rows[0][0]
    max_ts = rows[-1][0]

    diffs_tb = sorted([float(r[8]) for r in rows if r[8] is not None])
    diffs_vol = sorted([float(r[9]) for r in rows if r[9] is not None])

    def calc_stats(arr: list[float]) -> tuple[float, float, float]:
        if not arr:
            return 0.0, 0.0, 0.0
        m = len(arr)
        med = arr[m // 2] if m % 2 == 1 else (arr[m // 2 - 1] + arr[m // 2]) / 2.0
        p95 = arr[min(int(m * 0.95), m - 1)]
        return med, p95, arr[-1]

    med_tb, p95_tb, max_tb = calc_stats(diffs_tb)
    med_vol, p95_vol, max_vol = calc_stats(diffs_vol)

    # Tính tương quan delta vs return cùng giờ: ret = (close - open) / open
    deltas = []
    rets = []
    for r in rows:
        delta = float(r[3])
        o_price = float(r[4])
        c_price = float(r[5])
        if o_price > 0:
            ret = (c_price - o_price) / o_price
            deltas.append(delta)
            rets.append(ret)

    # Spearman rank correlation
    def spearman_corr(x: list[float], y: list[float]) -> float:
        if len(x) < 2:
            return 0.0
        n_pts = len(x)

        def rank(vals: list[float]) -> list[float]:
            sorted_indices = sorted(range(n_pts), key=lambda i: vals[i])
            ranks = [0.0] * n_pts
            i = 0
            while i < n_pts:
                j = i
                while j < n_pts - 1 and vals[sorted_indices[j]] == vals[sorted_indices[j + 1]]:
                    j += 1
                avg_rank = (i + j + 2) / 2.0
                for k in range(i, j + 1):
                    ranks[sorted_indices[k]] = avg_rank
                i = j + 1
            return ranks

        rx = rank(x)
        ry = rank(y)
        mx = sum(rx) / n_pts
        my = sum(ry) / n_pts
        num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n_pts))
        den = (sum((rx[i] - mx) ** 2 for i in range(n_pts)) * sum((ry[i] - my) ** 2 for i in range(n_pts))) ** 0.5
        return num / den if den > 0 else 0.0

    corr_spearman = spearman_corr(deltas, rets)

    return {
        "total_bars": n,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "taker_buy_check": {
            "median_diff_pct": med_tb,
            "p95_diff_pct": p95_tb,
            "max_diff_pct": max_tb,
            "pass": med_tb <= 0.5,
        },
        "total_volume_check": {
            "median_diff_pct": med_vol,
            "p95_diff_pct": p95_vol,
            "max_diff_pct": max_vol,
            "pass": med_vol <= 0.5,
        },
        "delta_return_correlation": corr_spearman,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tải và gộp aggTrades thành nến 1h (Brief đợt 40 & 41).")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument("--from-month", dest="from_month", default=None, help="Tháng bắt đầu (YYYY-MM)")
    parser.add_argument("--to-month", dest="to_month", default=None, help="Tháng kết thúc (YYYY-MM)")
    parser.add_argument("--force", action="store_true", help="Nạp lại kể cả khi DB đã có đủ")
    parser.add_argument("--verify-all", action="store_true", help="Chỉ chạy đối soát trên toàn bộ DB")
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()
    conn = psycopg.connect(resolve_dsn(args.dsn))

    if args.verify_all:
        print(f"=== ĐỐI SOÁT TOÀN KỲ ORDER FLOW CHO {args.symbol} ===")
        res = verify_orderflow_full_range(conn, symbol=args.symbol)
        print(f"Tổng số nến trong DB: {res['total_bars']:,}")
        print(f"Mốc đầu (UTC)       : {res['min_ts']}")
        print(f"Mốc cuối (UTC)      : {res['max_ts']}")
        tb = res["taker_buy_check"]
        print(f"Đối soát Taker Buy  : Median={tb['median_diff_pct']:.6f}%, Max={tb['max_diff_pct']:.6f}% -> {'PASS' if tb['pass'] else 'FAIL'}")
        vol = res["total_volume_check"]
        print(f"Đối soát Total Vol  : Median={vol['median_diff_pct']:.6f}%, Max={vol['max_diff_pct']:.6f}% -> {'PASS' if vol['pass'] else 'FAIL'}")
        print(f"Tương quan Delta vs Lợi suất cùng giờ (Spearman rho): {res['delta_return_correlation']:+.4f}")
        conn.close()
        return

    if args.from_month and args.to_month:
        results = run_orderflow_range(conn, symbol=args.symbol, from_month=args.from_month, to_month=args.to_month, force=args.force)
        loaded_count = sum(1 for r in results if r.get("status") == "LOADED")
        skipped_count = sum(1 for r in results if r.get("status") == "SKIPPED_ALREADY_LOADED")
        print(f"\nTổng kết: {loaded_count} tháng mới nạp, {skipped_count} tháng bỏ qua.")

        print("\n=== ĐỐI SOÁT TOÀN KỲ SAU KHI NẠP ===")
        v_all = verify_orderflow_full_range(conn, symbol=args.symbol)
        print(f"Tổng số nến trong DB: {v_all['total_bars']:,}")
        print(f"Mốc đầu (UTC)       : {v_all['min_ts']}")
        print(f"Mốc cuối (UTC)      : {v_all['max_ts']}")
        tb = v_all["taker_buy_check"]
        print(f"Đối soát Taker Buy  : Median={tb['median_diff_pct']:.6f}%, Max={tb['max_diff_pct']:.6f}% -> {'PASS' if tb['pass'] else 'FAIL'}")
        print(f"Tương quan Delta vs Lợi suất cùng giờ (Spearman rho): {v_all['delta_return_correlation']:+.4f}")
    else:
        # Tương thích ngược: 1 tháng
        res = process_orderflow_month(conn, symbol=args.symbol, year=args.year, month=args.month)
        print(f"Hoàn thành tháng {args.year}-{args.month:02d}: {res['bars_count']} nến.")
        v = verify_orderflow_vs_klines(conn, symbol=args.symbol, year=args.year, month=args.month)
        print("Kết quả đối soát:", v)

    conn.close()


if __name__ == "__main__":
    main()


