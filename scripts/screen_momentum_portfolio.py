"""Momentum danh muc tren co phieu VN (12-1 thang, giu 1 thang) — Brief dot 102.

Thiet ke DANG KY TRUOC (moi tham so chot trong brief, khong doi sau khi thay du lieu):
- Nguon: `bars_daily` qua Storage.read_daily_bars; ngay cua nen theo GIO VN (`bar_date`).
- Niem phong: doc toi 2022-12-31; nen tu 2023-01-01 (gio VN) thi NEM LOI (dung
  `validate_sealed_bars` cua scripts/screen_vcp_daily.py).
- Chi lay ma co PHIEU: dung 3 ky tu, moi ky tu la chu IN HOA hoac chu so
  (L14/VC3/D2D duoc GIU; ETF E1VFVN30, chung quyen CHPG2301 bi loai).
- Ngay xep hang F = phien giao dich CUOI CUNG cua thang duong lich, lay tu CHINH du lieu
  (ngay lon nhat co nen cua BAT KY ma nao trong thang).
- Dieu kien duoc xep hang tai F: co nen tai F; trung binh close x volume cua 20 nen
  KET THUC tai F >= 1 ty (goi `liquidity_ok(bars, i_F + 1)`); co nen o chi so i_F - 252 va
  i_F - 21; ngay cua nen i_F - 252 khong som hon F - 400 ngay lich.
- Diem momentum: `close[i_F - 21] / close[i_F - 252] - 1` (bo 21 phien gan nhat).
- Danh muc WIN = 10% mom cao nhat (lam tron LEN, toi thieu 10 ma); EW = TOAN BO ma du
  dieu kien; LOSE = 10% thap nhat (chi de mo ta). Duoi 100 ma du dieu kien -> bo thang.
- Giu thang ke tiep: vao tai open phien DAU (cua ma do trong thang giu), ra tai close
  phien CUOI (cua ma do trong thang giu). Ma mo cua gia tran phien vao -> loai khoi danh
  muc thang do, KHONG thay bang ma khac.
- Chi phi: net = gross - turnover(M) x cost_rt, cost_rt = 2 x FEE_RATE + SELL_TAX_RATE
  + 2 x SLIPPAGE_BPS/10.000 (HANG SO IMPORT tu trading/paper_broker.py).
- Phep thu chinh: excess(M) = net_WIN(M) - net_EW(M); bootstrap theo KHOI 3 THANG LIEN NHAU
  (2.000 lan, seed 42); CO LOI THE khi p < 0,05 VA TB net_WIN > 0 VA trung vi excess > 0.

Khong dung pandas/numpy (repo khong co).
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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ
from trading.metrics import calculate_percentile
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import (
    bar_date,
    clean_bars,
    is_ceiling_open,
    liquidity_ok,
    load_universe,
    validate_sealed_bars,
)
from trading.storage.db import Storage

__all__ = ["bar_date", "main", "run_screen"]

# --- Tham so dang ky truoc ---------------------------------------------------------

MOM_LOOKBACK = 252            # 12 thang phien
MOM_SKIP = 21                 # bo ~1 thang gan nhat
HISTORY_MAX_GAP_DAYS = 400    # ngay cua nen i_F-252 khong som hon F - 400 ngay
MIN_TURNOVER_VND = 1_000_000_000.0
TURNOVER_WINDOW = 20          # cua so thanh khoan (khop liquidity_ok)
WIN_FRACTION = 0.10
MIN_WIN_SIZE = 10
MIN_UNIVERSE_FOR_MONTH = 100
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 42
BLOCK_MONTHS = 3
MIN_MONTHS = 60
ALPHA = 0.05
CI_LOW_PCT = 2.5
CI_HIGH_PCT = 97.5

SEALED_START = date(2023, 1, 1)
RANK_START = date(2016, 12, 30)
RANK_END = date(2022, 11, 30)
ETF_SYMBOL = "E1VFVN30"
ETF_FIRST_MONTH = (2017, 1)
ETF_LAST_MONTH = (2022, 12)
READ_FROM = datetime(2016, 1, 1, tzinfo=TZ)
READ_TO = datetime(2023, 1, 1, tzinfo=TZ)

STOCK_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

# --- Ma co phieu ------------------------------------------------------------------

def is_stock_symbol(sym: str) -> bool:
    """Dung 3 ky tu, moi ky tu la chu IN HOA hoac chu so (ETF/chung quyen bi loai)."""
    return len(sym) == 3 and all(c in STOCK_CHARS for c in sym)


def stock_symbols(universe: Sequence[str]) -> tuple[list[str], list[str]]:
    """Chia vu tru thanh (giu, loai) theo quy tac ma co phieu."""
    kept = [s for s in universe if is_stock_symbol(s)]
    dropped = [s for s in universe if not is_stock_symbol(s)]
    return kept, dropped


# --- Thoi gian --------------------------------------------------------------------

def month_key_of(d: date) -> tuple[int, int]:
    """Khoa thang duong lich cua mot ngay (gio VN): (nam, thang)."""
    return (d.year, d.month)


def next_month_key(mk: tuple[int, int]) -> tuple[int, int]:
    """Thang ke tiep cua mot khoa thang."""
    y, m = mk
    return (y + 1, 1) if m == 12 else (y, m + 1)


def last_session_by_month(dates: Iterable[date]) -> dict[tuple[int, int], date]:
    """Ngay giao dich CUOI CUNG cua moi thang: ngay lon nhat co nen trong thang do."""
    out: dict[tuple[int, int], date] = {}
    for d in dates:
        mk = month_key_of(d)
        cur = out.get(mk)
        if cur is None or d > cur:
            out[mk] = d
    return out


@dataclass(slots=True)
class Span:
    """Khoang chi so cua mot ma trong mot thang (theo chuoi nen cua chinh ma do)."""

    first: int
    last: int
    last_date: date


def month_spans(bars: list[Bar]) -> dict[tuple[int, int], Span]:
    """Voi tung thang: (chi so nen dau, chi so nen cuoi, ngay nen cuoi) cua ma nay."""
    out: dict[tuple[int, int], Span] = {}
    for i, b in enumerate(bars):
        d = bar_date(b)
        mk = month_key_of(d)
        sp = out.get(mk)
        if sp is None:
            out[mk] = Span(first=i, last=i, last_date=d)
        else:
            sp.last = i
            sp.last_date = d
    return out


def read_symbol_bars(
    storage: Any, symbol: str, read_from: datetime = READ_FROM, read_to: datetime = READ_TO
) -> tuple[list[Bar], int]:
    """Doc nen cua mot ma, KIEM NIEM PHONG roi bo nen OHLC <= 0. Tra ve (nen, so nen rac)."""
    bars = storage.read_daily_bars(symbol, read_from, read_to)
    if not bars:
        return [], 0
    validate_sealed_bars(bars)
    return clean_bars(bars)


# --- Xep hang ---------------------------------------------------------------------

def eligible_at(
    bars: list[Bar], i_f: int, f_date: date, min_turnover: float = MIN_TURNOVER_VND
) -> str:
    """Ly do du / khong du dieu kien xep hang tai F (nguoi goi bao dam bars[i_f] la phien F).

    'ok' | 'thieu_du_lieu' | 'thieu_thanh_khoan' | 'lich_su_gian_doan'
    """
    if i_f - MOM_LOOKBACK < 0 or i_f - MOM_SKIP < 0:
        return "thieu_du_lieu"
    if not liquidity_ok(bars, i_f + 1, window=TURNOVER_WINDOW, min_turnover=min_turnover):
        return "thieu_thanh_khoan"
    if bar_date(bars[i_f - MOM_LOOKBACK]) < f_date - timedelta(days=HISTORY_MAX_GAP_DAYS):
        return "lich_su_gian_doan"
    return "ok"


def momentum_at(bars: list[Bar], i_f: int) -> float:
    """mom = close[i_F - 21] / close[i_F - 252] - 1 (nem IndexError neu thieu lich su)."""
    if i_f - MOM_LOOKBACK < 0 or i_f - MOM_SKIP < 0:
        raise IndexError(f"khong du {MOM_LOOKBACK} phien lich su de tinh momentum tai i_f={i_f}")
    return bars[i_f - MOM_SKIP].close / bars[i_f - MOM_LOOKBACK].close - 1


def win_size(n_eligible: int) -> int:
    """Co danh muc WIN: 10% lam tron LEN, toi thieu 10 ma."""
    return max(MIN_WIN_SIZE, math.ceil(n_eligible * WIN_FRACTION))


def month_usable(n_eligible: int) -> bool:
    """Thang chi duoc dung khi co it nhat 100 ma du dieu kien."""
    return n_eligible >= MIN_UNIVERSE_FOR_MONTH


def win_members(moms: Mapping[str, float]) -> list[str]:
    """Nhom mom cao nhat (WIN)."""
    size = min(win_size(len(moms)), len(moms))
    return sorted(moms, key=lambda s: (-moms[s], s))[:size]


def lose_members(moms: Mapping[str, float]) -> list[str]:
    """Nhom mom thap nhat (LOSE) — chi de mo ta."""
    size = min(win_size(len(moms)), len(moms))
    return sorted(moms, key=lambda s: (moms[s], s))[:size]


# --- Thang giu, chi phi -----------------------------------------------------------

def hold_return(bars: list[Bar], i_entry: int, i_exit: int, exchange: str | None) -> tuple[float | None, str]:
    """Loi nhuan gop cua ma trong thang giu: close[i_exit]/open[i_entry] - 1.

    'ok' | 'ceiling' (mo cua gia tran -> khong mua duoc) | 'thieu_nen'.
    Neu i_entry = 0 thi khong co phien truoc do de so tran -> coi la mua duoc.
    """
    if i_entry < 0 or i_exit < 0 or i_entry >= len(bars) or i_exit >= len(bars):
        return None, "thieu_nen"
    if i_entry > 0 and is_ceiling_open(bars[i_entry - 1].close, bars[i_entry].open, exchange):
        return None, "ceiling"
    return bars[i_exit].close / bars[i_entry].open - 1, "ok"


def month_members_returns(
    members: Sequence[str], ret_by_sym: Mapping[str, tuple[float | None, str]]
) -> tuple[dict[str, float], dict[str, int]]:
    """Loc ma MUA DUOC cua mot danh muc trong thang: ma mo tran / thieu nen bi LOAI.

    KHONG thay bang ma khac — tra ve (r cua tung ma giu duoc, so lan bi loai theo ly do).
    """
    held: dict[str, float] = {}
    drop: dict[str, int] = defaultdict(int)
    for sym in members:
        r, why = ret_by_sym.get(sym, (None, "thieu_nen"))
        if why == "ok" and r is not None:
            held[sym] = r
        else:
            drop[why] += 1
    return held, dict(drop)


def portfolio_gross(held: Mapping[str, float]) -> float | None:
    """Loi nhuan gop cua danh muc = trung binh deu ty trong; rong thi None."""
    if not held:
        return None
    return sum(held.values()) / len(held)


def turnover(prev_members: Sequence[str] | None, cur_members: Sequence[str]) -> float:
    """Ty le ma cua thang nay KHONG co trong thang truoc (thang dau = 1,0)."""
    if not cur_members:
        return 0.0
    if not prev_members:
        return 1.0
    prev = set(prev_members)
    return sum(1 for s in cur_members if s not in prev) / len(cur_members)


def round_trip_cost() -> float:
    """cost_rt = 2 x phi + thue ban + 2 x truot gia (hang so IMPORT tu paper_broker)."""
    return 2 * FEE_RATE + SELL_TAX_RATE + 2 * SLIPPAGE_BPS / 10_000


def net_month(gross: float, turn: float, cost_rt: float) -> float:
    """net = gross - turnover x cost_rt."""
    return gross - turn * cost_rt


# --- Thong ke ---------------------------------------------------------------------

def cagr(monthly_net: Sequence[float]) -> float | None:
    """Loi nhuan kep nam (CAGR) tu chuoi loi nhuan RONG theo thang."""
    n = len(monthly_net)
    if n == 0:
        return None
    acc = 1.0
    for r in monthly_net:
        acc *= 1 + r
    if acc <= 0:
        return -1.0
    return acc ** (12 / n) - 1


def max_drawdown(monthly_net: Sequence[float]) -> float:
    """Do sut von lon nhat (so duong) cua duong von tu chuoi loi nhuan rong theo thang."""
    peak = 1.0
    equity = 1.0
    worst = 0.0
    for r in monthly_net:
        equity *= 1 + r
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    return worst


def share_positive(values: Sequence[float]) -> float:
    """Ty le gia tri > 0 (0,0 khong tinh la duong)."""
    if not values:
        return 0.0
    return sum(1 for v in values if v > 0) / len(values)


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


# --- Bootstrap theo KHOI thang lien nhau ------------------------------------------

def block_samples(
    series: Sequence[float],
    block: int = BLOCK_MONTHS,
    rng: random.Random | None = None,
    n_boot: int = N_BOOTSTRAP,
) -> list[list[float]]:
    """n_boot mau, moi mau gom cac KHOI `block` thang LIEN NHAU lay co hoan lai.

    Moi khoi bat dau tai mot chi so bat ky trong chuoi va gom `block` gia tri lien tiep;
    lay them khoi cho toi khi du do dai chuoi roi cat dung bang do dai chuoi.
    """
    if rng is None:
        rng = random.Random(BOOTSTRAP_SEED)
    n = len(series)
    if n == 0:
        return [[] for _ in range(n_boot)]
    starts = list(range(max(1, n - block + 1)))
    out: list[list[float]] = []
    for _ in range(n_boot):
        sample: list[float] = []
        while len(sample) < n:
            s0 = rng.choice(starts)
            sample.extend(series[s0 : s0 + block])
        out.append(sample[:n])
    return out


def block_bootstrap(
    series: Sequence[float],
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    block: int = BLOCK_MONTHS,
) -> dict[str, Any]:
    """Trung binh / trung vi cua chuoi, KTC 95% va p mot phia theo bootstrap khoi lien nhau."""
    rng = random.Random(seed)
    samples = block_samples(series, block, rng, n_boot)
    means = [statistics.fmean(s) if s else 0.0 for s in samples]
    means_sorted = sorted(means)
    p = sum(1 for m in means if m <= 0) / len(means) if means else 1.0
    return {
        "mean": _mean(series),
        "median": _median(series),
        "p": p,
        "ci_low": calculate_percentile(means_sorted, CI_LOW_PCT),
        "ci_high": calculate_percentile(means_sorted, CI_HIGH_PCT),
        "n_boot": n_boot,
        "block": block,
        "n_months": len(series),
    }


# --- Danh muc ETF (chi de mo ta) --------------------------------------------------

def etf_buy_hold(
    storage: Any,
    cost_rt: float | None = None,
    symbol: str = ETF_SYMBOL,
    first_month: tuple[int, int] = ETF_FIRST_MONTH,
    last_month: tuple[int, int] = ETF_LAST_MONTH,
) -> dict[str, Any]:
    """Mua va giu ETF tu open phien dau thang dau toi close phien cuoi thang cuoi, tru 1 vong chi phi."""
    bars, _ = read_symbol_bars(storage, symbol)
    if not bars:
        return {"ok": False, "symbol": symbol}
    sp = month_spans(bars)
    a, z = sp.get(first_month), sp.get(last_month)
    if a is None or z is None:
        return {"ok": False, "symbol": symbol}
    gross = bars[z.last].close / bars[a.first].open - 1
    net = gross - (round_trip_cost() if cost_rt is None else cost_rt)
    n_months = (last_month[0] - first_month[0]) * 12 + (last_month[1] - first_month[1]) + 1
    return {
        "ok": True,
        "symbol": symbol,
        "gross": gross,
        "net": net,
        "n_months": n_months,
        "cagr": cagr([net]) if n_months == 12 else ((1 + net) ** (12 / n_months) - 1),
    }


# --- Chay phep do ----------------------------------------------------------------

@dataclass(slots=True)
class MonthRow:
    """Mot thang duoc dung: thang xep hang, ngay F, co danh muc, ket qua tung danh muc."""

    mk: tuple[int, int]
    f_date: date
    n_eligible: int
    gross: dict[str, float] = field(default_factory=dict)
    net: dict[str, float] = field(default_factory=dict)
    turn: dict[str, float] = field(default_factory=dict)
    held_n: dict[str, int] = field(default_factory=dict)


PORTFOLIOS = ("WIN", "EW", "LOSE")


def run_screen(
    storage: Any,
    exclude_file: str = "exclusions.txt",
    limit: int = 0,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Chay toan bo phep do (MOT lan). Tra ve dict ket qua de in bao cao."""
    t0 = time.perf_counter()
    universe, exchange, n_all, excluded = load_universe(storage, exclude_file)
    kept, non_stock = stock_symbols(universe)
    if limit > 0:
        kept = kept[:limit]

    # --- LUOT 1: khoang thang cua tung ma + lich giao dich (ngay cuoi thang) ---
    spans: dict[str, dict[tuple[int, int], Span]] = {}
    last_by_month: dict[tuple[int, int], date] = {}
    n_junk = 0
    n_syms_with_bars = 0
    t_read1 = 0.0
    for sym in kept:
        t1 = time.perf_counter()
        bars, junk = read_symbol_bars(storage, sym)
        t_read1 += time.perf_counter() - t1
        n_junk += junk
        if not bars:
            continue
        n_syms_with_bars += 1
        sp = month_spans(bars)
        spans[sym] = sp
        for mk, s in sp.items():
            cur = last_by_month.get(mk)
            if cur is None or s.last_date > cur:
                last_by_month[mk] = s.last_date

    rank_months = [mk for mk in sorted(last_by_month) if RANK_START <= last_by_month[mk] <= RANK_END]
    rank_set = set(rank_months)

    # --- LUOT 2: doc lai, tinh mom tai F va loi nhuan thang giu ---
    moms: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    hrets: dict[tuple[int, int], dict[str, tuple[float | None, str]]] = defaultdict(dict)
    reasons: dict[str, int] = defaultdict(int)
    for sym in kept:
        bars, _ = read_symbol_bars(storage, sym)
        if not bars:
            continue
        sp = spans[sym]
        ex = exchange.get(sym, "")
        for mk in rank_set:
            s = sp.get(mk)
            if s is not None and s.last_date == last_by_month[mk]:
                why = eligible_at(bars, s.last, s.last_date)
                if why == "ok":
                    moms[mk][sym] = momentum_at(bars, s.last)
                else:
                    reasons[why] += 1
            hs = sp.get(next_month_key(mk))
            if hs is not None:
                hrets[mk][sym] = hold_return(bars, hs.first, hs.last, ex)

    # --- Dung danh muc tung thang ---
    cost_rt = round_trip_cost()
    rows: list[MonthRow] = []
    n_skip_small = 0
    n_skip_empty = 0
    drop_by: dict[str, dict[str, int]] = {name: defaultdict(int) for name in PORTFOLIOS}
    prev: dict[str, list[str]] = {}
    elig_counts: list[int] = []
    for mk in rank_months:
        m = moms.get(mk, {})
        n_elig = len(m)
        elig_counts.append(n_elig)
        if not month_usable(n_elig):
            n_skip_small += 1
            continue
        groups = {"WIN": win_members(m), "EW": sorted(m), "LOSE": lose_members(m)}
        held_by: dict[str, dict[str, float]] = {}
        for name, members in groups.items():
            held, drop = month_members_returns(members, hrets.get(mk, {}))
            for k, v in drop.items():
                drop_by[name][k] += v
            held_by[name] = held
        if not held_by["WIN"] or not held_by["EW"]:
            n_skip_empty += 1
            continue
        row = MonthRow(mk=mk, f_date=last_by_month[mk], n_eligible=n_elig)
        for name, held in held_by.items():
            g = portfolio_gross(held)
            if g is None:
                continue  # danh muc rong: khong co loi nhuan thang nay (WIN/EW da loai tu truoc)
            t = turnover(prev.get(name), list(held))
            row.gross[name] = g
            row.turn[name] = t
            row.net[name] = net_month(g, t, cost_rt)
            row.held_n[name] = len(held)
            prev[name] = list(held)
        rows.append(row)

    # --- Thong ke ---
    def col(name: str, key: str) -> list[float]:
        return [getattr(r, key)[name] for r in rows if name in getattr(r, key)]

    stats: dict[str, dict[str, Any]] = {}
    for name in PORTFOLIOS:
        g, nt = col(name, "gross"), col(name, "net")
        stats[name] = {
            "n_months": len(nt),
            "mean_gross": _mean(g),
            "median_gross": _median(g),
            "mean_net": _mean(nt),
            "median_net": _median(nt),
            "cagr": cagr(nt),
            "max_dd": max_drawdown(nt),
            "share_pos": share_positive(nt),
            "mean_turn": _mean(col(name, "turn")),
        }

    excess = [r.net["WIN"] - r.net["EW"] for r in rows]
    boot = block_bootstrap(excess, n_boot=n_bootstrap, seed=seed)
    win_lose = [r.net["WIN"] - r.net["LOSE"] for r in rows]

    yearly: dict[int, list[float]] = defaultdict(list)
    yearly_ew: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        y = next_month_key(r.mk)[0]
        yearly[y].append(r.net["WIN"])
        yearly_ew[y].append(r.net["EW"])

    cond_a = boot["p"] < ALPHA
    cond_b = stats["WIN"]["mean_net"] is not None and stats["WIN"]["mean_net"] > 0
    cond_c = boot["median"] is not None and boot["median"] > 0
    if len(rows) < MIN_MONTHS:
        verdict = "IT_THANG"
    else:
        verdict = "CO_LOI_THE" if (cond_a and cond_b and cond_c) else "KHONG_CO_LOI_THE"

    return {
        "n_all": n_all,
        "n_excluded": len(excluded),
        "n_universe": len(universe),
        "n_non_stock": len(non_stock),
        "non_stock_sample": sorted(non_stock)[:20],
        "n_stock": len(kept),
        "n_syms_with_bars": n_syms_with_bars,
        "n_junk": n_junk,
        "n_months_rank": len(rank_months),
        "n_months_used": len(rows),
        "n_skip_small": n_skip_small,
        "n_skip_empty": n_skip_empty,
        "elig_min": min(elig_counts) if elig_counts else 0,
        "elig_median": _median(elig_counts),
        "elig_max": max(elig_counts) if elig_counts else 0,
        "win_sizes": [r.held_n["WIN"] for r in rows],
        "first_month": rank_months[0] if rank_months else None,
        "last_month": rank_months[-1] if rank_months else None,
        "reasons": dict(reasons),
        "drop_by": {k: dict(v) for k, v in drop_by.items()},
        "stats": stats,
        "excess": boot,
        "excess_mean_check": _mean(excess),
        "win_lose_mean": _mean(win_lose),
        "win_lose_share_pos": share_positive(win_lose),
        "yearly_win": {y: _mean(v) for y, v in sorted(yearly.items())},
        "yearly_ew": {y: _mean(v) for y, v in sorted(yearly_ew.items())},
        "etf": etf_buy_hold(storage, cost_rt),
        "cost_rt": cost_rt,
        "cond_a": cond_a,
        "cond_b": cond_b,
        "cond_c": cond_c,
        "verdict": verdict,
        "seconds": time.perf_counter() - t0,
        "seconds_read1": t_read1,
    }


# --- In bao cao -----------------------------------------------------------------

def _fmt(v: float | None, spec: str = "+.4f") -> str:
    return "n/a" if v is None else format(v, spec)


def _pct(v: float | None, spec: str = "+.2%") -> str:
    return "n/a" if v is None else format(v, spec)


def print_report(res: dict[str, Any]) -> None:
    """In bao cao theo muc 4 cua brief."""
    print("=== MOMENTUM DANH MUC CO PHIEU VN 12-1 THANG (BRIEF DOT 102) ===\n")
    print("[1] VU TRU MA")
    print(f"- Ma co nen trong bars_daily: {res['n_all']}")
    print(f"- Loai theo exclusions.txt: {res['n_excluded']}")
    print(f"- Loai vi KHONG phai ma co phieu 3 ky tu: {res['n_non_stock']}")
    print(f"- 20 ma bi loai dau tien: {', '.join(res['non_stock_sample'])}")
    print(f"- Vu tru sau khi loc (ma co phieu): {res['n_stock']}; co nen doc duoc: {res['n_syms_with_bars']}")
    print(f"- So nen rac bi bo (OHLC <= 0): {res['n_junk']}")
    months_used = res["first_month"], res["last_month"]
    print(f"- Thang xep hang dung duoc: {res['n_months_used']} (tu {months_used[0]} den {months_used[1]})\n")

    print("[2] THANG")
    print(f"- So thang trong cua so dang ky: {res['n_months_rank']}")
    print(f"- Bo vi duoi 100 ma du dieu kien: {res['n_skip_small']}")
    print(f"- Bo vi danh muc rong: {res['n_skip_empty']}")
    print(
        f"- So ma du dieu kien moi thang: nho nhat {res['elig_min']}, "
        f"trung vi {_fmt(res['elig_median'], '.1f').lstrip('+')}, lon nhat {res['elig_max']}"
    )
    ws = res["win_sizes"]
    print(f"- Co WIN moi thang: nho nhat {min(ws) if ws else 0}, lon nhat {max(ws) if ws else 0}")
    print(f"- Ly do khong du dieu kien: {res['reasons']}\n")

    print("[3] DANH MUC (loi nhuan thang, thap phan)")
    head = f"{'danh muc':8} | {'n':>3} | {'TB gop':>8} | {'TV gop':>8} | {'TB rong':>8} | {'TV rong':>8} | {'CAGR':>8} | {'MaxDD':>7} | {'%>0':>6} | {'vong quay':>9}"
    print(head)
    for name in PORTFOLIOS:
        s = res["stats"][name]
        print(
            f"{name:8} | {s['n_months']:>3} | {_fmt(s['mean_gross']):>8} | {_fmt(s['median_gross']):>8} | "
            f"{_fmt(s['mean_net']):>8} | {_fmt(s['median_net']):>8} | {_pct(s['cagr']):>8} | "
            f"{_pct(s['max_dd']):>7} | {_pct(s['share_pos'], '.1%'):>6} | {_fmt(s['mean_turn'], '.3f'):>9}"
        )
    print()

    print("[4] ETF MUA VA GIU (mo ta)")
    etf = res["etf"]
    if etf.get("ok"):
        print(
            f"- {etf['symbol']}: gop {_pct(etf['gross'])}, rong {_pct(etf['net'])}, "
            f"CAGR rong {_pct(etf['cagr'])} ({etf['n_months']} thang)"
        )
    else:
        print("- Khong doc duoc du lieu ETF")
    print()

    print("[5] CHENH WIN - LOSE (mo ta)")
    print(f"- Trung binh thang: {_fmt(res['win_lose_mean'])}")
    print(f"- Ty le thang duong: {_pct(res['win_lose_share_pos'], '.1%')}\n")

    print("[6] PHEP THU CHINH (excess = net_WIN - net_EW)")
    b = res["excess"]
    print(f"- So thang: {b['n_months']}; khoi {b['block']} thang lien nhau; {b['n_boot']} lan bootstrap")
    print(f"- Trung binh excess: {_fmt(b['mean'])}")
    print(f"- KTC 95%: [{_fmt(b['ci_low'])}, {_fmt(b['ci_high'])}]")
    print(f"- p (ty le mau co trung binh <= 0): {b['p']:.4f}")
    print(f"- Trung vi excess: {_fmt(b['median'])}")
    print(f"- (a) p < 0,05: {res['cond_a']}   (b) TB net_WIN > 0: {res['cond_b']}   (c) trung vi excess > 0: {res['cond_c']}")
    print(f"- => {res['verdict']}\n")

    print("[7] THEO NAM (thang giu) - loi nhuan RONG trung binh")
    print(f"{'nam':>6} | {'WIN':>9} | {'EW':>9}")
    for y in sorted(res["yearly_win"]):
        print(f"{y:>6} | {_fmt(res['yearly_win'][y]):>9} | {_fmt(res['yearly_ew'][y]):>9}")
    print()

    print("[8] SO LAN LOAI VA THOI GIAN")
    for name in PORTFOLIOS:
        print(f"- {name}: {res['drop_by'][name]}")
    print(f"- Chi phi mot vong: {_fmt(res['cost_rt'], '.4f')}")
    print(f"- Thoi gian: {res['seconds']:.1f}s (doc du lieu luot 1: {res['seconds_read1']:.1f}s)")
    print()
    print("=== KET LUAN ===")
    if res["verdict"] == "CO_LOI_THE":
        print("- CO LOI THE theo muc 1.6 cua brief. KHONG mo tap tu 2023, KHONG xay chien luoc.")
    elif res["verdict"] == "IT_THANG":
        print("- IT_THANG: duoi 60 thang hop le -> khong ket luan.")
    else:
        print(
            "- Momentum 12-1 danh muc thang: KHONG vuot duoc mua-deu co phieu du thanh khoan, "
            "sau chi phi."
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Momentum danh muc co phieu VN 12-1 thang (Brief dot 102)")
    ap.add_argument("--dsn", default=None, help="DSN Postgres (mac dinh lay tu .env)")
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--limit", type=int, default=0, help="Gioi han so ma (0 = tat ca)")
    args = ap.parse_args()

    storage = Storage(resolve_dsn(args.dsn))
    res = run_screen(storage, exclude_file=args.exclude_file, limit=args.limit)
    print_report(res)


if __name__ == "__main__":
    main()
