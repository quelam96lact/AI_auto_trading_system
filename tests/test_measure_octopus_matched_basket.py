"""Unit tests cho scripts/measure_octopus_matched_basket.py (Gói Q).

Kiểm chứng:
1. test_analyze_basket_partitioning: Phân rổ đúng và tính mốc Buy & Hold khớp với đúng tập mã được chọn.
2. test_basket_diff_logic: Khẳng định chênh lệch = tot_strat - tot_bh trên đúng tập mã con.
"""

from scripts.measure_octopus_matched_basket import analyze_basket


def test_analyze_basket_partitioning():
    """1. test_analyze_basket_partitioning (Tiêu chí 1 & 3):
    Khẳng định analyze_basket tính đúng tổng PnL chiến lược, tổng PnL BH
    và tỷ lệ thắng BH trên đúng tập mã được truyền vào.
    """
    mock_results = [
        # Mã 1: có lệnh, lãi 50tr, BH lãi 100tr -> diff = -50tr (thua BH)
        {"symbol": "AAA", "trades": 3, "strat_pnl": 50_000_000.0, "bh_pnl": 100_000_000.0, "diff": -50_000_000.0, "liquid": True},
        # Mã 2: có lệnh, lãi 80tr, BH lỗ 20tr -> diff = +100tr (thắng BH)
        {"symbol": "BBB", "trades": 2, "strat_pnl": 80_000_000.0, "bh_pnl": -20_000_000.0, "diff": 100_000_000.0, "liquid": True},
        # Mã 3: 0 lệnh, lãi 0, BH lãi 200tr -> diff = -200tr (không sinh lệnh)
        {"symbol": "CCC", "trades": 0, "strat_pnl": 0.0, "bh_pnl": 200_000_000.0, "diff": -200_000_000.0, "liquid": False},
    ]

    # Rổ toàn bộ (3 mã)
    stats_all = analyze_basket(mock_results, "Toàn bộ")
    assert stats_all["n_symbols"] == 3
    assert stats_all["total_trades"] == 5
    assert stats_all["strat_pnl"] == 130_000_000.0
    assert stats_all["bh_pnl"] == 280_000_000.0
    assert stats_all["diff"] == -150_000_000.0

    # Rổ chỉ mã sinh lệnh (2 mã: AAA, BBB)
    traded_results = [r for r in mock_results if r["trades"] > 0]
    stats_traded = analyze_basket(traded_results, "Sinh lệnh")
    assert stats_traded["n_symbols"] == 2
    assert stats_traded["total_trades"] == 5
    assert stats_traded["strat_pnl"] == 130_000_000.0
    # Mốc BH chỉ tính trên AAA (100tr) + BBB (-20tr) = 80tr (KHÔNG cộng 200tr của CCC)
    assert stats_traded["bh_pnl"] == 80_000_000.0
    assert stats_traded["diff"] == +50_000_000.0
    assert stats_traded["win_bh_count"] == 1
    assert stats_traded["win_bh_pct"] == 50.0
