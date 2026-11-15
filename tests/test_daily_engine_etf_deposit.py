"""Unit & integration tests for EtfDepositStrategy (Brief 239 §2-§4)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts.measure_etf_deposit_mix import MAIN_RATE, MAIN_WEIGHT, SYMBOL
from tests.conftest import TEST_DSN
from trading.calendar_vn import TZ
from trading.daily_engine.core import DailyBar
from trading.daily_engine.runner import CAPITAL, run_daily_engine
from trading.daily_engine.strategy import (
    STRATEGIES,
    DailyContext,
    EtfDepositStrategy,
    OrderIntent,
    resolve_strategy,
)
from trading.models import Bar
from trading.storage.db import Storage


def _ts_vn(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=TZ)


@pytest.fixture
def clean_daily_db() -> Storage:
    storage = Storage(TEST_DSN)
    storage.init_schema()
    with storage.conn() as c:
        c.execute(
            "TRUNCATE paper_daily_state, paper_daily_lots, paper_daily_orders, paper_daily_nav, "
            "bars_daily, symbol_universe RESTART IDENTITY CASCADE"
        )
    yield storage
    with storage.conn() as c:
        c.execute(
            "TRUNCATE paper_daily_state, paper_daily_lots, paper_daily_orders, paper_daily_nav, "
            "bars_daily, symbol_universe RESTART IDENTITY CASCADE"
        )


def _seed_universe(storage: Storage, symbols: list[str]) -> None:
    storage.upsert_symbol_universe(
        [
            {
                "symbol": sym,
                "exchange": "HOSE",
                "avg_value_20d": 10_000_000_000.0,
                "avg_volume_20d": 500_000.0,
                "is_active": True,
            }
            for sym in symbols
        ]
    )


def _seed_day_bars(
    storage: Storage,
    d: date,
    prices: dict[str, tuple[float, float]],
) -> None:
    bars = [
        Bar(
            symbol=sym,
            ts=_ts_vn(d),
            open=op,
            high=max(op, cl) * 1.01,
            low=min(op, cl) * 0.99,
            close=cl,
            volume=100_000,
            source="test",
        )
        for sym, (op, cl) in prices.items()
    ]
    storage.write_daily(bars)


def test_etf_deposit_constants_match_measure_etf_deposit_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hằng của EtfDepositStrategy khớp tuyệt đối với scripts/measure_etf_deposit_mix.py."""
    assert "etf_deposit" in STRATEGIES
    strat = EtfDepositStrategy()
    assert strat.name == "etf_deposit"
    assert strat.ETF_SYMBOL == SYMBOL
    assert strat.ETF_WEIGHT == MAIN_WEIGHT
    assert strat.cash_rate == MAIN_RATE

    monkeypatch.setenv("DAILY_ENGINE_STRATEGY", "etf_deposit")
    resolved = resolve_strategy()
    assert isinstance(resolved, EtfDepositStrategy)


def test_mutation_f_target_uses_nav_not_cash_and_floors_to_lot_100() -> None:
    """Phép phá (f): target = floor(ETF_WEIGHT * nav / close / 100) * 100 (dùng nav, không dùng cash)."""
    strat = EtfDepositStrategy()
    bar = DailyBar(SYMBOL, date(2026, 6, 15), 21_500.0, 21_700.0, 21_400.0, 21_500.0, 50_000)
    # 0.15 * 100_000_000 / 21_500 = 697.6744 -> floor to lot 100 = 600
    # (vs round -> 700; unrounded -> 697; cash=20M -> floor(0.15*20M/21500/100)*100 = 100)
    ctx = DailyContext(
        d=date(2026, 6, 15),
        universe=[SYMBOL],
        cash=20_000_000.0,
        nav=100_000_000.0,
        positions={},
        bars_loader=lambda sym, n: [bar] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=date(2026, 6, 16),
    )
    assert strat.on_day(ctx) == [OrderIntent(SYMBOL, "BUY", 600)]


def test_mutation_g_rebalance_only_at_year_end_not_mid_year_and_not_never() -> None:
    """Phép phá (g): Khi pos > 0 chỉ tái cân bằng ở phiên cuối năm (next_trading_day.year > d.year)."""
    strat = EtfDepositStrategy()
    # Mid-year -> [] even with 200 share gap (pos=500, target=700)
    bar_mid = DailyBar(SYMBOL, date(2026, 6, 15), 20_000.0, 20_500.0, 19_800.0, 20_000.0, 50_000)
    ctx_mid = DailyContext(
        d=date(2026, 6, 15),
        universe=[SYMBOL],
        cash=90_000_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 500},
        bars_loader=lambda sym, n: [bar_mid] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=date(2026, 6, 16),
    )
    assert strat.on_day(ctx_mid) == []

    # next_trading_day=None -> [] (cannot assume year-end)
    bar_end = DailyBar(SYMBOL, date(2026, 12, 31), 20_000.0, 20_500.0, 19_800.0, 20_000.0, 50_000)
    ctx_none = DailyContext(
        d=date(2026, 12, 31),
        universe=[SYMBOL],
        cash=90_000_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 500},
        bars_loader=lambda sym, n: [bar_end] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=None,
    )
    assert strat.on_day(ctx_none) == []

    # True year-end (2026-12-31 -> 2027-01-04) -> rebalances +200
    ctx_end = DailyContext(
        d=date(2026, 12, 31),
        universe=[SYMBOL],
        cash=90_000_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 500},
        bars_loader=lambda sym, n: [bar_end] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=date(2027, 1, 4),
    )
    assert strat.on_day(ctx_end) == [OrderIntent(SYMBOL, "BUY", 200)]


def test_mutation_h_no_order_when_etf_bar_missing_or_wrong_date_or_nonpositive_close() -> None:
    """Phép phá (h): Không có nến, nến cuối khác ctx.d, hoặc close <= 0 -> trả []."""
    strat = EtfDepositStrategy()
    d = date(2026, 12, 31)
    next_td = date(2027, 1, 4)

    # Empty bars
    ctx_empty = DailyContext(
        d=d,
        universe=[SYMBOL],
        cash=100_000_000.0,
        nav=100_000_000.0,
        positions={},
        bars_loader=lambda _sym, _n: [],
        next_trading_day=next_td,
    )
    assert strat.on_day(ctx_empty) == []

    # Stale bar (date < ctx.d) on initial buy AND on year-end rebalance
    stale_bar = DailyBar(SYMBOL, date(2026, 12, 30), 20_000.0, 20_200.0, 19_800.0, 20_000.0, 50_000)
    for pos in ({}, {SYMBOL: 500}):
        ctx_stale = DailyContext(
            d=d,
            universe=[SYMBOL],
            cash=90_000_000.0,
            nav=100_000_000.0,
            positions=pos,
            bars_loader=lambda sym, n: [stale_bar] if sym == SYMBOL and n >= 1 else [],
            next_trading_day=next_td,
        )
        assert strat.on_day(ctx_stale) == []

    # Non-positive close
    bad_bar = DailyBar(SYMBOL, d, 20_000.0, 20_200.0, 0.0, 0.0, 50_000)
    ctx_zero_close = DailyContext(
        d=d,
        universe=[SYMBOL],
        cash=100_000_000.0,
        nav=100_000_000.0,
        positions={},
        bars_loader=lambda sym, n: [bad_bar] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=next_td,
    )
    assert strat.on_day(ctx_zero_close) == []


def test_mutation_i_rebalance_direction_and_under_100_lot_threshold() -> None:
    """Phép phá (i): Thừa tỷ trọng -> SELL (đúng dấu); |diff| < 100 cp -> []."""
    strat = EtfDepositStrategy()
    d_end = date(2026, 12, 31)
    next_td = date(2027, 1, 4)
    bar_end = DailyBar(SYMBOL, d_end, 20_000.0, 20_500.0, 19_800.0, 20_000.0, 50_000)

    # Overweight: pos=900, target=700, diff=-200 -> SELL 200
    ctx_over = DailyContext(
        d=d_end,
        universe=[SYMBOL],
        cash=82_000_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 900},
        bars_loader=lambda sym, n: [bar_end] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=next_td,
    )
    assert strat.on_day(ctx_over) == [OrderIntent(SYMBOL, "SELL", 200)]

    # Underweight: pos=500, target=700, diff=+200 -> BUY 200
    ctx_under = DailyContext(
        d=d_end,
        universe=[SYMBOL],
        cash=90_000_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 500},
        bars_loader=lambda sym, n: [bar_end] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=next_td,
    )
    assert strat.on_day(ctx_under) == [OrderIntent(SYMBOL, "BUY", 200)]

    # Sub-lot gap: pos=650 (diff=+50) and pos=750 (diff=-50) -> []
    for pos in (650, 750, 700):
        ctx_small_diff = DailyContext(
            d=d_end,
            universe=[SYMBOL],
            cash=86_000_000.0,
            nav=100_000_000.0,
            positions={SYMBOL: pos},
            bars_loader=lambda sym, n: [bar_end] if sym == SYMBOL and n >= 1 else [],
            next_trading_day=next_td,
        )
        assert strat.on_day(ctx_small_diff) == []

    # Raw fractional gap 80 shares (0.15 * 100M / 19230 = 780.03 -> floor=700): pos=700 -> diff=0 -> []
    bar_frac = DailyBar(SYMBOL, d_end, 19_230.0, 19_500.0, 19_000.0, 19_230.0, 50_000)
    ctx_frac = DailyContext(
        d=d_end,
        universe=[SYMBOL],
        cash=86_539_000.0,
        nav=100_000_000.0,
        positions={SYMBOL: 700},
        bars_loader=lambda sym, n: [bar_frac] if sym == SYMBOL and n >= 1 else [],
        next_trading_day=next_td,
    )
    assert strat.on_day(ctx_frac) == []


@pytest.mark.integration
def test_etf_deposit_six_sessions_year_end_rebalance_hand_calculated(
    clean_daily_db: Storage,
) -> None:
    """§4: 6 phiên tổng hợp đi qua cuối năm (12/2026 -> 01/2027), đối chiếu từng ngày với số tính tay."""
    storage = clean_daily_db
    _seed_universe(storage, [SYMBOL])

    init_d = date(2026, 12, 25)
    sessions = [
        date(2026, 12, 28),  # d1: +3d interest -> BUY 700
        date(2026, 12, 29),  # d2: +1d interest -> BUY 700 fills @ open=20_000
        date(2026, 12, 30),  # d3: +1d interest -> hold 700 (mid-year, no rebalance)
        date(2026, 12, 31),  # d4 (year-end): +1d interest, close=30_000 -> target=500 -> SELL 200
        date(2027, 1, 4),    # d5 (new year, +4d interest): SELL 200 fills @ open=30_000
        date(2027, 1, 5),    # d6: +1d interest -> hold 500
    ]

    _seed_day_bars(storage, init_d, {SYMBOL: (19_800.0, 19_800.0)})
    daily_prices = {
        sessions[0]: {SYMBOL: (20_000.0, 20_000.0)},
        sessions[1]: {SYMBOL: (20_000.0, 21_000.0)},
        sessions[2]: {SYMBOL: (21_000.0, 22_000.0)},
        sessions[3]: {SYMBOL: (22_000.0, 30_000.0)},
        sessions[4]: {SYMBOL: (30_000.0, 31_000.0)},
        sessions[5]: {SYMBOL: (31_000.0, 32_000.0)},
    }
    for d, px_map in daily_prices.items():
        _seed_day_bars(storage, d, px_map)

    strat = EtfDepositStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=init_d) == 0
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=sessions[-1]) == 0

    expected_navs = [
        (date(2026, 12, 28), 100_047_903.72342323, 0.0, 100_047_903.72342323, 47_903.72342323, 0),
        (date(2026, 12, 29), 86_017_657.13016981, 14_700_000.0, 100_717_657.13016981, 15_973.00674658, 1),
        (date(2026, 12, 30), 86_031_390.15771493, 15_400_000.0, 101_431_390.15771493, 13_733.02754512, 1),
        (date(2026, 12, 31), 86_045_125.37778717, 21_000_000.0, 107_045_125.37778717, 13_735.22007223, 1),
        (date(2027, 1, 4), 92_074_299.59034902, 15_500_000.0, 107_574_299.59034902, 54_962.81256184, 1),
        (date(2027, 1, 5), 92_088_999.58259083, 16_000_000.0, 108_088_999.58259083, 14_699.99224181, 1),
    ]

    with storage.conn() as c:
        nav_rows = c.execute(
            "SELECT date, cash, market_value, nav, interest, n_positions "
            "FROM paper_daily_nav ORDER BY date"
        ).fetchall()
        state = c.execute(
            "SELECT strategy, capital, cash, realized_pnl, last_processed_date "
            "FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        orders = c.execute(
            "SELECT created_date, exec_date, side, qty, filled_qty, status "
            "FROM paper_daily_orders ORDER BY id"
        ).fetchall()
        lots = c.execute(
            "SELECT symbol, qty, cost_per_share, buy_date FROM paper_daily_lots"
        ).fetchall()
        lots_cost_sum = float(
            c.execute(
                "SELECT COALESCE(SUM(qty * cost_per_share), 0.0) FROM paper_daily_lots"
            ).fetchone()[0]
        )

    assert len(nav_rows) == 6
    for got, exp in zip(nav_rows, expected_navs, strict=True):
        assert got[0] == exp[0]
        assert float(got[1]) == pytest.approx(exp[1], abs=1e-4)
        assert float(got[2]) == pytest.approx(exp[2], abs=1e-4)
        assert float(got[3]) == pytest.approx(exp[3], abs=1e-4)
        assert float(got[4]) == pytest.approx(exp[4], abs=1e-4)
        assert got[5] == exp[5]

    assert state[0] == "etf_deposit"
    assert float(state[1]) == pytest.approx(CAPITAL)
    assert float(state[2]) == pytest.approx(92_088_999.58259083, abs=1e-4)
    assert float(state[3]) == pytest.approx(2_122_013.58259081, abs=1e-4)
    assert state[4] == date(2027, 1, 5)
    assert float(state[2]) + lots_cost_sum - float(state[1]) == pytest.approx(float(state[3]), abs=1e-4)

    assert orders == [
        (date(2026, 12, 28), date(2026, 12, 29), "BUY", 700, 700, "filled"),
        (date(2026, 12, 31), date(2027, 1, 4), "SELL", 200, 200, "filled"),
    ]
    assert len(lots) == 1
    assert lots[0][0] == SYMBOL
    assert lots[0][1] == 500
    assert float(lots[0][2]) == pytest.approx(20_010.0 * 1.0028, abs=1e-6)
    assert lots[0][3] == date(2026, 12, 29)
