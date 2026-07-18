"""Ghi raw message SSI thành fixtures. Chạy: python scripts/record_fixtures.py [--rest-only]
Cần env SSI_CONSUMER_ID, SSI_CONSUMER_SECRET. Phần stream cần phiên giao dịch đang mở.

Ghi chú từ Task 6 Step 1 (đọc source SDK ssi-fc-data):
- Import path xác minh: ssi_fc_data.fc_md_client.MarketDataClient, ssi_fc_data.fc_md_stream.MarketDataStream.
- MarketDataStream.start() NON-BLOCKING (SDK tự chạy daemon thread) → script phải tự sleep giữ tiến trình.
- REST methods: client.daily_ohlc(None, model.daily_ohlc(...)), client.intraday_ohlc(None, model.intraday_ohlc(...)).
- Format ngày fromDate/toDate: 'dd/MM/yyyy' (ĐÃ xác minh từ error response API), max range 30 ngày.
"""
import json
import os
import sys
import time


class _Cfg:  # đúng attrs SDK yêu cầu (xác minh từ fc_md_client.py/fc_md_stream.py)
    auth_type = "Bearer"
    consumerID = os.environ["SSI_CONSUMER_ID"]
    consumerSecret = os.environ["SSI_CONSUMER_SECRET"]
    url = "https://fc-data.ssi.com.vn/"
    stream_url = "https://fc-datahub.ssi.com.vn/"


def record_stream(seconds: int = 180, channel: str = "B:VCB-TCB-HPG") -> None:
    from ssi_fc_data.fc_md_stream import MarketDataStream  # đã xác minh Step 1
    from ssi_fc_data.fc_md_client import MarketDataClient

    out_b = open("tests/fixtures/ssi_b_messages.jsonl", "a", encoding="utf-8")
    out_mi = open("tests/fixtures/ssi_mi_messages.jsonl", "a", encoding="utf-8")

    def on_message(msg):  # SDK đã json.loads → msg là dict
        line = json.dumps(msg, ensure_ascii=False, default=str)
        dt = str(msg.get("DataType", msg.get("datatype", ""))) if isinstance(msg, dict) else ""
        (out_mi if dt.upper() == "MI" else out_b).write(line + "\n")

    def on_error(err):
        print("ERROR:", err, file=sys.stderr)

    def on_close():
        print("STREAM CLOSED", file=sys.stderr)

    cfg = _Cfg()
    stream = MarketDataStream(cfg, MarketDataClient(cfg), on_close=on_close)
    # Kênh MI: SDK không nêu format; thử "MI:VNINDEX" qua --channel và ghi kết quả vào findings
    stream.start(on_message, on_error, channel)
    # start() non-blocking (đã xác minh từ signalr/transports/_transport.py) → giữ tiến trình:
    time.sleep(seconds)


def record_rest() -> None:
    from ssi_fc_data.fc_md_client import MarketDataClient
    from ssi_fc_data.model import model

    # Format ngày XÁC MINH từ API: "dd/MM/yyyy", from <= to < now, max range 30 ngày
    client = MarketDataClient(_Cfg())
    daily = client.daily_ohlc(None, model.daily_ohlc(
        symbol="VCB", fromDate="20/06/2026", toDate="17/07/2026",
        pageIndex=1, pageSize=100, ascending=True))
    with open("tests/fixtures/ssi_daily_ohlc.json", "w", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, indent=2)
    intraday = client.intraday_ohlc(None, model.intraday_ohlc(
        symbol="VCB", fromDate="17/07/2026", toDate="17/07/2026",
        pageIndex=1, pageSize=100, ascending=True, resolution=1))
    with open("tests/fixtures/ssi_intraday_ohlc.json", "w", encoding="utf-8") as f:
        json.dump(intraday, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    channel = "B:VCB-TCB-HPG"
    if "--channel" in sys.argv:
        channel = sys.argv[sys.argv.index("--channel") + 1]
    if "--rest-only" not in sys.argv:
        record_stream(channel=channel)
    record_rest()