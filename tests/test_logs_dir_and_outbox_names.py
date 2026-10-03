"""Test gom DEFAULT_LOGS_DIR và tên file hàng đợi về một chỗ (Brief đợt 158).

Đợt này không đổi hành vi: mọi đường dẫn tính ra phải y hệt trước.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULES = [
    "heartbeat_check",
    "backup_check",
    "disk_check",
    "restore_drill",
    "daily_data_check",
]
# Viết THẲNG tên nguyên văn, không sinh bằng cùng công thức đang kiểm (bài học đợt 157).
EXPECTED_OUTBOX_FILE = {
    "heartbeat_check": "alert_outbox_heartbeat.jsonl",
    "backup_check": "alert_outbox_backup-check.jsonl",
    "disk_check": "alert_outbox_disk-check.jsonl",
    "restore_drill": "alert_outbox_restore-drill.jsonl",
    "daily_data_check": "alert_outbox_daily-check.jsonl",
}


def _outbox_name_of(mod) -> str:
    return getattr(mod, "OUTBOX_NAME", None) or mod.HEARTBEAT_OUTBOX_NAME


def test_nam_module_cho_ra_cung_mot_duong_dan_logs_bang_goc_repo_logs():
    values = {
        m: importlib.import_module(f"scripts.{m}").DEFAULT_LOGS_DIR for m in MODULES
    }
    assert len(set(values.values())) == 1, values
    only = next(iter(values.values()))
    assert os.path.normcase(only) == os.path.normcase(str(REPO / "logs"))


def test_duong_dan_logs_KHONG_doi_khi_chay_tu_thu_muc_khac(tmp_path):
    """Tính chất quan trọng: job cron chạy với cwd do sched.sh đặt, không phải repo."""
    code = (
        "import importlib, json;"
        f"ms = {MODULES!r};"
        "print(json.dumps({m: importlib.import_module('scripts.'+m).DEFAULT_LOGS_DIR"
        " for m in ms}))"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout.strip().splitlines()[-1])
    for m, v in got.items():
        assert os.path.isabs(v), (m, v)
        assert os.path.normcase(v) == os.path.normcase(str(REPO / "logs")), (m, v)


@pytest.mark.parametrize("module", MODULES)
def test_ten_file_hang_doi_nguyen_van_nhu_truoc(module):
    mod = importlib.import_module(f"scripts.{module}")
    assert _outbox_name_of(mod) == EXPECTED_OUTBOX_FILE[module]


def test_ham_dung_chung_cho_ra_ten_va_duong_dan_nguyen_van(tmp_path):
    from scripts._alert_common import outbox_name

    assert outbox_name("heartbeat") == "alert_outbox_heartbeat.jsonl"
    assert outbox_name("restore-drill") == "alert_outbox_restore-drill.jsonl"
