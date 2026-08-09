from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.engine.logic import bar_from_payload, process_bar
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import Crossover, SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager


def bar_at(i, close, sym="VCB"):
    return Bar(
        sym,
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
        close,
        close,
        close,
        close,
        100,
    )


def test_process_bar_submits_and_next_bar_fills():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(
        fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0
    )
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager()
    marks: dict[str, float] = {}
    day_state: dict = {}

    prices = [10, 10, 10, 10, 20, 20]
    all_fills = []
    for i, p in enumerate(prices):
        all_fills.extend(
            process_bar(
            bar_at(i, p), broker, strategy, risk, trailing_stop, marks, day_state
        )
        )

    assert any(f.side == "BUY" for f in all_fills)


def test_bar_from_payload_roundtrip():
    payload = {
        "symbol": "VCB",
        "ts": "2026-07-15T09:00:00+07:00",
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1000,
        "source": "ssi",
    }
    bar = bar_from_payload(payload)
    assert bar.symbol == "VCB" and bar.close == 10.5 and bar.ts.tzinfo is not None


def test_process_bar_calls_on_crossover_when_crossover_fires():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(
        fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0
    )
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager()
    marks: dict[str, float] = {}
    day_state: dict = {}
    calls = []

    def on_crossover(crossover: Crossover, bar: Bar) -> None:
        calls.append((crossover, bar))

    prices = [10, 10, 10, 10, 20, 20]
    bars = [bar_at(i, p) for i, p in enumerate(prices)]
    for b in bars:
        process_bar(
            b,
            broker,
            strategy,
            risk,
            trailing_stop,
            marks,
            day_state,
            on_crossover=on_crossover,
        )

    assert len(calls) == 1
    assert calls[0][0] == "bull"
    assert calls[0][1].close == 20


def test_process_bar_does_not_call_on_crossover_when_no_crossover():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(
        fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0
    )
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager()
    marks: dict[str, float] = {}
    day_state: dict = {}
    calls = []

    def on_crossover(crossover: Crossover, bar: Bar) -> None:
        calls.append((crossover, bar))

    prices = [10, 10, 10]
    bars = [bar_at(i, p) for i, p in enumerate(prices)]
    for b in bars:
        process_bar(
            b,
            broker,
            strategy,
            risk,
            trailing_stop,
            marks,
            day_state,
            on_crossover=on_crossover,
        )

    assert len(calls) == 0


def test_process_bar_calls_on_crossover_even_when_paper_signal_suppressed():
    """Đây là bằng chứng trực tiếp lỗ hổng cũ đã được giải quyết: bearish crossover
    xảy ra ngay lần đầu (PaperBroker chưa từng mua, held=0) nên on_bar() trả None,
    nhưng on_crossover VẪN phải được gọi để real_orders có thể bán vị thế thật.
    """
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(
        fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0
    )
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager()
    marks: dict[str, float] = {}
    day_state: dict = {}
    calls = []

    def on_crossover(crossover: Crossover, bar: Bar) -> None:
        calls.append((crossover, bar))

    # Prices rise just enough that by the time history fills (bar #3, the
    # first-ever crossover computation) cur_above is already True — this is
    # recorded as None (no prior prev_above to compare against), NOT "bull",
    # so PaperBroker never buys. The drop on bar #4 then produces the first
    # real crossover ever detected, and it's bearish, with held still 0.
    prices = [10, 10, 20, 20, 5]
    bars = [bar_at(i, p) for i, p in enumerate(prices)]
    for b in bars:
        process_bar(
            b,
            broker,
            strategy,
            risk,
            trailing_stop,
            marks,
            day_state,
            on_crossover=on_crossover,
        )

    assert any(c[0] == "bear" for c in calls), f"expected bear crossover, got {calls}"
    assert broker.positions.get("VCB") is None, "PaperBroker must never have bought"


def test_trailing_stop_exits_before_bear_crossover_would_fire():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.0)
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager(sl_multiplier=1.0)
    marks: dict[str, float] = {}
    day_state: dict = {}

    # Tang manh 10->23 (bull crossover + vi the mo), roi giat lui vua phai
    # xuong 21 - du de cham trailing stop (theo ATR%1.0) nhung KHONG du de
    # lam MA (fast=2,slow=4) dao chieu thanh bear crossover trong chuoi nay.
    prices = [10, 10, 10, 10, 20, 21, 22, 23, 21]
    all_fills = []
    crossovers = []
    for i, p in enumerate(prices):
        fills = process_bar(
            bar_at(i, p), broker, strategy, risk, trailing_stop, marks, day_state
        )
        all_fills.extend(fills)
        crossovers.append(strategy.last_crossover("VCB"))

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    assert len(sell_fills) == 1
    assert sell_fills[0].price == 21.0
    assert broker.position_qty("VCB") == 0
    # Crossover KHONG BAO GIO thanh "bear" trong ca chuoi nay - chung minh
    # lenh thoat den tu trailing stop, khong phai tu crossover.
    assert "bear" not in crossovers


def bar_on(day, i, close, sym="VCB"):
    return Bar(
        sym,
        datetime(2026, 7, day, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
        close,
        close,
        close,
        close,
        100,
    )


class RecordingRisk(RiskManager):
    """Ghi lai daily_pnl ma process_bar truyen vao, van giu nguyen hanh vi that."""

    def __init__(self, capital):
        super().__init__(capital=capital)
        self.seen = []

    def approve_sized(self, signal, ref_price, atr, positions, daily_pnl, today):
        self.seen.append((today, daily_pnl))
        return super().approve_sized(
            signal, ref_price, atr, positions, daily_pnl, today
        )


def test_daily_pnl_resets_next_day_and_does_not_halt_forever():
    """Lo cua NGAY HOM TRUOC khong duoc tinh vao daily_pnl hom nay.

    Bug goc: daily_pnl = broker.realized_pnl (tich luy tu luc khoi dong) +
    unrealized. Khi lo tich luy vuot 3% von, RiskManager halt va KHONG BAO GIO
    mo lai vi realized_pnl tich luy khong hoi -> engine im lang ngung vao lenh
    vinh vien. Cung loai bug da sua cho backtest o commit 351e6e1.
    """
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(
        fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0
    )
    risk = RecordingRisk(100_000_000)
    trailing_stop = TrailingStopManager()
    marks: dict[str, float] = {}
    day_state: dict = {}

    # Ngay 15: 20 bar gia phang, chua co crossover.
    for i in range(20):
        process_bar(
            bar_on(15, i, 10), broker, strategy, risk, trailing_stop, marks, day_state
        )

    # Gia lap: ket ngay 15 lo 5 trieu (vuot nguong 3% cua 100tr = 3 trieu).
    broker.realized_pnl = -5_000_000.0

    # Ngay 16: gia nhay len 20 -> bull crossover -> co signal -> risk duoc hoi.
    for i in range(5):
        process_bar(
            bar_on(16, i, 20), broker, strategy, risk, trailing_stop, marks, day_state
        )

    day16 = [(d, pnl) for d, pnl in risk.seen if d == date(2026, 7, 16)]
    assert day16, "phai co it nhat 1 lan risk duoc hoi trong ngay 16"
    for _, pnl in day16:
        assert pnl > -3_000_000, (
            f"daily_pnl ngay 16 = {pnl} van mang lo tich luy cua ngay 15"
        )
    assert risk.halted_date is None, "khong duoc halt: ngay 16 chua lo gi"
