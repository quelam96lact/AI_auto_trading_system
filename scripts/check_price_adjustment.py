"""Bước 0 (spec 2026-08-15-daily-breakout): kiểm tra bars_daily đã điều chỉnh
chia tách/cổ tức chưa.

Câu hỏi mở chặn việc tin vào kết quả backtest: nếu giá chưa điều chỉnh, ngày
chia tách sẽ tạo bước nhảy giả làm breakout sinh tín hiệu sai.

Phương pháp — quét TỪNG mã (không nạp hết 2.97M dòng vào RAM):
  1. Bỏ bar rác OHLC<=0 trước khi tính (giống run_backtest).
  2. Bước nhảy qua đêm: r = close[t]/close[t-1] nằm NGOÀI [0.75, 1.25]
     (|r-1| > 25%) mà volume KHÔNG bất thường tương ứng (< 5x trung vị) —
     cổ phiếu VN giới hạn biên độ ±7%/±10%/±15% theo sàn, nên bước nhảy qua
     đêm > 25% về bản chất không phải biến động thị trường thật: hoặc là
     hiệu chỉnh (chia tách/cổ tức bằng cổ phiếu) hoặc là dữ liệu hỏng.
  3. Tỉ lệ đặc trưng chia tách: r ~ 1/2, 1/3, 2/3, 1/1.1 (dung sai 3%) —
     kiểm tra RIÊNG, kể cả khi nằm trong biên 25% (vì 1/1.1 = 0.909 nằm
     trong biên).
  4. Ngày lịch cách nhau > 60 ngày = tạm ngừng giao dịch dài (delist/
     suspend) — ghi chú riêng, KHÔNG tính là dấu hiệu chia tách.

Kết luận: "đã điều chỉnh" / "chưa điều chỉnh" / "không đủ bằng chứng".

CLI:
  uv run python scripts/check_price_adjustment.py [--dsn ...] [--top 20]
"""

import argparse
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

import psycopg

from trading.calendar_vn import TZ

# Tỉ lệ đặc trưng của chia tách/trả cổ tức bằng cổ phiếu (giá giảm xuống còn
# bao nhiêu so với hôm trước nếu chưa điều chỉnh). Chia 2 nhóm:
# - MẠNH (1:2, 1:3, 2:3): giảm 33-50% qua đêm — KHÔNG THỂ là biến động thị
#   trường (biên độ tối đa 15%/phiên) -> bằng chứng CHẮC chắn chưa điều chỉnh.
# - YẾU (1:1.1 = 0.909): dải ±3% trùng phiên giảm mạnh bình thường (7-10%) —
#   chỉ đếm, không dùng cho kết luận.
STRONG_SPLIT = {0.5: "1:2", 1 / 3: "1:3", 2 / 3: "2:3"}
WEAK_SPLIT = {1 / 1.1: "1:1.1"}
SPLIT_TOL = 0.03
GAP_LO, GAP_HI = 0.75, 1.25
VOL_ANOMALY_X = 5.0  # volume >= 5x trung vị = "bất thường tương ứng"
MAX_CAL_DAYS = 60  # hơn = tạm ngừng giao dịch dài, không phải chia tách


def _load_dotenv() -> None:
    """uv run KHÔNG nạp .env — script tự đọc, không nhúng secret vào file."""
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def resolve_dsn(override: str | None) -> str:
    if override:
        return override
    _load_dotenv()
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise SystemExit("DB_DSN chưa set — cần .env hoặc --dsn")
    # Windows máy này: DSN dùng localhost bị IPv6 làm mỗi kết nối chậm ~130s.
    return dsn.replace("localhost", "127.0.0.1")


def _is_dirty(o: float, h: float, l: float, c: float) -> bool:
    return o <= 0 or h <= 0 or l <= 0 or c <= 0


def _split_note(r: float) -> tuple[str | None, bool]:
    """Trả về (tên tỉ lệ, có phải chia tách MẠNH không). None nếu không khớp."""
    for ratio, name in STRONG_SPLIT.items():
        if abs(r - ratio) / ratio <= SPLIT_TOL:
            return name, True
    for ratio, name in WEAK_SPLIT.items():
        if abs(r - ratio) / ratio <= SPLIT_TOL:
            return name, False
    return None, False


def scan_symbol(rows) -> dict:
    """Quét 1 mã. Trả về thống kê + danh sách bước nhảy nghi ngờ.

    rows: [(ts, open, high, low, close, volume), ...] theo thứ tự thời gian.
    """
    clean = [(ts, c, v) for ts, o, h, l, c, v in rows if not _is_dirty(o, h, l, c)]
    n_dirty = len(rows) - len(clean)
    vols = [v for _, _, v in clean]
    median_vol = statistics.median(vols) if vols else 0.0

    gaps: list[dict] = []  # |r-1| > 25%, volume không bất thường, không suspend dài
    long_suspend: list[dict] = []  # bước nhảy qua khoảng ngừng giao dịch dài
    split_hits: list[dict] = []  # khớp tỉ lệ chia tách (bất kể cỡ bước nhảy)

    prev_ts = prev_c = None
    for ts, c, v in clean:
        if prev_ts is not None and prev_c is not None and prev_c > 0:
            r = c / prev_c
            cal_days = (ts.astimezone(TZ).date() - prev_ts.astimezone(TZ).date()).days
            vol_ratio = v / median_vol if median_vol > 0 else None
            outside = r < GAP_LO or r > GAP_HI
            note, strong = _split_note(r)
            rec = {
                "ts": ts,
                "prev_close": prev_c,
                "close": c,
                "ratio": r,
                "cal_days": cal_days,
                "vol_ratio": vol_ratio,
                "split": note,
                "strong": strong,
            }
            if cal_days > MAX_CAL_DAYS:
                long_suspend.append(rec)
            else:
                if outside and (vol_ratio is None or vol_ratio < VOL_ANOMALY_X):
                    gaps.append(rec)
                if note:
                    split_hits.append(rec)
        prev_ts, prev_c = ts, c

    return {
        "n_clean": len(clean),
        "n_dirty": n_dirty,
        "median_vol": median_vol,
        "gaps": gaps,
        "long_suspend": long_suspend,
        "split_hits": split_hits,
    }


def _fmt_ts(ts: datetime) -> str:
    return ts.astimezone(TZ).strftime("%Y-%m-%d")


def print_top_examples(title: str, entries: list[dict], top: int) -> None:
    print(f"\nTop {min(top, len(entries))} ví dụ — {title}:")
    print(f"  {'mã':<8} {'ngày (HCM)':<12} {'close trước':>12} {'close':>12} "
          f"{'tỉ lệ':>8}  {'ngày lịch':>9} {'vol/xTV':>8} {'chia tách':>9}")
    for e in entries[:top]:
        split = e["split"] or "-"
        volr = f"{e['vol_ratio']:.1f}x" if e["vol_ratio"] is not None else "n/a"
        print(f"  {e['symbol']:<8} {_fmt_ts(e['ts']):<12} {e['prev_close']:>12,.0f} "
              f"{e['close']:>12,.0f} {e['ratio']:>8.4f} {e['cal_days']:>9} "
              f"{volr:>8} {split:>9}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    dsn = resolve_dsn(args.dsn)

    with psycopg.connect(dsn) as c:
        symbols = [r[0] for r in c.execute(
            "SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol"
        )]

        all_gaps: list[dict] = []
        all_split: list[dict] = []
        all_suspend: list[dict] = []
        dirty_by_symbol: dict[str, int] = {}
        total_clean = 0

        for i, sym in enumerate(symbols, 1):
            rows = c.execute(
                "SELECT ts, open, high, low, close, volume FROM bars_daily "
                "WHERE symbol = %s ORDER BY ts",
                (sym,),
            ).fetchall()
            res = scan_symbol(rows)
            total_clean += res["n_clean"]
            if res["n_dirty"]:
                dirty_by_symbol[sym] = res["n_dirty"]
            for e in res["gaps"]:
                e["symbol"] = sym
                all_gaps.append(e)
            for e in res["split_hits"]:
                e["symbol"] = sym
                all_split.append(e)
            for e in res["long_suspend"]:
                e["symbol"] = sym
                all_suspend.append(e)
            if i % 300 == 0:
                print(f"  ...đã quét {i}/{len(symbols)} mã", file=sys.stderr)

    n_dirty_total = sum(dirty_by_symbol.values())
    gap_symbols = {e["symbol"] for e in all_gaps}
    strong_split = [e for e in all_split if e["strong"]]
    strong_split_symbols = {e["symbol"] for e in strong_split}

    print("=" * 78)
    print("BƯỚC 0 — KIỂM TRA GIÁ ĐÃ ĐIỀU CHỈNH CHIA TÁCH/CỔ TỨC CHƯA")
    print("=" * 78)
    print(f"Mã quét: {len(symbols)}  Bar sạch: {total_clean:,}  "
          f"Bar rác OHLC<=0: {n_dirty_total:,} ({n_dirty_total / (total_clean + n_dirty_total):.2%})")
    print(f"Mã có bar rác: {len(dirty_by_symbol)} — top 10:")
    for sym, n in sorted(dirty_by_symbol.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {sym}: {n}")
    print()
    print(f"Bước nhảy qua đêm |close(t)/close(t-1)-1| > 25% (volume KHÔNG bất thường): "
          f"{len(all_gaps)} sự kiện trên {len(gap_symbols)} mã")
    print(f"Khớp tỉ lệ chia tách MẠNH (1:2/1:3/2:3 — giảm 33-50% qua đêm, không thể "
          f"là biến động thường): {len(strong_split)} sự kiện trên "
          f"{len(strong_split_symbols)} mã")
    if strong_split:
        by_ratio: dict[str, int] = {}
        for e in strong_split:
            by_ratio[e["split"]] = by_ratio.get(e["split"], 0) + 1
        print(f"  Phân bố theo tỉ lệ: {by_ratio}")
    print(f"Khớp tỉ lệ YẾU (1:1.1 — dải trùng phiên giảm mạnh thường, chỉ đếm): "
          f"{len(all_split) - len(strong_split)} sự kiện")
    print(f"Bước nhảy qua khoảng ngừng giao dịch dài (> {MAX_CAL_DAYS} ngày lịch, "
          f"delist/suspend — KHÔNG tính là chia tách): {len(all_suspend)} sự kiện "
          f"trên {len({e['symbol'] for e in all_suspend})} mã")

    if strong_split:
        print_top_examples("chia tách MẠNH còn nguyên trong giá (bằng chứng CHƯA điều chỉnh)",
                           sorted(strong_split, key=lambda e: e["ts"]), args.top)
    if all_gaps:
        print_top_examples("bước nhảy >25% không khớp tỉ lệ chia tách (nghi dữ liệu hỏng)",
                           sorted(all_gaps, key=lambda e: e["ts"]), args.top)

    print()
    print("KẾT LUẬN:", end=" ")
    if len(strong_split_symbols) >= 3:
        print("CHƯA điều chỉnh — có chia tách tỉ lệ mạnh (1:2/1:3/2:3) còn nguyên "
              "trong giá (breakout sẽ sinh tín hiệu giả đúng ngày chia tách, kết quả "
              "đo phải đọc kèm cảnh báo này).")
    elif not all_gaps and not all_split:
        print("không đủ bằng chứng — không thấy bước nhảy bất thường nào, nhưng thiếu "
              "dữ liệu sự kiện doanh nghiệp để chứng minh đã điều chỉnh.")
    else:
        print("không đủ bằng chứng — có bước nhảy >25% nhưng không khớp tỉ lệ chia tách "
              "mạnh đặc trưng (có thể là dữ liệu hỏng hoặc hiệu chỉnh cổ tức tiền mặt).")


if __name__ == "__main__":
    main()
