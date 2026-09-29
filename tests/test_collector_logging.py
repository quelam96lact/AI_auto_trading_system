import logging

import pytest

from trading.collector import main as collector_main
from trading.logging_setup import silence_ssi_sdk_secrets


def test_configure_logging_mutes_websocket_headers_logger(caplog):
    """LOG-1: logger ssi_sdk.transport.websocket (dong 76 log headers chua
    `Authorization: Bearer <token>` plaintext) phai bi nang level len WARNING —
    info() khong con record nao. Kiem chung bang chinh chuoi token gia."""
    collector_main._configure_logging()

    with caplog.at_level(logging.INFO):
        logging.getLogger("ssi_sdk.transport.websocket").info(
            "Connecting to WebSocket with headers: {'Authorization': 'Bearer FAKE_TOKEN_123'}"
        )

    assert not any(
        "FAKE_TOKEN_123" in r.message for r in caplog.records
    ), "access token KHONG duoc phep lo ra log"


def test_configure_logging_keeps_token_manager_logger(caplog):
    """LOG-1: chi bitt dung 1 logger (websocket) — token_manager van o INFO
    (log 'Token refreshed successfully', huu ich va khong chua secret)."""
    collector_main._configure_logging()

    with caplog.at_level(logging.INFO):
        logging.getLogger("ssi_sdk.services.token_manager").info(
            "Token refreshed successfully"
        )

    assert any("Token refreshed successfully" in r.message for r in caplog.records), (
        "logger token_manager phai van con o INFO"
    )


def test_silence_ssi_sdk_secrets_blocks_bearer_token(caplog):
    """LOG-1 (ham dung chung): silence_ssi_sdk_secrets() trong trading.logging_setup
    phai chan INFO 'Authorization: Bearer ...' tu ssi_sdk.transport.websocket.
    Kiem chung ham moi hoat dong doc lap, khong phu thuoc vao _configure_logging."""
    # Reset ve INFO truoc de bao dam test doc lap
    ws_logger = logging.getLogger("ssi_sdk.transport.websocket")
    ws_logger.setLevel(logging.INFO)

    silence_ssi_sdk_secrets()

    with caplog.at_level(logging.INFO):
        ws_logger.info(
            "Connecting to WebSocket with headers: {'Authorization': 'Bearer TEST.JWT.TOKEN'}"
        )

    assert not any(
        "TEST.JWT.TOKEN" in r.message for r in caplog.records
    ), "silence_ssi_sdk_secrets() phai chan token khoi moi handler/stream"


def test_silence_ssi_sdk_secrets_websocket_debug_also_blocked(caplog):
    """LOG-1: websocket_client.py:278 cung log header o muc DEBUG.
    Sau khi setLevel(WARNING), ca DEBUG lan INFO deu bi chan."""
    silence_ssi_sdk_secrets()

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("ssi_sdk.transport.websocket").debug(
            "headers: {'Authorization': 'Bearer DEBUG.TOKEN'}"
        )

    assert not any(
        "DEBUG.TOKEN" in r.message for r in caplog.records
    ), "DEBUG header cung phai bi chan sau silence_ssi_sdk_secrets()"


@pytest.mark.asyncio
async def test_record_orderbook_silence_called_before_asyncstream(monkeypatch, caplog):
    """Phá thử A1 / A2 hướng đường orderbook: chạy record_orderbook_stream()
    (mock non-trading day để dừng sạch ngay đầu, không chạm mạng hay DB).
    Nếu bỏ silence_ssi_sdk_secrets() trong record_vn30f_orderbook.py (A1)
    hoặc đổi level thành INFO (A2) -> test này phải RED."""
    from scripts import record_vn30f_orderbook

    # Đặt logger về INFO trước khi test
    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.INFO)

    # Mock để dừng sạch ngay sau bước silence_ssi_sdk_secrets(), không chạm mạng/DB
    monkeypatch.setattr(record_vn30f_orderbook, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(
        record_vn30f_orderbook,
        "load_config",
        lambda *a, **k: type("DummyCfg", (), {"holidays": frozenset()})(),
    )
    monkeypatch.setattr(record_vn30f_orderbook, "is_trading_day", lambda *a, **k: False)

    await record_vn30f_orderbook.record_orderbook_stream()

    # Kiểm tra: sau khi record_orderbook_stream chạy, logger websocket phải bị chặn
    with caplog.at_level(logging.INFO):
        logging.getLogger("ssi_sdk.transport.websocket").info(
            "Connecting to WebSocket with headers: {'Authorization': 'Bearer ORDERBOOK.TOKEN'}"
        )

    assert not any(
        "ORDERBOOK.TOKEN" in r.message for r in caplog.records
    ), "record_vn30f_orderbook.py phải gọi silence_ssi_sdk_secrets() để chặn token"
