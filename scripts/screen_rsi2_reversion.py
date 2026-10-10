"""Mua quá bán RSI(2) trong xu hướng tăng, cổ phiếu VN nến ngày — Brief đợt 177 (ĐĂNG KÝ TRƯỚC).

THIẾT KẾ ĐĂNG KÝ TRƯỚC (chốt trong brief, KHÔNG đổi sau khi thấy số):
- Dữ liệu/universe/niêm phong: Giống hệt đợt 175 §1.1 — `bars_daily`, `load_universe(storage,
  "exclusions.txt")`, chỉ mã cổ phiếu (`stock_symbols`), bỏ nến giá <= 0, đọc bằng `read_bars`
  của `screen_pullback_trend` (có cổng niêm phong: nến >= 2023-01-01 thì NÉM LỖI).
  IS = mọi tín hiệu có ngày tín hiệu trong 2017-01-01 -> 2022-11-30 (2016 làm nóng MA200).
- RSI(2) tính theo làm trơn Wilder n = 2 (§1.2).
- Tín hiệu mua (tại CLOSE phiên t, chỉ dùng dữ liệu <= t), đủ cả bốn điều kiện:
  1. thanh khoản: `liquidity_ok(bars, t, window=20, min_turnover=2 tỷ)`;
  2. close[t] > MA200[t] (SMA 200 phiên kết thúc tại t);
  3. RSI2[t] < 10;
  4. không đang giữ mã đó (phiên thoát cũng tính là đang giữ).
- Vào lệnh: mua ở OPEN phiên t+1; `entry_status` khác "ok" thì bỏ. E = t+1.
- Thoát: kiểm tại CLOSE mỗi phiên d >= E (kể cả d = E):
  1. hồi phục: close[d] > MA5[d];
  2. hết giờ: d = E + 9 (giữ tối đa 10 phiên).
  Ràng buộc T+2: phiên thoát = max(d+1, E+2). Thoát rơi vào nến volume == 0 thì lùi tiếp.
- Đánh giá: 5 điều kiện (4 điều kiện của evaluate + điều kiện 5 bỏ 1% lệnh lãi nhất).
"""

from __future__ import annotations

import argparse
import io
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Chạy trực tiếp `python scripts/...` phải import được `scripts.*`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_momentum_portfolio import (
    block_bootstrap,
    round_trip_cost,
    stock_symbols,
)
from scripts.screen_pullback_trend import (
    MIN_TURNOVER,
    TURNOVER_WINDOW,
    ew_returns_by_date,
    excess_of_trade,
    monthly_excess,
    read_bars,
)
from trading.metrics import profit_factor
from trading.models import Bar
from trading.stock_study import (
    bar_date,
    entry_status,
    liquidity_ok,
    load_universe,
    net_return,
)
from trading.storage.db import Storage

__all__ = [
    "BLOCK_MONTHS",
    "BOOTSTRAP_SEED",
    "IS_END",
    "IS_START",
    "MAX_HOLD",
    "MA_EXIT",
    "MA_LONG",
    "MIN_TURNOVER",
    "N_BOOTSTRAP",
    "RSI_PERIOD",
    "RSI_THRESHOLD",
    "TURNOVER_WINDOW",
    "WIN_THRESHOLD",
    "compute_rsi2",
    "evaluate",
    "ew_returns_by_date",
    "excess_of_trade",
    "find_signal",
    "main",
    "monthly_excess",
    "read_bars",
    "simulate_symbol",
]

# --- Tham số đăng ký trước ---------------------------------------------------------

RSI_PERIOD = 2
RSI_THRESHOLD = 10.0
MA_LONG = 200
MA_EXIT = 5
MAX_HOLD = 10  # d = E+9 (tối đa 10 phiên)
WIN_THRESHOLD = 300
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 42
BLOCK_MONTHS = 3

IS_START = date(2017, 1, 1)
IS_END = date(2022, 11, 30)


# --- Tính toán chỉ báo --------------------------------------------------------------


def compute_rsi2(closes: list[float]) -> list[float | None]:
    """Tính RSI(2) theo làm trơn Wilder (Brief đợt 177 §1.2).

    - Δ_i = close[i] - close[i-1]
    - U_i = max(Δ_i, 0), D_i = max(-Δ_i, 0)
    - Khởi tạo tại i = 2: AU = (U_1 + U_2)/2, AD = (D_1 + D_2)/2
    - Sau đó: AU_i = (AU_{i-1} + U_i) / 2, AD_i = (AD_{i-1} + D_i) / 2 (vì n = 2)
    - RSI = 100 nếu AD == 0; ngược lại 100 - 100 / (1 + AU / AD)
    - Trả về list[float | None], len bằng len(closes). Với i < 2: None.
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < 3:
        return out

    u1 = max(closes[1] - closes[0], 0.0)
    d1 = max(closes[0] - closes[1], 0.0)

    u2 = max(closes[2] - closes[1], 0.0)
    d2 = max(closes[1] - closes[2], 0.0)

    au = (u1 + u2) / 2.0
    ad = (d1 + d2) / 2.0

    if ad == 0.0:
        out[2] = 100.0
    else:
        out[2] = 100.0 - 100.0 / (1.0 + au / ad)

    for i in range(3, n):
        ui = max(closes[i] - closes[i - 1], 0.0)
        di = max(closes[i - 1] - closes[i], 0.0)

        au = (au + ui) / 2.0
        ad = (ad + di) / 2.0

        if ad == 0.0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + au / ad)

    return out


def _precompute_sma(closes: list[float], period: int) -> list[float | None]:
    """Tiền tính SMA n phiên kết thúc tại từng phiên (để chạy nhanh)."""
    n = len(closes)
    out: list[float | None] = [None] * n
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= period:
            s -= closes[i - period]
        if i + 1 >= period:
            out[i] = s / period
    return out


def _sma(closes: list[float], t: int, n: int) -> float | None:
    """SMA n phiên kết thúc tại t."""
    if t + 1 < n:
        return None
    return statistics.fmean(closes[t - n + 1 : t + 1])


# --- Tín hiệu mua -------------------------------------------------------------------


def find_signal(
    bars: list[Bar],
    t: int,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Kiểm tra điều kiện mua tại CLOSE phiên t (§1.3).

    Chỉ dùng dữ liệu <= t:
    1. liquidity_ok(bars, t, window=20, min_turnover=2 tỷ);
    2. close[t] > MA200[t];
    3. RSI2[t] < 10.
    """
    if t < 2:
        return None

    if not liquidity_ok(bars, t, window=TURNOVER_WINDOW, min_turnover=MIN_TURNOVER):
        return None

    if ctx is not None:
        closes = ctx["closes"]
        ma200_val = ctx["ma200"][t]
        rsi2_val = ctx["rsi2"][t]
    else:
        closes = [b.close for b in bars]
        ma200_val = _sma(closes, t, MA_LONG)
        rsi_series = compute_rsi2(closes[: t + 1])
        rsi2_val = rsi_series[t]

    if ma200_val is None or closes[t] <= ma200_val:
        return None

    if rsi2_val is None or rsi2_val >= RSI_THRESHOLD:
        return None

    return {
        "rsi2": rsi2_val,
        "ma200": ma200_val,
        "close": closes[t],
    }


# --- Thoát lệnh --------------------------------------------------------------------


def _find_exit(
    bars: list[Bar],
    E: int,
    closes: list[float],
    ma5: list[float | None],
) -> tuple[int, str]:
    """Tìm phiên thoát theo thứ tự ưu tiên (§1.5).

    Kiểm tra tại CLOSE mỗi phiên d >= E (kể cả E):
    1. Hồi phục: close[d] > MA5[d]
    2. Hết giờ: d = E + 9 (giữ tối đa 10 phiên)

    T+2: phiên thoát = max(d + 1, E + 2).
    Nếu rơi vào nến volume == 0 thì lùi tiếp tới phiên có giao dịch.
    """
    n = len(bars)
    exit_target: int | None = None
    exit_reason = ""

    max_d = min(E + MAX_HOLD - 1, n - 1)
    for d in range(E, max_d + 1):
        # 1. Hồi phục
        m5 = ma5[d]
        if m5 is not None and closes[d] > m5:
            exit_reason = "hoi_phuc"
            exit_target = max(d + 1, E + 2)
            break
        # 2. Hết giờ
        if d == E + MAX_HOLD - 1:
            exit_reason = "het_gio"
            exit_target = max(d + 1, E + 2)
            break

    if exit_target is None:
        exit_reason = "het_gio"
        exit_target = max(max_d + 1, E + 2)

    # Lùi nếu rơi vào nến volume == 0
    exit_i = exit_target
    while exit_i < n and bars[exit_i].volume == 0:
        exit_i += 1
    if exit_i >= n:
        exit_i = n - 1

    return exit_i, exit_reason


# --- Mô phỏng một mã --------------------------------------------------------------


def simulate_symbol(
    bars: list[Bar],
    symbol: str,
    exchange: str = "HOSE",
    is_start: date | None = IS_START,
    is_end: date | None = IS_END,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Mô phỏng giao dịch một mã cổ phiếu (§1.3 - §1.5)."""
    if not bars:
        return []

    closes = [b.close for b in bars]
    rsi2 = compute_rsi2(closes)
    ma200 = _precompute_sma(closes, MA_LONG)
    ma5 = _precompute_sma(closes, MA_EXIT)
    ctx = {"closes": closes, "rsi2": rsi2, "ma200": ma200, "ma5": ma5}

    trades: list[dict[str, Any]] = []
    n = len(bars)
    t = 0
    while t < n - 1:
        sig = find_signal(bars, t, ctx)
        d_t = bar_date(bars[t])
        if sig is None or (is_start and d_t < is_start) or (is_end and d_t > is_end):
            t += 1
            continue

        st = entry_status(bars, t, exchange)
        if st != "ok":
            if stats is not None:
                stats[st] = stats.get(st, 0) + 1
            t += 1
            continue

        E = t + 1
        exit_i, reason = _find_exit(bars, E, closes, ma5)
        trades.append(
            {
                "symbol": symbol,
                "entry_i": E,
                "exit_i": exit_i,
                "entry_date": bar_date(bars[E]),
                "exit_date": bar_date(bars[exit_i]),
                "entry_price": bars[E].open,
                "exit_price": bars[exit_i].close,
                "reason": reason,
                "hold": exit_i - E,
                "net": net_return(bars[E].open, bars[exit_i].close),
            }
        )
        # Phiên thoát cũng tính là đang giữ -> tín hiệu mới chỉ xét từ exit_i + 1
        t = exit_i + 1

    return trades


# --- Phép thử & Đánh giá 5 điều kiện -----------------------------------------------


def evaluate(trades: list[dict[str, Any]], series: list[float]) -> dict[str, Any]:
    """Đánh giá 5 điều kiện đăng ký trước (§1.6).

    1. >= 300 lệnh;
    2. p < 0.05 một phía và trung bình vượt trội tháng > 0;
    3. TB ròng mỗi lệnh >= 0.5 * cost_rt;
    4. profit factor ròng > 1.2;
    5. Vượt trội trung bình tính theo trọng số lệnh > 0 sau khi bỏ 1% lệnh có lợi nhuận ròng cao nhất.
    """
    cost_rt = round_trip_cost()
    nets = [t["net"] for t in trades]
    mean_net = statistics.fmean(nets) if nets else 0.0
    pf = profit_factor(nets)
    boot = (
        block_bootstrap(
            series, n_boot=N_BOOTSTRAP, seed=BOOTSTRAP_SEED, block=BLOCK_MONTHS
        )
        if series
        else {
            "mean": 0.0,
            "median": 0.0,
            "p": 1.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "n_months": 0,
        }
    )
    cond1 = len(trades) >= WIN_THRESHOLD
    cond2 = boot["p"] < 0.05 and boot["mean"] > 0
    cond3 = mean_net >= 0.5 * cost_rt
    cond4 = pf is not None and pf > 1.2

    # Điều kiện 5: Bỏ 1% lệnh có net return cao nhất
    if trades:
        sorted_by_net = sorted(trades, key=lambda tr: tr["net"])
        k_trim = max(1, int(len(trades) * 0.01))
        trimmed_trades = (
            sorted_by_net[:-k_trim] if k_trim < len(sorted_by_net) else []
        )
        mean_excess_trimmed = (
            statistics.fmean(tr["excess"] for tr in trimmed_trades)
            if trimmed_trades
            else 0.0
        )
        cond5 = mean_excess_trimmed > 0.0
    else:
        mean_excess_trimmed = 0.0
        cond5 = False

    dat = cond1 and cond2 and cond3 and cond4 and cond5
    return {
        "n_trades": len(trades),
        "n_months": len(series),
        "mean_excess": boot["mean"],
        "median_excess": boot["median"],
        "p": boot["p"],
        "ci_low": boot["ci_low"],
        "ci_high": boot["ci_high"],
        "mean_net": mean_net,
        "cost_rt": cost_rt,
        "profit_factor": pf if pf is not None else float("nan"),
        "mean_excess_trimmed": mean_excess_trimmed,
        "cond1": cond1,
        "cond2": cond2,
        "cond3": cond3,
        "cond4": cond4,
        "cond5": cond5,
        "dat": dat,
        "thieu_suc_manh": len(trades) < WIN_THRESHOLD,
    }


# --- Hàm chạy chính (CLI) ----------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sàng lọc chiến lược quá bán RSI(2) trên MA200 (Brief đợt 177)"
    )
    parser.add_argument(
        "--universe",
        default="exclusions.txt",
        help="Đường dẫn file exclusions.txt (mặc định exclusions.txt)",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="Lọc sàn giao dịch cụ thể (ví dụ HOSE, HNX)",
    )
    args = parser.parse_args()

    print("=" * 84)
    print("  BRIEF ĐỢT 177 — QUÁ BÁN RSI(2) TRÊN MA200, NẾN NGÀY CỔ PHIẾU VN")
    print(f"  Khoảng thời gian IS: {IS_START} -> {IS_END} (2016 làm nóng MA200)")
    print("=" * 84)

    storage = Storage(resolve_dsn())
    universe, exchanges, _n_all, _excluded = load_universe(storage, args.universe)
    symbols, _ = stock_symbols(universe)
    if args.exchange:
        symbols = [s for s in symbols if exchanges.get(s, "") == args.exchange]
    symbols = sorted(symbols)

    print(f"\n[1/4] Đọc dữ liệu {len(symbols)} mã cổ phiếu...")
    t0 = time.time()
    by_symbol: dict[str, list[Bar]] = {}
    tot_dropped = 0
    for sym in symbols:
        bars, n_drop = read_bars(storage, sym)
        if bars:
            by_symbol[sym] = bars
            tot_dropped += n_drop
    print(
        f"  Đã nạp {len(by_symbol)} mã có dữ liệu ({tot_dropped} nến lỗi bị bỏ) trong {time.time()-t0:.2f}s."
    )

    print("\n[2/4] Mô phỏng tín hiệu & vào/thoát lệnh...")
    all_trades: list[dict[str, Any]] = []
    stats: dict[str, int] = defaultdict(int)
    for sym, bars in by_symbol.items():
        ex = exchanges.get(sym, "HOSE")
        trs = simulate_symbol(
            bars, sym, exchange=ex, is_start=IS_START, is_end=IS_END, stats=stats
        )
        all_trades.extend(trs)
    all_trades.sort(key=lambda tr: (tr["entry_date"], tr["symbol"]))
    print(f"  Tổng số lệnh sinh ra trong IS: {len(all_trades)}")

    print("\n[3/4] Tính mốc so sánh Equal-Weight (EW) & vượt trội từng lệnh...")
    ew = ew_returns_by_date(by_symbol)
    for tr in all_trades:
        tr["excess"] = excess_of_trade(tr, ew)

    series = monthly_excess(all_trades)
    print(f"  Số tháng có giao dịch: {len(series)}")

    print("\n[4/4] Đánh giá 5 điều kiện đăng ký trước...")
    res = evaluate(all_trades, series)

    # In kết quả đánh giá 5 điều kiện
    print("\n" + "=" * 84)
    print("  KẾT QUẢ ĐÁNH GIÁ 5 ĐIỀU KIỆN ĐĂNG KÝ TRƯỚC:")
    print("=" * 84)
    print(
        f"  1. Số lệnh >= 300                 : {res['n_trades']:>6} lệnh "
        f"[{'ĐẠT' if res['cond1'] else 'KHÔNG ĐẠT'}]"
    )
    print(
        f"  2. Bootstrap p < 0.05 & excess > 0 : p={res['p']:.4f}, mean={res['mean_excess']*100:+.2f}% "
        f"(95% CI [{res['ci_low']*100:+.2f}%, {res['ci_high']*100:+.2f}%]) "
        f"[{'ĐẠT' if res['cond2'] else 'KHÔNG ĐẠT'}]"
    )
    print(
        f"  3. TB ròng >= 0.5 * cost_rt       : {res['mean_net']*100:+.2f}% vs {0.5*res['cost_rt']*100:+.2f}% "
        f"[{'ĐẠT' if res['cond3'] else 'KHÔNG ĐẠT'}]"
    )
    print(
        f"  4. Profit factor ròng > 1.2       : {res['profit_factor']:.2f} "
        f"[{'ĐẠT' if res['cond4'] else 'KHÔNG ĐẠT'}]"
    )
    print(
        f"  5. Vượt trội TB (bỏ 1% lãi nhất)  : {res['mean_excess_trimmed']*100:+.2f}% > 0 "
        f"[{'ĐẠT' if res['cond5'] else 'KHÔNG ĐẠT'}]"
    )
    print("-" * 84)
    if res["dat"]:
        print("  >>> KẾT LUẬN CHUNG: ĐẠT CẢ 5 ĐIỀU KIỆN! <<<")
    else:
        if res["thieu_suc_manh"]:
            print("  >>> KẾT LUẬN CHUNG: THIẾU SỨC MẠNH (< 300 lệnh) <<<")
        else:
            print("  >>> KẾT LUẬN CHUNG: KHÔNG ĐẠT! <<<")
    print("=" * 84)

    # Thống kê bổ sung (§1.7)
    if all_trades:
        print("\n--- THỐNG KÊ MÔ TẢ BỔ SUNG (§1.7) ---")
        # 1. Phân phối số ngày giữ & lý do thoát
        holds = [t["hold"] for t in all_trades]
        n_hp = sum(1 for t in all_trades if t["reason"] == "hoi_phuc")
        n_hg = sum(1 for t in all_trades if t["reason"] == "het_gio")
        print("\n* Phân phối số ngày giữ & Lý do thoát:")
        print(
            f"  - Số ngày giữ: Min={min(holds)}, Trung vị={statistics.median(holds):.1f}, "
            f"Mean={statistics.fmean(holds):.1f}, Max={max(holds)}"
        )
        print(
            f"  - Thoát do Hồi phục (MA5) : {n_hp:>5} lệnh ({n_hp/len(all_trades)*100:5.1f}%)"
        )
        print(
            f"  - Thoát do Hết giờ (10 phiên): {n_hg:>5} lệnh ({n_hg/len(all_trades)*100:5.1f}%)"
        )

        # 2. Vị thế mở đồng thời theo ngày
        # Gom các ngày từ entry_date tới exit_date
        date_pos_count: dict[date, int] = defaultdict(int)
        for tr in all_trades:
            # Ước tính các ngày trong khoảng
            ed = tr["entry_date"]
            xd = tr["exit_date"]
            for d in sorted(ew.keys()):
                if ed <= d <= xd:
                    date_pos_count[d] += 1
        pos_counts = list(date_pos_count.values()) if date_pos_count else [0]
        print("\n* Số vị thế mở đồng thời theo ngày giao dịch:")
        print(
            f"  - Min: {min(pos_counts)}, Trung vị: {statistics.median(pos_counts):.1f}, Max: {max(pos_counts)}"
        )

        # 3. Kết quả theo năm
        print("\n* Kết quả theo năm:")
        print(
            f"  {'Năm':<6} | {'Số lệnh':<8} | {'TB ròng':<10} | {'TB vượt trội':<12}"
        )
        print("  " + "-" * 42)
        by_year: dict[int, list[dict]] = defaultdict(list)
        for tr in all_trades:
            by_year[tr["entry_date"].year].append(tr)
        for yr in sorted(by_year.keys()):
            y_trs = by_year[yr]
            y_net = statistics.fmean(t["net"] for t in y_trs)
            y_exc = statistics.fmean(t["excess"] for t in y_trs)
            print(
                f"  {yr:<6} | {len(y_trs):<8} | {y_net*100:>+8.2f}% | {y_exc*100:>+10.2f}%"
            )

        # 4. 10 lệnh lỗ nặng nhất & tỷ lệ lệnh lỗ > 10%
        n_loss_10 = sum(1 for t in all_trades if t["net"] < -0.10)
        print(
            f"\n* Tỷ lệ lệnh lỗ hơn 10%: {n_loss_10}/{len(all_trades)} ({n_loss_10/len(all_trades)*100:.1f}%)"
        )
        print("* 10 lệnh lỗ nặng nhất:")
        sorted_losses = sorted(all_trades, key=lambda t: t["net"])
        for i, tr in enumerate(sorted_losses[:10], 1):
            print(
                f"   {i:>2}. Mã {tr['symbol']:<5} | Vào {tr['entry_date']} -> Ra {tr['exit_date']} "
                f"| Net: {tr['net']*100:>+6.2f}% | Vượt trội: {tr['excess']*100:>+6.2f}% | Lý do: {tr['reason']}"
            )

        # 5. Tín hiệu bị bỏ do giá trần
        print(
            f"\n* Số tín hiệu bị bỏ do giá trần / không vào được: {stats.get('ceiling', 0) + stats.get('no_volume', 0)} "
            f"(Trần: {stats.get('ceiling', 0)}, Khối lượng 0: {stats.get('no_volume', 0)})"
        )

    print("\n" + "=" * 84)
    print("  CẢNH BÁO BẮT BUỘC:")
    print(
        "  1. THIÊN LỆCH SỐNG SÓT: Dữ liệu thiếu mã đã hủy niêm yết — điều này thổi phồng"
    )
    print(
        "     chiến lược mua khi giảm nhiều nhất vì các mã giảm rồi chết đã biến mất."
    )
    print(
        "  2. ĐA SO SÁNH: Đây là giả thuyết thứ 7 trong tháng 10/2026. Với mức alpha=0.05,"
    )
    print(
        "     xác suất có ít nhất một kết quả dương do may rủi lên tới ~30%."
    )
    print("=" * 84)


if __name__ == "__main__":
    main()
