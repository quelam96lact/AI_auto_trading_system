import argparse
import asyncio
import json
import logging
import signal
from datetime import datetime

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
    cfg: Config,
    max_messages: int | None = None,
    stop_event: asyncio.Event | None = None,
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
    # WARM-UP (rui ro 5 GO_LIVE_AUDIT, WARM-1): nap lich su SMA/ATR tu bang
    # bars luc khoi dong. Consumer engine la DURABLE: sau lan chay dau no tiep
    # tuc tu vi tri cu chu khong phat lai tu dau — khong nap thi engine mu
    # ~1h45' (21 bar 5 phut) va IM LANG. Nap bang compute_crossover() (chi cap
    # nhat state ky thuat MA+ATR, KHONG qua broker/khong sinh lenh — tuyet doi
    # khong dung process_bar cho bar lich su). So bar do CHINH CHIEN LUOC quyet
    # (warmup_bars) — khong hardcode, ai do doi atr_period thi so bar theo.
    warmed_until: dict[str, datetime] = {}
    for sym in cfg.symbols:
        hist = storage.read_last_bars(sym, strategy.warmup_bars)
        if len(hist) < strategy.warmup_bars:
            alert(
                "WARN",
                f"warm-up {sym} thieu lich su: chi co {len(hist)}/"
                f"{strategy.warmup_bars} bar trong bang bars — ma nay VAN DANG MU",
                symbol=sym,
            )
            continue
        for hb in hist:
            strategy.compute_crossover(hb)
        warmed_until[sym] = hist[-1].ts
        alert(
            "INFO",
            f"warm-up {sym} xong",
            bars=len(hist),
            until=str(hist[-1].ts),
        )
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
    real_trailing_stop = TrailingStopManager()
    # Tai dung _highest cho vi the THAT sau restart (RTS-1), giong luong paper
    # o tren: doc tu real_order_fills (loc account_no). Vi the that co the do
    # chu tai khoan TU MUA ngoai he thong -> khong co fill -> khong tai dung
    # duoc -> alert WARN neu ro ma, KHONG im lang.
    for sym, rpos in storage.read_real_positions(cfg.real_order_account).items():
        if rpos.qty > 0:
            rhighest = storage.read_real_highest_since_buy(cfg.real_order_account, sym)
            if rhighest is not None:
                real_trailing_stop.on_position_opened(sym, rhighest)
            else:
                alert(
                    "WARN",
                    f"khong tai dung duoc trailing stop cho vi the that {sym}: "
                    f"khong co BUY fill trong real_order_fills (co the mua ngoai "
                    f"he thong) — vi the nay DANG KHONG co trailing stop",
                )
    # GUARD-1: kiem tra duong dat lenh that co that su co the sinh lenh BUY
    # khong. Tran gia tri lenh = real_order_capital * max_order_value_pct; neu
    # khong du mua noi 1 lo 100 cp cua ma re nhat trong cfg.symbols (gia dong
    # gan nhat) -> alert CRITICAL noi ro: duong lenh that INERT. CHI canh bao,
    # khong chan engine — luong paper van chay dung va van co gia tri; van de
    # goc la IM LANG, khong phai thieu che tai. Khong lay duoc gia nao (bang
    # rong) -> bo qua im lang: khong the ket luan, canh bao sai lam nhon canh
    # bao that.
    # CHI chay khi real_trading_enabled=True (sua GUARD-2): chủ dự án CO Y
    # giu real_order_capital=21459 de khoa duong lenh that — khi trading tat,
    # tran nho la TRANG THAI MONG MUON, canh bao moi lan khoi dong chi la
    # nhieu (cai bay NOISE-1). Gia tri that nam o luc ai do bat
    # real_trading_enabled=true ma quen cap nhat capital.
    if cfg.real_trading_enabled:
        order_cap = cfg.real_order_capital * real_risk.max_order_value_pct
        cheapest: float | None = None
        for sym in cfg.symbols:
            close = storage.read_last_close(sym)
            if close is not None and (cheapest is None or close < cheapest):
                cheapest = close
        if cheapest is not None and order_cap < cheapest * 100:
            alert(
                "CRITICAL",
                f"duong dat lenh that INERT: tran gia tri lenh {order_cap:,.0f} VND "
                f"khong du mua 1 lo 100 cp cua ma re nhat ({cheapest:,.0f} VND/cp = "
                f"{cheapest * 100:,.0f} VND/lo) trong cfg.symbols — se khong bao "
                f"gio sinh lenh BUY",
            )
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
                # CHONG NAP TRUNG (WARM-1 muc 4): consumer engine la DURABLE —
                # khi restart, JetStream giao lai cac bar CHUA ACK. Nhung bar
                # do cung nam trong bang bars (COLLECTOR ghi, engine khong ghi)
                # nen vua duoc warm-up nap. Khong chan thi cung mot bar vao
                # _closes HAI LAN, lech cua so MA — bien chien luoc "mu" thanh
                # chien luoc "SAI", te hon bug dang sua. Bo qua toan bo xu ly
                # bar ts <= warmed_until (van ack: state da phan anh no roi).
                if bar.ts <= warmed_until.get(
                    bar.symbol, datetime.min.replace(tzinfo=bar.ts.tzinfo)
                ):
                    await msg.ack()
                    processed += 1  # bar da xu ly (state da phan anh) — dem vao, khong thi loop cho message khong ton tai
                    continue
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
                # Trailing stop luong THAT (RTS-1): canh bao cham stop moi bar —
                # KHONG phai stop-loss tu dong, chi sinh lenh SELL cho xac
                # nhan (nguoi van hanh bam nut qua confirm_real_order.py).
                real_orders.handle_stop_touch(
                    cfg,
                    storage,
                    bar,
                    strategy.last_atr(bar.symbol),
                    real_trailing_stop,
                )
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
