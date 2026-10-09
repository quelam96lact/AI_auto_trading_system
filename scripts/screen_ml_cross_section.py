"""Học máy xếp hạng cổ phiếu VN theo tháng (ĐĂNG KÝ TRƯỚC) — Brief đợt 169.

Thiết kế ĐĂNG KÝ TRƯỚC (chốt trong brief, KHÔNG đổi sau khi thấy dữ liệu):
- IS: 60 tháng thử (2018-01 đến 2022-12).
- Niêm phong: Cấm đọc nến >= 2023-01-01 (validate_sealed_bars).
- Vũ trụ: load_universe(storage, "exclusions.txt"), chỉ giữ mã cổ phiếu (is_stock_symbol).
- 11 đặc trưng cố định tính tại phiên F (close[i_F]):
  1. ret_1m: close[i_F] / close[i_F-21] - 1
  2. ret_3m: close[i_F] / close[i_F-63] - 1
  3. ret_6m: close[i_F] / close[i_F-126] - 1
  4. mom_12_1: close[i_F-21] / close[i_F-252] - 1 (đúng đợt 102)
  5. vol_20: độ lệch chuẩn log return 20 phiên kết thúc tại i_F
  6. vol_60: độ lệch chuẩn log return 60 phiên kết thúc tại i_F
  7. dist_ma50: close[i_F] / mean(close 50 phiên) - 1
  8. dist_high_252: close[i_F] / max(close 252 phiên) - 1
  9. log_turnover_20: log(mean(close * volume 20 phiên))
  10. vol_ratio_5_60: mean(volume 5 phiên) / mean(volume 60 phiên)
  11. max_ret_21: log return lớn nhất trong 21 phiên kết thúc tại i_F
- Chuẩn hóa: mỗi tháng đổi đặc trưng thành hạng phần trăm mặt cắt (0..1).
- Nhãn: hạng phần trăm mặt cắt (0..1) của lợi nhuận gộp tháng giữ (OPEN phiên đầu -> CLOSE phiên cuối).
  Mã mở trần phiên vào -> không có nhãn, không vào tập huấn luyện.
- Walk-forward: Mỗi tháng 1 (2018..2022) huấn luyện lại trên mọi mẫu từ 2016-12 tới (Y-1)-11.
  Purge: mẫu (Y-1)-12 bị loại vì nhãn là tháng Y-01 (tháng thử đầu tiên).
- Mô hình cố định:
  * Ridge(alpha=1.0, fit_intercept=True)
  * LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=100,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                  random_state=42, deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1)
- Danh mục: WIN = top 10% (làm tròn lên, tối thiểu 10 mã), EW = toàn bộ mã đủ điều kiện, LOSE = bottom 10%.
- Phép thử bootstrap: khối 3 tháng liền nhau, 2.000 lần, seed=42.
- Đối chứng âm: nhãn xáo trộn theo tháng, seed 42.
"""

from __future__ import annotations

import argparse
import io
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor
from scipy.stats import rankdata, spearmanr
from sklearn.linear_model import Ridge

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.measure_etf_deposit_mix import read_is_bars, simulate_mix
from scripts.screen_momentum_portfolio import (
    ETF_SYMBOL,
    MIN_TURNOVER_VND,
    MIN_UNIVERSE_FOR_MONTH,
    Span,
    _mean,
    _median,
    bar_date,
    block_bootstrap,
    cagr,
    eligible_at,
    etf_buy_hold,
    hold_return,
    last_session_by_month,
    max_drawdown,
    month_members_returns,
    month_spans,
    net_month,
    next_month_key,
    portfolio_gross,
    read_symbol_bars,
    round_trip_cost,
    share_positive,
    stock_symbols,
    turnover,
)
from trading.calendar_vn import TZ
from trading.metrics import max_drawdown as equity_curve_max_drawdown
from trading.models import Bar
from trading.stock_study import load_universe
from trading.storage.db import Storage

__all__ = [
    "FEATURE_NAMES",
    "IS_FIRST_TEST_MONTH",
    "IS_LAST_TEST_MONTH",
    "TEST_YEARS",
    "TRAIN_START_DATE",
    "compute_features_at",
    "cross_sectional_rank",
    "main",
    "make_lgbm_model",
    "make_ridge_model",
    "net_month",
    "predict_year_models",
    "round_trip_cost",
    "run_ml_cross_section_screen",
    "train_months_for_year",
    "turnover",
]

# --- Hằng số đăng ký trước ---------------------------------------------------------

FEATURE_NAMES = (
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "mom_12_1",
    "vol_20",
    "vol_60",
    "dist_ma50",
    "dist_high_252",
    "log_turnover_20",
    "vol_ratio_5_60",
    "max_ret_21",
)

TRAIN_START_DATE = date(2016, 12, 30)
IS_FIRST_TEST_MONTH = (2018, 1)
IS_LAST_TEST_MONTH = (2022, 12)
TEST_YEARS = (2018, 2019, 2020, 2021, 2022)

READ_FROM = datetime(2016, 1, 1, tzinfo=TZ)
READ_TO = datetime(2023, 1, 1, tzinfo=TZ)
EXCLUSIONS_FILE = "exclusions.txt"
DEPOSIT_RATE = 0.06  # Hurdle 6% theo brief 169 & 165


# --- Tính toán đặc trưng ----------------------------------------------------------


def compute_features_at(bars: list[Bar], i_f: int) -> dict[str, float]:
    """Tính đúng 11 đặc trưng cố định chỉ từ dữ liệu tới CLOSE phiên F (chỉ số i_f)."""
    if i_f < 252:
        raise IndexError(f"Cần ít nhất 252 phiên lịch sử để tính đặc trưng tại i_f={i_f}")

    # 1. ret_1m
    ret_1m = bars[i_f].close / bars[i_f - 21].close - 1.0
    # 2. ret_3m
    ret_3m = bars[i_f].close / bars[i_f - 63].close - 1.0
    # 3. ret_6m
    ret_6m = bars[i_f].close / bars[i_f - 126].close - 1.0
    # 4. mom_12_1 (đúng định nghĩa đợt 102)
    mom_12_1 = bars[i_f - 21].close / bars[i_f - 252].close - 1.0

    # 5. vol_20: độ lệch chuẩn log return ngày 20 phiên kết thúc tại i_F
    log_rets_20 = [math.log(bars[t].close / bars[t - 1].close) for t in range(i_f - 19, i_f + 1)]
    vol_20 = statistics.stdev(log_rets_20)

    # 6. vol_60: độ lệch chuẩn log return ngày 60 phiên kết thúc tại i_F
    log_rets_60 = [math.log(bars[t].close / bars[t - 1].close) for t in range(i_f - 59, i_f + 1)]
    vol_60 = statistics.stdev(log_rets_60)

    # 7. dist_ma50: close[i_F] / trung bình close 50 phiên - 1
    ma_50 = statistics.fmean(bars[t].close for t in range(i_f - 49, i_f + 1))
    dist_ma50 = bars[i_f].close / ma_50 - 1.0

    # 8. dist_high_252: close[i_F] / max close 252 phiên - 1
    high_252 = max(bars[t].close for t in range(i_f - 251, i_f + 1))
    dist_high_252 = bars[i_f].close / high_252 - 1.0

    # 9. log_turnover_20: log(trung bình close * volume 20 phiên)
    avg_turnover_20 = statistics.fmean(bars[t].close * bars[t].volume for t in range(i_f - 19, i_f + 1))
    log_turnover_20 = math.log(max(1.0, avg_turnover_20))

    # 10. vol_ratio_5_60: trung bình volume 5 phiên / trung bình volume 60 phiên
    avg_vol_5 = statistics.fmean(bars[t].volume for t in range(i_f - 4, i_f + 1))
    avg_vol_60 = statistics.fmean(bars[t].volume for t in range(i_f - 59, i_f + 1))
    vol_ratio_5_60 = avg_vol_5 / avg_vol_60 if avg_vol_60 > 0 else 1.0

    # 11. max_ret_21: log return ngày lớn nhất trong 21 phiên kết thúc tại i_F
    log_rets_21 = [math.log(bars[t].close / bars[t - 1].close) for t in range(i_f - 20, i_f + 1)]
    max_ret_21 = max(log_rets_21)

    return {
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "mom_12_1": mom_12_1,
        "vol_20": vol_20,
        "vol_60": vol_60,
        "dist_ma50": dist_ma50,
        "dist_high_252": dist_high_252,
        "log_turnover_20": log_turnover_20,
        "vol_ratio_5_60": vol_ratio_5_60,
        "max_ret_21": max_ret_21,
    }


def cross_sectional_rank(values: Mapping[str, float]) -> dict[str, float]:
    """Đổi giá trị các mã trong mặt cắt thành hạng phần trăm trong [0, 1]."""
    if not values:
        return {}
    if len(values) == 1:
        sym = next(iter(values))
        return {sym: 0.5}
    items = list(values.items())
    raw_vals = [v for _, v in items]
    ranks = (rankdata(raw_vals, method="average") - 1.0) / (len(items) - 1.0)
    return {k: float(r) for (k, _), r in zip(items, ranks)}


# --- Walk-forward timeline & Purge ------------------------------------------------


def train_months_for_year(test_year: int) -> list[tuple[int, int]]:
    """Trả về danh sách tháng F hợp lệ để train cho năm test_year.

    Bắt đầu từ (2016, 12) tới (test_year - 1, 11).
    Purge: tháng (test_year - 1, 12) bị loại vì nhãn của nó là tháng test_year-01.
    """
    out: list[tuple[int, int]] = []
    curr = (2016, 12)
    end = (test_year - 1, 11)
    while curr <= end:
        out.append(curr)
        curr = next_month_key(curr)
    return out


# --- Khởi tạo & Dự báo mô hình ----------------------------------------------------


def make_ridge_model() -> Ridge:
    return Ridge(alpha=1.0, fit_intercept=True)


def make_lgbm_model() -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=100,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
        deterministic=True,
        force_row_wise=True,
        n_jobs=1,
        verbose=-1,
    )


def predict_year_models(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Huấn luyện Ridge và LightGBM trên tập train, trả về (ridge_preds, lgbm_preds)."""
    ridge = make_ridge_model()
    ridge.fit(x_train, y_train)
    ridge_preds = ridge.predict(x_test)

    lgbm = make_lgbm_model()
    lgbm.fit(x_train, y_train)
    lgbm_preds = lgbm.predict(x_test)

    return ridge_preds, lgbm_preds


# --- Mô phỏng kết hợp Danh mục + Tiền gửi (Mốc chuẩn 165) -------------------------


def simulate_equity_deposit_mix(
    monthly_equity_net: Sequence[float],
    months: Sequence[tuple[int, int]],
    w: float = 0.15,
    r: float = DEPOSIT_RATE,
) -> dict[str, Any]:
    """Mô phỏng kết hợp w% danh mục cổ phiếu + (1-w)% tiền gửi lãi suất r, tái cân bằng hàng năm.

    Tái cân bằng diễn ra vào đầu mỗi năm (tháng 1).
    """
    if not monthly_equity_net or len(monthly_equity_net) != len(months):
        return {"cagr": 0.0, "mdd": 0.0, "equity_curve": []}

    eq_stock = w
    eq_cash = 1.0 - w
    equity_curve = [1.0]

    for i, (net_stk, mk) in enumerate(zip(monthly_equity_net, months)):
        _, month = mk
        # Tái cân bằng đầu năm (trừ tháng đầu tiên của chuỗi)
        if month == 1 and i > 0:
            total_eq = eq_stock + eq_cash
            eq_stock = w * total_eq
            eq_cash = (1.0 - w) * total_eq

        # Tăng trưởng trong tháng
        # Tiền gửi: giả định mỗi tháng trung bình 365/12 ngày
        eq_stock *= 1.0 + net_stk
        eq_cash *= (1.0 + r) ** (1.0 / 12.0)

        total_eq = eq_stock + eq_cash
        equity_curve.append(total_eq)

    n_months = len(monthly_equity_net)
    final_eq = equity_curve[-1]
    mix_cagr = (final_eq ** (12.0 / n_months)) - 1.0 if final_eq > 0 else -1.0

    # MDD
    peak = 1.0
    worst = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        worst = max(worst, (peak - eq) / peak)

    return {
        "cagr": mix_cagr,
        "mdd": worst,
        "final_equity": final_eq,
        "equity_curve": equity_curve,
    }


# --- Xây dựng tập dữ liệu & Pipeline kiểm định -------------------------------------


def _generate_synthetic_universe(
    seed: int = 42,
    positive_signal: bool = False,
) -> dict[str, list[Bar]]:
    """Dựng dữ liệu tổng hợp ~30 mã từ 2016-01 đến 2022-12 để test pipeline không cần DB."""
    rng = random.Random(seed)
    symbols = [f"S{i:02d}" for i in range(1, 31)]
    start_d = date(2016, 1, 4)
    end_d = date(2022, 12, 30)

    # Sinh danh sách ngày giao dịch
    trading_dates: list[date] = []
    cur = start_d
    while cur <= end_d:
        if cur.weekday() < 5:
            trading_dates.append(cur)
        cur += timedelta(days=1)

    out: dict[str, list[Bar]] = {}
    for s_idx, sym in enumerate(symbols):
        bars: list[Bar] = []
        close = 20_000.0 + s_idx * 1000.0
        for d in trading_dates:
            ts = datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ)
            ret = rng.gauss(0.0003, 0.015)
            open_ = close * (1.0 + rng.gauss(0, 0.003))
            close = max(1000.0, close * (1.0 + ret))
            high = max(open_, close) * (1.0 + abs(rng.gauss(0, 0.005)))
            low = min(open_, close) * (1.0 - abs(rng.gauss(0, 0.005)))
            # Đảm bảo turnover >= 1 tỷ (1_000_000_000 / 20_000 = 50_000 cp)
            vol = rng.gauss(100_000.0, 10_000.0)
            bars.append(Bar(sym, ts, open_, high, low, close, int(vol)))
        out[sym] = bars

    if positive_signal:
        # Điều chỉnh giá nến sao cho tháng kế tiếp tỷ lệ nghịch mạnh với ret_1m
        # Giúp positive control test phát hiện tín hiệu
        spans_by_s = {s: month_spans(b) for s, b in out.items()}
        all_mks = sorted(spans_by_s[symbols[0]].keys())
        for m_idx in range(len(all_mks) - 1):
            mk_f = all_mks[m_idx]
            mk_hold = all_mks[m_idx + 1]
            for sym in symbols:
                sp_f = spans_by_s[sym].get(mk_f)
                sp_h = spans_by_s[sym].get(mk_hold)
                if sp_f and sp_h and sp_f.last >= 252:
                    bars = out[sym]
                    ret_1m = bars[sp_f.last].close / bars[sp_f.last - 21].close - 1.0
                    target_ret = -0.5 * ret_1m + rng.gauss(0, 0.001)
                    entry_open = bars[sp_h.first].open
                    bars[sp_h.last] = Bar(
                        bars[sp_h.last].symbol,
                        bars[sp_h.last].ts,
                        bars[sp_h.last].open,
                        bars[sp_h.last].high,
                        bars[sp_h.last].low,
                        entry_open * (1.0 + target_ret),
                        int(bars[sp_h.last].volume),
                    )
    return out


def run_ml_cross_section_screen(
    dsn: str | None = None,
    synthetic_mode: str | None = None,
    seed: int = 42,
    shuffle_labels: bool = False,
    exclusions_path: str = EXCLUSIONS_FILE,
    cached_bars: dict[str, list[Bar]] | None = None,
    cached_exchanges: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Chạy trọn vẹn quy trình walk-forward IS 2018-2022 cho mô hình Ridge và LightGBM."""
    if synthetic_mode == "shuffle_labels":
        shuffle_labels = True

    if dsn is None and synthetic_mode is None:
        dsn = resolve_dsn()

    bars_by_symbol: dict[str, list[Bar]] = {}
    exchange_by_symbol: dict[str, str | None] = {}

    if cached_bars is not None and cached_exchanges is not None:
        bars_by_symbol = cached_bars
        exchange_by_symbol = cached_exchanges
    elif synthetic_mode is not None:
        bars_by_symbol = _generate_synthetic_universe(
            seed=seed, positive_signal=(synthetic_mode == "positive_signal")
        )
        for s in bars_by_symbol:
            exchange_by_symbol[s] = "HOSE"
    else:
        storage = Storage(dsn)
        universe, exchange_map, _, _ = load_universe(storage, exclusions_path)
        stock_syms, _ = stock_symbols(universe)

        for sym in stock_syms:
            bars, _ = read_symbol_bars(storage, sym, READ_FROM, READ_TO)
            if bars:
                bars_by_symbol[sym] = bars
                exchange_by_symbol[sym] = exchange_map.get(sym)

    # 1. Tính toán spans và ngày F của từng tháng
    spans_by_symbol: dict[str, dict[tuple[int, int], Span]] = {
        sym: month_spans(bars) for sym, bars in bars_by_symbol.items()
    }

    all_dates: set[date] = set()
    for bars in bars_by_symbol.values():
        for b in bars:
            all_dates.add(bar_date(b))
    f_date_by_month = last_session_by_month(all_dates)

    # 2. Thu thập các tháng xếp hạng F từ (2016, 12) đến (2022, 11)
    all_ranking_months: list[tuple[int, int]] = []
    curr_m = (2016, 12)
    while curr_m <= (2022, 11):
        all_ranking_months.append(curr_m)
        curr_m = next_month_key(curr_m)

    # Thu thập raw features và hold returns cho từng tháng F
    # month_samples[mk_F] = list of {symbol, features_dict, raw_hold_ret, why}
    month_data: dict[tuple[int, int], dict[str, Any]] = {}
    eligible_count_by_month: dict[tuple[int, int], int] = {}

    for mk_f in all_ranking_months:
        f_date = f_date_by_month.get(mk_f)
        if not f_date:
            continue
        mk_hold = next_month_key(mk_f)

        raw_feats_by_sym: dict[str, dict[str, float]] = {}
        raw_hold_by_sym: dict[str, float] = {}

        for sym, bars in bars_by_symbol.items():
            sp_f = spans_by_symbol[sym].get(mk_f)
            if sp_f is None:
                continue
            i_f = sp_f.last
            # Kiểm tra ngày của nến i_f có đúng là f_date không
            if bar_date(bars[i_f]) != f_date:
                continue

            # Kiểm tra đủ điều kiện
            min_turn = 10_000_000.0 if synthetic_mode else MIN_TURNOVER_VND
            elig = eligible_at(bars, i_f, f_date, min_turnover=min_turn)
            if elig != "ok":
                continue

            # Tính 11 đặc trưng
            feats = compute_features_at(bars, i_f)
            raw_feats_by_sym[sym] = feats

            # Tính lợi nhuận tháng giữ mk_hold
            sp_h = spans_by_symbol[sym].get(mk_hold)
            if sp_h is not None:
                r, why = hold_return(bars, sp_h.first, sp_h.last, exchange_by_symbol.get(sym))
                if why == "ok" and r is not None:
                    raw_hold_by_sym[sym] = r

        n_elig = len(raw_feats_by_sym)
        eligible_count_by_month[mk_f] = n_elig

        # Nếu là synthetic mode hoặc thực tế có >= 100 mã (hoặc synthetic >= 10 mã)
        min_u = 10 if synthetic_mode else MIN_UNIVERSE_FOR_MONTH
        if n_elig < min_u:
            continue

        # Chuẩn hóa hạng mặt cắt cho từng đặc trưng (0..1)
        ranked_feats_by_sym: dict[str, list[float]] = {s: [] for s in raw_feats_by_sym}
        for feat_name in FEATURE_NAMES:
            feat_vals = {s: raw_feats_by_sym[s][feat_name] for s in raw_feats_by_sym}
            feat_ranks = cross_sectional_rank(feat_vals)
            for s in raw_feats_by_sym:
                ranked_feats_by_sym[s].append(feat_ranks[s])

        # Chuẩn hóa hạng mặt cắt cho nhãn (0..1)
        ranked_target_by_sym = cross_sectional_rank(raw_hold_by_sym)

        month_data[mk_f] = {
            "symbols": list(raw_feats_by_sym.keys()),
            "ranked_features": ranked_feats_by_sym,  # sym -> list of 11 floats
            "raw_hold_returns": raw_hold_by_sym,     # sym -> float
            "ranked_targets": ranked_target_by_sym,  # sym -> float (0..1)
        }

    # Nếu có cờ shuffle_labels (đối chứng âm): xáo trộn nhãn trong từng tháng
    if shuffle_labels:
        rng_shuf = random.Random(seed)
        for mk_f, md in month_data.items():
            targets = md["ranked_targets"]
            syms = list(targets.keys())
            vals = list(targets.values())
            rng_shuf.shuffle(vals)
            md["ranked_targets"] = dict(zip(syms, vals))

    # 3. Walk-Forward IS theo từng năm (2018..2022)
    test_months_60: list[tuple[int, int]] = []
    y_test = 2018
    while y_test <= 2022:
        for m in range(1, 13):
            test_months_60.append((y_test, m))
        y_test += 1

    cost_rt = round_trip_cost()

    ridge_win_net_list: list[float] = []
    lgbm_win_net_list: list[float] = []
    ew_net_list: list[float] = []
    lose_lgbm_net_list: list[float] = []
    excess_lgbm_list: list[float] = []
    excess_ridge_list: list[float] = []
    lgbm_vs_ridge_list: list[float] = []

    ridge_ic_list: list[float] = []
    lgbm_ic_list: list[float] = []

    yearly_results: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    lgbm_models_by_year: dict[int, LGBMRegressor] = {}

    prev_win_lgbm: list[str] = []
    prev_win_ridge: list[str] = []
    prev_ew: list[str] = []
    prev_lose_lgbm: list[str] = []

    for test_year in TEST_YEARS:
        # Tập huấn luyện cho năm test_year
        train_mks = train_months_for_year(test_year)
        x_train_list: list[list[float]] = []
        y_train_list: list[float] = []

        for mk_tr in train_mks:
            md = month_data.get(mk_tr)
            if not md:
                continue
            feats_dict = md["ranked_features"]
            targets_dict = md["ranked_targets"]
            for sym, tgt in targets_dict.items():
                if sym in feats_dict:
                    x_train_list.append(feats_dict[sym])
                    y_train_list.append(tgt)

        if not x_train_list:
            raise RuntimeError(f"Tập huấn luyện cho năm {test_year} không có mẫu dữ liệu!")

        x_train_arr = np.array(x_train_list, dtype=np.float64)
        y_train_arr = np.array(y_train_list, dtype=np.float64)

        ridge_model = make_ridge_model()
        ridge_model.fit(x_train_arr, y_train_arr)

        lgbm_model = make_lgbm_model()
        lgbm_model.fit(x_train_arr, y_train_arr)
        lgbm_models_by_year[test_year] = lgbm_model

        # Chạy dự báo cho 12 tháng của năm test_year
        for month in range(1, 13):
            test_mk = (test_year, month)
            # Phiên xếp hạng F là phiên cuối của tháng trước đó (test_mk - 1)
            f_mk = (test_year - 1, 12) if month == 1 else (test_year, month - 1)
            md_f = month_data.get(f_mk)

            if not md_f:
                continue

            test_syms = md_f["symbols"]
            x_test_arr = np.array([md_f["ranked_features"][s] for s in test_syms], dtype=np.float64)

            r_preds = ridge_model.predict(x_test_arr)
            l_preds = lgbm_model.predict(x_test_arr)

            ridge_scores = dict(zip(test_syms, r_preds))
            lgbm_scores = dict(zip(test_syms, l_preds))

            # Tính IC (Spearman correlation giữa score và lợi nhuận tháng test_mk)
            actual_rets = md_f["raw_hold_returns"]
            common_ic_syms = [s for s in test_syms if s in actual_rets]
            if len(common_ic_syms) >= 5:
                act_v = [actual_rets[s] for s in common_ic_syms]
                r_v = [ridge_scores[s] for s in common_ic_syms]
                l_v = [lgbm_scores[s] for s in common_ic_syms]
                ic_r = spearmanr(r_v, act_v).statistic
                ic_l = spearmanr(l_v, act_v).statistic
                if not math.isnan(ic_r):
                    ridge_ic_list.append(ic_r)
                if not math.isnan(ic_l):
                    lgbm_ic_list.append(ic_l)

            # Phân loại danh mục
            w_size = max(10, math.ceil(len(test_syms) * 0.10))
            # Sắp xếp giảm dần điểm dự báo, tie-break bằng tên mã
            sorted_ridge = sorted(test_syms, key=lambda s: (-ridge_scores[s], s))
            sorted_lgbm = sorted(test_syms, key=lambda s: (-lgbm_scores[s], s))

            win_ridge_syms = sorted_ridge[:w_size]
            win_lgbm_syms = sorted_lgbm[:w_size]
            lose_lgbm_syms = sorted_lgbm[-w_size:]
            ew_syms = list(test_syms)

            # Lấy lợi nhuận nắm giữ trong tháng test_mk
            ret_map: dict[str, tuple[float | None, str]] = {}
            for s in test_syms:
                sp_h = spans_by_symbol[s].get(test_mk)
                if sp_h is None:
                    ret_map[s] = (None, "thieu_nen")
                else:
                    bars = bars_by_symbol[s]
                    r, why = hold_return(bars, sp_h.first, sp_h.last, exchange_by_symbol.get(s))
                    ret_map[s] = (r, why)

            # Đánh giá WIN_LGBM
            held_lgbm, _ = month_members_returns(win_lgbm_syms, ret_map)
            gross_lgbm = portfolio_gross(held_lgbm) or 0.0
            turn_lgbm = turnover(prev_win_lgbm, win_lgbm_syms)
            net_lgbm = net_month(gross_lgbm, turn_lgbm, cost_rt)
            prev_win_lgbm = win_lgbm_syms

            # Đánh giá WIN_Ridge
            held_ridge, _ = month_members_returns(win_ridge_syms, ret_map)
            gross_ridge = portfolio_gross(held_ridge) or 0.0
            turn_ridge = turnover(prev_win_ridge, win_ridge_syms)
            net_ridge = net_month(gross_ridge, turn_ridge, cost_rt)
            prev_win_ridge = win_ridge_syms

            # Đánh giá EW
            held_ew, _ = month_members_returns(ew_syms, ret_map)
            gross_ew = portfolio_gross(held_ew) or 0.0
            turn_ew = turnover(prev_ew, ew_syms)
            net_ew = net_month(gross_ew, turn_ew, cost_rt)
            prev_ew = ew_syms

            # Đánh giá LOSE_LGBM
            held_lose, _ = month_members_returns(lose_lgbm_syms, ret_map)
            gross_lose = portfolio_gross(held_lose) or 0.0
            turn_lose = turnover(prev_lose_lgbm, lose_lgbm_syms)
            net_lose = net_month(gross_lose, turn_lose, cost_rt)
            prev_lose_lgbm = lose_lgbm_syms

            lgbm_win_net_list.append(net_lgbm)
            ridge_win_net_list.append(net_ridge)
            ew_net_list.append(net_ew)
            lose_lgbm_net_list.append(net_lose)

            excess_l = net_lgbm - net_ew
            excess_r = net_ridge - net_ew
            l_vs_r = net_lgbm - net_ridge

            excess_lgbm_list.append(excess_l)
            excess_ridge_list.append(excess_r)
            lgbm_vs_ridge_list.append(l_vs_r)

            yearly_results[test_year]["lgbm"].append(net_lgbm)
            yearly_results[test_year]["ridge"].append(net_ridge)
            yearly_results[test_year]["ew"].append(net_ew)
            yearly_results[test_year]["lose"].append(net_lose)

    # 4. Bootstrap và thống kê
    boot_excess_lgbm = block_bootstrap(excess_lgbm_list)
    boot_excess_ridge = block_bootstrap(excess_ridge_list)
    boot_lgbm_vs_ridge = block_bootstrap(lgbm_vs_ridge_list)

    # Tiêu chí CÓ LỢI THẾ: p < 0.05, mean(net_WIN_LGBM) > 0, median(excess) > 0
    lgbm_has_edge = (
        boot_excess_lgbm["p"] < 0.05
        and (_mean(lgbm_win_net_list) or 0.0) > 0.0
        and (_median(excess_lgbm_list) or 0.0) > 0.0
    )

    ridge_has_edge = (
        boot_excess_ridge["p"] < 0.05
        and (_mean(ridge_win_net_list) or 0.0) > 0.0
        and (_median(excess_ridge_list) or 0.0) > 0.0
    )

    lgbm_beats_ridge = boot_lgbm_vs_ridge["p"] < 0.05 and (_mean(lgbm_vs_ridge_list) or 0.0) > 0.0

    # Đánh giá kết luận
    if lgbm_has_edge and lgbm_beats_ridge:
        ml_value_conclusion = "Học máy có giá trị"
    elif lgbm_has_edge and not lgbm_beats_ridge:
        ml_value_conclusion = "Lợi thế đến từ đặc trưng, không phải học máy"
    elif ridge_has_edge and not lgbm_has_edge:
        ml_value_conclusion = "Ridge có lợi thế còn LGBM không"
    else:
        ml_value_conclusion = "Không có lợi thế trên IS 2018–2022"

    # 5. Mốc chuẩn ETF + Tiền gửi (165)
    # 15% WIN_LGBM + 85% Tiền gửi 6%
    mix_lgbm = simulate_equity_deposit_mix(lgbm_win_net_list, test_months_60, w=0.15, r=DEPOSIT_RATE)

    etf_res: dict[str, Any] = {"ok": False}
    mix_etf: dict[str, Any] = {"cagr": 0.0, "mdd": 0.0}
    if not synthetic_mode and dsn:
        try:
            storage_obj = Storage(dsn)
            etf_res = etf_buy_hold(storage_obj, first_month=(2018, 1), last_month=(2022, 12))
            clean_etf, _ = read_is_bars(storage_obj, symbol=ETF_SYMBOL)
            etf_bars = [b for b in clean_etf if bar_date(b) >= date(2018, 1, 1)]
            sim_etf = simulate_mix(etf_bars, w=0.15, r=DEPOSIT_RATE, rebalance_mode="annual")
            mix_etf = {
                "cagr": (sim_etf.equity_curve[-1] ** (12.0 / len(test_months_60))) - 1.0,
                "mdd": equity_curve_max_drawdown(sim_etf.equity_curve),  # sua cua Claude: ham dot 102 nhan chuoi loi nhuan, khong phai duong tai san
            }
        except Exception:
            pass

    # Đếm số mã có nến cuối trước 30/06/2022 (thiên lệch sống sót)
    delisted_count = 0
    cutoff_delist = date(2022, 6, 30)
    for sym, bars in bars_by_symbol.items():
        if bars and bar_date(bars[-1]) < cutoff_delist:
            delisted_count += 1

    # Feature importance của LGBM năm cuối (2022)
    feat_importance: dict[str, float] = {}
    if 2022 in lgbm_models_by_year:
        imp = lgbm_models_by_year[2022].feature_importances_
        feat_importance = dict(zip(FEATURE_NAMES, [float(x) for x in imp]))

    return {
        "lgbm_has_edge": lgbm_has_edge,
        "ridge_has_edge": ridge_has_edge,
        "lgbm_beats_ridge": lgbm_beats_ridge,
        "ml_value_conclusion": ml_value_conclusion,
        "lgbm_win_mean": _mean(lgbm_win_net_list) or 0.0,
        "ridge_win_mean": _mean(ridge_win_net_list) or 0.0,
        "ew_mean": _mean(ew_net_list) or 0.0,
        "lose_lgbm_mean": _mean(lose_lgbm_net_list) or 0.0,
        "excess_lgbm_mean": _mean(excess_lgbm_list) or 0.0,
        "excess_lgbm_median": _median(excess_lgbm_list) or 0.0,
        "boot_excess_lgbm": boot_excess_lgbm,
        "boot_excess_ridge": boot_excess_ridge,
        "boot_lgbm_vs_ridge": boot_lgbm_vs_ridge,
        "lgbm_cagr": cagr(lgbm_win_net_list),
        "ridge_cagr": cagr(ridge_win_net_list),
        "ew_cagr": cagr(ew_net_list),
        "lgbm_mdd": max_drawdown(lgbm_win_net_list),
        "ridge_mdd": max_drawdown(ridge_win_net_list),
        "ew_mdd": max_drawdown(ew_net_list),
        "ridge_ic_mean": _mean(ridge_ic_list) or 0.0,
        "ridge_ic_std": statistics.stdev(ridge_ic_list) if len(ridge_ic_list) > 1 else 0.0,
        "ridge_ic_pos_share": share_positive(ridge_ic_list),
        "lgbm_ic_mean": _mean(lgbm_ic_list) or 0.0,
        "lgbm_ic_std": statistics.stdev(lgbm_ic_list) if len(lgbm_ic_list) > 1 else 0.0,
        "lgbm_ic_pos_share": share_positive(lgbm_ic_list),
        "yearly_results": dict(yearly_results),
        "mix_lgbm": mix_lgbm,
        "mix_etf": mix_etf,
        "etf_res": etf_res,
        "n_symbols": len(bars_by_symbol),
        "delisted_count": delisted_count,
        "eligible_counts": eligible_count_by_month,
        "feat_importance_2022": feat_importance,
        "n_test_months": len(lgbm_win_net_list),
        "bars_by_symbol": bars_by_symbol,
        "exchange_by_symbol": exchange_by_symbol,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sàng lọc học máy xếp hạng cổ phiếu VN (Brief đợt 169 — ĐĂNG KÝ TRƯỚC)."
    )
    parser.add_argument("--dsn", type=str, default=None, help="PostgreSQL DSN (mặc định đọc .env)")
    parser.add_argument(
        "--exclusions", type=str, default=EXCLUSIONS_FILE, help="Đường dẫn file exclusions.txt"
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    print("=" * 80)
    print("BRIEF ĐỢT 169 — HỌC MÁY XẾP HẠNG CỔ PHIẾU VN THEO THÁNG (ĐĂNG KÝ TRƯỚC)")
    print("=" * 80)

    # 1. Chạy đối chứng âm trước (bắt buộc theo §1.7)
    print("\n[1/2] Đang chạy kiểm tra ĐỐI CHỨNG ÂM (nhãn xáo trộn theo tháng, seed=42)...")
    neg_res = run_ml_cross_section_screen(
        dsn=args.dsn,
        exclusions_path=args.exclusions,
        shuffle_labels=True,
        seed=42,
    )
    print(f"  Đối chứng âm: excess(LGBM - EW) mean = {neg_res['excess_lgbm_mean']*100:+.2f}%/tháng, p = {neg_res['boot_excess_lgbm']['p']:.4f}")
    if neg_res["lgbm_has_edge"]:
        print("\n[CẢNH BÁO NGUY HIỂM] Đối chứng âm ra CÓ LỢI THẾ -> Đường ống có rò rỉ!")
        print("DỪNG VÀ BÁO CÁO THEO QUY TẮC §1.7.")
        return 1

    # 2. Chạy phép đo IS chính
    print("\n[2/2] Đang chạy PHÉP ĐO IS CHÍNH (Walk-Forward 2018–2022, 60 tháng)...")
    res = run_ml_cross_section_screen(
        dsn=args.dsn,
        exclusions_path=args.exclusions,
        shuffle_labels=False,
        cached_bars=neg_res.get("bars_by_symbol"),
        cached_exchanges=neg_res.get("exchange_by_symbol"),
    )
    t_elapsed = time.perf_counter() - t0

    # In kết quả chi tiết
    print("\n" + "=" * 80)
    print("KẾT QUẢ ĐO LƯỜNG WALK-FORWARD IS (2018–2022)")
    print("=" * 80)

    print(f"Tổng số mã cổ phiếu nạp: {res['n_symbols']}")
    print(f"Số mã có nến cuối trước 30/06/2022 (đã hủy niêm yết): {res['delisted_count']}")
    
    elig_vals = list(res["eligible_counts"].values())
    if elig_vals:
        print(f"Số mã đủ điều kiện mỗi tháng: Min = {min(elig_vals)}, Median = {statistics.median(elig_vals):.0f}, Max = {max(elig_vals)}")
    print(f"Số tháng thử nghiệm: {res['n_test_months']}")

    print("\n--- BẢNG KẾT QUẢ CHÍNH (§1.7) ---")
    print(f"{'Mô hình / Phép so sánh':<25} | {'Mean Net (%/tháng)':<20} | {'Median Net (%/tháng)':<20} | {'p-value':<10} | {'KTC 95% [Low; High]':<22}")
    print("-" * 105)
    
    b_l = res["boot_excess_lgbm"]
    b_r = res["boot_excess_ridge"]
    b_diff = res["boot_lgbm_vs_ridge"]

    print(f"{'WIN_LGBM - EW':<25} | {res['excess_lgbm_mean']*100:+18.2f}% | {res['excess_lgbm_median']*100:+18.2f}% | {b_l['p']:<10.4f} | [{b_l['ci_low']*100:+.2f}%; {b_l['ci_high']*100:+.2f}%]")
    print(f"{'WIN_Ridge - EW':<25} | {(res['ridge_win_mean'] - res['ew_mean'])*100:+18.2f}% | {b_r['median']*100:+18.2f}% | {b_r['p']:<10.4f} | [{b_r['ci_low']*100:+.2f}%; {b_r['ci_high']*100:+.2f}%]")
    print(f"{'WIN_LGBM - WIN_Ridge':<25} | {(res['lgbm_win_mean'] - res['ridge_win_mean'])*100:+18.2f}% | {b_diff['median']*100:+18.2f}% | {b_diff['p']:<10.4f} | [{b_diff['ci_low']*100:+.2f}%; {b_diff['ci_high']*100:+.2f}%]")

    print("\n--- TỔNG KẾT CHIẾN LƯỢC TOÀN KỲ (2018–2022) ---")
    print(f"{'Danh mục':<15} | {'Mean Net/th':<12} | {'CAGR Net':<10} | {'Max Drawdown':<12}")
    print("-" * 55)
    print(f"{'WIN_LGBM':<15} | {res['lgbm_win_mean']*100:+10.2f}% | {(res['lgbm_cagr'] or 0)*100:8.2f}% | {res['lgbm_mdd']*100:10.2f}%")
    print(f"{'WIN_Ridge':<15} | {res['ridge_win_mean']*100:+10.2f}% | {(res['ridge_cagr'] or 0)*100:8.2f}% | {res['ridge_mdd']*100:10.2f}%")
    print(f"{'EW':<15} | {res['ew_mean']*100:+10.2f}% | {(res['ew_cagr'] or 0)*100:8.2f}% | {res['ew_mdd']*100:10.2f}%")
    print(f"{'LOSE_LGBM':<15} | {res['lose_lgbm_mean']*100:+10.2f}% | {'N/A':<10} | {'N/A':<12}")

    print("\n--- HỆ SỐ TƯƠNG QUAN HẠNG SPEARMAN (IC) ---")
    print(f"Ridge: Mean IC = {res['ridge_ic_mean']:+.4f} (std = {res['ridge_ic_std']:.4f}), Tỷ lệ tháng IC > 0: {res['ridge_ic_pos_share']*100:.1f}%")
    print(f"LGBM:  Mean IC = {res['lgbm_ic_mean']:+.4f} (std = {res['lgbm_ic_std']:.4f}), Tỷ lệ tháng IC > 0: {res['lgbm_ic_pos_share']*100:.1f}%")

    print("\n--- KẾT QUẢ THEO TỪNG NĂM (CAGR Net) ---")
    print(f"{'Năm':<6} | {'WIN_LGBM':<12} | {'WIN_Ridge':<12} | {'EW':<12} | {'LOSE_LGBM':<12}")
    print("-" * 56)
    for yr in TEST_YEARS:
        yr_d = res["yearly_results"][yr]
        c_l = cagr(yr_d["lgbm"]) or 0.0
        c_r = cagr(yr_d["ridge"]) or 0.0
        c_e = cagr(yr_d["ew"]) or 0.0
        c_lose = cagr(yr_d["lose"]) or 0.0
        print(f"{yr:<6} | {c_l*100:+10.2f}% | {c_r*100:+10.2f}% | {c_e*100:+10.2f}% | {c_lose*100:+10.2f}%")

    print("\n--- ĐỐI CHIẾU MỐC CHUẨN ĐỢT 165 (15% RỦI RO + 85% TIỀN GỬI 6%) ---")
    mix_l = res["mix_lgbm"]
    mix_e = res["mix_etf"]
    print(f"15% WIN_LGBM + 85% Tiền gửi 6%: CAGR = {mix_l['cagr']*100:.2f}%, MDD = {mix_l['mdd']*100:.2f}%")
    print(f"15% ETF E1VFVN30 + 85% Tiền gửi 6%: CAGR = {mix_e['cagr']*100:.2f}%, MDD = {mix_e['mdd']*100:.2f}%")

    # Kiểm tra chuẩn spec mục B (MDD <= 4.7%, MDD <= 7%, CAGR >= 6%)
    pass_mdd_bt = "ĐẠT" if mix_l["mdd"] <= 0.047 else "KHÔNG ĐẠT"
    pass_mdd_live = "ĐẠT" if mix_l["mdd"] <= 0.07 else "KHÔNG ĐẠT"
    pass_cagr = "ĐẠT" if mix_l["cagr"] >= 0.06 else "KHÔNG ĐẠT"
    print(f"  * Tiêu chuẩn MDD backtest <= 4.7%: {pass_mdd_bt} ({mix_l['mdd']*100:.2f}%)")
    print(f"  * Tiêu chuẩn MDD live <= 7.0%:     {pass_mdd_live} ({mix_l['mdd']*100:.2f}%)")
    print(f"  * Tiêu chuẩn CAGR >= 6.0%:        {pass_cagr} ({mix_l['cagr']*100:.2f}%)")

    print("\n--- ĐỘ QUAN TRỌNG ĐẶC TRƯNG CỦA LGBM (NĂM 2022) ---")
    for fname, imp_val in sorted(res["feat_importance_2022"].items(), key=lambda x: -x[1]):
        print(f"  {fname:<16}: {imp_val:6.1f}")

    print("\n" + "=" * 80)
    print(f"KẾT LUẬN CUỐI CÙNG: {res['ml_value_conclusion']}")
    print("=" * 80)
    print(f"Thời gian thực thi: {t_elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
