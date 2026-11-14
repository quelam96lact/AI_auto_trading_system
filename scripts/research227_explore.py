"""Exploration runner for Brief 227: Volume Spike Events + LightGBM Event Filter.

Executes the pre-registered exploration workflow (§1, §3, §5) on data/research227/explore/:
1. Asserts ledger safety at line 1 of run_exploration().
2. Loads sessions, stocks, exchanges and verifies §1 pre-counts before any return computation.
3. For H in (5, 10): evaluates ML, B0, and SHUFFLE variants (logging all 6 rows to trial_ledger.csv).
4. Halts immediately if SHUFFLE passes Gate 1 (§3.7 leakage check).
5. Evaluates all 7 candidate gates (§5) and exports candidates.json & exploration_report.md.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.research188_core import deflated_sharpe
from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import StockDailyBar, load_exchanges, load_stocks
from scripts.research191_exits import assert_ledger_safety
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
)
from scripts.research227_core import (
    COST_RT,
    FEATURE_NAMES,
    MIN_TURNOVER_227,
    PRIOR_NEGATIVE_FAMILIES,
    ClosedEventTrade,
    EventRecord,
    MarketContext,
    compute_open_mkt_return,
    count_precheck_events,
    find_events,
    precompute_market_context,
    prepare_events_with_outcomes,
    simulate_event_portfolio,
    train_and_score,
)

IDEA_ID = "I1_VOLSPIKE_LGBM"
IDEA_SHA = "I1_VOLSPIKE_LGBM"
H_VALUES: tuple[int, ...] = (5, 10)
TEST_YEARS: tuple[int, ...] = (2019, 2020, 2021, 2022)
ALL_YEARS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2020, 2021, 2022)

EXPECTED_TOTAL_EVENTS = 4495
EXPECTED_EVENTS_BY_YEAR: dict[int, int] = {
    2016: 114,
    2017: 385,
    2018: 367,
    2019: 429,
    2020: 661,
    2021: 1445,
    2022: 1094,
}
EXPECTED_LIQUID_SYMBOLS_BY_YEAR: dict[int, int] = {
    2016: 47,
    2017: 72,
    2018: 68,
    2019: 73,
    2020: 93,
    2021: 185,
    2022: 194,
}

LEDGER_PATH = Path("docs/research/dot227/trial_ledger.csv")
CANDIDATES_PATH = Path("docs/research/dot227/candidates.json")
REPORT_PATH = Path("docs/research/dot227/exploration_report.md")


def _compute_trimmed_trade_excess(
    closed_trades: list[ClosedEventTrade],
    event_by_key: dict[tuple[str, date], EventRecord],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    ctx: MarketContext,
    min_turnover: float = MIN_TURNOVER_227,
) -> dict[str, Any]:
    """Compute per-trade net_return - mkt and trimmed mean dropping top 1% winners (Gate 5)."""
    if not closed_trades:
        return {
            "n_trades": 0,
            "n_dropped_ceil": 0,
            "n_dropped_floor": 0,
            "mean_excess_all": 0.0,
            "mean_excess_trimmed_ceil": 0.0,
            "mean_excess_trimmed_floor": 0.0,
            "mean_excess_trimmed_by_net": 0.0,
        }

    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    mkt_cache: dict[tuple[date, date], float | None] = {}
    records: list[tuple[float, float]] = []  # (net_return, net_minus_mkt)

    for tr in closed_trades:
        ev = event_by_key.get((tr.symbol, tr.signal_date))
        if ev is not None and tr.exit_date == ev.sell_date and ev.mkt is not None:
            mkt_val = ev.mkt
        elif tr.exit_reason == "TIME":
            mkt_val = compute_open_mkt_return(
                buy_date=tr.entry_date,
                sell_date=tr.exit_date,
                bars_by_symbol=bars_by_symbol,
                sessions=sessions,
                min_turnover=min_turnover,
                sess_idx_map=sess_idx_map,
                ctx=ctx,
                mkt_cache=mkt_cache,
            )
        else:
            # END liquidation: close[exit_date] / open[entry_date] - 1 across liquid universe
            i_buy = sess_idx_map.get(tr.entry_date)
            if i_buy is not None and i_buy >= 1:
                prev_sess = sessions[i_buy - 1]
                end_rets = []
                for sym, _ in ctx.liquid_syms_prev20.get(prev_sess, ()):
                    d_bar = ctx.sym_date_bar[sym]
                    b_buy = d_bar.get(tr.entry_date)
                    b_sell = d_bar.get(tr.exit_date)
                    if b_buy is not None and b_sell is not None and b_buy.open > 0:
                        end_rets.append(b_sell.close / b_buy.open - 1.0)
                mkt_val = float(np.mean(end_rets)) if end_rets else None
            else:
                mkt_val = None

        if mkt_val is None:
            mkt_val = 0.0
        records.append((tr.net_return, tr.net_return - mkt_val))

    n = len(records)
    n_drop_ceil = math.ceil(0.01 * n)
    n_drop_floor = math.floor(0.01 * n)

    sorted_by_excess = sorted(r[1] for r in records)
    sorted_by_net = sorted(records, key=lambda item: item[0])

    kept_ceil = sorted_by_excess[: max(1, n - n_drop_ceil)] if n > n_drop_ceil else []
    kept_floor = sorted_by_excess[: max(1, n - n_drop_floor)] if n > n_drop_floor else []
    kept_by_net = [r[1] for r in sorted_by_net[: max(1, n - n_drop_ceil)]] if n > n_drop_ceil else []

    return {
        "n_trades": n,
        "n_dropped_ceil": n_drop_ceil,
        "n_dropped_floor": n_drop_floor,
        "mean_excess_all": float(np.mean(sorted_by_excess)),
        "mean_excess_trimmed_ceil": float(np.mean(kept_ceil)) if kept_ceil else 0.0,
        "mean_excess_trimmed_floor": float(np.mean(kept_floor)) if kept_floor else 0.0,
        "mean_excess_trimmed_by_net": float(np.mean(kept_by_net)) if kept_by_net else 0.0,
    }


def _yearly_compounded_returns(
    monthly_returns: list[float],
    rebalance_dates: list[date],
) -> dict[int, float]:
    """Compute compounded annual return per calendar year from monthly returns."""
    by_year: dict[int, list[float]] = {}
    for idx, r_val in enumerate(monthly_returns):
        m_date = rebalance_dates[idx + 1]
        by_year.setdefault(m_date.year, []).append(r_val)
    return {
        yr: float(np.prod([1.0 + x for x in vals]) - 1.0)
        for yr, vals in sorted(by_year.items())
    }


def _format_pct(val: float | None, digits: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.{digits}f}%"


def _verify_precounts(stocks: dict[str, list[StockDailyBar]]) -> dict[str, Any]:
    """Verify §1 event and liquid-symbol counts before computing any returns."""
    pre = count_precheck_events(stocks, min_turnover=MIN_TURNOVER_227)
    print(
        f"Pre-check (cond 1-4): total={pre['total_events']}, "
        f"events_by_year={pre['events_by_year']}"
    )
    print(f"Liquid symbols t>=120 (prev20): {pre['liquid_symbols_by_year_t120']}")
    print(f"Liquid symbols t>=20  (prev20): {pre['liquid_symbols_by_year_t20']}")
    print(f"Liquid symbols t>=19  (incl20): {pre['liquid_symbols_by_year_incl']}")

    mismatches: list[str] = []
    if pre["total_events"] != EXPECTED_TOTAL_EVENTS:
        mismatches.append(
            f"total_events={pre['total_events']} != expected {EXPECTED_TOTAL_EVENTS}"
        )
    if pre["events_by_year"] != EXPECTED_EVENTS_BY_YEAR:
        mismatches.append(
            f"events_by_year={pre['events_by_year']} != expected {EXPECTED_EVENTS_BY_YEAR}"
        )

    matched_sym_def: str | None = None
    for def_name, counts in (
        ("liquid_symbols_by_year_t120", pre["liquid_symbols_by_year_t120"]),
        ("liquid_symbols_by_year_t20", pre["liquid_symbols_by_year_t20"]),
        ("liquid_symbols_by_year_incl", pre["liquid_symbols_by_year_incl"]),
    ):
        if counts == EXPECTED_LIQUID_SYMBOLS_BY_YEAR:
            matched_sym_def = def_name
            break

    if matched_sym_def is None:
        mismatches.append(
            "liquid_symbols_by_year did not match expected "
            f"{EXPECTED_LIQUID_SYMBOLS_BY_YEAR} under t120={pre['liquid_symbols_by_year_t120']}, "
            f"t20={pre['liquid_symbols_by_year_t20']}, incl={pre['liquid_symbols_by_year_incl']}"
        )
    else:
        pre["matched_symbol_count_def"] = matched_sym_def
        print(f"Pre-check matched expected liquid symbol counts via: {matched_sym_def}")

    if mismatches:
        raise RuntimeError(
            "Pre-count mismatch vs Brief §1 (stopped BEFORE computing returns): "
            + "; ".join(mismatches)
        )
    return pre


def run_exploration(
    data_dir: Path | str = "data/research227/explore",
    ledger_path: Path | str = LEDGER_PATH,
    candidates_path: Path | str = CANDIDATES_PATH,
    report_path: Path | str = REPORT_PATH,
    verify_precounts: bool = True,
) -> dict[str, Any]:
    """Run full exploration for Brief 227 (§5).

    First line calls assert_ledger_safety(ledger_path).
    """
    assert_ledger_safety(ledger_path)

    d_dir = Path(data_dir)
    print(f"Loading data from {d_dir}...")
    sessions = load_sessions(d_dir, end=date(2022, 12, 30))
    stocks = load_stocks(d_dir, end=date(2022, 12, 30))
    exchanges = load_exchanges(d_dir)

    precheck: dict[str, Any] | None = None
    if verify_precounts:
        precheck = _verify_precounts(stocks)

    # Rebalance dates for 48 monthly returns: L(2018-12) .. L(2022-12)
    all_rebal = get_rebalance_dates(sessions)
    rebal_dates = [r for r in all_rebal if (2018, 12) <= (r.year, r.month) <= (2022, 12)]
    start_date_2019 = next(s for s in sessions if s.year == 2019)
    end_date_2022 = date(2022, 12, 30)

    print(
        f"Calculating EW benchmark across {len(rebal_dates) - 1} months "
        f"({rebal_dates[0]} -> {rebal_dates[-1]})..."
    )
    ew_rets = ew_benchmark(rebal_dates, stocks, sessions, min_turnover=MIN_TURNOVER_227)

    print("Finding base events (cond 1-5) and precomputing features...")
    ctx = precompute_market_context(stocks, min_turnover=MIN_TURNOVER_227)
    base_events = find_events(
        bars_by_symbol=stocks,
        sessions=sessions,
        exchanges=exchanges,
        min_turnover=MIN_TURNOVER_227,
    )
    print(f"Base events passing all 5 conditions: {len(base_events)}")

    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(candidates_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)

    results_by_h: dict[int, dict[str, Any]] = {}

    for h in H_VALUES:
        print(f"\n=== Evaluating H={h} ===")
        prepared_events = prepare_events_with_outcomes(
            events=base_events,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            h=h,
            min_turnover=MIN_TURNOVER_227,
            ctx=ctx,
        )
        event_by_key = {ev.key: ev for ev in prepared_events}

        ev_count_by_yr = {
            yr: sum(1 for ev in prepared_events if ev.signal_date.year == yr)
            for yr in ALL_YEARS
        }
        labeled_count_by_yr = {
            yr: sum(
                1
                for ev in prepared_events
                if ev.signal_date.year == yr and ev.y is not None
            )
            for yr in ALL_YEARS
        }

        ml_fit = train_and_score(
            events=prepared_events,
            sessions=sessions,
            test_years=TEST_YEARS,
            shuffle_labels=False,
        )
        shuf_fit = train_and_score(
            events=prepared_events,
            sessions=sessions,
            test_years=TEST_YEARS,
            shuffle_labels=True,
            shuffle_seed=227,
        )

        train_size_by_yr = {
            yr: len(ml_fit["train_events_by_year"].get(yr, ())) for yr in TEST_YEARS
        }

        variant_bundles: dict[str, dict[str, Any]] = {}
        for variant, scores in (
            ("ML", ml_fit["scores_by_event_key"]),
            ("B0", None),
            ("SHUFFLE", shuf_fit["scores_by_event_key"]),
        ):
            sim = simulate_event_portfolio(
                events=prepared_events,
                sessions=sessions,
                bars_by_symbol=stocks,
                exchanges=exchanges,
                h=h,
                variant=variant,
                scores=scores,
                rebalance_dates=rebal_dates,
                start_date=start_date_2019,
                end_date=end_date_2022,
                cost_threshold=COST_RT,
            )
            metrics = calculate_rotation_metrics(
                monthly_r=sim["monthly_returns"],
                monthly_ew=ew_rets,
                rebalance_dates=rebal_dates,
                portfolio_metrics={
                    "cagr": sim["cagr"],
                    "mdd": sim["mdd"],
                    "calmar": sim["calmar"],
                },
                seed=227,
            )

            trades = sim["closed_trades"]
            n_trades = len(trades)
            n_time = sum(1 for tr in trades if tr.exit_reason == "TIME")
            n_end = sum(1 for tr in trades if tr.exit_reason == "END")
            win_rate = (
                sum(1 for tr in trades if tr.net_return > 0) / n_trades
                if n_trades > 0
                else 0.0
            )
            mean_net_ret = (
                float(np.mean([tr.net_return for tr in trades]))
                if n_trades > 0
                else 0.0
            )
            trimmed_info = _compute_trimmed_trade_excess(
                closed_trades=trades,
                event_by_key=event_by_key,
                bars_by_symbol=stocks,
                sessions=sessions,
                ctx=ctx,
            )

            ledger_metrics = {
                "n": metrics["n"],
                "mean_net": metrics["mean_X"],
                "sharpe": metrics["sharpe_X"],
                "p": metrics["p"],
                "cagr": metrics["cagr"],
                "mdd": metrics["mdd"],
                "calmar": metrics["calmar"],
            }
            evaluate_and_log(
                idea_id=IDEA_ID,
                idea_fn_or_sha=IDEA_SHA,
                params={"H": h, "variant": variant},
                market="stock",
                period="EXPLORE",
                metrics=ledger_metrics,
                ledger_path=str(ledger_path),
            )

            fit_info = ml_fit if variant == "ML" else (shuf_fit if variant == "SHUFFLE" else None)
            variant_bundles[variant] = {
                "sim": sim,
                "metrics": metrics,
                "n_trades": n_trades,
                "n_time": n_time,
                "n_end": n_end,
                "win_rate": win_rate,
                "mean_net_ret": mean_net_ret,
                "trimmed_excess": trimmed_info,
                "fit": fit_info,
                "yearly_r": _yearly_compounded_returns(sim["monthly_returns"], rebal_dates),
                "yearly_ew": _yearly_compounded_returns(ew_rets, rebal_dates),
            }

            print(
                f"  H={h} {variant:7s}: mean_X={metrics['mean_X']*100:+.2f}%, "
                f"sharpe_X={metrics['sharpe_X']:.3f}, p={metrics['p']:.4f}, "
                f"CAGR={metrics['cagr']*100:.2f}%, MDD={metrics['mdd']*100:.2f}%, "
                f"Calmar={metrics['calmar']:.2f}, trades={n_trades}"
            )

        # §3.7 Shuffled-label pipeline leakage check
        shuf_m = variant_bundles["SHUFFLE"]["metrics"]
        if shuf_m["mean_X"] > 0 and shuf_m["p"] < 0.025:
            raise RuntimeError(
                f"LEAKAGE DETECTED (§3.7): SHUFFLE H={h} passed Gate 1 "
                f"(mean_X={shuf_m['mean_X']*100:.3f}%, p={shuf_m['p']:.4f} < 0.025). "
                "Stopped immediately; report NOT generated."
            )

        # ML vs B0 comparison (Gate 4)
        r_ml = variant_bundles["ML"]["sim"]["monthly_returns"]
        r_b0 = variant_bundles["B0"]["sim"]["monthly_returns"]
        ml_vs_b0 = calculate_rotation_metrics(
            monthly_r=r_ml,
            monthly_ew=r_b0,
            rebalance_dates=rebal_dates,
            portfolio_metrics={
                "cagr": variant_bundles["ML"]["metrics"]["cagr"],
                "mdd": variant_bundles["ML"]["metrics"]["mdd"],
                "calmar": variant_bundles["ML"]["metrics"]["calmar"],
            },
            seed=227,
        )

        # 2022 model feature importances (split & gain)
        model_2022 = ml_fit["models_by_year"].get(2022)
        feat_imp: list[dict[str, Any]] = []
        if model_2022 is not None:
            split_imp = model_2022.booster_.feature_importance(importance_type="split")
            gain_imp = model_2022.booster_.feature_importance(importance_type="gain")
            for fname, sp, gn in zip(FEATURE_NAMES, split_imp, gain_imp):
                feat_imp.append({"feature": fname, "split": int(sp), "gain": float(gn)})
            feat_imp.sort(key=lambda row: (-row["gain"], -row["split"], row["feature"]))

        results_by_h[h] = {
            "event_counts_by_year": ev_count_by_yr,
            "labeled_counts_by_year": labeled_count_by_yr,
            "train_size_by_year": train_size_by_yr,
            "variants": variant_bundles,
            "ml_vs_b0": ml_vs_b0,
            "feature_importance_2022": feat_imp,
        }

    # Evaluate Gates 1-7 for H=5 and H=10
    sharpe_pair = [results_by_h[h]["variants"]["ML"]["metrics"]["sharpe_X"] for h in H_VALUES]
    sr_trials_var = float(np.var(sharpe_pair, ddof=1)) if len(sharpe_pair) > 1 else 0.0
    n_trials_total = len(H_VALUES) + PRIOR_NEGATIVE_FAMILIES  # 2 + 28 = 30

    gates_by_h: dict[int, dict[str, Any]] = {}
    passing_candidates: list[dict[str, Any]] = []

    for h in H_VALUES:
        other_h = 10 if h == 5 else 5
        bundle_ml = results_by_h[h]["variants"]["ML"]
        m_ml = bundle_ml["metrics"]
        ml_vs_b0 = results_by_h[h]["ml_vs_b0"]
        trim_info = bundle_ml["trimmed_excess"]
        other_mean_x = results_by_h[other_h]["variants"]["ML"]["metrics"]["mean_X"]

        dsr_val = deflated_sharpe(
            sr=m_ml["sharpe_X"],
            n_obs=m_ml["n"],
            skew=m_ml["skew"],
            kurt=m_ml["kurt"],
            n_trials=n_trials_total,
            sr_trials_var=sr_trials_var,
        )

        g1 = (m_ml["mean_X"] > 0.0) and (m_ml["p"] < 0.025)
        g2 = bundle_ml["n_trades"] >= 100
        g3 = m_ml["calmar"] >= 0.86
        g4 = (ml_vs_b0["mean_X"] > 0.0) and (ml_vs_b0["p"] < 0.05)
        g5 = trim_info["mean_excess_trimmed_ceil"] > 0.0
        g6 = other_mean_x > 0.0
        g7 = dsr_val >= 0.95
        all_pass = bool(g1 and g2 and g3 and g4 and g5 and g6 and g7)

        gate_summary = {
            "gate1_mean_x_gt_0_and_p_lt_0025": {
                "passed": bool(g1),
                "mean_X": m_ml["mean_X"],
                "p": m_ml["p"],
            },
            "gate2_closed_trades_ge_100": {
                "passed": bool(g2),
                "closed_trades": bundle_ml["n_trades"],
            },
            "gate3_calmar_ge_086": {
                "passed": bool(g3),
                "calmar": m_ml["calmar"],
            },
            "gate4_ml_beats_b0": {
                "passed": bool(g4),
                "mean_diff": ml_vs_b0["mean_X"],
                "p": ml_vs_b0["p"],
            },
            "gate5_trimmed_excess_net_gt_0": {
                "passed": bool(g5),
                "mean_excess_trimmed_ceil": trim_info["mean_excess_trimmed_ceil"],
                "mean_excess_trimmed_floor": trim_info["mean_excess_trimmed_floor"],
                "n_dropped_ceil": trim_info["n_dropped_ceil"],
            },
            "gate6_other_h_mean_x_gt_0": {
                "passed": bool(g6),
                "other_h": other_h,
                "other_mean_X": other_mean_x,
            },
            "gate7_dsr_ge_095": {
                "passed": bool(g7),
                "dsr": dsr_val,
                "n_trials": n_trials_total,
                "sr_trials_var": sr_trials_var,
            },
            "all_passed": all_pass,
        }
        gates_by_h[h] = gate_summary

        if all_pass:
            passing_candidates.append(
                {
                    "idea_id": IDEA_ID,
                    "h": h,
                    "sharpe_X": m_ml["sharpe_X"],
                    "gates": gate_summary,
                }
            )

    # At most 1 candidate: if both pass, choose higher sharpe_X
    if len(passing_candidates) > 1:
        passing_candidates.sort(key=lambda c: -c["sharpe_X"])
        candidates = [passing_candidates[0]]
    else:
        candidates = passing_candidates

    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)

    cand_sha = hashlib.sha256(Path(candidates_path).read_bytes()).hexdigest()
    print(
        f"\nCandidates written to {candidates_path} "
        f"(count: {len(candidates)}, sha256: {cand_sha})"
    )

    report_md = _build_exploration_report(
        precheck=precheck,
        results_by_h=results_by_h,
        gates_by_h=gates_by_h,
        candidates=candidates,
        cand_sha=cand_sha,
        rebal_dates=rebal_dates,
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Exploration report written to {report_path}")

    return {
        "precheck": precheck,
        "results_by_h": results_by_h,
        "gates_by_h": gates_by_h,
        "candidates": candidates,
        "cand_sha": cand_sha,
    }


def _build_exploration_report(
    precheck: dict[str, Any] | None,
    results_by_h: dict[int, dict[str, Any]],
    gates_by_h: dict[int, dict[str, Any]],
    candidates: list[dict[str, Any]],
    cand_sha: str,
    rebal_dates: list[date],
) -> str:
    """Format comprehensive exploration report per Brief 227 §5."""
    lines: list[str] = [
        "# Báo Cáo Khám Phá Đợt 227: Sự Kiện Khối Lượng Đột Biến + LightGBM Lọc Sự Kiện",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS) & ĐA SO SÁNH:**",
        "> - Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết; kết quả tuyệt đối của cả danh mục và EW có thể cao hơn thực tế.",
        f"> - Đã thử 2 cấu hình (`H=5`, `H=10`) trên cùng tập 48 tháng và tính cộng dồn {PRIOR_NEGATIVE_FAMILIES} họ âm trước đó (`n_trials = 2 + {PRIOR_NEGATIVE_FAMILIES} = 30`) vào DSR.",
        "> - Tổng số dòng ghi vào `trial_ledger.csv`: 6 dòng (`I1_VOLSPIKE_LGBM`, H ∈ {5, 10} × {ML, B0, SHUFFLE}).",
        "",
        f"- **Số ứng viên đạt cả 7 cổng:** {len(candidates)}",
        f"- **SHA256 `candidates.json`:** `{cand_sha}`",
        f"- **Giai đoạn mô phỏng 48 tháng:** `{rebal_dates[0]}` → `{rebal_dates[-1]}`",
        "",
    ]

    if precheck is not None:
        lines.extend(
            [
                "## 0. Đối Chiếu Đếm Trước Sự Kiện (§1)",
                "",
                f"- **Sự kiện thoả ĐK 1–4 (chưa ĐK 5):** `{precheck['total_events']}` (dự kiến 4.495) | theo năm: `{precheck['events_by_year']}`",
                f"- **Số mã GTGD20 ≥ 5 tỷ theo năm (`{precheck.get('matched_symbol_count_def', 'N/A')}`):** `{precheck.get(precheck.get('matched_symbol_count_def', 'liquid_symbols_by_year_t20'), {})}`",
                "",
            ]
        )

    lines.extend(
        [
            "## 1. Đối Chiếu Ước Lượng Trước Của Claude (§0)",
            "",
            "- **Ước lượng trước ở §0:** Khả năng qua đủ cổng là **thấp** (28 phép đo âm; các đợt 169/173/175/177 trước đây gặp khó vì phí khứ hồi ~0,76% hoặc trượt kiểm chứng). 0 ứng viên là kết quả hợp lệ.",
            f"- **Kết quả thực tế:** `{len(candidates)}` ứng viên qua đủ 7 cổng.",
            "",
        ]
    )

    for h in H_VALUES:
        h_res = results_by_h[h]
        g = gates_by_h[h]
        lines.extend(
            [
                "---",
                "",
                f"## 2.{h} Cấu Hình H = {h}",
                "",
                "### Số Sự Kiện & Tập Huấn Luyện",
                "",
                "| Năm | Sự kiện đủ 5 ĐK | Có nhãn `y` | Cỡ tập train (khi là năm thử Y) |",
                "|---|---|---|---|",
            ]
        )
        for yr in ALL_YEARS:
            tr_sz = h_res["train_size_by_year"].get(yr, "—")
            lines.append(
                f"| {yr} | {h_res['event_counts_by_year'].get(yr, 0)} | "
                f"{h_res['labeled_counts_by_year'].get(yr, 0)} | {tr_sz} |"
            )

        lines.extend(
            [
                "",
                "### Bảng Chỉ Số 48 Tháng Theo Biến Thể",
                "",
                "| Biến thể | mean_X | Sharpe_X | p | mean_R | mean_EW | CAGR | MDD | Calmar | CAGR EW | Lệnh đóng (TIME/END) | Thắng % | Lãi ròng TB/lệnh | Vốn trong CP TB | Phí/năm (% NAV TB) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for variant in ("ML", "B0", "SHUFFLE"):
            vb = h_res["variants"][variant]
            m = vb["metrics"]
            s = vb["sim"]
            lines.append(
                f"| **{variant}** | {_format_pct(m['mean_X'])} | {m['sharpe_X']:.3f} | {m['p']:.4f} | "
                f"{_format_pct(m['mean_R'])} | {_format_pct(m['mean_EW'])} | "
                f"{_format_pct(m['cagr'])} | {_format_pct(m['mdd'])} | {m['calmar']:.2f} | "
                f"{_format_pct(m['cagr_ew'])} | {vb['n_trades']} ({vb['n_time']}/{vb['n_end']}) | "
                f"{vb['win_rate']*100:.1f}% | {_format_pct(vb['mean_net_ret'])} | "
                f"{s['avg_stock_exposure']*100:.1f}% | {_format_pct(s['annual_fee_pct'])} |"
            )

        lines.extend(
            [
                "",
                "### Phí Theo Năm (% NAV Bình Quân Của Năm)",
                "",
                "| Biến thể | 2019 | 2020 | 2021 | 2022 |",
                "|---|---|---|---|---|",
            ]
        )
        for variant in ("ML", "B0", "SHUFFLE"):
            f_yr = h_res["variants"][variant]["sim"]["fee_pct_by_year"]
            lines.append(
                f"| **{variant}** | {_format_pct(f_yr.get(2019, 0.0))} | "
                f"{_format_pct(f_yr.get(2020, 0.0))} | {_format_pct(f_yr.get(2021, 0.0))} | "
                f"{_format_pct(f_yr.get(2022, 0.0))} |"
            )

        lines.extend(
            [
                "",
                "### Bảng Theo Năm 2019–2022 (Lợi Nhuận Gộp Năm R, EW, X = R − EW)",
                "",
                "| Biến thể | Năm | R | EW | X = R − EW |",
                "|---|---|---|---|---|",
            ]
        )
        for variant in ("ML", "B0", "SHUFFLE"):
            vb = h_res["variants"][variant]
            for yr in TEST_YEARS:
                r_y = vb["yearly_r"].get(yr, 0.0)
                ew_y = vb["yearly_ew"].get(yr, 0.0)
                lines.append(
                    f"| {variant} | {yr} | {_format_pct(r_y)} | {_format_pct(ew_y)} | {_format_pct(r_y - ew_y)} |"
                )

        lines.extend(
            [
                "",
                "### Tương Quan Spearman (Score vs Nhãn Thật y) Theo Năm Thử (Mô Tả)",
                "",
                "| Biến thể | 2019 | 2020 | 2021 | 2022 |",
                "|---|---|---|---|---|",
            ]
        )
        for variant in ("ML", "SHUFFLE"):
            sp = h_res["variants"][variant]["fit"]["spearman_by_year"]
            vals = [
                f"{sp[yr]:.4f}" if sp.get(yr) is not None else "N/A"
                for yr in TEST_YEARS
            ]
            lines.append(f"| {variant} | {' | '.join(vals)} |")

        lines.extend(
            [
                "",
                "### Độ Quan Trọng Đặc Trưng Mô Hình Năm 2022 (Mô Tả, Không Dùng Chọn Lại)",
                "",
                "| Đặc trưng | Gain | Split |",
                "|---|---|---|",
            ]
        )
        for row in h_res["feature_importance_2022"]:
            lines.append(f"| `{row['feature']}` | {row['gain']:.4f} | {row['split']} |")

        g1 = g["gate1_mean_x_gt_0_and_p_lt_0025"]
        g2 = g["gate2_closed_trades_ge_100"]
        g3 = g["gate3_calmar_ge_086"]
        g4 = g["gate4_ml_beats_b0"]
        g5 = g["gate5_trimmed_excess_net_gt_0"]
        g6 = g["gate6_other_h_mean_x_gt_0"]
        g7 = g["gate7_dsr_ge_095"]

        lines.extend(
            [
                "",
                f"### Kết Quả 7 Cổng Cho H = {h}",
                "",
                "| Cổng | Yêu cầu | Giá trị đo | Kết quả |",
                "|---|---|---|---|",
                f"| 1. ML vượt EW | mean_X > 0 & p < 0,025 | mean_X={_format_pct(g1['mean_X'])}, p={g1['p']:.4f} | {'ĐẠT' if g1['passed'] else 'TRƯỢT'} |",
                f"| 2. Số lệnh ML | closed_trades ≥ 100 | {g2['closed_trades']} | {'ĐẠT' if g2['passed'] else 'TRƯỢT'} |",
                f"| 3. Calmar ML | Calmar ≥ 0,86 | {g3['calmar']:.2f} | {'ĐẠT' if g3['passed'] else 'TRƯỢT'} |",
                f"| 4. ML > B0 | mean(R_ML − R_B0) > 0 & p < 0,05 | mean={_format_pct(g4['mean_diff'])}, p={g4['p']:.4f} | {'ĐẠT' if g4['passed'] else 'TRƯỢT'} |",
                f"| 5. Lãi ròng − mkt (bỏ 1% đỉnh) | mean > 0 (bỏ {g5['n_dropped_ceil']} lệnh) | ceil={_format_pct(g5['mean_excess_trimmed_ceil'], 3)}, floor={_format_pct(g5['mean_excess_trimmed_floor'], 3)} | {'ĐẠT' if g5['passed'] else 'TRƯỢT'} |",
                f"| 6. H còn lại dương | mean_X(H={g6['other_h']}) > 0 | {_format_pct(g6['other_mean_X'])} | {'ĐẠT' if g6['passed'] else 'TRƯỢT'} |",
                f"| 7. DSR | DSR ≥ 0,95 (N={g7['n_trials']}, var={g7['sr_trials_var']:.6f}) | {g7['dsr']:.4f} | {'ĐẠT' if g7['passed'] else 'TRƯỢT'} |",
                "",
            ]
        )

    lines.extend(["---", "", "## 3. Danh Sách Ứng Viên Chốt", ""])
    if candidates:
        for cand in candidates:
            lines.append(
                f"- Ứng viên: `{cand['idea_id']}` (`H={cand['h']}`), "
                f"Sharpe_X={cand['sharpe_X']:.3f}, DSR={cand['gates']['gate7_dsr_ge_095']['dsr']:.4f}"
            )
    else:
        lines.append(
            "- **0 ứng viên** đạt đồng thời cả 7 cổng (đúng chuẩn đăng ký trước, không nới cổng)."
        )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    run_exploration()
