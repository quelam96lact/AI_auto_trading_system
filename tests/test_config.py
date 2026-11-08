from datetime import date

import pytest

from trading.config import load_config, normalize_loopback


def test_load_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SSI_CONSUMER_ID", "id123")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "sec456")
    monkeypatch.setenv("SSI_API_KEY", "key789")
    monkeypatch.setenv("SSI_API_SECRET", "secret000")
    monkeypatch.setenv("SSI_PRIVATE_KEY", "privatekey000")
    monkeypatch.setenv("DB_DSN", "postgresql://t:t@localhost:5432/trading")
    p = tmp_path / "c.yaml"
    p.write_text(
        "symbols: [VCB, HPG]\n"
        "indices: [VNINDEX]\n"
        "bar_interval_minutes: 5\n"
        "ssi_equity_accounts: ['0434221', '0434226']\n"
        "holidays: ['2026-09-02']\n"
        "real_trading_enabled: false\n"
        "real_order_account: '0434221'\n"
        "nats: {url: 'nats://localhost:4222', stream: BARS}\n"
        "watchdog: {stale_seconds: 180, max_failures: 3}\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.symbols == ["VCB", "HPG"]
    assert cfg.ssi_equity_accounts == ["0434221", "0434226"]
    assert cfg.holidays == {date(2026, 9, 2)}
    assert cfg.ssi_consumer_id == "id123"
    assert cfg.ssi_api_key == "key789"
    assert cfg.ssi_api_secret == "secret000"
    assert cfg.ssi_private_key == "privatekey000"
    assert cfg.real_trading_enabled is False
    assert cfg.real_order_account == "0434221"
    assert cfg.db_dsn.startswith("postgresql://")
    assert cfg.nats_stream == "BARS"
    assert cfg.watchdog_stale_seconds == 180


def check_real_order_account_in_equity_accounts(config_path: str = "config/config.yaml") -> None:
    cfg = load_config(config_path)
    assert cfg.real_order_account in cfg.ssi_equity_accounts, (
        f"real_order_account '{cfg.real_order_account}' phai thuoc ssi_equity_accounts {cfg.ssi_equity_accounts}"
    )


def test_real_order_account_in_ssi_equity_accounts(config_path: str = "config/config.yaml"):
    """Viec 1: kiem tra real_order_account phai nam trong ssi_equity_accounts
    (neu khong se khong co NAV dong bo -> real_capital = 0)."""
    check_real_order_account_in_equity_accounts(config_path)


@pytest.mark.parametrize(
    "raw_url,expected",
    [
        (
            "postgresql://trading:trading@localhost:5432/trading",
            "postgresql://trading:trading@127.0.0.1:5432/trading",
        ),
        (
            "postgresql://trading:trading@postgres:5432/trading",
            "postgresql://trading:trading@postgres:5432/trading",
        ),
        ("nats://localhost:4222", "nats://127.0.0.1:4222"),
        ("nats://nats:4222", "nats://nats:4222"),
        (
            "postgresql://u:localhost@db:5432/x",
            "postgresql://u:localhost@db:5432/x",
        ),
        (
            "postgresql://u:p@localhost-db:5432/x",
            "postgresql://u:p@localhost-db:5432/x",
        ),
        (
            "postgresql://u:p@LOCALHOST:5432/x",
            "postgresql://u:p@127.0.0.1:5432/x",
        ),
        (
            "postgresql://u:p@localhost/x",
            "postgresql://u:p@127.0.0.1/x",
        ),
        ("host=localhost dbname=x", "host=localhost dbname=x"),
        ("postgresql://u:p@[::1]:5432/x", "postgresql://u:p@[::1]:5432/x"),
        ("", ""),
    ],
)
def test_normalize_loopback(raw_url, expected):
    assert normalize_loopback(raw_url) == expected


def _set_dummy_ssi_env(monkeypatch):
    monkeypatch.setenv("SSI_CONSUMER_ID", "id123")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "sec456")
    monkeypatch.setenv("SSI_API_KEY", "key789")
    monkeypatch.setenv("SSI_API_SECRET", "secret000")
    monkeypatch.setenv("SSI_PRIVATE_KEY", "privatekey000")


def test_load_config_normalizes_localhost_in_env(tmp_path, monkeypatch):
    _set_dummy_ssi_env(monkeypatch)
    monkeypatch.setenv("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
    monkeypatch.setenv("NATS_URL", "nats://localhost:4222")

    p = tmp_path / "c.yaml"
    p.write_text(
        "symbols: [VCB]\n"
        "ssi_equity_accounts: ['0434221']\n"
        "real_order_account: '0434221'\n"
        "nats: {url: 'nats://nats:4222', stream: BARS}\n"
        "watchdog: {stale_seconds: 180, max_failures: 3}\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.db_dsn == "postgresql://trading:trading@127.0.0.1:5432/trading"
    assert cfg.nats_url == "nats://127.0.0.1:4222"


def test_load_config_normalizes_localhost_in_yaml_fallback(tmp_path, monkeypatch):
    _set_dummy_ssi_env(monkeypatch)
    monkeypatch.setenv("DB_DSN", "postgresql://trading:trading@postgres:5432/trading")
    monkeypatch.delenv("NATS_URL", raising=False)

    p = tmp_path / "c.yaml"
    p.write_text(
        "symbols: [VCB]\n"
        "ssi_equity_accounts: ['0434221']\n"
        "real_order_account: '0434221'\n"
        "nats: {url: 'nats://localhost:4222', stream: BARS}\n"
        "watchdog: {stale_seconds: 180, max_failures: 3}\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.db_dsn == "postgresql://trading:trading@postgres:5432/trading"
    assert cfg.nats_url == "nats://127.0.0.1:4222"
