"""Tests for scripts/research195_validate.py (§5 & §6).

Uses synthetic test environments in tmp_path.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.research195_validate import validate_candidates


def _create_mock_environment(
    tmp_path: Path,
    scenario: str = "bullish",
) -> tuple[Path, Path, str, date, date]:
    """Create minimal mock validate environment with manifest.json and mock data.

    scenario: 'bullish' (candidate passes with low min_trades) or 'bearish' (candidate fails).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 70 sessions
    start_d = date(2026, 1, 5)
    sessions: list[date] = []
    curr = start_d
    while len(sessions) < 70:
        if curr.weekday() < 5:
            sessions.append(curr)
        curr += timedelta(days=1)

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
            # 60 warm up bars with price around 20_000, volume 100_000 (turnover 2B > 1e9)
            if scenario == "bullish":
                p_a = 20_000.0 + i * 50.0
                p_b = 20_000.0
            else:
                # Bearish: declining prices
                p_a = max(1000.0, 30_000.0 - i * 300.0)
                p_b = max(1000.0, 30_000.0 - i * 300.0)

            writer.writerow(["SYM_A", s.isoformat(), p_a, p_a * 1.01, p_a * 0.99, p_a, 100_000.0])
            writer.writerow(["SYM_B", s.isoformat(), p_b, p_b * 1.01, p_b * 0.99, p_b, 100_000.0])

    # bars_5m.csv.gz
    bars_path = data_dir / "bars_5m.csv.gz"
    with gzip.open(bars_path, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "ts", "open", "high", "low", "close", "volume"])

        for i, s in enumerate(sessions):
            # On session 62..65, generate 5m bars for hours 09, 10, 11, 13, 14
            for h in (9, 10, 11, 13, 14):
                for m in (0, 30):
                    ts_str = f"{s.isoformat()}T{h:02d}:{m:02d}"
                    if scenario == "bullish":
                        # Dip at session 61 bar 28 to pull RSI < 30, then bounce at bar 29 to pull RSI >= 30
                        # SYM_A dips then surges
                        val_a = 20_000.0 + i * 50.0
                        if i == 61 and h == 10 and m == 0:
                            val_a = 18_000.0  # dip
                        elif i == 61 and h == 11:
                            val_a = 21_000.0  # cross up
                        elif i >= 62:
                            val_a = 25_000.0  # gain
                        val_b = 20_000.0  # EW flat
                    else:
                        val_a = max(1000.0, 30_000.0 - i * 300.0)
                        val_b = max(1000.0, 30_000.0 - i * 300.0)

                    writer.writerow(["SYM_A", ts_str, val_a, val_a * 1.01, val_a * 0.99, val_a, 10_000.0])
                    writer.writerow(["SYM_B", ts_str, val_b, val_b * 1.01, val_b * 0.99, val_b, 10_000.0])

    # manifest.json
    def compute_sha(p: Path) -> str:
        h = hashlib.sha256()
        with open(p, "rb") as f_in:
            while chunk := f_in.read(65536):
                h.update(chunk)
        return h.hexdigest()

    manifest = {
        "files": {
            "stocks_daily.csv.gz": {"sha256": compute_sha(stocks_path)},
            "bars_5m.csv.gz": {"sha256": compute_sha(bars_path)},
            "sessions.csv": {"sha256": compute_sha(sess_path)},
            "exchanges.csv": {"sha256": compute_sha(exch_path)},
        }
    }
    with open(data_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    # candidates.json
    cand_path = tmp_path / "candidates.json"
    cand_obj = {
        "candidates": [
            {
                "idea_id": "I1_DMA_RSI1H_ATR",
                "n": 50,
                "theta": 30.0,
                "k": 2.0,
            }
        ]
    }
    cand_str = json.dumps(cand_obj)
    cand_path.write_text(cand_str, encoding="utf-8")
    cand_sha = hashlib.sha256(cand_str.encode("utf-8")).hexdigest()

    return data_dir, cand_path, cand_sha, sessions[60], sessions[-1]


def test_validator_returns_2_on_wrong_sha(tmp_path: Path):
    data_dir, cand_path, _cand_sha, first_s, last_s = _create_mock_environment(tmp_path)
    res = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_path,
        expected_sha="wrong_sha256_hash",
        part="V1",
        first_session=first_s,
        last_session=last_s,
    )
    assert res == 2


def test_validator_returns_3_on_missing_file(tmp_path: Path):
    data_dir, _cand_path, cand_sha, first_s, last_s = _create_mock_environment(tmp_path)
    res = validate_candidates(
        data_dir=data_dir,
        candidates_path=tmp_path / "non_existent_candidates.json",
        expected_sha=cand_sha,
        part="V1",
        first_session=first_s,
        last_session=last_s,
    )
    assert res == 3


def test_validator_returns_0_when_empty_candidates(tmp_path: Path):
    data_dir, cand_path, _cand_sha, first_s, last_s = _create_mock_environment(tmp_path)
    empty_cand = json.dumps({"candidates": []})
    cand_path.write_text(empty_cand, encoding="utf-8")
    expected_sha = hashlib.sha256(empty_cand.encode("utf-8")).hexdigest()

    res = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_path,
        expected_sha=expected_sha,
        part="V1",
        first_session=first_s,
        last_session=last_s,
    )
    assert res == 0


def test_validator_fails_bearish_scenario(tmp_path: Path):
    data_dir, cand_path, cand_sha, first_s, last_s = _create_mock_environment(tmp_path, scenario="bearish")
    res = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_path,
        expected_sha=cand_sha,
        part="V1",
        first_session=first_s,
        last_session=last_s,
        min_trades=1,
    )
    # Bearish has negative returns / no entries -> fails criteria -> returns 1
    assert res == 1
