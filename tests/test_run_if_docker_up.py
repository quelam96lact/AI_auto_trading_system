"""Tests cho scripts/run_if_docker_up.sh (Brief đợt 127 Phần A).

Kiểm thử tự động cho 3 nhánh của cổng giám sát:
A1. Thiếu .env -> thoát 2, stderr và log có SKIP, không chạy lệnh.
A2. .env có CRLF -> thoát 2, stderr và log có lỗi CRLF, không chạy lệnh.
A3. Đường thông (.env LF + Docker gate UP) -> thoát 0, chạy lệnh, log ghi EXIT=0.
A4. logs/ chưa có, không phải root -> tự tạo logs/, KHÔNG gọi chown.

Ghi chú:
- Chép scripts/run_if_docker_up.sh và scripts/log_rotate.sh sang tmp_path để chạy,
  tránh ghi log thật hay nạp .env thật của repo.
- Stub docker và chown có file đánh dấu riêng để chứng minh stub được gọi,
  tránh xanh nhờ may hoặc rơi vào docker thật.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Windows: PATH co the resolve `bash` sang WSL relay (execvpe(/bin/bash) that
# bai) — goi thang git-bash. Ubuntu CI: git-bash khong ton tai, dung `bash`.
_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"


def _setup_repo(tmp_path: Path) -> Path:
    """Tạo cây thư mục giả lập repo trong tmp_path."""
    repo = tmp_path / "trading"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO_ROOT / "scripts" / "run_if_docker_up.sh", scripts / "run_if_docker_up.sh"
    )
    shutil.copy2(REPO_ROOT / "scripts" / "log_rotate.sh", scripts / "log_rotate.sh")
    (scripts / "run_if_docker_up.sh").chmod(0o755)
    (scripts / "log_rotate.sh").chmod(0o755)
    return repo


def _to_posix(path: Path) -> str:
    """Chuyển Path sang định dạng POSIX hợp lệ cho bash (vd: C:\\foo -> /c/foo)."""
    p = str(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return f"/{p[0].lower()}{p[2:]}"
    return p


def _run(
    repo: Path,
    args: list[str],
    env_extra: dict[str, str] | None = None,
    bin_dir: Path | None = None,
) -> subprocess.CompletedProcess:
    """Chạy run_if_docker_up.sh thông qua BASH."""
    script = repo / "scripts" / "run_if_docker_up.sh"
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)

    # Đảm bảo bin_dir đứng đầu PATH trong bash (kể cả trên Windows Git Bash)
    if bin_dir:
        posix_bin = _to_posix(bin_dir)
        posix_script = _to_posix(script)
        cmd = [
            BASH,
            "-c",
            'export PATH="$1:$PATH"; shift; exec "$@"',
            "--",
            posix_bin,
            posix_script,
        ] + args
    else:
        cmd = [BASH, str(script)] + args

    return subprocess.run(
        cmd,
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_a1_missing_env_exits_2(tmp_path):
    """A1 thiếu .env: thoát 2; stderr và file log có SKIP; file đánh dấu không tồn tại."""
    repo = _setup_repo(tmp_path)
    marker = repo / "marker.txt"

    res = _run(repo, ["a1.log", "A1_TEST", "touch", "marker.txt"])

    assert (
        res.returncode == 2
    ), f"Expected rc 2, got {res.returncode}. Stderr: {res.stderr}"
    assert "SKIP: khong tim thay .env" in res.stderr
    log_file = repo / "logs" / "a1.log"
    assert log_file.exists()
    assert "SKIP: khong tim thay .env" in log_file.read_text(encoding="utf-8")
    assert not marker.exists(), "Command should not have executed"


def test_a2_crlf_env_exits_2(tmp_path):
    """A2 .env CRLF: thoát 2; stderr và log có CRLF; file đánh dấu không tồn tại."""
    repo = _setup_repo(tmp_path)
    marker = repo / "marker.txt"
    (repo / ".env").write_bytes(b"FOO=bar\r\nBAZ=qux\r\n")

    # KHONG thay grep bang ban gia: grep cua Git Bash nuot \r o text-mode, va chinh
    # script phai tu xu ly (grep -U). Test chay grep THAT de bat dung loi do tren Windows.
    res = _run(repo, ["a2.log", "A2_TEST", "touch", "marker.txt"])

    assert (
        res.returncode == 2
    ), f"Expected rc 2, got {res.returncode}. Stderr: {res.stderr}"
    assert "CRLF" in res.stderr
    log_file = repo / "logs" / "a2.log"
    assert log_file.exists()
    assert "CRLF" in log_file.read_text(encoding="utf-8")
    assert not marker.exists(), "Command should not have executed"


def test_a3_normal_pass_through(tmp_path):
    """A3 đường thông: .env LF, docker stub ở đầu PATH in ID, thoát 0, marker có, log có EXIT=0."""
    repo = _setup_repo(tmp_path)
    marker = repo / "marker.txt"
    # write_bytes, KHONG write_text: tren Windows write_text doi \n thanh \r\n, tuc la
    # .env CRLF — truoc day test van xanh chi vi grep cua Git Bash mu voi \r.
    (repo / ".env").write_bytes(
        b"FOO=bar\nDB_DSN=postgres://trading:pwd@127.0.0.1:5432/trading\n"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_marker = tmp_path / "docker_called.txt"

    # docker stub: ghi dau vet va in ra mot id container gia
    docker_script = (
        f"#!/bin/sh\n"
        f'echo docker_called >> "{docker_marker.as_posix()}"\n'
        f'echo "fake-container-id-123"\n'
    )
    docker_stub = bin_dir / "docker"
    docker_stub.write_bytes(docker_script.encode("utf-8"))
    docker_stub.chmod(0o755)

    res = _run(
        repo,
        ["a3.log", "A3_TEST", "touch", "marker.txt"],
        env_extra={"DOCKER_GATE_CONTAINER": "x"},
        bin_dir=bin_dir,
    )

    # Chứng minh stub đã được gọi (không lọt vào docker thật)
    assert (
        docker_marker.exists()
    ), f"Docker stub was not called! PATH translation may have failed. Stderr: {res.stderr}"
    assert (
        res.returncode == 0
    ), f"Expected rc 0, got {res.returncode}. Stderr: {res.stderr}"
    assert marker.exists(), "Target command should have executed and created marker"
    log_file = repo / "logs" / "a3.log"
    assert log_file.exists()
    assert "EXIT=0" in log_file.read_text(encoding="utf-8")


def test_a4_logs_created_not_root(tmp_path):
    """A4 logs/ vắng, không root: logs/ được tạo, chown không bị gọi."""
    repo = _setup_repo(tmp_path)
    # write_bytes, KHONG write_text: tren Windows write_text doi \n thanh \r\n, tuc la
    # .env CRLF — truoc day test van xanh chi vi grep cua Git Bash mu voi \r.
    (repo / ".env").write_bytes(
        b"FOO=bar\nDB_DSN=postgres://trading:pwd@127.0.0.1:5432/trading\n"
    )

    logs_dir = repo / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_marker = tmp_path / "docker_called.txt"
    chown_marker = tmp_path / "chown_called.txt"

    # docker stub
    docker_script = (
        f"#!/bin/sh\n"
        f'echo docker_called >> "{docker_marker.as_posix()}"\n'
        f'echo "fake-container-id-123"\n'
    )
    docker_stub = bin_dir / "docker"
    docker_stub.write_bytes(docker_script.encode("utf-8"))
    docker_stub.chmod(0o755)

    # chown stub: ghi dau vet neu bi goi
    chown_script = f"#!/bin/sh\n" f'echo chown_called >> "{chown_marker.as_posix()}"\n'
    chown_stub = bin_dir / "chown"
    chown_stub.write_bytes(chown_script.encode("utf-8"))
    chown_stub.chmod(0o755)

    res = _run(
        repo,
        ["a4.log", "A4_TEST", "touch", "marker.txt"],
        env_extra={"DOCKER_GATE_CONTAINER": "x"},
        bin_dir=bin_dir,
    )

    assert docker_marker.exists(), "Docker stub was not called"
    assert (
        res.returncode == 0
    ), f"Expected rc 0, got {res.returncode}. Stderr: {res.stderr}"
    assert logs_dir.exists(), "logs/ directory should have been created"
    assert not chown_marker.exists(), "chown should NOT be called when not root"
