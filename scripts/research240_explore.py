"""Exploration runner for Brief 240 (Short-Term Reversal Monthly Rotation).

Reuses the Step 0-4 exploration framework from scripts/research237_explore.py with:
- select_reversal_symbols (lowest RET_S first, A->Z tie-break)
- Grid: S in {5, 10, 20} x N in {10, 15, 20}
- idea_id = 'I1_REV', seed = 240
- DSR n_trials = 9 + PRIOR_NEGATIVE_FAMILIES(31) = 40
- Outputs under docs/research/dot240/
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
from scripts.research240_core import select_reversal_symbols

LEDGER_PATH = "docs/research/dot240/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot240/candidates.json"
REPORT_PATH = "docs/research/dot240/exploration_report.md"
SELECTIONS_PATH = "docs/research/dot240/selections.json"
DOT238_REPORT_PATH = "docs/research/dot238/exploration_report.md"

IDEA_ID = "I1_REV"
IDEA_TYPE = "REV"
SEED_240 = 240
PRIOR_NEGATIVE_FAMILIES_240 = 31

GRID: dict[str, list[int]] = {
    "S": [5, 10, 20],
    "N": [10, 15, 20],
}

# Grid-position correspondence between Dot 240 (S in {5, 10, 20}) and Dot 238 (S in {20, 40, 60}).
_S_240_TO_238_POS = {5: 20, 10: 40, 20: 60}

__all__ = [
    "CANDIDATES_PATH",
    "DATA_DIR",
    "DOT238_REPORT_PATH",
    "GRID",
    "IDEA_ID",
    "IDEA_TYPE",
    "LEDGER_PATH",
    "PRIOR_NEGATIVE_FAMILIES_240",
    "REPORT_PATH",
    "SEED_240",
    "SELECTIONS_PATH",
    "check_eb_gates",
    "check_plateau",
    "check_step0_universe",
    "compute_step4_dsr_240",
    "run_exploration",
    "run_step0_only",
    "select_best_ea_config",
]


def compute_step4_dsr_240(
    sharpe_x: float,
    n_months: int,
    skew: float,
    kurt: float,
    ea_sharpes: list[float],
) -> float:
    """Compute Step 4 DSR with n_trials = len(ea_sharpes) + 31 (§1)."""
    return compute_step4_dsr(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
        extra_trials=PRIOR_NEGATIVE_FAMILIES_240,
    )


def _parse_dot238_turnover_and_fees(
    dot238_report_path: Path | str = DOT238_REPORT_PATH,
) -> dict[str, tuple[str, str]]:
    """Read existing dot238 EA/EB turnover and annual fee columns verbatim from report."""
    p = Path(dot238_report_path)
    if not p.exists():
        return {}

    parsed: dict[str, tuple[str, str]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 15:
            continue
        m = re.search(r"(?:EB_)?S\d+_N\d+", cells[0])
        if not m:
            continue
        parsed[m.group(0)] = (cells[12], cells[13])
    return parsed


def _build_report_markdown_240(
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
    dot238_costs = _parse_dot238_turnover_and_fees()
    lines: list[str] = [
        "# Báo Cáo Khám Phá Đảo Chiều Ngắn Hạn (Brief 240)",
        "",
        "> [!CAUTION]",
        "> **CẢNH BÁO ĐA SO SÁNH & VƯỢT NGÂN SÁCH MỤC F:**",
        "> Đây là giả thuyết thứ 5 của tháng 11 (vượt ngân sách mục F, chủ dự án cho phép làm tiếp). Tổng số phép thử tính DSR là `N_trials = 9 + 31 = 40` (cộng 31 họ phép đo âm trước đó).",
        "",
        "> [!WARNING]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (CÓ LỢI CHO CHIẾN LƯỢC) & GẦN HỌ MOMENTUM:**",
        "> - **Thiên lệch sống sót có lợi cho đảo chiều ngắn hạn:** Dữ liệu `stocks_daily` gần như thiếu các mã đã huỷ niêm yết hoặc phá sản. Những mã giảm sâu không bao giờ hồi phục bị vắng mặt khỏi mẫu, khiến kết quả hồi cứu của chiến lược bắt đáy ngắn hạn (`RET_S` thấp nhất) bị lạc quan hoá một cách giả tạo.",
        "> - **Gần họ đã đo:** Gần họ momentum (đợt 102, chân trời khác) và cùng họ danh mục cổ phiếu xoay vòng tháng (đợt 193, 237, 238).",
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
        "### So sánh Turnover & Phí với Đợt 238 (EA)",
        "",
        "| Cấu hình (240) | Turnover tháng TB (240) | Phí / năm % NAV (240) | Cấu hình cùng S (238) | Turnover tháng TB (238 cùng S) | Phí / năm % NAV (238 cùng S) | Cấu hình cùng vị trí lưới (238) | Turnover tháng TB (238 vị trí) | Phí / năm % NAV (238 vị trí) |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for entry in ea_results:
        key = _config_key(entry["params"])
        s_ea = entry["sim"]
        exact_t238, exact_f238 = dot238_costs.get(key, ("—", "—"))
        exact_lbl = key if key in dot238_costs else "—"

        mapped_s = _S_240_TO_238_POS[int(entry["params"]["S"])]
        pos_key = f"S{mapped_s}_N{int(entry['params']['N'])}"
        pos_t238, pos_f238 = dot238_costs.get(pos_key, ("N/A", "N/A"))
        lines.append(
            f"| {key} | {s_ea['mean_turnover']*100:.2f}% | {s_ea['annual_fee_pct']*100:.2f}% | "
            f"{exact_lbl} | {exact_t238} | {exact_f238} | "
            f"{pos_key} | {pos_t238} | {pos_f238} |"
        )

    lines.extend([
        "",
        "#### Bảng số gốc Turnover & Phí chép từ `docs/research/dot238/exploration_report.md`",
        "",
        "| Cấu hình (238) | Turnover tháng TB (238) | Phí / năm % NAV (238) |",
        "|---|---|---|",
    ])
    for cfg_238, (t238, f238) in dot238_costs.items():
        lines.append(f"| {cfg_238} | {t238} | {f238} |")

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
        "## Bước 4: DSR (n_trials = 9 + 31 = 40)",
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
    """Execute Brief 240 exploration workflow, delegating safely to 237 framework."""
    ledger_parts = Path(ledger_path).parts
    other_batches = [part for part in ledger_parts if re.fullmatch(r"dot\d+", part) and part != "dot240"]
    if other_batches:
        raise ValueError(f"Refusing to write dot240 ledger into {other_batches[0]} directory: {ledger_path}")
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
        seed=SEED_240,
        select_symbols_fn=select_reversal_symbols,
        dsr_fn=compute_step4_dsr_240,
        report_builder_fn=_build_report_markdown_240,
        grid=GRID,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Brief 240 (Short-Term Reversal Rotation).")
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
