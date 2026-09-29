"""Cảnh báo khi container tự khởi động lại hoặc bị kill vì hết bộ nhớ.

Brief đợt 130 (2026-09-29):
Giám sát các service postgres, collector, engine, nats, grafana:
- Phát hiện crash/restart (RestartCount tăng).
- Phát hiện OOMKilled (State.OOMKilled == true).
- Phát hiện kernel kill tiến trình con trong container (cgroup memory.events oom_kill tăng).
- Phát hiện container không ở trạng thái running.
- Ghi nhận memory.events max tăng ra log (không báo động spam).

Mã thoát:
  0: Mọi thứ ổn, hoặc ghi nhận mốc mới thành công.
  1: Có cảnh báo và đã gửi thành công (hoặc in ra khi --dry-run).
  2: Sai cấu hình, lỗi Docker daemon, hoặc cảnh báo cần gửi mà gửi hỏng.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from typing import Any, NamedTuple

try:
    from scripts.deploy_drift_check import get_container_name
except ImportError:
    from deploy_drift_check import get_container_name

try:
    from scripts.docker_down_alert import SPAM_GUARD_FILE
except ImportError:
    try:
        from docker_down_alert import SPAM_GUARD_FILE
    except ImportError:
        SPAM_GUARD_FILE = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs",
            ".docker_down_last_alert",
        )

from trading.alerts import _print_safe
from trading.telegram import send_telegram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_SERVICES = ("postgres", "collector", "engine", "nats", "grafana")

DEFAULT_STATE_FILE = os.path.join(
    os.path.dirname(SPAM_GUARD_FILE),
    ".container_health_state.json",
)


class ContainerStats(NamedTuple):
    name: str
    container_id: str
    restart_count: int
    status: str
    oom_killed: bool
    started_at: str
    oom_kill: int | None
    mem_max: int | None
    read_error: str | None = None


def parse_memory_events(raw_text: str) -> tuple[int | None, int | None]:
    """Parse nội dung file /sys/fs/cgroup/memory.events để lấy (oom_kill, max).

    Nếu không parse được hoặc rỗng, trả về None thay vì 0.
    """
    oom_kill = None
    mem_max = None
    for line in raw_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            key, val = parts[0], parts[1]
            if key == "oom_kill" and val.isdigit():
                oom_kill = int(val)
            elif key == "max" and val.isdigit():
                mem_max = int(val)
    return oom_kill, mem_max


def inspect_container(name: str) -> ContainerStats:
    """Đọc thông số container qua docker inspect và docker exec memory.events."""
    try:
        res = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.Id}} {{.RestartCount}} {{.State.Status}} {{.State.OOMKilled}} {{.State.StartedAt}}",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"docker inspect {name} quá thời gian 30s")
    except Exception as e:
        raise RuntimeError(f"docker inspect {name} lỗi: {e}")

    if res.returncode != 0:
        err = res.stderr.strip() or "container không tồn tại hoặc docker lỗi"
        return ContainerStats(
            name=name,
            container_id="",
            restart_count=0,
            status="missing",
            oom_killed=False,
            started_at="",
            oom_kill=None,
            mem_max=None,
            read_error=err,
        )

    parts = res.stdout.strip().split()
    if len(parts) < 5:
        return ContainerStats(
            name=name,
            container_id="",
            restart_count=0,
            status="parse_error",
            oom_killed=False,
            started_at="",
            oom_kill=None,
            mem_max=None,
            read_error=f"Không parse được output inspect: {res.stdout.strip()}",
        )

    cid, rc_str, status, oom_str, started_at = (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
    )
    rc = int(rc_str) if rc_str.isdigit() else 0
    oom_killed = oom_str.lower() == "true"

    oom_kill = None
    mem_max = None
    if status == "running":
        try:
            cgroup_res = subprocess.run(
                ["docker", "exec", name, "cat", "/sys/fs/cgroup/memory.events"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if cgroup_res.returncode == 0:
                oom_kill, mem_max = parse_memory_events(cgroup_res.stdout)
            else:
                _print_safe(
                    f"[container-health] {name}: không đọc được memory.events (rc={cgroup_res.returncode})"
                )
        except Exception as e:
            _print_safe(f"[container-health] {name}: lỗi đọc memory.events: {e}")

    return ContainerStats(
        name=name,
        container_id=cid,
        restart_count=rc,
        status=status,
        oom_killed=oom_killed,
        started_at=started_at,
        oom_kill=oom_kill,
        mem_max=mem_max,
        read_error=None,
    )


def evaluate_container_health(
    stats_map: dict[str, ContainerStats],
    previous_state: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[str, Any]], list[str]]:
    """Hàm thuần túy (pure function) đánh giá các quy tắc theo bảng §1b.

    Trả về:
      alerts: Danh sách các thông báo cảnh báo CRITICAL (gửi Telegram).
      new_state: Trạng thái mới tính toán để lưu lại nếu cảnh báo thành công.
      info_logs: Danh sách các dòng thông tin ghi log (không cảnh báo Telegram).
    """
    alerts: list[str] = []
    info_logs: list[str] = []
    new_state: dict[str, dict[str, Any]] = dict(previous_state)

    for name, stat in stats_map.items():
        if stat.read_error:
            alerts.append(f"[CRITICAL] {name}: lỗi đọc container ({stat.read_error})")
            continue

        prev = previous_state.get(name)

        # Trạng thái hiện tại sẽ ghi nếu hợp lệ
        current_record: dict[str, Any] = {
            "id": stat.container_id,
            "restart_count": stat.restart_count,
            "oom_kill": stat.oom_kill,
            "mem_max": stat.mem_max,
            "status": stat.status,
            "oom_killed": stat.oom_killed,
            "started_at": stat.started_at,
        }

        # 1. Lần chạy đầu (chưa có trạng thái)
        if not prev:
            info_logs.append(
                f"[container-health] Ghi mốc ban đầu cho {name}: "
                f"Id={stat.container_id[:12]}, RestartCount={stat.restart_count}, "
                f"oom_kill={stat.oom_kill if stat.oom_kill is not None else 'không đọc được'}, "
                f"max={stat.mem_max if stat.mem_max is not None else 'không đọc được'}"
            )
            new_state[name] = current_record
            continue

        prev_id = prev.get("id", "")

        # 2. Id đổi (container được tạo lại, ví dụ deploy mới)
        if stat.container_id != prev_id:
            info_logs.append(
                f"[container-health] Container {name} đã được tạo lại "
                f"(Id đổi: {prev_id[:12]} -> {stat.container_id[:12]}). Ghi mốc mới."
            )
            new_state[name] = current_record
            continue

        # Cùng Id: kiểm tra các sự cố.
        #
        # OOMKilled và Status là TRẠNG THÁI, không phải bộ đếm: chúng đứng nguyên
        # cho tới khi container được tạo lại. Báo động vô điều kiện ở đây thì cron
        # 10 phút sẽ gửi ~144 tin/ngày cho MỘT sự cố không đổi, và một sự cố MỚI
        # sẽ bị chôn trong nhiễu (đo thật 29/09: lần 3, 4, 5, 6 đều reo lại).
        # Nên chỉ báo khi CHUYỂN trạng thái; còn kéo dài thì ghi log.
        # Thiếu khoá trong trạng thái cũ => coi là chuyển (báo một lần, an toàn).

        # 3. Status không phải running
        if stat.status != "running":
            if prev.get("status") != stat.status:
                alerts.append(
                    f"[CRITICAL] {name}: container không ở trạng thái running (Status: {stat.status})"
                )
            else:
                info_logs.append(
                    f"[container-health] INFO: {name} vẫn ở trạng thái {stat.status} (đã báo trước đó)"
                )

        # 4. State.OOMKilled == true
        if stat.oom_killed:
            if not prev.get("oom_killed", False):
                alerts.append(
                    f"[CRITICAL] {name}: State.OOMKilled == true (container bị kernel kill vì hết bộ nhớ)"
                )
            else:
                info_logs.append(
                    f"[container-health] INFO: {name} vẫn mang cờ OOMKilled từ lần chết trước (đã báo)"
                )

        # 5. RestartCount tăng
        prev_rc = prev.get("restart_count", 0)
        if stat.restart_count > prev_rc:
            diff_rc = stat.restart_count - prev_rc
            alerts.append(
                f"[CRITICAL] {name}: container tự khởi động lại {diff_rc} lần "
                f"(RestartCount tăng từ {prev_rc} lên {stat.restart_count})"
            )

        # 6. oom_kill tăng (tiến trình con bị kernel kill)
        prev_oom = prev.get("oom_kill")
        if (
            stat.oom_kill is not None
            and prev_oom is not None
            and stat.oom_kill > prev_oom
        ):
            diff_oom = stat.oom_kill - prev_oom
            alerts.append(
                f"[CRITICAL] {name}: kernel kill tiến trình con trong container vì hết bộ nhớ "
                f"(memory.events oom_kill tăng {diff_oom}, từ {prev_oom} lên {stat.oom_kill})"
            )

        # 7. memory.events max tăng: chỉ in log, KHÔNG cảnh báo
        prev_max = prev.get("mem_max")
        if (
            stat.mem_max is not None
            and prev_max is not None
            and stat.mem_max > prev_max
        ):
            info_logs.append(
                f"[container-health] INFO: {name} memory.events max tăng từ {prev_max} lên {stat.mem_max}"
            )

        new_state[name] = current_record

    return alerts, new_state, info_logs


def load_state(filepath: str) -> dict[str, dict[str, Any]]:
    """Đọc file trạng thái JSON. Nếu không tồn tại hoặc lỗi, trả về {}."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            _print_safe(
                f"[container-health] File trạng thái {filepath} không đúng định dạng dict — coi như lần đầu."
            )
            return {}
    except Exception as e:
        _print_safe(
            f"[container-health] File trạng thái {filepath} hỏng hoặc không đọc được ({e}) — coi như lần chạy đầu."
        )
        return {}


def save_state(filepath: str, state: dict[str, dict[str, Any]]) -> None:
    """Ghi trạng thái ra file JSON an toàn qua file tạm."""
    dir_path = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_path, exist_ok=True)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, filepath)


def check_docker_daemon() -> bool:
    """Kiểm tra Docker daemon có phản hồi hay không trong 10s."""
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kiểm tra sức khoẻ container và cảnh báo restart / OOM."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chế độ chạy thử: in cảnh báo thay vì gửi Telegram.",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default="",
        help="Đường dẫn file trạng thái JSON (bắt buộc khi có --dry-run).",
    )
    parser.add_argument(
        "--containers",
        type=str,
        default="",
        help="Danh sách tên container phân cách bằng dấu phẩy.",
    )

    args = parser.parse_args(argv)

    # Brief §1c: --dry-run bắt buộc đi kèm --state-file
    if args.dry_run and not args.state_file:
        _print_safe("LỖI: --dry-run bắt buộc đi kèm --state-file <đường_dẫn_tạm>")
        return 2

    state_file = args.state_file if args.state_file else DEFAULT_STATE_FILE

    # Brief §1b: docker không chạy hoặc hết timeout: không cảnh báo ở đây, thoát 2
    if not check_docker_daemon():
        _print_safe("LỖI: Docker daemon không chạy hoặc không phản hồi trong 10s.")
        return 2

    # Xác định danh sách tên container cần kiểm tra
    if args.containers:
        container_names = [c.strip() for c in args.containers.split(",") if c.strip()]
    else:
        container_names = [get_container_name(s) for s in DEFAULT_SERVICES]

    # Đọc trạng thái cũ
    prev_state = load_state(state_file)

    # Đọc thông số hiện tại của từng container
    stats_map: dict[str, ContainerStats] = {}
    for cname in container_names:
        try:
            stat = inspect_container(cname)
            stats_map[cname] = stat
        except Exception as e:
            _print_safe(f"LỖI: Không thể kiểm tra container {cname}: {e}")
            return 2

    # Đánh giá luật thuần túy
    alerts, new_state, info_logs = evaluate_container_health(stats_map, prev_state)

    # In các dòng thông tin nếu có
    for info in info_logs:
        _print_safe(info)

    if alerts:
        alert_body = "\n".join(alerts)
        _print_safe(alert_body)

        if args.dry_run:
            _print_safe(
                "[DRY-RUN] Không gửi Telegram thật. Lưu trạng thái vào file tạm."
            )
            save_state(state_file, new_state)
            return 1
        else:
            # Gửi thật qua Telegram
            sent = send_telegram(alert_body)
            if sent:
                # Trạng thái chỉ được cập nhật SAU KHI cảnh báo đã gửi thành công
                save_state(state_file, new_state)
                return 1
            else:
                _print_safe(
                    "LỖI: Cảnh báo cần gửi nhưng send_telegram trả về thất bại!"
                )
                # Không cập nhật trạng thái để lần sau báo lại
                return 2

    # Không có cảnh báo: lưu trạng thái mốc mới và thoát 0
    save_state(state_file, new_state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
