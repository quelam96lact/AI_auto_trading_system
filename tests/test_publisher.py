import json
from datetime import datetime

import nats
import pytest

from tests.conftest import TEST_NATS_URL
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.models import Bar

pytestmark = pytest.mark.integration


async def test_publish_roundtrip():
    pub = BarPublisher(TEST_NATS_URL, "BARS")
    await pub.connect()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 100.0, 102.0, 99.0, 101.0, 1000)
    await pub.publish(bar)

    nc = await nats.connect(TEST_NATS_URL)
    js = nc.jetstream()
    try:
        sub = await js.subscribe("bars.ssi.VCB", stream="BARS")
        msg = await sub.next_msg(timeout=5)
        data = json.loads(msg.data)
        assert data["symbol"] == "VCB" and data["close"] == 101.0
        assert data["ts"].endswith("+07:00")
    finally:
        # Tu DON phan test nay tao ra (tech-debt C2): purge theo DUNG subject
        # bars.ssi.VCB — khong dong cham message cua test khac; chay ca khi
        # assert fail (neu khong don, moi lan suite de lai rac trong stream BARS
        # lam isolation engine test phu thuoc vao 1 lan purge trong fixture).
        await js.purge_stream("BARS", subject="bars.ssi.VCB")
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

    nc = await nats.connect(TEST_NATS_URL)
    js = nc.jetstream()
    try:
        await js.delete_stream("BARSLIMIT")
    except Exception:
        pass
    # Dung tinh huong that: stream cu, khong gioi han gi ca.
    await js.add_stream(StreamConfig(name="BARSLIMIT", subjects=["barslimit.>"]))
    before = await js.stream_info("BARSLIMIT")
    assert before.config.max_age in (None, 0)

    pub = BarPublisher(TEST_NATS_URL, "BARSLIMIT")
    pub.subjects = ["barslimit.>"]
    await pub.connect()
    await pub.close()

    after = await js.stream_info("BARSLIMIT")
    assert after.config.max_age == STREAM_MAX_AGE_SECONDS
    assert after.config.max_bytes == STREAM_MAX_BYTES

    await js.delete_stream("BARSLIMIT")
    await nc.close()
