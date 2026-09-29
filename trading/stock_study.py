"""Thư viện đo lường và sàng lọc cổ phiếu thị trường chứng khoán Việt Nam.

Tập trung các hàm trung tính, sự thật khách quan của thị trường (luật biên độ sàn,
mốc niêm phong holdout, định nghĩa Trend Template Minervini) và các hàm tiện ích
tính toán chuỗi thời gian, thanh khoản, kiểm thử thống kê.

Các tham số mang tính lựa chọn của từng đợt nghiên cứu (cửa sổ thanh khoản, nến nghỉ,
k mục tiêu, số lần bootstrap, khoảng tin cậy...) KHÔNG có giá trị mặc định ở đây;
nơi gọi phải truyền tường minh các hằng số tiền đăng ký của chính mình.
"""

from __future__ import annotations

import pathlib
import random
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from trading.calendar_vn import TZ
from trading.metrics import calculate_percentile, empirical_percentile_rank
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.storage.db import Storage

# --- Sự thật khách quan và định nghĩa chuẩn -----------------------------------------

SEALED_START = date(2023, 1, 1)

LIMIT_BY_EXCHANGE = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
DEFAULT_LIMIT_RATE = 0.07
LIMIT_EPS = 0.001

TREND_MIN_BARS = 252
RANGE_WINDOW = 252

TREND_KEYS = (
    "c1_close_tren_sma150_200",
    "c2_sma150_tren_sma200",
    "c3_sma200_di_len",
    "c4_sma50_tren_sma150_200",
    "c5_close_tren_sma50",
    "c6_cach_day_252_nen",
    "c7_gan_dinh_252_nen",
)


# --- Tiện ích thời gian và dữ liệu --------------------------------------------------

def bar_date(b: Bar) -> date:
    """Ngày giao dịch của nến theo GIỜ VN (bars_daily lưu 00:00 VN = 17:00 UTC hôm trước)."""
    return b.ts.astimezone(TZ).date()


def month_key(d: date) -> tuple[int, int]:
    """Khoá khối bootstrap: tháng dương lịch của ngày (giờ VN)."""
    return (d.year, d.month)


def validate_sealed_bars(bars: list[Bar]) -> None:
    """Ném lỗi nếu có nến từ 2023-01-01 (giờ VN) trở đi — khuôn của screen_vn30f_intraday."""
    for b in bars:
        d = bar_date(b)
        if d >= SEALED_START:
            raise ValueError(
                f"Vi phạm niêm phong (Holdout Breach): nến {d.isoformat()} "
                f">= mốc niêm phong {SEALED_START.isoformat()}"
            )


def clean_bars(bars: list[Bar]) -> tuple[list[Bar], int]:
    """Bỏ nến có open/high/low/close <= 0. Nến volume = 0 GIỮ NGUYÊN trong chuỗi."""
    kept: list[Bar] = []
    dropped = 0
    for b in bars:
        if b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0:
            dropped += 1
        else:
            kept.append(b)
    return kept, dropped


def load_universe(
    storage: Storage, exclude_file: str | None = "exclusions.txt"
) -> tuple[list[str], dict[str, str], int, set[str]]:
    """Danh sách mã có nến trong bars_daily, đã loại mã hỏng; kèm bản đồ sàn.

    exclude_file=None hoặc "" -> không loại mã nào, không chạm filesystem.
    Trên Windows, pathlib.Path("").exists() trả True (trỏ vào ".") rồi read_text()
    ném PermissionError — bẫy đã làm agent đợt 120 phải né (vá đợt 124).
    """
    excluded: set[str] = set()
    if exclude_file:
        p = pathlib.Path(exclude_file)
        if p.exists():
            excluded = {s.strip().upper() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()}
    with storage.conn() as c:
        all_syms = [r[0] for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")]
        exchange = {r[0]: (r[1] or "") for r in c.execute("SELECT symbol, exchange FROM symbol_universe")}
    n_all = len(all_syms)
    universe = [s for s in all_syms if s.upper() not in excluded]
    return universe, exchange, n_all, excluded


# --- Trượt (không dùng numpy/pandas) ------------------------------------------------

def rolling_mean(values: list[float], window: int) -> list[float | None]:
    """Trung bình trượt của `window` giá trị KẾT THÚC tại i (tổng trượt, không tính lại)."""
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out


def rolling_max(values: list[float], window: int) -> list[float | None]:
    """Max trượt của `window` giá trị kết thúc tại i (hàng đợi đơn điệu)."""
    out: list[float | None] = [None] * len(values)
    dq: deque[int] = deque()
    for i, v in enumerate(values):
        while dq and values[dq[-1]] <= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - window:
            dq.popleft()
        if i >= window - 1:
            out[i] = values[dq[0]]
    return out


def rolling_min(values: list[float], window: int) -> list[float | None]:
    """Min trượt của `window` giá trị kết thúc tại i."""
    out: list[float | None] = [None] * len(values)
    dq: deque[int] = deque()
    for i, v in enumerate(values):
        while dq and values[dq[-1]] >= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - window:
            dq.popleft()
        if i >= window - 1:
            out[i] = values[dq[0]]
    return out


# --- Bộ lọc xu hướng (7 điều kiện tại t-1) ------------------------------------------

def _trend_from_arrays(
    *,
    close_i: float,
    sma50_i: float,
    sma150_i: float,
    sma200_i: float,
    sma200_prev21: float,
    low252_i: float,
    high252_i: float,
) -> dict[str, bool]:
    return {
        "c1_close_tren_sma150_200": close_i > sma150_i and close_i > sma200_i,
        "c2_sma150_tren_sma200": sma150_i > sma200_i,
        "c3_sma200_di_len": sma200_i > sma200_prev21,
        "c4_sma50_tren_sma150_200": sma50_i > sma150_i and sma50_i > sma200_i,
        "c5_close_tren_sma50": close_i > sma50_i,
        "c6_cach_day_252_nen": close_i >= 1.30 * low252_i,
        "c7_gan_dinh_252_nen": close_i >= 0.75 * high252_i,
    }


def _all_false() -> dict[str, bool]:
    return dict.fromkeys(TREND_KEYS, False)


def trend_conditions(
    bars: list[Bar],
    t: int,
    *,
    sma50: list[float | None] | None = None,
    sma150: list[float | None] | None = None,
    sma200: list[float | None] | None = None,
    win_low: list[float | None] | None = None,
    win_high: list[float | None] | None = None,
) -> dict[str, bool]:
    """Bảy điều kiện của bộ lọc xu hướng, tính tại ĐÓNG CỬA NẾN t-1.

    `t` là chỉ số nến tín hiệu. Bỏ qua các mảng tính trước thì hàm tự tính (đường chậm,
    dùng cho test); truyền vào thì dùng lại (đường nhanh, dùng khi chạy thật).
    """
    if t < TREND_MIN_BARS:
        return _all_false()
    i = t - 1
    if sma50 is None or sma150 is None or sma200 is None or win_low is None or win_high is None:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        sma50 = rolling_mean(closes, 50)
        sma150 = rolling_mean(closes, 150)
        sma200 = rolling_mean(closes, 200)
        win_low = rolling_min(lows, RANGE_WINDOW)
        win_high = rolling_max(highs, RANGE_WINDOW)

    s50, s150, s200 = sma50[i], sma150[i], sma200[i]
    s200_prev = sma200[i - 21]
    lo252, hi252 = win_low[i], win_high[i]
    if s50 is None or s150 is None or s200 is None or s200_prev is None or lo252 is None or hi252 is None:
        return _all_false()
    return _trend_from_arrays(
        close_i=bars[i].close,
        sma50_i=s50,
        sma150_i=s150,
        sma200_i=s200,
        sma200_prev21=s200_prev,
        low252_i=lo252,
        high252_i=hi252,
    )


# --- Cơ chế thị trường VN, chi phí và lệnh ----------------------------------------

def limit_rate(exchange: str | None) -> float:
    """Biên độ trần theo sàn; sàn không rõ thì dùng 0,07."""
    return LIMIT_BY_EXCHANGE.get((exchange or "").upper(), DEFAULT_LIMIT_RATE)


def is_ceiling_open(prev_close: float, next_open: float, exchange: str | None) -> bool:
    """Mở cửa ở giá trần: open >= close[trước] x (1 + biên độ - 0,001)."""
    return next_open >= prev_close * (1 + limit_rate(exchange) - LIMIT_EPS)


def entry_status(bars: list[Bar], t: int, exchange: str | None) -> str:
    """'ok' | 'ceiling' | 'zero_volume' | 'no_bar' — vào lệnh tại open[t+1]."""
    if t + 1 >= len(bars):
        return "no_bar"
    nxt = bars[t + 1]
    if is_ceiling_open(bars[t].close, nxt.open, exchange):
        return "ceiling"
    if nxt.volume == 0:
        return "zero_volume"
    return "ok"


def net_return(entry_open: float, exit_close: float) -> float:
    """Lợi nhuận ròng (phí, thuế, trượt giá) — dùng các hằng số import từ paper_broker."""
    s = SLIPPAGE_BPS / 10_000.0
    return (exit_close * (1 - FEE_RATE - SELL_TAX_RATE - s)) / (entry_open * (1 + FEE_RATE + s)) - 1.0


def compute_targets(
    bars: list[Bar],
    t: int,
    *,
    ks: tuple[int, ...],
) -> dict[int, float | None]:
    """Lợi nhuận GỘP r_k = close[t+k] / open[t+1] - 1; None khi thiếu nến.

    Tham số `ks` là bắt buộc theo §2.3 Brief đợt 122.
    """
    out: dict[int, float | None] = {}
    if t + 1 >= len(bars):
        return dict.fromkeys(ks, None)
    entry = bars[t + 1].open
    for k in ks:
        out[k] = (bars[t + k].close / entry - 1.0) if (t + k < len(bars) and entry > 0) else None
    return out


def liquidity_ok(
    bars: list[Bar],
    t: int,
    *,
    window: int,
    min_turnover: float,
) -> bool:
    """Trung bình `close x volume` của `window` nến TRƯỚC t phải >= `min_turnover`.

    Các tham số `window` và `min_turnover` là bắt buộc theo §2.3 Brief đợt 122.
    """
    if t < window:
        return False
    total = sum(bars[i].close * bars[i].volume for i in range(t - window, t))
    return total / window >= min_turnover


def apply_cooldown(
    indices: list[int],
    *,
    cooldown: int,
) -> list[int]:
    """Sau một sự kiện, không nhận sự kiện mới trong `cooldown` nến tiếp theo.

    Tham số `cooldown` là bắt buộc theo §2.3 Brief đợt 122.
    """
    out: list[int] = []
    last: int | None = None
    for i in indices:
        if last is None or i - last > cooldown:
            out.append(i)
            last = i
    return out


# --- Thống kê: bootstrap theo khối tháng -------------------------------------------

def bootstrap_by_month(
    by_month: dict[tuple[int, int], list[float]],
    *,
    n: int,
    seed: int,
    ci_low_pct: float,
    ci_high_pct: float,
) -> dict[str, Any]:
    """Bootstrap khối THÁNG dương lịch: lấy mẫu lại các tháng có hoàn lại, n lần, seed cố định.

    p = tỷ lệ mẫu bootstrap có trung bình <= 0 (kiểm một phía: giả thuyết trung bình > 0).
    Các tham số `n`, `seed`, `ci_low_pct`, `ci_high_pct` là bắt buộc theo §2.3 Brief đợt 122.
    """
    months = sorted(by_month.keys())
    all_vals = [v for m in months for v in by_month[m]]
    if not months or not all_vals:
        return {"mean": None, "ci_low": None, "ci_high": None, "p": None, "n_months": 0}
    mean_obs = sum(all_vals) / len(all_vals)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n):
        vals: list[float] = []
        for _ in range(len(months)):
            vals.extend(by_month[months[rng.randrange(len(months))]])
        means.append(sum(vals) / len(vals))
    means.sort()
    p = sum(1 for m in means if m <= 0.0) / len(means)
    return {
        "mean": mean_obs,
        "ci_low": calculate_percentile(means, ci_low_pct),
        "ci_high": calculate_percentile(means, ci_high_pct),
        "p": p,
        "n_months": len(months),
    }


# --- RS Rating (Minervini SEPA) -----------------------------------------------------

def calculate_rs_ranks(rs_raw_by_symbol: dict[str, float]) -> dict[str, int]:
    """Quy đổi RS_raw thành RS_rank thang 1–99 dựa trên phân vị thực nghiệm.

    Dời từ score_sepa_daily.py theo §2.2 Brief đợt 122.
    """
    if not rs_raw_by_symbol:
        return {}

    raw_values = list(rs_raw_by_symbol.values())
    ranks: dict[str, int] = {}
    for sym, raw_val in rs_raw_by_symbol.items():
        pct = empirical_percentile_rank(raw_values, raw_val)
        rank_val = max(1, min(99, round(pct)))
        ranks[sym] = rank_val
    return ranks


# --- Ro doi chung trung tinh (khong loc xu huong) -----------------------------------

@dataclass(frozen=True, slots=True)
class BasketEntry:
    """Mot ma trong ro doi chung cua mot ngay (r = None nghia la khung do khong co du lieu)."""

    symbol: str
    r: dict[int, float | None]

    def r_of(self, k: int) -> float | None:
        return self.r.get(k)


def make_basket_entry(
    symbol: str,
    bars: list[Bar],
    i: int,
    exchange: str | None,
    *,
    min_turnover: float,
    window: int,
    ks: tuple[int, ...],
) -> BasketEntry | None:
    """None neu ma nay khong duoc vao ro (duoi thanh khoan, khong vao duoc lenh, khong co du lieu)."""
    if not liquidity_ok(bars, i, window=window, min_turnover=min_turnover):
        return None
    if entry_status(bars, i, exchange) != "ok":
        return None
    tg = compute_targets(bars, i, ks=ks)
    if all(tg.get(k) is None for k in ks):
        return None
    return BasketEntry(symbol, dict(tg))


def basket_for_day(entries: Mapping[str, BasketEntry], event_symbol: str) -> list[BasketEntry]:
    """Ro doi chung cua mot ngay: moi ma khac ma su kien (KHONG gom chinh ma su kien)."""
    return [e for sym, e in entries.items() if sym != event_symbol]


def baseline_for_basket(entries: list[BasketEntry], k: int) -> tuple[float | None, int]:
    """(baseline_k, so ma duoc tinh) — chi tinh cac ma co r_k (du du lieu vao/thoat)."""
    vals = [v for v in (e.r_of(k) for e in entries) if v is not None]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def excess_k(
    r_event: float | None,
    entries: list[BasketEntry],
    k: int,
    *,
    min_control: int,
) -> tuple[float | None, float | None, int]:
    """(baseline_k, excess_k, so ma trong ro); excess = None khi ro < min_control hoac thieu du lieu."""
    baseline, n = baseline_for_basket(entries, k)
    if r_event is None or baseline is None or n < min_control:
        return baseline, None, n
    return baseline, r_event - baseline, n

