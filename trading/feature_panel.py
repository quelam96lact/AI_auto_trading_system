"""Bảng đặc trưng 1 giờ từ dữ liệu phi giá Binance (Brief đợt 41).

Luật căn dòng và chống nhìn trước:
- Mỗi hàng đại diện cho 1 nến 1 giờ, khoá theo `ts` (thời điểm MỞ nến).
- `close_ts = ts + 1 giờ` là thời điểm nến đóng.
- MỌI đặc trưng của hàng này chỉ được dùng thông tin có tại hoặc trước `close_ts`.
- Nguồn funding:
    Lấy bản ghi đã settle gần nhất có funding_time <= close_ts.
    Tuyệt đối không dùng lần settle kế tiếp.
- Nguồn metrics:
    Lấy mốc 5 phút gần nhất có ts <= close_ts.
    Nếu mốc đó cũ hơn max_metric_staleness_minutes (mặc định 10 phút) -> NULL.
    Luật OI = 0: Nếu sum_open_interest = 0 hoặc sum_open_interest_value = 0 -> coi là NULL.
- Nguồn orderflow:
    Lấy đúng hàng có ts = nến.ts (delta được biết tại close_ts).
- 9 đặc trưng:
    1. funding_rate: funding đã settle gần nhất
    2. funding_z: z-score của (1) trên 90 ngày các lần settle trước đó, không gồm hiện tại (cần >= 260 lần settle)
    3. oi_chg_3h: OI(close_ts) / OI(close_ts - 3h) - 1 (cần cả 2 đầu mút hợp lệ)
    4. oi_chg_24h: OI(close_ts) / OI(close_ts - 24h) - 1 (cần cả 2 đầu mút hợp lệ)
    5. long_short_ratio: count_long_short_ratio
    6. toptrader_ls_ratio: sum_toptrader_long_short_ratio
    7. taker_ls_vol_ratio: sum_taker_long_short_vol_ratio
    8. delta_norm: delta / (taker_buy_volume + taker_sell_volume)
    9. cvd_chg_3h: tổng delta của 3 nến gần nhất chia tổng khối lượng 3 nến đó
- 3 biến mục tiêu:
    fwd_ret_1h  = close[t+1]  / close[t] - 1
    fwd_ret_4h  = close[t+4]  / close[t] - 1
    fwd_ret_24h = close[t+24] / close[t] - 1
"""

import bisect
from datetime import datetime, timedelta

from trading.models import Bar


def build_feature_panel(
    klines: list[Bar],
    funding: list[tuple[datetime, float]],
    metrics: list[dict],
    orderflow: list[dict],
    *,
    metric_lag_minutes: int = 5,
    max_metric_staleness_minutes: int = 10,
) -> list[dict]:
    """Dựng bảng đặc trưng 1 giờ chống nhìn trước từ các nguồn dữ liệu phi giá.

    Parameters:
    - klines: Danh sách Bar 1h của Binance (đã sort theo ts hoặc sẽ được sort).
    - funding: Danh sách tuple (funding_time, funding_rate).
    - metrics: Danh sách dict metrics 5m (chứa ts, sum_open_interest, count_long_short_ratio,...).
    - orderflow: Danh sách dict orderflow 1h (chứa ts, delta, taker_buy_volume, taker_sell_volume,...).
    - metric_lag_minutes: Số phút hoàn tất của metric (mặc định 5, Brief đợt 42).
    - max_metric_staleness_minutes: Số phút tối đa cho phép độ trễ của metrics (mặc định 10).
    """
    if not klines:
        return []

    # 1. Sắp xếp các danh sách theo thời gian
    sorted_klines = sorted(klines, key=lambda b: b.ts)
    sorted_funding = sorted(funding, key=lambda f: f[0])

    # 2. Xử lý sạch metrics: áp dụng luật OI = 0 thành None
    cleaned_metrics = []
    for m in sorted(metrics, key=lambda x: x["ts"]):
        m_copy = dict(m)
        oi = m_copy.get("sum_open_interest")
        oiv = m_copy.get("sum_open_interest_value")
        # Luật §0.2: sum_open_interest = 0 hoặc sum_open_interest_value = 0 là NULL
        if oi is not None and oi <= 0:
            m_copy["sum_open_interest"] = None
        if oiv is not None and oiv <= 0:
            m_copy["sum_open_interest_value"] = None
        cleaned_metrics.append(m_copy)

    # 3. Tra cứu Orderflow theo ts (O(1))
    of_by_ts: dict[datetime, dict] = {o["ts"]: o for o in orderflow}

    # 4. Chuẩn bị mảng thời gian cho bisect
    funding_times = [f[0] for f in sorted_funding]
    funding_rates = [f[1] for f in sorted_funding]

    metric_times = [m["ts"] for m in cleaned_metrics]

    # Map klines theo ts và index để tính biến mục tiêu và liên tục
    kline_by_ts: dict[datetime, Bar] = {b.ts: b for b in sorted_klines}

    results = []

    # Helper tìm metric gần nhất thoả: ts + metric_lag_minutes <= target_ts (Brief 42 §2.1)
    def get_latest_metric(target_ts: datetime) -> dict | None:
        if not metric_times:
            return None
        effective_target = target_ts - timedelta(minutes=metric_lag_minutes)
        # bisect_right tìm vị trí chèn sau các phần tử <= effective_target
        idx = bisect.bisect_right(metric_times, effective_target) - 1
        if idx < 0:
            return None
        m = cleaned_metrics[idx]
        diff_sec = (target_ts - (m["ts"] + timedelta(minutes=metric_lag_minutes))).total_seconds()
        # Không được dùng tương lai và không được quá cũ
        if 0 <= diff_sec <= max_metric_staleness_minutes * 60:
            return m
        return None

    for i, bar in enumerate(sorted_klines):
        close_ts = bar.ts + timedelta(hours=1)

        # --- NGUỒN 1: FUNDING ---
        # Tìm lần settle gần nhất có funding_time <= close_ts
        f_idx = bisect.bisect_right(funding_times, close_ts) - 1
        cur_funding_rate = None
        cur_funding_z = None

        if f_idx >= 0:
            cur_funding_rate = funding_rates[f_idx]
            cur_f_time = funding_times[f_idx]

            # Tính funding_z: z-score trên 90 ngày các lần settle TRƯỚC ĐÓ (không gồm hiện tại)
            cutoff_90d = cur_f_time - timedelta(days=90)
            # Cần lịch sử đủ 90 ngày: tức lần settle đầu tiên phải <= cutoff_90d
            if funding_times[0] <= cutoff_90d:
                # Lấy các lần settle trong [cutoff_90d, cur_f_time)
                left_idx = bisect.bisect_left(funding_times, cutoff_90d)
                past_rates = funding_rates[left_idx:f_idx]
                # Chu kỳ 8h/lần -> 90 ngày có 270 lần settle. Yêu cầu ít nhất 260 lần để đảm bảo tính đại diện
                if len(past_rates) >= 260:
                    mean_f = sum(past_rates) / len(past_rates)
                    var_f = sum((x - mean_f) ** 2 for x in past_rates) / (len(past_rates) - 1)
                    std_f = var_f ** 0.5
                    if std_f > 1e-12:
                        cur_funding_z = (cur_funding_rate - mean_f) / std_f

        # --- NGUỒN 2: METRICS ---
        m_now = get_latest_metric(close_ts)
        ls_ratio = None
        toptrader_ls = None
        taker_ls_vol = None
        oi_now = None

        if m_now is not None:
            ls_ratio = m_now.get("count_long_short_ratio")
            toptrader_ls = m_now.get("sum_toptrader_long_short_ratio")
            taker_ls_vol = m_now.get("sum_taker_long_short_vol_ratio")
            oi_now = m_now.get("sum_open_interest")

        # oi_chg_3h: OI(close_ts) / OI(close_ts - 3h) - 1
        oi_chg_3h = None
        ts_minus_3h = close_ts - timedelta(hours=3)
        m_3h = get_latest_metric(ts_minus_3h)
        if m_3h is not None and oi_now is not None and oi_now > 0:
            oi_past_3h = m_3h.get("sum_open_interest")
            if oi_past_3h is not None and oi_past_3h > 0:
                oi_chg_3h = (oi_now / oi_past_3h) - 1.0

        # oi_chg_24h: OI(close_ts) / OI(close_ts - 24h) - 1
        oi_chg_24h = None
        ts_minus_24h = close_ts - timedelta(hours=24)
        m_24h = get_latest_metric(ts_minus_24h)
        if m_24h is not None and oi_now is not None and oi_now > 0:
            oi_past_24h = m_24h.get("sum_open_interest")
            if oi_past_24h is not None and oi_past_24h > 0:
                oi_chg_24h = (oi_now / oi_past_24h) - 1.0

        # --- NGUỒN 3: ORDERFLOW ---
        of_cur = of_by_ts.get(bar.ts)
        delta_norm = None
        if of_cur is not None:
            tb = of_cur.get("taker_buy_volume", 0.0)
            ts_vol = of_cur.get("taker_sell_volume", 0.0)
            delta = of_cur.get("delta", tb - ts_vol)
            tot_vol = tb + ts_vol
            if tot_vol > 0:
                delta_norm = delta / tot_vol

        # cvd_chg_3h: Tổng delta của 3 nến gần nhất (t-2, t-1, t) chia tổng khối lượng 3 nến đó
        cvd_chg_3h = None
        of_prev1 = of_by_ts.get(bar.ts - timedelta(hours=1))
        of_prev2 = of_by_ts.get(bar.ts - timedelta(hours=2))
        if of_cur is not None and of_prev1 is not None and of_prev2 is not None:
            d0 = of_cur.get("delta", 0.0)
            v0 = of_cur.get("taker_buy_volume", 0.0) + of_cur.get("taker_sell_volume", 0.0)
            d1 = of_prev1.get("delta", 0.0)
            v1 = of_prev1.get("taker_buy_volume", 0.0) + of_prev1.get("taker_sell_volume", 0.0)
            d2 = of_prev2.get("delta", 0.0)
            v2 = of_prev2.get("taker_buy_volume", 0.0) + of_prev2.get("taker_sell_volume", 0.0)
            tot_3h_vol = v0 + v1 + v2
            if tot_3h_vol > 0:
                cvd_chg_3h = (d0 + d1 + d2) / tot_3h_vol

        # --- BA BIẾN MỤC TIÊU (FORWARD RETURNS) ---
        # fwd_ret_1h = close[t+1] / close[t] - 1
        fwd_ret_1h = None
        target_ts_1h = bar.ts + timedelta(hours=1)
        b_1h = kline_by_ts.get(target_ts_1h)
        if b_1h is not None and bar.close > 0:
            fwd_ret_1h = (b_1h.close / bar.close) - 1.0

        # fwd_ret_4h = close[t+4] / close[t] - 1
        fwd_ret_4h = None
        target_ts_4h = bar.ts + timedelta(hours=4)
        b_4h = kline_by_ts.get(target_ts_4h)
        if b_4h is not None and bar.close > 0:
            fwd_ret_4h = (b_4h.close / bar.close) - 1.0

        # fwd_ret_24h = close[t+24] / close[t] - 1
        fwd_ret_24h = None
        target_ts_24h = bar.ts + timedelta(hours=24)
        b_24h = kline_by_ts.get(target_ts_24h)
        if b_24h is not None and bar.close > 0:
            fwd_ret_24h = (b_24h.close / bar.close) - 1.0

        row = {
            "ts": bar.ts,
            "close_ts": close_ts,
            "close": bar.close,
            # 9 đặc trưng
            "funding_rate": cur_funding_rate,
            "funding_z": cur_funding_z,
            "oi_chg_3h": oi_chg_3h,
            "oi_chg_24h": oi_chg_24h,
            "long_short_ratio": ls_ratio,
            "toptrader_ls_ratio": toptrader_ls,
            "taker_ls_vol_ratio": taker_ls_vol,
            "delta_norm": delta_norm,
            "cvd_chg_3h": cvd_chg_3h,
            # 3 mục tiêu
            "fwd_ret_1h": fwd_ret_1h,
            "fwd_ret_4h": fwd_ret_4h,
            "fwd_ret_24h": fwd_ret_24h,
        }
        results.append(row)

    return results
