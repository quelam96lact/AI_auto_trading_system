import os
from dataclasses import dataclass
from datetime import date

import yaml


@dataclass(frozen=True)
class Config:
    symbols: list[str]
    indices: list[str]
    bar_interval_minutes: int
    holidays: set[date]
    db_dsn: str
    nats_url: str
    nats_stream: str
    watchdog_stale_seconds: int
    watchdog_max_failures: int
    ssi_consumer_id: str
    ssi_consumer_secret: str


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        symbols=list(raw["symbols"]),
        indices=list(raw.get("indices", [])),
        bar_interval_minutes=int(raw.get("bar_interval_minutes", 5)),
        holidays={date.fromisoformat(str(h)) for h in raw.get("holidays", [])},
        db_dsn=os.environ["DB_DSN"],
        nats_url=raw["nats"]["url"],
        nats_stream=raw["nats"]["stream"],
        watchdog_stale_seconds=int(raw["watchdog"]["stale_seconds"]),
        watchdog_max_failures=int(raw["watchdog"]["max_failures"]),
        ssi_consumer_id=os.environ["SSI_CONSUMER_ID"],
        ssi_consumer_secret=os.environ["SSI_CONSUMER_SECRET"],
    )