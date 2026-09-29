"""Script bảo trì: gộp chunk bars_daily theo năm và đặt chunk_time_interval thành 1 năm.

Brief đợt 128 (2026-09-29):
- Mặc định dry-run: in danh sách nhóm chunk theo năm, số chunk mỗi nhóm, tổng trước -> sau.
- Chỉ thực thi khi có cờ --apply.
- Tham số --dsn là BẮT BUỘC. Script tự từ chối nếu DB là 'trading' mà thiếu
  --i-am-claude-in-maintenance-window để bảo vệ DB thật.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import psycopg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_db_name(dsn: str) -> str:
    """Trích xuất tên database từ chuỗi DSN."""
    try:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
        name = info.get("dbname")
        if name:
            return name
    except Exception:
        pass
    parsed = urlparse(dsn)
    path = parsed.path.lstrip("/")
    if path:
        return path
    return ""


def group_chunks_by_year(
    chunks: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Nhóm danh sách chunk theo năm của range_start."""
    groups: dict[int, list[dict[str, Any]]] = {}
    for c in chunks:
        rs: datetime = c["range_start"]
        yr = rs.year
        groups.setdefault(yr, []).append(c)
    # Sắp xếp theo range_start trong từng năm
    for ch_list in groups.values():
        ch_list.sort(key=lambda x: x["range_start"])
    return dict(sorted(groups.items()))


def fetch_bars_daily_chunks(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Lấy danh sách tất cả các chunk của bars_daily từ timescaledb_information."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT chunk_schema, chunk_name, range_start, range_end
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'bars_daily'
            ORDER BY range_start;
        """)
        rows = cur.fetchall()
        return [
            {
                "chunk_schema": r[0],
                "chunk_name": r[1],
                "range_start": r[2],
                "range_end": r[3],
                "regclass": f"{r[0]}.{r[1]}",
            }
            for r in rows
        ]


GAP_SYMBOL = "__GAP_TEMP__"

_GAPS_SQL = """
    WITH ordered AS (
        SELECT chunk_name, range_start, range_end,
               lead(range_start) OVER (ORDER BY range_start) AS next_start
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'bars_daily'
    )
    SELECT range_end, next_start
    FROM ordered
    WHERE next_start IS NOT NULL AND next_start > range_end;
"""


def bridge_chunk_gaps(conn: psycopg.Connection) -> None:
    """Nếu có khoảng trống giữa các chunk liên tiếp (ví dụ tuần nghỉ Tết không có dữ liệu giao dịch),
    tạo chunk trống bằng cách chèn và xoá ngay một dòng tạm.
    Điều này giúp các chunk liền kề để TimescaleDB merge_chunks thực hiện được.

    INSERT và DELETE nằm trong MỘT transaction, hai lệnh riêng (psycopg 3 không cho
    nhiều lệnh kèm tham số trong một execute). Phiên khác không bao giờ thấy dòng
    tạm (giá 0), và nếu có lỗi thì cả hai bị huỷ — không để lại nến giá 0 trong
    bars_daily thật (loại dữ liệu bẩn đã phải dọn ở đợt 121).
    """
    with conn.cursor() as cur:
        cur.execute(_GAPS_SQL)
        gaps = cur.fetchall()
    if not gaps:
        return
    print(f"\nPhát hiện {len(gaps)} khoảng trống giữa các chunk (ví dụ nghỉ lễ/Tết):")
    for r_end, n_start in gaps:
        print(f"  - Khoảng trống: {r_end} -> {n_start}")
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bars_daily (symbol, ts, open, high, low, close, volume, source)"
                " VALUES (%s, %s, 0, 0, 0, 0, 0, 'gap')",
                (GAP_SYMBOL, r_end),
            )
            cur.execute(
                "DELETE FROM bars_daily WHERE symbol = %s AND ts = %s",
                (GAP_SYMBOL, r_end),
            )
    with conn.cursor() as cur:
        cur.execute(_GAPS_SQL)
        left = cur.fetchall()
        cur.execute("SELECT count(*) FROM bars_daily WHERE symbol = %s", (GAP_SYMBOL,))
        residue = cur.fetchone()[0]
    if left or residue:
        raise RuntimeError(
            f"Lấp khoảng trống thất bại: còn {len(left)} khoảng trống, {residue} dòng tạm"
        )
    print("  -> Đã tạo chunk rỗng lấp đầy khoảng trống; 0 dòng tạm còn lại.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gộp chunk bars_daily theo năm (TimescaleDB 2.27.2)."
    )
    parser.add_argument(
        "--dsn",
        required=True,
        help="DSN kết nối Postgres (bắt buộc).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Thực thi thay đổi trên DB. Mặc định chỉ dry-run in kế hoạch.",
    )
    parser.add_argument(
        "--i-am-claude-in-maintenance-window",
        action="store_true",
        help="Cờ bảo vệ bắt buộc khi thao tác trên DB thật ('trading').",
    )

    args = parser.parse_args()

    # Chuẩn hoá localhost -> 127.0.0.1 để tránh lỗi IPv6 trễ 130s trên Windows
    dsn = args.dsn.replace("localhost", "127.0.0.1")
    db_name = get_db_name(dsn)

    # Chốt an toàn: DB trading bắt buộc phải có cờ bảo vệ. Không đọc được tên DB
    # thì coi như có thể là 'trading' — chốt phải ĐÓNG khi không chắc.
    if db_name in ("trading", "") and not args.i_am_claude_in_maintenance_window:
        print(
            "LỖI: DB 'trading' chỉ được thao tác khi có cờ "
            "--i-am-claude-in-maintenance-window!",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"=== KẾT NỐI DATABASE: {db_name} ===")
    with psycopg.connect(dsn, autocommit=True) as conn:
        if args.apply:
            bridge_chunk_gaps(conn)
        else:
            # Dry-run CHỈ ĐỌC, nhưng phải báo trước việc --apply sẽ GHI một dòng tạm
            # (trong transaction) để lấp khoảng trống — kế hoạch in ra bên dưới là
            # TRƯỚC khi lấp, nên năm có khoảng trống sẽ có thêm 1 chunk khi apply.
            with conn.cursor() as cur:
                cur.execute(_GAPS_SQL)
                for r_end, n_start in cur.fetchall():
                    print(
                        f"[DRY-RUN] Khoảng trống {r_end} -> {n_start}: --apply sẽ lấp bằng chunk rỗng."
                    )

        chunks = fetch_bars_daily_chunks(conn)
        total_before = len(chunks)
        groups = group_chunks_by_year(chunks)

        # Tính kế hoạch
        total_after = 0
        groups_to_merge: list[tuple[int, list[dict[str, Any]]]] = []
        groups_skipped: list[tuple[int, list[dict[str, Any]]]] = []

        for yr, ch_list in groups.items():
            if len(ch_list) > 1:
                total_after += 1
                groups_to_merge.append((yr, ch_list))
            else:
                total_after += len(ch_list)
                groups_skipped.append((yr, ch_list))

        print(f"\nTổng số chunk: {total_before}")
        print(f"Tổng số nhóm năm: {len(groups)}")
        print("\nChi tiết các nhóm năm:")
        for yr, ch_list in groups.items():
            status = (
                f"gộp {len(ch_list)} -> 1"
                if len(ch_list) > 1
                else f"giữ nguyên ({len(ch_list)} chunk)"
            )
            min_ts = ch_list[0]["range_start"].strftime("%Y-%m-%d")
            max_ts = ch_list[-1]["range_end"].strftime("%Y-%m-%d")
            print(
                f"  - Năm {yr}: {len(ch_list)} chunk ({min_ts} -> {max_ts}) [{status}]"
            )

        print(
            f"\nƯớc tính số chunk sau gộp: {total_after} (giảm {total_before - total_after} chunk)"
        )

        if not args.apply:
            print(
                "\n[DRY-RUN] Chế độ xem trước kế hoạch. Không có thay đổi nào được thực thi."
            )
            print("Thêm cờ --apply để thực thi gộp chunk.")
            return

        if not groups_to_merge:
            print(
                "\n[IDEMPOTENT] Tất cả các năm đều đã có ≤ 1 chunk. Không cần gộp thêm gì."
            )
            # Vẫn đảm bảo set_chunk_time_interval thành 1 year
            print("Đảm bảo set_chunk_time_interval('bars_daily', INTERVAL '1 year')...")
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_chunk_time_interval('bars_daily', INTERVAL '1 year');"
                )
            print("Hoàn tất (no-op).")
            return

        print("\n=== BẮT ĐẦU THỰC THI (--apply) ===")

        # 1. Đặt chunk_time_interval thành 1 năm
        print("1. Đặt chunk_time_interval('bars_daily', INTERVAL '1 year')...")
        t_interval = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_chunk_time_interval('bars_daily', INTERVAL '1 year');"
            )
        print(f"   Xong trong {time.perf_counter() - t_interval:.3f}s")

        # 2. Gộp từng nhóm năm, mỗi nhóm một transaction
        print(
            f"\n2. Bắt đầu gộp {len(groups_to_merge)} nhóm năm (mỗi nhóm 1 transaction):"
        )
        total_merge_time = 0.0

        for yr, ch_list in groups_to_merge:
            # Kiểm tra tính liền kề
            for i in range(len(ch_list) - 1):
                if ch_list[i]["range_end"] != ch_list[i + 1]["range_start"]:
                    raise RuntimeError(
                        f"Năm {yr}: Chunks không liền kề giữa {ch_list[i]['chunk_name']} "
                        f"({ch_list[i]['range_end']}) và {ch_list[i+1]['chunk_name']} "
                        f"({ch_list[i+1]['range_start']})"
                    )

            regclass_arr = ", ".join(f"'{c['regclass']}'::regclass" for c in ch_list)
            sql = f"CALL merge_chunks(ARRAY[{regclass_arr}]);"

            t0 = time.perf_counter()
            # Mở transaction riêng cho từng nhóm năm
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(sql)
            elapsed = time.perf_counter() - t0
            total_merge_time += elapsed
            print(
                f"   - Năm {yr}: gộp {len(ch_list)} chunk thành 1 chunk trong {elapsed:.3f}s"
            )

        print(
            f"\nTổng thời gian gộp {len(groups_to_merge)} nhóm: {total_merge_time:.3f}s"
        )

        # 3. Kiểm tra lại số chunk sau khi gộp
        final_chunks = fetch_bars_daily_chunks(conn)
        final_count = len(final_chunks)
        print(f"\nSố chunk sau gộp thực tế: {final_count} (kỳ vọng: {total_after})")
        if final_count != total_after:
            print(
                f"CẢNH BÁO: Số chunk thực tế ({final_count}) khác kỳ vọng ({total_after})!",
                file=sys.stderr,
            )
        else:
            print("Gộp chunk thành công hoàn toàn!")


if __name__ == "__main__":
    main()
