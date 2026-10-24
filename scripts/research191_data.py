"""Data loader and preprocessing for Brief 191 (Foreign flow exploration).

Loads:
- stocks_daily.csv.gz (symbol,date,open,high,low,close,volume)
- foreign_flow.csv.gz (symbol,date,buy_vol,sell_vol,buy_val,sell_val,net_vol,net_val,current_room)
- exchanges.csv (symbol,exchange)
- manifest.json (sha256 checksums and metadata)

Strict constraints:
- Never query database (no trading.storage imports).
- Verify sha256 checksums against manifest.json; raise ValueError if mismatch.
- Raise ValueError if any row has date > end (never silently filter).
- join_daily leaves foreign flow fields as None when no foreign flow row exists (never fill 0).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StockDailyBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def ts(self) -> datetime:
        return datetime.combine(self.date, time.min)


@dataclass(slots=True)
class ForeignFlowRow:
    symbol: str
    date: date
    buy_vol: float
    sell_vol: float
    buy_val: float
    sell_val: float
    net_vol: float
    net_val: float
    current_room: float | None = None


@dataclass(slots=True)
class DailyRecord:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_vol: float | None = None
    sell_vol: float | None = None
    buy_val: float | None = None
    sell_val: float | None = None
    net_vol: float | None = None
    net_val: float | None = None
    current_room: float | None = None

    @property
    def ts(self) -> datetime:
        return datetime.combine(self.date, time.min)

    @property
    def gtgd(self) -> float:
        return self.close * self.volume


def compute_file_sha256(path: Path | str) -> str:
    """Compute sha256 hex digest of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def load_manifest(data_dir: Path | str) -> dict[str, Any]:
    """Load manifest.json from data_dir."""
    p = Path(data_dir) / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_expected_sha256(manifest: dict[str, Any], filename: str) -> str | None:
    """Extract expected sha256 from manifest if present."""
    entry = manifest.get(filename)
    if entry is None and "files" in manifest and isinstance(manifest["files"], dict):
        entry = manifest["files"].get(filename)
    if entry is None:
        alt = filename[:-3] if filename.endswith(".gz") else f"{filename}.gz"
        entry = manifest.get(alt)
        if entry is None and "files" in manifest and isinstance(manifest["files"], dict):
            entry = manifest["files"].get(alt)
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry.lower()
    if isinstance(entry, dict) and "sha256" in entry:
        return str(entry["sha256"]).lower()
    return None


def _verify_checksum(filepath: Path) -> None:
    """Verify sha256 checksum against manifest.json; raise if manifest missing or mismatched."""
    manifest_p = filepath.parent / "manifest.json"
    if not manifest_p.exists():
        raise FileNotFoundError(f"Missing manifest.json in {filepath.parent}")
    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    expected = _get_expected_sha256(manifest, filepath.name)
    if expected is None:
        raise ValueError(f"No sha256 checksum found in manifest.json for {filepath.name}")
    actual = compute_file_sha256(filepath)
    if actual != expected:
        raise ValueError(
            f"Checksum mismatch for {filepath.name}: expected {expected}, got {actual}"
        )


def _resolve_data_file(data_dir: Path, base_name: str) -> Path:
    gz_p = data_dir / f"{base_name}.csv.gz"
    csv_p = data_dir / f"{base_name}.csv"
    if gz_p.exists():
        return gz_p
    if csv_p.exists():
        return csv_p
    raise FileNotFoundError(f"Neither {gz_p.name} nor {csv_p.name} found in {data_dir}")


def load_stocks(
    data_dir: Path | str,
    end: date | str = "2022-12-31",
) -> dict[str, list[StockDailyBar]]:
    """Load stock daily bars, verifying sha256 and enforcing end date limit.

    Raises:
    - FileNotFoundError if manifest.json is missing.
    - ValueError if sha256 does not match manifest or is missing in manifest.
    - ValueError if any row date > end (never silently filtered).
    """
    d_dir = Path(data_dir)
    filepath = _resolve_data_file(d_dir, "stocks_daily")
    _verify_checksum(filepath)

    end_d = end if isinstance(end, date) else date.fromisoformat(str(end))

    stocks: dict[str, list[StockDailyBar]] = {}
    is_gz = filepath.name.endswith(".gz")
    open_fn = gzip.open if is_gz else open

    with open_fn(filepath, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_d = date.fromisoformat(row["date"].strip())
            if row_d > end_d:
                raise ValueError(
                    f"Row date {row_d} exceeds end limit {end_d} for symbol {row.get('symbol')}"
                )
            sym = row["symbol"].strip()
            bar = StockDailyBar(
                symbol=sym,
                date=row_d,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            if sym not in stocks:
                stocks[sym] = []
            stocks[sym].append(bar)

    for bar_list in stocks.values():
        bar_list.sort(key=lambda b: b.date)

    return stocks


def load_foreign_flow(
    data_dir: Path | str,
    end: date | str = "2022-12-31",
) -> dict[str, list[ForeignFlowRow]]:
    """Load foreign flow rows, verifying sha256 and enforcing end date limit.

    Raises:
    - FileNotFoundError if manifest.json is missing.
    - ValueError if sha256 does not match manifest or is missing in manifest.
    - ValueError if any row date > end (never silently filtered).
    """
    d_dir = Path(data_dir)
    filepath = _resolve_data_file(d_dir, "foreign_flow")
    _verify_checksum(filepath)

    end_d = end if isinstance(end, date) else date.fromisoformat(str(end))

    flows: dict[str, list[ForeignFlowRow]] = {}
    is_gz = filepath.name.endswith(".gz")
    open_fn = gzip.open if is_gz else open

    with open_fn(filepath, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_d = date.fromisoformat(row["date"].strip())
            if row_d > end_d:
                raise ValueError(
                    f"Row date {row_d} exceeds end limit {end_d} for symbol {row.get('symbol')}"
                )
            sym = row["symbol"].strip()
            room_raw = row.get("current_room")
            room_val: float | None = None
            if room_raw is not None:
                cleaned = room_raw.strip()
                if cleaned != "" and cleaned.lower() != "none":
                    room_val = float(cleaned)

            flow = ForeignFlowRow(
                symbol=sym,
                date=row_d,
                buy_vol=float(row["buy_vol"]),
                sell_vol=float(row["sell_vol"]),
                buy_val=float(row["buy_val"]),
                sell_val=float(row["sell_val"]),
                net_vol=float(row["net_vol"]),
                net_val=float(row["net_val"]),
                current_room=room_val,
            )
            if sym not in flows:
                flows[sym] = []
            flows[sym].append(flow)

    for flow_list in flows.values():
        flow_list.sort(key=lambda f_row: f_row.date)

    return flows


def load_exchanges(data_dir: Path | str) -> dict[str, str]:
    """Load exchanges.csv returning symbol -> exchange."""
    p = Path(data_dir) / "exchanges.csv"
    if not p.exists():
        return {}
    exchanges: dict[str, str] = {}
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"].strip()
            exch = row["exchange"].strip()
            exchanges[sym] = exch
    return exchanges


def join_daily(
    stocks: dict[str, list[StockDailyBar]],
    flows: dict[str, list[ForeignFlowRow]],
) -> dict[str, list[DailyRecord]]:
    """Join daily stock bars with foreign flow rows by symbol and date.

    If a stock date has no foreign flow row, all flow fields must remain None
    (NEVER filled with 0).
    """
    joined: dict[str, list[DailyRecord]] = {}

    for sym, bar_list in stocks.items():
        flow_list = flows.get(sym, [])
        flow_by_date = {f.date: f for f in flow_list}

        rec_list: list[DailyRecord] = []
        for b in bar_list:
            fl = flow_by_date.get(b.date)
            if fl is not None:
                rec = DailyRecord(
                    symbol=b.symbol,
                    date=b.date,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    buy_vol=fl.buy_vol,
                    sell_vol=fl.sell_vol,
                    buy_val=fl.buy_val,
                    sell_val=fl.sell_val,
                    net_vol=fl.net_vol,
                    net_val=fl.net_val,
                    current_room=fl.current_room,
                )
            else:
                # Date has price but NO foreign flow: fields are None, NEVER 0!
                rec = DailyRecord(
                    symbol=b.symbol,
                    date=b.date,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    buy_vol=None,
                    sell_vol=None,
                    buy_val=None,
                    sell_val=None,
                    net_vol=None,
                    net_val=None,
                    current_room=None,
                )
            rec_list.append(rec)

        rec_list.sort(key=lambda r: r.date)
        joined[sym] = rec_list

    return joined
