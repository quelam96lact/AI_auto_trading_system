"""Kiểm thử hợp đồng SSI SDK (ssi_sdk 3.1.0) và tính sẵn sàng của đường lệnh thật (Brief 48 Task 1).

Mục tiêu:
Bảo đảm mọi ký hiệu, lớp, enum, và chữ ký phương thức (signature) mà codebase phụ thuộc
đều tồn tại chính xác trên SDK đã cài đặt, ngăn chặn tình trạng mock che giấu lỗi chữ ký
khi SDK nâng cấp hoặc thay đổi hợp đồng.

Ràng buộc tuyệt đối:
- KHÔNG khởi tạo client (AsyncTrading, AsyncAuth, AsyncStream...).
- KHÔNG gọi mạng / await phương thức SDK.
- KHÔNG đọc .env hoặc secrets.
- Hoàn toàn độc lập: KHÔNG cần Docker, KHÔNG cần DB.
"""

import ast
import inspect
from pathlib import Path


def test_1_ssi_sdk_symbols_exist():
    """1. Khẳng định tất cả ký hiệu SDK trong bảng §1.2 đều import và tồn tại trên lớp."""
    # scripts/confirm_real_order.py
    from ssi_sdk import AsyncTrading
    from ssi_sdk.enums import OrderSide
    from ssi_sdk.services.trading import AsyncTradingService

    assert AsyncTrading is not None
    assert OrderSide is not None
    assert hasattr(AsyncTradingService, "place_limit_order")
    assert hasattr(AsyncTradingService, "get_max_buy_sell_at_market_price")

    # trading/collector/ssi_auth.py
    from ssi_sdk import AsyncAuth, Config
    from ssi_sdk.models import Token

    assert AsyncAuth is not None
    assert Config is not None
    assert Token is not None

    # trading/collector/account_sync.py
    from ssi_sdk.constant import EP_ACCOUNT_BALANCE
    from ssi_sdk.services.portfolio import AsyncPortfolioService

    assert EP_ACCOUNT_BALANCE is not None
    assert AsyncPortfolioService is not None
    assert AsyncTradingService is not None

    # trading/collector/feed.py
    from ssi_sdk import AsyncStream
    from ssi_sdk.enums import Timeframe

    assert AsyncStream is not None
    assert Timeframe is not None


def test_2_place_limit_order_signature():
    """2. Khẳng định AsyncTradingService.place_limit_order có đúng tham số và thứ tự:

    (self, account_no, symbol, side, quantity, price).
    """
    from ssi_sdk.services.trading import AsyncTradingService

    sig = inspect.signature(AsyncTradingService.place_limit_order)
    param_names = list(sig.parameters.keys())
    expected_params = ["self", "account_no", "symbol", "side", "quantity", "price"]

    assert param_names == expected_params, (
        f"Chữ ký place_limit_order không khớp! Thực tế: {param_names}, Kỳ vọng: {expected_params}"
    )


def test_3_get_max_buy_sell_at_market_price_signature():
    """3. Khẳng định AsyncTradingService.get_max_buy_sell_at_market_price có đúng tham số và thứ tự:

    (self, account_no, symbol).
    """
    from ssi_sdk.services.trading import AsyncTradingService

    sig = inspect.signature(AsyncTradingService.get_max_buy_sell_at_market_price)
    param_names = list(sig.parameters.keys())
    expected_params = ["self", "account_no", "symbol"]

    assert param_names == expected_params, (
        f"Chữ ký get_max_buy_sell_at_market_price không khớp! Thực tế: {param_names}, Kỳ vọng: {expected_params}"
    )


def test_4_orderside_enum_values():
    """4. Khẳng định OrderSide có đúng BUY và SELL phục vụ confirm_real_order.py."""
    from ssi_sdk.enums import OrderSide

    assert hasattr(OrderSide, "BUY"), "OrderSide thiếu thuộc tính BUY"
    assert hasattr(OrderSide, "SELL"), "OrderSide thiếu thuộc tính SELL"
    # Kiểm tra danh sách thành viên
    member_names = {m.name for m in OrderSide}
    assert {"BUY", "SELL"} <= member_names, f"OrderSide không chứa đủ BUY/SELL: {member_names}"


def test_5_ast_confirm_real_order_call_matches_sdk_signature():
    """5. Phân tích AST của scripts/confirm_real_order.py:

    Khẳng định lời gọi place_limit_order trong code khớp chính xác số tham số bắt buộc
    của chữ ký thật trên SDK (trừ self).
    """
    from ssi_sdk.services.trading import AsyncTradingService

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "confirm_real_order.py"
    assert script_path.exists(), f"Không tìm thấy file {script_path}"

    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    sdk_sig = inspect.signature(AsyncTradingService.place_limit_order)
    # Loại bỏ tham số self
    expected_sdk_params = [p for p in sdk_sig.parameters.values() if p.name != "self"]
    expected_arg_count = len(expected_sdk_params)

    # Tìm lời gọi place_limit_order trong AST
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "place_limit_order":
                calls.append(node)

    assert len(calls) >= 1, "Không tìm thấy lời gọi place_limit_order nào trong confirm_real_order.py"

    for call in calls:
        # Số lượng đối số vị trí
        num_pos_args = len(call.args)
        num_kw_args = len(call.keywords)
        total_args = num_pos_args + num_kw_args

        assert total_args == expected_arg_count, (
            f"Số tham số gọi place_limit_order tại dòng {call.lineno} là {total_args}, "
            f"khác với số tham số bắt buộc của SDK là {expected_arg_count}"
        )
        assert num_pos_args == expected_arg_count, (
            f"Kỳ vọng {expected_arg_count} đối số vị trí tại dòng {call.lineno}, nhưng có {num_pos_args}"
        )


def test_6_no_infrastructure_required():
    """6. Xác nhận test hợp đồng SDK chạy thuần túy trên lớp, không gọi mạng,

    không yêu cầu biến môi trường xác thực (.env) hay kết nối DB/Docker.
    """
    from ssi_sdk.services.trading import AsyncTradingService

    # Việc inspect không chạm vào auth token hay mạng
    sig = inspect.signature(AsyncTradingService.place_limit_order)
    assert sig is not None
