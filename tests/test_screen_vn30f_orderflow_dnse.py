"""Test suite cho scripts/screen_vn30f_orderflow_dnse.py (Brief đợt 186 Tests 8..13)."""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import scripts.screen_vn30f_orderflow as screen_182
import scripts.screen_vn30f_orderflow_dnse as screen_dnse
from scripts.fetch_dnse_vn30f_trades import front_month_symbol
from scripts.screen_vn30f_orderbook import IS_START_DATE
from scripts.screen_vn30f_orderflow import (
    OrderFlowEvent,
    _session_grid_5m,
    build_footprint_bars_and_trades,
)
from trading.calendar_vn import TZ


def _generate_canonical_session_rows(
    d: date,
    p_base: float = 1800.0,
    delta_sign: int = 1,
    n_bars: int = 48,
    missing_cont: int = 0,
    base_qtty: int = 5,
) -> list[dict[str, Any]]:
    """Tạo danh sách các dòng DNSE chuẩn cho phiên d sử dụng chính xác lưới 48 nến _session_grid_5m."""
    grid = _session_grid_5m(d)
    rows: list[dict[str, Any]] = []
    tv = 0

    for idx, block_id, t_start, t_end in grid[:n_bars]:
        # Nếu có chèn khoảng thiếu khối lượng trong phiên liên tục (tại nến 5)
        if idx == 5 and missing_cont > 0:
            tv += missing_cont

        t1_str = (t_start + timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S.000")
        t2_str = (t_start + timedelta(seconds=50)).strftime("%Y-%m-%d %H:%M:%S.000")

        # Thay đổi return và delta theo idx để tránh ConstantInputWarning (Spearman rho = nan)
        p_diff = 0.5 + float(idx % 8) * 0.5
        q1 = base_qtty + (idx % 8)
        q2 = base_qtty

        if delta_sign > 0:
            # BUY: delta > 0 và close > open (đồng dấu dương)
            tv += q1
            rows.append({
                "match_price": p_base,
                "match_qtty": q1,
                "side": "BUY",
                "total_volume_traded": tv,
                "time": t1_str,
            })
            tv += q2
            rows.append({
                "match_price": p_base + p_diff,
                "match_qtty": q2,
                "side": "BUY",
                "total_volume_traded": tv,
                "time": t2_str,
            })
        else:
            # SELL: delta < 0 nhưng close > open (ngược dấu âm)
            tv += q1
            rows.append({
                "match_price": p_base,
                "match_qtty": q1,
                "side": "SELL",
                "total_volume_traded": tv,
                "time": t1_str,
            })
            tv += q2
            rows.append({
                "match_price": p_base + p_diff,
                "match_qtty": q2,
                "side": "SELL",
                "total_volume_traded": tv,
                "time": t2_str,
            })

    return rows


# --- Test 8: Chuyển dòng DNSE sang tin TRADE SSI ---
def test_8_dnse_row_to_message():
    """BUY -> B, SELL -> S, UNSPECIFIED -> U; giờ cắt mili giây; ba dòng tự dựng cho delta nến đúng bằng tay; dòng U không vào delta."""
    row_buy = {
        "match_price": 1805.2,
        "match_qtty": 2,
        "side": "BUY",
        "time": "2026-04-01 09:05:12.345",
    }
    row_sell = {
        "match_price": 1805.0,
        "match_qtty": 3,
        "side": "SELL",
        "time": "2026-04-01 09:05:15.890",
    }
    row_u = {
        "match_price": 1805.1,
        "match_qtty": 5,
        "side": "UNSPECIFIED",
        "time": "2026-04-01 09:05:20.123",
    }

    msg_buy = screen_dnse.dnse_row_to_message(row_buy)
    msg_sell = screen_dnse.dnse_row_to_message(row_sell)
    msg_u = screen_dnse.dnse_row_to_message(row_u)

    assert msg_buy["side"] == "B"
    assert msg_buy["trading_time"] == "2026-04-01 09:05:12"
    assert msg_buy["price"] == 1805.2
    assert msg_buy["quantity"] == 2

    assert msg_sell["side"] == "S"
    assert msg_sell["trading_time"] == "2026-04-01 09:05:15"
    assert msg_sell["quantity"] == 3

    assert msg_u["side"] == "U"
    assert msg_u["trading_time"] == "2026-04-01 09:05:20"

    # Đưa vào build_footprint_bars_and_trades để kiểm tra delta tính tay
    d = date(2026, 4, 1)
    bars, _trades, _stats = build_footprint_bars_and_trades(
        [msg_buy, msg_sell, msg_u],
        session_date=d,
    )

    # Bar 1 là 09:05 - 09:10
    bar_1 = bars[1]
    assert bar_1.trade_count == 2  # Dòng U bị loại, chỉ còn BUY và SELL
    assert bar_1.buy == 2.0
    assert bar_1.sell == 3.0
    # Delta bằng tay: buy (2) - sell (3) = -1.0; dòng U không vào delta
    assert bar_1.delta == -1.0


# --- Test 9: Điều kiện hợp lệ của phiên ---
def test_9_session_validity(tmp_path: Path):
    """Thiếu khối lượng liên tục 0.6% -> không hợp lệ; 0.4% -> hợp lệ; < 44 nến -> không hợp lệ; file cắt cụt -> không hợp lệ, không sập."""
    sym = "41I1G4000"
    dir_sym = tmp_path / sym
    dir_sym.mkdir(parents=True, exist_ok=True)

    def _create_session_file(fpath: Path, rows: list[dict[str, Any]]) -> None:
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    # 1. Thiếu KL liên tục 0.6%: base_qtty=100 -> tổng ~9600. missing_cont=60 -> 60 / ~9660 ~= 0.0062 > 0.005
    f_06 = dir_sym / "2026-04-01.jsonl.gz"
    rows_06 = _generate_canonical_session_rows(date(2026, 4, 1), n_bars=48, missing_cont=60, base_qtty=100)
    _create_session_file(f_06, rows_06)

    # 2. Thiếu KL liên tục 0.4%: base_qtty=100. missing_cont=35 -> 35 / ~9635 ~= 0.0036 <= 0.005
    f_04 = dir_sym / "2026-04-02.jsonl.gz"
    rows_04 = _generate_canonical_session_rows(date(2026, 4, 2), n_bars=48, missing_cont=35, base_qtty=100)
    _create_session_file(f_04, rows_04)

    # 3. Phiên thưa: chỉ có 40 nến (< 44)
    f_sparse = dir_sym / "2026-04-03.jsonl.gz"
    rows_sparse = _generate_canonical_session_rows(date(2026, 4, 3), n_bars=40, missing_cont=0)
    _create_session_file(f_sparse, rows_sparse)

    # 4. File cắt cụt / hỏng
    f_corrupt = dir_sym / "2026-04-06.jsonl.gz"
    with open(f_corrupt, "wb") as f:
        f.write(b"\x1f\x8b\x08\x00_NOT_A_VALID_GZIP_CONTENT_CORRUPTED")

    sessions = screen_dnse.load_dnse_sessions(
        data_dir=tmp_path,
        start=date(2026, 4, 1),
        end=date(2026, 4, 6),
    )

    s_map = {s.session_date: s for s in sessions}

    # Kiểm 0.6%
    s_06 = s_map[date(2026, 4, 1)]
    assert not s_06.is_valid
    assert s_06.invalid_reason is not None and "thiếu KL liên tục" in s_06.invalid_reason

    # Kiểm 0.4%
    s_04 = s_map[date(2026, 4, 2)]
    assert s_04.is_valid
    assert s_04.invalid_reason is None

    # Kiểm phiên thưa
    s_sparse = s_map[date(2026, 4, 3)]
    assert not s_sparse.is_valid
    assert s_sparse.invalid_reason is not None and "phiên thưa" in s_sparse.invalid_reason

    # Kiểm file hỏng
    s_corrupt = s_map[date(2026, 4, 6)]
    assert not s_corrupt.is_valid
    assert s_corrupt.invalid_reason == "file hỏng"


# --- Test 10: Tái sử dụng nguyên vẹn hàm từ 182 ---
def test_10_reuse_182_functions():
    """Kiểm tra đối tượng hàm được import nguyên vẹn, không viết lại hay chép lại."""
    assert screen_dnse.build_price_lookup is screen_182.build_price_lookup
    assert screen_dnse.detect_e1_events is screen_182.detect_e1_events
    assert screen_dnse.detect_e2_events is screen_182.detect_e2_events
    assert screen_dnse.detect_e3_events is screen_182.detect_e3_events
    assert screen_dnse.calculate_event_targets is screen_182.calculate_event_targets
    assert screen_dnse.filter_non_overlapping_events is screen_182.filter_non_overlapping_events
    assert screen_dnse.block_bootstrap_p_value is screen_182.block_bootstrap_p_value
    assert screen_dnse.check_control_variable_orderflow is screen_182.check_control_variable_orderflow
    assert screen_dnse.compute_economic_hurdle is screen_182.compute_economic_hurdle
    assert screen_dnse.evaluate_pair_criteria is screen_182.evaluate_pair_criteria


# --- Test 11: Logic phán quyết CHÍNH và LẶP LẠI ---
def test_11_verdict_logic():
    """Cặp qua CHÍNH trượt LẶP LẠI -> TRƯỢT; qua cả hai -> ĐẠT; k=2, p=0.03 -> TRƯỢT; hurdle LẶP LẠI cố định từ CHÍNH."""
    # Giả lập sự kiện độc lập
    dummy_event = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=date(2026, 7, 1),
        block_id="morning",
        bar_idx=10,
        t_end=datetime(2026, 7, 1, 9, 50, 0, tzinfo=TZ),
        close=1800.0,
        exit_price=1810.0,
        y=5.0,
    )
    events = [dummy_event] * 50

    hurdle_main = 2.5
    different_hurdle_repeat = 6.0  # Nếu tính lại từ giá repeat thì ra 6.0

    # 1. Với k = 2, ngưỡng alpha = 0.05 / 2 = 0.025.
    # Nếu p_val = 0.03: 0.03 > 0.025 -> TRƯỢT
    res_k2_p03 = screen_dnse.evaluate_repeat_pair(
        events,
        hurdle_main=hurdle_main,
        p_val=0.03,
        k_passed=2,
    )
    assert not res_k2_p03["passed"]
    assert res_k2_p03["alpha_threshold"] == 0.025

    # Nếu p_val = 0.02: 0.02 < 0.025 và mean_y (5.0) >= hurdle_main (2.5) -> ĐẠT
    res_k2_p02 = screen_dnse.evaluate_repeat_pair(
        events,
        hurdle_main=hurdle_main,
        p_val=0.02,
        k_passed=2,
    )
    assert res_k2_p02["passed"]
    assert res_k2_p02["hurdle"] == hurdle_main  # Dùng hurdle của CHÍNH

    # Nếu dùng hurdle khác từ giá LẶP LẠI (6.0), mean_y (5.0) < 6.0 -> sẽ trượt
    assert res_k2_p02["mean_y"] < different_hurdle_repeat


def test_11b_repeat_truot_khi_duoi_hurdle_chinh():
    """p rất nhỏ nhưng trung bình y dưới hurdle CHÍNH -> LẶP LẠI TRƯỢT."""
    ev = OrderFlowEvent(
        event_type="E1",
        direction=1,
        session_id=date(2026, 7, 1),
        block_id="morning",
        bar_idx=10,
        t_end=datetime(2026, 7, 1, 9, 50, 0, tzinfo=TZ),
        close=1800.0,
        exit_price=1801.0,
        y=1.0,
    )
    res = screen_dnse.evaluate_repeat_pair([ev] * 50, hurdle_main=2.5, p_val=0.0001, k_passed=1)
    assert res["cond_stat"]
    assert not res["cond_hurdle"]
    assert not res["passed"]


# --- Test 12: Biến đối chứng hỏng trả về mã 4 ---
def test_12_control_variable_failure(tmp_path: Path):
    """Delta ngược dấu close - open -> return 4, không in bảng kết quả."""
    # Sinh 41 phiên CHÍNH và 31 phiên LẶP LẠI để đủ số phiên nhưng đối chứng hỏng
    all_dates = [
        date(2026, 3, 25) + timedelta(days=i) for i in range(41)
    ] + [
        date(2026, 7, 1) + timedelta(days=i) for i in range(31)
    ]

    for d in all_dates:
        d_sym = front_month_symbol(d)
        p_dir = tmp_path / d_sym
        p_dir.mkdir(parents=True, exist_ok=True)
        fpath = p_dir / f"{d.isoformat()}.jsonl.gz"

        # Sinh phiên 48 nến nhưng delta_sign = -1 (delta < 0, close > open -> rho âm)
        rows = _generate_canonical_session_rows(d, p_base=1800.0, delta_sign=-1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    res = screen_dnse.run_dnse_screening(data_dir=tmp_path)
    assert res["exit_code"] == 4


# --- Test 13: Đầu-cuối ---
def test_13_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    """Đầu-cuối: 41 CHÍNH + 31 LẶP LẠI hợp lệ; 1 phiên thưa; 1 phiên thiếu KL; 1 file 2026-09-25 hỏng. main() return 0, file 2026-09-25 không bị mở."""
    # Danh sách các ngày CHÍNH (41 ngày)
    main_dates = [date(2026, 3, 25) + timedelta(days=i) for i in range(41)]
    # Danh sách các ngày LẶP LẠI (31 ngày)
    repeat_dates = [date(2026, 7, 1) + timedelta(days=i) for i in range(31)]

    # Tạo 41 phiên CHÍNH và 31 phiên LẶP LẠI hợp lệ
    for d in main_dates:
        sym = front_month_symbol(d)
        dir_sym = tmp_path / sym
        dir_sym.mkdir(parents=True, exist_ok=True)
        fpath = dir_sym / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1800.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    for d in repeat_dates:
        sym = front_month_symbol(d)
        dir_sym = tmp_path / sym
        dir_sym.mkdir(parents=True, exist_ok=True)
        fpath = dir_sym / f"{d.isoformat()}.jsonl.gz"
        rows = _generate_canonical_session_rows(d, p_base=1850.0, delta_sign=1, n_bars=48)
        with gzip.open(fpath, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    # 1 phiên thưa (active_bars = 10 < 44) vào ngày 2026-05-10 (trong CHÍNH)
    d_sparse = date(2026, 5, 10)
    sym_sparse = front_month_symbol(d_sparse)
    f_sparse = tmp_path / sym_sparse / f"{d_sparse.isoformat()}.jsonl.gz"
    rows_sparse = _generate_canonical_session_rows(d_sparse, p_base=1800.0, delta_sign=1, n_bars=10)
    with gzip.open(f_sparse, "wt", encoding="utf-8") as f:
        for r in rows_sparse:
            f.write(json.dumps(r) + "\n")

    # 1 phiên thiếu KL liên tục (ratio > 0.5%) vào ngày 2026-05-11 (trong CHÍNH)
    d_cont = date(2026, 5, 11)
    sym_cont = front_month_symbol(d_cont)
    f_cont = tmp_path / sym_cont / f"{d_cont.isoformat()}.jsonl.gz"
    rows_cont = _generate_canonical_session_rows(d_cont, p_base=1800.0, delta_sign=1, n_bars=48, missing_cont=100)
    with gzip.open(f_cont, "wt", encoding="utf-8") as f:
        for r in rows_cont:
            f.write(json.dumps(r) + "\n")

    # 1 file ngày 2026-09-25 cố ý hỏng
    d_is = IS_START_DATE
    sym_is = front_month_symbol(d_is)
    dir_is = tmp_path / sym_is
    dir_is.mkdir(parents=True, exist_ok=True)
    f_is = dir_is / f"{d_is.isoformat()}.jsonl.gz"
    with open(f_is, "wb") as f:
        f.write(b"CORRUPTED_NOT_A_VALID_GZIP_FILE")

    # Spy hàm mở file gzip.open
    real_gzip_open = gzip.open
    opened_files = []

    def spy_gzip_open(filename, *args, **kwargs):
        opened_files.append(str(filename))
        return real_gzip_open(filename, *args, **kwargs)

    monkeypatch.setattr(gzip, "open", spy_gzip_open)

    # Chạy main
    ret = screen_dnse.main(["--data-dir", str(tmp_path)])
    assert ret == 0

    # Kiểm tra loader khi khoảng ngày bao gồm IS_START_DATE (2026-09-25)
    screen_dnse.load_dnse_sessions(data_dir=str(tmp_path), start=date(2026, 9, 20), end=date(2026, 9, 25))

    # Kiểm tra spy: file 2026-09-25 KHÔNG bao giờ bị mở
    for path_str in opened_files:
        assert "2026-09-25" not in path_str

    captured = capsys.readouterr()
    # Kiểm tra bảng CHÍNH có đủ 6 cặp
    for ev in ("E1", "E2", "E3"):
        for h in (15, 30):
            assert f"{ev}_H{h}" in captured.out

    # Kiểm tra thông báo hai phiên không hợp lệ kèm lý do
    assert "phiên thưa" in captured.out
    assert "thiếu KL liên tục" in captured.out
