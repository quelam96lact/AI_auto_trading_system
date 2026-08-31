from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SESSIONS = [(time(9, 0), time(11, 30)), (time(13, 0), time(14, 45))]


def is_trading_time(ts: datetime, holidays: set[date] = frozenset()) -> bool:
    ts = ts.astimezone(TZ)
    if ts.weekday() >= 5 or ts.date() in holidays:
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in SESSIONS)
