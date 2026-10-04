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
import warnings
from collections.abc import Sequence
from datetime import date
from itertools import pairwise

from trading.calendar_vn import TZ, trading_days_between_dates
from trading.models import Bar

DEFAULT_MIN_OBS = 500
# Sigma 1 ngày trên 15% là không thể tin (biên độ giá HOSE ±7%): chỉ có thể là mô hình
# khớp suy biến (đo thật ra 1814% ở IJC 12/10/2025), nên coi như không có dự báo.
MAX_PLAUSIBLE_SIGMA = 0.15


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
        from arch.utility.exceptions import ConvergenceWarning
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
    with warnings.catch_warnings():
        # Không hội tụ đã được xử lý bằng convergence_flag bên dưới (trả None); cảnh báo
        # của arch chỉ làm ồn đầu ra script.
        warnings.simplefilter("ignore", ConvergenceWarning)
        res = model.fit(disp="off")
    if res.convergence_flag != 0:
        return None
    alpha, beta = float(res.params["alpha[1]"]), float(res.params["beta[1]"])
    variance = float(res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0])
    if not math.isfinite(variance) or variance <= 0:
        return None
    sigma = math.sqrt(variance) / 100.0
    return sigma if is_plausible_fit(alpha, beta, sigma) else None


def is_plausible_fit(alpha: float, beta: float, sigma: float) -> bool:
    """Mô hình khớp dùng được: dừng (alpha + beta < 1) và sigma dự báo hợp lý.

    Hội tụ về mặt số học (convergence_flag == 0) chưa đủ — vẫn có nghiệm explosive."""
    return alpha + beta < 1.0 and 0.0 < sigma <= MAX_PLAUSIBLE_SIGMA


def sigma_asof(
    bars: Sequence[Bar],
    asof: date,
    holidays: set[date] | frozenset = frozenset(),
    min_obs: int = DEFAULT_MIN_OBS,
) -> float | None:
    """Dự báo sigma ngày kế tiếp, chỉ dùng bar có ngày <= `asof` (không nhìn trước).

    `asof` phải là ngày theo ĐÚNG quy ước của backtest/engine (`bar.ts.date()` — ngày
    theo múi giờ của chính bar, không đổi sang giờ VN), nếu không phiên tín hiệu bị
    lọc mất khi bar lưu giờ UTC (đo thật: ngày tín hiệu hiển thị lệch 1 ngày)."""
    usable = [b for b in bars if b.ts.date() <= asof]
    returns = [r for _, r in daily_log_returns(usable, holidays)]
    return forecast_sigma(returns, min_obs)
