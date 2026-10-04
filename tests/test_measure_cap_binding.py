"""Unit tests cho scripts/measure_cap_binding.py (bước 0, GARCH).

Kiểm chứng:
1. ATR nhỏ (qty_atr lớn) -> trần 20% chặn: cap_binds, qty có trần < không trần.
2. ATR lớn (qty_atr nhỏ) -> trần không chặn: not_binding, qty bằng nhau.
3. ATR không hợp lệ -> rejected_other.
4. Script KHÔNG đổi quyết định của RiskManager gốc (qty trả về bằng RiskManager thường).
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from measure_cap_binding import CapProbeRiskManager, format_report, measure_cap_binding

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategy import Signal

CAPITAL = 100_000_000.0
TODAY = date(2026, 1, 5)


def test_cap_binds_when_atr_small():
    r = CapProbeRiskManager(capital=CAPITAL)
    # qty_atr = 1% * 100tr / (10 * 2) = 50.000 cp; qty_cap = 20% * 100tr / 10.000 = 2.000 cp
    out = r.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, 10.0, {}, 0.0, TODAY)
    assert out is not None and out.qty == 2_000
    assert r.records[0]["category"] == "cap_binds"
    assert r.records[0]["qty_capped"] == 2_000
    assert r.records[0]["qty_uncapped"] == 50_000


def test_not_binding_when_atr_large():
    r = CapProbeRiskManager(capital=CAPITAL)
    # qty_atr = 1tr / (1.000 * 2) = 500 cp < qty_cap 2.000 cp
    out = r.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, 1_000.0, {}, 0.0, TODAY)
    assert out is not None and out.qty == 500
    assert r.records[0]["category"] == "not_binding"
    assert r.records[0]["qty_uncapped"] == 500


def test_invalid_atr_is_rejected_other():
    r = CapProbeRiskManager(capital=CAPITAL)
    assert r.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, None, {}, 0.0, TODAY) is None
    assert r.records[0]["category"] == "rejected_other"


def test_probe_matches_plain_risk_manager():
    probe = CapProbeRiskManager(capital=CAPITAL)
    plain = RiskManager(capital=CAPITAL)
    for atr in (5.0, 100.0, 1_000.0, 5_000.0):
        a = probe.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, atr, {}, 0.0, TODAY)
        b = plain.approve_sized(Signal("HPG", "BUY", 100), 10_000.0, atr, {}, 0.0, TODAY)
        assert a == b


def test_sell_is_not_recorded():
    r = CapProbeRiskManager(capital=CAPITAL)
    r.approve_sized(Signal("HPG", "SELL", 100), 10_000.0, 10.0, {}, 0.0, TODAY)
    assert r.records == []


class _BuyOnceStrategy:
    """Mua đúng 1 lần ở bar thứ 3, ATR cố định — chỉ để đi qua run_backtest."""

    warmup_bars = 0

    def __init__(self, atr: float):
        self._atr = atr
        self._n = 0

    def compute_crossover(self, bar):
        return None

    def on_bar(self, bar, context):
        self._n += 1
        return Signal(bar.symbol, "BUY", 100) if self._n == 3 else None

    def last_crossover(self, symbol):
        return None

    def last_atr(self, symbol):
        return self._atr


def _bars(symbol: str, n: int = 6, price: float = 10_000.0) -> list[Bar]:
    t0 = datetime(2026, 1, 5, 9, 0, tzinfo=TZ)
    return [
        Bar(symbol, t0 + timedelta(minutes=5 * i), price, price, price, price, 1_000_000)
        for i in range(n)
    ]


def test_measure_cap_binding_end_to_end_and_report():
    result = measure_cap_binding(
        {"HPG": _bars("HPG")}, lambda: _BuyOnceStrategy(atr=10.0), CAPITAL
    )
    assert result["HPG"]["total"] == 1
    assert result["HPG"]["cap_binds"] == 1
    assert "100%" in format_report(result)
