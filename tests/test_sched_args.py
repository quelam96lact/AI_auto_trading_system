"""Tests ghim tham số cho scripts/sched.sh và các script được gọi (Brief 140).

Nguyên tắc:
1. Mọi nhánh trong sched.sh có exec "$RUN" đều phải chuyển "$@".
2. Mọi script Python được sched.sh gọi đều phải có hàm build_parser()
   và từ chối cờ lạ (ném SystemExit với mã != 0 trước khi làm bất cứ việc gì).
3. Danh sách script lấy động từ chính sched.sh, không viết cứng.
"""

from __future__ import annotations

import argparse
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHED_SH = REPO_ROOT / "scripts" / "sched.sh"


def parse_sched_branches(sched_path: Path = SCHED_SH) -> dict[str, str]:
    """Phân tích các nhánh case trong scripts/sched.sh thành {tên_nhánh: nội_dung}."""
    text = sched_path.read_text(encoding="utf-8")
    m = re.search(r"case\s+.*?\s+in\s*(.*?)\s*esac", text, re.DOTALL)
    if not m:
        raise ValueError(f"Không tìm thấy khối case..esac trong {sched_path}")

    case_body = m.group(1)
    chunks = [c.strip() for c in case_body.split(";;") if c.strip()]
    branches: dict[str, str] = {}
    for chunk in chunks:
        bm = re.match(r"([a-zA-Z0-9_-]+)\s*\)\s*(.*)", chunk, re.DOTALL)
        if bm:
            branches[bm.group(1)] = bm.group(2).strip()
    return branches


def extract_python_modules(sched_path: Path = SCHED_SH) -> list[str]:
    """Trích xuất tất cả các module/script Python được gọi bởi sched.sh.

    Hỗ trợ cả cú pháp `python scripts/foo.py` và `python -m scripts.foo`.
    Trả về danh sách tên module chuẩn (ví dụ: 'scripts.heartbeat_check').
    """
    text = sched_path.read_text(encoding="utf-8")
    modules = set()

    # Pattern 1: python scripts/<name>.py
    for match in re.finditer(r"python\s+scripts/([a-zA-Z0-9_]+)\.py", text):
        modules.add(f"scripts.{match.group(1)}")

    # Pattern 2: python -m scripts.<name>
    for match in re.finditer(r"python\s+-m\s+scripts\.([a-zA-Z0-9_]+)", text):
        modules.add(f"scripts.{match.group(1)}")

    return sorted(modules)


def test_every_exec_run_branch_forwards_args():
    """Mọi nhánh trong sched.sh có exec \"$RUN\" bắt buộc phải chuyển \"$@\".

    Phá thử: nếu gỡ \"$@\" khỏi bất kỳ nhánh nào, test này sẽ đỏ và chỉ đích danh tên nhánh.
    """
    branches = parse_sched_branches(SCHED_SH)
    assert len(branches) >= 16, f"sched.sh phải có ít nhất 16 nhánh, tìm thấy: {len(branches)}"

    missing_at_branches: list[str] = []
    missing_exec_branches: list[str] = []

    for name, code in branches.items():
        if 'exec "$RUN"' in code:
            if '"$@"' not in code:
                missing_at_branches.append(name)
        else:
            missing_exec_branches.append(name)

    assert not missing_exec_branches, (
        f"Các nhánh sau trong sched.sh thiếu exec \"$RUN\": {missing_exec_branches}"
    )
    assert not missing_at_branches, (
        f"Các nhánh sau trong sched.sh có exec \"$RUN\" nhưng THIẾU \"$@\": {missing_at_branches}"
    )


@pytest.mark.parametrize("mod_name", extract_python_modules(SCHED_SH))
def test_python_script_has_build_parser_and_rejects_unknown_flag(mod_name: str):
    """Mọi script Python được sched.sh gọi phải có build_parser() và từ chối cờ lạ với SystemExit != 0.

    Danh sách script lấy động từ chính sched.sh để nhánh thêm về sau tự được kiểm.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        pytest.fail(f"Không thể import module {mod_name}: {e}")

    # 1. Phải có hàm build_parser()
    assert hasattr(mod, "build_parser"), f"Module {mod_name} thiếu hàm build_parser()"
    build_parser_fn = mod.build_parser
    assert callable(build_parser_fn), f"{mod_name}.build_parser không phải là callable"

    # 2. build_parser() phải trả về ArgumentParser
    parser = build_parser_fn()
    assert isinstance(parser, argparse.ArgumentParser), (
        f"{mod_name}.build_parser() trả về {type(parser)}, không phải argparse.ArgumentParser"
    )

    # 3. Không được dùng parse_known_args trong mã nguồn
    mod_file = Path(getattr(mod, "__file__", ""))
    if mod_file.is_file():
        source_code = mod_file.read_text(encoding="utf-8")
        assert "parse_known_args" not in source_code, (
            f"Module {mod_name} chứa parse_known_args — vi phạm nguyên tắc từ chối cờ lạ!"
        )

    # 4. Gọi với cờ lạ phải ném SystemExit với mã khác 0
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--khong-ton-tai"])
    assert exc_info.value.code != 0, f"{mod_name} không ném SystemExit mã != 0 khi gặp cờ lạ"


def test_daily_data_check_has_dry_run_flag():
    """daily_data_check.py phải có cờ --dry-run để phục vụ chạy bù an toàn (Việc 3)."""
    from scripts.daily_data_check import build_parser

    parser = build_parser()
    args = parser.parse_args(["--dry-run", "--date", "2026-10-01"])
    assert args.dry_run is True
    assert args.date == "2026-10-01"


_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"


def _posix_path(p: Path) -> str:
    s = p.as_posix()
    if len(s) >= 2 and s[1] == ":":
        return f"/{s[0].lower()}{s[2:]}"
    return s


def test_shell_scripts_reject_unknown_flags():
    """Kiểm tra 2 script shell backup_db.sh và backup_orderbook.sh từ chối cờ lạ và thoát mã 2."""
    for sh_script in ("scripts/backup_db.sh", "scripts/backup_orderbook.sh"):
        script_path = REPO_ROOT / sh_script
        assert script_path.exists(), f"Không tìm thấy {sh_script}"
        # Chạy bash với --khong-ton-tai
        res = subprocess.run(
            [BASH, _posix_path(script_path), "--khong-ton-tai"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 2, (
            f"{sh_script} không thoát mã 2 khi nhận cờ lạ. Mã: {res.returncode}, stderr: {res.stderr}"
        )
        assert "ERROR:" in res.stderr or "Usage:" in res.stderr
