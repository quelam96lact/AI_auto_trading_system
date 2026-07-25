"""Phase 0 spike: xác nhận OTP flow + đo TTL refresh_token của ssi-sdk mới.
Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py --refresh

Cần env SSI_API_KEY, SSI_API_SECRET (không cần client_id/private_key —
xem PLAN_SSI_SDK_MIGRATION.md mục 2.1.1: 2 giá trị đó chỉ dùng cho
Trading/Portfolio API, ngoài scope market-data hiện tại).

Lần đầu (không có --refresh): xin OTP qua SMS/email, xác thực, lưu token
vào scripts/.ssi_sdk_token.json (gitignored — KHÔNG commit file này).
Lần sau (--refresh): đọc token đã lưu, gọi refresh() — PHẢI chạy được
mà KHÔNG cần nhập OTP nếu refresh_token còn hạn. Đây là điều cần verify.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

TOKEN_FILE = Path(__file__).parent / ".ssi_sdk_token.json"


async def do_authenticate() -> None:
    from ssi_sdk import AsyncAuth, Config

    config = Config(
        api_key=os.environ["SSI_API_KEY"],
        api_secret=os.environ["SSI_API_SECRET"],
    )
    async with AsyncAuth(config) as auth:
        print("Đang xin OTP (SSI sẽ gửi qua SMS/email)...")
        await auth.request_otp()
        otp = input("Nhập OTP vừa nhận: ").strip()
        token = await auth.authenticate(otp=otp)
        _save_token(token)
        _print_token_info(token, label="AUTHENTICATE (lần đầu, có OTP)")


async def do_refresh() -> None:
    from ssi_sdk import AsyncAuth, Config

    if not TOKEN_FILE.exists():
        print(
            f"Chưa có token đã lưu ở {TOKEN_FILE} — chạy script không kèm --refresh trước."
        )
        sys.exit(1)

    saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    config = Config(
        api_key=os.environ["SSI_API_KEY"],
        api_secret=os.environ["SSI_API_SECRET"],
    )
    async with AsyncAuth(config) as auth:
        from ssi_sdk.models import Token

        # to_dict() trả key camelCase (accessToken...) → phải dùng from_dict(),
        # không phải Token(**saved) (field name snake_case sẽ không khớp).
        await auth.token_manager.set_token(Token.from_dict(saved))
        print("Đang refresh (KHÔNG dùng OTP)...")
        token = await auth.token_manager.refresh()
        _save_token(token)
        _print_token_info(token, label="REFRESH (không OTP)")


def _save_token(token) -> None:
    TOKEN_FILE.write_text(
        json.dumps(token.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _print_token_info(token, label: str) -> None:
    import time

    print(f"\n=== {label} — THÀNH CÔNG ===")
    print(f"access_token (rút gọn): {token.access_token[:20]}...")
    print(f"expires_at: {token.expires_at} (còn {token.expires_at - time.time():.0f}s)")
    print(
        f"refresh_token_expires_at: {token.refresh_token_expires_at} "
        f"(còn {(token.refresh_token_expires_at - time.time()) / 3600:.1f} giờ "
        f"= {(token.refresh_token_expires_at - time.time()) / 86400:.1f} ngày)"
    )
    print(f"Đã lưu vào {TOKEN_FILE}")


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        asyncio.run(do_refresh())
    else:
        asyncio.run(do_authenticate())
