import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from scripts.significance_test import (
    calculate_percentile,
    empirical_percentile_rank,
    run_null_simulation,
)
from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar
from trading.perp_backtest import (
    RandomEntryConfig,
    run_perp_backtest,
)


def _make_bar(
    idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    vol: float = 100.0,
    symbol: str = "BTC-USDT",
) -> Bar:
    base_dt = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    dt = base_dt + timedelta(hours=idx)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=vol,
    )


def _build_warmup_bars(n: int = 280, base_price: float = 100.0) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(n):
        bars.append(_make_bar(i, base_price, base_price + 1.0, base_price - 1.0, base_price))
    return bars


def _build_oscillating_bars(n: int = 400, seed: int = 123) -> list[Bar]:
    """Tạo chuỗi nến có biến động và xu hướng ngẫu nhiên để các lệnh chờ có thể khớp."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    p = 100.0
    for i in range(n):
        step = rng.gauss(0.0, 1.0)
        p += step
        o = p
        c = p + rng.gauss(0.0, 0.5)
        h = max(o, c) + abs(rng.gauss(0.5, 0.5))
        l = min(o, c) - abs(rng.gauss(0.5, 0.5))
        bars.append(_make_bar(i, o, h, l, c))
    return bars


def _build_module_b_warmup_bars(n: int = 280) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(n):
        delta = math.sin(i * 0.05) * 0.5
        if i % 2 == 0:
            bars.append(_make_bar(i, 99.5, 101.5 + delta, 98.5 - delta, 101.0 + delta))
        else:
            bars.append(_make_bar(i, 100.5, 101.0 + delta, 98.0 - delta, 99.0 - delta))
    return bars


# ---------------------------------------------------------------------------
# Task 1: Kiểm chứng chế độ ngẫu nhiên và bộ đếm (§1.5)
# ---------------------------------------------------------------------------


def test_random_entry_deterministic_same_seed():
    """1. Cùng seed chạy 2 lần -> PerpReport giống hệt (số lệnh, net_pnl từng chữ số)."""
    bars = _build_oscillating_bars(350)
    cfg1 = RandomEntryConfig(seed=42, signal_prob=0.1, long_prob=0.5)
    cfg2 = RandomEntryConfig(seed=42, signal_prob=0.1, long_prob=0.5)

    rep1 = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg1)
    rep2 = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg2)

    assert len(rep1.trades) == len(rep2.trades)
    assert rep1.signals_generated == rep2.signals_generated
    assert math.isclose(rep1.ending_capital, rep2.ending_capital, rel_tol=1e-12)
    for t1, t2 in zip(rep1.trades, rep2.trades, strict=True):
        assert t1.side == t2.side
        assert math.isclose(t1.entry_price, t2.entry_price)
        assert math.isclose(t1.net_pnl, t2.net_pnl)


def test_random_entry_different_seed():
    """2. Seed khác nhau -> kết quả khác nhau."""
    bars = _build_oscillating_bars(350)
    cfg1 = RandomEntryConfig(seed=42, signal_prob=0.1, long_prob=0.5)
    cfg2 = RandomEntryConfig(seed=999, signal_prob=0.1, long_prob=0.5)

    rep1 = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg1)
    rep2 = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg2)

    trades1_summary = [(t.entry_ts, t.side, round(t.net_pnl, 4)) for t in rep1.trades]
    trades2_summary = [(t.entry_ts, t.side, round(t.net_pnl, 4)) for t in rep2.trades]
    assert trades1_summary != trades2_summary


def test_random_entry_side_probability():
    """3. long_prob=1.0 -> 100% LONG; long_prob=0.0 -> 100% SHORT."""
    bars = _build_oscillating_bars(350)

    # 100% Long
    cfg_long = RandomEntryConfig(seed=42, signal_prob=0.15, long_prob=1.0)
    rep_long = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg_long)
    assert len(rep_long.trades) > 0
    assert all(t.side == "LONG" for t in rep_long.trades)

    # 100% Short
    cfg_short = RandomEntryConfig(seed=42, signal_prob=0.15, long_prob=0.0)
    rep_short = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg_short)
    assert len(rep_short.trades) > 0
    assert all(t.side == "SHORT" for t in rep_short.trades)


def test_random_entry_zero_signal_prob():
    """4. signal_prob=0.0 -> không có lệnh nào, signals_generated == 0."""
    bars = _build_oscillating_bars(350)
    cfg_zero = RandomEntryConfig(seed=1, signal_prob=0.0, long_prob=0.5)
    rep = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg_zero)

    assert rep.signals_generated == 0
    assert len(rep.trades) == 0
    assert rep.ending_capital == rep.starting_capital


def test_random_entry_warmup_blocked():
    """5. Không phát tín hiệu ở bar chưa đủ warm-up: dù signal_prob=1.0, signals_generated < len(bars)."""
    # 280 bars: Module A cần 64 bar đầu để đủ Donchian 20 + ATR14 + 50 bar ATR history
    bars = _build_warmup_bars(280)
    cfg = RandomEntryConfig(seed=1, signal_prob=1.0, long_prob=0.5)
    rep = run_perp_backtest(bars, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg)

    # signals_generated phải nhỏ hơn số bar vì phần đầu chuỗi bị chặn
    assert rep.signals_generated < len(bars)
    # 64 bar đầu tiên không thể phát tín hiệu, nên số tín hiệu không thể vượt quá (len(bars) - 64)
    assert rep.signals_generated <= (len(bars) - 64 + 1)


def test_counter_accounting_equation():
    """6. Phương trình đối soát §1.4 cho cả 2 module:
    signals_generated == orders_expired + orders_cancelled + orders_dropped + len(trades) + con_treo
    với con_treo in (0, 1).
    """
    # Test Module A
    bars_a = _build_oscillating_bars(400, seed=1)
    for seed in [1, 42, 100]:
        cfg = RandomEntryConfig(seed=seed, signal_prob=0.08, long_prob=0.5)
        rep_a = run_perp_backtest(bars_a, "donchian_breakout", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg)
        con_treo_a = rep_a.signals_generated - (
            rep_a.orders_expired + rep_a.orders_cancelled + rep_a.orders_dropped + len(rep_a.trades)
        )
        assert con_treo_a in (0, 1), f"Module A seed {seed} vi phạm đối soát: con_treo={con_treo_a}"

    # Test Module B
    bars_b = _build_module_b_warmup_bars(400)
    for seed in [1, 42, 100]:
        cfg = RandomEntryConfig(seed=seed, signal_prob=0.08, long_prob=0.5)
        rep_b = run_perp_backtest(bars_b, "bollinger_mr", fee_rate=BINGX_PERP_TAKER, slippage_bps=0.0, random_entry=cfg)
        con_treo_b = rep_b.signals_generated - (
            rep_b.orders_expired + rep_b.orders_cancelled + rep_b.orders_dropped + len(rep_b.trades)
        )
        assert con_treo_b in (0, 1), f"Module B seed {seed} vi phạm đối soát: con_treo={con_treo_b}"


# ---------------------------------------------------------------------------
# Task 2: Kiểm chứng tính tất định, đối chứng dương và đối chứng âm (§2.5)
# ---------------------------------------------------------------------------


def test_significance_deterministic():
    """Task 2.1: Tất định - cùng tham số chạy 2 lần -> phân vị giống hệt."""
    bars = _build_oscillating_bars(320)
    stats1 = run_null_simulation(
        bars=bars,
        module="donchian_breakout",
        iterations=20,
        signal_prob=0.05,
        long_prob=0.5,
        real_pnl=2.5,
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
        max_workers=1,
    )
    stats2 = run_null_simulation(
        bars=bars,
        module="donchian_breakout",
        iterations=20,
        signal_prob=0.05,
        long_prob=0.5,
        real_pnl=2.5,
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
        max_workers=1,
    )

    assert math.isclose(stats1.real_percentile, stats2.real_percentile)
    assert math.isclose(stats1.median, stats2.median)
    assert math.isclose(stats1.p95, stats2.p95)


def test_positive_control_synthetic_trend():
    """Task 2.2: ĐỐI CHỨNG DƯƠNG (§2.5.2) - Tiêu chí quan trọng nhất của cả brief.
    Dựng chuỗi giá tổng hợp có Donchian breakout thật tiếp diễn mạnh:
    Mỗi lần phá đỉnh kênh 20, các bar sau luôn tiếp diễn mạnh chạm TP (+2R);
    thời gian còn lại giá đi ngang nhiễu.
    Khẳng định: kết quả thật nằm trên phân vị 95 của phân phối null (percentile >= 95.0).
    """
    bars: list[Bar] = []
    # 260 bar warm-up TR=2.0
    for i in range(260):
        bars.append(_make_bar(i, 100.0, 101.0, 99.0, 100.0))
    for i in range(260, 270):
        bars.append(_make_bar(i, 100.0, 102.0, 98.0, 100.0))

    cur = 270
    base = 100.0
    # 5 chu kỳ breakout hoàn hảo
    for _cycle in range(5):
        # 1. Signal bar phá đỉnh kênh Donchian với CLV cao
        bars.append(_make_bar(cur, base + 1.0, base + 5.0, base, base + 4.5))
        cur += 1
        # 2. Entry bar khớp trigger
        bars.append(_make_bar(cur, base + 2.0, base + 3.0, base + 1.5, base + 2.5))
        cur += 1
        # 3. TP bar tăng vọt chạm TP (+2R)
        bars.append(_make_bar(cur, base + 3.5, base + 20.0, base + 3.0, base + 15.0))
        cur += 1
        base += 15.0
        # 4. Sideways bars đi ngang ổn định kênh Donchian mới
        for _j in range(40):
            bars.append(_make_bar(cur, base, base + 1.0, base - 1.0, base))
            cur += 1
        for _j in range(15):
            bars.append(_make_bar(cur, base, base + 2.0, base - 2.0, base))
            cur += 1

    # Chạy kết quả thật
    rep_real = run_perp_backtest(
        bars,
        module="donchian_breakout",
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
    )
    real_pnl = rep_real.ending_capital - rep_real.starting_capital
    assert len(rep_real.trades) >= 4, f"Lượt thật phải có ít nhất 4 trade, thực tế: {len(rep_real.trades)}"
    assert all(t.exit_reason == "TP" for t in rep_real.trades), "Mọi trade thật phải ăn TP"

    # Chạy 50 lượt đối chứng null ngẫu nhiên
    stats = run_null_simulation(
        bars=bars,
        module="donchian_breakout",
        iterations=50,
        signal_prob=0.03,
        long_prob=0.5,
        real_pnl=real_pnl,
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
        max_workers=1,
    )

    # Khẳng định phân vị của kết quả thật nằm trên phân vị 95
    assert stats.real_percentile >= 95.0, (
        f"Đối chứng dương THẤT BẠI: real_pnl={real_pnl:.2f}, phân vị={stats.real_percentile:.1f}% (< 95.0%)"
    )


def test_negative_control_random_walk():
    """Task 2.3: Đối chứng âm (§2.5.3).
    Trên chuỗi bước ngẫu nhiên (random walk, hạt giống cố định),
    kết quả thật KHÔNG nằm trên phân vị 95 (real_percentile < 95.0).
    """
    rng = random.Random(42)
    bars: list[Bar] = []
    price = 100.0
    for i in range(600):
        change = rng.gauss(0.0, 1.0)
        o = price
        c = price + change
        h = max(o, c) + abs(rng.gauss(0.0, 0.5))
        low = min(o, c) - abs(rng.gauss(0.0, 0.5))
        bars.append(_make_bar(i, o, h, low, c))
        price = c

    rep_real = run_perp_backtest(
        bars,
        module="donchian_breakout",
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
    )
    real_pnl = rep_real.ending_capital - rep_real.starting_capital

    stats = run_null_simulation(
        bars=bars,
        module="donchian_breakout",
        iterations=50,
        signal_prob=0.03,
        long_prob=0.5,
        real_pnl=real_pnl,
        capital=500.0,
        fee_rate=BINGX_PERP_TAKER,
        slippage_bps=0.0,
        risk_fraction=0.005,
        max_leverage=10.0,
        use_ema_filter=False,
        max_workers=1,
    )

    # Khẳng định trên random walk, kết quả thật không có lợi thế (dưới phân vị 95)
    assert stats.real_percentile < 95.0, (
        f"Đối chứng âm THẤT BẠI: real_pnl={real_pnl:.2f} lại vượt phân vị 95 ({stats.real_percentile:.1f}%)"
    )


def test_percentile_helper_functions():
    """Kiểm tra độ chính xác của các hàm phụ trợ tính phân vị."""
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Median = 3.0
    assert math.isclose(calculate_percentile(data, 50.0), 3.0)
    # p0 = 1.0, p100 = 5.0
    assert math.isclose(calculate_percentile(data, 0.0), 1.0)
    assert math.isclose(calculate_percentile(data, 100.0), 5.0)

    # Empirical rank
    # target = 3.0 -> 2 less, 1 equal -> (2 + 0.5) / 5 = 50%
    assert math.isclose(empirical_percentile_rank(data, 3.0), 50.0)
    # target = 6.0 -> 5 less -> 100%
    assert math.isclose(empirical_percentile_rank(data, 6.0), 100.0)
    # target = 0.0 -> 0 less -> 0%
    assert math.isclose(empirical_percentile_rank(data, 0.0), 0.0)


def test_phan_vi_tren_danh_sach_rong_phai_raise_khong_tra_0():
    """Danh sách rỗng thì hai hàm phân vị phải RAISE, không được trả 0.0.

    Vì sao quan trọng: `empirical_percentile_rank` là hàm dùng để đổi phân phối
    đối chứng thành p-value. Trả 0.0 khi rỗng nghĩa là "target thấp hơn toàn bộ
    đối chứng" — một kết luận thống kê thật, sinh ra từ chỗ không có dữ liệu nào.
    Tuỳ cách người gọi quy đổi, nó có thể thành p = 0, tức "rất có ý nghĩa".

    Lưu ý: `empirical_percentile_rank([1,2,3,4,5], 0.0) == 0.0` vẫn ĐÚNG và phải
    giữ, vì ở đó danh sách không rỗng và target thật sự thấp hơn mọi phần tử.
    Test 351-362 trong file này đã ghim điều đó.
    """
    with pytest.raises(ValueError, match="danh sách rỗng"):
        calculate_percentile([], 50.0)

    with pytest.raises(ValueError, match="phân phối đối chứng rỗng"):
        empirical_percentile_rank([], 1.23)

    # Danh sach khong rong thi van tra 0.0 nhu cu, khong bi anh huong
    assert empirical_percentile_rank([1.0, 2.0, 3.0], 0.0) == 0.0
