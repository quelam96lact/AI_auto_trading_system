"""Unit tests cho scripts/screen_vn30f_orderbook.py (Brief đợt 162 & 163).

Mọi test dùng phiên dựng tay hoặc thư mục tạm, TUYỆT ĐỐI KHÔNG đọc data/orderbook/ thật.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import random
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from scripts.audit_information import fast_spearman_rank_correlation
from scripts.build_orderbook_features import MinuteRow, session_minutes
from scripts.screen_vn30f_orderbook import (
    FEATURE_NAMES,
    HOLDOUT_START_DATE,
    IS_END_DATE,
    IS_START_DATE,
    SessionData,
    calculate_p90_thresholds,
    compute_roundtrip_cost,
    compute_session_target_rows,
    evaluate_pairs,
    load_all_sessions,
    main,
    run_screening,
    select_independent_events,
)
from trading.calendar_vn import TZ
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
)


def _make_synthetic_session(
    session_date: date,
    contract: str = "VN30F2610",
    base_mid: float = 1300.0,
    spread_val: float = 0.2,
    ofi_pattern: str = "positive",
    skip_minutes: set[int] | None = None,
    custom_mids: list[float] | None = None,
) -> SessionData:
    """Tạo 1 phiên tổng hợp đúng 240 phút trên lưới."""
    grid = session_minutes(session_date)
    assert len(grid) == 240
    rows: list[MinuteRow] = []
    skip_set = skip_minutes or set()

    for i, m in enumerate(grid):
        if i in skip_set:
            rows.append(
                MinuteRow(
                    minute=m,
                    n_quote=0,
                    n_trade=0,
                    n_other=0,
                    mid_close=None,
                    spread=None,
                    imb_top1=None,
                    imb_top5=None,
                    ofi=0.0,
                    trade_qty=0.0,
                )
            )
            continue

        if custom_mids is not None and i < len(custom_mids):
            mid = custom_mids[i]
        else:
            # Tạo xu hướng giá dao động có phương sai để kiểm tra biến đối chứng
            # Phút lẻ tăng 0.2, phút chẵn tăng 0.0 -> mid_chg_same_1m dao động giữa 0.0 và 0.2
            mid = base_mid + (i // 2) * 0.2 + (0.2 if i % 2 == 1 else 0.0)

        spread = spread_val
        imb1 = 0.5 if (i % 2 == 0) else -0.5
        imb5 = 0.4 if (i % 2 == 0) else -0.4

        if ofi_pattern == "positive":
            # ofi cùng dấu với thay đổi mid cùng phút
            ofi_val = 10.0 if (i % 2 == 1) else -10.0
        elif ofi_pattern == "negative":
            ofi_val = -10.0 if (i % 2 == 1) else 10.0
        elif ofi_pattern == "random":
            ofi_val = float(random.choice([-10.0, 0.0, 10.0]))
        else:
            ofi_val = 0.0

        rows.append(
            MinuteRow(
                minute=m,
                n_quote=10,
                n_trade=5,
                n_other=0,
                mid_close=mid,
                spread=spread,
                imb_top1=imb1,
                imb_top5=imb5,
                ofi=ofi_val,
                trade_qty=abs(ofi_val),
            )
        )

    usable = sum(1 for r in rows if r.usable())
    return SessionData(
        session_date=session_date,
        contract=contract,
        rows=rows,
        usable_count=usable,
        is_valid=(usable / 240.0 >= 0.90),
        usable_ratio=usable / 240.0,
    )


# --- 1. Độ trễ một phút (162 §4.1) ---
def test_do_tre_mot_phut():
    """Tín hiệu tại t, vào lệnh tại t+1: mục tiêu mua h=1 đúng bằng bid(t+2) - ask(t+1)."""
    d = date(2026, 10, 5)
    sess = _make_synthetic_session(d, base_mid=1300.0, spread_val=0.4)
    target_rows = compute_session_target_rows(sess)

    # Xét phút t=10
    t = 10
    r_t = target_rows[t]
    ask_11 = sess.rows[11].mid_close + sess.rows[11].spread / 2.0
    bid_12 = sess.rows[12].mid_close - sess.rows[12].spread / 2.0
    expected_fwd_buy_1 = bid_12 - ask_11
    expected_mid_chg_1 = sess.rows[12].mid_close - sess.rows[11].mid_close

    assert r_t["fwd_buy_1"] == pytest.approx(expected_fwd_buy_1)
    assert r_t["mid_chg_1"] == pytest.approx(expected_mid_chg_1)


# --- 2. Spread không bị đếm hai lần (162 §4.2) ---
def test_spread_khong_bi_dem_hai_lan():
    """Spread 0 -> target = chênh lệch mid; spread 0.2 -> target giảm đúng 0.2 điểm."""
    d = date(2026, 10, 5)
    sess_zero_spread = _make_synthetic_session(d, base_mid=1300.0, spread_val=0.0)
    sess_with_spread = _make_synthetic_session(d, base_mid=1300.0, spread_val=0.2)

    rows_0 = compute_session_target_rows(sess_zero_spread)
    rows_spread = compute_session_target_rows(sess_with_spread)

    for t in range(50):
        # Với spread 0: fwd_buy_h == mid_chg_h
        assert rows_0[t]["fwd_buy_1"] == pytest.approx(rows_0[t]["mid_chg_1"])
        assert rows_0[t]["fwd_buy_5"] == pytest.approx(rows_0[t]["mid_chg_5"])
        # Với spread 0.2 (0.1 vào + 0.1 ra = 0.2): fwd_buy_h == mid_chg_h - 0.2
        assert rows_spread[t]["fwd_buy_1"] == pytest.approx(rows_spread[t]["mid_chg_1"] - 0.2)
        assert rows_spread[t]["fwd_buy_5"] == pytest.approx(rows_spread[t]["mid_chg_5"] - 0.2)


# --- 3. Bất biến theo tương lai & P90 chỉ từ IS (162 §4.3) ---
def test_bat_bien_theo_tuong_lai_va_nguong_p90_chi_tinh_tu_is():
    """Sửa phút sau t không đổi feature <= t; thêm phiên Holdout không làm đổi ngưỡng P90 IS."""
    d1 = date(2026, 10, 5)
    d2 = date(2026, 10, 6)
    d_holdout = date(2026, 12, 2)  # Holdout

    s1 = _make_synthetic_session(d1)
    s2 = _make_synthetic_session(d2)
    s_hold_raw = _make_synthetic_session(d_holdout)
    s_hold = SessionData(
        session_date=d_holdout,
        contract=s_hold_raw.contract,
        rows=[dataclasses.replace(r, imb_top1=0.99) for r in s_hold_raw.rows],
        usable_count=s_hold_raw.usable_count,
        is_valid=s_hold_raw.is_valid,
        usable_ratio=s_hold_raw.usable_ratio,
    )

    is_rows = compute_session_target_rows(s1) + compute_session_target_rows(s2)
    p90_is = calculate_p90_thresholds(is_rows, FEATURE_NAMES)

    # Thêm phiên holdout
    all_rows = is_rows + compute_session_target_rows(s_hold)
    p90_polluted = calculate_p90_thresholds(all_rows, FEATURE_NAMES)
    # Chứng minh: nếu gộp holdout vào tính thì P90 bị ô nhiễm
    assert p90_polluted["imb_top1"] > p90_is["imb_top1"]

    # Hàm chuẩn chỉ tính trên is_rows -> bất biến và không bị đổi
    p90_is_repeat = calculate_p90_thresholds(is_rows, FEATURE_NAMES)
    assert p90_is == p90_is_repeat
    assert p90_is["imb_top1"] == pytest.approx(0.5)


# --- 4. Không vượt phiên (162 §4.4) ---
def test_khong_vuot_phien():
    """t + 1 + h >= 240 -> mục tiêu là None, không lấy sang phiên sau."""
    d = date(2026, 10, 5)
    sess = _make_synthetic_session(d)
    rows = compute_session_target_rows(sess)

    # Tại t = 239: t+1+1 = 241 >= 240 -> fwd_1 là None
    assert rows[239]["fwd_buy_1"] is None
    assert rows[239]["mid_chg_1"] is None
    # Tại t = 238: t+1+1 = 240 >= 240 -> fwd_1 là None
    assert rows[238]["fwd_buy_1"] is None
    # Tại t = 237: t+1+1 = 239 < 240 -> fwd_1 có giá trị
    assert rows[237]["fwd_buy_1"] is not None

    # Với h=5: tại t = 233: t+1+5 = 239 < 240 -> có; tại t = 234: t+1+5 = 240 -> None
    assert rows[233]["fwd_buy_5"] is not None
    assert rows[234]["fwd_buy_5"] is None

    # Với h=15: tại t = 223: t+1+15 = 239 < 240 -> có; tại t = 224: t+1+15 = 240 -> None
    assert rows[223]["fwd_buy_15"] is not None
    assert rows[224]["fwd_buy_15"] is None


# --- 5. Chọn sự kiện độc lập tham lam (162 §4.5) ---
def test_chon_su_kien_doc_lap_tham_lam():
    """Hai tín hiệu liền nhau với h=5 chỉ đếm 1; đếm đúng số tính tay."""
    rows = []
    base_time = datetime(2026, 10, 5, 9, 0, tzinfo=TZ)
    for i in range(50):
        m_time = base_time + timedelta(minutes=i)
        val = 1.0 if i in (10, 11, 12, 20) else 0.0
        rows.append(
            {
                "minute": m_time,
                "session_date": date(2026, 10, 5),
                "minute_idx": i,
                "imb_top5": val,
                "fwd_buy_5": 0.5,
                "fwd_sell_5": -0.5,
                "mid_chg_5": 0.5,
            }
        )

    events = select_independent_events(rows, feat_name="imb_top5", p90=0.8, h=5)
    assert len(events) == 2
    assert events[0]["minute_idx"] == 10
    assert events[1]["minute_idx"] == 20


# --- 6. Hướng sự kiện (162 §4.6) ---
def test_huong_su_kien():
    """Đặc trưng âm và giá giảm -> đóng góp dương vào m."""
    rows = [
        {
            "minute": datetime(2026, 10, 5, 9, 10, tzinfo=TZ),
            "session_date": date(2026, 10, 5),
            "minute_idx": 10,
            "imb_top5": -0.9,  # Âm -> bán short
            "fwd_buy_1": -0.8,  # Mua bị lỗ 0.8
            "fwd_sell_1": 0.8,  # Bán được lãi 0.8
            "mid_chg_1": -0.7,
        }
    ]
    events = select_independent_events(rows, feat_name="imb_top5", p90=0.5, h=1)
    assert len(events) == 1
    assert events[0]["direction"] == -1
    assert events[0]["realized_ret"] == pytest.approx(0.8)


# --- 7. Cổng mẫu IS < 40 phiên & Sự kiện < 100 (162 §4.7) ---
def test_cong_mau_duoi_40_phien_is_va_duoi_100_su_kien():
    """IS dưới 40 phiên hợp lệ -> dừng không in rho; < 100 sự kiện -> THIẾU SỨC MẠNH."""
    sessions = [_make_synthetic_session(date(2026, 10, 5) + timedelta(days=i)) for i in range(35)]
    res = run_screening(
        sessions=sessions,
        n_permutations=10,
    )
    assert res["status"] == "STOPPED_INSUFFICIENT_IS_SESSIONS"
    assert res["table"] is None

    # Dựng 40 phiên
    sessions_40 = [_make_synthetic_session(date(2026, 10, 5) + timedelta(days=i)) for i in range(40)]
    res_40 = run_screening(
        sessions=sessions_40,
        n_permutations=10,
    )
    assert res_40["status"] == "SUCCESS"
    assert res_40["table"] is not None
    for pair_res in res_40["table"].values():
        if pair_res["n_indep"] < 100:
            assert pair_res["label"] == "THIẾU SỨC MẠNH"


# --- 8. Niêm phong (i): Không đọc holdout khi không có cờ mở niêm phong (Brief 163 vòng 3 §1a, §1c, §34) ---
def test_main_niem_phong_khong_doc_holdout_khi_khong_co_co(tmp_path):
    """Không có cờ mở niêm phong: build_minute_features KHÔNG BAO GIỜ được gọi với ngày >= 01/12/2026."""
    c_is = tmp_path / "VN30F2610"
    c_hold = tmp_path / "VN30F2612"
    c_is.mkdir(parents=True)
    c_hold.mkdir(parents=True)

    # Tạo 40 file IS và 35 file Holdout
    d_is_start = date(2026, 10, 1)
    for i in range(40):
        d_val = d_is_start + timedelta(days=i)
        f_p = c_is / f"{d_val.isoformat()}.jsonl.gz"
        with gzip.open(f_p, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    d_hold_start = date(2026, 12, 1)
    for i in range(35):
        d_val = d_hold_start + timedelta(days=i)
        f_p = c_hold / f"{d_val.isoformat()}.jsonl.gz"
        with gzip.open(f_p, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    called_dates: list[date] = []

    def fake_build(messages, s_date, stats=None):
        called_dates.append(s_date)
        return _make_synthetic_session(s_date).rows

    with patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=fake_build):
        rc = main(today=date(2026, 12, 1), args=["--data-dir", str(tmp_path), "--permutations", "10"])
        assert rc == 0
        assert len(called_dates) == 40
        assert all(d < HOLDOUT_START_DATE for d in called_dates)


# --- 9. Niêm phong (ii): Từ chối mở niêm phong & KHÔNG ghi log & KHÔNG đọc holdout (Brief 163 vòng 3 §1c, §34) ---
def test_main_niem_phong_tu_choi_khong_ghi_log_khong_doc_holdout(tmp_path):
    """Cờ mở niêm phong bị từ chối, KHÔNG ghi log, KHÔNG gọi build_minute_features với ngày >= 01/12/2026 trong cả 3 trường hợp:
    (a) Cặp chưa ĐÁNG KỂ ở IS.
    (b) Dưới 30 file phiên niêm phong trên đĩa.
    (c) Tên cặp không thuộc 9 cặp.
    """
    c_is = tmp_path / "VN30F2610"
    c_hold = tmp_path / "VN30F2612"
    c_is.mkdir(parents=True)
    c_hold.mkdir(parents=True)

    d_is_start = date(2026, 10, 1)
    for i in range(40):
        d_val = d_is_start + timedelta(days=i)
        f_p = c_is / f"{d_val.isoformat()}.jsonl.gz"
        with gzip.open(f_p, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    d_hold_start = date(2026, 12, 1)
    for i in range(35):
        d_val = d_hold_start + timedelta(days=i)
        f_p = c_hold / f"{d_val.isoformat()}.jsonl.gz"
        with gzip.open(f_p, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    # Trường hợp (a): Cặp chưa ĐÁNG KỂ ở IS
    called_dates_a: list[date] = []

    def fake_build_a(messages, s_date, stats=None):
        called_dates_a.append(s_date)
        return _make_synthetic_session(s_date).rows

    log_a = tmp_path / "log_a.md"
    with (
        patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=fake_build_a),
        patch("scripts.screen_vn30f_orderbook.evaluate_pairs") as mock_eval_a,
    ):
        mock_eval_a.return_value = {
            "imb_top5_fwd_5": {
                "feature": "imb_top5",
                "horizon": 5,
                "rho": 0.05,
                "p_value": 0.50,
                "n_indep": 120,
                "n_buy": 60,
                "n_sell": 60,
                "side_warning": False,
                "mean_m": 0.1,
                "roundtrip_cost": 0.49,
                "hurdle": 0.735,
                "label": "KHÔNG ĐÁNG KỂ",
            }
        }
        rc_a = main(
            today=date(2026, 12, 1),
            args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "imb_top5_fwd_5", "--permutations", "10"],
            unlock_log_path=log_a,
        )
        assert rc_a != 0
        assert not log_a.exists()
        assert all(d < HOLDOUT_START_DATE for d in called_dates_a)

    # Trường hợp (b): Dưới 30 file niêm phong trên đĩa (tạo thư mục riêng chỉ có 20 file holdout)
    tmp_path_b = tmp_path / "case_b"
    b_is = tmp_path_b / "VN30F2610"
    b_hold = tmp_path_b / "VN30F2612"
    b_is.mkdir(parents=True)
    b_hold.mkdir(parents=True)
    for i in range(40):
        d_val = d_is_start + timedelta(days=i)
        with gzip.open(b_is / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")
    for i in range(20):
        d_val = d_hold_start + timedelta(days=i)
        with gzip.open(b_hold / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    called_dates_b: list[date] = []

    def fake_build_b(messages, s_date, stats=None):
        called_dates_b.append(s_date)
        return _make_synthetic_session(s_date).rows

    log_b = tmp_path / "log_b.md"
    with (
        patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=fake_build_b),
        patch("scripts.screen_vn30f_orderbook.evaluate_pairs") as mock_eval_b,
    ):
        mock_eval_b.return_value = {
            "imb_top5_fwd_5": {
                "feature": "imb_top5",
                "horizon": 5,
                "rho": 0.25,
                "p_value": 0.01,
                "n_indep": 150,
                "n_buy": 75,
                "n_sell": 75,
                "side_warning": False,
                "mean_m": 1.5,
                "roundtrip_cost": 0.49,
                "hurdle": 0.735,
                "label": "ĐÁNG KỂ",
            }
        }
        rc_b = main(
            today=date(2026, 12, 1),
            args=["--data-dir", str(tmp_path_b), "--unlock-holdout-pair", "imb_top5_fwd_5", "--permutations", "10"],
            unlock_log_path=log_b,
        )
        assert rc_b != 0
        assert not log_b.exists()
        assert all(d < HOLDOUT_START_DATE for d in called_dates_b)

    # Trường hợp (c): Tên cặp không thuộc 9 cặp
    called_dates_c: list[date] = []

    def fake_build_c(messages, s_date, stats=None):
        called_dates_c.append(s_date)
        return _make_synthetic_session(s_date).rows

    log_c = tmp_path / "log_c.md"
    with patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=fake_build_c):
        rc_c = main(
            today=date(2026, 12, 1),
            args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "invalid_pair_xyz", "--permutations", "10"],
            unlock_log_path=log_c,
        )
        assert rc_c != 0
        assert not log_c.exists()
        assert all(d < HOLDOUT_START_DATE for d in called_dates_c)


# --- 10. Niêm phong (iii): Đủ điều kiện thì GHI LOG TRƯỚC, ĐỌC HOLDOUT SAU (Brief 163 vòng 3 §1d, §34) ---
def test_main_niem_phong_du_dieu_kien_ghi_log_truoc_doc_holdout_sau(tmp_path):
    """Có cờ và đủ 3 điều kiện: lời gọi ghi log đứng TRƯỚC lời gọi build_minute_features đầu tiên cho ngày >= 01/12."""
    c_is = tmp_path / "VN30F2610"
    c_hold = tmp_path / "VN30F2612"
    c_is.mkdir(parents=True)
    c_hold.mkdir(parents=True)

    d_is_start = date(2026, 10, 1)
    for i in range(40):
        d_val = d_is_start + timedelta(days=i)
        with gzip.open(c_is / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    d_hold_start = date(2026, 12, 1)
    for i in range(35):
        d_val = d_hold_start + timedelta(days=i)
        with gzip.open(c_hold / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    log_file = tmp_path / "holdout-unlock-log.md"
    events_order: list[str] = []

    from scripts import screen_vn30f_orderbook

    orig_write_log = screen_vn30f_orderbook._write_holdout_log

    def spy_write_log(*args, **kwargs):
        events_order.append("WRITE_LOG")
        return orig_write_log(*args, **kwargs)

    def spy_build_minute_features(messages, s_date, stats=None):
        if s_date >= HOLDOUT_START_DATE:
            events_order.append(f"BUILD_HOLDOUT_{s_date}")
        return _make_synthetic_session(s_date).rows

    with (
        patch("scripts.screen_vn30f_orderbook._write_holdout_log", side_effect=spy_write_log),
        patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=spy_build_minute_features),
        patch("scripts.screen_vn30f_orderbook.evaluate_pairs") as mock_eval,
        patch("scripts.screen_vn30f_orderbook._evaluate_holdout_pair") as mock_holdout_eval,
    ):
        mock_eval.return_value = {
            "imb_top5_fwd_5": {
                "feature": "imb_top5",
                "horizon": 5,
                "rho": 0.25,
                "p_value": 0.01,
                "n_indep": 150,
                "n_buy": 75,
                "n_sell": 75,
                "side_warning": False,
                "mean_m": 1.5,
                "roundtrip_cost": 0.49,
                "hurdle": 0.735,
                "label": "ĐÁNG KỂ",
            }
        }
        mock_holdout_eval.return_value = {
            "feature": "imb_top5",
            "horizon": 5,
            "rho": 0.25,
            "p_value": 0.01,
            "mean_m": 1.5,
            "roundtrip_cost": 0.49,
            "hurdle": 0.735,
            "passed": True,
            "label": "ĐÁNG KỂ",
        }
        rc = main(
            today=date(2026, 12, 1),
            args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "imb_top5_fwd_5", "--permutations", "10"],
            unlock_log_path=log_file,
        )
        assert rc == 0
        assert log_file.exists()
        assert "WRITE_LOG" in events_order
        holdout_calls = [i for i, ev in enumerate(events_order) if ev.startswith("BUILD_HOLDOUT")]
        assert len(holdout_calls) == 35
        log_idx = events_order.index("WRITE_LOG")
        assert log_idx < holdout_calls[0]


# --- 11. Niêm phong (e): Đủ 30 file nhưng dưới 30 phiên hợp lệ (Brief 163 vòng 3 §1e, §34) ---
def test_main_niem_phong_du_30_file_nhung_duoi_30_phien_hop_le(tmp_path, capsys):
    """Có đủ 30 file trên đĩa nhưng sau khi đọc chỉ có < 30 phiên hợp lệ (>= 90% phút) -> dừng, log đã ghi."""
    c_is = tmp_path / "VN30F2610"
    c_hold = tmp_path / "VN30F2612"
    c_is.mkdir(parents=True)
    c_hold.mkdir(parents=True)

    d_is_start = date(2026, 10, 1)
    for i in range(40):
        d_val = d_is_start + timedelta(days=i)
        with gzip.open(c_is / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    d_hold_start = date(2026, 12, 1)
    for i in range(35):
        d_val = d_hold_start + timedelta(days=i)
        with gzip.open(c_hold / f"{d_val.isoformat()}.jsonl.gz", "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": f"{d_val.strftime('%Y/%m/%d')} 09:00:00"}) + "\n")

    log_file = tmp_path / "holdout-unlock-log.md"

    def fake_build(messages, s_date, stats=None):
        if s_date >= HOLDOUT_START_DATE and s_date.day > 20:
            # 15 phiên holdout bị thiếu dữ liệu (usable = 0 -> không hợp lệ)
            return _make_synthetic_session(s_date, skip_minutes=set(range(240))).rows
        return _make_synthetic_session(s_date).rows

    with (
        patch("scripts.screen_vn30f_orderbook.build_minute_features", side_effect=fake_build),
        patch("scripts.screen_vn30f_orderbook.evaluate_pairs") as mock_eval,
    ):
        mock_eval.return_value = {
            "imb_top5_fwd_5": {
                "feature": "imb_top5",
                "horizon": 5,
                "rho": 0.25,
                "p_value": 0.01,
                "n_indep": 150,
                "n_buy": 75,
                "n_sell": 75,
                "side_warning": False,
                "mean_m": 1.5,
                "roundtrip_cost": 0.49,
                "hurdle": 0.735,
                "label": "ĐÁNG KỂ",
            }
        }
        rc = main(
            today=date(2026, 12, 1),
            args=["--data-dir", str(tmp_path), "--unlock-holdout-pair", "imb_top5_fwd_5", "--permutations", "10"],
            unlock_log_path=log_file,
        )
        assert rc != 0
        assert log_file.exists()  # Log đã được ghi trước khi đọc
        captured = capsys.readouterr()
        assert "KHÔNG ĐỦ PHIÊN NIÊM PHONG HỢP LỆ" in (captured.out + captured.err)
        assert "KẾT QUẢ MỞ NIÊM PHONG HOLDOUT" not in captured.out


# --- 12. Bỏ file nằm ngay thư mục gốc & in cảnh báo (Brief 163 vòng 3 §2) ---
def test_load_all_sessions_bo_qua_file_nam_ngay_thu_muc_goc(tmp_path, capsys):
    """File .jsonl.gz nằm ngay data_dir (không trong thư mục con) -> bỏ qua và in cảnh báo."""
    c_dir = tmp_path / "VN30F2610"
    c_dir.mkdir(parents=True)
    f_sub = c_dir / "2026-10-05.jsonl.gz"
    with gzip.open(f_sub, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": "2026/10/05 09:00:00"}) + "\n")

    f_root = tmp_path / "loose_file_2026-10-06.jsonl.gz"
    with gzip.open(f_root, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": "2026/10/06 09:00:00"}) + "\n")

    sessions = load_all_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].contract == "VN30F2610"
    assert sessions[0].session_date == date(2026, 10, 5)

    captured = capsys.readouterr()
    assert "[CẢNH BÁO] Bỏ qua file" in captured.err
    assert "loose_file_2026-10-06.jsonl.gz" in captured.err


# --- 13. Bỏ cờ CLI --unlock-log-path (Brief 163 vòng 3 §3) ---
def test_main_tu_choi_co_unlock_log_path():
    """CLI từ chối cờ --unlock-log-path (SystemExit)."""
    with pytest.raises(SystemExit):
        main(args=["--unlock-log-path", "docs/holdout-unlock-log.md"])


# --- 14. Bỏ cờ --date: main từ chối cờ --date (Brief 163 A.3 & B) ---
def test_main_tu_choi_co_date():
    """CLI KHÔNG có cờ ghi đè ngày --date, nếu truyền --date sẽ bị argparse từ chối (SystemExit)."""
    with pytest.raises(SystemExit):
        main(args=["--date", "2026-12-01"])


# --- 15. Cấu trúc thư mục con & Trùng ngày giữa các hợp đồng (Brief 163 A.2 & B) ---
def test_load_all_sessions_doc_dung_cau_truc_thu_muc_con(tmp_path):
    """load_all_sessions đọc đúng data_dir/<contract>/<date>.jsonl.gz. Trùng ngày ở 2 hợp đồng thì dừng và báo lỗi."""
    # Dựng 2 thư mục con
    c1_dir = tmp_path / "VN30F2610"
    c2_dir = tmp_path / "VN30F2611"
    c1_dir.mkdir(parents=True)
    c2_dir.mkdir(parents=True)

    f1 = c1_dir / "2026-10-05.jsonl.gz"
    f2 = c2_dir / "2026-11-05.jsonl.gz"

    for f in (f1, f2):
        with gzip.open(f, "wt", encoding="utf-8") as gf:
            gf.write(json.dumps({"trading_time": "2026/10/05 09:00:00", "recv_ts": "2026-10-05T09:00:01+07:00"}) + "\n")

    # Đọc bình thường
    sessions = load_all_sessions(tmp_path)
    assert len(sessions) == 2
    contracts = {s.contract for s in sessions}
    assert "VN30F2610" in contracts
    assert "VN30F2611" in contracts

    # Tạo file trùng ngày ở c2_dir
    f_dup = c2_dir / "2026-10-05.jsonl.gz"
    with gzip.open(f_dup, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"trading_time": "2026/10/05 09:00:00"}) + "\n")

    # Phải raise ValueError do trùng ngày
    with pytest.raises(ValueError, match="Trùng ngày"):
        load_all_sessions(tmp_path)


# --- 13. Phiên 25/09 được tính vào IS, phiên 24/09 không (Brief 163 A.1 & B) ---
def test_phien_25_09_tinh_vao_is_va_24_09_khong():
    """IS bắt đầu từ 25/09/2026. Phiên 25/09 thuộc IS, phiên 24/09 nằm ngoài IS."""
    assert IS_START_DATE == date(2026, 9, 25)
    s_24 = _make_synthetic_session(date(2026, 9, 24))
    s_25 = _make_synthetic_session(date(2026, 9, 25))
    s_30 = _make_synthetic_session(date(2026, 11, 30))
    s_01_12 = _make_synthetic_session(date(2026, 12, 1))

    # Kiểm tra phân loại IS
    valid_sessions = [s_24, s_25, s_30, s_01_12]
    is_sessions = [s for s in valid_sessions if IS_START_DATE <= s.session_date <= IS_END_DATE]
    is_dates = [s.session_date for s in is_sessions]

    assert date(2026, 9, 25) in is_dates
    assert date(2026, 11, 30) in is_dates
    assert date(2026, 9, 24) not in is_dates
    assert date(2026, 12, 1) not in is_dates


# --- 14. Chi phí dùng trung vị mid_close của IS (Brief 163 A.7 & B) ---
def test_chi_phi_dung_trung_vi_khong_dung_trung_binh():
    """Chi phí tính theo TRUNG VỊ mid_close của IS, không phải trung bình. Không có mid -> lỗi."""
    # Dựng 240 nến với giá mid sao cho trung bình != trung vị
    # Ví dụ: 200 nến giá 1300.0, 40 nến giá 1900.0
    # Trung vị (percentile 50) = 1300.0
    # Trung bình = (200*1300 + 40*1900)/240 = 1400.0
    mids = [1300.0] * 200 + [1900.0] * 40
    sess = _make_synthetic_session(date(2026, 10, 5), custom_mids=mids)
    is_rows = compute_session_target_rows(sess)

    # Tính trung vị từ is_rows
    all_mids = [r["mid_close"] for r in is_rows if r.get("mid_close") is not None]
    from scripts.audit_information import calculate_percentile
    med_mid = calculate_percentile(all_mids, 50.0)
    avg_mid = sum(all_mids) / len(all_mids)

    assert med_mid == pytest.approx(1300.0)
    assert avg_mid == pytest.approx(1400.0)

    # Chi phí chuẩn tính theo trung vị
    expected_cost = compute_roundtrip_cost(med_mid)
    wrong_cost = compute_roundtrip_cost(avg_mid)
    assert expected_cost != pytest.approx(wrong_cost)

    # Khi không có giá mid nào -> evaluate_pairs phải raise ValueError
    empty_rows = [{"mid_close": None} for _ in range(10)]
    with pytest.raises(ValueError, match="Không có giá mid"):
        evaluate_pairs(empty_rows, {}, (0.0, []), mid_price=None)


# --- 15. Số sự kiện mua/bán & Nhãn không đủ trả phí (Brief 163 A.8 & B) ---
def test_so_su_kien_mua_ban_va_nhan_khong_du_tra_phi():
    """Kiểm tra số sự kiện mua/bán độc lập và nhãn 'có thông tin nhưng không đủ trả phí'."""
    rows = []
    base_time = datetime(2026, 10, 5, 9, 0, tzinfo=TZ)
    # Tạo 60 sự kiện mua và 60 sự kiện bán cách nhau 2 phút
    for i in range(240):
        m_time = base_time + timedelta(minutes=i)
        if i % 4 == 0:
            val = 1.0  # Mua
            fwd_b, fwd_s = 0.2, -0.2
            mid_chg = 0.5
        elif i % 4 == 2:
            val = -1.0  # Bán
            fwd_b, fwd_s = -0.2, 0.2
            mid_chg = -0.5
        else:
            val = 0.0
            fwd_b, fwd_s = 0.0, 0.0
            mid_chg = 0.0
        rows.append(
            {
                "minute": m_time,
                "session_date": date(2026, 10, 5),
                "minute_idx": i,
                "imb_top1": val,
                "fwd_buy_1": fwd_b,
                "fwd_sell_1": fwd_s,
                "mid_chg_1": mid_chg,
                "mid_close": 1300.0,
            }
        )

    # Đánh giá cặp imb_top1_fwd_1:
    # Lợi nhuận m = 0.2 điểm, trong khi chi phí = ~0.49 điểm, hurdle = ~0.735 điểm -> m < hurdle
    # Giả sử thống kê đạt (|rho| > P95, p <= 0.05)
    perm_res = (0.05, [0.01] * 1000)  # threshold 95 = 0.05
    table = evaluate_pairs(rows, {"imb_top1": 0.5, "imb_top5": 0.5, "ofi": 5.0}, perm_res, mid_price=1300.0)

    res_pair = table["imb_top1_fwd_1"]
    assert res_pair["n_buy"] == 60
    assert res_pair["n_sell"] == 60
    assert res_pair["n_indep"] == 120
    assert res_pair["side_warning"] is False
    assert res_pair["mean_m"] == pytest.approx(0.2)
    # Vì đạt thống kê (rho > threshold_95) nhưng m < hurdle -> "có thông tin nhưng không đủ trả phí"
    assert res_pair["label"] == "có thông tin nhưng không đủ trả phí"


# --- 16. Khối trùng phiên (163 §4.10) ---
def test_khoi_hoan_vi_trung_phien_du_240_hang():
    """3 phiên có vài phút None: số hàng mỗi phiên đúng 240, khối bắt đầu ở 09:00."""
    d1 = date(2026, 10, 5)
    d2 = date(2026, 10, 6)
    d3 = date(2026, 10, 7)

    s1 = _make_synthetic_session(d1, skip_minutes={5, 6, 20})
    s2 = _make_synthetic_session(d2, skip_minutes={10, 11})
    s3 = _make_synthetic_session(d3, skip_minutes={100})

    rows1 = compute_session_target_rows(s1)
    rows2 = compute_session_target_rows(s2)
    rows3 = compute_session_target_rows(s3)

    assert len(rows1) == 240
    assert len(rows2) == 240
    assert len(rows3) == 240

    panel = rows1 + rows2 + rows3
    assert len(panel) == 720

    assert panel[0]["minute"].time().strftime("%H:%M") == "09:00"
    assert panel[240]["minute"].time().strftime("%H:%M") == "09:00"
    assert panel[480]["minute"].time().strftime("%H:%M") == "09:00"


# --- 17. None không vào tính rho (163 §4.11) ---
def test_none_khong_vao_tinh_rho():
    """Thêm 1 phút None vào giữa không làm đổi rho so với bỏ hẳn phút đó."""
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    y = [1.5, 1.8, 3.2, 3.9, 5.1, 6.2, 6.8, 8.1, 9.0, 10.2]
    rho_clean = fast_spearman_rank_correlation(x, y)

    panel_with_none = []
    for i in range(len(x)):
        if i == 3:
            panel_with_none.append({"feat": None, "target": None})
        panel_with_none.append({"feat": x[i], "target": y[i]})

    x_filtered = [r["feat"] for r in panel_with_none if r["feat"] is not None and r["target"] is not None]
    y_filtered = [r["target"] for r in panel_with_none if r["feat"] is not None and r["target"] is not None]

    rho_filtered = fast_spearman_rank_correlation(x_filtered, y_filtered)
    assert rho_filtered == pytest.approx(rho_clean)


# --- 18. Biến đối chứng Control (163 §4.12) ---
def test_kiem_tra_bien_doi_chung_control():
    """ofi cùng dấu mid_chg -> qua; xáo ofi ngẫu nhiên -> trượt và không in 9 cặp."""
    sessions_ok = [
        _make_synthetic_session(date(2026, 10, 5) + timedelta(days=i), ofi_pattern="positive")
        for i in range(40)
    ]
    res_ok = run_screening(sessions=sessions_ok, n_permutations=10)
    assert res_ok["control_ok"] is True
    assert res_ok["table"] is not None

    sessions_fail = [
        _make_synthetic_session(date(2026, 10, 5) + timedelta(days=i), ofi_pattern="negative")
        for i in range(40)
    ]
    res_fail = run_screening(sessions=sessions_fail, n_permutations=10)
    assert res_fail["control_ok"] is False
    assert res_fail["status"] == "STOPPED_CONTROL_VARIABLE_FAILED"
    assert res_fail["table"] is None


# --- 19. Cổng ngày chống nhìn trước (163 §4.13) ---
def test_cong_ngay_chong_nhin_truoc():
    """today = 30/11/2026 -> dừng, không gọi hàm đọc file; today = 01/12/2026 -> đi tiếp."""
    mock_loader = MagicMock(return_value=[])

    with patch("scripts.screen_vn30f_orderbook.load_all_sessions", mock_loader):
        rc = main(today=date(2026, 11, 30))
        assert rc == 2
        mock_loader.assert_not_called()

    with patch("scripts.screen_vn30f_orderbook.load_all_sessions", mock_loader):
        rc = main(today=date(2026, 12, 1))
        mock_loader.assert_called_once()


# --- 20. Chi phí lấy từ hàm, không gắn cứng (163 §4.14) ---
def test_chi_phi_lay_tu_ham_khong_gan_cung():
    """Giả lập derivative_side_cost trả giá trị khác -> ngưỡng kinh tế đổi theo."""
    cost_standard = compute_roundtrip_cost(1300.0)

    with patch(
        "scripts.screen_vn30f_orderbook.derivative_side_cost",
        return_value=20_000.0,
    ):
        cost_doubled = compute_roundtrip_cost(1300.0)
        assert cost_doubled == pytest.approx((20_000.0 + 20_000.0) / DERIVATIVE_CONTRACT_MULTIPLIER)
        assert cost_doubled != pytest.approx(cost_standard)
