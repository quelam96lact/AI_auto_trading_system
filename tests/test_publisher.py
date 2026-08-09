import json
from datetime import datetime

import nats
import pytest

from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.models import Bar

pytestmark = pytest.mark.integration


async def test_publish_roundtrip():
    pub = BarPublisher("nats://127.0.0.1:4222", "BARS")
    await pub.connect()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 100.0, 102.0, 99.0, 101.0, 1000)
    await pub.publish(bar)

    nc = await nats.connect("nats://127.0.0.1:4222")
    js = nc.jetstream()
    sub = await js.subscribe("bars.ssi.VCB", stream="BARS")
    msg = await sub.next_msg(timeout=5)
    data = json.loads(msg.data)
    assert data["symbol"] == "VCB" and data["close"] == 101.0
    assert data["ts"].endswith("+07:00")
    await nc.close()
    await pub.close()