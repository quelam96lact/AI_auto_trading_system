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
    """1. Log có 3 dòng 'bars closed' trong khoảng phiên sáng -> đếm đúng 3."""
    # 09:20 VN = 02:20 UTC, 09:25 VN = 02:25 UTC, 10:00 VN = 03:00 UTC
    sample_log = """
collector-1  | 2026-09-14T02:20:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 14.5}
collector-1  | 2026-09-14T02:25:01.234567Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 12.1}
collector-1  | 2026-09-14T03:00:00.345678Z {"level": "INFO", "msg": "bars closed", "n": 3, "symbols": ["HPG", "IJC", "AAA"], "lag_ms": 15.0}
"""
    cnt = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert cnt == 3


def test_2_stream_bars_closed_empty_session():
    """2. Log không có dòng nào trong khoảng phiên -> count = 0."""
    sample_log = """
collector-1  | 2026-09-14T02:00:00.000000Z Token refreshed successfully
collector-1  | 2026-09-14T02:05:00.000000Z HTTP Request: GET https://api.ssi.com.vn/api/v3/trading/position "HTTP/1.1 200 OK"
"""
    cnt = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert cnt == 0


def test_3_stream_bars_closed_outside_session_ignored():
    """3. Log có dòng 'bars closed' nhưng NGOÀI khoảng phiên -> count = 0 (bị loại)."""
    # 12:05 VN = 05:05 UTC (giữa trưa, ngoài cả phiên sáng lẫn phiên chiều)
    # 20:00 VN = 13:00 UTC (buổi tối)
    sample_log = """
collector-1  | 2026-09-14T05:05:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "lag_ms": 10.0}
collector-1  | 2026-09-14T13:00:00.123456Z {"level": "INFO", "msg": "bars closed", "n": 3, "lag_ms": 10.0}
"""
    cnt_sang = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert cnt_sang == 0
    cnt_chieu = count_stream_bars_closed(sample_log, session="chieu", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert cnt_chieu == 0


def test_4_only_backfill_done_results_in_zero():
    """4. Log chỉ có 'backfill done' mà không có 'bars closed' -> count = 0 (tình huống sáng 14/09)."""
    sample_log = """
collector-1  | 2026-09-14T04:30:00.000000Z {"level": "INFO", "msg": "backfill start"}
collector-1  | 2026-09-14T04:30:05.000000Z {"level": "INFO", "msg": "backfill done", "counts": {"HPG": 27, "IJC": 27, "AAA": 27}}
"""
    cnt = count_stream_bars_closed(sample_log, session="sang", check_date=date(2026, 9, 14), tz=TZ_VN)
    assert cnt == 0


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
    assert "OK: phien sang ngay 2026-09-14 co 1 lan chot nen" in captured1.out

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


