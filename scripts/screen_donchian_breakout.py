"""Pha dinh Donchian 55/20, co phieu VN nen ngay — Brief dot 175 (DANG KY TRUOC).

THIET KE DANG KY TRUOC (chot trong brief, KHONG doi sau khi thay so):
- Du lieu/universe/niem phong: GIONG HET dot 173 §1.1 — `bars_daily`, `load_universe(storage,
  "exclusions.txt")`, chi ma co phieu, bo nen gia <= 0, doc bang `read_bars` cua
  screen_pullback_trend (co cong niem phong: nen >= 2023-01-01 thi NEM LOI).
  IS = moi tin hieu co ngay tin hieu trong 2017-01-01 -> 2022-10-31 (2016 lam nong;
  tin hieu cuoi cach 31/12/2022 du 40 phien de dong lenh).
- Tin hieu mua (tai CLOSE phien t, chi dung du lieu <= t), du ca ba:
  1. thanh khoan: `liquidity_ok(bars, t, window=20, min_turnover=2 ty)`;
  2. pha dinh: `close[t] > max(high[t-55..t-1])` (can du 55 nen truoc t);
  3. khong dang giu ma do — phien thoat lenh cu CUNG tinh la dang giu.
- Vao lenh: mua o OPEN phien t+1; `entry_status` khac "ok" thi bo. E = t+1.
- Thoat: kiem tai CLOSE moi phien d >= E, KE CA d = E; thoat o CLOSE phien d+1. Thu tu uu tien:
  1. cat lo `close[d] <= open[E]*0,90`; 2. thung kenh day `close[d] < min(low[d-20..d-1])`
  (cua so truot theo d, co the lui truoc E); 3. het gio `d = E+39` (giu toi da 40 phien).
  Rang buoc T+2: phien thoat = `max(d+1, E+2)` — dieu kien cham o phien E hoac E+1 VAN duoc
  ghi nhan, chi ban muon toi E+2. (Day la loi agent dot 173 tung mac: bo qua dieu kien tai E.)
  Thoat roi vao nen khoi luong 0 thi lui tiep. Loi nhuan = `net_return(open[E], close[exit])`.
- Moc so sanh va phep thu: MƯỢN NGUYÊN VĂN tu screen_pullback_trend — `ew_returns_by_date`,
  `excess_of_trade`, `monthly_excess`, `evaluate` (bootstrap khoi 3 thang, 2.000 lan, seed 42).
  DAT khi ca bon: >=300 lenh; p < 0,05 mot phia VA trung binh > 0; TB rong moi lenh >= 0,5*cost_rt;
  profit factor rong > 1,2. Duoi 300 lenh: THIEU SUC MANH.

CHO BRIEF MO HO (tu dien giai, khong im lang chon):
- §1.2 dieu kien 2 ghi `max(high[t-55..t-1])` — nghia la KHONG tinh high cua chinh phien t. Da lam
  dung nhu chu, va co test rieng cho ca "dong cua bang dung dinh thi khong tinh la pha dinh".
- §1.4 ghi "thoat o CLOSE phien d+1" cho CA BA ly do, roi ngay sau do ghi rang buoc T+2 la
  `max(d+1, E+2)`. Hai cau nay mau thuan khi d = E (d+1 = E+1 < E+2). Toi theo cau thu hai (T+2
  thang): phien thoat = max(d+1, E+2), va dieu kien chay o phien E VAN duoc ghi nhan.
- "Thung kenh day" khi d < 20: khong du 20 nen truoc d thi KHONG xet dieu kien nay (khong dung
  cua so ngan hon).
- Het gio d = E+39 nhung phien thoat = max(d+1, E+2) = E+40 nen so phien giu toi da la 40 phien
  SAU phien vao lenh (khop cau "giu toi da 40 phien" cua brief).
- Du lieu chi co OHLC ngay: khong mo phong duoc khop lenh trong phien; `entry_status` chi bat
  duoc gia tran / khoi luong 0 / thieu nen.
"""

from __future__ import annotations

import argparse
import io
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Chay truc tiep `python scripts/...` phai import duoc `scripts.*`.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from scripts.screen_momentum_portfolio import stock_symbols
from scripts.screen_pullback_trend import (
    MIN_TURNOVER,
    TURNOVER_WINDOW,
    evaluate,
    ew_returns_by_date,
    excess_of_trade,
    monthly_excess,
    read_bars,
)
from trading.stock_study import (
    bar_date,
    entry_status,
    liquidity_ok,
    load_universe,
    net_return,
)
from trading.storage.db import Storage

__all__ = [
    "BREAKOUT_LOOKBACK",
    "CHANNEL_LOOKBACK",
    "MAX_HOLD",
    "MIN_TURNOVER",
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

BREAKOUT_LOOKBACK = 55  # pha dinh 55 phien
CHANNEL_LOOKBACK = 20  # kenh day 20 phien (trailing)
STOP_LOSS = 0.10
MAX_HOLD = 40  # d = E+39 -> thoat o close E+40
IS_START = date(2017, 1, 1)
IS_END = date(2022, 10, 31)


# --- Tin hieu ----------------------------------------------------------------------


def find_signal(bars: list[Any], t: int) -> dict | None:
    """Ba dieu kien cua §1.2 tai CLOSE phien t. Tra {"donchian_high": float} hoac None.

    Chi dung du lieu <= t. Dinh so sanh la `max(high[t-55..t-1])` — KHONG gom phien t.
    """
    if t < BREAKOUT_LOOKBACK:
        return None
    if not liquidity_ok(bars, t, window=TURNOVER_WINDOW, min_turnover=MIN_TURNOVER):
        return None
    hi = max(bars[i].high for i in range(t - BREAKOUT_LOOKBACK, t))
    if not (bars[t].close > hi):
        return None
    return {"donchian_high": hi}


# --- Mo phong lenh -----------------------------------------------------------------


def _find_exit(bars: list[Any], E: int, entry_open: float) -> tuple[int, str]:
    """Tra (chi so nen thoat, ly do). Kiem tai CLOSE moi phien d >= E (KE CA E), thoat o CLOSE d+1.

    Thu tu uu tien: cat lo -> thung kenh day -> het gio. T+2: phien thoat = max(d+1, E+2).
    """
    n = len(bars)
    stop_level = entry_open * (1.0 - STOP_LOSS)
    for d in range(E, min(E + MAX_HOLD, n)):
        trig: str | None = None
        if bars[d].close <= stop_level:
            trig = "STOP"
        elif d >= CHANNEL_LOOKBACK and bars[d].close < min(
            bars[i].low for i in range(d - CHANNEL_LOOKBACK, d)
        ):
            trig = "CHANNEL"
        if trig is None and d == E + MAX_HOLD - 1:
            trig = "TIME"
        if trig is not None:
            x = max(d + 1, E + 2)  # T+2
            while x < n and bars[x].volume <= 0:  # nen khong giao dich -> lui tiep
                x += 1
            if x >= n:
                x = n - 1
            return x, trig
    return n - 1, "TIME"


def simulate_symbol(
    bars: list[Any],
    exchange: str | None,
    symbol: str,
    *,
    is_start: date | None = IS_START,
    is_end: date | None = IS_END,
    stats: dict[str, int] | None = None,
) -> list[dict]:
    """Moi lenh cua MOT ma. Tra list trade (cung khoa voi dot 173 de dung lai `evaluate`).

    `is_start`/`is_end` loc theo NGAY TIN HIEU. `stats` (neu truyen) dem tin hieu bi bo vi gia tran.
    """
    if not bars:
        return []
    trades: list[dict] = []
    n = len(bars)
    t = 0
    while t < n - 1:
        sig = find_signal(bars, t)
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
        exit_i, reason = _find_exit(bars, E, bars[E].open)
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
                "donchian_high": sig["donchian_high"],
            }
        )
        # Phien thoat CUNG tinh la dang giu -> tin hieu tai chinh phien do bi bo.
        t = exit_i + 1
    return trades


# --- main --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pha dinh Donchian 55/20, co phieu VN nen ngay (chi doc)"
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
    print(f"# Universe: {n_all} ma trong bars_daily, {len(universe)} sau exclusions.txt, "
          f"{len(kept)} la ma co phieu (bo {len(non_stock)} khong phai co phieu, "
          f"{len(excluded)} ma trong exclusions)")
    print("# CANH BAO thien lech song sot: KHONG co ma da huy niem yet trong bars_daily. "
          "Moi so sanh chi trong CUNG universe nay, khong so voi ETF.")
    print("# Niem phong: doc toi 2023-01-01, nem loi voi nen >= 2023-01-01. "
          f"IS = tin hieu {IS_START} -> {IS_END}.")

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
            if not liquidity_ok(bars, i, window=TURNOVER_WINDOW, min_turnover=MIN_TURNOVER):
                continue
            acc[bar_date(bars[i])].append(bars[i].close / prev - 1.0)

    ew = {d: statistics.fmean(v) for d, v in acc.items()}
    for tr in trades:
        tr["excess"] = excess_of_trade(tr, ew)
    series = monthly_excess(trades)
    res = evaluate(trades, series)

    print(f"# Doc {n_read} ma, bo {n_junk} nen gia <= 0, {n_used} ma co du lieu dung duoc")
    print(f"# So lenh IS: {res['n_trades']} | so thang co lenh: {res['n_months']}")
    print()
    print("### §1.5 Bon dieu kien")
    print(f"  (1) >= 300 lenh           : {res['n_trades']}            "
          f"-> {'DAT' if res['cond1'] else 'KHONG DAT'}")
    print(f"  (2) p < 0,05 & TB > 0     : p = {res['p']:.4f}, TB vuot troi/thang = "
          f"{res['mean_excess'] * 100:+.4f}% (KTC95 [{res['ci_low'] * 100:+.4f}%; "
          f"{res['ci_high'] * 100:+.4f}%]) -> {'DAT' if res['cond2'] else 'KHONG DAT'}")
    print(f"  (3) TB rong >= 0,5*cost_rt: TB rong = {res['mean_net'] * 100:+.4f}%, "
          f"0,5*cost_rt = {0.5 * res['cost_rt'] * 100:.4f}% (cost_rt = "
          f"{res['cost_rt'] * 100:.4f}%) -> {'DAT' if res['cond3'] else 'KHONG DAT'}")
    print(f"  (4) profit factor rong>1,2: PF = {res['profit_factor']:.4f} -> "
          f"{'DAT' if res['cond4'] else 'KHONG DAT'}")
    if res["thieu_suc_manh"]:
        print("  => THIEU SUC MANH (<300 lenh): KHONG ket luan")
    else:
        print(f"  => {'DAT' if res['dat'] else 'KHONG DAT'}")
    print()

    if trades:
        holds = [t["hold"] for t in trades]
        print("### §1.6 Mo ta")
        print(f"  So ngay giu: min {min(holds)} | trung vi {statistics.median(holds):.0f} | "
              f"max {max(holds)} | TB {statistics.fmean(holds):.2f}")
        reasons = defaultdict(int)
        for t in trades:
            reasons[t["reason"]] += 1
        total = len(trades)
        for k in ("STOP", "CHANNEL", "TIME"):
            print(f"  Thoat vi {k:<7}: {reasons[k]:>5} ({reasons[k] / total * 100:.1f}%)")
        by_day: dict[date, int] = defaultdict(int)
        for t in trades:
            d = t["entry_date"]
            while d <= t["exit_date"]:
                by_day[d] += 1
                d = d.fromordinal(d.toordinal() + 1)
        occ = sorted(by_day.values())
        print(f"  Vi the mo dong thoi (theo ngay): min {occ[0]} | trung vi "
              f"{statistics.median(occ):.0f} | max {occ[-1]} (tb {statistics.fmean(occ):.2f})")
        by_year: dict[int, list[dict]] = defaultdict(list)
        for t in trades:
            by_year[t["entry_date"].year].append(t)
        print("  Theo nam vao lenh (n, TB rong, tong rong, TB vuot troi):")
        for y in sorted(by_year):
            v = by_year[y]
            nets = [t["net"] for t in v]
            exc = [t["excess"] for t in v]
            print(f"    {y}: {len(v):>4} lenh, TB {statistics.fmean(nets) * 100:+.3f}%, "
                  f"tong {sum(nets) * 100:+.2f}%, vuot troi TB "
                  f"{statistics.fmean(exc) * 100:+.3f}%")
        print(f"  Tin hieu bi bo vi vao lenh: {dict(stats)}")
    print(f"# Xong sau {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
