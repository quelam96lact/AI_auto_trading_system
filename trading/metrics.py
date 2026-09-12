"""Module chuẩn hóa các số đo hiệu năng (metrics) cho hệ thống backtest (Brief đợt 9).

MỘT CÔNG THỨC MỘT CHỖ:
Tất cả các script đo lường, backtest và báo cáo trong repo PHẢI sử dụng các hàm
thuần túy trong module này để tính toán số đo, cấm tự sao chép công thức.
"""

import math
import statistics
from collections.abc import Sequence
from datetime import date


def profit_factor(pnls: Sequence[float]) -> float | None:
    """Tính Profit Factor = Tổng lãi các lệnh thắng / |Tổng lỗ các lệnh thua|.

    Args:
        pnls: Danh sách PnL của các lệnh giao dịch đã đóng.

    Returns:
        float: Giá trị Profit Factor.
        None: Nếu không có lệnh nào, hoặc không có lệnh thua (tránh trả inf).
    """
    if not pnls:
        return None

    gains = sum(p for p in pnls if p > 0)
    losses = sum(p for p in pnls if p < 0)

    if losses == 0:
        return None

    return gains / abs(losses)


def expectancy(pnls: Sequence[float]) -> float:
    """Tính Kỳ vọng toán học (Expectancy) = PnL trung bình mỗi lệnh.

    Args:
        pnls: Danh sách PnL của các lệnh giao dịch.

    Returns:
        float: PnL trung bình (0.0 nếu rỗng).
    """
    if not pnls:
        return 0.0
    return sum(pnls) / len(pnls)


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Tính Sụt giảm vốn sâu nhất (Max Drawdown) theo tỷ lệ phần trăm (0.0 - 1.0).

    Khớp chuẩn định nghĩa trong trading/backtest.py:242-247.

    Args:
        equity_curve: Chuỗi giá trị vốn (equity) qua thời gian.

    Returns:
        float: Tỷ lệ sụt giảm sâu nhất từ đỉnh (0.0 nếu rỗng hoặc vốn không đổi).
    """
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    return max_dd


def sharpe(daily_returns: Sequence[float], periods_per_year: float) -> float | None:
    """Tính Tỷ số Sharpe chuẩn hóa theo năm (Annualized Sharpe Ratio).

    LƯU Ý BẮT BUỘC:
    `periods_per_year` là tham số BẮT BUỘC, KHÔNG CÓ GIÁ TRỊ MẶC ĐỊNH để tránh bẫy
    đơn vị giữa các thị trường (VN stock = 252, Crypto 1D = 365, Crypto 1H = 365*24 = 8760).

    Args:
        daily_returns: Chuỗi tỷ suất sinh lời theo từng kỳ (ví dụ: ngày hoặc giờ).
        periods_per_year: Số kỳ giao dịch trong một năm (VN: 252, Crypto 1D: 365, Crypto 1H: 8760).

    Returns:
        float: Tỷ số Sharpe chuẩn hóa.
        None: Nếu chuỗi có ít hơn 2 quan sát hoặc độ lệch chuẩn = 0.
    """
    if len(daily_returns) < 2:
        return None

    mean_ret = statistics.mean(daily_returns)
    std_ret = statistics.stdev(daily_returns)

    if std_ret == 0:
        return None

    return (mean_ret / std_ret) * math.sqrt(periods_per_year)


def portfolio_equity_curve(
    per_symbol_pnl_by_date: dict[str, dict[date, float]],
    capital_per_symbol: float,
) -> list[float]:
    """Gộp PnL theo ngày của từng mã thành một đường cong vốn danh mục (Portfolio Equity Curve).

    CẢNH BÁO BẮT BUỘC VỀ GIẢ ĐỊNH & HẠN CHẾ CỦA MÔ HÌNH:
    Hàm này gộp PnL của N mã được chạy độc lập, mỗi mã có một lượng vốn cố định
    `capital_per_symbol` (ví dụ 1.308 tài khoản song song, mỗi tài khoản 1 tỷ VND).
    Mô hình này KHÔNG mô phỏng ràng buộc vốn chung (shared capital pool) và
    KHÔNG mô phỏng sự tranh chấp tiền mặt giữa các mã khi có nhiều tín hiệu đồng thời.
    Tổng vốn ban đầu của danh mục được tính bằng N * capital_per_symbol.

    Args:
        per_symbol_pnl_by_date: Dict ánh xạ symbol -> dict[date, daily_pnl_delta].
        capital_per_symbol: Vốn ban đầu cấp cho mỗi mã.

    Returns:
        list[float]: Danh sách giá trị vốn tổng của danh mục qua các ngày có giao dịch.
    """
    if not per_symbol_pnl_by_date:
        return []

    n_symbols = len(per_symbol_pnl_by_date)
    total_initial_capital = n_symbols * capital_per_symbol

    # Thu thập tất cả các ngày duy nhất có biến động PnL và sắp xếp tăng dần
    all_dates = sorted(
        {d for pnl_dict in per_symbol_pnl_by_date.values() for d in pnl_dict}
    )

    if not all_dates:
        return [total_initial_capital]

    curve = []
    current_equity = total_initial_capital

    for d in all_dates:
        day_total_pnl = sum(
            pnl_dict.get(d, 0.0) for pnl_dict in per_symbol_pnl_by_date.values()
        )
        current_equity += day_total_pnl
        curve.append(current_equity)

    return curve


def calculate_percentile(values: list[float], p: float) -> float:
    """Tính phân vị thứ p (0 đến 100) theo phương pháp nội suy tuyến tính."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    rank = (p / 100.0) * (n - 1)
    k = int(rank)
    d = rank - k
    if k >= n - 1:
        return sorted_v[-1]
    return sorted_v[k] + d * (sorted_v[k + 1] - sorted_v[k])


def empirical_percentile_rank(values: list[float], target: float) -> float:
    """Tính phân vị thực nghiệm của target trong null distribution (0 đến 100)."""
    if not values:
        return 0.0
    less = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if math.isclose(v, target, abs_tol=1e-9))
    return (less + 0.5 * equal) / len(values) * 100.0
