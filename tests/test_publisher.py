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

async def test_connect_applies_retention_limits_to_existing_unlimited_stream():
    """Stream da ton tai voi config khong gioi han phai duoc CAP NHAT.

    Bug goc: connect() bat BadRequestError roi bo qua, nen mot stream cu (tao
    truoc khi co limit) giu nguyen retention vo han — file store NATS phinh to
    khong gioi han tren dia VPS. add_stream() mot minh KHONG bao gio sua duoc
    stream da ton tai.
    """
    from nats.js.api import StreamConfig

    from trading.bus.publisher import STREAM_MAX_AGE_SECONDS, STREAM_MAX_BYTES

    nc = await nats.connect("nats://127.0.0.1:4222")
    js = nc.jetstream()
    try:
        await js.delete_stream("BARSLIMIT")
    except Exception:
        pass
    # Dung tinh huong that: stream cu, khong gioi han gi ca.
    await js.add_stream(StreamConfig(name="BARSLIMIT", subjects=["barslimit.>"]))
    before = await js.stream_info("BARSLIMIT")
    assert before.config.max_age in (None, 0)

    pub = BarPublisher("nats://127.0.0.1:4222", "BARSLIMIT")
    pub.subjects = ["barslimit.>"]
    await pub.connect()
    await pub.close()

    after = await js.stream_info("BARSLIMIT")
    assert after.config.max_age == STREAM_MAX_AGE_SECONDS
    assert after.config.max_bytes == STREAM_MAX_BYTES

    await js.delete_stream("BARSLIMIT")
    await nc.close()
