"""Tests cho OctopusPullbackStrategy (brief 2026-08-15-hermes-octopus-pullback.md).

Strong Long = đồng thời:
1. close > EMA(200)
2. >= 2 nến đỏ (close < open) trong 5 phiên gần nhất, TRƯỚC bar hiện tại
3. EMA(9) cắt LÊN EMA(21) (prev EMA9 <= EMA21, now EMA9 > EMA21) VÀ MACD hist > 0
Bộ lọc thanh khoản point-in-time: bình quân close*volume 20 phiên TRƯỚC bar
hiện tại >= 2 tỷ, kiểm tại bar sinh tín hiệu.

Các chuỗi giá dưới đây được kiểm chứng bằng EmaCalculator/MacdCalculator độc lập
(xem commit message của test_indicators.py) — đây là fixture tham chiếu, không tự
xác nhận bằng chính strategy.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.octopus_pullback import OctopusPullbackStrategy


class FakeContext:
    def __init__(self, qty=0, positions=None):
        self.qty = qty
        self.positions = positions or {}

    def position_qty(self, symbol):
        return self.qty


def bar_at(i, close, open_=None, high=None, low=None, volume=10_000_000, symbol="VCB"):
    """open mặc định = close trước (tạo nến đỏ khi giảm), như chuỗi đã kiểm chứng."""
    open_ = close if open_ is None else open_
    high = close if high is None else high
    low = close if low is None else low
    return Bar(
        symbol,
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(days=i),
        open_,
        high,
        low,
        close,
        volume,
    )


def base_series(symbol="VCB", volume=10_000_000):
    """0..199 tăng 100+i; 200..207 giảm 2.0 (5 nến đỏ); 208 bounce +15.

    Kiểm chứng độc lập tại bar 208: close>EMA200, reds5=5, cross=True,
    hist=+3.94 — đủ 3 điều kiện. Volume 10M * close ~ 283-299 -> ~2.8-3 tỷ
    >= 2 tỷ (đạt thanh khoản)."""
    closes = []
    for i in range(209):
        if i < 200:
            closes.append(100.0 + i)
        elif i < 208:
            closes.append(closes[-1] - 2.0)
        else:
            closes.append(closes[-1] + 15.0)
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(bar_at(i, c, open_=o, volume=volume, symbol=symbol))
    return bars


def feed(strategy, bars):
    return [strategy.compute_crossover(b) for b in bars]


def test_warmup_bars_and_none_before_full_history():
    s = OctopusPullbackStrategy()
    # max(200, 26+9) + 1 = 201
    assert s.warmup_bars == 201
    assert s.qty == 100
    bars = base_series()[:200]  # thiếu 1 bar so với warmup
    results = feed(s, bars)
    assert results == [None] * 200


def test_bull_when_all_three_conditions():
    s = OctopusPullbackStrategy()
    bars = base_series()
    results = feed(s, bars)
    assert results[208] == "bull"
    assert results[207] is None  # chưa bounce -> chưa cắt lên


def test_none_below_ema200():
    """Chuỗi giảm đều: close luôn dưới EMA200 -> không bao giờ bull."""
    s = OctopusPullbackStrategy()
    bars = [
        bar_at(i, 400.0 - i) for i in range(209)
    ]  # 400 -> 191, giảm đều
    results = feed(s, bars)
    assert all(r is None for r in results)


def red_window_series(symbol="VCB"):
    """Pha giảm 7 nến NGOÀI cửa sổ, 2 xanh, 1 đỏ nhẹ (t-4), 3 doji, bar t ĐỎ
    (gap-up: open > close nhưng close > close trước). Tại bar t (index 213):
    cross=True, hist>0, close>EMA200, [t-5..t-1] có ĐÚNG 1 nến đỏ, bar t đỏ.
    → Đúng đặc tả (chỉ 5 phiên TRƯỚC bar t): 1 đỏ < 2 → None.
    → Code cũ (tính cả bar t): cửa sổ = 2 đỏ → "bull" (SAI)."""
    closes = []
    for i in range(200):
        closes.append(100.0 + i)
    c = closes[-1]
    for _ in range(7):
        c -= 2.0
        closes.append(c)
    for _ in range(2):
        c += 1.0
        closes.append(c)
    c -= 1.0
    closes.append(c)  # t-4: nến đỏ nhẹ duy nhất trong window
    for _ in range(3):
        closes.append(c)  # doji
    closes.append(c + 10.0)  # bar t: close tăng mạnh
    t = len(closes) - 1
    bars = []
    for i, cl in enumerate(closes):
        if i == t:
            o = closes[i - 1] + 11.0  # open cao hơn close -> nến ĐỎ
        else:
            o = closes[i - 1] if i > 0 else cl
        bars.append(bar_at(i, cl, open_=o, symbol=symbol))
    return bars


def test_current_red_bar_not_counted_in_pullback_window():
    """Lỗi off-by-one: bar hiện tại ĐỎ KHÔNG được tính vào cửa sổ nến đỏ.
    [t-5..t-1] có 1 nến đỏ (dưới ngưỡng 2), bar t đỏ (close < open nhưng
    close > close trước — nến đỏ không nhất thiết giá giảm). Các điều kiện
    khác (cross, hist>0, close>EMA200, thanh khoản) đều đạt tại t.
    → Đúng đặc tả: 1 đỏ trong 5 phiên TRƯỚC -> None.
    → Code cũ (cửa sổ gồm bar t): thấy 2 đỏ -> "bull" (SAI, test phải bắt)."""
    s = OctopusPullbackStrategy()
    bars = red_window_series()
    results = feed(s, bars)
    t = len(bars) - 1
    assert results[t] is None


def test_none_when_not_enough_red_candles():
    """1 nến đỏ MẠNH duy nhất ở 202 (đẩy EMA9 xuống dưới EMA21), 203..207 xanh
    nhẹ, bounce 208: cross + hist + EMA200 đều đạt nhưng reds5 = 0 -> None."""
    s = OctopusPullbackStrategy()
    closes = []
    for i in range(209):
        if i < 200:
            closes.append(100.0 + i)
        elif i == 200 or i == 201:
            closes.append(closes[-1] + 1.0)
        elif i == 202:
            closes.append(closes[-1] - 25.0)  # nến đỏ mạnh duy nhất
        elif i < 208:
            closes.append(closes[-1] + 1.0)
        else:
            closes.append(closes[-1] + 30.0)
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(bar_at(i, c, open_=o))
    results = feed(s, bars)
    assert results[208] is None


def test_none_when_no_cross():
    """Chuỗi cơ sở nhưng bar 208 giảm tiếp (không bounce): hist vẫn dương,
    đủ nến đỏ, close > EMA200 — nhưng EMA9 không cắt lên -> None."""
    s = OctopusPullbackStrategy()
    bars = base_series()
    bars[208] = bar_at(208, bars[207].close - 2.0,
                       open_=bars[207].close)
    results = feed(s, bars)
    assert results[208] is None


def test_none_when_histogram_non_positive():
    """0..189 tăng; 190..199 giảm 5.0 (10 nến đỏ); 200 bounce +100: cross=True,
    reds5=5, close>EMA200 nhưng hist = -0.76 <= 0 -> None."""
    s = OctopusPullbackStrategy()
    closes = []
    for i in range(201):
        if i < 190:
            closes.append(100.0 + i)
        elif i < 200:
            closes.append(closes[-1] - 5.0)
        else:
            closes.append(closes[-1] + 100.0)
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(bar_at(i, c, open_=o))
    results = feed(s, bars)
    assert results[200] is None


def test_symbol_state_isolated():
    s = OctopusPullbackStrategy()
    vcb = base_series(symbol="VCB")
    for i, b in enumerate(vcb):
        r = s.compute_crossover(b)
        if i == 208:
            assert r == "bull"
    # HPG chỉ 5 bar — không đủ warmup riêng, không được hưởng state VCB
    hpg = [bar_at(i, 5.0, symbol="HPG") for i in range(5)]
    assert all(s.compute_crossover(b) is None for b in hpg)
    # VCB vẫn nguyên sau khi HPG chen vào: bar 209 close bằng close 208
    # (không tạo cross mới vì prev EMA9 đã > EMA21) -> None
    b209 = bar_at(209, 298.0, open_=298.0, symbol="VCB")
    assert s.compute_crossover(b209) is None


def test_liquidity_filter_blocks_low_value():
    """Cùng chuỗi cơ sở nhưng volume nhỏ (close*volume ~ 291M < 2 tỷ):
    đủ 3 điều kiện kỹ thuật nhưng bị chặn bởi thanh khoản -> None."""
    s = OctopusPullbackStrategy()
    bars = base_series(volume=1_000_000)
    results = feed(s, bars)
    assert results[208] is None


def test_liquidity_20_window_excludes_current_bar():
    """Bar hiện tại volume KHỔNG LỒ nhưng 20 phiên trước volume nhỏ:
    cửa sổ không tính bar hiện tại -> vẫn None (không đủ thanh khoản quá khứ)."""
    s = OctopusPullbackStrategy()
    bars = base_series(volume=1_000_000)
    # bar 208 (tín hiệu) volume khổng lồ — nhưng 20 phiên trước vẫn nhỏ
    bars[208] = bar_at(208, bars[207].close + 15.0,
                       open_=bars[207].close, volume=100_000_000_000)
    results = feed(s, bars)
    assert results[208] is None


def test_liquidity_passes_when_prior_20_are_high():
    """Bar hiện tại volume = 0 nhưng 20 phiên trước volume lớn (đã tính khi
    feed 20 bar trước): cửa sổ dùng 20 phiên TRƯỚC -> tín hiệu vẫn được nhận."""
    s = OctopusPullbackStrategy()
    bars = base_series(volume=10_000_000)
    # bar 208 volume 0 — không ảnh hưởng avg20 (đã tính từ 20 phiên trước)
    bars[208] = bar_at(208, bars[207].close + 15.0,
                       open_=bars[207].close, volume=0)
    results = feed(s, bars)
    assert results[208] == "bull"


def test_on_bar_buys_when_flat():
    s = OctopusPullbackStrategy(qty=100)
    ctx = FakeContext(qty=0)
    bars = base_series()
    for i, b in enumerate(bars):
        sig = s.on_bar(b, ctx)
        if i == 208:
            assert sig is not None and sig.side == "BUY" and sig.qty == 100
        else:
            assert sig is None


def test_on_bar_no_buy_when_already_holding():
    """Đang giữ 100 cp -> bull không mua thêm. Dùng chuỗi có high/low rộng để
    ATR > 0, TP không chạm ngay trong vòng lặp (chỉ kiểm không có BUY)."""
    s = OctopusPullbackStrategy(qty=100)
    ctx = FakeContext(qty=100)
    bars = []
    for i, b in enumerate(base_series()):
        bars.append(bar_at(i, b.close, open_=b.open,
                           high=b.close * 1.03, low=b.close * 0.97))
    for i, b in enumerate(bars):
        sig = s.on_bar(b, ctx)
        assert sig is None or sig.side != "BUY"  # không mua thêm khi đang giữ


def test_take_profit_sells_at_entry_plus_2atr():
    """TP = giá vào + 2*ATR(14): giá vào = open của bar ĐẦU TIÊN thấy vị thế
    (bar fill, giống run_backtest: BUY signal bar t -> fill bar t+1 open).
    Sau khi TP được set, close chạm TP -> SELL toàn bộ."""
    s = OctopusPullbackStrategy(qty=100, atr_period=14, tp_atr_mult=2.0)
    # Chuỗi có high/low dao động để ATR > 0; volume đủ thanh khoản
    closes = []
    for i in range(209):
        if i < 200:
            closes.append(100.0 + i)
        elif i < 208:
            closes.append(closes[-1] - 2.0)
        else:
            closes.append(closes[-1] + 15.0)
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(bar_at(i, c, open_=o, high=c * 1.03, low=c * 0.97))
    ctx = FakeContext(qty=0)
    buy_bar = None
    for i, b in enumerate(bars):
        sig = s.on_bar(b, ctx)
        if i == 208 and sig is not None and sig.side == "BUY":
            buy_bar = b
            break
    assert buy_bar is not None
    ctx.qty = 100  # đã khớp BUY
    # Bar fill: bar đầu tiên strategy thấy vị thế -> giá vào = open bar này
    fill_open = buy_bar.close  # open bar sau = close bar tín hiệu
    fill_bar = bar_at(209, fill_open + 3.0, open_=fill_open,
                      high=(fill_open + 3.0) * 1.03, low=(fill_open + 3.0) * 0.97)
    sig_fill = s.on_bar(fill_bar, ctx)
    assert sig_fill is None  # chưa chạm TP
    atr = s.last_atr("VCB")
    assert atr is not None and atr > 0
    # close vượt fill_open + 2*ATR -> SELL toàn bộ
    tp_bar = bar_at(210, fill_open + 5 * atr, open_=fill_open + 3.0,
                    high=fill_open + 5 * atr, low=fill_open + 4 * atr)
    sig = s.on_bar(tp_bar, ctx)
    assert sig is not None and sig.side == "SELL" and sig.qty == 100


def test_last_atr_tracks_per_symbol():
    s = OctopusPullbackStrategy(atr_period=1)
    assert s.last_atr("VCB") is None
    b = bar_at(0, 10.0, high=10.0, low=10.0)
    s.compute_crossover(b)
    assert s.last_atr("VCB") == 0.0  # TR = high-low = 0
    b2 = bar_at(1, 20.0, high=20.0, low=20.0)
    s.compute_crossover(b2)
    assert s.last_atr("VCB") == 10.0  # TR = |20-10| = 10


# ---------------------------------------------------------------------------
# Brief đợt 107 — tái dựng take-profit sau khi engine khởi động lại
# ---------------------------------------------------------------------------

def _tp_bars(n, sym="AAA", start=None):
    """n bar 15' có biên độ thật (TR > 0) để ATR có giá trị khác 0."""
    start = start or datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
    out = []
    for i in range(n):
        o = 100.0 + (i % 7) * 0.5
        c = o + (0.4 if i % 3 else -0.3)
        out.append(
            Bar(
                sym,
                start + timedelta(minutes=15 * i),
                o,
                max(o, c) + 0.2,
                min(o, c) - 0.2,
                c,
                10_000_000,
            )
        )
    return out


def test_restore_take_profit_bang_dung_tp_luong_song():
    """§1 brief 107: TP khôi phục phải bằng ĐÚNG TP luồng sống tính ở bar neo A.

    Luồng sống: warm-up `warmup_bars` bar (main.py:255-268), rồi bar cuối là bar
    neo A — logic.py:36 nạp broker TRƯỚC logic.py:44 gọi strategy.on_bar, nên bar
    mà lệnh BUY khớp CHÍNH LÀ bar đầu tiên `on_bar` thấy held > 0.
    """
    sym = "AAA"
    live = OctopusPullbackStrategy()
    bars = _tp_bars(live.warmup_bars, sym=sym)
    for b in bars[:-1]:
        live.compute_crossover(b)
    assert live.on_bar(bars[-1], FakeContext(qty=100)) is None
    tp_live = live._tp[sym]
    assert tp_live > 0

    fresh = OctopusPullbackStrategy()
    tp_restored = fresh.restore_take_profit(sym, bars)

    assert tp_restored == tp_live  # cố ý == tuyệt đối, không dùng approx
    assert fresh._tp[sym] == tp_live


def test_restore_take_profit_none_khi_thieu_bar():
    """Thiếu bar (< atr_period + 1) → None và KHÔNG ghi `_tp` (để luồng sống neo lại)."""
    s = OctopusPullbackStrategy()
    bars = _tp_bars(s.atr_period, sym="AAA")  # 14 bar, cần >= 15
    assert s.restore_take_profit("AAA", bars) is None
    assert "AAA" not in s._tp


def test_on_bar_sau_khoi_phuc_khong_neo_lai_tp():
    """Sau khôi phục, bar sau KHÔNG neo lại TP theo giá mở cửa bar đó.

    Có ĐỐI CHỨNG: cùng chuỗi bar, chiến lược KHÔNG khôi phục (đúng như code cũ
    sau restart) thì neo lại TP theo open bar này và bán — nếu không có đối
    chứng thì test không phân biệt được hai hành vi.
    """
    sym = "AAA"
    s = OctopusPullbackStrategy()
    bars = _tp_bars(s.warmup_bars, sym=sym)
    tp = s.restore_take_profit(sym, bars)
    assert tp is not None

    nxt = bars[-1].ts + timedelta(minutes=15)
    o = tp - 5.0
    c = tp - 0.5  # dưới TP khôi phục, trên TP nếu bị neo lại
    b1 = Bar(sym, nxt, o, max(o, c) + 0.2, min(o, c) - 0.2, c, 10_000_000)

    ctrl = OctopusPullbackStrategy()  # KHÔNG khôi phục -> neo lại ở b1
    for b in bars[:-1]:
        ctrl.compute_crossover(b)
    ctrl_sig = ctrl.on_bar(b1, FakeContext(qty=100))
    assert ctrl_sig is not None and ctrl_sig.side == "SELL", (
        "đối chứng: không khôi phục thì neo lại TP theo open bar này và bán"
    )
    assert s.on_bar(b1, FakeContext(qty=100)) is None, (
        "đã khôi phục TP thì KHÔNG được bán theo mức neo lại"
    )

    b2 = Bar(sym, nxt + timedelta(minutes=15), c, tp + 1.0, c, tp + 0.5, 10_000_000)
    sig = s.on_bar(b2, FakeContext(qty=100))
    assert sig is not None and sig.side == "SELL" and sig.qty == 100
