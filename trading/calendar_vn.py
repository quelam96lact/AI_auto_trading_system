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


def session_end_after(ts: datetime) -> datetime | None:
    """Thời điểm kết thúc của phiên chứa/ngay sau ts trong cùng ngày, None nếu hết phiên."""
    ts = ts.astimezone(TZ)
    for _, end in SESSIONS:
        end_dt = ts.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
        if ts <= end_dt:
            return end_dt
    return None