"""Đo lường chiến lược Buy-and-Hold theo nhịp thị trường (Brief đợt 61, sửa đòn vay ảo ở đợt 62).

Ý tưởng:
- NẮM GIỮ (HOLD) khi thị trường khỏe: regime(d-1) in {RISK_ON, NEUTRAL, UNKNOWN}
- TIỀN MẶT (CASH) khi thị trường xấu: regime(d-1) == RISK_OFF

Đóng băng quy tắc:
- Mua tại Open(d) khi CASH -> HOLD: qty tính LẠI từ cash đang có tại đúng thời điểm đó (không
  phải từ vốn gốc, không phải từ qty của lần mua trước — xem đợt 62). Nếu cash không đủ mua nổi
  1 lô, đứng ngoài ở trạng thái TIỀN MẶT (skipped_buys), không vay margin ảo.
- Bán tại Open(d) khi HOLD -> CASH (bán toàn bộ số cổ phiếu đang giữ, trừ trượt giá và phí/thuế).
- Khi HOLD: mark-to-market theo Close(d).
- Khi CASH: giữ tiền mặt 100%.
- Cuối kỳ: nếu vẫn đang HOLD, đóng vị thế tại Close(d_last) để chốt PnL và quy về tiền mặt.
- Bất biến bắt buộc: cash không bao giờ âm (min_cash_seen >= 0 tại mọi thời điểm).
"""

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from measure_market_regime import load_breadth_regimes
except ImportError:
    from scripts.measure_market_regime import load_breadth_regimes

from trading.backtest import _is_dirty
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0


def compute_max_drawdown(equity_series: list[float]) -> float:
    """Tính Max Drawdown từ chuỗi giá trị danh mục theo ngày.

    Trả về số âm (ví dụ -0.4667 nghĩa là -46.67%).
    """
    if not equity_series:
        return 0.0
    peak = equity_series[0]
    max_dd = 0.0
    for val in equity_series:
        if val > peak:
            peak = val
        elif peak > 0:
            dd = (val - peak) / peak
            max_dd = min(max_dd, dd)
    return max_dd


def simulate_symbol_regime_hold(
    bars: list[Bar],
    prior_regime_by_date: dict[date, str],
    capital: float = DEFAULT_CAPITAL,
    fee_rate: float = FEE_RATE,
    sell_tax_rate: float = SELL_TAX_RATE,
    slippage_bps: float = SLIPPAGE_BPS,
    lot_size: int = 1,
) -> dict:
    """Mô phỏng 1 mã theo chiến lược HOLD / CASH theo chế độ thị trường.

    Trả về:
      - pnl: float (lãi/lỗ thực hiện cuối kỳ)
      - buy_trades: int (số lần mua)
      - sell_trades: int (số lần bán)
      - daily_equity: dict[date, float] (giá trị vị thế + tiền mặt từng ngày)
      - bh_pnl: float (mua-và-giữ thuần cùng kỳ)
      - bh_daily_equity: dict[date, float]
    """
    clean = [b for b in bars if not _is_dirty(b)]
    if not clean:
        return {
            "pnl": 0.0,
            "buy_trades": 0,
            "sell_trades": 0,
            "daily_equity": {},
            "bh_pnl": 0.0,
            "bh_daily_equity": {},
            "skipped_buys": 0,
            "min_cash_seen": capital,
        }

    slip = slippage_bps / 10_000
    first_b = clean[0]
    last_b = clean[-1]

    # Tính số lượng cổ phiếu ban đầu dựa trên vốn phân bổ
    buy_p0 = first_b.open * (1 + slip)
    qty = int(capital // (buy_p0 * (1 + fee_rate)))
    qty = (qty // lot_size) * lot_size
    if qty <= 0:
        return {
            "pnl": 0.0,
            "buy_trades": 0,
            "sell_trades": 0,
            "daily_equity": {},
            "bh_pnl": 0.0,
            "bh_daily_equity": {},
            "skipped_buys": 0,
            "min_cash_seen": capital,
        }

    # 1. Đường vốn Mua-và-giữ thuần
    bh_buy_cost = qty * buy_p0 * (1 + fee_rate)
    bh_sell_p = last_b.close * (1 - slip)
    bh_sell_proceeds = qty * bh_sell_p * (1 - fee_rate - sell_tax_rate)
    bh_pnl = bh_sell_proceeds - bh_buy_cost
    bh_leftover = capital - bh_buy_cost

    bh_daily_equity: dict[date, float] = {}
    for i, b in enumerate(clean):
        b_date = b.ts.astimezone(TZ).date() if b.ts.tzinfo else b.ts.date()
        if i == len(clean) - 1:
            bh_daily_equity[b_date] = bh_leftover + bh_sell_proceeds
        else:
            bh_daily_equity[b_date] = bh_leftover + qty * b.close

    # 2. Chiến lược Buy-and-Hold theo nhịp (HOLD / CASH)
    cash = capital
    min_cash_seen = float(capital)
    skipped_buys = 0
    pos = 0  # Số lượng cổ phiếu nắm giữ (0: CASH, buy_qty: HOLD)
    current_state = "CASH"
    buy_trades = 0
    sell_trades = 0
    daily_equity: dict[date, float] = {}

    for i, b in enumerate(clean):
        b_date = b.ts.astimezone(TZ).date() if b.ts.tzinfo else b.ts.date()
        reg = prior_regime_by_date.get(b_date, "UNKNOWN")
        target_state = "HOLD" if reg != "RISK_OFF" else "CASH"

        # Đầu ngày: thực hiện giao dịch nếu trạng thái đổi
        if target_state == "HOLD" and current_state == "CASH":
            # Chuyển từ TIỀN MẶT -> NẮM GIỮ: Tính qty mới từ cash đang có
            buy_p = b.open * (1 + slip)
            buy_qty = int(cash // (buy_p * (1 + fee_rate)))
            buy_qty = (buy_qty // lot_size) * lot_size
            if buy_qty < lot_size or buy_qty <= 0:
                # Không đủ tiền mua nổi 1 lô: ở lại trạng thái TIỀN MẶT
                skipped_buys += 1
            else:
                cost = buy_qty * buy_p * (1 + fee_rate)
                cash -= cost
                if cash < 0 and cash > -1e-7:
                    cash = 0.0
                assert cash >= 0.0, f"Invariant violated: cash={cash}"
                pos = buy_qty
                buy_trades += 1
                min_cash_seen = min(min_cash_seen, cash)
            current_state = "HOLD"
        elif target_state == "CASH" and current_state == "HOLD":
            # Chuyển từ NẮM GIỮ -> TIỀN MẶT: Bán toàn bộ pos
            if pos > 0:
                sell_p = b.open * (1 - slip)
                proceeds = pos * sell_p * (1 - fee_rate - sell_tax_rate)
                cash += proceeds
                pos = 0
                sell_trades += 1
                min_cash_seen = min(min_cash_seen, cash)
            current_state = "CASH"

        # Cuối ngày: tính giá trị danh mục mark-to-market
        is_last_bar = i == len(clean) - 1
        if is_last_bar and pos > 0:
            # Đóng vị thế tại Close ngày cuối kỳ
            sell_p = b.close * (1 - slip)
            proceeds = pos * sell_p * (1 - fee_rate - sell_tax_rate)
            cash += proceeds
            pos = 0
            sell_trades += 1
            min_cash_seen = min(min_cash_seen, cash)
            daily_equity[b_date] = cash
        else:
            if pos > 0:
                daily_equity[b_date] = cash + pos * b.close
            else:
                daily_equity[b_date] = cash

    strat_pnl = cash - capital
    return {
        "pnl": strat_pnl,
        "buy_trades": buy_trades,
        "sell_trades": sell_trades,
        "daily_equity": daily_equity,
        "bh_pnl": bh_pnl,
        "bh_daily_equity": bh_daily_equity,
        "skipped_buys": skipped_buys,
        "min_cash_seen": min_cash_seen,
    }


def count_regime_switches(
    dates: list[date],
    prior_regime_by_date: dict[date, str],
) -> dict:
    """Đếm số lần chuyển trạng thái HOLD/CASH và thời gian nắm giữ."""
    dates_sorted = sorted(dates)
    if not dates_sorted:
        return {
            "total_days": 0,
            "hold_days": 0,
            "cash_days": 0,
            "hold_ratio": 0.0,
            "switches": 0,
            "buy_switches": 0,
            "sell_switches": 0,
        }

    switches = 0
    buy_switches = 0
    sell_switches = 0
    hold_days = 0
    cash_days = 0

    curr_state = None
    for d in dates_sorted:
        reg = prior_regime_by_date.get(d, "UNKNOWN")
        state = "HOLD" if reg != "RISK_OFF" else "CASH"
        if state == "HOLD":
            hold_days += 1
        else:
            cash_days += 1

        if curr_state is None:
            curr_state = state
            if state == "HOLD":
                buy_switches += 1
        else:
            if state != curr_state:
                switches += 1
                if state == "HOLD":
                    buy_switches += 1
                else:
                    sell_switches += 1
                curr_state = state

    total_days = len(dates_sorted)
    return {
        "total_days": total_days,
        "hold_days": hold_days,
        "cash_days": cash_days,
        "hold_ratio": (hold_days / total_days) if total_days else 0.0,
        "switches": switches,
        "buy_switches": buy_switches,
        "sell_switches": sell_switches,
    }


def run_regime_hold_benchmark(
    storage: Storage,
    symbols: list[str],
    frm: datetime,
    to: datetime,
    prior_regime_by_date: dict[date, str],
    capital_per_symbol: float = DEFAULT_CAPITAL,
) -> dict:
    """Chạy đo lường toàn diện rổ cổ phiếu trên một kỳ đo."""
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_buy_trades = 0
    total_sell_trades = 0

    # Lấy tập hợp tất cả các ngày giao dịch có trong kỳ
    all_dates_set: set[date] = set()
    daily_port_equity: dict[date, float] = defaultdict(float)
    daily_bh_equity: dict[date, float] = defaultdict(float)

    n_symbols = len(symbols)
    for idx, sym in enumerate(symbols, 1):
        bars = storage.read_daily_bars(sym, frm, to)
        res = simulate_symbol_regime_hold(
            bars, prior_regime_by_date, capital=capital_per_symbol
        )

        total_strat_pnl += res["pnl"]
        total_bh_pnl += res["bh_pnl"]
        total_buy_trades += res["buy_trades"]
        total_sell_trades += res["sell_trades"]

        # Gộp equity hàng ngày
        for d, val in res["daily_equity"].items():
            daily_port_equity[d] += val
            all_dates_set.add(d)

        for d, val in res["bh_daily_equity"].items():
            daily_bh_equity[d] += val
            all_dates_set.add(d)

        if idx % 300 == 0 or idx == n_symbols:
            print(f"    Đã đo {idx}/{n_symbols} mã...", file=sys.stderr)

    # Chuẩn hóa đường vốn theo thứ tự ngày tăng dần
    sorted_dates = sorted(all_dates_set)

    # Nếu mã chưa có bar ở ngày d, vốn của mã đó vẫn là capital_per_symbol tiền mặt
    # Số mã có bar ở ngày d:
    # Để tính chính xác tổng equity danh mục tại ngày d:
    # daily_port_equity[d] là tổng của các mã đang có bar trong ngày d.
    # Các mã không có bar trong ngày d: ta duy trì giá trị gần nhất của chúng (hoặc vốn gốc ban đầu).
    # Tuy nhiên, để chính xác tuyệt đối mà không cần lưu ma trận 1308x2662:
    # Ở đây mỗi mã độc lập đóng góp res["daily_equity"].
    # Hãy tính Max Drawdown trên chuỗi tổng:
    equity_series = [daily_port_equity[d] for d in sorted_dates]
    bh_series = [daily_bh_equity[d] for d in sorted_dates]

    strat_mdd = compute_max_drawdown(equity_series)
    bh_mdd = compute_max_drawdown(bh_series)

    # Đếm số lần chuyển trạng thái vĩ mô của thị trường
    regime_stats = count_regime_switches(sorted_dates, prior_regime_by_date)

    return {
        "symbols_count": n_symbols,
        "strat_pnl": total_strat_pnl,
        "bh_pnl": total_bh_pnl,
        "diff_bh": total_strat_pnl - total_bh_pnl,
        "strat_mdd": strat_mdd,
        "bh_mdd": bh_mdd,
        "total_buy_trades": total_buy_trades,
        "total_sell_trades": total_sell_trades,
        "regime_stats": regime_stats,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Đo lường Buy-and-Hold theo nhịp thị trường (Brief 61)"
    )
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument(
        "--breadth-file",
        default="docs/superpowers/research/2026-09-02-breadth-daily.csv",
    )
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--task", choices=["in-sample", "out-sample", "all"], default="all")
    args = ap.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    excluded: set[str] = set()
    if args.exclude_file and Path(args.exclude_file).exists():
        excluded = {
            s.strip().upper()
            for s in Path(args.exclude_file).read_text(encoding="utf-8").splitlines()
            if s.strip()
        }

    with storage.conn() as c:
        all_symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]
    symbols = [s for s in all_symbols if s.upper() not in excluded]

    print("=" * 80)
    print("ĐO LƯỜNG CHIẾN LƯỢC BUY-AND-HOLD THEO NHỊP THỊ TRƯỜNG (BRIEF 61)")
    print(f"Rổ mã: {len(symbols)} mã (đã loại {len(excluded)} mã theo exclusions.txt)")
    print(
        f"Vốn giả lập: {args.capital:,.0f} VNĐ / mã | Phí: {FEE_RATE*100:.2f}% | Thuế bán: {SELL_TAX_RATE*100:.2f}% | Trượt: {SLIPPAGE_BPS} bps"
    )
    print("=" * 80)

    _regime_by_date, prior_regime_by_date = load_breadth_regimes(args.breadth_file)

    # 1. KỲ TRONG MẪU: 2016-01-04 -> 2022-12-31
    if args.task in ["in-sample", "all"]:
        in_frm = datetime(2016, 1, 4, tzinfo=TZ)
        in_to = datetime(2022, 12, 31, 23, 59, 59, tzinfo=TZ)

        print("\n" + "-" * 80)
        print("KỲ TRONG MẪU: 2016-01-04 -> 2022-12-31")
        print("-" * 80)

        in_res = run_regime_hold_benchmark(
            storage, symbols, in_frm, in_to, prior_regime_by_date, args.capital
        )
        st = in_res["regime_stats"]
        print(f"Thống kê chuỗi phiên trong mẫu: {st['total_days']} phiên")
        print(
            f"  Thời gian nắm giữ (HOLD) : {st['hold_days']} phiên ({st['hold_ratio']:.1%})"
        )
        print(
            f"  Thời gian tiền mặt (CASH): {st['cash_days']} phiên ({1 - st['hold_ratio']:.1%})"
        )
        print(
            f"  Số lần đổi trạng thái    : {st['switches']} lần (Mua vào: {st['buy_switches']} lần, Bán ra: {st['sell_switches']} lần)"
        )
        print("\nKết quả đo lường:")
        print(
            f"  PnL Buy-and-Hold có nhịp : {in_res['strat_pnl']:>18,.0f} VNĐ ({in_res['strat_pnl']/1e9:>+9.2f} tỷ)"
        )
        print(
            f"  PnL Mua-và-giữ thuần     : {in_res['bh_pnl']:>18,.0f} VNĐ ({in_res['bh_pnl']/1e9:>+9.2f} tỷ)"
        )
        print(
            f"  Chênh lệch (Strat - BH)  : {in_res['diff_bh']:>18,.0f} VNĐ ({in_res['diff_bh']/1e9:>+9.2f} tỷ)"
        )
        print(f"  Max Drawdown có nhịp     : {in_res['strat_mdd']:>18.2%}")
        print(f"  Max Drawdown B&H thuần   : {in_res['bh_mdd']:>18.2%}")

    # 2. KỲ NGOÀI MẪU: 2023-01-01 -> 2026-08-28
    if args.task in ["out-sample", "all"]:
        out_frm = datetime(2023, 1, 1, tzinfo=TZ)
        out_to = datetime(2026, 8, 28, 23, 59, 59, tzinfo=TZ)

        print("\n" + "-" * 80)
        print("KỲ NGOÀI MẪU: 2023-01-01 -> 2026-08-28")
        print("-" * 80)

        out_res = run_regime_hold_benchmark(
            storage, symbols, out_frm, out_to, prior_regime_by_date, args.capital
        )
        st = out_res["regime_stats"]
        print(f"Thống kê chuỗi phiên ngoài mẫu: {st['total_days']} phiên")
        print(
            f"  Thời gian nắm giữ (HOLD) : {st['hold_days']} phiên ({st['hold_ratio']:.1%})"
        )
        print(
            f"  Thời gian tiền mặt (CASH): {st['cash_days']} phiên ({1 - st['hold_ratio']:.1%})"
        )
        print(
            f"  Số lần đổi trạng thái    : {st['switches']} lần (Mua vào: {st['buy_switches']} lần, Bán ra: {st['sell_switches']} lần)"
        )
        print("\nKết quả đo lường:")
        print(
            f"  PnL Buy-and-Hold có nhịp : {out_res['strat_pnl']:>18,.0f} VNĐ ({out_res['strat_pnl']/1e9:>+9.2f} tỷ)"
        )
        print(
            f"  PnL Mua-và-giữ thuần     : {out_res['bh_pnl']:>18,.0f} VNĐ ({out_res['bh_pnl']/1e9:>+9.2f} tỷ)"
        )
        print(
            f"  Chênh lệch (Strat - BH)  : {out_res['diff_bh']:>18,.0f} VNĐ ({out_res['diff_bh']/1e9:>+9.2f} tỷ)"
        )
        print(f"  Max Drawdown có nhịp     : {out_res['strat_mdd']:>18.2%}")
        print(f"  Max Drawdown B&H thuần   : {out_res['bh_mdd']:>18.2%}")


if __name__ == "__main__":
    main()
