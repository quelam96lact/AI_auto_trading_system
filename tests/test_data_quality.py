from datetime import date
from typing import ClassVar

import pytest

from trading.data_quality import (
    SymbolCompleteness,
    classify_missing_dates,
    compute_daily_missing_counts,
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
        date(2026, 1, 7): 5,  # Thứ 4: ngày test / nghỉ lễ
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


def test_daily_data_check_union_includes_must_price(monkeypatch):
    """Brief 2026-09-01 (dot 2): daily_data_check kiem tren HOP active +
    must_price (cfg.symbols + ma dang nam giu). Ma nang giu CAP thieu bar ->
    phai bao THIEU (truoc khi sua thi khong — chi soi active)."""
    import scripts.daily_data_check as ddc

    # Storage gia: active chi co {VCB, SSI}; must_price (read_real_positions
    # cua account) tra CAP; bar hom nay chi co VCB, SSI -> CAP thieu
    class FakeStorage:
        def read_active_universe(self):
            return ["VCB", "SSI"]

        def read_must_price_symbols(self, accounts, extra):
            return ["CAP"]

        def read_symbols_with_bar_on_date(self, d):
            return {"VCB", "SSI"}

    class FakeCfg:
        ssi_equity_accounts: ClassVar[list[str]] = ["CAP"]
        symbols: ClassVar[list[str]] = []
        # Config that co field bat buoc `holidays` (trading/config.py:14) — fake
        # thieu no la fake lech that, khong phai ly do de giu getattr o production.
        holidays: ClassVar[set] = set()

    sent = []
    monkeypatch.setattr(ddc, "send_telegram", lambda msg: sent.append(msg))
    monkeypatch.setattr(ddc, "load_config", lambda path: FakeCfg())
    monkeypatch.setattr(ddc, "Storage", lambda dsn: FakeStorage())
    monkeypatch.setattr(
        ddc, "resolve_dsn", lambda dsn: "postgresql://x:x@127.0.0.1:1/x"
    )
    monkeypatch.setattr("sys.argv", ["daily_data_check.py", "--date", "2026-09-01"])

    with pytest.raises(SystemExit) as exc:
        ddc.main()
    assert exc.value.code == 1, f"CAP thieu bar phai bao, thuc te code={exc.value.code}"
    assert sent, "phai gui Telegram"
    assert "CAP" in sent[0], f"tin nhan phai nhac CAP, thuc te: {sent[0]}"


def test_daily_data_check_main_config_error(monkeypatch):
    from scripts.daily_data_check import main

    monkeypatch.setattr("sys.argv", ["daily_data_check.py", "--date", "invalid-date"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_classify_missing_dates_isolated_vs_correlated():
    # 3 ngày thiếu của 1 mã:
    # Day 1: thị trường vắng 5 mã (<100) -> NO_TRADING
    # Day 2: thị trường vắng 200 mã (>=100) -> COLLECTION_ERROR
    # Day 3: thị trường vắng đúng 100 mã (>=100) -> COLLECTION_ERROR
    # Day 4: thị trường vắng 99 mã (<100) -> NO_TRADING
    session_missing_counts = {
        date(2026, 1, 5): 5,
        date(2026, 1, 6): 200,
        date(2026, 1, 7): 100,
        date(2026, 1, 8): 99,
    }
    missing_dates = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
    ]
    no_trading, collection_error = classify_missing_dates(
        missing_dates=missing_dates,
        session_missing_counts=session_missing_counts,
        threshold=100,
    )
    assert no_trading == [date(2026, 1, 5), date(2026, 1, 8)]
    assert collection_error == [date(2026, 1, 6), date(2026, 1, 7)]


def test_compute_daily_missing_counts():
    trading_sessions = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    # 3 mã:
    # A: [Jan 5, Jan 7] (in lifespan cả 3 ngày)
    # B: [Jan 5, Jan 6] (in lifespan Jan 5, 6)
    # C: [Jan 6, Jan 7] (in lifespan Jan 6, 7)
    summaries = [
        {"symbol": "A", "first_date": date(2026, 1, 5), "last_date": date(2026, 1, 7)},
        {"symbol": "B", "first_date": date(2026, 1, 5), "last_date": date(2026, 1, 6)},
        {"symbol": "C", "first_date": date(2026, 1, 6), "last_date": date(2026, 1, 7)},
    ]
    # Jan 5: in_lifespan = A, B (2). present = 2 -> missing = 0
    # Jan 6: in_lifespan = A, B, C (3). present = 1 -> missing = 2
    # Jan 7: in_lifespan = A, C (2). present = 1 -> missing = 1
    daily_counts = {
        date(2026, 1, 5): 2,
        date(2026, 1, 6): 1,
        date(2026, 1, 7): 1,
    }
    missing_map = compute_daily_missing_counts(
        summaries=summaries,
        trading_sessions=trading_sessions,
        daily_counts=daily_counts,
    )
    assert missing_map[date(2026, 1, 5)] == 0
    assert missing_map[date(2026, 1, 6)] == 2
    assert missing_map[date(2026, 1, 7)] == 1


def test_evaluate_symbol_completeness_with_gap_causes():
    trading_sessions = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    # Mã X có bar ngày 5, 8, 9 (thiếu ngày 6 và 7).
    # Ngày 6: market missing = 2 (<100) -> NO_TRADING
    # Ngày 7: market missing = 150 (>=100) -> COLLECTION_ERROR
    session_missing_counts = {
        date(2026, 1, 5): 0,
        date(2026, 1, 6): 2,
        date(2026, 1, 7): 150,
        date(2026, 1, 8): 0,
        date(2026, 1, 9): 0,
    }
    present_dates = {date(2026, 1, 5), date(2026, 1, 8), date(2026, 1, 9)}
    res = evaluate_symbol_completeness(
        symbol="X",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 9),
        total_bars=3,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2026, 1, 9),
        present_dates=present_dates,
        session_missing_counts=session_missing_counts,
        collection_error_threshold=100,
    )
    assert res.expected_in_lifespan == 5
    assert res.missing_middle == 2
    assert res.missing_middle_no_trading == 1
    assert res.missing_middle_collection_error == 1
    assert res.missing_tail == 0


def test_evaluate_symbol_completeness_bars_beyond_last_consensus_session_never_exceeds_100_pct():
    # Consensus trading sessions chỉ tới 2026-08-07 (5 phiên)
    trading_sessions = [
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 8, 5),
        date(2026, 8, 6),
        date(2026, 8, 7),
    ]
    # Mã AAA là mã live collector ghi thêm bar ngày 2026-08-18 (tổng 6 bar > 5 phiên consensus)
    res = evaluate_symbol_completeness(
        symbol="AAA",
        first_date=date(2026, 8, 3),
        last_date=date(2026, 8, 18),
        total_bars=6,
        dirty_bars=0,
        trading_sessions=trading_sessions,
        as_of_date=date(2026, 8, 7),
    )
    assert res.expected_in_lifespan == 5
    assert res.missing_middle == 0
    assert res.missing_tail == 0


def test_get_status_str_cause_tags():
    from scripts.check_data_completeness import get_status_str

    full = SymbolCompleteness(
        symbol="FULL",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 7),
        total_bars=3,
        dirty_bars=0,
        expected_in_lifespan=3,
        missing_middle=0,
        missing_tail=0,
    )
    assert get_status_str(full) == "FULL"

    coll_err = SymbolCompleteness(
        symbol="ERR",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 7),
        total_bars=2,
        dirty_bars=0,
        expected_in_lifespan=3,
        missing_middle=1,
        missing_tail=0,
        missing_middle_collection_error=1,
    )
    assert get_status_str(coll_err) == "COLLECTION_ERROR"

    no_trade = SymbolCompleteness(
        symbol="NOTRADE",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 7),
        total_bars=2,
        dirty_bars=0,
        expected_in_lifespan=3,
        missing_middle=1,
        missing_tail=0,
        missing_middle_no_trading=1,
    )
    assert get_status_str(no_trade) == "NO_TRADING"

    mixed = SymbolCompleteness(
        symbol="MIXED",
        first_date=date(2026, 1, 5),
        last_date=date(2026, 1, 9),
        total_bars=2,
        dirty_bars=1,
        expected_in_lifespan=5,
        missing_middle=2,
        missing_tail=1,
        missing_middle_collection_error=1,
        missing_middle_no_trading=1,
    )
    assert (
        get_status_str(mixed) == "COLLECTION_ERROR+NO_TRADING+MISSING_TAIL+DIRTY_BARS"
    )


def test_daily_data_check_khong_noi_doi_khi_gui_telegram_that_bai(monkeypatch, capsys):
    """Brief 56: doan gui Telegram truoc day in "Da gui" VO DIEU KIEN.

    Tuc la khi thieu bien moi truong hoac mang hong, script van khang dinh da gui -
    dung kieu noi doi ma bao cao dot 56 Task 2 tu neu ra. Sau khi send_telegram doi
    hop dong sang tra bool (FEE-ALARM-2), doan nay phai noi that.
    """
    import scripts.daily_data_check as ddc

    class FakeStorage:
        def read_active_universe(self):
            return ["VCB", "SSI"]

        def read_must_price_symbols(self, accounts, extra):
            return ["CAP"]

        def read_symbols_with_bar_on_date(self, d):
            return {"VCB", "SSI"}

    class FakeCfg:
        ssi_equity_accounts: ClassVar[list[str]] = ["CAP"]
        symbols: ClassVar[list[str]] = []
        holidays: ClassVar[set] = set()

    monkeypatch.setattr(ddc, "load_config", lambda path: FakeCfg())
    monkeypatch.setattr(ddc, "Storage", lambda dsn: FakeStorage())
    monkeypatch.setattr(ddc, "resolve_dsn", lambda dsn: "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr("sys.argv", ["daily_data_check.py", "--date", "2026-09-01"])

    # (a) gui THAT BAI -> khong duoc khang dinh da gui
    monkeypatch.setattr(ddc, "send_telegram", lambda msg: False)
    with pytest.raises(SystemExit):
        ddc.main()
    out = capsys.readouterr().out
    assert "KHÔNG gửi được" in out, f"gui hong ma van bao da gui: {out!r}"

    # (b) gui THANH CONG -> phai khang dinh da gui
    monkeypatch.setattr(ddc, "send_telegram", lambda msg: True)
    with pytest.raises(SystemExit):
        ddc.main()
    out = capsys.readouterr().out
    assert "Đã gửi cảnh báo qua Telegram" in out, f"gui duoc ma khong bao: {out!r}"
