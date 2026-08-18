import json
from datetime import datetime, time, timedelta
from pathlib import Path

from trading.calendar_vn import TZ
from trading.derivative_backtest import DERIVATIVE_SYMBOL, run_derivative_backtest
from trading.derivative_position import DERIVATIVE_CONTRACT_MULTIPLIER
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy

CAP = 100_000_000
FEE = 8_250.0


def bars_from_prices(prices: list[float], sym: str = DERIVATIVE_SYMBOL) -> list[Bar]:
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate(prices)
    ]


def new_strategy() -> SmaCrossStrategy:
    # fast=2/slow=4, atr_pct_threshold=0.0: tat filter ATR% de crossover
    # khong bi che (cung ky thuat da dung trong tests/test_engine_logic.py
    # cho trailing-stop test) - qty=1 vi lot_size phai sinh = 1.
    return SmaCrossStrategy(fast=2, slow=4, qty=1, atr_period=1, atr_pct_threshold=0.0)


def test_report_unrealized_pnl_applies_contract_multiplier():
    # Chuoi gia da xac nhan that (chay qua compute_crossover truc tiep): bull
    # tai bar4 (close=11) mo long, cac bar sau tiep tuc uptrend, KHONG co bear
    # crossover -> vi the con mo o cuoi chuoi, mark = close bar6 (16).
    # _unrealized() phai nhan he so nhan hop dong (100,000 VND/diem), khong
    # tru fee (hanh vi hien tai giu nguyen - chi them he so nhan).
    prices = [10, 10, 10, 10, 11, 13, 16]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    expected_unrealized = (16.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER
    assert len(report.fills) == 1  # chi mo long, chua co lenh dong
    # DERIV-FEE-1: unrealized tru phi MO (vi the dang mo 1 hop dong)
    assert abs(report.unrealized_pnl - (expected_unrealized - FEE)) < 1e-9


def test_stop_loss_long_exits_at_level_on_low_touch():
    # Chuoi gia da xac nhan that (chay qua compute_crossover truc tiep): bull
    # bar4 (close=11) mo long. SL=1 -> level 10. Bar5 (close=9.5): low=9.5 <= 10
    # va KHONG co bear crossover (fast 10.25 > slow 10.125) -> chi SL moi dong
    # duoc lenh. Exit tai min(open=9.5, level 10) = 9.5 (bar dong duoi muc SL
    # = min quy uoc gap cua repo, giong TrailingStopManager).
    prices = [10, 10, 10, 10, 11, 9.5]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP, stop_loss_points=1.0)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and abs(close_fill.price - 9.5) < 1e-9
    expected_pnl = (9.5 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_stop_loss_short_exits_at_level_on_high_touch():
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): bear bar5
    # (close=9) mo short tu flat. SL=1 -> level 10. Bar6 (close=10): high=10 >= 10
    # va KHONG co bull crossover (fast 9.5 < slow 11.25) -> chi SL moi dong duoc.
    # Exit tai max(open=10, level 10) = 10.
    prices = [10, 11, 12, 14, 12, 9, 10]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP, stop_loss_points=1.0)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "SELL" and abs(open_fill.price - 9.0) < 1e-9
    assert close_fill.side == "BUY" and abs(close_fill.price - 10.0) < 1e-9
    expected_pnl = (9.0 - 10.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_take_profit_long_exits_at_level_on_high_touch():
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): bull bar4
    # (close=11) mo long. TP=1 -> level 12. Bar5 (close=13): high=13 >= 12,
    # khong co crossover -> chi TP moi dong duoc. Exit tai max(open=13, 12) = 13.
    prices = [10, 10, 10, 10, 11, 13]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP, take_profit_points=1.0)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and abs(close_fill.price - 13.0) < 1e-9
    expected_pnl = (13.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_take_profit_short_exits_at_level_on_low_touch():
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): bear bar5
    # (close=9) mo short tu flat. TP=1 -> level 8. Bar6 (close=6): low=6 <= 8,
    # khong co crossover -> chi TP moi dong duoc. Exit tai min(open=6, 8) = 6.
    prices = [10, 11, 12, 14, 12, 9, 6]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP, take_profit_points=1.0)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "SELL" and abs(open_fill.price - 9.0) < 1e-9
    assert close_fill.side == "BUY" and abs(close_fill.price - 6.0) < 1e-9
    expected_pnl = (9.0 - 6.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_stop_loss_takes_priority_when_tp_and_sl_both_hit_same_bar():
    # Bar5 custom (open=10, high=14, low=8, close=12): low=8 <= 9 (SL=2 tu entry
    # 11) VA high=14 >= 13 (TP=2) cung luc -> SL uu tien (conservative), dong
    # tai min(open=10, level 9) = 9. Khong co crossover o bar5 (close=12 giu
    # fast > slow) nen exit nay chi den tu SL/TP.
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = bars_from_prices([10, 10, 10, 10, 11])  # bull bar4 -> long @11
    bars.append(Bar(sym, start + timedelta(minutes=5 * 5), 10.0, 14.0, 8.0, 12.0, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP, stop_loss_points=2.0, take_profit_points=2.0
    )

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and abs(close_fill.price - 9.0) < 1e-9
    expected_pnl = (9.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_no_reentry_on_same_bar_after_stop_loss_exit():
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): bull bar4
    # (close=11) mo long, bar5 (close=9) VUA cham SL (9 <= 10, SL=1) VUA la
    # bear crossover. Sau khi SL dong, KHONG duoc mo vi the moi cung bar nay
    # (neu khong, bear & flat se mo short -> 3 fills).
    prices = [10, 10, 10, 10, 11, 9]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP, stop_loss_points=1.0)

    assert len(report.fills) == 2  # chi mo long + dong SL, khong mo short cung bar
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and abs(close_fill.price - 9.0) < 1e-9


def test_two_consecutive_losing_trades_halt_third_open_same_day():
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): bull bar4
    # (11) mo long -> bear bar5 (9) dong, LO 1 (-208,250); bull bar6 (13) mo
    # long -> bear bar7 (7) dong, LO 2 (-608,250); bull bar8 (16) la tin hieu
    # mo thu 3 CUNG NGAY -> bi risk chan boi 2 lenh thua lien tiep (streak),
    # KHONG phai daily-loss: tong lo -816,500 < 2% x 100tr = 2,000,000.
    prices = [10, 10, 10, 10, 11, 9, 13, 7, 16]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    # Chi 2 round-trip (4 fill) - lenh mo thu 3 KHONG duoc fill.
    assert len(report.fills) == 4
    assert report.trades == 2
    assert risk.halted_date == bars[-1].ts.date()
    assert all(f.pnl is not None and f.pnl < 0 for f in report.fills if f.pnl is not None)


def test_intraday_close_time_none_default_keeps_position_open_past_1420():
    # Regression: khong truyen intraday_close_time -> vi the van mo qua 14:20,
    # khong co fill dong ngoai y strategy (bar5 close=12 khong tao crossover).
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 12.0, 12.0, 12.0, 12.0, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 1  # chi mo long, khong dong
    assert report.fills[0].side == "BUY" and abs(report.fills[0].price - 11.0) < 1e-9
    # DERIV-FEE-1: tru phi mo
    assert abs(report.unrealized_pnl - ((12.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE)) < 1e-9


def test_intraday_close_time_force_closes_open_position_at_cutoff():
    # Truyen intraday_close_time=14:20: bar 14:25 (close=7) co ts.time() >= 14:20
    # -> ep dong tai bar.close=7, VA bar nay cung la bear crossover -> khong
    # duoc mo vi the moi cung bar (rule "khong mo lai cung bar" nhu SL/TP).
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 7.0, 7.0, 7.0, 7.0, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP, intraday_close_time=time(14, 20)
    )

    assert len(report.fills) == 2  # mo long + dong EOD, khong mo short cung bar
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and abs(close_fill.price - 7.0) < 1e-9
    expected_pnl = (7.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_intraday_close_time_does_not_fire_when_already_flat():
    # Khong co vi the mo tai/sau gio cat -> khong phat sinh fill thua.
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 10])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 10.0, 10.0, 10.0, 10.0, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP, intraday_close_time=time(14, 20)
    )

    assert len(report.fills) == 0  # flat suot, khong co gi de dong


def test_intraday_close_time_keeps_profitable_position_past_cutoff():
    # User yeu cau: den 14:20 ma lenh DANG LAI thi giu qua dem. Bar 14:25
    # close=13, long @11 -> unrealized +200,000 > 0 -> KHONG ep dong, vi the
    # van mo cuoi chuoi (bar5 close=13 khong tao crossover).
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 13.0, 13.0, 13.0, 13.0, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP, intraday_close_time=time(14, 20)
    )

    assert len(report.fills) == 1  # chi mo long, lenh lai duoc giu
    assert report.fills[0].side == "BUY" and abs(report.fills[0].price - 11.0) < 1e-9
    # DERIV-FEE-1: tru phi mo
    assert abs(report.unrealized_pnl - ((13.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE)) < 1e-9


def test_daily_loss_halt_resets_next_day_not_cumulative():
    # Bug that: daily_pnl truyen vao approve_open la PnL TICH LUY tu dau chuoi
    # (broker.realized_pnl khong reset theo ngay) -> voi von nho (30tr, nguong
    # 2% = 600,000), 1 lenh thua dau -708,250 lam halt VINH VIEN (cumulative
    # khong bao gio phuc hoi) -> moi lenh mo sau deu bi chan.
    # Chuoi gia da xac nhan that (compute_crossover truc tiep): ngay 1 (08-08)
    # [10,10,10,10,11,4]: bull bar4 @11 mo long, bear bar5 @4 dong (lo
    # -708,250 <= -600,000). Ngay 2 (08-09) [13,16,1]: bull bar7 @16 mo lai,
    # bear bar8 @1 dong. Voi fix (daily theo ngay): ngay 2 daily pnl bat dau
    # tu 0 -> lenh ngay 2 duoc phep; khong halt.
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11, 4])
    ]
    bars += [
        Bar(sym, datetime(2026, 8, 9, 9, 0, tzinfo=TZ) + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([13, 16, 1])
    ]
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=30_000_000, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, 30_000_000)

    # 2 round-trip day du (mo/dong ngay 1 + mo/dong ngay 2), khong halt.
    assert len(report.fills) == 4
    assert report.trades == 2
    assert risk.halted_date is None


def test_eod_keep_min_profit_points_closes_small_profit_below_threshold():
    # Lenh lai gross +50,000 (bar 14:25 close=11.5, long @11) nho hon nguong
    # 1.0 diem = 100,000 (du bu D+ 1 dem ~87k + phi dong 8,250 @1900) ->
    # KHONG giu, dong tai cutoff (bar.close=11.5).
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 11.5, 11.5, 11.5, 11.5, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP,
        intraday_close_time=time(14, 20), eod_keep_min_profit_points=1.0,
    )

    assert len(report.fills) == 2  # mo long + dong EOD
    _open_fill, close_fill = report.fills
    assert close_fill.side == "SELL" and abs(close_fill.price - 11.5) < 1e-9
    expected_pnl = (11.5 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


def test_eod_keep_min_profit_points_keeps_profit_above_threshold():
    # Lenh lai +150,000 (bar 14:25 close=12.5) > nguong 1.0 diem -> GIU qua dem.
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 12.5, 12.5, 12.5, 12.5, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP,
        intraday_close_time=time(14, 20), eod_keep_min_profit_points=1.0,
    )

    assert len(report.fills) == 1  # chi mo long, khong dong
    # DERIV-FEE-1: tru phi mo
    assert abs(report.unrealized_pnl - ((12.5 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE)) < 1e-9


def test_eod_keep_min_profit_points_default_zero_keeps_any_profit():
    # Regression: default 0.0 -> +50,000 van duoc giu (hanh vi cu).
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    sym = DERIVATIVE_SYMBOL
    bars = [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate([10, 10, 10, 10, 11])
    ]
    bars.append(Bar(sym, datetime(2026, 8, 8, 14, 25, tzinfo=TZ), 11.5, 11.5, 11.5, 11.5, 100))
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(
        bars, strategy, risk, CAP, intraday_close_time=time(14, 20)
    )

    assert len(report.fills) == 1  # +50,000 > 0 (nguong mac dinh) -> giu
    # DERIV-FEE-1: tru phi mo
    assert abs(report.unrealized_pnl - ((11.5 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE)) < 1e-9


def test_long_cycle_bull_opens_long_then_bear_closes_it():
    # Chuoi gia da xac nhan that (chay qua SmaCrossStrategy.compute_crossover
    # truc tiep de lay index bull/bear that, khong doan tay): bull tai bar4
    # (close=11), bear tai bar10 (close=16).
    prices = [10, 10, 10, 10, 11, 13, 16, 20, 24, 20, 16, 12, 9, 7]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert (
        open_fill.side == "BUY"
        and open_fill.qty == 1
        and abs(open_fill.price - 11.0) < 1e-9
    )
    assert (
        close_fill.side == "SELL"
        and close_fill.qty == 1
        and abs(close_fill.price - 16.0) < 1e-9
    )
    expected_pnl = (16.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9
    # DERIV-FEE-1: realized tru ca phi mo (fill.pnl giu nguyen — chi ket toan doi)
    assert abs(report.realized_pnl - (expected_pnl - FEE)) < 1e-9
    assert report.trades == 1


def test_short_cycle_bear_opens_short_from_flat_then_bull_covers_it():
    # Chuoi gia da xac nhan that: bear tai bar5 (close=9, tu trang thai
    # flat - chua tung mo long truoc do), bull tai bar8 (close=12, cover).
    prices = [10, 11, 12, 14, 12, 9, 6, 9, 12, 15]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert (
        open_fill.side == "SELL"
        and open_fill.qty == 1
        and abs(open_fill.price - 9.0) < 1e-9
    )
    assert (
        close_fill.side == "BUY"
        and close_fill.qty == 1
        and abs(close_fill.price - 12.0) < 1e-9
    )
    expected_pnl = (9.0 - 12.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9
    assert close_fill.pnl < 0
    # DERIV-FEE-1: realized tru ca phi mo
    assert abs(report.realized_pnl - (expected_pnl - FEE)) < 1e-9


def test_halted_day_blocks_new_open_after_loss_breaches_threshold():
    # Chuoi gia da xac nhan that (chay qua compute_crossover truc tiep, khong
    # doan tay): bull bar4 (close=11) mo long, bear bar8 (close=10) dong.
    # Round-trip dau tien LO THAT sau khi co he so nhan:
    # (10-11)*1*100,000 - 8,250 = -108,250 - khong con la "lo ao" do phi che
    # mat lai 5 diem nhu chuoi cu (16-11)*100,000-8,250 = +491,750 (LAI).
    prices = [10, 10, 10, 10, 11, 13, 16, 13, 10, 7, 9, 12, 16, 20]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    # Von nho de khoan lo round-trip dau tien (-102,700) vuot nguong 3% cua
    # 50,000 (=-1,500).
    risk = DerivativeRiskManager(
        capital=50_000, max_contracts=1, max_daily_loss_pct=0.03
    )

    report = run_derivative_backtest(bars, strategy, risk, 50_000)

    # Chi co dung 2 fill (mo bar4, dong bar8) - bull thu 2 tai bar11 KHONG
    # duoc mo vi da bi halt do lo round-trip dau vuot nguong.
    assert len(report.fills) == 2
    assert risk.halted_date is not None


def test_real_captured_ohlc_sample_runs_end_to_end():
    # Smoke test doi voi du lieu OHLC that da capture (Phase 0/khao sat
    # 2026-08-07) - dam bao code chay duoc voi shape response that, khong
    # chi bar tong hop. File da nam TRONG repo (commit cc8048e, 2026-08-18)
    # nen luon co san - khong con can nhanh skip gitignored.
    sample_path = Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json")

    raw = json.loads(sample_path.read_text())
    bars = sorted(
        (
            Bar(
                row["symbol"],
                datetime.strptime(row["trading_date"], "%Y/%m/%d %H:%M:%S").replace(
                    tzinfo=TZ
                ),
                row["open_price"],
                row["high_price"],
                row["low_price"],
                row["close_price"],
                int(row["volume"]),
            )
            for row in raw
        ),
        key=lambda b: b.ts,
    )
    strategy = SmaCrossStrategy(
        qty=1
    )  # tham so mac dinh (fast=10/slow=20) - khong ep crossover
    risk = DerivativeRiskManager(capital=CAP)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    # Khong assert crossover cu the nao xay ra (du lieu that, khong kiem
    # soat duoc) - chi chung minh code chay het toan bo bar that ma khong
    # loi/crash, va bao cao co hinh dang hop le: moi fill "mo" (pnl=None)
    # phai co dung 1 fill "dong" (pnl khong None) di kem, tru toi da 1 vi
    # the con dang mo o cuoi chuoi du lieu (chua co bar nao dong no).
    opens = [f for f in report.fills if f.pnl is None]
    closes = [f for f in report.fills if f.pnl is not None]
    assert report.trades == len(closes)
    assert len(opens) - len(closes) in (0, 1)
    assert isinstance(report.realized_pnl, float)


# ============ DERIV-FEE-1: phi MO trong PnL phai sinh (open_fee rieng) ============


def _broker():
    from trading.derivative_position import DerivativePaperBroker

    return DerivativePaperBroker(capital=CAP)


def test_roundtrip_long_cash_minus_capital_equals_realized_pnl():
    """DERIV-FEE-1 kiem chung 1 (RED bat buoc, LONG): mo long roi dong -> 
    cash - capital == realized_pnl. Phai DO tren code cu (bo sot phi mo),
    lech dung bang phi mo (qty * fee_per_contract)."""
    b = _broker()
    ts = datetime(2026, 8, 8, 9, 5, tzinfo=TZ)
    b.open_long(DERIVATIVE_SYMBOL, 1, 1300.0, ts)
    b.close(DERIVATIVE_SYMBOL, 1300.0, datetime(2026, 8, 8, 9, 10, tzinfo=TZ))
    assert b.position_qty(DERIVATIVE_SYMBOL) == 0
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01, (
        f"cash-capital ({b.cash - b.capital}) phai bang realized_pnl ({b.realized_pnl}) — "
        f"hien lech {abs((b.cash - b.capital) - b.realized_pnl)} = phi mo bi bo sot"
    )


def test_roundtrip_short_cash_minus_capital_equals_realized_pnl():
    """DERIV-FEE-1 kiem chung 2 (RED bat buoc, SHORT): nhanh short co cong
    thuc PnL rieng (avg_price - price) — mot ban sua chi dung long la chua xong."""
    b = _broker()
    b.open_short(DERIVATIVE_SYMBOL, 1, 1300.0, datetime(2026, 8, 8, 9, 5, tzinfo=TZ))
    b.close(DERIVATIVE_SYMBOL, 1300.0, datetime(2026, 8, 8, 9, 10, tzinfo=TZ))
    assert b.position_qty(DERIVATIVE_SYMBOL) == 0
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01, (
        f"cash-capital ({b.cash - b.capital}) phai bang realized_pnl ({b.realized_pnl}) — "
        f"hien lech {abs((b.cash - b.capital) - b.realized_pnl)} = phi mo bi bo sot"
    )


def test_unrealized_reflects_open_fee():
    """DERIV-FEE-1 kiem chung 4: mo vi the, mark BANG DUNG gia vao ->
    _unrealized phai AM dung bang phi mo (khong phai 0)."""
    from trading.derivative_backtest import _unrealized

    b = _broker()
    ts = datetime(2026, 8, 8, 9, 5, tzinfo=TZ)
    b.open_long(DERIVATIVE_SYMBOL, 1, 1300.0, ts)
    upnl = _unrealized(b, {DERIVATIVE_SYMBOL: 1300.0})
    assert upnl == -FEE, f"_unrealized phai = -phi mo ({-FEE}), thuc te: {upnl}"


def test_open_fee_cleared_between_rounds():
    """DERIV-FEE-1 kiem chung 5: nhieu vong lien tiep — open_fee duoc don
    sach sau close, khong ro sang vong sau (realized = tong dung cua 2 vong)."""
    b = _broker()
    t1 = datetime(2026, 8, 8, 9, 5, tzinfo=TZ)
    t2 = datetime(2026, 8, 8, 9, 10, tzinfo=TZ)
    t3 = datetime(2026, 8, 8, 9, 15, tzinfo=TZ)
    t4 = datetime(2026, 8, 8, 9, 20, tzinfo=TZ)
    # vong 1: long 1300 -> 1302 (+200.000 - phi dong 8.250 - phi mo 8.250)
    b.open_long(DERIVATIVE_SYMBOL, 1, 1300.0, t1)
    b.close(DERIVATIVE_SYMBOL, 1302.0, t2)
    assert b.positions[DERIVATIVE_SYMBOL].open_fee == 0.0, "open_fee phai duoc don sau close"
    # vong 2: short 1302 -> 1300 (+200.000 - phi dong - phi mo)
    b.open_short(DERIVATIVE_SYMBOL, 1, 1302.0, t3)
    b.close(DERIVATIVE_SYMBOL, 1300.0, t4)
    assert b.positions[DERIVATIVE_SYMBOL].open_fee == 0.0, "open_fee phai duoc don sau close"
    expected = 2 * (2 * DERIVATIVE_CONTRACT_MULTIPLIER - 2 * FEE)
    assert abs(b.realized_pnl - expected) < 0.01, (
        f"realized 2 vong phai = {expected}, thuc te: {b.realized_pnl}"
    )
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01
