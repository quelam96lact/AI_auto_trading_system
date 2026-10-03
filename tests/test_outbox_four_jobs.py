"""Test hàng đợi gửi lại cho bốn job theo lịch (Brief đợt 157).

Bốn job: backup-check, disk-check, restore-drill, daily-check. Mọi test dùng
`tmp_path` làm `--logs-dir`; không test nào chạm `logs/` thật.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts import backup_check, daily_data_check, disk_check, restore_drill
from scripts.heartbeat_check import SCHEDULE_EXIT_POLICIES

GB = 1024**3
DAILY_CODE = 2  # mã thoát "sự cố dữ liệu" mà test dựng cho daily-check

JOBS = ["backup-check", "disk-check", "restore-drill", "daily-check"]
MODULES = {
    "backup-check": backup_check,
    "disk-check": disk_check,
    "restore-drill": restore_drill,
    "daily-check": daily_data_check,
}
# Mã thoát khi gửi hỏng (= trước đợt 157). daily-check giữ nguyên `code`.
EXPECTED_FAILED_SEND_EXIT = {
    "backup-check": 2,
    "disk-check": 2,
    "restore-drill": 2,
    "daily-check": DAILY_CODE,
}
EXPECTED_OK_SEND_EXIT = {
    "backup-check": 1,
    "disk-check": 1,
    "restore-drill": 1,
    "daily-check": DAILY_CODE,
}


def _run(job, tmp_path, logs_dir, send, variant="a", dry_run=False, outbox_fn=None):
    """Chạy `main` của job, trả mã thoát. `variant` làm nội dung tin khác nhau."""
    extra = ["--dry-run"] if dry_run else []
    mod = MODULES[job]
    work = tmp_path / f"work_{job}_{variant}"
    work.mkdir(exist_ok=True)
    patches = [patch.object(mod, "send_telegram", send)]
    if outbox_fn is not None:
        patches.append(patch.object(mod, "send_with_outbox", outbox_fn))
    if job == "backup-check":
        argv = ["--backup-dir", str(work), "--logs-dir", str(logs_dir), *extra]
        runner = mod.main
    elif job == "disk-check":
        patches.append(
            patch.object(
                mod.shutil, "disk_usage", return_value=(40 * GB, 39 * GB, 1 * GB)
            )
        )
        patches.append(patch.object(mod, "docker_usage", return_value="docker"))
        argv = [
            "--path",
            str(work),
            "--backup-dir",
            "",
            "--logs-dir",
            str(logs_dir),
            *extra,
        ]
        runner = mod.main
    elif job == "restore-drill":
        argv = ["--backup-dir", str(work), "--logs-dir", str(logs_dir), *extra]
        runner = mod.main
    else:  # daily-check: main() thoát bằng SystemExit
        cfg = SimpleNamespace(ssi_equity_accounts=[], symbols=[], holidays=frozenset())
        storage = MagicMock()
        storage.read_active_universe.return_value = []
        storage.read_must_price_symbols.return_value = []
        storage.read_symbols_with_bar_on_date.return_value = set()
        patches += [
            patch.object(mod, "resolve_dsn", return_value="dsn"),
            patch.object(mod, "Storage", return_value=storage),
            patch.object(mod, "load_config", return_value=cfg),
            patch.object(
                mod,
                "evaluate_daily_completeness",
                return_value=(DAILY_CODE, ["X"], f"thieu bar {variant}"),
            ),
        ]
        # 2026-10-02 là thứ Sáu: bỏ nhánh đọc lịch sử bar.
        day = "2026-10-02" if variant == "a" else "2026-09-25"
        argv = ["--date", day, "--logs-dir", str(logs_dir), *extra]

        def runner(a):
            with pytest.raises(SystemExit) as ei:
                mod.main(a)
            return ei.value.code

    for p in patches:
        p.start()
    try:
        return runner(argv)
    finally:
        for p in reversed(patches):
            p.stop()


def _outbox(job, logs_dir) -> Path:
    return logs_dir / f"alert_outbox_{job}.jsonl"


@pytest.mark.parametrize("job", JOBS)
def test_ca1_gui_duoc_ma_thoat_nhu_truoc_va_khong_co_file_hang_doi(job, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    send = MagicMock(return_value=True)
    code = _run(job, tmp_path, logs, send)
    assert code == EXPECTED_OK_SEND_EXIT[job]
    assert send.call_count == 1
    assert not _outbox(job, logs).exists()


@pytest.mark.parametrize("job", JOBS)
def test_ca2_gui_hong_ma_thoat_nhu_truoc_va_tin_nam_trong_hang_doi(job, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    code = _run(job, tmp_path, logs, MagicMock(return_value=False))
    assert code == EXPECTED_FAILED_SEND_EXIT[job]
    f = _outbox(job, logs)
    assert f.exists()
    lines = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x]
    assert len(lines) == 1
    assert lines[0]["text"]


@pytest.mark.parametrize("job", JOBS)
def test_ca3_lan_sau_gui_duoc_tin_cu_di_truoc_roi_tin_moi_va_file_tu_xoa(
    job, tmp_path
):
    logs = tmp_path / "logs"
    logs.mkdir()
    _run(job, tmp_path, logs, MagicMock(return_value=False), variant="a")
    queued = json.loads(
        _outbox(job, logs).read_text(encoding="utf-8").splitlines()[0]
    )["text"]

    received: list[str] = []

    def ok_send(text):
        received.append(text)
        return True

    code = _run(job, tmp_path, logs, ok_send, variant="b")
    assert code == EXPECTED_OK_SEND_EXIT[job]
    assert len(received) == 2
    assert queued in received[0]  # tin CŨ trước (kèm tiền tố [GỬI TRỄ])
    assert "GỬI TRỄ" in received[0]
    assert queued not in received[1]  # rồi tin MỚI
    assert received[1] != queued  # rồi tin MỚI
    assert not _outbox(job, logs).exists()


@pytest.mark.parametrize("job", JOBS)
def test_ca4_dry_run_khong_gui_va_khong_tao_file_hang_doi(job, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    send = MagicMock(return_value=False)
    _run(job, tmp_path, logs, send, dry_run=True)
    send.assert_not_called()
    assert not _outbox(job, logs).exists()


@pytest.mark.parametrize("job", JOBS)
def test_xep_hang_KHONG_doi_ma_thoat_bang_chinh_sach_dot_156_phu_thuoc_vao_day(
    job, tmp_path
):
    """Quy tắc đợt 157: tin bị xếp hàng vẫn là tin CHƯA tới người.

    Khi `send_with_outbox` trả False (xếp hàng), mã thoát PHẢI y như trước khi có
    hàng đợi: 2 với backup-check/disk-check/restore-drill, `code` với daily-check.
    Bảng `SCHEDULE_EXIT_POLICIES` của đợt 156 phụ thuộc vào điều này: ba job đầu
    coi {0, 1} là bình thường nên mã 2 là cái duy nhất làm heartbeat báo "job chưa
    gửi được". Nếu coi "xếp hàng" là "đã gửi" (trả 1), heartbeat im lặng và tin
    nằm trong hàng đợi mà không ai hay.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    code = _run(
        job,
        tmp_path,
        logs,
        MagicMock(return_value=False),
        outbox_fn=lambda text, send, outbox_path: False,
    )
    assert code == EXPECTED_FAILED_SEND_EXIT[job]
    if job != "daily-check":
        policy = SCHEDULE_EXIT_POLICIES[job]
        assert code not in policy.normal_exit_codes, (
            "mã thoát khi xếp hàng phải nằm NGOÀI diện bình thường của bảng đợt 156"
        )


@pytest.mark.parametrize("job", JOBS)
def test_logs_dir_mac_dinh_suy_tu_vi_tri_file_va_ten_hang_doi_theo_job(job):
    mod = MODULES[job]
    assert (
        Path(mod.DEFAULT_LOGS_DIR) == Path(mod.__file__).resolve().parents[1] / "logs"
    )
    assert mod.OUTBOX_NAME == f"alert_outbox_{job}.jsonl"
def test_daily_check_ma_1_xep_hang_van_tra_1_khong_bi_keo_thanh_2(tmp_path):
    """Audit đợt 157 (Claude): ghim `daily-check` bằng mã thoát 1, không phải 2.

    Test ghim của agent dựng `daily-check` với DAILY_CODE = 2. Phá thử "xếp hàng thì
    trả 2" cũng ra 2, nên test đó KHÔNG phân biệt được hai hành vi — Claude phá thử
    và nó vẫn xanh (chỉ một test không liên quan ở test_data_quality.py bắt được, do
    may). Với mã 1 ("sót mã active"), "giữ nguyên" = 1 và "kéo theo gửi hỏng" = 2 là
    hai số khác nhau, nên ghim mới có hiệu lực.

    Bảng `SCHEDULE_EXIT_POLICIES` đợt 156 xếp mã 1 của `daily-check` vào diện bình
    thường: nếu tin bị xếp hàng mà mã thoát nhảy sang 2, heartbeat sẽ báo thêm một
    tin "job thất bại" cho một job vốn đã xử lý đúng.
    """
    import scripts.daily_data_check as mod

    logs = tmp_path / "logs"
    logs.mkdir()
    cfg = SimpleNamespace(ssi_equity_accounts=[], symbols=[], holidays=frozenset())
    storage = MagicMock()
    storage.read_active_universe.return_value = []
    storage.read_must_price_symbols.return_value = []
    storage.read_symbols_with_bar_on_date.return_value = set()

    patches = [
        patch.object(mod, "resolve_dsn", return_value="dsn"),
        patch.object(mod, "Storage", return_value=storage),
        patch.object(mod, "load_config", return_value=cfg),
        patch.object(
            mod,
            "evaluate_daily_completeness",
            return_value=(1, ["X"], "sot ma active"),
        ),
        # Tin bi XEP HANG, khong gui duoc
        patch.object(mod, "send_with_outbox", return_value=False),
    ]
    for p in patches:
        p.start()
    try:
        with pytest.raises(SystemExit) as ei:
            mod.main(["--date", "2026-10-02", "--logs-dir", str(logs)])
        assert ei.value.code == 1, (
            "xep hang KHONG duoc doi ma thoat cua daily-check: phai van la 1, "
            f"thuc te {ei.value.code}"
        )
    finally:
        for p in reversed(patches):
            p.stop()

    policy = SCHEDULE_EXIT_POLICIES["daily-check"]
    assert (
        1 in policy.normal_exit_codes
    ), "bang dot 156 phai coi ma 1 cua daily-check la binh thuong"
