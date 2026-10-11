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

import gzip
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from scripts.record_vn30f_orderbook import MORNING_START
from scripts.screen_vn30f_orderbook import load_all_sessions
from scripts.screen_vn30f_orderflow import (
    ALPHA_PER_PAIR,
    BarSummary,
    OrderFlowEvent,
    block_bootstrap_p_value,
    build_footprint_bars,
    build_footprint_bars_and_trades,
    build_price_lookup,
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


def test_7_cong_ngay(tmp_path):
    """Ca 7 (Brief 185): Cổng số phiên IS: chưa đủ 40 phiên hợp lệ -> trả mã 2 (bảo vệ chống nhìn trước)."""
    # Thư mục rỗng (< 40 phiên) -> trả 2 bất kể ngày
    ret_before = main(args=["--data-dir", str(tmp_path)], today=date(2026, 11, 30))
    assert ret_before == 2

    ret_after = main(args=["--data-dir", str(tmp_path)], today=date(2026, 12, 1))
    assert ret_after == 2


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


# --- Helpers & Ca kiem chung 12-18 (Brief dot 182b) ------------------------------


def _make_synthetic_session_file(
    session_date: date,
    filepath: Path,
    n_bars: int = 48,
    correlated: bool = True,
) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    m_start = datetime.combine(session_date, datetime.strptime("09:00:00", "%H:%M:%S").time(), tzinfo=TZ)
    a_start = datetime.combine(session_date, datetime.strptime("13:00:00", "%H:%M:%S").time(), tzinfo=TZ)

    records = []
    for b_idx in range(n_bars):
        if b_idx < 30:
            b_start = m_start + timedelta(minutes=5 * b_idx)
        else:
            b_start = a_start + timedelta(minutes=5 * (b_idx - 30))

        if correlated:
            if b_idx % 2 == 0:
                p1, p2 = 1900.0, 1902.0
                s1, s2 = "B", "B"
            else:
                p1, p2 = 1902.0, 1900.0
                s1, s2 = "S", "S"
        else:
            # Ngich dao delta voi huong gia: gia tang thi ban, gia giam thi mua -> rho = -1.0 <= 0.3
            if b_idx % 2 == 0:
                p1, p2 = 1900.0, 1902.0
                s1, s2 = "S", "S"  # gia tang, delta am
            else:
                p1, p2 = 1902.0, 1900.0
                s1, s2 = "B", "B"  # gia giam, delta duong

        for m in range(5):
            m_dt = b_start + timedelta(minutes=m)
            records.append({
                "type": "QUOTE",
                "bid_prices": [1900.0],
                "ask_prices": [1900.2],
                "bid_volumes": [10],
                "ask_volumes": [10],
                "trading_time": m_dt.strftime("%Y/%m/%d %H:%M:%S"),
                "recv_ts": m_dt.isoformat(),
            })

        t1 = b_start + timedelta(minutes=1)
        t2 = b_start + timedelta(minutes=3)
        records.append({
            "msg_type": "33",
            "side": s1,
            "price": p1,
            "quantity": 10,
            "trading_time": t1.strftime("%Y/%m/%d %H:%M:%S"),
            "recv_ts": t1.isoformat(),
        })
        records.append({
            "msg_type": "33",
            "side": s2,
            "price": p2,
            "quantity": 20,
            "trading_time": t2.strftime("%Y/%m/%d %H:%M:%S"),
            "recv_ts": t2.isoformat(),
        })

    with gzip.open(filepath, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_12_dau_cuoi_is_hop_le_va_khong_mo_holdout(tmp_path, monkeypatch, capsys):
    """Ca 12: Dau-cuoi today=2026-12-01: 40 phien hop le, 1 file cat cut, 1 phien thua, 1 file holdout.
    Assert return 0, bao 40 hop le, file hong, phien thua, bang 6 dong, file holdout KHONG bi mo.
    """
    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)

    current_d = date(2026, 10, 1)
    for _ in range(20):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(current_d, f, n_bars=48, correlated=True)
        current_d += timedelta(days=1)

    # 1 file IS bi cat cut (nam giua cac phien de loader doc qua no)
    corrupt_d = current_d
    corrupt_f = contract_dir / f"{corrupt_d.isoformat()}.jsonl.gz"
    _make_synthetic_session_file(corrupt_d, corrupt_f, n_bars=48, correlated=True)
    raw_bytes = corrupt_f.read_bytes()
    corrupt_f.write_bytes(raw_bytes[: len(raw_bytes) // 2])
    current_d += timedelta(days=1)

    # 1 phien IS chi co 10 nen co giao dich
    sparse_d = current_d
    sparse_f = contract_dir / f"{sparse_d.isoformat()}.jsonl.gz"
    _make_synthetic_session_file(sparse_d, sparse_f, n_bars=10, correlated=True)
    current_d += timedelta(days=1)

    # 20 phien hop le tiep theo de dat du 40 phien hop le
    for _ in range(20):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(current_d, f, n_bars=48, correlated=True)
        current_d += timedelta(days=1)

    # 1 file ngay 2026-12-02 (Holdout)
    holdout_d = date(2026, 12, 2)
    holdout_f = contract_dir / f"{holdout_d.isoformat()}.jsonl.gz"
    _make_synthetic_session_file(holdout_d, holdout_f, n_bars=48, correlated=True)

    opened_files: list[str] = []
    import scripts.screen_vn30f_orderflow as mod
    orig_iter = mod.iter_file_messages

    def spy_iter(path):
        opened_files.append(Path(path).name)
        return orig_iter(path)

    monkeypatch.setattr(mod, "iter_file_messages", spy_iter)

    ret = mod.main(args=["--data-dir", str(tmp_path)], today=date(2026, 12, 1))
    captured = capsys.readouterr()

    assert ret == 0
    assert "Số phiên hợp lệ (>= 44/48 nến): 40" in captured.out
    assert "file hỏng" in captured.out
    assert "phiên thưa" in captured.out
    for p_name in ("E1_H15", "E1_H30", "E2_H15", "E2_H30", "E3_H15", "E3_H30"):
        assert p_name in captured.out

    assert "2026-12-02.jsonl.gz" not in opened_files


def test_13_khong_du_phien_is_return_3(tmp_path, capsys):
    """Ca 13 (Brief 185): Chi co 39 phien hop le -> in CHUA DU PHIEN IS va return 2."""
    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)

    current_d = date(2026, 10, 1)
    for _ in range(39):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(current_d, f, n_bars=48, correlated=True)
        current_d += timedelta(days=1)

    import scripts.screen_vn30f_orderflow as mod
    ret = mod.main(args=["--data-dir", str(tmp_path)], today=date(2026, 12, 1))
    captured = capsys.readouterr()

    assert ret == 2
    assert "CHƯA ĐỦ PHIÊN IS: 39/40" in captured.err


def test_14_control_variable_that_bai_return_4(tmp_path, capsys):
    """Ca 14: Side gan doc lap/nguoc huong gia -> rho <= 0.3 -> return 4."""
    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)

    current_d = date(2026, 10, 1)
    for _ in range(40):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(current_d, f, n_bars=48, correlated=False)
        current_d += timedelta(days=1)

    import scripts.screen_vn30f_orderflow as mod
    ret = mod.main(args=["--data-dir", str(tmp_path)], today=date(2026, 12, 1))
    captured = capsys.readouterr()

    assert ret == 4
    assert "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN" in captured.err


def test_15_price_lookup():
    """Ca 15: price_lookup: tin dung luc x duoc lay; x + 1s thi khong; tin U dung luc x bi bo qua."""
    x = datetime(2026, 10, 1, 9, 15, 0, tzinfo=TZ)
    msgs = [
        {"msg_type": "33", "side": "B", "price": 1900.0, "quantity": 10, "trading_time": "2026/10/01 09:10:00"},
        {"msg_type": "33", "side": "S", "price": 1905.0, "quantity": 10, "trading_time": "2026/10/01 09:15:00"},
        {"msg_type": "33", "side": "U", "price": 1908.0, "quantity": 10, "trading_time": "2026/10/01 09:15:00"},
        {"msg_type": "33", "side": "B", "price": 1910.0, "quantity": 10, "trading_time": "2026/10/01 09:15:01"},
    ]
    _, clean_trades, stats = build_footprint_bars_and_trades(msgs, session_date=date(2026, 10, 1))
    lookup = build_price_lookup(clean_trades)

    assert lookup(x) == 1905.0
    assert lookup(x) != 1910.0
    assert lookup(x) != 1908.0
    assert stats["dropped_u_or_zero"] == 1
    assert lookup(x + timedelta(seconds=1)) == 1910.0


def test_16_holdout_quy_trinh_va_return_5(tmp_path, monkeypatch):
    """Ca 16: Holdout:
    - Cap khong DAT -> return 5, log khong doi, loader holdout khong duoc goi.
    - Cap DAT -> trinh tu goi: GHI LOG ROI MOI NAP HOLDOUT.
    - Lan hai cung cap -> return 5 (vi log da co).
    """
    import scripts.screen_vn30f_orderflow as mod

    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)
    current_d = date(2026, 10, 1)
    for _ in range(40):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(current_d, f, n_bars=48, correlated=True)
        current_d += timedelta(days=1)

    h_dir = tmp_path / "VN30F2612"
    h_dir.mkdir(parents=True, exist_ok=True)
    for i in range(30):
        h_d = date(2026, 12, 1) + timedelta(days=i)
        f_h = h_dir / f"{h_d.isoformat()}.jsonl.gz"
        _make_synthetic_session_file(h_d, f_h, n_bars=48, correlated=True)

    dummy_log = tmp_path / "holdout-unlock-log.md"

    # 1. Cap khong DAT o IS -> return 5, mock loader khong duoc goi
    mock_load_holdout = MagicMock()
    monkeypatch.setattr(mod, "load_holdout_sessions_orderflow", mock_load_holdout)

    orig_eval = mod.evaluate_pair_criteria
    def fail_eval(*args, **kwargs):
        res = orig_eval(*args, **kwargs)
        res["passed"] = False
        return res
    monkeypatch.setattr(mod, "evaluate_pair_criteria", fail_eval)

    ret1 = mod.main(
        args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "E1_H15"],
        today=date(2027, 1, 1),
        unlock_log_path=dummy_log,
    )
    assert ret1 == 5
    assert not dummy_log.exists()
    assert mock_load_holdout.call_count == 0

    # 2. Cap DAT o IS -> trinh tu: GHI LOG ROI MOI NAP HOLDOUT
    call_sequence = []
    def pass_eval(*args, **kwargs):
        res = orig_eval(*args, **kwargs)
        res["passed"] = True
        return res
    monkeypatch.setattr(mod, "evaluate_pair_criteria", pass_eval)

    def spy_load_holdout(*args, **kwargs):
        assert dummy_log.exists()
        log_text = dummy_log.read_text(encoding="utf-8").lower()
        assert "đợt 182" in log_text
        assert "e1_h15" in log_text
        call_sequence.append("load_holdout")
        return []
    monkeypatch.setattr(mod, "load_holdout_sessions_orderflow", spy_load_holdout)

    ret2 = mod.main(
        args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "E1_H15"],
        today=date(2027, 1, 1),
        unlock_log_path=dummy_log,
    )
    assert ret2 == 0
    assert "load_holdout" in call_sequence
    assert dummy_log.exists()
    assert "E1_H15" in dummy_log.read_text(encoding="utf-8")

    # 3. Lan hai cung cap -> return 5 (vi log da ton tai dong dot 182)
    ret3 = mod.main(
        args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "E1_H15"],
        today=date(2027, 1, 1),
        unlock_log_path=dummy_log,
    )
    assert ret3 == 5


def test_17_162_file_cat_cut_khong_sap(tmp_path):
    """Ca 17: load_all_sessions cua 162 tren thu muc co file bi cat cut khong sap,
    phien do is_valid=False, file lanh con lai van doc duoc.
    """
    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)

    healthy_f = contract_dir / "2026-10-01.jsonl.gz"
    _make_synthetic_session_file(date(2026, 10, 1), healthy_f, n_bars=48, correlated=True)

    corrupt_f = contract_dir / "2026-10-02.jsonl.gz"
    _make_synthetic_session_file(date(2026, 10, 2), corrupt_f, n_bars=48, correlated=True)
    raw = corrupt_f.read_bytes()
    corrupt_f.write_bytes(raw[: len(raw) // 2])

    sessions = load_all_sessions(tmp_path)
    assert len(sessions) == 2

    s_healthy = next(s for s in sessions if s.session_date == date(2026, 10, 1))
    s_corrupt = next(s for s in sessions if s.session_date == date(2026, 10, 2))

    assert s_healthy.is_valid is True
    assert s_corrupt.is_valid is False


def test_18_calculate_event_targets_block_end_fn_rieng():
    """Ca 18: calculate_event_targets voi block_end_fn rieng:
    su kien co t_end + H bang dung gio ket thuc -> giu; vuot 1 phut -> bo.
    """
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=TZ)
    ev1 = OrderFlowEvent("E1", +1, date(2026, 10, 1), "morning", 12, t0, 1900.0)

    t1 = datetime(2026, 10, 1, 10, 1, 0, tzinfo=TZ)
    ev2 = OrderFlowEvent("E1", +1, date(2026, 10, 1), "morning", 12, t1, 1900.0)

    custom_end = datetime(2026, 10, 1, 10, 15, 0, tzinfo=TZ)
    fn_end = lambda e: custom_end
    dummy_lookup = lambda dt: 1905.0

    kept = calculate_event_targets([ev1, ev2], dummy_lookup, h_minutes=15, block_end_fn=fn_end)
    assert len(kept) == 1
    assert kept[0].t_end == ev1.t_end
    assert kept[0].target_time == custom_end


def test_19_phan_quyet_holdout_giong_162():
    """Ca 19 (Claude bo sung khi audit 182b): Holdout dat khi p < 0.05 va mean_y >= hurdle, khong doi 100 su kien."""
    from scripts.screen_vn30f_orderflow import holdout_verdict

    assert holdout_verdict(0.049, 1.032, 1.032) is True
    assert holdout_verdict(0.05, 2.0, 1.032) is False
    assert holdout_verdict(0.01, 1.031, 1.032) is False


# --- T5: 182 loader dung sau phien 40 va khong mo today (Brief 185 §2) ---
def test_t5_182_loader_dung_sau_phien_40_va_khong_mo_today(tmp_path, monkeypatch):
    """T5 (Brief 185 §2): 182 loader: 42 file (40 hợp lệ + 1 cắt cụt xen giữa + 1 sau phiên 40) và 1 file ngày today.
    Spy iter_file_messages: file sau phiên 40 và file today KHÔNG bị mở; file cắt cụt không làm sập và không được đếm.
    """
    import scripts.screen_vn30f_orderflow as mod

    c_dir = tmp_path / "VN30F2610"
    c_dir.mkdir(parents=True)
    today = date(2026, 11, 20)
    d_start = date(2026, 9, 25)

    # 20 phien hop le dau
    dates_valid = [d_start + timedelta(days=i) for i in range(20)]
    # 1 file cat cut o ngay 21
    corrupt_date = d_start + timedelta(days=20)
    # 20 phien hop le tiep (tong 40 hop le)
    dates_valid += [d_start + timedelta(days=21 + i) for i in range(20)]
    # 1 file sau phien 40
    after_date = d_start + timedelta(days=41)
    # 1 file ngay today
    today_date = today

    for d in dates_valid:
        f = c_dir / f"{d.isoformat()}.jsonl.gz"
        with gzip.open(f, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    # File cat cut
    cf = c_dir / f"{corrupt_date.isoformat()}.jsonl.gz"
    with gzip.open(cf, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": f"{corrupt_date.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")
    cf.write_bytes(cf.read_bytes()[:10])

    # File sau phien 40
    af = c_dir / f"{after_date.isoformat()}.jsonl.gz"
    with gzip.open(af, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": f"{after_date.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    # File today
    tf = c_dir / f"{today_date.isoformat()}.jsonl.gz"
    with gzip.open(tf, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": f"{today_date.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    opened_paths: list[Path] = []
    orig_iter = mod.iter_file_messages

    def spy_iter(path):
        opened_paths.append(Path(path))
        return orig_iter(path)

    def fake_build(messages, s_date, stats=None):
        list(messages)
        bars = [
            mod.FootprintBar(
                session_id=s_date,
                block_id="morning",
                bar_idx=i,
                t_start=datetime(2026, 10, 1, 9, 0, tzinfo=TZ),
                t_end=datetime(2026, 10, 1, 9, 5, tzinfo=TZ),
                open=1900.0,
                high=1905.0,
                low=1895.0,
                close=1900.0,
                close_k=19000,
                delta=10.0,
                cvd=10.0,
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
                buy=20.0,
                sell=10.0,
                fp=None,
                trade_count=10,
            )
            for i in range(48)
        ]
        return bars, [], {}

    monkeypatch.setattr(mod, "iter_file_messages", spy_iter)
    monkeypatch.setattr(mod, "build_footprint_bars_and_trades", fake_build)

    sessions = mod.load_is_sessions_orderflow(tmp_path, today=today)
    opened_names = {p.name for p in opened_paths}

    assert f"{after_date.isoformat()}.jsonl.gz" not in opened_names
    assert f"{today_date.isoformat()}.jsonl.gz" not in opened_names
    assert f"{corrupt_date.isoformat()}.jsonl.gz" in opened_names

    valid_sessions = [s for s in sessions if s.is_valid]
    assert len(valid_sessions) == 40
    corrupt_sess = [s for s in sessions if s.session_date == corrupt_date]
    assert len(corrupt_sess) == 1
    assert corrupt_sess[0].is_valid is False
    assert corrupt_sess[0].invalid_reason == "file hỏng"

    # Kiem tra file ngay today khong bi mo ngay ca khi chua du 40 phien (ngay 2026-10-05):
    opened_paths.clear()
    mod.load_is_sessions_orderflow(tmp_path, today=date(2026, 10, 5))
    opened_today = {p.name for p in opened_paths}
    assert "2026-10-05.jsonl.gz" not in opened_today


# --- T6: 182 main chua du phien tra 2 khong goi detect_e1 (Brief 185 §2) ---
def test_t6_182_main_chua_du_phien_tra_2_khong_goi_detect_e1(tmp_path, monkeypatch, capsys):
    """T6 (Brief 185 §2): 182 main khi 39 phiên -> return 2; detect_e1_events (spy) không được gọi."""
    import scripts.screen_vn30f_orderflow as mod

    contract_dir = tmp_path / "VN30F2610"
    contract_dir.mkdir(parents=True, exist_ok=True)
    current_d = date(2026, 9, 25)
    for _ in range(39):
        f = contract_dir / f"{current_d.isoformat()}.jsonl.gz"
        with gzip.open(f, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{current_d.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")
        current_d += timedelta(days=1)

    def fake_build(messages, s_date, stats=None):
        list(messages)
        bars = [
            mod.FootprintBar(
                session_id=s_date,
                block_id="morning",
                bar_idx=i,
                t_start=datetime(2026, 10, 1, 9, 0, tzinfo=TZ),
                t_end=datetime(2026, 10, 1, 9, 5, tzinfo=TZ),
                open=1900.0,
                high=1905.0,
                low=1895.0,
                close=1900.0,
                close_k=19000,
                delta=10.0,
                cvd=10.0,
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
                buy=20.0,
                sell=10.0,
                fp=None,
                trade_count=10,
            )
            for i in range(48)
        ]
        return bars, [], {}

    called_e1 = False
    def spy_e1(*args, **kwargs):
        nonlocal called_e1
        called_e1 = True
        return []

    monkeypatch.setattr(mod, "build_footprint_bars_and_trades", fake_build)
    monkeypatch.setattr(mod, "detect_e1_events", spy_e1)

    ret = mod.main(args=["--data-dir", str(tmp_path)], today=date(2026, 12, 1))
    captured = capsys.readouterr()

    assert ret == 2
    assert "39/40" in captured.err
    assert called_e1 is False


# --- T7: 182 holdout su kien ngay boundary khong vao h_ev_list (Brief 185 §2) ---
def test_t7_182_holdout_su_kien_ngay_boundary_khong_vao_h_ev_list():
    """T7 (Brief 185 §2): Sự kiện của ngày boundary không vào h_ev_list; sự kiện của phiên sau đó thì có."""
    from scripts.screen_vn30f_orderflow import filter_holdout_events

    boundary = date(2026, 11, 10)
    day_before = date(2026, 11, 9)
    day_boundary = date(2026, 11, 10)
    day_after = date(2026, 11, 11)

    t0 = datetime(2026, 11, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 11, 11, 9, 30, tzinfo=TZ)

    ev_before = OrderFlowEvent("E1", +1, day_before, "morning", 5, t0, 1900.0)
    ev_boundary = OrderFlowEvent("E1", +1, day_boundary, "morning", 5, t0, 1900.0)
    ev_after = OrderFlowEvent("E1", +1, day_after, "morning", 5, t1, 1905.0)

    h_ev_list = filter_holdout_events([ev_before, ev_boundary, ev_after], boundary=boundary)

    assert ev_before not in h_ev_list
    assert ev_boundary not in h_ev_list
    assert ev_after in h_ev_list
    assert len(h_ev_list) == 1


def test_t10_loader_182_keo_is_qua_01_12_va_qua_roll(tmp_path):
    """Claude audit 185: loader 182 phai mo phien thang 12 khi phien hop le thu 40 roi vao thang 12.

    Hai hop dong (roll 19/11 -> 20/11); xen phien thua nen phien hop le thu 40 nam sau 01/12.
    """
    d = date(2026, 11, 1)
    valid_dates: list[date] = []
    i = 0
    while len(valid_dates) < 41:
        folder = tmp_path / ("41I1GB000" if d <= date(2026, 11, 19) else "41I1GC000")
        f = folder / f"{d.isoformat()}.jsonl.gz"
        if i % 4 == 3:
            _make_synthetic_session_file(d, f, n_bars=10, correlated=True)
        else:
            _make_synthetic_session_file(d, f, n_bars=48, correlated=True)
            valid_dates.append(d)
        d += timedelta(days=1)
        i += 1

    from scripts import screen_vn30f_orderflow as mod

    sessions = mod.load_is_sessions_orderflow(tmp_path, today=date(2027, 1, 31))
    valid = [s for s in sessions if s.is_valid]
    assert len(valid) == 40
    assert valid[-1].session_date == valid_dates[39]
    assert valid[-1].session_date > date(2026, 11, 30)
    assert {s.contract for s in valid} == {"41I1GB000", "41I1GC000"}
    assert all(s.session_date != valid_dates[40] for s in sessions)
