"""Kiểm tra sức khoẻ luồng thời gian thực collector (Brief đợt 43 Task 3 / Brief đợt 49 Task 2).

Mục tiêu:
Đọc log của container collector (hoặc chuỗi log kiểm thử) và xác minh:
Trong phiên giao dịch vừa rồi, có bao nhiêu nến/dòng được chốt từ luồng thời gian thực ("bars closed")?
Tính tỷ lệ bao phủ luồng (coverage) dựa trên số nến kỳ vọng trong cơ sở dữ liệu.

Luật độ phủ luồng (Brief 49 §2.2, §2.3):
- Tử số  = tổng n nến chốt từ luồng thời gian thực trong log.
- Mẫu số = (số khung nến khác nhau có trong bảng bars) x (số mã trong khoảng đó) (từ DB).
- Tỷ lệ phủ = tử số / mẫu số.
- Phân loại:
  * 0 nến hoặc phủ < min-coverage-crit (0.50): CRITICAL -> in "dung: ..." ra stderr, exit 2.
  * min-coverage-crit <= phủ < min-coverage-warn (0.90): WARN -> in "WARN: ..." ra stdout, exit 1.
  * phủ >= min-coverage-warn (0.90): OK -> in "OK: ..." ra stdout, exit 0.
- Nếu KHÔNG truyền cờ --min-coverage-warn / --min-coverage-crit: giữ nguyên hành vi cũ (0 nến -> exit 2; > 0 nến -> exit 0).

Vì sao dùng DB làm mẫu số dù Brief 43 nói "đừng tin DB":
DB nói dối về NGUỒN GỐC của nến (do backfill bù), không nói dối về KHUNG NÀO TỒN TẠI.
Log cho biết nến nào đến từ luồng; DB cho biết tổng số nến đáng lẽ phải có.
Chính phép so này phơi ra ngày 16/09 (0%) và 17/09 (~59%).

Giới hạn đã biết: Nếu cả backfill cũng không chạy thì mẫu số nhỏ và độ phủ trông vẫn đẹp.
Công cụ không phát hiện được tình huống đó — đó là việc của heartbeat_check.

Quy tắc chọn phiên mặc định (Brief 49 §2.6):
- Chạy trước 11:30: phiên chiều ngày làm việc trước (nếu trong vòng 24h).
- Chạy 11:30 - 15:05: phiên sáng hôm nay.
- Chạy sau 15:05: phiên chiều hôm nay.
- Nếu không có phiên nào kết thúc trong 24 giờ (cuối tuần, ngày lễ): in "bo qua: ..." và exit 0.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

from trading.calendar_vn import is_trading_day

try:
    from scripts.deploy_drift_check import get_container_name
except ImportError:
    from deploy_drift_check import get_container_name

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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


class StreamBarsCount(NamedTuple):
    bars: int
    lines: int
    fallback_lines: int = 0


def count_stream_bars_closed(
    log_content: str,
    session: str,
    check_date: date,
    tz: ZoneInfo = TZ_VN,
) -> StreamBarsCount:
    """Đếm số nến chốt (bars) và số dòng log (lines) rơi trong phiên giao dịch chỉ định."""
    if session not in SESSION_HOURS:
        raise ValueError(f"Phiên '{session}' không hợp lệ. Chọn 'sang' hoặc 'chieu'.")

    t_start, t_end = SESSION_HOURS[session]
    start_dt = datetime.combine(check_date, t_start, tzinfo=tz)
    end_dt = datetime.combine(check_date, t_end, tzinfo=tz)

    bars_total = 0
    lines_total = 0
    fallback_lines = 0

    for line in log_content.splitlines():
        if "bars closed" not in line:
            continue
        ts_vn = parse_log_timestamp(line)
        if ts_vn is not None and start_dt <= ts_vn <= end_dt:
            lines_total += 1
            n_val = None
            try:
                brace_idx = line.find("{")
                if brace_idx != -1:
                    data = json.loads(line[brace_idx:])
                    n_candidate = data.get("n")
                    if (
                        isinstance(n_candidate, int)
                        and not isinstance(n_candidate, bool)
                        and n_candidate > 0
                    ):
                        n_val = n_candidate
            except Exception:
                pass

            if n_val is not None:
                bars_total += n_val
            else:
                bars_total += 1
                fallback_lines += 1

    return StreamBarsCount(
        bars=bars_total, lines=lines_total, fallback_lines=fallback_lines
    )


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
        container_name = get_container_name("collector")
        res_fb = subprocess.run(
            ["docker", "logs", "-t", container_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if res_fb.returncode == 0 and res_fb.stdout:
            return res_fb.stdout
    return res.stdout or ""


def load_holidays(config_path: str = "config/config.yaml") -> set[date]:
    """Đọc danh sách ngày lễ từ config/config.yaml (Brief 55 Task 1).

    An toàn, không yêu cầu biến môi trường DB/SSI như load_config.
    """
    p = Path(config_path)
    if not p.is_file():
        repo_root = Path(__file__).resolve().parents[1]
        p = repo_root / config_path
    if not p.is_file():
        return set()
    try:
        import yaml

        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return {date.fromisoformat(str(h)) for h in raw.get("holidays", [])}
    except Exception:
        return set()


def resolve_target_session(
    now_vn: datetime,
    holidays: set[date] | None = None,
) -> tuple[date, str] | None:
    """Xác định phiên gần nhất ĐÃ KẾT THÚC tại thời điểm chạy (Brief 49 §2.6).

    Quy tắc:
    - Nếu now_vn là ngày nghỉ cuối tuần (thứ 7, CN) hoặc ngày lễ: trả về None -> caller in 'bo qua: ...' và exit 0.
    - Nếu now_vn là ngày làm việc:
      * Chạy trước 11:30: phiên chiều ngày làm việc trước (nếu kết thúc trong vòng 24h).
      * Chạy 11:30 -> 15:05: phiên sáng hôm nay.
      * Chạy sau 15:05: phiên chiều hôm nay.
    """
    check_holidays = holidays or set()
    current_date = now_vn.date()

    # Nếu hôm nay là thứ 7 (5), Chủ Nhật (6) hoặc ngày lễ -> không có phiên kết thúc trong ngày
    if now_vn.weekday() in (5, 6) or current_date in check_holidays:
        return None

    current_time = now_vn.time()

    if current_time < time(11, 30, 0):
        # Phiên chiều ngày làm việc trước
        prev_date = current_date - timedelta(days=1)
        while prev_date.weekday() in (5, 6) or prev_date in check_holidays:
            prev_date -= timedelta(days=1)

        prev_session_end = datetime.combine(prev_date, time(15, 5, 0), tzinfo=TZ_VN)
        # Nếu phiên gần nhất kết thúc cách đây > 24 giờ (ví dụ sáng thứ Hai) -> bỏ qua
        if (now_vn - prev_session_end).total_seconds() > 24 * 3600:
            return None
        return prev_date, "chieu"

    elif time(11, 30, 0) <= current_time <= time(15, 5, 0):
        # Phiên sáng hôm nay đã kết thúc lúc 11:35
        return current_date, "sang"

    else:
        # Sau 15:05: phiên chiều hôm nay đã kết thúc
        return current_date, "chieu"


def is_session_ended(check_date: date, session: str | None, now_vn: datetime) -> bool:
    """Kiểm tra xem phiên giao dịch đã kết thúc tại thời điểm now_vn chưa (Brief 50 Task 1).

    - Phiên sáng kết thúc lúc 11:30.
    - Phiên chiều kết thúc lúc 15:05.
    - Chế độ cả ngày (session is None) coi là kết thúc khi phiên chiều đã kết thúc (15:05).
    """
    cur_date = now_vn.date()
    if check_date < cur_date:
        return True
    if check_date > cur_date:
        return False

    # check_date == cur_date
    if session == "sang":
        cutoff = datetime.combine(check_date, time(11, 30), tzinfo=TZ_VN)
    else:
        # "chieu" hoặc None (cả ngày)
        cutoff = datetime.combine(check_date, time(15, 5), tzinfo=TZ_VN)

    return now_vn >= cutoff


def fetch_expected_bars_from_db(
    check_date: date,
    session: str | None = None,
    dsn: str | None = None,
    symbols: tuple[str, ...] = ("HPG", "AAA", "IJC"),
) -> int:
    """Truy vấn PostgreSQL để tính mẫu số nến kỳ vọng theo Brief 49 §2.2.

    Mẫu số = (số khung nến khác nhau có trong bảng bars) x (số mã trong khoảng đó).
    """
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from _db_common import resolve_dsn
    except ImportError:
        from scripts._db_common import resolve_dsn

    import psycopg

    db_dsn = resolve_dsn(dsn)
    conn = psycopg.connect(db_dsn)
    with conn.cursor() as cur:
        cur.execute("SET TimeZone='Asia/Ho_Chi_Minh';")

        if session == "sang":
            cur.execute(
                """
                SELECT count(DISTINCT time_bucket('5m', ts)) as slots,
                       count(DISTINCT symbol) as syms,
                       count(*) as total_bars
                FROM bars
                WHERE ts >= (%s || ' 09:00:00+07')::timestamptz
                  AND ts <= (%s || ' 11:35:00+07')::timestamptz
                  AND symbol = ANY(%s);
            """,
                (check_date.isoformat(), check_date.isoformat(), list(symbols)),
            )
        elif session == "chieu":
            cur.execute(
                """
                SELECT count(DISTINCT time_bucket('5m', ts)) as slots,
                       count(DISTINCT symbol) as syms,
                       count(*) as total_bars
                FROM bars
                WHERE ts >= (%s || ' 13:00:00+07')::timestamptz
                  AND ts <= (%s || ' 15:05:00+07')::timestamptz
                  AND symbol = ANY(%s);
            """,
                (check_date.isoformat(), check_date.isoformat(), list(symbols)),
            )
        else:
            # Cả ngày (cả 2 phiên)
            cur.execute(
                """
                SELECT count(DISTINCT time_bucket('5m', ts)) as slots,
                       count(DISTINCT symbol) as syms,
                       count(*) as total_bars
                FROM bars
                WHERE ts >= (%s || ' 09:00:00+07')::timestamptz
                  AND ts <= (%s || ' 15:05:00+07')::timestamptz
                  AND symbol = ANY(%s)
                  AND (
                    (ts::time >= '09:00:00' AND ts::time <= '11:35:00') OR
                    (ts::time >= '13:00:00' AND ts::time <= '15:05:00')
                  );
            """,
                (check_date.isoformat(), check_date.isoformat(), list(symbols)),
            )

        row = cur.fetchone()
        slots = row[0] if row else 0
        syms = row[1] if row else 0
        total_bars = row[2] if row else 0

    conn.close()

    expected = slots * syms
    return expected if expected > 0 else total_bars


def evaluate_stream_health(
    count: int,
    denom: int | None = None,
    min_coverage_warn: float | None = None,
    min_coverage_crit: float | None = None,
) -> tuple[int, str]:
    """Đánh giá mã thoát theo số nến luồng và độ phủ (Brief 49 §2.3).

    Trả về (exit_code, level_str):
    0: OK
    1: WARN
    2: CRITICAL (dung)
    """
    if count == 0:
        return 2, "CRITICAL"

    if min_coverage_warn is None and min_coverage_crit is None:
        return 0, "OK"

    crit_thresh = min_coverage_crit if min_coverage_crit is not None else 0.50
    warn_thresh = min_coverage_warn if min_coverage_warn is not None else 0.90

    if denom is None or denom <= 0:
        return 0, "OK"

    coverage = count / denom
    if coverage < crit_thresh:
        return 2, "CRITICAL"
    elif coverage < warn_thresh:
        return 1, "WARN"
    else:
        return 0, "OK"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kiểm tra sức khoẻ luồng SSI thời gian thực (Brief 43 & Brief 49)."
    )
    parser.add_argument(
        "--session",
        choices=["sang", "chieu"],
        default=None,
        help="Phiên giao dịch (sang hoặc chieu)",
    )
    parser.add_argument("--date", default=None, help="Ngày kiểm tra (YYYY-MM-DD)")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Đường dẫn file log để đọc (dùng cho test/audit)",
    )
    parser.add_argument(
        "--persistent-log",
        default=None,
        help="Đường dẫn file log bền vững (mặc định logs/bars_closed.log)",
    )
    parser.add_argument(
        "--min-coverage-warn",
        type=float,
        default=None,
        help="Ngưỡng cảnh báo độ phủ luồng (ví dụ 0.90)",
    )
    parser.add_argument(
        "--min-coverage-crit",
        type=float,
        default=None,
        help="Ngưỡng nghiêm trọng độ phủ luồng (ví dụ 0.50)",
    )
    parser.add_argument(
        "--expected-bars",
        type=int,
        default=None,
        help="Số nến kỳ vọng mẫu số (mock cho test)",
    )
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()
    now_vn = datetime.now(TZ_VN)
    holidays = load_holidays()

    # 3 tổ hợp tham số theo Brief 49 §2.6
    if args.date and args.session:
        check_date = date.fromisoformat(args.date)
        session = args.session
        target_name = f"phien {session}"
    elif args.date and not args.session:
        check_date = date.fromisoformat(args.date)
        session = None
        target_name = "ca ngay"
    else:
        # Cả hai đều thiếu: chọn phiên gần nhất ĐÃ KẾT THÚC (Brief 55 Task 1.1b: nối dây holidays)
        resolved = resolve_target_session(now_vn, holidays=holidays)
        if resolved is None:
            print(
                "bo qua: khong co phien giao dich nao ket thuc trong vong 24 gio (ngay nghi/cuoi tuan)"
            )
            sys.exit(0)
        check_date, session = resolved
        target_name = f"phien {session}"

    # Brief 55 Task 1.2: Ba cửa kiểm tra theo thứ tự:
    # 1. ngay nghi?        -> bo qua, exit 0
    # 2. phien chua xong?  -> bo qua, exit 0     (dot 50)
    # 3. do do phu luong                          (dot 47/49)
    if not is_trading_day(check_date, holidays=holidays):
        print(f"bo qua: {check_date.isoformat()} la ngay nghi")
        sys.exit(0)

    # 2. Phiên chưa kết thúc thì bỏ qua, không kêu (Brief 50 Task 1)
    if not is_session_ended(check_date, session, now_vn):
        print(
            f"bo qua: {target_name} ngay {check_date.isoformat()} chua ket thuc tai thoi diem kiem tra"
        )
        sys.exit(0)

    # Brief 52 Task 1.3: Thứ tự ưu tiên nguồn log:
    # 1. args.log_file (nếu truyền cờ --log-file, dùng cho audit/test riêng).
    # 2. File bền vững (args.persistent_log hoặc logs/bars_closed.log), nguồn 'file'.
    # 3. Docker container logs (fetch_docker_collector_logs), nguồn 'log'.
    repo_root = Path(__file__).resolve().parents[1]
    default_persistent_path = repo_root / "logs" / "bars_closed.log"
    persistent_path = (
        Path(args.persistent_log) if args.persistent_log else default_persistent_path
    )

    if args.log_file:
        source = "file"
        with open(args.log_file, encoding="utf-8", errors="replace") as f:
            logs = f.read()
    else:
        # File bền chỉ được ưu tiên khi nó THỰC SỰ chứa bằng chứng chốt nến. Nếu chỉ
        # có nó mà rỗng bằng chứng thì rơi về log container — nếu không, một file
        # chứa toàn alert khác (hoặc rác từ một tiến trình lạ) sẽ đè lên nguồn thật
        # và biến mọi phiên cũ thành "0 nen / exit 2".
        persistent_text = None
        if persistent_path.is_file():
            with open(persistent_path, encoding="utf-8", errors="replace") as f:
                candidate = f.read()
            if "bars closed" in candidate:
                persistent_text = candidate

        if persistent_text is not None:
            source = "file"
            logs = persistent_text
        else:
            source = "log"
            logs = fetch_docker_collector_logs()

    # Tính tử số: số nến chốt từ luồng
    if session is None:
        res_sang = count_stream_bars_closed(logs, "sang", check_date)
        res_chieu = count_stream_bars_closed(logs, "chieu", check_date)
        count = res_sang.bars + res_chieu.bars
        lines_count = res_sang.lines + res_chieu.lines
        fallback_count = res_sang.fallback_lines + res_chieu.fallback_lines
    else:
        res = count_stream_bars_closed(logs, session, check_date)
        count = res.bars
        lines_count = res.lines
        fallback_count = res.fallback_lines

    # Tính mẫu số nếu bật kiểm tra độ phủ
    denom = None
    has_coverage_check = (args.min_coverage_warn is not None) or (
        args.min_coverage_crit is not None
    )
    if has_coverage_check:
        if args.expected_bars is not None:
            denom = args.expected_bars
        else:
            try:
                denom = fetch_expected_bars_from_db(check_date, session, args.dsn)
            except Exception as e:
                sys.stderr.write(f"Loi truy van DB tinh mau so do phu: {e}\n")
                denom = None

    code, _level = evaluate_stream_health(
        count, denom, args.min_coverage_warn, args.min_coverage_crit
    )

    detail_suffix = (
        f"({count}/{denom} nen, tu {lines_count} dong log)"
        if (denom and denom > 0)
        else f"({count} nen, tu {lines_count} dong log)"
    )
    if fallback_count > 0:
        detail_suffix += f" ({fallback_count} dong khong doc duoc n, tinh 1 nen/dong)"

    if code == 2:
        if count == 0:
            sys.stderr.write(
                f"dung: {target_name} ngay {check_date.isoformat()} khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: {source}]\n"
            )
        else:
            cov_str = f"{count / denom:.1%}" if (denom and denom > 0) else "N/A"
            crit_val = (
                args.min_coverage_crit if args.min_coverage_crit is not None else 0.50
            )
            sys.stderr.write(
                f"dung: do phu luong {target_name} ngay {check_date.isoformat()} chi dat {cov_str} "
                f"{detail_suffix}, duoi nguong nghiem trong {crit_val:.0%} [nguon: {source}]\n"
            )
        sys.exit(2)
    elif code == 1:
        cov_str = f"{count / denom:.1%}" if (denom and denom > 0) else "N/A"
        warn_val = (
            args.min_coverage_warn if args.min_coverage_warn is not None else 0.90
        )
        print(
            f"WARN: do phu luong {target_name} ngay {check_date.isoformat()} dat {cov_str} "
            f"{detail_suffix}, duoi nguong canh bao {warn_val:.0%} [nguon: {source}]"
        )
        sys.exit(1)
    else:
        if denom and denom > 0 and has_coverage_check:
            cov_str = f"{count / denom:.1%}"
            print(
                f"OK: do phu luong {target_name} ngay {check_date.isoformat()} dat {cov_str} {detail_suffix} tu luong thoi gian thuc [nguon: {source}]."
            )
        else:
            nen_detail = f"{lines_count} lan chot nen ({count} nen)"
            if fallback_count > 0:
                nen_detail += (
                    f" ({fallback_count} dong khong doc duoc n, tinh 1 nen/dong)"
                )
            print(
                f"OK: {target_name} ngay {check_date.isoformat()} co {nen_detail} tu luong thoi gian thuc [nguon: {source}]."
            )
        sys.exit(0)


if __name__ == "__main__":
    main()
