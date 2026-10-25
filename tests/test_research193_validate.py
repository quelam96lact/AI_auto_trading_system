"""Unit tests for scripts/research193_validate.py on synthetic data."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.research193_validate import validate_candidates


def _write_csv_gz(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        f.writelines(",".join(str(x) for x in r) + "\n" for r in rows)


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
        first_rebalance="2020-01-31",
        last_rebalance="2020-12-31",
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
        first_rebalance="2020-01-31",
        last_rebalance="2020-12-31",
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
        first_rebalance="2020-01-31",
        last_rebalance="2020-12-31",
    )
    assert rc == 0


def _build_synthetic_dataset(
    tmp_path: Path,
    low_vol_profitable: bool,
) -> tuple[Path, date, date]:
    """Build synthetic dataset with 3 months of trading sessions."""
    # Month ends: Jan 31, Feb 28, Mar 31 2020
    # Sessions: Jan 2 to Mar 31 2020 (weekdays)
    curr = date(2020, 1, 2)
    end = date(2020, 3, 31)
    sessions: list[date] = []
    while curr <= end:
        if curr.weekday() < 5:
            sessions.append(curr)
        curr += timedelta(days=1)

    sess_file = tmp_path / "sessions.csv"
    _write_csv(sess_file, ["date"], [[s.isoformat()] for s in sessions])

    # 2 symbols: LOW (low vol), HIGH (high vol)
    # Both have 200M volume @ 100 VND = 20B turnover (liquid)
    rows = []
    jan_end = date(2020, 1, 31)
    feb_end = date(2020, 2, 28)
    mar_end = date(2020, 3, 31)

    for i, s in enumerate(sessions):
        # LOW vol price
        if low_vol_profitable:
            # Steady steady rise: 100 in Jan, 115 in Feb, 130 in Mar
            if s <= jan_end:
                p_low = 100.0
            elif s <= feb_end:
                p_low = 115.0
            else:
                p_low = 130.0
        else:
            # Steady steady drop: 100 in Jan, 80 in Feb, 60 in Mar
            if s <= jan_end:
                p_low = 100.0
            elif s <= feb_end:
                p_low = 80.0
            else:
                p_low = 60.0

        # HIGH vol price: wild swings around 100
        p_high = 100.0 + (10.0 if (i % 2 == 1) else -10.0)

        rows.append(["LOW", s.isoformat(), p_low, p_low, p_low, p_low, 20_000_000.0])
        rows.append(["HIGH", s.isoformat(), p_high, p_high, p_high, p_high, 20_000_000.0])

    stock_file = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stock_file, ["symbol", "date", "open", "high", "low", "close", "volume"], rows)

    exch_file = tmp_path / "exchanges.csv"
    _write_csv(exch_file, ["symbol", "exchange"], [["LOW", "HOSE"], ["HIGH", "HOSE"]])

    manifest = {
        "files": {
            "sessions.csv": {"sha256": _sha256(sess_file)},
            "stocks_daily.csv.gz": {"sha256": _sha256(stock_file)},
            "exchanges.csv": {"sha256": _sha256(exch_file)},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    return tmp_path, jan_end, mar_end


def test_validate_synthetic_passing_candidate_returns_0(tmp_path: Path):
    """Synthetic dataset where low-vol stock has steady profit: candidate passes (rc=0)."""
    d_dir, start_r, end_r = _build_synthetic_dataset(tmp_path, low_vol_profitable=True)

    cand = [{"idea_id": "I1_LOWVOL", "params": {"L": 2, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand))
    cand_sha = _sha256(cand_file)

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=cand_sha,
        part="V1",
        first_rebalance=start_r,
        last_rebalance=end_r,
    )
    assert rc == 0


def test_validate_synthetic_failing_candidate_returns_1(tmp_path: Path):
    """Synthetic dataset where low-vol stock loses money: candidate fails (rc=1)."""
    d_dir, start_r, end_r = _build_synthetic_dataset(tmp_path, low_vol_profitable=False)

    cand = [{"idea_id": "I1_LOWVOL", "params": {"L": 2, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand))
    cand_sha = _sha256(cand_file)

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=cand_sha,
        part="V1",
        first_rebalance=start_r,
        last_rebalance=end_r,
    )
    assert rc == 1
