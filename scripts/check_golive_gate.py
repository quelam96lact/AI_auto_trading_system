"""Cổng kiểm tra tự động trước khi bật real_trading_enabled: true (Brief 57 Task 3).

Chạy: uv run python scripts/check_golive_gate.py [--dsn ...] [--config ...]

Quy ước mã thoát:
- 0: BẬT ĐƯỢC (Tất cả lá chắn an toàn và điều kiện bắt buộc đều ĐẠT).
- 1: CÓ CẢNH BÁO CẦN ĐỌC (Lá chắn đạt nhưng có cảnh báo không chặn trực tiếp).
- 2: KHÔNG ĐƯỢC BẬT (Ít nhất một lá chắn an toàn hoặc điều kiện bắt buộc bị HỎNG).

Ràng buộc:
- CHỈ ĐỌC (SELECT DB, đọc config, đọc log).
- KHÔNG gọi API SSI.
- KHÔNG gửi tin Telegram thật (chỉ kiểm biến môi trường).
- KHÔNG tự bật cờ real_trading_enabled.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import psycopg
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading.calendar_vn import TZ, is_trading_day
from trading.real_orders import (
    BUYING_POWER_MAX_AGE_MINUTES,
    POSITION_MAX_AGE_MINUTES,
)

# Brief 79 Task 2: Ngưỡng tuổi NAV cảnh báo (khớp ngưỡng > 24h trong trading/engine/main.py:229)
NAV_MAX_AGE_HOURS = 24


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class GateItem:
    name: str
    requirement: str
    measured_value: str
    status: str  # "PASS", "WARN", "FAIL", "INFO"
    note: str = ""


def format_currency(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.0f} VND"


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "Chưa có bản ghi"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def read_config_info(config_path: str = "config/config.yaml") -> dict:
    p = Path(config_path)
    if not p.is_file():
        p = REPO_ROOT / config_path
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def read_latest_stream_coverage(
    log_path: str = "logs/stream-health.log",
) -> tuple[float | None, str, datetime | None]:
    p = Path(log_path)
    if not p.is_file():
        p = REPO_ROOT / log_path
    if not p.is_file():
        return None, "File log không tồn tại", None

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            # Tìm dòng có chứa tỷ lệ phần trăm nến chốt (ví dụ: dat 89.5% hoặc 93,8%)
            m = re.search(r"(\d+(?:[.,]\d+)?)%", line)
            if m:
                val_str = m.group(1).replace(",", ".")
                cov = float(val_str) / 100.0

                measured_at = None
                # Tìm dòng stream-health start gần nhất phía trước dòng i
                for j in range(i - 1, -1, -1):
                    start_line = lines[j]
                    if "stream-health start" in start_line:
                        m_ts = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", start_line)
                        if m_ts:
                            try:
                                dt_raw = datetime.fromisoformat(m_ts.group(1))
                                measured_at = dt_raw.replace(tzinfo=TZ)
                            except Exception:
                                pass
                        break
                return cov, line.strip(), measured_at
        return None, "Chưa có dòng đo độ phủ nến nào trong log", None
    except Exception as e:
        return None, f"Lỗi đọc log: {e}", None


def check_telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def check_deploy_drift() -> tuple[bool, str]:
    try:
        from scripts.deploy_drift_check import (
            SERVICES,
            _git_trading_commit_epoch,
            _image_created_epoch,
            drift_report,
            get_container_name,
        )

        commit_epoch = _git_trading_commit_epoch()
        if commit_epoch is None:
            return False, "Không đọc được commit git gần nhất chạm trading/"

        images = {svc: _image_created_epoch(get_container_name(svc)) for svc in SERVICES}
        msgs = drift_report(commit_epoch, images)
        if msgs:
            return False, "; ".join(msgs)
        return True, "Image collector và engine mới hơn hoặc bằng commit trading/"
    except Exception as e:
        return False, f"Lỗi kiểm tra deploy drift: {e}"


def get_latest_completed_trading_day(
    now: datetime,
    holidays: set[date] | frozenset = frozenset(),
) -> date:
    """Xác định ngày của phiên giao dịch hoàn tất gần nhất (Brief 79 Task 1).

    Quy tắc:
    Lùi dần từng ngày từ ngày hiện tại. Ngày đầu tiên thỏa is_trading_day()
    VÀ đã qua 14:45 VN (nếu là hôm nay thì giờ >= 14:45 VN; nếu là ngày trong
    quá khứ thì phiên đó đương nhiên đã đóng cửa hoàn tất).
    """
    now_vn = now.astimezone(TZ)
    cur_date = now_vn.date()
    if is_trading_day(cur_date, holidays) and now_vn.time() >= time(14, 45):
        return cur_date

    cur_date -= timedelta(days=1)
    while True:
        if is_trading_day(cur_date, holidays):
            return cur_date
        cur_date -= timedelta(days=1)


def evaluate_golive_gate(
    real_trading_enabled: bool,
    real_account: str,
    nav: float | None,
    buying_powers: dict[str, int],  # symbol -> max_buy_qty
    buying_power_age_sec: float | None,
    position_age_sec: float | None,
    stream_coverage: float | None,
    stream_coverage_summary: str,
    telegram_configured: bool,
    deploy_drift_ok: bool,
    deploy_drift_msg: str,
    real_fills_count: int,
    symbols: list[str],
    stream_measured_at: datetime | None = None,
    stream_age_sec: float | None = None,
    nav_age_sec: float | None = None,
    now: datetime | None = None,
) -> tuple[int, list[GateItem]]:
    """Hàm thuần đánh giá các tiêu chí cổng go-live, không phụ thuộc I/O."""
    items: list[GateItem] = []

    # 1. Cờ real_trading_enabled hiện tại
    items.append(
        GateItem(
            name="real_trading_enabled (Cờ chính)",
            requirement="In ra giá trị hiện tại (chờ bật ở T5)",
            measured_value=str(real_trading_enabled),
            status="INFO",
            note="Đang là false (chuẩn bị bật sang true vào T5 sau khi pass cổng)"
            if not real_trading_enabled
            else "ĐÃ BẬT TRUE",
        )
    )

    # 2. Tài khoản và NAV (Brief 79 Task 2: Lá chắn độ tươi NAV)
    if nav is not None:
        nav_max_sec = NAV_MAX_AGE_HOURS * 3600.0
        if nav_age_sec is not None and nav_age_sec > nav_max_sec:
            age_h = nav_age_sec / 3600.0
            items.append(
                GateItem(
                    name="Tài khoản & NAV",
                    requirement=f"Tài khoản {real_account} có snapshot NAV <= {NAV_MAX_AGE_HOURS}h",
                    measured_value=f"{format_currency(nav)} ({format_age(nav_age_sec)})",
                    status="WARN",
                    note=f"NAV cũ hơn {NAV_MAX_AGE_HOURS}h ({age_h:.1f}h) — tài khoản cấu hình: {real_account}",
                )
            )
        else:
            items.append(
                GateItem(
                    name="Tài khoản & NAV",
                    requirement=f"Tài khoản {real_account} có snapshot NAV",
                    measured_value=format_currency(nav),
                    status="PASS",
                    note=f"Tài khoản cấu hình: {real_account}",
                )
            )
    else:
        items.append(
            GateItem(
                name="Tài khoản & NAV",
                requirement=f"Tài khoản {real_account} có snapshot NAV",
                measured_value="Không có dữ liệu",
                status="FAIL",
                note="Chưa có bản ghi nào trong account_nav_snapshot",
            )
        )


    # 3. Sức mua từng mã trong danh mục
    lacking_symbols = [s for s in symbols if buying_powers.get(s, 0) < 100]
    bp_detail_str = ", ".join(f"{s}: {buying_powers.get(s, 0)}cp" for s in symbols)
    if not lacking_symbols and symbols:
        items.append(
            GateItem(
                name="Sức mua tối thiểu",
                requirement="Đủ >= 100 cổ phiếu cho tất cả mã cấu hình",
                measured_value=bp_detail_str,
                status="PASS",
                note="Đạt điều kiện tối thiểu 1 lô HOSE/HNX cho toàn bộ danh mục",
            )
        )
    else:
        items.append(
            GateItem(
                name="Sức mua tối thiểu",
                requirement="Đủ >= 100 cổ phiếu cho tất cả mã cấu hình",
                measured_value=bp_detail_str,
                status="FAIL",
                note=f"Các mã không đủ 1 lô: {', '.join(lacking_symbols)}",
            )
        )

    # 4. Tuổi bản ghi vị thế (account_sync_log)
    pos_max_sec = POSITION_MAX_AGE_MINUTES * 60.0
    if position_age_sec is not None and position_age_sec <= pos_max_sec:
        items.append(
            GateItem(
                name="Lá chắn độ tươi vị thế",
                requirement=f"<= {POSITION_MAX_AGE_MINUTES} phút ({pos_max_sec:.0f}s)",
                measured_value=format_age(position_age_sec),
                status="PASS",
                note="Vị thế tươi mới, sẵn sàng cho lệnh thật",
            )
        )
    else:
        items.append(
            GateItem(
                name="Lá chắn độ tươi vị thế",
                requirement=f"<= {POSITION_MAX_AGE_MINUTES} phút ({pos_max_sec:.0f}s)",
                measured_value=format_age(position_age_sec),
                status="FAIL",
                note="Quá hạn -> Lệnh thật SẼ BỊ TỪ CHỐI nếu phát sinh",
            )
        )

    # 5. Tuổi bản ghi sức mua (account_buying_power)
    bp_max_sec = BUYING_POWER_MAX_AGE_MINUTES * 60.0
    if buying_power_age_sec is not None and buying_power_age_sec <= bp_max_sec:
        items.append(
            GateItem(
                name="Lá chắn độ tươi sức mua",
                requirement=f"<= {BUYING_POWER_MAX_AGE_MINUTES} phút ({bp_max_sec:.0f}s)",
                measured_value=format_age(buying_power_age_sec),
                status="PASS",
                note="Sức mua tươi mới, sẵn sàng cho lệnh thật",
            )
        )
    else:
        items.append(
            GateItem(
                name="Lá chắn độ tươi sức mua",
                requirement=f"<= {BUYING_POWER_MAX_AGE_MINUTES} phút ({bp_max_sec:.0f}s)",
                measured_value=format_age(buying_power_age_sec),
                status="FAIL",
                note="Quá hạn -> Lệnh thật SẼ BỊ TỪ CHỐI nếu phát sinh",
            )
        )

    # 6. Độ phủ luồng phiên gần nhất
    if stream_coverage is not None:
        cov_pct_str = f"{stream_coverage * 100:.1f}%"
        if stream_measured_at is not None and stream_age_sec is not None:
            time_str = stream_measured_at.strftime("%d/%m %H:%M")
            if stream_age_sec >= 86400:
                age_str = f"{round(stream_age_sec / 86400)} ngay truoc"
            elif stream_age_sec >= 3600:
                age_str = f"{round(stream_age_sec / 3600)} gio truoc"
            elif stream_age_sec >= 60:
                age_str = f"{round(stream_age_sec / 60)} phut truoc"
            else:
                age_str = f"{round(stream_age_sec)}s truoc"
            measured_val_str = f"{cov_pct_str} (do luc {time_str}, {age_str})"
        else:
            measured_val_str = cov_pct_str

        # Brief 79 Task 1: Tiêu chí 6 phải FAIL nếu số đo không thuộc phiên hoàn tất gần nhất
        effective_now = now or datetime.now(TZ)
        latest_completed_day = get_latest_completed_trading_day(effective_now)

        if stream_measured_at is not None and stream_measured_at.date() != latest_completed_day:
            items.append(
                GateItem(
                    name="Độ phủ luồng phiên gần nhất",
                    requirement=">= 90% số nến chốt",
                    measured_value=measured_val_str,
                    status="FAIL",
                    note=(
                        f"Số đo từ phiên {stream_measured_at.strftime('%d/%m')} "
                        f"nhưng phiên hoàn tất gần nhất là {latest_completed_day.strftime('%d/%m')} — "
                        f"không có dữ liệu luồng cho phiên gần nhất."
                    ),
                )
            )
        elif stream_coverage >= 0.90:
            items.append(
                GateItem(
                    name="Độ phủ luồng phiên gần nhất",
                    requirement=">= 90% số nến chốt",
                    measured_value=measured_val_str,
                    status="PASS",
                    note=stream_coverage_summary,
                )
            )
        elif stream_coverage >= 0.50:
            items.append(
                GateItem(
                    name="Độ phủ luồng phiên gần nhất",
                    requirement=">= 90% số nến chốt",
                    measured_value=measured_val_str,
                    status="WARN",
                    note=f"Hơi thấp (< 90%): {stream_coverage_summary}",
                )
            )
        else:
            items.append(
                GateItem(
                    name="Độ phủ luồng phiên gần nhất",
                    requirement=">= 90% số nến chốt",
                    measured_value=measured_val_str,
                    status="FAIL",
                    note=f"Quá thấp (< 50%): {stream_coverage_summary}",
                )
            )
    else:
        items.append(
            GateItem(
                name="Độ phủ luồng phiên gần nhất",
                requirement=">= 90% số nến chốt",
                measured_value="Không có dữ liệu",
                status="WARN",
                note=stream_coverage_summary,
            )
        )

    # 7. Đường cảnh báo Telegram
    if telegram_configured:
        items.append(
            GateItem(
                name="Đường truyền Telegram",
                requirement="Đầy đủ biến BOT_TOKEN và CHAT_ID",
                measured_value="ĐÃ CẤU HÌNH",
                status="PASS",
                note="Không gửi tin kiểm tra, chỉ kiểm cấu hình môi trường",
            )
        )
    else:
        items.append(
            GateItem(
                name="Đường truyền Telegram",
                requirement="Đầy đủ biến BOT_TOKEN và CHAT_ID",
                measured_value="THIẾU BIẾN MÔI TRƯỜNG",
                status="FAIL",
                note="Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID",
            )
        )

    # 8. Lệch triển khai (Deploy drift)
    if deploy_drift_ok:
        items.append(
            GateItem(
                name="Lệch triển khai (Image vs Git)",
                requirement="Image collector/engine >= commit git",
                measured_value="KHỚP",
                status="PASS",
                note=deploy_drift_msg,
            )
        )
    else:
        items.append(
            GateItem(
                name="Lệch triển khai (Image vs Git)",
                requirement="Image collector/engine >= commit git",
                measured_value="LỆCH / LỖI",
                status="FAIL",
                note=deploy_drift_msg,
            )
        )

    # 9. Số lệnh thật đã khớp
    items.append(
        GateItem(
            name="Lịch sử lệnh thật đã khớp",
            requirement="In ra số dòng (không chặn)",
            measured_value=f"{real_fills_count} lệnh",
            status="INFO",
            note="Số lệnh đã ghi nhận trong bảng real_order_fills",
        )
    )

    # Tính toán mã thoát chung
    has_fail = any(it.status == "FAIL" for it in items)
    has_warn = any(it.status == "WARN" for it in items)
    if has_fail:
        exit_code = 2
    elif has_warn:
        exit_code = 1
    else:
        exit_code = 0

    return exit_code, items


def run_gate_check(dsn: str, config_path: str = "config/config.yaml") -> int:
    cfg = read_config_info(config_path)
    if not cfg:
        print(f"LỖI: Không thể đọc cấu hình từ {config_path}")
        return 2

    real_trading_enabled = bool(cfg.get("real_trading_enabled", False))
    real_account = str(cfg.get("real_order_account", "0434221"))
    symbols = list(cfg.get("symbols", []))

    now_vn = datetime.now(TZ)

    # Đọc DB
    nav = None
    nav_age_sec = None
    buying_powers = {}
    bp_age_sec = None
    pos_age_sec = None
    real_fills_count = 0

    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
            # 1. NAV (Brief 79 Task 2: Đọc kèm timestamp để tính tuổi)
            cur.execute(
                "SELECT nav, ts FROM account_nav_snapshot WHERE account_no = %s ORDER BY ts DESC LIMIT 1;",
                (real_account,),
            )
            r_nav = cur.fetchone()
            if r_nav and r_nav[0] is not None:
                nav = float(r_nav[0])
                if r_nav[1]:
                    nav_ts = r_nav[1].astimezone(TZ)
                    nav_age_sec = (now_vn - nav_ts).total_seconds()

            # 2. Sức mua
            for sym in symbols:
                cur.execute(
                    "SELECT max_buy_qty FROM account_buying_power WHERE account_no = %s AND symbol = %s ORDER BY ts DESC LIMIT 1;",
                    (real_account, sym),
                )
                r_bp = cur.fetchone()
                buying_powers[sym] = int(r_bp[0]) if r_bp and r_bp[0] is not None else 0

            cur.execute(
                "SELECT max(ts) FROM account_buying_power WHERE account_no = %s;",
                (real_account,),
            )
            r_bp_ts = cur.fetchone()
            if r_bp_ts and r_bp_ts[0]:
                bp_ts = r_bp_ts[0].astimezone(TZ)
                bp_age_sec = (now_vn - bp_ts).total_seconds()

            # 3. Vị thế sync log
            cur.execute(
                "SELECT ts FROM account_sync_log WHERE account_no = %s;",
                (real_account,),
            )
            r_pos = cur.fetchone()
            if r_pos and r_pos[0]:
                pos_ts = r_pos[0].astimezone(TZ)
                pos_age_sec = (now_vn - pos_ts).total_seconds()

            # 4. Fills
            cur.execute("SELECT count(*) FROM real_order_fills;")
            r_fills = cur.fetchone()
            if r_fills:
                real_fills_count = int(r_fills[0])
    except Exception as e:
        print(f"LỖI KẾT NỐI DATABASE: {e}")
        return 2

    # Đọc stream coverage
    stream_coverage, stream_summary, stream_measured_at = read_latest_stream_coverage()
    stream_age_sec = (now_vn - stream_measured_at).total_seconds() if stream_measured_at else None

    # Đọc telegram config
    telegram_ok = check_telegram_configured()

    # Đọc deploy drift
    drift_ok, drift_msg = check_deploy_drift()

    # Đánh giá
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=real_trading_enabled,
        real_account=real_account,
        nav=nav,
        buying_powers=buying_powers,
        buying_power_age_sec=bp_age_sec,
        position_age_sec=pos_age_sec,
        stream_coverage=stream_coverage,
        stream_coverage_summary=stream_summary,
        telegram_configured=telegram_ok,
        deploy_drift_ok=drift_ok,
        deploy_drift_msg=drift_msg,
        real_fills_count=real_fills_count,
        symbols=symbols,
        stream_measured_at=stream_measured_at,
        stream_age_sec=stream_age_sec,
        nav_age_sec=nav_age_sec,
        now=now_vn,
    )

    # In bảng báo cáo
    print("=" * 105)
    print(f" BẢNG KIỂM ĐỊNH CỔNG GO-LIVE (GOLIVE GATE CHECK) — {now_vn.strftime('%Y-%m-%d %H:%M:%S')} (VN)")
    print(f" Tài khoản: {real_account} | Danh mục: {', '.join(symbols)}")
    print("=" * 105)
    print(f"{'#':<3} | {'Tiêu chí':<32} | {'Trạng thái đo được':<30} | {'Kết luận':<8} | {'Ghi chú':<22}")
    print("-" * 105)

    status_icon = {
        "PASS": "[ĐẠT]",
        "WARN": "[CẢNH BÁO]",
        "FAIL": "[CHẶN]",
        "INFO": "[THÔNG TIN]",
    }

    for idx, it in enumerate(items, 1):
        s_text = status_icon.get(it.status, it.status)
        print(f"{idx:<3} | {it.name:<32} | {it.measured_value:<30} | {s_text:<10} | {it.note}")

    print("=" * 105)
    if exit_code == 0:
        print(">>> KẾT LUẬN: ĐỦ ĐIỀU KIỆN GO-LIVE (EXIT 0) — MỌI LÁ CHẮN AN TOÀN ĐỀU ĐẠT CHUẨN.")
        print("    Chủ dự án có thể bật real_trading_enabled: true trên tài khoản", real_account)
    elif exit_code == 1:
        print(">>> KẾT LUẬN: CÓ CẢNH BÁO (EXIT 1) — CÁC LÁ CHẮN ĐẠT NHƯNG CÓ THÔNG TIN CẦN XÁC NHẬN.")
    else:
        print(">>> KẾT LUẬN: KHÔNG ĐƯỢC BẬT (EXIT 2) — CÁC LÁ CHẮN AN TOÀN ĐANG BỊ TỪ CHỐI HOẶC HỎNG.")
        print("    Nếu phát sinh lệnh thật tại thời điểm này, hệ thống sẽ chặn lệnh để bảo toàn vốn.")
    print("=" * 105)

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiểm tra cổng go-live trước khi bật real_trading_enabled")
    parser.add_argument("--dsn", default=None, help="Postgres DSN override")
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn config.yaml")
    args = parser.parse_args()

    try:
        from _db_common import resolve_dsn
    except ImportError:
        from scripts._db_common import resolve_dsn

    dsn = resolve_dsn(args.dsn)
    sys.exit(run_gate_check(dsn, args.config))


if __name__ == "__main__":
    main()
