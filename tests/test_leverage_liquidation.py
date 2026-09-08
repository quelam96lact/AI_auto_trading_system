from datetime import UTC, datetime

from trading.backtest import run_backtest
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategy import Signal, Strategy
from trading.trailing_stop import TrailingStopManager


class SimpleAlwaysBuyOnceStrategy(Strategy):
    """Chiến lược mua 1 lần ở bar đầu tiên để test thanh lý."""

    def __init__(self):
        self.bought = False

    def on_bar(self, bar: Bar, broker) -> Signal | None:
        if not self.bought:
            self.bought = True
            return Signal(bar.symbol, "BUY", 1.0)
        return None

    def last_atr(self, symbol: str) -> float | None:
        return 1.0


def _make_bar(ts_sec: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(
        symbol="BTC-USDT",
        ts=datetime.fromtimestamp(ts_sec, tz=UTC),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        source="bingx",
    )


def test_liquidation_triggers_at_correct_threshold():
    """Task 2.4 Test 1: LONG 30x, giá vào 100, ký quỹ duy trì 0,5% => giá thanh lý ≈ 96.68 (≈96.8).
    Nến có low = 96 phải kích thanh lý; nến có low = 97 thì không."""
    # Case A: low = 97 (chưa chạm liq_price ~96.68) -> không thanh lý
    bars_no_liq = [
        _make_bar(1000, 100.0, 101.0, 99.0, 100.0),  # bar 0: sinh tín hiệu BUY
        _make_bar(1060, 100.0, 101.0, 99.0, 100.0),  # bar 1: khớp BUY tại open=100.0
        _make_bar(1120, 100.0, 101.0, 97.0, 98.0),   # bar 2: low=97 > 96.68 -> NO liquidation
    ]
    strat_a = SimpleAlwaysBuyOnceStrategy()
    risk_a = RiskManager(capital=1000.0, lot_size=0.01)
    ts_a = TrailingStopManager(sl_multiplier=100.0)  # trailing stop xa để không cắt nhầm
    rep_a = run_backtest(
        bars_no_liq,
        strat_a,
        risk_a,
        ts_a,
        capital=1000.0,
        fee_rate=0.0,
        sell_tax_rate=0.0,
        slippage_bps=0.0,
        settle_days=0,
        leverage=30.0,
        maintenance_margin_rate=0.005,
    )
    assert rep_a.liquidations == 0
    assert len([f for f in rep_a.fills if f.side == "SELL"]) == 0

    # Case B: low = 96 (chạm liq_price ~96.68) -> kích thanh lý
    bars_liq = [
        _make_bar(1000, 100.0, 101.0, 99.0, 100.0),  # bar 0: sinh tín hiệu BUY
        _make_bar(1060, 100.0, 101.0, 99.0, 100.0),  # bar 1: khớp BUY tại open=100.0
        _make_bar(1120, 100.0, 101.0, 96.0, 98.0),   # bar 2: low=96 <= 96.68 -> LIQUIDATION
    ]
    strat_b = SimpleAlwaysBuyOnceStrategy()
    risk_b = RiskManager(capital=1000.0, lot_size=0.01)
    ts_b = TrailingStopManager(sl_multiplier=100.0)
    rep_b = run_backtest(
        bars_liq,
        strat_b,
        risk_b,
        ts_b,
        capital=1000.0,
        fee_rate=0.0,
        sell_tax_rate=0.0,
        slippage_bps=0.0,
        settle_days=0,
        leverage=30.0,
        maintenance_margin_rate=0.005,
    )
    assert rep_b.liquidations == 1
    sell_fills = [f for f in rep_b.fills if f.side == "SELL"]
    assert len(sell_fills) == 1
    assert sell_fills[0].price < 97.0


def test_liquidation_catches_intrabar_low_missed_by_close():
    """Task 2.4 Test 2: Nến open=100, low=96, close=101 PHẢI kích thanh lý cho LONG 30x.
    Test này chống việc kiểm tra thanh lý chỉ bằng close."""
    bars = [
        _make_bar(1000, 100.0, 101.0, 99.0, 100.0),  # bar 0: sinh tín hiệu BUY
        _make_bar(1060, 100.0, 101.0, 99.0, 100.0),  # bar 1: khớp BUY
        _make_bar(1120, 100.0, 102.0, 96.0, 101.0),  # bar 2: low=96 nhưng close=101
    ]
    strat = SimpleAlwaysBuyOnceStrategy()
    risk = RiskManager(capital=1000.0, lot_size=0.01)
    ts = TrailingStopManager(sl_multiplier=100.0)
    rep = run_backtest(
        bars,
        strat,
        risk,
        ts,
        capital=1000.0,
        fee_rate=0.0,
        sell_tax_rate=0.0,
        slippage_bps=0.0,
        settle_days=0,
        leverage=30.0,
        maintenance_margin_rate=0.005,
    )
    assert rep.liquidations == 1
    sell_fills = [f for f in rep.fills if f.side == "SELL"]
    assert len(sell_fills) == 1


def test_no_liquidation_at_1x_leverage():
    """Task 2.4 Test 3: Cùng chuỗi giá, đòn bẩy 1x => 0 sự kiện thanh lý, PnL khớp kết quả không đòn bẩy."""
    bars = [
        _make_bar(1000, 100.0, 101.0, 99.0, 100.0),
        _make_bar(1060, 100.0, 101.0, 99.0, 100.0),
        _make_bar(1120, 100.0, 102.0, 96.0, 101.0),
    ]
    # Chạy 1x với leverage=1.0 tường minh
    strat_1x = SimpleAlwaysBuyOnceStrategy()
    risk_1x = RiskManager(capital=1000.0, lot_size=0.01)
    ts_1x = TrailingStopManager(sl_multiplier=100.0)
    rep_1x = run_backtest(
        bars,
        strat_1x,
        risk_1x,
        ts_1x,
        capital=1000.0,
        fee_rate=0.0,
        sell_tax_rate=0.0,
        slippage_bps=0.0,
        settle_days=0,
        leverage=1.0,
    )
    assert rep_1x.liquidations == 0

    # Chạy mặc định (không truyền leverage)
    strat_def = SimpleAlwaysBuyOnceStrategy()
    risk_def = RiskManager(capital=1000.0, lot_size=0.01)
    ts_def = TrailingStopManager(sl_multiplier=100.0)
    rep_def = run_backtest(
        bars,
        strat_def,
        risk_def,
        ts_def,
        capital=1000.0,
        fee_rate=0.0,
        sell_tax_rate=0.0,
        slippage_bps=0.0,
        settle_days=0,
    )
    assert rep_def.liquidations == 0
    assert rep_1x.realized_pnl == rep_def.realized_pnl
    assert rep_1x.unrealized_pnl == rep_def.unrealized_pnl
