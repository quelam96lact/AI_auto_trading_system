"""Task 1 (Brief 97): Tham do: SSI co tra trang thai "han che giao dich" khong? (CHI DOC)

Goi API du lieu SSI, lay thong tin chung khoan tho (truoc khi SDK parse) cho POM va HPG.
Token tu ssi_auth_state qua ensure_authenticated (khong OTP moi).
"""

import asyncio
import json
import sys

import httpx
from _db_common import load_dotenv, resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def main() -> None:
    load_dotenv()
    from trading.collector.ssi_auth import ensure_authenticated
    from trading.config import load_config
    from trading.storage.db import Storage

    cfg = load_config("config/config.yaml")
    storage = Storage(resolve_dsn())

    auth = await ensure_authenticated(cfg, storage)
    try:
        token = auth.token_manager.token
        access = getattr(token, "access_token", None) if token else None
        if not access:
            access = getattr(token, "accessToken", None) if token else None
        if not access:
            print("KHONG lay duoc access_token tu ssi_auth_state")
            return

        headers = {"Authorization": f"Bearer {access}"}
        base_url = "https://api.ssi.com.vn"

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Thu /api/v3/data/securitiesByBoard voi param symbol
            results = {}
            for sym in ["POM", "HPG"]:
                url = f"{base_url}/api/v3/data/securitiesByBoard"
                resp = await client.get(url, params={"symbol": sym}, headers=headers)
                print(f"securitiesByBoard?symbol={sym} -> HTTP {resp.status_code}")
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, list):
                        data = payload
                    elif isinstance(payload, dict):
                        data = payload.get("data") or payload.get("Data") or []
                    else:
                        data = []
                    results[sym] = data[0] if data else {}
                else:
                    print(f"Error {sym}: {resp.text}")

            print("\n=== KET QUA /api/v3/data/securitiesByBoard?symbol=... ===")
            for sym in ["POM", "HPG"]:
                print(f"\n--- {sym} (RAW KEYS: {sorted(results.get(sym, {}).keys())}) ---")
                print(json.dumps(results.get(sym, {}), ensure_ascii=False, indent=2))

            # 2. Thu them endpoint khac neu co (vi du securitiesDetails, securitiesSummary)
            for sym in ["POM", "HPG"]:
                url_sum = f"{base_url}/api/v3/data/securitiesSummary"
                resp_sum = await client.get(url_sum, params={"symbol": sym, "pageIndex": 1, "pageSize": 1}, headers=headers)
                print(f"securitiesSummary?symbol={sym} -> HTTP {resp_sum.status_code}")
                if resp_sum.status_code == 200:
                    d_sum = resp_sum.json().get("data") or []
                    if d_sum:
                        print(f"securitiesSummary first item keys {sym}: {sorted(d_sum[0].keys())}")

    finally:
        await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
