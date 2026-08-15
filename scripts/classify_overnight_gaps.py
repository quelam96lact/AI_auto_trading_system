"""Bước 1 (prompt 2026-08-15-hermes-data-integrity.md): phân loại 837 bước nhảy
qua đêm >25% (có khớp lệnh cả 2 bên) trong bars_daily theo NGUYÊN NHÂN, tìm
phần dư thật sự không giải thích được.

CHỈ ĐỌC bars_daily — TUYỆT ĐỐI không UPDATE/DELETE/INSERT. Kết quả ghi ra
scripts/research_gap_causes.csv (file, không phải bảng DB).

4 nguyên nhân hợp lệ cần loại TRƯỚC (mỗi cái kiểm bằng dữ liệu, không suy đoán):
  1. niem_yet_moi         — bar t nằm trong 3 bar đầu đời của mã (phiên đầu
                             sau niêm yết dùng biên độ ±20/30/40% thay vì
                             ±7/10/15%).
  2. tro_lai_sau_dinh_chi — giữa bar t-1 và t có >= 10 ngày MỞ CỬA (toàn thị
                             trường có giao dịch) mà mã này không có bar —
                             mã bị đình chỉ dài, phiên đầu trở lại dùng biên
                             độ rộng.
  3. bar_thieu            — giữa bar t-1 và t có 1..9 ngày mở cửa mà mã không
                             có bar: close(t-1) thực ra là của t-k (tích luỹ
                             nhiều phiên), không phải bước nhảy qua 1 đêm.
  4. chia_tach_ti_le_le   — ratio < 1 khớp p/(p+k) với p, k nguyên nhỏ (vd
                             10:11, 100:15) ngoài tập {1:2, 1:3, 2:3} đang
                             kiểm — bộ tỉ lệ cũ quá hẹp, không phải hỏng.
  Phần còn lại: khong_giai_thich_duoc.

Lịch mở cửa = các ngày có >= 1 mã có bar trong bars_daily (GROUP BY ngày) —
tự nó loại nghỉ lễ (cả thị trường đóng) ra khỏi "ngày thiếu".

CLI:
  uv run python scripts/classify_overnight_gaps.py [--dsn ...] [--csv scripts/research_gap_causes.csv]
"""

import argparse
import csv
import os
import statistics
import sys
from pathlib import Path

import psycopg

from trading.calendar_vn import TZ

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GAP_LO, GAP_HI = 0.75, 1.25
VOL_ANOMALY_X = 5.0  # volume >= 5x trung vị = "bất thường" (khớp script cũ)
MAX_CAL_DAYS = 60  # hơn = đã nằm trong nhóm long_suspend, không phải 837 này
# Đình chỉ dài: số ngày mở cửa mà mã không có bar >= ngưỡng này
SUSPEND_MIN_OPEN_DAYS = 10
# Bar thiếu: 1..SUSPEND_MIN_OPEN_DAYS-1 ngày mở cửa không có bar
NEW_LISTING_MAX_INDEX = 2  # bar t có index (0-based trong lịch sử mã) <= 2
ODD_SPLIT_TOL = 0.015  # sai số khớp tỉ lệ p/(p+k)
ODD_SPLIT_MAX_P = 200
ODD_SPLIT_MAX_K = 600
# Tỉ lệ chia tách MẠNH đã biết (51 sự kiện/49 mã ở a7c6c41) — nếu lọt vào 837
# do định nghĩa chồng lấn thì KHÔNG tính vào phần dư.
STRONG_SPLIT_RATIOS = {0.5, 1 / 3, 2 / 3}


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


def resolve_dsn(override: str | None) -> str:
    if override:
        return override
    _load_dotenv()
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise SystemExit("DB_DSN chưa set — cần .env hoặc --dsn")
    return dsn.replace("localhost", "127.0.0.1")


def _is_dirty(o: float, h: float, l: float, c: float) -> bool:
    return o <= 0 or h <= 0 or l <= 0 or c <= 0


def odd_split_label(r: float) -> str | None:
    """Kiểm tra r có khớp MỘT TẬP TỈ LỆ doanh nghiệp CỤ THỂ đã chọn trước
    (curated, không phải lưới p/m) — chỉ dùng để GẮN CỜ "nghi" cho phần dư
    chờ đối chiếu SSI ở Bước 2, KHÔNG phải phân loại chính thức.

    Vì sao không dùng lưới p/m (p, m <= 200, sai số 1.5%): phân số với mẫu
    <= 200 dày đặc tới mức BẤT KỲ tỉ lệ nào trong [0.4, 1.5] cũng có xấp xỉ
    trong 1.5% — matcher khớp tất cả thì bằng chứng vô nghĩa (đúng bẫy
    "ngưỡng lọc tính từ chính dữ liệu" ở a7c6c41). Chỉ các tỉ lệ VN thực tế
    phổ biến mới đáng xét: phát hành/thưởng 100:q và 10:q (q tròn), chia tách
    p:q nhỏ, gộp cổ phiếu hiếm gặp.
    """
    if r >= 1:
        return None
    # Tỉ lệ mạnh đã biết không phải "tỉ lệ lẻ" — trả None để caller xếp vào
    # nhóm chia_tach_manh_da_biet (không tính phần dư).
    if any(abs(r - s) / s <= ODD_SPLIT_TOL for s in STRONG_SPLIT_RATIOS):
        return None
    # Tập tỉ lệ phát hành/thưởng cổ phiếu phổ biến VN (q tròn, không phải lưới)
    ratios: dict[float, str] = {}
    for q in (40, 50, 60, 80, 100, 120, 150, 200, 250, 300, 400, 500):
        ratios[100 / (100 + q)] = f"100:{q}"
    for q in (4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50):
        ratios[10 / (10 + q)] = f"10:{q}"
    for p, q in ((2, 5), (3, 5), (3, 7), (4, 7), (5, 8), (5, 9), (7, 10)):
        ratios[p / q] = f"{p}:{q}"
    best: tuple[float, str] | None = None
    for v, label in ratios.items():
        if abs(r - v) / v <= ODD_SPLIT_TOL and (
            best is None or abs(r - v) < best[0]
        ):
            best = (abs(r - v), label)
    return best[1] if best else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--csv", default="scripts/research_gap_causes.csv")
    args = ap.parse_args()
    dsn = resolve_dsn(args.dsn)

    with psycopg.connect(dsn) as c:
        # Lịch mở cửa: ngày (HCM) có >= 1 mã có bar -> thị trường mở.
        rows = c.execute(
            "SELECT DISTINCT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
            "FROM bars_daily"
        ).fetchall()
        market_days = {r[0] for r in rows}
        symbols = [r[0] for r in c.execute(
            "SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol"
        )]

        all_gaps: list[dict] = []
        for sym in symbols:
            bars = c.execute(
                "SELECT ts, open, high, low, close, volume FROM bars_daily "
                "WHERE symbol = %s ORDER BY ts",
                (sym,),
            ).fetchall()
            clean = [(ts, o, h, l, cl, v) for ts, o, h, l, cl, v in bars
                     if not _is_dirty(o, h, l, cl)]
            vols = [v for _, _, _, _, _, v in clean]
            median_vol = statistics.median(vols) if vols else 0.0

            prev = None  # (ts, close, volume)
            for idx, (ts, _o, _h, _l, cl, v) in enumerate(clean):
                if prev is not None and prev[1] > 0:
                    p_ts, p_c, p_v = prev
                    r = cl / p_c
                    cal_days = (ts.astimezone(TZ).date()
                                - p_ts.astimezone(TZ).date()).days
                    vol_ratio = v / median_vol if median_vol > 0 else None
                    outside = r < GAP_LO or r > GAP_HI
                    traded = (p_v or 0) > 0 and (v or 0) > 0
                    # Đúng định nghĩa 837 của check_price_adjustment.py:
                    # |r-1|>25%, có khớp lệnh 2 bên, volume < 5x trung vị,
                    # không qua khoảng ngừng > 60 ngày lịch.
                    if (outside and traded
                            and (vol_ratio is None or vol_ratio < VOL_ANOMALY_X)
                            and cal_days <= MAX_CAL_DAYS):
                        open_between = [
                            d for d in market_days
                            if p_ts.astimezone(TZ).date() < d
                            < ts.astimezone(TZ).date()
                        ]
                        n_open_gap = len(open_between)
                        if idx <= NEW_LISTING_MAX_INDEX:
                            cause = "niem_yet_moi"
                            detail = f"index={idx}"
                        elif n_open_gap >= SUSPEND_MIN_OPEN_DAYS:
                            cause = "tro_lai_sau_dinh_chi"
                            detail = f"open_days_thieu={n_open_gap}"
                        elif n_open_gap >= 1:
                            cause = "bar_thieu"
                            detail = f"open_days_thieu={n_open_gap}"
                        else:
                            if r < 1 and any(
                                abs(r - s) / s <= ODD_SPLIT_TOL
                                for s in STRONG_SPLIT_RATIOS
                            ):
                                cause = "chia_tach_manh_da_biet"
                                detail = "trung 51 su kien da biet (a7c6c41)"
                            else:
                                lbl = odd_split_label(r)
                                if lbl:
                                    cause = "nghi_chia_tach_le"
                                    detail = f"ty_le={lbl}"
                                else:
                                    cause = "khong_giai_thich_duoc"
                                    detail = ""
                        all_gaps.append({
                            "symbol": sym,
                            "ts": ts.astimezone(TZ).strftime("%Y-%m-%d"),
                            "prev_ts": p_ts.astimezone(TZ).strftime("%Y-%m-%d"),
                            "prev_close": p_c,
                            "close": cl,
                            "ratio": round(r, 6),
                            "cal_days": cal_days,
                            "open_days_thieu": n_open_gap,
                            "prev_volume": p_v,
                            "volume": v,
                            "idx": idx,
                            "cause": cause,
                            "detail": detail,
                        })
                prev = (ts, cl, v)
            if len(symbols) and len(all_gaps) % 500 == 0:
                pass

    by_cause: dict[str, list[dict]] = {}
    for g in all_gaps:
        by_cause.setdefault(g["cause"], []).append(g)

    print("=" * 78)
    print("BƯỚC 1 — PHÂN LOẠI BƯỚC NHẢY QUA ĐÊM >25% (có khớp lệnh 2 bên)")
    print(f"Tổng: {len(all_gaps)} sự kiện trên {len({g['symbol'] for g in all_gaps})} mã")
    print("=" * 78)
    order = [
        ("niem_yet_moi", "Phiên đầu sau niêm yết mới (biên độ rộng ±20/30/40%)"),
        ("tro_lai_sau_dinh_chi", "Phiên đầu sau đình chỉ dài (>= 10 ngày mở cửa không có bar)"),
        ("bar_thieu", "Bar bị thiếu trong DB (1..9 ngày mở cửa trống -> tích luỹ nhiều phiên)"),
        ("chia_tach_manh_da_biet", "Chia tách tỉ lệ mạnh đã biết {1:2, 1:3, 2:3} (trùng 51 sự kiện a7c6c41)"),
        ("nghi_chia_tach_le", "NGHI chia tách tỉ lệ lẻ (curated, chờ đối chiếu SSI ở Bước 2)"),
        ("khong_giai_thich_duoc", "KHÔNG GIẢI THÍCH ĐƯỢC (phần dư)"),
    ]
    unexplained = 0
    for key, label in order:
        evs = by_cause.get(key, [])
        syms = {g["symbol"] for g in evs}
        print(f"  {label:<55} {len(evs):>6} sự kiện / {len(syms):>4} mã")
        if key == "khong_giai_thich_duoc":
            unexplained = len(evs)

    # Phân tích phần dư: tăng/giảm, vol 1 lô (100) = nghi giá treo
    leftovers = by_cause.get("khong_giai_thich_duoc", [])
    if leftovers:
        n_up = sum(1 for g in leftovers if g["ratio"] > 1)
        n_down = len(leftovers) - n_up
        n_lot100 = sum(
            1 for g in leftovers
            if g["volume"] <= 100 or g["prev_volume"] <= 100
        )
        n_both_big = len(leftovers) - n_lot100
        print()
        print(f"  Chi tiết phần dư ({len(leftovers)}): tăng {n_up}, giảm {n_down}, "
              f"có bên volume <= 1 lô (100): {n_lot100}, cả 2 bên volume > 1 lô: {n_both_big}")

    print()
    print("Ví dụ theo từng nhóm:")
    for key, label in order:
        evs = by_cause.get(key, [])
        if not evs:
            continue
        print(f"  [{key}]")
        for g in evs[:8]:
            print(f"    {g['symbol']:<6} {g['prev_ts']} {g['prev_close']:>12,.0f} -> "
                  f"{g['ts']} {g['close']:>12,.0f}  r={g['ratio']:.4f} "
                  f"vol {g['prev_volume']:>8,}/{g['volume']:>8,}  {g['detail']}")

    if unexplained:
        print()
        print(f"PHẦN DƯ: {unexplained} sự kiện trên "
              f"{len({g['symbol'] for g in by_cause.get('khong_giai_thich_duoc', [])})} "
              f"mã thật sự không giải thích được bằng 4 nguyên nhân hợp lệ.")

    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "symbol", "ts", "prev_ts", "prev_close", "close", "ratio",
            "cal_days", "open_days_thieu", "prev_volume", "volume", "idx",
            "cause", "detail",
        ])
        w.writeheader()
        for g in sorted(all_gaps, key=lambda x: (x["ts"], x["symbol"])):
            w.writerow(g)
    print(f"\nĐã ghi {len(all_gaps)} sự kiện -> {args.csv} (file research, "
          f"KHÔNG chạm DB)")


if __name__ == "__main__":
    main()
