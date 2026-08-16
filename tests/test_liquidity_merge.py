"""Task B (2026-08-16): gộp công thức thanh khoản về MỘT nguồn.

Hai bản từng lệch nhau:
- trading/backtest.py lọc bar rác (OHLC<=0) TRƯỚC khi strategy nhìn thấy → cửa
  sổ của OctopusPullbackStrategy._liquidity_ok không bao giờ chứa bar rác.
- scripts/measure_strategy.py::ever_liquid append cả bar rác vào cửa sổ rồi
  mới continue → bar rác NẰM TRONG cửa sổ, kéo bình quân xuống dưới ngưỡng.

Test này tái hiện sai lệch: 22 phiên sạch (close*volume = 2,1 tỷ >= 2 tỷ) xen
1 bar rác (close=0, giá trị 0). Strategy (rác bị loại) thấy cửa sổ 20 phiên
sạch → đủ thanh khoản. ever_liquid cũ (rác trong deque) thấy cửa sổ chứa một
giá trị 0 → bình quân = 19*2,1 tỷ / 20 = 1,995 tỷ < 2 tỷ → KHÔNG đủ.

RED: assert ever_liquid(...) is True (khớp strategy) — bản cũ trả False → FAIL.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.measure_strategy import ever_liquid
from tests.test_octopus_pullback import bar_at, feed
from trading.backtest import _is_dirty
from trading.strategies.octopus_pullback import OctopusPullbackStrategy


def test_ever_liquid_matches_strategy_when_dirty_bar_in_window():
    """Bar rác trong cửa sổ: strategy (rác bị loại) = True, ever_liquid cũ
    (rác trong deque, giá trị 0) = False → khẳng định ever_liquid phải cùng
    kết luận strategy (bỏ hẳn bar rác khỏi cửa sổ)."""
    s = OctopusPullbackStrategy()
    bars = []
    for i in range(23):
        if i == 10:
            bars.append(bar_at(i, 0.0, volume=0))  # open=high=low=close=0 -> rác
        else:
            bars.append(bar_at(i, 210.0, volume=10_000_000))  # 2,1 tỷ
    # Mô phỏng đúng run_backtest: loại bar rác TRƯỚC khi strategy nhìn thấy.
    clean = [b for b in bars if not _is_dirty(b)]
    feed(s, clean)
    assert s._liquidity_ok("VCB") is True
    assert ever_liquid(bars, 2_000_000_000.0, 20) is True
