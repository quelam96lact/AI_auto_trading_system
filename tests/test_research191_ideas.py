"""Unit tests for scripts/research191_ideas.py and scripts/research191_explore.py."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from scripts.research191_data import DailyRecord
from scripts.research191_exits import Trade191
from scripts.research191_explore import (
    calculate_exit_breakdown,
    compute_bootstrap_p,
    get_parameter_neighbors,
)
from scripts.research191_ideas import (
    IDEA_GRIDS,
    IDEA_IDS,
    generate_trades_for_idea,
    rule_idea1_foreign_streak,
    rule_idea3_foreign_divergence_dip,
    rule_idea4_foreign_reversal_surge,
    rule_idea5_foreign_room_exhaustion,
)


def _make_dummy_records(n: int = 40) -> list[DailyRecord]:
    records: list[DailyRecord] = []
    base_val = 100.0
    for i in range(1, n + 1):
        # Generate monotonic dates in 2020-03 and 2020-04
        d = date(2020, 3, i) if i <= 31 else date(2020, 4, i - 31)
        val = base_val + (i * 0.5)
        # 20 billion turnover: price ~ 100, volume = 200_000_000
        rec = DailyRecord(
            symbol="HPG",
            date=d,
            open=val,
            high=val + 1.0,
            low=val - 1.0,
            close=val + 0.2,
            volume=200_000_000.0,
            buy_vol=50_000_000.0,
            sell_vol=10_000_000.0,
            buy_val=5_000_000_000.0,
            sell_val=1_000_000_000.0,
            net_vol=40_000_000.0,
            net_val=4_000_000_000.0,
            current_room=100_000_000.0,
        )
        records.append(rec)
    return records


def test_research191_grids_total_combinations():
    """Verify that the 5 pre-registered grids sum to exactly 99 EA trials."""
    assert len(IDEA_IDS) == 5
    total = 0
    for idea_id in IDEA_IDS:
        assert idea_id in IDEA_GRIDS
        grid = IDEA_GRIDS[idea_id]
        combos = 1
        for vals in grid.values():
            combos *= len(vals)
        total += combos
    assert total == 99


def test_research191_parameter_neighbors():
    grid = {
        "k": [3, 5],
        "min_ratio": [0.08, 0.15, 0.25],
        "tp": [0.10, 0.15, 0.20],
    }
    # Middle of grid
    params = {"k": 3, "min_ratio": 0.15, "tp": 0.15}
    nb = get_parameter_neighbors(grid, params)
    # k has 1 neighbor (5), min_ratio has 2 (0.08, 0.25), tp has 2 (0.10, 0.20) -> 5 neighbors
    assert len(nb) == 5

    # Corner of grid
    params_corner = {"k": 3, "min_ratio": 0.08, "tp": 0.10}
    nb_corner = get_parameter_neighbors(grid, params_corner)
    # each param has exactly 1 forward neighbor -> 3 neighbors
    assert len(nb_corner) == 3


def test_research191_calculate_exit_breakdown():
    empty_bd = calculate_exit_breakdown([])
    assert empty_bd["tp_pct"] == 0.0
    assert empty_bd["median_hold"] == 0.0

    t1 = Trade191(
        symbol="HPG",
        entry_ts=datetime(2020, 3, 5, tzinfo=UTC),
        exit_ts=datetime(2020, 3, 10, tzinfo=UTC),
        entry_price=100.0,
        exit_price=110.0,
        net_return=0.096,
        gross_return=0.10,
        market="stock",
        side="long",
        score=0.0,
        holding_sessions=3,
        exit_reason="TP",
    )
    t2 = Trade191(
        symbol="VNM",
        entry_ts=datetime(2020, 3, 5, tzinfo=UTC),
        exit_ts=datetime(2020, 3, 12, tzinfo=UTC),
        entry_price=100.0,
        exit_price=92.0,
        net_return=-0.084,
        gross_return=-0.08,
        market="stock",
        side="long",
        score=0.0,
        holding_sessions=5,
        exit_reason="SL",
    )
    bd = calculate_exit_breakdown([t1, t2])
    assert bd["tp_pct"] == 0.5
    assert bd["sl_pct"] == 0.5
    assert bd["median_hold"] == 4.0


def test_research191_compute_bootstrap_p():
    assert compute_bootstrap_p([]) == 1.0


def test_mutation_i_rules_do_not_read_foreign_flow_of_t_plus_1():
    """Audit 25/10 (phep pha i): goi luat THAT; khoi ngoai t+1 'bao truoc' khong duoc kich tin hieu o t.

    Ban cu cua test (i) chi so hai ham tu dinh nghia trong test, nen pha luat van xanh.
    """
    t = 25
    # IDEA1 k=3: cua so dung [t-2..t] co mot phien ban rong -> khong tin hieu;
    # cua so lech sang [t-1..t+1] toan mua rong -> co tin hieu.
    r1 = _make_dummy_records(35)
    r1[t - 2].net_val = -1_000_000_000.0
    r1[t + 1].net_val = 4_000_000_000.0
    assert rule_idea1_foreign_streak(r1, t, k=3, min_ratio=0.08)[0] is False
    assert rule_idea1_foreign_streak(r1, t + 1, k=3, min_ratio=0.08)[0] is True

    # IDEA4: 10 phien truoc t ban rong, phien t trung tinh, t+1 mua dot bien.
    r4 = _make_dummy_records(35)
    for i in range(t - 10, t + 1):
        r4[i].net_val = -1_000_000_000.0
    r4[t].net_val = 0.0
    r4[t + 1].net_val = 8_000_000_000.0
    assert rule_idea4_foreign_reversal_surge(r4, t, spike_ratio=0.15, m=1.5)[0] is False

    # IDEA3 / IDEA5: chi phien t+1 dat nguong khoi ngoai -> o t phai im.
    r3 = _make_dummy_records(35)
    for i in range(t - 10, t + 2):
        r3[i].close = 100.0
    r3[t].close = 90.0
    for i in range(t - 9, t + 1):
        r3[i].net_val = 0.0
    r3[t + 1].net_val = 1e12
    assert (
        rule_idea3_foreign_divergence_dip(r3, t, drop_rate=0.05, foreign_ratio=0.05)[0]
        is False
    )

    r5 = _make_dummy_records(35)
    r5[t].net_val = 0.0
    r5[t].current_room = 50_000_000.0
    r5[t + 1].net_val = 8_000_000_000.0
    assert (
        rule_idea5_foreign_room_exhaustion(
            r5, t, room_drop_pct=0.10, min_flow_ratio=0.05
        )[0]
        is False
    )


def test_mutation_j_run_exploration_refuses_existing_ledger(tmp_path, monkeypatch):
    """Audit 25/10 (phep pha j): so da co (ke ca chi co EA) thi run_exploration dung truoc khi nap
    du lieu va khong dung vao so. Ban cu chi test assert_ledger_safety, explore khong goi no khi so chi co EA.
    """
    import scripts.research191_explore as ex

    ledger = tmp_path / "trial_ledger.csv"
    content = "utc_ts,idea_id,idea_sha,market,period,params_json,n,mean_net,sharpe,p,cagr,mdd,calmar\n"
    ledger.write_text(content, encoding="utf-8")
    monkeypatch.setattr(ex, "LEDGER_PATH", str(ledger))
    with pytest.raises(SystemExit, match="đã tồn tại"):
        ex.run_exploration(data_dir=tmp_path / "khong_co")
    assert ledger.read_text(encoding="utf-8") == content


def test_research191_signal_generation_smoke():
    records = _make_dummy_records(35)
    data = {"HPG": records}
    exchanges = {"HPG": "HOSE"}

    p_start = date(2020, 3, 1)
    p_end = date(2020, 4, 30)

    # Smoke test all 5 ideas through generate_trades_for_idea
    for idea_id in IDEA_IDS:
        first_param = {k: v[0] for k, v in IDEA_GRIDS[idea_id].items()}
        trades = generate_trades_for_idea(
            idea_id, first_param, data, exchanges, p_start, p_end
        )
        assert isinstance(trades, list)
