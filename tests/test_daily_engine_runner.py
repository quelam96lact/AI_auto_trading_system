"""Integration tests & mutation checks (k-n) for trading.daily_engine.runner (Brief 233 §5, §6).

All DB tests run exclusively against `trading_test` (enforced via tests/conftest.py).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from tests.conftest import TEST_DSN
from trading.calendar_vn import TZ
from trading.daily_engine.core import (
    FEE_RATE,
    SELL_TAX_RATE,
    SETTLE_DAYS,
    SLIPPAGE_BPS,
)
from trading.daily_engine.runner import CAPITAL, run_daily_engine
from trading.daily_engine.strategy import DailyContext, OrderIntent
from trading.models import Bar
from trading.storage.db import Storage


def _ts_vn(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=TZ)


@pytest.fixture
def clean_daily_db() -> Storage:
    storage = Storage(TEST_DSN)
    storage.init_schema()
    with storage.conn() as c:
        c.execute(
            "TRUNCATE paper_daily_state, paper_daily_lots, paper_daily_orders, paper_daily_nav, "
            "bars_daily, symbol_universe RESTART IDENTITY CASCADE"
        )
    yield storage
    with storage.conn() as c:
        c.execute(
            "TRUNCATE paper_daily_state, paper_daily_lots, paper_daily_orders, paper_daily_nav, "
            "bars_daily, symbol_universe RESTART IDENTITY CASCADE"
        )


def _seed_universe(storage: Storage, symbols: list[str]) -> None:
    storage.upsert_symbol_universe(
        [
            {
                "symbol": sym,
                "exchange": "HOSE",
                "avg_value_20d": 10_000_000_000.0,
                "avg_volume_20d": 500_000.0,
                "is_active": True,
            }
            for sym in symbols
        ]
    )


def _seed_day_bars(
    storage: Storage,
    d: date,
    prices: dict[str, tuple[float, float]],
) -> None:
    """Insert daily bars for (symbol -> (open, close)) on VN date d."""
    bars = [
        Bar(
            symbol=sym,
            ts=_ts_vn(d),
            open=op,
            high=max(op, cl) * 1.01,
            low=min(op, cl) * 0.99,
            close=cl,
            volume=100_000,
            source="test",
        )
        for sym, (op, cl) in prices.items()
    ]
    storage.write_daily(bars)


@pytest.mark.integration
def test_first_run_initializes_state_without_processing_days(clean_daily_db: Storage) -> None:
    """§5.4: Chưa có state -> tạo state với last_processed_date = phiên đủ dữ liệu gần nhất <= hôm nay, không xử lý ngày nào."""
    storage = clean_daily_db
    _seed_universe(storage, [f"S{i}" for i in range(10)])
    # Day 1 (2026-01-05): 10/10 ready; Day 2 (2026-01-06): only 5/10 incomplete
    _seed_day_bars(storage, date(2026, 1, 5), {f"S{i}": (20_000.0, 20_500.0) for i in range(10)})
    _seed_day_bars(storage, date(2026, 1, 6), {f"S{i}": (21_000.0, 21_500.0) for i in range(5)})

    rc = run_daily_engine(dsn=TEST_DSN, today=date(2026, 1, 6))
    assert rc == 0

    with storage.conn() as c:
        row = c.execute(
            "SELECT id, strategy, capital, cash, realized_pnl, last_processed_date "
            "FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        nav_cnt = c.execute("SELECT count(*) FROM paper_daily_nav").fetchone()[0]

    assert row == (1, "null", CAPITAL, CAPITAL, 0.0, date(2026, 1, 5))
    assert nav_cnt == 0


@pytest.mark.integration
def test_mutation_k_runner_idempotent_does_not_reprocess_session(clean_daily_db: Storage) -> None:
    """Phép phá (k): Chạy lại cùng ngày hoặc ngày đã xử lý không xử lý lại phiên và không khớp lệnh hai lần."""
    storage = clean_daily_db
    _seed_universe(storage, ["AAA", "BBB"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"AAA": (20_000.0, 20_000.0), "BBB": (30_000.0, 30_000.0)})
    assert run_daily_engine(dsn=TEST_DSN, today=d0) == 0

    with storage.conn() as c:
        c.execute(
            "INSERT INTO paper_daily_orders (strategy, created_date, symbol, side, qty, status) "
            "VALUES ('null', %s, 'AAA', 'BUY', 100, 'pending')",
            (d0,),
        )
    _seed_day_bars(storage, d1, {"AAA": (20_000.0, 20_500.0), "BBB": (30_000.0, 30_500.0)})

    assert run_daily_engine(dsn=TEST_DSN, today=d1) == 0
    # Run a second time on the same day d1 -> must be a no-op
    assert run_daily_engine(dsn=TEST_DSN, today=d1) == 0

    with storage.conn() as c:
        lots = c.execute("SELECT symbol, qty FROM paper_daily_lots").fetchall()
        nav_rows = c.execute("SELECT date FROM paper_daily_nav ORDER BY date").fetchall()
        orders = c.execute("SELECT id, status, filled_qty FROM paper_daily_orders").fetchall()
        cash = c.execute("SELECT cash FROM paper_daily_state WHERE id = 1").fetchone()[0]

    assert lots == [("AAA", 100)]
    assert [r[0] for r in nav_rows] == [d1]
    assert orders == [(1, "filled", 100)]
    assert cash == pytest.approx(CAPITAL - 2_006_602.8)


@pytest.mark.integration
def test_mutation_l_runner_stops_at_incomplete_session_without_skipping(
    clean_daily_db: Storage,
) -> None:
    """Phép phá (l): Dữ liệu phiên d1 chưa đạt 90% mã active -> dừng với mã 1, không nhảy cóc sang d2 dù d2 đủ 100%."""
    storage = clean_daily_db
    _seed_universe(storage, [f"S{i}" for i in range(10)])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)  # incomplete: 8/10 = 80% < 90%
    d2 = date(2026, 1, 7)  # complete: 10/10 = 100%

    _seed_day_bars(storage, d0, {f"S{i}": (20_000.0, 20_000.0) for i in range(10)})
    assert run_daily_engine(dsn=TEST_DSN, today=d0) == 0

    _seed_day_bars(storage, d1, {f"S{i}": (20_000.0, 20_500.0) for i in range(8)})
    _seed_day_bars(storage, d2, {f"S{i}": (21_000.0, 21_500.0) for i in range(10)})

    rc = run_daily_engine(dsn=TEST_DSN, today=d2)
    assert rc == 1

    with storage.conn() as c:
        last_proc = c.execute("SELECT last_processed_date FROM paper_daily_state WHERE id = 1").fetchone()[0]
        nav_cnt = c.execute("SELECT count(*) FROM paper_daily_nav").fetchone()[0]

    assert last_proc == d0
    assert nav_cnt == 0


@pytest.mark.integration
def test_mutation_m_runner_rejects_mismatched_state_strategy(
    clean_daily_db: Storage, capsys: pytest.CaptureFixture[str]
) -> None:
    """Phép phá (m): State trong DB mang strategy khác với env hiện chọn -> in LỖI ra stderr, không ghi gì, thoát 2."""
    storage = clean_daily_db
    _seed_universe(storage, ["AAA"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"AAA": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d1, {"AAA": (20_000.0, 21_000.0)})

    with storage.conn() as c:
        c.execute(
            "INSERT INTO paper_daily_state (id, strategy, capital, cash, realized_pnl, last_processed_date) "
            "VALUES (1, 'other_strat', %s, %s, 0.0, %s)",
            (CAPITAL, CAPITAL, d0),
        )

    rc = run_daily_engine(dsn=TEST_DSN, today=d1)
    assert rc == 2
    captured = capsys.readouterr()
    assert "LỖI" in captured.err

    with storage.conn() as c:
        last_proc = c.execute("SELECT last_processed_date FROM paper_daily_state WHERE id = 1").fetchone()[0]
        nav_cnt = c.execute("SELECT count(*) FROM paper_daily_nav").fetchone()[0]
    assert last_proc == d0
    assert nav_cnt == 0


@pytest.mark.integration
def test_mutation_n_dry_run_leaves_no_rows_in_db(clean_daily_db: Storage) -> None:
    """Phép phá (n): --dry-run rollback toàn bộ transaction, không để lại dòng nào trong cả 4 bảng sổ mới."""
    storage = clean_daily_db
    _seed_universe(storage, ["AAA", "BBB"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"AAA": (20_000.0, 20_000.0), "BBB": (30_000.0, 30_000.0)})
    _seed_day_bars(storage, d1, {"AAA": (20_000.0, 21_000.0), "BBB": (30_000.0, 31_000.0)})

    # 1. Dry-run on fresh DB -> 0 rows after rollback
    assert run_daily_engine(dsn=TEST_DSN, dry_run=True, today=d1) == 0
    with storage.conn() as c:
        state_cnt = c.execute("SELECT count(*) FROM paper_daily_state").fetchone()[0]
    assert state_cnt == 0

    # 2. Initialize d0 for real, add pending order, then dry-run on d1 -> zero state/nav/lots mutations persist
    assert run_daily_engine(dsn=TEST_DSN, today=d0) == 0
    with storage.conn() as c:
        c.execute(
            "INSERT INTO paper_daily_orders (strategy, created_date, symbol, side, qty, status) "
            "VALUES ('null', %s, 'AAA', 'BUY', 100, 'pending')",
            (d0,),
        )

    class _BuyOnceOnD1:
        name = "null"

        def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
            return [OrderIntent("BBB", "BUY", 100)]

    assert run_daily_engine(dsn=TEST_DSN, dry_run=True, strategy=_BuyOnceOnD1(), today=d1) == 0

    with storage.conn() as c:
        state = c.execute(
            "SELECT cash, realized_pnl, last_processed_date FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        lots_cnt = c.execute("SELECT count(*) FROM paper_daily_lots").fetchone()[0]
        nav_cnt = c.execute("SELECT count(*) FROM paper_daily_nav").fetchone()[0]
        orders = c.execute("SELECT id, status FROM paper_daily_orders ORDER BY id").fetchall()

    assert state == (CAPITAL, 0.0, d0)
    assert lots_cnt == 0
    assert nav_cnt == 0
    assert orders == [(1, "pending")]


@pytest.mark.integration
def test_integration_five_sessions_buy_and_sell_after_settle_days_hand_calculated(
    clean_daily_db: Storage,
) -> None:
    """§6: Chiến lược giả lập trong test: mua 100 cp ở ngày 1, bán tại ngày 1 + SETTLE_DAYS qua 5 phiên tổng hợp."""
    assert SETTLE_DAYS == 3
    storage = clean_daily_db
    _seed_universe(storage, ["AAA", "BBB"])

    # Trading days Jan 5..Jan 12 2026 (Mon..Fri + Mon = 6 trading days)
    init_d = date(2026, 1, 5)
    sessions = [
        date(2026, 1, 6),   # d1: close -> signal BUY 100 AAA
        date(2026, 1, 7),   # d2: BUY fills at open=20_000 (buy_date = d2)
        date(2026, 1, 8),   # d3: holding (1 session)
        date(2026, 1, 9),   # d4: holding (2 sessions), close -> signal SELL 100 AAA
        date(2026, 1, 12),  # d5 (= buy_date + 3 = buy + SETTLE_DAYS): SELL fills at open=25_000
    ]

    _seed_day_bars(storage, init_d, {"AAA": (19_500.0, 19_800.0), "BBB": (30_000.0, 30_000.0)})
    daily_prices = {
        sessions[0]: {"AAA": (20_000.0, 20_000.0), "BBB": (30_000.0, 30_000.0)},
        sessions[1]: {"AAA": (20_000.0, 21_000.0), "BBB": (30_000.0, 30_500.0)},
        sessions[2]: {"AAA": (21_200.0, 22_000.0), "BBB": (30_500.0, 30_500.0)},
        sessions[3]: {"AAA": (22_500.0, 23_000.0), "BBB": (30_500.0, 31_000.0)},
        sessions[4]: {"AAA": (25_000.0, 24_000.0), "BBB": (31_000.0, 31_200.0)},
    }
    for d, px_map in daily_prices.items():
        _seed_day_bars(storage, d, px_map)

    class _TestBuyHoldSellStrategy:
        name = "test_fake"

        def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
            # Check ctx.bars reads bars_daily up to ctx.d correctly
            hist = ctx.bars("AAA", 2)
            assert all(b.date <= ctx.d for b in hist)
            if ctx.d == sessions[0]:
                return [OrderIntent(symbol="AAA", side="BUY", qty=100)]
            if ctx.d == sessions[3]:
                return [OrderIntent(symbol="AAA", side="SELL", qty=100)]
            return []

    strat = _TestBuyHoldSellStrategy()

    # Step 0: initialize state at init_d
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=init_d) == 0

    # Step 1: process all 5 synthetic sessions sessions[0] .. sessions[4] in one catch-up run
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=sessions[4]) == 0

    # Hand-calculated economics:
    slip = SLIPPAGE_BPS / 10_000.0
    buy_px = 20_000.0 * (1.0 + slip)  # 20_010.0
    buy_val = 100 * buy_px            # 2_001_000.0
    buy_fee = buy_val * FEE_RATE      # 5_602.8
    cash_after_buy = CAPITAL - buy_val - buy_fee  # 97_993_397.2

    sell_px = 25_000.0 * (1.0 - slip)  # 24_987.5
    sell_val = 100 * sell_px           # 2_498_750.0
    sell_fee = sell_val * FEE_RATE     # 6_996.5
    sell_tax = sell_val * SELL_TAX_RATE  # 2_498.75
    sell_proceeds = sell_val - sell_fee - sell_tax  # 2_489_254.75
    cash_after_sell = cash_after_buy + sell_proceeds  # 100_482_651.95
    expected_realized = sell_proceeds - (buy_val + buy_fee)  # 482_651.95

    with storage.conn() as c:
        nav_rows = c.execute(
            "SELECT date, cash, market_value, nav, n_positions FROM paper_daily_nav ORDER BY date"
        ).fetchall()
        state = c.execute(
            "SELECT cash, realized_pnl, last_processed_date FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        lots = c.execute("SELECT symbol, qty FROM paper_daily_lots").fetchall()
        orders = c.execute(
            "SELECT created_date, exec_date, side, qty, filled_qty, status, price, fee, tax "
            "FROM paper_daily_orders ORDER BY id"
        ).fetchall()

    expected_navs = [
        (sessions[0], CAPITAL, 0.0, CAPITAL, 0),
        (sessions[1], cash_after_buy, 100 * 21_000.0, cash_after_buy + 2_100_000.0, 1),
        (sessions[2], cash_after_buy, 100 * 22_000.0, cash_after_buy + 2_200_000.0, 1),
        (sessions[3], cash_after_buy, 100 * 23_000.0, cash_after_buy + 2_300_000.0, 1),
        (sessions[4], cash_after_sell, 0.0, cash_after_sell, 0),
    ]
    assert len(nav_rows) == 5
    for got, exp in zip(nav_rows, expected_navs):
        assert got[0] == exp[0]
        assert got[1] == pytest.approx(exp[1])
        assert got[2] == pytest.approx(exp[2])
        assert got[3] == pytest.approx(exp[3])
        assert got[4] == exp[4]

    assert state[0] == pytest.approx(cash_after_sell)
    assert state[1] == pytest.approx(expected_realized)
    assert state[2] == sessions[4]
    assert lots == []
    assert len(orders) == 2
    assert orders[0] == (sessions[0], sessions[1], "BUY", 100, 100, "filled", pytest.approx(buy_px), pytest.approx(buy_fee), pytest.approx(0.0))
    assert orders[1] == (sessions[3], sessions[4], "SELL", 100, 100, "filled", pytest.approx(sell_px), pytest.approx(sell_fee), pytest.approx(sell_tax))


def test_runner_cli_exits_2_on_unknown_strategy() -> None:
    """CLI with unknown DAILY_ENGINE_STRATEGY exits with code 2 (config error)."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DAILY_ENGINE_STRATEGY"] = "bad_unknown_strategy"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "trading.daily_engine.runner"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 2
    assert "LỖI" in proc.stderr


def test_runner_entrypoint_exits_3_on_unhandled_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """§5.9: Ngoại lệ chưa bắt trong main được bọc và trả mã thoát 3, in traceback ra stderr."""
    import importlib
    import textwrap

    mod = importlib.import_module("trading.daily_engine.runner")

    def failing_main(*_args, **_kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(mod, "main", failing_main)

    runner_path = Path(__file__).resolve().parents[1] / "trading" / "daily_engine" / "runner.py"
    content = runner_path.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in content
    entry_code = textwrap.dedent(content.split('if __name__ == "__main__":')[1])

    with pytest.raises(SystemExit) as exc_info:
        exec(entry_code, mod.__dict__)  # noqa: S102
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "simulated crash" in captured.err


@pytest.mark.integration
def test_mutation_b_interest_added_to_realized_pnl_preserves_ledger_invariant(
    clean_daily_db: Storage,
) -> None:
    """Phép phá (b): Lãi tiền gửi cộng vào cả cash và realized_pnl để giữ bất biến sổ."""
    from trading.daily_engine.strategy import EtfDepositStrategy

    storage = clean_daily_db
    _seed_universe(storage, ["E1VFVN30"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    d2 = date(2026, 1, 7)
    _seed_day_bars(storage, d0, {"E1VFVN30": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d1, {"E1VFVN30": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d2, {"E1VFVN30": (20_000.0, 20_500.0)})

    strat = EtfDepositStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d0) == 0
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d2) == 0

    expected_interest_total = 15_965.358745284597 + 15_967.907672083255
    with storage.conn() as c:
        row = c.execute(
            "SELECT capital, cash, realized_pnl, last_processed_date FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        lots_cost_row = c.execute(
            "SELECT COALESCE(SUM(qty * cost_per_share), 0.0) FROM paper_daily_lots"
        ).fetchone()

    capital, cash, realized_pnl, last_proc = (
        float(row[0]),
        float(row[1]),
        float(row[2]),
        row[3],
    )
    lots_cost = float(lots_cost_row[0])
    assert last_proc == d2
    assert realized_pnl == pytest.approx(expected_interest_total, abs=1e-4)
    assert cash + lots_cost - capital == pytest.approx(realized_pnl, abs=1e-4)


@pytest.mark.integration
def test_mutation_c_rerun_same_day_does_not_accrue_interest_twice(
    clean_daily_db: Storage,
) -> None:
    """Phép phá (c): Chạy lại cùng ngày đã xử lý không cộng lãi lần hai."""
    from trading.daily_engine.strategy import EtfDepositStrategy

    storage = clean_daily_db
    _seed_universe(storage, ["E1VFVN30"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"E1VFVN30": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d1, {"E1VFVN30": (20_000.0, 20_000.0)})

    strat = EtfDepositStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d0) == 0
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d1) == 0
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d1) == 0

    expected_intr = 15_965.358745284597
    with storage.conn() as c:
        cash, realized_pnl = c.execute(
            "SELECT cash, realized_pnl FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        nav_rows = c.execute(
            "SELECT date, interest, cash FROM paper_daily_nav ORDER BY date"
        ).fetchall()

    assert float(cash) == pytest.approx(CAPITAL + expected_intr, abs=1e-4)
    assert float(realized_pnl) == pytest.approx(expected_intr, abs=1e-4)
    assert len(nav_rows) == 1
    assert nav_rows[0][0] == d1
    assert float(nav_rows[0][1]) == pytest.approx(expected_intr, abs=1e-4)
    assert float(nav_rows[0][2]) == pytest.approx(CAPITAL + expected_intr, abs=1e-4)


@pytest.mark.integration
def test_mutation_d_null_strategy_accrues_zero_interest(clean_daily_db: Storage) -> None:
    """Phép phá (d): Chiến lược null có cash_rate=0 nên không được cộng lãi tiền gửi."""
    storage = clean_daily_db
    _seed_universe(storage, ["AAA"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"AAA": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d1, {"AAA": (20_000.0, 21_000.0)})

    assert run_daily_engine(dsn=TEST_DSN, today=d0) == 0
    assert run_daily_engine(dsn=TEST_DSN, today=d1) == 0

    with storage.conn() as c:
        cash, realized_pnl = c.execute(
            "SELECT cash, realized_pnl FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        interest = c.execute(
            "SELECT interest FROM paper_daily_nav WHERE date = %s",
            (d1,),
        ).fetchone()[0]

    assert float(cash) == pytest.approx(CAPITAL)
    assert float(realized_pnl) == pytest.approx(0.0)
    assert float(interest) == pytest.approx(0.0)


@pytest.mark.integration
def test_mutation_e_interest_accrued_before_order_matching_hand_calculated(
    clean_daily_db: Storage,
) -> None:
    """Phép phá (e): Lãi cộng TRƯỚC process_day giúp tiền mặt tăng trước giờ mở cửa khớp lệnh mua."""
    storage = clean_daily_db
    _seed_universe(storage, ["E1VFVN30"])
    d0 = date(2026, 1, 9)   # Friday
    d1 = date(2026, 1, 12)  # Monday -> days = 3
    _seed_day_bars(storage, d0, {"E1VFVN30": (19_900.0, 19_900.0)})
    # Buy cost for 5000 shares @ open=19_935 = 5000 * 19935 * 1.0005 * 1.0028 = 100_004_067.045
    # Initial cash 100_000_000 alone only affords 4900 shares, but + 3-day interest (47_903.7234) affords all 5000!
    _seed_day_bars(storage, d1, {"E1VFVN30": (19_935.0, 20_000.0)})

    class _NoopDepositRateStrategy:
        name = "test_deposit_only"
        cash_rate = 0.06

        def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
            return []

    strat = _NoopDepositRateStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d0) == 0
    with storage.conn() as c:
        c.execute(
            "INSERT INTO paper_daily_orders (strategy, created_date, symbol, side, qty, status) "
            "VALUES ('test_deposit_only', %s, 'E1VFVN30', 'BUY', 5000, 'pending')",
            (d0,),
        )

    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d1) == 0

    with storage.conn() as c:
        order_row = c.execute(
            "SELECT status, filled_qty FROM paper_daily_orders ORDER BY id LIMIT 1"
        ).fetchone()
        state_row = c.execute(
            "SELECT cash, realized_pnl FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        nav_row = c.execute(
            "SELECT interest, cash FROM paper_daily_nav WHERE date = %s",
            (d1,),
        ).fetchone()

    assert order_row == ("filled", 5000)
    assert float(nav_row[0]) == pytest.approx(47_903.723423226016, abs=1e-4)
    assert float(nav_row[1]) == pytest.approx(43_836.67842324078, abs=1e-4)
    assert float(state_row[0]) == pytest.approx(43_836.67842324078, abs=1e-4)
    assert float(state_row[1]) == pytest.approx(47_903.723423226016, abs=1e-4)


@pytest.mark.integration
def test_mutation_j_runner_populates_next_trading_day_correctly(clean_daily_db: Storage) -> None:
    """Phép phá (j): Runner điền ctx.next_trading_day theo is_trading_day + holidays (bỏ qua lễ Tết Tây & cuối tuần)."""
    storage = clean_daily_db
    _seed_universe(storage, ["AAA"])
    d0 = date(2026, 12, 29)
    d1 = date(2026, 12, 30)  # next_trading_day -> 2026-12-31
    d2 = date(2026, 12, 31)  # next_trading_day -> 2027-01-04 (2027-01-01 holiday, 02/03 weekend)
    _seed_day_bars(storage, d0, {"AAA": (10_000.0, 10_000.0)})
    _seed_day_bars(storage, d1, {"AAA": (10_000.0, 10_000.0)})
    _seed_day_bars(storage, d2, {"AAA": (10_000.0, 10_000.0)})

    recorded: list[tuple[date, date | None]] = []

    class _CaptureNextTradingDayStrategy:
        name = "test_next_td"
        cash_rate = 0.0

        def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
            recorded.append((ctx.d, ctx.next_trading_day))
            return []

    strat = _CaptureNextTradingDayStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d0) == 0
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d2) == 0

    assert recorded == [
        (date(2026, 12, 30), date(2026, 12, 31)),
        (date(2026, 12, 31), date(2027, 1, 4)),
    ]


@pytest.mark.integration
def test_mutation_k_dry_run_leaves_no_interest_or_orders_in_db(clean_daily_db: Storage) -> None:
    """Phép phá (k): --dry-run rollback toàn bộ, không để lại lãi tiền gửi hay lệnh trong DB."""
    from trading.daily_engine.strategy import EtfDepositStrategy

    storage = clean_daily_db
    _seed_universe(storage, ["E1VFVN30"])
    d0 = date(2026, 1, 5)
    d1 = date(2026, 1, 6)
    _seed_day_bars(storage, d0, {"E1VFVN30": (20_000.0, 20_000.0)})
    _seed_day_bars(storage, d1, {"E1VFVN30": (20_000.0, 20_000.0)})

    strat = EtfDepositStrategy()
    assert run_daily_engine(dsn=TEST_DSN, strategy=strat, today=d0) == 0
    assert run_daily_engine(dsn=TEST_DSN, dry_run=True, strategy=strat, today=d1) == 0

    with storage.conn() as c:
        state = c.execute(
            "SELECT cash, realized_pnl, last_processed_date FROM paper_daily_state WHERE id = 1"
        ).fetchone()
        nav_cnt = c.execute("SELECT count(*) FROM paper_daily_nav").fetchone()[0]
        orders_cnt = c.execute("SELECT count(*) FROM paper_daily_orders").fetchone()[0]

    assert state == (CAPITAL, 0.0, d0)
    assert nav_cnt == 0
    assert orders_cnt == 0
