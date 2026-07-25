"""Phase 0 spike: xác nhận Portfolio/Account API thật (số dư, vị thế).

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_account.py

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để có token trong
scripts/.ssi_sdk_token.json (script này đọc lại, KHÔNG xin OTP mới;
tự refresh nếu access_token hết hạn, giống spike_ssi_sdk_ohlc.py).

Mục đích (PLAN_ACCOUNT_DATA_SYNC.md Phase 0):
1. Decode client_id + accounts từ JWT access_token — xác nhận giả
   thuyết "client_id đã có sẵn trong token, không cần credential mới".
2. Gọi get_account_info() — xem loại từng account trong 3 account.
3. Gọi get_equity_balance()/get_equity_positions() cho account xác
   định là equity — xác nhận có cần OTP không (nếu lỗi 401/403, in rõ
   response_body qua log_level=DEBUG, giống pattern các script trước).
4. Lưu response thật ra tests/fixtures/ (thư mục scripts/ trước, review
   xong mới copy vào tests/fixtures/ chính thức).

Cần env SSI_API_KEY, SSI_API_SECRET (không cần SSI_CLIENT_ID — lấy từ
JWT, xem mục đích #1).
"""

import base64
import dataclasses
import json
from pathlib import Path

from _ssi_spike_common import make_auth

ACCOUNT_INFO_OUT = Path(__file__).parent / ".spike_account_info.json"
BALANCE_OUT = Path(__file__).parent / ".spike_equity_balance.json"
POSITIONS_OUT = Path(__file__).parent / ".spike_equity_positions.json"


def _decode_jwt_claims(access_token: str) -> dict:
    """Decode phần payload (giữa) của JWT — không verify signature (chỉ đọc claim)."""
    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


async def main() -> None:
    from ssi_sdk import AsyncTrading

    auth = await make_auth()

    claims = _decode_jwt_claims(auth.token_manager.access_token)
    client_id = claims.get("client_id", "")
    accounts = str(claims.get("accounts", "")).split(",")
    print(f"client_id (từ JWT): {client_id}")
    print(f"accounts (từ JWT): {accounts}")

    # client_id không được set khi ensure_authenticated() tạo Config ban đầu
    # (đúng thiết kế hiện tại — chỉ Data/Stream cần, xem PLAN_SSI_SDK_MIGRATION.md
    # mục 2.1.1). Set thủ công ở đây cho mục đích spike/test only.
    auth.config.client_id = client_id

    trading = AsyncTrading(auth)

    print("\nGọi get_account_info()...")
    try:
        accounts_info = await trading.account.get_account_info()
        payload = [dataclasses.asdict(a) for a in accounts_info]
        # default=str: AccountType là Enum, json.dumps không tự serialize được
        # (đã gặp thật 2026-07-25: "Object of type AccountType is not JSON serializable").
        ACCOUNT_INFO_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Nhận {len(accounts_info)} account → {ACCOUNT_INFO_OUT}")
        for a in payload:
            print(" ", a)
    except Exception as e:
        print(f"!! get_account_info() lỗi: {e}")

    # Gom kết quả tất cả account vào 1 dict thay vì ghi đè file mỗi vòng lặp
    # (bug đã gặp: BALANCE_OUT/POSITIONS_OUT bị ghi đè, chỉ còn account cuối).
    all_balances: dict[str, dict] = {}
    all_positions: dict[str, list] = {}

    for acc_no in accounts:
        acc_no = acc_no.strip()
        if not acc_no:
            continue
        print(f"\nGọi get_equity_balance({acc_no})...")
        try:
            balance = await trading.portfolio.get_equity_balance(acc_no)
            if balance is None:
                # Account không có phần "equity" (vd account derivative thuần) —
                # đây là kết quả hợp lệ, KHÔNG phải lỗi (đã gặp thật với account
                # derivative 2026-07-25, script cũ crash ở dataclasses.asdict(None)).
                print(" (account này không có dữ liệu equity — bỏ qua)")
                continue
            payload = dataclasses.asdict(balance)
            all_balances[acc_no] = payload
            print(f"OK — total_debt: {payload.get('total_debt')}")
            # available_cash/withdrawal/advance_cash_t0/advance_cash_t1 KHÔNG
            # tin được — bug xác nhận trong ssi-sdk 3.1.0 EquityAccountBalance.
            # from_dict() đọc sai tên field (availableCash/withdrawal thay vì
            # accountBalance/withdrawable thật) → luôn 0.0. Xem
            # PLAN_ACCOUNT_DATA_SYNC.md mục "Phase 0 — Kết quả thật" #3.
            print(
                " !! available_cash/withdrawal (BUG SDK, luôn 0.0, đừng tin):",
                payload.get("available_cash"),
                "/",
                payload.get("withdrawal"),
            )
        except Exception as e:
            print(f"!! get_equity_balance({acc_no}) lỗi: {e}")
            continue  # account này không hợp lệ cho equity, thử account khác

        print(f"Gọi get_equity_positions({acc_no})...")
        try:
            positions = await trading.portfolio.get_equity_positions(acc_no)
            all_positions[acc_no] = [dataclasses.asdict(p) for p in positions]
            print(f"Nhận {len(positions)} vị thế")
        except Exception as e:
            print(f"!! get_equity_positions({acc_no}) lỗi: {e}")

    BALANCE_OUT.write_text(
        json.dumps(all_balances, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    POSITIONS_OUT.write_text(
        json.dumps(all_positions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nĐã lưu balance ({len(all_balances)} account) → {BALANCE_OUT}")
    print(f"Đã lưu positions ({len(all_positions)} account) → {POSITIONS_OUT}")

    await auth.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
