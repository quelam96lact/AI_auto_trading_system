"""Bước 1 (prompt 2026-08-15-hermes-refprice-check.md): đối chiếu 10 mã đã biết
— giá tham chiếu có bị reset giữa hai phiên tạo bước nhảy không?

refPrice(t) = close(t) / (1 + priceChangePercentage(t)/100)   [suy từ pct]
(Bước 0 phát hiện: priceChange tuyệt đối = null cho dữ liệu 2016, chỉ pct có giá trị;
kiểm chứng công thức trên HNB 2016-03-30: refPrice=15470.8 ≈ close(03/25)=15468.7,
sai 0.014% — công thức vận hành.)

BẪY ĐƠN VỊ: bars_daily là giá ĐÃ back-adjust, API cũng trả giá adjust (HNB 03/31
close=18057.847 khớp DB 18058) — nhưng KHÔNG so số tuyệt đối giữa DB và API. Lấy
close(t-1) từ CHÍNH API (cùng nguồn với refPrice(t)) — chọn cách này.

Kết luận từng mã:
- refPrice(t) ≈ close(t-1) (cùng nguồn, sai số <= 3%) -> THAM CHIẾU KHÔNG RESET
  -> một phiên nhảy quá biên độ mà không có sự kiện -> dữ liệu nguồn sai thật.
- refPrice(t) ≠ close(t-1) -> THAM CHIẾU RESET -> sự kiện đổi giá tham chiếu,
  hệ số điều chỉnh = refPrice(t)/close(t-1).

CHỈ ĐỌC. Token từ ssi_auth_state, không OTP mới. Không commit/push.
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://api.ssi.com.vn/api/v3/data/securitiesSummary"
RESET_TOL = 0.03  # refPrice/close_prev trong [1-3%, 1+3%] = KHÔNG RESET

# (mã, ngày nhảy) — đúng 10 mẫu trong docs/superpowers/research/2026-08-15-overnight-gap-causes.md
CASES = [
    ("HNB", "2016-03-31"),
    ("VNI", "2016-05-30"),
    ("VRG", "2016-11-25"),
    ("HU4", "2017-02-17"),
    ("S12", "2017-04-28"),
    ("KSV", "2017-08-23"),
    ("TUG", "2018-04-26"),
    ("IPA", "2018-06-13"),
    ("PTH", "2018-10-08"),
    ("VTA", "2018-12-28"),
]


def _load_dotenv() -> None:
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def resolve_dsn() -> str:
    _load_dotenv()
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise SystemExit("DB_DSN chưa set — cần .env")
    return dsn.replace("localhost", "127.0.0.1")


def _fmt(d: str) -> str:
    """YYYY-MM-DD -> YYYY/MM/DD (định dạng API)."""
    return d.replace("-", "/")


async def _fetch(client: httpx.AsyncClient, headers: dict, symbol: str,
                 frm: str, to: str) -> list[dict]:
    resp = await client.get(API_URL, params={
        "symbol": symbol, "from": _fmt(frm), "to": _fmt(to),
        "pageIndex": 1, "pageSize": 100,
    }, headers=headers)
    resp.raise_for_status()
    raw = resp.json()
    return raw.get("data") or raw.get("Data") or []


async def _run() -> None:
    _load_dotenv()
    from trading.config import load_config
    from trading.storage.db import Storage

    cfg = load_config("config/config.yaml")
    storage = Storage(resolve_dsn())

    from trading.collector.ssi_auth import ensure_authenticated

    auth = await ensure_authenticated(cfg, storage)
    try:
        token = auth.token_manager.token
        access = getattr(token, "access_token", None) if token else None
        if not access:
            print("KHÔNG lấy được access_token — dừng, không tự xoay token")
            return
        headers = {"Authorization": f"Bearer {access}"}

        print("BẢNG 10 MÃ — refPrice suy từ priceChangePercentage, close(t-1) từ CHÍNH API:")
        print(f"{'mã':<5} {'ngày nhảy':<12} {'close(t-1)':>11} {'close(t)':>11} "
              f"{'refPrice(t)':>11} {'pct':>7} {'refPrice/c(t-1)':>14}  kết luận")
        print("-" * 100)

        async with httpx.AsyncClient(timeout=30) as client:
            for symbol, day in CASES:
                d = date.fromisoformat(day)
                frm = (d - timedelta(days=15)).isoformat()
                to = (d + timedelta(days=5)).isoformat()
                try:
                    rows = await _fetch(client, headers, symbol, frm, to)
                except Exception as e:
                    print(f"{symbol:<5} LỖI gọi SSI: {type(e).__name__}: {str(e)[:120]}")
                    continue
                # map tradingDate -> row, sort theo ngày
                by_date = {}
                for r in rows:
                    td = r.get("tradingDate", "")
                    if td:
                        by_date[td.replace("/", "-")] = r
                if not by_date:
                    print(f"{symbol:<5} {day:<12} KHÔNG có dữ liệu API trong tháng — bỏ qua")
                    continue
                if day not in by_date:
                    print(f"{symbol:<5} {day:<12} ngày nhảy KHÔNG có trong API — bỏ qua")
                    continue
                dates = sorted(by_date)
                idx = dates.index(day)
                if idx == 0:
                    print(f"{symbol:<5} {day:<12} ngày nhảy là dòng đầu tháng — bỏ qua")
                    continue
                prev_day = dates[idx - 1]
                r_t = by_date[day]
                r_prev = by_date[prev_day]
                close_t = float(r_t.get("close"))
                close_prev = float(r_prev.get("close"))
                pct = r_t.get("priceChangePercentage")
                if pct is None:
                    print(f"{symbol:<5} {day:<12} priceChangePercentage = null — bỏ qua")
                    continue
                pct = float(pct)
                ref_price = close_t / (1 + pct / 100)
                ratio = ref_price / close_prev if close_prev else 0.0
                if abs(ratio - 1) <= RESET_TOL:
                    verdict = "KHÔNG RESET"
                else:
                    verdict = f"RESET (hệ số {ratio:.4f})"
                print(f"{symbol:<5} {day:<12} {close_prev:>11,.2f} {close_t:>11,.2f} "
                      f"{ref_price:>11,.2f} {pct:>6.2f}% {ratio:>14.4f}  {verdict}")
    finally:
        await auth.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=None,
                    help="SYM:YYYY-MM-DD,... — mặc định 10 mẫu trong research doc")
    args = ap.parse_args()
    global CASES
    if args.cases:
        CASES = []
        for part in args.cases.split(","):
            sym, _, day = part.strip().partition(":")
            CASES.append((sym.strip(), day.strip()))
    asyncio.run(_run())


if __name__ == "__main__":
    main()
