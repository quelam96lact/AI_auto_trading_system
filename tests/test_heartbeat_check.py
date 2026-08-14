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
        def __init__(self, result=None):
            self._result = result

        def fetchall(self):
            # heartbeat: cả 2 service đều tươi — chỉ 2A/2B quyết định
            return [("collector", fixed_now - timedelta(seconds=30)), ("engine", fixed_now - timedelta(seconds=45))]

        def fetchone(self):
            return self._result  # max(ts) = None (khong bar); engine_state = None

    class FakeConn:
        def execute(self, *a, **k):
            # 2C: engine_state khong co dong -> None (khong phai (None,))
            if "FROM engine_state" in str(a[0]):
                return FakeCur(None)
            if "FROM positions" in str(a[0]):
                return FakeCur([])
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


# ============ LEDGER-1 Viec 1: bat bien so sach (2C) ============


def test_ledger_deviation_zero_when_books_match():
    from scripts.heartbeat_check import ledger_deviation

    # cash 99.671.201,69 + 0 gia von - 100.000.000 = -328.798,31 == realized
    dev = ledger_deviation(99_671_201.69, -328_798.31, 0.0)
    assert abs(dev) < 0.01


def test_ledger_deviation_catches_historical_bug():
    from scripts.heartbeat_check import ledger_deviation

    # Dung trang thai loi lich su (6664cd9): realized thieu phi mua -> ve phai
    # cao hon ve trai -> dev AM, do lon dung 119.417,18
    dev = ledger_deviation(99_671_201.69, -209_381.13, 0.0)
    # LEDGER-2: abs KEP — abs(dev) la do lon, so sanh voi 119.417,18. Ban dau
    # thieu lop abs ngoai (`abs(dev) - 119417.18 < 0.01`) dung voi MOI dev nho
    # hon 119.417,19 ke ca 0 — test rong (Claude chung minh bang thuc nghiem)
    assert abs(abs(dev) - 119_417.18) < 0.01, f"phai lech dung 119.417,18, thuc te: {dev}"


def test_ledger_deviation_negative_case_fails_on_wrong_magnitude():
    """Ca am tinh: dev sai DO LON (khong phai 119.417,18) -> assert phai DO
    (chung minh test biet do, khong phai test rong)."""
    from scripts.heartbeat_check import ledger_deviation

    # realized dung (= -328.798,31) -> dev = 0, sai do lon
    dev = ledger_deviation(99_671_201.69, -328_798.31, 0.0)
    assert abs(dev) < 0.01  # tien de: dev thuc su = 0
    assert abs(abs(dev) - 119_417.18) > 0.01, "dev=0 khong duoc trung voi do lech lich su"


def test_ledger_deviation_open_position_counts():
    from scripts.heartbeat_check import ledger_deviation

    # Vi the dang mo: cash 99.000.000 + gia von 1000*1000 = 1.000.000
    # -> 99.000.000 + 1.000.000 - 100.000.000 = 0 == realized 0 -> khop
    # (bat bien dung LUON, khong chi khi phang)
    dev = ledger_deviation(99_000_000.0, 0.0, 1_000 * 1_000.0)
    assert abs(dev) < 0.01


def _run_main_with_ledger(monkeypatch, engine_state, positions_rows, fixed_now=None):
    """Chay main() voi du lieu so sach cho truoc (2A/2B im lang: bar moi,
    token ok). Tra ve (rc, messages)."""
    import scripts.heartbeat_check as hc

    sent = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent.append(msg))
    if fixed_now is None:
        fixed_now = datetime(2026, 8, 14, 10, 0, tzinfo=TZ)  # thu 6, trong phien

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    class FakeCur:
        def __init__(self, result):
            self._result = result

        def fetchall(self):
            if isinstance(self._result, list):
                return self._result
            return []

        def fetchone(self):
            return self._result

    class FakeConn:
        def __init__(self, queries):
            self._queries = queries
            self._i = 0

        def execute(self, query, *a, **k):
            # route theo noi dung query
            if "FROM heartbeat" in query:
                return FakeCur([("collector", fixed_now - timedelta(seconds=30)), ("engine", fixed_now - timedelta(seconds=45))])
            if "max(ts) FROM bars" in query:
                return FakeCur((fixed_now - timedelta(minutes=2),))  # bar moi -> 2A im
            if "FROM engine_state" in query:
                return FakeCur(engine_state)
            if "FROM positions" in query:
                return FakeCur(positions_rows)
            return FakeCur(None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn(None))
    # token ok -> 2B im lang
    monkeypatch.setattr(
        hc, "Storage",
        lambda dsn: type("S", (), {"load_ssi_token": lambda self: {"refresh_token_expires_at": fixed_now.timestamp() + 7200}})(),
    )
    # Khong monkeypatch open — main() doc config/config.yaml that (file ton tai)
    rc = hc.main()
    return rc, sent


def test_main_alerts_when_ledger_mismatch(monkeypatch):
    """2C qua DUONG DUNG TIN NHAN trong main(): lech qua dung sai -> bao,
    tin nhan chua du ba so (ve trai, ve phai, do lech)."""
    rc, sent = _run_main_with_ledger(monkeypatch, (99_671_201.69, -209_381.13), [])
    assert rc == 1, f"phai bao khi lech so sach, rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    msg = sent[0]
    assert "hai sổ sách LỆCH" in msg
    assert "119,417.18" in msg or "119.417,18" in msg, f"tin nhan phai co do lech 119.417,18, thuc te: {msg}"


def test_main_silent_when_ledger_matches_with_open_position(monkeypatch):
    """2C: vi the dang mo (qty>0) van khop -> im lang (bat bien dung LUON)."""
    # cash 99.000.000 + gia von 1000 x 1000 = 1.000.000 -> tong 100.000.000
    # - capital = 0 == realized 0 -> khop
    rc, sent = _run_main_with_ledger(monkeypatch, (99_000_000.0, 0.0), [(1_000.0, 1_000)])
    assert rc == 0, f"khong duoc bao khi so sach khop, rc={rc} (tin: {sent})"
