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
