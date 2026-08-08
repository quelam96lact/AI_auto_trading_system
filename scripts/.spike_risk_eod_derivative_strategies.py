"""Spike: kiem chung risk moi (2% + 2 lenh thua lien tiep) va EOD close (14:20)
tren du lieu that 2 thang, so sanh 4 cau hinh risk/exit.

Cau hinh:
1. Baseline: risk cu (3%, khong consecutive-loss halt), khong EOD close
   -> phai khop +20.25% / MaxDD 2.9% / 17 lenh (research doc 2026-08-08)
2. Risk moi (2% + 2-loss halt), khong EOD close
3. Risk cu, EOD close time(14, 20)
4. Risk moi + EOD close time(14, 20)

Entry co dinh: MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0,
volume_period=20, atr_pct_threshold=0.001) - tham so khuyen nghi da kiem chung.

Throwaway - output duoc chep nguyen van vao
docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md.
"""

import json
from datetime import datetime, time
from pathlib import Path

from trading.calendar_vn import TZ
from trading.derivative_backtest import run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy

sample_path = Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json")
raw = json.loads(sample_path.read_text())
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
CAP = 100_000_000


def run(risk_cfg: dict, eod: time | None):
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1, **risk_cfg)
    strat = MomentumBreakoutStrategy(
        qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001
    )
    rep = run_derivative_backtest(bars, strat, risk, CAP, intraday_close_time=eod)
    closes = [f for f in rep.fills if f.pnl is not None]
    wins = [f for f in closes if f.pnl > 0]
    eq = rep.ending_cash + rep.unrealized_pnl
    aw = sum(f.pnl for f in wins) / len(wins) if wins else 0.0
    return len(closes), rep.win_rate, aw, rep.realized_pnl, eq, rep.max_drawdown, risk.halted_date


OLD_RISK = {"max_daily_loss_pct": 0.03, "max_consecutive_losses": 999}  # 999 = tat streak halt
NEW_RISK = {"max_daily_loss_pct": 0.02, "max_consecutive_losses": 2}

configs = [
    ("1. Baseline (risk cu 3%, khong streak, khong EOD)", OLD_RISK, None),
    ("2. Risk moi (2% + 2-loss halt), khong EOD", NEW_RISK, None),
    ("3. Risk cu, EOD close 14:20", OLD_RISK, time(14, 20)),
    ("4. Risk moi + EOD close 14:20", NEW_RISK, time(14, 20)),
]

print("=" * 100)
print("SPIKE: risk moi (2% + 2 lenh thua lien tiep) x EOD close 14:20 - MomentumBreakout lb=5 atr=0.001")
print(f"Data: {len(bars)} bars 5m | {bars[0].ts:%Y-%m-%d} -> {bars[-1].ts:%Y-%m-%d} | von {CAP:,} | fee 8,250")
print("=" * 100)
print(f"{'Cau hinh':<42}{'Trd':>5}{'Win%':>7}{'avgW':>11}{'PnL':>14}{'Ret':>9}{'MaxDD':>8}{'halt':>6}")
for name, risk_cfg, eod in configs:
    n, wr, aw, pnl, eq, mdd, halted = run(risk_cfg, eod)
    print(f"{name:<42}{n:>5}{wr:>6.1%}{aw:>11,.0f}{pnl:>14,.0f}{(eq / CAP - 1):>+8.2%}{mdd:>7.1%}{halted!s:>6}")
