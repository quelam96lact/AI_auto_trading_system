"""Unit tests for scripts/research188_ideas.py and scripts/research188_explore.py."""

from datetime import UTC, datetime

from scripts import research188_explore, research188_ideas
from scripts.research188_core import Bar


def _make_dummy_bar(ts_str: str, close: float) -> Bar:
    ts = datetime.fromisoformat(ts_str)
    return Bar("TEST", ts, close, close + 1, close - 1, close, 1000.0, ts)


def test_research188_ideas_smoke():
    """Verify all 6 rules in research188_ideas can run on dummy data without errors."""
    bars = [
        _make_dummy_bar("2020-01-01T09:00:00+07:00", 10.0),
        _make_dummy_bar("2020-01-02T09:00:00+07:00", 10.5),
        _make_dummy_bar("2020-01-03T09:00:00+07:00", 11.0),
    ]

    p_start = datetime(2020, 1, 1, tzinfo=UTC)
    p_end = datetime(2020, 1, 10, tzinfo=UTC)

    # Idea 1
    t1 = research188_ideas.rule_idea1_stk_wk_trend_pullback(
        bars, bars, [bars[0], bars[1], bars[2]], "HOSE",
        {"w_period": 10, "rsi_len": 5, "rsi_thresh": 30}, p_start, p_end
    )
    assert isinstance(t1, list)

    # Idea 2
    t2 = research188_ideas.rule_idea2_stk_wk_vol_breakout(
        bars, bars, [bars[0], bars[1], bars[2]], "HOSE",
        {"vol_thresh": 0.05, "n_days": 15, "exit_days": 5}, p_start, p_end
    )
    assert isinstance(t2, list)

    # Idea 3
    t3 = research188_ideas.rule_idea3_stk_mn_trend_wk_mom(
        bars, bars, bars, [bars[0], bars[1], bars[2]], [bars[0], bars[1], bars[2]], "HOSE",
        {"m_len": 6, "k_weeks": 2, "mom_thresh": 0.02}, p_start, p_end
    )
    assert isinstance(t3, list)

    # Idea 4
    t4 = research188_ideas.rule_idea4_cry_1d_trend_4h_pullback(
        bars, bars, bars, [bars[0], bars[1], bars[2]], [bars[0], bars[1], bars[2]],
        {"d_period": 15, "rsi_low": 30, "exit_len": 10}, p_start, p_end
    )
    assert isinstance(t4, list)

    # Idea 5
    t5 = research188_ideas.rule_idea5_cry_4h_vol_breakout(
        bars, bars, bars, [bars[0], bars[1], bars[2]], [bars[0], bars[1], bars[2]],
        {"trend_len": 10, "bb_len": 15, "bb_std": 2.0}, p_start, p_end
    )
    assert isinstance(t5, list)

    # Idea 6
    t6 = research188_ideas.rule_idea6_stk_wk_donchian_channel(
        bars, bars, [bars[0], bars[1], bars[2]], "HOSE",
        {"n_weeks": 10, "exit_weeks": 5}, p_start, p_end
    )
    assert isinstance(t6, list)


def test_research188_explore_neighbors():
    """Verify grid neighbor helper from research188_explore."""
    grid = {"a": [1, 2, 3], "b": [10, 20]}
    neighbors = research188_explore.get_grid_neighbors({"a": 2, "b": 10}, grid)
    assert len(neighbors) == 3
    assert {"a": 1, "b": 10} in neighbors
    assert {"a": 3, "b": 10} in neighbors
    assert {"a": 2, "b": 20} in neighbors
