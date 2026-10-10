"""Test cho `scripts/measure_vcb_strategies.py` — Brief đợt 181 §3.

Dữ liệu dựng tay, KHÔNG chạm DB. Mọi ca theo bảng §3 của brief.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import measure_vcb_strategies as mvs
from scripts.screen_donchian_breakout import simulate_symbol as donchian_sim
from scripts.screen_pullback_trend import simulate_symbol as pullback_sim
from scripts.screen_rsi2_reversion import simulate_symbol as rsi2_sim
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.stock_study import net_return

VOL = 25_000_000  # close ~100 -> ~2,5 ty/phan > nguong thanh khoan 2 ty cua ca ba luat


# --- Dung du lieu -------------------------------------------------------------------

def _dates(n: int, start: date = date(2017, 1, 2)) -> list[date]:
    """n ngay GIAO DICH (bo thu Bay, Chu Nhat) bat dau tu 02/01/2017."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bar(d: date, close: float, open_: float | None = None, volume: int = VOL) -> Bar:
    o = close if open_ is None else open_
    return Bar(
        symbol="VCB",
        ts=datetime(d.year, d.month, d.day, tzinfo=TZ),
        open=o,
        high=max(o, close) * 1.001,
        low=min(o, close) * 0.999,
        close=close,
        volume=volume,
    )


def _bars(closes: list[float], opens: list[float] | None = None) -> list[Bar]:
    ds = _dates(len(closes))
    return [_bar(ds[i], c, None if opens is None else opens[i]) for i, c in enumerate(closes)]


def _trend_series() -> list[float]:
    """250 nen di len nhe -> 6 nen giam manh (dieu chinh + qua ban) -> 80 nen tang manh.

    Du de ca ba luat sinh it nhat mot lenh: MA200 da du 200 nen, RSI2 tut duoi 10
    trong dot giam, va dot tang sau do pha dinh 55 phien.
    """
    closes = [100.0]
    for _ in range(249):
        closes.append(closes[-1] * 1.003)
    for _ in range(6):
        closes.append(closes[-1] * 0.97)
    for _ in range(80):
        closes.append(closes[-1] * 1.02)
    return closes


class _FakeStorage:
    """Storage gia: tra ve dung danh sach nen duoc cho, bo qua khoang ngay."""

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def read_daily_bars(self, symbol: str, frm, to) -> list[Bar]:
        return list(self._bars)


# --- Ca 1: goi dung code goc ---------------------------------------------------------

def test_luat_2_3_4_goi_dung_code_goc():
    bars = _bars(_trend_series())
    assert len(bars) >= 300, "du lieu phai >= 300 phien"

    got = mvs.law_trades(bars, mvs.LAW_PULLBACK, "HOSE")
    assert got == pullback_sim(bars, "HOSE", "VCB")
    assert len(got) >= 1, "du lieu phai sinh lenh, neu khong phep so la vo nghia"

    got = mvs.law_trades(bars, mvs.LAW_DONCHIAN, "HOSE")
    assert got == donchian_sim(bars, "HOSE", "VCB")
    assert len(got) >= 1, "du lieu phai sinh lenh, neu khong phep so la vo nghia"

    got = mvs.law_trades(bars, mvs.LAW_RSI2, "HOSE")
    assert got == rsi2_sim(bars, "VCB", "HOSE")
    assert len(got) >= 1, "du lieu phai sinh lenh, neu khong phep so la vo nghia"


# --- Ca 2: loi suat gop va drawdown theo lenh ---------------------------------------

def test_loi_suat_gop_va_drawdown_theo_lenh():
    nets = [0.10, -0.20, 0.05]
    assert abs(mvs.gross_return(nets) - (1.1 * 0.8 * 1.05 - 1.0)) < 1e-12
    assert abs(mvs.gross_return(nets) - (-0.076)) < 1e-12
    # dinh 1,1 -> day 0,88  => drawdown 20%
    assert abs(mvs.max_drawdown_by_trade(nets) - 0.20) < 1e-12
    assert mvs.gross_return([]) == 0.0
    assert mvs.max_drawdown_by_trade([]) == 0.0


# --- Ca 3: moc mua-va-giu ------------------------------------------------------------

def test_moc_mua_va_giu_dung_open_2017_va_close_2022():
    ds = [date(2016, 12, 30), date(2017, 1, 3), date(2022, 12, 30)]
    closes = [45.0, 110.0, 150.0]
    opens = [50.0, 100.0, 149.0]
    bars = [_bar(d, c, o) for d, c, o in zip(ds, closes, opens)]

    bh = mvs.buy_and_hold_vcb(bars)

    assert bh["entry_date"] == date(2017, 1, 3), "phai bo qua nen 2016"
    assert bh["exit_date"] == date(2022, 12, 30)
    assert bh["entry_open"] == 100.0, "vao o OPEN phien dau >= 2017-01-01"
    assert bh["exit_close"] == 150.0
    want = net_return(100.0, 150.0)
    assert abs(bh["gross"] - want) < 1e-12
    # Neu ai do dung close phien dau (110) thay vi open (100), con so se khac:
    assert abs(mvs.buy_and_hold_vcb(bars)["gross"] - net_return(110.0, 150.0)) > 1e-9


# --- Ca 4: bootstrap p --------------------------------------------------------------

def test_bootstrap_p_ba_ca():
    p_all_up = mvs.bootstrap_p([0.01] * 30)
    assert p_all_up == 0.0

    p_sym = mvs.bootstrap_p([0.01, -0.01] * 15)
    assert 0.3 < p_sym < 0.7, f"chuoi doi xung quanh 0 phai ra p giua 0,3 va 0,7: {p_sym}"

    assert mvs.bootstrap_p([0.01, -0.01] * 15) == p_sym, "cung seed phai ra cung p"


# --- Ca 5: cong "dang do tiep" ------------------------------------------------------

_OK = {"n": 20, "mean_net": 0.01, "pf": 2.0, "gross": 2.0, "bh_gross": 1.0, "p": 0.001}


def _gate(**over):
    kw = {**_OK}
    kw.update(over)
    passed, cond = mvs.gate_rule234(**kw)
    return passed, cond


def test_cong_bien_moi_ca_truot_dung_mot_dieu_kien():
    cases = [
        ("n = 19", {"n": 19}, "n_ge_20"),
        ("trung binh = 0", {"mean_net": 0.0}, "mean_positive"),
        ("PF = 1,2 dung bang", {"pf": 1.2}, "pf_gt_1_2"),
        ("loi suat gop = B&H dung bang", {"gross": 1.0, "bh_gross": 1.0}, "gross_gt_bh"),
        ("p = 0,0125 dung bang", {"p": 0.0125}, "p_lt_00125"),
        ("p = 0,03 (truot, khong duoc noi nguong)", {"p": 0.03}, "p_lt_00125"),
    ]
    for name, over, key in cases:
        passed, cond = _gate(**over)
        assert passed is False, f"{name}: phai TRUOT"
        assert cond[key] is False, f"{name}: dieu kien {key} phai sai"
        others = [k for k, v in cond.items() if k != key and not v]
        assert not others, f"{name}: chi duoc truot {key}, nhung cung truot {others}"


def test_cong_dat_du_nam_dieu_kien_thi_qua():
    passed, cond = _gate()
    assert passed is True
    assert all(cond.values()), cond


def test_cong_luat_1_pnl_bang_bh_thi_truot():
    assert mvs.gate_rule1(n_fills=20, pnl=500.0, bh_pnl=100.0)[0] is True
    assert mvs.gate_rule1(n_fills=19, pnl=500.0, bh_pnl=100.0)[0] is False
    assert mvs.gate_rule1(n_fills=20, pnl=0.0, bh_pnl=-100.0)[0] is False
    assert mvs.gate_rule1(n_fills=20, pnl=100.0, bh_pnl=100.0)[0] is False, "PnL = B&H thi truot"


# --- Ca 6: niem phong ---------------------------------------------------------------

def test_niem_phong_nen_2023_thi_nem_loi():
    bars = [_bar(date(2023, 1, 3), 100.0)]
    with pytest.raises(ValueError):
        mvs.load_vcb_bars(_FakeStorage(bars))
