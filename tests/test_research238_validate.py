"""Unit tests for scripts/research238_validate.py on synthetic data in tmp_path."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.research238_validate import validate_candidates


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


def test_validate_238_missing_candidates_returns_3(tmp_path: Path):
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=tmp_path / "missing.json",
        expected_sha="abc",
        part="V1",
        first_rebalance="2020-01-31",
        last_rebalance="2020-04-30",
    )
    assert rc == 3


def test_validate_238_sha_mismatch_returns_2(tmp_path: Path):
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]", encoding="utf-8")
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_file,
        expected_sha="wrong_sha",
        part="V1",
        first_rebalance="2020-01-31",
        last_rebalance="2020-04-30",
    )
    assert rc == 2


def test_validate_238_empty_candidates_returns_0(tmp_path: Path):
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]", encoding="utf-8")
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_file,
        expected_sha=_sha256(cand_file),
        part="V1",
        first_rebalance="2020-01-31",
        last_rebalance="2020-04-30",
    )
    assert rc == 0


def _build_synthetic_238_dataset(
    tmp_path: Path,
    high_attn_profitable: bool,
) -> tuple[Path, date, date]:
    """Build synthetic dataset where BUSY has high AT_20 (> 1.0) and QUIET has low AT_20 (< 1.0)."""
    curr = date(2018, 12, 1)
    end = date(2020, 4, 30)
    sessions: list[date] = []
    while curr <= end:
        if curr.weekday() < 5:
            sessions.append(curr)
        curr += timedelta(days=1)

    sess_file = tmp_path / "sessions.csv"
    _write_csv(sess_file, ["date"], [[s.isoformat()] for s in sessions])

    jan_end = max(s for s in sessions if s.year == 2020 and s.month == 1)
    feb_end = max(s for s in sessions if s.year == 2020 and s.month == 2)
    mar_end = max(s for s in sessions if s.year == 2020 and s.month == 3)
    apr_end = max(s for s in sessions if s.year == 2020 and s.month == 4)

    rows: list[list[Any]] = []
    for idx, s in enumerate(sessions):
        # BUSY: low older volume -> surging recent volume => AT_20 > 1.0 at all rebalances.
        v_busy = 20_000_000.0 if s < date(2019, 12, 1) else (200_000_000.0 + idx * 1_000_000.0)
        if s <= jan_end:
            p_busy = 100.0
        elif high_attn_profitable:
            if s <= feb_end:
                p_busy = 115.0
            elif s <= mar_end:
                p_busy = 132.0
            else:
                p_busy = 152.0
        else:
            if s <= feb_end:
                p_busy = 85.0
            elif s <= mar_end:
                p_busy = 72.0
            else:
                p_busy = 60.0

        # QUIET: high older volume -> lower recent volume => AT_20 < 1.0, flat price 100.0.
        v_quiet = 200_000_000.0 if s < date(2019, 12, 1) else 20_000_000.0
        rows.append(["BUSY", s.isoformat(), p_busy, p_busy, p_busy, p_busy, v_busy])
        rows.append(["QUIET", s.isoformat(), 100.0, 100.0, 100.0, 100.0, v_quiet])

    stock_file = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stock_file, ["symbol", "date", "open", "high", "low", "close", "volume"], rows)

    exch_file = tmp_path / "exchanges.csv"
    _write_csv(exch_file, ["symbol", "exchange"], [["BUSY", "HOSE"], ["QUIET", "HOSE"]])

    manifest = {
        "files": {
            "sessions.csv": {"sha256": _sha256(sess_file)},
            "stocks_daily.csv.gz": {"sha256": _sha256(stock_file)},
            "exchanges.csv": {"sha256": _sha256(exch_file)},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, jan_end, apr_end


def test_validate_238_synthetic_passing_candidate_returns_0(tmp_path: Path):
    """High-attention stock rises steadily while low-attention stays flat -> ĐẠT (rc=0)."""
    d_dir, start_r, end_r = _build_synthetic_238_dataset(tmp_path, high_attn_profitable=True)
    cand = [{"idea_id": "I1_HIGHATTN", "params": {"S": 20, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand), encoding="utf-8")

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=_sha256(cand_file),
        part="V1",
        first_rebalance=start_r,
        last_rebalance=end_r,
        etf_cagr=0.05,
        etf_mdd=0.30,
    )
    assert rc == 0


def test_validate_238_synthetic_failing_candidate_returns_1(tmp_path: Path):
    """High-attention stock loses steadily while low-attention stays flat -> TRƯỢT (rc=1)."""
    d_dir, start_r, end_r = _build_synthetic_238_dataset(tmp_path, high_attn_profitable=False)
    cand = [{"idea_id": "I1_HIGHATTN", "params": {"S": 20, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand), encoding="utf-8")

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=_sha256(cand_file),
        part="V1",
        first_rebalance=start_r,
        last_rebalance=end_r,
        etf_cagr=0.05,
        etf_mdd=0.30,
    )
    assert rc == 1


def test_validate_238_v2_hurdle_cagr_gate(tmp_path: Path):
    """V2 fails when portfolio CAGR <= hurdle_cagr."""
    d_dir, start_r, end_r = _build_synthetic_238_dataset(tmp_path, high_attn_profitable=True)
    cand = [{"idea_id": "I1_HIGHATTN", "params": {"S": 20, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand), encoding="utf-8")

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=_sha256(cand_file),
        part="V2",
        first_rebalance=start_r,
        last_rebalance=end_r,
        hurdle_cagr=10.0,
        etf_cagr=0.05,
        etf_mdd=0.30,
    )
    assert rc == 1
