"""Công cụ sàng lọc 9 cặp đặc trưng sổ lệnh VN30F theo đăng ký trước ở Brief 162 & 163.

Quy trình:
1. Cổng ngày chống nhìn trước: chỉ chạy khi đã bước sang tập Holdout (>= 2026-12-01).
2. Kiểm tra biến đối chứng (OFI vs Delta Mid cùng phút): rho_truoc > 0.3.
3. Tính 9 cặp (3 đặc trưng x 3 chân trời) trên In-Sample (2026-09-25 đến 2026-11-30).
4. Kiểm định thống kê (Block Permutation Test) + Tiêu chuẩn kinh tế (Lợi nhuận trừ phí theo trung vị giá P).
5. Niêm phong Holdout: chỉ mở duy nhất 1 cặp khi thỏa mãn đủ 3 điều kiện (thuộc 9 cặp, ĐÁNG KỂ ở IS,
   và >= 30 phiên Holdout hợp lệ), bắt buộc ghi log vào docs/holdout-unlock-log.md TRƯỚC khi đọc phiên Holdout.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.audit_information import (
    calculate_percentile,
    fast_spearman_rank_correlation,
    run_block_permutation_test,
)
from scripts.build_orderbook_features import (
    MinuteRow,
    build_minute_features,
    iter_file_messages,
    session_date_from_filename,
)
from scripts.leakage_audit import check_control_variable
from trading.calendar_vn import TZ
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
    derivative_side_cost,
)

FEATURE_NAMES: tuple[str, ...] = ("imb_top1", "imb_top5", "ofi")
HORIZONS: tuple[int, ...] = (1, 5, 15)
TARGET_MID_NAMES: tuple[str, ...] = ("mid_chg_1", "mid_chg_5", "mid_chg_15")

IS_START_DATE: date = date(2026, 9, 25)
IS_END_DATE: date = date(2026, 11, 30)
HOLDOUT_START_DATE: date = date(2026, 12, 1)

MIN_IS_SESSIONS: int = 40
MIN_HOLDOUT_SESSIONS: int = 30
MIN_INDEP_EVENTS: int = 100
MIN_SIDE_EVENTS: int = 30
ALPHA_LEVEL: float = 0.05
ECONOMIC_HURDLE_FACTOR: float = 1.5
CONTROL_MIN_RHO: float = 0.3

DEFAULT_UNLOCK_LOG_PATH: Path = Path("docs/holdout-unlock-log.md")


@dataclass
class SessionData:
    session_date: date
    contract: str
    rows: list[MinuteRow]
    usable_count: int
    is_valid: bool
    usable_ratio: float


def compute_session_target_rows(sess: SessionData) -> list[dict[str, Any]]:
    """Tính các biến mục tiêu tương lai và biến đối chứng cho 240 phút trong phiên."""
    n = len(sess.rows)
    target_rows: list[dict[str, Any]] = []

    for t, r in enumerate(sess.rows):
        row_dict: dict[str, Any] = {
            "minute": r.minute,
            "session_date": sess.session_date,
            "contract": sess.contract,
            "minute_idx": t,
            "n_quote": r.n_quote,
            "n_trade": r.n_trade,
            "n_other": r.n_other,
            "mid_close": r.mid_close,
            "spread": r.spread,
            "imb_top1": r.imb_top1,
            "imb_top5": r.imb_top5,
            "ofi": r.ofi,
            "trade_qty": r.trade_qty,
        }

        # Biến đối chứng cùng phút: mid_chg_same_1m = mid(t) - mid(t-1)
        if t >= 1 and r.mid_close is not None and sess.rows[t - 1].mid_close is not None:
            row_dict["mid_chg_same_1m"] = r.mid_close - sess.rows[t - 1].mid_close
        else:
            row_dict["mid_chg_same_1m"] = None

        # Tính target cho các chân trời h in {1, 5, 15}
        for h in HORIZONS:
            entry_idx = t + 1
            exit_idx = t + 1 + h

            if exit_idx >= n:
                row_dict[f"fwd_buy_{h}"] = None
                row_dict[f"fwd_sell_{h}"] = None
                row_dict[f"mid_chg_{h}"] = None
                continue

            r_entry = sess.rows[entry_idx]
            r_exit = sess.rows[exit_idx]

            if (
                r_entry.mid_close is None
                or r_entry.spread is None
                or r_exit.mid_close is None
                or r_exit.spread is None
            ):
                row_dict[f"fwd_buy_{h}"] = None
                row_dict[f"fwd_sell_{h}"] = None
                row_dict[f"mid_chg_{h}"] = None
                continue

            entry_mid = r_entry.mid_close
            entry_spread = r_entry.spread
            exit_mid = r_exit.mid_close
            exit_spread = r_exit.spread

            ask_entry = entry_mid + entry_spread / 2.0
            bid_entry = entry_mid - entry_spread / 2.0
            ask_exit = exit_mid + exit_spread / 2.0
            bid_exit = exit_mid - exit_spread / 2.0

            row_dict[f"fwd_buy_{h}"] = bid_exit - ask_entry
            row_dict[f"fwd_sell_{h}"] = bid_entry - ask_exit
            row_dict[f"mid_chg_{h}"] = exit_mid - entry_mid

        target_rows.append(row_dict)

    return target_rows


def calculate_p90_thresholds(
    is_rows: list[dict[str, Any]],
    feature_names: Sequence[str] = FEATURE_NAMES,
) -> dict[str, float]:
    """Tính ngưỡng phân vị 90 của trị tuyệt đối đặc trưng chỉ trên tập In-Sample."""
    thresholds: dict[str, float] = {}
    for f in feature_names:
        vals = [abs(float(r[f])) for r in is_rows if r.get(f) is not None]
        if not vals:
            thresholds[f] = 0.0
        else:
            thresholds[f] = calculate_percentile(vals, 90.0)
    return thresholds


def select_independent_events(
    rows: list[dict[str, Any]],
    feat_name: str,
    p90: float,
    h: int,
) -> list[dict[str, Any]]:
    """Chọn các sự kiện độc lập tham lam theo thời gian để tránh chồng lấn cửa sổ vị thế."""
    events: list[dict[str, Any]] = []
    last_exit_time: datetime | None = None

    for r in rows:
        val = r.get(feat_name)
        if val is None:
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue

        if abs(fval) < p90:
            continue

        fwd_buy = r.get(f"fwd_buy_{h}")
        fwd_sell = r.get(f"fwd_sell_{h}")
        if fwd_buy is None or fwd_sell is None:
            continue

        if fval > 0:
            direction = 1
            realized_ret = float(fwd_buy)
        elif fval < 0:
            direction = -1
            realized_ret = float(fwd_sell)
        else:
            continue

        m_time: datetime = r["minute"]
        entry_time = m_time + timedelta(minutes=1)
        exit_time = entry_time + timedelta(minutes=h)

        if last_exit_time is not None and entry_time <= last_exit_time:
            # Đang trong khoảng giữ vị thế của sự kiện trước -> bỏ qua
            continue

        event = {
            "minute": m_time,
            "session_date": r.get("session_date"),
            "contract": r.get("contract"),
            "minute_idx": r.get("minute_idx"),
            "feat_name": feat_name,
            "feat_val": fval,
            "direction": direction,
            "realized_ret": realized_ret,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "h": h,
        }
        events.append(event)
        last_exit_time = exit_time

    return events


def compute_roundtrip_cost(price: float) -> float:
    """Tính chi phí 2 chiều (mở + đóng) theo điểm VN30F tại mức giá tương ứng."""
    open_cost = derivative_side_cost(price, 1, opening=True)
    close_cost = derivative_side_cost(price, 1, opening=False)
    total_vnd = open_cost + close_cost
    return float(total_vnd / DERIVATIVE_CONTRACT_MULTIPLIER)


def evaluate_pairs(
    is_rows: list[dict[str, Any]],
    p90_thresholds: dict[str, float],
    perm_results: tuple[float, list[float]],
    mid_price: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Đánh giá 9 cặp đặc trưng x chân trời theo tiêu chuẩn thống kê và kinh tế."""
    if mid_price is None:
        mids = [r["mid_close"] for r in is_rows if r.get("mid_close") is not None]
        if not mids:
            raise ValueError("Không có giá mid hợp lệ trong tập dữ liệu để tính chi phí")
        mid_price = calculate_percentile(mids, 50.0)

    threshold_95, max_null_rhos = perm_results
    roundtrip_cost = compute_roundtrip_cost(mid_price)
    hurdle = ECONOMIC_HURDLE_FACTOR * roundtrip_cost

    table: dict[str, dict[str, Any]] = {}

    for f in FEATURE_NAMES:
        p90_val = p90_thresholds.get(f, 0.0)
        for h in HORIZONS:
            pair_name = f"{f}_fwd_{h}"
            target_name = f"mid_chg_{h}"

            # Lọc các cặp không None để tính Spearman correlation
            x_v: list[float] = []
            y_v: list[float] = []
            for r in is_rows:
                xv = r.get(f)
                yv = r.get(target_name)
                if xv is not None and yv is not None:
                    x_v.append(float(xv))
                    y_v.append(float(yv))

            if len(x_v) >= 10:
                rho = fast_spearman_rank_correlation(x_v, y_v)
            else:
                rho = 0.0

            # Tính p-value từ phân phối max_null_rhos
            if max_null_rhos:
                n_extreme = sum(1 for null_r in max_null_rhos if null_r >= abs(rho))
                p_val = n_extreme / len(max_null_rhos)
            else:
                p_val = 1.0

            # Chọn sự kiện độc lập
            events = select_independent_events(is_rows, f, p90_val, h)
            n_indep = len(events)
            n_buy = sum(1 for e in events if e["direction"] == 1)
            n_sell = sum(1 for e in events if e["direction"] == -1)
            side_warning = (n_buy < MIN_SIDE_EVENTS or n_sell < MIN_SIDE_EVENTS)

            mean_m = (sum(e["realized_ret"] for e in events) / n_indep) if n_indep > 0 else 0.0

            # Tiêu chuẩn thống kê & kinh tế (Brief 162 §1.5, §5)
            # Thống kê: |rho| > ngưỡng P95 và rho > 0 (đúng chiều giả thuyết đăng ký trước)
            stat_ok = (abs(rho) > threshold_95) and (rho > 0.0)
            econ_ok = mean_m >= hurdle

            if n_indep < MIN_INDEP_EVENTS:
                label = "THIẾU SỨC MẠNH"
            elif stat_ok and econ_ok:
                label = "ĐÁNG KỂ"
            elif stat_ok and not econ_ok:
                label = "có thông tin nhưng không đủ trả phí"
            else:
                label = "KHÔNG ĐÁNG KỂ"

            table[pair_name] = {
                "feature": f,
                "horizon": h,
                "rho": rho,
                "p_value": p_val,
                "null_threshold_95": threshold_95,
                "n_indep": n_indep,
                "n_buy": n_buy,
                "n_sell": n_sell,
                "side_warning": side_warning,
                "mean_m": mean_m,
                "roundtrip_cost": roundtrip_cost,
                "hurdle": hurdle,
                "label": label,
            }

    return table


def _write_holdout_log(
    log_path: Path | str,
    pair_name: str,
    is_sessions_count: int,
    holdout_sessions_count: int,
) -> None:
    """Ghi nhật ký mở niêm phong Holdout trước khi đọc phiên Holdout."""
    log_p = Path(log_path)
    log_p.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(TZ).isoformat()
    with open(log_p, "a", encoding="utf-8") as lf:
        lf.write(
            f"- [{now_str}] MỞ NIÊM PHONG HOLDOUT cho cặp: {pair_name} "
            f"(IS sessions: {is_sessions_count}, Holdout sessions: {holdout_sessions_count})\n"
        )


def _evaluate_holdout_pair(
    holdout_rows: list[dict[str, Any]],
    pair_name: str,
    p90_threshold: float,
    hurdle: float,
    seed: int = 42,
) -> dict[str, Any]:
    """Đánh giá cặp được chỉ định trên tập Holdout với P90 và chi phí lấy từ IS."""
    parts = pair_name.rsplit("_fwd_", 1)
    if len(parts) != 2:
        raise ValueError(f"Tên cặp không hợp lệ: {pair_name}")
    feat_name = parts[0]
    h = int(parts[1])
    target_name = f"mid_chg_{h}"

    x_h = [r.get(feat_name) for r in holdout_rows if r.get(feat_name) is not None and r.get(target_name) is not None]
    y_h = [r.get(target_name) for r in holdout_rows if r.get(feat_name) is not None and r.get(target_name) is not None]
    rho_h = fast_spearman_rank_correlation(x_h, y_h) if len(x_h) >= 10 else 0.0

    # Chạy hoán vị trên Holdout để tính p-value một phía cho cặp này
    perm_hold = run_block_permutation_test(
        holdout_rows,
        n_permutations=1000,
        block_size_hours=240,
        seed=seed,
        feature_names=[feat_name],
        target_names=[target_name],
    )
    _threshold_95_h, max_null_rhos_h = perm_hold
    if max_null_rhos_h:
        # p-value một phía cho rho > 0
        n_extreme = sum(1 for null_r in max_null_rhos_h if null_r >= rho_h)
        p_val_h = n_extreme / len(max_null_rhos_h)
    else:
        p_val_h = 1.0

    events_h = select_independent_events(holdout_rows, feat_name, p90_threshold, h)
    n_h = len(events_h)
    n_b = sum(1 for e in events_h if e["direction"] == 1)
    n_s = sum(1 for e in events_h if e["direction"] == -1)
    mean_m_h = (sum(e["realized_ret"] for e in events_h) / n_h) if n_h > 0 else 0.0

    # Brief 162 §5: Cần p < 0.05 một phía VÀ m >= 1.5 x chi phí
    passed = (p_val_h < ALPHA_LEVEL) and (rho_h > 0.0) and (mean_m_h >= hurdle)

    return {
        "pair": pair_name,
        "rho": rho_h,
        "p_value": p_val_h,
        "n_indep": n_h,
        "n_buy": n_b,
        "n_sell": n_s,
        "mean_m": mean_m_h,
        "hurdle": hurdle,
        "passed": passed,
    }


def run_screening(
    sessions: list[SessionData],
    n_permutations: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Thực hiện toàn bộ quy trình sàng lọc 9 cặp đặc trưng trên tập In-Sample."""
    valid_is_sessions = [s for s in sessions if s.is_valid and IS_START_DATE <= s.session_date <= IS_END_DATE]
    invalid_sessions = [s for s in sessions if not s.is_valid]

    # Cổng số lượng phiên IS: >= 40 phiên hợp lệ
    if len(valid_is_sessions) < MIN_IS_SESSIONS:
        return {
            "status": "STOPPED_INSUFFICIENT_IS_SESSIONS",
            "control_ok": None,
            "rho_control": None,
            "table": None,
            "evaluated_holdout_pair": None,
            "holdout_result": None,
            "n_is_sessions": len(valid_is_sessions),
            "n_holdout_sessions": 0,
            "n_invalid_sessions": len(invalid_sessions),
            "contracts_is": sorted({s.contract for s in valid_is_sessions}),
            "contracts_holdout": [],
        }

    # Xây dựng các hàng target cho IS
    is_rows: list[dict[str, Any]] = []
    for s in valid_is_sessions:
        is_rows.extend(compute_session_target_rows(s))

    # Kiểm tra biến đối chứng (OFI vs mid_chg_same_1m)
    rho_control, control_ok = check_control_variable(
        is_rows,
        control_feature="ofi",
        past_ret_col="mid_chg_same_1m",
        future_ret_col="mid_chg_1",
        min_rho=CONTROL_MIN_RHO,
    )
    if not control_ok:
        return {
            "status": "STOPPED_CONTROL_VARIABLE_FAILED",
            "control_ok": False,
            "rho_control": rho_control,
            "table": None,
            "evaluated_holdout_pair": None,
            "holdout_result": None,
            "n_is_sessions": len(valid_is_sessions),
            "n_holdout_sessions": 0,
            "n_invalid_sessions": len(invalid_sessions),
            "contracts_is": sorted({s.contract for s in valid_is_sessions}),
            "contracts_holdout": [],
        }

    # Tính ngưỡng P90 chỉ từ IS
    p90_thresholds = calculate_p90_thresholds(is_rows, FEATURE_NAMES)

    # Tính chi phí & hurdle từ TRUNG VỊ mid_close của IS
    mids = [r["mid_close"] for r in is_rows if r.get("mid_close") is not None]
    if not mids:
        raise ValueError("Không có giá mid hợp lệ trong tập IS để tính chi phí")
    mid_median = calculate_percentile(mids, 50.0)
    cost = compute_roundtrip_cost(mid_median)
    hurdle = ECONOMIC_HURDLE_FACTOR * cost

    # Chạy Block Permutation Test với khối 240 hàng (1 phiên)
    perm_results = run_block_permutation_test(
        is_rows,
        n_permutations=n_permutations,
        block_size_hours=240,
        seed=seed,
        feature_names=list(FEATURE_NAMES),
        target_names=list(TARGET_MID_NAMES),
    )

    # Đánh giá 9 cặp trên IS
    table = evaluate_pairs(is_rows, p90_thresholds, perm_results, mid_price=mid_median)

    # Tính tỷ lệ phút bị loại (None) trên toàn IS
    total_minutes_is = len(is_rows)
    dropped_minutes_is = sum(1 for r in is_rows if r.get("mid_close") is None)
    dropped_ratio_is = (dropped_minutes_is / total_minutes_is * 100.0) if total_minutes_is else 0.0

    return {
        "status": "SUCCESS",
        "control_ok": True,
        "rho_control": rho_control,
        "p90_thresholds": p90_thresholds,
        "roundtrip_cost": cost,
        "hurdle": hurdle,
        "table": table,
        "evaluated_holdout_pair": None,
        "holdout_result": None,
        "n_is_sessions": len(valid_is_sessions),
        "n_holdout_sessions": 0,
        "n_invalid_sessions": len(invalid_sessions),
        "dropped_minutes_ratio": dropped_ratio_is,
        "contracts_is": sorted({s.contract for s in valid_is_sessions}),
        "contracts_holdout": [],
    }


def count_holdout_files(data_dir: Path | str = "data/orderbook") -> int:
    """Đếm số lượng file phiên Holdout (>= 2026-12-01) trên đĩa chỉ qua tên file trong các thư mục con, KHÔNG mở file."""
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return 0
    count = 0
    for item in sorted(p_dir.iterdir()):
        if item.is_dir():
            for f in sorted(item.glob("*.jsonl.gz")):
                s_date = session_date_from_filename(f)
                if s_date is not None and s_date >= HOLDOUT_START_DATE:
                    count += 1
    return count


def load_holdout_sessions(data_dir: Path | str = "data/orderbook") -> list[SessionData]:
    """Đọc các phiên Holdout (>= 2026-12-01). CHỈ được gọi sau khi kiểm tra đủ điều kiện và ghi log."""
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return []
    date_to_contract: dict[date, str] = {}
    file_entries: list[tuple[date, str, Path]] = []
    for item in sorted(p_dir.iterdir()):
        if item.is_dir():
            contract_name = item.name
            for f in sorted(item.glob("*.jsonl.gz")):
                s_date = session_date_from_filename(f)
                if s_date is None or s_date < HOLDOUT_START_DATE:
                    continue
                if s_date in date_to_contract:
                    raise ValueError(
                        f"Trùng ngày {s_date} giữa các hợp đồng Holdout: '{date_to_contract[s_date]}' và '{contract_name}'"
                    )
                date_to_contract[s_date] = contract_name
                file_entries.append((s_date, contract_name, f))

    sessions: list[SessionData] = []
    for s_date, contract_name, fpath in sorted(file_entries, key=lambda x: x[0]):
        stats: dict[str, Any] = {}
        rows = build_minute_features(iter_file_messages(fpath), s_date, stats=stats)
        usable = sum(1 for r in rows if r.usable())
        ratio = usable / 240.0 if len(rows) == 240 else 0.0
        sessions.append(
            SessionData(
                session_date=s_date,
                contract=contract_name,
                rows=rows,
                usable_count=usable,
                is_valid=(ratio >= 0.90),
                usable_ratio=ratio,
            )
        )
    return sessions


def load_all_sessions(
    data_dir: Path | str = "data/orderbook",
) -> list[SessionData]:
    """Đọc các file phiên In-Sample từ cấu trúc thư mục con data_dir/<mã hợp đồng>/<ngày>.jsonl.gz.

    - LUÔN LUÔN bỏ qua phiên >= 01/12/2026 (KHÔNG mở file, KHÔNG gọi build_minute_features).
    - File nằm ngay thư mục gốc (không trong thư mục con) -> bỏ qua và in cảnh báo.
    - Nếu có 2 thư mục con chứa cùng 1 ngày -> dừng và raise ValueError.
    """
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return []

    date_to_contract: dict[date, str] = {}
    file_entries: list[tuple[date, str, Path]] = []

    # Duyệt qua các thư mục con
    for item in sorted(p_dir.iterdir()):
        if item.is_dir():
            contract_name = item.name
            for f in sorted(item.glob("*.jsonl.gz")):
                s_date = session_date_from_filename(f)
                if s_date is None:
                    continue
                if s_date in date_to_contract:
                    raise ValueError(
                        f"Trùng ngày {s_date} giữa các hợp đồng: '{date_to_contract[s_date]}' và '{contract_name}'"
                    )
                date_to_contract[s_date] = contract_name
                file_entries.append((s_date, contract_name, f))
        elif item.is_file() and item.name.endswith(".jsonl.gz"):
            print(
                f"[CẢNH BÁO] Bỏ qua file '{item.name}' nằm ngay thư mục gốc (yêu cầu cấu trúc <mã hợp đồng>/<ngày>.jsonl.gz)",
                file=sys.stderr,
            )

    sessions: list[SessionData] = []
    for s_date, contract_name, fpath in sorted(file_entries, key=lambda x: x[0]):
        # NIÊM PHONG: Tuyệt đối KHÔNG mở file / gọi build_minute_features cho phiên Holdout
        if s_date >= HOLDOUT_START_DATE:
            continue

        stats: dict[str, Any] = {}
        rows = build_minute_features(iter_file_messages(fpath), s_date, stats=stats)
        usable = sum(1 for r in rows if r.usable())
        ratio = usable / 240.0 if len(rows) == 240 else 0.0
        sessions.append(
            SessionData(
                session_date=s_date,
                contract=contract_name,
                rows=rows,
                usable_count=usable,
                is_valid=(ratio >= 0.90),
                usable_ratio=ratio,
            )
        )

    return sessions


def format_screening_report(res: dict[str, Any]) -> str:
    """Định dạng báo cáo kết quả sàng lọc 9 cặp đặc trưng theo Brief 163 §3 & Brief 162."""
    lines: list[str] = []
    lines.append("=" * 95)
    lines.append("=== BÁO CÁO SÀNG LỌC 9 CẶP ĐẶC TRƯNG SỔ LỆNH VN30F (BRIEF 162 & 163) ===")
    lines.append("=" * 95)
    lines.append(f"Trạng thái: {res['status']}")
    if res.get("rejection_reason"):
        lines.append(f"Lý do từ chối: {res['rejection_reason']}")

    lines.append(
        f"Số phiên In-Sample: {res.get('n_is_sessions', 0)} (Mã HĐ: {', '.join(res.get('contracts_is', [])) or 'None'}) | "
        f"Số phiên Holdout: {res.get('n_holdout_sessions', 0)} (Mã HĐ: {', '.join(res.get('contracts_holdout', [])) or 'None'}) | "
        f"Số phiên bị loại: {res.get('n_invalid_sessions', 0)}"
    )
    lines.append(f"Tỷ lệ phút bị loại (None) trên In-Sample: {res.get('dropped_minutes_ratio', 0.0):.2f}%")

    rho_ctrl = res.get("rho_control")
    rho_ctrl_str = f"{rho_ctrl:.4f}" if rho_ctrl is not None else "N/A"
    ctrl_label = "ĐẠT" if res.get("control_ok") is True else ("TRƯỢT" if res.get("control_ok") is False else "CHƯA ĐO")
    lines.append(f"Kiểm tra biến đối chứng (OFI vs Delta Mid 1m): rho = {rho_ctrl_str} -> {ctrl_label} (ngưỡng: > 0.3000)")

    if res.get("table") is None:
        lines.append(f"[DỪNG] Không thể xuất bảng kết quả do: {res['status']}")
        lines.append("=" * 95)
        return "\n".join(lines)

    lines.append(
        f"Chi phí 2 chiều (trung vị giá P): {res['roundtrip_cost']:.3f} điểm | "
        f"Ngưỡng kinh tế Hurdle (1.5x chi phí): {res['hurdle']:.3f} điểm"
    )
    lines.append("")
    lines.append(
        f"{'Cặp đặc trưng':<18} | {'Spearman rho':<12} | {'p-value':<9} | {'N (Tổng/M/B)':<15} | {'Lợi nhuận m':<12} | {'Nhãn kết luận':<35}"
    )
    lines.append("-" * 110)

    for pair_name, r in res["table"].items():
        n_str = f"{r['n_indep']} ({r['n_buy']}/{r['n_sell']})"
        label_str = r["label"]
        if r.get("side_warning"):
            label_str += " [CẢNH BÁO: Phía < 30]"
        lines.append(
            f"{pair_name:<18} | {r['rho']:>12.4f} | {r['p_value']:>9.4f} | {n_str:>15} | {r['mean_m']:>12.4f} | {label_str:<35}"
        )

    if res.get("evaluated_holdout_pair"):
        lines.append("")
        lines.append(f"=== KẾT QUẢ MỞ NIÊM PHONG HOLDOUT: {res['evaluated_holdout_pair']} ===")
        hr = res.get("holdout_result") or {}
        lines.append(f"- Spearman rho Holdout : {hr.get('rho', 0.0):.4f} (p-value một phía: {hr.get('p_value', 1.0):.4f})")
        lines.append(f"- Số sự kiện độc lập   : {hr.get('n_indep', 0)} (Mua: {hr.get('n_buy', 0)} | Bán: {hr.get('n_sell', 0)})")
        lines.append(f"- Lợi nhuận trung bình m: {hr.get('mean_m', 0.0):.4f} điểm (Hurdle từ IS: {hr.get('hurdle', 0.0):.4f} điểm)")
        lines.append(f"- Kết luận Holdout      : {'ĐẠT' if hr.get('passed') else 'KHÔNG ĐẠT'}")

    lines.append("=" * 95)
    return "\n".join(lines)


def main(
    today: date | None = None,
    args: list[str] | None = None,
    unlock_log_path: Path | str | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Sàng lọc 9 cặp đặc trưng sổ lệnh VN30F (Brief 162 & 163)"
    )
    parser.add_argument("--data-dir", default="data/orderbook", help="Thư mục dữ liệu sổ lệnh")
    parser.add_argument("--unlock-holdout-pair", default=None, help="Tên cặp mở niêm phong Holdout")
    parser.add_argument("--permutations", type=int, default=1000, help="Số lần hoán vị")

    effective_args = args if args is not None else ([] if today is not None else sys.argv[1:])
    parsed_args = parser.parse_args(effective_args)

    if today is None:
        today = datetime.now(TZ).date()

    # CỔNG NGÀY CHỐNG NHÌN TRƯỚC (Brief 163 §3)
    if today < HOLDOUT_START_DATE:
        print(
            f"[BẢO VỆ CHỐNG NHÌN TRƯỚC] Ngày hiện tại ({today}) chưa tới ngày kết thúc In-Sample "
            f"({HOLDOUT_START_DATE}). Dừng toàn bộ chương trình để bảo vệ tính vô tư của tập dữ liệu.",
            file=sys.stderr,
        )
        return 2

    # 1. Chạy trọn phép đo IS trước
    is_sessions = load_all_sessions(parsed_args.data_dir)
    res = run_screening(
        sessions=is_sessions,
        n_permutations=parsed_args.permutations,
    )

    # 2. Xử lý mở niêm phong Holdout (nếu có cờ)
    if parsed_args.unlock_holdout_pair is not None:
        if res["status"] != "SUCCESS" or res["table"] is None:
            print(format_screening_report(res))
            return 1

        pair_name = parsed_args.unlock_holdout_pair
        cond1_valid_name = pair_name in res["table"]
        cond2_is_significant = cond1_valid_name and (res["table"][pair_name]["label"] == "ĐÁNG KỂ")
        n_holdout_files = count_holdout_files(parsed_args.data_dir)
        cond3_enough_files = n_holdout_files >= MIN_HOLDOUT_SESSIONS

        unlock_rejected_reason: str | None = None
        if not cond1_valid_name:
            unlock_rejected_reason = f"Tên cặp '{pair_name}' không thuộc 9 cặp hợp lệ."
        elif not cond2_is_significant:
            unlock_rejected_reason = f"Cặp '{pair_name}' không đạt nhãn 'ĐÁNG KỂ' trên tập In-Sample (nhãn hiện tại: '{res['table'][pair_name]['label']}')."
        elif not cond3_enough_files:
            unlock_rejected_reason = f"Tập Holdout chưa đủ 30 file phiên trên đĩa (hiện có: {n_holdout_files} file)."

        if unlock_rejected_reason is not None:
            res["status"] = "REJECTED_HOLDOUT_UNLOCK"
            res["rejection_reason"] = unlock_rejected_reason
            print(format_screening_report(res))
            return 1

        # ĐỦ CẢ 3 ĐIỀU KIỆN: GHI LOG TRƯỚC
        log_p = unlock_log_path or DEFAULT_UNLOCK_LOG_PATH
        _write_holdout_log(
            log_path=log_p,
            pair_name=pair_name,
            is_sessions_count=res["n_is_sessions"],
            holdout_sessions_count=n_holdout_files,
        )

        # RỒI MỚI ĐỌC CÁC PHIÊN NIÊM PHONG
        holdout_sessions = load_holdout_sessions(parsed_args.data_dir)
        valid_holdout = [s for s in holdout_sessions if s.is_valid]

        if len(valid_holdout) < MIN_HOLDOUT_SESSIONS:
            res["status"] = "STOPPED_INSUFFICIENT_VALID_HOLDOUT_SESSIONS"
            res["rejection_reason"] = (
                f"KHÔNG ĐỦ PHIÊN NIÊM PHONG HỢP LỆ (yêu cầu >= 30 phiên >= 90% phút dùng được, "
                f"hiện chỉ có {len(valid_holdout)}/{len(holdout_sessions)} phiên hợp lệ)."
            )
            res["n_holdout_sessions"] = len(valid_holdout)
            res["contracts_holdout"] = sorted({s.contract for s in valid_holdout})
            print(format_screening_report(res))
            return 1

        # Đủ >= 30 phiên hợp lệ -> Đánh giá cặp trên Holdout
        holdout_rows: list[dict[str, Any]] = []
        for s in valid_holdout:
            holdout_rows.extend(compute_session_target_rows(s))

        parts = pair_name.rsplit("_fwd_", 1)
        feat_name = parts[0]
        holdout_res = _evaluate_holdout_pair(
            holdout_rows=holdout_rows,
            pair_name=pair_name,
            p90_threshold=res["p90_thresholds"][feat_name],
            hurdle=res["hurdle"],
        )
        res["evaluated_holdout_pair"] = pair_name
        res["holdout_result"] = holdout_res
        res["n_holdout_sessions"] = len(valid_holdout)
        res["contracts_holdout"] = sorted({s.contract for s in valid_holdout})

    print(format_screening_report(res))
    if res["status"] != "SUCCESS":
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
