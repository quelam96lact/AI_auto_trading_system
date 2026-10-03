"""Nạp .env và giải DSN — dùng chung cho các script nghiên cứu trong scripts/.

Tách 2026-08-15: hai hàm này từng bị copy vào 6 script khác nhau, và đã bắt đầu
LỆCH NHAU (một nhóm nhận `--dsn` override, nhóm kia không; thông báo lỗi khác
nhau). Gộp về một bản, giữ hành vi rộng hơn (`override` có mặc định None nên
người gọi không có `--dsn` vẫn dùng được y như cũ).

Import theo đúng lối `_ssi_spike_common` đang dùng: script chạy bằng
`uv run python scripts/x.py` nên thư mục scripts/ nằm ở sys.path[0].

    from _db_common import resolve_dsn
"""

import os
from pathlib import Path

# Dot 158: thu muc logs o goc repo, tinh tu vi tri file (KHONG tu cwd - job cron chay voi
# cwd do sched.sh dat). Nguon duy nhat; cac script gan lai thanh DEFAULT_LOGS_DIR.
REPO_LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)


def load_dotenv() -> None:
    """uv run KHÔNG nạp .env — script tự đọc, không nhúng secret vào file."""
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def resolve_dsn(override: str | None = None) -> str:
    """DSN Postgres, ưu tiên `override` (cờ --dsn) rồi tới DB_DSN trong môi trường/.env."""
    if override:
        return override
    load_dotenv()
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise SystemExit("DB_DSN chưa set — cần .env hoặc --dsn")
    # Windows máy này: DSN dùng localhost bị IPv6 làm mỗi kết nối chậm ~130s.
    return dsn.replace("localhost", "127.0.0.1")
