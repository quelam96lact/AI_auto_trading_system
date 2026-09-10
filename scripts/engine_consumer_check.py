"""Chuông 2C: Giám sát engine có đang tiêu thụ bar thật từ JetStream hay không.

Brief đợt 25 (Task 2) / Brief đợt 26 (Task 5) / Brief đợt 27 (Task 1).
CHỈ ĐỌC (read-only): Gọi duy nhất `js.consumer_info("BARS", "engine")` và SELECT bars.
CẤM TUYỆT ĐỐI các thao tác ghi, xoá, purge, thêm hay sửa consumer.

Cảnh báo khi:
1. Đang trong giờ giao dịch (is_trading_time).
2. num_pending vượt ngưỡng HOẶC delivered.stream_seq không đổi trong khi số bar trong DB tăng.
3. Đã qua thời gian chống spam (15 phút).

Exit code:
0 = OK (hoặc ngoài phiên)
1 = Đã gửi cảnh báo (hoặc phát hiện sự cố trong phiên)
2 = Lỗi cấu hình / DB_DSN chưa set / kết nối
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import nats
import psycopg
import yaml

from trading.alerts import _print_safe
from trading.calendar_vn import TZ, is_trading_time
from trading.telegram import send_telegram

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = Path(REPO) / "logs" / ".engine_consumer_last_check"
ALERT_COOLDOWN_SECONDS = 900  # 15 phút chống spam


async def read_nats_consumer_info(nats_url: str, stream: str = "BARS", consumer: str = "engine"):
    """Chỉ đọc consumer_info từ NATS JetStream (read-only)."""
    target_url = nats_url.replace("localhost", "127.0.0.1") if "localhost" in nats_url else nats_url
    try:
        nc = await nats.connect(target_url, connect_timeout=3)
    except Exception:
        nc = await nats.connect(nats_url, connect_timeout=3)
    try:
        js = nc.jetstream()
        info = await js.consumer_info(stream, consumer)
        return info
    finally:
        await nc.close()


def read_today_bars_count(dsn: str) -> int:
    """Đếm số bar được ghi trong ngày hôm nay từ DB."""
    target_dsn = dsn.replace("@localhost", "@127.0.0.1") if "@localhost" in dsn else dsn
    query = "SELECT count(*) FROM bars WHERE ts >= CURRENT_DATE;"
    with psycopg.connect(target_dsn) as conn, conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        _print_safe(f"[engine-consumer] Không thể ghi file state: {e}")


def check_consumer(
    info,
    today_bars: int,
    prev_state: dict,
    now: datetime,
    pending_threshold: int = 20,
) -> tuple[bool, str]:
    """Kiểm tra logic tiêu thụ bar của engine.
    Trả về (is_faulty: bool, reason: str).
    """
    num_pending = getattr(info, "num_pending", 0) or 0
    delivered = getattr(info, "delivered", None)
    stream_seq = getattr(delivered, "stream_seq", 0) if delivered else 0

    if num_pending >= pending_threshold:
        return True, f"num_pending vượt ngưỡng ({num_pending} >= {pending_threshold})"

    if prev_state:
        prev_stream_seq = prev_state.get("stream_seq", stream_seq)
        prev_bars = prev_state.get("today_bars", today_bars)
        # Nếu DB đã tăng bar mới nhưng engine không nhúc nhích stream_seq
        if today_bars > prev_bars and stream_seq <= prev_stream_seq:
            return True, (
                f"engine dừng tiêu thụ bar: DB tăng {today_bars - prev_bars} bar "
                f"nhưng stream_seq không đổi ({stream_seq} <= {prev_stream_seq})"
            )

    return False, "OK"


def run_check(
    config_path: str = "config/config.yaml",
    force: bool = False,
    pending_threshold: int = 20,
) -> int:
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        print("DB_DSN chưa được set", file=sys.stderr)
        return 2

    # Đọc config bằng yaml.safe_load — KHÔNG import load_config
    try:
        cfg_file = Path(config_path)
        if not cfg_file.is_absolute():
            cfg_file = Path(REPO) / config_path
        with open(cfg_file, encoding="utf-8") as f:
            cfg_data = yaml.safe_load(f) or {}

        holidays = frozenset(
            date.fromisoformat(str(h)) for h in (cfg_data.get("holidays") or [])
        )
        nats_url = os.environ.get("NATS_URL") or cfg_data.get("nats_url", "nats://localhost:4222")
        nats_stream = os.environ.get("NATS_STREAM") or cfg_data.get("nats_stream", "BARS")
    except Exception as e:
        send_telegram(
            f"[CRITICAL] engine_consumer_check không đọc được config/config.yaml: {type(e).__name__}: {e}"[:300]
        )
        return 1

    now = datetime.now(TZ)
    if not force and not is_trading_time(now, holidays):
        _print_safe(f"[engine-consumer] Ngoài giờ giao dịch VN ({now.strftime('%H:%M:%S')}), bỏ qua.")
        return 0

    try:
        today_bars = read_today_bars_count(dsn)
    except Exception as e:
        _print_safe(f"[engine-consumer] Lỗi đọc DB: {e}")
        today_bars = 0

    try:
        info = asyncio.run(read_nats_consumer_info(nats_url, nats_stream, "engine"))
    except Exception as e:
        msg = f"[engine-consumer] LỖI: Không thể kết nối NATS hoặc đọc consumer 'engine': {e}"
        _print_safe(msg)
        send_telegram(f"🚨 CHUÔNG 2C: {msg}")
        return 1

    prev_state = load_state()
    is_faulty, reason = check_consumer(
        info,
        today_bars=today_bars,
        prev_state=prev_state,
        now=now,
        pending_threshold=pending_threshold,
    )

    delivered = getattr(info, "delivered", None)
    stream_seq = getattr(delivered, "stream_seq", 0) if delivered else 0

    new_state = {
        "stream_seq": stream_seq,
        "today_bars": today_bars,
        "ts": now.timestamp(),
        "last_alert_ts": prev_state.get("last_alert_ts", 0),
    }

    if is_faulty:
        last_alert_ts = prev_state.get("last_alert_ts", 0)
        cooldown_elapsed = now.timestamp() - last_alert_ts
        alert_msg = f"🚨 CHUÔNG 2C (Engine Consumer): Phát hiện sự cố tiêu thụ bar: {reason}"
        _print_safe(alert_msg)

        if cooldown_elapsed >= ALERT_COOLDOWN_SECONDS:
            send_telegram(alert_msg)
            new_state["last_alert_ts"] = now.timestamp()
        else:
            _print_safe(f"[engine-consumer] Đang trong thời gian chống spam ({cooldown_elapsed:.0f}s < {ALERT_COOLDOWN_SECONDS}s), chưa gửi lại.")

        save_state(new_state)
        return 1

    _print_safe(f"[engine-consumer] OK: engine đang tiêu thụ bình thường (seq={stream_seq}, bars_today={today_bars}).")
    save_state(new_state)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Chuông 2C: Giám sát engine tiêu thụ bar từ NATS JetStream (chỉ đọc).")
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn file config")
    parser.add_argument("--force", action="store_true", help="Bỏ qua kiểm tra giờ giao dịch")
    parser.add_argument("--threshold", type=int, default=20, help="Ngưỡng num_pending cảnh báo")
    args = parser.parse_args()

    sys.exit(run_check(args.config, force=args.force, pending_threshold=args.threshold))


if __name__ == "__main__":
    main()
