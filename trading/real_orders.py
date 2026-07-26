from datetime import datetime, timedelta

from trading.alerts import alert
from trading.config import Config
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import Crossover
from trading.strategy import Signal

PENDING_ORDER_TTL_MINUTES = 15
BUY_QTY = 100  # lô tối thiểu HOSE/HNX — KHÔNG lấy theo SmaCrossStrategy.qty (đó là
               # tham số mô phỏng cho paper trading, không nên quyết định khối lượng
               # lệnh thật; xem PLAN_REAL_ORDER_PLACEMENT.md).


def handle_crossover(
    cfg: Config, storage: Storage, risk: RiskManager, crossover: Crossover, bar: Bar
) -> None:
    """Gate 1 sự kiện crossover (từ SmaCrossStrategy.last_crossover() — thuần kỹ
    thuật, KHÔNG liên quan PaperBroker) qua RiskManager riêng cho lệnh thật, dựa
    HOÀN TOÀN trên vị thế THẬT của tài khoản Cash.

    KHÔNG gọi bất kỳ API đặt lệnh nào — chỉ ghi DB + cảnh báo. Việc đặt lệnh thật
    là scripts/confirm_real_order.py, chạy thủ công bởi ngườ dùng.
    """
    positions = storage.read_real_positions(cfg.real_order_account)
    real_pos = positions.get(bar.symbol)

    if crossover == "bull":
        if real_pos is not None and real_pos.qty > 0:
            return  # tài khoản thật đã nắm giữ mã này rồi, không mua thêm
        signal = Signal(symbol=bar.symbol, side="BUY", qty=BUY_QTY)
    elif crossover == "bear":
        sellable = real_pos.sellable_qty if real_pos is not None else 0
        if sellable <= 0:
            return  # không nắm giữ, hoặc chưa settle T+2.5 — không có gì để bán
        signal = Signal(symbol=bar.symbol, side="SELL", qty=sellable)
    else:
        return

    today = bar.ts.date()
    daily_pnl = storage.read_real_daily_pnl(cfg.real_order_account, today)

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
