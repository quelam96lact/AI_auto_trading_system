"""Test suite cho scripts/fetch_dnse_vn30f_trades.py (Brief đợt 186 Tests 1..7)."""

from __future__ import annotations

import gzip
from datetime import date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.fetch_dnse_vn30f_trades import (
    fetch_session_trades,
    front_month_symbol,
    main,
    parse_trade_second,
    save_session_trades,
    volume_continuity,
)
from trading.calendar_vn import TZ


class MockMarket:
    """Mock API DNSE Market: mới nhất trước, limit <= 1000, to không gồm chính giây đó."""

    def __init__(self, trades: list[dict[str, Any]]):
        self._trades = trades
        self.call_count = 0

    def trades(
        self,
        symbol: str,
        board_id: Any,
        from_ts: str,
        to_ts: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        self.call_count += 1
        f = int(from_ts)
        t = int(to_ts)
        matching = []
        for tr in self._trades:
            sec = parse_trade_second(tr["time"])
            if f <= sec < t:
                matching.append(tr)

        # Mới nhất trước: sắp xếp theo (thời gian giây desc, total_volume_traded desc)
        matching.sort(
            key=lambda x: (parse_trade_second(x["time"]), int(x.get("total_volume_traded", 0))),
            reverse=True,
        )
        return matching[:limit]


class MockClient:
    def __init__(self, trades: list[dict[str, Any]]):
        self.market = MockMarket(trades)
        self.board_id = "G1"


# --- Test 1: front_month_symbol ---
def test_1_front_month_symbol():
    """Kiểm tra mã hợp đồng front-month theo ngày."""
    assert front_month_symbol(date(2026, 3, 25)) == "41I1G4000"
    assert front_month_symbol(date(2026, 4, 16)) == "41I1G4000"  # Đáo hạn tháng 4
    assert front_month_symbol(date(2026, 4, 17)) == "41I1G5000"  # Sau đáo hạn tháng 4
    assert front_month_symbol(date(2026, 9, 17)) == "41I1G9000"  # Đáo hạn tháng 9
    assert front_month_symbol(date(2026, 9, 18)) == "41I1GA000"  # Sau đáo hạn tháng 9 (tháng 10 mã A)


# --- Test 2: Phân trang API ---
def test_2_pagination():
    """3.500 lệnh giả, nhiều giây có 3-5 lệnh vắt qua ranh giới trang -> đủ đúng 3.500, không trùng, missing_continuous == 0."""
    total_trades = 3500
    mock_trades = []
    d = date(2026, 4, 1)

    # Sinh 3.500 lệnh rải từ 09:00:00 trở đi, có các cụm 4 lệnh cùng giây vắt qua ranh giới trang (500, 1500, 2500)
    cur_sec = int(datetime(2026, 4, 1, 9, 0, 0, tzinfo=TZ).timestamp())
    for i in range(1, total_trades + 1):
        if i in (499, 500, 501, 502, 1499, 1500, 1501, 1502, 2499, 2500, 2501, 2502):
            pass  # Giữ cùng giây để vắt qua ranh giới trang
        else:
            cur_sec += 1
        dt = datetime.fromtimestamp(cur_sec, tz=TZ)
        mock_trades.append(
            {
                "market_id": "DVX",
                "board_id": "G1",
                "symbol": "41I1G4000",
                "match_price": 1800.0,
                "match_qtty": 1,
                "side": "BUY",
                "total_volume_traded": i,
                "time": dt.strftime("%Y-%m-%d %H:%M:%S.000"),
            }
        )

    client = MockClient(mock_trades)
    dummy_sleep = MagicMock()

    rows, _info = fetch_session_trades(client, "41I1G4000", d, sleep_fn=dummy_sleep)

    assert len(rows) == total_trades
    # Kiểm tra không trùng lặp total_volume_traded
    seen_tv = set()
    for r in rows:
        assert r["total_volume_traded"] not in seen_tv
        seen_tv.add(r["total_volume_traded"])

    cont = volume_continuity(rows)
    assert cont["missing_continuous"] == 0
    assert cont["total_volume"] == total_trades


# --- Test 3: Giây kẹt ---
def test_3_stuck_second():
    """1.200 lệnh cùng giây 14:45:00 -> hàm kết thúc, stuck_seconds >= 1, phần thiếu nằm ở missing_outside."""
    total_trades = 1200
    mock_trades = []
    d = date(2026, 4, 1)
    stuck_time_str = "2026-04-01 14:45:00.000"

    for i in range(1, total_trades + 1):
        mock_trades.append(
            {
                "market_id": "DVX",
                "board_id": "G1",
                "symbol": "41I1G4000",
                "match_price": 1800.0,
                "match_qtty": 1,
                "side": "BUY",
                "total_volume_traded": i,
                "time": stuck_time_str,
            }
        )

    client = MockClient(mock_trades)
    dummy_sleep = MagicMock()

    rows, info = fetch_session_trades(client, "41I1G4000", d, sleep_fn=dummy_sleep)

    # Vì limit=1000 và 1200 lệnh cùng giây, hàm chỉ lấy được 1000 lệnh mới nhất (trades 201..1200)
    assert len(rows) == 1000
    assert info["stuck_seconds"] >= 1
    # 200 lệnh đầu bị thiếu tại 14:45:00 (ngoài phiên liên tục)
    cont = volume_continuity(rows)
    assert cont["missing_continuous"] == 0
    assert cont["missing_outside"] == 200


# --- Test 4: Tính liên tục của khối lượng (volume_continuity) ---
def test_4_volume_continuity():
    """Khoảng thiếu ATO -> missing_outside; khoảng thiếu 10:00 -> missing_continuous; khoảng thiếu 14:45 -> missing_outside."""
    rows = [
        # ATO: thiếu 50 lệnh ở dòng đầu (tv=100, qtty=50 -> gap=50)
        {
            "time": "2026-04-01 08:45:00.000",
            "total_volume_traded": 100,
            "match_qtty": 50,
        },
        # Phiên liên tục 10:00: thiếu 30 lệnh (tv=150 -> tv=200, qtty=20 -> gap=30)
        {
            "time": "2026-04-01 10:00:00.000",
            "total_volume_traded": 150,
            "match_qtty": 50,
        },
        {
            "time": "2026-04-01 10:00:05.000",
            "total_volume_traded": 200,
            "match_qtty": 20,
        },
        # Ngoài phiên liên tục 14:45: thiếu 40 lệnh (tv=200 -> tv=260, qtty=20 -> gap=40)
        {
            "time": "2026-04-01 14:45:00.000",
            "total_volume_traded": 260,
            "match_qtty": 20,
        },
    ]

    cont = volume_continuity(rows)
    assert cont["total_volume"] == 260
    assert cont["missing_continuous"] == 30
    assert cont["missing_outside"] == 50 + 40  # ATO 50 + ATC 40 = 90


def test_4b_volume_continuity_bien_9h_va_14h30():
    """Khoảng thiếu giữa hai dòng ATO, qua mốc 09:00 hoặc chạm 14:30 -> missing_outside; ngay sau 09:00 -> missing_continuous."""
    rows = [
        {"time": "2026-04-01 08:45:00.000", "total_volume_traded": 10, "match_qtty": 10},
        # 08:45 -> 08:50: thiếu 5, dòng trước < 09:00 -> ngoài
        {"time": "2026-04-01 08:50:00.000", "total_volume_traded": 20, "match_qtty": 5},
        # 08:50 -> 09:00:01: thiếu 7, dòng trước < 09:00 -> ngoài
        {"time": "2026-04-01 09:00:01.000", "total_volume_traded": 30, "match_qtty": 3},
        # 09:00:01 -> 09:00:02: thiếu 11 -> liên tục
        {"time": "2026-04-01 09:00:02.000", "total_volume_traded": 42, "match_qtty": 1},
        # 09:00:02 -> 14:30:00: thiếu 13, dòng sau không < 14:30 -> ngoài
        {"time": "2026-04-01 14:30:00.000", "total_volume_traded": 57, "match_qtty": 2},
    ]
    cont = volume_continuity(rows)
    assert cont["missing_continuous"] == 11
    assert cont["missing_outside"] == 5 + 7 + 13


# --- Test 5: Từ chối ngày >= IS_START_DATE ---
def test_5_reject_is_start_date(tmp_path: Path):
    """--to 2026-09-25 -> return 2, hàm tạo client (mock) không được gọi."""
    mock_factory = MagicMock()
    ret = main(
        ["--from", "2026-09-20", "--to", "2026-09-25", "--out", str(tmp_path)],
        client_factory=mock_factory,
    )
    assert ret == 2
    mock_factory.assert_not_called()


# --- Test 6: Ghi file an toàn ---
def test_6_safe_file_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Phiên đã có file thì bỏ qua (client không được gọi); lỗi giữa chừng không để lại file .gz dở."""
    d = date(2026, 4, 1)
    sym = "41I1G4000"
    target_dir = tmp_path / sym
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{d.isoformat()}.jsonl.gz"

    # Tạo trước target_file
    with gzip.open(target_file, "wt", encoding="utf-8") as f:
        f.write('{"test": 1}\n')

    mock_factory = MagicMock()
    # Chạy main cho ngày 2026-04-01
    ret = main(
        ["--from", "2026-04-01", "--to", "2026-04-01", "--out", str(tmp_path)],
        client_factory=mock_factory,
    )
    assert ret == 0
    # Vì file đã có, client không được gọi để tải phiên đó
    # Client tạo ra nhưng fetch_session_trades không được gọi
    client = mock_factory.return_value
    assert client.market.trades.call_count == 0 if hasattr(client, "market") else True

    # Test lỗi giữa chừng khi ghi file không để lại .tmp hoặc file dở
    d2 = date(2026, 4, 2)
    rows = [{"total_volume_traded": 10, "match_qtty": 10, "time": "2026-04-02 09:00:00"}]
    info = {"date": d2.isoformat(), "symbol": sym, "total_volume": 10}

    # Giả lập lỗi trong gzip.open
    def raise_err(*args, **kwargs):
        raise OSError("Disk write error")

    monkeypatch.setattr(gzip, "open", raise_err)
    with pytest.raises(OSError):
        save_session_trades(tmp_path, sym, d2, rows, info)

    # Đảm bảo không để lại file .jsonl.gz hay .tmp
    f2 = target_dir / f"{d2.isoformat()}.jsonl.gz"
    f2_tmp = target_dir / f"{d2.isoformat()}.jsonl.gz.tmp"
    assert not f2.exists()
    assert not f2_tmp.exists()


# --- Test 7: Không làm lộ key/secret trong stdout/stderr ---
def test_7_no_secret_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    """Env giả có key KHOA_BI_MAT_123 và client giả -> stdout/stderr không chứa chuỗi đó."""
    secret = "KHOA_BI_MAT_123"
    monkeypatch.setenv("PRODUCT_DNSE_API_Key", secret)
    monkeypatch.setenv("PRODUCT_DNSE_API_Secret", secret)

    mock_client = MockClient([])
    main(
        ["--from", "2026-04-01", "--to", "2026-04-01", "--out", str(tmp_path)],
        client_factory=lambda k, s: mock_client,
        sleep_fn=MagicMock(),
    )

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
