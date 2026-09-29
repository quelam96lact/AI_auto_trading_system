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
from unittest.mock import patch

from scripts.container_health_check import (
    ContainerStats,
    evaluate_container_health,
    load_state,
    main,
    parse_memory_events,
    save_state,
)


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


