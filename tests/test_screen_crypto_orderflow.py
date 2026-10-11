"""Tests cho scripts/screen_crypto_orderflow.py (Brief dot 183 - Ca 4 den Ca 9)."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

import scripts.screen_vn30f_orderflow as vn30f
from scripts.screen_crypto_orderflow import (
    ECONOMIC_HURDLE,
    BarSummary,
    OrderFlowEvent,
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
    run_crypto_screening_pipeline,
)


def test_4_khung_funding_va_cvd_reset(tmp_path):
    """Ca 4: Khung funding 8h, cat su kien vuot khung, E3 khong vat qua funding, CVD reset luc 00:00 UTC."""
    # 1. Kiem tra crypto_block_end_fn
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

    # Nen co giao dich luc 07:55 (ket thuc 08:00 UTC) voi close = 60100.0
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
        close_k=5008,
        delta=10.0,
        cvd=10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=None,
        bid_k_max=None,
    )
    price_lookup = build_crypto_price_lookup([bar_0755])

    # Danh gia voi H = 15m
    res = evaluate_crypto_pair(
        events=[e1, e2],
        price_lookup=price_lookup,
        h_minutes=15,
        alpha_threshold=0.05,
        block_end_fn=crypto_block_end_fn,
    )

    # e1 bi loai vi 08:05 > 08:00; e2 duoc giu va co gia exit tai 08:00 la 60100.0
    assert res["n_events"] == 1
    # y = +1 * (60100.0 / 60000.0 - 1) = 0.00166666...
    assert res["mean_y"] == pytest.approx(60100.0 / 60000.0 - 1.0, rel=1e-6)

    # 2. E3 khong vat qua moc funding 08:00 UTC
    # Nen t-1 = 07:55 (block_id 2023-01-01_00_08) co bid imbalance, close > max bid (absorbed sell)
    # Nen t = 08:00 (block_id 2023-01-01_08_16) co ask imbalance, close >= max ask (initiative buy)
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
        close_k=5001,
        delta=-10.0,
        cvd=-10.0,
        ask_k_min=None,
        ask_k_max=None,
        bid_k_min=4995,
        bid_k_max=4999,  # close_k 5001 > 4999 (hap thu ban)
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
        close_k=5006,
        delta=20.0,
        cvd=10.0,
        ask_k_min=5002,
        ask_k_max=5005,  # close_k 5006 >= 5005 va khong co bid (khoi xuong mua)
        bid_k_min=None,
        bid_k_max=None,
    )
    e3_events = detect_e3_events([bar_prev, bar_curr])
    assert len(e3_events) == 0  # Vi khac block_id!

    # 3. CVD reset luc 00:00 UTC moi ngay
    # Tao file csv.gz voi 2 ngay: 2023-01-01 va 2023-01-02
    import gzip
    f_path = tmp_path / "2023-01.csv.gz"
    with gzip.open(f_path, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,ask_k_min,ask_k_max,bid_k_min,bid_k_max\n")
        # Ngay 1: nen 23:55
        gf.write("2023-01-01T23:55:00Z,60000.0,60010.0,59990.0,60005.0,10.0,5.0,5.0,20,12.0,5000,,,,\n")
        # Ngay 2: nen 00:00
        gf.write("2023-01-02T00:00:00Z,60005.0,60020.0,60000.0,60010.0,8.0,6.0,2.0,15,12.0,5000,,,,\n")

    loaded_bars = load_crypto_footprint_bars(data_dir=tmp_path)
    assert len(loaded_bars) == 2
    assert loaded_bars[0].delta == 5.0
    assert loaded_bars[0].cvd == 5.0
    # Nen 00:00 cua ngay 2 phai reset ve dung delta cua chinh no (2.0), khong phai 5.0 + 2.0 = 7.0
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
    # Event buy (+1): close = 50000.0, exit = 50200.0 => y = +1 * (50200 / 50000 - 1) = +0.0040
    e_buy = OrderFlowEvent(
        event_type="E1",
        direction=+1,
        session_id=d,
        block_id="2023-01-01_00_08",
        bar_idx=10,
        t_end=datetime(2023, 1, 1, 1, 0, 0, tzinfo=UTC),
        close=50000.0,
    )
    # Event sell (-1): close = 50000.0, exit = 49800.0 => y = -1 * (49800 / 50000 - 1) = +0.0040
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
        close_k=5020,
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
        close_k=4980,
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

    # Kiem tra Hurdle 0.0021 sai so < 1e-12
    assert abs(ECONOMIC_HURDLE - 0.0021) < 1e-12


def test_7_cong_ngay_chong_nhin_truoc():
    """Ca 7: Cong ngay tu choi truoc 2026-11-01 (tra ve 2, khong mo file); tu 2026-11-01 di tiep."""
    # 2026-10-31: Tra ve 2 va loader khong duoc goi
    with patch("scripts.screen_crypto_orderflow.run_crypto_screening_pipeline") as mock_pipe:
        ret_block = main(args=[], today=date(2026, 10, 31))
        assert ret_block == 2
        mock_pipe.assert_not_called()

    # 2026-11-01: Di tiep vao pipeline
    with patch("scripts.screen_crypto_orderflow.run_crypto_screening_pipeline") as mock_pipe:
        mock_pipe.return_value = {
            "status": "CONTROL_FAILED",
            "ctrl_rho": 0.1,
            "message": "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN",
            "pairs": {},
        }
        ret_pass = main(args=[], today=date(2026, 11, 1))
        # Pipeline duoc goi
        mock_pipe.assert_called_once()
        assert ret_pass == 4


def test_8_phan_quyet_va_control_rho():
    """Ca 8: Cap dat CHINH nhung LAP LAI < hurdle => khong DAT; nguong p o LAP LAI la 0.05/k; rho = 0.3 => dung."""
    # 1. Kiem tra control rho dung bang 0.3 => BI LOAI
    bars = []
    d = date(2023, 1, 1)
    for i in range(50):
        bars.append(
            BarSummary(
                session_id=d,
                block_id="2023-01-01_00_08",
                bar_idx=i,
                t_start=datetime(2023, 1, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=5 * i),
                t_end=datetime(2023, 1, 1, 0, 5, tzinfo=UTC) + timedelta(minutes=5 * i),
                open=60000.0,
                high=60010.0,
                low=59990.0,
                close=60000.0,
                close_k=5000,
                delta=float(i),
                cvd=float(i),
                ask_k_min=None,
                ask_k_max=None,
                bid_k_min=None,
                bid_k_max=None,
            )
        )
    # Patch check_control_variable_crypto tra ve 0.30
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
            if call_counter["n"] <= 6:  # 6 cap dau tien la cua so CHINH
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0030,
                    "p_val": 0.001,
                    "passed": True,
                }
            else:  # 6 cap tiep theo la cua so LAP LAI
                return {
                    "n_events": 120,
                    "n_buy": 60,
                    "n_sell": 60,
                    "mean_y": 0.0015,  # < hurdle!
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
                # Chi cho 2 cap dau dat
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
    # Bay 2 khoi:
    # Khoi 1 (2023-01-01): 50 su kien y = +0.0100
    # Khoi 2 (2023-01-02): 50 su kien y = -0.0100
    # Neu bootstrap theo tung su kien doc lap, p-value se rat khac so voi bootstrap theo 2 khoi ngay.
    # Khi bootstrap theo 2 khoi ngay, cac ket qua co the co cua mean la:
    # - Chon khoi 1 hai lan (xac suat 1/4): mean = +0.0100
    # - Chon khoi 2 hai lan (xac suat 1/4): mean = -0.0100
    # - Chon 1 khoi 1 va 1 khoi 2 (xac suat 2/4): mean = 0.0000
    # Do do bootstrap mean <= 0 se xuat hien trong khoang 75% so lan => p-value ~ 0.75 (hoac p mot phia ~ 0.25).
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

    # Goi block_bootstrap_p_value tu screen_vn30f_orderflow
    p_val, _ = vn30f.block_bootstrap_p_value(evs, n_bootstrap=2000, seed=42)
    # Voi 2 khoi co trung binh doi xung (+0.01 va -0.01), p-value bootstrap theo khoi phai quanh 0.75
    # (neu resample tung su kien thi voi N=100 bien ngau nhien co tong 0, p-val se quanh 0.50 va phan phoi tap trung chat)
    assert 0.70 <= p_val <= 0.80


def _bar(dt: datetime, close: float | None, **kw) -> BarSummary:
    return BarSummary(
        session_id=dt.date(),
        block_id=get_crypto_block_id(dt),
        bar_idx=(dt.hour * 60 + dt.minute) // 5,
        t_start=dt,
        t_end=dt + timedelta(minutes=5),
        open=close,
        high=close,
        low=close,
        close=close,
        close_k=None if close is None else int(close // 12),
        delta=kw.get("delta", 0.0),
        cvd=kw.get("delta", 0.0),
        ask_k_min=kw.get("ask_k_min"),
        ask_k_max=kw.get("ask_k_max"),
        bid_k_min=kw.get("bid_k_min"),
        bid_k_max=kw.get("bid_k_max"),
    )


def test_10_nen_cuoi_khung_khong_vat_qua_funding():
    """Claude audit: nen 07:55 (t_end 08:00) thuoc khung 00-08, het khung la 08:00 chu khong phai 16:00."""
    ev_0755 = OrderFlowEvent(
        event_type="E1", direction=1, session_id=date(2023, 1, 1), block_id="2023-01-01_00_08",
        bar_idx=95, t_end=datetime(2023, 1, 1, 8, 0, tzinfo=UTC), close=60000.0,
    )
    ev_2355 = OrderFlowEvent(
        event_type="E1", direction=1, session_id=date(2023, 1, 1), block_id="2023-01-01_16_24",
        bar_idx=287, t_end=datetime(2023, 1, 2, 0, 0, tzinfo=UTC), close=60000.0,
    )
    assert crypto_block_end_fn(ev_0755) == datetime(2023, 1, 1, 8, 0, tzinfo=UTC)
    assert crypto_block_end_fn(ev_2355) == datetime(2023, 1, 2, 0, 0, tzinfo=UTC)

    lookup = build_crypto_price_lookup([
        _bar(datetime(2023, 1, 1, 8, 10, tzinfo=UTC), 60500.0),
        _bar(datetime(2023, 1, 2, 0, 10, tzinfo=UTC), 60500.0),
    ])
    res = evaluate_crypto_pair([ev_0755, ev_2355], lookup, h_minutes=15, alpha_threshold=0.05)
    assert res["n_events"] == 0


def test_11_nen_trong_giu_cho_de_e3_chi_ghep_nen_lien_nhau(tmp_path):
    """Claude audit: nen khong giao dich phai giu cho (close=None) de E3 khong ghep 00:00 voi 00:10."""
    import gzip

    f_path = tmp_path / "2023-01.csv.gz"
    with gzip.open(f_path, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,ask_k_min,ask_k_max,bid_k_min,bid_k_max\n")
        # 00:00 hap thu ban: close_k 5001 > bid_k_max 4999
        gf.write("2023-01-01T00:00:00Z,60000.0,60050.0,59950.0,60020.0,1.0,3.0,-2.0,10,12.0,5001,,,4995,4999\n")
        # 00:05 khong co giao dich
        gf.write("2023-01-01T00:05:00Z,,,,,0.0,0.0,0.0,0,,,,,,\n")
        # 00:10 khoi xuong mua: close_k 5006 >= ask_k_max 5005, khong co bid
        gf.write("2023-01-01T00:10:00Z,60020.0,60100.0,60010.0,60080.0,3.0,1.0,2.0,10,12.0,5006,5002,5005,,\n")

    bars = load_crypto_footprint_bars(data_dir=tmp_path)
    assert len(bars) == 3
    assert bars[1].close is None
    assert bars[2].cvd == pytest.approx(0.0)
    assert detect_e3_events(bars) == []


def _write_synthetic_month(path, year: int, month: int, n_days: int, seed: int) -> None:
    """Ghi file tom tat gia: delta cung dau voi close-open (rho doi chung cao), vai nen trong."""
    import gzip
    import random

    rng = random.Random(seed)
    price = 30000.0
    with gzip.open(path, "wt", encoding="utf-8") as gf:
        gf.write("ts,open,high,low,close,buy,sell,delta,n_trades,step,close_k,ask_k_min,ask_k_max,bid_k_min,bid_k_max\n")
        for day in range(n_days):
            for i in range(288):
                dt = datetime(year, month, day + 1, tzinfo=UTC) + timedelta(minutes=5 * i)
                ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if i == 100:
                    gf.write(f"{ts},,,,,0.0,0.0,0.0,0,,,,,,\n")
                    continue
                o = price
                c = round(o + rng.gauss(0, 20), 1)
                delta = (c - o) * 0.5 + rng.gauss(0, 2)
                step = 6.0
                ck = int(c // step)
                ask = f"{ck - 2},{ck}" if rng.random() < 0.2 else ","
                bid = f"{ck + 1},{ck + 3}" if rng.random() < 0.2 else ","
                gf.write(
                    f"{ts},{o},{max(o, c) + 5},{min(o, c) - 5},{c},{max(delta, 0) + 5},{max(-delta, 0) + 5},"
                    f"{delta:.4f},50,{step},{ck},{ask},{bid}\n"
                )
                price = c


def test_12_dau_cuoi_main_sau_cong_ngay(tmp_path, capsys):
    """Claude audit: main() sau cong ngay chay tron tren file gia (CHINH + LAP LAI), in bang 6 cap, return 0."""
    _write_synthetic_month(tmp_path / "2024-12.csv.gz", 2024, 12, 10, seed=1)
    _write_synthetic_month(tmp_path / "2025-01.csv.gz", 2025, 1, 10, seed=2)
    # File ngoai cua so (niem phong) khong duoc doc vao: dat noi dung hong de neu doc se co canh bao
    (tmp_path / "2026-09.csv.gz").write_bytes(b"khong phai gzip")

    ret = main(args=["--data-dir", str(tmp_path)], today=date(2026, 11, 1))
    out, err = capsys.readouterr()
    assert ret == 0
    assert "2026-09" not in err
    for pair in ("E1_15m", "E1_30m", "E2_15m", "E2_30m", "E3_15m", "E3_30m"):
        assert pair in out
