"""Nap token da xac thuc (scripts/.ssi_sdk_token.json, ghi boi
spike_ssi_sdk_auth.py) vao bang ssi_auth_state trong Postgres.

Chay: uv run python scripts/load_token_to_db.py

Can: da chay scripts/spike_ssi_sdk_auth.py truoc (co file token cuc bo);
Postgres dang chay (docker compose up -d postgres); bien env DB_DSN tro dung.

Collector (trading/collector/ssi_auth.py::ensure_authenticated) doc
refresh_token tu DB, KHONG doc scripts/.ssi_sdk_token.json — script nay la
cau noi duy nhat giua 2 noi luu token (Phase 4, xem PLAN_PHASE4_E2E.md).
"""

import json
from pathlib import Path
from urllib.parse import urlparse

from _db_common import resolve_dsn

from trading.storage.db import Storage

TOKEN_FILE = Path(__file__).parent / ".ssi_sdk_token.json"


def main() -> None:
    dsn = resolve_dsn()

    if not TOKEN_FILE.exists():
        print(
            f"Chua co token da luu o {TOKEN_FILE} — "
            "chay scripts/spike_ssi_sdk_auth.py truoc."
        )
        raise SystemExit(1)

    saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    storage = Storage(dsn)
    storage.init_schema()
    storage.save_ssi_token(
        access_token=saved["accessToken"],
        expires_at=saved["expiresAt"],
        refresh_token=saved["refreshToken"],
        refresh_token_expires_at=saved["refreshExpiresAt"],
    )
    # Khong in DSN: no chua mat khau Postgres (ro ri mat khau ra console).
    parts = urlparse(dsn)
    print(f"Da nap token vao ssi_auth_state (host={parts.hostname}, db={parts.path.lstrip('/')}).")
    print(f"refresh_token_expires_at: {saved['refreshExpiresAt']}")


if __name__ == "__main__":
    main()
