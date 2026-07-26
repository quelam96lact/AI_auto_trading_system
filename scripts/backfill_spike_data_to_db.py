"""Ghi dữ liệu spike thật (5 phút) từ file JSON vào bảng `bars`, có kiểm tra trùng lặp.

Chỉ đọc các file JSON local đã có sẵn:
- .spike_derivative_ohlc_5m_2m_sample.json
- .spike_ohlc_hnx_sample.json
- .spike_ohlc_upcom_sample.json

Không gọi SSI API, không sửa code production.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

# Windows console thường dùng cp1252; ép UTF-8 để print tiếng Việt không lỗi.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SPIKE_FILES = [
    Path(__file__).parent / ".spike_derivative_ohlc_5m_2m_sample.json",
    Path(__file__).parent / ".spike_ohlc_hnx_sample.json",
    Path(__file__).parent / ".spike_ohlc_upcom_sample.json",
]


def _parse_trading_date(s: str) -> datetime:
    # Cùng format/TZ với trading/collector/backfill.py::_parse_trading_date
    dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)


def _rows_to_bars(rows: list[dict]) -> list[Bar]:
    return [
        Bar(
            symbol=r["symbol"],
            ts=_parse_trading_date(r["trading_date"]),
            open=float(r["open_price"]),
            high=float(r["high_price"]),
            low=float(r["low_price"]),
            close=float(r["close_price"]),
            volume=int(r["volume"]),
            source="ssi-spike",
        )
        for r in rows
    ]


def _load_bars_from_file(path: Path) -> list[Bar] | None:
    if not path.exists():
        print(f"[skip] file chưa tồn tại: {path}")
        return None
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    rows = raw if isinstance(raw, list) else raw.get("data", [])
    if not rows:
        print(f"[skip] file rỗng: {path}")
        return []
    return _rows_to_bars(rows)


def _process_file(storage: Storage, path: Path) -> None:
    bars = _load_bars_from_file(path)
    if bars is None:
        return
    if not bars:
        print(f"[empty] {path.name}: không có bar nào")
        return

    symbol = bars[0].symbol
    incoming_ts = {b.ts for b in bars}

    with storage.conn() as c:
        existing_ts = {
            row[0]
            for row in c.execute(
                "SELECT ts FROM bars WHERE symbol = %s", (symbol,)
            ).fetchall()
        }

    n_duplicate = len(existing_ts & incoming_ts)
    n_new = len(incoming_ts - existing_ts)
    expected_after = len(existing_ts | incoming_ts)

    print(
        f"{symbol}: {len(bars)} bar sắp ghi — "
        f"{n_duplicate} trùng (sẽ ghi đè), {n_new} dòng mới. "
        f"Dự kiến tổng sau khi ghi: {expected_after}"
    )

    storage.write_bars(bars)

    with storage.conn() as c:
        count_after = c.execute(
            "SELECT count(*) FROM bars WHERE symbol = %s", (symbol,)
        ).fetchone()[0]

    print(
        f"{symbol}: đã ghi xong — tổng dòng trong bars = {count_after} "
        f"(dự kiến {expected_after}, {'khớp' if count_after == expected_after else 'KHÔNG khớp'})"
    )


def main() -> None:
    dsn = os.environ["DB_DSN"]
    storage = Storage(dsn)

    for path in SPIKE_FILES:
        _process_file(storage, path)


if __name__ == "__main__":
    main()
