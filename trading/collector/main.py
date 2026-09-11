import argparse
import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from trading.alerts import alert
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ, is_trading_time
from trading.collector.account_sync import sync_account_data
from trading.collector.backfill import SSIRestClient, run_backfill
from trading.collector.derivative_sync import sync_derivative_data
from trading.collector.feed import SSIFeed
from trading.collector.latch import BarLatch
from trading.collector.parser import parse_interval_message
from trading.collector.watchdog import Watchdog
from trading.config import load_config
from trading.storage.db import Storage

EOD_HOUR, EOD_MINUTE = 15, 5  # EOD gap repair job
CLOCK_DRIFT_THRESHOLD_SECONDS = 120.0  # Ngưỡng phát hiện máy chủ ngủ (nhịp tick 30s: drift > 120s chỉ ra hệ thống ngủ/đóng băng)


async def _restart_feed_and_alert(feed) -> None:
    """Brief 2026-09-01 (dot 3) Task C: chi kêu "forcing reconnect" khi
    feed.restart() that su disconnect duoc stream (tra True). Khi _stream None
    (feed chua tung nối, dang trong backoff) restart la no-op — kêu luc do la
    chuong mo ta hanh dong khong xay ra (H2)."""
    if await feed.restart():
        alert("WARN", "feed stale, forcing reconnect")


def held_symbols_for_pricing(storage, cfg) -> list[str]:
    """MARGIN-2: ma DANG NAM GIU can gia tuoi de tinh NAV, tru ma da co trong
    cfg.symbols (luot backfill truoc da keo day du).

    Doc MOI tai khoan trong cfg.ssi_equity_accounts chu khong chi
    real_order_account: quyet dinh chon tai khoan CHUA chot, va NAV duoc tinh
    cho tung tai khoan. SYNC-1: mot tai khoan doc loi -> WARN + bo qua, khong
    giet cac tai khoan con lai (dung bug e20e647 da tung xoa so 0434226).
    Sap xep de thu tu on dinh giua cac lan chay."""
    held: set[str] = set()
    for account_no in cfg.ssi_equity_accounts:
        try:
            positions = storage.read_real_positions(account_no)
        except Exception as e:
            alert(
                "WARN",
                "khong doc duoc vi the de lay ma can dinh gia, bo qua tai khoan",
                account_no=account_no,
                error=f"{type(e).__name__}: {e}"[:100],
            )
            continue
        held.update(sym for sym, pos in positions.items() if pos.qty > 0)
    return sorted(held - set(cfg.symbols))


def _install_stop_handlers(stop_event: asyncio.Event) -> None:
    """Bắt SIGTERM/SIGINT -> set stop_event để các vòng lặp dừng sạch.

    Windows (nơi dev): loop.add_signal_handler ném NotImplementedError — fallback
    sang signal.signal (chỉ thật sự hữu dụng trên Linux, nơi sản xuất chạy)."""

    def _on_signal(*_args):
        stop_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _on_signal)
    except NotImplementedError:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _on_signal)


async def persist_bars(
    storage,
    pub,
    bars,
    interval: timedelta = timedelta(minutes=5),
) -> None:
    """Publish NATS trước + ghi DB sau. KHÔNG BAO GIỜ ném: hàm này được gọi qua
    asyncio.create_task() fire-and-forget, exception thoát ra sẽ bị asyncio nuốt
    thành 'Task exception was never retrieved' — bar mất mà không ai biết."""
    if not bars:
        return
    try:
        for b in bars:
            await pub.publish(b)
        publish_done_at = datetime.now(TZ)
    except Exception as e:
        alert(
            "CRITICAL",
            "bar publish failed, bars dropped (not delivered to engine)",
            error=f"{type(e).__name__}: {e}"[:200],
            symbols=[b.symbol for b in bars],
            ts=[b.ts.isoformat() for b in bars],
        )
        return

    try:
        storage.write_bars(bars)
    except Exception as e:
        alert(
            "CRITICAL",
            "bar db persist failed, bars already published to engine (db missing)",
            error=f"{type(e).__name__}: {e}"[:200],
            symbols=[b.symbol for b in bars],
            ts=[b.ts.isoformat() for b in bars],
        )
        return

    max_close_ts = max(b.ts for b in bars) + interval
    lag_ms = round((publish_done_at - max_close_ts).total_seconds() * 1000, 2)
    alert(
        "INFO",
        "bars closed",
        n=len(bars),
        symbols=[b.symbol for b in bars],
        lag_ms=lag_ms,
    )


async def persist_snapshot(storage, bar) -> None:
    """Ghi DB duy nhất cho snapshot nến đang chạy (upsert, không publish NATS)."""
    try:
        storage.write_bars([bar])
    except Exception as e:
        alert(
            "WARN",
            "snapshot write failed",
            error=f"{type(e).__name__}: {e}"[:200],
            symbol=bar.symbol,
            ts=bar.ts.isoformat(),
        )


def make_stream_message_handler(wd, storage, pub, persist_tasks=None, latch=None):
    """Callback cho AsyncStream.streaming.on_data. Một message dị dạng không
    được ném ngược vào vòng stream của SDK. `persist_tasks` (set, tuỳ chọn):
    theo dõi task persist_bars fire-and-forget để shutdown chờ chúng xong.
    `latch` (BarLatch, tuỳ chọn): lọc chỉ publish nến đã đóng ra NATS."""
    if latch is None:
        latch = BarLatch()

    def on_stream_message(msg):
        try:
            bar = parse_interval_message(msg)
        except Exception as e:
            alert(
                "WARN",
                "failed to parse stream message, skipping",
                error=f"{type(e).__name__}: {e}"[:200],
            )
            return
        if bar is not None:
            wd.beat()
            now = datetime.now(TZ)
            late_ms = (now - (bar.ts + latch.interval)).total_seconds() * 1000
            if late_ms > 0:
                alert(
                    "INFO",
                    "late snapshot",
                    symbol=bar.symbol,
                    bar_ts=bar.ts.isoformat(),
                    late_ms=round(late_ms, 2),
                )
            task_snap = asyncio.create_task(persist_snapshot(storage, bar))
            if persist_tasks is not None:
                persist_tasks.add(task_snap)
                task_snap.add_done_callback(persist_tasks.discard)

            closed = latch.offer(bar)
            if closed is not None:
                task = asyncio.create_task(
                    persist_bars(storage, pub, [closed], interval=latch.interval)
                )
                if persist_tasks is not None:
                    persist_tasks.add(task)
                    task.add_done_callback(persist_tasks.discard)
        # Index streaming (VNINDEX/VN30): không có nguồn dữ liệu real-time nào
        # trong ssi-sdk hiện tại — xem PLAN_INDEX_STREAMING.md (điều tra thật
        # 2026-08-07). Không viết IndexValue cho tới khi có nguồn dữ liệu khác.

    return on_stream_message


@dataclass
class HousekeepingState:
    eod_done_for: date | None = None
    last_account_sync: datetime | None = None
    last_monotonic: float | None = None
    last_wall: datetime | None = None


async def housekeeping_tick(
    cfg,
    storage,
    wd,
    state: HousekeepingState,
    latch: BarLatch | None = None,
    pub: BarPublisher | None = None,
    persist_tasks: set[asyncio.Task] | None = None,
) -> None:
    """Một vòng housekeeping. Được phép ném — housekeeping_loop chịu trách nhiệm bắt.

    Phát hiện gián đoạn/máy chủ ngủ: So sánh độ trôi giữa time.monotonic() và datetime.now(TZ).
    LƯU Ý GIỚI HẠN: Đây là phát hiện sau sự việc (post-factum detection), không phải phòng ngừa.
    Khi máy đang ngủ thì toàn bộ tiến trình đóng băng nên không thể phát cảnh báo trong lúc ngủ.
    """
    wd.check()
    # WARM-1 Viec B: timeout=5 thay vi 30s mac dinh — khi DB chet, tick that bai
    # NHANH (5s + sleep 30s = ~35s phuc hoi heartbeat thay vi ~90s truoc; chu du
    # an khong ha timeout toan cuc vi _get_pool la CRITICAL). Mac dinh None giu
    # nguyen hanh vi cho moi caller khac.
    storage.beat("collector", timeout=5)

    cur_mono = time.monotonic()
    now = datetime.now(TZ)

    if state.last_monotonic is not None and state.last_wall is not None:
        delta_wall = (now - state.last_wall).total_seconds()
        delta_mono = cur_mono - state.last_monotonic
        drift = delta_wall - delta_mono
        if drift >= CLOCK_DRIFT_THRESHOLD_SECONDS:
            holidays = getattr(cfg, "holidays", frozenset())
            in_session = is_trading_time(now, holidays) or is_trading_time(state.last_wall, holidays)
            session_str = "trong giờ giao dịch" if in_session else "ngoài giờ giao dịch"
            alert(
                "CRITICAL",
                f"phát hiện máy chủ ngủ/gián đoạn {drift:.0f}s ({session_str}) từ {state.last_wall.strftime('%H:%M:%S')} đến {now.strftime('%H:%M:%S')}",
                dead_seconds=round(drift, 1),
                from_ts=state.last_wall.isoformat(),
                to_ts=now.isoformat(),
                in_trading_hours=in_session,
            )
    state.last_monotonic = cur_mono
    state.last_wall = now

    if latch is not None and pub is not None:
        due = latch.flush_due(now)
        if due:
            task = asyncio.create_task(
                persist_bars(storage, pub, due, interval=latch.interval)
            )
            if persist_tasks is not None:
                persist_tasks.add(task)
                task.add_done_callback(persist_tasks.discard)
    if state.last_account_sync is None or now - state.last_account_sync >= timedelta(
        minutes=5
    ):
        state.last_account_sync = now
        try:
            await sync_account_data(cfg, storage)
        except Exception as e:
            alert("WARN", "account sync failed, skipping", error=str(e)[:100])
        try:
            await sync_derivative_data(cfg, storage)
        except Exception as e:
            alert("WARN", "derivative sync failed, skipping", error=str(e)[:100])
    if (now.hour, now.minute) >= (
        EOD_HOUR,
        EOD_MINUTE,
    ) and state.eod_done_for != now.date():
        state.eod_done_for = now.date()
        eod_client = SSIRestClient(cfg, storage)
        try:
            counts = await run_backfill(storage, eod_client, cfg.symbols, now.date())
            alert("INFO", "eod backfill done", counts=counts)
            # MARGIN-2: ma DANG NAM GIU khong nam trong cfg.symbols nen khong co
            # duong nao cap nhat gia cho chung — do that 14/08: CAP/HCM/SSI/TCX
            # bar cuoi 06/08, tut ra ngoai cua so 5 ngay cua compute_nav nen NAV
            # tinh chung bang 0 va hut ~55%. Chi keo DAILY: chung khong giao
            # dich, NAV chi can gia dong cua.
            held = held_symbols_for_pricing(storage, cfg)
            if held:
                held_counts = await run_backfill(
                    storage, eod_client, held, now.date(), daily_only=True
                )
                alert("INFO", "eod held-symbol pricing done", counts=held_counts)
        finally:
            await eod_client.close()


async def housekeeping_loop(
    cfg,
    storage,
    wd,
    sleep_seconds: float = 30.0,
    max_ticks: int | None = None,
    stop_event: asyncio.Event | None = None,
    latch: BarLatch | None = None,
    pub: BarPublisher | None = None,
    persist_tasks: set[asyncio.Task] | None = None,
) -> None:
    """Vòng housekeeping vô hạn. Một lỗi (vd Postgres restart) KHÔNG được giết
    collector — bắt hết, alert WARN, rồi chạy tiếp vòng sau.
    `max_ticks` chỉ dùng cho test, cùng pattern với run(max_messages) của engine.
    `stop_event` (SIGTERM): dừng sạch sau vòng hiện tại."""
    if stop_event is None:
        stop_event = asyncio.Event()
    state = HousekeepingState()
    ticks = 0
    while not stop_event.is_set() and (max_ticks is None or ticks < max_ticks):
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
        except TimeoutError:
            pass  # hết khoảng chờ bình thường, chạy tick
        # Bug đo thật: wait_for trả về BÌNH THƯỜNG (không ném TimeoutError) khi
        # stop được set giữa lúc chờ -> KHÔNG được rơi xuống tick (tick có thể
        # là EOD backfill job SSI dài — chạy giữa lúc đang tắt máy).
        if stop_event.is_set():
            break
        try:
            await housekeeping_tick(
                cfg,
                storage,
                wd,
                state,
                latch=latch,
                pub=pub,
                persist_tasks=persist_tasks,
            )
        except Exception as e:
            alert(
                "WARN",
                "housekeeping tick failed, continuing",
                error=f"{type(e).__name__}: {e}"[:200],
            )
        ticks += 1


async def run(cfg, stop_event: asyncio.Event | None = None) -> None:
    if stop_event is None:
        stop_event = asyncio.Event()
        _install_stop_handlers(stop_event)

    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()
    persist_tasks: set[asyncio.Task] = set()
    latch = BarLatch(
        interval_seconds=cfg.bar_interval_minutes * 60,
        grace_seconds=60,
    )

    alert("INFO", "backfill start")
    client = SSIRestClient(cfg, storage)
    try:
        counts = await run_backfill(
            storage, client, cfg.symbols, datetime.now(TZ).date()
        )
        alert("INFO", "backfill done", counts=counts)
    except Exception as e:
        alert("WARN", "backfill failed, skipping", error=str(e)[:100])
        counts = {}
    finally:
        await client.close()

    def _on_stale():
        # Brief 2026-09-01 (dot 3) Task C: restart() tra True chi khi that su
        # disconnect duoc stream. Khi _stream None (feed chua tung nối, dang
        # trong backoff) thi restart khong lam gi — kêu "forcing reconnect" luc
        # do la chuong mo ta hanh dong khong xay ra (H2). Keu dung viec da lam.
        asyncio.create_task(_restart_feed_and_alert(feed))

    wd = Watchdog(
        cfg.watchdog_stale_seconds,
        cfg.watchdog_max_failures,
        now_fn=lambda: datetime.now(TZ),
        is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays),
        on_stale=_on_stale,
        on_critical=lambda: alert("CRITICAL", "feed stale beyond max failures"),
    )

    feed = SSIFeed(
        cfg,
        storage,
        on_message=make_stream_message_handler(wd, storage, pub, persist_tasks, latch=latch),
    )
    feed.start()

    try:
        await housekeeping_loop(
            cfg,
            storage,
            wd,
            stop_event=stop_event,
            latch=latch,
            pub=pub,
            persist_tasks=persist_tasks,
        )
    finally:
        await feed.stop()
        remaining = latch.flush_all()
        if remaining:
            try:
                storage.write_bars(remaining)
                for b in remaining:
                    await pub.publish(b)
                alert("INFO", "flushed remaining bars at shutdown", count=len(remaining))
            except Exception as e:
                alert("WARN", "failed to flush remaining bars at shutdown", error=str(e)[:100])
        if persist_tasks:
            _, pending = await asyncio.wait(persist_tasks, timeout=10)
            if pending:
                alert(
                    "WARN",
                    "persist tasks still running at shutdown",
                    count=len(pending),
                )
        await pub.close()


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
    # log `logger.info("Connecting to WebSocket with headers: %s", self._headers)`
    # — self._headers chứa `Authorization: Bearer <token>` plaintext (token sống
    # 15 phút nhưng log được giữ lâu hơn). Nâng level logger NÀY lên WARNING
    # (không phải filter regex — một dòng setLevel giải quyết trọn vẹn, regex
    # phải bảo trì và hỏng lặng lẽ khi SDK đổi format). Đánh đổi: mất dòng
    # INFO "WebSocket connected to wss://..." — chấp nhận vì lỗi kết nối vẫn
    # hiện ("SSIFeed connection error") và collector có heartbeat riêng trong
    # bảng heartbeat. KHÔNG đụng logger ssi_sdk.services.token_manager — nó log
    # "Token refreshed successfully", hữu ích và không chứa secret.
    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    _configure_logging()
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
