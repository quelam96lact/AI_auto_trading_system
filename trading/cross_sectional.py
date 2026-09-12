"""Engine danh mục cắt ngang 20 mã, trung tính thị trường (Brief đợt 39).

Xếp hạng động lượng cắt ngang (Cross-sectional momentum):
- Long k mã mạnh nhất, Short k mã yếu nhất.
- Tái cân bằng mỗi 7 ngày lịch.
- Quản trị danh mục không đòn bẩy: Gross 1x, Net 0 (thị trường trung tính).
- Nhận biết quay vòng (turnover with awareness) để giảm chi phí giao dịch.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from trading.data_quality import is_dirty_bar
from trading.models import Bar


@dataclass
class Rebalance:
    ts: datetime                    # ngày ra tín hiệu (close), UTC
    fill_ts: datetime               # ngày khớp lệnh (open t+1), UTC
    universe_size: int
    longs: list[str]
    shorts: list[str]
    turnover_notional: float        # tổng giá trị danh nghĩa đã giao dịch kỳ này
    fees: float
    skipped_fills: int              # mã thiếu nến t+1


@dataclass
class CrossSectionalReport:
    starting_capital: float
    ending_capital: float
    equity_curve: list[tuple[datetime, float]]   # theo ngày
    rebalances: list[Rebalance]
    total_fees: float
    skipped_rebalances: int         # kỳ bỏ vì vũ trụ < min_universe


def run_cross_sectional(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    start: datetime,
    end: datetime,
    lookback_days: int = 30,
    rebalance_days: int = 7,
    k: int = 3,
    min_universe: int = 10,
    capital: float = 500.0,
    fee_rate: float,            # BẮT BUỘC tường minh
    slippage_bps: float,        # BẮT BUỘC tường minh
    skip_recent_days: int = 0,  # biến thể: bỏ qua N ngày gần nhất khi tính động lượng
    long_only: bool = False,    # Mua-và-giữ toàn vũ trụ: chỉ Long 100% vốn, không Short
    selector: Callable[[list[str], dict[str, float], int, random.Random | None], tuple[list[str], list[str]]] | None = None,
    rng: random.Random | None = None,
) -> CrossSectionalReport:
    """Chạy mô phỏng danh mục cắt ngang trung tính thị trường.

    Args:
        bars_by_symbol: Dữ liệu nến 1D theo từng mã.
        start: Mốc thời gian bắt đầu xét tái cân bằng (UTC).
        end: Mốc thời gian kết thúc mô phỏng (UTC).
        lookback_days: Số ngày nhìn lại để tính tỷ suất sinh lời động lượng.
        rebalance_days: Chu kỳ tái cân bằng tính theo ngày lịch.
        k: Số lượng mã chọn mỗi vế (k Long, k Short).
        min_universe: Ngưỡng tối thiểu số mã đủ tư cách để tiến hành tái cân bằng.
        capital: Vốn ban đầu (USDT). Mặc định 500.0.
        fee_rate: Tỷ lệ phí mỗi chiều (ví dụ BINGX_PERP_TAKER).
        slippage_bps: Trượt giá mỗi chiều tính theo điểm cơ bản (bps).
        skip_recent_days: Số ngày gần nhất bỏ qua khi tính động lượng (mặc định 0).
        selector: Hàm bốc thăm / chọn mã tuỳ biến. Nếu None, dùng xếp hạng động lượng.
        rng: Bộ sinh số ngẫu nhiên cô lập dùng cho selector nếu có.
    """
    # 1. Tiền xử lý dữ liệu: lọc bar rác và index theo date (UTC)
    # Map: sym -> {date: Bar}
    bars_by_date: dict[str, dict[datetime, Bar]] = {}
    for sym, bars in bars_by_symbol.items():
        clean = {}
        for b in bars:
            if not is_dirty_bar(b):
                # Chuẩn hóa về 00:00:00 UTC của ngày đó
                dt_day = datetime(b.ts.year, b.ts.month, b.ts.day, tzinfo=UTC)
                clean[dt_day] = b
        bars_by_date[sym] = clean

    # Chuẩn hóa start và end về 00:00:00 UTC
    start_day = datetime(start.year, start.month, start.day, tzinfo=UTC)
    end_day = datetime(end.year, end.month, end.day, tzinfo=UTC)

    # 2. Xác định các mốc ngày lịch từ start_day đến end_day
    all_calendar_days: list[datetime] = []
    cur_d = start_day
    while cur_d <= end_day:
        all_calendar_days.append(cur_d)
        cur_d += timedelta(days=1)

    # Xác định các ngày ra tín hiệu tái cân bằng t
    rebalance_dates: set[datetime] = set()
    cur_reb = start_day
    while cur_reb < end_day:
        rebalance_dates.add(cur_reb)
        cur_reb += timedelta(days=rebalance_days)

    # 3. Trạng thái danh mục
    cash = capital
    # positions: sym -> qty (dương: Long, âm: Short)
    current_positions: dict[str, float] = {}
    last_known_close: dict[str, float] = {}

    equity_curve: list[tuple[datetime, float]] = []
    rebalances: list[Rebalance] = []
    total_fees = 0.0
    skipped_rebalances = 0

    # Biến lưu trữ tín hiệu đã ra tại close ngày t, chờ khớp tại open ngày t+1
    pending_rebalance_signal: dict | None = None

    # 4. Vòng lặp theo từng ngày lịch
    for day in all_calendar_days:
        # Cập nhật giá close gần nhất nếu có nến trong ngày này
        for sym, date_map in bars_by_date.items():
            if day in date_map:
                last_known_close[sym] = date_map[day].close

        # A. KHỚP LỆNH TÁI CÂN BẰNG TẠI OPEN NGÀY t+1 (nếu có tín hiệu từ ngày trước)
        if pending_rebalance_signal is not None:
            sig = pending_rebalance_signal
            pending_rebalance_signal = None

            t = sig["t"]
            eligible = sig["eligible"]
            target_longs = sig["longs"]
            target_shorts = sig["shorts"]

            # Kiểm tra nến ngày day (t+1)
            skipped_fills = 0
            active_longs: list[str] = []
            active_shorts: list[str] = []

            for s in target_longs:
                if s in bars_by_date and day in bars_by_date[s]:
                    active_longs.append(s)
                else:
                    skipped_fills += 1

            for s in target_shorts:
                if s in bars_by_date and day in bars_by_date[s]:
                    active_shorts.append(s)
                else:
                    skipped_fills += 1

            # Định giá danh mục tại open ngày t+1 để xác định vốn khả dụng (equity_at_open)
            equity_at_open = cash
            for s, qty in current_positions.items():
                if qty != 0.0:
                    if s in bars_by_date and day in bars_by_date[s]:
                        p_op = bars_by_date[s][day].open
                    else:
                        p_op = last_known_close.get(s, 0.0)
                    equity_at_open += qty * p_op

            # Phân bổ target notional cho từng mã
            if long_only:
                target_side_notional = equity_at_open if equity_at_open > 0 else 0.0
                target_notional: dict[str, float] = {}
                if active_longs:
                    target_per_long = target_side_notional / len(active_longs)
                    for s in active_longs:
                        target_notional[s] = target_per_long
            else:
                # Gross 1x: mỗi vế target_side_notional = equity_at_open / 2.0
                target_side_notional = equity_at_open / 2.0 if equity_at_open > 0 else 0.0
                target_notional: dict[str, float] = {}
                if active_longs:
                    target_per_long = target_side_notional / len(active_longs)
                    for s in active_longs:
                        target_notional[s] = target_per_long

                if active_shorts:
                    target_per_short = -target_side_notional / len(active_shorts)
                    for s in active_shorts:
                        target_notional[s] = target_per_short


            # Các mã không còn trong active_longs hoặc active_shorts sẽ có target_notional = 0.0
            all_symbols_to_check = set(current_positions.keys()) | set(target_notional.keys())

            period_turnover = 0.0
            period_fees = 0.0

            # Thực hiện giao dịch chỉ cho phần chênh lệch (turnover with awareness)
            for s in all_symbols_to_check:
                # Nếu mã thiếu nến t+1 mà đang có vị thế, không thể giao dịch -> giữ nguyên
                if s not in bars_by_date or day not in bars_by_date[s]:
                    continue

                b_bar = bars_by_date[s][day]
                p_open = b_bar.open
                cur_qty = current_positions.get(s, 0.0)
                cur_notional = cur_qty * p_open
                tgt_notional = target_notional.get(s, 0.0)
                delta_notional = tgt_notional - cur_notional

                if abs(delta_notional) > 1e-6:
                    turnover = abs(delta_notional)
                    period_turnover += turnover
                    fee = turnover * fee_rate
                    period_fees += fee

                    slip = slippage_bps / 10000.0
                    if delta_notional > 0:  # Mua thêm hoặc giảm Short
                        exec_price = p_open * (1.0 + slip)
                        delta_qty = delta_notional / exec_price
                        cash -= (delta_qty * exec_price + fee)
                        current_positions[s] = cur_qty + delta_qty
                    else:  # Bán bớt hoặc mở thêm Short
                        exec_price = p_open * (1.0 - slip)
                        delta_qty = delta_notional / exec_price  # delta_qty âm
                        cash += (abs(delta_qty) * exec_price - fee)
                        current_positions[s] = cur_qty + delta_qty

            total_fees += period_fees

            rebalances.append(
                Rebalance(
                    ts=t,
                    fill_ts=day,
                    universe_size=len(eligible),
                    longs=target_longs,
                    shorts=target_shorts,
                    turnover_notional=period_turnover,
                    fees=period_fees,
                    skipped_fills=skipped_fills,
                )
            )

        # B. TÍNH EQUITY TẠI CLOSE NGÀY day
        day_equity = cash
        for s, qty in current_positions.items():
            if qty != 0.0:
                p_close = last_known_close.get(s, 0.0)
                day_equity += qty * p_close
        equity_curve.append((day, day_equity))

        # C. PHÁT HIỆN TÍN HIỆU TÁI CÂN BẰNG TẠI CLOSE NGÀY day (nếu day thuộc rebalance_dates)
        if day in rebalance_dates:
            t = day
            eligible: list[str] = []
            returns: dict[str, float] = {}

            t_lookback = t - timedelta(days=lookback_days)
            t_skip = t - timedelta(days=skip_recent_days)

            # Kiểm tra 3 điều kiện đủ tư cách (§2.3) cho từng mã
            for sym, date_map in bars_by_date.items():
                # 1. Có nến ngày tại đúng t
                if t not in date_map:
                    continue
                # 2. Có nến ngày tại đúng t - lookback
                if t_lookback not in date_map:
                    continue
                # Nếu skip_recent_days > 0, cần có nến tại t - skip_recent_days
                if skip_recent_days > 0 and t_skip not in date_map:
                    continue

                # 3. Số nến trong (t - lookback, t] >= 0.9 * lookback
                # Đếm số bar có ts trong khoảng (t_lookback, t]
                bars_in_window = sum(1 for dt_bar in date_map if t_lookback < dt_bar <= t)
                if bars_in_window < 0.9 * lookback_days:
                    continue

                # Đủ tư cách -> tính lợi suất động lượng
                p_num = date_map[t_skip].close
                p_den = date_map[t_lookback].close
                if p_den > 0:
                    ret = (p_num / p_den) - 1.0
                    eligible.append(sym)
                    returns[sym] = ret

            # Bỏ qua kỳ nếu số mã đủ tư cách < min_universe (§2.6)
            if len(eligible) < min_universe:
                skipped_rebalances += 1
            else:
                # Chọn mã: nếu long_only thì toàn bộ eligible làm Long, không có Short
                if long_only and selector is None:
                    longs = list(eligible)
                    shorts = []
                elif selector is None:
                    sorted_eligible = sorted(eligible, key=lambda s: returns[s], reverse=True)
                    longs = sorted_eligible[:k]
                    shorts = sorted_eligible[-k:]
                else:
                    longs, shorts = selector(eligible, returns, k, rng)


                # Lưu tín hiệu chờ khớp tại open ngày t+1
                pending_rebalance_signal = {
                    "t": t,
                    "eligible": eligible,
                    "longs": longs,
                    "shorts": shorts,
                }

    ending_capital = equity_curve[-1][1] if equity_curve else capital

    return CrossSectionalReport(
        starting_capital=capital,
        ending_capital=ending_capital,
        equity_curve=equity_curve,
        rebalances=rebalances,
        total_fees=total_fees,
        skipped_rebalances=skipped_rebalances,
    )
