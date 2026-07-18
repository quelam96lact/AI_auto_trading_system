import threading
import time
from typing import Callable

from trading.config import Config


def build_channel(symbols: list[str]) -> str:
    return "B:" + "-".join(symbols)


class SSIFeed:
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
        self._make_stream = lambda: MarketDataStream(self._sdk_cfg, MarketDataClient(self._sdk_cfg))
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
                stream.start(self.on_raw, lambda e: dead.set(), build_channel(self.symbols))
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