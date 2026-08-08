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


def test_default_max_daily_loss_pct_is_2_percent():
    # Theo file nguoi dung de xuat: dung ngay khi lo 2% von.
    risk = DerivativeRiskManager(capital=100_000_000)
    assert risk.max_daily_loss_pct == 0.02


def test_approve_open_blocks_after_two_consecutive_losing_trades():
    risk = DerivativeRiskManager(capital=100_000_000)  # max_consecutive_losses=2 mac dinh
    today = date(2026, 8, 8)
    risk.record_trade_result(pnl=-100_000, today=today)
    # Moi 1 lenh thua - van duoc mo lenh tiep.
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=today) is True
    risk.record_trade_result(pnl=-50_000, today=today)
    # Lenh thua thu 2 lien tiep -> halt.
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=today) is False
    assert risk.halted_date == today


def test_consecutive_loss_streak_resets_on_winning_trade():
    risk = DerivativeRiskManager(capital=100_000_000)
    today = date(2026, 8, 8)
    risk.record_trade_result(pnl=-1.0, today=today)
    risk.record_trade_result(pnl=+1.0, today=today)  # lenh thang reset streak
    risk.record_trade_result(pnl=-1.0, today=today)  # streak chi con 1
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=today) is True


def test_consecutive_loss_streak_resets_next_day():
    risk = DerivativeRiskManager(capital=100_000_000)
    day1 = date(2026, 8, 8)
    day2 = date(2026, 8, 9)
    risk.record_trade_result(pnl=-1.0, today=day1)
    risk.record_trade_result(pnl=-1.0, today=day1)
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=day1) is False
    assert risk.halted_date == day1
    # Sang ngay mai: streak reset theo ngay, khong con halt.
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=day2) is True
