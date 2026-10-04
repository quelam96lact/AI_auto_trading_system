"""Volatility targeting tren ETF VN30 mua-va-giu — Brief dot 161 (CHI DO, khong dung engine).

Cau hoi: chia co vi the theo du bao do bien dong co lam giam drawdown ma khong mat qua
nhieu lai kep khong? Do tren thu DUY NHAT trong du an da do la co lai ky vong duong:
ETF `E1VFVN30` mua-va-giu (dot 102).

Thiet ke DANG KY TRUOC (chot trong brief, KHONG chinh sau khi thay ket qua):
- Lam am 2016 (chi de uoc luong sigma). Do 2017-01-02 -> 2026-09-30.
- Doi chung: mua-va-giu 100%, mua o OPEN phien do dau, ban o CLOSE phien cuoi, du phi/thue/truot gia.
- sigma_hat: EWMA tren loi suat LOG ngay, lambda = 0,94 (RiskMetrics), annualize sqrt(252).
- Bien dong muc tieu: TRUNG VI cua moi sigma_hat tinh toi het phien t (cua so MO RONG). Khong tham so.
- w*_t = min(1, muc_tieu_t / sigma_hat_t). Tran 1: khong vay margin.
- Quyet dinh o close phien t, khop o OPEN phien t+1. Khong dung du lieu sau close phien t.
- Nguong tai can bang: chi giao dich khi |w*_t - w_hien_tai| >= 0,20.
- Phi (IMPORT tu trading/paper_broker.py, khong go lai so): moi lan mua FEE_RATE + truot gia;
  moi lan ban FEE_RATE + SELL_TAX_RATE + truot gia.
- Tien mat lai 0 (bao thu).
- Duoc dung ty trong le.

Mo hinh chi phi (noi ro de doc lai duoc):
- Moi giao dich tra `|notional khop| x don_gia_phi`, notional do tren EQUITY GOP truoc giao dich.
- Chi phi duoc CONG DON rieng, khong tru vao von dung de tinh notional cua lan sau:
  equity bao cao = equity gop - chi phi cong don. Nho vay mot vong mua-ban o gia phang mat
  DUNG `2*FEE_RATE + SELL_TAX_RATE + 2*truot_gia` (dung nhu brief ghi, sai so 0).

VI SAO KHONG dung `read_symbol_bars` (nhu brief chi dinh): ham do goi `validate_sealed_bars`,
ham nay NEM LOI voi moi nen tu 2023-01-01 va khong co co bo qua. Brief lai chot do den
30/09/2026. Nen o day dung dung hai manh cua no — `storage.read_daily_bars` + `clean_bars`
(trading/stock_study.py) — va BO rieng cong niem phong. Day la phep DO mot ETF cong khai voi
thiet ke da chot TRUOC, khong phai di tim chien luoc tren du lieu niêm phong; bien the nhay
chi de bao cao, khong duoc dung de chon. Xem bao cao dot 161 muc "brief sai o dau".
"""

from __future__ import annotations

import argparse
import io
import math
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Bootstrap: chay truc tiep (`python scripts/...`) thi repo root chua co tren sys.path,
# nen `from scripts._db_common import ...` se nem ModuleNotFoundError (da mac o dot 106).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ
from trading.metrics import max_drawdown, sharpe
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import bar_date, clean_bars
from trading.storage.db import Storage

__all__ = [
    "EWMA_LAMBDA",
    "ROLL_WINDOW",
    "buy_hold",
    "clean_price_bars",
    "ewma_vol",
    "expanding_median",
    "garch_persistence",
    "log_returns",
    "main",
    "rolling_vol",
    "simulate",
    "target_weights",
]

# --- Tham so dang ky truoc ---------------------------------------------------------

SYMBOL = "E1VFVN30"
EWMA_LAMBDA = 0.94
ROLL_WINDOW = 20
REBAL_THRESHOLD = 0.20
ANN = math.sqrt(252.0)
SLIP = SLIPPAGE_BPS / 10_000.0
CASH_RETURN = 0.0  # bao thu: tien mat lai 0
INITIAL_CAPITAL = 1.0

WARMUP_FROM = datetime(2016, 1, 1, tzinfo=TZ)
MEASURE_FROM = date(2017, 1, 2)
MEASURE_TO = date(2026, 9, 30)
READ_TO = datetime(2026, 10, 1, tzinfo=TZ)  # read_daily_bars dung `ts < end`
SEALED_START = date(2023, 1, 1)  # moc niem phong cua repo — xem docstring module
GARCH_REFIT_EVERY = 21
TRADING_DAYS_PER_YEAR = 252


def clean_price_bars(bars: Sequence[Bar]) -> tuple[list[Bar], int]:
    """Bo phien co OHLC <= 0 (bars_daily co y giu 71 nghin dong gia 0). Tra (nen, so bo)."""
    return clean_bars(list(bars))


def read_prices(
    storage: Any,
    symbol: str = SYMBOL,
    start: datetime = WARMUP_FROM,
    end: datetime = READ_TO,
) -> tuple[list[Bar], int]:
    """Doc nen ngay cua mot ma + bo nen gia <= 0 (dung read_daily_bars + clean_bars)."""
    bars = storage.read_daily_bars(symbol, start, end)
    return clean_price_bars(bars)


# --- Cac ham thuan ----------------------------------------------------------------


def log_returns(closes: Sequence[float]) -> list[float]:
    """r[k] = ln(close[k+1] / close[k]). Do dai = len(closes) - 1."""
    return [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]


def ewma_vol(returns: Sequence[float], lam: float = EWMA_LAMBDA) -> list[float]:
    """sigma_hat annualize theo EWMA RiskMetrics.

    sigma^2_0 = r_0^2; sigma^2_t = lam*sigma^2_{t-1} + (1-lam)*r_t^2. Annualize sqrt(252).
    sigma_hat_t chi dung r_0..r_t — dung cho quyet dinh o close phien t.
    """
    out: list[float] = []
    var: float | None = None
    for r in returns:
        var = r * r if var is None else lam * var + (1.0 - lam) * r * r
        out.append(math.sqrt(var * TRADING_DAYS_PER_YEAR))
    return out


def rolling_vol(
    returns: Sequence[float], window: int = ROLL_WINDOW
) -> list[float | None]:
    """Do lech chuan mau cua `window` loi suat ket thuc tai t, annualize. Chua du -> None."""
    out: list[float | None] = [None] * len(returns)
    for i in range(window - 1, len(returns)):
        out[i] = statistics.stdev(returns[i - window + 1 : i + 1]) * ANN
    return out


def expanding_median(values: Sequence[float | None]) -> list[float]:
    """Trung vi cua MOI gia tri khac None tinh toi het phien t (cua so mo rong tu dau).

    Chua co gia tri nao -> nan (nguoi goi coi la chua du du lieu).
    """
    out: list[float] = []
    buf: list[float] = []
    for v in values:
        if v is not None:
            buf.append(v)
        out.append(statistics.median(buf) if buf else float("nan"))
    return out


def target_weights(
    vols: Sequence[float | None],
    targets: Sequence[float],
    cap: float = 1.0,
) -> list[float]:
    """w* = min(cap, muc_tieu / sigma_hat). Thieu du lieu / sigma <= 0 -> 0 (dung tien mat)."""
    out: list[float] = []
    for v, t in zip(vols, targets, strict=True):
        if v is None or v <= 0 or math.isnan(t) or t <= 0:
            out.append(0.0)
        else:
            out.append(min(cap, t / v))
    return out


def vol_series(
    closes: Sequence[float],
    kind: str = "ewma",
    lam: float = EWMA_LAMBDA,
    window: int = ROLL_WINDOW,
) -> list[float | None]:
    """sigma_hat gan theo CHI SO NEN: phan tu 0 = None (phien dau chua co loi suat)."""
    r = log_returns(closes)
    raw: list[float | None]
    if kind == "ewma":
        raw = list(ewma_vol(r, lam))
    elif kind == "rolling":
        raw = list(rolling_vol(r, window))
    else:
        raise ValueError(f"kind khong hop le: {kind}")
    return [None, *raw]


def weights_series(
    closes: Sequence[float], kind: str = "ewma", lam: float = EWMA_LAMBDA
) -> list[float]:
    """w* gan theo chi so nen, voi bien dong muc tieu = trung vi mo rong cua sigma_hat."""
    vols = vol_series(closes, kind=kind, lam=lam)
    targets = expanding_median(vols)
    return target_weights(vols, targets)


def garch_persistence(
    returns: Sequence[float], model: Any = None, refit_every: int = GARCH_REFIT_EVERY
) -> dict[str, float] | None:
    """Uoc luong GARCH(1,1) theo CUA SO MO RONG, lap lai moi `refit_every` phien.

    Tra tham so cua lan uoc luong CUOI (omega, alpha, beta, alpha+beta, n_fits).
    Loi suat nhan 100 (arch lam viec tot o don vi %) — omega vi vay cung o don vi %^2.
    `model` la module `arch` (truyen vao de test importorskip duoc).
    """
    if model is None:
        import arch as model  # type: ignore[no-redef]

    if len(returns) < 50:
        return None
    n_fits = 0
    res = None
    i = refit_every
    while i <= len(returns):
        res = model.arch_model(
            [r * 100.0 for r in returns[:i]], vol="GARCH", p=1, q=1, mean="Constant"
        ).fit(disp="off")
        n_fits += 1
        i += refit_every
    if res is None or n_fits == 0:
        return None
    p = res.params
    omega = float(p.get("omega", float("nan")))
    alpha = float(p.get("alpha[1]", float("nan")))
    beta = float(p.get("beta[1]", float("nan")))
    return {
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "alpha_plus_beta": alpha + beta,
        "n_fits": float(n_fits),
    }


def garch_vol_series(
    returns: Sequence[float],
    model: Any = None,
    refit_every: int = GARCH_REFIT_EVERY,
) -> list[float | None]:
    """sigma_hat GARCH(1,1) annualize, chi dung du lieu toi phien t, refit moi `refit_every`.

    Giua hai lan refit: duy tri phuong sai co dieu kien bang
    sigma^2_{t+1|t} = omega + alpha*r_t^2 + beta*sigma^2_t.
    """
    if model is None:
        import arch as model  # type: ignore[no-redef]

    out: list[float | None] = [None]
    if len(returns) < 50:
        return out + [None] * (len(returns) - 1)

    params: tuple[float, float, float] | None = None
    var: float | None = None
    for t, r in enumerate(returns):
        if t >= 50 and (params is None or (t - 50) % refit_every == 0):
            res = model.arch_model(
                [x * 100.0 for x in returns[: t + 1]], vol="GARCH", p=1, q=1, mean="Constant"
            ).fit(disp="off")
            p = res.params
            params = (
                float(p.get("omega", 0.0)),
                float(p.get("alpha[1]", 0.0)),
                float(p.get("beta[1]", 0.0)),
            )
            # phuong sai co dieu kien cuoi cung cua lan fit (don vi %^2)
            var = float(res.conditional_volatility[-1]) ** 2
        if params is None or var is None:
            out.append(None)
            continue
        omega, alpha, beta = params
        var = omega + alpha * (r * 100.0) ** 2 + beta * var
        out.append(math.sqrt(var) / 100.0 * ANN)
    return out


# --- Mo phong ----------------------------------------------------------------------


@dataclass(slots=True)
class Trade:
    bar_index: int
    day: date
    side: str
    notional: float  # notional khop, do tren EQUITY GOP truoc giao dich
    weight_after: float
    cost: float


@dataclass(slots=True)
class SimResult:
    label: str
    dates: list[date] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(t.cost for t in self.trades)

    @property
    def avg_weight(self) -> float:
        return statistics.fmean(self.weights) if self.weights else 0.0

    @property
    def n_trades(self) -> int:
        return len(self.trades)


def _per_side_rate(side: str) -> float:
    if side == "BUY":
        return FEE_RATE + SLIP
    return FEE_RATE + SELL_TAX_RATE + SLIP


def simulate(
    bars: Sequence[Bar],
    w_star: Sequence[float | None],
    threshold: float = REBAL_THRESHOLD,
    start_idx: int = 0,
    end_idx: int | None = None,
    initial: float = 1.0,
    label: str = "vol-target",
) -> SimResult:
    """Mo phong co nguong tai can bang. Quyet dinh o CLOSE phien i, khop o OPEN phien i+1.

    Chi phi cong don rieng (`cost_paid`), khong tru vao notional cua lan sau — nho vay mot
    vong mua-ban o gia phang mat dung 2*FEE_RATE + SELL_TAX_RATE + 2*truot_gia.
    """
    end = len(bars) - 1 if end_idx is None else end_idx
    res = SimResult(label=label)
    units = 0.0
    cash = initial
    cost_paid = 0.0
    pending: float | None = None

    for i in range(start_idx, end + 1):
        if pending is not None:
            px = bars[i].open
            gross = cash + units * px
            delta = pending * gross - units * px
            if abs(delta) > 0.0:
                side = "BUY" if delta > 0 else "SELL"
                cost = abs(delta) * _per_side_rate(side)
                cost_paid += cost
                units += delta / px
                cash -= delta  # mua: tien mat giam; ban: tien mat tang
                res.trades.append(
                    Trade(i, bar_date(bars[i]), side, abs(delta), pending, cost)
                )
        close = bars[i].close
        gross = cash + units * close
        res.equity_curve.append(gross - cost_paid)
        res.weights.append(units * close / gross if gross > 0 else 0.0)
        res.dates.append(bar_date(bars[i]))

        w_t = w_star[i] if i < len(w_star) else None
        if (
            w_t is not None
            and i < end
            and abs(w_t - res.weights[-1]) >= threshold
        ):
            pending = w_t
        else:
            pending = None

    # tien mat khong sinh lai (CASH_RETURN = 0) nen khong co so hang nao them vao
    assert CASH_RETURN == 0.0
    return res


def buy_hold(
    bars: Sequence[Bar], start_idx: int, end_idx: int, initial: float = 1.0
) -> SimResult:
    """Mua-va-giu 100%: mua o OPEN phien dau, ban o CLOSE phien cuoi, du phi/thue/truot gia."""
    res = SimResult(label="buy&hold")
    px = bars[start_idx].open
    units = initial / px
    buy_cost = initial * _per_side_rate("BUY")
    for i in range(start_idx, end_idx + 1):
        close = bars[i].close
        gross = units * close
        cost = buy_cost + (units * close * _per_side_rate("SELL") if i == end_idx else 0.0)
        res.equity_curve.append(gross - cost)
        res.weights.append(1.0)
        res.dates.append(bar_date(bars[i]))
    res.trades.append(Trade(start_idx, bar_date(bars[start_idx]), "BUY", initial, 1.0, buy_cost))
    res.trades.append(
        Trade(
            end_idx,
            bar_date(bars[end_idx]),
            "SELL",
            units * bars[end_idx].close,
            0.0,
            units * bars[end_idx].close * _per_side_rate("SELL"),
        )
    )
    return res


# --- Thong ke ----------------------------------------------------------------------


def cagr(equity: Sequence[float], dates: Sequence[date]) -> float:
    """CAGR theo NGAY DUONG LICH (so ngay / 365,25)."""
    if len(equity) < 2 or equity[0] <= 0 or equity[-1] <= 0:
        return float("nan")
    years = (dates[-1] - dates[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return (equity[-1] / equity[0]) ** (1.0 / years) - 1.0


def cagr_sessions(equity: Sequence[float]) -> float:
    """CAGR theo SO PHIEN (252/nam) — de doi chieu, khong dung cho ket luan."""
    n = len(equity) - 1
    if n <= 0 or equity[0] <= 0 or equity[-1] <= 0:
        return float("nan")
    return (equity[-1] / equity[0]) ** (TRADING_DAYS_PER_YEAR / n) - 1.0


def daily_returns(equity: Sequence[float]) -> list[float]:
    return [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity)) if equity[i - 1] > 0]


def month_end_equity(res: SimResult) -> list[tuple[tuple[int, int], float]]:
    """(khoa thang, equity cuoi thang) theo thu tu thoi gian."""
    out: list[tuple[tuple[int, int], float]] = []
    for d, e in zip(res.dates, res.equity_curve, strict=True):
        k = (d.year, d.month)
        if out and out[-1][0] == k:
            out[-1] = (k, e)
        else:
            out.append((k, e))
    return out


def year_end_equity(res: SimResult) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for d, e in zip(res.dates, res.equity_curve, strict=True):
        if out and out[-1][0] == d.year:
            out[-1] = (d.year, e)
        else:
            out.append((d.year, e))
    return out


def yearly_table(res: SimResult) -> list[tuple[int, float]]:
    """Loi suat tung nam. Nam DAU tinh tu VON BAN DAU (=1,0) chu khong bo trong:
    phep do bat dau giua thang 01/2017 nen nam dau khong co moc "cuoi nam truoc"."""
    years = year_end_equity(res)
    if not years:
        return []
    out = [(years[0][0], years[0][1] / INITIAL_CAPITAL - 1.0)]
    for i in range(1, len(years)):
        out.append((years[i][0], years[i][1] / years[i - 1][1] - 1.0))
    return out


def monthly_returns(res: SimResult) -> list[float]:
    """Loi suat tung thang; thang DAU tinh tu von ban dau (cung ly do nhu yearly_table)."""
    months = month_end_equity(res)
    if not months:
        return []
    out = [months[0][1] / INITIAL_CAPITAL - 1.0]
    for i in range(1, len(months)):
        if months[i - 1][1] > 0:
            out.append(months[i][1] / months[i - 1][1] - 1.0)
    return out


def summarize(res: SimResult) -> dict[str, float]:
    """CAGR, MDD, nam te nhat, thang te nhat, Sharpe, so giao dich, tong phi, ty trong TB."""
    eq = res.equity_curve
    month_rets = monthly_returns(res)
    years = year_end_equity(res)
    year_rets = [
        years[i][1] / years[i - 1][1] - 1.0 for i in range(1, len(years)) if years[i - 1][1] > 0
    ]
    s = sharpe(daily_returns(eq), TRADING_DAYS_PER_YEAR)
    return {
        "cagr": cagr(eq, res.dates),
        "cagr_sessions": cagr_sessions(eq),
        "total_return": eq[-1] / eq[0] - 1.0 if eq else float("nan"),
        "mdd": max_drawdown(eq),
        "worst_year": min(year_rets) if year_rets else float("nan"),
        "worst_month": min(month_rets) if month_rets else float("nan"),
        "sharpe": s if s is not None else float("nan"),
        "n_trades": float(res.n_trades),
        "total_cost": res.total_cost,
        "avg_weight": res.avg_weight,
    }


def yearly_from_daily(dates: Sequence[date], equity: Sequence[float]) -> list[tuple[int, float]]:
    res = SimResult(label="x", dates=list(dates), equity_curve=list(equity))
    return yearly_table(res)


# --- In bang -----------------------------------------------------------------------


def fmt_pct(x: float, nd: int = 2) -> str:
    return "n/a" if math.isnan(x) else f"{x * 100:.{nd}f}%"


def print_summary_table(rows: list[tuple[str, dict[str, float]]]) -> None:
    print(
        f"{'bien the':<34} {'CAGR':>9} {'MDD':>9} {'nam te':>9} {'thang te':>10} "
        f"{'Sharpe':>8} {'GD':>5} {'phi':>9} {'w TB':>7}"
    )
    print("-" * 116)
    for name, s in rows:
        print(
            f"{name:<34} {fmt_pct(s['cagr']):>9} {fmt_pct(s['mdd']):>9} "
            f"{fmt_pct(s['worst_year']):>9} {fmt_pct(s['worst_month']):>10} "
            f"{s['sharpe']:>8.2f} {int(s['n_trades']):>5} {s['total_cost'] * 100:>8.3f}% "
            f"{fmt_pct(s['avg_weight'], 1):>7}"
        )


def print_year_table(main: SimResult, bh: SimResult) -> None:
    my = dict(yearly_table(main))
    by = dict(yearly_table(bh))
    print(f"{'nam':<6} {'bien the chinh':>15} {'mua-va-giu':>12} {'chenh':>10}")
    print("-" * 46)
    win = lose = tie = 0
    for y in sorted(set(my) | set(by)):
        a, b = my.get(y, float("nan")), by.get(y, float("nan"))
        d = a - b if not (math.isnan(a) or math.isnan(b)) else float("nan")
        if not math.isnan(d):
            if d > 1e-12:
                win += 1
            elif d < -1e-12:
                lose += 1
            else:
                tie += 1
        print(f"{y:<6} {fmt_pct(a):>15} {fmt_pct(b):>12} {fmt_pct(d):>10}")
    print("-" * 46)
    print(f"thang {win} / thua {lose} / hoa {tie}   (nam 2026 la nam do dang)")


# --- main --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Do volatility targeting tren ETF VN30 (chi doc)")
    p.add_argument("--dsn", default=None, help="Postgres DSN (mac dinh lay tu moi truong)")
    p.add_argument("--symbol", default=SYMBOL)
    p.add_argument("--no-garch", action="store_true", help="bo qua bien the GARCH")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    t0 = time.perf_counter()
    storage = Storage(resolve_dsn(args.dsn))

    bars, n_junk = read_prices(storage, args.symbol)
    if not bars:
        print("KHONG co nen nao", file=sys.stderr)
        return 2
    dates = [bar_date(b) for b in bars]
    closes = [b.close for b in bars]
    print(f"# {args.symbol}: {len(bars)} phien ({dates[0]} -> {dates[-1]}), bo {n_junk} phien gia <= 0")
    print(f"# Niem phong: {SEALED_START} — phep do CO doc qua moc nay theo thiet ke da chot truoc.")
    print()

    start_idx = next(i for i, d in enumerate(dates) if d >= MEASURE_FROM)
    end_idx = max(i for i, d in enumerate(dates) if d <= MEASURE_TO)
    print(
        f"# Lam am tu {dates[0]} (chi de uoc luong sigma). Do tu {dates[start_idx]} "
        f"-> {dates[end_idx]} ({end_idx - start_idx + 1} phien)"
    )
    print()

    bh = buy_hold(bars, start_idx, end_idx)

    w_ewma = weights_series(closes, kind="ewma")
    main_res = simulate(bars, w_ewma, REBAL_THRESHOLD, start_idx, end_idx, label="EWMA 0,94 (chinh)")

    variants: list[tuple[str, SimResult]] = [("EWMA 0,94 (chinh)", main_res)]
    w_roll = weights_series(closes, kind="rolling")
    variants.append(
        ("sigma = do lech chuan 20 phien", simulate(bars, w_roll, REBAL_THRESHOLD, start_idx, end_idx))
    )
    for th in (0.10, 0.30):
        variants.append(
            (f"nguong {th:.2f}".replace(".", ","), simulate(bars, w_ewma, th, start_idx, end_idx))
        )

    garch_note = ""
    if not args.no_garch:
        try:
            import arch  # noqa: F401  (chi kiem tra co mat)

            g_vols = garch_vol_series(log_returns(closes), refit_every=GARCH_REFIT_EVERY)
            g_targets = expanding_median(g_vols)
            w_g = target_weights(g_vols, g_targets)
            variants.append(
                (
                    "GARCH(1,1) refit 21 phien",
                    simulate(bars, w_g, REBAL_THRESHOLD, start_idx, end_idx),
                )
            )
            gp = garch_persistence(log_returns(closes), refit_every=GARCH_REFIT_EVERY)
            if gp:
                garch_note = (
                    f"# GARCH(1,1) lan uoc luong cuoi ({int(gp['n_fits'])} lan refit): "
                    f"omega={gp['omega']:.4f}, alpha={gp['alpha']:.4f}, beta={gp['beta']:.4f}, "
                    f"alpha+beta={gp['alpha_plus_beta']:.4f} (don vi loi suat %^2)"
                )
        except ImportError:
            garch_note = "# GARCH: KHONG co module `arch` -> bo qua bien the nay (chay `uv run --with arch ...`)"

    rows = [("mua-va-giu 100%", summarize(bh))] + [(n, summarize(r)) for n, r in variants]
    print("### Bang tong (sau moi chi phi)")
    print_summary_table(rows)
    print()
    if garch_note:
        print(garch_note)
        print()

    print("### Theo nam: bien the chinh vs mua-va-giu")
    print_year_table(main_res, bh)
    print()

    # Mua-va-giu rieng 2017-2022 (Claude doi chieu voi phep do cu)
    i22 = max(i for i, d in enumerate(dates) if d <= date(2022, 12, 31))
    bh_1722 = buy_hold(bars, start_idx, i22)
    s1722 = summarize(bh_1722)
    print("### Mua-va-giu rieng 2017-2022 (de doi chieu phep do cu)")
    print(
        f"  {bar_date(bars[start_idx])} -> {bar_date(bars[i22])}: "
        f"gross={bh_1722.equity_curve[-1] / bh_1722.equity_curve[0]:.4f}, "
        f"CAGR={fmt_pct(s1722['cagr'])}, MDD={fmt_pct(s1722['mdd'])}"
    )
    print()

    # Ket luan theo tieu chi da chot
    sm, sb = summarize(main_res), summarize(bh)
    a_ok = sm["mdd"] <= (2.0 / 3.0) * sb["mdd"]
    b_ok = sm["cagr"] >= sb["cagr"] - 0.01
    print("### Ket luan theo tieu chi da chot (chi xet bien the chinh)")
    print(
        f"  (a) MDD chinh {fmt_pct(sm['mdd'])} <= 2/3 x MDD mua-va-giu "
        f"({fmt_pct((2.0 / 3.0) * sb['mdd'])}) : {'DAT' if a_ok else 'KHONG DAT'}"
    )
    print(
        f"  (b) CAGR chinh {fmt_pct(sm['cagr'])} >= CAGR mua-va-giu {fmt_pct(sb['cagr'])} - 1,0 diem % "
        f"({fmt_pct(sb['cagr'] - 0.01)}) : {'DAT' if b_ok else 'KHONG DAT'}"
    )
    print(f"  => {'DAT' if (a_ok and b_ok) else 'KHONG DAT'}")
    print()
    print(f"# CAGR neu annualize theo 252 phien: chinh {fmt_pct(sm['cagr_sessions'])}, "
          f"mua-va-giu {fmt_pct(sb['cagr_sessions'])}")
    print(f"# Xong sau {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
