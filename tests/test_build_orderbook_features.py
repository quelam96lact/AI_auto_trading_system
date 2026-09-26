"""Test cho scripts/build_orderbook_features.py (Brief dot 93).

Kiem chung 7 nhom theo muc 4 cua brief:
1. Mot phut co 3 QUOTE + 2 TRADE -> kiem TUNG COT bang so tinh tay, gom ca viec
   mid_close lay dung QUOTE CUOI (khong phai dau, khong phai trung binh).
2. ofi co dau dung: 1 lenh B 10 va 1 lenh S 4 -> ofi = 6, trade_qty = 14.
3. Phut khong co QUOTE -> cot QUOTE la None; phut khong co TRADE -> ofi = 0
   (KHONG phai None) — phan biet "khong co du lieu" voi "khong co giao dich".
4. imb_top1 o hai bien: chi ben mua -> +1; chi ben ban -> -1; can bang -> 0.
5. Ca bien chia cho 0: bid_volumes[0] va ask_volumes[0] deu 0 -> imb None, khong no.
6. Do khoang thieu: chuoi dung tay co 5 phut trong lien tiep -> bao dung 5 va dung moc.
7. (Kiem thu pha hoai o cong cu ngoai: doi mid_close sang QUOTE DAU -> ca 1 do.)
"""

from datetime import date, datetime

import pytest

from scripts.build_orderbook_features import (
    build_minute_features,
    longest_missing_run,
    session_minutes,
)
from trading.calendar_vn import TZ

NGAY = date(2026, 9, 25)


def _quote(hh: int, mm: int, ss: int, bid_vols: list[int], ask_vols: list[int],
           bid_px: float = 101.0, ask_px: float = 102.0) -> dict:
    """Dung mot tin QUOTE theo dung khuon file that (10 buoc gia moi ben)."""
    return {
        "type": "DataType.QUOTE",
        "trading_time": f"2026/09/25 {hh:02d}:{mm:02d}:{ss:02d}",
        "symbol": "41I1GA000",
        "bid_prices": [bid_px - i * 0.1 for i in range(10)],
        "bid_volumes": bid_vols + [0] * (10 - len(bid_vols)),
        "ask_prices": [ask_px + i * 0.1 for i in range(10)],
        "ask_volumes": ask_vols + [0] * (10 - len(ask_vols)),
        "recv_ts": f"2026-09-25T{hh:02d}:{mm:02d}:{ss:02d}.000000+07:00",
    }


def _trade(hh: int, mm: int, ss: int, side: str, qty: int, price: float = 101.5) -> dict:
    """Dung mot tin TRADE theo dung khuon file that."""
    return {
        "type": "DataType.TRADE",
        "trading_time": f"2026/09/25 {hh:02d}:{mm:02d}:{ss:02d}",
        "symbol": "41I1GA000",
        "price": price,
        "quantity": qty,
        "side": side,
        "total_volume": 100,
        "recv_ts": f"2026-09-25T{hh:02d}:{mm:02d}:{ss:02d}.000000+07:00",
    }


def _row_at(rows: list, hh: int, mm: int):
    for r in rows:
        if r.minute.hour == hh and r.minute.minute == mm:
            return r
    raise AssertionError(f"khong co hang cho phut {hh:02d}:{mm:02d}")


# --- 1. Mot phut: 3 QUOTE + 2 TRADE, kiem tung cot bang so tinh tay ----------------

def test_1_1_mot_phut_3_quote_2_trade_tung_cot_tinh_tay():
    msgs = [
        # QUOTE dau phut: top1 = 2 vs 9 ; top5 = (2+3+4+5+6)=20 vs (9+1+1+1+1)=13
        _quote(9, 3, 10, [2, 3, 4, 5, 6], [9, 1, 1, 1, 1]),
        # QUOTE giua phut (khong duoc dung cho cot nao)
        _quote(9, 3, 30, [7], [7]),
        # QUOTE CUOI phut: bid_px=101.0 -> 101.0 ; ask_px=102.0 -> 102.0
        # top1 = 10 vs 5 ; top5 = 10 vs 25
        _quote(9, 3, 55, [10], [5, 5, 5, 5, 5]),
        _trade(9, 3, 20, "B", 10),
        _trade(9, 3, 40, "S", 4),
    ]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 3)

    assert r.n_quote == 3
    assert r.n_trade == 2
    # mid_close lay QUOTE CUOI: (101.0 + 102.0) / 2 = 101.5
    assert r.mid_close == pytest.approx(101.5)
    assert r.spread == pytest.approx(1.0)
    # imb_top1 = (10 - 5) / (10 + 5)
    assert r.imb_top1 == pytest.approx(5 / 15)
    # imb_top5 = (10 - 25) / (10 + 25)  <- khac top1, chung minh khong lan do sau
    assert r.imb_top5 == pytest.approx(-15 / 35)
    # ofi = 10 - 4 ; trade_qty = 14
    assert r.ofi == pytest.approx(6)
    assert r.trade_qty == pytest.approx(14)


def test_1_2_mid_close_khong_phai_trung_binh_cac_quote_trong_phut():
    """Neu lay trung binh hai quote thi mid = 100.0, con lay quote cuoi thi 200.0."""
    msgs = [
        _quote(9, 5, 10, [1], [1], bid_px=50.0, ask_px=50.0),
        _quote(9, 5, 50, [1], [1], bid_px=199.5, ask_px=200.5),
    ]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 5)
    assert r.mid_close == pytest.approx(200.0)
    assert r.spread == pytest.approx(1.0)


# --- 2. ofi co dau dung ------------------------------------------------------------

def test_2_ofi_dau_dung_B_tru_S():
    msgs = [_trade(9, 7, 5, "B", 10), _trade(9, 7, 9, "S", 4)]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 7)
    assert r.ofi == pytest.approx(6)
    assert r.trade_qty == pytest.approx(14)
    assert r.n_trade == 2
    assert r.n_quote == 0


def test_2b_ofi_am_khi_ban_nhieu_hon():
    msgs = [_trade(9, 8, 5, "S", 30), _trade(9, 8, 9, "B", 5)]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 8)
    assert r.ofi == pytest.approx(-25)
    assert r.trade_qty == pytest.approx(35)


# --- 3. "khong co du lieu" khac "khong co giao dich" ------------------------------

def test_3_1_phut_khong_co_quote_thi_cot_quote_la_none():
    msgs = [_trade(9, 10, 5, "B", 3)]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 10)
    assert r.mid_close is None
    assert r.spread is None
    assert r.imb_top1 is None
    assert r.imb_top5 is None
    # Co TRADE -> ofi la gia tri that
    assert r.ofi == pytest.approx(3)
    assert r.n_quote == 0


def test_3_2_phut_khong_co_trade_thi_ofi_bang_0_khong_phai_none():
    msgs = [_quote(9, 11, 5, [1], [1])]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 11)
    assert r.ofi == 0
    assert r.trade_qty == 0
    assert r.n_trade == 0
    assert r.ofi is not None


def test_3_3_phut_trong_hoan_toan_thi_ofi_van_bang_0():
    rows = build_minute_features([], NGAY)
    r = _row_at(rows, 9, 12)
    assert r.n_quote == 0 and r.n_trade == 0
    assert r.ofi == 0 and r.trade_qty == 0
    assert r.mid_close is None


# --- 4. imb_top1 o hai bien --------------------------------------------------------

def test_4_imb_top1_hai_bien_va_can_bang():
    msgs = [
        _quote(9, 13, 5, [10], [0]),          # chi ben mua -> +1
        _quote(9, 14, 5, [0], [10]),          # chi ben ban  -> -1
        _quote(9, 15, 5, [7], [7]),           # can bang     -> 0
    ]
    rows = build_minute_features(msgs, NGAY)
    assert _row_at(rows, 9, 13).imb_top1 == pytest.approx(1.0)
    assert _row_at(rows, 9, 14).imb_top1 == pytest.approx(-1.0)
    assert _row_at(rows, 9, 15).imb_top1 == pytest.approx(0.0)


# --- 5. Ca bien chia cho 0 ---------------------------------------------------------

def test_5_chia_cho_0_tra_none_khong_no():
    msgs = [_quote(9, 16, 5, [0], [0])]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 16)
    assert r.imb_top1 is None
    assert r.imb_top5 is None
    # Cac cot khac van tinh binh thuong
    assert r.mid_close == pytest.approx(101.5)
    assert r.spread == pytest.approx(1.0)


def test_5b_imb_top5_chia_0_khi_top1_khac_0():
    """top1 co du lieu nhung 5 buoc dau cong lai van > 0 -> khong the None; kiem nguoc lai
    truong hop chi co du lieu o buoc thu 3 (top1 = 0 nen top1 None, top5 khac 0)."""
    msgs = [_quote(9, 17, 5, [0, 0, 5], [0, 0, 2])]
    rows = build_minute_features(msgs, NGAY)
    r = _row_at(rows, 9, 17)
    assert r.imb_top1 is None      # 0 vs 0 -> chia 0
    assert r.imb_top5 == pytest.approx(3 / 7)


# --- 6. Do khoang thieu ------------------------------------------------------------

def test_6_khoang_thieu_5_phut_lien_tiep_bao_dung_5_va_dung_moc():
    # Dien du MOI phut cua phien, chi chua hut 09:05..09:09 -> khoang dai nhat dung la 5
    msgs = [
        _quote(m.hour, m.minute, 10, [1], [1])
        for m in session_minutes(NGAY)
        if not (m.hour == 9 and 5 <= m.minute <= 9)
    ]
    rows = build_minute_features(msgs, NGAY)
    n, start = longest_missing_run(rows, key=lambda r: r.n_quote + r.n_trade == 0)
    assert n == 5
    assert start == datetime(2026, 9, 25, 9, 5, tzinfo=TZ)


def test_6b_khong_co_khoang_thieu_thi_bao_0_va_khong_co_moc():
    msgs = [_quote(m.hour, m.minute, 10, [1], [1]) for m in session_minutes(NGAY)]
    rows = build_minute_features(msgs, NGAY)
    n, start = longest_missing_run(rows, key=lambda r: r.n_quote + r.n_trade == 0)
    assert n == 0
    assert start is None


def test_6c_khoang_thieu_o_giua_lay_dung_khoang_dai_nhat():
    """Chi co du lieu 09:20-09:21 -> cac khoang thieu la 20, 128 (09:22->11:29) va 90
    (13:00->14:29); phai chon dung khoang DAI NHAT la 128 bat dau 09:22."""
    msgs = [_quote(9, 20, 10, [1], [1]), _quote(9, 21, 10, [1], [1])]
    rows = build_minute_features(msgs, NGAY)
    n, start = longest_missing_run(rows, key=lambda r: r.n_quote + r.n_trade == 0)
    assert n == 128
    assert start == datetime(2026, 9, 25, 9, 22, tzinfo=TZ)


# --- Luoi phut ---------------------------------------------------------------------

def test_7_luoi_phut_phu_dung_phien_khop_lenh_lien_tuc():
    rows = build_minute_features([], NGAY)
    assert len(rows) == 240                       # 150 sang (09:00-11:29) + 90 chieu
    assert rows[0].minute == datetime(2026, 9, 25, 9, 0, tzinfo=TZ)
    assert rows[149].minute == datetime(2026, 9, 25, 11, 29, tzinfo=TZ)
    assert rows[150].minute == datetime(2026, 9, 25, 13, 0, tzinfo=TZ)
    assert rows[-1].minute == datetime(2026, 9, 25, 14, 29, tzinfo=TZ)
    # khong co phut nao roi vao gio nghi trua
    assert all(r.minute.hour != 12 for r in rows)


def test_7b_session_minutes_tra_danh_sach_deu_dan():
    mins = session_minutes(NGAY)
    assert len(mins) == len(set(mins)) == 240
    gaps = {(mins[i + 1] - mins[i]).total_seconds() for i in range(len(mins) - 1)}
    # buoc 60 giay, tru mot cho nhay qua nghi trua (11:29 -> 13:00 = 91 phut)
    assert gaps == {60.0, 91 * 60.0}


def test_7c_tin_ngoai_khung_phien_khong_lam_sai_luoi():
    """Tin luc 08:59 va 14:50 nam ngoai khung -> khong tao hang, khong vo luoi."""
    msgs = [
        _quote(8, 59, 30, [1], [1]),
        _quote(14, 50, 30, [1], [1]),
        _quote(10, 30, 0, [1], [1]),
    ]
    rows = build_minute_features(msgs, NGAY)
    assert len(rows) == 240
    assert _row_at(rows, 10, 30).n_quote == 1


def test_7d_phien_atc_khong_lot_vao_dac_trung():
    """14:30-14:45 la ATC, khong phai khop lenh lien tuc (Claude audit dot 93).

    Tren file that 25/09: tin 'TRADE' 14:30-14:44 co side='U', quantity=0; 14:45 la lan
    khop ATC 5.757 HD mot phia. Ban dau o 14:44 nuot ca phut 14:45, nen ofi min va
    trade_qty max cua ca phien CHINH LA lan khop ATC. Tin tu 14:30:00 tro di phai nam
    ngoai luoi; o cuoi luoi 14:29 chi co tin cua chinh no.
    """
    msgs = [
        _trade(14, 29, 59, "B", 3),
        _trade(14, 30, 0, "B", 7),
        _trade(14, 44, 59, "B", 11),
        _trade(14, 45, 0, "S", 5757),
        _quote(14, 45, 0, [1], [1]),
    ]
    rows = build_minute_features(msgs, NGAY)
    assert rows[-1].minute == datetime(2026, 9, 25, 14, 29, tzinfo=TZ)
    assert rows[-1].ofi == 3
    assert rows[-1].trade_qty == 3
    assert rows[-1].n_quote == 0
    assert sum(r.trade_qty for r in rows) == 3
