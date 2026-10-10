"""Kiem bon luat giao dich DA CO tren rieng ma VCB, so voi mua-va-giu VCB — Brief dot 181.

DANG KY TRUOC (chot trong brief, KHONG doi sau khi thay so):
- Nguon: chi VCB, `bars_daily`, doc qua `read_bars` cua `screen_pullback_trend` (cong niem
  phong chay TRUOC: nen >= 2023-01-01 thi NEM LOI). Cua so 2016-01-01 -> truoc 2023-01-01.
- Bon luat, KHONG sua code nao, KHONG doi tham so nao:
  1. octopus_pullback  : `trading.backtest.STRATEGIES["octopus_pullback"]` + `run_backtest`
                         (RiskManager(capital=1e9) + TrailingStopManager, giong
                         `scripts/measure_strategy.py::measure_one`);
  2. pullback trong xu huong : `screen_pullback_trend.simulate_symbol`;
  3. pha dinh Donchian 55/20 : `screen_donchian_breakout.simulate_symbol`;
  4. RSI(2) qua ban tren MA200 : `screen_rsi2_reversion.simulate_symbol`.
  Luat 2-4 goi qua import, dung nguyen IS_START/IS_END mac dinh cua tung script (loc theo
  NGAY TIN HIEU), nen 2016-2022 truyen vao de lam nong.
- Moc mua-va-giu VCB (luat 2-4): mua OPEN phien dau >= 2017-01-01, ban CLOSE phien cuoi
  <= 2022-12-31, tinh bang `trading.stock_study.net_return`. Luat 1 so voi
  `report.buy_and_hold_pnl` do `run_backtest` tu tinh.
- Cong "dang do tiep" (luat 2-4): n >= 20 VA lai rong trung binh/lanh > 0 VA PF > 1,2 VA
  loi suat gop > mua-va-giu VCB VA p < 0,0125 (0,05/4 luat, Bonferroni).
  Luat 1: so fill SELL >= 20 VA PnL > 0 VA PnL > buy_and_hold_pnl.
- BA CANH BAO (brief §0, khong duoc bo):
  (1) chon ma sau khi luat da truot tren toan thi truong la kieu cau ca kinh dien;
  (2) mau nho: mot ma trong 6 nam chi vai chuc lenh, cong >= 300 lenh cua spec KHONG the dat
      => dot nay khong the dua luat nao toi von that;
  (3) chu du an dang gi 1.500 VCB ngoai he thong (dot 150) — phep do nay KHONG khuyen nghi
      gi ve so co phieu do.
- Chi doc. KHONG commit, KHONG push, KHONG ghi DB, KHONG goi API dat lenh.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Console/redirect tren Windows mac dinh cp1252 -> print tieng Viet nem UnicodeEncodeError
# SAU KHI da do xong. Doi sang utf-8 truoc khi in bat cu thu gi.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_donchian_breakout import IS_END as DONCHIAN_IS_END
from scripts.screen_donchian_breakout import IS_START as DONCHIAN_IS_START
from scripts.screen_donchian_breakout import simulate_symbol as donchian_sim
from scripts.screen_pullback_trend import IS_END as PULLBACK_IS_END
from scripts.screen_pullback_trend import IS_START as PULLBACK_IS_START
from scripts.screen_pullback_trend import read_bars
from scripts.screen_pullback_trend import simulate_symbol as pullback_sim
from scripts.screen_rsi2_reversion import IS_END as RSI2_IS_END
from scripts.screen_rsi2_reversion import IS_START as RSI2_IS_START
from scripts.screen_rsi2_reversion import simulate_symbol as rsi2_sim
from trading.backtest import STRATEGIES, run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.stock_study import bar_date, load_universe, net_return
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

SYMBOL = "VCB"
CAPITAL = 1_000_000_000.0
DEFAULT_FROM = datetime(2016, 1, 1, tzinfo=TZ)
DEFAULT_TO = datetime(2023, 1, 1, tzinfo=TZ)  # read_daily_bars dung `ts < end`
BH_START = date(2017, 1, 1)
BH_END = date(2022, 12, 31)

N_MIN = 20
PF_MIN = 1.2
P_MAX = 0.0125  # 0,05 / 4 luat (Bonferroni), brief §1.3
N_BOOT = 2000
BOOT_SEED = 42

LAW_OCTOPUS = "octopus_pullback"
LAW_PULLBACK = "pullback"
LAW_DONCHIAN = "donchian"
LAW_RSI2 = "rsi2"

# Nhan + cua so IS cua tung luat (lay NGUYEN tu script goc, khong khai lai so).
LAW_SPECS: dict[str, dict[str, Any]] = {
    LAW_PULLBACK: {
        "label": "Pullback trong xu huong",
        "is_start": PULLBACK_IS_START,
        "is_end": PULLBACK_IS_END,
    },
    LAW_DONCHIAN: {
        "label": "Pha dinh Donchian 55/20",
        "is_start": DONCHIAN_IS_START,
        "is_end": DONCHIAN_IS_END,
    },
    LAW_RSI2: {
        "label": "RSI(2) qua ban tren MA200",
        "is_start": RSI2_IS_START,
        "is_end": RSI2_IS_END,
    },
}

WARNINGS = (
    "(1) Chon ma SAU KHI luat da truot tren toan thi truong la kieu cau ca kinh dien: voi ~1.200 ma,",
    "    chac chan co vai ma ma luat 'thang' do may. VCB duoc chon vi chu du an hoi, KHONG phai vi du lieu.",
    "(2) Mau nho: mot ma trong 6 nam chi vai chuc lenh; cong >= 300 lenh cua spec KHONG the dat.",
    "    Dot nay KHONG the dua luat nao toi von that. Ket qua tot nhat co the la 'dang do tiep tren",
    "    nhom ngan hang', va do se la mot brief khac.",
    "(3) Chu du an dang gi 1.500 VCB ngoai he thong (dot 150). Phep do nay KHONG khuyen nghi gi ve so",
    "    co phieu do.",
)


def load_vcb_bars(
    storage: Any,
    read_from: datetime = DEFAULT_FROM,
    read_to: datetime = DEFAULT_TO,
) -> tuple[list[Bar], int]:
    """Doc nen VCB qua `read_bars` cua screen_pullback_trend (cong niem phong chay TRUOC)."""
    return read_bars(storage, SYMBOL, read_from, read_to)


def law_trades(bars: list[Bar], law: str, exchange: str | None) -> list[dict]:
    """Goi DUNG `simulate_symbol` cua tung luat, khong truyen tham so nao khac mac dinh."""
    if law == LAW_PULLBACK:
        return pullback_sim(bars, exchange, SYMBOL)
    if law == LAW_DONCHIAN:
        return donchian_sim(bars, exchange, SYMBOL)
    if law == LAW_RSI2:
        return rsi2_sim(bars, SYMBOL, exchange)
    raise ValueError(f"luat khong ho tro: {law}")


def gross_return(nets: list[float]) -> float:
    """Loi suat gop khi mot vi the tai mot thoi diem, tien nhan roi lai 0: PI(1+net_i) - 1."""
    equity = 1.0
    for n in nets:
        equity *= 1.0 + n
    return equity - 1.0


def max_drawdown_by_trade(nets: list[float]) -> float:
    """Drawdown lon nhat cua duong von gop theo lenh (dinh chay -> day)."""
    equity = peak = 1.0
    mdd = 0.0
    for n in nets:
        equity *= 1.0 + n
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak)
    return mdd


def bootstrap_p(nets: list[float], seed: int = BOOT_SEED, n_boot: int = N_BOOT) -> float:
    """p mot phia: ty le trung binh bootstrap cua chuoi DA TRU TRUNG BINH >= trung binh quan sat."""
    n = len(nets)
    if n == 0:
        return 1.0
    arr = np.asarray(nets, dtype=float)
    observed = float(arr.mean())
    demeaned = arr - observed
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = demeaned[idx].mean(axis=1)
    return float(np.mean(means >= observed))


def buy_and_hold_vcb(bars: list[Bar]) -> dict[str, Any]:
    """Mua OPEN phien dau >= 2017-01-01, ban CLOSE phien cuoi <= 2022-12-31 (net_return)."""
    entries = [b for b in bars if bar_date(b) >= BH_START]
    exits = [b for b in bars if bar_date(b) <= BH_END]
    if not entries or not exits:
        raise ValueError("khong du nen cho moc mua-va-giu VCB")
    entry, exit_bar = entries[0], exits[-1]
    entry_open, exit_close = entry.open, exit_bar.close
    gross = net_return(entry_open, exit_close)

    years = (bar_date(exit_bar) - bar_date(entry)).days / 365.25
    cagr = ((1.0 + gross) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    peak = equity = entry_open
    mdd = 0.0
    for b in bars:
        d = bar_date(b)
        if bar_date(entry) <= d <= bar_date(exit_bar):
            equity = b.close
            peak = max(peak, equity)
            mdd = max(mdd, (peak - equity) / peak)

    return {
        "entry_date": bar_date(entry),
        "exit_date": bar_date(exit_bar),
        "entry_open": entry_open,
        "exit_close": exit_close,
        "gross": gross,
        "cagr": cagr,
        "max_dd": mdd,
    }


def rule_stats(trades: list[dict], n_sessions: int) -> dict[str, Any]:
    """Sau so lieu cua brief §1.2 cho luat 2-4."""
    nets = [float(t["net"]) for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    gain = sum(wins)
    loss = abs(sum(losses))
    pf = (gain / loss) if loss > 0 else float("inf")
    held = sum(int(t["hold"]) for t in trades)
    return {
        "n": len(nets),
        "win_rate": (len(wins) / len(nets)) if nets else 0.0,
        "mean_net": statistics.fmean(nets) if nets else 0.0,
        "pf": pf,
        "gross": gross_return(nets),
        "max_dd": max_drawdown_by_trade(nets),
        "session_ratio": (held / n_sessions) if n_sessions else 0.0,
        "p": bootstrap_p(nets),
    }


def gate_rule234(
    *,
    n: int,
    mean_net: float,
    pf: float,
    gross: float,
    bh_gross: float,
    p: float,
) -> tuple[bool, dict[str, bool]]:
    """Cong §1.3 cho luat 2-4: nam dieu kien, so sanh NGHIEM NGAT (khong co >= o bien)."""
    cond = {
        "n_ge_20": n >= N_MIN,
        "mean_positive": mean_net > 0.0,
        "pf_gt_1_2": pf > PF_MIN,
        "gross_gt_bh": gross > bh_gross,
        "p_lt_00125": p < P_MAX,
    }
    return all(cond.values()), cond


def gate_rule1(*, n_fills: int, pnl: float, bh_pnl: float) -> tuple[bool, dict[str, bool]]:
    """Cong §1.3 cho luat 1."""
    cond = {
        "n_ge_20": n_fills >= N_MIN,
        "pnl_positive": pnl > 0.0,
        "pnl_gt_bh": pnl > bh_pnl,
    }
    return all(cond.values()), cond


def count_sessions(bars: list[Bar], is_start: date, is_end: date) -> int:
    """So phien trong cua so IS cua mot luat (mau so cho ty le phien co vi the)."""
    return sum(1 for b in bars if is_start <= bar_date(b) <= is_end)


def _fmt(x: float) -> str:
    return "inf" if x == float("inf") else f"{x:,.4f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kiem bon luat giao dich da co tren rieng ma VCB so voi mua-va-giu (chi doc)"
    )
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args(argv)

    storage = Storage(resolve_dsn(args.dsn))

    universe, exchange_map, n_all, _stocks = load_universe(storage, "exclusions.txt")
    if SYMBOL not in universe:
        print(f"DUNG: {SYMBOL} khong co trong universe ({n_all} ma trong bars_daily).")
        return 2

    exchange = exchange_map.get(SYMBOL) or ""
    bars, dropped = load_vcb_bars(storage)
    if not bars:
        print(f"DUNG: khong doc duoc nen nao cua {SYMBOL}.")
        return 2

    print(f"# {SYMBOL} | san {exchange} | {len(bars)} nen {bar_date(bars[0])} -> {bar_date(bars[-1])}")
    print(f"# Bo {dropped} nen gia <= 0. Cong niem phong: nen >= 2023-01-01 thi nem loi.")
    print("# Luat 2-4: IS theo NGAY TIN HIEU (mac dinh tung script). Luat 1: run_backtest toan bo.")
    print(f"# Cong: n >= {N_MIN} | TB/lanh > 0 | PF > {PF_MIN} | gop > B&H | p < {P_MAX} (Bonferroni 0,05/4)")
    print(f"# Bootstrap {N_BOOT} lan, seed {BOOT_SEED}. Chi doc, khong ghi DB.")
    print()

    bh = buy_and_hold_vcb(bars)
    print(
        f"Moc mua-va-giu {SYMBOL} {bh['entry_date']} -> {bh['exit_date']}: "
        f"gop {bh['gross'] * 100:+.2f}% | CAGR {bh['cagr'] * 100:+.2f}% | "
        f"drawdown lon nhat {bh['max_dd'] * 100:.2f}%"
    )
    print()

    results: dict[str, dict[str, Any]] = {}
    for law in (LAW_PULLBACK, LAW_DONCHIAN, LAW_RSI2):
        spec = LAW_SPECS[law]
        trades = law_trades(bars, law, exchange)
        n_sessions = count_sessions(bars, spec["is_start"], spec["is_end"])
        stats = rule_stats(trades, n_sessions)
        passed, cond = gate_rule234(
            n=stats["n"],
            mean_net=stats["mean_net"],
            pf=stats["pf"],
            gross=stats["gross"],
            bh_gross=bh["gross"],
            p=stats["p"],
        )
        results[law] = {"stats": stats, "passed": passed, "cond": cond}

        print(f"=== Luat 2-4 | {spec['label']} ===")
        print(
            f"  n {stats['n']} | thang {stats['win_rate'] * 100:.1f}% | "
            f"TB/lanh {stats['mean_net'] * 100:+.4f}% | PF {_fmt(stats['pf'])}"
        )
        print(
            f"  gop {stats['gross'] * 100:+.2f}% | drawdown lon nhat {stats['max_dd'] * 100:.2f}% | "
            f"ty le phien co vi the {stats['session_ratio'] * 100:.1f}%"
        )
        print(f"  p mot phia (bootstrap {N_BOOT}) = {stats['p']:.4f}")
        for key, ok in cond.items():
            print(f"    {'DAT' if ok else 'TRUOT'}  {key}")
        print(f"  => {'DAT (dang do tiep)' if passed else 'KHONG DAT'}")
        print()

    # Luat 1: octopus_pullback qua run_backtest, so voi buy_and_hold_pnl cua chinh no.
    report = run_backtest(
        bars,
        STRATEGIES[LAW_OCTOPUS](),
        RiskManager(capital=CAPITAL),
        TrailingStopManager(),
        CAPITAL,
    )
    strat_pnl = report.realized_pnl + report.unrealized_pnl
    l1_passed, l1_cond = gate_rule1(
        n_fills=report.trades, pnl=strat_pnl, bh_pnl=report.buy_and_hold_pnl
    )
    results[LAW_OCTOPUS] = {"passed": l1_passed, "cond": l1_cond}

    print("=== Luat 1 | octopus_pullback (engine dang chay) ===")
    print(f"  so fill SELL {report.trades} | win rate {report.win_rate * 100:.1f}%")
    print(
        f"  PnL chien luoc {strat_pnl:,.0f} (realized {report.realized_pnl:,.0f} + "
        f"unrealized {report.unrealized_pnl:,.0f})"
    )
    print(f"  buy_and_hold_pnl {report.buy_and_hold_pnl:,.0f} | max_drawdown {report.max_drawdown * 100:.2f}%")
    for key, ok in l1_cond.items():
        print(f"    {'DAT' if ok else 'TRUOT'}  {key}")
    print(f"  => {'DAT (dang do tiep)' if l1_passed else 'KHONG DAT'}")
    print()

    print("### Ket luan")
    winners = [law for law, r in results.items() if r["passed"]]
    if winners:
        print(f"  DANG DO TIEP: {', '.join(winners)} — DUNG, khong mo 2023+, khong de xuat chay that.")
    else:
        print("  KHONG luat nao trong bon luat thang viec giu VCB 2017-2022.")
    print()
    print("### Canh bao bat buoc (brief §0)")
    for line in WARNINGS:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
