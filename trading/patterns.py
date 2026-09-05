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
    lookback_prior: int = 5,
    require_range: bool = True,
) -> bool:
    """Nhận dạng nến Doji theo slide Buổi 9&10 (tr.12).

    Quy tắc:
    - Giá đóng cửa rất gần giá mở cửa: |close - open| <= doji_ratio * (high - low).
    - Doji hoàn hảo khi close == open.
    - Luật Near Doji: Nếu trước đó trong `lookback_prior` phiên có > `max_prior_doji` nến Doji,
      mẫu hình Doji hiện tại bị coi là KHÔNG hiệu quả (trả về False).

    Args:
        bar: Bar hiện tại cần kiểm tra.
        prev_bars: Danh sách các bar trước đó (sắp xếp tăng dần theo thời gian).
        doji_ratio: Tỷ lệ thân nến tối đa so với toàn bộ chiều dài nến (mặc định 0.1 = 10%).
        max_prior_doji: Số lượng Doji tối đa cho phép xuất hiện trước đó (mặc định 2).
        lookback_prior: Số nến nhìn lại phía trước để đếm Doji (mặc định 5 nến).
        require_range: Nến PHẲNG (high == low) có được tính là doji không.

    VỀ `require_range` — đây là điểm mơ hồ THỨ TÁM của slide, phát hiện khi
    audit 06/09, không có trong danh sách 7 điểm ở brief:

    Theo chữ của slide (tr.12) thì "doji hoàn hảo là close == open", và một nến
    phẳng thoả điều đó. Nhưng nến phẳng không có biên độ: nó không phải thế
    giằng co giữa mua và bán — nó là KHÔNG CÓ THỊ TRƯỜNG. Trên `bars_daily`
    của dự án này, 36,6% số bar là phẳng và 25,2% có volume = 0 (mã thanh
    khoản kém, nhiều phiên không khớp lệnh nào).

    Đo khi audit: để `require_range=False` (hành vi bản đầu) thì 43,1% số doji
    tìm được là nến phẳng — con số tổng bị thổi lên khoảng 1,8 lần so với số
    doji trên nến có giao dịch thật.

    Mặc định `True` (nến phẳng KHÔNG phải doji) vì phép đếm này tồn tại để trả
    lời "có đủ tín hiệu giao dịch được không". Đặt `False` để tái hiện đúng chữ
    của slide.
    """
    candle_range = bar.high - bar.low
    if candle_range <= 0.0:
        # Nến phẳng (high == low). Xem khối giải thích `require_range` ở trên.
        is_cur_doji = (not require_range) and bar.close == bar.open
    else:
        body = abs(bar.close - bar.open)
        is_cur_doji = body <= doji_ratio * candle_range

    if not is_cur_doji:
        return False

    # Kiểm tra luật Near Doji nếu có lịch sử bar trước đó
    if prev_bars:
        window = (
            prev_bars[-lookback_prior:]
            if len(prev_bars) > lookback_prior
            else prev_bars
        )
        prior_doji_count = 0
        for b in window:
            b_range = b.high - b.low
            if b_range <= 0.0:
                # Cùng luật với nến hiện tại — nếu nến phẳng không phải doji
                # thì nó cũng không được tính vào hạn ngạch Near Doji.
                if (not require_range) and b.close == b.open:
                    prior_doji_count += 1
            else:
                if abs(b.close - b.open) <= doji_ratio * b_range:
                    prior_doji_count += 1

        if prior_doji_count > max_prior_doji:
            return False

    return True


def is_hammer(
    bar: Bar,
    prev_bars: list[Bar] | None = None,
    trend_lookback: int = 3,
    body_ratio: float = 0.35,
    lower_shadow_multiplier: float = 2.0,
    upper_shadow_ratio: float = 0.1,
) -> bool:
    """Nhận dạng nến Búa (Hammer / Bullish Pin bar) thoả mãn 4 điều kiện slide (tr.19).

    4 điều kiện:
    1. Xuất hiện sau một xu hướng GIẢM GIÁ (downtrend).
    2. Thân búa ở phần TRÊN của cây nến (thân tăng hay giảm đều được).
    3. Bóng nến DƯỚI dài gấp ít nhất `lower_shadow_multiplier` lần thân nến (>= 2x thân).
    4. Bóng nến TRÊN rất ngắn (<= `upper_shadow_ratio` * chiều dài nến).

    Args:
        bar: Bar hiện tại cần kiểm tra.
        prev_bars: Danh sách các bar trước đó (sắp xếp tăng dần theo thời gian).
        trend_lookback: Số bar tối thiểu cần nhìn lại để xác định xu hướng giảm.
        body_ratio: Tỷ lệ thân nến tối đa so với toàn bộ chiều dài nến (mặc định 0.35).
        lower_shadow_multiplier: Hệ số tối thiểu của bóng dưới so với thân nến (mặc định 2.0).
        upper_shadow_ratio: Tỷ lệ bóng trên tối đa so với toàn bộ chiều dài nến (mặc định 0.1).
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

    # ĐK1: Xuất hiện sau một xu hướng GIẢM GIÁ
    if prev_bars is not None and len(prev_bars) >= trend_lookback:
        window = prev_bars[-trend_lookback:]
        # Xu hướng giảm: giá bar trước thấp hơn bar đầu cửa sổ
        # và bar hiện tại tạo đáy thấp mới hoặc duy trì đà giảm
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
