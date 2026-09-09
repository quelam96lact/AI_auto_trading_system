"""Probe đọc trạng thái consumer 'engine' trên JetStream stream 'BARS'.

Chỉ đọc (read-only): Gọi duy nhất `js.consumer_info("BARS", "engine")`.
Không có bất kỳ tác vụ ghi, xoá, cập nhật, publish hay subscribe nào.
Dùng để giám sát xem engine có đang tiêu thụ bar thật từ NATS hay không trong phiên.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import nats

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def get_consumer_info(nats_url: str, stream: str = "BARS", consumer: str = "engine"):
    try:
        nc = await nats.connect(nats_url)
    except Exception:
        if "localhost" in nats_url:
            alt_url = nats_url.replace("localhost", "127.0.0.1")
            nc = await nats.connect(alt_url)
        elif "127.0.0.1" in nats_url:
            alt_url = nats_url.replace("127.0.0.1", "localhost")
            nc = await nats.connect(alt_url)
        else:
            raise
    try:
        js = nc.jetstream()
        info = await js.consumer_info(stream, consumer)
        return info
    finally:
        await nc.close()


def main():
    parser = argparse.ArgumentParser(description="Đọc trạng thái JetStream consumer của engine (chỉ đọc).")
    parser.add_argument("--nats-url", default=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"), help="NATS URL")
    parser.add_argument("--stream", default="BARS", help="Stream name (mặc định BARS)")
    parser.add_argument("--consumer", default="engine", help="Consumer name (mặc định engine)")
    args = parser.parse_args()

    now_vn = datetime.now(TZ_VN)
    print(f"=== TRẠNG THÁI NATS CONSUMER: stream={args.stream}, consumer={args.consumer} ===")
    print(f"Thời gian kiểm tra (VN): {now_vn.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    try:
        info = asyncio.run(get_consumer_info(args.nats_url, args.stream, args.consumer))
    except Exception as e:
        print(f"[LỖI] Không thể đọc consumer info: {e}")
        sys.exit(1)

    # In các trường cốt lõi
    num_pending = getattr(info, "num_pending", None)
    num_ack_pending = getattr(info, "num_ack_pending", None)
    num_redelivered = getattr(info, "num_redelivered", None)

    delivered = getattr(info, "delivered", None)
    delivered_seq = getattr(delivered, "stream_seq", None) if delivered else None
    delivered_consumer_seq = getattr(delivered, "consumer_seq", None) if delivered else None

    ack_floor = getattr(info, "ack_floor", None)
    ack_floor_seq = getattr(ack_floor, "stream_seq", None) if ack_floor else None
    ack_floor_consumer_seq = getattr(ack_floor, "consumer_seq", None) if ack_floor else None

    print(f"  - num_pending (bar chưa nhận): {num_pending}")
    print(f"  - num_ack_pending (đã giao, chờ ack): {num_ack_pending}")
    print(f"  - delivered.stream_seq (bar cuối đã giao): {delivered_seq}")
    print(f"  - ack_floor.stream_seq (bar cuối đã ack): {ack_floor_seq}")
    print(f"  - num_redelivered (số lần giao lại): {num_redelivered}")
    if delivered_consumer_seq is not None:
        print(f"  - delivered.consumer_seq: {delivered_consumer_seq}")
    if ack_floor_consumer_seq is not None:
        print(f"  - ack_floor.consumer_seq: {ack_floor_consumer_seq}")


if __name__ == "__main__":
    main()
