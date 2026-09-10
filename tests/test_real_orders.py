from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from trading.calendar_vn import TZ
from trading.config import Config
from trading.models import Bar
from trading.real_orders import (
    PENDING_ORDER_TTL_MINUTES,
    _warned_nav_discrepancy_accounts,
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


@pytest.fixture(autouse=True)
def _default_patch_now(monkeypatch):
    """Mặc định đồng bộ _now với bar fixture (2026-07-15 09:05) cho mọi test."""
    from trading import real_orders as ro_mod

    fixed = datetime(2026, 7, 15, 9, 5, tzinfo=TZ)
    monkeypatch.setattr(ro_mod, "_now", lambda tz=None: fixed)


def _make_storage():
    from trading import real_orders as ro_mod

    storage = MagicMock()
    storage.read_real_positions.return_value = {}
    storage.read_position_sync_ts.side_effect = lambda account=None: ro_mod._now(TZ) - timedelta(minutes=5)
    storage.read_real_daily_pnl.return_value = 0.0
    storage.create_pending_order.return_value = 42
    storage.read_latest_account_navs.return_value = {}
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
    monkeypatch.setattr(ro_mod, "_now", lambda tz=None: fixed)
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
    # Task 5: min(qty_atr 10k, qty_cap 4k, max_buy 10k, MAX_REAL_BUY_QTY 100) = 100
    assert args["quantity"] == 100, f"qty sizing kep tran 100 cp, thuc te: {args['quantity']}"
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
    assert args["quantity"] == 100


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
    assert qty == 100, f"min(800, 550, MAX_REAL_BUY_QTY 100) = 100, thuc te: {qty}"
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
    5.021.459*1%/(100*2) = 251 cp -> 2 lo; min = 100; tran 666 -> 100."""
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
    assert qty == 100, f"NAV 5tr phai mua duoc 1 lo AAA (100 cp), thuc te {qty}"


def test_buy_real_numbers_nav_200tr_sized_well_above_one_lot(cfg, monkeypatch):
    """T1-B5 & Task 5: NAV 200tr tinh ra 5.600 cp nhung bi tran tam thoi 100 cp (Task 5)."""
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
    assert qty == 100, f"NAV 200tr kep tran MAX_REAL_BUY_QTY 100 cp, thuc te {qty}"


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
    - max_buy_qty = 250 -> làm tròn xuống 100 do trần MAX_REAL_BUY_QTY."""
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

    # Trường hợp 2: max_buy_qty = 250 -> kẹp trần 100
    storage2 = _make_sized_storage(
        buying_power=(250, 250, 50.0, fixed_now - timedelta(minutes=5)),
    )
    with patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage2, risk_default, "bull", bar_test, atr=500.0)
    storage2.create_pending_order.assert_called_once()
    assert storage2.create_pending_order.call_args.kwargs["quantity"] == 100


# ===========================================================================
# Brief Đợt 10 — Task 2: Fail-safe độ cũ vị thế (P1)
# ===========================================================================


def test_crossover_position_sync_fresh_passes(cfg, bar, monkeypatch):
    """Vị thế đồng bộ 5 phút trước (< 15 phút) -> Cho qua và xử lý bình thường."""
    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    sync_ts = now - timedelta(minutes=5)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = sync_ts
    storage.read_buying_power.return_value = (1000, 1000, 50.0, sync_ts)
    risk = RiskManager(capital=100_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_called_once()


def test_crossover_position_sync_stale_rejected_critical(cfg, bar, monkeypatch):
    """Vị thế đồng bộ 20 phút trước (> 15 phút) -> Từ chối + alert CRITICAL."""
    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    stale_ts = now - timedelta(minutes=20)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = stale_ts
    risk = RiskManager(capital=100_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL"
    assert "vị thế" in mock_alert.call_args.args[1] or "vi the" in mock_alert.call_args.args[1]


def test_crossover_position_sync_none_rejected_critical(cfg, bar, monkeypatch):
    """Chưa từng đồng bộ vị thế (sync_ts is None) -> Từ chối + alert CRITICAL."""
    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = None
    risk = RiskManager(capital=100_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL"
    assert "chua tung dong bo" in mock_alert.call_args.args[1]


def test_stop_touch_position_sync_fresh_passes(cfg, bar, monkeypatch):
    """Stop touch với vị thế tươi (< 15m) -> Cho qua và tạo pending order SELL."""
    from trading.real_orders import handle_stop_touch

    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    sync_ts = now - timedelta(minutes=5)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = sync_ts
    storage.read_real_positions.return_value = {"VCB": RealPosition("VCB", 200, 50_000.0, 200)}
    storage.has_active_pending_sell.return_value = False

    trailing = MagicMock()
    trailing.is_tracking.return_value = True
    trailing.check.return_value = 49_000.0

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert"):
        handle_stop_touch(cfg, storage, bar, atr=500.0, real_trailing_stop=trailing)

    storage.create_pending_order.assert_called_once()
    assert storage.create_pending_order.call_args.kwargs["side"] == "SELL"
    assert storage.create_pending_order.call_args.kwargs["quantity"] == 200


def test_stop_touch_position_sync_stale_rejected_critical(cfg, bar, monkeypatch):
    """Stop touch với vị thế cũ (> 15m) -> Từ chối + alert CRITICAL."""
    from trading.real_orders import handle_stop_touch

    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    stale_ts = now - timedelta(minutes=20)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = stale_ts
    storage.read_real_positions.return_value = {"VCB": RealPosition("VCB", 200, 50_000.0, 200)}

    trailing = MagicMock()
    trailing.is_tracking.return_value = True
    trailing.check.return_value = 49_000.0

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_stop_touch(cfg, storage, bar, atr=500.0, real_trailing_stop=trailing)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL"
    assert "cu" in mock_alert.call_args.args[1] or "cũ" in mock_alert.call_args.args[1]


def test_stop_touch_position_sync_none_rejected_critical(cfg, bar, monkeypatch):
    """Stop touch khi chưa từng đồng bộ vị thế (sync_ts is None) -> Từ chối + alert CRITICAL."""
    from trading.real_orders import handle_stop_touch

    now = datetime(2026, 9, 1, 9, 20, tzinfo=TZ)
    storage = _make_storage()
    storage.read_position_sync_ts.side_effect = None
    storage.read_position_sync_ts.return_value = None

    trailing = MagicMock()

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_stop_touch(cfg, storage, bar, atr=500.0, real_trailing_stop=trailing)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "CRITICAL"


# ===========================================================================
# Brief Đợt 10 — Task 5: Trần 100 cổ phiếu cho lệnh MUA thật
# ===========================================================================


def test_task5_buy_capped_at_100_when_sized_500(cfg, bar, monkeypatch):
    """Trường hợp 1: approve_sized trả 500, max_buy_qty = 5000 -> Lệnh BUY ra 100."""
    now = datetime(2026, 9, 1, 9, 10, tzinfo=TZ)
    storage = _make_sized_storage(buying_power=(5000, 5000, 50.0, now - timedelta(minutes=5)))
    risk = RiskManager(capital=500_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_called_once()
    assert storage.create_pending_order.call_args.kwargs["quantity"] == 100


def test_task5_buy_rounds_down_to_0_when_sized_50(cfg, bar, monkeypatch):
    """Trường hợp 2: approve_sized trả 50 -> ra 0 (làm tròn xuống bội 100) -> từ chối."""
    now = datetime(2026, 9, 1, 9, 10, tzinfo=TZ)
    storage = _make_sized_storage(buying_power=(5000, 5000, 50.0, now - timedelta(minutes=5)))
    # Capital 2.5tr, giá 50k, ATR 500 -> qty_cap = 2.5tr*20%/50k = 10, qty_atr = 25 -> sized.qty = 25 < 100
    risk = RiskManager(capital=2_500_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "INFO"


def test_task5_buy_failsafe_when_max_buy_qty_zero(cfg, bar, monkeypatch):
    """Trường hợp 3: max_buy_qty = 0 -> ra 0, không đặt lệnh mua."""
    now = datetime(2026, 9, 1, 9, 10, tzinfo=TZ)
    storage = _make_sized_storage(buying_power=(0, 0, 0.0, now - timedelta(minutes=5)))
    risk = RiskManager(capital=100_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg, storage, risk, "bull", bar, atr=500.0)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] == "INFO"


def test_task5_sell_not_capped_at_100(cfg, bar, monkeypatch):
    """Trường hợp 4: Nhánh SELL với sellable_qty = 500 -> ra 500, KHÔNG bị kẹp trần 100."""
    now = datetime(2026, 9, 1, 9, 10, tzinfo=TZ)
    storage = _make_sized_storage(
        positions={"VCB": RealPosition("VCB", 500, 50_000.0, 500)},
    )
    risk = RiskManager(capital=100_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert"):
        handle_crossover(cfg, storage, risk, "bear", bar, atr=None)

    storage.create_pending_order.assert_called_once()
    assert storage.create_pending_order.call_args.kwargs["quantity"] == 500


# ============ Brief 30 Task 2: Lá chắn cấu hình tài khoản lệnh thật ============


def test_nav_discrepancy_warns_when_ratio_exceeds_threshold(cfg, bar, monkeypatch):
    """1. Tài khoản cấu hình NAV 5.021.712, tài khoản khác NAV 197.517.988 -> WARN có cả 2 số TK và 2 NAV."""
    _warned_nav_discrepancy_accounts.clear()

    now = datetime(2026, 9, 10, 9, 10, tzinfo=TZ)
    storage = _make_storage()
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_021_712.0,
        "0434226": 197_517_988.0,
    }

    cfg_custom = replace(cfg, real_order_account="0434221")
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)

    # Check that WARN alert was emitted for NAV discrepancy
    warn_calls = [c for c in mock_alert.call_args_list if c.args and c.args[0] == "WARN"]
    nav_warns = [
        c for c in warn_calls
        if "tai khoan cau hinh 0434221 co NAV" in str(c.args[1])
    ]
    assert len(nav_warns) == 1
    call_kwargs = nav_warns[0].kwargs
    assert call_kwargs["account"] == "0434221"
    assert call_kwargs["nav"] == 5_021_712.0
    assert call_kwargs["other_account"] == "0434226"
    assert call_kwargs["other_nav"] == 197_517_988.0
    assert call_kwargs["ratio"] >= 10.0


def test_nav_discrepancy_no_warn_when_ratio_below_threshold(cfg, bar, monkeypatch):
    """2. Hai tài khoản NAV xấp xỉ nhau -> KHÔNG WARN."""
    _warned_nav_discrepancy_accounts.clear()

    now = datetime(2026, 9, 10, 9, 10, tzinfo=TZ)
    storage = _make_storage()
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_000_000.0,
        "0434226": 6_000_000.0,
    }

    cfg_custom = replace(cfg, real_order_account="0434221")
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)

    nav_warns = [
        c for c in mock_alert.call_args_list
        if c.args and c.args[0] == "WARN" and "tai khoan cau hinh" in str(c.args[1])
    ]
    assert len(nav_warns) == 0


def test_nav_discrepancy_no_warn_when_single_account(cfg, bar, monkeypatch):
    """3. Chỉ có đúng một tài khoản trong snapshot -> KHÔNG WARN, không nổ."""
    _warned_nav_discrepancy_accounts.clear()

    now = datetime(2026, 9, 10, 9, 10, tzinfo=TZ)
    storage = _make_storage()
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_021_712.0,
    }

    cfg_custom = replace(cfg, real_order_account="0434221")
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)

    nav_warns = [
        c for c in mock_alert.call_args_list
        if c.args and c.args[0] == "WARN" and "tai khoan cau hinh" in str(c.args[1])
    ]
    assert len(nav_warns) == 0


def test_nav_discrepancy_warns_only_once_across_bars(cfg, bar, monkeypatch):
    """4. Cảnh báo phát một lần, không lặp lại ở bar tiếp theo."""
    _warned_nav_discrepancy_accounts.clear()

    now = datetime(2026, 9, 10, 9, 10, tzinfo=TZ)
    storage = _make_storage()
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_021_712.0,
        "0434226": 197_517_988.0,
    }

    cfg_custom = replace(cfg, real_order_account="0434221")
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert") as mock_alert:
        # First bar
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)
        nav_warns_1 = [
            c for c in mock_alert.call_args_list
            if c.args and c.args[0] == "WARN" and "tai khoan cau hinh" in str(c.args[1])
        ]
        assert len(nav_warns_1) == 1

        mock_alert.reset_mock()
        # Second bar (reset positions so it doesn't skip buy because already held)
        storage.read_real_positions.return_value = {}
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)
        nav_warns_2 = [
            c for c in mock_alert.call_args_list
            if c.args and c.args[0] == "WARN" and "tai khoan cau hinh" in str(c.args[1])
        ]
        assert len(nav_warns_2) == 0


def test_nav_discrepancy_does_not_block_order_creation(cfg, bar, monkeypatch):
    """5. Có WARN nhưng lệnh vẫn được xử lý bình thường (không chặn lệnh)."""
    _warned_nav_discrepancy_accounts.clear()

    now = datetime(2026, 9, 10, 9, 10, tzinfo=TZ)
    storage = _make_storage()
    storage.read_buying_power.return_value = (
        10_000,
        10_000,
        50.0,
        now - timedelta(minutes=5),
    )
    storage.read_position_sync_ts.return_value = now - timedelta(minutes=5)
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_021_712.0,
        "0434226": 197_517_988.0,
    }

    cfg_custom = replace(cfg, real_order_account="0434221")
    risk = RiskManager(capital=1_000_000_000.0)

    with patch("trading.real_orders._now", return_value=now), patch("trading.real_orders.alert"):
        handle_crossover(cfg_custom, storage, risk, "bull", bar, atr=500.0)

    # Pending order was still created
    storage.create_pending_order.assert_called_once()
    assert storage.create_pending_order.call_args.kwargs["account_no"] == "0434221"




