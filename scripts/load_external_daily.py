"""Tải dữ liệu dài hạn của tài sản gốc từ các nguồn mở hợp pháp (Brief đợt 115).

Chỉ nạp từ các nguồn đã duyệt:
1. Federal Reserve Board H.10 Statistical Release (Public Domain):
   - EUR/USD (Series: RXI$US_N.B.EU)
   - USD/JPY (Series: RXI_N.B.JA)
2. European Central Bank (ECB) Data Portal (Free Access & Free Reuse with attribution):
   - EUR/USD (Key: EXR.D.USD.EUR.SP00.A)

Niêm phong: Không nạp dữ liệu từ 2026-09-01 (max_date = 2026-08-31).
Ghi vào bảng mới: bars_ext_daily.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from datetime import date, datetime, timedelta
from typing import Any

import psycopg
import requests

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEALED_MAX_DATE = date(2026, 8, 31)

URL_FRB_H10_ZIP = "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&filetype=zip"
URL_ECB_EURUSD_CSV = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata&startPeriod=1999-01-01"
)


# ---------------------------------------------------------------------------
# 1. Các hàm thuần (Pure Functions) có Unit Test
# ---------------------------------------------------------------------------

def parse_frb_h10_xml(
    xml_content: str,
    series_name: str,
    symbol: str,
    max_date: date | None = None,
) -> list[dict[str, Any]]:
    """Phân tích nội dung XML SDMX của Federal Reserve H.10.

    Lọc bỏ giá trị không phải số (ND) và các ngày lớn hơn max_date.
    """
    pattern = rf'<kf:Series [^>]*SERIES_NAME="{re.escape(series_name)}"[^>]*>(.*?)</kf:Series>'
    m = re.search(pattern, xml_content, re.DOTALL)
    if not m:
        return []

    series_body = m.group(1)
    obs = re.findall(r'<frb:Obs [^>]*OBS_VALUE="([^"]*)" [^>]*TIME_PERIOD="([^"]*)"', series_body)

    records: list[dict[str, Any]] = []
    for val_str, date_str in obs:
        if val_str == "ND":
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if max_date and d > max_date:
                continue
            price = float(val_str)
            if price <= 0:
                continue
            records.append({
                "source": "FRB_H10",
                "symbol": symbol,
                "date": d,
                "close": price,
                "open": None,
                "high": None,
                "low": None,
            })
        except (ValueError, TypeError):
            continue

    records.sort(key=lambda x: x["date"])
    return records


def parse_ecb_csv(
    csv_content: str,
    symbol: str = "EURUSD",
    max_date: date | None = None,
) -> list[dict[str, Any]]:
    """Phân tích nội dung CSV SDMX của Ngân hàng Trung ương Châu Âu (ECB)."""
    records: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        date_str = row.get("TIME_PERIOD", "").strip()
        val_str = row.get("OBS_VALUE", "").strip()
        if not date_str or not val_str:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if max_date and d > max_date:
                continue
            price = float(val_str)
            if price <= 0:
                continue
            records.append({
                "source": "ECB",
                "symbol": symbol,
                "date": d,
                "close": price,
                "open": None,
                "high": None,
                "low": None,
            })
        except (ValueError, TypeError):
            continue

    records.sort(key=lambda x: x["date"])
    return records


def count_business_days_between(d1: date, d2: date) -> int:
    """Đếm số ngày làm việc (Thứ 2 đến Thứ 6) giữa d1 và d2 (tính từ d1+1 đến d2)."""
    if d1 >= d2:
        return 0
    cur = d1 + timedelta(days=1)
    b_days = 0
    while cur <= d2:
        if cur.weekday() < 5:  # Mon to Fri
            b_days += 1
        cur += timedelta(days=1)
    return b_days


def calculate_data_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính các thông số kiểm kê chất lượng chuỗi dữ liệu ngoại sinh.

    Trả về:
    - total_rows: Tổng số dòng
    - first_date: Ngày đầu tiên
    - last_date: Ngày cuối cùng
    - nonpositive_count: Số ngày giá <= 0
    - duplicate_dates_count: Số ngày bị trùng lặp
    - max_business_day_gap: Khoảng trống dài nhất tính theo ngày làm việc
    """
    if not records:
        return {
            "total_rows": 0,
            "first_date": None,
            "last_date": None,
            "nonpositive_count": 0,
            "duplicate_dates_count": 0,
            "max_business_day_gap": 0,
        }

    total_rows = len(records)
    first_date = records[0]["date"]
    last_date = records[-1]["date"]
    nonpositive_count = sum(1 for r in records if r["close"] <= 0)

    dates = [r["date"] for r in records]
    duplicate_dates_count = len(dates) - len(set(dates))

    unique_dates = sorted(set(dates))
    max_b_gap = 0
    for i in range(len(unique_dates) - 1):
        b_gap = count_business_days_between(unique_dates[i], unique_dates[i + 1])
        max_b_gap = max(max_b_gap, b_gap)

    return {
        "total_rows": total_rows,
        "first_date": first_date,
        "last_date": last_date,
        "nonpositive_count": nonpositive_count,
        "duplicate_dates_count": duplicate_dates_count,
        "max_business_day_gap": max_b_gap,
    }


# ---------------------------------------------------------------------------
# 2. Database và Nạp dữ liệu
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bars_ext_daily (
    source VARCHAR(64) NOT NULL,
    symbol VARCHAR(64) NOT NULL,
    date DATE NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    PRIMARY KEY (source, symbol, date)
);
"""


def ensure_table_exists(conn: psycopg.Connection) -> None:
    """Tạo bảng bars_ext_daily nếu chưa tồn tại. Tuyệt đối không đụng bảng khác."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def insert_records(conn: psycopg.Connection, records: list[dict[str, Any]]) -> int:
    """Nạp danh sách bản ghi vào bars_ext_daily với ON CONFLICT DO UPDATE."""
    if not records:
        return 0

    sql = """
    INSERT INTO bars_ext_daily (source, symbol, date, close, open, high, low)
    VALUES (%(source)s, %(symbol)s, %(date)s, %(close)s, %(open)s, %(high)s, %(low)s)
    ON CONFLICT (source, symbol, date) DO UPDATE SET
        close = EXCLUDED.close,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low;
    """
    with conn.cursor() as cur:
        cur.executemany(sql, records)
    conn.commit()
    return len(records)


def fetch_frb_h10_zip() -> bytes:
    """Tải gói ZIP H.10 từ Federal Reserve Board."""
    resp = requests.get(
        URL_FRB_H10_ZIP,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=30,
    )
    resp.raise_for_string = True
    if resp.status_code != 200:
        raise RuntimeError(f"Lỗi tải Federal Reserve H.10 ZIP: HTTP {resp.status_code}")
    return resp.content


def fetch_ecb_eurusd_csv() -> str:
    """Tải chuỗi CSV EUR/USD từ API ECB Data Portal."""
    resp = requests.get(
        URL_ECB_EURUSD_CSV,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Lỗi tải ECB Data Portal CSV: HTTP {resp.status_code}")
    return resp.text


def run_loader(dsn: str | None = None) -> list[dict[str, Any]]:
    """Thực thi toàn bộ luồng nạp dữ liệu ngoại sinh và trả về bảng tổng kết."""
    resolved_dsn = resolve_dsn(dsn)
    print("=" * 80)
    print("BẮT ĐẦU NẠP DỮ LIỆU NGOẠI SINH DÀI HẠN (BRIEF 115)")
    print(f"Mốc niêm phong (Sealed max date): {SEALED_MAX_DATE}")
    print("=" * 80)

    results_summary: list[dict[str, Any]] = []

    # 1. Tải và xử lý Federal Reserve H.10
    print("\n[1/2] Đang tải Federal Reserve Board H.10 Statistical Release...")
    frb_zip_bytes = fetch_frb_h10_zip()
    with (
        zipfile.ZipFile(io.BytesIO(frb_zip_bytes)) as z,
        z.open("H10_data.xml") as f,
    ):
        frb_xml_str = f.read().decode("utf-8", errors="replace")

    # 1a. EUR/USD (Series: RXI$US_N.B.EU)
    eurusd_frb = parse_frb_h10_xml(
        xml_content=frb_xml_str,
        series_name="RXI$US_N.B.EU",
        symbol="EURUSD",
        max_date=SEALED_MAX_DATE,
    )
    summary_eur_frb = calculate_data_summary(eurusd_frb)
    summary_eur_frb.update({"source": "FRB_H10", "symbol": "EURUSD", "records": eurusd_frb})
    results_summary.append(summary_eur_frb)
    print(f"  -> FRB EUR/USD: {len(eurusd_frb)} nến (từ {summary_eur_frb['first_date']} đến {summary_eur_frb['last_date']})")

    # 1b. USD/JPY (Series: RXI_N.B.JA)
    usdjpy_frb = parse_frb_h10_xml(
        xml_content=frb_xml_str,
        series_name="RXI_N.B.JA",
        symbol="USDJPY",
        max_date=SEALED_MAX_DATE,
    )
    summary_jpy_frb = calculate_data_summary(usdjpy_frb)
    summary_jpy_frb.update({"source": "FRB_H10", "symbol": "USDJPY", "records": usdjpy_frb})
    results_summary.append(summary_jpy_frb)
    print(f"  -> FRB USD/JPY: {len(usdjpy_frb)} nến (từ {summary_jpy_frb['first_date']} đến {summary_jpy_frb['last_date']})")

    # 2. Tải và xử lý ECB Data Portal (EUR/USD)
    print("\n[2/2] Đang tải European Central Bank (ECB) Data Portal...")
    ecb_csv_str = fetch_ecb_eurusd_csv()
    eurusd_ecb = parse_ecb_csv(
        csv_content=ecb_csv_str,
        symbol="EURUSD",
        max_date=SEALED_MAX_DATE,
    )
    summary_eur_ecb = calculate_data_summary(eurusd_ecb)
    summary_eur_ecb.update({"source": "ECB", "symbol": "EURUSD", "records": eurusd_ecb})
    results_summary.append(summary_eur_ecb)
    print(f"  -> ECB EUR/USD: {len(eurusd_ecb)} nến (từ {summary_eur_ecb['first_date']} đến {summary_eur_ecb['last_date']})")

    # 3. Ghi vào Database
    print("\n[3/3] Đang ghi vào bảng PostgreSQL bars_ext_daily...")
    with psycopg.connect(resolved_dsn) as conn:
        ensure_table_exists(conn)
        for item in results_summary:
            inserted = insert_records(conn, item["records"])
            print(f"  -> Đã nạp {inserted} dòng cho ({item['source']}, {item['symbol']})")

    print("\n" + "=" * 105)
    print("BẢNG KIỂM CHỨNG CHẤT LƯỢNG NẠP DỮ LIỆU NGOẠI SINH DÀI HẠN (§4.2)")
    print("=" * 105)
    headers = ["Nguồn", "Mã", "Số dòng", "Ngày đầu", "Ngày cuối", "Giá <= 0", "Ngày trùng", "Khoảng trống max (ngày LV)"]
    fmt = "{:<10} | {:<8} | {:>8} | {:<10} | {:<10} | {:>9} | {:>10} | {:>26}"
    print(fmt.format(*headers))
    print("-" * 105)
    for s in results_summary:
        print(fmt.format(
            s["source"],
            s["symbol"],
            s["total_rows"],
            str(s["first_date"]),
            str(s["last_date"]),
            s["nonpositive_count"],
            s["duplicate_dates_count"],
            s["max_business_day_gap"],
        ))
    print("=" * 105)

    return results_summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Tải dữ liệu ngoại sinh dài hạn (Brief 115)")
    ap.add_argument("--dsn", default=None, help="Postgres DSN")
    args = ap.parse_args()

    run_loader(args.dsn)


if __name__ == "__main__":
    main()
