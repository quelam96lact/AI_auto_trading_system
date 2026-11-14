"""Pure daily-candle paper engine accounting rules (Brief 233 §3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SETTLE_DAYS, SLIPPAGE_BPS

LOT = 100


@dataclass(slots=True)
class DailyBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Lot:
    symbol: str
    qty: int
    cost_per_share: float
    buy_date: date


@dataclass(frozen=True, slots=True)
class PendingOrder:
    id: int
    created_date: date
    symbol: str
    side: str
    qty: int


@dataclass(frozen=True, slots=True)
class OrderOutcome:
    order_id: int
    status: str
    filled_qty: int
    price: float | None
    fee: float | None
    tax: float | None
    reason: str | None


@dataclass(slots=True)
class DayResult:
    cash: float
    realized_pnl: float
    lots: list[Lot]
    outcomes: list[OrderOutcome]
    market_value: float
    nav: float


__all__ = [
    "FEE_RATE",
    "LOT",
    "SELL_TAX_RATE",
    "SETTLE_DAYS",
    "SLIPPAGE_BPS",
    "DailyBar",
    "DayResult",
    "Lot",
    "OrderOutcome",
    "PendingOrder",
    "process_day",
]


def _rejected(order_id: int, reason: str) -> OrderOutcome:
    return OrderOutcome(
        order_id=order_id,
        status="rejected",
        filled_qty=0,
        price=None,
        fee=None,
        tax=None,
        reason=reason,
    )


def _expired(order_id: int, reason: str) -> OrderOutcome:
    return OrderOutcome(
        order_id=order_id,
        status="expired",
        filled_qty=0,
        price=None,
        fee=None,
        tax=None,
        reason=reason,
    )


def _execute_sell(
    order: PendingOrder,
    open_px: float,
    work_lots: list[Lot],
    session_index: dict[date, int],
    d_idx: int,
) -> tuple[OrderOutcome, float, float]:
    held_lots = [(idx, lot) for idx, lot in enumerate(work_lots) if lot.symbol == order.symbol and lot.qty > 0]
    if not held_lots:
        return _rejected(order.id, "not_held"), 0.0, 0.0

    settled_lots: list[tuple[int, Lot]] = []
    for idx, lot in held_lots:
        buy_idx = session_index.get(lot.buy_date)
        if buy_idx is None:
            raise ValueError(f"Lot buy_date {lot.buy_date} not present in sessions")
        if d_idx - buy_idx >= SETTLE_DAYS:
            settled_lots.append((idx, lot))

    settled_qty = sum(lot.qty for _, lot in settled_lots)
    if settled_qty == 0:
        return _rejected(order.id, "unsettled"), 0.0, 0.0

    settled_lots.sort(key=lambda item: (item[1].buy_date, item[0]))
    q = min(order.qty, settled_qty)
    px = open_px * (1.0 - SLIPPAGE_BPS / 10_000.0)
    val = q * px
    fee = val * FEE_RATE
    tax = val * SELL_TAX_RATE
    net_proceeds = val - fee - tax

    remaining_to_deduct = q
    cost_basis = 0.0
    for _, lot in settled_lots:
        if remaining_to_deduct == 0:
            break
        take = min(remaining_to_deduct, lot.qty)
        lot.qty -= take
        cost_basis += take * lot.cost_per_share
        remaining_to_deduct -= take

    pnl_delta = net_proceeds - cost_basis
    reason = "partial" if q < order.qty else None
    outcome = OrderOutcome(
        order_id=order.id,
        status="filled",
        filled_qty=q,
        price=px,
        fee=fee,
        tax=tax,
        reason=reason,
    )
    return outcome, net_proceeds, pnl_delta


def _execute_buy(
    order: PendingOrder,
    open_px: float,
    cash: float,
    d: date,
    work_lots: list[Lot],
) -> tuple[OrderOutcome, float]:
    px = open_px * (1.0 + SLIPPAGE_BPS / 10_000.0)
    unit_cost = px * (1.0 + FEE_RATE)
    if unit_cost <= 0 or cash <= 0:
        return _rejected(order.id, "cash"), cash

    afford = math.floor(cash / unit_cost / LOT) * LOT
    while afford >= LOT:
        candidate_val = afford * px
        candidate_total = candidate_val + candidate_val * FEE_RATE
        if candidate_total <= cash + 1e-9:
            break
        afford -= LOT

    q = min(order.qty, afford)
    if q <= 0:
        return _rejected(order.id, "cash"), cash

    val = q * px
    fee = val * FEE_RATE
    new_cash = cash - val - fee
    if -1e-9 < new_cash < 0.0:
        new_cash = 0.0
    elif new_cash < 0.0:
        raise ValueError(f"Buy calculation produced negative cash: {new_cash}")

    work_lots.append(
        Lot(
            symbol=order.symbol,
            qty=q,
            cost_per_share=px * (1.0 + FEE_RATE),
            buy_date=d,
        )
    )
    reason = "partial" if q < order.qty else None
    outcome = OrderOutcome(
        order_id=order.id,
        status="filled",
        filled_qty=q,
        price=px,
        fee=fee,
        tax=0.0,
        reason=reason,
    )
    return outcome, new_cash


def _mark_to_market(
    lots: list[Lot],
    bars_on_d: dict[str, DailyBar],
    last_close: dict[str, float],
    d: date,
) -> float:
    market_value = 0.0
    for lot in lots:
        bar = bars_on_d.get(lot.symbol)
        if bar is not None and bar.close > 0:
            price = bar.close
        else:
            fallback = last_close.get(lot.symbol)
            if fallback is None or fallback <= 0:
                raise ValueError(f"Missing close price for held symbol {lot.symbol!r} on {d}")
            price = fallback
        market_value += lot.qty * price
    return market_value


def process_day(
    cash: float,
    realized_pnl: float,
    lots: list[Lot],
    pending: list[PendingOrder],
    bars_on_d: dict[str, DailyBar],
    last_close: dict[str, float],
    d: date,
    sessions: list[date],
) -> DayResult:
    """Process all pending orders and mark portfolio NAV at close of trading day `d`."""
    session_index = {session_date: idx for idx, session_date in enumerate(sessions)}
    d_idx = session_index.get(d)
    if d_idx is None:
        raise ValueError(f"Session date {d} not present in sessions")

    work_lots = [
        Lot(
            symbol=lot.symbol,
            qty=lot.qty,
            cost_per_share=lot.cost_per_share,
            buy_date=lot.buy_date,
        )
        for lot in lots
    ]
    work_cash = float(cash)
    work_pnl = float(realized_pnl)

    for order in pending:
        if order.side not in ("BUY", "SELL"):
            raise ValueError(f"Unsupported order side {order.side!r} on order {order.id}")
    ordered_pending = sorted(pending, key=lambda o: (0 if o.side == "SELL" else 1, o.id))

    outcomes: list[OrderOutcome] = []
    for order in ordered_pending:
        if order.qty <= 0 or order.qty % LOT != 0:
            outcomes.append(_rejected(order.id, "bad_qty"))
            continue

        bar = bars_on_d.get(order.symbol)
        if bar is None or bar.open <= 0:
            outcomes.append(_expired(order.id, "no_bar"))
            continue

        if order.side == "SELL":
            outcome, cash_delta, pnl_delta = _execute_sell(order, bar.open, work_lots, session_index, d_idx)
            work_cash += cash_delta
            work_pnl += pnl_delta
            outcomes.append(outcome)
        else:
            outcome, work_cash = _execute_buy(order, bar.open, work_cash, d, work_lots)
            outcomes.append(outcome)

    remaining_lots = [lot for lot in work_lots if lot.qty > 0]
    market_value = _mark_to_market(remaining_lots, bars_on_d, last_close, d)
    nav = work_cash + market_value
    return DayResult(
        cash=work_cash,
        realized_pnl=work_pnl,
        lots=remaining_lots,
        outcomes=outcomes,
        market_value=market_value,
        nav=nav,
    )
