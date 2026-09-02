"""Đo lường chiến lược theo chế độ thị trường (Brief đợt 9).

Giai đoạn 1: ĐO
- Task 2: Đo từng chiến lược (daily_breakout, octopus_pullback, sma_cross)
  theo từng chế độ (RISK_ON, NEUTRAL, RISK_OFF) trên KỲ TRONG MẪU (2016-01-04 -> 2022-12-31).
  Quy kết từng giao dịch về chế độ tại ngày mở lệnh (anti-lookahead: dùng regime của ngày T-1).
  So sánh với 2 mốc: Mua-và-giữ cùng kỳ và Chiến lược đơn tốt nhất suốt kỳ.

- Task 3: Chạy quy tắc chuyển đổi đã đóng băng trên KỲ NGOÀI MẪU (2023-01-01 -> 2026-08-28).
  So sánh với 3 mốc: Mua-và-giữ ngoài mẫu, Chiến lược đơn tốt nhất ngoài mẫu, và chính quy tắc trên kỳ trong mẫu.
"""

import argparse
import sys
from collections import deque
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.backtest import STRATEGIES, _is_dirty, run_backtest
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0


def load_breadth_regimes(csv_path: str | Path) -> tuple[dict[date, str], dict[date, str]]:
    """Đọc file CSV date,breadth,regime.
    Trả về:
      - regime_by_date: {date: regime}
      - prior_regime_by_date: {date: prior_day_regime} (chống look-ahead)
    """
    lines = Path(csv_path).read_text(encoding="utf-8").splitlines()
    regime_by_date: dict[date, str] = {}
    dates: list[date] = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        d = datetime.strptime(parts[0], "%Y-%m-%d").date()
        reg = parts[2].strip()
        regime_by_date[d] = reg
        dates.append(d)

    dates.sort()
    prior_regime_by_date: dict[date, str] = {}
    for i, d in enumerate(dates):
        if i == 0:
            prior_regime_by_date[d] = regime_by_date[d]
        else:
            prior_regime_by_date[d] = regime_by_date[dates[i - 1]]

    return regime_by_date, prior_regime_by_date


def attribute_trades(
    fills: list[Fill],
    prior_regime_by_date: dict[date, str],
) -> dict[str, list[Fill]]:
    """Quy kết các lệnh SELL về chế độ tại ngày mở lệnh (BUY date) theo FIFO."""
    trades_by_regime: dict[str, list[Fill]] = {
        "RISK_ON": [],
        "NEUTRAL": [],
        "RISK_OFF": [],
    }

    buy_queue: deque[tuple[date, int]] = deque()
    for f in fills:
        f_date = f.ts.astimezone(TZ).date() if f.ts.tzinfo else f.ts.date()
        if f.side == "BUY":
            buy_queue.append((f_date, f.qty))
        elif f.side == "SELL":
            entry_date = buy_queue[0][0] if buy_queue else f_date
            sell_qty = f.qty
            while buy_queue and sell_qty > 0:
                b_date, b_qty = buy_queue[0]
                if b_qty <= sell_qty:
                    sell_qty -= b_qty
                    buy_queue.popleft()
                else:
                    buy_queue[0] = (b_date, b_qty - sell_qty)
                    sell_qty = 0

            # Chế độ tại thời điểm mở lệnh (dùng regime của ngày trước đó để chống look-ahead)
            regime = prior_regime_by_date.get(entry_date, "RISK_OFF")
            trades_by_regime.setdefault(regime, []).append(f)

    return trades_by_regime


def measure_strategy_on_symbols(
    storage: Storage,
    symbols: list[str],
    strat_name: str,
    make_strat: Callable,
    frm: datetime,
    to: datetime,
    capital: float,
    prior_regime_by_date: dict[date, str],
) -> dict:
    """Đo 1 chiến lược trên danh sách mã và phân bổ theo regime."""
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_trades = 0
    total_wins = 0

    regime_stats = {
        "RISK_ON": {"pnl": 0.0, "trades": 0, "wins": 0},
        "NEUTRAL": {"pnl": 0.0, "trades": 0, "wins": 0},
        "RISK_OFF": {"pnl": 0.0, "trades": 0, "wins": 0},
    }

    for i, sym in enumerate(symbols, 1):
        bars = storage.read_daily_bars(sym, frm, to)
        report = run_backtest(
            bars,
            make_strat(),
            RiskManager(capital=capital),
            TrailingStopManager(),
            capital,
        )
        strat_pnl = report.realized_pnl + report.unrealized_pnl
        total_strat_pnl += strat_pnl
        total_bh_pnl += report.buy_and_hold_pnl
        total_trades += report.trades
        sell_fills = [f for f in report.fills if f.side == "SELL"]
        total_wins += sum(1 for f in sell_fills if f.pnl is not None and f.pnl > 0)

        # Phân bổ trade theo regime
        by_reg = attribute_trades(report.fills, prior_regime_by_date)
        for reg, fills in by_reg.items():
            for f in fills:
                if f.pnl is not None:
                    regime_stats[reg]["pnl"] += f.pnl
                    regime_stats[reg]["trades"] += 1
                    if f.pnl > 0:
                        regime_stats[reg]["wins"] += 1

        if i % 300 == 0 or i == len(symbols):
            print(f"    [{strat_name}] đã chạy {i}/{len(symbols)} mã", file=sys.stderr)

    return {
        "strat_name": strat_name,
        "total_strat_pnl": total_strat_pnl,
        "total_bh_pnl": total_bh_pnl,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "overall_win_rate": (total_wins / total_trades) if total_trades else 0.0,
        "by_regime": regime_stats,
    }


def run_regime_switching_backtest(
    storage: Storage,
    symbols: list[str],
    rule: dict[str, str],  # VD: {"RISK_ON": "daily_breakout", "NEUTRAL": "NONE", "RISK_OFF": "NONE"}
    frm: datetime,
    to: datetime,
    capital: float,
    prior_regime_by_date: dict[date, str],
) -> dict:
    """Chạy backtest theo quy tắc chuyển đổi regime trên danh sách mã.

    Tại mỗi bar của mã:
    - Xác định regime thị trường tại ngày hôm đó (sử dụng prior_regime_by_date để chống lookahead).
    - Lấy chiến lược tương ứng từ rule:
      * Nếu rule[regime] == 'NONE' hoặc 'KHONG_GIAO_DICH': không mở vị thế mới (không sinh BUY signal).
        Vị thế đang có vẫn được quản lý thoát lệnh theo TrailingStop / logic hiện hành.
      * Nếu rule[regime] in STRATEGIES: dùng strategy tương ứng để sinh signal.
    """
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_trades = 0
    total_wins = 0

    # Khởi tạo strategies
    # Chúng ta cần chạy từng mã độc lập
    for i, sym in enumerate(symbols, 1):
        bars = storage.read_daily_bars(sym, frm, to)
        clean_bars = [b for b in bars if not _is_dirty(b)]
        if not clean_bars:
            continue

        # Dựng PaperBroker, RiskManager, TrailingStop
        from trading.paper_broker import PaperBroker

        broker = PaperBroker(capital)
        risk = RiskManager(capital=capital)
        trailing_stop = TrailingStopManager()

        # Dựng các strategy instances cho mã này
        strat_instances = {name: factory() for name, factory in STRATEGIES.items()}
        all_fills: list[Fill] = []
        marks: dict[str, float] = {}

        for bar in clean_bars:
            fills = broker.on_bar(bar)
            all_fills.extend(fills)
            marks[bar.symbol] = bar.close
            for f in fills:
                if f.side == "BUY":
                    trailing_stop.on_position_opened(f.symbol, f.price)
                else:
                    trailing_stop.on_position_closed(f.symbol)

            bar_d = bar.ts.astimezone(TZ).date() if bar.ts.tzinfo else bar.ts.date()
            current_regime = prior_regime_by_date.get(bar_d, "RISK_OFF")
            active_strat_name = rule.get(current_regime, "NONE")

            # Update bars cho tất cả strategy để duy trì chỉ báo (warmup, ATR...)
            # Nhưng chỉ lấy signal từ chiến lược đang active
            signal = None
            for sname, s_inst in strat_instances.items():
                s_sig = s_inst.on_bar(bar, broker)
                if sname == active_strat_name:
                    signal = s_sig

            stop_price = None
            if broker.position_qty(bar.symbol) > 0:
                # Lấy last_atr từ active strategy nếu có, hoặc từ strategy bất kỳ
                atr = None
                if active_strat_name in strat_instances:
                    atr = strat_instances[active_strat_name].last_atr(bar.symbol)
                if atr is None:
                    for s_inst in strat_instances.values():
                        atr = s_inst.last_atr(bar.symbol)
                        if atr is not None:
                            break
                stop_price = trailing_stop.check(bar, atr)

            if stop_price is not None:
                forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
                if forced.qty > 0:
                    trailing_stop.on_position_closed(bar.symbol)
                    all_fills.append(forced)
            elif signal is not None:
                # Nếu rule là NONE / KHONG_GIAO_DICH, signal là None nên không vào lệnh
                daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
                atr = strat_instances[active_strat_name].last_atr(bar.symbol)
                sized = risk.approve_sized(
                    signal,
                    bar.close,
                    atr,
                    broker.positions,
                    daily_pnl,
                    bar.ts.date(),
                )
                if sized is not None:
                    broker.submit(sized)

        # Tính PnL cho mã
        from trading.backtest import _buy_and_hold
        bh_pnl = _buy_and_hold(clean_bars, capital, broker.fee_rate, broker.sell_tax_rate, broker.slippage_bps)
        strat_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)

        total_strat_pnl += strat_pnl
        total_bh_pnl += bh_pnl
        sell_fills = [f for f in all_fills if f.side == "SELL"]
        total_trades += len(sell_fills)
        total_wins += sum(1 for f in sell_fills if f.pnl is not None and f.pnl > 0)

        if i % 300 == 0 or i == len(symbols):
            print(f"    [Regime-Switching] đã chạy {i}/{len(symbols)} mã", file=sys.stderr)

    return {
        "rule": rule,
        "strat_pnl": total_strat_pnl,
        "bh_pnl": total_bh_pnl,
        "diff_bh": total_strat_pnl - total_bh_pnl,
        "trades": total_trades,
        "wins": total_wins,
        "win_rate": (total_wins / total_trades) if total_trades else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--breadth-file", default="docs/superpowers/research/2026-09-02-breadth-daily.csv")
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--task", choices=["task2", "task3", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0)
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
        symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]
    symbols = [s for s in symbols if s.upper() not in excluded]
    if args.limit > 0:
        symbols = symbols[:args.limit]

    print(f"Rổ đo lường: {len(symbols)} mã (đã loại {len(excluded)} mã không đáng tin)")

    # Nạp breadth
    _regime_by_date, prior_regime_by_date = load_breadth_regimes(args.breadth_file)

    # ==========================================
    # TASK 2: KỲ TRONG MẪU (2016-01-04 -> 2022-12-31)
    # ==========================================
    if args.task in ["task2", "all"]:
        in_frm = datetime(2016, 1, 4, tzinfo=TZ)
        in_to = datetime(2022, 12, 31, tzinfo=TZ) + timedelta(days=1)

        print("\n" + "=" * 78)
        print("TASK 2: ĐO TỪNG CHIẾN LƯỢC THEO CHẾ ĐỘ THỊ TRƯỜNG — KỲ TRONG MẪU (2016 -> 2022)")
        print("=" * 78)

        in_sample_results = {}
        for sname, factory in STRATEGIES.items():
            print(f"Đang chạy backtest chiến lược {sname} trên {len(symbols)} mã...")
            res = measure_strategy_on_symbols(
                storage, symbols, sname, factory, in_frm, in_to, args.capital, prior_regime_by_date
            )
            in_sample_results[sname] = res

        print("\n" + "=" * 78)
        print("BẢNG 3x3 KỲ TRONG MẪU (2016-01-04 -> 2022-12-31)")
        print("=" * 78)
        header = f"{'Chiến lược':<18} | {'RISK_ON (PnL / Lệnh / Win%)':<28} | {'NEUTRAL (PnL / Lệnh / Win%)':<28} | {'RISK_OFF (PnL / Lệnh / Win%)':<28}"
        print(header)
        print("-" * len(header))

        for sname in ["daily_breakout", "octopus_pullback", "sma_cross"]:
            res = in_sample_results[sname]
            cols = []
            for reg in ["RISK_ON", "NEUTRAL", "RISK_OFF"]:
                st = res["by_regime"][reg]
                wr = (st["wins"] / st["trades"]) if st["trades"] else 0.0
                pnl_b = st["pnl"] / 1e9  # Tỷ đồng
                cols.append(f"{pnl_b:>+7.2f} tỷ | {st['trades']:>5} | {wr:>5.1%}")
            print(f"{sname:<18} | {cols[0]:<28} | {cols[1]:<28} | {cols[2]:<28}")

        print("=" * 78)
        print("\nHAI MỐC SO SÁNH KỲ TRONG MẪU (2016-01-04 -> 2022-12-31):")
        # Mua-và-giữ cùng kỳ
        bh_pnl_in = in_sample_results["daily_breakout"]["total_bh_pnl"]
        print(f"  1. Mua-và-giữ cùng kỳ ({len(symbols)} mã) : {bh_pnl_in:>18,.0f} ({bh_pnl_in / 1e9:>+.2f} tỷ)")

        # Chiến lược đơn tốt nhất suốt kỳ
        for sname in ["daily_breakout", "octopus_pullback", "sma_cross"]:
            res = in_sample_results[sname]
            print(f"  2. {sname:<18} (toàn kỳ, ko chuyển) : PnL {res['total_strat_pnl']:>15,.0f} ({res['total_strat_pnl'] / 1e9:>+7.2f} tỷ) | lệnh {res['total_trades']:>6} | win {res['overall_win_rate']:>5.1%}")

    # ==========================================
    # TASK 3: KỲ NGOÀI MẪU (2023-01-01 -> 2026-08-28)
    # ==========================================
    if args.task in ["task3", "all"]:
        out_frm = datetime(2023, 1, 1, tzinfo=TZ)
        out_to = datetime(2026, 8, 28, tzinfo=TZ) + timedelta(days=1)

        print("\n" + "=" * 78)
        print("TASK 3: QUY TẮC CHUYỂN ĐỔI ĐÓNG BĂNG — KỲ NGOÀI MẪU (2023 -> 2026-08-28)")
        print("=" * 78)

        # Đóng băng quy tắc: từ bảng Task 2, kiểm tra xem quy tắc nào tốt nhất trên kỳ trong mẫu
        # Cấu hình rule đóng băng:
        # Giả định quy tắc: RISK_ON -> daily_breakout, NEUTRAL -> KHONG_GIAO_DICH, RISK_OFF -> KHONG_GIAO_DICH
        # Hoặc theo kết quả thực tế của Task 2.
        # Chúng ta sẽ chạy rule đóng băng và đo lường.
        rule_frozen = {
            "RISK_ON": "daily_breakout",
            "NEUTRAL": "NONE",
            "RISK_OFF": "NONE",
        }
        print(f"Quy tắc chuyển đổi đóng băng: {rule_frozen}")

        # Chạy quy tắc đóng băng trên kỳ trong mẫu để có mốc so sánh
        in_frm = datetime(2016, 1, 4, tzinfo=TZ)
        in_to = datetime(2022, 12, 31, tzinfo=TZ) + timedelta(days=1)
        res_rule_in = run_regime_switching_backtest(
            storage, symbols, rule_frozen, in_frm, in_to, args.capital, prior_regime_by_date
        )

        # Chạy quy tắc đóng băng trên kỳ ngoài mẫu
        res_rule_out = run_regime_switching_backtest(
            storage, symbols, rule_frozen, out_frm, out_to, args.capital, prior_regime_by_date
        )

        # Chạy các chiến lược đơn trên kỳ ngoài mẫu để làm mốc so sánh
        out_sample_single = {}
        for sname, factory in STRATEGIES.items():
            res = measure_strategy_on_symbols(
                storage, symbols, sname, factory, out_frm, out_to, args.capital, prior_regime_by_date
            )
            out_sample_single[sname] = res

        print("\n" + "=" * 78)
        print("KẾT QUẢ KỲ NGOÀI MẪU (2023-01-01 -> 2026-08-28)")
        print("=" * 78)
        print(f"Quy tắc đã đóng băng: {rule_frozen}")
        print(f"  PnL Quy tắc ngoài mẫu     : {res_rule_out['strat_pnl']:>18,.0f} ({res_rule_out['strat_pnl']/1e9:>+7.2f} tỷ)")
        print(f"  Lệnh / Win rate ngoài mẫu  : {res_rule_out['trades']:>6} lệnh | win {res_rule_out['win_rate']:>5.1%}")
        print(f"  Chênh lệch so với BH ngoài : {res_rule_out['diff_bh']:>18,.0f}")

        print("\nBA MỐC SO SÁNH BẮT BUỘC:")
        bh_out = res_rule_out["bh_pnl"]
        print(f"  1. Mua-và-giữ ngoài mẫu (2023->2026-08)      : {bh_out:>18,.0f} ({bh_out/1e9:>+7.2f} tỷ)")

        # Tìm chiến lược đơn tốt nhất ngoài mẫu
        best_single_name = max(out_sample_single, key=lambda k: out_sample_single[k]["total_strat_pnl"])
        best_single_pnl = out_sample_single[best_single_name]["total_strat_pnl"]
        print(f"  2. Chiến lược đơn tốt nhất ngoài mẫu ({best_single_name}) : {best_single_pnl:>18,.0f} ({best_single_pnl/1e9:>+7.2f} tỷ)")
        for sname in ["daily_breakout", "octopus_pullback", "sma_cross"]:
            s_res = out_sample_single[sname]
            print(f"     - {sname:<18} : PnL {s_res['total_strat_pnl']:>15,.0f} | lệnh {s_res['total_trades']:>5} | win {s_res['overall_win_rate']:>5.1%}")

        print(f"  3. Chính quy tắc đó trên kỳ trong mẫu (2016->2022) : {res_rule_in['strat_pnl']:>18,.0f} ({res_rule_in['strat_pnl']/1e9:>+7.2f} tỷ) | {res_rule_in['trades']} lệnh | win {res_rule_in['win_rate']:.1%}")


if __name__ == "__main__":
    main()
