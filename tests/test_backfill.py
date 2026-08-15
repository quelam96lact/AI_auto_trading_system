import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from trading.calendar_vn import TZ
from trading.collector.backfill import (
    SSIRestClient,
    _ohlc_rows_to_bars,
    parse_intraday_response,
    run_backfill,
)
from trading.models import Bar

FIXTURES = Path(__file__).parent / "fixtures"


class FakeStorage:
    def __init__(self, last=None):
        self.last = last
        self.bars, self.daily = [], []

    def last_bar_ts(self, symbol):
        return self.last

    def write_bars(self, bars):
        self.bars.extend(bars)

    def write_daily(self, bars):
        self.daily.extend(bars)


class FakeClient:
    async def daily_ohlc(self, symbol, frm, to):
        return [Bar(symbol, datetime(2026, 7, 14, tzinfo=TZ), 1, 2, 1, 2, 10)]

    async def intraday_ohlc(self, symbol, frm, to):
        return [
            Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10),
            Bar(symbol, datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 2, 3, 2, 3, 20),
        ]


async def test_run_backfill_writes_missing_bars():
    st = FakeStorage(last=datetime(2026, 7, 15, 8, 55, tzinfo=TZ))
    counts = await run_backfill(st, FakeClient(), ["VCB"], today=date(2026, 7, 15))
    assert counts["VCB"] == 2 and len(st.bars) == 2 and len(st.daily) == 1


class FailingDailyClient:
    """Mô phỏng đúng lỗi thật quan sát 2026-08-07: get_ohlc_5minute_historical
    (intraday) trả 200 OK bình thường, nhưng get_ohlc_1day_historical (daily)
    trả 500 cho 1 mã cụ thể."""

    def __init__(self, fail_symbol: str):
        self.fail_symbol = fail_symbol
        self.intraday_calls: list[str] = []

    async def daily_ohlc(self, symbol, frm, to):
        if symbol == self.fail_symbol:
            raise RuntimeError("API error: 500")
        return [Bar(symbol, datetime(2026, 7, 14, tzinfo=TZ), 1, 2, 1, 2, 10)]

    async def intraday_ohlc(self, symbol, frm, to):
        self.intraday_calls.append(symbol)
        return [Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10)]


async def test_run_backfill_continues_after_one_symbol_fails():
    st = FakeStorage(last=None)
    client = FailingDailyClient(fail_symbol="VCB")

    counts = await run_backfill(
        st, client, ["VCB", "HPG", "TCB"], today=date(2026, 8, 7)
    )

    # Bug thật 2026-08-07: 1 try/except bọc ngoài TOÀN BỘ vòng lặp khiến VCB
    # lỗi giữa chừng làm HPG/TCB không bao giờ được gọi tới - production chỉ
    # backfill được VCB (nhờ intraday_ohlc chạy trước dòng lỗi), HPG/TCB có 0 bar.
    assert client.intraday_calls == [
        "VCB",
        "HPG",
        "TCB",
    ], "phai goi intraday_ohlc cho CA 3 ma, khong duoc dung lai o VCB"
    assert counts.get("HPG") == 1
    assert counts.get("TCB") == 1


class RecordingClient:
    """Ghi lai TUNG loi goi de kiem nhanh daily_only co thuc su bo intraday."""

    def __init__(self):
        self.intraday_calls: list[str] = []
        self.daily_calls: list[tuple[str, date, date]] = []

    async def daily_ohlc(self, symbol, frm, to):
        self.daily_calls.append((symbol, frm, to))
        return [Bar(symbol, datetime(2026, 8, 14, tzinfo=TZ), 1, 2, 1, 2, 10)]

    async def intraday_ohlc(self, symbol, frm, to):
        self.intraday_calls.append(symbol)
        return [Bar(symbol, datetime(2026, 8, 14, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10)]


async def test_daily_only_skips_intraday_entirely():
    """MARGIN-2: ma DANG NAM GIU (CAP/HCM/SSI/TCX) khong giao dich nen khong
    can bar 5m — chi can gia dong cua de dinh gia NAV. Keo intraday cho chung
    la lang phi loi goi API va ghi rac vao bang `bars`."""
    st = FakeStorage(last=None)
    client = RecordingClient()

    counts = await run_backfill(
        st, client, ["CAP"], today=date(2026, 8, 14), daily_only=True
    )

    assert client.intraday_calls == [], "daily_only=True KHONG duoc goi intraday_ohlc"
    assert st.bars == [], "daily_only=True KHONG duoc ghi vao bang bars (5m)"
    assert len(st.daily) == 1, "van phai ghi bar daily"
    assert counts["CAP"] == 1, "counts dem so bar daily da ghi khi daily_only"


async def test_daily_only_uses_fixed_window_not_last_bar_ts():
    """`last_bar_ts` doc bang `bars` (5m) — ma khong giao dich thi VINH VIEN
    None, nen cua so 7 ngay cua nhanh cu chi dung do tinh co. daily_only dung
    cua so co dinh 10 ngay, khong phu thuoc bang 5m."""
    st = FakeStorage(last=None)
    client = RecordingClient()

    await run_backfill(st, client, ["HCM"], today=date(2026, 8, 14), daily_only=True)

    symbol, frm, to = client.daily_calls[0]
    assert symbol == "HCM"
    assert to == date(2026, 8, 14)
    assert frm == date(2026, 8, 4), "cua so co dinh 10 ngay tinh nguoc tu today"


async def test_default_is_not_daily_only():
    """Hanh vi mac dinh KHONG doi: 3 caller hien tai (backfill._run,
    main.housekeeping_tick, main.run) goi khong kem tham so nay."""
    st = FakeStorage(last=None)
    client = RecordingClient()

    await run_backfill(st, client, ["VCB"], today=date(2026, 8, 14))

    assert client.intraday_calls == ["VCB"], "mac dinh phai VAN keo intraday"


class FakeMarketDataDaily:
    """Bat params thuc te truyen vao get_ohlc_1day_historical de kiem tra format."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.market_data = self

    async def get_ohlc_1day_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        self.calls.append((symbol, from_str, to_str))
        return []


async def test_daily_ohlc_includes_time_component_in_date_params():
    # Bug that xac nhan 2026-08-07 (test truc tiep len SSI API bang token
    # dang song): daily OHLC cung yeu cau from/to co "HH:MM:SS" giong het
    # intraday (_fmt_intraday) - thieu gio bi server tra "400213 Invalid
    # Date/Timestamp" (SDK boc thanh HTTP 500). _fmt_day() cu chi format
    # "%Y/%m/%d" khong co gio -> tat ca 3 ma (VCB/HPG/TCB) deu 500 tren daily,
    # khong phai loi rieng cua VCB nhu tuong ban dau (bug loop-abort cu che mat).
    client = SSIRestClient.__new__(SSIRestClient)  # khong can cfg/storage that
    fake = FakeMarketDataDaily()
    client._data = fake

    await client.daily_ohlc("VCB", date(2026, 7, 31), date(2026, 8, 7))

    _, frm_str, to_str = fake.calls[0]
    assert frm_str == "2026/07/31 00:00:00", "thieu gio -> SSI tra loi 400213"
    assert to_str == "2026/08/07 23:59:59", "thieu gio -> SSI tra loi 400213"


class _DailyRow:
    """Gia lap OHLCData that SSI tra ve cho timeFrame=1d: tradingDate KHONG
    kem gio (khac intraday), xac nhan that 2026-08-07 qua call truc tiep len
    API: {"symbol":"VCB","tradingDate":"2026/08/07","open":"58700",...}."""

    def __init__(self):
        self.symbol = "VCB"
        self.trading_date = "2026/08/07"
        self.open_price = "58700"
        self.high_price = "60800"
        self.low_price = "58700"
        self.close_price = "59700"
        self.volume = "6522200"


def test_ohlc_rows_to_bars_handles_daily_trading_date_without_time():
    # Bug that xac nhan 2026-08-07: sau khi fix loi 400213 o tren, daily OHLC
    # tra 200 OK nhung tradingDate chi la "YYYY/MM/DD" (khong co gio) trong khi
    # _parse_trading_date cu chi chap nhan "YYYY/MM/DD HH:mm:ss" cua intraday ->
    # crash "time data '2026/08/07' does not match format '%Y/%m/%d %H:%M:%S'".
    bars = _ohlc_rows_to_bars([_DailyRow()])
    assert bars[0].ts == datetime(2026, 8, 7, tzinfo=TZ)


def test_parse_intraday_fixture():
    raw = json.loads((FIXTURES / "ssi_intraday_ohlc.json").read_text(encoding="utf-8"))
    bars = parse_intraday_response(raw)
    assert bars and all(b.ts.tzinfo is not None for b in bars)
    assert all(b.ts.minute % 5 == 0 for b in bars)  # đã chuẩn hóa 5m


def test_ohlc_rows_to_bars_from_real_fixture():
    from ssi_sdk.models import OHLCData

    raw = json.loads(
        (FIXTURES / "ssi_sdk_ohlc_5m_vcb.json").read_text(encoding="utf-8")
    )
    rows = OHLCData.from_list(raw["data"])
    bars = _ohlc_rows_to_bars(rows)

    assert len(bars) == 230
    assert all(b.ts.tzinfo is not None for b in bars)
    # dòng đầu fixture: 2026/07/24 14:45:00, open=54100 (xem file fixture)
    first = next(b for b in bars if b.ts == datetime(2026, 7, 24, 14, 45, tzinfo=TZ))
    assert first.symbol == "VCB" and first.open == 54100 and first.volume == 189100


def _gen_ohlc_rows(symbol: str, days: list[date], per_day: int = 60):
    from ssi_sdk.models import OHLCData

    rows = []
    for d in days:
        for i in range(per_day):
            ts = datetime(d.year, d.month, d.day, 9, 0) + timedelta(minutes=5 * i)
            rows.append(
                OHLCData(
                    symbol=symbol,
                    trading_date=ts.strftime("%Y/%m/%d %H:%M:%S"),
                    open_price=10,
                    high_price=11,
                    low_price=9,
                    close_price=10,
                    volume=100,
                    value=1000,
                )
            )
    return rows


class FakeMarketData:
    """Mô phỏng đúng hành vi thật đã xác nhận (commit 95f563f): pageIndex của
    get_ohlc_5minute_historical KHÔNG phải OFFSET cursor chuẩn — với 1 khoảng
    ngày rộng (>7 ngày, tương tự cách _paged_intraday cũ gọi thẳng frm..to
    không chunk), server trả lặp lại gần như y hệt cửa sổ dữ liệu mới nhất
    ở mọi page thay vì tiến dần về dữ liệu cũ hơn. Với khoảng ngày hẹp
    (<=7 ngày, cách chunk-theo-ngày dùng để fix) trả đúng dữ liệu của đúng
    khoảng đó — đây là hành vi SSI thật quan sát được, không phải suy đoán.
    """

    def __init__(self, rows):
        self.rows = rows
        self._big_window_calls = 0
        self.market_data = self

    async def get_ohlc_5minute_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        frm_d = datetime.strptime(from_str, "%Y/%m/%d %H:%M:%S").date()
        to_d = datetime.strptime(to_str, "%Y/%m/%d %H:%M:%S").date()
        window = sorted(
            (
                r
                for r in self.rows
                if frm_d
                <= datetime.strptime(r.trading_date, "%Y/%m/%d %H:%M:%S").date()
                <= to_d
            ),
            key=lambda r: r.trading_date,
        )
        if (to_d - frm_d).days > 7:
            # cách gọi cũ (không chunk): mô phỏng server "hết ngân sách" sau
            # vài page lặp lại cùng cửa sổ dữ liệu mới nhất
            self._big_window_calls += 1
            if self._big_window_calls > 2:
                return []
            return window[-size:]
        return window[:size]


async def test_paged_intraday_dedupes_when_ssi_page_index_overlaps():
    symbol = "VCB"
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(20)]
    rows = _gen_ohlc_rows(symbol, days, per_day=60)  # 1200 dòng: 60/ngày x 20 ngày
    fake_data = FakeMarketData(rows)

    client = SSIRestClient.__new__(SSIRestClient)  # không cần cfg/storage thật
    result = await client._paged_intraday(fake_data, symbol, days[0], days[-1])

    got_dates = {r.trading_date for r in result}
    expected_dates = {r.trading_date for r in rows}
    assert got_dates == expected_dates, (
        f"mat {len(expected_dates - got_dates)} ban ghi (bug phan trang page cu) "
        f"hoac co du lieu la (bug moi)"
    )
    assert (
        rows[0].trading_date in got_dates
    ), "ban ghi cu nhat trong khoang ngay yeu cau bi mat"


class FakeMarketDataDailyCapped:
    """Mô phỏng hành vi thật SSI (đo 2026-08-09): get_ohlc_1day_historical chặn
    1000 dòng/call và trả CỬA SỔ MỚI NHẤT — gọi 1 lần với khoảng 10 năm chỉ trả
    1000 bar cuối (2021-2025), mất âm thầm 2016-2020."""

    def __init__(self, rows):
        self.rows = rows  # list[OHLCData] daily, trading_date "YYYY/MM/DD"
        self.market_data = self
        self.calls: list[tuple] = []

    async def get_ohlc_1day_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        self.calls.append((from_str, to_str))
        frm_d = datetime.strptime(from_str, "%Y/%m/%d %H:%M:%S").date()
        to_d = datetime.strptime(to_str, "%Y/%m/%d %H:%M:%S").date()
        window = sorted(
            (
                r
                for r in self.rows
                if frm_d
                <= datetime.strptime(r.trading_date, "%Y/%m/%d").date()
                <= to_d
            ),
            key=lambda r: r.trading_date,
        )
        if len(window) > size:
            return window[-size:]  # trần 1000 + cửa sổ mới nhất (hành vi thật)
        return window


def _gen_daily_rows(symbol: str, start: date, end: date):
    from ssi_sdk.models import OHLCData

    rows = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # ~250 phiên/năm, chỉ ngày trong tuần
            rows.append(
                OHLCData(
                    symbol=symbol,
                    trading_date=d.strftime("%Y/%m/%d"),
                    open_price=10,
                    high_price=11,
                    low_price=9,
                    close_price=10,
                    volume=100,
                    value=1000,
                )
            )
        d += timedelta(days=1)
    return rows


async def test_daily_ohlc_chunks_and_keeps_oldest_rows():
    symbol = "VCB"
    start, end = date(2016, 1, 1), date(2025, 12, 31)
    rows = _gen_daily_rows(symbol, start, end)
    fake = FakeMarketDataDailyCapped(rows)
    client = SSIRestClient.__new__(SSIRestClient)
    client._data = fake

    bars = await client.daily_ohlc(symbol, start, end)

    got = {b.ts.date() for b in bars}
    expected = {
        datetime.strptime(r.trading_date, "%Y/%m/%d").date() for r in rows
    }
    assert (
        date(2016, 1, 4) in got
    ), "bar cu nhat (2016) bi mat: daily_ohlc khong chunk theo ngay"
    assert len(bars) == len(rows), (
        f"tong so bar khong khop: got {len(bars)}, expected {len(rows)} "
        f"(mat hoac trung du lieu)"
    )
    assert got == expected


class FakeMarketDataReauth:
    """Mô phỏng access token hết hạn giữa job: lần gọi API đầu tiên raise
    AuthenticationError (SSI dùng class này cho cả 401/403 — xác minh
    rest_client.py:31-42), lần sau thành công."""

    def __init__(self, rows, always_fail: bool = False):
        self.rows = rows
        self.market_data = self
        self.calls = 0
        self.always_fail = always_fail

    async def _maybe_fail(self):
        self.calls += 1
        if self.always_fail or self.calls == 1:
            from ssi_sdk.exceptions import AuthenticationError

            raise AuthenticationError("Authentication failed: 401")

    async def get_ohlc_5minute_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        await self._maybe_fail()
        return self.rows

    async def get_ohlc_1day_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        await self._maybe_fail()
        return self.rows


def _make_reauth_client(fake) -> SSIRestClient:
    """Client với _ensure_data bị giả để đếm số lần re-auth và trả fake data."""
    client = SSIRestClient.__new__(SSIRestClient)
    ensures: list[int] = []

    async def fake_ensure():
        ensures.append(1)
        client._data = fake
        return fake

    client._ensure_data = fake_ensure  # type: ignore[method-assign]
    client._ensures = ensures
    return client


async def test_daily_ohlc_single_call_for_short_range():
    """Ràng buộc collector live: frm cách today ≤ 7 ngày (run_backfill) thì
    chunk 366 ngày phải là no-op — ĐÚNG 1 call, không phải 2 (off-by-one ở
    biên chunk sẽ làm tăng gấp đôi request cho production path)."""
    symbol = "VCB"
    rows = _gen_daily_rows(symbol, date(2026, 8, 1), date(2026, 8, 7))
    fake = FakeMarketDataDailyCapped(rows)
    client = SSIRestClient.__new__(SSIRestClient)
    client._data = fake

    bars = await client.daily_ohlc(symbol, date(2026, 8, 1), date(2026, 8, 7))

    assert len(fake.calls) == 1, (
        f"khoang <= 366 ngay phai dung 1 chunk/1 call, thuc te {len(fake.calls)} "
        f"(off-by-one tai bien chunk)"
    )
    assert len(bars) == len(rows)


async def test_intraday_reauth_once_after_401_then_succeeds():
    from ssi_sdk.models import OHLCData

    rows = [
        OHLCData(
            symbol="VCB",
            trading_date="2026/07/15 09:00:00",
            open_price=10,
            high_price=11,
            low_price=9,
            close_price=10,
            volume=100,
            value=1000,
        )
    ]
    client = _make_reauth_client(FakeMarketDataReauth(rows))
    frm, to = date(2026, 7, 15), date(2026, 7, 15)

    bars = await client.intraday_ohlc("VCB", frm, to)

    assert len(bars) == 1, "call dau 401 -> reauth 1 lan -> phai tra du lieu dung"
    assert len(client._ensures) == 2, "ensure_authenticated phai duoc goi lai dung 1 lan"


async def test_daily_ohlc_also_reauths_on_401():
    from ssi_sdk.models import OHLCData

    rows = [
        OHLCData(
            symbol="VCB",
            trading_date="2026/07/15",
            open_price=10,
            high_price=11,
            low_price=9,
            close_price=10,
            volume=100,
            value=1000,
        )
    ]
    client = _make_reauth_client(FakeMarketDataReauth(rows))

    bars = await client.daily_ohlc("VCB", date(2026, 7, 15), date(2026, 7, 15))

    assert len(bars) == 1, "daily cung phai di qua re-auth khi 401"
    assert len(client._ensures) == 2


async def test_reauth_is_attempted_only_once():
    from ssi_sdk.exceptions import AuthenticationError

    client = _make_reauth_client(FakeMarketDataReauth([], always_fail=True))
    frm, to = date(2026, 7, 15), date(2026, 7, 15)

    with pytest.raises(AuthenticationError):
        await client.intraday_ohlc("VCB", frm, to)

    # refresh_token het han that thi retry vo ich — phai fail to va ro, khong
    # nuot, khong retry vo han; so lan re-auth dung bang 1.
    assert len(client._ensures) == 2, (
        f"re-auth phai dung 1 lan (ensure lan dau + 1 lan sau 401), "
        f"thuc te {len(client._ensures)}"
    )


class FakeMarketDataMultiChunk:
    """Mô phỏng production: mỗi lần ensure_authenticated trả AsyncData MỚI.
    Object cũ bị đóng (closed=True) và RAISE nếu bị dùng lại — đúng thứ
    _reset_auth làm (auth.close()). Chỉ OBJECT ĐẦU TIÊN fail 401 (access token
    hết hạn 1 lần); các object sau (sau re-auth) hoạt động bình thường."""

    def __init__(self, fail_first: bool = False):
        self.closed = False
        self.calls = 0
        self.fail_first = fail_first
        self.market_data = self

    async def close(self):
        self.closed = True

    async def get_ohlc_1day_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        if self.closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        self.calls += 1
        if self.fail_first and self.calls == 1:  # chunk dau -> access token het han
            from ssi_sdk.exceptions import AuthenticationError

            raise AuthenticationError("Authentication failed: 401")
        from ssi_sdk.models import OHLCData

        year = int(from_str[:4])
        return [
            OHLCData(
                symbol=symbol,
                trading_date=f"{year}/01/04",
                open_price=10,
                high_price=11,
                low_price=9,
                close_price=10,
                volume=100,
                value=1000,
            )
        ]


def _make_multi_chunk_client():
    """_ensure_data giả tạo fake MỚI mỗi lần (như production) + set _auth để
    _reset_auth thật sự close object cũ. Chỉ object đầu fail 401."""
    client = SSIRestClient.__new__(SSIRestClient)
    fakes: list[FakeMarketDataMultiChunk] = []
    first_done = False

    async def fake_ensure():
        nonlocal first_done
        f = FakeMarketDataMultiChunk(fail_first=not first_done)
        first_done = True
        fakes.append(f)
        client._data = f
        client._auth = f
        return f

    client._ensure_data = fake_ensure  # type: ignore[method-assign]
    client._fakes = fakes
    return client


async def test_reauth_mid_loop_uses_fresh_data_for_next_chunks():
    """Bug that (Claude repro): 401 o chunk 1 -> _reset_auth close object cu,
    nhung vong lap van giu bien `data` cu -> chunk 2 goi HTTP client da dong
    (RuntimeError). Phai dung data MOI cho cac chunk sau chunk bi 401."""
    client = _make_multi_chunk_client()

    bars = await client.daily_ohlc("VCB", date(2023, 1, 1), date(2025, 12, 31))

    # 3 chunk (2023/2024/2025): chunk 1 bi 401 -> reauth -> chunk 2, 3 phai
    # chay tren data moi, khong duoc dung client da close
    assert len(bars) == 3, f"thieu du lieu sau chunk bi 401: {len(bars)}"
    assert client._fakes[0].closed, "object cu phai bi dong sau 401"
    assert client._fakes[-1] is client._data, "vong lap phai dung data moi nhat"


class FakeMarketDataIntradayCount:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
        self.market_data = self

    async def get_ohlc_5minute_historical(
        self, symbol, from_str, to_str, page=1, size=1000
    ):
        self.calls += 1
        return self.rows


async def test_intraday_single_call_for_short_range():
    """Collector live lui toi da 7 ngay: chunk 7 ngay phai la no-op — dung 1
    call, khong tang request cho production path."""
    from ssi_sdk.models import OHLCData

    rows = [
        OHLCData(
            symbol="VCB",
            trading_date="2026/08/03 09:00:00",
            open_price=10,
            high_price=11,
            low_price=9,
            close_price=10,
            volume=100,
            value=1000,
        )
    ]
    fake = FakeMarketDataIntradayCount(rows)
    client = SSIRestClient.__new__(SSIRestClient)
    client._data = fake

    bars = await client.intraday_ohlc("VCB", date(2026, 8, 1), date(2026, 8, 7))

    assert fake.calls == 1, (
        f"khoang <= 7 ngay phai dung 1 call intraday, thuc te {fake.calls}"
    )
    assert len(bars) == 1


async def test_fetch_with_reauth_logs_on_retry_success(caplog):
    """Re-auth sau 401 phai de lai dau vet: log INFO 're-authenticated after
    AuthenticationError' (lan kiem chung job 900 ma phai suy luan 5 buoc vi
    duong nay khong log gi - plan 2026-08-10-log-fetch-reauth)."""
    from ssi_sdk.models import OHLCData

    rows = [
        OHLCData(
            symbol="VCB",
            trading_date="2026/07/15",
            open_price=10,
            high_price=11,
            low_price=9,
            close_price=10,
            volume=100,
            value=1000,
        )
    ]
    client = _make_reauth_client(FakeMarketDataReauth(rows))

    with caplog.at_level(logging.INFO):
        bars = await client.daily_ohlc("VCB", date(2026, 7, 15), date(2026, 7, 15))

    assert len(bars) == 1
    assert any(
        "re-authenticated after AuthenticationError" in r.message
        and "get_ohlc_1day_historical" in r.message
        for r in caplog.records
    ), "phai co log INFO khi retry thanh cong, kem ten method"


async def test_fetch_with_reauth_no_log_when_first_call_succeeds(caplog):
    """Goi thanh cong ngay lan dau (khong loi) KHONG duoc log — tranh log on
    vo ich tren moi luot goi."""
    from ssi_sdk.models import OHLCData

    rows = [
        OHLCData(
            symbol="VCB",
            trading_date="2026/07/15",
            open_price=10,
            high_price=11,
            low_price=9,
            close_price=10,
            volume=100,
            value=1000,
        )
    ]
    fake = FakeMarketDataReauth(rows)
    fake.calls = 1  # lan goi dau tien thuc su la lan thu 2 -> khong fail
    client = _make_reauth_client(fake)

    with caplog.at_level(logging.INFO):
        bars = await client.daily_ohlc("VCB", date(2026, 7, 15), date(2026, 7, 15))

    assert len(bars) == 1
    assert not any(
        "re-authenticated after AuthenticationError" in r.message
        for r in caplog.records
    ), "khong duoc log khi thanh cong ngay lan dau"
