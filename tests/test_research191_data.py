"""Unit tests for scripts/research191_data.py.

Verifies:
- Checksum validation against manifest.json (raises on mismatch).
- Row date validation against end parameter (raises on > end, never silently filters).
- join_daily leaves foreign flow fields as None when no flow row exists (never fill 0).
- Loading exchanges and manifest.
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.research191_data import (
    compute_file_sha256,
    join_daily,
    load_exchanges,
    load_foreign_flow,
    load_manifest,
    load_stocks,
)


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


def test_load_manifest(tmp_path: Path) -> None:
    m_data = {"files": {"stocks_daily.csv.gz": {"sha256": "abc123"}}}
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(m_data, f)

    res = load_manifest(tmp_path)
    assert res == m_data


def test_load_stocks_valid_checksum_and_sorting(tmp_path: Path) -> None:
    stock_rows = [
        {"symbol": "HPG", "date": "2020-03-02", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
        {"symbol": "HPG", "date": "2020-03-01", "open": "9.5", "high": "10.0", "low": "9.4", "close": "9.9", "volume": "800000"},
    ]
    stk_path = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stk_path, stock_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])
    sha = compute_file_sha256(stk_path)

    manifest = {"stocks_daily.csv.gz": sha}
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    stocks = load_stocks(tmp_path, end="2022-12-31")
    assert "HPG" in stocks
    assert len(stocks["HPG"]) == 2
    # Check sorting by date
    assert stocks["HPG"][0].date == date(2020, 3, 1)
    assert stocks["HPG"][1].date == date(2020, 3, 2)
    assert stocks["HPG"][0].close == 9.9


def test_load_stocks_checksum_mismatch_raises(tmp_path: Path) -> None:
    stock_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
    ]
    stk_path = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stk_path, stock_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])

    # Put incorrect sha in manifest
    manifest = {"stocks_daily.csv.gz": "0000000000000000000000000000000000000000000000000000000000000000"}
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    with pytest.raises(ValueError, match="Checksum mismatch"):
        load_stocks(tmp_path, end="2022-12-31")


def test_load_stocks_missing_manifest_raises(tmp_path: Path) -> None:
    """Brief §3.1 note: Must raise FileNotFoundError when manifest.json is missing."""
    stock_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
    ]
    stk_path = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stk_path, stock_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])

    with pytest.raises(FileNotFoundError, match="Missing manifest.json"):
        load_stocks(tmp_path, end="2022-12-31")


def test_load_foreign_flow_missing_manifest_raises(tmp_path: Path) -> None:
    """Brief §3.1 note: Must raise FileNotFoundError when manifest.json is missing."""
    flow_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "buy_vol": "100", "sell_vol": "50", "buy_val": "1000", "sell_val": "500", "net_vol": "50", "net_val": "500", "current_room": "12345"},
    ]
    flow_path = tmp_path / "foreign_flow.csv.gz"
    _write_csv_gz(
        flow_path,
        flow_rows,
        ["symbol", "date", "buy_vol", "sell_vol", "buy_val", "sell_val", "net_vol", "net_val", "current_room"],
    )

    with pytest.raises(FileNotFoundError, match="Missing manifest.json"):
        load_foreign_flow(tmp_path, end="2022-12-31")


def test_load_stocks_missing_sha_in_manifest_raises(tmp_path: Path) -> None:
    stock_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
    ]
    stk_path = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stk_path, stock_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])

    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"other_file.csv": "123"}, f)

    with pytest.raises(ValueError, match="No sha256 checksum found"):
        load_stocks(tmp_path, end="2022-12-31")


def test_load_stocks_exceeds_end_date_raises(tmp_path: Path) -> None:
    """Brief §3.1 & Mutation (g): Row with date > end must raise ValueError, not silently filter."""
    stock_rows = [
        {"symbol": "HPG", "date": "2022-12-30", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
        {"symbol": "HPG", "date": "2023-01-05", "open": "11.0", "high": "11.5", "low": "10.8", "close": "11.2", "volume": "1200000"},
    ]
    stk_path = tmp_path / "stocks_daily.csv.gz"
    _write_csv_gz(stk_path, stock_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])
    sha = compute_file_sha256(stk_path)
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"stocks_daily.csv.gz": sha}, f)

    with pytest.raises(ValueError, match="exceeds end limit"):
        load_stocks(tmp_path, end="2022-12-31")


def test_load_foreign_flow_and_end_date_validation(tmp_path: Path) -> None:
    flow_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "buy_vol": "100", "sell_vol": "50", "buy_val": "1000", "sell_val": "500", "net_vol": "50", "net_val": "500", "current_room": "12345"},
        {"symbol": "HPG", "date": "2023-01-02", "buy_vol": "200", "sell_vol": "100", "buy_val": "2000", "sell_val": "1000", "net_vol": "100", "net_val": "1000", "current_room": "None"},
    ]
    flow_path = tmp_path / "foreign_flow.csv.gz"
    _write_csv_gz(
        flow_path,
        flow_rows,
        ["symbol", "date", "buy_vol", "sell_vol", "buy_val", "sell_val", "net_vol", "net_val", "current_room"],
    )
    sha = compute_file_sha256(flow_path)
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"foreign_flow.csv.gz": sha}, f)

    with pytest.raises(ValueError, match="exceeds end limit"):
        load_foreign_flow(tmp_path, end="2022-12-31")


def test_load_exchanges(tmp_path: Path) -> None:
    rows = [
        {"symbol": "HPG", "exchange": "HOSE"},
        {"symbol": "SHS", "exchange": "HNX"},
    ]
    _write_csv(tmp_path / "exchanges.csv", rows, ["symbol", "exchange"])
    exchanges = load_exchanges(tmp_path)
    assert exchanges == {"HPG": "HOSE", "SHS": "HNX"}


def test_join_daily_missing_flow_must_be_none(tmp_path: Path) -> None:
    """Brief §3.1 & Mutation (f): Missing foreign flow on a stock date must be None, NOT filled with 0."""
    stk_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "open": "10.0", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"},
        {"symbol": "HPG", "date": "2020-03-02", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.6", "volume": "1100000"},
    ]
    flow_rows = [
        {"symbol": "HPG", "date": "2020-03-01", "buy_vol": "100", "sell_vol": "50", "buy_val": "1000", "sell_val": "500", "net_vol": "50", "net_val": "500", "current_room": "12345"},
        # 2020-03-02 has NO foreign flow row!
    ]

    stk_p = tmp_path / "stocks_daily.csv.gz"
    fl_p = tmp_path / "foreign_flow.csv.gz"
    _write_csv_gz(stk_p, stk_rows, ["symbol", "date", "open", "high", "low", "close", "volume"])
    _write_csv_gz(
        fl_p,
        flow_rows,
        ["symbol", "date", "buy_vol", "sell_vol", "buy_val", "sell_val", "net_vol", "net_val", "current_room"],
    )

    manifest = {
        "stocks_daily.csv.gz": compute_file_sha256(stk_p),
        "foreign_flow.csv.gz": compute_file_sha256(fl_p),
    }
    with open(tmp_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    stocks = load_stocks(tmp_path, end="2022-12-31")
    flows = load_foreign_flow(tmp_path, end="2022-12-31")
    joined = join_daily(stocks, flows)

    assert len(joined["HPG"]) == 2
    rec1 = joined["HPG"][0]
    rec2 = joined["HPG"][1]

    # Day 1: matched flow
    assert rec1.net_val == 500.0
    assert rec1.net_vol == 50.0
    assert rec1.current_room == 12345.0

    # Day 2: missing flow -> MUST BE None, NEVER 0!
    assert rec2.net_val is None
    assert rec2.net_vol is None
    assert rec2.buy_vol is None
    assert rec2.sell_vol is None
    assert rec2.buy_val is None
    assert rec2.sell_val is None
    assert rec2.current_room is None
