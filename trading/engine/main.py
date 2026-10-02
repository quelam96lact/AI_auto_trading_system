import argparse
import asyncio
import json
import logging
import signal
from datetime import date, datetime, time, timedelta

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy

from trading import real_orders
from trading.alerts import alert, start_outbox
from trading.calendar_vn import (
    CONTINUOUS_SESSIONS,
    TZ,
    is_trading_day,
    market_minutes_between,
    previous_trading_day,
)
from trading.config import Config, load_config
from trading.data_quality import is_dirty_bar
from trading.engine.logic import bar_from_payload, process_bar
from trading.logging_setup import attach_durable_alert_handler
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.strategy import RestoresTakeProfit, Strategy
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


def _default_strategy() -> Strategy:
    """Chien luoc engine chay THAT.

    04/09: doi tu SmaCrossStrategy sang octopus theo quyet dinh chu du an. Lan
    dau octopus chay that — truoc goi B1 no chet ngay bar dau vi thieu
    last_crossover, ma logic.py:44 goi KHONG dieu kien.

    warmup_bars nhay 21 -> 201 bar 5 phut (EMA trend 200 + 1). Da do 04/09
    truoc khi doi: HII 3.211 / IJC 4.719 / AAA 4.597 bar trong bang bars — du
    xa. Them ma moi vao cfg.symbols thi ma do bao "VAN DANG MU" o main.py cho
    den khi du 201 bar — canh bao that, khong phai nhieu.

    LUA CHON NAY CHUA CO PHEP DO UNG HO — doc truoc khi dua vao no.
    research/2026-09-01-strategy-comparison-v2.md do tren ro da loc 1.308 ma
    (bieu phi VN, T+2,5): octopus_pullback -1.615.319.902 tren 1.514 lenh.
    Ket luan §3 cua bao cao do: khong chien luoc nao trong ba chien luoc thang
    mua-va-giu tren ro da loc. Diem sang MaxDD 2,0% / thang 56% chi do tren DUNG
    BA ma (VCB, HPG, TCB, 25 lenh) — co mau lon mau thuan voi co mau nho.

    Engine dang chay PAPER nen chi phi bang 0. Nhung neu ai do dinh bat
    real_trading_enabled: doc them muc J (octopus khong bao gio phat "bear" nen
    duong lenh that chi MUA, khong bao gio BAN).

    05/09: phat hien "engine dang CAM" — min_avg_value_20 = 2 ty bi tinh binh
    quan tren N BAR thay vi N NGAY, nen tren bar 5 phut no thanh nguong cao gap
    ~78 lan y dinh. HII 0/3.211 bar mo cong, AAA 0/4.597, IJC 24/4.719 => 0 tin
    hieu "bull".

    06/09 (goi K): DA SUA — DailyLiquidityTracker gop gia tri giao dich theo
    ngay giao dich truoc khi lay binh quan (xem octopus_pullback.py). Tai hien
    dung bit-for-bit bang khung ngay cu (-1.615.319.902 / 1.514 lenh / 439 ma)
    sau khi sua — chi don vi thoi gian cua cua so sai, khong phai cong thuc.

    Do lai tren bang `bars` that sau khi sua (05/09→06/09):
    IJC 0→6 tin hieu bull, AAA 0→6, nhung HII VAN 0 bull (cong thanh khoan da
    mo 41,8% — khong con la loi don vi, la vi dieu kien EMA/MACD/pullback cua
    chinh HII chua khop trong lich su co). Chay lai
    `scripts/check_silent_engine.py` de xem trang thai hien tai — DUNG doc
    dong nay nhu "da het cam hoan toan", HII van bi chuong CRITICAL flag.

    Con so -1.615.319.902 van mo ta khung NGAY (10 nam), khac voi so do duoc
    tren khung 5 phut ma engine that su chay (xem
    docs/superpowers/research/2026-09-06-master-audit-report-dot-6.md).
    """
    return OctopusPullbackStrategy()


def count_warmup_gap(
    warmed_until: datetime,
    first_live_ts: datetime,
    bar_interval_minutes: int,
    holidays: frozenset,
) -> int:
    """Đếm số nến bị nhảy cóc giữa mốc warm-up và nến live đầu tiên.

    Dùng CONTINUOUS_SESSIONS (09:15-11:30, 13:00-14:30) để bỏ qua nghỉ trưa,
    cuối tuần, ngày lễ, và đặc biệt nến ATC (14:45 nằm ngoài CONTINUOUS_SESSIONS).

    Công thức: market_minutes_between(warmed_until + step, first_live_ts) / step
    - Nếu warmed_until là nến ATC (14:45), warmed_until+step = 14:50 nằm sau
      14:30 kết thúc CONTINUOUS — phần thứ Sáu = 0, tính đúng từ 09:15 thứ Hai.
    - Nếu liền mạch (ví dụ 11:20 → 11:25), trả về 0 (không báo động giả).

    Trả về: số nguyên nến thiếu (0 = liền mạch, >= 1 = có lỗ).
    """
    step = timedelta(minutes=bar_interval_minutes)
    mins = market_minutes_between(
        warmed_until + step,
        first_live_ts,
        holidays=holidays,
        sessions=CONTINUOUS_SESSIONS,
    )
    return round(mins / bar_interval_minutes)


# Nến cuối phiên có ts = 14:45 nhưng chỉ đóng lúc 14:50, và collector cần thêm
# chút thời gian để ghi. 15:00 là 14:45 + một nến + biên.
# Không dùng STREAM_COVERAGE_READY_TIME (15:25) của check_golive_gate.py vì con số
# đó gắn liền với thời điểm job stream-health chạy lúc 15:10, lý do hoàn toàn khác.
SESSION_DATA_READY_TIME = time(15, 0)


def last_session_date_needed(
    now: datetime, holidays: frozenset = frozenset()
) -> date:
    """Ngày của phiên giao dịch gần nhất mà DB PHẢI có nến, tính tại thời điểm now.

    Quy tắc (dùng lại is_trading_day từ trading.calendar_vn):
    - Nếu hôm nay là ngày giao dịch VN VÀ now >= 15:00 VN: phiên hôm nay đã xong
      và collector đã có đủ thời gian ghi dữ liệu -> trả về hôm nay.
    - Ngược lại (chưa tới 15:00, hoặc cuối tuần, hoặc ngày lễ): lùi về ngày giao
      dịch gần nhất trước đó.
    """
    now_vn = now.astimezone(TZ)
    current_date = now_vn.date()
    if is_trading_day(current_date, holidays) and now_vn.time() >= SESSION_DATA_READY_TIME:
        return current_date
    return previous_trading_day(current_date, holidays)


async def run(
    cfg: Config,
    max_messages: int | None = None,
    stop_event: asyncio.Event | None = None,
    strategy: Strategy | None = None,
    warmup_wait_timeout_sec: float = 600.0,
    warmup_wait_sleep=asyncio.sleep,
    warmup_wait_interval_sec: float = 5.0,
    now: datetime | None = None,
) -> None:
    """`strategy=None` (mac dinh) = chien luoc chay THAT, xem _default_strategy().

    Khe nay co tu 04/09 khi doi sang octopus: cac test duong ong engine
    (test_engine_main.py) kiem warm-up / khoi phuc trang thai / noi lenh that,
    khong kiem chien luoc — nhung chung ngam phu thuoc warmup_bars = 21 cua
    sma_cross, nen doi chien luoc lam sau test do voi ly do khong lien quan gi
    den thu chung kiem. Chung ghim sma_cross qua tham so nay; con lua chon chay
    that duoc ghim rieng boi test_default_strategy_la_octopus.
    """
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
        buy_dates: dict[str, date] = {}
        for sym, pos in positions.items():
            if pos.qty > 0:
                buy_date = storage.read_last_buy_date(sym)
                if buy_date is not None:
                    buy_dates[sym] = buy_date
                else:
                    alert(
                        "WARN",
                        f"khong tim thay ngay mua cho {sym}: vi the se bi khoa "
                        f"3 ngay giao dich theo cach bao thu (day_index=0)",
                    )
        broker = PaperBroker.restore(
            CAPITAL,
            cash,
            realized_pnl,
            positions,
            buy_dates=buy_dates,
            holidays=frozenset(cfg.holidays),
        )
        alert(
            "INFO",
            "engine restored state",
            cash=cash,
            realized_pnl=realized_pnl,
            positions={s: p.qty for s, p in positions.items()},
        )

    strategy = _default_strategy() if strategy is None else strategy
    # CHỜ ĐỦ DỮ LIỆU PHIÊN GẦN NHẤT TRƯỚC KHI WARM-UP (Brief 81 Task 2):
    # Tránh sự cố warm-up trước khi collector backfill xong (tối 23/09).
    # Chờ cho tới khi mọi mã trong cfg.symbols đều có nến của needed_date trong DB.
    # So sánh ở mức NGÀY (date >= needed_date), không so ở mức nến để tránh báo động giả
    # khi mã thiếu nến lẻ do không có giao dịch trong phiên.
    current_now = now if now is not None else datetime.now(TZ)
    needed_date = last_session_date_needed(current_now, cfg.holidays)
    waited_sec = 0.0
    while True:
        missing_symbols = []
        for sym in cfg.symbols:
            lts = storage.last_bar_ts(sym)
            if lts is None or lts.astimezone(TZ).date() < needed_date:
                missing_symbols.append(sym)
        if not missing_symbols:
            if waited_sec > 0:
                alert(
                    "INFO",
                    "da co du lieu bars cho phien gan nhat sau khi cho",
                    needed_date=str(needed_date),
                    waited_sec=waited_sec,
                )
            break
        if waited_sec >= warmup_wait_timeout_sec:
            alert(
                "CRITICAL",
                "het thoi gian cho du lieu bars truoc warm-up — van chay tiep",
                missing_symbols=missing_symbols,
                needed_date=str(needed_date),
                timeout_sec=warmup_wait_timeout_sec,
            )
            break
        await warmup_wait_sleep(warmup_wait_interval_sec)
        waited_sec += warmup_wait_interval_sec

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
        # DIRTY-1 (brief dot 108): bo nen rac khoi lich su TRUOC khi nap. Bar gia
        # 0 lam ATR(14) nhay tu ~20 len ~2.100 va keo EMA ve 0 (dot 107 da do),
        # tuc chien luoc "nong" bang so rac ngay tu luc khoi dong.
        clean_hist = [b for b in hist if not is_dirty_bar(b)]
        if len(clean_hist) != len(hist):
            alert(
                "INFO",
                f"warm-up {sym}: bo {len(hist) - len(clean_hist)} bar rac "
                f"(co gia <= 0) khoi lich su",
                symbol=sym,
                so_bar_rac=len(hist) - len(clean_hist),
                con_lai=len(clean_hist),
            )
        if len(clean_hist) < strategy.warmup_bars:
            alert(
                "WARN",
                f"warm-up {sym} thieu lich su: chi co {len(clean_hist)}/"
                f"{strategy.warmup_bars} bar trong bang bars — ma nay VAN DANG MU",
                symbol=sym,
            )
            continue
        for hb in clean_hist:
            strategy.compute_crossover(hb)
        warmed_until[sym] = clean_hist[-1].ts
        alert(
            "INFO",
            f"warm-up {sym} xong",
            bars=len(clean_hist),
            until=str(clean_hist[-1].ts),
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
    # TAI DUNG TP CHO CHIEN LUOC KHAI BAO DUOC (brief dot 107): `_tp` la dict
    # in-memory nen sau restart no rong, va bar dau tien thay vi the se NEO LAI TP
    # theo gia mo cua HOM DO (octopus_pullback.py:217-223) — gia da giam thi lenh
    # "chot loi" thanh ban lo duoi gia von, khong canh bao. Tai dung dung cong thuc
    # luong song da dung: TP = open bar neo A + tp_atr_mult * ATR_A, voi A la bar
    # dau tien `strategy.on_bar` thay held > 0 (logic.py:36 nap broker TRUOC
    # logic.py:44 goi strategy -> A CHINH LA bar cua fill). Tai dung duoc hay khong
    # deu phai noi ra: WARN khi thieu BUY/bar, khong bao gio im lang.
    # Kiem bang isinstance tren Protocol RestoresTakeProfit, KHONG dung hasattr.
    if isinstance(strategy, RestoresTakeProfit):
        for sym, pos in positions.items():
            if pos.qty <= 0:
                continue
            fill = storage.read_last_buy_fill(sym)
            if fill is None:
                alert(
                    "WARN",
                    f"khong tai dung duoc take-profit cho {sym}: khong co lenh BUY "
                    f"nao trong orders — TP se bi NEO LAI theo gia mo cua bar dau "
                    f"tien sau restart",
                    symbol=sym,
                )
                continue
            fill_ts, _fill_price = fill
            anchor = storage.read_anchor_bar(sym, fill_ts)
            if anchor is None:
                alert(
                    "WARN",
                    f"khong tai dung duoc take-profit cho {sym}: khong co bar nao "
                    f"tu lenh BUY ({fill_ts}) — TP se bi NEO LAI theo gia mo cua "
                    f"bar dau tien sau restart",
                    symbol=sym,
                )
                continue
            window = storage.read_bars_until(sym, anchor.ts, strategy.warmup_bars)
            if is_dirty_bar(anchor):
                # Ly do thu tu (brief dot 108): bar neo A co gia 0 thi KHONG the
                # chay lai ATR tu no, va cung khong duoc lang le lay ATR tu chuoi
                # khac — khong tai dung duoc thi phai noi ra.
                alert(
                    "WARN",
                    f"khong tai dung duoc take-profit cho {sym}: bar neo "
                    f"{anchor.ts} la bar rac "
                    f"(OHLC={anchor.open}/{anchor.high}/{anchor.low}/{anchor.close}) "
                    f"— khong chay lai duoc ATR tu no; TP se bi NEO LAI theo gia "
                    f"mo cua bar dau tien sau restart",
                    symbol=sym,
                )
                continue
            # DIRTY-1: cua so chay lai ATR phai la chuoi DA LOC, neu khong ATR
            # khoi phuc se tinh ca cac TR gia tu nen 0 (dung loi dot 107).
            clean_window = [b for b in window if not is_dirty_bar(b)]
            if len(clean_window) != len(window):
                alert(
                    "INFO",
                    f"khoi phuc take-profit {sym}: bo {len(window) - len(clean_window)} "
                    f"bar rac trong cua so ATR",
                    symbol=sym,
                    so_bar_rac=len(window) - len(clean_window),
                    con_lai=len(clean_window),
                )
            tp = strategy.restore_take_profit(sym, clean_window)
            if tp is None:
                alert(
                    "WARN",
                    f"khong tai dung duoc take-profit cho {sym}: chi co "
                    f"{len(clean_window)} bar tinh den bar neo {anchor.ts}, khong du de "
                    f"chay lai ATR — TP se bi NEO LAI theo gia mo cua bar dau tien "
                    f"sau restart",
                    symbol=sym,
                )
                continue
            alert(
                "INFO",
                f"tai dung take-profit {sym} sau restart",
                symbol=sym,
                anchor=str(anchor.ts),
                anchor_open=anchor.open,
                tp=tp,
            )
    # NAV-CI: vốn lệnh thật đọc NAV từ account_nav_snapshot (chủ dự án BỎ
    # real_order_capital khỏi config — quyết định 13/08; và 14/08 chốt vốn rủi
    # ro = NAV = tiền mặt + Σ(qty×giá) − nợ, KHÔNG phải withdrawable: 1% rủi
    # ro/lệnh phải là 1% của thứ mình THỰC SỰ sở hữu, không phải 1% của thứ
    # mình vay được. NAV do collector ghi (account_sync._sync_nav), engine chỉ
    # đọc. Ba nhánh fail-safe của CAP-1 giữ nguyên, KHÔNG nhánh nào im lặng:
    # không có dòng nào -> capital=0 + CRITICAL (fail-safe: approve() từ chối
    # MỌI lệnh, KHÔNG rơi về số dư khả dụng cho "đỡ gắt"); cũ >24h -> vẫn
    # dùng + WARN kèm tuổi; bình thường -> INFO nêu số tiền + mốc thời gian
    # (người vận hành phải nhìn được hệ thống đang tính rủi ro trên con số
    # nào). Nhánh thứ tư: unpriced_symbols không rỗng -> WARN nêu rõ mã nào
    # (account_sync tính mã không định giá được THÀNH 0 nên NAV bị tính HỤT —
    # hụt là an toàn nên vẫn dùng, nhưng im lặng thì không chấp nhận được).
    nav_row = storage.read_nav(cfg.real_order_account)
    if nav_row is None:
        real_capital = 0.0
        alert(
            "CRITICAL",
            "khong doc duoc NAV (account_nav_snapshot khong co dong "
            "cho tai khoan nay) — real capital = 0, MOI lenh that bi tu choi "
            "(fail-safe, khong roi ve account_balance_snapshot)",
            account=cfg.real_order_account,
        )
    elif nav_row[0] <= 0:
        real_capital = 0.0
        nav_val, nav_ts, _ = nav_row
        alert(
            "CRITICAL",
            f"NAV khong hop le (<= 0): {nav_val:,.0f} — real capital = 0, "
            f"MOI lenh that bi tu choi (fail-safe)",
            account=cfg.real_order_account,
            nav=nav_val,
            ts=str(nav_ts),
        )
    else:
        real_capital, nav_ts, unpriced = nav_row
        age_h = (datetime.now(TZ) - nav_ts).total_seconds() / 3600
        if age_h > 24:
            alert(
                "WARN",
                f"NAV cu hon 24h ({age_h:.1f}h) — van dung de tinh rui ro",
                account=cfg.real_order_account,
                nav=real_capital,
                ts=str(nav_ts),
            )
        else:
            alert(
                "INFO",
                "NAV lam real capital",
                account=cfg.real_order_account,
                nav=real_capital,
                ts=str(nav_ts),
            )
        if unpriced:
            alert(
                "WARN",
                f"NAV tinh thieu: {len(unpriced)} ma khong dinh gia duoc (tinh 0) "
                f"— van dung NAV nhung co the dat lenh nho hon",
                account=cfg.real_order_account,
                nav=real_capital,
                unpriced=",".join(unpriced),
            )
    real_risk = RiskManager(capital=real_capital)
    real_risk.halted_date = storage.read_real_risk_halt()
    real_trailing_stop = TrailingStopManager()
    # Tai dung _highest cho vi the THAT sau restart (RTS-1), giong luong paper
    # o tren: doc tu real_order_fills (loc account_no). Vi the that co the do
    # chu tai khoan TU MUA ngoai he thong -> khong co fill -> khong tai dung
    # duoc -> alert WARN neu ro ma, KHONG im lang.
    # Dot 150: chi khoi phuc trailing stop cho sym in cfg.symbols; cac ma ngoai
    # cfg.symbols gom thanh 1 dong INFO de tranh spam Telegram (bay NOISE-1).
    ignored_external_positions: dict[str, int] = {}
    for sym, rpos in storage.read_real_positions(cfg.real_order_account).items():
        if rpos.qty <= 0:
            continue
        if sym not in cfg.symbols:
            ignored_external_positions[sym] = rpos.qty
            continue
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
    if ignored_external_positions:
        alert(
            "INFO",
            "vi the that ngoai cfg.symbols, engine khong quan ly",
            account=cfg.real_order_account,
            positions=ignored_external_positions,
        )
    # GUARD-1: kiem tra duong dat lenh that co that su co the sinh lenh BUY
    # khong. Tran gia tri lenh = NAV * max_order_value_pct (NAV-CI: doc tu
    # account_nav_snapshot, khong con real_order_capital trong config); neu
    # khong du mua noi 1 lo 100 cp cua ma re nhat trong cfg.symbols (gia dong
    # gan nhat) -> alert CRITICAL noi ro: duong lenh that INERT. CHI canh bao,
    # khong chan engine — luong paper van chay dung va van co gia tri; van de
    # goc la IM LANG, khong phai thieu che tai. Khong lay duoc gia nao (bang
    # rong) -> bo qua im lang: khong the ket luan, canh bao sai lam nhon canh
    # bao that.
    # CHI chay khi real_trading_enabled=True (sua GUARD-2): khi trading tat,
    # canh bao moi lan khoi dong chi la nhieu (cai bay NOISE-1) — gia tri that
    # nam o luc ai do bat real_trading_enabled=true.
    if cfg.real_trading_enabled:
        order_cap = real_capital * real_risk.max_order_value_pct
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
        # GUARD-3 (plan 2026-09-01 T2): cong bo QUYEN BAN. Khi doi
        # real_order_account sang tai khoan khac, engine dot nhien co quyen ban
        # nhung co phieu that ma cfg.symbols giao voi danh muc — truoc day im
        # lang. Liet ke tung ma + qty + sellable_qty de nguoi van hanh nhin
        # thay minh vua trao quyen gi. Giao rong -> im lang (NOISE-1). CHI
        # chay khi real_trading_enabled=True, cung khuon GUARD-1/2.
        real_positions = storage.read_real_positions(cfg.real_order_account)
        overlap = [
            (sym, p.qty, p.sellable_qty)
            for sym in cfg.symbols
            if (p := real_positions.get(sym)) is not None and p.qty > 0
        ]
        if overlap:
            detail = ", ".join(
                f"{sym} {qty} cp (sellable {sellable})"
                for sym, qty, sellable in overlap
            )
            alert(
                "WARN",
                f"engine co quyền bán {detail} — cfg.symbols giao voi danh muc "
                f"that cua {cfg.real_order_account}; crossover bear se sinh lenh "
                f"BAN so co phieu nay",
                account=cfg.real_order_account,
            )
    marks: dict[str, float] = {}
    day_state: dict = {}
    last_processed_ts: dict[str, datetime] = dict(warmed_until)
    # GAP-1: theo doi ma nao da duoc kiem cua so warm-up — chi kiem 1 lan cho
    # moi ma (nen live dau tien). Tu nen thu hai tro di cua so da lien mach,
    # kiem tiep chi la nhieu.
    _warmup_gap_checked: set[str] = set()

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
        # Plan 2026-09-01 T1: truyen atr (float | None) cho dinh co BUY that —
        # khong keo object strategy vao real_orders.py
        real_orders.handle_crossover(
            cfg, storage, real_risk, crossover, bar, atr=strategy.last_atr(bar.symbol)
        )

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
                # CHONG NAP TRUNG (WARM-1 muc 4) & RAO CHAN TIEN TRINH (Brief 26 Task 2):
                # 1. Bar trong qua khu hoac trung voi warm-up -> bo qua khong canh bao (replayed durable message).
                # 2. Bar trung hoac lui thoi gian so voi bar da xu ly trong phien -> alert WARN vi la bar khong tien len.
                last_ts = last_processed_ts.get(bar.symbol)
                if last_ts is not None and bar.ts <= last_ts:
                    warm_cutoff = warmed_until.get(
                        bar.symbol, datetime.min.replace(tzinfo=bar.ts.tzinfo)
                    )
                    if bar.ts <= warm_cutoff:
                        await msg.ack()
                        processed += 1
                        continue
                    else:
                        alert(
                            "WARN",
                            "non-advancing bar timestamp received, skipping",
                            symbol=bar.symbol,
                            incoming_ts=bar.ts.isoformat(),
                            last_processed_ts=last_ts.isoformat(),
                        )
                        await msg.ack()
                        processed += 1
                        continue
                # GAP-1 (Brief 74 Task 1): nen live DAU TIEN — goi count_warmup_gap().
                # Chi kiem 1 lan/ma; tu nen thu hai tro di cua so da lien mach.
                # Ma chua warm-up duoc (khong co khoa trong warmed_until) da co
                # WARN rieng o phan warm-up tren — khong canh bao them.
                if bar.symbol not in _warmup_gap_checked:
                    _warmup_gap_checked.add(bar.symbol)
                    wu = warmed_until.get(bar.symbol)
                    if wu is not None:
                        missing = count_warmup_gap(
                            wu,
                            bar.ts,
                            cfg.bar_interval_minutes,
                            frozenset(cfg.holidays),
                        )
                        if missing >= 1:
                            alert(
                                "WARN",
                                f"GAP-1 cua so warm-up co lo: {bar.symbol} nhan coc "
                                f"{missing} nen (warm-up den {wu.isoformat()}, "
                                f"nen live dau={bar.ts.isoformat()}) — chi bao hieu, "
                                f"khong tu dong bu",
                                symbol=bar.symbol,
                                warmed_until=wu.isoformat(),
                                first_live_ts=bar.ts.isoformat(),
                                missing_bars=missing,
                            )
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
                last_processed_ts[bar.symbol] = bar.ts
                now_engine = datetime.now(TZ)
                bar_close_ts = bar.ts + timedelta(minutes=cfg.bar_interval_minutes)
                engine_lag_ms = round(
                    (now_engine - bar_close_ts).total_seconds() * 1000, 2
                )
                alert(
                    "INFO",
                    "bar processed",
                    symbol=bar.symbol,
                    ts=bar.ts.isoformat(),
                    lag_ms=engine_lag_ms,
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


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    attach_durable_alert_handler(filename="engine_alerts.log")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    _configure_logging()
    start_outbox("engine")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
