"""Module D — VWAP + Volume Profile + Order Flow pullback cho BTCUSDT perp 1H (brief dot 106).

Gom:
- ham THUAN: `vwap_series`, `value_area`, `build_volume_profile` (+ `DayProfile`);
- engine `run_value_pullback_backtest` (doi chieu §2.2-§2.4 cua brief).

Quy uoc: moi ham nhan `Bar` da sap theo `ts`; thoi gian la UTC.
"""

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from trading.data_quality import is_dirty_bar
from trading.indicators import AtrCalculator, EmaCalculator
from trading.models import Bar
from trading.perp_backtest import PerpTrade, RandomEntryConfig


@dataclass(frozen=True)
class DayProfile:
    """Profile cua mot ngay UTC: POC, VAH, VAL, Profile High/Low (brief §2.1)."""

    poc: float
    vah: float
    val: float
    ph: float
    pl: float


def _hlc3(bar: Bar) -> float:
    """Gia tri dai dien HLC3 = (high + low + close) / 3."""
    return (bar.high + bar.low + bar.close) / 3.0


def vwap_series(bars: list[Bar]) -> dict[datetime, float | None]:
    """VWAP luỹ kế trong ngày UTC, reset tại 00:00.

    `VWAP_t = Σ(HLC3·volume) / Σ volume` trên các nến 1H **cùng ngày UTC** từ 00:00 đến hết `t`.
    Nếu ngày đó thiếu bất kỳ nến 1H nào trong khoảng 00:00..`t` thì VWAP không hợp lệ (`None`).

    `bars` phải sắp theo `ts` tăng dần.
    """
    out: dict[datetime, float | None] = {}
    cur_day: date | None = None
    hours_seen: set[int] = set()
    cum_pv = 0.0
    cum_v = 0.0

    for bar in bars:
        day = bar.ts.date()
        if day != cur_day:
            cur_day = day
            hours_seen = set()
            cum_pv = 0.0
            cum_v = 0.0

        hour = bar.ts.hour
        hours_seen.add(hour)
        cum_pv += _hlc3(bar) * bar.volume
        cum_v += bar.volume

        complete = hours_seen == set(range(hour + 1))
        out[bar.ts] = (cum_pv / cum_v) if (complete and cum_v > 0) else None

    return out


def value_area(vols: list[float], poc_idx: int, va_pct: float) -> tuple[int, int]:
    """Mở rộng Value Area từ POC (brief §2.1), trả `(hàng_thấp, hàng_cao)`.

    Mỗi bước thêm MỘT hàng kề (trên hoặc dưới) — chọn hàng có khối lượng lớn hơn;
    hoà thì chọn hàng TRÊN; hết hàng một phía thì lấy phía còn lại.
    Dừng khi tổng đã lấy >= `va_pct` × tổng ngày.
    """
    total = sum(vols)
    if total <= 0:
        return poc_idx, poc_idx

    target = va_pct * total
    lo_idx = poc_idx
    hi_idx = poc_idx
    acc = vols[poc_idx]

    while acc < target:
        up = hi_idx + 1
        down = lo_idx - 1
        has_up = up < len(vols)
        has_down = down >= 0

        if not has_up and not has_down:
            break
        if has_up and has_down:
            if vols[up] > vols[down]:
                hi_idx = up
                acc += vols[up]
            elif vols[down] > vols[up]:
                lo_idx = down
                acc += vols[down]
            else:
                hi_idx = up  # hoà -> hàng TRÊN
                acc += vols[up]
        elif has_up:
            hi_idx = up
            acc += vols[up]
        else:
            lo_idx = down
            acc += vols[down]

    return lo_idx, hi_idx


def build_volume_profile(
    bars_5m: list[Bar],
    *,
    rows: int = 48,
    va_pct: float = 0.70,
    expected_bars: int = 288,
) -> DayProfile | None:
    """Dựng profile ngày D từ **toàn bộ nến 5m của ngày D-1** (brief §2.1).

    Không hợp lệ (`None`) khi: số nến khác `expected_bars` (mặc định 288), `rows < 1`,
    hoặc `hi <= lo` (không chia được hàng).

    Khối lượng mỗi nến 5m gán TRỌN vào hàng chứa `HLC3` của nó; `HLC3 = hi` vào hàng trên cùng.
    POC = hàng khối lượng lớn nhất, hoà thì hàng THẤP nhất.
    """
    if rows < 1 or len(bars_5m) != expected_bars:
        return None

    lo = min(b.low for b in bars_5m)
    hi = max(b.high for b in bars_5m)
    if hi <= lo:
        return None

    width = (hi - lo) / rows
    vols = [0.0] * rows
    for bar in bars_5m:
        idx = int((_hlc3(bar) - lo) / width)
        if idx >= rows:
            idx = rows - 1  # HLC3 = hi
        elif idx < 0:
            idx = 0
        vols[idx] += bar.volume

    poc_idx = vols.index(max(vols))  # index() tra hang THAP nhat khi hoa
    va_lo, va_hi = value_area(vols, poc_idx, va_pct)

    return DayProfile(
        poc=lo + (poc_idx + 0.5) * width,
        vah=lo + (va_hi + 1) * width,
        val=lo + va_lo * width,
        ph=hi,
        pl=lo,
    )


def profile_for_days(
    bars_5m_by_day: Mapping[date, list[Bar]],
    *,
    rows: int = 48,
    va_pct: float = 0.70,
    expected_bars: int = 288,
) -> dict[date, DayProfile]:
    """Tra ve `{ngay_D: profile_dung_cho_ngay_D}`, tức profile dựng từ nến 5m của D-1.

    Khoá là ngày D mà profile được DÙNG (không phải ngày D-1 nguồn dữ liệu).
    Ngày D-1 thiếu dữ liệu thì D không có mặt trong dict (engine coi là không hợp lệ).
    """
    out: dict[date, DayProfile] = {}
    for src_day, bars in bars_5m_by_day.items():
        prof = build_volume_profile(bars, rows=rows, va_pct=va_pct, expected_bars=expected_bars)
        if prof is None:
            continue
        out[src_day + timedelta(days=1)] = prof
    return out


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Snap:
    """Anh chup chi bao tai mot nen, du de xet regime cua nen do."""

    close: float
    high: float
    low: float
    ema20: float | None
    ema50: float | None
    ema200: float | None
    vwap: float | None
    vah: float | None
    val: float | None
    ema20_prev3: float | None


@dataclass
class ValuePullbackReport:
    """Ket qua mot lan chay module D (cung dang PerpReport + bo dem bo lenh)."""

    symbol: str
    trades: list[PerpTrade]
    starting_capital: float
    ending_capital: float
    equity_curve: list[tuple[datetime, float]]
    signals_generated: int
    entries: int
    orders_expired: int
    dropped_flow: int
    dropped_r: int
    dropped_cost: int
    dropped_barrier: int


def _ema20_lag3(ema20_history: list[float]) -> float | None:
    """EMA20_{x-3} khi `ema20_history` DA gom EMA20 cua chinh nen x (phan tu cuoi).

    [-1] = x, [-2] = x-1, [-3] = x-2, [-4] = x-3. Audit dot 106: ban dau dung [-3] (lech mot nen).
    """
    return ema20_history[-4] if len(ema20_history) >= 4 else None


def _regime_long(s: _Snap) -> bool:
    """Cả 5 điều kiện regime LONG của §2.2 tại nến `x`."""
    return (
        s.ema20 is not None
        and s.ema50 is not None
        and s.ema200 is not None
        and s.vwap is not None
        and s.vah is not None
        and s.ema20_prev3 is not None
        and s.close > s.ema200
        and s.ema20 > s.ema50
        and s.ema20 > s.ema20_prev3
        and s.close > s.vwap
        and s.close > s.vah
    )


def _regime_short(s: _Snap) -> bool:
    """Đối xứng của `_regime_long` (§2.2)."""
    return (
        s.ema20 is not None
        and s.ema50 is not None
        and s.ema200 is not None
        and s.vwap is not None
        and s.val is not None
        and s.ema20_prev3 is not None
        and s.close < s.ema200
        and s.ema20 < s.ema50
        and s.ema20 < s.ema20_prev3
        and s.close < s.vwap
        and s.close < s.val
    )


def run_value_pullback_backtest(
    bars_1h: list[Bar],
    profiles: Mapping[date, DayProfile],
    *,
    fee_rate: float,
    slippage_bps: float,
    capital: float = 500.0,
    risk_fraction: float = 0.005,
    max_leverage: float = 10.0,
    entry_filter: Callable[[Bar, str], bool] | None = None,
    random_entry: RandomEntryConfig | None = None,
    use_cost_filter: bool = True,
    use_barrier_filter: bool = True,
) -> ValuePullbackReport:
    """Chay module D: VWAP + Volume Profile + Order Flow pullback (brief dot 106 §2.2-§2.4).

    Args:
        bars_1h: nen 1H da sap theo ts.
        profiles: `{ngay_UTC_D: DayProfile}` dung cho ngay D (profile dung chinh ngay D,
            tuc dung tu nen 5m cua D-1).
        fee_rate, slippage_bps: chi phi moi chieu (bat buoc tuong minh).
        entry_filter: `f(bar_t, side) -> bool`, goi tai NEN TIN HIEU t cho tin hieu THAT
            (khong goi cho nhanh `random_entry`); tra False thi bo tin hieu.
        random_entry: doi chung ngau nhien (§2.5) — moi nen du dieu kien, xac suat `signal_prob`.
        use_cost_filter, use_barrier_filter: tat bo loc chi phi / vung can (ablation).
    """
    clean_bars = [b for b in bars_1h if not is_dirty_bar(b)]
    symbol = clean_bars[0].symbol if clean_bars else (bars_1h[0].symbol if bars_1h else "")

    empty = ValuePullbackReport(
        symbol=symbol,
        trades=[],
        starting_capital=capital,
        ending_capital=capital,
        equity_curve=[],
        signals_generated=0,
        entries=0,
        orders_expired=0,
        dropped_flow=0,
        dropped_r=0,
        dropped_cost=0,
        dropped_barrier=0,
    )
    if len(clean_bars) < 260:
        return empty

    ema20_calc = EmaCalculator(period=20)
    ema50_calc = EmaCalculator(period=50)
    ema200_calc = EmaCalculator(period=200)
    atr_calc = AtrCalculator(period=14)

    vwap_map = vwap_series(clean_bars)

    equity = capital
    trades: list[PerpTrade] = []
    equity_curve: list[tuple[datetime, float]] = []
    signals_generated = 0
    entries = 0
    orders_expired = 0
    dropped_flow = 0
    dropped_r = 0
    dropped_cost = 0
    dropped_barrier = 0

    rng = random.Random(random_entry.seed) if random_entry is not None else None

    ema20_history: list[float] = []
    snaps: list[_Snap] = []

    # Trạng thái vị thế (2 chân)
    pos_open = False
    pos_side: Literal["LONG", "SHORT"] = "LONG"
    pos_entry_price = 0.0
    pos_stop_price = 0.0
    pos_r_value = 0.0
    pos_qty_leg = 0.0
    pos_entry_ts: datetime = clean_bars[0].ts
    pos_signal_ts: datetime = clean_bars[0].ts
    pos_entry_bar_idx = -1
    pos_clipped = False
    pos_would_liquidate = False
    pos_legs_open = 0
    pos_tp1_done = False
    pos_be_from_idx = -1  # stop BE áp dụng TỪ nến này

    pending: dict | None = None

    for i, b in enumerate(clean_bars):
        ema20_val = ema20_calc.update(b)
        ema50_val = ema50_calc.update(b)
        ema200_val = ema200_calc.update(b)
        atr_val = atr_calc.update(b)
        vwap_t = vwap_map.get(b.ts)
        prof = profiles.get(b.ts.date())
        just_closed_in_bar = False

        def _close_leg(
            reason: str,
            exit_price: float,
            target_price: float,
            *,
            _i: int = i,
            _bar: Bar = b,
            _side: Literal["LONG", "SHORT"] = pos_side,
            _entry_price: float = pos_entry_price,
            _qty_leg: float = pos_qty_leg,
            _entry_bar_idx: int = pos_entry_bar_idx,
            _stop_price: float = pos_stop_price,
            _r_value: float = pos_r_value,
            _clipped: bool = pos_clipped,
            _entry_ts: datetime = pos_entry_ts,
            _signal_ts: datetime = pos_signal_ts,
        ) -> None:
            """Đóng một chân còn mở tại `exit_price` (đã gồm trượt giá bất lợi).

            Trạng thái vị thế buộc qua tham số mặc định (ruff B023): hàm lồng trong vòng
            lặp và chỉ được gọi trong cùng vòng nên giá trị đọc lúc định nghĩa là đúng.
            """
            nonlocal equity, pos_legs_open
            if _side == "LONG":
                gross = (exit_price - _entry_price) * _qty_leg
            else:
                gross = (_entry_price - exit_price) * _qty_leg
            fees = _qty_leg * _entry_price * fee_rate + _qty_leg * exit_price * fee_rate
            net = gross - fees
            equity += net
            funding_spans = sum(
                1
                for h_bar in clean_bars[_entry_bar_idx + 1 : _i + 1]
                if h_bar.ts.hour in (0, 8, 16) and h_bar.ts.minute == 0
            )
            trades.append(
                PerpTrade(
                    symbol=_bar.symbol,
                    side=_side,
                    signal_ts=_signal_ts,
                    entry_ts=_entry_ts,
                    exit_ts=_bar.ts,
                    entry_price=_entry_price,
                    exit_price=exit_price,
                    stop_price=_stop_price,
                    target_price=target_price,
                    qty=_qty_leg,
                    r_value=_r_value,
                    gross_pnl=gross,
                    fees=fees,
                    net_pnl=net,
                    exit_reason=reason,  # type: ignore[arg-type]
                    bars_held=_i - _entry_bar_idx,
                    clipped=_clipped,
                    # cờ này có thể được bật SAU khi hàm được định nghĩa trong cùng nến
                    # -> phải đọc giá trị sống, không buộc theo tham số.
                    would_liquidate=pos_would_liquidate,  # noqa: B023
                    funding_spans=funding_spans,
                )
            )
            pos_legs_open -= 1

        # --- 1. Quản lý vị thế đang mở ---
        if pos_open and i > pos_entry_bar_idx:
            slip = slippage_bps / 10000.0
            be_stop = (
                pos_entry_price * (1.0 + 2.0 * fee_rate + 2.0 * slip)
                if pos_side == "LONG"
                else pos_entry_price * (1.0 - 2.0 * fee_rate - 2.0 * slip)
            )
            be_active = pos_be_from_idx >= 0 and i >= pos_be_from_idx
            stop_now = be_stop if be_active else pos_stop_price
            tp1_level = (
                pos_entry_price + pos_r_value if pos_side == "LONG" else pos_entry_price - pos_r_value
            )
            tp2_level = (
                pos_entry_price + 2.0 * pos_r_value
                if pos_side == "LONG"
                else pos_entry_price - 2.0 * pos_r_value
            )
            bar_done = False

            if pos_side == "LONG":
                if b.low < pos_entry_price * (1.0 - 1.0 / max_leverage):
                    pos_would_liquidate = True

                # (1) Stop trước
                if b.low <= stop_now:
                    raw = min(b.open, stop_now)
                    exit_price = raw * (1.0 - slip)
                    reason = "BE" if be_active else "SL"
                    legs = pos_legs_open
                    for _ in range(legs):
                        _close_leg(reason, exit_price, tp2_level)
                    bar_done = True

                # (2) TP1
                if not bar_done and not pos_tp1_done and b.high >= tp1_level:
                    raw = max(b.open, tp1_level)
                    _close_leg("TP1", raw * (1.0 - slip), tp1_level)
                    pos_tp1_done = True
                    pos_be_from_idx = i + 1  # BE áp dụng TỪ nến sau
                    bar_done = True

                # (3) Sau khi đã chốt TP1 ở nến trước
                if not bar_done and pos_tp1_done and pos_legs_open > 0:
                    if b.high >= tp2_level:
                        raw = max(b.open, tp2_level)
                        _close_leg("TP2", raw * (1.0 - slip), tp2_level)
                    elif ema20_val is not None and b.close < ema20_val:
                        _close_leg("EMA20", b.close * (1.0 - slip), tp2_level)
                    bar_done = True

                # (4) Time stop khi chưa chốt TP1
                if not bar_done and not pos_tp1_done and (i - pos_entry_bar_idx) >= 12:
                    exit_price = b.close * (1.0 - slip)
                    legs = pos_legs_open
                    for _ in range(legs):
                        _close_leg("TIME", exit_price, tp2_level)
                    bar_done = True

            else:  # SHORT
                if b.high > pos_entry_price * (1.0 + 1.0 / max_leverage):
                    pos_would_liquidate = True

                if b.high >= stop_now:
                    raw = max(b.open, stop_now)
                    exit_price = raw * (1.0 + slip)
                    reason = "BE" if be_active else "SL"
                    legs = pos_legs_open
                    for _ in range(legs):
                        _close_leg(reason, exit_price, tp2_level)
                    bar_done = True

                if not bar_done and not pos_tp1_done and b.low <= tp1_level:
                    raw = min(b.open, tp1_level)
                    _close_leg("TP1", raw * (1.0 + slip), tp1_level)
                    pos_tp1_done = True
                    pos_be_from_idx = i + 1
                    bar_done = True

                if not bar_done and pos_tp1_done and pos_legs_open > 0:
                    if b.low <= tp2_level:
                        raw = min(b.open, tp2_level)
                        _close_leg("TP2", raw * (1.0 + slip), tp2_level)
                    elif ema20_val is not None and b.close > ema20_val:
                        _close_leg("EMA20", b.close * (1.0 + slip), tp2_level)
                    bar_done = True

                if not bar_done and not pos_tp1_done and (i - pos_entry_bar_idx) >= 12:
                    exit_price = b.close * (1.0 + slip)
                    legs = pos_legs_open
                    for _ in range(legs):
                        _close_leg("TIME", exit_price, tp2_level)
                    bar_done = True

            if pos_legs_open <= 0:
                pos_open = False
                just_closed_in_bar = True

        # --- 2. Lệnh chờ ---
        if not pos_open and not just_closed_in_bar and pending is not None:
            side = pending["side"]
            trigger = pending["trigger"]
            atr_sig = pending["atr_sig"]
            filled = False
            if side == "LONG":
                if b.high >= trigger:
                    filled = True
                    raw_entry = max(b.open, trigger)
                    entry_price = raw_entry * (1.0 + slippage_bps / 10000.0)
                    stop_price = pending["stop"]
                elif i - pending["created_bar_idx"] >= 2:
                    orders_expired += 1
                    pending = None
            else:
                if b.low <= trigger:
                    filled = True
                    raw_entry = min(b.open, trigger)
                    entry_price = raw_entry * (1.0 - slippage_bps / 10000.0)
                    stop_price = pending["stop"]
                elif i - pending["created_bar_idx"] >= 2:
                    orders_expired += 1
                    pending = None

            if filled:
                r_value = abs(entry_price - stop_price)
                drop = False
                if r_value < 0.20 * atr_sig or r_value > 1.50 * atr_sig:
                    dropped_r += 1
                    drop = True
                if (
                    not drop
                    and use_cost_filter
                    and entry_price * 2.0 * slippage_bps / 1e4 > 0.15 * r_value
                ):
                    dropped_cost += 1
                    drop = True
                if not drop and use_barrier_filter:
                    ph = pending["ph"]
                    pl = pending["pl"]
                    if side == "LONG" and ph > entry_price and (ph - entry_price) < r_value or side == "SHORT" and pl < entry_price and (entry_price - pl) < r_value:
                        dropped_barrier += 1
                        drop = True

                if drop:
                    pending = None
                else:
                    qty = (equity * risk_fraction) / (r_value + 2.0 * entry_price * fee_rate)
                    clipped = False
                    if qty * entry_price > max_leverage * equity:
                        qty = (max_leverage * equity) / entry_price
                        clipped = True
                    pos_open = True
                    pos_side = side
                    pos_entry_price = entry_price
                    pos_stop_price = stop_price
                    pos_r_value = r_value
                    pos_qty_leg = qty / 2.0
                    pos_entry_ts = b.ts
                    pos_signal_ts = pending["signal_ts"]
                    pos_entry_bar_idx = i
                    pos_clipped = clipped
                    pos_legs_open = 2
                    pos_tp1_done = False
                    pos_be_from_idx = -1
                    if side == "LONG":
                        pos_would_liquidate = b.low < entry_price * (1.0 - 1.0 / max_leverage)
                    else:
                        pos_would_liquidate = b.high > entry_price * (1.0 + 1.0 / max_leverage)
                    entries += 1
                    pending = None

        # --- 3. Tín hiệu tại close bar t ---
        can_signal = not pos_open and pending is None and not just_closed_in_bar
        if can_signal and b.ts.hour != 0:
            vah_t = prof.vah if prof is not None else None
            val_t = prof.val if prof is not None else None
            warm = atr_val is not None and vwap_t is not None and prof is not None

            if random_entry is not None and rng is not None:
                if warm and rng.random() < random_entry.signal_prob:
                    assert prof is not None  # warm đã bảo đảm
                    assert atr_val is not None
                    signals_generated += 1
                    is_long = rng.random() < random_entry.long_prob
                    atr_sig = atr_val
                    if is_long:
                        pending = {
                            "side": "LONG",
                            "trigger": b.high + 0.05 * atr_sig,
                            "stop": b.low - 0.25 * atr_sig,
                            "atr_sig": atr_sig,
                            "ph": prof.ph,
                            "pl": prof.pl,
                            "signal_ts": b.ts,
                            "created_bar_idx": i,
                        }
                    else:
                        pending = {
                            "side": "SHORT",
                            "trigger": b.low - 0.05 * atr_sig,
                            "stop": b.high + 0.25 * atr_sig,
                            "atr_sig": atr_sig,
                            "ph": prof.ph,
                            "pl": prof.pl,
                            "signal_ts": b.ts,
                            "created_bar_idx": i,
                        }

            elif warm and len(snaps) >= 3 and atr_val is not None:
                assert prof is not None  # warm đã bảo đảm
                atr_sig = atr_val
                prev_snaps = (snaps[-1], snaps[-2], snaps[-3])
                long_regime = any(_regime_long(s) for s in prev_snaps)
                short_regime = any(_regime_short(s) for s in prev_snaps)

                if long_regime and vah_t is not None:
                    touched = [
                        lvl for lvl in (vwap_t, vah_t)
                        if lvl is not None and abs(b.low - lvl) <= 0.25 * atr_sig
                    ]
                    if touched:
                        level = min(touched, key=lambda lvl: abs(lvl - b.close))
                        if (
                            b.close > level
                            and b.close > b.open
                            and b.close > snaps[-1].high
                            and b.close > vah_t
                        ):
                            if entry_filter is not None and not entry_filter(b, "LONG"):
                                dropped_flow += 1
                            else:
                                signals_generated += 1
                                pending = {
                                    "side": "LONG",
                                    "trigger": b.high + 0.05 * atr_sig,
                                    "stop": min(b.low, level - 0.25 * atr_sig),
                                    "atr_sig": atr_sig,
                                    "ph": prof.ph,
                                    "pl": prof.pl,
                                    "signal_ts": b.ts,
                                    "created_bar_idx": i,
                                }

                # SHORT xet DOC LAP voi LONG (audit dot 106: `elif` cu bo qua SHORT moi khi
                # co regime LONG trong 3 nen truoc, ke ca khi LONG khong phat tin hieu).
                if pending is None and short_regime and val_t is not None:
                    touched = [
                        lvl for lvl in (vwap_t, val_t)
                        if lvl is not None and abs(b.high - lvl) <= 0.25 * atr_sig
                    ]
                    if touched:
                        level = min(touched, key=lambda lvl: abs(lvl - b.close))
                        if (
                            b.close < level
                            and b.close < b.open
                            and b.close < snaps[-1].low
                            and b.close < val_t
                        ):
                            if entry_filter is not None and not entry_filter(b, "SHORT"):
                                dropped_flow += 1
                            else:
                                signals_generated += 1
                                pending = {
                                    "side": "SHORT",
                                    "trigger": b.low - 0.05 * atr_sig,
                                    "stop": max(b.high, level + 0.25 * atr_sig),
                                    "atr_sig": atr_sig,
                                    "ph": prof.ph,
                                    "pl": prof.pl,
                                    "signal_ts": b.ts,
                                    "created_bar_idx": i,
                                }

        # --- 4. Lịch sử + equity ---
        if ema20_val is not None:
            ema20_history.append(ema20_val)
        snaps.append(
            _Snap(
                close=b.close,
                high=b.high,
                low=b.low,
                ema20=ema20_val,
                ema50=ema50_val,
                ema200=ema200_val,
                vwap=vwap_t,
                vah=prof.vah if prof is not None else None,
                val=prof.val if prof is not None else None,
                ema20_prev3=_ema20_lag3(ema20_history),
            )
        )
        equity_curve.append((b.ts, equity))

    return ValuePullbackReport(
        symbol=symbol,
        trades=trades,
        starting_capital=capital,
        ending_capital=equity,
        equity_curve=equity_curve,
        signals_generated=signals_generated,
        entries=entries,
        orders_expired=orders_expired,
        dropped_flow=dropped_flow,
        dropped_r=dropped_r,
        dropped_cost=dropped_cost,
        dropped_barrier=dropped_barrier,
    )
