"""Unit tests and mutation tests for Brief 227 core infrastructure (§4).

Covers:
- Mutation tests (a)–(o) calling the exact product functions required by Brief 227 §4
- Hand-calculated fees & final NAV across all 3 fee branches (buy, TIME, END)
- Positive control (signal proportional to close_pos + small noise -> ML beats B0)
- Negative control (shuffled labels -> ML does NOT beat B0)
- Determinism test (identical scores across two runs)
- Validation pipeline test on synthetic data in tmp_path
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.research191_data import StockDailyBar
from scripts.research227_core import (
    COST_RT,
    FEATURE_NAMES,
    MIN_TURNOVER_227,
    EventRecord,
    compute_event_features,
    compute_event_label,
    event_trade,
    find_events,
    precompute_market_context,
    prepare_events_with_outcomes,
    simulate_event_portfolio,
    train_and_score,
)
from scripts.research227_explore import run_exploration
from scripts.research227_validate import run_validation


def _make_weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    cur = start
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _make_liquid_bars(
    sym: str,
    sessions: list[date],
    close_val: float = 100_000.0,
    volume_val: float = 60_000.0,
) -> list[StockDailyBar]:
    """Create uniform liquid bars (GT20 = 6e9 >= 5e9 by default)."""
    return [
        StockDailyBar(
            symbol=sym,
            date=d,
            open=close_val,
            high=close_val + 1_000.0,
            low=close_val - 1_000.0,
            close=close_val,
            volume=volume_val,
        )
        for d in sessions
    ]


def _make_dummy_event(
    sym: str,
    bar_idx: int,
    signal_date: date,
    buy_date: date,
    sell_date: date | None,
    y_val: float | None,
    vol_ratio: float = 2.5,
    close_pos: float = 0.8,
) -> EventRecord:
    feats = {f: 0.0 for f in FEATURE_NAMES}
    feats["vol_ratio"] = vol_ratio
    feats["close_pos"] = close_pos
    feats["log_gt20"] = 22.5
    return EventRecord(
        symbol=sym,
        bar_idx=bar_idx,
        signal_date=signal_date,
        buy_date=buy_date,
        buy_price=100_000.0,
        exchange="HOSE",
        gt20=6_000_000_000.0,
        vol_ratio=vol_ratio,
        features=feats,
        sell_date=sell_date,
        sell_price=105_000.0 if sell_date is not None else None,
        gross=0.05 if sell_date is not None else None,
        mkt=0.0,
        y=y_val,
        exit_reason="TIME" if sell_date is not None else "END",
    )


def _write_synthetic_dataset_dir(
    out_dir: Path,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    exchanges: dict[str, str],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    sess_path = out_dir / "sessions.csv"
    with open(sess_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date"])
        for d in sessions:
            writer.writerow([d.isoformat()])

    exch_path = out_dir / "exchanges.csv"
    with open(exch_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "exchange"])
        for sym in sorted(bars_by_symbol.keys()):
            writer.writerow([sym, exchanges.get(sym, "HOSE")])

    stocks_path = out_dir / "stocks_daily.csv.gz"
    with gzip.open(stocks_path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "date", "open", "high", "low", "close", "volume"])
        for sym in sorted(bars_by_symbol.keys()):
            for b in bars_by_symbol[sym]:
                writer.writerow(
                    [b.symbol, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume]
                )

    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    manifest = {
        "files": {
            "stocks_daily.csv.gz": {"sha256": _sha(stocks_path)},
            "sessions.csv": {"sha256": _sha(sess_path)},
            "exchanges.csv": {"sha256": _sha(exch_path)},
        }
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ==============================================================================
# Mutation Tests (a)–(o) required by Brief 227 §4
# ==============================================================================


def test_mutation_a_v20_and_gt20_exclude_bar_t():
    """Mutation (a): V20/GT20 tính gồm cả nến t. Product: find_events."""
    sessions = _make_weekdays(date(2020, 1, 2), 140)

    # Case 1: V20 over t-20..t-1 = 60,000 -> 2*V20 = 120,000.
    # At t=125: vol=125,000 >= 120,000 (TRUE event).
    # If V20 erroneously includes t (t-19..t): (19*60,000 + 125,000)/20 = 63,250 -> 2*V20=126,500 > 125,000 -> missed!
    bars_v = _make_liquid_bars("V20_SYM", sessions, close_val=100_000.0, volume_val=60_000.0)
    bars_v[125].close = 102_000.0
    bars_v[125].high = 103_000.0
    bars_v[125].volume = 125_000.0

    evs_v = find_events({"V20_SYM": bars_v}, sessions, {"V20_SYM": "HOSE"})
    assert [e.bar_idx for e in evs_v] == [125], (
        "Event at t=125 must pass when V20 uses t-20..t-1 strictly"
    )

    # Case 2: GT20 over t-20..t-1 = 4.95e9 < 5e9 -> NOT liquid.
    # At t=125: close*vol = 102,000 * 120,000 = 12.24e9.
    # If GT20 erroneously includes t: (19*4.95e9 + 12.24e9)/20 = 5.3145e9 >= 5e9 -> false positive!
    bars_g = _make_liquid_bars("GT20_SYM", sessions, close_val=100_000.0, volume_val=49_500.0)
    bars_g[125].close = 102_000.0
    bars_g[125].high = 103_000.0
    bars_g[125].volume = 120_000.0

    evs_g = find_events({"GT20_SYM": bars_g}, sessions, {"GT20_SYM": "HOSE"})
    assert evs_g == [], "Bar t must NOT count toward GT20 >= 5e9"


def test_mutation_b_requires_close_strictly_higher_than_prev():
    """Mutation (b): Bỏ điều kiện close[t] > close[t-1]. Product: find_events."""
    sessions = _make_weekdays(date(2020, 1, 2), 140)
    bars_flat = _make_liquid_bars("FLAT", sessions)
    bars_flat[125].close = 100_000.0  # equal to bars[124].close
    bars_flat[125].volume = 200_000.0  # > 3x V20

    bars_down = _make_liquid_bars("DOWN", sessions)
    bars_down[125].close = 98_000.0  # lower than bars[124].close
    bars_down[125].volume = 200_000.0

    evs = find_events(
        {"FLAT": bars_flat, "DOWN": bars_down},
        sessions,
        {"FLAT": "HOSE", "DOWN": "HOSE"},
    )
    assert evs == [], "Flat or down close[t] must NOT trigger an event"


def test_mutation_c_requires_gt20_at_least_5b():
    """Mutation (c): Bỏ điều kiện GT20 >= 5 tỷ. Product: find_events."""
    sessions = _make_weekdays(date(2020, 1, 2), 140)
    # close=10,000 * volume=100,000 => GT20 = 1e9 < 5e9
    bars = _make_liquid_bars("SMALL", sessions, close_val=10_000.0, volume_val=100_000.0)
    bars[125].close = 10_300.0
    bars[125].high = 10_400.0
    bars[125].volume = 350_000.0

    evs = find_events({"SMALL": bars}, sessions, {"SMALL": "HOSE"})
    assert evs == [], "Symbol with GT20 < 5e9 must NOT produce events"


def test_mutation_d_rejects_when_entry_status_not_ok_or_session_gap():
    """Mutation (d): Mua được khi entry_status != 'ok'. Product: find_events."""
    sessions = _make_weekdays(date(2020, 1, 2), 140)

    # Subcase 1: Ceiling open at t+1 (HOSE +7% -> 102,000 * 1.07 = 109,140)
    bars_ceil = _make_liquid_bars("CEIL", sessions)
    bars_ceil[125].close = 102_000.0
    bars_ceil[125].high = 103_000.0
    bars_ceil[125].volume = 180_000.0
    bars_ceil[126].open = 109_100.0
    bars_ceil[126].high = 109_100.0
    bars_ceil[126].low = 109_100.0
    bars_ceil[126].close = 109_100.0

    # Subcase 2: Zero volume at t+1
    bars_zvol = _make_liquid_bars("ZVOL", sessions)
    bars_zvol[125].close = 102_000.0
    bars_zvol[125].high = 103_000.0
    bars_zvol[125].volume = 180_000.0
    bars_zvol[126].volume = 0.0

    # Subcase 3: Missing session t+1 (suspended day)
    bars_gap = _make_liquid_bars("GAP", sessions)
    bars_gap[125].close = 102_000.0
    bars_gap[125].high = 103_000.0
    bars_gap[125].volume = 180_000.0
    del bars_gap[126]

    evs = find_events(
        {"CEIL": bars_ceil, "ZVOL": bars_zvol, "GAP": bars_gap},
        sessions,
        {"CEIL": "HOSE", "ZVOL": "HOSE", "GAP": "HOSE"},
    )
    assert evs == [], "Ceiling open, zero volume, and session gaps at t+1 must be rejected"


def test_mutation_e_features_never_use_future_bars_ret1_and_mkt_breadth():
    """Mutation (e): Một đặc trưng dùng nến t+1 (ret_1, mkt_breadth). Product: compute_event_features."""
    sessions = _make_weekdays(date(2020, 1, 2), 140)
    bars_a = _make_liquid_bars("AAA", sessions, close_val=100_000.0, volume_val=60_000.0)
    bars_b = _make_liquid_bars("BBB", sessions, close_val=100_000.0, volume_val=60_000.0)
    for k in range(120, 126):
        bars_a[k].close = 100_000.0 + (k - 120) * 500.0
        bars_b[k].close = 100_000.0 + (k - 120) * 300.0
    bars_a[125].volume = 150_000.0
    bars_a[125].high = 104_000.0
    bars_a[125].low = 99_000.0

    uni_orig = {"AAA": bars_a, "BBB": bars_b}
    feats_orig = compute_event_features(bars_a, 125, bars_by_symbol=uni_orig)

    # Corrupt EVERY bar strictly after t=125 across all symbols
    bars_a_mut = [StockDailyBar(b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars_a]
    bars_b_mut = [StockDailyBar(b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars_b]
    for idx in range(126, len(sessions)):
        bars_a_mut[idx].open = 50_000.0
        bars_a_mut[idx].high = 200_000.0
        bars_a_mut[idx].low = 40_000.0
        bars_a_mut[idx].close = 190_000.0
        bars_a_mut[idx].volume = 999_999.0

        bars_b_mut[idx].close = 50_000.0
        bars_b_mut[idx].volume = 999_999.0

    uni_mut = {"AAA": bars_a_mut, "BBB": bars_b_mut}
    feats_mut = compute_event_features(bars_a_mut, 125, bars_by_symbol=uni_mut)

    assert feats_orig == feats_mut, (
        "All features (including ret_1 and mkt_breadth) must be invariant to bars after t"
    )


def test_mutation_f_train_and_score_purges_events_selling_in_or_after_year_y():
    """Mutation (f): Bỏ purge (sell_date trong năm Y lọt vào tập train năm Y). Product: train_and_score."""
    sessions_2018 = _make_weekdays(date(2018, 12, 3), 20)
    sessions_2019 = _make_weekdays(date(2019, 1, 2), 20)
    sessions = sessions_2018 + sessions_2019
    first_sess_2019 = min(s for s in sessions if s.year == 2019)

    clean_events = [
        _make_dummy_event(
            sym=f"CLEAN{i}",
            bar_idx=120 + i,
            signal_date=sessions_2018[i],
            buy_date=sessions_2018[i + 1],
            sell_date=sessions_2018[i + 6],  # < 2019-01-02 -> MUST remain
            y_val=0.02 * (i + 1),
        )
        for i in range(3)
    ]
    straddle_event = _make_dummy_event(
        sym="STRADDLE",
        bar_idx=130,
        signal_date=sessions_2018[-2],
        buy_date=sessions_2018[-1],
        sell_date=first_sess_2019 + timedelta(days=3),  # sells inside 2019 -> MUST BE PURGED
        y_val=0.50,
    )
    exact_boundary_event = _make_dummy_event(
        sym="BOUNDARY",
        bar_idx=131,
        signal_date=sessions_2018[-3],
        buy_date=sessions_2018[-2],
        sell_date=first_sess_2019,  # sell_date == first_sess_2019 -> MUST BE PURGED (< strict)
        y_val=0.40,
    )
    test_2019 = _make_dummy_event(
        sym="TEST19",
        bar_idx=140,
        signal_date=sessions_2019[2],
        buy_date=sessions_2019[3],
        sell_date=sessions_2019[8],
        y_val=0.01,
    )

    res = train_and_score(
        events=[*clean_events, straddle_event, exact_boundary_event, test_2019],
        sessions=sessions,
        test_years=(2019,),
    )
    train_2019 = res["train_events_by_year"][2019]
    train_syms = {ev.symbol for ev in train_2019}
    assert {"CLEAN0", "CLEAN1", "CLEAN2"}.issubset(train_syms)
    assert "STRADDLE" not in train_syms, "Event selling in year Y must be purged"
    assert "BOUNDARY" not in train_syms, "Event selling on first session of Y must be purged"
    assert all(ev.sell_date is not None and ev.sell_date < first_sess_2019 for ev in train_2019)


def test_mutation_g_modifying_labels_in_year_ge_y_never_changes_year_y_scores():
    """Mutation (g): Đổi nhãn của sự kiện năm >= Y làm đổi điểm năm Y. Product: train_and_score."""
    s_2018 = _make_weekdays(date(2018, 1, 2), 200)
    s_2019 = _make_weekdays(date(2019, 1, 2), 100)
    s_2020 = _make_weekdays(date(2020, 1, 2), 60)
    sessions = s_2018 + s_2019 + s_2020

    rng = np.random.default_rng(123)
    events: list[EventRecord] = []
    # 200 training events safely selling in 2018
    for i in range(200):
        cpos = float(rng.uniform(0.0, 1.0))
        y_val = 0.04 * (cpos - 0.5) + float(rng.normal(0.0, 0.005))
        events.append(
            _make_dummy_event(
                sym=f"TR{i:03d}",
                bar_idx=120 + (i % 10),
                signal_date=s_2018[i % 150],
                buy_date=s_2018[(i % 150) + 1],
                sell_date=s_2018[(i % 150) + 6],
                y_val=y_val,
                close_pos=cpos,
            )
        )

    # 30 events in 2019 and 20 in 2020
    for i in range(30):
        events.append(
            _make_dummy_event(
                sym=f"Y19_{i:02d}",
                bar_idx=220 + i,
                signal_date=s_2019[i],
                buy_date=s_2019[i + 1],
                sell_date=s_2019[i + 6],
                y_val=0.01 * ((i % 3) - 1),
                close_pos=float(i / 29.0),
            )
        )
    for i in range(20):
        events.append(
            _make_dummy_event(
                sym=f"Y20_{i:02d}",
                bar_idx=310 + i,
                signal_date=s_2020[i],
                buy_date=s_2020[i + 1],
                sell_date=s_2020[i + 6],
                y_val=0.02 + 0.001 * i,
                close_pos=float(i / 19.0),
            )
        )

    res_base = train_and_score(events, sessions, test_years=(2019, 2020))

    # Clone and massively corrupt labels for ALL events in years >= 2019
    mutated_events: list[EventRecord] = []
    for ev in events:
        copy_ev = EventRecord(
            symbol=ev.symbol,
            bar_idx=ev.bar_idx,
            signal_date=ev.signal_date,
            buy_date=ev.buy_date,
            buy_price=ev.buy_price,
            exchange=ev.exchange,
            gt20=ev.gt20,
            vol_ratio=ev.vol_ratio,
            features=dict(ev.features),
            sell_date=ev.sell_date,
            sell_price=ev.sell_price,
            gross=ev.gross,
            mkt=ev.mkt,
            y=(ev.y + 99.0 if ev.buy_date.year >= 2019 and ev.y is not None else ev.y),
            exit_reason=ev.exit_reason,
        )
        mutated_events.append(copy_ev)

    res_mut = train_and_score(mutated_events, sessions, test_years=(2019, 2020))

    assert len(res_base["models_by_year"][2019].booster_.trees_to_dataframe()) > 1
    for ev in events:
        if ev.buy_date.year == 2019:
            assert res_base["scores_by_event_key"][ev.key] == res_mut["scores_by_event_key"][ev.key], (
                "Year 2019 score changed when >= 2019 labels were modified!"
            )


def test_mutation_h_event_trade_sells_at_exact_h_not_h_minus_1():
    """Mutation (h): Bán ở phiên i_e + H - 1. Product: event_trade."""
    sessions = _make_weekdays(date(2020, 1, 2), 30)
    bars = _make_liquid_bars("SELLH", sessions, close_val=100_000.0)
    # Signal at t=10 -> buy at e=11 (sessions[11]), H=5 -> sell at i_e + 5 = 16
    bars[11].open = 100_000.0
    bars[15].open = 50_000.0   # i_e + H - 1
    bars[16].open = 120_000.0  # i_e + H (exact target)
    bars[17].open = 80_000.0   # i_e + H + 1

    outcome = event_trade(bars, t=10, sessions=sessions, h=5, exchange="HOSE")
    assert outcome.sell_date == sessions[16]
    assert np.isclose(outcome.sell_price, 120_000.0)
    assert np.isclose(outcome.gross, 0.20)


def test_mutation_i_event_trade_defers_sell_when_floor_locked():
    """Mutation (i): Bán được khi khoá sàn. Product: event_trade."""
    sessions = _make_weekdays(date(2020, 1, 2), 30)
    bars = _make_liquid_bars("FLOOR", sessions, close_val=100_000.0)
    # Signal t=10, buy e=11, H=5 -> target sell bar index = 16.
    # Make bar 16 floor-locked on HOSE (-7% from prev close 100,000 -> 93,000, high == low)
    bars[15].close = 100_000.0
    bars[16].open = 93_000.0
    bars[16].high = 93_000.0
    bars[16].low = 93_000.0
    bars[16].close = 93_000.0

    # Bar 17 opens cleanly
    bars[17].open = 95_000.0
    bars[17].high = 96_000.0
    bars[17].low = 94_000.0
    bars[17].close = 95_500.0

    outcome = event_trade(bars, t=10, sessions=sessions, h=5, exchange="HOSE")
    assert outcome.sell_date == sessions[17], "Floor lock must defer sell to next open"
    assert np.isclose(outcome.sell_price, 95_000.0)


def test_mutation_j_ml_buy_threshold_is_cost_rt_not_zero():
    """Mutation (j): Ngưỡng mua là điểm > 0 thay vì > COST_RT. Product: simulate_event_portfolio."""
    sessions = _make_weekdays(date(2019, 1, 2), 20)
    bars_a = _make_liquid_bars("BELOW", sessions, close_val=100_000.0)
    bars_b = _make_liquid_bars("ABOVE", sessions, close_val=100_000.0)

    ev_below = _make_dummy_event("BELOW", 1, sessions[1], sessions[2], sessions[7], 0.01)
    ev_above = _make_dummy_event("ABOVE", 1, sessions[1], sessions[2], sessions[7], 0.01)

    scores = {
        ev_below.key: 0.002,              # > 0, <= COST_RT (~0.0076) -> MUST NOT BUY
        ev_above.key: COST_RT + 0.002,    # > COST_RT -> MUST BUY
    }
    sim = simulate_event_portfolio(
        events=[ev_below, ev_above],
        sessions=sessions,
        bars_by_symbol={"BELOW": bars_a, "ABOVE": bars_b},
        exchanges={"BELOW": "HOSE", "ABOVE": "HOSE"},
        h=5,
        variant="ML",
        scores=scores,
        start_date=sessions[1],
        end_date=sessions[10],
    )
    bought_syms = {tr.symbol for tr in sim["closed_trades"]}
    assert "BELOW" not in bought_syms, "Score between 0 and COST_RT must NOT be bought"
    assert "ABOVE" in bought_syms, "Score strictly > COST_RT must be bought"


def test_mutation_k_max_10_slots_and_no_rebuy_held_symbol():
    """Mutation (k): Giữ quá 10 mã, hoặc mua lại mã đang giữ. Product: simulate_event_portfolio."""
    sessions = _make_weekdays(date(2019, 1, 2), 20)

    # Part 1: Slot cap K=10 even when spare cash exceeds 2 slots.
    # - WIN buys at session 2 (sells at session 7 for ~30M cash after tripling).
    # - HOLD00..HOLD08 buy at session 4 (held until session 9).
    # - At session 8 open: 9 positions held, ~29.87M cash (~12M per slot -> affords 2 buys!),
    #   and 3 fresh signals NEW00..NEW02 arrive. K=10 cap allows only 1 buy (11 total trades, never 12).
    bars_map: dict[str, list[StockDailyBar]] = {}
    exchanges: dict[str, str] = {}
    events: list[EventRecord] = []
    scores: dict[tuple[str, date], float] = {}

    bars_win = _make_liquid_bars("WIN", sessions, close_val=100_000.0)
    bars_win[6].close = 300_000.0
    bars_win[7].open = 300_000.0
    bars_map["WIN"] = bars_win
    exchanges["WIN"] = "HOSE"
    ev_win = _make_dummy_event("WIN", 1, sessions[1], sessions[2], sessions[7], 0.05)
    events.append(ev_win)
    scores[ev_win.key] = 0.08

    for i in range(9):
        sym = f"HOLD{i:02d}"
        bars_map[sym] = _make_liquid_bars(sym, sessions, close_val=100_000.0)
        exchanges[sym] = "HOSE"
        ev = _make_dummy_event(sym, 3, sessions[3], sessions[4], sessions[9], 0.05)
        events.append(ev)
        scores[ev.key] = 0.05 - i * 0.001

    for j in range(3):
        sym = f"NEW{j:02d}"
        bars_map[sym] = _make_liquid_bars(sym, sessions, close_val=100_000.0)
        exchanges[sym] = "HOSE"
        ev = _make_dummy_event(sym, 7, sessions[7], sessions[8], sessions[13], 0.05)
        events.append(ev)
        scores[ev.key] = 0.06 - j * 0.001

    sim1 = simulate_event_portfolio(
        events=events,
        sessions=sessions,
        bars_by_symbol=bars_map,
        exchanges=exchanges,
        h=5,
        variant="ML",
        scores=scores,
        start_date=sessions[1],
        end_date=sessions[15],
    )
    assert len(sim1["closed_trades"]) == 11, (
        "Must cap open positions at K=10 (1 WIN + 9 HOLD + 1 NEW = 11 total)"
    )

    # Part 2: Rebuy check — same symbol fires another event while held (between sessions[2] and sessions[7])
    ev_held_1 = _make_dummy_event("HOLD00", 1, sessions[1], sessions[2], sessions[7], 0.05)
    ev_held_2 = _make_dummy_event("HOLD00", 3, sessions[3], sessions[4], sessions[9], 0.08)
    sim2 = simulate_event_portfolio(
        events=[ev_held_1, ev_held_2],
        sessions=sessions,
        bars_by_symbol={"HOLD00": bars_map["HOLD00"]},
        exchanges={"HOLD00": "HOSE"},
        h=5,
        variant="ML",
        scores={ev_held_1.key: 0.05, ev_held_2.key: 0.08},
        start_date=sessions[1],
        end_date=sessions[11],
    )
    assert len(sim2["closed_trades"]) == 1, "Must NOT rebuy a symbol while already held"
    assert sim2["closed_trades"][0].entry_date == sessions[2]


def _make_hand_calculated_fee_scenario():
    """Hand-calculated scenario exercising all 3 fee branches (buy, TIME sell, END sell):

    - Initial capital = 100,000,000, K = 10, H = 5.
    - SYM1 buys at sessions[2] open @ 100,000 (v1 = 10,000,000 -> 100 shares, buy_fee_1 = 33,000).
      Closes TIME at sessions[7] open @ 110,000 (gross = 11,000,000, sell_fee_1 = 47,300).
      On sessions[4] close (before SYM2 buy signal), SYM1 closes at 100,330 so NAV[4] == 100,000,000 exact!
    - SYM2 buys at sessions[5] open @ 100,000 (v2 = 10,000,000 -> 100 shares, buy_fee_2 = 33,000).
      At end_date = sessions[8] close (before maturity), closes END @ 120,000
      (gross = 12,000,000, sell_fee_2 = 51,600).
    - Hand-calculated totals:
      total_fees = 33,000 + 33,000 + 47,300 + 51,600 = 164,900.0
      final_nav  = 100,000,000 - 10,033,000 - 10,033,000 + 10,952,700 + 11,948,400 = 102,835,100.0
    """
    sessions = _make_weekdays(date(2019, 1, 2), 15)
    bars_1 = _make_liquid_bars("SYM1", sessions, close_val=100_000.0)
    bars_2 = _make_liquid_bars("SYM2", sessions, close_val=100_000.0)

    bars_1[4].close = 100_330.0
    bars_1[7].open = 110_000.0
    bars_1[7].high = 110_000.0
    bars_1[7].close = 110_000.0

    bars_2[8].close = 120_000.0
    bars_2[8].high = 120_000.0

    ev1 = _make_dummy_event("SYM1", 1, sessions[1], sessions[2], sessions[7], 0.05)
    ev2 = _make_dummy_event("SYM2", 4, sessions[4], sessions[5], None, None)

    scores = {ev1.key: 0.05, ev2.key: 0.05}
    return sessions, {"SYM1": bars_1, "SYM2": bars_2}, [ev1, ev2], scores


def test_mutation_l1_l2_l3_hand_calculated_fees_and_final_nav():
    """Mutations (l1, l2, l3): Bỏ phí ở nhánh mua / bán thường / bán END. Product: simulate_event_portfolio."""
    sessions, bars_map, events, scores = _make_hand_calculated_fee_scenario()

    sim = simulate_event_portfolio(
        events=events,
        sessions=sessions,
        bars_by_symbol=bars_map,
        exchanges={"SYM1": "HOSE", "SYM2": "HOSE"},
        h=5,
        variant="ML",
        scores=scores,
        start_date=sessions[0],
        end_date=sessions[8],
    )

    expected_total_fees = 164_900.0
    expected_final_nav = 102_835_100.0

    reasons = {tr.symbol: tr.exit_reason for tr in sim["closed_trades"]}
    assert reasons == {"SYM1": "TIME", "SYM2": "END"}
    assert np.isclose(sim["total_fees"], expected_total_fees, atol=1e-2), (
        f"Expected total_fees={expected_total_fees}, got {sim['total_fees']}"
    )
    assert np.isclose(sim["final_nav"], expected_final_nav, atol=1e-2), (
        f"Expected final_nav={expected_final_nav}, got {sim['final_nav']}"
    )


def test_mutation_m_mdd_uses_daily_nav_not_monthly():
    """Mutation (m): MDD tính trên NAV tháng thay vì NAV ngày. Product: simulate_event_portfolio."""
    sessions = _make_weekdays(date(2019, 1, 2), 45)
    # SYM bought at sessions[2] open @ 100,000 (10% slot), H=20 so held past mid-month crash and recovery
    bars = _make_liquid_bars("CRASH", sessions, close_val=100_000.0)
    # Mid-month Jan crash: close plunges to 10,000 (~90% stock drop -> ~9% portfolio drop)
    bars[10].close = 10_000.0
    bars[10].low = 10_000.0
    # Month-end (Jan 31 is around sessions[21]) recovers completely to 110,000
    for idx in range(11, len(sessions)):
        bars[idx].open = 110_000.0
        bars[idx].high = 110_000.0
        bars[idx].close = 110_000.0

    ev = _make_dummy_event("CRASH", 1, sessions[1], sessions[2], sessions[22], 0.05)
    sim = simulate_event_portfolio(
        events=[ev],
        sessions=sessions,
        bars_by_symbol={"CRASH": bars},
        exchanges={"CRASH": "HOSE"},
        h=20,
        variant="ML",
        scores={ev.key: 0.05},
        start_date=sessions[0],
        end_date=sessions[-1],
    )
    assert sim["mdd"] >= 0.08, (
        "Daily MDD must capture intra-month crash even when monthly NAV strictly increases"
    )


def test_mutation_n_b0_prioritizes_by_vol_ratio_not_score():
    """Mutation (n): B0 ưu tiên theo điểm thay vì vol_ratio. Product: simulate_event_portfolio."""
    sessions = _make_weekdays(date(2019, 1, 2), 20)
    bars_map: dict[str, list[StockDailyBar]] = {}
    exchanges: dict[str, str] = {}
    events: list[EventRecord] = []
    scores: dict[tuple[str, date], float] = {}

    # 11 symbols: S00 has LOWEST vol_ratio (2.1) but HIGHEST score (0.99).
    # S01..S10 have HIGH vol_ratio (3.0..3.9) and NEGATIVE/LOW scores (-0.05).
    # B0 must pick S01..S10 by vol_ratio and skip S00.
    for i in range(11):
        sym = f"S{i:02d}"
        bars_map[sym] = _make_liquid_bars(sym, sessions, close_val=100_000.0)
        exchanges[sym] = "HOSE"
        vr = 2.1 if i == 0 else 3.0 + i * 0.1
        ev = _make_dummy_event(sym, 1, sessions[1], sessions[2], sessions[7], 0.01, vol_ratio=vr)
        events.append(ev)
        scores[ev.key] = 0.99 if i == 0 else -0.05

    sim = simulate_event_portfolio(
        events=events,
        sessions=sessions,
        bars_by_symbol=bars_map,
        exchanges=exchanges,
        h=5,
        variant="B0",
        scores=scores,
        start_date=sessions[1],
        end_date=sessions[10],
    )
    bought_syms = {tr.symbol for tr in sim["closed_trades"]}
    assert len(bought_syms) == 10
    assert "S00" not in bought_syms, "B0 must prioritize by vol_ratio, NOT ML score"


def test_mutation_o_run_exploration_enforces_ledger_safety(tmp_path: Path):
    """Mutation (o): run_exploration bỏ assert_ledger_safety hoặc xoá sổ cũ. Product: run_exploration."""
    existing_ledger = tmp_path / "trial_ledger.csv"
    existing_ledger.write_text("utc_ts,idea_id\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="đã tồn tại; sổ thử không được xoá để chạy lại"):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=existing_ledger,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
        )


# ==============================================================================
# Extra Tests (§4): Positive Control, Negative Control, Determinism, Validation
# ==============================================================================


def _make_synthetic_ml_world(seed: int = 227) -> tuple[
    list[date],
    dict[str, list[StockDailyBar]],
    dict[str, str],
    list[EventRecord],
]:
    """Build synthetic multi-year event world where return is strongly proportional to close_pos.

    Half of events have close_pos ~ 0.92 and positive future excess return (~+4.5%);
    half have close_pos ~ 0.12 and negative future excess return (~-3.5%).
    B0 buys blindly (vol_ratio independent of close_pos), while ML learns close_pos -> beats B0 cleanly.
    """
    rng = np.random.default_rng(seed)
    # Sessions covering 2016..2022 (~1760 weekdays)
    sessions = _make_weekdays(date(2016, 1, 4), 1780)
    sessions = [s for s in sessions if s <= date(2022, 12, 30)]
    n_sess = len(sessions)

    # Create 12 liquid stocks whose base bars stay flat so open[sell]/open[buy]-1 == 0 for market benchmark
    # We put event-day close_pos patterns directly in events with consistent prices on event buy/sell dates
    # by letting two stocks alternate event periods and keeping 10 benchmark stocks flat!
    bars_by_sym: dict[str, list[StockDailyBar]] = {}
    exchanges: dict[str, str] = {}
    for b_idx in range(10):
        sym = f"BM{b_idx:02d}"
        bars_by_sym[sym] = _make_liquid_bars(sym, sessions, close_val=100_000.0, volume_val=60_000.0)
        exchanges[sym] = "HOSE"

    # Build 20 tradeable stocks; place isolated non-overlapping event windows on them
    for s_idx in range(20):
        sym = f"EV{s_idx:02d}"
        bars_by_sym[sym] = _make_liquid_bars(sym, sessions, close_val=100_000.0, volume_val=60_000.0)
        exchanges[sym] = "HOSE"

    h = 5
    base_events: list[EventRecord] = []
    # Every 10 sessions starting at 130, generate a batch of 10 events across EV00..EV19
    for t in range(130, n_sess - 12, 12):
        batch_offset = 0 if ((t // 12) % 2 == 0) else 10
        for j in range(10):
            sym = f"EV{batch_offset + j:02d}"
            bars = bars_by_sym[sym]
            good_signal = bool(j % 2 == 0)

            # Construct signal bar t
            if good_signal:
                bars[t].open = 100_000.0
                bars[t].low = 98_000.0
                bars[t].high = 102_200.0
                bars[t].close = 102_000.0  # close_pos = (102-98)/(102.2-98) ~ 0.952
                bars[t].volume = float(rng.uniform(130_000.0, 220_000.0))
                ret = 0.045 + float(rng.normal(0.0, 0.004))
            else:
                bars[t].open = 103_000.0
                bars[t].low = 100_400.0
                bars[t].high = 105_000.0
                bars[t].close = 100_600.0  # close_pos ~ 0.043 (still > prev close 100_000)
                bars[t].volume = float(rng.uniform(130_000.0, 220_000.0))
                ret = -0.035 + float(rng.normal(0.0, 0.004))

            # Set open at buy (t+1) and open at sell (t+1+h)
            bars[t + 1].open = 100_000.0
            bars[t + 1].close = 100_000.0
            sell_bar_open = 100_000.0 * (1.0 + ret)
            for k in range(t + 2, t + 1 + h):
                bars[k].open = 100_000.0
                bars[k].close = 100_000.0
            bars[t + 1 + h].open = sell_bar_open
            bars[t + 1 + h].close = 100_000.0

    ctx = precompute_market_context(bars_by_sym, min_turnover=MIN_TURNOVER_227)
    raw_evs = find_events(bars_by_sym, sessions, exchanges, min_turnover=MIN_TURNOVER_227)
    base_events = prepare_events_with_outcomes(
        raw_evs, bars_by_sym, sessions, exchanges, h=h, min_turnover=MIN_TURNOVER_227, ctx=ctx
    )
    return sessions, bars_by_sym, exchanges, base_events


def test_positive_and_negative_controls_and_determinism():
    """§4 Extra tests: positive control, shuffled negative control, and determinism."""
    sessions, bars_by_sym, exchanges, events = _make_synthetic_ml_world(seed=227)

    # Filter rebalance dates for 2019-2022 (or 2018-12 to 2022-12)
    from scripts.research193_core import (
        calculate_rotation_metrics,
        ew_benchmark,
        get_rebalance_dates,
    )

    all_rebal = get_rebalance_dates(sessions)
    rebal_dates = [r for r in all_rebal if (2018, 12) <= (r.year, r.month) <= (2022, 12)]
    start_2019 = next(s for s in sessions if s.year == 2019)
    end_2022 = max(s for s in sessions if s.year == 2022)
    ew_rets = ew_benchmark(rebal_dates, bars_by_sym, sessions, min_turnover=MIN_TURNOVER_227)

    ml_fit_1 = train_and_score(events, sessions, test_years=(2019, 2020, 2021, 2022), shuffle_labels=False)
    ml_fit_2 = train_and_score(events, sessions, test_years=(2019, 2020, 2021, 2022), shuffle_labels=False)
    shuf_fit = train_and_score(
        events, sessions, test_years=(2019, 2020, 2021, 2022), shuffle_labels=True, shuffle_seed=227
    )

    # 1. Determinism: identical predictions across repeated runs
    assert ml_fit_1["scores_by_event_key"] == ml_fit_2["scores_by_event_key"], (
        "train_and_score must be completely deterministic"
    )

    sim_ml = simulate_event_portfolio(
        events, sessions, bars_by_sym, exchanges, h=5, variant="ML",
        scores=ml_fit_1["scores_by_event_key"], rebalance_dates=rebal_dates,
        start_date=start_2019, end_date=end_2022, cost_threshold=COST_RT,
    )
    sim_b0 = simulate_event_portfolio(
        events, sessions, bars_by_sym, exchanges, h=5, variant="B0",
        scores=None, rebalance_dates=rebal_dates,
        start_date=start_2019, end_date=end_2022, cost_threshold=COST_RT,
    )
    sim_shuf = simulate_event_portfolio(
        events, sessions, bars_by_sym, exchanges, h=5, variant="SHUFFLE",
        scores=shuf_fit["scores_by_event_key"], rebalance_dates=rebal_dates,
        start_date=start_2019, end_date=end_2022, cost_threshold=COST_RT,
    )

    m_ml = calculate_rotation_metrics(sim_ml["monthly_returns"], ew_rets, rebal_dates, {"cagr": sim_ml["cagr"], "mdd": sim_ml["mdd"], "calmar": sim_ml["calmar"]}, seed=227)
    m_b0 = calculate_rotation_metrics(sim_b0["monthly_returns"], ew_rets, rebal_dates, {"cagr": sim_b0["cagr"], "mdd": sim_b0["mdd"], "calmar": sim_b0["calmar"]}, seed=227)
    m_shuf = calculate_rotation_metrics(sim_shuf["monthly_returns"], ew_rets, rebal_dates, {"cagr": sim_shuf["cagr"], "mdd": sim_shuf["mdd"], "calmar": sim_shuf["calmar"]}, seed=227)

    # 2. Positive control: ML cleanly beats B0 on signal proportional to close_pos
    assert m_ml["mean_X"] > m_b0["mean_X"] + 0.005, (
        f"Positive control failed: ML mean_X={m_ml['mean_X']:.4f} vs B0 mean_X={m_b0['mean_X']:.4f}"
    )

    # 3. Negative control: shuffled labels provide no meaningful edge over B0.
    # Justification of threshold: with ~50% +4.5% / ~50% -3.5% random labels and mean_y ~ +0.5% < COST_RT (0.76%),
    # shuffled LGBM either stays mostly flat in cash or picks randomly around mean, so mean_X_shuf stays far below true ML
    # and cannot beat random B0 baseline by > +0.005/month.
    assert m_shuf["mean_X"] < m_b0["mean_X"] + 0.005, (
        f"Negative control failed: SHUFFLE mean_X={m_shuf['mean_X']:.4f} vs B0={m_b0['mean_X']:.4f}"
    )
    assert m_shuf["mean_X"] < m_ml["mean_X"] - 0.005


def test_run_validation_synthetic_tmp_path(tmp_path: Path):
    """Test run_validation on synthetic train/validation directories in tmp_path (§5)."""
    sessions_all = _make_weekdays(date(2019, 1, 2), 900)
    train_sessions = [s for s in sessions_all if s.year <= 2021]
    val_sessions = [s for s in sessions_all if s.year >= 2021]

    rng = np.random.default_rng(99)
    train_bars: dict[str, list[StockDailyBar]] = {}
    train_exch: dict[str, str] = {}
    for sym in ("BM1", "BM2"):
        train_bars[sym] = _make_liquid_bars(sym, train_sessions, 100_000.0, 60_000.0)
        train_exch[sym] = "HOSE"
    for j in range(6):
        sym = f"TR{j}"
        bars = _make_liquid_bars(sym, train_sessions, 100_000.0, 60_000.0)
        for t in range(130, len(train_sessions) - 10, 15):
            bars[t].close = 102_000.0
            bars[t].high = 102_500.0
            bars[t].low = 98_500.0
            bars[t].volume = 160_000.0
            bars[t + 6].open = 103_000.0 + float(rng.uniform(0.0, 2_000.0))
        train_bars[sym] = bars
        train_exch[sym] = "HOSE"

    val_bars: dict[str, list[StockDailyBar]] = {}
    val_exch: dict[str, str] = {}
    for sym in ("VBM1", "VBM2"):
        val_bars[sym] = _make_liquid_bars(sym, val_sessions, 100_000.0, 60_000.0)
        val_exch[sym] = "HOSE"
    for j in range(4):
        sym = f"VA{j}"
        bars = _make_liquid_bars(sym, val_sessions, 100_000.0, 60_000.0)
        for t in range(130, len(val_sessions) - 10, 15):
            bars[t].close = 102_000.0
            bars[t].high = 102_500.0
            bars[t].low = 98_500.0
            bars[t].volume = 160_000.0
            bars[t + 6].open = 102_000.0
        val_bars[sym] = bars
        val_exch[sym] = "HOSE"

    train_dir = tmp_path / "train"
    val_dir = tmp_path / "val"
    _write_synthetic_dataset_dir(train_dir, train_sessions, train_bars, train_exch)
    _write_synthetic_dataset_dir(val_dir, val_sessions, val_bars, val_exch)

    val_start = date(2022, 1, 3)
    val_end = max(s for s in val_sessions if s.year == 2022)
    out = run_validation(
        data_dir=val_dir,
        model_train_dir=train_dir,
        h=5,
        start=val_start,
        end=val_end,
    )
    assert out["h"] == 5
    assert out["n_val_events"] > 0
    assert 2022 in out["train_counts_by_year"]
    assert out["train_counts_by_year"][2022] > 0
    assert len(out["scores_by_event_key"]) == out["n_val_events"]


def test_compute_event_label_requires_liquid_universe_at_prev_session():
    """Verify compute_event_label computes y = gross - mkt strictly from liquid universe at prev_sess."""
    sessions = _make_weekdays(date(2020, 1, 2), 35)
    # Two liquid market stocks open at 100k on sessions[21] and 110k on sessions[26] -> mkt = +10%
    m1 = _make_liquid_bars("M1", sessions, close_val=100_000.0, volume_val=60_000.0)
    m1[26].open = 110_000.0
    # One illiquid stock opens at 100k and doubles -> MUST be excluded from mkt!
    ill = _make_liquid_bars("ILL", sessions, close_val=1_000.0, volume_val=100.0)
    ill[26].open = 2_000.0

    # Target stock opens at 100k on sessions[21] and sells at 115k on sessions[26] -> gross = +15%
    tgt = _make_liquid_bars("TGT", sessions, close_val=100_000.0, volume_val=60_000.0)
    tgt[26].open = 115_000.0

    universe = {"M1": m1, "ILL": ill, "TGT": tgt}
    outcome = event_trade(tgt, t=20, sessions=sessions, h=5, exchange="HOSE")
    y_val, mkt_val = compute_event_label(outcome, universe, sessions, min_turnover=MIN_TURNOVER_227)

    # Liquid universe at sessions[20] is {M1, TGT}: M1 ret = +10%, TGT ret = +15% -> mean mkt = +12.5%
    assert mkt_val is not None and np.isclose(mkt_val, 0.125)
    assert y_val is not None and np.isclose(y_val, 0.15 - 0.125)
