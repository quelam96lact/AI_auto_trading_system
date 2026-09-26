"""Unit tests: MomentumRSIStrategy - RSI filter tren MomentumBreakoutStrategy.

RSI 14 (70/30) la "bo GIAM RUI RO" hon "bo TANG LOI NHUAN": muc tieu chinh
la giam MaxDD + tang win rate (tranh mua duoi/bán duoi vung cuc doan);
PnL tang nhe la he qua phu, khong phai muc tieu chinh (xem research
2026-08-09-derivative-risk-eod-verification.md).

Chuoi gia DA XAC NHAN qua compute_crossover() truc tiep (MomentumBreakoutStrategy
parent): overbought -> bull + RSI 100; oversold -> bear + RSI 0; mid-range ->
bull + RSI 66.15 (trong 30-70).
"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from trading.calendar_vn import TZ
from trading.derivative_backtest import run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy
from trading.strategies.momentum_rsi import MomentumRSIStrategy

SYM = "S"
START = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)


def _bars(closes: list[float], last: tuple[float, float]) -> list[Bar]:
    bars = [
        Bar(SYM, START + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate(closes)
    ]
    lc, lv = last
    bars.append(Bar(SYM, START + timedelta(minutes=5 * len(closes)), lc, lc, lc, lc, lv))
    return bars


def _sig(strategy, bars: list[Bar]) -> str | None:
    sig = None
    for b in bars:
        sig = strategy.compute_crossover(b)
    return sig


def _mk(**kw) -> MomentumRSIStrategy:
    base = {"qty": 1, "lookback": 5, "volume_multiplier": 2.0, "volume_period": 20, "atr_pct_threshold": 0.0}
    base.update(kw)
    return MomentumRSIStrategy(**base)


def test_bull_suppressed_when_rsi_overbought():
    # 20 bar tang lien tiep (RSI = 100, qua mua) + breakout len -> parent "bull",
    # RSI strategy chan (RSI 100 >= 70).
    bars = _bars([100 + i for i in range(20)], (125.0, 250))
    parent = MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0, volume_period=20)
    rsi = _mk()
    assert _sig(parent, bars) == "bull"  # san sang nhan tin hieu
    assert _sig(rsi, bars) is None  # RSI >= 70 -> chan


def test_bear_suppressed_when_rsi_oversold():
    # 20 bar giam lien tiep (RSI = 0, qua ban) + breakout xuong -> parent "bear",
    # RSI strategy chan (RSI 0 <= 30).
    bars = _bars([119 - i for i in range(20)], (95.0, 250))
    parent = MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0, volume_period=20)
    rsi = _mk()
    assert _sig(parent, bars) == "bear"
    assert _sig(rsi, bars) is None  # RSI <= 30 -> chan


def test_bull_passes_when_rsi_mid_range():
    # Dao dong 100/101 xen ke (RSI ~66, trong 30-70) + breakout len -> giu "bull".
    osc = [100.0 if i % 2 == 0 else 101.0 for i in range(20)]
    bars = _bars(osc, (106.0, 250))
    parent = MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0, volume_period=20)
    rsi = _mk()
    assert _sig(parent, bars) == "bull"
    assert _sig(rsi, bars) == "bull"  # RSI trung binh -> khong chan


def test_warmup_returns_none():
    # Chuoi ngan (chua du volume_period) -> None (warmup ke thua tu parent).
    bars = _bars([100.0, 101.0, 102.0, 103.0, 104.0], (110.0, 250))
    rsi = _mk()
    assert _sig(rsi, bars) is None


def test_chot_config_with_rsi_matches_spike_results():
    # Regression: cau hinh chot (EOD 14:20 keep 1.0, risk 2%/ngay + 2-loi,
    # fee 8,250, von 30tr) tren sample that 2 thang phai khop spike
    # scripts/.spike_rsi_combination_analysis.py: 18 lenh / 66.7% /
    # realized 19,081,500 (con so da chay that - neu lech, dung bao cao,
    # khong tu sua).
    # DERIV-FEE-1 (2026-08-14): realized gio tru ca phi MO (18 lenh x 8.250
    # = 148.500) -> 19.081.500 - 148.500 = 18.932.999,99... (spike cu thieu
    # phi mo — chinh la loii dang sua).
    sample = Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json")
    if not sample.exists():
        raise FileNotFoundError(f"thieu sample: {sample}")  # chi chay khi co data
    raw = json.loads(sample.read_text())
    bars = sorted(
        (
            Bar(
                row["symbol"],
                datetime.strptime(row["trading_date"], "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ),
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
    strat = MomentumRSIStrategy(
        qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001
    )
    risk = DerivativeRiskManager(capital=30_000_000, max_contracts=1)
    rep = run_derivative_backtest(
        bars, strat, risk, 30_000_000,
        intraday_close_time=time(14, 20), eod_keep_min_profit_points=1.0,
    )
    assert rep.trades == 18
    # Brief 95: 12/18 -> 11/18 do bieu phi moi (co thue TNCN, ~50.000d/vong thay vi
    # 16.500d). Lenh 7 (short 09/07 1993.0 -> 1992.6) lai gop +40.000d, phi 50.377,6d
    # -> rong -10.377,6d. So lenh van 18 (ngay 09/07 chi co 1 lenh, khong cham quy tac
    # 2 loi/ngay). Claude da tu chay lai, liet ke tung vong, xac nhan.
    assert rep.win_rate == pytest.approx(11 / 18, abs=0.001)
    # Lãi gộp trước phí của spike (19_081_500 đã trừ 18 x 8_250 phí đóng) = 19_230_000,
    # không phụ thuộc biểu phí. realized_pnl = lãi gộp - tổng phí của mọi lượt đã đóng.
    closed_fees = sum(f.fee for f in rep.fills[: 2 * rep.trades])
    assert rep.realized_pnl + closed_fees == pytest.approx(19_230_000.0, abs=1.0)

