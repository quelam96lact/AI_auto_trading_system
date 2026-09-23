"""Công cụ đo độ trễ xử lý nến giữa Collector và Engine — Brief đợt 79 Task 3.

Mục tiêu:
  1. Đọc logs/bars_closed.log và logs/engine_alerts.log, ghép cặp theo (symbol, bar_ts).
  2. Đo độ trễ collector (từ lúc đóng nến đến khi publish xong), độ trễ engine
     (từ lúc đóng nến đến khi engine xử lý xong), và hiệu số (engine cộng thêm).
  3. Tính phân vị p50, p90, p99, max cho cả 3 đại lượng.
  4. Tách số liệu theo từng mã (HPG, IJC, AAA).
  5. Tách số liệu theo khung giờ phiên (Mở cửa, Giữa phiên, Cuối phiên / ATC).

Ràng buộc:
  - CHỈ ĐỌC LOG, CHỈ IN SỐ, KHÔNG SỬA GÌ TRONG COLLECTOR / ENGINE.
  - Không thêm dependency mới (dùng thư viện chuẩn Python).
"""

import argparse
import json
import math
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def compute_percentiles(values: list[float]) -> dict[str, float]:
    """Tính phân vị p50, p90, p99 và max bằng nội suy tuyến tính chuẩn.

    Công thức: k = (n - 1) * (p / 100), nội suy giữa floor(k) và ceil(k).
    """
    if not values:
        return {"p50": 0.0, "p90": 0.0, "p99": 0.0, "max": 0.0}

    sorted_v = sorted(values)
    n = len(sorted_v)

    def _get_p(p: float) -> float:
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_v[int(k)]
        return sorted_v[int(f)] * (c - k) + sorted_v[int(c)] * (k - f)

    return {
        "p50": _get_p(50.0),
        "p90": _get_p(90.0),
        "p99": _get_p(99.0),
        "max": sorted_v[-1],
    }


def parse_collector_closed_bars(log_path: Path | str) -> list[dict]:
    """Đọc và giải mã các dòng 'bars closed' từ bars_closed.log.

    Trong collector/main.py:
      lag_ms = round((publish_done_at - max_close_ts).total_seconds() * 1000, 2)
      max_close_ts = max(b.ts for b in bars) + interval
    Vì vậy:
      close_ts = publish_done_at - timedelta(milliseconds=lag_ms)
      bar_ts = close_ts - interval (15 phút cho ATC 14:45, 5 phút cho các nến khác).
    """
    p = Path(log_path)
    if not p.is_file():
        return []

    records = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"bars closed"' not in line:
                continue
            line = line.strip()
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue

            try:
                log_ts = datetime.fromisoformat(parts[0])
                data = json.loads(parts[1])
                lag_ms = float(data.get("lag_ms", 0.0))
                symbols = data.get("symbols", [])
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

            # Ước tính mốc đóng nến max_close_ts
            est_close = log_ts - timedelta(milliseconds=lag_ms)
            est_close_vn = est_close.astimezone(TZ)

            # Khớp mốc 5 phút / 15 phút
            # ATC phiên chiều đóng lúc 14:45 (nến ts 14:30)
            minute = round(est_close_vn.minute / 5.0) * 5
            hour = est_close_vn.hour
            if minute == 60:
                minute = 0
                hour += 1
            rounded_close_vn = est_close_vn.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if rounded_close_vn.hour == 14 and rounded_close_vn.minute == 45:
                bar_ts_vn = rounded_close_vn.replace(minute=30)
            else:
                bar_ts_vn = rounded_close_vn - timedelta(minutes=5)

            for sym in symbols:
                records.append({
                    "symbol": sym,
                    "bar_ts": bar_ts_vn,
                    "close_ts": rounded_close_vn,
                    "collector_lag_s": lag_ms / 1000.0,
                    "collector_log_dt": log_ts,
                })

    return records


def parse_engine_processed_bars(log_path: Path | str) -> list[dict]:
    """Đọc và giải mã các dòng 'bar processed' từ engine_alerts.log.

    Trong engine/main.py:
      alert("INFO", "bar processed", symbol=bar.symbol, ts=bar.ts.isoformat(), lag_ms=engine_lag_ms)
    """
    p = Path(log_path)
    if not p.is_file():
        return []

    records = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"bar processed"' not in line:
                continue
            line = line.strip()
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue

            try:
                log_ts = datetime.fromisoformat(parts[0])
                data = json.loads(parts[1])
                sym = data.get("symbol")
                ts_raw = data.get("ts")
                lag_ms = float(data.get("lag_ms", 0.0))
                if not sym or not ts_raw:
                    continue
                bar_ts = datetime.fromisoformat(ts_raw).astimezone(TZ)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

            records.append({
                "symbol": sym,
                "bar_ts": bar_ts,
                "engine_lag_s": lag_ms / 1000.0,
                "engine_log_dt": log_ts,
            })

    return records


def match_bar_latencies(
    collector_bars: list[dict],
    engine_bars: list[dict],
) -> list[dict]:
    """Ghép cặp nến giữa collector và engine theo khóa (symbol, bar_ts)."""
    # Nếu có trùng khóa trong cùng log (ví dụ restart ghi lại), lấy bản ghi cuối
    c_map = {(r["symbol"], r["bar_ts"]): r for r in collector_bars}
    e_map = {(r["symbol"], r["bar_ts"]): r for r in engine_bars}

    common_keys = sorted(set(c_map.keys()) & set(e_map.keys()), key=lambda k: (k[1], k[0]))

    matched = []
    for sym, bar_ts in common_keys:
        c = c_map[(sym, bar_ts)]
        e = e_map[(sym, bar_ts)]
        c_lag = c["collector_lag_s"]
        e_lag = e["engine_lag_s"]
        diff = e_lag - c_lag
        matched.append({
            "symbol": sym,
            "bar_ts": bar_ts,
            "collector_lag_s": c_lag,
            "engine_lag_s": e_lag,
            "engine_diff_s": diff,
        })

    return matched


def classify_timeframe(bar_ts: datetime) -> str:
    """Phân loại khung giờ trong phiên:

    - Mở cửa: 09:15 - 10:00
    - Giữa phiên: 10:05 - 11:30 & 13:00 - 14:15
    - Cuối phiên / ATC: 14:20 - 14:45
    """
    t = bar_ts.astimezone(TZ).time()
    if time(9, 15) <= t <= time(10, 0):
        return "1. Mở cửa (09:15 - 10:00)"
    if (time(10, 5) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(14, 15)):
        return "2. Giữa phiên (10:05 - 11:30 & 13:00 - 14:15)"
    if time(14, 20) <= t <= time(14, 45):
        return "3. Cuối phiên / ATC (14:20 - 14:45)"
    return "4. Ngoài phiên"


def print_summary_table(title: str, matched_items: list[dict]) -> None:
    """In bảng phân vị độ trễ (Collector, Engine, Hiệu số)."""
    n = len(matched_items)
    if n == 0:
        print(f"\n{title}: Không có nến nào")
        return

    c_lags = [it["collector_lag_s"] for it in matched_items]
    e_lags = [it["engine_lag_s"] for it in matched_items]
    diffs = [it["engine_diff_s"] for it in matched_items]

    c_p = compute_percentiles(c_lags)
    e_p = compute_percentiles(e_lags)
    d_p = compute_percentiles(diffs)

    print(f"\n{title} (n = {n} nến):")
    print(f"{'Đại lượng':<32} | {'p50':>8} | {'p90':>8} | {'p99':>8} | {'max':>8}")
    print("-" * 72)
    print(
        f"{'Collector (đóng nến -> publish)':<32} | {c_p['p50']:>7.3f}s | {c_p['p90']:>7.3f}s | {c_p['p99']:>7.3f}s | {c_p['max']:>7.3f}s"
    )
    print(
        f"{'Engine (đóng nến -> xử lý xong)':<32} | {e_p['p50']:>7.3f}s | {e_p['p90']:>7.3f}s | {e_p['p99']:>7.3f}s | {e_p['max']:>7.3f}s"
    )
    print(
        f"{'Hiệu số (phần engine cộng thêm)':<32} | {d_p['p50']:>7.3f}s | {d_p['p90']:>7.3f}s | {d_p['p99']:>7.3f}s | {d_p['max']:>7.3f}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Đo độ trễ xử lý nến giữa Collector và Engine (Brief đợt 79 Task 3)."
    )
    parser.add_argument(
        "--collector-log",
        default="logs/bars_closed.log",
        help="Đường dẫn file bars_closed.log (mặc định: logs/bars_closed.log)",
    )
    parser.add_argument(
        "--engine-log",
        default="logs/engine_alerts.log",
        help="Đường dẫn file engine_alerts.log (mặc định: logs/engine_alerts.log)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="In chi tiết từng nến ghép được",
    )
    args = parser.parse_args()

    c_bars = parse_collector_closed_bars(args.collector_log)
    e_bars = parse_engine_processed_bars(args.engine_log)

    print("=" * 88)
    print("  BÁO CÁO PHÂN TÍCH ĐỘ TRỄ XỬ LÝ NẾN (Brief đợt 79 Task 3)")
    print(f"  Nguồn collector: {args.collector_log} ({len(c_bars)} bản ghi nến)")
    print(f"  Nguồn engine:    {args.engine_log} ({len(e_bars)} bản ghi nến)")
    print("=" * 88)

    matched = match_bar_latencies(c_bars, e_bars)
    print(f"\nTổng số nến ghép cặp thành công: {len(matched)} / {len(e_bars)} nến engine")

    # 1. Bảng tổng thể
    print_summary_table("=== 1. TỔNG THỂ TOÀN BỘ DANH MỤC ===", matched)

    # 2. Tách theo từng mã
    symbols = sorted({it["symbol"] for it in matched})
    print("\n" + "=" * 88)
    print("=== 2. ĐỘ TRỄ TÁCH THEO TỪNG MÃ CỔ PHIẾU ===")
    print("=" * 88)
    for sym in symbols:
        sym_items = [it for it in matched if it["symbol"] == sym]
        print_summary_table(f"Mã {sym}", sym_items)

    # 3. Tách theo khung giờ trong phiên
    print("\n" + "=" * 88)
    print("=== 3. ĐỘ TRỄ TÁCH THEO KHUNG GIỜ TRONG PHIÊN ===")
    print("=" * 88)
    timeframes = sorted({classify_timeframe(it["bar_ts"]) for it in matched})
    for tf in timeframes:
        tf_items = [it for it in matched if classify_timeframe(it["bar_ts"]) == tf]
        print_summary_table(f"Khung giờ: {tf}", tf_items)

    # In 5 nến có độ trễ lớn nhất
    matched_by_lag = sorted(matched, key=lambda it: it["engine_lag_s"], reverse=True)
    print("\n" + "=" * 88)
    print("=== 4. TOP 5 NẾN CÓ ĐỘ TRỄ LỚN NHẤT ===")
    print("=" * 88)
    print(f"{'Mã':<6} | {'Bar timestamp (VN)':<20} | {'Collector lag':>14} | {'Engine lag':>12} | {'Hiệu số':>10}")
    print("-" * 72)
    for it in matched_by_lag[:5]:
        ts_str = it["bar_ts"].strftime("%Y-%m-%d %H:%M")
        print(
            f"{it['symbol']:<6} | {ts_str:<20} | {it['collector_lag_s']:>13.3f}s | {it['engine_lag_s']:>11.3f}s | {it['engine_diff_s']:>9.3f}s"
        )


if __name__ == "__main__":
    main()
