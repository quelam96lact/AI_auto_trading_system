"""Sàng lọc tín hiệu trong phiên trên VN30F1M_CONT (Brief 85 Task 3).

Thiết kế đã đăng ký trước:
- Nguồn: bars_derivative, symbol 'VN30F1M_CONT', đọc qua Storage.read_derivative_bars.
- In-Sample (IS): 2026-04-03 -> 2026-07-31.
- Niêm phong: Cấm đọc từ 2026-08-01 trở đi.
- Lọc phiên: Loại mọi phiên có số nến != 49.
- Đơn vị: ĐIỂM (không phải phần trăm) vì chuỗi Panama bảo toàn hiệu số giá.
- Không vượt phiên: Đặc trưng và mục tiêu chỉ tính trong cùng 1 phiên.
- Mục tiêu: fwd_1, fwd_3, fwd_6 (close[t+h] - close[t]).
- 6 đặc trưng: mom_1, mom_6, range_1, vol_ratio_12, dist_open, bar_index.
- Chốt an toàn: check_control_variable (intrabar vs ret_past_1, min_rho=0.50).
- Hoán vị khối: run_block_permutation_test (1 lần duy nhất cho cả 18 cặp, block_size_hours=49, n=1000).
- Gắn cờ: classify_signal (CO_TIN_HIEU / KHONG_TIN_HIEU).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import date, datetime
from typing import Any

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import pathlib

# Ensure repo root is in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_information import run_block_permutation_test
from scripts.leakage_audit import check_control_variable, compute_leakage_pair
from scripts.screen_vn_signal_candidates import classify_signal
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_series import DEFAULT_CONTINUOUS_SYMBOL
from trading.models import Bar
from trading.storage.db import Storage

# Cấu hình niêm phong và In-Sample đã đăng ký trước
IS_START_DATE = datetime(2026, 4, 3, 0, 0, 0, tzinfo=TZ)
IS_END_DATE = datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)
SEALED_DATE = datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)

FEATURE_NAMES = [
    "mom_1",
    "mom_6",
    "range_1",
    "vol_ratio_12",
    "dist_open",
    "bar_index",
]

TARGET_NAMES = [
    "fwd_1",
    "fwd_3",
    "fwd_6",
]

CONTROL_MIN_RHO_REQUIRED = 0.50
EXPECTED_BARS_PER_SESSION = 49


def validate_sealed_bars(
    bars: list[Bar],
    max_allowed_ts: datetime = SEALED_DATE,
) -> None:
    """Kiểm tra niêm phong dữ liệu: cấm tuyệt đối nến >= 2026-08-01 00:00 VN."""
    for b in bars:
        if b.ts >= max_allowed_ts:
            raise ValueError(
                f"Vi phạm niêm phong dữ liệu (Holdout Breach): "
                f"Nến {b.ts.isoformat()} >= mốc niêm phong {max_allowed_ts.isoformat()}"
            )


def load_is_bars(
    storage: Storage,
    symbol: str = DEFAULT_CONTINUOUS_SYMBOL,
    start: datetime = IS_START_DATE,
    end: datetime = IS_END_DATE,
) -> list[Bar]:
    """Tải dữ liệu In-Sample từ bars_derivative và áp đặt niêm phong nghiêm ngặt."""
    bars = storage.read_derivative_bars(symbol, start, end)
    validate_sealed_bars(bars, max_allowed_ts=end)
    return bars


def filter_and_group_sessions(
    bars: list[Bar],
    expected_bars_per_session: int = EXPECTED_BARS_PER_SESSION,
) -> tuple[dict[date, list[Bar]], list[tuple[date, int]]]:
    """Gom nhóm nến theo phiên giao dịch (giờ VN) và loại các phiên có số nến != 49."""
    by_date: dict[date, list[Bar]] = {}
    for b in bars:
        d = b.ts.astimezone(TZ).date()
        by_date.setdefault(d, []).append(b)

    valid_sessions: dict[date, list[Bar]] = {}
    dropped_sessions: list[tuple[date, int]] = []

    for d in sorted(by_date.keys()):
        session_bars = sorted(by_date[d], key=lambda x: x.ts)
        if len(session_bars) == expected_bars_per_session:
            valid_sessions[d] = session_bars
        else:
            dropped_sessions.append((d, len(session_bars)))

    return valid_sessions, dropped_sessions


def compute_session_features_and_targets(
    session_bars: list[Bar],
) -> list[dict[str, Any]]:
    """Tính 6 đặc trưng và 3 mục tiêu cho một phiên giao dịch (không vượt phiên).

    Quy ước nến trong phiên: t từ 0 đến N-1 (với N=49).
    - t: chỉ số nến trong phiên (bar_index = t).
    - open_0: open của nến đầu tiên (session_bars[0].open).

    Mục tiêu (điểm):
    - fwd_1: close[t+1] - close[t] nếu t+1 < N else None
    - fwd_3: close[t+3] - close[t] nếu t+3 < N else None
    - fwd_6: close[t+6] - close[t] nếu t+6 < N else None

    Đặc trưng (điểm):
    - mom_1: close[t] - close[t-1] nếu t >= 1 else None
    - mom_6: close[t] - close[t-6] nếu t >= 6 else None
    - range_1: high[t] - low[t]
    - vol_ratio_12: volume[t] / trung bình(volume[t-12 .. t-1]) nếu t >= 12 else None
    - dist_open: close[t] - open_0
    - bar_index: t (0..48)

    Biến đối chứng chốt an toàn:
    - intrabar: close[t] - open[t]
    - ret_past_1: close[t] - close[t-1] nếu t >= 1 else None
    """
    n = len(session_bars)
    open_0 = session_bars[0].open
    rows: list[dict[str, Any]] = []

    for t in range(n):
        b = session_bars[t]

        # Targets (không vượt phiên)
        fwd_1 = (session_bars[t + 1].close - b.close) if t + 1 < n else None
        fwd_3 = (session_bars[t + 3].close - b.close) if t + 3 < n else None
        fwd_6 = (session_bars[t + 6].close - b.close) if t + 6 < n else None

        # Features (không vượt phiên)
        mom_1 = (b.close - session_bars[t - 1].close) if t >= 1 else None
        mom_6 = (b.close - session_bars[t - 6].close) if t >= 6 else None
        range_1 = b.high - b.low

        if t >= 12:
            past_vols = [session_bars[k].volume for k in range(t - 12, t)]
            avg_vol = sum(past_vols) / 12.0
            vol_ratio_12 = (b.volume / avg_vol) if avg_vol > 0 else None
        else:
            vol_ratio_12 = None

        dist_open = b.close - open_0
        bar_index = t

        # Safety control variables
        intrabar = b.close - b.open
        ret_past_1 = (b.close - session_bars[t - 1].close) if t >= 1 else None

        row = {
            "ts": b.ts,
            "bar_index": bar_index,
            "mom_1": mom_1,
            "mom_6": mom_6,
            "range_1": range_1,
            "vol_ratio_12": vol_ratio_12,
            "dist_open": dist_open,
            "intrabar": intrabar,
            "ret_past_1": ret_past_1,
            "fwd_1": fwd_1,
            "fwd_3": fwd_3,
            "fwd_6": fwd_6,
        }
        rows.append(row)

    return rows


def build_intraday_panel(
    valid_sessions: dict[date, list[Bar]],
) -> list[dict[str, Any]]:
    """Tạo panel dữ liệu bằng cách nối các phiên hợp lệ theo thứ tự thời gian."""
    panel_rows: list[dict[str, Any]] = []
    for d in sorted(valid_sessions.keys()):
        s_rows = compute_session_features_and_targets(valid_sessions[d])
        panel_rows.extend(s_rows)
    return panel_rows


def run_vn30f_screening(
    rows: list[dict[str, Any]],
    n_permutations: int = 1000,
    seed: int = 42,
    min_control_rho: float = CONTROL_MIN_RHO_REQUIRED,
) -> dict[str, Any]:
    """Chạy quy trình sàng lọc 18 cặp tín hiệu theo thiết kế Brief 85.

    1. Kiểm tra chốt an toàn (intrabar vs ret_past_1, min_rho=0.50).
    2. Chạy hoán vị khối 49 nến tìm ngưỡng P95 FWER cho cả 18 cặp.
    3. Đo tương quan Spearman (rho_truoc, rho_sau, n_sau) và gắn cờ.
    """
    # 1. Chốt an toàn
    rho_ctrl, ok = check_control_variable(
        rows,
        control_feature="intrabar",
        past_ret_col="ret_past_1",
        future_ret_col="fwd_1",
        min_rho=min_control_rho,
    )

    if not ok:
        return {
            "control_ok": False,
            "rho_control": rho_ctrl,
            "threshold_p95": None,
            "results": [],
        }

    # 2. Hoán vị khối 49 hàng (1 phiên giao dịch)
    threshold_p95, _max_null_rhos = run_block_permutation_test(
        panel_rows=rows,
        n_permutations=n_permutations,
        block_size_hours=49,
        seed=seed,
        feature_names=FEATURE_NAMES,
        target_names=TARGET_NAMES,
    )

    # 3. Tính tương quan cho 18 cặp
    results: list[dict[str, Any]] = []
    for f in FEATURE_NAMES:
        feat_vals = [r.get(f) for r in rows]
        past_vals = [r.get("ret_past_1") for r in rows]
        for t in TARGET_NAMES:
            fut_vals = [r.get(t) for r in rows]
            rho_truoc, rho_sau, _n_truoc, n_sau = compute_leakage_pair(
                feat_vals, past_vals, fut_vals
            )
            flag = classify_signal(rho_sau, threshold_p95)
            results.append(
                {
                    "feature": f,
                    "target": t,
                    "rho_truoc": rho_truoc,
                    "rho_sau": rho_sau,
                    "n_sau": n_sau,
                    "flag": flag,
                }
            )

    return {
        "control_ok": True,
        "rho_control": rho_ctrl,
        "threshold_p95": threshold_p95,
        "results": results,
    }


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sàng lọc tín hiệu trong phiên trên VN30F1M_CONT (Brief 85)"
    )
    parser.add_argument(
        "--config", default="config/config.yaml", help="Đường dẫn file cấu hình"
    )
    args = parser.parse_args()

    _load_dotenv()
    app_cfg = load_config(args.config)
    db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
    storage = Storage(db_dsn)

    # 1. Tải dữ liệu IS và kiểm tra niêm phong
    bars = load_is_bars(storage, symbol=DEFAULT_CONTINUOUS_SYMBOL)
    valid_sessions, dropped_sessions = filter_and_group_sessions(bars)

    total_is_sessions = len(valid_sessions) + len(dropped_sessions)
    total_bars_used = sum(len(bs) for bs in valid_sessions.values())

    # Khẳng định mẫu số khớp thiết kế đã đăng ký trước
    assert total_is_sessions == 82, (
        f"Mẫu số phiên trước khi loại sai: {total_is_sessions} != 82"
    )
    assert len(bars) == 3970, f"Tổng số nến nạp trước khi loại sai: {len(bars)} != 3970"
    assert len(valid_sessions) == 81, (
        f"Mẫu số phiên hợp lệ sai: {len(valid_sessions)} != 81"
    )
    assert total_bars_used == 3969, (
        f"Tổng số nến hợp lệ sử dụng sai: {total_bars_used} != 3969"
    )

    # Dựng bảng đặc trưng
    rows = build_intraday_panel(valid_sessions)

    # Chạy sàng lọc
    screen_res = run_vn30f_screening(rows)

    # In báo cáo theo mục 3.3 nguyên văn
    print("=== BÁO CÁO SÀNG LỌC TÍN HIỆU TRONG PHIÊN VN30F1M_CONT (BRIEF 85) ===\n")
    print(f"- Số phiên IS: {total_is_sessions} phiên (từ 2026-04-03 đến 2026-07-31)")
    if dropped_sessions:
        dropped_str = ", ".join(
            f"{d.isoformat()} ({cnt} nến)" for d, cnt in dropped_sessions
        )
        print(f"- Số phiên bị loại: {len(dropped_sessions)} phiên [{dropped_str}]")
    else:
        print("- Số phiên bị loại: 0 phiên")
    print(
        f"- Số nến dùng: {total_bars_used} nến ({len(valid_sessions)} phiên x 49 nến)"
    )

    rho_ctrl = screen_res["rho_control"]
    ctrl_ok = screen_res["control_ok"]
    ctrl_str = "ĐẠT" if ctrl_ok else "THẤT BẠI"
    print(
        f"- rho đối chứng: {rho_ctrl:.4f} (yêu cầu > {CONTROL_MIN_RHO_REQUIRED:.2f}) -> Kết quả chốt an toàn: {ctrl_str}"
    )

    if not ctrl_ok:
        print(
            "\n[CẢNH BÁO NGUY HIỂM] Chốt an toàn bị vi phạm! Đường ống đo đang bị lệch pha / off-by-one."
        )
        print("DỪNG VÀ KHÔNG IN BẢNG KẾT QUẢ THEO QUY ĐỊNH BRIEF 85.")
        sys.exit(1)

    threshold = screen_res["threshold_p95"]
    print(f"- Ngưỡng P95 FWER (1000 hoán vị khối 49 nến): {threshold:.4f}\n")

    print(
        f"{'Đặc trưng':<15} | {'Khung':<6} | {'rho_truoc':<10} | {'rho_sau':<10} | {'n_sau':<6} | {'Cờ'}"
    )
    print("-" * 65)
    for r in screen_res["results"]:
        rho_tr_str = f"{r['rho_truoc']:+.4f}"
        rho_sa_str = f"{r['rho_sau']:+.4f}"
        print(
            f"{r['feature']:<15} | {r['target']:<6} | {rho_tr_str:<10} | {rho_sa_str:<10} | {r['n_sau']:<6} | {r['flag']}"
        )


if __name__ == "__main__":
    main()
