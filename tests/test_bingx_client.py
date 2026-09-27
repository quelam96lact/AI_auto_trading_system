"""Unit tests for BingX read-only client (Brief 111).

TDD test suite verifying:
1. HMAC-SHA256 signature generation with sorted parameters.
2. Secret masking (api_secret never leaked in repr, str, or exceptions).
3. Parsing of read-only endpoints (server time, balance, positions, open orders, contracts, ticker).
4. Strict error handling (HTTP != 200, code != 0, corrupt JSON, timeout).
5. Read-only architectural guarantee (no POST/PUT/DELETE, no order placement/cancellation methods).
"""

import ast
import hashlib
import hmac
import inspect
from typing import Any
from unittest.mock import patch

import pytest
import requests

from trading.bingx_client import BingXClient, BingXError, sign_params


class MockResponse:
    """Mock requests.Response for unit tests."""

    def __init__(self, json_data: Any, status_code: int = 200, text: str = ""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text or str(json_data)

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


# ---------------------------------------------------------------------------
# 1. Signature Tests (TDD)
# ---------------------------------------------------------------------------

def test_sign_params_sorted_order_and_hmac():
    """Verify parameters are sorted alphabetically and hashed with HMAC-SHA256."""
    secret = "my_secret_key_123"
    params = {
        "timestamp": 1700000000000,
        "symbol": "BTC-USDT",
        "recvWindow": 5000,
    }

    # Expected canonical query string after sorting:
    expected_qs = "recvWindow=5000&symbol=BTC-USDT&timestamp=1700000000000"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        expected_qs.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    qs, sig = sign_params(params, secret)
    assert qs == expected_qs, "Parameter string must be sorted alphabetically by key"
    assert sig == expected_sig, "Signature must match HMAC-SHA256 hex digest"


def test_sign_params_ignores_none_values():
    """Verify None values are excluded from query string and signature."""
    secret = "secret"
    params = {
        "timestamp": 1000,
        "symbol": None,
        "recvWindow": 5000,
    }
    qs, _ = sign_params(params, secret)
    assert "symbol" not in qs
    assert qs == "recvWindow=5000&timestamp=1000"


# ---------------------------------------------------------------------------
# 2. Secret Protection Tests
# ---------------------------------------------------------------------------

def test_client_repr_and_str_mask_secret_and_key():
    """Verify api_secret is never visible in repr or str, and api_key is masked."""
    api_key = "abcdef1234567890"
    api_secret = "super_sensitive_secret_never_leak"

    client = BingXClient(api_key=api_key, api_secret=api_secret)

    repr_str = repr(client)
    str_str = str(client)

    assert api_secret not in repr_str, "api_secret must NEVER be in repr"
    assert api_secret not in str_str, "api_secret must NEVER be in str"
    assert api_key not in repr_str, "Full api_key should not be in repr"
    assert "abcd..." in repr_str, "Masked api_key should be displayed"


# ---------------------------------------------------------------------------
# 3. Read Endpoint Success Tests (Fake HTTP)
# ---------------------------------------------------------------------------

@patch.object(requests.Session, "get")
def test_get_server_time_and_clock_offset(mock_get):
    """Verify get_server_time and get_clock_offset parse correctly."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": {"serverTime": 1700000050000},
    })

    client = BingXClient(api_key="key", api_secret="sec")
    server_time = client.get_server_time()
    assert server_time == 1700000050000

    with patch("time.time", return_value=1700000050.100):  # 1700000050100 ms
        offset = client.get_clock_offset()
        assert offset == 100  # 100ms drift


@patch.object(requests.Session, "get")
def test_get_perpetual_balance_success(mock_get):
    """Verify parsing of USDT perpetual balance."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": {
            "balance": {
                "asset": "USDT",
                "balance": "100.5000",
                "equity": "100.5000",
                "unrealizedProfit": "0.0000",
                "realisedProfit": "0",
                "availableMargin": "100.5000",
                "usedMargin": "0.0000",
                "freezedMargin": "0.0000",
            }
        },
    })

    client = BingXClient(api_key="key", api_secret="sec")
    bal = client.get_perpetual_balance()
    assert bal["asset"] == "USDT"
    assert bal["balance"] == 100.5
    assert bal["equity"] == 100.5
    assert bal["available_margin"] == 100.5


@patch.object(requests.Session, "get")
def test_get_positions_success(mock_get):
    """Verify parsing of open positions."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": [
            {
                "symbol": "BTC-USDT",
                "positionId": "123",
                "positionSide": "LONG",
                "positionAmt": "0.01",
                "avgPrice": "65000.0",
                "unrealizedProfit": "50.0",
                "leverage": 10,
            }
        ],
    })

    client = BingXClient(api_key="key", api_secret="sec")
    positions = client.get_positions(symbol="BTC-USDT")
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTC-USDT"
    assert positions[0]["position_amt"] == 0.01


@patch.object(requests.Session, "get")
def test_get_open_orders_success(mock_get):
    """Verify parsing of open orders."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": {
            "orders": [
                {
                    "orderId": 987654321,
                    "symbol": "BTC-USDT",
                    "price": "60000.0",
                    "origQty": "0.01",
                    "side": "BUY",
                    "type": "LIMIT",
                }
            ]
        },
    })

    client = BingXClient(api_key="key", api_secret="sec")
    orders = client.get_open_orders()
    assert len(orders) == 1
    assert orders[0]["order_id"] == 987654321
    assert orders[0]["symbol"] == "BTC-USDT"


@patch.object(requests.Session, "get")
def test_get_contract_specs(mock_get):
    """Verify contract specifications parsing (tick size, step size, min qty)."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": [
            {
                "symbol": "BTC-USDT",
                "size": "0.0001",
                "quantityPrecision": 4,
                "pricePrecision": 1,
                "tradeMinQuantity": 0.0001,
                "tradeMinUSDT": 2,
                "makerFeeRate": 0.0002,
                "takerFeeRate": 0.0005,
            }
        ],
    })

    client = BingXClient(api_key="key", api_secret="sec")
    spec = client.get_contract("BTC-USDT")
    assert spec["symbol"] == "BTC-USDT"
    assert spec["price_precision"] == 1
    assert spec["quantity_precision"] == 4
    assert spec["tick_size"] == 0.1
    assert spec["step_size"] == 0.0001
    assert spec["min_qty"] == 0.0001
    assert spec["min_notional"] == 2.0
    assert spec["maker_fee_rate"] == 0.0002
    assert spec["taker_fee_rate"] == 0.0005


@patch.object(requests.Session, "get")
def test_get_ticker(mock_get):
    """Verify ticker price parsing."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": {
            "symbol": "BTC-USDT",
            "lastPrice": "84300.5",
            "bidPrice": "84300.0",
            "askPrice": "84301.0",
            "volume": "1234.5",
        },
    })

    client = BingXClient(api_key="key", api_secret="sec")
    ticker = client.get_ticker("BTC-USDT")
    assert ticker["symbol"] == "BTC-USDT"
    assert ticker["last_price"] == 84300.5
    assert ticker["bid_price"] == 84300.0
    assert ticker["ask_price"] == 84301.0


# ---------------------------------------------------------------------------
# 4. Error Handling Tests (No silent failures, no leaked secret)
# ---------------------------------------------------------------------------

@patch.object(requests.Session, "get")
def test_error_http_not_200(mock_get):
    """HTTP != 200 must raise BingXError without leaking api_secret."""
    api_secret = "sensitive_key_secret_xyz"
    mock_get.return_value = MockResponse(
        {"code": 100410, "msg": "IP not whitelisted"},
        status_code=403,
        text="Forbidden",
    )

    client = BingXClient(api_key="key", api_secret=api_secret)
    with pytest.raises(BingXError) as exc_info:
        client.get_perpetual_balance()

    err_str = str(exc_info.value)
    assert api_secret not in err_str, "Secret must not leak into exception message"
    assert exc_info.value.status_code == 403
    assert "403" in err_str or "IP not whitelisted" in err_str


@patch.object(requests.Session, "get")
def test_error_code_not_zero_raises_bingx_error(mock_get):
    """code != 0 in response body must raise BingXError and never return None."""
    api_secret = "sensitive_key_secret_xyz"
    mock_get.return_value = MockResponse(
        {"code": 100001, "msg": "Signature verification failed", "timestamp": 12345},
        status_code=200,
    )

    client = BingXClient(api_key="key", api_secret=api_secret)
    with pytest.raises(BingXError) as exc_info:
        client.get_perpetual_balance()

    assert exc_info.value.code == 100001
    assert "Signature verification failed" in str(exc_info.value)
    assert api_secret not in str(exc_info.value)


@patch.object(requests.Session, "get")
def test_error_corrupt_json_raises_bingx_error(mock_get):
    """Corrupt JSON body must raise BingXError."""
    api_secret = "sensitive_key_secret_xyz"
    mock_get.return_value = MockResponse(
        json_data=ValueError("Expecting value: line 1 column 1 (char 0)"),
        status_code=200,
        text="<!DOCTYPE html><html>502 Bad Gateway</html>",
    )

    client = BingXClient(api_key="key", api_secret=api_secret)
    with pytest.raises(BingXError) as exc_info:
        client.get_perpetual_balance()

    assert api_secret not in str(exc_info.value)
    assert "JSON" in str(exc_info.value) or "502" in str(exc_info.value)


@patch.object(requests.Session, "get")
def test_error_timeout_raises_bingx_error(mock_get):
    """Timeout must raise BingXError."""
    api_secret = "sensitive_key_secret_xyz"
    mock_get.side_effect = requests.exceptions.Timeout("Connection timed out after 10.0s")

    client = BingXClient(api_key="key", api_secret=api_secret)
    with pytest.raises(BingXError) as exc_info:
        client.get_perpetual_balance()

    assert api_secret not in str(exc_info.value)
    assert "timeout" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 5. Read-Only Architectural Guarantee (AST & Introspection)
# ---------------------------------------------------------------------------

def test_client_is_strictly_read_only():
    """Verify BingXClient module has NO order placement/modification/cancellation methods."""
    # 1. Introspection check: methods of BingXClient
    forbidden_prefixes = ["place", "create", "order", "cancel", "modify", "amend", "buy", "sell", "delete", "post", "put"]
    methods = [name for name, _ in inspect.getmembers(BingXClient, predicate=inspect.isfunction)]

    for m in methods:
        for prefix in forbidden_prefixes:
            assert not m.startswith(prefix), f"Forbidden trading method detected: {m}"

    # 2. AST check: examine trading/bingx_client.py
    import trading.bingx_client as client_module
    source = inspect.getsource(client_module)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        # Check HTTP method calls
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.lower() in ("post", "delete", "put", "patch")
        ):
            pytest.fail(f"Forbidden HTTP mutation method '{node.func.attr}' found at line {node.lineno}")
        # Check string literals for mutation endpoints
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.lower()
            if "/trade/order" in val and ("post" in val or "delete" in val):
                pytest.fail(f"Forbidden trade order mutation string found: {node.value}")



# ---------------------------------------------------------------------------
# Audit dot 111 (Claude): thieu truong -> loi, khong ra 0; loc vi the; dong ho
# ---------------------------------------------------------------------------

@patch.object(requests.Session, "get")
def test_balance_missing_field_raises_not_zero(mock_get):
    """Phan hoi thieu 'balance' KHONG duoc doc thanh so du 0 (brief §3 muc 3)."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        # DU moi truong TRU 'balance' -> loi phai do CHINH truong nay, khong do truong khac.
        "data": {"balance": {
            "asset": "USDT", "equity": "8.0", "availableMargin": "8.0", "usedMargin": "0",
            "freezedMargin": "0", "unrealizedProfit": "0", "realisedProfit": "0",
        }},
    })
    client = BingXClient(api_key="key", api_secret="sec")
    with pytest.raises(BingXError, match="truong bat buoc 'balance'"):
        client.get_perpetual_balance()


@patch.object(requests.Session, "get")
def test_contract_missing_fee_raises_not_guessed(mock_get):
    """Thieu takerFeeRate -> loi; KHONG doan phi 0.0005 (rang buoc dung cua du an)."""
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": [{
            "symbol": "BTC-USDT", "pricePrecision": 1, "quantityPrecision": 4,
            "size": "0.0001", "tradeMinQuantity": "0.0001", "tradeMinUSDT": "2",
            "makerFeeRate": "0.0002",
        }],
    })
    client = BingXClient(api_key="key", api_secret="sec")
    with pytest.raises(BingXError, match="takerFeeRate"):
        client.get_contract("BTC-USDT")


@patch.object(requests.Session, "get")
def test_positions_without_symbol_excludes_zero_size(mock_get):
    """Khong truyen symbol van phai bo vi the khoi luong 0 (dieu kien cu `or not symbol`)."""
    base = {"positionSide": "LONG", "avgPrice": "1", "unrealizedProfit": "0", "leverage": 5}
    mock_get.return_value = MockResponse({
        "code": 0,
        "msg": "",
        "data": [
            {**base, "symbol": "BTC-USDT", "positionAmt": "0"},
            {**base, "symbol": "ETH-USDT", "positionAmt": "0.5"},
        ],
    })
    client = BingXClient(api_key="key", api_secret="sec")
    positions = client.get_positions()
    assert [p["symbol"] for p in positions] == ["ETH-USDT"]


def test_clock_offset_uses_round_trip_midpoint(monkeypatch):
    """Do tre khu hoi KHONG duoc tinh thanh lech dong ho: dung diem giua t0..t1."""
    times = iter([1000.000, 1002.000])  # giay: gui luc 1000, nhan luc 1002 (RTT 2s)
    monkeypatch.setattr("trading.bingx_client.time.time", lambda: next(times))
    client = BingXClient(api_key="key", api_secret="sec")
    monkeypatch.setattr(client, "get_server_time", lambda: 1_001_000)  # server = diem giua
    assert client.get_clock_offset() == 0
