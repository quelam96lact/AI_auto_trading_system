"""Đo lường tần suất xuất hiện của 3 mẫu nến từ slide Buổi 9&10 (Gói P1 — plan 2026-09-06).

Khảo sát tần suất:
1. is_doji (kèm luật Near Doji)
2. is_hammer (thoả 4 điều kiện)
3. combo_signal (Combo BUY / Combo SELL với MA20 + MACD 5/25/5)

Trên các tập dữ liệu:
- Cổ phiếu VN (bars_daily — 1D)
- Cổ phiếu VN (bars — 5M)
- Crypto BingX (bars_crypto — 1D & 1H)

CLI:
    uv run python scripts/measure_candlestick_patterns.py [--market all|vn|crypto] [--dsn ...]
"""

import argparse
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

# Thêm scripts/ vào sys.path để import _db_common
sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.indicators import MacdCalculator
from trading.models import Bar
from trading.patterns import combo_signal, is_doji, is_hammer
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def scan_patterns_in_bars(bars: list[Bar]) -> dict:
    """Quét và đếm số lần xuất hiện của từng mẫu nến trong chuỗi bar."""
    if not bars:
        return {
            "n_bars": 0,
            "doji": 0,
            "hammer": 0,
            "combo_buy": 0,
            "combo_sell": 0,
            "by_year": defaultdict(lambda: {"bars": 0, "doji": 0, "hammer": 0, "combo_buy": 0, "combo_sell": 0}),
        }

    doji_count = 0
    hammer_count = 0
    combo_buy_count = 0
    combo_sell_count = 0

    by_year = defaultdict(lambda: {"bars": 0, "doji": 0, "hammer": 0, "combo_buy": 0, "combo_sell": 0})

    # Indicators cho Combo: MA(20) và MACD(5,25,5)
    ma_window: deque[float] = deque(maxlen=20)
    macd_calc = MacdCalculator(fast=5, slow=25, signal=5)

    recent_bars: list[Bar] = []

    for b in bars:
        yr = b.ts.year
        by_year[yr]["bars"] += 1

        # Cập nhật MA20
        ma_window.append(b.close)
        ma20 = (sum(ma_window) / 20.0) if len(ma_window) == 20 else None

        # Cập nhật MACD
        macd_hist = macd_calc.update(b)

        # 1. Doji
        if is_doji(b, prev_bars=recent_bars):
            doji_count += 1
            by_year[yr]["doji"] += 1

        # 2. Hammer
        if is_hammer(b, prev_bars=recent_bars):
            hammer_count += 1
            by_year[yr]["hammer"] += 1

        # 3. Combo
        c_sig = combo_signal(b, ma20=ma20, macd_hist=macd_hist)
        if c_sig == "buy":
            combo_buy_count += 1
            by_year[yr]["combo_buy"] += 1
        elif c_sig == "sell":
            combo_sell_count += 1
            by_year[yr]["combo_sell"] += 1

        recent_bars.append(b)
        if len(recent_bars) > 10:
            recent_bars.pop(0)

    return {
        "n_bars": len(bars),
        "doji": doji_count,
        "hammer": hammer_count,
        "combo_buy": combo_buy_count,
        "combo_sell": combo_sell_count,
        "by_year": by_year,
    }


def measure_dataset(name: str, bars_by_symbol: dict[str, list[Bar]]) -> dict:
    """Tổng hợp tần suất mẫu nến cho toàn bộ danh mục mã."""
    total_symbols = len(bars_by_symbol)
    total_bars = 0
    total_doji = 0
    total_hammer = 0
    total_combo_buy = 0
    total_combo_sell = 0

    symbols_with_doji = 0
    symbols_with_hammer = 0
    symbols_with_combo_buy = 0
    symbols_with_combo_sell = 0

    yearly_agg = defaultdict(lambda: {"bars": 0, "doji": 0, "hammer": 0, "combo_buy": 0, "combo_sell": 0})

    for bars in bars_by_symbol.values():
        res = scan_patterns_in_bars(bars)
        total_bars += res["n_bars"]
        total_doji += res["doji"]
        total_hammer += res["hammer"]
        total_combo_buy += res["combo_buy"]
        total_combo_sell += res["combo_sell"]

        if res["doji"] > 0:
            symbols_with_doji += 1
        if res["hammer"] > 0:
            symbols_with_hammer += 1
        if res["combo_buy"] > 0:
            symbols_with_combo_buy += 1
        if res["combo_sell"] > 0:
            symbols_with_combo_sell += 1

        for yr, ydata in res["by_year"].items():
            for k in ["bars", "doji", "hammer", "combo_buy", "combo_sell"]:
                yearly_agg[yr][k] += ydata[k]

    return {
        "name": name,
        "total_symbols": total_symbols,
        "total_bars": total_bars,
        "total_doji": total_doji,
        "total_hammer": total_hammer,
        "total_combo_buy": total_combo_buy,
        "total_combo_sell": total_combo_sell,
        "symbols_with_doji": symbols_with_doji,
        "symbols_with_hammer": symbols_with_hammer,
        "symbols_with_combo_buy": symbols_with_combo_buy,
        "symbols_with_combo_sell": symbols_with_combo_sell,
        "yearly_agg": yearly_agg,
    }


def print_summary_table(summaries: list[dict]) -> None:
    print("\n" + "=" * 125)
    print("BẢNG TỔNG HỢP TẦN SUẤT XUẤT HIỆN MẪU NẾN (GÓI P1 — DOJI / HAMMER / COMBO)")
    print("=" * 125)
    header = (
        f"{'Thị trường / Khung':<28} | {'Tổng nến':<10} | {'Mã':<6} | "
        f"{'Doji (Mã %)':<16} | {'Hammer (Mã %)':<16} | {'Combo BUY':<12} | {'Combo SELL':<12}"
    )
    print(header)
    print("-" * 125)

    for s in summaries:
        doji_str = f"{s['total_doji']:,} ({s['symbols_with_doji']}/{s['total_symbols']})"
        hammer_str = f"{s['total_hammer']:,} ({s['symbols_with_hammer']}/{s['total_symbols']})"
        cb_str = f"{s['total_combo_buy']:,}"
        cs_str = f"{s['total_combo_sell']:,}"
        print(
            f"{s['name']:<28} | {s['total_bars']:<10,} | {s['total_symbols']:<6} | "
            f"{doji_str:<16} | {hammer_str:<16} | {cb_str:<12} | {cs_str:<12}"
        )

    print("=" * 125)

    # In phân bố theo năm cho từng dataset
    for s in summaries:
        print(f"\n--- Phân bố theo năm: {s['name']} ---")
        print(f"{'Năm':<6} | {'Số nến':>12} | {'Doji':>10} | {'Hammer':>10} | {'Combo BUY':>12} | {'Combo SELL':>12}")
        print("-" * 75)
        for yr in sorted(s["yearly_agg"].keys()):
            y = s["yearly_agg"][yr]
            print(f"{yr:<6} | {y['bars']:>12,} | {y['doji']:>10,} | {y['hammer']:>10,} | {y['combo_buy']:>12,} | {y['combo_sell']:>12,}")
        print("-" * 75)


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo lường tần suất mẫu nến")
    parser.add_argument("--market", default="all", choices=["all", "vn", "crypto"])
    parser.add_argument("--dsn", default=None, help="Postgres DSN")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số mã (smoke test)")
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    summaries = []

    # 1. VN Stock 1D (bars_daily)
    if args.market in ("all", "vn"):
        print("Đang tải dữ liệu Chứng khoán VN khung 1 Ngày (bars_daily)...")
        with storage.conn() as c:
            rows = c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol").fetchall()
        vn_daily_symbols = [r[0] for r in rows]
        if args.limit > 0:
            vn_daily_symbols = vn_daily_symbols[: args.limit]

        vn_daily_bars = {}
        for sym in vn_daily_symbols:
            bars = storage.read_daily_bars(sym, datetime(2016, 1, 1), datetime(2027, 1, 1))
            if bars:
                vn_daily_bars[sym] = bars

        s_vn_daily = measure_dataset("VN Stock (1D bars_daily)", vn_daily_bars)
        summaries.append(s_vn_daily)

    # 2. VN Stock 5M (bars)
    if args.market in ("all", "vn"):
        print("Đang tải dữ liệu Chứng khoán VN khung 5 Phút (bars)...")
        with storage.conn() as c:
            rows = c.execute("SELECT DISTINCT symbol FROM bars ORDER BY symbol").fetchall()
        vn_5m_symbols = [r[0] for r in rows]
        if args.limit > 0:
            vn_5m_symbols = vn_5m_symbols[: args.limit]

        vn_5m_bars = {}
        for sym in vn_5m_symbols:
            bars = storage.read_bars(sym, datetime(2026, 1, 1), datetime(2027, 1, 1))
            if bars:
                vn_5m_bars[sym] = bars

        s_vn_5m = measure_dataset("VN Stock (5M bars)", vn_5m_bars)
        summaries.append(s_vn_5m)

    # 3. Crypto 1D & 1H (bars_crypto)
    if args.market in ("all", "crypto"):
        print("Đang tải dữ liệu Crypto khung 1 Ngày (bars_crypto)...")
        crypto_1d_bars = {}
        with storage.conn() as c:
            rows = c.execute(
                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1d\' ORDER BY symbol, ts'
            ).fetchall()
            for r in rows:
                bar = Bar(symbol=r[0], ts=r[1], open=float(r[2]), high=float(r[3]), low=float(r[4]), close=float(r[5]), volume=int(r[6]), source="bingx")
                crypto_1d_bars.setdefault(r[0], []).append(bar)

        s_crypto_1d = measure_dataset("Crypto BingX (1D)", crypto_1d_bars)
        summaries.append(s_crypto_1d)

        print("Đang tải dữ liệu Crypto khung 1 Giờ (bars_crypto)...")
        crypto_1h_bars = {}
        with storage.conn() as c:
            rows = c.execute(
                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1h\' ORDER BY symbol, ts'
            ).fetchall()
            for r in rows:
                bar = Bar(symbol=r[0], ts=r[1], open=float(r[2]), high=float(r[3]), low=float(r[4]), close=float(r[5]), volume=int(r[6]), source="bingx")
                crypto_1h_bars.setdefault(r[0], []).append(bar)

        s_crypto_1h = measure_dataset("Crypto BingX (1H)", crypto_1h_bars)
        summaries.append(s_crypto_1h)

    print_summary_table(summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
