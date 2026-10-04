"""Đo rủi ro THỰC của hệ thống trên backtest gộp các mã (sau bước 0/GARCH).

Bước 0 cho thấy bar 5 phút luôn bị trần 20% vốn chặn: mỗi lệnh ra đúng 20% vốn,
`risk_pct` = 1% trong RiskManager không có hiệu lực. Câu hỏi còn lại là rủi ro thực
là bao nhiêu. Script này chỉ ĐỌC DB và chạy `run_backtest` như engine (một RiskManager,
một vốn chung cho mọi mã), rồi đo từ chính danh sách fill — không chép công thức nào:

1. Mỗi vòng giao dịch (từ vị thế 0 -> >0 tới lúc về 0): kích thước vào lệnh, lãi/lỗ ròng
   (pnl của broker đã gồm phí mua + phí bán + thuế + trượt giá) theo % vốn và % giá trị
   vào lệnh, phí, thời gian giữ.
2. Số vị thế mở đồng thời và tổng giá trị vị thế / vốn theo từng bar (mark = close).
3. Max drawdown theo equity của backtest.

So với: risk_pct = 1% vốn mỗi lệnh (cấu hình), max_positions = 5, trần 20% vốn mỗi lệnh.

CLI (chạy từ gốc repo):
    uv run python scripts/measure_real_risk.py [--symbols HPG,IJC,AAA]
        [--strategy octopus_pullback] [--tf 5m] [--capital 100000000]
        [--fee-rate 0.0015] [--dsn ...]
"""

import argparse
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.backtest import _TF_SPEC, STRATEGIES, run_backtest
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RISK_PCT = RiskManager.__dataclass_fields__["risk_pct"].default
MAX_POSITIONS = RiskManager.__dataclass_fields__["max_positions"].default


def round_trips(fills: Sequence[Fill], capital: float) -> tuple[list[dict], int]:
    """Gộp fill thành vòng giao dịch theo từng mã. Trả (các vòng đã đóng, số vị thế còn mở).

    Fill SELL có qty = 0 (stop chạm nhưng chưa settle T+2,5) bị bỏ qua."""
    open_trip: dict[str, dict] = {}
    qty: dict[str, int] = {}
    done: list[dict] = []
    for f in sorted(fills, key=lambda x: x.ts):
        if f.qty <= 0:
            continue
        t = open_trip.get(f.symbol)
        if f.side == "BUY":
            if t is None:
                t = open_trip[f.symbol] = {
                    "symbol": f.symbol, "open_ts": f.ts, "entry_value": 0.0,
                    "fees": 0.0, "pnl": 0.0,
                }
            t["entry_value"] += f.price * f.qty
            t["fees"] += f.fee
            qty[f.symbol] = qty.get(f.symbol, 0) + f.qty
        elif t is not None:
            t["fees"] += f.fee
            t["pnl"] += f.pnl or 0.0
            qty[f.symbol] -= f.qty
            if qty[f.symbol] == 0:
                t["close_ts"] = f.ts
                t["hold_days"] = (f.ts - t["open_ts"]).total_seconds() / 86_400
                t["entry_pct_capital"] = t["entry_value"] / capital
                t["pnl_pct_capital"] = t["pnl"] / capital
                t["pnl_pct_entry"] = t["pnl"] / t["entry_value"]
                t["fee_pct_entry"] = t["fees"] / t["entry_value"]
                t["fees_pct_capital"] = t["fees"] / capital
                done.append(open_trip.pop(f.symbol))
    return done, len(open_trip)


def exposure_profile(
    fills: Sequence[Fill], bars: Sequence[Bar], capital: float
) -> dict:
    """Theo từng bar: số vị thế mở và tổng giá trị vị thế / vốn (mark = close gần nhất)."""
    ordered = sorted((f for f in fills if f.qty > 0), key=lambda x: x.ts)
    held: dict[str, int] = {}
    marks: dict[str, float] = {}
    i = 0
    max_pos, max_exposure, bars_over = 0, 0.0, 0
    ordered_bars = sorted(bars, key=lambda b: (b.ts, b.symbol))
    for bar in ordered_bars:
        while i < len(ordered) and ordered[i].ts <= bar.ts:
            f = ordered[i]
            held[f.symbol] = held.get(f.symbol, 0) + (f.qty if f.side == "BUY" else -f.qty)
            i += 1
        marks[bar.symbol] = bar.close
        exposure = sum(q * marks.get(s, 0.0) for s, q in held.items() if q > 0) / capital
        max_exposure = max(max_exposure, exposure)
        max_pos = max(max_pos, sum(1 for q in held.values() if q > 0))
        bars_over += exposure > 0.4
    return {
        "max_positions": max_pos,
        "max_exposure": max_exposure,
        "share_bars_over_40pct": bars_over / len(ordered_bars) if ordered_bars else 0.0,
    }


def _q(values: Sequence[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]


def _totals_lines(trips: Sequence[dict]) -> list[str]:
    """Tổng lãi/lỗ ròng, trung bình mỗi vòng (kèm sai số chuẩn) và tổng phí+thuế.

    `pnl` của broker là lãi/lỗ RÒNG: đã trừ phí mua, phí bán, thuế bán, và giá khớp đã
    gồm trượt giá. Lãi gộp ở đây = ròng + phí+thuế, tức trước phí/thuế (vẫn sau trượt giá)."""
    n = len(trips)
    net = sum(t["pnl"] for t in trips)
    fees = sum(t["fees"] for t in trips)
    net_pct = sum(t["pnl_pct_capital"] for t in trips)
    fees_pct = sum(t["fees_pct_capital"] for t in trips)
    per_trip = [t["pnl_pct_capital"] for t in trips]
    mean = statistics.mean(per_trip)
    lines = [
        f"Tổng lãi/lỗ ròng: {net:+,.0f} đồng ({net_pct:+.2%} vốn)",
        f"Tổng phí+thuế: {fees:,.0f} đồng ({fees_pct:.2%} vốn)",
        (
            f"Lãi/lỗ gộp trước phí+thuế (sau trượt giá): {net + fees:+,.0f} đồng "
            f"({net_pct + fees_pct:+.2%} vốn)"
        ),
    ]
    if n >= 2:
        se = statistics.stdev(per_trip) / n**0.5
        lines.append(
            f"Trung bình mỗi vòng: {net / n:+,.0f} đồng ({mean:+.3%} vốn) "
            f"± {se:.3%} (sai số chuẩn, n = {n})"
        )
        lines.append(
            "Trung bình mỗi vòng "
            + ("PHÂN BIỆT được với 0" if abs(mean) > 2 * se else "CHƯA phân biệt được với 0")
            + " (ngưỡng thô: |trung bình| > 2 sai số chuẩn)"
        )
    else:
        lines.append(f"Trung bình mỗi vòng: {net / n:+,.0f} đồng (n = 1, không có sai số chuẩn)")
    return lines


def format_report(
    trips: Sequence[dict], still_open: int, exposure: dict, max_drawdown: float
) -> str:
    lines = [f"Vòng giao dịch đã đóng: {len(trips)}, còn mở cuối kỳ: {still_open}"]
    if not trips:
        lines.append("KẾT LUẬN: không có vòng giao dịch nào để đo.")
        return "\n".join(lines)
    pnl_cap = [t["pnl_pct_capital"] for t in trips]
    pnl_entry = [t["pnl_pct_entry"] for t in trips]
    fee_entry = [t["fee_pct_entry"] for t in trips]
    entry = [t["entry_pct_capital"] for t in trips]
    losers = [x for x in pnl_cap if x < 0]
    breach = sum(1 for x in pnl_cap if x < -RISK_PCT)
    lines += [
        (
            f"Kích thước vào lệnh (% vốn): trung vị {statistics.median(entry):.1%}, "
            f"max {max(entry):.1%}  [cấu hình risk_pct = {RISK_PCT:.0%} vốn rủi ro mỗi lệnh]"
        ),
        f"Tỷ lệ thắng: {sum(1 for x in pnl_cap if x > 0) / len(trips):.0%}",
        (
            f"Lãi/lỗ ròng mỗi vòng (% vốn): trung vị {statistics.median(pnl_cap):+.2%}, "
            f"p5 {_q(pnl_cap, 0.05):+.2%}, tệ nhất {min(pnl_cap):+.2%}"
        ),
        (
            "Lãi/lỗ ròng mỗi vòng (% giá trị vào lệnh): "
            f"trung vị {statistics.median(pnl_entry):+.2%}"
        ),
        f"Phí+thuế (% giá trị vào lệnh): trung vị {statistics.median(fee_entry):.2%}",
        (
            f"Vòng lỗ nặng hơn {RISK_PCT:.0%} vốn: {breach}/{len(trips)}"
            + (
                f"; lỗ trung vị của các vòng lỗ {statistics.median(losers):+.2%} vốn"
                if losers
                else ""
            )
        ),
        (
            f"Thời gian giữ (ngày): trung vị {statistics.median(t['hold_days'] for t in trips):.1f}, "
            f"max {max(t['hold_days'] for t in trips):.1f}"
        ),
        f"Vị thế mở đồng thời tối đa: {exposure['max_positions']} (trần cấu hình {MAX_POSITIONS})",
        (
            f"Tổng giá trị vị thế / vốn: tối đa {exposure['max_exposure']:.0%}; "
            f"{exposure['share_bars_over_40pct']:.1%} số bar trên 40% vốn"
        ),
        f"Max drawdown equity (backtest): {max_drawdown:.1%}",
        *_totals_lines(trips),
    ]
    return "\n".join(lines)


def validate_fee_rate(fee_rate: float | None) -> float | None:
    """Phí mỗi chiều dạng thập phân (0.0015 = 0,15%). Chặn gõ nhầm kiểu 0.15 (= 15%)."""
    if fee_rate is not None and not 0.0 <= fee_rate < 0.01:
        raise SystemExit(
            f"--fee-rate = {fee_rate} không hợp lý: dùng dạng thập phân, "
            "ví dụ 0.0015 cho 0,15% mỗi chiều (phải nhỏ hơn 0.01 = 1%)."
        )
    return fee_rate


def run_report(bars, strategy, capital: float, fee_rate: float | None = None):
    """Chạy backtest gộp như engine. `fee_rate` = None -> dùng FEE_RATE mặc định của repo."""
    return run_backtest(
        bars, strategy, RiskManager(capital=capital), TrailingStopManager(), capital,
        fee_rate=fee_rate,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="HPG,IJC,AAA")
    ap.add_argument("--strategy", default="octopus_pullback", choices=list(STRATEGIES))
    ap.add_argument("--tf", default="5m", choices=list(_TF_SPEC))
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--from", dest="frm", default="2020-01-01")
    ap.add_argument("--to", dest="to", default="2030-01-01")
    ap.add_argument(
        "--fee-rate", type=float, default=None,
        help=f"phí môi giới mỗi chiều, dạng thập phân (mặc định {FEE_RATE} = FEE_RATE của "
        "paper_broker; thuế bán 0,1% và trượt giá giữ nguyên)",
    )
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()
    fee_rate = validate_fee_rate(args.fee_rate)

    storage = Storage(resolve_dsn(args.dsn))
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ)
    source, resample_fn = _TF_SPEC[args.tf]
    read = storage.read_bars if source == "bars" else storage.read_daily_bars
    bars: list[Bar] = []
    for sym in args.symbols.split(","):
        bars.extend(resample_fn(read(sym, frm, to)))
    bars.sort(key=lambda b: (b.ts, b.symbol))

    report = run_report(bars, STRATEGIES[args.strategy](), args.capital, fee_rate)
    trips, still_open = round_trips(report.fills, args.capital)
    exposure = exposure_profile(report.fills, bars, args.capital)
    used_fee = FEE_RATE if fee_rate is None else fee_rate
    print(f"Vốn: {args.capital:,.0f}  Chiến lược: {args.strategy}  Khung: {args.tf}  "
          f"Mã: {args.symbols}  Số bar: {len(bars)}  Phí mỗi chiều: {used_fee:.4%}"
          + (" (mặc định)" if fee_rate is None else " (--fee-rate)"))
    print(format_report(trips, still_open, exposure, report.max_drawdown))


if __name__ == "__main__":
    main()
