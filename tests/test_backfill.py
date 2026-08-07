import json
from datetime import date, datetime, timedelta
from pathlib import Path

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
