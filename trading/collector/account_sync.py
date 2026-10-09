from datetime import date, datetime, time

from ssi_sdk.constant import EP_ACCOUNT_BALANCE

from trading.alerts import alert
from trading.calendar_vn import TZ, is_trading_day, trading_days_between
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import Config
from trading.real_order_reconcile import decide_update
from trading.storage.db import Storage

# Khử trùng lặp alert CRITICAL cho lệnh thật không rõ trạng thái (đúng 1 alert / dòng / ngày)
_alerted_unmatched_fills: set[tuple[int, date]] = set()

# CONFIRM-1: trạng thái chờ xác nhận khi SSI trả rỗng đột ngột.
# Giữ trong bộ nhớ tiến trình — mất khi collector restart (an toàn: lần rỗng
# đầu tiên sau restart sẽ bị hoãn thêm 1 nhịp, tức ~5 phút). Test phải reset
# về {} trước khi chạy để đảm bảo độc lập giữa các test.
_pending_empty_positions: dict[str, bool] = {}   # account_no -> True khi đang chờ
_pending_zero_balance: dict[str, bool] = {}       # account_no -> True khi đang chờ

CONFIRM_WINDOW_START = time(9, 0)
CONFIRM_WINDOW_END = time(15, 30)


def _is_in_confirmation_window(ts: datetime, holidays: set[date] | frozenset = frozenset()) -> bool:
    """Kiểm tra ts có nằm trong cửa sổ xác nhận CONFIRM-1 (ngày giao dịch, 09:00 - 15:30 tính cả 2 đầu)."""
    ts_vn = ts.astimezone(TZ)
    if not is_trading_day(ts_vn.date(), holidays):
        return False
    t = ts_vn.time()
    return CONFIRM_WINDOW_START <= t <= CONFIRM_WINDOW_END


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
                await _sync_balance(auth, client_id, account_no, now, storage, cfg.holidays)
                await _sync_positions(portfolio, account_no, now, storage, cfg.holidays)
                # MARGIN-1 (phan 1): thu thap + tinh, CHUA noi vao duong dat lenh.
                # Suc mua theo tung ma trong cfg.symbols (trần cứng — phan 2).
                await _sync_buying_power(trading, account_no, now, cfg.symbols, storage)
                await _sync_nav(account_no, now, storage, cfg.holidays)
                # Doi soat lenh that chay SAU CUNG (audit dot 103): neu SSI loi o buoc phu
                # nay, suc mua va NAV cua tai khoan van da duoc cap nhat - khong duoc de mot
                # buoc phu lam cu so lieu ma cong go-live va duong lenh that dua vao.
                await _reconcile_real_orders(portfolio, account_no, now, storage, cfg.holidays)
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


REQUIRED_BALANCE_FIELDS = ("accountBalance", "totalDebt", "withdrawable")


def _find_missing_balance_fields(equity: dict) -> list[str]:
    missing = []
    for f in REQUIRED_BALANCE_FIELDS:
        val = equity.get(f)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f)
    return missing


async def _sync_balance(
    auth, client_id: str, account_no: str, ts: datetime, storage: Storage,
    holidays: set[date] | frozenset = frozenset(),
) -> None:
    raw = await auth.rest_client.get(
        EP_ACCOUNT_BALANCE,
        params={"clientId": client_id, "accountNo": account_no},
    )
    equity = raw.get("equity")
    if not equity:
        return
    missing = _find_missing_balance_fields(equity)
    if missing:
        alert(
            "WARN",
            f"equity missing required balance fields: {','.join(missing)}",
            account_no=account_no,
            missing_fields=missing,
        )
        return

    acct_bal = float(equity["accountBalance"])
    total_debt = float(equity["totalDebt"])
    withdrawable = float(equity["withdrawable"])

    # CONFIRM-1 (Phần B, đợt 124 & đợt 164): cả ba trường = 0 đồng thời là dấu hiệu bảo trì SSI
    # (đo được 14 lần trong lịch sử, luôn cả hai tài khoản cùng lúc, không thể thật).
    # Điều kiện bắt: CẢ BA = 0 (không phải bất kỳ một trường = 0 — b7: withdrawable=0
    # thật cho tài khoản margin, không được bắt nhầm).
    # Áp quy tắc xác nhận hai lần tương tự _sync_positions: chỉ xác nhận trong cửa sổ giao dịch.
    if acct_bal == 0.0 and total_debt == 0.0 and withdrawable == 0.0:
        prev_bal = storage.read_account_balance_with_debt(account_no)
        prev_nonzero = prev_bal is not None and (prev_bal[0] != 0.0 or prev_bal[1] != 0.0)
        if prev_nonzero:
            if not _pending_zero_balance.get(account_no):
                _pending_zero_balance[account_no] = True
                alert(
                    "WARN",
                    "CONFIRM-1: số dư cả ba trường = 0 đột ngột (SSI bảo trì?), chờ xác nhận",
                    account_no=account_no,
                )
                return  # KHÔNG ghi
            else:
                if not _is_in_confirmation_window(ts, holidays):
                    alert(
                        "INFO",
                        "CONFIRM-1: số dư cả ba trường vẫn = 0 ngoài cửa sổ giao dịch, tiếp tục chờ",
                        account_no=account_no,
                    )
                    return  # KHÔNG ghi
                _pending_zero_balance.pop(account_no, None)
                alert(
                    "WARN",
                    "CONFIRM-1: xác nhận số dư = 0 sau hai nhịp liên tiếp",
                    account_no=account_no,
                )
        else:
            _pending_zero_balance.pop(account_no, None)
    else:
        _pending_zero_balance.pop(account_no, None)

    storage.save_account_balance(
        account_no=account_no,
        ts=ts,
        account_balance=acct_bal,
        total_debt=total_debt,
        withdrawable=withdrawable,
        buy_unmatched=float(equity.get("buyUnmatched") or 0),
        sell_unmatched=float(equity.get("sellUnmatched") or 0),
    )


async def _sync_positions(
    portfolio, account_no: str, ts: datetime, storage: Storage,
    holidays: set[date] | frozenset = frozenset(),
) -> None:
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
            "bought_quantity": getattr(p, "bought_quantity", 0) or 0,
            "buying_quantity": getattr(p, "buying_quantity", 0) or 0,
            "sold_quantity": getattr(p, "sold_quantity", 0) or 0,
            "selling_quantity": getattr(p, "selling_quantity", 0) or 0,
            "t1_sell_quantity": getattr(p, "t1_sell_quantity", 0) or 0,
            "t2_sell_quantity": getattr(p, "t2_sell_quantity", 0) or 0,
            "dividend_quantity": getattr(p, "dividend_quantity", 0) or 0,
        }
        for p in positions
    ]

    # CONFIRM-1 (Phần B, đợt 124 & đợt 164): chặn "rỗng đột ngột" do bảo trì SSI.
    # Chỉ hoãn khi danh mục mới rỗng VÀ snapshot gần nhất không rỗng.
    # Tài khoản luôn rỗng (0434221): prev_positions rỗng -> ghi ngay (SYNC-1).
    # Cái giá: bán sạch thật -> ghi chậm 1 nhịp (~5 phút). Trong 5 phút,
    # nếu engine sinh lệnh SELL thì SSI từ chối (không có cổ phiếu) -> an toàn.
    # Ngược lại, rỗng giả trong phiên làm NAV âm, cổng vốn chặn BUY -> tai hại.
    # Đợt 164: Ngoài giờ giao dịch (hoặc ngày nghỉ/cuối tuần), chuyển từ "có cổ phiếu"
    # sang "rỗng" không thể là thật -> chỉ XÁC NHẬN trong cửa sổ 09:00 - 15:30 ngày giao dịch.
    if not rows:
        prev_positions = storage.read_real_positions(account_no)
        if prev_positions:
            # Snapshot trước không rỗng: kiểm tra xem đây là lần đầu hay thứ hai
            if not _pending_empty_positions.get(account_no):
                # Lần đầu: hoãn, đặt cờ, alert WARN
                _pending_empty_positions[account_no] = True
                alert(
                    "WARN",
                    "CONFIRM-1: danh mục vừa trống đột ngột (SSI trả None/rỗng), chờ xác nhận lần tiếp",
                    account_no=account_no,
                    prev_symbols=len(prev_positions),
                )
                return  # KHÔNG ghi, KHÔNG gọi record_position_sync
            else:
                if not _is_in_confirmation_window(ts, holidays):
                    alert(
                        "INFO",
                        "CONFIRM-1: danh mục vẫn rỗng ngoài cửa sổ giao dịch, tiếp tục chờ",
                        account_no=account_no,
                    )
                    return  # KHÔNG ghi, KHÔNG gọi record_position_sync
                # Lần thứ hai liên tiếp rỗng trong cửa sổ giao dịch: xác nhận thật, ghi bình thường
                _pending_empty_positions.pop(account_no, None)
                alert(
                    "WARN",
                    "CONFIRM-1: xác nhận danh mục rỗng sau hai nhịp liên tiếp",
                    account_no=account_no,
                )
        else:
            # Snapshot trước cũng rỗng (tài khoản 0434221): ghi ngay
            _pending_empty_positions.pop(account_no, None)
    else:
        _pending_empty_positions.pop(account_no, None)

    storage.save_account_positions(account_no, ts, rows)  # no-op khi rong
    # SYNC-LOG-1: ghi su kien dong bo LUON khi fetch thanh cong (CA KHI danh
    # muc RONG) — de read_real_positions phan biet "chua dong bo" voi "da dong
    # bo va rong". Khong ghi thi max(ts) dung o lan cu, vi the da ban ve VINH
    # VIEN (nhanh SELL sinh lenh ban co phieu khong ton tai). Khong goi khi
    # fetch nem exception (exception day len sync_account_data, dong nay khong
    # chay — ghi mot lan dong bo chua xay ra con te hon khong ghi).
    storage.record_position_sync(account_no, ts)


async def _reconcile_real_orders(
    portfolio,
    account_no: str,
    ts: datetime,
    storage: Storage,
    holidays: frozenset = frozenset(),
) -> None:
    """Đối soát các dòng lệnh thật có status='placed' với sổ lệnh SSI (Brief 103).

    1. Không có dòng placed nào: không gọi SSI (đa số chu kỳ).
    2. Có dòng placed: gọi get_historical_orders từ ngày của dòng cũ nhất đến hôm nay.
    3. Ghép theo ssi_order_id == order.order_id:
       - Có kết quả cập nhật: update_real_order_fill (WHERE status = 'placed').
       - Alert INFO cho lệnh khớp đủ/huỷ; alert WARN cho lệnh khớp một phần.
    4. Dòng placed có ts cách hiện tại quá 1 ngày giao dịch mà không tìm thấy trong SSI:
       - Alert CRITICAL "lệnh thật không rõ trạng thái — kiểm tra iBoard".
       - Khử trùng lặp đúng 1 lần mỗi dòng mỗi ngày qua _alerted_unmatched_fills.
    """
    placed_rows = storage.read_placed_real_fills(account_no)
    if not placed_rows:
        return

    earliest_date = min(r.ts.astimezone(TZ).date() for r in placed_rows)
    today_date = ts.astimezone(TZ).date()

    from_date = earliest_date.strftime("%Y/%m/%d")
    to_date = today_date.strftime("%Y/%m/%d")

    orders = await portfolio.get_historical_orders(account_no, from_date, to_date)
    orders_by_id = {
        str(o.order_id): o for o in (orders or []) if getattr(o, "order_id", None)
    }

    for row in placed_rows:
        order = orders_by_id.get(str(row.ssi_order_id))
        if order is not None:
            update = decide_update(row, order)
            if update is not None:
                affected = storage.update_real_order_fill(
                    id=row.id,
                    status=update.status,
                    qty=update.qty,
                    price=update.price,
                    fee=update.fee,
                    pnl=update.pnl,
                )
                if affected > 0:
                    if update.status == "filled" and update.qty < row.qty:
                        alert(
                            "WARN",
                            "lệnh thật khớp một phần",
                            account_no=account_no,
                            symbol=row.symbol,
                            order_id=row.ssi_order_id,
                            status=update.status,
                            matched_qty=update.qty,
                            orig_qty=row.qty,
                        )
                    else:
                        alert(
                            "INFO",
                            "đối soát lệnh thật cập nhật",
                            account_no=account_no,
                            symbol=row.symbol,
                            order_id=row.ssi_order_id,
                            status=update.status,
                            matched_qty=update.qty,
                            orig_qty=row.qty,
                        )
        else:
            if trading_days_between(row.ts, ts, holidays) > 1:
                today = ts.astimezone(TZ).date()
                if (row.id, today) not in _alerted_unmatched_fills:
                    _alerted_unmatched_fills.add((row.id, today))
                    alert(
                        "CRITICAL",
                        "lệnh thật không rõ trạng thái — kiểm tra iBoard",
                        account_no=account_no,
                        symbol=row.symbol,
                        order_id=row.ssi_order_id,
                        fill_id=row.id,
                        placed_ts=row.ts.isoformat(),
                    )


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
