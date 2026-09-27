"""Unit tests for BingX place/cancel drill script (Brief 112).

Tests cover:
1. Strict repository isolation: AST scan ensuring NO files in trading/ or scripts/
   (except the drill script itself) import or instantiate BingXTradeClient.
2. Price calculation & rounding down (floor to tick size).
3. Hard safety gates:
   - Clock drift check.
   - Existing open orders check.
   - Existing open positions check.
   - Margin sufficiency check (>= 2x margin).
   - Hard notional cap check (<= 20 USDT).
4. Dry-run safety: zero write requests when --send is absent.
5. Operator confirmation gate: rejection if input != 'YES'.
6. Post-send handling:
   - Exception on send -> CRITICAL alert, exit 2.
   - Filled -> CRITICAL alert, manual close instruction, exit 2.
   - Pending -> cancelled -> confirmed CANCELED -> exit 0.
   - Cancel failure -> CRITICAL alert, exit 2.
   - Not found -> manual reconciliation, exit 1.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import MagicMock

import pytest

from scripts.bingx_drill_place_cancel import (
    calculate_drill_price,
    round_down_to_tick,
    run_drill,
)
from trading.bingx_client import BingXError, BingXTradeClient

# ---------------------------------------------------------------------------
# 1. Repository-wide Isolation Test (AST scan)
# ---------------------------------------------------------------------------

def test_repo_isolation_no_unauthorized_imports_of_bingx_trade_client():
    """Verify NO files in trading/ or scripts/ (except drill script) import BingXTradeClient."""
    repo_root = pathlib.Path(__file__).parent.parent
    allowed_files = {
        (repo_root / "trading" / "bingx_client.py").resolve(),
        (repo_root / "scripts" / "bingx_drill_place_cancel.py").resolve(),
    }

    scanned_dirs = [repo_root / "trading", repo_root / "scripts"]
    violations = []

    for s_dir in scanned_dirs:
        for py_path in s_dir.rglob("*.py"):
            resolved = py_path.resolve()
            if resolved in allowed_files:
                continue

            content = resolved.read_text(encoding="utf-8")
            if "BingXTradeClient" not in content:
                continue

            # Parse AST to confirm actual import or usage
            try:
                tree = ast.parse(content, filename=str(resolved))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                # Check import BingXTradeClient or from ... import BingXTradeClient
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.name == "BingXTradeClient":
                            violations.append(f"{py_path}: line {node.lineno} imports BingXTradeClient")
                elif isinstance(node, ast.Name) and node.id == "BingXTradeClient":
                    violations.append(f"{py_path}: line {node.lineno} references BingXTradeClient")

    assert not violations, "Forbidden BingXTradeClient usages found in repo:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# 2. Price Calculation & Rounding Down Tests
# ---------------------------------------------------------------------------

def test_round_down_to_tick():
    """Verify round_down_to_tick floors to tick size and respects precision."""
    # tick_size = 0.1, precision = 1
    assert round_down_to_tick(65432.19, 0.1, 1) == 65432.1
    assert round_down_to_tick(65432.11, 0.1, 1) == 65432.1
    assert round_down_to_tick(65432.10, 0.1, 1) == 65432.1
    assert round_down_to_tick(65432.09, 0.1, 1) == 65432.0

    # tick_size = 0.5, precision = 1
    assert round_down_to_tick(100.49, 0.5, 1) == 100.0
    assert round_down_to_tick(100.51, 0.5, 1) == 100.5


def test_calculate_drill_price_floors_5_percent_below():
    """Verify drill price is market_price * (1 - 0.05) floored to tick_size."""
    market_price = 100000.0
    tick_size = 0.1
    precision = 1

    # 100000 * 0.95 = 95000.0
    price = calculate_drill_price(market_price, tick_size, precision, discount_rate=0.05)
    assert price == 95000.0
    assert price < market_price

    # Market price with fractional calculation: 65432.7 * 0.95 = 62161.065 -> floored to 62161.0
    price_frac = calculate_drill_price(65432.7, 0.1, 1, discount_rate=0.05)
    assert price_frac == 62161.0
    assert price_frac <= 65432.7 * 0.95


# ---------------------------------------------------------------------------
# 3. Dry-Run & Confirmation Gate Tests
# ---------------------------------------------------------------------------

def create_mock_client():
    """Create a mock BingXTradeClient with valid default responses."""
    client = MagicMock(spec=BingXTradeClient)
    client.get_server_time.return_value = 1700000000000
    client.get_clock_offset.return_value = 50  # 50ms offset
    client.get_ticker.return_value = {
        "symbol": "BTC-USDT",
        "last_price": 60000.0,
        "bid_price": 59999.0,
        "ask_price": 60001.0,
        "volume_24h": 100.0,
    }
    client.get_contract.return_value = {
        "symbol": "BTC-USDT",
        "price_precision": 1,
        "quantity_precision": 4,
        "tick_size": 0.1,
        "step_size": 0.0001,
        "min_qty": 0.0001,
        "min_notional": 2.0,
        "maker_fee_rate": 0.0002,
        "taker_fee_rate": 0.0005,
    }
    client.get_positions.return_value = []
    client.get_open_orders.return_value = []
    client.get_perpetual_balance.return_value = {
        "asset": "USDT",
        "balance": 100.0,
        "equity": 100.0,
        "available_margin": 100.0,
        "used_margin": 0.0,
        "freezed_margin": 0.0,
        "unrealized_profit": 0.0,
        "realized_profit": 0.0,
    }
    return client


def test_dry_run_makes_zero_write_calls():
    """When send=False, run_drill prints order plan, makes 0 write calls, exits 0."""
    client = create_mock_client()
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=False,
        env="demo",
        alert_fn=alert_fn,
    )

    assert code == 0
    client.place_limit_order.assert_not_called()
    client.cancel_order.assert_not_called()
    alert_fn.assert_not_called()


def test_operator_confirmation_gate_rejects_wrong_input():
    """When send=True but operator input != 'YES', exits 0 without placing order."""
    client = create_mock_client()
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "NO",
        alert_fn=alert_fn,
    )

    assert code == 0
    client.place_limit_order.assert_not_called()
    client.cancel_order.assert_not_called()
    alert_fn.assert_not_called()


def test_live_env_requires_explicit_env_live():
    """When send=True on live without explicit env='live', script must abort."""
    client = create_mock_client()
    # If base url is live but env flag is demo or missing
    client._base_url = "https://open-api.bingx.com"

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",  # mismatch with live client
        input_fn=lambda _: "YES",
    )

    assert code != 0
    client.place_limit_order.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Safety Gates Tests
# ---------------------------------------------------------------------------

def test_safety_gate_clock_drift_exceeded():
    """Exit != 0 if clock drift > safe threshold (e.g. 2500ms)."""
    client = create_mock_client()
    client.get_clock_offset.return_value = 3500  # 3.5s drift

    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo", input_fn=lambda _: "YES")
    assert code != 0
    client.place_limit_order.assert_not_called()


def test_safety_gate_existing_open_orders():
    """Exit != 0 if open orders exist on the symbol."""
    client = create_mock_client()
    client.get_open_orders.return_value = [{"order_id": 111, "symbol": "BTC-USDT"}]

    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo", input_fn=lambda _: "YES")
    assert code != 0
    client.place_limit_order.assert_not_called()


def test_safety_gate_existing_open_positions():
    """Exit != 0 if open positions exist on the symbol."""
    client = create_mock_client()
    client.get_positions.return_value = [{"symbol": "BTC-USDT", "position_amt": 0.01}]

    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo", input_fn=lambda _: "YES")
    assert code != 0
    client.place_limit_order.assert_not_called()


def test_safety_gate_insufficient_available_margin():
    """Exit != 0 if available margin < 2x estimated margin."""
    client = create_mock_client()
    # Order notional: 0.0001 BTC * 57000 = 5.7 USDT -> 2x margin is 11.4 USDT
    # Set available margin to only 5.0 USDT
    client.get_perpetual_balance.return_value["available_margin"] = 5.0

    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo", input_fn=lambda _: "YES")
    assert code != 0
    client.place_limit_order.assert_not_called()


def test_safety_gate_notional_cap_exceeded():
    """Exit != 0 if order notional exceeds hard cap of 20 USDT."""
    client = create_mock_client()
    # Set min_qty high so notional = 100000 * 0.001 = 100 USDT > 20 USDT
    client.get_ticker.return_value["last_price"] = 100000.0
    client.get_contract.return_value["min_qty"] = 0.001  # notional ~95 USDT

    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo", input_fn=lambda _: "YES")
    assert code != 0
    client.place_limit_order.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Post-Send Execution Flow Tests
# ---------------------------------------------------------------------------

def test_post_send_exception_triggers_critical_alert_and_exit_2():
    """If place_limit_order throws exception, send CRITICAL alert and exit 2."""
    client = create_mock_client()
    client.place_limit_order.side_effect = BingXError("Network timeout after sending order")
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "YES",
        alert_fn=alert_fn,
    )

    assert code == 2
    alert_fn.assert_called_once()
    assert alert_fn.call_args[0][0] == "CRITICAL"
    assert "KHÔNG RÕ LỆNH ĐÃ LÊN SÀN CHƯA" in alert_fn.call_args[0][1]


def test_post_send_filled_triggers_critical_alert_and_exit_2():
    """If order filled immediately, trigger CRITICAL alert and exit 2 (do NOT auto close)."""
    client = create_mock_client()
    client.place_limit_order.return_value = {
        "order_id": 99999,
        "client_order_id": "drill_123",
        "status": "NEW",
    }
    # When polled, order is FILLED
    client.get_order.return_value = {
        "order_id": 99999,
        "client_order_id": "drill_123",
        "status": "FILLED",
        "executed_qty": 0.0001,
    }
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "YES",
        alert_fn=alert_fn,
        sleep_fn=lambda _: None,
    )

    assert code == 2
    alert_fn.assert_called_once()
    assert alert_fn.call_args[0][0] == "CRITICAL"
    assert "ĐÃ KHỚP" in alert_fn.call_args[0][1]
    client.cancel_order.assert_not_called()


def test_post_send_cancel_success_returns_exit_0():
    """Normal success flow: NEW -> cancel_order -> CANCELED -> returns exit 0."""
    client = create_mock_client()
    client.place_limit_order.return_value = {
        "order_id": 99999,
        "client_order_id": "drill_123",
        "status": "NEW",
    }
    # First get_order returns NEW, after cancel returns CANCELED
    client.get_order.side_effect = [
        {"order_id": 99999, "status": "NEW", "executed_qty": 0.0},
        {"order_id": 99999, "status": "CANCELED", "executed_qty": 0.0},
    ]
    client.cancel_order.return_value = {"order_id": 99999, "status": "CANCELED"}
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "YES",
        alert_fn=alert_fn,
        sleep_fn=lambda _: None,
    )

    assert code == 0
    client.cancel_order.assert_called_once_with(symbol="BTC-USDT", order_id=99999, client_order_id="drill_123")
    alert_fn.assert_not_called()


def test_post_send_cancel_failure_triggers_critical_alert_and_exit_2():
    """If cancel_order fails, trigger CRITICAL alert and exit 2."""
    client = create_mock_client()
    client.place_limit_order.return_value = {
        "order_id": 99999,
        "client_order_id": "drill_123",
        "status": "NEW",
    }
    client.get_order.return_value = {"order_id": 99999, "status": "NEW", "executed_qty": 0.0}
    client.cancel_order.side_effect = BingXError("Exchange rejected cancel request")
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "YES",
        alert_fn=alert_fn,
        sleep_fn=lambda _: None,
    )

    assert code == 2
    alert_fn.assert_called_once()
    assert alert_fn.call_args[0][0] == "CRITICAL"
    assert "LỆNH CÒN TREO — HUỶ TAY" in alert_fn.call_args[0][1]


def test_post_send_not_found_returns_exit_1():
    """If order cannot be retrieved after 3 attempts, exit 1 for manual check."""
    client = create_mock_client()
    client.place_limit_order.return_value = {
        "order_id": 99999,
        "client_order_id": "drill_123",
        "status": "NEW",
    }
    client.get_order.return_value = None  # Not found
    alert_fn = MagicMock()

    code = run_drill(
        client=client,
        symbol="BTC-USDT",
        send=True,
        env="demo",
        input_fn=lambda _: "YES",
        alert_fn=alert_fn,
        sleep_fn=lambda _: None,
    )

    assert code == 1



# ---------------------------------------------------------------------------
# Audit dot 113 (Claude): positionSide theo che do vi the; tu choi != khong ro
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hedge,expected", [(True, "LONG"), (False, "BOTH")])
def test_position_side_follows_account_mode(hedge, expected):
    """Hedge mode -> LONG (BOTH bi san tu choi 109400, dot 113); One-way -> BOTH."""
    client = create_mock_client()
    client.get_position_mode_dual.return_value = hedge
    client.place_limit_order.side_effect = BingXError("dung sau khi da thay tham so", code=109400)
    run_drill(client=client, symbol="BTC-USDT", send=True, env="demo",
              input_fn=lambda _: "YES", alert_fn=MagicMock())
    assert client.place_limit_order.call_args.kwargs["position_side"] == expected


def test_exchange_rejection_is_not_reported_as_unknown():
    """San tra code != 0 -> lenh KHONG duoc tao: exit 1, khong CRITICAL 'khong ro'."""
    client = create_mock_client()
    client.get_position_mode_dual.return_value = True
    client.place_limit_order.side_effect = BingXError("rejected", code=109400)
    alert_fn = MagicMock()
    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo",
                     input_fn=lambda _: "YES", alert_fn=alert_fn)
    assert code == 1
    alert_fn.assert_not_called()


def test_position_mode_unreadable_stops_before_send():
    """Khong doc duoc che do vi the -> dung, KHONG gui lenh."""
    client = create_mock_client()
    client.get_position_mode_dual.side_effect = BingXError("x", code=1)
    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo",
                     input_fn=lambda _: "YES", alert_fn=MagicMock())
    assert code == 1
    client.place_limit_order.assert_not_called()



def _order(status: str, executed: float = 0.0) -> dict:
    return {"order_id": 1, "symbol": "BTC-USDT", "price": 57000.0, "orig_qty": 0.0001,
            "executed_qty": executed, "status": status, "raw": {}}


def test_real_cancelled_spelling_confirms_cancel(tmp_path, monkeypatch):
    """San THAT tra 'CANCELLED' (dot 113, demo 27/09) -> phai xac nhan huy, exit 0.

    Ban dau code chi nhan 'CANCELED' -> bao dong gia 'LENH CON TREO' tren mot lenh da huy.
    """
    import scripts.bingx_drill_place_cancel as drill

    monkeypatch.setattr(drill, "LOGS_DIR", tmp_path)
    client = create_mock_client()
    client.get_position_mode_dual.return_value = True
    client.place_limit_order.return_value = {"order_id": 1, "client_order_id": "c", "status": "PENDING",
                                             "raw": {"postOnly": False}}
    client.get_order.side_effect = [_order("PENDING"), _order("CANCELLED")]
    alert_fn = MagicMock()
    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo",
                     input_fn=lambda _: "YES", alert_fn=alert_fn, sleep_fn=lambda _: None)
    assert code == 0
    alert_fn.assert_not_called()


def test_cancelled_but_partially_executed_is_critical(tmp_path, monkeypatch):
    """Da huy nhung executedQty > 0 -> da co vi the: CRITICAL, exit 2, khong bao 'huy thanh cong'."""
    import scripts.bingx_drill_place_cancel as drill

    monkeypatch.setattr(drill, "LOGS_DIR", tmp_path)
    client = create_mock_client()
    client.get_position_mode_dual.return_value = True
    client.place_limit_order.return_value = {"order_id": 1, "client_order_id": "c", "status": "PENDING", "raw": {}}
    client.get_order.side_effect = [_order("PENDING"), _order("CANCELLED", executed=0.0001)]
    alert_fn = MagicMock()
    code = run_drill(client=client, symbol="BTC-USDT", send=True, env="demo",
                     input_fn=lambda _: "YES", alert_fn=alert_fn, sleep_fn=lambda _: None)
    assert code == 2
    assert alert_fn.call_args[0][0] == "CRITICAL"
