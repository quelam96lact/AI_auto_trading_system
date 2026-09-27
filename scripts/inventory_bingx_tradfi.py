"""Kiểm kê và phân tích chất lượng dữ liệu BingX TradFi (Brief đợt 114).

Không gọi bất kỳ endpoint nào cần chữ ký.
Không đặt lệnh.
Không đọc dữ liệu từ 2026-09-01 (dữ liệu tháng 09/2026 được niêm phong).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import requests

from trading.data_quality import is_dirty_bar_dict

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://open-api.bingx.com"

SYMBOLS = [
    "NCCOGOLD2USD-USDT",      # Vàng
    "NCCOXAG2USD-USDT",       # Bạc
    "NCCO1OILWTI2USD-USDT",   # Dầu WTI
    "NCSISP5002USD-USDT",     # S&P 500
    "NCSINASDAQ1002USD-USDT", # NASDAQ 100
    "NCFXEUR2USD-USDT",       # EUR/USD
    "NCFXUSD2JPY-USDT",       # USD/JPY
    "NCSKAAPL2USD-USDT",      # Apple
    "NCSKNVDA2USD-USDT",      # NVIDIA
    "BTC-USDT",               # Đối chứng (Crypto 24/7)
]


# ---------------------------------------------------------------------------
# 1. Các hàm phân tích thuần (Pure Functions - có Unit Test)
# ---------------------------------------------------------------------------

def build_hourly_profile_matrix(bars: list[dict]) -> list[list[int]]:
    """Xây dựng bảng ma trận 7x24 đếm số nến theo Thứ trong tuần (UTC) × Giờ (UTC).

    Thứ 2 = 0 ... Chủ Nhật = 6.
    Giờ: 0 .. 23.
    """
    matrix = [[0] * 24 for _ in range(7)]
    for b in bars:
        ts = b["ts"]
        if not isinstance(ts, datetime):
            continue
        dow = ts.weekday()  # 0 = Monday, 6 = Sunday
        hour = ts.hour
        matrix[dow][hour] += 1
    return matrix


def classify_trading_schedule(matrix: list[list[int]]) -> str:
    """Phân loại hồ sơ giờ giao dịch từ ma trận 7x24 UTC."""
    # Tính số slot (dow, hour) có nến > 0
    total_slots = 7 * 24
    active_slots = sum(1 for d in range(7) for h in range(24) if matrix[d][h] > 0)

    # Đếm số giờ hoạt động theo từng ngày
    active_hours_per_day = [sum(1 for h in range(24) if matrix[d][h] > 0) for d in range(7)]
    weekday_active = sum(active_hours_per_day[:5])  # Mon-Fri
    weekend_active = sum(active_hours_per_day[5:])  # Sat-Sun

    if active_slots >= total_slots * 0.90 and weekend_active >= 40:
        return "24/7 (Liên tục)"
    elif weekday_active >= 5 * 20 and weekend_active <= 10:
        return "24/5 (Toàn bộ ngày thường)"
    elif weekday_active > 0 and weekend_active <= 5:
        max_h = max(active_hours_per_day[:5]) if active_hours_per_day[:5] else 0
        return f"Phiên sở ({max_h}h/ngày)"
    else:
        return "Đặc thù / Gián đoạn"


def aggregate_1h_to_daily(bars_1h: list[dict]) -> dict[date, dict]:
    """Gộp các nến 1h thành nến ngày UTC (open, high, low, close cuối ngày, volume)."""
    groups: dict[date, list[dict]] = defaultdict(list)
    for b in bars_1h:
        ts = b["ts"]
        d = ts.date() if isinstance(ts, datetime) else ts
        groups[d].append(b)

    aggregated: dict[date, dict] = {}
    for d, b_list in groups.items():
        # Sắp xếp tăng dần theo thời gian
        sorted_bars = sorted(b_list, key=lambda x: x["ts"])
        aggregated[d] = {
            "open": sorted_bars[0]["open"],
            "high": max(b["high"] for b in sorted_bars),
            "low": min(b["low"] for b in sorted_bars),
            "close": sorted_bars[-1]["close"],  # Nến cuối cùng trong ngày
            "volume": sum(b["volume"] for b in sorted_bars),
            "count_1h": len(sorted_bars),
        }
    return aggregated


def compare_1h_aggregated_with_1d(
    agg_daily: dict[date, dict],
    bars_1d: list[dict],
    threshold: float = 0.001,
) -> list[dict]:
    """So sánh nến ngày gộp từ 1h với nến 1d thật trong DB.

    Trả về danh sách các ngày có độ lệch > threshold (0.1%).
    """
    mismatches = []
    # Index 1d bars by date
    bars_1d_map = {}
    for b in bars_1d:
        ts = b["ts"]
        d = ts.date() if isinstance(ts, datetime) else ts
        bars_1d_map[d] = b

    for d, agg in agg_daily.items():
        if d not in bars_1d_map:
            continue
        bar_1d = bars_1d_map[d]
        diffs = []

        close_1d = bar_1d["close"]
        if close_1d > 0:
            diff_close = abs(close_1d - agg["close"]) / close_1d
            if diff_close > threshold:
                diffs.append("close")

        high_1d = bar_1d["high"]
        if high_1d > 0:
            diff_high = abs(high_1d - agg["high"]) / high_1d
            if diff_high > threshold:
                diffs.append("high")

        low_1d = bar_1d["low"]
        if low_1d > 0:
            diff_low = abs(low_1d - agg["low"]) / low_1d
            if diff_low > threshold:
                diffs.append("low")

        if diffs:
            mismatches.append({
                "date": d,
                "diff_fields": diffs,
                "1d_close": close_1d,
                "agg_close": agg["close"],
                "1d_high": high_1d,
                "agg_high": agg["high"],
                "1d_low": low_1d,
                "agg_low": agg["low"],
                "count_1h": agg.get("count_1h", 0),
            })
    return mismatches


def detect_gaps(
    bars: list[dict],
    interval: str = "1h",
    matrix_7x24: list[list[int]] | None = None,
) -> tuple[int, list[dict]]:
    """Phát hiện các khoảng trống dữ liệu.

    Loại bỏ các khoảng nghỉ bình thường (dựa trên ma trận 7x24).
    Trả về: (số khoảng trống bất thường, top 10 khoảng trống bất thường dài nhất).
    """
    if len(bars) < 2:
        return 0, []

    sorted_bars = sorted(bars, key=lambda x: x["ts"])
    expected_delta = timedelta(hours=1) if interval == "1h" else timedelta(days=1)

    # Xác định các slot thường đóng cửa từ ma trận
    # Một slot bị coi là đóng thường lệ nếu số nến trong slot đó <= 5% giá trị max của ma trận
    closed_slots = set()
    if matrix_7x24:
        max_val = max(max(row) for row in matrix_7x24) if matrix_7x24 else 0
        threshold_count = max(1, int(max_val * 0.05))
        for d in range(7):
            for h in range(24):
                if matrix_7x24[d][h] < threshold_count:
                    closed_slots.add((d, h))

    abnormal_gaps = []

    for i in range(len(sorted_bars) - 1):
        curr_ts = sorted_bars[i]["ts"]
        next_ts = sorted_bars[i + 1]["ts"]
        diff = next_ts - curr_ts

        if diff > expected_delta:
            # Kiểm tra xem khoảng trống này có hoàn toàn rơi vào các slot thường đóng cửa không
            is_normal = False
            if interval == "1h" and closed_slots:
                # Kiểm tra các giờ ở giữa
                check_ts = curr_ts + timedelta(hours=1)
                all_closed = True
                while check_ts < next_ts:
                    if (check_ts.weekday(), check_ts.hour) not in closed_slots:
                        all_closed = False
                        break
                    check_ts += timedelta(hours=1)
                is_normal = all_closed

            if not is_normal:
                gap_hours = diff.total_seconds() / 3600.0
                abnormal_gaps.append({
                    "from_ts": curr_ts,
                    "to_ts": next_ts,
                    "gap_hours": gap_hours,
                    "gap_days": round(gap_hours / 24.0, 2),
                })

    abnormal_gaps.sort(key=lambda x: x["gap_hours"], reverse=True)
    return len(abnormal_gaps), abnormal_gaps[:10]


def count_dirty_and_zero_volume_bars(bars: list[dict]) -> tuple[int, int]:
    """Đếm số nến bẩn theo is_dirty_bar_dict và nến có volume = 0."""
    dirty_count = 0
    zero_vol_count = 0
    for b in bars:
        if is_dirty_bar_dict(b):
            dirty_count += 1
        if b.get("volume", 0) == 0:
            zero_vol_count += 1
    return dirty_count, zero_vol_count


def calculate_cost_to_atr_ratio(bars_1h: list[dict], taker_fee_rate: float) -> tuple[float, float, float]:
    """Tính ATR14 trung vị theo % giá, phí 2 chiều taker, và tỷ lệ phí/ATR1h.

    Trả về: (median_atr_pct, round_trip_fee_pct, fee_to_atr_ratio)
    """
    if len(bars_1h) < 15:
        return 0.0, taker_fee_rate * 2.0 * 100.0, 0.0

    sorted_bars = sorted(bars_1h, key=lambda x: x["ts"])
    trs = []
    for i in range(1, len(sorted_bars)):
        curr = sorted_bars[i]
        prev = sorted_bars[i - 1]
        tr = max(
            curr["high"] - curr["low"],
            abs(curr["high"] - prev["close"]),
            abs(curr["low"] - prev["close"]),
        )
        trs.append((curr["close"], tr))

    # Tính ATR14 đơn giản (Rolling SMA 14)
    atr_pcts = []
    for i in range(13, len(trs)):
        window_trs = [item[1] for item in trs[i - 13 : i + 1]]
        atr14 = sum(window_trs) / 14.0
        close_p = trs[i][0]
        if close_p > 0:
            atr_pcts.append((atr14 / close_p) * 100.0)

    median_atr_pct = statistics.median(atr_pcts) if atr_pcts else 0.0
    round_trip_fee_pct = 2.0 * taker_fee_rate * 100.0
    fee_to_atr_ratio = (round_trip_fee_pct / median_atr_pct) if median_atr_pct > 0 else 0.0

    return median_atr_pct, round_trip_fee_pct, fee_to_atr_ratio


def analyze_funding_history(funding_records: list[dict]) -> dict[str, Any]:
    """Phân tích lịch sử funding rate từ API BingX."""
    if not funding_records:
        return {
            "count": 0,
            "interval_hours": 0.0,
            "mean_rate": 0.0,
            "mean_abs_rate": 0.0,
        }

    rates = [float(r["fundingRate"]) for r in funding_records]
    times = [int(r["fundingTime"]) for r in funding_records]

    # Tính khoảng cách giữa các mốc
    intervals = []
    for i in range(len(times) - 1):
        diff_ms = abs(times[i] - times[i + 1])
        diff_h = diff_ms / 3600000.0
        if diff_h > 0:
            intervals.append(round(diff_h, 1))

    interval_mode = statistics.mode(intervals) if intervals else 0.0

    return {
        "count": len(rates),
        "interval_hours": interval_mode,
        "mean_rate": statistics.mean(rates) if rates else 0.0,
        "mean_abs_rate": statistics.mean(abs(r) for r in rates) if rates else 0.0,
    }


# ---------------------------------------------------------------------------
# 2. Truy vấn dữ liệu từ DB và API công khai (Public Unsigned Only)
# ---------------------------------------------------------------------------

def load_bars_from_db(conn: psycopg.Connection, symbol: str, interval: str) -> list[dict]:
    """Đọc nến từ bảng bars_crypto, giới hạn <= 2026-08-31 23:59:59 UTC."""
    sql = """
        SELECT symbol, interval, ts, open, high, low, close, volume, quote_volume, trades
        FROM bars_crypto
        WHERE symbol = %s AND interval = %s AND ts <= '2026-08-31 23:59:59+00'
        ORDER BY ts ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol, interval))
        rows = cur.fetchall()

    bars = []
    for r in rows:
        bars.append({
            "symbol": r[0],
            "interval": r[1],
            "ts": r[2],
            "open": float(r[3]),
            "high": float(r[4]),
            "low": float(r[5]),
            "close": float(r[6]),
            "volume": float(r[7]),
            "quote_volume": float(r[8]) if r[8] is not None else 0.0,
            "trades": int(r[9]) if r[9] is not None else 0,
        })
    return bars


def fetch_contracts_info() -> dict[str, dict]:
    """Lấy thông tin hợp đồng niêm yết từ API công khai BingX."""
    url = f"{BASE_URL}/openApi/swap/v2/quote/contracts"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json().get("data", [])
        return {c["symbol"]: c for c in data if isinstance(c, dict)}
    except Exception as e:
        print(f"[Warning] Không tải được thông tin contracts: {e}", file=sys.stderr)
        return {}


def fetch_funding_history_api(symbol: str, limit: int = 100) -> list[dict]:
    """Lấy lịch sử funding rate từ API công khai BingX."""
    url = f"{BASE_URL}/openApi/swap/v2/quote/fundingRate"
    try:
        resp = requests.get(url, params={"symbol": symbol, "limit": limit}, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", [])
        return []
    except Exception as e:
        print(f"[Warning] Lỗi khi gọi fundingRate cho {symbol}: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# 3. Luồng chính thực thi kiểm kê
# ---------------------------------------------------------------------------

def run_inventory(dsn: str | None = None) -> dict[str, Any]:
    """Chạy toàn bộ quy trình kiểm kê cho 10 mã."""
    conn_dsn = resolve_dsn(dsn)
    contracts = fetch_contracts_info()

    report_data = []

    with psycopg.connect(conn_dsn) as conn:
        for symbol in SYMBOLS:
            c_info = contracts.get(symbol, {})
            launch_ms = c_info.get("launchTime")
            launch_str = datetime.fromtimestamp(launch_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d") if launch_ms else "N/A"
            status = c_info.get("status", "N/A")
            taker_fee = float(c_info.get("takerFeeRate", 0.0005))

            # 1. Đọc dữ liệu DB
            bars_1d = load_bars_from_db(conn, symbol, "1d")
            bars_1h = load_bars_from_db(conn, symbol, "1h")

            n_1d = len(bars_1d)
            n_1h = len(bars_1h)

            cal_days_1d = (bars_1d[-1]["ts"].date() - bars_1d[0]["ts"].date()).days + 1 if bars_1d else 0
            cal_days_1h = (bars_1h[-1]["ts"].date() - bars_1h[0]["ts"].date()).days + 1 if bars_1h else 0

            # 2. Hồ sơ giờ giao dịch (khung 1h)
            matrix_7x24 = build_hourly_profile_matrix(bars_1h)
            schedule_type = classify_trading_schedule(matrix_7x24) if bars_1h else "Không có dữ liệu (pause)"

            # 3. Khoảng trống bất thường
            abnormal_gaps_count, top_10_gaps = detect_gaps(bars_1h, interval="1h", matrix_7x24=matrix_7x24)

            # 4. Nến bẩn và volume 0
            dirty_1d, zero_vol_1d = count_dirty_and_zero_volume_bars(bars_1d)
            dirty_1h, zero_vol_1h = count_dirty_and_zero_volume_bars(bars_1h)

            # 5. Đối chiếu 1h -> 1d
            agg_1d = aggregate_1h_to_daily(bars_1h)
            mismatches = compare_1h_aggregated_with_1d(agg_1d, bars_1d, threshold=0.001)

            # 6. Funding
            funding_records = fetch_funding_history_api(symbol, limit=100)
            funding_res = analyze_funding_history(funding_records)

            # 7. Chi phí so với biến động
            median_atr_pct, round_trip_fee_pct, fee_to_atr_ratio = calculate_cost_to_atr_ratio(bars_1h, taker_fee)

            # 8. Đánh giá đủ/không đủ điều kiện đo
            # Ngưỡng:
            # - Đo khung ngày: >= 3 năm (>= 1095 ngày lịch)
            # - Đo khung giờ: >= 1 năm (>= 365 ngày lịch) và abnormal_gaps_count / n_1h < 1%
            gap_pct = (abnormal_gaps_count / n_1h * 100.0) if n_1h > 0 else 0.0

            eligible_daily = cal_days_1d >= 1095
            eligible_hourly = (cal_days_1h >= 365) and (gap_pct < 1.0)

            report_data.append({
                "symbol": symbol,
                "status": status,
                "launch_date": launch_str,
                "n_1d": n_1d,
                "cal_days_1d": cal_days_1d,
                "earliest_1d": bars_1d[0]["ts"].strftime("%Y-%m-%d") if bars_1d else "N/A",
                "latest_1d": bars_1d[-1]["ts"].strftime("%Y-%m-%d") if bars_1d else "N/A",
                "n_1h": n_1h,
                "cal_days_1h": cal_days_1h,
                "earliest_1h": bars_1h[0]["ts"].strftime("%Y-%m-%d") if bars_1h else "N/A",
                "latest_1h": bars_1h[-1]["ts"].strftime("%Y-%m-%d") if bars_1h else "N/A",
                "schedule_type": schedule_type,
                "matrix_7x24": matrix_7x24,
                "abnormal_gaps_count": abnormal_gaps_count,
                "gap_pct": gap_pct,
                "top_10_gaps": top_10_gaps,
                "dirty_1d": dirty_1d,
                "zero_vol_1d": zero_vol_1d,
                "dirty_1h": dirty_1h,
                "zero_vol_1h": zero_vol_1h,
                "mismatches_count": len(mismatches),
                "mismatches": mismatches[:5],
                "funding_count": funding_res["count"],
                "funding_interval_h": funding_res["interval_hours"],
                "funding_mean": funding_res["mean_rate"],
                "funding_mean_abs": funding_res["mean_abs_rate"],
                "taker_fee": taker_fee,
                "round_trip_fee_pct": round_trip_fee_pct,
                "median_atr_pct": median_atr_pct,
                "fee_to_atr_ratio": fee_to_atr_ratio,
                "eligible_daily": eligible_daily,
                "eligible_hourly": eligible_hourly,
            })

    return {"symbols": report_data}


def print_report_tables(report_dict: dict[str, Any]) -> None:
    """In các bảng theo thể thức yêu cầu của Brief 114."""
    data = report_dict["symbols"]

    print("=" * 115)
    print("BẢNG CHÍNH: TỔNG HỢP KIỂM KÊ DỮ LIỆU BINGX TRADFI (ĐỢT 114)")
    print("=" * 115)
    headers = [
        "Mã", "Niêm yết", "Nến 1d", "Nến 1h", "Hồ sơ giờ", "Khoảng trống", "Nến bẩn", "Funding (CK, TB)", "Phí/ATR1h", "Đủ đo?"
    ]
    fmt = "{:<22} | {:<10} | {:>7} | {:>7} | {:<18} | {:>12} | {:>7} | {:<16} | {:>9} | {:<10}"
    print(fmt.format(*headers))
    print("-" * 115)

    for item in data:
        sym = item["symbol"]
        launch = item["launch_date"]
        n_1d = f"{item['n_1d']} ({item['cal_days_1d']}d)"
        n_1h = f"{item['n_1h']} ({item['cal_days_1h']}d)"
        sched = item["schedule_type"]
        gaps = f"{item['abnormal_gaps_count']} ({item['gap_pct']:.1f}%)" if item['n_1h'] > 0 else "N/A"
        dirty = f"{item['dirty_1h']} (1h)"
        fund = f"{item['funding_interval_h']:.0f}h, {item['funding_mean']*100:+.4f}%" if item['funding_count'] > 0 else "Không có"
        cost = f"{item['fee_to_atr_ratio']*100:.1f}%" if item['median_atr_pct'] > 0 else "N/A"

        elig = []
        if item["eligible_daily"]:
            elig.append("1D")
        if item["eligible_hourly"]:
            elig.append("1H")
        elig_str = "+".join(elig) if elig else "KHÔNG ĐỦ"

        print(fmt.format(
            sym, launch, n_1d, n_1h, sched, gaps, dirty, fund, cost, elig_str
        ))
    print("=" * 115)

    # In chi tiết 7x24 cho từng mã
    print("\n" + "=" * 115)
    print("CHI TIẾT HỒ SƠ GIỜ GIAO DỊCH 7x24 (UTC) TỪNG MÃ:")
    print("=" * 115)
    day_names = ["Thứ 2 (Mon)", "Thứ 3 (Tue)", "Thứ 4 (Wed)", "Thứ 5 (Thu)", "Thứ 6 (Fri)", "Thứ 7 (Sat)", "CN (Sun)"]
    for item in data:
        sym = item["symbol"]
        matrix = item["matrix_7x24"]
        print(f"\n--- {sym} (Lịch trình: {item['schedule_type']}) ---")
        if item["n_1h"] == 0:
            print("  (Không có dữ liệu 1h do sàn pause cuối tuần hoặc chưa giao dịch)")
            continue

        header_hours = "      " + " ".join(f"{h:02d}" for h in range(24))
        print(header_hours)
        for d, d_name in enumerate(day_names):
            row_str = " ".join(f"{matrix[d][h]:2d}" if matrix[d][h] > 0 else " ." for h in range(24))
            print(f"{d_name[:6]:<6} {row_str}")

        if item["top_10_gaps"]:
            print("  Top khoảng trống bất thường:")
            for g in item["top_10_gaps"][:3]:
                print(f"    - Từ {g['from_ts']} đến {g['to_ts']} ({g['gap_hours']:.1f}h / {g['gap_days']} ngày)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Kiểm kê dữ liệu BingX TradFi")
    ap.add_argument("--dsn", default=None, help="Postgres DSN")
    args = ap.parse_args()

    report = run_inventory(args.dsn)
    print_report_tables(report)


if __name__ == "__main__":
    main()
