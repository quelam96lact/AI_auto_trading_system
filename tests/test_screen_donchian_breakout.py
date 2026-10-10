"""Test cho scripts/screen_donchian_breakout.py — Brief đợt 175 §3.

Toàn bộ dữ liệu DỰNG TAY, không đọc DB. Chín ca theo đúng danh sách brief.
"""

from datetime import date, datetime, timedelta

import pytest

from scripts.screen_donchian_breakout import (
    BREAKOUT_LOOKBACK,
    CHANNEL_LOOKBACK,
    MAX_HOLD,
    MIN_TURNOVER,
    STOP_LOSS,
    TURNOVER_WINDOW,
    evaluate,
    ew_returns_by_date,
    excess_of_trade,
    find_signal,
    monthly_excess,
    read_bars,
    simulate_symbol,
)
from trading.calendar_vn import TZ
from trading.models import Bar

VOL = 25_000_000  # close ~100 -> 2,5 tỷ/phiên, vượt ngưỡng 2 tỷ


def _dates(n: int, start: date = date(2017, 1, 2)) -> list[date]:
    """n ngày GIAO DỊCH (bỏ thứ Bảy, Chủ Nhật), bắt đầu từ thứ Hai 02/01/2017.

    Bắt đầu TRONG cửa sổ IS (2017-01-01 → 2022-10-31) để tín hiệu dựng tay không bị
    bộ lọc `is_start`/`is_end` của `simulate_symbol` loại bỏ — đã mắc một lần ở đợt 173.
    """
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def bars_from(closes: list[float], symbol: str = "AAA", volume: int = VOL,
              opens: list[float] | None = None) -> list[Bar]:
    """Nến từ danh sách close. open[i] = close[i-1] (hoặc `opens`), high/low bao quanh."""
    ds = _dates(len(closes))
    out: list[Bar] = []
    for i, c in enumerate(closes):
        o = (opens[i] if opens else (closes[i - 1] if i else c))
        out.append(
            Bar(symbol, datetime(ds[i].year, ds[i].month, ds[i].day, tzinfo=TZ),
                o, max(o, c), min(o, c), c, volume)
        )
    return out


def _signal_index(bars: list[Bar]) -> int | None:
    for i in range(len(bars)):
        if find_signal(bars, i) is not None:
            return i
    return None


# ============ 1. Tín hiệu đúng ============


def test_tin_hieu_pha_dinh_dung_ngay_va_khong_tinh_nen_t():
    closes = [100.0] * 60 + [102.0]
    bars = bars_from(closes)
    sigs = [i for i in range(len(bars)) if find_signal(bars, i) is not None]
    assert sigs == [60], f"đúng một tín hiệu tại phiên phá đỉnh (index 60), thực tế {sigs}"

    # đóng cửa BẰNG ĐÚNG đỉnh (không vượt) -> không tín hiệu
    bars_eq = bars_from([100.0] * 60 + [100.0])
    assert _signal_index(bars_eq) is None, "close == đỉnh 55 phiên thì KHÔNG tính là phá đỉnh"

    # chưa đủ 55 nến trước t -> không tín hiệu
    bars_short = bars_from([100.0] * 40 + [105.0])
    assert _signal_index(bars_short) is None, "chưa đủ 55 nến thì không xét"

    assert (BREAKOUT_LOOKBACK, CHANNEL_LOOKBACK, MAX_HOLD) == (55, 20, 40)


# ============ 2. Không nhìn tương lai ============


def test_sua_nen_sau_t_khong_doi_tin_hieu_tai_t():
    closes = [100.0] * 60 + [102.0] + [103.0] * 30
    bars = bars_from(closes)
    t = 60
    before = find_signal(bars, t)
    assert before is not None
    assert t < len(bars) - 1, "phải có nến SAU t thì phép thử mới có nghĩa"

    changed = list(closes)
    for i in range(t + 1, len(changed)):
        changed[i] = closes[i] * 1.5
    assert find_signal(bars_from(changed), t) == before, "đổi nến SAU t không được đổi tín hiệu tại t"


# ============ 3. Vào ở open t+1, loại giá trần ============


def test_open_t_plus_1_gia_tran_thi_khong_vao_lenh():
    closes = [100.0] * 60 + [102.0] + [103.0]
    opens = [c for c in closes]
    opens[61] = 102.0 * 1.07  # open phiên t+1 ở giá trần (7%)
    bars = bars_from(closes, opens=opens)
    assert find_signal(bars, 60) is not None
    assert simulate_symbol(bars, "HOSE", "AAA") == [], "open ở giá trần -> không có lệnh"


# ============ 4. Ba lý do thoát ============


def _series_for_exit(kind: str) -> list[float]:
    """Tín hiệu ở index 60 (E = 61, open[E] = 102). Ba nến trung tính rồi mới chạm,
    để phiên chạm = E+3 và phiên thoát = E+4 (T+2 không còn chen vào)."""
    closes = [100.0] * 60 + [102.0] + [102.0] * 3
    if kind == "stop":
        closes += [102.0 * (1 - STOP_LOSS) - 0.5] * 4
    elif kind == "channel":
        closes += [99.0] * 4  # thủng đáy 20 phiên (đáy = 100) nhưng chưa tới cắt lỗ
    else:
        # 38 nến tăng đều: dài đúng tới E+40 (hết giờ) nên không sinh tín hiệu thứ hai
        closes += [102.0 * (1 + 0.003 * i) for i in range(1, 39)]
    return closes


def test_ba_ly_do_thoat_dung_ly_do_va_dung_phien():
    for kind, reason in (("stop", "STOP"), ("channel", "CHANNEL"), ("time", "TIME")):
        bars = bars_from(_series_for_exit(kind))
        trades = simulate_symbol(bars, "HOSE", "AAA")
        assert len(trades) == 1, f"{kind}: phải có đúng 1 lệnh, thực tế {trades}"
        tr = trades[0]
        assert tr["reason"] == reason, f"{kind}: lý do phải là {reason}, thực tế {tr['reason']}"
        if kind == "time":
            assert tr["exit_i"] == tr["entry_i"] + MAX_HOLD, (
                f"hết giờ: thoát ở close E+40, thực tế E+{tr['exit_i'] - tr['entry_i']}"
            )
        else:
            # chạm ở phiên E+3 -> thoát ở close phiên SAU đó = E+4
            assert tr["exit_i"] == tr["entry_i"] + 4, (
                f"{kind}: thoát ở close phiên sau phiên chạm (E+4), thực tế "
                f"E+{tr['exit_i'] - tr['entry_i']}"
            )


# ============ 5. Ưu tiên cắt lỗ trước thủng kênh ============


def test_cung_phien_cham_ca_cat_lo_va_thung_kenh_thi_ly_do_la_cat_lo():
    closes = [100.0] * 60 + [102.0] + [102.0 * 0.88] * 4  # 89.76 <= 91.8 (cắt lỗ) VÀ < 100 (kênh)
    bars = bars_from(closes)
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1
    assert trades[0]["reason"] == "STOP", (
        f"cùng phiên chạm cả hai -> cắt lỗ thắng, thực tế {trades[0]['reason']}"
    )


# ============ 6. T+2: chạm ở phiên E vẫn được ghi nhận ============


def test_cham_cat_lo_ngay_phien_E_thi_thoat_o_close_E_cong_2():
    closes = [100.0] * 60 + [102.0] + [102.0 * (1 - STOP_LOSS)] * 4
    bars = bars_from(closes)
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1
    tr = trades[0]
    assert tr["reason"] == "STOP", "chạm ở phiên E phải được GHI NHẬN, không được bỏ qua"
    assert tr["exit_i"] == tr["entry_i"] + 2, (
        f"T+2: phiên thoát = max(d+1, E+2) = E+2, thực tế E+{tr['exit_i'] - tr['entry_i']}"
    )


# ============ 7. Một vị thế mỗi mã ============


def test_tin_hieu_thu_hai_trong_luc_giu_bi_bo_con_sau_khi_thoat_thi_nhan():
    # (a) ĐỈNH ĐÔI: phá đỉnh 102 -> lùi nhẹ 101 (không thủng kênh, không cắt lỗ) -> phá đỉnh 103
    #     => tín hiệu thứ hai xuất hiện TRONG LÚC ĐANG GIỮ -> phải bị bỏ
    closes = [100.0] * 60 + [102.0] + [101.0] * 5 + [103.0] + [103.5] * 40
    bars = bars_from(closes)
    sigs = [i for i in range(len(bars)) if find_signal(bars, i) is not None]
    assert sigs[0] == 60 and len(sigs) >= 2, f"phải có tín hiệu thứ hai: {sigs[:5]}"
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1, f"tín hiệu trong lúc đang giữ phải bị bỏ: {trades}"
    assert sigs[1] <= trades[0]["exit_i"], "tín hiệu 2 phải rơi vào lúc đang giữ mới có nghĩa"

    # (b) tín hiệu NGAY SAU phiên thoát lệnh cũ phải được nhận
    closes2 = [100.0] * 60 + [102.0] + [102.0 * 0.88] * 4  # lệnh 1 cắt lỗ
    closes2 += [100.0] * 60 + [104.0, 104.5]               # nền mới + phá đỉnh mới (+1 nến đệm)
    trades2 = simulate_symbol(bars_from(closes2), "HOSE", "AAA")
    assert len(trades2) == 2, f"tín hiệu sau khi thoát phải được nhận: {trades2}"


# ============ 8. Niêm phong ============


def test_doc_nen_tu_2023_thi_nem_loi():
    sealed = bars_from([100.0] * 10) + [
        Bar("AAA", datetime(2023, 1, 3, tzinfo=TZ), 100, 101, 99, 100, VOL)
    ]

    class FakeStorage:
        def read_daily_bars(self, symbol, start, end):
            return sealed

    with pytest.raises(ValueError, match="niêm phong|Holdout"):
        read_bars(FakeStorage(), "AAA")


# ============ 9. Đối chứng dương / âm ============


def _control_series(move: str, n_cycles: int = 120) -> list[float]:
    """Chu kỳ: đi ngang 60 phiên (đủ dài 55) -> phá đỉnh 2% -> (tăng 15% rồi gãy | đi ngang)."""
    closes = [100.0]
    for cycle in range(n_cycles):
        for _ in range(60):
            closes.append(closes[-1] * 1.001)
        peak = closes[-1]
        closes.append(peak * 1.02)  # phá đỉnh -> tín hiệu
        entry = closes[-1]
        losing = move == "up" and cycle % 4 == 3
        if move == "up" and not losing:
            # lên đủ lâu (25 phiên) để ĐÁY 20 PHIÊN vượt lên TRÊN giá vốn, rồi mới gãy:
            # thủng kênh ở mức ≈ +8% (thắng), và vẫn trên cắt lỗ 10% dưới giá vốn
            for _ in range(25):
                closes.append(closes[-1] * 1.012)
            for _ in range(12):
                closes.append(closes[-1] * 0.972)
        else:
            for i in range(15):
                closes.append(entry * (1 + 0.002 * (1 if i % 2 else -1)))
            if losing:
                # chu kỳ thua: rơi trong THỜI GIAN GIỮ xuống −6% (thủng kênh, trên cắt lỗ)
                for k in range(1, 7):
                    closes.append(entry * (1 - 0.01 * k))
                closes += [entry * 0.94] * 3
            else:
                for i in range(25):
                    closes.append(entry * (1 + 0.002 * (1 if i % 2 else -1)))
    return closes


def _flat_market(n: int, start: float = 1000.0) -> list[float]:
    return [start * (1 + 0.0005 * (i % 3 - 1)) for i in range(n)]


def _run_control(move: str, n_cycles: int = 120):
    hero = bars_from(_control_series(move, n_cycles=n_cycles), symbol="AAA")
    m1 = bars_from(_flat_market(len(hero)), symbol="BBB", volume=3_000_000)
    m2 = bars_from(_flat_market(len(hero)), symbol="CCC", volume=3_000_000)
    by_symbol = {"AAA": hero, "BBB": m1, "CCC": m2}
    exchange = dict.fromkeys(by_symbol, "HOSE")
    trades = []
    for sym, sym_bars in by_symbol.items():
        trades += simulate_symbol(sym_bars, exchange[sym], sym)
    ew = ew_returns_by_date(by_symbol, MIN_TURNOVER, TURNOVER_WINDOW)
    for tr in trades:
        tr["excess"] = excess_of_trade(tr, ew)
    series = monthly_excess(trades)
    return trades, series, evaluate(trades, series)


def test_doi_chung_duong_dat_dieu_kien_2_3_4():
    trades, series, res = _run_control("up")
    assert len(trades) >= 10, f"cần đủ lệnh để bootstrap: {len(trades)}"
    assert len(series) >= 6, f"cần đủ tháng: {len(series)}"
    assert res["mean_excess"] > 0
    assert res["p"] < 0.05, f"đối chứng dương phải ĐẠT (2): p={res['p']}"
    assert res["cond3"] and res["cond4"], f"đối chứng dương phải ĐẠT (3),(4): {res}"


def test_doi_chung_am_khong_dat():
    _trades, _series, res = _run_control("flat")
    assert not (res["cond3"] and res["cond4"]), f"đi ngang quanh mốc -> không ĐẠT (3),(4): {res}"
