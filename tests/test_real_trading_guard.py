"""Chốt an toàn cho mục J (Gói S — test-only).

Mục J: octopus_pullback không bao giờ phát "bear", trong khi real_orders.py rẽ nhánh
theo "bull"/"bear". Nếu bật real_trading_enabled trong khi engine chạy octopus,
hệ thống sẽ ĐẶT LỆNH MUA THẬT VÀ KHÔNG BAO GIỜ ĐẶT LỆNH BÁN THẬT.

Test này ghim chốt an toàn ở mức cấu hình:
1. Hàm thuần _vi_pham_J kiểm chứng 4 tổ hợp.
2. Phép dò _can_emit_bear đưa chuỗi bar tất định qua compute_crossover.
3. Chốt chống mục ruỗng: bắt buộc sma_cross ra "bear", octopus không ra "bear".
4. Chốt thật: đọc trực tiếp config/config.yaml qua yaml.safe_load (không dùng load_config).
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from trading.calendar_vn import TZ
from trading.engine.main import _default_strategy
from trading.models import Bar
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.strategies.sma_cross import SmaCrossStrategy
from trading.strategy import Strategy


def _vi_pham_J(real_trading_enabled: bool, phat_duoc_bear: bool) -> bool:
    """Vi phạm mục J xảy ra KHI VÀ CHỈ KHI:
    Bật tiền thật (real_trading_enabled=True) nhưng chiến lược không thể
    phát tín hiệu 'bear' (phat_duoc_bear=False).

    Khi đó đường lệnh thật chỉ MUA, không bao giờ BÁN -> rủi ro cháy tài khoản.
    """
    return bool(real_trading_enabled and not phat_duoc_bear)


# 20 triệu cp/phiên × giá 100-350 => giá trị giao dịch 2-7 tỷ, TRÊN ngưỡng
# min_avg_value_20 = 2 tỷ của octopus. Con số này KHÔNG tuỳ tiện — xem
# test_anti_rot_octopus_cannot_emit_bear: với volume nhỏ (bản đầu dùng 100.000
# => 35 triệu/phiên) cổng thanh khoản của octopus ĐÓNG ở cả 300/300 bar, nên
# phép dò không bao giờ chạm tới logic tín hiệu và khẳng định "octopus không
# phát bear" trở thành rỗng nghĩa: nó đúng vì bar quá nhỏ, không phải vì
# chiến lược một chiều. Đây là lần thứ tư dự án vấp cùng một hình dạng lỗi —
# một ngưỡng đúng trong hệ quy chiếu thị trường thật mang sang dữ liệu tổng hợp.
_VOLUME = 20_000_000


def _generate_deterministic_bars(
    symbol: str = "GUARD",
    n_up: int = 250,
    n_down: int = 50,
) -> list[Bar]:
    """Tạo chuỗi bar tất định:
    - Giai đoạn 1 (n_up bar): Giá tăng đều từ 100.0 lên 350.0 với biên độ dao động
      đủ lớn để ATR > 0 và vượt ngưỡng atr_pct_threshold, đủ dài để vượt qua
      warmup_bars của cả SmaCross (21) lẫn Octopus (201).
    - Giai đoạn 2 (n_down bar): Giá giảm mạnh đột ngột (mỗi bar giảm 5.0) để tạo
      tín hiệu giao cắt xuống (bearish crossover) cho các chiến lược 2 chiều.
    """
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    bars: list[Bar] = []
    price = 100.0

    # Pha tăng giá: 250 bar
    for _ in range(n_up):
        price += 1.0
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=price - 2.0,
                high=price + 5.0,
                low=price - 5.0,
                close=price,
                volume=_VOLUME,
            )
        )

    # Pha giảm giá: 50 bar
    for _ in range(n_down):
        price -= 5.0
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=price + 2.0,
                high=price + 5.0,
                low=price - 5.0,
                close=price,
                volume=_VOLUME,
            )
        )

    return bars


def _can_emit_bear(strategy: Strategy) -> bool:
    """Phép dò: cho chiến lược ăn chuỗi bar tất định và gọi compute_crossover
    từng bar, ghi lại xem có bất kỳ bar nào trả về tín hiệu 'bear' hay không.
    """
    bars = _generate_deterministic_bars()
    for bar in bars:
        sig = strategy.compute_crossover(bar)
        if sig == "bear":
            return True
    return False


# ---------------------------------------------------------------------------
# (a) Kiểm thử hàm thuần với đủ 4 tổ hợp
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("real_trading_enabled", "phat_duoc_bear", "expected_vi_pham"),
    [
        (True, False, True),  # BẬT TIỀN THẬT + KHÔNG BÁN ĐƯỢC -> VI PHẠM NGUY HIỂM!
        (True, True, False),  # Bật tiền thật + có bán được -> Hợp lệ (2 chiều)
        (
            False,
            False,
            False,
        ),  # Tắt tiền thật + không bán được -> Hợp lệ (Paper/Dry-run)
        (False, True, False),  # Tắt tiền thật + có bán được -> Hợp lệ (Paper)
    ],
)
def test_vi_pham_J_pure_logic_four_combinations(
    real_trading_enabled: bool,
    phat_duoc_bear: bool,
    expected_vi_pham: bool,
):
    """Hàm thuần phải trả True khi và chỉ khi (real_trading_enabled=True, phat_duoc_bear=False)."""
    assert _vi_pham_J(real_trading_enabled, phat_duoc_bear) is expected_vi_pham


# ---------------------------------------------------------------------------
# (b) & (c) Chốt chống mục ruỗng (Anti-rot Invariant)
# ---------------------------------------------------------------------------


def test_anti_rot_sma_cross_must_emit_bear():
    """BẮT BUỘC: SmaCrossStrategy khi gặp chuỗi bar tăng rồi giảm mạnh PHẢI phát ra 'bear'.
    Nếu test này hỏng, chuỗi bar mẫu hoặc phép dò đã mất khả năng kích hoạt tín hiệu.
    """
    strategy = SmaCrossStrategy()
    assert _can_emit_bear(strategy) is True, (
        "ANTI-ROT FAILURE: SmaCrossStrategy không phát được tín hiệu 'bear' trên chuỗi bar mẫu! "
        "Phép dò _can_emit_bear đã bị mục ruỗng."
    )


def test_phep_do_vuot_qua_duoc_cong_thanh_khoan_cua_octopus():
    """Chốt chống mục ruỗng cho CHÍNH phép dò, phía octopus.

    `_can_emit_bear(octopus)` trả False vì HAI lý do rất khác nhau có thể xảy
    ra: (1) octopus một chiều thật, hoặc (2) bar mẫu quá nhỏ nên cổng thanh
    khoản `min_avg_value_20 = 2 tỷ` chặn hết, chiến lược chưa từng chạy tới
    logic tín hiệu. Bản đầu của file này rơi đúng vào (2): volume 100.000 cho
    giá trị 35 triệu/phiên, cổng ĐÓNG ở 300/300 bar — khẳng định đúng nhưng
    bằng chứng rỗng.

    Test này bắt phép dò phải đi qua được cổng, để lời khẳng định ở
    test_anti_rot_octopus_cannot_emit_bear nói về chiến lược chứ không nói về
    độ nhỏ của dữ liệu giả.
    """
    strategy = OctopusPullbackStrategy()
    mo = 0
    for bar in _generate_deterministic_bars():
        strategy.compute_crossover(bar)
        if strategy._liquidity_ok("GUARD"):
            mo += 1
    assert mo > 0, (
        f"Phép dò KHÔNG chạm tới logic tín hiệu của octopus: cổng thanh khoản "
        f"đóng ở toàn bộ bar (min_avg_value_20 = "
        f"{strategy.min_avg_value_20:,.0f}, giá trị bar mẫu quá nhỏ). "
        f"Tăng _VOLUME cho tới khi cổng mở."
    )


def test_anti_rot_octopus_cannot_emit_bear():
    """BẮT BUỘC: OctopusPullbackStrategy KHÔNG BAO GIỜ phát ra 'bear'.

    Đọc kèm test_phep_do_vuot_qua_duoc_cong_thanh_khoan_cua_octopus — không có
    test đó thì khẳng định này rỗng nghĩa.
    """
    strategy = OctopusPullbackStrategy()
    assert _can_emit_bear(strategy) is False, (
        "OctopusPullbackStrategy bất ngờ phát tín hiệu 'bear'. Nếu octopus đã được nâng cấp "
        "phát bear, hãy cập nhật lại tài liệu và chốt kiểm thử."
    )


def test_anti_rot_default_strategy_is_octopus_and_cannot_emit_bear():
    """BẮT BUỘC: _default_strategy() của engine hiện tại là octopus và không phát được 'bear'."""
    strategy = _default_strategy()
    assert isinstance(strategy, OctopusPullbackStrategy)
    assert _can_emit_bear(strategy) is False


# ---------------------------------------------------------------------------
# (d) Chốt thật: Đọc trực tiếp config/config.yaml và kiểm tra vi phạm mục J
# ---------------------------------------------------------------------------


def test_real_trading_guard_with_live_config():
    """Chốt an toàn chặn nổ tiền thật:
    Đọc config/config.yaml bằng yaml.safe_load (tuyệt đối không load_config vì đòi secret env).
    Nếu real_trading_enabled=True mà chiến lược mặc định không phát được bear -> BÁO ĐỘNG ĐỎ.
    """
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    assert config_path.is_file(), f"Không tìm thấy file config tại {config_path}"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f) or {}

    real_trading_enabled = bool(cfg_data.get("real_trading_enabled", False))
    strategy = _default_strategy()
    phat_duoc_bear = _can_emit_bear(strategy)

    assert not _vi_pham_J(real_trading_enabled, phat_duoc_bear), (
        f"NGUY HIỂM (VI PHẠM MỤC J): File config '{config_path.name}' đang bật real_trading_enabled=True, "
        f"nhưng engine đang chạy chiến lược '{strategy.__class__.__name__}' vốn KHÔNG BAO GIỜ phát "
        f"tín hiệu 'bear'. Hệ thống sẽ chỉ MUA thật mà KHÔNG BAO GIỜ BÁN thật! "
        f"Vui lòng tắt real_trading_enabled: false hoặc chuyển engine sang chiến lược hỗ trợ đóng vị thế thật."
    )
