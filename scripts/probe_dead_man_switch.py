"""Probe: kiem chung duong day Telegram + dead-man's switch O LOCAL, khong can
doi den gio giao dich that.

Dung DUNG code san xuat: trading.alerts.alert(), trading.telegram.send_telegram(),
trading.collector.watchdog.Watchdog. Chi gia now_fn/is_trading_fn de bo qua dieu
kien "dang trong gio giao dich" cua watchdog — do la dieu KHONG the mo phong
duoc bang cach chay collector that ngoai gio.

CHI DOC/GUI TELEGRAM. Khong dong Postgres, khong dong NATS, khong ket noi SSI.

Chay (PowerShell, tai goc repo, sau khi da nap .env vao bien moi truong):

  Get-Content .env | Where-Object { $_ -match '^\\s*[^#].*=' } | ForEach-Object {
      $k, $v = $_ -split '=', 2
      Set-Item -Path "env:$($k.Trim())" -Value $v.Trim()
  }
  uv run python scripts/probe_dead_man_switch.py
"""

import os
import sys
import time
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.watchdog import Watchdog
from trading.telegram import send_telegram

TAG = "[PROBE dead-man-switch]"


def check_env() -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(
            "THIEU TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong bien moi truong.\n"
            "Nap .env vao shell truoc (xem docstring dau file), roi chay lai."
        )
        return False
    print(f"OK: TELEGRAM_BOT_TOKEN da duoc thiet lap (an secret), TELEGRAM_CHAT_ID={chat_id}")
    return True


def part_a_sanity() -> bool:
    print("\n=== PHAN A: gui thang 1 tin qua send_telegram() (khong qua alert) ===")
    try:
        ok = send_telegram(f"{TAG} Phan A: kiem tra duong truyen Telegram tu local.")
        if ok:
            print("Telegram API xac nhan da nhan: THANH CONG (send_telegram tra ve True).")
        else:
            print("send_telegram tra ve False: THAT BAI (xem log WARNING).")
        return ok
    except Exception as e:
        print(f"LOI khi goi send_telegram: {type(e).__name__}: {e}")
        print("Dung lai o day — sua token/chat_id truoc khi chay Phan B.")
        sys.exit(1)


def part_b_watchdog() -> None:
    print("\n=== PHAN B: mo phong Watchdog that (WARN roi CRITICAL) ===")
    print("Dung dung class Watchdog + alert() cua production, chi gia dong ho.")

    clock = {"t": datetime(2026, 8, 11, 10, 0, tzinfo=TZ)}  # gia dinh giua gio GD

    def now_fn():
        return clock["t"]

    def is_trading_fn(_ts):
        return True  # BO QUA dieu kien gio that — muc dich cua probe nay

    def on_stale():
        alert(
            "WARN",
            f"{TAG} feed stale, forcing reconnect (SIMULATED, khong phai su co that)",
        )

    def on_critical():
        alert(
            "CRITICAL",
            f"{TAG} feed stale beyond max failures (SIMULATED, khong phai su co that)",
        )

    stale_seconds = 180
    max_failures = 3
    wd = Watchdog(
        stale_seconds=stale_seconds,
        max_failures=max_failures,
        now_fn=now_fn,
        is_trading_fn=is_trading_fn,
        on_stale=on_stale,
        on_critical=on_critical,
    )
    print(f"config that: stale_seconds={stale_seconds} max_failures={max_failures}")
    print("KHONG goi wd.beat() nua tu day — mo phong feed dung hoan toan.\n")

    # Đủ (max_failures + 1) vòng để thấy WARN lặp lại rồi CRITICAL, rồi 1 vòng
    # sau CRITICAL để xác nhận bộ đếm đã reset về 0 (đúng watchdog.py:33).
    for i in range(max_failures + 2):
        clock["t"] += timedelta(seconds=stale_seconds + 1)
        print(f"[vong {i+1}] gio gia lap = {clock['t'].isoformat()}  (khong co beat)")
        wd.check()
        time.sleep(2)  # nhuong CPU cho thread gui Telegram cua alert() kip chay

    print("\nDa het vong. Doi them 3s cho cac thread Telegram con lai...")
    time.sleep(3)
    print(
        "\nKY VONG tren Telegram that: MOI vong deu co dung 1 tin WARN (moi vong"
        " la mot lan on_stale rieng, ke ca vong co CRITICAL), va dung 1 tin"
        f" CRITICAL o vong {max_failures}. Vong {max_failures + 1} quay lai chi"
        " co WARN — bo dem da reset ve 0, day moi la thu can kiem chung (khong"
        f" spam CRITICAL). Tong: {max_failures + 2} tin WARN + 1 tin CRITICAL."
    )


if __name__ == "__main__":
    if not check_env():
        sys.exit(1)
    part_a_sanity()
    if "--part-a" in sys.argv or "--part-a-only" in sys.argv:
        sys.exit(0)
    input(
        "\nDa thay tin Phan A tren Telegram chua? Enter de chay Phan B, Ctrl+C de dung: "
    )
    part_b_watchdog()
