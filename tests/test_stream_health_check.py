"""Tests for scripts/stream_health_check.py (Brief đợt 43 Task 3).

5 bài kiểm chứng §3.4:
1. Log có 3 dòng 'bars closed' trong khoảng phiên -> count = 3.
2. Log không có dòng nào trong khoảng phiên -> count = 0 (exit 2, message mở đầu 'dung:').
3. Log có dòng 'bars closed' nhưng NGOÀI khoảng phiên -> count = 0 (vẫn exit 2).
4. Log chỉ có 'backfill done' mà không có 'bars closed' -> count = 0 (exit 2, tình huống thật sáng 14/09).
5. Kiểm tra CLI qua monkeypatch sys.argv / capsys / tmp_path.
"""

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from scripts.stream_health_check import count_stream_bars_closed, main

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def test_1_stream_bars_closed_inside_session():
    """1. Log có 3 dòng 'bars closed' trong khoảng phiên sáng, mỗi dòng n=3 -> đếm đúng 9 nến, 3 dòng."""
    # 09:20 VN = 02:20 UTC, 09:25 VN = 02:25 UTC, 10:00 VN = 03:00 UTC
    sample_log = """
collector-1  | 2026-09-14T02:20:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 14.5}
collector-1  | 2026-09-14T02:25:01.234567Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 12.1}
collector-1  | 2026-09-14T03:00:00.345678Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 15.0}
"""
    res = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res.bars == 9
    assert res.lines == 3
    assert res.fallback_lines == 0


def test_2_stream_bars_closed_empty_session():
    """2. Log không có dòng nào trong khoảng phiên -> bars = 0, lines = 0."""
    sample_log = """
collector-1  | 2026-09-14T02:00:00.000000Z Token refreshed successfully
collector-1  | 2026-09-14T02:05:00.000000Z HTTP Request: GET https://api.ssi.com.vn/api/v3/trading/position "HTTP/1.1 200 OK"
"""
    res = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res.bars == 0
    assert res.lines == 0


def test_3_stream_bars_closed_outside_session_ignored():
    """3. Log có dòng 'bars closed' nhưng NGOÀI khoảng phiên -> count = 0 (bị loại)."""
    # 12:05 VN = 05:05 UTC (giữa trưa, ngoài cả phiên sáng lẫn phiên chiều)
    # 20:00 VN = 13:00 UTC (buổi tối)
    sample_log = """
collector-1  | 2026-09-14T05:05:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "lag_ms": 10.0}
collector-1  | 2026-09-14T13:00:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "lag_ms": 10.0}
"""
    res_sang = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res_sang.bars == 0 and res_sang.lines == 0
    res_chieu = count_stream_bars_closed(sample_log, session="chieu", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res_chieu.bars == 0 and res_chieu.lines == 0


def test_4_only_backfill_done_results_in_zero():
    """4. Log chỉ có 'backfill done' mà không có 'bars closed' -> count = 0 (tình huống sáng 14/09)."""
    sample_log = """
collector-1  | 2026-09-14T04:30:00.000000Z {"level": "INFO", "msg": "backfill start"}
collector-1  | 2026-09-14T04:30:05.000000Z {"level": "INFO", "msg": "backfill done", "counts": {"HPG": 27, "IJC": 27, "AAA": 27}}
"""
    res = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res.bars == 0 and res.lines == 0


def test_5_cli_exit_codes_and_messages(tmp_path, monkeypatch, capsys):
    """5. Kiểm tra CLI: có dòng -> exit 0; không có dòng -> exit 2 kèm 'dung:' mở đầu."""
    # File log có nến
    log_ok = tmp_path / "log_ok.log"
    log_ok.write_text(
        '2026-09-14T02:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 3}\n',
        encoding="utf-8",
    )

    # File log rỗng/không có bars closed
    log_fail = tmp_path / "log_fail.log"
    log_fail.write_text(
        '2026-09-14T04:30:05.000000Z {"level": "INFO", "msg": "backfill done"}\n',
        encoding="utf-8",
    )

    # Trường hợp 1: Có nến -> exit 0
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--session", "sang",
        "--date", "2026-09-14",
        "--log-file", str(log_ok),
    ])
    with pytest.raises(SystemExit) as exc1:
        main()
    assert exc1.value.code == 0
    captured1 = capsys.readouterr()
    assert "1 lan chot nen (3 nen)" in captured1.out

    # Trường hợp 2: Không có nến -> exit 2, message mở đầu bằng "dung:"
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--session", "sang",
        "--date", "2026-09-14",
        "--log-file", str(log_fail),
    ])
    with pytest.raises(SystemExit) as exc2:
        main()
    assert exc2.value.code == 2
    captured2 = capsys.readouterr()
    assert captured2.err.startswith("dung:")
    assert "0 nen" in captured2.err


def test_6_coverage_evaluation_unit():
    """6. Kiểm tra hàm evaluate_stream_health với các mức độ phủ (Brief 49 §2.3, §2.5)."""
    from scripts.stream_health_check import evaluate_stream_health

    # 1. 0 nến -> luôn CRITICAL / exit 2
    assert evaluate_stream_health(0, denom=100, min_coverage_warn=0.90, min_coverage_crit=0.50) == (2, "CRITICAL")
    assert evaluate_stream_health(0) == (2, "CRITICAL")

    # 2. Phủ 95% -> exit 0, OK
    assert evaluate_stream_health(95, denom=100, min_coverage_warn=0.90, min_coverage_crit=0.50) == (0, "OK")

    # 3. Phủ 59% -> exit 1, WARN
    assert evaluate_stream_health(59, denom=100, min_coverage_warn=0.90, min_coverage_crit=0.50) == (1, "WARN")

    # 4. Phủ 20% -> exit 2, CRITICAL
    assert evaluate_stream_health(20, denom=100, min_coverage_warn=0.90, min_coverage_crit=0.50) == (2, "CRITICAL")

    # 5. Không truyền cờ ngưỡng -> hành vi cũ (>0 nến luôn là OK / exit 0)
    assert evaluate_stream_health(59, denom=100, min_coverage_warn=None, min_coverage_crit=None) == (0, "OK")


def test_7_cli_with_coverage_flags(tmp_path, monkeypatch, capsys):
    """7. Kiểm tra CLI với cờ coverage và expected-bars mock."""
    # Tạo log với 59 dòng bars closed
    log_file = tmp_path / "log_warn.log"
    content = "\n".join(
        f'2026-09-17T02:20:{i%60:02d}.000000Z {{"level": "INFO", "msg": "bars closed", "n": 1}}'
        for i in range(59)
    )
    log_file.write_text(content, encoding="utf-8")

    # Phủ 59/100 = 59% -> exit 1, in WARN
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--session", "sang",
        "--date", "2026-09-17",
        "--log-file", str(log_file),
        "--expected-bars", "100",
        "--min-coverage-warn", "0.90",
        "--min-coverage-crit", "0.50",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "59.0%" in out


def test_8_resolve_target_session_midday_friday():
    """8. Giả lập mốc 12:14 thứ Sáu -> chọn phiên sáng thứ Sáu (Brief 49 §2.6)."""
    from datetime import datetime

    from scripts.stream_health_check import resolve_target_session

    dt_friday_noon = datetime(2026, 9, 18, 12, 14, 0, tzinfo=TZ_VN)
    res = resolve_target_session(dt_friday_noon)
    assert res == (date(2026, 9, 18), "sang"), f"Kỳ vọng (2026-09-18, 'sang'), nhận: {res}"


def test_9_resolve_target_session_saturday_ignored(monkeypatch, capsys):
    """9. Giả lập mốc 10:00 thứ Bảy -> trả về None và CLI exit 0 với thông điệp bỏ qua (Brief 49 §2.6)."""
    from datetime import datetime

    from scripts.stream_health_check import resolve_target_session

    dt_sat_morning = datetime(2026, 9, 19, 10, 0, 0, tzinfo=TZ_VN)
    res = resolve_target_session(dt_sat_morning)
    assert res is None

    # Kiểm tra CLI khi now là thứ Bảy
    monkeypatch.setattr("scripts.stream_health_check.datetime", type("MockDT", (), {
        "now": lambda tz=None: dt_sat_morning,
        "combine": datetime.combine,
        "fromisoformat": datetime.fromisoformat,
    }))
    monkeypatch.setattr("sys.argv", ["stream_health_check.py"])

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("bo qua:")


def test_10_is_session_ended_unit():
    """10. Kiểm tra hàm is_session_ended (Brief 50 Task 1.1)."""
    from datetime import datetime

    from scripts.stream_health_check import is_session_ended

    dt_noon = datetime(2026, 9, 18, 12, 0, 0, tzinfo=TZ_VN)
    today = date(2026, 9, 18)
    yesterday = date(2026, 9, 17)
    tomorrow = date(2026, 9, 19)

    # 1. Hôm nay lúc 12:00 -> phiên chiều chưa kết thúc (15:05)
    assert is_session_ended(today, "chieu", dt_noon) is False

    # 2. Hôm nay lúc 12:00 -> phiên sáng ĐÃ kết thúc (11:30)
    assert is_session_ended(today, "sang", dt_noon) is True

    # 3. Hôm nay lúc 12:00 -> cả ngày chưa kết thúc (cần phiên chiều xong)
    assert is_session_ended(today, None, dt_noon) is False

    # 4. Hôm qua -> phiên chiều ĐÃ kết thúc
    assert is_session_ended(yesterday, "chieu", dt_noon) is True

    # 5. Ngày mai -> chưa kết thúc
    assert is_session_ended(tomorrow, "sang", dt_noon) is False


def test_11_cli_unended_session_scenarios(monkeypatch, capsys, tmp_path):
    """11. Kiểm chứng CLI với các trường hợp phiên chưa/đã kết thúc (Brief 50 §1.2)."""
    from datetime import datetime

    dt_noon = datetime(2026, 9, 18, 12, 0, 0, tzinfo=TZ_VN)

    monkeypatch.setattr("scripts.stream_health_check.datetime", type("MockDT", (), {
        "now": lambda tz=None: dt_noon,
        "combine": datetime.combine,
        "fromisoformat": datetime.fromisoformat,
    }))

    dummy_log = tmp_path / "dummy.log"
    dummy_log.write_text(
        '2026-09-18T02:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 10}\n'
        '2026-09-17T07:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 10}\n',
        encoding="utf-8",
    )

    # Case 1: --date <hôm nay> --session chieu chạy lúc 12:00 -> bo qua, exit 0
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-18",
        "--session", "chieu",
        "--log-file", str(dummy_log),
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("bo qua:")
    assert "phien chieu" in out

    # Case 2: --date <hôm nay> (cả ngày) chạy lúc 12:00 -> bo qua, exit 0
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-18",
        "--log-file", str(dummy_log),
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("bo qua:")
    assert "ca ngay" in out

    # Case 3: --date <hôm nay> --session sang chạy lúc 12:00 -> kiểm bình thường (sáng đã xong)
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-18",
        "--session", "sang",
        "--log-file", str(dummy_log),
        "--expected-bars", "1",
        "--min-coverage-warn", "0.90",
        "--min-coverage-crit", "0.50",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert not out.startswith("bo qua:")

    # Case 4: --date <hôm qua> --session chieu -> kiểm bình thường
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--log-file", str(dummy_log),
        "--expected-bars", "1",
        "--min-coverage-warn", "0.90",
        "--min-coverage-crit", "0.50",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert not out.startswith("bo qua:")


def test_12_persistent_file_only_uses_file_source(tmp_path, monkeypatch, capsys):
    """12. Brief 52 Task 1.4: Có file bền, không có docker log -> đếm đúng, in nguồn file."""
    from scripts import stream_health_check

    p_file = tmp_path / "bars_closed.log"
    p_file.write_text(
        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
        '2026-09-17T06:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
        '2026-09-17T06:30:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(stream_health_check, "fetch_docker_collector_logs", lambda: "")
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--persistent-log", str(p_file),
    ])
    with pytest.raises(SystemExit) as exc:
        stream_health_check.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "co 3 lan chot nen" in out
    assert "[nguon: file]" in out


def test_13_no_persistent_file_falls_back_to_log_source(tmp_path, monkeypatch, capsys):
    """13. Brief 52 Task 1.4: Không có file bền, có log -> đếm đúng như cũ, in nguồn log."""
    from scripts import stream_health_check

    non_existent = tmp_path / "bars_closed_missing.log"
    docker_log = (
        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
        '2026-09-17T06:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
    )
    monkeypatch.setattr(stream_health_check, "fetch_docker_collector_logs", lambda: docker_log)
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--persistent-log", str(non_existent),
    ])
    with pytest.raises(SystemExit) as exc:
        stream_health_check.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "co 2 lan chot nen" in out
    assert "[nguon: log]" in out


def test_14_both_sources_exist_prefers_persistent_file(tmp_path, monkeypatch, capsys):
    """14. Brief 52 Task 1.4: Có cả hai nguồn -> ưu tiên file bền, chọn con số từ file (5 nến thay vì 2 nến từ log)."""
    from scripts import stream_health_check

    p_file = tmp_path / "bars_closed.log"
    p_file.write_text(
        "".join(
            f'2026-09-17T06:1{i}:00.000000Z {{"level": "INFO", "msg": "bars closed", "n": 1}}\n'
            for i in range(5)
        ),
        encoding="utf-8",
    )
    docker_log = (
        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
        '2026-09-17T06:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
    )
    monkeypatch.setattr(stream_health_check, "fetch_docker_collector_logs", lambda: docker_log)
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--persistent-log", str(p_file),
    ])
    with pytest.raises(SystemExit) as exc:
        stream_health_check.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    # Con số từ file bền (5) được chọn, không phải con số từ log (2)
    assert "co 5 lan chot nen" in out
    assert "[nguon: file]" in out


def test_15_persistent_file_without_evidence_falls_back_to_log(tmp_path, monkeypatch, capsys):
    """15. Hoi quy 18/09: file ben TON TAI nhung khong chua dong 'bars closed' nao.

    That su da xay ra: nhanh du phong ghi vao Path("logs") tren host khien pytest
    do 559 dong alert TEST (SYM_B, ENGT) vao dung file ma stream_health_check lay
    lam nguon uu tien. Ket qua: phien sang 15/09 von 93,8% bi bao "0 nen / exit 2".

    Luat dung: file ben chi duoc uu tien khi no THUC SU chua bang chung chot nen.
    Khong thi roi ve log container.
    """
    from scripts import stream_health_check

    p_file = tmp_path / "bars_closed.log"
    p_file.write_text(
        '2026-09-17T06:00:00.000000Z {"level": "INFO", "msg": "backfill done"}\n'
        '2026-09-17T06:05:00.000000Z {"level": "CRITICAL", "msg": "khong co dong vi the", "symbol": "ENGT"}\n',
        encoding="utf-8",
    )
    docker_log = (
        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
        '2026-09-17T06:20:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n'
    )
    monkeypatch.setattr(stream_health_check, "fetch_docker_collector_logs", lambda: docker_log)
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--persistent-log", str(p_file),
    ])
    with pytest.raises(SystemExit) as exc:
        stream_health_check.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "co 2 lan chot nen" in out
    assert "[nguon: log]" in out


def test_16_resolve_target_session_receives_holidays():
    """16. Brief 55 Task 1.1b: resolve_target_session nhận holidays và bỏ qua ngày lễ giữa tuần."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from scripts.stream_health_check import resolve_target_session

    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    # Ngày 02/09/2026 là thứ Tư (ngày thường trong tuần)
    dt_holiday_noon = datetime(2026, 9, 2, 12, 0, 0, tzinfo=tz_vn)
    holidays = {date(2026, 9, 2)}

    # Gọi với holidays chứa ngày đó -> phải trả về None
    res = resolve_target_session(dt_holiday_noon, holidays=holidays)
    assert res is None, f"Kỳ vọng None vì là ngày lễ giữa tuần, nhận: {res}"

    # Gọi không có holidays -> trả về phiên sáng (lỗi cũ trước khi sửa)
    res_no_holidays = resolve_target_session(dt_holiday_noon, holidays=None)
    assert res_no_holidays == (date(2026, 9, 2), "sang")


def test_17_explicit_date_past_saturday_ignored(monkeypatch, capsys):
    """17. Brief 55 Task 1.1: Truyền tường minh một thứ Bảy đã qua -> bỏ qua, exit 0."""
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-12",
        "--session", "sang",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "bo qua: 2026-09-12 la ngay nghi" in out


def test_18_explicit_date_weekday_holiday_ignored(monkeypatch, capsys):
    """18. Brief 55 Task 1.1: Truyền tường minh ngày lễ giữa tuần (01/09 thứ Ba) -> bỏ qua, exit 0."""
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-01",
        "--session", "sang",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "bo qua: 2026-09-01 la ngay nghi" in out


def test_19_explicit_date_past_trading_day_not_ignored(monkeypatch, capsys, tmp_path):
    """19. Brief 55 Task 1.3: Truyền ngày giao dịch đã qua (17/09 thứ Năm) -> đo bình thường, không bỏ qua."""
    dummy_log = tmp_path / "dummy.log"
    dummy_log.write_text(
        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", [
        "stream_health_check.py",
        "--date", "2026-09-17",
        "--session", "chieu",
        "--log-file", str(dummy_log),
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert not out.startswith("bo qua:")
    assert "co 1 lan chot nen" in out


def test_20_batch_aggregation_single_line_multiple_bars():
    """20. Brief 70 Task 3.2.1: Gộp lô: 1 dòng duy nhất 'n': 3 -> bars=3 nến, lines=1 dòng log."""
    sample_log = 'collector-1  | 2026-09-14T02:20:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"]}\n'
    res = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res.bars == 3
    assert res.lines == 1
    assert res.fallback_lines == 0


def test_21_fallback_when_n_missing_or_invalid():
    """21. Brief 70 Task 3.2.2: Dự phòng khi thiếu n hoặc không đọc được JSON -> tính 1 nến/dòng và đếm fallback."""
    sample_log = """
collector-1  | 2026-09-14T02:20:00.000000Z {"level": "INFO", "msg": "bars closed"}
collector-1  | 2026-09-14T02:25:00.000000Z {"level": "INFO", "msg": "bars closed", "n": "invalid"}
collector-1  | 2026-09-14T02:30:00.000000Z collector-1 | 2026-09-14T02:30:00Z bars closed non-json text
"""
    res = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert res.bars == 3
    assert res.lines == 3
    assert res.fallback_lines == 3


def test_22_fetch_docker_collector_logs_respects_compose_project_name(monkeypatch):
    """22. Brief 126 Việc 1: fetch_docker_collector_logs dùng get_container_name('collector') khi fallback."""
    from scripts.stream_health_check import fetch_docker_collector_logs

    called_cmds = []

    def mock_run(cmd, **kwargs):
        called_cmds.append(cmd)
        if cmd[0:3] == ["docker", "compose", "logs"]:
            return type("SubprocessResult", (), {"returncode": 1, "stdout": "", "stderr": "error"})()
        if cmd[0:3] == ["docker", "logs", "-t"]:
            return type("SubprocessResult", (), {"returncode": 0, "stdout": "dummy logs", "stderr": ""})()
        return type("SubprocessResult", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "trading")
    monkeypatch.setattr("subprocess.run", mock_run)

    logs = fetch_docker_collector_logs()
    assert logs == "dummy logs"
    assert len(called_cmds) == 2
    assert called_cmds[1] == ["docker", "logs", "-t", "trading-collector-1"]

