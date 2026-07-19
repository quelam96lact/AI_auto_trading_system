from collections import defaultdict
from datetime import datetime

from trading.models import Bar


def resample_bars(bars: list[Bar], target_minutes: int) -> list[Bar]:
    by_bucket: dict[tuple[str, datetime], list[Bar]] = defaultdict(list)
    for b in bars:
        by_bucket[(b.symbol, _bucket(b.ts, target_minutes))].append(b)

    out: list[Bar] = []
    for (symbol, bucket), group in sorted(by_bucket.items(), key=lambda kv: kv[0]):
        group.sort(key=lambda b: b.ts)
        out.append(
            Bar(
                symbol=symbol,
                ts=bucket,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
                source=group[0].source,
            )
        )
    return out


def _bucket(ts: datetime, target_minutes: int) -> datetime:
    minute = (ts.minute // target_minutes) * target_minutes
    return ts.replace(minute=minute, second=0, microsecond=0)
