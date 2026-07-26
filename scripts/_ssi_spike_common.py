"""Helper dùng chung cho các script spike scripts/spike_ssi_sdk_*.py.

KHÔNG phải script độc lập — không có __main__, chỉ import. Gom lại sau khi
3 script (auth/ohlc/account) đều tự viết lại cùng 1 logic auth-bootstrap
gần như giống hệt nhau (rule of three — 2 bản trước đó cố tình chưa gộp
vì chưa đủ bằng chứng cần thiết, xem lịch sử; 3 bản là đủ lý do gộp).
"""

import io
import json
import os
import sys
from pathlib import Path

# Windows cmd/ps mặc định cp1252 gây UnicodeEncodeError khi print tiếng Việt.
# Force UTF-8 cho stdout/stderr nếu chưa phải UTF-8, giúp các script spike
# hiển thị được mà không crash khi gặp ký tự tiếng Việt.
if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

TOKEN_FILE = Path(__file__).parent / ".ssi_sdk_token.json"


def make_config():
    """Config với log_level=DEBUG — bắt buộc để xem raw response khi lỗi
    (APIError.response_body luôn None do bug kế thừa ctor trong ssi-sdk
    3.1.0: APIError.__init__ gọi super().__init__(message, code) không
    forward status_code/response_body, SSIError.__init__ ghi đè về None
    ngay sau đó). Đây là cách duy nhất xem được nội dung lỗi thật từ SSI."""
    from ssi_sdk import Config

    return Config(
        api_key=os.environ["SSI_API_KEY"],
        api_secret=os.environ["SSI_API_SECRET"],
        log_level="DEBUG",
    )


def load_saved_token() -> dict:
    """Đọc token đã lưu bởi spike_ssi_sdk_auth.py; thoát rõ ràng nếu chưa có."""
    if not TOKEN_FILE.exists():
        print(
            f"Chưa có token đã lưu ở {TOKEN_FILE} — "
            "chạy scripts/spike_ssi_sdk_auth.py trước để xác thực OTP."
        )
        sys.exit(1)
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


def save_token(token) -> None:
    TOKEN_FILE.write_text(
        json.dumps(token.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def make_auth():
    """AsyncAuth với token đã lưu; refresh() nếu access_token hết hạn (lưu
    lại token mới sau khi refresh — nếu refresh cũng thất bại, refresh_token
    đã hết hạn, thoát rõ ràng yêu cầu chạy lại spike_ssi_sdk_auth.py)."""
    import httpx
    from ssi_sdk import AsyncAuth
    from ssi_sdk.exceptions import SSIError
    from ssi_sdk.models import Token

    saved = load_saved_token()
    auth = AsyncAuth(make_config())
    # to_dict() trả key camelCase → phải dùng from_dict(), không phải Token(**saved)
    await auth.token_manager.set_token(Token.from_dict(saved))
    if auth.token_manager.is_token_expired:
        print("access_token hết hạn — đang refresh bằng refresh_token đã lưu...")
        try:
            token = await auth.token_manager.refresh()
        except (SSIError, httpx.HTTPError) as e:
            print(
                f"refresh() thất bại ({e}) — refresh_token có thể đã hết hạn. "
                "Chạy lại scripts/spike_ssi_sdk_auth.py để xác thực OTP mới."
            )
            sys.exit(1)
        save_token(token)
        print("refresh() OK — đã cập nhật token file.")
    return auth
