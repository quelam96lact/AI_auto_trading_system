"""Dự báo biến động 1 ngày bằng GARCH(1,1) Student-t (nghiên cứu, bước 1).

Chỉ dùng để NGHIÊN CỨU/ĐO (scripts/measure_garch_vs_atr_qty.py) — chưa nối vào
engine hay RiskManager. `arch` nằm trong extra `dev`, KHÔNG có trong image
production (`uv sync --no-dev`), nên import `arch` để lười trong hàm: module này
import được cả khi thiếu `arch`, chỉ lỗi rõ ràng khi thật sự gọi dự báo.

Không nhìn trước tương lai: dự báo "tính đến ngày t" chỉ dùng return có ngày <= t
(cùng quy ước với ATR(14) tại bar t: quyết định sau khi đóng cửa phiên t).

Ngày thiếu nến: return nối hai bar liền kề mà giữa chúng thiếu một ngày giao dịch
(ví dụ 31/08-02/09/2026 không có nến) là return NHIỀU NGÀY — bị LOẠI, không coi là
return 1 ngày (sẽ làm phương sai phình sai).
"""

import math
from collections.abc import Sequence
from datetime import date
from itertools import pairwise

from trading.calendar_vn import TZ, trading_days_between_dates
from trading.models import Bar

DEFAULT_MIN_OBS = 500


def daily_log_returns(
    bars: Sequence[Bar], holidays: set[date] | frozenset = frozenset()
) -> list[tuple[date, float]]:
    """Log return 1 ngày giao dịch giữa các bar daily liền kề, kèm ngày của bar sau.

    Bỏ qua bar có giá <= 0 và return nối qua ngày giao dịch bị thiếu nến."""
    clean = sorted((b for b in bars if b.close > 0), key=lambda b: b.ts)
    out: list[tuple[date, float]] = []
    for prev, cur in pairwise(clean):
        d0, d1 = prev.ts.astimezone(TZ).date(), cur.ts.astimezone(TZ).date()
        if trading_days_between_dates(d0, d1, holidays) != 1:
            continue
        out.append((d1, math.log(cur.close / prev.close)))
    return out


def forecast_sigma(
    returns: Sequence[float], min_obs: int = DEFAULT_MIN_OBS
) -> float | None:
    """Độ lệch chuẩn dự báo cho ngày kế tiếp (đơn vị: log return, ví dụ 0.02 = 2%).

    None nếu chưa đủ `min_obs` quan sát hoặc mô hình không hội tụ — không đoán."""
    if len(returns) < min_obs:
        return None
    try:
        import numpy as np
        from arch import arch_model
    except ImportError as e:  # pragma: no cover - chỉ khi thiếu extra dev
        raise RuntimeError(
            "Thiếu thư viện `arch` — chạy `uv sync --extra dev`"
        ) from e

    # Nhân 100 cho ổn định số học của bộ tối ưu (khuyến nghị của arch), chia lại sau.
    model = arch_model(
        np.asarray(returns, dtype=float) * 100.0,
        mean="Constant",
        vol="GARCH",
        p=1,
        q=1,
        dist="t",
        rescale=False,
    )
    res = model.fit(disp="off")
    if res.convergence_flag != 0:
        return None
    variance = float(res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0])
    if not math.isfinite(variance) or variance <= 0:
        return None
    return math.sqrt(variance) / 100.0


def sigma_asof(
    bars: Sequence[Bar],
    asof: date,
    holidays: set[date] | frozenset = frozenset(),
    min_obs: int = DEFAULT_MIN_OBS,
) -> float | None:
    """Dự báo sigma ngày kế tiếp, chỉ dùng bar có ngày <= `asof` (không nhìn trước)."""
    usable = [b for b in bars if b.ts.astimezone(TZ).date() <= asof]
    returns = [r for _, r in daily_log_returns(usable, holidays)]
    return forecast_sigma(returns, min_obs)
