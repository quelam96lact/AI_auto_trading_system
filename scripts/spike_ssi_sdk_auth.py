"""Phase 0 spike: xác nhận OTP flow + đo TTL refresh_token của ssi-sdk mới.

⚠️ LƯU Ý VẬN HÀNH (Brief 17): Script này KHÔNG PHẢI spike vứt đi.
Đây là công cụ khôi phục OTP của vận hành khi token hết hạn hoặc hỏng.
Được gọi / tham chiếu từ: trading/collector/ssi_auth.py, scripts/heartbeat_check.py,
scripts/load_token_to_db.py, tests/test_ssi_auth.py, và RUNBOOK_OTP_AUTH.txt.
TUYỆT ĐỐI KHÔNG XOÁ.

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py --no-otp
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py --request-otp
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py --otp 123456
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py --refresh

Cần env SSI_API_KEY, SSI_API_SECRET (không cần client_id/private_key —
xem PLAN_SSI_SDK_MIGRATION.md mục 2.1.1: 2 giá trị đó chỉ dùng cho
Trading/Portfolio API, ngoài scope market-data hiện tại).

Mặc định (không cờ): xin OTP, hỏi nhập trực tiếp trong terminal (interactive).
--no-otp: xác thực THẲNG không xin/nhập OTP — theo client.py docstring
  (Data client "pass Auth, no OTP needed"), test xem apiKey/apiSecret có
  hợp lệ cho scope market-data cơ bản không, tách biệt khỏi vấn đề OTP.
--request-otp: chỉ xin OTP rồi thoát (không chờ nhập) — dùng khi muốn tách
  bước xin OTP và bước xác thực (vd người khác tra OTP hộ qua email).
--otp CODE: xác thực thẳng bằng mã đã có sẵn, không hỏi lại, không tự xin
  OTP mới (dùng sau khi đã chạy --request-otp và có mã trong tay).
--refresh: đọc token đã lưu, gọi refresh() — PHẢI chạy được mà KHÔNG cần
  OTP nếu refresh_token còn hạn. Đây là điều cần verify.

Token lưu vào scripts/.ssi_sdk_token.json (gitignored — KHÔNG commit).
"""

import asyncio
import json
import sys

from _ssi_spike_common import TOKEN_FILE, make_config
from _ssi_spike_common import save_token as _save_token


async def do_request_otp() -> None:
    from ssi_sdk import AsyncAuth

    async with AsyncAuth(make_config()) as auth:
        print("Đang xin OTP (SSI sẽ gửi qua SMS/email)...")
        try:
            await auth.request_otp()
        except Exception as e:
            _print_api_error(e)
            raise
        print("Đã gửi yêu cầu OTP. Chạy lại với --otp CODE khi có mã.")


def _print_api_error(e: Exception) -> None:
    """SSIError.message mặc định không in kèm response_body — in rõ ra để debug."""
    status = getattr(e, "status_code", None)
    body = getattr(e, "response_body", None)
    print(f"\n!!! Loi tu SSI API (status={status}): {body}\n")


async def do_authenticate(otp: str | None = None, ask_if_missing: bool = True) -> None:
    from ssi_sdk import AsyncAuth

    async with AsyncAuth(make_config()) as auth:
        if otp is None and ask_if_missing:
            print("Đang xin OTP (SSI sẽ gửi qua SMS/email)...")
            await auth.request_otp()
            otp = input("Nhập OTP vừa nhận: ").strip()
        try:
            # otp=None hop le (theo client.py docstring: Data client "pass Auth,
            # no OTP needed" — TokenRequest.to_dict() bo qua field "otp" khi None).
            token = await auth.authenticate(otp=otp)
        except Exception as e:
            _print_api_error(e)
            raise
        _save_token(token)
        label = (
            "AUTHENTICATE co OTP" if otp else "AUTHENTICATE KHONG OTP (Data-only scope)"
        )
        _print_token_info(token, label=label)


async def do_refresh() -> None:
    from ssi_sdk import AsyncAuth

    if not TOKEN_FILE.exists():
        print(
            f"Chưa có token đã lưu ở {TOKEN_FILE} — chạy script không kèm --refresh trước."
        )
        sys.exit(1)

    saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    async with AsyncAuth(make_config()) as auth:
        from ssi_sdk.models import Token

        # to_dict() trả key camelCase (accessToken...) → phải dùng from_dict(),
        # không phải Token(**saved) (field name snake_case sẽ không khớp).
        await auth.token_manager.set_token(Token.from_dict(saved))
        print("Đang refresh (KHÔNG dùng OTP)...")
        try:
            token = await auth.token_manager.refresh()
        except Exception as e:
            _print_api_error(e)
            raise
        _save_token(token)
        _print_token_info(token, label="REFRESH (không OTP)")


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
    elif "--request-otp" in sys.argv:
        asyncio.run(do_request_otp())
    elif "--otp" in sys.argv:
        asyncio.run(do_authenticate(otp=sys.argv[sys.argv.index("--otp") + 1]))
    elif "--no-otp" in sys.argv:
        asyncio.run(do_authenticate(otp=None, ask_if_missing=False))
    else:
        asyncio.run(do_authenticate())
