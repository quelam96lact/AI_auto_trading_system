"""Test suite cho scripts/optimize_octopus_walk_forward.py (Brief đợt 171).

Kiểm chứng TDD trên nến dựng tay (synthetic mock data), KHÔNG đọc DB:
1. test_luoi_sinh_dung_12_bo_co_mac_dinh
2. test_tham_so_di_vao_chien_luoc
3. test_khong_tinh_lenh_trong_warmup
4. test_quy_tac_chon
5. test_nam_dieu_kien_dat
6. test_niem_phong_nen_2023_nem_loi
7. test_giai_doan_kiem_khong_anh_huong_viec_chon
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from scripts.optimize_octopus_walk_forward import (
    DEFAULT_CONFIG,
    GRID_CONFIGS,
    GRID_EMA_TREND,
    GRID_PULLBACK_WINDOW,
    GRID_TP_ATR,
    GridConfig,
    PhaseMetrics,
    build_grid_configs,
    compute_spearman_ic,
    delisted_gate_ok,
    evaluate_verification,
    is_stock_symbol,
    run_symbol_phase_backtest,
    select_best_config,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.stock_study import validate_sealed_bars


def _make_bar(
    symbol: str,
    d: date,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 500_000.0,
) -> Bar:
    ts = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="test",
    )


def _generate_synthetic_trend_bars(
    symbol: str,
    start_date: date,
    num_bars: int,
    base_price: float = 20_000.0,
    daily_gain: float = 50.0,
) -> list[Bar]:
    """Tạo chuỗi nến tăng dần để chỉ báo EMA/MACD hội tụ và sinh tín hiệu."""
    bars: list[Bar] = []
    cur_date = start_date
    cur_price = base_price
    while len(bars) < num_bars:
        # Bỏ qua cuối tuần
        if cur_date.weekday() < 5:
            o = cur_price
            c = cur_price + daily_gain
            h = max(o, c) + 100.0
            l = min(o, c) - 100.0
            # Volume đủ để đạt thanh khoản 2 tỷ: ví dụ 200_000 cp x 20_000 = 4 tỷ > 2 tỷ
            bars.append(_make_bar(symbol, cur_date, o, h, l, c, volume=200_000.0))
            cur_price = c
        cur_date += timedelta(days=1)
    return bars


def _build_proven_signal_bars(
    symbol: str,
    start_date: date,
    base_price: float = 10_000.0,
    daily_gain: float = 100.0,
) -> list[Bar]:
    """Tạo chuỗi nến chuẩn có Strong Long tại bar 208 và chốt lời sau đó."""
    closes = []
    for i in range(220):
        if i < 200:
            closes.append(base_price + i * daily_gain)
        elif i < 208:
            closes.append(closes[-1] - 200.0)
        elif i == 208:
            closes.append(closes[-1] + 1500.0)
        else:
            closes.append(closes[-1] + 200.0)

    bars: list[Bar] = []
    d0 = datetime(start_date.year, start_date.month, start_date.day, 15, 0, tzinfo=TZ)
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        h = max(o, c) + 50.0
        l = min(o, c) - 50.0
        bars.append(Bar(symbol, d0 + timedelta(days=i), o, h, l, c, 500_000.0, "test"))
    return bars


def _make_dummy_metrics(
    config: GridConfig,
    trades: int = 350,
    net_pf: float = 1.5,
    net_pnl: float = 100_000_000.0,
    wins: int = 200,
) -> PhaseMetrics:
    win_rate = (wins / trades) if trades > 0 else 0.0
    return PhaseMetrics(
        config=config,
        trades=trades,
        wins=wins,
        win_rate=win_rate,
        gross_profit=net_pnl + 50_000_000.0 if net_pnl > 0 else 50_000_000.0,
        gross_loss=50_000_000.0,
        net_pf=net_pf,
        net_pnl=net_pnl,
        pnl_on_capital=net_pnl / 1_000_000_000.0,
        buy_and_hold_pnl=20_000_000.0,
        symbols_traded=10,
        total_symbols=10,
    )


# --- 1. Test Lưới sinh đúng 12 bộ có mặc định --------------------------------------

def test_luoi_sinh_dung_12_bo_co_mac_dinh() -> None:
    configs = build_grid_configs()
    assert len(configs) == 12
    assert len(set(configs)) == 12

    # Có bộ mặc định (2.0, 5, 200)
    assert DEFAULT_CONFIG in configs
    def_found = [c for c in configs if c.is_default]
    assert len(def_found) == 1
    assert def_found[0] == GridConfig(tp_atr_mult=2.0, pullback_window=5, ema_trend=200)
    assert def_found[0].diff_from_default == 0

    # Kiểm tra toàn bộ tham số nằm trong danh sách cho phép
    for c in configs:
        assert c.tp_atr_mult in GRID_TP_ATR
        assert c.pullback_window in GRID_PULLBACK_WINDOW
        assert c.ema_trend in GRID_EMA_TREND


# --- 2. Test Tham số thật sự đi vào chiến lược ------------------------------------

def test_tham_so_di_vao_chien_luoc() -> None:
    cfg = GridConfig(tp_atr_mult=3.0, pullback_window=10, ema_trend=100)
    strat = cfg.make_strategy()
    assert strat.tp_atr_mult == 3.0
    assert strat.pullback_window == 10
    assert strat.ema_trend == 100

    # Chuỗi nến có Strong Long
    all_test_bars = _build_proven_signal_bars("AAA", date(2016, 1, 4))

    cfg_tp15 = GridConfig(tp_atr_mult=1.5, pullback_window=5, ema_trend=200)
    cfg_tp30 = GridConfig(tp_atr_mult=3.0, pullback_window=5, ema_trend=200)

    rep15 = run_symbol_phase_backtest(
        all_test_bars,
        phase_start=date(2016, 1, 1),
        phase_end=date(2019, 12, 31),
        config=cfg_tp15,
        capital=1e9,
    )
    rep30 = run_symbol_phase_backtest(
        all_test_bars,
        phase_start=date(2016, 1, 1),
        phase_end=date(2019, 12, 31),
        config=cfg_tp30,
        capital=1e9,
    )

    sells15 = [f for f in rep15.fills if f.side == "SELL"]
    sells30 = [f for f in rep30.fills if f.side == "SELL"]
    assert len(sells15) > 0
    assert len(sells30) > 0
    # TP 1.5 vs 3.0 cho ra giá bán hoặc PnL khác nhau
    assert (sells15[0].price != sells30[0].price) or (rep15.realized_pnl != rep30.realized_pnl)


# --- 3. Test Không tính lệnh trong warm-up ------------------------------------------

def test_khong_tinh_lenh_trong_warmup() -> None:
    # 220 nến trong năm 2015 chứa Strong Long sinh lệnh vào tháng 7/2015
    bars_2015 = _build_proven_signal_bars("AAA", date(2015, 1, 1))

    # 50 nến trong năm 2016 (phase 1)
    bars_2016 = _generate_synthetic_trend_bars("AAA", date(2016, 1, 4), 50, 40_000.0, 50.0)

    all_bars = bars_2015 + bars_2016

    rep = run_symbol_phase_backtest(
        all_bars,
        phase_start=date(2016, 1, 1),
        phase_end=date(2019, 12, 31),
        config=DEFAULT_CONFIG,
        capital=1e9,
    )

    # Khẳng định: mọi fill phải từ 2016-01-01 trở đi, TUYỆT ĐỐI không có fill nào trong năm 2015
    assert all(f.ts.date() >= date(2016, 1, 1) for f in rep.fills)
    assert not any(f.ts.date() < date(2016, 1, 1) for f in rep.fills)


# --- 4. Test Quy tắc chọn (trên giai đoạn CHỌN) -------------------------------------

def test_quy_tac_chon() -> None:
    configs = GRID_CONFIGS

    # Ca 1: Bộ có >= 300 lệnh có PF cao nhất được chọn; bộ < 300 lệnh bị loại dù PF cao hơn
    m1 = _make_dummy_metrics(configs[0], trades=350, net_pf=1.45)
    m2 = _make_dummy_metrics(configs[1], trades=250, net_pf=2.50)  # Bị loại do < 300 lệnh
    other_m = [_make_dummy_metrics(c, trades=310, net_pf=1.10) for c in configs[2:]]
    metrics_case1 = [m1, m2] + other_m

    res1 = select_best_config(metrics_case1)
    assert res1.status == "OK"
    assert res1.selected_config == configs[0]

    # Ca 2 (Hòa PF): Hai bộ cùng >= 300 lệnh và cùng max PF -> chọn bộ gần mặc định hơn
    cfg_def = DEFAULT_CONFIG  # diff = 0
    cfg_diff2 = GridConfig(tp_atr_mult=1.5, pullback_window=10, ema_trend=200)  # diff = 2
    m_def = _make_dummy_metrics(cfg_def, trades=400, net_pf=1.60)
    m_diff2 = _make_dummy_metrics(cfg_diff2, trades=400, net_pf=1.60)
    others = [
        _make_dummy_metrics(c, trades=320, net_pf=1.20)
        for c in configs
        if c not in (cfg_def, cfg_diff2)
    ]
    metrics_case2 = [m_diff2, m_def] + others

    res2 = select_best_config(metrics_case2)
    assert res2.status == "OK"
    assert res2.selected_config == cfg_def

    # Ca 3: Không bộ nào đạt >= 300 lệnh -> THIẾU SỨC MẠNH
    metrics_case3 = [_make_dummy_metrics(c, trades=200, net_pf=1.50) for c in configs]
    res3 = select_best_config(metrics_case3)
    assert res3.status == "THIEU_SUC_MANH"
    assert res3.selected_config is None


# --- 5. Test Năm điều kiện ĐẠT ----------------------------------------------------

def test_nam_dieu_kien_dat() -> None:
    configs = GRID_CONFIGS
    sel_cfg = configs[0]  # Giả sử bộ 0 được chọn ở Phase 1
    def_cfg = DEFAULT_CONFIG

    # Phase 1 metrics
    p1_metrics = [_make_dummy_metrics(c, trades=350, net_pf=1.5) for c in configs]

    # Ca chuẩn: ĐẠT cả 5 điều kiện
    # Phase 2 metrics:
    # 1. trades >= 100 (150)
    # 2. net_pf > 1.2 (1.45)
    # 3. net_pnl > 0 (80_000_000)
    # 4. net_pf > def_p2.net_pf (1.45 > 1.10)
    # 5. rank <= 3 (hạng 2/12)
    def make_p2(
        trades: int = 150,
        net_pf: float = 1.45,
        net_pnl: float = 80_000_000.0,
        def_pf: float = 1.10,
        top_rank_pfs: list[float] | None = None,
    ) -> list[PhaseMetrics]:
        res = []
        for c in configs:
            if c == sel_cfg:
                res.append(_make_dummy_metrics(c, trades=trades, net_pf=net_pf, net_pnl=net_pnl))
            elif c == def_cfg:
                res.append(_make_dummy_metrics(c, trades=120, net_pf=def_pf, net_pnl=30_000_000.0))
            else:
                res.append(_make_dummy_metrics(c, trades=120, net_pf=1.05, net_pnl=10_000_000.0))

        if top_rank_pfs:
            # Điều chỉnh PF của các bộ khác để đẩy rank của sel_cfg
            other_idx = 0
            for m in res:
                if m.config not in (sel_cfg, def_cfg) and other_idx < len(top_rank_pfs):
                    m.net_pf = top_rank_pfs[other_idx]
                    other_idx += 1
        return res

    # 1. Ca chuẩn -> ĐẠT
    p2_pass = make_p2()
    v_pass = evaluate_verification(sel_cfg, p1_metrics, p2_pass)
    assert v_pass.passed is True
    assert all(ok for ok, _ in v_pass.conditions.values())

    # 2. Ca trượt ĐK 1: số lệnh < 100
    p2_fail1 = make_p2(trades=90)
    v_fail1 = evaluate_verification(sel_cfg, p1_metrics, p2_fail1)
    assert v_fail1.passed is False
    assert v_fail1.conditions["cond1_min_100_trades"][0] is False

    # 3. Ca trượt ĐK 2: PF <= 1.2
    p2_fail2 = make_p2(net_pf=1.18, def_pf=1.05)
    v_fail2 = evaluate_verification(sel_cfg, p1_metrics, p2_fail2)
    assert v_fail2.passed is False
    assert v_fail2.conditions["cond2_pf_gt_1_2"][0] is False

    # 4. Ca trượt ĐK 3: PnL <= 0
    p2_fail3 = make_p2(net_pnl=-5_000_000.0)
    v_fail3 = evaluate_verification(sel_cfg, p1_metrics, p2_fail3)
    assert v_fail3.passed is False
    assert v_fail3.conditions["cond3_pnl_gt_0"][0] is False

    # 5. Ca trượt ĐK 4: PF không cao hơn mặc định
    p2_fail4 = make_p2(net_pf=1.40, def_pf=1.45)
    v_fail4 = evaluate_verification(sel_cfg, p1_metrics, p2_fail4)
    assert v_fail4.passed is False
    assert v_fail4.conditions["cond4_pf_gt_default"][0] is False

    # 6. Ca trượt ĐK 5: Rank ngoài top 3/12 (ví dụ có 4 bộ khác có PF > 1.45 -> rank 5)
    p2_fail5 = make_p2(net_pf=1.45, top_rank_pfs=[2.0, 1.9, 1.8, 1.7])
    v_fail5 = evaluate_verification(sel_cfg, p1_metrics, p2_fail5)
    assert v_fail5.passed is False
    assert v_fail5.conditions["cond5_rank_top_3"][0] is False


# --- 6. Test Niêm phong nến 2023 ném lỗi -------------------------------------------

def test_niem_phong_nen_2023_nem_loi() -> None:
    # Nến hợp lệ
    b_ok = _make_bar("AAA", date(2022, 12, 30), 20_000, 21_000, 19_000, 20_500)
    validate_sealed_bars([b_ok])

    # Nến vi phạm niêm phong >= 2023-01-01
    b_sealed = _make_bar("AAA", date(2023, 1, 3), 20_000, 21_000, 19_000, 20_500)
    with pytest.raises(ValueError, match="Vi phạm niêm phong"):
        validate_sealed_bars([b_ok, b_sealed])

    with pytest.raises(ValueError, match="Vi phạm niêm phong"):
        run_symbol_phase_backtest(
            [b_ok, b_sealed],
            phase_start=date(2020, 1, 1),
            phase_end=date(2022, 12, 31),
            config=DEFAULT_CONFIG,
        )


# --- 7. Test Giai đoạn kiểm không ảnh hưởng việc chọn -------------------------------

def test_giai_doan_kiem_khong_anh_huong_viec_chon() -> None:
    configs = GRID_CONFIGS

    # Phase 1: Bộ 0 có PF cao nhất (1.80, 400 lệnh)
    p1_metrics = [
        _make_dummy_metrics(configs[0], trades=400, net_pf=1.80),
        _make_dummy_metrics(configs[1], trades=400, net_pf=1.30),
    ] + [_make_dummy_metrics(c, trades=350, net_pf=1.10) for c in configs[2:]]

    # Kịch bản Phase 2 số 1: Bộ 1 thắng đậm ở Phase 2
    p2_scenario_1 = [
        _make_dummy_metrics(configs[0], trades=100, net_pf=0.80),
        _make_dummy_metrics(configs[1], trades=200, net_pf=2.50),
    ] + [_make_dummy_metrics(c, trades=100, net_pf=1.00) for c in configs[2:]]

    # Kịch bản Phase 2 số 2: Bộ 5 thắng đậm ở Phase 2
    p2_scenario_2 = [
        _make_dummy_metrics(configs[0], trades=100, net_pf=0.50),
        _make_dummy_metrics(configs[5], trades=250, net_pf=3.00),
    ] + [
        _make_dummy_metrics(c, trades=100, net_pf=0.90)
        for c in configs
        if c not in (configs[0], configs[5])
    ]

    # Việc chọn bộ tham số chỉ dựa vào Phase 1
    sel_res1 = select_best_config(p1_metrics)
    sel_res2 = select_best_config(p1_metrics)

    assert sel_res1.selected_config == configs[0]
    assert sel_res2.selected_config == configs[0]
    assert sel_res1.selected_config == sel_res2.selected_config

    # Khi evaluate_verification cho hai kịch bản Phase 2 khác nhau,
    # bộ tham số được kiểm tra vẫn luôn là bộ configs[0] được chọn từ Phase 1
    v1 = evaluate_verification(sel_res1.selected_config, p1_metrics, p2_scenario_1)
    v2 = evaluate_verification(sel_res2.selected_config, p1_metrics, p2_scenario_2)
    assert v1.selected_config == configs[0]
    assert v2.selected_config == configs[0]


# --- Test phụ trợ: Stock symbol filter & Spearman calculation -----------------------

def test_is_stock_symbol_and_spearman() -> None:
    assert is_stock_symbol("SSI") is True
    assert is_stock_symbol("VCB") is True
    assert is_stock_symbol("E1VFVN30") is False
    assert is_stock_symbol("CVPB2301") is False

    configs = GRID_CONFIGS
    p1 = [_make_dummy_metrics(c, net_pf=float(i + 1)) for i, c in enumerate(configs)]
    p2 = [_make_dummy_metrics(c, net_pf=float(i + 1)) for i, c in enumerate(configs)]
    ic, _ = compute_spearman_ic(p1, p2)
    assert abs(ic - 1.0) < 1e-6


def test_cong_ma_da_huy_khong_mo_voi_mot_ma_co_san():
    """Sua cua Claude khi audit: DB chua nap ma chet van co 1 ma -> cong phai dong."""
    assert delisted_gate_ok(0) is False
    assert delisted_gate_ok(1) is False
    assert delisted_gate_ok(19) is False
    assert delisted_gate_ok(20) is True
