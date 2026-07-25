"""Bootstrap auth cho ssi-sdk mới trong collector (Phase 1).

Đọc refresh_token đã lưu trong DB (bảng ssi_auth_state) → refresh() lấy
access_token mới mà KHÔNG cần OTP. Nếu chưa có token hoặc refresh_token đã
hết hạn → raise RuntimeError yêu cầu đội vận hành chạy
scripts/spike_ssi_sdk_auth.py thủ công để xác thực OTP lại rồi nạp token
vào DB. Module này KHÔNG tự xin/nhập OTP.
"""

import time

from ssi_sdk import AsyncAuth
from ssi_sdk import Config as SsiConfig
from ssi_sdk.models import Token

from trading.config import Config
from trading.storage.db import Storage


async def ensure_authenticated(cfg: Config, storage: Storage) -> AsyncAuth:
    """Trả về AsyncAuth đã có access_token hợp lệ.

    Đọc refresh_token đã lưu trong DB → nếu còn hạn, refresh() (không cần OTP).
    Nếu chưa có / refresh_token đã hết hạn → raise lỗi rõ ràng, yêu cầu đội
    vận hành chạy `scripts/spike_ssi_sdk_auth.py` thủ công để lấy OTP mới rồi
    nạp lại vào DB. KHÔNG tự động xin/nhập OTP trong hàm này.

    Caller chịu trách nhiệm đóng auth (await auth.close()) khi dùng xong.
    """
    saved = storage.load_ssi_token()
    if saved is None or saved["refresh_token_expires_at"] <= time.time():
        raise RuntimeError(
            "SSI refresh_token missing/expired — run scripts/spike_ssi_sdk_auth.py "
            "manually to re-authenticate with OTP, then re-run collector"
        )
    auth = AsyncAuth(SsiConfig(api_key=cfg.ssi_api_key, api_secret=cfg.ssi_api_secret))
    # Token.from_dict nhận key camelCase (khớp Token.to_dict() / API response)
    await auth.token_manager.set_token(
        Token.from_dict(
            {
                "accessToken": saved["access_token"],
                "expiresAt": saved["expires_at"],
                "refreshToken": saved["refresh_token"],
                "refreshExpiresAt": saved["refresh_token_expires_at"],
            }
        )
    )
    try:
        token = await auth.token_manager.refresh()
    except Exception:
        await auth.close()  # tránh rò rỉ HTTP client khi refresh thất bại
        raise
    storage.save_ssi_token(
        access_token=token.access_token,
        expires_at=token.expires_at,
        refresh_token=token.refresh_token,
        refresh_token_expires_at=token.refresh_token_expires_at,
    )
    return auth
