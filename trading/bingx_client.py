"""Client HTTP chỉ đọc cho BingX Swap / Perpetual API (Brief 111).

Tài liệu chính thức:
- Cổng tài liệu: https://bingx-api.github.io/docs/
- Base URL: https://open-api.bingx.com
- Xác thực & Ký HMAC-SHA256: https://bingx-api.github.io/docs/#/swapV2/authentication.html#Signature
- Giờ server: https://bingx-api.github.io/docs/#/swapV2/base-info.html#Server%20Time
- Số dư tài khoản: https://bingx-api.github.io/docs/#/swapV2/account-api.html#Query%20Account%20Data
- Vị thế đang mở: https://bingx-api.github.io/docs/#/swapV2/account-api.html#Position%20Information
- Lệnh đang chờ: https://bingx-api.github.io/docs/#/swapV2/trade-api.html#Query%20Open%20Orders
- Thông số hợp đồng: https://bingx-api.github.io/docs/#/swapV2/market-api.html#Contract%20Information
- Ticker giá hiện tại: https://bingx-api.github.io/docs/#/swapV2/market-api.html#24hr%20Ticker%20Price%20Change%20Statistics

RÀNG BUỘC KIẾN TRÚC:
- Client này TUYỆT ĐỐI CHỈ ĐỌC (chỉ gửi HTTP GET). Không có phương thức đặt/hủy/sửa lệnh.
- Không bao giờ để lộ api_secret trong log, exception, repr hoặc str.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import requests


class BingXError(Exception):
    """Ngoại lệ khi gọi BingX API thất bại.

    Đảm bảo an toàn: Không bao giờ chứa api_secret trong thông điệp.
    """

    def __init__(self, message: str, code: int | None = None, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:
        parts = []
        if self.status_code is not None:
            parts.append(f"HTTP {self.status_code}")
        if self.code is not None:
            parts.append(f"code={self.code}")
        parts.append(self.message)
        return f"[BingXError] {': '.join(parts)}"


def sign_params(params: dict[str, Any], api_secret: str) -> tuple[str, str]:
    """Tạo chuỗi tham số đã sắp xếp thứ tự và tính chữ ký HMAC-SHA256.

    Quy chuẩn BingX:
    - Loại bỏ các tham số có giá trị None.
    - Sắp xếp các tham số theo thứ tự bảng chữ cái của key (alphabetical order).
    - Nối các cặp key=value bằng dấu '&'.
    - Ký chuỗi trên bằng thuật toán HMAC-SHA256 với api_secret.

    Returns:
        tuple (canonical_query_string, hex_signature)
    """
    filtered_params = {k: v for k, v in params.items() if v is not None}
    sorted_keys = sorted(filtered_params.keys())
    canonical_qs = "&".join(f"{k}={filtered_params[k]}" for k in sorted_keys)

    signature = hmac.new(
        api_secret.encode("utf-8"),
        canonical_qs.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return canonical_qs, signature


def _require(d: Any, key: str, ctx: str) -> Any:
    """Lay truong BAT BUOC tu phan hoi BingX; thieu -> BingXError, KHONG tra mac dinh.

    Audit dot 111: ban dau dung `.get(key, 0.0)` nen phan hoi doi dinh dang se ra "so du 0"
    thay vi loi — dung loai "khong doc duoc" gia lam "bang 0" ma brief §3 muc 3 cam.
    """
    if not isinstance(d, dict) or key not in d or d[key] is None:
        raise BingXError(f"Phan hoi {ctx} thieu truong bat buoc '{key}'")
    return d[key]


def _num(d: Any, key: str, ctx: str) -> float:
    return float(_require(d, key, ctx))


class BingXClient:
    """Client HTTP chỉ đọc tương tác với BingX Perpetual Swap API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://open-api.bingx.com",
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ):
        self._api_key = api_key.strip()
        self._api_secret = api_secret.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()

    def __repr__(self) -> str:
        masked_key = f"{self._api_key[:4]}..." if len(self._api_key) >= 4 else "***"
        return f"BingXClient(api_key='{masked_key}', base_url='{self._base_url}')"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def api_key(self) -> str:
        """Trả về API key (dạng che nếu cần log)."""
        return self._api_key

    def _get(self, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> dict[str, Any]:
        """Gửi request HTTP GET duy nhất (kiến trúc chỉ đọc)."""
        request_params = dict(params or {})
        headers = {}

        if signed:
            if not self._api_key or not self._api_secret:
                raise BingXError("Missing API key or secret for signed request")

            if "timestamp" not in request_params:
                request_params["timestamp"] = int(time.time() * 1000)

            qs, signature = sign_params(request_params, self._api_secret)
            url = f"{self._base_url}{path}?{qs}&signature={signature}"
            headers["X-BX-APIKEY"] = self._api_key
            req_params = None  # Đã gộp vào URL cùng signature
        else:
            url = f"{self._base_url}{path}"
            req_params = {k: v for k, v in request_params.items() if v is not None}

        try:
            resp = self._session.get(url, params=req_params, headers=headers, timeout=self._timeout)
        except requests.exceptions.Timeout as e:
            raise BingXError(f"Request timeout to {path}: {e}") from e
        except requests.exceptions.RequestException as e:
            # Đảm bảo không bao giờ để lộ secret nếu exception có url chứa query string
            safe_err = str(e).replace(self._api_secret, "***") if self._api_secret else str(e)
            raise BingXError(f"HTTP request failed to {path}: {safe_err}") from e

        # 1. Kiểm tra HTTP Status Code
        if resp.status_code != 200:
            err_msg = f"HTTP status {resp.status_code}: {resp.text}"
            safe_msg = err_msg.replace(self._api_secret, "***") if self._api_secret else err_msg
            raise BingXError(safe_msg, status_code=resp.status_code)

        # 2. Parse JSON
        try:
            data = resp.json()
        except Exception as e:
            safe_text = resp.text.replace(self._api_secret, "***") if self._api_secret else resp.text
            raise BingXError(f"Failed to parse JSON response: {safe_text}") from e

        if not isinstance(data, dict):
            raise BingXError(f"Unexpected non-dict response format: {type(data)}")

        # 3. Kiểm tra mã lỗi nghiệp vụ của BingX (code != 0 là lỗi)
        code = data.get("code")
        if code != 0:
            msg = data.get("msg", "Unknown error")
            safe_msg = str(msg).replace(self._api_secret, "***") if self._api_secret else str(msg)
            raise BingXError(f"BingX API error (code {code}): {safe_msg}", code=code, status_code=resp.status_code)

        return data

    # -----------------------------------------------------------------------
    # Các phương thức công khai (Public Endpoints)
    # -----------------------------------------------------------------------

    def get_server_time(self) -> int:
        """Lấy giờ hiện tại của server BingX (milliseconds epoch).

        Endpoint: GET /openApi/swap/v2/server/time (Public)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/base-info.html#Server%20Time
        """
        res = self._get("/openApi/swap/v2/server/time", signed=False)
        data = res.get("data", {})
        server_time = data.get("serverTime")
        if server_time is None:
            raise BingXError(f"Missing serverTime in response: {res}")
        return int(server_time)

    def get_clock_offset(self) -> int:
        """Đo độ lệch đồng hồ giữa máy local và server BingX (ms).

        Cong thuc: diem_giua_khu_hoi_local - server_time_ms. Audit dot 111: ban dau lay gio
        local TRUOC khi gui roi tru gio server -> ca do tre khu hoi bi tinh thanh lech dong ho.
        """
        t0 = time.time() * 1000
        server_time_ms = self.get_server_time()
        t1 = time.time() * 1000
        return int((t0 + t1) / 2 - server_time_ms)

    def get_contracts(self) -> list[dict[str, Any]]:
        """Lấy danh sách thông số các hợp đồng perpetual futures đang giao dịch.

        Endpoint: GET /openApi/swap/v2/quote/contracts (Public)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/market-api.html#Contract%20Information
        """
        res = self._get("/openApi/swap/v2/quote/contracts", signed=False)
        data = _require(res, "data", "contracts")
        if not isinstance(data, list):
            raise BingXError(f"Phan hoi contracts: 'data' khong phai list ({type(data).__name__})")
        return list(data)

    def get_contract(self, symbol: str) -> dict[str, Any]:
        """Lấy thông số chi tiết hợp đồng của mã cụ thể (vd: 'BTC-USDT').

        Trích xuất và chuẩn hóa:
        - tick_size (bước giá): tính từ pricePrecision (vd: 1 -> 0.1)
        - step_size (bước khối lượng): size hoặc tính từ quantityPrecision (vd: 4 -> 0.0001)
        - min_qty (khối lượng tối thiểu): tradeMinQuantity
        - min_notional (giá trị tối thiểu): tradeMinUSDT
        - maker_fee_rate, taker_fee_rate: phí niêm yết
        """
        contracts = self.get_contracts()
        target = symbol.upper()
        for c in contracts:
            if c.get("symbol", "").upper() == target:
                ctx = f"contract {target}"
                price_precision = int(_require(c, "pricePrecision", ctx))
                qty_precision = int(_require(c, "quantityPrecision", ctx))
                tick_size = round(10.0 ** (-price_precision), price_precision)
                step_size = _num(c, "size", ctx)

                return {
                    "symbol": c.get("symbol"),
                    "contract_id": c.get("contractId"),
                    "price_precision": price_precision,
                    "quantity_precision": qty_precision,
                    "tick_size": tick_size,
                    "step_size": step_size,
                    "min_qty": _num(c, "tradeMinQuantity", ctx),
                    "min_notional": _num(c, "tradeMinUSDT", ctx),
                    # KHONG doan phi (rang buoc dung cua du an): thieu truong -> loi.
                    "maker_fee_rate": _num(c, "makerFeeRate", ctx),
                    "taker_fee_rate": _num(c, "takerFeeRate", ctx),
                    "raw": c,
                }
        raise BingXError(f"Symbol '{symbol}' not found in contract information")

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Lấy thông tin giá mới nhất của mã (vd: 'BTC-USDT').

        Endpoint: GET /openApi/swap/v2/quote/ticker (Public)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/market-api.html#24hr%20Ticker%20Price%20Change%20Statistics
        """
        res = self._get("/openApi/swap/v2/quote/ticker", params={"symbol": symbol.upper()}, signed=False)
        data = _require(res, "data", "ticker")
        ctx = f"ticker {symbol.upper()}"
        return {
            "symbol": _require(data, "symbol", ctx),
            "last_price": _num(data, "lastPrice", ctx),
            "bid_price": _num(data, "bidPrice", ctx),
            "ask_price": _num(data, "askPrice", ctx),
            "volume_24h": _num(data, "volume", ctx),
            "raw": data,
        }

    # -----------------------------------------------------------------------
    # Các phương thức có chữ ký xác thực (Private Endpoints)
    # -----------------------------------------------------------------------

    def get_perpetual_balance(self, recv_window: int = 5000) -> dict[str, Any]:
        """Lấy số dư tài khoản Perpetual Swap (USDT-M).

        Endpoint: GET /openApi/swap/v2/user/balance (Signed)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/account-api.html#Query%20Account%20Data
        """
        params: dict[str, Any] = {"recvWindow": recv_window}
        res = self._get("/openApi/swap/v2/user/balance", params=params, signed=True)
        data = _require(res, "data", "balance")
        bal_data = _require(data, "balance", "balance")
        ctx = "balance"
        return {
            "asset": _require(bal_data, "asset", ctx),
            "balance": _num(bal_data, "balance", ctx),
            "equity": _num(bal_data, "equity", ctx),
            "available_margin": _num(bal_data, "availableMargin", ctx),
            "used_margin": _num(bal_data, "usedMargin", ctx),
            "freezed_margin": _num(bal_data, "freezedMargin", ctx),
            "unrealized_profit": _num(bal_data, "unrealizedProfit", ctx),
            "realized_profit": _num(bal_data, "realisedProfit", ctx),
            "raw": bal_data,
        }

    def get_positions(self, symbol: str | None = None, recv_window: int = 5000) -> list[dict[str, Any]]:
        """Lấy danh sách các vị thế perpetual đang mở.

        Endpoint: GET /openApi/swap/v2/user/positions (Signed)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/account-api.html#Position%20Information
        """
        params: dict[str, Any] = {"recvWindow": recv_window}
        if symbol:
            params["symbol"] = symbol.upper()

        res = self._get("/openApi/swap/v2/user/positions", params=params, signed=True)
        raw_positions = _require(res, "data", "positions")
        if isinstance(raw_positions, dict):
            raw_positions = [raw_positions]
        if not isinstance(raw_positions, list):
            raise BingXError(f"Phan hoi positions: 'data' khong phai list ({type(raw_positions).__name__})")

        positions = []
        ctx = "positions"
        for p in raw_positions:
            pos_amt = _num(p, "positionAmt", ctx)
            # Chi lay vi the THAT SU co khoi luong. Audit dot 111: dieu kien cu
            # `pos_amt != 0.0 or not symbol` tra ca vi the 0 khi khong truyen symbol.
            if pos_amt != 0.0:
                positions.append({
                    "symbol": _require(p, "symbol", ctx),
                    "position_id": p.get("positionId"),
                    "position_side": _require(p, "positionSide", ctx),
                    "position_amt": pos_amt,
                    "avg_price": _num(p, "avgPrice", ctx),
                    "unrealized_profit": _num(p, "unrealizedProfit", ctx),
                    "leverage": int(_num(p, "leverage", ctx)),
                    "raw": p,
                })
        return positions

    def get_open_orders(self, symbol: str | None = None, recv_window: int = 5000) -> list[dict[str, Any]]:
        """Lấy danh sách các lệnh đang chờ (open orders).

        Endpoint: GET /openApi/swap/v2/trade/openOrders (Signed)
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/trade-api.html#Query%20Open%20Orders
        """
        params: dict[str, Any] = {"recvWindow": recv_window}
        if symbol:
            params["symbol"] = symbol.upper()

        res = self._get("/openApi/swap/v2/trade/openOrders", params=params, signed=True)
        data = _require(res, "data", "openOrders")
        raw_orders = _require(data, "orders", "openOrders") if isinstance(data, dict) else data
        if not isinstance(raw_orders, list):
            raise BingXError(f"Phan hoi openOrders: 'orders' khong phai list ({type(raw_orders).__name__})")

        orders = []
        ctx = "openOrders"
        for o in raw_orders:
            orders.append({
                "order_id": _require(o, "orderId", ctx),
                "symbol": _require(o, "symbol", ctx),
                "price": _num(o, "price", ctx),
                "orig_qty": _num(o, "origQty", ctx),
                "side": _require(o, "side", ctx),
                "type": _require(o, "type", ctx),
                "raw": o,
            })
        return orders


# ---------------------------------------------------------------------------
# Lớp đặt / huỷ / tra cứu lệnh (Brief 112)
# TÁCH BIỆT HOÀN TOÀN: BingXClient chỉ đọc giữ nguyên, không có quyền đặt lệnh.
# BingXTradeClient kế thừa BingXClient nhưng trang bị các phương thức giao dịch.
# ---------------------------------------------------------------------------


def _order_payload(res: dict[str, Any], ctx: str) -> dict[str, Any]:
    """Lay object lenh tu phan hoi trade (`data.order` hoac `data`); thieu -> BingXError."""
    data = _require(res, "data", ctx)
    if not isinstance(data, dict):
        raise BingXError(f"Phan hoi {ctx}: 'data' khong phai object ({type(data).__name__})")
    order = data.get("order", data)
    if not isinstance(order, dict):
        raise BingXError(f"Phan hoi {ctx}: 'order' khong phai object ({type(order).__name__})")
    return order


class BingXTradeClient(BingXClient):
    """Client đặt và huỷ lệnh cho BingX Perpetual Swap API (Brief 112).

    Kế thừa BingXClient để tái sử dụng các phương thức đọc thị trường / số dư,
    và bổ sung các phương thức gửi lệnh có ký HMAC-SHA256 (POST / DELETE / GET).

    BẢO MẬT:
    - Không bao giờ để lộ api_secret trong exception, repr, str, hoặc log.
    - Lớp này CHỈ được phép import trong scripts/bingx_drill_place_cancel.py
      và các file test tương ứng. Tuyệt đối không import vào trading/engine/.
    """

    def __repr__(self) -> str:
        masked_key = f"{self._api_key[:4]}..." if len(self._api_key) >= 4 else "***"
        return f"BingXTradeClient(api_key='{masked_key}', base_url='{self._base_url}')"

    def _trade_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gửi request HTTP (POST/DELETE/GET) có chữ ký HMAC-SHA256 cho Trade API."""
        if not self._api_key or not self._api_secret:
            raise BingXError("Missing API key or secret for signed trade request")

        request_params = dict(params or {})
        if "timestamp" not in request_params:
            request_params["timestamp"] = int(time.time() * 1000)

        qs, signature = sign_params(request_params, self._api_secret)
        url = f"{self._base_url}{path}?{qs}&signature={signature}"
        headers = {"X-BX-APIKEY": self._api_key}

        try:
            resp = self._session.request(
                method.upper(),
                url,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as e:
            raise BingXError(f"Trade request timeout to {path}: {e}") from e
        except requests.exceptions.RequestException as e:
            safe_err = str(e).replace(self._api_secret, "***") if self._api_secret else str(e)
            raise BingXError(f"Trade HTTP request failed to {path}: {safe_err}") from e

        if resp.status_code != 200:
            err_msg = f"HTTP status {resp.status_code}: {resp.text}"
            safe_msg = err_msg.replace(self._api_secret, "***") if self._api_secret else err_msg
            raise BingXError(safe_msg, status_code=resp.status_code)

        try:
            data = resp.json()
        except Exception as e:
            safe_text = resp.text.replace(self._api_secret, "***") if self._api_secret else resp.text
            raise BingXError(f"Failed to parse JSON trade response: {safe_text}") from e

        if not isinstance(data, dict):
            raise BingXError(f"Unexpected non-dict trade response format: {type(data)}")

        code = data.get("code")
        if code != 0:
            msg = data.get("msg", "Unknown trade error")
            safe_msg = str(msg).replace(self._api_secret, "***") if self._api_secret else str(msg)
            raise BingXError(f"BingX Trade API error (code {code}): {safe_msg}", code=code, status_code=resp.status_code)

        return data

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        position_side: str = "BOTH",
        time_in_force: str = "PostOnly",
        client_order_id: str | None = None,
        recv_window: int = 5000,
    ) -> dict[str, Any]:
        """Đặt lệnh giới hạn (LIMIT) trên BingX Perpetual Swap.

        Endpoint: POST /openApi/swap/v2/trade/order
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/trade-api.html#Place%20Order
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "positionSide": position_side.upper(),
            "price": str(price),
            "quantity": str(quantity),
            "timeInForce": time_in_force,
            "recvWindow": recv_window,
        }
        if client_order_id:
            params["clientOrderID"] = client_order_id

        res = self._trade_request("POST", "/openApi/swap/v2/trade/order", params=params)
        order_dict = _order_payload(res, "place_order")
        # orderId BAT BUOC (audit dot 112): thieu no thi KHONG huy duoc -> lenh mo coi tren san.
        # Cac truong con lai tra nguyen tu san (co the vang), KHONG dien gia tri minh gui.
        return {
            "order_id": _require(order_dict, "orderId", "place_order"),
            "client_order_id": order_dict.get("clientOrderID"),
            "symbol": order_dict.get("symbol"),
            "side": order_dict.get("side"),
            "type": order_dict.get("type"),
            "status": order_dict.get("status"),
            "raw": order_dict,
        }

    def cancel_order(
        self,
        symbol: str,
        order_id: int | str | None = None,
        client_order_id: str | None = None,
        recv_window: int = 5000,
    ) -> dict[str, Any]:
        """Huỷ một lệnh trên BingX Perpetual Swap theo orderId hoặc clientOrderID.

        Endpoint: DELETE /openApi/swap/v2/trade/order
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/trade-api.html#Cancel%20an%20Order
        """
        if order_id is None and client_order_id is None:
            raise BingXError("Phải cung cấp ít nhất order_id hoặc client_order_id để huỷ lệnh")

        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "recvWindow": recv_window,
        }
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["clientOrderID"] = client_order_id

        res = self._trade_request("DELETE", "/openApi/swap/v2/trade/order", params=params)
        order_dict = _order_payload(res, "cancel_order")
        # KHONG mac dinh status "CANCELED" (audit dot 112): phan hoi thieu status ma tra
        # "da huy" la bao an toan gia cho mot lenh co the con treo. Xac nhan huy that nam
        # o get_order sau do (drill buoc 3).
        return {
            "order_id": order_dict.get("orderId"),
            "client_order_id": order_dict.get("clientOrderID"),
            "symbol": order_dict.get("symbol"),
            "status": order_dict.get("status"),
            "raw": order_dict,
        }

    def get_order(
        self,
        symbol: str,
        order_id: int | str | None = None,
        client_order_id: str | None = None,
        recv_window: int = 5000,
    ) -> dict[str, Any]:
        """Tra cứu chi tiết một lệnh trên BingX Perpetual Swap theo orderId hoặc clientOrderID.

        Endpoint: GET /openApi/swap/v2/trade/order
        Tài liệu: https://bingx-api.github.io/docs/#/swapV2/trade-api.html#Query%20Order%20Details
        """
        if order_id is None and client_order_id is None:
            raise BingXError("Phải cung cấp ít nhất order_id hoặc client_order_id để tra cứu lệnh")

        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "recvWindow": recv_window,
        }
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["clientOrderID"] = client_order_id

        res = self._trade_request("GET", "/openApi/swap/v2/trade/order", params=params)
        order_dict = _order_payload(res, "get_order")
        ctx = "get_order"
        # status va executedQty BAT BUOC (audit dot 112): day la hai truong drill dung de
        # quyet "da khop / con treo / da huy". Mac dinh 0/"" se doc lenh DA KHOP thanh chua khop.
        return {
            "order_id": _require(order_dict, "orderId", ctx),
            "client_order_id": order_dict.get("clientOrderID"),
            "symbol": _require(order_dict, "symbol", ctx),
            "price": _num(order_dict, "price", ctx),
            "orig_qty": _num(order_dict, "origQty", ctx),
            "executed_qty": _num(order_dict, "executedQty", ctx),
            "status": str(_require(order_dict, "status", ctx)),
            "type": order_dict.get("type"),
            "side": order_dict.get("side"),
            "raw": order_dict,
        }

