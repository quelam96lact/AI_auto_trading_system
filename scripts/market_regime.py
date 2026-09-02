"""Định nghĩa chế độ thị trường (market regime) từ độ rộng thị trường (market breadth).

Brief đợt 9 — Chiến lược theo chế độ thị trường, giai đoạn 1: ĐO.
- Không có VNINDEX trong bars_daily -> dựng độ rộng thị trường từ rổ cổ phiếu.
- breadth(d) = tỷ lệ mã có close(d) > SMA200(close, d), tính trên các mã có đủ 200 phiên lịch sử tính tới ngày d.
- Phân loại:
    RISK_ON:  breadth >= 0.60
    NEUTRAL:  0.40 <= breadth < 0.60
    RISK_OFF: breadth < 0.40
- Chống look-ahead: breadth ngày d chỉ dùng dữ liệu tới hết ngày d.
  Quyết định giao dịch ngày d phải dùng breadth(d-1).
"""

import argparse
import sys
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _is_dirty(bar: Bar) -> bool:
    """SPEC-1c: bar rác = có open/high/low/close <= 0."""
    return bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0


def _bar_date(b: Bar) -> date:
    """Chuyển timestamp của bar sang ngày theo giờ Việt Nam."""
    return b.ts.astimezone(TZ).date() if b.ts.tzinfo else b.ts.date()


def compute_breadth(bars_by_symbol: Mapping[str, list[Bar]], as_of: date) -> float:
    """breadth(d) = tỷ lệ mã có close(d) > SMA200(close, d), tính trên các mã
    có đủ 200 phiên lịch sử tính tới ngày d (as_of).
    Hàm thuần, không phụ thuộc DB, chống look-ahead.
    """
    denom = 0
    num = 0
    for bars in bars_by_symbol.values():
        clean_bars = [
            b for b in bars
            if not _is_dirty(b) and _bar_date(b) <= as_of
        ]
        if len(clean_bars) < 200:
            continue
        last_200 = clean_bars[-200:]
        sma200 = sum(b.close for b in last_200) / 200.0
        current_close = last_200[-1].close
        denom += 1
        if current_close > sma200:
            num += 1
    if denom == 0:
        return 0.0
    return num / denom


def classify_regime(breadth: float) -> str:
    """Phân loại 3 chế độ theo ngưỡng cố định 0.40 / 0.60:
    RISK_ON:  breadth >= 0.60
    NEUTRAL:  0.40 <= breadth < 0.60
    RISK_OFF: breadth < 0.40
    """
    if breadth >= 0.60:
        return "RISK_ON"
    elif breadth >= 0.40:
        return "NEUTRAL"
    else:
        return "RISK_OFF"


def compute_breadth_series(
    bars_by_symbol: Mapping[str, list[Bar]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Tính chuỗi breadth và regime cho tất cả các ngày giao dịch từ dữ liệu bars.
    Được tối ưu hóa tuần tự để tránh quét lặp O(N*M).
    """
    # Lọc bar rác và sắp xếp theo ngày cho từng mã
    cleaned_by_sym: dict[str, list[tuple[date, float]]] = {}
    all_dates_set: set[date] = set()
    for sym, bars in bars_by_symbol.items():
        sym_clean: list[tuple[date, float]] = []
        for b in bars:
            if not _is_dirty(b):
                d = _bar_date(b)
                sym_clean.append((d, b.close))
                all_dates_set.add(d)
        sym_clean.sort(key=lambda x: x[0])
        cleaned_by_sym[sym] = sym_clean

    all_dates = sorted(all_dates_set)
    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d <= end_date]

    # Duyệt từng ngày
    # Duy trì con trỏ / rolling buffer 200 cho từng mã
    sym_state: dict[str, list[float]] = {sym: [] for sym in cleaned_by_sym}
    sym_idx: dict[str, int] = {sym: 0 for sym in cleaned_by_sym}

    results: list[dict] = []
    for d in sorted(all_dates_set):
        denom = 0
        num = 0
        for sym, bars in cleaned_by_sym.items():
            idx = sym_idx[sym]
            while idx < len(bars) and bars[idx][0] <= d:
                sym_state[sym].append(bars[idx][1])
                idx += 1
            sym_idx[sym] = idx

            history = sym_state[sym]
            if len(history) >= 200:
                last_200 = history[-200:]
                sma200 = sum(last_200) / 200.0
                curr = last_200[-1]
                denom += 1
                if curr > sma200:
                    num += 1

        if (start_date is None or d >= start_date) and (end_date is None or d <= end_date):
            b_val = (num / denom) if denom > 0 else 0.0
            reg = classify_regime(b_val)
            results.append({
                "date": d.strftime("%Y-%m-%d"),
                "breadth": b_val,
                "regime": reg,
                "symbols_eligible": denom,
                "symbols_above": num,
            })

    return results


def load_all_bars(
    storage: Storage,
    excluded_symbols: set[str],
    limit: int = 0,
) -> dict[str, list[Bar]]:
    """Đọc toàn bộ bars_daily cho các mã hợp lệ."""
    with storage.conn() as c:
        symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]
    symbols = [s for s in symbols if s.upper() not in excluded_symbols]
    if limit > 0:
        symbols = symbols[:limit]

    bars_by_symbol: dict[str, list[Bar]] = {}
    frm = datetime(2016, 1, 1, tzinfo=TZ)
    to = datetime(2026, 9, 1, tzinfo=TZ)
    for i, sym in enumerate(symbols, 1):
        bars = storage.read_daily_bars(sym, frm, to)
        bars_by_symbol[sym] = bars
        if i % 300 == 0 or i == len(symbols):
            print(f"  ...đã nạp {i}/{len(symbols)} mã", file=sys.stderr)
    return bars_by_symbol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--output", default="docs/superpowers/research/2026-09-02-breadth-daily.csv")
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
        print(f"Đã nạp {len(excluded)} mã loại trừ từ {args.exclude_file}")

    print("Đang đọc bars_daily...")
    bars_by_symbol = load_all_bars(storage, excluded, limit=args.limit)

    print("Đang tính chuỗi breadth...")
    series = compute_breadth_series(bars_by_symbol)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("date,breadth,regime\n")
        for row in series:
            f.write(f"{row['date']},{row['breadth']:.6f},{row['regime']}\n")
    print(f"Đã ghi {len(series)} phiên vào {out_path}")

    # Thống kê phân bố chế độ
    counts: dict[str, int] = {"RISK_ON": 0, "NEUTRAL": 0, "RISK_OFF": 0}
    for row in series:
        counts[row["regime"]] += 1

    total = len(series)
    print("\n" + "=" * 60)
    print("BẢNG THỐNG KÊ PHÂN BỐ CHẾ ĐỘ THỊ TRƯỜNG (2016-01-04 -> 2026-08-28)")
    print("=" * 60)
    print(f"{'Chế độ':<12} {'Số phiên':>10} {'Tỷ lệ %':>10}")
    print("-" * 34)
    for regime in ["RISK_ON", "NEUTRAL", "RISK_OFF"]:
        cnt = counts[regime]
        pct = (cnt / total) if total else 0.0
        print(f"{regime:<12} {cnt:>10} {pct:>9.1%}")
    print("-" * 34)
    print(f"{'Tổng cộng':<12} {total:>10} {1.0:>9.1%}")
    print("=" * 60)

    for regime, cnt in counts.items():
        pct = cnt / total if total else 0.0
        if pct < 0.10:
            print(f"CẢNH BÁO: Chế độ {regime} chiếm {pct:.1%} < 10% số phiên!")


if __name__ == "__main__":
    main()
