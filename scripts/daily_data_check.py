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
from datetime import datetime
from pathlib import Path

# Đảm bảo import được _db_common và trading
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import resolve_dsn

from trading.alerts import _print_safe
from trading.calendar_vn import TZ, is_trading_day
from trading.config import load_config
from trading.storage.db import Storage
from trading.telegram import send_telegram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiểm tra các mã active đã có bar daily của phiên gần nhất chưa"
    )
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    parser.add_argument(
        "--date",
        default=None,
        help="Ngày kiểm tra (YYYY-MM-DD), mặc định: ngày hiện tại theo giờ VN",
    )
    return parser.parse_args()


def evaluate_daily_completeness(
    active_symbols: list[str],
    present_symbols: set[str],
    is_trading_day: bool = False,
) -> tuple[int, set[str], str]:
    """Hàm thuần đánh giá trạng thái bar daily của các mã active.

    Trả về: (exit_code, missing_symbols, message)
    - exit_code 0: Đầy đủ bar, HOẶC ngày nghỉ không có bar (nhường 2A).
    - exit_code 1: Sót mã active khi feed vẫn có dữ liệu các mã khác.
    - exit_code 2: Ngày giao dịch mà KHÔNG có mã nào có bar (lỗi dữ liệu / feed chết toàn diện).
    """
    if not active_symbols:
        return 0, set(), "Không có mã active nào trong symbol_universe."

    # Nếu toàn bộ thị trường 0 có bar nào:
    if not present_symbols:
        if is_trading_day:
            msg = (
                f"🚨 [AI Trading] SỰ CỐ DỮ LIỆU: Ngày giao dịch nhưng 0 mã nào có bar daily trong DB "
                f"(toàn bộ {len(active_symbols)} mã active thiếu bar)!"
            )
            return 2, set(active_symbols), msg
        return (
            0,
            set(),
            "Không có mã nào có bar trong ngày (ngày nghỉ hoặc feed ngừng toàn diện — nhường Heartbeat 2A).",
        )

    missing = set(active_symbols) - set(present_symbols)
    if not missing:
        return (
            0,
            set(),
            f"Đầy đủ: toàn bộ {len(active_symbols)} mã active đều đã có bar daily.",
        )

    missing_list = sorted(missing)
    sample_missing = ", ".join(missing_list[:15])
    if len(missing_list) > 15:
        sample_missing += f" ... (+{len(missing_list) - 15} mã nữa)"

    msg = (
        f"⚠️ [AI Trading] CẢNH BÁO: Sót bar daily sau phiên!\n"
        f"Tổng số mã active: {len(active_symbols)}\n"
        f"Số mã có bar: {len(set(active_symbols) & set(present_symbols))}\n"
        f"Số mã THIẾU bar ({len(missing)} mã): {sample_missing}"
    )
    return 1, missing, msg


def main() -> None:
    args = parse_args()

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
    except Exception as e:
        _print_safe(f"LỖI TRUY VẤN DB: {e}")
        sys.exit(2)

    holidays = cfg.holidays
    trading_day = is_trading_day(target_date, holidays)

    code, _missing, msg = evaluate_daily_completeness(
        active_symbols, present_symbols, is_trading_day=trading_day
    )

    _print_safe(f"[{target_date}] {msg}")

    if code in (1, 2):
        # Brief 56: send_telegram khong con nem (FEE-ALARM-2) va tra bool. Truoc day
        # doan nay in "Da gui" VO DIEU KIEN — tuc la noi doi khi thieu bien moi
        # truong hoac mang hong. Bao cao dot 56 Task 2 tu neu ra lo nay.
        if send_telegram(f"[{target_date}] {msg}"):
            _print_safe("-> Đã gửi cảnh báo qua Telegram.")
        else:
            _print_safe(
                "-> KHÔNG gửi được cảnh báo qua Telegram (xem log để biết lý do)."
            )
        sys.exit(code)

    sys.exit(0)


if __name__ == "__main__":
    main()
