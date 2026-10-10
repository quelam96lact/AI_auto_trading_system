"""Pullback trong xu huong, giu 2-4 tuan, co phieu VN nen ngay — Brief dot 173.

THIET KE DANG KY TRUOC (chot trong brief, KHONG doi sau khi thay so):
- Universe: `bars_daily` qua `load_universe(storage, "exclusions.txt")`, chi ma co phieu
  (`stock_symbols` cua screen_momentum_portfolio). Bo nen gia <= 0 (`clean_bars`). Ngay theo
  gio VN (`bar_date`). KHONG dung ma da huy niem yet — va chi so voi thi truong CUNG universe.
- Niem phong: doc toi 31/12/2022; nen tu 01/01/2023 thi NEM LOI (`validate_sealed_bars`).
  IS = moi tin hieu co ngay tin hieu trong 2017-01-01 -> 2022-11-30 (2016 chi de lam nong MA200).
- Tin hieu mua (tai CLOSE phien t, chi dung du lieu <= t), du ca nam dieu kien:
  1. thanh khoan: trung binh close x volume 20 phien >= 2 ty (`liquidity_ok`);
  2. close[t] > MA200[t] VA MA50[t] > MA200[t];
  3. H20 = close cao nhat trong 20 phien ket thuc tai t-1; do sau 1 - min(close[t-5..t-1])/H20
     nam trong [5%, 15%];
  4. bat len: close[t] > high[t-1];
  5. khong dang giu ma do.
- Vao lenh: mua o OPEN phien t+1, `entry_status` khac "ok" thi BO (khong thay ma khac). E = t+1.
- Thoat: kiem tai CLOSE moi phien d >= E, thoat o CLOSE phien d+1 (theo thu tu: cat lo
  close[d] <= open[E]*0,92; chot loi close[d] >= H20; het gio d = E+19). T+2: phien thoat
  khong som hon E+2. Thoat roi vao nen khong giao dich (volume 0) thi lui tiep.
  Loi nhuan lenh = `net_return(open[E], close[exit])`.
- Moc so sanh: EW_ret(d) = trung binh cong close[d]/close[d-1]-1 cua moi ma du dieu kien
  thanh khoan o phien d; moc cua lenh = tich(1+EW_ret(d)) - 1, d tu E toi phien thoat, KHONG tru phi.
  Vuot troi = loi nhuan rong - moc.
- Phep thu: gom lenh theo thang vao lenh, moi thang lay trung binh vuot troi; `block_bootstrap`
  khoi 3 thang, 2.000 lan, seed 42 (ham cua screen_momentum_portfolio). DAT khi ca bon:
  >=300 lenh; p < 0,05 mot phia VA trung binh vuot troi > 0; trung binh loi nhuan rong moi lenh
  >= 0,5*cost_rt; profit factor rong > 1,2. Duoi 300 lenh: THIEU SUC MANH.

CHO BRIEF MO HO (tu dien giai, khong im lang chon):
- §1.2 dieu kien 1 ghi "20 phien KET THUC TAI t" nhung `liquidity_ok(bars, t)` lai tinh 20 phien
  TRUOC t (t-20..t-1). Brief chot dung `liquidity_ok` nen o day dung nguyen ham do, khong keo
  cua so dich di mot phien.
- §1.4 ghi "thoat o CLOSE phien d+1" cho CA BA ly do, ke ca het gio: nen lenh het gio (d = E+19)
  thuc su dong o close E+20, tuc giu 20 phien SAU phien vao lenh. Doc theo cau chu cua §1.4.
- Nen khong giao dich duoc nhan dien bang `volume == 0` (khong co khai niem "nghi giua phien"
  o du lieu ngay).
- Thieu EW_ret(d) cho mot ngay (khong ma nao du thanh khoan) thi coi nhu 0 — khong bo ngay do ra
  khoi tich, de moc khong bi phong dai.
- Du lieu chi co OHLC ngay: khong mo phong duoc khop lenh trong phien, khong tran/san ngoai
  `entry_status`, khong thanh khoan theo khoi luong.
"""

from __future__ import annotations

import argparse
import io
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Chay truc tiep `python scripts/...` phai import duoc `scripts.*` (loi da xay ra o dot 171).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_momentum_portfolio import (
    block_bootstrap,
    round_trip_cost,
    stock_symbols,
)
from trading.calendar_vn import TZ
from trading.metrics import profit_factor
from trading.models import Bar
from trading.stock_study import (
    bar_date,
    clean_bars,
    entry_status,
    liquidity_ok,
    load_universe,
    net_return,
    validate_sealed_bars,
)
from trading.storage.db import Storage

__all__ = [
    "MAX_HOLD",
    "MIN_TURNOVER",
    "PULLBACK_MAX",
    "PULLBACK_MIN",
    "STOP_LOSS",
    "TURNOVER_WINDOW",
    "evaluate",
    "ew_returns_by_date",
    "excess_of_trade",
    "find_signal",
    "main",
    "monthly_excess",
    "read_bars",
    "simulate_symbol",
]

# --- Tham so dang ky truoc ---------------------------------------------------------

SYMBOL_LEN = 3
MIN_TURNOVER = 2_000_000_000.0  # 2 ty/phan/trading (dieu kien 1)
TURNOVER_WINDOW = 20
MA_MID = 50
MA_LONG = 200
PULLBACK_WINDOW = 20  # H20
PULLBACK_HOLD = 5  # close[t-5..t-1]
PULLBACK_MIN = 0.05
PULLBACK_MAX = 0.15
MAX_HOLD = 20  # d = E+19
STOP_LOSS = 0.08
WIN_THRESHOLD = 300  # dieu kien 1
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 42
BLOCK_MONTHS = 3

IS_START = date(2017, 1, 1)
IS_END = date(2022, 11, 30)
READ_FROM = datetime(2016, 1, 1, tzinfo=TZ)
READ_TO = datetime(2023, 1, 1, tzinfo=TZ)  # read_daily_bars dung `ts < end`


# --- Doc du lieu -------------------------------------------------------------------


def read_bars(
    storage: Any,
    symbol: str,
    read_from: datetime = READ_FROM,
    read_to: datetime = READ_TO,
) -> tuple[list[Bar], int]:
    """Doc nen ngay mot ma: Kiem niem phong TRUOC, roi bo nen gia <= 0. Tra (nen, so bo)."""
    bars = storage.read_daily_bars(symbol, read_from, read_to)
    if not bars:
        return [], 0
    validate_sealed_bars(bars)
    return clean_bars(bars)


# --- Tin hieu ----------------------------------------------------------------------


def _sma(closes: list[float], t: int, n: int) -> float | None:
    if t + 1 < n:
        return None
    return statistics.fmean(closes[t - n + 1 : t + 1])


def _signal_ctx(bars: list[Bar], closes: list[float]) -> dict[str, Any]:
    """Tien tinh MA50/MA200 mot lan cho ca chuoi (chi de chay nhanh, khong doi ket qua)."""
    ma_mid: list[float | None] = [None] * len(closes)
    ma_long: list[float | None] = [None] * len(closes)
    s_mid = s_long = 0.0
    for i, c in enumerate(closes):
        s_mid += c
        s_long += c
        if i >= MA_MID:
            s_mid -= closes[i - MA_MID]
        if i >= MA_LONG:
            s_long -= closes[i - MA_LONG]
        if i + 1 >= MA_MID:
            ma_mid[i] = s_mid / MA_MID
        if i + 1 >= MA_LONG:
            ma_long[i] = s_long / MA_LONG
    return {"ma_mid": ma_mid, "ma_long": ma_long}


def find_signal(
    bars: list[Bar], t: int, ctx: dict[str, Any] | None = None
) -> dict | None:
    """Nam dieu kien cua §1.2 tai CLOSE phien t. Tra {"h20","depth"} hoac None.

    Chi dung du lieu <= t: khong co phep tinh nao cham toi t+1.
    """
    if t < 1 or t < MAX_PULLBACK_NEED:
        return None
    if not liquidity_ok(bars, t, window=TURNOVER_WINDOW, min_turnover=MIN_TURNOVER):
        return None

    closes = ctx["closes"] if ctx else [b.close for b in bars]
    ma_mid = ctx["ma_mid"][t] if ctx else _sma(closes, t, MA_MID)
    ma_long = ctx["ma_long"][t] if ctx else _sma(closes, t, MA_LONG)
    if ma_mid is None or ma_long is None:
        return None

    c = closes[t]
    if not (c > ma_long and ma_mid > ma_long):
        return None

    h20 = max(closes[t - PULLBACK_WINDOW : t])  # 20 phien KET THUC TAI t-1
    low5 = min(closes[t - PULLBACK_HOLD : t])  # close[t-5..t-1]
    if h20 <= 0:
        return None
    depth = 1.0 - low5 / h20
    if not (PULLBACK_MIN <= depth <= PULLBACK_MAX):
        return None

    if not (c > bars[t - 1].high):  # bat len
        return None
    return {"h20": h20, "depth": depth}


MAX_PULLBACK_NEED = MA_LONG  # can du 200 phien de co MA200


# --- Mo phong lenh -----------------------------------------------------------------


def _find_exit(bars: list[Bar], E: int, h20: float) -> tuple[int, str]:
    """Tra (chi so nen thoat, ly do). Kiem tai close moi phien d >= E, thoat o close d+1."""
    n = len(bars)
    stop_level = bars[E].open * (1.0 - STOP_LOSS)
    for d in range(E, min(E + MAX_HOLD, n)):
        # Sua cua Claude khi audit: brief §1.4 kiem tai close MOI phien d >= E (ke ca E);
        # T+2 chi lam BAN MUON toi E+2, khong bo qua dieu kien cham o phien E.
        trig: str | None = None
        if bars[d].close <= stop_level:
            trig = "STOP"
        elif bars[d].close >= h20:
            trig = "TP"
        if trig is None and d == E + MAX_HOLD - 1:
            trig = "TIME"
        if trig is not None:
            x = max(d + 1, E + 2)
            while x < n and bars[x].volume <= 0:  # nen khong giao dich -> lui tiep
                x += 1
            if x >= n:
                x = n - 1
            return x, trig
    return n - 1, "TIME"


def simulate_symbol(
    bars: list[Bar],
    exchange: str | None,
    symbol: str,
    *,
    is_start: date | None = IS_START,
    is_end: date | None = IS_END,
    stats: dict[str, int] | None = None,
) -> list[dict]:
    """Moi lenh cua MOT ma. Tra list trade: entry_i/exit_i/entry_date/exit_date/net/reason/hold.

    `is_start`/`is_end` loc theo NGAY TIN HIEU (IS cua §1.1). `stats` (neu truyen) dem so tin
    hieu bi bo vi gia tran.
    """
    if not bars:
        return []
    closes = [b.close for b in bars]
    ctx = _signal_ctx(bars, closes)
    ctx["closes"] = closes
    trades: list[dict] = []
    n = len(bars)
    t = 0
    while t < n - 1:
        sig = find_signal(bars, t, ctx)
        d_t = bar_date(bars[t])
        if sig is None or (is_start and d_t < is_start) or (is_end and d_t > is_end):
            t += 1
            continue
        st = entry_status(bars, t, exchange)
        if st != "ok":
            if stats is not None:
                stats[st] = stats.get(st, 0) + 1
            t += 1
            continue
        E = t + 1
        exit_i, reason = _find_exit(bars, E, sig["h20"])
        trades.append(
            {
                "symbol": symbol,
                "entry_i": E,
                "exit_i": exit_i,
                "entry_date": bar_date(bars[E]),
                "exit_date": bar_date(bars[exit_i]),
                "entry_price": bars[E].open,
                "exit_price": bars[exit_i].close,
                "reason": reason,
                "hold": exit_i - E,
                "net": net_return(bars[E].open, bars[exit_i].close),
                "h20": sig["h20"],
                "depth": sig["depth"],
            }
        )
        t = (
            exit_i + 1
        )  # dang giu thi khong nhan tin hieu moi -> nhay qua khoi thoi gian giu
    return trades


# --- Moc so sanh -------------------------------------------------------------------


def ew_returns_by_date(
    by_symbol: dict[str, list[Bar]],
    min_turnover: float = MIN_TURNOVER,
    window: int = TURNOVER_WINDOW,
) -> dict[date, float]:
    """EW_ret(d) = trung binh cong loi suat ngay cua moi ma du thanh khoan o phien d."""
    acc: dict[date, list[float]] = defaultdict(list)
    for bars in by_symbol.values():
        for i in range(1, len(bars)):
            prev = bars[i - 1].close
            if prev <= 0:
                continue
            if not liquidity_ok(bars, i, window=window, min_turnover=min_turnover):
                continue
            acc[bar_date(bars[i])].append(bars[i].close / prev - 1.0)
    return {d: statistics.fmean(v) for d, v in acc.items()}


def excess_of_trade(trade: dict, ew: dict[date, float]) -> float:
    """Vuot troi = loi nhuan rong cua lenh - moc EW cung khoang thoi gian (khong tru phi)."""
    bench = 1.0
    for d in sorted(ew):
        if trade["entry_date"] <= d <= trade["exit_date"]:
            bench *= 1.0 + ew[d]
    return trade["net"] - (bench - 1.0)


def monthly_excess(trades: list[dict]) -> list[float]:
    """Trung binh vuot troi theo THANG VAO LENH, sap theo thang; thang khong co lenh thi bo."""
    by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
    for tr in trades:
        by_month[(tr["entry_date"].year, tr["entry_date"].month)].append(tr["excess"])
    return [statistics.fmean(by_month[k]) for k in sorted(by_month)]


# --- Phep thu ----------------------------------------------------------------------


def evaluate(trades: list[dict], series: list[float]) -> dict[str, Any]:
    """Bon dieu kien cua §1.6 + bootstrap khoi 3 thang tren chuoi vuot troi theo thang."""
    cost_rt = round_trip_cost()
    nets = [t["net"] for t in trades]
    mean_net = statistics.fmean(nets) if nets else 0.0
    pf = profit_factor(nets)
    boot = (
        block_bootstrap(
            series, n_boot=N_BOOTSTRAP, seed=BOOTSTRAP_SEED, block=BLOCK_MONTHS
        )
        if series
        else {
            "mean": 0.0,
            "median": 0.0,
            "p": 1.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "n_months": 0,
        }
    )
    cond1 = len(trades) >= WIN_THRESHOLD
    cond2 = boot["p"] < 0.05 and boot["mean"] > 0
    cond3 = mean_net >= 0.5 * cost_rt
    cond4 = pf is not None and pf > 1.2
    return {
        "n_trades": len(trades),
        "n_months": len(series),
        "mean_excess": boot["mean"],
        "median_excess": boot["median"],
        "p": boot["p"],
        "ci_low": boot["ci_low"],
        "ci_high": boot["ci_high"],
        "mean_net": mean_net,
        "cost_rt": cost_rt,
        "profit_factor": pf if pf is not None else float("nan"),
        "cond1": cond1,
        "cond2": cond2,
        "cond3": cond3,
        "cond4": cond4,
        "dat": cond1 and cond2 and cond3 and cond4,
        "thieu_suc_manh": len(trades) < WIN_THRESHOLD,
    }


# --- main --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pullback trong xu huong, giu <= 20 phien, co phieu VN nen ngay (chi doc)"
    )
    p.add_argument("--dsn", default=None, help="Postgres DSN (mac dinh: moi truong)")
    p.add_argument("--limit", type=int, default=0, help="chi chay N ma dau (de thu)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t0 = time.perf_counter()
    storage = Storage(resolve_dsn(args.dsn))

    universe, exchange, n_all, excluded = load_universe(storage, "exclusions.txt")
    kept, non_stock = stock_symbols(universe)
    if args.limit:
        kept = kept[: args.limit]
    print(
        f"# Universe: {n_all} ma trong bars_daily, {len(universe)} sau exclusions.txt, "
        f"{len(kept)} la ma co phieu (bo {len(non_stock)} khong phai co phieu, "
        f"{len(excluded)} ma trong exclusions)"
    )
    print(
        "# CANH BAO thien lech song sot: KHONG co ma da huy niem yet trong bars_daily. "
        "Moi so sanh chi trong CUNG universe nay, khong so voi ETF."
    )
    print(
        f"# Niem phong: doc toi {READ_TO.date()}, nem loi voi nen >= 2023-01-01. "
        f"IS = tin hieu {IS_START} -> {IS_END}."
    )

    trades: list[dict] = []
    stats: dict[str, int] = {}
    acc: dict[date, list[float]] = defaultdict(list)
    n_read = n_junk = n_used = 0
    for sym in kept:
        bars, junk = read_bars(storage, sym)
        n_read += 1
        n_junk += junk
        if not bars:
            continue
        n_used += 1
        trades += simulate_symbol(bars, exchange.get(sym), sym, stats=stats)
        for i in range(1, len(bars)):
            prev = bars[i - 1].close
            if prev <= 0:
                continue
            if not liquidity_ok(
                bars, i, window=TURNOVER_WINDOW, min_turnover=MIN_TURNOVER
            ):
                continue
            acc[bar_date(bars[i])].append(bars[i].close / prev - 1.0)

    ew = {d: statistics.fmean(v) for d, v in acc.items()}
    for tr in trades:
        tr["excess"] = excess_of_trade(tr, ew)
    series = monthly_excess(trades)
    res = evaluate(trades, series)

    print(
        f"# Doc {n_read} ma, bo {n_junk} nen gia <= 0, {n_used} ma co du lieu dung duoc"
    )
    print(f"# So lenh IS: {res['n_trades']} | so thang co lenh: {res['n_months']}")
    print()
    print("### §1.6 Bon dieu kien")
    print(
        f"  (1) >= 300 lenh           : {res['n_trades']}            "
        f"-> {'DAT' if res['cond1'] else 'KHONG DAT'}"
    )
    print(
        f"  (2) p < 0,05 & TB > 0     : p = {res['p']:.4f}, TB vuot troi/thang = "
        f"{res['mean_excess'] * 100:+.4f}% (KTC95 [{res['ci_low'] * 100:+.4f}%; "
        f"{res['ci_high'] * 100:+.4f}%]) -> {'DAT' if res['cond2'] else 'KHONG DAT'}"
    )
    print(
        f"  (3) TB rong >= 0,5*cost_rt: TB rong = {res['mean_net'] * 100:+.4f}%, "
        f"0,5*cost_rt = {0.5 * res['cost_rt'] * 100:.4f}% (cost_rt = "
        f"{res['cost_rt'] * 100:.4f}%) -> {'DAT' if res['cond3'] else 'KHONG DAT'}"
    )
    print(
        f"  (4) profit factor rong>1,2: PF = {res['profit_factor']:.4f} -> "
        f"{'DAT' if res['cond4'] else 'KHONG DAT'}"
    )
    if res["thieu_suc_manh"]:
        print("  => THIEU SUC MANH (<300 lenh): KHONG ket luan")
    else:
        print(f"  => {'DAT' if res['dat'] else 'KHONG DAT'}")
    print()

    if trades:
        holds = [t["hold"] for t in trades]
        print("### §1.7 Mo ta")
        print(
            f"  So ngay giu: min {min(holds)} | trung vi {statistics.median(holds):.0f} | "
            f"max {max(holds)} | TB {statistics.fmean(holds):.2f}"
        )
        reasons = defaultdict(int)
        for t in trades:
            reasons[t["reason"]] += 1
        total = len(trades)
        for k in ("STOP", "TP", "TIME"):
            print(
                f"  Thoat vi {k:<4}: {reasons[k]:>5} ({reasons[k] / total * 100:.1f}%)"
            )
        by_day: dict[date, int] = defaultdict(int)
        for t in trades:
            d = t["entry_date"]
            while d <= t["exit_date"]:
                by_day[d] += 1
                d = d.fromordinal(d.toordinal() + 1)
        occ = sorted(by_day.values())
        print(
            f"  Vi the mo dong thoi (theo ngay): min {occ[0]} | trung vi "
            f"{statistics.median(occ):.0f} | max {occ[-1]} (tb {statistics.fmean(occ):.2f})"
        )
        by_year: dict[int, list[float]] = defaultdict(list)
        for t in trades:
            by_year[t["entry_date"].year].append(t["net"])
        print("  Theo nam vao lenh (n, TB rong, tong rong):")
        for y in sorted(by_year):
            v = by_year[y]
            print(
                f"    {y}: {len(v):>4} lenh, TB {statistics.fmean(v) * 100:+.3f}%, "
                f"tong {sum(v) * 100:+.2f}%"
            )
        print(f"  Tin hieu bi bo vi vao lenh: {dict(stats)}")
        print(
            f"  TB do sau dieu chinh: {statistics.fmean([t['depth'] for t in trades]) * 100:.2f}%"
        )
    print(f"# Xong sau {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
