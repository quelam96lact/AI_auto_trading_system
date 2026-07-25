import os
from dataclasses import dataclass
from datetime import date

import yaml


@dataclass(frozen=True)
class Config:
    symbols: list[str]
    indices: list[str]
    bar_interval_minutes: int
    ssi_equity_accounts: list[str]
    holidays: set[date]
    db_dsn: str
    nats_url: str
    nats_stream: str
    watchdog_stale_seconds: int
    watchdog_max_failures: int
    ssi_consumer_id: str
    ssi_consumer_secret: str
    ssi_api_key: str
    ssi_api_secret: str
    ssi_private_key: str
    real_trading_enabled: bool
    real_order_capital: float
    real_order_account: str


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        symbols=list(raw["symbols"]),
        indices=list(raw.get("indices", [])),
        bar_interval_minutes=int(raw.get("bar_interval_minutes", 5)),
        ssi_equity_accounts=list(raw["ssi_equity_accounts"]),
        holidays={date.fromisoformat(str(h)) for h in raw.get("holidays", [])},
        db_dsn=os.environ["DB_DSN"],
        nats_url=os.environ.get("NATS_URL") or raw["nats"]["url"],
        nats_stream=raw["nats"]["stream"],
        watchdog_stale_seconds=int(raw["watchdog"]["stale_seconds"]),
        watchdog_max_failures=int(raw["watchdog"]["max_failures"]),
        ssi_consumer_id=os.environ["SSI_CONSUMER_ID"],
        ssi_consumer_secret=os.environ["SSI_CONSUMER_SECRET"],
        ssi_api_key=os.environ["SSI_API_KEY"],
        ssi_api_secret=os.environ["SSI_API_SECRET"],
        ssi_private_key=os.environ["SSI_PRIVATE_KEY"],
        real_trading_enabled=bool(raw.get("real_trading_enabled", False)),
        real_order_capital=float(raw["real_order_capital"]),
        real_order_account=str(raw["real_order_account"]),
    )
