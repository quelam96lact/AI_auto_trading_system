"""Cong cu sang loc 6 cap order flow footprint tren BTCUSDT perp (Brief dot 183).

- Du lieu: data/crypto_footprint/BTCUSDT/<YYYY-MM>.csv.gz
- Cua so CHINH: 2023-01-01 -> 2024-12-31.
- Cua so LAP LAI: 2025-01-01 -> 2026-08-31.
- Cong ngay: Tu choi chay truoc 2026-11-01 (ngay VN).
- Khong sua file khac, khong ghi DB, khong dat lenh.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import math
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.screen_vn30f_orderflow import (
    BarSummary,
    OrderFlowEvent,
    block_bootstrap_p_value,
    calculate_event_targets,
    detect_e1_events,
    detect_e2_events,
    detect_e3_events,
    filter_non_overlapping_events,
    imbalance_levels,
)
from trading.calendar_vn import TZ

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

__all__ = [
    "ALPHA_PER_PAIR_INITIAL",
    "CONTROL_MIN_RHO",
    "DEFAULT_DATA_DIR",
    "ECONOMIC_HURDLE",
    "EVENT_NAMES",
    "HOLDOUT_START_DATE",
    "HORIZONS",
    "MAIN_END_DATE",
    "MAIN_START_DATE",
    "MIN_DIRECTION_EVENTS",
    "MIN_TOTAL_EVENTS",
    "REPEAT_END_DATE",
    "REPEAT_START_DATE",
    "build_crypto_price_lookup",
    "check_control_variable_crypto",
    "crypto_block_end_fn",
    "detect_e1_events",
    "detect_e2_events",
    "detect_e3_events",
    "evaluate_crypto_pair",
    "get_crypto_block_id",
    "imbalance_levels",
    "load_crypto_footprint_bars",
    "main",
    "run_crypto_screening_pipeline",
]

# --- Hang so dang ky truoc (§1.3, §1.4) -------------------------------------------

EVENT_NAMES: tuple[str, ...] = ("E1", "E2", "E3")
HORIZONS: tuple[int, ...] = (15, 30)

HOLDOUT_START_DATE: date = date(2026, 11, 1)

MAIN_START_DATE: date = date(2023, 1, 1)
MAIN_END_DATE: date = date(2024, 12, 31)

REPEAT_START_DATE: date = date(2025, 1, 1)
REPEAT_END_DATE: date = date(2026, 8, 31)

# Chi phi & Hurdle (§1.4): 1.5 * (0.0010 taker + 0.0004 slippage) = 0.0021
ECONOMIC_HURDLE: float = 0.0021

CONTROL_MIN_RHO: float = 0.3
MIN_TOTAL_EVENTS: int = 100
MIN_DIRECTION_EVENTS: int = 30
ALPHA_PER_PAIR_INITIAL: float = 0.05 / 6.0

DEFAULT_DATA_DIR = Path("data/crypto_footprint/BTCUSDT")


# --- 1. Khung 8 gio funding & Ket thuc khung (§1.2, §1.3) -------------------------


def get_crypto_block_id(dt: datetime) -> str:
    """Tra ve ID khung 8 gio funding: YYYY-MM-DD_00, _08, hoac _16."""
    h = dt.hour
    if h < 8:
        suffix = "00_08"
    elif h < 16:
        suffix = "08_16"
    else:
        suffix = "16_24"
    return f"{dt.date().isoformat()}_{suffix}"


def crypto_block_end_fn(event: Any) -> datetime:
    """Moc ket thuc khung 8 gio funding chua su kien (UTC), suy tu block_id.

    Dung block_id chu khong dung gio cua t_end: nen 07:55 co t_end = 08:00 nhung thuoc
    khung 00-08, nen het khung la 08:00 (khong phai 16:00).
    """
    day_str, _, end_h = event.block_id.split("_")
    d = date.fromisoformat(day_str)
    return datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(hours=int(end_h))


# --- 2. Doc file tom tat & Dung danh sach BarSummary (§1.2) -----------------------


def load_crypto_footprint_bars(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[BarSummary]:
    """Doc cac file <YYYY-MM>.csv.gz trong data_dir thanh danh sach BarSummary.

    - CVD duoc reset luc 00:00 UTC moi ngay (= delta cua nen dau tien trong ngay).
    - Nen khong co giao dich duoc giu voi close=None.
    """
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return []

    files = sorted(p_dir.glob("*.csv.gz"))
    bars: list[BarSummary] = []
    cur_session: date | None = None
    accum_cvd: float = 0.0

    for fpath in files:
        # Lay YYYY-MM tu ten file de kiem tra khoang ngay
        stem = fpath.name.replace(".csv.gz", "")
        parts = stem.split("-")
        if len(parts) == 2:
            try:
                f_year = int(parts[0])
                f_month = int(parts[1])
                f_start = date(f_year, f_month, 1)
                if f_month == 12:
                    f_end = date(f_year + 1, 1, 1) - timedelta(days=1)
                else:
                    f_end = date(f_year, f_month + 1, 1) - timedelta(days=1)

                if start_date and f_end < start_date:
                    continue
                if end_date and f_start > end_date:
                    continue
            except ValueError:
                pass

        try:
            with gzip.open(fpath, "rt", encoding="utf-8") as gf:
                reader = csv.DictReader(gf)
                for row in reader:
                    ts_str = row["ts"]
                    dt = datetime.fromisoformat(ts_str)
                    s_date = dt.date()

                    if start_date and s_date < start_date:
                        continue
                    if end_date and s_date > end_date:
                        continue

                    # Reset CVD khi qua ngay moi UTC (§1.2)
                    if cur_session != s_date:
                        cur_session = s_date
                        accum_cvd = 0.0

                    block_id = get_crypto_block_id(dt)
                    bar_idx = (dt.hour * 60 + dt.minute) // 5

                    # Nen khong giao dich van giu cho (close=None) de E1/E3 chi xet nen lien nhau
                    raw_n = row.get("n_trades")
                    if not raw_n or int(raw_n) == 0 or not row.get("close"):
                        bars.append(
                            BarSummary(
                                session_id=s_date,
                                block_id=block_id,
                                bar_idx=bar_idx,
                                t_start=dt,
                                t_end=dt + timedelta(minutes=5),
                                open=None,
                                high=None,
                                low=None,
                                close=None,
                                close_k=None,
                                delta=0.0,
                                cvd=accum_cvd,
                                ask_k_min=None,
                                ask_k_max=None,
                                bid_k_min=None,
                                bid_k_max=None,
                            )
                        )
                        continue

                    o = float(row["open"])
                    h = float(row["high"])
                    l = float(row["low"])
                    c = float(row["close"])
                    delta = float(row["delta"])
                    accum_cvd += delta

                    close_k = int(row["close_k"])
                    ask_min = int(row["ask_k_min"]) if row.get("ask_k_min") else None
                    ask_max = int(row["ask_k_max"]) if row.get("ask_k_max") else None
                    bid_min = int(row["bid_k_min"]) if row.get("bid_k_min") else None
                    bid_max = int(row["bid_k_max"]) if row.get("bid_k_max") else None

                    bars.append(
                        BarSummary(
                            session_id=s_date,
                            block_id=block_id,
                            bar_idx=bar_idx,
                            t_start=dt,
                            t_end=dt + timedelta(minutes=5),
                            open=o,
                            high=h,
                            low=l,
                            close=c,
                            close_k=close_k,
                            delta=delta,
                            cvd=accum_cvd,
                            ask_k_min=ask_min,
                            ask_k_max=ask_max,
                            bid_k_min=bid_min,
                            bid_k_max=bid_max,
                        )
                    )
        except Exception as exc:
            print(f"[CANH BAO] File loi '{fpath}': {exc}", file=sys.stderr)

    return bars


# --- 3. Tra cuu gia P(x) cho Crypto (§1.3) ----------------------------------------


def build_crypto_price_lookup(
    bars: Sequence[BarSummary],
) -> Callable[[datetime], float | None]:
    """P(x) = close cua nen co giao dich gan nhat ket thuc <= x."""
    sorted_pairs: list[tuple[datetime, float]] = []
    for b in bars:
        if b.close is not None:
            sorted_pairs.append((b.t_end, b.close))

    sorted_pairs.sort(key=lambda item: item[0])
    times = [p[0] for p in sorted_pairs]

    def lookup(x: datetime) -> float | None:
        idx = bisect.bisect_right(times, x)
        if idx == 0:
            return None
        return sorted_pairs[idx - 1][1]

    return lookup


# --- 4. Tinh bien muc tieu & Danh gia tung cap (§1.3, §1.4) -----------------------


def check_control_variable_crypto(bars: Sequence[BarSummary]) -> float:
    """Kiem tra bien doi chung tren cua so CHINH:
    Spearman rho(delta, close - open cung nen) > 0.3.
    """
    deltas: list[float] = []
    diffs: list[float] = []
    for b in bars:
        if b.close is not None and b.open is not None:
            deltas.append(b.delta)
            diffs.append(b.close - b.open)

    if len(deltas) < 10:
        return 0.0

    rho, _ = spearmanr(deltas, diffs)
    return float(rho) if not math.isnan(rho) else 0.0


def evaluate_crypto_pair(
    events: Sequence[OrderFlowEvent],
    price_lookup: Callable[[datetime], float | None],
    h_minutes: int,
    alpha_threshold: float,
    hurdle: float = ECONOMIC_HURDLE,
    block_end_fn: Callable[..., datetime] = crypto_block_end_fn,
) -> dict[str, Any]:
    """Tinh muc tieu theo ty le, loc chong lan, bootstrap va danh gia cap."""
    raw_targets = calculate_event_targets(
        events=events,
        price_lookup=price_lookup,
        h_minutes=h_minutes,
        block_end_fn=block_end_fn,
    )

    # Chuyen bien muc tieu y sang ty le: y = d * (P(t_end + H) / close_t - 1)
    ratio_events: list[OrderFlowEvent] = []
    for e in raw_targets:
        if e.y is not None and e.close > 0.0:
            y_ratio = e.y / e.close
            ratio_events.append(
                OrderFlowEvent(
                    event_type=e.event_type,
                    direction=e.direction,
                    session_id=e.session_id,
                    block_id=e.block_id,
                    bar_idx=e.bar_idx,
                    t_end=e.t_end,
                    close=e.close,
                    target_time=e.target_time,
                    exit_price=e.exit_price,
                    y=y_ratio,
                )
            )

    indep = filter_non_overlapping_events(ratio_events, h_minutes=h_minutes)
    n_events = len(indep)
    n_buy = sum(1 for e in indep if e.direction == 1)
    n_sell = sum(1 for e in indep if e.direction == -1)

    if n_events == 0:
        return {
            "n_events": 0,
            "n_buy": 0,
            "n_sell": 0,
            "mean_y": 0.0,
            "p_val": 1.0,
            "p_value": 1.0,
            "passed": False,
        }

    mean_y = sum(e.y for e in indep if e.y is not None) / n_events
    p_val, _ = block_bootstrap_p_value(indep, n_bootstrap=2000, seed=42)

    passed = (
        (n_events >= MIN_TOTAL_EVENTS)
        and (n_buy >= MIN_DIRECTION_EVENTS)
        and (n_sell >= MIN_DIRECTION_EVENTS)
        and (mean_y >= hurdle)
        and (p_val < alpha_threshold)
    )

    return {
        "n_events": n_events,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "mean_y": mean_y,
        "p_val": p_val,
        "p_value": p_val,
        "passed": passed,
    }


# --- 5. Pipeline Sang loc toan dien 6 cap (§1.4) -----------------------------------


def run_crypto_screening_pipeline(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    block_end_fn: Callable[..., datetime] = crypto_block_end_fn,
) -> dict[str, Any]:
    """Thuc hien sang loc 6 cap tren ca hai cua so CHINH va LAP LAI."""
    all_bars = load_crypto_footprint_bars(
        data_dir=data_dir,
        start_date=MAIN_START_DATE,
        end_date=REPEAT_END_DATE,
    )

    # 1. Kiem tra bien doi chung tren cua so CHINH
    main_bars = [
        b for b in all_bars if MAIN_START_DATE <= b.session_id <= MAIN_END_DATE
    ]
    ctrl_rho = check_control_variable_crypto(main_bars)

    if ctrl_rho <= CONTROL_MIN_RHO:
        return {
            "status": "CONTROL_FAILED",
            "ctrl_rho": ctrl_rho,
            "message": "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN",
            "pairs": {},
        }

    # 2. Phat hien su kien tren toan bo chuoi nen
    e1_all = detect_e1_events(all_bars)
    e2_all = detect_e2_events(all_bars)
    e3_all = detect_e3_events(all_bars)

    events_by_type = {
        "E1": e1_all,
        "E2": e2_all,
        "E3": e3_all,
    }

    price_lookup = build_crypto_price_lookup(all_bars)

    results: dict[str, Any] = {}
    main_passed_pairs: list[str] = []

    # 3. Danh gia cua so CHINH cho 6 cap
    for ev_name in EVENT_NAMES:
        for h_val in HORIZONS:
            pair_key = f"{ev_name}_{h_val}m"
            ev_list = [
                e
                for e in events_by_type[ev_name]
                if MAIN_START_DATE <= e.session_id <= MAIN_END_DATE
            ]
            res_main = evaluate_crypto_pair(
                events=ev_list,
                price_lookup=price_lookup,
                h_minutes=h_val,
                alpha_threshold=ALPHA_PER_PAIR_INITIAL,
                hurdle=ECONOMIC_HURDLE,
                block_end_fn=block_end_fn,
            )
            results[pair_key] = {"main": res_main}
            if res_main["passed"]:
                main_passed_pairs.append(pair_key)

    k_passed = len(main_passed_pairs)
    repeat_alpha = (0.05 / k_passed) if k_passed > 0 else 0.05

    # 4. Danh gia cua so LAP LAI cho 6 cap
    for ev_name in EVENT_NAMES:
        for h_val in HORIZONS:
            pair_key = f"{ev_name}_{h_val}m"
            ev_list_rep = [
                e
                for e in events_by_type[ev_name]
                if REPEAT_START_DATE <= e.session_id <= REPEAT_END_DATE
            ]
            res_rep = evaluate_crypto_pair(
                events=ev_list_rep,
                price_lookup=price_lookup,
                h_minutes=h_val,
                alpha_threshold=repeat_alpha,
                hurdle=ECONOMIC_HURDLE,
                block_end_fn=block_end_fn,
            )
            results[pair_key]["repeat"] = res_rep

            # Danh gia DAT cuoi cung (§1.4)
            is_main_passed = results[pair_key]["main"]["passed"]
            # Cap phai dat o CHINH, VA o LAP LAI co mean_y >= hurdle va p < 0.05 / k
            rep_satisfied = (res_rep["mean_y"] >= ECONOMIC_HURDLE) and (
                res_rep["p_val"] < repeat_alpha
            )
            final_passed = is_main_passed and rep_satisfied

            results[pair_key]["final_passed"] = final_passed

    return {
        "status": "SUCCESS",
        "ctrl_rho": ctrl_rho,
        "k_main_passed": k_passed,
        "repeat_alpha": repeat_alpha,
        "pairs": results,
    }


# --- 6. CLI Main Runner & Cong ngay chong nhin truoc (§1.4, §2.B) -----------------


def main(
    args: Sequence[str] | None = None,
    today: date | None = None,
    block_end_fn: Callable[..., datetime] = crypto_block_end_fn,
) -> int:
    parser = argparse.ArgumentParser(
        description="Cong cu sang loc 6 cap order flow footprint tren BTCUSDT perp (Brief dot 183)"
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Thu muc chua nen footprint tom tat (mac dinh: {DEFAULT_DATA_DIR})",
    )
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    if today is None:
        today = datetime.now(TZ).date()

    print("=" * 84)
    print(
        "  BRIEF ĐỢT 183 — SÀNG LỌC ORDER FLOW FOOTPRINT BTCUSDT PERP (ĐĂNG KÝ TRƯỚC)"
    )
    print(f"  Ngày hiện tại (giờ VN): {today}")
    print(f"  Mốc bắt đầu đo        : {HOLDOUT_START_DATE}")
    print("=" * 84)

    # CỔNG NGÀY CHỐNG NHÌN TRƯỚC (§1.4, §2.B):
    # Từ chối chạy trước 2026-11-01, TRƯỚC KHI MỞ BẤT KỲ FILE NÀO.
    if today < HOLDOUT_START_DATE:
        print(
            f"\n[BẢO VỆ CHỐNG NHÌN TRƯỚC] Ngày hiện tại ({today}) chưa tới ngày bắt đầu đo "
            f"({HOLDOUT_START_DATE}).\nDừng toàn bộ chương trình và từ chối mở dữ liệu để bảo vệ "
            f"tính vô tư của tập nghiên cứu.",
            file=sys.stderr,
        )
        return 2

    res = run_crypto_screening_pipeline(
        data_dir=parsed_args.data_dir,
        block_end_fn=block_end_fn,
    )

    if res["status"] == "CONTROL_FAILED":
        print(
            f"\n[DỪNG] {res['message']} (Spearman rho = {res['ctrl_rho']:.4f} <= {CONTROL_MIN_RHO})",
            file=sys.stderr,
        )
        return 4

    print(f"\nKiểm đối chứng rho: {res['ctrl_rho']:.4f} > {CONTROL_MIN_RHO} (ĐẠT)")
    print(
        f"Số cặp đạt ở CHÍNH: {res['k_main_passed']}/6 (Ngưỡng p LẶP LẠI: {res['repeat_alpha']:.4f})"
    )
    print("-" * 84)
    print(
        f"{'Cặp':<10} | {'CHÍNH (N/Buy/Sell)':<20} | {'Mean y':<10} | {'p-val':<8} | {'LẶP LẠI (N/Mean/p)':<20} | {'Kết luận'}"
    )
    print("-" * 84)

    for pair_key, val in res["pairs"].items():
        m = val["main"]
        r = val["repeat"]
        m_str = f"{m['n_events']}/{m['n_buy']}/{m['n_sell']}"
        r_str = f"{r['n_events']}/{r['mean_y']:.4f}/{r['p_val']:.4f}"
        outcome = "ĐẠT" if val["final_passed"] else "TRƯỢT"
        print(
            f"{pair_key:<10} | {m_str:<20} | {m['mean_y']:<10.4f} | {m['p_val']:<8.4f} | {r_str:<20} | {outcome}"
        )

    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
