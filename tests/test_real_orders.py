from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from trading.calendar_vn import TZ
from trading.config import Config
from trading.models import Bar
from trading.real_orders import (
    PENDING_ORDER_TTL_MINUTES,
    handle_crossover,
)
from trading.risk import RiskManager
from trading.storage.db import RealPosition


@pytest.fixture
def cfg():
    return Config(
        symbols=["VCB"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=["0434221"],
        holidays=set(),
        db_dsn="postgresql://x:***@localhost/db",
        nats_url="nats://localhost:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="c",
        ssi_consumer_secret="s",
        ssi_api_key="k",
        ssi_api_secret="a",
        ssi_private_key="pk",
        real_trading_enabled=False,
        real_order_account="ACC_REAL",
    )


@pytest.fixture
def bar():
    return Bar(
        "VCB",
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ),
        50_000,
        50_000,
        50_000,
        50_000,
        100,
    )


def _make_storage():
    storage = MagicMock()
    storage.read_real_positions.return_value = {}
    storage.read_real_daily_pnl.return_value = 0.0
    storage.create_pending_order.return_value = 42
    # T1-B2: suc mua TUOI mac dinh (du lon, khong chan qty sizing trong test cu)
    storage.read_buying_power.return_value = (
        10_000,
        10_000,
        50.0,
        datetime(2026, 7, 15, 8, 55, tzinfo=TZ),
    )
    return storage


def _patch_now(monkeypatch, fixed=None):
    """T1-B2: dong ho phai tiêm duoc — mac dinh dong bo voi bar (9:05 ngay
    15/07), de bp_ts 8:55 (10 phut truoc) con TUOI trong test khong lien quan
    den dong ho that."""
    from trading import real_orders as ro_mod

    if fixed is None:
        fixed = datetime(2026, 7, 15, 9, 5, tzinfo=TZ)
    monkeypatch.setattr(ro_mod, "_now", lambda tz: fixed)
    return fixed


def test_handle_crossover_buy_when_not_held(cfg, bar, monkeypatch):
    fixed_now = _patch_now(monkeypatch)  # 2026-07-15 09:05
    storage = _make_storage()
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_called_once()
    args = storage.create_pending_order.call_args.kwargs
    assert args["account_no"] == "ACC_REAL"
    assert args["symbol"] == "VCB"
    assert args["side"] == "BUY"
    # T1-B3: qty qua approve_sized (ATR sizing) roi kep tran suc mua — khong
    # con la hang so BUY_QTY=100. capital 1ty, atr 500, gia 50k:
    # qty_atr = 1ty*1%/(500*2) = 10.000; qty_cap = 1ty*20%/50k = 4.000
    # -> min = 4.000; tran suc mua 10.000 -> 4.000
    assert args["quantity"] == 4_000, f"qty sizing, thuc te: {args['quantity']}"
    assert args["price"] == 50_000
    expires_at = args["expires_at"]
    assert expires_at.tzinfo is not None
    assert expires_at > fixed_now
    assert expires_at <= fixed_now + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)

    mock_alert.assert_called_once()
    alert_kwargs = mock_alert.call_args.kwargs
    assert alert_kwargs["id"] == 42
    assert (
        alert_kwargs["confirm_cmd"] == "uv run python scripts/confirm_real_order.py 42"
    )


def test_handle_crossover_skips_buy_when_already_held(cfg, bar):
    storage = _make_storage()
    storage.read_real_positions.return_value = {
        "VCB": RealPosition("VCB", 100, 50_000.0, 100)
    }
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_not_called()


def test_handle_crossover_sell_caps_to_sellable_qty(cfg, bar):
    storage = _make_storage()
    storage.read_real_positions.return_value = {
        "VCB": RealPosition("VCB", 100, 50_000.0, 30)
    }
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bear", bar)

    storage.create_pending_order.assert_called_once()
    args = storage.create_pending_order.call_args.kwargs
    assert args["side"] == "SELL"
    assert args["quantity"] == 30
    mock_alert.assert_called_once()


def test_handle_crossover_skips_sell_when_nothing_sellable(cfg, bar):
    storage = _make_storage()
    storage.read_real_positions.return_value = {}
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bear", bar)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_not_called()


def test_handle_crossover_does_nothing_when_risk_rejects(cfg, bar, monkeypatch):
    _patch_now(monkeypatch)
    storage = _make_storage()
    storage.read_real_positions.return_value = {}
    risk = RiskManager(capital=1.0)  # capital 1d -> moi lenh deu vo tran -> reject

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar)

    storage.create_pending_order.assert_not_called()
    # SIZE-1 Viec 2: tu choi PHẢI noi ly do qua alert INFO (khong con im lang)
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "INFO"
    assert "reason" in mock_alert.call_args.kwargs
    assert mock_alert.call_args.kwargs["reason"] is not None


def test_handle_crossover_skips_buy_when_position_qty_is_zero(cfg, bar, monkeypatch):
    _patch_now(monkeypatch)
    storage = _make_storage()
    storage.read_real_positions.return_value = {
        "VCB": RealPosition("VCB", 0, 50_000.0, 0)
    }
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_called_once()
    args = storage.create_pending_order.call_args.kwargs
    assert args["side"] == "BUY"
    # T1-B3: qty qua approve_sized — 4.000 (xem test_handle_crossover_buy_when_not_held)
    assert args["quantity"] == 4_000


# ============ Plan 2026-09-01 T1-B2/B3: dinh co BUY that theo NAV + suc mua ============


def _make_sized_storage(buying_power=None, positions=None):
    """Storage mock kem read_buying_power + read_real_positions co the cau hinh."""
    storage = _make_storage()
    storage.read_real_positions.return_value = positions or {}
    storage.read_buying_power.return_value = buying_power
    return storage


def test_buy_rejected_when_no_buying_power_row(cfg, bar):
    """T1-B2 (a): khong co dong suc mua nao -> TU CHOI lenh + alert CRITICAL,
    KHONG tao pending order (fail-safe theo khuon NAV engine/main.py:122-136)."""
    storage = _make_sized_storage(buying_power=None)
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL", (
        f"phai alert CRITICAL, thuc te: {mock_alert.call_args}"
    )
    assert "sức mua" in mock_alert.call_args.args[1]


def test_buy_rejected_when_buying_power_stale(cfg, bar):
    """T1-B2 (b): dong suc mua CU hon 15 phut -> TU CHOI + alert CRITICAL.
    Dong ho tiêm duoc qua monkeypatch `_now` — khong goi datetime.now() tran."""
    from trading import real_orders as ro_mod

    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    old_ts = now - timedelta(minutes=20)  # 20 phut > nguong 15
    storage = _make_sized_storage(
        buying_power=(800, 600, 40.0, old_ts)
    )
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert, patch.object(
        ro_mod, "_now", return_value=now
    ):
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL", (
        f"phai alert CRITICAL, thuc te: {mock_alert.call_args}"
    )
    assert "phút" in mock_alert.call_args.args[1]


def test_buy_qty_capped_to_max_buy_qty_and_rounded_down(cfg, bar, monkeypatch):
    """T1-B3: approve_sized cho qty_atr=1000, qty_cap=800 -> 800; tran suc mua
    550 -> min(800, 550) = 550 -> lam tron xuong lo 100 = 500. KHONG phai 550,
    KHONG phai 800.

    Tham so da xac nhan that: capital 200tr, atr=100, gia 50k ->
    qty_atr = 200tr*1%/(100*2) = 10.000; qty_cap = 200tr*20%/50k = 800
    -> min = 800; min(800, 550) = 550 -> 500."""
    fixed_now = _patch_now(monkeypatch, fixed=datetime(2026, 9, 1, 9, 10, tzinfo=TZ))
    storage = _make_sized_storage(
        buying_power=(550, 600, 40.0, fixed_now - timedelta(minutes=10))
    )
    risk = RiskManager(capital=200_000_000.0)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=100.0)

    storage.create_pending_order.assert_called_once()
    qty = storage.create_pending_order.call_args.kwargs["quantity"]
    assert qty == 500, f"min(800, 550) tron xuong lo = 500, thuc te: {qty}"
    mock_alert.assert_called_once()


def test_sell_unchanged_when_buying_power_zero(cfg, bar, monkeypatch):
    """T1-B4: SELL khong di qua suc mua — sellable_qty=137 van ra 137 ke ca
    khi max_buy_qty=0 (suc mua chi cap cho nhanh BUY)."""
    _patch_now(monkeypatch)
    storage = _make_sized_storage(
        buying_power=(0, 0, None, datetime(2026, 9, 1, 9, 0, tzinfo=TZ)),
        positions={"VCB": RealPosition("VCB", 200, 50_000.0, 137)},
    )
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bear", bar, atr=None)

    storage.create_pending_order.assert_called_once()
    qty = storage.create_pending_order.call_args.kwargs["quantity"]
    assert qty == 137, f"SELL phai giu nguyen sellable_qty, thuc te: {qty}"


def test_buy_real_numbers_nav_5tr_can_still_buy_one_lot(cfg, monkeypatch):
    """T1-B5 (bat buoc, khong phai phu): so THAT tu plan muc 0 — NAV 0434221 =
    5.021.459, gia AAA = 7030, suc mua AAA = 666, ATR = 100 (hợp lý voi gia
    7030: 1.4%). qty_cap = 5.021.459*20%/7030 = 142 cp -> 1 lo; qty_atr =
    5.021.459*1%/(100*2) = 251 cp -> 2 lo; min = 100; tran 666 -> 100.
    DUONG BUY THAT KHONG CHET VE MAT SO HOC (bai hoc SIZE-1: 4 thang khong
    mua noi). Neu khong ra noi 1 lo: PHAI HIEN, khong noi luat cho test xanh."""
    fixed_now = _patch_now(monkeypatch, fixed=datetime(2026, 9, 1, 9, 10, tzinfo=TZ))
    storage = _make_sized_storage(
        buying_power=(666, 666, 0.0, fixed_now - timedelta(minutes=5)),
    )
    risk = RiskManager(capital=5_021_459.0)

    bar_aaa = Bar(
        "AAA",
        datetime(2026, 9, 1, 9, 0, tzinfo=TZ),
        7030, 7030, 7030, 7030, 1000,
    )
    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar_aaa, atr=100.0)

    storage.create_pending_order.assert_called_once()
    qty = storage.create_pending_order.call_args.kwargs["quantity"]
    assert qty >= 100, (
        f"NAV 5tr phai mua duoc 1 lo AAA (qty_cap=100), thuc te {qty} — "
        f"day la PHAI HIEN, khong noi luat"
    )


def test_buy_real_numbers_nav_200tr_sized_well_above_one_lot(cfg, monkeypatch):
    """T1-B5: so THAT 0434226 — NAV 200.188.000, AAA 7030, suc mua 10.807.
    qty_cap = 200.188.000*20%/7030 = 5.695 -> 56 lo; qty_atr =
    200.188.000*1%/(100*2) = 10.009 -> 100 lo; min = 5.600; tran 10.807
    -> 5.600 (>= 100, khong bi ngheo doi)."""
    fixed_now = _patch_now(monkeypatch, fixed=datetime(2026, 9, 1, 9, 10, tzinfo=TZ))
    storage = _make_sized_storage(
        buying_power=(10_807, 10_807, 40.0, fixed_now - timedelta(minutes=5)),
    )
    risk = RiskManager(capital=200_188_000.0)

    bar_aaa = Bar(
        "AAA",
        datetime(2026, 9, 1, 9, 0, tzinfo=TZ),
        7030, 7030, 7030, 7030, 1000,
    )
    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar_aaa, atr=100.0)

    storage.create_pending_order.assert_called_once()
    qty = storage.create_pending_order.call_args.kwargs["quantity"]
    assert qty >= 100, f"NAV 200tr phai mua duoc it nhat 1 lo, thuc te {qty}"
    assert qty == 5_600, f"min(qty_atr 10.000, qty_cap 5.600) = 5.600, thuc te {qty}"


def test_buy_respects_custom_lot_size_one(cfg, monkeypatch):
    """GÓI I: handle_crossover với lot_size=1 và max_buy_qty không chia hết cho 100.
    Code cũ sẽ áp cứng // 100 * 100 -> qty = 0 < 100 -> từ chối.
    Code mới phải dùng risk.lot_size -> qty = 33 -> tạo pending order."""
    fixed_now = _patch_now(monkeypatch, fixed=datetime(2026, 9, 1, 9, 10, tzinfo=TZ))
    storage = _make_sized_storage(
        buying_power=(33, 33, 50.0, fixed_now - timedelta(minutes=5)),
    )
    # capital 10tr, giá 50k, atr 1500, lot_size=1:
    # qty_atr = 10tr*1%/(1500*2) = 33; qty_cap = 10tr*20%/50k = 40; min = 33; trần 33 -> 33
    risk = RiskManager(capital=10_000_000.0, lot_size=1)

    bar_btc = Bar(
        "BTC",
        datetime(2026, 9, 1, 9, 0, tzinfo=TZ),
        50_000, 50_000, 50_000, 50_000, 100,
    )
    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar_btc, atr=1500.0)

    storage.create_pending_order.assert_called_once()
    qty = storage.create_pending_order.call_args.kwargs["quantity"]
    assert qty == 33, f"lot_size=1 phai ra qty=33, thuc te: {qty}"


def test_buy_default_lot_size_hundred_invariant(cfg, monkeypatch):
    """GÓI I: Mặc định lot_size=100 phải bất biến:
    - max_buy_qty = 33 < 100 -> từ chối (không gọi create_pending_order).
    - max_buy_qty = 250 -> làm tròn xuống bội 100 là 200."""
    fixed_now = _patch_now(monkeypatch, fixed=datetime(2026, 9, 1, 9, 10, tzinfo=TZ))

    # Trường hợp 1: max_buy_qty = 33 < 100
    storage1 = _make_sized_storage(
        buying_power=(33, 33, 50.0, fixed_now - timedelta(minutes=5)),
    )
    risk_default = RiskManager(capital=100_000_000.0)  # lot_size mặc định 100
    bar_test = Bar("VCB", datetime(2026, 9, 1, 9, 0, tzinfo=TZ), 50_000, 50_000, 50_000, 50_000, 100)
    with patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage1, risk_default, "bull", bar_test, atr=500.0)
    storage1.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert "khong du 1 lo 100 cp" in mock_alert.call_args.kwargs["reason"]

    # Trường hợp 2: max_buy_qty = 250 -> làm tròn xuống 200
    storage2 = _make_sized_storage(
        buying_power=(250, 250, 50.0, fixed_now - timedelta(minutes=5)),
    )
    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage2, risk_default, "bull", bar_test, atr=500.0)
    storage2.create_pending_order.assert_called_once()
    assert storage2.create_pending_order.call_args.kwargs["quantity"] == 200

