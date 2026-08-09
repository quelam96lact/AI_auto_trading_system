import json
from dataclasses import asdict

import nats
from nats.js.api import StreamConfig
from nats.js.errors import BadRequestError

from trading.models import Bar

# JetStream chi la DUONG TRUYEN, khong phai noi luu tru — hypertable `bars` trong
# Postgres moi la nguon su that. Khong dat gioi han thi file store cua NATS phinh
# to vo han tren dia VPS. 7 ngay du de engine chet vai ngay van bat kip duoc.
STREAM_MAX_AGE_SECONDS = 7 * 24 * 3600
STREAM_MAX_BYTES = 1024**3  # 1 GiB


class BarPublisher:
    def __init__(self, url: str, stream: str):
        self.url = url
        self.stream = stream
        self.subjects = ["bars.>"]
        self.nc = None
        self.js = None

    async def connect(self) -> None:
        self.nc = await nats.connect(self.url)
        self.js = self.nc.jetstream()
        config = StreamConfig(
            name=self.stream,
            subjects=self.subjects,
            max_age=STREAM_MAX_AGE_SECONDS,
            max_bytes=STREAM_MAX_BYTES,
        )
        try:
            await self.js.add_stream(config)
        except BadRequestError:
            # Stream da ton tai. add_stream() KHONG sua config cua stream cu, nen
            # neu chi bo qua loi nay thi cac deployment da chay tu truoc se giu
            # retention vo han mai mai. Phai update_stream().
            await self.js.update_stream(config)

    async def publish(self, bar: Bar) -> None:
        payload = asdict(bar)
        payload["ts"] = bar.ts.isoformat()
        await self.js.publish(f"bars.ssi.{bar.symbol}", json.dumps(payload).encode())

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()
