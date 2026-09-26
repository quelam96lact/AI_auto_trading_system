from datetime import date, datetime, timedelta

from trading.broker import Fill
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

    # Tang manh 10->23 (bull crossover + vi the mo), roi giat lui vua phai —
    # du de cham trailing stop (theo ATR) nhung KHONG du de lam MA (fast=2,
    # slow=4) dao chieu thanh bear crossover trong chuoi nay.
    # SPEC-1a: trailing stop cung phai ton trong T+2,5 — mua ngay 16/07, cham
    # stop ngay 17-18/07 bi TU CHOI (chua settle), ngay 19/07 (D+3) moi thoat.
    # Gia ngay 18-19 chi giam nhe (23.5 -> 23.4) de fast > slow, khong tao bear.
    bars = [
        bar_on(15, 0, 10.0), bar_on(15, 1, 10.0),
        bar_on(15, 2, 10.0), bar_on(15, 3, 10.0),
        bar_on(16, 0, 20.0), bar_on(16, 1, 20.5),
        bar_on(17, 0, 22.0), bar_on(17, 1, 23.0),
        bar_on(18, 0, 23.5),
        bar_on(19, 0, 23.4),
    ]
    all_fills = []
    crossovers = []
    for b in bars:
        fills = process_bar(
            b, broker, strategy, risk, trailing_stop, marks, day_state
        )
        all_fills.extend(fills)
        crossovers.append(strategy.last_crossover("VCB"))

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    assert len(sell_fills) == 1
    assert sell_fills[0].price == 23.4
    assert broker.position_qty("VCB") == 0
    # Crossover KHONG BAO GIO thanh "bear" trong ca chuoi nay - chung minh
    # lenh thoat den tu trailing stop, khong phai tu crossover.
    assert "bear" not in crossovers


# ============ SPEC1-FIX: stop chạm khi CHƯA settle (T+2,5) ============


def _run_stop_sequence(prices_by_day) -> tuple[list[Fill], PaperBroker, TrailingStopManager]:
    """Chay process_bar tren chuoi gia theo ngay, tra ve (fills, broker, stop).
    Gia moi ngay la 1 bar; bull crossover xay ra ngay 16 -> BUY fill, roi cac
    ngay sau co the cham trailing stop."""
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.0)
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager(sl_multiplier=1.0)
    marks: dict[str, float] = {}
    day_state: dict = {}
    all_fills: list[Fill] = []
    for day, prices in prices_by_day:
        for i, p in enumerate(prices):
            all_fills.extend(
                process_bar(
                    bar_on(day, i, p),
                    broker, strategy, risk, trailing_stop, marks, day_state,
                )
            )
    return all_fills, broker, trailing_stop


def test_stop_touch_before_settle_keeps_tracking_and_position():
    """SPEC1-FIX Lỗi 1 (RED bat buoc): stop chạm khi vị thế CHƯA settle (mua
    16/07, stop cham 17/07 = D+1, gia 19 <= stop 19.01) -> trailing stop VẪN
    theo dõi (is_tracking True), vị thế giữ nguyên qty, KHÔNG có fill SELL
    nào được append."""
    fills, broker, trailing_stop = _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),   # warmup, chua crossover
            (16, [20.0, 20.5]),               # bull crossover -> BUY fill
            (17, [19.0]),                     # gia tut xuong 19: CHAM stop, chua settle (D+1)
        ]
    )
    assert trailing_stop.is_tracking("VCB"), (
        "stop chua settle: trailing stop phai VAN theo doi vi the (khong duoc xoa state)"
    )
    assert broker.position_qty("VCB") > 0, "vi the phai giu nguyen qty"
    assert not any(f.side == "SELL" for f in fills), (
        f"khong duoc co SELL fill nao (chua settle), thuc te: {[f for f in fills if f.side == 'SELL']}"
    )


def test_stop_touch_after_settle_exits_normally():
    """SPEC1-FIX Lỗi 1 (rao chan hoi quy): stop cham khi DA settle (D+3) ->
    thoat binh thuong nhu cu, dung 1 SELL fill."""
    fills, broker, trailing_stop = _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),
            (16, [20.0, 20.5]),   # BUY fill ngay 16
            (17, [21.0, 22.0]),   # gia len, khong cham stop
            (18, [23.0, 24.0]),   # tiep tuc len, khong cham
            (19, [23.5]),         # giat nhe xuong: cham stop, D+3 -> thoat
        ]
    )
    sell_fills = [f for f in fills if f.side == "SELL"]
    assert len(sell_fills) == 1, f"phai co dung 1 SELL (D+3), thuc te {len(sell_fills)}"
    assert broker.position_qty("VCB") == 0, "D+3: vi the phai dong"
    assert not trailing_stop.is_tracking("VCB"), "da dong vi the -> stop het theo doi"


def test_stop_blocked_then_exits_on_d3_state_survives():
    """SPEC1-FIX Lỗi 1 (kiem chung 3): sau khi bi chan vi chua settle (17/07,
    gia 19 cham stop), toi ngay D+3 (19/07) stop VAN thoat duoc — chung minh
    trang thai khong bi mat giua chung."""
    fills, broker, _ = _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),
            (16, [20.0, 20.5]),
            (17, [19.0]),   # cham stop (19 <= 19.01) + chan vi chua settle (D+1)
            (18, [22.0, 23.0, 24.0]),   # gia hoi phuc, khong cham stop
            (19, [23.5]),   # giat nhe: cham stop lan nua, D+3 -> thoat
        ]
    )
    sell_fills = [f for f in fills if f.side == "SELL"]
    assert len(sell_fills) == 1, f"D+3 phai thoat duoc, thuc te {len(sell_fills)} SELL"
    assert broker.position_qty("VCB") == 0


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


# ============ Brief 96 Task 2: Cảnh báo có khử trùng lặp khi stop chạm nhưng chưa settle ============


def test_stop_blocked_warns_once_per_day(monkeypatch):
    """Brief 96 Task 2: 5 bar trong cùng ngày chạm stop khi sellable_qty == 0
    phát đúng 1 alert WARN (khử trùng lặp per-symbol-per-day)."""
    alerts = []
    monkeypatch.setattr(
        "trading.engine.logic.alert",
        lambda level, msg, **kw: alerts.append((level, msg, kw)),
    )
    _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),
            (16, [20.0, 20.5]),  # BUY fill
            (17, [19.0, 18.5, 18.0, 18.2, 18.1]),  # 5 bar đều chạm stop nhưng chưa settle (D+1)
        ]
    )
    blocked_alerts = [a for a in alerts if "chua ban duoc" in a[1]]
    assert len(blocked_alerts) == 1, f"phải có đúng 1 alert WARN, thực tế {len(blocked_alerts)}"
    level, msg, kw = blocked_alerts[0]
    assert level == "WARN"
    assert "vi the VCB da cham stop" in msg
    assert "chua settle T+2.5, sellable_qty=0" in msg
    assert kw.get("symbol") == "VCB"


def test_stop_blocked_warns_again_on_new_day(monkeypatch):
    """Brief 96 Task 2: Sang ngày hôm sau lại chạm stop -> phát tiếp đúng 1 alert WARN nữa (tổng 2)."""
    alerts = []
    monkeypatch.setattr(
        "trading.engine.logic.alert",
        lambda level, msg, **kw: alerts.append((level, msg, kw)),
    )
    _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),
            (16, [20.0, 20.5]),  # BUY fill
            (17, [19.0, 18.5, 18.0]),  # 3 bar chạm stop ngày 17 (D+1) -> 1 alert
            (18, [18.0, 17.5, 17.0]),  # 3 bar chạm stop ngày 18 (D+2) -> 1 alert nữa
        ]
    )
    blocked_alerts = [a for a in alerts if "chua ban duoc" in a[1]]
    assert len(blocked_alerts) == 2, f"phải có đúng 2 alert WARN cho 2 ngày, thực tế {len(blocked_alerts)}"
    for level, msg, kw in blocked_alerts:
        assert level == "WARN"
        assert "vi the VCB da cham stop" in msg
        assert kw.get("symbol") == "VCB"


def test_stop_settled_exits_without_blocked_warn(monkeypatch):
    """Brief 96 Task 2: Khi đã settle, chạm stop -> bán thành công, 0 alert WARN về blocked."""
    alerts = []
    monkeypatch.setattr(
        "trading.engine.logic.alert",
        lambda level, msg, **kw: alerts.append((level, msg, kw)),
    )
    fills, broker, _ = _run_stop_sequence(
        [
            (15, [10.0, 10.0, 10.0, 10.0]),
            (16, [20.0, 20.5]),  # BUY fill
            (17, [21.0, 22.0]),  # giá lên, không chạm stop
            (18, [23.0, 24.0]),  # tiếp tục lên
            (19, [19.0]),        # D+3 (đã settle): chạm stop -> bán thành công
        ]
    )
    blocked_alerts = [a for a in alerts if "chua ban duoc" in a[1]]
    assert len(blocked_alerts) == 0, f"không được có alert blocked nào, thực tế {len(blocked_alerts)}"
    sell_fills = [f for f in fills if f.side == "SELL"]
    assert len(sell_fills) == 1
    assert broker.position_qty("VCB") == 0

