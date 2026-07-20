import json
from datetime import datetime
from typing import Any

from trading.calendar_vn import TZ
from trading.models import IndexValue, Tick


def ci_get(d: dict, *names: str) -> Any | None:
    lower = {str(k).lower(): v for k, v in d.items()}
    for name in names:
        value = lower.get(name.lower())
        if value is not None:
            return value
    return None


def _parse_content(raw: Any) -> dict | None:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else None


def _parse_ts(content: dict) -> datetime | None:
    trading_date = ci_get(content, "TradingDate")
    raw_time = ci_get(content, "Time")
    if trading_date is None or raw_time is None:
        return None
    parsed = datetime.strptime(f"{trading_date} {raw_time}", "%d/%m/%Y %H:%M:%S")
    return parsed.replace(tzinfo=TZ)


def _parse_b(content: dict) -> Tick | None:
    symbol = ci_get(content, "Symbol")
    price = ci_get(content, "Close")
    volume = ci_get(content, "Volume")
    ts = _parse_ts(content)
    if symbol is None or price is None or ts is None:
        return None
    return Tick(str(symbol), float(price), int(float(volume or 0)), ts)


def _parse_mi(content: dict) -> IndexValue | None:
    index_id = ci_get(content, "IndexId")
    value = ci_get(content, "IndexValue")
    ts = _parse_ts(content)
    if index_id is None or value is None or ts is None:
        return None
    return IndexValue(str(index_id), ts, float(value))


def parse_message(raw: dict | str) -> Tick | IndexValue | None:
    try:
        envelope = _parse_content(raw)
        if envelope is None:
            return None
        dtype = str(ci_get(envelope, "DataType") or "").upper()
        content = _parse_content(ci_get(envelope, "Content"))
        if content is None:
            return None
        if dtype == "B":
            return _parse_b(content)
        if dtype == "MI":
            return _parse_mi(content)
        return None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
