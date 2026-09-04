import asyncio
import logging
from datetime import date, datetime, timedelta

import nats
import pytest

from tests.conftest import TEST_DSN, TEST_NATS_URL
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.config import Config
from trading.engine.main import run
from trading.models import Bar
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

# ISO-1: suite chay tren ha tang RIENG (DB trading_test + NATS 4223) — xem
# tests/conftest.py (hang rao chan DB/NATS san xuat). 127.0.0.1 thay vi
# localhost: tren Windows localhost resolve ::1 truoc, Docker chi publish IPv4,
# nen moi psycopg.connect() ton ~130s cho tai TCP timeout roi moi fallback sang
# IPv4. Storage mo connection moi cho MOI query, nen ca file test khong chay
# noi neu dung localhost.

DSN = TEST_DSN
pytestmark = pytest.mark.integration


def make_cfg(
    real_order_account: str = "",
    symbols: list[str] | None = None,
    real_trading_enabled: bool = False,
) -> Config:
    return Config(
        symbols=symbols if symbols is not None else ["ENGT"],
        indices=[],
        bar_interval_minutes=15,
        ssi_equity_accounts=[],
        holidays=set(),
        db_dsn=DSN,
        # 127.0.0.1 thay vi localhost: tren Windows localhost resolve ::1 truoc,
        # Docker chi publish IPv4 -> SYN toi ::1:4222 bi drop lan (nats-py treo
        # retry vo han). Test-infra fix, khong anh huong config san xuat.
        nats_url=TEST_NATS_URL,
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="x",
        ssi_consumer_secret="y",
        ssi_api_key="k",
        ssi_api_secret="s",
        ssi_private_key="pk",
        real_trading_enabled=real_trading_enabled,
        real_order_account=real_order_account,
    )


def _seed_balance(storage, withdrawable: float, ts=None) -> None:
    """Seed account_balance_snapshot cho ACC_RTS (CAP-1: engine doc so du that
    tu bang nay, khong con real_order_capital trong config)."""
    ts = ts or datetime(2026, 7, 15, 15, 0, tzinfo=TZ)
    with storage.conn() as c:
        c.execute(
            "INSERT INTO account_balance_snapshot "
            "(account_no, ts, account_balance, total_debt, withdrawable, "
            "buy_unmatched, sell_unmatched) "
            "VALUES (%s, %s, %s, 0, %s, 0, 0)",
            (RTS_ACCOUNT, ts, withdrawable, withdrawable),
        )


def _seed_nav(storage, nav: float, unpriced: list[str] | None = None, ts=None) -> None:
    """Seed account_nav_snapshot cho ACC_RTS (2026-08-18: engine lay real
    capital tu NAV thay vi account_balance_snapshot — quyet dinh chu du an
    14/08, noi dung task NAV-CI-CLEANUP)."""
    ts = ts or datetime(2026, 7, 15, 15, 0, tzinfo=TZ)
    with storage.conn() as c:
        c.execute(
            "INSERT INTO account_nav_snapshot (account_no, ts, nav, unpriced_symbols) "
            "VALUES (%s, %s, %s, %s)",
            (RTS_ACCOUNT, ts, nav, unpriced or []),
        )


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM orders WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
        c.execute("DELETE FROM real_risk_state WHERE id = 1")
        c.execute("DELETE FROM pending_real_orders WHERE symbol = 'ENGT'")
        c.execute(
            "DELETE FROM account_position_snapshot WHERE account_no = 'ACC_RTS'"
        )
        c.execute("DELETE FROM real_order_fills WHERE account_no = 'ACC_RTS'")
        c.execute(
            "DELETE FROM account_balance_snapshot WHERE account_no = 'ACC_RTS'"
        )  # CAP-1: tests seed so du that
        c.execute(
            "DELETE FROM account_nav_snapshot WHERE account_no = 'ACC_RTS'"
        )  # NAV-CI: engine real capital doc tu bang nay tu 2026-08-18
        c.execute("DELETE FROM bars WHERE symbol = 'ENGT'")  # WARM-1: warm-up doc bars tu DB
        c.execute("DELETE FROM bars_daily WHERE symbol = 'ENGT'")
        # WARM-1: test warmup seed ts0 = 2026-07-14 -> persist_fills ghi pnl_daily
        # 14/07; cac test khac ghi 15/07 — don ca 2 de khong ran cho test khac
        c.execute("DELETE FROM pnl_daily WHERE date IN ('2026-07-14', '2026-07-15')")
    yield s
    # TEARDOWN: don ca pending_real_orders (RESTORE-1 Task B) — test ghi vao
    # bang that ma khong don se tich rac (208 dong ENGT do truoc day, cung
    # loai voi 26 message NATS da sua). Don-ca-sau hoc tu 9d829f0: don chi
    # truoc = rac van con lai sau khi suite chay xong, isolation phu thuoc
    # vao dung mot lan don o lan chay ke tiep.
    # CLEAN-1: them account_position_snapshot + real_order_fills (CHI theo
    # account_no = 'ACC_RTS' — DB chua du lieu that, tuyet doi khong DELETE
    # khong dieu kien tren 2 bang nay). Test _seed_real_position() ghi vao
    # account_position_snapshot moi lan chay.
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM orders WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
        c.execute("DELETE FROM real_risk_state WHERE id = 1")
        c.execute("DELETE FROM pending_real_orders WHERE symbol = 'ENGT'")
        c.execute(
            "DELETE FROM account_position_snapshot WHERE account_no = 'ACC_RTS'"
        )
        c.execute("DELETE FROM real_order_fills WHERE account_no = 'ACC_RTS'")
        c.execute(
            "DELETE FROM account_balance_snapshot WHERE account_no = 'ACC_RTS'"
        )  # CAP-1: tests seed so du that
        c.execute(
            "DELETE FROM account_nav_snapshot WHERE account_no = 'ACC_RTS'"
        )  # NAV-CI: engine real capital doc tu bang nay tu 2026-08-18
        c.execute("DELETE FROM bars WHERE symbol = 'ENGT'")  # WARM-1: warm-up doc bars tu DB
        c.execute("DELETE FROM bars_daily WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM pnl_daily WHERE date IN ('2026-07-14', '2026-07-15')")


async def _reset_stream_and_consumer(js) -> None:
    """Purge + VERIFY stream thật sự rỗng — KHÔNG nuốt lỗi. Flake đã tái hiện
    (plan 2026-08-10): purge không ăn -> message cũ còn sót -> engine ăn nhầm
    dùng hết max_messages budget -> assert [] xa xăm. Phải fail NGAY tại
    fixture với thông điệp nói rõ, không phải 200 dòng sau."""
    info = None
    for _ in range(3):
        await js.purge_stream("BARS")
        info = await js.stream_info("BARS")
        if info.state.messages == 0:
            break
        await asyncio.sleep(0.5)
    else:
        raise AssertionError(
            f"stream BARS khong rong sau purge (con {info.state.messages} messages) — "
            f"test se an nham message cu cua test khac"
        )


@pytest.fixture(autouse=True)
async def reset_stream_and_durable_consumer():
    from nats.js.api import StreamConfig
    from nats.js.errors import BadRequestError, NotFoundError

    nc = await nats.connect(TEST_NATS_URL)
    js = nc.jetstream()
    # Stream phải TỒN TẠI để purge/stream_info chạy được trên NATS sạch
    # (NotFoundError khi mới khởi tạo) — tạo nếu chưa có, như BarPublisher.connect()
    try:
        await js.add_stream(StreamConfig(name="BARS", subjects=["bars.>"]))
    except BadRequestError:
        pass  # stream đã tồn tại
    try:
        await js.delete_consumer("BARS", "engine")
    except NotFoundError:
        pass  # consumer chưa tồn tại = trạng thái hợp lệ ở lần chạy đầu
    await _reset_stream_and_consumer(js)
    yield
    # TEARDOWN: dọn SAU test — chỉ dọn, KHÔNG assert/raise (teardown fail sẽ
    # che mất lỗi thật của chính test đó). Dọn bằng connection riêng của
    # fixture (monkeypatch purge_stream của test chỉ áp lên object js cục bộ
    # của test nên không ảnh hưởng connection này). Purge toàn bộ stream:
    # gom cả message bars.FIXTURE_PROBE mà test_fixture_fails_loudly cố ý để
    # lại — mục tiêu: sau full suite stream BARS = 0 message (plan 2026-08-12).
    try:
        await js.purge_stream("BARS")
    except Exception:
        pass  # teardown không được raise — dọn thất bại cũng không được che lỗi test
    await nc.close()


async def test_fixture_fails_loudly_when_stream_not_empty(monkeypatch):
    """Fixture phải fail NGAY và NÓI RÕ khi stream còn message sau purge —
    thay vì test chạy tiếp rồi chết ở assert cách đó 200 dòng (flake assert [])."""
    import nats
    from nats.js.api import StreamConfig
    from nats.js.errors import BadRequestError

    nc = await nats.connect(TEST_NATS_URL)
    js = nc.jetstream()
    try:
        await js.add_stream(StreamConfig(name="BARS", subjects=["bars.>"]))
    except BadRequestError:
        pass
    await js.purge_stream("BARS")
    await js.publish("bars.FIXTURE_PROBE", b"stale")  # cố ý để lại message

    async def fake_purge(*_a, **_k):
        pass  # giả lập purge không ăn — message vẫn còn trong stream

    monkeypatch.setattr(js, "purge_stream", fake_purge)
    with pytest.raises(AssertionError, match="khong rong sau purge"):
        await _reset_stream_and_consumer(js)
    await nc.close()


def make_bars(prices, sym="ENGT"):
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=15 * i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]


async def _publish(cfg, bars):
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()
    for bar in bars:
        await pub.publish(bar)
    await pub.close()


async def test_engine_persists_fill_and_restores_state_on_next_run(storage, caplog):
    cfg = make_cfg()
    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    positions = storage.read_positions()
    qty_first_run = positions["ENGT"].qty
    # ATR sizing (approve_sized) quyet dinh qty — khong hard-code con so;
    # dieu test nay can khang dinh la qty doc lai tu DB bang dung qty da ghi.
    assert qty_first_run > 0, "phai co vi the duoc mo"
    state = storage.read_engine_state()
    assert state is not None and state[0] < 100_000_000

    with storage.conn() as c:
        n_orders = c.execute(
            "SELECT count(*) FROM orders WHERE symbol = 'ENGT'"
        ).fetchone()[0]
    assert n_orders == 1

    await _publish(cfg, make_bars([20], sym="ENGT"))
    with caplog.at_level(logging.INFO):
        await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)
    assert any("engine restored state" in r.message for r in caplog.records)
    assert storage.read_positions()["ENGT"].qty == qty_first_run


async def test_engine_run_calls_real_orders_handle_crossover_on_crossover(storage, monkeypatch):
    import trading.real_orders as real_orders_mod

    cfg = make_cfg()
    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    calls = []

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar, atr=None):
        calls.append((crossover, bar))

    monkeypatch.setattr(real_orders_mod, "handle_crossover", fake_handle_crossover)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert len(calls) == 1
    assert calls[0][0] == "bull"
    assert calls[0][1].close == 20


async def test_engine_alerts_critical_on_risk_halt(storage, monkeypatch):
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    # Day noi: ep process_bar (duoc engine loop goi cho moi message) set
    # risk.halted_date, roi assert engine phat CRITICAL. Khong co gang dung lai
    # chuoi gia lam halt tu nhien — fixture gia hang lam ATR filter
    # (0.0038 < 0.005) giet crossover nen approve_sized khong bao gio duoc goi
    # (da instrument xac nhan 0 lan). Tien le: test real-risk halt cung monkeypatch.
    def fake_process_bar(bar, broker, strategy, risk, trailing_stop, marks, day_state, **kwargs):
        risk.halted_date = bar.ts.date()
        return []

    monkeypatch.setattr(engine_main, "process_bar", fake_process_bar)

    cfg = make_cfg()
    prices = [90_000] * 20 + [95_000] * 10 + [50_000] * 10
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert ("CRITICAL", "risk halt: max daily loss reached") in alerts_seen


async def test_engine_run_persists_real_risk_halt_on_transition(storage, monkeypatch):
    import trading.engine.main as engine_main
    import trading.real_orders as real_orders_mod

    halt_day = None

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar, atr=None):
        nonlocal halt_day
        if halt_day is None:
            halt_day = bar.ts.date()
            risk_arg.halted_date = halt_day

    monkeypatch.setattr(real_orders_mod, "handle_crossover", fake_handle_crossover)

    alerts_seen = []
    monkeypatch.setattr(
        engine_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    cfg = make_cfg(real_order_account="ACC_REAL_HALT")
    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert halt_day is not None
    assert ("CRITICAL", "REAL risk halt: max daily loss reached") in alerts_seen
    assert storage.read_real_risk_halt() == halt_day


async def test_engine_run_expires_stale_pending_real_order(storage):
    cfg = make_cfg()
    order_id = storage.create_pending_order(
        account_no="ACC_REAL_EXPIRE",
        symbol="ENGT",
        side="BUY",
        quantity=100,
        price=10_000.0,
        expires_at=datetime.now(TZ) - timedelta(minutes=1),
    )

    bars = make_bars([10])
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)

    assert storage.get_pending_order(order_id)["status"] == "expired"


async def test_engine_run_restores_real_risk_halt_on_startup(storage, monkeypatch):
    import trading.real_orders as real_orders_mod

    signals_seen = []

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar, atr=None):
        signals_seen.append((risk_arg.halted_date, crossover, bar))

    monkeypatch.setattr(real_orders_mod, "handle_crossover", fake_handle_crossover)

    cfg = make_cfg(real_order_account="ACC_REAL_RESTORE")
    halted_day = date(2026, 7, 15)
    storage.save_real_risk_halt(halted_day)

    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert signals_seen
    for halted_date, crossover, bar in signals_seen:
        assert halted_date == halted_day, "real_risk.halted_date should be restored from DB on startup"


async def test_engine_survives_poison_message_and_keeps_processing(
    storage, monkeypatch
):
    import json

    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    cfg = make_cfg()
    nc = await nats.connect(cfg.nats_url)
    js = nc.jetstream()
    await js.publish("bars.ssi.ENGT", json.dumps({"symbol": "ENGT"}).encode())
    await nc.close()
    await _publish(cfg, make_bars([10]))

    # Không được ném exception: message hỏng phải bị term(), không được giết engine.
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=2)

    assert any(
        lvl == "CRITICAL" and "engine failed to process bar" in m
        for lvl, m in alerts_seen
    )
    with storage.conn() as c:
        n = c.execute(
            "SELECT count(*) FROM heartbeat WHERE service = 'engine'"
        ).fetchone()[0]
    assert n == 1, "engine phải vẫn đập heartbeat sau khi gặp message hỏng"


async def test_engine_exits_cleanly_when_stop_event_set(storage):
    """SIGTERM (docker stop) -> stop_event set -> vòng lặp phải thoát ở ranh
    giới message (SAU khi ack), không cắt giữa chừng. Test phần logic, không
    gửi signal thật (Windows: add_signal_handler NotImplementedError)."""
    import asyncio

    cfg = make_cfg()
    stop_event = asyncio.Event()
    bars = make_bars([10] * 20 + [20] * 5)
    await _publish(cfg, bars[:5])

    task = asyncio.create_task(run(cfg, strategy=SmaCrossStrategy(), stop_event=stop_event))
    # chờ engine xử lý được ít nhất 1 message (heartbeat beat — chỉ xảy ra
    # sau khi message đã được xử lý trọn vẹn + ack)
    n = 0
    for _ in range(100):
        with storage.conn() as c:
            n = c.execute(
                "SELECT count(*) FROM heartbeat WHERE service = 'engine'"
            ).fetchone()[0]
        if n >= 1:
            break
        await asyncio.sleep(0.1)
    assert n >= 1, "engine phai xu ly duoc it nhat 1 message truoc khi dung"

    stop_event.set()
    await asyncio.wait_for(task, timeout=15)
    # thoát sạch: không exception, không treo


async def test_engine_stops_within_docker_grace_when_idle(storage):
    """SIGTERM lúc engine ĐANG RẢNH (không có message nào) phải thoát < 10s
    (grace của docker stop). Bug đo thật: while check stop_event ở ĐẦU vòng
    rồi block trong sub.next_msg(timeout=60) -> mất tới 58.2s -> luôn bị
    SIGKILL; trong 10s grace engine VẪN nhận + xử lý message mới -> ghi DB
    chưa ack -> JetStream giao lại -> lệnh trùng."""
    import asyncio

    cfg = make_cfg()
    stop_event = asyncio.Event()

    task = asyncio.create_task(run(cfg, strategy=SmaCrossStrategy(), stop_event=stop_event))
    await asyncio.sleep(0.5)  # engine đã vào vòng lặp, đang block chờ message
    stop_event.set()

    await asyncio.wait_for(task, timeout=10)
    # không publish message nào — vòng lặp phải thoát ngay khi stop_event set


async def test_engine_no_stop_waiter_leak_after_run(storage):
    """Mỗi vòng lặp phải HỦY stop_task (stop_event.wait()) khi next_msg thắng —
    bug đo thật (Claude): thiếu stop_task.cancel() -> mỗi vòng lặp rò rỉ 1
    future wait() -> ev._waiters tăng tuyến tính theo số message (sau 200
    message = 200 waiters) kèm cảnh báo 'Task was destroyed but it is pending!'."""
    import asyncio

    cfg = make_cfg()
    stop_event = asyncio.Event()
    bars = make_bars([10] * 20 + [20] * 5)
    await _publish(cfg, bars)

    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars), stop_event=stop_event)

    assert len(stop_event._waiters) == 0, (
        f"stop waiter bi ro ri: {len(stop_event._waiters)} (phai la 0 sau khi run xong)"
    )


async def test_engine_restores_trailing_stop_after_restart(storage, monkeypatch):
    """Bug RESTORE-1 Task A: TrailingStopManager._highest la dict in-memory —
    sau restart, vi the khoi phuc tu DB nhung _highest rong -> check() return
    None -> trailing stop BI VO HIEU HOA VINH VIEN, im lang, cho toi khi vi
    the dong roi mo lai. Test nay phai FAIL tren code hien tai (chua tai dung
    _highest luc khoi dong)."""
    from trading.broker import Fill, Position

    cfg = make_cfg()
    entry_ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    # Seed trang thai nhu sau restart: vi the dang mo + BUY fill cu + 1 bar
    # daily voi high 20 (dinh gia tu luc vao lenh — trailing stop phai tinh
    # tu day, khong phai tu gia vao lenh 10).
    storage.upsert_position(Position("ENGT", 1, 10.0))
    storage.write_order(Fill("ENGT", "BUY", 1, 10.0, 0.0, entry_ts))
    storage.write_bars([Bar("ENGT", entry_ts, 20.0, 20.0, 20.0, 20.0, 1000)])
    # engine_state phai TON TAI de run() di duong restore (broker.restore nap
    # positions vao broker) — neu de trong, engine chay fresh, broker khong co
    # vi the -> trailing stop khong bao gio duoc check (sai kich ban restart).
    storage.write_engine_state(100_000_000 - 10.0, 0.0)

    # Bar moi: gia quanh dinh (de ATR co gia tri) roi BUT xuong low 5 — duoi
    # stop tinh tu dinh 20 (20 - atr*2 ~ 19.8). Trailing stop DUNG phai trigger.
    # T+2,5 (commit 4a61186): PaperBroker.restore dat lot day_index=0 (ngay
    # restart), chi ban duoc khi today - day_index >= SETTLE_DAYS=3. Bar kich
    # hoat PHAI nam o D+3 (ngay giao dich thu 4), khong duoc cung ngay 15/07 —
    # khong thi force_exit tra qty=0 (chua settle) va vi the khong bao gio dong.
    bars = make_bars([20] * 20 + [21] * 4)  # 15/07 (day 0): warm-up ATR quanh dinh
    d2 = datetime(2026, 7, 16, 9, 0, tzinfo=TZ)  # day 1
    d3 = datetime(2026, 7, 17, 9, 0, tzinfo=TZ)  # day 2
    for day in (d2, d3):
        bars.append(Bar("ENGT", day, 21.0, 21.0, 21.0, 21.0, 1000))
    bars.append(  # day 3 (D+3): BUT xuong low 5 — duoi stop, da settle -> ban duoc
        Bar("ENGT", datetime(2026, 7, 20, 9, 0, tzinfo=TZ), 21.0, 21.0, 5.0, 21.0, 1000)
    )
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    pos = storage.read_positions().get("ENGT")
    assert pos is None or pos.qty == 0, (
        "trailing stop phai duoc tai dung sau restart: vi the phai bi dong "
        f"khi gia but xuong, nhung con qty={pos.qty if pos else 'closed'}"
    )


async def test_engine_alerts_warn_when_trailing_stop_cannot_restore(storage, monkeypatch):
    """Vi the mo nhung khong tai dung duoc trailing stop (khong co BUY fill,
    khong co bar tu luc vao lenh) -> PHAI alert WARN noi ro symbol — im lang
    chinh la ban chat cua bug RESTORE-1 Task A, khong duoc tai tao no."""
    import trading.engine.main as engine_main
    from trading.broker import Position

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg()
    storage.upsert_position(Position("ENGT", 1, 10.0))
    storage.write_engine_state(100_000_000 - 10.0, 0.0)
    # KHONG write_order -> khong co BUY fill -> read_highest_since_buy tra None

    bars = make_bars([10] * 5)
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert any(
        level == "WARN" and "ENGT" in msg and "trailing stop" in msg
        for level, msg in alerts_seen
    ), f"phai alert WARN neu ro symbol va vi the khong co trailing stop, thuc te: {alerts_seen}"


async def test_engine_alerts_critical_when_real_nav_too_small(storage, monkeypatch):
    """GUARD-1 (NAV-CI): NAV nho den muc tran gia tri lenh khong du mua
    1 lo 100 cp cua ma re nhat -> alert CRITICAL noi ro ca hai con so. Seed
    account_nav_snapshot thay vi real_order_capital (da bo khoi config)."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    _seed_nav(storage, 21459)  # tran 4.292d < 1 lo ENGT 2.200.000d
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=True)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert any(
        level == "CRITICAL" and "INERT" in msg and "4,292" in msg and "2,200,000" in msg
        for level, msg in alerts_seen
    ), f"phai alert CRITICAL noi ro tran (4.292) va gia lo re nhat (2.200.000), thuc te: {alerts_seen}"


async def test_engine_silent_when_trading_disabled_and_nav_tiny(storage, monkeypatch):
    """GUARD-2 (NAV-CI): real_trading_enabled=False + NAV nho = trang thai
    dang chay -> phai IM LANG hoan toan. Neu test nay fail nghia la ta vua
    them mot nguon canh bao rac vinh vien."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    _seed_nav(storage, 21459)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=False)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"trading tat + so du nho la trang thai mong muon -> phai im lang, thuc te: {alerts_seen}"
    )


async def test_engine_no_critical_alert_when_nav_sufficient(storage, monkeypatch):
    """GUARD-1 (NAV-CI): NAV du lon (100 trieu, tran 20 trieu > 1 lo
    2.200.000) -> KHONG co alert CRITICAL — canh bao khong keu bua."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    _seed_nav(storage, 100_000_000)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=True)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"so du du lon khong duoc keu INERT, thuc te: {alerts_seen}"
    )


async def test_engine_skips_guard_silently_when_no_prices(storage, monkeypatch):
    """GUARD-1 (CAP-1): khong lay duoc gia nao (bang rong) -> bo qua im lang,
    khong alert sai, khong crash."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    _seed_nav(storage, 21459)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    with storage.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM bars_daily WHERE symbol = 'ENGT'")

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"khong co gia -> khong duoc canh bao INERT, thuc te: {alerts_seen}"
    )


# ============ CAP-1/NAV-CI: vốn lệnh thật đọc từ account_nav_snapshot ============


async def test_engine_informs_real_nav_at_startup(storage, monkeypatch):
    """NAV-CI: seed account_nav_snapshot = 5.021.459 -> engine khoi dong ->
    alert INFO neu dung so tien + moc thoi gian (nguoi van hanh phai nhin duoc
    he thong dang tinh rui ro tren con so nao). NAV = capital (quyet dinh chu
    du an 14/08), khong phai withdrawable."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg, f))
    )

    ts_nav = datetime.now(TZ) - timedelta(hours=1)  # moi nhat — < 24h bat ky ngay nao
    _seed_nav(storage, 5_021_459, ts=ts_nav)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    await _publish(cfg, make_bars([10]))
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)

    assert any(
        level == "INFO"
        and "NAV" in msg
        and f.get("nav") == 5_021_459
        and datetime.fromisoformat(f.get("ts", "")).astimezone(TZ) == ts_nav
        for level, msg, f in alerts_seen
    ), f"phai INFO neu NAV that + moc thoi gian, thuc te: {alerts_seen}"


async def test_engine_critical_and_blocks_buy_when_no_nav(storage, monkeypatch):
    """NAV-CI fail-safe: khong co dong account_nav_snapshot nao -> CRITICAL +
    real capital = 0 -> MOI lenh that bi approve() tu choi (khong tao pending).
    KHONG duoc roi ve so du kha dung cho 'do gat'. RED bat buoc: doi
    fallback thanh so de dai -> test phai FAIL."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    # KHONG seed nav — bang rong. NHUNG seed balance LON: neu ai do cai
    # fallback ve so du kha dung thi capital se to va sinh lenh —
    # day la cai bay bat dung hanh vi bi cam.
    _seed_balance(storage, 500_000_000.0)

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    bars = make_bars([10] * 20 + [20] * 5)  # crossover bull o bar 21
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert any(
        level == "CRITICAL" and "khong doc duoc NAV" in msg
        for level, msg in alerts_seen
    ), f"phai CRITICAL khi khong doc duoc NAV, thuc te: {alerts_seen}"
    with storage.conn() as c:
        n = c.execute(
            "SELECT count(*) FROM pending_real_orders WHERE symbol = 'ENGT'"
        ).fetchone()[0]
    assert n == 0, f"capital=0 (fail-safe) -> MOI lenh that bi tu choi, thuc te pending={n}"


async def test_engine_warns_when_nav_stale(storage, monkeypatch):
    """NAV-CI WARN: dong NAV cu hon 24h -> VAN dung nhung alert WARN kem tuoi
    cua du lieu (khong im lang ve du lieu cu)."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    stale_ts = datetime(2026, 7, 13, 9, 0, tzinfo=TZ)  # 2 ngay truoc test day
    _seed_nav(storage, 5_021_459, ts=stale_ts)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    await _publish(cfg, make_bars([10]))
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)

    assert any(
        level == "WARN" and "cu hon 24h" in msg and "h)" in msg
        for level, msg in alerts_seen
    ), f"phai WARN kem tuoi du lieu cu, thuc te: {alerts_seen}"


async def test_engine_warns_when_nav_unpriced(storage, monkeypatch):
    """NAV-CI nhanh thu tu: unpriced_symbols khong rong -> VAN dung NAV (tinh
    hut la an toan — vốn nho hon thuc te -> lenh nho hon) nhung phai WARN neu
    ro ma nao, khong im lang. 0434226 that co unpriced=['MIRHCM261'] nen nhanh
    nay chay that."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg, f))
    )

    _seed_nav(storage, 197_222_417, unpriced=["MIRHCM261"], ts=datetime.now(TZ))
    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    await _publish(cfg, make_bars([10]))
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)

    assert any(
        level == "WARN"
        and "NAV tinh thieu" in msg
        and f.get("unpriced") == "MIRHCM261"
        for level, msg, f in alerts_seen
    ), f"phai WARN neu ro ma khong dinh gia duoc, thuc te: {alerts_seen}"
    # Van dung NAV (khong bi chan vi co unpriced): phai INFO nav bang dung so
    assert any(
        level == "INFO" and f.get("nav") == 197_222_417
        for level, msg, f in alerts_seen
    ), f"NAV van duoc dung lam capital, thuc te: {alerts_seen}"


# ============ RTS-1: trailing stop luong lenh THAT ============

RTS_ACCOUNT = "ACC_RTS"


def _seed_real_position(storage, qty=100, sellable=100, account=RTS_ACCOUNT):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.save_account_positions(
        account, ts, [{"symbol": "ENGT", "quantity": qty, "cost_price": 10.0, "sellable_quantity": sellable}]
    )


def _make_real_stop_bar(low=5.0):
    return Bar("ENGT", datetime(2026, 7, 15, 10, 0, tzinfo=TZ), 21.0, 21.0, low, 21.0, 1000)


def _count_pending_sells(storage, account=RTS_ACCOUNT):
    with storage.conn() as c:
        return c.execute(
            "SELECT count(*) FROM pending_real_orders WHERE account_no = %s AND side = 'SELL'",
            (account,),
        ).fetchone()[0]


async def test_real_stop_touch_creates_pending_sell(storage, monkeypatch):
    """RTS-1 muc 1: cham stop + sellable_qty > 0 -> co pending SELL dung
    sellable_qty + co alert (canh bao CHAM STOP, khong phai stop-loss tu dong)."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    ts = TrailingStopManager()
    ts.on_position_opened("ENGT", 20.0)  # dinh 20

    handle_stop_touch(cfg, storage, _make_real_stop_bar(low=5.0), atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 1
    with storage.conn() as c:
        row = c.execute(
            "SELECT quantity, side, price FROM pending_real_orders WHERE account_no = %s AND side = 'SELL'",
            (RTS_ACCOUNT,),
        ).fetchone()
    assert row[0] == 100, f"phai dung sellable_qty (100), thuc te {row[0]}"
    assert any(level == "WARN" and "STOP TOUCH" in msg for level, msg in alerts_seen), alerts_seen


async def test_real_stop_touch_ignores_daily_halt(storage, monkeypatch):
    """RTS-1 muc 2 + muc 4: halt lo ngay (risk.approve() chan ca SELL khi
    halted_date == today) KHONG chan lenh cat lo — tien le logic.py:51-54
    (luong paper bo qua risk cho stop-loss). Lenh SELL do cham stop KHONG di
    qua risk.approve()."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    storage.save_real_risk_halt(date(2026, 7, 15))  # halt DUNG ngay cua bar
    ts = TrailingStopManager()
    ts.on_position_opened("ENGT", 20.0)

    handle_stop_touch(cfg, storage, _make_real_stop_bar(low=5.0), atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 1, (
        "halt lo ngay KHONG duoc chan lenh cat lo (halt xay ra vi dang lo roi "
        "chinh no khoa duong thoat la nguy hiem — logic.py:51-54)"
    )


async def test_real_stop_touch_warns_when_not_settled(storage, monkeypatch):
    """RTS-1 muc 3: sellable_qty = 0 (chua settle T+2.5) -> khong sinh lenh,
    CO alert WARN neu ro (thong tin nguoi van hanh can, khong nuot)."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage, qty=100, sellable=0)  # qty>0 nhung chua settle
    ts = TrailingStopManager()
    ts.on_position_opened("ENGT", 20.0)

    handle_stop_touch(cfg, storage, _make_real_stop_bar(low=5.0), atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 0
    assert any(
        level == "WARN" and "chua settle" in msg and "ENGT" in msg
        for level, msg in alerts_seen
    ), f"phai alert WARN noi ro chua ban duoc vi chua settle, thuc te: {alerts_seen}"


async def test_real_stop_touch_no_duplicate_pending(storage, monkeypatch):
    """RTS-1 muc 4: hai bar lien tiep deu cham stop -> chi MOT pending SELL
    (moi bar cham stop se de ra mot lenh cho moi neu khong chan)."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    ts = TrailingStopManager()
    ts.on_position_opened("ENGT", 20.0)

    bar1 = _make_real_stop_bar(low=5.0)
    bar2 = Bar("ENGT", bar1.ts + timedelta(minutes=15), 21.0, 21.0, 4.0, 21.0, 1000)
    handle_stop_touch(cfg, storage, bar1, atr=1.0, real_trailing_stop=ts)
    handle_stop_touch(cfg, storage, bar2, atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 1, "phai chan lenh SELL trung khi da co pending hieu luc"


async def test_engine_restores_real_trailing_stop_and_touches_stop(storage, monkeypatch):
    """RTS-1 muc 5: sau restart, real_trailing_stop tai dung tu real_order_fills
    (BUY fill) + bars — bar moi but xuong cham stop -> sinh pending SELL."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    # engine_state phai ton tai de di duong restore (như test paper)
    storage.write_engine_state(100_000_000 - 10.0, 0.0)
    # BUY fill that + bar daily high 20 (dinh tu luc vao lenh)
    entry_ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    with storage.conn() as c:
        c.execute(
            "INSERT INTO real_order_fills (ts, account_no, symbol, side, qty, price, fee, status) "
            "VALUES (%s, %s, 'ENGT', 'BUY', 100, 10.0, 0, 'filled')",
            (entry_ts, RTS_ACCOUNT),
        )
    storage.write_bars([Bar("ENGT", entry_ts, 20.0, 20.0, 20.0, 20.0, 1000)])

    bars = make_bars([20] * 20 + [21] * 4)
    bars.append(Bar("ENGT", bars[-1].ts + timedelta(minutes=15), 21.0, 21.0, 5.0, 21.0, 1000))
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert _count_pending_sells(storage) == 1, (
        "real_trailing_stop phai duoc tai dung sau restart (dinh 20) va cham "
        "stop phai sinh pending SELL"
    )


async def test_engine_warns_when_real_trailing_stop_cannot_restore(storage, monkeypatch):
    """RTS-1 muc 5: vi the that ton tai nhung khong co BUY fill trong
    real_order_fills (mua ngoai he thong) -> khong tai dung duoc -> alert WARN
    neu ro ma, KHONG im lang."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    storage.write_engine_state(100_000_000 - 10.0, 0.0)
    # CLEAN-1: fixture da don real_order_fills/account_position_snapshot cho
    # ACC_RTS (setup + teardown) — khong can DELETE thu cong trong test nua.
    # Kich ban: vi the that ton tai NHUNG khong co fill nao (mua ngoai he thong).

    bars = make_bars([10] * 5)
    await _publish(cfg, bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=len(bars))

    assert any(
        level == "WARN" and "ENGT" in msg and "khong tai dung duoc trailing stop" in msg
        for level, msg in alerts_seen
    ), f"phai alert WARN noi ro khong tai dung duoc trailing stop cho vi the that, thuc te: {alerts_seen}"


async def test_real_stop_touch_init_tracking_mid_session(storage, monkeypatch):
    """RTS-2: vi the that xuat hien GIUA PHIEN (nguoi dung xac nhan BUY that,
    SSI khop, snapshot cap nhat) — trailing stop CHUA theo doi ma do (khoi tao
    chi chay luc engine khoi dong). Phai khoi tao truoc khi check, khong thi
    check() tra None MAI MAI (trailing_stop.py:26-28) -> khong bao gio cham
    stop. Test nay phai FAIL tren code hien tai (lo hong co that)."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)
    entry_ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    with storage.conn() as c:
        c.execute(
            "INSERT INTO real_order_fills (ts, account_no, symbol, side, qty, price, fee, status) "
            "VALUES (%s, %s, 'ENGT', 'BUY', 100, 10.0, 0, 'filled')",
            (entry_ts, RTS_ACCOUNT),
        )
    storage.write_bars([Bar("ENGT", entry_ts, 10.0, 10.0, 10.0, 10.0, 1000)])

    ts = TrailingStopManager()  # KHONG goi on_position_opened — vi the mo GIUA PHIEN
    bar1 = Bar("ENGT", entry_ts + timedelta(minutes=15), 30.0, 30.0, 30.0, 30.0, 1000)
    bar2 = Bar("ENGT", entry_ts + timedelta(minutes=30), 30.0, 30.0, 5.0, 30.0, 1000)
    handle_stop_touch(cfg, storage, bar1, atr=1.0, real_trailing_stop=ts)
    handle_stop_touch(cfg, storage, bar2, atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 1, (
        "vi the that mo giua phien phai duoc trailing stop khoi tao truoc khi "
        "check (bar but len 30 roi sup xuong 5 phai cham stop tu dinh 30)"
    )


async def test_real_stop_touch_falls_back_to_avg_price(storage, monkeypatch):
    """RTS-2 fallback: khong co real_order_fills (mua ngoai he thong) ->
    khoi tao _highest bang avg_price + alert WARN noi ro dang dung gia von
    thay cho dinh that. Canh bao 1 lan (lan sau da tracking)."""
    from trading.real_orders import handle_stop_touch
    from trading.trailing_stop import TrailingStopManager

    alerts_seen = []
    monkeypatch.setattr(
        "trading.real_orders.alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_account=RTS_ACCOUNT)
    _seed_real_position(storage)  # cost_price = 10 — khong INSERT fill nao
    ts = TrailingStopManager()
    entry_ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    bar1 = Bar("ENGT", entry_ts + timedelta(minutes=15), 30.0, 30.0, 30.0, 30.0, 1000)
    bar2 = Bar("ENGT", entry_ts + timedelta(minutes=30), 30.0, 30.0, 5.0, 30.0, 1000)
    handle_stop_touch(cfg, storage, bar1, atr=1.0, real_trailing_stop=ts)
    handle_stop_touch(cfg, storage, bar2, atr=1.0, real_trailing_stop=ts)

    assert _count_pending_sells(storage) == 1
    gia_von_warns = [
        m for l, m in alerts_seen if l == "WARN" and "GIA VON" in m and "ENGT" in m
    ]
    assert len(gia_von_warns) == 1, (
        f"phai alert WARN 1 lan noi ro dang dung gia von thay cho dinh that, thuc te: {alerts_seen}"
    )


# ============ WARM-1 Viec A: warm-up SMA/ATR luc engine khoi dong ============


def _warm_bars(n: int, price: float, start: datetime) -> list[Bar]:
    """n bar 5 phut gia khong doi bat dau tu start — seed cho warm-up."""
    return [
        Bar("ENGT", start + timedelta(minutes=5 * i), price, price, price, price, 1000)
        for i in range(n)
    ]


async def test_engine_warmup_enables_immediate_signal(storage, monkeypatch):
    """WARM-1 A1: warm-up nap 21 bar lich su (slow=20 + 1 de _prev_above thoat
    None) tu bang bars -> bar SONG dau tien qua NATS tao crossover -> lenh sinh
    NGAy tu bar dau tien (khong phai doi ~1h45' nhu truoc). RED bat buoc: bo
    phan nap di -> cung kich ban -> khong co lenh nao."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    cfg = make_cfg()
    ts0 = datetime(2026, 7, 14, 9, 0, tzinfo=TZ)
    storage.write_bars(_warm_bars(21, 10.0, ts0))  # 21 bar gia 10 — chua crossover
    live = Bar(
        "ENGT", ts0 + timedelta(minutes=5 * 21), 20.0, 20.0, 20.0, 20.0, 1000
    )  # bar 1: crossover -> broker.submit lenh
    live2 = Bar(
        "ENGT", ts0 + timedelta(minutes=5 * 22), 20.0, 20.0, 20.0, 20.0, 1000
    )  # bar 2: broker fill lenh (PaperBroker submit -> fill o bar ke tiep)
    await _publish(cfg, [live, live2])
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=2)
    with storage.conn() as c:
        n = c.execute("SELECT count(*) FROM orders WHERE symbol = 'ENGT'").fetchone()[0]
    assert n == 1, f"warm-up xong phai ban duoc ngay bar dau, thuc te orders={n}, alerts={alerts_seen}"


async def test_engine_warmup_skips_replayed_bars(storage, monkeypatch):
    """WARM-1 A2 CHONG NAP TRUNG: consumer durable giao lai bar CHUA ACK sau
    restart — bar do da nam trong DB nen vua duoc warm-up nap. Publish lai bar
    ts CU (trong cua so warm-up) -> phai bi BO QUA, khong an lan hai (leth cua
    so MA). Kiem qua ts cua lenh: phai la bar SONG, khong phai bar cu duoc nap
    lai. RED bat buoc: bo dieu kien warmed_until -> lenh sinh tu bar cu -> fail."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    cfg = make_cfg()
    ts0 = datetime(2026, 7, 14, 9, 0, tzinfo=TZ)
    storage.write_bars(_warm_bars(21, 10.0, ts0))  # warm-up den T20
    old = Bar(
        "ENGT", ts0 + timedelta(minutes=5 * 20), 20.0, 20.0, 20.0, 20.0, 1000
    )  # ts CU = T20 — nam trong cua so warm-up (durable consumer giao lai)
    live = Bar(
        "ENGT", ts0 + timedelta(minutes=5 * 21), 20.0, 20.0, 20.0, 20.0, 1000
    )  # bar song 1: crossover -> submit
    live2 = Bar(
        "ENGT", ts0 + timedelta(minutes=5 * 22), 20.0, 20.0, 20.0, 20.0, 1000
    )  # bar song 2: broker fill (ts cua lenh = T22 = live2.ts)
    await _publish(cfg, [old, live, live2])
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=3)
    with storage.conn() as c:
        row = c.execute(
            "SELECT ts FROM orders WHERE symbol = 'ENGT' ORDER BY ts LIMIT 1"
        ).fetchone()
    assert row is not None, "phai co lenh tu bar song"
    assert row[0] == live2.ts, (
        f"lenh phai sinh tu bar SONG (khong phai bar cu duoc nap lai), thuc te ts={row[0]}"
    )


async def test_engine_warmup_warns_when_history_short(storage, monkeypatch):
    """WARM-1 A3: DB chi co vai bar -> alert WARN neu ro symbol + so bar nap
    duoc, noi ro ma do VAN DANG MU. Khong co WARN la fail (chinh la cai 'im
    lang' ma rui ro 5 noi toi)."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    cfg = make_cfg()
    ts0 = datetime(2026, 7, 14, 9, 0, tzinfo=TZ)
    storage.write_bars(_warm_bars(5, 10.0, ts0))  # 5 bar — thieu (can 21)
    await _publish(cfg, make_bars([10]))
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=1)
    assert any(
        level == "WARN" and "ENGT" in msg and "thieu lich su" in msg
        for level, msg in alerts_seen
    ), f"phai WARN thieu lich su cho ENGT, thuc te: {alerts_seen}"


async def test_engine_warmup_does_not_generate_orders(storage, monkeypatch):
    """WARM-1 A4: warm-up nap bang compute_crossover() (chi cap nhat state ky
    thuat) TUYET DOI khong dung process_bar — bar lich su khong duoc di qua
    broker. Seed lich su chua ca bull lan bear crossover -> sau khi khoi dong,
    orders KHONG co dong nao sinh tu chung."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    cfg = make_cfg()
    ts0 = datetime(2026, 7, 14, 9, 0, tzinfo=TZ)
    prices = [10] * 10 + [20] * 10 + [10]  # bull (10->20) roi bear (20->10)
    bars = [
        Bar("ENGT", ts0 + timedelta(minutes=5 * i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]
    storage.write_bars(bars)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=0)  # warm-up chay truoc loop, khong co message nao
    with storage.conn() as c:
        n = c.execute("SELECT count(*) FROM orders WHERE symbol = 'ENGT'").fetchone()[0]
    assert n == 0, f"warm-up KHONG duoc sinh lenh, thuc te orders={n}"


# ============ Plan 2026-09-01 T2-B1: GUARD-3 cong bo quyen ban ============


async def test_guard3_silent_when_no_intersection(storage, monkeypatch):
    """GUARD-3 (a): giao cfg.symbols vs danh muc that RONG -> im lang. Khi
    trading bat ma khong co gi de ban, canh bao chi la tieng on (NOISE-1)."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=True)
    # danh muc that rong — khong seed gi
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=0)
    assert not any(
        level == "WARN" and "quyền bán" in msg for level, msg in alerts_seen
    ), f"giao rong phai im lang, thuc te: {alerts_seen}"


async def test_guard3_alerts_sell_entitlement_when_intersection(storage, monkeypatch):
    """GUARD-3 (b): giao co ENGT 1500 -> alert WARN liet ke ma + khoi luong +
    sellable_qty, noi ro engine co the sinh lenh BAN so co phieu nay."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    _seed_real_position(storage, qty=1500, sellable=1400)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=True)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=0)
    assert any(
        level == "WARN" and "quyền bán" in msg and "ENGT" in msg and "1500" in msg and "1400" in msg
        for level, msg in alerts_seen
    ), f"phai WARN cong bo quyen ban ENGT 1500 (sellable 1400), thuc te: {alerts_seen}"


async def test_guard3_silent_when_trading_disabled(storage, monkeypatch):
    """GUARD-3 (c): real_trading_enabled=False -> im lang DU danh muc that co
    giao voi symbols (bai hoc NOISE-1: canh bao khi trading tat la nhieu)."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )
    _seed_real_position(storage, qty=1500, sellable=1400)
    cfg = make_cfg(real_order_account=RTS_ACCOUNT, real_trading_enabled=False)
    await run(cfg, strategy=SmaCrossStrategy(), max_messages=0)
    assert not any(
        level == "WARN" and "quyền bán" in msg for level, msg in alerts_seen
    ), f"trading tat phai im lang, thuc te: {alerts_seen}"
