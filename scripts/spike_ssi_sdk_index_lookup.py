"""Spike: tra mã index thật SSI dùng qua get_indexes(), so với "VNINDEX"/"VN30"
đang giả định dùng cho subscribe_index() (đang xác nhận KHÔNG nhận được tick nào
qua 2 lần test thật trong giờ giao dịch — nghi ngờ giống bug mã hợp đồng phái
sinh cũ: public code khác internal code SSI dùng để subscribe).

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_index_lookup.py

Cần env SSI_API_KEY, SSI_API_SECRET. REST call thuần — chạy được ngoài giờ
giao dịch, không cần đợi phiên mở.
"""

import asyncio
import dataclasses
import json
from pathlib import Path

from _ssi_spike_common import make_auth

OUT = Path(__file__).parent / ".spike_indexes.json"


async def main() -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        indexes = await data.market_data.get_indexes()
        payload = [dataclasses.asdict(i) for i in indexes]
        OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Tổng {len(indexes)} index → {OUT}")
        for i in indexes:
            marker = (
                " <-- VNINDEX/VN30?" if i.index.upper() in ("VNINDEX", "VN30") else ""
            )
            print(
                f"  index={i.index!r} index_name={i.index_name!r} board={i.board}{marker}"
            )


if __name__ == "__main__":
    asyncio.run(main())
