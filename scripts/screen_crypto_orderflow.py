"""Cong cu sang loc 6 cap order flow footprint tren BTCUSDT perp v2 (Brief dot 183b).

- Du lieu: data/crypto_footprint_v2/BTCUSDT/<YYYY-MM>.csv.gz
- Cua so CHINH: 2023-01-01 -> 2024-12-31.
- Cua so LAP LAI: 2025-01-01 -> 2026-08-31.
- Nguong imbalance tuong doi: p90 (min_vol) va p50 (denom_floor) tinh tu 5 ngay truoc.
- Quy tac suy bien: Ty le nen 'ca hai' > 50% tren CHINH => E3 bi LOAI, con 4 cap.
- Cong ngay: Tu choi chay truoc 2026-10-12 (ngay VN).
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
    calculate_percentile,
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
    "E3_DEGENERATE_BOTH_SHARE",
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
    "CryptoBarSummary",
    "apply_relative_imbalance",
    "build_crypto_price_lookup",
    "check_control_variable_crypto",
    "crypto_block_end_fn",
    "detect_e1_events",
    "detect_e2_events",
    "detect_e3_events",
    "evaluate_crypto_pair",
    "get_crypto_block_id",
    "imbalance_levels",
    "imbalance_prevalence",
    "load_crypto_footprint_bars",
    "main",
    "parse_fp_string",
    "run_crypto_screening_pipeline",
]

# --- Hang so dang ky truoc (§1.3, §1.4) -------------------------------------------

EVENT_NAMES: tuple[str, ...] = ("E1", "E2", "E3")
HORIZONS: tuple[int, ...] = (15, 30)

# Mo som theo cho phep cua chu du an 11/10 (gia thuyet 10 thang 10, spec H)
HOLDOUT_START_DATE: date = date(2026, 10, 12)

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

E3_DEGENERATE_BOTH_SHARE: float = 0.5

DEFAULT_DATA_DIR = Path("data/crypto_footprint_v2/BTCUSDT")


@dataclass
class CryptoBarSummary(BarSummary):
    """Nen BarSummary mo rong co chua thong tin phan bo footprint tai tung muc k."""

    fp: dict[int, tuple[float, float]] | None = None
    min_vol: float | None = None
    denom_floor: float | None = None


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


# --- 2. Doc file tom tat v2 & Parse footprint (§1.2) ------------------------------


def parse_fp_string(fp_str: str) -> dict[int, tuple[float, float]]:
    """Parse chuoi k:buy_usdt:sell_usdt|... thanh dict map k -> (buy_usdt, sell_usdt)."""
    if not fp_str or not fp_str.strip():
        return {}
    res: dict[int, tuple[float, float]] = {}
    for part in fp_str.strip().split("|"):
        if not part:
            continue
        items = part.split(":")
        if len(items) == 3:
            try:
                k = int(items[0])
                buy_val = float(items[1])
                sell_val = float(items[2])
                res[k] = (buy_val, sell_val)
            except ValueError:
                continue
    return res


def load_crypto_footprint_bars(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[CryptoBarSummary]:
    """Doc cac file <YYYY-MM>.csv.gz trong data_dir thanh danh sach CryptoBarSummary.

    - File khong co cot 'fp' se bi nem loi ValueError (dinh dang v1).
    - Cac truong imbalance khoi tao la None (se tinh boi apply_relative_imbalance).
    """
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return []

    files = sorted(p_dir.glob("*.csv.gz"))
    bars: list[CryptoBarSummary] = []
    cur_session: date | None = None
    accum_cvd: float = 0.0

    for fpath in files:
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

        with gzip.open(fpath, "rt", encoding="utf-8") as gf:
            reader = csv.DictReader(gf)
            if reader.fieldnames is None or "fp" not in reader.fieldnames:
                raise ValueError(
                    f"File '{fpath.name}' su dung dinh dang v1 (thieu cot 'fp'). Yeu cau dinh dang v2."
                )

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
                        CryptoBarSummary(
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
                            fp=None,
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
                fp_dict = parse_fp_string(row.get("fp", ""))

                bars.append(
                    CryptoBarSummary(
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
                        ask_k_min=None,
                        ask_k_max=None,
                        bid_k_min=None,
                        bid_k_max=None,
                        fp=fp_dict,
                    )
                )

    return bars


# --- 3. Nguong Imbalance Tuong Doi & Pho Bien (§1.3, §1.4) -------------------------


def apply_relative_imbalance(
    bars: list[CryptoBarSummary],
) -> list[CryptoBarSummary]:
    """Ap nguong imbalance tuong doi cho tung ngay D:
    min_vol(D) = p90 cua pool 5 ngay truoc; denom_floor(D) = p50 cua pool.
    5 ngay dau khong co nguong => imbalance giu None.
    """
    sessions_order: list[date] = []
    bars_by_session: dict[date, list[CryptoBarSummary]] = defaultdict(list)
    for b in bars:
        s_date = b.session_id
        if s_date not in bars_by_session:
            sessions_order.append(s_date)
        bars_by_session[s_date].append(b)

    for s_idx, d_date in enumerate(sessions_order):
        if s_idx < 5:
            # 5 ngay dau: khong du 5 ngay truoc, imbalance giu None
            for b in bars_by_session[d_date]:
                b.min_vol = None
                b.denom_floor = None
                b.ask_k_min = None
                b.ask_k_max = None
                b.bid_k_min = None
                b.bid_k_max = None
            continue

        hist_days = sessions_order[s_idx - 5 : s_idx]
        pool: list[float] = []
        for h_d in hist_days:
            for b in bars_by_session[h_d]:
                if b.fp:
                    for buy_val, sell_val in b.fp.values():
                        if buy_val > 0.0:
                            pool.append(buy_val)
                        if sell_val > 0.0:
                            pool.append(sell_val)

        if not pool:
            for b in bars_by_session[d_date]:
                b.min_vol = None
                b.denom_floor = None
                b.ask_k_min = None
                b.ask_k_max = None
                b.bid_k_min = None
                b.bid_k_max = None
            continue

        min_vol_d = calculate_percentile(pool, 90.0)
        denom_floor_d = calculate_percentile(pool, 50.0)

        for b in bars_by_session[d_date]:
            b.min_vol = min_vol_d
            b.denom_floor = denom_floor_d
            if b.fp:
                ask_ks, bid_ks = imbalance_levels(
                    b.fp,
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

    return bars


def imbalance_prevalence(
    bars: Sequence[BarSummary],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, int]:
    """Dem ti le 4 nhom imbalance tren cac nen co giao dich:
    - only ask
    - only bid
    - both (ca hai)
    - neither (khong co)
    """
    filtered = [
        b
        for b in bars
        if b.close is not None
        and (start_date is None or b.session_id >= start_date)
        and (end_date is None or b.session_id <= end_date)
    ]

    both = 0
    ask_only = 0
    bid_only = 0
    neither = 0

    for b in filtered:
        has_ask = b.ask_k_min is not None
        has_bid = b.bid_k_min is not None
        if has_ask and has_bid:
            both += 1
        elif has_ask:
            ask_only += 1
        elif has_bid:
            bid_only += 1
        else:
            neither += 1

    return {
        "both": both,
        "ask_only": ask_only,
        "bid_only": bid_only,
        "neither": neither,
        "total": len(filtered),
    }


# --- 4. Tra cuu gia P(x) cho Crypto (§1.3) ----------------------------------------


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


# --- 5. Tinh bien muc tieu & Danh gia tung cap (§1.3, §1.4) -----------------------


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


# --- 6. Pipeline Sang loc toan dien 6 cap (§1.4) -----------------------------------


def run_crypto_screening_pipeline(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    block_end_fn: Callable[..., datetime] = crypto_block_end_fn,
) -> dict[str, Any]:
    """Thuc hien sang loc 6 cap tren ca hai cua so CHINH va LAP LAI."""
    all_bars_raw = load_crypto_footprint_bars(
        data_dir=data_dir,
        start_date=MAIN_START_DATE,
        end_date=REPEAT_END_DATE,
    )
    all_bars = apply_relative_imbalance(all_bars_raw)

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

    # 2. Kiem tra quy tac suy bien E3 tren cua so CHINH (§1.4)
    main_prev = imbalance_prevalence(
        all_bars, start_date=MAIN_START_DATE, end_date=MAIN_END_DATE
    )
    both_ratio = (
        main_prev["both"] / main_prev["total"] if main_prev["total"] > 0 else 0.0
    )
    e3_degenerate = both_ratio > E3_DEGENERATE_BOTH_SHARE

    # 3. Phat hien su kien tren toan bo chuoi nen
    e1_all = detect_e1_events(all_bars)
    e2_all = detect_e2_events(all_bars)
    e3_all = detect_e3_events(all_bars) if not e3_degenerate else []

    events_by_type = {
        "E1": e1_all,
        "E2": e2_all,
        "E3": e3_all,
    }

    price_lookup = build_crypto_price_lookup(all_bars)

    results: dict[str, Any] = {}
    main_passed_pairs: list[str] = []

    # 4. Danh gia cua so CHINH cho 6 cap (Bonferroni luon 0.05 / 6)
    for ev_name in EVENT_NAMES:
        for h_val in HORIZONS:
            pair_key = f"{ev_name}_{h_val}m"
            if ev_name == "E3" and e3_degenerate:
                results[pair_key] = {
                    "main": {
                        "n_events": 0,
                        "n_buy": 0,
                        "n_sell": 0,
                        "mean_y": 0.0,
                        "p_val": 1.0,
                        "passed": False,
                        "degenerate": True,
                    },
                    "repeat": {
                        "n_events": 0,
                        "mean_y": 0.0,
                        "p_val": 1.0,
                        "passed": False,
                    },
                    "final_passed": False,
                    "degenerate": True,
                }
                continue

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

    # 5. Danh gia cua so LAP LAI cho 6 cap
    for ev_name in EVENT_NAMES:
        for h_val in HORIZONS:
            pair_key = f"{ev_name}_{h_val}m"
            if ev_name == "E3" and e3_degenerate:
                continue

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

            is_main_passed = results[pair_key]["main"]["passed"]
            rep_satisfied = (res_rep["mean_y"] >= ECONOMIC_HURDLE) and (
                res_rep["p_val"] < repeat_alpha
            )
            results[pair_key]["final_passed"] = is_main_passed and rep_satisfied
            results[pair_key]["degenerate"] = False

    return {
        "status": "SUCCESS",
        "ctrl_rho": ctrl_rho,
        "k_main_passed": k_passed,
        "repeat_alpha": repeat_alpha,
        "e3_degenerate": e3_degenerate,
        "both_share": both_ratio,
        "pairs": results,
    }


# --- 7. CLI Main Runner & Cong ngay chong nhin truoc (§1.4, §2.B) -----------------


def main(
    args: Sequence[str] | None = None,
    today: date | None = None,
    block_end_fn: Callable[..., datetime] = crypto_block_end_fn,
) -> int:
    parser = argparse.ArgumentParser(
        description="Cong cu sang loc 6 cap order flow footprint tren BTCUSDT perp v2 (Brief dot 183b)"
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Thu muc chua nen footprint tom tat v2 (mac dinh: {DEFAULT_DATA_DIR})",
    )
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    if today is None:
        today = datetime.now(TZ).date()

    print("=" * 84)
    print(
        "  BRIEF ĐỢT 183b — SÀNG LỌC ORDER FLOW FOOTPRINT BTCUSDT PERP (ĐĂNG KÝ TRƯỚC)"
    )
    print(f"  Ngày hiện tại (giờ VN): {today}")
    print(f"  Mốc bắt đầu đo        : {HOLDOUT_START_DATE}")
    print("=" * 84)

    # CỔNG NGÀY CHỐNG NHÌN TRƯỚC (§1.4, §2.B):
    # Từ chối chạy trước 2026-10-12, TRƯỚC KHI MỞ BẤT KỲ FILE NÀO.
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
    if res.get("e3_degenerate"):
        print(
            f"Cảnh báo: E3 BỊ LOẠI do suy biến (tỷ lệ 'cả hai' = {res['both_share'] * 100:.2f}% > 50%). Còn 4 cặp."
        )
    print(
        f"Số cặp đạt ở CHÍNH: {res['k_main_passed']}/6 (Ngưỡng p LẶP LẠI: {res['repeat_alpha']:.4f})"
    )
    print("-" * 84)
    print(
        f"{'Cặp':<10} | {'CHÍNH (N/Buy/Sell)':<20} | {'Mean y':<10} | {'p-val':<8} | {'LẶP LẠI (N/Mean/p)':<20} | {'Kết luận'}"
    )
    print("-" * 84)

    for pair_key, val in res["pairs"].items():
        if val.get("degenerate"):
            print(f"{pair_key:<10} | E3 LOẠI (suy biến)")
            continue

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
