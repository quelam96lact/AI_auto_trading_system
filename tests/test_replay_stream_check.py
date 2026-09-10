"""Tests for scripts/replay_stream_check.py (Task 3)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.js.errors import NotFoundError

from scripts.replay_stream_check import replay_stream


@pytest.mark.asyncio
async def test_replay_stream_mock(monkeypatch):
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)

    # Mock stream info
    mock_info = MagicMock()
    mock_info.state.first_seq = 1
    mock_info.state.last_seq = 4
    mock_info.state.messages = 4
    mock_js.stream_info = AsyncMock(return_value=mock_info)

    # Mock get_msg
    # 3 messages for AAA @ 09:00 with increasing volume, 1 for AAA @ 09:05
    msgs = {
        1: {
            "symbol": "AAA",
            "ts": "2026-09-10T09:00:00+07:00",
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 100,
        },
        2: {
            "symbol": "AAA",
            "ts": "2026-09-10T09:00:00+07:00",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "volume": 500,
        },
        3: {
            "symbol": "AAA",
            "ts": "2026-09-10T09:00:00+07:00",
            "open": 10.0,
            "high": 10.5,
            "low": 9.9,
            "close": 10.5,
            "volume": 1200,
        },
        4: {
            "symbol": "AAA",
            "ts": "2026-09-10T09:05:00+07:00",
            "open": 10.5,
            "high": 10.6,
            "low": 10.4,
            "close": 10.4,
            "volume": 300,
        },
    }

    async def fake_get_msg(stream, seq):
        if seq not in msgs:
            raise NotFoundError
        raw = MagicMock()
        raw.subject = f"bars.ssi.{msgs[seq]['symbol']}"
        raw.data = json.dumps(msgs[seq]).encode("utf-8")
        return raw

    mock_js.get_msg.side_effect = fake_get_msg

    monkeypatch.setattr("nats.connect", AsyncMock(return_value=mock_nc))

    res = await replay_stream(
        url="nats://127.0.0.1:4222",
        stream_name="BARS",
        from_seq=1,
        to_seq=4,
    )

    assert res["total_read"] == 4
    assert res["unique_bars"] == 2
    assert res["ratio"] == 2.0
    assert res["max_count"] == 3
    assert res["max_key"] == ("AAA", "2026-09-10T09:00:00+07:00")
    assert len(res["max_records"]) == 3
    assert res["max_records"][-1]["volume"] == 1200
