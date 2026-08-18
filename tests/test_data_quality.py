from datetime import date

import pytest

from trading.data_quality import (
    evaluate_symbol_completeness,
    find_missing_dates,
    infer_trading_sessions,
    is_dirty_bar_dict,
)


def test_infer_trading_sessions_excludes_holidays_and_weekends():
    # Giả lập: ngày thường có 800 mã, ngày lễ/chạy thử có 5 mã
    daily_counts = {
        date(2026, 1, 5): 850,  # Thứ 2: phiên thật
        date(2026, 1, 6): 860,  # Thứ 3: phiên thật
        date(2026, 1, 7): 5,    # Thứ 4: ngày test / nghỉ lễ
        date(2026, 1, 8): 870,  # Thứ 5: phiên thật
        date(2026, 1, 9): 865,  # Thứ 6: phiên thật
    }
    sessions = infer_trading_sessions(daily_counts, min_symbols=100)
    assert sessions == [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    assert date(2026, 1, 7) not in sessions


def test_late_listed_symbol_not_counted_missing_before_listing():
    # Toàn bộ vũ trụ giao dịch từ 2016 đến 2026 (5 ngày mẫu)
    trading_sessions = [
        date(2016, 1, 4),
        date(2016, 1, 5),
        date(2020, 1, 2),
        date(2020, 1, 3),
        date(2020, 1, 6),
    ]
    # Mã BAF chỉ niêm yết từ 2020-01-02 đến 2020-01-06 (3 phiên)
    res = evaluate_symbol_completeness(
        symbol="BAF",
        first_date=date(2020, 1, 2),
        last_date=date(2020, 1, 6),
        total_bars=3,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2020, 1, 6),
    )
    assert res.expected_in_lifespan == 3
    assert res.missing_middle == 0
    assert res.missing_tail == 0
    assert res.dirty_bars == 0


def test_delisted_symbol_counts_as_missing_tail_not_middle():
    trading_sessions = [
        date(2020, 1, 2),
        date(2020, 1, 3),
        date(2020, 1, 6),
        date(2020, 1, 7),
        date(2020, 1, 8),
    ]
    # Mã ROS hủy niêm yết / ngừng giao dịch sau 2020-01-03
    res = evaluate_symbol_completeness(
        symbol="ROS",
        first_date=date(2020, 1, 2),
        last_date=date(2020, 1, 3),
        total_bars=2,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2020, 1, 8),
    )
    assert res.expected_in_lifespan == 2
    assert res.missing_middle == 0
    # Thiếu ở đuôi: 2020-01-06, 07, 08 -> 3 phiên
    assert res.missing_tail == 3


def test_gap_in_middle_counts_as_missing_middle():
    trading_sessions = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    # Mã HPG có mặt ngày 5, 6, 9 (thiếu ngày 7, 8 ở giữa)
    res = evaluate_symbol_completeness(
        symbol="HPG",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 9),
        total_bars=3,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2026, 1, 9),
    )
    assert res.expected_in_lifespan == 5
    assert res.missing_middle == 2
    assert res.missing_tail == 0


def test_dirty_bars_counted_separately():
    trading_sessions = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    # Mã FLC có 3 bar nhưng 1 bar rác
    res = evaluate_symbol_completeness(
        symbol="FLC",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 7),
        total_bars=3,
        dirty_bars=1,
        trading_sessions=trading_sessions,
        as_of_date=date(2026, 1, 7),
    )
    assert res.total_bars == 3
    assert res.dirty_bars == 1
    assert res.missing_middle == 0
    assert res.missing_tail == 0


def test_find_missing_dates_detail():
    trading_sessions = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    # Có mặt 5, 8
    present = {date(2026, 1, 5), date(2026, 1, 8)}
    middle_missing, tail_missing = find_missing_dates(
        present_dates=present,
        trading_sessions=trading_sessions,
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 8),
        as_of_date=date(2026, 1, 9),
    )
    assert middle_missing == [date(2026, 1, 6), date(2026, 1, 7)]
    assert tail_missing == [date(2026, 1, 9)]


def test_empty_symbol_handled_cleanly():
    trading_sessions = [date(2026, 1, 5), date(2026, 1, 6)]
    res = evaluate_symbol_completeness(
        symbol="EMPTY",
        first_date=None,
        last_date=None,
        total_bars=0,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2026, 1, 6),
    )
    assert res.expected_in_lifespan == 0
    assert res.missing_middle == 0
    assert res.missing_tail == 2


def test_is_dirty_bar_dict():
    # OHLC <= 0
    assert is_dirty_bar_dict({"open": 0, "high": 10, "low": 5, "close": 8}) is True
    assert is_dirty_bar_dict({"open": 10, "high": -1, "low": 5, "close": 8}) is True
    assert is_dirty_bar_dict({"open": 10, "high": 10, "low": 0, "close": 8}) is True
    assert is_dirty_bar_dict({"open": 10, "high": 10, "low": 5, "close": 0}) is True
    assert is_dirty_bar_dict({"open": 10, "high": 10, "low": 5, "close": 8}) is False


@pytest.mark.integration
def test_storage_data_completeness_integration():
    from datetime import datetime

    from tests.conftest import TEST_DSN
    from trading.calendar_vn import TZ
    from trading.storage.db import Storage

    s = Storage(TEST_DSN)
    test_symbols = ["_TEST_COMP_FULL", "_TEST_COMP_GAP", "_TEST_COMP_DIRTY"]

    with s.conn() as c:
        c.execute("DELETE FROM bars_daily WHERE symbol = ANY(%s)", (test_symbols,))

        # Insert test bars
        # Day 1: 2026-01-05
        # Day 2: 2026-01-06
        # Day 3: 2026-01-07
        c.execute(
            """
            INSERT INTO bars_daily (symbol, ts, open, high, low, close, volume, source) VALUES
            ('_TEST_COMP_FULL', %s, 10, 11, 9, 10, 100, 'test'),
            ('_TEST_COMP_FULL', %s, 10, 11, 9, 10, 100, 'test'),
            ('_TEST_COMP_FULL', %s, 10, 11, 9, 10, 100, 'test'),
            ('_TEST_COMP_GAP',  %s, 20, 21, 19, 20, 200, 'test'),
            ('_TEST_COMP_GAP',  %s, 20, 21, 19, 20, 200, 'test'),
            ('_TEST_COMP_DIRTY',%s, 0,  10, 0,  10, 100, 'test')
            """,
            (
                datetime(2026, 1, 5, 15, 0, tzinfo=TZ),
                datetime(2026, 1, 6, 15, 0, tzinfo=TZ),
                datetime(2026, 1, 7, 15, 0, tzinfo=TZ),
                datetime(2026, 1, 5, 15, 0, tzinfo=TZ),
                datetime(2026, 1, 7, 15, 0, tzinfo=TZ),
                datetime(2026, 1, 5, 15, 0, tzinfo=TZ),
            ),
        )

    try:
        # 1. Summaries
        summaries = {
            r["symbol"]: r
            for r in s.read_symbol_completeness_summaries(symbols=test_symbols)
        }
        assert "_TEST_COMP_FULL" in summaries
        assert summaries["_TEST_COMP_FULL"]["first_date"] == date(2026, 1, 5)
        assert summaries["_TEST_COMP_FULL"]["last_date"] == date(2026, 1, 7)
        assert summaries["_TEST_COMP_FULL"]["total_bars"] == 3
        assert summaries["_TEST_COMP_FULL"]["dirty_bars"] == 0

        assert "_TEST_COMP_GAP" in summaries
        assert summaries["_TEST_COMP_GAP"]["first_date"] == date(2026, 1, 5)
        assert summaries["_TEST_COMP_GAP"]["last_date"] == date(2026, 1, 7)
        assert summaries["_TEST_COMP_GAP"]["total_bars"] == 2
        assert summaries["_TEST_COMP_GAP"]["dirty_bars"] == 0

        assert "_TEST_COMP_DIRTY" in summaries
        assert summaries["_TEST_COMP_DIRTY"]["first_date"] == date(2026, 1, 5)
        assert summaries["_TEST_COMP_DIRTY"]["last_date"] == date(2026, 1, 5)
        assert summaries["_TEST_COMP_DIRTY"]["total_bars"] == 1
        assert summaries["_TEST_COMP_DIRTY"]["dirty_bars"] == 1

        # 2. Present dates
        gap_dates = s.read_symbol_present_dates("_TEST_COMP_GAP")
        assert gap_dates == {date(2026, 1, 5), date(2026, 1, 7)}

        # 3. Symbols on date
        symbols_day2 = s.read_symbols_with_bar_on_date(
            date(2026, 1, 6), symbols=test_symbols
        )
        assert symbols_day2 == {"_TEST_COMP_FULL"}

        symbols_day1 = s.read_symbols_with_bar_on_date(
            date(2026, 1, 5), symbols=test_symbols
        )
        assert symbols_day1 == {"_TEST_COMP_FULL", "_TEST_COMP_GAP", "_TEST_COMP_DIRTY"}

    finally:
        with s.conn() as c:
            c.execute("DELETE FROM bars_daily WHERE symbol = ANY(%s)", (test_symbols,))


def test_daily_data_check_all_present():
    from scripts.daily_data_check import evaluate_daily_completeness

    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["HPG", "VIC", "VNM"],
        present_symbols={"HPG", "VIC", "VNM", "TCB"},
    )
    assert code == 0
    assert missing == set()
    assert "Đầy đủ" in msg


def test_daily_data_check_dead_feed_silent_for_heartbeat_2a():
    from scripts.daily_data_check import evaluate_daily_completeness

    # Khi cả feed chết hoặc ngày nghỉ, present_symbols = rỗng
    # Job phải im lặng (code 0) để không bắn cảnh báo trùng với Heartbeat 2A
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["HPG", "VIC", "VNM"],
        present_symbols=set(),
    )
    assert code == 0
    assert missing == set()
    assert "Heartbeat 2A" in msg


def test_daily_data_check_missing_active_symbol_triggers_alert():
    from scripts.daily_data_check import evaluate_daily_completeness

    # Feed sống (có VIC, VNM) nhưng SÓT HPG
    code, missing, msg = evaluate_daily_completeness(
        active_symbols=["HPG", "VIC", "VNM"],
        present_symbols={"VIC", "VNM", "SSI"},
    )
    assert code == 1
    assert missing == {"HPG"}
    assert "HPG" in msg


def test_daily_data_check_no_active_symbols():
    from scripts.daily_data_check import evaluate_daily_completeness

    code, missing, _msg = evaluate_daily_completeness(
        active_symbols=[],
        present_symbols={"VIC"},
    )
    assert code == 0
    assert missing == set()


def test_daily_data_check_main_config_error(monkeypatch):
    from scripts.daily_data_check import main

    monkeypatch.setattr("sys.argv", ["daily_data_check.py", "--date", "invalid-date"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


