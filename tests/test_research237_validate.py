"""Unit tests for scripts/research237_validate.py on synthetic data in tmp_path."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.research237_validate import validate_candidates


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
        candidates_path=tmp_path / "missing.json",
        expected_sha="abc",
        part="V1",
        first_rebalance="2020-01-31",
        last_rebalance="2020-04-30",
    )
    assert rc == 3


def test_validate_sha_mismatch_returns_2(tmp_path: Path):
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


def test_validate_empty_candidates_returns_0(tmp_path: Path):
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


def _build_synthetic_237_dataset(
    tmp_path: Path,
    low_attn_profitable: bool,
) -> tuple[Path, date, date]:
    """Build synthetic dataset with >= 250 lookback sessions before Jan 2020 rebalance."""
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
    for s in sessions:
        # Quiet symbol has lower recent turnover than 250-day average -> selected by LOWATTN.
        if s <= jan_end:
            p_quiet = 100.0
            v_quiet = 200_000_000.0 if s < date(2019, 12, 1) else 20_000_000.0
        else:
            v_quiet = 20_000_000.0 if s.day <= 10 else 200_000_000.0
            if low_attn_profitable:
                if s <= feb_end:
                    p_quiet = 115.0
                elif s <= mar_end:
                    p_quiet = 132.0
                else:
                    p_quiet = 152.0
            else:
                if s <= feb_end:
                    p_quiet = 85.0
                elif s <= mar_end:
                    p_quiet = 72.0
                else:
                    p_quiet = 60.0

        # Busy symbol has recent turnover surge so AT_20 >> 1.0, and flat price 100.0.
        v_busy = 20_000_000.0 if s < date(2019, 12, 1) else 200_000_000.0
        rows.append(["QUIET", s.isoformat(), p_quiet, p_quiet, p_quiet, p_quiet, v_quiet])
        rows.append(["BUSY", s.isoformat(), 100.0, 100.0, 100.0, 100.0, v_busy])

    stock_file = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stock_file, ["symbol", "date", "open", "high", "low", "close", "volume"], rows)

    exch_file = tmp_path / "exchanges.csv"
    _write_csv(exch_file, ["symbol", "exchange"], [["QUIET", "HOSE"], ["BUSY", "HOSE"]])

    manifest = {
        "files": {
            "sessions.csv": {"sha256": _sha256(sess_file)},
            "stocks_daily.csv.gz": {"sha256": _sha256(stock_file)},
            "exchanges.csv": {"sha256": _sha256(exch_file)},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, jan_end, apr_end


def test_validate_synthetic_passing_candidate_returns_0(tmp_path: Path):
    """Low-attention stock rises steadily while high-attention stays flat -> ĐẠT (rc=0)."""
    d_dir, start_r, end_r = _build_synthetic_237_dataset(tmp_path, low_attn_profitable=True)
    cand = [{"idea_id": "I1_LOWATTN", "params": {"S": 20, "N": 1}}]
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


def test_validate_synthetic_failing_candidate_returns_1(tmp_path: Path):
    """Low-attention stock loses steadily while high-attention stays flat -> TRƯỢT (rc=1)."""
    d_dir, start_r, end_r = _build_synthetic_237_dataset(tmp_path, low_attn_profitable=False)
    cand = [{"idea_id": "I1_LOWATTN", "params": {"S": 20, "N": 1}}]
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


def test_validate_v2_hurdle_cagr_gate(tmp_path: Path):
    """V2 fails when portfolio CAGR <= hurdle_cagr even if excess over EW passes."""
    d_dir, start_r, end_r = _build_synthetic_237_dataset(tmp_path, low_attn_profitable=True)
    cand = [{"idea_id": "I1_LOWATTN", "params": {"S": 20, "N": 1}}]
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text(json.dumps(cand), encoding="utf-8")

    rc = validate_candidates(
        data_dir=d_dir,
        candidates_path=cand_file,
        expected_sha=_sha256(cand_file),
        part="V2",
        first_rebalance=start_r,
        last_rebalance=end_r,
        hurdle_cagr=10.0,  # impossibly high hurdle
        etf_cagr=0.05,
        etf_mdd=0.30,
    )
    assert rc == 1
