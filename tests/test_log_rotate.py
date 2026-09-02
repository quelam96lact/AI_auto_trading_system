"""Tests cho scripts/log_rotate.sh (brief agent B 02/09/2026, phan 1).

Xoay log theo kich thuoc cho cac file trong logs/ ma dam scheduled task ghi.
Tat dinh: khong sleep, khong so gio tuong — chi tao file + chay bash.
Chay duoc tren CI ubuntu (khong can Docker, khong can .env) vi chi goi
scripts/log_rotate.sh truc tiep.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROTATE_SH = REPO / "scripts" / "log_rotate.sh"

# Windows: PATH co the resolve `bash` sang WSL relay (execvpe(/bin/bash) that
# bai) — goi thang git-bash. Ubuntu CI: git-bash khong ton tai, dung `bash`.
_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
        env={**os.environ, "LOG_MAX_BYTES": "100", "LOG_KEEP": "3"},
    )


def test_file_vuot_nguong_duoc_xoay_noi_dung_khong_mat(tmp_path):
    """File > 100 byte (nguong test) -> xoay sang .1, noi dung cu con nguyen."""
    f = tmp_path / "heartbeat.log"
    old = "dong cu " * 50  # ~400 byte > 100
    f.write_text(old, encoding="utf-8")
    r = _bash(f'source "{ROTATE_SH}"; rotate_log "{f}"', tmp_path)
    assert r.returncode == 0
    assert not f.exists()  # file goc da xoay sang .1
    backup = tmp_path / "heartbeat.log.1"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == old


def test_file_duoi_nguong_khong_bi_dung(tmp_path):
    """File < ngưỡng -> khong tao ban .1, noi dung giu nguyen."""
    f = tmp_path / "heartbeat.log"
    f.write_text("nho hon ngưỡng", encoding="utf-8")
    r = _bash(f'source "{ROTATE_SH}"; rotate_log "{f}"', tmp_path)
    assert r.returncode == 0
    assert f.exists()
    assert f.read_text(encoding="utf-8") == "nho hon ngưỡng"
    assert not (tmp_path / "heartbeat.log.1").exists()


def test_xoay_that_bai_van_ghi_duoc_dong_moi(tmp_path):
    """QUAN TRONG NHAT: xoay hong thi dong log moi VAN phai vao file. Uu tien:
    mat ban xoay con hon mat dong log (brief phan 1, yeu cau 3).

    Gia lap xoay hong bang cach thay `mv` bang ham luon tra 1 (tuong duong
    file bi khoa / dia day tren Windows) — tat dinh tren moi OS, khong can
    chmod hay lock that."""
    f = tmp_path / "heartbeat.log"
    f.write_text("x" * 200, encoding="utf-8")  # vuot ngưỡng 100
    script = (
        'mv() { return 1; }  # gia lap: moi lan doi ten deu that bai\n'
        'set -e  # kich ban xau nhat: caller co set -e — xoay hong van khong\n'
        '        # duoc chan ghi (rotate_log phai nuot loi va tra 0)\n'
        f'source "{ROTATE_SH}"; '
        f'rotate_log "{f}"; '
        f'echo "dong log moi" >> "{f}"'
    )
    r = _bash(script, tmp_path)
    assert r.returncode == 0
    # file goc con nguyen (khong mat noi dung cu) VA nhan duoc dong moi
    content = f.read_text(encoding="utf-8")
    assert "x" * 200 in content
    assert "dong log moi" in content


def test_giu_vai_ban_roi_xoa_dan(tmp_path):
    """3 lan xoay lien tiep: chi giu LOG_KEEP=3 ban, ban cu nhat (.3) bi xoa,
    cac ban dich lui dung thu tu."""
    f = tmp_path / "h.log"
    for gen in range(4):  # 4 lan xoay
        f.write_text(f"noi dung the he {gen}\n" * 30, encoding="utf-8")
        r = _bash(f'source "{ROTATE_SH}"; rotate_log "{f}"', tmp_path)
        assert r.returncode == 0
        f.write_text("", encoding="utf-8")  # caller tao file moi rong
    # Sau 4 lan: chi .1 .2 .3 (moi nhat la the he 3), khong co .4
    assert (tmp_path / "h.log.1").read_text(encoding="utf-8").startswith("noi dung the he 3")
    assert (tmp_path / "h.log.2").read_text(encoding="utf-8").startswith("noi dung the he 2")
    assert (tmp_path / "h.log.3").read_text(encoding="utf-8").startswith("noi dung the he 1")
    assert not (tmp_path / "h.log.4").exists()
