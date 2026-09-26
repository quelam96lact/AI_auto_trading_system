"""Do module D (VWAP + Volume Profile + Order Flow) tren BTCUSDT perp 1H — brief dot 106.

Cau truc:
- ham thuan: `mag_ok_series` (+ `MAG_WINDOW`), `bars_5m_by_day`, `load_bars_5m`;
- chay hai cua so CHINH/LAP LAI voi 4 bien the: baseline, flow tat, bo loc chi phi tat,
  bo loc vung can tat;
- doi chung ngau nhien §2.5 (hieu chinh p toi da 5 vong x 50 luot, roi N=1000 x 2 null);
- ket luan §2.6.

Tai dung tu dot 105 (KHONG chep lai): delta, buy_ratio, flow_valid, funding_cost,
null_p_value, buy_and_hold, load_bars, load_flow, load_funding, cac hang so.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import psycopg

from scripts.measure_perp_orderflow import (
    CAPITAL,
    MAIN_END,
    MAIN_START,
    MAX_LEVERAGE,
    NULL_ITERATIONS,
    REPEAT_END,
    REPEAT_START,
    RISK_FRACTION,
    SLIPPAGE_BPS,
    SYMBOL,
    FlowRow,
    buy_and_hold,
    buy_ratio,
    delta,
    flow_valid,
    funding_cost,
    load_bars,
    load_flow,
    load_funding,
    null_p_value,
)
from trading.crypto_fees import BINGX_PERP_TAKER
from trading.metrics import max_drawdown, profit_factor
from trading.models import Bar
from trading.perp_backtest import PerpTrade, RandomEntryConfig
from trading.perp_value_pullback import (
    DayProfile,
    profile_for_days,
    run_value_pullback_backtest,
)

# ---------------------------------------------------------------------------
# Hang so (dang ky truoc theo §2.1)
# ---------------------------------------------------------------------------

MAG_WINDOW = 20  # so nen 1H trong cua so mag_ok (khong gom nen t)
PROFILE_ROWS = 48
VA_PCT = 0.70
INTERVAL_5M = "5m"
LONG_BUY_RATIO = 0.55
SHORT_BUY_RATIO = 0.45
FEE_RATE = BINGX_PERP_TAKER
CALIB_ROUNDS = 5
CALIB_PROBES = 50
CALIB_TOL = 0.10

VARIANTS = (
    ("baseline", True, True, True),
    ("flow_tat", False, True, True),
    ("chi_phi_tat", True, False, True),
    ("vung_can_tat", True, True, False),
)


# ---------------------------------------------------------------------------
# 1. Nap du lieu 5m (chi doc) + ham thuan
# ---------------------------------------------------------------------------

def load_bars_5m(dsn: str, start: datetime, end: datetime) -> list[Bar]:
    """Doc nen 5m tu binance_klines -> list[Bar] (chi doc)."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, open, high, low, close, volume
            FROM binance_klines
            WHERE symbol = %s AND interval = %s AND ts >= %s AND ts < %s
            ORDER BY ts
            """,
            (SYMBOL, INTERVAL_5M, start, end),
        )
        return [
            Bar(
                symbol=SYMBOL,
                ts=r[0],
                open=float(r[1]),
                high=float(r[2]),
                low=float(r[3]),
                close=float(r[4]),
                volume=float(r[5]),
            )
            for r in cur.fetchall()
        ]


def bars_5m_by_day(bars: list[Bar]) -> dict[date, list[Bar]]:
    """Gom nen 5m theo ngay UTC."""
    out: dict[date, list[Bar]] = defaultdict(list)
    for b in bars:
        out[b.ts.date()].append(b)
    return dict(out)


def mag_ok_series(rows: list[FlowRow]) -> dict[datetime, bool | None]:
    """`mag_ok_t = |delta_t| >= median(|delta_{t-20}| .. |delta_{t-1}|)` (§2.1).

    Cua so la `MAG_WINDOW` dong TRUOC trong danh sach, KHONG gom dong `t`.
    Tra `None` khi: dong `t` khong hop le flow, chua du `MAG_WINDOW` dong truoc,
    hoac co dong khong hop le trong cua so (khong noi suy).
    """
    out: dict[datetime, bool | None] = {}
    abs_deltas: list[float] = []
    ok_flags: list[bool] = []
    for row in rows:
        row_ok = flow_valid(row)
        window = abs_deltas[-MAG_WINDOW:]
        window_ok = ok_flags[-MAG_WINDOW:]
        if not row_ok or len(window) < MAG_WINDOW or not all(window_ok):
            out[row.ts] = None
        else:
            out[row.ts] = abs(delta(row)) >= statistics.median(window)
        abs_deltas.append(abs(delta(row)))
        ok_flags.append(row_ok)
    return out


def make_flow_filter(
    flow: dict[datetime, FlowRow],
    mag_ok: dict[datetime, bool | None],
):
    """`entry_filter` cho module D: delta, buy_ratio, mag_ok (§2.2 muc 4)."""

    def _filter(bar: Bar, side: str) -> bool:
        row = flow.get(bar.ts)
        if row is None or not flow_valid(row):
            return False
        if mag_ok.get(bar.ts) is not True:
            return False
        ratio = buy_ratio(row)
        if ratio is None:
            return False
        if side == "LONG":
            return delta(row) > 0 and ratio >= LONG_BUY_RATIO
        return delta(row) < 0 and ratio <= SHORT_BUY_RATIO

    return _filter


# ---------------------------------------------------------------------------
# 2. Chay mot bien the + tong hop
# ---------------------------------------------------------------------------

def run_variant(
    bars: list[Bar],
    profiles: dict[date, DayProfile],
    entry_filter,
    *,
    use_cost_filter: bool = True,
    use_barrier_filter: bool = True,
    random_entry: RandomEntryConfig | None = None,
):
    return run_value_pullback_backtest(
        bars,
        profiles,
        fee_rate=FEE_RATE,
        slippage_bps=SLIPPAGE_BPS,
        capital=CAPITAL,
        risk_fraction=RISK_FRACTION,
        max_leverage=MAX_LEVERAGE,
        entry_filter=entry_filter,
        random_entry=random_entry,
        use_cost_filter=use_cost_filter,
        use_barrier_filter=use_barrier_filter,
    )


def funding_of_trades(trades: list[PerpTrade], rates: list[tuple[datetime, float]]) -> float:
    """Tong phi funding theo tung chan, notional = entry * qty (§2.4)."""
    return sum(
        funding_cost(t.entry_ts, t.exit_ts, t.side, t.entry_price * t.qty, rates) for t in trades
    )


def entries_pnl(trades: list[PerpTrade]) -> dict[tuple[datetime, str], float]:
    """Gop `net_pnl` theo TUNG LAN VAO (entry_ts, side) — §2.6 tieu chi 1."""
    grouped: dict[tuple[datetime, str], float] = defaultdict(float)
    for t in trades:
        grouped[(t.entry_ts, t.side)] += t.net_pnl
    return dict(grouped)


def summarize(report, rates: list[tuple[datetime, float]]) -> dict:
    """Cac so cua §4.5 cho mot bien the."""
    trades = report.trades
    net = sum(t.net_pnl for t in trades)
    funding = funding_of_trades(trades, rates)
    by_entry = entries_pnl(trades)
    wins = sum(1 for v in by_entry.values() if v > 0)
    n_entries = report.entries
    by_year: dict[int, list[float]] = defaultdict(list)
    by_reason: dict[str, list[float]] = defaultdict(list)
    by_side: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_year[t.entry_ts.year].append(t.net_pnl)
        by_reason[t.exit_reason].append(t.net_pnl)
        by_side[t.side].append(t.net_pnl)
    equity_values = [v for _, v in report.equity_curve]
    return {
        "entries": n_entries,
        "legs": len(trades),
        "signals": report.signals_generated,
        "expired": report.orders_expired,
        "dropped_flow": report.dropped_flow,
        "dropped_r": report.dropped_r,
        "dropped_cost": report.dropped_cost,
        "dropped_barrier": report.dropped_barrier,
        "net_pnl": net,
        "funding": funding,
        "net_after_funding": net - funding,
        "win_rate": (wins / n_entries) if n_entries else 0.0,
        "profit_factor": profit_factor([t.net_pnl for t in trades]),
        "max_dd": max_drawdown(equity_values) if equity_values else 0.0,
        "by_year": {y: (len(v), sum(v)) for y, v in sorted(by_year.items())},
        "by_reason": {r: (len(v), sum(v)) for r, v in sorted(by_reason.items())},
        "by_side": {s: (len(v), sum(v)) for s, v in sorted(by_side.items())},
        "long_entries": sum(1 for (_, s) in by_entry if s == "LONG"),
        "end_capital": report.ending_capital,
    }


def _f(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def print_variant(name: str, s: dict) -> None:
    print(
        f"  {name:14s} vao={s['entries']:4d} chan={s['legs']:4d} "
        f"tin_hieu={s['signals']:4d} het_han={s['expired']:3d} "
        f"bo[flow={s['dropped_flow']:3d} R={s['dropped_r']:3d} "
        f"phi={s['dropped_cost']:3d} can={s['dropped_barrier']:3d}]"
    )
    print(
        f"    net={s['net_pnl']:10.2f} funding={s['funding']:8.2f} "
        f"net_sau_funding={s['net_after_funding']:10.2f} "
        f"win={s['win_rate']:.1%} PF={_f(s['profit_factor'])} maxDD={s['max_dd']:.2%}"
    )
    side_txt = " ".join(f"{k}={v[0]}/{v[1]:.2f}" for k, v in s["by_side"].items())
    reason_txt = " ".join(f"{k}={v[0]}/{v[1]:.2f}" for k, v in s["by_reason"].items())
    year_txt = " ".join(f"{k}={v[0]}/{v[1]:.2f}" for k, v in s["by_year"].items())
    print(f"    chieu: {side_txt}")
    print(f"    ly_do_thoat: {reason_txt}")
    print(f"    theo_nam: {year_txt}")


# ---------------------------------------------------------------------------
# 3. Doi chung ngau nhien (§2.5)
# ---------------------------------------------------------------------------

def _null_once(
    bars: list[Bar],
    profiles: dict[date, DayProfile],
    *,
    signal_prob: float,
    long_prob: float,
    seed: int,
) -> tuple[int, float]:
    """Mot luot null: (so lan vao, net_pnl TRUOC funding)."""
    report = run_variant(
        bars,
        profiles,
        None,
        random_entry=RandomEntryConfig(seed=seed, signal_prob=signal_prob, long_prob=long_prob),
    )
    return report.entries, sum(t.net_pnl for t in report.trades)


def calibrate_prob(
    bars: list[Bar],
    profiles: dict[date, DayProfile],
    target_entries: int,
    *,
    long_prob: float = 0.5,
) -> tuple[float, list[tuple[int, float, float]]]:
    """Hieu chinh p cho so lan vao trung binh lech <= 10% (toi da 5 vong x 50 luot)."""
    prob = 0.02
    table: list[tuple[int, float, float]] = []
    for rnd in range(1, CALIB_ROUNDS + 1):
        counts = []
        for i in range(CALIB_PROBES):
            n, _ = _null_once(
                bars,
                profiles,
                signal_prob=prob,
                long_prob=long_prob,
                seed=10_000 + rnd * 100 + i,
            )
            counts.append(n)
        mean = sum(counts) / len(counts)
        table.append((rnd, prob, mean))
        print(f"    vong {rnd}: p={prob:.5f} -> vao trung binh={mean:.1f} (muc tieu {target_entries})")
        if target_entries <= 0:
            break
        if abs(mean - target_entries) <= CALIB_TOL * target_entries:
            break
        if mean <= 0:
            prob *= 2.0
        else:
            prob *= target_entries / mean
        prob = min(max(prob, 1e-4), 0.5)
    return prob, table


def run_null(
    bars: list[Bar],
    profiles: dict[date, DayProfile],
    real: dict,
    iterations: int,
) -> dict:
    """Null A (long 50%) va null B (khop ty le long thuc); lay p LON hon (§2.5)."""
    real_pnl = real["net_pnl"]
    n_entries = max(real["entries"], 1)
    long_prob = real["long_entries"] / n_entries
    print("  Hieu chinh p (50 luot/vong, toi da 5 vong):")
    prob, _ = calibrate_prob(bars, profiles, real["entries"])
    print(f"  p dung: {prob:.5f}; N={iterations} moi null")

    out: dict[str, float] = {}
    for label, lp in (("null A (long 50%)", 0.5), ("null B (ty le long thuc)", long_prob)):
        pnls = []
        for i in range(iterations):
            _, pnl = _null_once(
                bars, profiles, signal_prob=prob, long_prob=lp, seed=500_000 + i
            )
            pnls.append(pnl)
        p = null_p_value(pnls, real_pnl)
        out[label] = p
        print(
            f"    {label}: N={len(pnls)} tb/null={sum(pnls) / len(pnls):.2f} "
            f"median={statistics.median(pnls):.2f} >=thuc={sum(1 for x in pnls if x >= real_pnl)} "
            f"p={p:.4f}"
        )
    out["p"] = max(out.get("null A (long 50%)", 0.0), out.get("null B (ty le long thuc)", 0.0))
    return out


# ---------------------------------------------------------------------------
# 4. Ket luan (§2.6)
# ---------------------------------------------------------------------------

def print_conclusion(main: dict, repeat: dict, p_value: float | None) -> None:
    print("\n### KET LUAN (§2.6)")
    c1 = main["entries"] >= 30
    c2 = main["net_after_funding"] > 0
    c3 = None if p_value is None else (p_value <= 0.05)
    c4 = repeat["net_after_funding"] > 0
    print(f"  (1) CHINH >= 30 lan vao: {main['entries']} -> {'DAT' if c1 else 'HONG'}")
    print(
        f"  (2) CHINH net_sau_funding > 0: {main['net_after_funding']:.2f} -> "
        f"{'DAT' if c2 else 'HONG'}"
    )
    if not (c1 and c2):
        print("  (3) doi chung ngau nhien: BO QUA (CHINH hong (1) hoac (2))")
        print(
            f"  (4) LAP LAI net_sau_funding > 0: {repeat['net_after_funding']:.2f} -> "
            f"{'DAT' if c4 else 'HONG'}"
        )
        print("  => D KHONG CO LOI THE.")
        return
    print(f"  (3) p <= 0,05: p={p_value:.4f} -> {'DAT' if c3 else 'HONG'}")
    print(
        f"  (4) LAP LAI net_sau_funding > 0: {repeat['net_after_funding']:.2f} -> "
        f"{'DAT' if c4 else 'HONG'}"
    )
    ok = c1 and c2 and bool(c3) and c4
    print(f"  => D {'CO' if ok else 'KHONG CO'} LOI THE.")


# ---------------------------------------------------------------------------
# 5. main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Do module D (VWAP + Volume Profile) — dot 106")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--iterations", type=int, default=NULL_ITERATIONS)
    parser.add_argument("--skip-null", action="store_true", help="Bo qua doi chung (chi de thu)")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _db_common import resolve_dsn

    dsn = resolve_dsn(args.dsn)
    t0 = time.time()

    print("### Nap nen 5m 2020-01-01 -> 2026-08-31")
    bars_5m = load_bars_5m(dsn, MAIN_START, REPEAT_END)
    by_day = bars_5m_by_day(bars_5m)
    full_days = sum(1 for v in by_day.values() if len(v) == 288)
    print(
        f"  nen_5m={len(bars_5m)}  ngay={len(by_day)}  ngay_du_288={full_days}  "
        f"tg={time.time() - t0:.1f}s"
    )
    profiles = profile_for_days(
        {d: v for d, v in by_day.items() if len(v) == 288},
        rows=PROFILE_ROWS,
        va_pct=VA_PCT,
    )
    print(f"  profile dung duoc cho {len(profiles)} ngay (dong hoa {time.time() - t0:.1f}s)")

    results: dict[str, dict[str, dict]] = {}
    btc_hold: dict[str, float] = {}

    for window_name, start, end in (
        ("CHINH", MAIN_START, MAIN_END),
        ("LAP LAI", REPEAT_START, REPEAT_END),
    ):
        print(f"\n### {window_name}: {start} -> {end}")
        tw = time.time()
        bars = load_bars(dsn, start, end)
        flow = load_flow(dsn, start, end)
        rates = load_funding(dsn, start, end)
        rows_sorted = [flow[b.ts] for b in bars if b.ts in flow]
        mag_ok = mag_ok_series(rows_sorted)
        missing = sum(1 for b in bars if b.ts not in flow)
        bad_flow = sum(1 for r in rows_sorted if not flow_valid(r))
        mag_true = sum(1 for v in mag_ok.values() if v is True)
        print(
            f"  nen_1h={len(bars)}  funding={len(rates)}  nen_thieu_flow={missing}  "
            f"flow_khong_hop_le={bad_flow}  mag_ok_true={mag_true}"
        )
        btc_hold[window_name] = buy_and_hold(bars)

        window_results: dict[str, dict] = {}
        for name, flow_on, cost_on, barrier_on in VARIANTS:
            v_filter = make_flow_filter(flow, mag_ok) if flow_on else None
            t1 = time.time()
            report = run_variant(
                bars,
                profiles,
                v_filter,
                use_cost_filter=cost_on,
                use_barrier_filter=barrier_on,
            )
            summary = summarize(report, rates)
            window_results[name] = summary
            print(f"  [{name}]  ({time.time() - t1:.1f}s)")
            print_variant(name, summary)
        print(f"  mua-giu BTC: {btc_hold[window_name]:+.2f}%")
        results[window_name] = window_results
        print(f"  (cua so {window_name} xong sau {time.time() - tw:.1f}s)")

    main_sum = results["CHINH"]["baseline"]
    repeat_sum = results["LAP LAI"]["baseline"]

    p_value: float | None = None
    if args.skip_null or not (main_sum["entries"] >= 30 and main_sum["net_after_funding"] > 0):
        print("\n### DOI CHUNG NGau NHIEN: BO QUA")
        if not args.skip_null:
            print(
                f"  ly do: CHINH vao={main_sum['entries']} "
                f"net_sau_funding={main_sum['net_after_funding']:.2f}"
            )
    else:
        print("\n### DOI CHUNG NGau NHIEN (§2.5)")
        tn = time.time()
        bars_main = load_bars(dsn, MAIN_START, MAIN_END)
        null_out = run_null(bars_main, profiles, main_sum, args.iterations)
        p_value = null_out["p"]
        print(f"  p lay lon hon = {p_value:.4f}   (tg {time.time() - tn:.1f}s)")

    print_conclusion(main_sum, repeat_sum, p_value)
    print(f"\nTong thoi gian chay: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
