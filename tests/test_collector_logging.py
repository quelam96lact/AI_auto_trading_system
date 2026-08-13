import logging

from trading.collector import main as collector_main


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
