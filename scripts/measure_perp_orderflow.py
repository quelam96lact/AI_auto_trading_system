"""Do Order Flow cho Donchian / Bollinger tren BTCUSDT perp 1H (brief dot 105).

Ba nhom ham:
1. Ham THUAN (khong I/O): `delta`, `buy_ratio`, `flow_valid`, `delta_z_series`,
   `filter_module_a`, `filter_module_b`, `funding_cost`.
2. Ham NAP du lieu (chi doc DB): `load_bars`, `load_flow`, `load_funding`.
3. Ham chay do: hai cua so x hai module x (flow bat/tat), goi `run_null_simulation`.

Tham so lay NGUYEN tu tai lieu chien luoc; khong toi uu, khong quet luoi.
"""

import argparse
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from scripts.significance_test import calibrate_signal_prob, run_null_simulation
except ImportError:
    from significance_test import calibrate_signal_prob, run_null_simulation

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar
from trading.perp_backtest import PerpTrade, run_perp_backtest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Hang so chot truoc (brief §2)
# ---------------------------------------------------------------------------

DELTA_Z_WINDOW = 240  # so nen tham chieu cho z-score cua delta (§2.2)
FLOW_BUY_RATIO_LONG_MIN = 0.55  # §2.2, module A LONG
FLOW_BUY_RATIO_SHORT_MAX = 0.45  # §2.2, module A SHORT
FLOW_DELTA_Z_MIN = 0.5  # §2.4, module B

CAPITAL = 500.0
RISK_FRACTION = 0.005
MAX_LEVERAGE = 10.0
SLIPPAGE_BPS = 2.0
NULL_ITERATIONS = 1000

SYMBOL = "BTCUSDT"
INTERVAL = "1h"

# [start, end) UTC
MAIN_START = datetime(2020, 1, 1, tzinfo=UTC)
MAIN_END = datetime(2024, 1, 1, tzinfo=UTC)
REPEAT_START = datetime(2024, 1, 1, tzinfo=UTC)
REPEAT_END = datetime(2026, 9, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. Ham thuan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlowRow:
    """Mot nen 1H voi cac truong can cho order flow."""

    ts: datetime
    volume: float
    quote_volume: float
    taker_buy_volume: float
    taker_buy_quote_volume: float


def delta(row: FlowRow) -> float:
    """delta = 2 * taker_buy_volume - volume (§2.2 brief)."""
    return 2.0 * row.taker_buy_volume - row.volume


def buy_ratio(row: FlowRow) -> float | None:
    """buy_ratio = taker_buy_quote_volume / quote_volume; None khi quote_volume <= 0."""
    if row.quote_volume <= 0:
        return None
    return row.taker_buy_quote_volume / row.quote_volume


def flow_valid(row: FlowRow) -> bool:
    """Nen dung duoc cho flow: volume > 0 va quote_volume > 0.

    Khong tra 0 gia cho nen thieu du lieu (brief §2.2: khong noi suy).
    """
    return row.volume > 0 and row.quote_volume > 0


def delta_z_series(rows: list[FlowRow]) -> dict[datetime, float | None]:
    """z-score cua delta theo tung nen, CHI dung du lieu truoc nen do.

    Voi nen tai chi so i: z = (delta[i] - mean(W)) / std(W), W = `delta[i-WINDOW:i]`
    (WINDOW = 240, KHONG gom nen i). Tu so la delta cua CHINH nen tin hieu (dung cong thuc
    brief §1); chi cua so tham chieu la qua khu. Ket qua tai t khong doi khi sua nen t+1.
    (Audit dot 105: ban dau tu so la delta[i-1] - lech mot nen, do brief tu mau thuan.)

    Tra None khi i < WINDOW (chua du lich su) hoac do lech chuan = 0.
    """
    out: dict[datetime, float | None] = {}
    deltas: list[float] = []
    for i, row in enumerate(rows):
        if i < DELTA_Z_WINDOW:
            out[row.ts] = None
        else:
            window = deltas[i - DELTA_Z_WINDOW : i]
            mean = statistics.fmean(window)
            sd = statistics.stdev(window)
            if sd == 0:
                out[row.ts] = None
            else:
                out[row.ts] = (delta(row) - mean) / sd
        deltas.append(delta(row))
    return out


def filter_module_a(row: FlowRow, side: str) -> bool:
    """A (§2.2): LONG can delta > 0 VA buy_ratio >= 0.55; SHORT nguoc lai (<= 0.45)."""
    if not flow_valid(row):
        return False
    d = delta(row)
    r = buy_ratio(row)
    if r is None:
        return False
    if side == "LONG":
        return d > 0 and r >= FLOW_BUY_RATIO_LONG_MIN
    return d < 0 and r <= FLOW_BUY_RATIO_SHORT_MAX


def filter_module_b(delta_z: float | None, side: str) -> bool:
    """B (§2.4): LONG can delta_z >= +0.5; SHORT can delta_z <= -0.5; None -> False."""
    if delta_z is None:
        return False
    if side == "LONG":
        return delta_z >= FLOW_DELTA_Z_MIN
    return delta_z <= -FLOW_DELTA_Z_MIN


def _to_second(ts: datetime) -> datetime:
    """Cat timestamp ve giay (brief §2: funding_time co lech mili-giay)."""
    return ts.replace(microsecond=0)


def funding_cost(
    entry_ts: datetime,
    exit_ts: datetime,
    side: str,
    notional: float,
    rates: list[tuple[datetime, float]],
) -> float:
    """Tong phi funding cua mot lenh (§2).

    funding_cost = sum(rate(ft) * notional * (+1 neu LONG, -1 neu SHORT))
    voi moi ft trong (entry_ts, exit_ts]; ft duoc cat ve giay truoc khi so sanh.
    """
    sign = 1.0 if side == "LONG" else -1.0
    entry_s = _to_second(entry_ts)
    exit_s = _to_second(exit_ts)
    total = 0.0
    for ft, rate in rates:
        ft_s = _to_second(ft)
        if entry_s < ft_s <= exit_s:
            total += rate * notional * sign
    return total


# ---------------------------------------------------------------------------
# 2. Nap du lieu (chi doc)
# ---------------------------------------------------------------------------


def load_bars(dsn: str, start: datetime, end: datetime) -> list[Bar]:
    """Doc nen 1H tu binance_klines -> list[Bar]."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, open, high, low, close, volume
            FROM binance_klines
            WHERE symbol = %s AND interval = %s AND ts >= %s AND ts < %s
            ORDER BY ts
            """,
            (SYMBOL, INTERVAL, start, end),
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


def load_flow(dsn: str, start: datetime, end: datetime) -> dict[datetime, FlowRow]:
    """Doc cac truong flow cua binance_klines -> dict theo ts."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, volume, quote_volume, taker_buy_volume, taker_buy_quote_volume
            FROM binance_klines
            WHERE symbol = %s AND interval = %s AND ts >= %s AND ts < %s
            ORDER BY ts
            """,
            (SYMBOL, INTERVAL, start, end),
        )
        return {
            r[0]: FlowRow(
                ts=r[0],
                volume=float(r[1]),
                quote_volume=float(r[2]),
                taker_buy_volume=float(r[3]),
                taker_buy_quote_volume=float(r[4]),
            )
            for r in cur.fetchall()
        }


def load_funding(
    dsn: str, start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    """Doc funding da settle tu binance_funding -> [(funding_time, rate)]."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT funding_time, funding_rate
            FROM binance_funding
            WHERE symbol = %s AND funding_time >= %s AND funding_time < %s
            ORDER BY funding_time
            """,
            (SYMBOL, start, end),
        )
        return [(r[0], float(r[1])) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# 3. Bo dem flow + ket qua mot lan chay
# ---------------------------------------------------------------------------


@dataclass
class FlowCounters:
    """Dem tin hieu theo tung ly do (brief §4.6)."""

    accepted: int = 0
    blocked: int = 0  # flow hop le nhung khong dat nguong
    invalid: int = 0  # flow khong hop le: thieu lich su, std = 0, thieu nen


@dataclass
class RunResult:
    window: str
    module: str
    flow_on: bool
    use_ema_filter: bool
    trades: int
    signals: int
    net_pnl: float
    funding_total: float
    net_after_funding: float
    win_rate: float
    profit_factor: float | None
    max_dd_usdt: float
    max_dd_pct: float
    long_trades: int
    short_trades: int
    long_net: float
    short_net: float
    by_year: dict[int, tuple[int, float]] = field(default_factory=dict)
    counters: FlowCounters = field(default_factory=FlowCounters)


def make_entry_filter(
    module: str,
    flow: dict[datetime, FlowRow],
    delta_z: dict[datetime, float | None],
    counters: FlowCounters,
):
    """Tao closure lam `entry_filter` cho `run_perp_backtest` (dot 105)."""

    def _filter(bar: Bar, side: str) -> bool:
        row = flow.get(bar.ts)
        if row is None or not flow_valid(row):
            counters.invalid += 1
            return False
        if module == "donchian_breakout":
            ok = filter_module_a(row, side)
        else:
            z = delta_z.get(bar.ts)
            if z is None:
                counters.invalid += 1
                return False
            ok = filter_module_b(z, side)
        if ok:
            counters.accepted += 1
        else:
            counters.blocked += 1
        return ok

    return _filter


def _max_drawdown(equity_points: list[float]) -> tuple[float, float]:
    """Tra (muc giam sau nhat tinh bang USDT, % so voi dinh truoc do)."""
    peak = equity_points[0]
    worst_usdt = 0.0
    worst_pct = 0.0
    for eq in equity_points:
        peak = max(peak, eq)
        dd = peak - eq
        if dd > worst_usdt:
            worst_usdt = dd
            worst_pct = (dd / peak * 100.0) if peak > 0 else 0.0
    return worst_usdt, worst_pct


def _funding_of_trades(
    trades: list[PerpTrade], rates: list[tuple[datetime, float]]
) -> list[float]:
    return [
        funding_cost(
            t.entry_ts,
            t.exit_ts,
            t.side,
            t.entry_price * t.qty,
            rates,
        )
        for t in trades
    ]


def run_one(
    bars: list[Bar],
    module: Literal["donchian_breakout", "bollinger_mr"],
    window: str,
    *,
    flow_on: bool,
    use_ema_filter: bool,
    flow: dict[datetime, FlowRow],
    delta_z: dict[datetime, float | None],
    rates: list[tuple[datetime, float]],
) -> RunResult:
    """Chay mot to hop (cua so x module x flow) va tinh chi so sau funding."""
    counters = FlowCounters()
    entry_filter = (
        make_entry_filter(module, flow, delta_z, counters) if flow_on else None
    )

    report = run_perp_backtest(
        bars,
        module,
        capital=CAPITAL,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=SLIPPAGE_BPS,
        risk_fraction=RISK_FRACTION,
        max_leverage=MAX_LEVERAGE,
        use_ema_filter=use_ema_filter,
        entry_filter=entry_filter,
    )

    trades = report.trades
    fund_list = _funding_of_trades(trades, rates)
    net_after_funding = sum(t.net_pnl for t in trades) - sum(fund_list)

    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    equity = CAPITAL
    curve = [equity]
    for t, f in zip(trades, fund_list, strict=True):
        equity += t.net_pnl - f
        curve.append(equity)
    max_dd_usdt, max_dd_pct = _max_drawdown(curve)

    long_trades = [t for t in trades if t.side == "LONG"]
    short_trades = [t for t in trades if t.side == "SHORT"]
    by_year: dict[int, tuple[int, float]] = {}
    for t, f in zip(trades, fund_list, strict=True):
        y = t.entry_ts.year
        n, s = by_year.get(y, (0, 0.0))
        by_year[y] = (n + 1, s + t.net_pnl - f)

    return RunResult(
        window=window,
        module=module,
        flow_on=flow_on,
        use_ema_filter=use_ema_filter,
        trades=len(trades),
        signals=report.signals_generated,
        net_pnl=sum(t.net_pnl for t in trades),
        funding_total=sum(fund_list),
        net_after_funding=net_after_funding,
        win_rate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
        profit_factor=profit_factor,
        max_dd_usdt=max_dd_usdt,
        max_dd_pct=max_dd_pct,
        long_trades=len(long_trades),
        short_trades=len(short_trades),
        long_net=sum(t.net_pnl for t in long_trades),
        short_net=sum(t.net_pnl for t in short_trades),
        by_year=by_year,
        counters=counters,
    )


def buy_and_hold(bars: list[Bar]) -> float:
    """Mua-gia BTC mot lan trong cua so: (close cuoi / close dau - 1) * 100 (%)."""
    if len(bars) < 2:
        return 0.0
    return (bars[-1].close / bars[0].close - 1.0) * 100.0


def null_p_value(raw_pnls: list[float], real_pnl: float) -> float:
    """p = (1 + #{null >= thuc}) / (1 + N) (brief §2, muc 3)."""
    n = len(raw_pnls)
    ge = sum(1 for x in raw_pnls if x >= real_pnl)
    return (1.0 + ge) / (1.0 + n)


# ---------------------------------------------------------------------------
# 4. In bang
# ---------------------------------------------------------------------------


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:+.{nd}f}"


def print_table(results: list[RunResult], window: str, btc_hold: float) -> None:
    print(f"\n{'=' * 108}")
    print(f"CUA SO {window}")
    print(f"{'=' * 108}")
    print(
        f"{'module':<20}{'flow':<6}{'EMA':<6}{'lenh':>6}{'tin hieu':>10}"
        f"{'net_pnl':>11}{'funding':>10}{'net_fund':>11}{'win%':>7}{'PF':>7}"
        f"{'maxDD$':>9}{'maxDD%':>8}"
    )
    for r in results:
        pf = f"{r.profit_factor:.2f}" if r.profit_factor is not None else "n/a"
        print(
            f"{r.module:<20}{'BAT' if r.flow_on else 'TAT':<6}"
            f"{'BAT' if r.use_ema_filter else 'TAT':<6}"
            f"{r.trades:>6}{r.signals:>10}{_fmt(r.net_pnl):>11}{_fmt(r.funding_total):>10}"
            f"{_fmt(r.net_after_funding):>11}{r.win_rate:>7.1f}{pf:>7}"
            f"{_fmt(r.max_dd_usdt):>9}{r.max_dd_pct:>8.1f}"
        )

    print(f"\nMua-gia BTC trong cua so: {btc_hold:+.2f}%")

    print("\n--- Long / Short rieng ---")
    print(
        f"{'module':<20}{'flow':<6}{'EMA':<6}{'L':>5}{'net L':>11}{'S':>6}{'net S':>11}"
    )
    for r in results:
        print(
            f"{r.module:<20}{'BAT' if r.flow_on else 'TAT':<6}"
            f"{'BAT' if r.use_ema_filter else 'TAT':<6}"
            f"{r.long_trades:>5}{_fmt(r.long_net):>11}"
            f"{r.short_trades:>6}{_fmt(r.short_net):>11}"
        )

    print("\n--- Theo tung nam (so lenh, net sau funding) ---")
    for r in results:
        parts = "  ".join(
            f"{y}: {n} lenh {_fmt(s)}" for y, (n, s) in sorted(r.by_year.items())
        )
        print(f"{r.module:<20}flow={'BAT' if r.flow_on else 'TAT'}  {parts}")

    print("\n--- Bo dem flow (so tin hieu) ---")
    for r in results:
        if not r.flow_on:
            continue
        print(
            f"{r.module:<20} nhan={r.counters.accepted}  chan_vi_nguong={r.counters.blocked}"
            f"  bo_vi_flow_khong_hop_le={r.counters.invalid}"
        )


def print_conclusion(
    module: str,
    main: RunResult,
    repeat: RunResult,
    p_a: float,
    p_b: float,
    p_used: float,
    p_min_overall: float,
) -> None:
    cond1 = main.trades >= 30
    cond2 = main.net_after_funding > 0
    if p_used == p_min_overall:
        cond3 = p_used <= 0.025
    else:
        cond3 = p_used <= 0.05
    cond4 = repeat.net_after_funding > 0

    print(f"\nMODULE {module}:")
    print(
        f"  (1) CHINH so lenh >= 30            : {main.trades} lenh -> {'DAT' if cond1 else 'KHONG DAT'}"
    )
    print(
        f"  (2) CHINH net_after_funding > 0    : {_fmt(main.net_after_funding)} -> {'DAT' if cond2 else 'KHONG DAT'}"
    )
    print(
        f"  (3) vuot doi chung (Holm, 2 gia thuyet): p = {p_used:.4f} "
        f"(null A {p_a:.4f}, null B {p_b:.4f}; nguong {0.025 if p_used == p_min_overall else 0.05})"
        f" -> {'DAT' if cond3 else 'KHONG DAT'}"
    )
    print(
        f"  (4) LAP LAI net_after_funding > 0  : {_fmt(repeat.net_after_funding)} -> {'DAT' if cond4 else 'KHONG DAT'}"
    )
    all_ok = cond1 and cond2 and cond3 and cond4
    print(f"  => {'CO LOI THE' if all_ok else 'KHONG CO BANG CHUNG LOI THE'}")


# ---------------------------------------------------------------------------
# 5. main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Do order flow cho perp BTC 1H (dot 105)"
    )
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--iterations", type=int, default=NULL_ITERATIONS)
    parser.add_argument(
        "--skip-null",
        action="store_true",
        help="Bo qua doi chung ngau nhien (chi de thu)",
    )
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)

    windows = [
        ("CHINH", MAIN_START, MAIN_END),
        ("LAP LAI", REPEAT_START, REPEAT_END),
    ]

    all_results: dict[str, list[RunResult]] = {}
    t0 = time.time()

    for window_name, start, end in windows:
        print(f"\n### Nap du lieu {window_name}: {start} -> {end}")
        bars = load_bars(dsn, start, end)
        flow = load_flow(dsn, start, end)
        rates = load_funding(dsn, start, end)
        rows_sorted = [flow[b.ts] for b in bars if b.ts in flow]
        delta_z = delta_z_series(rows_sorted)
        missing = sum(1 for b in bars if b.ts not in flow)
        bad_flow = sum(1 for r in rows_sorted if not flow_valid(r))
        print(
            f"  nen={len(bars)}  flow={len(flow)}  funding={len(rates)}"
            f"  nen_thieu_flow={missing}  nen_flow_khong_hop_le={bad_flow}"
        )

        results: list[RunResult] = []
        for module in ("donchian_breakout", "bollinger_mr"):
            for flow_on in (True, False):
                for use_ema in (
                    (True, False) if module == "donchian_breakout" else (True,)
                ):
                    r = run_one(
                        bars,
                        module,  # type: ignore[arg-type]
                        window_name,
                        flow_on=flow_on,
                        use_ema_filter=use_ema,
                        flow=flow,
                        delta_z=delta_z,
                        rates=rates,
                    )
                    results.append(r)
                    print(
                        f"  -> {module} flow={'BAT' if flow_on else 'TAT'} "
                        f"ema={'BAT' if use_ema else 'TAT'}: {r.trades} lenh, "
                        f"net={_fmt(r.net_pnl)}, net_fund={_fmt(r.net_after_funding)}"
                    )

        print_table(results, window_name, buy_and_hold(bars))
        all_results[window_name] = results

    # --- Doi chung ngau nhien tren cua so CHINH (§2, muc 3) ---
    p_values: dict[str, tuple[float, float, float]] = {}
    main_bars = load_bars(dsn, MAIN_START, MAIN_END)
    for module in ("donchian_breakout", "bollinger_mr"):
        real = next(
            r
            for r in all_results["CHINH"]
            if r.module == module and r.flow_on and r.use_ema_filter
        )
        print(f"\n### Doi chung ngau nhien {module} (CHINH, N={args.iterations})")
        if args.skip_null or real.trades < 30:
            print("  BO QUA (skip-null hoac so lenh < 30)")
            p_values[module] = (float("nan"), float("nan"), float("nan"))
            continue
        real_long_ratio = real.long_trades / real.trades if real.trades else 0.5

        locked_prob, hist = calibrate_signal_prob(
            bars=main_bars,
            module=module,
            real_signals=real.signals,
            real_trades=real.trades,
            long_prob=0.5,
            capital=CAPITAL,
            fee_rate=BINGX_PERP_TAKER,
            slippage_bps=SLIPPAGE_BPS,
            risk_fraction=RISK_FRACTION,
            max_leverage=MAX_LEVERAGE,
            use_ema_filter=real.use_ema_filter,
            max_rounds=3,
            probe_iterations=50,
        )
        for step in hist:
            print(
                f"  hieu chinh: prob={step['signal_prob']:.6f} "
                f"tb_lenh={step['avg_trades']:.1f} lech={step.get('diff_pct', 0.0):+.1f}%"
            )
        print(
            f"  KHOa signal_prob = {locked_prob:.6f}  (long that = {real_long_ratio:.3f})"
        )

        base_kwargs = {
            "bars": main_bars,
            "module": module,
            "iterations": args.iterations,
            "signal_prob": locked_prob,
            "real_pnl": real.net_pnl,
            "capital": CAPITAL,
            "fee_rate": BINGX_PERP_TAKER,
            "slippage_bps": SLIPPAGE_BPS,
            "risk_fraction": RISK_FRACTION,
            "max_leverage": MAX_LEVERAGE,
            "use_ema_filter": real.use_ema_filter,
        }
        t_a = time.time()
        stats_a = run_null_simulation(long_prob=0.5, **base_kwargs)  # type: ignore[arg-type]
        print(
            f"  null A xong sau {time.time() - t_a:.1f}s (tb {stats_a.avg_trades:.1f} lenh)"
        )
        t_b = time.time()
        stats_b = run_null_simulation(long_prob=real_long_ratio, **base_kwargs)  # type: ignore[arg-type]
        print(
            f"  null B xong sau {time.time() - t_b:.1f}s (tb {stats_b.avg_trades:.1f} lenh)"
        )

        p_a = null_p_value(stats_a.raw_pnls, real.net_pnl)
        p_b = null_p_value(stats_b.raw_pnls, real.net_pnl)
        print(f"  net thuc (truoc funding) = {_fmt(real.net_pnl)}")
        print(
            f"  null A: p05={_fmt(stats_a.p05)} p50={_fmt(stats_a.median)} p95={_fmt(stats_a.p95)} -> p={p_a:.4f}"
        )
        print(
            f"  null B: p05={_fmt(stats_b.p05)} p50={_fmt(stats_b.median)} p95={_fmt(stats_b.p95)} -> p={p_b:.4f}"
        )
        p_values[module] = (p_a, p_b, max(p_a, p_b))

    print(f"\n{'=' * 108}")
    print("KET LUAN THEO §2 (Holm cho 2 gia thuyet: A-flow, B-flow)")
    print(f"{'=' * 108}")
    finite = [v[2] for v in p_values.values() if v[2] == v[2]]
    p_min_overall = min(finite) if finite else float("nan")
    for module in ("donchian_breakout", "bollinger_mr"):
        main = next(
            r
            for r in all_results["CHINH"]
            if r.module == module and r.flow_on and r.use_ema_filter
        )
        repeat = next(
            r
            for r in all_results["LAP LAI"]
            if r.module == module and r.flow_on and r.use_ema_filter
        )
        p_a, p_b, p_used = p_values[module]
        print_conclusion(module, main, repeat, p_a, p_b, p_used, p_min_overall)

    print(f"\nTong thoi gian chay: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
