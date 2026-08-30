from collections import deque
from dataclasses import dataclass, field

from trading.broker import Fill
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.daily_breakout import DailyBreakoutStrategy
from trading.strategies.octopus_pullback import (
    OctopusPullbackStrategy,
    liquidity_avg_before,
)
from trading.strategy import Strategy
from trading.trailing_stop import TrailingStopManager


@dataclass
class BacktestReport:
    fills: list[Fill] = field(default_factory=list)
    ending_cash: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades: int = 0
    # SPEC-1b: moc mua-va-giu (cung ma, cung ky, cung von, cung bieu phi, gom
    # phi mua lan phi ban) — chien luoc co lai nhung thua moc nay = THẤT BẠI.
    buy_and_hold_pnl: float = 0.0
    # SPEC-1c: so dong bar bi loai vi OHLC <= 0, theo tung ma.
    filtered_bars: dict[str, int] = field(default_factory=dict)
    # backtest-grafana: duong von moi bar — (ts, equity), ts lay tu bar sach.
    # Phoi ra tu run_backtest (NOI BO da tinh) — KHONG tinh lai trong script
    # (commit 4ea4c8d: mot cong thuc hai ban = hai tap bar khac nhau).
    equity_curve: list[tuple] = field(default_factory=list)
    # backtest-grafana: duong MUA-VA-GIU that, cung moc ts voi equity_curve.
    # Diem cuoi LUON bang capital + buy_and_hold_pnl (co test khang dinh) — do
    # la cach chung minh day KHONG phai ban thu hai cua cong thuc _buy_and_hold.
    # Truoc day Grafana noi suy tuyen tinh capital -> capital+pnl: duong thang
    # do co drawdown = 0, che mat cu sap that cua benchmark (VCB 2020-02 dang
    # lo 7,5% ma duong ve dang lai) va la mot ban SQL cua cung cong thuc.
    buy_and_hold_curve: list[tuple] = field(default_factory=list)


def _is_dirty(bar: Bar) -> bool:
    """SPEC-1c: bar rac = co open/high/low/close <= 0."""
    return bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0


def ever_liquid(bars: list[Bar], threshold: float, window: int) -> bool:
    """Mã có từng đủ thanh khoản chưa: >= 1 bar mà rolling-`window` (KHÔNG tính
    bar hiện tại) của close*volume >= threshold.

    MỘT NGUỒN SỰ THẬT với OctopusPullbackStrategy._liquidity_ok (2026-08-16):
    bar rác (OHLC<=0) bị loại HẲN khỏi cửa sổ, không bao giờ được append — đúng
    hành vi strategy, nơi run_backtest đã lọc bar rác TRƯỚC khi strategy nhìn
    thấy. Bản cũ của hàm này (trong scripts/measure_strategy.py) append cả bar
    rác vào deque rồi mới continue, nên bình quân cửa sổ bị kéo lệch. Cửa sổ
    tính qua liquidity_avg_before — cùng hàm lõi strategy dùng."""
    vals: deque = deque(maxlen=window + 1)
    for b in bars:
        if _is_dirty(b):
            continue  # bar rác KHÔNG vào cửa sổ — bar rác không phải phiên thật
        vals.append(b.close * b.volume)
        avg = liquidity_avg_before(list(vals), window)
        if avg is not None and avg >= threshold:
            return True
    return False


def _buy_and_hold(bars: list[Bar], capital: float, fee_rate: float, sell_tax_rate: float, slippage_bps: float) -> float:
    """SPEC-1b: voi moi ma, mua o bar DAU (gom phi mua vao gia von nhu
    PaperBroker), giu toi bar CUOI, ban (tru phi ban + thue). Von ban dau chia
    deu cho cac ma de khong double-count; 1 ma -> dung toan bo von."""
    symbols = sorted({b.symbol for b in bars})
    if not symbols:
        return 0.0
    per_symbol = capital / len(symbols)
    slip = slippage_bps / 10_000
    total = 0.0
    for sym in symbols:
        sym_bars = [b for b in bars if b.symbol == sym]
        first, last = sym_bars[0], sym_bars[-1]
        buy_price = first.open * (1 + slip)
        sell_price = last.close * (1 - slip)
        qty = int(per_symbol // (buy_price * (1 + fee_rate)))  # phi mua trong gia von
        if qty <= 0:
            continue
        buy_cost = qty * buy_price * (1 + fee_rate)
        sell_proceeds = qty * sell_price * (1 - fee_rate - sell_tax_rate)
        total += sell_proceeds - buy_cost
    return total


def _buy_and_hold_curve(
    bars: list[Bar],
    capital: float,
    fee_rate: float,
    sell_tax_rate: float,
    slippage_bps: float,
) -> list[tuple]:
    """Duong von MUA-VA-GIU that, mot diem moi bar (cung moc ts voi
    equity_curve cua run_backtest).

    Dung NGUYEN cach tinh cua `_buy_and_hold` — cung gia mua/ban, cung phi,
    cung cach chia von — chi khac o cho no ghi lai gia tri TUNG BAR thay vi
    chi tra ve lai/lo cuoi ky. Bat bien: diem cuoi == capital +
    _buy_and_hold(...). Neu hai ham nay lech nhau thi test se do; do la co y,
    vi mot cong thuc ton tai hai ban chinh la loi 4ea4c8d da phai di sua.

    Trong khi con giu: mark-to-market theo close (chua tru phi ban — chua ban).
    Tu bar CUOI cua moi ma tro di: quy ra tien da tru phi ban + thue.
    """
    if not bars:
        return []
    symbols = sorted({b.symbol for b in bars})
    per_symbol = capital / len(symbols)
    slip = slippage_bps / 10_000

    qty: dict[str, int] = {}
    sold_value: dict[str, float] = {}
    last_idx: dict[str, int] = {}
    spent = 0.0
    for sym in symbols:
        sym_bars = [b for b in bars if b.symbol == sym]
        first, last = sym_bars[0], sym_bars[-1]
        buy_price = first.open * (1 + slip)
        q = int(per_symbol // (buy_price * (1 + fee_rate)))
        if q <= 0:
            continue
        qty[sym] = q
        spent += q * buy_price * (1 + fee_rate)
        sell_price = last.close * (1 - slip)
        sold_value[sym] = q * sell_price * (1 - fee_rate - sell_tax_rate)
    for i, b in enumerate(bars):
        last_idx[b.symbol] = i

    leftover = capital - spent
    marks: dict[str, float] = {}
    curve: list[tuple] = [(bars[0].ts, capital)]
    for i, bar in enumerate(bars):
        marks[bar.symbol] = bar.close
        held = 0.0
        for sym, q in qty.items():
            if i >= last_idx[sym]:
                held += sold_value[sym]  # da ban xong ma nay
            else:
                held += q * marks.get(sym, 0.0)
        curve.append((bar.ts, leftover + held))
    return curve


def run_backtest(
    bars: list[Bar],
    strategy: Strategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    capital: float,
) -> BacktestReport:
    # SPEC-1c: loai bar rac TRUOC khi vao vong lap — khong co lenh nao khop o
    # gia 0, va so dong loai duoc bao cao theo tung ma (im lang loc = che giau
    # van de du lieu).
    filtered: dict[str, int] = {}
    clean_bars: list[Bar] = []
    for b in bars:
        if _is_dirty(b):
            filtered[b.symbol] = filtered.get(b.symbol, 0) + 1
        else:
            clean_bars.append(b)
    bars = clean_bars

    broker = PaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    # backtest-grafana: (ts, equity) — ts diem DAU lay tu bar dau tien (sach),
    # equity = capital; moi bar sau them 1 diem. bars rong (khong co bar sach
    # nao) -> chi con diem dau, ts=None.
    first_ts = bars[0].ts if bars else None
    equity_curve: list[tuple] = [(first_ts, capital)]

    for bar in bars:
        fills = broker.on_bar(bar)
        all_fills.extend(fills)
        marks[bar.symbol] = bar.close
        for f in fills:
            if f.side == "BUY":
                trailing_stop.on_position_opened(f.symbol, f.price)
            else:
                trailing_stop.on_position_closed(f.symbol)

        signal = strategy.on_bar(bar, broker)

        stop_price = None
        if broker.position_qty(bar.symbol) > 0:
            stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

        if stop_price is not None:
            forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
            if forced.qty > 0:  # SPEC-1a: chua settle -> qty=0, vi the giu nguyen
                trailing_stop.on_position_closed(bar.symbol)
                all_fills.append(forced)
        elif signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            sized = risk.approve_sized(
                signal,
                bar.close,
                strategy.last_atr(bar.symbol),
                broker.positions,
                daily_pnl,
                bar.ts.date(),
            )
            if sized is not None:
                broker.submit(sized)

        equity = broker.cash + sum(
            p.qty * marks.get(s, p.avg_price) for s, p in broker.positions.items()
        )
        equity_curve.append((bar.ts, equity))

    peak = equity_curve[0][1]
    max_dd = 0.0
    for _, e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    wins = sum(1 for f in sell_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=broker.unrealized_pnl(marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(sell_fills)) if sell_fills else 0.0,
        trades=len(sell_fills),
        buy_and_hold_pnl=_buy_and_hold(
            bars, capital, broker.fee_rate, broker.sell_tax_rate, broker.slippage_bps
        ),
        filtered_bars=filtered,
        equity_curve=equity_curve,
        buy_and_hold_curve=_buy_and_hold_curve(
            bars, capital, broker.fee_rate, broker.sell_tax_rate, broker.slippage_bps
        ),
    )


import argparse
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.resample import (
    resample_bars,
    resample_monthly,
    resample_weekly,
)
from trading.storage.db import Storage

# sma_cross DA BI GO khoi danh sach (2026-08-15, quyet dinh cua chu du an): do tren
# 4 cau hinh deu lo TRUOC KHI tinh phi, va no chua bao gio duoc chung minh co bien loi
# the. Class van con vi `trading/engine/main.py:71` dang chay no o che do paper —
# go khoi engine la mot quyet dinh KHAC, can co chien luoc thay the.
STRATEGIES = {
    "daily_breakout": lambda: DailyBreakoutStrategy(),
    "octopus_pullback": lambda: OctopusPullbackStrategy(),
}

# (bang_nguon, ham_resample). Khung noi ngay tinh tu bar 5m trong `bars`;
# 1d/1w/1M tinh tu `bars_daily`. Xem plan 2026-08-09-multi-timeframe-data.md.
_TF_SPEC = {
    "5m": ("bars", lambda bars: bars),
    "10m": ("bars", lambda bars: resample_bars(bars, 10)),
    "15m": ("bars", lambda bars: resample_bars(bars, 15)),
    "30m": ("bars", lambda bars: resample_bars(bars, 30)),
    "1h": ("bars", lambda bars: resample_bars(bars, 60)),
    "4h": ("bars", lambda bars: resample_bars(bars, 240)),
    "1d": ("bars_daily", lambda bars: bars),
    "1w": ("bars_daily", resample_weekly),
    "1M": ("bars_daily", resample_monthly),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    ap.add_argument("--symbols", required=True, help="VD: VCB,HPG")
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--tf", default="5m", choices=list(_TF_SPEC))
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    source, resample_fn = _TF_SPEC[args.tf]
    read = (
        storage.read_bars if source == "bars" else storage.read_daily_bars
    )

    bars: list[Bar] = []
    for sym in args.symbols.split(","):
        rows = read(sym, frm, to)
        bars.extend(resample_fn(rows))
    bars.sort(key=lambda b: (b.ts, b.symbol))

    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager(capital=args.capital)
    trailing_stop = TrailingStopManager()
    report = run_backtest(bars, strategy, risk, trailing_stop, args.capital)

    print(f"Bars replayed: {len(bars)}")
    if report.filtered_bars:
        detail = ", ".join(f"{s}: {n}" for s, n in sorted(report.filtered_bars.items()))
        print(f"Bars filtered (OHLC<=0): {sum(report.filtered_bars.values())} ({detail})")
    print(f"Trades: {report.trades}  Win rate: {report.win_rate:.1%}")
    print(
        f"Realized PnL: {report.realized_pnl:,.0f}  Unrealized PnL: {report.unrealized_pnl:,.0f}"
    )
    strat_pnl = report.realized_pnl + report.unrealized_pnl
    bh = report.buy_and_hold_pnl
    print(f"Buy&Hold PnL: {bh:,.0f}  Strategy PnL: {strat_pnl:,.0f}  Diff: {strat_pnl - bh:,.0f}")
    if report.trades > 0 and strat_pnl < bh:
        print("KET LUAN: THUA mua-va-giu (co lai nhung khong co bien loi the)")
    print(
        f"Ending cash: {report.ending_cash:,.0f}  Max drawdown: {report.max_drawdown:.1%}"
    )


if __name__ == "__main__":
    main()
