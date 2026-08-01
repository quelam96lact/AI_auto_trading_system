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
