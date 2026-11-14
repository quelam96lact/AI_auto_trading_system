"""Unit tests & mutation checks (a-j) for trading.daily_engine.core & strategy (Brief 233 §3, §4, §6)."""

from __future__ import annotations

from datetime import date

import pytest

from trading.daily_engine.core import (
    FEE_RATE,
    LOT,
    SELL_TAX_RATE,
    SETTLE_DAYS,
    SLIPPAGE_BPS,
    DailyBar,
    Lot,
    PendingOrder,
    process_day,
)
from trading.daily_engine.strategy import (
    STRATEGIES,
    DailyContext,
    NullDailyStrategy,
    UnknownStrategyError,
    resolve_strategy,
)


def _sessions_jan() -> list[date]:
    return [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
    ]


def test_constants_imported_from_paper_broker() -> None:
    assert LOT == 100
    assert FEE_RATE == pytest.approx(0.0028)
    assert SELL_TAX_RATE == pytest.approx(0.001)
    assert SLIPPAGE_BPS == 5
    assert SETTLE_DAYS == 3


def test_mutation_a_cannot_sell_lot_at_settle_days_minus_1() -> None:
    """Phép phá (a): Lô mới nắm giữ SETTLE_DAYS - 1 phiên bị từ chối unsettled; đủ SETTLE_DAYS mới bán được."""
    s = _sessions_jan()
    lot_day0 = Lot(symbol="AAA", qty=100, cost_per_share=20_000.0, buy_date=s[0])
    d_early = s[SETTLE_DAYS - 1]
    sell_early = PendingOrder(id=1, created_date=s[1], symbol="AAA", side="SELL", qty=100)
    bar_early = {"AAA": DailyBar("AAA", d_early, 25_000.0, 25_500.0, 24_800.0, 25_000.0, 10_000)}

    res_early = process_day(
        cash=0.0,
        realized_pnl=0.0,
        lots=[lot_day0],
        pending=[sell_early],
        bars_on_d=bar_early,
        last_close={},
        d=d_early,
        sessions=s,
    )
    assert len(res_early.outcomes) == 1
    assert res_early.outcomes[0].status == "rejected"
    assert res_early.outcomes[0].reason == "unsettled"
    assert res_early.outcomes[0].filled_qty == 0
    assert len(res_early.lots) == 1 and res_early.lots[0].qty == 100

    # At exact SETTLE_DAYS: allowed to fill
    d_ready = s[SETTLE_DAYS]
    bar_ready = {"AAA": DailyBar("AAA", d_ready, 25_000.0, 25_500.0, 24_800.0, 25_000.0, 10_000)}
    res_ready = process_day(
        cash=0.0,
        realized_pnl=0.0,
        lots=[lot_day0],
        pending=[PendingOrder(id=2, created_date=s[2], symbol="AAA", side="SELL", qty=100)],
        bars_on_d=bar_ready,
        last_close={},
        d=d_ready,
        sessions=s,
    )
    assert res_ready.outcomes[0].status == "filled"
    assert res_ready.outcomes[0].filled_qty == 100
    assert res_ready.lots == []


def test_mutation_b_buy_fee_hand_calculated() -> None:
    """Phép phá (b): Phí mua FEE_RATE=0.0028 được tính đúng và trừ khỏi cash + cộng vào cost_per_share (số tính tay)."""
    s = _sessions_jan()
    d = s[1]
    buy = PendingOrder(id=1, created_date=s[0], symbol="AAA", side="BUY", qty=100)
    bars = {"AAA": DailyBar("AAA", d, 20_000.0, 21_000.0, 19_900.0, 20_500.0, 50_000)}

    # Hand calc:
    # px = 20_000 * (1 + 5/10_000) = 20_010.0
    # val = 100 * 20_010.0 = 2_001_000.0
    # fee = 2_001_000.0 * 0.0028 = 5_602.8
    # cash = 10_000_000.0 - 2_006_602.8 = 7_993_397.2
    # cost_per_share = 20_010.0 * 1.0028 = 20_066.028
    # mv = 100 * 20_500.0 = 2_050_000.0 -> nav = 10_043_397.2
    res = process_day(
        cash=10_000_000.0,
        realized_pnl=0.0,
        lots=[],
        pending=[buy],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    out = res.outcomes[0]
    assert out.status == "filled"
    assert out.filled_qty == 100
    assert out.price == pytest.approx(20_010.0)
    assert out.fee == pytest.approx(5_602.8)
    assert res.cash == pytest.approx(7_993_397.2)
    assert len(res.lots) == 1
    assert res.lots[0].cost_per_share == pytest.approx(20_066.028)
    assert res.market_value == pytest.approx(2_050_000.0)
    assert res.nav == pytest.approx(10_043_397.2)


def test_mutation_c_sell_tax_hand_calculated() -> None:
    """Phép phá (c): Thuế bán SELL_TAX_RATE=0.001 được trừ khỏi cash và realized_pnl (số tính tay)."""
    s = _sessions_jan()
    d = s[3]
    lot = Lot(symbol="AAA", qty=100, cost_per_share=20_000.0, buy_date=s[0])
    sell = PendingOrder(id=1, created_date=s[2], symbol="AAA", side="SELL", qty=100)
    bars = {"AAA": DailyBar("AAA", d, 25_000.0, 25_500.0, 24_500.0, 25_200.0, 40_000)}

    # Hand calc:
    # px = 25_000 * (1 - 0.0005) = 24_987.5
    # val = 100 * 24_987.5 = 2_498_750.0
    # fee = 2_498_750.0 * 0.0028 = 6_996.5
    # tax = 2_498_750.0 * 0.001 = 2_498.75
    # net_proceeds = 2_498_750.0 - 6_996.5 - 2_498.75 = 2_489_254.75
    # realized_pnl = 2_489_254.75 - 100 * 20_000.0 = 489_254.75
    res = process_day(
        cash=0.0,
        realized_pnl=0.0,
        lots=[lot],
        pending=[sell],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    out = res.outcomes[0]
    assert out.status == "filled"
    assert out.price == pytest.approx(24_987.5)
    assert out.fee == pytest.approx(6_996.5)
    assert out.tax == pytest.approx(2_498.75)
    assert res.cash == pytest.approx(2_489_254.75)
    assert res.realized_pnl == pytest.approx(489_254.75)
    assert res.market_value == pytest.approx(0.0)
    assert res.nav == pytest.approx(2_489_254.75)


def test_mutation_d_slippage_direction_hand_calculated() -> None:
    """Phép phá (d): Trượt giá SLIPPAGE_BPS=5 luôn bất lợi: BUY = open*(1+s), SELL = open*(1-s)."""
    s = _sessions_jan()
    d = s[3]
    lot = Lot(symbol="BBB", qty=100, cost_per_share=20_000.0, buy_date=s[0])
    sell = PendingOrder(id=1, created_date=s[2], symbol="BBB", side="SELL", qty=100)
    buy = PendingOrder(id=2, created_date=s[2], symbol="AAA", side="BUY", qty=100)
    bars = {
        "AAA": DailyBar("AAA", d, 20_000.0, 20_500.0, 19_800.0, 20_000.0, 20_000),
        "BBB": DailyBar("BBB", d, 25_000.0, 25_200.0, 24_700.0, 25_000.0, 20_000),
    }

    res = process_day(
        cash=5_000_000.0,
        realized_pnl=0.0,
        lots=[lot],
        pending=[sell, buy],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    by_id = {o.order_id: o for o in res.outcomes}
    # SELL unfavorable (lower than open)
    assert by_id[1].price == pytest.approx(24_987.5)
    assert by_id[1].price < 25_000.0
    # BUY unfavorable (higher than open)
    assert by_id[2].price == pytest.approx(20_010.0)
    assert by_id[2].price > 20_000.0
    # cash = 5_000_000 + 2_489_254.75 - 2_006_602.8 = 5_482_651.95
    assert res.cash == pytest.approx(5_482_651.95)


def test_mutation_e_buy_lot_rounding_and_non_negative_cash() -> None:
    """Phép phá (e): Mua làm tròn xuống bội LOT=100, ghi nhận partial hoặc reject 'cash', không bao giờ âm cash."""
    s = _sessions_jan()
    d = s[1]
    bars = {
        "AAA": DailyBar("AAA", d, 20_000.0, 20_500.0, 19_800.0, 20_000.0, 10_000),
        "BBB": DailyBar("BBB", d, 20_000.0, 20_500.0, 19_800.0, 20_000.0, 10_000),
    }
    # 100 AAA costs 2_006_602.8; 200 costs 4_013_205.6.
    # With cash=3_900_000: afford = 100 (cannot buy 194, cannot buy 200 -> cash >= 0).
    buy_partial = PendingOrder(id=1, created_date=s[0], symbol="AAA", side="BUY", qty=300)
    res1 = process_day(
        cash=3_900_000.0,
        realized_pnl=0.0,
        lots=[],
        pending=[buy_partial],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    assert res1.outcomes[0].status == "filled"
    assert res1.outcomes[0].filled_qty == 100
    assert res1.outcomes[0].filled_qty % LOT == 0
    assert res1.outcomes[0].reason == "partial"
    assert res1.cash == pytest.approx(3_900_000.0 - 2_006_602.8)
    assert res1.cash >= 0.0

    # With cash=1_500_000: afford = 0 -> rejected 'cash', cash untouched
    buy_insufficient = PendingOrder(id=2, created_date=s[0], symbol="BBB", side="BUY", qty=100)
    res2 = process_day(
        cash=1_500_000.0,
        realized_pnl=0.0,
        lots=[],
        pending=[buy_insufficient],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    assert res2.outcomes[0].status == "rejected"
    assert res2.outcomes[0].reason == "cash"
    assert res2.outcomes[0].filled_qty == 0
    assert res2.cash == pytest.approx(1_500_000.0)


def test_mutation_f_order_without_bar_on_d_expires() -> None:
    """Phép phá (f): Mã không có nến ngày d hoặc open <= 0 -> expired ('no_bar'), không khớp."""
    s = _sessions_jan()
    d = s[3]
    lot = Lot(symbol="MISSING", qty=100, cost_per_share=10_000.0, buy_date=s[0])
    orders = [
        PendingOrder(id=1, created_date=s[2], symbol="MISSING", side="SELL", qty=100),
        PendingOrder(id=2, created_date=s[2], symbol="ZEROOPEN", side="BUY", qty=100),
    ]
    bars = {
        "ZEROOPEN": DailyBar("ZEROOPEN", d, 0.0, 10_000.0, 9_500.0, 9_800.0, 1_000),
    }

    res = process_day(
        cash=10_000_000.0,
        realized_pnl=0.0,
        lots=[lot],
        pending=orders,
        bars_on_d=bars,
        last_close={"MISSING": 11_000.0},
        d=d,
        sessions=s,
    )
    by_id = {o.order_id: o for o in res.outcomes}
    assert by_id[1].status == "expired" and by_id[1].reason == "no_bar"
    assert by_id[1].filled_qty == 0
    assert by_id[2].status == "expired" and by_id[2].reason == "no_bar"
    assert by_id[2].filled_qty == 0
    assert res.cash == pytest.approx(10_000_000.0)
    assert len(res.lots) == 1 and res.lots[0].symbol == "MISSING"


def test_mutation_g_nav_uses_close_and_last_close_not_cost() -> None:
    """Phép phá (g): NAV định giá bằng bars_on_d.close (>0), fallback last_close, không dùng giá vốn; thiếu giá -> ValueError."""
    s = _sessions_jan()
    d = s[2]
    lots = [
        Lot(symbol="AAA", qty=100, cost_per_share=10_000.0, buy_date=s[0]),
        Lot(symbol="BBB", qty=200, cost_per_share=15_000.0, buy_date=s[0]),
    ]
    bars = {
        "AAA": DailyBar("AAA", d, 12_000.0, 12_500.0, 11_800.0, 12_300.0, 5_000),
    }
    res = process_day(
        cash=1_000_000.0,
        realized_pnl=0.0,
        lots=lots,
        pending=[],
        bars_on_d=bars,
        last_close={"BBB": 16_000.0},
        d=d,
        sessions=s,
    )
    # AAA uses bars_on_d close (12_300), BBB falls back to last_close (16_000) -> 1_230_000 + 3_200_000 = 4_430_000
    assert res.market_value == pytest.approx(4_430_000.0)
    assert res.nav == pytest.approx(5_430_000.0)

    # Missing both bars_on_d.close > 0 and last_close > 0 must raise ValueError
    with pytest.raises(ValueError):
        process_day(
            cash=1_000_000.0,
            realized_pnl=0.0,
            lots=[Lot(symbol="ZZZ", qty=100, cost_per_share=10_000.0, buy_date=s[0])],
            pending=[],
            bars_on_d={},
            last_close={},
            d=d,
            sessions=s,
        )


def test_mutation_h_sells_before_buys_same_day() -> None:
    """Phép phá (h): Bán trước mua sau dù BUY có id nhỏ hơn; trong cùng nhóm chạy theo id tăng dần."""
    s = _sessions_jan()
    d = s[3]
    lot_aaa = Lot(symbol="AAA", qty=100, cost_per_share=20_000.0, buy_date=s[0])
    # Buy orders have lower ids (1, 2) than Sell order (3), yet Sell proceeds fund Buy id=1, and id=2 gets cash rejection.
    orders = [
        PendingOrder(id=2, created_date=s[2], symbol="CCC", side="BUY", qty=100),
        PendingOrder(id=1, created_date=s[2], symbol="BBB", side="BUY", qty=100),
        PendingOrder(id=3, created_date=s[2], symbol="AAA", side="SELL", qty=100),
    ]
    bars = {
        "AAA": DailyBar("AAA", d, 25_000.0, 25_500.0, 24_500.0, 25_000.0, 10_000),
        "BBB": DailyBar("BBB", d, 20_000.0, 20_500.0, 19_500.0, 20_000.0, 10_000),
        "CCC": DailyBar("CCC", d, 20_000.0, 20_500.0, 19_500.0, 20_000.0, 10_000),
    }

    res = process_day(
        cash=0.0,
        realized_pnl=0.0,
        lots=[lot_aaa],
        pending=orders,
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    by_id = {o.order_id: o for o in res.outcomes}
    assert by_id[3].status == "filled"
    assert by_id[1].status == "filled"  # funded by SELL id=3!
    assert by_id[2].status == "rejected" and by_id[2].reason == "cash"
    # Sell proceeds 2_489_254.75 - Buy cost 2_006_602.8 = 482_651.95
    assert res.cash == pytest.approx(482_651.95)


def test_mutation_i_fifo_deducts_oldest_settled_lot_first() -> None:
    """Phép phá (i): Trừ lô FIFO (buy_date cũ trước, cùng ngày theo thứ tự trong danh sách), chỉ trong lô đã settle."""
    s = _sessions_jan()
    d = s[4]  # s[0] settled (4>=3), s[1] settled (3>=3), s[2] unsettled (2<3)
    lots = [
        Lot(symbol="AAA", qty=100, cost_per_share=30_000.0, buy_date=s[1]),  # newer buy_date
        Lot(symbol="AAA", qty=100, cost_per_share=10_000.0, buy_date=s[0]),  # oldest #1 -> must go FIRST
        Lot(symbol="AAA", qty=100, cost_per_share=20_000.0, buy_date=s[0]),  # oldest #2 -> must go SECOND if needed
        Lot(symbol="AAA", qty=100, cost_per_share=99_000.0, buy_date=s[2]),  # unsettled
    ]
    sell = PendingOrder(id=1, created_date=s[3], symbol="AAA", side="SELL", qty=100)
    bars = {"AAA": DailyBar("AAA", d, 25_000.0, 25_500.0, 24_500.0, 25_000.0, 10_000)}

    res = process_day(
        cash=0.0,
        realized_pnl=0.0,
        lots=lots,
        pending=[sell],
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    # Proceeds = 2_489_254.75; deducted oldest s[0] #1 lot cost=1_000_000 -> realized_pnl = 1_489_254.75
    assert res.realized_pnl == pytest.approx(1_489_254.75)
    remaining_costs = [(l.buy_date, l.cost_per_share, l.qty) for l in res.lots]
    assert remaining_costs == [
        (s[1], 30_000.0, 100),
        (s[0], 20_000.0, 100),
        (s[2], 99_000.0, 100),
    ]


def test_mutation_j_all_pending_orders_resolved_in_single_session() -> None:
    """Phép phá (j): Mọi lệnh pending đều được xử lý dứt điểm trong ngày (bad_qty, not_held, no_bar, filled), không còn pending."""
    s = _sessions_jan()
    d = s[1]
    orders = [
        PendingOrder(id=1, created_date=s[0], symbol="AAA", side="BUY", qty=0),
        PendingOrder(id=2, created_date=s[0], symbol="AAA", side="BUY", qty=150),
        PendingOrder(id=3, created_date=s[0], symbol="AAA", side="SELL", qty=100),
        PendingOrder(id=4, created_date=s[0], symbol="NOBAR", side="BUY", qty=100),
    ]
    bars = {"AAA": DailyBar("AAA", d, 20_000.0, 20_200.0, 19_800.0, 20_000.0, 10_000)}

    res = process_day(
        cash=5_000_000.0,
        realized_pnl=0.0,
        lots=[],
        pending=orders,
        bars_on_d=bars,
        last_close={},
        d=d,
        sessions=s,
    )
    assert len(res.outcomes) == 4
    by_id = {o.order_id: o for o in res.outcomes}
    assert all(o.status in ("filled", "expired", "rejected") for o in res.outcomes)
    assert by_id[1].status == "rejected" and by_id[1].reason == "bad_qty"
    assert by_id[2].status == "rejected" and by_id[2].reason == "bad_qty"
    assert by_id[3].status == "rejected" and by_id[3].reason == "not_held"
    assert by_id[4].status == "expired" and by_id[4].reason == "no_bar"


def test_strategy_registry_and_null_daily_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "null" in STRATEGIES
    monkeypatch.delenv("DAILY_ENGINE_STRATEGY", raising=False)
    strat = resolve_strategy()
    assert isinstance(strat, NullDailyStrategy)
    assert strat.name == "null"

    monkeypatch.setenv("DAILY_ENGINE_STRATEGY", "  NuLl \n")
    assert resolve_strategy().name == "null"

    ctx = DailyContext(
        d=date(2026, 1, 5),
        universe=["AAA"],
        cash=100_000_000.0,
        nav=100_000_000.0,
        positions={},
        bars_loader=lambda sym, n: [DailyBar(sym, date(2026, 1, 5), 10.0, 10.0, 10.0, 10.0, 100)][:n],
    )
    assert strat.on_day(ctx) == []
    assert len(ctx.bars("AAA", 1)) == 1

    monkeypatch.setenv("DAILY_ENGINE_STRATEGY", "does_not_exist")
    with pytest.raises(UnknownStrategyError):
        resolve_strategy()
