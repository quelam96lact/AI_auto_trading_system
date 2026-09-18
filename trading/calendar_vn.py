from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SESSIONS = [(time(9, 0), time(11, 30)), (time(13, 0), time(14, 45))]


def is_trading_time(ts: datetime, holidays: set[date] = frozenset()) -> bool:
    ts = ts.astimezone(TZ)
    if ts.weekday() >= 5 or ts.date() in holidays:
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in SESSIONS)


def trading_days_between(
    start: datetime, end: datetime, holidays: frozenset = frozenset()
) -> int:
    """So NGAY GIAO DICH trong (start.date(), end.date()] — khong tinh start.

    Dung cho compute_nav (MARGIN-1): do tuoi cua gia theo ngay giao dich, khong
    phai ngay lich. Vi du bar daily 28/08/2026 (T6, phien gan nhat truoc le
    31/08-02/09) toi 03/09: 6 ngay LICH nhung chi 1 ngay GIAO DICH (03/09) —
    gia con tuoi. Dem cuoi tuan va ngay le la dem SAI (plan 2026-09-03 goi A).

    Quy uoc: (start, end] — ngay cua chinh bar (start) khong tinh vi gia do
    da phan anh phien do; end tinh (hom nay da mo cua thi la 1 phien da qua).
    """
    s = start.astimezone(TZ).date()
    e = end.astimezone(TZ).date()
    n = 0
    d = s + timedelta(days=1)
    while d <= e:
        if d.weekday() < 5 and d not in holidays:
            n += 1
        d += timedelta(days=1)
    return n


def market_minutes_between(
    start: datetime,
    end: datetime,
    holidays: frozenset = frozenset(),
    sessions: list[tuple[time, time]] | None = None,
) -> float:
    """So PHUT TRONG PHIEN giua hai moc — bo qua ngoai gio, nghi trua, cuoi
    tuan, ngay le (plan 2026-09-03 goi A, dung cho chuong 2A bar_stale).

    Khac trading_days_between o don vi (phut vs ngay) va pham vi (trong phien
    vs ca ngay). Vi du bar cuoi 11:25 (phien sang) toi 13:00:03 cung ngay:
    95 phut DONG HO nhung chi ~5 phut TRONG PHIEN (11:25-11:30, nghi trua
    khong tinh, 13:00:03 chua co bar phien chieu la binh thuong) -> khong
    bao dong gia. Con bar cuoi 09:30 (feed chet tu sang) toi 13:00: 120 phut
    trong phien -> bao dong.

    sessions: mac dinh SESSIONS (den 14:45). Chuong 2A truyen CHECK_SESSIONS
    cua no (cat 14:30 de tranh ATC) — cung cong thuc, cau hinh phien khac.
    """
    sessions = sessions if sessions is not None else SESSIONS
    s = start.astimezone(TZ)
    e = end.astimezone(TZ)
    if e <= s:
        return 0.0
    total = 0.0
    day = s.date()
    while day <= e.date():
        if day.weekday() < 5 and day not in holidays:
            for sess_start, sess_end in sessions:
                seg_start = max(s, datetime.combine(day, sess_start, tzinfo=TZ))
                seg_end = min(e, datetime.combine(day, sess_end, tzinfo=TZ))
                if seg_end > seg_start:
                    total += (seg_end - seg_start).total_seconds() / 60.0
        day += timedelta(days=1)
    return total


CONTINUOUS_SESSIONS = [(time(9, 15), time(11, 30)), (time(13, 0), time(14, 30))]


def is_continuous_matching(ts: datetime, holidays: set[date] | frozenset = frozenset()) -> bool:
    """Đúng khi thị trường đang KHỚP LỆNH LIÊN TỤC — loại ATO (09:00-09:15) và ATC (14:30-14:45).

    Dùng lại phép kiểm ngày nghỉ/cuối tuần của is_trading_time.
    """
    ts = ts.astimezone(TZ)
    if ts.weekday() >= 5 or ts.date() in holidays:
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in CONTINUOUS_SESSIONS)

