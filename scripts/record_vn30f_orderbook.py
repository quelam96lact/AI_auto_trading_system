"""Máy ghi dữ liệu sổ lệnh và dòng lệnh VN30F1M thời gian thực (Brief 87).

Chức năng:
1. Xác thực bằng trading.collector.ssi_auth.ensure_authenticated(cfg, storage)
   (đọc và cập nhật token trong bảng ssi_auth_state của DB - đồng nhất với collector).
2. Kết nối WebSocket qua ssi_sdk.AsyncStream(auth) và subscribe hợp đồng phái sinh.
3. Ghi nguyên văn mọi tin QUOTE / TRADE kèm timestamp nhận recv_ts vào:
   data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz.
4. Tự dừng khi tới mốc --until HH:MM (giờ VN) hoặc khi nhận tín hiệu dừng (Ctrl+C).
5. In báo cáo thống kê: số tin mỗi loại, dung lượng file, khoảng lặng dài nhất
   và danh sách các khoảng lặng > 10s trong giờ giao dịch (bỏ qua nghỉ trưa).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import gzip
import io
import json
import os
import pathlib
import signal
import sys
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

# Ensure repo root is in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading.calendar_vn import TZ
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import load_config
from trading.storage.db import Storage

# Các mốc giờ phiên giao dịch phái sinh Việt Nam
MORNING_START = dt_time(9, 0, 0)
MORNING_END = dt_time(11, 30, 0)
AFTERNOON_START = dt_time(13, 0, 0)
AFTERNOON_END = dt_time(14, 45, 0)


def classify_message(raw_msg: dict[str, Any]) -> str:
    """Phân loại tin nhận từ WebSocket SSI thành QUOTE, TRADE hoặc OTHER."""
    if not isinstance(raw_msg, dict):
        return "OTHER"

    msg_type = str(raw_msg.get("type", ""))
    if "QUOTE" in msg_type or "bid_prices" in raw_msg or "ask_prices" in raw_msg:
        return "QUOTE"
    if "TRADE" in msg_type or (
        "side" in raw_msg and ("price" in raw_msg or "total_volume" in raw_msg)
    ):
        return "TRADE"

    return "OTHER"


def get_orderbook_filepath(
    base_dir: Path | str,
    symbol: str,
    dt: datetime,
) -> Path:
    """Trả về đường dẫn file lưu trữ: data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz.

    Tạo sẵn thư mục cha nếu chưa tồn tại.
    """
    base = Path(base_dir)
    date_str = dt.astimezone(TZ).strftime("%Y-%m-%d")
    target_dir = base / symbol
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{date_str}.jsonl.gz"


def compute_market_silence_seconds(t1: datetime, t2: datetime) -> float:
    """Tính số giây khoảng lặng giữa hai mốc thời gian trong giờ giao dịch.

    Bỏ qua hoàn toàn khoảng nghỉ trưa (11:30:00 -> 13:00:00) và ngoài giờ phiên.
    Chỉ tính thời gian thực sự nằm trong phiên sáng [09:00, 11:30] và chiều [13:00, 14:45].
    """
    t1_vn = t1.astimezone(TZ)
    t2_vn = t2.astimezone(TZ)
    if t2_vn <= t1_vn:
        return 0.0

    # Nếu khác ngày lịch, không tính vượt ngày
    if t1_vn.date() != t2_vn.date():
        return 0.0

    d = t1_vn.date()
    m_s = datetime.combine(d, MORNING_START, tzinfo=TZ)
    m_e = datetime.combine(d, MORNING_END, tzinfo=TZ)
    a_s = datetime.combine(d, AFTERNOON_START, tzinfo=TZ)
    a_e = datetime.combine(d, AFTERNOON_END, tzinfo=TZ)

    # Giao cắt với phiên sáng [09:00, 11:30]
    overlap_m_start = max(t1_vn, m_s)
    overlap_m_end = min(t2_vn, m_e)
    sec_m = (
        max(0.0, (overlap_m_end - overlap_m_start).total_seconds())
        if overlap_m_end > overlap_m_start
        else 0.0
    )

    # Giao cắt với phiên chiều [13:00, 14:45]
    overlap_a_start = max(t1_vn, a_s)
    overlap_a_end = min(t2_vn, a_e)
    sec_a = (
        max(0.0, (overlap_a_end - overlap_a_start).total_seconds())
        if overlap_a_end > overlap_a_start
        else 0.0
    )

    return sec_m + sec_a


def detect_silence_gaps(
    timestamps: list[datetime],
    min_gap_seconds: float = 10.0,
) -> tuple[float, list[tuple[datetime, datetime, float]], int]:
    """Dò khoảng lặng giữa các tin liên tiếp trong giờ giao dịch.

    Parameters:
        timestamps: Danh sách các mốc thời gian nhận tin (đã sắp xếp tăng dần).
        min_gap_seconds: Ngưỡng tối thiểu (giây) để ghi nhận khoảng lặng (mặc định 10.0s).

    Returns:
        (max_gap_seconds, list_of_gaps, total_messages_considered)
        Mỗi phần tử trong list_of_gaps là: (t1, t2, gap_seconds)
    """
    total_messages = len(timestamps)
    if total_messages < 2:
        return 0.0, [], total_messages

    max_gap = 0.0
    long_gaps: list[tuple[datetime, datetime, float]] = []

    for i in range(len(timestamps) - 1):
        t1 = timestamps[i]
        t2 = timestamps[i + 1]
        gap_sec = compute_market_silence_seconds(t1, t2)
        max_gap = max(max_gap, gap_sec)
        if gap_sec >= min_gap_seconds:
            long_gaps.append((t1, t2, gap_sec))

    return max_gap, long_gaps, total_messages


def _parse_until_time(until_str: str | None) -> dt_time | None:
    """Parse chuỗi --until thành datetime.time."""
    if not until_str:
        return None
    until_str = until_str.strip()
    parts = until_str.split(":")
    if len(parts) == 2:
        return dt_time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return dt_time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Định dạng --until không hợp lệ (kỳ vọng HH:MM hoặc HH:MM:SS): '{until_str}'")


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def record_orderbook_stream(
    symbol: str,
    until_time: dt_time | None = None,
    config_path: str = "config/config.yaml",
    data_dir: Path | str = "data/orderbook",
) -> dict[str, Any]:
    """Kết nối WebSocket SSI và ghi nhận dòng tin QUOTE / TRADE."""
    _load_dotenv()
    app_cfg = load_config(config_path)
    db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
    storage = Storage(db_dsn)

    now_vn = datetime.now(TZ)
    out_path = get_orderbook_filepath(data_dir, symbol, now_vn)
    print(f"[{now_vn.strftime('%H:%M:%S')}] Khởi động máy ghi sổ lệnh {symbol}")
    print(f"  File ghi nhận: {out_path}")
    if until_time:
        print(f"  Thời điểm tự dừng: {until_time.strftime('%H:%M:%S')} (giờ VN)")

    from ssi_sdk import AsyncStream

    auth = await ensure_authenticated(app_cfg, storage)
    stream = AsyncStream(auth)

    counts = {"QUOTE": 0, "TRADE": 0, "OTHER": 0}
    timestamps: list[datetime] = []

    # Nạp dữ liệu đã ghi trước đó trong ngày (nếu có) để thống kê toàn diện cuối phiên
    if out_path.exists() and out_path.stat().st_size > 0:
        try:
            with gzip.open(out_path, mode="rt", encoding="utf-8") as existing_f:
                for line in existing_f:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    m = json.loads(line_s)
                    c = classify_message(m)
                    counts[c] = counts.get(c, 0) + 1
                    r_ts = m.get("recv_ts")
                    if r_ts:
                        timestamps.append(datetime.fromisoformat(r_ts))
            print(f"  Đã nạp {sum(counts.values()):,} tin đã ghi trước đó trong ngày.")
        except Exception as e:
            print(f"  Cảnh báo: không thể nạp dữ liệu cũ: {e}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_signal() -> None:
        print("\nNhận tín hiệu ngắt (Ctrl+C / SIGTERM), đang dừng an toàn...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, RuntimeError):
            # Trên Windows, add_signal_handler có thể không hỗ trợ trong một số loop
            pass

    # Mở file gzip chế độ append
    with gzip.open(out_path, mode="at", encoding="utf-8") as gz_file:

        def on_message(raw_msg: Any) -> None:
            recv_dt = datetime.now(TZ)
            msg_dict = (
                dataclasses.asdict(raw_msg)
                if dataclasses.is_dataclass(raw_msg)
                else raw_msg
            )
            if not isinstance(msg_dict, dict):
                return

            cat = classify_message(msg_dict)
            counts[cat] = counts.get(cat, 0) + 1

            if cat in ("QUOTE", "TRADE"):
                msg_dict["recv_ts"] = recv_dt.isoformat()
                line = json.dumps(msg_dict, ensure_ascii=False, default=str)
                gz_file.write(line + "\n")
                gz_file.flush()
                timestamps.append(recv_dt)

        while not stop_event.is_set():
            if until_time and datetime.now(TZ).time() >= until_time:
                print(
                    f"\nĐã đạt mốc thời gian tự dừng ({until_time.strftime('%H:%M:%S')}), kết thúc phiên ghi."
                )
                break

            auth = None
            stream = None
            try:
                auth = await ensure_authenticated(app_cfg, storage)
                stream = AsyncStream(auth)
                stream.streaming.on_data = on_message
                now_str = datetime.now(TZ).strftime("%H:%M:%S")
                print(f"[{now_str}] Đang kết nối WebSocket SSI...")
                await stream.streaming.connect()
                print(f"[{now_str}] Đã kết nối, đang đăng ký nhận dữ liệu mã {symbol}...")
                await stream.streaming.subscribe_symbol([symbol])
                print(f"[{now_str}] Bắt đầu lắng nghe dữ liệu stream...\n")

                while not stop_event.is_set():
                    if until_time and datetime.now(TZ).time() >= until_time:
                        stop_event.set()
                        print(
                            f"\nĐã đạt mốc thời gian tự dừng ({until_time.strftime('%H:%M:%S')}), kết thúc phiên ghi."
                        )
                        break

                    # Tự động phát hiện ngắt kết nối từ SSI và nối lại
                    ws_client = getattr(stream.streaming, "_ws", None)
                    if ws_client is not None and not ws_client.is_connected:
                        print(
                            f"\n[{datetime.now(TZ).strftime('%H:%M:%S')}] WebSocket bị ngắt từ server SSI, chuẩn bị kết nối lại..."
                        )
                        break

                    await asyncio.sleep(0.5)

            except KeyboardInterrupt:
                print("\nNhận ngắt bàn phím (KeyboardInterrupt)...")
                stop_event.set()
                break
            except Exception as e:
                print(f"\n[{datetime.now(TZ).strftime('%H:%M:%S')}] Lỗi kết nối WebSocket: {e}, thử lại sau 3s...")
                await asyncio.sleep(3.0)
            finally:
                if stream is not None:
                    try:
                        await stream.streaming.disconnect()
                    except Exception:
                        pass
                if auth is not None:
                    try:
                        await auth.close()
                    except Exception:
                        pass

            if not stop_event.is_set() and (not until_time or datetime.now(TZ).time() < until_time):
                await asyncio.sleep(1.0)

    # Thống kê sau phiên ghi
    file_size_bytes = out_path.stat().st_size if out_path.exists() else 0
    file_size_mb = file_size_bytes / (1024 * 1024)

    max_gap, long_gaps, total_considered = detect_silence_gaps(
        timestamps, min_gap_seconds=10.0
    )

    print("\n" + "=" * 65)
    print("=== BÁO CÁO THỐNG KÊ MÁY GHI SỔ LỆNH VN30F (BRIEF 87) ===")
    print("=" * 65)
    print(f"- Hợp đồng: {symbol}")
    print(f"- File dữ liệu: {out_path}")
    print(f"- Dung lượng file: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB)")
    print(
        f"- Tổng số tin nhận: {sum(counts.values()):,} "
        f"(QUOTE: {counts['QUOTE']:,}, TRADE: {counts['TRADE']:,}, KHÁC: {counts['OTHER']:,})"
    )
    print(f"- Tổng số tin QUOTE/TRADE đã xét khoảng lặng: {total_considered:,}")
    print(f"- Khoảng lặng dài nhất trong giờ phiên: {max_gap:.2f} giây")

    if long_gaps:
        print(f"- Danh sách {len(long_gaps)} khoảng lặng > 10.0s trong giờ phiên:")
        for t1, t2, sec in long_gaps:
            t1_s = t1.astimezone(TZ).strftime("%H:%M:%S")
            t2_s = t2.astimezone(TZ).strftime("%H:%M:%S")
            print(f"  + Từ {t1_s} đến {t2_s}: {sec:.2f} giây")
    else:
        print("- Không phát hiện khoảng lặng nào > 10.0 giây trong giờ giao dịch.")
    print("=" * 65 + "\n")

    return {
        "symbol": symbol,
        "file_path": str(out_path),
        "file_size_bytes": file_size_bytes,
        "counts": counts,
        "total_considered": total_considered,
        "max_gap_seconds": max_gap,
        "long_gaps": long_gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Máy ghi dữ liệu sổ lệnh và dòng lệnh VN30F (Brief 87)"
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Mã hợp đồng bắt buộc (ví dụ: 41I1GA000)",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Mốc giờ VN tự dừng (định dạng HH:MM hoặc HH:MM:SS)",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn file config (mặc định: config/config.yaml)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/orderbook",
        help="Thư mục gốc lưu trữ dữ liệu (mặc định: data/orderbook)",
    )
    args = parser.parse_args()

    until_time = _parse_until_time(args.until)

    try:
        asyncio.run(
            record_orderbook_stream(
                symbol=args.symbol,
                until_time=until_time,
                config_path=args.config,
                data_dir=args.data_dir,
            )
        )
    except Exception as e:
        print(f"\n[LỖI] Máy ghi gặp sự cố: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
