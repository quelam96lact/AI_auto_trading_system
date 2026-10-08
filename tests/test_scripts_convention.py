"""Thi hành quy ước `scripts/` (Brief đợt 159), theo khuôn đợt 142.

Mỗi script `.py` không dấu chấm trong `scripts/` (bỏ qua `_*.py`) phải thuộc ít nhất một nhóm:
  1. được `scripts/sched.sh` gọi;
  2. được `tests/**/*.py` nhắc tên (nhập hoặc gọi);
  3. có một dòng khai báo trong bảng mục 4 của `scripts/README.md`.

Không thuộc nhóm nào thì test đỏ và nêu đúng tên file. Test cũng bắt khai báo lỗi thời:
một dòng khai báo cho script đã thuộc nhóm 1 hoặc 2, hoặc cho file không còn tồn tại.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
THIS_FILE = Path(__file__).resolve()
README = SCRIPTS / "README.md"
STATUSES = {"CÒN CẦN", "ĐÃ GHI SỐ ĐO", "KHÔNG RÕ"}
EVIDENCE_RE = re.compile(r"`([^`\s]+\.(?:md|py|sh|json)):(\d+)`")


def _word(name: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")


def _convention_scripts() -> list[str]:
    return sorted(
        p.stem
        for p in SCRIPTS.glob("*.py")
        if not p.name.startswith((".", "_"))
    )


def _sched_text() -> str:
    return (SCRIPTS / "sched.sh").read_text(encoding="utf-8", errors="replace")


@functools.lru_cache(maxsize=1)
def _tests_combined_text() -> str:
    out = []
    for p in (REPO / "tests").rglob("*.py"):
        if p.resolve() == THIS_FILE:
            continue
        out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n\x00\n".join(out)


def _declared_rows() -> dict[str, tuple[str, str]]:
    """Bảng mục 4: tên script -> (trạng thái, ô bằng chứng)."""
    text = README.read_text(encoding="utf-8")
    marker = "## 4. Khai báo script"
    assert marker in text, "scripts/README.md thiếu mục 4 (khai báo script)"
    section = text.split(marker, 1)[1]
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|(.*)$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        # cells: vai trò | trạng thái | bằng chứng | (rỗng cuối)
        assert len(cells) >= 3, f"dòng khai báo hỏng: {line[:80]}"
        name = m.group(1)
        assert name not in rows, f"script khai báo hai lần: {name}"
        rows[name] = (cells[1], cells[2])
    return rows


@functools.lru_cache(maxsize=1)
def _groups() -> tuple[set[str], set[str], set[str]]:
    sched = _sched_text()
    combined_tests = _tests_combined_text()
    test_words = set(re.findall(r"[A-Za-z0-9_]+", combined_tests))
    sched_words = set(re.findall(r"[A-Za-z0-9_]+", sched))
    names = _convention_scripts()
    in_sched = {n for n in names if n in sched_words}
    in_tests = {n for n in names if n in test_words}
    declared = set(_declared_rows())
    return in_sched, in_tests, declared


def test_moi_script_khong_dau_cham_thuoc_mot_trong_ba_nhom():
    in_sched, in_tests, declared = _groups()
    orphans = [
        n for n in _convention_scripts() if n not in in_sched | in_tests | declared
    ]
    assert not orphans, (
        "Script không dấu chấm không thuộc nhóm nào (không do sched.sh gọi, không do "
        "tests/ nhắc, không có dòng khai báo ở mục 4 của scripts/README.md): "
        + ", ".join(f"{n}.py" for n in orphans)
    )


def test_khai_bao_khong_lo_thoi_va_khong_tro_vao_file_khong_ton_tai():
    in_sched, in_tests, declared = _groups()
    names = set(_convention_scripts())
    missing_file = sorted(declared - names)
    assert not missing_file, (
        "Khai báo cho script không còn tồn tại: " + ", ".join(missing_file)
    )
    stale = sorted(declared & (in_sched | in_tests))
    assert not stale, (
        "Script đã được sched.sh hoặc tests/ dùng nhưng vẫn còn dòng khai báo (xoá dòng): "
        + ", ".join(stale)
    )


def test_dong_khai_bao_co_trang_thai_hop_le_va_bang_chung_that():
    rows = _declared_rows()
    problems: list[str] = []
    for name, (status, evidence) in rows.items():
        if status not in STATUSES:
            problems.append(f"{name}: trạng thái không hợp lệ {status!r}")
            continue
        cited = EVIDENCE_RE.findall(evidence)
        if status != "KHÔNG RÕ" and not cited:
            problems.append(f"{name}: trạng thái {status} mà không có bằng chứng path:dòng")
        for rel, _ln in cited:
            p = REPO / rel
            if not p.is_file():
                problems.append(f"{name}: bằng chứng trỏ vào file không tồn tại: {rel}")
            elif not _word(name).search(p.read_text(encoding="utf-8", errors="replace")):
                problems.append(f"{name}: file bằng chứng {rel} không còn chứa tên script")
    assert not problems, "\n".join(problems)
