"""Công cụ sàng lọc E2/E3 order flow VN30F với ngưỡng tương đối, đo trên DNSE (Brief đợt 187).

Chức năng:
1. Áp ngưỡng imbalance tương đối (min_vol=p95, denom_floor=p50 của pool 5 phiên trước) cho E3.
2. Áp ngưỡng delta tương đối (|delta| >= p25 của 5 phiên trước) cho E2.
3. Chặn suy biến: nếu tỷ lệ nến imbalance cả hai phía trên CHÍNH > 50% thì loại E3.
4. Sàng lọc 4 cặp (E2_H15, E2_H30, E3_H15, E3_H30) trên CHÍNH (alpha = 0.05 / 4).
5. Kiểm k cặp đạt ở CHÍNH trên LẶP LẠI (alpha = 0.05 / k, hurdle CHÍNH).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# Ép mã hoá UTF-8 trên Windows để tránh lỗi UnicodeEncodeError
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream and getattr(_stream, "encoding", None) and _stream.encoding.lower() not in ("utf-8", "utf8"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.screen_vn30f_orderflow import (
    BarSummary,
    OrderFlowEvent,
    block_bootstrap_p_value,
    calculate_event_targets,
    check_control_variable_orderflow,
    compute_economic_hurdle,
    detect_e3_events,
    evaluate_pair_criteria,
    filter_non_overlapping_events,
    imbalance_levels,
)
from scripts.screen_vn30f_orderflow_dnse import (
    MAIN_END,
    MAIN_START,
    MIN_MAIN_SESSIONS,
    MIN_REPEAT_SESSIONS,
    REPEAT_END,
    REPEAT_START,
    evaluate_repeat_pair,
    load_dnse_sessions,
)
from trading.metrics import calculate_percentile

__all__ = [
    "ALPHA_MAIN",
    "E2_DELTA_PCT",
    "E3_DENOM_FLOOR_PCT",
    "E3_MIN_VOL_PCT",
    "HORIZONS",
    "MAIN_END",
    "MAIN_START",
    "MAX_BOTH_SIDES_SHARE",
    "MIN_MAIN_SESSIONS",
    "MIN_REPEAT_SESSIONS",
    "REPEAT_END",
    "REPEAT_START",
    "WARMUP_SESSIONS",
    "apply_relative_imbalance_pct",
    "both_sides_share",
    "detect_e2_events_pct",
    "detect_e3_events",
    "evaluate_pair_criteria",
    "evaluate_repeat_pair",
    "load_dnse_sessions",
    "main",
    "run_187",
]

# Hằng số đăng ký trước theo Brief 187 §2.1
E3_MIN_VOL_PCT: float = 95.0
E3_DENOM_FLOOR_PCT: float = 50.0
E2_DELTA_PCT: float = 25.0
ALPHA_MAIN: float = 0.05 / 4.0
MAX_BOTH_SIDES_SHARE: float = 0.5
WARMUP_SESSIONS: int = 5
HORIZONS: tuple[int, ...] = (15, 30)


def apply_relative_imbalance_pct(
    bars: Sequence[Any],
    min_vol_pct: float = E3_MIN_VOL_PCT,
    floor_pct: float = E3_DENOM_FLOOR_PCT,
) -> None:
    """Áp ngưỡng imbalance tương đối cho từng phiên D từ 5 phiên hợp lệ liền trước.

    min_vol(D) = percentile(pool, min_vol_pct); denom_floor(D) = percentile(pool, floor_pct).
    5 phiên đầu không có ngưỡng => imbalance = None.
    """
    sessions_order: list[Any] = []
    bars_by_session: dict[Any, list[Any]] = defaultdict(list)
    for b in bars:
        s_date = b.session_id
        if s_date not in bars_by_session:
            sessions_order.append(s_date)
        bars_by_session[s_date].append(b)

    for s_idx, d_date in enumerate(sessions_order):
        if s_idx < WARMUP_SESSIONS:
            for b in bars_by_session[d_date]:
                b.ask_k_min = None
                b.ask_k_max = None
                b.bid_k_min = None
                b.bid_k_max = None
            continue

        hist_sessions = sessions_order[s_idx - WARMUP_SESSIONS : s_idx]
        pool: list[float] = []
        for h_id in hist_sessions:
            for b in bars_by_session[h_id]:
                fp = getattr(b, "fp", None)
                if fp:
                    for buy_val, sell_val in fp.values():
                        if buy_val > 0.0:
                            pool.append(float(buy_val))
                        if sell_val > 0.0:
                            pool.append(float(sell_val))

        if not pool:
            for b in bars_by_session[d_date]:
                b.ask_k_min = None
                b.ask_k_max = None
                b.bid_k_min = None
                b.bid_k_max = None
            continue

        min_vol_d = calculate_percentile(pool, min_vol_pct)
        denom_floor_d = calculate_percentile(pool, floor_pct)

        for b in bars_by_session[d_date]:
            fp = getattr(b, "fp", None)
            if fp:
                ask_ks, bid_ks = imbalance_levels(
                    fp,
                    ratio=3.0,
                    min_vol=min_vol_d,
                    denom_floor=denom_floor_d,
                )
                b.ask_k_min = ask_ks[0] if ask_ks else None
                b.ask_k_max = ask_ks[-1] if ask_ks else None
                b.bid_k_min = bid_ks[0] if bid_ks else None
                b.bid_k_max = bid_ks[-1] if bid_ks else None
            else:
                b.ask_k_min = None
                b.ask_k_max = None
                b.bid_k_min = None
                b.bid_k_max = None


def detect_e2_events_pct(
    bars: Sequence[BarSummary],
    pct: float = E2_DELTA_PCT,
) -> list[OrderFlowEvent]:
    """Phát hiện sự kiện E2 (phân kỳ delta trong nến) theo phân vị tương đối pct của 5 phiên trước."""
    events: list[OrderFlowEvent] = []
    sessions_order: list[Any] = []
    bars_by_session: dict[Any, list[BarSummary]] = defaultdict(list)
    for b in bars:
        if b.session_id not in bars_by_session:
            sessions_order.append(b.session_id)
        bars_by_session[b.session_id].append(b)

    for s_idx, s_id in enumerate(sessions_order):
        if s_idx < WARMUP_SESSIONS:
            continue
        hist_sessions = sessions_order[s_idx - WARMUP_SESSIONS : s_idx]
        deltas_pool: list[float] = []
        for h_id in hist_sessions:
            for b in bars_by_session[h_id]:
                if b.close is not None and b.open is not None:
                    deltas_pool.append(abs(b.delta))
        if not deltas_pool:
            continue
        threshold = calculate_percentile(deltas_pool, pct)

        for curr in bars_by_session[s_id]:
            if curr.close is None or curr.open is None:
                continue
            if abs(curr.delta) < threshold:
                continue
            if curr.close == curr.open:
                continue
            if curr.delta > 0 and curr.close < curr.open:
                d = +1
            elif curr.delta < 0 and curr.close > curr.open:
                d = -1
            else:
                continue

            events.append(
                OrderFlowEvent(
                    event_type="E2",
                    direction=d,
                    session_id=curr.session_id,
                    block_id=curr.block_id,
                    bar_idx=curr.bar_idx,
                    t_end=curr.t_end,
                    close=curr.close,
                )
            )
    return events


def both_sides_share(
    bars: Sequence[Any],
    skip_sessions: Iterable[Any] | None = None,
) -> float:
    """Tỷ lệ nến có giá mà có cả ask_k_min lẫn bid_k_min, bỏ các phiên trong skip_sessions."""
    skip_set = set(skip_sessions) if skip_sessions is not None else set()
    total_priced = 0
    both_count = 0
    for b in bars:
        if b.session_id in skip_set:
            continue
        if b.close is not None and b.open is not None:
            total_priced += 1
            if getattr(b, "ask_k_min", None) is not None and getattr(b, "bid_k_min", None) is not None:
                both_count += 1
    if total_priced == 0:
        return 0.0
    return float(both_count / total_priced)


def run_187(data_dir: Path | str = "data/dnse_trades") -> dict[str, Any]:
    """Thực thi toàn bộ quy trình sàng lọc đợt 187."""
    print("=" * 96)
    print("  BRIEF ĐỢT 187 — SÀNG LỌC E2/E3 ORDER FLOW VN30F VỚI NGƯỠNG TƯƠNG ĐỐI (DNSE)")
    print(f"  Tập CHÍNH  : {MAIN_START} -> {MAIN_END} (yêu cầu >= {MIN_MAIN_SESSIONS} phiên hợp lệ)")
    print(f"  Tập LẶP LẠI: {REPEAT_START} -> {REPEAT_END} (yêu cầu >= {MIN_REPEAT_SESSIONS} phiên hợp lệ)")
    print("=" * 96)

    # 1. Nạp phiên CHÍNH và LẶP LẠI
    main_sessions = load_dnse_sessions(data_dir=data_dir, start=MAIN_START, end=MAIN_END)
    repeat_sessions = load_dnse_sessions(data_dir=data_dir, start=REPEAT_START, end=REPEAT_END)

    valid_main = [s for s in main_sessions if s.is_valid]
    invalid_main = [s for s in main_sessions if not s.is_valid]

    valid_repeat = [s for s in repeat_sessions if s.is_valid]
    invalid_repeat = [s for s in repeat_sessions if not s.is_valid]

    print(f"\n[TẬP CHÍNH] Tổng phiên: {len(main_sessions)} | Hợp lệ: {len(valid_main)} | Không hợp lệ: {len(invalid_main)}")
    for inv in invalid_main:
        print(f"  * Ngày {inv.session_date} ({inv.contract}): {inv.invalid_reason}")

    print(f"\n[TẬP LẶP LẠI] Tổng phiên: {len(repeat_sessions)} | Hợp lệ: {len(valid_repeat)} | Không hợp lệ: {len(invalid_repeat)}")
    for inv in invalid_repeat:
        print(f"  * Ngày {inv.session_date} ({inv.contract}): {inv.invalid_reason}")

    if len(valid_main) < MIN_MAIN_SESSIONS or len(valid_repeat) < MIN_REPEAT_SESSIONS:
        print(
            f"\n[LỖI] KHÔNG ĐỦ PHIÊN: CHÍNH ({len(valid_main)}/{MIN_MAIN_SESSIONS}), "
            f"LẶP LẠI ({len(valid_repeat)}/{MIN_REPEAT_SESSIONS}).",
            file=sys.stderr,
        )
        return {"exit_code": 3}

    # 2. Kiểm đối chứng
    main_bars = [b for s in valid_main for b in s.bars]
    ctrl_ok, ctrl_rho = check_control_variable_orderflow(main_bars)
    print(f"\n[BIẾN ĐỐI CHỨNG] Spearman rho giữa delta và ret_same_5m trên CHÍNH: {ctrl_rho:.4f}")
    if not ctrl_ok:
        print(
            f"\n[LỖI] DỮ LIỆU SIDE KHÔNG ĐÁNG TIN: Spearman rho = {ctrl_rho:.4f} <= 0.3",
            file=sys.stderr,
        )
        return {"exit_code": 4}

    # 3. Tính hurdle
    main_closes = [b.close for b in main_bars if b.close is not None]
    median_close = float(np.median(main_closes)) if main_closes else 1300.0
    hurdle = compute_economic_hurdle(median_close)
    print(f"[TIÊU CHUẨN KINH TẾ] Trung vị Close CHÍNH: {median_close:.2f} | Hurdle CHÍNH: {hurdle:.4f} điểm")

    # 4. Áp imbalance tương đối trên toàn bộ nến hợp lệ CHÍNH + LẶP LẠI
    all_valid_sessions = valid_main + valid_repeat
    all_valid_bars = [b for s in all_valid_sessions for b in s.bars]

    apply_relative_imbalance_pct(
        all_valid_bars,
        min_vol_pct=E3_MIN_VOL_PCT,
        floor_pct=E3_DENOM_FLOOR_PCT,
    )

    # 5. In both_sides_share của CHÍNH, bỏ 5 phiên khởi động; > 50% thì loại E3
    main_sessions_order = [s.session_date for s in valid_main]
    skip_warmup = set(main_sessions_order[:WARMUP_SESSIONS])
    share = both_sides_share(main_bars, skip_sessions=skip_warmup)
    print(f"\n[CHẶN SUY BIẾN] Tỷ lệ nến CHÍNH có imbalance cả 2 phía (bỏ {WARMUP_SESSIONS} phiên đầu): {share * 100:.1f}%")

    exclude_e3 = share > MAX_BOTH_SIDES_SHARE
    if exclude_e3:
        print(
            f"[CẢNH BÁO] Tỷ lệ imbalance 2 phía ({share * 100:.1f}%) > {MAX_BOTH_SIDES_SHARE * 100:.0f}%. "
            f"Loại E3 khỏi sàng lọc.",
            file=sys.stderr,
        )
        eval_events = ["E2"]
    else:
        eval_events = ["E2", "E3"]

    # 6. Phát hiện sự kiện E2/E3
    events_by_type: dict[str, list[OrderFlowEvent]] = {
        "E2": detect_e2_events_pct(all_valid_bars, pct=E2_DELTA_PCT),
        "E3": [] if exclude_e3 else detect_e3_events(all_valid_bars),
    }

    main_sids = {s.session_date for s in valid_main}
    repeat_sids = {s.session_date for s in valid_repeat}
    lookup_map = {s.session_date: s.price_lookup for s in all_valid_sessions}

    def global_price_lookup(x: datetime) -> float | None:
        fn = lookup_map.get(x.date())
        return fn(x) if fn else None

    # 7. In bảng CHÍNH (alpha = ALPHA_MAIN = 0.05 / 4)
    print("\n" + "=" * 96)
    print("  BẢNG KẾT QUẢ TẬP CHÍNH (2026-03-25 -> 2026-06-30)")
    print(f"  Ngưỡng alpha = {ALPHA_MAIN:.4f} (Bonferroni 0.05 / 4)")
    print(f"{'Cặp':<10} {'N':>5} {'N Mua':>7} {'N Bán':>7} {'Mean y':>10} {'Hurdle':>8} {'p-value':>10} {'Kết quả':>10}")
    print("-" * 96)

    results_main: dict[str, dict[str, Any]] = {}
    passed_pairs_main: list[str] = []

    for ev_name in eval_events:
        all_evs = events_by_type[ev_name]
        main_evs = [e for e in all_evs if e.session_id in main_sids]

        for h in HORIZONS:
            pair_key = f"{ev_name}_H{h}"
            ev_targets = calculate_event_targets(main_evs, global_price_lookup, h_minutes=h)
            indep = filter_non_overlapping_events(ev_targets, h_minutes=h)
            p_val, _ = block_bootstrap_p_value(indep, n_bootstrap=2000, seed=42)
            res = evaluate_pair_criteria(
                indep,
                hurdle=hurdle,
                control_rho=ctrl_rho,
                p_val=p_val,
                alpha_threshold=ALPHA_MAIN,
            )
            results_main[pair_key] = res
            verdict = "ĐẠT" if res["passed"] else "TRƯỢT"
            if res["passed"]:
                passed_pairs_main.append(pair_key)

            print(
                f"{pair_key:<10} {res['n_events']:>5} {res['n_buy']:>7} {res['n_sell']:>7} "
                f"{res['mean_y']:>10.4f} {res['hurdle']:>8.4f} {res['p_value']:>10.4f} {verdict:>10}"
            )

    print("=" * 96)

    k = len(passed_pairs_main)
    results_repeat: dict[str, dict[str, Any]] = {}
    passed_pairs_final: list[str] = []

    # 8. Sàng lọc tập LẶP LẠI
    print("\n" + "=" * 96)
    print("  BẢNG KẾT QUẢ TẬP LẶP LẠI (2026-07-01 -> 2026-09-24)")
    if k == 0:
        print("LẶP LẠI: không có cặp nào để kiểm")
        print("=" * 96)
    else:
        print(f"  Số cặp đạt ở CHÍNH k = {k} (Ngưỡng alpha = 0.05 / {k} = {0.05 / k:.4f})")
        print(f"{'Cặp':<10} {'N':>5} {'N Mua':>7} {'N Bán':>7} {'Mean y':>10} {'Hurdle':>8} {'p-value':>10} {'Kết quả':>10}")
        print("-" * 96)

        for pair_key in passed_pairs_main:
            ev_name, h_str = pair_key.split("_")
            h = int(h_str.replace("H", ""))

            all_evs = events_by_type[ev_name]
            repeat_evs = [e for e in all_evs if e.session_id in repeat_sids]

            ev_targets = calculate_event_targets(repeat_evs, global_price_lookup, h_minutes=h)
            indep = filter_non_overlapping_events(ev_targets, h_minutes=h)
            p_val, _ = block_bootstrap_p_value(indep, n_bootstrap=2000, seed=42)
            res_rep = evaluate_repeat_pair(
                indep,
                hurdle_main=hurdle,
                p_val=p_val,
                k_passed=k,
            )
            results_repeat[pair_key] = res_rep
            verdict = "ĐẠT" if res_rep["passed"] else "TRƯỢT"
            if res_rep["passed"]:
                passed_pairs_final.append(pair_key)

            print(
                f"{pair_key:<10} {res_rep['n_events']:>5} {res_rep['n_buy']:>7} {res_rep['n_sell']:>7} "
                f"{res_rep['mean_y']:>10.4f} {res_rep['hurdle']:>8.4f} {res_rep['p_value']:>10.4f} {verdict:>10}"
            )
        print("=" * 96)

    # 9. Phán quyết cuối cùng
    print("\n" + "=" * 96)
    print("  PHÁN QUYẾT CUỐI CÙNG BRIEF ĐỢT 187")
    if passed_pairs_final:
        print(f"  CÁC CẶP ĐẠT CẢ HAI TẬP: {', '.join(passed_pairs_final)}")
    else:
        print("  KẾT LUẬN: Không có cặp nào ĐẠT cả hai tập CHÍNH và LẶP LẠI.")
    print("=" * 96)

    return {
        "exit_code": 0,
        "results_main": results_main,
        "results_repeat": results_repeat,
        "passed_main": passed_pairs_main,
        "passed_final": passed_pairs_final,
        "both_sides_share": share,
        "exclude_e3": exclude_e3,
        "k_passed": k,
        "hurdle": hurdle,
        "ctrl_rho": ctrl_rho,
    }


def main(args: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sàng lọc E2/E3 order flow VN30F với ngưỡng tương đối trên DNSE (Brief 187)"
    )
    parser.add_argument(
        "--data-dir",
        default="data/dnse_trades",
        help="Thư mục chứa dữ liệu DNSE (mặc định: data/dnse_trades)",
    )
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    res = run_187(data_dir=parsed_args.data_dir)
    return int(res.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
