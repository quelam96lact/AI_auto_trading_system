"""Dead-man's switch: cảnh báo Telegram khi collector/engine ngừng đập heartbeat.

Chạy bằng cron TRÊN HOST (không phải trong container) — nếu chạy trong chính
container đang chết thì nó cũng chết theo. Xem DEPLOYMENT.md §9.

Exit code: 0 = ổn, 1 = có cảnh báo đã gửi, 2 = sai cấu hình.
"""

import os
import sys
from datetime import datetime, timedelta

import psycopg

from trading.calendar_vn import TZ, is_trading_time
from trading.telegram import send_telegram

SERVICES = ("collector", "engine")
DEFAULT_MAX_AGE_SECONDS = 300


def stale_services(rows, now, max_age_seconds, expected=SERVICES) -> list[str]:
    """rows: list[(service, last_seen)] đọc từ bảng heartbeat.

    Trả về tên các service thiếu hẳn dòng heartbeat hoặc có last_seen quá hạn.
    """
    seen = {r[0]: r[1] for r in rows}
    limit = timedelta(seconds=max_age_seconds)
    return [
        svc
        for svc in expected
        if seen.get(svc) is None or now - seen[svc] > limit
    ]


def main() -> int:
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        print("DB_DSN chưa được set", file=sys.stderr)
        return 2
    max_age = int(os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS))

    now = datetime.now(TZ)
    # Chỉ cảnh báo trong giờ giao dịch: cả 2 service đều đập 24/7, nhưng ngoài
    # phiên thì service chết không gây hại ngay — tránh spam đêm/cuối tuần.
    if not is_trading_time(now):
        return 0

    try:
        with psycopg.connect(dsn, connect_timeout=10) as c:
            rows = c.execute("SELECT service, last_seen FROM heartbeat").fetchall()
    except Exception as e:
        send_telegram(
            f"[CRITICAL] heartbeat check không đọc được DB: {type(e).__name__}: {e}"[:300]
        )
        return 1

    stale = stale_services(rows, now, max_age)
    if stale:
        send_telegram(
            f"[CRITICAL] service ngừng heartbeat quá {max_age}s: {', '.join(stale)}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
