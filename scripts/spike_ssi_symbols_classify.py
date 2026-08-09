"""Spike Task 4b: khám phá trường phân loại của get_securities_info_by_board.

Mục đích (yêu cầu Claude 2026-08-09):
1. In TẤT CẢ field của 1 phần tử (tìm trường securityType/type/market...)
2. Bảng thành phần mỗi sàn: cổ phiếu / index / CW / loại khác
3. Lưu file symbols KÈM trường phân loại (không chỉ list string)

Chạy: uv run python -m scripts.spike_ssi_symbols_classify
"""

import asyncio
import dataclasses
import json
from datetime import datetime
from pathlib import Path

from trading.calendar_vn import TZ
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import load_config
from trading.storage.db import Storage

OUT = Path(__file__).parent / ".spike_all_symbols_classified.json"


async def main() -> None:
    cfg = load_config("config/config.yaml")
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    auth = await ensure_authenticated(cfg, storage)
    from ssi_sdk import AsyncData
    from ssi_sdk.enums import Board

    data = AsyncData(auth)

    try:
        all_rows = {}
        for label, board in [
            ("HOSE", Board.HOSE),
            ("HNX", Board.HNX),
            ("UPCOM", Board.UPCOM),
        ]:
            securities = await data.market_data.get_securities_info_by_board(board)
            rows = []
            for s in securities:
                d = dataclasses.asdict(s) if dataclasses.is_dataclass(s) else vars(s)
                rows.append(d)
            all_rows[label] = rows
            print(f"[{label}] {len(rows)} phan tu")

        # 1) Toan bo field cua phan tu dau tien (HOSE)
        first = all_rows["HOSE"][0]
        print("\n=== Field phan tu dau tien (HOSE) ===")
        for k, v in first.items():
            print(f"  {k}: {v!r}")

        # 2) Bang thanh phan: dem theo field phan loai
        print("\n=== Bang thanh phan ===")
        for label, rows in all_rows.items():
            cw = [r for r in rows if r.get("cw_underlying_symbol")]
            idx = [r for r in rows if r.get("index") is not None]
            idx_none = [r for r in rows if r.get("index") is None and not r.get("cw_underlying_symbol")]
            has_shares = [r for r in idx_none if (r.get("listed_shares") or 0) > 0]
            no_shares = [r for r in idx_none if not (r.get("listed_shares") or 0) > 0]
            print(f"[{label}] tong={len(rows)}")
            print(f"  CW (cw_underlying_symbol != null): {len(cw)}")
            print(f"  index != null: {len(idx)} | vi du: {[r['symbol'] for r in idx[:5]]}")
            print(f"  con lai (index=null, khong CW): {len(idx_none)}")
            print(f"    - co listed_shares > 0: {len(has_shares)}")
            print(f"    - khong co shares (index None?): {len(no_shares)} | vi du: {[r['symbol'] for r in no_shares[:8]]}")
            # index field cua index that co gia tri gi?
            if idx:
                print(f"    gia tri index field cua {idx[0]['symbol']}: {idx[0]['index']!r}")
            # dieu tra cac ma no-shares co phai CW qua maturity_date / pattern
            if no_shares:
                with_maturity = [r for r in no_shares if r.get("maturity_date")]
                print(f"    no-shares co maturity_date != '': {len(with_maturity)} | vi du: {[r['symbol'] for r in with_maturity[:6]]}")
                # in day du 1 phan tu la (vi du HNX: DSE125004)
                probe = next(
                    (r for r in no_shares if r["symbol"].startswith(("DSE", "F88", "HDB"))),
                    no_shares[0],
                )
                print(f"    FULL FIELD cua {probe['symbol']} (board {label}):")
                for k, v in probe.items():
                    print(f"      {k}: {v!r}")

        # 3) Luu file kem truong phan loai
        payload = {
            "timestamp": datetime.now(TZ).isoformat(),
            "boards": all_rows,
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nDa luu {OUT} (kem toan bo field)")
    finally:
        await auth.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
