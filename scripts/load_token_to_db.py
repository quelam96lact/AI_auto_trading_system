"""Nạp token đã xác thực (scripts/.ssi_sdk_token.json, ghi bởi
spike_ssi_sdk_auth.py) vào bảng ssi_auth_state trong Postgres.

Chạy: uv run python scripts/load_token_to_db.py --config config/config.yaml

Cần: đã chạy scripts/spike_ssi_sdk_auth.py trước (có file token cục bộ);
Postgres đang chạy (docker compose up -d postgres) và cfg.db_dsn trỏ đúng.

Collector (trading/collector/ssi_auth.py::ensure_authenticated) đọc
refresh_token từ DB, KHÔNG đọc scripts/.ssi_sdk_token.json — script này là
cầu nối duy nhất giữa 2 nơi lưu token (Phase 4, xem PLAN_PHASE4_E2E.md).
"""

import argparse
import json
from pathlib import Path

from trading.config import load_config
from trading.storage.db import Storage

TOKEN_FILE = Path(__file__).parent / ".ssi_sdk_token.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    if not TOKEN_FILE.exists():
        print(
            f"Chưa có token đã lưu ở {TOKEN_FILE} — chạy scripts/spike_ssi_sdk_auth.py trước."
        )
        raise SystemExit(1)

    saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    storage.save_ssi_token(
        access_token=saved["accessToken"],
        expires_at=saved["expiresAt"],
        refresh_token=saved["refreshToken"],
        refresh_token_expires_at=saved["refreshExpiresAt"],
    )
    print(f"Đã nạp token vào ssi_auth_state (DB: {cfg.db_dsn}).")
    print(f"refresh_token_expires_at: {saved['refreshExpiresAt']}")


if __name__ == "__main__":
    main()
