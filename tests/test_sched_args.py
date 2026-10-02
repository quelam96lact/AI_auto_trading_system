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


# ---------------------------------------------------------------------------
# Brief 141: `main` phai THUC SU goi parser. Test o tren chi chung minh PARSER tu choi co la
# (build_parser().parse_args(["--khong-ton-tai"])), khong chung minh `main` goi parser:
# o heartbeat_check.py va deploy_drift_check.py `main` chi parse khi `argv is not None`, nen
# `main()` nuot im lang moi co. Phan tich AST (khong import, khong chay) de ghim dieu do;
# TUYET DOI khong goi main(["--khong-ton-tai"]) — go parser di thi test do se chay job that.
# ---------------------------------------------------------------------------
import ast

# Danh sach trang: {module: so cau lenh duoc phep dung TRUOC cau parse}. Hien khong script nao can:
# moi script goi parser NGAY cau dau tien cua `main`. Them vao day phai kem ly do trong bao cao.
STATEMENTS_ALLOWED_BEFORE_PARSE: dict[str, int] = {}


def _module_path(mod_name: str) -> Path:
    return REPO_ROOT / (mod_name.replace(".", "/") + ".py")


def _top_level_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None
    )


def _body_without_docstring(fn: ast.FunctionDef) -> list[ast.stmt]:
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _is_unconditional_parse_statement(stmt: ast.stmt) -> bool:
    """`args = build_parser().parse_args(argv)` hoac `build_parser().parse_args(argv)` — nhu mot cau
    lenh don o cap than ham (If/Try/With... khong phai Assign/Expr nen bi loai)."""
    if not isinstance(stmt, (ast.Assign, ast.Expr)):
        return False
    call = stmt.value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
        return False
    if call.func.attr != "parse_args":
        return False
    builder = call.func.value
    if not (
        isinstance(builder, ast.Call)
        and isinstance(builder.func, ast.Name)
        and builder.func.id == "build_parser"
    ):
        return False
    # Phai chuyen tiep `argv` cua main (khong parse mot danh sach khac).
    return len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id == "argv"


@pytest.mark.parametrize("mod_name", extract_python_modules(SCHED_SH))
def test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau(mod_name: str):
    """Cau lenh dau tien co hieu luc cua `main` (bo docstring) la parse_args(argv) cua build_parser(),
    khong nam trong if/try. Phan tich AST, khong import, khong chay."""
    path = _module_path(mod_name)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    main_fn = _top_level_function(tree, "main")
    assert main_fn is not None, f"{mod_name} khong co ham main() o cap module"
    assert [a.arg for a in main_fn.args.args] == ["argv"], (
        f"{mod_name}.main phai nhan dung mot tham so `argv`"
    )

    body = _body_without_docstring(main_fn)
    skip = STATEMENTS_ALLOWED_BEFORE_PARSE.get(mod_name, 0)
    assert len(body) > skip, f"{mod_name}.main rong"
    first = body[skip]
    assert _is_unconditional_parse_statement(first), (
        f"{mod_name}.main: cau lenh dau tien co hieu luc phai la "
        f"`args = build_parser().parse_args(argv)` vo dieu kien, nhung la: "
        f"{ast.unparse(first).splitlines()[0][:100]!r}"
    )


@pytest.mark.parametrize("mod_name", extract_python_modules(SCHED_SH))
def test_khoi_main_goi_ham_main(mod_name: str):
    """Khoi `if __name__ == "__main__":` thuc su goi main (khong thoat som bang cach khac)."""
    tree = ast.parse(_module_path(mod_name).read_text(encoding="utf-8"))
    blocks = [
        n
        for n in tree.body
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "__name__"
    ]
    assert blocks, f"{mod_name} thieu khoi if __name__ == '__main__'"
    calls_main = any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "main"
        for block in blocks
        for c in ast.walk(block)
    )
    assert calls_main, f"{mod_name}: khoi __main__ khong goi main()"


def test_cong_cu_ast_phan_biet_dung_sai():
    """Tu kiem cong cu phat hien: mau dung phai qua, mau sai (nhu hai script o brief 141) phai bi bat."""
    ok = ast.parse("def main(argv=None):\n    args = build_parser().parse_args(argv)\n")
    bare = ast.parse("def main(argv=None):\n    build_parser().parse_args(argv)\n")
    guarded = ast.parse(
        "def main(argv=None):\n    if argv is not None:\n        build_parser().parse_args(argv)\n"
    )
    wrapped = ast.parse(
        "def main(argv=None):\n    if argv:\n        args = build_parser().parse_args(argv)\n"
    )
    two_step = ast.parse(
        "def main(argv=None):\n    parser = build_parser()\n    args = parser.parse_args(argv)\n"
    )
    other_list = ast.parse("def main(argv=None):\n    args = build_parser().parse_args([])\n")
    in_try = ast.parse(
        "def main(argv=None):\n    try:\n        args = build_parser().parse_args(argv)\n    except Exception:\n        pass\n"
    )

    def first(tree):
        return _body_without_docstring(_top_level_function(tree, "main"))[0]

    assert _is_unconditional_parse_statement(first(ok))
    assert _is_unconditional_parse_statement(first(bare))
    for bad in (guarded, wrapped, two_step, other_list, in_try):
        assert not _is_unconditional_parse_statement(first(bad))
