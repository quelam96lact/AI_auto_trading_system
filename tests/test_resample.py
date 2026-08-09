from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.resample import (
    resample_bars,
    resample_daily,
    resample_monthly,
    resample_weekly,
)


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


def _session_bars(month, day, sym="VCB", price=10.0):
    """46 slot that cua 1 phien VN, khop luoi do duoc tu DB."""
    times = (
        [(9, 15 + 5 * i) for i in range(27)]  # 09:15 -> 11:25
        + [(13, 5 * i) for i in range(18)]  # 13:00 -> 14:25
        + [(14, 45)]  # bar ATC
    )
    out = []
    for h, m in times:
        ts = datetime(2026, month, day, 9, 0, tzinfo=TZ) + timedelta(
            hours=h - 9, minutes=m
        )
        out.append(Bar(sym, ts, price, price + 1, price - 1, price, 100))
    return out


def test_bucket_above_one_hour_no_longer_collapses_to_hourly():
    """4h phai ra 2 bar/phien. Bug goc: moi khung >= 60 phut deu ra bar 1 gio."""
    out = resample_bars(_session_bars(8, 3), 240)
    assert len(out) == 2, f"4h phai ra 2 bar/phien, dang ra {len(out)}"
    assert [b.ts.astimezone(TZ).strftime("%H:%M") for b in out] == ["08:00", "12:00"]


def test_resample_below_one_hour_unchanged():
    """Regression: ket qua <= 60 phut phai y het truoc khi sua.

    10m: sang 14 bucket + chieu 9 + ATC 1 = 24
    15m: sang 9 + chieu 6 + ATC 1 = 16
    1h : sang 3 (09,10,11) + chieu 2 (13,14) = 5
    """
    bars = _session_bars(8, 3)
    assert len(resample_bars(bars, 10)) == 24
    assert len(resample_bars(bars, 15)) == 16
    assert len(resample_bars(bars, 60)) == 5


def test_resample_daily_groups_by_vn_calendar_day():
    bars = _session_bars(8, 3) + _session_bars(8, 4)
    out = resample_daily(bars)
    assert len(out) == 2
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d %H:%M") for b in out] == [
        "2026-08-03 00:00",
        "2026-08-04 00:00",
    ]
    assert out[0].open == bars[0].open
    assert out[0].close == bars[45].close
    assert out[0].volume == sum(b.volume for b in bars[:46])


def test_resample_weekly_anchors_on_monday():
    # 2026-08-03 thu Hai, 2026-08-07 thu Sau, 2026-08-10 thu Hai ke tiep
    out = resample_weekly(_session_bars(8, 3) + _session_bars(8, 7) + _session_bars(8, 10))
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d") for b in out] == [
        "2026-08-03",
        "2026-08-10",
    ]


def test_resample_monthly_anchors_on_first_of_month():
    out = resample_monthly(_session_bars(7, 15) + _session_bars(8, 3) + _session_bars(8, 20))
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d") for b in out] == [
        "2026-07-01",
        "2026-08-01",
    ]
