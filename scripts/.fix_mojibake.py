"""Go mojibake nhieu lop: UTF-8 bi doc nham thanh cp1252 roi ghi lai UTF-8.

Lam theo TUNG DONG vi file tron ba muc do. Chi nhan ket qua khi vong bien doi
nguoc chay tron ven — dong tieng Viet sach chua ky tu ngoai cp1252/latin-1 nen
encode se that bai va dong do duoc giu nguyen.

Cp1252 co nam byte khong dinh nghia (0x81 0x8D 0x8F 0x90 0x9D). Van ban bi mangle
nhieu lop hay chua dung chung, nen phai nga sang latin-1 cho rieng nhung ky tu do,
neu khong ca dong se that bai ngay vong dau.
"""

import sys
from pathlib import Path

UNDEFINED_CP1252 = {"", "", "", "", ""}


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


def unmangle_once(s: str) -> str | None:
    raw = to_bytes(s)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def fix_line(s: str) -> str:
    cur = s
    for _ in range(5):
        nxt = unmangle_once(cur)
        if nxt is None or nxt == cur:
            break
        cur = nxt
    return cur


def main() -> None:
    path = Path(sys.argv[1])
    lines = path.read_text(encoding="utf-8").split("\n")
    fixed = [fix_line(ln) for ln in lines]
    changed = sum(1 for a, b in zip(lines, fixed) if a != b)
    residue = sum(1 for ln in fixed if "Ã" in ln or "Æ’" in ln)
    path.write_text("\n".join(fixed), encoding="utf-8", newline="\n")
    print(f"da sua {changed}/{len(lines)} dong | con nghi ngo: {residue}")


if __name__ == "__main__":
    main()
