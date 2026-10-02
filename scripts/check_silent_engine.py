"""Kiểm tra chốt chặn 'Engine Câm' (Gói X — plan 2026-09-05).

Engine bị coi là 'câm' khi chạy trên dữ liệu bar 5 phút thực tế mà:
1. Cổng thanh khoản (nếu có, vd: octopus_pullback) đóng 100% (0 bar mở), HOẶC
2. Không sinh ra bất kỳ tín hiệu MUA (bull) nào trong toàn bộ lịch sử bar cấu hình.

Script này dùng để phát hiện sớm lỗi lệch hệ quy chiếu tham số (như ngưỡng thanh
khoản 2 tỷ của bar ngày bị áp nhầm lên bar 5 phút).

CLI:
    uv run python scripts/check_silent_engine.py [--config config/config.yaml] [--dsn ...]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Thêm scripts/ vào sys.path để import _db_common
sys.path.insert(0, str(Path(__file__).parent))
from _alert_common import alert_and_fail
from _db_common import resolve_dsn

from trading.engine.main import _default_strategy
from trading.models import Bar
from trading.storage.db import Storage
from trading.strategy import Strategy
from trading.telegram import send_telegram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def analyze_symbol_bars(symbol: str, bars: list[Bar], strategy: Strategy) -> dict:
    """Phân tích chuỗi bar của một mã qua chiến lược và xác định engine có bị câm không.

    Hàm thuần: không phụ thuộc DB/mạng, nhận list[Bar] và Strategy instance.
    """
    total_bars = len(bars)
    if total_bars == 0:
        return {
            "symbol": symbol,
            "total_bars": 0,
            "avg_bar_value": 0.0,
            "has_liquidity_gate": hasattr(strategy, "_liquidity_ok"),
            "gate_open_bars": 0,
            "gate_open_pct": 0.0,
            "bull_signals": 0,
            "bear_signals": 0,
            "is_silent": True,
            "status": "NO_DATA",
            "reason": "Không có bar nào trong DB",
        }

    total_value = sum(b.close * b.volume for b in bars)
    avg_bar_value = total_value / total_bars

    has_gate = hasattr(strategy, "_liquidity_ok")
    gate_open_bars = 0
    bull_signals = 0
    bear_signals = 0

    for bar in bars:
        sig = strategy.compute_crossover(bar)
        if has_gate:
            if strategy._liquidity_ok(symbol):
                gate_open_bars += 1
        else:
            gate_open_bars += 1

        if sig == "bull":
            bull_signals += 1
        elif sig == "bear":
            bear_signals += 1

    gate_open_pct = (gate_open_bars / total_bars * 100.0) if total_bars > 0 else 0.0

    # Tiêu chí câm:
    # 1. Cổng thanh khoản đóng 100% (gate_open_bars == 0) trong khi strategy có cổng
    # 2. Hoặc không sinh bất kỳ tín hiệu bull nào (bull_signals == 0)
    is_silent = (has_gate and gate_open_bars == 0) or (bull_signals == 0)

    if has_gate and gate_open_bars == 0:
        status = "CRITICAL_SILENT"
        reason = "Cổng thanh khoản đóng 100% (0 bar mở)"
    elif bull_signals == 0:
        status = "WARN_NO_BULL"
        reason = f"0 tín hiệu bull (cổng mở {gate_open_bars} bar, {gate_open_pct:.1f}%)"
    else:
        status = "OK"
        reason = f"Hoạt động ({bull_signals} bull, {bear_signals} bear)"

    return {
        "symbol": symbol,
        "total_bars": total_bars,
        "avg_bar_value": avg_bar_value,
        "has_liquidity_gate": has_gate,
        "gate_open_bars": gate_open_bars,
        "gate_open_pct": gate_open_pct,
        "bull_signals": bull_signals,
        "bear_signals": bear_signals,
        "is_silent": is_silent,
        "status": status,
        "reason": reason,
    }


def check_engine_symbols(
    symbols: list[str],
    strategy_factory,
    storage: Storage,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Chạy kiểm tra tất cả các mã được cấu hình cho engine."""
    if start is None:
        start = datetime(2020, 1, 1)
    if end is None:
        end = datetime(2030, 1, 1)

    results = []
    for sym in symbols:
        bars = storage.read_bars(sym, start, end)
        strat = strategy_factory()
        res = analyze_symbol_bars(sym, bars, strat)
        results.append(res)
    return results


def _alert(messages: list[str]) -> int:
    """Cong thuc o `_alert_common` (khuon deploy_drift_check). `send_telegram`
    truyen vao de no van la bien toan cuc cua MODULE NAY — test monkeypatch
    theo day.

    Khong co ham nay thi goi X chi la mot script phai nho chay bang tay, ma
    chinh loi no phat hien da song bon thang vi khong ai nho nhin.
    """
    return alert_and_fail("[engine-cam]", messages, send_telegram)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kiểm tra chốt chặn engine câm")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent.parent / "config" / "config.yaml"),
        help="Đường dẫn file config.yaml",
    )
    parser.add_argument("--dsn", default=None, help="Postgres DSN")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Danh sách mã cần kiểm (mặc định lấy từ config)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"LỖI: Không tìm thấy file config tại {cfg_path}", file=sys.stderr)
        return 2

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f) or {}

    symbols = args.symbols or cfg_data.get("symbols", [])
    if not symbols:
        print(
            "LỖI: Không có mã nào trong config hoặc tham số --symbols", file=sys.stderr
        )
        return 2

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    default_strat = _default_strategy()
    strat_name = default_strat.__class__.__name__

    print("=" * 105)
    print(f"BÁO CÁO CHỐT CHẶN 'ENGINE CÂM' (GÓI X) — Chiến lược: {strat_name}")
    print("=" * 105)
    print(
        f"{'Mã':<8} | {'Số bar 5m':<10} | {'BQ giá trị/bar':<18} | "
        f"{'Cổng mở (bar / %)':<20} | {'Tín hiệu (Bull/Bear)':<22} | {'Trạng thái'}"
    )
    print("-" * 105)

    results = check_engine_symbols(symbols, _default_strategy, storage)
    any_silent = False

    for r in results:
        sym = r["symbol"]
        total = r["total_bars"]
        avg_val = f"{r['avg_bar_value']:,.0f} đ"
        gate_str = f"{r['gate_open_bars']:,} bar ({r['gate_open_pct']:.1f}%)"
        sigs_str = f"{r['bull_signals']} bull / {r['bear_signals']} bear"
        status_str = f"[{r['status']}] {r['reason']}"

        if r["is_silent"]:
            any_silent = True

        print(
            f"{sym:<8} | {total:<10,} | {avg_val:<18} | {gate_str:<20} | {sigs_str:<22} | {status_str}"
        )

    print("=" * 105)

    if any_silent:
        cam = [r for r in results if r["is_silent"]]
        return _alert(
            [
                (
                    f"[engine-cam] CRITICAL: {strat_name} KHONG THE sinh tin hieu"
                    f" mua tren {len(cam)}/{len(results)} ma cau hinh."
                ),
                *[
                    (
                        f"  {r['symbol']}: {r['total_bars']:,} bar, cong mo "
                        f"{r['gate_open_bars']} bar ({r['gate_open_pct']:.1f}%), "
                        f"{r['bull_signals']} bull — {r['reason']}"
                    )
                    for r in cam
                ],
                (
                    "Engine dang chay nhung khong dat duoc lenh nao. Xem docs/"
                    "superpowers/plans/2026-09-05-danh-gia-go-live-va-plan-ton-dong.md"
                ),
            ]
        )
    else:
        print(
            "\n[OK] Tất cả các mã cấu hình đều có cổng thanh khoản mở và sinh tín hiệu bình thường."
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
