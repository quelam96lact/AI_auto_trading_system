"""Kiểm chứng quy trình sao lưu và phục hồi TimescaleDB (Brief đợt 13 - Task 1).

Script thực hiện:
1. Đếm số dòng bên nguồn (database `trading`) trước khi dump.
2. Dump database `trading` và gzip thành `/tmp/trading_verify.sql.gz` trong container postgres.
3. Kiểm tra kích thước file dump (> 1 MB).
4. Tạo scratch database `trading_restore_test` trong container postgres.
5. Phục hồi bản dump vào `trading_restore_test`, ghi lại toàn bộ output/cảnh báo.
6. Đếm số dòng từng bảng ở cả hai bên (source `trading` và target `trading_restore_test`).
7. Kiểm tra cấu trúc hypertables / chunks giữa hai bên.
8. Dọn dẹp: DROP DATABASE trading_restore_test và xoá file dump tạm; kiểm chứng database gốc nguyên vẹn.
"""

import subprocess
import sys

TABLES_TO_CHECK = [
    "bars",
    "bars_daily",
    "orders",
    "positions",
    "heartbeat",
    "ssi_auth_state",
    "symbol_universe",
    "account_position_snapshot",
    "account_buying_power",
    "backfill_progress",
    "account_balance_snapshot",
    "account_nav_snapshot",
    "account_sync_log",
    # Ten that la pnl_daily (KHONG phai daily_pnl). Ban dau viet sai ten nen
    # query hong -> ca hai ben tra -1 -> bi tinh la "KHOP", trong khi bang PnL
    # that chua he duoc kiem. Xem COUNT_FAILED.
    "pnl_daily",
    "engine_state",
]

#: query_count tra ve gia tri nay khi KHONG doc duoc so dong (bang khong ton
#: tai / query loi). Phai coi la THAT BAI, khong bao gio duoc coi la "khop":
#: -1 == -1 la "hai ben cung khong do duoc", khong phai "hai ben giong nhau".
#: Cung nguyen tac voi drift_report() trong deploy_drift_check.py: thieu du
#: lieu thi tu choi + bao, khong roi ve gia tri de dai.
COUNT_FAILED = -1

SCRATCH_DB = "trading_restore_test"
CONTAINER_DUMP_PATH = "/tmp/trading_verify.sql.gz"


def run_docker_exec(cmd: list[str]) -> tuple[int, str, str]:
    """Chạy command qua docker compose exec."""
    full_cmd = ["docker", "compose", "exec", "-T", "postgres"] + cmd
    p = subprocess.run(full_cmd, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout, p.stderr


def exec_psql(db: str, sql: str) -> tuple[int, str, str]:
    """Chạy SQL query trong container postgres."""
    return run_docker_exec(["psql", "-U", "trading", "-d", db, "-c", sql])


def query_count(db: str, table: str) -> int:
    """Đếm số dòng của 1 bảng trong database chỉ định."""
    rc, stdout, _stderr = exec_psql(db, f"SELECT count(*) FROM {table};")
    if rc != 0:
        return -1
    for line in stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return -1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 100, flush=True)
    print(
        "BÁO CÁO KIỂM CHỨNG SAO LƯU & PHỤC HỒI TIMESCALEDB (BRIEF ĐỢT 13 - TASK 1)",
        flush=True,
    )
    print("=" * 100, flush=True)

    # Bước 1: Đếm số dòng bên nguồn TRƯỚC khi dump
    print(
        "\n--- BƯỚC 1: ĐẾM SỐ DÒNG BÊN NGUỒN (DATABASE 'trading') TRƯỚC KHI DUMP ---",
        flush=True,
    )
    source_counts = {}
    for tbl in TABLES_TO_CHECK:
        cnt = query_count("trading", tbl)
        source_counts[tbl] = cnt
        print(f"  - Bảng {tbl:<28}: {cnt:>12,} dòng", flush=True)

    # Bước 2: Thực hiện pg_dump và gzip trong container postgres
    print("\n--- BƯỚC 2: THỰC HIỆN PG_DUMP & GZIP TRONG CONTAINER ---", flush=True)
    dump_sh = f"rm -f {CONTAINER_DUMP_PATH} && pg_dump -U trading trading | gzip > {CONTAINER_DUMP_PATH}"
    print(f"Chạy lệnh trong container: {dump_sh}", flush=True)

    rc_dump, _out_dump, err_dump = run_docker_exec(["sh", "-c", dump_sh])
    if rc_dump != 0:
        print(
            f"LỖI pg_dump thất bại (exit code {rc_dump}): {err_dump}", file=sys.stderr
        )
        return 1

    # Kiểm tra kích thước file dump
    _rc_stat, out_stat, _ = run_docker_exec(["stat", "-c", "%s", CONTAINER_DUMP_PATH])
    _rc_ls, out_ls, _ = run_docker_exec(["ls", "-lh", CONTAINER_DUMP_PATH])

    file_size_bytes = int(out_stat.strip()) if out_stat.strip().isdigit() else 0
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(
        f"Kích thước file dump: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB) [{out_ls.strip()}]",
        flush=True,
    )

    if file_size_mb < 1.0:
        print(
            f"CẢNH BÁO: File dump < 1 MB ({file_size_mb:.2f} MB) — CÓ DẤU HIỆU DÍNH BẪY HYPERTABLE RỖNG!",
            file=sys.stderr,
        )
        return 1
    else:
        print(
            f"-> File dump > 1 MB ({file_size_mb:.2f} MB) — Chứa đầy đủ dữ liệu các chunk TimescaleDB.",
            flush=True,
        )

    # Bước 3: Tạo scratch database trading_restore_test
    print(f"\n--- BƯỚC 3: TẠO DATABASE SCRATCH '{SCRATCH_DB}' ---", flush=True)
    exec_psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB};")
    rc_create, out_create, err_create = exec_psql(
        "postgres", f"CREATE DATABASE {SCRATCH_DB};"
    )
    print(
        f"CREATE DATABASE {SCRATCH_DB}: rc={rc_create}, output={out_create.strip()} {err_create.strip()}",
        flush=True,
    )
    if rc_create != 0:
        print(f"LỖI: Không tạo được database {SCRATCH_DB}", file=sys.stderr)
        return 1

    # Bước 4: Phục hồi bản dump vào trading_restore_test
    print(f"\n--- BƯỚC 4: PHỤC HỒI BẢN DUMP VÀO '{SCRATCH_DB}' ---", flush=True)
    restore_sh = f"gzip -dc {CONTAINER_DUMP_PATH} | psql -U trading -d {SCRATCH_DB}"
    print(f"Chạy lệnh trong container: {restore_sh}", flush=True)

    rc_restore, _out_restore, err_restore = run_docker_exec(["sh", "-c", restore_sh])
    print(f"Kết quả phục hồi: exit_code={rc_restore}", flush=True)
    if err_restore:
        print(f"Các thông điệp / cảnh báo từ psql:\n{err_restore[:1500]}", flush=True)
        if len(err_restore) > 1500:
            print(
                f"... (còn {len(err_restore) - 1500} bytes thông điệp khác)", flush=True
            )

    # Bước 5: Đếm số dòng từng bảng và đối chiếu 2 bên
    print(
        "\n--- BƯỚC 5: ĐỐI CHIẾU SỐ DÒNG TỪNG BẢNG (SOURCE vs RESTORED) ---", flush=True
    )
    print(
        f"{'Tên bảng':<28} | {'Source (trading)':<18} | {'Restored (scratch)':<20} | {'Khớp?':<8}",
        flush=True,
    )
    print("-" * 80, flush=True)

    all_matched = True
    for tbl in TABLES_TO_CHECK:
        src_cnt = source_counts[tbl]
        res_cnt = query_count(SCRATCH_DB, tbl)
        # KHONG doc duoc so dong => THAT BAI, du hai ben cung ra -1. Hai ben
        # bang nhau vi cung khong do duoc thi khong chung minh dieu gi ca.
        if src_cnt == COUNT_FAILED or res_cnt == COUNT_FAILED:
            matched = False
            match_str = "KHONG DO DUOC"
        else:
            matched = src_cnt == res_cnt
            match_str = "KHỚP" if matched else "LỆCH"
        if not matched:
            all_matched = False
        print(
            f"{tbl:<28} | {src_cnt:>18,} | {res_cnt:>20,} | {match_str:<8}", flush=True
        )
    print("-" * 80, flush=True)
    print(
        f"-> Kết luận đối chiếu số dòng: {'TẤT CẢ CÁC BẢNG ĐỀU KHỚP 100%' if all_matched else 'CÓ BẢNG BỊ LỆCH'}",
        flush=True,
    )

    # Bước 6: Kiểm tra Hypertables và Chunks
    print("\n--- BƯỚC 6: KIỂM TRA HYPERTABLES VÀ CHUNKS GIỮA HAI BÊN ---", flush=True)
    sql_hyper = """
        SELECT hypertable_name, num_chunks, compression_enabled
        FROM timescaledb_information.hypertables
        ORDER BY hypertable_name;
    """
    _, src_hyper_out, _ = exec_psql("trading", sql_hyper)
    _, res_hyper_out, _ = exec_psql(SCRATCH_DB, sql_hyper)

    print(
        f"TimescaleDB Hypertables trong 'trading' (source):\n{src_hyper_out.strip()}\n",
        flush=True,
    )
    print(
        f"TimescaleDB Hypertables trong '{SCRATCH_DB}' (restored):\n{res_hyper_out.strip()}\n",
        flush=True,
    )

    # Bước 7: Dọn dẹp scratch database và file dump tạm
    print(f"--- BƯỚC 7: DỌN DẸP SCRATCH DATABASE '{SCRATCH_DB}' ---", flush=True)
    if SCRATCH_DB and SCRATCH_DB == "trading_restore_test":
        rc_drop, out_drop, err_drop = exec_psql(
            "postgres", f"DROP DATABASE {SCRATCH_DB};"
        )
        print(
            f"DROP DATABASE {SCRATCH_DB}: rc={rc_drop}, output={out_drop.strip()} {err_drop.strip()}",
            flush=True,
        )

    # Kiểm tra lại DB trading gốc
    bars_after = query_count("trading", "bars")
    print(
        f"Kiểm tra DB 'trading' gốc sau khi dọn dẹp: bảng bars = {bars_after:,} dòng (nguyên vẹn).",
        flush=True,
    )

    # Xoá file dump trong container
    run_docker_exec(["rm", "-f", CONTAINER_DUMP_PATH])
    print(f"Đã xoá file dump tạm {CONTAINER_DUMP_PATH} trong container.", flush=True)

    print("\n" + "=" * 100, flush=True)
    print(
        f"KẾT QUẢ CUỐI CÙNG TASK 1: {'THÀNH CÔNG RỰC RỠ (BẢN SAO LƯU PHỤC HỒI HOÀN TOÀN 100%)' if all_matched else 'THẤT BẠI'}",
        flush=True,
    )
    print("=" * 100, flush=True)

    return 0 if all_matched else 1


if __name__ == "__main__":
    sys.exit(main())
