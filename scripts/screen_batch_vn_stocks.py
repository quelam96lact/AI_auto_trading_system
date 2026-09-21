"""Mở rộng sàng lọc tín hiệu ra nhiều mã — Brief đợt 77.

Mục tiêu:
  1. Chọn 50 mã có giá trị giao dịch bình quân ngày cao nhất trong IS (2016-2025),
     sau khi loại các mã trong exclusions.txt.
  2. Chạy screen_symbol() (đợt 76) cho từng mã — bắt lỗi từng mã riêng biệt.
  3. Tổng hợp: đếm CO_TIN_HIEU theo đặc trưng, so với kỳ vọng nhị thức (p=0.05).

Ràng buộc (từ brief):
  - KHÔNG sửa screen_vn_signal_candidates.py — chỉ gọi screen_symbol() nguyên gốc.
  - IS = 2016-01-01 -> 2025-12-31; 2026 NIÊM PHONG.
  - Không thêm dependency mới (tự viết binomial bằng Python thuần).
  - Không commit, không push.
"""

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from screen_vn_signal_candidates import FEATURE_NAMES, screen_symbol
except ImportError:
    from scripts.screen_vn_signal_candidates import FEATURE_NAMES, screen_symbol

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thư mục gốc project để tìm exclusions.txt
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

IS_START = date(2016, 1, 1)
IS_END = date(2025, 12, 31)

# Tỷ lệ nền null: P95 theo hoán vị khối → nếu đặc trưng không có thông tin,
# xác suất gắn cờ CO_TIN_HIEU = ~5%.
NULL_HIT_RATE = 0.05

# Số mã muốn chọn
TOP_N = 50


# ==============================================================================
# Task 1 — Chọn 50 mã thanh khoản cao nhất
# ==============================================================================


def load_exclusions(path: Path | None = None) -> set[str]:
    """Đọc danh sách mã bị loại từ exclusions.txt."""
    if path is None:
        path = _PROJECT_ROOT / "exclusions.txt"
    if not path.exists():
        return set()
    return {line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def select_top_liquid_symbols(
    conn: psycopg.Connection,
    top_n: int = TOP_N,
    is_start: date = IS_START,
    is_end: date = IS_END,
    exclusions: set[str] | None = None,
) -> list[tuple[str, float]]:
    """Chọn top_n mã có AVG(close * volume) cao nhất trong khoảng IS.

    Loại các mã trong exclusions.txt (giống đợt 61/64).
    Trả về danh sách tuple (symbol, avg_turnover) đã sắp xếp giảm dần.
    """
    if exclusions is None:
        exclusions = set()

    sql = """
        SELECT symbol,
               AVG(close * volume) AS avg_turnover
        FROM bars_daily
        WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= %s
          AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= %s
        GROUP BY symbol
        ORDER BY avg_turnover DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (is_start, is_end))
        rows = cur.fetchall()

    result: list[tuple[str, float]] = []
    for symbol, avg_t in rows:
        if symbol.upper() in exclusions:
            continue
        result.append((symbol.upper(), float(avg_t)))
        if len(result) >= top_n:
            break

    return result


# ==============================================================================
# Task 3 — Binomial test (Python thuần, không cần scipy)
# ==============================================================================


def _log_factorial(n: int) -> float:
    """Tính ln(n!) dùng công thức Stirling gần đúng hoặc tính trực tiếp."""
    if n <= 20:
        result = 0.0
        for k in range(2, n + 1):
            result += math.log(k)
        return result
    # Stirling's approximation đủ chính xác cho n > 20
    return n * math.log(n) - n + 0.5 * math.log(2 * math.pi * n)


def _log_binom_coeff(n: int, k: int) -> float:
    """Tính ln(C(n,k)) = ln(n!) - ln(k!) - ln((n-k)!)."""
    if k < 0 or k > n:
        return float("-inf")
    return _log_factorial(n) - _log_factorial(k) - _log_factorial(n - k)


def binomial_p_value(observed: int, n: int, p: float) -> float:
    """Tính P(X >= observed) với X ~ Binomial(n, p).

    Đây là upper-tail p-value: xác suất quan sát được >= observed
    nếu tỷ lệ nền thật sự là p (mô hình null).

    Không dùng scipy — dùng công thức nhị thức Python thuần.
    """
    if observed <= 0:
        return 1.0
    if n <= 0:
        return 1.0 if observed <= 0 else 0.0

    log_p = math.log(p) if p > 0 else float("-inf")
    log_1mp = math.log(1.0 - p) if p < 1 else float("-inf")

    total = 0.0
    for k in range(observed, n + 1):
        # log P(X = k) = log C(n,k) + k*log(p) + (n-k)*log(1-p)
        log_pk = _log_binom_coeff(n, k) + k * log_p + (n - k) * log_1mp
        total += math.exp(log_pk)

    # Clamp vì floating-point có thể vượt 1.0 nhẹ
    return min(total, 1.0)


def is_hit_rate_abnormal(observed: int, n: int, p: float = NULL_HIT_RATE, alpha: float = 0.05) -> bool:
    """True nếu tỷ lệ trúng CO_TIN_HIEU bất thường so với ngẫu nhiên (p-value < alpha)."""
    return binomial_p_value(observed, n, p) < alpha


def summarize_results(
    all_results: list[dict],
    n_total: int,
) -> list[dict]:
    """Tổng hợp kết quả sàng lọc: đếm CO_TIN_HIEU mỗi đặc trưng và kiểm binomial.

    Args:
        all_results: Danh sách kết quả từ screen_symbol() cho từng mã thành công.
        n_total: Tổng số mã sàng lọc thành công (N ≤ 50).

    Returns:
        Danh sách dict: feature, n_hit, n_total, expected_random, p_value, is_abnormal.
    """
    n = n_total

    # Đếm CO_TIN_HIEU per feature
    hit_count: dict[str, int] = {f: 0 for f in FEATURE_NAMES}
    for res in all_results:
        for r in res["results"]:
            if r["flag"] == "CO_TIN_HIEU":
                hit_count[r["feature"]] += 1

    summary = []
    for feat in FEATURE_NAMES:
        observed = hit_count[feat]
        expected = NULL_HIT_RATE * n
        pv = binomial_p_value(observed, n, NULL_HIT_RATE)
        abnormal = is_hit_rate_abnormal(observed, n)
        summary.append({
            "feature": feat,
            "n_hit": observed,
            "n_total": n,
            "expected_random": expected,
            "p_value": pv,
            "is_abnormal": abnormal,
        })
    return summary


# ==============================================================================
# In kết quả
# ==============================================================================


def print_top_symbols(symbols_turnover: list[tuple[str, float]]) -> None:
    """In bảng 50 mã đã chọn với giá trị giao dịch bình quân."""
    print("\n" + "=" * 72)
    print(f"  DANH SÁCH {len(symbols_turnover)} MÃ THANH KHOẢN CAO NHẤT (IS 2016-2025)")
    print("  Tiêu chí: AVG(close × volume) - Sau khi loại exclusions.txt")
    print("=" * 72)
    print(f"{'#':<4} {'Mã':<8} {'AVG(close×volume)':<22}")
    print("-" * 38)
    for i, (sym, avg_t) in enumerate(symbols_turnover, 1):
        print(f"{i:<4} {sym:<8} {avg_t:>20,.0f}")


def print_batch_summary(summary: list[dict]) -> None:
    """In bảng tổng hợp Task 3."""
    n = summary[0]["n_total"] if summary else 0
    expected = NULL_HIT_RATE * n
    print("\n" + "=" * 88)
    print(f"  TỔNG HỢP TASK 3 — TỶ LỆ TRÚNG CO_TIN_HIEU vs KỲ VỌNG NGẪU NHIÊN (N={n} mã)")
    print(f"  Kỳ vọng ngẫu nhiên: {NULL_HIT_RATE*100:.0f}% × {n} = {expected:.1f} mã/đặc trưng")
    print("=" * 88)
    print(
        f"{'Đặc trưng':<20} | {'Trúng':>6} | {'Kỳ vọng':>8} | {'P-value':>10} | {'Bất thường?'}"
    )
    print("-" * 70)
    for row in summary:
        abnormal_str = "*** BẤT THƯỜNG ***" if row["is_abnormal"] else "bình thường (nhiễu)"
        print(
            f"{row['feature']:<20} | {row['n_hit']:>6} | {row['expected_random']:>8.1f} "
            f"| {row['p_value']:>10.4f} | {abnormal_str}"
        )


def print_abnormal_symbols(all_results: list[dict], summary: list[dict]) -> None:
    """Nếu có đặc trưng bất thường, liệt kê chính xác những mã trúng."""
    abnormal_features = [row for row in summary if row["is_abnormal"]]
    if not abnormal_features:
        return

    print("\n" + "=" * 88)
    print("  DANH SÁCH MÃ TRÚNG CO_TIN_HIEU CHO ĐẶC TRƯNG BẤT THƯỜNG")
    print("  (Chỉ liệt kê sự kiện — không suy diễn nguyên nhân)")
    print("=" * 88)
    for row in abnormal_features:
        feat = row["feature"]
        print(f"\n  Đặc trưng: {feat} (trúng {row['n_hit']}/{row['n_total']} mã)")
        for res in all_results:
            for r in res["results"]:
                if r["feature"] == feat and r["flag"] == "CO_TIN_HIEU":
                    print(
                        f"    {res['symbol']}: rho_sau={r['rho_sau']:+.4f}, "
                        f"ngưỡng={r['threshold']:.4f}"
                    )


# ==============================================================================
# main
# ==============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sàng lọc tín hiệu kỹ thuật mở rộng — Brief đợt 77."
    )
    parser.add_argument("--top-n", type=int, default=TOP_N, help=f"Số mã top thanh khoản (mặc định {TOP_N})")
    parser.add_argument("--permutations", type=int, default=500, help="Số lần hoán vị khối (mặc định 500)")
    parser.add_argument("--block-size", type=int, default=20, help="Kích thước khối hoán vị theo ngày (mặc định 20)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dsn", default=None, help="Database DSN override")
    parser.add_argument(
        "--exclusions",
        default=None,
        help="Đường dẫn tới exclusions.txt (mặc định: <project_root>/exclusions.txt)",
    )
    # Task 4.1: tái hiện đợt 76 nếu truyền --verify-d76
    parser.add_argument(
        "--verify-d76",
        action="store_true",
        help="Chỉ chạy 3 mã HPG/IJC/AAA để kiểm tái hiện kết quả đợt 76",
    )
    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))

    if args.verify_d76:
        print("=== TÁI HIỆN KẾT QUẢ ĐỢT 76 (HPG / IJC / AAA) ===")
        for sym in ["HPG", "IJC", "AAA"]:
            res = screen_symbol(
                conn,
                symbol=sym,
                n_permutations=args.permutations,
                seed=args.seed,
                block_size_days=args.block_size,
            )
            print(f"\n{sym}: threshold_p95={res['threshold_p95']:.4f}, rho_control={res['rho_control']:+.4f}")
            for r in res["results"]:
                print(f"  {r['feature']:<20} rho_sau={r['rho_sau']:+.4f}  {r['flag']}")
        conn.close()
        return

    print("=== SÀNG LỌC TÍN HIỆU MỞ RỘNG — BRIEF ĐỢT 77 ===")
    print(f"Khoảng IS: {IS_START} → {IS_END} (2026 NIÊM PHONG)")
    print(f"Cấu hình hoán vị: {args.permutations} lượt, khối {args.block_size} ngày, seed={args.seed}")

    # Task 1: Chọn 50 mã
    exclusion_path = Path(args.exclusions) if args.exclusions else None
    exclusions = load_exclusions(exclusion_path)
    print(f"\nĐã tải {len(exclusions)} mã exclusions từ {exclusion_path or _PROJECT_ROOT / 'exclusions.txt'}")

    top_symbols = select_top_liquid_symbols(
        conn,
        top_n=args.top_n,
        is_start=IS_START,
        is_end=IS_END,
        exclusions=exclusions,
    )
    print_top_symbols(top_symbols)

    symbol_list = [sym for sym, _ in top_symbols]

    # Task 2: Chạy sàng lọc từng mã, bắt lỗi riêng biệt
    print(f"\n{'=' * 88}")
    print(f"  TASK 2 — CHẠY SÀNG LỌC CHO {len(symbol_list)} MÃ (lần lượt, bắt lỗi từng mã)")
    print(f"{'=' * 88}")

    all_results: list[dict] = []
    skipped: list[tuple[str, str]] = []

    for i, sym in enumerate(symbol_list, 1):
        print(f"\n[{i:02d}/{len(symbol_list)}] Sàng lọc {sym}...", end=" ", flush=True)
        try:
            res = screen_symbol(
                conn,
                symbol=sym,
                n_permutations=args.permutations,
                seed=args.seed,
                block_size_days=args.block_size,
            )
            all_results.append(res)
            n_signal = sum(1 for r in res["results"] if r["flag"] == "CO_TIN_HIEU")
            print(f"OK ({res['n_bars']} nến, threshold={res['threshold_p95']:.4f}, CO_TIN_HIEU={n_signal}/6)")
        except (ValueError, RuntimeError) as exc:
            reason = str(exc)
            skipped.append((sym, reason))
            print(f"BỎ QUA — {reason}")

    conn.close()

    # Tổng hợp mã bị loại
    print(f"\n{'=' * 88}")
    print(f"  TASK 2 KẾT QUẢ: {len(all_results)} mã thành công, {len(skipped)} mã bị loại")
    if skipped:
        print("\n  Mã bị loại:")
        for sym, reason in skipped:
            print(f"    {sym}: {reason}")
    print(f"{'=' * 88}")

    if not all_results:
        print("\nKhông có mã nào sàng lọc thành công — dừng.")
        return

    # Task 3: Tổng hợp binomial
    n_ok = len(all_results)
    summary = summarize_results(all_results, n_ok)
    print_batch_summary(summary)
    print_abnormal_symbols(all_results, summary)

    # Kết luận tổng quát
    n_abnormal = sum(1 for row in summary if row["is_abnormal"])
    print(f"\n{'=' * 88}")
    if n_abnormal == 0:
        print(
            f"  KẾT LUẬN: Tất cả {len(FEATURE_NAMES)} đặc trưng có tỷ lệ trúng ≈ 5% (nhiễu)."
        )
        print("  Nhất quán với đợt 76 — không có đặc trưng nào vượt ngưỡng ngẫu nhiên trên mẫu rộng.")
    else:
        print(
            f"  KẾT LUẬN: {n_abnormal}/{len(FEATURE_NAMES)} đặc trưng có tỷ lệ trúng BẤT THƯỜNG."
        )
        print("  Xem bảng trên để biết các mã cụ thể — cần Claude kiểm tra thêm.")
    print(f"{'=' * 88}")


if __name__ == "__main__":
    main()
