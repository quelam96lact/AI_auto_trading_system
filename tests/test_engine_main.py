import asyncio
import logging
import os
from datetime import date, datetime, timedelta

import nats
import pytest

from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.config import Config
from trading.engine.main import run
from trading.models import Bar
from trading.storage.db import Storage

# 127.0.0.1 thay vi localhost: cung ly do nhu nats_url ben duoi — tren Windows
# localhost resolve ::1 truoc, Docker chi publish IPv4, nen moi psycopg.connect()
# ton ~130s cho tai TCP timeout roi moi fallback sang IPv4. Storage mo connection
# moi cho MOI query, nen ca file test khong chay noi neu dung localhost.
DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@127.0.0.1:5432/trading")
pytestmark = pytest.mark.integration


def make_cfg(
    real_order_account: str = "",
    real_order_capital: float = 0,
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
        nats_url="nats://127.0.0.1:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="x",
        ssi_consumer_secret="y",
        ssi_api_key="k",
        ssi_api_secret="s",
        ssi_private_key="pk",
        real_trading_enabled=real_trading_enabled,
        real_order_capital=real_order_capital,
        real_order_account=real_order_account,
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
    yield s
    # TEARDOWN: don ca pending_real_orders (RESTORE-1 Task B) — test ghi vao
    # bang that ma khong don se tich rac (208 dong ENGT do truoc day, cung
    # loai voi 26 message NATS da sua). Don-ca-sau hoc tu 9d829f0: don chi
    # truoc = rac van con lai sau khi suite chay xong, isolation phu thuoc
    # vao dung mot lan don o lan chay ke tiep.
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM orders WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
        c.execute("DELETE FROM real_risk_state WHERE id = 1")
        c.execute("DELETE FROM pending_real_orders WHERE symbol = 'ENGT'")


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

    nc = await nats.connect("nats://127.0.0.1:4222")
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

    nc = await nats.connect("nats://127.0.0.1:4222")
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

    await run(cfg, max_messages=len(bars))

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
        await run(cfg, max_messages=1)
    assert any("engine restored state" in r.message for r in caplog.records)
    assert storage.read_positions()["ENGT"].qty == qty_first_run


async def test_engine_run_calls_real_orders_handle_crossover_on_crossover(storage, monkeypatch):
    import trading.real_orders as real_orders_mod

    cfg = make_cfg()
    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    calls = []

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar):
        calls.append((crossover, bar))

    monkeypatch.setattr(real_orders_mod, "handle_crossover", fake_handle_crossover)

    await run(cfg, max_messages=len(bars))

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

    await run(cfg, max_messages=len(bars))

    assert ("CRITICAL", "risk halt: max daily loss reached") in alerts_seen


async def test_engine_run_persists_real_risk_halt_on_transition(storage, monkeypatch):
    import trading.engine.main as engine_main
    import trading.real_orders as real_orders_mod

    halt_day = None

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar):
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

    await run(cfg, max_messages=len(bars))

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

    await run(cfg, max_messages=1)

    assert storage.get_pending_order(order_id)["status"] == "expired"


async def test_engine_run_restores_real_risk_halt_on_startup(storage, monkeypatch):
    import trading.real_orders as real_orders_mod

    signals_seen = []

    def fake_handle_crossover(cfg_arg, storage_arg, risk_arg, crossover, bar):
        signals_seen.append((risk_arg.halted_date, crossover, bar))

    monkeypatch.setattr(real_orders_mod, "handle_crossover", fake_handle_crossover)

    cfg = make_cfg(real_order_account="ACC_REAL_RESTORE")
    halted_day = date(2026, 7, 15)
    storage.save_real_risk_halt(halted_day)

    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, max_messages=len(bars))

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
    await run(cfg, max_messages=2)

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

    task = asyncio.create_task(run(cfg, stop_event=stop_event))
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

    task = asyncio.create_task(run(cfg, stop_event=stop_event))
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

    await run(cfg, max_messages=len(bars), stop_event=stop_event)

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
    bars = make_bars([20] * 20 + [21] * 4)
    bars.append(Bar("ENGT", bars[-1].ts + timedelta(minutes=15), 21.0, 21.0, 5.0, 21.0, 1000))
    await _publish(cfg, bars)
    await run(cfg, max_messages=len(bars))

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
    await run(cfg, max_messages=len(bars))

    assert any(
        level == "WARN" and "ENGT" in msg and "trailing stop" in msg
        for level, msg in alerts_seen
    ), f"phai alert WARN neu ro symbol va vi the khong co trailing stop, thuc te: {alerts_seen}"


async def test_engine_alerts_critical_when_real_order_capital_too_small(storage, monkeypatch):
    """GUARD-1: real_order_capital nho den muc tran gia tri lenh khong du mua
    1 lo 100 cp cua ma re nhat -> alert CRITICAL noi ro ca hai con so. Day la
    tinh huong THAT dang ton tai (capital=21459: tran 4.292d < 1 lo HPG
    2.200.000d) — duong dat lenh that la CODE CHET ma khong ai biet."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_capital=21459, real_trading_enabled=True)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, max_messages=len(bars))

    assert any(
        level == "CRITICAL" and "INERT" in msg and "4,292" in msg and "2,200,000" in msg
        for level, msg in alerts_seen
    ), f"phai alert CRITICAL noi ro tran (4.292) va gia lo re nhat (2.200.000), thuc te: {alerts_seen}"


async def test_engine_silent_when_trading_disabled_and_capital_tiny(storage, monkeypatch):
    """GUARD-2: real_trading_enabled=False + capital nho = CAU HINH THAT dang
    chay (chu du an CO Y khoa duong lenh that) -> phai IM LANG hoan toan.
    Neu test nay fail nghia la ta vua them mot nguon canh bao rac vinh vien."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_capital=21459, real_trading_enabled=False)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"trading tat + capital nho la trang thai mong muon -> phai im lang, thuc te: {alerts_seen}"
    )


async def test_engine_no_critical_alert_when_capital_sufficient(storage, monkeypatch):
    """GUARD-1: capital du lon (100 trieu, tran 20 trieu > 1 lo 2.200.000) ->
    KHONG co alert CRITICAL — canh bao khong keu bua."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_capital=100_000_000, real_trading_enabled=True)
    ts = datetime(2026, 7, 15, 15, 30, tzinfo=TZ)
    storage.write_bars([Bar("ENGT", ts, 22000.0, 22000.0, 22000.0, 22000.0, 1000)])

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"capital du lon khong duoc keu INERT, thuc te: {alerts_seen}"
    )


async def test_engine_skips_guard_silently_when_no_prices(storage, monkeypatch):
    """GUARD-1: khong lay duoc gia nao (bang rong) -> bo qua im lang, khong
    alert sai, khong crash."""
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg))
    )

    cfg = make_cfg(real_order_capital=21459)
    with storage.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM bars_daily WHERE symbol = 'ENGT'")

    bars = make_bars([10])
    await _publish(cfg, bars)
    await run(cfg, max_messages=len(bars))

    assert not any(level == "CRITICAL" and "INERT" in msg for level, msg in alerts_seen), (
        f"khong co gia -> khong duoc canh bao INERT, thuc te: {alerts_seen}"
    )
