"""Đo chi phí giữ vị thế forex perp BingX và so sánh với biên độ ngày (Brief đợt 116).

Tuân thủ nghiêm ngặt:
- Không commit, không push, không đặt lệnh.
- Không sửa trading/, bars, bars_daily, bars_ext_daily: chỉ đọc.
- Không gọi endpoint có ký. Cấm đặt/hủy/sửa lệnh. Cấm in secret.
- Niêm phong: chỉ nạp và chỉ đọc dữ liệu đến hết 2026-08-31 23:59:59 UTC.
- Cấm hằng số vô nguồn: mọi số liệu về phí, chu kỳ, tỷ lệ đều từ API/tài liệu chính thức.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.request
from datetime import UTC, datetime
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEALED_MAX_TIMESTAMP_MS = 1788220799000  # 2026-08-31 23:59:59 UTC
SEALED_MAX_DATE_STR = "2026-08-31"
ATR_PERIOD = 14

URL_CONTRACTS_API = "https://open-api.bingx.com/openApi/swap/v2/quote/contracts"
URL_FUNDING_API = "https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate"
DOC_URL_CONTRACTS = "https://bingx-api.github.io/docs/#/swap/market-api (Contract Information)"
DOC_URL_FUNDING = "https://bingx-api.github.io/docs/#/swap/market-api (Get Funding Rate History)"


# ---------------------------------------------------------------------------
# 1. Các hàm thuần toán học & thống kê có Unit Test
# ---------------------------------------------------------------------------

def compute_funding_interval_hours(funding_times_ms: list[int]) -> dict[str, Any]:
    """Tính chu kỳ funding giữa các mốc fundingTime liên tiếp (đổi ra giờ).

    Trả về:
    - median_hours: trung vị khoảng cách đổi ra giờ
    - deviated_count: số mốc lệch khỏi trung vị
    - intervals: danh sách khoảng cách giữa các mốc
    """
    if len(funding_times_ms) < 2:
        return {
            "median_hours": 0.0,
            "deviated_count": 0,
            "intervals": [],
        }

    sorted_ts = sorted(funding_times_ms)
    intervals = [
        (sorted_ts[i] - sorted_ts[i - 1]) / 3_600_000.0
        for i in range(1, len(sorted_ts))
    ]

    median_hours = statistics.median(intervals)
    deviated = sum(1 for d in intervals if abs(d - median_hours) > 1e-6)

    return {
        "median_hours": median_hours,
        "deviated_count": deviated,
        "intervals": intervals,
    }


def convert_funding_rate_to_daily_pct(rate: float, interval_hours: float) -> float:
    """Quy đổi funding rate mỗi chu kỳ sang %/ngày.

    Công thức: rate * (24.0 / interval_hours) * 100.0
    Ví dụ: rate = 0.000040, interval = 8h -> 0.000040 * 3 * 100 = 0.0120% / ngày.
    """
    if interval_hours <= 0:
        raise ValueError(f"interval_hours must be positive, got {interval_hours}")
    return rate * (24.0 / interval_hours) * 100.0


def _get_percentile(data: list[float], p: float) -> float:
    """Tính phân vị p (0.0 đến 1.0) theo nội suy tuyến tính."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    if len(sorted_d) == 1:
        return sorted_d[0]
    k = (len(sorted_d) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_d[int(k)]
    return sorted_d[f] * (c - k) + sorted_d[c] * (k - f)


def compute_funding_distribution_daily_pct(
    funding_rates: list[float],
    interval_hours: float,
) -> dict[str, float]:
    """Tính phân phối funding rate theo %/ngày: mean có dấu, mean tuyệt đối, P5, P95."""
    if not funding_rates:
        return {
            "mean_daily_signed_pct": 0.0,
            "mean_daily_abs_pct": 0.0,
            "p5_daily_pct": 0.0,
            "p95_daily_pct": 0.0,
        }

    daily_rates = [
        convert_funding_rate_to_daily_pct(r, interval_hours)
        for r in funding_rates
    ]
    abs_daily_rates = [abs(r) for r in daily_rates]

    return {
        "mean_daily_signed_pct": statistics.mean(daily_rates),
        "mean_daily_abs_pct": statistics.mean(abs_daily_rates),
        "p5_daily_pct": _get_percentile(daily_rates, 0.05),
        "p95_daily_pct": _get_percentile(daily_rates, 0.95),
    }


def compute_roundtrip_taker_fee_pct(taker_fee_rate: float) -> float:
    """Tính phí một vòng taker (mở lệnh + đóng lệnh) theo %.

    Công thức: 2 * takerFeeRate * 100.0 (%)
    Ví dụ: takerFeeRate = 0.0005 -> phí 1 vòng = 0.1000%.
    """
    return 2.0 * taker_fee_rate * 100.0


def compute_daily_amplitude_pct(prices: list[float]) -> float:
    """Tính biên độ ngày: trung vị |lợi suất ngày| tính bằng %.

    Công thức: r_t = (P_t / P_{t-1}) - 1, tính trung vị của |r_t| * 100.0.
    """
    if len(prices) < 2:
        return 0.0
    abs_returns = [
        abs(prices[i] / prices[i - 1] - 1.0) * 100.0
        for i in range(1, len(prices))
        if prices[i - 1] > 0
    ]
    if not abs_returns:
        return 0.0
    return statistics.median(abs_returns)


def compute_cost_to_amplitude_ratio(fee_pct: float, daily_amplitude_pct: float) -> float:
    """Tính tỷ lệ % của phí so với biên độ ngày của tài sản gốc."""
    if daily_amplitude_pct <= 0:
        return 0.0
    return (fee_pct / daily_amplitude_pct) * 100.0


def compute_holding_cost_ratio(
    roundtrip_taker_fee_pct: float,
    daily_funding_abs_pct: float,
    daily_amplitude_pct: float,
    hold_days: int,
) -> float:
    """Tính tỷ lệ % chi phí giữ vị thế H ngày so với biên độ ngày gốc.

    Công thức: (2 * takerFeeRate + H * funding_trung_binh_tuyet_doi) / bien_do_ngay * 100%
    """
    if daily_amplitude_pct <= 0:
        return 0.0
    total_cost = roundtrip_taker_fee_pct + hold_days * daily_funding_abs_pct
    return (total_cost / daily_amplitude_pct) * 100.0


def compute_atr14_series_pct(bars: list[dict[str, float]]) -> dict[str, float]:
    """Tính ATR14 của nến 1d theo % Close.

    TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    ATR14 = SMA(TR, 14) / Close * 100%
    """
    if len(bars) < 15:
        raise ValueError(
            f"ATR14 can it nhat 15 nen, chi co {len(bars)}. "
            "Khong tra 0.0 vi 0.0 nghia la 'khong bien dong', khac han 'khong do duoc'."
        )

    trs: list[float] = []
    atr_pcts: list[float] = []

    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        c = bars[i]["close"]
        prev_c = bars[i - 1]["close"]

        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)

        if len(trs) >= ATR_PERIOD:
            atr = statistics.mean(trs[-ATR_PERIOD:])
            if c <= 0:
                raise ValueError(f"Nen thu {i} co close={c} <= 0: nen ban, khong tinh ATR")
            atr_pcts.append((atr / c) * 100.0)

    if not atr_pcts:
        raise ValueError("Khong tinh duoc ATR14 nao tu chuoi nen da cho")

    return {
        "median_atr14_pct": statistics.median(atr_pcts),
        "mean_atr14_pct": statistics.mean(atr_pcts),
    }


# ---------------------------------------------------------------------------
# 2. Truy xuất dữ liệu từ API và DB
# ---------------------------------------------------------------------------

def _robust_urlopen_json(url: str, retries: int = 5, delay: float = 1.0) -> dict[str, Any]:
    """Gọi HTTP GET và parse JSON có cơ chế retry tự động chống lỗi mạng/DNS tạm thời."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("code") == 0:
                    return data
                # Nếu API trả mã khác 0 (ví dụ rate limit), đợi rồi retry
                last_err = RuntimeError(f"API returned code {data.get('code')}: {data.get('msg')}")
        except Exception as e:
            last_err = e
        time.sleep(delay * (attempt + 1))

    raise RuntimeError(f"Gọi {url} thất bại sau {retries} lần thử: {last_err}")


def fetch_bingx_contract_info(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Lấy thông tin hợp đồng từ GET /openApi/swap/v2/quote/contracts.

    Tuyệt đối không dùng giá trị mặc định nếu thiếu trường, mà raise lỗi.
    """
    data = _robust_urlopen_json(URL_CONTRACTS_API)

    items = data.get("data")
    if items is None:
        raise RuntimeError("Missing 'data' field in contracts response")

    result: dict[str, dict[str, Any]] = {}
    target_set = set(symbols)

    for item in items:
        sym = item.get("symbol")
        if sym in target_set:
            # Kiểm tra nghiêm ngặt sự hiện diện của các trường bắt buộc
            required_keys = [
                "takerFeeRate", "makerFeeRate", "pricePrecision",
                "quantityPrecision", "tradeMinQuantity", "tradeMinUSDT",
            ]
            for k in required_keys:
                if k not in item or item[k] is None:
                    raise KeyError(f"Trường bắt buộc '{k}' không có trong API response cho mã {sym}")

            result[sym] = {
                "symbol": sym,
                "takerFeeRate": float(item["takerFeeRate"]),
                "makerFeeRate": float(item["makerFeeRate"]),
                "pricePrecision": int(item["pricePrecision"]),
                "quantityPrecision": int(item["quantityPrecision"]),
                "tradeMinQuantity": float(item["tradeMinQuantity"]),
                "tradeMinUSDT": float(item["tradeMinUSDT"]),
            }

    for sym in symbols:
        if sym not in result:
            raise RuntimeError(f"Không tìm thấy mã {sym} trong danh sách hợp đồng BingX")

    return result


def fetch_bingx_funding_history(
    symbol: str,
    max_ts_ms: int = SEALED_MAX_TIMESTAMP_MS,
) -> list[dict[str, Any]]:
    """Lấy toàn bộ lịch sử funding rate từ BingX API up to max_ts_ms (<= 2026-08-31 23:59:59 UTC).

    Phân trang bằng tham số endTime. Có retry chống nghẽn mạng/rate-limit.
    """
    records: list[dict[str, Any]] = []
    end_time = max_ts_ms

    while True:
        url = f"{URL_FUNDING_API}?symbol={symbol}&limit=1000&endTime={end_time}"
        items: list[dict[str, Any]] = []

        # Cơ chế retry đặc biệt: Một số node của BingX có cache chỉ trả 418 mốc thay vì 1000 mốc
        for attempt in range(5):
            data = _robust_urlopen_json(url)
            if data.get("code") != 0:
                raise RuntimeError(f"BingX fundingRate API error {data.get('code')}: {data.get('msg')}")

            raw_items = data.get("data")
            items = raw_items if raw_items is not None else []

            if end_time == max_ts_ms and 300 < len(items) < 800:
                time.sleep(0.5)
                continue
            break

        if not items:
            break

        # Đảm bảo tuyệt đối không có bản ghi nào vượt mốc niêm phong
        valid_items = [it for it in items if int(it["fundingTime"]) <= max_ts_ms]
        records.extend(valid_items)

        if len(items) < 1000:
            break

        oldest_ts = int(items[-1]["fundingTime"])
        if oldest_ts >= end_time:
            break
        end_time = oldest_ts - 1
        time.sleep(0.3)

    # Loại bỏ bản ghi trùng nếu có theo fundingTime
    seen_ts = set()
    dedup: list[dict[str, Any]] = []
    for r in records:
        ts = int(r["fundingTime"])
        if ts not in seen_ts:
            seen_ts.add(ts)
            dedup.append(r)

    # Sắp xếp tăng dần theo thời gian
    dedup.sort(key=lambda x: int(x["fundingTime"]))
    return dedup


def load_ext_daily_prices(
    conn: psycopg.Connection,
    source: str,
    symbol: str,
    date_from: str | None = None,
) -> list[float]:
    """Đọc chuỗi giá đóng cửa tài sản gốc từ bars_ext_daily up to 2026-08-31."""
    sql = """
        SELECT close
        FROM bars_ext_daily
        WHERE source = %s AND symbol = %s AND date <= %s
          AND (%s::date IS NULL OR date >= %s::date)
        ORDER BY date ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source, symbol, SEALED_MAX_DATE_STR, date_from, date_from))
        return [float(r[0]) for r in cur.fetchall()]


def first_bingx_date(conn: psycopg.Connection, symbol: str) -> str:
    """Ngay co nen 1d dau tien cua ma BingX. Khong co nen thi raise, khong tra mac dinh."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT min(ts)::date FROM bars_crypto WHERE symbol = %s AND interval = '1d'",
            (symbol,),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(f"Khong co nen 1d nao cho {symbol} trong bars_crypto")
    return row[0].isoformat()


def load_bingx_daily_bars(
    conn: psycopg.Connection,
    symbol: str,
) -> list[dict[str, float]]:
    """Đọc nến 1d của BingX từ bars_crypto up to 2026-08-31 23:59:59 UTC."""
    sql = """
        SELECT open, high, low, close
        FROM bars_crypto
        WHERE symbol = %s AND interval = '1d' AND ts <= '2026-08-31 23:59:59+00'
        ORDER BY ts ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol,))
        return [
            {
                "open": float(r[0]),
                "high": float(r[1]),
                "low": float(r[2]),
                "close": float(r[3]),
            }
            for r in cur.fetchall()
        ]


# ---------------------------------------------------------------------------
# 3. Phân tích tổng hợp và In báo cáo
# ---------------------------------------------------------------------------

def run_cost_analysis(dsn: str | None = None) -> dict[str, Any]:
    """Thực thi đầy đủ phép đo chi phí Task B và trả về kết quả cấu trúc."""
    resolved_dsn = resolve_dsn(dsn)

    symbols = ["NCFXEUR2USD-USDT", "NCFXUSD2JPY-USDT"]

    # 1. Lấy thông tin hợp đồng từ API
    contract_info = fetch_bingx_contract_info(symbols)

    # 2. Lấy lịch sử funding từ API
    funding_data: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols:
        funding_data[sym] = fetch_bingx_funding_history(sym)

    # 3. Đọc dữ liệu từ DB
    with psycopg.connect(resolved_dsn) as conn:
        ext_frb_eur = load_ext_daily_prices(conn, "FRB_H10", "EURUSD")
        ext_ecb_eur = load_ext_daily_prices(conn, "ECB", "EURUSD")
        ext_frb_jpy = load_ext_daily_prices(conn, "FRB_H10", "USDJPY")

        # Mau so thu hai: CUNG cua so thoi gian ma BingX co nen.
        # Bien do EURUSD giai doan 2025-2026 thap hon han trung binh 27 nam,
        # nen dung mau so 27 nam se lam ty le chi phi bi NHE di.
        eur_from = first_bingx_date(conn, "NCFXEUR2USD-USDT")
        jpy_from = first_bingx_date(conn, "NCFXUSD2JPY-USDT")
        ext_frb_eur_ov = load_ext_daily_prices(conn, "FRB_H10", "EURUSD", date_from=eur_from)
        ext_frb_jpy_ov = load_ext_daily_prices(conn, "FRB_H10", "USDJPY", date_from=jpy_from)

        bingx_eur_bars = load_bingx_daily_bars(conn, "NCFXEUR2USD-USDT")
        bingx_jpy_bars = load_bingx_daily_bars(conn, "NCFXUSD2JPY-USDT")

    # 4. Tính toán các chỉ số cho từng mã
    results: dict[str, Any] = {}

    configs = [
        {
            "symbol": "NCFXEUR2USD-USDT",
            "name": "EUR/USD",
            "bars": bingx_eur_bars,
            "ext_primary_name": "FRB_H10 EURUSD",
            "ext_primary_prices": ext_frb_eur,
            "ext_secondary_name": "ECB EURUSD",
            "ext_secondary_prices": ext_ecb_eur,
            "ext_overlap_prices": ext_frb_eur_ov,
            "overlap_from": eur_from,
        },
        {
            "symbol": "NCFXUSD2JPY-USDT",
            "name": "USD/JPY",
            "bars": bingx_jpy_bars,
            "ext_primary_name": "FRB_H10 USDJPY",
            "ext_primary_prices": ext_frb_jpy,
            "ext_secondary_name": None,
            "ext_secondary_prices": None,
            "ext_overlap_prices": ext_frb_jpy_ov,
            "overlap_from": jpy_from,
        },
    ]

    for cfg in configs:
        sym = cfg["symbol"]
        c_info = contract_info[sym]
        f_list = funding_data[sym]

        f_times = [int(x["fundingTime"]) for x in f_list]
        if not f_times:
            raise RuntimeError(f"Khong lay duoc mot moc funding nao cho {sym}")
        f_rates = [float(x["fundingRate"]) for x in f_list]

        # Chu kỳ funding
        interval_stats = compute_funding_interval_hours(f_times)
        interv_h = interval_stats["median_hours"]

        # Phân phối funding %/ngày
        f_dist = compute_funding_distribution_daily_pct(f_rates, interv_h)

        # Phí một vòng taker
        rt_taker_fee = compute_roundtrip_taker_fee_pct(c_info["takerFeeRate"])

        # Biên độ ngày tài sản gốc
        ext_prim_amp = compute_daily_amplitude_pct(cfg["ext_primary_prices"])
        ext_sec_amp = (
            compute_daily_amplitude_pct(cfg["ext_secondary_prices"])
            if cfg["ext_secondary_prices"]
            else None
        )

        # Biên độ ngày BingX perp
        bingx_prices = [b["close"] for b in cfg["bars"]]
        bingx_amp = compute_daily_amplitude_pct(bingx_prices)

        # ATR14 của BingX
        atr_stats = compute_atr14_series_pct(cfg["bars"])

        # Tỷ lệ phí vòng / biên độ ngày gốc (theo ext_primary)
        ratio_fee_to_amp = compute_cost_to_amplitude_ratio(rt_taker_fee, ext_prim_amp)

        # Mẫu số thứ hai: biên độ tài sản gốc CHỈ trên cửa sổ BingX có dữ liệu
        ext_overlap_amp = compute_daily_amplitude_pct(cfg["ext_overlap_prices"])
        ratio_fee_to_amp_overlap = compute_cost_to_amplitude_ratio(rt_taker_fee, ext_overlap_amp)

        # Tỷ lệ chi phí giữ H ngày / biên độ ngày gốc (H = 1, 3, 5, 10)
        holding_ratios: dict[int, float] = {}
        holding_ratios_overlap: dict[int, float] = {}
        mean_abs_f_daily = f_dist["mean_daily_abs_pct"]
        for h in [1, 3, 5, 10]:
            holding_ratios[h] = compute_holding_cost_ratio(
                roundtrip_taker_fee_pct=rt_taker_fee,
                daily_funding_abs_pct=mean_abs_f_daily,
                daily_amplitude_pct=ext_prim_amp,
                hold_days=h,
            )
            holding_ratios_overlap[h] = compute_holding_cost_ratio(
                roundtrip_taker_fee_pct=rt_taker_fee,
                daily_funding_abs_pct=mean_abs_f_daily,
                daily_amplitude_pct=ext_overlap_amp,
                hold_days=h,
            )

        results[sym] = {
            "name": cfg["name"],
            "contract_info": c_info,
            "funding_count": len(f_list),
            "funding_first_ms": min(f_times),
            "funding_last_ms": max(f_times),
            "funding_interval_stats": interval_stats,
            "funding_dist": f_dist,
            "roundtrip_taker_fee_pct": rt_taker_fee,
            "ext_primary_name": cfg["ext_primary_name"],
            "ext_primary_amp": ext_prim_amp,
            "ext_secondary_name": cfg["ext_secondary_name"],
            "ext_secondary_amp": ext_sec_amp,
            "bingx_amp": bingx_amp,
            "atr_stats": atr_stats,
            "ratio_fee_to_amp": ratio_fee_to_amp,
            "holding_ratios": holding_ratios,
            "overlap_from": cfg["overlap_from"],
            "ext_overlap_amp": ext_overlap_amp,
            "ratio_fee_to_amp_overlap": ratio_fee_to_amp_overlap,
            "holding_ratios_overlap": holding_ratios_overlap,
        }

    return results


def print_cost_report(res: dict[str, Any]) -> None:
    """In đầy đủ các bảng dữ liệu của Task B (§1 Brief 116)."""
    print("\n" + "=" * 100)
    print("BÁO CÁO TASK B: CHI PHÍ GIỮ VỊ THẾ FOREX PERP BINGX (BRIEF ĐỢT 116)")
    print("=" * 100)

    # 1. Bảng thông số hợp đồng
    print("\n1. THÔNG SỐ HỢP ĐỒNG TỪ API BINGX (/openApi/swap/v2/quote/contracts):")
    print(f"URL Nguồn: {DOC_URL_CONTRACTS}")
    headers1 = [
        "Mã perp", "Tên", "Maker Fee", "Taker Fee", "Phí 1 vòng Taker",
        "Price Prec", "Qty Prec", "Min Qty", "Min USDT",
    ]
    fmt1 = "{:<18} | {:<8} | {:>9} | {:>9} | {:>16} | {:>10} | {:>8} | {:>8} | {:>8}"
    print("-" * 105)
    print(fmt1.format(*headers1))
    print("-" * 105)
    for sym, d in res.items():
        ci = d["contract_info"]
        print(fmt1.format(
            sym,
            d["name"],
            f"{ci['makerFeeRate']*100:.3f}%",
            f"{ci['takerFeeRate']*100:.3f}%",
            f"{d['roundtrip_taker_fee_pct']:.3f}%",
            str(ci["pricePrecision"]),
            str(ci["quantityPrecision"]),
            str(ci["tradeMinQuantity"]),
            str(ci["tradeMinUSDT"]),
        ))
    print("-" * 105)

    # 2. Bảng thống kê Funding Rate
    print("\n2. THỐNG KÊ FUNDING RATE (GET /openApi/swap/v2/quote/fundingRate, up to 2026-08-31):")
    print(f"URL Nguồn: {DOC_URL_FUNDING}")
    headers2 = [
        "Mã perp", "Số mốc", "Chu kỳ", "Mốc lệch",
        "Mean có dấu (%/ngày)", "Mean |abs| (%/ngày)", "P5 (%/ngày)", "P95 (%/ngày)",
    ]
    fmt2 = "{:<18} | {:>7} | {:>7} | {:>8} | {:>20} | {:>18} | {:>12} | {:>12}"
    print("-" * 115)
    print(fmt2.format(*headers2))
    print("-" * 115)
    for sym, d in res.items():
        fdist = d["funding_dist"]
        fint = d["funding_interval_stats"]
        print(fmt2.format(
            sym,
            str(d["funding_count"]),
            f"{fint['median_hours']:.1f}h",
            str(fint["deviated_count"]),
            f"{fdist['mean_daily_signed_pct']:+.6f}%",
            f"{fdist['mean_daily_abs_pct']:.6f}%",
            f"{fdist['p5_daily_pct']:+.6f}%",
            f"{fdist['p95_daily_pct']:+.6f}%",
        ))
    print("-" * 115)
    print("Chú thích hướng dấu funding: fundingRate > 0 nghĩa là bên Long trả cho bên Short.")

    # 3. Bảng biên độ ngày và chi phí giữ vị thế
    print("\n3. BIÊN ĐỘ NGÀY VÀ CHI PHÍ GIỮ VỊ THẾ SO VỚI BIÊN ĐỘ GỐC:")
    headers3 = [
        "Mã", "Biên độ gốc (trung vị)", "Biên độ BingX", "ATR14 BingX",
        "Phí vòng / BĐ gốc", "Giữ 1d / BĐ", "Giữ 3d / BĐ", "Giữ 5d / BĐ", "Giữ 10d / BĐ",
    ]
    fmt3 = "{:<8} | {:<22} | {:>13} | {:>12} | {:>17} | {:>11} | {:>11} | {:>11} | {:>12}"
    print("-" * 125)
    print(fmt3.format(*headers3))
    print("-" * 125)
    for sym, d in res.items():
        ext_desc = f"{d['ext_primary_amp']:.4f}% ({d['ext_primary_name']})"
        hr = d["holding_ratios"]
        print(fmt3.format(
            d["name"],
            ext_desc,
            f"{d['bingx_amp']:.4f}%",
            f"{d['atr_stats']['median_atr14_pct']:.4f}%",
            f"{d['ratio_fee_to_amp']:.2f}%",
            f"{hr[1]:.2f}%",
            f"{hr[3]:.2f}%",
            f"{hr[5]:.2f}%",
            f"{hr[10]:.2f}%",
        ))
    print("-" * 125)

    print()
    print("=" * 125)
    print("CỬA SỔ FUNDING THỰC SỰ LẤY ĐƯỢC — ĐỌC TRƯỚC KHI DÙNG SỐ CHI PHÍ")
    print("BingX tra lich su funding KHONG on dinh giua cac lan goi (cac node tra do sau khac nhau).")
    print("Moi lan do phai in lai cua so nay; neu no ngan hon cua so nen thi so chi phi CHUA phai")
    print("trung binh ca doi hop dong, va se doi giua cac lan chay.")
    print("=" * 125)
    fmt_cov = "{:<19}| {:>8}| {:<12}| {:<12}| {:<12}| {:<22}"
    print(fmt_cov.format("Mã perp", "Số mốc", "Mốc đầu", "Mốc cuối", "Nến 1d từ", "Funding phủ hết nến?"))
    print("-" * 125)
    for sym, d in res.items():
        first = datetime.fromtimestamp(d["funding_first_ms"] / 1000, tz=UTC).date().isoformat()
        last = datetime.fromtimestamp(d["funding_last_ms"] / 1000, tz=UTC).date().isoformat()
        covers = first <= d["overlap_from"]
        print(fmt_cov.format(
            sym,
            d["funding_count"],
            first,
            last,
            d["overlap_from"],
            "ĐỦ" if covers else f"THIẾU {first} trở về trước",
        ))
    print("-" * 125)

    print()
    print("=" * 125)
    print("BẢNG 4: CÙNG PHÉP ĐO, NHƯNG MẪU SỐ LẤY TRÊN CÙNG CỬA SỔ THỜI GIAN VỚI BINGX")
    print("Lý do: biên độ EURUSD/USDJPY giai đoạn 2025-2026 thấp hơn trung bình dài hạn,")
    print("nên mẫu số dài hạn làm tỷ lệ chi phí bị NHẸ đi. Hai bảng là cùng số liệu, khác mẫu số.")
    print("=" * 125)
    fmt4 = "{:<9}| {:<22}| {:<22}| {:<11}| {:<11}| {:<11}| {:<11}"
    print(fmt4.format(
        "Mã", "Mẫu số dài hạn", "Mẫu số cùng cửa sổ",
        "Phí vòng", "Giữ 1d", "Giữ 5d", "Giữ 10d",
    ))
    print("-" * 125)
    for sym, d in res.items():
        hro = d["holding_ratios_overlap"]
        print(fmt4.format(
            d["name"],
            f"{d['ext_primary_amp']:.4f}% (toàn bộ)",
            f"{d['ext_overlap_amp']:.4f}% (từ {d['overlap_from']})",
            f"{d['ratio_fee_to_amp_overlap']:.2f}%",
            f"{hro[1]:.2f}%",
            f"{hro[5]:.2f}%",
            f"{hro[10]:.2f}%",
        ))
    print("-" * 125)


def main() -> None:
    ap = argparse.ArgumentParser(description="Đo chi phí giữ vị thế forex perp BingX")
    ap.add_argument("--dsn", default=None, help="Postgres DSN")
    args = ap.parse_args()

    results = run_cost_analysis(args.dsn)
    print_cost_report(results)


if __name__ == "__main__":
    main()
