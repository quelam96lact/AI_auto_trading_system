"""Unit tests cho GAP-1 warm-up gap detection — Brief đợt 74 Task 1.

Dùng hàm count_warmup_gap() đã tách ra (không cần NATS, không mark integration).
Bốn ca kiểm chứng theo mốc thật 18/09/2026 và 21/09/2026:

1. Tái hiện tình huống sáng nay: warmed_until = 18/09 14:45 (nến ATC),
   nến live đầu = 21/09 09:30 → 3 nến thiếu → WARN.
2. Ba ca im lặng:
   - 18/09 14:45 → 21/09 09:15 (liền mạch qua cuối tuần và nến ATC).
   - 11:25 → 13:00 cùng ngày (liền mạch qua nghỉ trưa).
   - 11:20 → 11:25 (liền mạch trong phiên — ca dễ làm hỏng nhất).
Phần nối dây trong run() (_warmup_gap_checked, lời gọi alert) CHƯA có test
— xem brief đợt 75.
"""

from datetime import datetime

from trading.calendar_vn import TZ
from trading.engine.main import count_warmup_gap

# Mốc thật từ log 18/09/2026 (thứ Sáu) và 21/09/2026 (thứ Hai)
FRI_ATC = datetime(2026, 9, 18, 14, 45, tzinfo=TZ)   # nến ATC cuối phiên thứ Sáu
MON_0930 = datetime(2026, 9, 21, 9, 30, tzinfo=TZ)   # nến live đầu thứ Hai (tình huống thật)
MON_0915 = datetime(2026, 9, 21, 9, 15, tzinfo=TZ)   # nến live đầu thứ Hai (liền mạch)

BAR_MIN = 5  # bar_interval_minutes thực tế hệ thống


def test_gap1_ca1_tai_hien_tinh_huong_sang_nay_3_nen_thieu() -> None:
    """Ca 1 — Tái hiện đúng tình huống 21/09 sáng nay.

    warmed_until = 18/09 14:45 (nến ATC thứ Sáu)
    nến live đầu tiên = 21/09 09:30 (thứ Hai)
    → 3 nến thiếu: 09:15, 09:20, 09:25.

    Giải thích xử lý ATC: warmed_until + 5m = 14:50, nằm sau 14:30
    (kết thúc CONTINUOUS_SESSIONS) → phần thứ Sáu = 0 phút.
    Thứ Hai: 09:15 → 09:30 = 15 phút → 15/5 = 3 nến thiếu.
    """
    missing = count_warmup_gap(FRI_ATC, MON_0930, BAR_MIN, frozenset())
    assert missing == 3, (
        f"Ca 1 that bai: ky vong 3 nen thieu (09:15, 09:20, 09:25), "
        f"thuc te = {missing}"
    )


def test_gap1_ca2_im_lang_qua_cuoi_tuan_va_ATC() -> None:
    """Ca 2a — Im lặng: 18/09 14:45 → 21/09 09:15 (liền mạch qua cuối tuần + ATC).

    09:15 là nến đầu tiên của thứ Hai = nến kế tiếp sau chuỗi kết thúc ATC.
    Không có nến nào thiếu → count_warmup_gap phải trả về 0.
    """
    missing = count_warmup_gap(FRI_ATC, MON_0915, BAR_MIN, frozenset())
    assert missing == 0, (
        f"Ca 2a that bai: qua ATC+cuoi tuan phai 0 nen thieu, thuc te = {missing}"
    )


def test_gap1_ca2_im_lang_qua_nghi_trua() -> None:
    """Ca 2b — Im lặng: 11:25 → 13:00 cùng ngày (liền mạch qua nghỉ trưa).

    11:25 là nến cuối sáng; 13:00 là nến đầu chiều — liền mạch.
    count_warmup_gap phải trả về 0 (không báo động giả nghỉ trưa).
    """
    ts_1125 = datetime(2026, 9, 18, 11, 25, tzinfo=TZ)
    ts_1300 = datetime(2026, 9, 18, 13, 0, tzinfo=TZ)
    missing = count_warmup_gap(ts_1125, ts_1300, BAR_MIN, frozenset())
    assert missing == 0, (
        f"Ca 2b that bai: qua nghi trua phai 0 nen thieu, thuc te = {missing}"
    )


def test_gap1_ca2_im_lang_lien_mach_trong_phien() -> None:
    """Ca 2c — Im lặng: 11:20 → 11:25 (liền mạch trong phiên — ca dễ làm hỏng nhất).

    Hai nến liền kề trong phiên sáng → 0 thiếu.
    """
    ts_1120 = datetime(2026, 9, 18, 11, 20, tzinfo=TZ)
    ts_1125 = datetime(2026, 9, 18, 11, 25, tzinfo=TZ)
    missing = count_warmup_gap(ts_1120, ts_1125, BAR_MIN, frozenset())
    assert missing == 0, (
        f"Ca 2c that bai: lien mach trong phien phai 0, thuc te = {missing}"
    )
