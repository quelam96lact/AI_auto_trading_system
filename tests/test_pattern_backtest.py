"""Unit tests cho module mô phỏng lệnh STOP trading/pattern_backtest.py (Gói P3).

Kiểm thử:
1. Tiêu chí 2: Khớp lệnh đúng quy ước gap (gap-up qua BUY/STOP, gap-down qua SELL/STOP, gap qua SL/TP).
2. Tiêu chí 3: Thứ tự SL/TP trong cùng 1 nến (sl_first=True -> SL, sl_first=False -> TP).
3. Tiêu chí 5: Ràng buộc T+2.5 chặn thoát vị thế trước ngày settle (premature_touch).
4. Long & Short trên Crypto vs Long-only trên VN Stock.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.pattern_backtest import run_pattern_backtest
from trading.trailing_stop import fill_price_on_touch


def _make_bar(
    symbol: str = "TEST",
    idx: int = 0,
    open: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 100.0,
    volume: int = 10_000,
) -> Bar:
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=base_time + timedelta(days=idx),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


# ---------------------------------------------------------------------------
# 1. Tests cho quy ước gap (Tiêu chí 2)
# ---------------------------------------------------------------------------


def test_fill_price_on_touch_buy_stop_gap_up():
    """BUY/STOP: Entry = 105.0. Bar mở cửa GAP UP tại 110.0 (high=115, low=108).
    Quy ước gap: Khớp tại open (110.0), không phải mức danh nghĩa 105.0.
    """
    b = _make_bar(open=110.0, high=115.0, low=108.0, close=112.0)
    fill = fill_price_on_touch(b, level=105.0, side="buy")
    assert fill == 110.0  # max(110.0, 105.0)


def test_fill_price_on_touch_sell_stop_gap_down():
    """SELL/STOP: Entry = 95.0. Bar mở cửa GAP DOWN tại 90.0 (high=92, low=85).
    Quy ước gap: Khớp tại open (90.0), không phải mức danh nghĩa 95.0.
    """
    b = _make_bar(open=90.0, high=92.0, low=85.0, close=88.0)
    fill = fill_price_on_touch(b, level=95.0, side="sell")
    assert fill == 90.0  # min(90.0, 95.0)


def test_fill_price_on_touch_no_gap():
    """Không có gap: Bar xuyên qua level trong phiên -> Khớp đúng level."""
    # Buy xuyên qua 105 (open=100, high=110)
    b_buy = _make_bar(open=100.0, high=110.0, low=98.0, close=108.0)
    assert fill_price_on_touch(b_buy, level=105.0, side="buy") == 105.0

    # Sell thủng qua 95 (open=100, low=90)
    b_sell = _make_bar(open=100.0, high=102.0, low=90.0, close=92.0)
    assert fill_price_on_touch(b_sell, level=95.0, side="sell") == 95.0


# ---------------------------------------------------------------------------
# 2. Tests cho thứ tự SL/TP trong cùng 1 nến (Tiêu chí 3)
# ---------------------------------------------------------------------------


def test_sl_tp_both_touched_order_assumption():
    """Khi nến có biên độ cực lớn chạm cả SL và TP:
    - sl_first=True: Phải tính là dính SL trước (mặc định bi quan).
    - sl_first=False: Phải tính là dính TP trước.
    """
    bars = []
    # 35 bar nền giảm nhẹ rồi tạo búa
    price = 200.0
    for i in range(35):
        price -= 2.0
        bars.append(
            _make_bar(idx=i, open=price + 2, high=price + 3, low=price - 1, close=price)
        )

    # Bar 35: Tạo nến Hammer chuẩn
    # range = 130 - 100 = 30; body = 2.0 (128-130); lower = 28.0 (14x body); upper = 0
    bars.append(_make_bar(idx=35, open=128.0, high=130.0, low=100.0, close=130.0))

    # Bar 36: Khớp BUY/STOP entry (entry ~ 130 + x)
    bars.append(_make_bar(idx=36, open=131.0, high=135.0, low=129.0, close=133.0))

    # Bar 37: Nến khổng lồ (high = 200, low = 50) -> Chạm CẢ SL (~98) và TP (~140)
    bars.append(_make_bar(idx=37, open=133.0, high=200.0, low=50.0, close=130.0))

    # Chạy với sl_first = True
    rep_sl = run_pattern_backtest(bars, strategy_name="hammer", sl_first=True)
    assert rep_sl.total_trades == 1
    assert rep_sl.both_touched_count >= 1
    assert rep_sl.trades[0].reason == "SL"
    assert rep_sl.trades[0].pnl < 0  # Lỗ vì dính SL

    # Chạy với sl_first = False
    rep_tp = run_pattern_backtest(bars, strategy_name="hammer", sl_first=False)
    assert rep_tp.total_trades == 1
    assert rep_tp.both_touched_count >= 1
    assert rep_tp.trades[0].reason == "TP"
    assert rep_tp.trades[0].pnl > 0  # Lãi vì dính TP


# ---------------------------------------------------------------------------
# 3. Tests cho ràng buộc T+2.5 trên Cổ phiếu VN (Tiêu chí 5)
# ---------------------------------------------------------------------------


def test_t25_settlement_prevents_premature_exit():
    """Khi settle_days = 3 (T+2.5 VN):
    Nếu SL/TP bị chạm vào ngày D+1 sau khi mua, vị thế KHÔNG được thoát ngay
    mà ghi nhận premature_touch_count và giữ vị thế.
    """
    bars = []
    price = 200.0
    for i in range(35):
        price -= 2.0
        bars.append(
            _make_bar(idx=i, open=price + 2, high=price + 3, low=price - 1, close=price)
        )

    # Bar 35: Hammer
    bars.append(_make_bar(idx=35, open=128.0, high=130.0, low=100.0, close=130.0))

    # Bar 36 (Ngày D): Khớp BUY
    bars.append(_make_bar(idx=36, open=131.0, high=135.0, low=129.0, close=133.0))

    # Bar 37 (Ngày D+1): Giá sập mạnh chạm SL (low = 80) nhưng CHƯA đủ settle T+2.5 (mới D+1)
    bars.append(_make_bar(idx=37, open=125.0, high=126.0, low=80.0, close=85.0))

    rep = run_pattern_backtest(
        bars, strategy_name="hammer", settle_days=3, sl_first=True
    )
    # Tại ngày D+1 (Bar 37) không được thoát lệnh
    assert rep.premature_touch_count >= 1
    assert rep.total_trades == 0  # Vẫn đang giữ vị thế do kẹt T+2.5


# ---------------------------------------------------------------------------
# Bar rác — thêm khi Claude audit 06/09 (module đã SẬP thật trên dữ liệu thật)
# ---------------------------------------------------------------------------


def test_bar_rac_bi_loai_hoan_toan_khoi_phep_do():
    """Bar co OHLC <= 0 phai bi loai TRUOC khi vao vong.

    Bat bien: ket qua tren chuoi CO bar rac phai TRUNG KHIT ket qua tren chuoi
    da tu tay bo bar rac. Manh hon "khong sap", vi bar rac con lam lech ca
    ATR/MACD/MA20 chu khong chi gay ZeroDivisionError.

    Da sap THAT khi audit 06/09: chay du 1.554 ma bars_daily (bang do co 71.439
    bar OHLC <= 0) thi int(capital / executed_price) chia cho 0 — nhanh SELL
    khop tai min(bar.open, level) = 0 khi bar co open = 0.

    _is_dirty la quy uoc dung chung cua repo (backtest.py + 3 script khac).
    """
    sach: list[Bar] = []
    price = 200.0
    for i in range(60):
        # Chuoi giam dan de combo phat tin hieu SELL (nhanh gay sap)
        price -= 1.5
        sach.append(
            _make_bar(
                idx=i, open=price + 1.0, high=price + 2.0, low=price - 2.0, close=price
            )
        )

    # Cung chuoi do nhung xen bar rac (open = 0 -> nhanh SELL khop gia 0)
    co_rac: list[Bar] = []
    for i, b in enumerate(sach):
        co_rac.append(b)
        if i % 11 == 10:
            co_rac.append(
                _make_bar(idx=i, open=0.0, high=0.0, low=0.0, close=0.0, volume=0)
            )

    kw = {"strategy_name": "combo", "capital": 100_000_000.0, "settle_days": 0}
    rep_sach = run_pattern_backtest(sach, **kw)
    rep_rac = run_pattern_backtest(co_rac, **kw)

    assert len(rep_rac.trades) == len(rep_sach.trades)
    assert rep_rac.realized_pnl == rep_sach.realized_pnl
    for t in rep_rac.trades:
        assert t.entry_price > 0.0


# ---------------------------------------------------------------------------
# 5. Tests cho Octopus + Combo Hybrid Strategy
# ---------------------------------------------------------------------------


def test_octopus_combo_requires_trend_pullback_and_buy_stop():
    """Kiểm thử chiến lược Octopus + Combo:
    1. Cần xu hướng Close > EMA200
    2. Cần >= 2 nến đỏ trong 5 phiên trước
    3. Cần nến xanh kích hoạt + EMA9 > EMA21 + MACD > 0
    4. Cần vượt đỉnh bằng lệnh BUY STOP ở bar sau mới khớp.
    """
    bars: list[Bar] = []
    # Khởi tạo 210 bar xu hướng tăng nhẹ để EMA200 ổn định quanh mức 100-110
    p = 100.0
    for i in range(210):
        p += 0.2
        bars.append(
            _make_bar(
                idx=i,
                open=p,
                high=p + 1.0,
                low=p - 1.0,
                close=p + 0.1,
                volume=20_000_000,  # ~2.8 tỷ/ngày
            )
        )

    # 3 phiên điều chỉnh đỏ (Close < Open)
    for i in range(3):
        p -= 0.5
        bars.append(
            _make_bar(
                idx=210 + i,
                open=p + 0.4,
                high=p + 0.6,
                low=p - 0.4,
                close=p,
                volume=20_000_000,
            )
        )

    # Phiên 213: Nến XANH bật tăng mạnh (Close > Open, Close > EMA200, EMA9 > EMA21, MACD > 0)
    p += 3.0
    bars.append(
        _make_bar(
            idx=213,
            open=p - 2.0,
            high=p + 0.5,
            low=p - 2.2,
            close=p,
            volume=20_000_000,
        )
    )

    # Kịch bản A: Phiên 214 không vượt đỉnh phiên 213 (High thấp hơn High 213 + x)
    # -> Lệnh STOP hết hạn, KHÔNG có lệnh nào được khớp
    bars_no_break = list(bars)
    bars_no_break.append(
        _make_bar(
            idx=214,
            open=p - 0.5,
            high=p + 0.1,  # Thấp hơn high 213 + x
            low=p - 1.0,
            close=p - 0.2,
            volume=20_000_000,
        )
    )
    rep_no_break = run_pattern_backtest(
        bars_no_break,
        strategy_name="octopus_combo",
        min_avg_value_20=2_000_000_000.0,
    )
    assert rep_no_break.total_trades == 0

    # Kịch bản B: Phiên 214 vượt đỉnh phiên 213 -> Khớp lệnh BUY STOP
    bars_break = list(bars)
    bars_break.append(
        _make_bar(
            idx=214,
            open=p,
            high=p + 3.0,  # Vượt đỉnh nến 213 + x
            low=p - 0.2,
            close=p + 2.0,
            volume=20_000_000,
        )
    )
    # Phiên 215: Tiếp tục tăng chạm TP
    bars_break.append(
        _make_bar(
            idx=215,
            open=p + 2.5,
            high=p + 10.0,  # Chạm TP
            low=p + 2.0,
            close=p + 8.0,
            volume=20_000_000,
        )
    )
    rep_break = run_pattern_backtest(
        bars_break,
        strategy_name="octopus_combo",
        min_avg_value_20=2_000_000_000.0,
    )
    assert rep_break.total_trades == 1
    assert rep_break.winning_trades == 1
    assert rep_break.trades[0].reason == "TP"


def test_octopus_combo_blocks_insufficient_liquidity():
    """Kiểm thử bộ lọc thanh khoản: Khối lượng thấp (< 2 tỷ) sẽ không kích hoạt lệnh."""
    bars: list[Bar] = []
    p = 100.0
    for i in range(210):
        p += 0.2
        bars.append(
            _make_bar(
                idx=i,
                open=p,
                high=p + 1.0,
                low=p - 1.0,
                close=p + 0.1,
                volume=100,  # Chỉ 10k - 20k VND/ngày << 2 tỷ
            )
        )
    for i in range(3):
        p -= 0.5
        bars.append(
            _make_bar(
                idx=210 + i,
                open=p + 0.4,
                high=p + 0.6,
                low=p - 0.4,
                close=p,
                volume=100,
            )
        )
    p += 3.0
    bars.append(
        _make_bar(
            idx=213,
            open=p - 2.0,
            high=p + 0.5,
            low=p - 2.2,
            close=p,
            volume=100,
        )
    )
    bars.append(
        _make_bar(
            idx=214,
            open=p,
            high=p + 5.0,
            low=p - 0.2,
            close=p + 4.0,
            volume=100,
        )
    )

    rep = run_pattern_backtest(
        bars,
        strategy_name="octopus_combo",
        min_avg_value_20=2_000_000_000.0,
    )
    assert rep.total_trades == 0  # Bị chặn bởi thanh khoản


def test_octopus_combo_with_trailing_stop():
    """Kiểm thử cơ chế Trailing Stop theo ATR giúp nâng mức SL khi giá lập đỉnh mới."""
    bars: list[Bar] = []
    p = 100.0
    for i in range(210):
        p += 0.2
        bars.append(
            _make_bar(
                idx=i,
                open=p,
                high=p + 1.0,
                low=p - 1.0,
                close=p + 0.1,
                volume=100_000,
            )
        )
    for i in range(3):
        p -= 0.5
        bars.append(
            _make_bar(
                idx=210 + i,
                open=p + 0.4,
                high=p + 0.6,
                low=p - 0.4,
                close=p,
                volume=100_000,
            )
        )
    p += 3.0
    bars.append(
        _make_bar(
            idx=213,
            open=p - 2.0,
            high=p + 0.5,
            low=p - 2.2,
            close=p,
            volume=100_000,
        )
    )
    # Khớp lệnh tại phiên 214
    bars.append(
        _make_bar(
            idx=214,
            open=p,
            high=p + 3.0,
            low=p - 0.2,
            close=p + 2.0,
            volume=100_000,
        )
    )
    # Phiên 215: Giá tiếp tục lên đỉnh cao mới
    bars.append(
        _make_bar(
            idx=215,
            open=p + 2.0,
            high=p + 15.0,
            low=p + 1.0,
            close=p + 12.0,
            volume=100_000,
        )
    )
    # Phiên 216: Giá quay đầu giảm chạm mức Trailing Stop nâng cao
    bars.append(
        _make_bar(
            idx=216,
            open=p + 11.0,
            high=p + 11.5,
            low=p + 2.0,
            close=p + 3.0,
            volume=100_000,
        )
    )

    rep = run_pattern_backtest(
        bars,
        strategy_name="octopus_combo",
        k_tp=50.0,  # TP rất xa để thoát bằng trailing SL
        use_trailing_sl=True,
        trailing_atr_mult=2.0,
    )
    assert rep.total_trades == 1
    assert rep.trades[0].reason == "SL"
    # Nhờ trailing SL kéo lên theo đỉnh p+15, thoát lệnh vẫn có lãi
    assert rep.trades[0].pnl > 0


def test_octopus_combo_short_trigger():
    """Kiểm tra octopus_combo phát hiện tín hiệu SHORT (Bearish Octopus Pullback):
    Downtrend (Close < EMA200 & MA20) + >=2 nến xanh hồi + nến đỏ đảo chiều -> SELL STOP.
    """
    bars = []
    p = 300.0
    # 210 nến downtrend
    for i in range(210):
        p -= 0.5
        bars.append(
            _make_bar(
                idx=i,
                open=p + 0.6,
                high=p + 0.8,
                low=p - 0.6,
                close=p,
                volume=100_000,
            )
        )
    # 3 nến xanh hồi phục
    for i in range(3):
        p += 0.5
        bars.append(
            _make_bar(
                idx=210 + i,
                open=p - 0.4,
                high=p + 0.6,
                low=p - 0.6,
                close=p,
                volume=100_000,
            )
        )
    # 1 nến đỏ đảo chiều mạnh
    p -= 3.0
    bars.append(
        _make_bar(
            idx=213,
            open=p + 2.5,
            high=p + 2.7,
            low=p - 0.5,
            close=p,
            volume=100_000,
        )
    )
    # Nến 214: Sập gãy đáy nến đỏ trước -> Khớp lệnh SELL STOP
    bars.append(
        _make_bar(
            idx=214,
            open=p,
            high=p + 0.2,
            low=p - 4.0,
            close=p - 3.5,
            volume=100_000,
        )
    )
    # Nến 215: Tiếp tục sập mạnh -> Chạm TP của vị thế Short
    bars.append(
        _make_bar(
            idx=215,
            open=p - 3.5,
            high=p - 3.0,
            low=p - 20.0,
            close=p - 18.0,
            volume=100_000,
        )
    )

    rep = run_pattern_backtest(
        bars,
        strategy_name="octopus_combo",
        k_tp=1.5,
        allow_short=True,
    )
    assert rep.total_trades >= 1
    assert all(t.side == "SELL" for t in rep.trades)
    assert rep.trades[-1].reason == "TP"
    assert rep.trades[-1].pnl > 0

