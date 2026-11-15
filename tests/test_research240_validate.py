"""Unit tests for scripts/research240_validate.py on synthetic data in tmp_path."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.research240_validate import validate_candidates


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


def test_validate_240_missing_candidates_returns_3(tmp_path: Path):
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=tmp_path / "missing.json",
        expected_sha="abc",
        part="V1",
        first_rebalance="2020-01-31",
        last_rebalance="2020-04-30",
    )
    assert rc == 3


def test_validate_240_sha_mismatch_returns_2(tmp_path: Path):
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


def test_validate_240_empty_candidates_returns_0(tmp_path: Path):
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


def _build_synthetic_240_dataset(
    tmp_path: Path,
    rebound_profitable: bool,
) -> tuple[Path, date, date]:
    """Build synthetic dataset where REV drops over last S=5 sessions before each r^-.

    When rebound_profitable=True: REV rises strongly across each month and pulls back
    slightly over the final 5 sessions before the next rebalance so RET_5 < 0 again
    while monthly return stays strongly positive vs FLAT (100.0).
    When rebound_profitable=False: REV declines continuously across every month.
    """
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

    rebal_indices = [sessions.index(d) for d in (jan_end, feb_end, mar_end, apr_end)]
    prices_rev = [100.0] * len(sessions)

    if rebound_profitable:
        # Target rebalance closes: jan=95 -> feb=112 -> mar=134 -> apr=160
        targets = [95.0, 112.0, 134.0, 160.0]
        # Before jan_end: dip slightly over last 5 sessions up to jan_end so RET_5 < 0 at r^-
        r0 = rebal_indices[0]
        for k in range(5):
            prices_rev[r0 - 5 + k] = 100.0 - k
        prices_rev[r0] = targets[0]

        for m_idx in range(3):
            start_i = rebal_indices[m_idx]
            end_i = rebal_indices[m_idx + 1]
            p_start = targets[m_idx]
            p_end = targets[m_idx + 1]
            p_peak = p_end + 6.0  # ensure a gentle 5-day pullback before next rebalance
            mid_i = end_i - 6
            # Ramp smoothly from p_start to p_peak
            for i in range(start_i + 1, mid_i + 1):
                frac = (i - start_i) / max(1, mid_i - start_i)
                prices_rev[i] = p_start + frac * (p_peak - p_start)
            # Gentle pullback from p_peak to p_end so RET_5 at r^- is negative without floor lock
            for i in range(mid_i + 1, end_i + 1):
                frac = (i - mid_i) / max(1, end_i - mid_i)
                prices_rev[i] = p_peak + frac * (p_end - p_peak)
    else:
        # Continuous steady decline from jan_end (95) -> feb (82) -> mar (70) -> apr (58)
        r0 = rebal_indices[0]
        for i in range(r0 - 6, len(sessions)):
            prices_rev[i] = max(20.0, 100.0 - 0.65 * (i - (r0 - 6)))

    rows: list[list[Any]] = []
    for idx, s in enumerate(sessions):
        p_rev = prices_rev[idx]
        # Keep non-zero intraday spread so neither ceiling_lock nor floor_lock triggers
        rows.append(["REV", s.isoformat(), p_rev, p_rev * 1.02, p_rev * 0.98, p_rev, 20_000_000.0])
        rows.append(["FLAT", s.isoformat(), 100.0, 101.0, 99.0, 100.0, 20_000_000.0])

    stock_file = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stock_file, ["symbol", "date", "open", "high", "low", "close", "volume"], rows)

    exch_file = tmp_path / "exchanges.csv"
    _write_csv(exch_file, ["symbol", "exchange"], [["REV", "HOSE"], ["FLAT", "HOSE"]])

    manifest = {
        "files": {
            "sessions.csv": {"sha256": _sha256(sess_file)},
            "stocks_daily.csv.gz": {"sha256": _sha256(stock_file)},
            "exchanges.csv": {"sha256": _sha256(exch_file)},
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, jan_end, apr_end


def test_validate_240_synthetic_rebound_candidate_returns_0(tmp_path: Path):
    """Steepest-drop stock rebounds steadily each month while FLAT stays flat -> ĐẠT (rc=0)."""
    d_dir, start_r, end_r = _build_synthetic_240_dataset(tmp_path, rebound_profitable=True)
    cand = [{"idea_id": "I1_REV", "params": {"S": 5, "N": 1}}]
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


def test_validate_240_synthetic_continued_drop_candidate_returns_1(tmp_path: Path):
    """Steepest-drop stock continues dropping each month while FLAT stays flat -> TRƯỢT (rc=1)."""
    d_dir, start_r, end_r = _build_synthetic_240_dataset(tmp_path, rebound_profitable=False)
    cand = [{"idea_id": "I1_REV", "params": {"S": 5, "N": 1}}]
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


def test_validate_240_v2_hurdle_cagr_gate(tmp_path: Path):
    """V2 fails when portfolio CAGR <= hurdle_cagr."""
    d_dir, start_r, end_r = _build_synthetic_240_dataset(tmp_path, rebound_profitable=True)
    cand = [{"idea_id": "I1_REV", "params": {"S": 5, "N": 1}}]
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
