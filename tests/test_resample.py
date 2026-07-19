from datetime import datetime

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.resample import resample_bars


def b5(m, o, h, l, c, v=100, sym="VCB"):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, v)


def test_resamples_three_5m_bars_into_one_15m_bar():
    bars = [
        b5(0, 10, 11, 9, 10.5),
        b5(5, 10.5, 12, 10, 11),
        b5(10, 11, 11.5, 10.5, 11.2),
    ]
    out = resample_bars(bars, 15)
    assert len(out) == 1
    r = out[0]
    assert (r.open, r.high, r.low, r.close, r.volume) == (10, 12, 9, 11.2, 300)
    assert r.ts == datetime(2026, 7, 15, 9, 0, tzinfo=TZ)


def test_symbols_kept_independent():
    bars = [b5(0, 1, 2, 1, 1.5, sym="VCB"), b5(0, 2, 3, 2, 2.5, sym="HPG")]
    out = resample_bars(bars, 15)
    assert {r.symbol for r in out} == {"VCB", "HPG"}


def test_incomplete_trailing_bucket_still_emitted():
    bars = [b5(0, 1, 1, 1, 1)]
    out = resample_bars(bars, 15)
    assert len(out) == 1 and out[0].volume == 100
