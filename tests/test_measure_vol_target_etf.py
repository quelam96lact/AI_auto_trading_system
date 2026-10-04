"""Test cho phép đo volatility targeting trên ETF VN30 — Brief đợt 161.

Toàn bộ test dùng dữ liệu TỔNG HỢP, không chạm DB. Các hàm thuần được gọi trực tiếp.
"""

import math
from datetime import datetime, timedelta

import pytest

from scripts.measure_vol_target_etf import (
    EWMA_LAMBDA,
    ROLL_WINDOW,
    buy_hold,
    clean_price_bars,
    ewma_vol,
    expanding_median,
    rolling_vol,
    simulate,
    target_weights,
    weights_series,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS

SLIP = SLIPPAGE_BPS / 10_000.0


def _bar(day: int, close: float, open_: float | None = None, month: int = 1) -> Bar:
    ts = datetime(2026, month, 1, tzinfo=TZ) + timedelta(days=day - 1)
    o = close if open_ is None else open_
    return Bar("E1VFVN30", ts, o, max(o, close), min(o, close), close, 1000)


# ============ 1. Biến động không đổi -> w* không đổi, không giao dịch thêm ============


def test_bien_dong_khong_doi_thi_khong_giao_dich_them():
    """Giá phẳng + w* hằng số: chỉ có ĐÚNG một lần mua đầu, sau đó không giao dịch."""
    bars = [_bar(d, 100.0) for d in range(1, 61)]
    w_star = [0.5] * len(bars)  # biến động không đổi -> tỷ trọng mục tiêu không đổi

    res = simulate(bars, w_star, threshold=0.20)

    assert len(res.trades) == 1, f"phải chỉ có 1 giao dịch (mua đầu), thực tế {res.trades}"
    assert res.trades[0].side == "BUY"
    assert res.trades[0].weight_after == pytest.approx(0.5)
    # phiên đầu còn ở tiền mặt nên tỷ trọng trung bình hơi dưới 0,5
    assert res.avg_weight == pytest.approx(0.5, abs=0.02)


# ============ 2. Chống nhìn trước ============


def test_doi_gia_sau_phien_t_khong_doi_w_sao_va_giao_dich_truoc_t():
    """Đổi MỌI giá sau phiên t -> w*_t và mọi giao dịch tới phiên t không đổi."""
    n = 80
    bars = [_bar(d, 100.0 + (d % 7) * 0.3) for d in range(1, n + 1)]
    closes = [b.close for b in bars]
    t = 50

    def w_star_for(c: list[float]) -> list[float]:
        # GỌI ĐÚNG hàm mà lần chạy thật dùng (weights_series: gắn theo CHỈ SỐ NẾN).
        # Tự dựng lại chuỗi theo chỉ số lợi suất là lệch một phiên — đã mắc một lần.
        return weights_series(c, kind="ewma")

    w_before = w_star_for(closes)
    res_before = simulate(bars, w_before, threshold=0.20)

    # đổi mạnh mọi giá SAU phiên t
    changed = list(closes)
    for i in range(t + 1, n):
        changed[i] = changed[i] * 1.5
    w_after = w_star_for(changed)

    assert w_before[: t + 1] == pytest.approx(w_after[: t + 1]), (
        "w* tại t và trước t phải KHÔNG đổi khi chỉ đổi giá sau t"
    )

    # và các giao dịch tới phiên t phải y hệt nhau
    before = [(tr.bar_index, tr.side, tr.weight_after) for tr in res_before.trades if tr.bar_index <= t]
    bars_after = [Bar(b.symbol, b.ts, b.open, b.high, b.low, changed[i], b.volume) for i, b in enumerate(bars)]
    res_after = simulate(bars_after, w_after, threshold=0.20)
    after = [(tr.bar_index, tr.side, tr.weight_after) for tr in res_after.trades if tr.bar_index <= t]
    assert before == after, f"giao dịch tới phiên {t} phải y hệt: {before} vs {after}"


# ============ 3. Ngưỡng tái cân bằng ============


def test_nguong_019_khong_giao_dich_021_thi_giao_dich():
    bars = [_bar(d, 100.0) for d in range(1, 41)]

    # bắt đầu bằng tiền mặt (w*_0 = 0 -> không mua, vì mua 0 là không giao dịch)
    w_19 = [0.0] * 20 + [0.19] * 20
    assert len(simulate(bars, w_19, threshold=0.20).trades) == 0, "lệch 0,19 < 0,20 -> không giao dịch"

    w_21 = [0.0] * 20 + [0.21] * 20
    trades = simulate(bars, w_21, threshold=0.20).trades
    assert len(trades) == 1 and trades[0].weight_after == pytest.approx(0.21), "lệch 0,21 >= 0,20 -> phải giao dịch"


# ============ 4. Chi phí một vòng ở giá phẳng ============


def test_mot_vong_gia_phang_mat_dung_cong_thuc():
    bars = [_bar(d, 100.0) for d in range(1, 41)]
    w_star = [1.0] * 20 + [0.0] * 20  # mua full, rồi bán hết

    res = simulate(bars, w_star, threshold=0.0)

    expected = 1.0 - (2 * FEE_RATE + SELL_TAX_RATE + 2 * SLIP)
    assert res.equity_curve[-1] == pytest.approx(expected, abs=1e-9), (
        f"vòng mua-bán ở giá phẳng phải mất đúng 2FEE+TAX+2SLIP: {res.equity_curve[-1]} vs {expected}"
    )
    assert len(res.trades) == 2, f"phải có đúng 2 giao dịch: {res.trades}"


# ============ 5. EWMA ba bước khớp số tính tay ============


def test_ewma_ba_buoc_khop_so_tinh_tay():
    """σ²_0 = r_0²; σ²_t = λσ²_{t-1} + (1-λ)r_t². Với λ = 0,94 và r = 1%, -2%, 3%:

    σ²_1 = 0,94*0,0001 + 0,06*0,0004 = 0,000118
    σ²_2 = 0,94*0,000118 + 0,06*0,0009 = 0,00016492
    """
    returns = [0.01, -0.02, 0.03]
    vols = ewma_vol(returns, lam=EWMA_LAMBDA)

    assert len(vols) == 3
    assert vols[0] == pytest.approx(math.sqrt(0.0001 * 252))
    assert vols[1] == pytest.approx(math.sqrt(0.000118 * 252))
    assert vols[2] == pytest.approx(math.sqrt(0.00016492 * 252))


# ============ 6. Phiên close <= 0 bị loại ============


def test_phien_close_khong_duong_bi_loai():
    bars = [_bar(1, 100.0), _bar(2, 0.0), _bar(3, 101.0), _bar(4, -5.0), _bar(5, 102.0)]
    kept, dropped = clean_price_bars(bars)
    assert dropped == 2
    assert [b.close for b in kept] == [100.0, 101.0, 102.0]


def test_rolling_vol_va_cua_so_mo_rong():
    returns = [0.01, -0.01] * 15
    rv = rolling_vol(returns, window=ROLL_WINDOW)
    assert rv[: ROLL_WINDOW - 1] == [None] * (ROLL_WINDOW - 1), "chưa đủ cửa sổ thì chưa có σ̂"
    assert rv[ROLL_WINDOW - 1] is not None
    med = expanding_median(rv)
    assert med[ROLL_WINDOW - 1] == pytest.approx(rv[ROLL_WINDOW - 1]), "trung vị tới t chỉ dùng dữ liệu tới t"
    assert len(med) == len(rv)

    # trần 1: biến động mục tiêu lớn hơn σ̂ thì vẫn không vay margin
    assert target_weights([0.01], [0.5]) == [1.0]
    assert target_weights([0.20], [0.10]) == [pytest.approx(0.5)]
    assert target_weights([None], [0.10]) == [0.0]


# ============ 7. GARCH(1,1) thu hồi tham số ============


def test_garch_thu_hoi_alpha_cong_beta():
    arch = pytest.importorskip("arch", reason="arch vắng mặt -> bỏ qua test GARCH (ghi rõ trong báo cáo)")
    import random

    from scripts.measure_vol_target_etf import garch_persistence

    # Mô phỏng GARCH(1,1) với omega=0.00001, alpha=0.08, beta=0.85 (alpha+beta = 0.93)
    rng = random.Random(161)
    omega, alpha, beta = 0.00001, 0.08, 0.85
    n = 1500
    var = omega / (1 - alpha - beta)
    returns = []
    for _ in range(n):
        z = rng.gauss(0.0, 1.0)
        r = math.sqrt(var) * z
        returns.append(r)
        var = omega + alpha * r * r + beta * var

    got = garch_persistence(returns, model=arch, refit_every=21)
    assert got is not None, "phải ước lượng được"
    total = got["alpha"] + got["beta"]
    assert abs(total - (alpha + beta)) <= 0.05, f"alpha+beta thu hồi {total:.4f}, kỳ vọng ~{alpha + beta}"
    assert got["n_fits"] >= 1


def test_buy_hold_tru_phi_va_thue_hai_dau():
    bars = [_bar(1, 100.0, open_=100.0), _bar(2, 110.0)]
    res = buy_hold(bars, start_idx=0, end_idx=1)
    gross = 110.0 / 100.0
    # mô hình chi phí đã chốt: mua trả (FEE+trượt) trên vốn, bán trả (FEE+thuế+trượt)
    # trên giá trị bán thật
    expected = gross - (FEE_RATE + SLIP) - gross * (FEE_RATE + SELL_TAX_RATE + SLIP)
    assert res.equity_curve[-1] == pytest.approx(expected, abs=1e-12)
