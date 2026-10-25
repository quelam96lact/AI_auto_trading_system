from datetime import date, datetime

from scripts.backfill_history import backfill_history, range_from_days_back
from trading.calendar_vn import TZ
from trading.models import Bar


def test_range_from_days_back():
    today = date(2026, 8, 1)
    assert range_from_days_back(90, today) == (date(2026, 5, 3), today)
    assert range_from_days_back(0, today) == (today, today)


class FakeStorage:
    def __init__(self):
        self.bars, self.daily = [], []

    def write_bars(self, bars):
        self.bars.extend(bars)

    def write_daily(self, bars):
        self.daily.extend(bars)


class FakeClient:
    def __init__(self):
        self.intraday_calls = []
        self.daily_calls = []

    async def intraday_ohlc(self, symbol, frm, to):
        self.intraday_calls.append((symbol, frm, to))
        return [Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10)]

    async def daily_ohlc(self, symbol, frm, to):
        self.daily_calls.append((symbol, frm, to))
        return [Bar(symbol, datetime(2026, 7, 15, tzinfo=TZ), 1, 2, 1, 2, 100)]


async def test_backfill_history_writes_wide_range_per_symbol():
    storage = FakeStorage()
    client = FakeClient()
    today = date(2026, 8, 1)

    counts = await backfill_history(
        storage, client, ["VCB", "HPG"], today, intraday_days=90, daily_days=730
    )

    assert counts == {
        "VCB": {"intraday": 1, "daily": 1},
        "HPG": {"intraday": 1, "daily": 1},
    }
    assert len(storage.bars) == 2 and len(storage.daily) == 2
    assert client.intraday_calls == [
        ("VCB", date(2026, 5, 3), today),
        ("HPG", date(2026, 5, 3), today),
    ]
    assert client.daily_calls == [
        ("VCB", date(2024, 8, 1), today),
        ("HPG", date(2024, 8, 1), today),
    ]


class BarsFakeClient:
    def __init__(self, intraday=None, daily=None):
        self._intraday = intraday if intraday is not None else []
        self._daily = daily if daily is not None else []
        self.intraday_calls = []
        self.daily_calls = []

    async def intraday_ohlc(self, symbol, frm, to):
        self.intraday_calls.append((symbol, frm, to))
        return list(self._intraday)

    async def daily_ohlc(self, symbol, frm, to):
        self.daily_calls.append((symbol, frm, to))
        return list(self._daily)


async def test_intraday_drops_dirty_bars_before_write():
    clean1 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 100
    )
    clean2 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 10.5, 12.0, 10.0, 11.5, 100
    )
    dirty_close = Bar(
        "VCB", datetime(2026, 7, 15, 9, 10, tzinfo=TZ), 10.0, 11.0, 9.0, 0.0, 100
    )
    dirty_low = Bar(
        "VCB", datetime(2026, 7, 15, 9, 15, tzinfo=TZ), 10.0, 11.0, 0.0, 10.0, 100
    )
    daily = [Bar("VCB", datetime(2026, 7, 15, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 1000)]

    storage = FakeStorage()
    client = BarsFakeClient(
        intraday=[clean1, dirty_close, clean2, dirty_low], daily=daily
    )
    today = date(2026, 8, 1)

    counts = await backfill_history(storage, client, ["VCB"], today, 90, 730)

    assert storage.bars == [clean1, clean2]
    assert counts["VCB"]["intraday"] == 2


async def test_intraday_all_dirty_writes_nothing_and_does_not_crash():
    dirty_close = Bar(
        "VCB", datetime(2026, 7, 15, 9, 10, tzinfo=TZ), 10.0, 11.0, 9.0, 0.0, 100
    )
    dirty_low = Bar(
        "VCB", datetime(2026, 7, 15, 9, 15, tzinfo=TZ), 10.0, 11.0, 0.0, 10.0, 100
    )
    daily = [Bar("VCB", datetime(2026, 7, 15, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 1000)]

    storage = FakeStorage()
    client = BarsFakeClient(intraday=[dirty_close, dirty_low], daily=daily)
    today = date(2026, 8, 1)

    counts = await backfill_history(storage, client, ["VCB"], today, 90, 730)

    assert storage.bars == []
    assert counts["VCB"]["intraday"] == 0
    assert storage.daily == daily


async def test_progress_line_reports_dropped_count(capsys):
    clean1 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 100
    )
    clean2 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 10.5, 12.0, 10.0, 11.5, 100
    )
    dirty_close = Bar(
        "VCB", datetime(2026, 7, 15, 9, 10, tzinfo=TZ), 10.0, 11.0, 9.0, 0.0, 100
    )
    dirty_low = Bar(
        "VCB", datetime(2026, 7, 15, 9, 15, tzinfo=TZ), 10.0, 11.0, 0.0, 10.0, 100
    )
    daily = [Bar("VCB", datetime(2026, 7, 15, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 1000)]
    today = date(2026, 8, 1)

    # 1. Co 2 bar rac -> chua "bo 2 bar rac"
    storage1 = FakeStorage()
    client1 = BarsFakeClient(
        intraday=[clean1, dirty_close, clean2, dirty_low], daily=daily
    )
    await backfill_history(storage1, client1, ["VCB"], today, 90, 730)
    out1 = capsys.readouterr().out
    assert "bo 2 bar rac" in out1

    # 2. Khong co bar rac -> khong chua "bar rac"
    storage2 = FakeStorage()
    client2 = BarsFakeClient(intraday=[clean1, clean2], daily=daily)
    await backfill_history(storage2, client2, ["VCB"], today, 90, 730)
    out2 = capsys.readouterr().out
    assert "bar rac" not in out2


async def test_progress_first_last_5m_use_clean_bars(capsys):
    """Nen ban nam o dau va cuoi chuoi: dong '5m dau/5m cuoi' phai in ts cua nen sach;
    toan nen ban thi khong in dong '5m dau' (audit dot 197)."""
    dirty_first = Bar(
        "VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10.0, 11.0, 9.0, 0.0, 100
    )
    clean1 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 100
    )
    clean2 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 10, tzinfo=TZ), 10.5, 12.0, 10.0, 11.5, 100
    )
    dirty_last = Bar(
        "VCB", datetime(2026, 7, 15, 9, 15, tzinfo=TZ), 0.0, 11.0, 9.0, 10.0, 100
    )
    today = date(2026, 8, 1)

    client = BarsFakeClient(intraday=[dirty_first, clean1, clean2, dirty_last])
    await backfill_history(FakeStorage(), client, ["VCB"], today, 90, 730)
    out = capsys.readouterr().out
    assert f"5m dau: {clean1.ts}  5m cuoi: {clean2.ts}" in out

    client_dirty = BarsFakeClient(intraday=[dirty_first, dirty_last])
    await backfill_history(FakeStorage(), client_dirty, ["VCB"], today, 90, 730)
    assert "5m dau" not in capsys.readouterr().out


async def test_daily_still_writes_zero_price_bars_unchanged():
    d_dirty = Bar("VCB", datetime(2026, 7, 14, tzinfo=TZ), 10.0, 11.0, 9.0, 0.0, 100)
    d_clean = Bar("VCB", datetime(2026, 7, 15, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 1000)
    daily = [d_dirty, d_clean]
    clean1 = Bar(
        "VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 100
    )

    storage = FakeStorage()
    client = BarsFakeClient(intraday=[clean1], daily=daily)
    today = date(2026, 8, 1)

    counts = await backfill_history(storage, client, ["VCB"], today, 90, 730)

    assert storage.daily == [d_dirty, d_clean]
    assert counts["VCB"]["daily"] == 2
