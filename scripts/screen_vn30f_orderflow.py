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
8. `main`: cong so phien IS (IS = 40 phien hop le dau tien; chua du thi dung va tra ma 2).
"""

from __future__ import annotations

import argparse
import bisect
import sys
import zlib
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
    iter_file_messages,
    parse_recv_ts,
    parse_trading_time,
    session_date_from_filename,
)
from scripts.record_vn30f_orderbook import (
    AFTERNOON_START,
    MORNING_END,
    MORNING_START,
    classify_message,
)
from scripts.screen_vn30f_orderbook import (
    ALPHA_LEVEL,
    CONTROL_MIN_RHO,
    DEFAULT_UNLOCK_LOG_PATH,
    ECONOMIC_HURDLE_FACTOR,
    IS_START_DATE,
    MIN_INDEP_EVENTS,
    MIN_SIDE_EVENTS,
    compute_is_boundary,
    compute_roundtrip_cost,
)
from trading.calendar_vn import TZ
from trading.metrics import calculate_percentile

__all__ = [
    "ALPHA_PER_PAIR",
    "EVENT_NAMES",
    "HORIZONS",
    "IS_START_DATE",
    "MIN_HOLDOUT_SESSIONS",
    "MIN_IS_SESSIONS",
    "SLIPPAGE_PTS",
    "VALID_BARS_THRESHOLD",
    "BarSummary",
    "FootprintBar",
    "OrderFlowEvent",
    "OrderFlowSession",
    "block_bootstrap_p_value",
    "build_footprint_bars",
    "build_footprint_bars_and_trades",
    "build_price_lookup",
    "calculate_event_targets",
    "check_control_variable_orderflow",
    "compute_economic_hurdle",
    "compute_is_boundary",
    "count_holdout_files",
    "detect_e1_events",
    "detect_e2_events",
    "detect_e3_events",
    "evaluate_pair_criteria",
    "filter_holdout_events",
    "filter_non_overlapping_events",
    "holdout_verdict",
    "imbalance_levels",
    "load_holdout_sessions",
    "load_holdout_sessions_orderflow",
    "load_is_sessions_orderflow",
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

MIN_IS_SESSIONS: int = 40
MIN_HOLDOUT_SESSIONS: int = 30
VALID_BARS_THRESHOLD: int = 44  # ceil(0.9 * 48)


# --- Cau truc du lieu -------------------------------------------------------------


@dataclass
class OrderFlowSession:
    session_date: date
    contract: str
    file_path: Path
    bars: list[FootprintBar]
    clean_trades: list[tuple[datetime, float]]
    price_lookup: Callable[[datetime], float | None]
    is_valid: bool
    invalid_reason: str | None
    active_bars: int
    stats: dict[str, Any]


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


def build_price_lookup(
    clean_trades: Sequence[tuple[datetime, float]],
) -> Callable[[datetime], float | None]:
    """Tra cuu P(x) = gia cua tin khop cuoi cung co trading_time <= x.

    Yeu cau: clean_trades da duoc sap xep theo trading_time tang dan.
    """
    if not clean_trades:
        return lambda _x: None

    times = [t[0] for t in clean_trades]
    prices = [t[1] for t in clean_trades]

    def _lookup(x: datetime) -> float | None:
        idx = bisect.bisect_right(times, x)
        if idx == 0:
            return None
        return prices[idx - 1]

    return _lookup


def build_footprint_bars_and_trades(
    messages: Iterable[dict[str, Any]],
    session_date: date,
    stats: dict[str, Any] | None = None,
    use_recv_ts_instead_of_trading_time: bool = False,
    same_level_instead_of_diagonal: bool = False,
) -> tuple[list[FootprintBar], list[tuple[datetime, float]], dict[str, Any]]:
    """Dung 48 nen footprint 5 phut va trich xuat danh sach tin khop sach cho mot phien.

    Chi nhan tin classify_message(msg) == 'TRADE', side in {'B', 'S'}, quantity > 0.
    CVD reset ve 0 tai dau phien.
    Tra ve (bars, clean_trades, stats).
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

    clean_trades = [(t["ts"], t["price"]) for t in valid_trades]

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

    return bars, clean_trades, stats


def build_footprint_bars(
    messages: Iterable[dict[str, Any]],
    session_date: date,
    stats: dict[str, Any] | None = None,
    use_recv_ts_instead_of_trading_time: bool = False,
    same_level_instead_of_diagonal: bool = False,
) -> tuple[list[FootprintBar], dict[str, Any]]:
    """Dung 48 nen footprint 5 phut cho mot phien giao dich (tuong thich nguoc)."""
    bars, _, st = build_footprint_bars_and_trades(
        messages=messages,
        session_date=session_date,
        stats=stats,
        use_recv_ts_instead_of_trading_time=use_recv_ts_instead_of_trading_time,
        same_level_instead_of_diagonal=same_level_instead_of_diagonal,
    )
    return bars, st


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
    block_end_fn: Callable[..., datetime] | None = None,
) -> list[OrderFlowEvent]:
    """Tinh bien muc tieu y = d * (P(t_end + H) - close_t).

    Bo su kien neu t_end + H vuot qua ket thuc khung dang chua no (11:30 hoac 14:30 mac dinh,
    hoac block_end_fn rieng neu truyen vao).
    """
    valid_events: list[OrderFlowEvent] = []

    for e in events:
        target_time = e.t_end + timedelta(minutes=h_minutes)

        # Kiem tra ket thuc khung
        if block_end_fn is not None:
            try:
                block_end = block_end_fn(e)
            except TypeError:
                block_end = block_end_fn(e.t_end, e.block_id)
        else:
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
        "p_value": p_val,
        "control_rho": control_rho,
        "cond_control": cond_control,
        "cond1_sample": cond1_sample,
        "cond2_stat": cond2_stat,
        "cond3_hurdle": cond3_hurdle,
    }


def holdout_verdict(p_val: float, mean_y: float, hurdle: float) -> bool:
    """Phan quyet Holdout cho DUNG MOT cap da dat IS (Claude bo sung khi audit 182b, truoc 01/12).

    Giong 162 (_evaluate_holdout_pair): p mot phia < 0.05 (khong chia 6 vi chi mo 1 cap)
    VA mean_y >= hurdle cua IS. Khong doi >= 100 su kien: ~30 phien Holdout khong the du,
    va doi vay se lam Holdout truot vi thieu mau chu khong vi khong co loi the.
    """
    return (p_val < ALPHA_LEVEL) and (mean_y >= hurdle)


def filter_holdout_events(
    events: Sequence[OrderFlowEvent],
    boundary: date,
) -> list[OrderFlowEvent]:
    """Loc cac su kien thuoc tap Holdout (session_id > boundary). Ngay boundary thuoc IS, KHONG vao holdout."""
    return [e for e in events if e.session_id > boundary]


# --- 6. Niem phong Holdout & Loader du lieu (§1.1, §1.4, §1B) --------------------


def count_holdout_files(
    data_dir: Path | str = "data/orderbook",
    boundary: date | None = None,
    today: date | None = None,
) -> int:
    """Dem so file Holdout (boundary < ngay < today) chi theo ten file, KHONG mo file."""
    if boundary is None:
        return 0
    if today is None:
        today = datetime.now(TZ).date()
    p_dir = Path(data_dir)
    if not p_dir.exists():
        return 0
    count = 0
    for item in sorted(p_dir.iterdir()):
        if item.is_dir():
            for f in sorted(item.glob("*.jsonl.gz")):
                s_date = session_date_from_filename(f)
                if s_date is not None and boundary < s_date < today:
                    count += 1
    return count


def verify_holdout_log_unlocked(
    log_path: Path | str = DEFAULT_UNLOCK_LOG_PATH,
    pair_name: str | None = None,
    tag: str = "đợt 182",
) -> bool:
    """Kiem tra log mo niem phong holdout-unlock-log.md co dong dot 182 va ten cap chua."""
    p = Path(log_path)
    if not p.exists():
        raise RuntimeError(f"File log mo niem phong khong ton tai: {p}")

    text = p.read_text(encoding="utf-8")
    for line in text.splitlines():
        line_lower = line.lower()
        if tag.lower() in line_lower and (
            pair_name is None or pair_name.lower() in line_lower
        ):
            return True

    detail = f"'{tag}'" if pair_name is None else f"'{tag}' và cặp '{pair_name}'"
    raise RuntimeError(
        f"Vi pham niem phong: chua co dong mo khoa {detail} trong {log_path}"
    )


def load_holdout_sessions_orderflow(
    data_dir: Path | str = "data/orderbook",
    log_path: Path | str = DEFAULT_UNLOCK_LOG_PATH,
    pair_name: str | None = None,
    boundary: date | None = None,
    today: date | None = None,
) -> list[OrderFlowSession]:
    """Doc phien Holdout (boundary < ngay < today). BAT BUOC kiem tra dong log truoc khi doc bat ky file nao."""
    verify_holdout_log_unlocked(log_path=log_path, pair_name=pair_name, tag="đợt 182")
    if boundary is None:
        return []
    if today is None:
        today = datetime.now(TZ).date()
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
                if s_date is None or not (boundary < s_date < today):
                    continue
                if s_date in date_to_contract:
                    raise ValueError(
                        f"Trùng ngày {s_date} giữa các hợp đồng Holdout: '{date_to_contract[s_date]}' và '{contract_name}'"
                    )
                date_to_contract[s_date] = contract_name
                file_entries.append((s_date, contract_name, f))

    sessions: list[OrderFlowSession] = []
    for s_date, contract_name, fpath in sorted(file_entries, key=lambda x: x[0]):
        try:
            stats: dict[str, Any] = {}
            bars, trades, stats = build_footprint_bars_and_trades(
                iter_file_messages(fpath), s_date, stats=stats
            )
            lookup = build_price_lookup(trades)
            active_bars = sum(1 for b in bars if b.trade_count > 0)
            is_valid = (active_bars >= VALID_BARS_THRESHOLD)
            reason = None if is_valid else f"phiên thưa ({active_bars}/48 nến)"
        except (EOFError, OSError, zlib.error) as exc:
            print(f"[CẢNH BÁO] File hỏng '{fpath}': {exc}", file=sys.stderr)
            bars = []
            trades = []
            lookup = lambda _x: None
            is_valid = False
            reason = "file hỏng"
            active_bars = 0
            stats = {}

        sessions.append(
            OrderFlowSession(
                session_date=s_date,
                contract=contract_name,
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

    return sessions


# Tuong thich nguoc voi import cu
load_holdout_sessions = load_holdout_sessions_orderflow


def load_is_sessions_orderflow(
    data_dir: Path | str = "data/orderbook",
    today: date | None = None,
) -> list[OrderFlowSession]:
    """Doc cac phien In-Sample (IS_START_DATE <= ngay < today, dung sau phien hop le thu 40).

    - Chi xet file co IS_START_DATE <= ngay < today. File cua hom nay dang duoc ghi, KHONG mo.
    - Dung ngay sau phien hop le thu 40. Khong mo them file nao sau do.
    - Hai hop dong trung ngay -> raise ValueError.
    - Bat loi file cat cut / hong: EOFError, OSError, zlib.error -> is_valid=False, ly do 'file hỏng'.
    - Phien hop le: >= 44 tren 48 nen co giao dich (ceil(0.9 * 48)).
    """
    if today is None:
        today = datetime.now(TZ).date()

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

    sessions: list[OrderFlowSession] = []
    valid_count = 0
    for s_date, contract_name, fpath in sorted(file_entries, key=lambda x: x[0]):
        # Chi xet file co IS_START_DATE <= ngay < today
        if not (IS_START_DATE <= s_date < today):
            continue

        try:
            stats: dict[str, Any] = {}
            bars, trades, stats = build_footprint_bars_and_trades(
                iter_file_messages(fpath), s_date, stats=stats
            )
            lookup = build_price_lookup(trades)
            active_bars = sum(1 for b in bars if b.trade_count > 0)
            if active_bars >= VALID_BARS_THRESHOLD:
                is_valid = True
                reason = None
            else:
                is_valid = False
                reason = f"phiên thưa ({active_bars}/48 nến)"
        except (EOFError, OSError, zlib.error) as exc:
            print(f"[CẢNH BÁO] File hỏng '{fpath}': {exc}", file=sys.stderr)
            bars = []
            trades = []
            lookup = lambda _x: None
            is_valid = False
            reason = "file hỏng"
            active_bars = 0
            stats = {}

        sessions.append(
            OrderFlowSession(
                session_date=s_date,
                contract=contract_name,
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
        if is_valid:
            valid_count += 1
            if valid_count >= MIN_IS_SESSIONS:
                break

    return sessions


# --- 7. CLI Main Runner & Cong ngay chong nhin truoc (§1.1, §1B) ------------------


def main(
    args: Sequence[str] | None = None,
    today: date | None = None,
    unlock_log_path: Path | str = DEFAULT_UNLOCK_LOG_PATH,
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
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    if today is None:
        today = datetime.now(TZ).date()

    print("=" * 84)
    print("  BRIEF ĐỢT 182 — SÀNG LỌC ORDER FLOW VN30F THEO FOOTPRINT (ĐĂNG KÝ TRƯỚC)")
    print(f"  Ngày hiện tại (giờ VN): {today}")
    print("=" * 84)

    # --- 1. Nạp phiên IS (§1B, Brief 185 §1.3) ---
    sessions = load_is_sessions_orderflow(data_dir=parsed_args.data_dir, today=today)
    valid_sessions = [s for s in sessions if s.is_valid]
    invalid_sessions = [s for s in sessions if not s.is_valid]

    tot_u_zero = sum(s.stats.get("dropped_u_or_zero", 0) for s in sessions)
    tot_outside = sum(s.stats.get("outside_session", 0) for s in sessions)

    print(f"\n[DỮ LIỆU IN-SAMPLE] Tổng phiên đọc được: {len(sessions)}")
    print(f"  - Số phiên hợp lệ (>= {VALID_BARS_THRESHOLD}/48 nến): {len(valid_sessions)}")
    print(f"  - Số phiên không hợp lệ: {len(invalid_sessions)}")
    for inv in invalid_sessions:
        print(f"    * Ngày {inv.session_date} ({inv.contract}): {inv.invalid_reason}")
    print(f"  - Tổng tin U hoặc khối lượng 0 bị loại: {tot_u_zero:,}")
    print(f"  - Tổng tin ngoài khung liên tục bị loại: {tot_outside:,}")

    # CỔNG SỐ PHIÊN IS (Brief 185 §1.3):
    sessions_validity = [(s.session_date, s.is_valid) for s in sessions]
    boundary = compute_is_boundary(sessions_validity, n=MIN_IS_SESSIONS)
    if boundary is None:
        k = len(valid_sessions)
        last_checked = max((s.session_date for s in sessions), default=IS_START_DATE)
        print(
            f"\n[BẢO VỆ CHỐNG NHÌN TRƯỚC] CHƯA ĐỦ PHIÊN IS: {k}/{MIN_IS_SESSIONS} phiên hợp lệ "
            f"(đã kiểm tới {last_checked}). Dừng toàn bộ chương trình và từ chối mở dữ liệu để bảo vệ "
            f"tính vô tư của tập nghiên cứu.",
            file=sys.stderr,
        )
        return 2

    print(f"\nRanh giới IS: phiên hợp lệ thứ 40 = {boundary}; holdout là các phiên sau ngày này")

    # --- 3. Kiểm đối chứng trên nến IS hợp lệ ---
    valid_bars = [b for s in valid_sessions for b in s.bars]
    ctrl_ok, ctrl_rho = check_control_variable_orderflow(valid_bars)
    print(f"\n[BIẾN ĐỐI CHỨNG] Spearman rho giữa delta và ret_same_5m: {ctrl_rho:.4f}")
    if not ctrl_ok:
        print(
            f"\n[LỖI] DỮ LIỆU SIDE KHÔNG ĐÁNG TIN: Spearman rho = {ctrl_rho:.4f} <= {CONTROL_MIN_RHO}",
            file=sys.stderr,
        )
        return 4

    # --- 4. Tính hurdle ---
    closes = [b.close for b in valid_bars if b.close is not None]
    median_close = float(np.median(closes)) if closes else 1300.0
    hurdle = compute_economic_hurdle(median_close)
    print(f"\n[TIÊU CHUẨN KINH TẾ] Median Close: {median_close:.2f} | Hurdle: {hurdle:.4f} điểm")

    lookup_map = {s.session_date: s.price_lookup for s in valid_sessions}
    def global_price_lookup(x: datetime) -> float | None:
        fn = lookup_map.get(x.date())
        return fn(x) if fn else None

    # --- 5 & 6. Chạy 6 cặp đặc trưng và in bảng ---
    print("\n" + "=" * 98)
    print(f"{'Cặp':<10} {'N':>5} {'N Mua':>7} {'N Bán':>7} {'Mean y':>10} {'Hurdle':>8} {'p-value':>10} {'C1-4/Ctrl':>12} {'Kết quả':>10}")
    print("-" * 98)

    results: dict[str, dict[str, Any]] = {}

    for ev_name in ("E1", "E2", "E3"):
        if ev_name == "E1":
            raw_events = detect_e1_events(valid_bars)
        elif ev_name == "E2":
            raw_events = detect_e2_events(valid_bars)
        else:
            raw_events = detect_e3_events(valid_bars)

        for h in (15, 30):
            pair_key = f"{ev_name}_H{h}"
            ev_targets = calculate_event_targets(raw_events, global_price_lookup, h_minutes=h)
            indep_events = filter_non_overlapping_events(ev_targets, h_minutes=h)
            p_val, _ = block_bootstrap_p_value(indep_events, n_bootstrap=2000, seed=42)
            res = evaluate_pair_criteria(indep_events, hurdle=hurdle, control_rho=ctrl_rho, p_val=p_val)
            results[pair_key] = res

            cond_str = f"{int(res['cond1_sample'])}{int(res['cond2_stat'])}{int(res['cond3_hurdle'])}{int(res['cond_control'])}"
            verdict = "ĐẠT" if res["passed"] else "TRƯỢT"
            print(
                f"{pair_key:<10} {res['n_events']:>5} {res['n_buy']:>7} {res['n_sell']:>7} "
                f"{res['mean_y']:>10.4f} {res['hurdle']:>8.4f} {res['p_value']:>10.4f} {cond_str:>12} {verdict:>10}"
            )

    print("=" * 98)

    # --- 7. Holdout mở khóa (§1.1, §1.4, §1B, Brief 185 §1.3) ---
    unlock_pair = parsed_args.unlock_holdout_pair
    if unlock_pair:
        print(f"\n[YÊU CẦU MỞ NIÊM PHONG HOLDOUT] Cặp chỉ định: {unlock_pair}")

        # Điều kiện 1: Cặp ĐẠT trong chính lượt chạy IS này
        if unlock_pair not in results or not results[unlock_pair]["passed"]:
            print(
                f"[TỪ CHỐI MỞ HOLDOUT] Cặp '{unlock_pair}' không ĐẠT ở In-Sample. Không được mở niêm phong.",
                file=sys.stderr,
            )
            return 5

        # Điều kiện 2: Số file holdout đếm theo tên file >= MIN_HOLDOUT_SESSIONS
        h_file_count = count_holdout_files(parsed_args.data_dir, boundary=boundary, today=today)
        if h_file_count < MIN_HOLDOUT_SESSIONS:
            print(
                f"[TỪ CHỐI MỞ HOLDOUT] Số file Holdout ({h_file_count}) chưa đủ ngưỡng tối thiểu ({MIN_HOLDOUT_SESSIONS}).",
                file=sys.stderr,
            )
            return 5

        # Điều kiện 3: Log chưa có dòng mở holdout của đợt 182
        p_log = Path(unlock_log_path)
        if p_log.exists():
            log_content = p_log.read_text(encoding="utf-8")
            if "đợt 182" in log_content.lower():
                print(
                    "[TỪ CHỐI MỞ HOLDOUT] Log đã có dòng mở niêm phong của đợt 182 (chỉ mở duy nhất 1 lần).",
                    file=sys.stderr,
                )
                return 5

        # Đủ cả 3 điều kiện:
        # a. GHI log trước (ghi thêm ranh giới IS)
        p_log.parent.mkdir(parents=True, exist_ok=True)
        now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        with p_log.open("a", encoding="utf-8") as f_log:
            f_log.write(
                f"\n- [{now_str}] Mở niêm phong đợt 182 cho cặp {unlock_pair} trên tập Holdout VN30F "
                f"(IS boundary: {boundary})\n"
            )
        print(f"[ĐÃ GHI LOG] Ghi nhận mở niêm phong cho cặp {unlock_pair} vào {unlock_log_path}")

        # b. Sau đó mới nạp phiên > boundary
        holdout_sessions = load_holdout_sessions_orderflow(
            data_dir=parsed_args.data_dir,
            log_path=unlock_log_path,
            pair_name=unlock_pair,
            boundary=boundary,
            today=today,
        )
        valid_h_sessions = [s for s in holdout_sessions if s.is_valid]
        print(f"[DỮ LIỆU HOLDOUT] Số phiên Holdout hợp lệ: {len(valid_h_sessions)}/{len(holdout_sessions)}")

        # c. Đo riêng cặp đó với hurdle của IS
        h_bars = [b for s in valid_h_sessions for b in s.bars]
        ev_type, h_str = unlock_pair.split("_")
        h_val = int(h_str.replace("H", ""))

        # Noi nen IS hop le phia truoc de nguong E2 cua 5 phien Holdout dau lay tu 5 phien IS cuoi
        # (chi la qua khu); E1/E3 gioi han trong phien nen khong doi. Chi giu su kien thuoc Holdout.
        hist_bars = valid_bars + h_bars
        if ev_type == "E1":
            h_ev_all = detect_e1_events(hist_bars)
        elif ev_type == "E2":
            h_ev_all = detect_e2_events(hist_bars)
        else:
            h_ev_all = detect_e3_events(hist_bars)
        h_ev_list = filter_holdout_events(h_ev_all, boundary=boundary)

        h_lookup_map = {s.session_date: s.price_lookup for s in valid_h_sessions}
        def h_price_lookup(x: datetime) -> float | None:
            fn = h_lookup_map.get(x.date())
            return fn(x) if fn else None

        h_ev_targets = calculate_event_targets(h_ev_list, h_price_lookup, h_minutes=h_val)
        h_indep = filter_non_overlapping_events(h_ev_targets, h_minutes=h_val)
        h_p_val, _ = block_bootstrap_p_value(h_indep, n_bootstrap=2000, seed=42)
        h_res = evaluate_pair_criteria(h_indep, hurdle=hurdle, control_rho=ctrl_rho, p_val=h_p_val)

        # d. In kết quả
        print("\n" + "=" * 84)
        print(f"  KẾT QUẢ ĐO HOLDOUT RIÊNG CHO CẶP: {unlock_pair}")
        print(f"  Số sự kiện độc lập: {h_res['n_events']} (Mua: {h_res['n_buy']}, Bán: {h_res['n_sell']})")
        print(f"  Mean y            : {h_res['mean_y']:.4f} (Hurdle IS: {hurdle:.4f})")
        print(f"  p-value (Bootstrap): {h_res['p_value']:.4f}")
        h_passed = holdout_verdict(h_p_val, h_res["mean_y"], hurdle)
        print(f"  Tiêu chí Holdout  : p < {ALPHA_LEVEL} và Mean y >= Hurdle IS (giống đợt 162)")
        print(f"  Kết luận Holdout  : {'ĐẠT' if h_passed else 'TRƯỢT'}")
        print("=" * 84)

    return 0


if __name__ == "__main__":
    sys.exit(main())
