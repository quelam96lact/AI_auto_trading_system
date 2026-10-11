"""Tests cho scripts/build_crypto_footprint.py (Brief dot 183 - Ca 1, 2, 3)."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.build_crypto_footprint import (
    SEALED_MAX_MS,
    aggregate_aggtrades_to_5m_bars,
    check_month_sealed,
    compute_footprint_step,
    main,
)


def test_1_gop_aggtrades_va_imbalance():
    """Ca 1: Gop aggTrades, kiem tra is_buyer_maker, OHLC, moc :05:00.000 va imbalance USDT."""
    # Tao 1 tap tin aggTrades synthetic cho thang 2023-01
    # Header aggTrades: agg_trade_id, price, quantity, first_id, last_id, transact_time, is_buyer_maker
    # Nen 1: [00:00:00, 00:05:00) UTC -> ts 1672531200000 -> 1672531499999
    # Nen 2: [00:05:00, 00:10:00) UTC -> ts 1672531500000 -> 1672531799999

    t0_ms = int(datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    t_0459_ms = t0_ms + 4 * 60 * 1000 + 59 * 1000  # 00:04:59.000
    t_0500_ms = t0_ms + 5 * 60 * 1000  # 00:05:00.000 (thuoc nen 2!)

    rows = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        # Nen 1:
        # Trade 1: Open = 60000.0, Qty = 1.0 BTC, is_buyer_maker = false (Buy)
        ["1", "60000.0", "1.0", "1", "1", str(t0_ms + 1000), "false"],
        # Trade 2: High = 60020.0, Qty = 2.0 BTC, is_buyer_maker = true (Sell)
        ["2", "60020.0", "2.0", "2", "2", str(t0_ms + 2000), "true"],
        # Trade 3: Low = 59980.0, Qty = 0.5 BTC, is_buyer_maker = false (Buy)
        ["3", "59980.0", "0.5", "3", "3", str(t0_ms + 3000), "false"],
        # Trade 4: Close = 60010.0, Qty = 1.0 BTC, is_buyer_maker = false (Buy)
        ["4", "60010.0", "1.0", "4", "4", str(t_0459_ms), "false"],
        # Nen 2:
        # Trade 5 dung moc 00:05:00.000 phai thuoc ve nen 2
        ["5", "60050.0", "1.5", "5", "5", str(t_0500_ms), "true"],
    ]

    bars, total_trades = aggregate_aggtrades_to_5m_bars(rows, year=2023, month=1)

    assert total_trades == 5
    bar1 = bars[0]
    bar2 = bars[1]

    # Kiem tra nen 1
    assert bar1["ts"] == "2023-01-01T00:00:00Z"
    assert bar1["open"] == "60000.00"
    assert bar1["high"] == "60020.00"
    assert bar1["low"] == "59980.00"
    assert bar1["close"] == "60010.00"
    assert bar1["n_trades"] == 4

    # is_buyer_maker = false -> buy (1.0 + 0.5 + 1.0 = 2.5)
    # is_buyer_maker = true -> sell (2.0)
    assert float(bar1["buy"]) == pytest.approx(2.5, abs=1e-4)
    assert float(bar1["sell"]) == pytest.approx(2.0, abs=1e-4)
    assert float(bar1["delta"]) == pytest.approx(0.5, abs=1e-4)

    # Kiem tra nen 2 (moc 00:05:00.000 thuoc nen sau)
    assert bar2["ts"] == "2023-01-01T00:05:00Z"
    assert bar2["open"] == "60050.00"
    assert bar2["close"] == "60050.00"
    assert bar2["n_trades"] == 1
    assert float(bar2["sell"]) == pytest.approx(1.5, abs=1e-4)
    assert float(bar2["buy"]) == 0.0

    # Kiem tra Imbalance chéo theo USDT:
    # Gia su open = 60000.0 => step = 12.0
    # Muc k: k = floor(p / 12.0)
    # Muc k = floor(60000 / 12.0) = 5000.
    # Muc k-1 = 4999 (gia ~ 59988), k+1 = 5001 (gia ~ 60012)
    # Ta test 2 tinh huong rieng biet:
    # - Ca duoi san 50.000 USDT (khong dat imbalance)
    # - Ca mau so cham san 10.000 USDT
    t_imb_base = t0_ms + 10 * 60 * 1000  # Nen 3 (00:10:00)
    # Nen 3: Open = 60000.0 (step 12.0).
    # k = 5000 (price 60000.0), k-1 = 4999 (price 59988.0).
    # Sub-case A: buy_usdt tai k = 45000 (qty = 45000 / 60000 = 0.75 BTC, buy), sell_usdt tai k-1 = 0
    # Du ti le > 3 * 10000, nhung buy_usdt = 45000 < 50000 => KHONG CO ask imbalance.
    rows_sub_a = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        ["1", "60000.0", "0.75", "1", "1", str(t_imb_base + 1000), "false"],  # 45k USDT buy
    ]
    bars_sub_a, _ = aggregate_aggtrades_to_5m_bars(rows_sub_a, year=2023, month=1)
    bar_a = bars_sub_a[2]
    assert bar_a["ask_k_min"] == ""
    assert bar_a["ask_k_max"] == ""

    # Sub-case B: sell_usdt tai k-1 = 2000 USDT (duoi san 10.000 USDT nen denom_floor = 10.000)
    # Can buy_usdt >= 3 * 10000 = 30000 va >= 50000 => can buy_usdt >= 50000.
    # Ta cho buy_usdt = 60000 (1.0 BTC buy tai 60000.0). Sell tai k-1 = 2000 USDT (qty 0.03334 tai 59988.0).
    # => Co ask imbalance tai k = 5000!
    rows_sub_b = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        ["1", "60000.0", "1.0", "1", "1", str(t_imb_base + 1000), "false"],  # 60k buy tai k=5000
        ["2", "59988.0", "0.03334", "2", "2", str(t_imb_base + 2000), "true"],  # ~2k sell tai k-1=4999
    ]
    bars_sub_b, _ = aggregate_aggtrades_to_5m_bars(rows_sub_b, year=2023, month=1)
    bar_b = bars_sub_b[2]
    assert bar_b["ask_k_min"] == 5000
    assert bar_b["ask_k_max"] == 5000


def test_2_buoc_footprint():
    """Ca 2: Buoc footprint round(open * 0.0002, 1), toi thieu 0.1, va theo open chu khong theo close."""
    # 1. Cong thuc chuan theo open
    assert compute_footprint_step(60000.0) == 12.0
    assert compute_footprint_step(7123.4) == 1.4
    assert compute_footprint_step(100.0) == 0.1

    # 2. Nen co open va close cho buoc khac nhau
    # open = 60000.0 -> buoc 12.0
    # close = 50000.0 -> buoc neu theo close se la 10.0
    # Ket qua phai tinh theo open (step = 12.0, close_k = floor(50000 / 12) = 4166)
    t0_ms = int(datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    rows = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        ["1", "60000.0", "1.0", "1", "1", str(t0_ms + 1000), "false"],
        ["2", "50000.0", "1.0", "2", "2", str(t0_ms + 2000), "true"],
    ]
    bars, _ = aggregate_aggtrades_to_5m_bars(rows, year=2023, month=1)
    b0 = bars[0]
    assert b0["step"] == "12.0"
    assert b0["close_k"] == 4166  # 50000 // 12 = 4166 (neu tinh theo close step 10 thi close_k = 5000)


def test_3_kiem_tra_niem_phong():
    """Ca 3: Niem phong thang >= 2026-09 tu choi truoc khi tai; dong > moc niem phong nem loi."""
    # 1. Tu choi thang >= 2026-09 truoc khi tai
    with pytest.raises(ValueError, match="vuot moc niem phong"):
        check_month_sealed("2026-09")

    # Kiem tra main tu choi --to 2026-09 va khong goi ham tai
    with patch("scripts.build_crypto_footprint.process_month") as mock_proc:
        ret = main(["--from", "2026-08", "--to", "2026-09"])
        assert ret == 2
        mock_proc.assert_not_called()

    # 2. File chua mot dong transact_time = 2026-09-01 00:00:00.000 UTC => nem loi
    t_beyond_ms = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    assert t_beyond_ms > SEALED_MAX_MS

    rows = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        ["1", "60000.0", "1.0", "1", "1", str(t_beyond_ms), "false"],
    ]

    with pytest.raises(ValueError, match="vuot qua moc niem phong"):
        aggregate_aggtrades_to_5m_bars(rows, year=2026, month=8)
