import asyncio
import time
from types import SimpleNamespace

import pytest

from trading.collector import feed as feed_module
from trading.collector.feed import SSIFeed, SSIFeedLegacy, build_channel


def test_build_channel():
    assert build_channel(["VCB", "TCB", "HPG"]) == "B:VCB-TCB-HPG"


def test_feed_reconnects_on_error(monkeypatch):
    starts = []

    class FakeStream:
        def __init__(self, cfg, client):
            pass
        def start(self, on_message, on_error, channel):
            starts.append(channel)
            if len(starts) == 1:
                on_error("boom")  # lần đầu lỗi → feed phải thử lại
            else:
                on_message({"DataType": "B", "Content": "{}"})
                time.sleep(10)  # giữ "kết nối" sống

    received = []
    feed = SSIFeedLegacy.__new__(SSIFeedLegacy)
    feed._init_for_test(FakeStream, on_raw=received.append,
                        symbols=["VCB"], backoff_base=0.01)
    feed.start()
    time.sleep(0.5)
    feed.stop()
    assert len(starts) >= 2 and received


async def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


class FakeAuth:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeStreaming:
    instances = []
    fail_first_wait = True

    def __init__(self):
        self.connect_calls = 0
        self.subscribe_calls = []
        self.disconnect_calls = 0
        self.on_data = None
        self._disconnected = asyncio.Event()
        FakeStreaming.instances.append(self)

    async def connect(self):
        self.connect_calls += 1

    async def subscribe_symbol_ohlcv(self, symbols, timeframe):
        self.subscribe_calls.append((symbols, timeframe))

    async def wait(self):
        if FakeStreaming.fail_first_wait and len(FakeStreaming.instances) == 1:
            raise RuntimeError("first connection died")
        await self._disconnected.wait()

    async def disconnect(self):
        self.disconnect_calls += 1
        self._disconnected.set()


class FakeAsyncStream:
    def __init__(self, auth):
        self.auth = auth
        self.streaming = FakeStreaming()


async def fake_ensure_authenticated(cfg, storage):
    return FakeAuth()


@pytest.fixture(autouse=True)
def reset_fake_streaming():
    FakeStreaming.instances = []
    FakeStreaming.fail_first_wait = True


async def test_async_feed_reconnects_after_wait_error(monkeypatch):
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01)
    feed.start()

    await _wait_until(lambda: len(FakeStreaming.instances) >= 2)
    await feed.stop()

    assert sum(s.connect_calls for s in FakeStreaming.instances) >= 2


async def test_async_feed_restart_disconnects_current_stream(monkeypatch):
    import ssi_sdk

    FakeStreaming.fail_first_wait = False
    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01)
    feed.start()

    await _wait_until(lambda: len(FakeStreaming.instances) >= 1)
    current = FakeStreaming.instances[-1]
    await feed.restart()
    await feed.stop()

    assert current.disconnect_calls >= 1
