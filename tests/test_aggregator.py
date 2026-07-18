from datetime import datetime
from trading.calendar_vn import TZ
from trading.collector.aggregator import BarAggregator
from trading.models import Tick

def tick(h, m, s, price, vol=100, sym="VCB"):
    return Tick(sym, price, vol, datetime(2026, 7, 15, h, m, s, tzinfo=TZ))

def test_aggregates_ohlcv_and_closes_on_boundary():
    agg = BarAggregator(5, set())
    assert agg.add_tick(tick(9, 0, 5, 100.0)) == []
    assert agg.add_tick(tick(9, 1, 0, 102.0)) == []
    assert agg.add_tick(tick(9, 4, 59, 99.0)) == []
    closed = agg.add_tick(tick(9, 5, 1, 101.0))  # sang bucket mới → đóng bar cũ
    assert len(closed) == 1
    b = closed[0]
    assert (b.open, b.high, b.low, b.close, b.volume) == (100.0, 102.0, 99.0, 99.0, 300)
    assert b.ts == datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

def test_ignores_out_of_session_tick():
    agg = BarAggregator(5, set())
    assert agg.add_tick(tick(12, 30, 0, 100.0)) == []
    assert agg.flush() == []

def test_flush_closes_open_bars():
    agg = BarAggregator(5, set())
    agg.add_tick(tick(14, 44, 0, 50.0))
    bars = agg.flush()
    assert len(bars) == 1 and bars[0].close == 50.0
    assert agg.flush() == []  # flush lần 2 không nhân đôi

def test_symbols_are_independent():
    agg = BarAggregator(5, set())
    agg.add_tick(tick(9, 0, 0, 100.0, sym="VCB"))
    agg.add_tick(tick(9, 0, 0, 20.0, sym="HPG"))
    closed = agg.add_tick(tick(9, 5, 0, 101.0, sym="VCB"))
    assert [b.symbol for b in closed] == ["VCB"]  # HPG vẫn mở