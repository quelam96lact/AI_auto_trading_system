"""Kiểm tra sức khoẻ luồng thời gian thực collector (Brief đợt 43 Task 3).

Mục tiêu:
Đọc log của container collector (hoặc chuỗi log kiểm thử) và xác minh:
Trong phiên giao dịch vừa rồi, có bao nhiêu nến/dòng được chốt từ luồng thời gian thực ("bars closed")?

Luật:
- Đếm số dòng có chữ "bars closed" rơi đúng trong khoảng thời gian của phiên.
- 0 dòng -> in "dung: ..." ra stderr và exit 2 (CRITICAL).
- > 0 dòng -> in số dòng ra stdout và exit 0 (OK).

Phiên giao dịch VN (Asia/Ho_Chi_Minh):
- Phiên sáng (sang): 09:00:00 -> 11:35:00
- Phiên chiều (chieu): 13:00:00 -> 15:05:00
"""

import argparse
import re
import subprocess
import sys
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

SESSION_HOURS = {
    "sang": (time(9, 0, 0), time(11, 35, 0)),
    "chieu": (time(13, 0, 0), time(15, 5, 0)),
}

TIMESTAMP_REGEX = re.compile(
    r"(?:collector(?:-\d+)?\s*\|\s*)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


def parse_log_timestamp(line: str) -> datetime | None:
    """Trích xuất và chuẩn hoá timestamp của dòng log về timezone Asia/Ho_Chi_Minh."""
    match = TIMESTAMP_REGEX.search(line)
    if not match:
        return None
    raw_ts = match.group(1).replace(" ", "T")
    try:
        # Xử lý trailing nanoseconds nếu quá 6 chữ số microsecond
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


def count_stream_bars_closed(
    log_content: str,
    session: str,
    check_date: date,
    tz: ZoneInfo = TZ_VN,
) -> int:
    """Đếm số dòng 'bars closed' rơi trong phiên giao dịch chỉ định."""
    if session not in SESSION_HOURS:
        raise ValueError(f"Phiên '{session}' không hợp lệ. Chọn 'sang' hoặc 'chieu'.")

    t_start, t_end = SESSION_HOURS[session]
    start_dt = datetime.combine(check_date, t_start, tzinfo=tz)
    end_dt = datetime.combine(check_date, t_end, tzinfo=tz)

    count = 0
    for line in log_content.splitlines():
        if "bars closed" not in line:
            continue
        ts_vn = parse_log_timestamp(line)
        if ts_vn is not None and start_dt <= ts_vn <= end_dt:
            count += 1
    return count


def fetch_docker_collector_logs() -> str:
    """Lấy log của container collector qua docker compose logs -t."""
    res = subprocess.run(
        ["docker", "compose", "logs", "collector", "-t", "--no-color"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if res.returncode != 0 or not res.stdout:
        res_fb = subprocess.run(
            ["docker", "logs", "-t", "ai_auto_trading_system-collector-1"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if res_fb.returncode == 0 and res_fb.stdout:
            return res_fb.stdout
    return res.stdout or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiểm tra sức khoẻ luồng SSI thời gian thực (Brief 43 Task 3).")
    parser.add_argument("--session", choices=["sang", "chieu"], default=None, help="Phiên giao dịch (sang hoặc chieu)")
    parser.add_argument("--date", default=None, help="Ngày kiểm tra (YYYY-MM-DD), mặc định hôm nay")
    parser.add_argument("--log-file", default=None, help="Đường dẫn file log để đọc (dùng cho test/audit)")

    args = parser.parse_args()

    now_vn = datetime.now(TZ_VN)
    check_date = date.fromisoformat(args.date) if args.date else now_vn.date()

    if args.session:
        session = args.session
    else:
        session = "sang" if now_vn.hour < 12 else "chieu"

    if args.log_file:
        with open(args.log_file, encoding="utf-8", errors="replace") as f:
            logs = f.read()
    else:
        logs = fetch_docker_collector_logs()

    count = count_stream_bars_closed(logs, session, check_date)

    if count == 0:
        sys.stderr.write(
            f"dung: phien {session} ngay {check_date.isoformat()} khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)\n"
        )
        sys.exit(2)
    else:
        print(f"OK: phien {session} ngay {check_date.isoformat()} co {count} lan chot nen tu luong thoi gian thuc.")
        sys.exit(0)


if __name__ == "__main__":
    main()
