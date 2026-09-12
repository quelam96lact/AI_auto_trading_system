"""Engine mô phỏng backtest cho hợp đồng Perpetual crypto 1H (Brief đợt 37).

Bao gồm hai module độc lập (price-only):
- Module A: Donchian breakout + ATR expansion.
- Module B: Bollinger mean reversion.

Ràng buộc & quy ước:
- Tín hiệu tại close bar t; lệnh sớm nhất đặt từ bar t+1 (chống look-ahead).
- Giả định bi quan: chạm cả SL lẫn TP trong cùng một bar -> SL xảy ra trước.
- Lệnh stop / SL bị gap: fill tại giá mở cửa nếu gap bất lợi.
- Phí taker hai chiều: BINGX_PERP_TAKER (0.0005).
- Không mô hình hoá funding & thanh lý (thay vào đó đo funding_spans và would_liquidate).
"""

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from trading.data_quality import is_dirty_bar
from trading.indicators import (
    AdxCalculator,
    AtrCalculator,
    BollingerCalculator,
    DonchianCalculator,
    EmaCalculator,
    percent_b,
)
from trading.models import Bar


@dataclass
class PerpTrade:
    symbol: str
    side: Literal["LONG", "SHORT"]
    signal_ts: datetime      # close của bar t (UTC)
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    qty: float
    r_value: float           # abs(entry - stop), mỗi đơn vị
    gross_pnl: float
    fees: float
    net_pnl: float           # gross - fees
    exit_reason: Literal["SL", "TP", "TIME"]
    bars_held: int
    clipped: bool            # đã bị cắt bởi trần đòn bẩy
    would_liquidate: bool    # biến động bất lợi vượt entry/max_leverage
    funding_spans: int       # số mốc 00/08/16 UTC mà lệnh sống qua


@dataclass
class PerpReport:
    module: str              # "donchian_breakout" | "bollinger_mr"
    symbol: str
    trades: list[PerpTrade]
    starting_capital: float
    ending_capital: float
    equity_curve: list[tuple[datetime, float]]
    signals_generated: int   # số tín hiệu phát ra
    orders_expired: int      # lệnh stop hết hạn không khớp
    orders_cancelled: int    # huỷ vì giá chạy quá xa


def run_perp_backtest(
    bars: list[Bar],
    module: Literal["donchian_breakout", "bollinger_mr"],
    *,
    capital: float = 500.0,
    fee_rate: float,            # BẮT BUỘC truyền tường minh
    slippage_bps: float,        # BẮT BUỘC truyền tường minh
    risk_fraction: float = 0.005,
    max_leverage: float = 10.0,
    use_ema_filter: bool = False,   # chỉ module A
) -> PerpReport:
    """Chạy backtest mô phỏng module perpetual 1H.

    Args:
        bars: Danh sách bar crypto 1H.
        module: 'donchian_breakout' hoặc 'bollinger_mr'.
        capital: Vốn khởi đầu (USDT). Mặc định 500.0.
        fee_rate: Tỷ lệ phí mỗi chiều (bắt buộc, ví dụ BINGX_PERP_TAKER).
        slippage_bps: Trượt giá mỗi chiều (bắt buộc, ví dụ 0.0 hoặc 2.0).
        risk_fraction: Tỷ lệ rủi ro vốn cho mỗi lệnh (0.005 = 0.5%).
        max_leverage: Trần đòn bẩy tối đa (10.0).
        use_ema_filter: Bật lọc xu hướng EMA50/EMA200 cho Module A.
    """
    clean_bars = [b for b in bars if not is_dirty_bar(b)]
    symbol = clean_bars[0].symbol if clean_bars else (bars[0].symbol if bars else "")

    # Cần đủ warm-up (tối thiểu 260 bar sạch cho cửa sổ 240 của module B)
    if len(clean_bars) < 260:
        return PerpReport(
            module=module,
            symbol=symbol,
            trades=[],
            starting_capital=capital,
            ending_capital=capital,
            equity_curve=[],
            signals_generated=0,
            orders_expired=0,
            orders_cancelled=0,
        )

    # Khởi tạo các chỉ báo theo module
    donchian = DonchianCalculator(period=20)
    atr_calc = AtrCalculator(period=14)
    bollinger = BollingerCalculator(period=20, num_std=2.0)
    adx_calc = AdxCalculator(period=14)
    ema50 = EmaCalculator(period=50)
    ema200 = EmaCalculator(period=200)

    # Bộ đệm lịch sử chỉ báo phục vụ các điều kiện quá khứ
    atr_history: list[float] = []
    bw_history: list[float] = []
    ema50_history: list[float] = []

    equity = capital
    trades: list[PerpTrade] = []
    equity_curve: list[tuple[datetime, float]] = []
    signals_generated = 0
    orders_expired = 0
    orders_cancelled = 0

    # Trạng thái vị thế đang mở
    pos_open = False
    pos_side: Literal["LONG", "SHORT"] = "LONG"
    pos_entry_price = 0.0
    pos_stop_price = 0.0
    pos_target_price = 0.0
    pos_qty = 0.0
    pos_r_value = 0.0
    pos_entry_ts: datetime = clean_bars[0].ts
    pos_signal_ts: datetime = clean_bars[0].ts
    pos_entry_bar_idx = -1
    pos_clipped = False
    pos_would_liquidate = False

    # Lệnh chờ khớp
    pending_order: dict | None = None

    for i, b in enumerate(clean_bars):
        just_closed_in_bar = False

        # --- 1. Cập nhật chỉ báo tại bar hiện tại ---
        donchian_val = donchian.update(b)
        atr_val = atr_calc.update(b)
        bb_val = bollinger.update(b)
        adx_val = adx_calc.update(b)
        ema50_val = ema50.update(b)
        ema200_val = ema200.update(b)

        # --- 2. Quản lý vị thế đang mở ---
        if pos_open:
            # Kiểm tra khả năng bị thanh lý do biến động bất lợi trong nến
            if pos_side == "LONG":
                if b.low < pos_entry_price * (1.0 - 1.0 / max_leverage):
                    pos_would_liquidate = True
            else:
                if b.high > pos_entry_price * (1.0 + 1.0 / max_leverage):
                    pos_would_liquidate = True

            # Chỉ xét thoát lệnh trên các bar SAU bar vào lệnh (i > pos_entry_bar_idx)
            if i > pos_entry_bar_idx:
                bars_held = i - pos_entry_bar_idx
                max_bars = 24 if module == "donchian_breakout" else 12

                sl_touch = False
                tp_touch = False
                raw_exit = None
                exit_reason: Literal["SL", "TP", "TIME"] | None = None

                if pos_side == "LONG":
                    sl_touch = b.low <= pos_stop_price
                    tp_touch = b.high >= pos_target_price

                    if sl_touch and tp_touch:
                        # Quy ước bi quan: SL trước TP
                        raw_exit = min(b.open, pos_stop_price)
                        exit_reason = "SL"
                    elif sl_touch:
                        raw_exit = min(b.open, pos_stop_price)
                        exit_reason = "SL"
                    elif tp_touch:
                        raw_exit = max(b.open, pos_target_price)
                        exit_reason = "TP"
                    elif bars_held >= max_bars:
                        raw_exit = b.close
                        exit_reason = "TIME"

                else:  # SHORT
                    sl_touch = b.high >= pos_stop_price
                    tp_touch = b.low <= pos_target_price

                    if sl_touch and tp_touch:
                        # Quy ước bi quan: SL trước TP
                        raw_exit = max(b.open, pos_stop_price)
                        exit_reason = "SL"
                    elif sl_touch:
                        raw_exit = max(b.open, pos_stop_price)
                        exit_reason = "SL"
                    elif tp_touch:
                        raw_exit = min(b.open, pos_target_price)
                        exit_reason = "TP"
                    elif bars_held >= max_bars:
                        raw_exit = b.close
                        exit_reason = "TIME"

                if exit_reason is not None and raw_exit is not None:
                    # Áp trượt giá bất lợi khi thoát
                    if pos_side == "LONG":
                        exit_price = raw_exit * (1.0 - slippage_bps / 10000.0)
                        gross_pnl = (exit_price - pos_entry_price) * pos_qty
                    else:
                        exit_price = raw_exit * (1.0 + slippage_bps / 10000.0)
                        gross_pnl = (pos_entry_price - exit_price) * pos_qty

                    fees = pos_qty * pos_entry_price * fee_rate + pos_qty * exit_price * fee_rate
                    net_pnl = gross_pnl - fees
                    equity += net_pnl

                    # Đếm số mốc funding 00/08/16 UTC mà lệnh sống qua
                    funding_spans = sum(
                        1
                        for h_bar in clean_bars[pos_entry_bar_idx + 1 : i + 1]
                        if h_bar.ts.hour in (0, 8, 16) and h_bar.ts.minute == 0
                    )

                    trades.append(
                        PerpTrade(
                            symbol=b.symbol,
                            side=pos_side,
                            signal_ts=pos_signal_ts,
                            entry_ts=pos_entry_ts,
                            exit_ts=b.ts,
                            entry_price=pos_entry_price,
                            exit_price=exit_price,
                            stop_price=pos_stop_price,
                            target_price=pos_target_price,
                            qty=pos_qty,
                            r_value=pos_r_value,
                            gross_pnl=gross_pnl,
                            fees=fees,
                            net_pnl=net_pnl,
                            exit_reason=exit_reason,
                            bars_held=bars_held,
                            clipped=pos_clipped,
                            would_liquidate=pos_would_liquidate,
                            funding_spans=funding_spans,
                        )
                    )

                    pos_open = False
                    just_closed_in_bar = True

        # --- 3. Xử lý lệnh chờ khớp (Pending Order) ---
        if not pos_open and not just_closed_in_bar and pending_order is not None:
            if module == "donchian_breakout":
                bars_since_signal = i - pending_order["created_bar_idx"]
                side = pending_order["side"]
                trigger = pending_order["trigger"]
                b_atr = pending_order["breakout_atr"]

                if side == "LONG":
                    # 1. Huỷ nếu mở cửa nhảy quá xa (không đuổi giá)
                    if b.open > trigger + 0.50 * b_atr:
                        orders_cancelled += 1
                        pending_order = None
                    # 2. Khớp lệnh stop
                    elif b.high >= trigger:
                        raw_entry = max(b.open, trigger)
                        entry_price = raw_entry * (1.0 + slippage_bps / 10000.0)
                        stop_price = min(
                            pending_order["breakout_low"] - 0.25 * b_atr,
                            entry_price - 1.5 * b_atr,
                        )
                        r_value = abs(entry_price - stop_price)
                        target_price = entry_price + 2.0 * r_value

                        cost_per_unit = 2.0 * entry_price * fee_rate
                        qty = (equity * risk_fraction) / (r_value + cost_per_unit)
                        clipped = False
                        if qty * entry_price > max_leverage * equity:
                            qty = (max_leverage * equity) / entry_price
                            clipped = True

                        pos_open = True
                        pos_side = "LONG"
                        pos_entry_price = entry_price
                        pos_stop_price = stop_price
                        pos_target_price = target_price
                        pos_qty = qty
                        pos_r_value = r_value
                        pos_entry_ts = b.ts
                        pos_signal_ts = pending_order["signal_ts"]
                        pos_entry_bar_idx = i
                        pos_clipped = clipped
                        pos_would_liquidate = (b.low < entry_price * (1.0 - 1.0 / max_leverage))
                        pending_order = None
                    # 3. Hết 2 bar không khớp -> hết hạn
                    elif bars_since_signal >= 2:
                        orders_expired += 1
                        pending_order = None

                else:  # SHORT
                    if b.open < trigger - 0.50 * b_atr:
                        orders_cancelled += 1
                        pending_order = None
                    elif b.low <= trigger:
                        raw_entry = min(b.open, trigger)
                        entry_price = raw_entry * (1.0 - slippage_bps / 10000.0)
                        stop_price = max(
                            pending_order["breakout_high"] + 0.25 * b_atr,
                            entry_price + 1.5 * b_atr,
                        )
                        r_value = abs(entry_price - stop_price)
                        target_price = entry_price - 2.0 * r_value

                        cost_per_unit = 2.0 * entry_price * fee_rate
                        qty = (equity * risk_fraction) / (r_value + cost_per_unit)
                        clipped = False
                        if qty * entry_price > max_leverage * equity:
                            qty = (max_leverage * equity) / entry_price
                            clipped = True

                        pos_open = True
                        pos_side = "SHORT"
                        pos_entry_price = entry_price
                        pos_stop_price = stop_price
                        pos_target_price = target_price
                        pos_qty = qty
                        pos_r_value = r_value
                        pos_entry_ts = b.ts
                        pos_signal_ts = pending_order["signal_ts"]
                        pos_entry_bar_idx = i
                        pos_clipped = clipped
                        pos_would_liquidate = (b.high > entry_price * (1.0 + 1.0 / max_leverage))
                        pending_order = None
                    elif bars_since_signal >= 2:
                        orders_expired += 1
                        pending_order = None

            elif module == "bollinger_mr":
                # Module B vào lệnh next-open tại bar t+1
                side = pending_order["side"]
                close_t = pending_order["close_t"]
                atr_t = pending_order["atr_t"]
                middle_t = pending_order["middle_t"]

                if side == "LONG":
                    # Bỏ lệnh nếu open t+1 lệch bất lợi quá 0.25 * ATR
                    if b.open > close_t + 0.25 * atr_t:
                        orders_cancelled += 1
                        pending_order = None
                    else:
                        raw_entry = b.open
                        entry_price = raw_entry * (1.0 + slippage_bps / 10000.0)
                        stop_price = pending_order["low_t"] - 0.25 * atr_t
                        r_value = abs(entry_price - stop_price)

                        # Ba phép loại bỏ (§2.4)
                        drop_order = False
                        if r_value < 0.60 * atr_t or r_value > 2.00 * atr_t:
                            drop_order = True
                        if abs(middle_t - entry_price) < 0.80 * r_value:
                            drop_order = True

                        if drop_order:
                            pending_order = None
                        else:
                            target_price = min(middle_t, entry_price + 1.25 * r_value)
                            cost_per_unit = 2.0 * entry_price * fee_rate
                            qty = (equity * risk_fraction) / (r_value + cost_per_unit)
                            clipped = False
                            if qty * entry_price > max_leverage * equity:
                                qty = (max_leverage * equity) / entry_price
                                clipped = True

                            pos_open = True
                            pos_side = "LONG"
                            pos_entry_price = entry_price
                            pos_stop_price = stop_price
                            pos_target_price = target_price
                            pos_qty = qty
                            pos_r_value = r_value
                            pos_entry_ts = b.ts
                            pos_signal_ts = pending_order["signal_ts"]
                            pos_entry_bar_idx = i
                            pos_clipped = clipped
                            pos_would_liquidate = (b.low < entry_price * (1.0 - 1.0 / max_leverage))
                            pending_order = None

                else:  # SHORT
                    if b.open < close_t - 0.25 * atr_t:
                        orders_cancelled += 1
                        pending_order = None
                    else:
                        raw_entry = b.open
                        entry_price = raw_entry * (1.0 - slippage_bps / 10000.0)
                        stop_price = pending_order["high_t"] + 0.25 * atr_t
                        r_value = abs(entry_price - stop_price)

                        drop_order = False
                        if r_value < 0.60 * atr_t or r_value > 2.00 * atr_t:
                            drop_order = True
                        if abs(middle_t - entry_price) < 0.80 * r_value:
                            drop_order = True

                        if drop_order:
                            pending_order = None
                        else:
                            target_price = max(middle_t, entry_price - 1.25 * r_value)
                            cost_per_unit = 2.0 * entry_price * fee_rate
                            qty = (equity * risk_fraction) / (r_value + cost_per_unit)
                            clipped = False
                            if qty * entry_price > max_leverage * equity:
                                qty = (max_leverage * equity) / entry_price
                                clipped = True

                            pos_open = True
                            pos_side = "SHORT"
                            pos_entry_price = entry_price
                            pos_stop_price = stop_price
                            pos_target_price = target_price
                            pos_qty = qty
                            pos_r_value = r_value
                            pos_entry_ts = b.ts
                            pos_signal_ts = pending_order["signal_ts"]
                            pos_entry_bar_idx = i
                            pos_clipped = clipped
                            pos_would_liquidate = (b.high > entry_price * (1.0 + 1.0 / max_leverage))
                            pending_order = None

        # --- 4. Phát hiện tín hiệu tại CLOSE bar t ---
        # Chỉ xét khi không có vị thế, không có lệnh chờ, và không vừa đóng vị thế trong bar này
        if not pos_open and pending_order is None and not just_closed_in_bar:
            if module == "donchian_breakout":
                # Điều kiện Donchian breakout (Price-only)
                # GHI CHÚ: Điều kiện Order Flow (delta, taker-buy ratio) bị BỎ vì repo không có dữ liệu.
                if donchian_val is not None and atr_val is not None and len(atr_history) >= 50:
                    upper_20, lower_20 = donchian_val
                    atr_14 = atr_val
                    prev_atr = atr_history[-1]
                    median_atr_50 = statistics.median(atr_history[-50:])

                    vol_expansion = (atr_14 / median_atr_50 >= 1.20) and (atr_14 > prev_atr)
                    bar_range = b.high - b.low
                    range_ok = bar_range >= 1.0 * atr_14

                    # Bộ lọc loại bỏ (§4.4)
                    shock_filter = (atr_14 / median_atr_50 < 2.50) and (bar_range <= 2.0 * atr_14)

                    if vol_expansion and range_ok and shock_filter and bar_range > 0:
                        clv = (b.close - b.low) / bar_range

                        # Lọc xu hướng EMA (tuỳ chọn)
                        ema_long_ok = True
                        ema_short_ok = True
                        if use_ema_filter:
                            if ema50_val is None or ema200_val is None:
                                ema_long_ok = False
                                ema_short_ok = False
                            else:
                                ema_long_ok = ema50_val > ema200_val
                                ema_short_ok = ema50_val < ema200_val

                        # Tín hiệu Long
                        if b.close > upper_20 and clv >= 0.65 and ema_long_ok:
                            signals_generated += 1
                            pending_order = {
                                "side": "LONG",
                                "trigger": upper_20 + 0.05 * atr_14,
                                "breakout_low": b.low,
                                "breakout_atr": atr_14,
                                "signal_ts": b.ts,
                                "created_bar_idx": i,
                            }
                        # Tín hiệu Short
                        elif b.close < lower_20 and clv <= 0.35 and ema_short_ok:
                            signals_generated += 1
                            pending_order = {
                                "side": "SHORT",
                                "trigger": lower_20 - 0.05 * atr_14,
                                "breakout_high": b.high,
                                "breakout_atr": atr_14,
                                "signal_ts": b.ts,
                                "created_bar_idx": i,
                            }

            elif (
                module == "bollinger_mr"
                and bb_val is not None
                and adx_val is not None
                and atr_val is not None
                and ema50_val is not None
                and ema200_val is not None
                and len(ema50_history) >= 3
                and len(bw_history) >= 240
            ):
                middle_t, upper_t, lower_t = bb_val
                atr_14 = atr_val
                bw_t = (upper_t - lower_t) / middle_t if middle_t > 0 else 0.0

                # 4 điều kiện chế độ thị trường (market regime)
                cond1 = adx_val < 20.0
                cond2 = abs(ema50_val - ema50_history[-3]) < 0.50 * atr_14
                cond3 = abs(ema50_val - ema200_val) <= 0.75 * atr_14

                bw_window = bw_history[-240:]
                cuts = statistics.quantiles(bw_window, n=5)
                p20 = cuts[0]
                p80 = cuts[3]
                cond4 = p20 <= bw_t <= p80

                regime_ok = cond1 and cond2 and cond3 and cond4

                if regime_ok:
                    pct_b = percent_b(b.close, upper_t, lower_t)
                    if pct_b is not None:
                        # Long: low_t <= lower_t < close_t, nến xanh, %B <= 0.25
                        if (
                            b.low <= lower_t
                            and b.close > lower_t
                            and b.close > b.open
                            and pct_b <= 0.25
                        ):
                            signals_generated += 1
                            pending_order = {
                                "side": "LONG",
                                "close_t": b.close,
                                "atr_t": atr_14,
                                "low_t": b.low,
                                "middle_t": middle_t,
                                "signal_ts": b.ts,
                                "created_bar_idx": i,
                            }
                        # Short: close_t < upper_t <= high_t, nến đỏ, %B >= 0.75
                        elif (
                            b.high >= upper_t
                            and b.close < upper_t
                            and b.close < b.open
                            and pct_b >= 0.75
                        ):
                            signals_generated += 1
                            pending_order = {
                                "side": "SHORT",
                                "close_t": b.close,
                                "atr_t": atr_14,
                                "high_t": b.high,
                                "middle_t": middle_t,
                                "signal_ts": b.ts,
                                "created_bar_idx": i,
                            }

        # --- 5. Lưu lịch sử chỉ báo và ghi nhận equity curve ---
        if atr_val is not None:
            atr_history.append(atr_val)
        if bb_val is not None:
            mid, up, low = bb_val
            bw_history.append((up - low) / mid if mid > 0 else 0.0)
        if ema50_val is not None:
            ema50_history.append(ema50_val)

        equity_curve.append((b.ts, equity))

    return PerpReport(
        module=module,
        symbol=symbol,
        trades=trades,
        starting_capital=capital,
        ending_capital=equity,
        equity_curve=equity_curve,
        signals_generated=signals_generated,
        orders_expired=orders_expired,
        orders_cancelled=orders_cancelled,
    )
