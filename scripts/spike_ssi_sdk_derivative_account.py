"""Phase 0 spike: xác nhận dữ liệu tài khoản phái sinh thật (VN30F1M).

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_account.py

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để có token trong
scripts/.ssi_sdk_token.json. Script này đọc lại (KHÔNG xin OTP mới);
tự refresh nếu access_token hết hạn.

Mục đích (PLAN_DERIVATIVE_TRADING.md Phase 0):
1. Gọi get_derivative_balance/get_derivative_ppmmr/get_derivative_positions/
   get_open_derivative_positions cho account phái sinh "0434228".
2. Tìm mã hợp đồng VN30F1M thật (front-month) qua get_indexes() hoặc
   get_securities_info_by_index("VN30").
3. Lưu raw response thật ra scripts/.spike_derivative_*.json để phân tích.

⚠️ TUYỆT ĐỐI KHÔNG gọi bất kừ method đặt lệnh nào trong script này.

Cần env SSI_API_KEY, SSI_API_SECRET.
"""

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from _ssi_spike_common import make_auth

ACCOUNT_NO = "0434228"
INDEX_NAME = "VN30"

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
        positions = await trading.portfolio.get_derivative_positions(ACCOUNT_NO)
        payload = [dataclasses.asdict(p) for p in positions] if positions else []
        _save_json(POSITIONS_OUT, payload)
        print(f"OK — {len(payload)} vị thế → {POSITIONS_OUT}")
        for p in payload:
            print(" ", p)
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


async def find_front_month_contract(data) -> str | None:
    """Tìm symbol thật của hợp đồng VN30 front-month từ response thật.

    Thử nhiều nguồn: get_indexes(), get_securities_info_by_index(),
    get_securities_summary_by_index(). Không hardcode symbol.
    """
    print(f"\nTìm mã hợp đồng {INDEX_NAME} front-month...")

    candidates: list[str] = []

    # 1) Thử get_indexes()
    try:
        indexes = await data.market_data.get_indexes()
        print(f" get_indexes() trả về {len(indexes)} index")
        for idx in indexes:
            d = dataclasses.asdict(idx) if dataclasses.is_dataclass(idx) else idx
            print("  ", d)
            # Các field gợi ý: indexCode, indexName, futureCode,...
            code = str(d.get("indexCode", d.get("index", d.get("code", ""))))
            name = str(d.get("indexName", d.get("name", "")))
            if INDEX_NAME in (code.upper(), name.upper()):
                future = d.get("futureCode") or d.get("futureSymbol") or d.get("derivativeCode")
                if future:
                    candidates.append(str(future))
    except Exception as e:
        print(f"!! get_indexes() lỗi: {e}")

    # 2) Thử get_securities_info_by_index(INDEX_NAME)
    try:
        securities = await data.market_data.get_securities_info_by_index(INDEX_NAME)
        print(f" get_securities_info_by_index({INDEX_NAME}) trả về {len(securities)} mã")
        for s in securities:
            d = dataclasses.asdict(s) if dataclasses.is_dataclass(s) else s
            print("  ", d)
            sym = str(d.get("symbol", d.get("Symbol", d.get("stockSymbol", ""))))
            # Chỉ chọn symbol bắt đầu VN30F — đó là hợp đồng tương lai VN30.
            if sym.upper().startswith("VN30F"):
                candidates.append(sym)
    except Exception as e:
        print(f"!! get_securities_info_by_index({INDEX_NAME}) lỗi: {e}")

    # 3) Thử get_securities_summary_by_index(INDEX_NAME) nếu vẫn chưa có
    if not candidates:
        try:
            summaries = await data.market_data.get_securities_summary_by_index(INDEX_NAME)
            print(f" get_securities_summary_by_index({INDEX_NAME}) trả về {len(summaries)} mã")
            for s in summaries:
                d = dataclasses.asdict(s) if dataclasses.is_dataclass(s) else s
                print("  ", d)
                sym = str(d.get("symbol", d.get("Symbol", d.get("stockSymbol", ""))))
                if sym.upper().startswith("VN30F"):
                    candidates.append(sym)
        except Exception as e:
            print(f"!! get_securities_summary_by_index({INDEX_NAME}) lỗi: {e}")

    if not candidates:
        print("!! Không tìm được mã hợp đồng VN30F front-month từ API.")
        return None

    # Ưu tiên symbol ngắn nhất trong các ứng viên bắt đầu VN30F (front-month
    # thường là mã gần nhất, không phải kỳ hạn xa).
    front = sorted({c for c in candidates if c.upper().startswith("VN30F")}, key=len)[0]
    print(f"\n=> Mã hợp đồng VN30 front-month chọn: {front}")
    _save_json(
        CONTRACT_OUT,
        {
            "symbol": front,
            "index": INDEX_NAME,
            "candidates": sorted(set(candidates)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"Đã lưu → {CONTRACT_OUT}")
    return front


async def main() -> None:
    from ssi_sdk import AsyncData, AsyncTrading

    auth = await make_auth()
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
