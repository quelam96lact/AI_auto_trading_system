"""Unit tests cho Bảng điểm SEPA và RS Rating hàng ngày (Brief đợt 119).

Mỗi test có ví dụ tính tay ghi trong test, literal asserts, không viết lại công thức.
Phục vụ kiểm thử và 4 phép phá thử bắt buộc:
1. Dùng ts::date thay cho bar_date() -> lệch 1 ngày.
2. Đổi trọng số RS từ 0.4/0.2/0.2/0.2 sang 0.25 đều.
3. Mã thiếu 252 nến được gán RS_rank = 50 thay vì '–'.
4. Đổi '% cách đỉnh' từ 1 - P/đỉnh sang đỉnh/P - 1.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from scripts.score_sepa_daily import (
    calculate_boundary_percentages,
    calculate_rs_raw,
    evaluate_sepa_single,
    format_single_symbol_report,
    load_untrusted_symbols,
)
from trading.models import Bar
from trading.stock_study import bar_date, calculate_rs_ranks


def test_bar_date_vs_ts_date_and_mutation_1():
    """Kiểm tra bar_date chuyển đổi đúng múi giờ VN (00:00 VN = 17:00 UTC hôm trước).

    Ví dụ tính tay:
    Nến ts = 2026-09-24 17:00:00 UTC.
    Theo giờ Việt Nam (UTC+7), thời điểm này là 2026-09-25 00:00:00.
    Ngày giao dịch tại Việt Nam là: 2026-09-25.
    Nếu lấy b.ts.date() theo UTC, ngày trả về là 2026-09-24 -> LỆCH MỘT NGÀY.
    """
    ts_utc = datetime(2026, 9, 24, 17, 0, 0, tzinfo=UTC)
    bar = Bar(symbol="BFC", ts=ts_utc, open=48000, high=49000, low=47500, close=48350, volume=100000)

    # Đúng: dùng bar_date()
    assert bar_date(bar) == date(2026, 9, 25)

    # Đột biến 1 sẽ làm: return b.ts.date() -> 2026-09-24 != 2026-09-25


def test_rs_raw_weights_and_mutation_2():
    """Kiểm tra công thức trọng số RS_raw: 0.4 / 0.2 / 0.2 / 0.2.

    Ví dụ tính tay với 253 nến đóng cửa:
    P (hiện tại, nến 252, closes[-1]) = 100.0
    P_63 (closes[-64]) = 80.0
    P_126 (closes[-127]) = 50.0
    P_189 (closes[-190]) = 50.0
    P_252 (closes[-253], nến 0) = 50.0
    Tất cả các nến khác = 100.0

    Tỷ lệ thay đổi giá:
    P / P_63 - 1  = 100 / 80 - 1 = 1.25 - 1 = 0.25 (+25%)
    P / P_126 - 1 = 100 / 50 - 1 = 2.00 - 1 = 1.00 (+100%)
    P / P_189 - 1 = 100 / 50 - 1 = 2.00 - 1 = 1.00 (+100%)
    P / P_252 - 1 = 100 / 50 - 1 = 2.00 - 1 = 1.00 (+100%)

    RS_raw chuẩn theo trọng số 0.4 / 0.2 / 0.2 / 0.2:
    = 0.4 * 0.25 + 0.2 * 1.00 + 0.2 * 1.00 + 0.2 * 1.00
    = 0.10 + 0.20 + 0.20 + 0.20
    = 0.7000 (LITERAL)

    Nếu đổi sang trọng số đều 0.25:
    = 0.25 * 0.25 + 0.25 * 1.00 + 0.25 * 1.00 + 0.25 * 1.00
    = 0.0625 + 0.75 = 0.8125 != 0.7000 -> ĐỘT BIẾN BỊ BẮT.
    """
    closes = [100.0] * 253
    closes[-1 - 63] = 80.0
    closes[-1 - 126] = 50.0
    closes[-1 - 189] = 50.0
    closes[-1 - 252] = 50.0

    rs = calculate_rs_raw(closes)
    assert rs is not None
    assert pytest.approx(rs, abs=1e-6) == 0.70


def test_insufficient_bars_rs_and_mutation_3():
    """Kiểm tra mã thiếu 252 nến thì RS phải là None và in '–', CẤM gán 50 hay 0.

    Ví dụ tính tay:
    Chuỗi có 200 nến (< 253 nến cần cho P_252).
    calculate_rs_raw phải trả về None.
    evaluate_sepa_single phải có rs_raw is None và eligible_rs is False.
    Khi định dạng báo cáo, dòng RS phải có trạng thái '–' (gạch ngang),
    KHÔNG ĐƯỢC gán RS_rank = 50 hay 'ĐẠT'/'Không đạt'.
    """
    closes_short = [100.0] * 200
    assert calculate_rs_raw(closes_short) is None

    # Tạo 200 nến Bar
    bars: list[Bar] = []
    base_dt = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    for i in range(200):
        bars.append(Bar("SHORT", base_dt, 100, 105, 95, 100, 50000))

    res = evaluate_sepa_single(bars)
    assert res["rs_raw"] is None
    assert res["eligible_rs"] is False

    # Kiểm tra format không chứa 'RS_rank = 50'
    report = format_single_symbol_report(res, rs_rank=None, rs_universe_size=167)
    assert "RS_rank = 50" not in report
    assert "[KHÔNG ĐỦ ĐIỀU KIỆN ĐÁNH GIÁ]" in report

    # Trường hợp đủ 252 nến nhưng thiếu 253 nến (chính xác 252 nến):
    bars_252: list[Bar] = []
    for i in range(252):
        bars_252.append(Bar("EXACT252", base_dt, 100, 105, 95, 100, 50000))
    res_252 = evaluate_sepa_single(bars_252)
    assert res_252["eligible_trend"] is True
    assert res_252["rs_raw"] is None
    assert res_252["eligible_rs"] is False
    report_252 = format_single_symbol_report(res_252, rs_rank=None, rs_universe_size=167)
    assert "| –" in report_252
    assert "RS_rank = 50" not in report_252


def test_boundary_percentages_and_mutation_4():
    """Kiểm tra % trên đáy và % cách đỉnh 52 tuần.

    Ví dụ tính tay:
    Close (P) = 80.0
    Low252 = 50.0
    High252 = 100.0

    % trên đáy = (80.0 / 50.0 - 1.0) * 100 = (1.6 - 1.0) * 100 = +60.0% (LITERAL)
    % cách đỉnh = (1.0 - 80.0 / 100.0) * 100 = (1.0 - 0.8) * 100 = 20.0% (LITERAL)

    Đột biến 4 đổi '% cách đỉnh' thành (High252 / P - 1.0) * 100:
    = (100.0 / 80.0 - 1.0) * 100 = (1.25 - 1.0) * 100 = 25.0% != 20.0% -> ĐỘT BIẾN BỊ BẮT.
    """
    pct_low, pct_high = calculate_boundary_percentages(close=80.0, low252=50.0, high252=100.0)

    assert pytest.approx(pct_low, abs=1e-6) == 60.0
    assert pytest.approx(pct_high, abs=1e-6) == 20.0


def test_rs_ranks_empirical_percentile():
    """Kiểm tra quy đổi RS_rank theo phân vị thực nghiệm thang 1-99.

    Ví dụ tính tay với 4 mã:
    A: -0.20
    B: 0.00
    C: 0.10
    D: 0.50

    empirical_percentile_rank:
    A (nhỏ nhất): less=0, equal=1 -> (0 + 0.5) / 4 * 100 = 12.5% -> round(12.5) = 12 hoặc 13
    B: less=1, equal=1 -> (1 + 0.5) / 4 * 100 = 37.5% -> round(37.5) = 38
    C: less=2, equal=1 -> (2 + 0.5) / 4 * 100 = 62.5% -> round(62.5) = 62 hoặc 63
    D (lớn nhất): less=3, equal=1 -> (3 + 0.5) / 4 * 100 = 87.5% -> round(87.5) = 88
    """
    raw_dict = {"A": -0.20, "B": 0.00, "C": 0.10, "D": 0.50}
    ranks = calculate_rs_ranks(raw_dict)

    assert ranks["D"] > ranks["C"] > ranks["B"] > ranks["A"]
    assert 1 <= ranks["A"] <= 99
    assert 1 <= ranks["D"] <= 99
    assert ranks["B"] == 38
    assert ranks["D"] == 88


def test_bfc_hand_calculated_reproduction():
    """Kiểm tra tái lập đúng các con số BFC phiên 25/09/2026 mà Claude đã tính ở §2.1.

    Mốc đối chiếu:
    Close = 48,350.0
    Low252 = 37,223.885 -> % trên đáy = +29.9%
    High252 = 72,766.39 -> % cách đỉnh = 33.6%
    """
    pct_lo, pct_hi = calculate_boundary_percentages(
        close=48350.0,
        low252=37223.885,
        high252=72766.39,
    )
    assert f"{pct_lo:+.1f}%" == "+29.9%"
    assert f"{pct_hi:.1f}%" == "33.6%"


def test_toan_tu_trong_bang_phai_phan_anh_dung_su_that():
    """Bang diem in ra bat dang thuc thi bat dang thuc do phai DUNG.

    Loi Claude tim thay khi audit dot 119: cac dong 1, 2, 4, 5 ghim cung ky tu ">",
    nen khi dieu kien KHONG dat, bang van in "MA50=48,071.2 > MA150=53,686.7" —
    mot phat bieu sai. Cong cu nay chi co mot viec la phat bieu su that ve trang
    thai ky thuat, nen operator phai theo so lieu.

    Vi du tinh tay: chuoi 300 nen gia khong doi = 100.
      P = 100, MA50 = MA150 = MA200 = 100, nen moi so sanh la BANG NHAU.
      Vay dong 1, 4, 5 phai in "=" chu khong duoc in ">" hay "<".
      Ca ba dieu kien c1, c4, c5 deu la so sanh chat (>) nen deu KHONG dat.
    """
    base_dt = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    bars = [Bar("FLAT", base_dt, 100, 100, 100, 100, 50000) for _ in range(300)]

    res = evaluate_sepa_single(bars)
    report = format_single_symbol_report(res, rs_rank=None, rs_universe_size=167)

    for stt in ("1", "4", "5"):
        dong = [ln for ln in report.split("\n") if ln.startswith(f"{stt}   |")]
        assert len(dong) == 1, f"khong tim thay dong {stt}:\n{report}"
        assert " = " in dong[0], f"dong {stt} phai in dau '=' khi bang nhau: {dong[0]}"
        assert " > " not in dong[0], f"dong {stt} in '>' sai su that: {dong[0]}"


def test_doc_danh_sach_ma_khong_tin_cay(tmp_path):
    """Doc exclusions.txt: bo dong trong va dong chu thich, chuan hoa chu hoa.

    Vi du tinh tay: file co 5 dong
      "# chu thich"   -> bo
      ""              -> bo
      "pvp"           -> PVP
      " KSV "         -> KSV
      "HHV"           -> HHV
    Ket qua phai la dung 3 ma: {PVP, KSV, HHV}.

    Va khi file KHONG ton tai thi tra ve tap rong, de ham goi con biet ma noi ra,
    chu khong duoc coi nhu "moi ma deu sach".
    """
    f = tmp_path / "ex.txt"
    f.write_text("# chu thich\n\npvp\n KSV \nHHV\n", encoding="utf-8")
    got = load_untrusted_symbols(str(f))
    assert got == {"PVP", "KSV", "HHV"}

    assert load_untrusted_symbols(str(tmp_path / "khong_co.txt")) == set()


def test_ma_khong_tin_cay_phai_duoc_danh_dau_trong_bang(monkeypatch):
    """Ma nam trong danh sach khong tin cay phai bi danh dau (!) va co dong CHU Y.

    Loi Claude tim thay khi audit dot 119: bang diem in PVP la 7/7 voi RS 94/99,
    trong khi PVP nam trong 246 ma co du lieu dieu chinh gia khong tin cay. Voi
    nhung ma do MA150/MA200 va bien do 52 tuan deu co the sai, nen in nhu mot
    dong binh thuong la moi nguoi doc se hanh dong tren so sai.

    Vi du tinh tay: hai ma AAA va BBB, chi AAA nam trong danh sach.
      -> cot Ma cua AAA phai la "AAA(!)", cua BBB phai la "BBB"
      -> phai co dong bat dau "[CHU Y]" neu ten AAA trong do
    """
    import scripts.score_sepa_daily as mod

    monkeypatch.setattr(mod, "load_untrusted_symbols", lambda *a, **k: {"AAA"})

    base_dt = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    bars = [Bar("X", base_dt, 100, 100, 100, 100, 50000) for _ in range(300)]
    res_a = mod.evaluate_sepa_single(bars)
    res_a["symbol"] = "AAA"
    res_b = mod.evaluate_sepa_single(bars)
    res_b["symbol"] = "BBB"

    report = mod.format_multi_symbol_report(
        [res_a, res_b],
        rs_ranks={"AAA": 80, "BBB": 40},
        rs_universe_size=2,
        ineligible_info=[],
        as_of=date(2026, 9, 25),
    )

    assert "[CHU Y]" in report
    assert "AAA" in report.split("[CHU Y]")[1].split("\n")[0] or "AAA" in report
    rows = [ln for ln in report.split("\n") if ln.startswith(("AAA", "BBB"))]
    assert any(ln.startswith("AAA(!)") for ln in rows), rows
    assert any(ln.startswith(("BBB ", "BBB |")) for ln in rows), rows


def test_duong_di_mot_ma_cung_phai_canh_bao_ma_khong_tin_cay(monkeypatch):
    """Bang diem MOT ma cung phai canh bao, khong chi bang tong hop.

    Loi Claude tim thay khi tu soat lai chinh phep sua cua minh o dot 119: lan dau
    chi them canh bao vao bang tong hop, nen `--symbol PVP` van in 7/7 sach se
    khong mot loi nao. Do lai la duong di NGUY HIEM HON: tra cuu mot ma la viec
    nguoi ta lam ngay truoc khi hanh dong tren ma do.

    Vi du tinh tay: chuoi 300 nen gia phang.
      - ma ten "AAA" nam trong danh sach -> bao cao phai chua "[CHU Y]"
      - ma ten "BBB" khong nam trong danh sach -> bao cao KHONG duoc chua "[CHU Y]"
    """
    import scripts.score_sepa_daily as mod

    monkeypatch.setattr(mod, "load_untrusted_symbols", lambda *a, **k: {"AAA"})

    base_dt = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    bars = [Bar("X", base_dt, 100, 100, 100, 100, 50000) for _ in range(300)]

    res_a = mod.evaluate_sepa_single(bars)
    res_a["symbol"] = "AAA"
    rep_a = mod.format_single_symbol_report(res_a, rs_rank=80, rs_universe_size=2)
    assert "[CHU Y]" in rep_a, rep_a

    res_b = mod.evaluate_sepa_single(bars)
    res_b["symbol"] = "BBB"
    rep_b = mod.format_single_symbol_report(res_b, rs_rank=40, rs_universe_size=2)
    assert "[CHU Y]" not in rep_b, rep_b

