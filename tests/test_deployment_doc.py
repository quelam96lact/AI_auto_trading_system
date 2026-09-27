"""Test chống lệch tài liệu triển khai DEPLOYMENT.md (Brief 110).

Đảm bảo:
1. Mọi job trong scripts/sched.sh đều có mặt trong khối crontab của DEPLOYMENT.md (và ngược lại).
2. DEPLOYMENT.md có cấu hình múi giờ Asia/Ho_Chi_Minh.
3. Mọi đường dẫn scripts/... được nhắc tới trong DEPLOYMENT.md đều tồn tại trong repo.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_MD = REPO_ROOT / "DEPLOYMENT.md"
SCHED_SH = REPO_ROOT / "scripts" / "sched.sh"


def extract_sched_jobs() -> set[str]:
    """Trích xuất các nhãn case job từ scripts/sched.sh (bỏ qua case *)"""
    text = SCHED_SH.read_text(encoding="utf-8")
    # Match pattern like: heartbeat) or orderbook-recorder)
    case_matches = re.findall(r"^\s*([a-zA-Z0-9_-]+)\)", text, re.MULTILINE)
    return set(case_matches)


def extract_crontab_jobs() -> set[str]:
    """Trích xuất các job được gọi qua sched.sh trong khối crontab của DEPLOYMENT.md"""
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    # Match lines calling sched.sh <job>
    # Formats:
    # ... /opt/trading/scripts/sched.sh <job>
    # ... cd /opt/trading && scripts/sched.sh <job>
    # ... cd /opt/trading && ./scripts/sched.sh <job>
    matches = re.findall(r"sched\.sh\s+([a-zA-Z0-9_-]+)", text)
    # Lọc bỏ placeholder hoặc từ khoá shell nếu có
    valid_jobs = {m for m in matches if not m.startswith("$")}
    return valid_jobs


def test_crontab_jobs_match_sched_sh():
    """Tập job trong scripts/sched.sh phải BẰNG tập job trong khối crontab của DEPLOYMENT.md."""
    sched_jobs = extract_sched_jobs()
    cron_jobs = extract_crontab_jobs()
    assert sched_jobs == cron_jobs, (
        f"Lệch job giữa sched.sh và DEPLOYMENT.md:\n"
        f"  Trong sched.sh nhưng thiếu trong DEPLOYMENT.md: {sched_jobs - cron_jobs}\n"
        f"  Trong DEPLOYMENT.md nhưng không có trong sched.sh: {cron_jobs - sched_jobs}"
    )


def test_deployment_md_contains_vietnam_timezone():
    """DEPLOYMENT.md phải có chuỗi 'Asia/Ho_Chi_Minh' để đảm bảo cấu hình múi giờ cho VPS."""
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    assert "Asia/Ho_Chi_Minh" in text, "DEPLOYMENT.md không nhắc tới múi giờ Asia/Ho_Chi_Minh!"


def test_referenced_scripts_exist():
    """Mọi đường dẫn scripts/... nhắc trong DEPLOYMENT.md phải tồn tại trong repo."""
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    # Tìm các đường dẫn file scripts/... (loại bỏ dấu ngoặc, dấu phẩy, v.v.)
    found_scripts = set(re.findall(r"(?:^|\s|/opt/trading/|[`'\"])scripts/([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+)", text))
    missing = []
    for s in found_scripts:
        script_path = REPO_ROOT / "scripts" / s
        if not script_path.exists():
            missing.append(f"scripts/{s}")
    assert not missing, f"Các script sau được nhắc trong DEPLOYMENT.md nhưng không tồn tại: {missing}"
