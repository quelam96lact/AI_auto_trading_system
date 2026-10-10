"""Test suite for scripts/drill_place_cancel_order.py (Brief đợt 100).

Mọi test đều dùng mock / fake client. TUYỆT ĐỐI KHÔNG gọi API SSI thật.
"""

import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import pytest

from scripts.drill_place_cancel_order import (
    drill_price,
    run_drill,
    select_reference_price,
)
from trading.calendar_vn import TZ


@dataclass
class FakeMbs:
    max_buy_quantity: int = 500
    max_sell_quantity: int = 0


@dataclass
class FakeOHLC:
    trading_date: str
    close_price: float | str


@dataclass
class FakePlaceResponse:
    order_id: str = "ORDER_12345"
    client_request_id: str = "REQ_67890"
    status: str = "PLACED"


@dataclass
class FakeCancelResponse:
    client_cancel_id: str = "CANCEL_111"
    order_id: str = "ORDER_12345"
    client_request_id: str = "REQ_67890"
    status: str = "SUCCESS"


@dataclass
class FakeOrderHistoryItem:
    client_request_id: str = "REQ_67890"
    order_id: str = "ORDER_12345"
    status: str = "CANCELLED"
    filled_quantity: int = 0
    cancel_quantity: int = 100


class FakeRestPortfolio:
    """Portfolio giả hỗ trợ _rest.get trả dict raw JSON từ SSI API (Brief đợt 178)."""

    def __init__(self, raw_resp: dict):
        self._rest = AsyncMock()
        self._rest.get.return_value = raw_resp


def make_mock_trading_client(
    max_buy_qty: int = 500,
    cancel_raises: bool = False,
    cancel_status: str = "SUCCESS",
):
    client = MagicMock()
    trading_svc = AsyncMock()
    trading_svc.get_max_buy_sell_at_market_price.return_value = FakeMbs(
        max_buy_quantity=max_buy_qty
    )
    trading_svc.place_limit_order.return_value = FakePlaceResponse()

    if cancel_raises:
        trading_svc.cancel_order.side_effect = RuntimeError("SSI cancel rejection 500")
    else:
        trading_svc.cancel_order.return_value = FakeCancelResponse(status=cancel_status)

    portfolio_svc = FakeRestPortfolio({
        "totalRecord": 1,
        "orderList": [
            {
                "orderId": "ORDER_12345",
                "clientRequestId": "REQ_67890",
                "orderStatus": "CL",
                "quantity": 100,
                "filledQty": 0,
                "cancelQty": 100,
                "avgPrice": 1000,
                "side": "B",
                "symbol": "VCB",
                "inputTime": "2026/10/12 10:00:00",
            }
        ],
    })

    client.trading = trading_svc
    client.portfolio = portfolio_svc
    return client


def make_mock_data_client(rows=None):
    client = MagicMock()
    market_svc = AsyncMock()
    if rows is None:
        rows = [
            FakeOHLC(trading_date="2026/09/24", close_price="12200"),
            FakeOHLC(trading_date="2026/09/25", close_price="12300"),
        ]
    market_svc.get_ohlc_1day_historical.return_value = rows
    client.market_data = market_svc
    return client


# ---------------------------------------------------------------------------
# Test 1: Chốt an toàn quan trọng nhất — không có --send thì place và cancel
#         của client giả KHÔNG BAO GIỜ được gọi (call_count == 0).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_safety_latch_no_send_never_places_or_cancels():
    mock_trading = make_mock_trading_client()
    mock_data = make_mock_data_client()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221",
            symbol="VCB",
            send=False,  # DRY RUN
            trading_client=mock_trading,
            data_client=mock_data,
            get_exchange_fn=lambda s: "HOSE",
        )

    assert exc.value.code == 0
    assert mock_trading.trading.place_limit_order.call_count == 0
    assert mock_trading.trading.cancel_order.call_count == 0


# ---------------------------------------------------------------------------
# Test 2: Có --send nhưng input_fn trả "yes", "", hoặc "YES " -> KHÔNG gửi.
#         Chỉ "YES" chính xác mới gửi.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_input", ["yes", "", "YES ", " YES", "y", "OK"])
async def test_send_rejects_non_exact_yes(invalid_input):
    mock_trading = make_mock_trading_client()
    mock_data = make_mock_data_client()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221",
            symbol="VCB",
            send=True,
            trading_client=mock_trading,
            data_client=mock_data,
            input_fn=lambda prompt: invalid_input,
            get_exchange_fn=lambda s: "HOSE",
        )

    assert exc.value.code == 0
    assert mock_trading.trading.place_limit_order.call_count == 0
    assert mock_trading.trading.cancel_order.call_count == 0


@pytest.mark.asyncio
async def test_send_exact_yes_places_and_cancels(tmp_path):
    mock_trading = make_mock_trading_client()
    mock_data = make_mock_data_client()

    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path):
        await run_drill(
            account="0434221",
            symbol="VCB",
            send=True,
            trading_client=mock_trading,
            data_client=mock_data,
            input_fn=lambda prompt: "YES",
            get_exchange_fn=lambda s: "HOSE",
        )

    assert mock_trading.trading.place_limit_order.call_count == 1
    assert mock_trading.trading.cancel_order.call_count == 1


# ---------------------------------------------------------------------------
# Test 3: Thiếu --account -> thoát khác 0, và client giả KHÔNG bị gọi hàm nào.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_account_exits_without_client_calls():
    mock_trading = make_mock_trading_client()
    mock_data = make_mock_data_client()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="",
            symbol="VCB",
            send=False,
            trading_client=mock_trading,
            data_client=mock_data,
        )

    assert exc.value.code != 0
    assert mock_trading.trading.get_max_buy_sell_at_market_price.call_count == 0
    assert mock_trading.trading.place_limit_order.call_count == 0
    assert mock_data.market_data.get_ohlc_1day_historical.call_count == 0


# ---------------------------------------------------------------------------
# Test 4: max_buy_quantity = 99 (< 100) -> dừng, không gửi.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insufficient_buying_power_aborts():
    mock_trading = make_mock_trading_client(max_buy_qty=99)
    mock_data = make_mock_data_client()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221",
            symbol="VCB",
            send=True,
            trading_client=mock_trading,
            data_client=mock_data,
            input_fn=lambda prompt: "YES",
            get_exchange_fn=lambda s: "HOSE",
        )

    assert exc.value.code != 0
    assert mock_trading.trading.place_limit_order.call_count == 0
    assert mock_trading.trading.cancel_order.call_count == 0


# ---------------------------------------------------------------------------
# Test 5: Mã UPCOM hoặc sàn không rõ -> dừng, không gửi.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_exchange", ["UPCOM", "UNKNOWN", "", None])
async def test_unsupported_exchange_aborts(bad_exchange):
    mock_trading = make_mock_trading_client()
    mock_data = make_mock_data_client()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221",
            symbol="BSR",
            send=True,
            trading_client=mock_trading,
            data_client=mock_data,
            input_fn=lambda prompt: "YES",
            get_exchange_fn=lambda s: bad_exchange,
        )

    assert exc.value.code != 0
    assert mock_trading.trading.place_limit_order.call_count == 0


# ---------------------------------------------------------------------------
# Test 6: Giá đặt, tính tay theo quy chế bước giá HOSE và HNX:
# ---------------------------------------------------------------------------
def test_drill_price_calculations():
    """Kiểm tra các ca tính giá đặt theo quy chế giao dịch:

    - HOSE ref 12.300:
      band = 0.07 -> floor raw = 12.300 * 0.93 = 11.439 -> bước 50đ:
      floor = ceil50(11.439) = 11.450
      price raw = 12.300 * 0.94 = 11.562 -> bước 50đ:
      price = ceil50(11.562) = 11.600
      Ràng buộc: 11.450 <= 11.600 < 12.300 (ĐẠT).

    - HOSE ref 9.870:
      band = 0.07 -> floor raw = 9.870 * 0.93 = 9.179.1 -> bước 10đ:
      floor = ceil10(9.179.1) = 9.180
      price raw = 9.870 * 0.94 = 9.277.8 -> bước 10đ:
      price = ceil10(9.277.8) = 9.280
      Ràng buộc: 9.180 <= 9.280 < 9.870 (ĐẠT).

    - HOSE ref 52.000:
      band = 0.07 -> floor raw = 52.000 * 0.93 = 48.360 -> bước 50đ/100đ:
      floor = 48.400
      price raw = 52.000 * 0.94 = 48.880 -> bước 50đ/100đ:
      price = 48.900
      Ràng buộc: 48.400 <= 48.900 < 52.000 (ĐẠT).

    - HNX ref 20.000:
      band = 0.10 -> floor raw = 20.000 * 0.90 = 18.000 -> bước 100đ:
      floor = 18.000
      price raw = 20.000 * 0.91 = 18.200 -> bước 100đ:
      price = 18.200
      Ràng buộc: 18.000 <= 18.200 < 20.000 (ĐẠT).

    - Biên bước giá: ref mà ref * 0.94 rơi đúng 10.000 hoặc 50.000:
      + ref = 10.000 / 0.94 = 10638.2978... -> price = 10.000 (bước 50)
      + ref = 50.000 / 0.94 = 53191.4893... -> price = 50.000 (bước 100)
    """
    # 1. HOSE ref 12.300
    p_12300 = drill_price(12_300, "HOSE")
    assert p_12300 == 11_600
    assert 11_450 <= p_12300 < 12_300

    # 2. HOSE ref 9.870
    p_9870 = drill_price(9_870, "HOSE")
    assert p_9870 == 9_280
    assert 9_180 <= p_9870 < 9_870

    # 3. HOSE ref 52.000
    p_52000 = drill_price(52_000, "HOSE")
    assert p_52000 == 48_900
    assert 48_400 <= p_52000 < 52_000

    # 4. HNX ref 20.000
    p_hnx = drill_price(20_000, "HNX")
    assert p_hnx == 18_200
    assert 18_000 <= p_hnx < 20_000

    # 5. Biên bước giá 10.000 và 50.000
    ref_border_10k = 10_000 / 0.94
    p_border_10k = drill_price(ref_border_10k, "HOSE")
    assert p_border_10k == 10_000

    ref_border_50k = 50_000 / 0.94
    p_border_50k = drill_price(ref_border_50k, "HOSE")
    assert p_border_50k == 50_000


# ---------------------------------------------------------------------------
# Test 7: Giá tham chiếu: dữ liệu giả có nến hôm nay (13.000) và hôm qua
#         (12.300); chạy "hôm nay" -> ref phải là 12.300 (không lấy nến hôm nay).
# ---------------------------------------------------------------------------
def test_select_reference_price_excludes_today():
    today = date(2026, 9, 26)
    rows = [
        FakeOHLC(trading_date="2026/09/24", close_price="12100"),
        FakeOHLC(trading_date="2026/09/25", close_price="12300"),
        FakeOHLC(trading_date="2026/09/26", close_price="13000"),  # nến hôm nay
    ]
    ref = select_reference_price(rows, today_vn=today)
    assert ref == 12_300.0


# ---------------------------------------------------------------------------
# Test 8: Huỷ thất bại: cancel_order giả ném lỗi -> thoát mã 2, có alert
#         CRITICAL, và output chứa "HUỶ TAY".
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_failure_triggers_critical_alert_and_exit_2(capsys):
    mock_trading = make_mock_trading_client(cancel_raises=True)
    mock_data = make_mock_data_client()
    mock_alert = MagicMock()

    with pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221",
            symbol="VCB",
            send=True,
            trading_client=mock_trading,
            data_client=mock_data,
            input_fn=lambda prompt: "YES",
            get_exchange_fn=lambda s: "HOSE",
            alert_fn=mock_alert,
        )

    assert exc.value.code == 2
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL"

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err
    assert "HUỶ TAY" in combined_output
    assert "LỆNH THẬT CÓ THỂ ĐANG TREO — HUỶ TAY NGAY TRÊN iBoard/ứng dụng SSI" in combined_output


# ---------------------------------------------------------------------------
# Test 9: Script cũ: gọi main() của spike_ssi_sdk_place_order.py -> thoát 1
#         và KHÔNG gọi mạng.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_old_spike_script_disabled_exits_1_without_network():
    from scripts.spike_ssi_sdk_place_order import main as old_main

    with pytest.raises(SystemExit) as exc:
        await old_main()

    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Claude audit dot 100: ba ca "that bai im lang" tren duong tien that.
# ---------------------------------------------------------------------------
async def _no_sleep(_s):
    return None


@pytest.mark.asyncio
async def test_place_raises_reports_unknown_state_critical_exit_2(capsys, tmp_path):
    """place_limit_order nem loi (vd het thoi gian cho SAU khi lenh da toi san): khong
    duoc chet bang traceback - phai CRITICAL, bao kiem tra iBoard, exit 2, KHONG goi huy."""
    mock_trading = make_mock_trading_client()
    mock_trading.trading.place_limit_order.side_effect = TimeoutError("read timeout")
    mock_alert = MagicMock()
    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path), pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=mock_alert, sleep_fn=_no_sleep,
        )
    assert exc.value.code == 2
    assert mock_alert.call_args.args[0] == "CRITICAL"
    assert mock_trading.trading.cancel_order.call_count == 0
    out = capsys.readouterr()
    assert "KIỂM TRA iBoard" in out.out + out.err


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filled", "cancelled", "can_thay"),
    [(100, 0, "ĐÃ KHỚP"), (40, 60, "ĐÃ KHỚP"), (0, 0, "CHƯA XÁC NHẬN HUỶ ĐỦ")],
)
async def test_post_cancel_status_not_fully_cancelled_is_critical(
    capsys, tmp_path, filled, cancelled, can_thay
):
    """San nhan yeu cau huy CHUA co nghia lenh da huy: so lenh cho thay da khop (mot phan)
    hoac chua huy du 100 -> CRITICAL, exit 2 (truoc day in 'thanh cong')."""
    mock_trading = make_mock_trading_client()
    mock_fetch = AsyncMock(
        return_value=[
            FakeOrderHistoryItem(filled_quantity=filled, cancel_quantity=cancelled, status="X")
        ]
    )
    mock_alert = MagicMock()
    with patch("scripts.drill_place_cancel_order.fetch_order_history", mock_fetch), \
         patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path), \
         pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=mock_alert, sleep_fn=_no_sleep,
        )
    assert exc.value.code == 2
    assert mock_alert.call_args.args[0] == "CRITICAL"
    out = capsys.readouterr()
    assert can_thay in out.out + out.err


@pytest.mark.asyncio
async def test_post_cancel_order_not_found_returns_1_after_polling(capsys, tmp_path):
    """Khong tim thay lenh trong so lenh sau 3 lan doc: khong duoc bao 'thanh cong' -
    tra ma 1, yeu cau doi chieu tay tren iBoard."""
    mock_trading = make_mock_trading_client()
    mock_fetch = AsyncMock(return_value=[])
    with patch("scripts.drill_place_cancel_order.fetch_order_history", mock_fetch), \
         patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path):
        code = await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=MagicMock(), sleep_fn=_no_sleep,
        )
    assert code == 1
    assert mock_fetch.call_count == 3
    out = capsys.readouterr()
    assert "ĐỐI CHIẾU TAY" in out.out + out.err


@pytest.mark.asyncio
async def test_happy_path_returns_0_when_fully_cancelled(tmp_path):
    mock_trading = make_mock_trading_client()   # so lenh mac dinh: filled 0, cancel 100
    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path):
        code = await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=MagicMock(), sleep_fn=_no_sleep,
        )
    assert code == 0


# ---------------------------------------------------------------------------
# Brief đợt 178: kiểm chứng đọc đúng số lượng khớp/hủy từ SSI API
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step10_e2e_raw_json_partially_filled_is_critical(capsys, tmp_path):
    """1. Đầu-cuối với JSON thô: orderStatus FFPC, filledQty 40, cancelQty 60
    không monkeypatch fetch_order_history -> CRITICAL, exit 2, chứa 'ĐÃ KHỚP'."""
    mock_trading = make_mock_trading_client()
    mock_trading.portfolio = FakeRestPortfolio({
        "totalRecord": 1,
        "orderList": [
            {
                "orderId": "ORDER_12345",
                "clientRequestId": "REQ_67890",
                "orderStatus": "FFPC",
                "quantity": 100,
                "filledQty": 40,
                "cancelQty": 60,
                "avgPrice": 1000,
                "side": "B",
                "symbol": "VCB",
                "inputTime": "2026/10/12 10:00:00",
            }
        ],
    })
    mock_alert = MagicMock()
    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path), pytest.raises(SystemExit) as exc:
        await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=mock_alert, sleep_fn=_no_sleep,
        )
    assert exc.value.code == 2
    assert mock_alert.call_args.args[0] == "CRITICAL"
    out = capsys.readouterr()
    assert "ĐÃ KHỚP" in out.out + out.err


@pytest.mark.asyncio
async def test_step10_e2e_raw_json_fully_cancelled_returns_0(tmp_path):
    """2. Hủy đủ: orderStatus CL, filledQty 0, cancelQty 100 -> exit 0, không CRITICAL."""
    mock_trading = make_mock_trading_client()
    mock_trading.portfolio = FakeRestPortfolio({
        "totalRecord": 1,
        "orderList": [
            {
                "orderId": "ORDER_12345",
                "clientRequestId": "REQ_67890",
                "orderStatus": "CL",
                "quantity": 100,
                "filledQty": 0,
                "cancelQty": 100,
                "avgPrice": 1000,
                "side": "B",
                "symbol": "VCB",
                "inputTime": "2026/10/12 10:00:00",
            }
        ],
    })
    mock_alert = MagicMock()
    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path):
        code = await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=mock_alert, sleep_fn=_no_sleep,
        )
    assert code == 0
    assert mock_alert.call_count == 0


@pytest.mark.asyncio
async def test_step10_date_params_matches_vn_today(tmp_path):
    """3. Ngày đúng giờ VN: params gửi tới _rest.get có from == to == ngày VN hôm nay theo %Y/%m/%d."""
    mock_trading = make_mock_trading_client()
    portfolio = FakeRestPortfolio({
        "totalRecord": 1,
        "orderList": [
            {
                "orderId": "ORDER_12345",
                "clientRequestId": "REQ_67890",
                "orderStatus": "CL",
                "quantity": 100,
                "filledQty": 0,
                "cancelQty": 100,
                "avgPrice": 1000,
                "side": "B",
                "symbol": "VCB",
                "inputTime": "2026/10/12 10:00:00",
            }
        ],
    })
    mock_trading.portfolio = portfolio
    with patch("scripts.drill_place_cancel_order.LOGS_DIR", tmp_path):
        await run_drill(
            account="0434221", symbol="VCB", send=True,
            trading_client=mock_trading, data_client=make_mock_data_client(),
            input_fn=lambda p: "YES", get_exchange_fn=lambda s: "HOSE",
            alert_fn=MagicMock(), sleep_fn=_no_sleep,
        )

    expected_today = datetime.now(TZ).strftime("%Y/%m/%d")
    call_args = portfolio._rest.get.call_args
    assert call_args is not None
    params = call_args.kwargs.get("params") or call_args.args[1]
    assert params["from"] == expected_today
    assert params["to"] == expected_today

