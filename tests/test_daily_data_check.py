"""Characterization tests cho evaluate_daily_completeness
(scripts/daily_data_check.py) — brief dot 11.

daily_data_check la chuong bao duy nhat trong 4 chuong co lich tu chay ma khong
co test. Ham nay da thuan (nhan 2 set, tra (code, missing, message)) nen test
duoc khong can DB/Docker/sleep.

KHONG sua scripts/daily_data_check.py — day la characterization test: ghim
hanh vi HIEN CO, khong phai refactor.
"""

from scripts.daily_data_check import evaluate_daily_completeness


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

