import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from trading.calendar_vn import TZ
from trading.derivative_backtest import DERIVATIVE_SYMBOL, run_derivative_backtest
from trading.derivative_position import DERIVATIVE_CONTRACT_MULTIPLIER
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy

CAP = 100_000_000
FEE = 8_250.0


def bars_from_prices(prices: list[float], sym: str = DERIVATIVE_SYMBOL) -> list[Bar]:
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate(prices)
    ]


def new_strategy() -> SmaCrossStrategy:
    # fast=2/slow=4, atr_pct_threshold=0.0: tat filter ATR% de crossover
    # khong bi che (cung ky thuat da dung trong tests/test_engine_logic.py
    # cho trailing-stop test) - qty=1 vi lot_size phai sinh = 1.
    return SmaCrossStrategy(fast=2, slow=4, qty=1, atr_period=1, atr_pct_threshold=0.0)


def test_report_unrealized_pnl_applies_contract_multiplier():
    # Chuoi gia da xac nhan that (chay qua compute_crossover truc tiep): bull
    # tai bar4 (close=11) mo long, cac bar sau tiep tuc uptrend, KHONG co bear
    # crossover -> vi the con mo o cuoi chuoi, mark = close bar6 (16).
    # _unrealized() phai nhan he so nhan hop dong (100,000 VND/diem), khong
    # tru fee (hanh vi hien tai giu nguyen - chi them he so nhan).
    prices = [10, 10, 10, 10, 11, 13, 16]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    expected_unrealized = (16.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER
    assert len(report.fills) == 1  # chi mo long, chua co lenh dong
    assert abs(report.unrealized_pnl - expected_unrealized) < 1e-9


def test_long_cycle_bull_opens_long_then_bear_closes_it():
    # Chuoi gia da xac nhan that (chay qua SmaCrossStrategy.compute_crossover
    # truc tiep de lay index bull/bear that, khong doan tay): bull tai bar4
    # (close=11), bear tai bar10 (close=16).
    prices = [10, 10, 10, 10, 11, 13, 16, 20, 24, 20, 16, 12, 9, 7]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert (
        open_fill.side == "BUY"
        and open_fill.qty == 1
        and abs(open_fill.price - 11.0) < 1e-9
    )
    assert (
        close_fill.side == "SELL"
        and close_fill.qty == 1
        and abs(close_fill.price - 16.0) < 1e-9
    )
    expected_pnl = (16.0 - 11.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert abs(report.realized_pnl - expected_pnl) < 1e-9
    assert report.trades == 1


def test_short_cycle_bear_opens_short_from_flat_then_bull_covers_it():
    # Chuoi gia da xac nhan that: bear tai bar5 (close=9, tu trang thai
    # flat - chua tung mo long truoc do), bull tai bar8 (close=12, cover).
    prices = [10, 11, 12, 14, 12, 9, 6, 9, 12, 15]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert (
        open_fill.side == "SELL"
        and open_fill.qty == 1
        and abs(open_fill.price - 9.0) < 1e-9
    )
    assert (
        close_fill.side == "BUY"
        and close_fill.qty == 1
        and abs(close_fill.price - 12.0) < 1e-9
    )
    expected_pnl = (9.0 - 12.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert close_fill.pnl < 0
    assert abs(report.realized_pnl - expected_pnl) < 1e-9


def test_halted_day_blocks_new_open_after_loss_breaches_threshold():
    # Chuoi gia da xac nhan that (chay qua compute_crossover truc tiep, khong
    # doan tay): bull bar4 (close=11) mo long, bear bar8 (close=10) dong.
    # Round-trip dau tien LO THAT sau khi co he so nhan:
    # (10-11)*1*100,000 - 8,250 = -108,250 - khong con la "lo ao" do phi che
    # mat lai 5 diem nhu chuoi cu (16-11)*100,000-8,250 = +491,750 (LAI).
    prices = [10, 10, 10, 10, 11, 13, 16, 13, 10, 7, 9, 12, 16, 20]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    # Von nho de khoan lo round-trip dau tien (-102,700) vuot nguong 3% cua
    # 50,000 (=-1,500).
    risk = DerivativeRiskManager(
        capital=50_000, max_contracts=1, max_daily_loss_pct=0.03
    )

    report = run_derivative_backtest(bars, strategy, risk, 50_000)

    # Chi co dung 2 fill (mo bar4, dong bar8) - bull thu 2 tai bar11 KHONG
    # duoc mo vi da bi halt do lo round-trip dau vuot nguong.
    assert len(report.fills) == 2
    assert risk.halted_date is not None


def test_real_captured_ohlc_sample_runs_end_to_end():
    # Smoke test doi voi du lieu OHLC that da capture (Phase 0/khao sat
    # 2026-08-07) - dam bao code chay duoc voi shape response that, khong
    # chi bar tong hop. File nay gitignored (du lieu that), khong commit -
    # skip gon neu khong co san thay vi fail.
    sample_path = Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json")
    if not sample_path.exists():
        pytest.skip(
            "scripts/.spike_derivative_ohlc_5m_2m_sample.json khong co san (gitignored)"
        )

    raw = json.loads(sample_path.read_text())
    bars = sorted(
        (
            Bar(
                row["symbol"],
                datetime.strptime(row["trading_date"], "%Y/%m/%d %H:%M:%S").replace(
                    tzinfo=TZ
                ),
                row["open_price"],
                row["high_price"],
                row["low_price"],
                row["close_price"],
                int(row["volume"]),
            )
            for row in raw
        ),
        key=lambda b: b.ts,
    )
    strategy = SmaCrossStrategy(
        qty=1
    )  # tham so mac dinh (fast=10/slow=20) - khong ep crossover
    risk = DerivativeRiskManager(capital=CAP)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    # Khong assert crossover cu the nao xay ra (du lieu that, khong kiem
    # soat duoc) - chi chung minh code chay het toan bo bar that ma khong
    # loi/crash, va bao cao co hinh dang hop le: moi fill "mo" (pnl=None)
    # phai co dung 1 fill "dong" (pnl khong None) di kem, tru toi da 1 vi
    # the con dang mo o cuoi chuoi du lieu (chua co bar nao dong no).
    opens = [f for f in report.fills if f.pnl is None]
    closes = [f for f in report.fills if f.pnl is not None]
    assert report.trades == len(closes)
    assert len(opens) - len(closes) in (0, 1)
    assert isinstance(report.realized_pnl, float)
