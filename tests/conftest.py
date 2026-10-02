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
import sys

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

# ISO-4 (2026-09-09): Telegram la "he thong that" thu ba ma suite cham vao
# (qua trading/alerts.py -> trading/telegram.py) nhung chua co rao nhu DB/NATS
# o tren. Neu may chay test co san TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID that
# trong moi truong (session shell cu, .env bi nap...), cac test integration
# goi thang trading.engine.main.run() (khong monkeypatch alert) se bắn
# CRITICAL Telegram THAT voi du lieu TEST: account="" + symbol="ENGT" (mac
# dinh make_cfg() o test_engine_main.py).
#
# HARD-SET (khong phai pop!) — dung y het khuon DB_DSN/NATS_URL o tren, KHONG
# duoc xoa: scripts/_db_common.py::load_dotenv() dung os.environ.setdefault()
# de nap .env that (goi qua resolve_dsn() trong scripts/daily_data_check.py,
# duoc mot so test o test_data_quality.py thuc thi that qua main()). Neu key
# bi XOA (pop) thi setdefault() coi la "chua co" va NAP LAI token that tu
# .env, vo hieu hoa hang rao nay giua chung suite (tu bat duoc bang
# tests/test_telegram_isolation.py khi chay CA suite, khong bat duoc khi
# chay rieng file do). Set chuoi rong: key VAN "co mat" nen setdefault() bo
# qua, va trading/telegram.py::send_telegram() coi rong la "chua cau hinh"
# nen tu no-op.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

# ISO-5 (2026-09-09 Brief dot 23): Hang rao SSI credentials.
# Cung ly do voi ISO-4: load_dotenv() trong scripts/_db_common.py dung setdefault()
# se nap lai secret that tu .env neu key bi pop. Hard-set chuoi rong de giu key ton tai,
# chan vo tinh goi SSI API that trong cac test hien tai va tuong lai.
os.environ["SSI_CONSUMER_ID"] = ""
os.environ["SSI_CONSUMER_SECRET"] = ""
os.environ["SSI_API_KEY"] = ""
os.environ["SSI_API_SECRET"] = ""
os.environ["SSI_PRIVATE_KEY"] = ""


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


# ISO-6 (2026-10-02 Brief dot 145): LUOI AN TOAN cho file trang thai THAT trong logs/.
# Su co: test_heartbeat_check goi main([]) nen moi lan chay pytest ghi de
# logs/.schedule_health_state.json that bang du kien gia ("stale", 2026-08-14);
# heartbeat that sau do gui 5 tin "DA CHAY LAI" oan, va neu mot job THAT chet thi
# thay trang thai truoc la stale, coi nhu "da bao", IM LANG.
#
# Cach chon: audit hook (sys.addaudithook) bat moi lan MO-DE-GHI / XOA / DOI TEN mot
# file `logs/.*state*` hoac `logs/.*last*` thuc ngay TRONG TIEN TRINH pytest nay, va
# ghi lai ten test dang chay. Khong so sanh "truoc/sau" tren dia: cron ghi
# .container_health_state.json THAT moi 10 phut (tien trinh khac) nen so sanh
# truoc/sau se do oan; audit hook chi thay viec CUA pytest. Gioi han (da noi o bao
# cao): tien trinh con (subprocess) khong bi bat.
_REPO_LOGS = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "logs")
)
_STATE_WRITES: list[tuple[str, str, str]] = []  # (ten test, su kien, ten file)


def _real_state_file_name(path) -> str | None:
    try:
        real = os.path.realpath(os.fsdecode(path))
        folder, name = os.path.split(real)
        if os.path.normcase(folder) != os.path.normcase(_REPO_LOGS):
            return None
        if name.startswith(".") and ("state" in name or "last" in name):
            return name
    except Exception:  # hook KHONG duoc nem: nem o day se pha open() cua nguoi khac
        pass
    return None


def _audit_real_state_files(event, args):
    try:
        if event == "open":
            path, mode, flags = args
            write_flags = (
                os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
            )
            if isinstance(flags, int):
                writing = bool(flags & write_flags)
            else:
                writing = any(c in str(mode) for c in "wax+")
            paths = [path] if writing else []
        elif event == "os.remove":
            paths = [args[0]]
        elif event == "os.rename":
            paths = [args[0], args[1]]
        else:
            return
        for p in paths:
            name = _real_state_file_name(p)
            if name:
                _STATE_WRITES.append(
                    (os.environ.get("PYTEST_CURRENT_TEST", "<ngoai test>"), event, name)
                )
    except Exception:
        pass


sys.addaudithook(_audit_real_state_files)


@pytest.fixture(scope="session", autouse=True)
def _khong_ghi_file_trang_thai_that():
    _STATE_WRITES.clear()
    yield
    if _STATE_WRITES:
        seen = sorted(set(_STATE_WRITES))
        pytest.fail(
            "Test da GHI/XOA/DOI TEN file trang thai THAT trong logs/ (cron doc file nay): "
            + "; ".join(f"{name} [{event}] boi {test}" for test, event, name in seen)
            + " - truyen thu muc tam (tmp_path) cho script, xem brief dot 145.",
            pytrace=False,
        )
