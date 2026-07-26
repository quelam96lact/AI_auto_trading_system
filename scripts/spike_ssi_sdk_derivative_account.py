"""Phase 0 spike: xác nhận dữ liệu tài khoản phái sinh thật (VN30F1M).

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_account.py

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để có token trong
scripts/.ssi_sdk_token.json. Script này đọc lại (KHÔNG xin OTP mới);
tự refresh nếu access_token hết hạn.

Mục đích (PLAN_DERIVATIVE_TRADING.md Phase 0):
1. Gọi get_derivative_balance/get_derivative_ppmmr/get_derivative_positions/
   get_open_derivative_positions cho account phái sinh "0434228".
2. Tìm mã hợp đồng VN30 front-month thật qua get_securities_info() — verify
   các mã thực tế quan sát trên UI SSI.
3. Lưu raw response thật ra scripts/.spike_derivative_*.json để phân tích.

⚠️ TUYỆT ĐỐI KHÔNG gọi bất kừ method đặt lệnh nào trong script này.

Cần env SSI_API_KEY, SSI_API_SECRET.
"""

import base64
import dataclasses
import json
from datetime import date, datetime, timezone
from pathlib import Path

from _ssi_spike_common import make_auth

ACCOUNT_NO = "0434228"
INDEX_NAME = "VN30"

# Các mã phái sinh VN30 thực tế quan sát trên UI SSI (2026-07-26), xếp theo
# open_interest giảm dần — dùng làm thứ tự ưu tiên thử qua get_securities_info.
# Giá trị OI chỉ để sắp xếp, KHÔNG lấy từ API; mã đầu tiên (41I1G8000) đã được
# UI xác nhận là HDTL VN30 đáo hạn 20/08/2026, OI cao nhất -> front-month.
OBSERVED_CANDIDATES: list[tuple[str, int]] = [
    ("41I1G8000", 39_352),
    ("41I1G9000", 1_140),
    ("41I1GC000", 843),
    ("41I1H3000", 36),
    ("41I2G8000", 68),
    ("41I2G9000", 19),
    ("41I2GC000", 42),
    ("41I2H3000", 6),
]

BALANCE_OUT = Path(__file__).parent / ".spike_derivative_balance.json"
PPMMR_OUT = Path(__file__).parent / ".spike_derivative_ppmmr.json"
POSITIONS_OUT = Path(__file__).parent / ".spike_derivative_positions.json"
CONTRACT_OUT = Path(__file__).parent / ".spike_derivative_contract_symbol.json"


def _serialize(obj):
    """Serialize dataclass / enum / datetime ra JSON an toàn."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)


def _save_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_serialize),
        encoding="utf-8",
    )


def _decode_jwt_claims(access_token: str) -> dict:
    """Decode phần payload (giữa) của JWT — không verify signature (chỉ đọc claim)."""
    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _parse_date(value: str | None) -> date | None:
    """Parse ngày từ các định dạng gặp phải: YYYY-MM-DD hoặc YYYY/MM/DD."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


async def fetch_derivative_account(trading) -> None:
    print(f"\nGọi get_derivative_balance({ACCOUNT_NO})...")
    try:
        balance = await trading.portfolio.get_derivative_balance(ACCOUNT_NO)
        payload = dataclasses.asdict(balance) if balance is not None else None
        _save_json(BALANCE_OUT, payload)
        print(f"OK → {BALANCE_OUT}")
        print(" ", payload)
    except Exception as e:
        print(f"!! get_derivative_balance({ACCOUNT_NO}) lỗi: {e}")

    print(f"\nGọi get_derivative_ppmmr({ACCOUNT_NO})...")
    try:
        ppmmr = await trading.portfolio.get_derivative_ppmmr(ACCOUNT_NO)
        payload = dataclasses.asdict(ppmmr) if ppmmr is not None else None
        _save_json(PPMMR_OUT, payload)
        print(f"OK → {PPMMR_OUT}")
        print(" ", payload)
    except Exception as e:
        print(f"!! get_derivative_ppmmr({ACCOUNT_NO}) lỗi: {e}")

    print(f"\nGọi get_derivative_positions({ACCOUNT_NO})...")
    try:
        result = await trading.portfolio.get_derivative_positions(ACCOUNT_NO)
        # Type hint SDK nói list[AllDerivativePosition] nhưng thực tế trả về 1
        # object AllDerivativePosition với open_positions + closed_positions.
        if result is not None:
            payload = {
                "open_positions": [dataclasses.asdict(p) for p in result.open_positions],
                "closed_positions": [dataclasses.asdict(p) for p in result.closed_positions],
            }
        else:
            payload = {"open_positions": [], "closed_positions": []}
        _save_json(POSITIONS_OUT, payload)
        print(
            f"OK — {len(payload['open_positions'])} mở, "
            f"{len(payload['closed_positions'])} đã đóng → {POSITIONS_OUT}"
        )
        print(" ", payload)
    except Exception as e:
        print(f"!! get_derivative_positions({ACCOUNT_NO}) lỗi: {e}")

    print(f"\nGọi get_open_derivative_positions({ACCOUNT_NO})...")
    try:
        open_positions = await trading.portfolio.get_open_derivative_positions(ACCOUNT_NO)
        print(f"OK — {len(open_positions)} vị thế mở")
        for p in open_positions:
            print(" ", dataclasses.asdict(p))
    except Exception as e:
        print(f"!! get_open_derivative_positions({ACCOUNT_NO}) lỗi: {e}")


async def _fetch_securities_info_raw(data, symbol: str) -> dict | None:
    """Bypass SecuritiesInfo.from_list() — SDK crash khi board='DERIVATIVES'
    (Board enum chỉ có HOSE/HNX/UPCOM, thiếu DERIVATIVES). Gọi thẳng REST endpoint
    thật (/api/v3/data/securitiesByBoard, param symbol=<symbol>) và tự đọc field
    cần thiết từ dict thô, không qua Board(...) enum conversion bị lỗi."""
    raw = await data.market_data._rest.get(
        "/api/v3/data/securitiesByBoard", params={"symbol": symbol}
    )
    if not raw:
        return None
    return raw[0]


async def find_front_month_contract(data) -> str | None:
    """Tìm symbol thật của hợp đồng VN30 front-month từ response thật.

    Các endpoint get_indexes()/get_securities_info_by_index()/get_securities_summary_by_index()
    đã xác nhận KHÔNG trả về hợp đồng phái sinh. Thay vào đó dùng
    get_securities_info(symbol) để verify từng mã thật quan sát trên UI SSI.
    """
    print(f"\nTìm mã hợp đồng {INDEX_NAME} front-month...")
    print("Thử các mã thật quan sát trên UI SSI qua get_securities_info()...")

    verified: list[dict] = []
    for symbol, _ in OBSERVED_CANDIDATES:
        try:
            record = await _fetch_securities_info_raw(data, symbol)
        except Exception as e:
            print(f"  {symbol}: lỗi khi gọi get_securities_info — {e}")
            continue
        if record is None:
            print(f"  {symbol}: không tồn tại qua get_securities_info()")
            continue
        print(f"  {symbol}: OK — {record}")
        verified.append(record)

    if not verified:
        tried = [s for s, _ in OBSERVED_CANDIDATES]
        print(
            "\nKhông mã nào trong danh sách quan sát từ UI SSI hợp lệ qua get_securities_info().\n"
            f"Đã thử: {tried}. get_securities_info() có thể không hỗ trợ tra cứu hợp "
            "đồng phái sinh theo symbol dạng này, hoặc mã đã đổi — cần đối chiếu lại "
            "UI SSI tại thởi điểm chạy script, không suy đoán thêm."
        )
        return None

    # Ưu tiên mã 41I1G8000 nếu hợp lệ (đã xác nhận qua UI là front-month VN30).
    preferred = "41I1G8000"
    preferred_record = next((r for r in verified if r.get("symbol") == preferred), None)

    if preferred_record:
        front = preferred
        print(f"\n=> Mã hợp đồng VN30 front-month chọn (ưu tiên UI): {front}")
    else:
        today = date.today()

        def _maturity_distance(record: dict) -> float:
            maturity = _parse_date(record.get("maturityDate"))
            if maturity is None:
                maturity = _parse_date(record.get("lastTradingDate"))
            if maturity is None:
                return float("inf")
            return abs((maturity - today).days)

        best = min(verified, key=_maturity_distance)
        front = best["symbol"]
        print(
            f"\n=> Mã hợp đồng VN30 front-month chọn (maturity gần nhất so với "
            f"{today.isoformat()}): {front}"
        )

    _save_json(
        CONTRACT_OUT,
        {
            "symbol": front,
            "index": INDEX_NAME,
            "candidates": verified,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"Đã lưu → {CONTRACT_OUT}")
    return front


async def main() -> None:
    from ssi_sdk import AsyncData, AsyncTrading

    auth = await make_auth()
    claims = _decode_jwt_claims(auth.token_manager.access_token)
    client_id = claims.get("client_id", "")
    print(f"client_id (từ JWT): {client_id}")
    # Các API Portfolio phái sinh (balance/positions) yêu cầu clientId;
    # set thủ công giống pattern trong scripts/spike_ssi_sdk_account.py.
    auth.config.client_id = client_id

    try:
        trading = AsyncTrading(auth)
        data = AsyncData(auth)

        await fetch_derivative_account(trading)
        await find_front_month_contract(data)
    finally:
        await auth.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
