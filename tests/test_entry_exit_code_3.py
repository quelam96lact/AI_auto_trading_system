"""Tests cho Task 4 (Brief 217): Phân biệt crash với 'đã báo' (mã thoát 3).

1. Bắt Exception ở điểm vào if __name__ == "__main__": và sys.exit(3).
2. SCHEDULE_EXIT_POLICIES không chứa mã 3 trong normal_exit_codes.
"""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path

import pytest

from scripts.heartbeat_check import SCHEDULE_EXIT_POLICIES

SCRIPTS = [
    ("heartbeat", "scripts.heartbeat_check", "scripts/heartbeat_check.py"),
    ("daily-check", "scripts.daily_data_check", "scripts/daily_data_check.py"),
    ("deploy-drift", "scripts.deploy_drift_check", "scripts/deploy_drift_check.py"),
    ("engine-cam", "scripts.check_silent_engine", "scripts/check_silent_engine.py"),
    ("engine-consumer", "scripts.engine_consumer_check", "scripts/engine_consumer_check.py"),
    ("backup-check", "scripts.backup_check", "scripts/backup_check.py"),
    ("disk-check", "scripts.disk_check", "scripts/disk_check.py"),
    ("restore-drill", "scripts.restore_drill", "scripts/restore_drill.py"),
    ("container-health", "scripts.container_health_check", "scripts/container_health_check.py"),
    ("orderbook-daily-check", "scripts.check_orderbook_daily", "scripts/check_orderbook_daily.py"),
]


def test_exit_policies_exclude_exit_code_3():
    """Mã 3 không nằm trong normal_exit_codes của bất kỳ job nào trong 10 script."""
    for branch, _, _ in SCRIPTS:
        policy = SCHEDULE_EXIT_POLICIES.get(branch)
        assert policy is not None, f"Không tìm thấy policy cho nhánh {branch}"
        assert 3 not in policy.normal_exit_codes, (
            f"Nhánh {branch} không được coi mã 3 là bình thường trong SCHEDULE_EXIT_POLICIES"
        )


@pytest.mark.parametrize("branch,mod_name,file_path", SCRIPTS)
def test_entry_point_exits_3_on_unhandled_exception(
    branch: str, mod_name: str, file_path: str, monkeypatch: pytest.MonkeyPatch
):
    """Khi main() ném RuntimeError, khối entry bắt Exception và thoát với mã 3."""
    mod = importlib.import_module(mod_name)

    def failing_main(*args, **kwargs):
        raise RuntimeError("Simulated crash in test")

    monkeypatch.setattr(mod, "main", failing_main)

    content = Path(file_path).read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in content
    entry_code = content.split('if __name__ == "__main__":')[1]
    dedented_code = textwrap.dedent(entry_code)

    with pytest.raises(SystemExit) as exc_info:
        exec(dedented_code, mod.__dict__)  # noqa: S102
    assert exc_info.value.code == 3
