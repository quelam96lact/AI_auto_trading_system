from datetime import datetime, timedelta

from trading.alerts import alert
from trading.config import Config
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import Crossover
from trading.strategy import Signal

PENDING_ORDER_TTL_MINUTES = 15
# Plan 2026-09-01 T1-B2: nguong "suc mua cu" — nhịp dong bo do duoc ~5 phut,
# 15 = 3x nhip (cung ly le chuong 2A/2D). Neu do lai thay nhip khac, bao cao
# truoc khi doi so.
BUYING_POWER_MAX_AGE_MINUTES = 15
# Brief dot 10 Task 2 (P1): Fail-safe do cu cho vi the (account_position_snapshot)
# Nguong 15 phut tuong duong BUYING_POWER_MAX_AGE_MINUTES (3x nhip sync 5m).
POSITION_MAX_AGE_MINUTES = 15
# Brief dot 10 Task 5 (E): Tran tam thoi 100 co phieu cho moi lenh MUA that
# do chu du an dat 06/09 cho giai doan thu nghiem (khong phai gioi han ky thuat).
# LUU Y: CHI ap dung cho lenh MUA, KHONG ap dung cho lenh BAN (tranh nhot vi the).
MAX_REAL_BUY_QTY = 100
# Brief dot 30 Task 2: Cảnh báo khi tài khoản cấu hình (real_order_account) có NAV
# nhỏ hơn đáng kể (từ 10x trở lên) so với một tài khoản khác đã đồng bộ trong
# account_nav_snapshot — nói ra sự chênh lệch đáng ngờ một lần khi khởi động,
# không tự đổi tài khoản và không chặn lệnh.
NAV_DISCREPANCY_RATIO_THRESHOLD = 10.0
_warned_nav_discrepancy_accounts: set[str] = set()


def _warn_nav_discrepancy_once(cfg: Config, storage: Storage) -> None:
    account = cfg.real_order_account
    if account in _warned_nav_discrepancy_accounts:
        return
    _warned_nav_discrepancy_accounts.add(account)
    try:
        nav_map = storage.read_latest_account_navs()
    except Exception:
        return

    if not nav_map:
        return

    current_nav = nav_map.get(account)
    if current_nav is None or current_nav <= 0:
        return

    for other_acc, other_nav in nav_map.items():
        if other_acc == account:
            continue
        if other_nav >= current_nav * NAV_DISCREPANCY_RATIO_THRESHOLD:
            ratio = other_nav / current_nav
            alert(
                "WARN",
                f"tai khoan cau hinh {account} co NAV ({current_nav:,.0f}) nho hon {ratio:.1f}x "
                f"so voi tai khoan {other_acc} ({other_nav:,.0f}) trong account_nav_snapshot — "
                f"kiem tra lai real_order_account neu day khong phai chu y",
                account=account,
                nav=current_nav,
                other_account=other_acc,
                other_nav=other_nav,
                ratio=round(ratio, 2),
            )


# Dong ho module-level de test tiêm duoc (plan: khong goi datetime.now() tran
# trong ham).
_now = datetime.now


def handle_crossover(
    cfg: Config,
    storage: Storage,
    risk: RiskManager,
    crossover: Crossover,
    bar: Bar,
    atr: float | None = None,
) -> None:
    """Gate 1 sự kiện crossover (từ SmaCrossStrategy.last_crossover() — thuần kỹ
    thuật, KHÔNG liên quan PaperBroker) qua RiskManager riêng cho lệnh thật, dựa
    HOÀN TOÀN trên vị thế THẬT của tài khoản Cash.

    Plan 2026-09-01 T1: nhanh BUY that gio day duoc DINH CO — goi LAI
    risk.approve_sized() (ATR sizing + tran 20%, KHONG chep lai cong thuc —
    bai hoc 4ea4c8d) roi kep tran CUNG max_buy_qty tu SSI (lam tron xuong boi
    100). atr truyen tu closure on_real_crossover (engine/main.py) — khong keo
    object strategy vao day. SELL van dung sellable_qty, khong qua suc mua.

    KHÔNG gọi bất kỳ API đặt lệnh nào — chỉ ghi DB + cảnh báo. Việc đặt lệnh thật
    là scripts/confirm_real_order.py, chạy thủ công bởi người dùng.
    """
    # Brief dot 10 Task 2 (P1): Fail-safe do cu vi the — bat buoc dong bo con tuoi
    pos_sync_ts = storage.read_position_sync_ts(cfg.real_order_account)
    if pos_sync_ts is None:
        alert(
            "CRITICAL",
            f"khong co dong vi the (account_position_snapshot) cho tai khoan {cfg.real_order_account} "
            f"— TU CHOI xu ly lenh that cho {bar.symbol} (fail-safe, chua tung dong bo vi the)",
            account=cfg.real_order_account,
            symbol=bar.symbol,
        )
        return
    pos_age_min = (_now(bar.ts.tzinfo) - pos_sync_ts).total_seconds() / 60
    if pos_age_min > POSITION_MAX_AGE_MINUTES:
        alert(
            "CRITICAL",
            f"vi the tai khoan {cfg.real_order_account} cu {pos_age_min:.0f} phut (nguong "
            f"{POSITION_MAX_AGE_MINUTES}) — TU CHOI xu ly lenh that cho {bar.symbol} "
            f"(fail-safe, khong dat lenh tren so lieu vi the cu)",
            account=cfg.real_order_account,
            symbol=bar.symbol,
            ts=str(pos_sync_ts),
        )
        return

    _warn_nav_discrepancy_once(cfg, storage)

    positions = storage.read_real_positions(cfg.real_order_account)
    real_pos = positions.get(bar.symbol)
    max_buy_qty = 0  # chi dung cho nhanh BUY; tranh possibly-unbound

    if crossover == "bull":
        if real_pos is not None and real_pos.qty > 0:
            return  # tài khoản thật đã nắm giữ mã này rồi, không mua thêm
        signal = Signal(symbol=bar.symbol, side="BUY", qty=1)
        # T1-B2 fail-safe suc mua (khuon NAV engine/main.py:122-136): thieu du
        # lieu => tu choi + CRITICAL, KHONG roi ve gia tri "cho do gat".
        bp = storage.read_buying_power(cfg.real_order_account, bar.symbol)
        if bp is None:
            alert(
                "CRITICAL",
                f"khong co dong sức mua (account_buying_power) cho {bar.symbol} "
                f"— TU CHOI lenh BUY that (fail-safe, khong doan max_buy_qty)",
                account=cfg.real_order_account,
                symbol=bar.symbol,
            )
            return
        max_buy_qty, _, _, bp_ts = bp
        age_min = (_now(bar.ts.tzinfo) - bp_ts).total_seconds() / 60
        if age_min > BUYING_POWER_MAX_AGE_MINUTES:
            alert(
                "CRITICAL",
                f"sức mua {bar.symbol} cu {age_min:.0f} phút (nguong "
                f"{BUYING_POWER_MAX_AGE_MINUTES}) — TU CHOI lenh BUY that "
                f"(fail-safe, khong dat lenh tren so lieu cu)",
                account=cfg.real_order_account,
                symbol=bar.symbol,
                ts=str(bp_ts),
            )
            return
    elif crossover == "bear":
        sellable = real_pos.sellable_qty if real_pos is not None else 0
        if sellable <= 0:
            return  # không nắm giữ, hoặc chưa settle T+2.5 — không có gì để bán
        signal = Signal(symbol=bar.symbol, side="SELL", qty=sellable)
    else:
        return

    today = bar.ts.date()
    daily_pnl = storage.read_real_daily_pnl(cfg.real_order_account, today)

    if signal.side == "BUY":
        # T1-B3: approve_sized resize BUY theo ATR + tran 20% (min qty_atr/cap)
        sized = risk.approve_sized(signal, bar.close, atr, positions, daily_pnl, today)
        if sized is None:
            # SIZE-1 Viec 2: moi lan tu choi noi duoc ly do
            alert(
                "INFO",
                "lenh that bi tu choi",
                symbol=signal.symbol,
                side=signal.side,
                reason=risk.last_reject_reason,
            )
            return
        # Tran CUNG suc mua SSI + tran 100 cp tam thoi Task 5, ap SAU approve_sized — lam tron xuong boi risk.lot_size
        qty = min(sized.qty, max_buy_qty, MAX_REAL_BUY_QTY) // risk.lot_size * risk.lot_size
        if qty < risk.lot_size:
            alert(
                "INFO",
                "lenh that bi tu choi",
                symbol=signal.symbol,
                side=signal.side,
                reason=f"suc mua {max_buy_qty} khong du 1 lo {risk.lot_size} cp",
            )
            return
        signal = Signal(signal.symbol, "BUY", qty)
    else:
        if not risk.approve(signal, bar.close, positions, daily_pnl, today):
            # SIZE-1 Viec 2: moi lan tu choi noi duoc ly do — caller ghi log INFO
            # (tu choi la chuyen binh thuong, khong WARN — bay NOISE-1).
            alert(
                "INFO",
                "lenh that bi tu choi",
                symbol=signal.symbol,
                side=signal.side,
                reason=risk.last_reject_reason,
            )
            return

    expires_at = _now(bar.ts.tzinfo) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)
    order_id = storage.create_pending_order(
        account_no=cfg.real_order_account,
        symbol=signal.symbol,
        side=signal.side,
        quantity=signal.qty,
        price=bar.close,
        expires_at=expires_at,
    )
    alert(
        "WARN",
        "real order pending confirmation",
        id=order_id,
        symbol=signal.symbol,
        side=signal.side,
        qty=signal.qty,
        price=bar.close,
        expires_in_minutes=PENDING_ORDER_TTL_MINUTES,
        confirm_cmd=f"uv run python scripts/confirm_real_order.py {order_id}",
    )


def handle_stop_touch(
    cfg: Config,
    storage: Storage,
    bar: Bar,
    atr: float | None,
    real_trailing_stop,
) -> None:
    """Canh bao CHAM STOP cho vi the that — KHONG phai stop-loss tu dong.

    Kien truc la nguoi bam nut: ham nay CHI ghi mot lenh SELL cho xac nhan
    vao pending_real_orders + alert; viec dat lenh that la
    scripts/confirm_real_order.py chay tay, phai go YES trong 15 phut. Khong
    co gi tu dong cat lo o day.

    Bo qua halt lo ngay: RiskManager.approve() chan ca SELL khi halted_date ==
    today (risk.py:37-38 -> _halt_check). Voi lenh cat lo thi dieu do nguy
    hiem — halt xay ra vi dang lo, roi chinh no khoa luon duong thoat. Tien
    le trong repo: luong paper da bo qua risk cho stop-loss — logic.py:51-54,
    nhanh force_exit chay TRUOC va doc lap voi risk.approve_sized() o nhanh
    elif. => Lenh SELL do cham stop KHONG di qua risk.approve().

    So luong ban dung RealPosition.sellable_qty (T+2.5), khong dung qty; neu
    sellable_qty <= 0 (chua settle) thi khong sinh lenh duoc -> alert WARN.

    Khong sinh lenh trung: neu da co pending SELL con hieu luc cho cung
    account_no + symbol thi bo qua (moi bar cham stop se de ra mot lenh cho
    moi neu khong chan).
    """
    # Brief dot 10 Task 2 (P1): Fail-safe do cu vi the — bat buoc dong bo con tuoi
    pos_sync_ts = storage.read_position_sync_ts(cfg.real_order_account)
    if pos_sync_ts is None:
        alert(
            "CRITICAL",
            f"khong co dong vi the (account_position_snapshot) cho tai khoan {cfg.real_order_account} "
            f"— TU CHOI xu ly stop touch cho {bar.symbol} (fail-safe, chua tung dong bo vi the)",
            account=cfg.real_order_account,
            symbol=bar.symbol,
        )
        return
    pos_age_min = (_now(bar.ts.tzinfo) - pos_sync_ts).total_seconds() / 60
    if pos_age_min > POSITION_MAX_AGE_MINUTES:
        alert(
            "CRITICAL",
            f"vi the tai khoan {cfg.real_order_account} cu {pos_age_min:.0f} phut (nguong "
            f"{POSITION_MAX_AGE_MINUTES}) — TU CHOI xu ly stop touch cho {bar.symbol} "
            f"(fail-safe, khong dat lenh tren so lieu vi the cu)",
            account=cfg.real_order_account,
            symbol=bar.symbol,
            ts=str(pos_sync_ts),
        )
        return

    positions = storage.read_real_positions(cfg.real_order_account)
    real_pos = positions.get(bar.symbol)
    if real_pos is None or real_pos.qty <= 0:
        return  # tai khoan that khong nam giu ma nay

    if not real_trailing_stop.is_tracking(bar.symbol):
        # RTS-2: vi the that co the mo GIUA PHIEN (xac nhan BUY that -> SSI
        # khop -> account_sync cap nhat snapshot), khong phai luc khoi dong —
        # on_position_opened chi duoc goi o vong lap khoi dong, nen phai khoi
        # tao o day truoc khi check; khong khoi tao thi check() tra None mai
        # mai (trailing_stop.py:26-28) = vi the khong bao gio cham stop.
        highest = storage.read_real_highest_since_buy(cfg.real_order_account, bar.symbol)
        if highest is not None:
            real_trailing_stop.on_position_opened(bar.symbol, highest)
        else:
            # Mua ngoai he thong / khong co fill: dung gia von thay cho dinh
            # that (under-protect nhuong buoc cho tinh huong khong co du lieu)
            # + alert WARN 1 lan noi ro (lan sau da tracking nen khong lap lai).
            real_trailing_stop.on_position_opened(bar.symbol, real_pos.avg_price)
            alert(
                "WARN",
                f"vi the that {bar.symbol} moi xuat hien va khong co BUY fill "
                f"trong real_order_fills — trailing stop khoi tao bang GIA VON "
                f"{real_pos.avg_price:,.0f} thay cho dinh that (mua ngoai he "
                f"thong?)",
                symbol=bar.symbol,
            )

    stop_price = real_trailing_stop.check(bar, atr)
    if stop_price is None:
        return  # chua cham stop (hoac atr None — khong tinh duoc stop)

    sellable = real_pos.sellable_qty
    if sellable <= 0:
        alert(
            "WARN",
            f"vi the that {bar.symbol} da cham stop {stop_price:.0f} nhung "
            f"chua ban duoc (chua settle T+2.5, sellable_qty=0)",
            symbol=bar.symbol,
        )
        return

    if storage.has_active_pending_sell(cfg.real_order_account, bar.symbol):
        return  # da co lenh SELL cho hieu luc — khong sinh trung

    expires_at = datetime.now(bar.ts.tzinfo) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)
    order_id = storage.create_pending_order(
        account_no=cfg.real_order_account,
        symbol=bar.symbol,
        side="SELL",
        quantity=sellable,
        price=stop_price,
        expires_at=expires_at,
    )
    alert(
        "WARN",
        "REAL STOP TOUCH: pending SELL cho xac nhan (KHONG tu dong cat lo — "
        "nguoi van hanh bam nut)",
        id=order_id,
        symbol=bar.symbol,
        side="SELL",
        qty=sellable,
        price=stop_price,
        expires_in_minutes=PENDING_ORDER_TTL_MINUTES,
        confirm_cmd=f"uv run python scripts/confirm_real_order.py {order_id}",
    )
