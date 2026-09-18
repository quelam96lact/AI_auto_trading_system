"""Quet toan bo file van ban trong repo tim dau vet mojibake.

Dau hieu: mot dong ma encode('cp1252')/latin-1 roi decode('utf-8') chay TRON VEN
va cho ket qua KHAC di — nghia la dong do von la UTF-8 bi doc nham mot lan nua.
Dong tieng Viet sach chua ky tu ngoai cp1252 nen encode that bai, khong bao gio
bi bao nham.
"""

import sys
from pathlib import Path

UNDEFINED_CP1252 = {"", "", "", "", ""}
EXTS = {".md", ".py", ".yaml", ".yml", ".sh", ".txt", ".sql", ".json"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def to_bytes(s: str) -> bytes | None:
    out = bytearray()
    for ch in s:
        if ch in UNDEFINED_CP1252:
            out.extend(ch.encode("latin-1"))
            continue
        try:
            out.extend(ch.encode("cp1252"))
        except UnicodeEncodeError:
            return None
    return bytes(out)


def is_mangled(line: str) -> bool:
    raw = to_bytes(line)
    if raw is None:
        return False
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    # Chi ke la hong khi that su doi VA co ky tu dau hieu; tranh bao nham
    # nhung dong ASCII thuan (encode/decode tron ven nhung khong doi gi).
    return decoded != line and any(c in line for c in "ÃÂÆ’â€")


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    hits: list[tuple[Path, int, int]] = []
    scanned = 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8").split("\n")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        bad = sum(1 for ln in lines if is_mangled(ln))
        if bad:
            hits.append((p, bad, len(lines)))

    print(f"da quet {scanned} file")
    if not hits:
        print("KHONG tim thay dau vet mojibake nao")
        return
    for p, bad, total in sorted(hits, key=lambda h: -h[1]):
        print(f"  {bad:4d}/{total:<5d} dong  {p.as_posix()}")


if __name__ == "__main__":
    main()
