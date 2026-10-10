"""Cong cu sang loc 6 cap dac trung order flow VN30F theo footprint (Brief dot 182).

Tach ham thuan de dot 183 (crypto) dung lai nguyen van.
Cac ham gom:
1. `imbalance_levels(fp, ratio=3, min_vol=5, denom_floor=1)`: tim imbalance ask/bid tren footprint.
2. `build_footprint_bars`: dung danh sach nen footprint 5 phut tu luong tin TRADE.
3. Bo phat hien su kien E1 (phan ky CVD), E2 (phan ky delta trong nen), E3 (bo doi hap thu -> khoi xuong).
4. `calculate_event_targets`: tinh bien muc tieu y tren cac chan troi H in {15, 30}.
5. `filter_non_overlapping_events`: loc su kien khong chong lan.
6. `block_bootstrap_p_value`: bootstrap theo khoi phien kiem dinh p mot phia.
7. `evaluate_pair_criteria`: cong kiem IS §1.4.
8. `main`: cong ngay chong nhin truoc (today < 2026-12-01 thi dung va tra ma 2).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import scipy.stats as st

# Ep ma hoa UTF-8 cho stdout/stderr tren Windows de tranh loi cp1252
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if getattr(_stream, "encoding", None) and _stream.encoding.lower() not in ("utf-8", "utf8"):
        _stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_orderbook_features import (
    CONTINUOUS_AFTERNOON_END,
    parse_recv_ts,
    parse_trading_time,
)
from scripts.record_vn30f_orderbook import (
    AFTERNOON_START,
    MORNING_END,
    MORNING_START,
    classify_message,
)
from scripts.screen_vn30f_orderbook import (
    CONTROL_MIN_RHO,
    DEFAULT_UNLOCK_LOG_PATH,
    ECONOMIC_HURDLE_FACTOR,
    HOLDOUT_START_DATE,
    MIN_INDEP_EVENTS,
    MIN_SIDE_EVENTS,
    compute_roundtrip_cost,
)
from trading.calendar_vn import TZ
from trading.metrics import calculate_percentile

__all__ = [
    "ALPHA_PER_PAIR",
    "EVENT_NAMES",
    "HORIZONS",
    "SLIPPAGE_PTS",
    "BarSummary",
    "FootprintBar",
    "OrderFlowEvent",
    "block_bootstrap_p_value",
    "build_footprint_bars",
    "calculate_event_targets",
    "check_control_variable_orderflow",
    "compute_economic_hurdle",
    "detect_e1_events",
    "detect_e2_events",
    "detect_e3_events",
    "evaluate_pair_criteria",
    "filter_non_overlapping_events",
    "imbalance_levels",
    "load_holdout_sessions",
    "main",
    "verify_holdout_log_unlocked",
]

# --- Hang so dang ky truoc (§1.1, §1.3, §1.4) --------------------------------------

EVENT_NAMES: tuple[str, ...] = ("E1", "E2", "E3")
HORIZONS: tuple[int, ...] = (15, 30)
ALPHA_PER_PAIR: float = 0.05 / 6.0  # 0.008333333333333333
SLIPPAGE_PTS: float = 0.2  # 1 buoc gia moi chieu (0.1 x 2)
RATIO_IMBALANCE: float = 3.0
MIN_VOL_IMBALANCE: float = 5.0
DENOM_FLOOR_IMBALANCE: float = 1.0


# --- Cau truc du lieu -------------------------------------------------------------


@dataclass
class BarSummary:
    """Nen tom tat dung cho cac bo phat hien su kien E1/E2/E3 (§2)."""

    session_id: Any
    block_id: Any
    bar_idx: int
    t_start: datetime
    t_end: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    close_k: int | None
    delta: float
    cvd: float
    ask_k_min: int | None
    ask_k_max: int | None
    bid_k_min: int | None
    bid_k_max: int | None


@dataclass
class FootprintBar(BarSummary):
    """Nen footprint day du kem thong tin phan bo buy/sell tren tung muc gia."""

    buy: float = 0.0
    sell: float = 0.0
    fp: dict[int, tuple[float, float]] | None = None
    trade_count: int = 0


@dataclass
class OrderFlowEvent:
    """Su kien order flow duoc phat hien tai cuoi nen t."""

    event_type: str  # "E1", "E2", "E3"
    direction: int  # +1 (mua), -1 (ban)
    session_id: Any
    block_id: Any
    bar_idx: int
    t_end: datetime
    close: float
    target_time: datetime | None = None
    exit_price: float | None = None
    y: float | None = None


# --- 1. Imbalance levels tren footprint (§1.3, §2) ---------------------------------


def imbalance_levels(
    fp: dict[int, tuple[float, float]],
    ratio: float = RATIO_IMBALANCE,
    min_vol: float = MIN_VOL_IMBALANCE,
    denom_floor: float = DENOM_FLOOR_IMBALANCE,
    same_level_instead_of_diagonal: bool = False,
) -> tuple[list[int], list[int]]:
    """Tim cac muc ask imbalance va bid imbalance trong footprint.

    fp: dict map muc gia nguyen k -> (buy_k, sell_k).
    - Ask imbalance tai k: buy[k] >= ratio * max(sell[k-1], denom_floor) va buy[k] >= min_vol.
    - Bid imbalance tai k: sell[k] >= ratio * max(buy[k+1], denom_floor) va sell[k] >= min_vol.
    Tra ve: (ask_ks, bid_ks) da sap xep tang dan.
    """
    ask_ks: list[int] = []
    bid_ks: list[int] = []

    for k, (buy_k, sell_k) in fp.items():
        if same_level_instead_of_diagonal:
            # Phep pha hoai (ii): so cung muc k thay vi cheo
            opp_sell = fp.get(k, (0.0, 0.0))[1]
            opp_buy = fp.get(k, (0.0, 0.0))[0]
        else:
            # So cheo chuan: buy[k] voi sell[k-1]; sell[k] voi buy[k+1]
            opp_sell = fp.get(k - 1, (0.0, 0.0))[1]
            opp_buy = fp.get(k + 1, (0.0, 0.0))[0]

        if buy_k >= ratio * max(opp_sell, denom_floor) and buy_k >= min_vol:
            ask_ks.append(k)

        if sell_k >= ratio * max(opp_buy, denom_floor) and sell_k >= min_vol:
            bid_ks.append(k)

    return sorted(ask_ks), sorted(bid_ks)


# --- 2. Dung nen footprint 5 phut tu luong tin TRADE (§1.2) ------------------------


def _session_grid_5m(session_date: date) -> list[tuple[int, str, datetime, datetime]]:
    """Tao luoi 48 nen 5 phut: 30 nen sang (09:00-11:30) + 18 nen chieu (13:00-14:30)."""
    grid: list[tuple[int, str, datetime, datetime]] = []

    # Sang: 09:00 -> 11:30 (30 nen)
    cur = datetime.combine(session_date, MORNING_START, tzinfo=TZ)
    end_m = datetime.combine(session_date, MORNING_END, tzinfo=TZ)
    idx = 0
    while cur < end_m:
        nxt = cur + timedelta(minutes=5)
        grid.append((idx, "morning", cur, nxt))
        cur = nxt
        idx += 1

    # Chieu: 13:00 -> 14:30 (18 nen)
    cur = datetime.combine(session_date, AFTERNOON_START, tzinfo=TZ)
    end_a = datetime.combine(session_date, CONTINUOUS_AFTERNOON_END, tzinfo=TZ)
    while cur < end_a:
        nxt = cur + timedelta(minutes=5)
        grid.append((idx, "afternoon", cur, nxt))
        cur = nxt
        idx += 1

    return grid


def build_footprint_bars(
    messages: Iterable[dict[str, Any]],
    session_date: date,
    stats: dict[str, Any] | None = None,
    use_recv_ts_instead_of_trading_time: bool = False,
    same_level_instead_of_diagonal: bool = False,
) -> tuple[list[FootprintBar], dict[str, Any]]:
    """Dung 48 nen footprint 5 phut cho mot phien giao dich.

    Chi nhan tin classify_message(msg) == 'TRADE', side in {'B', 'S'}, quantity > 0.
    CVD reset ve 0 tai dau phien.
    """
    if stats is None:
        stats = {}
    stats.setdefault("total_messages", 0)
    stats.setdefault("trades_used", 0)
    stats.setdefault("dropped_u_or_zero", 0)
    stats.setdefault("outside_session", 0)
    stats.setdefault("bad_time", 0)
    stats.setdefault("quotes_or_other", 0)

    grid = _session_grid_5m(session_date)
    # Map (t_start, t_end) -> bar index
    # Cac moc gioi han
    m_start = datetime.combine(session_date, MORNING_START, tzinfo=TZ)
    m_end = datetime.combine(session_date, MORNING_END, tzinfo=TZ)
    a_start = datetime.combine(session_date, AFTERNOON_START, tzinfo=TZ)
    a_end = datetime.combine(session_date, CONTINUOUS_AFTERNOON_END, tzinfo=TZ)

    # Thu thap tin TRADE hop le
    valid_trades: list[dict[str, Any]] = []

    for msg in messages:
        stats["total_messages"] += 1
        if not isinstance(msg, dict):
            continue

        cat = classify_message(msg)
        if cat != "TRADE":
            stats["quotes_or_other"] += 1
            continue

        side = str(msg.get("side") or "").strip().upper()
        try:
            qty = float(msg.get("quantity") or 0.0)
            price = float(msg.get("price") or 0.0)
        except (ValueError, TypeError):
            stats["dropped_u_or_zero"] += 1
            continue

        if side not in ("B", "S") or qty <= 0.0 or price <= 0.0:
            stats["dropped_u_or_zero"] += 1
            continue

        if use_recv_ts_instead_of_trading_time:
            # Phep pha hoai (i): gom theo recv_ts thay vi trading_time
            ts = parse_recv_ts(msg.get("recv_ts"))
        else:
            ts = parse_trading_time(msg.get("trading_time"))

        if ts is None:
            stats["bad_time"] += 1
            continue

        # Kiem tra khung lien tuc
        if not ((m_start <= ts < m_end) or (a_start <= ts < a_end)):
            stats["outside_session"] += 1
            continue

        stats["trades_used"] += 1
        valid_trades.append(
            {
                "ts": ts,
                "price": price,
                "quantity": qty,
                "side": side,
            }
        )

    # Sap xep tin theo thoi gian giao dich (on dinh thu tu xuat hien)
    valid_trades.sort(key=lambda t: t["ts"])

    # Nhom tin vao tung nen trong 48 nen
    # Moi nen: list tin
    trades_by_bar: list[list[dict[str, Any]]] = [[] for _ in range(len(grid))]

    for t in valid_trades:
        ts = t["ts"]
        if m_start <= ts < m_end:
            mins = int((ts - m_start).total_seconds() // 60)
            b_idx = mins // 5
            if 0 <= b_idx < 30:
                trades_by_bar[b_idx].append(t)
        elif a_start <= ts < a_end:
            mins = int((ts - a_start).total_seconds() // 60)
            b_idx = 30 + (mins // 5)
            if 30 <= b_idx < 48:
                trades_by_bar[b_idx].append(t)

    # Dung cac FootprintBar
    bars: list[FootprintBar] = []
    accum_cvd = 0.0

    for idx, block_id, t_start, t_end in grid:
        t_list = trades_by_bar[idx]
        if not t_list:
            # Nen khong co tin khop
            bars.append(
                FootprintBar(
                    session_id=session_date,
                    block_id=block_id,
                    bar_idx=idx,
                    t_start=t_start,
                    t_end=t_end,
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
                    buy=0.0,
                    sell=0.0,
                    fp={},
                    trade_count=0,
                )
            )
            continue

        o = t_list[0]["price"]
        c = t_list[-1]["price"]
        h = max(t["price"] for t in t_list)
        low = min(t["price"] for t in t_list)
        close_k = round(c * 10.0)

        tot_buy = 0.0
        tot_sell = 0.0
        fp_dict: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])

        for t in t_list:
            p_k = round(t["price"] * 10.0)
            q = t["quantity"]
            if t["side"] == "B":
                tot_buy += q
                fp_dict[p_k][0] += q
            else:
                tot_sell += q
                fp_dict[p_k][1] += q

        bar_delta = tot_buy - tot_sell
        accum_cvd += bar_delta

        fp_tuple = {k: (v[0], v[1]) for k, v in fp_dict.items()}
        ask_ks, bid_ks = imbalance_levels(
            fp_tuple,
            same_level_instead_of_diagonal=same_level_instead_of_diagonal,
        )

        bars.append(
            FootprintBar(
                session_id=session_date,
                block_id=block_id,
                bar_idx=idx,
                t_start=t_start,
                t_end=t_end,
                open=o,
                high=h,
                low=low,
                close=c,
                close_k=close_k,
                delta=bar_delta,
                cvd=accum_cvd,
                ask_k_min=ask_ks[0] if ask_ks else None,
                ask_k_max=ask_ks[-1] if ask_ks else None,
                bid_k_min=bid_ks[0] if bid_ks else None,
                bid_k_max=bid_ks[-1] if bid_ks else None,
                buy=tot_buy,
                sell=tot_sell,
                fp=fp_tuple,
                trade_count=len(t_list),
            )
        )

    return bars, stats


# --- 3. Bo phat hien su kien E1, E2, E3 (§1.3, §2) ----------------------------------


def detect_e1_events(bars: Sequence[BarSummary]) -> list[OrderFlowEvent]:
    """Phat hien su kien E1 (Phan ky CVD).

    Ban (d = -1): close_t > max(11 close truoc trong cung phien) va cvd_t < max(11 cvd truoc).
    Mua (d = +1): close_t < min(11 close truoc trong cung phien) va cvd_t > min(11 cvd truoc).
    Can du 11 nen truoc deu co gia trong cung session_id.
    """
    events: list[OrderFlowEvent] = []

    for t in range(len(bars)):
        curr = bars[t]
        if curr.close is None:
            continue

        if t < 11:
            continue

        prev_11 = bars[t - 11 : t]
        # Kiem tra tat ca 11 nen truoc deu thuoc cung session_id
        if not all(b.session_id == curr.session_id for b in prev_11):
            continue

        # Kiem tra tat ca 11 nen truoc deu co gia
        if not all(b.close is not None for b in prev_11):
            continue

        prev_closes = [b.close for b in prev_11 if b.close is not None]
        prev_cvds = [b.cvd for b in prev_11]

        max_close = max(prev_closes)
        min_close = min(prev_closes)
        max_cvd = max(prev_cvds)
        min_cvd = min(prev_cvds)

        # Ban: d = -1
        if curr.close > max_close and curr.cvd < max_cvd:
            events.append(
                OrderFlowEvent(
                    event_type="E1",
                    direction=-1,
                    session_id=curr.session_id,
                    block_id=curr.block_id,
                    bar_idx=curr.bar_idx,
                    t_end=curr.t_end,
                    close=curr.close,
                )
            )
        # Mua: d = +1
        elif curr.close < min_close and curr.cvd > min_cvd:
            events.append(
                OrderFlowEvent(
                    event_type="E1",
                    direction=+1,
                    session_id=curr.session_id,
                    block_id=curr.block_id,
                    bar_idx=curr.bar_idx,
                    t_end=curr.t_end,
                    close=curr.close,
                )
            )

    return events


def detect_e2_events(
    bars: Sequence[BarSummary],
    include_current_session: bool = False,
    reverse_direction: bool = False,
) -> list[OrderFlowEvent]:
    """Phat hien su kien E2 (Phan ky delta trong nen theo video §6.2).

    - Nguong |delta| >= p90 cua 5 phien hop le lien truoc (khong gom phien hien tai).
    - delta > 0 va close < open (nho hon han) => Mua, d = +1 (nguoi ban bi hap thu).
    - delta < 0 va close > open (lon hon han) => Ban, d = -1.
    - close == open => khong co su kien.
    """
    events: list[OrderFlowEvent] = []

    # Phan chia bars theo session_id
    sessions_order: list[Any] = []
    bars_by_session: dict[Any, list[BarSummary]] = defaultdict(list)
    for b in bars:
        if b.session_id not in bars_by_session:
            sessions_order.append(b.session_id)
        bars_by_session[b.session_id].append(b)

    for s_idx, s_id in enumerate(sessions_order):
        # Can it nhat 5 phien truoc
        if s_idx < 5:
            continue

        if include_current_session:
            # Phep pha hoai (iii): nguong E2 gom ca phien hien tai
            hist_sessions = sessions_order[s_idx - 5 : s_idx + 1]
        else:
            # Chuan: chi lay 5 phien truoc (khong gom phien hien tai)
            hist_sessions = sessions_order[s_idx - 5 : s_idx]

        # Thu thap |delta| cua moi nen co giao dich trong 5 phien truoc
        deltas_pool: list[float] = []
        for h_id in hist_sessions:
            for b in bars_by_session[h_id]:
                if b.close is not None and b.open is not None:
                    deltas_pool.append(abs(b.delta))

        if not deltas_pool:
            continue

        p90 = calculate_percentile(deltas_pool, 90.0)

        for curr in bars_by_session[s_id]:
            if curr.close is None or curr.open is None:
                continue

            if abs(curr.delta) < p90:
                continue

            if curr.close == curr.open:
                continue

            if curr.delta > 0 and curr.close < curr.open:
                # Bên bán bị hấp thụ -> Mua (d = +1)
                d = -1 if reverse_direction else +1
            elif curr.delta < 0 and curr.close > curr.open:
                # Bên mua bị hấp thụ -> Bán (d = -1)
                d = +1 if reverse_direction else -1
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


def detect_e3_events(bars: Sequence[BarSummary]) -> list[OrderFlowEvent]:
    """Phat hien su kien E3 (Bo doi hap thu -> khoi xuong theo video §6.1).

    Xet tai cuoi nen t:
    - Nen t-1 va t phai lien nhau trong cung block_id (khung lien tuc).
    - t-1 hap thu ban va t khoi xuong mua => d = +1.
    - t-1 hap thu mua va t khoi xuong ban => d = -1.
    """
    events: list[OrderFlowEvent] = []

    for t in range(1, len(bars)):
        prev = bars[t - 1]
        curr = bars[t]

        # Phai cung session_id va cung block_id
        if prev.session_id != curr.session_id or prev.block_id != curr.block_id:
            continue

        # Ca 2 nen phai co giao dich
        if prev.close is None or curr.close is None or prev.close_k is None or curr.close_k is None:
            continue

        # Trang thai nen t-1
        # Hap thu mua: co ask imbalance va close < gia ask imbalance thap nhat
        prev_absorbed_buy = (prev.ask_k_min is not None) and (prev.close_k < prev.ask_k_min)
        # Hap thu ban: co bid imbalance va close > gia bid imbalance cao nhat
        prev_absorbed_sell = (prev.bid_k_max is not None) and (prev.close_k > prev.bid_k_max)

        # Trang thai nen t
        # Khoi xuong mua: co ask imbalance, close >= gia ask imbalance cao nhat, va KHONG co bid imbalance
        curr_initiative_buy = (
            (curr.ask_k_max is not None)
            and (curr.close_k >= curr.ask_k_max)
            and (curr.bid_k_min is None)
        )
        # Khoi xuong ban: co bid imbalance, close <= gia bid imbalance thap nhat, va KHONG co ask imbalance
        curr_initiative_sell = (
            (curr.bid_k_min is not None)
            and (curr.close_k <= curr.bid_k_min)
            and (curr.ask_k_max is None)
        )

        if prev_absorbed_sell and curr_initiative_buy:
            events.append(
                OrderFlowEvent(
                    event_type="E3",
                    direction=+1,
                    session_id=curr.session_id,
                    block_id=curr.block_id,
                    bar_idx=curr.bar_idx,
                    t_end=curr.t_end,
                    close=curr.close,
                )
            )
        elif prev_absorbed_buy and curr_initiative_sell:
            events.append(
                OrderFlowEvent(
                    event_type="E3",
                    direction=-1,
                    session_id=curr.session_id,
                    block_id=curr.block_id,
                    bar_idx=curr.bar_idx,
                    t_end=curr.t_end,
                    close=curr.close,
                )
            )

    return events


# --- 4. Tinh bien muc tieu & Loc khong chong lan (§1.3) -----------------------------


def calculate_event_targets(
    events: Sequence[OrderFlowEvent],
    price_lookup: Callable[[datetime], float | None],
    h_minutes: int,
) -> list[OrderFlowEvent]:
    """Tinh bien muc tieu y = d * (P(t_end + H) - close_t).

    Bo su kien neu t_end + H vuot qua ket thuc khung dang chua no (11:30 hoac 14:30).
    """
    valid_events: list[OrderFlowEvent] = []

    for e in events:
        target_time = e.t_end + timedelta(minutes=h_minutes)

        # Kiem tra ket thuc khung
        s_date = e.t_end.date()
        if e.block_id == "morning":
            block_end = datetime.combine(s_date, MORNING_END, tzinfo=TZ)
        else:
            block_end = datetime.combine(s_date, CONTINUOUS_AFTERNOON_END, tzinfo=TZ)

        if target_time > block_end:
            # Vuot qua ket thuc khung -> bo qua
            continue

        exit_p = price_lookup(target_time)
        if exit_p is None:
            continue

        y_val = e.direction * (exit_p - e.close)
        valid_events.append(
            OrderFlowEvent(
                event_type=e.event_type,
                direction=e.direction,
                session_id=e.session_id,
                block_id=e.block_id,
                bar_idx=e.bar_idx,
                t_end=e.t_end,
                close=e.close,
                target_time=target_time,
                exit_price=exit_p,
                y=y_val,
            )
        )

    return valid_events


def filter_non_overlapping_events(
    events: Sequence[OrderFlowEvent],
    h_minutes: int,
) -> list[OrderFlowEvent]:
    """Loc khong chong lan: su kien moi chi duoc nhan khi t_end >= t_end_prev + H."""
    if not events:
        return []

    sorted_events = sorted(events, key=lambda e: e.t_end)
    accepted: list[OrderFlowEvent] = []
    last_accepted_end: datetime | None = None

    for e in sorted_events:
        if last_accepted_end is None or e.t_end >= last_accepted_end + timedelta(minutes=h_minutes):
            accepted.append(e)
            last_accepted_end = e.t_end

    return accepted


# --- 5. Kiem dinh thong ke Bootstrap & Cong tieu chuan (§1.4) ----------------------


def block_bootstrap_p_value(
    events: Sequence[OrderFlowEvent],
    n_bootstrap: int = 2000,
    seed: int = 42,
    resample_by_event_instead_of_session: bool = False,
) -> tuple[float, np.ndarray]:
    """Bootstrap theo khoi phien kiem dinh p mot phia cho trung binh y.

    Tra ve (p_value, bootstrap_means).
    """
    if not events:
        return 1.0, np.zeros(n_bootstrap)

    y_vals = np.array([e.y for e in events if e.y is not None], dtype=float)
    if len(y_vals) == 0:
        return 1.0, np.zeros(n_bootstrap)

    obs_mean = float(np.mean(y_vals))
    rng = np.random.default_rng(seed)

    if resample_by_event_instead_of_session:
        # Phep pha hoai (v): lay lai theo su kien thay vi theo phien
        y_centered = y_vals - obs_mean
        n = len(y_vals)
        boot_means = np.empty(n_bootstrap, dtype=float)
        for b in range(n_bootstrap):
            sample = rng.choice(y_centered, size=n, replace=True)
            boot_means[b] = float(np.mean(sample))
        p_val = float(np.mean(boot_means >= obs_mean))
        return p_val, boot_means

    # Gom su kien theo session_id
    sessions_map: dict[Any, list[float]] = defaultdict(list)
    for e in events:
        if e.y is not None:
            sessions_map[e.session_id].append(float(e.y))

    unique_sessions = list(sessions_map.keys())
    m = len(unique_sessions)
    if m == 0:
        return 1.0, np.zeros(n_bootstrap)

    # Centered y theo session
    centered_sessions = [np.array(sessions_map[s], dtype=float) - obs_mean for s in unique_sessions]

    boot_means = np.empty(n_bootstrap, dtype=float)
    for b in range(n_bootstrap):
        sampled_indices = rng.choice(m, size=m, replace=True)
        total_y = sum(float(np.sum(centered_sessions[idx])) for idx in sampled_indices)
        total_count = sum(len(centered_sessions[idx]) for idx in sampled_indices)
        boot_means[b] = (total_y / total_count) if total_count > 0 else 0.0

    p_val = float(np.mean(boot_means >= obs_mean))
    return p_val, boot_means


def check_control_variable_orderflow(
    bars: Sequence[BarSummary],
    min_rho: float = CONTROL_MIN_RHO,
) -> tuple[bool, float]:
    """Kiem doi chung truoc khi do: Spearman rho giua delta va close - open cung nen > 0.3."""
    deltas: list[float] = []
    rets: list[float] = []

    for b in bars:
        if b.close is not None and b.open is not None:
            deltas.append(b.delta)
            rets.append(b.close - b.open)

    if len(deltas) < 10:
        return False, 0.0

    res = st.spearmanr(deltas, rets)
    rho = float(res.statistic if hasattr(res, "statistic") else res.correlation)
    passed = rho > min_rho
    return passed, rho


def compute_economic_hurdle(median_close: float) -> float:
    """Tinh nguong kinh te: hurdle = 1.5 * (compute_roundtrip_cost(median_close) + 0.2)."""
    cost_rt = compute_roundtrip_cost(median_close)
    return float(ECONOMIC_HURDLE_FACTOR * (cost_rt + SLIPPAGE_PTS))


def evaluate_pair_criteria(
    events: Sequence[OrderFlowEvent],
    hurdle: float,
    control_rho: float,
    p_val: float,
    min_indep_events: int = MIN_INDEP_EVENTS,
    min_side_events: int = MIN_SIDE_EVENTS,
    alpha_threshold: float = ALPHA_PER_PAIR,
    control_min_rho: float = CONTROL_MIN_RHO,
) -> dict[str, Any]:
    """Danh gia mot cap theo 3 dieu kien cua §1.4.

    1. Du mau: >= 100 su kien, moi huong >= 30.
    2. Y nghia thong ke: p < 0.05 / 6.
    3. Du bu chi phi: mean_y >= hurdle.
    Kiem doi chung: rho > 0.3.
    """
    n_events = len(events)
    n_buy = sum(1 for e in events if e.direction > 0)
    n_sell = sum(1 for e in events if e.direction < 0)

    y_vals = [e.y for e in events if e.y is not None]
    mean_y = float(np.mean(y_vals)) if y_vals else 0.0

    cond_control = control_rho > control_min_rho
    cond1_sample = (n_events >= min_indep_events) and (n_buy >= min_side_events) and (n_sell >= min_side_events)
    cond2_stat = p_val < alpha_threshold
    cond3_hurdle = mean_y >= hurdle

    is_passed = cond_control and cond1_sample and cond2_stat and cond3_hurdle

    return {
        "passed": is_passed,
        "n_events": n_events,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "mean_y": mean_y,
        "hurdle": hurdle,
        "p_val": p_val,
        "control_rho": control_rho,
        "cond_control": cond_control,
        "cond1_sample": cond1_sample,
        "cond2_stat": cond2_stat,
        "cond3_hurdle": cond3_hurdle,
    }


# --- 6. Niem phong Holdout (§1.1, §1.4) -------------------------------------------


def verify_holdout_log_unlocked(
    log_path: Path | str = DEFAULT_UNLOCK_LOG_PATH,
    tag: str = "đợt 182",
) -> bool:
    """Kiem tra log mo niem phong holdout-unlock-log.md co dong dot 182 chua."""
    p = Path(log_path)
    if not p.exists():
        raise RuntimeError(f"File log mo niem phong khong ton tai: {p}")

    text = p.read_text(encoding="utf-8")
    for line in text.splitlines():
        if tag.lower() in line.lower():
            return True

    raise RuntimeError(
        f"Vi pham niem phong: chua co dong mo khoa '{tag}' trong {log_path}"
    )


def load_holdout_sessions(
    data_dir: Path | str = "data/orderbook",
    log_path: Path | str = DEFAULT_UNLOCK_LOG_PATH,
) -> list[Any]:
    """Doc phien Holdout. BAT BUOC kiem tra dong log dot 182 truoc khi doc bat ky file nao."""
    verify_holdout_log_unlocked(log_path, tag="đợt 182")
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return []
    # Khong tu tien doc file that truoc 01/12
    return []


# --- 7. CLI Main Runner & Cong ngay chong nhin truoc (§1.1, §2) -------------------


def main(
    args: list[str] | None = None,
    today: date | None = None,
    list_files_fn: Callable[..., Any] | None = None,
    bypass_date_gate: bool = False,
) -> int:
    parser = argparse.ArgumentParser(
        description="Cong cu sang loc 6 cap dac trung order flow VN30F footprint (Brief dot 182)"
    )
    parser.add_argument(
        "--data-dir",
        default="data/orderbook",
        help="Thu muc chua so lenh (mac dinh: data/orderbook)",
    )
    parser.add_argument(
        "--unlock-holdout-pair",
        default=None,
        help="Ten cap mo holdout neu dat IS (mac dinh: None)",
    )
    effective_args = [] if args is None and "pytest" in sys.argv[0] else args
    parsed_args = parser.parse_args(effective_args)

    if today is None:
        today = datetime.now(TZ).date()

    print("=" * 84)
    print("  BRIEF ĐỢT 182 — SÀNG LỌC ORDER FLOW VN30F THEO FOOTPRINT (ĐĂNG KÝ TRƯỚC)")
    print(f"  Ngày hiện tại (giờ VN): {today}")
    print(f"  Mốc bắt đầu Holdout    : {HOLDOUT_START_DATE}")
    print("=" * 84)

    # CỔNG NGÀY CHỐNG NHÌN TRƯỚC (§1.1):
    # Từ chối chạy phần đo khi ngày hôm nay < 2026-12-01, TRƯỚC KHI MỞ BẤT KỲ FILE NÀO.
    if not bypass_date_gate and today < HOLDOUT_START_DATE:
        print(
            f"\n[BẢO VỆ CHỐNG NHÌN TRƯỚC] Ngày hiện tại ({today}) chưa tới ngày kết thúc In-Sample "
            f"({HOLDOUT_START_DATE}).\nDừng toàn bộ chương trình và từ chối mở dữ liệu để bảo vệ "
            f"tính vô tư của tập nghiên cứu.",
            file=sys.stderr,
        )
        return 2

    # Chi khi today >= 2026-12-01 moi duoc phep liet ke hoac mo file
    if list_files_fn is not None:
        list_files_fn(parsed_args.data_dir)

    print("\n[THÔNG BÁO] Ngày hợp lệ (>= 2026-12-01). Tiếp tục quy trình đo đạc...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
