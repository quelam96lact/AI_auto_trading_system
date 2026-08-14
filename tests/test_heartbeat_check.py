from datetime import datetime, timedelta

from scripts.heartbeat_check import bar_stale, stale_services, token_expiry_status
from trading.calendar_vn import TZ

NOW = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)  # thu 4, trong phien sang


def test_no_stale_when_all_services_fresh():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=45)),
    ]
    assert stale_services(rows, NOW, 300) == []


def test_service_past_max_age_is_stale():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=600)),
    ]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_missing_service_row_is_stale():
    rows = [("collector", NOW - timedelta(seconds=30))]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_all_services_missing_are_stale():
    assert stale_services([], NOW, 300) == ["collector", "engine"]


# ============ FEE-ALARM-1 Viec 2A: dữ liệu ngừng chảy ============


def test_bar_fresh_no_alarm():
    assert bar_stale(NOW - timedelta(minutes=2), NOW) is False


def test_bar_stale_during_session_alarms():
    assert bar_stale(NOW - timedelta(minutes=20), NOW) is True  # ngưỡng 15 phút


def test_bar_stale_at_atc_window_no_alarm():
    """bar cũ lúc 14:35 (khung ATC 14:30-14:45) -> KHÔNG báo — khung ATC lúc
    có lúc không tùy mã tùy ngày (đo thật 12/08: 0 bar), kiểm qua đó báo láo."""
    now_atc = datetime(2026, 7, 15, 14, 35, tzinfo=TZ)
    assert bar_stale(now_atc - timedelta(hours=2), now_atc) is False


def test_bar_stale_outside_hours_no_alarm():
    """bar cũ ngoài giờ giao dịch -> không báo."""
    now_night = datetime(2026, 7, 15, 20, 0, tzinfo=TZ)
    assert bar_stale(now_night - timedelta(hours=5), now_night) is False


def test_no_bar_whole_day_alarms():
    """không có bar nào cả ngày (max_ts=None), đang trong phiên -> CÓ báo —
    ca 'feed chưa từng nối được', dễ tuột nhất."""
    assert bar_stale(None, NOW) is True


def test_bar_stale_weekend_no_alarm():
    now_sat = datetime(2026, 7, 18, 10, 0, tzinfo=TZ)  # thứ 7
    assert bar_stale(now_sat - timedelta(hours=3), now_sat) is False


# ============ FEE-ALARM-1 Viec 2B: token SSI ============


def _now_ts(hour=10, minute=0):
    return datetime(2026, 7, 15, hour, minute, tzinfo=TZ).timestamp()


def test_token_90min_ok():
    assert token_expiry_status(_now_ts() + 90 * 60, NOW) is None


def test_token_30min_warn():
    assert token_expiry_status(_now_ts() + 30 * 60, NOW) == "WARN"


def test_token_expired_critical():
    assert token_expiry_status(_now_ts() - 60, NOW) == "CRITICAL"


def test_no_token_row_critical():
    assert token_expiry_status(None, NOW) == "CRITICAL"


def test_premarket_830_expired_alarms():
    """8:30 sáng (ngoài is_trading_time) mà token đã hết hạn -> CÓ báo —
    khung 8:00-9:00 để kịp hành động trước giờ mở cửa (điểm khác biệt 2B)."""
    now_830 = datetime(2026, 7, 15, 8, 30, tzinfo=TZ)
    assert token_expiry_status(_now_ts(hour=8, minute=0) - 60, now_830) == "CRITICAL"


def test_main_no_crash_when_no_bar_any_day(monkeypatch):
    """FEE-ALARM-2 Lỗi 1: max_ts=None (feed chưa từng nối được) đi QUA đường
    dựng tin nhắn trong main() — trước đây `now - None` -> TypeError, chuông
    báo chết đúng lúc cần nhất. Dead-man's switch không được ném exception."""
    import scripts.heartbeat_check as hc

    sent = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent.append(msg))

    # Cố định 'now' = 14:00 thứ Sáu (trong cửa sổ 2A) — main gọi datetime.now(TZ)
    fixed_now = datetime(2026, 8, 14, 14, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    class FakeCur:
        def fetchall(self):
            # heartbeat: cả 2 service đều tươi — chỉ 2A/2B quyết định
            return [("collector", fixed_now - timedelta(seconds=30)), ("engine", fixed_now - timedelta(seconds=45))]

        def fetchone(self):
            return (None,)  # max(ts) = KHÔNG có bar nào

    class FakeConn:
        def execute(self, *a, **k):
            return FakeCur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn())
    # token OK — chỉ test đường 2A
    monkeypatch.setattr(hc, "Storage", lambda dsn: type("S", (), {"load_ssi_token": lambda self: {"refresh_token_expires_at": fixed_now.timestamp() + 7200}})())

    rc = hc.main()
    assert rc == 1, f"phai gui canh bao (feed chua tung noi), rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    assert any("không có bar nào cả ngày" in m for m in sent), f"tin nhan phai noi ro ca khong-bar, thuc te: {sent}"
