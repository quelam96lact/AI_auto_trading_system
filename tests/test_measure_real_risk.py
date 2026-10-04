"""Unit tests cho scripts/measure_real_risk.py (đo rủi ro thực sau bước 0).

Kiểm chứng:
1. Gộp fill thành vòng giao dịch: pnl, phí, kích thước, thời gian giữ; mua thêm vẫn là một vòng.
2. Fill SELL qty = 0 (chưa settle) bị bỏ qua; vị thế chưa đóng được đếm riêng.
3. Hồ sơ vị thế: số vị thế mở đồng thời và tổng giá trị / vốn theo từng bar.
4. Báo cáo đếm đúng số vòng lỗ nặng hơn risk_pct và không chia cho 0 khi không có vòng nào.
5. Chạy xuyên suốt với run_backtest thật trên dữ liệu giả lập.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import measure_real_risk as m

from trading.backtest import run_backtest
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategy import Signal
from trading.trailing_stop import TrailingStopManager

CAPITAL = 100_000_000.0
T0 = datetime(2026, 1, 5, 9, 0, tzinfo=TZ)


def _fill(sym, side, qty, price, fee, minutes, pnl=None):
    return Fill(sym, side, qty, price, fee, T0 + timedelta(minutes=minutes), pnl)


def test_round_trip_aggregates_buys_and_sells():
    fills = [
        _fill("HPG", "BUY", 1000, 20_000.0, 50_000.0, 0),
        _fill("HPG", "BUY", 500, 20_200.0, 25_000.0, 5),  # mua thêm: vẫn một vòng
        _fill("HPG", "SELL", 1500, 19_500.0, 100_000.0, 1_440, pnl=-1_000_000.0),
    ]
    trips, still_open = m.round_trips(fills, CAPITAL)
    assert still_open == 0 and len(trips) == 1
    t = trips[0]
    assert t["entry_value"] == 1000 * 20_000.0 + 500 * 20_200.0
    assert t["pnl"] == -1_000_000.0
    assert t["pnl_pct_capital"] == -0.01
    assert t["fees"] == 175_000.0
    assert t["hold_days"] == 1.0
    assert abs(t["entry_pct_capital"] - 0.301) < 1e-9


def test_zero_qty_sell_ignored_and_open_position_counted():
    fills = [
        _fill("HPG", "BUY", 100, 20_000.0, 5_000.0, 0),
        _fill("HPG", "SELL", 0, 19_000.0, 0.0, 10),  # stop chạm nhưng chưa settle
        _fill("IJC", "BUY", 100, 10_000.0, 2_500.0, 20),
        _fill("IJC", "SELL", 100, 10_500.0, 3_000.0, 30, pnl=40_000.0),
    ]
    trips, still_open = m.round_trips(fills, CAPITAL)
    assert [t["symbol"] for t in trips] == ["IJC"]
    assert still_open == 1  # HPG vẫn mở


def _bar(sym, minutes, close):
    return Bar(sym, T0 + timedelta(minutes=minutes), close, close, close, close, 1_000_000)


def test_exposure_profile_tracks_concurrent_positions():
    fills = [
        _fill("HPG", "BUY", 1000, 20_000.0, 0.0, 0),  # 20% vốn
        _fill("IJC", "BUY", 2000, 10_000.0, 0.0, 5),  # +20% vốn
        _fill("HPG", "SELL", 1000, 20_000.0, 0.0, 10, pnl=0.0),
    ]
    bars = [
        _bar("HPG", 0, 20_000.0),
        _bar("IJC", 5, 10_000.0),
        _bar("HPG", 10, 20_000.0),
    ]
    p = m.exposure_profile(fills, bars, CAPITAL)
    assert p["max_positions"] == 2
    assert abs(p["max_exposure"] - 0.4) < 1e-9


def test_report_counts_breaches_and_handles_empty():
    assert "không có vòng giao dịch nào" in m.format_report([], 0, {}, 0.0)
    trips = [
        {"pnl_pct_capital": -0.02, "pnl_pct_entry": -0.10, "fee_pct_entry": 0.007,
         "entry_pct_capital": 0.2, "hold_days": 3.0, "pnl": -2_000_000.0,
         "fees": 140_000.0, "fees_pct_capital": 0.0014},
        {"pnl_pct_capital": -0.004, "pnl_pct_entry": -0.02, "fee_pct_entry": 0.007,
         "entry_pct_capital": 0.2, "hold_days": 4.0, "pnl": -400_000.0,
         "fees": 140_000.0, "fees_pct_capital": 0.0014},
        {"pnl_pct_capital": 0.01, "pnl_pct_entry": 0.05, "fee_pct_entry": 0.007,
         "entry_pct_capital": 0.2, "hold_days": 5.0, "pnl": 1_000_000.0,
         "fees": 140_000.0, "fees_pct_capital": 0.0014},
    ]
    exp = {"max_positions": 3, "max_exposure": 0.6, "share_bars_over_40pct": 0.25}
    text = m.format_report(trips, 0, exp, 0.08)
    assert "Vòng lỗ nặng hơn 1% vốn: 1/3" in text
    assert "tối đa: 60%" not in text and "tối đa 60%" in text


class _BuyOnceStrategy:
    warmup_bars = 0

    def __init__(self):
        self._n = 0

    def compute_crossover(self, bar):
        return None

    def on_bar(self, bar, context):
        self._n += 1
        return Signal(bar.symbol, "BUY", 100) if self._n == 2 else None

    def last_crossover(self, symbol):
        return None

    def last_atr(self, symbol):
        return 20.0  # 0,1% giá -> trailing stop rất sát


def test_end_to_end_with_real_backtest():
    price = 20_000.0
    bars = []
    for i in range(6):
        price *= 0.99  # giá giảm đều -> stop sẽ chạm
        bars.append(Bar("HPG", T0 + timedelta(minutes=5 * i), price, price, price, price, 1_000_000))
    report = run_backtest(
        bars, _BuyOnceStrategy(), RiskManager(capital=CAPITAL), TrailingStopManager(), CAPITAL
    )
    trips, still_open = m.round_trips(report.fills, CAPITAL)
    p = m.exposure_profile(report.fills, bars, CAPITAL)
    assert len(trips) + still_open == 1
    assert p["max_positions"] == 1
    assert 0 < p["max_exposure"] <= 0.2 + 1e-9


def _trip(pnl, fees, capital=CAPITAL):
    return {
        "pnl": pnl, "fees": fees, "pnl_pct_capital": pnl / capital,
        "fees_pct_capital": fees / capital, "pnl_pct_entry": 0.0,
        "fee_pct_entry": 0.0, "entry_pct_capital": 0.2, "hold_days": 3.0,
    }


def test_totals_net_fees_and_gross():
    trips = [_trip(-1_000_000.0, 100_000.0), _trip(500_000.0, 100_000.0)]
    text = "\n".join(m._totals_lines(trips))
    assert "Tổng lãi/lỗ ròng: -500,000 đồng (-0.50% vốn)" in text
    assert "Tổng phí+thuế: 200,000 đồng (0.20% vốn)" in text
    # gộp = ròng + phí = -500.000 + 200.000
    assert "Lãi/lỗ gộp trước phí+thuế (sau trượt giá): -300,000 đồng (-0.30% vốn)" in text


def test_mean_and_standard_error_flag_noise_vs_signal():
    noisy = [_trip(x, 0.0) for x in (-1_000_000.0, 900_000.0, -800_000.0, 1_000_000.0)]
    assert "CHƯA phân biệt được với 0" in "\n".join(m._totals_lines(noisy))
    clear = [_trip(x, 0.0) for x in (500_000.0, 520_000.0, 480_000.0, 510_000.0)]
    assert "PHÂN BIỆT được với 0" in "\n".join(m._totals_lines(clear))


def test_totals_single_trip_has_no_standard_error():
    text = "\n".join(m._totals_lines([_trip(-250_000.0, 50_000.0)]))
    assert "n = 1, không có sai số chuẩn" in text


def test_round_trips_store_fees_pct_capital():
    fills = [
        _fill("HPG", "BUY", 1000, 20_000.0, 50_000.0, 0),
        _fill("HPG", "SELL", 1000, 20_500.0, 70_000.0, 60, pnl=380_000.0),
    ]
    trips, _ = m.round_trips(fills, CAPITAL)
    assert trips[0]["fees_pct_capital"] == 120_000.0 / CAPITAL


def _falling_bars():
    price = 20_000.0
    bars = []
    for i in range(6):
        price *= 0.99
        bars.append(Bar("HPG", T0 + timedelta(minutes=5 * i), price, price, price, price, 1_000_000))
    return bars


def test_fee_rate_flows_into_backtest_fills():
    from trading.paper_broker import FEE_RATE

    default = m.run_report(_falling_bars(), _BuyOnceStrategy(), CAPITAL)
    lower = m.run_report(_falling_bars(), _BuyOnceStrategy(), CAPITAL, fee_rate=0.0015)
    buy_default = next(f for f in default.fills if f.side == "BUY")
    buy_lower = next(f for f in lower.fills if f.side == "BUY")
    # Cùng giá khớp và qty, chỉ phí mua khác nhau đúng theo tỷ lệ phí.
    assert buy_default.price == buy_lower.price and buy_default.qty == buy_lower.qty
    assert abs(buy_lower.fee / buy_default.fee - 0.0015 / FEE_RATE) < 1e-9


def test_fee_rate_none_keeps_default_behavior():
    a = m.run_report(_falling_bars(), _BuyOnceStrategy(), CAPITAL)
    b = m.run_report(_falling_bars(), _BuyOnceStrategy(), CAPITAL, fee_rate=None)
    assert [f.fee for f in a.fills] == [f.fee for f in b.fills]


def test_validate_fee_rate_rejects_percent_typo():
    assert m.validate_fee_rate(None) is None
    assert m.validate_fee_rate(0.0015) == 0.0015
    for bad in (0.15, 1.0, -0.001):
        try:
            m.validate_fee_rate(bad)
        except SystemExit as e:
            assert "0.0015" in str(e)
        else:
            raise AssertionError(f"không chặn --fee-rate {bad}")
