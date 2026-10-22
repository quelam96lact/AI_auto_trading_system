"""Unit tests for scripts/research188_ledger.py."""

import csv
from pathlib import Path

import pytest

from scripts.research188_ledger import compute_idea_sha, evaluate_and_log


def dummy_rule_v1(x: int) -> int:
    return x + 1


def dummy_rule_v2(x: int) -> int:
    return x + 2


def test_evaluate_and_log_happy_path(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"
    metrics = {"n": 100, "mean_net": 0.05, "sharpe": 1.2, "p": 0.01, "cagr": 0.15, "mdd": 0.10, "calmar": 1.5}
    evaluate_and_log("IDEA_1", dummy_rule_v1, {"param": 10}, "stock", "EA", metrics, str(ledger))

    assert ledger.exists()
    with open(ledger, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        row = reader[0]
        assert row["idea_id"] == "IDEA_1"
        assert row["period"] == "EA"
        assert row["n"] == "100"
        assert row["idea_sha"] == compute_idea_sha(dummy_rule_v1)


def test_ledger_appends_and_mutation_e(tmp_path: Path):
    """Mutation (e) test: evaluate_and_log must actually append rows to the CSV file.

    If evaluate_and_log did not write a row, the file would be empty or row count wouldn't increase.
    """
    ledger = tmp_path / "ledger.csv"
    metrics = {"n": 50, "mean_net": 0.02, "sharpe": 0.8, "p": 0.04, "cagr": 0.1, "mdd": 0.05, "calmar": 2.0}

    evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": 1}, "stock", "EA", metrics, str(ledger))
    evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": 2}, "stock", "EA", metrics, str(ledger))

    with open(ledger, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 2, "Must append both rows"


def test_ledger_hard_budget_400_ea_and_mutation_f1(tmp_path: Path):
    """Mutation (f1) test: exceeding 400 EA rows must RAISE ValueError."""
    ledger = tmp_path / "ledger.csv"
    metrics = {"n": 50, "mean_net": 0.02, "sharpe": 0.8, "p": 0.04, "cagr": 0.1, "mdd": 0.05, "calmar": 2.0}

    # Simulate 400 EA rows
    for i in range(400):
        evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": i}, "stock", "EA", metrics, str(ledger))

    # The 401st EA row MUST raise ValueError
    with pytest.raises(ValueError, match="Hard budget exceeded.*400"):
        evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": 401}, "stock", "EA", metrics, str(ledger))

    # EB row should still be allowed since budget is on EA
    evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": 0}, "stock", "EB", metrics, str(ledger))


def test_ledger_sha_immutability_and_mutation_f2(tmp_path: Path):
    """Mutation (f2) test: reusing existing idea_id with different idea_sha must RAISE ValueError."""
    ledger = tmp_path / "ledger.csv"
    metrics = {"n": 50, "mean_net": 0.02, "sharpe": 0.8, "p": 0.04, "cagr": 0.1, "mdd": 0.05, "calmar": 2.0}

    evaluate_and_log("IDEA_1", dummy_rule_v1, {"p": 1}, "stock", "EA", metrics, str(ledger))

    # Changing rule to dummy_rule_v2 with SAME idea_id MUST raise ValueError!
    with pytest.raises(ValueError, match="previously logged with sha"):
        evaluate_and_log("IDEA_1", dummy_rule_v2, {"p": 1}, "stock", "EA", metrics, str(ledger))


def test_ledger_max_6_ideas(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"
    metrics = {"n": 50, "mean_net": 0.02, "sharpe": 0.8, "p": 0.04, "cagr": 0.1, "mdd": 0.05, "calmar": 2.0}

    for i in range(1, 7):
        evaluate_and_log(f"IDEA_{i}", dummy_rule_v1, {"p": 1}, "stock", "EA", metrics, str(ledger))

    # 7th idea must raise
    with pytest.raises(ValueError, match="Idea budget exceeded.*6"):
        evaluate_and_log("IDEA_7", dummy_rule_v1, {"p": 1}, "stock", "EA", metrics, str(ledger))
