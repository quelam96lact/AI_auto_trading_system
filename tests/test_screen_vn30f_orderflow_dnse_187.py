"""Test suite cho scripts/screen_vn30f_orderflow_dnse_187.py (Brief đợt 187 Tests 1..10)."""

from __future__ import annotations

import copy
import gzip
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import scripts.screen_crypto_orderflow as screen_crypto
import scripts.screen_vn30f_orderflow as screen_182
import scripts.screen_vn30f_orderflow_dnse as screen_dnse
import scripts.screen_vn30f_orderflow_dnse_187 as screen_187
from scripts.fetch_dnse_vn30f_trades import front_month_symbol
from scripts.screen_crypto_orderflow import CryptoBarSummary
from scripts.screen_vn30f_orderbook import IS_START_DATE
from scripts.screen_vn30f_orderflow import (
    FootprintBar,
    OrderFlowEvent,
    evaluate_pair_criteria,
)
from tests.test_screen_vn30f_orderflow_dnse import _generate_canonical_session_rows
from trading.calendar_vn import TZ


# --- Test 1: Hằng mới đúng giá trị §2.1 ---
def test_1_constants():
    """Hằng mới đúng giá trị Brief 187 §2.1:
    E3_MIN_VOL_PCT = 95.0, E3_DENOM_FLOOR_PCT = 50.0, E2_DELTA_PCT = 25.0,
    ALPHA_MAIN = 0.05 / 4, MAX_BOTH_SIDES_SHARE = 0.5, WARMUP_SESSIONS = 5.
    """
    assert screen_187.E3_MIN_VOL_PCT == 95.0
    assert screen_187.E3_DENOM_FLOOR_PCT == 50.0
    assert screen_187.E2_DELTA_PCT == 25.0
    assert screen_187.ALPHA_MAIN == pytest.approx(0.05 / 4.0)
    assert screen_187.MAX_BOTH_SIDES_SHARE == 0.5
    assert screen_187.WARMUP_SESSIONS == 5
    assert screen_187.HORIZONS == (15, 30)


# --- Test 2: apply_relative_imbalance_pct trùng crypto ở (90, 50), khác ở 95 ---
def test_2_apply_relative_imbalance_pct_compatibility():
    """Trên cùng một bộ nến có fp:
    - apply_relative_imbalance_pct(bars, 90.0, 50.0) cho ra ask_k_min/ask_k_max/bid_k_min/bid_k_max
      trùng từng nến với apply_relative_imbalance của crypto.
    - Với 95.0 thì có ít nhất một nến khác.
    """
    sessions = [date(2026, 4, 1) + timedelta(days=i) for i in range(7)]
    base_dt = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)

    # 5 phiên đầu khởi động: mỗi phiên 2 nến, tạo pool 20 giá trị [10]*11 + [20, 30, ..., 100]
    # Pool sẽ có: p50 = 10.0, p90 = 81.0, p95 = 90.5
    v_list = [10.0] * 2 + [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    bars_pool: list[CryptoBarSummary] = []
    idx = 0
    for s_idx in range(5):
        s_date = sessions[s_idx]
        for b_in_s in range(2):
            v = v_list[idx]
            idx += 1
            # sell ở 100 = 10.0, buy ở 101 = v
            fp = {100: (0.0, 10.0), 101: (v, 0.0)}
            bars_pool.append(
                CryptoBarSummary(
                    session_id=s_date,
                    block_id="morning",
                    bar_idx=b_in_s,
                    t_start=base_dt + timedelta(days=s_idx, minutes=b_in_s * 5),
                    t_end=base_dt + timedelta(days=s_idx, minutes=(b_in_s + 1) * 5),
                    open=1800.0,
                    high=1805.0,
                    low=1795.0,
                    close=1802.0,
                    close_k=18020,
                    delta=10.0,
                    cvd=10.0,
                    ask_k_min=None,
                    ask_k_max=None,
                    bid_k_min=None,
                    bid_k_max=None,
                    fp=fp,
                )
            )

    # Phiên 6 (ngày thứ 6, s_idx = 5):
    # Nến 0: buy = 75.0 (nằm giữa p90=71.0 và p95=80.5). Với min_vol p90 -> kích hoạt; với p95 -> không kích hoạt.
    # Nến 1: buy = 120.0 (vượt cả p95). Với denom_floor p50=10.0 -> ratio 12.0 >= 3.0 -> kích hoạt;
    #        với denom_floor p90=71.0 -> ratio 1.69 < 3.0 -> không kích hoạt.
    s_date_eval = sessions[5]
    bar_eval_0 = CryptoBarSummary(
        session_id=s_date_eval,
        block_id="morning",
        bar_idx=0,
        t_start=base_dt + timedelta(days=5, minutes=0),
        t_end=base_dt + timedelta(days=5, minutes=5),
        open=1800.0,
        high=1805.0,
        low=1795.0,
        close=1802.0,
        close_k=18020,
        delta=10.0,
        cvd=10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
        fp={100: (0.0, 1.0), 101: (75.0, 0.0)},
    )
    bar_eval_1 = CryptoBarSummary(
        session_id=s_date_eval,
        block_id="morning",
        bar_idx=1,
        t_start=base_dt + timedelta(days=5, minutes=5),
        t_end=base_dt + timedelta(days=5, minutes=10),
        open=1800.0,
        high=1805.0,
        low=1795.0,
        close=1802.0,
        close_k=18020,
        delta=10.0,
        cvd=10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
        fp={100: (0.0, 1.0), 101: (120.0, 0.0)},
    )
    eval_bars = [bar_eval_0, bar_eval_1]

    all_bars_raw = bars_pool + eval_bars

    bars_crypto = copy.deepcopy(all_bars_raw)
    bars_187_p90 = copy.deepcopy(all_bars_raw)
    bars_187_p95 = copy.deepcopy(all_bars_raw)

    # 1. Chạy crypto apply_relative_imbalance
    screen_crypto.apply_relative_imbalance(bars_crypto)

    # 2. Chạy 187 apply_relative_imbalance_pct với (90.0, 50.0)
    screen_187.apply_relative_imbalance_pct(bars_187_p90, min_vol_pct=90.0, floor_pct=50.0)

    # Kiểm tra trùng khớp 100% từng nến
    assert len(bars_187_p90) == len(bars_crypto)
    for b_187, b_c in zip(bars_187_p90, bars_crypto):
        assert b_187.ask_k_min == b_c.ask_k_min
        assert b_187.ask_k_max == b_c.ask_k_max
        assert b_187.bid_k_min == b_c.bid_k_min
        assert b_187.bid_k_max == b_c.bid_k_max

    # 3. Chạy 187 apply_relative_imbalance_pct với 95.0
    screen_187.apply_relative_imbalance_pct(bars_187_p95, min_vol_pct=95.0, floor_pct=50.0)

    # Với 95.0 thì có ít nhất một nến khác
    diffs = [
        (b_95, b_c)
        for b_95, b_c in zip(bars_187_p95, bars_crypto)
        if (
            b_95.ask_k_min != b_c.ask_k_min
            or b_95.ask_k_max != b_c.ask_k_max
            or b_95.bid_k_min != b_c.bid_k_min
            or b_95.bid_k_max != b_c.bid_k_max
        )
    ]
    assert len(diffs) >= 1
    # Cụ thể, nến 0 ở phiên 6: p90 có ask_k_min = 101, nhưng p95 có ask_k_min = None
    assert bars_187_p90[-2].ask_k_min == 101
    assert bars_187_p95[-2].ask_k_min is None


# --- Test 3: detect_e2_events_pct trùng detect_e2_events ở 90.0, nhiều hơn ở 25.0 ---
def test_3_detect_e2_events_pct_compatibility():
    """detect_e2_events_pct(bars, 90.0) trùng từng sự kiện (session_id, bar_idx, direction) với detect_e2_events(bars).
    Với 25.0 thì ra nhiều sự kiện hơn.
    """
    sessions = [date(2026, 4, 1) + timedelta(days=i) for i in range(6)]
    base_dt = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)
    bars: list[FootprintBar] = []

    # 5 phiên đầu khởi động (mỗi phiên 10 nến), abs(delta) từ 10.0 đến 100.0
    for s_idx in range(5):
        s_date = sessions[s_idx]
        for b_idx in range(10):
            delta_val = float((s_idx * 10 + b_idx) + 10)  # 10..59
            bars.append(
                FootprintBar(
                    session_id=s_date,
                    block_id="morning",
                    bar_idx=b_idx,
                    t_start=base_dt + timedelta(days=s_idx, minutes=b_idx * 5),
                    t_end=base_dt + timedelta(days=s_idx, minutes=(b_idx + 1) * 5),
                    open=1800.0,
                    high=1805.0,
                    low=1795.0,
                    close=1802.0,
                    close_k=18020,
                    delta=delta_val,
                    cvd=delta_val,
                    ask_k_min=None,
                    ask_k_max=None,
                    bid_k_min=None,
                    bid_k_max=None,
                    buy=delta_val,
                    sell=0.0,
                    fp={},
                    trade_count=10,
                )
            )

    # Phiên 6 (s_idx = 5):
    # Nến 0: delta = 100.0 (> p90), close < open => d = +1 (kích hoạt ở cả 90 và 25)
    # Nến 1: delta = 30.0 (giữa p25 và p90), close < open => d = +1 (chỉ kích hoạt ở 25)
    # Nến 2: delta = -30.0 (giữa p25 và p90), close > open => d = -1 (chỉ kích hoạt ở 25)
    s_date_eval = sessions[5]
    bars.append(
        FootprintBar(
            session_id=s_date_eval,
            block_id="morning",
            bar_idx=0,
            t_start=base_dt + timedelta(days=5, minutes=0),
            t_end=base_dt + timedelta(days=5, minutes=5),
            open=1805.0,
            high=1806.0,
            low=1799.0,
            close=1800.0,
            close_k=18000,
            delta=100.0,
            cvd=100.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
            buy=100.0,
            sell=0.0,
            fp={},
            trade_count=10,
        )
    )
    bars.append(
        FootprintBar(
            session_id=s_date_eval,
            block_id="morning",
            bar_idx=1,
            t_start=base_dt + timedelta(days=5, minutes=5),
            t_end=base_dt + timedelta(days=5, minutes=10),
            open=1805.0,
            high=1806.0,
            low=1799.0,
            close=1800.0,
            close_k=18000,
            delta=30.0,
            cvd=130.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
            buy=30.0,
            sell=0.0,
            fp={},
            trade_count=10,
        )
    )
    bars.append(
        FootprintBar(
            session_id=s_date_eval,
            block_id="morning",
            bar_idx=2,
            t_start=base_dt + timedelta(days=5, minutes=10),
            t_end=base_dt + timedelta(days=5, minutes=15),
            open=1800.0,
            high=1806.0,
            low=1799.0,
            close=1805.0,
            close_k=18050,
            delta=-30.0,
            cvd=100.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
            buy=0.0,
            sell=30.0,
            fp={},
            trade_count=10,
        )
    )

    ev_182 = screen_182.detect_e2_events(bars)
    ev_187_p90 = screen_187.detect_e2_events_pct(bars, pct=90.0)
    ev_187_p25 = screen_187.detect_e2_events_pct(bars, pct=25.0)

    # 1. Trùng từng sự kiện giữa p90 và 182
    assert len(ev_187_p90) == len(ev_182) == 1
    assert ev_187_p90[0].session_id == ev_182[0].session_id
    assert ev_187_p90[0].bar_idx == ev_182[0].bar_idx
    assert ev_187_p90[0].direction == ev_182[0].direction

    # 2. Với 25.0 thì ra nhiều sự kiện hơn
    assert len(ev_187_p25) > len(ev_187_p90)
    assert len(ev_187_p25) == 3


# --- Test 4: Ngưỡng chỉ lấy từ 5 phiên trước ---
def test_4_threshold_only_from_previous_5_sessions():
    """Ngưỡng chỉ lấy từ 5 phiên trước: đổi fp hoặc delta của phiên hiện tại thành cực lớn
    thì ngưỡng của chính phiên đó không đổi.
    """
    sessions = [date(2026, 4, 1) + timedelta(days=i) for i in range(6)]
    base_dt = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)

    bars_orig: list[CryptoBarSummary] = []
    # 5 phiên trước
    for s_idx in range(5):
        s_date = sessions[s_idx]
        for b_idx in range(2):
            bars_orig.append(
                CryptoBarSummary(
                    session_id=s_date,
                    block_id="morning",
                    bar_idx=b_idx,
                    t_start=base_dt + timedelta(days=s_idx, minutes=b_idx * 5),
                    t_end=base_dt + timedelta(days=s_idx, minutes=(b_idx + 1) * 5),
                    open=1800.0,
                    high=1805.0,
                    low=1795.0,
                    close=1802.0,
                    close_k=18020,
                    delta=10.0,
                    cvd=10.0,
                    ask_k_min=None,
                    ask_k_max=None,
                    bid_k_min=None,
                    bid_k_max=None,
                    fp={100: (0.0, 10.0), 101: (20.0, 0.0)},
                )
            )

    # Phiên 6 (ngày thứ 6):
    # Nến 0: nến mục tiêu kiểm tra
    s_date_eval = sessions[5]
    bars_orig.append(
        CryptoBarSummary(
            session_id=s_date_eval,
            block_id="morning",
            bar_idx=0,
            t_start=base_dt + timedelta(days=5, minutes=0),
            t_end=base_dt + timedelta(days=5, minutes=5),
            open=1805.0,
            high=1806.0,
            low=1795.0,
            close=1800.0,
            close_k=18000,
            delta=50.0,
            cvd=50.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
            fp={100: (0.0, 1.0), 101: (100.0, 0.0)},
        )
    )
    # Nến 1: nến khác trong cùng phiên
    bars_orig.append(
        CryptoBarSummary(
            session_id=s_date_eval,
            block_id="morning",
            bar_idx=1,
            t_start=base_dt + timedelta(days=5, minutes=5),
            t_end=base_dt + timedelta(days=5, minutes=10),
            open=1800.0,
            high=1805.0,
            low=1795.0,
            close=1802.0,
            close_k=18020,
            delta=10.0,
            cvd=60.0,
            ask_k_min=None,
            ask_k_max=None,
            bid_k_min=None,
            bid_k_max=None,
            fp={100: (0.0, 10.0), 101: (10.0, 0.0)},
        )
    )

    bars_mod = copy.deepcopy(bars_orig)
    # Trong bars_mod: sửa nến 1 của phiên hiện tại thành khối lượng và delta cực lớn (1 tỷ)
    bars_mod[-1].fp = {100: (0.0, 1_000_000_000.0), 101: (1_000_000_000.0, 0.0)}
    bars_mod[-1].delta = 1_000_000_000.0

    # Chạy apply_relative_imbalance_pct
    screen_187.apply_relative_imbalance_pct(bars_orig)
    screen_187.apply_relative_imbalance_pct(bars_mod)

    # Nến 0 của phiên hiện tại phải có kết quả imbalance giống hệt nhau
    b0_orig = bars_orig[-2]
    b0_mod = bars_mod[-2]
    assert b0_orig.ask_k_min == 101
    assert b0_mod.ask_k_min == b0_orig.ask_k_min

    # Tương tự với E2:
    e2_orig = screen_187.detect_e2_events_pct(bars_orig)
    e2_mod = screen_187.detect_e2_events_pct(bars_mod)
    # Nến 0 đều tạo sự kiện E2 ở cả 2 tập
    e2_orig_b0 = [e for e in e2_orig if e.session_id == s_date_eval and e.bar_idx == 0]
    e2_mod_b0 = [e for e in e2_mod if e.session_id == s_date_eval and e.bar_idx == 0]
    assert len(e2_orig_b0) == 1
    assert len(e2_mod_b0) == 1
    assert e2_mod_b0[0].direction == e2_orig_b0[0].direction


# --- Test 5: 5 phiên khởi động: không có imbalance, không có E2 ---
def test_5_warmup_sessions_no_imbalance_no_e2():
    """5 phiên khởi động: không có imbalance (None), không có sự kiện E2."""
    sessions = [date(2026, 4, 1) + timedelta(days=i) for i in range(7)]
    base_dt = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)
    bars: list[CryptoBarSummary] = []

    for s_idx, s_date in enumerate(sessions):
        for b_idx in range(4):
            bars.append(
                CryptoBarSummary(
                    session_id=s_date,
                    block_id="morning",
                    bar_idx=b_idx,
                    t_start=base_dt + timedelta(days=s_idx, minutes=b_idx * 5),
                    t_end=base_dt + timedelta(days=s_idx, minutes=(b_idx + 1) * 5),
                    open=1805.0 if b_idx % 2 == 0 else 1800.0,
                    high=1810.0,
                    low=1790.0,
                    close=1800.0 if b_idx % 2 == 0 else 1805.0,
                    close_k=18000,
                    delta=500.0 if b_idx % 2 == 0 else -500.0,
                    cvd=100.0,
                    ask_k_min=None,
                    ask_k_max=None,
                    bid_k_min=None,
                    bid_k_max=None,
                    fp={100: (0.0, 10.0), 101: (2000.0, 0.0)},
                )
            )

    screen_187.apply_relative_imbalance_pct(bars)
    events = screen_187.detect_e2_events_pct(bars)

    warmup_sids = set(sessions[:5])

    # 5 phiên đầu không có imbalance
    for b in bars:
        if b.session_id in warmup_sids:
            assert b.ask_k_min is None
            assert b.ask_k_max is None
            assert b.bid_k_min is None
            assert b.bid_k_max is None

    # 5 phiên đầu không có E2
    for e in events:
        assert e.session_id not in warmup_sids

    # Từ phiên 6 trở đi có sự kiện
    post_warmup_events = [e for e in events if e.session_id not in warmup_sids]
    assert len(post_warmup_events) > 0


# --- Test 6: both_sides_share ---
def test_6_both_sides_share():
    """both_sides_share: bộ nến dựng tay 3/4 nến có cả hai phía => 0.75;
    bỏ phiên khởi động thì mẫu số đúng.
    """
    s_warmup = date(2026, 4, 1)
    s_main = date(2026, 4, 2)
    base_dt = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)

    bars: list[CryptoBarSummary] = []

    # Phiên khởi động: 2 nến
    for i in range(2):
        bars.append(
            CryptoBarSummary(
                session_id=s_warmup,
                block_id="morning",
                bar_idx=i,
                t_start=base_dt + timedelta(minutes=i * 5),
                t_end=base_dt + timedelta(minutes=(i + 1) * 5),
                open=1800.0,
                high=1805.0,
                low=1795.0,
                close=1802.0,
                close_k=18020,
                delta=10.0,
                cvd=10.0,
                ask_k_min=100 if i == 0 else None,
                ask_k_max=100 if i == 0 else None,
                bid_k_min=90 if i == 0 else None,
                bid_k_max=90 if i == 0 else None,
                fp=None,
            )
        )

    # Phiên chính: 4 nến, 3 nến có cả 2 phía, 1 nến chỉ có ask
    for i in range(4):
        has_both = i < 3
        bars.append(
            CryptoBarSummary(
                session_id=s_main,
                block_id="morning",
                bar_idx=i,
                t_start=base_dt + timedelta(days=1, minutes=i * 5),
                t_end=base_dt + timedelta(days=1, minutes=(i + 1) * 5),
                open=1800.0,
                high=1805.0,
                low=1795.0,
                close=1802.0,
                close_k=18020,
                delta=10.0,
                cvd=10.0,
                ask_k_min=100,
                ask_k_max=100,
                bid_k_min=90 if has_both else None,
                bid_k_max=90 if has_both else None,
                fp=None,
            )
        )

    # Bỏ phiên khởi động: 3 / 4 = 0.75
    share_skip = screen_187.both_sides_share(bars, skip_sessions=[s_warmup])
    assert share_skip == pytest.approx(0.75)

    # Không bỏ phiên khởi động: tổng 6 nến có giá, 4 nến có cả 2 phía => 4/6
    share_no_skip = screen_187.both_sides_share(bars, skip_sessions=[])
    assert share_no_skip == pytest.approx(4.0 / 6.0)
    assert share_no_skip != 0.75


# --- Test 7: Chặn suy biến: tỷ lệ cả 2 phía > 50% => loại E3 ---
def test_7_degenerate_gate_excludes_e3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """Chặn suy biến: dữ liệu giả có tỷ lệ cả hai phía > 50% =>
    bảng CHÍNH không có dòng E3, ngưỡng in ra vẫn là 0.05/4.
    """
    main_dates = [date(2026, 3, 25) + timedelta(days=i) for i in range(41)]
    repeat_dates = [date(2026, 7, 1) + timedelta(days=i) for i in range(31)]

    for d in main_dates:
        sym = front_month_symbol(d)
        p_dir = tmp_path / sym
        p_dir.mkdir(parents=True, exist_ok=True)
        fpath = p_dir / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1800.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    for d in repeat_dates:
        sym = front_month_symbol(d)
        p_dir = tmp_path / sym
        p_dir.mkdir(parents=True, exist_ok=True)
        fpath = p_dir / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1850.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    # Giả lập both_sides_share > 50% (ví dụ 60%)
    monkeypatch.setattr(screen_187, "both_sides_share", lambda *args, **kwargs: 0.60)

    res = screen_187.run_187(data_dir=tmp_path)
    assert res["exit_code"] == 0
    assert res["exclude_e3"] is True

    # Bảng CHÍNH chỉ có E2, KHÔNG có E3
    assert "E3_H15" not in res["results_main"]
    assert "E3_H30" not in res["results_main"]
    assert "E2_H15" in res["results_main"]
    assert "E2_H30" in res["results_main"]

    captured = capsys.readouterr()
    assert "E3_H15" not in captured.out
    assert "E3_H30" not in captured.out
    assert "E2_H15" in captured.out
    assert "E2_H30" in captured.out
    # Ngưỡng alpha in ra vẫn là 0.05 / 4 = 0.0125
    assert "0.0125" in captured.out or "0.05 / 4" in captured.out


# --- Test 8: Ngưỡng CHÍNH 0.05/4: p = 0.02 đủ mẫu và hurdle => TRƯỢT ---
def test_8_main_alpha_bonferroni():
    """Ngưỡng CHÍNH là 0.05/4: một cặp giả có p = 0.02, đủ mẫu và đủ hurdle => TRƯỢT.
    Với p = 0.010 thì ĐẠT.
    """
    assert screen_187.ALPHA_MAIN == pytest.approx(0.05 / 4.0)

    # Tạo 120 sự kiện (60 Mua, 60 Bán) đều có y = 5.0 (vượt hurdle 2.0)
    ev_buy = OrderFlowEvent(
        event_type="E2",
        direction=1,
        session_id=date(2026, 4, 1),
        block_id="morning",
        bar_idx=10,
        t_end=datetime(2026, 4, 1, 9, 50, tzinfo=TZ),
        close=1800.0,
        exit_price=1805.0,
        y=5.0,
    )
    ev_sell = OrderFlowEvent(
        event_type="E2",
        direction=-1,
        session_id=date(2026, 4, 1),
        block_id="morning",
        bar_idx=11,
        t_end=datetime(2026, 4, 1, 9, 55, tzinfo=TZ),
        close=1805.0,
        exit_price=1800.0,
        y=5.0,
    )
    events = [ev_buy] * 60 + [ev_sell] * 60

    # p = 0.02: 0.02 > 0.0125 (0.05/4) => TRƯỢT
    res_p02 = evaluate_pair_criteria(
        events,
        hurdle=2.0,
        control_rho=0.5,
        p_val=0.02,
        alpha_threshold=screen_187.ALPHA_MAIN,
    )
    assert not res_p02["cond2_stat"]
    assert not res_p02["passed"]

    # p = 0.010: 0.010 < 0.0125 => ĐẠT
    res_p01 = evaluate_pair_criteria(
        events,
        hurdle=2.0,
        control_rho=0.5,
        p_val=0.010,
        alpha_threshold=screen_187.ALPHA_MAIN,
    )
    assert res_p01["cond2_stat"]
    assert res_p01["passed"]


# --- Test 9: Đầu-cuối: 4 cặp E2/E3, không có E1, bảo vệ niêm phong ---
def test_9_end_to_end_and_is_start_date_shield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """Đầu-cuối: phiên giả CHÍNH + LẶP LẠI => main() trả 0,
    in đủ 4 cặp E2/E3 và KHÔNG CÓ dòng E1.
    Spy gzip.open cho thấy không mở file ngày >= 2026-09-25.
    """
    main_dates = [date(2026, 3, 25) + timedelta(days=i) for i in range(41)]
    repeat_dates = [date(2026, 7, 1) + timedelta(days=i) for i in range(31)]

    for d in main_dates:
        sym = front_month_symbol(d)
        p_dir = tmp_path / sym
        p_dir.mkdir(parents=True, exist_ok=True)
        fpath = p_dir / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1800.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    for d in repeat_dates:
        sym = front_month_symbol(d)
        p_dir = tmp_path / sym
        p_dir.mkdir(parents=True, exist_ok=True)
        fpath = p_dir / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1850.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    # 1 file ngày 2026-09-25 cố ý hỏng để kiểm tra niêm phong
    d_is = IS_START_DATE
    sym_is = front_month_symbol(d_is)
    dir_is = tmp_path / sym_is
    dir_is.mkdir(parents=True, exist_ok=True)
    f_is = dir_is / f"{d_is.isoformat()}.jsonl.gz"
    with open(f_is, "wb") as f:
        f.write(b"CORRUPTED_NOT_VALID_GZIP_FILE")

    # Spy hàm gzip.open
    real_gzip_open = gzip.open
    opened_files: list[str] = []

    def spy_gzip_open(filename: Any, *args: Any, **kwargs: Any) -> Any:
        opened_files.append(str(filename))
        return real_gzip_open(filename, *args, **kwargs)

    monkeypatch.setattr(gzip, "open", spy_gzip_open)

    # Chạy main
    ret = screen_187.main(["--data-dir", str(tmp_path)])
    assert ret == 0

    # Gọi trực tiếp loader với end=2026-09-25 để kiểm tra quy tắc niêm phong
    screen_187.load_dnse_sessions(data_dir=str(tmp_path), start=date(2026, 9, 20), end=date(2026, 9, 25))

    # Spy: file 2026-09-25 KHÔNG bao giờ bị mở
    for path_str in opened_files:
        assert "2026-09-25" not in path_str

    captured = capsys.readouterr()
    # In đủ 4 cặp E2/E3
    for pair in ("E2_H15", "E2_H30", "E3_H15", "E3_H30"):
        assert pair in captured.out

    # Tuyệt đối không có dòng E1
    assert "E1_H15" not in captured.out
    assert "E1_H30" not in captured.out


# --- Test 10: Dùng lại hàm không sửa ---
def test_10_reuses_unmodified_functions():
    """Tái sử dụng: mod.load_dnse_sessions is screen_vn30f_orderflow_dnse.load_dnse_sessions,
    tương tự cho evaluate_repeat_pair, detect_e3_events, evaluate_pair_criteria.
    """
    assert screen_187.load_dnse_sessions is screen_dnse.load_dnse_sessions
    assert screen_187.evaluate_repeat_pair is screen_dnse.evaluate_repeat_pair
    assert screen_187.detect_e3_events is screen_182.detect_e3_events
    assert screen_187.evaluate_pair_criteria is screen_182.evaluate_pair_criteria
    assert screen_187.imbalance_levels is screen_182.imbalance_levels
    assert screen_187.calculate_percentile is screen_182.calculate_percentile
# --- Test audit (Claude): pool E2 chỉ từ 5 phiên trước; ratio imbalance đúng 3,0 ---
def _bar_187(
    s_date: date, b_idx: int, delta: float, open_: float, close: float, fp: dict
) -> CryptoBarSummary:
    t0 = datetime(s_date.year, s_date.month, s_date.day, 9, 0, tzinfo=TZ) + timedelta(
        minutes=5 * b_idx
    )
    return CryptoBarSummary(
        session_id=s_date,
        block_id="morning",
        bar_idx=b_idx,
        t_start=t0,
        t_end=t0 + timedelta(minutes=5),
        open=open_,
        high=max(open_, close) + 1.0,
        low=min(open_, close) - 1.0,
        close=close,
        close_k=round(close * 10),
        delta=delta,
        cvd=delta,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
        fp=fp,
    )


def test_4c_e2_pool_chi_tu_5_phien_truoc():
    """|delta| pool 5 phiên trước = 1..10 (p90 ~ 9,1); nến mục tiêu delta 9,5 lệch dấu thân nến => có E2.
    Thêm 3 nến |delta| 1e9 ở phiên hiện tại: nếu pool gồm phiên hiện tại thì p90 vọt lên và E2 mất.
    """
    days = [date(2026, 4, 1) + timedelta(days=i) for i in range(6)]
    bars: list[CryptoBarSummary] = []
    v = 1.0
    for d in days[:5]:
        for b_idx in range(2):
            bars.append(_bar_187(d, b_idx, v, 1800.0, 1801.0, {}))
            v += 1.0
    bars.append(_bar_187(days[5], 0, 9.5, 1801.0, 1800.0, {}))
    for b_idx in range(1, 4):
        bars.append(_bar_187(days[5], b_idx, 1e9, 1800.0, 1801.0, {}))

    events = screen_187.detect_e2_events_pct(bars, 90.0)
    assert [(e.session_id, e.bar_idx, e.direction) for e in events] == [
        (days[5], 0, +1)
    ]


def test_2c_ratio_imbalance_dung_3():
    """Pool 5 phiên trước toàn 10 => min_vol = denom_floor = 10. Nến mục tiêu buy 25 ở k=101, sell 10 ở k=100:
    25 < 3 x 10 => KHÔNG có ask imbalance (ratio 2 sẽ thành có); buy 30 => có."""
    days = [date(2026, 4, 1) + timedelta(days=i) for i in range(6)]
    bars = [
        _bar_187(d, 0, 0.0, 1800.0, 1801.0, {100: (0.0, 10.0), 101: (10.0, 0.0)})
        for d in days[:5]
    ]
    target = _bar_187(
        days[5], 0, 15.0, 1800.0, 1801.0, {100: (0.0, 10.0), 101: (25.0, 0.0)}
    )
    bars.append(target)
    screen_187.apply_relative_imbalance_pct(bars, 95.0, 50.0)
    assert target.ask_k_min is None

    target.fp = {100: (0.0, 10.0), 101: (30.0, 0.0)}
    screen_187.apply_relative_imbalance_pct(bars, 95.0, 50.0)
    assert target.ask_k_min == 101
