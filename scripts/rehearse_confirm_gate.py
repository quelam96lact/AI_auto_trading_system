"""Diễn tập quy trình mở cửa xác nhận lệnh thật (Brief đợt 52 Task 2).

Mục tiêu:
Cho phép chủ dự án diễn tập toàn bộ quy trình xác nhận lệnh thật qua confirm_real_order.py
mà TUYỆT ĐỐI không chạm DB thật, không chạm SSI, không bật cờ real_trading_enabled.

Hàng rào an toàn cứng (bắt buộc):
1. DB DSN PHẢI trỏ tới cơ sở dữ liệu kết thúc bằng '_test' (mặc định trading_test).
2. real_trading_enabled PHẢI là False.
Nếu vi phạm bất kỳ điều kiện nào -> từ chối chạy và raise ValueError / exit 1 ngay lập tức.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from scripts.confirm_real_order import confirm
except ImportError:
    from confirm_real_order import confirm
from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.storage.db import Storage


def verify_safety_barriers(cfg: Config) -> None:
    """Kiểm tra hàng rào an toàn trước khi diễn tập."""
    # 1. Hàng rào DSN
    dsn = cfg.db_dsn or ""
    parsed = urlparse(dsn)
    db_name = parsed.path.lstrip("/")
    if not db_name.endswith("_test"):
        raise ValueError(
            f"HÀNG RÀO AN TOÀN CHẶN: DSN database {db_name!r} không kết thúc bằng '_test' "
            f"(DSN={dsn}). Từ chối diễn tập để bảo vệ DB sản xuất."
        )

    # 2. Hàng rào real_trading_enabled
    if cfg.real_trading_enabled:
        raise ValueError(
            "HÀNG RÀO AN TOÀN CHẶN: real_trading_enabled đang là True. "
            "Kịch bản diễn tập TUYỆT ĐỐI chỉ chạy khi real_trading_enabled=False."
        )


async def rehearse(cfg: Config, storage: Storage) -> int:
    """Thực hiện một lượt diễn tập hoàn chỉnh trên trading_test.

    Trả về order_id vừa diễn tập.
    """
    verify_safety_barriers(cfg)

    # Đảm bảo schema trong DB test đã sẵn sàng
    storage.init_schema()

    # Bước 1: Tạo một dòng pending_real_orders qua Storage.create_pending_order
    # Mẫu theo dòng thật id=1226: account_no="0434221", symbol="IJC", side="BUY", qty=100, price=7330.0
    now = datetime.now(TZ)
    ttl_minutes = 15
    expires_at = now + timedelta(minutes=ttl_minutes)
    account_no = cfg.real_order_account if cfg.real_order_account else "0434221"

    order_id = storage.create_pending_order(
        account_no=account_no,
        symbol="IJC",
        side="BUY",
        quantity=100,
        price=7330.0,
        expires_at=expires_at,
    )
    print("=== BƯỚC 1: ĐÃ TẠO ĐƠN CHỜ DIỄN TẬP ===")
    print(f"Order ID: {order_id}")
    print(
        f"Chi tiết: {account_no} | IJC | BUY 100 @ 7330.0 | "
        f"TTL {ttl_minutes}m (hết hạn lúc {expires_at.strftime('%H:%M:%S')})"
    )

    # Bước 2: In đúng câu lệnh mà người dùng sẽ phải gõ
    confirm_cmd = f"uv run --with ssi-sdk python scripts/confirm_real_order.py {order_id}"
    print("\n=== BƯỚC 2: CÂU LỆNH XÁC NHẬN CẦN GÕ ===")
    print(f"Lệnh: {confirm_cmd}")
    print("Hành động: Nhập lệnh trên vào terminal và gõ 'YES'")

    # Bước 3: Chạy confirm() với confirm_input="YES" và real_trading_enabled=False
    print("\n=== BƯỚC 3: TIẾN HÀNH XÁC NHẬN (CONFIRM YES / DRY-RUN) ===")
    try:
        await confirm(cfg, storage, order_id, confirm_input="YES")
    except SystemExit:
        # confirm() kết thúc bằng sys.exit(0), bắt lại để in tiếp bước 4
        pass

    # Bước 4: In trạng thái dòng đó sau khi chạy
    updated_order = storage.get_pending_order(order_id)
    status_after = updated_order["status"] if updated_order else "NOT_FOUND"
    print("\n=== BƯỚC 4: TRẠNG THÁI ĐƠN SAU KHI XÁC NHẬN ===")
    print(f"Order ID: {order_id} | Status: {status_after}")
    return order_id


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Diễn tập cửa xác nhận lệnh thật trên trading_test")
    parser.add_argument("--config", default="config/config.yaml", help="Path tới file config")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("TEST_DB_DSN", "postgresql://trading:trading@127.0.0.1:5432/trading_test"),
        help="DSN database test (phải là *_test)",
    )
    args = parser.parse_args()

    # Thiết lập biến môi trường an toàn trước khi load_config (không mở / không cần .env)
    os.environ["DB_DSN"] = args.dsn
    os.environ.setdefault("SSI_CONSUMER_ID", "rehearse_mock")
    os.environ.setdefault("SSI_CONSUMER_SECRET", "rehearse_mock")
    os.environ.setdefault("SSI_API_KEY", "rehearse_mock")
    os.environ.setdefault("SSI_API_SECRET", "rehearse_mock")
    os.environ.setdefault("SSI_PRIVATE_KEY", "rehearse_mock")

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    asyncio.run(rehearse(cfg, storage))


if __name__ == "__main__":
    main()
