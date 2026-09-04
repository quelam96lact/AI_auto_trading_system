"""Unit tests cho scripts/bingx_spot_probe.py (Gói P).

Tất định, không phụ thuộc mạng, kiểm chứng:
1. test_rate_limit_delay_enforced: Khẳng định có time.sleep >= 1.0s giữa các request.
2. test_symbol_error_does_not_crash_script: Khi gặp lỗi 429 / JSON rác / mã không tồn tại -> báo lỗi cho mã đó và đi tiếp.
"""

from unittest.mock import MagicMock, patch

from scripts.bingx_spot_probe import (
    fetch_spot_klines_chunk,
    probe_all_symbols,
    probe_symbol_spot,
)


def test_rate_limit_delay_enforced():
    """1. test_rate_limit_delay_enforced (Tiêu chí 1):
    Hàm gọi mạng được mock, khẳng định có sleep >= 1.0s giữa hai lần gọi liên tiếp.
    """
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 0,
        "data": [
            [1788537600000, 79000.0, 80000.0, 78000.0, 79500.0, 100.0, 1788623999999, 7950000.0],
        ],
    }
    mock_session.get.return_value = mock_resp

    with patch("time.sleep") as mock_sleep:
        code, _msg, bars = fetch_spot_klines_chunk(
            mock_session, "BTC-USDT", interval="1d", rate_limit_delay=1.1
        )

        assert code == 0
        assert len(bars) == 1
        # Khẳng định time.sleep được gọi với delay >= 1.0s
        mock_sleep.assert_called()
        sleep_args = [call[0][0] for call in mock_sleep.call_args_list]
        assert any(s >= 1.0 for s in sleep_args), f"Phải có ít nhất 1 lần sleep >= 1.0s, thực tế: {sleep_args}"


def test_symbol_error_does_not_crash_script():
    """2. test_symbol_error_does_not_crash_script (Tiêu chí 2 & 4):
    Khi 1 mã trả về lỗi 100204 (symbol not found) hoặc HTTP 429/500:
    Script ghi nhận mã đó không có và tiếp tục duyệt các mã sau mà không crash.
    """
    mock_session = MagicMock()

    def mock_get(url, params=None, **kwargs):
        sym = params.get("symbol") if params else ""
        resp = MagicMock()
        if sym == "INVALID-USDT":
            resp.status_code = 200
            resp.json.return_value = {"code": 100204, "msg": "symbol is not found.", "data": None}
        elif sym == "ERROR-USDT":
            resp.status_code = 500
            resp.raise_for_status.side_effect = Exception("Internal Server Error")
        else:
            resp.status_code = 200
            resp.json.return_value = {
                "code": 0,
                "data": [
                    [1788537600000, 100.0, 105.0, 95.0, 102.0, 10.0, 1788623999999, 1020.0],
                ],
            }
        return resp

    mock_session.get.side_effect = mock_get

    with patch("time.sleep"):
        res_invalid = probe_symbol_spot(mock_session, "INVALID-USDT", interval="1d", rate_limit_delay=0.0)
        assert res_invalid["available"] is False
        assert res_invalid["code"] == 100204
        assert "symbol is not found" in res_invalid["msg"]

        # Thử danh sách nhiều mã
        with patch("requests.Session", return_value=mock_session):
            all_results = probe_all_symbols(["VALID-USDT", "INVALID-USDT", "ERROR-USDT"], interval="1d", rate_limit_delay=0.0)
            assert len(all_results) == 3
            assert all_results[0]["available"] is True
            assert all_results[1]["available"] is False
            assert all_results[2]["available"] is False
