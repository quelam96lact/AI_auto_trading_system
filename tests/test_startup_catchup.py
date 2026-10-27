"""Unit tests cho Brief 199: Tự kiểm và nạp bù khi khởi động máy.

Bao gồm:
- Test các hàm thuần (§3.2):
  - catchup_end: (a)-(e)
  - plan_universe_start: (f)-(k)
  - plan_foreign_flow_start: (l)-(o)
  - find_short_days: (p)-(t)
- Test main(argv) với giả lập (§3.3):
  - Các ca (i)-(x)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from scripts.startup_catchup import (
    catchup_end,
    find_short_days,
    main,
    plan_foreign_flow_start,
    plan_universe_start,
)
from trading.calendar_vn import TZ

# ============================================================================
# §3.2 Test hàm thuần
# ============================================================================


def test_catchup_end_tuesday_before_cutoff():
    """(a) Thứ Ba 27/10 21:29 -> P = thứ Hai 26/10."""
    now = datetime(2026, 10, 27, 21, 29, 0, tzinfo=TZ)
    assert catchup_end(now, frozenset()) == date(2026, 10, 26)


def test_catchup_end_tuesday_at_cutoff():
    """(b) Thứ Ba 27/10 21:30 -> Thứ Ba 27/10."""
    now = datetime(2026, 10, 27, 21, 30, 0, tzinfo=TZ)
    assert catchup_end(now, frozenset()) == date(2026, 10, 27)


def test_catchup_end_saturday_weekend():
    """(c) Thứ Bảy 31/10 23:00 -> Thứ Sáu 30/10."""
    now = datetime(2026, 10, 31, 23, 0, 0, tzinfo=TZ)
    assert catchup_end(now, frozenset()) == date(2026, 10, 30)


def test_catchup_end_monday_morning():
    """(d) Thứ Hai 26/10 08:00 -> Thứ Sáu 23/10."""
    now = datetime(2026, 10, 26, 8, 0, 0, tzinfo=TZ)
    assert catchup_end(now, frozenset()) == date(2026, 10, 23)


def test_catchup_end_holiday():
    """(e) holidays = {thứ Hai 02/11}, now = thứ Ba 03/11 10:00 -> Thứ Sáu 30/10."""
    holidays = frozenset({date(2026, 11, 2)})
    now = datetime(2026, 11, 3, 10, 0, 0, tzinfo=TZ)
    assert catchup_end(now, holidays) == date(2026, 10, 30)


def test_plan_universe_start_all_up_to_date():
    """(f) Mọi mã attempted_until = end -> (None, False)."""
    end = date(2026, 10, 27)
    progress = {
        "AAA": {"status": "ok", "attempted_until": end},
        "HPG": {"status": "ok", "attempted_until": end},
    }
    assert plan_universe_start(progress, end, max_days=90) == (None, False)


def test_plan_universe_start_three_symbols_min_date():
    """(g) Ba mã với ngày 20/10, 22/10, 26/10, end 27/10 -> (20/10, False)."""
    end = date(2026, 10, 27)
    progress = {
        "AAA": {"status": "ok", "attempted_until": date(2026, 10, 20)},
        "HPG": {"status": "ok", "attempted_until": date(2026, 10, 22)},
        "VIC": {"status": "ok", "attempted_until": date(2026, 10, 26)},
    }
    assert plan_universe_start(progress, end, max_days=90) == (
        date(2026, 10, 20),
        False,
    )


def test_plan_universe_start_error_or_none_defaults_to_7_days():
    """(h) Một mã status error, một mã progress None -> mốc là end - 7 ngày."""
    end = date(2026, 10, 27)
    expected = end - timedelta(days=7)
    # Riêng mã lỗi: nếu bỏ kiểm status == "ok" sẽ lấy nhầm attempted_until (26/10) thay vì end - 7
    progress_error_only = {
        "AAA": {"status": "error", "attempted_until": date(2026, 10, 26)},
        "VIC": {"status": "ok", "attempted_until": date(2026, 10, 26)},
    }
    assert plan_universe_start(progress_error_only, end, max_days=90) == (
        expected,
        False,
    )

    progress = {
        "AAA": {"status": "error", "attempted_until": date(2026, 10, 26)},
        "HPG": None,
        "VIC": {"status": "ok", "attempted_until": date(2026, 10, 26)},
    }
    assert plan_universe_start(progress, end, max_days=90) == (expected, False)


def test_plan_universe_start_gap_over_max_days_clamped():
    """(i) Một mã có attempted_until cách end 120 ngày, max 90 -> (end - 90, True)."""
    end = date(2026, 10, 27)
    progress = {
        "AAA": {"status": "ok", "attempted_until": end - timedelta(days=120)},
        "HPG": {"status": "ok", "attempted_until": end - timedelta(days=10)},
    }
    assert plan_universe_start(progress, end, max_days=90) == (
        end - timedelta(days=90),
        True,
    )


def test_plan_universe_start_gap_exact_max_days_not_clamped():
    """(j) Đúng 90 ngày -> không bị cắt."""
    end = date(2026, 10, 27)
    progress = {
        "AAA": {"status": "ok", "attempted_until": end - timedelta(days=90)},
    }
    assert plan_universe_start(progress, end, max_days=90) == (
        end - timedelta(days=90),
        False,
    )


def test_plan_universe_start_empty_progress():
    """(k) Progress rỗng -> (end - 7, False)."""
    end = date(2026, 10, 27)
    assert plan_universe_start({}, end, max_days=90) == (end - timedelta(days=7), False)


def test_plan_foreign_flow_start_normal_gap():
    """(l) last = 23/10, end = 27/10 -> (24/10, False)."""
    end = date(2026, 10, 27)
    counts = {
        date(2026, 10, 22): 640,
        date(2026, 10, 23): 642,
    }
    assert plan_foreign_flow_start(counts, end, max_days=90) == (
        date(2026, 10, 24),
        False,
    )


def test_plan_foreign_flow_start_already_at_end():
    """(m) last = end -> (None, False)."""
    end = date(2026, 10, 27)
    counts = {date(2026, 10, 27): 640}
    assert plan_foreign_flow_start(counts, end, max_days=90) == (None, False)


def test_plan_foreign_flow_start_empty_counts():
    """(n) dict rỗng -> (end - 90, True)."""
    end = date(2026, 10, 27)
    assert plan_foreign_flow_start({}, end, max_days=90) == (
        end - timedelta(days=90),
        True,
    )


def test_plan_foreign_flow_start_zero_counts_ignored():
    """(o) Có ngày count 0 sau last -> bị bỏ qua."""
    end = date(2026, 10, 27)
    counts = {
        date(2026, 10, 23): 640,
        date(2026, 10, 24): 0,
        date(2026, 10, 25): 0,
    }
    assert plan_foreign_flow_start(counts, end, max_days=90) == (
        date(2026, 10, 24),
        False,
    )


def test_find_short_days_threshold_comparison():
    """(p) base 172, một ngày 137 -> thiếu; 138 -> đủ (137 < 0.8 * 172 = 137.6 <= 138)."""
    d1 = date(2026, 10, 20)
    d2 = date(2026, 10, 21)
    base_days = [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)]
    counts = {
        date(2026, 10, 10): 172,
        date(2026, 10, 11): 172,
        date(2026, 10, 12): 172,
        d1: 137,
        d2: 138,
    }
    assert find_short_days(counts, [d1, d2], base_days, ratio=0.8) == [d1]


def test_find_short_days_exact_80_pct_is_sufficient():
    """(q) Đúng 80% (8/10) -> đủ."""
    d = date(2026, 10, 20)
    base_days = [date(2026, 10, 10)]
    counts = {
        date(2026, 10, 10): 10,
        d: 8,
    }
    assert find_short_days(counts, [d], base_days, ratio=0.8) == []


def test_find_short_days_missing_date_in_counts():
    """(r) Ngày không có trong counts -> thiếu."""
    d = date(2026, 10, 20)
    base_days = [date(2026, 10, 10)]
    counts = {date(2026, 10, 10): 172}
    assert find_short_days(counts, [d], base_days, ratio=0.8) == [d]


def test_find_short_days_empty_or_zero_baseline():
    """(s) Baseline toàn 0 -> mọi ngày thiếu."""
    d1 = date(2026, 10, 20)
    d2 = date(2026, 10, 21)
    base_days = [date(2026, 10, 10)]
    counts = {
        date(2026, 10, 10): 0,
        d1: 100,
        d2: 100,
    }
    assert find_short_days(counts, [d1, d2], base_days, ratio=0.8) == [d1, d2]


def test_find_short_days_uses_median_not_min_or_mean():
    """(t) Trung vị chứ không phải min hay trung bình.
    Baseline [172, 172, 172, 3, 3] median=172 (ngưỡng 137.6).
    - Ngày kiểm 150 >= 137.6 -> đủ ([]).
    - Ngày kiểm 100 < 137.6 -> thiếu ([d2]). Nếu dùng min(=3), 100 >= 2.4 sẽ bị tính nhầm là đủ!
    """
    b_days = [date(2026, 10, i) for i in range(10, 15)]
    d1 = date(2026, 10, 20)
    d2 = date(2026, 10, 21)
    counts = {
        b_days[0]: 172,
        b_days[1]: 172,
        b_days[2]: 172,
        b_days[3]: 3,
        b_days[4]: 3,
        d1: 150,
        d2: 100,
    }
    assert find_short_days(counts, [d1], b_days, ratio=0.8) == []
    assert find_short_days(counts, [d2], b_days, ratio=0.8) == [d2]


# ============================================================================
# §3.3 Test main(argv) với giả lập
# ============================================================================


@dataclass
class FakeConfig:
    db_dsn: str = "mock://dsn"
    symbols: list[str] = field(default_factory=lambda: ["HPG"])
    ssi_equity_accounts: list[str] = field(default_factory=list)
    holidays: frozenset = frozenset()


class FakeCatchupStorage:
    def __init__(
        self,
        symbols: list[str] | None = None,
        progress: dict[tuple[str, str], dict | None] | None = None,
        ff_counts: dict[date, int] | None = None,
        daily_counts: dict[date, int] | None = None,
        m5_counts: dict[date, int] | None = None,
        fails_before_ready: int = 0,
    ):
        self.symbols = symbols or ["AAA", "HPG", "VIC", "VNM"]
        self.progress = progress or {}
        self.ff_counts = ff_counts or {}
        self.daily_counts = daily_counts or {}
        self.m5_counts = m5_counts or {}
        self.fails_left = fails_before_ready

    def read_active_universe(self) -> list[str]:
        if self.fails_left > 0:
            self.fails_left -= 1
            raise ConnectionError("DB not ready")
        return list(self.symbols)

    def read_must_price_symbols(
        self, accounts: list[str], extra: list[str]
    ) -> list[str]:
        return list(extra)

    def get_backfill_progress(self, symbol: str, timeframe: str) -> dict | None:
        return self.progress.get((symbol, timeframe))

    def read_foreign_flow_day_counts(self, frm: date, to: date) -> dict[date, int]:
        return {d: c for d, c in self.ff_counts.items() if frm <= d <= to}

    def read_daily_active_symbol_day_counts(
        self, frm: date, to: date
    ) -> dict[date, int]:
        return {d: c for d, c in self.daily_counts.items() if frm <= d <= to}

    def read_5m_active_symbol_day_counts(self, frm: date, to: date) -> dict[date, int]:
        return {d: c for d, c in self.m5_counts.items() if frm <= d <= to}


def setup_base_env(
    monkeypatch, storage=None, cfg=None, now_dt=None, auto_fill_ff_on_load: bool = True
):
    """Helper set up monkeypatch for main."""
    cfg = cfg or FakeConfig()
    storage = storage or FakeCatchupStorage()
    now_dt = now_dt or datetime(2026, 10, 27, 22, 0, 0, tzinfo=TZ)
    bu_calls: list[list[str]] = []
    bff_calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_bu_main(argv):
        bu_calls.append(list(argv))
        return 0

    def fake_bff_main(argv):
        bff_calls.append(list(argv))
        if auto_fill_ff_on_load:
            # Simulate foreign flow job populating missing days up to end
            storage.ff_counts.update(make_clean_counts(now_dt.date()))
        return 0

    monkeypatch.setattr("scripts.startup_catchup.load_config", lambda path: cfg)
    monkeypatch.setattr("scripts.startup_catchup.Storage", lambda dsn: storage)
    monkeypatch.setattr("scripts.startup_catchup._now", lambda: now_dt)
    monkeypatch.setattr("scripts.startup_catchup._sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("scripts.startup_catchup.backfill_universe.main", fake_bu_main)
    monkeypatch.setattr(
        "scripts.startup_catchup.backfill_foreign_flow.main", fake_bff_main
    )

    return {
        "cfg": cfg,
        "storage": storage,
        "bu_calls": bu_calls,
        "bff_calls": bff_calls,
        "sleeps": sleeps,
    }


def make_clean_counts(end: date, n_days: int = 40, count: int = 172):
    """Tao dict counts day du cho buoc kiem tra khong bi thieu."""
    return {end - timedelta(days=i): count for i in range(n_days)}


def test_main_calls_all_three_sources_when_gaps_exist(monkeypatch):
    """(i) Có khoảng trống cả ba nguồn: argv 1d, 5m (--skip-config-symbols), và khối ngoại."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    cfg = FakeConfig(symbols=["HPG"])
    storage = FakeCatchupStorage(
        symbols=["AAA", "HPG", "VIC"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 22)},
            ("HPG", "1d"): {"status": "ok", "attempted_until": end},
            ("VIC", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 24)},
            ("VIC", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 25)},
        },
        ff_counts={date(2026, 10, 23): 640},
        daily_counts=clean,
        m5_counts=clean,
    )
    env = setup_base_env(
        monkeypatch,
        storage=storage,
        cfg=cfg,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
    )

    rc = main([])
    assert rc == 0
    assert len(env["bu_calls"]) == 2
    # 1d call
    assert env["bu_calls"][0] == [
        "--timeframe",
        "1d",
        "--from",
        "2026-10-20",
        "--to",
        "2026-10-26",
        "--use-universe",
        "--sleep-ms",
        "200",
    ]
    # 5m call
    assert env["bu_calls"][1] == [
        "--timeframe",
        "5m",
        "--from",
        "2026-10-22",
        "--to",
        "2026-10-26",
        "--use-universe",
        "--skip-config-symbols",
        "--sleep-ms",
        "200",
    ]
    # foreign flow call
    assert env["bff_calls"] == [["--from", "2026-10-24", "--to", "2026-10-26"]]


def test_main_invariant_1_never_loads_today_before_cutoff(monkeypatch):
    """(ii) Bất biến số 1: now = thứ Ba 27/10 10:00 -> mọi argv có --to 2026-10-26, không bao giờ là 2026-10-27."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    cfg = FakeConfig(symbols=[])
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
        },
        ff_counts={date(2026, 10, 20): 600},
        daily_counts=clean,
        m5_counts=clean,
    )
    # 10:00 AM on Tuesday 27/10
    now_dt = datetime(2026, 10, 27, 10, 0, 0, tzinfo=TZ)
    env = setup_base_env(monkeypatch, storage=storage, cfg=cfg, now_dt=now_dt)

    rc = main([])
    assert rc == 0
    for call in env["bu_calls"]:
        to_idx = call.index("--to")
        assert call[to_idx + 1] == "2026-10-26"
    for call in env["bff_calls"]:
        to_idx = call.index("--to")
        assert call[to_idx + 1] == "2026-10-26"


def test_main_5m_progress_ignores_stream_symbols(monkeypatch):
    """(iii) 5m: progress chỉ hỏi các mã không thuộc cfg.symbols. HPG có attempted_until cũ 60 ngày không kéo --from 5m về 60 ngày."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    cfg = FakeConfig(symbols=["HPG"])
    storage = FakeCatchupStorage(
        symbols=["AAA", "HPG"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 24)},
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 24)},
            # HPG is a streaming symbol with stale progress of 60 days ago
            ("HPG", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 24)},
            ("HPG", "5m"): {"status": "ok", "attempted_until": date(2026, 8, 27)},
        },
        ff_counts=clean,
        daily_counts=clean,
        m5_counts=clean,
    )
    env = setup_base_env(
        monkeypatch,
        storage=storage,
        cfg=cfg,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
    )

    rc = main([])
    assert rc == 0
    # 5m call should have --from 2026-10-24, not 2026-08-27!
    call_5m = env["bu_calls"][1]
    from_idx = call_5m.index("--from")
    assert call_5m[from_idx + 1] == "2026-10-24"


def test_main_none_plan_skips_corresponding_load(monkeypatch):
    """(iv) Kế hoạch None -> hàm nạp tương ứng không được gọi."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    cfg = FakeConfig(symbols=[])
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            # 1d already up to date
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            # 5m needs catchup
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 24)},
        },
        # foreign flow already up to date
        ff_counts=clean,
        daily_counts=clean,
        m5_counts=clean,
    )
    env = setup_base_env(
        monkeypatch,
        storage=storage,
        cfg=cfg,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
    )

    rc = main([])
    assert rc == 0
    # only 1 bu call (5m), no 1d call, no bff call
    assert len(env["bu_calls"]) == 1
    assert env["bu_calls"][0][1] == "5m"
    assert len(env["bff_calls"]) == 0


def test_main_1d_exception_continues_other_steps(monkeypatch, capsys):
    """(v) Bước 1d ném exception -> bước 5m và khối ngoại vẫn được gọi, stdout có [catchup] LOI, return 1."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    cfg = FakeConfig(symbols=[])
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 22)},
        },
        ff_counts={date(2026, 10, 22): 640},
        daily_counts=clean,
        m5_counts=clean,
    )
    env = setup_base_env(
        monkeypatch,
        storage=storage,
        cfg=cfg,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
    )

    # Make 1d raise exception
    calls: list[str] = []

    def mock_bu(argv):
        calls.append(argv[1])
        if argv[1] == "1d":
            raise RuntimeError("1D fail simulation")
        return 0

    monkeypatch.setattr("scripts.startup_catchup.backfill_universe.main", mock_bu)

    rc = main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[catchup] LOI 1d: RuntimeError: 1D fail simulation" in out
    # 5m and foreign flow still called!
    assert "5m" in calls
    assert len(env["bff_calls"]) == 1


def test_main_foreign_flow_non_zero_exit_code_fails(monkeypatch):
    """(vi) backfill_foreign_flow.main trả 2 -> return 1."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts={date(2026, 10, 20): 640},
        daily_counts=clean,
        m5_counts=clean,
    )
    setup_base_env(
        monkeypatch,
        storage=storage,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
        auto_fill_ff_on_load=False,
    )
    monkeypatch.setattr(
        "scripts.startup_catchup.backfill_foreign_flow.main", lambda argv: 2
    )

    rc = main([])
    assert rc == 1


def test_main_foreign_flow_non_zero_exit_alone_fails(monkeypatch, capsys):
    """(vi-b) Audit 199: khối ngoại trả 2 nhưng dữ liệu đã đủ (bước kiểm sạch) -> vẫn return 1 và in LOI.
    Ca (vi) ở trên có ngày thiếu nên return 1 kể cả khi mã trả về bị bỏ qua."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    ff = {d: c for d, c in clean.items() if d <= date(2026, 10, 23)}
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=ff,
        daily_counts=clean,
        m5_counts=clean,
    )
    setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    def bff_fill_then_fail(argv):
        storage.ff_counts.update(clean)
        return 2

    monkeypatch.setattr(
        "scripts.startup_catchup.backfill_foreign_flow.main", bff_fill_then_fail
    )

    rc = main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[catchup] LOI foreign-flow" in out


def test_main_short_day_only_in_foreign_flow_returns_1(monkeypatch):
    """Audit 199: chỉ khối ngoại có ngày thiếu (1d, 5m đủ) -> return 1."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    ff = dict(clean)
    ff[date(2026, 10, 22)] = 10
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=ff,
        daily_counts=clean,
        m5_counts=clean,
    )
    setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    assert main([]) == 1


def test_main_week_long_outage_flagged_against_30_day_baseline(monkeypatch, capsys):
    """Audit 199: 9 phiên cuối đều thiếu nến ngày. So với trung vị của chính các ngày kiểm
    (đa số thiếu) thì không thấy gì; phải so với nền 30 ngày mới bắt được."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    daily = dict(clean)
    for d in [date(2026, 10, x) for x in (14, 15, 16, 19, 20, 21, 22, 23, 26)]:
        daily[d] = 10
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=clean,
        daily_counts=daily,
        m5_counts=clean,
    )
    setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    rc = main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "2026-10-14" in out and "2026-10-26" in out


def test_main_dry_run_skips_all_loads_runs_checks(monkeypatch, capsys):
    """(vii) --dry-run -> không hàm nạp nào được gọi, bước kiểm vẫn chạy."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
            ("AAA", "5m"): {"status": "ok", "attempted_until": date(2026, 10, 20)},
        },
        # Khối ngoại cũng có khoảng trống (từ 24/10) để kiểm dry-run chặn cả bước này.
        ff_counts={d: c for d, c in clean.items() if d <= date(2026, 10, 23)},
        daily_counts=clean,
        m5_counts=clean,
    )
    env = setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    rc = main(["--dry-run"])
    out = capsys.readouterr().out
    # Không nạp nên phiên 26/10 khối ngoại vẫn thiếu (24-25/10 là cuối tuần) -> return 1.
    assert rc == 1
    assert "[kiem] foreign-flow: 11 ngay, thieu: ['2026-10-26']" in out
    assert len(env["bu_calls"]) == 0
    assert len(env["bff_calls"]) == 0
    assert "[kiem] 1d:" in out
    assert "[kiem] 5m:" in out
    assert "[kiem] foreign-flow:" in out


def test_main_missing_days_in_check_returns_1(monkeypatch):
    """(viii) Bước kiểm có ngày thiếu -> return 1; đủ hết và không lỗi -> return 0."""
    end = date(2026, 10, 26)
    # counts with one day short in 1d
    short_counts = make_clean_counts(end)
    short_counts[date(2026, 10, 22)] = 10  # very low count
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=make_clean_counts(end),
        daily_counts=short_counts,
        m5_counts=make_clean_counts(end),
    )
    setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    rc = main([])
    assert rc == 1


def test_main_clamped_plan_prints_warning_and_returns_1(monkeypatch, capsys):
    """(ix) Bị cắt -> return 1 và stdout có can chay tay --from."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            # gap 120 days, clamped by max_days=90
            ("AAA", "1d"): {
                "status": "ok",
                "attempted_until": end - timedelta(days=120),
            },
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=clean,
        daily_counts=clean,
        m5_counts=clean,
    )
    setup_base_env(
        monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )

    rc = main(["--max-days", "90"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "CANH BAO: khoang hong vuot 90 ngay, can chay tay --from" in out


def test_main_clamped_5m_only_returns_1(monkeypatch, capsys):
    """Audit 199: chỉ kế hoạch 5m bị cắt (1d, khối ngoại bình thường) -> return 1."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end, n_days=200)
    storage = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end - timedelta(days=120)},
        },
        ff_counts=clean,
        daily_counts=clean,
        m5_counts=clean,
    )
    setup_base_env(monkeypatch, storage=storage, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ))

    rc = main(["--max-days", "90"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "can chay tay --from" in out


def test_main_db_retry_success_and_failure(monkeypatch, capsys):
    """(x) read_active_universe hỏng 2 lần rồi được -> chạy tiếp; hỏng 30 lần -> return 1, sleep 29 lần."""
    end = date(2026, 10, 26)
    clean = make_clean_counts(end)

    # Sub-case 1: fails 2 times then succeeds
    storage_ok = FakeCatchupStorage(
        symbols=["AAA"],
        progress={
            ("AAA", "1d"): {"status": "ok", "attempted_until": end},
            ("AAA", "5m"): {"status": "ok", "attempted_until": end},
        },
        ff_counts=clean,
        daily_counts=clean,
        m5_counts=clean,
        fails_before_ready=2,
    )
    env_ok = setup_base_env(
        monkeypatch, storage=storage_ok, now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ)
    )
    rc = main([])
    assert rc == 0
    assert len(env_ok["sleeps"]) == 2

    # Sub-case 2: fails 30 times -> return 1
    storage_fail = FakeCatchupStorage(fails_before_ready=35)
    env_fail = setup_base_env(
        monkeypatch,
        storage=storage_fail,
        now_dt=datetime(2026, 10, 27, 10, 0, tzinfo=TZ),
    )
    rc_fail = main([])
    out = capsys.readouterr().out
    assert rc_fail == 1
    assert "[catchup] DB chua san sang sau 300s" in out
    assert len(env_fail["sleeps"]) == 29
