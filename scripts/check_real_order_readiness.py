"""Báo cáo mức độ sẵn sàng của đường lệnh thật (Brief 48 Task 2).

Chạy: uv run python scripts/check_real_order_readiness.py

Mục tiêu:
Kiểm tra toàn diện trạng thái đường lệnh thật trước khi go-live:
(a) Trạng thái đường lệnh thật (pending_real_orders, real_order_fills).
(b) Sức mua so với nhu cầu trên tài khoản cấu hình (real_order_account).
(c) So sánh NAV và sức mua giữa hai tài khoản (0434221 vs 0434226) - phục vụ Q-2.
(d) Đánh giá tuổi dữ liệu của mọi lá chắn (vị thế, sức mua) - kiểm tra xem lệnh có bị từ chối không.

Ràng buộc:
- CHỈ ĐỌC (SELECT thuần tuý), KHÔNG ghi DB.
- KHÔNG gọi mạng / API SSI.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.config import load_config
from trading.real_orders import (
    BUYING_POWER_MAX_AGE_MINUTES,
    POSITION_MAX_AGE_MINUTES,
)

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def format_currency(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.0f}"


def format_age(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def run_readiness_check(dsn: str, config_path: str = "config/config.yaml") -> None:
    now_vn = datetime.now(TZ_VN)
    cfg = load_config(config_path)
    real_account = cfg.real_order_account

    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("SET TimeZone='Asia/Ho_Chi_Minh';")

        print("=" * 80)
        print(f"BÁO CÁO MỨC ĐỘ SẴN SÀNG CỦA ĐƯỜNG LỆNH THẬT — {now_vn.strftime('%Y-%m-%d %H:%M:%S')} (GIỜ VN)")
        print(f"Tài khoản đang cấu hình (real_order_account): {real_account}")
        print(f"Danh mục theo dõi: {', '.join(cfg.symbols)}")
        print("=" * 80)

        # =========================================================================
        # (a) Trạng thái đường lệnh thật
        # =========================================================================
        print("\n(a) TRẠNG THÁI ĐƯỜNG LỆNH THẬT")
        print("-" * 40)
        cur.execute("""
            SELECT status, count(*)
            FROM pending_real_orders
            GROUP BY status
            ORDER BY status;
        """)
        status_rows = cur.fetchall()
        total_pending = sum(r[1] for r in status_rows)
        status_str = ", ".join(f"{r[0]}: {r[1]}" for r in status_rows) if status_rows else "0 lệnh"

        cur.execute("""
            SELECT count(*)
            FROM pending_real_orders
            WHERE ssi_order_id IS NOT NULL AND ssi_order_id != '';
        """)
        orders_with_ssi_id = cur.fetchone()[0]

        cur.execute("""
            SELECT status, count(*)
            FROM real_order_fills
            GROUP BY status
            ORDER BY status;
        """)
        fill_status_rows = cur.fetchall()
        total_fills = sum(r[1] for r in fill_status_rows)
        fill_status_str = ", ".join(f"{r[0]}: {r[1]}" for r in fill_status_rows) if fill_status_rows else "0 lệnh"

        cur.execute("SELECT max(created_at) FROM pending_real_orders;")
        latest_order_time = cur.fetchone()[0]
        latest_order_str = (
            latest_order_time.astimezone(TZ_VN).strftime("%Y-%m-%d %H:%M:%S")
            if latest_order_time
            else "Chưa từng có"
        )

        print(f"  • Tổng số pending_real_orders : {total_pending} ({status_str})")
        print(f"  • Số lệnh có ssi_order_id     : {orders_with_ssi_id} (chưa từng đặt thành công lên sàn)")
        print(f"  • Số dòng real_order_fills    : {total_fills} ({fill_status_str})")
        print(f"  • Thời điểm lệnh gần nhất     : {latest_order_str}")

        # =========================================================================
        # (b) Sức mua so với nhu cầu trên tài khoản cấu hình
        # =========================================================================
        print(f"\n(b) SỨC MUA SO VỚI NHU CẦU (Tài khoản cấu hình: {real_account})")
        print("-" * 80)
        print(
            f"{'Mã':<6} | {'Max Buy Qty':<12} | {'Giá gần nhất':<15} | {'Giá trị mua tối đa':<20} | {'Đủ 1 lô (100cp)?':<18}"
        )
        print("-" * 80)

        buying_power_ages = {}
        for sym in cfg.symbols:
            cur.execute("""
                SELECT max_buy_qty, max_sell_qty, margin_ratio_pct, ts
                FROM account_buying_power
                WHERE account_no = %s AND symbol = %s
                ORDER BY ts DESC LIMIT 1;
            """, (real_account, sym))
            bp_row = cur.fetchone()

            cur.execute("""
                SELECT close, ts
                FROM bars
                WHERE symbol = %s
                ORDER BY ts DESC LIMIT 1;
            """, (sym,))
            bar_row = cur.fetchone()

            max_buy_qty = bp_row[0] if bp_row else 0
            bp_ts = bp_row[3].astimezone(TZ_VN) if bp_row else None
            if bp_ts:
                age_sec = (now_vn - bp_ts).total_seconds()
                buying_power_ages[sym] = (age_sec, bp_ts)

            close_price = bar_row[0] if bar_row else 0.0
            max_buy_val = max_buy_qty * close_price
            enough_lot = "ĐỦ (>= 100)" if max_buy_qty >= 100 else "KHÔNG ĐỦ (< 100)"

            print(
                f"{sym:<6} | {max_buy_qty:<12,d} | {format_currency(close_price) + ' VND':<15} | "
                f"{format_currency(max_buy_val) + ' VND':<20} | {enough_lot:<18}"
            )

        print("-" * 80)
        for sym, (age_sec, bp_ts) in buying_power_ages.items():
            print(f"  • Tuổi bản ghi sức mua {sym}: {format_age(age_sec)} (lúc {bp_ts.strftime('%H:%M:%S')})")

        # =========================================================================
        # (c) So sánh hai tài khoản (0434221 vs 0434226)
        # =========================================================================
        print("\n(c) SO SÁNH HAI TÀI KHOẢN (0434221 vs 0434226 - Dữ liệu cho Q-2)")
        print("-" * 80)
        cur.execute("""
            SELECT DISTINCT ON (account_no) account_no, nav, ts, unpriced_symbols
            FROM account_nav_snapshot
            WHERE account_no IN ('0434221', '0434226')
            ORDER BY account_no, ts DESC;
        """)
        nav_rows = cur.fetchall()
        nav_dict = {r[0]: (r[1], r[2].astimezone(TZ_VN), r[3]) for r in nav_rows}

        for acc in ["0434221", "0434226"]:
            if acc in nav_dict:
                nav_val, nav_ts, unpriced = nav_dict[acc]
                print(f"  Tài khoản {acc}:")
                print(f"    - NAV mới nhất        : {format_currency(nav_val)} VND (lúc {nav_ts.strftime('%Y-%m-%d %H:%M:%S')})")
                print(f"    - Mã chưa định giá    : {unpriced if unpriced else 'Không có'}")
            else:
                print(f"  Tài khoản {acc}: Không có dữ liệu NAV snapshot")

        print("\n  So sánh sức mua (max_buy_qty) giữa hai tài khoản:")
        label_221 = "0434221 (Đang cấu hình)" if real_account == "0434221" else "0434221"
        label_226 = "0434226 (Đang cấu hình)" if real_account == "0434226" else "0434226"
        print(f"  {'Mã':<6} | {label_221:<25} | {label_226:<25} | {'Tỷ lệ chênh lệch':<18}")
        print("  " + "-" * 76)
        for sym in cfg.symbols:
            cur.execute("""
                SELECT max_buy_qty FROM account_buying_power
                WHERE account_no = '0434221' AND symbol = %s
                ORDER BY ts DESC LIMIT 1;
            """, (sym,))
            r221 = cur.fetchone()
            q221 = r221[0] if r221 else 0

            cur.execute("""
                SELECT max_buy_qty FROM account_buying_power
                WHERE account_no = '0434226' AND symbol = %s
                ORDER BY ts DESC LIMIT 1;
            """, (sym,))
            r226 = cur.fetchone()
            q226 = r226[0] if r226 else 0

            ratio_str = f"{q226 / q221:.1f}x" if q221 > 0 else "N/A"
            print(f"  {sym:<6} | {q221:<25,d} | {q226:<25,d} | {ratio_str:<18}")

        # =========================================================================
        # (d) Tuổi dữ liệu của mọi lá chắn
        # =========================================================================
        print("\n(d) TUỔI DỮ LIỆU CỦA MỌI LÁ CHẮN (Fail-safes)")
        print("-" * 80)
        # 1. Lá chắn vị thế
        cur.execute("SELECT ts FROM account_sync_log WHERE account_no = %s;", (real_account,))
        pos_sync_row = cur.fetchone()
        pos_sync_ts = pos_sync_row[0].astimezone(TZ_VN) if pos_sync_row and pos_sync_row[0] else None

        pos_shield_pass = False
        if pos_sync_ts:
            pos_age_sec = (now_vn - pos_sync_ts).total_seconds()
            pos_age_min = pos_age_sec / 60.0
            pos_shield_pass = pos_age_min <= POSITION_MAX_AGE_MINUTES
            pos_status_str = "ĐẠT" if pos_shield_pass else "SẼ TỪ CHỐI LỆNH"
            pos_detail = f"Tuổi: {format_age(pos_age_sec)} (ngưỡng <= {POSITION_MAX_AGE_MINUTES}m) -> {pos_status_str}"
        else:
            pos_status_str = "SẼ TỪ CHỐI LỆNH"
            pos_detail = "Chưa từng có bản ghi đồng bộ vị thế -> SẼ TỪ CHỐI LỆNH"

        print("  1. Lá chắn độ tươi vị thế (account_sync_log):")
        print(f"     Mốc sync gần nhất: {pos_sync_ts.strftime('%Y-%m-%d %H:%M:%S') if pos_sync_ts else 'None'}")
        print(f"     Trạng thái: {pos_detail}")

        # 2. Lá chắn sức mua
        cur.execute("""
            SELECT max(ts) FROM account_buying_power WHERE account_no = %s;
        """, (real_account,))
        latest_bp_ts_row = cur.fetchone()
        latest_bp_ts = (
            latest_bp_ts_row[0].astimezone(TZ_VN)
            if latest_bp_ts_row and latest_bp_ts_row[0]
            else None
        )

        bp_shield_pass = False
        if latest_bp_ts:
            bp_age_sec = (now_vn - latest_bp_ts).total_seconds()
            bp_age_min = bp_age_sec / 60.0
            bp_shield_pass = bp_age_min <= BUYING_POWER_MAX_AGE_MINUTES
            bp_status_str = "ĐẠT" if bp_shield_pass else "SẼ TỪ CHỐI LỆNH"
            bp_detail = f"Tuổi: {format_age(bp_age_sec)} (ngưỡng <= {BUYING_POWER_MAX_AGE_MINUTES}m) -> {bp_status_str}"
        else:
            bp_status_str = "SẼ TỪ CHỐI LỆNH"
            bp_detail = "Chưa từng có bản ghi sức mua -> SẼ TỪ CHỐI LỆNH"

        print("  2. Lá chắn độ tươi sức mua (account_buying_power):")
        print(f"     Mốc sync gần nhất: {latest_bp_ts.strftime('%Y-%m-%d %H:%M:%S') if latest_bp_ts else 'None'}")
        print(f"     Trạng thái: {bp_detail}")

        print("\n  => KẾT LUẬN CỦA BỘ LÁ CHẮN TẠI THỜI ĐIỂM HIỆN TẠI:")
        if pos_shield_pass and bp_shield_pass:
            print("     [SẴN SÀNG] Nếu phát sinh tín hiệu lúc này, lệnh SẼ ĐƯỢC CHẤP THUẬN qua các lá chắn bảo vệ.")
        else:
            reasons = []
            if not pos_shield_pass:
                reasons.append("Vị thế quá hạn (stale position)")
            if not bp_shield_pass:
                reasons.append("Sức mua quá hạn (stale buying power)")
            print(f"     [TỪ CHỐI] Nếu phát sinh tín hiệu lúc này, lệnh SẼ BỊ CHẶN do: {', '.join(reasons)}.")
        print("=" * 80)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra mức độ sẵn sàng của đường lệnh thật (Brief 48 Task 2).")
    parser.add_argument("--dsn", default=None, help="Database DSN override")
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn file config")
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    run_readiness_check(dsn, args.config)


if __name__ == "__main__":
    main()
