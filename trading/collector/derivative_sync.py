from datetime import datetime

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage


def margin_alert_level(
    rc_call: bool,
    account_ratio_ssi: float,
    account_ratio_vsdc: float,
    level1: float,
    level2: float,
    level3: float,
) -> str | None:
    """Map margin usage to an alert level. Field names verified real against
    the installed ssi-sdk (DerivativePPMMR), but semantics under real non-zero
    margin usage are unverified (account has never been funded/traded — see
    docs/superpowers/specs/2026-08-01-derivative-monitoring-design.md).
    Compares both ssi/vsdc ratios against the ssi warning levels (single set
    of thresholds, worse-of-two-ratios) — simplification, re-check once the
    account carries a real position."""
    if rc_call:
        return "CRITICAL"
    ratio = max(account_ratio_ssi, account_ratio_vsdc)
    if ratio >= level3:
        return "CRITICAL"
    if ratio >= level2 or ratio >= level1:
        return "WARN"
    return None


async def _sync_balance(
    portfolio, account_no: str, ts: datetime, storage: Storage
) -> None:
    balance = await portfolio.get_derivative_balance(account_no)
    storage.save_derivative_balance(
        account_no=account_no,
        ts=ts,
        account_balance=float(balance.account_balance or 0),
        floating_pl=float(balance.floating_pl or 0),
        trading_pl=float(balance.trading_pl or 0),
        total_pl=float(balance.total_pl or 0),
        withdrawable=float(balance.withdrawable or 0),
    )


REQUIRED_MARGIN_FIELDS = (
    "account_ratio_ssi",
    "account_ratio_vsdc",
    "used_limit_warning_level1_ssi",
    "used_limit_warning_level2_ssi",
    "used_limit_warning_level3_ssi",
)


def _find_missing_margin_fields(ppmmr: object) -> list[str]:
    missing = []
    for f in REQUIRED_MARGIN_FIELDS:
        val = ppmmr.get(f) if isinstance(ppmmr, dict) else getattr(ppmmr, f, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f)
    return missing


async def _sync_margin(
    portfolio, account_no: str, ts: datetime, storage: Storage
) -> None:
    ppmmr = await portfolio.get_derivative_ppmmr(account_no)
    if not ppmmr:
        return
    missing = _find_missing_margin_fields(ppmmr)
    if missing:
        alert(
            "WARN",
            f"derivative ppmmr missing required margin fields: {','.join(missing)}",
            account_no=account_no,
            missing_fields=missing,
        )
        return

    rc_call = bool(
        ppmmr.get("rc_call")
        if isinstance(ppmmr, dict)
        else getattr(ppmmr, "rc_call", False)
    )
    get_f = (
        (lambda k: ppmmr.get(k))
        if isinstance(ppmmr, dict)
        else (lambda k: getattr(ppmmr, k))
    )
    ratio_ssi = float(get_f("account_ratio_ssi"))
    ratio_vsdc = float(get_f("account_ratio_vsdc"))
    level1 = float(get_f("used_limit_warning_level1_ssi"))
    level2 = float(get_f("used_limit_warning_level2_ssi"))
    level3 = float(get_f("used_limit_warning_level3_ssi"))
    total_eq = (
        ppmmr.get("total_equity")
        if isinstance(ppmmr, dict)
        else getattr(ppmmr, "total_equity", 0)
    )

    storage.save_derivative_margin(
        account_no=account_no,
        ts=ts,
        rc_call=rc_call,
        account_ratio_ssi=ratio_ssi,
        account_ratio_vsdc=ratio_vsdc,
        used_limit_warning_level1_ssi=level1,
        used_limit_warning_level2_ssi=level2,
        used_limit_warning_level3_ssi=level3,
        total_equity=float(total_eq or 0),
    )

    level = margin_alert_level(rc_call, ratio_ssi, ratio_vsdc, level1, level2, level3)
    if level is not None:
        alert(
            level,
            "derivative margin usage elevated",
            account_no=account_no,
            rc_call=rc_call,
            account_ratio_ssi=ratio_ssi,
            account_ratio_vsdc=ratio_vsdc,
        )


async def _sync_positions(
    portfolio, account_no: str, ts: datetime, storage: Storage
) -> None:
    # SDK type hint says list[AllDerivativePosition]; Phase 0 confirmed the
    # real runtime response is a single AllDerivativePosition object.
    all_positions = await portfolio.get_derivative_positions(account_no)
    rows = [
        {
            "symbol": p.symbol,
            "long": p.long,
            "short": p.short,
            "net": p.net,
            "floating_pl": p.floating_pl,
        }
        for p in (all_positions.open_positions or [])
    ]
    storage.save_derivative_positions(account_no, ts, rows)


async def sync_derivative_data(cfg: Config, storage: Storage) -> None:
    if not cfg.ssi_derivative_account:
        return

    from ssi_sdk.services.portfolio import AsyncPortfolioService

    auth = await ensure_authenticated(cfg, storage)
    try:
        client_id = decode_client_id(auth.token_manager.access_token)
        auth.config.client_id = client_id
        portfolio = AsyncPortfolioService(auth.rest_client, auth.config)
        account_no = cfg.ssi_derivative_account
        now = datetime.now(TZ)

        await _sync_balance(portfolio, account_no, now, storage)
        await _sync_margin(portfolio, account_no, now, storage)
        await _sync_positions(portfolio, account_no, now, storage)
    finally:
        await auth.close()
