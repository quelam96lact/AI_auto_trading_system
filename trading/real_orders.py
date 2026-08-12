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


def handle_stop_touch(
    cfg: Config,
    storage: Storage,
    bar: Bar,
    atr: float | None,
    real_trailing_stop,
) -> None:
    """Canh bao CHAM STOP cho vi the that — KHONG phai stop-loss tu dong.

    Kien truc la nguoi bam nut: ham nay CHI ghi mot lenh SELL cho xac nhan
    vao pending_real_orders + alert; viec dat lenh that la
    scripts/confirm_real_order.py chay tay, phai go YES trong 15 phut. Khong
    co gi tu dong cat lo o day.

    Bo qua halt lo ngay: RiskManager.approve() chan ca SELL khi halted_date ==
    today (risk.py:37-38 -> _halt_check). Voi lenh cat lo thi dieu do nguy
    hiem — halt xay ra vi dang lo, roi chinh no khoa luon duong thoat. Tien
    le trong repo: luong paper da bo qua risk cho stop-loss — logic.py:51-54,
    nhanh force_exit chay TRUOC va doc lap voi risk.approve_sized() o nhanh
    elif. => Lenh SELL do cham stop KHONG di qua risk.approve().

    So luong ban dung RealPosition.sellable_qty (T+2.5), khong dung qty; neu
    sellable_qty <= 0 (chua settle) thi khong sinh lenh duoc -> alert WARN.

    Khong sinh lenh trung: neu da co pending SELL con hieu luc cho cung
    account_no + symbol thi bo qua (moi bar cham stop se de ra mot lenh cho
    moi neu khong chan).
    """
    positions = storage.read_real_positions(cfg.real_order_account)
    real_pos = positions.get(bar.symbol)
    if real_pos is None or real_pos.qty <= 0:
        return  # tai khoan that khong nam giu ma nay

    if not real_trailing_stop.is_tracking(bar.symbol):
        # RTS-2: vi the that co the mo GIUA PHIEN (xac nhan BUY that -> SSI
        # khop -> account_sync cap nhat snapshot), khong phai luc khoi dong —
        # on_position_opened chi duoc goi o vong lap khoi dong, nen phai khoi
        # tao o day truoc khi check; khong khoi tao thi check() tra None mai
        # mai (trailing_stop.py:26-28) = vi the khong bao gio cham stop.
        highest = storage.read_real_highest_since_buy(cfg.real_order_account, bar.symbol)
        if highest is not None:
            real_trailing_stop.on_position_opened(bar.symbol, highest)
        else:
            # Mua ngoai he thong / khong co fill: dung gia von thay cho dinh
            # that (under-protect nhuong buoc cho tinh huong khong co du lieu)
            # + alert WARN 1 lan noi ro (lan sau da tracking nen khong lap lai).
            real_trailing_stop.on_position_opened(bar.symbol, real_pos.avg_price)
            alert(
                "WARN",
                f"vi the that {bar.symbol} moi xuat hien va khong co BUY fill "
                f"trong real_order_fills — trailing stop khoi tao bang GIA VON "
                f"{real_pos.avg_price:,.0f} thay cho dinh that (mua ngoai he "
                f"thong?)",
                symbol=bar.symbol,
            )

    stop_price = real_trailing_stop.check(bar, atr)
    if stop_price is None:
        return  # chua cham stop (hoac atr None — khong tinh duoc stop)

    sellable = real_pos.sellable_qty
    if sellable <= 0:
        alert(
            "WARN",
            f"vi the that {bar.symbol} da cham stop {stop_price:.0f} nhung "
            f"chua ban duoc (chua settle T+2.5, sellable_qty=0)",
            symbol=bar.symbol,
        )
        return

    if storage.has_active_pending_sell(cfg.real_order_account, bar.symbol):
        return  # da co lenh SELL cho hieu luc — khong sinh trung

    expires_at = datetime.now(bar.ts.tzinfo) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)
    order_id = storage.create_pending_order(
        account_no=cfg.real_order_account,
        symbol=bar.symbol,
        side="SELL",
        quantity=sellable,
        price=stop_price,
        expires_at=expires_at,
    )
    alert(
        "WARN",
        "REAL STOP TOUCH: pending SELL cho xac nhan (KHONG tu dong cat lo — "
        "nguoi van hanh bam nut)",
        id=order_id,
        symbol=bar.symbol,
        side="SELL",
        qty=sellable,
        price=stop_price,
        expires_in_minutes=PENDING_ORDER_TTL_MINUTES,
        confirm_cmd=f"uv run python scripts/confirm_real_order.py {order_id}",
    )
