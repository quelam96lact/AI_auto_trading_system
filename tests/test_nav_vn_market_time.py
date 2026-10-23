"""Plan 2026-09-03 goi A: compute_nav tinh NAV theo NGAY GIAO DICH + no THAT.

Khong danh dau integration: compute_nav la ham THUAN (static, khong DB) — phai
chay duoc trong `uv run pytest -m "not integration"`. Tai hien dung hai loi
ngay 03/09: (1) gia daily 28/08 (phien gan nhat truoc le 31/08-02/09) bi loai
nham vi dem 6 ngay lich > 5; (2) debt nap cung 0.0 lam NAV tai khoan margin
= 0.0 sai ~160tr.
"""

import asyncio
from datetime import date, datetime
from types import SimpleNamespace

from trading.calendar_vn import TZ, trading_days_between
from trading.collector.account_sync import _sync_nav
from trading.storage.db import Storage

# 28/08/2026 = thu 6; 31/08-02/09 = nghi Quoc khanh (config.yaml).
HOLIDAYS = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})
NOW_0309 = datetime(2026, 9, 3, 9, 0, tzinfo=TZ)


def _vn_price_age_ok(price_ts: datetime, now: datetime) -> bool:
    """Vị từ thật account_sync truyen cho compute_nav (2.3): gia con tuoi neu
    so ngay GIAO DICH giua price_ts va now <= 5."""
    return trading_days_between(price_ts, now, HOLIDAYS) <= 5


def test_gia_28_08_con_tuoi_sau_ngay_le():
    """Gia daily 28/08 nhin tu 03/09: 6 ngay LICH nhung 1 ngay GIAO DICH -> tinh
    vao NAV (truoc day loai nham, NAV = 0)."""
    nav, unpriced = Storage.compute_nav(
        0.0,
        68_607_848.0,
        {"CAP": 1200},
        lambda sym: (90.0, datetime(2026, 8, 28, tzinfo=TZ)),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    assert unpriced == []
    assert nav == -68_607_848.0 + 1200 * 90.0


def test_gia_qua_5_ngay_giao_dich_van_loai():
    """Gia 20/08 (nhieu hon 5 ngay giao dich truoc 03/09) -> van loai: sua loi
    ngay lich KHONG duoc phep loai bo fail-safe tuoi gia."""
    nav, unpriced = Storage.compute_nav(
        100_000.0,
        0.0,
        {"CAP": 100},
        lambda sym: (20.0, datetime(2026, 8, 20, tzinfo=TZ)),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    assert nav == 100_000.0
    assert unpriced == ["CAP"]


def test_debt_that_thay_vi_0_margin_account_ra_nav_dung():
    """Tai khoan margin: withdrawable=0, total_debt=68,6tr, co vi the -> NAV =
    -debt + gia tri cp (truoc day debt=0.0 lam NAV = 0.0 sai)."""
    nav, unpriced = Storage.compute_nav(
        0.0,
        68_607_848.0,
        {"CAP": 1200, "HCM": 1000},
        lambda sym: {
            "CAP": (15_000.0, datetime(2026, 9, 3, tzinfo=TZ)),
            "HCM": (90_000.0, datetime(2026, 9, 3, tzinfo=TZ)),
        }[sym],
        NOW_0309,
    )
    assert unpriced == []
    assert nav == -68_607_848.0 + 1200 * 15_000.0 + 1000 * 90_000.0


def test_vi_the_rong_nav_bang_cash_tru_no():
    """0434221 khong giu ma that (2.6b — da do, khong phai loi): positions rong
    -> NAV = withdrawable - no. Test chan khong ai 'sua' thanh cong them gi."""
    nav, unpriced = Storage.compute_nav(
        5_021_459.0,
        0.0,
        {},
        lambda sym: None,
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    assert nav == 5_021_459.0
    assert unpriced == []


# ============ Brief 189: test compute_nav voi pending_buy_cost ============


def test_compute_nav_with_pending_buy_cost_adds_cost():
    """Brief 189 Buoc 1: co pending_buy_cost=2_746_850 thi NAV lon hon dung 2.746.850."""
    cash = 100_000.0
    debt = 10_000.0
    pending_cost = 2_746_850.0
    base_nav, _ = Storage.compute_nav(
        cash,
        debt,
        {"VCB": 100},
        lambda sym: (90.0, NOW_0309),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    nav_with_pending, unpriced = Storage.compute_nav(
        cash,
        debt,
        {"VCB": 100},
        lambda sym: (90.0, NOW_0309),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
        pending_buy_cost=pending_cost,
    )
    assert unpriced == []
    assert nav_with_pending - base_nav == pending_cost
    assert nav_with_pending == cash - debt + 100 * 90.0 + pending_cost


def test_compute_nav_omitted_pending_buy_cost_preserves_old_behavior():
    """Brief 189 Buoc 1: khong truyen pending_buy_cost thi NAV bang ket qua cu (default 0.0)."""
    cash = 50_000.0
    debt = 5_000.0
    nav_default, unpriced_default = Storage.compute_nav(
        cash,
        debt,
        {"VCB": 50},
        lambda sym: (90.0, NOW_0309),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    nav_explicit_zero, unpriced_explicit = Storage.compute_nav(
        cash,
        debt,
        {"VCB": 50},
        lambda sym: (90.0, NOW_0309),
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
        pending_buy_cost=0.0,
    )
    assert nav_default == nav_explicit_zero
    assert unpriced_default == unpriced_explicit == []


def test_compute_nav_pending_buy_cost_preserves_unpriced_behavior():
    """Brief 189 Buoc 1: ma khong dinh gia duoc van tinh 0 va van nam trong unpriced khi co pending_buy_cost."""
    cash = 80_000.0
    debt = 0.0
    pending_cost = 2_746_850.0
    nav, unpriced = Storage.compute_nav(
        cash,
        debt,
        {"UNPRICED_SYM": 1000},
        lambda sym: None,
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
        pending_buy_cost=pending_cost,
    )
    assert unpriced == ["UNPRICED_SYM"]
    assert nav == cash - debt + pending_cost


# ============ vong bo sung (03/09 18:10): test NOI DAY _sync_nav ============
# Bug that nam o noi day (account_sync truyen 0.0 / bo quen price_age_ok),
# khong phai cong thuc. Test nay goi _sync_nav THAT (khong stub), FakeStorage
# chi thay phan DB doc/ghi — compute_nav van la ham that (delegate).


class _NavFakeStorage:
    """Storage gia cho _sync_nav: balance + positions + bar co dinh, bat
    record_nav de doc ket qua, compute_nav = ham THAT cua Storage."""

    def __init__(
        self,
        withdrawable,
        total_debt,
        positions,
        bar_row,
        buy_t0=0.0,
        buy_t1=0.0,
        buy_t2=0.0,
        pending_buy_cost=None,
        bought_quantities=None,
    ):
        self._bal_with_debt = (withdrawable, total_debt, NOW_0309)
        cost = buy_t0 + buy_t1 if pending_buy_cost is None else pending_buy_cost
        self._bal_for_nav = (withdrawable, total_debt, cost, NOW_0309)
        self._positions = positions  # symbol -> qty
        self._bought_quantities = bought_quantities or {}
        self._bar = bar_row  # (ts, close) hoac None
        self.nav_calls = []  # (account_no, ts, nav, unpriced) tu record_nav
        self.compute_nav_calls = []  # kiem tra tham so truyen vao

    def read_account_balance_with_debt(self, account_no):
        return self._bal_with_debt

    def read_balance_for_nav(self, account_no):
        return self._bal_for_nav

    def read_real_positions(self, account_no):
        return {
            s: SimpleNamespace(qty=q, bought_quantity=self._bought_quantities.get(s, 0))
            for s, q in self._positions.items()
        }

    def read_latest_bar(self, symbol):
        return self._bar

    def record_nav(self, account_no, ts, nav, unpriced_symbols):
        self.nav_calls.append((account_no, nav, unpriced_symbols))

    def compute_nav(self, cash, debt, positions, price_fn, now, **kwargs):
        # delegate ham THAT — chi chan de ghi lai tham so
        self.compute_nav_calls.append((debt, kwargs.get("price_age_ok")))
        return Storage.compute_nav(cash, debt, positions, price_fn, now, **kwargs)


def _captured_nav(
    withdrawable,
    total_debt,
    positions,
    bar_row,
    buy_t0=0.0,
    buy_t1=0.0,
    buy_t2=0.0,
    pending_buy_cost=None,
    bought_quantities=None,
):
    storage = _NavFakeStorage(
        withdrawable,
        total_debt,
        positions,
        bar_row,
        buy_t0=buy_t0,
        buy_t1=buy_t1,
        buy_t2=buy_t2,
        pending_buy_cost=pending_buy_cost,
        bought_quantities=bought_quantities,
    )
    asyncio.run(_sync_nav("0434226", NOW_0309, storage, HOLIDAYS))
    assert (
        len(storage.nav_calls) == 1
    ), f"record_nav phai duoc goi dung 1 lan, thuc te: {storage.nav_calls}"
    return storage


def test_sync_nav_truyen_no_that():
    """NOI DAY lop 1: _sync_nav phai truyen total_debt doc tu snapshot vao
    compute_nav (khong phai 0.0). Tai khoan margin: withdrawable=0, no
    68.607.848, giu 1200 CAP gia 90 -> NAV = -68.607.848 + 108.000."""
    st = _captured_nav(
        0.0,
        68_607_848.0,
        {"CAP": 1200},
        (datetime(2026, 8, 28, tzinfo=TZ), 90.0),
    )
    # compute_nav nhan debt = 68.607.848 (khong phai 0.0)
    assert st.compute_nav_calls[0][0] == 68_607_848.0
    acc, nav, unpriced = st.nav_calls[0]
    assert acc == "0434226"
    assert nav == -68_607_848.0 + 1200 * 90.0
    assert unpriced == []


def test_sync_nav_truyen_vi_tu_tuoi_gia():
    """NOI DAY lop 2: _sync_nav phai truyen price_age_ok vao compute_nav (khong
    bo sot ve dem ngay LICH). Moc 28/08 -> 03/09: 6 ngay lich (loi cu => loai)
    nhung 1 ngay giao dich (dung => giu)."""
    st = _captured_nav(
        0.0,
        68_607_848.0,
        {"CAP": 1200},
        (datetime(2026, 8, 28, tzinfo=TZ), 90.0),
    )
    # compute_nav nhan price_age_ok (khong None)
    assert st.compute_nav_calls[0][1] is not None
    _, nav, unpriced = st.nav_calls[0]
    assert unpriced == []  # gia 28/08 con tuoi sau le -> khong loai
    assert nav == -68_607_848.0 + 1200 * 90.0


# ============ Brief 189 Buoc 3: 4 test vong doi lenh mua _sync_nav ============

TCX_PRICE = 27_350.0
W_BASE = 10_000_000.0
ORDER_COST = 2_746_850.0


def test_sync_nav_lifecycle_state_a_t0_post_fill():
    """Brief 189: Trang thai (A) T0 sau khop:
    quantity TCX = 68, withdrawable = W - 2.746.850, buy_t0 = 2.746.850, buy_t1 = 0, buy_t2 = 0.
    NAV (A) phai bang NAV truoc khop (W, 68 TCX, khong buy_*)."""
    nav_pre = W_BASE + 68 * TCX_PRICE
    st_a = _captured_nav(
        W_BASE - ORDER_COST,
        0.0,
        {"TCX": 68},
        (NOW_0309, TCX_PRICE),
        buy_t0=ORDER_COST,
        buy_t1=0.0,
        buy_t2=0.0,
        bought_quantities={"TCX": 100},
    )
    acc, nav_a, unpriced = st_a.nav_calls[0]
    assert acc == "0434226"
    assert unpriced == []
    assert nav_a == nav_pre


def test_sync_nav_lifecycle_state_b_morning_t1():
    """Brief 189: Trang thai (B) sang T+1:
    quantity TCX = 68, withdrawable = W - 2.746.850, buy_t0 = 0, buy_t1 = 2.746.850, buy_t2 = 0.
    NAV (B) phai bang NAV truoc khop (W, 68 TCX, khong buy_*)."""
    nav_pre = W_BASE + 68 * TCX_PRICE
    st_b = _captured_nav(
        W_BASE - ORDER_COST,
        0.0,
        {"TCX": 68},
        (NOW_0309, TCX_PRICE),
        buy_t0=0.0,
        buy_t1=ORDER_COST,
        buy_t2=0.0,
        bought_quantities={"TCX": 0},
    )
    acc, nav_b, unpriced = st_b.nav_calls[0]
    assert acc == "0434226"
    assert unpriced == []
    assert nav_b == nav_pre


def test_sync_nav_lifecycle_state_c_after_night_update():
    """Brief 189: Trang thai (C) sau cap nhat dem:
    quantity TCX = 168 (100 co phieu da vao quantity), withdrawable = W - 2.746.850,
    buy_t0 = 0, buy_t1 = 0, buy_t2 = 2.746.850 (khong tinh buy_t2).
    NAV (C) phai bang NAV truoc khop + 100 * 27.350 - 2.746.850 (chenh gia/phi)."""
    nav_pre = W_BASE + 68 * TCX_PRICE
    st_c = _captured_nav(
        W_BASE - ORDER_COST,
        0.0,
        {"TCX": 168},
        (NOW_0309, TCX_PRICE),
        buy_t0=0.0,
        buy_t1=0.0,
        buy_t2=ORDER_COST,
        bought_quantities={"TCX": 0},
    )
    acc, nav_c, unpriced = st_c.nav_calls[0]
    assert acc == "0434226"
    assert unpriced == []
    assert nav_c == nav_pre + 100 * TCX_PRICE - ORDER_COST


def test_sync_nav_lifecycle_state_c_no_double_counting_buy_t2():
    """Brief 189: Trang thai (C) KHONG DUOC lon hon NAV truoc khop cong 100 * 27.350.
    Bat loi tinh trung buy_t2 (khi co phieu da vao quantity ma van cong buy_t2)."""
    nav_pre = W_BASE + 68 * TCX_PRICE
    st_c = _captured_nav(
        W_BASE - ORDER_COST,
        0.0,
        {"TCX": 168},
        (NOW_0309, TCX_PRICE),
        buy_t0=0.0,
        buy_t1=0.0,
        buy_t2=ORDER_COST,
        bought_quantities={"TCX": 0},
    )
    _, nav_c, _ = st_c.nav_calls[0]
    assert nav_c <= nav_pre + 100 * TCX_PRICE
    assert nav_c < nav_pre + 100 * TCX_PRICE + ORDER_COST
