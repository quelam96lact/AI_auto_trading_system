"""Trading ideas and signal generation for Brief 191 (Foreign flow exploration).

Defines 5 pre-registered ideas:
- IDEA1_FOREIGN_ACCUMULATION_STREAK: Consecutive net buying streak with high volume ratio.
- IDEA2_FOREIGN_CROSS_SECTION_TOP: Top cross-sectional foreign accumulation ratio in liquid universe.
- IDEA3_FOREIGN_DIVERGENCE_DIP: Foreign accumulation during price pullback/consolidation.
- IDEA4_FOREIGN_REVERSAL_SURGE: Reversal from multi-day net selling to sudden strong net buying.
- IDEA5_FOREIGN_ROOM_EXHAUSTION: Rapid depletion of available foreign room accompanied by buying.

All ideas share:
- Universe: 20-session GTGD >= 10 tỷ VND at signal date t.
- Exit rules: simulate_trade_exits from research191_exits.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from scripts.research191_data import DailyRecord
from scripts.research191_exits import Trade191, is_liquid, simulate_trade_exits

IDEA_IDS = [
    "IDEA1_FOREIGN_ACCUMULATION_STREAK",
    "IDEA2_FOREIGN_CROSS_SECTION_TOP",
    "IDEA3_FOREIGN_DIVERGENCE_DIP",
    "IDEA4_FOREIGN_REVERSAL_SURGE",
    "IDEA5_FOREIGN_ROOM_EXHAUSTION",
]

IDEA_GRIDS: dict[str, dict[str, list[Any]]] = {
    "IDEA1_FOREIGN_ACCUMULATION_STREAK": {
        "k": [3, 5],
        "min_ratio": [0.08, 0.15, 0.25],
        "tp": [0.10, 0.15, 0.20],
    },
    "IDEA2_FOREIGN_CROSS_SECTION_TOP": {
        "q": [5, 10],
        "threshold": [0.05, 0.10, 0.15],
        "tp": [0.10, 0.15, 0.20],
    },
    "IDEA3_FOREIGN_DIVERGENCE_DIP": {
        "drop_rate": [0.03, 0.05, 0.08],
        "foreign_ratio": [0.05, 0.10, 0.15],
        "tp": [0.10, 0.15, 0.20],
    },
    "IDEA4_FOREIGN_REVERSAL_SURGE": {
        "spike_ratio": [0.10, 0.15, 0.20],
        "m": [1.5, 2.0],
        "tp": [0.10, 0.15, 0.20],
    },
    "IDEA5_FOREIGN_ROOM_EXHAUSTION": {
        "room_drop_pct": [0.10, 0.20, 0.30],
        "min_flow_ratio": [0.05, 0.10],
        "tp": [0.10, 0.15, 0.20],
    },
}


def rule_idea1_foreign_streak(
    records: list[DailyRecord],
    t: int,
    k: int,
    min_ratio: float,
) -> tuple[bool, float]:
    """Check K-session foreign net buying streak and accumulated ratio."""
    if t < k - 1:
        return False, 0.0

    sum_net = 0.0
    sum_gtgd = 0.0
    for i in range(t - k + 1, t + 1):
        rec = records[i]
        if rec.net_val is None or rec.net_val <= 0:
            return False, 0.0
        sum_net += rec.net_val
        sum_gtgd += rec.gtgd

    if sum_gtgd <= 0:
        return False, 0.0

    ratio = sum_net / sum_gtgd
    if ratio >= min_ratio:
        return True, ratio
    return False, 0.0


def rule_idea3_foreign_divergence_dip(
    records: list[DailyRecord],
    t: int,
    drop_rate: float,
    foreign_ratio: float,
) -> tuple[bool, float]:
    """Check price drop over 10 sessions while foreign flow is accumulating net buying."""
    if t < 10:
        return False, 0.0

    p_curr = records[t].close
    p_prev = records[t - 10].close
    if p_prev <= 0:
        return False, 0.0

    price_change = (p_curr / p_prev) - 1.0
    if price_change > -drop_rate:
        return False, 0.0

    sum_net = 0.0
    sum_gtgd = 0.0
    for i in range(t - 9, t + 1):
        rec = records[i]
        if rec.net_val is None:
            return False, 0.0
        sum_net += rec.net_val
        sum_gtgd += rec.gtgd

    if sum_gtgd <= 0:
        return False, 0.0

    f_ratio = sum_net / sum_gtgd
    if f_ratio >= foreign_ratio:
        return True, f_ratio
    return False, 0.0


def rule_idea4_foreign_reversal_surge(
    records: list[DailyRecord],
    t: int,
    spike_ratio: float,
    m: float,
) -> tuple[bool, float]:
    """Check reversal from 10-session net selling to a strong net buying spike at t."""
    if t < 10:
        return False, 0.0

    # 10 sessions before t: t-10 to t-1
    sum_prev_net = 0.0
    for i in range(t - 10, t):
        rec = records[i]
        if rec.net_val is None:
            return False, 0.0
        sum_prev_net += rec.net_val

    if sum_prev_net >= 0:
        return False, 0.0

    avg_sell = abs(sum_prev_net) / 10.0

    rec_t = records[t]
    if rec_t.net_val is None or rec_t.net_val <= 0 or rec_t.gtgd <= 0:
        return False, 0.0

    flow_ratio = rec_t.net_val / rec_t.gtgd
    if flow_ratio >= spike_ratio and rec_t.net_val >= m * avg_sell:
        return True, flow_ratio

    return False, 0.0


def rule_idea5_foreign_room_exhaustion(
    records: list[DailyRecord],
    t: int,
    room_drop_pct: float,
    min_flow_ratio: float,
) -> tuple[bool, float]:
    """Check foreign room depletion over 10 sessions with active net buying."""
    if t < 10:
        return False, 0.0

    room_curr = records[t].current_room
    room_prev = records[t - 10].current_room
    if room_curr is None or room_prev is None or room_prev <= 0:
        return False, 0.0

    drop = (room_prev - room_curr) / room_prev
    if drop < room_drop_pct:
        return False, 0.0

    rec_t = records[t]
    if rec_t.net_val is None or rec_t.net_val <= 0 or rec_t.gtgd <= 0:
        return False, 0.0

    flow_ratio = rec_t.net_val / rec_t.gtgd
    if flow_ratio >= min_flow_ratio:
        return True, drop

    return False, 0.0


def generate_trades_for_idea(
    idea_id: str,
    params: dict[str, Any],
    all_joined: dict[str, list[DailyRecord]],
    exchanges: dict[str, str],
    start_date: date,
    end_date: date,
) -> list[Trade191]:
    """Generate all executed trades for a given idea and parameter configuration.

    Guarantees:
    - Signals only generated within [start_date, end_date].
    - Liquid universe filter enforced on signal date.
    - No overlapping positions in the same symbol.
    """
    tp = float(params.get("tp", 0.10))
    trades: list[Trade191] = []

    if idea_id == "IDEA2_FOREIGN_CROSS_SECTION_TOP":
        q = int(params.get("q", 5))
        threshold = float(params.get("threshold", 0.05))

        # Index records by date
        date_records: dict[date, dict[str, DailyRecord]] = {}
        date_indices: dict[str, dict[date, int]] = {}
        for sym, b_list in all_joined.items():
            date_indices[sym] = {}
            for idx, b in enumerate(b_list):
                d = b.date
                if d not in date_records:
                    date_records[d] = {}
                date_records[d][sym] = b
                date_indices[sym][d] = idx

        # Find all unique sorted dates within [start_date, end_date]
        all_dates = sorted(d for d in date_records if start_date <= d <= end_date)

        # Track active positions per symbol: sym -> exit_date
        active_pos_exit: dict[str, date] = {}

        for cur_d in all_dates:
            candidates: list[tuple[float, str, int]] = []
            for sym, b_list in all_joined.items():
                if sym not in date_indices or cur_d not in date_indices[sym]:
                    continue
                t = date_indices[sym][cur_d]
                if t < 19:
                    continue
                if not is_liquid(b_list, t):
                    continue
                # Cannot enter if still in active position
                if sym in active_pos_exit and active_pos_exit[sym] > cur_d:
                    continue

                rec_t = b_list[t]
                if rec_t.net_val is None or rec_t.net_val <= 0:
                    continue

                # 20-session cumulative ratio
                sum_net = 0.0
                sum_gtgd = 0.0
                valid = True
                for i in range(t - 19, t + 1):
                    r = b_list[i]
                    if r.net_val is None:
                        valid = False
                        break
                    sum_net += r.net_val
                    sum_gtgd += r.gtgd

                if not valid or sum_gtgd <= 0:
                    continue

                cum_ratio = sum_net / sum_gtgd
                if cum_ratio >= threshold:
                    candidates.append((cum_ratio, sym, t))

            # Sort descending by cum_ratio, take top Q
            candidates.sort(key=lambda x: -x[0])
            selected = candidates[:q]

            for score, sym, t in selected:
                # Double-check position availability
                if sym in active_pos_exit and active_pos_exit[sym] > cur_d:
                    continue
                tr = simulate_trade_exits(
                    all_joined[sym],
                    signal_idx=t,
                    exchange=exchanges.get(sym),
                    tp=tp,
                    score=score,
                    enforce_liquidity=True,
                )
                if tr is not None:
                    trades.append(tr)
                    active_pos_exit[sym] = tr.exit_ts.date()

        return trades

    # For Ideas 1, 3, 4, 5: evaluate symbol by symbol
    for sym, records in all_joined.items():
        exchange = exchanges.get(sym)
        i = 0
        n_rec = len(records)
        while i < n_rec:
            cur_d = records[i].date
            if cur_d < start_date:
                i += 1
                continue
            if cur_d > end_date:
                break

            if not is_liquid(records, i):
                i += 1
                continue

            has_signal = False
            score = 0.0

            if idea_id == "IDEA1_FOREIGN_ACCUMULATION_STREAK":
                has_signal, score = rule_idea1_foreign_streak(
                    records, i, k=int(params["k"]), min_ratio=float(params["min_ratio"])
                )
            elif idea_id == "IDEA3_FOREIGN_DIVERGENCE_DIP":
                has_signal, score = rule_idea3_foreign_divergence_dip(
                    records, i, drop_rate=float(params["drop_rate"]), foreign_ratio=float(params["foreign_ratio"])
                )
            elif idea_id == "IDEA4_FOREIGN_REVERSAL_SURGE":
                has_signal, score = rule_idea4_foreign_reversal_surge(
                    records, i, spike_ratio=float(params["spike_ratio"]), m=float(params["m"])
                )
            elif idea_id == "IDEA5_FOREIGN_ROOM_EXHAUSTION":
                has_signal, score = rule_idea5_foreign_room_exhaustion(
                    records, i, room_drop_pct=float(params["room_drop_pct"]), min_flow_ratio=float(params["min_flow_ratio"])
                )

            if has_signal:
                tr = simulate_trade_exits(
                    records,
                    signal_idx=i,
                    exchange=exchange,
                    tp=tp,
                    score=score,
                    enforce_liquidity=True,
                )
                if tr is not None:
                    trades.append(tr)
                    # Advance i to the exit bar index so we don't open another trade in same symbol
                    exit_d = tr.exit_ts.date()
                    while i < n_rec and records[i].date <= exit_d:
                        i += 1
                    continue

            i += 1

    return trades
