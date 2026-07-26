from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files

import psycopg

from trading.broker import Fill, Position
from trading.models import Bar, IndexValue


@dataclass(frozen=True)
class RealPosition:
    symbol: str
    qty: int
    avg_price: float
    sellable_qty: int

_UPSERT_BAR = """
INSERT INTO {table} (symbol, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


class Storage:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def conn(self):
        with psycopg.connect(self.dsn) as c:
            yield c

    def init_schema(self) -> None:
        sql = files("trading.storage").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.conn() as c:
            c.execute(sql)

    def _write(self, table: str, bars: list[Bar]) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_BAR.format(table=table),
                [(b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source) for b in bars],
            )

    def write_bars(self, bars: list[Bar]) -> None:
        self._write("bars", bars)

    def write_daily(self, bars: list[Bar]) -> None:
        self._write("bars_daily", bars)

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def last_bar_ts(self, symbol: str) -> datetime | None:
        with self.conn() as c:
            row = c.execute("SELECT max(ts) FROM bars WHERE symbol = %s", (symbol,)).fetchone()
        return row[0]

    def write_index_values(self, vals: list[IndexValue]) -> None:
        if not vals:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO index_values (index_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (index_id, ts) DO UPDATE SET value = EXCLUDED.value",
                [(v.index_id, v.ts, v.value) for v in vals],
            )

    def beat(self, service: str) -> None:
        with self.conn() as c:
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
            rows = c.execute("SELECT symbol, qty, avg_price FROM positions WHERE qty > 0").fetchall()
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
            row = c.execute("SELECT cash, realized_pnl FROM engine_state WHERE id = 1").fetchone()
        return (row[0], row[1]) if row else None

    def save_real_risk_halt(self, halted_date: date) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO real_risk_state (id, halted_date, updated_at) VALUES (1, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET halted_date = EXCLUDED.halted_date, updated_at = now()",
                (halted_date,),
            )

    def read_real_risk_halt(self) -> date | None:
        with self.conn() as c:
            row = c.execute("SELECT halted_date FROM real_risk_state WHERE id = 1").fetchone()
        return row[0] if row else None

    def write_order(self, fill: Fill, mode: str = "paper") -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO orders (ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (fill.ts, fill.symbol, fill.side, fill.qty, fill.price, fill.fee, fill.pnl, mode),
            )

    def save_ssi_token(self, access_token: str, expires_at: int, refresh_token: str, refresh_token_expires_at: int) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO ssi_auth_state (id, access_token, expires_at, refresh_token, refresh_token_expires_at, updated_at) "
                "VALUES (1, %s, %s, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET access_token = EXCLUDED.access_token, "
                "expires_at = EXCLUDED.expires_at, refresh_token = EXCLUDED.refresh_token, "
                "refresh_token_expires_at = EXCLUDED.refresh_token_expires_at, updated_at = now()",
                (access_token, expires_at, refresh_token, refresh_token_expires_at),
            )

    def load_ssi_token(self) -> dict | None:
        with self.conn() as c:
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
                (account_no, ts, account_balance, total_debt, withdrawable, buy_unmatched, sell_unmatched),
            )

    def save_account_positions(self, account_no: str, ts: datetime, positions: list[dict]) -> None:
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

    def update_pnl_daily(self, day: date, realized_delta: float, fee_delta: float, unrealized: float) -> None:
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
                raise ValueError(f"pending_real_orders id={order_id} not found — status update did not apply")

    def expire_stale_pending_orders(self) -> int:
        """UPDATE status='expired' WHERE status='pending' AND expires_at < now(). Trả về số dòng bị ảnh hưởng."""
        with self.conn() as c:
            cur = c.execute(
                "UPDATE pending_real_orders SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at < now()"
            )
        return cur.rowcount

    def read_real_positions(self, account_no: str) -> dict[str, RealPosition]:
        """Đọc account_position_snapshot, lấy ts mới nhất theo account_no.

        KHÔNG correlate thêm theo symbol — nếu correlate cả symbol, mã đã bán hết
        sẽ không bao giờ bị ghi đè, hiện vĩnh viễn. Trả về dict[symbol, RealPosition]
        chỉ gồm các symbol có quantity > 0. `sellable_qty` (khác `qty` — tổng nắm giữ)
        là số cổ phiếu THẬT SỰ khả dụng để bán (SSI đã tự trừ phần chưa settle T+2,5) —
        dùng để cap số lượng SELL ở real_orders.handle_crossover(), KHÔNG được bỏ qua.
        """
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, quantity, cost_price, sellable_quantity FROM account_position_snapshot "
                "WHERE account_no = %s AND ts = (SELECT max(ts) FROM account_position_snapshot WHERE account_no = %s) "
                "AND quantity > 0",
                (account_no, account_no),
            ).fetchall()
        return {r[0]: RealPosition(r[0], r[1], r[2], r[3]) for r in rows}

    def read_real_daily_pnl(self, account_no: str, day: date) -> float:
        """SUM(pnl) từ real_order_fills cho 1 ngày theo giờ Việt Nam.

        Dùng `ts AT TIME ZONE 'Asia/Ho_Chi_Minh'` thay vì `ts::date` — cast trực tiếp
        phụ thuộc timezone của session/server Postgres (thường mặc định UTC, không cấu
        hình rõ ràng ở đâu trong dự án), có thể quy sai ngày cho các dòng gần ranh giới
        nửa đêm. `day` truyền vào luôn là ngày lịch Việt Nam (vd `bar.ts.date()` với
        `bar.ts` ở TZ Asia/Ho_Chi_Minh), nên phải quy đổi `ts` về cùng timezone trước khi so.
        Trả về 0.0 nếu không có dòng nào.
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM real_order_fills "
                "WHERE account_no = %s AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = %s",
                (account_no, day),
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
                (ts, account_no, symbol, side, qty, price, fee, pnl, ssi_order_id, status),
            )
