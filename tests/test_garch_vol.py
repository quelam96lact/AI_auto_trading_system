"""Unit tests cho trading/garch_vol.py (bước 1, GARCH nghiên cứu).

Kiểm chứng:
1. Không nhìn trước: dự báo tính đến ngày t không đổi khi dữ liệu SAU t bị thay.
2. Ngày thiếu nến: return nối qua ngày giao dịch bị thiếu bị loại, không coi là 1 ngày.
3. Chưa đủ quan sát -> None (không đoán).
4. Khôi phục mức biến động: chuỗi return i.i.d. sigma 2% -> dự báo gần 2%.
"""

import math
from datetime import date, datetime, timedelta

import numpy as np

from trading.calendar_vn import TZ, is_trading_day
from trading.garch_vol import daily_log_returns, forecast_sigma, sigma_asof
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
    s = forecast_sigma(_iid_returns(800), min_obs=500)
    assert s is not None
    assert 0.015 < s < 0.026


def test_too_few_observations_returns_none():
    assert forecast_sigma(_iid_returns(100), min_obs=500) is None


def test_no_lookahead_sigma_asof_ignores_future():
    rets = _iid_returns(700)
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
