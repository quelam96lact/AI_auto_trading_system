import json
import logging
import threading

import trading.alerts as alerts_mod
from trading.alerts import alert


def test_alert_emits_structured_json(caplog):
    with caplog.at_level(logging.INFO):
        alert("WARN", "feed stale", symbol="VCB")
    record = json.loads(caplog.records[0].message)
    assert record == {"level": "WARN", "msg": "feed stale", "symbol": "VCB"}


def test_info_does_not_trigger_telegram(monkeypatch):
    called = threading.Event()
    monkeypatch.setattr(alerts_mod, "send_telegram", lambda text: called.set())
    alert("INFO", "bars closed", n=1)
    assert not called.wait(timeout=0.3)


def test_warn_triggers_telegram(monkeypatch):
    received = {}
    done = threading.Event()

    def fake_send(text):
        received["text"] = text
        done.set()

    monkeypatch.setattr(alerts_mod, "send_telegram", fake_send)
    alert("WARN", "feed stale", symbol="VCB")
    assert done.wait(timeout=1.0)
    assert "feed stale" in received["text"]


def test_critical_triggers_telegram(monkeypatch):
    done = threading.Event()
    monkeypatch.setattr(alerts_mod, "send_telegram", lambda text: done.set())
    alert("CRITICAL", "feed stale beyond max failures")
    assert done.wait(timeout=1.0)


def test_alert_critical_returns_thread_and_can_join(monkeypatch):
    """Brief 59 Task 1: alert(CRITICAL) trả về Thread daemon và có thể join()."""
    started = threading.Event()
    finish = threading.Event()

    def fake_send(text):
        started.set()
        finish.wait(timeout=1.0)

    monkeypatch.setattr(alerts_mod, "send_telegram", fake_send)
    t = alert("CRITICAL", "critical alert")
    assert isinstance(t, threading.Thread)
    assert t.daemon is True
    assert started.wait(timeout=1.0)
    finish.set()
    t.join(timeout=1.0)
    assert not t.is_alive()


def test_alert_info_returns_none(monkeypatch):
    """Brief 59 Task 1: alert(INFO) không gửi telegram và trả về None."""
    called = threading.Event()
    monkeypatch.setattr(alerts_mod, "send_telegram", lambda text: called.set())
    t = alert("INFO", "info only")
    assert t is None
    assert not called.wait(timeout=0.1)


def test_alert_warn_join_finishes_promptly(monkeypatch):
    """Brief 59 Task 1: alert(WARN) trả về Thread và join kết thúc đúng hạn."""
    def fake_send(text):
        pass

    monkeypatch.setattr(alerts_mod, "send_telegram", fake_send)
    t = alert("WARN", "warning alert")
    assert isinstance(t, threading.Thread)
    t.join(timeout=1.0)
    assert not t.is_alive()

