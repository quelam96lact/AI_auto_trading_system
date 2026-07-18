import time

from trading.collector.feed import SSIFeed, build_channel


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
    feed = SSIFeed.__new__(SSIFeed)
    feed._init_for_test(FakeStream, on_raw=received.append,
                        symbols=["VCB"], backoff_base=0.01)
    feed.start()
    time.sleep(0.5)
    feed.stop()
    assert len(starts) >= 2 and received