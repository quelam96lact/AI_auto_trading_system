"""Exploration runner for Brief 245: Ceiling-Lock Continuation (IS-only).

Modes:
- --events-only: Run §2 E3 event detection only and report counts by year/exchange
  (no post-event prices or returns; safe for Step 2 Researcher oracle before 2026-12-01).
- Full IS exploration (default): Run §2-§4 on IS data and write outputs to
  docs/research/dot245/. Guarded against running on real IS data before 2026-12-01.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.research245_core import (
    BOOT_N,
    BOOT_SEED,
    DSR_THRESHOLD,
    HOLDING_HORIZONS,
    HOLM_ALPHA,
    IS_END_DATE,
    MIN_IS_TRADES,
    CeilingEvent,
    SimulationResult245,
    build_sessions,
    detect_ceiling_events,
    evaluate_is_gates,
    load_is_data,
    simulate_horizon,
)

DEFAULT_DATA_DIR = Path("data/research244/is")
DEFAULT_OUT_DIR = Path("docs/research/dot245")
IS_UNLOCK_DATE = date(2026, 12, 1)


def summarize_events(events: list[CeilingEvent]) -> dict[str, Any]:
    """Summarize event counts by year and exchange (no post-event returns)."""
    by_year: dict[int, int] = {}
    by_exchange: dict[str, int] = {}
    unique_days: set[date] = set()
    for ev in events:
        by_year[ev.event_date.year] = by_year.get(ev.event_date.year, 0) + 1
        by_exchange[ev.exchange] = by_exchange.get(ev.exchange, 0) + 1
        unique_days.add(ev.event_date)
    return {
        "total_events": len(events),
        "unique_days": len(unique_days),
        "by_year": dict(sorted(by_year.items())),
        "by_exchange": dict(sorted(by_exchange.items())),
    }


def format_is_report(
    events_summary: dict[str, Any],
    gate_result: dict[str, Any],
) -> str:
    """Format §4 IS exploration report in Markdown."""
    stats_by_h = gate_result["stats_by_h"]
    lines: list[str] = [
        "# Báo cáo IS đợt 245: sự kiện chạm trần khoá (E3)",
        "",
        "## 1. Cảnh báo dữ liệu",
        "- Thiên lệch sống sót (spec H 10/10) và chuỗi giá điều chỉnh chưa hoàn toàn (245 mã bị loại).",
        f"- Tổng sự kiện E3 IS: **{events_summary['total_events']}** trên **{events_summary['unique_days']}** ngày.",
        "",
        "## 2. Kết quả theo cấu hình (H ∈ {3, 5, 10})",
        "",
        "| H | n | mean_X | median_X | X > 0 | sharpe_X | p_boot (tuần) | p_holm | Bỏ (thiếu vào / thiếu ra / đang giữ) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for h in HOLDING_HORIZONS:
        st = stats_by_h[h]
        skipped = (
            f"{st['skipped_missing_entry']} / "
            f"{st['skipped_missing_exit']} / "
            f"{st['skipped_holding']}"
        )
        lines.append(
            f"| {h} | {st['n']} | {st['mean_x']*100:.3f}% | "
            f"{st['median_x']*100:.3f}% | {st['win_rate_x']*100:.1f}% | "
            f"{st['sharpe_x']:.4f} | {st['p_boot']:.4f} | {st['p_holm']:.4f} | {skipped} |"
        )

    pbo_str = f"{gate_result['pbo']:.4f}" if gate_result["pbo"] is not None else "N/A (< 4 tháng)"
    best_h = gate_result["best_h"]
    best_st = stats_by_h[best_h]
    verdict = "ĐẠT IS" if gate_result["is_pass"] else "KHÔNG ĐẠT IS (phép đo âm #33)"

    lines.extend(
        [
            "",
            "## 3. Cổng IS (§4)",
            f"- **PBO (tháng của t+1, chỉ báo cáo):** `{pbo_str}` ({gate_result['pbo_months']} tháng)",
            f"- **Cấu hình chọn (max sharpe_X):** `H={best_h}` (`sharpe_X={best_st['sharpe_x']:.4f}`)",
            f"- **Cao nguyên (láng giềng 3↔5↔10 có mean_X > 0):** `{gate_result['plateau_pass']}`",
            f"- **DSR (n_trials={gate_result['n_trials']}):** `{gate_result['dsr']:.4f}` (ngưỡng ≥ {DSR_THRESHOLD})",
            (
                f"- **Cổng n ≥ {MIN_IS_TRADES}:** `{best_st['n'] >= MIN_IS_TRADES}`; "
                f"**mean_X > 0:** `{best_st['mean_x'] > 0}`; "
                f"**p_holm < {HOLM_ALPHA}:** `{best_st['p_holm'] < HOLM_ALPHA}`"
            ),
            f"- **Kết luận:** **{verdict}**",
            "",
            f"## 4. Mô tả theo năm & sàn (H={best_h})",
            "",
            "### Theo năm (t+1)",
            "| Năm | n | mean_X | X > 0 | sharpe_X |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for yr, y_st in best_st["by_year"].items():
        lines.append(
            f"| {yr} | {y_st['n']} | {y_st['mean_x']*100:.3f}% | "
            f"{y_st['win_rate_x']*100:.1f}% | {y_st['sharpe_x']:.4f} |"
        )

    lines.extend(
        [
            "",
            "### Theo sàn",
            "| Sàn | n | mean_X | X > 0 | sharpe_X |",
            "|:---|---:|---:|---:|---:|",
        ]
    )
    for exch, e_st in best_st["by_exchange"].items():
        lines.append(
            f"| {exch} | {e_st['n']} | {e_st['mean_x']*100:.3f}% | "
            f"{e_st['win_rate_x']*100:.1f}% | {e_st['sharpe_x']:.4f} |"
        )

    return "\n".join(lines) + "\n"


def write_events_csv(events: list[CeilingEvent], csv_path: Path) -> None:
    """Write detected events (symbol, t, exchange) without any price fields."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "t", "exchange"])
        for ev in events:
            writer.writerow([ev.symbol, ev.event_date.isoformat(), ev.exchange])


def run_exploration(
    data_dir: Path,
    out_dir: Path,
    *,
    events_only: bool = False,
    events_csv: Path | None = None,
    n_boot: int = BOOT_N,
    seed: int = BOOT_SEED,
    today: date | None = None,
) -> dict[str, Any]:
    """Run either --events-only or full IS exploration."""
    cur_date = today or datetime.now(timezone(timedelta(hours=7))).date()
    is_real_is_dir = data_dir.resolve() == DEFAULT_DATA_DIR.resolve()
    if not events_only and is_real_is_dir and cur_date < IS_UNLOCK_DATE:
        raise RuntimeError(
            f"Refusing full IS profit run on {data_dir} before {IS_UNLOCK_DATE} "
            f"(today={cur_date}). Use --events-only for Step 2 oracle."
        )

    bars_by_symbol, exchanges = load_is_data(data_dir, end=IS_END_DATE)
    sessions = build_sessions(bars_by_symbol)
    events = detect_ceiling_events(bars_by_symbol, exchanges, sessions=sessions)
    events_summary = summarize_events(events)

    out_dir.mkdir(parents=True, exist_ok=True)
    if events_only:
        (out_dir / "events_summary.json").write_text(
            json.dumps(events_summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if events_csv is not None:
            write_events_csv(events, events_csv)
        return {"events_summary": events_summary}

    sims_by_h: dict[int, SimulationResult245] = {
        h: simulate_horizon(events, bars_by_symbol, sessions, horizon=h)
        for h in HOLDING_HORIZONS
    }
    gate_result = evaluate_is_gates(sims_by_h, n_boot=n_boot, seed=seed)

    rng = random.Random(seed)
    best_trades = sims_by_h[gate_result["best_h"]].trades
    sample_trades = (
        rng.sample(best_trades, min(5, len(best_trades))) if best_trades else []
    )
    sample_dicts = [
        {
            "symbol": t.symbol,
            "horizon": t.horizon,
            "event_date": t.event_date.isoformat(),
            "entry_date": t.entry_date.isoformat(),
            "exit_date": t.exit_date.isoformat(),
            "entry_open": t.entry_open,
            "exit_close": t.exit_close,
            "r_net": t.r_net,
            "r_ew": t.r_ew,
            "excess_x": t.excess_x,
        }
        for t in sample_trades
    ]

    report_md = format_is_report(events_summary, gate_result)
    (out_dir / "is_report.md").write_text(report_md, encoding="utf-8")

    payload = {
        "events_summary": events_summary,
        "gate_result": gate_result,
        "sample_trades": sample_dicts,
    }
    (out_dir / "is_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Brief 245 IS Exploration")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--events-only",
        action="store_true",
        help="Only detect events and output counts (no returns).",
    )
    parser.add_argument(
        "--events-csv",
        type=Path,
        default=None,
        help="Optional CSV path to write (symbol, t, exchange) in --events-only mode.",
    )
    parser.add_argument("--n-boot", type=int, default=BOOT_N)
    parser.add_argument("--seed", type=int, default=BOOT_SEED)
    args = parser.parse_args()

    res = run_exploration(
        data_dir=args.data_dir,
        out_dir=args.out_dir,
        events_only=args.events_only,
        events_csv=args.events_csv,
        n_boot=args.n_boot,
        seed=args.seed,
    )
    print(json.dumps(res["events_summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
