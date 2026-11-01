"""Tests cho scripts/screen_liquidity.py (Brief dot 206 §1.2)."""

from datetime import date
from unittest.mock import MagicMock

from scripts.screen_liquidity import active_set, apply, is_stale, main


def test_is_stale():
    cutoff = date(2026, 9, 30)
    assert is_stale(("HOSE", 2e9, 1000, None), cutoff)
    assert is_stale(("HOSE", 2e9, 1000, date(2026, 9, 29)), cutoff)
    assert not is_stale(("HOSE", 2e9, 1000, date(2026, 9, 30)), cutoff)
    assert not is_stale(("HOSE", 2e9, 1000, date(2026, 10, 1)), cutoff)


def test_active_set_filtering():
    """Test active_set: ma stale bi loai, duoi nguong bi loai, du nguong va moi thi vao."""
    cutoff = date(2026, 9, 30)
    stats = {
        "AAA": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),  # Moi + tren nguong -> IN
        "BBB": ("HOSE", 0.5e9, 50_000, date(2026, 10, 25)),  # Moi + duoi nguong -> OUT
        "CCC": ("HNX", 5e9, 200_000, date(2026, 8, 1)),      # Tren nguong + stale -> OUT
        "DDD": ("UPCOM", 2e9, 100_000, None),                 # max_ts None (stale) -> OUT
        "EEE": ("HOSE", 1e9, 80_000, date(2026, 9, 30)),     # Dung ngay cutoff + dung nguong -> IN
    }
    res = active_set(stats, cutoff, min_value=1e9)
    assert res == {"AAA", "EEE"}


def test_apply_executes_updates_and_returns_count(monkeypatch):
    """Test apply goi UPDATE cho moi ma va tra ve so luong ma active."""
    cutoff = date(2026, 9, 30)
    stats = {
        "AAA": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
        "BBB": ("HOSE", 0.5e9, 50_000, date(2026, 10, 25)),
    }

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_cursor
    monkeypatch.setattr("psycopg.connect", lambda dsn: mock_conn)

    count = apply(stats, cutoff, min_value=1e9, dsn="postgresql://fake")
    assert count == 1
    assert mock_cursor.execute.call_count == 2


def test_main_dry_run_does_not_call_apply(monkeypatch, capsys):
    """Test main(--dry-run) chi in phan bo, khong goi apply."""
    cutoff = date(2026, 9, 30)
    stats = {
        "AAA": ("HOSE", 2e9, 100_000, date(2026, 10, 25)),
    }
    monkeypatch.setattr("scripts.screen_liquidity.compute", lambda w, s, dsn: (stats, cutoff))

    apply_called = []
    monkeypatch.setattr("scripts.screen_liquidity.apply", lambda *args, **kwargs: apply_called.append(True))

    main(["--dry-run"])
    assert not apply_called, "apply khong duoc goi khi co --dry-run"
    out = capsys.readouterr().out
    assert "dry-run: chua ghi is_active" in out
