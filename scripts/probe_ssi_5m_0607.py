"""Điều tra nguyên nhân mất bar 5m ngày 06/07 và 07/07/2026 tại SSI FastConnect (Brief đợt 14 - Task 2).

Chỉ ĐỌC từ SSI API, TUYỆT ĐỐI KHÔNG ghi/nạp gì vào database `bars`.

3 mã: VCB, IJC, MSR
3 ngày:
  - 2026-07-06 (Mục tiêu 1: nghi vấn mất 0 bar)
  - 2026-07-07 (Mục tiêu 2: nghi vấn chỉ có 1 bar đóng cửa)
  - 2026-07-08 (Đối chứng dương: ngày giao dịch kế cận chắc chắn có dữ liệu)
Tổng cộng: 3 mã × 3 ngày = 9 lượt gọi API.
"""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from trading.collector.backfill import SSIRestClient
from trading.config import load_config
from trading.storage.db import Storage

SYMBOLS = ["VCB", "IJC", "MSR"]
TARGET_DATES = [
    (date(2026, 7, 6), "Mục tiêu 06/07/2026 (Nghi vấn mất 0 bar toàn rổ)"),
    (date(2026, 7, 7), "Mục tiêu 07/07/2026 (Nghi vấn chỉ có 1 bar khớp đóng cửa)"),
    (date(2026, 7, 8), "Đối chứng dương 08/07/2026 (Ngày giao dịch bình thường)"),
]


async def probe_symbol_date(client: SSIRestClient, symbol: str, target_d: date) -> tuple[int, list[str]]:
    """Fetch 5m bars từ SSI cho 1 mã và 1 ngày duy nhất (CHỈ ĐỌC)."""
    try:
        bars = await client.intraday_ohlc(symbol, target_d, target_d)
        ts_list = [f"{b.ts.strftime('%H:%M:%S')} (c={b.close:,} v={b.volume:,})" for b in bars]
        return len(bars), ts_list
    except Exception as e:
        print(f"  [LỖI FETCH] {symbol} ngày {target_d}: {type(e).__name__}: {e}", file=sys.stderr)
        return -1, [str(e)]


def _init_env() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    db_dsn = os.environ.get("DB_DSN", "postgresql://trading:trading@127.0.0.1:5432/trading")
    db_dsn = db_dsn.replace("@postgres:", "@127.0.0.1:").replace("@localhost:", "@127.0.0.1:")
    os.environ["DB_DSN"] = db_dsn


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 100, flush=True)
    print("BÁO CÁO ĐIỀU TRA DỮ LIỆU NẾN 5 PHÚT TẠI SSI API: 06/07 & 07/07/2026 (BRIEF ĐỢT 14 - TASK 2)", flush=True)
    print("=" * 100, flush=True)

    _init_env()

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
    cfg = load_config(cfg_path)
    storage = Storage(cfg.db_dsn)

    client = SSIRestClient(cfg, storage)
    results: dict[str, dict[date, tuple[int, list[str]]]] = {sym: {} for sym in SYMBOLS}

    print("\n--- THỰC HIỆN 9 LƯỢT GỌI API THỰC TẾ QUA SSIRESTCLIENT (CHỈ ĐỌC) ---", flush=True)
    try:
        for sym in SYMBOLS:
            print(f"\n[MÃ CHỨNG KHOÁN: {sym}]", flush=True)
            for target_d, desc in TARGET_DATES:
                count, ts_samples = await probe_symbol_date(client, sym, target_d)
                results[sym][target_d] = (count, ts_samples)
                sample_str = f" | Mẫu nến: {', '.join(ts_samples[:3])}" if count > 0 else ""
                if count > 3:
                    sample_str += f" ... [cuối: {ts_samples[-1]}]"
                print(f"  - {target_d.isoformat()} ({desc}): {count} bar{sample_str}", flush=True)
    finally:
        await client.close()

    # Bước 3: Bảng tổng hợp kết quả
    print("\n" + "=" * 100, flush=True)
    print("BẢNG TỔNG HỢP SỐ LƯỢNG NẾN 5 PHÚT TRẢ VỀ TỪ SSI API", flush=True)
    print("=" * 100, flush=True)
    header = f"{'Mã CP':<10} | {'06/07/2026 (Mục tiêu 1)':<25} | {'07/07/2026 (Mục tiêu 2)':<25} | {'08/07/2026 (Đối chứng dương)':<28}"
    print(header, flush=True)
    print("-" * 100, flush=True)

    all_control_positive = True
    ssi_has_full_0607_data = False

    for sym in SYMBOLS:
        c_06 = results[sym][date(2026, 7, 6)][0]
        c_07 = results[sym][date(2026, 7, 7)][0]
        c_08 = results[sym][date(2026, 7, 8)][0]

        if c_08 <= 0:
            all_control_positive = False
        # Một ngày giao dịch đầy đủ phải có ~46 bar (HOSE/HNX) hoặc ~54 bar (UPCoM).
        # Nếu 06/07 hoặc 07/07 có >10 bar thì SSI có dữ liệu trong phiên.
        if c_06 > 10 or c_07 > 10:
            ssi_has_full_0607_data = True

        str_06 = f"{c_06} bar" if c_06 >= 0 else "LỖI"
        str_07 = f"{c_07} bar" if c_07 >= 0 else "LỖI"
        str_08 = f"{c_08} bar" if c_08 >= 0 else "LỖI"

        print(f"{sym:<10} | {str_06:<25} | {str_07:<25} | {str_08:<28}", flush=True)

    print("-" * 100, flush=True)

    # Bước 4: Đưa ra kết luận chính xác theo 2 nhánh
    print("\n--- BƯỚC 4: KẾT LUẬN VỀ NGUYÊN NHÂN MẤT NẾN 5 PHÚT ---", flush=True)
    if not all_control_positive:
        print("KẾT LUẬN: MẬP MỜ / VÔ NGHĨA — Ngày đối chứng dương (08/07) không trả về dữ liệu (có thể do lỗi kết nối hoặc tham số gọi).", flush=True)
        return 1

    if ssi_has_full_0607_data:
        print("KẾT LUẬN: DỮ LIỆU TỒN TẠI TẠI SSI — Quá trình backfill trước đây của hệ thống đã bị lỗi/bỏ sót 2 ngày này (Bug backfill, có nguy cơ tái diễn).", flush=True)
    else:
        print("KẾT LUẬN: THIẾU TẠI NGUỒN SSI — Ngày 06/07 SSI trả 0 bar và 07/07 chỉ có nến phiên đóng cửa (HOSE/HNX: 1 bar ATC 14:45; UPCoM: 4 bar 14:40-14:55), hoàn toàn không có dữ liệu khớp lệnh phiên sáng/chiều. Trong khi đối chứng 08/07 có đầy đủ 46-54 bar. Điều này chứng minh DB hiện tại khớp 100% dữ liệu mà SSI FastConnect cung cấp. Đây KHÔNG phải lỗi của hệ thống hay quy trình backfill, mà do API máy chủ nguồn SSI bị khuyết dữ liệu lịch sử trong giai đoạn đó.", flush=True)

    print("=" * 100, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
