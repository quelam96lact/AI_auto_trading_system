"""Unit tests cho phần tính toán đo khối lượng hợp đồng phái sinh (Brief 82 Task 2).

Kiểm thử thuần (không I/O, không gọi SSI API) với dữ liệu dựng tay và kết quả tính tay.
"""

from datetime import date

from scripts.measure_derivative_contract_volume import (
    ContractInfo,
    ContractVolumeStats,
    compute_volume_stats,
    filter_living_contracts,
    find_winning_contract,
    identify_front_month,
)


def test_compute_volume_stats_ranking_and_totals():
    """Kiểm thử xếp hạng giảm dần, tính tổng khối lượng và tỷ trọng %."""
    # Dữ liệu tính tay:
    # SYM_C: 1 phiên, volume = 1000
    # SYM_A: 3 phiên [100, 200, 300], volume = 600
    # SYM_B: 2 phiên [50, 50], volume = 100
    # Tổng thị trường: 1000 + 600 + 100 = 1700
    # Tỷ trọng %:
    # SYM_C: 1000 / 1700 = 58.82%
    # SYM_A: 600 / 1700 = 35.29%
    # SYM_B: 100 / 1700 = 5.88%
    data = {
        "SYM_A": ("Contract A", [100, 200, 300]),
        "SYM_B": ("Contract B", [50, 50]),
        "SYM_C": ("Contract C", [1000]),
    }

    stats = compute_volume_stats(data)

    assert len(stats) == 3
    # Xếp hạng giảm dần: C > A > B
    assert stats[0].symbol == "SYM_C"
    assert stats[0].total_volume == 1000
    assert stats[0].volume_share_pct == 58.82

    assert stats[1].symbol == "SYM_A"
    assert stats[1].total_volume == 600
    assert stats[1].volume_share_pct == 35.29

    assert stats[2].symbol == "SYM_B"
    assert stats[2].total_volume == 100
    assert stats[2].volume_share_pct == 5.88


def test_compute_volume_stats_median():
    """Kiểm thử tính trung vị khối lượng cho số phiên lẻ, chẵn và rỗng."""
    data = {
        # Lẻ: [10, 20, 50, 100, 500] -> median = 50.0
        "ODD": ("Odd sessions", [10, 20, 50, 100, 500]),
        # Chẵn: [10, 20, 40, 100] -> median = (20 + 40) / 2 = 30.0
        "EVEN": ("Even sessions", [10, 20, 40, 100]),
        # Rỗng: [] -> median = 0.0
        "EMPTY": ("Empty sessions", []),
    }

    stats = {s.symbol: s for s in compute_volume_stats(data)}

    assert stats["ODD"].median_volume == 50.0
    assert stats["ODD"].sessions_count == 5

    assert stats["EVEN"].median_volume == 30.0
    assert stats["EVEN"].sessions_count == 4

    assert stats["EMPTY"].median_volume == 0.0
    assert stats["EMPTY"].sessions_count == 0


def test_compute_volume_stats_zero_total_volume():
    """Kiểm thử trường hợp biên khi toàn bộ volume = 0 (không chia cho 0)."""
    data = {
        "S1": ("Contract 1", [0, 0]),
        "S2": ("Contract 2", [0]),
    }
    stats = compute_volume_stats(data)
    assert len(stats) == 2
    for s in stats:
        assert s.total_volume == 0
        assert s.volume_share_pct == 0.0


def test_filter_living_contracts():
    """Kiểm thử lọc các hợp đồng còn sống tại ngày chỉ định."""
    as_of = date(2026, 9, 24)
    contracts = [
        ContractInfo("EXP1", "Expired 1", "DERIVATIVES", "2026/06/19", "2026/08/20"),
        ContractInfo("EXP2", "Expired 2", "DERIVATIVES", "2026/01/16", "2026/09/17"),
        ContractInfo("LIVE1", "Live 1", "DERIVATIVES", "2026/08/21", "2026/10/15"),
        ContractInfo("LIVE2", "Live 2", "DERIVATIVES", "2026/04/17", "2026/12/17"),
    ]

    living = filter_living_contracts(contracts, as_of)
    living_syms = [c.symbol for c in living]

    assert living_syms == ["LIVE1", "LIVE2"]


def test_identify_front_month():
    """Kiểm thử xác định hợp đồng front-month (đáo hạn gần nhất trong tương lai)."""
    as_of = date(2026, 9, 24)
    contracts = [
        ContractInfo("F1M", "Front Month", "DERIVATIVES", "2026/08/21", "2026/10/15"),
        ContractInfo("F2M", "Next Month", "DERIVATIVES", "2026/09/18", "2026/11/19"),
        ContractInfo("F1Q", "Next Quarter", "DERIVATIVES", "2026/04/17", "2026/12/17"),
        ContractInfo("F2Q", "Far Quarter", "DERIVATIVES", "2026/07/17", "2027/03/18"),
    ]

    front = identify_front_month(contracts, as_of)
    assert front is not None
    assert front.symbol == "F1M"


def test_find_winning_contract():
    """Kiểm thử chọn mã thắng cuộc từ bảng xếp hạng."""
    stats = [
        ContractVolumeStats("WINNER", "Winner", 20, 1_000_000, 50_000.0, 99.5),
        ContractVolumeStats("LOSER", "Loser", 20, 5_000, 250.0, 0.5),
    ]
    winner = find_winning_contract(stats)
    assert winner is not None
    assert winner.symbol == "WINNER"
    assert winner.volume_share_pct == 99.5

    assert find_winning_contract([]) is None
