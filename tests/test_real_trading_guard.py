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


def _generate_pullback_bars(symbol: str = "GUARD") -> list[Bar]:
    """Chuỗi HÌNH CHỮ V: tăng dài → chỉnh 8 nến đỏ → bật lại dốc.

    Khác chuỗi ở trên, chuỗi này đưa octopus đi HẾT đường vào lệnh, thoả cả năm
    điều kiện của `compute_crossover`: EMA9 cắt lên EMA21 (cần một nhịp chỉnh đủ
    sâu để EMA9 tụt xuống dưới trước đã), MACD hist > 0, close > EMA200,
    >= 2 nến đỏ trong 5 phiên trước, và cổng thanh khoản mở.

    Ba tham số dưới đây không tuỳ tiện: nhịp chỉnh phải đủ sâu (8 nến, −6,0) để
    EMA9 cắt xuống, và nhịp bật phải đủ dốc (+30,0) để EMA9 cắt lên lại TRONG
    vòng 5 bar — nếu bật chậm thì lúc cắt lên, cửa sổ 5 phiên trước đã sạch nến
    đỏ và điều kiện pullback trượt.
    """
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    bars: list[Bar] = []
    price = 100.0

    def add(open_: float, close_: float) -> None:
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=open_,
                high=max(open_, close_) + 1.0,
                low=min(open_, close_) - 1.0,
                close=close_,
                volume=_VOLUME,
            )
        )

    for _ in range(300):  # nền tăng, đủ dài cho EMA200
        o = price
        price += 2.0
        add(o, price)
    for _ in range(8):  # nhịp chỉnh — nến đỏ
        o = price
        price -= 6.0
        add(o, price)
    for _ in range(40):  # bật lại
        o = price
        price += 30.0
        add(o, price)

    return bars


def _signals(strategy: Strategy, bars: list[Bar]) -> set[str | None]:
    """Tập tín hiệu chiến lược phát ra trên một chuỗi bar."""
    return {strategy.compute_crossover(bar) for bar in bars}


def _can_emit_bear(strategy: Strategy) -> bool:
    """Phép dò: cho chiến lược ăn chuỗi bar tất định và gọi compute_crossover
    từng bar, ghi lại xem có bất kỳ bar nào trả về tín hiệu 'bear' hay không.
    """
    return "bear" in _signals(strategy, _generate_deterministic_bars())


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


def test_anti_rot_phep_do_cham_duoc_duong_vao_lenh_cua_octopus():
    """Chốt chống mục ruỗng cho CHÍNH phép dò, phía octopus.

    "Octopus không phát bear" có thể đúng vì HAI lý do rất khác nhau:
    (1) chiến lược một chiều thật, hoặc (2) bar mẫu không bao giờ đưa nó tới
    chỗ ra quyết định, nên nó im lặng vì lý do chẳng liên quan gì. Bản đầu của
    file này rơi đúng vào (2) theo cách tệ nhất: volume 100.000 cho giá trị 35
    triệu/phiên, cổng thanh khoản 2 tỷ ĐÓNG ở cả 300/300 bar.

    Test này đòi bằng chứng dương: trên chuỗi chữ V, octopus PHẢI phát "bull"
    ít nhất một lần. Phát được "bull" nghĩa là cả năm điều kiện đã chạy qua
    (kể cả cổng thanh khoản) — tức phép dò thật sự chạm vào logic tín hiệu.
    Chỉ khi đó câu "cũng chuỗi ấy mà không có 'bear' nào" mới nói về chiến
    lược, chứ không nói về độ nhỏ của dữ liệu giả.
    """
    tin_hieu = _signals(OctopusPullbackStrategy(), _generate_pullback_bars())
    assert "bull" in tin_hieu, (
        f"Phép dò KHÔNG chạm tới đường vào lệnh của octopus — chuỗi mẫu không "
        f"kích hoạt nổi một tín hiệu nào (thấy: {sorted(map(str, tin_hieu))}). "
        f"Mọi khẳng định 'octopus không phát bear' dựa trên chuỗi này đều rỗng "
        f"nghĩa cho tới khi test này xanh trở lại."
    )


def test_anti_rot_octopus_cannot_emit_bear():
    """BẮT BUỘC: OctopusPullbackStrategy KHÔNG BAO GIỜ phát ra 'bear'.

    Kiểm trên CẢ HAI chuỗi — chuỗi giảm sâu (nơi sma_cross phát bear) và chuỗi
    chữ V (nơi octopus thật sự vào lệnh). Đọc kèm
    test_anti_rot_phep_do_cham_duoc_duong_vao_lenh_cua_octopus: không có test
    đó thì khẳng định này rỗng nghĩa.
    """
    assert _can_emit_bear(OctopusPullbackStrategy()) is False, (
        "OctopusPullbackStrategy bất ngờ phát tín hiệu 'bear'. Nếu octopus đã được nâng cấp "
        "phát bear, hãy cập nhật lại tài liệu và chốt kiểm thử."
    )
    assert "bear" not in _signals(
        OctopusPullbackStrategy(), _generate_pullback_bars()
    ), "OctopusPullbackStrategy phát 'bear' trên chuỗi chữ V — mục J đã đổi bản chất."


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
