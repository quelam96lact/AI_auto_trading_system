from datetime import datetime, timedelta

from trading.alerts import alert
from trading.config import Config
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategy import Signal

PENDING_ORDER_TTL_MINUTES = 15


def handle_signal(
    cfg: Config,
    storage: Storage,
    risk: RiskManager,
    signal: Signal,
    bar: Bar,
) -> None:
    """Gate 1 Signal qua RiskManager RIÊNG cho lệnh thật; nếu duyệt, ghi pending_real_orders + Telegram.

    KHÔNG gọi bất kỳ API đặt lệnh nào — chỉ ghi DB + cảnh báo. Việc đặt lệnh thật
    là scripts/confirm_real_order.py (Phase 3), chạy thủ công bởi ngườ dùng.
    """
    positions = storage.read_real_positions(cfg.real_order_account)
    today = bar.ts.date()
    daily_pnl = storage.read_real_daily_pnl(cfg.real_order_account, today)

    if signal.side == "SELL":
        pos = positions.get(signal.symbol)
        sellable = pos.sellable_qty if pos is not None else 0
        if sellable <= 0:
            # Không có gì khả dụng để bán (chưa nắm giữ, hoặc cổ phiếu chưa settle T+2,5) —
            # không tạo pending order, không cố gửi lệnh biết trước sẽ sai/bị SSI từ chối.
            return
        if signal.qty > sellable:
            signal = Signal(symbol=signal.symbol, side=signal.side, qty=sellable)

    if not risk.approve(signal, bar.close, positions, daily_pnl, today):
        return

    expires_at = datetime.now(bar.ts.tzinfo) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)
    order_id = storage.create_pending_order(
        account_no=cfg.real_order_account,
        symbol=signal.symbol,
        side=signal.side,
        quantity=signal.qty,
        price=bar.close,
        expires_at=expires_at,
    )
    alert(
        "WARN",
        "real order pending confirmation",
        id=order_id,
        symbol=signal.symbol,
        side=signal.side,
        qty=signal.qty,
        price=bar.close,
        expires_in_minutes=PENDING_ORDER_TTL_MINUTES,
        confirm_cmd=f"uv run python scripts/confirm_real_order.py {order_id}",
    )
