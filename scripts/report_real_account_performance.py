"""Báo cáo hiệu suất tài khoản thật từ lịch sử lệnh SSI (Brief đợt 174).

Chỉ đọc, không ghi DB, không gọi lệnh ghi nào.
Tính toán chi phí giao dịch thật (phí, thuế) và lãi/lỗ từng vòng theo FIFO.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import io
import os
import statistics
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Console encoding UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ssi_sdk.models.portfolio import Order, OrderBookRequest, OrderSide
from ssi_sdk.services.portfolio import EP_ORDER_HISTORY, OrderBook

from scripts._db_common import load_dotenv, resolve_dsn
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import load_config
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE
from trading.storage.db import Storage

# SSI SDK bug workaround: SSI API /api/v3/trading/orderBook trả về "filledQty" và "cancelQty",
# nhưng Order.from_dict chỉ đọc "filledQuantity" và "cancelQuantity".
_orig_order_from_dict = Order.from_dict


def _compat_order_from_dict(cls: Any, data: dict, account_no: str = "") -> Order:
    d = dict(data)
    if "filledQuantity" not in d and "filledQty" in d:
        d["filledQuantity"] = d["filledQty"]
    if "cancelQuantity" not in d and "cancelQty" in d:
        d["cancelQuantity"] = d["cancelQty"]
    return _orig_order_from_dict(d, account_no)


Order.from_dict = classmethod(_compat_order_from_dict)


@dataclass
class RoundTripTrade:
    symbol: str
    qty: int
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    holding_days: int
    buy_value: float
    buy_fee: float
    sell_value: float
    sell_fee: float
    sell_tax: float
    gross_pnl: float
    net_pnl: float
    return_pct: float


@dataclass
class OpenPosition:
    symbol: str
    qty: int
    entry_time: str
    entry_price: float
    buy_value: float
    buy_fee: float


@dataclass
class UnmatchedSell:
    symbol: str
    qty: int
    exit_time: str
    exit_price: float
    sell_value: float
    sell_fee: float
    sell_tax: float


@dataclass
class MonthlyStat:
    month: str
    rounds_count: int
    buy_value: float
    sell_value: float
    fee_tax: float
    gross_pnl: float
    net_pnl: float
    cost_to_gross_pct: float | None


@dataclass
class PerformanceReport:
    account_no: str
    from_date: str
    to_date: str
    total_orders: int
    filled_orders_count: int
    total_buy_value: float
    total_sell_value: float
    total_buy_fee: float
    total_sell_fee: float
    total_sell_tax: float
    total_fee_tax: float
    round_trips: list[RoundTripTrade]
    open_positions: list[OpenPosition]
    unmatched_sells: list[UnmatchedSell]
    win_rounds_count: int
    win_rate: float
    total_gross_pnl: float
    total_net_pnl: float
    avg_net_pnl_per_round: float
    median_holding_days: float
    cost_to_gross_pct: float | None
    monthly_stats: list[MonthlyStat]


def parse_order_time(time_str: str) -> datetime:
    """Parse chuỗi thời gian SSI thành datetime."""
    s = time_str.strip().replace("-", "/")
    parts = s.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else "00:00:00"
    dt_str = f"{date_part} {time_part}"
    try:
        return datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return datetime.fromisoformat(time_str)


def compute_holding_days(entry_time_str: str, exit_time_str: str) -> int:
    """Tính số ngày giữ giữa thời gian vào và thời gian ra."""
    dt_entry = parse_order_time(entry_time_str)
    dt_exit = parse_order_time(exit_time_str)
    return max(0, (dt_exit.date() - dt_entry.date()).days)


def _is_buy(order: Order) -> bool:
    side = getattr(order, "side", None)
    if isinstance(side, OrderSide):
        return side == OrderSide.BUY
    side_str = str(side or "").upper()
    return side_str in ("B", "BUY")


def match_fifo_orders(
    orders: list[Order],
    mode: str = "FIFO",
    fee_rate: float = FEE_RATE,
    sell_tax_rate: float = SELL_TAX_RATE,
) -> tuple[list[RoundTripTrade], list[OpenPosition], list[UnmatchedSell]]:
    """Ghép các lệnh khớp thành các vòng mua-bán theo FIFO (hoặc LIFO).

    - Chỉ dùng lệnh có filled_quantity > 0.
    - Sắp xếp tăng dần theo input_time.
    """
    valid_orders = [o for o in orders if getattr(o, "filled_quantity", 0) > 0]
    valid_orders.sort(key=lambda o: parse_order_time(o.input_time))

    # Symbol -> deque of lots: dict(qty, price, input_time, order_id)
    buy_queues: dict[str, deque[dict]] = defaultdict(deque)
    round_trips: list[RoundTripTrade] = []
    unmatched_sells: list[UnmatchedSell] = []

    for o in valid_orders:
        sym = o.symbol.upper()
        filled_qty = int(o.filled_quantity)
        avg_price = float(o.avg_price)
        t_str = o.input_time

        if _is_buy(o):
            buy_queues[sym].append(
                {
                    "qty": filled_qty,
                    "price": avg_price,
                    "input_time": t_str,
                    "order_id": str(getattr(o, "order_id", "")),
                }
            )
        else:
            # Lệnh BÁN
            remaining_sell = filled_qty
            queue = buy_queues[sym]

            while remaining_sell > 0 and queue:
                # FIFO lấy lot đầu; LIFO lấy lot cuối
                lot = queue[0] if mode == "FIFO" else queue[-1]
                matched_qty = min(remaining_sell, lot["qty"])

                buy_val = matched_qty * lot["price"]
                buy_fee = buy_val * fee_rate
                total_cost = buy_val + buy_fee

                sell_val = matched_qty * avg_price
                sell_fee = sell_val * fee_rate
                sell_tax = sell_val * sell_tax_rate
                net_proceeds = sell_val - sell_fee - sell_tax

                gross_pnl = sell_val - buy_val
                net_pnl = net_proceeds - total_cost
                return_pct = (net_pnl / total_cost) if total_cost > 0 else 0.0

                h_days = compute_holding_days(lot["input_time"], t_str)

                rt = RoundTripTrade(
                    symbol=sym,
                    qty=matched_qty,
                    entry_time=lot["input_time"],
                    exit_time=t_str,
                    entry_price=lot["price"],
                    exit_price=avg_price,
                    holding_days=h_days,
                    buy_value=buy_val,
                    buy_fee=buy_fee,
                    sell_value=sell_val,
                    sell_fee=sell_fee,
                    sell_tax=sell_tax,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    return_pct=return_pct,
                )
                round_trips.append(rt)

                lot["qty"] -= matched_qty
                remaining_sell -= matched_qty
                if lot["qty"] == 0:
                    if mode == "FIFO":
                        queue.popleft()
                    else:
                        queue.pop()

            if remaining_sell > 0:
                # Bán không có giá vốn trong kỳ (mua trước kỳ --from)
                s_val = remaining_sell * avg_price
                s_fee = s_val * fee_rate
                s_tax = s_val * sell_tax_rate
                unmatched_sells.append(
                    UnmatchedSell(
                        symbol=sym,
                        qty=remaining_sell,
                        exit_time=t_str,
                        exit_price=avg_price,
                        sell_value=s_val,
                        sell_fee=s_fee,
                        sell_tax=s_tax,
                    )
                )

    # Vị thế còn mở cuối kỳ
    open_positions: list[OpenPosition] = []
    for sym, queue in buy_queues.items():
        for lot in queue:
            if lot["qty"] > 0:
                b_val = lot["qty"] * lot["price"]
                b_fee = b_val * fee_rate
                open_positions.append(
                    OpenPosition(
                        symbol=sym,
                        qty=lot["qty"],
                        entry_time=lot["input_time"],
                        entry_price=lot["price"],
                        buy_value=b_val,
                        buy_fee=b_fee,
                    )
                )

    return round_trips, open_positions, unmatched_sells


def build_performance_report(
    account_no: str,
    from_date: str,
    to_date: str,
    all_orders: list[Order],
    mode: str = "FIFO",
    fee_rate: float = FEE_RATE,
    sell_tax_rate: float = SELL_TAX_RATE,
) -> PerformanceReport:
    """Xây dựng báo cáo hiệu suất tài khoản đầy đủ."""
    filled_orders = [
        o for o in all_orders if getattr(o, "filled_quantity", 0) > 0
    ]

    tot_buy_val = 0.0
    tot_sell_val = 0.0
    tot_buy_fee = 0.0
    tot_sell_fee = 0.0
    tot_sell_tax = 0.0

    for o in filled_orders:
        val = int(o.filled_quantity) * float(o.avg_price)
        if _is_buy(o):
            tot_buy_val += val
            tot_buy_fee += val * fee_rate
        else:
            tot_sell_val += val
            tot_sell_fee += val * fee_rate
            tot_sell_tax += val * sell_tax_rate

    round_trips, open_pos, unmatch_sells = match_fifo_orders(
        orders=filled_orders,
        mode=mode,
        fee_rate=fee_rate,
        sell_tax_rate=sell_tax_rate,
    )

    n_rounds = len(round_trips)
    win_rounds = sum(1 for r in round_trips if r.net_pnl > 0)
    win_rate = (win_rounds / n_rounds) if n_rounds > 0 else 0.0

    tot_gross = sum(r.gross_pnl for r in round_trips)
    tot_net = sum(r.net_pnl for r in round_trips)
    avg_net = (tot_net / n_rounds) if n_rounds > 0 else 0.0

    h_days_list = [r.holding_days for r in round_trips]
    med_holding = statistics.median(h_days_list) if h_days_list else 0.0

    tot_fee_tax = tot_buy_fee + tot_sell_fee + tot_sell_tax
    cost_to_gross = (tot_fee_tax / tot_gross) if tot_gross > 0 else None

    # Bảng theo tháng
    monthly_data: dict[str, list[RoundTripTrade]] = defaultdict(list)
    for r in round_trips:
        m_key = r.exit_time.split(" ")[0][:7].replace("/", "-")
        monthly_data[m_key].append(r)

    monthly_stats: list[MonthlyStat] = []
    for m_key in sorted(monthly_data.keys()):
        m_rts = monthly_data[m_key]
        m_b_val = sum(r.buy_value for r in m_rts)
        m_s_val = sum(r.sell_value for r in m_rts)
        m_fee_tax = sum(
            r.buy_fee + r.sell_fee + r.sell_tax for r in m_rts
        )
        m_gross = sum(r.gross_pnl for r in m_rts)
        m_net = sum(r.net_pnl for r in m_rts)
        m_cost_ratio = (m_fee_tax / m_gross) if m_gross > 0 else None
        monthly_stats.append(
            MonthlyStat(
                month=m_key,
                rounds_count=len(m_rts),
                buy_value=m_b_val,
                sell_value=m_s_val,
                fee_tax=m_fee_tax,
                gross_pnl=m_gross,
                net_pnl=m_net,
                cost_to_gross_pct=m_cost_ratio,
            )
        )

    return PerformanceReport(
        account_no=account_no,
        from_date=from_date,
        to_date=to_date,
        total_orders=len(all_orders),
        filled_orders_count=len(filled_orders),
        total_buy_value=tot_buy_val,
        total_sell_value=tot_sell_val,
        total_buy_fee=tot_buy_fee,
        total_sell_fee=tot_sell_fee,
        total_sell_tax=tot_sell_tax,
        total_fee_tax=tot_fee_tax,
        round_trips=round_trips,
        open_positions=open_pos,
        unmatched_sells=unmatch_sells,
        win_rounds_count=win_rounds,
        win_rate=win_rate,
        total_gross_pnl=tot_gross,
        total_net_pnl=tot_net,
        avg_net_pnl_per_round=avg_net,
        median_holding_days=float(med_holding),
        cost_to_gross_pct=cost_to_gross,
        monthly_stats=monthly_stats,
    )


async def fetch_historical_orders_page(
    portfolio: Any,
    account_no: str,
    from_date: str,
    to_date: str,
    page: int = 1,
    size: int = 100,
) -> tuple[list[Order], int]:
    """Fetch 1 trang lịch sử lệnh từ portfolio service."""
    # 1. Hỗ trợ phương thức get_historical_orders_page nếu có
    if hasattr(portfolio, "get_historical_orders_page"):
        res = await portfolio.get_historical_orders_page(
            account_no, from_date, to_date, page=page, size=size
        )
        if isinstance(res, tuple):
            return res[0], res[1]
        return getattr(res, "orders", res), getattr(res, "total_orders", len(res))

    # 2. Hỗ trợ get_historical_orders có tham số page/size
    if hasattr(portfolio, "get_historical_orders"):
        sig = inspect.signature(portfolio.get_historical_orders)
        if "page" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        ):
            kwargs: dict[str, Any] = {"page": page}
            if "size" in sig.parameters:
                kwargs["size"] = size
            res = await portfolio.get_historical_orders(
                account_no, from_date, to_date, **kwargs
            )
            if isinstance(res, tuple):
                return res[0], res[1]
            if hasattr(res, "orders"):
                return res.orders, getattr(
                    res, "total_orders", len(res.orders)
                )
            total = getattr(res, "total_orders", None)
            if total is None:
                total = getattr(portfolio, "total_orders", None)
            return list(res), (total if total is not None else len(res))

    # 3. Hỗ trợ AsyncPortfolioService thực tế qua _rest
    if hasattr(portfolio, "_rest"):
        req = OrderBookRequest(
            account_no=account_no,
            from_date=from_date,
            to_date=to_date,
            page=page,
            size=size,
        ).to_dict()
        data = await portfolio._rest.get(EP_ORDER_HISTORY, params=req)
        book = OrderBook.from_dict(data)
        return book.orders, book.total_orders

    # 4. Fallback mặc định
    res = await portfolio.get_historical_orders(account_no, from_date, to_date)
    return res, len(res)


async def fetch_all_historical_orders(
    portfolio: Any,
    account_no: str,
    from_date: str,
    to_date: str,
    page_size: int = 100,
) -> tuple[list[Order], int]:
    """Lấy toàn bộ lịch sử lệnh qua tất cả các trang và kiểm tra total_orders."""
    page = 1
    all_orders: list[Order] = []
    total_expected: int | None = None

    while True:
        orders, total_orders = await fetch_historical_orders_page(
            portfolio, account_no, from_date, to_date, page=page, size=page_size
        )
        if total_expected is None:
            total_expected = total_orders

        all_orders.extend(orders)

        if len(all_orders) >= total_orders or not orders:
            break
        page += 1

    if total_expected is not None and len(all_orders) != total_expected:
        raise ValueError(
            f"Số lệnh lấy về ({len(all_orders)}) không khớp total_orders ({total_expected})"
        )

    return all_orders, (
        total_expected if total_expected is not None else len(all_orders)
    )


def print_performance_report(rep: PerformanceReport) -> None:
    """In báo cáo định dạng chuẩn ra màn hình."""
    print("=" * 88)
    print(
        f"  BÁO CÁO HIỆU SUẤT TÀI KHOẢN THẬT SSI: {rep.account_no} "
        f"({rep.from_date} -> {rep.to_date})"
    )
    print("=" * 88)

    print("\n(A) TỔNG QUAN GIÁ TRỊ VÀ CHI PHÍ GIAO DỊCH:")
    print(f"  - Tổng số lệnh nhận từ API : {rep.total_orders}")
    print(f"  - Số lệnh có khớp thực tế   : {rep.filled_orders_count}")
    print(f"  - Tổng giá trị MUA khớp     : {rep.total_buy_value:>16,.0f} VND")
    print(f"  - Tổng giá trị BÁN khớp    : {rep.total_sell_value:>16,.0f} VND")
    print(
        f"  - Tổng phí giao dịch (mua+bán): {rep.total_buy_fee + rep.total_sell_fee:>14,.0f} VND (FEE_RATE={FEE_RATE*100:.2f}%)"
    )
    print(
        f"  - Tổng thuế bán             : {rep.total_sell_tax:>16,.0f} VND (TAX_RATE={SELL_TAX_RATE*100:.2f}%)"
    )
    print(f"  - TỔNG CHI PHÍ (phí + thuế) : {rep.total_fee_tax:>16,.0f} VND")

    print("\n(B) KẾT QUẢ CÁC VÒNG MUA - BÁN (FIFO):")
    print(f"  - Số vòng hoàn thành (khép kín): {len(rep.round_trips)}")
    print(
        f"  - Số vòng có lãi ròng         : {rep.win_rounds_count} ({rep.win_rate * 100:.1f}%)"
    )
    print(f"  - Tổng lãi/lỗ GỘP             : {rep.total_gross_pnl:>16,.0f} VND")
    print(f"  - TỔNG LÃI/LỖ RÒNG (sau CP)   : {rep.total_net_pnl:>16,.0f} VND")
    print(f"  - Lãi/lỗ ròng trung bình/vòng : {rep.avg_net_pnl_per_round:>16,.0f} VND")
    print(f"  - Trung vị số ngày giữ        : {rep.median_holding_days:>16.1f} ngày")

    print("\n(C) TÁC ĐỘNG CỦA CHI PHÍ GIAO DỊCH:")
    if rep.cost_to_gross_pct is not None:
        pct_str = f"{rep.cost_to_gross_pct * 100:.2f}%"
        print(f"  - Chi phí / Lãi gộp           : {pct_str}")
        print(f"    (Chi phí ăn {pct_str} tổng lợi nhuận gộp sinh ra)")
    else:
        print(
            "  - Chi phí / Lãi gộp           : N/A (Tổng lãi gộp <= 0 hoặc âm)"
        )

    print("\n(D) BẢNG HIỆU SUẤT THEO THÁNG (theo ngày chốt vòng bán):")
    print("-" * 88)
    print(
        f"{'Tháng':<10} | {'Số vòng':<8} | {'Giá trị mua':<14} | {'Giá trị bán':<14} | "
        f"{'Phí + Thuế':<12} | {'Lãi/Lỗ ròng':<14} | {'CP/Lãi gộp':<10}"
    )
    print("-" * 88)
    for m in rep.monthly_stats:
        c_ratio = (
            f"{m.cost_to_gross_pct * 100:.1f}%"
            if m.cost_to_gross_pct is not None
            else "N/A"
        )
        print(
            f"{m.month:<10} | {m.rounds_count:<8} | {m.buy_value:>14,.0f} | "
            f"{m.sell_value:>14,.0f} | {m.fee_tax:>12,.0f} | "
            f"{m.net_pnl:>14,.0f} | {c_ratio:>10}"
        )
    print("-" * 88)

    if rep.open_positions:
        print(f"\n(E) VỊ THẾ CÒN MỞ CUỐI KỲ ({len(rep.open_positions)} lô):")
        print("-" * 72)
        print(
            f"{'Mã':<6} | {'KL mở':<8} | {'Giá mua':<10} | {'Giá trị mua (VND)':<18} | {'Ngày vào':<20}"
        )
        print("-" * 72)
        for p in rep.open_positions:
            print(
                f"{p.symbol:<6} | {p.qty:<8} | {p.entry_price:<10.1f} | "
                f"{p.buy_value:>18,.0f} | {p.entry_time:<20}"
            )
        print("-" * 72)

    if rep.unmatched_sells:
        print(
            f"\n(F) BÁN KHÔNG CÓ GIÁ VỐN TRONG KỲ ({len(rep.unmatched_sells)} lệnh/lô mua trước {rep.from_date}):"
        )
        print("-" * 72)
        print(
            f"{'Mã':<6} | {'KL bán':<8} | {'Giá bán':<10} | {'Giá trị bán (VND)':<18} | {'Ngày bán':<20}"
        )
        print("-" * 72)
        for u in rep.unmatched_sells:
            print(
                f"{u.symbol:<6} | {u.qty:<8} | {u.exit_price:<10.1f} | "
                f"{u.sell_value:>18,.0f} | {u.exit_time:<20}"
            )
        print("-" * 72)

    print("\n" + "=" * 88)


async def run_report(
    account_no: str,
    from_date_str: str,
    to_date_str: str | None = None,
) -> PerformanceReport:
    """Chạy báo cáo cho tài khoản thật từ SSI API."""
    cfg = load_config(os.path.join(str(_ROOT), "config", "config.yaml"))
    storage = Storage(resolve_dsn())

    auth = await ensure_authenticated(cfg, storage)
    try:
        from ssi_sdk.services.portfolio import AsyncPortfolioService

        client_id = decode_client_id(auth.token_manager.access_token)
        auth.config.client_id = client_id
        portfolio = AsyncPortfolioService(auth.rest_client, auth.config)

        # Chuyển đổi YYYY-MM-DD sang YYYY/MM/DD cho SSI
        api_from = from_date_str.replace("-", "/")
        if to_date_str:
            api_to = to_date_str.replace("-", "/")
        else:
            api_to = datetime.now(TZ).strftime("%Y/%m/%d")

        all_orders, _ = await fetch_all_historical_orders(
            portfolio, account_no, api_from, api_to, page_size=100
        )

        rep = build_performance_report(
            account_no=account_no,
            from_date=from_date_str,
            to_date=to_date_str or datetime.now(TZ).strftime("%Y-%m-%d"),
            all_orders=all_orders,
            mode="FIFO",
            fee_rate=FEE_RATE,
            sell_tax_rate=SELL_TAX_RATE,
        )
        return rep
    finally:
        await auth.close()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Báo cáo hiệu suất tài khoản thật SSI từ lịch sử lệnh"
    )
    parser.add_argument(
        "--account",
        default="0434226",
        help="Số tài khoản SSI (mặc định 0434226)",
    )
    parser.add_argument(
        "--from",
        dest="frm",
        required=True,
        help="Ngày bắt đầu (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to",
        default=None,
        help="Ngày kết thúc (YYYY-MM-DD, mặc định hôm nay)",
    )
    args = parser.parse_args()

    report = asyncio.run(run_report(args.account, args.frm, args.to))
    print_performance_report(report)


if __name__ == "__main__":
    main()
