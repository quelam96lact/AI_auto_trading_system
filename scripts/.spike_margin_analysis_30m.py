"""Spike: phan tich margin giao dich phai sinh VN30F voi von 30,000,000.

Tinh: (A) yeu cau ky quy theo gia (base 17%, D+ 3% intraday / 6% qua dem),
(B) backtest chien luoc Momentum lb=5+ATR 0.001 voi von 30tr vs 100tr
(nguong lo ngay 2% doi 600k vs 2tr -> halt co the kich hoat),
(C) uoc tinh chi phi D+ qua dem 0.0487%/ngay cho cac lenh giu qua dem
(gia dinh: lai tinh tren phan SSI tai tro = gia tri HD x (1 - 6%), can
kiem tra lai bieu phi SSI).

Throwaway - khong commit.
"""

import json
from datetime import datetime, time
from pathlib import Path

from trading.calendar_vn import TZ
from trading.derivative_backtest import run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy

raw = json.loads(Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json").read_text())
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

CAP30 = 30_000_000
CAP100 = 100_000_000
D_RATE = 0.000487  # 0.0487%/ngay lai D+ qua dem
D_OVER_MARGIN = 0.06  # ky quy D+ qua dem 6%

print("=" * 92)
print("A) YEU CAU KY QUY 1 HOP DONG VN30F (gia tri = gia x 100,000)")
print("=" * 92)
print(f"{'Gia VN30F':>10}{'Gia tri':>12}{'Base 17%':>12}{'D+ intra 3%':>13}{'D+ qua dem 6%':>14}")
for px in (1796.3, 1900.0, 2022.8):
    v = px * 100_000
    print(
        f"{px:>10.1f}{v/1e6:>10.1f}tr{v*0.17/1e6:>10.2f}tr{v*0.03/1e6:>11.2f}tr{v*0.06/1e6:>12.2f}tr"
    )
print()
print(f"Von 30tr chi du base 17% khi gia <= {CAP30/(0.17*100_000):.0f} diem")
print(f"  (voi dem 1.25x: <= {CAP30/(0.17*1.25*100_000):.0f} diem; 1.5x: <= {CAP30/(0.17*1.5*100_000):.0f})")
print(f"Von 30tr du D+ qua dem 6% toi gia <= {CAP30/(0.06*100_000):.0f} diem (dem 1.25x: {CAP30/(0.06*1.25*100_000):.0f})")
print("  -> trong sample (1796-2022), base 17% KHONG du voi 30tr; chi kha thi qua D+ (3%/6%)")
print()

print("=" * 92)
print("B) BACKTEST 100tr vs 30tr - sau fix daily-theo-ngay + nguong giu lai 1.0 diem")
print("=" * 92)
print(f"{'Config':<36}{'Trd':>5}{'Win%':>7}{'PnL':>13}{'Ret':>9}{'MaxDD':>8}{'halt':>11}{'O/N dem':>8}")


def run_cfg(cap: int, eod: time | None, keep_min: float = 0.0):
    risk = DerivativeRiskManager(capital=cap, max_contracts=1)
    strat = MomentumBreakoutStrategy(
        qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001
    )
    rep = run_derivative_backtest(
        bars, strat, risk, cap, intraday_close_time=eod, eod_keep_min_profit_points=keep_min
    )
    closes = [f for f in rep.fills if f.pnl is not None]
    opens = [f for f in rep.fills if f.pnl is None]
    wins = [f for f in closes if f.pnl > 0]
    eq = rep.ending_cash + rep.unrealized_pnl
    wr = len(wins) / len(closes) if closes else 0.0
    overnight_days = sum(
        (c.ts.date() - o.ts.date()).days for o, c in zip(opens, closes + [None]) if c
    )
    return len(closes), wr, rep.realized_pnl, eq, rep.max_drawdown, risk.halted_date, overnight_days


for cap, cap_name in ((CAP100, "100tr"), (CAP30, "30tr")):
    for eod_name, eod, keep in (
        ("khong EOD", None, 0.0),
        ("EOD 14:20 nguong 0.0", time(14, 20), 0.0),
        ("EOD 14:20 nguong 1.0", time(14, 20), 1.0),
    ):
        n, wr, pnl, eq, mdd, halted, on_days = run_cfg(cap, eod, keep)
        print(
            f"{cap_name + ' ' + eod_name:<36}{n:>5}{wr:>6.1%}{pnl:>13,.0f}"
            f"{(eq - cap) / cap:>+8.2%}{mdd:>7.1%}{halted!s:>11}{on_days:>8}"
        )
print()

print("=" * 92)
print("C) CHI PHI D+ QUA DEM (0.0487%/ngay tren phan tai tro = gia tri x 94%) - EOD giu lai, von 30tr")
print("=" * 92)
risk = DerivativeRiskManager(capital=CAP30, max_contracts=1)
strat = MomentumBreakoutStrategy(
    qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001
)
rep = run_derivative_backtest(bars, strat, risk, CAP30, intraday_close_time=time(14, 20))
opens = [f for f in rep.fills if f.pnl is None]
closes = [f for f in rep.fills if f.pnl is not None]
total_interest = 0.0
rows = []
for o, c in zip(opens, closes + [None]):
    if not c:
        continue
    days = (c.ts.date() - o.ts.date()).days
    if days <= 0:
        continue
    financed = o.price * 100_000 * (1 - D_OVER_MARGIN)
    interest = D_RATE * financed * days
    total_interest += interest
    rows.append((o.ts.date(), o.side, o.price, c.price, c.pnl, days, interest))
print(f"  So lenh giu qua dem: {len(rows)}/{len(closes)} round-trip")
print(f"  Tong phi D+ qua dem uoc tinh: {total_interest:,.0f} VND (tren {len(bars)} bars, 2 thang)")
print(f"  Phi D+ trung binh/lenh qua dem: {total_interest/len(rows) if rows else 0:,.0f} VND")
print(f"  So sanh: tong phi giao dich (fee 8,250 x 2 x {len(closes)} lenh) = {8_250*2*len(closes):,.0f} VND")
print("  (Gia dinh: lai tinh tren phan SSI tai tro; CAN KIEM TRA LAI BIEU PHI SSI)")
if rows:
    print("  5 lenh giu qua dem lon nhat (phi D+):")
    for d, side, op, cp, pnl, days, interest in sorted(rows, key=lambda r: -r[6])[:5]:
        print(
            f"    {d} {('LONG' if side=='BUY' else 'SHORT'):>5} {op:>7.1f}->{cp:>7.1f} "
            f"pnl={pnl:>+11,.0f} {days:>3} dem phiD+={interest:>9,.0f}"
        )
