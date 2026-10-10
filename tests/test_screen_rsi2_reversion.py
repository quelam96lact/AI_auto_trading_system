"""Test suite cho scripts/screen_rsi2_reversion.py — Brief đợt 177 §3 (ĐĂNG KÝ TRƯỚC).

Toàn bộ dữ liệu DỰNG TAY, KHÔNG đọc DB. 10 ca kiểm thử theo đúng danh sách brief:
1. RSI(2) tính tay khớp công thức Wilder; chuỗi chỉ tăng -> 100.
2. Tín hiệu trên MA200 và dưới MA200.
3. Không nhìn tương lai.
4. Giá trần không vào được lệnh.
5. Hai lý do thoát: hồi phục MA5 và hết giờ 10 phiên.
6. Ràng buộc T+2: thoát kích hoạt ở phiên E thoát tại E+2.
7. Một vị thế mỗi mã: phiên thoát vẫn tính là đang giữ.
8. Niêm phong: nến >= 2023-01-01 ném lỗi.
9. Điều kiện 5: bỏ 1% lệnh lãi nhất.
10. Đối chứng dương và âm.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pytest

from scripts.screen_rsi2_reversion import (
    IS_START,
    MA_EXIT,
    MA_LONG,
    MAX_HOLD,
    RSI_PERIOD,
    RSI_THRESHOLD,
    compute_rsi2,
    evaluate,
    find_signal,
    simulate_symbol,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.stock_study import validate_sealed_bars

VOL = 25_000_000  # close ~100 -> 2.5 tỷ turnover/phiên, vượt ngưỡng 2 tỷ


def _dates(n: int, start: date = date(2016, 1, 4)) -> list[date]:
    """n ngày giao dịch (bỏ thứ 7, CN), bắt đầu từ start."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def bars_from(
    closes: list[float],
    symbol: str = "AAA",
    volume: int = VOL,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    start: date = date(2016, 1, 4),
) -> list[Bar]:
    """Tạo danh sách nến từ giá đóng cửa."""
    ds = _dates(len(closes), start=start)
    out: list[Bar] = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else (closes[i - 1] if i else c)
        h = highs[i] if highs else max(o, c)
        l = lows[i] if lows else min(o, c)
        out.append(
            Bar(
                symbol=symbol,
                ts=datetime(ds[i].year, ds[i].month, ds[i].day, tzinfo=TZ),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=volume,
            )
        )
    return out


# ============ 1. RSI(2) tính tay ============


def test_1_rsi2_tinh_tay() -> None:
    # Chuỗi [10, 11, 10.5, 10, 9] tính tay đúng theo công thức Wilder n=2
    closes = [10.0, 11.0, 10.5, 10.0, 9.0]
    rsi = compute_rsi2(closes)

    assert rsi[0] is None
    assert rsi[1] is None
    # i=2: U=(1+0)/2=0.5, D=(0+0.5)/2=0.25 -> AU/AD=2 -> RSI = 100 - 100/3 = 66.66666666666667
    assert rsi[2] is not None and abs(rsi[2] - (100.0 - 100.0 / 3.0)) < 1e-9
    # i=3: U=(0.5+0)/2=0.25, D=(0.25+0.5)/2=0.375 -> AU/AD=2/3 -> RSI = 100 - 100/(5/3) = 40.0
    assert rsi[3] is not None and abs(rsi[3] - 40.0) < 1e-9
    # i=4: U=(0.25+0)/2=0.125, D=(0.375+1)/2=0.6875 -> AU/AD=2/11 -> RSI = 100 - 1100/13
    assert rsi[4] is not None and abs(rsi[4] - (100.0 - 1100.0 / 13.0)) < 1e-9

    # Chuỗi chỉ tăng -> RSI = 100
    closes_up = [10.0, 11.0, 12.0, 13.0, 14.0]
    rsi_up = compute_rsi2(closes_up)
    assert all(r == 100.0 for r in rsi_up[2:])

    assert (RSI_PERIOD, RSI_THRESHOLD, MA_LONG, MA_EXIT, MAX_HOLD) == (2, 10.0, 200, 5, 10)


# ============ 2. Tín hiệu trên MA200 và dưới MA200 ============


def test_2_tin_hieu_tren_ma200_va_duoi_ma200() -> None:
    # 263 nến: 254 nến nền 80.0, 6 nến tăng (95..105), 3 nến giảm đưa RSI2 < 10 (104, 101, 95)
    # Tín hiệu duy nhất tại t = 262
    closes = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    bars = bars_from(closes, start=date(2016, 1, 4))
    t = len(bars) - 1
    assert t == 262

    # Ngày tại t nằm trong IS (2017)
    assert bars[t].ts.date() >= IS_START

    sigs = [i for i in range(len(bars)) if find_signal(bars, i) is not None]
    assert sigs == [262], f"Phải có đúng một tín hiệu tại index 262, thực tế {sigs}"

    sig = find_signal(bars, t)
    assert sig is not None
    assert sig["rsi2"] < 10.0
    assert sig["close"] > sig["ma200"]

    # Cùng chuỗi nhưng giá lịch sử là 120.0 -> MA200 ~ 118 > 95.0 -> không có tín hiệu
    closes_below = [120.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    bars_below = bars_from(closes_below, start=date(2016, 1, 4))
    sig_below = find_signal(bars_below, t)
    assert sig_below is None, "Dưới MA200 thì KHÔNG có tín hiệu"


# ============ 3. Không nhìn tương lai ============


def test_3_sua_nen_sau_t_khong_doi_tin_hieu_tai_t() -> None:
    closes = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0] + [96.0] * 30
    bars = bars_from(closes, start=date(2016, 1, 4))
    t = 262
    assert t < len(bars) - 1

    sig_before = find_signal(bars, t)
    assert sig_before is not None

    # Thay đổi mọi nến sau t
    changed = list(closes)
    for i in range(t + 1, len(changed)):
        changed[i] = closes[i] * 1.5
    bars_after = bars_from(changed, start=date(2016, 1, 4))
    sig_after = find_signal(bars_after, t)
    assert sig_after == sig_before


# ============ 4. Giá trần không vào được lệnh ============


def test_4_gia_tran_bo_tin_hieu() -> None:
    base = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    closes = list(base) + [100.0 + i for i in range(15)]
    # Open tại t+1 (263) = 95.0 * 1.15 (trần)
    opens = list(closes)
    t = 262
    opens[t + 1] = closes[t] * 1.15
    bars = bars_from(closes, opens=opens, start=date(2016, 1, 4))

    stats: dict[str, int] = {}
    trades = simulate_symbol(bars, "AAA", stats=stats)
    assert len(trades) == 0
    assert stats.get("ceiling", 0) >= 1


# ============ 5. Hai lý do thoát: hồi phục MA5 và hết giờ ============


def test_5_hai_ly_do_thoat() -> None:
    base = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    t = 262
    E = t + 1  # 263

    # Ca 1: Hồi phục trên MA5 tại E+3 (266) -> thoát close E+4 (267) lý do "hoi_phuc"
    closes_hp = list(base) + [95.0, 95.0, 95.0, 110.0] + [110.0] * 15
    bars_hp = bars_from(closes_hp, start=date(2016, 1, 4))
    trades_hp = simulate_symbol(bars_hp, "AAA")
    assert len(trades_hp) == 1
    tr_hp = trades_hp[0]
    assert tr_hp["entry_i"] == E
    assert tr_hp["exit_i"] == E + 4
    assert tr_hp["reason"] == "hoi_phuc"

    # Ca 2: Đi ngang dưới MA5 -> thoát close E+10 (273) lý do "het_gio"
    closes_hg = list(base) + [94.0 - 0.1 * i for i in range(11)] + [100.0] * 10
    bars_hg = bars_from(closes_hg, start=date(2016, 1, 4))
    trades_hg = simulate_symbol(bars_hg, "AAA")
    assert len(trades_hg) == 1
    tr_hg = trades_hg[0]
    assert tr_hg["entry_i"] == E
    assert tr_hg["exit_i"] == E + 10
    assert tr_hg["reason"] == "het_gio"


# ============ 6. Ràng buộc T+2: thoát kích hoạt ở E thoát tại E+2 ============


def test_6_t2_dieu_kien_thoat_o_phien_e() -> None:
    base = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    t = 262
    E = t + 1  # 263

    # Tại E (263), giá bật mạnh ngay: close[E] = 110.0 > MA5[E]
    closes = list(base) + [110.0, 85.0, 85.0, 85.0, 85.0, 85.0]
    bars = bars_from(closes, start=date(2016, 1, 4))
    trades = simulate_symbol(bars, "AAA")
    assert len(trades) == 1
    tr = trades[0]
    assert tr["entry_i"] == E
    # Điều kiện hồi phục kích hoạt ở E, nhưng do T+2 nên thoát ở E+2
    assert tr["exit_i"] == E + 2
    assert tr["reason"] == "hoi_phuc"


# ============ 7. Một vị thế mỗi mã ============


def test_7_mot_vi_the_moi_ma() -> None:
    base = [80.0] * 254 + [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    # Sig 1 tại 262, E=263, exit tại 267
    closes = list(base) + [95.0, 95.0, 95.0, 110.0, 110.0]
    # Sau exit tại 267: tạo sóng giảm mới tại 268..276 để sinh tín hiệu 2
    closes += [95.0, 97.0, 99.0, 101.0, 103.0, 105.0, 104.0, 101.0, 95.0]
    closes += [95.0, 95.0, 95.0, 110.0, 110.0]
    bars = bars_from(closes, start=date(2016, 1, 4))

    trades = simulate_symbol(bars, "AAA")
    assert len(trades) == 2
    assert trades[0]["exit_i"] < trades[1]["entry_i"]


# ============ 8. Niêm phong ============


def test_8_niem_phong() -> None:
    # Nến >= 2023-01-01 phải ném lỗi
    b_sealed = Bar("AAA", datetime(2023, 1, 3, tzinfo=TZ), 10.0, 11.0, 9.0, 10.5, 1000)
    with pytest.raises(ValueError, match="sealed|niêm phong|2023"):
        validate_sealed_bars([b_sealed])


# ============ 9. Điều kiện 5: Bỏ 1% lệnh lãi nhất ============


def test_9_dieu_kien_5_bo_1_phan_tram_lenh_lai_nhat() -> None:
    # Ca 1: 100 lệnh, trong đó 1 lệnh +500% (excess +500%) và 99 lệnh vượt trội -0.1% (-0.001)
    # Bỏ 1% (1 lệnh lãi nhất) -> 99 lệnh còn lại có mean excess = -0.001 < 0 -> cond5 KHÔNG ĐẠT
    trades_bad: list[dict] = []
    # 1 lệnh khủng
    trades_bad.append({
        "net": 5.0,
        "excess": 5.0,
        "entry_date": date(2018, 1, 1),
    })
    for i in range(99):
        trades_bad.append({
            "net": -0.001,
            "excess": -0.001,
            "entry_date": date(2018, 1, 2 + (i % 20)),
        })
    res_bad = evaluate(trades_bad, [-0.001] * 12)
    assert res_bad["cond5"] is False, "Phải loại trừ outlier 1% lãi nhất -> cond5 False"

    # Ca 2: 100 lệnh đều có excess +0.5% (+0.005) -> cond5 ĐẠT
    trades_good: list[dict] = []
    for i in range(100):
        trades_good.append({
            "net": 0.01,
            "excess": 0.005,
            "entry_date": date(2018, 1, 2 + (i % 20)),
        })
    res_good = evaluate(trades_good, [0.005] * 12)
    assert res_good["cond5"] is True, "Tất cả lệnh đều dương -> cond5 True"


# ============ 10. Đối chứng dương và âm ============


def test_10_doi_chung_duong_va_am() -> None:
    # Đối chứng dương: Dựng tập lệnh trong IS thỏa mãn cả cond2-cond5
    # 290 lệnh thắng +5% và 30 lệnh thua -1% -> PF = (290*0.05)/(30*0.01) = 48.33 > 1.2
    trades_pos: list[dict] = []
    series_pos: list[float] = []
    ds = _dates(350, start=date(2017, 1, 2))
    for i in range(290):
        d = ds[i]
        trades_pos.append({
            "net": 0.05,
            "excess": 0.04,
            "entry_date": d,
        })
    for i in range(290, 320):
        d = ds[i]
        trades_pos.append({
            "net": -0.01,
            "excess": -0.01,
            "entry_date": d,
        })
    for m in range(40):
        series_pos.append(0.04)

    res_pos = evaluate(trades_pos, series_pos)
    assert res_pos["cond1"] is True
    assert res_pos["cond2"] is True
    assert res_pos["cond3"] is True
    assert res_pos["cond4"] is True
    assert res_pos["cond5"] is True
    assert res_pos["dat"] is True

    # Đối chứng âm: Lệnh đi ngẫu nhiên qua random.Random(7)
    rng = random.Random(7)
    trades_neg: list[dict] = []
    series_neg: list[float] = []
    for i in range(320):
        d = ds[i]
        ret = rng.gauss(-0.01, 0.04)
        exc = ret - 0.005
        trades_neg.append({
            "net": ret,
            "excess": exc,
            "entry_date": d,
        })
    for m in range(40):
        series_neg.append(rng.gauss(-0.01, 0.02))

    res_neg = evaluate(trades_neg, series_neg)
    assert res_neg["dat"] is False, "Dữ liệu ngẫu nhiên âm không được ĐẠT"
