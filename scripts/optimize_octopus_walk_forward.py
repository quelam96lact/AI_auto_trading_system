"""Tối ưu tham số octopus_pullback trên nến ngày, walk-forward (Brief đợt 171).

ĐĂNG KÝ TRƯỚC - KHÔNG ĐỔI SAU KHI THẤY SỐ:
- Giai đoạn CHỌN: 2016-01-01 -> 2019-12-31 (warm-up từ 2015-01-01).
- Giai đoạn KIỂM: 2020-01-01 -> 2022-12-31 (warm-up từ 2019-01-01).
- Niêm phong: CẤM đọc nến >= 2023-01-01 (validate_sealed_bars).
- Lưới 12 bộ tham số cố định:
    tp_atr_mult: [1.5, 2.0, 3.0]
    pullback_window: [5, 10]
    ema_trend: [100, 200]
  Bộ mặc định: (tp_atr_mult=2.0, pullback_window=5, ema_trend=200).
- Quy tắc chọn (2016-2019):
    Trong các bộ >= 300 lệnh, chọn bộ PF ròng cao nhất.
    Hòa -> chọn bộ gần mặc định hơn (khác ít tham số hơn).
    Không bộ nào >= 300 lệnh -> ghi "THIẾU SỨC MẠNH", dừng, không kiểm.
- Phép kiểm (2020-2022, chạy MỘT lần cho cả 12 bộ):
    Bộ được chọn ĐẠT khi đủ cả 5 điều kiện:
      1. >= 100 lệnh ở 2020-2022;
      2. PF ròng > 1.2;
      3. PnL ròng > 0;
      4. PF ròng cao hơn bộ mặc định ở 2020-2022;
      5. Xếp hạng PF ròng ở 2020-2022 nằm trong top 3/12.
- Báo thêm hệ số tương quan hạng Spearman giữa PF giai đoạn chọn và kiểm trên 12 bộ.
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

try:
    from _db_common import resolve_dsn
    from screen_momentum_portfolio import is_stock_symbol
except ImportError:
    from scripts._db_common import resolve_dsn
    from scripts.screen_momentum_portfolio import is_stock_symbol

from trading.backtest import BacktestReport, run_backtest
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.data_quality import is_dirty_bar
from trading.models import Bar
from trading.risk import RiskManager
from trading.stock_study import load_universe, validate_sealed_bars
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0

PHASE1_START = date(2016, 1, 1)
PHASE1_END = date(2019, 12, 31)
PHASE1_WARMUP_START = date(2015, 1, 1)

PHASE2_START = date(2020, 1, 1)
PHASE2_END = date(2022, 12, 31)
PHASE2_WARMUP_START = date(2019, 1, 1)

SEALED_START = date(2023, 1, 1)
DELISTED_CUTOFF_DATE = date(2022, 6, 30)


@dataclass(frozen=True)
class GridConfig:
    tp_atr_mult: float
    pullback_window: int
    ema_trend: int

    @property
    def is_default(self) -> bool:
        return (
            abs(self.tp_atr_mult - 2.0) < 1e-6
            and self.pullback_window == 5
            and self.ema_trend == 200
        )

    @property
    def diff_from_default(self) -> int:
        """Số lượng tham số khác bộ mặc định (2.0, 5, 200)."""
        diff = 0
        if abs(self.tp_atr_mult - 2.0) >= 1e-6:
            diff += 1
        if self.pullback_window != 5:
            diff += 1
        if self.ema_trend != 200:
            diff += 1
        return diff

    @property
    def label(self) -> str:
        return (
            f"TP={self.tp_atr_mult:0.1f}_W={self.pullback_window}_EMA={self.ema_trend}"
        )

    def make_strategy(self) -> OctopusPullbackStrategy:
        return OctopusPullbackStrategy(
            tp_atr_mult=self.tp_atr_mult,
            pullback_window=self.pullback_window,
            ema_trend=self.ema_trend,
        )


DEFAULT_CONFIG = GridConfig(tp_atr_mult=2.0, pullback_window=5, ema_trend=200)

GRID_TP_ATR = [1.5, 2.0, 3.0]
GRID_PULLBACK_WINDOW = [5, 10]
GRID_EMA_TREND = [100, 200]


def build_grid_configs() -> list[GridConfig]:
    """Sinh đúng 12 bộ tham số lưới theo thứ tự xác định."""
    configs: list[GridConfig] = []
    for tp, w, ema in itertools.product(
        GRID_TP_ATR, GRID_PULLBACK_WINDOW, GRID_EMA_TREND
    ):
        configs.append(
            GridConfig(
                tp_atr_mult=float(tp),
                pullback_window=int(w),
                ema_trend=int(ema),
            )
        )
    return configs


GRID_CONFIGS: list[GridConfig] = build_grid_configs()


@dataclass
class PhaseMetrics:
    config: GridConfig
    trades: int
    wins: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pf: float
    net_pnl: float
    pnl_on_capital: float
    buy_and_hold_pnl: float
    symbols_traded: int
    total_symbols: int
    rank: int = 0


@dataclass
class SelectionResult:
    status: str  # "OK" | "THIEU_SUC_MANH"
    selected_config: GridConfig | None
    reason: str
    phase1_metrics: list[PhaseMetrics]


@dataclass
class VerificationResult:
    passed: bool
    selected_config: GridConfig
    conditions: dict[str, tuple[bool, str]]
    spearman_ic: float
    spearman_pvalue: float | None
    phase1_metrics: list[PhaseMetrics]
    phase2_metrics: list[PhaseMetrics]


def run_symbol_phase_backtest(
    bars: list[Bar],
    phase_start: date,
    phase_end: date,
    config: GridConfig,
    capital: float = DEFAULT_CAPITAL,
) -> BacktestReport:
    """Chạy backtest cho 1 mã trong 1 giai đoạn có warm-up.

    - bars: toàn bộ nến từ warmup_start đến phase_end.
    - Nến trước phase_start chỉ dùng để nạp indicator cho strategy (compute_crossover).
    - run_backtest chỉ chạy trên phase_bars (ts.date >= phase_start và <= phase_end).
    - Không có lệnh/PnL nào được sinh ra trước phase_start.
    """
    validate_sealed_bars(bars)

    warmup_bars: list[Bar] = []
    phase_bars: list[Bar] = []

    for b in bars:
        d = b.ts.date()
        if d < phase_start:
            warmup_bars.append(b)
        elif d <= phase_end:
            phase_bars.append(b)

    strat = config.make_strategy()

    # Pre-warm indicator bằng nến sạch trước phase_start
    for b in warmup_bars:
        if not is_dirty_bar(b):
            strat.compute_crossover(b)

    if not phase_bars:
        return BacktestReport()

    risk = RiskManager(capital=capital)
    trailing_stop = TrailingStopManager()

    return run_backtest(
        bars=phase_bars,
        strategy=strat,
        risk=risk,
        trailing_stop=trailing_stop,
        capital=capital,
    )


def aggregate_phase_metrics(
    config: GridConfig,
    reports: list[BacktestReport],
    capital: float = DEFAULT_CAPITAL,
) -> PhaseMetrics:
    """Cộng dồn metrics từ BacktestReport của mọi mã trong giai đoạn."""
    all_sell_fills: list[Fill] = []
    symbols_traded = 0
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0

    for rep in reports:
        sells = [f for f in rep.fills if f.side == "SELL"]
        all_sell_fills.extend(sells)
        if sells:
            symbols_traded += 1
        total_strat_pnl += rep.realized_pnl + rep.unrealized_pnl
        total_bh_pnl += rep.buy_and_hold_pnl

    trades = len(all_sell_fills)
    wins = sum(1 for f in all_sell_fills if f.pnl is not None and f.pnl > 0)
    win_rate = (wins / trades) if trades > 0 else 0.0

    gross_profit = sum(f.pnl for f in all_sell_fills if f.pnl is not None and f.pnl > 0)
    gross_loss = sum(
        abs(f.pnl) for f in all_sell_fills if f.pnl is not None and f.pnl < 0
    )

    if gross_loss == 0.0:
        net_pf = float("inf") if gross_profit > 0 else 0.0
    else:
        net_pf = gross_profit / gross_loss

    total_symbols = len(reports)
    total_capital = total_symbols * capital
    pnl_on_capital = (total_strat_pnl / total_capital) if total_capital > 0 else 0.0

    return PhaseMetrics(
        config=config,
        trades=trades,
        wins=wins,
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pf=net_pf,
        net_pnl=total_strat_pnl,
        pnl_on_capital=pnl_on_capital,
        buy_and_hold_pnl=total_bh_pnl,
        symbols_traded=symbols_traded,
        total_symbols=total_symbols,
    )


def select_best_config(phase1_metrics: list[PhaseMetrics]) -> SelectionResult:
    """Quy tắc chọn (trên giai đoạn CHỌN 2016-2019):

    - Bộ lọc: các bộ có >= 300 lệnh.
    - Nếu không có bộ nào >= 300 lệnh: THIẾU SỨC MẠNH.
    - Chọn bộ có PF ròng cao nhất.
    - Hòa: chọn bộ gần mặc định hơn (diff_from_default nhỏ hơn).
    """
    eligible = [m for m in phase1_metrics if m.trades >= 300]
    if not eligible:
        return SelectionResult(
            status="THIEU_SUC_MANH",
            selected_config=None,
            reason="Không có bộ tham số nào đạt >= 300 lệnh ở giai đoạn chọn 2016-2019.",
            phase1_metrics=phase1_metrics,
        )

    # Tìm max PF
    max_pf = max(m.net_pf for m in eligible)
    candidates = [m for m in eligible if abs(m.net_pf - max_pf) < 1e-9]

    # Hòa: ưu tiên diff_from_default nhỏ nhất, sau đó thứ tự deterministic
    candidates.sort(
        key=lambda m: (
            m.config.diff_from_default,
            m.config.tp_atr_mult,
            m.config.pullback_window,
            m.config.ema_trend,
        )
    )

    best = candidates[0]
    return SelectionResult(
        status="OK",
        selected_config=best.config,
        reason=(
            f"Chọn {best.config.label}: PF={best.net_pf:.4f}, "
            f"trades={best.trades}, diff={best.config.diff_from_default}"
        ),
        phase1_metrics=phase1_metrics,
    )


def rank_metrics_by_pf(metrics_list: list[PhaseMetrics]) -> list[PhaseMetrics]:
    """Gán rank (1-indexed) theo PF giảm dần. Hỗ trợ xử lý hòa."""
    sorted_m = sorted(metrics_list, key=lambda m: m.net_pf, reverse=True)
    for idx, m in enumerate(sorted_m, 1):
        m.rank = idx
    return sorted_m


def rank_data_fractional(vals: Sequence[float]) -> list[float]:
    """Tính thứ hạng phân số (fractional rank) cho Spearman correlation."""
    n = len(vals)
    indexed = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(indexed[j][1] - indexed[i][1]) < 1e-9:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def compute_spearman_ic(
    phase1_metrics: list[PhaseMetrics],
    phase2_metrics: list[PhaseMetrics],
) -> tuple[float, float | None]:
    """Tính tương quan hạng Spearman giữa PF Phase 1 và PF Phase 2 trên 12 bộ."""
    # Khớp theo config
    p1_map = {m.config: m.net_pf for m in phase1_metrics}
    p2_map = {m.config: m.net_pf for m in phase2_metrics}

    configs = list(p1_map.keys())
    if len(configs) < 2:
        return 0.0, None

    x = [p1_map[c] for c in configs]
    y = [p2_map[c] for c in configs]

    # Kiểm tra nếu x hoặc y là mảng hằng số (variance == 0)
    if len(set(x)) <= 1 or len(set(y)) <= 1:
        return 0.0, None

    try:
        import warnings

        from scipy import stats

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = stats.spearmanr(x, y)
        stat = float(res.statistic) if hasattr(res, "statistic") else float(res[0])
        pval = float(res.pvalue) if hasattr(res, "pvalue") else float(res[1])
        if math.isnan(stat):
            return 0.0, None
        return stat, pval
    except Exception:
        # Fallback tính tay
        rx = rank_data_fractional(x)
        ry = rank_data_fractional(y)
        n = len(x)
        mx = sum(rx) / n
        my = sum(ry) / n
        cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
        var_x = sum((rx[i] - mx) ** 2 for i in range(n))
        var_y = sum((ry[i] - my) ** 2 for i in range(n))
        if var_x <= 1e-12 or var_y <= 1e-12:
            return 0.0, None
        return cov / ((var_x * var_y) ** 0.5), None


def evaluate_verification(
    selected_config: GridConfig,
    phase1_metrics: list[PhaseMetrics],
    phase2_metrics: list[PhaseMetrics],
) -> VerificationResult:
    """Phép kiểm (trên giai đoạn KIỂM 2020-2022):

    Bộ được chọn ĐẠT khi đủ cả 5 điều kiện:
      1. >= 100 lệnh ở 2020-2022;
      2. PF ròng > 1.2;
      3. PnL ròng > 0;
      4. PF ròng cao hơn bộ mặc định ở 2020-2022;
      5. Xếp hạng PF của bộ được chọn ở 2020-2022 nằm trong top 3/12.
    """
    # Gán rank cho phase 2
    rank_metrics_by_pf(phase2_metrics)

    p2_map = {m.config: m for m in phase2_metrics}
    sel_p2 = p2_map[selected_config]
    def_p2 = p2_map[DEFAULT_CONFIG]

    cond1 = sel_p2.trades >= 100
    cond1_msg = f"{sel_p2.trades} lệnh (yêu cầu >= 100)"

    cond2 = sel_p2.net_pf > 1.2
    cond2_msg = f"PF={sel_p2.net_pf:.4f} (yêu cầu > 1.2)"

    cond3 = sel_p2.net_pnl > 0
    cond3_msg = f"PnL={sel_p2.net_pnl:,.0f} VND (yêu cầu > 0)"

    cond4 = sel_p2.net_pf > def_p2.net_pf
    cond4_msg = f"PF bộ chọn ({sel_p2.net_pf:.4f}) > PF mặc định ({def_p2.net_pf:.4f})"

    cond5 = sel_p2.rank <= 3
    cond5_msg = f"Hạng {sel_p2.rank}/12 (yêu cầu top 3/12)"

    conditions = {
        "cond1_min_100_trades": (cond1, cond1_msg),
        "cond2_pf_gt_1_2": (cond2, cond2_msg),
        "cond3_pnl_gt_0": (cond3, cond3_msg),
        "cond4_pf_gt_default": (cond4, cond4_msg),
        "cond5_rank_top_3": (cond5, cond5_msg),
    }

    passed = all(c[0] for c in conditions.values())
    spearman_ic, spearman_pval = compute_spearman_ic(phase1_metrics, phase2_metrics)

    return VerificationResult(
        passed=passed,
        selected_config=selected_config,
        conditions=conditions,
        spearman_ic=spearman_ic,
        spearman_pvalue=spearman_pval,
        phase1_metrics=phase1_metrics,
        phase2_metrics=phase2_metrics,
    )


def count_delisted_before_cutoff(storage: Storage, symbols: Sequence[str]) -> int:
    """Đếm số mã có nến cuối trước 30/06/2022 (giờ VN) trong DB."""
    cutoff = datetime(
        DELISTED_CUTOFF_DATE.year,
        DELISTED_CUTOFF_DATE.month,
        DELISTED_CUTOFF_DATE.day,
        23,
        59,
        59,
        tzinfo=TZ,
    )
    with storage.conn() as c:
        rows = c.execute(
            "SELECT symbol, max(ts) FROM bars_daily " "WHERE ts < %s GROUP BY symbol",
            (
                datetime(
                    SEALED_START.year, SEALED_START.month, SEALED_START.day, tzinfo=TZ
                ),
            ),
        ).fetchall()

    sym_set = set(symbols)
    delisted = [
        r[0] for r in rows if r[0] in sym_set and r[1] is not None and r[1] < cutoff
    ]
    return len(delisted)


def load_all_bars_for_phase(
    storage: Storage,
    symbols: Sequence[str],
    warmup_start: date,
    phase_end: date,
) -> dict[str, list[Bar]]:
    """Đọc nến cho danh sách mã trong khoảng [warmup_start, phase_end]."""
    start_dt = datetime(
        warmup_start.year, warmup_start.month, warmup_start.day, tzinfo=TZ
    )
    end_dt = datetime(
        phase_end.year, phase_end.month, phase_end.day, tzinfo=TZ
    ) + timedelta(days=1)

    bars_by_symbol: dict[str, list[Bar]] = {}
    for sym in symbols:
        bars = storage.read_daily_bars(sym, start_dt, end_dt)
        validate_sealed_bars(bars)
        bars_by_symbol[sym] = bars

    return bars_by_symbol


def run_phase_grid_backtest(
    bars_by_symbol: dict[str, list[Bar]],
    phase_start: date,
    phase_end: date,
    configs: Sequence[GridConfig],
    capital: float = DEFAULT_CAPITAL,
) -> list[PhaseMetrics]:
    """Chạy backtest cho danh sách config trên dữ liệu đã nạp sẵn vào RAM."""
    results: list[PhaseMetrics] = []
    for cfg in configs:
        reports: list[BacktestReport] = []
        for bars in bars_by_symbol.values():
            rep = run_symbol_phase_backtest(
                bars=bars,
                phase_start=phase_start,
                phase_end=phase_end,
                config=cfg,
                capital=capital,
            )
            reports.append(rep)
        metrics = aggregate_phase_metrics(cfg, reports, capital=capital)
        results.append(metrics)
    return results


def run_smoke_timing(
    storage: Storage,
    symbols: list[str],
    capital: float = DEFAULT_CAPITAL,
) -> None:
    """Chạy thử 1 bộ tham số trên 10 mã để ước tính thời gian chạy.

    QUY TẮC: KHÔNG in hay báo kết quả PnL của lần thử.
    """
    smoke_symbols = symbols[:10]
    cfg = DEFAULT_CONFIG

    print(
        f"--- SMOKE TIMING TEST (1 bộ tham số x {len(smoke_symbols)} mã, Phase 1) ---"
    )
    t0 = time.perf_counter()

    bars_map = load_all_bars_for_phase(
        storage=storage,
        symbols=smoke_symbols,
        warmup_start=PHASE1_WARMUP_START,
        phase_end=PHASE1_END,
    )
    t_load = time.perf_counter() - t0

    t1 = time.perf_counter()
    reports = []
    for bars in bars_map.values():
        rep = run_symbol_phase_backtest(
            bars=bars,
            phase_start=PHASE1_START,
            phase_end=PHASE1_END,
            config=cfg,
            capital=capital,
        )
        reports.append(rep)
    t_bt = time.perf_counter() - t1
    t_total = time.perf_counter() - t0

    n_total_syms = len(symbols)
    est_load_all = (t_load / len(smoke_symbols)) * n_total_syms
    est_bt_all_phase1 = (t_bt / len(smoke_symbols)) * n_total_syms * 12
    # Phase 2 (3 năm vs 4 năm) ~ 0.75x Phase 1
    est_bt_all_phase2 = est_bt_all_phase1 * 0.75
    est_total_seconds = est_load_all * 2 + est_bt_all_phase1 + est_bt_all_phase2

    print(f"Số mã thử: {len(smoke_symbols)}")
    print(
        f"Thời gian nạp nến: {t_load:.3f} s ({t_load / len(smoke_symbols) * 1000:.1f} ms/mã)"
    )
    print(
        f"Thời gian chạy 1 backtest: {t_bt:.3f} s "
        f"({t_bt / len(smoke_symbols) * 1000:.1f} ms/mã/bộ)"
    )
    print(f"Tổng thời gian smoke: {t_total:.3f} s")
    print(
        f"\n--- ƯỚC TÍNH TOÀN BỘ PHÉP ĐO (12 bộ x 2 giai đoạn x {n_total_syms} mã) ---"
    )
    print(f"Tổng số mã trong universe: {n_total_syms}")
    print(
        f"Ước tính thời gian chạy: {est_total_seconds:.1f} s (~{est_total_seconds / 60:.1f} phút)"
    )
    print(
        "(Đã bảo toàn quy tắc: KHÔNG in, KHÔNG tính và KHÔNG báo kết quả PnL "
        "của smoke test)"
    )


def print_metrics_table(title: str, metrics: list[PhaseMetrics]) -> None:
    print(f"\n{title}")
    print("=" * 115)
    header = (
        f"{'Bộ tham số':<24} | {'Hạng':<4} | {'Lệnh':<6} | {'Thắng':<5} | "
        f"{'WinRate':<7} | {'PF ròng':<8} | {'PnL ròng (VND)':<16} | "
        f"{'PnL/Vốn':<7} | {'B&H PnL (VND)':<16}"
    )
    print(header)
    print("-" * 115)
    for m in metrics:
        def_tag = " (*)" if m.config.is_default else ""
        cfg_name = m.config.label + def_tag
        pf_str = f"{m.net_pf:.4f}" if m.net_pf != float("inf") else "inf"
        row = (
            f"{cfg_name:<24} | {m.rank:<4} | {m.trades:<6} | {m.wins:<5} | "
            f"{m.win_rate * 100:>6.1f}% | {pf_str:>8} | "
            f"{m.net_pnl:>16,.0f} | {m.pnl_on_capital * 100:>6.2f}% | "
            f"{m.buy_and_hold_pnl:>16,.0f}"
        )
        print(row)
    print("=" * 115)
    print("(*) = Bộ mặc định (tp_atr_mult=2.0, pullback_window=5, ema_trend=200)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tối ưu tham số octopus_pullback walk-forward (Brief 171)"
    )
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    parser.add_argument(
        "--capital",
        type=float,
        default=DEFAULT_CAPITAL,
        help="Vốn mỗi mã (mặc định 1 tỷ)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Giới hạn số mã (0 = toàn bộ)",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Danh sách mã cách nhau bởi dấu phẩy",
    )
    parser.add_argument(
        "--exclude-file",
        default="exclusions.txt",
        help="File danh sách mã loại trừ",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Chạy smoke test đo thời gian (1 bộ x 10 mã, không in PnL)",
    )
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    # 1. Universe
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        universe = [s for s in symbols if is_stock_symbol(s)]
    else:
        loaded_univ, _, _, _ = load_universe(storage, args.exclude_file)
        universe = [s for s in loaded_univ if is_stock_symbol(s)]

    if args.limit > 0:
        universe = universe[: args.limit]

    print("=== TỐI ƯU THAM SỐ OCTOPUS_PULLBACK WALK-FORWARD (BRIEF 171) ===")
    print(f"Tổng số mã trong universe: {len(universe)}")

    # 2. Kiểm tra mã hủy niêm yết
    delisted_count = count_delisted_before_cutoff(storage, universe)
    print(f"Số mã có nến cuối trước 30/06/2022 (mã đã hủy niêm yết): {delisted_count}")
    # Chu du an quyet dinh 10/10/2026: KHONG dung ma da huy niem yet (brief 171 §7).
    # Bo cong du lieu; ket qua bat buoc mang canh bao thien lech song sot.
    print(
        "[CẢNH BÁO] Universe gần như chỉ gồm mã còn sống (thiên lệch sống sót, "
        "đợt 169). Kết quả có thể bị thổi phồng; chỉ so được với mua-và-giữ cùng mã."
    )

    # 3. Smoke timing mode
    if args.smoke:
        run_smoke_timing(storage, universe, capital=args.capital)
        return

    # 4. Phase 1: Giai đoạn CHỌN (2016-01-01 -> 2019-12-31)
    print("\n>>> Đang nạp nến và chạy Giai đoạn CHỌN (2016-01-01 -> 2019-12-31)...")
    p1_bars_map = load_all_bars_for_phase(
        storage=storage,
        symbols=universe,
        warmup_start=PHASE1_WARMUP_START,
        phase_end=PHASE1_END,
    )
    p1_metrics = run_phase_grid_backtest(
        bars_by_symbol=p1_bars_map,
        phase_start=PHASE1_START,
        phase_end=PHASE1_END,
        configs=GRID_CONFIGS,
        capital=args.capital,
    )
    rank_metrics_by_pf(p1_metrics)
    print_metrics_table(
        "BẢNG KẾT QUẢ GIAI ĐOẠN CHỌN (2016-01-01 -> 2019-12-31)", p1_metrics
    )

    # 5. Áp dụng quy tắc chọn
    sel_res = select_best_config(p1_metrics)
    print("\n--- KẾT QUẢ CHỌN THAM SỐ (Giai đoạn 2016-2019) ---")
    print(f"Trạng thái: {sel_res.status}")
    print(f"Chi tiết: {sel_res.reason}")

    if sel_res.status == "THIEU_SUC_MANH" or sel_res.selected_config is None:
        print(
            "\n>>> KẾT LUẬN: THIẾU SỨC MẠNH. Dừng theo quy định Brief 171 §1.6. "
            "Không kiểm Phase 2."
        )
        return

    selected_cfg = sel_res.selected_config
    print(f"\n>>> Bộ tham số được chọn: {selected_cfg.label}")

    # 6. Phase 2: Giai đoạn KIỂM (2020-01-01 -> 2022-12-31)
    print("\n>>> Đang nạp nến và chạy Giai đoạn KIỂM (2020-01-01 -> 2022-12-31)...")
    p2_bars_map = load_all_bars_for_phase(
        storage=storage,
        symbols=universe,
        warmup_start=PHASE2_WARMUP_START,
        phase_end=PHASE2_END,
    )
    p2_metrics = run_phase_grid_backtest(
        bars_by_symbol=p2_bars_map,
        phase_start=PHASE2_START,
        phase_end=PHASE2_END,
        configs=GRID_CONFIGS,
        capital=args.capital,
    )
    rank_metrics_by_pf(p2_metrics)
    print_metrics_table(
        "BẢNG KẾT QUẢ GIAI ĐOẠN KIỂM (2020-01-01 -> 2022-12-31)", p2_metrics
    )

    # 7. Đánh giá phép kiểm 5 điều kiện
    ver_res = evaluate_verification(
        selected_config=selected_cfg,
        phase1_metrics=p1_metrics,
        phase2_metrics=p2_metrics,
    )

    print(
        f"\n--- PHÉP KIỂM 5 ĐIỀU KIỆN (Giai đoạn 2020-2022 cho bộ {selected_cfg.label}) ---"
    )
    for name, (ok, msg) in ver_res.conditions.items():
        status_str = "[ĐẠT]" if ok else "[KHÔNG ĐẠT]"
        print(f"  {status_str} {name}: {msg}")

    print("\n--- TƯƠNG QUAN HẠNG SPEARMAN (12 bộ giữa 2016-2019 và 2020-2022) ---")
    pval_str = (
        f", p-value={ver_res.spearman_pvalue:.4f}"
        if ver_res.spearman_pvalue is not None
        else ""
    )
    print(f"Spearman rank correlation (PF): {ver_res.spearman_ic:.4f}{pval_str}")

    print("\n" + "=" * 80)
    if ver_res.passed:
        print(">>> KẾT LUẬN TOÀN CỤC: ĐẠT")
        print(
            "CẢNH BÁO ĐA SO SÁNH: 12 bộ tham số, giả thuyết thứ 4 trong tháng 10.\n"
            "Bước tiếp theo: Paper forward song song bộ được chọn với bộ mặc định\n"
            "(>= 50 lệnh hoặc >= 3 tháng) trước khi xem xét đổi tham số engine."
        )
    else:
        print(">>> KẾT LUẬN TOÀN CỤC: KHÔNG ĐẠT")
        print(
            "Tối ưu tham số octopus_pullback (12 bộ, walk-forward 2016–2019 / 2020–2022):\n"
            "KHÔNG có bộ tham số bền (Phép đo âm thứ 16).\n"
            "Đề xuất chủ dự án ngừng phát triển octopus."
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
