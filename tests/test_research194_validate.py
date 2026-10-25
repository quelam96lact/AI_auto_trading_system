"""Tests for scripts/research194_validate.py CLI and gate validation (§5 & §6)."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.research194_validate import validate_candidates


def _create_mock_env(
    tmp_path: Path,
    trend_up: bool = True,
) -> tuple[Path, Path, str, date, date]:
    """Create minimal mock explore/validate directory with manifest.json."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    start_d = date(2020, 1, 6)
    sessions = [
        start_d + timedelta(days=i)
        for i in range(110)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]

    r0 = date(2020, 3, 31)
    r1 = date(2020, 4, 30)

    # sessions.csv
    sess_path = data_dir / "sessions.csv"
    with open(sess_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date"])
        for s in sessions:
            writer.writerow([s.isoformat()])

    # exchanges.csv
    exch_path = data_dir / "exchanges.csv"
    with open(exch_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "exchange"])
        writer.writerow(["SYM_A", "HOSE"])
        writer.writerow(["SYM_B", "HOSE"])

    # stocks_daily.csv.gz
    stocks_path = data_dir / "stocks_daily.csv.gz"
    with gzip.open(stocks_path, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "date", "open", "high", "low", "close", "volume"])

        for i, s in enumerate(sessions):
            if trend_up:
                o = 50.0 + (i // 5) * 5.0
                c = o
                if i in (60, 61):
                    o, c = 70.0, 70.0
                elif i == 62:
                    o, c = 70.0, 115.0
                elif i == 63:
                    o, c = 100.0, 100.0
                elif i == 64:
                    o, c = 100.0, 50.0
                elif i == 65:
                    o, c = 120.0, 120.0
                elif i >= 66:
                    o, c = 70.0, 70.0
                writer.writerow(
                    ["SYM_A", s.isoformat(), o, max(o, c), min(o, c), c, 20_000_000]
                )
            else:
                p_a = 100.0 - (i // 5) * 5.0  # Downtrend
                writer.writerow(
                    ["SYM_A", s.isoformat(), p_a, p_a, p_a, p_a, 20_000_000]
                )

            # SYM_B: flat benchmark stock
            p_b = 100.0
            writer.writerow(["SYM_B", s.isoformat(), p_b, p_b, p_b, p_b, 20_000_000])

    # manifest.json
    manifest = {
        "files": {
            "stocks_daily.csv.gz": {
                "sha256": hashlib.sha256(stocks_path.read_bytes()).hexdigest()
            },
            "sessions.csv": {
                "sha256": hashlib.sha256(sess_path.read_bytes()).hexdigest()
            },
            "exchanges.csv": {
                "sha256": hashlib.sha256(exch_path.read_bytes()).hexdigest()
            },
        }
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    cand_path = tmp_path / "candidates.json"
    candidates = [
        {
            "idea_id": "I1_WKMA_RSI_ATR",
            "params": {"n": 2, "theta": 40.0, "k": 2.0},
        }
    ]
    cand_path.write_text(json.dumps(candidates), encoding="utf-8")
    cand_sha = hashlib.sha256(cand_path.read_bytes()).hexdigest()

    return data_dir, cand_path, cand_sha, r0, r1


def test_validate_missing_candidates_returns_3(tmp_path: Path):
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=tmp_path / "non_existent.json",
        expected_sha="deadbeef",
        part="V1",
        first_rebalance=date(2020, 1, 1),
        last_rebalance=date(2020, 3, 1),
    )
    assert rc == 3


def test_validate_sha_mismatch_returns_2(tmp_path: Path):
    cand_p = tmp_path / "candidates.json"
    cand_p.write_text("[]", encoding="utf-8")
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_p,
        expected_sha="wrong_sha256",
        part="V1",
        first_rebalance=date(2020, 1, 1),
        last_rebalance=date(2020, 3, 1),
    )
    assert rc == 2


def test_validate_v2_missing_hurdle_cagr_returns_3(tmp_path: Path):
    cand_p = tmp_path / "candidates.json"
    cand_p.write_text("[]", encoding="utf-8")
    cand_sha = hashlib.sha256(cand_p.read_bytes()).hexdigest()
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_p,
        expected_sha=cand_sha,
        part="V2",
        first_rebalance=date(2020, 1, 1),
        last_rebalance=date(2020, 3, 1),
        hurdle_cagr=None,
    )
    assert rc == 3


def test_validate_empty_candidates_returns_0(tmp_path: Path):
    cand_p = tmp_path / "candidates.json"
    cand_p.write_text("[]", encoding="utf-8")
    cand_sha = hashlib.sha256(cand_p.read_bytes()).hexdigest()
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_p,
        expected_sha=cand_sha,
        part="V1",
        first_rebalance=date(2020, 1, 1),
        last_rebalance=date(2020, 3, 1),
    )
    assert rc == 0


def test_validate_synthetic_passing_candidate_returns_0(tmp_path: Path):
    data_dir, cand_path, cand_sha, r0, r1 = _create_mock_env(tmp_path, trend_up=True)
    rc = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_path,
        expected_sha=cand_sha,
        part="V1",
        first_rebalance=r0,
        last_rebalance=r1,
        min_closed_trades=1,
    )
    assert rc == 0


def test_validate_synthetic_failing_candidate_returns_1(tmp_path: Path):
    data_dir, cand_path, cand_sha, r0, r1 = _create_mock_env(tmp_path, trend_up=False)
    # Downtrend mock data will fail mean_X > 0 and Calmar
    rc = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_path,
        expected_sha=cand_sha,
        part="V1",
        first_rebalance=r0,
        last_rebalance=r1,
        min_closed_trades=1,
    )
    assert rc == 1
