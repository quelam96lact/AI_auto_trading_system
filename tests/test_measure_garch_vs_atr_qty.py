"""Unit tests cho scripts/measure_garch_vs_atr_qty.py (bước 2, GARCH).

Kiểm chứng:
1. qty ATR và qty GARCH đều do RiskManager.approve_sized tính (không công thức riêng):
   sigma = 2%, giá 10.000 -> atr quy đổi 200 -> qty = 1% vốn / (200 * 2) = 2.500 cp
   (trần 20% vốn = 2.000 cp -> qty thực 2.000).
2. Tín hiệu thiếu ATR hoặc thiếu dự báo GARCH bị bỏ qua có lý do, không đoán.
3. Báo cáo kết luận đúng theo ngưỡng 15% trên qty THỰC (sau trần).
4. SignalProbeRiskManager ghi đủ ngữ cảnh BUY và không đổi quyết định của RiskManager.
"""

import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import measure_garch_vs_atr_qty as m

from trading.calendar_vn import TZ, is_trading_day
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategy import Signal

CAPITAL = 100_000_000.0
D = date(2026, 1, 5)


def _call(atr, price=10_000.0, symbol="HPG"):
    return {"symbol": symbol, "today": D, "price": price, "atr": atr}


def test_compare_sizing_uses_risk_manager_for_both_quantities():
    with patch.object(m, "sigma_asof", return_value=0.02):
        rows = m.compare_sizing([_call(atr=200.0)], {"HPG": []}, set(), CAPITAL, 500)
    r = rows[0]
    assert r["skipped"] is None
    # ATR 200 (2%) và GARCH sigma 2% -> cùng qty thô 2.500, sau trần 20% = 2.000.
    assert r["qty_atr_raw"] == r["qty_garch_raw"] == 2_500
    assert r["qty_atr_eff"] == r["qty_garch_eff"] == 2_000


def test_compare_sizing_skips_missing_inputs_with_reason():
    with patch.object(m, "sigma_asof", return_value=None):
        rows = m.compare_sizing(
            [_call(atr=None), _call(atr=200.0)], {"HPG": []}, set(), CAPITAL, 500
        )
    assert rows[0]["skipped"] == "thiếu ATR"
    assert rows[1]["skipped"] == "thiếu dự báo GARCH"


def test_report_conclusion_follows_threshold_on_effective_qty():
    # Qty thô lệch (ATR 1% -> 5.000 cp, GARCH 2% -> 2.500 cp) nhưng cùng chạm trần 2.000 cp
    # -> lệch thực = 0.
    with patch.object(m, "sigma_asof", return_value=0.02):
        rows = m.compare_sizing([_call(atr=100.0)], {"HPG": []}, set(), CAPITAL, 500)
    text = m.format_report(rows, {"HPG": (900, 880)})
    assert "dừng hướng này" in text

    # GARCH 8% -> qty thô 625, làm tròn xuống bội 100 = 600 cp so với 2.000 cp (sau trần)
    # theo ATR 1% -> lệch 70%.
    with patch.object(m, "sigma_asof", return_value=0.08):
        rows = m.compare_sizing([_call(atr=100.0)], {"HPG": []}, set(), CAPITAL, 500)
    assert "đáng bàn bước tiếp" in m.format_report(rows, {"HPG": (900, 880)})


def test_report_without_usable_signals_does_not_conclude():
    with patch.object(m, "sigma_asof", return_value=None):
        rows = m.compare_sizing([_call(atr=200.0)], {"HPG": []}, set(), CAPITAL, 500)
    assert "không có tín hiệu nào đủ dữ liệu" in m.format_report(rows, {})


def test_probe_records_buy_context_and_matches_plain_risk_manager():
    probe = m.SignalProbeRiskManager(capital=CAPITAL)
    plain = RiskManager(capital=CAPITAL)
    a = probe.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, 200.0, {}, 0.0, D)
    b = plain.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, 200.0, {}, 0.0, D)
    probe.approve_sized(Signal("HPG", "SELL", 100), 10_000.0, 200.0, {}, 0.0, D)
    assert a == b
    assert probe.calls == [{"symbol": "HPG", "today": D, "price": 10_000.0, "atr": 200.0}]


class _BuyAtBarStrategy:
    """Mua đúng 1 lần ở bar thứ `at`, ATR cố định — chỉ để đi qua run_backtest."""

    warmup_bars = 0

    def __init__(self, at: int, atr: float):
        self._at, self._atr, self._n = at, atr, 0

    def compute_crossover(self, bar):
        return None

    def on_bar(self, bar, context):
        self._n += 1
        return Signal(bar.symbol, "BUY", 100) if self._n == self._at else None

    def last_crossover(self, symbol):
        return None

    def last_atr(self, symbol):
        return self._atr


def _daily_bars(symbol: str, n: int, seed: int = 3) -> list[Bar]:
    rng = np.random.default_rng(seed)
    bars, price, d = [], 20_000.0, date(2022, 1, 3)
    while len(bars) < n:
        if is_trading_day(d):
            price *= math.exp(rng.standard_t(8) * 0.015)
            ts = datetime(d.year, d.month, d.day, tzinfo=TZ)
            bars.append(Bar(symbol, ts, price, price, price, price, 1_000_000))
        d += timedelta(days=1)
    return bars


def test_run_measurement_end_to_end():
    bars = {"HPG": _daily_bars("HPG", 620)}
    rows, depth = m.run_measurement(
        bars, lambda: _BuyAtBarStrategy(at=600, atr=300.0), set(), CAPITAL, 500
    )
    assert len(rows) == 1 and rows[0]["skipped"] is None
    assert 0.005 < rows[0]["sigma"] < 0.04
    assert rows[0]["qty_garch_eff"] > 0
    assert depth["HPG"] == (620, 619)
    assert "Tín hiệu: 1, dùng được: 1" in m.format_report(rows, depth)


def test_calibrated_deviation_removes_level_shift():
    # GARCH luôn cho qty gấp 1,5 lần ATR (chênh mức thuần) -> sau hiệu chỉnh lệch = 0.
    rows = [
        {"skipped": None, "qty_atr_raw": 1000, "qty_garch_raw": 1500},
        {"skipped": None, "qty_atr_raw": 2000, "qty_garch_raw": 3000},
        {"skipped": None, "qty_atr_raw": 800, "qty_garch_raw": 1200},
    ]
    assert m._calibrated_deviations(rows, "raw") == [0.0, 0.0, 0.0]
    # Một tín hiệu lệch hình dạng (gấp 3 thay vì 1,5) -> lệch 100% so với trung vị 1,5.
    rows.append({"skipped": None, "qty_atr_raw": 1000, "qty_garch_raw": 3000})
    assert max(m._calibrated_deviations(rows, "raw")) == 1.0
