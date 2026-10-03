import json
import os
import sys
import urllib.error
from datetime import date, datetime, timedelta

from scripts.heartbeat_check import (
    bar_stale,
    check_holiday_exhaustion,
    position_sync_stale,
    stale_services,
    token_expiry_status,
)
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


def test_bar_stale_1300_after_lunch_no_alarm():
    """2026-09-03 13:00:03, bar cuoi 11:25 (phien sang) — tai hien dung loi
    chuong bao GIA 13:00:03: dong ho 95 phut nhung trong phien chi ~5 phut
    (11:25-11:30; nghi trua khong tinh; 13:00 moi mo cua phien chieu). Phai
    KHONG bao dong (bar phien chieu dau tien ve ~13:05)."""
    holidays = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})
    assert (
        bar_stale(
            datetime(2026, 9, 3, 11, 25, tzinfo=TZ),
            datetime(2026, 9, 3, 13, 0, 3, tzinfo=TZ),
            holidays=holidays,
        )
        is False
    )


def test_bar_stale_1300_feed_dead_still_alarms():
    """Cung 13:00 nhung bar cuoi 09:30 (feed chet tu sang): 120 phut trong
    phien > 15 -> VAN bao dong. Sửa chuong khong duoc lam no cam khi feed
    chet that (tieu chi 3, quan trong ngang tieu chi 2)."""
    assert (
        bar_stale(
            datetime(2026, 9, 3, 9, 30, tzinfo=TZ),
            datetime(2026, 9, 3, 13, 0, 3, tzinfo=TZ),
        )
        is True
    )


def test_bar_stale_first_minutes_of_morning_no_alarm():
    """09:00:09 sang dau phien, bar cuoi la phien truoc (28/08) — 0 phut trong
    phien hom nay troi qua, bar dau phien ve ~09:05. Khong bao (truoc day bao
    GIA vi dem ca dem + ngay le theo dong ho)."""
    holidays = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})
    assert (
        bar_stale(
            datetime(2026, 8, 28, 14, 45, tzinfo=TZ),
            datetime(2026, 9, 3, 9, 0, 9, tzinfo=TZ),
            holidays=holidays,
        )
        is False
    )


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


def _fresh_job_logs(logs_dir, now):
    """Brief 145: main() doc log THAT cua cron — nay doc thu muc tam. Dung log gia
    "vua chay 30 giay truoc" cho moi job duoc canh, de nhanh canh lich im lang va
    cac test cu van do dung dieu chung do (so sach, vi the, bar)."""
    import scripts.heartbeat_check as hc

    stamp = (now - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
    for job in hc.SCHEDULE_WATCH_JOBS.values():
        (logs_dir / job.log_file).write_text(
            f"{stamp} {job.label} start" + chr(10), encoding="utf-8"
        )


def test_main_no_crash_when_no_bar_any_day(monkeypatch, tmp_path):
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

        # get_last_called_timestamp doc log bang datetime.strptime (brief 145:
        # nay doc log gia trong thu muc tam thay vi log that)
        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    class FakeCur:
        def __init__(self, result=None):
            self._result = result

        def fetchall(self):
            # heartbeat: cả 2 service đều tươi — chỉ 2A/2B quyết định
            return [
                ("collector", fixed_now - timedelta(seconds=30)),
                ("engine", fixed_now - timedelta(seconds=45)),
            ]

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
    # token OK — chỉ test đường 2A; vi the dong bo TUOI (2D im lang)
    monkeypatch.setattr(
        hc,
        "Storage",
        lambda dsn: type(
            "S",
            (),
            {
                "load_ssi_token": lambda self: {
                    "refresh_token_expires_at": fixed_now.timestamp() + 7200
                },
                "read_position_sync_ts": lambda self, account_no: fixed_now
                - timedelta(minutes=2),
            },
        )(),
    )

    _fresh_job_logs(tmp_path, fixed_now)
    rc = hc.main(["--logs-dir", str(tmp_path)])
    assert rc == 1, f"phai gui canh bao (feed chua tung noi), rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    assert any(
        "không có bar nào cả ngày" in m for m in sent
    ), f"tin nhan phai noi ro ca khong-bar, thuc te: {sent}"


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
    assert (
        abs(abs(dev) - 119_417.18) < 0.01
    ), f"phai lech dung 119.417,18, thuc te: {dev}"


def test_ledger_deviation_negative_case_fails_on_wrong_magnitude():
    """Ca am tinh: dev sai DO LON (khong phai 119.417,18) -> assert phai DO
    (chung minh test biet do, khong phai test rong)."""
    from scripts.heartbeat_check import ledger_deviation

    # realized dung (= -328.798,31) -> dev = 0, sai do lon
    dev = ledger_deviation(99_671_201.69, -328_798.31, 0.0)
    assert abs(dev) < 0.01  # tien de: dev thuc su = 0
    assert (
        abs(abs(dev) - 119_417.18) > 0.01
    ), "dev=0 khong duoc trung voi do lech lich su"


def test_ledger_deviation_open_position_counts():
    from scripts.heartbeat_check import ledger_deviation

    # Vi the dang mo: cash 99.000.000 + gia von 1000*1000 = 1.000.000
    # -> 99.000.000 + 1.000.000 - 100.000.000 = 0 == realized 0 -> khop
    # (bat bien dung LUON, khong chi khi phang)
    dev = ledger_deviation(99_000_000.0, 0.0, 1_000 * 1_000.0)
    assert abs(dev) < 0.01


def _run_main_with_ledger(
    monkeypatch, logs_dir, engine_state, positions_rows, fixed_now=None
):
    """Chay main() voi du lieu so sach cho truoc (2A/2B im lang: bar moi,
    token ok). Tra ve (rc, messages)."""
    import scripts.heartbeat_check as hc

    sent = []

    def _fake_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(hc, "send_telegram", _fake_send)
    if fixed_now is None:
        fixed_now = datetime(2026, 8, 14, 10, 0, tzinfo=TZ)  # thu 6, trong phien

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

        # get_last_called_timestamp doc log bang datetime.strptime (brief 145:
        # nay doc log gia trong thu muc tam thay vi log that)
        strptime = staticmethod(datetime.strptime)

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
                return FakeCur(
                    [
                        ("collector", fixed_now - timedelta(seconds=30)),
                        ("engine", fixed_now - timedelta(seconds=45)),
                    ]
                )
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
    # token ok -> 2B im lang; vi the dong bo TUOI -> 2D im lang
    monkeypatch.setattr(
        hc,
        "Storage",
        lambda dsn: type(
            "S",
            (),
            {
                "load_ssi_token": lambda self: {
                    "refresh_token_expires_at": fixed_now.timestamp() + 7200
                },
                "read_position_sync_ts": lambda self, account_no: fixed_now
                - timedelta(minutes=2),
            },
        )(),
    )
    # Khong monkeypatch open — main() doc config/config.yaml that (file ton tai)
    _fresh_job_logs(logs_dir, fixed_now)
    rc = hc.main(["--logs-dir", str(logs_dir)])
    return rc, sent


def test_main_alerts_when_ledger_mismatch(monkeypatch, tmp_path):
    """2C qua DUONG DUNG TIN NHAN trong main(): lech qua dung sai -> bao,
    tin nhan chua du ba so (ve trai, ve phai, do lech)."""
    rc, sent = _run_main_with_ledger(
        monkeypatch, tmp_path, (99_671_201.69, -209_381.13), []
    )
    assert rc == 1, f"phai bao khi lech so sach, rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    msg = sent[0]
    assert "hai sổ sách LỆCH" in msg
    assert (
        "119,417.18" in msg or "119.417,18" in msg
    ), f"tin nhan phai co do lech 119.417,18, thuc te: {msg}"


def test_main_silent_when_ledger_matches_with_open_position(monkeypatch, tmp_path):
    """2C: vi the dang mo (qty>0) van khop -> im lang (bat bien dung LUON)."""
    # cash 99.000.000 + gia von 1000 x 1000 = 1.000.000 -> tong 100.000.000
    # - capital = 0 == realized 0 -> khop
    rc, sent = _run_main_with_ledger(
        monkeypatch, tmp_path, (99_000_000.0, 0.0), [(1_000.0, 1_000)]
    )
    assert rc == 0, f"khong duoc bao khi so sach khop, rc={rc} (tin: {sent})"


# ============ 2D: vị thế ngừng đồng bộ ============


def test_position_sync_fresh_no_alarm():
    """2D (a): mới đồng bộ (2 phút trước) -> False — chưa cần báo."""
    assert position_sync_stale(NOW - timedelta(minutes=2), NOW, 15) is False


def test_position_sync_past_threshold_alarms():
    """2D (b): quá ngưỡng (20 phút trước, ngưỡng 15) -> True — phải báo."""
    assert position_sync_stale(NOW - timedelta(minutes=20), NOW, 15) is True


def test_position_sync_never_synced_alarms():
    """2D (c): sync_ts=None (chưa từng đồng bộ) -> True và KHÔNG ném exception —
    ca dễ tuột nhất, giống max_ts=None của 2A."""
    assert position_sync_stale(None, NOW, 15) is True


def test_position_sync_at_threshold_boundary():
    """2D (d): biên ngưỡng — đúng 15 phút thì CHƯA quá (> mới stale, cùng quy ước
    bar_stale 2A: `now - ts > timedelta`); 15 phút + 1 giây thì quá."""
    assert position_sync_stale(NOW - timedelta(minutes=15), NOW, 15) is False
    assert position_sync_stale(NOW - timedelta(minutes=15, seconds=1), NOW, 15) is True


def _run_main_with_position_sync(monkeypatch, logs_dir, sync_ts, fixed_now=None):
    """Chay main() voi moc dong bo vi the cho truoc (2A/2B/2C im lang: bar moi,
    token ok, ledger khop). Tra ve (rc, messages)."""
    import scripts.heartbeat_check as hc

    sent = []

    def _fake_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(hc, "send_telegram", _fake_send)
    if fixed_now is None:
        fixed_now = datetime(2026, 8, 14, 10, 0, tzinfo=TZ)  # thu 6, trong phien

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

        # get_last_called_timestamp doc log bang datetime.strptime (brief 145:
        # nay doc log gia trong thu muc tam thay vi log that)
        strptime = staticmethod(datetime.strptime)

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
        def execute(self, query, *a, **k):
            if "FROM heartbeat" in query:
                return FakeCur(
                    [
                        ("collector", fixed_now - timedelta(seconds=30)),
                        ("engine", fixed_now - timedelta(seconds=45)),
                    ]
                )
            if "max(ts) FROM bars" in query:
                return FakeCur((fixed_now - timedelta(minutes=2),))  # bar moi -> 2A im
            if "FROM engine_state" in query:
                return FakeCur(None)
            if "FROM positions" in query:
                return FakeCur([])
            return FakeCur(None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn())
    # token ok -> 2B im lang; sync_ts theo tham so -> 2D quyet dinh
    monkeypatch.setattr(
        hc,
        "Storage",
        lambda dsn: type(
            "S",
            (),
            {
                "load_ssi_token": lambda self: {
                    "refresh_token_expires_at": fixed_now.timestamp() + 7200
                },
                "read_position_sync_ts": lambda self, account_no: sync_ts,
            },
        )(),
    )
    _fresh_job_logs(logs_dir, fixed_now)
    rc = hc.main(["--logs-dir", str(logs_dir)])
    return rc, sent


def _expected_real_order_account() -> str:
    """Đọc real_order_account từ config/config.yaml giống cách heartbeat_check đọc (Brief 152 Việc 3)."""
    import yaml

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["real_order_account"]


def test_main_alerts_when_position_sync_stale(monkeypatch, tmp_path):
    """2D qua DUONG DUNG TIN NHAN: moc dong bo 20 phut truoc (nguong 15) ->
    dung MOT tin [CRITICAL] chua ten tai khoan va so phut."""
    rc, sent = _run_main_with_position_sync(
        monkeypatch, tmp_path, datetime(2026, 8, 14, 9, 40, tzinfo=TZ)
    )  # 20 phut truoc fixed_now 10:00
    assert rc == 1, f"phai bao khi vi the dong bo cu, rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    assert len(sent) == 1, f"dung mot tin, thuc te: {sent}"
    msg = sent[0]
    assert "[CRITICAL]" in msg, f"phai la CRITICAL, thuc te: {msg}"
    assert _expected_real_order_account() in msg, f"tin nhan phai chua ten tai khoan, thuc te: {msg}"
    assert "20 phút" in msg, f"tin nhan phai chua so phut, thuc te: {msg}"


def test_main_never_synced_message_has_no_arithmetic(monkeypatch, tmp_path):
    """2D: chua tung dong bo (sync_ts=None) -> tin RIENG, KHONG dung
    `now - sync_ts` (bai hoc FEE-ALARM-2 Loi 1: chuong bao khong duoc nem
    exception dung luc can nhat)."""
    rc, sent = _run_main_with_position_sync(monkeypatch, tmp_path, None)
    assert rc == 1, f"phai bao khi chua tung dong bo, rc={rc}"
    assert sent, "phai gui tin nhan Telegram"
    msg = sent[0]
    assert "[CRITICAL]" in msg
    assert _expected_real_order_account() in msg, f"tin nhan phai chua ten tai khoan, thuc te: {msg}"
    assert (
        "chưa từng đồng bộ" in msg
    ), f"tin nhan phai noi ro ca chua-dong-bo, thuc te: {msg}"


def test_main_prints_message_to_stdout_before_sending(monkeypatch, capsys, tmp_path):
    """Brief 2026-09-01 (dot 3) Task B: khi co canh bao, noi dung phai duoc in
    ra stdout — de log tai cho co ly do, khong phai chi EXIT=1 (chuong bao
    khong de lai dau vet = chuong nua voi)."""
    rc, sent = _run_main_with_position_sync(
        monkeypatch, tmp_path, datetime(2026, 8, 14, 9, 40, tzinfo=TZ)
    )  # 20 phut truoc fixed_now 10:00
    captured = capsys.readouterr()
    assert rc == 1
    assert sent, "phai gui Telegram"
    assert (
        "[CRITICAL]" in captured.out
    ), f"stdout phai chua noi dung canh bao, thuc te: {captured.out!r}"
    assert _expected_real_order_account() in captured.out
    # stdout phai giong noi dung da gui Telegram
    assert (
        captured.out.strip() == sent[0]
    ), f"stdout phai bang noi dung gui Telegram, thuc te stdout={captured.out!r} sent={sent[0]!r}"


def test_main_still_sends_telegram_when_stdout_cannot_encode(monkeypatch, tmp_path):
    """Chuong bao khong duoc chet vi khong in duoc.

    Su co that 01/09: scheduled task chuyen huong stdout ra file, Python chon
    cp1252, ky tu "dữ" trong "dữ lieu ngung chay" nem UnicodeEncodeError NGAY
    TRUOC send_telegram. Nam lan chay 13:00-13:17 khong gui duoc gi, dung luc
    feed dang chet. capsys bat stdout bang utf-8 nen test cu KHONG bat duoc —
    test nay tiem thang mot stdout tu choi ma hoa.
    """

    class RefusingStdout:
        encoding = "cp1252"

        def write(self, text):
            if any(ord(c) > 127 for c in text):
                raise UnicodeEncodeError("charmap", text, 0, 1, "khong ma hoa duoc")
            return len(text)

        def flush(self):
            pass

        def reconfigure(self, **kwargs):
            raise OSError("khong reconfigure duoc")

    monkeypatch.setattr(sys, "stdout", RefusingStdout())
    rc, sent = _run_main_with_position_sync(
        monkeypatch, tmp_path, datetime(2026, 8, 14, 9, 40, tzinfo=TZ)
    )
    assert rc == 1, f"van phai bao, rc={rc}"
    assert sent, "stdout hong KHONG duoc lam mat tin nhan Telegram"
    assert "[CRITICAL]" in sent[0]


def test_ngay_le_khong_bao_lao():
    """Su co 01/09/2026: nghi Quoc khanh, khong phien nao, nhung 2A no moi 5
    phut suot ca ngay vi bar_stale/token_expiry_status bo qua danh sach ngay
    nghi. Duong tinh gia lap lai thi lan sau khong ai doc canh bao nua.
    """
    le = date(2026, 9, 1)
    giua_phien = datetime(2026, 9, 1, 10, 0, tzinfo=TZ)  # thu Ba, trong khung 2A

    # Khong khai bao ngay nghi -> van bao (hanh vi cu, giu lam moc doi chieu)
    assert bar_stale(None, giua_phien) is True
    # Khai bao roi -> im
    assert (
        bar_stale(None, giua_phien, holidays=frozenset({le})) is False
    ), "ngay nghi thi khong duoc bao du lieu ngung chay"

    # 2B cung phai im, ca trong khung tien-phien 8:00-8:59
    tien_phien = datetime(2026, 9, 1, 8, 30, tzinfo=TZ)
    assert token_expiry_status(None, tien_phien) == "CRITICAL"
    assert (
        token_expiry_status(None, tien_phien, frozenset({le})) is None
    ), "ngay nghi thi khong duoc nhac token o khung tien-phien"


# ============ Brief Đợt 10 Task 4: Cảnh báo cạn lịch nghỉ lễ ============


def test_holiday_exhaustion_before_october_no_alarm():
    """Trường hợp 1: now = 15/09/2026, lịch chỉ có ngày đã qua -> KHÔNG cảnh báo (chưa tới 01/10)."""
    now = datetime(2026, 9, 15, 10, 0, tzinfo=TZ)
    past_holidays = frozenset({date(2026, 1, 1), date(2026, 9, 2)})
    assert check_holiday_exhaustion(past_holidays, now) is None


def test_holiday_exhaustion_after_october_past_holidays_alarms():
    """Trường hợp 2: now = 02/10/2026, lịch chỉ có ngày đã qua -> CÓ cảnh báo [WARN]."""
    now = datetime(2026, 10, 2, 10, 0, tzinfo=TZ)
    past_holidays = frozenset({date(2026, 1, 1), date(2026, 9, 2)})
    result = check_holiday_exhaustion(past_holidays, now)
    assert result is not None
    assert "[WARN]" in result
    assert "lịch nghỉ lễ trong config/config.yaml đã cạn" in result
    assert "HOSE/HNX" in result


def test_holiday_exhaustion_after_october_with_future_holiday_no_alarm():
    """Trường hợp 3: now = 02/10/2026, lịch có 01/01/2027 -> KHÔNG cảnh báo."""
    now = datetime(2026, 10, 2, 10, 0, tzinfo=TZ)
    holidays_with_next_year = frozenset({date(2026, 9, 2), date(2027, 1, 1)})
    assert check_holiday_exhaustion(holidays_with_next_year, now) is None


def test_holiday_exhaustion_after_october_empty_holidays_alarms():
    """Trường hợp 4: now = 02/10/2026, lịch rỗng hoàn toàn -> CÓ cảnh báo [WARN]."""
    now = datetime(2026, 10, 2, 10, 0, tzinfo=TZ)
    empty_holidays = frozenset()
    result = check_holiday_exhaustion(empty_holidays, now)
    assert result is not None
    assert "[WARN]" in result


# --- Brief 145: duong dan state/log tiem duoc, mac dinh giu nguyen cho cron ---


def test_mac_dinh_duong_dan_cho_cron_khong_doi():
    import scripts.heartbeat_check as hc

    args = hc.build_parser().parse_args([])
    assert args.logs_dir == hc.DEFAULT_LOGS_DIR
    assert args.state_file is None  # -> <logs-dir>/.schedule_health_state.json
    assert (
        os.path.join(args.logs_dir, hc.SCHEDULE_STATE_NAME)
        == hc.DEFAULT_SCHEDULE_STATE_FILE
    )
    assert os.path.basename(hc.DEFAULT_LOGS_DIR) == "logs"


def test_main_ghi_trang_thai_vao_thu_muc_tam_khong_phai_logs_that(
    monkeypatch, tmp_path
):
    rc, _ = _run_main_with_ledger(
        monkeypatch, tmp_path, (99_000_000.0, 0.0), [(1_000.0, 1_000)]
    )
    assert rc == 0
    assert (tmp_path / ".schedule_health_state.json").is_file()


# --- Brief 149: Chống lệch giờ và đối chiếu lịch canh với DEPLOYMENT.md §9 ---


def test_khong_canh_reasons_contain_no_hardcoded_times():
    """Brief 149: Không lý do nào trong KHONG_CANH được chứa giờ chạy cụ thể (tránh lệch với DEPLOYMENT.md §9)."""
    import re

    import scripts.heartbeat_check as hc

    time_pattern = re.compile(r"\b\d{1,2}:\d{2}\b")
    violations = {
        job: reason
        for job, reason in hc.KHONG_CANH.items()
        if time_pattern.search(reason)
    }
    assert not violations, f"KHONG_CANH chứa giờ cụ thể: {violations}"


def verify_schedule_watch_jobs_against_deployment_cron(deployment_path=None):
    """Brief 149: Đối chiếu 5 job canh 24/7 trong SCHEDULE_WATCH_JOBS với dòng cron trong DEPLOYMENT.md §9."""
    import re
    from pathlib import Path

    import scripts.heartbeat_check as hc

    path = (
        Path(deployment_path)
        if deployment_path is not None
        else Path(hc.DEFAULT_LOGS_DIR).parent / "DEPLOYMENT.md"
    )
    text = path.read_text(encoding="utf-8")

    # Trích xuất biểu thức cron của các dòng gọi sched.sh <branch>
    # Dòng cron trong DEPLOYMENT.md có dạng:
    # <expr> cd /opt/trading && scripts/sched.sh <branch>
    cron_pattern = re.compile(
        r"^([0-9*/,-]+\s+[0-9*/,-]+\s+[0-9*/,-]+\s+[0-9*/,-]+\s+[0-9*/,-]+)\s+cd\s+/opt/trading\s+&&\s+scripts/sched\.sh\s+([a-zA-Z0-9_-]+)",
        re.MULTILINE,
    )
    cron_map = {branch: expr.strip() for expr, branch in cron_pattern.findall(text)}

    expected_cron_features = {
        "container-health": "*/10",
        "disk-check": "*/6",
        "backup": "0 2 * * *",
        "orderbook-backup": "30 2 * * *",
        "backup-check": "0 3 * * *",
    }

    for job_name, expected in expected_cron_features.items():
        assert job_name in cron_map, f"Thiếu dòng cron cho {job_name} trong {path.name} §9"
        cron_expr = cron_map[job_name]
        if expected.startswith("*/"):
            assert expected in cron_expr, (
                f"Job {job_name} kỳ vọng cron chứa '{expected}', nhưng trong {path.name} là '{cron_expr}'"
            )
        else:
            assert cron_expr == expected, (
                f"Job {job_name} kỳ vọng cron '{expected}', nhưng trong {path.name} là '{cron_expr}'"
            )


def test_schedule_watch_jobs_match_deployment_cron():
    """Brief 149: Giờ gốc của 5 job canh 24/7 phải khớp đúng dòng cron tương ứng trong DEPLOYMENT.md §9."""
    verify_schedule_watch_jobs_against_deployment_cron()


# =============================================================================
# Brief 155: Gửi Telegram hỏng không được ăn mất trạng thái "đã báo"
# =============================================================================
from scripts._alert_common import send_with_outbox


def test_send_with_outbox_success(tmp_path):
    """Việc 2: send_with_outbox gửi thành công -> trả True, không tạo file outbox."""
    delivered = []
    outbox_file = tmp_path / "alert_outbox_test.jsonl"
    ok = send_with_outbox(
        "Cảnh báo test", send=lambda msg: delivered.append(msg) or True, outbox_path=outbox_file
    )
    assert ok is True
    assert delivered == ["Cảnh báo test"]
    assert not outbox_file.exists()


def test_send_with_outbox_failure_enqueues(tmp_path):
    """Việc 2: send_with_outbox gửi hỏng (send trả False) -> trả False, xếp hàng vào outbox."""
    outbox_file = tmp_path / "alert_outbox_test.jsonl"
    ok = send_with_outbox("Cảnh báo hỏng", send=lambda msg: False, outbox_path=outbox_file)
    assert ok is False
    assert outbox_file.exists()
    lines = [ln for ln in outbox_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["text"] == "Cảnh báo hỏng"
    assert "emitted_at" in record


def test_send_with_outbox_flushes_old_before_new(tmp_path):
    """Việc 2: Tin cũ trong hàng đợi đi TRƯỚC tin mới khi flush()."""
    outbox_file = tmp_path / "alert_outbox_test.jsonl"
    # Lần 1: gửi hỏng -> tin 1 vào hàng đợi
    send_with_outbox("Tin cũ số 1", send=lambda msg: False, outbox_path=outbox_file)
    assert outbox_file.exists()

    # Lần 2: mạng phục hồi -> tin cũ được flush TRƯỚC tin mới
    calls = []

    def tracker_send(msg):
        calls.append(msg)
        return True

    ok = send_with_outbox("Tin mới số 2", send=tracker_send, outbox_path=outbox_file)
    assert ok is True
    assert len(calls) == 2
    assert "Tin cũ số 1" in calls[0]
    assert "[GỬI TRỄ" in calls[0]
    assert calls[1] == "Tin mới số 2"
    # Outbox đã được làm sạch
    assert not outbox_file.exists() or not outbox_file.read_text(encoding="utf-8").strip()


def test_send_with_outbox_pending_prints(tmp_path, capsys):
    """Việc 2: In số tin còn tồn (pending) khi khác 0 để log ghi nhận nợ tin."""
    outbox_file = tmp_path / "alert_outbox_test.jsonl"
    send_with_outbox("Nợ tin 1", send=lambda msg: False, outbox_path=outbox_file)
    captured = capsys.readouterr()
    assert "[HANG DOI]" in captured.out
    assert "Đang nợ 1 cảnh báo" in captured.out


def test_send_with_outbox_send_raises_enqueues(tmp_path):
    """Việc 2: send ném URLError -> không chết, xếp hàng và trả False."""
    outbox_file = tmp_path / "alert_outbox_test.jsonl"

    def broken_send(msg):
        raise urllib.error.URLError("DNS resolution failed")

    ok = send_with_outbox("Tin ném lỗi", send=broken_send, outbox_path=outbox_file)
    assert ok is False
    assert outbox_file.exists()


def _setup_heartbeat_stale_env(monkeypatch, logs_dir, fixed_now=None, stale_job="container-health"):
    """Dàn dựng môi trường heartbeat với một job theo lịch bị stale."""
    import scripts.heartbeat_check as hc

    if fixed_now is None:
        fixed_now = datetime(2026, 8, 14, 10, 0, tzinfo=TZ)

    monkeypatch.setenv("DB_DSN", "postgresql://fake:5432/trading")

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    class FakeCur:
        def __init__(self, result=None, rows=None):
            self._result = result
            self._rows = rows or []

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._result

    class FakeConn:
        def execute(self, *a, **k):
            q = str(a[0])
            if "FROM heartbeat" in q:
                return FakeCur(
                    rows=[
                        ("collector", fixed_now - timedelta(seconds=30)),
                        ("engine", fixed_now - timedelta(seconds=45)),
                    ]
                )
            if "max(ts) FROM bars" in q:
                return FakeCur(result=(fixed_now - timedelta(minutes=2),))
            if "FROM engine_state" in q:
                return FakeCur(result=None)
            if "FROM positions" in q:
                return FakeCur(rows=[])
            return FakeCur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn())
    monkeypatch.setattr(
        hc,
        "Storage",
        lambda dsn: type(
            "S",
            (),
            {
                "load_ssi_token": lambda self: {
                    "refresh_token_expires_at": fixed_now.timestamp() + 7200
                },
                "read_position_sync_ts": lambda self, account_no: fixed_now - timedelta(minutes=2),
            },
        )(),
    )

    _fresh_job_logs(logs_dir, fixed_now)
    # Làm cho stale_job bị quá hạn (stale)
    cfg = hc.SCHEDULE_WATCH_JOBS[stale_job]
    old_time = fixed_now - timedelta(seconds=cfg.max_age_seconds + 300)
    (logs_dir / cfg.log_file).write_text(
        f"{old_time.strftime('%Y-%m-%d %H:%M:%S')} {cfg.label} start\n",
        encoding="utf-8",
    )


def test_heartbeat_case_a_send_failure_does_not_save_state(monkeypatch, tmp_path, capsys):
    """Ca A: Gửi hỏng (send_telegram trả False) -> KHÔNG lưu trạng thái, stdout có dấu vết, exit 1."""
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME
    assert not state_file.exists()

    monkeypatch.setattr(hc, "send_telegram", lambda msg: False)

    rc = hc.main(["--logs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert rc == 1
    # File trạng thái KHÔNG được tạo/đổi
    assert not state_file.exists(), "Trạng thái không được lưu khi gửi Telegram hỏng"
    # Stdout có dấu vết gửi hỏng
    assert "GUI TELEGRAM HONG" in captured.out
    # Đã vào hàng đợi outbox
    outbox_file = tmp_path / hc.HEARTBEAT_OUTBOX_NAME
    assert outbox_file.exists()


def test_heartbeat_case_b_subsequent_run_still_alerts_and_saves_state(monkeypatch, tmp_path):
    """Ca B: Ngay sau Ca A, gửi True -> vẫn gửi cảnh báo NGỪNG CHẠY, trạng thái được lưu."""
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME

    # Ca A: gửi hỏng
    monkeypatch.setattr(hc, "send_telegram", lambda msg: False)
    rc1 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc1 == 1
    assert not state_file.exists()

    # Ca B: chạy lại ngay sau Ca A với send_telegram trả True
    delivered = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: delivered.append(msg) or True)

    rc2 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc2 == 1
    # Vẫn gửi cảnh báo NGỪNG CHẠY (không bị nuốt thành 'đã báo trước đó')
    assert any("NGỪNG CHẠY" in m for m in delivered)
    assert any("container-health" in m for m in delivered)
    # Trạng thái ĐƯỢC lưu
    assert state_file.exists()
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["container-health"]["status"] == "stale"


def test_heartbeat_case_c_success_preserves_anti_spam_on_second_run(monkeypatch, tmp_path):
    """Ca C: Gửi được (True), rồi chạy lần hai -> lần hai KHÔNG gửi lại (chống lặp)."""
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME

    delivered_1 = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: delivered_1.append(msg) or True)

    # Lần 1: gửi thành công
    rc1 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc1 == 1
    assert len(delivered_1) >= 1
    assert state_file.exists()

    # Lần 2: chạy lại khi job vẫn đang stale -> chống lặp, không gửi lại
    delivered_2 = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: delivered_2.append(msg) or True)

    rc2 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc2 == 0  # Không có cảnh báo mới -> exit 0
    assert len(delivered_2) == 0, "Lần hai không được gửi lại cảnh báo đã báo"


def test_heartbeat_case_d_send_raises_does_not_crash_or_save_state(monkeypatch, tmp_path, capsys):
    """Ca D: send_telegram ném URLError -> không crash, không lưu trạng thái, có dấu vết, exit 1."""
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME

    def broken_send(msg):
        raise urllib.error.URLError("<urlopen error [Errno 11001] getaddrinfo failed>")

    monkeypatch.setattr(hc, "send_telegram", broken_send)

    rc = hc.main(["--logs-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert rc == 1
    assert not state_file.exists(), "Không được lưu trạng thái khi send_telegram ném lỗi"
    assert "GUI TELEGRAM HONG" in captured.out
    # Tin nhắn được xếp vào hàng đợi an toàn
    outbox_file = tmp_path / hc.HEARTBEAT_OUTBOX_NAME
    assert outbox_file.exists()


def test_heartbeat_end_to_end_recipient_receives_queued_messages(monkeypatch, tmp_path):
    """Test đầu-cuối: Lần 1 gửi hỏng, lần 2 gửi được -> người nhận được CẢ tin của lần 1."""
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, tmp_path)

    # Lần 1: hỏng mạng (send_telegram trả False)
    monkeypatch.setattr(hc, "send_telegram", lambda msg: False)
    rc1 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc1 == 1

    # Lần 2: mạng phục hồi
    all_received = []

    def tracking_send(msg):
        all_received.append(msg)
        return True

    monkeypatch.setattr(hc, "send_telegram", tracking_send)
    rc2 = hc.main(["--logs-dir", str(tmp_path)])
    assert rc2 == 1

    # Kiểm tra người nhận nhận được cả 2 tin: tin cũ (lần 1) được flush và tin mới (lần 2)
    assert len(all_received) >= 2
    assert any("[GỬI TRỄ" in m and "container-health" in m for m in all_received)
    # Outbox được dọn sạch
    outbox_file = tmp_path / hc.HEARTBEAT_OUTBOX_NAME
    assert not outbox_file.exists() or not outbox_file.read_text(encoding="utf-8").strip()
def _setup_db_unreachable(monkeypatch, logs_dir):
    """Audit dot 155: nhu _setup_heartbeat_stale_env nhung psycopg.connect NEM.

    Nhanh "khong doc duoc DB" la nhanh nổ đúng lúc postgres chet — luc can canh bao
    nhat. Claude pha thu: tra nhanh nay ve "luu trang thai vo dieu kien" thi ca 52
    test cu van xanh, nen nhanh nay chua duoc ghim.
    """
    import scripts.heartbeat_check as hc

    _setup_heartbeat_stale_env(monkeypatch, logs_dir)

    def boom(*a, **k):
        raise OSError("postgres khong ket noi duoc")

    monkeypatch.setattr(hc.psycopg, "connect", boom)


def test_heartbeat_db_error_send_failure_does_not_save_state(
    monkeypatch, tmp_path, capsys
):
    """Audit dot 155: nhanh loi doc DB — gui hong thi KHONG an mat trang thai."""
    import scripts.heartbeat_check as hc

    _setup_db_unreachable(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME
    assert not state_file.exists()

    monkeypatch.setattr(hc, "send_telegram", lambda msg: False)

    rc = hc.main(["--logs-dir", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 1
    assert (
        not state_file.exists()
    ), "nhanh loi doc DB: gui hong thi KHONG duoc luu trang thai canh lich"
    assert "GUI TELEGRAM HONG" in out


def test_heartbeat_db_error_alert_includes_stale_job(monkeypatch, tmp_path):
    """Audit dot 155: nhanh loi doc DB phai gui CA canh bao job ngung chay.

    Truoc dot 155, nhanh nay gui DUY NHAT err_msg roi van luu trang thai, nen canh
    bao "job ngung chay" bi an mat vinh vien khi DB cung dang hong.
    """
    import scripts.heartbeat_check as hc

    _setup_db_unreachable(monkeypatch, tmp_path)
    state_file = tmp_path / hc.SCHEDULE_STATE_NAME

    sent: list[str] = []

    def ok_send(msg):
        sent.append(msg)
        return True

    monkeypatch.setattr(hc, "send_telegram", ok_send)

    rc = hc.main(["--logs-dir", str(tmp_path)])

    assert rc == 1
    assert sent, "phai gui mot tin"
    body = "\n".join(sent)
    assert "không đọc được DB" in body, f"phai noi DB hong, thuc te: {body}"
    assert (
        "NGỪNG CHẠY" in body
    ), f"phai gui ca canh bao job ngung chay, khong duoc an mat: {body}"
    assert state_file.exists(), "gui duoc thi moi luu trang thai"
