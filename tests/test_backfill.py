import json
from datetime import date, datetime
from pathlib import Path

from trading.calendar_vn import TZ
from trading.collector.backfill import (
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
        return [Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10),
                Bar(symbol, datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 2, 3, 2, 3, 20)]


async def test_run_backfill_writes_missing_bars():
    st = FakeStorage(last=datetime(2026, 7, 15, 8, 55, tzinfo=TZ))
    counts = await run_backfill(st, FakeClient(), ["VCB"], today=date(2026, 7, 15))
    assert counts["VCB"] == 2 and len(st.bars) == 2 and len(st.daily) == 1


def test_parse_intraday_fixture():
    raw = json.loads((FIXTURES / "ssi_intraday_ohlc.json").read_text(encoding="utf-8"))
    bars = parse_intraday_response(raw)
    assert bars and all(b.ts.tzinfo is not None for b in bars)
    assert all(b.ts.minute % 5 == 0 for b in bars)  # đã chuẩn hóa 5m


def test_ohlc_rows_to_bars_from_real_fixture():
    from ssi_sdk.models import OHLCData

    raw = json.loads((FIXTURES / "ssi_sdk_ohlc_5m_vcb.json").read_text(encoding="utf-8"))
    rows = OHLCData.from_list(raw["data"])
    bars = _ohlc_rows_to_bars(rows)

    assert len(bars) == 230
    assert all(b.ts.tzinfo is not None for b in bars)
    # dòng đầu fixture: 2026/07/24 14:45:00, open=54100 (xem file fixture)
    first = next(b for b in bars if b.ts == datetime(2026, 7, 24, 14, 45, tzinfo=TZ))
    assert first.symbol == "VCB" and first.open == 54100 and first.volume == 189100
