"""Test cho scripts/screen_pullback_trend.py — Brief đợt 173 §3.

Toàn bộ dữ liệu DỰNG TAY, không đọc DB. Chín ca theo đúng danh sách brief.
"""

from datetime import date, datetime, timedelta

import pytest

from scripts.screen_pullback_trend import (
    MAX_HOLD,
    MIN_TURNOVER,
    PULLBACK_MAX,
    PULLBACK_MIN,
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

VOL = 20_000_000  # close ~120 -> turnover ~2,4 tỷ/phiên, vượt ngưỡng 2 tỷ của §1.2


def _dates(n: int, start: date = date(2016, 1, 4)) -> list[date]:
    """n ngày GIAO DỊCH (bỏ thứ Bảy, Chủ Nhật), bắt đầu từ thứ Hai."""
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
) -> list[Bar]:
    """Nến từ danh sách close. open[i] = close[i-1] (hoặc `opens`), high/low bao quanh."""
    ds = _dates(len(closes))
    out: list[Bar] = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else (closes[i - 1] if i else c)
        out.append(
            Bar(
                symbol,
                datetime(ds[i].year, ds[i].month, ds[i].day, tzinfo=TZ),
                o,
                max(o, c),
                min(o, c),
                c,
                volume,
            )
        )
    return out


def _trend_base(n: int = 260, start: float = 100.0, step: float = 0.12) -> list[float]:
    """Chuỗi nền TĂNG chậm để close > MA200 và MA50 > MA200."""
    return [start + step * i for i in range(n)]


def _pullback_and_bounce(
    peak: float, depth: float, bounce: float = 0.06
) -> list[float]:
    """5 phiên điều chỉnh đúng `depth` dưới đỉnh, rồi một phiên bật lên `bounce`.

    `bounce` phải LỚN HƠN bước điều chỉnh (depth/4) thì close phiên bật mới vượt
    `high` của phiên trước đó (high của nến giảm giá = open = close phiên trước).
    """
    low = peak * (1 - depth)
    step = (peak - low) / 4.0
    closes = [peak - step * (i + 1) for i in range(5)]
    closes.append(closes[-1] * (1 + bounce))
    return closes


def _series_with_signal(depth: float = 0.10) -> list[float]:
    base = _trend_base()
    peak = base[-1]
    return base + _pullback_and_bounce(peak, depth)


# ============ 1. Tín hiệu đúng ============


def test_tin_hieu_dung_ngay_va_bien_do_sau():
    bars = bars_from(_series_with_signal(0.10))
    sigs = [i for i in range(len(bars)) if find_signal(bars, i) is not None]
    assert len(sigs) == 1, f"đúng MỘT tín hiệu, thực tế {sigs}"
    assert sigs[0] == len(bars) - 1, "tín hiệu ở phiên bật lên (phiên cuối)"

    for depth in (0.03, 0.20):
        b = bars_from(_series_with_signal(depth))
        got = [i for i in range(len(b)) if find_signal(b, i) is not None]
        assert (
            got == []
        ), f"điều chỉnh {depth:.0%} nằm ngoài [5%,15%] -> không tín hiệu, thực tế {got}"

    assert (PULLBACK_MIN, PULLBACK_MAX) == (0.05, 0.15)


# ============ 2. Không nhìn tương lai ============


def test_sua_nen_sau_t_khong_doi_tin_hieu_tai_t():
    """Phải có NẾN SAU t thì phép thử mới có nghĩa (nếu t là nến cuối thì không sửa được gì)."""
    closes = _series_with_signal(0.10) + [130.0] * 30  # 30 nến SAU phiên có tín hiệu
    bars = bars_from(closes)
    t = next(i for i in range(len(bars)) if find_signal(bars, i) is not None)
    before = find_signal(bars, t)
    assert before is not None, "dữ liệu dựng tay phải có tín hiệu"
    assert (
        t < len(bars) - 1
    ), "tín hiệu phải nằm TRƯỚC cuối chuỗi mới kiểm được nhìn trước"

    changed = list(closes)
    for i in range(t + 1, len(changed)):
        changed[i] = closes[i] * 1.5
    bars_after = bars_from(changed)
    assert (
        find_signal(bars_after, t) == before
    ), "đổi nến SAU t không được đổi tín hiệu tại t"


# ============ 3. Vào ở open t+1, loại giá trần ============


def test_open_t_plus_1_gia_tran_thi_khong_vao_lenh():
    closes = _series_with_signal(0.10)
    bars = bars_from(closes)
    t = len(closes) - 1
    assert find_signal(bars, t) is not None

    # nến t+1 có open = trần (7% trên close t) -> entry_status = 'ceiling'
    # `opens` phải cùng quy ước với bars_from: open[i] = close[i-1]
    closes2 = closes + [closes[-1] * 1.02]
    opens2 = [closes[0]] + list(closes)
    opens2[-1] = closes[-1] * 1.07
    bars2 = bars_from(closes2, opens=opens2)
    trades = simulate_symbol(bars2, "HOSE", "AAA")
    assert trades == [], f"open ở giá trần -> không có lệnh: {trades}"


# ============ 4. Ba lý do thoát ============


def _series_for_exit(kind: str) -> list[float]:
    base = _trend_base()
    peak = base[-1]
    closes = base + _pullback_and_bounce(peak, 0.10)
    entry_open = closes[-1]
    if kind == "stop":
        # d=E bị chặn bởi T+2 -> chạm lại ở d=E+1, thoát ở close E+2 (cần đủ nến E+2)
        closes += [entry_open * (1 - STOP_LOSS - 0.02)] * 4
    elif kind == "tp":
        closes += [peak * 1.001] * 4  # vượt H20
    else:
        closes += [entry_open * (1 - 0.001) + 0.0005 * i for i in range(1, 40)]
    return closes


def test_ba_ly_do_thoat_dung_ly_do_va_dung_phien():
    for kind, reason in (("stop", "STOP"), ("tp", "TP"), ("time", "TIME")):
        bars = bars_from(_series_for_exit(kind))
        trades = simulate_symbol(bars, "HOSE", "AAA")
        assert len(trades) == 1, f"{kind}: phải có đúng 1 lệnh, thực tế {trades}"
        tr = trades[0]
        assert (
            tr["reason"] == reason
        ), f"{kind}: lý do thoát phải là {reason}, thực tế {tr['reason']}"
        if kind == "time":
            # §1.4: thoát ở CLOSE phiên d+1 với d = E+19 -> giữ 20 phiên SAU phiên vào lệnh
            assert (
                tr["exit_i"] == tr["entry_i"] + MAX_HOLD
            ), f"hết giờ: thoát ở close E+20, thực tế E+{tr['exit_i'] - tr['entry_i']}"
        else:
            # thoát ở CLOSE của phiên SAU phiên chạm điều kiện
            assert tr["exit_i"] >= tr["entry_i"] + 1


# ============ 5. Ràng buộc T+2 ============


def test_cat_lo_ngay_phien_vao_khong_thoat_som_hon_E_cong_2():
    base = _trend_base()
    peak = base[-1]
    closes = base + _pullback_and_bounce(peak, 0.10)
    entry_open = closes[-1]
    # nến E (t+1) và E+1 sập sâu: chạm cắt lỗ ngay phiên E
    # (KHÔNG truyền `opens`: mặc định open[i] = close[i-1] đúng là giá vào lệnh)
    closes += [entry_open * 0.90, entry_open * 0.88, entry_open * 0.87]
    bars = bars_from(closes)
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1
    tr = trades[0]
    assert (
        tr["entry_i"] + 2 <= tr["exit_i"]
    ), f"T+2: phiên thoát {tr['exit_i']} phải >= E+2 = {tr['entry_i'] + 2}"


def test_cham_ngay_phien_E_van_duoc_ghi_nhan_thoat_o_E_cong_2():
    """Sửa của Claude khi audit (§1.4: 'kiểm tại CLOSE mỗi phiên d >= E'): điều kiện chạm
    ngay phiên E KHÔNG bị bỏ qua — chỉ bán muộn tới E+2. Ca thật VNM 05/12/2017."""
    base = _trend_base()
    peak = base[-1]
    closes = base + _pullback_and_bounce(peak, 0.10)
    entry_open = closes[-1]
    # E đóng cửa trên H20 (chạm chốt lời), E+1 sập dưới mức cắt lỗ, rồi đi ngang
    closes += [peak * 1.01, entry_open * 0.85] + [entry_open * 0.85] * 5
    bars = bars_from(closes)
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1
    tr = trades[0]
    assert (
        tr["reason"] == "TP"
    ), f"chạm TP ở phiên E phải được ghi nhận, thực tế {tr['reason']}"
    assert tr["exit_i"] == tr["entry_i"] + 2


# ============ 6. Một vị thế mỗi mã ============


def test_tin_hieu_thu_hai_trong_luc_dang_giu_bi_bo():
    base = _trend_base()
    peak = base[-1]
    closes = base + _pullback_and_bounce(peak, 0.10)
    # Trong lúc đang giữ: giá LÊN nhưng CHƯA vượt đỉnh cũ (không chốt lời sớm), rồi điều
    # chỉnh 6% (đủ [5%,15%]), rồi bật lên -> TÍN HIỆU THỨ HAI khi vẫn đang giữ lệnh đầu.
    for _ in range(10):
        closes.append(closes[-1] * 1.005)
    local_high = closes[-1]
    assert (
        local_high < peak
    ), "phải giữ dưới đỉnh cũ để lệnh đầu KHÔNG chốt lời trước tín hiệu 2"
    for i in range(5):
        closes.append(local_high * (1 - 0.06 * (i + 1) / 5))
    closes.append(closes[-1] * 1.03)  # bật lên -> tín hiệu thứ hai
    closes += [closes[-1]] * 3

    bars = bars_from(closes)
    assert any(
        find_signal(bars, i) is not None for i in range(len(bars) // 2, len(bars) - 1)
    ), "dữ liệu dựng tay phải có tín hiệu thứ hai thì phép thử mới có nghĩa"
    trades = simulate_symbol(bars, "HOSE", "AAA")
    assert len(trades) == 1, f"tín hiệu thứ hai trong lúc đang giữ phải bị bỏ: {trades}"


# ============ 7. Vượt trội ============


def test_vuot_troi_bang_loi_nhuan_rong_tru_moc_ew():
    bars = bars_from([100.0] * 3)
    ew = {bars[2].ts.astimezone(TZ).date(): 0.03}
    trade = {
        "entry_i": 1,
        "exit_i": 2,
        "entry_date": bars[1].ts.astimezone(TZ).date(),
        "exit_date": bars[2].ts.astimezone(TZ).date(),
        "net": 0.05,
        "reason": "TP",
    }
    got = excess_of_trade(trade, ew)
    assert got == pytest.approx(0.05 - 0.03, abs=1e-12), f"vượt trội phải là +2%: {got}"


# ============ 8. Niêm phong ============


def test_doc_nen_tu_2023_thi_nem_loi():
    """Hàm đọc phải ném lỗi khi dữ liệu chạm nến niêm phong (2023-01-01)."""
    sealed = bars_from(_trend_base(10)) + [
        Bar("AAA", datetime(2023, 1, 3, tzinfo=TZ), 100, 101, 99, 100, VOL)
    ]

    class FakeStorage:
        def read_daily_bars(self, symbol, start, end):
            return sealed

    with pytest.raises(ValueError, match="niêm phong|Holdout"):
        read_bars(FakeStorage(), "AAA")


# ============ 9. Đối chứng dương / âm ============


def _control_series(hero_move: str, n_cycles: int = 180) -> list[float]:
    """Chuỗi cho mã 'hero': nhiều chu kỳ [tăng nền -> điều chỉnh 10% -> bật lên -> giữ 20 phiên].

    hero_move = 'up'   : sau khi bật lên thì +10% trong 20 phiên; CỨ 4 CHU KỲ có 1 chu kỳ đi
                         ngang để có lệnh thua -> profit factor hữu hạn (không chia cho 0)
    hero_move = 'flat' : đi ngang quanh mức vào lệnh (đối chứng âm)
    """
    closes = [100.0]
    for cycle in range(n_cycles):
        for _ in range(12):  # tăng nền
            closes.append(closes[-1] * 1.01)
        peak = closes[-1]
        for i in range(5):  # điều chỉnh 10%
            closes.append(peak * (1 - 0.10 * (i + 1) / 5))
        closes.append(closes[-1] * 1.06)  # bật lên (vượt high phiên trước) -> tín hiệu
        entry = closes[-1]
        losing = hero_move == "up" and cycle % 4 == 3
        if hero_move == "up" and not losing:
            for _ in range(MAX_HOLD):
                closes.append(closes[-1] * 1.005)
            closes.append(peak)  # trở lại nền để chu kỳ sau bắt đầu từ đỉnh cũ
        else:
            for i in range(MAX_HOLD):
                closes.append(entry * (1 + 0.002 * (1 if i % 2 else -1)))
            # chu kỳ thua: nến thoát (E+20) phải NẰM DƯỚI giá vốn, nếu không lệnh lại hoà/lãi
            closes.append(entry * 0.97 if losing else entry)
    return closes


def _flat_market(n: int, start: float = 1000.0) -> list[float]:
    """Mã 'thị trường': đi ngang, đủ thanh khoản để nằm trong mốc EW."""
    return [start * (1 + 0.0005 * (i % 3 - 1)) for i in range(n)]


def _run_control(hero_move: str, n_cycles: int = 120):
    """`n_cycles` đủ lớn để dữ liệu phủ hết cửa sổ IS 2017-2022; cứ 4 chu kỳ có 1 chu kỳ thua
    để profit factor hữu hạn (không chia cho 0)."""
    hero = bars_from(_control_series(hero_move, n_cycles=n_cycles), symbol="AAA")
    m1 = bars_from(_flat_market(len(hero)), symbol="BBB", volume=3_000_000)
    m2 = bars_from(_flat_market(len(hero)), symbol="CCC", volume=3_000_000)
    by_symbol = {"AAA": hero, "BBB": m1, "CCC": m2}
    exchange = {"AAA": "HOSE", "BBB": "HOSE", "CCC": "HOSE"}
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
    assert res["p"] < 0.05, f"đối chứng dương phải ĐẠT điều kiện 2: p={res['p']}"
    assert res["cond3"] and res["cond4"], f"đối chứng dương phải ĐẠT (3),(4): {res}"


def test_doi_chung_am_khong_dat():
    _trades, _series, res = _run_control("flat")
    assert not (
        res["cond3"] and res["cond4"]
    ), f"đi ngang quanh mốc thì KHÔNG được ĐẠT (3),(4): {res}"
