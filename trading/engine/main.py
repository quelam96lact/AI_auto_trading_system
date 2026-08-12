import argparse
import asyncio
import json
import logging
import signal

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy

from trading import real_orders
from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.engine.logic import bar_from_payload, process_bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager

CAPITAL = 100_000_000.0


def _install_stop_handlers(stop_event: asyncio.Event) -> None:
    """Bắt SIGTERM/SIGINT -> set stop_event để vòng lặp thoát ở ranh giới message.

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


async def run(
    cfg: Config, max_messages: int | None = None, stop_event: asyncio.Event | None = None
) -> None:
    if stop_event is None:
        stop_event = asyncio.Event()
        _install_stop_handlers(stop_event)

    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    state = storage.read_engine_state()
    positions = storage.read_positions()
    if state is None:
        broker = PaperBroker(CAPITAL)
        alert("INFO", "engine starting fresh", capital=CAPITAL)
    else:
        cash, realized_pnl = state
        broker = PaperBroker.restore(CAPITAL, cash, realized_pnl, positions)
        alert(
            "INFO",
            "engine restored state",
            cash=cash,
            realized_pnl=realized_pnl,
            positions={s: p.qty for s, p in positions.items()},
        )

    strategy = SmaCrossStrategy()
    risk = RiskManager(capital=CAPITAL)
    trailing_stop = TrailingStopManager()
    # Tai dung _highest cho vi the dang mo sau restart (bug RESTORE-1 Task A):
    # _highest la dict in-memory, mat sau restart -> trailing stop vo hieu hoa
    # vinh vien im lang. Khong tai dung duoc -> alert WARN, khong duoc im lang.
    for sym, pos in positions.items():
        if pos.qty > 0:
            highest = storage.read_highest_since_buy(sym)
            if highest is not None:
                trailing_stop.on_position_opened(sym, highest)
            else:
                alert(
                    "WARN",
                    f"khong tai dung duoc trailing stop cho {sym}: khong co BUY "
                    f"fill hoac khong co bar tu luc vao lenh — vi the nay DANG "
                    f"KHONG co trailing stop",
                )
    real_risk = RiskManager(capital=cfg.real_order_capital)
    real_risk.halted_date = storage.read_real_risk_halt()
    marks: dict[str, float] = {}
    day_state: dict = {}

    nc = await nats.connect(cfg.nats_url)
    js = nc.jetstream()
    sub = await js.subscribe(
        "bars.>",
        durable="engine",
        stream=cfg.nats_stream,
        config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
    )

    def persist_fills(fills) -> None:
        for fill in fills:
            storage.upsert_position(broker.positions[fill.symbol])
            storage.write_engine_state(broker.cash, broker.realized_pnl)
            storage.write_order(fill)
            storage.update_pnl_daily(
                fill.ts.astimezone(TZ).date(),
                fill.pnl or 0.0,
                fill.fee,
                broker.unrealized_pnl(marks),
            )
            alert(
                "INFO",
                "order filled",
                symbol=fill.symbol,
                side=fill.side,
                qty=fill.qty,
                price=fill.price,
                pnl=fill.pnl,
            )

    def expire_stale_real_orders() -> None:
        n = storage.expire_stale_pending_orders()
        if n > 0:
            alert("WARN", "real pending orders expired without confirmation", count=n)

    def on_real_crossover(crossover, bar) -> None:
        real_orders.handle_crossover(cfg, storage, real_risk, crossover, bar)

    def idle_maintenance() -> None:
        """expire + heartbeat, không được để lỗi DB tạm thời giết engine."""
        try:
            expire_stale_real_orders()
            storage.beat("engine")
        except Exception as e:
            alert(
                "WARN",
                "engine maintenance failed, continuing",
                error=f"{type(e).__name__}: {e}"[:200],
            )

    processed = 0
    try:
        while not stop_event.is_set() and (
            max_messages is None or processed < max_messages
        ):
            # Đua next_msg với stop_event: SIGTERM lúc engine đang RẢNH phải
            # thoát ngay (không chờ hết timeout 60s của next_msg) — bug đo thật:
            # check stop ở đầu vòng rồi block trong next_msg làm engine mất 58s
            # nhận ra lệnh dừng, vượt grace 10s của docker stop -> SIGKILL, và
            # trong 10s grace engine vẫn xử lý message mới -> ghi DB chưa ack
            # -> JetStream giao lại -> lệnh trùng. Hủy next_msg khi chưa xử lý
            # là AN TOÀN: chưa ack -> JetStream giao lại, không mất không trùng.
            next_task = asyncio.ensure_future(sub.next_msg(timeout=60))
            stop_task = asyncio.ensure_future(stop_event.wait())
            done, _ = await asyncio.wait(
                {next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if stop_task in done:
                next_task.cancel()
                # Chờ task kết thúc và nuốt exception của nó (CancelledError
                # lẫn ConnectionClosedError khi finally: nc.close() đóng
                # connection lúc task vẫn đang chờ) — nếu không, asyncio in
                # "Task exception was never retrieved" ở MỌI lần shutdown
                # bình thường, tập cho người vận hành thói quen bỏ qua
                # traceback. Logic huỷ giữ nguyên: chưa ack -> JetStream giao
                # lại, không mất không trùng (comment dòng 131-137).
                try:
                    await next_task
                except (asyncio.CancelledError, Exception):
                    pass  # nuốt — task chỉ chạy next_msg, không có lỗi thật nào đáng giữ
                break
            stop_task.cancel()  # next_msg thắng — hủy waiter, không để rò rỉ
            try:
                msg = next_task.result()
            except nats.errors.TimeoutError:
                idle_maintenance()
                continue
            try:
                bar = bar_from_payload(json.loads(msg.data))
                was_halted = risk.halted_date
                was_real_halted = real_risk.halted_date
                fills = process_bar(
                    bar,
                    broker,
                    strategy,
                    risk,
                    trailing_stop,
                    marks,
                    day_state,
                    on_crossover=on_real_crossover,
                )
                persist_fills(fills)
                if risk.halted_date is not None and risk.halted_date != was_halted:
                    alert(
                        "CRITICAL",
                        "risk halt: max daily loss reached",
                        date=str(risk.halted_date),
                    )
                if (
                    real_risk.halted_date is not None
                    and real_risk.halted_date != was_real_halted
                ):
                    storage.save_real_risk_halt(real_risk.halted_date)
                    alert(
                        "CRITICAL",
                        "REAL risk halt: max daily loss reached",
                        date=str(real_risk.halted_date),
                    )
                await msg.ack()
            except Exception as e:
                # term() chứ không nak(): broker là state in-memory đã bị
                # process_bar mutate, và write_order() là INSERT thuần không
                # idempotent — redeliver sẽ ghi trùng lệnh + tính trùng PnL.
                # Bỏ 1 nến an toàn hơn vào lệnh nhân đôi. Xem plan P0 Task 1.
                alert(
                    "CRITICAL",
                    "engine failed to process bar, message dropped",
                    error=f"{type(e).__name__}: {e}"[:200],
                    payload=msg.data.decode("utf-8", "replace")[:200],
                )
                await msg.term()
            idle_maintenance()
            processed += 1
    finally:
        await nc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
