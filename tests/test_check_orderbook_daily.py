"""Kiểm thử đơn vị cho scripts/check_orderbook_daily.py (Brief 94 Task 2).

Kiểm tra:
1. Hàm thuần evaluate_daily_orderbook_check:
   - Ngày không giao dịch -> thoát 0 im lặng (alert_level=None, is_silent=True).
   - Ngày giao dịch nhưng file không tồn tại -> thoát 2, alert CRITICAL.
   - File có nhưng không đạt nghiệm thu -> thoát 1, alert WARN.
   - File có và đạt nghiệm thu -> thoát 0 im lặng (alert_level=None, is_silent=True).
2. Quy trình check_orderbook_daily:
   - Ngày không giao dịch -> thoát 0, không gọi alert.
   - File thiếu trên ngày giao dịch -> gọi alert("CRITICAL", ...), thoát 2.
   - File không đạt -> gọi alert("WARN", ...), thoát 1.
   - File đạt -> thoát 0, không gọi alert.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts.check_orderbook_daily import (
    check_orderbook_daily,
    evaluate_daily_orderbook_check,
)
from scripts.verify_orderbook_file import OrderbookMetrics, VerificationResult


def test_evaluate_daily_check_non_trading_day():
    """Ca 1: Ngày không giao dịch -> Thoát 0 im lặng (không alert)."""
    decision = evaluate_daily_orderbook_check(
        is_trading_day=False,
        file_exists=False,
        target_date=date(2026, 9, 26),
    )
    assert decision.exit_code == 0
    assert decision.is_silent is True
    assert decision.alert_level is None
    assert "không phải ngày giao dịch" in decision.message


def test_evaluate_daily_check_file_missing_on_trading_day():
    """Ca 2: Ngày giao dịch nhưng file không tồn tại -> Thoát 2, alert CRITICAL."""
    decision = evaluate_daily_orderbook_check(
        is_trading_day=True,
        file_exists=False,
        target_date=date(2026, 9, 28),
        symbol="41I1GA000",
    )
    assert decision.exit_code == 2
    assert decision.is_silent is False
    assert decision.alert_level == "CRITICAL"
    assert "không tìm thấy file" in decision.message
    assert "41I1GA000" in decision.message
    assert len(decision.reasons) > 0


def test_evaluate_daily_check_file_exists_verification_fails():
    """Ca 3: File tồn tại nhưng không đạt chuẩn nghiệm thu -> Thoát 1, alert WARN."""
    failed_result = VerificationResult(
        is_valid=False,
        reasons=["Độ phủ phiên chỉ đạt 45.0%, thiếu 28 ô."],
        criteria_status={"parseable": True, "coverage": False, "front_month": True},
        expected_front_month="41I1GA000",
        front_month_error=None,
    )

    decision = evaluate_daily_orderbook_check(
        is_trading_day=True,
        file_exists=True,
        verification_result=failed_result,
        target_date=date(2026, 9, 28),
        symbol="41I1GA000",
    )
    assert decision.exit_code == 1
    assert decision.is_silent is False
    assert decision.alert_level == "WARN"
    assert "không đạt tiêu chuẩn" in decision.message
    assert "Độ phủ phiên chỉ đạt 45.0%" in decision.message


def test_evaluate_daily_check_file_exists_verification_passes():
    """Ca 4: File tồn tại và đạt chuẩn nghiệm thu -> Thoát 0 im lặng (không alert)."""
    passed_result = VerificationResult(
        is_valid=True,
        reasons=[],
        criteria_status={"parseable": True, "coverage": True, "front_month": True},
        expected_front_month="41I1GA000",
        front_month_error=None,
    )

    decision = evaluate_daily_orderbook_check(
        is_trading_day=True,
        file_exists=True,
        verification_result=passed_result,
        target_date=date(2026, 9, 28),
        symbol="41I1GA000",
    )
    assert decision.exit_code == 0
    assert decision.is_silent is True
    assert decision.alert_level is None
    assert "đạt đầy đủ tiêu chuẩn" in decision.message


async def test_check_orderbook_daily_workflow_non_trading_day():
    """Workflow: Ngày không giao dịch -> thoát 0 im lặng, không phát alert."""
    with (
        patch("scripts.check_orderbook_daily.is_trading_day", return_value=False),
        patch("scripts.check_orderbook_daily.alert") as mock_alert,
    ):
        code = await check_orderbook_daily(target_date=date(2026, 9, 26))
        assert code == 0
        mock_alert.assert_not_called()


async def test_check_orderbook_daily_workflow_missing_file(tmp_path: Path):
    """Workflow: Ngày giao dịch nhưng thiếu file -> alert CRITICAL, thoát 2."""
    symbol = "41I1GA000"
    target_d = date(2026, 9, 28)

    with (
        patch("scripts.check_orderbook_daily.is_trading_day", return_value=True),
        patch("scripts.check_orderbook_daily.resolve_front_month_symbol", AsyncMock(return_value=symbol)),
        patch("scripts.check_orderbook_daily.alert") as mock_alert,
    ):
        code = await check_orderbook_daily(
            target_date=target_d,
            symbol=symbol,
            data_dir=tmp_path,
        )
        assert code == 2
        mock_alert.assert_called_once()
        call_args, call_kwargs = mock_alert.call_args
        assert call_args[0] == "CRITICAL"
        assert symbol in call_args[1]
        assert "không tìm thấy file" in call_args[1]
        assert call_kwargs.get("symbol") == symbol


async def test_check_orderbook_daily_workflow_verification_failed(tmp_path: Path):
    """Workflow: File tồn tại nhưng nghiệm thu không đạt -> alert WARN, thoát 1."""
    symbol = "41I1GA000"
    target_d = date(2026, 9, 28)

    file_dir = tmp_path / symbol
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / f"{target_d.isoformat()}.jsonl.gz"
    with gzip.open(file_path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"type": "QUOTE", "symbol": symbol, "recv_ts": f"{target_d}T09:00:00+07:00"}) + "\n")

    mock_metrics = OrderbookMetrics(
        symbol=symbol,
        target_date=target_d,
        counts={"QUOTE": 1, "TRADE": 0, "OTHER": 0},
        unparseable_lines=0,
        first_recv_ts=None,
        last_recv_ts=None,
        total_slots=51,
        covered_slots=1,
        coverage_ratio=1 / 51,
        empty_slots=["09:05-09:10"],
    )
    mock_result = VerificationResult(
        is_valid=False,
        reasons=["Độ phủ phiên chỉ đạt 2.0% (1/51 ô), thấp hơn ngưỡng tối thiểu 90%."],
        criteria_status={"parseable": True, "coverage": False, "front_month": True},
        expected_front_month=symbol,
        front_month_error=None,
    )

    with (
        patch("scripts.check_orderbook_daily.is_trading_day", return_value=True),
        patch("scripts.check_orderbook_daily.verify_orderbook_file", AsyncMock(return_value=(mock_metrics, mock_result))),
        patch("scripts.check_orderbook_daily.alert") as mock_alert,
    ):
        code = await check_orderbook_daily(
            target_date=target_d,
            symbol=symbol,
            data_dir=tmp_path,
        )
        assert code == 1
        mock_alert.assert_called_once()
        call_args, call_kwargs = mock_alert.call_args
        assert call_args[0] == "WARN"
        assert "không đạt tiêu chuẩn" in call_args[1]
        assert call_kwargs.get("symbol") == symbol


async def test_check_orderbook_daily_workflow_verification_passed(tmp_path: Path):
    """Workflow: File tồn tại và đạt nghiệm thu -> thoát 0, KHÔNG phát alert."""
    symbol = "41I1GA000"
    target_d = date(2026, 9, 28)

    file_dir = tmp_path / symbol
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / f"{target_d.isoformat()}.jsonl.gz"
    with gzip.open(file_path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"type": "QUOTE", "symbol": symbol, "recv_ts": f"{target_d}T09:00:00+07:00"}) + "\n")

    mock_metrics = OrderbookMetrics(
        symbol=symbol,
        target_date=target_d,
        counts={"QUOTE": 10000, "TRADE": 5000, "OTHER": 0},
        unparseable_lines=0,
        first_recv_ts=None,
        last_recv_ts=None,
        total_slots=51,
        covered_slots=51,
        coverage_ratio=1.0,
        empty_slots=[],
    )
    mock_result = VerificationResult(
        is_valid=True,
        reasons=[],
        criteria_status={"parseable": True, "coverage": True, "front_month": True},
        expected_front_month=symbol,
        front_month_error=None,
    )

    with (
        patch("scripts.check_orderbook_daily.is_trading_day", return_value=True),
        patch("scripts.check_orderbook_daily.verify_orderbook_file", AsyncMock(return_value=(mock_metrics, mock_result))),
        patch("scripts.check_orderbook_daily.alert") as mock_alert,
    ):
        code = await check_orderbook_daily(
            target_date=target_d,
            symbol=symbol,
            data_dir=tmp_path,
        )
        assert code == 0
        mock_alert.assert_not_called()
