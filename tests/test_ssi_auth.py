import base64
import json
import time
from types import SimpleNamespace

import pytest
from ssi_sdk.models import Token

from trading.collector import ssi_auth

NOW = int(time.time())


class FakeTokenManager:
    def __init__(self):
        self.set_token_calls = []
        self.refresh_calls = 0
        self.authenticate_calls = []

    async def set_token(self, token):
        self.set_token_calls.append(token)

    async def refresh(self):
        self.refresh_calls += 1
        return Token(
            access_token="new-access",
            expires_at=NOW + 3600,
            refresh_token="new-refresh",
            refresh_token_expires_at=NOW + 30 * 86400,
        )

    async def authenticate(self, otp=None):
        self.authenticate_calls.append(otp)
        return Token(
            access_token="auto-access",
            expires_at=NOW + 3600,
            refresh_token="auto-refresh",
            refresh_token_expires_at=NOW + 30 * 86400,
        )


class FakeAuth:
    def __init__(self, config):
        self.config = config
        self.token_manager = FakeTokenManager()
        self.closed = False

    async def close(self):
        self.closed = True

    async def authenticate(self, otp=None):
        # AsyncAuth that gia phan giai dong qua token_manager (giong that)
        return await self.token_manager.authenticate(otp=otp)


class FakeStorage:
    def __init__(self, saved):
        self._saved = saved
        self.saved_tokens = []
        self.token_timeouts = []

    def load_ssi_token(self, timeout=None):
        # SYNC-LOG-1 Phan 2: track timeout de test xac nhan ensure_authenticated
        # truyen timeout=5
        self.token_timeouts.append(timeout)
        return self._saved

    def save_ssi_token(self, **kwargs):
        self.saved_tokens.append(kwargs)


def _cfg():
    return SimpleNamespace(ssi_api_key="key123", ssi_api_secret="secret456")


def _valid_saved():
    return {
        "access_token": "old-access",
        "expires_at": NOW - 10,  # access_token đã hết hạn → phải refresh
        "refresh_token": "old-refresh",
        "refresh_token_expires_at": NOW + 30 * 86400,  # refresh còn hạn
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_decode_client_id_from_access_token():
    payload = _b64url(json.dumps({"client_id": "043422"}).encode("utf-8"))
    token = f"{_b64url(b'{}')}.{payload}.{_b64url(b'signature')}"

    assert ssi_auth.decode_client_id(token) == "043422"


async def test_refresh_token_con_han_goi_refresh_va_luu_token_moi(monkeypatch):
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    storage = FakeStorage(_valid_saved())

    auth = await ssi_auth.ensure_authenticated(_cfg(), storage)

    assert auth.config.api_key == "key123"
    assert auth.config.api_secret == "secret456"
    # set_token nhận Token từ dữ liệu DB (refresh_token cũ)
    assert len(auth.token_manager.set_token_calls) == 1
    assert auth.token_manager.set_token_calls[0].refresh_token == "old-refresh"
    # refresh() được gọi không cần OTP, token mới được lưu lại vào DB
    assert auth.token_manager.refresh_calls == 1
    assert storage.saved_tokens == [
        {
            "access_token": "new-access",
            "expires_at": NOW + 3600,
            "refresh_token": "new-refresh",
            "refresh_token_expires_at": NOW + 30 * 86400,
        }
    ]


async def test_chua_co_token_tu_authenticate_va_luu_token(monkeypatch):
    """Chưa có token trong DB → tự authenticate() (không OTP), lưu token mới,
    KHÔNG raise RuntimeError."""
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    storage = FakeStorage(None)

    auth = await ssi_auth.ensure_authenticated(_cfg(), storage)

    assert auth.token_manager.authenticate_calls == [None]  # otp=None
    assert storage.saved_tokens == [
        {
            "access_token": "auto-access",
            "expires_at": NOW + 3600,
            "refresh_token": "auto-refresh",
            "refresh_token_expires_at": NOW + 30 * 86400,
        }
    ]


async def test_refresh_token_het_han_tu_authenticate_va_luu_token(monkeypatch):
    """refresh_token đã hết hạn trong DB → tự authenticate() (không OTP), lưu
    token mới, KHÔNG raise RuntimeError."""
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    expired = _valid_saved()
    expired["refresh_token_expires_at"] = NOW - 1  # refresh_token đã hết hạn
    storage = FakeStorage(expired)

    auth = await ssi_auth.ensure_authenticated(_cfg(), storage)

    assert auth.token_manager.authenticate_calls == [None]
    assert storage.saved_tokens == [
        {
            "access_token": "auto-access",
            "expires_at": NOW + 3600,
            "refresh_token": "auto-refresh",
            "refresh_token_expires_at": NOW + 30 * 86400,
        }
    ]


async def test_ensure_authenticated_doc_token_voi_timeout_5(monkeypatch):
    """SYNC-LOG-1 Phan 2 kiem chung 2: ensure_authenticated goi load_ssi_token
    voi timeout=5 (vong ket noi lai cua feed khong cho 30s moi lan DB chet)."""
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    storage = FakeStorage(_valid_saved())

    await ssi_auth.ensure_authenticated(_cfg(), storage)

    assert storage.token_timeouts == [
        5
    ], f"ensure_authenticated phai doc token voi timeout=5, thuc te: {storage.token_timeouts}"


async def test_authenticate_that_bai_raise_runtime_error_nhac_ca_hai_script(
    monkeypatch,
):
    """DEPGAP-1 (nhánh fallback mới): khi authenticate() tự động cũng thất bại
    (vd api_key/api_secret sai), raise RuntimeError với thông báo nhắc CẢ HAI
    script — spike_ssi_sdk_auth.py (nhập OTP) RỒI load_token_to_db.py (cầu nối
    duy nhất sang DB). Nếu ai đó sau này rút gọn còn một bước, test này phải đỏ."""

    class FailingTokenManager(FakeTokenManager):
        async def authenticate(self, otp=None):
            raise RuntimeError("SSI API tu choi authenticate")

    class FailingAuth(FakeAuth):
        def __init__(self, config):
            super().__init__(config)
            self.token_manager = FailingTokenManager()

    monkeypatch.setattr(ssi_auth, "AsyncAuth", FailingAuth)
    storage = FakeStorage(None)  # không có token -> phải tự authenticate

    with pytest.raises(RuntimeError) as ei:
        await ssi_auth.ensure_authenticated(_cfg(), storage)

    msg = str(ei.value)
    assert "spike_ssi_sdk_auth.py" in msg, f"thieu buoc 1 (spike auth), thuc te: {msg}"
    assert (
        "load_token_to_db.py" in msg
    ), f"thieu buoc 2 (load token vao DB), thuc te: {msg}"
    # Khong con loi khuyen hanh dong "re-run collector" (tu noi lai) — chuoi moi
    # chi giai thich "khong can restart" (dung), khong RA LENH restart
    assert (
        "re-run collector" not in msg
    ), f"khong duoc nha lenh re-run collector, thuc te: {msg}"
