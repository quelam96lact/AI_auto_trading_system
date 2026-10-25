"""Unit tests for scripts/research192_validate.py on synthetic data."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.research192_validate import validate_candidates


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


def test_validate_missing_candidates_returns_3(tmp_path: Path):
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=tmp_path / "nonexistent.json",
        expected_sha="abc",
        part="V1",
        start_date="2020-01-01",
        end_date="2020-12-31",
    )
    assert rc == 3


def test_validate_sha_mismatch_returns_2(tmp_path: Path):
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]")
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_file,
        expected_sha="wrong_sha",
        part="V1",
        start_date="2020-01-01",
        end_date="2020-12-31",
    )
    assert rc == 2


def test_validate_empty_candidates_returns_0(tmp_path: Path):
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]")
    correct_sha = _sha256(cand_file)
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_file,
        expected_sha=correct_sha,
        part="V1",
        start_date="2020-01-01",
        end_date="2020-12-31",
    )
    assert rc == 0


def test_validate_synthetic_insufficient_sample_size_returns_1(tmp_path: Path):
    """Test validation detects n < 100 and outputs THIẾU SỨC MẠNH (rc=1)."""
    # Create synthetic dataset with only 30 sessions
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(30)]

    sess_rows = [[s.isoformat()] for s in sessions]
    sess_file = tmp_path / "sessions.csv"
    _write_csv(sess_file, ["date"], sess_rows)

    stock_rows = []
    for s in sessions:
        stock_rows.append(["HPG", s.isoformat(), 100.0, 105.0, 95.0, 100.0, 200_000_000.0])
    stock_file = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stock_file, ["symbol", "date", "open", "high", "low", "close", "volume"], stock_rows)

    exch_file = tmp_path / "exchanges.csv"
    _write_csv(exch_file, ["symbol", "exchange"], [["HPG", "HOSE"]])

    manifest = {
        "files": {
            "sessions.csv": {"sha256": _sha256(sess_file)},
            "stocks_daily.csv.gz": {"sha256": _sha256(stock_file)},
            "exchanges.csv": {"sha256": _sha256(exch_file)},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    cand = [{"idea_id": "I1_TOM", "params": {"k": 1, "m": 2}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand))
    cand_sha = _sha256(cand_file)

    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_file,
        expected_sha=cand_sha,
        part="V1",
        start_date="2020-01-01",
        end_date="2020-01-30",
    )
    assert rc == 1
