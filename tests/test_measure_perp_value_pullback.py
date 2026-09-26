"""Test hàm thuần của `scripts/measure_perp_value_pullback.py` — `mag_ok` (brief dot 106 §2.1)."""

from datetime import UTC, datetime, timedelta

from scripts.measure_perp_orderflow import FlowRow
from scripts.measure_perp_value_pullback import MAG_WINDOW, mag_ok_series

DAY = datetime(2020, 3, 2, tzinfo=UTC)


def _row(ts: datetime, *, delta: float, volume: float = 100.0) -> FlowRow:
    """FlowRow có delta mong muốn, vì `delta = 2*taker_buy_volume - volume`."""
    return FlowRow(
        ts=ts,
        volume=volume,
        quote_volume=volume * 10.0,
        taker_buy_volume=(delta + volume) / 2.0,
        taker_buy_quote_volume=volume * 5.0,
    )


def _rows(deltas: list[float]) -> list[FlowRow]:
    return [_row(DAY + timedelta(hours=i), delta=d) for i, d in enumerate(deltas)]


def test_mag_ok_manual_window_of_20():
    """|delta_t| so với trung vị của |delta| 20 nến TRƯỚC."""
    rows = _rows([float(i) for i in range(1, 21)] + [25.0, 5.0])
    ok = mag_ok_series(rows)
    assert MAG_WINDOW == 20
    assert ok[rows[19].ts] is None  # chưa đủ 20 nến trước
    assert ok[rows[20].ts] is True  # 25 >= trung vị(1..20) = 10,5
    assert ok[rows[21].ts] is False  # 5 < trung vị(2..20, 25) = 11,5


def test_mag_ok_window_excludes_bar_t():
    """Cửa sổ KHÔNG gồm nến t: 45 < trung vị([1]*10 + [100]*10) = 50,5 -> False.

    Nếu cửa sổ gồm cả nến t (21 giá trị) thì trung vị = 45 và kết quả là True —
    test này phân biệt hai cách hiểu.
    """
    rows = _rows([1.0] * 10 + [100.0] * 10 + [45.0])
    ok = mag_ok_series(rows)
    assert ok[rows[20].ts] is False


def test_mag_ok_unaffected_by_bar_t_plus_1():
    """Sửa nến t+1 không đổi kết quả tại t."""
    rows = _rows([float(i) for i in range(1, 21)] + [25.0, 5.0])
    base = mag_ok_series(rows)
    edited = list(rows)
    edited[21] = _row(rows[21].ts, delta=999.0)
    mod = mag_ok_series(edited)
    assert base[rows[20].ts] is True
    assert mod[rows[20].ts] is True  # sửa nến t+1 không đổi kết quả tại t


def test_mag_ok_none_when_window_row_invalid():
    """Thiếu dữ liệu trong cửa sổ -> không nội suy, trả None."""
    deltas = [float(i) for i in range(1, 21)] + [25.0]
    rows = _rows(deltas)
    rows[5] = _row(rows[5].ts, delta=0.0, volume=0.0)  # quote/volume = 0 -> flow không hợp lệ
    ok = mag_ok_series(rows)
    assert ok[rows[20].ts] is None


def test_mag_ok_none_when_current_row_invalid():
    rows = _rows([float(i) for i in range(1, 21)] + [25.0])
    rows[20] = _row(rows[20].ts, delta=0.0, volume=0.0)
    ok = mag_ok_series(rows)
    assert ok[rows[20].ts] is None


def test_mag_ok_median_is_even_count_average():
    """Trung vị của 20 giá trị = trung bình hai giá trị giữa."""
    rows = _rows([10.0] * 20 + [12.0])
    ok = mag_ok_series(rows)
    assert ok[rows[20].ts] is True  # 12 >= 10
    rows = _rows([10.0] * 20 + [10.0])
    assert mag_ok_series(rows)[rows[20].ts] is True  # >= , không phải >
    rows = _rows([10.0] * 20 + [9.99])
    assert mag_ok_series(rows)[rows[20].ts] is False


def test_mag_ok_bars_without_ts_order_keeper():
    """Hàm dùng đúng thứ tự danh sách (đã sắp theo ts từ loader)."""
    rows = _rows([float(i) for i in range(1, 22)])
    ok = mag_ok_series(rows)
    assert len(ok) == len(rows)
    assert set(ok) == {r.ts for r in rows}
    assert ok[rows[20].ts] is True  # 21 >= trung vị(1..20) = 10,5