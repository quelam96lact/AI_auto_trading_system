"""Các hàm nhận dạng mẫu nến thuần tuý (Gói P1 — brief 2026-09-06-brief-ba-chien-luoc-nen-tu-slide.md).

Bao gồm 3 bộ nhận dạng theo slide khoá học (Buổi 9&10):
1. is_doji: Mẫu Doji + luật Near Doji (loại bỏ nếu có >2 doji trước đó).
2. is_hammer: Mẫu nến búa (Hammer / Pin bar) thoả 4 điều kiện hình thái và xu hướng.
3. combo_signal: Tín hiệu phối hợp (Combo BUY / Combo SELL) giữa Nến + MA(20) + MACD(5,25,5).

RÀNG BUỘC KIẾN TRÚC:
- Hàm thuần tuý, không phụ thuộc broker, engine hay cơ chế đặt lệnh.
- KHÔNG sử dụng hằng số đơn vị tuyệt đối (VND / USD / USDT) — mọi tham số đều là
  tỷ lệ tương đối hoặc theo cấu trúc nến/ATR.
"""

from typing import Literal

from trading.models import Bar


def is_doji(
    bar: Bar,
    prev_bars: list[Bar] | None = None,
    doji_ratio: float = 0.1,
    max_prior_doji: int = 2,
    max_prior_small_body: int = 3,
    small_body_ratio: float = 0.25,
    lookback_prior: int = 5,
    require_range: bool = True,
) -> bool:
    """Nhận dạng nến Doji theo slide Buổi 9&10 (tr.12).

    Quy tắc:
    - Giá đóng cửa rất gần giá mở cửa: |close - open| <= doji_ratio * (high - low).
    - Doji hoàn hảo khi close == open.
    - Luật Near Doji (2 vế tách bạch theo slide tr.12):
      1. Nếu trước đó trong `lookback_prior` phiên có > `max_prior_doji` nến Doji (mặc định 2).
      2. HOẶC xuất hiện nhiều nến thân nhỏ (> `max_prior_small_body`, mặc định 3 nến có thân <= `small_body_ratio` * range).
      Thì mẫu hình Doji hiện tại bị coi là KHÔNG hiệu quả (trả về False).

    Args:
        bar: Bar hiện tại cần kiểm tra.
        prev_bars: Danh sách các bar trước đó (sắp xếp tăng dần theo thời gian).
        doji_ratio: Tỷ lệ thân nến tối đa so với toàn bộ chiều dài nến (mặc định 0.1 = 10%).
        max_prior_doji: Số lượng Doji tối đa cho phép xuất hiện trước đó (mặc định 2).
        max_prior_small_body: Số lượng nến thân nhỏ tối đa cho phép trước đó (mặc định 3).
        small_body_ratio: Tỷ lệ thân nến tối đa để xem là nến thân nhỏ (mặc định 0.25 = 25%).
        lookback_prior: Số nến nhìn lại phía trước để đếm (mặc định 5 nến).
        require_range: Nến PHẲNG (high == low) có được tính là doji không.
    """
    candle_range = bar.high - bar.low
    if candle_range <= 0.0:
        # Nến phẳng (high == low). Xem khối giải thích `require_range`.
        is_cur_doji = (not require_range) and bar.close == bar.open
    else:
        body = abs(bar.close - bar.open)
        is_cur_doji = body <= doji_ratio * candle_range

    if not is_cur_doji:
        return False

    # Kiểm tra luật Near Doji (2 vế) nếu có lịch sử bar trước đó
    if prev_bars:
        window = (
            prev_bars[-lookback_prior:]
            if len(prev_bars) > lookback_prior
            else prev_bars
        )
        prior_doji_count = 0
        prior_small_body_count = 0

        for b in window:
            b_range = b.high - b.low
            if b_range <= 0.0:
                if (not require_range) and b.close == b.open:
                    prior_doji_count += 1
                    prior_small_body_count += 1
            else:
                b_body = abs(b.close - b.open)
                if b_body <= doji_ratio * b_range:
                    prior_doji_count += 1
                if b_body <= small_body_ratio * b_range:
                    prior_small_body_count += 1

        # Vế 1: Quá nhiều Doji trước đó
        if prior_doji_count > max_prior_doji:
            return False

        # Vế 2: Quá nhiều nến thân nhỏ trước đó
        if prior_small_body_count > max_prior_small_body:
            return False

    return True


def is_hammer(
    bar: Bar,
    prev_bars: list[Bar] | None = None,
    trend_lookback: int = 3,
    body_ratio: float = 0.35,
    lower_shadow_multiplier: float = 2.0,
    upper_shadow_ratio: float = 0.1,
    require_history: bool = True,
) -> bool:
    """Nhận dạng nến Búa (Hammer / Bullish Pin bar) thoả mãn 4 điều kiện slide (tr.19).

    4 điều kiện:
    1. Xuất hiện sau một xu hướng GIẢM GIÁ (downtrend).
    2. Thân búa ở phần TRÊN của cây nến (thân tăng hay giảm đều được).
    3. Bóng nến DƯỚI dài gấp ít nhất `lower_shadow_multiplier` lần thân nến (>= 2x thân).
    4. Bóng nến TRÊN rất ngắn (<= `upper_shadow_ratio` * chiều dài nến).

    HỎNG ĐÓNG (Fail-closed): Nếu `require_history=True` và thiếu dữ liệu lịch sử
    (prev_bars is None hoặc len(prev_bars) < trend_lookback), hàm trả về False
    vì không thể kiểm chứng ĐK1 bắt buộc.

    Args:
        bar: Bar hiện tại cần kiểm tra.
        prev_bars: Danh sách các bar trước đó (sắp xếp tăng dần theo thời gian).
        trend_lookback: Số bar tối thiểu cần nhìn lại để xác định xu hướng giảm.
        body_ratio: Tỷ lệ thân nến tối đa so với toàn bộ chiều dài nến (mặc định 0.35).
        lower_shadow_multiplier: Hệ số tối thiểu của bóng dưới so với thân nến (mặc định 2.0).
        upper_shadow_ratio: Tỷ lệ bóng trên tối đa so với toàn bộ chiều dài nến (mặc định 0.1).
        require_history: Bắt buộc phải có đủ lịch sử để kiểm chứng xu hướng giảm (mặc định True).
    """
    candle_range = bar.high - bar.low
    if candle_range <= 0.0:
        return False

    body = abs(bar.close - bar.open)
    lower_body = min(bar.open, bar.close)
    upper_body = max(bar.open, bar.close)

    lower_shadow = lower_body - bar.low
    upper_shadow = bar.high - upper_body

    # ĐK2: Thân búa ở phần TRÊN của cây nến và thân không chiếm quá nhiều chiều dài
    # Đáy thân nến phải nằm ở nửa trên của dải nến (lower_shadow >= 0.5 * candle_range)
    if lower_shadow < 0.5 * candle_range:
        return False
    if body > body_ratio * candle_range:
        return False

    # ĐK3: Bóng nến DƯỚI dài gấp ít nhất lower_shadow_multiplier lần thân nến
    if lower_shadow < lower_shadow_multiplier * body:
        return False

    # ĐK4: Bóng nến TRÊN rất ngắn
    if upper_shadow > upper_shadow_ratio * candle_range:
        return False

    # ĐK1: Xuất hiện sau một xu hướng GIẢM GIÁ (Hỏng đóng nếu thiếu lịch sử)
    if prev_bars is None or len(prev_bars) < trend_lookback:
        if require_history:
            return False
    else:
        window = prev_bars[-trend_lookback:]
        # Xu hướng giảm: giá bar trước thấp hơn bar đầu cửa sổ
        is_downtrend = window[-1].close < window[0].close
        if not is_downtrend:
            return False

    return True


def combo_signal(
    bar: Bar,
    ma20: float | None,
    macd_hist: float | None,
) -> Literal["buy", "sell"] | None:
    """Tín hiệu chiến lược Combo nến + MA(20) + MACD(5,25,5) thuận xu hướng (slide tr.26-29).

    Điều kiện:
    - Combo BUY: CLOSE > OPEN (nến xanh) VÀ CLOSE > MA(20) VÀ MACD_HIST > 0.
    - Combo SELL: CLOSE < OPEN (nến đỏ) VÀ CLOSE < MA(20) VÀ MACD_HIST < 0.

    Args:
        bar: Bar hiện tại.
        ma20: Giá trị MA(20) tại bar hiện tại (SMA hoặc EMA tuỳ chọn).
        macd_hist: Giá trị MACD histogram tại bar hiện tại.

    Returns:
        "buy" nếu thoả điều kiện Combo BUY.
        "sell" nếu thoả điều kiện Combo SELL.
        None nếu không thoả hoặc thiếu chỉ báo.
    """
    if ma20 is None or macd_hist is None:
        return None

    if bar.close > bar.open and bar.close > ma20 and macd_hist > 0.0:
        return "buy"

    if bar.close < bar.open and bar.close < ma20 and macd_hist < 0.0:
        return "sell"

    return None
