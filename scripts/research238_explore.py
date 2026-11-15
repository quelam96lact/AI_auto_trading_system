"""Exploration runner for Brief 238 (High Attention Monthly Rotation).

Reuses the Step 0-4 exploration framework from scripts/research237_explore.py with:
- select_highattn_symbols (highest AT_S first, A->Z tie-break)
- idea_id = 'I1_HIGHATTN', seed = 238
- DSR n_trials = 9 + MIRROR_TRIALS(9) + PRIOR_NEGATIVE_FAMILIES(30) = 48
- Outputs under docs/research/dot238/
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any

from scripts.research191_exits import assert_ledger_safety
from scripts.research237_explore import (
    DATA_DIR,
    ETF_EA_CAGR,
    ETF_EA_MDD,
    ETF_EB_CAGR,
    ETF_EB_MDD,
    EXPECTED_STEP0_COUNTS,
    GRID,
    OLD_CALMAR_GATE,
    _config_key,
    _format_report_row,
    check_eb_gates,
    check_plateau,
    check_step0_universe,
    compute_step4_dsr,
    run_step0_only,
    select_best_ea_config,
)
from scripts.research237_explore import (
    run_exploration as _run_exploration_237,
)
from scripts.research238_core import select_highattn_symbols

LEDGER_PATH = "docs/research/dot238/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot238/candidates.json"
REPORT_PATH = "docs/research/dot238/exploration_report.md"
SELECTIONS_PATH = "docs/research/dot238/selections.json"
DOT237_REPORT_PATH = "docs/research/dot237/exploration_report.md"

IDEA_ID = "I1_HIGHATTN"
IDEA_TYPE = "HIGHATTN"
SEED_238 = 238
MIRROR_TRIALS = 9
PRIOR_NEGATIVE_FAMILIES_238 = 30

__all__ = [
    "CANDIDATES_PATH",
    "DATA_DIR",
    "DOT237_REPORT_PATH",
    "GRID",
    "IDEA_ID",
    "IDEA_TYPE",
    "LEDGER_PATH",
    "MIRROR_TRIALS",
    "PRIOR_NEGATIVE_FAMILIES_238",
    "REPORT_PATH",
    "SEED_238",
    "SELECTIONS_PATH",
    "check_eb_gates",
    "check_plateau",
    "check_step0_universe",
    "compute_step4_dsr_238",
    "run_exploration",
    "run_step0_only",
    "select_best_ea_config",
]


def compute_step4_dsr_238(
    sharpe_x: float,
    n_months: int,
    skew: float,
    kurt: float,
    ea_sharpes: list[float],
) -> float:
    """Compute Step 4 DSR with n_trials = len(ea_sharpes) + 9 + 30 (§1)."""
    return compute_step4_dsr(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
        extra_trials=MIRROR_TRIALS + PRIOR_NEGATIVE_FAMILIES_238,
    )


def _parse_dot237_turnover_and_fees(
    dot237_report_path: Path | str = DOT237_REPORT_PATH,
) -> dict[str, tuple[str, str]]:
    """Read existing dot237 EA turnover and annual fee columns verbatim from report."""
    p = Path(dot237_report_path)
    if not p.exists():
        return {}

    parsed: dict[str, tuple[str, str]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 15:
            continue
        m = re.search(r"S\d+_N\d+", cells[0])
        if not m:
            continue
        parsed[m.group(0)] = (cells[12], cells[13])
    return parsed


def _build_report_markdown_238(
    step0_counts: dict[str, int] | None,
    ea_results: list[dict[str, Any]],
    best_ea: dict[str, Any],
    plateau_passed: bool,
    plateau_reasons: list[str],
    eb_entry: dict[str, Any] | None,
    eb_passed: bool | None,
    eb_reasons: list[str],
    dsr_val: float | None,
    candidates: list[dict[str, Any]],
    cand_sha: str,
    sel_sha: str,
) -> str:
    dot237_costs = _parse_dot237_turnover_and_fees()
    lines: list[str] = [
        "# Báo Cáo Khám Phá Danh Mục Đang Được Chú Ý (Brief 238)",
        "",
        "> [!CAUTION]",
        "> **CẢNH BÁO GIẢ THUYẾT SINH SAU KHI XEM DỮ LIỆU (EA ĐÃ NHIỄM) & ĐA SO SÁNH:**",
        "> Đợt 237 cho 9/9 cấu hình `AT_S` thấp thua EW trên EA; đợt 238 thử chiều ngược (`AT_S` cao) là giả thuyết sinh sau khi đã thấy kết quả EA và vượt ngân sách mục F (suất thứ 4 tháng 11, tổng `N_trials = 9 + 9 + 30 = 48` khi tính DSR). Kết quả EA chỉ dùng để chọn đỉnh và kiểm cao nguyên; bằng chứng nằm ở EB (chưa mở trước đó) và V1/V2.",
        "",
        "> [!WARNING]",
        "> **CẢNH BÁO TRÁI CHIỀU ĐỢT 227 & THIÊN LỆCH SỐNG SÓT:**",
        "> - Trái chiều với đợt 227 và giả thuyết ban đầu của đợt 237 về quá giá do chú ý ngắn hạn.",
        "> - Dữ liệu `stocks_daily` gần như không có mã huỷ niêm yết (thiên lệch sống sót), làm sai lệch phân phối lợi nhuận/turnover tương đối.",
        "",
        f"- **Tổng số dòng EA đã ghi sổ:** {len(ea_results)}",
        f"- **Tổng số dòng EB đã ghi sổ:** {1 if eb_entry is not None else 0}",
        f"- **Số ứng viên chốt:** {len(candidates)}",
        f"- **SHA256 `candidates.json`:** `{cand_sha}`",
        f"- **SHA256 `selections.json`:** `{sel_sha}`",
        "",
    ]

    if step0_counts:
        lines.extend([
            "## Bước 0: Kiểm đếm Universe (§1 & §3.2)",
            "",
            "| Mốc | Số mã thực tế | Số mã Lead đếm trước |",
            "|---|---|---|",
        ])
        for (yr, mo), exp in EXPECTED_STEP0_COUNTS.items():
            lbl = f"L({mo:02d}/{yr})"
            lines.append(f"| {lbl} | {step0_counts.get(lbl, 'N/A')} | {exp} |")
        lines.append("")

    lines.extend([
        "## Bước 1: Kết quả toàn bộ 9 cấu hình EA (L(01/2017) -> L(12/2019))",
        "",
        f"- **Mốc ETF EA (`E1VFVN30`):** CAGR = `{ETF_EA_CAGR*100:.2f}%`, MDD = `{ETF_EA_MDD*100:.2f}%`.",
        f"- **Cấu hình chọn (Sharpe_X cao nhất):** `{best_ea['params']}` (Sharpe_X = `{best_ea['metrics']['sharpe_X']:.4f}`, mean_X = `{best_ea['metrics']['mean_X']*100:.2f}%`).",
        "",
        "| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ])
    for entry in ea_results:
        cfg_label = _config_key(entry["params"])
        if entry["params"] == best_ea["params"]:
            cfg_label = f"**{cfg_label} (đỉnh)**"
        lines.append(_format_report_row(cfg_label, entry["metrics"], entry["sim"]))

    lines.extend([
        "",
        "### So sánh Turnover & Phí với Đợt 237 (EA)",
        "",
        "| Cấu hình | Turnover tháng TB (238) | Turnover tháng TB (237) | Phí / năm % NAV (238) | Phí / năm % NAV (237) |",
        "|---|---|---|---|---|",
    ])
    for entry in ea_results:
        key = _config_key(entry["params"])
        s_ea = entry["sim"]
        t237, f237 = dot237_costs.get(key, ("N/A", "N/A"))
        lines.append(
            f"| {key} | {s_ea['mean_turnover']*100:.2f}% | {t237} | "
            f"{s_ea['annual_fee_pct']*100:.2f}% | {f237} |"
        )

    lines.extend([
        "",
        "## Bước 2: Kiểm cao nguyên (±1 bước trên cả `S` và `N`)",
        "",
        f"- **Kết quả:** **{'ĐẠT' if plateau_passed else 'TRƯỢT'}**",
    ])
    if plateau_reasons:
        for reason in plateau_reasons:
            lines.append(f"  - Lỗi láng giềng: {reason}")
    else:
        lines.append("  - Mọi láng giềng ±1 bước theo cả `S` và `N` đều có `mean_X > 0` và `sharpe_X >= 50%` đỉnh.")

    lines.extend([
        "",
        "## Bước 3: Kiểm định EB (L(12/2019) -> L(12/2022))",
        "",
        f"- **Mốc ETF EB (`E1VFVN30`):** CAGR = `{ETF_EB_CAGR*100:.2f}%` (ngưỡng >= `{(ETF_EB_CAGR-0.01)*100:.2f}%`), MDD = `{ETF_EB_MDD*100:.2f}%` (ngưỡng <= `{(2/3*ETF_EB_MDD)*100:.2f}%`).",
    ])
    if eb_entry is None:
        lines.append("- **Kết quả:** Không chạy EB (dừng tại Bước 2 - cao nguyên).")
    else:
        lines.extend([
            f"- **Kết quả:** **{'ĐẠT' if eb_passed else 'TRƯỢT'}**",
            "",
            "| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            _format_report_row(_config_key(eb_entry["params"], prefix="EB_"), eb_entry["metrics"], eb_entry["sim"]),
            "",
        ])
        if eb_reasons:
            for r in eb_reasons:
                lines.append(f"  - Lý do trượt: {r}")

    lines.extend([
        "",
        "## Bước 4: DSR (n_trials = 9 + 9 + 30 = 48)",
        "",
        f"- **DSR (EA):** {'không tính' if dsr_val is None else f'{dsr_val:.4f} (ngưỡng >= 0.95 -> ' + ('ĐẠT' if dsr_val >= 0.95 else 'TRƯỢT') + ')'}",
        "",
        "## Kết luận Ứng Viên",
        "",
    ])
    if candidates:
        for c in candidates:
            lines.append(f"- `{c['idea_id']}`: `{c['params']}`, DSR = `{c['dsr']:.4f}`")
    else:
        lines.append("> **0 ứng viên** vượt qua đủ các cổng. Đóng giả thuyết, không nới cổng.")

    lines.append("")
    lines.append(f"- *Ghi chú cổng cũ tham khảo:* Calmar >= {OLD_CALMAR_GATE:.2f} không còn là cổng chính của EB.")
    return "\n".join(lines) + "\n"


def run_exploration(
    data_dir: Path | str = DATA_DIR,
    ledger_path: Path | str = LEDGER_PATH,
    candidates_path: Path | str = CANDIDATES_PATH,
    report_path: Path | str = REPORT_PATH,
    selections_path: Path | str = SELECTIONS_PATH,
    verify_step0: bool = True,
) -> dict[str, Any]:
    """Execute Brief 238 exploration workflow, delegating safely to 237 framework."""
    if "dot237" in Path(ledger_path).parts:
        raise ValueError(f"Refusing to write Dot 238 ledger into dot237 directory: {ledger_path}")
    assert_ledger_safety(ledger_path)

    return _run_exploration_237(
        data_dir=data_dir,
        ledger_path=ledger_path,
        candidates_path=candidates_path,
        report_path=report_path,
        selections_path=selections_path,
        verify_step0=verify_step0,
        idea_id=IDEA_ID,
        idea_type=IDEA_TYPE,
        seed=SEED_238,
        select_symbols_fn=select_highattn_symbols,
        dsr_fn=compute_step4_dsr_238,
        report_builder_fn=_build_report_markdown_238,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Brief 238 (High Attention Rotation).")
    parser.add_argument("--step0-only", action="store_true", help="Only run Step 0 universe count check.")
    args = parser.parse_args()

    if args.step0_only:
        run_step0_only(DATA_DIR)
        return 0

    run_exploration()
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
