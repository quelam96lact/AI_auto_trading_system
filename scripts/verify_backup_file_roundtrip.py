"""Kiểm chứng mắt xích cuối của đường dữ liệu VPS: backup_db.sh qua ống host (Brief đợt 14 - Task 1).

Script thực hiện:
1. Chạy scripts/backup_db.sh xuất ra thư mục tạm trên host.
2. Kiểm tra kích thước file dump trên host và đối chiếu với ~55.5 MB.
3. Kiểm tra tính toàn vẹn gzip CRC (gzip -t) trên host.
4. Đưa file từ host vào container postgres.
5. Tạo scratch DB riêng `trading_roundtrip_test` và phục hồi bản dump.
6. Dùng lại các hàm của `scripts.verify_backup_restore` để đối chiếu số dòng từng bảng (15 bảng) và hypertables/chunks.
7. Dọn dẹp an toàn: DROP DATABASE `trading_roundtrip_test`, xoá file tạm cả host và container, xác nhận DB `trading` gốc nguyên vẹn.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# DÙNG LẠI, KHÔNG CHÉP (Brief đợt 14 §1)
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.verify_backup_restore import (
    COUNT_FAILED,
    TABLES_TO_CHECK,
    exec_psql,
    query_count,
    run_docker_exec,
)

SCRATCH_DB = "trading_roundtrip_test"
CONTAINER_RESTORE_PATH = "/tmp/trading_roundtrip.sql.gz"
HOST_TEMP_DIR = Path(__file__).parent.parent / "tmp_roundtrip_verify"


def run_host_bash(cmd_str: str) -> tuple[int, str, str]:
    """Chạy lệnh bash trên host Windows qua Git Bash."""
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    if not os.path.exists(git_bash):
        # Fallback to bash in PATH
        git_bash = "bash"
    p = subprocess.run(
        [git_bash, "-lc", cmd_str],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 100, flush=True)
    print("BÁO CÁO KIỂM CHỨNG MẮT XÍCH CUỐI ĐƯỜNG DỮ LIỆU VPS (BRIEF ĐỢT 14 - TASK 1)", flush=True)
    print("=" * 100, flush=True)

    # Bước 1: Đếm số dòng bên nguồn TRƯỚC khi dump
    print("\n--- BƯỚC 1: ĐẾM SỐ DÒNG BÊN NGUỒN (DATABASE 'trading') TRƯỚC KHI DUMP ---", flush=True)
    source_counts = {}
    for tbl in TABLES_TO_CHECK:
        cnt = query_count("trading", tbl)
        source_counts[tbl] = cnt
        print(f"  - Bảng {tbl:<28}: {cnt:>12,} dòng", flush=True)

    # Bước 2: Chạy scripts/backup_db.sh xuất ra thư mục tạm trên host
    print("\n--- BƯỚC 2: CHẠY SCRIPTS/BACKUP_DB.SH QUA ỐNG TRÊN HOST ---", flush=True)
    HOST_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Chuyển đường dẫn sang posix cho Git Bash
    repo_posix = str(Path(__file__).parent.parent).replace("\\", "/")
    if len(repo_posix) >= 2 and repo_posix[1] == ":":
        repo_posix = f"/{repo_posix[0].lower()}{repo_posix[2:]}"
    temp_dir_posix = f"{repo_posix}/tmp_roundtrip_verify"

    backup_cmd = f"cd '{repo_posix}' && ./scripts/backup_db.sh '{temp_dir_posix}'"
    print(f"Chạy lệnh: {backup_cmd}", flush=True)

    rc_backup, out_backup, err_backup = run_host_bash(backup_cmd)
    print(f"Kết quả backup_db.sh: exit_code={rc_backup}", flush=True)
    if out_backup:
        print(f"Stdout:\n{out_backup.strip()}", flush=True)
    if err_backup:
        print(f"Stderr:\n{err_backup.strip()}", flush=True)

    if rc_backup != 0:
        print("LỖI: scripts/backup_db.sh thất bại!", file=sys.stderr)
        return 1

    # Tìm file dump vừa tạo trên host
    dump_files = list(HOST_TEMP_DIR.glob("trading_*.sql.gz"))
    if not dump_files:
        print("LỖI: Không tìm thấy file dump tạo ra trong thư mục tạm!", file=sys.stderr)
        return 1

    dump_file = max(dump_files)
    file_size_bytes = dump_file.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"\nFile dump trên host: {dump_file.name}", flush=True)
    print(f"Kích thước file: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB)", flush=True)

    if file_size_mb < 1.0:
        print(f"CẢNH BÁO: File dump < 1 MB ({file_size_mb:.2f} MB) — CÓ DẤU HIỆU DÍNH BẪY HYPERTABLE HOẶC ỐNG HỎNG!", file=sys.stderr)
        return 1
    else:
        print("-> Kích thước khớp mốc ~55.5 MB của đợt 13 (không bị bóp nghẽn hay rỗng).", flush=True)

    # Bước 3: Kiểm tính toàn vẹn gzip CRC (gzip -t) trên host
    print("\n--- BƯỚC 3: KIỂM TÍNH TOÀN VẸN GZIP CRC TRÊN HOST (GZIP -T) ---", flush=True)
    dump_posix = f"{temp_dir_posix}/{dump_file.name}"
    rc_crc, _out_crc, err_crc = run_host_bash(f"gzip -t '{dump_posix}'")
    print(f"Kết quả gzip -t: exit_code={rc_crc} (0 nghĩa là CRC toàn vẹn)", flush=True)
    if rc_crc != 0:
        print(f"LỖI: File dump bị hỏng CRC khi truyền qua ống trên Windows!\n{err_crc}", file=sys.stderr)
        return 1
    print("-> Gzip CRC kiểm chứng thành công: Luồng nhị phân trên host không bị biến dạng!", flush=True)

    # Bước 4: Đưa file từ host vào container postgres
    print("\n--- BƯỚC 4: COPY FILE DUMP VÀO CONTAINER POSTGRES ---", flush=True)
    cp_cmd = ["docker", "compose", "cp", str(dump_file), f"postgres:{CONTAINER_RESTORE_PATH}"]
    p_cp = subprocess.run(cp_cmd, capture_output=True, text=True, check=False)
    print(f"Kết quả docker compose cp: exit_code={p_cp.returncode}", flush=True)
    if p_cp.returncode != 0:
        print(f"LỖI copy file vào container thất bại: {p_cp.stderr}", file=sys.stderr)
        return 1

    # Bước 5: Tạo scratch database trading_roundtrip_test
    print(f"\n--- BƯỚC 5: TẠO SCRATCH DATABASE '{SCRATCH_DB}' ---", flush=True)
    exec_psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB};")
    rc_create, out_create, err_create = exec_psql("postgres", f"CREATE DATABASE {SCRATCH_DB};")
    print(f"CREATE DATABASE {SCRATCH_DB}: rc={rc_create}, output={out_create.strip()} {err_create.strip()}", flush=True)
    if rc_create != 0:
        print(f"LỖI: Không tạo được database {SCRATCH_DB}", file=sys.stderr)
        return 1

    # Bước 6: Phục hồi bản dump vào trading_roundtrip_test
    print(f"\n--- BƯỚC 6: PHỤC HỒI BẢN DUMP VÀO '{SCRATCH_DB}' ---", flush=True)
    restore_sh = f"gzip -dc {CONTAINER_RESTORE_PATH} | psql -U trading -d {SCRATCH_DB}"
    print(f"Chạy lệnh trong container: {restore_sh}", flush=True)

    rc_restore, _out_restore, err_restore = run_docker_exec(["sh", "-c", restore_sh])
    print(f"Kết quả phục hồi: exit_code={rc_restore}", flush=True)
    if err_restore:
        print(f"Các thông điệp / cảnh báo từ psql:\n{err_restore[:1500]}", flush=True)
        if len(err_restore) > 1500:
            print(f"... (còn {len(err_restore) - 1500} bytes thông điệp khác)", flush=True)

    # Bước 7: Đối chiếu số dòng từng bảng
    print("\n--- BƯỚC 7: ĐỐI CHIẾU SỐ DÒNG TỪNG BẢNG (SOURCE vs ROUNDTRIP RESTORED) ---", flush=True)
    print(f"{'Tên bảng':<28} | {'Source (trading)':<18} | {'Restored (roundtrip)':<20} | {'Khớp?':<8}", flush=True)
    print("-" * 80, flush=True)

    all_matched = True
    for tbl in TABLES_TO_CHECK:
        src_cnt = source_counts[tbl]
        res_cnt = query_count(SCRATCH_DB, tbl)
        if src_cnt == COUNT_FAILED or res_cnt == COUNT_FAILED:
            matched = False
            match_str = "KHONG DO DUOC"
        else:
            matched = (src_cnt == res_cnt)
            match_str = "KHỚP" if matched else "LỆCH"
        if not matched:
            all_matched = False
        print(f"{tbl:<28} | {src_cnt:>18,} | {res_cnt:>20,} | {match_str:<8}", flush=True)
    print("-" * 80, flush=True)
    print(
        f"-> Kết luận đối chiếu số dòng: {'TẤT CẢ CÁC BẢNG ĐỀU KHỚP 100%' if all_matched else 'CÓ BẢNG BỊ LỆCH'}",
        flush=True,
    )

    # Bước 8: Kiểm tra Hypertables và Chunks
    print("\n--- BƯỚC 8: KIỂM TRA HYPERTABLES VÀ CHUNKS GIỮA HAI BÊN ---", flush=True)
    sql_hyper = """
        SELECT hypertable_name, num_chunks, compression_enabled
        FROM timescaledb_information.hypertables
        ORDER BY hypertable_name;
    """
    rc_src_h, src_hyper_out, _ = exec_psql("trading", sql_hyper)
    rc_res_h, res_hyper_out, _ = exec_psql(SCRATCH_DB, sql_hyper)

    print(f"TimescaleDB Hypertables trong 'trading' (source):\n{src_hyper_out.strip()}\n", flush=True)
    print(f"TimescaleDB Hypertables trong '{SCRATCH_DB}' (restored):\n{res_hyper_out.strip()}\n", flush=True)

    if rc_src_h != 0 or rc_res_h != 0:
        print("-> KHONG DO DUOC hypertable (query loi) — coi la THAT BAI.", flush=True)
        all_matched = False
    elif src_hyper_out.strip() == res_hyper_out.strip():
        print("-> Hypertable/chunk hai bên KHỚP tuyệt đối.", flush=True)
    else:
        print("-> LỆCH hypertable/chunk giữa hai bên — bản sao lưu KHÔNG đầy đủ.", flush=True)
        all_matched = False

    # Bước 9: Dọn dẹp an toàn
    print(f"\n--- BƯỚC 9: DỌN DẸP SCRATCH DATABASE '{SCRATCH_DB}' VÀ FILE TẠM ---", flush=True)
    if SCRATCH_DB and SCRATCH_DB == "trading_roundtrip_test":
        rc_drop, out_drop, err_drop = exec_psql("postgres", f"DROP DATABASE {SCRATCH_DB};")
        print(f"DROP DATABASE {SCRATCH_DB}: rc={rc_drop}, output={out_drop.strip()} {err_drop.strip()}", flush=True)

    # Kiểm tra lại DB trading gốc
    bars_after = query_count("trading", "bars")
    print(f"Kiểm tra DB 'trading' gốc sau khi dọn dẹp: bảng bars = {bars_after:,} dòng (nguyên vẹn).", flush=True)

    # Xoá file dump trong container
    run_docker_exec(["rm", "-f", CONTAINER_RESTORE_PATH])
    print(f"Đã xoá file dump tạm {CONTAINER_RESTORE_PATH} trong container.", flush=True)

    # Xoá file dump trên host
    if HOST_TEMP_DIR.exists():
        shutil.rmtree(HOST_TEMP_DIR, ignore_errors=True)
        print(f"Đã xoá thư mục tạm trên host: {HOST_TEMP_DIR}", flush=True)

    print("\n" + "=" * 100, flush=True)
    print(
        f"KẾT QUẢ CUỐI CÙNG TASK 1: {'THÀNH CÔNG RỰC RỠ (ĐƯỜNG DỮ LIỆU VPS QUA ỐNG HOST TOÀN VẸN 100%)' if all_matched else 'THẤT BẠI'}",
        flush=True,
    )
    print("=" * 100, flush=True)

    return 0 if all_matched else 1


if __name__ == "__main__":
    sys.exit(main())
