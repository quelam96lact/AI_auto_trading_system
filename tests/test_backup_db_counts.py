"""Tests cho ban ke so dong `trading_<ts>.counts` cua scripts/backup_db.sh (Brief 137).

Chay backup_db.sh that qua bash, voi `docker` va `pg_restore` GIA tren PATH (cung cach voi
tests/test_run_if_docker_up.py). Khong can Docker.

Ban ke chup NGAY TRUOC pg_dump, cung ten goc voi file .dump, va:
  - dump hong / xac minh hong -> khong con ban ke (ban ke khong co dump la rac gay hieu nham);
  - ghi ra file tam roi doi ten, khong bao gio de lai ban ke viet do;
  - bi don theo han giu (BACKUP_RETENTION_DAYS) cung voi .dump.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"

FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *psql*)
    if [ "${FAKE_PSQL_RC:-0}" != 0 ]; then echo "psql boom" >&2; exit "$FAKE_PSQL_RC"; fi
    if [ -n "${FAKE_PSQL_EMPTY:-}" ]; then exit 0; fi
    printf 'bars\\t100\\norders\\t5\\n'
    ;;
  *pg_dump*)
    exit "${FAKE_DUMP_RC:-0}"
    ;;
  *" cp "*)
    dest="${@: -1}"
    printf 'PGDMP' > "$dest"
    ;;
  *) : ;;
esac
"""

FAKE_PG_RESTORE = """#!/usr/bin/env bash
exit "${FAKE_VERIFY_RC:-0}"
"""


def _posix(path: Path) -> str:
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/{p[0].lower()}{p[2:]}"
    return p


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("pg_restore", FAKE_PG_RESTORE)):
        f = bin_dir / name
        f.write_text(body, encoding="utf-8", newline="\n")
        f.chmod(0o755)
    backup_dir = tmp_path / "bak"
    backup_dir.mkdir()
    return bin_dir, backup_dir, tmp_path / "docker.log"


def _run(tmp_path: Path, backup_dir: Path, bin_dir: Path, log: Path, **env_extra: str):
    env = dict(os.environ)
    env.update({"FAKE_LOG": _posix(log), **env_extra})
    cmd = [
        BASH,
        "-c",
        'export PATH="$1:$PATH"; shift; exec "$@"',
        "_",
        _posix(bin_dir),
        BASH,
        _posix(REPO_ROOT / "scripts" / "backup_db.sh"),
        _posix(backup_dir),
    ]
    return subprocess.run(
        cmd, env=env, capture_output=True, text=True, cwd=str(REPO_ROOT), check=False
    )


def _files(backup_dir: Path, suffix: str) -> list[Path]:
    return sorted(p for p in backup_dir.iterdir() if p.name.endswith(suffix))


def _log_lines(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_thanh_cong_co_dump_va_ban_ke_cung_ten_goc(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log)
    assert r.returncode == 0, r.stderr
    dumps, counts = _files(bak, ".dump"), _files(bak, ".counts")
    assert len(dumps) == 1 and len(counts) == 1
    assert dumps[0].stem == counts[0].stem
    assert counts[0].read_bytes().decode() == "bars\t100\norders\t5\n"
    assert _files(bak, ".tmp") == []


def test_ban_ke_duoc_chup_TRUOC_pg_dump(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    _run(tmp_path, bak, bin_dir, log)
    lines = _log_lines(log)
    i_psql = next(i for i, ln in enumerate(lines) if "psql" in ln)
    i_dump = next(i for i, ln in enumerate(lines) if "pg_dump" in ln)
    assert i_psql < i_dump


def test_ban_ke_liet_ke_tu_catalog_khong_danh_sach_cung(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    _run(tmp_path, bak, bin_dir, log)
    psql = next(ln for ln in _log_lines(log) if "psql" in ln)
    assert (
        "pg_class" in psql
        and "relkind IN ('r','p')" in psql
        and "nspname = 'public'" in psql
    )


def test_dump_hong_khong_con_ban_ke(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log, FAKE_DUMP_RC="1")
    assert r.returncode != 0
    assert _files(bak, ".counts") == []
    assert _files(bak, ".tmp") == []


def test_xac_minh_pg_restore_hong_khong_con_dump_lan_ban_ke(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log, FAKE_VERIFY_RC="1")
    assert r.returncode == 1
    assert _files(bak, ".dump") == []
    assert _files(bak, ".counts") == []


def test_lap_ban_ke_loi_van_dump_canh_bao_khong_giet_ban_sao_luu(tmp_path):
    """Brief 138: ban ke chi la cong cu KIEM ban sao luu; loi cua no khong duoc giet luon dump.
    (Doi thanh loi cung o dot 137 da bi dao nguoc — test dot 137 cu doi hoi khong pg_dump.)
    """
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log, FAKE_PSQL_RC="1")
    assert r.returncode == 0, r.stderr
    assert len(_files(bak, ".dump")) == 1
    assert _files(bak, ".counts") == [] and _files(bak, ".tmp") == []
    assert "WARNING" in r.stderr
    assert any("pg_dump" in ln for ln in _log_lines(log))


def test_ban_ke_rong_van_dump_canh_bao_khong_de_lai_file_rong(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log, FAKE_PSQL_EMPTY="1")
    assert r.returncode == 0, r.stderr
    assert len(_files(bak, ".dump")) == 1
    assert _files(bak, ".counts") == [] and _files(bak, ".tmp") == []
    assert "WARNING" in r.stderr


def test_ban_ke_loi_roi_dump_hong_van_thoat_khac_0_va_khong_con_ban_ke(tmp_path):
    """Hai loi cung luc: dump hong van la loi cung."""
    bin_dir, bak, log = _setup(tmp_path)
    r = _run(tmp_path, bak, bin_dir, log, FAKE_PSQL_RC="1", FAKE_DUMP_RC="1")
    assert r.returncode != 0
    assert _files(bak, ".counts") == [] and _files(bak, ".tmp") == []


def test_ban_ke_cu_hon_han_giu_bi_xoa_ban_moi_thi_giu(tmp_path):
    bin_dir, bak, log = _setup(tmp_path)
    old = bak / "trading_20200101_000000.counts"
    recent = bak / "trading_20260929_020000.counts"
    for f in (old, recent):
        f.write_text("bars\t1\n", encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 20 * 86400, now - 20 * 86400))
    os.utime(recent, (now - 1 * 86400, now - 1 * 86400))
    r = _run(tmp_path, bak, bin_dir, log)
    assert r.returncode == 0, r.stderr
    assert not old.exists()
    assert recent.exists()
