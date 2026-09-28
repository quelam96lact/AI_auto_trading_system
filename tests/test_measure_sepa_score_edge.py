"""Unit tests cho scripts/measure_sepa_score_edge.py — Brief đợt 120.

Tuân thủ nghiêm ngặt:
- Hàm thuần, ví dụ tính tay ghi trong test.
- CẤM dựng expected bằng cách viết lại công thức trong thân test — ghim số literal.
- Thiết kế để bắt chết 5 phép phá thử bắt buộc (§5):
  1. Điểm tại t tính từ nến t+1 (nhìn trước).
  2. Sự kiện = mọi ngày 7/7, bỏ điều kiện chuyển trạng thái.
  3. Bỏ excess_for_event, dùng lợi suất thô thay vì trừ đối chứng cùng ngày.
  4. Bỏ apply_cooldown.
  5. Bỏ lọc exclusions.txt.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from scripts.measure_sepa_score_edge import (
    SepaEvent,
    assign_event_excess,
    compute_rolling_rs_raw,
    compute_score_series,
    evaluate_gate,
    evaluate_gate_mean,
    find_score_events,
    resolve_universe,
    run_sepa_measurement,
)
from scripts.screen_vcp_daily import (
    MIN_TURNOVER_VND,
    TARGET_KS,
    TURNOVER_WINDOW,
    ControlEntry,
    SymbolData,
    excess_for_event,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.stock_study import (
    TREND_MIN_BARS,
    BasketEntry,
    apply_cooldown,
    basket_for_day,
    make_basket_entry,
    rolling_max,
    rolling_mean,
    rolling_min,
)


def _make_bar(idx: int, close: float, high: float | None = None, low: float | None = None, volume: float = 1_000_000.0) -> Bar:
    """Tạo Bar giả lập đơn giản cho test."""
    h = high if high is not None else close * 1.01
    lo = low if low is not None else close * 0.99
    op = close
    ts = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)
    return Bar(
        symbol="TEST",
        ts=ts,
        open=op,
        high=h,
        low=lo,
        close=close,
        volume=volume,
        source="test",
    )


# --- Test 1: Bắt đột biến 1 (Nhìn trước nến t+1) -----------------------------------

def test_compute_score_series_no_lookahead():
    """Kiểm tra điểm tại nến t KHÔNG nhìn trước dữ liệu nến t+1.

    Đột biến 1: Tính điểm tại t dùng nến t+1.
    Nếu bị đột biến 1, scores[252] sẽ nhận điểm của nến 253 thay vì nến 252.
    """
    # 252 nến đầu tiên đi ngang ở mức 10.0 (chưa đủ điều kiện tăng trưởng)
    bars: list[Bar] = [_make_bar(i, 10.0) for i in range(252)]
    # Nến 252: tăng nhẹ lên 10.1 (chưa đủ 30% trên đáy 52 tuần)
    bars.append(_make_bar(252, 10.1))
    # Nến 253: tăng vọt lên 20.0 (thỏa mãn c6: close >= 1.30 * low252)
    bars.append(_make_bar(253, 20.0))

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]

    s50 = rolling_mean(closes, 50)
    s150 = rolling_mean(closes, 150)
    s200 = rolling_mean(closes, 200)
    w_low = rolling_min(lows, 252)
    w_high = rolling_max(highs, 252)

    scores = compute_score_series(bars, s50, s150, s200, w_low, w_high)

    # Nến 252: giá 10.1, đáy 9.9 -> 10.1 < 1.3 * 9.9 = 12.87 -> c6 False (điểm = 6).
    # Nến 253: giá 20.0, đáy 9.9 -> 20.0 >= 12.87 -> c6 True (điểm = 7).
    # Điểm tại nến 252 phải khác nến 253.
    # Giá trị literal được ghim: scores[252] == 6, scores[253] == 7
    assert scores[252] == 6
    assert scores[253] == 7


# --- Test 2: Bắt đột biến 2 (Bỏ điều kiện chuyển trạng thái, lấy mọi ngày 7/7) ----

def test_find_score_events_transition_vs_state():
    """Kiểm tra sự kiện transition chỉ nhận khi chuyển từ < 7 sang 7.

    Đột biến 2: Bỏ điều kiện chuyển trạng thái, coi mọi ngày có điểm 7 là sự kiện.
    Nếu bị đột biến 2, các ngày 254 và 255 (vẫn giữ điểm 7) sẽ bị nhận nhầm làm sự kiện mới.
    """
    bars = [_make_bar(i, 10.0, volume=1_000_000.0) for i in range(260)]
    # turnover20 luôn đạt 1 tỷ đồng
    turnover20: list[float | None] = [2_000_000_000.0] * 260

    # Chuỗi điểm:
    # 252: 6
    # 253: 7 (transition từ 6 -> 7) -> ĐƯỢC NHẬN
    # 254: 7 (duy trì 7)            -> PHẢI BỎ
    # 255: 7 (duy trì 7)            -> PHẢI BỎ
    # 256: 5 (giảm về 5)           -> BỎ
    # 257: 7 (transition từ 5 -> 7) -> ĐƯỢC NHẬN (với cooldown = 1)
    scores = [0] * 252 + [6, 7, 7, 7, 5, 7, 6, 6]

    events_transition = find_score_events(
        bars, scores, target_score=7, turnover20=turnover20, mode="transition", cooldown=1
    )
    # Literal: chỉ có nến 253 và 257 là bước chuyển trạng thái
    assert events_transition == [253, 257]

    # Kiểm tra song song với mode="state"
    events_state = find_score_events(
        bars, scores, target_score=7, turnover20=turnover20, mode="state", cooldown=1
    )
    # Mode state với cooldown 1 sẽ nhận 253, 255, 257
    assert events_state == [253, 255, 257]


# --- Test 3: Bắt đột biến 3 (Bỏ excess_for_event, dùng lợi suất thô) --------------

def test_excess_for_event_subtraction():
    """Kiểm tra lợi suất vượt trội bắt buộc phải trừ đối chứng rổ cùng ngày.

    Đột biến 3: Bỏ excess_for_event, gán thẳng lợi suất thô r.
    Nếu bị đột biến 3, giá trị trả về là +0.05 thay vì -0.03.
    """
    r_event = 0.05  # Lợi suất mã sự kiện: +5%
    # Rổ 5 mã đối chứng cùng ngày, đều có r20 = +0.08 (+8%)
    peers = [
        ControlEntry("SYM1", 0.01, 0.02, 0.08),
        ControlEntry("SYM2", 0.01, 0.02, 0.08),
        ControlEntry("SYM3", 0.01, 0.02, 0.08),
        ControlEntry("SYM4", 0.01, 0.02, 0.08),
        ControlEntry("SYM5", 0.01, 0.02, 0.08),
    ]

    baseline, excess, n = excess_for_event(r_event, peers, 20)

    # Ghim số literal: baseline = 0.08, excess = 0.05 - 0.08 = -0.03 (-3%)
    assert baseline == 0.08
    assert round(excess, 4) == -0.03
    assert n == 5

    # Kiểm tra qua hàm assign_event_excess của measure_sepa_score_edge
    ev = SepaEvent(
        symbol="TEST",
        day=datetime(2020, 1, 1, tzinfo=UTC).date(),
        exchange="HOSE",
        entry_open=10.0,
        score=7,
        r={20: r_event},
    )
    assign_event_excess(ev, peers, ks=(20,))
    assert ev.excess[20] is not None
    assert round(ev.excess[20], 4) == -0.03


# --- Test 4: Bắt đột biến 4 (Bỏ apply_cooldown) ------------------------------------

def test_apply_cooldown_strictly_enforced():
    """Kiểm tra thời gian giãn cách COOLDOWN_BARS = 20 được thực thi nghiêm ngặt.

    Đột biến 4: Bỏ apply_cooldown.
    Nếu bị đột biến 4, danh sách sự kiện giữ nguyên cả 5 chỉ số thay vì 3.
    """
    cand = [260, 265, 275, 281, 305]
    cooldown = 20

    # 260: giữ (last = 260)
    # 265: bỏ (265 - 260 = 5 <= 20)
    # 275: bỏ (275 - 260 = 15 <= 20)
    # 281: giữ (281 - 260 = 21 > 20, last = 281)
    # 305: giữ (305 - 281 = 24 > 20, last = 305)
    kept = apply_cooldown(cand, cooldown=cooldown)

    # Ghim số literal
    assert kept == [260, 281, 305]

    # Kiểm tra trực tiếp hàm find_score_events của measure_sepa_score_edge
    bars = [_make_bar(i, 10.0, volume=1_000_000.0) for i in range(320)]
    turnover20: list[float | None] = [2_000_000_000.0] * 320
    scores = [0] * 320
    for idx in cand:
        scores[idx - 1] = 6
        scores[idx] = 7

    ev_kept = find_score_events(bars, scores, target_score=7, turnover20=turnover20, mode="transition", cooldown=20)
    assert ev_kept == [260, 281, 305]


# --- Test 5: Bắt đột biến 5 (Bỏ lọc exclusions.txt) --------------------------------

def test_exclusions_loaded_and_filtered(tmp_path):
    """Kiểm tra loại bỏ đúng các mã trong exclusions.txt.

    Đột biến 5: Bỏ lọc exclusions.txt.
    Nếu bị đột biến 5, mã BAD1 vẫn nằm trong universe.
    """
    excl_file = tmp_path / "test_exclusions.txt"
    excl_file.write_text("BAD1\nBAD2\n", encoding="utf-8")

    class MockStorage:
        class ConnCtx:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def execute(self, sql):
                if "bars_daily" in sql:
                    return [("AAA",), ("BAD1",), ("BBB",), ("BAD2",), ("CCC",)]
                return [("AAA", "HOSE"), ("BAD1", "HOSE"), ("BBB", "HNX"), ("BAD2", "UPCOM"), ("CCC", "HOSE")]
        def conn(self):
            return self.ConnCtx()

    storage = MockStorage()
    universe, _exchange, n_all, excluded = resolve_universe(storage, str(excl_file))

    # Ghim literal: universe chỉ còn AAA, BBB, CCC; n_all = 5, len(excluded) = 2
    assert universe == ["AAA", "BBB", "CCC"]
    assert "BAD1" not in universe
    assert "BAD2" not in universe
    assert n_all == 5
    assert len(excluded) == 2


# --- Test 6: Kiểm tra 4 điều kiện cổng đánh giá -----------------------------------

def test_evaluate_gate_logic():
    """Kiểm tra logic cổng chính: chỉ ĐẠT khi cả 4 điều kiện cùng thỏa mãn."""
    # Case 1: Đạt cả 4 điều kiện
    passed, details = evaluate_gate(
        median_excess_k20=0.025,
        n_events=120,
        boot_ci=(0.005, 0.045),
        holm_pass=True,
    )
    assert passed is True
    assert details["passed_all"] is True

    # Case 2: Hỏng điều kiện 1 (median <= 0)
    p2, d2 = evaluate_gate(
        median_excess_k20=-0.01,
        n_events=120,
        boot_ci=(0.005, 0.045),
        holm_pass=True,
    )
    assert p2 is False
    assert d2["cond1_median_gt_0"] is False

    # Case 3: Hỏng điều kiện 2 (n_events < 100)
    p3, d3 = evaluate_gate(
        median_excess_k20=0.025,
        n_events=85,
        boot_ci=(0.005, 0.045),
        holm_pass=True,
    )
    assert p3 is False
    assert d3["cond2_min_events"] is False

    # Case 4: Hỏng điều kiện 3 (KTC chứa 0)
    p4, d4 = evaluate_gate(
        median_excess_k20=0.025,
        n_events=120,
        boot_ci=(-0.010, 0.045),
        holm_pass=True,
    )
    assert p4 is False
    assert d4["cond3_ci_excludes_0"] is False

    # Case 5: Hỏng điều kiện 4 (Holm không đạt)
    p5, d5 = evaluate_gate(
        median_excess_k20=0.025,
        n_events=120,
        boot_ci=(0.005, 0.045),
        holm_pass=False,
    )
    assert p5 is False
    assert d5["cond4_holm_pass"] is False


# --- Test 7: Tính toán RS_raw tính tay --------------------------------------------

def test_compute_rolling_rs_raw_hand_calculated():
    """Kiểm tra RS_raw theo đúng công thức chuẩn với số tính tay literal."""
    # Tạo 253 nến
    closes = [10.0] * 253
    # Ghim mốc cụ thể:
    # idx 252 (P) = 25.0
    # idx 189 (P_63 = 252 - 63) = 20.0
    # idx 126 (P_126 = 252 - 126) = 15.0
    # idx 63  (P_189 = 252 - 189) = 12.0
    # idx 0   (P_252 = 252 - 252) = 10.0
    closes[252] = 25.0
    closes[189] = 20.0
    closes[126] = 15.0
    closes[63] = 12.0
    closes[0] = 10.0

    bars = [_make_bar(i, closes[i]) for i in range(253)]
    rs_raw = compute_rolling_rs_raw(bars)

    # Tính tay:
    # 0.4 * (25/20 - 1) = 0.4 * 0.25 = 0.10
    # 0.2 * (25/15 - 1) = 0.2 * 0.66666667 = 0.13333333
    # 0.2 * (25/12 - 1) = 0.2 * 1.08333333 = 0.21666667
    # 0.2 * (25/10 - 1) = 0.2 * 1.50 = 0.30
    # Tổng = 0.10 + 0.13333333 + 0.21666667 + 0.30 = 0.75
    val = rs_raw[252]
    assert val is not None
    assert round(val, 4) == 0.75


# --- Tests 3a - 3f: Các bài test rổ trung tính và evaluate_gate_mean (Brief đợt 123) ---

def _make_daily_bar_seq(sym: str, n: int, start_date: date, p: float = 20_000.0, vol: float = 100_000.0) -> list[Bar]:
    return [
        Bar(
            symbol=sym,
            ts=datetime.combine(start_date + timedelta(days=i), datetime.min.time(), tzinfo=TZ),
            open=p,
            high=p * 1.01,
            low=p * 0.99,
            close=p,
            volume=vol,
            source="test",
        )
        for i in range(n)
    ]


class _MockDailyStorage:
    def __init__(self, data: dict[str, list[Bar]]):
        self.data = data

    class _Conn:
        def __init__(self, syms: list[str]):
            self.syms = syms

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql: str):
            if "bars_daily" in sql:
                return [(s,) for s in self.syms]
            return [(s, "HOSE") for s in self.syms]

    def conn(self):
        return self._Conn(list(self.data.keys()))

    def read_daily_bars(self, sym: str, s: datetime, e: datetime) -> list[Bar]:
        return list(self.data.get(sym, []))


def test_3a_neutral_basket_contains_non_trend_symbol():
    """Cổng 3a: Rổ trung tính CHỨA một mã KHÔNG đạt trend_ok nhưng đủ thanh khoản và vào được lệnh.

    Đột biến 1: Trong chế độ neutral, chỉ cho vào rổ các mã có sd.trend_ok(i) đúng -> test 3a phải RED.
    """
    start_d = date(2020, 1, 6)
    bars_evt = _make_daily_bar_seq("AAA", 300, start_d, p=20_000.0, vol=100_000.0)
    bars_down = _make_daily_bar_seq("BBB", 300, start_d, p=25_000.0, vol=100_000.0)

    # BBB là chuỗi nến đi ngang nên không đạt 7/7 trend_ok (trend_ok = False)
    sd_down = SymbolData.build("BBB", "HOSE", bars_down)
    assert not sd_down.trend_ok(252)

    # make_basket_entry trực tiếp vẫn nhận BBB
    e_down = make_basket_entry(
        "BBB",
        bars_down,
        252,
        "HOSE",
        min_turnover=MIN_TURNOVER_VND,
        window=TURNOVER_WINDOW,
        ks=TARGET_KS,
    )
    assert e_down is not None

    # Chạy qua run_sepa_measurement ở chế độ neutral
    storage = _MockDailyStorage({"AAA": bars_evt, "BBB": bars_down})
    res = run_sepa_measurement(storage, no_exclusions=True, basket="neutral")
    first_day = min(res["neutral_basket_by_day"].keys())

    # Rổ trung tính của ngày đầu tiên PHẢI chứa BBB (dù trend_ok = False)
    assert "BBB" in res["neutral_basket_by_day"][first_day]


def test_3b_neutral_basket_excludes_low_liquidity_symbol():
    """Cổng 3b: Rổ trung tính KHÔNG chứa mã dưới ngưỡng thanh khoản."""
    start_d = date(2020, 1, 6)
    # vol = 10 -> turnover = 20_000 * 10 = 200_000 VND << 1_000_000_000 VND
    bars_low = _make_daily_bar_seq("LOW", 50, start_d, p=20_000.0, vol=10.0)
    e = make_basket_entry(
        "LOW",
        bars_low,
        25,
        "HOSE",
        min_turnover=MIN_TURNOVER_VND,
        window=TURNOVER_WINDOW,
        ks=TARGET_KS,
    )
    assert e is None


def test_3c_neutral_basket_excludes_ceiling_open_symbol():
    """Cổng 3c: Rổ trung tính KHÔNG chứa mã mở trần ở phiên sau."""
    start_d = date(2020, 1, 6)
    bars = _make_daily_bar_seq("CEIL", 50, start_d, p=20_000.0, vol=100_000.0)
    # Sửa phiên sau (i=26) mở trần: sàn HOSE biên độ 7% -> open = 20000 * 1.07 = 21400
    bars[26] = Bar(
        symbol="CEIL",
        ts=bars[26].ts,
        open=20_000.0 * 1.07,
        high=20_000.0 * 1.07,
        low=20_000.0 * 1.05,
        close=20_000.0 * 1.07,
        volume=100_000.0,
        source="test",
    )
    e = make_basket_entry(
        "CEIL",
        bars,
        25,
        "HOSE",
        min_turnover=MIN_TURNOVER_VND,
        window=TURNOVER_WINDOW,
        ks=TARGET_KS,
    )
    assert e is None


def test_3d_basket_for_day_excludes_event_symbol():
    """Cổng 3d: Rổ của một sự kiện KHÔNG chứa chính mã sự kiện.

    Đột biến 2: basket_for_day giữ lại chính mã sự kiện -> test 3d phải RED.
    """
    entries = {
        "AAA": BasketEntry("AAA", {5: 0.01, 10: 0.02, 20: 0.03}),
        "BBB": BasketEntry("BBB", {5: 0.02, 10: 0.03, 20: 0.04}),
        "CCC": BasketEntry("CCC", {5: 0.03, 10: 0.04, 20: 0.05}),
    }
    basket = basket_for_day(entries, "AAA")
    symbols = [e.symbol for e in basket]
    assert "AAA" not in symbols
    assert set(symbols) == {"BBB", "CCC"}


def test_3e_neutral_basket_contains_short_series_symbol():
    """Cổng 3e: Rổ trung tính CHỨA một mã có ít hơn 253 nến nhưng đủ điều kiện a.

    Đột biến 4: Vòng đọc dữ liệu vẫn continue với mã < 253 nến ở chế độ neutral -> test 3e phải RED.
    """
    start_d = date(2020, 1, 6)
    bars_evt = _make_daily_bar_seq("AAA", 300, start_d, p=20_000.0, vol=100_000.0)
    # CCC chỉ có 40 nến (< 253 nến TREND_MIN_BARS + 1)
    bars_short = _make_daily_bar_seq("CCC", 40, start_d + timedelta(days=230), p=30_000.0, vol=100_000.0)
    assert len(bars_short) < TREND_MIN_BARS + 1

    # make_basket_entry trực tiếp thành công cho CCC
    e_short = make_basket_entry(
        "CCC",
        bars_short,
        22,
        "HOSE",
        min_turnover=MIN_TURNOVER_VND,
        window=TURNOVER_WINDOW,
        ks=TARGET_KS,
    )
    assert e_short is not None

    # Chạy qua run_sepa_measurement
    storage = _MockDailyStorage({"AAA": bars_evt, "CCC": bars_short})
    res = run_sepa_measurement(storage, no_exclusions=True, basket="neutral")
    first_day = min(res["neutral_basket_by_day"].keys())

    # CCC PHẢI có mặt trong rổ trung tính của ngày sự kiện đầu tiên
    assert "CCC" in res["neutral_basket_by_day"][first_day]


def test_3f_evaluate_gate_mean_condition_1_uses_mean():
    """Cổng 3f: evaluate_gate_mean với dữ liệu có trung bình > 0 nhưng trung vị < 0, điều kiện 1 ĐÚNG.

    Đột biến 3: evaluate_gate_mean điều kiện 1 dùng trung vị -> test 3f phải RED.
    """
    passed, details = evaluate_gate_mean(
        mean_excess_k20=0.015,
        n_events=120,
        boot_ci=(0.005, 0.035),
        holm_pass=True,
        median_excess_k20=-0.025,
    )
    assert passed is True
    assert details["cond1_mean_gt_0"] is True

    # Khi trung bình excess K=20 <= 0, điều kiện 1 phải SAI (dù trung vị có > 0)
    p2, d2 = evaluate_gate_mean(
        mean_excess_k20=-0.005,
        n_events=120,
        boot_ci=(0.005, 0.035),
        holm_pass=True,
        median_excess_k20=0.030,
    )
    assert p2 is False
    assert d2["cond1_mean_gt_0"] is False

