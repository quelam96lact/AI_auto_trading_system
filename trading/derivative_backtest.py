import argparse
from datetime import date, datetime, time, timedelta

from trading.backtest import BacktestReport
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
    DerivativePaperBroker,
)
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

# DEPRECATED (Brief 84): Hằng số cũ để giữ tương thích import cho các test cũ.
# CLI và logic nghiệp vụ KHÔNG dùng hằng số này; bắt buộc truyền tham số --symbol.
DERIVATIVE_SYMBOL = "41I1G8000"


def _unrealized(broker: DerivativePaperBroker, marks: dict[str, float]) -> float:
    total = 0.0
    for symbol, pos in broker.positions.items():
        if pos.qty == 0 or symbol not in marks:
            continue
        mark = marks[symbol]
        if pos.qty > 0:
            total += (mark - pos.avg_price) * pos.qty * broker.contract_multiplier
        else:
            total += (pos.avg_price - mark) * abs(pos.qty) * broker.contract_multiplier
        # DERIV-FEE-1 Phan 2: tru phi MO da tra cho vi the dang mo — truoc day
        # thuan theo diem, khong phan anh phi vao lenh (cung thieu sot ma ban
        # co phieu da sua o 6664cd9: unrealized_pnl phan anh phi vao lenh).
        total -= pos.open_fee
    return total


def _exit_price(net: int, price: float, half_spread: float) -> float:
    """Giá đóng vị thế sau nửa spread: đóng long = bán (thấp hơn), đóng short = mua (cao hơn)."""
    return price - half_spread if net > 0 else price + half_spread


def run_derivative_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: DerivativeRiskManager,
    capital: float,
    stop_loss_points: float = 0.0,
    take_profit_points: float = 0.0,
    intraday_close_time: time | None = None,
    eod_keep_min_profit_points: float = 0.0,
    spread_points: float = 0.0,
) -> BacktestReport:
    """`spread_points`: spread TRỌN VÒNG (điểm chỉ số) khi vào và ra bằng lệnh thị trường.
    Mỗi lượt khớp chịu `spread_points / 2`: mua cao hơn, bán thấp hơn giá tham chiếu (giá
    đóng nến, hoặc mức SL/TP/giá mở khi gap). Áp cho MỌI lượt khớp, kể cả SL, TP và đóng EOD
    (bảo thủ: lệnh TP giới hạn thực tế có thể không trả spread). Mặc định 0 = hành vi cũ.
    Đợt 98 đo spread VN30F trung vị 0,2 điểm. Giá khớp vẫn là giá đóng CỦA NẾN SINH TÍN HIỆU
    (không khớp ở nến sau): spread chỉ bù một phần, không loại bỏ độ lạc quan đó."""
    if spread_points < 0:
        raise ValueError(f"spread_points phải >= 0, nhận {spread_points}")
    half = spread_points / 2.0
    broker = DerivativePaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]
    current_day: date | None = None
    day_start_realized: float = 0.0

    for bar in bars:
        crossover = strategy.compute_crossover(bar)
        marks[bar.symbol] = bar.close
        net = broker.position_qty(bar.symbol)
        # daily_pnl tinh theo NGAY: realized phat sinh trong ngay hien tai
        # (snapshot realized dau ngay, reset khi doi ngay) + unrealized dang
        # mo - khong tich luy tu dau backtest (bug da fix - xem plan
        # 2026-08-09-derivative-daily-loss-and-eod-threshold-fix.md).
        if bar.ts.date() != current_day:
            current_day = bar.ts.date()
            day_start_realized = broker.realized_pnl
        daily_pnl = (
            broker.realized_pnl - day_start_realized + _unrealized(broker, marks)
        )
        today = bar.ts.date()

        # Exit SL/TP (kiem tra TRUOC logic crossover; SL uu tien khi trung bar
        # - conservative; bar gap qua muc thi fill tai open - quy uoc gap cua
        # repo, giong TrailingStopManager). Sau exit khong mo lai cung bar.
        if net != 0 and (stop_loss_points > 0 or take_profit_points > 0):
            entry = broker.positions[bar.symbol].avg_price
            exit_price: float | None = None
            if net > 0:  # long
                if stop_loss_points > 0 and bar.low <= entry - stop_loss_points:
                    exit_price = min(bar.open, entry - stop_loss_points)
                elif take_profit_points > 0 and bar.high >= entry + take_profit_points:
                    exit_price = max(bar.open, entry + take_profit_points)
            else:  # short
                if stop_loss_points > 0 and bar.high >= entry + stop_loss_points:
                    exit_price = max(bar.open, entry + stop_loss_points)
                elif take_profit_points > 0 and bar.low <= entry - take_profit_points:
                    exit_price = min(bar.open, entry - take_profit_points)
            if exit_price is not None:
                fill = broker.close(
                    bar.symbol, _exit_price(net, exit_price, half), bar.ts
                )
                all_fills.append(fill)
                assert fill.pnl is not None  # fill dong vi the luon co pnl
                risk.record_trade_result(fill.pnl, bar.ts.date())
                equity = broker.cash + _unrealized(broker, marks)
                equity_curve.append(equity)
                continue

        # Ep dong vi the tai/sau gio cat (intraday_close_time) - truoc logic
        # crossover, khong mo lai cung bar. Theo yeu cau user: lenh dang LAI
        # duoc giu qua dem, NHUNG chi khi lai du bu chi phi qua dem (nguong
        # eod_keep_min_profit_points, tinh bang diem x he so nhan; user truyen
        # gia tri uoc luong D+ + phi dong, engine khong tu gia dinh chi phi).
        if (
            net != 0
            and intraday_close_time is not None
            and bar.ts.astimezone(TZ).time() >= intraday_close_time
            and _unrealized(broker, marks)
            <= eod_keep_min_profit_points * DERIVATIVE_CONTRACT_MULTIPLIER
        ):
            fill = broker.close(
                bar.symbol, _exit_price(net, bar.close, half), bar.ts
            )
            all_fills.append(fill)
            assert fill.pnl is not None  # fill dong vi the luon co pnl
            risk.record_trade_result(fill.pnl, bar.ts.date())
            equity = broker.cash + _unrealized(broker, marks)
            equity_curve.append(equity)
            continue

        if crossover == "bull" and net < 0:
            fill = broker.close(
                bar.symbol, _exit_price(net, bar.close, half), bar.ts
            )
            all_fills.append(fill)
            assert fill.pnl is not None  # fill dong vi the luon co pnl
            risk.record_trade_result(fill.pnl, bar.ts.date())
        elif crossover == "bull" and net == 0:
            if risk.approve_open("long", net, daily_pnl, today):
                all_fills.append(
                    broker.open_long(
                        bar.symbol, strategy.qty, bar.close + half, bar.ts
                    )
                )
        elif crossover == "bear" and net > 0:
            fill = broker.close(
                bar.symbol, _exit_price(net, bar.close, half), bar.ts
            )
            all_fills.append(fill)
            assert fill.pnl is not None  # fill dong vi the luon co pnl
            risk.record_trade_result(fill.pnl, bar.ts.date())
        elif (
            crossover == "bear"
            and net == 0
            and risk.approve_open("short", net, daily_pnl, today)
        ):
            all_fills.append(
                broker.open_short(
                    bar.symbol, strategy.qty, bar.close - half, bar.ts
                )
            )

        equity = broker.cash + _unrealized(broker, marks)
        equity_curve.append(equity)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    close_fills = [f for f in all_fills if f.pnl is not None]
    wins = sum(1 for f in close_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=_unrealized(broker, marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(close_fills)) if close_fills else 0.0,
        trades=len(close_fills),
    )


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Chạy backtest cho phân hệ phái sinh VN.")
    ap.add_argument(
        "--symbol",
        required=True,
        help="Mã hợp đồng phái sinh hoặc chuỗi liên tục (bắt buộc, vd: VN30F1M_CONT, 41I1GA000)",
    )
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    return ap.parse_args(args)


def main() -> None:
    args = parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    bars = storage.read_derivative_bars(args.symbol, frm, to)

    strategy = SmaCrossStrategy(qty=1)
    risk = DerivativeRiskManager(capital=args.capital)
    report = run_derivative_backtest(bars, strategy, risk, args.capital)

    print(f"Bars replayed: {len(bars)}")
    print(f"Trades: {report.trades}  Win rate: {report.win_rate:.1%}")
    print(
        f"Realized PnL: {report.realized_pnl:,.0f}  Unrealized PnL: {report.unrealized_pnl:,.0f}"
    )
    print(
        f"Ending cash: {report.ending_cash:,.0f}  Max drawdown: {report.max_drawdown:.1%}"
    )


if __name__ == "__main__":
    main()
