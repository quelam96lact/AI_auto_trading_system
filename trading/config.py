import os
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import yaml

SSI_FC_DATA_URL = "https://fc-data.ssi.com.vn/"
SSI_FC_STREAM_URL = "https://fc-datahub.ssi.com.vn/"

# 0.28% mỗi chiều = 0.25% phí môi giới SSI + 0.03% phí trả Sở (nguồn chuẩn chung cho
# PaperBroker và ước lượng đối soát lệnh thật).
VN_EQUITY_FEE_RATE = 0.0028


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
    real_order_account: str
    ssi_derivative_account: str = ""


def normalize_loopback(url: str) -> str:
    """Chuẩn hoá hostname localhost thành 127.0.0.1.

    Windows: localhost ra IPv6 trước, mỗi kết nối DB treo ~130s.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url
        hostname = parts.hostname
        if not hostname or hostname.lower() != "localhost":
            return url
        userinfo, sep, host_port = parts.netloc.rpartition("@")
        if ":" in host_port:
            _, colon, port = host_port.partition(":")
            new_host_port = f"127.0.0.1{colon}{port}"
        else:
            new_host_port = "127.0.0.1"
        new_netloc = f"{userinfo}{sep}{new_host_port}"
        return urlunsplit(
            (parts.scheme, new_netloc, parts.path, parts.query, parts.fragment)
        )
    except ValueError:
        return url


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        symbols=list(raw["symbols"]),
        indices=list(raw.get("indices", [])),
        bar_interval_minutes=int(raw.get("bar_interval_minutes", 5)),
        ssi_equity_accounts=list(raw["ssi_equity_accounts"]),
        holidays={date.fromisoformat(str(h)) for h in raw.get("holidays", [])},
        db_dsn=normalize_loopback(os.environ["DB_DSN"]),
        nats_url=normalize_loopback(
            os.environ.get("NATS_URL") or raw["nats"]["url"]
        ),
        nats_stream=raw["nats"]["stream"],
        watchdog_stale_seconds=int(raw["watchdog"]["stale_seconds"]),
        watchdog_max_failures=int(raw["watchdog"]["max_failures"]),
        ssi_consumer_id=os.environ["SSI_CONSUMER_ID"],
        ssi_consumer_secret=os.environ["SSI_CONSUMER_SECRET"],
        ssi_api_key=os.environ["SSI_API_KEY"],
        ssi_api_secret=os.environ["SSI_API_SECRET"],
        ssi_private_key=os.environ["SSI_PRIVATE_KEY"],
        real_trading_enabled=bool(raw.get("real_trading_enabled", False)),
        real_order_account=str(raw["real_order_account"]),
        ssi_derivative_account=str(raw.get("ssi_derivative_account", "")),
    )
