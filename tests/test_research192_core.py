"""Unit tests and mutation test suite for scripts/research192_core.py and scripts/research192_explore.py.

Includes:
- Data loading tests for load_sessions.
- Window generation tests for get_tom_windows and get_prehol_windows.
- Hand-calculated 2-symbol synthetic test for time_baseline_excess (§3.4).
- 10 mutation tests (a)–(j) from Brief 192 §4, each directly calling the exact
  product function specified in the table without any flags in product code.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.research188_core import Trade
from scripts.research191_data import StockDailyBar
from scripts.research192_core import (
    generate_calendar_trades,
    get_prehol_windows,
    get_tom_windows,
    load_sessions,
    time_baseline_excess,
)
from scripts.research192_explore import run_exploration


def _write_csv_gz(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        f.writelines(",".join(str(x) for x in r) + "\n" for r in rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_dummy_bars(
    sym: str,
    dates: list[date],
    base_price: float = 100.0,
    volume: float = 200_000_000.0,
    price_map: dict[date, float] | None = None,
) -> list[StockDailyBar]:
    bars = []
    for d in dates:
        p = price_map.get(d, base_price) if price_map else base_price
        bars.append(
            StockDailyBar(
                symbol=sym,
                date=d,
                open=p,
                high=p,
                low=p,
                close=p,
                volume=volume,
            )
        )
    return bars


# ==============================================================================
# 1. Loader & Calendar Tests
# ==============================================================================


def test_load_sessions_missing_manifest_raises(tmp_path: Path):
    sess_file = tmp_path / "sessions.csv"
    sess_file.write_text("date\n2020-01-02\n")
    with pytest.raises(FileNotFoundError, match="Missing manifest.json"):
        load_sessions(tmp_path)


def test_load_sessions_checksum_mismatch_raises(tmp_path: Path):
    sess_file = tmp_path / "sessions.csv"
    sess_file.write_text("date\n2020-01-02\n")
    manifest = {"files": {"sessions.csv": {"sha256": "wrong_sha"}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Checksum mismatch"):
        load_sessions(tmp_path)


def test_load_sessions_happy_path_and_end_filter(tmp_path: Path):
    sess_file = tmp_path / "sessions.csv"
    sess_file.write_text("date\n2020-01-02\n2020-01-03\n2020-01-06\n")
    manifest = {"files": {"sessions.csv": {"sha256": _sha256(sess_file)}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    res = load_sessions(tmp_path, end="2020-01-10")
    assert len(res) == 3
    assert res[0] == date(2020, 1, 2)
    assert res[2] == date(2020, 1, 6)

    with pytest.raises(ValueError, match="exceeds end limit"):
        load_sessions(tmp_path, end="2020-01-04")


# ==============================================================================
# 2. Hand-Calculated 2-Symbol Synthetic Test for time_baseline_excess (§3.4)
# ==============================================================================


def test_time_baseline_excess_hand_calculated_2_symbols():
    """Verify time_baseline_excess with exact hand-calculated numbers (§3.4).

    Setup:
    - 2 symbols: AAA and BBB.
    - 25 sessions: s0 through s24 (daily increments).
    - Liquid threshold: 10 billion VND. Both symbols have 200,000,000 volume @ 100 VND
      (turnover = 20 billion VND >= 10B) so is_liquid is True at every session after s19.
    - Consider holding length h = 2 sessions.
    - Evaluation period: s20 to s22.
      - Session s20: price AAA = 100, s22 (s20+2): price AAA = 120 -> return = +0.20
      - Session s21: price AAA = 100, s23 (s21+2): price AAA = 110 -> return = +0.10
      - Session s22: price AAA = 120, s24 (s22+2): price AAA = 90  -> return = 90/120 - 1 = -0.25
      Expected AAA baseline mean return = (0.20 + 0.10 - 0.25) / 3 = 0.05 / 3 = 0.01666667.

      - Session s20: price BBB = 100, s22: price BBB = 105 -> return = +0.05
      - Session s21: price BBB = 100, s23: price BBB = 105 -> return = +0.05
      - Session s22: price BBB = 105, s24: price BBB = 105 -> return = 105/105 - 1 = 0.00
      Expected BBB baseline mean return = (0.05 + 0.05 + 0.00) / 3 = 0.10 / 3 = 0.03333333.

    - Trade on AAA from s20 to s22: net_return = 0.15.
      Excess AAA = 0.15 - 0.01666667 = 0.13333333.
    - Trade on BBB from s20 to s22: net_return = 0.08.
      Excess BBB = 0.08 - 0.03333333 = 0.04666667.

    - Mean excess = (0.13333333 + 0.04666667) / 2 = 0.18 / 2 = 0.09000000.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    s20, s21, s22, s23, s24 = sessions[20], sessions[21], sessions[22], sessions[23], sessions[24]

    price_map_aaa = {s20: 100.0, s21: 100.0, s22: 120.0, s23: 110.0, s24: 90.0}
    price_map_bbb = {s20: 100.0, s21: 100.0, s22: 105.0, s23: 105.0, s24: 105.0}

    bars_aaa = _make_dummy_bars("AAA", sessions, base_price=100.0, price_map=price_map_aaa)
    bars_bbb = _make_dummy_bars("BBB", sessions, base_price=100.0, price_map=price_map_bbb)

    bars_by_symbol = {"AAA": bars_aaa, "BBB": bars_bbb}

    t_aaa = Trade(
        symbol="AAA",
        entry_ts=datetime.combine(s20, datetime.min.time(), tzinfo=UTC),
        exit_ts=datetime.combine(s22, datetime.min.time(), tzinfo=UTC),
        entry_price=100.0,
        exit_price=115.0,
        net_return=0.15,
        gross_return=0.15,
        market="stock",
        side="long",
        score=100.0,
        holding_sessions=2,
    )
    t_bbb = Trade(
        symbol="BBB",
        entry_ts=datetime.combine(s20, datetime.min.time(), tzinfo=UTC),
        exit_ts=datetime.combine(s22, datetime.min.time(), tzinfo=UTC),
        entry_price=100.0,
        exit_price=108.0,
        net_return=0.08,
        gross_return=0.08,
        market="stock",
        side="long",
        score=100.0,
        holding_sessions=2,
    )

    res = time_baseline_excess(
        trades=[t_aaa, t_bbb],
        bars_by_symbol=bars_by_symbol,
        sessions=sessions,
        period_start=s20,
        period_end=s22,
    )

    expected_excess_aaa = 0.15 - (0.05 / 3.0)  # 0.13333333
    expected_excess_bbb = 0.08 - (0.10 / 3.0)  # 0.04666667
    expected_mean_excess = (expected_excess_aaa + expected_excess_bbb) / 2.0  # 0.09000000

    assert np.isclose(res["mean_excess"], expected_mean_excess, atol=1e-6)
    assert np.isclose(res["mean_excess_trim1pct"], expected_mean_excess, atol=1e-6)


# ==============================================================================
# 3. Ten Mutation Tests (a)–(j) Calling Exact Product Functions (§4)
# ==============================================================================


def test_mutation_a_tom_calendar_uses_session_not_calendar_end():
    """Mutation (a): L(M) takes calendar month end instead of last session in S.

    Product function called: get_tom_windows(sessions, k, m).
    In May 2020: 2020-05-31 is a Sunday. The last trading session L(M) is Friday 2020-05-29.
    For k=1, m=2: buy session b must be 2020-05-29 (not Sunday 2020-05-31).
    """
    sessions = [
        date(2020, 5, 27),
        date(2020, 5, 28),
        date(2020, 5, 29),  # Friday: L(May 2020)
        date(2020, 6, 1),   # Monday: 1st session of June
        date(2020, 6, 2),   # Tuesday: 2nd session of June (m=2)
        date(2020, 6, 3),
    ]
    windows = get_tom_windows(sessions, k=1, m=2)
    assert len(windows) == 1
    b, e, _wid = windows[0]
    assert b == date(2020, 5, 29), "b must be the last trading session L(M), not calendar month end 2020-05-31"
    assert e == date(2020, 6, 2)


def test_mutation_b_prehol_calendar_excludes_regular_weekend():
    """Mutation (b): Holiday treats regular weekend (Fri -> Mon) as holiday.

    Product function called: get_prehol_windows(sessions, n, q).
    Regular weekend: Friday followed by Monday (no Mon-Fri gap days).
    Must NOT generate any pre-holiday windows!
    """
    # Pure regular weekend: Friday 2020-05-15 to Monday 2020-05-18
    sessions = [
        date(2020, 5, 13),
        date(2020, 5, 14),
        date(2020, 5, 15),  # Friday
        date(2020, 5, 18),  # Monday
        date(2020, 5, 19),
        date(2020, 5, 20),
    ]
    windows = get_prehol_windows(sessions, n=2, q=1)
    assert len(windows) == 0, "Regular weekend must not generate holiday windows"


def test_mutation_c_universe_gtgd20_up_to_session_before_b():
    """Mutation (c): Universe uses GTGD20 up to session b instead of session before b.

    Product function called: generate_calendar_trades.
    Stock has low turnover (5 tỷ < 10 tỷ) for all 20 sessions up to b_prev.
    On session b, stock has massive 100 tỷ turnover.
    If product function strictly evaluates up to b_prev, stock is NOT liquid and 0 trades generated.
    """
    # 25 sessions: s0..s20 (b_prev=s20, b=s21, e=s23)
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    b, e = sessions[21], sessions[23]

    # AAA has volume 80,000,000 @ 100 -> 8 billion VND turnover up to b_prev (illiquid < 10B)
    # At session b, volume jumps to 500,000,000 (50 billion VND), making 20-session turnover up to b = 10.1B >= 10B
    bars_aaa = _make_dummy_bars("AAA", sessions, base_price=100.0, volume=80_000_000.0)
    for bar in bars_aaa:
        if bar.date == b:
            bar.volume = 500_000_000.0

    windows = [(b, e, "TEST_WINDOW")]
    trades = generate_calendar_trades(
        windows=windows,
        bars_by_symbol={"AAA": bars_aaa},
        sessions=sessions,
        exchanges={"AAA": "HOSE"},
    )
    assert len(trades) == 0, "Stock was illiquid up to b_prev; must not enter based on session b volume"


def test_mutation_d_entry_drops_ceiling_locked():
    """Mutation (d): Omit ceiling lock check on buy session b.

    Product function called: generate_calendar_trades.
    Stock is ceiling-locked on session b (high == low == limit_up).
    Product function must drop the stock (0 trades).
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    b, e = sessions[21], sessions[23]

    bars = _make_dummy_bars("AAA", sessions, base_price=100.0, volume=200_000_000.0)
    # Make session b ceiling-locked (+7% on HOSE)
    ceiling_price = 107.0
    for bar in bars:
        if bar.date == b:
            bar.open = ceiling_price
            bar.high = ceiling_price
            bar.low = ceiling_price
            bar.close = ceiling_price

    windows = [(b, e, "TEST_CEILING")]
    trades = generate_calendar_trades(
        windows=windows,
        bars_by_symbol={"AAA": bars},
        sessions=sessions,
        exchanges={"AAA": "HOSE"},
    )
    assert len(trades) == 0, "Ceiling locked stock at session b must be skipped"


def test_mutation_e_exit_defers_floor_locked():
    """Mutation (e): Omit rolling sell when session e is floor-locked.

    Product function called: generate_calendar_trades.
    Session e is floor-locked (-7% on HOSE), unlocks on session e+1.
    Product function must roll exit to session e+1.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(26)]
    b, e, e_plus_1 = sessions[21], sessions[23], sessions[24]

    bars = _make_dummy_bars("AAA", sessions, base_price=100.0, volume=200_000_000.0)
    floor_price = 93.0
    for bar in bars:
        if bar.date == e:
            bar.open = floor_price
            bar.high = floor_price
            bar.low = floor_price
            bar.close = floor_price
        elif bar.date == e_plus_1:
            bar.open = 95.0
            bar.high = 96.0
            bar.low = 94.0
            bar.close = 95.0

    windows = [(b, e, "TEST_FLOOR")]
    trades = generate_calendar_trades(
        windows=windows,
        bars_by_symbol={"AAA": bars},
        sessions=sessions,
        exchanges={"AAA": "HOSE"},
    )
    assert len(trades) == 1
    assert trades[0].exit_ts.date() == e_plus_1, "Exit must roll to e+1 when e is floor locked"


def test_mutation_f_entry_limits_max_10_symbols():
    """Mutation (f): Omit 10 symbols limit.

    Product function called: generate_calendar_trades.
    15 liquid eligible stocks. Product function must select exactly 10.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    b, e = sessions[21], sessions[23]

    bars_by_symbol = {}
    for i in range(15):
        sym = f"S{i:02d}"
        bars_by_symbol[sym] = _make_dummy_bars(sym, sessions, base_price=100.0, volume=200_000_000.0)

    windows = [(b, e, "TEST_MAX10")]
    trades = generate_calendar_trades(
        windows=windows,
        bars_by_symbol=bars_by_symbol,
        sessions=sessions,
        exchanges={f"S{i:02d}": "HOSE" for i in range(15)},
        max_symbols=10,
    )
    assert len(trades) == 10, "Must limit selection to at most 10 symbols"


def test_mutation_g_baseline_period_bounds():
    """Mutation (g): Baseline evaluates j on all data instead of within [period_start, period_end].

    Product function called: time_baseline_excess.
    Period is [s20, s22]. Holding h = 2.
    Inside [s19, s24], price is completely flat at 100.0 (return = 0.0%).
    Outside period: session s10 -> s12 has a massive 400% jump (100 -> 500),
    and session s24 -> s26 has a massive 400% jump.
    If baseline strictly evaluates j in [s20, s22], baseline return is exactly 0.0%.
    If mutated to evaluate j across all data, baseline return is heavily inflated (> 0.50).
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(30)]
    s20, s22 = sessions[20], sessions[22]

    price_map = {s: 100.0 for s in sessions}
    # Out-of-period jumps
    price_map[sessions[12]] = 500.0
    price_map[sessions[26]] = 500.0

    bars = _make_dummy_bars("AAA", sessions, base_price=100.0, price_map=price_map)
    t = Trade(
        symbol="AAA",
        entry_ts=datetime.combine(s20, datetime.min.time(), tzinfo=UTC),
        exit_ts=datetime.combine(s22, datetime.min.time(), tzinfo=UTC),
        entry_price=100.0,
        exit_price=100.0,
        net_return=0.0,
        gross_return=0.0,
        market="stock",
        side="long",
        score=100.0,
        holding_sessions=2,
    )

    res = time_baseline_excess(
        trades=[t],
        bars_by_symbol={"AAA": bars},
        sessions=sessions,
        period_start=s20,
        period_end=s22,
    )
    # In-period baseline: return from s20->s22 is (100/100 - 1) = 0.0
    assert np.isclose(res["mean_excess"], 0.0, atol=1e-4), "Baseline must only evaluate j within [period_start, period_end]"


def test_mutation_h_baseline_requires_liquidity():
    """Mutation (h): Baseline omits liquidity condition on session before j.

    Product function called: time_baseline_excess.
    At session s20, stock was liquid at s19 (volume 200M). Price s20->s22 is flat (0.0%).
    At session s21, stock was illiquid at s20 (volume 0M, turnover 0). Price s21->s23 drops -50%.
    With liquidity filter, only s20 is evaluated (baseline = 0.0%).
    Without liquidity filter, baseline includes s21 (baseline = (0 - 0.5)/2 = -0.25).
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(26)]
    s20, s21, s22 = sessions[20], sessions[21], sessions[22]

    bars = _make_dummy_bars("AAA", sessions, base_price=100.0, volume=200_000_000.0)
    # Make s20 have 0 volume for 20 sessions prior to s21, so session before s21 is illiquid
    for i in range(1, 21):
        bars[i].volume = 0.0

    # Prices
    bars[21].close = 100.0  # s21
    bars[23].close = 50.0   # s23 (-50%)

    t = Trade(
        symbol="AAA",
        entry_ts=datetime.combine(s20, datetime.min.time(), tzinfo=UTC),
        exit_ts=datetime.combine(s22, datetime.min.time(), tzinfo=UTC),
        entry_price=100.0,
        exit_price=100.0,
        net_return=0.0,
        gross_return=0.0,
        market="stock",
        side="long",
        score=100.0,
        holding_sessions=2,
    )

    res = time_baseline_excess(
        trades=[t],
        bars_by_symbol={"AAA": bars},
        sessions=sessions,
        period_start=s20,
        period_end=s21,
    )
    # Only s20 had liquid previous 20 sessions; s21 is rejected by is_liquid
    assert np.isclose(res["mean_excess"], 0.0, atol=1e-4), "Baseline must enforce is_liquid on session before j"


def test_mutation_i_exploration_asserts_ledger_safety(tmp_path: Path):
    """Mutation (i): run_exploration deletes old ledger or omits assert_ledger_safety.

    Product function called: run_exploration with ledger_path in tmp_path.
    If ledger file already exists, run_exploration must raise SystemExit at line 1.
    """
    existing_ledger = tmp_path / "trial_ledger.csv"
    existing_ledger.write_text("existing ledger data\n")

    with pytest.raises(SystemExit, match="đã tồn tại; sổ thử không được xoá để chạy lại"):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=existing_ledger,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
        )


def test_mutation_j_enforces_t_plus_2_holding():
    """Mutation (j): Allows selling when e - b = 1 (violates T+2).

    Product function called: generate_calendar_trades with window where e - b = 1.
    Product function must enforce T+2 and raise AssertionError.
    """
    sessions = [date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6)]
    b = sessions[0]
    e = sessions[1]  # index 1 - index 0 = 1 session (T+1, violates T+2)

    bars = _make_dummy_bars("AAA", sessions, base_price=100.0)
    windows = [(b, e, "INVALID_T1")]

    with pytest.raises(AssertionError, match="T\\+2 violated"):
        generate_calendar_trades(
            windows=windows,
            bars_by_symbol={"AAA": bars},
            sessions=sessions,
            exchanges={"AAA": "HOSE"},
        )
