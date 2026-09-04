"""Unit tests cho scripts/liquidity_sensitivity.py (Gói M).

Kiểm chứng:
1. test_inject_threshold_changes_trades: Tiêm các ngưỡng khác nhau sinh ra số lệnh khác nhau.
2. test_monotonicity_qualifying_symbols: Tính đơn điệu: ngưỡng tăng -> số mã đủ điều kiện không tăng.
"""

from datetime import UTC, datetime, timedelta

from scripts.liquidity_sensitivity import (
    compute_sensitivity_table,
    run_threshold_backtest,
)
from trading.models import Bar


def _make_sample_crypto_bars(symbol: str, base_val: float, daily_volume: float) -> list[Bar]:
    """Tạo chuỗi nến test có xu hướng tăng để kích hoạt pullback."""
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars = []
    # 25 nến đầu tích lũy quanh base_val
    for i in range(25):
        p = base_val * (1 + 0.005 * i)
        bars.append(Bar(symbol, base_dt + timedelta(days=i), p * 0.99, p * 1.02, p * 0.98, p, daily_volume, source="bingx"))
    # Nến 25-30: Breakout mạnh rồi pullback
    for i in range(25, 35):
        p = base_val * 1.25 * (1 + 0.01 * (i - 25)) if i < 30 else base_val * 1.25 * (1 - 0.02 * (i - 30))
        bars.append(Bar(symbol, base_dt + timedelta(days=i), p * 0.98, p * 1.03, p * 0.97, p, daily_volume, source="bingx"))
    # Nến 35-50: Tăng tiếp để thoát
    for i in range(35, 50):
        p = base_val * 1.35 * (1 + 0.008 * (i - 35))
        bars.append(Bar(symbol, base_dt + timedelta(days=i), p * 0.99, p * 1.02, p * 0.98, p, daily_volume, source="bingx"))
    return bars


def test_inject_threshold_changes_trades():
    """1. test_inject_threshold_changes_trades:
    Với 1 mã có giá trị giao dịch trung bình ~1.000.000 USDT (close 100 * volume 10.000):
    - Ngưỡng 100.000 (thấp) -> đủ thanh khoản -> có thể vào lệnh.
    - Ngưỡng 10.000.000 (cao) -> bị chặn thanh khoản -> 0 lệnh.
    """
    bars = _make_sample_crypto_bars("TEST-USDT", base_val=100.0, daily_volume=10_000.0)
    # Giá trị giao dịch trung bình ~ 100 * 10.000 = 1.000.000 USDT

    res_low = run_threshold_backtest({"TEST-USDT": bars}, threshold=100_000.0, capital_per_symbol=100_000.0, lot_size=1)
    res_high = run_threshold_backtest({"TEST-USDT": bars}, threshold=10_000_000.0, capital_per_symbol=100_000.0, lot_size=1)

    assert res_low["qualifying_symbols"] == 1
    assert res_high["qualifying_symbols"] == 0
    assert res_high["total_trades"] == 0


def test_monotonicity_qualifying_symbols():
    """2. test_monotonicity_qualifying_symbols:
    Khi ngưỡng tăng dần: số mã đủ điều kiện thanh khoản (qualifying_symbols)
    phải đơn điệu giảm hoặc bằng (không bao giờ tăng).
    """
    # Tạo 3 mã với 3 mức thanh khoản khác nhau: 50k, 500k, 5M USDT
    bars1 = _make_sample_crypto_bars("SYM1", base_val=10.0, daily_volume=5_000.0)      # ~50k
    bars2 = _make_sample_crypto_bars("SYM2", base_val=50.0, daily_volume=10_000.0)    # ~500k
    bars3 = _make_sample_crypto_bars("SYM3", base_val=500.0, daily_volume=10_000.0)   # ~5M

    bars_by_symbol = {"SYM1": bars1, "SYM2": bars2, "SYM3": bars3}
    thresholds = [0.0, 1e4, 1e5, 1e6, 1e7, 1e8]

    table = compute_sensitivity_table(bars_by_symbol, thresholds=thresholds, capital_per_symbol=100_000.0, lot_size=1)

    prev_qual = 999
    for row in table:
        assert row["qualifying_symbols"] <= prev_qual, (
            f"Vi phạm tính đơn điệu: ngưỡng {row['threshold']} có {row['qualifying_symbols']} mã "
            f"> mức trước đó ({prev_qual} mã)"
        )
        prev_qual = row["qualifying_symbols"]
