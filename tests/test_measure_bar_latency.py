"""Unit tests cho scripts/measure_bar_latency.py (Brief đợt 79 Task 3).

Kiểm tra:
1. Tính phân vị bằng công thức tay độc lập (không dùng script sinh kỳ vọng).
2. Ghép cặp nến giữa collector và engine bằng dữ liệu tay.
3. Xử lý trường hợp không khớp / thiếu nến.
4. Phân loại khung giờ trong phiên.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.measure_bar_latency import (
    classify_timeframe,
    compute_percentiles,
    match_bar_latencies,
    parse_collector_closed_bars,
    parse_engine_processed_bars,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def test_compute_percentiles_hand_calculated():
    """Kiểm tra tính phân vị với kết quả tính tay chuẩn xác trên tập [10, 20, 30, 40, 50].

    n = 5:
    - p50: k = 4 * 0.5 = 2.0 -> index 2 = 30.0
    - p90: k = 4 * 0.9 = 3.6 -> index 3 (40) * 0.4 + index 4 (50) * 0.6 = 46.0
    - p99: k = 4 * 0.99 = 3.96 -> index 3 (40) * 0.04 + index 4 (50) * 0.96 = 49.6
    - max: 50.0
    """
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    p = compute_percentiles(data)
    assert abs(p["p50"] - 30.0) < 1e-9
    assert abs(p["p90"] - 46.0) < 1e-9
    assert abs(p["p99"] - 49.6) < 1e-9
    assert abs(p["max"] - 50.0) < 1e-9

    # Kiểm tra danh sách rỗng
    p_empty = compute_percentiles([])
    assert p_empty == {"p50": 0.0, "p90": 0.0, "p99": 0.0, "max": 0.0}

    # Kiểm tra danh sách 1 phần tử
    p_single = compute_percentiles([12.34])
    assert p_single["p50"] == 12.34
    assert p_single["p90"] == 12.34
    assert p_single["p99"] == 12.34
    assert p_single["max"] == 12.34


def test_match_bar_latencies_hand_calculated():
    """Kiểm tra ghép cặp nến bằng dữ liệu dựng tay."""
    dt_hpg = datetime(2026, 9, 22, 9, 15, tzinfo=TZ)
    dt_ijc = datetime(2026, 9, 22, 9, 15, tzinfo=TZ)

    c_bars = [
        {"symbol": "HPG", "bar_ts": dt_hpg, "collector_lag_s": 2.500},
        {"symbol": "IJC", "bar_ts": dt_ijc, "collector_lag_s": 15.000},
    ]

    e_bars = [
        {"symbol": "HPG", "bar_ts": dt_hpg, "engine_lag_s": 2.505},
        {"symbol": "IJC", "bar_ts": dt_ijc, "engine_lag_s": 15.012},
    ]

    matched = match_bar_latencies(c_bars, e_bars)
    assert len(matched) == 2

    hpg_match = next(m for m in matched if m["symbol"] == "HPG")
    assert abs(hpg_match["collector_lag_s"] - 2.500) < 1e-9
    assert abs(hpg_match["engine_lag_s"] - 2.505) < 1e-9
    assert abs(hpg_match["engine_diff_s"] - 0.005) < 1e-9

    ijc_match = next(m for m in matched if m["symbol"] == "IJC")
    assert abs(ijc_match["collector_lag_s"] - 15.000) < 1e-9
    assert abs(ijc_match["engine_lag_s"] - 15.012) < 1e-9
    assert abs(ijc_match["engine_diff_s"] - 0.012) < 1e-9


def test_match_bar_latencies_unmatched_handling():
    """Nến không có đối ứng giữa 2 bên -> bỏ qua không ghép, không lỗi."""
    c_bars = [
        {"symbol": "AAA", "bar_ts": datetime(2026, 9, 22, 9, 15, tzinfo=TZ), "collector_lag_s": 1.0}
    ]
    e_bars = [
        {"symbol": "AAA", "bar_ts": datetime(2026, 9, 22, 9, 20, tzinfo=TZ), "engine_lag_s": 1.5},
        {"symbol": "VNM", "bar_ts": datetime(2026, 9, 22, 9, 15, tzinfo=TZ), "engine_lag_s": 2.0},
    ]

    matched = match_bar_latencies(c_bars, e_bars)
    assert len(matched) == 0


def test_classify_timeframe_hand_calculated():
    """Kiểm tra phân loại khung giờ trong phiên."""
    assert "Mở cửa" in classify_timeframe(datetime(2026, 9, 22, 9, 15, tzinfo=TZ))
    assert "Mở cửa" in classify_timeframe(datetime(2026, 9, 22, 10, 0, tzinfo=TZ))
    assert "Giữa phiên" in classify_timeframe(datetime(2026, 9, 22, 10, 5, tzinfo=TZ))
    assert "Giữa phiên" in classify_timeframe(datetime(2026, 9, 22, 11, 30, tzinfo=TZ))
    assert "Giữa phiên" in classify_timeframe(datetime(2026, 9, 22, 13, 0, tzinfo=TZ))
    assert "Cuối phiên" in classify_timeframe(datetime(2026, 9, 22, 14, 20, tzinfo=TZ))
    assert "Cuối phiên" in classify_timeframe(datetime(2026, 9, 22, 14, 45, tzinfo=TZ))
    assert "Ngoài phiên" in classify_timeframe(datetime(2026, 9, 22, 8, 30, tzinfo=TZ))


def test_parse_logs_from_synthetic_files(tmp_path):
    """Kiểm tra đọc file log nhân tạo của collector và engine."""
    c_log = tmp_path / "bars_closed.log"
    e_log = tmp_path / "engine_alerts.log"

    # Dòng collector: nến 09:15-09:20 (ts=09:15, đóng lúc 09:20 VN = 02:20 UTC)
    # publish lúc 02:20:05 UTC -> lag_ms = 5000.0
    c_line = '2026-09-22T02:20:05.000000Z {"level": "INFO", "msg": "bars closed", "n": 2, "symbols": ["HPG", "AAA"], "lag_ms": 5000.0}\n'
    c_log.write_text(c_line, encoding="utf-8")

    # Dòng engine
    e_line_hpg = '2026-09-22T02:20:05.010000Z {"level": "INFO", "msg": "bar processed", "symbol": "HPG", "ts": "2026-09-22T09:15:00+07:00", "lag_ms": 5010.0}\n'
    e_line_aaa = '2026-09-22T02:20:05.020000Z {"level": "INFO", "msg": "bar processed", "symbol": "AAA", "ts": "2026-09-22T09:15:00+07:00", "lag_ms": 5020.0}\n'
    e_log.write_text(e_line_hpg + e_line_aaa, encoding="utf-8")

    c_parsed = parse_collector_closed_bars(c_log)
    e_parsed = parse_engine_processed_bars(e_log)

    assert len(c_parsed) == 2
    assert len(e_parsed) == 2

    matched = match_bar_latencies(c_parsed, e_parsed)
    assert len(matched) == 2

    hpg_res = next(m for m in matched if m["symbol"] == "HPG")
    assert abs(hpg_res["collector_lag_s"] - 5.0) < 1e-6
    assert abs(hpg_res["engine_lag_s"] - 5.010) < 1e-6
    assert abs(hpg_res["engine_diff_s"] - 0.010) < 1e-6
