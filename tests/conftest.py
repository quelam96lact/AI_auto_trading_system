"""Ha tang test RIENG (ISO-1) — suite KHONG BAO GIO cham vao DB/NATS cua he
thong that (su co 13/08: suite ghi de engine_state, xoa durable consumer
engine, purge BARS — vi chay tren dung DB va NATS san xuat). Xem
docs/superpowers/plans/2026-08-13-test-isolation.md.

Test tro vao:
- DB: trading_test (cung instance Postgres, database rieng)
- NATS: server rieng cong 4223 (service nats-test trong docker-compose.yml,
  profile "test": docker compose --profile test up -d nats-test)
"""
import os

import psycopg
import pytest

from trading.storage.db import Storage

TEST_DSN = os.environ.get(
    "TEST_DB_DSN", "postgresql://trading:trading@127.0.0.1:5432/trading_test"
)
TEST_NATS_URL = os.environ.get("TEST_NATS_URL", "nats://127.0.0.1:4223")


# HANG RAO AN TOAN — phan quan trong nhat cua ISO-1: tu choi chay neu cau hinh
# tro vao ha tang san xuat. Dung pytest.exit() (dung ca phien) chu KHONG skip —
# skip im lang la thu da che giau su co nay bay lau.
if not TEST_DSN.rsplit("/", 1)[-1].endswith("_test"):
    pytest.exit(
        f"TEST_DB_DSN tro vao DB KHONG phai *_test: {TEST_DSN!r} — test se ghi "
        f"de state san xuat, dung lai",
        returncode=1,
    )
if "4222" in TEST_NATS_URL:
    pytest.exit(
        f"TEST_NATS_URL tro vao cong 4222 (NATS san xuat): {TEST_NATS_URL!r} — "
        f"test se purge stream/xoa consumer cua he thong that, dung lai",
        returncode=1,
    )

# GIA CO CAU TRUC (ISO-3): sau khi hang rao xong, set env toan cuc — moi file
# doc os.environ.get("DB_DSN"/"NATS_URL", <mac dinh san xuat>) TU DONG an toan,
# ke ca file moi viet sau nay ma quen. Bien bai toan "nho sua tung file" (thu
# vua lam ca hai ta truot: test_storage_engine.py con sot DSN san xuat) thanh
# mot bat bien o dung mot cho. conftest duoc pytest nap TRUOC khi import test
# module, nen hang so cap module trong cac file do cung nhan gia tri moi.
os.environ["DB_DSN"] = TEST_DSN
os.environ["NATS_URL"] = TEST_NATS_URL


@pytest.fixture(scope="session", autouse=True)
def _isolated_infra(request):
    """Tao database trading_test neu chua co + init schema — chi khi session
    co it nhat 1 test integration SE CHAY (khong co thi tra ve ngay, khong ket
    noi gi: unit test phai chay duoc khong can Docker). Doc request.session.
    items (da qua deselection cua -m) chu khong dung hook collection — items
    trong modifyitems van con ca test bi deselected nen flag sai."""
    has_integration = any(
        item.get_closest_marker("integration") is not None
        for item in request.session.items
    )
    if not has_integration:
        yield  # khong co test integration -> khong dung ha tang, khong ket noi
        return
    db_name = TEST_DSN.rsplit("/", 1)[-1]
    admin_dsn = TEST_DSN.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        exists = c.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            c.execute(f'CREATE DATABASE "{db_name}"')
    Storage(TEST_DSN).init_schema()
    yield
