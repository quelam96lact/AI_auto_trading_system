"""Test module D (VWAP + Volume Profile + Order Flow) — BTCUSDT perp 1H.

Phần 1: hàm thuần (vwap_series, build_volume_profile, value_area).
Phần 2: engine run_value_pullback_backtest.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar
from trading.perp_value_pullback import (
    DayProfile,
    build_volume_profile,
    profile_for_days,
    run_value_pullback_backtest,
    value_area,
    vwap_series,
)

DAY = datetime(2020, 3, 2, 0, 0, tzinfo=UTC)  # thứ Hai, 00:00 UTC


def _bar(ts: datetime, o: float, h: float, l: float, c: float, vol: float = 1.0) -> Bar:
    return Bar(symbol="BTCUSDT", ts=ts, open=o, high=h, low=l, close=c, volume=vol)


def _h(ts: datetime, o: float, h: float, l: float, c: float, vol: float = 1.0) -> Bar:
    """Bar 1H với ts đã cho."""
    return _bar(ts, o, h, l, c, vol)


def _m5(day: datetime, minute: int, o: float, h: float, l: float, c: float, vol: float) -> Bar:
    """Bar 5m tại day + minute phút."""
    return _bar(day + timedelta(minutes=minute), o, h, l, c, vol)


# ---------------------------------------------------------------------------
# 1. vwap_series
# ---------------------------------------------------------------------------

def test_vwap_manual_three_bars():
    """3 nến cùng ngày: VWAP luỹ kế tới từng nến = Σ(HLC3·vol)/Σvol."""
    bars = [
        _h(DAY + timedelta(hours=0), 10.0, 11.0, 9.0, 10.0, 1.0),   # HLC3 = 10
        _h(DAY + timedelta(hours=1), 10.0, 12.0, 10.0, 11.0, 2.0),  # HLC3 = 11
        _h(DAY + timedelta(hours=2), 11.0, 13.0, 11.0, 12.0, 3.0),  # HLC3 = 12
    ]
    vw = vwap_series(bars)
    assert vw[bars[0].ts] == pytest.approx(10.0)
    assert vw[bars[1].ts] == pytest.approx(32.0 / 3.0)
    assert vw[bars[2].ts] == pytest.approx(68.0 / 6.0)


def test_vwap_resets_at_utc_midnight():
    """VWAP của ngày mới chỉ tính từ 00:00 ngày đó.

    Ngày trước phải ĐỦ 24 nến 1H mới hợp lệ, nên dựng đủ ngày rồi mới sang ngày mới.
    """
    bars = [_h(DAY + timedelta(hours=h), 10.0, 10.0, 10.0, 10.0, 1.0) for h in range(24)]
    bars.append(_h(DAY + timedelta(days=1), 20.0, 20.0, 20.0, 20.0, 1.0))
    vw = vwap_series(bars)
    assert vw[bars[23].ts] == pytest.approx(10.0)
    assert vw[bars[24].ts] == pytest.approx(20.0)  # reset, không kéo 10 vào


def test_vwap_invalid_after_missing_hour_in_day():
    """Thiếu 01:00 -> từ 02:00 trở đi trong ngày đó VWAP không hợp lệ."""
    bars = [
        _h(DAY + timedelta(hours=0), 10.0, 10.0, 10.0, 10.0, 1.0),
        _h(DAY + timedelta(hours=2), 12.0, 12.0, 12.0, 12.0, 1.0),
        _h(DAY + timedelta(days=1), 30.0, 30.0, 30.0, 30.0, 1.0),
    ]
    vw = vwap_series(bars)
    assert vw[bars[0].ts] == pytest.approx(10.0)
    assert vw[bars[1].ts] is None
    assert vw[bars[2].ts] == pytest.approx(30.0)  # ngày mới hợp lệ lại


# ---------------------------------------------------------------------------
# 2. value_area và build_volume_profile
# ---------------------------------------------------------------------------

def test_value_area_manual():
    """vols [1,2,4,2,1], POC = hàng 2, target 70% của 10 = 7, acc ban đầu 4.
    Bước 1: hai bên cùng khối lượng 2 -> luật hoà chọn hàng TRÊN (3) -> acc 6.
    Bước 2: trên = hàng 4 (1), dưới = hàng 1 (2) -> chọn hàng 1 -> acc 8 >= 7 -> dừng.
    VA = hàng 1..3 (hàng 4 KHÔNG được lấy).
    """
    lo_idx, hi_idx = value_area([1.0, 2.0, 4.0, 2.0, 1.0], poc_idx=2, va_pct=0.70)
    assert (lo_idx, hi_idx) == (1, 3)


def test_value_area_tie_chooses_upper_row():
    """Hoà khối lượng hai bên -> chọn hàng trên.

    vols [2,10,2,10,2]: tổng 26, target 18,2; POC = hàng 1 (hoà thì lấy hàng thấp) -> acc 10.
    Bước 1: trên = 2, dưới = 0 cùng khối lượng 2 -> luật hoà chọn hàng TRÊN (2) -> acc 12.
    Bước 2: trên = 3 (10) > dưới = 0 (2) -> lấy hàng 3 -> acc 22 >= 18,2 -> dừng.
    Nếu luật hoà chọn hàng DƯỚI thì kết quả phải là (0, 3) — test này phân biệt hai luật.
    """
    lo_idx, hi_idx = value_area([2.0, 10.0, 2.0, 10.0, 2.0], poc_idx=1, va_pct=0.70)
    assert (lo_idx, hi_idx) == (1, 3)


def test_value_area_runs_out_on_one_side():
    """Hết hàng một phía thì lấy phía còn lại."""
    lo_idx, hi_idx = value_area([9.0, 5.0, 1.0], poc_idx=0, va_pct=0.70)
    # POC là hàng thấp nhất: không còn hàng dưới -> chỉ mở lên trên
    assert (lo_idx, hi_idx) == (0, 1)


def test_build_volume_profile_manual_two_rows():
    """rows=2 trên [10, 20]: HLC3 = 12,13,11 vào hàng 0; HLC3 = 18 vào hàng 1.
    vols = [4, 5]; POC = hàng 1; VA cần >= 6.3 -> lấy thêm hàng 0 -> VAL = 10, VAH = 20.
    """
    m5 = [
        _m5(DAY, 0, 10.0, 14.0, 10.0, 12.0, 1.0),
        _m5(DAY, 5, 11.0, 15.0, 11.0, 13.0, 2.0),
        _m5(DAY, 10, 10.0, 12.0, 10.0, 11.0, 1.0),
        _m5(DAY, 15, 16.0, 20.0, 16.0, 18.0, 5.0),
    ]
    prof = build_volume_profile(m5, rows=2, va_pct=0.70, expected_bars=4)
    assert prof is not None
    assert prof.pl == pytest.approx(10.0)
    assert prof.ph == pytest.approx(20.0)
    assert prof.poc == pytest.approx(17.5)   # tâm hàng trên: 15 + 2.5
    assert prof.val == pytest.approx(10.0)
    assert prof.vah == pytest.approx(20.0)


def test_hlc3_equal_hi_goes_to_top_row():
    """HLC3 đúng bằng hi thì gán vào hàng trên cùng (không tràn khỏi mảng)."""
    m5 = [
        _m5(DAY, 0, 10.0, 20.0, 20.0, 20.0, 3.0),  # HLC3 = 20 = hi
        _m5(DAY, 5, 10.0, 10.0, 10.0, 10.0, 1.0),  # HLC3 = 10 = lo
    ]
    prof = build_volume_profile(m5, rows=2, va_pct=0.70, expected_bars=2)
    assert prof is not None
    assert prof.poc == pytest.approx(17.5)  # hàng trên (khối lượng 3 > 1)


def test_poc_tie_takes_lowest_row():
    """Hoà khối lượng -> POC là hàng THẤP nhất."""
    m5 = [
        _m5(DAY, 0, 10.0, 15.0, 10.0, 12.0, 5.0),
        _m5(DAY, 5, 15.0, 20.0, 15.0, 18.0, 5.0),
    ]
    prof = build_volume_profile(m5, rows=2, va_pct=0.70, expected_bars=2)
    assert prof is not None
    assert prof.poc == pytest.approx(12.5)  # hàng 0 (thấp hơn) dù hoà


def test_profile_invalid_when_bars_missing():
    """D-1 thiếu nến (287 thay vì 288) -> profile không hợp lệ."""
    m5 = [_m5(DAY, i * 5, 10.0, 11.0, 9.0, 10.0, 1.0) for i in range(287)]
    assert build_volume_profile(m5, expected_bars=288) is None


# ---------------------------------------------------------------------------
# 3. Kết cấu DayProfile
# ---------------------------------------------------------------------------

def test_day_profile_fields_frozen():
    """DayProfile là dataclass bất biến, đủ 5 trường như brief §3."""
    p = DayProfile(poc=1.0, vah=2.0, val=0.5, ph=3.0, pl=0.0)
    with pytest.raises(FrozenInstanceError):
        p.poc = 9.0  # type: ignore[misc]
    assert (p.poc, p.vah, p.val, p.ph, p.pl) == (1.0, 2.0, 0.5, 3.0, 0.0)


# ---------------------------------------------------------------------------
# 4. Engine: dựng chuỗi nến 1H có tín hiệu LONG
# ---------------------------------------------------------------------------

from trading.perp_backtest import RandomEntryConfig

D1 = datetime(2024, 1, 1, tzinfo=UTC)  # thứ Hai, 00:00 UTC
RAMP_DAYS = 10
SIG_TS = D1 + timedelta(hours=RAMP_DAYS * 24 + 12)  # ngày 10, 12:00 UTC
VALUE_C = 124.0
VALUE_LO = 99.0


def _idx(bars: list[Bar], ts: datetime) -> int:
    return next(i for i, b in enumerate(bars) if b.ts == ts)


def _over(bars: list[Bar], idx: int, *, o=None, h=None, l=None, c=None, v=None) -> None:
    b = bars[idx]
    bars[idx] = _bar(
        b.ts,
        b.open if o is None else o,
        b.high if h is None else h,
        b.low if l is None else l,
        b.close if c is None else c,
        b.volume if v is None else v,
    )


def _ramp(days: int, *, rising: bool = True) -> list[Bar]:
    out = []
    for i in range(days * 24):
        c = 100.0 + 0.1 * i if rising else 124.0 - 0.1 * i
        o = c - 0.06 if rising else c + 0.06
        out.append(_bar(D1 + timedelta(hours=i), o, c + 0.04, c - 0.04, c, 1.0))
    return out


def _value_day(day_index: int, *, rising: bool = True) -> list[Bar]:
    """Ngày 'value': doji (open = close) nên KHÔNG nến nào tự phát tín hiệu.

    Biên 0,1 trên / 0,4 dưới -> ATR14 ~ 0,45; dốc 0,01/nến để EMA20 tăng/giảm qua 3 nến.
    """
    base = VALUE_C if rising else VALUE_LO
    out = []
    for h in range(24):
        c = base + (0.01 * h if rising else -0.01 * h)
        o, hi, lo = (c, c + 0.1, c - 0.4) if rising else (c, c + 0.4, c - 0.1)
        out.append(_bar(D1 + timedelta(hours=day_index * 24 + h), o, hi, lo, c, 1.0))
    return out


def _scenario(*, rising: bool = True, tail_days: int = 2) -> list[Bar]:
    bars = _ramp(RAMP_DAYS, rising=rising) + _value_day(RAMP_DAYS, rising=rising)
    for d in range(RAMP_DAYS + 1, RAMP_DAYS + 1 + tail_days):
        bars += _value_day(d, rising=rising)
    return bars


def _shape_signal(bars: list[Bar], idx: int, *, rising: bool = True) -> None:
    """Nến tín hiệu: thân 0,12 theo hướng lệnh, bấc xa 0,3 về phía giá trị.

    LONG: `close = high = c + 0,12`, `low = c - 0,3` (chạm VAH = low, cách VWAP ~0,2).
    SHORT là ảnh soi gương qua `c`: `close = low = c - 0,12`, `high = c + 0,3`.
    """
    c = bars[idx].close
    if rising:
        _over(bars, idx, o=c + 0.05, h=c + 0.12, l=c - 0.3, c=c + 0.12)
    else:
        _over(bars, idx, o=c - 0.05, h=c + 0.3, l=c - 0.12, c=c - 0.12)


def _shape_fill(bars: list[Bar], idx: int, *, rising: bool = True) -> None:
    """Nến sau tín hiệu chạm lệnh chờ (buy-stop trên high_t / sell-stop dưới low_t)."""
    c = bars[idx].close
    if rising:
        _over(bars, idx, o=c + 0.1, h=c + 0.4, l=c + 0.05, c=c + 0.3)
    else:
        _over(bars, idx, o=c - 0.1, h=c - 0.05, l=c - 0.4, c=c - 0.3)


def _flat(bars: list[Bar], i_from: int, i_to: int, *, mid: float, span: float) -> None:
    for i in range(i_from, i_to + 1):
        _over(bars, i, o=mid, h=mid + span, l=mid - span, c=mid)


def _run(
    bars: list[Bar],
    *,
    rising: bool = True,
    sig_ts: datetime = SIG_TS,
    profiles: dict | None = None,
    vah: float | None = None,
    val: float | None = None,
    ph: float | None = None,
    pl: float | None = None,
    **kw,
):
    if profiles is None:
        b = bars[_idx(bars, sig_ts)]
        if rising:
            vah_v = b.low if vah is None else vah
            val_v = vah_v - 5.0 if val is None else val
        else:
            val_v = b.high if val is None else val
            vah_v = val_v + 5.0 if vah is None else vah
        profiles = {
            b.ts.date(): DayProfile(
                poc=b.close,
                vah=vah_v,
                val=val_v,
                ph=b.close + 100.0 if ph is None else ph,
                pl=b.close - 100.0 if pl is None else pl,
            )
        }
    kw.setdefault("fee_rate", BINGX_PERP_TAKER)
    kw.setdefault("slippage_bps", 0.0)
    return run_value_pullback_backtest(bars, profiles, **kw)


def _ready(*, rising: bool = True) -> tuple[list[Bar], int]:
    """Kịch bản đã định hình nến tín hiệu + nến khớp; trả (bars, chỉ số nến tín hiệu)."""
    bars = _scenario(rising=rising)
    si = _idx(bars, SIG_TS)
    _shape_signal(bars, si, rising=rising)
    _shape_fill(bars, si + 1, rising=rising)
    return bars, si


def _entry_metrics(bars: list[Bar], *, rising: bool = True) -> tuple[float, float]:
    """Lượt chạy dò để lấy (entry, R) thật — dùng định hình nến thoát."""
    r = _run(bars, rising=rising)
    assert r.trades, "kịch bản dò chưa vào được lệnh"
    return r.trades[0].entry_price, r.trades[0].r_value


# ---------------------------------------------------------------------------
# 5. Tín hiệu, vào lệnh, ba bộ lọc
# ---------------------------------------------------------------------------

def test_engine_long_signal_fires_and_fills():
    bars, si = _ready()
    r = _run(bars)
    assert r.signals_generated == 1
    assert r.entries == 1
    assert (r.dropped_flow, r.dropped_r, r.dropped_cost, r.dropped_barrier) == (0, 0, 0, 0)
    t = r.trades[0]
    assert t.side == "LONG"
    assert t.signal_ts == SIG_TS
    assert t.entry_ts == SIG_TS + timedelta(hours=1)  # khớp ở t+1, không ở nến tín hiệu
    assert t.entry_price > bars[si].high  # buy-stop trên high_t


def test_engine_editing_next_bar_does_not_change_signal():
    """Sửa nến t+1 không đổi việc tín hiệu tại t có phát hay không."""
    base, _ = _ready()
    r0 = _run(base)
    edited, si2 = _ready()
    _over(edited, si2 + 1, h=edited[si2].close + 20.0)
    r1 = _run(edited)
    assert (r0.signals_generated, r0.entries) == (1, 1)
    assert (r1.signals_generated, r1.entries) == (1, 1)
    assert r0.trades[0].signal_ts == r1.trades[0].signal_ts == SIG_TS


def test_engine_no_signal_at_utc_midnight_with_control():
    """Cùng một nến tín hiệu đặt ở 00:00 (không phát) so với 01:00 (phát)."""
    mid = _idx(_scenario(), SIG_TS) + 12
    for off, expected in ((0, 0), (1, 1)):
        bars = _scenario()
        si = mid + off
        _shape_signal(bars, si)
        b = bars[si]
        profiles = {
            (b.ts - timedelta(days=1)).date(): DayProfile(
                poc=VALUE_C, vah=VALUE_C - 1.0, val=VALUE_C - 4.0, ph=VALUE_C + 1.0, pl=VALUE_C - 2.0
            ),
            b.ts.date(): DayProfile(
                poc=b.close, vah=b.low, val=b.low - 5.0, ph=b.close + 100.0, pl=b.close - 100.0
            ),
        }
        r = _run(bars, sig_ts=b.ts, profiles=profiles)
        assert r.signals_generated == expected, f"nến {b.ts} lệch kỳ vọng"


def test_engine_no_signal_without_profile():
    bars, _ = _ready()
    r = _run(bars, profiles={})
    assert r.signals_generated == 0 and r.entries == 0 and r.trades == []


def test_engine_no_signal_when_vwap_invalid():
    """Thiếu một nến giữa ngày -> VWAP vô hiệu -> regime sai -> không tín hiệu."""
    bars, si = _ready()
    assert _run(bars).signals_generated == 1  # đối chứng
    del bars[si - 6]  # bỏ một nến trong chính ngày của nến tín hiệu
    r = _run(bars, sig_ts=SIG_TS)
    assert r.signals_generated == 0 and r.entries == 0


def test_engine_no_signal_when_level_not_touched():
    bars, si = _ready()
    r = _run(bars, vah=bars[si].low - 1.5)  # VAH xa low_t hơn 0,25*ATR
    assert r.signals_generated == 0 and r.entries == 0


def test_engine_no_signal_when_close_below_prev_high():
    bars, si = _ready()
    _over(bars, si - 1, h=bars[si].close + 0.6)
    r = _run(bars)
    assert r.signals_generated == 0 and r.entries == 0


def test_engine_no_signal_when_bar_not_green():
    bars, si = _ready()
    _over(bars, si, o=bars[si].close + 0.1, h=bars[si].close + 0.2)  # close < open
    r = _run(bars)
    assert r.signals_generated == 0 and r.entries == 0


def test_engine_no_signal_when_close_below_vah():
    bars, si = _ready()
    r = _run(bars, vah=bars[si].close + 0.5)  # close < VAH
    assert r.signals_generated == 0 and r.entries == 0


def test_regime_long_requires_all_five_conditions():
    from trading.perp_value_pullback import _regime_long, _Snap

    base = {
        "close": 110.0, "high": 111.0, "low": 109.0, "ema20": 105.0, "ema50": 104.0,
        "ema200": 100.0, "vwap": 108.0, "vah": 109.0, "val": 90.0, "ema20_prev3": 104.5,
    }
    assert _regime_long(_Snap(**base)) is True
    flips = {
        "close <= EMA200": {"close": 100.0, "high": 101.0, "low": 99.0},
        "EMA20 <= EMA50": {"ema20": 103.0},
        "EMA20 khong tang qua 3 nen": {"ema20_prev3": 105.5},
        "close <= VWAP": {"close": 107.0, "high": 108.0, "low": 106.0},
        "close <= VAH": {"vah": 111.0},
    }
    for name, over in flips.items():
        assert _regime_long(_Snap(**{**base, **over})) is False, name


def test_regime_short_requires_all_five_conditions():
    from trading.perp_value_pullback import _regime_short, _Snap

    base = {
        "close": 90.0, "high": 91.0, "low": 89.0, "ema20": 95.0, "ema50": 96.0,
        "ema200": 100.0, "vwap": 92.0, "vah": 110.0, "val": 91.0, "ema20_prev3": 95.5,
    }
    assert _regime_short(_Snap(**base)) is True
    flips = {
        "close >= EMA200": {"close": 100.0, "high": 101.0, "low": 99.0},
        "EMA20 >= EMA50": {"ema20": 97.0},
        "EMA20 khong giam qua 3 nen": {"ema20_prev3": 94.5},
        "close >= VWAP": {"close": 93.0, "high": 94.0, "low": 92.0},
        "close >= VAL": {"val": 90.0},
    }
    for name, over in flips.items():
        assert _regime_short(_Snap(**{**base, **over})) is False, name


def test_engine_pending_order_expires_after_two_bars():
    bars, si = _ready()
    _flat(bars, si + 1, si + 2, mid=VALUE_C - 0.05, span=0.02)  # dưới trigger -> không khớp
    r = _run(bars[: si + 9])  # cắt nhưng vẫn phải >= 260 nến (engine trả rỗng dưới ngưỡng)
    assert r.orders_expired == 1
    assert r.entries == 0 and r.trades == []


def test_engine_entry_filter_false_blocks_signal():
    bars, _ = _ready()
    r = _run(bars, entry_filter=lambda b, side: False)
    assert r.dropped_flow == 1
    assert r.signals_generated == 0 and r.entries == 0


def test_engine_random_entry_does_not_call_entry_filter():
    bars, _ = _ready()
    calls: list[str] = []

    def spy(b, side):
        calls.append(side)
        return False

    r = _run(
        bars,
        entry_filter=spy,
        random_entry=RandomEntryConfig(seed=7, signal_prob=0.5, long_prob=0.5),
    )
    assert calls == []
    assert r.dropped_flow == 0
    assert r.signals_generated > 0


def test_engine_drop_r_filter_when_stop_too_far():
    """R > 1,50*ATR: nến tín hiệu có biên rất rộng -> stop xa entry."""
    bars, si = _ready()
    c = bars[si].close
    _over(bars, si, h=c + 3.0, c=c + 3.0)  # vẫn chạm VAH = low_t, vẫn xanh, vẫn > VAH
    _over(bars, si + 1, h=c + 5.0, c=c + 4.5)  # nến sau vẫn khớp được buy-stop cao
    r = _run(bars)
    assert r.dropped_r == 1 and r.entries == 0 and r.trades == []


def test_engine_drop_cost_filter_and_ablation():
    bars, _ = _ready()
    r = _run(bars, slippage_bps=8.0)
    assert r.dropped_cost == 1 and r.entries == 0 and r.trades == []
    r2 = _run(bars, slippage_bps=8.0, use_cost_filter=False)
    assert r2.dropped_cost == 0 and r2.entries == 1


def test_engine_drop_barrier_filter_and_ablation():
    probe, _ = _ready()
    entry, r_unit = _entry_metrics(probe)
    bars, _ = _ready()
    r = _run(bars, ph=entry + 0.3 * r_unit)  # PH trên entry nhưng gần hơn R
    assert r.dropped_barrier == 1 and r.entries == 0 and r.trades == []
    r2 = _run(bars, ph=entry + 0.3 * r_unit, use_barrier_filter=False)
    assert r2.dropped_barrier == 0 and r2.entries == 1


# ---------------------------------------------------------------------------
# 6. Luật thoát (a)-(g), LONG
# ---------------------------------------------------------------------------

def test_engine_exit_a_stop_loss():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    stop = entry - r_unit
    _over(bars, si + 2, o=entry + 0.2, h=entry + 0.9 * r_unit, l=stop - 1.0, c=stop - 0.5)
    res = _run(bars)
    assert [t.exit_reason for t in res.trades] == ["SL", "SL"]
    assert res.trades[0].exit_price == pytest.approx(stop)
    assert res.trades[0].exit_price == pytest.approx(res.trades[0].stop_price)


def test_engine_exit_b_tp1_then_be_next_bar():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    be = entry * (1.0 + 2.0 * BINGX_PERP_TAKER)
    _over(bars, si + 2, o=entry + 0.2, h=entry + 1.5 * r_unit, l=entry + 0.1, c=entry + 1.4 * r_unit)
    _over(bars, si + 3, o=be + 0.05, h=entry + 1.6 * r_unit, l=be - 0.05, c=be)
    res = _run(bars)
    assert [t.exit_reason for t in res.trades] == ["TP1", "BE"]
    assert res.trades[0].exit_price == pytest.approx(entry + r_unit)
    assert res.trades[1].exit_price == pytest.approx(be)
    assert res.trades[1].exit_ts == bars[si + 3].ts  # BE chỉ áp dụng từ nến SAU TP1


def test_engine_exit_c_tp1_then_tp2():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    _over(bars, si + 2, o=entry + 0.2, h=entry + 1.5 * r_unit, l=entry + 0.1, c=entry + 1.4 * r_unit)
    _over(bars, si + 3, o=entry + 1.5 * r_unit, h=entry + 2.5 * r_unit, l=entry + 1.0 * r_unit, c=entry + 2.2 * r_unit)
    res = _run(bars)
    assert [t.exit_reason for t in res.trades] == ["TP1", "TP2"]
    assert res.trades[1].exit_price == pytest.approx(entry + 2.0 * r_unit)


def test_engine_exit_d_tp1_then_close_below_ema20():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    _over(bars, si + 2, o=entry + 0.2, h=entry + 1.5 * r_unit, l=entry + 0.1, c=entry + 1.4 * r_unit)
    # đẩy giá lên sát 2R nhưng không chạm, cho EMA20 bám theo
    for j in range(si + 3, si + 10):
        _over(bars, j, o=entry + 1.5 * r_unit, h=entry + 1.9 * r_unit, l=entry + 1.3 * r_unit,
              c=entry + 1.8 * r_unit)
    exit_close = entry + 0.25
    _over(bars, si + 10, o=entry + 1.8 * r_unit, h=entry + 1.9 * r_unit, l=entry + 0.2, c=exit_close)
    res = _run(bars)
    assert [t.exit_reason for t in res.trades] == ["TP1", "EMA20"]
    assert res.trades[1].exit_price == pytest.approx(exit_close)
    assert res.trades[1].exit_ts == bars[si + 10].ts


def test_engine_exit_e_time_stop_12_bars():
    bars, si = _ready()
    entry, _r_unit = _entry_metrics(bars)
    mid = entry - 0.1
    _flat(bars, si + 2, si + 20, mid=mid, span=0.05)  # không chạm TP1, không chạm stop
    res = _run(bars)
    assert [t.exit_reason for t in res.trades] == ["TIME", "TIME"]
    assert res.trades[0].bars_held == 12
    assert res.trades[0].exit_ts == bars[si + 13].ts  # k = si+1 -> j = k+12
    assert res.trades[0].exit_price == pytest.approx(mid)


def test_engine_exit_f_stop_and_tp1_same_bar_takes_stop():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    stop = entry - r_unit
    _over(bars, si + 2, o=entry + 0.2, h=entry + 1.5 * r_unit, l=stop - 1.0, c=entry + 0.1)
    res = _run(bars)
    first = [t for t in res.trades if t.exit_ts == bars[si + 2].ts]
    assert [t.exit_reason for t in first] == ["SL", "SL"]
    assert res.trades[0].exit_price == pytest.approx(stop)


def test_engine_exit_g_tp1_and_2r_same_bar_takes_only_tp1():
    bars, si = _ready()
    entry, r_unit = _entry_metrics(bars)
    _over(bars, si + 2, o=entry + 0.5 * r_unit, h=entry + 2.5 * r_unit, l=entry + 0.4 * r_unit,
          c=entry + 2.4 * r_unit)
    res = _run(bars)
    same_bar = [t for t in res.trades if t.exit_ts == bars[si + 2].ts]
    assert len(same_bar) == 1
    assert same_bar[0].exit_reason == "TP1"
    assert same_bar[0].exit_price == pytest.approx(entry + r_unit)


# ---------------------------------------------------------------------------
# 7. SHORT đối xứng cho (a) và (c)
# ---------------------------------------------------------------------------

def test_engine_short_stop_loss():
    bars, si = _ready(rising=False)
    entry, r_unit = _entry_metrics(bars, rising=False)
    stop = entry + r_unit
    _over(bars, si + 2, o=entry - 0.2, h=stop + 1.0, l=entry - 0.9 * r_unit, c=stop + 0.5)
    res = _run(bars, rising=False)
    assert [t.side for t in res.trades] == ["SHORT", "SHORT"]
    assert [t.exit_reason for t in res.trades] == ["SL", "SL"]
    assert res.trades[0].exit_price == pytest.approx(stop)


def test_engine_short_tp1_then_tp2():
    bars, si = _ready(rising=False)
    entry, r_unit = _entry_metrics(bars, rising=False)
    _over(bars, si + 2, o=entry - 0.2, h=entry - 0.1, l=entry - 1.5 * r_unit, c=entry - 1.4 * r_unit)
    _over(bars, si + 3, o=entry - 1.5 * r_unit, h=entry - 1.0 * r_unit, l=entry - 2.5 * r_unit,
          c=entry - 2.2 * r_unit)
    res = _run(bars, rising=False)
    assert [t.exit_reason for t in res.trades] == ["TP1", "TP2"]
    assert res.trades[1].exit_price == pytest.approx(entry - 2.0 * r_unit)


# ---------------------------------------------------------------------------
# 8. Ghép profile theo ngày: D-1 -> D
# ---------------------------------------------------------------------------

def _m5_day(day: datetime, *, base: float, vol: float = 1.0) -> list[Bar]:
    """288 nến 5m của một ngày UTC, biên [base, base + 2]."""
    return [
        _m5(day, i * 5, base, base + 2.0, base, base + 1.0, vol)
        for i in range(288)
    ]


def test_profile_for_days_uses_previous_day_data():
    """Profile dùng cho ngày D dựng từ nến 5m của D-1 (khoá dict là chính ngày D)."""
    day_a = DAY
    day_b = DAY + timedelta(days=1)
    bars_a = _m5_day(day_a, base=10.0)
    bars_b = _m5_day(day_b, base=20.0)
    prof = profile_for_days({day_a.date(): bars_a, day_b.date(): bars_b})
    assert set(prof) == {day_b.date(), (day_b + timedelta(days=1)).date()}
    assert day_a.date() not in prof
    # ngày D = day_b nhận profile của day_a (hi = 12), KHÔNG phải của chính nó (hi = 22)
    assert prof[day_b.date()].ph == pytest.approx(12.0)
    assert prof[(day_b + timedelta(days=1)).date()].ph == pytest.approx(22.0)


def test_profile_for_day_d_unchanged_when_day_d_bar_edited_but_not_when_d_minus_1():
    """Sửa nến 5m của chính ngày D -> profile dùng cho D không đổi; sửa D-1 -> đổi."""
    day_a = DAY
    day_b = DAY + timedelta(days=1)
    bars_a = _m5_day(day_a, base=10.0)
    bars_b = _m5_day(day_b, base=20.0)
    base_prof = profile_for_days({day_a.date(): bars_a, day_b.date(): bars_b})

    edited_b = list(bars_b)
    edited_b[100] = _m5(day_b, 500, 20.0, 99.0, 20.0, 20.0, 5.0)  # nến của D
    prof_b = profile_for_days({day_a.date(): bars_a, day_b.date(): edited_b})
    assert prof_b[day_b.date()] == base_prof[day_b.date()]
    assert prof_b[(day_b + timedelta(days=1)).date()] != base_prof[(day_b + timedelta(days=1)).date()]

    edited_a = list(bars_a)
    edited_a[100] = _m5(day_a, 500, 10.0, 50.0, 10.0, 10.0, 5.0)  # nến của D-1
    prof_a = profile_for_days({day_a.date(): edited_a, day_b.date(): bars_b})
    assert prof_a[day_b.date()] != base_prof[day_b.date()]


def test_profile_for_days_skips_day_with_287_bars():
    """D-1 thiếu nến -> ngày D không có profile (engine coi là không hợp lệ)."""
    day_a = DAY
    day_b = DAY + timedelta(days=1)
    bars_a = _m5_day(day_a, base=10.0)[:287]
    prof = profile_for_days({day_a.date(): bars_a, day_b.date(): _m5_day(day_b, base=20.0)})
    assert day_b.date() not in prof





def test_ema20_lag3_is_three_bars_before_current():
    """history gom ca nen x o cuoi: [x-3, x-2, x-1, x] -> tra x-3 (audit dot 106)."""
    from trading.perp_value_pullback import _ema20_lag3

    assert _ema20_lag3([10.0, 11.0, 12.0, 13.0]) == 10.0
    assert _ema20_lag3([9.0, 10.0, 11.0, 12.0, 13.0]) == 10.0
    assert _ema20_lag3([11.0, 12.0, 13.0]) is None
