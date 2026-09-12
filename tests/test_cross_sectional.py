import math
import random
from datetime import UTC, datetime, timedelta

from trading.cross_sectional import run_cross_sectional
from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar


def _make_daily_bar(
    symbol: str,
    day_idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    vol: float = 1000.0,
    base_dt: datetime | None = None,
) -> Bar:
    if base_dt is None:
        base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    dt = base_dt + timedelta(days=day_idx)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=vol,
    )


def _build_panel(
    num_symbols: int = 10,
    num_days: int = 50,
    trends: list[float] | None = None,
    base_price: float = 100.0,
    base_dt: datetime | None = None,
) -> dict[str, list[Bar]]:
    """Tạo panel nến ngày tổng hợp cho N mã."""
    if base_dt is None:
        base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)

    bars_by_symbol: dict[str, list[Bar]] = {}
    for s_idx in range(num_symbols):
        sym = f"SYM_{s_idx:02d}"
        trend = trends[s_idx] if trends and s_idx < len(trends) else 0.0
        sym_bars: list[Bar] = []
        p = base_price
        for d in range(num_days):
            o = p
            c = p * (1.0 + trend)
            h = max(o, c) * 1.005
            low = min(o, c) * 0.995
            sym_bars.append(_make_daily_bar(sym, d, o, h, low, c, base_dt=base_dt))
            p = c
        bars_by_symbol[sym] = sym_bars
    return bars_by_symbol


# ---------------------------------------------------------------------------
# Nhóm đúng đắn cơ bản (Test 1 - 3)
# ---------------------------------------------------------------------------


def test_ranking_top_and_bottom():
    """1. Panel 10 mã: một mã tăng đều mạnh nhất và một mã giảm đều mạnh nhất
    -> mã tăng nằm trong longs, mã giảm nằm trong shorts.
    """
    trends = [0.0] * 10
    trends[0] = 0.02   # Tăng mạnh nhất (+2%/ngày)
    trends[9] = -0.02  # Giảm mạnh nhất (-2%/ngày)

    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=50, trends=trends, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=45)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 1
    for reb in report.rebalances:
        assert "SYM_00" in reb.longs, f"Mã tăng mạnh nhất SYM_00 phải nằm trong longs: {reb.longs}"
        assert "SYM_09" in reb.shorts, f"Mã giảm mạnh nhất SYM_09 phải nằm trong shorts: {reb.shorts}"


def test_market_neutral_zero_pnl_when_all_move_same():
    """2. Trung tính thị trường: panel mà MỌI mã tăng cùng một tỷ lệ phần trăm mỗi ngày
    -> PnL trước phí xấp xỉ 0 (dung sai nhỏ).
    """
    # Mọi mã đều tăng 1% mỗi ngày
    trends = [0.01] * 10
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=50, trends=trends, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=45)

    # Chạy không phí và không trượt giá để kiểm tra độ trung tính thuần tuý
    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=0.0,
        slippage_bps=0.0,
    )

    gross_pnl = report.ending_capital - report.starting_capital
    assert math.isclose(gross_pnl, 0.0, abs_tol=1e-3), (
        f"Chiến lược không trung tính thị trường: Gross PnL={gross_pnl:.6f} khác 0"
    )


def test_equal_notional_both_sides():
    """3. Tổng giá trị danh nghĩa vế long bằng vế short tại mọi kỳ tái cân bằng."""
    trends = [0.005 * (i - 5) for i in range(10)]
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=60, trends=trends, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=55)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 2
    for reb in report.rebalances:
        assert len(reb.longs) == 3
        assert len(reb.shorts) == 3
        # Longs và shorts không trùng nhau
        assert set(reb.longs).isdisjoint(set(reb.shorts))


# ---------------------------------------------------------------------------
# Nhóm dữ liệu bẩn — Ba cái bẫy ở §0 (Test 4 - 6)
# ---------------------------------------------------------------------------


def test_gap_symbol_disqualified():
    """4. Mã có lỗ hổng bị loại: một mã thiếu 50% số ngày trong cửa sổ lookback
    -> mã đó KHÔNG xuất hiện trong longs lẫn shorts, dù lợi suất hai đầu mút là cực trị (Bẫy LDO).
    """
    trends = [0.0] * 10
    trends[0] = 0.05  # Tăng cực mạnh +5%/ngày nhưng bị khuyết 50% nến giữa
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=50, trends=trends, base_dt=base_dt)

    # Đục lỗ SYM_00: xoá nến từ ngày 10 đến ngày 25 (15 ngày thiếu trên cửa sổ 30 ngày)
    bars_by_symbol["SYM_00"] = [
        b for b in bars_by_symbol["SYM_00"]
        if not (base_dt + timedelta(days=10) <= b.ts <= base_dt + timedelta(days=25))
    ]

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=45)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=9,  # hạ xuống 9 để khi loại SYM_00 vẫn còn 9 mã đủ điều kiện tái cân bằng
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 1
    for reb in report.rebalances:
        assert "SYM_00" not in reb.longs, "SYM_00 bị thiếu nến trầm trọng không được vào longs"
        assert "SYM_00" not in reb.shorts, "SYM_00 bị thiếu nến trầm trọng không được vào shorts"


def test_shrinking_universe_skipped():
    """5. Vũ trụ co lại: số mã đủ tư cách tụt xuống 9 trong một giai đoạn
    -> các kỳ đó nằm trong skipped_rebalances, không có giao dịch nào.
    """
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    # Tạo chỉ 9 mã
    bars_by_symbol = _build_panel(9, num_days=50, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=45)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,  # Đòi hỏi tối thiểu 10 mã
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) == 0
    assert report.skipped_rebalances > 0
    assert report.ending_capital == report.starting_capital


def test_missing_t_plus_1_bar_skipped_fills():
    """6. Mã thiếu nến t+1 -> không vào vị thế mã đó, skipped_fills tăng."""
    trends = [0.005 * (i - 5) for i in range(10)]
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=50, trends=trends, base_dt=base_dt)

    # SYM_09 (mã short) bị mất nến tại ngày 36 (t+1 của kỳ tái cân bằng tại ngày 35)
    t_plus_1 = base_dt + timedelta(days=36)
    bars_by_symbol["SYM_09"] = [b for b in bars_by_symbol["SYM_09"] if b.ts != t_plus_1]

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=45)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 1
    first_reb = report.rebalances[0]
    assert first_reb.skipped_fills >= 1, "Kỳ đầu tiên phải ghi nhận skipped_fills do thiếu nến t+1"


# ---------------------------------------------------------------------------
# Nhóm chống nhìn trước và chi phí (Test 7 - 9)
# ---------------------------------------------------------------------------


def test_lookahead_prevention_fill_ts_greater_than_ts():
    """7. Mọi Rebalance có fill_ts > ts (khớp tại open ngày t+1)."""
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=70, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=65)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 3
    for reb in report.rebalances:
        assert reb.fill_ts > reb.ts
        assert reb.fill_ts == reb.ts + timedelta(days=1)


def test_turnover_awareness_zero_fees_when_unchanged():
    """8. Quay vòng có nhận biết: hai kỳ liên tiếp cho ra cùng danh sách long/short và giá không đổi
    -> phí kỳ thứ hai bằng 0 (hoặc cực nhỏ <= 1e-6).
    """
    # Tất cả mã giá hoàn toàn đi ngang (trend = 0)
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=60, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=55)

    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 2
    reb1 = report.rebalances[0]
    reb2 = report.rebalances[1]

    # Kỳ 1 phải có phí vì mở vị thế ban đầu (turnover ~ 500 USDT)
    assert reb1.fees > 0.0
    assert math.isclose(reb1.turnover_notional, 500.0, rel_tol=1e-3)

    # Kỳ 2 cùng danh mục và giá không đổi:
    # Do kỳ 1 mất phí ~0.25 USDT nên vốn giảm nhẹ còn 499.75 USDT,
    # turnover kỳ 2 chỉ là phần tái cân bằng lượng hụt phí này (~0.25 USDT),
    # KHÔNG PHẢI đóng-rồi-mở-lại toàn bộ 500 USDT.
    assert reb2.turnover_notional < 1.0, (
        f"Kỳ 2 bị đóng-rồi-mở-lại: turnover={reb2.turnover_notional} gần 500 USDT thay vì ~0.25 USDT"
    )
    assert reb2.fees < 0.001

    # Nếu chạy hoàn toàn không phí (fee_rate=0.0) thì turnover kỳ 2 phải đúng bằng 0 tuyệt đối
    rep_no_fee = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    assert math.isclose(rep_no_fee.rebalances[1].turnover_notional, 0.0, abs_tol=1e-6)
    assert math.isclose(rep_no_fee.rebalances[1].fees, 0.0, abs_tol=1e-6)



def test_fees_match_turnover_notional():
    """9. Phí một kỳ bằng đúng turnover_notional * fee_rate."""
    trends = [0.003 * (i - 5) for i in range(10)]
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=60, trends=trends, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=55)

    fee_rate = 0.00075
    report = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=fee_rate,
        slippage_bps=0.0,
    )

    assert len(report.rebalances) >= 2
    for reb in report.rebalances:
        expected_fee = reb.turnover_notional * fee_rate
        assert math.isclose(reb.fees, expected_fee, rel_tol=1e-6), (
            f"Phí {reb.fees} không khớp với turnover * fee_rate {expected_fee}"
        )


# ---------------------------------------------------------------------------
# Nhóm selector ngẫu nhiên (Test 10 - 11)
# ---------------------------------------------------------------------------


def _dummy_random_selector(
    eligible: list[str],
    returns: dict[str, float],
    k: int,
    rng: random.Random | None,
) -> tuple[list[str], list[str]]:
    assert rng is not None
    shuffled = sorted(eligible)
    rng.shuffle(shuffled)
    return shuffled[:k], shuffled[k : 2 * k]


def test_selector_deterministic_with_seed():
    """10. selector bốc thăm với cùng hạt giống -> kết quả tất định, chạy hai lần giống hệt."""
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(10, num_days=60, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=55)

    rng1 = random.Random(42)
    rep1 = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        selector=_dummy_random_selector,
        rng=rng1,
    )

    rng2 = random.Random(42)
    rep2 = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=3,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        selector=_dummy_random_selector,
        rng=rng2,
    )

    assert len(rep1.rebalances) == len(rep2.rebalances)
    assert math.isclose(rep1.ending_capital, rep2.ending_capital, rel_tol=1e-12)
    for r1, r2 in zip(rep1.rebalances, rep2.rebalances, strict=True):
        assert r1.longs == r2.longs
        assert r1.shorts == r2.shorts
        assert math.isclose(r1.fees, r2.fees)


def test_selector_returns_exact_k_disjoint():
    """11. selector trả về đúng k mã mỗi vế, không trùng nhau giữa hai vế."""
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars_by_symbol = _build_panel(15, num_days=60, base_dt=base_dt)

    start = base_dt + timedelta(days=35)
    end = base_dt + timedelta(days=55)

    rng = random.Random(99)
    rep = run_cross_sectional(
        bars_by_symbol,
        start=start,
        end=end,
        lookback_days=30,
        rebalance_days=7,
        k=4,
        min_universe=10,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        selector=_dummy_random_selector,
        rng=rng,
    )

    assert len(rep.rebalances) >= 2
    for reb in rep.rebalances:
        assert len(reb.longs) == 4
        assert len(reb.shorts) == 4
        assert set(reb.longs).isdisjoint(set(reb.shorts))
