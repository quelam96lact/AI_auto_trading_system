"""Sàng lọc tín hiệu kỹ thuật cho cổ phiếu VN (Brief đợt 76).

Mục tiêu:
Kiểm tra xem trong 6 đặc trưng kỹ thuật đơn giản tính từ bars_daily cho 3 mã
đang chạy sống (HPG, IJC, AAA), có tồn tại MỘT đặc trưng nào mang tương quan thật
với lợi suất tương lai fwd_ret_1d hay không, trước khi tính đến việc đưa ML vào.

Khác biệt cốt lõi với leakage_audit (Brief 76 §2.2):
- leakage_audit trả lời: "Đặc trưng có bị rò rỉ nhìn trước không?"
    -> So sánh bất đối xứng rho_sau > rho_truoc và |rho_sau| > threshold -> NGHI_VAN.
- screen_vn_signal_candidates trả lời: "Đặc trưng có tương quan dự báo thật không?"
    -> Không quan tâm rho_truoc; gắn cờ CO_TIN_HIEU khi |rho_sau| > threshold (ngược lại KHONG_TIN_HIEU).

Quy ước:
- Dữ liệu: bars_daily từ 2016-01-01 đến 2025-12-31 (In-Sample 10 năm).
- Năm 2026 NIÊM PHONG: không đọc bất kỳ dòng nào của năm 2026.
- Hoán vị khối: block_size_days = 20 ngày giao dịch (≈ 1 tháng) để bảo toàn tự tương quan.
- Chốt an toàn đối chứng: intraday_ret tương quan mạnh dương với ret_past_1d (> 0.50).
"""

import argparse
import math
import sys
from datetime import date

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from audit_information import run_block_permutation_test
    from leakage_audit import compute_leakage_pair
except ImportError:
    from scripts.audit_information import run_block_permutation_test
    from scripts.leakage_audit import compute_leakage_pair

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Danh sách 3 mã đang chạy sống
TARGET_SYMBOLS = ["HPG", "IJC", "AAA"]

# 6 đặc trưng ứng viên tính từ bars_daily
FEATURE_NAMES = [
    "mom_5d",
    "mom_20d",
    "vol_ratio_20d",
    "rsi_14",
    "dist_from_sma20",
    "realized_vol_20d",
]

# Ngưỡng chốt an toàn đối chứng: intraday_ret vs ret_past_1d
CONTROL_MIN_RHO = 0.50

# Mặc định kích thước khối hoán vị: 20 ngày giao dịch ≈ 1 tháng
DEFAULT_BLOCK_SIZE_DAYS = 20


def compute_mom(closes: list[float], period: int) -> list[float | None]:
    """Tính momentum: close[t] / close[t - period] - 1.0."""
    n = len(closes)
    result: list[float | None] = [None] * n
    for i in range(period, n):
        c_prev = closes[i - period]
        if c_prev > 0:
            result[i] = (closes[i] / c_prev) - 1.0
    return result


def compute_vol_ratio(volumes: list[float], period: int = 20) -> list[float | None]:
    """Tính tỷ lệ khối lượng: volume[t] / mean(volume[t-period .. t-1]).

    LƯU Ý: Mẫu số loại trừ volume[t] để đo đột biến khối lượng phiên t so với 20 phiên trước.
    """
    n = len(volumes)
    result: list[float | None] = [None] * n
    for i in range(period, n):
        window = volumes[i - period : i]
        mean_vol = sum(window) / float(period)
        if mean_vol > 0:
            result[i] = volumes[i] / mean_vol
    return result


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Tính RSI chuẩn Wilder 14 ngày, chỉ dùng dữ liệu tới hết phiên t."""
    n = len(closes)
    result: list[float | None] = [None] * n
    if n <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []

    avg_gain = 0.0
    avg_loss = 0.0

    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0.0)
        loss = max(-diff, 0.0)
        gains.append(gain)
        losses.append(loss)

        if i == period:
            avg_gain = sum(gains[:period]) / float(period)
            avg_loss = sum(losses[:period]) / float(period)
            if avg_loss == 0.0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))
        elif i > period:
            avg_gain = (avg_gain * (period - 1) + gain) / float(period)
            avg_loss = (avg_loss * (period - 1) + loss) / float(period)
            if avg_loss == 0.0:
                result[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def compute_dist_from_sma(closes: list[float], period: int = 20) -> list[float | None]:
    """Tính khoảng cách so với SMA20: close[t] / SMA20(close[t-19 .. t]) - 1.0."""
    n = len(closes)
    result: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        sma = sum(window) / float(period)
        if sma > 0:
            result[i] = (closes[i] / sma) - 1.0
    return result


def compute_realized_vol(returns: list[float | None], period: int = 20) -> list[float | None]:
    """Tính độ biến động thực hiện 20 ngày: độ lệch chuẩn mẫu của 20 lợi suất ngày."""
    n = len(returns)
    result: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = [returns[k] for k in range(i - period + 1, i + 1)]
        if any(r is None or math.isnan(r) for r in window):
            continue
        valid_r = [float(r) for r in window]  # type: ignore[arg-type]
        m = sum(valid_r) / float(period)
        var = sum((x - m) ** 2 for x in valid_r) / float(period - 1)
        result[i] = math.sqrt(var)
    return result


def build_candidate_features_panel(daily_bars: list[dict]) -> list[dict]:
    """Dựng bảng đặc trưng ứng viên từ danh sách nến ngày đã sắp xếp theo ts.

    Mỗi nến ngày dict cần có: ts, open, high, low, close, volume.
    Trả về danh sách dict với đầy đủ 6 đặc trưng + biến mục tiêu + biến đối chứng:
    - mom_5d
    - mom_20d
    - vol_ratio_20d
    - rsi_14
    - dist_from_sma20
    - realized_vol_20d
    - intraday_ret: (close[t] - open[t]) / open[t] (đối chứng)
    - ret_past_1d: close[t] / close[t-1] - 1.0
    - fwd_ret_1d: close[t+1] / close[t] - 1.0 (mục tiêu)
    """
    n = len(daily_bars)
    if n == 0:
        return []

    closes = [float(b["close"]) for b in daily_bars]
    opens = [float(b["open"]) for b in daily_bars]
    volumes = [float(b["volume"]) for b in daily_bars]

    # Lợi suất quá khứ và tương lai
    ret_past_1d: list[float | None] = [None] * n
    for i in range(1, n):
        if closes[i - 1] > 0:
            ret_past_1d[i] = (closes[i] / closes[i - 1]) - 1.0

    fwd_ret_1d: list[float | None] = [None] * n
    for i in range(n - 1):
        if closes[i] > 0:
            fwd_ret_1d[i] = (closes[i + 1] / closes[i]) - 1.0

    # Đối chứng: lợi suất trong phiên ngày t
    intraday_ret: list[float | None] = [None] * n
    for i in range(n):
        if opens[i] > 0:
            intraday_ret[i] = (closes[i] - opens[i]) / opens[i]

    # Tính các đặc trưng ứng viên
    mom5 = compute_mom(closes, 5)
    mom20 = compute_mom(closes, 20)
    vol_ratio = compute_vol_ratio(volumes, 20)
    rsi14 = compute_rsi(closes, 14)
    dist_sma = compute_dist_from_sma(closes, 20)
    rvol = compute_realized_vol(ret_past_1d, 20)

    rows: list[dict] = []
    for i in range(n):
        rows.append({
            "ts": daily_bars[i]["ts"],
            "mom_5d": mom5[i],
            "mom_20d": mom20[i],
            "vol_ratio_20d": vol_ratio[i],
            "rsi_14": rsi14[i],
            "dist_from_sma20": dist_sma[i],
            "realized_vol_20d": rvol[i],
            "intraday_ret": intraday_ret[i],
            "ret_past_1d": ret_past_1d[i],
            "fwd_ret_1d": fwd_ret_1d[i],
        })

    return rows


def classify_signal(rho_sau: float, threshold: float) -> str:
    """Gắn cờ sàng lọc tín hiệu (Brief đợt 76 §2.2).

    CO_TIN_HIEU khi: |rho_sau| > threshold.
    KHONG_TIN_HIEU khi: |rho_sau| <= threshold.

    Khác với classify_leakage (so sánh rho_sau > rho_truoc), ở đây chỉ kiểm định
    liệu tương quan với lợi suất tương lai có vượt ngưỡng ngẫu nhiên phân phối null P95 hay không.
    """
    if abs(rho_sau) > threshold:
        return "CO_TIN_HIEU"
    return "KHONG_TIN_HIEU"


def check_intraday_control(
    rows: list[dict],
    min_rho: float = CONTROL_MIN_RHO,
) -> tuple[float, bool]:
    """Kiểm tra chốt an toàn đối chứng: intraday_ret vs ret_past_1d.

    Cả hai biến đều phản ánh chuyển động giá trong cùng ngày t. Tương quan mạnh dương
    xác nhận đường ống nạp dữ liệu và tính lợi suất không bị lệch pha / off-by-one.
    """
    feat_vals = [r.get("intraday_ret") for r in rows]
    past_vals = [r.get("ret_past_1d") for r in rows]
    fut_vals = [r.get("fwd_ret_1d") for r in rows]

    rho_truoc, _rho_sau, _n_truoc, _n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)
    ok = rho_truoc > min_rho
    return rho_truoc, ok


def load_symbol_is_bars(
    conn: psycopg.Connection,
    symbol: str,
    is_start: date = date(2016, 1, 1),
    is_end: date = date(2025, 12, 31),
) -> list[dict]:
    """Tải dữ liệu In-Sample (IS) của một mã từ bars_daily.

    Quy ước In-Sample: 2016-01-01 -> 2025-12-31 theo ngày giao dịch giờ VN.
    Tuyệt đối KHÔNG đọc dữ liệu từ năm 2026 trở đi (niêm phong).
    """
    sql = """
        SELECT ts, (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d,
               open, high, low, close, volume
        FROM bars_daily
        WHERE symbol = %s
          AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= %s
          AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol, is_start, is_end))
        rows = cur.fetchall()

    return [
        {
            "ts": r[0],
            "date": r[1],
            "open": float(r[2]),
            "high": float(r[3]),
            "low": float(r[4]),
            "close": float(r[5]),
            "volume": float(r[6]),
        }
        for r in rows
    ]


def screen_symbol(
    conn: psycopg.Connection,
    symbol: str,
    n_permutations: int = 500,
    seed: int = 42,
    block_size_days: int = DEFAULT_BLOCK_SIZE_DAYS,
    is_start: date = date(2016, 1, 1),
    is_end: date = date(2025, 12, 31),
) -> dict:
    """Chạy sàng lọc tín hiệu độc lập cho một mã cổ phiếu.

    Quy trình:
    1. Tải nến ngày IS (2016 - 2025).
    2. Dựng bảng 6 đặc trưng ứng viên + biến mục tiêu fwd_ret_1d + biến đối chứng intraday_ret.
    3. Kiểm tra chốt an toàn đối chứng (intraday_ret vs ret_past_1d > 0.50).
    4. Hoán vị khối 20 ngày giao dịch (500 lần) tìm ngưỡng null P95 FWER.
    5. Tính rho_sau (và rho_truoc) cho từng đặc trưng, gắn cờ CO_TIN_HIEU / KHONG_TIN_HIEU.
    """
    bars = load_symbol_is_bars(conn, symbol, is_start=is_start, is_end=is_end)
    if len(bars) < 50:
        raise ValueError(f"Dữ liệu {symbol} không đủ nến IS ({len(bars)} nến)")

    panel = build_candidate_features_panel(bars)

    # 1. Chốt an toàn
    rho_ctrl, ctrl_ok = check_intraday_control(panel)
    if not ctrl_ok:
        raise RuntimeError(
            f"CHỐT AN TOÀN THẤT BẠI cho {symbol}: intraday_ret rho = {rho_ctrl:.4f} (yêu cầu > {CONTROL_MIN_RHO:.2f})"
        )

    # 2. Hoán vị khối 20 ngày (target = fwd_ret_1d)
    threshold_95, _ = run_block_permutation_test(
        panel,
        n_permutations=n_permutations,
        block_size_hours=block_size_days,  # mỗi hàng là 1 ngày giao dịch
        seed=seed,
        feature_names=FEATURE_NAMES,
        target_names=["fwd_ret_1d"],
    )

    # 3. Tính tương quan và gắn cờ
    feature_results = []
    for feat in FEATURE_NAMES:
        feat_vals = [r.get(feat) for r in panel]
        past_vals = [r.get("ret_past_1d") for r in panel]
        fut_vals = [r.get("fwd_ret_1d") for r in panel]

        rho_truoc, rho_sau, n_truoc, n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)
        flag = classify_signal(rho_sau, threshold_95)

        feature_results.append({
            "feature": feat,
            "rho_truoc": rho_truoc,
            "rho_sau": rho_sau,
            "n_truoc": n_truoc,
            "n_sau": n_sau,
            "threshold": threshold_95,
            "flag": flag,
        })

    return {
        "symbol": symbol,
        "n_bars": len(bars),
        "rho_control": rho_ctrl,
        "threshold_p95": threshold_95,
        "results": feature_results,
    }


def print_symbol_results(res: dict) -> None:
    """In kết quả sàng lọc cho một mã."""
    symbol = res["symbol"]
    print(f"\n{'=' * 88}")
    print(
        f"  KẾT QUẢ SÀNG LỌC TÍN HIỆU: {symbol} (N = {res['n_bars']} phiên IS 2016-2025)"
    )
    print(
        f"  Chốt đối chứng (intraday vs ret_past): rho = {res['rho_control']:+.4f} (ĐẠT > {CONTROL_MIN_RHO:.2f})"
    )
    print(f"  Ngưỡng hoán vị khối P95 (FWER 6 đặc trưng): {res['threshold_p95']:.4f}")
    print(f"{'=' * 88}")
    print(
        f"{'Đặc trưng':<20} | {'rho_truoc':>10} | {'rho_sau':>10} | {'Ngưỡng P95':>10} | Cờ sàng lọc"
    )
    print("-" * 88)

    for r in res["results"]:
        flag_display = "*** CÓ TÍN HIỆU ***" if r["flag"] == "CO_TIN_HIEU" else "KHÔNG TÍN HIỆU"
        print(
            f"{r['feature']:<20} | {r['rho_truoc']:>+10.4f} | {r['rho_sau']:>+10.4f} | {r['threshold']:>10.4f} | {flag_display}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sàng lọc tín hiệu kỹ thuật cho cổ phiếu VN (Brief đợt 76)."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=TARGET_SYMBOLS,
        help="Danh sách mã cần sàng lọc (mặc định HPG IJC AAA)",
    )
    parser.add_argument(
        "--permutations",
        type=int,
        default=500,
        help="Số lần hoán vị khối (mặc định 500)",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=DEFAULT_BLOCK_SIZE_DAYS,
        help="Kích thước khối hoán vị (tính bằng số ngày giao dịch, mặc định 20)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    print("=== SÀNG LỌC TÍN HIỆU KỸ THUẬT VN STOCKS (Brief đợt 76) ===")
    print(f"Mã sàng lọc: {', '.join(args.symbols)}")
    print("Khoảng In-Sample: 2016-01-01 -> 2025-12-31 (Năm 2026 NIÊM PHONG)")
    print(f"Cấu hình hoán vị: {args.permutations} lượt, khối {args.block_size} ngày, seed={args.seed}")

    all_results = []
    for sym in args.symbols:
        res = screen_symbol(
            conn,
            symbol=sym,
            n_permutations=args.permutations,
            seed=args.seed,
            block_size_days=args.block_size,
        )
        print_symbol_results(res)
        all_results.append(res)

    conn.close()

    # Tổng kết bảng ma trận
    print(f"\n{'=' * 88}")
    print("  TỔNG HỢP KẾT QUẢ SÀNG LỌC TRÊN CẢ 3 MÃ")
    print(f"{'=' * 88}")
    header = f"{'Đặc trưng':<20}"
    for sym in args.symbols:
        header += f" | {sym + ' (rho_sau / Co)':<22}"
    print(header)
    print("-" * len(header))

    for feat in FEATURE_NAMES:
        line = f"{feat:<20}"
        for res in all_results:
            r_feat = next(r for r in res["results"] if r["feature"] == feat)
            status = "CO_TIN_HIEU" if r_feat["flag"] == "CO_TIN_HIEU" else "KHONG"
            line += f" | {r_feat['rho_sau']:>+7.4f} ({status:<11})"
        print(line)


if __name__ == "__main__":
    main()
