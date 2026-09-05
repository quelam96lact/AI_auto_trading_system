"""Mô phỏng backtest chuyên biệt cho 3 chiến lược nến (Hammer, Combo, Doji) với lệnh STOP (Gói P3).

RÀNG BUỘC THIẾT KẾ (Brief 2026-09-06-brief-dot-7-P2-P3.md):
1. Tự chứa, độc lập, KHÔNG sửa đổi PaperBroker hay run_backtest.
2. Sử dụng quy ước khớp lệnh fill_price_on_touch từ trading/trailing_stop.py (xử lý gap nhất quán).
3. Hỗ trợ song song 2 giả định thứ tự khi nến chạm cả SL và TP:
   - sl_first=True (Mặc định bi quan: SL trước).
   - sl_first=False (TP trước).
4. Ràng buộc T+2,5 trên cổ phiếu VN: Theo dõi và đếm tỷ lệ chạm SL/TP trước ngày settle.
5. Hỗ trợ cả 2 chiều LONG và SHORT (T+0 trên crypto perp, Long-only trên VN stock).
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from trading.data_quality import is_dirty_bar
from trading.indicators import AtrCalculator, EmaCalculator, MacdCalculator
from trading.models import Bar
from trading.patterns import combo_signal, is_doji, is_hammer
from trading.strategies.octopus_pullback import DailyLiquidityTracker
from trading.trailing_stop import fill_price_on_touch


@dataclass
class PatternTrade:
    symbol: str
    side: Literal["BUY", "SELL"]  # BUY = Long, SELL = Short
    entry_ts: datetime
    exit_ts: datetime | None
    entry_price: float
    exit_price: float | None
    qty: int
    pnl: float
    reason: str  # "TP", "SL", "FORCE_EXIT", etc.
    premature_touch: bool = False  # Chạm SL/TP trước khi đủ settle (T+2.5)
    both_touched: bool = False  # Nến chạm cả SL và TP cùng lúc


@dataclass
class PatternBacktestReport:
    symbol: str
    trades: list[PatternTrade] = field(default_factory=list)
    total_trades: int = 0
    winning_trades: int = 0
    realized_pnl: float = 0.0
    buy_and_hold_pnl: float = 0.0
    both_touched_count: int = 0
    premature_touch_count: int = 0

    @property
    def win_rate(self) -> float:
        return (
            (self.winning_trades / self.total_trades) if self.total_trades > 0 else 0.0
        )


def run_pattern_backtest(
    bars: list[Bar],
    strategy_name: Literal["hammer", "combo", "doji_buy", "doji_sell", "octopus_combo"],
    capital: float = 100_000.0,
    x_atr_ratio: float = 0.1,
    k_tp: float = 1.5,
    sl_first: bool = True,
    fee_rate: float = 0.0,
    sell_tax_rate: float = 0.0,
    slippage_bps: float = 0.0,
    settle_days: int = 0,
    lot_size: int = 1,
    allow_short: bool = True,
    min_avg_value_20: float = 0.0,
    pullback_red: int = 2,
    pullback_window: int = 5,
    ema_fast_period: int = 9,
    ema_slow_period: int = 21,
    ema_trend_period: int = 200,
    use_trailing_sl: bool = False,
    trailing_atr_mult: float = 2.0,
    use_breakeven: bool = False,
    breakeven_atr_mult: float = 1.0,
) -> PatternBacktestReport:
    """Chạy mô phỏng lệnh STOP + SL/TP cho chiến lược nến trên chuỗi bar của 1 mã.

    Args:
        bars: Danh sách bar lịch sử.
        strategy_name: "hammer", "combo", "doji_buy", "doji_sell", "octopus_combo".
        capital: Số vốn ấn định cho mã.
        x_atr_ratio: Hệ số của ATR(5) cho tham số điều chỉnh x (x = x_atr_ratio * ATR).
        k_tp: Hệ số khoảng cách Take Profit theo ATR(5) (TP = Entry +/- k_tp * ATR).
        sl_first: Thứ tự khi nến chạm cả SL và TP (True = SL trước, False = TP trước).
        fee_rate: Tỷ lệ phí giao dịch mỗi chiều.
        sell_tax_rate: Tỷ lệ thuế bán (cổ phiếu VN: 0.001).
        slippage_bps: Trượt giá (basis points).
        settle_days: Số ngày thanh toán T+N (cổ phiếu VN: 3 ngày).
        lot_size: Kích thước lô (Crypto: 1, VN stock: 100).
        allow_short: Cho phép mở vị thế Short (Crypto: True, VN stock: False).
        min_avg_value_20: Ngưỡng thanh khoản bình quân 20 ngày (VN stock: 2 tỷ).
        pullback_red: Số nến đỏ tối thiểu trong cửa sổ pullback.
        pullback_window: Cửa sổ pullback (phiên trước bar hiện tại).
        ema_fast_period: Chu kỳ EMA nhanh.
        ema_slow_period: Chu kỳ EMA chậm.
        ema_trend_period: Chu kỳ EMA xu hướng.
        use_trailing_sl: Bật Trailing Stop theo ATR.
        trailing_atr_mult: Hệ số Trailing Stop theo ATR.
    """
    sym = bars[0].symbol if bars else "UNKNOWN"
    report = PatternBacktestReport(symbol=sym)

    # Loại bỏ bar rác trước khi tính toán
    clean_bars = [b for b in bars if not is_dirty_bar(b)]
    if len(clean_bars) < 30:
        return report

    atr_calc = AtrCalculator(period=5)
    macd_calc = (
        MacdCalculator(fast=12, slow=26, signal=9)
        if strategy_name == "octopus_combo"
        else MacdCalculator(fast=5, slow=25, signal=5)
    )
    ema_fast_calc = EmaCalculator(period=ema_fast_period)
    ema_slow_calc = EmaCalculator(period=ema_slow_period)
    ema_trend_calc = EmaCalculator(period=ema_trend_period)
    liquidity_tracker = DailyLiquidityTracker(window=20)
    reds_deque: deque[int] = deque(maxlen=pullback_window + 1)
    greens_deque: deque[int] = deque(maxlen=pullback_window + 1)
    ma_closes: list[float] = []

    # Trạng thái vị thế đang mở
    pos_side: Literal["BUY", "SELL"] | None = None
    pos_entry_price: float = 0.0
    pos_entry_ts: datetime | None = None
    pos_entry_day_idx: int = 0
    pos_qty: int = 0
    pos_sl: float = 0.0
    pos_tp: float = 0.0
    pos_highest: float = 0.0
    pos_lowest: float = 0.0

    # Lệnh STOP đang chờ kích hoạt (chỉ có hiệu lực trong 1 bar kế tiếp)
    pending_stop: dict | None = None

    slip_factor_buy = 1.0 + slippage_bps / 10000.0
    slip_factor_sell = 1.0 - slippage_bps / 10000.0

    recent_bars: list[Bar] = []
    day_idx = 0
    prev_date = None

    # BAR RÁC đã được loại tại clean_bars ở đầu hàm.

    for i, b in enumerate(clean_bars):
        cur_date = b.ts.date()
        if prev_date is None or cur_date != prev_date:
            day_idx += 1
            prev_date = cur_date

        atr = atr_calc.update(b)
        macd_hist = macd_calc.update(b)
        ma_closes.append(b.close)
        if len(ma_closes) > 20:
            ma_closes.pop(0)
        ma20 = (sum(ma_closes) / 20.0) if len(ma_closes) == 20 else None

        # Cập nhật EMA, Thanh khoản và Chuỗi nến cho Octopus Combo
        if strategy_name == "octopus_combo":
            prev_fast = ema_fast_calc.last(b.symbol)
            prev_slow = ema_slow_calc.last(b.symbol)
            ema_fast = ema_fast_calc.update(b)
            ema_slow = ema_slow_calc.update(b)
            ema_trend = ema_trend_calc.update(b)
            if min_avg_value_20 > 0:
                liquidity_tracker.update(b)
            reds_deque.append(1 if b.close < b.open else 0)
            greens_deque.append(1 if b.close > b.open else 0)

        # -------------------------------------------------------------------
        # 1. Kiểm tra khớp lệnh STOP đang chờ từ bar trước
        # -------------------------------------------------------------------
        if pending_stop is not None and pos_side is None:
            p_side = pending_stop["side"]
            p_entry = pending_stop["entry_level"]
            p_sl = pending_stop["sl_level"]
            p_tp = pending_stop["tp_level"]
            pending_stop = None  # Lệnh STOP hết hạn sau 1 bar

            fill_p = None
            if p_side == "BUY":
                fill_p = fill_price_on_touch(b, p_entry, side="buy")
            elif p_side == "SELL" and allow_short:
                fill_p = fill_price_on_touch(b, p_entry, side="sell")

            if fill_p is not None:
                # Khớp lệnh mở vị thế
                executed_price = fill_p * (
                    slip_factor_buy if p_side == "BUY" else slip_factor_sell
                )
                raw_qty = int(capital / executed_price)
                if lot_size > 1:
                    raw_qty = (raw_qty // lot_size) * lot_size

                if raw_qty > 0:
                    pos_side = p_side
                    pos_entry_price = executed_price
                    pos_entry_ts = b.ts
                    pos_entry_day_idx = day_idx
                    pos_qty = raw_qty
                    pos_sl = p_sl
                    pos_tp = p_tp
                    pos_highest = executed_price
                    pos_lowest = executed_price

        # -------------------------------------------------------------------
        # 2. Quản lý vị thế đang mở (Kiểm tra SL / TP / Trailing Stop)
        # -------------------------------------------------------------------
        if pos_side is not None:
            # Cập nhật Breakeven SL nếu được bật (khi giá đi đúng hướng >= breakeven_atr_mult * ATR)
            if use_breakeven and atr is not None and atr > 0:
                if pos_side == "BUY" and (b.high - pos_entry_price) >= breakeven_atr_mult * atr:
                    pos_sl = max(pos_sl, pos_entry_price)
                elif pos_side == "SELL" and (pos_entry_price - b.low) >= breakeven_atr_mult * atr:
                    pos_sl = min(pos_sl, pos_entry_price)

            # Cập nhật trailing SL nếu được bật
            if pos_side == "BUY" and use_trailing_sl and atr is not None and atr > 0:
                pos_highest = max(pos_highest, b.high)
                trailing_level = pos_highest - trailing_atr_mult * atr
                pos_sl = max(pos_sl, trailing_level)
            elif pos_side == "SELL" and use_trailing_sl and atr is not None and atr > 0:
                pos_lowest = min(pos_lowest, b.low)
                trailing_level = pos_lowest + trailing_atr_mult * atr
                pos_sl = min(pos_sl, trailing_level)

            is_settled = (day_idx - pos_entry_day_idx) >= settle_days
            sl_touch = False
            tp_touch = False
            sl_fill = None
            tp_fill = None

            if pos_side == "BUY":
                # Long: SL khi giá giảm chạm pos_sl, TP khi giá tăng chạm pos_tp
                if b.low <= pos_sl:
                    sl_touch = True
                    sl_fill = (
                        fill_price_on_touch(b, pos_sl, side="sell") * slip_factor_sell
                    )
                if b.high >= pos_tp:
                    tp_touch = True
                    tp_fill = (
                        fill_price_on_touch(b, pos_tp, side="buy") * slip_factor_sell
                    )
            else:
                # Short: SL khi giá tăng chạm pos_sl, TP khi giá giảm chạm pos_tp
                if b.high >= pos_sl:
                    sl_touch = True
                    sl_fill = (
                        fill_price_on_touch(b, pos_sl, side="buy") * slip_factor_buy
                    )
                if b.low <= pos_tp:
                    tp_touch = True
                    tp_fill = (
                        fill_price_on_touch(b, pos_tp, side="sell") * slip_factor_buy
                    )

            both_touched = sl_touch and tp_touch
            if both_touched:
                report.both_touched_count += 1

            if sl_touch or tp_touch:
                if not is_settled:
                    # Chạm trước khi đủ settle (T+2.5 trên VN stock)
                    report.premature_touch_count += 1
                    # Nếu chưa đủ settle thì không được thoát ngay, phải giữ vị thế
                else:
                    # Đã đủ settle -> Thoát vị thế
                    exit_price = None
                    reason = ""

                    if both_touched:
                        if sl_first:
                            exit_price = sl_fill
                            reason = "SL"
                        else:
                            exit_price = tp_fill
                            reason = "TP"
                    elif sl_touch:
                        exit_price = sl_fill
                        reason = "SL"
                    else:
                        exit_price = tp_fill
                        reason = "TP"

                    if exit_price is not None:
                        # Tính PnL
                        entry_val = pos_entry_price * pos_qty
                        exit_val = exit_price * pos_qty
                        fees = entry_val * fee_rate + exit_val * (
                            fee_rate + sell_tax_rate
                        )

                        if pos_side == "BUY":
                            pnl = (exit_val - entry_val) - fees
                        else:
                            pnl = (entry_val - exit_val) - fees

                        report.trades.append(
                            PatternTrade(
                                symbol=sym,
                                side=pos_side,
                                entry_ts=pos_entry_ts,
                                exit_ts=b.ts,
                                entry_price=pos_entry_price,
                                exit_price=exit_price,
                                qty=pos_qty,
                                pnl=pnl,
                                reason=reason,
                                premature_touch=False,
                                both_touched=both_touched,
                            )
                        )
                        report.total_trades += 1
                        if pnl > 0:
                            report.winning_trades += 1
                        report.realized_pnl += pnl

                        # Reset vị thế
                        pos_side = None

        # -------------------------------------------------------------------
        # 3. Phát hiện tín hiệu mới tại bar hiện tại (nếu chưa có vị thế/lệnh)
        # -------------------------------------------------------------------
        if pos_side is None and pending_stop is None and atr is not None and atr > 0:
            x_val = x_atr_ratio * atr

            if strategy_name == "hammer":
                if is_hammer(b, prev_bars=recent_bars, require_history=True):
                    pending_stop = {
                        "side": "BUY",
                        "entry_level": b.high + x_val,
                        "sl_level": b.low - x_val,
                        "tp_level": (b.high + x_val) + k_tp * atr,
                    }

            elif strategy_name == "combo":
                c_sig = combo_signal(b, ma20=ma20, macd_hist=macd_hist)
                if c_sig == "buy":
                    pending_stop = {
                        "side": "BUY",
                        "entry_level": b.high + x_val,
                        "sl_level": b.low - x_val,
                        "tp_level": (b.high + x_val) + k_tp * atr,
                    }
                elif c_sig == "sell" and allow_short:
                    pending_stop = {
                        "side": "SELL",
                        "entry_level": b.low - x_val,
                        "sl_level": b.high + x_val,
                        "tp_level": (b.low - x_val) - k_tp * atr,
                    }

            elif strategy_name == "doji_buy":
                if is_doji(b, prev_bars=recent_bars):
                    pending_stop = {
                        "side": "BUY",
                        "entry_level": b.high + x_val,
                        "sl_level": b.low - x_val,
                        "tp_level": (b.high + x_val) + k_tp * atr,
                    }

            elif (
                strategy_name == "doji_sell"
                and allow_short
                and is_doji(b, prev_bars=recent_bars)
            ):
                pending_stop = {
                    "side": "SELL",
                    "entry_level": b.low - x_val,
                    "sl_level": b.high + x_val,
                    "tp_level": (b.low - x_val) - k_tp * atr,
                }

            elif (
                strategy_name == "octopus_combo"
                and ema_fast is not None
                and ema_slow is not None
                and ema_trend is not None
                and macd_hist is not None
                and prev_fast is not None
                and prev_slow is not None
            ):
                # 4. Thanh khoản:
                liq_ok = True
                if min_avg_value_20 > 0:
                    cur_liq = liquidity_tracker.current_avg()
                    liq_ok = cur_liq is not None and cur_liq >= min_avg_value_20

                if liq_ok:
                    # A. Chiều MUA (LONG / Bullish Pullback)
                    trend_up = b.close > ema_trend and (ma20 is None or b.close > ma20)
                    bull_trigger = (
                        b.close > b.open and ema_fast > ema_slow and macd_hist > 0
                    )
                    reds_ok = False
                    if len(reds_deque) >= pullback_window + 1:
                        reds_count = sum(list(reds_deque)[:pullback_window])
                        reds_ok = reds_count >= pullback_red

                    if trend_up and bull_trigger and reds_ok:
                        pending_stop = {
                            "side": "BUY",
                            "entry_level": b.high + x_val,
                            "sl_level": b.low - x_val,
                            "tp_level": (b.high + x_val) + k_tp * atr,
                        }

                    # B. Chiều BÁN KHỐNG (SHORT / Bearish Rally - chỉ khi allow_short)
                    elif allow_short:
                        trend_down = b.close < ema_trend and (
                            ma20 is None or b.close < ma20
                        )
                        bear_trigger = (
                            b.close < b.open and ema_fast < ema_slow and macd_hist < 0
                        )
                        greens_ok = False
                        if len(greens_deque) >= pullback_window + 1:
                            greens_count = sum(list(greens_deque)[:pullback_window])
                            greens_ok = greens_count >= pullback_red

                        if trend_down and bear_trigger and greens_ok:
                            pending_stop = {
                                "side": "SELL",
                                "entry_level": b.low - x_val,
                                "sl_level": b.high + x_val,
                                "tp_level": (b.low - x_val) - k_tp * atr,
                            }

        recent_bars.append(b)
        if len(recent_bars) > 10:
            recent_bars.pop(0)

    # -----------------------------------------------------------------------
    # Tính Mua & Giữ (Buy & Hold) chuẩn
    # -----------------------------------------------------------------------
    if len(clean_bars) >= 2:
        first_p = clean_bars[0].close
        last_p = clean_bars[-1].close
        if first_p > 0:
            bh_qty = int(capital / first_p)
            if lot_size > 1:
                bh_qty = (bh_qty // lot_size) * lot_size
            if bh_qty > 0:
                bh_entry_val = first_p * bh_qty
                bh_exit_val = last_p * bh_qty
                bh_fees = bh_entry_val * fee_rate + bh_exit_val * (
                    fee_rate + sell_tax_rate
                )
                report.buy_and_hold_pnl = (bh_exit_val - bh_entry_val) - bh_fees

    return report
