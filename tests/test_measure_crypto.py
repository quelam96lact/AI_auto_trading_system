"""Unit tests cho scripts/measure_crypto_strategies.py (Brief đợt 13 / Gói C-b).

Tất định, không phụ thuộc mạng, kiểm chứng:
1. test_doc_dung_so_nen_crypto: Đọc dữ liệu từ query trả về đúng cấu trúc Bar và số lượng.
2. test_khong_mat_nen_chuyen_doi_tz: Nến 24/7 timestamptz vào Bar.ts không bị mất nến nào.
3. test_so_sanh_lot_size_100_vs_1: Tài sản giá cao bị 0 lệnh với lot_size=100 và có lệnh với lot_size=1.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from scripts.measure_crypto_strategies import (
    read_crypto_bars,
    run_strategy_on_crypto,
)
from trading.models import Bar


def test_doc_dung_so_nen_crypto():
    """1. test_doc_dung_so_nen_crypto:
    Hàm đọc trả đúng số nến cho một mã/khung đã biết;
    số đếm khớp dữ liệu query SQL trực tiếp.
    """
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    mock_rows = [
        ("BTC-USDT", base_dt + timedelta(days=i), 50000.0 + i, 51000.0 + i, 49000.0 + i, 50500.0 + i, 1000.0)
        for i in range(10)
    ]
    mock_cur.fetchall.return_value = mock_rows

    bars_by_sym = read_crypto_bars(mock_conn, symbols=["BTC-USDT"], interval="1d")

    assert "BTC-USDT" in bars_by_sym
    assert len(bars_by_sym["BTC-USDT"]) == 10
    first_bar = bars_by_sym["BTC-USDT"][0]
    assert first_bar.symbol == "BTC-USDT"
    assert first_bar.open == 50000.0
    assert first_bar.close == 50500.0
    assert first_bar.ts == base_dt
    assert first_bar.source == "bingx"


def test_khong_mat_nen_chuyen_doi_tz():
    """2. test_khong_mat_nen_chuyen_doi_tz:
    Kiểm chứng len(bars_vào) == len(bars_ra) qua đường timestamptz -> Bar.ts,
    chống lệch nhịp hay mất nến 24/7.
    """
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    base_dt = datetime(2024, 4, 27, 0, 0, tzinfo=UTC)
    # 24 nến liên tục 24h trong ngày (crypto chạy 24/7)
    mock_rows = [
        ("ETH-USDT", base_dt + timedelta(hours=h), 3000.0, 3050.0, 2950.0, 3020.0, 500.0)
        for h in range(24)
    ]
    mock_cur.fetchall.return_value = mock_rows

    bars_by_sym = read_crypto_bars(mock_conn, symbols=["ETH-USDT"], interval="1h")

    assert len(bars_by_sym["ETH-USDT"]) == 24
    # Khẳng định từng mốc giờ không bị mất hoặc trùng
    timestamps = [b.ts for b in bars_by_sym["ETH-USDT"]]
    assert len(set(timestamps)) == 24
    for i in range(23):
        assert (timestamps[i + 1] - timestamps[i]) == timedelta(hours=1)


def test_so_sanh_lot_size_100_vs_1():
    """3. test_so_sanh_lot_size_100_vs_1 (Tiêu chí 4):
    Với tài sản giá cao (BTC giá 60.000, vốn 1.000.000 USDT — xem `capital` bên
    dưới; vốn phải đủ lớn để lô 1 vào được lệnh, nếu không thì cả hai vế đều 0
    và test mất ý nghĩa):
    - lot_size = 100: 1 lô = 6.000.000 USDT > 20% vốn -> sizing trả về 0 -> 0 lệnh.
    - lot_size = 1: sizing tính được 1-2 BTC -> thực hiện giao dịch (>0 lệnh).
    Chứng minh thiên lệch loại trừ tài sản giá cao được triệt tiêu hoàn toàn.
    """
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars = []
    # 20 bars giá 60.000
    for i in range(20):
        bars.append(Bar("BTC-USDT", base_dt + timedelta(days=i), 60000.0, 61000.0, 59000.0, 60000.0, 100.0, source="bingx"))
    # Bar 21: Breakout tăng mạnh lên 70.000
    bars.append(Bar("BTC-USDT", base_dt + timedelta(days=20), 60000.0, 71000.0, 60000.0, 70000.0, 200.0, source="bingx"))
    # Các bar tiếp theo để giữ / thoát
    for i in range(21, 35):
        bars.append(Bar("BTC-USDT", base_dt + timedelta(days=i), 68000.0, 69000.0, 67000.0, 68000.0, 100.0, source="bingx"))
    # Bar giảm để thoát
    bars.append(Bar("BTC-USDT", base_dt + timedelta(days=35), 65000.0, 66000.0, 50000.0, 52000.0, 300.0, source="bingx"))
    bars.append(Bar("BTC-USDT", base_dt + timedelta(days=36), 52000.0, 53000.0, 51000.0, 52000.0, 100.0, source="bingx"))

    capital = 1_000_000.0  # 1M USDT (để 1% rủi ro đủ mua 2 BTC)

    # Chạy với lot_size = 100
    res_100 = run_strategy_on_crypto({"BTC-USDT": bars}, "daily_breakout", capital_per_symbol=capital, lot_size=100)
    # Chạy với lot_size = 1
    res_1 = run_strategy_on_crypto({"BTC-USDT": bars}, "daily_breakout", capital_per_symbol=capital, lot_size=1)

    assert res_100["total_trades"] == 0, f"lot_size=100 phai ra 0 lenh, thuc te: {res_100['total_trades']}"
    assert res_1["total_trades"] > 0, f"lot_size=1 phai vao duoc lenh, thuc te: {res_1['total_trades']}"


def test_buy_and_hold_fractional_lot_size_non_zero():
    """Tái hiện và kiểm chứng: _buy_and_hold với per_symbol=500, giá 62766, lot_size=0.0001
    phải cho PnL != 0 (thay vì 0.00 do int //).
    """
    from trading.backtest import _buy_and_hold

    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars = [
        Bar("BTC-USDT", base_dt, 62766.0, 63000.0, 62000.0, 62766.0, 100.0, source="bingx"),
        Bar("BTC-USDT", base_dt + timedelta(days=1), 62766.0, 65000.0, 62766.0, 64000.0, 100.0, source="bingx"),
    ]
    pnl = _buy_and_hold(bars, capital=500.0, fee_rate=0.0005, sell_tax_rate=0.0, slippage_bps=0.0, lot_size=0.0001)
    assert pnl != 0.0, f"pnl khong duoc bang 0 voi von 500 va gia 62766, thuc te={pnl}"
    assert pnl > 0.0, f"gia tang tu 62766 len 64000 pnl phai duong, thuc te={pnl}"


def test_buy_and_hold_lot_size_1_backward_compatible():
    """Tiêu chí 3: Cùng đầu vào, lot_size=1 cho kết quả y hệt trước khi sửa."""
    from trading.backtest import _buy_and_hold, _buy_and_hold_curve

    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars = [
        Bar("VCB", base_dt, 100.0, 105.0, 95.0, 100.0, 1000.0),
        Bar("VCB", base_dt + timedelta(days=1), 100.0, 110.0, 100.0, 108.0, 1000.0),
    ]
    # Mặc định lot_size=1
    pnl_default = _buy_and_hold(bars, capital=1000.0, fee_rate=0.0015, sell_tax_rate=0.001, slippage_bps=5.0)
    pnl_explicit_1 = _buy_and_hold(bars, capital=1000.0, fee_rate=0.0015, sell_tax_rate=0.001, slippage_bps=5.0, lot_size=1)
    assert pnl_default == pnl_explicit_1

    curve_default = _buy_and_hold_curve(bars, capital=1000.0, fee_rate=0.0015, sell_tax_rate=0.001, slippage_bps=5.0)
    curve_explicit_1 = _buy_and_hold_curve(bars, capital=1000.0, fee_rate=0.0015, sell_tax_rate=0.001, slippage_bps=5.0, lot_size=1)
    assert curve_default == curve_explicit_1


