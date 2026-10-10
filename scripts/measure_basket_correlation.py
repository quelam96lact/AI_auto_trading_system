"""Ma tran tuong quan cua ro ma dang chay (Brief dot 180 - DANG KY TRUOC, phep do MO TA).

Muc tieu:
Kiem chung ro dang chay [HPG, IJC, AAA] co thuc su la 3 cuoc doc lap khong?
Do ma tran tuong quan Pearson, Spearman, tri rieng, so cuoc hieu dung (PR),
moc so sanh thi truong toan bo co phieu, so phien ca 3 cung giam,
va mo ta rui ro ro theo dinh co ATR cua RiskManager.

Cua so A: 2017-01-01 -> 2022-12-31 (niem phong, read_bars).
Cua so B: 2023-01-01 -> 2026-10-01 (duoc Claude cho phep va da ghi holdout-unlock-log.md).
"""

from __future__ import annotations

import argparse
import io
import math
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import scipy.stats as st

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Chay truc tiep `python scripts/...` phai import duoc `scripts.*` va `trading.*`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_momentum_portfolio import stock_symbols
from scripts.screen_pullback_trend import read_bars
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.stock_study import (
    bar_date,
    clean_bars,
    load_universe,
    validate_sealed_bars,
)
from trading.storage.db import Storage

__all__ = [
    "CONFIG_SYMBOLS",
    "DIRTY_SPLIT_THRESHOLD",
    "MIN_BARS",
    "WINDOW_A_END",
    "WINDOW_A_START",
    "WINDOW_B_END",
    "WINDOW_B_START",
    "align_series",
    "compute_atr20_series",
    "compute_correlation_matrix",
    "compute_eigenvalues_and_pr",
    "compute_joint_drawdown_stats",
    "compute_log_returns",
    "compute_market_benchmark",
    "compute_portfolio_loss_distribution",
    "detect_dirty_splits",
    "main",
    "read_bars_window_a",
    "read_bars_window_b",
]

# --- Tham so dang ky truoc (§1.1, §1.2, §8) -----------------------------------------

CONFIG_SYMBOLS = ["HPG", "IJC", "AAA"]
WINDOW_A_START = date(2017, 1, 1)
WINDOW_A_END = date(2022, 12, 31)
WINDOW_B_START = date(2023, 1, 1)
WINDOW_B_END = date(2026, 10, 1)
MIN_BARS = 250
DIRTY_SPLIT_THRESHOLD = 0.5


# --- Doc du lieu co cong niem phong -------------------------------------------------


def read_bars_window_a(storage: Storage, symbol: str) -> tuple[list[Bar], int]:
    """Doc du lieu cua so A (2017-01-01 -> 2022-12-31) qua read_bars (co niem phong)."""
    bars, n_drop = read_bars(storage, symbol)
    validate_sealed_bars(bars)
    kept = [b for b in bars if WINDOW_A_START <= bar_date(b) <= WINDOW_A_END]
    return kept, n_drop


def read_bars_window_b(storage: Storage, symbol: str) -> tuple[list[Bar], int]:
    """Doc du lieu cua so B (2023-01-01 -> 2026-10-01) - duoc Claude cho phep (§8)."""
    start_dt = datetime.combine(WINDOW_B_START, datetime.min.time(), tzinfo=TZ)
    end_dt = datetime.combine(WINDOW_B_END + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    raw_bars = storage.read_daily_bars(symbol, start_dt, end_dt)
    bars, n_drop = clean_bars(raw_bars)
    kept = [b for b in bars if WINDOW_B_START <= bar_date(b) <= WINDOW_B_END]
    return kept, n_drop


# --- Tinh toan loi suat & ghep theo ngay ---------------------------------------------


def compute_log_returns(closes: Sequence[float]) -> np.ndarray:
    """Tinh loi suat log theo phien: r_t = ln(close[t] / close[t-1])."""
    c = np.asarray(closes, dtype=float)
    if len(c) < 2:
        return np.empty(0, dtype=float)
    return np.log(c[1:] / c[:-1])


def align_series(
    bars_by_symbol: dict[str, list[Bar]],
    use_prices_instead_of_returns: bool = False,
    match_by_index_instead_of_date: bool = False,
) -> tuple[list[date], np.ndarray, list[str]]:
    """Ghep cac chuoi theo NGAY va tinh ma tran loi suat log (hoac gia).

    Tra ve:
    - common_dates: danh sach ngay chung (chieu dai N)
    - data_matrix: ma tran kich thuoc (N-1, K) chua log returns (hoac N, K neu use_prices)
    - symbols: danh sach ma theo thu tu cot
    """
    symbols = list(bars_by_symbol.keys())
    if not symbols:
        return [], np.empty((0, 0)), []

    # Map ngay -> bar cho tung ma
    date_maps: dict[str, dict[date, Bar]] = {}
    for s in symbols:
        date_maps[s] = {bar_date(b): b for b in bars_by_symbol[s] if b.close > 0}

    if match_by_index_instead_of_date:
        # Phep pha hoai (ii): ghep theo chi so thay vi theo ngay
        min_len = min(len(bars_by_symbol[s]) for s in symbols) if symbols else 0
        if min_len < 2:
            return [], np.empty((0, len(symbols))), symbols
        cols = []
        for s in symbols:
            closes = [bars_by_symbol[s][i].close for i in range(min_len)]
            if use_prices_instead_of_returns:
                cols.append(closes)
            else:
                cols.append(compute_log_returns(closes))
        mat = np.column_stack(cols)
        dummy_dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(min_len)]
        return dummy_dates, mat, symbols

    # Ghep dung theo ngay (date intersection)
    common_dates_set = set(date_maps[symbols[0]].keys())
    for s in symbols[1:]:
        common_dates_set &= set(date_maps[s].keys())

    common_dates = sorted(common_dates_set)
    if len(common_dates) < 2:
        return common_dates, np.empty((0, len(symbols))), symbols

    cols = []
    for s in symbols:
        closes = [date_maps[s][d].close for d in common_dates]
        if use_prices_instead_of_returns:
            cols.append(closes)
        else:
            cols.append(compute_log_returns(closes))

    data_matrix = np.column_stack(cols)
    return common_dates, data_matrix, symbols


# --- Tinh ma tran tuong quan, tri rieng, PR -----------------------------------------


def compute_correlation_matrix(
    returns_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Tinh ma tran tuong quan Pearson va Spearman, kem trung binh ngoai duong cheo."""
    k = returns_matrix.shape[1]
    if k == 0 or returns_matrix.shape[0] < 2:
        return np.eye(k), np.eye(k), 0.0, 0.0

    corr_p = np.corrcoef(returns_matrix, rowvar=False)
    if corr_p.ndim == 0:
        corr_p = np.array([[corr_p]])

    spearman_res = st.spearmanr(returns_matrix, axis=0)
    s_stat = (
        spearman_res.statistic
        if hasattr(spearman_res, "statistic")
        else spearman_res.correlation
    )
    if k == 2:
        val = float(s_stat)
        corr_s = np.array([[1.0, val], [val, 1.0]])
    elif np.ndim(s_stat) == 0:
        corr_s = np.array([[float(s_stat)]])
    else:
        corr_s = np.asarray(s_stat)

    if k > 1:
        mask = ~np.eye(k, dtype=bool)
        mean_p = float(np.mean(corr_p[mask]))
        mean_s = float(np.mean(corr_s[mask]))
    else:
        mean_p = 1.0
        mean_s = 1.0

    return corr_p, corr_s, mean_p, mean_s


def compute_eigenvalues_and_pr(
    corr_matrix: np.ndarray,
    use_wrong_pr_formula: bool = False,
) -> tuple[np.ndarray, float, float]:
    """Tinh ba tri rieng giam dan, so cuoc hieu dung (PR) va PR entropy.

    PR = (sum(lambda))^2 / sum(lambda^2) = 9 / sum(lambda^2) (voi ma tran 3x3).
    """
    eigvals = np.linalg.eigvalsh(corr_matrix)
    # Sap xep giam dan
    eigvals = np.sort(eigvals)[::-1]
    # Cat giu am rat nho do sai so dau phay dong
    eigvals = np.maximum(eigvals, 0.0)

    sum_l = float(np.sum(eigvals))
    sum_l2 = float(np.sum(eigvals**2))

    if use_wrong_pr_formula:
        # Phep pha hoai (iii): cong thuc sai sum(l^2) / sum(l)
        pr = sum_l2 / sum_l if sum_l > 0 else 0.0
    else:
        pr = (sum_l**2) / sum_l2 if sum_l2 > 0 else 0.0

    # Entropy cua tri rieng chuan hoa
    if sum_l > 0:
        p_k = eigvals / sum_l
        p_k_nonzero = p_k[p_k > 1e-12]
        entropy = -float(np.sum(p_k_nonzero * np.log(p_k_nonzero)))
        pr_entropy = float(np.exp(entropy))
    else:
        pr_entropy = 0.0

    return eigvals, float(pr), pr_entropy


# --- Tinh toan ATR20 va phan phoi lo ro theo RiskManager ----------------------------


def compute_atr20_series(bars: list[Bar]) -> dict[date, float]:
    """Tinh ATR20 cho tung phien d (trung binh true range 20 phien ket thuc tai d)."""
    n = len(bars)
    if n < 21:
        return {}
    trs: list[float] = [0.0] * n
    for i in range(1, n):
        h, l = bars[i].high, bars[i].low
        prev_c = bars[i - 1].close
        trs[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))

    atr_by_date: dict[date, float] = {}
    for i in range(20, n):
        atr20 = sum(trs[i - 19 : i + 1]) / 20.0
        atr_by_date[bar_date(bars[i])] = atr20
    return atr_by_date


def compute_portfolio_loss_distribution(
    bars_by_symbol: dict[str, list[Bar]],
    rm: RiskManager | None = None,
) -> dict[str, Any]:
    """Mo ta rui ro ro theo cong thuc dinh co ATR cua RiskManager (§8).

    - w_i = min(risk_pct / (atr_multiplier * ATR20_i[d-1] / close_i[d-1]), max_order_value_pct)
    - Lo ro phien d = -sum(w_i * (close_i[d] / close_i[d-1] - 1))
    """
    if rm is None:
        rm = RiskManager(capital=100_000_000.0)

    symbols = list(bars_by_symbol.keys())
    atr_maps = {s: compute_atr20_series(bars_by_symbol[s]) for s in symbols}
    date_bar_maps = {s: {bar_date(b): b for b in bars_by_symbol[s] if b.close > 0} for s in symbols}

    common_dates_set = set(date_bar_maps[symbols[0]].keys())
    for s in symbols[1:]:
        common_dates_set &= set(date_bar_maps[s].keys())
    common_dates = sorted(common_dates_set)

    losses: list[float] = []
    loss_dates: list[date] = []
    weights_record: dict[str, list[float]] = defaultdict(list)

    for i in range(1, len(common_dates)):
        d = common_dates[i]
        prev_d = common_dates[i - 1]

        # Kiem tra ca 3 ma deu co ATR20 tai prev_d
        has_all_atr = all(prev_d in atr_maps[s] for s in symbols)
        if not has_all_atr:
            continue

        loss_d = 0.0
        for s in symbols:
            prev_close = date_bar_maps[s][prev_d].close
            curr_close = date_bar_maps[s][d].close
            atr_val = atr_maps[s][prev_d]

            atr_pct = (atr_val / prev_close) if prev_close > 0 else 0.0
            if atr_pct > 0:
                raw_w = rm.risk_pct / (rm.atr_multiplier * atr_pct)
                w = min(raw_w, rm.max_order_value_pct)
            else:
                w = rm.max_order_value_pct

            weights_record[s].append(w)
            ret_s = (curr_close / prev_close) - 1.0
            loss_d -= w * ret_s

        losses.append(loss_d)
        loss_dates.append(d)

    if not losses:
        return {
            "max_loss": 0.0,
            "p99_loss": 0.0,
            "days_over_threshold": 0,
            "threshold": rm.max_daily_loss_pct,
            "total_days": 0,
            "mean_weights": {s: 0.0 for s in symbols},
            "losses": [],
            "loss_dates": [],
        }

    arr_loss = np.array(losses)
    max_loss = float(np.max(arr_loss))
    p99_loss = float(np.percentile(arr_loss, 99))
    days_over = int(np.sum(arr_loss > rm.max_daily_loss_pct))
    mean_w = {s: float(np.mean(weights_record[s])) for s in symbols}

    return {
        "max_loss": max_loss,
        "p99_loss": p99_loss,
        "days_over_threshold": days_over,
        "threshold": rm.max_daily_loss_pct,
        "total_days": len(losses),
        "mean_weights": mean_w,
        "losses": losses,
        "loss_dates": loss_dates,
    }


# --- Kiem tra phien ca 3 cung giam & 10 phien te nhat thi truong ----------------------


def compute_joint_drawdown_stats(
    returns_matrix: np.ndarray,
    mkt_returns: np.ndarray | None = None,
) -> dict[str, Any]:
    """Dem so phien ca 3 ma cung giam, va trong 10 phien te nhat cua thi truong."""
    n_days = returns_matrix.shape[0]
    if n_days == 0:
        return {
            "all_down_days": 0,
            "all_down_pct": 0.0,
            "total_days": 0,
            "worst_10_all_down_count": 0,
        }

    # Ca 3 ma cung giam: moi cot deu < 0
    all_down_mask = np.all(returns_matrix < 0.0, axis=1)
    all_down_count = int(np.sum(all_down_mask))
    all_down_pct = float(all_down_count / n_days * 100.0)

    worst_10_count = 0
    if mkt_returns is not None and len(mkt_returns) == n_days:
        worst_indices = np.argsort(mkt_returns)[: min(10, n_days)]
        worst_10_count = int(np.sum(all_down_mask[worst_indices]))

    return {
        "all_down_days": all_down_count,
        "all_down_pct": all_down_pct,
        "total_days": n_days,
        "worst_10_all_down_count": worst_10_count,
    }


# --- Phat hien chia tach chua chinh -------------------------------------------------


def detect_dirty_splits(
    bars_by_symbol: dict[str, list[Bar]],
    threshold: float = DIRTY_SPLIT_THRESHOLD,
) -> dict[str, list[tuple[date, float]]]:
    """Dem cac phien co |log ret| > threshold (nghi chia tach chua chinh)."""
    dirty: dict[str, list[tuple[date, float]]] = {}
    for s, bars in bars_by_symbol.items():
        dirty_list: list[tuple[date, float]] = []
        for i in range(1, len(bars)):
            p0 = bars[i - 1].close
            p1 = bars[i].close
            if p0 > 0 and p1 > 0:
                lret = math.log(p1 / p0)
                if abs(lret) > threshold:
                    dirty_list.append((bar_date(bars[i]), lret))
        dirty[s] = dirty_list
    return dirty


# --- Tinh moc so sanh tuong quan toan thi truong -----------------------------------


def compute_market_benchmark(
    storage: Storage,
    window_start: date,
    window_end: date,
    is_window_b: bool = False,
    min_bars: int = MIN_BARS,
    sample_limit: int = 200,
) -> float:
    """Tinh tuong quan Pearson trung binh cap giua cac ma co phieu tren thi truong."""
    universe, _, _, _ = load_universe(storage, "exclusions.txt")
    symbols, _ = stock_symbols(universe)

    date_returns_by_sym: dict[str, dict[date, float]] = {}

    for sym in symbols:
        if is_window_b:
            bars, _ = read_bars_window_b(storage, sym)
        else:
            try:
                bars, _ = read_bars_window_a(storage, sym)
            except (ValueError, KeyError, RuntimeError):
                bars = []

        if len(bars) < min_bars:
            continue

        r_map: dict[date, float] = {}
        for i in range(1, len(bars)):
            p0 = bars[i - 1].close
            p1 = bars[i].close
            if p0 > 0 and p1 > 0:
                r_map[bar_date(bars[i])] = math.log(p1 / p0)
        if len(r_map) >= min_bars:
            date_returns_by_sym[sym] = r_map

    valid_syms = sorted(date_returns_by_sym.keys())
    if len(valid_syms) < 2:
        return 0.0

    # Neu so ma qua lon, lay mau dai dien ngau nhien co dinh seed de tinh nhanh
    if len(valid_syms) > sample_limit:
        rng = np.random.default_rng(42)
        valid_syms = list(rng.choice(valid_syms, size=sample_limit, replace=False))

    # Tim cac ngay chung cua cac ma trong mau
    all_dates = sorted(set.intersection(*(set(date_returns_by_sym[s].keys()) for s in valid_syms[:20])))
    if len(all_dates) < 50:
        # Neu giao cua 20 ma dau qua it, tim ngay pho bien xuat hien >= 80% ma
        date_counts: dict[date, int] = defaultdict(int)
        for s in valid_syms:
            for d in date_returns_by_sym[s]:
                date_counts[d] += 1
        all_dates = sorted(d for d, c in date_counts.items() if c >= len(valid_syms) * 0.70)

    # Xay dung ma tran returns
    rows = []
    for d in all_dates:
        row = [date_returns_by_sym[s].get(d, 0.0) for s in valid_syms]
        rows.append(row)

    if len(rows) < 30:
        return 0.0

    mat = np.array(rows)
    # Tinh correlation matrix
    corr = np.corrcoef(mat, rowvar=False)
    k = corr.shape[0]
    mask = ~np.eye(k, dtype=bool)
    valid_corrs = corr[mask]
    valid_corrs = valid_corrs[np.isfinite(valid_corrs)]
    return float(np.mean(valid_corrs)) if len(valid_corrs) > 0 else 0.0


# --- CLI Main Runner ---------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ma tran tuong quan cua ro ma dang chay [HPG, IJC, AAA] (Brief dot 180)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=CONFIG_SYMBOLS,
        help="Danh sach ma can do (mac dinh: HPG IJC AAA)",
    )
    args = parser.parse_args()

    symbols = [s.upper().strip() for s in args.symbols]
    storage = Storage(resolve_dsn())

    print("=" * 84)
    print("  BRIEF ĐỢT 180 — MA TRẬN TƯƠNG QUAN CỦA RỔ MÃ ĐANG CHẠY")
    print(f"  Rổ khảo sát: {symbols}")
    print("=" * 84)

    # ========================== CỬA SỔ A ==========================
    print("\n" + "=" * 84)
    print(f"  [1/2] CỬA SỔ A: {WINDOW_A_START} -> {WINDOW_A_END} (In-Sample, có niêm phong)")
    print("=" * 84)

    bars_a: dict[str, list[Bar]] = {}
    for s in symbols:
        b, _ = read_bars_window_a(storage, s)
        bars_a[s] = b
        print(f"  {s}: nạp {len(b)} nến hợp lệ trong cửa sổ A.")

    dates_a, mat_a, _ = align_series(bars_a)
    print(f"\n  Số phiên giao dịch chung của cả 3 mã: {len(dates_a)} ngày ({mat_a.shape[0]} lợi suất log).")

    if mat_a.shape[0] < MIN_BARS:
        print(f"  !! DỪNG: Số phiên chung {mat_a.shape[0]} < {MIN_BARS} tối thiểu.")
        return

    _run_analysis_window("CỬA SỔ A (2017–2022)", symbols, bars_a, dates_a, mat_a, storage, WINDOW_A_START, WINDOW_A_END, is_b=False)

    # ========================== CỬA SỔ B ==========================
    print("\n" + "=" * 84)
    print(f"  [2/2] CỬA SỔ B: {WINDOW_B_START} -> {WINDOW_B_END} (Holdout gần đây, đã mở niêm phong)")
    print("=" * 84)

    bars_b: dict[str, list[Bar]] = {}
    for s in symbols:
        b, _ = read_bars_window_b(storage, s)
        bars_b[s] = b
        print(f"  {s}: nạp {len(b)} nến hợp lệ trong cửa sổ B.")

    dates_b, mat_b, _ = align_series(bars_b)
    print(f"\n  Số phiên giao dịch chung của cả 3 mã: {len(dates_b)} ngày ({mat_b.shape[0]} lợi suất log).")

    if mat_b.shape[0] < MIN_BARS:
        print(f"  !! CẢNH BÁO: Số phiên chung {mat_b.shape[0]} < {MIN_BARS} tối thiểu ở cửa sổ B.")

    _run_analysis_window("CỬA SỔ B (2023–2026)", symbols, bars_b, dates_b, mat_b, storage, WINDOW_B_START, WINDOW_B_END, is_b=True)

    print("\n" + "=" * 84)
    print("  KẾT THÚC BÁO CÁO MÔ TẢ RỦI RO ĐỢT 180:")
    print("  * Phép đo này KHÔNG thay đổi rổ mã, KHÔNG thay đổi định cỡ rủi ro, KHÔNG mở đường tới vốn thật.")
    print("  * Mọi hành động điều chỉnh (nếu có) phải thuộc brief riêng.")
    print("=" * 84)


def _run_analysis_window(
    title: str,
    symbols: list[str],
    bars_by_sym: dict[str, list[Bar]],
    dates: list[date],
    mat: np.ndarray,
    storage: Storage,
    start_d: date,
    end_d: date,
    is_b: bool,
) -> None:
    # 1. Pearson & Spearman
    corr_p, _corr_s, mean_p, mean_s = compute_correlation_matrix(mat)

    # 2. Eigenvalues & PR
    eigvals, pr, pr_ent = compute_eigenvalues_and_pr(corr_p)

    # 3. Market benchmark
    mkt_rho = compute_market_benchmark(storage, start_d, end_d, is_window_b=is_b)

    # 4. Joint drawdown
    # Sua cua Claude khi audit: day la binh quan 3 ma CUA RO, khong phai thi truong mua deu.
    # Nhan in ra da doi cho dung; so voi thi truong that xem muc audit trong tai lieu nghien cuu.
    mkt_ew_returns = np.mean(mat, axis=1)
    dd_stats = compute_joint_drawdown_stats(mat, mkt_ew_returns)

    # 5. Portfolio ATR loss distribution
    loss_stats = compute_portfolio_loss_distribution(bars_by_sym)

    # 6. Dirty splits check
    dirty = detect_dirty_splits(bars_by_sym)
    total_dirty = sum(len(v) for v in dirty.values())

    print(f"\n--- BÁO CÁO CHI TIẾT {title} ---")
    print("1. Tương quan trung bình đôi:")
    print(f"   - Pearson  ρ̄  : {mean_p:+.4f}")
    print(f"   - Spearman ρ̄_s: {mean_s:+.4f}")

    print("\n2. Ma trận tương quan Pearson 3x3:")
    print(f"         {'  '.join(f'{s:>7}' for s in symbols)}")
    for i, s in enumerate(symbols):
        row_str = "  ".join(f"{corr_p[i, j]:+7.4f}" for j in range(len(symbols)))
        print(f"   {s:<4}: {row_str}")

    print("\n   Ba trị riêng (λ₁ ≥ λ₂ ≥ λ₃):")
    print(f"   λ = [{eigvals[0]:.4f}, {eigvals[1]:.4f}, {eigvals[2]:.4f}] (Tổng = {np.sum(eigvals):.4f})")

    print("\n3. Số cược hiệu dụng (Participation Ratio):")
    print(f"   - PR (đúng công thức) : {pr:.4f} / 3.0 cược")
    print(f"   - PR entropy          : {pr_ent:.4f} / 3.0 cược")

    print("\n4. Mốc so sánh toàn thị trường cổ phiếu:")
    print(f"   - ρ̄_mkt (toàn thị trường): {mkt_rho:+.4f}")
    print(f"   - Chênh lệch (ρ̄ - ρ̄_mkt)  : {mean_p - mkt_rho:+.4f}")

    print("\n5. Phân tích cùng chiều giảm:")
    print(f"   - Số phiên cả ba cùng giảm             : {dd_stats['all_down_days']}/{dd_stats['total_days']} phiên ({dd_stats['all_down_pct']:.1f}%)")
    print(f"   - Trong 10 phiên tệ nhất của CHÍNH RỔ (bình quân 3 mã): cả ba cùng giảm {dd_stats['worst_10_all_down_count']}/10 phiên")

    print("\n6. Phân phối lỗ rổ theo định cỡ ATR (mô tả, không phí):")
    print("   - Tỷ trọng bình quân mỗi mã            : " + ", ".join(f"{s}: {loss_stats['mean_weights'][s]*100:.1f}%" for s in symbols))
    print(f"   - Lỗ rổ lớn nhất trong 1 phiên (Max loss): {loss_stats['max_loss']*100:.2f}%")
    print(f"   - Phân vị 99% lỗ rổ một phiên (P99 loss) : {loss_stats['p99_loss']*100:.2f}%")
    print(f"   - Số phiên lỗ rổ vượt trần ngày (> {loss_stats['threshold']*100:.0f}%): {loss_stats['days_over_threshold']}/{loss_stats['total_days']} phiên")

    print("\n7. Kiểm tra dữ liệu nến bẩn (|log ret| > 0.5):")
    if total_dirty == 0:
        print("   - Không có phiên nào nghi chia tách chưa chỉnh (|log ret| > 0.5).")
    else:
        print(f"   - Có {total_dirty} phiên nghi chia tách chưa chỉnh:")
        for s, lst in dirty.items():
            for d, r in lst:
                print(f"     + {s} ngày {d}: log ret = {r:+.2f}")
        # Tinh bien the ben loai bo cac ngay nay
        dirty_dates = {d for lst in dirty.values() for d, _ in lst}
        clean_mask = [d not in dirty_dates for d in dates[1:]]
        clean_mat = mat[clean_mask]
        _, _, clean_mean_p, clean_mean_s = compute_correlation_matrix(clean_mat)
        _clean_eigvals, clean_pr, _ = compute_eigenvalues_and_pr(compute_correlation_matrix(clean_mat)[0])
        print("   - Bản tính lại đã loại các phiên đó (Biến thể bền):")
        print(f"     + Pearson ρ̄  : {clean_mean_p:+.4f}")
        print(f"     + Spearman ρ̄ : {clean_mean_s:+.4f}")
        print(f"     + PR         : {clean_pr:.4f}")

    # Đánh giá theo ngưỡng diễn giải chốt trước (§1.4)
    print("\n* ĐÁNH GIÁ THEO NGƯỠNG ĐĂNG KÝ TRƯỚC (§1.4):")
    if mean_p < 0.50:
        muc_tuong_quan = "KHÔNG TẬP TRUNG ĐÁNG KỂ (ρ̄ < 0.50)"
    elif mean_p < 0.70:
        muc_tuong_quan = "VỪA (0.50 ≤ ρ̄ < 0.70)"
    else:
        muc_tuong_quan = "CAO (ρ̄ ≥ 0.70)"

    if pr >= 2.5:
        muc_pr = "GẦN BA CƯỢC ĐỘC LẬP (PR ≥ 2.5)"
    elif pr >= 2.0:
        muc_pr = "VỪA (2.0 ≤ PR < 2.5)"
    else:
        muc_pr = "BA VỊ THẾ CHỈ CÒN ≤ 2 CƯỢC (PR < 2.0)"

    print(f"  - Mức tương quan : {muc_tuong_quan}")
    print(f"  - Mức phân tán PR: {muc_pr}")

    is_dang_lo = (mean_p >= 0.70 and pr < 2.0) or ((mean_p - mkt_rho >= 0.10) and pr < 2.0)
    if is_dang_lo:
        print("  >>> KẾT LUẬN: RỔ TẬP TRUNG ĐÁNG LO! <<<")
    else:
        print("  >>> KẾT LUẬN: CHƯA KẾT LUẬN ĐƯỢC (không hội đủ điều kiện rổ tập trung đáng lo). <<<")


if __name__ == "__main__":
    main()
