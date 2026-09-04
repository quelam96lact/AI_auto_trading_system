"""Conformance test cho hop dong Strategy (plan 04/09 goi B1).

Engine goi NAM thuoc tinh tren strategy — khong phai ba:
  engine/main.py:81,86  -> strategy.warmup_bars        (property, luc warm-up)
  engine/main.py:91     -> strategy.compute_crossover(bar)
  engine/logic.py:43    -> strategy.on_bar(bar, broker)
  engine/logic.py:44    -> strategy.last_crossover(symbol)   (goi KHONG dieu kien)
  engine/logic.py:50    -> strategy.last_atr(symbol)

Moi muc trong STRATEGIES (so dang ky DE DO, trading/backtest.py:290) phai thoả
du hop dong nay — neu khong, nap vao engine se AttributeError ngay bar dau.

KHONG sua trading/backtest.py — chi IMPORT STRATEGIES de quet.
"""


from trading.backtest import STRATEGIES
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.strategy import Context, Strategy


def _bar(sym="HII", i=0, close=10_000.0):
    from datetime import datetime, timedelta

    return Bar(
        sym,
        datetime(2026, 9, 1, 9, 0, tzinfo=TZ) + timedelta(minutes=5 * i),
        close, close + 100, close - 100, close, 1_000_000,
    )


class _Ctx(Context):
    def __init__(self):
        self.held = 0

    def position_qty(self, symbol: str) -> int:
        return self.held


def test_moi_strategy_trong_dang_ky_thoa_hop_dong_protocol():
    """Tung muc STRATEGIES phai co du 5 thuoc tinh engine goi. Dung isinstance
    voi Protocol Strategy — bat ca thieu warmup_bars/compute_crossover (engine
    main.py:81,91) lan last_crossover (logic.py:44)."""
    for name, factory in STRATEGIES.items():
        s = factory()
        assert isinstance(s, Strategy), (
            f"[{name}] khong thoa Strategy Protocol — engine se AttributeError "
            f"ngay bar dau (main.py:81 hoac logic.py:44)"
        )


def test_moi_strategy_engine_path_khong_attributerror():
    """Di dung duong engine: warmup -> on_bar/last_crossover/last_atr tren bar
    dau — khong duoc nem AttributeError (tai hien loi octopus_pullback)."""
    for name, s in ((n, f()) for n, f in STRATEGIES.items()):
        ctx = _Ctx()
        # warm-up du so bar strategy yeu cau
        warmup = s.warmup_bars
        # main.py:82 so sanh `len(hist) < strategy.warmup_bars` — neu strategy
        # khai warmup_bars la method (dung theo chu Protocol cu) thi doc ra
        # bound method va main.py chet TypeError. isinstance() KHONG bat duoc
        # vi Protocol chi kiem tra hasattr.
        assert isinstance(warmup, int), (
            f"[{name}] warmup_bars phai la property tra int, thuc te: {warmup!r}"
        )
        for i in range(warmup + 2):
            s.compute_crossover(_bar("HII", i))
        # bar dau sau warm-up: duong logic.py:43-50
        s.on_bar(_bar("HII", warmup + 3), ctx)
        s.last_crossover("HII")  # logic.py:44 — goi khong dieu kien
        s.last_atr("HII")        # logic.py:50


def test_octopus_pullback_nap_engine_duoc():
    """Truong hop da bi loi that: octopus_pullback thieu last_crossover nen chet
    o logic.py:44. Sau khi bo sung phai co du method + tra ve dung kieu."""
    s = OctopusPullbackStrategy()
    assert hasattr(s, "last_crossover")
    warmup = s.warmup_bars
    for i in range(warmup + 2):
        s.compute_crossover(_bar("HII", i))
    got = s.last_crossover("HII")
    assert got in (None, "bull"), f"last_crossover phai tra None|'bull', thuc te: {got!r}"


def test_duong_phai_sinh_khong_bi_ep():
    """1.3: momentum_breakout/rsi KHONG nam trong STRATEGIES (so dang ky co
    phieu) — chung thuoc duong phai sinh (compute_crossover + qty). Test nay
    chan: neu ai do nhet chung vao STRATEGIES ma chua co on_bar/warmup_bars,
    conformance se bat ngay."""
    assert "momentum_breakout" not in STRATEGIES
    assert "momentum_rsi" not in STRATEGIES
