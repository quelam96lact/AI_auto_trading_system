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
