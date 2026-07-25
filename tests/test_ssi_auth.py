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


class FakeAuth:
    def __init__(self, config):
        self.config = config
        self.token_manager = FakeTokenManager()
        self.closed = False

    async def close(self):
        self.closed = True


class FakeStorage:
    def __init__(self, saved):
        self._saved = saved
        self.saved_tokens = []

    def load_ssi_token(self):
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


async def test_chua_co_token_raise_runtime_error(monkeypatch):
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    storage = FakeStorage(None)

    with pytest.raises(RuntimeError, match="SSI refresh_token missing/expired"):
        await ssi_auth.ensure_authenticated(_cfg(), storage)


async def test_refresh_token_het_han_raise_runtime_error(monkeypatch):
    monkeypatch.setattr(ssi_auth, "AsyncAuth", FakeAuth)
    expired = _valid_saved()
    expired["refresh_token_expires_at"] = NOW - 1  # refresh_token đã hết hạn
    storage = FakeStorage(expired)

    with pytest.raises(RuntimeError, match="SSI refresh_token missing/expired"):
        await ssi_auth.ensure_authenticated(_cfg(), storage)
