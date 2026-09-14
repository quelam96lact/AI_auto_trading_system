"""Đo đạc chỉ số chốt nến thời gian thực phiên chiều (Brief 43 Task 2 / Brief 36 Task 3).

Chạy sau 15:05 ngày giao dịch:
- Tiêu chí B: Khớp số nến duy nhất từ luồng vs DB bars.
- Tiêu chí C: Khung 14:45 có mặt đủ cả 3 mã HPG, IJC, AAA.
- Phân bố lag_ms: min, p25, median, p75, p90, p95, max.
- Phân bố late_ms: median, p95, max, tỷ lệ snapshot đến muộn.
- Đề xuất grace dựa trên dữ liệu thực tế.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.metrics import calculate_percentile

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

TIMESTAMP_REGEX = re.compile(
    r"(?:collector(?:-\d+)?\s*\|\s*)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def parse_timestamp_vn(line: str) -> datetime | None:
    match = TIMESTAMP_REGEX.search(line)
    if not match:
        return None
    raw_ts = match.group(1).replace(" ", "T")
    try:
        if "." in raw_ts:
            dot_idx = raw_ts.find(".")
            tz_part = ""
            for idx in range(dot_idx + 1, len(raw_ts)):
                if raw_ts[idx] in ("Z", "+", "-"):
                    tz_part = raw_ts[idx:]
                    raw_ts = raw_ts[: min(dot_idx + 7, idx)] + tz_part
                    break
            else:
                raw_ts = raw_ts[: dot_idx + 7]
        dt = datetime.fromisoformat(raw_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(TZ_VN)
    except Exception:
        return None


def fetch_collector_logs_since(since: str = "4h") -> str:
    res = subprocess.run(
        ["docker", "compose", "logs", "collector", "-t", "--since", since, "--no-color"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return res.stdout or ""


def analyze_afternoon_session(logs: str, check_date: date, conn: psycopg.Connection):
    start_session = datetime.combine(check_date, time(13, 0, 0), tzinfo=TZ_VN)
    end_session = datetime.combine(check_date, time(15, 5, 0), tzinfo=TZ_VN)

    lines = logs.splitlines()

    # 1. Kiểm tra khoảng chết máy ngủ
    sleep_criticals = []
    for line in lines:
        if "CRITICAL" in line and "sleep" in line.lower() and '"in_trading_hours": true' in line:
            sleep_criticals.append(line)

    if sleep_criticals:
        print("[CẢNH BÁO] Phát hiện khoảng chết máy ngủ trong phiên (CRITICAL):")
        for s in sleep_criticals:
            print("  ", s)
        print("DỪNG: Không kết luận tiêu chí B/C trượt do phiên bị ngắt quãng.")
        return

    # 2. Thu thập các dòng bars closed và late snapshot
    bars_closed_events = []
    late_snapshots = []
    total_snapshots_count = 0

    for line in lines:
        ts_vn = parse_timestamp_vn(line)
        if ts_vn is None or not (start_session <= ts_vn <= end_session):
            continue

        if "late snapshot" in line:
            # Parse late snapshot JSON
            try:
                brace_idx = line.find("{")
                if brace_idx != -1:
                    data = json.loads(line[brace_idx:])
                    late_ms = data.get("late_ms")
                    if late_ms is not None:
                        late_snapshots.append(float(late_ms))
            except Exception:
                pass

        if "bars closed" in line:
            try:
                brace_idx = line.find("{")
                if brace_idx != -1:
                    data = json.loads(line[brace_idx:])
                    bars_closed_events.append({
                        "ts": ts_vn,
                        "n": data.get("n", 1),
                        "symbols": data.get("symbols", []),
                        "lag_ms": float(data.get("lag_ms", 0.0)),
                    })
            except Exception:
                pass

        if "snapshot" in line:
            total_snapshots_count += 1

    # 3. Thống kê lag_ms
    lags = [e["lag_ms"] for e in bars_closed_events]
    lags_sorted = sorted(lags)

    print(f"=== KẾT QUẢ ĐO ĐẠC PHIÊN CHIỀU NGÀY {check_date.isoformat()} (GIỜ VN) ===")
    print(f"Số lần chốt nến ('bars closed'): {len(bars_closed_events)}")

    # 4. Tiêu chí B & C từ DB
    sql_bars = """
        SELECT symbol, time_bucket('5m', ts) AS bar_ts, count(*)
        FROM bars
        WHERE ts >= %s AND ts <= %s
          AND symbol IN ('HPG', 'AAA', 'IJC')
        GROUP BY symbol, bar_ts
        ORDER BY bar_ts, symbol;
    """
    db_start = datetime.combine(check_date, time(13, 0, 0), tzinfo=TZ_VN)
    db_end = datetime.combine(check_date, time(14, 45, 0), tzinfo=TZ_VN)

    with conn.cursor() as cur:
        cur.execute(sql_bars, (db_start, db_end))
        db_rows = cur.fetchall()

    db_counts_by_symbol = {"HPG": 0, "AAA": 0, "IJC": 0}
    c_1445_symbols = set()

    for r in db_rows:
        sym = r[0]
        b_ts = r[1].astimezone(TZ_VN)
        if sym in db_counts_by_symbol:
            db_counts_by_symbol[sym] += 1
        if b_ts.hour == 14 and b_ts.minute == 45:
            c_1445_symbols.add(sym)

    print("\n--- TIÊU CHÍ B (SỐ NẾN DUY NHẤT PHIÊN CHIỀU) ---")
    print(f"DB bars (13:00 -> 14:45): {db_counts_by_symbol}")
    print(f"Tổng số nến trong DB: {sum(db_counts_by_symbol.values())} nến")

    print("\n--- TIÊU CHÍ C (KHUNG 14:45 GIỜ VN) ---")
    print(f"Các mã có nến 14:45: {sorted(c_1445_symbols)}")
    tieu_chi_c_pass = ({"HPG", "AAA", "IJC"} <= c_1445_symbols)
    print(f"Kết quả Tiêu chí C: {'ĐẠT (đủ 3 mã)' if tieu_chi_c_pass else 'CHƯA ĐẠT'}")

    print("\n--- PHÂN BỐ LAG_MS CỦA PHIÊN CHIỀU ---")
    if lags_sorted:
        p0 = lags_sorted[0]
        p25 = calculate_percentile(lags_sorted, 25.0)
        p50 = calculate_percentile(lags_sorted, 50.0)
        p75 = calculate_percentile(lags_sorted, 75.0)
        p90 = calculate_percentile(lags_sorted, 90.0)
        p95 = calculate_percentile(lags_sorted, 95.0)
        p100 = lags_sorted[-1]

        print(f"Min:      {p0:,.2f} ms")
        print(f"P25:      {p25:,.2f} ms")
        print(f"Trung vị: {p50:,.2f} ms  (Mốc so sánh 11/09: 14,318 ms)")
        print(f"P75:      {p75:,.2f} ms")
        print(f"P90:      {p90:,.2f} ms")
        print(f"P95:      {p95:,.2f} ms  (Mốc so sánh 11/09: 68,822 ms)")
        print(f"Max:      {p100:,.2f} ms")
    else:
        print("Không có bản ghi lag_ms nào.")

    print("\n--- PHÂN BỐ LATE_MS VÀ TỶ LỆ SNAPSHOT ĐẾN MUỘN ---")
    if late_snapshots:
        late_sorted = sorted(late_snapshots)
        lp50 = calculate_percentile(late_sorted, 50.0)
        lp95 = calculate_percentile(late_sorted, 95.0)
        lmax = late_sorted[-1]
        late_pct = (len(late_snapshots) / max(total_snapshots_count, len(late_snapshots))) * 100.0
        print(f"Số dòng late snapshot: {len(late_snapshots)}")
        print(f"Trung vị: {lp50:,.2f} ms")
        print(f"P95:      {lp95:,.2f} ms")
        print(f"Max:      {lmax:,.2f} ms")
        print(f"Tỷ lệ snapshot đến muộn: {late_pct:.2f}% ({len(late_snapshots)}/{max(total_snapshots_count, len(late_snapshots))})")
    else:
        print("Số dòng late snapshot: 0 dòng (0.0%).")

    print("\n--- ĐỀ XUẤT VỀ GRACE (HIỆN TẠI LÀ 60 GIÂY) ---")
    if lags_sorted:
        max_delay_sec = lags_sorted[-1] / 1000.0
        p95_delay_sec = calculate_percentile(lags_sorted, 95.0) / 1000.0
        print(f"P95 lag_ms thực tế: {p95_delay_sec:.2f}s, Max lag_ms: {max_delay_sec:.2f}s.")
        if max_delay_sec < 50.0:
            print("Đề xuất: Giữ nguyên grace = 60s để bảo toàn biên an toàn cho các snapshot SSI có thể đến muộn sau ATC.")
        else:
            print("Đề xuất: Cân nhắc nâng grace hoặc giữ 60s tuỳ thuộc vào phân bố late snapshot.")
    else:
        print("Chưa đủ dữ liệu để đề xuất.")


def main():
    parser = argparse.ArgumentParser(description="Đo đạc chỉ số chốt nến thời gian thực phiên chiều.")
    parser.add_argument("--date", default=None, help="Ngày kiểm tra (YYYY-MM-DD), mặc định hôm nay")
    parser.add_argument("--since", default="4h", help="Thời gian log cần lấy (mặc định 4h)")
    parser.add_argument("--dsn", default=None, help="Database DSN override")
    args = parser.parse_args()

    now_vn = datetime.now(TZ_VN)
    check_date = date.fromisoformat(args.date) if args.date else now_vn.date()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    logs = fetch_collector_logs_since(args.since)
    analyze_afternoon_session(logs, check_date, conn)
    conn.close()


if __name__ == "__main__":
    main()
