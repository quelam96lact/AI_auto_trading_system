"""Data loader for Brief 188 (multi-timeframe anti-overfitting research).

Strictly reads data from files in the specified directory.
Verifies sha256 against manifest.json.
Enforces hard maximum date/ts cutoffs (raises on violation; NEVER silently filters).
Does NOT query DB or import trading.storage.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(slots=True, frozen=True)
class Bar:
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_manifest_entry(data_path: Path, filename: str) -> None:
    manifest_path = data_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {data_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    file_info = manifest.get("files", {}).get(filename)
    if not file_info:
        raise ValueError(f"File {filename} not listed in manifest.json")

    expected_sha = file_info.get("sha256")
    actual_sha = _compute_sha256(data_path / filename)
    if actual_sha != expected_sha:
        raise ValueError(
            f"sha256 mismatch for {filename}: expected {expected_sha}, got {actual_sha}"
        )


def load_stocks(
    data_dir: str = "data/research188/explore",
    max_date: str = "2022-12-31",
) -> dict[str, list[Bar]]:
    """Load daily stock bars from stocks_daily.csv.gz with integrity and date checks.

    Raises:
        FileNotFoundError: if files are missing.
        ValueError: if sha256 does not match manifest or row date > max_date.
    """
    data_path = Path(data_dir)
    filename = "stocks_daily.csv.gz"
    file_path = data_path / filename
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} not found")

    _verify_manifest_entry(data_path, filename)

    stocks: dict[str, list[Bar]] = {}
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Expected: symbol,date,open,high,low,close,volume
        if header != ["symbol", "date", "open", "high", "low", "close", "volume"]:
            raise ValueError(f"Unexpected header in {filename}: {header}")

        for row in reader:
            sym, d_str, o, h, l, c, v = row
            if d_str > max_date:
                raise ValueError(
                    f"Stock row date {d_str} exceeds max_date {max_date} for {sym}"
                )

            y, m, d = int(d_str[:4]), int(d_str[5:7]), int(d_str[8:10])
            ts = datetime(y, m, d, 9, 0, tzinfo=TZ_VN)
            ct = datetime(y, m, d, 15, 0, tzinfo=TZ_VN)
            bar = Bar(
                symbol=sym,
                ts=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                close_time=ct,
            )
            if sym not in stocks:
                stocks[sym] = []
            stocks[sym].append(bar)

    for bar_list in stocks.values():
        bar_list.sort(key=lambda b: b.ts)

    return stocks


def load_crypto(
    data_dir: str = "data/research188/explore",
    max_ts: str = "2026-08-31T23:00:00+00:00",
) -> dict[str, list[Bar]]:
    """Load 1h crypto bars from crypto_1h.csv.gz with integrity and timestamp checks.

    Raises:
        FileNotFoundError: if files are missing.
        ValueError: if sha256 does not match manifest or row ts > max_ts.
    """
    data_path = Path(data_dir)
    filename = "crypto_1h.csv.gz"
    file_path = data_path / filename
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} not found")

    _verify_manifest_entry(data_path, filename)

    max_dt = datetime.fromisoformat(max_ts)
    if max_dt.tzinfo is None:
        max_dt = max_dt.replace(tzinfo=UTC)

    crypto: dict[str, list[Bar]] = {}
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Expected: symbol,ts_utc,open,high,low,close,volume
        if header != ["symbol", "ts_utc", "open", "high", "low", "close", "volume"]:
            raise ValueError(f"Unexpected header in {filename}: {header}")

        for row in reader:
            sym, ts_str, o, h, l, c, v = row
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)

            if ts > max_dt:
                raise ValueError(
                    f"Crypto row timestamp {ts_str} exceeds max_ts {max_ts} for {sym}"
                )

            # 1h bar closes 1 hour after open
            ct = datetime.fromtimestamp(ts.timestamp() + 3600, tz=UTC)
            bar = Bar(
                symbol=sym,
                ts=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                close_time=ct,
            )
            if sym not in crypto:
                crypto[sym] = []
            crypto[sym].append(bar)

    for bar_list in crypto.values():
        bar_list.sort(key=lambda b: b.ts)

    return crypto


def load_exchanges(data_dir: str = "data/research188/explore") -> dict[str, str]:
    """Load exchange mapping for stocks: symbol -> HOSE/HNX/UPCOM."""
    file_path = Path(data_dir) / "exchanges.csv"
    if not file_path.exists():
        return {}

    mapping: dict[str, str] = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                mapping[row[0].strip()] = row[1].strip()
    return mapping
