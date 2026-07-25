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
import os
import sys
from pathlib import Path

TOKEN_FILE = Path(__file__).parent / ".ssi_sdk_token.json"
ACCOUNT_INFO_OUT = Path(__file__).parent / ".spike_account_info.json"
BALANCE_OUT = Path(__file__).parent / ".spike_equity_balance.json"
POSITIONS_OUT = Path(__file__).parent / ".spike_equity_positions.json"


def decode_jwt_claims(access_token: str) -> dict:
    """Decode phần payload (giữa) của JWT — không verify signature (chỉ đọc claim)."""
    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _load_saved_token() -> dict:
    if not TOKEN_FILE.exists():
        print(
            f"Chưa có token đã lưu ở {TOKEN_FILE} — chạy scripts/spike_ssi_sdk_auth.py trước."
        )
        sys.exit(1)
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


async def _make_auth():
    """AsyncAuth với token đã lưu; refresh() nếu access_token hết hạn.
    Log DEBUG bật sẵn để xem raw response nếu lỗi (xem spike_ssi_sdk_auth.py
    cho lý do: APIError.response_body luôn None do bug ctor trong ssi-sdk 3.1.0)."""
    from ssi_sdk import AsyncAuth, Config
    from ssi_sdk.models import Token

    saved = _load_saved_token()
    config = Config(
        api_key=os.environ["SSI_API_KEY"],
        api_secret=os.environ["SSI_API_SECRET"],
        log_level="DEBUG",
    )
    auth = AsyncAuth(config)
    await auth.token_manager.set_token(Token.from_dict(saved))
    if auth.token_manager.is_token_expired:
        print("access_token hết hạn — đang refresh...")
        await auth.token_manager.refresh()
    return auth


async def main() -> None:
    from ssi_sdk import AsyncTrading

    auth = await _make_auth()

    claims = decode_jwt_claims(auth.token_manager.access_token)
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
        ACCOUNT_INFO_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Nhận {len(accounts_info)} account → {ACCOUNT_INFO_OUT}")
        for a in payload:
            print(" ", a)
    except Exception as e:
        print(f"!! get_account_info() lỗi: {e}")
        accounts_info = []

    for acc_no in accounts:
        acc_no = acc_no.strip()
        if not acc_no:
            continue
        print(f"\nGọi get_equity_balance({acc_no})...")
        try:
            balance = await trading.portfolio.get_equity_balance(acc_no)
            payload = dataclasses.asdict(balance)
            BALANCE_OUT.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"OK → {BALANCE_OUT}")
            print(" available_cash:", payload.get("available_cash"))
        except Exception as e:
            print(f"!! get_equity_balance({acc_no}) lỗi: {e}")
            continue  # account này không phải equity hoặc không hợp lệ, thử account khác

        print(f"Gọi get_equity_positions({acc_no})...")
        try:
            positions = await trading.portfolio.get_equity_positions(acc_no)
            payload = [dataclasses.asdict(p) for p in positions]
            POSITIONS_OUT.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Nhận {len(positions)} vị thế → {POSITIONS_OUT}")
        except Exception as e:
            print(f"!! get_equity_positions({acc_no}) lỗi: {e}")

    await auth.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
