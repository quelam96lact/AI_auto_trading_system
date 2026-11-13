"""Storage Facade va quan ly ConnectionPool theo DSN."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from importlib.resources import files

from psycopg_pool import ConnectionPool

from trading.storage.accounts import AccountStorageMixin, RealPosition
from trading.storage.bars import (
    _UPSERT_BAR,
    _UPSERT_STOCK_TF_BAR,
    _UPSERT_TF_BAR,
    BarStorageMixin,
)
from trading.storage.orders import (
    EFFECTIVE_FILL_STATUSES,
    EngineOrderStorageMixin,
    PlacedRealFill,
)
from trading.storage.universe import UniverseBacktestStorageMixin

__all__ = [
    "EFFECTIVE_FILL_STATUSES",
    "_POOLS",
    "_POOL_LOCK",
    "_UPSERT_BAR",
    "_UPSERT_STOCK_TF_BAR",
    "_UPSERT_TF_BAR",
    "PlacedRealFill",
    "RealPosition",
    "Storage",
    "_get_pool",
]

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


class Storage(
    BarStorageMixin,
    EngineOrderStorageMixin,
    AccountStorageMixin,
    UniverseBacktestStorageMixin,
):
    """Facade hợp nhất toàn bộ domain Storage mixins cho trading system."""

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

    def beat(self, service: str, timeout: float | None = None) -> None:
        with self.conn(timeout=timeout) as c:
            c.execute(
                "INSERT INTO heartbeat (service, last_seen) VALUES (%s, now()) "
                "ON CONFLICT (service) DO UPDATE SET last_seen = now()",
                (service,),
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
