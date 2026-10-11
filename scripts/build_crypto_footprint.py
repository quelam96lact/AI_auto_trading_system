"""Tai va gop du lieu aggTrades cua Binance thanh nen footprint 5 phut v2 (Brief dot 183b).

- Nguon: https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/
- Pham vi: 2023-01 -> 2026-08 (44 thang).
- Buoc gia: step = max(0.1, round(open * 0.0001, 1)) (~1 bp theo open).
- Dau ra: data/crypto_footprint_v2/BTCUSDT/<YYYY-MM>.csv.gz
- Cot: ts, open, high, low, close, buy, sell, delta, n_trades, step, close_k, fp
- Khong tinh imbalance o day (tinh luc do theo nguong tuong doi).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import math
import os
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.binance_orderflow import (
    BASE_VISION_URL,
    MIN_RATE_LIMIT_SLEEP,
    calculate_file_sha256,
    download_file_to_path,
    fetch_checksum_text,
)
from scripts.seal import CRYPTO_SEALED_MAX_TS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "SEALED_CUTOFF_MONTH",
    "SEALED_MAX_MS",
    "aggregate_aggtrades_to_5m_bars",
    "check_month_sealed",
    "compute_footprint_step",
    "main",
    "process_month",
]

# --- Hang so dang ky truoc (§1.1, §1.2) -------------------------------------------

SEALED_CUTOFF_MONTH = "2026-08"

# Moc niem phong epoch ms UTC: 2026-08-31 23:59:59.999 UTC
_dt_sealed = datetime.fromisoformat(CRYPTO_SEALED_MAX_TS.replace(" ", "T"))
SEALED_MAX_MS: int = int(_dt_sealed.timestamp() * 1000) + 999

DEFAULT_OUTPUT_DIR = Path("data/crypto_footprint_v2/BTCUSDT")


# --- 1. Buoc footprint va kiem tra niem phong (§1.1, §1.2) ------------------------


def compute_footprint_step(open_price: float) -> float:
    """Tinh buoc gia footprint theo open cua chinh nen:
    step = max(0.1, round(open * 0.0001, 1)) (~1 bp).
    """
    return max(0.1, round(open_price * 0.0001, 1))


def check_month_sealed(month_str: str) -> None:
    """Kiem tra thang theo moc niem phong. Thang >= 2026-09 bi tu choi TRUOC KHI TAI."""
    if month_str > SEALED_CUTOFF_MONTH:
        raise ValueError(
            f"Thang {month_str} vuot moc niem phong (toi da {SEALED_CUTOFF_MONTH}). Tu choi tai."
        )


# --- 2. Gop aggTrades thanh nen footprint 5 phut v2 (§1.1, §1.2) ------------------


def aggregate_aggtrades_to_5m_bars(
    row_iterator: Iterable[list[str]],
    year: int,
    month: int,
) -> tuple[list[dict[str, Any]], int]:
    """Gop stream aggTrades thanh danh sach nen 5 phut tom tat v2 cho thang (year, month).

    Dau vao:
      row_iterator: iterable chua cac dong [agg_trade_id, price, qty, first_id, last_id, transact_time, is_buyer_maker].
    Tra ve:
      (danh sach dict nen 5 phut v2 kem cot fp, tong so trades da xu ly).
    """
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    cur_month_start = date(year, month, 1)
    days_in_month = (next_month_start - cur_month_start).days
    total_bars_expected = days_in_month * 288

    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(datetime(next_month_start.year, next_month_start.month, 1, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)

    # trade_data: (price, qty, is_buy)
    trades_by_bucket: dict[int, list[tuple[float, float, bool]]] = defaultdict(list)
    total_trades = 0

    for row in row_iterator:
        if not row or not row[0].strip().isdigit():
            continue

        try:
            price = float(row[1])
            qty = float(row[2])
            ts_ms = int(row[5])
            raw_is_buyer_maker = row[6].strip().lower() == "true"
        except (ValueError, IndexError):
            continue

        # Kiem tra niem phong theo tung dong (§1.1)
        if ts_ms > SEALED_MAX_MS:
            raise ValueError(
                f"Dong co transact_time {ts_ms} vuot qua moc niem phong {SEALED_MAX_MS}. Tu choi du lieu."
            )

        if ts_ms < start_ms or ts_ms >= end_ms:
            continue

        total_trades += 1
        # Quy uoc Binance: is_buyer_maker = false => Mua chu dong; true => Ban chu dong
        is_buy = not raw_is_buyer_maker

        bucket_idx = (ts_ms - start_ms) // 300000
        trades_by_bucket[bucket_idx].append((price, qty, is_buy))

    bars: list[dict[str, Any]] = []

    for b_idx in range(total_bars_expected):
        bar_start_dt = start_dt + timedelta(minutes=5 * b_idx)
        ts_str = bar_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        t_list = trades_by_bucket.get(b_idx)
        if not t_list:
            # Nen khong co giao dich: fp rong
            bars.append(
                {
                    "ts": ts_str,
                    "open": "",
                    "high": "",
                    "low": "",
                    "close": "",
                    "buy": 0.0,
                    "sell": 0.0,
                    "delta": 0.0,
                    "n_trades": 0,
                    "step": "",
                    "close_k": "",
                    "fp": "",
                }
            )
            continue

        prices = [t[0] for t in t_list]
        o = prices[0]
        h = max(prices)
        l = min(prices)
        c = prices[-1]

        buy_vol = sum(t[1] for t in t_list if t[2])
        sell_vol = sum(t[1] for t in t_list if not t[2])
        delta = buy_vol - sell_vol
        n_tr = len(t_list)

        step = compute_footprint_step(o)
        close_k = math.floor(c / step)

        # Footprint tinh theo gia tri USDT tai moi muc k
        fp_usdt: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for p, q, is_b in t_list:
            k = math.floor(p / step)
            val = p * q
            if is_b:
                fp_usdt[k][0] += val
            else:
                fp_usdt[k][1] += val

        # Tao chuoi fp: k:buy_usdt:sell_usdt noi bang |, gia tri lam tron so nguyen
        sorted_k = sorted(fp_usdt.keys())
        fp_parts: list[str] = []
        for k in sorted_k:
            b_val = round(fp_usdt[k][0])
            s_val = round(fp_usdt[k][1])
            if b_val > 0 or s_val > 0:
                fp_parts.append(f"{k}:{b_val}:{s_val}")
        fp_str = "|".join(fp_parts)

        bars.append(
            {
                "ts": ts_str,
                "open": f"{o:.2f}",
                "high": f"{h:.2f}",
                "low": f"{l:.2f}",
                "close": f"{c:.2f}",
                "buy": f"{buy_vol:.4f}",
                "sell": f"{sell_vol:.4f}",
                "delta": f"{delta:.4f}",
                "n_trades": n_tr,
                "step": f"{step:.1f}",
                "close_k": close_k,
                "fp": fp_str,
            }
        )

    return bars, total_trades


# --- 3. Xu ly mot thang hoan chinh: Tai -> Xac thuc -> Gop -> Ghi file ------------


def process_month(
    year: int,
    month: int,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Tai zip aggTrades tu Binance Vision, doi chieu checksum va gop thanh .csv.gz v2."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    month_str = f"{year:04d}-{month:02d}"

    # Kiem tra niem phong truoc khi lam bat cu dieu gi
    check_month_sealed(month_str)

    if month == 12:
        next_m = date(year + 1, 1, 1)
    else:
        next_m = date(year, month + 1, 1)
    days_in_m = (next_m - date(year, month, 1)).days
    expected_bars = days_in_m * 288

    target_file = out_dir / f"{month_str}.csv.gz"

    # Chay lai an toan: du so dong VA header co cot fp thi bo qua
    if target_file.exists():
        try:
            with gzip.open(target_file, "rt", encoding="utf-8") as gf:
                first_line = gf.readline()
                has_fp = "fp" in [c.strip() for c in first_line.split(",")]
                line_count = 1 + sum(1 for _ in gf)

            if has_fp and line_count == expected_bars + 1:
                active_count = 0
                fp_levels_list: list[int] = []
                with gzip.open(target_file, "rt", encoding="utf-8") as gf:
                    reader = csv.DictReader(gf)
                    for r in reader:
                        if r.get("n_trades") and int(r["n_trades"]) > 0:
                            active_count += 1
                            fp_s = r.get("fp", "")
                            n_levels = len(fp_s.split("|")) if fp_s else 0
                            fp_levels_list.append(n_levels)

                med_levels = 0.0
                if fp_levels_list:
                    fp_levels_list.sort()
                    mid = len(fp_levels_list) // 2
                    med_levels = float(fp_levels_list[mid])

                return {
                    "month": month_str,
                    "total_bars": expected_bars,
                    "active_bars": active_count,
                    "expected_bars": expected_bars,
                    "file_size": target_file.stat().st_size,
                    "median_fp_levels": med_levels,
                    "skipped": True,
                }
        except Exception:
            pass

    symbol = "BTCUSDT"
    zip_name = f"{symbol}-aggTrades-{month_str}.zip"
    zip_url = f"{BASE_VISION_URL}/data/futures/um/monthly/aggTrades/{symbol}/{zip_name}"
    checksum_url = f"{zip_url}.CHECKSUM"

    http = session or requests.Session()

    # 1. Tai checksum
    expected_sha256 = fetch_checksum_text(checksum_url, session=http)
    if not expected_sha256:
        raise RuntimeError(f"Khong the lay checksum cho {month_str}: {checksum_url}")

    # 2. Tai zip vao thu muc tam
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip_path = os.path.join(tmp_dir, zip_name)
        bytes_written, err = download_file_to_path(zip_url, tmp_zip_path, session=http)
        if err or bytes_written == 0:
            raise RuntimeError(f"Loi tai zip {month_str}: {err}")

        # 3. Kiem tra SHA-256
        actual_sha256 = calculate_file_sha256(tmp_zip_path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Sai SHA256 cho {month_str}: ky vong {expected_sha256}, thuc te {actual_sha256}"
            )

        # 4. Doc streaming zip va gop nen
        with zipfile.ZipFile(tmp_zip_path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                raise RuntimeError(f"Khong tim thay file CSV ben trong zip {zip_name}")
            csv_name = csv_names[0]

            with zf.open(csv_name, "r") as zf_raw:
                wrapper = io.TextIOWrapper(zf_raw, encoding="utf-8", errors="replace")
                reader = csv.reader(wrapper)
                bars, _ = aggregate_aggtrades_to_5m_bars(
                    reader,
                    year=year,
                    month=month,
                )

        # 5. Ghi ra file .csv.gz tam roi rename
        tmp_out = out_dir / f"{month_str}.csv.gz.tmp"
        fieldnames = [
            "ts",
            "open",
            "high",
            "low",
            "close",
            "buy",
            "sell",
            "delta",
            "n_trades",
            "step",
            "close_k",
            "fp",
        ]
        with gzip.open(tmp_out, "wt", encoding="utf-8", newline="") as gf:
            writer = csv.DictWriter(gf, fieldnames=fieldnames)
            writer.writeheader()
            for b in bars:
                writer.writerow(b)

        if target_file.exists():
            target_file.unlink()
        tmp_out.rename(target_file)

    active_count = sum(1 for b in bars if b["n_trades"] > 0)
    fp_levels_list = [len(b["fp"].split("|")) for b in bars if b["fp"]]
    med_levels = 0.0
    if fp_levels_list:
        fp_levels_list.sort()
        mid = len(fp_levels_list) // 2
        med_levels = float(fp_levels_list[mid])

    time.sleep(MIN_RATE_LIMIT_SLEEP)

    return {
        "month": month_str,
        "total_bars": len(bars),
        "active_bars": active_count,
        "expected_bars": expected_bars,
        "file_size": target_file.stat().st_size,
        "median_fp_levels": med_levels,
        "skipped": False,
    }


# --- 4. CLI Runner & Prevalence (§2.A, §2.C) --------------------------------------


def parse_month_str(m_str: str) -> tuple[int, int]:
    parts = m_str.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Dinh dang thang khong hop le (can YYYY-MM): {m_str}")
    return int(parts[0]), int(parts[1])


def month_range(start_ym: tuple[int, int], end_ym: tuple[int, int]) -> list[tuple[int, int]]:
    cur_y, cur_m = start_ym
    end_y, end_m = end_ym
    res: list[tuple[int, int]] = []
    while (cur_y < end_y) or (cur_y == end_y and cur_m <= end_m):
        res.append((cur_y, cur_m))
        cur_m += 1
        if cur_m > 12:
            cur_m = 1
            cur_y += 1
    return res


def run_prevalence_report(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> int:
    """Dem ti le pho bien 4 nhom imbalance tren thu muc v2 va phan quyet E3.

    Chi goi load_crypto_footprint_bars, apply_relative_imbalance va imbalance_prevalence.
    Tuyet doi KHONG goi detect_e1/e2/e3 hay calculate_event_targets.
    """
    from scripts.screen_crypto_orderflow import (
        E3_DEGENERATE_BOTH_SHARE,
        MAIN_END_DATE,
        MAIN_START_DATE,
        apply_relative_imbalance,
        imbalance_prevalence,
        load_crypto_footprint_bars,
    )

    out_p = Path(output_dir)
    print("=" * 88)
    print("  BRIEF ĐỢT 183b — BÁO CÁO PHỔ BIẾN IMBALANCE TRÊN DỮ LIỆU FOOTPRINT V2")
    print(f"  Thư mục dữ liệu: {out_p}")
    print("=" * 88)

    bars_raw = load_crypto_footprint_bars(data_dir=out_p)
    if not bars_raw:
        print(f"[CẢNH BÁO] Không tìm thấy dữ liệu footprint v2 trong '{out_p}'.", file=sys.stderr)
        return 1

    bars = apply_relative_imbalance(bars_raw)

    # Gom theo từng tháng
    bars_by_month: dict[str, list[Any]] = defaultdict(list)
    for b in bars:
        m_key = b.session_id.strftime("%Y-%m")
        bars_by_month[m_key].append(b)

    print(f"{'Tháng':<10} | {'Tổng nến':<10} | {'Chỉ Ask':<10} | {'Chỉ Bid':<10} | {'Cả hai':<10} | {'Không có':<10} | {'% Cả hai'}")
    print("-" * 88)

    for m_key in sorted(bars_by_month.keys()):
        m_bars = bars_by_month[m_key]
        p_res = imbalance_prevalence(m_bars)
        tot = p_res["total"]
        both_pct = (p_res["both"] / tot * 100.0) if tot > 0 else 0.0
        print(
            f"{m_key:<10} | {tot:<10} | {p_res['ask_only']:<10} | {p_res['bid_only']:<10} | "
            f"{p_res['both']:<10} | {p_res['neither']:<10} | {both_pct:>6.2f}%"
        )

    # Tổng cửa sổ CHÍNH (2023-01-01 -> 2024-12-31)
    main_res = imbalance_prevalence(bars, start_date=MAIN_START_DATE, end_date=MAIN_END_DATE)
    main_tot = main_res["total"]
    main_both_pct = (main_res["both"] / main_tot * 100.0) if main_tot > 0 else 0.0
    main_both_share = (main_res["both"] / main_tot) if main_tot > 0 else 0.0

    print("=" * 88)
    print(
        f"{'TỔNG CHÍNH':<10} | {main_tot:<10} | {main_res['ask_only']:<10} | {main_res['bid_only']:<10} | "
        f"{main_res['both']:<10} | {main_res['neither']:<10} | {main_both_pct:>6.2f}%"
    )
    print("=" * 88)

    if main_both_share > E3_DEGENERATE_BOTH_SHARE:
        verdict = f"PHÁN QUYẾT: E3 BỊ LOẠI (suy biến: cả hai {main_both_pct:.2f}% > 50%)"
    else:
        verdict = f"PHÁN QUYẾT: E3 ĐƯỢC GIỮ (cả hai {main_both_pct:.2f}% <= 50%)"
    print(f"\n  {verdict}\n")
    return 0


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dung du lieu nen footprint 5 phut v2 tu Binance aggTrades (Brief dot 183b)"
    )
    parser.add_argument(
        "--from",
        dest="from_month",
        default="2023-01",
        help="Thang bat dau (mac dinh: 2023-01)",
    )
    parser.add_argument(
        "--to",
        dest="to_month",
        default="2026-08",
        help="Thang ket thuc (mac dinh: 2026-08, toi da 2026-08)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Thu muc dau ra (mac dinh: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--prevalence",
        action="store_true",
        help="Dem ti le pho bien 4 nhom imbalance tren thu muc v2 va phan quyet E3",
    )
    effective_args = sys.argv[1:] if args is None else list(args)
    parsed = parser.parse_args(effective_args)

    if parsed.prevalence:
        return run_prevalence_report(output_dir=parsed.output_dir)

    try:
        start_ym = parse_month_str(parsed.from_month)
        end_ym = parse_month_str(parsed.to_month)
    except ValueError as e:
        print(f"[LOI] {e}", file=sys.stderr)
        return 1

    months = month_range(start_ym, end_ym)
    if not months:
        print("[LOI] Khoang thang rong.", file=sys.stderr)
        return 1

    # Kiem tra tat ca cac thang truoc khi chay
    for y, m in months:
        m_str = f"{y:04d}-{m:02d}"
        try:
            check_month_sealed(m_str)
        except ValueError as exc:
            print(f"[LOI NIEM PHONG] {exc}", file=sys.stderr)
            return 2

    print("=" * 88)
    print("  BRIEF ĐỢT 183b — DỰNG DỮ LIỆU FOOTPRINT V2 BTCUSDT PERP (BINANCE VISION)")
    print(f"  Phạm vi      : {parsed.from_month} -> {parsed.to_month} ({len(months)} tháng)")
    print(f"  Thư mục lưu  : {parsed.output_dir}")
    print(f"  Niêm phong   : Tháng <= {SEALED_CUTOFF_MONTH}")
    print("=" * 88)

    session = requests.Session()
    stats_list: list[dict[str, Any]] = []

    for idx, (y, m) in enumerate(months, 1):
        m_str = f"{y:04d}-{m:02d}"
        print(f"[{idx}/{len(months)}] Đang xử lý {m_str}...", end="", flush=True)
        try:
            st = process_month(
                year=y,
                month=m,
                output_dir=parsed.output_dir,
                session=session,
            )
            stats_list.append(st)
            status = "ĐÃ CÓ (bỏ qua)" if st["skipped"] else "XONG"
            print(
                f" {status} | Nến: {st['active_bars']}/{st['total_bars']} (kỳ vọng {st['expected_bars']}) | "
                f"Mức trung vị: {st['median_fp_levels']:.0f} | Size: {st['file_size'] / 1024 / 1024:.2f} MB"
            )
        except Exception as e:
            print(f" THẤT BẠI: {e}", file=sys.stderr)
            return 3

    print("\n" + "=" * 88)
    print("  TỔNG KẾT DỰNG DỮ LIỆU FOOTPRINT V2")
    print(f"  Tổng số tháng đã xử lý: {len(stats_list)}")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
