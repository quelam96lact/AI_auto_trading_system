from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.engine.logic import bar_from_payload, process_bar
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Signal
from trading.strategies.sma_cross import SmaCrossStrategy


def bar_at(i, close, sym="VCB"):
    return Bar(
        sym,
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
        close,
        close,
        close,
        close,
        100,
    )


def test_process_bar_submits_and_next_bar_fills():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, qty=100)
    risk = RiskManager(capital=100_000_000)
    marks: dict[str, float] = {}

    prices = [10, 10, 10, 10, 20, 20]
    all_fills = []
    for i, p in enumerate(prices):
        all_fills.extend(process_bar(bar_at(i, p), broker, strategy, risk, marks))

    assert any(f.side == "BUY" for f in all_fills)


def test_bar_from_payload_roundtrip():
    payload = {
        "symbol": "VCB",
        "ts": "2026-07-15T09:00:00+07:00",
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1000,
        "source": "ssi",
    }
    bar = bar_from_payload(payload)
    assert bar.symbol == "VCB" and bar.close == 10.5 and bar.ts.tzinfo is not None


def test_process_bar_calls_on_signal_when_signal_fires():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, qty=100)
    risk = RiskManager(capital=100_000_000)
    marks: dict[str, float] = {}
    calls = []

    def on_signal(signal: Signal, bar: Bar) -> None:
        calls.append((signal, bar))

    prices = [10, 10, 10, 10, 20, 20]
    bars = [bar_at(i, p) for i, p in enumerate(prices)]
    for b in bars:
        process_bar(b, broker, strategy, risk, marks, on_signal=on_signal)

    assert len(calls) == 1
    assert calls[0][0].symbol == "VCB"
    assert calls[0][0].side == "BUY"
    assert calls[0][0].qty == 100
    assert calls[0][1].close == 20


def test_process_bar_does_not_call_on_signal_when_no_signal():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, qty=100)
    risk = RiskManager(capital=100_000_000)
    marks: dict[str, float] = {}
    calls = []

    def on_signal(signal: Signal, bar: Bar) -> None:
        calls.append((signal, bar))

    prices = [10, 10, 10]
    bars = [bar_at(i, p) for i, p in enumerate(prices)]
    for b in bars:
        process_bar(b, broker, strategy, risk, marks, on_signal=on_signal)

    assert len(calls) == 0
