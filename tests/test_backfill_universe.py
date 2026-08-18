"""Tests cho backfill_universe.backfill_one — progress phải phản ánh độ phủ THẬT.

Bug gốc (2026-08-18): backfill_one ghi `last_done_date = to` bất kể bars chứa
gì, KỂ CẢ RỖNG — rồi lần chạy sau skip vì last_done_date >= to. Lỗ hổng tự
bịt miệng: ghi nhận thành công cho dữ liệu không có.

Phương án: tách hai khái niệm:
- `attempted_until`: ngày đã HỎI API tới (ghi LUÔN sau mỗi lần fetch thành
  công, kể cả rỗng) — skip dựa trên cột này, chống fetch lại mã ít thanh
  khoản vĩnh viễn.
- `last_done_date`: ngày bar THẬT cuối cùng nhận được — KHÔNG tiến khi rỗng
  (nguyên tắc: không ghi nhận độ phủ mình không có).

Nguyên tắc chỉ đạo: KHÔNG BAO GIỜ ghi nhận độ phủ mà mình không có.
"""
from datetime import date, datetime

from scripts.backfill_universe import backfill_one
from trading.calendar_vn import TZ
from trading.models import Bar


def _bar(symbol: str, d: date) -> Bar:
    return Bar(
        symbol,
        datetime(d.year, d.month, d.day, tzinfo=TZ),
        10.0, 11.0, 9.0, 10.5, 1000,
    )


class FakeStorage:
    """Progress lưu trong dict — cùng contract với Storage.get/set_backfill_progress."""

    def __init__(self):
        self.progress: dict[tuple[str, str], dict] = {}
        self.written: list[list[Bar]] = []

    def get_backfill_progress(self, symbol: str, timeframe: str) -> dict | None:
        return self.progress.get((symbol, timeframe))

    def set_backfill_progress(
        self, symbol: str, timeframe: str, last_done_date, status: str,
        error: str | None = None, attempted_until=None,
    ) -> None:
        self.progress[(symbol, timeframe)] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "last_done_date": last_done_date,
            "status": status,
            "error": error,
            "attempted_until": attempted_until,
        }

    def write_daily(self, bars: list[Bar]) -> None:
        self.written.append(bars)


class FakeClient:
    def __init__(self, bars_by_symbol: dict[str, list[Bar]]):
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[tuple[str, date, date]] = []

    async def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        self.calls.append((symbol, frm, to))
        return self.bars_by_symbol.get(symbol, [])


async def _run_backfill_one(storage, client, symbol="SDC", frm=None, to=None):
    """await backfill_one rồi trả (status, detail) — tránh await-slice sai."""
    result = await backfill_one(
        client, storage, symbol, "1d",
        frm or date(2026, 8, 1), to or date(2026, 8, 18), 0,
    )
    return result[1], result[2]


async def test_progress_records_last_real_bar_not_requested_to():
    """API trả bar cuối 05/08 < to 18/08 -> last_done_date = 05/08 (KHÔNG phải
    to), attempted_until = to (đã hỏi tới đó)."""
    storage = FakeStorage()
    client = FakeClient({"SDC": [_bar("SDC", date(2026, 8, 5))]})

    status, _ = await _run_backfill_one(storage, client)

    prog = storage.get_backfill_progress("SDC", "1d")
    assert status == "ok"
    assert prog["last_done_date"] == date(2026, 8, 5), (
        f"last_done_date phai la ngay bar cuoi THUC (05/08), khong phai to (18/08): {prog}"
    )
    assert prog["attempted_until"] == date(2026, 8, 18)


async def test_empty_response_does_not_advance_last_done_date():
    """API trả mảng rỗng -> last_done_date KHÔNG tiến (giữ nguyên), nhưng
    attempted_until = to (đã hỏi — để lần sau không fetch lại vĩnh viễn)."""
    storage = FakeStorage()
    # Lần chạy trước đã có dữ liệu tới 07/08
    storage.set_backfill_progress(
        "SDC", "1d", date(2026, 8, 7), "ok", attempted_until=date(2026, 8, 7)
    )
    client = FakeClient({"SDC": []})  # rỗng

    status, _ = await _run_backfill_one(storage, client)

    prog = storage.get_backfill_progress("SDC", "1d")
    assert status == "ok"
    assert prog["last_done_date"] == date(2026, 8, 7), (
        f"rỗng -> KHÔNG được tiến last_done_date: {prog}"
    )
    assert prog["attempted_until"] == date(2026, 8, 18)


async def test_not_skipped_when_attempted_until_below_to():
    """Lần chạy kế tiếp với to MỚI hơn attempted_until -> KHÔNG skip, fetch tiếp.
    Đây là test bắt cơ chế tự bịt miệng: mã chưa thực sự đủ dữ liệu phải được
    thử lại, không được bỏ qua vĩnh viễn."""
    storage = FakeStorage()
    # Bug cũ: last_done_date = to mặc dù dữ liệu chỉ tới 05/08; attempted_until
    # không tồn tại (None) — mô phỏng dòng progress nói dối từ trước.
    storage.set_backfill_progress("SDC", "1d", date(2026, 8, 10), "ok", attempted_until=None)
    client = FakeClient({"SDC": [_bar("SDC", date(2026, 8, 15))]})

    status, _ = await _run_backfill_one(storage, client)

    assert status != "skip", "mã chưa thực sự đủ dữ liệu (attempted_until None) KHÔNG được skip"
    assert client.calls, "phải gọi API để thử lại mã chưa đủ dữ liệu"
    prog = storage.get_backfill_progress("SDC", "1d")
    assert prog["attempted_until"] == date(2026, 8, 18)


async def test_not_skipped_when_rerunning_same_range_to_repair_gap():
    """Kich ban TU BIT MIENG THAT: dong progress noi doi last_done_date = 10/08
    trong khi du lieu chi toi 05/08. Chay LAI DUNG KHOANG do (to = 10/08) de va
    lo hong — bug cu se skip vinh vien vi last_done_date >= to.

    Test test_not_skipped_when_attempted_until_below_to KHONG bat duoc ca nay:
    no chay voi to = 18/08 (moi hon), nen 10/08 >= 18/08 sai o ca hai ban va
    test pass du logic skip bi hong. Kiem chung 2026-08-19: doi dieu kien skip
    ve last_done_date thi test do VAN XANH, test nay DO."""
    storage = FakeStorage()
    storage.set_backfill_progress("SDC", "1d", date(2026, 8, 10), "ok", attempted_until=None)
    client = FakeClient({"SDC": [_bar("SDC", date(2026, 8, 5))]})

    status, _ = await _run_backfill_one(storage, client, to=date(2026, 8, 10))

    assert status != "skip", "chay lai dung khoang cu de va lo hong KHONG duoc skip"
    assert client.calls, "phai goi API de va lo hong"


async def test_skipped_when_attempted_until_covers_to():
    """Đã hỏi tới to (attempted_until >= to) -> skip — kể cả khi last_done_date
    nhỏ hơn (mã ít thanh khoản, không giao dịch mỗi ngày — không fetch lại
    vĩnh viễn)."""
    storage = FakeStorage()
    storage.set_backfill_progress(
        "SDC", "1d", date(2026, 8, 7), "ok", attempted_until=date(2026, 8, 18)
    )
    client = FakeClient({})  # không được gọi

    status, _ = await _run_backfill_one(storage, client)

    assert status == "skip"
    assert client.calls == [], "đã hỏi tới to -> không được gọi API lại"


async def test_full_data_still_records_to_and_skips_next_time():
    """Trường hợp bình thường: bar về đủ tới to -> last_done_date = to,
    attempted_until = to -> lần sau skip (hành vi cũ giữ nguyên cho mã đủ dữ liệu)."""
    storage = FakeStorage()
    client = FakeClient(
        {"AAH": [_bar("AAH", date(2026, 8, 18))]}
    )

    status, _ = await _run_backfill_one(storage, client, symbol="AAH")

    prog = storage.get_backfill_progress("AAH", "1d")
    assert status == "ok"
    assert prog["last_done_date"] == date(2026, 8, 18)
    assert prog["attempted_until"] == date(2026, 8, 18)

    # Lần sau: skip
    status2, _ = await _run_backfill_one(storage, client, symbol="AAH")
    assert status2 == "skip"
