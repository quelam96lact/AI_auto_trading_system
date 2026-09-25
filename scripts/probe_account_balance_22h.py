"""Script thăm dò phản hồi account balance SSI trong khung 22h (Brief 88 Task 1).

Chức năng:
1. Xác thực bằng trading.collector.ssi_auth.ensure_authenticated(cfg, storage)
   (dùng chung token trong bảng ssi_auth_state của DB - đồng nhất với collector).
2. Gọi endpoint EP_ACCOUNT_BALANCE với clientId + accountNo = '0434221' mỗi 60 giây.
3. Ghi nguyên văn JSON thô mỗi lần gọi ra data/probe/account_balance_<YYYY-MM-DD>.jsonl kèm recv_ts.
4. In ra màn hình: giờ VN, danh sách khoá có trong equity, và giá trị thô (chưa float())
   của withdrawable, totalDebt, accountBalance.
5. Tự động dừng lúc 23:00 giờ VN hoặc khi nhận Ctrl+C.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import pathlib
import sys
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

# Force UTF-8 stdout/stderr on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Ensure repo root is in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ssi_sdk.constant import EP_ACCOUNT_BALANCE

from trading.calendar_vn import TZ
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import load_config
from trading.storage.db import Storage

TARGET_ACCOUNT = "0434221"
DEFAULT_STOP_TIME = dt_time(23, 0, 0)


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def probe_account_balance(
    account_no: str = TARGET_ACCOUNT,
    stop_time: dt_time = DEFAULT_STOP_TIME,
    interval_seconds: float = 60.0,
    config_path: str = "config/config.yaml",
    data_dir: Path | str = "data/probe",
) -> None:
    _load_dotenv()
    cfg = load_config(config_path)
    db_dsn = cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
    storage = Storage(db_dsn)

    now_vn = datetime.now(TZ)
    date_str = now_vn.strftime("%Y-%m-%d")
    out_dir = Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"account_balance_{date_str}.jsonl"

    print("=" * 70)
    print("=== PROBE ACCOUNT BALANCE SSI (BRIEF 88 TASK 1) ===")
    print(f"- Tài khoản: {account_no}")
    print(f"- Endpoint: {EP_ACCOUNT_BALANCE}")
    print(f"- Chu kỳ: {interval_seconds}s")
    print(f"- File ghi thô: {out_file}")
    print(f"- Dừng lúc: {stop_time.strftime('%H:%M:%S')} (giờ VN)")
    print("=" * 70 + "\n")

    auth = await ensure_authenticated(cfg, storage)
    client_id = decode_client_id(auth.token_manager.access_token)

    call_count = 0
    anomalies_detected = 0

    try:
        while True:
            cur_vn = datetime.now(TZ)
            if cur_vn.time() >= stop_time:
                print(f"\nĐã đạt mốc dừng {stop_time.strftime('%H:%M:%S')}. Kết thúc probe.")
                break

            call_count += 1
            ts_str = cur_vn.strftime("%Y-%m-%d %H:%M:%S")

            try:
                raw = await auth.rest_client.get(
                    EP_ACCOUNT_BALANCE,
                    params={"clientId": client_id, "accountNo": account_no},
                )
            except Exception as e:
                print(f"[{ts_str}] [LỖI GỌI REST] #{call_count}: {type(e).__name__}: {e}")
                raw = {"error": f"{type(e).__name__}: {e}"}

            record: dict[str, Any] = {
                "recv_ts": cur_vn.isoformat(),
                "account_no": account_no,
                "call_index": call_count,
                "raw": raw,
            }

            with open(out_file, "a", encoding="utf-8") as f:  # noqa: ASYNC230
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()

            equity = raw.get("equity") if isinstance(raw, dict) else None
            if equity is None:
                print(f"[{ts_str}] #{call_count:03d} -> KHÔNG CÓ KHỐI EQUITY (equity is None)")
                anomalies_detected += 1
            elif not isinstance(equity, dict):
                print(f"[{ts_str}] #{call_count:03d} -> equity không phải dict: {type(equity)} = {equity!r}")
                anomalies_detected += 1
            else:
                keys = list(equity.keys())
                withdrawable_raw = equity.get("withdrawable")
                total_debt_raw = equity.get("totalDebt")
                balance_raw = equity.get("accountBalance")

                is_anomaly = False
                for f_name, f_val in [
                    ("withdrawable", withdrawable_raw),
                    ("totalDebt", total_debt_raw),
                    ("accountBalance", balance_raw),
                ]:
                    if f_name not in equity or f_val is None or (isinstance(f_val, str) and not f_val.strip()):
                        is_anomaly = True

                status_tag = "[BẤT THƯỜNG]" if is_anomaly else "[BÌNH THƯỜNG]"
                if is_anomaly:
                    anomalies_detected += 1

                print(
                    f"[{ts_str}] #{call_count:03d} {status_tag} "
                    f"keys={keys} | "
                    f"withdrawable={withdrawable_raw!r} "
                    f"totalDebt={total_debt_raw!r} "
                    f"accountBalance={balance_raw!r}"
                )

            await asyncio.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("\nNhận ngắt bàn phím (Ctrl+C). Dừng probe an toàn.")
    finally:
        try:
            await auth.close()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("=== TỔNG KẾT PROBE KHUNG 22H ===")
    print(f"- Tổng số lần gọi: {call_count}")
    print(f"- Số lần phát hiện bất thường: {anomalies_detected}")
    print(f"- File dữ liệu: {out_file}")
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Thăm dò phản hồi account balance SSI trong khung 22h (Brief 88 Task 1)"
    )
    parser.add_argument(
        "--account",
        default=TARGET_ACCOUNT,
        help=f"Mã tài khoản (mặc định: {TARGET_ACCOUNT})",
    )
    parser.add_argument(
        "--until",
        default="23:00",
        help="Giờ tự dừng HH:MM (mặc định: 23:00)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="Chu kỳ gọi tính theo giây (mặc định: 60.0)",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn config.yaml (mặc định: config/config.yaml)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/probe",
        help="Thư mục lưu JSONL (mặc định: data/probe)",
    )
    args = parser.parse_args()

    parts = [int(p) for p in args.until.split(":")]
    stop_t = dt_time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)

    asyncio.run(
        probe_account_balance(
            account_no=args.account,
            stop_time=stop_t,
            interval_seconds=args.interval,
            config_path=args.config,
            data_dir=args.data_dir,
        )
    )


if __name__ == "__main__":
    main()
