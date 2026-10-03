"""Kiểm tra định kỳ sau phiên: các mã is_active trong symbol_universe đã có bar daily chưa.

Hợp đồng exit code (theo đúng scripts/heartbeat_check.py):
- 0: Ổn (toàn bộ mã active đã có bar, HOẶC cả feed không có bar nào -> im lặng nhường 2A).
- 1: Đã gửi cảnh báo Telegram (feed sống nhưng sót mã active).
- 2: Sai cấu hình / không kết nối được DB.

Phân định với heartbeat 2A:
- 2A bắt "bar ngừng về" (toàn bộ feed chết).
- Job này bắt "feed sống nhưng SÓT mã". Nếu 0 mã nào có bar (feed chết hoặc ngày nghỉ),
  job này PHẢI IM LẶNG để không bắn cảnh báo trùng.

CLI:
  uv run python scripts/daily_data_check.py [--dsn ...] [--date YYYY-MM-DD]
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Đảm bảo import được _db_common và trading
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _alert_common import send_with_outbox
from _db_common import resolve_dsn

from trading.alerts import _print_safe
from trading.calendar_vn import TZ, is_trading_day, previous_trading_day
from trading.config import load_config
from trading.storage.db import Storage
from trading.telegram import send_telegram

DEFAULT_LOGS_DIR = str(Path(__file__).resolve().parents[1] / "logs")
OUTBOX_NAME = "alert_outbox_daily-check.jsonl"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kiểm tra các mã active đã có bar daily của phiên gần nhất chưa"
    )
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    parser.add_argument(
        "--date",
        default=None,
        help="Ngày kiểm tra (YYYY-MM-DD), mặc định: ngày hiện tại theo giờ VN",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="In cảnh báo thay vì gửi Telegram (chạy bù an toàn)",
    )
    parser.add_argument(
        "--logs-dir",
        default=DEFAULT_LOGS_DIR,
        help="Thư mục logs trên host, nơi đặt hàng đợi gửi lại alert_outbox_*.jsonl",
    )
    return parser


def check_backfill_completed(log_path: Path | str, target_date: date) -> bool:
    """Kiểm tra file log backfill để biết tác vụ backfill-universe cho ngày target_date đã hoàn tất chưa.

    Dấu hiệu hoàn tất:
    - Log có chứa mốc ngày target_date (ở dòng start hoặc dòng Backfill 1d: ... -> target_date)
    - Sau đó có dòng 'DONE: ok=...' và 'EXIT=0'
    """
    p = Path(log_path)
    if not p.exists():
        return False

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

    target_str = target_date.isoformat()
    blocks = content.split("backfill start")
    if len(blocks) <= 1:
        return False

    # Duyệt từ phiên chạy gần nhất ngược về trước
    for block in reversed(blocks[1:]):
        if target_str in block:
            return bool("DONE:" in block and "EXIT=0" in block)

    return False


FRIDAY_ONLY_WINDOW_TRADING_DAYS = 30


def recent_trading_days(
    check_date: date, n: int, holidays: set[date] | frozenset = frozenset()
) -> set[date]:
    """n ngay giao dich gan nhat TRUOC check_date (khong gom check_date).

    Mot cho duy nhat: friday_only_symbols() va truy van cua main() cung dung ham nay,
    de cua so cua phep loc va cua cau SQL khong the lech nhau."""
    days: set[date] = set()
    cur = check_date - timedelta(days=1)
    while len(days) < n:
        if is_trading_day(cur, holidays):
            days.add(cur)
        cur -= timedelta(days=1)
    return days


def friday_only_symbols(
    bar_dates_by_symbol: dict[str, list[date | datetime]],
    check_date: date,
    holidays: set[date] | frozenset = frozenset(),
) -> set[str]:
    """Tìm tập các mã 'chỉ-thứ-Sáu' cần loại khi kiểm tra vào các ngày không phải thứ Sáu.

    Quy tắc (Brief 97 Task 2):
    - Ngày kiểm tra là thứ Sáu (check_date.weekday() == 4): không loại mã nào (trả về set rỗng).
    - Cửa sổ: 30 ngày giao dịch gần nhất trước ngày kiểm tra (sử dụng is_trading_day với holidays).
    - Một mã là 'chỉ-thứ-Sáu' nếu trong cửa sổ đó:
        * có ít nhất 3 nến (len(dates_in_window) >= 3)
        * VÀ mọi nến đều rơi vào thứ Sáu (all(d.weekday() == 4 theo giờ VN)).
    """
    if check_date.weekday() == 4:
        return set()

    window_days = recent_trading_days(
        check_date, FRIDAY_ONLY_WINDOW_TRADING_DAYS, holidays
    )

    result: set[str] = set()
    for sym, raw_dates in bar_dates_by_symbol.items():
        # Chuyển đổi an toàn sang date theo giờ VN nếu phần tử là datetime
        dates: list[date] = []
        for d in raw_dates:
            if isinstance(d, datetime):
                dates.append(d.astimezone(TZ).date())
            else:
                dates.append(d)

        dates_in_window = [d for d in dates if d in window_days]
        if len(dates_in_window) >= 3 and all(d.weekday() == 4 for d in dates_in_window):
            result.add(sym)

    return result


def evaluate_daily_completeness(
    active_symbols: list[str],
    present_symbols: set[str],
    is_trading_day: bool = False,
    backfill_done: bool = True,
    excluded_symbols: set[str] | None = None,
    prev_backfill_done: bool = True,
) -> tuple[int, set[str], str]:
    """Hàm thuần đánh giá trạng thái bar daily của các mã active.

    Trả về: (exit_code, missing_symbols, message)
    - exit_code 0: Đầy đủ bar, HOẶC ngày nghỉ không có bar (nhường 2A).
    - exit_code 1: Sót mã active khi feed vẫn có dữ liệu các mã khác, HOẶC hoãn phán quyết do backfill chưa xong 1 ngày.
    - exit_code 2: Ngày giao dịch mà KHÔNG có mã nào có bar VÀ backfill đã hoàn tất (sự cố dữ liệu thật),
                   HOẶC backfill chưa hoàn thành 2 ngày giao dịch liên tiếp (CRITICAL leo thang - Brief 97 Task 3).
    """
    excluded = (
        (set(excluded_symbols) & set(active_symbols)) if excluded_symbols else set()
    )
    effective_active = [s for s in active_symbols if s not in excluded]

    if not effective_active:
        return 0, set(), "Không có mã active nào trong symbol_universe."

    # Ghi chú về các mã được loại trừ (nếu có)
    excluded_note = ""
    if excluded:
        excluded_list = sorted(excluded)
        excluded_note = f"\nLoại {len(excluded)} mã chỉ giao dịch thứ Sáu ({', '.join(excluded_list)})"

    # Nếu toàn bộ thị trường 0 có bar nào:
    if not present_symbols:
        if is_trading_day:
            if not backfill_done:
                if not prev_backfill_done:
                    # Task 3: 2 ngày giao dịch liên tiếp chưa hoàn thành backfill -> CRITICAL leo thang, exit 2
                    msg = (
                        "🚨 [AI Trading] SỰ CỐ DỮ LIỆU CRITICAL: backfill-universe không hoàn thành 2 ngày giao dịch liên tiếp "
                        "(ngày kiểm tra và ngày giao dịch liền trước đều chưa hoàn tất)!"
                        f"{excluded_note}"
                    )
                    return 2, set(effective_active), msg

                msg = (
                    "⚠️ [AI Trading] HOÃN PHÁN QUYẾT: Ngày giao dịch nhưng 0 mã nào có bar daily trong DB, "
                    "và tác vụ backfill-universe chưa hoàn tất (dữ liệu chưa về). Hoãn phán quyết, không báo đỏ sai."
                    f"{excluded_note}"
                )
                return 1, set(effective_active), msg

            msg = (
                f"🚨 [AI Trading] SỰ CỐ DỮ LIỆU: Ngày giao dịch nhưng 0 mã nào có bar daily trong DB "
                f"(toàn bộ {len(effective_active)} mã active thiếu bar)!"
                f"{excluded_note}"
            )
            return 2, set(effective_active), msg
        return (
            0,
            set(),
            f"Không có mã nào có bar trong ngày (ngày nghỉ hoặc feed ngừng toàn diện — nhường Heartbeat 2A).{excluded_note}",
        )

    missing = set(effective_active) - set(present_symbols)
    if not missing:
        return (
            0,
            set(),
            f"Đầy đủ: toàn bộ {len(effective_active)} mã active đều đã có bar daily.{excluded_note}",
        )

    missing_list = sorted(missing)
    sample_missing = ", ".join(missing_list[:15])
    if len(missing_list) > 15:
        sample_missing += f" ... (+{len(missing_list) - 15} mã nữa)"

    msg = (
        f"⚠️ [AI Trading] CẢNH BÁO: Sót bar daily sau phiên!\n"
        f"Tổng số mã active: {len(effective_active)}\n"
        f"Số mã có bar: {len(set(effective_active) & set(present_symbols))}\n"
        f"Số mã THIẾU bar ({len(missing)} mã): {sample_missing}"
        f"{excluded_note}"
    )
    return 1, missing, msg


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        dsn = resolve_dsn(args.dsn)
        storage = Storage(dsn)
    except Exception as e:
        _print_safe(f"LỖI CẤU HÌNH / KẾT NỐI DB: {e}")
        sys.exit(2)

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError as e:
            _print_safe(f"LỖI ĐỊNH DẠNG NGÀY (--date YYYY-MM-DD): {e}")
            sys.exit(2)
    else:
        target_date = datetime.now(TZ).date()

    try:
        # Brief 2026-09-01 (dot 2): kiem tren HOP hai tap, cung tap voi backfill
        # hang dem — neu backfill nap CAP ma kiem tra khong soi CAP, ngay CAP
        # thieu bar se khong ai biet (dung kieu hong am tham ca dot nay sinh ra
        # de diet). read_must_price_symbols = cfg.symbols + ma dang nam giu.
        cfg = load_config("config/config.yaml")
        active = storage.read_active_universe()
        must_price = storage.read_must_price_symbols(
            cfg.ssi_equity_accounts, cfg.symbols
        )
        active_symbols = sorted(set(active) | set(must_price))
        present_symbols = storage.read_symbols_with_bar_on_date(target_date)

        # Brief 97 Task 2: Xác định các mã chỉ giao dịch thứ Sáu
        holidays = cfg.holidays
        bar_dates_by_symbol: dict[str, list[date]] = {}
        if target_date.weekday() != 4:
            min_date = min(
                recent_trading_days(
                    target_date, FRIDAY_ONLY_WINDOW_TRADING_DAYS, holidays
                )
            )
            bar_dates_by_symbol = storage.read_daily_bar_dates(
                active_symbols, min_date, target_date
            )

        excluded = friday_only_symbols(bar_dates_by_symbol, target_date, holidays)
    except Exception as e:
        _print_safe(f"LỖI TRUY VẤN DB: {e}")
        sys.exit(2)

    trading_day = is_trading_day(target_date, holidays)

    backfill_log = Path("logs/backfill.log")
    backfill_done = check_backfill_completed(backfill_log, target_date)
    prev_date = previous_trading_day(target_date, holidays)
    prev_backfill_done = check_backfill_completed(backfill_log, prev_date)

    code, _missing, msg = evaluate_daily_completeness(
        active_symbols,
        present_symbols,
        is_trading_day=trading_day,
        backfill_done=backfill_done,
        excluded_symbols=excluded,
        prev_backfill_done=prev_backfill_done,
    )

    _print_safe(f"[{target_date}] {msg}")

    if code in (1, 2):
        if args.dry_run:
            _print_safe(f"[DRY-RUN] Không gửi Telegram (mã thoát {code}).")
            sys.exit(code)
        # Brief 56: send_telegram khong con nem (FEE-ALARM-2) va tra bool. Truoc day
        # doan nay in "Da gui" VO DIEU KIEN — tuc la noi doi khi thieu bien moi
        # truong hoac mang hong. Bao cao dot 56 Task 2 tu neu ra lo nay.
        # Brief 157: gui qua hang doi gui lai. Ma thoat `code` KHONG doi theo viec
        # gui duoc hay khong (hanh vi san co; bang chinh sach dot 156 dua vao do).
        outbox_path = Path(args.logs_dir) / OUTBOX_NAME
        if send_with_outbox(
            f"[{target_date}] {msg}", send=send_telegram, outbox_path=outbox_path
        ):
            _print_safe("-> Đã gửi cảnh báo qua Telegram.")
        else:
            _print_safe(
                "-> KHÔNG gửi được cảnh báo qua Telegram (xem log để biết lý do)."
            )
            _print_safe(
                f"[HANG DOI] Tin CHƯA tới người, đã xếp hàng trong {outbox_path} "
                "— sẽ gửi lại ở lần chạy sau (21:00 ngày hôm sau)."
            )
        sys.exit(code)

    sys.exit(0)


if __name__ == "__main__":
    main()
