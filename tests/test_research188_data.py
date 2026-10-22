"""Unit tests for scripts/research188_data.py."""

import csv
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts.research188_data import load_crypto, load_exchanges, load_stocks


def _write_gz_csv(path: Path, rows: list[list[str]]) -> str:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_load_stocks_valid(tmp_path: Path):
    stocks_file = tmp_path / "stocks_daily.csv.gz"
    rows = [
        ["symbol", "date", "open", "high", "low", "close", "volume"],
        ["AAA", "2016-01-04", "10.0", "11.0", "9.5", "10.5", "1000"],
        ["AAA", "2016-01-05", "10.5", "12.0", "10.0", "11.5", "2000"],
    ]
    sha = _write_gz_csv(stocks_file, rows)

    manifest = {"files": {"stocks_daily.csv.gz": {"sha256": sha}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    stocks = load_stocks(str(tmp_path), max_date="2022-12-31")
    assert "AAA" in stocks
    assert len(stocks["AAA"]) == 2
    b1 = stocks["AAA"][0]
    assert b1.symbol == "AAA"
    assert b1.open == 10.0
    assert b1.close_time.hour == 15


def test_load_stocks_sha_mismatch(tmp_path: Path):
    stocks_file = tmp_path / "stocks_daily.csv.gz"
    rows = [
        ["symbol", "date", "open", "high", "low", "close", "volume"],
        ["AAA", "2016-01-04", "10.0", "11.0", "9.5", "10.5", "1000"],
    ]
    _write_gz_csv(stocks_file, rows)

    manifest = {"files": {"stocks_daily.csv.gz": {"sha256": "wrong_sha"}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="sha256 mismatch"):
        load_stocks(str(tmp_path), max_date="2022-12-31")


def test_load_stocks_exceeds_max_date_raises_not_silently_filters(tmp_path: Path):
    """Mutation (d) test: loader must RAISE when date > max_date, not silently filter."""
    stocks_file = tmp_path / "stocks_daily.csv.gz"
    rows = [
        ["symbol", "date", "open", "high", "low", "close", "volume"],
        ["AAA", "2016-01-04", "10.0", "11.0", "9.5", "10.5", "1000"],
        ["AAA", "2023-01-02", "15.0", "16.0", "14.5", "15.5", "5000"],  # Exceeds 2022-12-31!
    ]
    sha = _write_gz_csv(stocks_file, rows)

    manifest = {"files": {"stocks_daily.csv.gz": {"sha256": sha}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # MUST raise ValueError. If loader silently filtered rows with d > max_date, this test would fail!
    with pytest.raises(ValueError, match="exceeds max_date"):
        load_stocks(str(tmp_path), max_date="2022-12-31")


def test_load_crypto_valid_and_exceeds_max_ts(tmp_path: Path):
    crypto_file = tmp_path / "crypto_1h.csv.gz"
    rows = [
        ["symbol", "ts_utc", "open", "high", "low", "close", "volume"],
        ["BTC-USDT", "2024-04-27T10:00:00+00:00", "63000.0", "63500.0", "62800.0", "63200.0", "50.0"],
        ["BTC-USDT", "2026-09-01T00:00:00+00:00", "70000.0", "71000.0", "69500.0", "70500.0", "80.0"],
    ]
    sha = _write_gz_csv(crypto_file, rows)
    manifest = {"files": {"crypto_1h.csv.gz": {"sha256": sha}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Fails when cutoff is 2026-08-31T23:00:00+00:00
    with pytest.raises(ValueError, match="exceeds max_ts"):
        load_crypto(str(tmp_path), max_ts="2026-08-31T23:00:00+00:00")

    # Passes if max_ts covers the date
    crypto = load_crypto(str(tmp_path), max_ts="2026-09-02T00:00:00+00:00")
    assert "BTC-USDT" in crypto
    assert len(crypto["BTC-USDT"]) == 2
    assert crypto["BTC-USDT"][0].close_time.hour == 11


def test_load_exchanges(tmp_path: Path):
    exchanges_file = tmp_path / "exchanges.csv"
    exchanges_file.write_text("symbol,exchange\nAAA,HOSE\nBSR,UPCOM\nSHS,HNX\n", encoding="utf-8")
    mapping = load_exchanges(str(tmp_path))
    assert mapping == {"AAA": "HOSE", "BSR": "UPCOM", "SHS": "HNX"}
