"""Unit tests cho hàm đánh giá thuần evaluate_golive_gate trong scripts/check_golive_gate.py (Brief 57 Task 3)."""

from scripts.check_golive_gate import evaluate_golive_gate


def test_golive_gate_all_pass_returns_zero():
    """Tất cả tiêu chí đều đạt chuẩn -> trả mã 0."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,  # 5 phút <= 15 phút
        position_age_sec=300.0,      # 5 phút <= 15 phút
        stream_coverage=0.95,        # 95% >= 90%
        stream_coverage_summary="95% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
    )
    assert exit_code == 0
    statuses = {it.name: it.status for it in items}
    assert statuses["Tài khoản & NAV"] == "PASS"
    assert statuses["Sức mua tối thiểu"] == "PASS"
    assert statuses["Lá chắn độ tươi vị thế"] == "PASS"
    assert statuses["Lá chắn độ tươi sức mua"] == "PASS"
    assert statuses["Độ phủ luồng phiên gần nhất"] == "PASS"
    assert statuses["Đường truyền Telegram"] == "PASS"
    assert statuses["Lệch triển khai (Image vs Git)"] == "PASS"


def test_golive_gate_warning_returns_one():
    """Các lá chắn đạt nhưng độ phủ luồng hơi thấp (< 90% nhưng >= 50%) -> trả mã 1."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=0.889,  # 88.9% < 90% nhưng >= 50% -> WARN
        stream_coverage_summary="88.9% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
    )
    assert exit_code == 1
    statuses = {it.name: it.status for it in items}
    assert statuses["Độ phủ luồng phiên gần nhất"] == "WARN"
    assert statuses["Lá chắn độ tươi vị thế"] == "PASS"


def test_golive_gate_stale_failsafe_returns_two():
    """Lá chắn vị thế hoặc sức mua quá hạn (> 15 phút) -> trả mã 2 (chặn bật)."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=3600.0,  # 60 phút > 15 phút -> FAIL
        stream_coverage=0.95,
        stream_coverage_summary="95% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
    )
    assert exit_code == 2
    statuses = {it.name: it.status for it in items}
    assert statuses["Lá chắn độ tươi vị thế"] == "FAIL"


def test_golive_gate_insufficient_buying_power_returns_two():
    """Sức mua < 100cp ở một mã -> trả mã 2 (chặn bật)."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 50, "IJC": 600, "AAA": 600},  # HPG chỉ có 50cp < 100cp
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=0.95,
        stream_coverage_summary="95% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
    )
    assert exit_code == 2
    statuses = {it.name: it.status for it in items}
    assert statuses["Sức mua tối thiểu"] == "FAIL"


def test_golive_gate_missing_telegram_returns_two():
    """Thiếu biến môi trường Telegram -> trả mã 2."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=0.95,
        stream_coverage_summary="95% coverage",
        telegram_configured=False,  # Thiếu env Telegram -> FAIL
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
    )
    assert exit_code == 2
    statuses = {it.name: it.status for it in items}
    assert statuses["Đường truyền Telegram"] == "FAIL"


def test_golive_gate_stream_coverage_measured_value_with_timestamp_and_age():
    """Brief 70 Task 2: Item 6 hiển thị thời điểm đo và độ tuổi."""
    from datetime import datetime

    from trading.calendar_vn import TZ

    measured_at = datetime(2026, 9, 18, 15, 10, tzinfo=TZ)
    age_sec = 2 * 86400.0  # 2 ngày
    _exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=0.895,
        stream_coverage_summary="89.5% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        stream_measured_at=measured_at,
        stream_age_sec=age_sec,
    )
    item6 = next(it for it in items if it.name == "Độ phủ luồng phiên gần nhất")
    assert item6.measured_value == "89.5% (do luc 18/09 15:10, 2 ngay truoc)"


# ==============================================================================
# Brief 79: Task 1 (Lá chắn phiên gần nhất cho độ phủ luồng) & Task 2 (Độ tươi NAV)
# ==============================================================================


def test_golive_gate_stream_coverage_wrong_session_fails():
    """Brief 79 Task 1: Tiêu chí 6 phải FAIL nếu số đo không thuộc phiên hoàn tất gần nhất (dù 100% coverage)."""
    from datetime import datetime

    from trading.calendar_vn import TZ

    # Ngày 22/09 đo luồng, ngày 23/09 chạy cổng lúc 22:14 VN (sau 14:45)
    measured_at = datetime(2026, 9, 22, 15, 10, tzinfo=TZ)
    now_run = datetime(2026, 9, 23, 22, 14, tzinfo=TZ)

    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,  # 100% độ phủ nhưng sai phiên
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        stream_measured_at=measured_at,
        stream_age_sec=(now_run - measured_at).total_seconds(),
        now=now_run,
    )
    assert exit_code == 2
    item6 = next(it for it in items if it.name == "Độ phủ luồng phiên gần nhất")
    assert item6.status == "FAIL"
    assert "Số đo từ phiên 22/09 nhưng phiên hoàn tất gần nhất là 23/09" in item6.note


def test_golive_gate_stream_coverage_correct_session_passes():
    """Brief 79 Task 1: Số đo cùng phiên hoàn tất gần nhất và coverage >= 90% -> PASS."""
    from datetime import datetime

    from trading.calendar_vn import TZ

    measured_at = datetime(2026, 9, 23, 15, 10, tzinfo=TZ)
    now_run = datetime(2026, 9, 23, 22, 14, tzinfo=TZ)

    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        stream_measured_at=measured_at,
        stream_age_sec=(now_run - measured_at).total_seconds(),
        now=now_run,
    )
    assert exit_code == 0
    item6 = next(it for it in items if it.name == "Độ phủ luồng phiên gần nhất")
    assert item6.status == "PASS"


def test_golive_gate_stream_coverage_weekend_monday_morning_passes():
    """Brief 79 Task 1: Chạy sáng thứ Hai (trước 14:45), phiên gần nhất là thứ Sáu -> PASS."""
    from datetime import datetime

    from trading.calendar_vn import TZ

    # Thứ Sáu: 2026-09-25 15:10, Thứ Hai: 2026-09-28 08:30 (trước 14:45)
    measured_at = datetime(2026, 9, 25, 15, 10, tzinfo=TZ)
    now_run = datetime(2026, 9, 28, 8, 30, tzinfo=TZ)

    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        stream_measured_at=measured_at,
        stream_age_sec=(now_run - measured_at).total_seconds(),
        now=now_run,
    )
    assert exit_code == 0
    item6 = next(it for it in items if it.name == "Độ phủ luồng phiên gần nhất")
    assert item6.status == "PASS"


def test_golive_gate_nav_stale_warns():
    """Brief 79 Task 2: NAV cũ hơn 24h -> WARN (exit_code 1), không chặn bật (không FAIL)."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        nav_age_sec=28.0 * 3600.0,  # 28 giờ > 24 giờ
    )
    assert exit_code == 1
    item2 = next(it for it in items if it.name == "Tài khoản & NAV")
    assert item2.status == "WARN"
    assert "24h" in item2.note


def test_golive_gate_nav_fresh_passes():
    """Brief 79 Task 2: NAV tươi <= 24h -> PASS."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        nav_age_sec=2.0 * 3600.0,  # 2 giờ <= 24 giờ
    )
    assert exit_code == 0
    item2 = next(it for it in items if it.name == "Tài khoản & NAV")
    assert item2.status == "PASS"


def test_golive_gate_nav_boundary_24h():
    """Brief 79 Task 2: Đúng mốc 24h biên -> PASS (vì engine dùng age_h > 24)."""
    exit_code, items = evaluate_golive_gate(
        real_trading_enabled=False,
        real_account="0434221",
        nav=5_000_000.0,
        buying_powers={"HPG": 200, "IJC": 600, "AAA": 600},
        buying_power_age_sec=300.0,
        position_age_sec=300.0,
        stream_coverage=1.0,
        stream_coverage_summary="100.0% coverage",
        telegram_configured=True,
        deploy_drift_ok=True,
        deploy_drift_msg="Khớp image",
        real_fills_count=0,
        symbols=["HPG", "IJC", "AAA"],
        nav_age_sec=24.0 * 3600.0,  # Đúng 24.0 giờ
    )
    assert exit_code == 0
    item2 = next(it for it in items if it.name == "Tài khoản & NAV")
    assert item2.status == "PASS"


