"""Đo tần suất trần giá trị lệnh (max_order_value_pct) chặn ATR sizing (bước 0, GARCH).

Câu hỏi: `RiskManager.approve_sized` lấy qty = min(qty_atr, qty_cap). Nếu qty_cap
luôn nhỏ hơn qty_atr thì mọi cải tiến ước lượng biến động (GARCH thay ATR) không
đổi được qty nào — chỉ cần đo trước khi đầu tư.

Cách đo KHÔNG chép công thức sizing (bài học 4ea4c8d): với mỗi BUY, gọi
approve_sized của chính RiskManager hai lần — một lần với trần thật, một lần với
trần gỡ bỏ (max_order_value_pct rất lớn) — rồi so qty. Chỉ đọc DB, không ghi gì,
không sửa code giao dịch.

Phân loại mỗi tín hiệu BUY:
- cap_binds        : được duyệt cả hai, qty có trần < qty không trần
- not_binding      : được duyệt cả hai, qty bằng nhau
- rejected_by_cap  : không trần thì duyệt, có trần thì bị từ chối (< 1 lô)
- rejected_other   : cả hai đều từ chối (ATR lỗi, max_positions, halt lỗ ngày)

CLI:
    uv run python scripts/measure_cap_binding.py --symbols HPG,IJC,AAA \\
        [--strategy octopus_pullback] [--tf 5m] [--capital 100000000] [--dsn ...]
"""

import argparse
import dataclasses
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.backtest import _TF_SPEC, STRATEGIES, run_backtest
from trading.broker import Position
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategy import Signal
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CATEGORIES = ("cap_binds", "not_binding", "rejected_by_cap", "rejected_other")
_NO_CAP = 1e9


@dataclasses.dataclass
class CapProbeRiskManager(RiskManager):
    """RiskManager thật + ghi lại, với mỗi BUY, kết quả có/không có trần."""

    def __post_init__(self) -> None:
        self.records: list[dict] = []

    def _uncapped_twin(self) -> RiskManager:
        kwargs = {
            f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init
        }
        kwargs["max_order_value_pct"] = _NO_CAP
        return RiskManager(**kwargs)

    def approve_sized(
        self,
        signal: Signal,
        ref_price: float,
        atr: float | None,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> Signal | None:
        capped = super().approve_sized(
            signal, ref_price, atr, positions, daily_pnl, today
        )
        if signal.side != "BUY":
            return capped
        uncapped = self._uncapped_twin().approve_sized(
            signal, ref_price, atr, positions, daily_pnl, today
        )
        if uncapped is None:
            category = "rejected_other"
        elif capped is None:
            category = "rejected_by_cap"
        elif capped.qty < uncapped.qty:
            category = "cap_binds"
        else:
            category = "not_binding"
        self.records.append(
            {
                "symbol": signal.symbol,
                "category": category,
                "qty_capped": capped.qty if capped else 0,
                "qty_uncapped": uncapped.qty if uncapped else 0,
            }
        )
        return capped


def measure_cap_binding(
    bars_by_symbol: dict[str, list[Bar]],
    strategy_factory: Callable,
    capital: float,
) -> dict[str, dict]:
    """Chạy backtest từng mã, trả về {symbol: {category: số tín hiệu, ...}}."""
    result: dict[str, dict] = {}
    for sym, bars in bars_by_symbol.items():
        risk = CapProbeRiskManager(capital=capital)
        run_backtest(
            sorted(bars, key=lambda b: b.ts),
            strategy_factory(),
            risk,
            TrailingStopManager(),
            capital,
        )
        counts = dict.fromkeys(CATEGORIES, 0)
        qty_capped = qty_uncapped = 0
        for r in risk.records:
            counts[r["category"]] += 1
            qty_capped += r["qty_capped"]
            qty_uncapped += r["qty_uncapped"]
        counts["total"] = len(risk.records)
        counts["qty_capped_sum"] = qty_capped
        counts["qty_uncapped_sum"] = qty_uncapped
        result[sym] = counts
    return result


def format_report(result: dict[str, dict]) -> str:
    lines = [
        (
            f"{'Mã':<6}{'BUY':>6}{'cap_binds':>11}{'not_bind':>10}"
            f"{'rej_by_cap':>12}{'rej_other':>11}{'qty có trần/không trần':>26}"
        )
    ]
    for sym, c in sorted(result.items()):
        ratio = (
            f"{c['qty_capped_sum'] / c['qty_uncapped_sum']:.1%}"
            if c["qty_uncapped_sum"]
            else "n/a"
        )
        lines.append(
            f"{sym:<6}{c['total']:>6}{c['cap_binds']:>11}{c['not_binding']:>10}"
            f"{c['rejected_by_cap']:>12}{c['rejected_other']:>11}{ratio:>26}"
        )
    decided = sum(
        c["cap_binds"] + c["not_binding"] + c["rejected_by_cap"]
        for c in result.values()
    )
    capped = sum(c["cap_binds"] + c["rejected_by_cap"] for c in result.values())
    if decided == 0:
        lines.append("KET LUAN: khong co tin hieu BUY nao du de ket luan.")
    else:
        lines.append(
            f"Tran chan {capped}/{decided} tin hieu hop le ({capped / decided:.0%}). "
            "Nguong quyet dinh theo ke hoach: > 80% thi GARCH sizing vo nghia."
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="HPG,IJC,AAA")
    ap.add_argument("--strategy", default="octopus_pullback", choices=list(STRATEGIES))
    ap.add_argument("--tf", default="5m", choices=list(_TF_SPEC))
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--from", dest="frm", default="2020-01-01")
    ap.add_argument("--to", dest="to", default="2030-01-01")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    storage = Storage(resolve_dsn(args.dsn))
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ)
    source, resample_fn = _TF_SPEC[args.tf]
    read = storage.read_bars if source == "bars" else storage.read_daily_bars

    bars_by_symbol = {
        sym: resample_fn(read(sym, frm, to)) for sym in args.symbols.split(",")
    }
    result = measure_cap_binding(bars_by_symbol, STRATEGIES[args.strategy], args.capital)
    print(f"Vốn: {args.capital:,.0f}  Chiến lược: {args.strategy}  Khung: {args.tf}")
    print(format_report(result))


if __name__ == "__main__":
    main()
