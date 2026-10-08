"""Mốc chuẩn "w% ETF VN30 + phần còn lại gửi tiết kiệm" — Brief đợt 165 (ĐĂNG KÝ TRƯỚC).

Mục tiêu:
Đo lường mốc chuẩn không cần chiến lược: w phần vốn mua-và-giữ ETF E1VFVN30 và
(1 - w) gửi tiết kiệm, tái cân bằng mỗi năm một lần, sau đầy đủ phí, thuế và trượt giá.

Thiết kế ĐĂNG KÝ TRƯỚC (chốt trong brief, KHÔNG chỉnh sau khi thấy kết quả):
- IS: phiên đầu tiên của 2017 tới 30/12/2022. Gọi validate_sealed_bars (>= 2023-01-01 ném lỗi).
- Tập niêm phong: 2023-01-03 -> 30/09/2026. Chỉ mở khi có cờ --unlock-holdout và ghi log trước.
- Lưới w ∈ {5%, 10%, 15%, 20%, 25%, 30%}. Biến thể chính: w = 15%.
- Tái cân bằng chính: mỗi năm một lần (quyết định ở CLOSE phiên cuối năm, khớp ở OPEN phiên đầu năm sau).
- Biến thể phụ: không tái cân bằng.
- Chi phí (import từ trading/paper_broker.py):
  * Mua ETF: FEE_RATE + SLIP
  * Bán ETF: FEE_RATE + SELL_TAX_RATE + SLIP
  * Tiền gửi: không phí, không thuế lãi.
  * Cuối kỳ: trừ phí bán giả định phần ETF để so sánh với tiền mặt.
- Lãi tiền gửi: lãi suất r, tính lãi kép theo ngày lịch: (1 + r) ** (số_ngày_lịch / 365).
  * Chính: r = 9%. Độ nhạy: r ∈ {0%, 5%, 7%, 9%}.
"""

from __future__ import annotations

import argparse
import io
import math
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ
from trading.metrics import max_drawdown
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import SEALED_START, bar_date, clean_bars, validate_sealed_bars
from trading.storage.db import Storage

__all__ = [
    "DEFAULT_RATES",
    "DEFAULT_WEIGHTS",
    "HOLDOUT_END",
    "HOLDOUT_LOG_PATH",
    "HOLDOUT_START",
    "INITIAL_CAPITAL",
    "IS_END",
    "IS_START",
    "MAIN_RATE",
    "MAIN_REBALANCE",
    "MAIN_WEIGHT",
    "SEALED_START",
    "SYMBOL",
    "SimResult",
    "Trade",
    "build_parser",
    "cagr",
    "main",
    "per_side_rate",
    "read_is_bars",
    "simulate_mix",
    "summarize_mix",
    "unlock_holdout",
    "yearly_table",
]

# --- Tham số đăng ký trước ---------------------------------------------------------

SYMBOL = "E1VFVN30"
INITIAL_CAPITAL = 1.0
IS_START = date(2017, 1, 1)
IS_END = date(2022, 12, 30)
HOLDOUT_START = date(2023, 1, 3)
HOLDOUT_END = date(2026, 9, 30)

DEFAULT_WEIGHTS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
MAIN_WEIGHT = 0.15
DEFAULT_RATES = (0.0, 0.05, 0.07, 0.09)
MAIN_RATE = 0.09
MAIN_REBALANCE = "annual"

SLIP = SLIPPAGE_BPS / 10_000.0
HOLDOUT_LOG_PATH = Path("docs/holdout-unlock-log.md")


def per_side_rate(side: str) -> float:
    """Tỷ lệ chi phí theo chiều giao dịch (import từ trading/paper_broker.py)."""
    if side == "BUY":
        return FEE_RATE + SLIP
    return FEE_RATE + SELL_TAX_RATE + SLIP


# --- Cấu trúc dữ liệu --------------------------------------------------------------


@dataclass(slots=True)
class Trade:
    bar_index: int
    day: date
    side: str
    notional: float  # Giá trị khớp
    weight_after: float
    cost: float


@dataclass(slots=True)
class SimResult:
    label: str
    w: float
    r: float
    rebalance_mode: str  # "annual" hoặc "none"
    dates: list[date] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    etf_weights: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(t.cost for t in self.trades)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def avg_etf_weight(self) -> float:
        return statistics.fmean(self.etf_weights) if self.etf_weights else 0.0


# --- Hàm mô phỏng ------------------------------------------------------------------


def simulate_mix(
    bars: Sequence[Bar],
    w: float = MAIN_WEIGHT,
    r: float = MAIN_RATE,
    rebalance_mode: str = MAIN_REBALANCE,
    initial: float = INITIAL_CAPITAL,
    label: str | None = None,
) -> SimResult:
    """Mô phỏng danh mục w% ETF + (1-w)% tiền gửi.

    Quy tắc chi phí và lãi tiền gửi:
    - Vốn ban đầu = initial (mặc định 1.0).
    - Ngày đầu (OPEN phiên đầu): mua w * initial ETF, phần còn lại (1-w)*initial gửi tiết kiệm.
    - Tiền gửi: lãi kép theo ngày lịch giữa 2 phiên liên tiếp: (1 + r) ** (số_ngày_lịch / 365).
    - Tái cân bằng năm: quyết định ở CLOSE phiên cuối năm, khớp ở OPEN phiên đầu năm sau đưa ETF về đúng w.
    - Cuối kỳ: trừ phí bán giả định của phần ETF để so sánh tương đương với tiền mặt.
    """
    lbl = label or f"w={w*100:.0f}%_r={r*100:.0f}%_{rebalance_mode}"
    res = SimResult(label=lbl, w=w, r=r, rebalance_mode=rebalance_mode)
    if not bars:
        return res

    n_bars = len(bars)
    d_0 = bar_date(bars[0])
    px_0 = bars[0].open

    etf_alloc = w * initial
    cash = (1.0 - w) * initial
    units = etf_alloc / px_0 if px_0 > 0 else 0.0
    cost_paid = 0.0

    if w > 0.0 and units > 0:
        buy_cost = etf_alloc * per_side_rate("BUY")
        cost_paid += buy_cost
        res.trades.append(Trade(0, d_0, "BUY", etf_alloc, w, buy_cost))

    # Đóng phiên đầu
    close_0 = bars[0].close
    gross_0 = cash + units * close_0
    if n_bars == 1 and units > 0:
        exit_cost = units * close_0 * per_side_rate("SELL")
        eq_0 = gross_0 - cost_paid - exit_cost
    else:
        eq_0 = gross_0 - cost_paid

    res.dates.append(d_0)
    res.equity_curve.append(eq_0)
    res.etf_weights.append((units * close_0) / gross_0 if gross_0 > 0 else 0.0)

    # Các phiên tiếp theo
    for i in range(1, n_bars):
        d_prev = bar_date(bars[i - 1])
        d_curr = bar_date(bars[i])
        days = (d_curr - d_prev).days

        # 1. Tiền gửi sinh lãi theo số ngày lịch trước giờ mở cửa phiên i
        if days > 0 and r != 0.0:
            cash = cash * ((1.0 + r) ** (days / 365.0))

        # 2. Tái cân bằng ở OPEN phiên đầu năm mới
        if rebalance_mode == "annual" and d_curr.year > d_prev.year:
            px_open = bars[i].open
            gross_open = cash + units * px_open
            target_etf_val = w * gross_open
            curr_etf_val = units * px_open
            delta = target_etf_val - curr_etf_val

            if abs(delta) > 1e-12:
                if delta > 0:
                    side = "BUY"
                    cost = delta * per_side_rate("BUY")
                else:
                    side = "SELL"
                    cost = abs(delta) * per_side_rate("SELL")

                cost_paid += cost
                units += delta / px_open
                cash -= delta
                res.trades.append(Trade(i, d_curr, side, abs(delta), w, cost))

        # 3. Đóng phiên i
        close_px = bars[i].close
        gross_close = cash + units * close_px

        # Cuối kỳ (phiên cuối cùng): trừ phí bán giả định cho phần ETF
        if i == n_bars - 1 and units > 0:
            exit_cost = units * close_px * per_side_rate("SELL")
            eq = gross_close - cost_paid - exit_cost
        else:
            eq = gross_close - cost_paid

        res.dates.append(d_curr)
        res.equity_curve.append(eq)
        res.etf_weights.append(
            (units * close_px) / gross_close if gross_close > 0 else 0.0
        )

    return res


# --- Thống kê & Chỉ số -------------------------------------------------------------


def cagr(
    equity: Sequence[float], dates: Sequence[date], initial: float = INITIAL_CAPITAL
) -> float:
    """CAGR theo ngày lịch (365.25 ngày/năm), mốc là VỐN ĐẦU `initial` — không phải tài sản
    sau phiên đầu (đã trừ phí mua, cộng biến động ngày đầu). Sửa của Claude khi audit.
    """
    if len(equity) < 2 or initial <= 0 or equity[-1] <= 0:
        return float("nan")
    years = (dates[-1] - dates[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return (equity[-1] / initial) ** (1.0 / years) - 1.0


def year_end_equity(res: SimResult) -> list[tuple[int, float]]:
    """(năm, equity cuối năm) theo thứ tự thời gian."""
    out: list[tuple[int, float]] = []
    for d, e in zip(res.dates, res.equity_curve, strict=True):
        if out and out[-1][0] == d.year:
            out[-1] = (d.year, e)
        else:
            out.append((d.year, e))
    return out


def yearly_table(res: SimResult) -> list[tuple[int, float]]:
    """Lợi suất từng năm dương lịch (năm đầu tính từ vốn ban đầu INITIAL_CAPITAL)."""
    years = year_end_equity(res)
    if not years:
        return []
    out = [(years[0][0], years[0][1] / INITIAL_CAPITAL - 1.0)]
    for i in range(1, len(years)):
        if years[i - 1][1] > 0:
            out.append((years[i][0], years[i][1] / years[i - 1][1] - 1.0))
    return out


def summarize_mix(res: SimResult) -> dict[str, Any]:
    """Tổng hợp chỉ số theo Brief 165 §1.5."""
    eq = res.equity_curve
    if not eq:
        return {}

    c = cagr(eq, res.dates)
    excess = c - res.r if not math.isnan(c) else float("nan")
    mdd = max_drawdown(eq)

    y_tab = yearly_table(res)
    worst_year_ret = (
        min((r for _, r in y_tab), default=float("nan")) if y_tab else float("nan")
    )

    # MDD tệ nhất trong một năm dương lịch
    years = sorted({d.year for d in res.dates})
    yearly_mdds: list[float] = []
    for y in years:
        y_slice = [e for d, e in zip(res.dates, eq, strict=True) if d.year == y]
        if len(y_slice) >= 2:
            yearly_mdds.append(max_drawdown(y_slice))
        else:
            yearly_mdds.append(0.0)
    worst_year_mdd = max(yearly_mdds) if yearly_mdds else 0.0

    return {
        "w": res.w,
        "r": res.r,
        "rebalance_mode": res.rebalance_mode,
        "cagr": c,
        "excess": excess,
        "mdd": mdd,
        "worst_year_mdd": worst_year_mdd,
        "worst_year_return": worst_year_ret,
        "n_trades": float(res.n_trades),
        "total_cost": res.total_cost,
        "total_cost_pct": res.total_cost / INITIAL_CAPITAL,
        "avg_etf_weight": res.avg_etf_weight,
        "pass_mdd_4_7": mdd <= 0.047,
        "pass_mdd_7_0": mdd <= 0.070,
        "pass_cagr_9_0": c >= 0.090 if not math.isnan(c) else False,
    }


# --- Đọc dữ liệu & Niêm phong ------------------------------------------------------


def read_is_bars(storage: Any, symbol: str = SYMBOL) -> tuple[list[Bar], int]:
    """Đọc nến In-Sample (2017-01-01 -> 2022-12-30).

    Bắt buộc gọi validate_sealed_bars (ném lỗi nếu có nến >= 2023-01-01).
    """
    bars = storage.read_daily_bars(
        symbol,
        datetime(IS_START.year, IS_START.month, IS_START.day, tzinfo=TZ),
        datetime(2022, 12, 31, tzinfo=TZ),
    )
    clean, n_dropped = clean_bars(bars)
    validate_sealed_bars(clean)
    return clean, n_dropped


def _append_holdout_log(log_path: Path, symbol: str) -> None:
    """Ghi một dòng vào log niêm phong trước khi mở khóa."""
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"| {now_str} | Mốc chuẩn ETF + tiền gửi (đợt 165) | "
        f"w=15%, rebalance=annual, r=9% & r=0% | "
        f"Đánh giá mốc chuẩn tham chiếu trên tập niêm phong sau khi audit IS ({symbol}) |\n"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


def unlock_holdout(
    storage: Any,
    symbol: str = SYMBOL,
    log_path: Path = HOLDOUT_LOG_PATH,
    unlocked: bool = False,
) -> tuple[list[Bar], int]:
    """Đọc tập niêm phong (2023-01-03 -> 2026-09-30).

    - Bắt buộc có cờ unlocked=True mới được mở.
    - Ghi một dòng vào log_path TRƯỚC KHI đọc dữ liệu.
    """
    if not unlocked:
        raise PermissionError(
            "Tập niêm phong (holdout) 2023-2026 chỉ được mở khi có cờ tường minh --unlock-holdout."
        )

    # Ghi log TRƯỚC KHI đọc dữ liệu
    _append_holdout_log(log_path, symbol)

    bars = storage.read_daily_bars(
        symbol,
        datetime(HOLDOUT_START.year, HOLDOUT_START.month, HOLDOUT_START.day, tzinfo=TZ),
        datetime(2026, 10, 1, tzinfo=TZ),
    )
    clean, n_dropped = clean_bars(bars)
    return clean, n_dropped


# --- In bảng báo cáo ---------------------------------------------------------------


def fmt_pct(x: float, nd: int = 2) -> str:
    return "n/a" if math.isnan(x) else f"{x * 100:.{nd}f}%"


def fmt_pass(p: bool) -> str:
    return "ĐẠT" if p else "K.ĐẠT"


def print_main_table(summaries: list[dict[str, Any]]) -> None:
    print(
        f"{'w':<6} {'Tái cân bằng':<14} {'CAGR':>8} {'Vượt r':>8} {'MDD':>8} "
        f"{'MDD năm tệ':>12} {'Năm tệ':>8} {'GD':>4} {'Tổng phí':>9} "
        f"{'MDD<=4.7%':>10} {'MDD<=7%':>8} {'CAGR>=9%':>9}"
    )
    print("-" * 115)
    for s in summaries:
        w_str = f"{s['w']*100:.0f}%"
        reb_str = "Hàng năm" if s["rebalance_mode"] == "annual" else "Không"
        print(
            f"{w_str:<6} {reb_str:<14} {fmt_pct(s['cagr']):>8} {fmt_pct(s['excess']):>8} "
            f"{fmt_pct(s['mdd']):>8} {fmt_pct(s['worst_year_mdd']):>12} "
            f"{fmt_pct(s['worst_year_return']):>8} {int(s['n_trades']):>4} "
            f"{s['total_cost_pct']*100:>8.3f}% "
            f"{fmt_pass(s['pass_mdd_4_7']):>10} {fmt_pass(s['pass_mdd_7_0']):>8} "
            f"{fmt_pass(s['pass_cagr_9_0']):>9}"
        )


def print_sensitivity_table(summaries: list[dict[str, Any]]) -> None:
    print(
        f"{'w':<6} {'r':>6} {'CAGR':>8} {'Vượt r':>8} {'MDD':>8} "
        f"{'Năm tệ':>8} {'MDD<=4.7%':>10} {'MDD<=7%':>8} {'CAGR>=9%':>9}"
    )
    print("-" * 75)
    for s in summaries:
        w_str = f"{s['w']*100:.0f}%"
        r_str = f"{s['r']*100:.0f}%"
        print(
            f"{w_str:<6} {r_str:>6} {fmt_pct(s['cagr']):>8} {fmt_pct(s['excess']):>8} "
            f"{fmt_pct(s['mdd']):>8} {fmt_pct(s['worst_year_return']):>8} "
            f"{fmt_pass(s['pass_mdd_4_7']):>10} {fmt_pass(s['pass_mdd_7_0']):>8} "
            f"{fmt_pass(s['pass_cagr_9_0']):>9}"
        )


def print_yearly_breakdown(res_main: SimResult, r: float = MAIN_RATE) -> None:
    y_tab = yearly_table(res_main)
    print(
        f"{'Năm':<6} {'Lợi nhuận':>12} {'Tiền gửi (r=9%)':>16} {'Chênh lệch':>12} {'MDD trong năm':>14}"
    )
    print("-" * 64)
    for y, ret in y_tab:
        # Slice mdd của năm đó
        y_slice = [
            e
            for d, e in zip(res_main.dates, res_main.equity_curve, strict=True)
            if d.year == y
        ]
        y_mdd = max_drawdown(y_slice) if len(y_slice) >= 2 else 0.0
        diff = ret - r
        print(
            f"{y:<6} {fmt_pct(ret):>12} {fmt_pct(r):>16} {fmt_pct(diff):>12} {fmt_pct(y_mdd):>14}"
        )


# --- CLI Main ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Đo mốc chuẩn w% ETF VN30 + (1-w)% tiền gửi (Brief 165)"
    )
    p.add_argument(
        "--dsn", default=None, help="Postgres DSN (mặc định từ biến môi trường)"
    )
    p.add_argument("--symbol", default=SYMBOL, help="Mã ETF (mặc định E1VFVN30)")
    p.add_argument(
        "--unlock-holdout",
        action="store_true",
        help="Mở khóa dữ liệu niêm phong 2023-2026",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t0 = time.perf_counter()
    storage = Storage(resolve_dsn(args.dsn))

    if args.unlock_holdout:
        print(f"# MỞ KHÓA TẬP NIÊM PHONG (HOLDOUT) CHO MÃ {args.symbol}")
        bars, n_junk = unlock_holdout(
            storage, args.symbol, log_path=HOLDOUT_LOG_PATH, unlocked=True
        )
        period_label = "HOLDOUT (2023-01-03 -> 2026-09-30)"
    else:
        bars, n_junk = read_is_bars(storage, args.symbol)
        period_label = "IN-SAMPLE (2017-01-03 -> 2022-12-30)"

    if not bars:
        print(f"LỖI: Không có nến nào cho {args.symbol}", file=sys.stderr)
        return 2

    dates = [bar_date(b) for b in bars]
    print(
        f"# {args.symbol}: {len(bars)} phiên ({dates[0]} -> {dates[-1]}), bỏ {n_junk} phiên giá <= 0"
    )
    print(f"# Giai đoạn: {period_label}")
    print()

    if args.unlock_holdout:
        # Brief 165 §1.6: tập niêm phong CHỈ hai cấu hình đã chốt, không in lưới (sửa của Claude).
        hold = [
            summarize_mix(
                simulate_mix(bars, w=MAIN_WEIGHT, r=rr, rebalance_mode=MAIN_REBALANCE)
            )
            for rr in (MAIN_RATE, 0.0)
        ]
        print_sensitivity_table(hold)
        return 0

    # 1. Bảng chính: w ∈ {5%, 10%, 15%, 20%, 25%, 30%} × {annual, none} với r = 9%
    print("## 1. BẢNG CHÍNH: CÁC TỔ HỢP w × TÁI CÂN BẰNG (r = 9% CỐ ĐỊNH)")
    main_summaries = []
    main_res_instance = None
    for reb in ("annual", "none"):
        for w in DEFAULT_WEIGHTS:
            res = simulate_mix(bars, w=w, r=MAIN_RATE, rebalance_mode=reb)
            if reb == MAIN_REBALANCE and math.isclose(w, MAIN_WEIGHT, abs_tol=1e-5):
                main_res_instance = res
            main_summaries.append(summarize_mix(res))

    print_main_table(main_summaries)
    print()

    # 2. Bảng độ nhạy: w × r (r ∈ {0%, 5%, 7%, 9%}) với tái cân bằng hàng năm
    print("## 2. BẢNG ĐỘ NHẠY THEO LÃI SUẤT TIỀN GỬI r (TÁI CÂN BẰNG HÀNG NĂM)")
    sens_summaries = []
    for r in DEFAULT_RATES:
        for w in DEFAULT_WEIGHTS:
            res = simulate_mix(bars, w=w, r=r, rebalance_mode="annual")
            sens_summaries.append(summarize_mix(res))

    print_sensitivity_table(sens_summaries)
    print()

    # 3. Bảng chi tiết từng năm cho biến thể chính (w = 15%, annual, r = 9%)
    if main_res_instance is not None:
        print(
            "## 3. CHI TIẾT TỪNG NĂM CỦA BIẾN THỂ CHÍNH (w = 15%, TÁI CÂN BẰNG HÀNG NĂM, r = 9%)"
        )
        print_yearly_breakdown(main_res_instance, r=MAIN_RATE)
        print()

    elapsed = time.perf_counter() - t0
    print(f"# Hoàn thành đo lường trong {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
