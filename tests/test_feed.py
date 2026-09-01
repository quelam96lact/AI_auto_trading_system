import asyncio
import time
from types import SimpleNamespace
from typing import ClassVar

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
    feed._init_for_test(
        FakeStream, on_raw=received.append, symbols=["VCB"], backoff_base=0.01
    )
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
    instances: ClassVar[list] = []
    fail_first_wait = True
    wait_error: ClassVar[str | None] = None  # None=khong loi; "HTTP 429..." / "boom"=loi
    alive_then_fail: ClassVar[float | None] = None  # song N giay roi chet

    def __init__(self):
        self.connect_calls = 0
        self.subscribe_calls = []
        self.disconnect_calls = 0
        self.on_data = None
        self._disconnected = asyncio.Event()
        self.created_at = time.monotonic()  # de do khoang cach giua cac lan connect
        FakeStreaming.instances.append(self)

    async def connect(self):
        self.connect_calls += 1

    async def subscribe_symbol_ohlcv(self, symbols, timeframe):
        self.subscribe_calls.append((symbols, timeframe))

    async def wait(self):
        if FakeStreaming.fail_first_wait and len(FakeStreaming.instances) == 1:
            raise RuntimeError("first connection died")
        if FakeStreaming.wait_error is not None:
            raise RuntimeError(FakeStreaming.wait_error)
        if FakeStreaming.alive_then_fail is not None:
            # Song that su mot luc roi chet — de kiem nhanh reset backoff.
            await asyncio.sleep(FakeStreaming.alive_then_fail)
            raise RuntimeError("died after being alive")
        await self._disconnected.wait()

    async def disconnect(self):
        self.disconnect_calls += 1
        self._disconnected.set()


class FakeAsyncStream:
    def __init__(self, auth):
        self.auth = auth
        self.streaming = FakeStreaming()


class FakeStreamingConnecting(FakeStreaming):
    """connect() treo (chua tra ve) — mo phong cua so SDK dang thu 5 lan."""

    def __init__(self):
        super().__init__()
        self.connect_started = asyncio.Event()

    async def connect(self):
        self.connect_calls += 1
        self.connect_started.set()
        await self._disconnected.wait()  # treo toi khi bi disconnect


class FakeAsyncStreamConnecting:
    def __init__(self, auth):
        self.auth = auth
        self.streaming = FakeStreamingConnecting()


async def fake_ensure_authenticated(cfg, storage):
    return FakeAuth()


@pytest.fixture(autouse=True)
def reset_fake_streaming():
    FakeStreaming.instances = []
    FakeStreaming.fail_first_wait = True
    FakeStreaming.wait_error = None


async def test_async_feed_reconnects_after_wait_error(monkeypatch):
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(
        cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01
    )
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
    feed = SSIFeed(
        cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01
    )
    feed.start()

    await _wait_until(lambda: len(FakeStreaming.instances) >= 1)
    current = FakeStreaming.instances[-1]
    did = await feed.restart()
    await feed.stop()

    assert did is True, "co stream dang nối thi restart phai that su disconnect"
    assert current.disconnect_calls >= 1


async def test_async_feed_restart_noop_when_never_connected(monkeypatch):
    """Brief 2026-09-01 (dot 3) Task C: khi _stream None (feed chua tung nối,
    dang trong backoff) thi restart() KHONG lam gi va tra False — de watchdog
    khong kêu 'forcing reconnect' cho mot hanh dong khong xay ra (H2)."""
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(
        cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01
    )
    # CHUA goi feed.start() -> _stream = None ngay tu dau
    did = await feed.restart()
    assert did is False, "khong co stream thi restart phai la no-op (False)"


# ============ Brief 2026-09-01 (dot 5) Task A: backoff rieng cho 429 ============


async def _measure_backoffs(
    monkeypatch, backoff_base, cap_429, error_text, n=12, reset_after_alive=60.0
):
    """Ghi lai CHINH gia tri backoff ma _run tinh ra — tuc `timeout` truyen
    vao asyncio.wait_for — thay vi do dong ho that.

    Ban dau ba test nay do khoang cach thuc te giua cac lan tao stream. Chung
    CHOP CHON tren Windows: do phan giai timer ~15,6ms lam cap 0.05 doc ra
    thanh 0.031/0.047/0.062, va hai lan chay full-suite lien tiep cho HAI test
    KHAC NHAU do (audit 01/09). Noi rong nguong chi giau van de — do dong ho
    de kiem mot phep tinh so hoc la sai dai luong ngay tu dau.

    Cach nay khong ngu mot giay nao: spy ghi timeout roi nem TimeoutError de
    vong lap chay tiep ngay, nen dung duoc so PRODUCTION that (cap 600s).
    """
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)
    FakeStreaming.fail_first_wait = False
    FakeStreaming.wait_error = error_text

    seen: list[float] = []
    real_wait_for = asyncio.wait_for

    async def spy(aw, timeout):
        seen.append(timeout)
        aw.close()  # khong await coroutine _stop.wait() -> tranh canh bao
        if len(seen) >= n:
            return  # _run se return -> vong lap dung
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", spy)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(
        cfg,
        storage=object(),
        on_message=lambda msg: None,
        backoff_base=backoff_base,
        backoff_cap_429=cap_429,
        reset_after_alive=reset_after_alive,
    )
    feed.start()
    await real_wait_for(feed._task, timeout=5.0)
    return seen


async def test_429_backoff_reaches_its_own_cap_not_60s(monkeypatch):
    """429 lien tiep -> backoff nhan doi VUOT QUA 60s va chap cap rieng 600s
    (= 10 phut, moc do duoc 01/09: im 10 phut thi noi lai duoc)."""
    seen = await _measure_backoffs(monkeypatch, 1.0, 600.0, "HTTP 429 rejected")
    assert seen[:6] == [2.0, 4.0, 8.0, 16.0, 32.0, 64.0], (
        f"phai nhan doi va VUOT 60s (khac loi thuong), thuc te: {seen}"
    )
    assert max(seen) == 600.0, f"phai chap cap 429 = 600s, thuc te: {seen}"
    assert seen[-1] == 600.0 and seen[-2] == 600.0, (
        f"cham cap roi phai giu nguyen: {seen}"
    )


async def test_non_429_backoff_keeps_old_behavior(monkeypatch):
    """Loi KHONG phai 429 -> giu nguyen tran 60s cu, khong duoc dung cap 429."""
    seen = await _measure_backoffs(
        monkeypatch, 1.0, 600.0, "timed out during handshake"
    )
    assert max(seen) == 60.0, f"loi thuong phai chap tran 60s, thuc te: {seen}"
    assert seen[:5] == [2.0, 4.0, 8.0, 16.0, 32.0], f"phai nhan doi: {seen}"


async def test_429_backoff_resets_after_successful_connect(monkeypatch):
    """Noi thanh cong va song du lau -> backoff ve base, khong nhan doi tiep."""
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStream)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)
    FakeStreaming.fail_first_wait = False
    FakeStreaming.wait_error = "HTTP 429 rejected"
    FakeStreaming.alive_then_fail = None

    seen: list[float] = []
    real_wait_for = asyncio.wait_for

    async def spy(aw, timeout):
        seen.append(timeout)
        aw.close()
        if len(seen) == 3:
            # Tu day cho ket noi song THAT SU (0.1s) roi moi chet.
            FakeStreaming.wait_error = None
            FakeStreaming.alive_then_fail = 0.1
        if len(seen) >= 5:
            return
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", spy)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(
        cfg,
        storage=object(),
        on_message=lambda msg: None,
        backoff_base=1.0,
        backoff_cap_429=600.0,
        reset_after_alive=0.02,  # ngu that 0.1s = bien 5x, khong sat do phan giai timer
    )
    feed.start()
    await real_wait_for(feed._task, timeout=5.0)

    assert seen[:3] == [2.0, 4.0, 8.0], f"ba lan 429 dau phai nhan doi: {seen}"
    assert seen[3] == 1.0, (
        f"noi thanh cong va song >= reset_after_alive -> phai ve base 1.0, thuc te: {seen}"
    )
async def test_restart_false_while_connect_in_progress(monkeypatch):
    """Task B, ca TRONG TAM: dang trong connect() chua xong (SDK dang thu
    5 lan ~30s, _stream da gan nhung CHUA noi duoc gi) -> restart() phai tra
    False, khong kêu — chi dau 'da noi' phai noi that."""
    import ssi_sdk

    monkeypatch.setattr(ssi_sdk, "AsyncStream", FakeAsyncStreamConnecting)
    monkeypatch.setattr(feed_module, "ensure_authenticated", fake_ensure_authenticated)

    cfg = SimpleNamespace(symbols=["VCB"])
    feed = SSIFeed(
        cfg, storage=object(), on_message=lambda msg: None, backoff_base=0.01
    )
    feed.start()
    await _wait_until(lambda: len(FakeStreamingConnecting.instances) >= 1, timeout=5.0)
    stream = FakeStreamingConnecting.instances[-1]
    await stream.connect_started.wait()  # chac chan connect dang treo

    did = await feed.restart()
    assert did is False, (
        "dang connect chua xong thi restart phai False (chua noi duoc gi de ngat)"
    )
    assert stream.disconnect_calls == 0, "restart False thi khong duoc disconnect"
    await feed.stop()
