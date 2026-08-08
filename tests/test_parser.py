import json
from datetime import datetime
from pathlib import Path

from trading.calendar_vn import TZ
from trading.collector.parser import ci_get, parse_interval_message, parse_message
from trading.models import IndexValue, Tick

FIXTURES = Path(__file__).parent / "fixtures"


def test_ci_get():
    assert ci_get({"LastPrice": 5}, "lastprice") == 5
    assert ci_get({"lastPrice": 5}, "LastPrice") == 5
    assert ci_get({}, "x") is None


def test_parse_all_b_fixtures():
    lines = (FIXTURES / "ssi_b_messages.jsonl").read_text(encoding="utf-8").splitlines()
    ticks = [t for t in (parse_message(json.loads(l)) for l in lines) if isinstance(t, Tick)]
    assert len(ticks) >= len(lines) * 0.9
    t = ticks[0]
    assert t.symbol and t.price > 0 and t.volume >= 0
    assert t.ts.tzinfo is not None and t.ts.utcoffset().total_seconds() == 7 * 3600


def test_parse_b_string_envelope():
    raw = (FIXTURES / "ssi_b_messages.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    tick = parse_message(raw)
    assert isinstance(tick, Tick)
    assert tick.symbol == "HPG"
    assert tick.price == 20800.0
    assert tick.volume == 100
    assert tick.ts.isoformat() == "2026-07-20T13:36:24+07:00"


def test_parse_mi_fixtures():
    p = FIXTURES / "ssi_mi_messages.jsonl"
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        import pytest

        pytest.skip("chua co fixture MI (xem findings Task 1)")
    lines = p.read_text(encoding="utf-8").splitlines()
    vals = [v for v in (parse_message(json.loads(l)) for l in lines) if isinstance(v, IndexValue)]
    assert vals and vals[0].value > 0
    assert vals[0].ts.tzinfo is not None
    assert vals[0].ts.utcoffset().total_seconds() == 7 * 3600


def test_unknown_message_returns_none():
    assert parse_message({"DataType": "X", "Content": "{}"}) is None
    assert parse_message({"garbage": True}) is None


def test_parse_interval_message_maps_fields():
    """Uses the unconfirmed stream timestamp format assumption, not a live fixture."""
    from ssi_sdk.models import IntervalMessage

    msg = IntervalMessage(
        symbol="VCB",
        interval_time="2026/07/24 14:45:00",
        trading_time="2026/07/24 14:45:03",
        open=54100,
        high=54100,
        low=54100,
        close=54100,
        volume=189100,
    )
    bar = parse_interval_message(msg)
    assert bar is not None
    assert bar.symbol == "VCB"
    assert bar.open == 54100
    assert bar.volume == 189100
    assert bar.ts == datetime(2026, 7, 24, 14, 45, tzinfo=TZ)


def test_parse_interval_message_bad_format_returns_none():
    """Bad timestamp formats should drop one message instead of crashing collection."""
    from ssi_sdk.models import IntervalMessage

    msg = IntervalMessage(
        symbol="VCB",
        interval_time="not-a-date",
        open=1,
        high=1,
        low=1,
        close=1,
        volume=1,
    )
    assert parse_interval_message(msg) is None
