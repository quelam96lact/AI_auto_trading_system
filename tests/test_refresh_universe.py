"""Tests cho scripts/refresh_universe.py (Brief dot 206 §1.3).

Cac ca kiem chung:
(a) cong tuan chan;
(b) --force bo qua cong;
(c) backfill loi thi khong goi apply va tra 1;
(d) co rut >50% thi khong goi apply, co gui Telegram va tra 1;
(e) duong binh thuong goi apply, in dung them/bo va tra 0;
(f) --dry-run khong goi backfill lan apply.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import refresh_universe
from trading.calendar_vn import TZ


class MockStorage:
    def __init__(self, dsn: str, max_updated: datetime | None = None, active: list[str] | None = None):
        self.dsn = dsn
        self._max_updated = max_updated
        self._active = active or ["HPG", "VCB", "SSI", "VHM"]
        self._symbols = {"HPG", "VCB", "SSI", "VHM"}

    def read_symbol_universe(self) -> set[str]:
        return set(self._symbols)

    def get_backfill_progress(self, sym: str, timeframe: str):
        return {"status": "ok", "attempted_until": "2026-10-25"}

    def read_active_universe(self) -> list[str]:
        return list(self._active)

    def conn(self):
        class MockConn:
            def __enter__(inner_self):
                class MockCur:
                    def execute(cur_self, sql):
                        return cur_self

                    def fetchone(cur_self):
                        return (self._max_updated,)

                return MockCur()

            def __exit__(inner_self, *args):
                pass

        return MockConn()


@pytest.fixture
def mock_env(monkeypatch):
    cfg_mock = SimpleNamespace(db_dsn="postgresql://mock", holidays=frozenset())
    monkeypatch.setattr(refresh_universe, "load_config", lambda p: cfg_mock)


def test_weekly_gate_blocks_within_six_days(mock_env, monkeypatch, capsys):
    """(a) Cong tuan chan neu lan lam moi gan nhat cach now < 6 ngay."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    # Lan cap nhat cuoi la 3 ngay truoc (< 6 ngay)
    last_update = now - timedelta(days=3)
    storage = MockStorage("postgresql://mock", max_updated=last_update)
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    rc = refresh_universe.main([], now=now)
    assert rc == 0
    out = capsys.readouterr().out
    assert "chua can" in out


def test_force_bypasses_weekly_gate(mock_env, monkeypatch, capsys):
    """(b) --force bo qua cong tuan."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    last_update = now - timedelta(days=2)
    storage = MockStorage("postgresql://mock", max_updated=last_update)
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    # Mock catchup_end tra ve end cu hon de khong can nap
    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 25))

    stats = {
        s: ("HOSE", 2e9, 100_000, date(2026, 10, 25))
        for s in ["HPG", "VCB", "SSI", "VHM"]
    }
    monkeypatch.setattr(refresh_universe.screen_liquidity, "compute", lambda w, s, dsn: (stats, date(2026, 9, 25)))

    applied = []
    monkeypatch.setattr(refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True))

    rc = refresh_universe.main(["--force"], now=now)
    assert rc == 0
    assert len(applied) == 1
    out = capsys.readouterr().out
    assert "chua can" not in out
    assert "active cu=" in out


def test_backfill_error_does_not_apply_and_returns_1(mock_env, monkeypatch, capsys):
    """(c) Backfill loi thi khong goi apply va tra 1."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    # Lan cap nhat cach 10 ngay (> 6 ngay)
    storage = MockStorage("postgresql://mock", max_updated=now - timedelta(days=10))
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 30))
    monkeypatch.setattr(
        refresh_universe,
        "plan_universe_start",
        lambda prog, end, max_days: (date(2026, 10, 26), False),
    )

    def boom_backfill(*args, **kwargs):
        raise RuntimeError("SSI API Connection refused")

    monkeypatch.setattr(refresh_universe.backfill_universe, "main", boom_backfill)

    applied = []
    monkeypatch.setattr(refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True))

    rc = refresh_universe.main([], now=now)
    assert rc == 1
    assert not applied, "apply KHONG duoc goi khi backfill loi"
    out = capsys.readouterr().out
    assert "LOI backfill" in out


def test_contraction_gate_sends_telegram_and_returns_1(mock_env, monkeypatch, capsys):
    """(d) Co rut >50% (len(new) < 0.5 * len(old)) thi khong goi apply, co gui Telegram va tra 1."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    # old co 4 ma: HPG, VCB, SSI, VHM
    storage = MockStorage("postgresql://mock", max_updated=now - timedelta(days=10))
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 30))
    monkeypatch.setattr(
        refresh_universe,
        "plan_universe_start",
        lambda prog, end, max_days: (None, False),
    )

    # Chi co 1 ma (HPG) dat nguong -> 1 < 0.5 * 4 = 2 (co rut >50%)
    stats = {
        "HPG": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
        "VCB": ("HOSE", 0.1e9, 10_000, date(2026, 10, 25)),  # Duoi nguong
        "SSI": ("HOSE", 0.1e9, 10_000, date(2026, 10, 25)),  # Duoi nguong
        "VHM": ("HOSE", 0.1e9, 10_000, date(2026, 10, 25)),  # Duoi nguong
    }
    monkeypatch.setattr(refresh_universe.screen_liquidity, "compute", lambda w, s, dsn: (stats, date(2026, 9, 25)))

    applied = []
    monkeypatch.setattr(refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True))

    telegram_sent = []
    monkeypatch.setattr(refresh_universe, "send_telegram", lambda msg: telegram_sent.append(msg))

    rc = refresh_universe.main([], now=now)
    assert rc == 1
    assert not applied, "apply KHONG duoc goi khi bi cong co rut chan"
    assert len(telegram_sent) == 1
    assert "Cong co rut chan" in telegram_sent[0]
    out = capsys.readouterr().out
    assert "Cong co rut chan" in out


def test_normal_path_calls_apply_and_prints_diff(mock_env, monkeypatch, capsys):
    """(e) Duong binh thuong goi apply, in dung them/bo va tra 0."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    # old co: HPG, VCB, SSI (3 ma)
    storage = MockStorage("postgresql://mock", max_updated=now - timedelta(days=10), active=["HPG", "VCB", "SSI"])
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 30))
    monkeypatch.setattr(
        refresh_universe,
        "plan_universe_start",
        lambda prog, end, max_days: (None, False),
    )

    # new co: HPG, VCB, VHM (3 ma -> them VHM, bo SSI)
    stats = {
        "HPG": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
        "VCB": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
        "VHM": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
        "SSI": ("HOSE", 0.1e9, 10_000, date(2026, 10, 25)),  # Bi loai
    }
    monkeypatch.setattr(refresh_universe.screen_liquidity, "compute", lambda w, s, dsn: (stats, date(2026, 9, 25)))

    applied = []
    monkeypatch.setattr(refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True))

    rc = refresh_universe.main([], now=now)
    assert rc == 0
    assert len(applied) == 1
    out = capsys.readouterr().out
    assert "[universe] active cu=3 moi=3" in out
    assert "them=['VHM']" in out
    assert "bo=['SSI']" in out


def test_dry_run_does_not_call_backfill_or_apply(mock_env, monkeypatch, capsys):
    """(f) --dry-run khong goi backfill lan apply."""
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    storage = MockStorage("postgresql://mock", max_updated=now - timedelta(days=10))
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)

    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 30))
    monkeypatch.setattr(
        refresh_universe,
        "plan_universe_start",
        lambda prog, end, max_days: (date(2026, 10, 26), False),
    )

    backfill_called = []
    monkeypatch.setattr(refresh_universe.backfill_universe, "main", lambda args: backfill_called.append(args))

    stats = {
        s: ("HOSE", 2e9, 100_000, date(2026, 10, 25))
        for s in ["HPG", "VCB", "SSI", "VHM"]
    }
    monkeypatch.setattr(refresh_universe.screen_liquidity, "compute", lambda w, s, dsn: (stats, date(2026, 9, 25)))

    applied = []
    monkeypatch.setattr(refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True))

    rc = refresh_universe.main(["--dry-run"], now=now)
    assert rc == 0
    assert not backfill_called, "--dry-run khong duoc goi backfill"
    assert not applied, "--dry-run khong duoc goi apply"
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "ke hoach 1d: nap 2026-10-26 -> 2026-10-30" in out


@pytest.mark.parametrize("n_err, expect_rc", [(2, 1), (0, 0)])
def test_backfill_swallowed_errors_gate(mock_env, monkeypatch, capsys, n_err, expect_rc):
    """(g) Audit Lead: backfill_universe nuot loi tung ma va tra None.

    Loi > 20% so ma (2/4) thi khong apply, gui Telegram, tra 1; 0 loi thi di tiep.
    """
    now = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)
    storage = MockStorage("postgresql://mock", max_updated=now - timedelta(days=10))
    err_syms = set(sorted(storage._symbols)[:n_err])
    storage.get_backfill_progress = lambda s, tf: {
        "status": "error" if s in err_syms else "ok",
        "attempted_until": "2026-10-25",
    }
    monkeypatch.setattr(refresh_universe, "Storage", lambda dsn: storage)
    monkeypatch.setattr(refresh_universe, "catchup_end", lambda now, h: date(2026, 10, 30))
    monkeypatch.setattr(
        refresh_universe,
        "plan_universe_start",
        lambda prog, end, max_days: (date(2026, 10, 26), False),
    )
    monkeypatch.setattr(refresh_universe.backfill_universe, "main", lambda args: None)
    stats = {s: ("HOSE", 2e9, 100_000, date(2026, 10, 30)) for s in storage._symbols}
    monkeypatch.setattr(
        refresh_universe.screen_liquidity, "compute", lambda w, s, dsn: (stats, date(2026, 9, 30))
    )
    applied = []
    monkeypatch.setattr(
        refresh_universe.screen_liquidity, "apply", lambda s, c, m, d: applied.append(True)
    )
    sent = []
    monkeypatch.setattr(refresh_universe, "send_telegram", lambda msg: sent.append(msg))

    rc = refresh_universe.main([], now=now)
    assert rc == expect_rc
    if expect_rc == 1:
        assert not applied
        assert len(sent) == 1 and "loi 2/4" in sent[0]
    else:
        assert applied == [True]
        assert not sent
