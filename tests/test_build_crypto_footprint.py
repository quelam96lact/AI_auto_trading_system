"""Tests cho scripts/build_crypto_footprint.py (Brief dot 183b - Ca 1, 2, 3, 15, 17)."""

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
    """Ca 1: Gop aggTrades v2, kiem tra is_buyer_maker, OHLC, moc :05:00.000 va chuoi fp."""
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

    # Kiem tra dinh dang chuoi fp trong nen 1
    # step voi open 60000 = 6.0
    # k = floor(price / 6.0)
    # 59980.0 -> k = 9996, buy = 0.5 * 59980 = 29990, sell = 0
    # 60000.0 -> k = 10000, buy = 1.0 * 60000 = 60000, sell = 0
    # 60010.0 -> k = 10001, buy = 1.0 * 60010 = 60010, sell = 0
    # 60020.0 -> k = 10003, buy = 0, sell = 2.0 * 60020 = 120040
    fp_str = bar1["fp"]
    assert "9996:29990:0" in fp_str
    assert "10000:60000:0" in fp_str
    assert "10001:60010:0" in fp_str
    assert "10003:0:120040" in fp_str

    # Nen trong (nen 3) phai co fp rong ""
    bar3 = bars[2]
    assert bar3["n_trades"] == 0
    assert bar3["fp"] == ""


def test_2_buoc_footprint():
    """Ca 2: Buoc footprint v2 round(open * 0.0001, 1) (~1 bp), toi thieu 0.1, va theo open."""
    # 1. Cong thuc chuan theo open (1 bp)
    assert compute_footprint_step(60000.0) == 6.0
    assert compute_footprint_step(7123.4) == 0.7
    assert compute_footprint_step(100.0) == 0.1

    # 2. Nen co open va close cho buoc khac nhau
    # open = 60000.0 -> buoc 6.0
    # close = 50000.0 -> buoc neu theo close se la 5.0
    # Ket qua phai tinh theo open (step = 6.0, close_k = floor(50000 / 6) = 8333)
    t0_ms = int(datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    rows = [
        ["agg_trade_id", "price", "quantity", "first_id", "last_id", "transact_time", "is_buyer_maker"],
        ["1", "60000.0", "1.0", "1", "1", str(t0_ms + 1000), "false"],
        ["2", "50000.0", "1.0", "2", "2", str(t0_ms + 2000), "true"],
    ]
    bars, _ = aggregate_aggtrades_to_5m_bars(rows, year=2023, month=1)
    b0 = bars[0]
    assert b0["step"] == "6.0"
    assert b0["close_k"] == 8333


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


def test_17_prevalence_khong_cham_su_kien(tmp_path, capsys):
    """Ca 17: --prevalence doc thu muc v2, in bang 4 nhom, KHONG goi bo phat hien E1/E2/E3 hay target."""
    import gzip

    # Tao file gia lap v2
    contract_dir = tmp_path
    f_path = contract_dir / "2023-01.csv.gz"
    with gzip.open(f_path, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,fp\n")
        # 6 ngay (moi ngay 1 nen)
        for d in range(1, 7):
            gf.write(
                f"2023-01-{d:02d}T00:00:00Z,60000.00,60010.00,59990.00,60005.00,"
                f"10.0000,5.0000,5.0000,10,6.0,10000,10000:600000:300000\n"
            )

    with (
        patch("scripts.screen_crypto_orderflow.detect_e1_events") as mock_e1,
        patch("scripts.screen_crypto_orderflow.detect_e2_events") as mock_e2,
        patch("scripts.screen_crypto_orderflow.detect_e3_events") as mock_e3,
        patch("scripts.screen_crypto_orderflow.calculate_event_targets") as mock_tgt,
    ):
        ret = main(["--prevalence", "--output-dir", str(contract_dir)])
        assert ret == 0

        # Assert tuyet doi khong cham su kien hay muc tieu
        mock_e1.assert_not_called()
        mock_e2.assert_not_called()
        mock_e3.assert_not_called()
        mock_tgt.assert_not_called()

    captured = capsys.readouterr().out
    assert "BÁO CÁO PHỔ BIẾN IMBALANCE" in captured
    assert "TỔNG CHÍNH" in captured
    assert "PHÁN QUYẾT: E3" in captured
