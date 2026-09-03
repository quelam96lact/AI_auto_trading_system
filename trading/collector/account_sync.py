from datetime import datetime

from ssi_sdk.constant import EP_ACCOUNT_BALANCE

from trading.alerts import alert
from trading.calendar_vn import TZ, trading_days_between
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage


async def sync_account_data(cfg: Config, storage: Storage) -> None:
    from ssi_sdk.services.portfolio import AsyncPortfolioService
    from ssi_sdk.services.trading import AsyncTradingService

    auth = await ensure_authenticated(cfg, storage)
    try:
        client_id = decode_client_id(auth.token_manager.access_token)
        auth.config.client_id = client_id
        portfolio = AsyncPortfolioService(auth.rest_client, auth.config)
        trading = AsyncTradingService(auth.rest_client)
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
                # MARGIN-1 (phan 1): thu thap + tinh, CHUA noi vao duong dat lenh.
                # Suc mua theo tung ma trong cfg.symbols (trần cứng — phan 2).
                await _sync_buying_power(trading, account_no, now, cfg.symbols, storage)
                await _sync_nav(account_no, now, storage, cfg.holidays)
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


async def _sync_buying_power(trading, account_no: str, ts: datetime, symbols: list[str], storage: Storage) -> None:
    """MARGIN-1 (phan 1): lay suc mua (max_buy/max_sell/margin_ratio) cho moi
    ma trong symbols, luu theo (account_no, symbol, ts). Mot ma loi -> WARN roi
    continue (cung khuon mau SYNC-1), khong lam hong ca vong dong bo. KHONG
    luu purchase_power (da do: chuoi RONG o ca 2 tai khoan). margin_ratio la
    chuoi '50%' -> parse thanh 50.0; dang la -> None (khong doan)."""
    for symbol in symbols:
        try:
            resp = await trading.get_max_buy_sell_at_market_price(account_no, symbol)
            storage.record_buying_power(
                account_no,
                symbol,
                ts,
                max_buy_qty=resp.max_buy_quantity,
                max_sell_qty=resp.max_sell_quantity,
                margin_ratio_pct=storage.parse_margin_ratio(resp.margin_ratio),
            )
        except Exception as e:
            alert(
                "WARN",
                "buying power sync failed, skipping symbol",
                account_no=account_no,
                symbol=symbol,
                error=f"{type(e).__name__}: {e}",
            )
            continue


async def _sync_nav(account_no: str, ts: datetime, storage: Storage,
                    holidays: frozenset) -> None:
    """MARGIN-1 (phan 1): tinh tai san rong (NAV) = tien mat + Σ(qty × gia) − no
    tu account_balance_snapshot (moi nhat) + account_position_snapshot (moi nhat)
    + gia tu bars_daily/bars. Fail-safe: ma khong dinh gia duoc (khong co gia /
    gia qua cu > 5 ngay giao dich) -> TINH 0 + WARN neu danh sach khong rong
    (NAV tinh hut ma khong ai biet thi te hon NAV khong tinh).

    2026-09-03 (goi A): (1) debt doc THAT tu snapshot (total_debt) thay vi nap
    cung 0.0 — truoc day tai khoan margin (withdrawable=0, no 68,6tr) ra NAV
    = 0.0 sai ~160tr; (2) do tuoi gia theo NGAY GIAO DICH (trading_days_between
    + holidays) thay vi ngay lich — truoc day nghi le 31/08-02/09 lam gia daily
    28/08 (chi cach 1 phien) bi loai nham, NAV = 0."""
    bal = storage.read_account_balance_with_debt(account_no)
    if bal is None:
        return  # chua co balance -> chua tinh duoc, khong bao (heartbeat da phu)
    withdrawable, total_debt = bal[0], bal[1]

    # positions moi nhat (account_position_snapshot) — dung read_real_positions
    # (da xu ly moc sync) de lay danh sach vi the dang giu
    pos = storage.read_real_positions(account_no)

    def price_fn(symbol: str):
        row = storage.read_latest_bar(symbol)
        if row is None:
            return None
        return (row[1], row[0])  # (price, ts)

    # db.py trung lap voi thi truong: vị từ "gia con tuoi" tinh o day (ben gan
    # SSI/VN), dem NGAY GIAO DICH khong phai ngay lich (4ea4c8d — cung cong
    # thuc voi chuong 2A, xem calendar_vn.market_minutes_between).
    def price_age_ok(price_ts: datetime, now: datetime) -> bool:
        return trading_days_between(price_ts, now, holidays) <= 5

    nav, unpriced = storage.compute_nav(
        withdrawable, total_debt, {s: p.qty for s, p in pos.items()},
        price_fn, ts, price_age_ok=price_age_ok,
    )
    storage.record_nav(account_no, ts, nav, unpriced)
    if unpriced:
        alert(
            "WARN",
            "NAV tinh thieu: mot so ma khong dinh gia duoc (tinh 0)",
            account_no=account_no,
            symbols=",".join(unpriced),
            nav=nav,
        )
