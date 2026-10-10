"""Test suite cho scripts/screen_vn30f_orderflow.py (Brief dot 182).

TDD tren du lieu tong hop dung tay va seed co dinh, khong cham data/orderbook/.
Gom 11 ca kiem chung:
1. Dung nen footprint va loc tin (buy/sell/delta/OHLC, fp, U/0/ATC bi loai, recv_ts vs trading_time).
2. CVD reset tai dau moi phien.
3. E1 phan ky CVD (so sanh nghiem ngat, cua so 11 nen, khong vat qua phien).
4. E2 phan ky delta trong nen (nguong 5 phien truoc, chieu d = sign(delta), close == open).
5. Imbalance va E3 bo doi hap thu -> khoi xuong (bay cung muc, san vol=5, lam tron k, 11:25 va 13:00).
6. Muc tieu y va loc chong lan (dau theo d, P(x), loai 11:20 o H=15, khoang cach < H).
7. Cong ngay (today < 2026-12-01 tra 2 va khong goi mock).
8. Niem phong Holdout (nem loi neu log chua co dot 182).
9. Nguong chi phi tai gia 1900.
10. Cong IS §1.4 (ca bien cho 99 events, 29 side, p == 0.05/6, mean_y == hurdle, rho == 0.3).
11. Bootstrap theo khoi phien (y=+1 -> p=0, doi xung, len(set) <= 3 voi 2 phien).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from scripts.record_vn30f_orderbook import MORNING_START
from scripts.screen_vn30f_orderflow import (
    ALPHA_PER_PAIR,
    BarSummary,
    OrderFlowEvent,
    block_bootstrap_p_value,
    build_footprint_bars,
    calculate_event_targets,
    compute_economic_hurdle,
    detect_e1_events,
    detect_e2_events,
    detect_e3_events,
    evaluate_pair_criteria,
    filter_non_overlapping_events,
    imbalance_levels,
    load_holdout_sessions,
    main,
    verify_holdout_log_unlocked,
)
from trading.calendar_vn import TZ


def test_1_dung_nen_footprint_va_loc_tin():
    """Ca 1: Dung nen footprint, kiem tra buy/sell/delta/OHLC, tin U/0/ATC, va xep theo trading_time."""
    session_d = date(2026, 10, 1)

    # Danh sach tin:
    # 1. 09:01:00 B 10 @ 1900.0 (Bar 0)
    # 2. 09:02:00 S 5  @ 1901.0 (Bar 0)
    # 3. 09:04:55 B 8  @ 1902.0, recv_ts = 09:05:15 (Bar 0 theo trading_time!)
    # 4. 09:03:00 U 0  @ 1900.5 (Tin chi bao -> loai)
    # 5. 09:03:30 B 0  @ 1900.5 (Qty 0 -> loai)
    # 6. 14:35:00 B 100 @ 1905.0 (ATC -> loai)
    # 7. 09:06:00 B 12 @ 1903.0 (Bar 1)
    msgs = [
        {
            "trading_time": "2026/10/01 09:01:00",
            "recv_ts": "2026-10-01T09:01:02+07:00",
            "side": "B",
            "quantity": 10,
            "price": 1900.0,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 09:02:00",
            "recv_ts": "2026-10-01T09:02:01+07:00",
            "side": "S",
            "quantity": 5,
            "price": 1901.0,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 09:04:55",
            "recv_ts": "2026-10-01T09:05:15+07:00",  # recv_ts roi sang nen sau!
            "side": "B",
            "quantity": 8,
            "price": 1902.0,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 09:03:00",
            "recv_ts": "2026-10-01T09:03:01+07:00",
            "side": "U",
            "quantity": 0,
            "price": 1900.5,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 09:03:30",
            "recv_ts": "2026-10-01T09:03:31+07:00",
            "side": "B",
            "quantity": 0,
            "price": 1900.5,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 14:35:00",
            "recv_ts": "2026-10-01T14:35:01+07:00",
            "side": "B",
            "quantity": 100,
            "price": 1905.0,
            "msg_type": "33",
        },
        {
            "trading_time": "2026/10/01 09:06:00",
            "recv_ts": "2026-10-01T09:06:02+07:00",
            "side": "B",
            "quantity": 12,
            "price": 1903.0,
            "msg_type": "33",
        },
    ]

    stats: dict = {}
    bars, stats = build_footprint_bars(msgs, session_d, stats=stats)
    assert len(bars) == 48

    # Kiem tra thong ke loc tin
    assert stats["dropped_u_or_zero"] == 2  # msg 4 va msg 5
    assert stats["outside_session"] == 1  # msg 6 (ATC)
    assert stats["trades_used"] == 4

    # Kiem tra Bar 0 (09:00 - 09:05)
    b0 = bars[0]
    assert b0.trade_count == 3
    assert b0.open == 1900.0
    assert b0.high == 1902.0
    assert b0.low == 1900.0
    assert b0.close == 1902.0  # msg 3 co trading_time cuoi cung
    assert b0.buy == 18.0  # 10 + 8
    assert b0.sell == 5.0
    assert b0.delta == 13.0
    assert b0.cvd == 13.0

    # Kiem tra footprint Bar 0
    fp0 = b0.fp or {}
    assert fp0[19000] == (10.0, 0.0)
    assert fp0[19010] == (0.0, 5.0)
    assert fp0[19020] == (8.0, 0.0)

    # Kiem tra Bar 1 (09:05 - 09:10)
    b1 = bars[1]
    assert b1.trade_count == 1
    assert b1.close == 1903.0
    assert b1.buy == 12.0
    assert b1.cvd == 25.0  # 13 + 12


def test_2_cvd_reset():
    """Ca 2: Hai phien lien nhau, CVD nen dau phien 2 phai bang dung delta cua chinh nen do."""
    d1 = date(2026, 10, 1)
    d2 = date(2026, 10, 2)

    msgs_d1 = [
        {
            "trading_time": "2026/10/01 09:01:00",
            "side": "B",
            "quantity": 50,
            "price": 1900.0,
            "msg_type": "33",
        }
    ]
    msgs_d2 = [
        {
            "trading_time": "2026/10/02 09:01:00",
            "side": "B",
            "quantity": 15,
            "price": 1910.0,
            "msg_type": "33",
        }
    ]

    bars1, _ = build_footprint_bars(msgs_d1, d1)
    bars2, _ = build_footprint_bars(msgs_d2, d2)

    assert bars1[0].cvd == 50.0
    # Phien 2 CVD reset ve 0 truoc khi cong delta phien 2
    assert bars2[0].delta == 15.0
    assert bars2[0].cvd == 15.0


def test_3_e1_phan_ky_cvd():
    """Ca 3: E1 kich hoat dung nen du kien, so sanh nghiem ngat, khong vat qua phien."""
    d1 = date(2026, 10, 1)
    d2 = date(2026, 10, 2)

    # Duyen dung 13 nen trong session d1:
    # 11 nen dau (i = 0..10): close tang dan 1000..1010, cvd tang dan 100..200
    bars_d1: list[BarSummary] = []
    t0 = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)
    for i in range(11):
        bars_d1.append(
            BarSummary(
                session_id=d1,
                block_id="morning",
                bar_idx=i,
                t_start=t0 + timedelta(minutes=5 * i),
                t_end=t0 + timedelta(minutes=5 * (i + 1)),
                open=1000.0 + i,
                high=1000.0 + i,
                low=1000.0 + i,
                close=1000.0 + i,
                close_k=int((1000.0 + i) * 10),
                delta=10.0,
                cvd=100.0 + i * 10.0,  # max cvd la 200.0
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
            )
        )

    # Nen thu 11 (index 10) chua du 11 nen truoc -> khong sinh E1
    events_10 = detect_e1_events(bars_d1[:11])
    assert len(events_10) == 0

    # Nen thu 12 (index 11): close = 1010.0 (BANG max 11 nen truoc) -> khong kich hoat!
    b_eq = BarSummary(
        session_id=d1,
        block_id="morning",
        bar_idx=11,
        t_start=t0 + timedelta(minutes=55),
        t_end=t0 + timedelta(minutes=60),
        open=1010.0,
        high=1010.0,
        low=1010.0,
        close=1010.0,  # Bang max
        close_k=10100,
        delta=-50.0,
        cvd=150.0,  # < max cvd
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    events_eq = detect_e1_events(bars_d1 + [b_eq])
    assert len(events_eq) == 0

    # Nen thu 12 (index 11): close = 1011.0 (> max) va cvd = 150.0 (< max) -> Kich hoat Ban (d = -1)
    b_trigger = BarSummary(
        session_id=d1,
        block_id="morning",
        bar_idx=11,
        t_start=t0 + timedelta(minutes=55),
        t_end=t0 + timedelta(minutes=60),
        open=1011.0,
        high=1011.0,
        low=1011.0,
        close=1011.0,
        close_k=10110,
        delta=-50.0,
        cvd=150.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    events_trig = detect_e1_events(bars_d1 + [b_trigger])
    assert len(events_trig) == 1
    assert events_trig[0].direction == -1
    assert events_trig[0].bar_idx == 11

    # Khong dung nen cua phien truoc: them nen phien d2 -> khong co du 11 nen trong d2
    b_d2 = BarSummary(
        session_id=d2,
        block_id="morning",
        bar_idx=0,
        t_start=datetime(2026, 10, 2, 9, 0, tzinfo=TZ),
        t_end=datetime(2026, 10, 2, 9, 5, tzinfo=TZ),
        open=1020.0,
        high=1020.0,
        low=1020.0,
        close=1020.0,
        close_k=10200,
        delta=-50.0,
        cvd=50.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    events_cross = detect_e1_events(bars_d1 + [b_trigger, b_d2])
    # Chi co 1 event o phien d1, phien d2 khong the lay nen d1
    assert len(events_cross) == 1


def test_4_e2_phan_ky_delta_trong_nen():
    """Ca 4: E2 nguong p90 lay tu 5 phien truoc, chieu d = sign(delta), close == open."""
    # Tao 6 phien (s0..s5), moi phien 10 nen
    sessions = [date(2026, 10, i + 1) for i in range(6)]
    all_bars: list[BarSummary] = []

    for s_idx, s_date in enumerate(sessions):
        t0 = datetime.combine(s_date, MORNING_START, tzinfo=TZ)
        for i in range(5):
            # 5 phien dau delta trong [-5, +5]
            d_val = 5.0 if (i % 2 == 0) else -5.0
            all_bars.append(
                BarSummary(
                    session_id=s_date,
                    block_id="morning",
                    bar_idx=i,
                    t_start=t0 + timedelta(minutes=5 * i),
                    t_end=t0 + timedelta(minutes=5 * (i + 1)),
                    open=1900.0,
                    high=1905.0,
                    low=1895.0,
                    close=1902.0 if d_val > 0 else 1898.0,
                    close_k=19020 if d_val > 0 else 18980,
                    delta=d_val,
                    cvd=d_val * (i + 1),
                    ask_k_min=None,
                    ask_k_max=None,
                    bid_k_min=None,
                    bid_k_max=None,
                )
            )

    # Phien thu 5 (index 4, sessions[4]) chi co 4 phien truoc -> khong sinh su kien
    bars_s0_s4 = [b for b in all_bars if b.session_id in sessions[:5]]
    events_s4 = detect_e2_events(bars_s0_s4)
    assert len(events_s4) == 0

    # Phien 6 (sessions[5]): p90 cua 5 phien truoc la 5.0
    # Thiet lap cac nen thu nghiem trong phien 6:
    s5_date = sessions[5]
    t0_s5 = datetime.combine(s5_date, MORNING_START, tzinfo=TZ)

    # Nen a: delta = +20 (> p90), close < open (1890 < 1900) -> Mua (d = +1)
    bar_buy = BarSummary(
        session_id=s5_date,
        block_id="morning",
        bar_idx=0,
        t_start=t0_s5,
        t_end=t0_s5 + timedelta(minutes=5),
        open=1900.0,
        high=1901.0,
        low=1889.0,
        close=1890.0,  # Nen giam
        close_k=18900,
        delta=20.0,  # Delta duong
        cvd=20.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )

    # Nen b: delta = -20 (< -p90), close > open (1910 > 1900) -> Ban (d = -1)
    bar_sell = BarSummary(
        session_id=s5_date,
        block_id="morning",
        bar_idx=1,
        t_start=t0_s5 + timedelta(minutes=5),
        t_end=t0_s5 + timedelta(minutes=10),
        open=1900.0,
        high=1911.0,
        low=1899.0,
        close=1910.0,  # Nen tang
        close_k=19100,
        delta=-20.0,  # Delta am
        cvd=0.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )

    # Nen c: delta = 50, close == open -> khong sinh su kien
    bar_doji = BarSummary(
        session_id=s5_date,
        block_id="morning",
        bar_idx=2,
        t_start=t0_s5 + timedelta(minutes=10),
        t_end=t0_s5 + timedelta(minutes=15),
        open=1900.0,
        high=1905.0,
        low=1895.0,
        close=1900.0,  # close == open
        close_k=19000,
        delta=50.0,
        cvd=50.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )

    # Nen d: them 5 nen delta khong lo sau do (bar_idx 3..7)
    huge_bars = [
        BarSummary(
            session_id=s5_date,
            block_id="morning",
            bar_idx=3 + k,
            t_start=t0_s5 + timedelta(minutes=15 + 5 * k),
            t_end=t0_s5 + timedelta(minutes=20 + 5 * k),
            open=1900.0,
            high=1900.0,
            low=1900.0,
            close=1900.0,
            close_k=19000,
            delta=99999.0,
            cvd=100049.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
        )
        for k in range(5)
    ]

    bars_test = bars_s0_s4 + [bar_buy, bar_sell, bar_doji] + huge_bars
    events = detect_e2_events(bars_test)

    assert len(events) == 2
    assert events[0].direction == +1  # Mua vi nguoi ban bi hap thu
    assert events[1].direction == -1  # Ban vi nguoi mua bi hap thu


def test_5_imbalance_va_e3():
    """Ca 5: Imbalance cheo, bay cung muc, bo doi hap thu -> khoi xuong E3."""
    # 1. Bay cung muc: so cung muc co ask imbalance, so cheo thi khong
    # Tai k=100: buy=10, sell=1. Neu so cung muc: 10 >= 3 * max(1, 1)=3 -> co imbalance
    # Nhung tai k-1=99: sell=10. So cheo: 10 >= 3 * max(10, 1)=30 -> KHONG co imbalance!
    fp_trap = {
        100: (10.0, 1.0),
        99: (0.0, 10.0),
    }
    ask_ks, _bid_ks = imbalance_levels(fp_trap)
    assert len(ask_ks) == 0  # So cheo khong co ask imbalance!

    # 2. San khoi luong min_vol = 5: buy=4 khong duoc tinh
    fp_low_vol = {
        100: (4.0, 0.0),
        99: (0.0, 0.0),
    }
    ask_ks_low, _ = imbalance_levels(fp_low_vol)
    assert len(ask_ks_low) == 0

    # 3. Kiem tra lien ke buoc gia: 1935.3 va 1935.4
    k1 = round(1935.3 * 10.0)
    k2 = round(1935.4 * 10.0)
    assert k2 - k1 == 1

    # 4. Bo doi mua dung (E3):
    # Nen t-1: hap thu ban (co bid imbalance, close > bid imbalance cao nhat)
    # Nen t  : khoi xuong mua (co ask imbalance, close >= ask imbalance cao nhat, khong co bid imbalance)
    s_date = date(2026, 10, 1)
    t_end_m = datetime(2026, 10, 1, 9, 10, tzinfo=TZ)

    bar_tm1 = BarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=0,
        t_start=t_end_m - timedelta(minutes=10),
        t_end=t_end_m - timedelta(minutes=5),
        open=1900.0,
        high=1905.0,
        low=1895.0,
        close=1904.0,  # close_k = 19040 > bid_k_max (19000)
        close_k=19040,
        delta=-10.0,
        cvd=-10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=18980,
        bid_k_max=19000,
    )

    bar_t = BarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=1,
        t_start=t_end_m - timedelta(minutes=5),
        t_end=t_end_m,
        open=1904.0,
        high=1910.0,
        low=1903.0,
        close=1908.0,  # close_k = 19080 >= ask_k_max (19080)
        close_k=19080,
        delta=25.0,
        cvd=15.0,
        ask_k_min=19050,
        ask_k_max=19080,
        bid_k_min=None,  # Khong co bid imbalance
        bid_k_max=None,
    )

    events_buy = detect_e3_events([bar_tm1, bar_t])
    assert len(events_buy) == 1
    assert events_buy[0].direction == +1

    # Nen t co them bid imbalance -> khong con khoi xuong mua -> khong co su kien
    bar_t_dirty = BarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=1,
        t_start=t_end_m - timedelta(minutes=5),
        t_end=t_end_m,
        open=1904.0,
        high=1910.0,
        low=1903.0,
        close=1908.0,
        close_k=19080,
        delta=25.0,
        cvd=15.0,
        ask_k_min=19050,
        ask_k_max=19080,
        bid_k_min=19020,  # Co them bid imbalance!
        bid_k_max=19020,
    )
    assert len(detect_e3_events([bar_tm1, bar_t_dirty])) == 0

    # close_{t-1} BANG bid imbalance cao nhat -> khong phai hap thu (nghiem ngat) -> khong co event
    bar_tm1_eq = BarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=0,
        t_start=t_end_m - timedelta(minutes=10),
        t_end=t_end_m - timedelta(minutes=5),
        open=1900.0,
        high=1905.0,
        low=1895.0,
        close=1900.0,  # close_k = 19000 == bid_k_max (19000)
        close_k=19000,
        delta=-10.0,
        cvd=-10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=18980,
        bid_k_max=19000,
    )
    assert len(detect_e3_events([bar_tm1_eq, bar_t])) == 0

    # 11:25 va 13:00 khac block_id -> khong ghep su kien
    bar_1125 = BarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=29,
        t_start=datetime(2026, 10, 1, 11, 25, tzinfo=TZ),
        t_end=datetime(2026, 10, 1, 11, 30, tzinfo=TZ),
        open=1900.0,
        high=1905.0,
        low=1895.0,
        close=1904.0,
        close_k=19040,
        delta=-10.0,
        cvd=-10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=18980,
        bid_k_max=19000,
    )
    bar_1300 = BarSummary(
        session_id=s_date,
        block_id="afternoon",
        bar_idx=30,
        t_start=datetime(2026, 10, 1, 13, 0, tzinfo=TZ),
        t_end=datetime(2026, 10, 1, 13, 5, tzinfo=TZ),
        open=1904.0,
        high=1910.0,
        low=1903.0,
        close=1908.0,
        close_k=19080,
        delta=25.0,
        cvd=15.0,
        ask_k_min=19050,
        ask_k_max=19080,
        bid_k_min=None,
        bid_k_max=None,
    )
    assert len(detect_e3_events([bar_1125, bar_1300])) == 0


def test_6_muc_tieu_va_chong_lan():
    """Ca 6: Tinh y theo d, P(x), bo su kien qua ket thuc khung, va loc khong chong lan."""
    s_date = date(2026, 10, 1)

    # Bang tra gia: gia = 1910.0 tai moi moc
    def price_lookup(t: datetime) -> float:
        return 1910.0

    # 1. Su kien mua: d = +1, close = 1900.0 -> y = +1 * (1910 - 1900) = +10.0
    ev_buy = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=s_date,
        block_id="morning",
        bar_idx=1,
        t_end=datetime(2026, 10, 1, 9, 15, tzinfo=TZ),
        close=1900.0,
    )
    res_buy = calculate_event_targets([ev_buy], price_lookup, h_minutes=15)
    assert len(res_buy) == 1
    assert res_buy[0].y == 10.0

    # 2. Su kien ban: d = -1, close = 1900.0 -> y = -1 * (1910 - 1900) = -10.0
    ev_sell = OrderFlowEvent(
        event_type="E1",
        direction=-1,
        session_id=s_date,
        block_id="morning",
        bar_idx=1,
        t_end=datetime(2026, 10, 1, 9, 15, tzinfo=TZ),
        close=1900.0,
    )
    res_sell = calculate_event_targets([ev_sell], price_lookup, h_minutes=15)
    assert len(res_sell) == 1
    assert res_sell[0].y == -10.0

    # 3. Su kien luc 11:20 (t_end = 11:25) voi H = 15:
    # 11:25 + 15m = 11:40 > 11:30 (ket thuc buoi sang) -> BI BO!
    ev_late = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=s_date,
        block_id="morning",
        bar_idx=28,
        t_end=datetime(2026, 10, 1, 11, 25, tzinfo=TZ),
        close=1900.0,
    )
    assert len(calculate_event_targets([ev_late], price_lookup, h_minutes=15)) == 0

    # 4. Loc chong lan: 2 su kien cach nhau < H thi chi nhan su kien dau
    ev1 = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=s_date,
        block_id="morning",
        bar_idx=1,
        t_end=datetime(2026, 10, 1, 9, 15, tzinfo=TZ),
        close=1900.0,
    )
    ev2 = OrderFlowEvent(
        event_type="E1",
        direction=-1,
        session_id=s_date,
        block_id="morning",
        bar_idx=2,
        t_end=datetime(2026, 10, 1, 9, 20, tzinfo=TZ),
        close=1905.0,
    )
    ev3 = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=s_date,
        block_id="morning",
        bar_idx=4,
        t_end=datetime(2026, 10, 1, 9, 30, tzinfo=TZ),
        close=1908.0,
    )
    filtered = filter_non_overlapping_events([ev1, ev2, ev3], h_minutes=15)
    assert len(filtered) == 2
    assert filtered[0].t_end == ev1.t_end
    assert filtered[1].t_end == ev3.t_end


def test_7_cong_ngay(capsys):
    """Ca 7: today < 2026-12-01 tra ma 2 va mock list_files khong duoc goi; today >= 2026-12-01 di tiep."""
    mock_list_files = MagicMock()

    # today = 2026-11-30 -> tra 2, mock khong duoc goi
    ret_before = main(today=date(2026, 11, 30), list_files_fn=mock_list_files)
    assert ret_before == 2
    assert mock_list_files.call_count == 0

    # today = 2026-12-01 -> di tiep va goi mock
    ret_after = main(today=date(2026, 12, 1), list_files_fn=mock_list_files)
    assert ret_after == 0
    assert mock_list_files.call_count == 1


def test_8_niem_phong_holdout(tmp_path):
    """Ca 8: Doc holdout khi log chua co dong cua dot 182 phai nem loi."""
    dummy_log = tmp_path / "holdout-unlock-log.md"

    # 1. Log khong ton tai -> nem loi
    with pytest.raises(RuntimeError, match="khong ton tai"):
        verify_holdout_log_unlocked(dummy_log)

    # 2. Log co dong khac nhung khong co dot 182 -> nem loi
    dummy_log.write_text("# Holdout Log\n| 2026-10-04 | dot 161 |\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Vi pham niem phong"):
        load_holdout_sessions(data_dir=str(tmp_path), log_path=dummy_log)

    # 3. Log co dong dot 182 -> hop le
    dummy_log.write_text("# Holdout Log\n| 2026-10-11 | VN30F orderflow (đợt 182) |\n", encoding="utf-8")
    assert verify_holdout_log_unlocked(dummy_log) is True


def test_9_nguong_chi_phi():
    """Ca 9: Hurdle tai gia 1900 bang 1.5 * (roundtrip_cost + 0.2), sai so 1e-12."""
    hurdle = compute_economic_hurdle(1900.0)
    # 1900.0: derivative cost = 0.488 diem -> (0.488 + 0.2) * 1.5 = 1.032
    expected = 1.5 * (0.488 + 0.2)
    assert math.isclose(hurdle, expected, abs_tol=1e-12)


def test_10_cong_kiem_is():
    """Ca 10: Ca bien cho 5 tieu chi IS cua §1.4, moi ca chi truot dung mot."""
    # Co so chuan (tat ca deu dat):
    # n_events = 100, n_buy = 50, n_sell = 50, p_val = 0.005, mean_y = 1.5, hurdle = 1.0, rho = 0.35
    hurdle = 1.0
    alpha_thresh = ALPHA_PER_PAIR  # 0.008333333333333333

    def _make_events(n: int, n_buy: int, n_sell: int, mean_val: float) -> list[OrderFlowEvent]:
        evs = []
        d0 = date(2026, 10, 1)
        t0 = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)
        for i in range(n_buy):
            evs.append(
                OrderFlowEvent("E1", +1, d0, "morning", i, t0, 1900.0, y=mean_val)
            )
        for i in range(n_sell):
            evs.append(
                OrderFlowEvent("E1", -1, d0, "morning", i + n_buy, t0, 1900.0, y=mean_val)
            )
        return evs

    # 1. Ca chuan dat
    ev_base = _make_events(100, 50, 50, 1.5)
    res_base = evaluate_pair_criteria(ev_base, hurdle=hurdle, control_rho=0.35, p_val=0.005)
    assert res_base["passed"] is True

    # 2. Truot: 99 su kien
    ev_99 = _make_events(99, 50, 49, 1.5)
    res_99 = evaluate_pair_criteria(ev_99, hurdle=hurdle, control_rho=0.35, p_val=0.005)
    assert res_99["passed"] is False
    assert res_99["cond1_sample"] is False

    # 3. Truot: mot huong chi co 29
    ev_29 = _make_events(100, 71, 29, 1.5)
    res_29 = evaluate_pair_criteria(ev_29, hurdle=hurdle, control_rho=0.35, p_val=0.005)
    assert res_29["passed"] is False
    assert res_29["cond1_sample"] is False

    # 4. Truot: p_val BANG dung alpha_thresh (dieu kien la < alpha_thresh)
    res_p_eq = evaluate_pair_criteria(ev_base, hurdle=hurdle, control_rho=0.35, p_val=alpha_thresh)
    assert res_p_eq["passed"] is False
    assert res_p_eq["cond2_stat"] is False

    # 5. Dat: trung binh BANG dung hurdle (dieu kien la >= hurdle)
    ev_hurdle_eq = _make_events(100, 50, 50, hurdle)
    res_h_eq = evaluate_pair_criteria(ev_hurdle_eq, hurdle=hurdle, control_rho=0.35, p_val=0.005)
    assert res_h_eq["cond3_hurdle"] is True
    assert res_h_eq["passed"] is True

    # 6. Truot: rho BANG dung 0.3 (dieu kien la > 0.3)
    res_rho_eq = evaluate_pair_criteria(ev_base, hurdle=hurdle, control_rho=0.3, p_val=0.005)
    assert res_rho_eq["cond_control"] is False
    assert res_rho_eq["passed"] is False


def test_11_bootstrap_theo_khoi_phien():
    """Ca 11: Bootstrap khoi phien: y=+1 -> p=0, doi xung -> 0.3 < p < 0.7, len(set) <= 3."""
    d0 = date(2026, 10, 1)
    t0 = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)

    # 1. Moi y = +1 -> p = 0
    evs_all_plus = [
        OrderFlowEvent("E1", +1, d0, "morning", i, t0, 1900.0, y=1.0)
        for i in range(50)
    ]
    p_plus, _ = block_bootstrap_p_value(evs_all_plus, n_bootstrap=500, seed=42)
    assert p_plus == 0.0

    # 2. y doi xung -> 0.3 < p < 0.7
    evs_sym = []
    for s_i in range(20):
        s_date = date(2026, 10, s_i + 1)
        val = +1.0 if (s_i % 2 == 0) else -1.0
        for i in range(10):
            evs_sym.append(
                OrderFlowEvent("E1", +1, s_date, "morning", i, t0, 1900.0, y=val)
            )
    p_sym, _ = block_bootstrap_p_value(evs_sym, n_bootstrap=1000, seed=42)
    assert 0.3 < p_sym < 0.7

    # 3. Cung seed cho cung p
    p_sym2, _ = block_bootstrap_p_value(evs_sym, n_bootstrap=1000, seed=42)
    assert p_sym == p_sym2

    # 4. Lay lai theo phien: 2 phien (A co 100 event y = +1, B co 1 event y = -50)
    # Moi lan lay chi co 3 to hop {A,A}, {B,B}, {A,B} -> len(set) <= 3
    dA = date(2026, 10, 1)
    dB = date(2026, 10, 2)
    evs_a = [
        OrderFlowEvent("E1", +1, dA, "morning", i, t0, 1900.0, y=1.0)
        for i in range(100)
    ]
    evs_b = [
        OrderFlowEvent("E1", -1, dB, "morning", 0, t0, 1900.0, y=-50.0)
    ]
    _, means = block_bootstrap_p_value(evs_a + evs_b, n_bootstrap=1000, seed=42)
    unique_means = set(np.round(means, 9))
    assert len(unique_means) <= 3
