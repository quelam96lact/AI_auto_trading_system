from collections.abc import Callable
from datetime import datetime

from trading.alerts import alert
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Crossover, Strategy
from trading.trailing_stop import TrailingStopManager


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: Strategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    marks: dict[str, float],
    day_state: dict,
    on_crossover: Callable[[Crossover, Bar], None] | None = None,
) -> list[Fill]:
    # daily_pnl phai tinh THEO NGAY: snapshot realized dau ngay, reset khi doi
    # ngay. Truoc day dung broker.realized_pnl tich luy tu luc khoi dong — khi
    # lo tich luy vuot max_daily_loss_pct thi RiskManager halt VINH VIEN, vi
    # realized tich luy khong bao gio hoi. Cung loai bug da sua cho backtest o
    # commit 351e6e1 (derivative_backtest.py); luong live khi do chua sua.
    # Snapshot TRUOC broker.on_bar() de fill cua chinh bar nay tinh vao ngay moi.
    today = bar.ts.date()
    if day_state.get("day") != today:
        day_state["day"] = today
        day_state["start_realized"] = broker.realized_pnl

    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close
    for f in fills:
        if f.side == "BUY":
            trailing_stop.on_position_opened(f.symbol, f.price)
        else:
            trailing_stop.on_position_closed(f.symbol)

    signal = strategy.on_bar(bar, broker)
    crossover = strategy.last_crossover(bar.symbol)
    if on_crossover is not None and crossover is not None:
        on_crossover(crossover, bar)

    stop_price = None
    if broker.position_qty(bar.symbol) > 0:
        stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

    if stop_price is not None:
        forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
        if forced.qty > 0:
            # SPEC1-FIX Lỗi 1: chi dong vi the khi thuc su ban duoc (da settle
            # T+2,5). Neu qty=0 (chua settle): vi the GIU NGUYEN, trailing stop
            # TIEP TUC theo doi (khong on_position_closed), khong ghi order rac
            # (persist_fills ghi moi fill khong loc).
            trailing_stop.on_position_closed(bar.symbol)
            fills.append(forced)
        # qty=0: stop da cham nhung luat khong cho ban — khong alert de tranh
        # nhiem (moi bar cham = 1 canh bao); stop se thu lai o bar ke tiep.
    elif signal is not None:
        daily_pnl = (
            broker.realized_pnl
            - day_state["start_realized"]
            + broker.unrealized_pnl(marks)
        )
        sized = risk.approve_sized(
            signal,
            bar.close,
            strategy.last_atr(bar.symbol),
            broker.positions,
            daily_pnl,
            today,
        )
        if sized is not None:
            broker.submit(sized)
        else:
            # SIZE-1 Viec 2: moi lan tu choi phai noi duoc ly do — caller ghi
            # log (risk.py giu thuan logic, khong import alert). Muc INFO chu
            # khong WARN: tu choi la chuyen binh thuong, WARN tao moi canh bao
            # (bay NOISE-1 da sua o 1e801ec).
            alert(
                "INFO",
                "signal bi tu choi",
                symbol=signal.symbol,
                side=signal.side,
                reason=risk.last_reject_reason,
            )

    return fills


def bar_from_payload(data: dict) -> Bar:
    return Bar(
        symbol=data["symbol"],
        ts=datetime.fromisoformat(data["ts"]).astimezone(TZ),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data["volume"],
        source=data.get("source", "ssi"),
    )
