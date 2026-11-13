"""Paper engine state, paper positions/orders, and real pending orders/fills mixin."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from trading.broker import Fill, Position
from trading.calendar_vn import TZ


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


class EngineOrderStorageMixin:
    """Mixin quan ly trang thai engine paper va so lenh / khop lenh that."""

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

    def read_last_buy_fill(self, symbol: str) -> tuple[datetime, float] | None:
        """`(ts, price)` của lệnh BUY MUỘN NHẤT trong bảng orders (brief đợt 107).

        Bỏ qua SELL: SELL không phải mốc mua, và sau khi bán hết thì không còn vị
        thế để tái dựng. Trả None nếu không có BUY nào → main.py WARN, không im lặng.
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT ts, price FROM orders WHERE symbol = %s AND side = 'BUY' "
                "ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return (row[0], row[1]) if row else None

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
