"""Test cho scripts/audit_information.py (Brief đợt 41).

Kiểm tra:
- Hàm fast_spearman_rank_correlation (đúng lý thuyết, xử lý ties)
- Kiểm tra hoán vị theo khối
- Kiểm tra tính toán phân vị và deciles
- Đối chứng dương và đối chứng âm
"""

import random

from scripts.audit_information import (
    analyze_deciles,
    compute_all_correlations,
    fast_spearman_rank_correlation,
    run_block_permutation_test,
)


def test_spearman_rank_correlation_perfect():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 20.0, 30.0, 40.0, 50.0]
    rho = fast_spearman_rank_correlation(x, y)
    assert abs(rho - 1.0) < 1e-6

    y_inv = [50.0, 40.0, 30.0, 20.0, 10.0]
    rho_inv = fast_spearman_rank_correlation(x, y_inv)
    assert abs(rho_inv - (-1.0)) < 1e-6


def test_spearman_rank_correlation_with_ties():
    x = [1.0, 2.0, 2.0, 4.0, 5.0]
    y = [5.0, 6.0, 7.0, 8.0, 9.0]
    rho = fast_spearman_rank_correlation(x, y)
    assert 0.95 < rho <= 1.0


def test_analyze_deciles():
    # Tạo 100 hàng có x tăng dần từ 1 đến 100, y = 2 * x
    panel = [{"feat": float(i), "target": float(2 * i)} for i in range(100)]
    deciles = analyze_deciles(panel, "feat", "target")

    assert len(deciles) == 10
    # Kiểm tra tính đơn điệu hoàn hảo
    for i in range(1, 10):
        assert deciles[i]["mean_fwd_ret_pct"] > deciles[i - 1]["mean_fwd_ret_pct"]
    assert deciles[0]["count"] == 10
    assert deciles[-1]["count"] == 10


def test_positive_and_negative_controls():
    """Kiểm chứng đối chứng dương và đối chứng âm (Brief §3.5)."""
    rng = random.Random(12345)
    n_rows = 500

    panel = []
    for _ in range(n_rows):
        fwd_ret = rng.gauss(0, 0.01)
        # Cheat: Tương quan cực mạnh với fwd_ret
        cheat = fwd_ret + rng.gauss(0, 0.0001)
        # Noise: Không liên quan
        noise = rng.gauss(0, 1.0)

        panel.append({
            "cheat": cheat,
            "noise": noise,
            "target_1h": fwd_ret,
        })

    corrs = compute_all_correlations(panel, feature_names=["cheat", "noise"], target_names=["target_1h"])
    rho_cheat = corrs[("cheat", "target_1h")][0]
    rho_noise = corrs[("noise", "target_1h")][0]

    assert rho_cheat > 0.95
    assert abs(rho_noise) < 0.15

    # Chạy hoán vị khối với 50 lần kiểm tra
    thresh_95, _ = run_block_permutation_test(
        panel,
        n_permutations=50,
        block_size_hours=24,
        seed=42,
        feature_names=["cheat", "noise"],
        target_names=["target_1h"],
    )

    # Đối chứng dương: cheat vượt ngưỡng 95 áp đảo
    assert abs(rho_cheat) > thresh_95
    # Đối chứng âm: noise không vượt ngưỡng 95
    assert abs(rho_noise) < thresh_95
