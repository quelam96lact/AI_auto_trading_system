import math
from datetime import UTC, datetime, timedelta

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar
from trading.perp_backtest import run_perp_backtest


def _make_bar(
    idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    vol: float = 100.0,
    symbol: str = "BTC-USDT",
) -> Bar:
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    dt = base_dt + timedelta(hours=idx)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=vol,
    )


def _build_module_a_base_bars(n: int = 280) -> list[Bar]:
    """Tạo chuỗi bar nền cho Module A:
    - 260 bar đầu biến động hẹp (TR=2.0, ATR14=2.0).
    - 10 bar tiếp theo biến động tăng nhẹ (TR=4.0) để nạp warm-up.
    """
    bars: list[Bar] = []
    for i in range(260):
        bars.append(_make_bar(i, 100.0, 101.0, 99.0, 100.0))
    for i in range(260, 270):
        bars.append(_make_bar(i, 100.0, 102.0, 98.0, 100.0))
    return bars


def _generate_valid_module_b_bars() -> list[Bar]:
    """Helper tạo chuỗi bar nền và bar tín hiệu thoả mãn Module B Long hoàn chỉnh."""
    bars: list[Bar] = []
    for i in range(270):
        delta = math.sin(i * 0.05) * 0.5
        if i % 2 == 0:
            bars.append(_make_bar(i, 99.5, 101.5 + delta, 98.5 - delta, 101.0 + delta))
        else:
            bars.append(_make_bar(i, 100.5, 101.0 + delta, 98.0 - delta, 99.0 - delta))

    # Bar 270: Signal bar thoả mãn Module B Long
    # middle ~ 100.0, upper ~ 102.4, lower ~ 97.4, ATR ~ 2.9
    # low <= lower < close, close > open, %B <= 0.25
    bars.append(_make_bar(270, 97.5, 98.5, 96.8, 98.0))
    return bars


# ---------------------------------------------------------------------------
# Nhóm quy ước khớp lệnh (Test 1 - 5)
# ---------------------------------------------------------------------------

def test_sl_before_tp():
    """1. SL trước TP: dựng một bar sau khi vào lệnh chạm cả stop lẫn target -> exit_reason == 'SL'."""
    bars = _build_module_a_base_bars(270)
    # Bar 270: Signal bar
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    # Bar 271: Entry bar (trigger ~ 102.175)
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    # Bar 272: Bar sau khi vào lệnh chạm CẢ SL lẫn TP
    bars.append(_make_bar(272, 102.5, 115.0, 90.0, 100.0))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.exit_reason == "SL"


def test_gap_through_trigger():
    """2. Gap qua trigger: bar t+1 mở cửa trên trigger long -> entry_price == bar.open, không phải trigger."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    # Bar 271: Open tại 103.0 (trên trigger 102.175, nhưng dưới ngưỡng huỷ 103.925)
    bars.append(_make_bar(271, 103.0, 104.0, 102.5, 103.5))
    # Bar 272: Thoát lệnh bình thường bằng TP
    bars.append(_make_bar(272, 103.5, 120.0, 103.0, 115.0))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.entry_price == 103.0


def test_gap_through_stop():
    """3. Gap qua stop: bar mở cửa dưới stop long -> exit_price == bar.open, không phải stop."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    # Bar 272: Mở cửa tại 95.0 (dưới stop ~96.9)
    bars.append(_make_bar(272, 95.0, 95.5, 94.0, 94.5))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    trade = report.trades[0]
    assert trade.exit_reason == "SL"
    assert trade.exit_price == 95.0


def test_cancel_chasing_order():
    """4. Huỷ vì đuổi giá: bar t+1 mở cửa trên trigger + 0.50*ATR -> orders_cancelled == 1, không có lệnh."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    # Bar 271: Mở cửa tại 105.0 > trigger + 0.50*ATR (~103.925)
    bars.append(_make_bar(271, 105.0, 106.0, 104.0, 105.5))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 0
    assert report.orders_cancelled == 1


def test_expired_order():
    """5. Hết hạn: giá không chạm trigger trong hai bar -> orders_expired == 1, không có lệnh."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    # Hai bar tiếp theo giá không chạm trigger 102.175
    bars.append(_make_bar(271, 100.0, 101.0, 99.0, 100.5))
    bars.append(_make_bar(272, 100.0, 101.0, 99.0, 100.5))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 0
    assert report.orders_expired == 1


# ---------------------------------------------------------------------------
# Nhóm phí và khối lượng (Test 6 - 8)
# ---------------------------------------------------------------------------

def test_two_way_fees():
    """6. Phí hai chiều: trade.fees bằng đúng qty*entry*fee_rate + qty*exit*fee_rate."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars.append(_make_bar(272, 103.0, 120.0, 102.0, 115.0))

    fee_rate = BINGX_PERP_TAKER
    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=fee_rate,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    t = report.trades[0]
    expected_fees = t.qty * t.entry_price * fee_rate + t.qty * t.exit_price * fee_rate
    assert math.isclose(t.fees, expected_fees, rel_tol=1e-9)


def test_risk_sizing():
    """7. Sizing theo rủi ro: với capital=500, risk_fraction=0.005 -> qty khớp công thức §2.5."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars.append(_make_bar(272, 103.0, 120.0, 102.0, 115.0))

    capital = 500.0
    risk_frac = 0.005
    fee_rate = BINGX_PERP_TAKER

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        capital=capital,
        risk_fraction=risk_frac,
        fee_rate=fee_rate,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    t = report.trades[0]

    risk_budget = capital * risk_frac
    cost_per_unit = 2.0 * t.entry_price * fee_rate
    expected_qty = risk_budget / (t.r_value + cost_per_unit)
    assert math.isclose(t.qty, expected_qty, rel_tol=1e-9)


def test_leverage_cap_clipping():
    """8. Trần đòn bẩy cắt khối lượng: stop rất sát entry -> qty*entry == max_leverage * equity và clipped is True."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars.append(_make_bar(272, 103.0, 120.0, 102.0, 115.0))

    capital = 500.0
    max_lev = 0.05  # Giới hạn đòn bẩy nhỏ để kích hoạt clipping
    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        capital=capital,
        risk_fraction=0.005,
        max_leverage=max_lev,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    t = report.trades[0]
    assert t.clipped is True
    assert math.isclose(t.qty * t.entry_price, max_lev * capital, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Nhóm chống nhìn trước (Test 9)
# ---------------------------------------------------------------------------

def test_no_entry_at_signal_bar():
    """9. Không vào lệnh tại bar tín hiệu: entry_ts > signal_ts với mọi lệnh trong report.trades."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars.append(_make_bar(272, 103.0, 120.0, 102.0, 115.0))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) > 0
    for trade in report.trades:
        assert trade.entry_ts > trade.signal_ts


# ---------------------------------------------------------------------------
# Nhóm time stop (Test 10 - 11)
# ---------------------------------------------------------------------------

def test_time_stop_module_a():
    """10. Module A: giá đi ngang 24 bar sau khi vào -> exit_reason == 'TIME', bars_held == 24."""
    bars = _build_module_a_base_bars(270)
    bars.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))  # Entry bar
    # 24 bar đi ngang quanh 102.5 (stop ~ 96.9, target ~ 112.7)
    for i in range(272, 272 + 24):
        bars.append(_make_bar(i, 102.5, 103.0, 102.0, 102.5))

    report = run_perp_backtest(
        bars,
        "donchian_breakout",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    t = report.trades[0]
    assert t.exit_reason == "TIME"
    assert t.bars_held == 24


def test_time_stop_module_b():
    """11. Module B: giá đi ngang 12 bar sau khi vào -> exit_reason == 'TIME', bars_held == 12."""
    bars = _generate_valid_module_b_bars()
    # Bar 271: Entry bar (open = 98.0)
    bars.append(_make_bar(271, 98.0, 98.5, 97.5, 98.0))
    # 12 bar tiếp theo đi ngang quanh 98.0
    for i in range(272, 272 + 12):
        bars.append(_make_bar(i, 98.0, 98.3, 97.7, 98.0))

    report = run_perp_backtest(
        bars,
        "bollinger_mr",
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )
    assert len(report.trades) == 1
    t = report.trades[0]
    assert t.exit_reason == "TIME"
    assert t.bars_held == 12


# ---------------------------------------------------------------------------
# Nhóm bộ lọc (Test 12 - 17: mỗi test 2 khẳng định)
# ---------------------------------------------------------------------------

def test_filter_module_a_atr_ratio():
    """12. Module A bỏ tín hiệu khi ATR ratio >= 2.50.
    Hai khẳng định: trường hợp bình thường có lệnh, trường hợp ratio >= 2.50 không có lệnh.
    """
    # Khẳng định 1: Bình thường (ratio ~ 1.75 < 2.50) -> có lệnh
    bars_ok = _build_module_a_base_bars(270)
    bars_ok.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars_ok.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_ok.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_ok = run_perp_backtest(bars_ok, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: Sốc biến động cực lớn làm ATR ratio >= 2.50 -> không có lệnh
    bars_fail = _build_module_a_base_bars(270)
    bars_fail.append(_make_bar(270, 101.0, 160.0, 100.0, 155.0))
    bars_fail.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_fail.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_fail = run_perp_backtest(bars_fail, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0


def test_filter_module_a_bar_range():
    """13. Module A bỏ tín hiệu khi high - low > 2.0 * ATR14.
    Hai khẳng định: range hợp lệ có lệnh, range > 2.0*ATR không có lệnh.
    """
    # Khẳng định 1: range hợp lệ (range=5.0 <= 2.0 * 3.50=7.0) -> có lệnh
    bars_ok = _build_module_a_base_bars(270)
    bars_ok.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars_ok.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_ok.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_ok = run_perp_backtest(bars_ok, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: range > 2.0 * ATR14
    bars_fail = _build_module_a_base_bars(270)
    bars_fail.append(_make_bar(270, 101.0, 105.5, 97.0, 104.5))
    bars_fail.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_fail.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_fail = run_perp_backtest(bars_fail, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0


def test_filter_module_a_zero_range():
    """14. Module A bỏ tín hiệu khi high == low (CLV không hợp lệ).
    Hai khẳng định: range > 0 có lệnh, high == low không có lệnh.
    """
    # Khẳng định 1: range > 0 có lệnh
    bars_ok = _build_module_a_base_bars(270)
    bars_ok.append(_make_bar(270, 101.0, 105.0, 100.0, 104.5))
    bars_ok.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_ok.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_ok = run_perp_backtest(bars_ok, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: high == low tại bar tín hiệu -> bỏ tín hiệu
    bars_fail = _build_module_a_base_bars(270)
    bars_fail.append(_make_bar(270, 104.5, 104.5, 104.5, 104.5))
    bars_fail.append(_make_bar(271, 102.0, 103.0, 101.5, 102.5))
    bars_fail.append(_make_bar(272, 102.5, 120.0, 102.0, 115.0))
    rep_fail = run_perp_backtest(bars_fail, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0


def test_filter_module_b_adx():
    """15. Module B không phát tín hiệu khi ADX >= 20.
    Hai khẳng định: chuỗi phẳng ADX < 20 có lệnh, chuỗi trend ADX >= 20 không có lệnh.
    """
    # Khẳng định 1: ADX < 20 có lệnh
    bars_ok = _generate_valid_module_b_bars()
    bars_ok.append(_make_bar(271, 98.0, 98.5, 97.5, 98.0))
    bars_ok.append(_make_bar(272, 98.0, 102.0, 97.5, 101.0))
    rep_ok = run_perp_backtest(bars_ok, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: Xu hướng mạnh làm ADX >= 20 -> không phát tín hiệu
    bars_fail: list[Bar] = []
    for i in range(270):
        base = 50.0 + i * 0.5
        bars_fail.append(_make_bar(i, base, base + 1.0, base - 0.5, base + 0.8))
    bars_fail.append(_make_bar(270, 180.0, 181.0, 175.0, 178.0))
    bars_fail.append(_make_bar(271, 178.0, 179.0, 177.0, 178.0))
    rep_fail = run_perp_backtest(bars_fail, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0


def test_filter_module_b_r_max():
    """16. Module B bỏ lệnh khi R > 2.00 * ATR14.
    Hai khẳng định: R hợp lệ có lệnh, R > 2.0*ATR bỏ lệnh.
    """
    # Khẳng định 1: R hợp lệ -> có lệnh
    bars_ok = _generate_valid_module_b_bars()
    bars_ok.append(_make_bar(271, 98.0, 98.5, 97.5, 98.0))
    bars_ok.append(_make_bar(272, 98.0, 102.0, 97.5, 101.0))
    rep_ok = run_perp_backtest(bars_ok, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: low_t rất sâu làm R > 2.0 * ATR14 (ATR ~ 2.9 -> 2*ATR = 5.8)
    # Sửa bar 270 có low = 90.0 -> stop = 90.0 - 0.725 = 89.275 -> R = 98.0 - 89.275 = 8.725 > 5.8
    bars_fail = _generate_valid_module_b_bars()
    bars_fail[270] = _make_bar(270, 97.5, 98.5, 90.0, 98.0)
    bars_fail.append(_make_bar(271, 98.0, 98.5, 97.5, 98.0))
    bars_fail.append(_make_bar(272, 98.0, 102.0, 97.5, 101.0))
    rep_fail = run_perp_backtest(bars_fail, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0


def test_filter_module_b_distance_to_middle():
    """17. Module B bỏ lệnh khi khoảng cách tới đường giữa < 0.80R.
    Hai khẳng định: distance >= 0.80R có lệnh, distance < 0.80R bỏ lệnh.
    """
    # Khẳng định 1: distance >= 0.80R có lệnh
    bars_ok = _generate_valid_module_b_bars()
    bars_ok.append(_make_bar(271, 98.0, 98.5, 97.5, 98.0))
    bars_ok.append(_make_bar(272, 98.0, 102.0, 97.5, 101.0))
    rep_ok = run_perp_backtest(bars_ok, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_ok.trades) == 1

    # Khẳng định 2: entry quá gần middle (khoảng cách < 0.80R)
    # middle ~ 100.0. Cho bar 271 mở cửa tại 99.0 -> mid - entry = 1.0.
    # stop ~ 95.9 -> R = 99.0 - 95.9 = 3.1. 0.80 * R = 2.48 > 1.0 -> bỏ lệnh!
    bars_fail = _generate_valid_module_b_bars()
    bars_fail.append(_make_bar(271, 99.0, 99.5, 98.5, 99.0))
    bars_fail.append(_make_bar(272, 99.0, 102.0, 98.5, 101.0))
    rep_fail = run_perp_backtest(bars_fail, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0)
    assert len(rep_fail.trades) == 0
