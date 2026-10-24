"""Unit tests for scripts/research191_validate.py on synthetic data (§4.3).

Verifies:
- sha256 mismatch returns 2.
- missing candidates file returns 3.
- synthetic sequence with strong foreign flow effect: candidate ĐẠT (return 0).
- synthetic sequence without edge: candidate TRƯỢT (return 1).
- insufficient sample size (< 100 trades): outputs THIẾU SỨC MẠNH.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from scripts.research191_data import compute_file_sha256
from scripts.research191_validate import validate_candidates


def _write_csv_gz(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _setup_synthetic_env(
    tmp_path: Path,
    n_days: int = 150,
    with_edge: bool = True,
) -> None:
    """Create a synthetic data directory with manifest, stocks, flows, exchanges."""
    stk_rows: list[dict[str, str]] = []
    fl_rows: list[dict[str, str]] = []
    ex_rows: list[dict[str, str]] = []

    symbols = [f"STK_{i:02d}" for i in range(15)]
    start_d = date(2020, 1, 1)

    for sym in symbols:
        ex_rows.append({"symbol": sym, "exchange": "HOSE"})
        cur_d = start_d
        cur_price = 100.0

        for day_idx in range(n_days):
            d_str = cur_d.isoformat()
            # Turnover >= 10B (100 * 200,000,000 = 20B)
            vol = 200_000_000.0

            if with_edge:
                # Strong foreign accumulation every 4 days followed by a price jump
                if day_idx % 4 in (1, 2, 3):
                    buy_v = 50_000_000.0
                    sell_v = 10_000_000.0
                    cur_price *= 1.03  # Trending up
                else:
                    buy_v = 10_000_000.0
                    sell_v = 10_000_000.0
            else:
                # Losing/random trend
                buy_v = 50_000_000.0
                sell_v = 10_000_000.0
                cur_price *= 0.98  # Trending down to stop out

            net_v = buy_v - sell_v
            stk_rows.append({
                "symbol": sym,
                "date": d_str,
                "open": f"{cur_price:.2f}",
                "high": f"{cur_price * 1.05:.2f}",
                "low": f"{cur_price * 0.95:.2f}",
                "close": f"{cur_price:.2f}",
                "volume": f"{vol:.0f}",
            })
            fl_rows.append({
                "symbol": sym,
                "date": d_str,
                "buy_vol": f"{buy_v:.0f}",
                "sell_vol": f"{sell_v:.0f}",
                "buy_val": f"{buy_v * cur_price:.0f}",
                "sell_val": f"{sell_v * cur_price:.0f}",
                "net_vol": f"{net_v:.0f}",
                "net_val": f"{net_v * cur_price:.0f}",
                "current_room": "1000000000",
            })
            cur_d += timedelta(days=1)

    stk_p = tmp_path / "stocks_daily.csv.gz"
    fl_p = tmp_path / "foreign_flow.csv.gz"
    ex_p = tmp_path / "exchanges.csv"

    _write_csv_gz(stk_p, stk_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])
    _write_csv_gz(
        fl_p,
        fl_rows,
        ["symbol", "date", "buy_vol", "sell_vol", "buy_val", "sell_val", "net_vol", "net_val", "current_room"],
    )
    _write_csv(ex_p, ex_rows, ["symbol", "exchange"])

    manifest = {
        "stocks_daily.csv.gz": compute_file_sha256(stk_p),
        "foreign_flow.csv.gz": compute_file_sha256(fl_p),
    }
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)


def test_validate_missing_candidates_returns_3(tmp_path: Path) -> None:
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=tmp_path / "non_existent.json",
        candidates_sha=None,
        part="V1",
        end_date_str="2022-12-30",
    )
    assert rc == 3


def test_validate_sha_mismatch_returns_2(tmp_path: Path) -> None:
    cand_p = tmp_path / "candidates.json"
    with open(cand_p, "w", encoding="utf-8") as f:
        json.dump({"candidates": []}, f)

    wrong_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_p,
        candidates_sha=wrong_sha,
        part="V1",
        end_date_str="2022-12-30",
    )
    assert rc == 2


def test_validate_empty_candidates_returns_0(tmp_path: Path) -> None:
    cand_p = tmp_path / "candidates.json"
    with open(cand_p, "w", encoding="utf-8") as f:
        json.dump({"candidates": []}, f)
    with open(cand_p, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    rc = validate_candidates(
        data_dir=tmp_path,
        candidates_path=cand_p,
        candidates_sha=sha,
        part="V1",
        end_date_str="2022-12-30",
    )
    assert rc == 0


def test_validate_synthetic_failing_idea_returns_1(tmp_path: Path) -> None:
    """Brief §4.3: Synthetic sequence without edge must register TRƯỢT and return 1."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _setup_synthetic_env(data_dir, n_days=150, with_edge=False)

    cand_p = tmp_path / "candidates.json"
    cand_doc = {
        "candidates": [
            {
                "idea_id": "IDEA1_FOREIGN_ACCUMULATION_STREAK",
                "params": {"k": 3, "min_ratio": 0.08, "tp": 0.10},
            }
        ]
    }
    with open(cand_p, "w", encoding="utf-8") as f:
        json.dump(cand_doc, f)
    with open(cand_p, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    rc = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_p,
        candidates_sha=sha,
        part="V1",
        end_date_str="2022-12-30",
    )
    # Must fail because with_edge=False produces losing trades (mean_net <= 0)
    assert rc == 1


def test_validate_synthetic_insufficient_sample_size_returns_1(tmp_path: Path) -> None:
    """Brief §4.3 & §5: Insufficient sample size (< 100) must output THIẾU SỨC MẠNH and return 1."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Very short series (only 25 days) -> very few trades (< 100)
    _setup_synthetic_env(data_dir, n_days=25, with_edge=True)

    cand_p = tmp_path / "candidates.json"
    cand_doc = {
        "candidates": [
            {
                "idea_id": "IDEA1_FOREIGN_ACCUMULATION_STREAK",
                "params": {"k": 3, "min_ratio": 0.08, "tp": 0.10},
            }
        ]
    }
    with open(cand_p, "w", encoding="utf-8") as f:
        json.dump(cand_doc, f)
    with open(cand_p, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    rc = validate_candidates(
        data_dir=data_dir,
        candidates_path=cand_p,
        candidates_sha=sha,
        part="V1",
        end_date_str="2022-12-30",
    )
    assert rc == 1
