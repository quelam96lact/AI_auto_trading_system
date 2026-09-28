"""Đo lường lợi thế dự báo của điểm SEPA (Minervini Trend Template 0–7) và RS ≥ 70 — Brief đợt 120.

Thiết kế TIỀN ĐĂNG KÝ (mọi tham số chốt trong brief, KHÔNG sửa hằng số):
- Dữ liệu nghiêm ngặt trước 2023-01-01 (READ_TO = 2023-01-01).
- Kiểm tra niêm phong bằng validate_sealed_bars.
- Nhập toàn bộ máy đo từ scripts/screen_vcp_daily.py theo đúng yêu cầu §1:
  trend_conditions, rolling_mean, rolling_max, rolling_min,
  clean_bars, bar_date, validate_sealed_bars, in_is,
  liquidity_ok, apply_cooldown, entry_status, is_ceiling_open, limit_rate,
  net_return, compute_targets, basket_baseline, excess_for_event,
  bootstrap_by_month, compact_control_series, load_universe,
  _describe, _percentile
- Giả thuyết chính (được gated): Lợi suất vượt trội so với đối chứng cùng ngày
  của nhóm sự kiện 7/7, tại K = 20, lớn hơn 0.
- Cổng đạt (cả bốn điều kiện):
  1. trung vị lợi suất vượt trội tại K = 20 > 0;
  2. ít nhất MIN_EVENTS = 100 sự kiện hợp lệ;
  3. khoảng tin cậy bootstrap khối theo tháng không chứa 0 (CI_LOW_PCT = 2.5, CI_HIGH_PCT = 97.5);
  4. đạt sau Holm trên số phép kiểm định thực sự chạy ở §3.1 (m = 1).
"""

from __future__ import annotations

import argparse
import io
import math
import pathlib
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_vcp_daily import (
    BOOTSTRAP_SEED,
    CI_HIGH_PCT,
    CI_LOW_PCT,
    COOLDOWN_BARS,
    IS_SIGNAL_END,
    IS_SIGNAL_START,
    MAIN_K,
    MIN_CONTROL,
    MIN_EVENTS,
    MIN_TURNOVER_VND,
    N_BOOTSTRAP,
    READ_FROM,
    READ_TO,
    TARGET_KS,
    TURNOVER_WINDOW,
    ControlEntry,
    SymbolData,
    _describe,
    basket_baseline,
    compact_control_series,
    excess_for_event,
    in_is,
)
from trading.metrics import empirical_percentile_rank, holm_adjust, max_drawdown
from trading.models import Bar
from trading.stock_study import (
    TREND_KEYS,
    TREND_MIN_BARS,
    BasketEntry,
    apply_cooldown,
    bar_date,
    basket_for_day,
    bootstrap_by_month,
    calculate_rs_ranks,
    clean_bars,
    compute_targets,
    entry_status,
    excess_k,
    is_ceiling_open,
    limit_rate,
    liquidity_ok,
    load_universe,
    make_basket_entry,
    month_key,
    net_return,
    rolling_max,
    rolling_mean,
    rolling_min,
    trend_conditions,
    validate_sealed_bars,
)
from trading.storage.db import Storage

__all__ = [
    "BOOTSTRAP_SEED",
    "CI_HIGH_PCT",
    "CI_LOW_PCT",
    "COOLDOWN_BARS",
    "IS_SIGNAL_END",
    "IS_SIGNAL_START",
    "MAIN_K",
    "MIN_CONTROL",
    "MIN_EVENTS",
    "MIN_TURNOVER_VND",
    "N_BOOTSTRAP",
    "READ_FROM",
    "READ_TO",
    "TARGET_KS",
    "TREND_KEYS",
    "TREND_MIN_BARS",
    "TURNOVER_WINDOW",
    "ControlEntry",
    "SepaEvent",
    "SymbolData",
    "_describe",
    "apply_cooldown",
    "assign_event_excess",
    "bar_date",
    "basket_baseline",
    "bootstrap_by_month",
    "clean_bars",
    "compact_control_series",
    "compute_rolling_rs_raw",
    "compute_score_series",
    "compute_targets",
    "empirical_percentile_rank",
    "entry_status",
    "evaluate_gate",
    "evaluate_gate_mean",
    "excess_for_event",
    "find_score_events",
    "format_rs_table",
    "format_state_table",
    "format_summary_table",
    "holm_adjust",
    "in_is",
    "is_ceiling_open",
    "limit_rate",
    "liquidity_ok",
    "load_universe",
    "max_drawdown",
    "month_key",
    "net_return",
    "resolve_universe",
    "rolling_max",
    "rolling_mean",
    "rolling_min",
    "run_sepa_measurement",
    "trend_conditions",
    "validate_sealed_bars",
]


# --- Cấu trúc sự kiện SEPA --------------------------------------------------------

@dataclass(slots=True)
class SepaEvent:
    symbol: str
    day: date
    exchange: str
    entry_open: float
    score: int
    rs_rank: int | None = None
    r: dict[int, float | None] = field(default_factory=dict)
    r_net: dict[int, float | None] = field(default_factory=dict)
    excess: dict[int, float | None] = field(default_factory=dict)


# --- Hàm thuần tính điểm và lọc sự kiện -------------------------------------------

def compute_score_series(
    bars: list[Bar],
    sma50: list[float | None],
    sma150: list[float | None],
    sma200: list[float | None],
    win_low: list[float | None],
    win_high: list[float | None],
) -> list[int]:
    """Tính điểm SEPA (0-7) tại đóng cửa của mỗi nến idx (0 <= idx < len(bars)).

    Quan trọng: Để tính điểm tại đóng cửa nến idx bằng `trend_conditions`,
    ta truyền t = idx + 1 vì `trend_conditions` tính tại i = t - 1 = idx.
    Tuyệt đối không dùng nến tương lai idx + 1 (tránh nhìn trước).
    """
    n = len(bars)
    scores: list[int] = [0] * n
    for idx in range(TREND_MIN_BARS, n):
        conds = trend_conditions(
            bars,
            idx + 1,
            sma50=sma50,
            sma150=sma150,
            sma200=sma200,
            win_low=win_low,
            win_high=win_high,
        )
        scores[idx] = sum(1 for v in conds.values() if v)
    return scores


def compute_rolling_rs_raw(bars: list[Bar]) -> list[float | None]:
    """Tính chuỗi RS_raw cho từng nến idx (chuẩn đợt 119).

    RS_raw = 0.4 * (P / P_63 - 1) + 0.2 * (P / P_126 - 1) + 0.2 * (P / P_189 - 1) + 0.2 * (P / P_252 - 1)
    Cần ít nhất 253 nến sạch (idx >= 252). Trả về None nếu thiếu nến hoặc giá <= 0.
    """
    n = len(bars)
    rs_raw: list[float | None] = [None] * n
    for idx in range(252, n):
        p = bars[idx].close
        p63 = bars[idx - 63].close
        p126 = bars[idx - 126].close
        p189 = bars[idx - 189].close
        p252 = bars[idx - 252].close
        if p63 <= 0 or p126 <= 0 or p189 <= 0 or p252 <= 0 or p <= 0:
            continue
        rs_raw[idx] = (
            0.4 * (p / p63 - 1.0)
            + 0.2 * (p / p126 - 1.0)
            + 0.2 * (p / p189 - 1.0)
            + 0.2 * (p / p252 - 1.0)
        )
    return rs_raw


def find_score_events(
    bars: list[Bar],
    scores: list[int],
    target_score: int,
    turnover20: list[float | None],
    mode: str = "transition",
    cooldown: int = COOLDOWN_BARS,
) -> list[int]:
    """Tìm chỉ số nến tín hiệu cho điểm target_score (0-7).

    mode:
      - 'transition': chuyển trạng thái sang target_score.
         + target_score == 7: scores[t-1] < 7 và scores[t] == 7
         + target_score == 0: scores[t-1] > 0 và scores[t] == 0
         + target_score in 1..6: scores[t-1] != target_score và scores[t] == target_score
      - 'state': mọi ngày có điểm == target_score (biến thể báo cáo §2.1).

    Sau đó áp dụng apply_cooldown(cand, cooldown).
    Thanh khoản: turnover20[t-1] >= MIN_TURNOVER_VND (chuẩn SymbolData.liq_ok).
    """
    cand: list[int] = []
    n = len(bars)
    for t in range(TREND_MIN_BARS, n):
        if bars[t].volume == 0:
            continue
        v = turnover20[t - 1] if t >= 1 else None
        if v is None or v < MIN_TURNOVER_VND:
            continue

        if mode == "transition":
            if target_score == 7:
                is_match = (scores[t - 1] < 7 and scores[t] == 7)
            elif target_score == 0:
                is_match = (scores[t - 1] > 0 and scores[t] == 0)
            else:
                is_match = (scores[t - 1] != target_score and scores[t] == target_score)
        elif mode == "state":
            is_match = (scores[t] == target_score)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        if is_match:
            cand.append(t)

    return apply_cooldown(cand, cooldown=cooldown)


def assign_event_excess(
    e: SepaEvent,
    peers: list[ControlEntry],
    ks: tuple[int, ...] = TARGET_KS,
) -> None:
    """Tính lợi suất vượt trội cho sự kiện e so với rổ đối chứng cùng ngày peers."""
    e.excess = {}
    for k in ks:
        _baseline, excess, _n = excess_for_event(e.r.get(k), peers, k)
        e.excess[k] = excess


# --- Đánh giá cổng tiền đăng ký --------------------------------------------------

def evaluate_gate(
    median_excess_k20: float | None,
    n_events: int,
    boot_ci: tuple[float | None, float | None],
    holm_pass: bool,
) -> tuple[bool, dict[str, Any]]:
    """Kiểm tra cả 4 điều kiện của cổng chính (§3):

    1. trung vị lợi suất vượt trội tại K = 20 > 0;
    2. ít nhất MIN_EVENTS = 100 sự kiện hợp lệ;
    3. khoảng tin cậy bootstrap khối theo tháng không chứa 0 (ci_low > 0);
    4. đạt sau Holm (m = 1: p_adjusted < 0.05).
    """
    cond1 = median_excess_k20 is not None and median_excess_k20 > 0
    cond2 = n_events >= MIN_EVENTS
    cond3 = (
        boot_ci[0] is not None
        and boot_ci[1] is not None
        and boot_ci[0] > 0
    )
    cond4 = holm_pass

    passed = cond1 and cond2 and cond3 and cond4
    details = {
        "cond1_median_gt_0": cond1,
        "cond2_min_events": cond2,
        "cond3_ci_excludes_0": cond3,
        "cond4_holm_pass": cond4,
        "passed_all": passed,
    }
    return passed, details


def evaluate_gate_mean(
    mean_excess_k20: float | None,
    n_events: int,
    boot_ci: tuple[float | None, float | None],
    holm_pass: bool,
    median_excess_k20: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Kiểm tra cả 4 điều kiện của cổng chính cho rổ trung tính (§2.4):

    CẢ BỐN điều kiện đều dùng TRUNG BÌNH:
    1. trung bình excess K=20 > 0;
    2. ít nhất MIN_EVENTS = 100 sự kiện hợp lệ;
    3. cận dưới KTC 95% của bootstrap_by_month > 0;
    4. đạt sau Holm (m = 1: p_adjusted < 0.05).
    """
    cond1 = mean_excess_k20 is not None and mean_excess_k20 > 0
    cond2 = n_events >= MIN_EVENTS
    cond3 = (
        boot_ci[0] is not None
        and boot_ci[1] is not None
        and boot_ci[0] > 0
    )
    cond4 = holm_pass

    passed = cond1 and cond2 and cond3 and cond4
    details = {
        "cond1_mean_gt_0": cond1,
        "cond2_min_events": cond2,
        "cond3_ci_excludes_0": cond3,
        "cond4_holm_pass": cond4,
        "passed_all": passed,
    }
    return passed, details


def resolve_universe(
    storage: Storage,
    exclude_file: str = "exclusions.txt",
    no_exclusions: bool = False,
) -> tuple[list[str], dict[str, str], int, set[str]]:
    """Nạp danh sách vũ trụ và loại trừ mã theo exclusions.txt."""
    if no_exclusions:
        return load_universe(storage, "__no_exclusions__.tmp")
    if not pathlib.Path(exclude_file).exists():
        raise FileNotFoundError(f"Tệp exclusions không tìm thấy: {exclude_file}")
    return load_universe(storage, exclude_file)


# --- Bộ xử lý toàn bộ phép đo ---------------------------------------------------

def run_sepa_measurement(
    storage: Storage,
    exclude_file: str = "exclusions.txt",
    no_exclusions: bool = False,
    limit: int = 0,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    basket: str = "trend",
) -> dict[str, Any]:
    """Chạy toàn bộ pipeline đo điểm SEPA."""
    if basket not in ("trend", "neutral"):
        raise ValueError(f"Chế độ rổ không hợp lệ: {basket} (chỉ hỗ trợ 'trend' hoặc 'neutral')")
    t0 = time.perf_counter()

    # 1. Nạp danh sách vũ trụ
    universe, exchange, n_all, excluded = resolve_universe(
        storage, exclude_file=exclude_file, no_exclusions=no_exclusions
    )
    if limit > 0:
        universe = universe[:limit]

    # 2. Đọc nến, tính chỉ báo, làm sạch, niêm phong
    sd_by_sym: dict[str, SymbolData] = {}
    scores_by_sym: dict[str, list[int]] = {}
    rs_raw_by_sym: dict[str, list[float | None]] = {}
    store_control: list[tuple[str, Any, Any, Any, Any]] = []
    all_bars_by_sym: dict[str, tuple[list[Bar], str]] = {}

    symbols_kept = 0
    n_junk = 0

    # Lập chỉ mục RS_raw theo ngày để tính RS_rank toàn vũ trụ hợp lệ mỗi ngày
    rs_raw_by_day_ord: dict[int, dict[str, float]] = defaultdict(dict)

    for sym in universe:
        bars = storage.read_daily_bars(sym, READ_FROM, READ_TO)
        if not bars:
            continue
        validate_sealed_bars(bars)
        bars, junk = clean_bars(bars)
        n_junk += junk
        ex = exchange.get(sym, "")
        if basket == "neutral":
            all_bars_by_sym[sym] = (bars, ex)
        if len(bars) < TREND_MIN_BARS + 1:
            continue
        symbols_kept += 1
        sd = SymbolData.build(sym, ex, bars)
        scores = compute_score_series(
            bars, sd.sma50, sd.sma150, sd.sma200, sd.win_low, sd.win_high
        )
        rs_raws = compute_rolling_rs_raw(bars)

        sd_by_sym[sym] = sd
        scores_by_sym[sym] = scores
        rs_raw_by_sym[sym] = rs_raws
        if basket == "trend":
            store_control.append((sym, *compact_control_series(sd)))

        for idx, b in enumerate(bars):
            raw_v = rs_raws[idx]
            if raw_v is not None:
                d_ord = bar_date(b).toordinal()
                rs_raw_by_day_ord[d_ord][sym] = raw_v

    read_done = time.perf_counter()

    # 3. Tính RS_rank (1-99) cho từng ngày
    rs_ranks_by_day_ord: dict[int, dict[str, int]] = {}
    for d_ord, raws_map in rs_raw_by_day_ord.items():
        if raws_map:
            rs_ranks_by_day_ord[d_ord] = calculate_rs_ranks(raws_map)

    # 4. Trích xuất sự kiện cho từng nhóm
    # - Sự kiện chuyển trạng thái (Scores 0..7)
    # - Sự kiện trạng thái kéo dài (Scores 0..7)
    events_transition_by_score: dict[int, list[SepaEvent]] = defaultdict(list)
    events_state_by_score: dict[int, list[SepaEvent]] = defaultdict(list)
    all_events_for_control: list[SepaEvent] = []

    for sym, sd in sd_by_sym.items():
        bars = sd.bars
        scores = scores_by_sym[sym]
        ex = sd.exchange

        # Trích xuất chuyển trạng thái (0..7)
        for s in range(8):
            ev_indices = find_score_events(
                bars, scores, target_score=s, turnover20=sd.turnover20, mode="transition"
            )
            for t in ev_indices:
                d = bar_date(bars[t])
                if not in_is(d):
                    continue
                if entry_status(bars, t, ex) != "ok":
                    continue
                tg = compute_targets(bars, t, ks=TARGET_KS)
                entry_open = bars[t + 1].open
                d_ord = d.toordinal()
                rank_val = rs_ranks_by_day_ord.get(d_ord, {}).get(sym)
                ev = SepaEvent(
                    symbol=sym,
                    day=d,
                    exchange=ex,
                    entry_open=entry_open,
                    score=s,
                    rs_rank=rank_val,
                    r=tg,
                    r_net={
                        k: (net_return(entry_open, bars[t + k].close) if tg.get(k) is not None else None)
                        for k in TARGET_KS
                    },
                )
                events_transition_by_score[s].append(ev)
                all_events_for_control.append(ev)

        # Trích xuất trạng thái (0..7)
        for s in range(8):
            ev_indices_state = find_score_events(
                bars, scores, target_score=s, turnover20=sd.turnover20, mode="state"
            )
            for t in ev_indices_state:
                d = bar_date(bars[t])
                if not in_is(d):
                    continue
                if entry_status(bars, t, ex) != "ok":
                    continue
                tg = compute_targets(bars, t, ks=TARGET_KS)
                entry_open = bars[t + 1].open
                d_ord = d.toordinal()
                rank_val = rs_ranks_by_day_ord.get(d_ord, {}).get(sym)
                ev = SepaEvent(
                    symbol=sym,
                    day=d,
                    exchange=ex,
                    entry_open=entry_open,
                    score=s,
                    rs_rank=rank_val,
                    r=tg,
                    r_net={
                        k: (net_return(entry_open, bars[t + k].close) if tg.get(k) is not None else None)
                        for k in TARGET_KS
                    },
                )
                events_state_by_score[s].append(ev)
                all_events_for_control.append(ev)

    # 5. Xây dựng rổ đối chứng cùng ngày & 6. Tính excess return
    event_day_ords = {e.day.toordinal() for e in all_events_for_control}
    neutral_basket_by_day: dict[int, dict[str, BasketEntry]] = defaultdict(dict)

    if basket == "trend":
        # 5. Xây dựng rổ đối chứng cùng ngày (đợt 120: rổ chỉ gồm mã 7/7)
        control_by_day: dict[int, list[ControlEntry]] = defaultdict(list)
        for sym, days_ord, r5, r10, r20 in store_control:
            for i, od in enumerate(days_ord):
                if od not in event_day_ords:
                    continue
                if math.isnan(r5[i]) and math.isnan(r10[i]) and math.isnan(r20[i]):
                    continue
                control_by_day[od].append(
                    ControlEntry(
                        symbol=sym,
                        r5=None if math.isnan(r5[i]) else r5[i],
                        r10=None if math.isnan(r10[i]) else r10[i],
                        r20=None if math.isnan(r20[i]) else r20[i],
                    )
                )

        # 6. Tính excess return cho tất cả sự kiện (đợt 120)
        def populate_excess_trend(events_list: list[SepaEvent]) -> None:
            for e in events_list:
                peers = [c for c in control_by_day.get(e.day.toordinal(), []) if c.symbol != e.symbol]
                assign_event_excess(e, peers, TARGET_KS)

        for s in range(8):
            populate_excess_trend(events_transition_by_score[s])
            populate_excess_trend(events_state_by_score[s])
    else:
        # 5. Xây dựng rổ đối chứng trung tính (đợt 123)
        for sym, (bars, ex) in all_bars_by_sym.items():
            for i in range(len(bars)):
                od = bar_date(bars[i]).toordinal()
                if od not in event_day_ords:
                    continue
                entry = make_basket_entry(
                    sym,
                    bars,
                    i,
                    ex,
                    min_turnover=MIN_TURNOVER_VND,
                    window=TURNOVER_WINDOW,
                    ks=TARGET_KS,
                )
                if entry is not None:
                    neutral_basket_by_day[od][sym] = entry

        # 6. Tính excess return với rổ trung tính (đợt 123)
        def populate_excess_neutral(events_list: list[SepaEvent]) -> None:
            for e in events_list:
                d_ord = e.day.toordinal()
                day_entries = neutral_basket_by_day.get(d_ord, {})
                peers = basket_for_day(day_entries, e.symbol)
                e.excess = {}
                for k in TARGET_KS:
                    _base, excess, _n = excess_k(e.r.get(k), peers, k, min_control=MIN_CONTROL)
                    e.excess[k] = excess

        for s in range(8):
            populate_excess_neutral(events_transition_by_score[s])
            populate_excess_neutral(events_state_by_score[s])

    # 7. Thống kê và bootstrap cho từng nhóm
    def summarize_group(evs: list[SepaEvent]) -> dict[str, Any]:
        stats = {k: _describe(evs, k) for k in TARGET_KS}
        by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
        for e in evs:
            v = e.excess.get(MAIN_K)
            if v is not None:
                by_month[month_key(e.day)].append(v)
        boot = bootstrap_by_month(
            dict(by_month),
            n=n_bootstrap,
            seed=seed,
            ci_low_pct=CI_LOW_PCT,
            ci_high_pct=CI_HIGH_PCT,
        )
        return {"stats": stats, "boot": boot, "events": evs}

    summary_transitions = {s: summarize_group(events_transition_by_score[s]) for s in range(8)}
    summary_states = {s: summarize_group(events_state_by_score[s]) for s in range(8)}

    # Phân nhóm RS trong 7/7 transition
    evs_score7 = events_transition_by_score[7]
    evs_rs_high = [e for e in evs_score7 if e.rs_rank is not None and e.rs_rank >= 70]
    evs_rs_low = [e for e in evs_score7 if e.rs_rank is not None and e.rs_rank < 70]
    evs_rs_none = [e for e in evs_score7 if e.rs_rank is None]

    summary_rs_high = summarize_group(evs_rs_high)
    summary_rs_low = summarize_group(evs_rs_low)
    summary_rs_none = summarize_group(evs_rs_none)

    # 8. Đánh giá CỔNG CHÍNH (Score 7 Transition tại K=20)
    primary_res = summary_transitions[7]
    p_k20_stats = primary_res["stats"][MAIN_K]
    p_boot = primary_res["boot"]
    p_val = p_boot["p"]
    # Holm adjustment với m=1 cho kiểm định chính trong cổng
    holm_dict = holm_adjust({"score7_transition_k20": p_val}) if p_val is not None else {"score7_transition_k20": False}
    holm_pass = holm_dict.get("score7_transition_k20", False)

    if basket == "trend":
        gate_passed, gate_details = evaluate_gate(
            median_excess_k20=p_k20_stats["median_excess"],
            n_events=p_k20_stats["n_excess"],
            boot_ci=(p_boot["ci_low"], p_boot["ci_high"]),
            holm_pass=holm_pass,
        )
    else:
        gate_passed, gate_details = evaluate_gate_mean(
            mean_excess_k20=p_k20_stats["mean_excess"],
            n_events=p_k20_stats["n_excess"],
            boot_ci=(p_boot["ci_low"], p_boot["ci_high"]),
            holm_pass=holm_pass,
        )

    # Thống kê thứ cấp (§2.4)
    evs_h1 = [
        e for e in evs_score7
        if date(2016, 1, 4) <= e.day <= date(2019, 12, 31) and e.excess.get(MAIN_K) is not None
    ]
    evs_h2 = [
        e for e in evs_score7
        if date(2020, 1, 1) <= e.day <= date(2022, 11, 30) and e.excess.get(MAIN_K) is not None
    ]
    mean_h1 = (sum(e.excess[MAIN_K] for e in evs_h1) / len(evs_h1)) if evs_h1 else None  # type: ignore[arg-type]
    mean_h2 = (sum(e.excess[MAIN_K] for e in evs_h2) / len(evs_h2)) if evs_h2 else None  # type: ignore[arg-type]

    rnet_vals = [e.r_net[MAIN_K] for e in evs_score7 if e.r_net.get(MAIN_K) is not None]
    mean_rnet = (sum(rnet_vals) / len(rnet_vals)) if rnet_vals else None  # type: ignore[arg-type]

    if basket == "neutral":
        basket_sizes = [len(neutral_basket_by_day[od]) for od in event_day_ords]
        basket_stats = {
            "mean_size": (sum(basket_sizes) / len(basket_sizes)) if basket_sizes else 0.0,
            "min_size": min(basket_sizes) if basket_sizes else 0,
            "max_size": max(basket_sizes) if basket_sizes else 0,
        }
    else:
        basket_stats = None

    t_end = time.perf_counter()

    return {
        "basket": basket,
        "n_all_symbols": n_all,
        "n_excluded": len(excluded),
        "n_universe": len(universe),
        "n_symbols_kept": symbols_kept,
        "n_junk_bars": n_junk,
        "summary_transitions": summary_transitions,
        "summary_states": summary_states,
        "summary_rs_high": summary_rs_high,
        "summary_rs_low": summary_rs_low,
        "summary_rs_none": summary_rs_none,
        "gate_passed": gate_passed,
        "gate_details": gate_details,
        "p_val": p_val,
        "holm_pass": holm_pass,
        "split_time": {
            "h1": {"n": len(evs_h1), "mean_excess_k20": mean_h1},
            "h2": {"n": len(evs_h2), "mean_excess_k20": mean_h2},
        },
        "rnet_k20": {"n": len(rnet_vals), "mean": mean_rnet},
        "basket_stats": basket_stats,
        "neutral_basket_by_day": neutral_basket_by_day if basket == "neutral" else None,
        "seconds_total": t_end - t0,
        "seconds_read": read_done - t0,
    }


# --- Định dạng và in báo cáo -----------------------------------------------------

def _fmt(v: float | None, fmt: str = "+.2%") -> str:
    if v is None:
        return "N/A"
    return format(v, fmt)


def format_summary_table(res: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 115)
    lines.append("BẢNG CHÍNH: ĐO LƯỜNG ĐIỂM SEPA (TRANSITION 0 -> s) VÀ TÍNH ĐƠN ĐIỆU")
    lines.append("=" * 115)
    lines.append(
        f"{'Điểm':<5} | {'Số SK':<7} | {'N Excess':<8} | {'Median Excess K=20':<19} | {'Mean Excess K=20':<17} | "
        f"{'CI 95% Bootstrap':<20} | {'Median Ex K=5':<14} | {'Median Ex K=10':<15} | {'Đạt cổng?'}"
    )
    lines.append("-" * 115)

    for s in range(8):
        summ = res["summary_transitions"][s]
        st20 = summ["stats"][20]
        st5 = summ["stats"][5]
        st10 = summ["stats"][10]
        boot = summ["boot"]
        ci_str = f"[{_fmt(boot['ci_low'])}, {_fmt(boot['ci_high'])}]"
        is_gated = "GATED: " + ("ĐẠT" if res["gate_passed"] else "KHÔNG ĐẠT") if s == 7 else "Thứ cấp (N/A)"
        lines.append(
            f"{s:<5} | {st20['n']:<7} | {st20['n_excess']:<8} | {_fmt(st20['median_excess']):<19} | "
            f"{_fmt(st20['mean_excess']):<17} | {ci_str:<20} | {_fmt(st5['median_excess']):<14} | "
            f"{_fmt(st10['median_excess']):<15} | {is_gated}"
        )
    lines.append("=" * 115)
    return "\n".join(lines)


def format_rs_table(res: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 115)
    lines.append("BẢNG TÁCH RS TRONG NHÓM 7/7 (TRANSITION)")
    lines.append("=" * 115)
    lines.append(
        f"{'Nhóm RS':<15} | {'Số SK':<7} | {'N Excess':<8} | {'Median Excess K=20':<19} | {'Mean Excess K=20':<17} | "
        f"{'CI 95% Bootstrap':<20} | {'Median Ex K=5':<14} | {'Median Ex K=10':<15}"
    )
    lines.append("-" * 115)

    groups = [
        ("RS >= 70", res["summary_rs_high"]),
        ("RS < 70", res["summary_rs_low"]),
        ("Tất cả 7/7", res["summary_transitions"][7]),
    ]
    for name, summ in groups:
        st20 = summ["stats"][20]
        st5 = summ["stats"][5]
        st10 = summ["stats"][10]
        boot = summ["boot"]
        ci_str = f"[{_fmt(boot['ci_low'])}, {_fmt(boot['ci_high'])}]"
        lines.append(
            f"{name:<15} | {st20['n']:<7} | {st20['n_excess']:<8} | {_fmt(st20['median_excess']):<19} | "
            f"{_fmt(st20['mean_excess']):<17} | {ci_str:<20} | {_fmt(st5['median_excess']):<14} | "
            f"{_fmt(st10['median_excess']):<15}"
        )
    lines.append("=" * 115)
    return "\n".join(lines)


def format_state_table(res: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 115)
    lines.append("BIẾN THỂ SỰ KIỆN: TRẠNG THÁI KÉO DÀI (MỌI NGÀY Ở ĐIỂM s, COOLDOWN = 20) — §2.1")
    lines.append("=" * 115)
    lines.append(
        f"{'Điểm':<5} | {'Số SK':<7} | {'N Excess':<8} | {'Median Excess K=20':<19} | {'Mean Excess K=20':<17} | "
        f"{'CI 95% Bootstrap':<20} | {'Median Ex K=5':<14} | {'Median Ex K=10':<15}"
    )
    lines.append("-" * 115)

    for s in range(8):
        summ = res["summary_states"][s]
        st20 = summ["stats"][20]
        st5 = summ["stats"][5]
        st10 = summ["stats"][10]
        boot = summ["boot"]
        ci_str = f"[{_fmt(boot['ci_low'])}, {_fmt(boot['ci_high'])}]"
        lines.append(
            f"{s:<5} | {st20['n']:<7} | {st20['n_excess']:<8} | {_fmt(st20['median_excess']):<19} | "
            f"{_fmt(st20['mean_excess']):<17} | {ci_str:<20} | {_fmt(st5['median_excess']):<14} | "
            f"{_fmt(st10['median_excess']):<15}"
        )
    lines.append("=" * 115)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Đo lường lợi thế điểm SEPA (Brief đợt 120 & 123)")
    ap.add_argument("--dsn", default=None, help="DSN Postgres (mặc định lấy từ .env)")
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--no-exclusions", action="store_true", help="Không loại mã trong exclusions.txt")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số mã (0 = tất cả)")
    ap.add_argument(
        "--basket",
        choices=["trend", "neutral"],
        default="trend",
        help="Chế độ rổ: trend (đợt 120, rổ chỉ 7/7) hoặc neutral (đợt 123, rổ trung tính)",
    )
    ap.add_argument("--output-dir", default=None, help="Thư mục ghi kết quả")
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    args = ap.parse_args()

    storage = Storage(resolve_dsn(args.dsn))

    print(f"=== BẮT ĐẦU CHẠY PHÉP ĐO ĐIỂM SEPA (basket={args.basket}, no_exclusions={args.no_exclusions}) ===")
    res = run_sepa_measurement(
        storage=storage,
        exclude_file=args.exclude_file,
        no_exclusions=args.no_exclusions,
        limit=args.limit,
        n_bootstrap=args.n_bootstrap,
        seed=args.bootstrap_seed,
        basket=args.basket,
    )

    tbl_summary = format_summary_table(res)
    tbl_rs = format_rs_table(res)
    tbl_state = format_state_table(res)

    print("\n" + tbl_summary)
    print("\n" + tbl_rs)
    print("\n" + tbl_state)

    gd = res["gate_details"]
    b7 = res["summary_transitions"][7]["boot"]

    if args.basket == "trend":
        print("\n=== KẾT QUẢ CỔNG CHÍNH (Score 7/7 Transition tại K=20) ===")
        print(f"- (1) Trung vị excess K=20 > 0: {gd['cond1_median_gt_0']} ({_fmt(res['summary_transitions'][7]['stats'][20]['median_excess'])})")
        print(f"- (2) Số sự kiện hợp lệ >= 100: {gd['cond2_min_events']} ({res['summary_transitions'][7]['stats'][20]['n_excess']})")
        print(f"- (3) KTC 95% bootstrap loại 0: {gd['cond3_ci_excludes_0']} ([{_fmt(b7['ci_low'])}, {_fmt(b7['ci_high'])}])")
        print(f"- (4) Đạt sau Holm (m=1): {gd['cond4_holm_pass']} (p_val = {_fmt(res['p_val'], '.4f')})")
        print(f"=> KẾT LUẬN CỔNG: {'ĐẠT' if res['gate_passed'] else 'KHÔNG ĐẠT'}")
    else:
        print("\n=== KẾT QUẢ CỔNG CHÍNH — RỔ TRUNG TÍNH (Score 7/7 Transition tại K=20) ===")
        print(f"- (1) Trung bình excess K=20 > 0: {gd['cond1_mean_gt_0']} ({_fmt(res['summary_transitions'][7]['stats'][20]['mean_excess'])})")
        print(f"- (2) Số sự kiện hợp lệ >= 100: {gd['cond2_min_events']} ({res['summary_transitions'][7]['stats'][20]['n_excess']})")
        print(f"- (3) KTC 95% bootstrap loại 0: {gd['cond3_ci_excludes_0']} ([{_fmt(b7['ci_low'])}, {_fmt(b7['ci_high'])}])")
        print(f"- (4) Đạt sau Holm (m=1): {gd['cond4_holm_pass']} (p_val = {_fmt(res['p_val'], '.4f')})")
        print(f"=> KẾT LUẬN CỔNG: {'ĐẠT' if res['gate_passed'] else 'KHÔNG ĐẠT'}")

        print("\n=== THỐNG KÊ THỨ CẤP (RỔ TRUNG TÍNH) ===")
        b_stats = res.get("basket_stats")
        if b_stats:
            print(f"- Kích thước rổ trung tính: trung bình {b_stats['mean_size']:.1f} mã/ngày (min: {b_stats['min_size']}, max: {b_stats['max_size']})")
        st = res.get("split_time", {})
        h1 = st.get("h1", {})
        h2 = st.get("h2", {})
        print("- Chia đôi thời gian (Score 7 Transition K=20):")
        print(f"  + 2016-01-04 -> 2019-12-31: N = {h1.get('n', 0)}, Mean Excess = {_fmt(h1.get('mean_excess_k20'))}")
        print(f"  + 2020-01-01 -> 2022-11-30: N = {h2.get('n', 0)}, Mean Excess = {_fmt(h2.get('mean_excess_k20'))}")
        rnet = res.get("rnet_k20", {})
        print(f"- Lợi suất ròng (r_net) K=20 trung bình nhóm 7/7: {_fmt(rnet.get('mean'))} (N = {rnet.get('n', 0)})")

    # Ghi ra file
    if args.output_dir is not None:
        out_dir = pathlib.Path(args.output_dir)
    elif args.basket == "neutral":
        out_dir = pathlib.Path("docs/superpowers/research/dot-123-output")
    else:
        out_dir = pathlib.Path("docs/superpowers/research/dot-120-output")

    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_no_exclusions" if args.no_exclusions else "_with_exclusions"

    summary_file = out_dir / f"summary_table{suffix}.txt"
    full_output_file = out_dir / f"full_run_output{suffix}.txt"

    summary_content = f"{tbl_summary}\n\n{tbl_rs}\n\n{tbl_state}"
    summary_file.write_text(summary_content, encoding="utf-8")

    full_content = []
    full_content.append(f"Chạy lúc: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    full_content.append(f"Vũ trụ: {res['n_universe']} mã (tổng: {res['n_all_symbols']}, loại: {res['n_excluded']})")
    full_content.append(f"Số mã hợp lệ: {res['n_symbols_kept']}, số nến rác bỏ: {res['n_junk_bars']}")
    full_content.append(f"Thời gian: {res['seconds_total']:.1f}s (đọc dữ liệu: {res['seconds_read']:.1f}s)\n")
    full_content.append(summary_content)

    if args.basket == "trend":
        full_content.append("\n=== KẾT LUẬN CỔNG ===")
        full_content.append(f"Cổng chính: {'ĐẠT' if res['gate_passed'] else 'KHÔNG ĐẠT'}")
        for k, v in gd.items():
            full_content.append(f"  {k}: {v}")
    else:
        full_content.append("\n=== KẾT LUẬN CỔNG (RỔ TRUNG TÍNH) ===")
        full_content.append(f"Cổng chính: {'ĐẠT' if res['gate_passed'] else 'KHÔNG ĐẠT'}")
        for k, v in gd.items():
            full_content.append(f"  {k}: {v}")
        full_content.append("\n=== THỐNG KÊ THỨ CẤP (RỔ TRUNG TÍNH) ===")
        b_stats = res.get("basket_stats")
        if b_stats:
            full_content.append(f"- Kích thước rổ trung tính: trung bình {b_stats['mean_size']:.1f} mã/ngày (min: {b_stats['min_size']}, max: {b_stats['max_size']})")
        st = res.get("split_time", {})
        h1 = st.get("h1", {})
        h2 = st.get("h2", {})
        full_content.append("- Chia đôi thời gian (Score 7 Transition K=20):")
        full_content.append(f"  + 2016-01-04 -> 2019-12-31: N = {h1.get('n', 0)}, Mean Excess = {_fmt(h1.get('mean_excess_k20'))}")
        full_content.append(f"  + 2020-01-01 -> 2022-11-30: N = {h2.get('n', 0)}, Mean Excess = {_fmt(h2.get('mean_excess_k20'))}")
        rnet = res.get("rnet_k20", {})
        full_content.append(f"- Lợi suất ròng (r_net) K=20 trung bình nhóm 7/7: {_fmt(rnet.get('mean'))} (N = {rnet.get('n', 0)})")

    full_output_file.write_text("\n".join(full_content), encoding="utf-8")
    print(f"\nĐã ghi kết quả ra: {summary_file} và {full_output_file}")


if __name__ == "__main__":
    main()
