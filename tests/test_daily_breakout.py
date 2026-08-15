from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.daily_breakout import DailyBreakoutStrategy


class FakeContext:
    def __init__(self, qty=0):
        self.qty = qty

    def position_qty(self, symbol):
        return self.qty


def bar_at(i, close, high=None, low=None, symbol="VCB"):
    high = high if high is not None else close
    low = low if low is not None else close
    return Bar(
        symbol,
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(days=i),
        close,
        high,
        low,
        close,
        1000,
    )


def test_warmup_bars_and_no_signal_before_full_history():
    s = DailyBreakoutStrategy()
    # N=20, M=10 chot truoc khi do: can max(N,M) phien TRUOC bar hien tai
    # + 1 bar hien tai moi co the co tin hieu.
    assert s.warmup_bars == max(20, 10) + 1 == 21
    assert s.qty == 100
    # Bar 0..19 (20 phien): bar 19 chi co 19 phien truoc -> chua du -> None
    crossovers = [s.compute_crossover(bar_at(i, 10.0)) for i in range(20)]
    assert crossovers == [None] * 20


def test_close_equal_to_prior_high_is_not_a_breakout():
    s = DailyBreakoutStrategy()
    for i in range(20):
        s.compute_crossover(bar_at(i, 10.0))
    # close == dung dinh 10 (khong vuot) -> KHONG vao lenh
    assert s.compute_crossover(bar_at(20, 10.0)) is None


def test_close_above_prior_high_gives_bull():
    s = DailyBreakoutStrategy()
    for i in range(20):
        s.compute_crossover(bar_at(i, 10.0))
    # close 12 vuot dinh 10 cua 20 phien truoc -> "bull"
    assert s.compute_crossover(bar_at(20, 12.0)) == "bull"


def test_current_bar_high_is_not_in_window():
    s = DailyBreakoutStrategy()
    for i in range(20):
        s.compute_crossover(bar_at(i, 10.0))
    # Bar 20 tu co high=100, close=50. Neu tinh ca bar hien tai vao cua so
    # thi close 50 <= high 100 -> None; dung thi close 50 > dinh 10 -> "bull"
    assert s.compute_crossover(bar_at(20, 50.0, high=100.0, low=10.0)) == "bull"


def test_previous_bar_high_is_included_in_window():
    s = DailyBreakoutStrategy()
    for i in range(19):
        s.compute_crossover(bar_at(i, 10.0))
    # Bar 19 (phien ngay truoc bar tin hieu) co high=100, close=10
    assert s.compute_crossover(bar_at(19, 10.0, high=100.0, low=10.0)) is None
    # Bar 20 close=50: van duoi dinh 100 cua bar 19 -> None. Neu loai nham
    # bar 19 ra khoi cua so thi 50 > 10 -> "bull" (sai).
    assert s.compute_crossover(bar_at(20, 50.0, high=50.0, low=10.0)) is None


def test_close_below_prior_low_gives_bear():
    s = DailyBreakoutStrategy()
    for i in range(20):
        s.compute_crossover(bar_at(i, 10.0))
    # close 5 thung day 10 cua 10 phien truoc -> "bear"
    assert s.compute_crossover(bar_at(20, 5.0)) == "bear"


def test_symbol_state_is_isolated():
    s = DailyBreakoutStrategy()
    # VCB: 20 phien flat + bar 20 vuot dinh -> "bull"
    for i in range(20):
        s.compute_crossover(bar_at(i, 10.0, symbol="VCB"))
    assert s.compute_crossover(bar_at(20, 12.0, symbol="VCB")) == "bull"
    # HPG: chi 5 phien — khong du warmup rieng, khong duoc huong state cua VCB
    hpg = [s.compute_crossover(bar_at(i, 5.0, symbol="HPG")) for i in range(5)]
    assert hpg == [None] * 5
    # VCB van con nguyen: bar 21 close=10 khong vuot dinh -> None (cua so cua
    # VCB khong bi cac bar HPG chen vao lam hong)
    assert s.compute_crossover(bar_at(21, 10.0, symbol="VCB")) is None


def test_on_bar_buys_when_flat_and_sells_when_holding():
    s = DailyBreakoutStrategy(qty=100)
    ctx = FakeContext(qty=0)
    for i in range(20):
        assert s.on_bar(bar_at(i, 10.0), ctx) is None
    # bull + dang flat -> BUY dung qty
    sig = s.on_bar(bar_at(20, 12.0), ctx)
    assert sig is not None and sig.side == "BUY" and sig.qty == 100
    ctx.qty = 100  # gia lap da mua
    # close thung day -> "bear" -> SELL toan bo vi the
    sig2 = s.on_bar(bar_at(21, 5.0), ctx)
    assert sig2 is not None and sig2.side == "SELL" and sig2.qty == 100


def test_on_bar_no_buy_when_already_holding():
    s = DailyBreakoutStrategy(qty=100)
    ctx = FakeContext(qty=100)
    for i in range(20):
        s.on_bar(bar_at(i, 10.0), ctx)
    # bull nhung dang giu -> khong mua them
    assert s.on_bar(bar_at(20, 12.0), ctx) is None


def test_last_atr_tracks_per_symbol_for_risk_and_stop():
    # run_backtest goi strategy.last_atr() cho RiskManager (approve_sized tu
    # choi BUY khi atr=None) va TrailingStopManager — ATR phai co that.
    s = DailyBreakoutStrategy(atr_period=1)
    assert s.last_atr("VCB") is None
    s.compute_crossover(bar_at(0, 10.0))
    assert s.last_atr("VCB") == 0.0  # TR = high-low = 0
    s.compute_crossover(bar_at(1, 20.0))
    assert s.last_atr("VCB") == 10.0  # TR = |20-10| = 10
