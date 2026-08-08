from datetime import date

from trading.derivative_risk import DerivativeRiskManager


def test_approve_open_allows_first_open_when_flat():
    risk = DerivativeRiskManager(capital=100_000_000, max_contracts=1)
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=date(2026, 8, 8)) is True


def test_approve_open_blocks_beyond_max_contracts():
    risk = DerivativeRiskManager(capital=100_000_000, max_contracts=1)
    # Da co 1 hop dong dang mo (current_qty=1) - mo them se vuot max_contracts=1.
    assert risk.approve_open("long", current_qty=1, daily_pnl=0.0, today=date(2026, 8, 8)) is False


def test_approve_open_blocks_when_daily_loss_exceeds_threshold():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    today = date(2026, 8, 8)
    # Lo vuot 3% von (-3,000,000) -> halt ngay lan goi nay.
    assert risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=today) is False
    assert risk.halted_date == today


def test_approve_open_stays_blocked_rest_of_day_even_if_pnl_recovers():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    today = date(2026, 8, 8)
    risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=today)
    # Cung ngay, daily_pnl da hoi phuc ve 0 - van bi chan vi halted_date da khoa ca ngay.
    assert risk.approve_open("short", current_qty=0, daily_pnl=0.0, today=today) is False


def test_halt_does_not_persist_to_next_day():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    day1 = date(2026, 8, 8)
    day2 = date(2026, 8, 9)
    risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=day1)
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=day2) is True


def test_no_approve_close_method_exists_closes_are_never_gated():
    # Lenh dong vi the KHONG bi gate boi bat ky method nao cua
    # DerivativeRiskManager (khac approve_open danh cho lenh mo).
    risk = DerivativeRiskManager(capital=100_000_000)
    assert not hasattr(risk, "approve_close")
