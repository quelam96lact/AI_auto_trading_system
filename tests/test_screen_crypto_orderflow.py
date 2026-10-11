"""Tests cho scripts/screen_crypto_orderflow.py (Brief dot 183b - Ca 4 den 9, 13 den 16)."""

import gzip
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

import scripts.screen_vn30f_orderflow as vn30f
from scripts.screen_crypto_orderflow import (
    ECONOMIC_HURDLE,
    BarSummary,
    CryptoBarSummary,
    OrderFlowEvent,
    apply_relative_imbalance,
    build_crypto_price_lookup,
    crypto_block_end_fn,
    detect_e1_events,
    detect_e2_events,
    detect_e3_events,
    evaluate_crypto_pair,
    get_crypto_block_id,
    imbalance_levels,
    load_crypto_footprint_bars,
    main,
    parse_fp_string,
    run_crypto_screening_pipeline,
)


def test_4_khung_funding_va_cvd_reset(tmp_path):
    """Ca 4: Khung funding 8h, cat su kien vuot khung, E3 khong vat qua funding, CVD reset luc 00:00 UTC."""
    d = date(2023, 1, 1)
    # Event 1: t_end = 07:50 UTC, H = 15 => target_time = 08:05 UTC > 08:00 (block_end) => BI LOAI
    t_0750 = datetime(2023, 1, 1, 7, 50, 0, tzinfo=UTC)
    e1 = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=94,
        t_end=t_0750,
        close=60000.0,
    )

    # Event 2: t_end = 07:45 UTC, H = 15 => target_time = 08:00 UTC == 08:00 (block_end) => DUOC GIU
    t_0745 = datetime(2023, 1, 1, 7, 45, 0, tzinfo=UTC)
    e2 = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=93,
        t_end=t_0745,
        close=60000.0,
    )

    bar_0755 = BarSummary(
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=95,
        t_start=datetime(2023, 1, 1, 7, 55, 0, tzinfo=UTC),
        t_end=datetime(2023, 1, 1, 8, 0, 0, tzinfo=UTC),
        open=60050.0,
        high=60120.0,
        low=60040.0,
        close=60100.0,
        close_k=10016,
        delta=10.0,
        cvd=10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    price_lookup = build_crypto_price_lookup([bar_0755])

    res = evaluate_crypto_pair(
        events=[e1, e2],
        price_lookup=price_lookup,
        h_minutes=15,
        alpha_threshold=0.05,
        block_end_fn=crypto_block_end_fn,
    )

    assert res["n_events"] == 1
    assert res["mean_y"] == pytest.approx(60100.0 / 60000.0 - 1.0, rel=1e-6)

    # 2. E3 khong vat qua moc funding 08:00 UTC
    bar_prev = BarSummary(
        session_id=d,
        block_id=get_crypto_block_id(datetime(2023, 1, 1, 7, 55, tzinfo=UTC)),
        bar_idx=95,
        t_start=datetime(2023, 1, 1, 7, 55, tzinfo=UTC),
        t_end=datetime(2023, 1, 1, 8, 0, tzinfo=UTC),
        open=60000.0,
        high=60050.0,
        low=59950.0,
        close=60020.0,
        close_k=10003,
        delta=-10.0,
        cvd=-10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=9995,
        bid_k_max=9999,
    )
    bar_curr = BarSummary(
        session_id=d,
        block_id=get_crypto_block_id(datetime(2023, 1, 1, 8, 0, tzinfo=UTC)),
        bar_idx=96,
        t_start=datetime(2023, 1, 1, 8, 0, tzinfo=UTC),
        t_end=datetime(2023, 1, 1, 8, 5, tzinfo=UTC),
        open=60020.0,
        high=60100.0,
        low=60010.0,
        close=60080.0,
        close_k=10013,
        delta=20.0,
        cvd=10.0,
        ask_k_min=10005,
        ask_k_max=10010,
        bid_k_min=None,
        bid_k_max=None,
    )
    e3_events = detect_e3_events([bar_prev, bar_curr])
    assert len(e3_events) == 0

    # 3. CVD reset luc 00:00 UTC moi ngay tren file v2
    f_path = tmp_path / "2023-01.csv.gz"
    with gzip.open(f_path, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,fp\n")
        gf.write("2023-01-01T23:55:00Z,60000.0,60010.0,59990.0,60005.0,10.0,5.0,5.0,20,6.0,10000,10000:600000:0\n")
        gf.write("2023-01-02T00:00:00Z,60005.0,60020.0,60000.0,60010.0,8.0,6.0,2.0,15,6.0,10001,10001:480000:0\n")

    loaded_bars = load_crypto_footprint_bars(data_dir=tmp_path)
    assert len(loaded_bars) == 2
    assert loaded_bars[0].delta == 5.0
    assert loaded_bars[0].cvd == 5.0
    assert loaded_bars[1].delta == 2.0
    assert loaded_bars[1].cvd == 2.0


def test_5_tai_dung_dung_doi_tuong_ham_182():
    """Ca 5: screen_crypto_orderflow dung dung doi tuong ham cua 182 (is) cho E1, E2, E3, imbalance."""
    assert detect_e1_events is vn30f.detect_e1_events
    assert detect_e2_events is vn30f.detect_e2_events
    assert detect_e3_events is vn30f.detect_e3_events
    assert imbalance_levels is vn30f.imbalance_levels


def test_6_muc_tieu_va_hurdle():
    """Ca 6: Bien muc tieu y dung dau va tinh theo ty le; hurdle dung 0.0021."""
    d = date(2023, 1, 1)
    e_buy = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=10,
        t_end=datetime(2023, 1, 1, 1, 0, 0, tzinfo=UTC),
        close=50000.0,
    )
    e_sell = OrderFlowEvent(
        event_type="E1",
        direction=-1,
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=20,
        t_end=datetime(2023, 1, 1, 2, 0, 0, tzinfo=UTC),
        close=50000.0,
    )

    bar_exit_buy = BarSummary(
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=13,
        t_start=datetime(2023, 1, 1, 1, 10, 0, tzinfo=UTC),
        t_end=datetime(2023, 1, 1, 1, 15, 0, tzinfo=UTC),
        open=50100.0,
        high=50250.0,
        low=50050.0,
        close=50200.0,
        close_k=10040,
        delta=1.0,
        cvd=1.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    bar_exit_sell = BarSummary(
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=23,
        t_start=datetime(2023, 1, 1, 2, 10, 0, tzinfo=UTC),
        t_end=datetime(2023, 1, 1, 2, 15, 0, tzinfo=UTC),
        open=49900.0,
        high=49950.0,
        low=49750.0,
        close=49800.0,
        close_k=9960,
        delta=1.0,
        cvd=1.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    lookup = build_crypto_price_lookup([bar_exit_buy, bar_exit_sell])

    res = evaluate_crypto_pair([e_buy, e_sell], lookup, h_minutes=15, alpha_threshold=0.05)
    assert res["n_events"] == 2
    assert res["mean_y"] == pytest.approx(0.0040, abs=1e-6)
    assert abs(ECONOMIC_HURDLE - 0.0021) < 1e-12


def test_7_cong_ngay_chong_nhin_truoc():
    """Ca 7: Cong ngay tu choi truoc 2026-11-01 (tra ve 2, khong mo file); tu 2026-11-01 di tiep."""
    with patch("scripts.screen_crypto_orderflow.run_crypto_screening_pipeline") as mock_pipe:
        ret_block = main(args=[], today=date(2026, 10, 31))
        assert ret_block == 2
        mock_pipe.assert_not_called()

    with patch("scripts.screen_crypto_orderflow.run_crypto_screening_pipeline") as mock_pipe:
        mock_pipe.return_value = {
            "status": "CONTROL_FAILED",
            "ctrl_rho": 0.1,
            "message": "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN",
            "pairs": {},
        }
        ret_pass = main(args=[], today=date(2026, 11, 1))
        mock_pipe.assert_called_once()
        assert ret_pass == 4


def test_8_phan_quyet_va_control_rho():
    """Ca 8: Cap dat CHINH nhung LAP LAI < hurdle => khong DAT; nguong p o LAP LAI la 0.05/k; rho = 0.3 => dung."""
    bars = []
    d = date(2023, 1, 1)
    for i in range(50):
        bars.append(
            CryptoBarSummary(
                session_id=d,
                block_id="2023-01-01_00_08",
                bar_idx=i,
                t_start=datetime(2023, 1, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=5 * i),
                t_end=datetime(2023, 1, 1, 0, 5, tzinfo=UTC) + timedelta(minutes=5 * i),
                open=60000.0,
                high=60010.0,
                low=59990.0,
                close=60000.0,
                close_k=10000,
                delta=float(i),
                cvd=float(i),
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
                fp={},
            )
        )

    # 1. Kiem tra control rho dung bang 0.3 => BI LOAI
    with (
        patch("scripts.screen_crypto_orderflow.load_crypto_footprint_bars", return_value=bars),
        patch("scripts.screen_crypto_orderflow.check_control_variable_crypto", return_value=0.30),
    ):
        res_ctrl = run_crypto_screening_pipeline(data_dir="dummy")
        assert res_ctrl["status"] == "CONTROL_FAILED"
        assert "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN" in res_ctrl["message"]

    # 2. Cap dat o CHINH nhung LAP LAI mean_y < hurdle => final_passed = False
    with (
        patch("scripts.screen_crypto_orderflow.load_crypto_footprint_bars", return_value=bars),
        patch("scripts.screen_crypto_orderflow.check_control_variable_crypto", return_value=0.45),
        patch("scripts.screen_crypto_orderflow.detect_e1_events", return_value=[]),
        patch("scripts.screen_crypto_orderflow.detect_e2_events", return_value=[]),
        patch("scripts.screen_crypto_orderflow.detect_e3_events", return_value=[]),
    ):
        call_counter = {"n": 0}

        def mock_eval(events, price_lookup, h_minutes, alpha_threshold, hurdle, block_end_fn):
            call_counter["n"] += 1
            if call_counter["n"] <= 6:
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0030,
                    "p_val": 0.001,
                    "passed": True,
                }
            else:
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0015,
                    "p_val": 0.002,
                    "passed": False,
                }

        with patch("scripts.screen_crypto_orderflow.evaluate_crypto_pair", side_effect=mock_eval):
            res = run_crypto_screening_pipeline(data_dir="dummy")
            assert res["k_main_passed"] == 6
            assert res["repeat_alpha"] == pytest.approx(0.05 / 6.0, rel=1e-6)
            for pair_info in res["pairs"].values():
                assert pair_info["final_passed"] is False

    # 3. Kiem tra neu co 2 cap dat CHINH => repeat_alpha = 0.05 / 2 = 0.025
    with (
        patch("scripts.screen_crypto_orderflow.load_crypto_footprint_bars", return_value=bars),
        patch("scripts.screen_crypto_orderflow.check_control_variable_crypto", return_value=0.45),
        patch("scripts.screen_crypto_orderflow.detect_e1_events", return_value=[]),
        patch("scripts.screen_crypto_orderflow.detect_e2_events", return_value=[]),
        patch("scripts.screen_crypto_orderflow.detect_e3_events", return_value=[]),
    ):
        call_count = {"val": 0}

        def mock_eval_2_pairs(events, price_lookup, h_minutes, alpha_threshold, hurdle, block_end_fn):
            if alpha_threshold == 0.05 / 6.0:
                call_count["val"] += 1
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0030,
                    "p_val": 0.001,
                    "passed": (call_count["val"] <= 2),
                }
            else:
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0025,
                    "p_val": 0.01,
                    "passed": True,
                }

        with patch("scripts.screen_crypto_orderflow.evaluate_crypto_pair", side_effect=mock_eval_2_pairs):
            res2 = run_crypto_screening_pipeline(data_dir="dummy")
            assert res2["k_main_passed"] == 2
            assert res2["repeat_alpha"] == pytest.approx(0.05 / 2.0, rel=1e-6)


def test_9_bootstrap_theo_khoi_ngay_utc():
    """Ca 9: Bootstrap theo khoi ngay UTC (bay hai khoi nhu ca 11 cua 182)."""
    d1 = date(2023, 1, 1)
    d2 = date(2023, 1, 2)
    evs: list[OrderFlowEvent] = []

    for i in range(50):
        evs.append(
            OrderFlowEvent(
                event_type="E1",
                direction=1,
                session_id=d1,
                block_id="2023-01-01_00_08",
                bar_idx=i,
                t_end=datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
                close=60000.0,
                y=0.0100,
            )
        )
    for i in range(50):
        evs.append(
            OrderFlowEvent(
                event_type="E1",
                direction=1,
                session_id=d2,
                block_id="2023-01-02_00_08",
                bar_idx=i,
                t_end=datetime(2023, 1, 2, 1, 0, tzinfo=UTC),
                close=60000.0,
                y=-0.0100,
            )
        )

    p_val, _ = vn30f.block_bootstrap_p_value(evs, n_bootstrap=2000, seed=42)
    assert 0.70 <= p_val <= 0.80


def test_13_nguong_tuong_doi_khong_nhin_truoc():
    """Ca 13: Nguong tuong doi khong nhin truoc: ngay 6 co muc khong lo nhung nguong chi tinh tu ngay 1-5."""
    bars: list[CryptoBarSummary] = []
    # Dựng 6 ngày (1 nến mỗi ngày)
    for day in range(1, 6):
        d = date(2023, 1, day)
        bars.append(
            CryptoBarSummary(
                session_id=d,
                block_id=f"2023-01-{day:02d}_00_08",
                bar_idx=0,
                t_start=datetime(2023, 1, day, 0, 0, tzinfo=UTC),
                t_end=datetime(2023, 1, day, 0, 5, tzinfo=UTC),
                open=60000.0,
                high=60010.0,
                low=59990.0,
                close=60000.0,
                close_k=10000,
                delta=0.0,
                cvd=0.0,
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
                # Mỗi ngày 2 mức: 50.000 và 100.000 USDT
                fp={10000: (50000.0, 50000.0), 10001: (100000.0, 100000.0)},
            )
        )

    # Ngày 6: có mức khổng lồ 50.000.000 USDT
    d6 = date(2023, 1, 6)
    bar6 = CryptoBarSummary(
        session_id=d6,
        block_id="2023-01-06_00_08",
        bar_idx=0,
        t_start=datetime(2023, 1, 6, 0, 0, tzinfo=UTC),
        t_end=datetime(2023, 1, 6, 0, 5, tzinfo=UTC),
        open=60000.0,
        high=60010.0,
        low=59990.0,
        close=60000.0,
        close_k=10000,
        delta=0.0,
        cvd=0.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
        fp={10000: (50000000.0, 50000000.0), 10001: (50000000.0, 50000000.0)},
    )
    bars.append(bar6)

    # Áp ngưỡng
    apply_relative_imbalance(bars)

    # 1. Ngày 1-5 không có imbalance (None)
    for b in bars[:5]:
        assert b.ask_k_min is None
        assert b.bid_k_min is None
        assert b.min_vol is None
        assert b.denom_floor is None

    # 2. Ngưỡng ngày 6 chỉ tính từ ngày 1-5
    # Pool ngày 1-5 có các giá trị: 50k, 50k, 100k, 100k mỗi ngày -> 20 giá trị [50k..100k]
    # p90 = 100k, p50 = 75k (hoặc quanh đó), KHÔNG THỂ là 50 triệu!
    pool_1_to_5 = [50000.0, 50000.0, 100000.0, 100000.0] * 5
    expected_min_vol = vn30f.calculate_percentile(pool_1_to_5, 90.0)
    expected_denom_floor = vn30f.calculate_percentile(pool_1_to_5, 50.0)
    assert bar6.min_vol == expected_min_vol
    assert bar6.denom_floor == expected_denom_floor
    assert bar6.ask_k_min == 10000

    # 3. Nếu thay đổi giá trị của ngày 6 từ 50M thành 500M, ngưỡng của ngày 6 không đổi
    bar6.fp = {10000: (500000000.0, 500000000.0), 10001: (500000000.0, 500000000.0)}
    apply_relative_imbalance(bars)
    assert bar6.min_vol == expected_min_vol
    assert bar6.denom_floor == expected_denom_floor
    assert bar6.ask_k_min == 10000


def test_14_ap_nguong_imbalance():
    """Ca 14: Ap nguong imbalance voi pool biet truoc (p90 = 100k, p50 = 20k)."""
    # Xay dung footprint cho 1 nen:
    # Muc 1000: buy 90.000, sell[k-1] 0 -> buy < p90 (100k) => KHONG phai imbalance
    # Muc 1002: buy 120.000, sell[1001] 0 -> mau so cham san 20k, 120k >= 3 * 20k = 60k va >= 100k => LA ask imbalance
    # Muc 1004: buy 150.000, sell[1003] 60.000 -> mau so 60k, 150k < 3 * 60k = 180k => KHONG phai ask imbalance
    fp_test = {
        1000: (90000.0, 0.0),
        1001: (0.0, 0.0),
        1002: (120000.0, 0.0),
        1003: (0.0, 60000.0),
        1004: (150000.0, 0.0),
    }

    ask_ks, bid_ks = imbalance_levels(
        fp=fp_test,
        ratio=3.0,
        min_vol=100000.0,
        denom_floor=20000.0,
    )
    # Chi co duy nhat muc 1002 dat ask imbalance!
    assert ask_ks == [1002]
    assert bid_ks == []


def test_15_chuoi_fp_ghi_doc_va_file_v1(tmp_path):
    """Ca 15: Chuoi fp ghi roi doc lai cho ra dung dict; nen trong fp rong; file v1 nem ValueError co chu 'v1'."""
    # 1. Parse chuoi fp
    s = "10001:250000:0|10002:1200000:300000"
    d = parse_fp_string(s)
    assert d == {10001: (250000.0, 0.0), 10002: (1200000.0, 300000.0)}

    # Chuoi rong => {}
    assert parse_fp_string("") == {}

    # 2. File v1 (khong co cot 'fp') => nem ValueError co chu 'v1'
    f_v1 = tmp_path / "2023-01.csv.gz"
    with gzip.open(f_v1, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,ask_k_min,ask_k_max,bid_k_min,bid_k_max\n")
        gf.write("2023-01-01T00:00:00Z,60000.0,60010.0,59990.0,60005.0,10.0,5.0,5.0,20,12.0,5000,,,,\n")

    with pytest.raises(ValueError, match="v1"):
        load_crypto_footprint_bars(data_dir=tmp_path)


def test_16_quy_tac_suy_bien_e3():
    """Ca 16: Quy tac suy bien: > 50% nen 'ca hai' => E3 bi LOAI, khong goi eval E3; <= 50% => E3 duoc giu."""
    d = date(2023, 1, 1)

    # Sub-case A: 51% nen 'ca hai' (51 nen both, 49 nen neither)
    bars_51: list[CryptoBarSummary] = []
    for i in range(100):
        is_both = (i < 51)
        bars_51.append(
            CryptoBarSummary(
                session_id=d,
                block_id="2023-01-01_00_08",
                bar_idx=i,
                t_start=datetime(2023, 1, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=5 * i),
                t_end=datetime(2023, 1, 1, 0, 5, tzinfo=UTC) + timedelta(minutes=5 * i),
                open=60000.0,
                high=60010.0,
                low=59990.0,
                close=60000.0,
                close_k=10000,
                delta=float(i),
                cvd=float(i),
                ask_k_min=10001 if is_both else None,
                ask_k_max=10005 if is_both else None,
                bid_k_min=9990 if is_both else None,
                bid_k_max=9995 if is_both else None,
                fp={},
            )
        )

    with (
        patch("scripts.screen_crypto_orderflow.load_crypto_footprint_bars", return_value=bars_51),
        patch("scripts.screen_crypto_orderflow.apply_relative_imbalance", side_effect=lambda b: b),
        patch("scripts.screen_crypto_orderflow.check_control_variable_crypto", return_value=0.50),
        patch("scripts.screen_crypto_orderflow.detect_e3_events") as mock_e3,
    ):
        res_51 = run_crypto_screening_pipeline(data_dir="dummy")
        assert res_51["e3_degenerate"] is True
        mock_e3.assert_not_called()
        # Bonferroni o CHINH van giu 0.05/6
        assert res_51["repeat_alpha"] == 0.05  # Vi khong co cap nao dat CHINH
        assert res_51["pairs"]["E3_15m"]["degenerate"] is True
        assert res_51["pairs"]["E3_30m"]["degenerate"] is True

    # Sub-case B: 50% dung bang nen 'ca hai' => E3 DUOC GIU
    bars_50: list[CryptoBarSummary] = []
    for i in range(100):
        is_both = (i < 50)
        bars_50.append(
            CryptoBarSummary(
                session_id=d,
                block_id="2023-01-01_00_08",
                bar_idx=i,
                t_start=datetime(2023, 1, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=5 * i),
                t_end=datetime(2023, 1, 1, 0, 5, tzinfo=UTC) + timedelta(minutes=5 * i),
                open=60000.0,
                high=60010.0,
                low=59990.0,
                close=60000.0,
                close_k=10000,
                delta=float(i),
                cvd=float(i),
                ask_k_min=10001 if is_both else None,
                ask_k_max=10005 if is_both else None,
                bid_k_min=9990 if is_both else None,
                bid_k_max=9995 if is_both else None,
                fp={},
            )
        )

    with (
        patch("scripts.screen_crypto_orderflow.load_crypto_footprint_bars", return_value=bars_50),
        patch("scripts.screen_crypto_orderflow.apply_relative_imbalance", side_effect=lambda b: b),
        patch("scripts.screen_crypto_orderflow.check_control_variable_crypto", return_value=0.50),
        patch("scripts.screen_crypto_orderflow.detect_e3_events", return_value=[]) as mock_e3_50,
    ):
        res_50 = run_crypto_screening_pipeline(data_dir="dummy")
        assert res_50["e3_degenerate"] is False
        mock_e3_50.assert_called_once()
V2_HEADER = "ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,fp\n"


def test_10_nen_cuoi_khung_khong_vat_qua_funding():
    """Claude audit 183: nen 07:55 (t_end 08:00) thuoc khung 00-08, het khung la 08:00 chu khong phai 16:00."""
    ev_0755 = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=date(2023, 1, 1),
        block_id="2023-01-01_00_08",
        bar_idx=95,
        t_end=datetime(2023, 1, 1, 8, 0, tzinfo=UTC),
        close=60000.0,
    )
    ev_2355 = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=date(2023, 1, 1),
        block_id="2023-01-01_16_24",
        bar_idx=287,
        t_end=datetime(2023, 1, 2, 0, 0, tzinfo=UTC),
        close=60000.0,
    )
    assert crypto_block_end_fn(ev_0755) == datetime(2023, 1, 1, 8, 0, tzinfo=UTC)
    assert crypto_block_end_fn(ev_2355) == datetime(2023, 1, 2, 0, 0, tzinfo=UTC)

    exit_bars = []
    for dt in (
        datetime(2023, 1, 1, 8, 10, tzinfo=UTC),
        datetime(2023, 1, 2, 0, 10, tzinfo=UTC),
    ):
        exit_bars.append(
            BarSummary(
                session_id=dt.date(),
                block_id=get_crypto_block_id(dt),
                bar_idx=0,
                t_start=dt,
                t_end=dt + timedelta(minutes=5),
                open=60500.0,
                high=60500.0,
                low=60500.0,
                close=60500.0,
                close_k=10083,
                delta=0.0,
                cvd=0.0,
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
            )
        )
    res = evaluate_crypto_pair(
        [ev_0755, ev_2355],
        build_crypto_price_lookup(exit_bars),
        h_minutes=15,
        alpha_threshold=0.05,
    )
    assert res["n_events"] == 0


def test_11_nen_trong_giu_cho_de_e3_chi_ghep_nen_lien_nhau(tmp_path):
    """Claude audit 183: nen khong giao dich giu cho (close=None) de E3 khong ghep 00:00 voi 00:10."""
    with gzip.open(tmp_path / "2023-01.csv.gz", "wt", encoding="utf-8") as gf:
        gf.write(V2_HEADER)
        gf.write(
            "2023-01-01T00:00:00Z,60000.0,60050.0,59950.0,60020.0,1.0,3.0,-2.0,10,6.0,10003,10003:1:1\n"
        )
        gf.write("2023-01-01T00:05:00Z,,,,,0.0,0.0,0.0,0,,,\n")
        gf.write(
            "2023-01-01T00:10:00Z,60020.0,60100.0,60010.0,60080.0,3.0,1.0,2.0,10,6.0,10013,10013:1:1\n"
        )

    bars = load_crypto_footprint_bars(data_dir=tmp_path)
    assert len(bars) == 3
    assert bars[1].close is None
    assert bars[2].cvd == pytest.approx(0.0)

    # 00:00 hap thu ban (close_k > bid_k_max), 00:10 khoi xuong mua (close_k >= ask_k_max, khong bid)
    bars[0].bid_k_min, bars[0].bid_k_max = 9995, 9999
    bars[2].ask_k_min, bars[2].ask_k_max = 10010, 10012
    assert detect_e3_events(bars) == []


def _write_synthetic_month_v2(
    path, year: int, month: int, n_days: int, seed: int
) -> None:
    """File v2 gia: delta cung dau voi close-open (rho doi chung cao), co fp nhieu muc, vai nen trong."""
    import random

    rng = random.Random(seed)
    price = 30000.0
    with gzip.open(path, "wt", encoding="utf-8") as gf:
        gf.write(V2_HEADER)
        for day in range(n_days):
            for i in range(288):
                dt = datetime(year, month, day + 1, tzinfo=UTC) + timedelta(
                    minutes=5 * i
                )
                ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if i == 100:
                    gf.write(f"{ts},,,,,0.0,0.0,0.0,0,,,\n")
                    continue
                o = price
                c = round(o + rng.gauss(0, 20), 1)
                delta = (c - o) * 0.5 + rng.gauss(0, 2)
                step = 3.0
                k0 = int(min(o, c) // step)
                fp = "|".join(
                    f"{k}:{int(rng.expovariate(1 / 200000))}:{int(rng.expovariate(1 / 200000))}"
                    for k in range(k0, k0 + 8)
                )
                gf.write(
                    f"{ts},{o},{max(o, c) + 5},{min(o, c) - 5},{c},{max(delta, 0) + 5},{max(-delta, 0) + 5},"
                    f"{delta:.4f},50,{step},{int(c // step)},{fp}\n"
                )
                price = c


def test_12_dau_cuoi_main_sau_cong_ngay(tmp_path, capsys):
    """Claude audit 183: main() sau cong ngay chay tron tren file v2 gia, in bang 6 cap, return 0."""
    _write_synthetic_month_v2(tmp_path / "2024-12.csv.gz", 2024, 12, 10, seed=1)
    _write_synthetic_month_v2(tmp_path / "2025-01.csv.gz", 2025, 1, 10, seed=2)
    # File ngoai cua so niem phong: hong co y, neu bi mo se no
    (tmp_path / "2026-09.csv.gz").write_bytes(b"khong phai gzip")

    ret = main(args=["--data-dir", str(tmp_path)], today=date(2026, 11, 1))
    out, _ = capsys.readouterr()
    assert ret == 0
    for pair in ("E1_15m", "E1_30m", "E2_15m", "E2_30m", "E3_15m", "E3_30m"):
        assert pair in out
    assert "E3 LOẠI" not in out
