"""Characterization tests cho evaluate_daily_completeness
(scripts/daily_data_check.py) — brief dot 11.

daily_data_check la chuong bao duy nhat trong 4 chuong co lich tu chay ma khong
co test. Ham nay da thuan (nhan 2 set, tra (code, missing, message)) nen test
duoc khong can DB/Docker/sleep.

KHONG sua scripts/daily_data_check.py — day la characterization test: ghim
hanh vi HIEN CO, khong phai refactor.
"""

from datetime import date, datetime
from pathlib import Path

from scripts.daily_data_check import (
    check_backfill_completed,
    evaluate_daily_completeness,
    friday_only_symbols,
    get_previous_trading_day,
)
from trading.calendar_vn import TZ


def test_active_symbols_rong_thi_code_0():
    """active_symbols rong -> code 0, khong co ma thieu."""
    code, missing, _msg = evaluate_daily_completeness([], {"AAA"})
    assert code == 0
    assert missing == set()


def test_ngay_le_khong_bao_lao_nhuong_2A():
    """KHONG ma nao co bar (ngay le / feed chet toan dien) -> code 0, IM LANG.

    Im lang o day la hanh vi DUNG, khong phai thieu sot: job nay bat "feed
    song nhung sot ma", con "toan bo feed chet" la viec cua Heartbeat 2A
    (chay 5 phut/lan trong phien). Neu 0 ma nao co bar ma job nay bao dong
    se ban TRUNG voi 2A — dong gop ngay 01/09 cua Claude chua tung duoc ghim
    bang test. Dung coi day la bug ma "sua" thanh bao dong.
    """
    code, missing, msg = evaluate_daily_completeness(["AAA", "HII"], set())
    assert code == 0
    assert missing == set()
    assert "Heartbeat 2A" in msg


def test_du_toan_bo_ma_thi_code_0():
    """Toan bo ma active deu co bar -> code 0."""
    code, missing, msg = evaluate_daily_completeness(
        ["AAA", "HII"], {"AAA", "HII", "VCB"}
    )
    assert code == 0
    assert missing == set()
    assert "Đầy đủ" in msg


def test_thieu_vai_ma_trong_khi_ma_khac_co_bar_thi_bao_dong():
    """Feed song (mot so ma co bar) nhung sot vai ma active -> code 1, missing
    dung tap, message neu du so luong."""
    active = ["AAA", "HII", "VCB", "TCX"]
    present = {"AAA", "VCB"}  # HII va TCX thieu
    code, missing, msg = evaluate_daily_completeness(active, present)
    assert code == 1
    assert missing == {"HII", "TCX"}
    assert "Tổng số mã active: 4" in msg
    assert "Số mã có bar: 2" in msg
    assert "Số mã THIẾU bar (2 mã)" in msg
    assert "HII" in msg and "TCX" in msg


def test_qua_15_ma_thieu_thi_message_co_phan_cut():
    """> 15 ma thieu -> message phai co phan '... (+N ma nua)' — cho de lech
    khi ai do chinh chuoi."""
    active = [f"SYM{i:03d}" for i in range(1, 21)]  # 20 ma
    present = {"SYM001"}  # thieu 19 ma
    code, missing, msg = evaluate_daily_completeness(active, present)
    assert code == 1
    assert len(missing) == 19
    assert "... (+4 mã nữa)" in msg  # 19 - 15 = 4


def test_ngay_giao_dich_present_rong_thi_exit_2():
    """Brief 51 Task 2: Ngày giao dịch mà 0 mã nào có bar -> exit 2 (lỗi dữ liệu / feed chết)."""
    active = ["AAA", "HPG", "IJC"]
    present = set()
    code, missing, msg = evaluate_daily_completeness(active, present, is_trading_day=True)
    assert code == 2
    assert missing == {"AAA", "HPG", "IJC"}
    assert "SỰ CỐ DỮ LIỆU" in msg
    assert "0 mã nào có bar" in msg


def test_ngay_nghi_present_rong_thi_exit_0():
    """Brief 51 Task 2: Ngày nghỉ (thứ Bảy / CN / Lễ) mà 0 mã nào có bar -> exit 0 (nhường 2A)."""
    active = ["AAA", "HPG", "IJC"]
    present = set()
    code, missing, msg = evaluate_daily_completeness(active, present, is_trading_day=False)
    assert code == 0
    assert missing == set()
    assert "Heartbeat 2A" in msg


def test_present_thieu_mot_phan_exit_1():
    """Brief 51 Task 2: Có bar nhưng thiếu một phần -> exit 1 như cũ."""
    active = ["AAA", "HPG", "IJC"]
    present = {"AAA", "HPG"}
    code, missing, msg = evaluate_daily_completeness(active, present, is_trading_day=True)
    assert code == 1
    assert missing == {"IJC"}
    assert "CẢNH BÁO: Sót bar daily" in msg


# =====================================================================
# Brief 92 Task 4: Phân biệt "dữ liệu chưa về" với "dữ liệu mất"
# =====================================================================


def test_task4_0_tren_175_ma_backfill_chua_xong_thi_hoan_co_warn_khong_bao_do():
    """Ca 1: 0/175 mã, backfill CHƯA xong -> HOÃN, có WARN, không báo đỏ (exit != 2)."""
    active_175 = [f"SYM{i:03d}" for i in range(175)]
    code, _missing, msg = evaluate_daily_completeness(
        active_symbols=active_175,
        present_symbols=set(),
        is_trading_day=True,
        backfill_done=False,
    )
    assert code != 2, "Tuyệt đối không được báo đỏ (code 2) khi backfill chưa xong!"
    assert code == 1
    assert "HOÃN" in msg or "hoãn" in msg
    assert "SỰ CỐ DỮ LIỆU" not in msg


def test_task4_0_tren_175_ma_backfill_da_xong_thi_bao_do():
    """Ca 2: 0/175 mã, backfill ĐÃ xong -> BÁO ĐỎ (sự cố dữ liệu thật, exit 2)."""
    active_175 = [f"SYM{i:03d}" for i in range(175)]
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=active_175,
        present_symbols=set(),
        is_trading_day=True,
        backfill_done=True,
    )
    assert code == 2
    assert missing == set(active_175)
    assert "SỰ CỐ DỮ LIỆU" in msg


def test_task4_174_tren_175_ma_thieu_mot_phan_bao_canh_bao_nhu_cu():
    """Ca 3: 174/175 mã (thiếu POM) -> cảnh báo sót mã (code 1), giữ nguyên hành vi đúng."""
    active_175 = [f"SYM{i:03d}" for i in range(175)]
    present_174 = set(active_175[:-1])
    missing_expected = {active_175[-1]}
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=active_175,
        present_symbols=present_174,
        is_trading_day=True,
        backfill_done=True,
    )
    assert code == 1
    assert missing == missing_expected
    assert "CẢNH BÁO: Sót bar daily" in msg


def test_task4_175_tren_175_ma_thi_im_lang_exit_0():
    """Ca 4: 175/175 mã đầy đủ -> im lặng, exit 0."""
    active_175 = [f"SYM{i:03d}" for i in range(175)]
    present_175 = set(active_175)
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=active_175,
        present_symbols=present_175,
        is_trading_day=True,
        backfill_done=True,
    )
    assert code == 0
    assert missing == set()
    assert "Đầy đủ" in msg


def test_task4_check_backfill_completed(tmp_path: Path):
    """Kiểm tra hàm đọc dấu hoàn tất của backfill trong file log."""
    log_file = tmp_path / "backfill.log"

    # 1. File log chưa tồn tại -> False
    assert check_backfill_completed(log_file, date(2026, 9, 25)) is False

    # 2. Đang chạy dở (chưa có DONE: và EXIT=0)
    log_file.write_text(
        "2026-09-25 21:42:11 backfill start\n[load] 175 ma\nBackfill 1d: 175 ma -> 2026-09-25\n",
        encoding="utf-8",
    )
    assert check_backfill_completed(log_file, date(2026, 9, 25)) is False

    # 3. Đã hoàn tất thành công (có DONE: và EXIT=0)
    log_file.write_text(
        "2026-09-25 21:42:11 backfill start\n[load] 175 ma\nBackfill 1d: 175 ma -> 2026-09-25\nDONE: ok=175 skip=0 err=0 / 175\nEXIT=0\n",
        encoding="utf-8",
    )
    assert check_backfill_completed(log_file, date(2026, 9, 25)) is True

    # 4. Khác ngày -> False
    assert check_backfill_completed(log_file, date(2026, 9, 26)) is False


# ============ Brief 97 Task 2: Mã chỉ giao dịch thứ Sáu ============


def test_task2_khong_bao_oan_kiem_thu_hai_va_pom_thieu():
    """1. (b) Không báo oan: POM có nến 6 thứ Sáu gần nhất; kiểm thứ Hai và POM thiếu -> exit 0, không WARN."""
    pom_fridays = [
        date(2026, 9, 18),
        date(2026, 9, 11),
        date(2026, 9, 4),
        date(2026, 8, 28),
        date(2026, 8, 21),
        date(2026, 8, 14),
    ]
    check_monday = date(2026, 9, 21)
    excluded = friday_only_symbols({"POM": pom_fridays}, check_date=check_monday)
    assert "POM" in excluded

    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["POM", "HPG"],
        present_symbols={"HPG"},
        is_trading_day=True,
        backfill_done=True,
        excluded_symbols=excluded,
    )
    assert code == 0
    assert missing == set()
    assert "Loại 1 mã chỉ giao dịch thứ Sáu (POM)" in msg


def test_task2_van_bat_thu_sau_pom_thieu_thi_warn():
    """2. (a) Vẫn bắt thứ Sáu: cùng lịch sử đó; kiểm thứ Sáu và POM thiếu -> WARN, có tên POM."""
    pom_fridays = [
        date(2026, 9, 18),
        date(2026, 9, 11),
        date(2026, 9, 4),
        date(2026, 8, 28),
        date(2026, 8, 21),
        date(2026, 8, 14),
    ]
    check_friday = date(2026, 9, 25)
    excluded = friday_only_symbols({"POM": pom_fridays}, check_date=check_friday)
    assert "POM" not in excluded

    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["POM", "HPG"],
        present_symbols={"HPG"},
        is_trading_day=True,
        backfill_done=True,
        excluded_symbols=excluded,
    )
    assert code == 1
    assert missing == {"POM"}
    assert "POM" in msg


def test_task2_khong_lam_mu_ma_thuong_hpg_thieu_thi_warn():
    """3. (a) Không làm mù mã thường: HPG có nến mọi ngày; kiểm thứ Hai và HPG thiếu -> WARN."""
    hpg_dates = [
        date(2026, 9, 18),  # T6
        date(2026, 9, 17),  # T5
        date(2026, 9, 16),  # T4
        date(2026, 9, 15),  # T3
        date(2026, 9, 14),  # T2
    ]
    check_monday = date(2026, 9, 21)
    excluded = friday_only_symbols({"HPG": hpg_dates}, check_date=check_monday)
    assert "HPG" not in excluded

    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["HPG", "AAA"],
        present_symbols={"AAA"},
        is_trading_day=True,
        backfill_done=True,
        excluded_symbols=excluded,
    )
    assert code == 1
    assert missing == {"HPG"}
    assert "HPG" in msg


def test_task2_mau_so_dung_174_ma_ghi_ro_loai_pom():
    """4. (c) Mẫu số: 175 mã, 1 mã chỉ-thứ-Sáu, kiểm thứ Hai -> báo cáo ghi 174 mã được kiểm, và ghi rõ đã loại POM."""
    active_175 = ["POM"] + [f"SYM{i:03d}" for i in range(174)]
    present_174 = set(active_175[1:])
    excluded = {"POM"}

    code, missing, msg = evaluate_daily_completeness(
        active_symbols=active_175,
        present_symbols=present_174,
        is_trading_day=True,
        backfill_done=True,
        excluded_symbols=excluded,
    )
    assert code == 0
    assert missing == set()
    assert "174" in msg
    assert "Loại 1 mã chỉ giao dịch thứ Sáu (POM)" in msg


def test_task2_quay_lai_binh_thuong_khi_co_nen_ngay_khac():
    """5. Quay lại bình thường: POM có thêm một nến thứ Ba trong cửa sổ -> không còn là chỉ-thứ-Sáu."""
    pom_dates = [
        date(2026, 9, 18),  # T6
        date(2026, 9, 15),  # T3
        date(2026, 9, 11),  # T6
        date(2026, 9, 4),   # T6
    ]
    check_monday = date(2026, 9, 21)
    excluded = friday_only_symbols({"POM": pom_dates}, check_date=check_monday)
    assert "POM" not in excluded


def test_task2_qua_it_du_lieu_duoi_3_nen_van_kiem_binh_thuong():
    """6. Quá ít dữ liệu: mã chỉ có 2 nến, cả hai là thứ Sáu -> không được coi là chỉ-thứ-Sáu (chưa đủ 3), vẫn kiểm bình thường."""
    sym_dates = [
        date(2026, 9, 18),  # T6
        date(2026, 9, 11),  # T6 (chỉ 2 nến)
    ]
    check_monday = date(2026, 9, 21)
    excluded = friday_only_symbols({"NEW": sym_dates}, check_date=check_monday)
    assert "NEW" not in excluded


def test_task2_cua_so_30_ngay_dem_bang_is_trading_day_va_holidays():
    """7. Ngày lễ: cửa sổ 30 ngày giao dịch đếm bằng trading.calendar_vn.is_trading_day với holidays."""
    holidays = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})
    check_monday = date(2026, 9, 21)
    pom_fridays = [
        date(2026, 9, 18),
        date(2026, 9, 11),
        date(2026, 9, 4),
        date(2026, 8, 28),
    ]
    excluded = friday_only_symbols({"POM": pom_fridays}, check_date=check_monday, holidays=holidays)
    assert "POM" in excluded


def test_task2_tinh_ngay_theo_gio_vn_khong_theo_utc():
    """Kiểm tra múi giờ VN vs UTC: nến ngày 00:00 VN = 17:00 UTC hôm trước.
    Thứ Sáu 25/09 00:00 VN tương đương Thứ Năm 24/09 17:00 UTC.
    Hàm phải tính đúng Thứ Sáu theo giờ VN."""
    dt_fridays = [
        datetime(2026, 9, 18, 0, 0, tzinfo=TZ),
        datetime(2026, 9, 11, 0, 0, tzinfo=TZ),
        datetime(2026, 9, 4, 0, 0, tzinfo=TZ),
    ]
    check_monday = date(2026, 9, 21)
    excluded = friday_only_symbols({"POM": dt_fridays}, check_date=check_monday)
    assert "POM" in excluded


# ============ Brief 97 Task 3: Hoãn hai ngày giao dịch liên tiếp thì phải leo thang ============


def test_task3_hom_nay_chua_xong_hom_qua_xong_exit_1():
    """1. Hôm nay chưa xong, hôm qua xong -> exit 1 (hoãn như cũ)."""
    code, _missing, msg = evaluate_daily_completeness(
        active_symbols=["AAA"],
        present_symbols=set(),
        is_trading_day=True,
        backfill_done=False,
        prev_backfill_done=True,
    )
    assert code == 1
    assert "HOÃN PHÁN QUYẾT" in msg


def test_task3_hom_nay_chua_xong_hom_qua_cung_chua_xong_exit_2_critical():
    """2. Hôm nay chưa xong, hôm qua cũng chưa xong -> exit 2, CRITICAL."""
    code, _missing, msg = evaluate_daily_completeness(
        active_symbols=["AAA"],
        present_symbols=set(),
        is_trading_day=True,
        backfill_done=False,
        prev_backfill_done=False,
    )
    assert code == 2
    assert "CRITICAL" in msg
    assert "backfill-universe không hoàn thành 2 ngày giao dịch liên tiếp" in msg


def test_task3_get_previous_trading_day_bo_qua_cuoi_tuan_va_ngay_le():
    """3. Hôm nay là thứ Hai: ngày liền trước là thứ Sáu (bỏ qua T7, CN)."""
    holidays = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})
    # Thứ Hai 21/09 -> Thứ Sáu 18/09
    assert get_previous_trading_day(date(2026, 9, 21), holidays) == date(2026, 9, 18)
    # Thứ Năm 03/09 (sau lễ 31/08 - 02/09) -> Thứ Sáu 28/08
    assert get_previous_trading_day(date(2026, 9, 3), holidays) == date(2026, 8, 28)


def test_task3_hom_nay_xong_kiem_binh_thuong():
    """4. Hôm nay xong -> hành vi kiểm bình thường, không bị ảnh hưởng."""
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["AAA", "HPG"],
        present_symbols={"AAA", "HPG"},
        is_trading_day=True,
        backfill_done=True,
        prev_backfill_done=False,
    )
    assert code == 0
    assert missing == set()
    assert "Đầy đủ" in msg


