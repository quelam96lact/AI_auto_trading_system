from datetime import date

from trading.config import load_config


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
        "real_order_capital: 21459\n"
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
    assert cfg.real_order_capital == 21459
    assert cfg.real_order_account == "0434221"
    assert cfg.db_dsn.startswith("postgresql://")
    assert cfg.nats_stream == "BARS"
    assert cfg.watchdog_stale_seconds == 180
