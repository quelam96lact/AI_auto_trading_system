"""Spike: xác nhận get_index_summary() trả giá trị index thật (REST, không phải
stream). Sau khi xác nhận subscribe_index()/subscribe_symbol_ohlcv() KHÔNG có
kênh WS nào phát giá trị index thật (subscribe_index -> trade/quote/room rỗng
vì index không giao dịch được; subscribe_symbol_ohlcv trên "VNINDEX"/"VN30" bị
server hiểu như board/nhóm, trả về nến của TỪNG cổ phiếu thành viên, không phải
nến index) - hướng còn lại là poll REST định kỳ, giống cách backfill bar đã
làm cho cổ phiếu.

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_index_summary.py

Cần env SSI_API_KEY, SSI_API_SECRET. REST call thuần - chạy được ngoài giờ
giao dịch (giá trị có thể là của phiên gần nhất, không phải live tick).
"""

import asyncio
import dataclasses
import json
from pathlib import Path

from _ssi_spike_common import make_auth

OUT = Path(__file__).parent / ".spike_index_summary.json"
INDICES = ["VNINDEX", "VN30"]


async def main() -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        results = {}
        for idx in INDICES:
            summary = await data.market_data.get_index_summary(idx)
            results[idx] = dataclasses.asdict(summary) if summary else None
            print(f"{idx}: {results[idx]}")
        OUT.write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Đã lưu → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
