from datetime import datetime, timedelta

import pytest

from trading.backtest import BacktestReport, run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategies.sma_cross import SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager

CAP = 100_000_000


def make_bars(prices: list[float]) -> list[Bar]:
    """Moi ngay giao dich co 8 bar (9:00-10:45, 15 phut/bar) — du cho T+2,5:
    mua ngay D, ban duoc tu D+3 (can >= 3 ngay giao dich giua mua va ban)."""
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [
        Bar(
            "VCB",
            start + timedelta(days=i // 8, minutes=15 * (i % 8)),
            p, p, p, p, 1000,
        )
        for i, p in enumerate(prices)
    ]


def test_deterministic_same_input_same_output():
    prices = [10] * 20 + [20] * 10 + [10] * 10
    bars = make_bars(prices)
    strategy = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk = RiskManager(capital=CAP)
    trailing_stop = TrailingStopManager()
    r1 = run_backtest(bars, strategy, risk, trailing_stop, CAP)

    strategy2 = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk2 = RiskManager(capital=CAP)
    trailing_stop2 = TrailingStopManager()
    r2 = run_backtest(bars, strategy2, risk2, trailing_stop2, CAP)

    assert r1 == r2


def test_report_has_at_least_one_round_trip_trade():
    # 60 bar = 7.5 ngay giao dich: bull crossover ~bar 21 (ngay 3), bear ~bar
    # 41 (ngay 6) — mua D+3 ban duoc, nen round-trip phai xay ra. Chuoi 40 bar
    # cu (5 ngay) la khong du: mua ngay 3, bear ngay 4 = D+1, chua settle.
    prices = [10] * 20 + [20] * 20 + [10] * 20
    bars = make_bars(prices)
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=10, slow=20, qty=100),
        # max_daily_loss_pct mac dinh (3%) khong con phu hop sau khi BUY qty
        # duoc ATR sizing quyet dinh (lon hon nhieu so voi fixed-100 truoc
        # day) - swing gia 20->10 tren qty lon trong test nay tao unrealized
        # loss ~7% von, se bi halt truoc khi kip SELL round-trip. Noi len
        # nguong o day chi de test nay khong bi chan boi 1 tinh huong tong
        # hop bien do lon bat thuong - KHONG doi default cua RiskManager.
        RiskManager(capital=CAP, max_daily_loss_pct=0.5),
        TrailingStopManager(),
        CAP,
    )
    assert r.trades >= 1
    assert 0.0 <= r.win_rate <= 1.0
    assert r.max_drawdown >= 0.0


def test_ending_cash_reflects_fees_when_no_trades():
    bars = make_bars([10] * 5)
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=10, slow=20, qty=100),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )
    assert r.ending_cash == CAP
    assert r.trades == 0


# ============ SPEC 1b: moc mua-va-giu (buy-and-hold) ============


def make_daily_bars(prices: list[float]) -> list[Bar]:
    """Mot bar moi ngay giao dich — du cho T+2,5: mua ngay D ban duoc tu D+3."""
    start = datetime(2026, 7, 1, 9, 0, tzinfo=TZ)
    return [
        Bar("VCB", start + timedelta(days=i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]


def _run(prices: list[float]) -> BacktestReport:
    return run_backtest(
        make_daily_bars(prices),
        SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )


def test_buy_and_hold_beats_strategy_on_steadily_rising_prices():
    """SPEC-1b kiem chung 1: chuoi gia tang deu — mua-va-giu phai THANG moi
    chien luoc co giao dich (vi phi: moi vong giao dich tru phi, mua-va-giu
    chi tra 2 lan phi)."""
    # Tang deu 10 -> 30. SmaCross(2,4) se co giao dich (bull roi bear), moi
    # vong tru phi -> realized + unrealized cua strategy phai THUA buy-and-hold.
    prices = [10.0 + i for i in range(30)]
    r = _run(prices)
    bh = r.buy_and_hold_pnl
    strat = r.realized_pnl + r.unrealized_pnl
    assert bh > 0, f"mua-va-giu tren chuoi tang phai co lai, thuc te {bh}"
    assert strat < bh, (
        f"chien luoc co giao dich phai thua mua-va-giu (phi), thuc te "
        f"strategy={strat}, buy_and_hold={bh}"
    )


def test_buy_and_hold_loses_on_steadily_falling_prices():
    """SPEC-1b kiem chung 2: chuoi gia giam deu — mua-va-giu phai LO."""
    prices = [30.0 - i for i in range(30)]
    r = _run(prices)
    assert r.buy_and_hold_pnl < 0, (
        f"mua-va-giu tren chuoi giam phai lo, thuc te {r.buy_and_hold_pnl}"
    )


# ============ SPEC 1c: loc bar OHLC <= 0, co bao cao ============


def test_dirty_bar_filtered_reported_and_never_filled_at_zero():
    """SPEC-1c kiem chung: chen bar open=0 vao chuoi — bar do phai bi LOAI,
    so dong loai phai duoc bao cao dung, va khong co lenh nao khop gia 0."""
    prices = [10.0] * 6 + [10.0 + i for i in range(24)]
    bars = make_daily_bars(prices)
    # chen bar rac open=0 vao ngay thu 4 (index 3) — dung giua chuoi
    dirty_ts = bars[3].ts
    bars.insert(4, Bar("VCB", dirty_ts + timedelta(hours=1), 0.0, 0.0, 0.0, 0.0, 0))
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )
    assert r.filtered_bars == {"VCB": 1}, (
        f"so dong rac phai duoc bao cao: 1, thuc te {r.filtered_bars}"
    )
    assert all(f.price > 0 for f in r.fills), (
        f"khong duoc co lenh khop gia 0: {[f.price for f in r.fills if f.price <= 0]}"
    )
    # Sang so voi chay khong co bar rac: cung so lenh, cung pnl (bar rac bi loai
    # truoc khi vao vong lap nen khong anh huong gi)
    r_clean = _run(prices)
    assert r.trades == r_clean.trades
    assert abs(r.realized_pnl - r_clean.realized_pnl) < 1e-6


# ============ Equity curve phoi ra BacktestReport (backtest-grafana) ============


def test_equity_curve_exposed_as_ts_equity_pairs():
    """Duong von phai phoi ra BacktestReport: moi phan tu la (ts, equity) voi
    ts lay tu bar; diem DAU = (ts bar dau, capital)."""
    bars = make_daily_bars([10.0] * 5)
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )
    curve = r.equity_curve
    assert len(curve) == len(bars) + 1, (
        f"diem dau capital + 1 diem/bar, thuc te {len(curve)} vs {len(bars) + 1}"
    )
    assert curve[0] == (bars[0].ts, CAP)
    assert all(
        isinstance(ts, datetime) and isinstance(equity, (int, float))
        for ts, equity in curve
    ), f"moi phan tu phai la (ts, equity), thuc te: {curve[:2]}"
    for i, b in enumerate(bars, start=1):
        assert curve[i][0] == b.ts, f"ts diem {i} phai lay tu bar, thuc te {curve[i][0]}"


def test_equity_curve_length_follows_clean_bars_not_raw():
    """Do dai duong von theo so bar SACH (bar rac bi loc TRUOC vong lap) —
    khong phai so bar tho. Chen 1 bar rac vao 5 bar sach -> len = 6
    (5 sach + diem dau capital), KHONG phai 7 (6 tho + diem dau)."""
    bars = make_daily_bars([10.0] * 5)
    bars.insert(3, Bar("VCB", bars[2].ts + timedelta(hours=1), 0.0, 0.0, 0.0, 0.0, 0))
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )
    assert len(r.equity_curve) == 6, (
        f"5 bar sach + 1 diem dau = 6, thuc te {len(r.equity_curve)} (bar rac khong duoc tinh)"
    )
    assert r.filtered_bars == {"VCB": 1}


def _bh_run(prices: list[float]):
    """Chay backtest tren mot day gia, tra ve BacktestReport."""
    return run_backtest(
        make_daily_bars(prices),
        SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0),
        RiskManager(capital=CAP),
        TrailingStopManager(),
        CAP,
    )


def test_buy_and_hold_curve_ends_exactly_at_buy_and_hold_pnl():
    """BAT BIEN chong "mot cong thuc hai ban": diem CUOI cua duong mua-va-giu
    phai bang chinh xac capital + buy_and_hold_pnl. Neu ai do tinh lai duong
    nay bang cong thuc khac (vd noi suy tuyen tinh trong SQL) thi test do."""
    r = _bh_run([10.0, 11.0, 9.0, 12.0, 10.5, 13.0])
    assert r.buy_and_hold_curve, "phai phoi ra duong mua-va-giu"
    _, end_equity = r.buy_and_hold_curve[-1]
    assert end_equity == pytest.approx(CAP + r.buy_and_hold_pnl), (
        f"diem cuoi {end_equity} phai == capital + buy_and_hold_pnl "
        f"{CAP + r.buy_and_hold_pnl} — hai cong thuc dang lech nhau"
    )


def test_buy_and_hold_curve_aligns_with_equity_curve():
    """Hai duong phai cung so diem va cung moc ts thi Grafana moi ve chong
    len nhau duoc."""
    r = _bh_run([10.0, 11.0, 9.0, 12.0, 10.5])
    assert len(r.buy_and_hold_curve) == len(r.equity_curve)
    assert [ts for ts, _ in r.buy_and_hold_curve] == [ts for ts, _ in r.equity_curve]


def test_buy_and_hold_curve_shows_real_drawdown_when_price_dips():
    """Day la LOI da bat duoc khi audit: Grafana ve mua-va-giu bang mot duong
    THANG noi suy, nen drawdown cua benchmark luon = 0 va cu sap that bi che
    di (do that: VCB 2020-02-26 gia -7,5% ma duong ve dang di LEN).

    Gia tut sau o giua -> duong mua-va-giu PHAI co drawdown > 0. Duong thang
    khong bao gio pass duoc test nay."""
    r = _bh_run([10.0, 12.0, 6.0, 11.0, 13.0])  # sap giua ky roi hoi
    curve = [e for _, e in r.buy_and_hold_curve]
    peak = curve[0]
    max_dd = 0.0
    for e in curve:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak)
    assert max_dd > 0.10, (
        f"gia tut 50% giua ky ma duong mua-va-giu chi sut {max_dd:.1%} — "
        f"dau hieu duong bi lam phang/noi suy"
    )


# ============ goi B (2026-09-03): run_backtest nhan phi/thue/settle ============


def _crypto_prices() -> list[float]:
    """Chuoi co giao dich round-trip (bull roi bear) — de thay phi ap vao dau."""
    return [10.0] * 20 + [20.0] * 10 + [10.0] * 10


def test_run_backtest_default_identical_to_no_params():
    """Khong truyen gi (mac dinh None -> hang so VN) phai ra Y HET khi khong
    co tham so moi — chan ranh gioi an toan voi phien 04/09 (engine goi qua
    PaperBroker khong tham so)."""
    bars = make_daily_bars(_crypto_prices())
    strat = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
    base = run_backtest(bars, strat, RiskManager(capital=CAP), TrailingStopManager(), CAP)
    with_params = run_backtest(
        bars, strat, RiskManager(capital=CAP), TrailingStopManager(), CAP,
        fee_rate=None, sell_tax_rate=None, slippage_bps=None, settle_days=None,
    )
    assert base.ending_cash == with_params.ending_cash
    assert base.realized_pnl == with_params.realized_pnl
    assert base.buy_and_hold_pnl == with_params.buy_and_hold_pnl
    assert base.fills == with_params.fills


def test_run_backtest_settle_zero_lets_sell_next_day():
    """settle_days=0 (crypto): SELL sau crossover bear khop ngay — khong bi T+3
    chan, so lenh/PNL khac voi mac dinh VN."""
    # Bull 3 ngay roi bear ngay — bear crossover xay ra < D+3 sau khi mua, nen
    # VN (settle=3) bi chan SELL den khi du ngay, crypto (settle=0) khop ngay.
    bars = make_daily_bars([10.0] * 6 + [20.0] * 3 + [10.0] * 6)
    strat = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
    vn = run_backtest(bars, strat, RiskManager(capital=CAP), TrailingStopManager(), CAP)
    crypto = run_backtest(
        bars, strat, RiskManager(capital=CAP), TrailingStopManager(), CAP, settle_days=0
    )
    # crypto ban duoc som hon -> so lenh phai khac (khong the bang nhau)
    assert crypto.trades != vn.trades or crypto.ending_cash != vn.ending_cash
