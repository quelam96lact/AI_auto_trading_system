"""Sàng lọc SMC (Smart Money Concepts) trên VN30F1M_CONT — Brief đợt 98.

Thiết kế ĐĂNG KÝ TRƯỚC (mọi tham số chốt trong brief, không đổi sau khi thấy dữ liệu):
- Nguồn: bars_derivative, symbol 'VN30F1M_CONT', qua load_is_bars() của Brief 85
  (hàm này đã áp niêm phong: cấm đọc từ 2026-08-01 trở đi).
- IS: 2026-04-03 -> 2026-07-31. Bỏ nến ATC 14:45 -> mỗi phiên 48 nến liên tục.
- Ba sự kiện, mỗi sự kiện là một cột +1 / -1 / 0, CHỈ dùng nến <= t trong CÙNG phiên:
  (a) sweep (N=12): quét đỉnh/đáy rồi đóng cửa quay đầu.
  (b) bos (fractal k=2): phá swing high/low đã xác nhận; swing tại j CHỈ biết từ nến j+2.
  (c) fvg: khoảng trống giá 3 nến (so sánh với nến t-2, bất đẳng thức NGẶT).
- Mục tiêu: fwd_1, fwd_3, fwd_6 (điểm) — dùng lại compute_session_features_and_targets().
- Chốt an toàn: check_control_variable (intrabar vs ret_past_1, min_rho=0.50). Trượt thì DỪNG.
- Ngưỡng FWER: run_block_permutation_test, 1000 hoán vị, khối 48 hàng (1 phiên), seed 42,
  gọi ĐÚNG MỘT LẦN cho cả 9 cặp. Không cộng thêm Bonferroni.
- Ngưỡng kinh tế (điều kiện thứ hai, độc lập thống kê): m = trung bình(fwd_k x dấu sự kiện)
  trên các nến có sự kiện != 0; ĐÁNG KỂ khi cờ = CO_TIN_HIEU VÀ |m| > chi phí một vòng.
- Chi phí một vòng (điểm): (derivative_side_cost(P,1,mở) + derivative_side_cost(P,1,đóng))
  / DERIVATIVE_CONTRACT_MULTIPLIER, với P = trung vị giá đóng cửa của IS.

Không đo order block (không có định nghĩa chặt duy nhất).
"""

from __future__ import annotations

import argparse
import io
import os
import pathlib
import statistics
import sys
from datetime import date
from typing import Any

# Ép UTF-8 cho stdout/stderr trên Windows (tránh UnicodeEncodeError) — như Brief 85
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_information import run_block_permutation_test
from scripts.leakage_audit import check_control_variable, compute_leakage_pair
from scripts.screen_vn30f_intraday import (
    CONTROL_MIN_RHO_REQUIRED,
    compute_session_features_and_targets,
    filter_and_group_sessions,
    load_is_bars,
)
from scripts.screen_vn_signal_candidates import classify_signal
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
    derivative_side_cost,
)
from trading.derivative_series import DEFAULT_CONTINUOUS_SYMBOL
from trading.models import Bar
from trading.storage.db import Storage

# --- Tham số đã đăng ký trước (KHÔNG đổi) -----------------------------------------
SWEEP_N = 12
FRACTAL_K = 2
SESS_LEN = 48
ATC_LABEL = "14:45"
EVENT_COLS = ["sweep", "bos", "fvg"]
TARGET_NAMES = ["fwd_1", "fwd_3", "fwd_6"]
EXPECTED_SESSIONS = 81
EXPECTED_ROWS = SESS_LEN * EXPECTED_SESSIONS  # 3.888
MIN_EVENTS = 30
N_PERMUTATIONS = 1000
SEED = 42


def _hhmm(bar: Bar) -> str:
    return bar.ts.astimezone(TZ).strftime("%H:%M")


def drop_atc_bars(bars: list[Bar], atc_label: str = ATC_LABEL) -> list[Bar]:
    """Bo nen ATC (14:45) — co che khop khac, khong phai khop lenh lien tuc."""
    return [b for b in bars if _hhmm(b) != atc_label]


def _la_swing_high(bars: list[Bar], j: int, k: int = FRACTAL_K) -> bool:
    """Nen j la swing high neu high[j] LON HON HAN high cua j-k..j+k (khong tinh j)."""
    if j - k < 0 or j + k >= len(bars):
        return False
    h = bars[j].high
    for m in range(j - k, j + k + 1):
        if m == j:
            continue
        if not h > bars[m].high:
            return False
    return True


def _la_swing_low(bars: list[Bar], j: int, k: int = FRACTAL_K) -> bool:
    """Nen j la swing low neu low[j] NHO HON HAN low cua j-k..j+k (khong tinh j)."""
    if j - k < 0 or j + k >= len(bars):
        return False
    lo = bars[j].low
    for m in range(j - k, j + k + 1):
        if m == j:
            continue
        if not lo < bars[m].low:
            return False
    return True


def compute_smc_columns(bars: list[Bar]) -> list[dict[str, Any]]:
    """Tinh ba cot su kien SMC cho MOT phien (khong vuot phien, khong nhin tuong lai).

    Tra ve danh sach theo tung nen, moi phan tu:
    - "sweep", "bos", "fvg": +1 / -1 / 0, hoac None khi chua du lich su.
    - "sweep_double": True khi nen quet CA HAI dau (duoc dem rieng theo muc 1.4).
    """
    n = len(bars)
    cols: list[dict[str, Any]] = [
        {"sweep": None, "bos": None, "fvg": None, "sweep_double": False} for _ in range(n)
    ]

    # (a) sweep — can t >= N
    for t in range(SWEEP_N, n):
        h = max(bars[m].high for m in range(t - SWEEP_N, t))
        low = min(bars[m].low for m in range(t - SWEEP_N, t))
        b = bars[t]
        quet_dinh = b.high > h and b.close < h
        quet_day = b.low < low and b.close > low
        if quet_dinh and quet_day:
            # "rau hai dau": tin hieu doi nghich nhau -> 0, dem rieng
            cols[t]["sweep"] = 0
            cols[t]["sweep_double"] = True
        elif quet_dinh:
            cols[t]["sweep"] = -1
        elif quet_day:
            cols[t]["sweep"] = 1
        else:
            cols[t]["sweep"] = 0

    # (b) bos — swing tai j CHI duoc biet tu nen j+2 tro di
    for t in range(n):
        s_h: float | None = None
        s_l: float | None = None
        for j in range(t - FRACTAL_K + 1):  # dieu kien j + k <= t
            if _la_swing_high(bars, j):
                s_h = bars[j].high  # swing gan nhat da xac nhan
            if _la_swing_low(bars, j):
                s_l = bars[j].low

        if t == 0 or (s_h is None and s_l is None):
            cols[t]["bos"] = None
            continue

        prev_close = bars[t - 1].close
        cur_close = bars[t].close
        val = 0
        if s_h is not None and prev_close <= s_h and cur_close > s_h:
            val = 1
        elif s_l is not None and prev_close >= s_l and cur_close < s_l:
            val = -1
        cols[t]["bos"] = val

    # (c) fvg — can t >= 2, so sanh NGAT voi nen t-2
    for t in range(2, n):
        if bars[t].low > bars[t - 2].high:
            cols[t]["fvg"] = 1
        elif bars[t].high < bars[t - 2].low:
            cols[t]["fvg"] = -1
        else:
            cols[t]["fvg"] = 0

    return cols


def add_smc_columns(
    base_rows: list[dict[str, Any]],
    bars: list[Bar],
) -> tuple[list[dict[str, Any]], int]:
    """Them ba cot sweep/bos/fvg vao hang cua compute_session_features_and_targets().

    Khong doi bat ky cot cu nao. Tra ve (hang da ghep, so nen "rau hai dau").
    """
    if len(base_rows) != len(bars):
        raise ValueError(f"So hang {len(base_rows)} != so nen {len(bars)}")
    cols = compute_smc_columns(bars)
    merged: list[dict[str, Any]] = []
    for row, col in zip(base_rows, cols, strict=True):
        new_row = dict(row)
        new_row["sweep"] = col["sweep"]
        new_row["bos"] = col["bos"]
        new_row["fvg"] = col["fvg"]
        merged.append(new_row)
    n_double = sum(1 for c in cols if c["sweep_double"])
    return merged, n_double


def build_smc_panel(
    valid_sessions: dict[date, list[Bar]],
) -> tuple[list[dict[str, Any]], int]:
    """Noi cac phien hop le theo thu tu thoi gian, moi phien tinh rieng (khong vuot phien)."""
    rows: list[dict[str, Any]] = []
    n_double = 0
    for d in sorted(valid_sessions.keys()):
        bars = valid_sessions[d]
        base = compute_session_features_and_targets(bars)
        merged, nd = add_smc_columns(base, bars)
        rows.extend(merged)
        n_double += nd
    return rows, n_double


def count_events(rows: list[dict[str, Any]], col: str) -> dict[str, int]:
    """Dem so lan xuat hien theo dau (bo qua None va 0)."""
    plus = sum(1 for r in rows if r.get(col) == 1)
    minus = sum(1 for r in rows if r.get(col) == -1)
    return {"plus": plus, "minus": minus, "total": plus + minus}


def event_mean_move(
    rows: list[dict[str, Any]], col: str, target: str
) -> float | None:
    """m = trung binh (fwd_k x dau su kien) tren cac nen co su kien != 0."""
    vals: list[float] = []
    for r in rows:
        ev = r.get(col)
        fw = r.get(target)
        if ev is None or ev == 0 or fw is None:
            continue
        vals.append(fw * ev)
    if not vals:
        return None
    return sum(vals) / len(vals)


def round_trip_cost_points(price: float) -> float:
    """Chi phi MOT VONG (mo + dong) tinh bang DIEM, dung ham cua trading/derivative_position."""
    mo = derivative_side_cost(price, 1, opening=True)
    dong = derivative_side_cost(price, 1, opening=False)
    return (mo + dong) / DERIVATIVE_CONTRACT_MULTIPLIER


def run_smc_screening(
    rows: list[dict[str, Any]],
    median_close: float,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = SEED,
    min_control_rho: float = CONTROL_MIN_RHO_REQUIRED,
) -> dict[str, Any]:
    """Chay sang loc 9 cap (3 su kien x 3 muc tieu) theo thiet ke dang ky truoc."""
    rho_ctrl, ctrl_ok = check_control_variable(
        rows,
        control_feature="intrabar",
        past_ret_col="ret_past_1",
        future_ret_col="fwd_1",
        min_rho=min_control_rho,
    )
    if not ctrl_ok:
        return {
            "control_ok": False,
            "rho_control": rho_ctrl,
            "threshold_p95": None,
            "cost_points": None,
            "results": [],
        }

    # Goi DUNG MOT LAN cho ca 9 cap: nguong P95 da hieu chinh da so sanh
    threshold_p95, _max_null_rhos = run_block_permutation_test(
        panel_rows=rows,
        n_permutations=n_permutations,
        block_size_hours=SESS_LEN,
        seed=seed,
        feature_names=EVENT_COLS,
        target_names=TARGET_NAMES,
    )

    cost = round_trip_cost_points(median_close)
    past_vals = [r.get("ret_past_1") for r in rows]

    results: list[dict[str, Any]] = []
    for f in EVENT_COLS:
        feat_vals = [r.get(f) for r in rows]
        for tgt in TARGET_NAMES:
            fut_vals = [r.get(tgt) for r in rows]
            rho_truoc, rho_sau, _n_truoc, n_sau = compute_leakage_pair(
                feat_vals, past_vals, fut_vals
            )
            flag = classify_signal(rho_sau, threshold_p95)
            m = event_mean_move(rows, f, tgt)
            dang_ke = flag == "CO_TIN_HIEU" and m is not None and abs(m) > cost
            results.append(
                {
                    "feature": f,
                    "target": tgt,
                    "rho_truoc": rho_truoc,
                    "rho_sau": rho_sau,
                    "n_sau": n_sau,
                    "flag": flag,
                    "m": m,
                    "dang_ke": dang_ke,
                }
            )

    return {
        "control_ok": True,
        "rho_control": rho_ctrl,
        "threshold_p95": threshold_p95,
        "cost_points": cost,
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


def _fmt(v: float | None, spec: str = "+.4f") -> str:
    return "None" if v is None else format(v, spec)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sàng lọc SMC trên VN30F1M_CONT (Brief đợt 98)"
    )
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn cấu hình")
    args = parser.parse_args()

    _load_dotenv()
    app_cfg = load_config(args.config)
    db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
    storage = Storage(db_dsn)

    # 1. Tai du lieu IS (niem phong ap trong load_is_bars) va bo nen ATC
    bars = load_is_bars(storage, symbol=DEFAULT_CONTINUOUS_SYMBOL)
    kept = drop_atc_bars(bars)
    valid_sessions, dropped_sessions = filter_and_group_sessions(
        kept, expected_bars_per_session=SESS_LEN
    )

    total_sessions_before = len(valid_sessions) + len(dropped_sessions)
    total_bars_used = sum(len(bs) for bs in valid_sessions.values())

    print("=== BÁO CÁO SÀNG LỌC SMC TRÊN VN30F1M_CONT (BRIEF ĐỢT 98) ===\n")
    print(f"- Nến nạp trước khi bỏ ATC: {len(bars)} nến")
    print(f"- Nến sau khi bỏ ATC 14:45: {len(kept)} nến")
    print(
        f"- Số phiên IS (trước khi lọc theo số nến): {total_sessions_before} phiên"
    )
    if dropped_sessions:
        dropped_str = ", ".join(
            f"{d.isoformat()} ({cnt} nến)" for d, cnt in dropped_sessions
        )
        print(f"- Số phiên bị loại: {len(dropped_sessions)} phiên [{dropped_str}]")
    else:
        print("- Số phiên bị loại: 0 phiên")
    print(f"- Số phiên dùng: {len(valid_sessions)} phiên")
    print(f"- Số nến dùng: {total_bars_used} nến ({len(valid_sessions)} phiên x {SESS_LEN} nến)")

    # Kiem tra moc da dang ky truoc: 81 phien / 3.888 hang. Khac thi DUNG, khong chay tiep.
    if len(valid_sessions) != EXPECTED_SESSIONS or total_bars_used != EXPECTED_ROWS:
        print(
            f"\n[DỪNG] Mốc đăng ký trước không khớp: cần {EXPECTED_SESSIONS} phiên / "
            f"{EXPECTED_ROWS} hàng, đo được {len(valid_sessions)} phiên / {total_bars_used} hàng."
        )
        print("Theo mục 4 của brief: DỪNG VÀ BÁO, không chạy tiếp.")
        sys.exit(1)

    rows, n_double = build_smc_panel(valid_sessions)
    median_close = statistics.median([b.close for b in kept])
    print(f"- Số hàng của bảng: {len(rows)}")
    print(f"- Trung vị giá đóng cửa IS (P): {median_close:.1f} điểm")

    # 2. Chay sang loc
    res = run_smc_screening(rows, median_close=median_close)

    rho_ctrl = res["rho_control"]
    ctrl_ok = res["control_ok"]
    ctrl_str = "ĐẠT" if ctrl_ok else "THẤT BẠI"
    print(
        f"- rho đối chứng (intrabar vs ret_past_1): {rho_ctrl:.4f} "
        f"(yêu cầu >= {CONTROL_MIN_RHO_REQUIRED:.2f}) -> Kết quả chốt an toàn: {ctrl_str}"
    )

    if not ctrl_ok:
        print(
            "\n[CẢNH BÁO NGUY HIỂM] Chốt an toàn bị vi phạm! Đường ống đo bị lệch pha / off-by-one."
        )
        print("DỪNG VÀ KHÔNG IN BẢNG KẾT QUẢ THEO QUY ĐỊNH BRIEF ĐỢT 98.")
        sys.exit(1)

    print(f"- Ngưỡng P95 FWER ({N_PERMUTATIONS} hoán vị khối {SESS_LEN} hàng, seed {SEED}): "
          f"{res['threshold_p95']:.4f}")
    print(f"- Chi phí một vòng (điểm): {res['cost_points']:.4f}\n")

    print(
        f"{'Sự kiện':<8} | {'Mục tiêu':<8} | {'rho_truoc':<10} | {'rho_sau':<10} | "
        f"{'n_sau':<6} | {'Cờ thống kê':<14} | {'m (điểm)':<10} | {'Chi phí':<8} | Kết luận"
    )
    print("-" * 110)
    for r in res["results"]:
        m_str = "None" if r["m"] is None else f"{r['m']:+.3f}"
        print(
            f"{r['feature']:<8} | {r['target']:<8} | {_fmt(r['rho_truoc']):<10} | "
            f"{_fmt(r['rho_sau']):<10} | {r['n_sau']:<6} | {r['flag']:<14} | "
            f"{m_str:<10} | {res['cost_points']:<8.4f} | "
            f"{'ĐÁNG KỂ' if r['dang_ke'] else 'KHÔNG'}"
        )

    # 3. Bang so su kien (muc 1.4)
    print("\n- Số sự kiện theo từng cột:")
    print(f"{'Sự kiện':<8} | {'+1':<8} | {'-1':<8} | {'Tổng':<8} | Ghi chú")
    print("-" * 70)
    for f in EVENT_COLS:
        c = count_events(rows, f)
        note = ""
        if c["plus"] < MIN_EVENTS or c["minus"] < MIN_EVENTS:
            note = "IT_SU_KIEN — sức mạnh thấp (dưới 30 ở một dấu, không kết luận)"
        print(f"{f:<8} | {c['plus']:<8} | {c['minus']:<8} | {c['total']:<8} | {note}")
    print(f"{'sweep*':<8} | {'':<8} | {'':<8} | {n_double:<8} | nến 'râu hai đầu' (quét cả hai đầu)")

    # 4. Ket luan theo muc 4 cua brief (khong tu dien giai them)
    dang_ke = [r for r in res["results"] if r["dang_ke"]]
    co_thong_tin = [r for r in res["results"] if r["flag"] == "CO_TIN_HIEU"]
    print("\n=== KẾT LUẬN (theo mục 4 của brief) ===")
    if not co_thong_tin:
        print("- Không cặp nào qua ngưỡng thống kê -> SMC dạng máy: KHÔNG có lợi thế sau chi phí trên VN30F1M IS.")
    elif not dang_ke:
        print("- Có cặp qua thống kê nhưng |m| dưới chi phí -> 'có thông tin nhưng không đủ trả phí'.")
    else:
        print("- Có cặp ĐÁNG KỂ:")
        for r in dang_ke:
            print(
                f"    {r['feature']} x {r['target']}: rho_sau {r['rho_sau']:+.4f}, "
                f"m {r['m']:+.3f} điểm, chi phí {res['cost_points']:.4f} điểm"
            )
        print("  KHÔNG mở tập niêm phong (từ 01/08), KHÔNG xây chiến lược. Chờ Claude quyết.")


if __name__ == "__main__":
    main()
