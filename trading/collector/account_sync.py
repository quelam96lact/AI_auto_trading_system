from datetime import datetime

from ssi_sdk.constant import EP_ACCOUNT_BALANCE

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage


async def sync_account_data(cfg: Config, storage: Storage) -> None:
    from ssi_sdk.services.portfolio import AsyncPortfolioService

    auth = await ensure_authenticated(cfg, storage)
    try:
        client_id = decode_client_id(auth.token_manager.access_token)
        auth.config.client_id = client_id
        portfolio = AsyncPortfolioService(auth.rest_client, auth.config)
        now = datetime.now(TZ)

        for account_no in cfg.ssi_equity_accounts:
            # Cô lập từng tài khoản (SYNC-1): một tài khoản hỏng (vd parse lỗi,
            # API trả dữ liệu lạ) KHÔNG được giết các tài khoản còn lại — đo
            # thật 13/08: 0434221 nổ -> 0434226 mất im lặng cả balance lẫn
            # position. Alert WARN nêu rõ account_no nao roi continue (tang
            # kha nang quan sat, khong phai nuot loi).
            try:
                await _sync_balance(auth, client_id, account_no, now, storage)
                await _sync_positions(portfolio, account_no, now, storage)
            except Exception as e:
                alert(
                    "WARN",
                    "account sync failed, skipping",
                    account_no=account_no,
                    error=f"{type(e).__name__}: {e}",
                )
                continue
    finally:
        await auth.close()


async def _sync_balance(auth, client_id: str, account_no: str, ts: datetime, storage: Storage) -> None:
    raw = await auth.rest_client.get(
        EP_ACCOUNT_BALANCE,
        params={"clientId": client_id, "accountNo": account_no},
    )
    equity = raw.get("equity")
    if not equity:
        return
    storage.save_account_balance(
        account_no=account_no,
        ts=ts,
        account_balance=float(equity.get("accountBalance") or 0),
        total_debt=float(equity.get("totalDebt") or 0),
        withdrawable=float(equity.get("withdrawable") or 0),
        buy_unmatched=float(equity.get("buyUnmatched") or 0),
        sell_unmatched=float(equity.get("sellUnmatched") or 0),
    )


async def _sync_positions(portfolio, account_no: str, ts: datetime, storage: Storage) -> None:
    positions = await portfolio.get_equity_positions(account_no)
    # SDK docstring (portfolio.py:330-331): "absent or empty sections yield
    # None for that side" — annotation `-> list[EquityPosition]` sai voi
    # hanh vi that (portfolio.py:184 tra thang .equity). Danh muc RONG la
    # trang thai HOP LE (tai khoan 0434221 dang rong, so du 21.459 VND),
    # khong phai loi — khong alert, khong nem (SYNC-1).
    rows = [] if positions is None else [
        {
            "symbol": p.symbol,
            "quantity": p.quantity,
            "cost_price": p.cost_price,
            "sellable_quantity": p.sellable_quantity,
        }
        for p in positions
    ]
    storage.save_account_positions(account_no, ts, rows)  # no-op khi rong
    # SYNC-LOG-1: ghi su kien dong bo LUON khi fetch thanh cong (CA KHI danh
    # muc RONG) — de read_real_positions phan biet "chua dong bo" voi "da dong
    # bo va rong". Khong ghi thi max(ts) dung o lan cu, vi the da ban ve VINH
    # VIEN (nhanh SELL sinh lenh ban co phieu khong ton tai). Khong goi khi
    # fetch nem exception (exception day len sync_account_data, dong nay khong
    # chay — ghi mot lan dong bo chua xay ra con te hon khong ghi).
    storage.record_position_sync(account_no, ts)
