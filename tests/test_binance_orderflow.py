"""Test cho scripts/binance_orderflow.py (Brief đợt 40).

Kiểm tra:
- Phép gộp theo luồng trên dữ liệu dựng tay
- Quy ước is_buyer_maker (false -> taker buy, true -> taker sell)
- Ranh giới giờ (:00.000 thuộc giờ mới)
- Tính toán delta và buy_ratio
"""

from datetime import UTC, datetime

from scripts.binance_orderflow import aggregate_aggtrades_stream


def test_aggregate_aggtrades_stream_manual():
    # Giờ 1: 2026-01-01 00:00:00 UTC đến 00:59:59 UTC
    # Giờ 2: 2026-01-01 01:00:00 UTC
    # Header: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
    t0_ms = int(datetime(2026, 1, 1, 0, 15, 0, tzinfo=UTC).timestamp() * 1000)
    t1_ms = int(datetime(2026, 1, 1, 0, 45, 0, tzinfo=UTC).timestamp() * 1000)
    t2_ms = int(datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC).timestamp() * 1000)  # Đúng mốc 01:00:00.000

    sample_rows = [
        # trade 1: hour 0, buy 2.5 (is_buyer_maker=false)
        ["1", "50000.0", "2.5", "10", "10", str(t0_ms), "false"],
        # trade 2: hour 0, sell 1.0 (is_buyer_maker=true)
        ["2", "50010.0", "1.0", "11", "11", str(t1_ms), "true"],
        # trade 3: hour 1, buy 3.0 (is_buyer_maker=false) tại đúng :00.000
        ["3", "50020.0", "3.0", "12", "12", str(t2_ms), "false"],
    ]

    records, trade_count = aggregate_aggtrades_stream(sample_rows, "BTCUSDT")

    assert trade_count == 3
    assert len(records) == 2

    # Hour 0
    h0 = records[0]
    assert h0["ts"] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert h0["taker_buy_volume"] == 2.5
    assert h0["taker_sell_volume"] == 1.0
    assert h0["delta"] == 1.5
    assert abs(h0["buy_ratio"] - (2.5 / 3.5)) < 1e-6
    assert h0["trade_count"] == 2

    # Hour 1 (chứa trade đúng mốc :00.000)
    h1 = records[1]
    assert h1["ts"] == datetime(2026, 1, 1, 1, 0, tzinfo=UTC)
    assert h1["taker_buy_volume"] == 3.0
    assert h1["taker_sell_volume"] == 0.0
    assert h1["delta"] == 3.0
    assert h1["buy_ratio"] == 1.0
    assert h1["trade_count"] == 1


def test_boundary_exact_seconds_belong_to_new_hour():
    # Kiểm tra giao dịch đúng tại mốc :00.000 đầu giờ
    # 2026-01-01 02:00:00.000
    ts_ms = int(datetime(2026, 1, 1, 2, 0, 0, tzinfo=UTC).timestamp() * 1000)
    row = [["100", "50000", "1.0", "1", "1", str(ts_ms), "false"]]

    records, count = aggregate_aggtrades_stream(row, "BTCUSDT")
    assert count == 1
    assert len(records) == 1
    assert records[0]["ts"] == datetime(2026, 1, 1, 2, 0, 0, tzinfo=UTC)
