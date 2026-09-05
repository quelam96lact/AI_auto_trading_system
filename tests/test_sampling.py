"""Unit tests cho module trading/sampling.py (Tiêu chí 5 của Brief đợt 9)."""

from datetime import datetime

import pytest

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.sampling import (
    filter_bars_by_split,
)


def _make_bar(d_str: str, symbol: str = "VCB") -> Bar:
    dt = datetime.strptime(d_str, "%Y-%m-%d").replace(tzinfo=TZ)
    return Bar(symbol, dt, 100.0, 105.0, 95.0, 100.0, 100_000)


def test_train_and_val_split_accessible_without_unlock():
    bars = [
        _make_bar("2018-05-10"),  # Train
        _make_bar("2023-01-15"),  # Val
        _make_bar("2025-03-20"),  # Holdout
    ]

    train_bars = filter_bars_by_split(bars, "train")
    assert len(train_bars) == 1
    assert train_bars[0].ts.date().year == 2018

    val_bars = filter_bars_by_split(bars, "validation")
    assert len(val_bars) == 1
    assert val_bars[0].ts.date().year == 2023


def test_holdout_locked_by_mechanism_raises_permission_error():
    bars = [
        _make_bar("2018-05-10"),
        _make_bar("2025-03-20"),  # Holdout
    ]

    # Truy cập holdout không có cờ -> Bắt buộc raise PermissionError
    with pytest.raises(PermissionError) as excinfo:
        filter_bars_by_split(bars, "holdout", unlock_holdout=False)
    assert "HOLDOUT" in str(excinfo.value)

    # Truy cập all chứa holdout không có cờ -> Raise PermissionError
    with pytest.raises(PermissionError):
        filter_bars_by_split(bars, "all", unlock_holdout=False)


def test_holdout_unlocked_with_flag_and_logs(tmp_path):
    log_file = tmp_path / "test-holdout-log.md"

    bars = [
        _make_bar("2018-05-10"),
        _make_bar("2025-03-20"),  # Holdout
    ]

    holdout_bars = filter_bars_by_split(
        bars,
        "holdout",
        unlock_holdout=True,
        strategy_name="OctopusTest",
        config_info="k_tp=2.0",
        unlock_reason="Final pre-live validation",
        log_file=str(log_file),
    )

    assert len(holdout_bars) == 1
    assert holdout_bars[0].ts.date().year == 2025

    # Kiểm tra nội dung log file đã được tạo
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "OctopusTest" in content
    assert "Final pre-live validation" in content
