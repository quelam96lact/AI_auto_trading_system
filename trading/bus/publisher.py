import json
from dataclasses import asdict

import nats
from nats.js.api import StreamConfig
from nats.js.errors import BadRequestError

from trading.models import Bar


class BarPublisher:
    def __init__(self, url: str, stream: str):
        self.url = url
        self.stream = stream
        self.nc = None
        self.js = None

    async def connect(self) -> None:
        self.nc = await nats.connect(self.url)
        self.js = self.nc.jetstream()
        try:
            await self.js.add_stream(StreamConfig(name=self.stream, subjects=["bars.>"]))
        except BadRequestError:
            pass  # stream đã tồn tại với config tương đương

    async def publish(self, bar: Bar) -> None:
        payload = asdict(bar)
        payload["ts"] = bar.ts.isoformat()
        await self.js.publish(f"bars.ssi.{bar.symbol}", json.dumps(payload).encode())

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()