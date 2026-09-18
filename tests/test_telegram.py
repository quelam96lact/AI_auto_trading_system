import io
import json
import urllib.error

import trading.telegram as telegram_mod
from trading.telegram import send_telegram


def test_noop_when_env_not_set(monkeypatch, caplog):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    calls = []
    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    with caplog.at_level("WARNING"):
        res = send_telegram("hello")
    assert res is False
    assert calls == []
    assert "Khong the gui Telegram vi thieu bien moi truong" in caplog.text


def test_sends_request_when_env_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", fake_urlopen)
    res = send_telegram("feed stale")
    assert res is True
    assert captured["url"] == "https://api.telegram.org/bottok123/sendMessage"
    assert captured["body"] == {"chat_id": "999", "text": "feed stale"}
    assert captured["timeout"] == 5


def test_missing_token_logs_warning_and_returns_false(monkeypatch, caplog):
    """Thiếu TELEGRAM_BOT_TOKEN -> trả False và ghi log WARNING, không ném."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    with caplog.at_level("WARNING"):
        res = send_telegram("test msg")
    assert res is False
    assert "TELEGRAM_BOT_TOKEN" in caplog.text


def test_urlopen_raises_urlerror_returns_false(monkeypatch, caplog):
    """urlopen ném URLError -> trả False và ghi log WARNING, không ném ra ngoài."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")

    def failing_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", failing_urlopen)
    with caplog.at_level("WARNING"):
        res = send_telegram("test msg")
    assert res is False
    assert "URLError" in caplog.text


def test_telegram_response_ok_false_returns_false(monkeypatch, caplog):
    """Telegram trả ok=false -> trả False và ghi log WARNING."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")

    def fake_urlopen(*args, **kwargs):
        return io.BytesIO(b'{"ok": false, "error_code": 401, "description": "Unauthorized"}')

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", fake_urlopen)
    with caplog.at_level("WARNING"):
        res = send_telegram("test msg")
    assert res is False
    assert "Telegram API tra ve loi" in caplog.text


def test_telegram_response_ok_true_returns_true(monkeypatch):
    """Telegram trả ok=true -> trả True."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")

    def fake_urlopen(*args, **kwargs):
        return io.BytesIO(b'{"ok": true, "result": {"message_id": 42}}')

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", fake_urlopen)
    res = send_telegram("test msg")
    assert res is True
