"""Unit tests cho trading/garch_vol.py (bước 1, GARCH nghiên cứu).

Kiểm chứng:
1. Không nhìn trước: dự báo tính đến ngày t không đổi khi dữ liệu SAU t bị thay.
2. Ngày thiếu nến: return nối qua ngày giao dịch bị thiếu bị loại, không coi là 1 ngày.
3. Chưa đủ quan sát -> None (không đoán).
4. Khôi phục mức biến động: chuỗi return i.i.d. sigma 2% -> dự báo gần 2%.
"""

import math
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import numpy as np

import trading.garch_vol as gv
from trading.calendar_vn import TZ, is_trading_day
from trading.garch_vol import (
    daily_log_returns,
    forecast_sigma,
    is_plausible_fit,
    sigma_asof,
)
from trading.models import Bar

START = date(2022, 1, 3)  # Thứ Hai


def _bars_from_returns(returns, start=START, skip: set[date] | None = None) -> list[Bar]:
    """Dựng bar daily trên các ngày giao dịch liên tiếp; ngày trong `skip` không có nến."""
    bars: list[Bar] = []
    price = 20_000.0
    d = start
    i = 0
    skip = skip or set()
    while i < len(returns):
        if is_trading_day(d):
            price *= math.exp(returns[i])
            i += 1
            if d not in skip:
                ts = datetime(d.year, d.month, d.day, tzinfo=TZ)
                bars.append(Bar("HPG", ts, price, price, price, price, 1_000_000))
        d += timedelta(days=1)
    return bars


def _iid_returns(n: int, sigma: float = 0.02, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(rng.standard_t(8, n) * sigma / math.sqrt(8 / 6))


def test_forecast_recovers_volatility_level():
    s = forecast_sigma(_iid_returns(300), min_obs=200)
    assert s is not None
    assert 0.015 < s < 0.026


def test_too_few_observations_returns_none():
    assert forecast_sigma(_iid_returns(100), min_obs=500) is None


def _garch_returns(n: int, seed: int = 11) -> list[float]:
    """Chuỗi GARCH(1,1) mô phỏng (alpha 0.10, beta 0.85, sigma dài hạn ~2%)."""
    rng = np.random.default_rng(seed)
    omega = 0.02**2 * (1 - 0.10 - 0.85)
    var, out = 0.02**2, []
    for z in rng.standard_normal(n):
        r = math.sqrt(var) * z
        out.append(r)
        var = omega + 0.10 * r * r + 0.85 * var
    return out


def test_no_lookahead_sigma_asof_ignores_future():
    rets = _garch_returns(700)
    bars = _bars_from_returns(rets)
    asof = bars[599].ts.astimezone(TZ).date()
    base = sigma_asof(bars, asof, min_obs=500)

    # Thay hẳn 100 phiên SAU asof bằng biến động gấp 10 lần: kết quả phải y hệt.
    rets_future_changed = rets[:600] + [r * 10 for r in rets[600:]]
    base_changed = sigma_asof(_bars_from_returns(rets_future_changed), asof, min_obs=500)
    assert base is not None
    assert base == base_changed


def test_missing_trading_day_drops_the_spanning_return():
    rets = _iid_returns(10)
    full = _bars_from_returns(rets)
    missing_day = full[4].ts.astimezone(TZ).date()
    gapped = _bars_from_returns(rets, skip={missing_day})

    assert len(daily_log_returns(full)) == 9
    # Thiếu 1 nến -> mất 2 return (vào nến thiếu và ra khỏi nến thiếu gộp thành 1 return
    # nhiều ngày, bị loại): 8 bar liền nhau còn 9 - 2 = 7 return hợp lệ.
    assert len(daily_log_returns(gapped)) == 7


def test_holiday_is_not_a_gap():
    rets = _iid_returns(10)
    bars = _bars_from_returns(rets)
    holiday = bars[4].ts.astimezone(TZ).date()
    # Nếu ngày đó là ngày lễ thì thiếu nến là bình thường: return nối qua nó hợp lệ.
    out = daily_log_returns(
        [b for b in bars if b.ts.astimezone(TZ).date() != holiday],
        holidays={holiday},
    )
    assert len(out) == 8


def test_implausible_fit_is_rejected():
    assert is_plausible_fit(0.08, 0.90, 0.02)
    assert not is_plausible_fit(0.30, 0.80, 0.02)  # alpha + beta >= 1: explosive
    assert not is_plausible_fit(0.08, 0.90, 18.1455)  # sigma 1814% (lỗi đo thật)
    assert not is_plausible_fit(0.08, 0.90, 0.0)


def test_sigma_asof_includes_signal_bar_when_bars_are_stored_in_utc():
    # Bar daily lưu 00:00 giờ VN = 17:00 UTC của ngày TRƯỚC (ts.date() lệch 1 ngày so với
    # ngày VN). Backtest truyền asof = bar.ts.date() -> phiên tín hiệu PHẢI được tính.
    rets = _iid_returns(10)
    utc = [
        Bar(b.symbol, b.ts.astimezone(UTC), b.open, b.high, b.low, b.close, b.volume)
        for b in _bars_from_returns(rets)
    ]
    signal_bar = utc[-1]
    seen: list[int] = []
    with patch.object(gv, "forecast_sigma", side_effect=lambda r, m: seen.append(len(r))):
        sigma_asof(utc, signal_bar.ts.date(), min_obs=1)
    assert seen == [9]  # 10 bar -> 9 return, gồm cả phiên tín hiệu
