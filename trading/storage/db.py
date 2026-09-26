import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files

from psycopg_pool import ConnectionPool

from trading.broker import Fill, Position
from trading.calendar_vn import TZ
from trading.models import Bar, IndexValue


@dataclass(frozen=True)
class RealPosition:
    symbol: str
    qty: int
    avg_price: float
    sellable_qty: int


@dataclass
class PlacedRealFill:
    id: int
    ts: datetime
    account_no: str
    symbol: str
    side: str
    qty: int
    price: float
    fee: float
    pnl: float | None
    ssi_order_id: str
    status: str


# Trạng thái fill có hiệu lực cho tính toán PnL ngày và trailing stop đỉnh mua.
# 'placed' được tính là có hiệu lực vì hiện chưa có vòng đối soát khớp lệnh thật
# với SSI (lệnh đã đặt được coi là đã có hiệu lực); khi có vòng đối soát thì cần xem lại.
EFFECTIVE_FILL_STATUSES = ("placed", "filled")


_UPSERT_BAR = """
INSERT INTO {table} (symbol, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


_POOLS: dict[str, ConnectionPool] = {}
_POOL_LOCK = threading.Lock()


def _get_pool(dsn: str) -> ConnectionPool:
    """Pool dùng chung ở CẤP MODULE, khoá theo DSN — KHÔNG một pool cho mỗi
    instance Storage (test tạo hàng chục Storage -> hết connection Postgres).
    Kích thước nhỏ: min_size=1, max_size=8. Pool tự thay connection chết
    (postgres restart giữa chừng không làm hỏng vĩnh viễn)."""
    with _POOL_LOCK:
        pool = _POOLS.get(dsn)
        if pool is None:
            # check=check_connection: validate connection TRƯỚC khi đưa ra caller,
            # connection chết (postgres restart/blip mạng) được thay TRONG pool
            # chứ không ném BAD connection ra ngoài — query đầu sau restart phải
            # thành công ngay (regression so với connection-per-query nếu không).
            pool = ConnectionPool(
                dsn,
                min_size=1,
                max_size=8,
                open=False,
                check=ConnectionPool.check_connection,
            )
            pool.open(wait=True)  # mở ngay, chờ conn đầu (báo lỗi sớm nếu DB chết)
            _POOLS[dsn] = pool
        return pool


class Storage:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def conn(self, timeout: float | None = None):
        """Connection tu pool. timeout=None (mac dinh) = hanh vi cu 30s cua
        pool; truyen timeout ngan (vd 5) cho duong can that bai NHANH (WARM-1
        Viec B: collector phai phat hien DB chet som de phuc hoi heartbeat —
        khong ha timeout toan cuc vi _get_pool la CRITICAL 59 symbol/29 luong
        gom ca duong dat lenh that)."""
        with _get_pool(self.dsn).connection(timeout=timeout) as c:
            yield c

    def init_schema(self) -> None:
        sql = (
            files("trading.storage").joinpath("schema.sql").read_text(encoding="utf-8")
        )
        with self.conn() as c:
            c.execute(sql)
            # 2026-08-18 (backfill-universe): tách "đã HỎI API tới ngày X" khỏi
            # "có dữ liệu thật tới ngày Y". attempted_until ghi ngày đã hỏi (kể
            # cả khi mã không giao dịch — mảng rỗng), last_done_date chỉ tiến
            # khi nhận được bar thật. ALTER idempotent cho bảng đã tồn tại.
            c.execute(
                "ALTER TABLE backfill_progress "
                "ADD COLUMN IF NOT EXISTS attempted_until date"
            )

    def _write(self, table: str, bars: list[Bar]) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_BAR.format(table=table),
                [
                    (b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source)
                    for b in bars
                ],
            )

    def write_bars(self, bars: list[Bar]) -> None:
        self._write("bars", bars)

    def write_daily(self, bars: list[Bar]) -> None:
        self._write("bars_daily", bars)

    def write_derivative_bars(self, bars: list[Bar]) -> None:
        self._write("bars_derivative", bars)

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def read_derivative_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_derivative "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def read_daily_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_daily "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def last_bar_ts(self, symbol: str) -> datetime | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT max(ts) FROM bars WHERE symbol = %s", (symbol,)
            ).fetchone()
        return row[0]

    def read_last_bars(self, symbol: str, n: int) -> list[Bar]:
        """n bar gan nhat cua symbol, sap xep TANG DAN theo ts (de nap tuan tu
        vao chien luoc) — dung cho WARM-UP SMA/ATR luc engine khoi dong (rui
        ro 5 GO_LIVE_AUDIT: consumer durable khong phat lai tu dau, khong nap
        lich su thi engine mu ~1h45' sau restart, im lang). Method moi — khong
        caller cu nao bi anh huong."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source "
                "FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT %s",
                (symbol, n),
            ).fetchall()
        bars = [Bar(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows]
        bars.reverse()  # DESC -> ASC theo ts
        return bars

    def write_index_values(self, vals: list[IndexValue]) -> None:
        """Ghi nhận danh sách IndexValue vào DB.

        LƯU Ý: Hàm công khai này hiện chưa có caller trong production do mảng chỉ số
        (VNINDEX/VN30) đang tạm dừng có chủ đích (xem trading/collector/feed.py:
        'KHÔNG map IndexValue cho tới khi có nguồn dữ liệu thật khác'). KHÔNG XOÁ.
        """
        if not vals:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO index_values (index_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (index_id, ts) DO UPDATE SET value = EXCLUDED.value",
                [(v.index_id, v.ts, v.value) for v in vals],
            )

    def beat(self, service: str, timeout: float | None = None) -> None:
        with self.conn(timeout=timeout) as c:
            c.execute(
                "INSERT INTO heartbeat (service, last_seen) VALUES (%s, now()) "
                "ON CONFLICT (service) DO UPDATE SET last_seen = now()",
                (service,),
            )

    def upsert_position(self, pos: Position) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO positions (symbol, qty, avg_price, updated_at) VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET qty = EXCLUDED.qty, avg_price = EXCLUDED.avg_price, "
                "updated_at = now()",
                (pos.symbol, pos.qty, pos.avg_price),
            )

    def read_positions(self) -> dict[str, Position]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, qty, avg_price FROM positions WHERE qty > 0"
            ).fetchall()
        return {r[0]: Position(r[0], r[1], r[2]) for r in rows}

    def write_engine_state(self, cash: float, realized_pnl: float) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO engine_state (id, cash, realized_pnl, updated_at) VALUES (1, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET cash = EXCLUDED.cash, "
                "realized_pnl = EXCLUDED.realized_pnl, updated_at = now()",
                (cash, realized_pnl),
            )

    def read_engine_state(self) -> tuple[float, float] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT cash, realized_pnl FROM engine_state WHERE id = 1"
            ).fetchone()
        return (row[0], row[1]) if row else None

    def read_highest_since_buy(self, symbol: str) -> float | None:
        """Dinh gia cao nhat cua vi the dang mo ke tu lan BUY fill gan nhat —
        dung de TAI DUNG TrailingStopManager._highest luc engine khoi dong lai.
        _highest la dict in-memory (trailing_stop.py:11) nen mat sau restart,
        trailing stop bi vo hieu hoa vinh vien im lang (bug RESTORE-1 Task A);
        vi the phai tai dung tu du lieu da co, khong duoc dat bang avg_price
        (under-protect khi gia da chay len roi moi restart). Tra ve None neu
        khong co BUY fill hoac khong co bar nao tu do toi nay — main.py se
        alert WARN, KHONG duoc im lang."""
        with self.conn() as c:
            row = c.execute(
                "SELECT max(high) FROM bars WHERE symbol = %s AND ts >= "
                "(SELECT max(ts) FROM orders WHERE symbol = %s AND side = 'BUY')",
                (symbol, symbol),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def read_last_buy_date(self, symbol: str) -> date | None:
        """Ngày (giờ VN) của BUY fill gần nhất trong bảng orders.

        Bảo thủ: nếu mua nhiều lần, lấy lần muộn nhất (không bao giờ bán sớm hơn luật).
        Bắt buộc dùng (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date để tránh bẫy múi giờ.
        Trả về None nếu không có lệnh BUY nào.
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
                "FROM orders WHERE symbol = %s AND side = 'BUY' "
                "ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

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

    def read_nav(self, account_no: str) -> tuple[float, datetime, list[str]] | None:
        """Tai san rong (NAV) moi nhat cua tai khoan — nguon CAPITAL cho
        RiskManager luong lenh that tu 2026-08-18 (quyet dinh chu du an 14/08:
        von rui ro = NAV = tien mat + Σ(qty × gia) − no, KHONG phai tien mat
        rut duoc). Bang rieng account_nav_snapshot vi NAV tinh tu positions +
        gia (nguon khac field SSI). Tra (nav, ts, unpriced_symbols) — KHONG
        duoc bo unpriced: main.py can no de WARN ma nao bi tinh 0 (NAV tinh
        hut la an toan nhung khong duoc im lang). Tra None neu chua co dong
        nao — main.py alert CRITICAL + capital=0 (fail-safe), KHONG duoc roi
        ve so du kha dung cho \"do gat\"."""
        with self.conn() as c:
            row = c.execute(
                "SELECT nav, ts, unpriced_symbols FROM account_nav_snapshot "
                "WHERE account_no = %s ORDER BY ts DESC LIMIT 1",
                (account_no,),
            ).fetchone()
        if row is None:
            return None
        return (row[0], row[1], list(row[2]) if row[2] else [])

    def read_last_close(self, symbol: str) -> float | None:
        """Gia dong cua gan nhat cua symbol (bars truoc, bars_daily sau) —
        dung de kiem tra tran gia tri lenh that luc khoi dong (GUARD-1): neu
        tran khong du mua noi 1 lo 100 cp thi duong dat lenh that INERT (se
        khong bao gio sinh lenh BUY) — phai alert CRITICAL, khong duoc im
        lang. Tra None neu ca hai bang rong cho symbol nay — caller bo qua
        im lang (khong the ket luan, canh bao sai se lam nhon canh bao that)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT close FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT close FROM bars_daily WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
        return row[0] if row else None

    def read_real_highest_since_buy(self, account_no: str, symbol: str) -> float | None:
        """Dinh gia cao nhat cua vi the THAT ke tu lan BUY fill gan nhat trong
        real_order_fills (loc account_no) — dung de TAI DUNG real_trailing_stop
        luc engine khoi dong lai (RTS-1), giong read_highest_since_buy() cho
        luong paper. Vi the that co the do chu tai khoan TU MUA ngoai he thong
        -> khong co fill nao -> tra None, caller phai alert WARN (khong im
        lang). Chi tinh fill da co hieu luc (placed/filled), bo cancelled."""
        with self.conn() as c:
            row = c.execute(
                "SELECT max(high) FROM bars WHERE symbol = %s AND ts >= "
                "(SELECT max(ts) FROM real_order_fills WHERE account_no = %s "
                "AND symbol = %s AND side = 'BUY' AND status = ANY(%s))",
                (symbol, account_no, symbol, list(EFFECTIVE_FILL_STATUSES)),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def has_active_pending_sell(self, account_no: str, symbol: str) -> bool:
        """Co pending SELL con hieu luc (status='pending' va chua het han) cho
        account_no + symbol khong — chan sinh lenh TRUNG (RTS-1): moi bar cham
        stop se de ra mot lenh cho moi neu khong chan."""
        with self.conn() as c:
            row = c.execute(
                "SELECT 1 FROM pending_real_orders WHERE account_no = %s "
                "AND symbol = %s AND side = 'SELL' AND status = 'pending' "
                "AND expires_at > now() LIMIT 1",
                (account_no, symbol),
            ).fetchone()
        return row is not None

    def save_real_risk_halt(self, halted_date: date) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO real_risk_state (id, halted_date, updated_at) VALUES (1, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET halted_date = EXCLUDED.halted_date, updated_at = now()",
                (halted_date,),
            )

    def read_real_risk_halt(self) -> date | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT halted_date FROM real_risk_state WHERE id = 1"
            ).fetchone()
        return row[0] if row else None

    def write_order(self, fill: Fill, mode: str = "paper") -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO orders (ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    fill.ts,
                    fill.symbol,
                    fill.side,
                    fill.qty,
                    fill.price,
                    fill.fee,
                    fill.pnl,
                    mode,
                ),
            )

    def save_ssi_token(
        self,
        access_token: str,
        expires_at: int,
        refresh_token: str,
        refresh_token_expires_at: int,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO ssi_auth_state (id, access_token, expires_at, refresh_token, refresh_token_expires_at, updated_at) "
                "VALUES (1, %s, %s, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET access_token = EXCLUDED.access_token, "
                "expires_at = EXCLUDED.expires_at, refresh_token = EXCLUDED.refresh_token, "
                "refresh_token_expires_at = EXCLUDED.refresh_token_expires_at, updated_at = now()",
                (access_token, expires_at, refresh_token, refresh_token_expires_at),
            )

    def load_ssi_token(self, timeout: float | None = None) -> dict | None:
        # SYNC-LOG-1 Phan 2: timeout tùy chọn — mặc định None giữ nguyên hành
        # vi cũ (30s pool); ensure_authenticated truyền 5 để vòng kết nối lại
        # của feed (feed.py:163) không chờ 30s mỗi lần DB chết. KHÔNG đụng
        # backoff feed.py:174 (thay đổi khác chưa đo).
        with self.conn(timeout=timeout) as c:
            row = c.execute(
                "SELECT access_token, expires_at, refresh_token, refresh_token_expires_at "
                "FROM ssi_auth_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "access_token": row[0],
            "expires_at": row[1],
            "refresh_token": row[2],
            "refresh_token_expires_at": row[3],
        }

    def save_account_balance(
        self,
        account_no: str,
        ts: datetime,
        account_balance: float,
        total_debt: float,
        withdrawable: float,
        buy_unmatched: float,
        sell_unmatched: float,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO account_balance_snapshot "
                "(account_no, ts, account_balance, total_debt, withdrawable, buy_unmatched, sell_unmatched) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts) DO UPDATE SET "
                "account_balance = EXCLUDED.account_balance, total_debt = EXCLUDED.total_debt, "
                "withdrawable = EXCLUDED.withdrawable, buy_unmatched = EXCLUDED.buy_unmatched, "
                "sell_unmatched = EXCLUDED.sell_unmatched",
                (
                    account_no,
                    ts,
                    account_balance,
                    total_debt,
                    withdrawable,
                    buy_unmatched,
                    sell_unmatched,
                ),
            )

    def save_account_positions(
        self, account_no: str, ts: datetime, positions: list[dict]
    ) -> None:
        """positions: list of symbol/quantity/cost_price/sellable_quantity dicts."""
        if not positions:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO account_position_snapshot "
                "(account_no, ts, symbol, quantity, cost_price, sellable_quantity) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (account_no, ts, symbol) DO UPDATE SET "
                "quantity = EXCLUDED.quantity, cost_price = EXCLUDED.cost_price, "
                "sellable_quantity = EXCLUDED.sellable_quantity",
                [
                    (
                        account_no,
                        ts,
                        p["symbol"],
                        p["quantity"],
                        p["cost_price"],
                        p["sellable_quantity"],
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

    def update_pnl_daily(
        self, day: date, realized_delta: float, fee_delta: float, unrealized: float
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO pnl_daily (date, realized, unrealized, fees) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (date) DO UPDATE SET "
                "realized = pnl_daily.realized + EXCLUDED.realized, "
                "fees = pnl_daily.fees + EXCLUDED.fees, "
                "unrealized = EXCLUDED.unrealized",
                (day, realized_delta, unrealized, fee_delta),
            )

    def create_pending_order(
        self,
        account_no: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        expires_at: datetime,
    ) -> int:
        """Insert 1 dòng pending, trả về id vừa tạo."""
        with self.conn() as c:
            row = c.execute(
                "INSERT INTO pending_real_orders "
                "(account_no, symbol, side, quantity, price, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (account_no, symbol, side, quantity, price, expires_at),
            ).fetchone()
        return row[0]

    def get_pending_order(self, order_id: int) -> dict | None:
        """Trả về dict các cột của 1 dòng pending_real_orders theo id, hoặc None nếu không có."""
        with self.conn() as c:
            row = c.execute(
                "SELECT id, created_at, expires_at, account_no, symbol, side, quantity, price, "
                "status, ssi_order_id, confirmed_at FROM pending_real_orders WHERE id = %s",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "expires_at": row[2],
            "account_no": row[3],
            "symbol": row[4],
            "side": row[5],
            "quantity": row[6],
            "price": row[7],
            "status": row[8],
            "ssi_order_id": row[9],
            "confirmed_at": row[10],
        }

    def update_pending_order_status(
        self,
        order_id: int,
        status: str,
        ssi_order_id: str | None = None,
    ) -> None:
        """Cập nhật status (và ssi_order_id nếu có); set confirmed_at = now() khi status != 'pending'.

        Raise ValueError nếu order_id không tồn tại — tránh silent no-op khiến caller
        tưởng đã ghi nhận trạng thái (vd "placed" cho 1 lệnh thật) trong khi DB không đổi gì.
        """
        with self.conn() as c:
            if ssi_order_id is not None:
                cur = c.execute(
                    "UPDATE pending_real_orders SET status = %s, ssi_order_id = %s, "
                    "confirmed_at = CASE WHEN status = 'pending' AND %s != 'pending' THEN now() ELSE confirmed_at END "
                    "WHERE id = %s",
                    (status, ssi_order_id, status, order_id),
                )
            else:
                cur = c.execute(
                    "UPDATE pending_real_orders SET status = %s, "
                    "confirmed_at = CASE WHEN status = 'pending' AND %s != 'pending' THEN now() ELSE confirmed_at END "
                    "WHERE id = %s",
                    (status, status, order_id),
                )
            if cur.rowcount == 0:
                raise ValueError(
                    f"pending_real_orders id={order_id} not found — status update did not apply"
                )

    def expire_stale_pending_orders(self) -> int:
        """UPDATE status='expired' WHERE status='pending' AND expires_at < now(). Trả về số dòng bị ảnh hưởng."""
        with self.conn() as c:
            cur = c.execute(
                "UPDATE pending_real_orders SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at < now()"
            )
        return cur.rowcount

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
    # ============ MARGIN-1 (phan 1): suc mua + NAV ============

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
    ) -> tuple[float, list[str]]:
        """NAV = tien mat + Σ(qty × gia) − no. THUAN — test duoc khong can DB.

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
        nav = cash - debt
        unpriced = []
        for symbol, qty in positions.items():
            if qty <= 0:
                continue
            got = price_fn(symbol)
            if got is None:
                unpriced.append(symbol)  # khong co gia -> tinh 0
                continue
            price, ts = got
            if price_age_ok is not None:
                if not price_age_ok(ts, now):
                    unpriced.append(symbol)  # gia qua cu -> tinh 0
                    continue
            elif (now - ts).days > max_price_age_days:
                unpriced.append(symbol)  # gia qua cu (ngay lich) -> tinh 0
                continue
            nav += qty * price
        return nav, unpriced

    def read_latest_bar(self, symbol: str) -> tuple[datetime, float] | None:
        """(ts, close) cua bar moi nhat — bars_daily truoc (ma dang giu nhu
        CAP/HCM/SSI/TCX chi co daily), bars 5m sau (ma cau hinh). MARGIN-1:
        dung de dinh gia vi the dang giu khi tinh NAV."""
        with self.conn() as c:
            row = c.execute(
                "SELECT ts, close FROM bars_daily WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT ts, close FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
        return (row[0], row[1]) if row else None

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


    def read_real_daily_pnl(self, account_no: str, day: date) -> float:
        """SUM(pnl) từ real_order_fills cho 1 ngày theo giờ Việt Nam.

        Dùng `ts AT TIME ZONE 'Asia/Ho_Chi_Minh'` thay vì `ts::date` — cast trực tiếp
        phụ thuộc timezone của session/server Postgres (thường mặc định UTC, không cấu
        hình rõ ràng ở đâu trong dự án), có thể quy sai ngày cho các dòng gần ranh giới
        nửa đêm. `day` truyền vào luôn là ngày lịch Việt Nam (vd `bar.ts.date()` với
        `bar.ts` ở TZ Asia/Ho_Chi_Minh), nên phải quy đổi `ts` về cùng timezone trước khi so.
        Chỉ tính fill có trạng thái trong EFFECTIVE_FILL_STATUSES (placed/filled), bỏ qua cancelled.
        Trả về 0.0 nếu không có dòng nào.
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM real_order_fills "
                "WHERE account_no = %s AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = %s "
                "AND status = ANY(%s)",
                (account_no, day, list(EFFECTIVE_FILL_STATUSES)),
            ).fetchone()
        return float(row[0])

    def write_real_order_fill(
        self,
        account_no: str,
        ts: datetime,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        fee: float,
        pnl: float | None,
        ssi_order_id: str | None,
        status: str,
    ) -> None:
        """INSERT 1 dòng vào real_order_fills."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO real_order_fills "
                "(ts, account_no, symbol, side, qty, price, fee, pnl, ssi_order_id, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    ts,
                    account_no,
                    symbol,
                    side,
                    qty,
                    price,
                    fee,
                    pnl,
                    ssi_order_id,
                    status,
                ),
            )

    def read_placed_real_fills(self, account_no: str) -> list[PlacedRealFill]:
        """Đọc các dòng real_order_fills có status='placed' và có ssi_order_id của một tài khoản."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, ts, account_no, symbol, side, qty, price, fee, pnl, ssi_order_id, status "
                "FROM real_order_fills "
                "WHERE account_no = %s AND status = 'placed' "
                "AND ssi_order_id IS NOT NULL AND ssi_order_id != '' "
                "ORDER BY id ASC",
                (account_no,),
            ).fetchall()
        return [
            PlacedRealFill(
                id=r[0],
                ts=r[1].astimezone(TZ) if r[1].tzinfo else r[1],
                account_no=r[2],
                symbol=r[3],
                side=r[4],
                qty=int(r[5]),
                price=float(r[6]),
                fee=float(r[7]),
                pnl=float(r[8]) if r[8] is not None else None,
                ssi_order_id=r[9],
                status=r[10],
            )
            for r in rows
        ]

    def update_real_order_fill(
        self,
        id: int,
        status: str,
        qty: int,
        price: float,
        fee: float,
        pnl: float | None,
    ) -> int:
        """Cập nhật một dòng real_order_fills theo id khi status vẫn là 'placed'.

        Trả về số dòng bị ảnh hưởng (c.rowcount). Nếu status không còn là 'placed', trả về 0.
        """
        with self.conn() as c:
            cur = c.execute(
                "UPDATE real_order_fills "
                "SET status = %s, qty = %s, price = %s, fee = %s, pnl = %s "
                "WHERE id = %s AND status = 'placed'",
                (status, qty, price, fee, pnl, id),
            )
            return cur.rowcount

    def upsert_symbol_universe(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO symbol_universe "
                "(symbol, exchange, avg_value_20d, avg_volume_20d, is_active, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET "
                "exchange = EXCLUDED.exchange, avg_value_20d = EXCLUDED.avg_value_20d, "
                "avg_volume_20d = EXCLUDED.avg_volume_20d, is_active = EXCLUDED.is_active, "
                "updated_at = now()",
                [
                    (
                        r["symbol"],
                        r["exchange"],
                        r.get("avg_value_20d"),
                        r.get("avg_volume_20d"),
                        r["is_active"],
                    )
                    for r in rows
                ],
            )

    def read_active_universe(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol FROM symbol_universe WHERE is_active ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]

    def read_must_price_symbols(
        self, accounts: list[str], extra: list[str]
    ) -> list[str]:
        """Brief 2026-09-01 (dot 2): tap ma BAT BUOC phai co gia hang ngay.

        = extra (vi du cfg.symbols — ma engine giao dich) HOP voi ma dang nam
        giu cua TUNG tai khoan trong accounts. Day la vai thu hai cua is_active
        cu: ma dang nam giu phai duoc nap bar DU thanh khoan thap (CAP 0,63 ty
        < nguong 1 ty van phai co gia — neu khong sau 5 phien NAV tinh chung
        bang 0, ma NAV la so nhan kich thuoc lenh that, commit 6159d39).

        BAT BUOC dung lai self.read_real_positions(account) de lay ma dang nam —
        khong viet truy van account_position_snapshot moi (bai hoc 4ea4c8d: mot
        cong thuc hai ban). Ham do da xu ly: bam moc account_sync_log (phan biet
        "chua dong bo" voi "da dong bo va rong").

        goi H (04/09): goi voi include_unsettled=True — DAY LA CHO DUY NHAT
        trong ca ma san pham lam vay. Ly do: ma vua mua co `quantity = 0` suot
        cua so thanh toan T+2, dung nhung ngay no CAN duoc nap gia nhat. FOX
        (33% danh muc) vi the bi dinh gia bang gia 28/08 suot 5 phien, va IM
        LANG vi kiem tra tuoi gia dem theo ngay giao dich nen 28/08 -> 04/09
        chi la 2 ngay <= nguong 5. "Bat buoc co gia" phai bao gom ca ma chua
        ve — no van la tien cua tai khoan.

        Tra ve danh sach sap xep, khong trung.
        """
        must: set[str] = set(extra)
        for account in accounts:
            positions = self.read_real_positions(account, include_unsettled=True)
            must.update(positions.keys())
        return sorted(must)

    def get_backfill_progress(self, symbol: str, timeframe: str) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT symbol, timeframe, last_done_date, status, error, attempted_until "
                "FROM backfill_progress WHERE symbol = %s AND timeframe = %s",
                (symbol, timeframe),
            ).fetchone()
        if row is None:
            return None
        return {
            "symbol": row[0],
            "timeframe": row[1],
            "last_done_date": row[2],
            "status": row[3],
            "error": row[4],
            "attempted_until": row[5],
        }

    def set_backfill_progress(
        self,
        symbol: str,
        timeframe: str,
        last_done_date,
        status: str,
        error: str | None = None,
        attempted_until=None,
    ) -> None:
        """Ghi trạng thái backfill. attempted_until = ngày ĐÃ HỎI API tới (kể cả
        khi mã không giao dịch — mảng rỗng); last_done_date = ngày bar THẬT cuối
        nhận được (chỉ tiến khi có dữ liệu). Tách hai khái niệm này từ
        2026-08-18 để skip dựa trên attempted_until (chống fetch lại vĩnh viễn)
        mà last_done_date vẫn trung thực (không ghi nhận độ phủ không có)."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO backfill_progress "
                "(symbol, timeframe, last_done_date, status, error, attempted_until, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol, timeframe) DO UPDATE SET "
                "last_done_date = EXCLUDED.last_done_date, status = EXCLUDED.status, "
                "error = EXCLUDED.error, attempted_until = EXCLUDED.attempted_until, "
                "updated_at = now()",
                (symbol, timeframe, last_done_date, status, error, attempted_until),
            )

    def read_daily_symbol_counts(self) -> dict[date, int]:
        """Thống kê số lượng symbol có bar theo từng ngày (quy về Asia/Ho_Chi_Minh)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d, "
                "       count(DISTINCT symbol) AS n "
                "FROM bars_daily "
                "GROUP BY 1 ORDER BY 1"
            ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def read_symbol_completeness_summaries(
        self, symbols: list[str] | None = None
    ) -> list[dict]:
        """Thống kê theo mã: first_date, last_date, total_bars, dirty_bars."""
        query = (
            "SELECT symbol, "
            "       MIN((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS first_date, "
            "       MAX((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS last_date, "
            "       COUNT(*) AS total_bars, "
            "       COUNT(*) FILTER (WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0) AS dirty_bars "
            "FROM bars_daily "
        )
        params: tuple = ()
        if symbols:
            query += "WHERE symbol = ANY(%s) "
            params = (list(symbols),)
        query += "GROUP BY symbol ORDER BY symbol"
        with self.conn() as c:
            rows = c.execute(query, params).fetchall()
        return [
            {
                "symbol": r[0],
                "first_date": r[1],
                "last_date": r[2],
                "total_bars": int(r[3]),
                "dirty_bars": int(r[4]),
            }
            for r in rows
        ]

    def read_symbol_present_dates(self, symbol: str) -> set[date]:
        """Lấy danh sách các ngày có bar của 1 mã (chỉ gọi cho các mã có lỗ hổng)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
                "FROM bars_daily WHERE symbol = %s ORDER BY 1",
                (symbol,),
            ).fetchall()
        return {r[0] for r in rows}

    def read_daily_bar_dates(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[date]]:
        """{ma: [ngay VN co bar daily]} voi start <= ngay < end. Dung cho phep loc
        ma chi-thu-Sau cua daily_data_check (dot 97). Ngay quy ve Asia/Ho_Chi_Minh:
        bars_daily luu 00:00 VN = 17:00 UTC hom truoc, ts::date se lui mot ngay."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM bars_daily "
                "WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= %s "
                "AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date < %s "
                "AND symbol = ANY(%s)",
                (start, end, list(symbols)),
            ).fetchall()
        out: dict[str, list[date]] = {}
        for sym, d in rows:
            out.setdefault(sym, []).append(d)
        return out

    def read_symbols_with_bar_on_date(
        self, day: date, symbols: list[str] | None = None
    ) -> set[str]:
        """Tập các mã có bar trong 1 ngày cụ thể (quy về Asia/Ho_Chi_Minh)."""
        query = (
            "SELECT DISTINCT symbol FROM bars_daily "
            "WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = %s "
        )
        params: list = [day]
        if symbols:
            query += "AND symbol = ANY(%s)"
            params.append(list(symbols))
        with self.conn() as c:
            rows = c.execute(query, tuple(params)).fetchall()
        return {r[0] for r in rows}

    # ============ backtest-grafana: bang backtest_runs / equity / fills ============

    def save_backtest_run(
        self,
        symbol: str,
        strategy: str,
        timeframe: str,
        frm: date,
        to_date: date,
        capital: float,
        realized_pnl: float,
        unrealized_pnl: float,
        buy_and_hold_pnl: float,
        max_drawdown: float,
        win_rate: float,
        trades: int,
        filtered_bars: dict[str, int] | None = None,
    ) -> int:
        """Ghi 1 dong backtest_runs, tra ve run_id. filtered_bars la dict
        (tong cac ma) — luu TONG so bar rac vao cot filtered_bars (int)."""
        total_filtered = sum((filtered_bars or {}).values())
        with self.conn() as c:
            row = c.execute(
                "INSERT INTO backtest_runs "
                "(symbol, strategy, timeframe, frm, to_date, capital, realized_pnl, "
                " unrealized_pnl, buy_and_hold_pnl, max_drawdown, win_rate, trades, "
                " filtered_bars) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id",
                (
                    symbol, strategy, timeframe, frm, to_date, capital,
                    realized_pnl, unrealized_pnl, buy_and_hold_pnl,
                    max_drawdown, win_rate, trades, total_filtered,
                ),
            ).fetchone()
        assert row is not None, "RETURNING run_id phai co dong"
        return int(row[0])

    def read_backtest_runs(self, limit: int = 100) -> list[dict]:
        """Doc cac lan chay backtest gan nhat (Grafana dung lam nguon bien)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT run_id, ts, symbol, strategy, timeframe, frm, to_date, "
                "       capital, realized_pnl, unrealized_pnl, buy_and_hold_pnl, "
                "       max_drawdown, win_rate, trades, filtered_bars "
                "FROM backtest_runs ORDER BY run_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": int(r[0]), "ts": r[1], "symbol": r[2], "strategy": r[3],
                "timeframe": r[4], "frm": r[5], "to_date": r[6], "capital": r[7],
                "realized_pnl": r[8], "unrealized_pnl": r[9],
                "buy_and_hold_pnl": r[10], "max_drawdown": r[11],
                "win_rate": r[12], "trades": int(r[13]) if r[13] is not None else 0,
                "filtered_bars": int(r[14]) if r[14] is not None else 0,
            }
            for r in rows
        ]

    def save_backtest_equity(
        self, run_id: int, curve: list[tuple], bh_curve: list[tuple] | None = None
    ) -> None:
        """Ghi duong von (list[(ts, equity)]) kem duong mua-va-giu THAT.

        bh_curve phai cung do dai va cung moc ts voi curve (run_backtest bao
        dam dieu do). Grafana chi DOC hai cot nay — khong tinh benchmark trong
        SQL, vi do la ban thu hai cua cong thuc _buy_and_hold."""
        if not curve:
            return
        bh = [e for _, e in bh_curve] if bh_curve else [None] * len(curve)
        if len(bh) != len(curve):
            raise ValueError(
                f"bh_curve {len(bh)} diem != equity_curve {len(curve)} diem — "
                "hai duong phai cung moc ts thi moi ve chong len nhau duoc"
            )
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO backtest_equity (run_id, ts, equity, equity_bh) "
                "VALUES (%s,%s,%s,%s)",
                [(run_id, ts, eq, b) for (ts, eq), b in zip(curve, bh)],
            )

    def read_backtest_equity(self, run_id: int) -> list[tuple]:
        """Doc duong von theo run_id, sap theo ts. Tra (ts, equity, equity_bh)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT ts, equity, equity_bh FROM backtest_equity "
                "WHERE run_id = %s ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [
            (r[0], float(r[1]), float(r[2]) if r[2] is not None else None) for r in rows
        ]

    def save_backtest_fills(self, run_id: int, fills: list[Fill]) -> None:
        """Ghi cac lenh cua 1 lan chay backtest."""
        if not fills:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO backtest_fills (run_id, ts, side, qty, price, fee) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                [(run_id, f.ts, f.side, f.qty, f.price, f.fee) for f in fills],
            )

    def read_backtest_fills(self, run_id: int) -> list[tuple]:
        """Doc cac lenh theo run_id, sap theo ts (khong co pnl — khuon plan)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT ts, side, qty, price, fee FROM backtest_fills "
                "WHERE run_id = %s ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [(r[0], r[1], int(r[2]), float(r[3]), float(r[4])) for r in rows]

