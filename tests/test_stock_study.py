"""Tests for trading/stock_study.py — load_universe (Brief 124 Phần C)."""
from __future__ import annotations

import sqlite3

from trading.stock_study import load_universe


class FakeStorageForLoadUniverse:
    """Fake storage với sqlite3 in-memory để kiểm tra load_universe mà không cần Postgres."""

    def __init__(self, symbols: list[str]):
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE bars_daily (symbol TEXT, close REAL)"
        )
        self._conn.execute(
            "CREATE TABLE symbol_universe (symbol TEXT, exchange TEXT)"
        )
        for sym in symbols:
            self._conn.execute("INSERT INTO bars_daily VALUES (?, 100.0)", (sym,))
            self._conn.execute("INSERT INTO symbol_universe VALUES (?, 'HOSE')", (sym,))
        self._conn.commit()

    def conn(self):
        return _SqliteContextManager(self._conn)


class _SqliteContextManager:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *_):
        pass


def test_load_universe_empty_string_returns_full_universe():
    """Phần C: exclude_file="" -> không loại mã nào, không chạm filesystem."""
    storage = FakeStorageForLoadUniverse(["HPG", "VCB", "MBB"])
    universe, _exchange, n_all, excluded = load_universe(storage, exclude_file="")
    assert set(universe) == {"HPG", "VCB", "MBB"}, "exclude_file='' không được loại mã nào"
    assert excluded == set(), "excluded phải rỗng khi exclude_file=''"
    assert n_all == 3


def test_load_universe_none_returns_full_universe():
    """Phần C: exclude_file=None -> không loại mã nào, không chạm filesystem."""
    storage = FakeStorageForLoadUniverse(["HPG", "VCB"])
    universe, _, _, excluded = load_universe(storage, exclude_file=None)
    assert set(universe) == {"HPG", "VCB"}, "exclude_file=None không được loại mã nào"
    assert excluded == set(), "excluded phải rỗng khi exclude_file=None"


def test_load_universe_with_real_exclusion_file(tmp_path):
    """Hành vi thường: exclude_file trỏ đến file thật -> loại đúng mã."""
    exc_file = tmp_path / "exclusions.txt"
    exc_file.write_text("VCB\nMBB\n", encoding="utf-8")
    storage = FakeStorageForLoadUniverse(["HPG", "VCB", "MBB"])
    universe, _, _, excluded = load_universe(storage, exclude_file=str(exc_file))
    assert "HPG" in universe
    assert "VCB" not in universe
    assert "MBB" not in universe
    assert excluded == {"VCB", "MBB"}


def test_load_universe_nonexistent_file_returns_full_universe():
    """exclude_file trỏ tới file không tồn tại -> không loại mã nào (hành vi cũ)."""
    storage = FakeStorageForLoadUniverse(["HPG", "VCB"])
    universe, _, _, excluded = load_universe(storage, exclude_file="__this_file_does_not_exist__.txt")
    assert set(universe) == {"HPG", "VCB"}
    assert excluded == set()
