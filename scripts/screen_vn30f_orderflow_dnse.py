"""Công cụ sàng lọc order flow VN30F trên lịch sử lệnh khớp DNSE 25/03 -> 24/09/2026 (Brief đợt 186).

Chức năng:
1. Nạp và kiểm định phiên CHÍNH (2026-03-25 -> 2026-06-30) và LẶP LẠI (2026-07-01 -> 2026-09-24).
2. Kiểm đối chứng: Spearman rho giữa delta và close - open cùng nến trên CHÍNH > 0.3.
3. Tính hurdle kinh tế cố định từ trung vị giá close tập CHÍNH.
4. Phát hiện sự kiện một lần trên toàn bộ nến CHÍNH + LẶP LẠI, chia sự kiện theo session_id.
5. Sàng lọc 6 cặp (E1/E2/E3 x H15/H30) trên CHÍNH; kiểm k cặp đạt trên LẶP LẠI (alpha = 0.05/k, hurdle CHÍNH).
6. Tuyệt đối không bao giờ mở file có ngày >= IS_START_DATE (2026-09-25).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import zlib
from collections.abc import Sequence
from datetime import date, datetime
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

from scripts.fetch_dnse_vn30f_trades import (
    front_month_symbol,
    volume_continuity,
)
from scripts.screen_vn30f_orderbook import IS_START_DATE
from scripts.screen_vn30f_orderflow import (
    VALID_BARS_THRESHOLD,
    OrderFlowEvent,
    OrderFlowSession,
    block_bootstrap_p_value,
    build_footprint_bars_and_trades,
    build_price_lookup,
    calculate_event_targets,
    check_control_variable_orderflow,
    compute_economic_hurdle,
    detect_e1_events,
    detect_e2_events,
    detect_e3_events,
    evaluate_pair_criteria,
    filter_non_overlapping_events,
)

__all__ = [
    "EVENT_NAMES",
    "HORIZONS",
    "MAIN_END",
    "MAIN_START",
    "MAX_MISSING_CONTINUOUS_RATIO",
    "MIN_MAIN_SESSIONS",
    "MIN_REPEAT_SESSIONS",
    "REPEAT_END",
    "REPEAT_START",
    "block_bootstrap_p_value",
    "build_price_lookup",
    "calculate_event_targets",
    "check_control_variable_orderflow",
    "compute_economic_hurdle",
    "detect_e1_events",
    "detect_e2_events",
    "detect_e3_events",
    "dnse_row_to_message",
    "evaluate_pair_criteria",
    "evaluate_repeat_pair",
    "filter_non_overlapping_events",
    "load_dnse_sessions",
    "main",
    "run_dnse_screening",
]

# Hằng số đăng ký trước theo Brief 186
MAIN_START: date = date(2026, 3, 25)
MAIN_END: date = date(2026, 6, 30)
REPEAT_START: date = date(2026, 7, 1)
REPEAT_END: date = date(2026, 9, 24)

MAX_MISSING_CONTINUOUS_RATIO: float = 0.005  # 0.5%
MIN_MAIN_SESSIONS: int = 40
MIN_REPEAT_SESSIONS: int = 30

EVENT_NAMES: tuple[str, ...] = ("E1", "E2", "E3")
HORIZONS: tuple[int, ...] = (15, 30)


def dnse_row_to_message(row: dict[str, Any]) -> dict[str, Any]:
    """Chuyển đổi một dòng giao dịch DNSE sang định dạng tin TRADE của máy ghi SSI."""
    raw_side = str(row.get("side", "")).upper()
    if raw_side == "BUY":
        side = "B"
    elif raw_side == "SELL":
        side = "S"
    else:
        side = "U"

    raw_time = str(row.get("time", ""))
    t_str = raw_time[:19]

    return {
        "type": "TRADE",
        "price": float(row.get("match_price", 0.0)),
        "quantity": int(row.get("match_qtty", 0)),
        "side": side,
        "trading_time": t_str,
    }


def load_dnse_sessions(
    data_dir: Path | str = "data/dnse_trades",
    start: date = MAIN_START,
    end: date = MAIN_END,
) -> list[OrderFlowSession]:
    """Nạp danh sách các phiên DNSE trong khoảng [start, end].

    Quy tắc:
    - Duyệt ngày trong [start, end].
    - Ngày >= IS_START_DATE (2026-09-25) thì bỏ qua mà KHÔNG MỞ.
    - Mỗi ngày chỉ mở file <data_dir>/<front_month_symbol(ngày)>/<ngày>.jsonl.gz.
    - Áp quy tắc hợp lệ mục 1.2:
      1. Đọc hết, không lỗi file hỏng (EOFError, OSError, zlib.error, json decode).
      2. Khối lượng thiếu liên tục <= 0.5% tổng khối lượng.
      3. >= VALID_BARS_THRESHOLD (44/48) nến có giao dịch.
    """
    p_dir = Path(data_dir)
    sessions: list[OrderFlowSession] = []

    curr = start
    one_day = 1
    while curr <= end:
        # Bảo vệ niêm phong tuyệt đối: Không mở file >= IS_START_DATE
        if curr >= IS_START_DATE:
            curr = date.fromordinal(curr.toordinal() + one_day)
            continue

        sym = front_month_symbol(curr)
        fpath = p_dir / sym / f"{curr.isoformat()}.jsonl.gz"

        if not fpath.is_file():
            curr = date.fromordinal(curr.toordinal() + one_day)
            continue

        try:
            with gzip.open(fpath, "rt", encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]

            cont = volume_continuity(rows)
            tot_vol = cont["total_volume"]
            m_cont = cont["missing_continuous"]
            ratio = (m_cont / tot_vol) if tot_vol > 0 else 0.0

            messages = [dnse_row_to_message(r) for r in rows]
            stats: dict[str, Any] = {}
            bars, trades, stats = build_footprint_bars_and_trades(
                messages, curr, stats=stats
            )
            lookup = build_price_lookup(trades)
            active_bars = sum(1 for b in bars if b.trade_count > 0)

            if ratio > MAX_MISSING_CONTINUOUS_RATIO:
                is_valid = False
                reason = f"thiếu KL liên tục {ratio * 100:.1f}%"
            elif active_bars < VALID_BARS_THRESHOLD:
                is_valid = False
                reason = f"phiên thưa ({active_bars}/48 nến)"
            else:
                is_valid = True
                reason = None

        except (EOFError, OSError, zlib.error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            bars = []
            trades = []
            lookup = lambda _x: None
            is_valid = False
            reason = "file hỏng"
            active_bars = 0
            stats = {}

        sessions.append(
            OrderFlowSession(
                session_date=curr,
                contract=sym,
                file_path=fpath,
                bars=bars,
                clean_trades=trades,
                price_lookup=lookup,
                is_valid=is_valid,
                invalid_reason=reason,
                active_bars=active_bars,
                stats=stats,
            )
        )
        curr = date.fromordinal(curr.toordinal() + one_day)

    return sessions


def evaluate_repeat_pair(
    indep_events: Sequence[OrderFlowEvent],
    hurdle_main: float,
    p_val: float,
    k_passed: int,
) -> dict[str, Any]:
    """Đánh giá một cặp trên tập LẶP LẠI theo Brief 186 §1.4.

    Tiêu chuẩn:
    - Ngưỡng p một phía < 0.05 / k (với k là số cặp đạt ở CHÍNH).
    - Mean y >= hurdle của tập CHÍNH (không tính lại).
    - Không đòi hỏi >= 100 sự kiện.
    """
    alpha_threshold = 0.05 / k_passed if k_passed > 0 else 0.05
    n_events = len(indep_events)
    n_buy = sum(1 for e in indep_events if e.direction > 0)
    n_sell = sum(1 for e in indep_events if e.direction < 0)

    y_vals = [e.y for e in indep_events if e.y is not None]
    mean_y = float(np.mean(y_vals)) if y_vals else 0.0

    cond_stat = p_val < alpha_threshold
    cond_hurdle = mean_y >= hurdle_main
    passed = cond_stat and cond_hurdle

    return {
        "passed": passed,
        "n_events": n_events,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "mean_y": mean_y,
        "hurdle": hurdle_main,
        "p_val": p_val,
        "p_value": p_val,
        "alpha_threshold": alpha_threshold,
        "cond_stat": cond_stat,
        "cond_hurdle": cond_hurdle,
    }


def run_dnse_screening(data_dir: Path | str = "data/dnse_trades") -> dict[str, Any]:
    """Thực thi toàn bộ quy trình sàng lọc order flow DNSE (Brief đợt 186)."""
    print("=" * 96)
    print("  BRIEF ĐỢT 186 — SÀNG LỌC ORDER FLOW VN30F TRÊN LỊCH SỬ KHỚP LỆNH DNSE")
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

    # Kiểm đủ phiên
    if len(valid_main) < MIN_MAIN_SESSIONS or len(valid_repeat) < MIN_REPEAT_SESSIONS:
        print(
            f"\n[LỖI] KHÔNG ĐỦ PHIÊN: CHÍNH ({len(valid_main)}/{MIN_MAIN_SESSIONS}), "
            f"LẶP LẠI ({len(valid_repeat)}/{MIN_REPEAT_SESSIONS}).",
            file=sys.stderr,
        )
        return {"exit_code": 3}

    # 2. Kiểm đối chứng trên nến CHÍNH
    main_bars = [b for s in valid_main for b in s.bars]
    ctrl_ok, ctrl_rho = check_control_variable_orderflow(main_bars)
    print(f"\n[BIẾN ĐỐI CHỨNG] Spearman rho giữa delta và ret_same_5m trên CHÍNH: {ctrl_rho:.4f}")
    if not ctrl_ok:
        print(
            f"\n[LỖI] DỮ LIỆU SIDE KHÔNG ĐÁNG TIN: Spearman rho = {ctrl_rho:.4f} <= 0.3",
            file=sys.stderr,
        )
        return {"exit_code": 4}

    # 3. Tính hurdle kinh tế cố định từ trung vị giá close tập CHÍNH
    main_closes = [b.close for b in main_bars if b.close is not None]
    median_close = float(np.median(main_closes)) if main_closes else 1300.0
    hurdle = compute_economic_hurdle(median_close)
    print(f"[TIÊU CHUẨN KINH TẾ] Trung vị Close CHÍNH: {median_close:.2f} | Hurdle CHÍNH: {hurdle:.4f} điểm")

    # 4. Phát hiện sự kiện một lần trên toàn bộ nến CHÍNH + LẶP LẠI theo thời gian
    all_valid_sessions = valid_main + valid_repeat
    all_valid_bars = [b for s in all_valid_sessions for b in s.bars]

    events_by_type: dict[str, list[OrderFlowEvent]] = {
        "E1": detect_e1_events(all_valid_bars),
        "E2": detect_e2_events(all_valid_bars),
        "E3": detect_e3_events(all_valid_bars),
    }

    main_sids = {s.session_date for s in valid_main}
    repeat_sids = {s.session_date for s in valid_repeat}

    lookup_map = {s.session_date: s.price_lookup for s in all_valid_sessions}

    def global_price_lookup(x: datetime) -> float | None:
        fn = lookup_map.get(x.date())
        return fn(x) if fn else None

    # 5. Sàng lọc tập CHÍNH (6 cặp)
    print("\n" + "=" * 96)
    print("  BẢNG KẾT QUẢ TẬP CHÍNH (2026-03-25 -> 2026-06-30)")
    print(f"{'Cặp':<10} {'N':>5} {'N Mua':>7} {'N Bán':>7} {'Mean y':>10} {'Hurdle':>8} {'p-value':>10} {'Kết quả':>10}")
    print("-" * 96)

    results_main: dict[str, dict[str, Any]] = {}
    passed_pairs_main: list[str] = []

    for ev_name in EVENT_NAMES:
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
                alpha_threshold=0.05 / 6.0,
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

    # 6. Sàng lọc tập LẶP LẠI
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

    # 7. Phán quyết cuối cùng
    print("\n" + "=" * 96)
    print("  PHÁN QUYẾT CUỐI CÙNG BRIEF ĐỢT 186")
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
        "k_passed": k,
        "hurdle": hurdle,
        "ctrl_rho": ctrl_rho,
    }


def main(args: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Công cụ sàng lọc order flow VN30F trên lịch sử khớp lệnh DNSE (Brief đợt 186)"
    )
    parser.add_argument(
        "--data-dir",
        default="data/dnse_trades",
        help="Thư mục chứa dữ liệu DNSE (mặc định: data/dnse_trades)",
    )
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    res = run_dnse_screening(data_dir=parsed_args.data_dir)
    return int(res.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
