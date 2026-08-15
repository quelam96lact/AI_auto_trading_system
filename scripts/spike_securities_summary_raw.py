"""Bước 0 (prompt 2026-08-15-hermes-refprice-check.md): kiểm khả thi endpoint
securitiesSummary TRƯỚC khi xây gì.

Hai câu hỏi chưa ai kiểm:
1. Endpoint /api/v3/data/securitiesSummary có trả dữ liệu ngày cũ (2016-2018) không?
2. Response THÔ có trường refPrice/ceiling/floor mà SDK SecuritiesSummary.from_list
   đang VỨT ĐI không? (from_list chỉ lấy tập key cố định — xem
   ssi_sdk/models/market_data.py:386-405: symbol, tradingDate, priceChange,
   priceChangePercentage, open, high, low, close, average, totalMatch...)

Gọi thẳng HTTP (httpx) với Bearer token từ ssi_auth_state (đường collector đang
dùng, KHÔNG OTP mới) để xem response THÔ trước khi parse.

CHỈ ĐỌC: không UPDATE/DELETE/INSERT. Token hết hạn -> DỪNG, báo, không tự xoay.

CLI:
  uv run python scripts/spike_securities_summary_raw.py [--symbol HNB] [--from 2016/03/25] [--to 2016/04/05]
"""

import argparse
import asyncio
import json
import sys

import httpx
from _db_common import load_dotenv, resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://api.ssi.com.vn/api/v3/data/securitiesSummary"


async def _run(symbol: str, frm: str, to: str) -> None:
    load_dotenv()
    from trading.config import load_config
    from trading.storage.db import Storage

    cfg = load_config("config/config.yaml")
    storage = Storage(resolve_dsn())

    from trading.collector.ssi_auth import ensure_authenticated

    auth = await ensure_authenticated(cfg, storage)
    try:
        token = auth.token_manager.token
        access = getattr(token, "access_token", None) if token else None
        if not access:
            # Token object có thể lưu camelCase — thử cả 2 tên
            access = getattr(token, "accessToken", None) if token else None
        if not access:
            print("KHÔNG lấy được access_token — dừng, không tự xoay token")
            return
        params = {
            "symbol": symbol,
            "from": frm,
            "to": to,
            "pageIndex": 1,
            "pageSize": 100,
        }
        headers = {"Authorization": f"Bearer {access}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(API_URL, params=params, headers=headers)
        print(f"HTTP {resp.status_code}")
        raw = resp.json()
        data = raw.get("data") or raw.get("Data") or []
        print(f"Tổng dòng trả về: {len(data)}")
        if not data:
            print("RAW FULL:")
            print(json.dumps(raw, ensure_ascii=False, indent=2)[:2000])
            return
        print("\nJSON THÔ — DÒNG ĐẦU TIÊN (trước parse):")
        print(json.dumps(data[0], ensure_ascii=False, indent=2))
        print("\nCÁC KEY CỦA DÒNG ĐẦU:")
        print(sorted(data[0].keys()))
        # Kiểm tra xem SDK có vứt field nào không
        sdk_keys = {
            "symbol", "tradingDate", "priceChange", "priceChangePercentage",
            "open", "high", "low", "close", "average", "totalMatch",
            "totalMatchValue", "totalBuy", "totalTradeBuy", "totalSell",
            "totalTradeSell",
        }
        raw_keys = set(data[0].keys())
        dropped = raw_keys - sdk_keys
        print(f"\nFIELD SDK VỨT ĐI (có trong raw, không trong SecuritiesSummary): {sorted(dropped) if dropped else 'KHÔNG CÓ'}")
        # Hiển thị vài dòng quanh 2016-03-31 nếu có
        print("\nTẤT CẢ DÒNG (tradingDate | close | priceChange | priceChangePercentage):")
        for r in data:
            print(f"  {r.get('tradingDate')} | close={r.get('close')} | "
                  f"priceChange={r.get('priceChange')} | "
                  f"priceChangePct={r.get('priceChangePercentage')}")
    finally:
        await auth.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="HNB")
    ap.add_argument("--from", dest="frm", default="2016/03/25")
    ap.add_argument("--to", dest="to", default="2016/04/05")
    args = ap.parse_args()
    asyncio.run(_run(args.symbol, args.frm, args.to))


if __name__ == "__main__":
    main()
