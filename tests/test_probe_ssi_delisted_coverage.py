"""Unit tests cho scripts/probe_ssi_delisted_coverage.py (TDD, không gọi mạng thật)."""

import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.probe_ssi_delisted_coverage import (
    RateLimiter,
    analyze_probe_results,
    generate_3letter_symbols,
    probe_symbol_with_retry,
    run_probe_workflow,
)
from trading.calendar_vn import TZ
from trading.models import Bar


def _make_bar(symbol: str, d: date, close: float = 10000.0) -> Bar:
    dt = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10000,
    )


def test_sinh_dung_17576_ma_khong_trung_dung_thu_tu():
    """1. Sinh đúng 17.576 mã, không trùng, đúng thứ tự từ AAA đến ZZZ."""
    all_syms = generate_3letter_symbols()
    assert len(all_syms) == 17576
    assert len(set(all_syms)) == 17576
    assert all_syms[0] == "AAA"
    assert all_syms[1] == "AAB"
    assert all_syms[-1] == "ZZZ"
    assert all_syms == sorted(all_syms)

    # Thử theo prefix
    a_syms = generate_3letter_symbols(prefix="A")
    assert len(a_syms) == 676
    assert a_syms[0] == "AAA"
    assert a_syms[-1] == "AZZ"


@pytest.mark.asyncio
async def test_chay_tiep_bo_qua_ma_da_co_tien_do():
    """2. Chạy tiếp: file tiến độ có sẵn mã -> chỉ gọi API cho các mã còn lại."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prog_file = Path(tmpdir) / "progress.json"
        # Giả lập đã có 3 mã trong file tiến độ
        import json

        initial_data = {
            "AAA": {
                "count": 100,
                "first_date": "2016-01-04",
                "last_date": "2022-12-30",
                "error": None,
            },
            "AAB": {
                "count": 0,
                "first_date": None,
                "last_date": None,
                "error": None,
            },
            "AAC": {
                "count": 50,
                "first_date": "2016-01-04",
                "last_date": "2018-05-10",
                "error": None,
            },
        }
        prog_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

        client = MagicMock()
        client.daily_ohlc = AsyncMock(return_value=[_make_bar("AAD", date(2021, 5, 1))])

        storage = MagicMock()
        storage.conn.return_value.__enter__.return_value.fetchall.return_value = [
            ("AAA",)
        ]

        # Khảo sát 5 mã (AAA, AAB, AAC, AAD, AAE)
        target_syms = ["AAA", "AAB", "AAC", "AAD", "AAE"]
        await run_probe_workflow(
            client=client,
            storage=storage,
            symbols=target_syms,
            progress_path=prog_file,
            throttle_seconds=0.0,
            save_interval=1,
        )

        # client.daily_ohlc chỉ được gọi đúng 2 lần (cho AAD và AAE)
        assert client.daily_ohlc.call_count == 2
        called_symbols = [
            call_args[0][0] for call_args in client.daily_ohlc.call_args_list
        ]
        assert called_symbols == ["AAD", "AAE"]


@pytest.mark.asyncio
async def test_chay_tiep_do_lai_ma_tung_loi():
    """Sửa của Claude khi audit: mã có 'error' trong file tiến độ (hết lượt thử 429)
    phải được dò lại khi chạy tiếp, không bị coi là đã xong."""
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        prog_file = Path(tmpdir) / "progress.json"
        prog_file.write_text(
            json.dumps(
                {
                    "AAA": {
                        "count": 0,
                        "first_date": None,
                        "last_date": None,
                        "error": None,
                    },
                    "AAB": {
                        "count": 0,
                        "first_date": None,
                        "last_date": None,
                        "error": "Exception: Rate limit exceeded",
                    },
                }
            ),
            encoding="utf-8",
        )
        client = MagicMock()
        client.daily_ohlc = AsyncMock(return_value=[_make_bar("AAB", date(2021, 5, 1))])
        storage = MagicMock()
        storage.conn.return_value.__enter__.return_value.fetchall.return_value = []

        await run_probe_workflow(
            client=client,
            storage=storage,
            symbols=["AAA", "AAB"],
            progress_path=prog_file,
            throttle_seconds=0.0,
            save_interval=1,
        )

        assert [c[0][0] for c in client.daily_ohlc.call_args_list] == ["AAB"]
        saved = json.loads(prog_file.read_text(encoding="utf-8"))
        assert saved["AAB"]["error"] is None and saved["AAB"]["count"] == 1


@pytest.mark.asyncio
async def test_loi_429_thu_lai_va_giu_ma():
    """3. Lỗi 429 cho một mã -> thử lại mã đó với backoff và lưu kết quả thành công."""
    client = MagicMock()
    call_counts = {"ERR_ONCE": 0}

    async def _mock_daily_ohlc(symbol: str, frm: date, to: date):
        if symbol == "ERR_ONCE":
            call_counts["ERR_ONCE"] += 1
            if call_counts["ERR_ONCE"] < 3:
                raise RuntimeError("429 Client Error: Too Many Requests")
            return [_make_bar("ERR_ONCE", date(2021, 1, 10))]
        return []

    client.daily_ohlc = AsyncMock(side_effect=_mock_daily_ohlc)

    res = await probe_symbol_with_retry(
        client=client,
        symbol="ERR_ONCE",
        frm=date(2016, 1, 1),
        to=date(2022, 12, 31),
        max_retries=3,
        base_backoff=0.01,
    )

    assert res["count"] == 1
    assert res["error"] is None
    assert call_counts["ERR_ONCE"] == 3


def test_tinh_ma_thieu_va_do_nhay_dung():
    """4. Tính mã thiếu và độ nhạy đúng trên tập dữ liệu giả định."""
    probed = {
        "AAA": {
            "count": 250,
            "first_date": "2016-01-04",
            "last_date": "2022-12-30",
        },
        "AAB": {
            "count": 100,
            "first_date": "2016-01-04",
            "last_date": "2022-12-30",
        },
        "AAC": {
            "count": 0,
            "first_date": None,
            "last_date": None,
        },  # Không có nến
        "AAD": {
            "count": 80,
            "first_date": "2016-01-04",
            "last_date": "2019-05-10",
        },  # Thiếu (chết trong IS)
        "AAE": {
            "count": 200,
            "first_date": "2016-01-04",
            "last_date": "2022-10-15",
        },  # Thiếu (sống sau IS)
    }
    db_symbols = {"AAA", "AAB"}  # DB có AAA và AAB

    analysis = analyze_probe_results(
        probed_data=probed,
        db_symbols=db_symbols,
        symbol_subset=["AAA", "AAB", "AAC", "AAD", "AAE"],
    )

    assert analysis["total_probed"] == 5
    assert analysis["s_count"] == 4  # AAA, AAB, AAD, AAE
    assert analysis["db_in_scope_count"] == 2
    assert analysis["matched_db_count"] == 2
    assert analysis["missed_db"] == []
    assert analysis["sensitivity"] == 1.0

    assert analysis["missing_count"] == 2  # AAD và AAE
    assert analysis["dead_in_is_count"] == 1
    assert analysis["dead_in_is"][0]["symbol"] == "AAD"
    assert analysis["other_missing_count"] == 1
    assert analysis["other_missing"][0]["symbol"] == "AAE"


@pytest.mark.asyncio
async def test_nhip_goi_khong_nhanh_hon_1_giay():
    """5. Nhịp gọi: RateLimiter đảm bảo các lần gọi cách nhau tối thiểu interval."""
    interval = 0.05
    limiter = RateLimiter(interval_seconds=interval)

    t0 = time.time()
    for _ in range(5):
        await limiter.wait()
    t1 = time.time()

    total_time = t1 - t0
    # 5 lần gọi với interval 0.05s sẽ mất tối thiểu ~ 4 * 0.05s = 0.20s
    assert total_time >= (4 * interval * 0.85)


@pytest.mark.asyncio
async def test_khong_goi_ham_ghi_db():
    """6. Khẳng định không có bất kỳ lời gọi ghi DB nào."""
    mock_storage = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("AAA",)]
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_cursor
    mock_storage.conn.return_value = mock_conn

    mock_storage.write_daily = MagicMock()
    mock_storage.write_bars = MagicMock()

    client = MagicMock()
    client.daily_ohlc = AsyncMock(return_value=[_make_bar("AAA", date(2021, 1, 10))])

    with tempfile.TemporaryDirectory() as tmpdir:
        prog_file = Path(tmpdir) / "prog.json"
        await run_probe_workflow(
            client=client,
            storage=mock_storage,
            symbols=["AAA"],
            progress_path=prog_file,
            throttle_seconds=0.0,
        )

    mock_storage.write_daily.assert_not_called()
    mock_storage.write_bars.assert_not_called()

    for call_item in mock_cursor.execute.call_args_list:
        query = call_item[0][0].strip().upper()
        assert query.startswith("SELECT"), f"Phát hiện query ghi DB: {query}"


def test_khong_chua_chuoi_http():
    """7. File script tuyệt đối không chứa chuỗi 'http' nào."""
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "probe_ssi_delisted_coverage.py"
    )
    content = script_path.read_text(encoding="utf-8")
    assert (
        "http" not in content.lower()
    ), "Phát hiện chuỗi 'http' trong scripts/probe_ssi_delisted_coverage.py!"
