"""Kiểm thử chặn bẫy date(ts) / ts::date không quy về giờ VN (Brief 85 Task 2).

Mục tiêu:
Quét mọi file .py trong trading/ và scripts/, tìm các chuỗi SQL chứa date(ts),
date(x.ts) hoặc ts::date mà không quy về múi giờ VN (Asia/Ho_Chi_Minh), báo đỏ nếu vi phạm.
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

# Từ khoá nhận diện chuỗi SQL
SQL_KEYWORD_RE = re.compile(
    r"\b(SELECT|WHERE|GROUP\s+BY|FROM)\b",
    re.IGNORECASE,
)

# Mẫu nguy hiểm: date(ts), date(x.ts), ts::date, x.ts::date
# (Không khớp với (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date vì trước ::date là dấu ngoặc đóng ')')
DANGEROUS_DATE_RE = re.compile(
    r"(\bdate\s*\(\s*(?:[a-zA-Z0-9_]+\.)?ts\s*\)|\b(?:[a-zA-Z0-9_]+\.)?ts\s*::\s*date\b)",
    re.IGNORECASE,
)


def is_sql_string(s: str) -> bool:
    """Xác định một chuỗi có chứa từ khoá SQL hay không."""
    return bool(SQL_KEYWORD_RE.search(s))


def find_timezone_violations_in_string(s: str) -> list[str]:
    """Tìm tất cả các mẫu date(ts) / ts::date nguy hiểm trong chuỗi SQL."""
    if not is_sql_string(s):
        return []
    return [m.group(0) for m in DANGEROUS_DATE_RE.finditer(s)]


def scan_source_for_timezone_violations(
    source_code: str,
) -> tuple[int, list[tuple[int, str, str]]]:
    """Quét mã nguồn Python thông qua tokenizer để chỉ xét các token chuỗi SQL.

    Returns:
        (sql_strings_count, violations)
        mỗi vi phạm gồm: (line_no, matched_pattern, snippet)
    """
    sql_count = 0
    violations: list[tuple[int, str, str]] = []

    tokens = list(tokenize.tokenize(io.BytesIO(source_code.encode("utf-8")).readline))
    for tok in tokens:
        if tok.type == tokenize.STRING:
            try:
                val = ast.literal_eval(tok.string)
            except Exception:
                val = tok.string

            if isinstance(val, str) and is_sql_string(val):
                sql_count += 1
                matches = find_timezone_violations_in_string(val)
                for m in matches:
                    violations.append((tok.start[0], m, val.strip()[:100]))

    return sql_count, violations


def scan_file_for_timezone_violations(
    filepath: pathlib.Path,
) -> tuple[int, list[tuple[pathlib.Path, int, str, str]]]:
    """Quét một file Python cụ thể."""
    with open(filepath, "rb") as f:
        try:
            content = f.read().decode("utf-8")
        except UnicodeDecodeError:
            return 0, []

    sql_count, file_violations = scan_source_for_timezone_violations(content)
    violations = [
        (filepath, line_no, pattern, snippet)
        for line_no, pattern, snippet in file_violations
    ]
    return sql_count, violations


def scan_repo_for_timezone_violations(
    repo_root: pathlib.Path,
    target_dirs: tuple[str, ...] = ("trading", "scripts"),
) -> dict:
    """Quét toàn bộ repo trong các thư mục chỉ định."""
    files_scanned = 0
    sql_strings_checked = 0
    all_violations: list[tuple[pathlib.Path, int, str, str]] = []

    for d in target_dirs:
        dir_path = repo_root / d
        if not dir_path.exists():
            continue
        for p in dir_path.rglob("*.py"):
            files_scanned += 1
            sql_count, violations = scan_file_for_timezone_violations(p)
            sql_strings_checked += sql_count
            all_violations.extend(violations)

    return {
        "files_scanned": files_scanned,
        "sql_strings_checked": sql_strings_checked,
        "violations": all_violations,
    }


# ==============================================================================
# BỘ TEST CHẶN BẪY (Task 2)
# ==============================================================================


def test_sql_timezone_scanner_catches_dangerous_patterns():
    """Tiêu chí 1 - Bắt đúng: phát hiện date(ts), ts::date, date(b.ts) trong chuỗi SQL."""
    # 1. date(ts)
    v1 = find_timezone_violations_in_string("SELECT date(ts) FROM bars")
    assert len(v1) == 1
    assert "date(ts)" in v1[0]

    # 2. ts::date
    v2 = find_timezone_violations_in_string("SELECT ts::date FROM bars_daily")
    assert len(v2) == 1
    assert "ts::date" in v2[0]

    # 3. date(b.ts) trong mệnh đề WHERE
    v3 = find_timezone_violations_in_string("SELECT * FROM bars b WHERE date(b.ts) = %s")
    assert len(v3) == 1
    assert "date(b.ts)" in v3[0]

    # 4. b.ts::date
    v4 = find_timezone_violations_in_string("SELECT b.ts::date FROM bars b")
    assert len(v4) == 1
    assert "b.ts::date" in v4[0]

    # 5. Có khoảng trắng: date( x.ts )
    v5 = find_timezone_violations_in_string("SELECT date( x.ts ) FROM bars x")
    assert len(v5) == 1


def test_sql_timezone_scanner_no_false_positives():
    """Tiêu chí 2 - Không báo giả:

    - Quy về giờ VN hợp lệ: (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
    - Comment nhắc tới date(ts)
    - Docstring nhắc tới ts::date nhưng không phải chuỗi SQL
    """
    # 1. Truy vấn chuẩn giờ VN
    safe_sql = "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM bars_daily"
    assert find_timezone_violations_in_string(safe_sql) == []

    safe_sql_alias = "SELECT (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d FROM bars b"
    assert find_timezone_violations_in_string(safe_sql_alias) == []

    # 2. Comment không được báo đỏ
    code_with_comment = """
# KHONG dung date(ts) vi gay lech mui gio UTC
def do_something():
    return 42
"""
    sql_cnt, violations = scan_source_for_timezone_violations(code_with_comment)
    assert sql_cnt == 0
    assert len(violations) == 0

    # 3. Docstring nhắc ts::date nhưng không có từ khoá SQL
    docstring_sample = '''
def read_pnl():
    """SUM(pnl) từ real_order_fills cho 1 ngày theo giờ Việt Nam.

    Dùng ts AT TIME ZONE 'Asia/Ho_Chi_Minh' thay vì ts::date — cast trực tiếp
    phụ thuộc timezone của session/server Postgres.
    """
    return 0.0
'''
    sql_cnt, violations = scan_source_for_timezone_violations(docstring_sample)
    assert sql_cnt == 0
    assert len(violations) == 0


def test_repo_has_zero_timezone_violations_with_adequate_denominator(capsys):
    """Tiêu chí 2 & 3 - Quét toàn repo trading/ và scripts/:

    - Mẫu số phải đủ lớn: số file quét >= 150, số chuỗi SQL kiểm tra >= 200.
    - Vi phạm thực tế trên repo hiện tại phải bằng 0.
    """
    repo_root = pathlib.Path(__file__).parent.parent
    res = scan_repo_for_timezone_violations(repo_root, target_dirs=("trading", "scripts"))

    # In kết quả mẫu số ra stdout theo yêu cầu Brief 85 (ASCII-safe cho Windows console)
    print(
        f"\n[Task 2 Audit] Files scanned: {res['files_scanned']} | "
        f"SQL strings checked: {res['sql_strings_checked']} | "
        f"Violations: {len(res['violations'])}"
    )

    # Tiêu chí 3: Mẫu số không được bằng 0 hoặc nhỏ bất thường
    assert res["files_scanned"] >= 150, (
        f"Bộ quét bị mù file: chỉ quét được {res['files_scanned']} files (< 150)"
    )
    assert res["sql_strings_checked"] >= 200, (
        f"Bộ quét bị mù SQL: chỉ kiểm tra được {res['sql_strings_checked']} chuỗi SQL (< 200)"
    )

    # Tiêu chí 2: 0 vi phạm trên codebase hiện tại
    if res["violations"]:
        details = "\n".join(
            f"  - {f}:{line} [{pattern}]: {snip}"
            for f, line, pattern, snip in res["violations"]
        )
        assert False, f"Phát hiện {len(res['violations'])} vi phạm bẫy múi giờ:\n{details}"

    assert len(res["violations"]) == 0
