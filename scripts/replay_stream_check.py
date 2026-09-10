"""Kiểm tra và phân tích message thô từ JetStream (Task 3 - Brief 26).

RÀNG BUỘC AN TOÀN:
- CHỈ ĐỌC: Chỉ sử dụng js.stream_info() và js.get_msg().
- TUYỆT ĐỐI KHÔNG: create_consumer, delete_consumer, purge_stream, delete_stream,
  publish, subscribe, v.v.

Mục đích:
- Đo lường số message NATS thực tế so với số khung bar duy nhất (symbol, ts).
- Phát hiện tình trạng snapshot chưa đóng bị phát nhiều lần trong cùng 1 khung.
- In phân bố số lần phát và chi tiết OHLCV tiến hóa theo seq của khung bị phát nhiều nhất.

CLI:
    uv run python scripts/replay_stream_check.py [--stream BARS] [--url nats://127.0.0.1:4222] [--from-seq N] [--to-seq M] [--date YYYY-MM-DD]
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict

import nats
from nats.js.errors import NotFoundError

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def _fetch_seq(js, stream_name: str, seq: int) -> dict | None:
    try:
        raw_msg = await js.get_msg(stream_name, seq=seq)
    except NotFoundError:
        return None
    except Exception:
        return None

    try:
        data = json.loads(raw_msg.data.decode("utf-8"))
    except Exception:
        return None

    return {
        "seq": seq,
        "subject": raw_msg.subject,
        "symbol": data.get("symbol"),
        "ts": data.get("ts", ""),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "close": data.get("close"),
        "volume": data.get("volume"),
    }


async def replay_stream(
    url: str = "nats://127.0.0.1:4222",
    stream_name: str = "BARS",
    from_seq: int | None = None,
    to_seq: int | None = None,
    filter_date: str | None = None,
) -> dict:
    """Đọc và phân tích message từ JetStream chỉ bằng get_msg."""
    nc = await nats.connect(url, connect_timeout=5)
    js = nc.jetstream()

    try:
        info = await js.stream_info(stream_name)
        first_seq = info.state.first_seq
        last_seq = info.state.last_seq
        num_messages = info.state.messages

        start_seq = from_seq if from_seq is not None else first_seq
        end_seq = to_seq if to_seq is not None else last_seq

        print(f"Stream: {stream_name}")
        print(f"  first_seq: {first_seq}, last_seq: {last_seq}, total_messages: {num_messages}")
        print(f"  Phạm vi quét: seq {start_seq} -> {end_seq}")

        messages = []
        bars_by_key = defaultdict(list)

        # Batch fetches for speed
        batch_size = 50
        seqs = list(range(start_seq, end_seq + 1))
        for i in range(0, len(seqs), batch_size):
            chunk = seqs[i : i + batch_size]
            tasks = [_fetch_seq(js, stream_name, s) for s in chunk]
            results = await asyncio.gather(*tasks)
            for record in results:
                if not record:
                    continue
                if filter_date and not record["ts"].startswith(filter_date):
                    continue
                messages.append(record)
                key = (record["symbol"], record["ts"])
                bars_by_key[key].append(record)

        total_read = len(messages)
        unique_bars = len(bars_by_key)
        ratio = (total_read / unique_bars) if unique_bars > 0 else 0.0

        # Phân bố số lần phát
        dist = defaultdict(int)
        max_count = 0
        max_key = None
        for k, list_msgs in bars_by_key.items():
            cnt = len(list_msgs)
            dist[cnt] += 1
            if cnt > max_count:
                max_count = cnt
                max_key = k

        return {
            "first_seq": first_seq,
            "last_seq": last_seq,
            "start_seq": start_seq,
            "end_seq": end_seq,
            "total_read": total_read,
            "unique_bars": unique_bars,
            "ratio": ratio,
            "dist": dict(sorted(dist.items())),
            "max_key": max_key,
            "max_count": max_count,
            "max_records": bars_by_key[max_key] if max_key else [],
            "messages": messages,
        }
    finally:
        await nc.close()


def print_report(res: dict) -> None:
    print("=" * 80)
    print("KẾT QUẢ KIỂM TRA MESSAGE THÔ JETSTREAM (TASK 3)")
    print("=" * 80)
    print(f"Tổng message đọc được: {res['total_read']}")
    print(f"Số bar duy nhất (symbol, ts): {res['unique_bars']}")
    print(f"Tỷ lệ message / bar: {res['ratio']:.2f}")

    if res["unique_bars"] == 0:
        print("Không có message nào trong phạm vi quét.")
        print("=" * 80)
        return

    print("\nPhân bố số lần phát:")
    for count, bar_cnt in res["dist"].items():
        print(f"  Phát {count:>3} lần : {bar_cnt:>4} bar")

    if res["max_key"]:
        sym, ts = res["max_key"]
        print(f"\nKhung bị phát nhiều nhất: {sym} @ {ts} ({res['max_count']} message)")
        print(f"{'seq':>8} | {'open':>8} | {'high':>8} | {'low':>8} | {'close':>8} | {'volume':>10}")
        print("-" * 60)
        records = res["max_records"]
        for r in records:
            print(
                f"{r['seq']:>8} | {r['open']:>8} | {r['high']:>8} | {r['low']:>8} | {r['close']:>8} | {r['volume']:>10,}"
            )

    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra message thô từ JetStream")
    parser.add_argument("--url", default="nats://127.0.0.1:4222", help="NATS URL")
    parser.add_argument("--stream", default="BARS", help="Stream name")
    parser.add_argument("--from-seq", type=int, default=None, help="Start sequence")
    parser.add_argument("--to-seq", type=int, default=None, help="End sequence")
    parser.add_argument("--date", default=None, help="Lọc theo ngày (YYYY-MM-DD)")
    args = parser.parse_args()

    try:
        res = asyncio.run(
            replay_stream(
                url=args.url,
                stream_name=args.stream,
                from_seq=args.from_seq,
                to_seq=args.to_seq,
                filter_date=args.date,
            )
        )
    except Exception as e:
        print(f"LỖI kết nối hoặc đọc stream: {e}", file=sys.stderr)
        return 2

    print_report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
