import json
from datetime import datetime
from typing import Any

from trading.calendar_vn import TZ
from trading.models import Bar, IndexValue, Tick


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


def parse_interval_message(msg) -> Bar | None:
    """Map ssi-sdk IntervalMessage to Bar.

    Định dạng "%Y/%m/%d %H:%M:%S" đã được xác nhận với dữ liệu stream thật.
    LƯU Ý QUAN TRỌNG: Một IntervalMessage từ SSI là SNAPSHOT của khung đang hình
    thành, KHÔNG phải sự kiện đóng nến. SSI phát lại cùng một khung trung bình 7 lần
    (cao nhất 30 lần), volume là luỹ kế trong khung, open bất biến, close là giá
    tạm thời. Không được publish trực tiếp Bar này ra NATS — phải đưa qua BarLatch
    để chỉ phát khi khung đã đóng.
    """
    try:
        ts = datetime.strptime(msg.interval_time, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ)
        return Bar(
            msg.symbol,
            ts,
            float(msg.open),
            float(msg.high),
            float(msg.low),
            float(msg.close),
            int(msg.volume),
        )
    except (TypeError, ValueError, AttributeError):
        return None
