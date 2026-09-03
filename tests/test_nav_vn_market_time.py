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
        0.0, 68_607_848.0, {"CAP": 1200},
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
        100_000.0, 0.0, {"CAP": 100},
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
        0.0, 68_607_848.0, {"CAP": 1200, "HCM": 1000},
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
        5_021_459.0, 0.0, {},
        lambda sym: None,
        NOW_0309,
        price_age_ok=_vn_price_age_ok,
    )
    assert nav == 5_021_459.0
    assert unpriced == []


# ============ vong bo sung (03/09 18:10): test NOI DAY _sync_nav ============
# Bug that nam o noi day (account_sync truyen 0.0 / bo quen price_age_ok),
# khong phai cong thuc. Test nay goi _sync_nav THAT (khong stub), FakeStorage
# chi thay phan DB doc/ghi — compute_nav van la ham that (delegate).


class _NavFakeStorage:
    """Storage gia cho _sync_nav: balance + positions + bar co dinh, bat
    record_nav de doc ket qua, compute_nav = ham THAT cua Storage."""

    def __init__(self, withdrawable, total_debt, positions, bar_row):
        self._bal = (withdrawable, total_debt, NOW_0309)
        self._positions = positions  # symbol -> qty
        self._bar = bar_row  # (ts, close) hoac None
        self.nav_calls = []  # (account_no, ts, nav, unpriced) tu record_nav
        self.compute_nav_calls = []  # kiem tra tham so truyen vao

    def read_account_balance_with_debt(self, account_no):
        return self._bal

    def read_real_positions(self, account_no):
        return {s: SimpleNamespace(qty=q) for s, q in self._positions.items()}

    def read_latest_bar(self, symbol):
        return self._bar

    def record_nav(self, account_no, ts, nav, unpriced_symbols):
        self.nav_calls.append((account_no, nav, unpriced_symbols))

    def compute_nav(self, cash, debt, positions, price_fn, now, **kwargs):
        # delegate ham THAT — chi chan de ghi lai tham so
        self.compute_nav_calls.append((debt, kwargs.get("price_age_ok")))
        return Storage.compute_nav(cash, debt, positions, price_fn, now, **kwargs)


def _captured_nav(withdrawable, total_debt, positions, bar_row):
    storage = _NavFakeStorage(withdrawable, total_debt, positions, bar_row)
    asyncio.run(_sync_nav("0434226", NOW_0309, storage, HOLIDAYS))
    assert len(storage.nav_calls) == 1, f"record_nav phai duoc goi dung 1 lan, thuc te: {storage.nav_calls}"
    return storage


def test_sync_nav_truyen_no_that():
    """NOI DAY lop 1: _sync_nav phai truyen total_debt doc tu snapshot vao
    compute_nav (khong phai 0.0). Tai khoan margin: withdrawable=0, no
    68.607.848, giu 1200 CAP gia 90 -> NAV = -68.607.848 + 108.000."""
    st = _captured_nav(
        0.0, 68_607_848.0, {"CAP": 1200},
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
        0.0, 68_607_848.0, {"CAP": 1200},
        (datetime(2026, 8, 28, tzinfo=TZ), 90.0),
    )
    # compute_nav nhan price_age_ok (khong None)
    assert st.compute_nav_calls[0][1] is not None
    _, nav, unpriced = st.nav_calls[0]
    assert unpriced == []  # gia 28/08 con tuoi sau le -> khong loai
    assert nav == -68_607_848.0 + 1200 * 90.0
