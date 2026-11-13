"""Account balance, derivative snapshots, real positions, buying power, and NAV mixin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RealPosition:
    symbol: str
    qty: int
    avg_price: float
    sellable_qty: int


class AccountStorageMixin:
    """Mixin quan ly snapshot tai khoan co so/phai sinh, vi the that, suc mua va NAV."""

    def read_account_balance_with_debt(self, account_no: str) -> tuple[float, float, datetime] | None:
        """(withdrawable, total_debt, ts) moi nhat — MARGIN-1 tinh NAV can CA no
        (debt). Dung chung bang account_balance_snapshot; total_debt la so SSI
        tra ve, khong tu tinh."""
        with self.conn() as c:
            row = c.execute(
                "SELECT withdrawable, total_debt, ts FROM account_balance_snapshot "
                "WHERE account_no = %s ORDER BY ts DESC LIMIT 1",
                (account_no,),
            ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def read_balance_for_nav(
        self, account_no: str
    ) -> tuple[float, float, float, datetime] | None:
        """(account_balance, total_debt, buy_t0 + buy_t1, ts) moi nhat cho cong thuc NAV.

        Dot 203 (01/11/2026): doc `account_balance` thay vi `withdrawable`. Tren tai khoan margin
        (0434226), SSI dat withdrawable = 0 du tien mat thuc con ~49,5tr. Ngoai ra, account_balance
        da gom san khoan vay (khi dung margin mua co phieu, account_balance am tuong ung total_debt),
        nen _sync_nav se khong tru no nua de tranh tru hai lan.
        Tuple tra ve giu nguyen 4 phan tu de giu on dinh caller/fake tests.

        Brief 189 (docs/superpowers/plans/2026-10-23-brief-dot-189-sua-nav-cong-lenh-mua-chua-ve.md):
        Khi lenh mua khop (T0/T+1), SSI tru tien ngay nhung co phieu chua vao quantity (dang o
        buy_t0 hoac buy_t1). NAV can cong khoan pending_buy_cost = buy_t0 + buy_t1 tu CUNG DONG
        snapshot moi nhat de bu dap so tien da tru, khong bi sut giam dot ngot hon 1 ngay.
        TUYET DOI KHONG cong buy_t2 vi buy_t2 xuat hien cung luc hoac vai phut truoc khi co phieu
        vao quantity dem T+1 (se bi tinh trung).
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT account_balance, total_debt, buy_t0, buy_t1, ts FROM account_balance_snapshot "
                "WHERE account_no = %s ORDER BY ts DESC LIMIT 1",
                (account_no,),
            ).fetchone()
        return (float(row[0]), float(row[1]), float(row[2]) + float(row[3]), row[4]) if row else None

    def read_nav(self, account_no: str) -> tuple[float, datetime, list[str]] | None:
        """Tai san rong (NAV) moi nhat cua tai khoan — nguon CAPITAL cho
        RiskManager luong lenh that tu 2026-08-18 (quyet dinh chu du an 14/08,
        cap nhat Dot 203 01/11/2026: von rui ro = NAV = account_balance +
        Σ(qty × gia) + pending_buy_cost, vi account_balance da gom san khoan vay,
        khong tru total_debt hai lan, KHONG phai tien mat rut duoc). Bang rieng
        account_nav_snapshot vi NAV tinh tu positions + gia (nguon khac field SSI).
        Tra (nav, ts, unpriced_symbols) — KHONG duoc bo unpriced: main.py can no
        de WARN ma nao bi tinh 0 (NAV tinh hut la an toan nhung khong duoc im lang).
        Tra None neu chua co dong nao — main.py alert CRITICAL + capital=0 (fail-safe),
        KHONG duoc roi ve so du kha dung cho \"do gat\"."""
        with self.conn() as c:
            row = c.execute(
                "SELECT nav, ts, unpriced_symbols FROM account_nav_snapshot "
                "WHERE account_no = %s ORDER BY ts DESC LIMIT 1",
                (account_no,),
            ).fetchone()
        if row is None:
            return None
        return (row[0], row[1], list(row[2]) if row[2] else [])

    def save_account_balance(
        self,
        account_no: str,
        ts: datetime,
        account_balance: float,
        total_debt: float,
        withdrawable: float,
        buy_unmatched: float,
        sell_unmatched: float,
        buy_t0: float = 0.0,
        buy_t1: float = 0.0,
        buy_t2: float = 0.0,
        sell_t0: float = 0.0,
        sell_t1: float = 0.0,
        sell_t2: float = 0.0,
        advanced_cash_t0: float = 0.0,
        advanced_cash_t1: float = 0.0,
        dividend_cash: float = 0.0,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO account_balance_snapshot "
                "(account_no, ts, account_balance, total_debt, withdrawable, buy_unmatched, sell_unmatched, "
                "buy_t0, buy_t1, buy_t2, sell_t0, sell_t1, sell_t2, advanced_cash_t0, advanced_cash_t1, dividend_cash) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts) DO UPDATE SET "
                "account_balance = EXCLUDED.account_balance, total_debt = EXCLUDED.total_debt, "
                "withdrawable = EXCLUDED.withdrawable, buy_unmatched = EXCLUDED.buy_unmatched, "
                "sell_unmatched = EXCLUDED.sell_unmatched, "
                "buy_t0 = EXCLUDED.buy_t0, buy_t1 = EXCLUDED.buy_t1, buy_t2 = EXCLUDED.buy_t2, "
                "sell_t0 = EXCLUDED.sell_t0, sell_t1 = EXCLUDED.sell_t1, sell_t2 = EXCLUDED.sell_t2, "
                "advanced_cash_t0 = EXCLUDED.advanced_cash_t0, advanced_cash_t1 = EXCLUDED.advanced_cash_t1, "
                "dividend_cash = EXCLUDED.dividend_cash",
                (
                    account_no,
                    ts,
                    account_balance,
                    total_debt,
                    withdrawable,
                    buy_unmatched,
                    sell_unmatched,
                    buy_t0,
                    buy_t1,
                    buy_t2,
                    sell_t0,
                    sell_t1,
                    sell_t2,
                    advanced_cash_t0,
                    advanced_cash_t1,
                    dividend_cash,
                ),
            )

    def save_account_positions(
        self, account_no: str, ts: datetime, positions: list[dict]
    ) -> None:
        """positions: list of symbol/quantity/cost_price/sellable_quantity + pending quantity dicts."""
        if not positions:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO account_position_snapshot "
                "(account_no, ts, symbol, quantity, cost_price, sellable_quantity, "
                "bought_quantity, buying_quantity, sold_quantity, selling_quantity, "
                "t1_sell_quantity, t2_sell_quantity, dividend_quantity) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts, symbol) DO UPDATE SET "
                "quantity = EXCLUDED.quantity, cost_price = EXCLUDED.cost_price, "
                "sellable_quantity = EXCLUDED.sellable_quantity, "
                "bought_quantity = EXCLUDED.bought_quantity, "
                "buying_quantity = EXCLUDED.buying_quantity, "
                "sold_quantity = EXCLUDED.sold_quantity, "
                "selling_quantity = EXCLUDED.selling_quantity, "
                "t1_sell_quantity = EXCLUDED.t1_sell_quantity, "
                "t2_sell_quantity = EXCLUDED.t2_sell_quantity, "
                "dividend_quantity = EXCLUDED.dividend_quantity",
                [
                    (
                        account_no,
                        ts,
                        p["symbol"],
                        p["quantity"],
                        p["cost_price"],
                        p["sellable_quantity"],
                        p.get("bought_quantity", 0) or 0,
                        p.get("buying_quantity", 0) or 0,
                        p.get("sold_quantity", 0) or 0,
                        p.get("selling_quantity", 0) or 0,
                        p.get("t1_sell_quantity", 0) or 0,
                        p.get("t2_sell_quantity", 0) or 0,
                        p.get("dividend_quantity", 0) or 0,
                    )
                    for p in positions
                ],
            )

    def save_derivative_balance(
        self,
        account_no: str,
        ts: datetime,
        account_balance: float,
        floating_pl: float,
        trading_pl: float,
        total_pl: float,
        withdrawable: float,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO derivative_balance_snapshot "
                "(account_no, ts, account_balance, floating_pl, trading_pl, total_pl, withdrawable) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts) DO UPDATE SET "
                "account_balance = EXCLUDED.account_balance, floating_pl = EXCLUDED.floating_pl, "
                "trading_pl = EXCLUDED.trading_pl, total_pl = EXCLUDED.total_pl, "
                "withdrawable = EXCLUDED.withdrawable",
                (
                    account_no,
                    ts,
                    account_balance,
                    floating_pl,
                    trading_pl,
                    total_pl,
                    withdrawable,
                ),
            )

    def save_derivative_margin(
        self,
        account_no: str,
        ts: datetime,
        rc_call: bool,
        account_ratio_ssi: float,
        account_ratio_vsdc: float,
        used_limit_warning_level1_ssi: float,
        used_limit_warning_level2_ssi: float,
        used_limit_warning_level3_ssi: float,
        total_equity: float,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO derivative_margin_snapshot "
                "(account_no, ts, rc_call, account_ratio_ssi, account_ratio_vsdc, "
                "used_limit_warning_level1_ssi, used_limit_warning_level2_ssi, "
                "used_limit_warning_level3_ssi, total_equity) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts) DO UPDATE SET "
                "rc_call = EXCLUDED.rc_call, account_ratio_ssi = EXCLUDED.account_ratio_ssi, "
                "account_ratio_vsdc = EXCLUDED.account_ratio_vsdc, "
                "used_limit_warning_level1_ssi = EXCLUDED.used_limit_warning_level1_ssi, "
                "used_limit_warning_level2_ssi = EXCLUDED.used_limit_warning_level2_ssi, "
                "used_limit_warning_level3_ssi = EXCLUDED.used_limit_warning_level3_ssi, "
                "total_equity = EXCLUDED.total_equity",
                (
                    account_no,
                    ts,
                    rc_call,
                    account_ratio_ssi,
                    account_ratio_vsdc,
                    used_limit_warning_level1_ssi,
                    used_limit_warning_level2_ssi,
                    used_limit_warning_level3_ssi,
                    total_equity,
                ),
            )

    def save_derivative_positions(
        self, account_no: str, ts: datetime, positions: list[dict]
    ) -> None:
        """positions: list of symbol/long/short/net/floating_pl dicts."""
        if not positions:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO derivative_position_snapshot "
                "(account_no, ts, symbol, long, short, net, floating_pl) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts, symbol) DO UPDATE SET "
                "long = EXCLUDED.long, short = EXCLUDED.short, net = EXCLUDED.net, "
                "floating_pl = EXCLUDED.floating_pl",
                [
                    (
                        account_no,
                        ts,
                        p["symbol"],
                        p["long"],
                        p["short"],
                        p["net"],
                        p["floating_pl"],
                    )
                    for p in positions
                ],
            )

    def read_real_positions(
        self, account_no: str, include_unsettled: bool = False
    ) -> dict[str, RealPosition]:
        """Đọc account_position_snapshot, lấy ts mới nhất theo account_no.

        SYNC-LOG-1: neu co ban ghi account_sync_log, doc dung ts cua LAN DONG
        BO do (khong phai max(ts)) — phan biet "chua dong bo bao gio" voi "da
        dong bo va RONG" (bug: danh muc rong khong ghi dong nao -> max(ts) dung
        o lan cu, vi the da ban ve VINH VIEN — nhanh SELL sinh lenh ban co
        phieu khong ton tai). Chua co ban ghi sync (bang moi them) -> giu NGUYEN
        hanh vi cu max(ts) — khong doi ket qua dot ngot cho du lieu da co, tu
        khoi sau lan dong bo dau tien (5 phut) — quyet dinh co chu dich (plan
        SYNC-LOG-1 muc 5: lua chon giua hai kieu sai, chon cai khong doi dot
        ngot).

        KHÔNG correlate thêm theo symbol — nếu correlate cả symbol, mã đã bán hết
        sẽ không bao giờ bị ghi đè, hiện vĩnh viễn. Trả về dict[symbol, RealPosition]
        chỉ gồm các symbol có quantity > 0. `sellable_qty` (khác `qty` — tổng nắm giữ)
        là số cổ phiếu THẬT SỰ khả dụng để bán (SSI đã tự trừ phần chưa settle T+2,5) —
        dùng để cap số lượng SELL ở real_orders.handle_crossover(), KHÔNG được bỏ qua.

        `include_unsettled` (goi H, 04/09) — MAC DINH False, tuc la hanh vi cu
        y nguyen cho ca 7 cho goi con lai, TRONG DO CO DUONG DAT LENH THAT
        (real_orders.py:42,174). Chi read_must_price_symbols bat co nay len.

        Bat len = them ma dang trong CUA SO THANH TOAN T+2: `quantity = 0` (SSI
        chua ghi co) nhung `cost_price > 0` (da co gia von => da khop mua).
        Ma da ban het co `cost_price = 0` nen VAN bi loai — day la ranh gioi
        song con: neu ma da ban het lot vao day thi nhanh SELL sinh lenh ban
        co phieu KHONG TON TAI (chinh cai bay doan tren cua docstring nay).

        Do that 04/09 tren toan bo lich su bang: dung mot ma tung co
        `quantity = 0 AND cost_price > 0` — FOX, dung cua so 29/08 -> 03/09.
        Hai doi chung am cung `quantity = 0` nhung `cost_price = 0`: CAP (da
        ban) va MIRHCM261. n = 1 phia duong — day la dau hieu tot nhat hien co,
        khong phai chung minh.
        """
        qty_filter = (
            "(quantity > 0 OR (quantity = 0 AND cost_price > 0))"
            if include_unsettled
            else "quantity > 0"
        )
        sync_ts = self.read_position_sync_ts(account_no)
        if sync_ts is None:
            # Chua co ban ghi sync — hanh vi cu (max ts)
            with self.conn() as c:
                rows = c.execute(
                    "SELECT symbol, quantity, cost_price, sellable_quantity FROM account_position_snapshot "
                    "WHERE account_no = %s AND ts = (SELECT max(ts) FROM account_position_snapshot WHERE account_no = %s) "
                    f"AND {qty_filter}",
                    (account_no, account_no),
                ).fetchall()
        else:
            # Co moc sync — doc dung lan dong bo do (rong = khong co dong nao)
            with self.conn() as c:
                rows = c.execute(
                    "SELECT symbol, quantity, cost_price, sellable_quantity FROM account_position_snapshot "
                    f"WHERE account_no = %s AND ts = %s AND {qty_filter}",
                    (account_no, sync_ts),
                ).fetchall()
        return {r[0]: RealPosition(r[0], r[1], r[2], r[3]) for r in rows}

    def record_position_sync(self, account_no: str, ts: datetime) -> None:
        """Ghi su kien dong bo vi the (upsert, chi luu lan gan nhat) — goi
        LUON khi fetch thanh cong, CA KHI danh muc RONG; KHONG goi khi fetch
        nem exception (ghi mot lan dong bo chua xay ra con te hon khong ghi —
        bien "chua biet" thanh "da biet va rong")."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO account_sync_log (account_no, ts) VALUES (%s, %s) "
                "ON CONFLICT (account_no) DO UPDATE SET ts = EXCLUDED.ts",
                (account_no, ts),
            )

    def read_position_sync_ts(self, account_no: str) -> datetime | None:
        """Moc thoi gian lan dong bo vi the gan nhat (None = chua bao gio dong bo)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT ts FROM account_sync_log WHERE account_no = %s",
                (account_no,),
            ).fetchone()
        return row[0] if row else None

    def record_buying_power(
        self,
        account_no: str,
        symbol: str,
        ts: datetime,
        max_buy_qty: int,
        max_sell_qty: int,
        margin_ratio_pct: float | None,
    ) -> None:
        """Luu suc mua theo (account_no, symbol, ts) — anh chup giong cac
        bang account khac. KHONG luu purchase_power (da do: chuoi RONG).
        margin_ratio_pct None = khong parse duoc (SSI tra dang la, khong doan)."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO account_buying_power (account_no, symbol, ts, max_buy_qty, max_sell_qty, margin_ratio_pct) "
                "VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (account_no, symbol, ts) DO UPDATE SET "
                "max_buy_qty = EXCLUDED.max_buy_qty, max_sell_qty = EXCLUDED.max_sell_qty, margin_ratio_pct = EXCLUDED.margin_ratio_pct",
                (account_no, symbol, ts, max_buy_qty, max_sell_qty, margin_ratio_pct),
            )

    def read_buying_power(self, account_no: str, symbol: str) -> tuple[int, int, float | None, datetime] | None:
        """Suc mua moi nhat cua (account_no, symbol) — (max_buy_qty,
        max_sell_qty, margin_ratio_pct, ts). Kem ts de engine tinh TUOI du lieu
        (plan 2026-09-01 T1-B1: fail-safe chong dat lenh tren suc mua cu)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT max_buy_qty, max_sell_qty, margin_ratio_pct, ts FROM account_buying_power "
                "WHERE account_no = %s AND symbol = %s ORDER BY ts DESC LIMIT 1",
                (account_no, symbol),
            ).fetchone()
        return (row[0], row[1], row[2], row[3]) if row else None

    @staticmethod
    def parse_margin_ratio(value) -> float | None:
        """Chuoi margin_ratio cua SSI: '50%' -> 50.0; None/dang la -> None (khong doan).
        Khong nhan so thap phan — API tra chuoi phan tram, co the khac ngay."""
        if value is None:
            return None
        s = str(value).strip()
        if s.endswith("%"):
            s = s.removesuffix("%")
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def compute_nav(
        cash: float,
        debt: float,
        positions: dict[str, float],  # symbol -> qty (vi the DANG GIU, qty > 0)
        price_fn,
        now: datetime,
        max_price_age_days: int = 5,
        price_age_ok: Callable[[datetime, datetime], bool] | None = None,
        pending_buy_cost: float = 0.0,
    ) -> tuple[float, list[str]]:
        """NAV = tien mat + Σ(qty × gia) − no + pending_buy_cost. THUAN — test duoc khong can DB.

        pending_buy_cost (2026-10-23, Brief 189): tong gia tri cac lenh mua da khop
        (da bi tru tien) nhung co phieu chua vao quantity (buy_t0 + buy_t1). Bu dap
        khoan sut giam NAV trong thoi gian cho co phieu ve (T0 den het T+1).
        KHONG cong buy_t2 vi buy_t2 xuat hien cung luc/vai phut truoc khi co phieu
        vao quantity (se bi tinh trung).

        price_fn(symbol) -> (price, ts) | None: gia + moc thoi gian gan nhat.

        Quy tac (fail-safe): co gia va gia KHONG cu hon max_price_age_days (ngay
        giao dich) -> tinh vao NAV; khong co gia / qua cu -> TINH 0 va them vao
        danh sach "khong dinh gia duoc" (canh bao — NAV tinh hut ma khong ai biet
        thi te hon NAV khong tinh). Dung cost_price thay the la SAI: gia von co
        the cao hon thi gia rat nhieu (nhat la margin).

        price_age_ok(price_ts, now) -> bool (2026-09-03, goi A): vị từ "gia con
        tuoi" do caller tiêm vao. db.py TRUNG LAP voi thi truong — khong import
        calendar_vn, khong biet ngay le/ngay giao dich VN la gi. Caller gan voi
        SSI (account_sync.py) truyen vị từ dem NGAY GIAO DICH (trading_days_
        between); khi None -> fallback ngay LICH (hanh vi cu) cho caller khong
        co lich VN."""
        nav = cash - debt + pending_buy_cost
        unpriced = []
        for symbol, qty in positions.items():
            if qty <= 0:
                continue
            got = price_fn(symbol)
            if got is None:
                unpriced.append(symbol)  # khong co gia -> tinh 0
                continue
            price, ts = got
            if price <= 0:
                unpriced.append(symbol)  # gia <= 0 -> khong phai gia -> tinh 0
                continue
            if price_age_ok is not None:
                if not price_age_ok(ts, now):
                    unpriced.append(symbol)  # gia qua cu -> tinh 0
                    continue
            elif (now - ts).days > max_price_age_days:
                unpriced.append(symbol)  # gia qua cu (ngay lich) -> tinh 0
                continue
            nav += qty * price
        return nav, unpriced

    def record_nav(self, account_no: str, ts: datetime, nav: float, unpriced_symbols: list[str]) -> None:
        """Luu NAV theo (account_no, ts) — bang rieng (nguon tinh tu positions
        + gia, khac field SSI) de khong nham voi account_balance_snapshot."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO account_nav_snapshot (account_no, ts, nav, unpriced_symbols) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts) DO UPDATE SET nav = EXCLUDED.nav, unpriced_symbols = EXCLUDED.unpriced_symbols",
                (account_no, ts, nav, list(unpriced_symbols)),
            )

    def read_latest_account_navs(self) -> dict[str, float]:
        """Ánh xạ account_no -> nav của bản ghi mới nhất mỗi tài khoản trong account_nav_snapshot.
        Bảng rỗng trả về dict rỗng."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT ON (account_no) account_no, nav "
                "FROM account_nav_snapshot "
                "ORDER BY account_no, ts DESC"
            ).fetchall()
        return {str(row[0]): float(row[1]) for row in rows if row[1] is not None}
