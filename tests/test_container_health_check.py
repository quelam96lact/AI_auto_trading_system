"""Unit tests cho scripts/container_health_check.py.

Brief đợt 130 (2026-09-29):
Kiểm tra mọi tình huống theo bảng §1b và §2a:
- Lần đầu chạy (chưa có trạng thái): ghi mốc, không cảnh báo.
- Id đổi (tạo lại container / deploy mới): ghi mốc, không cảnh báo.
- RestartCount tăng: CRITICAL.
- State.OOMKilled == true: CRITICAL.
- oom_kill tăng (tiến trình con bị kill): CRITICAL.
- State.Status != 'running': CRITICAL.
- memory.events max tăng: chỉ ghi log, KHÔNG cảnh báo.
- memory.events không đọc được: giữ None, không coi là 0.
- File trạng thái hỏng: coi như lần đầu, không ném lỗi.
- Gửi Telegram thất bại: trả mã 2 và KHÔNG cập nhật file trạng thái.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from scripts.container_health_check import (
    ContainerStats,
    evaluate_container_health,
    load_state,
    main,
    parse_memory_events,
    save_state,
)
from trading.calendar_vn import TZ


def _make_stat(
    name: str = "test-service-1",
    container_id: str = "cid_1234567890",
    restart_count: int = 0,
    status: str = "running",
    oom_killed: bool = False,
    started_at: str = "2026-09-29T10:00:00Z",
    oom_kill: int | None = 0,
    mem_max: int | None = 0,
    read_error: str | None = None,
    health_status: str = "none",
) -> ContainerStats:
    return ContainerStats(
        name=name,
        container_id=container_id,
        restart_count=restart_count,
        status=status,
        oom_killed=oom_killed,
        started_at=started_at,
        oom_kill=oom_kill,
        mem_max=mem_max,
        read_error=read_error,
        health_status=health_status,
    )


def test_first_run_records_baseline_no_alert():
    """Lần chạy đầu: ghi nhận mốc trạng thái, không tạo cảnh báo nào."""
    stat = _make_stat(restart_count=0, oom_kill=0, mem_max=10)
    alerts, new_state, info_logs = evaluate_container_health(
        {"test-1": stat},
        previous_state={},
    )
    assert len(alerts) == 0
    assert "test-1" in new_state
    assert new_state["test-1"]["id"] == "cid_1234567890"
    assert new_state["test-1"]["restart_count"] == 0
    assert any("Ghi mốc ban đầu" in log for log in info_logs)


def test_container_recreated_id_changed_no_alert():
    """Container được tạo lại (Id thay đổi): ghi mốc mới, không coi là crash."""
    prev_state = {
        "test-1": {
            "id": "old_id_111111",
            "restart_count": 5,
            "oom_kill": 2,
            "mem_max": 100,
        }
    }
    stat = _make_stat(container_id="new_id_222222", restart_count=0, oom_kill=0)
    alerts, new_state, info_logs = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert len(alerts) == 0
    assert new_state["test-1"]["id"] == "new_id_222222"
    assert any("đã được tạo lại" in log for log in info_logs)


def test_restart_count_increased_critical():
    """Cùng Id nhưng RestartCount tăng: cảnh báo CRITICAL container tự khởi động lại."""
    prev_state = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 1,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    stat = _make_stat(restart_count=3)
    alerts, new_state, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert len(alerts) == 1
    assert "[CRITICAL] test-1: container tự khởi động lại 2 lần" in alerts[0]
    assert new_state["test-1"]["restart_count"] == 3


def test_state_oom_killed_critical():
    """State.OOMKilled == true: cảnh báo CRITICAL."""
    prev_state = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    stat = _make_stat(oom_killed=True)
    alerts, _, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert any("State.OOMKilled == true" in a for a in alerts)


def test_oom_kill_increased_critical():
    """Cùng Id nhưng oom_kill trong cgroup memory.events tăng: cảnh báo CRITICAL."""
    prev_state = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    stat = _make_stat(oom_kill=1)
    alerts, new_state, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert any("kernel kill tiến trình con trong container" in a for a in alerts)
    assert new_state["test-1"]["oom_kill"] == 1


def test_status_not_running_critical():
    """Container không ở trạng thái running (ví dụ: exited): cảnh báo CRITICAL."""
    prev_state = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    stat = _make_stat(status="exited")
    alerts, _, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert any("không ở trạng thái running (Status: exited)" in a for a in alerts)


def test_memory_events_max_increased_log_only():
    """memory.events max tăng: chỉ ghi dòng INFO log, KHÔNG cảnh báo."""
    prev_state = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 100,
        }
    }
    stat = _make_stat(mem_max=150)
    alerts, new_state, info_logs = evaluate_container_health(
        {"test-1": stat},
        previous_state=prev_state,
    )
    assert len(alerts) == 0
    assert any("memory.events max tăng từ 100 lên 150" in log for log in info_logs)
    assert new_state["test-1"]["mem_max"] == 150


def test_memory_events_unreadable_not_zero():
    """memory.events không đọc được: oom_kill và max trả về None, KHÔNG coi là 0."""
    oom, max_v = parse_memory_events("invalid cgroup content or empty")
    assert oom is None
    assert max_v is None

    stat = _make_stat(oom_kill=None, mem_max=None)
    _, new_state, info_logs = evaluate_container_health(
        {"test-1": stat},
        previous_state={},
    )
    assert new_state["test-1"]["oom_kill"] is None
    assert new_state["test-1"]["mem_max"] is None
    assert any("không đọc được" in log for log in info_logs)


def test_state_file_corrupted_treated_as_first_run(tmp_path):
    """File trạng thái bị hỏng hoặc không đúng JSON: coi như lần đầu, không ném exception."""
    corrupted_file = tmp_path / "corrupted_state.json"
    corrupted_file.write_text("{this is not valid json", encoding="utf-8")

    data = load_state(str(corrupted_file))
    assert data == {}

    # File không phải dạng dict
    list_file = tmp_path / "list_state.json"
    list_file.write_text("[1, 2, 3]", encoding="utf-8")
    data2 = load_state(str(list_file))
    assert data2 == {}


def test_save_and_load_state_roundtrip(tmp_path):
    """Lưu và nạp lại trạng thái an toàn qua JSON."""
    sf = tmp_path / "state.json"
    sample_data = {
        "service-a": {"id": "111", "restart_count": 2, "oom_kill": 0}
    }
    save_state(str(sf), sample_data)
    loaded = load_state(str(sf))
    assert loaded == sample_data


def test_dry_run_without_state_file_returns_2():
    """Cờ --dry-run mà thiếu --state-file: thoát mã 2."""
    ret = main(["--dry-run"])
    assert ret == 2


@patch("scripts.container_health_check.check_docker_daemon", return_value=True)
@patch("scripts.container_health_check.inspect_container")
@patch("scripts.container_health_check.send_telegram", return_value=False)
def test_send_telegram_failure_returns_2_and_state_unchanged(
    mock_send, mock_inspect, mock_daemon, tmp_path
):
    """Khi có cảnh báo mà gửi Telegram thất bại: trả mã 2 và KHÔNG cập nhật file trạng thái."""
    state_file = tmp_path / "state.json"
    initial_state = {
        "test-app": {
            "id": "cid_old",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    state_file.write_text(json.dumps(initial_state), encoding="utf-8")

    # Container bị crash: restart_count tăng lên 3
    mock_inspect.return_value = _make_stat(
        name="test-app",
        container_id="cid_old",
        restart_count=3,
    )

    ret = main(["--containers", "test-app", "--state-file", str(state_file)])
    # Gửi Telegram thất bại -> mã 2
    assert ret == 2

    # Trạng thái trong file PHẢI GIỮ NGUYÊN để lần sau báo lại
    current_saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert current_saved["test-app"]["restart_count"] == 0


@patch("scripts.container_health_check.check_docker_daemon", return_value=True)
@patch("scripts.container_health_check.inspect_container")
@patch("scripts.container_health_check.send_telegram", return_value=True)
def test_send_telegram_success_returns_1_and_updates_state(
    mock_send, mock_inspect, mock_daemon, tmp_path
):
    """Khi có cảnh báo và gửi Telegram thành công: trả mã 1 và cập nhật file trạng thái."""
    state_file = tmp_path / "state.json"
    initial_state = {
        "test-app": {
            "id": "cid_old",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    state_file.write_text(json.dumps(initial_state), encoding="utf-8")

    mock_inspect.return_value = _make_stat(
        name="test-app",
        container_id="cid_old",
        restart_count=3,
    )

    ret = main(["--containers", "test-app", "--state-file", str(state_file)])
    assert ret == 1

    current_saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert current_saved["test-app"]["restart_count"] == 3


@patch("scripts.container_health_check.check_docker_daemon", return_value=True)
@patch("scripts.container_health_check.inspect_container")
def test_dry_run_with_alerts_returns_1_and_saves_state(
    mock_inspect, mock_daemon, tmp_path
):
    """--dry-run khi có cảnh báo: in cảnh báo, trả 1, và lưu trạng thái vào file tạm."""
    state_file = tmp_path / "dry_state.json"
    initial_state = {
        "test-app": {
            "id": "cid_old",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
        }
    }
    state_file.write_text(json.dumps(initial_state), encoding="utf-8")

    mock_inspect.return_value = _make_stat(
        name="test-app",
        container_id="cid_old",
        restart_count=1,
    )

    ret = main([
        "--containers",
        "test-app",
        "--dry-run",
        "--state-file",
        str(state_file),
    ])
    assert ret == 1

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["test-app"]["restart_count"] == 1


@patch("scripts.container_health_check.check_docker_daemon", return_value=False)
def test_docker_daemon_down_returns_2(mock_daemon, tmp_path):
    """Docker daemon không hoạt động: trả mã 2."""
    state_file = tmp_path / "state.json"
    ret = main(["--state-file", str(state_file)])
    assert ret == 2


def test_oom_killed_khong_reo_lai_khi_khong_doi():
    """OOMKilled còn true nhưng đã báo lần trước: chỉ log, KHÔNG cảnh báo lại.

    Đo thật 29/09 (audit đợt 130): bản đầu báo lại mọi lần chạy, nên cron 10 phút
    gửi ~144 tin/ngày cho một sự cố không đổi và chôn mất sự cố mới.
    """
    stat = _make_stat(oom_killed=True)
    # lần 1: chuyển trạng thái -> phải cảnh báo
    alerts1, state1, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state={
            "test-1": {
                "id": "cid_1234567890",
                "restart_count": 0,
                "oom_kill": 0,
                "mem_max": 0,
                "status": "running",
                "oom_killed": False,
            }
        },
    )
    assert any("State.OOMKilled == true" in a for a in alerts1)
    assert state1["test-1"]["oom_killed"] is True

    # lần 2: nạp lại đúng trạng thái vừa lưu -> KHÔNG được cảnh báo nữa
    alerts2, _, info2 = evaluate_container_health({"test-1": stat}, previous_state=state1)
    assert not any("State.OOMKilled" in a for a in alerts2), alerts2
    assert any("vẫn mang cờ OOMKilled" in i for i in info2), info2


def test_status_khong_running_khong_reo_lai_khi_khong_doi():
    """Container vẫn exited sau khi đã báo: chỉ log, KHÔNG cảnh báo lại."""
    stat = _make_stat(status="exited")
    alerts1, state1, _ = evaluate_container_health(
        {"test-1": stat},
        previous_state={
            "test-1": {
                "id": "cid_1234567890",
                "restart_count": 0,
                "oom_kill": 0,
                "mem_max": 0,
                "status": "running",
                "oom_killed": False,
            }
        },
    )
    assert any("không ở trạng thái running" in a for a in alerts1)

    alerts2, _, info2 = evaluate_container_health({"test-1": stat}, previous_state=state1)
    assert not any("không ở trạng thái running" in a for a in alerts2), alerts2
    assert any("vẫn ở trạng thái exited" in i for i in info2), info2


def test_su_co_MOI_van_bao_du_da_co_su_co_cu():
    """Sự cố cũ đang kéo dài KHÔNG được che sự cố mới (oom_kill tăng thêm)."""
    prev = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 1,
            "mem_max": 0,
            "status": "running",
            "oom_killed": True,  # da bao truoc do
        }
    }
    stat = _make_stat(oom_killed=True, oom_kill=2)  # co lan kill MOI
    alerts, _, _ = evaluate_container_health({"test-1": stat}, previous_state=prev)
    assert any("kernel kill tiến trình con" in a for a in alerts), alerts
    assert not any("State.OOMKilled" in a for a in alerts), alerts


def test_read_error_khong_reo_lai_khi_khong_doi():
    """read_error chỉ báo khi chuyển trạng thái; lỗi kéo dài thì ghi log, không reo lại (đợt 131 Việc 7)."""
    stat = _make_stat(status="missing", read_error="container không tồn tại")
    prev_normal = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "read_error": None,
        }
    }
    # Lần 1: chuyển từ bình thường sang lỗi đọc -> phải cảnh báo
    alerts1, state1, _ = evaluate_container_health({"test-1": stat}, previous_state=prev_normal)
    assert any("lỗi đọc container" in a for a in alerts1), alerts1
    assert state1["test-1"]["read_error"] == "container không tồn tại"

    # Lần 2: cùng lỗi kéo dài -> chỉ log, KHÔNG cảnh báo lại
    alerts2, _, info2 = evaluate_container_health({"test-1": stat}, previous_state=state1)
    assert not any("lỗi đọc container" in a for a in alerts2), alerts2
    assert any("vẫn lỗi đọc" in i for i in info2), info2


def test_memory_events_unreadable_keeps_old_baseline_catches_later_oom():
    """memory.events đọc hỏng một lần: giữ mốc cũ, không bị mù OOM ở lần sau (đợt 131 Việc 7)."""
    prev = {
        "test-1": {
            "id": "cid_1234567890",
            "restart_count": 0,
            "oom_kill": 2,
            "mem_max": 100,
            "status": "running",
        }
    }
    # Lần 1: đọc cgroup hỏng (oom_kill=None) -> phải giữ lại mốc cũ 2
    stat_unreadable = _make_stat(oom_kill=None, mem_max=None)
    alerts1, state1, info1 = evaluate_container_health({"test-1": stat_unreadable}, previous_state=prev)
    assert len(alerts1) == 0
    assert state1["test-1"]["oom_kill"] == 2
    assert state1["test-1"]["mem_max"] == 100
    assert any("không đọc được memory.events oom_kill, giữ lại mốc cũ (2)" in i for i in info1)

    # Lần 2: sau đó tiến trình bị OOM (oom_kill tăng lên 3) -> phải so được với mốc 2 và báo động
    stat_oom = _make_stat(oom_kill=3, mem_max=120)
    alerts2, state2, _ = evaluate_container_health({"test-1": stat_oom}, previous_state=state1)
    assert any("memory.events oom_kill tăng 1, từ 2 lên 3" in a for a in alerts2), alerts2
    assert state2["test-1"]["oom_kill"] == 3


def test_su_co_MOI_van_bao_khi_read_error_dang_keo_dai():
    """Sự cố mới trên container khác vẫn phải báo động dù container kia đang lỗi kéo dài (đợt 131 Việc 7)."""
    prev_state = {
        "service-1": {
            "id": "",
            "restart_count": 0,
            "oom_kill": None,
            "mem_max": None,
            "status": "missing",
            "read_error": "daemon timeout",
        },
        "service-2": {
            "id": "cid_222222",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "read_error": None,
        },
    }
    stats = {
        "service-1": _make_stat(name="service-1", status="missing", read_error="daemon timeout"),
        "service-2": _make_stat(name="service-2", container_id="cid_222222", restart_count=1),
    }
    alerts, _, info = evaluate_container_health(stats, previous_state=prev_state)
    # service-2 phải được cảnh báo
    assert any("service-2: container tự khởi động lại 1 lần" in a for a in alerts), alerts
    # service-1 không được cảnh báo lại vì lỗi cũ kéo dài
    assert not any("service-1" in a for a in alerts), alerts
    assert any("service-1 vẫn lỗi đọc" in i for i in info), info


def test_scheduler_in_default_services():
    """Đợt 202: scheduler phải nằm trong danh sách DEFAULT_SERVICES."""
    from scripts.container_health_check import DEFAULT_SERVICES

    assert "scheduler" in DEFAULT_SERVICES


def test_inspect_container_parses_health_status():
    """Kiểm tra inspect_container đọc đúng State.Health: healthy, unhealthy, starting, none."""
    from unittest.mock import MagicMock

    from scripts.container_health_check import inspect_container

    cases = [
        ("cid1 0 running false 2026-11-09T00:00:00Z healthy", "healthy"),
        ("cid2 0 running false 2026-11-09T00:00:00Z unhealthy", "unhealthy"),
        ("cid3 0 running false 2026-11-09T00:00:00Z starting", "starting"),
        ("cid4 0 running false 2026-11-09T00:00:00Z none", "none"),
        ("cid5 0 running false 2026-11-09T00:00:00Z", "none"),  # Định dạng cũ 5 trường
    ]

    for stdout_text, expected_health in cases:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = stdout_text
        mock_proc.stderr = ""

        # Khi gọi inspect_container: lần 1 gọi inspect, lần 2 gọi cgroup memory.events
        mock_cgroup = MagicMock()
        mock_cgroup.returncode = 0
        mock_cgroup.stdout = "oom_kill 0\nmax 100\n"

        with patch("subprocess.run", side_effect=[mock_proc, mock_cgroup]):
            stat = inspect_container("test-service")
            assert stat.health_status == expected_health, f"Thất bại với {stdout_text}"


def test_container_unhealthy_critical_alert_and_deduplication():
    """unhealthy: báo CRITICAL; lần sau vẫn unhealthy -> không báo lại (chỉ log info)."""
    prev = {
        "postgres": {
            "id": "cid_pg_1",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "health_status": "healthy",
        }
    }
    stat_unhealthy = _make_stat(
        name="postgres",
        container_id="cid_pg_1",
        status="running",
        health_status="unhealthy",
    )

    # Lần 1: chuyển từ healthy -> unhealthy: phải báo CRITICAL
    alerts1, state1, _ = evaluate_container_health(
        {"postgres": stat_unhealthy}, previous_state=prev
    )
    assert len(alerts1) == 1
    assert "[CRITICAL] postgres: container UNHEALTHY (healthcheck thất bại)" in alerts1[0]
    assert state1["postgres"]["health_status"] == "unhealthy"

    # Lần 2: tiếp tục unhealthy: không báo lại
    alerts2, state2, info2 = evaluate_container_health(
        {"postgres": stat_unhealthy}, previous_state=state1
    )
    assert alerts2 == []
    assert state2["postgres"]["health_status"] == "unhealthy"
    assert any("vẫn ở trạng thái unhealthy" in i for i in info2)


def test_container_unhealthy_to_healthy_recovery_alert():
    """unhealthy chuyển sang healthy -> báo INFO hồi phục một lần (Lead Adjustment 5)."""
    prev = {
        "postgres": {
            "id": "cid_pg_1",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "health_status": "unhealthy",
        }
    }
    stat_healthy = _make_stat(
        name="postgres",
        container_id="cid_pg_1",
        status="running",
        health_status="healthy",
    )

    # Chuyển từ unhealthy -> healthy: báo INFO hồi phục
    alerts, state, _ = evaluate_container_health(
        {"postgres": stat_healthy}, previous_state=prev
    )
    assert len(alerts) == 1
    assert "[INFO] postgres: container ĐÃ HỒI PHỤC (healthcheck chuyển sang healthy)" in alerts[0]
    assert state["postgres"]["health_status"] == "healthy"

    # Lần sau vẫn healthy -> không báo gì
    alerts_next, _, _ = evaluate_container_health(
        {"postgres": stat_healthy}, previous_state=state
    )
    assert alerts_next == []


def test_container_starting_healthy_none_no_alert():
    """starting, healthy và none không bao giờ tạo cảnh báo."""
    prev = {
        "app": {
            "id": "cid_app_1",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "health_status": "none",
        }
    }
    for h in ["none", "starting", "healthy"]:
        stat = _make_stat(
            name="app",
            container_id="cid_app_1",
            status="running",
            health_status=h,
        )
        alerts, state, _ = evaluate_container_health(
            {"app": stat}, previous_state=prev
        )
        assert alerts == [], f"Không được báo cảnh báo cho {h}"
        assert state["app"]["health_status"] == h


# =============================================================================
# Task 6 (Brief 218): Phân biệt Docker daemon tắt (exit 2) và chậm (exit 4)
# =============================================================================


def test_docker_daemon_returncode_nonzero_returns_2(tmp_path, monkeypatch):
    """docker info trả returncode != 0 (daemon tắt): thoát mã 2."""
    import subprocess

    def mock_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout=b"", stderr=b"daemon down"
        )

    monkeypatch.setattr("scripts.container_health_check.RUN_CMD", mock_run)
    state_file = tmp_path / "state.json"
    ret = main(["--state-file", str(state_file)])
    assert ret == 2


def test_docker_daemon_timeout_then_retry_ok(tmp_path, monkeypatch):
    """Lần 1 timeout, thử lại lần 2 OK (returncode 0): chạy tiếp bình thường."""
    import subprocess

    calls = []

    def mock_run(*args, **kwargs):
        calls.append(kwargs.get("timeout"))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(
                cmd=args[0], timeout=kwargs.get("timeout", 10.0)
            )
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=b"", stderr=b""
        )

    monkeypatch.setattr("scripts.container_health_check.RUN_CMD", mock_run)
    monkeypatch.setattr("scripts.container_health_check.TIMEOUT_FIRST", 1.0)
    monkeypatch.setattr("scripts.container_health_check.TIMEOUT_RETRY", 2.0)
    monkeypatch.setattr(
        "scripts.container_health_check.inspect_container",
        lambda name: _make_stat(name=name),
    )
    monkeypatch.setattr(
        "scripts.container_health_check.get_last_called_timestamp",
        lambda *a, **k: (datetime.now(TZ), None),
    )
    state_file = tmp_path / "state.json"
    ret = main(["--state-file", str(state_file)])
    assert len(calls) == 2
    assert calls == [1.0, 2.0]
    assert ret == 0


def test_docker_daemon_timeout_both_times_returns_4(tmp_path, capsys, monkeypatch):
    """Timeout cả 2 lần (daemon chậm): in thông báo và thoát mã 4."""
    import subprocess

    calls = []

    def mock_run(*args, **kwargs):
        calls.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(
            cmd=args[0], timeout=kwargs.get("timeout", 10.0)
        )

    monkeypatch.setattr("scripts.container_health_check.RUN_CMD", mock_run)
    monkeypatch.setattr("scripts.container_health_check.TIMEOUT_FIRST", 1.0)
    monkeypatch.setattr("scripts.container_health_check.TIMEOUT_RETRY", 2.0)
    state_file = tmp_path / "state.json"
    ret = main(["--state-file", str(state_file)])
    assert len(calls) == 2
    assert calls == [1.0, 2.0]
    assert ret == 4
    captured = capsys.readouterr()
    assert (
        "LỖI: Docker daemon đang chạy nhưng không phản hồi trong 30s (chậm)"
        in captured.out
    )


def test_container_health_policy_does_not_contain_4():
    """Policy container-health không coi mã 4 là bình thường để chuông cảnh báo."""
    from scripts.heartbeat_check import SCHEDULE_EXIT_POLICIES

    policy = SCHEDULE_EXIT_POLICIES["container-health"]
    assert 4 not in policy.normal_exit_codes
    assert "4" in policy.reason


# ==============================================================================
# Tests cho Đợt 223 (Sửa template docker inspect .Id -> .ID, lỗi đọc kéo dài)
# ==============================================================================


def test_inspect_template_uses_uppercase_id():
    """Việc 1(a): Khẳng định template docker inspect không chứa {{.Id}} và có {{.ID}}."""
    import inspect

    from scripts import container_health_check

    src = inspect.getsource(container_health_check.inspect_container)
    assert "{{.Id}}" not in src, "Template không được chứa {{.Id}} vì gây lỗi trên Docker 29"
    assert "{{.ID}}" in src, "Template phải dùng {{.ID}}"


@pytest.mark.integration
def test_inspect_container_integration_nats_test():
    """Việc 1(b): Gọi thật inspect_container trên ai_auto_trading_system-nats-test-1."""
    import subprocess

    from scripts.container_health_check import inspect_container

    container_name = "ai_auto_trading_system-nats-test-1"
    try:
        res = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={container_name}",
                "--filter",
                "status=running",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            pytest.skip(f"Container {container_name} không chạy hoặc không có docker")
    except Exception as e:
        pytest.skip(f"Không thể kiểm tra docker: {e}")

    stat = inspect_container(container_name)
    assert stat.read_error is None, f"Lỗi đọc container: {stat.read_error}"
    assert stat.status == "running"
    assert stat.health_status == "none"
    assert len(stat.container_id) == 64


@patch("scripts.container_health_check.check_docker_daemon", return_value=0)
@patch("scripts.container_health_check.inspect_container")
@patch("scripts.container_health_check.send_telegram", return_value=True)
def test_persistent_read_error_exits_4_and_does_not_spam(
    mock_send, mock_inspect, mock_daemon, tmp_path
):
    """Việc 2: Lỗi đọc lần 1 thoát khác 0 (1) và có cảnh báo; lần 2 giống hệt thoát khác 0 (4) và không cảnh báo; hết lỗi thoát 0."""
    state_file = tmp_path / "state.json"

    # Lần 1: lỗi đọc mới
    mock_inspect.return_value = _make_stat(
        name="test-app",
        status="missing",
        read_error="template parsing error: map has no entry for key Health",
    )
    ret1 = main(["--containers", "test-app", "--state-file", str(state_file)])
    assert ret1 != 0
    assert ret1 == 1
    assert mock_send.call_count == 1
    assert "[CRITICAL] test-app: lỗi đọc container" in mock_send.call_args[0][0]

    # Lần 2: lỗi đọc kéo dài giống hệt
    mock_send.reset_mock()
    ret2 = main(["--containers", "test-app", "--state-file", str(state_file)])
    assert ret2 != 0
    assert ret2 == 4
    assert mock_send.call_count == 0  # Không cảnh báo lại (chống lặp)

    # Lần 3: hết lỗi (đọc được bình thường)
    mock_send.reset_mock()
    mock_inspect.return_value = _make_stat(
        name="test-app",
        container_id="cid_new_1234567890",
        status="running",
        read_error=None,
    )
    ret3 = main(["--containers", "test-app", "--state-file", str(state_file)])
    assert ret3 == 0
    assert mock_send.call_count == 0


def test_transition_from_blind_to_readable_id_changed_info_only():
    """Việc 3(a): Chuyển từ mù (read_error, status='missing') sang đọc được với Id đổi -> chỉ ghi INFO, không có CRITICAL."""
    prev_blind_state = {
        "collector": {
            "id": "old_id_1111111111111111111111111111111111111111111111111111111111111111",
            "restart_count": 0,
            "oom_kill": None,
            "mem_max": None,
            "status": "missing",
            "oom_killed": False,
            "started_at": "",
            "read_error": "template parsing error: template: :1:97: executing \"\" at <.State.Health>: map has no entry for key \"Health\"",
            "health_status": "none",
        }
    }
    stat_new_id = _make_stat(
        name="collector",
        container_id="new_id_2222222222222222222222222222222222222222222222222222222222222222",
        restart_count=0,
        status="running",
        read_error=None,
        health_status="none",
    )
    alerts, new_state, info_logs = evaluate_container_health(
        {"collector": stat_new_id}, previous_state=prev_blind_state
    )
    assert alerts == [], f"Id đổi không được sinh cảnh báo CRITICAL: {alerts}"
    assert any("đã được tạo lại" in msg for msg in info_logs)
    assert new_state["collector"]["id"] == stat_new_id.container_id
    assert new_state["collector"]["read_error"] is None


def test_transition_from_blind_to_readable_id_same_restart_count_increased():
    """Việc 3(b): Chuyển từ mù sang đọc được với Id giữ nguyên và RestartCount tăng -> PHẢI có cảnh báo CRITICAL restart."""
    cid = "same_id_3333333333333333333333333333333333333333333333333333333333333333"
    prev_blind_state = {
        "nats": {
            "id": cid,
            "restart_count": 1,
            "oom_kill": None,
            "mem_max": None,
            "status": "missing",
            "oom_killed": False,
            "started_at": "",
            "read_error": "template parsing error: template: :1:97: executing \"\" at <.State.Health>: map has no entry for key \"Health\"",
            "health_status": "none",
        }
    }
    stat_restarted = _make_stat(
        name="nats",
        container_id=cid,
        restart_count=3,
        status="running",
        read_error=None,
        health_status="none",
    )
    alerts, new_state, _ = evaluate_container_health(
        {"nats": stat_restarted}, previous_state=prev_blind_state
    )
    assert len(alerts) == 1
    assert (
        "[CRITICAL] nats: container tự khởi động lại 2 lần (RestartCount tăng từ 1 lên 3)"
        in alerts[0]
    )
    assert new_state["nats"]["restart_count"] == 3
    assert new_state["nats"]["read_error"] is None


# ==============================================================================
# Tests cho Đợt 224 (Bắt restart cùng Id qua StartedAt và reset mốc memory.events)
# ==============================================================================


def test_same_id_started_at_changed_critical():
    """Cùng Id, StartedAt đổi, RestartCount không tăng -> sinh 1 CRITICAL nêu rõ StartedAt cũ và mới."""
    prev_state = {
        "postgres": {
            "id": "cid_postgres_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "oom_killed": False,
            "started_at": "2026-11-12T14:53:15Z",
            "read_error": None,
            "health_status": "healthy",
        }
    }
    stat = _make_stat(
        name="postgres",
        container_id="cid_postgres_1234567890",
        restart_count=0,
        status="running",
        started_at="2026-11-13T00:46:18Z",
        health_status="healthy",
    )
    alerts, new_state, _ = evaluate_container_health({"postgres": stat}, prev_state)
    assert len(alerts) == 1
    assert "[CRITICAL] postgres: container đã khởi động lại" in alerts[0]
    assert "2026-11-12T14:53:15Z" in alerts[0]
    assert "2026-11-13T00:46:18Z" in alerts[0]
    assert new_state["postgres"]["started_at"] == "2026-11-13T00:46:18Z"


def test_same_id_started_at_unchanged_no_alert():
    """Cùng Id, StartedAt không đổi -> không sinh cảnh báo."""
    ts = "2026-11-13T00:46:18Z"
    prev_state = {
        "postgres": {
            "id": "cid_postgres_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "oom_killed": False,
            "started_at": ts,
            "read_error": None,
            "health_status": "healthy",
        }
    }
    stat = _make_stat(
        name="postgres",
        container_id="cid_postgres_1234567890",
        restart_count=0,
        status="running",
        started_at=ts,
        health_status="healthy",
    )
    alerts, new_state, _ = evaluate_container_health({"postgres": stat}, prev_state)
    assert alerts == []
    assert new_state["postgres"]["started_at"] == ts


def test_prev_started_at_empty_records_baseline_no_alert():
    """Trạng thái cũ có started_at = '' (từ thời còn mù) -> ghi mốc, không báo."""
    prev_state = {
        "postgres": {
            "id": "cid_postgres_1234567890",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "missing",
            "oom_killed": False,
            "started_at": "",
            "read_error": "template parsing error",
            "health_status": "none",
        }
    }
    stat = _make_stat(
        name="postgres",
        container_id="cid_postgres_1234567890",
        restart_count=0,
        status="running",
        started_at="2026-11-13T00:46:18Z",
        health_status="healthy",
    )
    alerts, new_state, _ = evaluate_container_health({"postgres": stat}, prev_state)
    assert alerts == [], f"started_at rỗng không được báo động: {alerts}"
    assert new_state["postgres"]["started_at"] == "2026-11-13T00:46:18Z"


def test_same_id_started_at_changed_and_restart_count_increased_single_alert():
    """Cùng Id, StartedAt đổi VÀ RestartCount tăng -> đúng 1 cảnh báo cho container đó (không báo trùng)."""
    prev_state = {
        "nats": {
            "id": "cid_nats_1234567890",
            "restart_count": 1,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "oom_killed": False,
            "started_at": "2026-11-12T14:53:15Z",
            "read_error": None,
            "health_status": "none",
        }
    }
    stat = _make_stat(
        name="nats",
        container_id="cid_nats_1234567890",
        restart_count=2,
        status="running",
        started_at="2026-11-13T00:46:18Z",
        health_status="none",
    )
    alerts, new_state, _ = evaluate_container_health({"nats": stat}, prev_state)
    assert len(alerts) == 1, f"Chỉ được có đúng 1 cảnh báo, thực tế: {alerts}"
    assert "[CRITICAL] nats: container tự khởi động lại 1 lần" in alerts[0]
    assert new_state["nats"]["restart_count"] == 2
    assert new_state["nats"]["started_at"] == "2026-11-13T00:46:18Z"


@patch("scripts.container_health_check.evaluate_heartbeat_watch", return_value=([], None, []))
@patch("scripts.container_health_check.check_docker_daemon", return_value=0)
@patch("scripts.container_health_check.inspect_container")
@patch("scripts.container_health_check.send_telegram", return_value=True)
def test_six_containers_started_at_changed_single_telegram_message(
    mock_send, mock_inspect, mock_daemon, mock_hb, tmp_path
):
    """6 container cùng đổi StartedAt (daemon restart) -> main() gom vào đúng 1 tin Telegram."""
    state_file = tmp_path / "state.json"
    old_ts = "2026-11-12T14:53:15Z"
    new_ts = "2026-11-13T00:46:18Z"
    cnames = [f"svc-{i}" for i in range(1, 7)]

    initial_state = {}
    for name in cnames:
        initial_state[name] = {
            "id": f"cid_{name}",
            "restart_count": 0,
            "oom_kill": 0,
            "mem_max": 0,
            "status": "running",
            "oom_killed": False,
            "started_at": old_ts,
            "read_error": None,
            "health_status": "none",
        }
    state_file.write_text(json.dumps(initial_state), encoding="utf-8")

    def fake_inspect(name):
        return _make_stat(
            name=name,
            container_id=f"cid_{name}",
            restart_count=0,
            status="running",
            started_at=new_ts,
            health_status="none",
        )

    mock_inspect.side_effect = fake_inspect

    ret = main(["--containers", ",".join(cnames), "--state-file", str(state_file)])
    assert ret == 1
    assert mock_send.call_count == 1, f"Chỉ được gửi đúng 1 tin Telegram, thực tế gọi {mock_send.call_count} lần"

    sent_msg = mock_send.call_args[0][0]
    for name in cnames:
        assert name in sent_msg, f"Tin nhắn phải chứa thông tin của {name}"


def test_oom_kill_baseline_reset_on_restart_chain():
    """Chuỗi OOM ở mục 2: mốc oom_kill = 2 -> restart oom_kill về 0 -> lần sau oom_kill = 1 -> kỳ vọng có CRITICAL OOM."""
    prev_state = {
        "engine": {
            "id": "cid_engine_1234567890",
            "restart_count": 0,
            "oom_kill": 2,
            "mem_max": 500,
            "status": "running",
            "oom_killed": False,
            "started_at": "2026-11-12T14:53:15Z",
            "read_error": None,
            "health_status": "none",
        }
    }

    # Lần 1: Restart, oom_kill về 0 (cgroup mới)
    stat_restart = _make_stat(
        name="engine",
        container_id="cid_engine_1234567890",
        restart_count=0,
        status="running",
        started_at="2026-11-13T00:46:18Z",
        oom_kill=0,
        mem_max=100,
        health_status="none",
    )
    alerts1, state1, _ = evaluate_container_health({"engine": stat_restart}, prev_state)
    assert len(alerts1) == 1
    assert "[CRITICAL] engine: container đã khởi động lại" in alerts1[0]
    # state1 phải cập nhật mốc oom_kill mới = 0
    assert state1["engine"]["oom_kill"] == 0

    # Lần 2: Chạy tiếp theo, oom_kill tăng từ 0 lên 1
    stat_oom = _make_stat(
        name="engine",
        container_id="cid_engine_1234567890",
        restart_count=0,
        status="running",
        started_at="2026-11-13T00:46:18Z",
        oom_kill=1,
        mem_max=150,
        health_status="none",
    )
    alerts2, _, _ = evaluate_container_health({"engine": stat_oom}, state1)
    assert len(alerts2) == 1
    assert "[CRITICAL] engine: kernel kill tiến trình con trong container vì hết bộ nhớ" in alerts2[0]
    assert "từ 0 lên 1" in alerts2[0]







