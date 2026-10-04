"""So qty ATR(14) daily với qty GARCH(1,1) trên cùng các tín hiệu BUY (bước 2, GARCH).

Câu hỏi: ở thang daily, thay ATR(14) bằng sigma dự báo GARCH có đổi qty đáng kể
không? Chỉ ĐỌC DB, không so PnL (n tín hiệu quá nhỏ để so PnL/Sharpe).

Cách đo không chép công thức sizing (bài học 4ea4c8d): cả hai qty đều do chính
`RiskManager.approve_sized` tính — ATR dùng atr của chiến lược, GARCH dùng
atr = sigma_dự_báo × giá (quy sigma log-return về đơn vị giá, cùng đơn vị ATR).
Mỗi qty được tính hai bản: có trần 20% (qty THỰC SỰ được đặt) và gỡ trần.

Tiêu chí chốt TRƯỚC khi đo: độ lệch tương đối trung vị |qty_garch/qty_atr - 1| của
qty THỰC (sau trần) < 15% thì dừng hướng GARCH — ATR daily đã đủ. Lớn hơn mới bàn
việc nối vào engine. Bản gỡ trần chỉ để tham khảo.

CLI (chạy từ gốc repo):
    uv run python scripts/measure_garch_vs_atr_qty.py [--symbols HPG,IJC,AAA]
        [--strategy octopus_pullback] [--capital 100000000] [--min-obs 500]
        [--config config/config.yaml] [--dsn ...]
"""

import argparse
import dataclasses
import statistics
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.backtest import STRATEGIES, run_backtest
from trading.broker import Position
from trading.calendar_vn import TZ
from trading.garch_vol import DEFAULT_MIN_OBS, daily_log_returns, sigma_asof
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategy import Signal
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

THRESHOLD = 0.15
_NO_CAP = 1e9


@dataclasses.dataclass
class SignalProbeRiskManager(RiskManager):
    """RiskManager thật + ghi lại ngữ cảnh mỗi tín hiệu BUY (mã, ngày, giá, ATR)."""

    def __post_init__(self) -> None:
        self.calls: list[dict] = []

    def approve_sized(
        self,
        signal: Signal,
        ref_price: float,
        atr: float | None,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> Signal | None:
        if signal.side == "BUY":
            self.calls.append(
                {"symbol": signal.symbol, "today": today, "price": ref_price, "atr": atr}
            )
        return super().approve_sized(
            signal, ref_price, atr, positions, daily_pnl, today
        )


def load_holidays(config_path: str) -> set[date]:
    """Đọc `holidays` thẳng từ yaml — KHÔNG dùng load_config (đòi đủ biến SSI_*)."""
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {date.fromisoformat(str(h)) for h in raw.get("holidays", [])}


def _qty(risk: RiskManager, symbol: str, price: float, atr: float, today: date) -> int:
    out = risk.approve_sized(Signal(symbol, "BUY", 100), price, atr, {}, 0.0, today)
    return out.qty if out else 0


def compare_sizing(
    calls: Sequence[dict],
    bars_by_symbol: dict[str, list[Bar]],
    holidays: set[date],
    capital: float,
    min_obs: int,
) -> list[dict]:
    """Với mỗi tín hiệu: qty theo ATR và theo GARCH (có/không trần). Bỏ tín hiệu
    thiếu ATR hoặc thiếu dự báo GARCH, ghi lý do vào `skipped`."""
    capped = RiskManager(capital=capital)
    uncapped = RiskManager(capital=capital, max_order_value_pct=_NO_CAP)
    rows: list[dict] = []
    for c in calls:
        row = {**c, "skipped": None}
        rows.append(row)
        if c["atr"] is None or c["atr"] <= 0:
            row["skipped"] = "thiếu ATR"
            continue
        sigma = sigma_asof(bars_by_symbol[c["symbol"]], c["today"], holidays, min_obs)
        if sigma is None:
            row["skipped"] = "thiếu dự báo GARCH"
            continue
        garch_atr = sigma * c["price"]
        row["sigma"] = sigma
        row["atr_pct"] = c["atr"] / c["price"]
        for tag, rm in (("eff", capped), ("raw", uncapped)):
            row[f"qty_atr_{tag}"] = _qty(rm, c["symbol"], c["price"], c["atr"], c["today"])
            row[f"qty_garch_{tag}"] = _qty(rm, c["symbol"], c["price"], garch_atr, c["today"])
    return rows


def _deviations(rows: Sequence[dict], tag: str) -> list[float]:
    return [
        abs(r[f"qty_garch_{tag}"] / r[f"qty_atr_{tag}"] - 1)
        for r in rows
        if r["skipped"] is None and r[f"qty_atr_{tag}"] > 0
    ]


def _calibrated_deviations(rows: Sequence[dict], tag: str) -> list[float]:
    """|tỷ lệ qty_garch/qty_atr chia cho trung vị tỷ lệ - 1|: bỏ chênh MỨC.

    ATR (biên độ high-low) lớn hơn độ lệch chuẩn close-to-close một cách hệ thống, nên
    GARCH cho qty lớn hơn ATR ở mọi tín hiệu — chênh mức đó atr_multiplier hấp thụ được.
    Phần GARCH thật sự thêm là độ phân tán của tỷ lệ quanh mức trung vị."""
    ratios = [
        r[f"qty_garch_{tag}"] / r[f"qty_atr_{tag}"]
        for r in rows
        if r["skipped"] is None and r[f"qty_atr_{tag}"] > 0
    ]
    if not ratios:
        return []
    mid = statistics.median(ratios)
    return [abs(x / mid - 1) for x in ratios]


def format_report(rows: Sequence[dict], depth: dict[str, tuple[int, int]]) -> str:
    lines = ["Độ sâu dữ liệu (số bar daily / số return 1 ngày dùng được):"]
    for sym, (n_bars, n_ret) in sorted(depth.items()):
        lines.append(f"  {sym}: {n_bars} bar / {n_ret} return")
    lines.append(
        f"{'Ngày':<12}{'Mã':<6}{'ATR%':>7}{'GARCH%':>8}"
        f"{'qty_ATR':>9}{'qty_GARCH':>11}{'(sau trần)':>12}"
    )
    for r in rows:
        if r["skipped"]:
            lines.append(f"{r['today']!s:<12}{r['symbol']:<6}  bỏ qua: {r['skipped']}")
            continue
        lines.append(
            f"{r['today']!s:<12}{r['symbol']:<6}{r['atr_pct']:>7.2%}{r['sigma']:>8.2%}"
            f"{r['qty_atr_raw']:>9}{r['qty_garch_raw']:>11}"
            f"{r['qty_atr_eff']:>7}→{r['qty_garch_eff']:<5}"
        )
    eff, raw = _deviations(rows, "eff"), _deviations(rows, "raw")
    n_skip = sum(1 for r in rows if r["skipped"])
    lines.append(f"Tín hiệu: {len(rows)}, dùng được: {len(rows) - n_skip}, bỏ qua: {n_skip}")
    if not eff:
        lines.append("KẾT LUẬN: không có tín hiệu nào đủ dữ liệu để kết luận.")
        return "\n".join(lines)
    med_eff, med_raw = statistics.median(eff), statistics.median(raw)
    lines.append(f"Lệch trung vị qty THỰC (sau trần 20%): {med_eff:.1%}  [tiêu chí quyết định]")
    lines.append(f"Lệch trung vị qty gỡ trần (tham khảo): {med_raw:.1%}")
    cal = _calibrated_deviations(rows, "raw")
    ratios = [
        r["qty_garch_raw"] / r["qty_atr_raw"]
        for r in rows
        if r["skipped"] is None and r["qty_atr_raw"] > 0
    ]
    lines.append(
        f"Chênh MỨC (trung vị qty_GARCH/qty_ATR, gỡ trần): {statistics.median(ratios):.2f}x; "
        f"lệch trung vị SAU hiệu chỉnh mức: {statistics.median(cal):.1%}  "
        "[chỉ số bổ sung sau lần đo đầu, tham khảo]"
    )
    if med_eff < THRESHOLD:
        lines.append(f"KẾT LUẬN: < {THRESHOLD:.0%} — GARCH không đổi qty đáng kể, dừng hướng này.")
    else:
        lines.append(f"KẾT LUẬN: >= {THRESHOLD:.0%} — GARCH đổi qty đáng kể, đáng bàn bước tiếp.")
    return "\n".join(lines)


def run_measurement(
    bars_by_symbol: dict[str, list[Bar]],
    strategy_factory: Callable,
    holidays: set[date],
    capital: float,
    min_obs: int,
) -> tuple[list[dict], dict[str, tuple[int, int]]]:
    calls: list[dict] = []
    for bars in bars_by_symbol.values():
        risk = SignalProbeRiskManager(capital=capital)
        run_backtest(
            sorted(bars, key=lambda b: b.ts),
            strategy_factory(),
            risk,
            TrailingStopManager(),
            capital,
        )
        calls.extend(risk.calls)
    rows = compare_sizing(calls, bars_by_symbol, holidays, capital, min_obs)
    depth = {
        sym: (len(bars), len(daily_log_returns(bars, holidays)))
        for sym, bars in bars_by_symbol.items()
    }
    return rows, depth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="HPG,IJC,AAA")
    ap.add_argument("--strategy", default="octopus_pullback", choices=list(STRATEGIES))
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--min-obs", type=int, default=DEFAULT_MIN_OBS)
    ap.add_argument("--from", dest="frm", default="2000-01-01")
    ap.add_argument("--to", dest="to", default="2030-01-01")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    holidays = load_holidays(args.config)
    storage = Storage(resolve_dsn(args.dsn))
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ)
    bars_by_symbol = {
        sym: storage.read_daily_bars(sym, frm, to) for sym in args.symbols.split(",")
    }
    rows, depth = run_measurement(
        bars_by_symbol, STRATEGIES[args.strategy], holidays, args.capital, args.min_obs
    )
    print(f"Vốn: {args.capital:,.0f}  Chiến lược: {args.strategy}  Khung: 1d  min_obs: {args.min_obs}")
    print(format_report(rows, depth))


if __name__ == "__main__":
    main()
