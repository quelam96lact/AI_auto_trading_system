"""Thăm dò toàn diện mã 3 chữ cái từ SSI để tìm mã đã hủy niêm yết 2016-2022.

Quy định Brief 170 vòng 2:
- CHỈ ĐỌC (API SSI và DB Postgres), KHÔNG GHI BẤT KỲ DỮ LIỆU NÀO VÀO DB.
- Dò không gian 26^3 = 17.576 mã (A-Z) hoặc theo khối tiền tố (ví dụ A**).
- Tốc độ gọi API: tối đa 1 request / giây (throttle 1.0s). Tự động thử lại khi gặp 429.
- Ghi tiến độ ra file JSON để có thể chạy tiếp sau khi bị ngắt.
- Tuyệt đối không nhúng chuỗi địa chỉ web nào.

Chạy:
  uv run python scripts/probe_ssi_delisted_coverage.py --prefix A
"""

import argparse
import asyncio
import io
import json
import string
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._db_common import resolve_dsn
from trading.collector.backfill import SSIRestClient
from trading.config import load_config
from trading.storage.db import Storage

PROBE_FROM = date(2016, 1, 1)
PROBE_TO = date(2022, 12, 31)
DEFAULT_PROGRESS_PATH = Path("data/probe_delisted_progress.json")
IS_CUTOFF_DATE = "2022-06-30"

KNOWN_13_CHECK_SYMBOLS = [
    "BGM",
    "CNH",
    "GTN",
    "HVG",
    "KDF",
    "KHB",
    "KSA",
    "MNC",
    "PME",
    "ROS",
    "SDE",
    "SDI",
    "SLC",
]


def generate_3letter_symbols(prefix: str | None = None) -> list[str]:
    """Sinh danh sách mã 3 chữ cái A-Z (26^3 = 17.576 mã hoặc 676 mã theo prefix)."""
    letters = string.ascii_uppercase
    if prefix:
        pref = prefix.strip().upper()
        if len(pref) == 1:
            return [pref + b + c for b in letters for c in letters]
        if len(pref) == 2:
            return [pref + c for c in letters]
        if len(pref) == 3:
            return [pref]
    return [a + b + c for a in letters for b in letters for c in letters]


def load_progress(path: Path | str) -> dict[str, dict[str, Any]]:
    """Đọc tiến độ thăm dò từ file json nếu có."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_progress(path: Path | str, data: dict[str, dict[str, Any]]) -> None:
    """Lưu tiến độ thăm dò ra file json."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp_p = p.with_suffix(".tmp")
    temp_p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_p.replace(p)


class RateLimiter:
    """Điều tiết nhịp gọi API tối đa 1 lần mỗi giây."""

    def __init__(self, interval_seconds: float = 1.0):
        self.interval = interval_seconds
        self._last_call: float = 0.0

    async def wait(self) -> None:
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self._last_call = time.time()


async def probe_symbol_with_retry(
    client: Any,
    symbol: str,
    frm: date = PROBE_FROM,
    to: date = PROBE_TO,
    max_retries: int = 3,
    base_backoff: float = 2.0,
) -> dict[str, Any]:
    """Gọi daily_ohlc cho một mã với cơ chế thử lại khi gặp 429 / rate limit."""
    attempt = 0
    while True:
        try:
            bars = await client.daily_ohlc(symbol, frm, to)
            if not bars:
                return {
                    "count": 0,
                    "first_date": None,
                    "last_date": None,
                    "error": None,
                }
            return {
                "count": len(bars),
                "first_date": bars[0].ts.date().isoformat(),
                "last_date": bars[-1].ts.date().isoformat(),
                "error": None,
            }
        except Exception as e:
            err_msg = str(e)
            attempt += 1
            is_429 = (
                "429" in err_msg
                or "rate limit" in err_msg.lower()
                or "too many requests" in err_msg.lower()
            )
            if is_429 and attempt <= max_retries:
                delay = base_backoff * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
                continue
            return {
                "count": 0,
                "first_date": None,
                "last_date": None,
                "error": f"{type(e).__name__}: {e}",
            }


def fetch_db_stock_symbols(storage: Any) -> set[str]:
    """Lấy danh sách mã cổ phiếu 3 chữ cái trong DB bars_daily có nến trong 2016-2022."""
    if storage is None or not hasattr(storage, "conn"):
        return set()
    try:
        with storage.conn() as c:
            rows = c.execute("""
                SELECT DISTINCT symbol
                FROM bars_daily
                WHERE ts >= '2016-01-01' AND ts <= '2022-12-31 23:59:59'
                  AND length(symbol) = 3
                """).fetchall()
            return {r[0].upper() for r in rows if r[0]}
    except Exception as e:
        print(f"[Cảnh báo] Lỗi khi đọc danh sách mã từ DB: {e}")
        return set()


def analyze_probe_results(
    probed_data: dict[str, dict[str, Any]],
    db_symbols: set[str],
    symbol_subset: list[str] | None = None,
) -> dict[str, Any]:
    """Phân tích kết quả thăm dò, tính độ nhạy và danh sách mã thiếu."""
    if symbol_subset is not None:
        subset_set = set(symbol_subset)
        relevant_probed = {k: v for k, v in probed_data.items() if k in subset_set}
        db_in_scope = {s for s in db_symbols if s in subset_set}
    else:
        relevant_probed = probed_data
        db_in_scope = db_symbols

    # Tập S: các mã có >= 1 nến
    s_symbols = {k: v for k, v in relevant_probed.items() if v.get("count", 0) > 0}

    # Độ nhạy (đối chứng dương): các mã trong DB phải có trong S
    matched_db = [s for s in db_in_scope if s in s_symbols]
    missed_db = [s for s in db_in_scope if s not in s_symbols]
    sensitivity = (len(matched_db) / len(db_in_scope)) if db_in_scope else 1.0

    # Mã thiếu = S trừ đi các mã có trong DB
    missing_from_db: list[dict[str, Any]] = []
    for sym, item in s_symbols.items():
        if sym not in db_symbols:
            missing_from_db.append(
                {
                    "symbol": sym,
                    "count": item.get("count", 0),
                    "first_date": item.get("first_date"),
                    "last_date": item.get("last_date"),
                }
            )

    # Sắp xếp mã thiếu theo ngày cuối
    missing_from_db.sort(key=lambda x: (x["last_date"] or "", x["symbol"]))

    # Phân nhóm mã thiếu
    dead_in_is = [
        m for m in missing_from_db if m["last_date"] and m["last_date"] < IS_CUTOFF_DATE
    ]
    other_missing = [
        m
        for m in missing_from_db
        if not m["last_date"] or m["last_date"] >= IS_CUTOFF_DATE
    ]

    return {
        "total_probed": len(relevant_probed),
        "s_count": len(s_symbols),
        "s_symbols": s_symbols,
        "db_in_scope_count": len(db_in_scope),
        "matched_db_count": len(matched_db),
        "missed_db": missed_db,
        "sensitivity": sensitivity,
        "missing_count": len(missing_from_db),
        "dead_in_is_count": len(dead_in_is),
        "other_missing_count": len(other_missing),
        "dead_in_is": dead_in_is,
        "other_missing": other_missing,
    }


async def run_probe_workflow(
    client: Any,
    storage: Any,
    symbols: list[str],
    progress_path: Path | str = DEFAULT_PROGRESS_PATH,
    throttle_seconds: float = 1.0,
    save_interval: int = 10,
) -> dict[str, Any]:
    """Thực thi luồng thăm dò danh sách mã có khả năng khôi phục tiến độ."""
    progress_data = load_progress(progress_path)
    limiter = RateLimiter(interval_seconds=throttle_seconds)

    # Ma tung loi (het luot thu 429) phai do lai, khong coi la da xong (sua cua Claude khi audit).
    to_probe = [
        s for s in symbols if s not in progress_data or progress_data[s].get("error")
    ]
    print(
        f"Tổng số mã cần khảo sát: {len(symbols)} (Đã có sẵn: {len(symbols) - len(to_probe)}, Cần gọi mới: {len(to_probe)})"
    )

    for idx, sym in enumerate(to_probe, start=1):
        await limiter.wait()
        res = await probe_symbol_with_retry(client, sym, PROBE_FROM, PROBE_TO)
        progress_data[sym] = res
        if res.get("count", 0) > 0:
            print(
                f"  -> Tìm thấy mã: {sym:<4} | {res['count']:<4} nến | {res['first_date']} -> {res['last_date']}"
            )
        if idx % save_interval == 0:
            save_progress(progress_path, progress_data)

    save_progress(progress_path, progress_data)

    db_symbols = fetch_db_stock_symbols(storage)
    analysis = analyze_probe_results(progress_data, db_symbols, symbol_subset=symbols)
    return analysis


def print_report(analysis: dict[str, Any], prefix: str | None = None) -> None:
    print("\n" + "=" * 90)
    pref_txt = f"KHỐI {prefix}**" if prefix else "TOÀN BỘ KHÔNG GIAN"
    print(f"BÁO CÁO KẾT QUẢ THĂM DÒ DỮ LIỆU SSI ({pref_txt}) — BRIEF 170 VÒNG 2")
    print("=" * 90)

    print(f"\n1. Tổng số mã đã thăm dò: {analysis['total_probed']}")
    print(f"2. Số mã có >= 1 nến trong 2016–2022 (Tập S): {analysis['s_count']}")

    print("\n--- 3. ĐỐI CHỨNG DƯƠNG / ĐỘ NHẠY ---")
    print(
        f"Mã 3 chữ cái trong DB bars_daily thuộc phạm vi: {analysis['db_in_scope_count']}"
    )
    print(
        f"Số mã tìm thấy lại trong S: {analysis['matched_db_count']} / {analysis['db_in_scope_count']}"
    )
    print(f"ĐỘ NHẠY (SENSITIVITY): {analysis['sensitivity']:.1%}")
    if analysis["missed_db"]:
        print(
            f"CẢNH BÁO: Có mã bị lọt ({len(analysis['missed_db'])} mã): {analysis['missed_db']}"
        )
    else:
        print("=> ĐẠT ĐỐI CHỨNG DƯƠNG: 100% mã trong DB đều được SSI trả về chính xác.")

    print(
        f"\n--- 4. DANH SÁCH MÃ THIẾU TRONG DB (TỔNG CỘNG: {analysis['missing_count']} MÃ) ---"
    )
    print(
        f"  * Nhóm 1: Chết trong IS (Ngày cuối < {IS_CUTOFF_DATE}): {analysis['dead_in_is_count']} mã"
    )
    print(
        f"  * Nhóm 2: Còn lại (Ngày cuối >= {IS_CUTOFF_DATE}): {analysis['other_missing_count']} mã"
    )

    if analysis["dead_in_is"]:
        print("\n  [Nhóm 1: Mã chết trong IS]")
        print(f"  {'Mã':<6} | {'Số nến':<8} | {'Nến đầu':<10} | {'Nến cuối':<10}")
        print("  " + "-" * 42)
        for m in analysis["dead_in_is"]:
            print(
                f"  {m['symbol']:<6} | {m['count']:<8} | {m['first_date']:<10} | {m['last_date']:<10}"
            )

    if analysis["other_missing"]:
        print("\n  [Nhóm 2: Mã thiếu khác (Còn hoạt động hoặc hủy sau 06/2022)]")
        print(f"  {'Mã':<6} | {'Số nến':<8} | {'Nến đầu':<10} | {'Nến cuối':<10}")
        print("  " + "-" * 42)
        for m in analysis["other_missing"]:
            print(
                f"  {m['symbol']:<6} | {m['count']:<8} | {m['first_date']:<10} | {m['last_date']:<10}"
            )

    print("\n--- 5. ĐỐI CHIẾU 13 MÃ MỤC §0 ---")
    s_syms = analysis.get("s_symbols", {})
    for sym in KNOWN_13_CHECK_SYMBOLS:
        if prefix and not sym.startswith(prefix.upper()):
            continue
        if sym in s_syms:
            item = s_syms[sym]
            print(
                f"  - {sym}: CÓ trong S ({item.get('count')} nến, từ {item.get('first_date')} đến {item.get('last_date')})"
            )
        else:
            print(f"  - {sym}: KHÔNG có trong S (hoặc chưa thăm dò)")

    print("=" * 90 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exhaustive SSI 3-letter delisted symbols probe (Read-only)"
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Prefix to filter symbols (e.g. 'A' for A** 676 symbols)",
    )
    parser.add_argument(
        "--config", default="config/config.yaml", help="Path to config file"
    )
    parser.add_argument("--dsn", default=None, help="Postgres DB DSN override")
    parser.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="Delay between SSI calls in seconds",
    )
    parser.add_argument(
        "--progress-file",
        default=str(DEFAULT_PROGRESS_PATH),
        help="Path to progress JSON file",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only analyze and print report from progress file",
    )
    args = parser.parse_args()

    symbols = generate_3letter_symbols(prefix=args.prefix)
    progress_file = Path(args.progress_file)

    if args.report_only:
        dsn = resolve_dsn(args.dsn)
        storage = Storage(dsn)
        probed_data = load_progress(progress_file)
        db_symbols = fetch_db_stock_symbols(storage)
        analysis = analyze_probe_results(probed_data, db_symbols, symbol_subset=symbols)
        print_report(analysis, prefix=args.prefix)
        return

    dsn = resolve_dsn(args.dsn)
    cfg = load_config(args.config)
    storage = Storage(dsn)

    async def _run():
        client = SSIRestClient(cfg, storage)
        try:
            analysis = await run_probe_workflow(
                client=client,
                storage=storage,
                symbols=symbols,
                progress_path=progress_file,
                throttle_seconds=args.throttle,
            )
            print_report(analysis, prefix=args.prefix)
        finally:
            await client.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
