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
         "entry_pct_capital": 0.2, "hold_days": 3.0},
        {"pnl_pct_capital": -0.004, "pnl_pct_entry": -0.02, "fee_pct_entry": 0.007,
         "entry_pct_capital": 0.2, "hold_days": 4.0},
        {"pnl_pct_capital": 0.01, "pnl_pct_entry": 0.05, "fee_pct_entry": 0.007,
         "entry_pct_capital": 0.2, "hold_days": 5.0},
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
