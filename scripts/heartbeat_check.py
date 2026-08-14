"""Dead-man's switch: cảnh báo Telegram khi collector/engine ngừng đập heartbeat.

Chạy bằng cron TRÊN HOST (không phải trong container) — nếu chạy trong chính
container đang chết thì nó cũng chết theo. Xem DEPLOYMENT.md §9.

Exit code: 0 = ổn, 1 = có cảnh báo đã gửi, 2 = sai cấu hình.

FEE-ALARM-1 Việc 2 — hai cảnh báo bổ sung cho kiểu hỏng âm thầm (tiến trình
còn sống nhưng việc thật đã chết):
- 2A "dữ liệu ngừng chảy": bar không về trong cửa sổ kiểm tra.
- 2B "token SSI sắp/đã hết hạn": bắt đúng sự cố 14/08 — refresh token hết hạn
  13:39, feed chết 14:33, heartbeat vẫn xanh suốt. 2A KHÔNG bắt được sự cố đó
  (bar chảy đủ); 2B mới bắt được.
"""

import os
import sys
from datetime import datetime, time, timedelta

import psycopg
import yaml

from trading.calendar_vn import TZ, is_trading_time
from trading.engine.main import CAPITAL  # LEDGER-1: import hang so tu trading/ —
# da kiem main.py module-level KHONG chay side effect (chi import + dinh nghia;
# storage/nats nam trong ham). KHONG chep so sang day (hai noi lech = bao lao
# mai mai hoac im mai mai).
from trading.storage.db import Storage
from trading.telegram import send_telegram

SERVICES = ("collector", "engine")
DEFAULT_MAX_AGE_SECONDS = 300

# LEDGER-1 2C: dung sai so sach. Can cu: float double tich luy qua hang nghin
# lenh sai so ~< 0.01 VND (15-17 chu so); 1.000 VND = ~100.000x bien an toan
# chong bao lao vi lam tron, dong thoi nho hon MỌI khoan lech that (phi mua
# nho nhat trong ho so la 6.670d/lenh — 6664cd9 lech 119.417).
LEDGER_TOLERANCE = 1_000.0

# 2A: cửa sổ kiểm tra bar — KHÔNG dùng SESSIONS của calendar_vn (coi tới 14:45
# là giờ giao dịch). Khung ATC 14:30-14:45 lúc có lúc không tùy mã tùy ngày
# (đo thật 12/08: 0 bar; 13/08: 3 bar trong 14:30-14:40) — kiểm qua đó báo láo.
# Cắt ở 14:30, chấp nhận mù 15 phút cuối phiên (FEE-ALARM-1).
CHECK_SESSIONS = [(time(9, 0), time(11, 30)), (time(13, 0), time(14, 30))]
# Ngưỡng bar cũ: ĐO trên dữ liệu thật (21 ngày, trong cửa sổ 2A, tách theo
# từng phiên) cho ĐÚNG đại lượng code đang đo — max(ts) GỘP các mã cấu hình
# (khoảng trống chỉ tồn tại khi KHÔNG mã nào ra bar; mã thanh khoản thấp có
# khung rỗng nhưng các mã khác lấp vào): gap lớn nhất = 5 PHÚT, 0 lần > 15.
# Ngưỡng 15 phút = 3x biên độ đo được, vẫn dư biên. (Bản đầu đặt 30 vì đo
# gap TỪNG MÃ — HII 35 phút — sai đại lượng; 30 sẽ làm feed chết 30 phút mới
# kêu, mù 1/3 phiên chiều 90 phút.)
DEFAULT_STALE_BAR_MINUTES = 15


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


def in_bar_check_window(ts: datetime) -> bool:
    """Trong cửa sổ kiểm tra bar 2A (9:00-11:30 / 13:00-14:30, ngày giao dịch)?"""
    ts = ts.astimezone(TZ)
    if ts.weekday() >= 5:
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in CHECK_SESSIONS)


def bar_stale(max_ts, now, stale_minutes=DEFAULT_STALE_BAR_MINUTES) -> bool:
    """2A: dữ liệu ngừng chảy. max_ts = max(ts) gộp các mã ĐANG CẤU HÌNH
    (None = không có bar nào cả ngày — ca "feed chưa từng nối được").

    Chỉ báo trong cửa sổ kiểm tra 2A. Ngoài cửa sổ (cuối tuần, khung ATC,
    ngoài giờ) -> False.

    Hạn chế đã biết: is_trading_time(holidays=frozenset()) mặc định rỗng ->
    ngày lễ VN sẽ báo láo cả ngày (không có bar nào). Đây là hạn chế đã biết,
    tham số holidays là chỗ mở rộng — KHÔNG tự dựng lịch nghỉ lễ (chưa được giao).
    """
    if not in_bar_check_window(now):
        return False
    if max_ts is None:
        return True  # "feed chưa từng nối được" — không có bar nào cả ngày
    return now - max_ts > timedelta(minutes=stale_minutes)


def token_expiry_status(refresh_expires_at, now) -> str | None:
    """2B: token SSI sắp/đã hết hạn. refresh_expires_at = epoch seconds
    (từ Storage.load_ssi_token) hoặc None (ssi_auth_state rỗng).

    Trả về: None (ổn) | "WARN" (còn < 60 phút) | "CRITICAL" (đã hết hạn hoặc
    không có dòng nào).

    Chỉ báo trong giờ giao dịch (is_trading_time dùng nguyên vẹn — 2B không
    liên quan khung ATC), CỘNG THÊM khung 8:00-9:00 sáng ngày giao dịch để
    cảnh báo kịp hành động trước giờ mở cửa (điểm khác biệt so với 2A).
    """
    if refresh_expires_at is None:
        return "CRITICAL"
    now_tz = now.astimezone(TZ)
    t = now_tz.time()
    pre_market = time(8, 0) <= t < time(9, 0) and now_tz.weekday() < 5
    if not (is_trading_time(now) or pre_market):
        return None
    remaining = refresh_expires_at - now.timestamp()
    if remaining < 0:
        return "CRITICAL"
    if remaining < 3600:
        return "WARN"
    return None


def ledger_deviation(cash: float, realized_pnl: float, positions_value: float, capital: float = CAPITAL) -> float:
    """2C: độ lệch hai sổ sách. Bất biến (đúng LUÔN, không chỉ khi phẳng):
        cash + Σ(avg_price × qty) − capital == realized_pnl
    Trả về vế trái − vế phải. > LEDGER_TOLERANCE (hoặc < −LEDGER_TOLERANCE)
    → hai sổ lệch (hai lỗi 6664cd9 / 2982900 đều là cash đúng, realized sai).
    """
    return (cash + positions_value - capital) - realized_pnl


def main() -> int:
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        print("DB_DSN chưa được set", file=sys.stderr)
        return 2
    max_age = int(os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS))

    now = datetime.now(TZ)
    # Chỉ cảnh báo trong giờ giao dịch: cả 2 service đều đập 24/7, nhưng ngoài
    # phiên thì service chết không gây hại ngay — tránh spam đêm/cuối tuần.
    if not is_trading_time(now) and not (
        time(8, 0) <= now.astimezone(TZ).time() < time(9, 0)
        and now.astimezone(TZ).weekday() < 5
    ):
        return 0

    # 2A: chỉ nhìn mã ĐANG CẤU HÌNH — bảng bars còn 302 mã universe nạp theo
    # lô, gộp chúng vào sẽ che mất một feed đã chết.
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
        with open(cfg_path, encoding="utf-8") as f:
            symbols = yaml.safe_load(f)["symbols"]
    except Exception as e:
        send_telegram(
            f"[CRITICAL] heartbeat check không đọc được config/config.yaml: {type(e).__name__}: {e}"[:300]
        )
        return 1

    try:
        with psycopg.connect(dsn, connect_timeout=10) as c:
            rows = c.execute("SELECT service, last_seen FROM heartbeat").fetchall()
            placeholders = ",".join(["%s"] * len(symbols))
            max_ts_row = c.execute(
                f"SELECT max(ts) FROM bars WHERE symbol IN ({placeholders})",
                list(symbols),
            ).fetchone()
            # 2C: doc engine_state + positions de kiem bat bien so sach
            es = c.execute("SELECT cash, realized_pnl FROM engine_state WHERE id = 1").fetchone()
            pos_rows = c.execute(
                "SELECT avg_price, qty FROM positions WHERE qty != 0"
            ).fetchall()
    except Exception as e:
        send_telegram(
            f"[CRITICAL] heartbeat check không đọc được DB: {type(e).__name__}: {e}"[:300]
        )
        return 1
    max_ts = max_ts_row[0] if max_ts_row else None

    stale = stale_services(rows, now, max_age)
    messages = []
    if stale:
        messages.append(
            f"[CRITICAL] service ngừng heartbeat quá {max_age}s: {', '.join(stale)}"
        )
    # 2C: bat bien so sach — cash + Σ(avg_price*qty) - capital == realized_pnl
    if es is not None:
        cash, realized = float(es[0]), float(es[1])
        positions_value = sum(float(r[0]) * float(r[1]) for r in pos_rows)
        dev = ledger_deviation(cash, realized, positions_value)
        if abs(dev) > LEDGER_TOLERANCE:
            # FEE-ALARM-2 bai hoc: chuong bao tuyet doi khong duoc nem exception —
            # dung lenh dang kiem, moi so lay tu DB, khong tinh gi them.
            messages.append(
                f"[CRITICAL] hai sổ sách LỆCH: vế trái (cash + giá vốn − vốn) "
                f"= {cash + positions_value - CAPITAL:,.2f}, vế phải (realized_pnl) "
                f"= {realized:,.2f}, độ lệch {dev:,.2f} VND"
            )
    if bar_stale(max_ts, now):
        # FEE-ALARM-2 Lỗi 1: max_ts=None (feed chưa từng nối được) mà dựng
        # tin nhắn với `now - max_ts` -> TypeError, chuông báo CHẾT đúng lúc
        # cần nhất. Dead-man's switch tuyệt đối không được ném exception.
        if max_ts is None:
            messages.append(
                "[CRITICAL] dữ liệu ngừng chảy: không có bar nào cả ngày "
                "(feed chưa từng nối được) trong cửa sổ kiểm tra"
            )
        else:
            messages.append(
                f"[CRITICAL] dữ liệu ngừng chảy: bar cuối cùng {max_ts} "
                f"({(now - max_ts).total_seconds() / 60:.0f} phút trước) "
                f"trong cửa sổ kiểm tra"
            )
    # 2B: dùng lại Storage.load_ssi_token — không viết truy vấn mới
    saved = Storage(dsn).load_ssi_token()
    expiry = saved.get("refresh_token_expires_at") if saved else None
    status = token_expiry_status(expiry, now)
    if status == "WARN":
        messages.append(
            f"[WARN] token SSI sắp hết hạn ({datetime.fromtimestamp(expiry, TZ):%H:%M %d/%m}) — "
            f"chạy scripts/spike_ssi_sdk_auth.py RỒI scripts/load_token_to_db.py "
            f"(bước thứ hai là cầu nối sang DB — chính nó hay bị bỏ quên)"
        )
    elif status == "CRITICAL":
        messages.append(
            "[CRITICAL] token SSI đã hết hạn hoặc không có trong DB — "
            "chạy scripts/spike_ssi_sdk_auth.py RỒI scripts/load_token_to_db.py "
            "(bước thứ hai là cầu nối sang DB — chính nó hay bị bỏ quên)"
        )

    if messages:
        send_telegram("\n".join(messages))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
