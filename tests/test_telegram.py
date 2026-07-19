import json

import trading.telegram as telegram_mod
from trading.telegram import send_telegram


def test_noop_when_env_not_set(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    calls = []
    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    send_telegram("hello")
    assert calls == []


def test_sends_request_when_env_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", fake_urlopen)
    send_telegram("feed stale")
    assert captured["url"] == "https://api.telegram.org/bottok123/sendMessage"
    assert captured["body"] == {"chat_id": "999", "text": "feed stale"}
    assert captured["timeout"] == 5
