"""Sàng lọc VCP (Volatility Contraction Pattern) trên cổ phiếu VN, nến ngày — Brief đợt 99.

Thiết kế ĐĂNG KÝ TRƯỚC (mọi tham số chốt trong brief, không đổi sau khi thấy dữ liệu):
- Nguồn: `bars_daily` qua Storage.read_daily_bars. Ngày của nến tính theo GIỜ VN
  (`bar.ts.astimezone(TZ).date()`), KHÔNG dùng `.date()` trên datetime UTC.
- Niêm phong: đọc tới 2022-12-31; nến từ 2023-01-01 (giờ VN) trở đi thì NÉM LỖI.
- Loại mã hỏng theo `exclusions.txt`; bỏ nến có OHLC <= 0; nến volume = 0 vẫn ở trong
  chuỗi nhưng không được làm nến tín hiệu / vào lệnh / thoát lệnh.
- Thanh khoản: trung bình `close x volume` của 20 nến TRƯỚC nến tín hiệu >= 1 tỷ đồng.
- Bộ lọc xu hướng 7 điều kiện tại đóng cửa nến t-1 (không có RS rating — ghi trong báo cáo).
- Nền VCP 60 nến chia 3 đoạn 20 nến: co hẹp dần và khối lượng cạn dần; pivot = max high S3.
- Nến phá vỡ t: close[t] > pivot va volume[t] >= 1,5 x trung binh volume 50 nen truoc.
- Thời gian nghỉ 20 nến sau mỗi sự kiện cùng mã.
- Vào tại open[t+1] (bỏ nếu mở giá trần theo sàn, hoặc volume[t+1] = 0); thoát tại close[t+k].
- Đối chứng CÙNG NGÀY: các mã khác đạt thanh khoản + bộ lọc xu hướng tại t-1, có đủ dữ liệu
  vào/thoát; `excess_k = r_k - baseline_k`. Rổ < 5 mã thì bỏ khỏi phép so vượt trội.
- Phép thử chính: k = 20, một phía, bootstrap theo khối THÁNG DƯƠNG LỊCH (2.000 lần, seed 42).

Không dùng pandas/numpy (repo không có). SMA và trung bình trượt dùng tổng trượt.
"""

from __future__ import annotations

import argparse
import io
import math
import pathlib
import random
import statistics
import sys
import time
from array import array
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.storage.db import Storage

# --- Nguong va tham so da dang ky truoc --------------------------------------------
IS_SIGNAL_START = date(2016, 1, 4)
IS_SIGNAL_END = date(2022, 11, 30)
SEALED_START = date(2023, 1, 1)
READ_FROM = datetime(2016, 1, 1, tzinfo=TZ)
READ_TO = datetime(2023, 1, 1, tzinfo=TZ)

LIMIT_BY_EXCHANGE = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
DEFAULT_LIMIT_RATE = 0.07
LIMIT_EPS = 0.001

MIN_TURNOVER_VND = 1_000_000_000.0
TURNOVER_WINDOW = 20
TREND_MIN_BARS = 252
RANGE_WINDOW = 252
DEPTH_MAX_S1 = 0.35
DEPTH_MAX_S3 = 0.10
BASE_LEN = 60
SEG_LEN = 20
BREAKOUT_VOL_MULT = 1.5
BREAKOUT_VOL_WINDOW = 50
COOLDOWN_BARS = 20
TARGET_KS = (5, 10, 20)
MAIN_K = 20
MIN_CONTROL = 5
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 42
MIN_EVENTS = 100
P95 = 0.95
CI_LOW_PCT = 2.5
CI_HIGH_PCT = 97.5

TREND_KEYS = (
    "c1_close_tren_sma150_200",
    "c2_sma150_tren_sma200",
    "c3_sma200_di_len",
    "c4_sma50_tren_sma150_200",
    "c5_close_tren_sma50",
    "c6_cach_day_252_nen",
    "c7_gan_dinh_252_nen",
)


# --- Tien ich thoi gian ------------------------------------------------------------

def bar_date(b: Bar) -> date:
    """Ngay giao dich cua nen theo GIO VN (bars_daily luu 00:00 VN = 17:00 UTC hom truoc)."""
    return b.ts.astimezone(TZ).date()


def in_is(d: date) -> bool:
    """Ngay tin hieu co nam trong In-Sample khong."""
    return IS_SIGNAL_START <= d <= IS_SIGNAL_END


def month_key(d: date) -> tuple[int, int]:
    """Khoa khoi bootstrap: thang duong lich cua ngay (gio VN)."""
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
    """Bo nen co open/high/low/close <= 0. Nen volume = 0 GIU NGUYEN trong chuoi."""
    kept: list[Bar] = []
    dropped = 0
    for b in bars:
        if b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0:
            dropped += 1
        else:
            kept.append(b)
    return kept, dropped


# --- Truot (khong dung numpy) ------------------------------------------------------

def rolling_mean(values: list[float], window: int) -> list[float | None]:
    """Trung binh truot cua `window` gia tri KET THUC tai i (tong truot, khong tinh lai)."""
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
    """Max truot cua `window` gia tri ket thuc tai i (hang doi don dieu)."""
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
    """Min truot cua `window` gia tri ket thuc tai i."""
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


# --- Bo loc xu huong (7 dieu kien tai t-1) -----------------------------------------

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
    """Bay dieu kien cua bo loc xu huong, tinh tai DONG CUA NEN t-1.

    `t` la chi so nen tin hieu. Bo qua cac mang tinh truoc thi ham tu tinh (duong cham,
    dung cho test); truyen vao thi dung lai (duong nhanh, dung khi chay that).
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


def trend_filter_ok(bars: list[Bar], t: int, **arrays: Any) -> bool:
    """Ca 7 dieu kien phai dung."""
    return all(trend_conditions(bars, t, **arrays).values())


# --- Thanh khoan, nen VCP, nen pha vo ---------------------------------------------

def liquidity_ok(
    bars: list[Bar],
    t: int,
    window: int = TURNOVER_WINDOW,
    min_turnover: float = MIN_TURNOVER_VND,
) -> bool:
    """Trung binh `close x volume` cua `window` nen TRUOC t phai >= 1 ty dong."""
    if t < window:
        return False
    total = sum(bars[i].close * bars[i].volume for i in range(t - window, t))
    return total / window >= min_turnover


def base_depths(bars: list[Bar], t: int) -> tuple[float, float, float]:
    """Do sau tung doan 20 nen cua nen VCP: (max high - min low) / max high."""
    out = []
    for seg in range(3):
        i0 = t - BASE_LEN + seg * SEG_LEN
        hmax = max(bars[i].high for i in range(i0, i0 + SEG_LEN))
        lmin = min(bars[i].low for i in range(i0, i0 + SEG_LEN))
        out.append((hmax - lmin) / hmax)
    return (out[0], out[1], out[2])


def pivot_price(bars: list[Bar], t: int) -> float:
    """Pivot P = max high cua S3 = 20 nen t-20..t-1 (KHONG gom nen t)."""
    return max(bars[i].high for i in range(t - SEG_LEN, t))


def vcp_base_ok(bars: list[Bar], t: int) -> bool:
    """Nen VCP: co hep dan 0,35 / 0,10 va khoi luong can dan."""
    if t < BASE_LEN:
        return False
    d1, d2, d3 = base_depths(bars, t)
    if not (d1 > d2 > d3):
        return False
    if d1 > DEPTH_MAX_S1 or d3 > DEPTH_MAX_S3:
        return False
    i0 = t - BASE_LEN
    vol_s1 = sum(bars[i].volume for i in range(i0, i0 + SEG_LEN)) / SEG_LEN
    vol_s3 = sum(bars[i].volume for i in range(t - SEG_LEN, t)) / SEG_LEN
    return vol_s3 < vol_s1


def breakout_ok(bars: list[Bar], t: int) -> bool:
    """close[t] > pivot VA volume[t] >= 1,5 x trung binh volume 50 nen truoc."""
    if t < BREAKOUT_VOL_WINDOW + 1:
        return False
    if not bars[t].close > pivot_price(bars, t):
        return False
    vmean = sum(bars[i].volume for i in range(t - BREAKOUT_VOL_WINDOW, t)) / BREAKOUT_VOL_WINDOW
    return vmean > 0 and bars[t].volume >= BREAKOUT_VOL_MULT * vmean


def apply_cooldown(indices: list[int], cooldown: int = COOLDOWN_BARS) -> list[int]:
    """Sau mot su kien, khong nhan su kien moi trong `cooldown` nen tiep theo."""
    out: list[int] = []
    last: int | None = None
    for i in indices:
        if last is None or i - last > cooldown:
            out.append(i)
            last = i
    return out


def find_events(bars: list[Bar], min_turnover: float = MIN_TURNOVER_VND) -> list[int]:
    """Chi so cac nen tin hieu VCP cua MOT ma, da ap thoi gian nghi."""
    highs = [b.high for b in bars]
    rmax20 = rolling_max(highs, SEG_LEN)
    cand: list[int] = []
    for t in range(len(bars)):
        if t < TREND_MIN_BARS or bars[t].volume == 0:
            continue
        hi_truoc = rmax20[t - 1]
        if hi_truoc is None or not bars[t].close > hi_truoc:
            continue                      # mem hieu nang: close > max high 20 nen truoc
        cand.append(t)
    kept = [
        t
        for t in cand
        # liquidity_ok: CUNG bo loc voi ro doi chung (SymbolData.liq_ok, cung cua so 20 nen
        # truoc t) - thieu no thi phe VCP va phe doi chung khac vu tru (audit dot 99).
        if liquidity_ok(bars, t, min_turnover=min_turnover)
        and trend_filter_ok(bars, t)
        and vcp_base_ok(bars, t)
        and breakout_ok(bars, t)
    ]
    return apply_cooldown(kept)


# --- Vao lenh, muc tieu, chi phi ---------------------------------------------------

def limit_rate(exchange: str | None) -> float:
    """Bien do tran theo san; san khong ro thi dung 0,07."""
    return LIMIT_BY_EXCHANGE.get((exchange or "").upper(), DEFAULT_LIMIT_RATE)


def is_ceiling_open(prev_close: float, next_open: float, exchange: str | None) -> bool:
    """Mo cua o gia tran: open >= close[truoc] x (1 + bien do - 0,001)."""
    return next_open >= prev_close * (1 + limit_rate(exchange) - LIMIT_EPS)


def entry_status(bars: list[Bar], t: int, exchange: str | None) -> str:
    """'ok' | 'ceiling' | 'zero_volume' | 'no_bar' — vao lenh tai open[t+1]."""
    if t + 1 >= len(bars):
        return "no_bar"
    nxt = bars[t + 1]
    if is_ceiling_open(bars[t].close, nxt.open, exchange):
        return "ceiling"
    if nxt.volume == 0:
        return "zero_volume"
    return "ok"


def net_return(entry_open: float, exit_close: float) -> float:
    """Loi nhuan rong (phi, thue, truot gia) — dung cac hang so import tu paper_broker."""
    s = SLIPPAGE_BPS / 10_000.0
    return (exit_close * (1 - FEE_RATE - SELL_TAX_RATE - s)) / (entry_open * (1 + FEE_RATE + s)) - 1.0


def compute_targets(bars: list[Bar], t: int, ks: tuple[int, ...] = TARGET_KS) -> dict[int, float | None]:
    """Loi nhuan GOP r_k = close[t+k] / open[t+1] - 1; None khi thieu nen."""
    out: dict[int, float | None] = {}
    if t + 1 >= len(bars):
        return dict.fromkeys(ks, None)
    entry = bars[t + 1].open
    for k in ks:
        out[k] = (bars[t + k].close / entry - 1.0) if (t + k < len(bars) and entry > 0) else None
    return out


# --- Doi chung cung ngay ----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ControlEntry:
    """Mot ma trong ro doi chung cua mot ngay (r = None nghia la khong du du lieu)."""

    symbol: str
    r5: float | None
    r10: float | None
    r20: float | None


def _r_of(entry: ControlEntry, k: int) -> float | None:
    return {5: entry.r5, 10: entry.r10, 20: entry.r20}[k]


def basket_baseline(entries: list[ControlEntry], k: int) -> tuple[float | None, int]:
    """(baseline_k, so ma trong ro) — chi tinh cac ma co r_k (du du lieu vao/thoat)."""
    vals = [v for v in (_r_of(e, k) for e in entries) if v is not None]
    if not vals:
        return None, len(entries)
    return sum(vals) / len(vals), len(vals)


def excess_for_event(
    r_event: float | None, entries: list[ControlEntry], k: int
) -> tuple[float | None, float | None, int]:
    """(baseline, excess, so ma trong ro). excess = None khi ro < MIN_CONTROL hoac thieu du lieu."""
    baseline, n = basket_baseline(entries, k)
    if r_event is None or baseline is None or n < MIN_CONTROL:
        return baseline, None, n
    return baseline, r_event - baseline, n


# --- Thong ke: bootstrap theo khoi thang ------------------------------------------

def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def bootstrap_by_month(
    by_month: dict[tuple[int, int], list[float]],
    n: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Bootstrap khoi THANG duong lich: lay mau lai cac thang co hoan lai, n lan, seed co dinh.

    p = ty le mau bootstrap co trung binh <= 0 (kiem mot phia: gia thuyet trung binh > 0).
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
        "ci_low": _percentile(means, CI_LOW_PCT),
        "ci_high": _percentile(means, CI_HIGH_PCT),
        "p": p,
        "n_months": len(months),
    }


# --- Du lieu theo ma ---------------------------------------------------------------

@dataclass(slots=True)
class SymbolData:
    """Chuoi mot ma + cac mang tinh truoc (SMAs, cua so 252 nen, thanh khoan)."""

    symbol: str
    exchange: str
    bars: list[Bar]
    closes: list[float]
    sma50: list[float | None]
    sma150: list[float | None]
    sma200: list[float | None]
    win_low: list[float | None]
    win_high: list[float | None]
    turnover20: list[float | None]

    @classmethod
    def build(cls, symbol: str, exchange: str, bars: list[Bar]) -> SymbolData:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        turnover = [b.close * b.volume for b in bars]
        return cls(
            symbol=symbol,
            exchange=exchange,
            bars=bars,
            closes=closes,
            sma50=rolling_mean(closes, 50),
            sma150=rolling_mean(closes, 150),
            sma200=rolling_mean(closes, 200),
            win_low=rolling_min(lows, RANGE_WINDOW),
            win_high=rolling_max(highs, RANGE_WINDOW),
            turnover20=rolling_mean(turnover, TURNOVER_WINDOW),
        )

    def trend_ok(self, t: int) -> bool:
        cond = trend_conditions(
            self.bars,
            t,
            sma50=self.sma50,
            sma150=self.sma150,
            sma200=self.sma200,
            win_low=self.win_low,
            win_high=self.win_high,
        )
        return all(cond.values())

    def liq_ok(self, t: int) -> bool:
        v = self.turnover20[t - 1] if t >= 1 else None
        return v is not None and v >= MIN_TURNOVER_VND

    def events(self) -> list[int]:
        return find_events(self.bars)


def compact_control_series(sd: SymbolData) -> tuple[array, array, array, array]:
    """Nen gon de tinh ro doi chung sau khi da bo het Bar khoi bo nho.

    Tra ve (ngay dang so ordinal, r5, r10, r20) voi NaN = khong lam doi chung duoc ngay do.
    """
    n = len(sd.bars)
    days = array("i", [0]) * n
    r5 = array("d", [math.nan]) * n
    r10 = array("d", [math.nan]) * n
    r20 = array("d", [math.nan]) * n
    for i in range(n):
        days[i] = bar_date(sd.bars[i]).toordinal()
        if not (sd.trend_ok(i) and sd.liq_ok(i)):
            continue
        if entry_status(sd.bars, i, sd.exchange) != "ok":
            continue
        tg = compute_targets(sd.bars, i, TARGET_KS)
        if tg[5] is None and tg[10] is None and tg[20] is None:
            continue
        if tg[5] is not None:
            r5[i] = tg[5]
        if tg[10] is not None:
            r10[i] = tg[10]
        if tg[20] is not None:
            r20[i] = tg[20]
    return days, r5, r10, r20


# --- Su kien va phep do ------------------------------------------------------------

@dataclass(slots=True)
class Event:
    symbol: str
    day: date
    exchange: str
    entry_open: float
    r: dict[int, float | None] = field(default_factory=dict)
    r_net: dict[int, float | None] = field(default_factory=dict)
    excess: dict[int, float | None] = field(default_factory=dict)


def load_universe(
    storage: Storage, exclude_file: str = "exclusions.txt"
) -> tuple[list[str], dict[str, str], int, set[str]]:
    """Danh sach ma co nen trong bars_daily, da loai ma hong; kem ban do san."""
    excluded: set[str] = set()
    p = pathlib.Path(exclude_file)
    if p.exists():
        excluded = {s.strip().upper() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()}
    with storage.conn() as c:
        all_syms = [r[0] for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")]
        exchange = {r[0]: (r[1] or "") for r in c.execute("SELECT symbol, exchange FROM symbol_universe")}
    n_all = len(all_syms)
    universe = [s for s in all_syms if s.upper() not in excluded]
    return universe, exchange, n_all, excluded


def run_screen(
    storage: Storage,
    exclude_file: str = "exclusions.txt",
    limit: int = 0,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Chay toan bo phep do (mot lan). Tra ve dict ket qua de in bao cao."""
    t0 = time.perf_counter()
    universe, exchange, n_all, excluded = load_universe(storage, exclude_file)
    if limit > 0:
        universe = universe[:limit]

    events: list[Event] = []
    store: list[tuple[str, array, array, array, array]] = []
    symbols_kept = 0
    n_junk = 0
    drop = defaultdict(int)

    for sym in universe:
        bars = storage.read_daily_bars(sym, READ_FROM, READ_TO)
        if not bars:
            continue
        validate_sealed_bars(bars)
        bars, junk = clean_bars(bars)
        n_junk += junk
        if len(bars) < TREND_MIN_BARS + 1:
            continue
        symbols_kept += 1
        ex = exchange.get(sym, "")
        sd = SymbolData.build(sym, ex, bars)
        for t in find_events(bars):
            d = bar_date(bars[t])
            if not in_is(d):
                continue
            st = entry_status(bars, t, ex)
            if st != "ok":
                drop[st] += 1
                continue
            tg = compute_targets(bars, t, TARGET_KS)
            entry_open = bars[t + 1].open
            ev = Event(
                symbol=sym,
                day=d,
                exchange=ex,
                entry_open=entry_open,
                r=tg,
                r_net={
                    k: (net_return(entry_open, bars[t + k].close) if tg.get(k) is not None else None)
                    for k in TARGET_KS
                },
            )
            for k in TARGET_KS:
                if tg.get(k) is None:
                    drop[f"thieu_du_lieu_{k}"] += 1
            events.append(ev)
        store.append((sym, *compact_control_series(sd)))

    read_done = time.perf_counter()

    # Ro doi chung: chi can cho cac NGAY co su kien
    event_day_ords = {e.day.toordinal() for e in events}
    control_by_day: dict[int, list[ControlEntry]] = defaultdict(list)
    for sym, days_ord, r5, r10, r20 in store:
        for i, od in enumerate(days_ord):
            if od not in event_day_ords:
                continue
            if math.isnan(r5[i]) and math.isnan(r10[i]) and math.isnan(r20[i]):
                continue
            control_by_day[od].append(
                ControlEntry(
                    symbol=sym,
                    r5=None if math.isnan(r5[i]) else r5[i],
                    r10=None if math.isnan(r10[i]) else r10[i],
                    r20=None if math.isnan(r20[i]) else r20[i],
                )
            )

    # Tính excess cho từng sự kiện
    for e in events:
        peers = [c for c in control_by_day.get(e.day.toordinal(), []) if c.symbol != e.symbol]
        e.excess = {}
        for k in TARGET_KS:
            _baseline, excess, _n = excess_for_event(e.r.get(k), peers, k)
            e.excess[k] = excess
            if excess is None:
                drop[f"ro_nho_{k}"] += 1

    stats = {k: _describe(events, k) for k in TARGET_KS}
    main_stats = stats[MAIN_K]
    by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
    for e in events:
        v = e.excess.get(MAIN_K)
        if v is not None:
            by_month[month_key(e.day)].append(v)
    boot = bootstrap_by_month(dict(by_month), n=n_bootstrap, seed=seed)

    n_valid = main_stats["n_excess"]
    ket_luan = _verdict(boot, main_stats, n_valid)
    total_excess = sum(
        v for v in (e.excess.get(MAIN_K) for e in events) if v is not None
    )
    top10 = sorted(
        (v for v in (e.excess.get(MAIN_K) for e in events) if v is not None), reverse=True
    )[:10]

    return {
        "n_all_symbols": n_all,
        "n_excluded": len(excluded),
        "n_universe": len(universe),
        "n_symbols_kept": symbols_kept,
        "n_junk_bars": n_junk,
        "events": events,
        "stats": stats,
        "drop": dict(drop),
        "boot": boot,
        "verdict": ket_luan,
        "n_valid_excess20": n_valid,
        "top10_share": (sum(top10) / total_excess) if total_excess else None,
        "seconds": time.perf_counter() - t0,
        "seconds_read": read_done - t0,
    }


def _describe(events: list[Event], k: int) -> dict[str, Any]:
    """Thong ke cho mot khung k: gop, rong, doi chung, vuot troi."""
    r = [v for v in (e.r.get(k) for e in events) if v is not None]
    rn = [v for v in (e.r_net.get(k) for e in events) if v is not None]
    ex = [v for v in (e.excess.get(k) for e in events) if v is not None]
    base: list[float] = []
    for e in events:
        rk = e.r.get(k)
        xk = e.excess.get(k)
        if rk is not None and xk is not None:
            base.append(rk - xk)
    return {
        "n": len(events),
        "n_r": len(r),
        "n_excess": len(ex),
        "mean_r": statistics.fmean(r) if r else None,
        "median_r": statistics.median(r) if r else None,
        "mean_r_net": statistics.fmean(rn) if rn else None,
        "median_r_net": statistics.median(rn) if rn else None,
        "mean_baseline": statistics.fmean(base) if base else None,
        "mean_excess": statistics.fmean(ex) if ex else None,
        "median_excess": statistics.median(ex) if ex else None,
        "share_excess_pos": (sum(1 for v in ex if v > 0) / len(ex)) if ex else None,
        "excess_vals": ex,
    }


def _verdict(boot: dict[str, Any], main_stats: dict[str, Any], n_valid: int) -> str:
    """Ket luan theo muc 1.7 cua brief."""
    if n_valid < MIN_EVENTS:
        return "IT_SU_KIEN — sức mạnh thấp (dưới 100 sự kiện hợp lệ), KHÔNG kết luận"
    p = boot["p"]
    if p is None or main_stats["mean_r_net"] is None or main_stats["median_excess"] is None:
        return "KHONG_DU_DU_LIEU"
    a = p < 0.05
    b = main_stats["mean_r_net"] > 0
    c = main_stats["median_excess"] > 0
    if a and b and c:
        return "CO_LOI_THE"
    return "KHONG_CO_LOI_THE"


def _fmt(v: float | None, spec: str = "+.4f") -> str:
    return "None" if v is None else format(v, spec)


def _pct(v: float | None, spec: str = "+.2%") -> str:
    return "None" if v is None else format(v, spec)


def print_report(res: dict[str, Any]) -> None:
    print("=== BÁO CÁO SÀNG LỌC VCP TRÊN CỔ PHIẾU VN, NẾN NGÀY (BRIEF ĐỢT 99) ===\n")
    print("[1] VŨ TRỤ MÃ")
    print(f"- Mã có nến trong bars_daily: {res['n_all_symbols']}")
    print(f"- Mã bị loại theo exclusions.txt: {res['n_excluded']}")
    print(f"- Vũ trụ sau khi loại: {res['n_universe']} mã")
    print(f"- Mã đủ độ dài để xét (>= {TREND_MIN_BARS + 1} nến): {res['n_symbols_kept']}")
    print(f"- Số nến rác bị bỏ (OHLC <= 0): {res['n_junk_bars']}")

    ev = res["events"]
    print(f"\n[2] SỰ KIỆN VCP TRONG IS ({IS_SIGNAL_START} -> {IS_SIGNAL_END})")
    print(f"- Tổng số sự kiện hợp lệ (đã vào được lệnh): {len(ev)}")
    by_year: dict[int, int] = defaultdict(int)
    by_ex: dict[str, int] = defaultdict(int)
    for e in ev:
        by_year[e.day.year] += 1
        by_ex[e.exchange or "(khong ro)"] += 1
    print(f"- Theo năm: {dict(sorted(by_year.items()))}")
    print(f"- Theo sàn: {dict(sorted(by_ex.items(), key=lambda kv: -kv[1]))}")
    d = res["drop"]
    print("- Số bị bỏ:")
    if not d:
        print("    (không có — 0 sự kiện bị bỏ vì trần, volume 0, thiếu dữ liệu hay rổ nhỏ)")
    for k in sorted(d):
        print(f"    {k}: {d[k]}")

    print("\n[3] THỐNG KÊ THEO KHUNG (đơn vị: lợi nhuận thập phân, không phải %)")
    print(
        f"{'k':<3} | {'n (có excess)':<13} | {'TB r_gộp':<10} | {'Trung vị r':<11} | "
        f"{'TB r_ròng':<10} | {'TB baseline':<12} | {'TB excess':<10} | {'Trung vị excess':<15} | "
        f"{'tỷ lệ excess>0':<14}"
    )
    print("-" * 130)
    for k in TARGET_KS:
        s = res["stats"][k]
        print(
            f"{k:<3} | {s['n_excess']:<13} | {_fmt(s['mean_r']):<10} | {_fmt(s['median_r']):<11} | "
            f"{_fmt(s['mean_r_net']):<10} | {_fmt(s['mean_baseline']):<12} | "
            f"{_fmt(s['mean_excess']):<10} | {_fmt(s['median_excess']):<15} | "
            f"{_pct(s['share_excess_pos']):<14}"
        )

    boot = res["boot"]
    print(f"\n[4] PHÉP THỬ CHÍNH (k = {MAIN_K}, một phía, bootstrap theo khối tháng)")
    print(f"- Số tháng dùng làm khối: {boot['n_months']}")
    print(f"- Số sự kiện có excess_{MAIN_K}: {res['n_valid_excess20']}")
    print(f"- Trung bình excess_{MAIN_K}: {_fmt(boot['mean'])}")
    print(f"- KTC 95% (bootstrap): [{_fmt(boot['ci_low'])}, {_fmt(boot['ci_high'])}]")
    print(f"- p (tỷ lệ mẫu bootstrap có trung bình <= 0): {_fmt(boot['p'], '.4f')}")
    s = res["stats"][MAIN_K]
    print(f"- (a) p < 0,05: {boot['p'] is not None and boot['p'] < 0.05}")
    print(f"- (b) trung bình r_{MAIN_K}_ròng > 0: {s['mean_r_net'] is not None and s['mean_r_net'] > 0} ({_fmt(s['mean_r_net'])})")
    print(f"- (c) trung vị excess_{MAIN_K} > 0: {s['median_excess'] is not None and s['median_excess'] > 0} ({_fmt(s['median_excess'])})")

    print("\n[5] KIỂM ĐỘ LỆCH")
    share = res["top10_share"]
    print(f"- Tỷ trọng của 10 sự kiện excess_{MAIN_K} lớn nhất trong tổng: {_pct(share)}")
    if share is not None and share > 0.5:
        print("  => 10 sự kiện lớn nhất chiếm HƠN 50% tổng excess: kết quả phụ thuộc vài cú tăng cực lớn.")

    print("\n[6] THỜI GIAN CHẠY")
    print(f"- Tổng: {res['seconds']:.1f}s (đọc dữ liệu: {res['seconds_read']:.1f}s)")

    print("\n=== KẾT LUẬN (theo mục 4 của brief) ===")
    v = res["verdict"]
    if v == "CO_LOI_THE":
        print("- ĐẠT cả ba điều kiện §1.7: VCP có lợi thế so với cổ phiếu cùng xu hướng, sau chi phí.")
        print("  KHÔNG mở tập từ 2023, KHÔNG xây chiến lược. Chờ Claude quyết (mở một lần duy nhất).")
    elif v.startswith("IT_SU_KIEN"):
        print(f"- {v}")
    else:
        print("- KHÔNG đạt §1.7 -> VCP dạng máy: KHÔNG có lợi thế so với cổ phiếu cùng xu hướng, sau chi phí.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sàng lọc VCP trên cổ phiếu VN nến ngày (Brief đợt 99)")
    ap.add_argument("--dsn", default=None, help="DSN Postgres (mặc định lấy từ .env)")
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số mã (0 = tất cả)")
    args = ap.parse_args()

    storage = Storage(resolve_dsn(args.dsn))
    res = run_screen(storage, exclude_file=args.exclude_file, limit=args.limit)
    print_report(res)


if __name__ == "__main__":
    main()
