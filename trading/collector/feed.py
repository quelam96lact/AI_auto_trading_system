import asyncio
import logging
import threading
import time
from collections.abc import Callable

from trading.collector.ssi_auth import ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage

logger = logging.getLogger("trading.collector.feed")


def build_channel(symbols: list[str]) -> str:
    return "B:" + "-".join(symbols)


class SSIFeedLegacy:
    def __init__(self, cfg: Config, on_raw: Callable[[dict], None]):
        from ssi_fc_data.fc_md_client import MarketDataClient  # đã xác minh Task 6
        from ssi_fc_data.fc_md_stream import MarketDataStream

        class _SdkCfg:
            auth_type = "Bearer"
            consumerID = cfg.ssi_consumer_id
            consumerSecret = cfg.ssi_consumer_secret
            url = "https://fc-data.ssi.com.vn/"
            stream_url = "https://fc-datahub.ssi.com.vn/"

        self._sdk_cfg = _SdkCfg()
        self._client_cls = MarketDataClient
        self._stream_cls = MarketDataStream
        self._make_stream = lambda: MarketDataStream(
            self._sdk_cfg, MarketDataClient(self._sdk_cfg)
        )
        self._common(on_raw, cfg.symbols, backoff_base=1.0)

    def _init_for_test(self, stream_cls, on_raw, symbols, backoff_base):
        self._make_stream = lambda: stream_cls(None, None)
        self._common(on_raw, symbols, backoff_base)

    def _common(self, on_raw, symbols, backoff_base):
        self.on_raw = on_raw
        self.symbols = symbols
        self.backoff_base = backoff_base
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Findings Task 6: MarketDataStream.start() của SDK thật NON-BLOCKING
        # (daemon thread chạy ws.run_forever, return ngay) → không thể dựa vào
        # việc start() trả về để biết kết nối chết. Thay vào đó chờ trên event
        # "dead" được set bởi on_error (hub "Error") và on_close (socket đóng/
        # lỗi, qua attr _on_close của MarketDataStream — xác minh từ
        # signalr/transports/_transport.py + base_transport.py).
        backoff = self.backoff_base
        while not self._stop.is_set():
            dead = threading.Event()
            try:
                stream = self._make_stream()
                prev_close = getattr(stream, "_on_close", None)
                if prev_close is not None or hasattr(stream, "_on_close"):

                    def _closed(prev=prev_close, dead=dead):
                        dead.set()
                        if callable(prev):
                            prev()

                    stream._on_close = _closed
                stream.start(
                    self.on_raw,
                    lambda e, dead=dead: dead.set(),
                    build_channel(self.symbols),
                )
            except Exception:
                dead.set()
            if self._stop.is_set():
                return
            # SDK thật: start() trả ngay → chờ tới khi kết nối chết hoặc bị stop.
            # (FakeStream trong test block trong start() tới khi "chết" — cũng khớp luồng này.)
            connected_at = time.monotonic()
            while not (dead.is_set() or self._stop.is_set()):
                self._stop.wait(0.05)
            if self._stop.is_set():
                return
            # Kết nối đã chết → reconnect với backoff (1s, 2s, 4s… tối đa 60s);
            # kết nối sống đủ lâu (≥60s) trước khi chết thì reset về base.
            alive = time.monotonic() - connected_at
            backoff = self.backoff_base if alive >= 60.0 else min(backoff * 2, 60.0)
            if self._stop.wait(backoff):
                return


class SSIFeed:
    """Streaming feed using ssi-sdk AsyncStream.

    AsyncStream is native asyncio, so this implementation plugs directly into the
    collector loop instead of bridging through a thread and queue.
    """

    def __init__(
        self,
        cfg: Config,
        storage: Storage,
        on_message: Callable,
        backoff_base: float = 1.0,
        backoff_cap_429: float = 600.0,
        reset_after_alive: float = 60.0,
    ):
        self._cfg = cfg
        self._storage = storage
        self._on_message = on_message
        self._backoff_base = backoff_base
        # Brief 2026-09-01 (dot 5) Task A: backoff RIÊNG cho 429. Mốc duy nhất
        # có bằng chứng: im 10 phút thì nối được (đo 01/09) -> cap 600s = 10
        # phút, đủ để rate-limit hết hạn. Lỗi khác giữ nguyên trần 60s cũ.
        # reset_after_alive: kết nối sống đủ lâu (>= giây này) trước khi chết
        # thì reset backoff về base (quy tắc cũ 60s giữ nguyên).
        self._backoff_cap_429 = backoff_cap_429
        self._reset_after_alive = reset_after_alive
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._auth = None
        self._stream = None
        # Brief dot 5 Task B: "đã tạo object stream" != "đã connect() xong".
        # Cờ này chỉ set SAU connect() trả về — restart() dựa vào nó để chỉ
        # trả True khi thật sự đã nối (chỉ dấu nói thật).
        self._connected = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            await self._stream.streaming.disconnect()
        if self._task is not None:
            await self._task

    async def restart(self) -> bool:
        """Brief 2026-09-01 (dot 5) Task B: tra True CHI KHI that su da
        connect() xong (dang co ket noi de ngat). _stream duoc gan TRUOC
        connect() (feed.py:154) nen khong the dung no lam chi dau — trong
        suot cua so SDK dang thu 5 lan (~30s), _stream da khac None nhung chua
        noi duoc gi. Dung self._connected (set sau connect thanh cong)."""
        if self._connected and self._stream is not None:
            await self._stream.streaming.disconnect()
            return True
        return False

    @staticmethod
    def _is_rate_limited(e: Exception | None) -> bool:
        """Brief dot 5 Task A, quyet dinh 1: nhan biet 429 bang chuoi text
        'HTTP 429' trong message cua exception. SDK nem WebSocketError CHUNG
        cho moi loi connect (websocket_client.py:111-113) — khong co kieu
        exception hay status_code rieng cho 429 o duong connect (RateLimitError
        ton tai nhung connect() khong dung no). Day la DIEM MONG MANH da biet:
        neu SDK doi message se vo. Kiem tra ca status_code phong khi SDK bo sung."""
        if e is None:
            return False
        if getattr(e, "status_code", None) == 429:
            return True
        return "HTTP 429" in str(e)

    async def _run(self) -> None:
        backoff = self._backoff_base
        while not self._stop.is_set():
            connected_at = None
            last_error = None
            try:
                from ssi_sdk import AsyncStream
                from ssi_sdk.enums import Timeframe

                self._auth = await ensure_authenticated(self._cfg, self._storage)
                self._stream = AsyncStream(self._auth)
                self._stream.streaming.on_data = self._on_message
                await self._stream.streaming.connect()
                # Chi set sau connect() thanh cong — Task B
                self._connected = True
                await self._stream.streaming.subscribe_symbol_ohlcv(
                    self._cfg.symbols, Timeframe.MINUTE_5
                )
                # Index streaming (VNINDEX/VN30): điều tra thật 2026-08-07 kết luận
                # KHÔNG có kênh WS/REST nào trong ssi-sdk trả giá trị index real-time
                # (subscribe_index/subscribe_symbol -> rỗng; subscribe_symbol_ohlcv trên
                # mã index -> server hiểu nhầm thành board, trả nến cổ phiếu thành viên;
                # get_index_summary REST -> chỉ EOD hôm trước). Xem PLAN_INDEX_STREAMING.md.
                # KHÔNG map IndexValue cho tới khi có nguồn dữ liệu thật khác.
                connected_at = asyncio.get_event_loop().time()
                await self._stream.streaming.wait()
            except Exception as e:
                last_error = e
                logger.warning("SSIFeed connection error: %s", e)
            finally:
                if self._auth is not None:
                    await self._auth.close()
                self._auth = None
                self._connected = False
                self._stream = None
            if self._stop.is_set():
                return
            alive = (
                (asyncio.get_event_loop().time() - connected_at) if connected_at else 0
            )
            if alive >= self._reset_after_alive:
                # Nối thành công và sống đủ lâu -> reset về base (quy tắc cũ)
                backoff = self._backoff_base
            elif self._is_rate_limited(last_error):
                # 429: rate-limit do ta gay ra — backoff phai du dai de het
                # han (10 phut la moc co so). Khong dung trung 60s nua.
                backoff = min(backoff * 2, self._backoff_cap_429)
            else:
                # Lỗi khác: giữ nguyên hành vi cũ, trần 60s
                backoff = min(backoff * 2, 60.0)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                return
            except TimeoutError:
                pass
