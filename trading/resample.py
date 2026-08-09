from collections import defaultdict
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar


def _aggregate(symbol: str, bucket: datetime, group: list[Bar]) -> Bar:
    group = sorted(group, key=lambda b: b.ts)
    return Bar(
        symbol=symbol,
        ts=bucket,
        open=group[0].open,
        high=max(g.high for g in group),
        low=min(g.low for g in group),
        close=group[-1].close,
        volume=sum(g.volume for g in group),
        source=group[0].source,
    )


def _group_by(bars: list[Bar], key) -> list[Bar]:
    buckets: dict[tuple[str, datetime], list[Bar]] = defaultdict(list)
    for b in bars:
        buckets[(b.symbol, key(b.ts))].append(b)
    return [
        _aggregate(sym, bucket, group)
        for (sym, bucket), group in sorted(buckets.items(), key=lambda kv: kv[0])
    ]


def _vn_midnight(ts: datetime) -> datetime:
    local = ts.astimezone(TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket(ts: datetime, target_minutes: int) -> datetime:
    """Neo theo nua dem GIO VN, khong phai phut-trong-gio.

    Cach cu (`ts.replace(minute=...)`) khong dung toi gio/ngay nen moi khung
    >= 60 phut deu sup ve bar 1 gio ma khong bao loi. Neo nua dem VN thay vi
    epoch UTC de ranh gioi 4h roi vao 00/04/08/12/16 gio VN — bucket 08:00 om
    tron phien sang, 12:00 om tron phien chieu.
    """
    day_start = _vn_midnight(ts)
    minutes = int((ts.astimezone(TZ) - day_start).total_seconds() // 60)
    return day_start + timedelta(minutes=(minutes // target_minutes) * target_minutes)


def resample_bars(bars: list[Bar], target_minutes: int) -> list[Bar]:
    return _group_by(bars, lambda ts: _bucket(ts, target_minutes))


def resample_daily(bars: list[Bar]) -> list[Bar]:
    """Gom theo NGAY LICH gio VN.

    Khong dung resample_bars(bars, 1440): phien VN chi chiem mot phan nho cua
    ngay va bar ATC nam lech (14:45, sau khoang trong 14:30-14:40), nen gom theo
    phut se cho ranh gioi sai.
    """
    return _group_by(bars, _vn_midnight)


def resample_weekly(bars: list[Bar]) -> list[Bar]:
    """Gom theo TUAN, moc thu Hai gio VN. Dung cho bar NGAY (bars_daily)."""

    def monday(ts: datetime) -> datetime:
        d = _vn_midnight(ts)
        return d - timedelta(days=d.weekday())

    return _group_by(bars, monday)


def resample_monthly(bars: list[Bar]) -> list[Bar]:
    """Gom theo THANG, moc ngay 1 gio VN. Dung cho bar NGAY (bars_daily)."""
    return _group_by(bars, lambda ts: _vn_midnight(ts).replace(day=1))
