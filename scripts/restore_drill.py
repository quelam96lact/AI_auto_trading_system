"""Diễn tập phục hồi THẬT bản sao lưu DB mới nhất (brief đợt 136, sửa ở đợt 137).

Vì sao có job này: `backup-check` gọi `pg_restore -l` rồi coi là "đã kiểm toàn vẹn", nhưng
`pg_restore -l` chỉ đọc MỤC LỤC ở đầu file, không đọc dữ liệu. Đo thật 30/09 trên bản dump đã
cắt còn 90%: `pg_restore -l` exit 0 (đúng 3.224 dòng mục lục), ngưỡng kích thước 80 MB qua,
`evaluate_backup_health` trả `[]` — nhưng phục hồi thật exit 1 (`could not read from input file:
end of file`). Bản phục hồi dở dang lại TRÔNG gần đủ (`bars` 99,99%) trong khi `orders` = 0.
Nên: (1) chỉ phục hồi thật mới bắt được lỗi này; (2) đếm "> 0" trên vài bảng lớn vẫn mù, phải
đối chiếu TỪNG bảng.

SO VỚI CÁI GÌ — bản kê số dòng lúc dump, KHÔNG so với nguồn đang sống (đợt 137): lần diễn tập thật
đầu tiên (30/09 20:09, trên bản dump TỐT, 18 giờ sau khi dump) báo 6 bảng snapshot tài khoản chỉ
còn ~96,5% so với nguồn (`account_nav_snapshot` nguồn=11.407, phục hồi=11.013) vì các bảng đó ghi
24/7 (22 dòng/giờ). So với nguồn sống thì kết quả phụ thuộc giờ chạy (chạy bù trễ vài giờ là báo
oan), còn băng 1% trên bảng lớn lại để lọt mất mát dưới 1% (`bars`: ~9.000 dòng). Nên `backup_db.sh`
ghi bản kê `trading_<ts>.counts` NGAY TRƯỚC `pg_dump`, cạnh file `.dump`; script này đọc bản kê
CÙNG TÊN GỐC và so `phục_hồi >= bản_kê` — không có băng dung sai.

Vì sao `>=` đúng: bản kê chụp TRƯỚC snapshot của `pg_dump`, nên trong mấy giây giữa hai mốc chỉ có
dòng được THÊM; bản phục hồi chỉ có thể nhiều hơn hoặc bằng. Tiền đề "không job định kỳ nào xoá
dòng" đã đo lại 30/09: `timescaledb_information.jobs` chỉ có `policy_telemetry` và
`policy_job_stat_history_retention` (không retention trên bảng dữ liệu, không có pg_cron); `DELETE`
trong code chỉ nằm ở script chạy tay (`merge_bars_daily_chunks.py`,
`build_derivative_continuous_series.py`, `.probe_event_loop_block.py`). Nếu sau này có job định kỳ
xoá dòng thì quy tắc này sẽ báo oan — khi đó phải xem lại tiền đề, đừng tự nới dung sai.

Không có bản kê (hoặc đọc không được, có dòng hỏng) -> CRITICAL. TUYỆT ĐỐI KHÔNG rơi về so với
nguồn sống: đường lui đó chính là lỗi đã sửa và sẽ lặng lẽ bật lại. Diễn tập cũng không còn đếm
số dòng trên database `trading` nữa; chỉ kiểm `trading` vẫn tồn tại sau khi dọn.

Các bước (dừng và cảnh báo ngay khi một bước hỏng): tìm dump mới nhất + bản kê cùng tên gốc ->
kiểm đĩa (>= 3x dump) -> tạo DB nháp -> CREATE EXTENSION timescaledb / pre_restore / pg_restore
--no-owner / post_restore -> phán xử mã thoát VÀ stderr -> so TẬP BẢNG (lấy từ bản kê, không danh
sách viết cứng) -> so số dòng từng bảng -> dọn trong `finally` và kiểm chứng đã dọn.

Mã thoát (họ "theo gửi được hay không", như backup_check.py — xem docstring _alert_common.py):
  0: sạch.
  1: có cảnh báo và đã gửi thành công (hoặc in ra khi --dry-run).
  2: sai cấu hình (vd tên DB đích là `trading`), hoặc cảnh báo cần gửi mà gửi hỏng.

An toàn: script này tạo và XOÁ một database nháp; tên DB đích bị chốt cứng — `trading`, rỗng
hoặc DB hệ thống là thoát mã 2 ngay, trước mọi lệnh.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from trading.alerts import _print_safe
from trading.telegram import send_telegram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BACKUP_DIR = os.environ.get("TRADING_BACKUP_DIR") or "/var/backups/trading-db"
DEFAULT_TARGET_DB = "trading_restore_drill"
SOURCE_DB = "trading"
PROTECTED_DBS = frozenset({"", SOURCE_DB, "postgres", "template0", "template1"})
CONTAINER_DUMP_PATH = "/tmp/restore_drill.dump"
MIN_FREE_FACTOR = 3  # cần trống >= 3x kích thước dump

#: Không đọc được số dòng. Phải coi là THẤT BẠI, không bao giờ là "khớp": -1 == -1 là "hai bên
#: cùng không đo được", không phải "hai bên giống nhau" (cùng nguyên tắc với COUNT_FAILED của
#: verify_backup_restore.py, nơi `daily_pnl` viết sai tên làm hai bên cùng ra -1 mà bị tính khớp).
COUNT_FAILED = -1

Runner = Callable[[list[str]], tuple[int, str, str]]


class ConfigError(Exception):
    pass


class CountsError(Exception):
    """Không có bản kê số dòng, hoặc bản kê hỏng."""


def guard_target_db(name: str) -> None:
    """Chốt cứng: tên DB đích rơi vào `trading`/rỗng/DB hệ thống thì từ chối."""
    if name.strip().lower() in PROTECTED_DBS:
        raise ConfigError(
            f"tên database đích bị cấm: {name!r} (script này tạo và XOÁ database đích)"
        )


# ---------------------------------------------------------------- bản kê
_COUNT_LINE = re.compile(r"^([^\t]+)\t(\d+)$")


def counts_path(dump: Path) -> Path:
    """Bản kê nằm cạnh dump, CÙNG TÊN GỐC: trading_<ts>.dump -> trading_<ts>.counts."""
    return dump.with_suffix(".counts")


def read_counts_file(dump: Path) -> dict[str, int]:
    """Đọc bản kê `ten_bang<TAB>so_dong`. Thiếu file, rỗng hoặc có dòng hỏng -> CountsError.

    Dòng hỏng KHÔNG được bỏ qua: bỏ qua nghĩa là bảng đó lặng lẽ không được kiểm."""
    path = counts_path(dump)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise CountsError(
            f"không có bản kê số dòng cho {dump.name} (cần {path.name}): {type(e).__name__}"
        ) from e
    counts: dict[str, int] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        m = _COUNT_LINE.match(line)
        if not m:
            raise CountsError(f"bản kê {path.name} dòng {n} hỏng (cần 'ten<TAB>so'): {line!r}")
        counts[m.group(1)] = int(m.group(2))
    if not counts:
        raise CountsError(f"bản kê {path.name} rỗng (không có bảng nào)")
    return counts


# ---------------------------------------------------------------- phán xử (thuần)
def judge_pg_restore(rc: int, stderr: str) -> list[str]:
    """Mã thoát VÀ stderr. Cảnh báo `continuous_agg` (circular foreign-key constraints) là
    vô hại (DEPLOYMENT.md, mục "Cảnh báo continuous_agg") và không chứa `error:` nên không bị
    bắt; chỉ dòng `error:` mới bị coi là lỗi ở nhánh exit 0. Mã khác 0 luôn là lỗi dù stderr
    rỗng (vd 137 = bị giết vì hết bộ nhớ)."""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    errors = [ln for ln in lines if re.search(r"\berror:", ln, re.IGNORECASE)]
    if rc != 0:
        first = errors[0] if errors else (lines[0] if lines else f"exit code {rc}")
        return [f"[CRITICAL] pg_restore thất bại (exit {rc}): {first}"]
    if errors:
        return [f"[CRITICAL] pg_restore exit 0 nhưng stderr có lỗi: {errors[0]}"]
    return []


def judge_tables(source: set[str], restored: set[str]) -> list[str]:
    if not source:
        return ["[CRITICAL] Bản kê không liệt kê bảng nào"]
    missing = sorted(source - restored)
    if missing:
        return [f"[CRITICAL] Bản phục hồi thiếu bảng có trong bản kê: {', '.join(missing)}"]
    return []


def judge_counts(source: dict[str, int], restored: dict[str, int]) -> list[str]:
    """`phục_hồi >= bản_kê`, không dung sai (xem docstring đầu file)."""
    alerts = []
    for table in sorted(set(source) & set(restored)):
        s, r = source[table], restored[table]
        if s == COUNT_FAILED or r == COUNT_FAILED:
            alerts.append(
                f"[CRITICAL] Không đọc được số dòng bảng {table} (bản kê={s}, phục hồi={r}): "
                "hai bên cùng không đo được KHÔNG phải là khớp"
            )
        elif r < s:
            alerts.append(
                f"[CRITICAL] Bảng {table} phục hồi thiếu dòng: bản kê={s:,}, phục hồi={r:,} "
                f"(thiếu {s - r:,})"
            )
    return alerts


# ---------------------------------------------------------------- chạy lệnh
def default_runner(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
    return p.returncode, p.stdout, p.stderr


def _exec(*args: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", "postgres", *args]


def _psql(db: str, sql: str) -> list[str]:
    return _exec("psql", "-U", SOURCE_DB, "-d", db, "-v", "ON_ERROR_STOP=1", "-Atc", sql)


#: Cùng truy vấn với bản kê của `backup_db.sh` (liệt kê từ catalog, không danh sách viết cứng).
LIST_TABLES_SQL = (
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') ORDER BY 1"
)


def _list_tables(runner: Runner, db: str) -> set[str]:
    rc, out, _ = runner(_psql(db, LIST_TABLES_SQL))
    if rc != 0:
        return set()
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def _count(runner: Runner, db: str, table: str) -> int:
    rc, out, _ = runner(_psql(db, f'SELECT count(*) FROM public."{table}"'))
    if rc != 0:
        return COUNT_FAILED
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.isdigit():
            return int(ln)
    return COUNT_FAILED


def find_latest_dump(backup_dir: Path) -> Path | None:
    if not backup_dir.is_dir():
        return None
    files = [f for f in backup_dir.glob("trading_*.dump") if f.is_file()]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def _cleanup(runner: Runner, target_db: str) -> list[str]:
    alerts = []
    for cmd in (
        _exec("rm", "-f", CONTAINER_DUMP_PATH),
        _psql("postgres", f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)'),
    ):
        try:
            rc, _, err = runner(cmd)
            if rc != 0:
                alerts.append(
                    f"[CRITICAL] Dọn dẹp thất bại ({' '.join(cmd[-2:])[:60]}): {err.strip()[:200]}"
                )
        except Exception as e:
            alerts.append(f"[CRITICAL] Dọn dẹp ném ngoại lệ {type(e).__name__}: {e}")
    try:
        rc, out, _ = runner(_psql("postgres", "SELECT datname FROM pg_database"))
        names = {ln.strip() for ln in out.splitlines() if ln.strip()} if rc == 0 else None
    except Exception:
        names = None
    if names is None:
        alerts.append("[CRITICAL] Không kiểm chứng được việc dọn dẹp (không liệt kê được database)")
    else:
        if target_db in names:
            alerts.append(
                f"[CRITICAL] Database nháp {target_db} vẫn còn sau khi dọn — đang chiếm đĩa"
            )
        if SOURCE_DB not in names:
            alerts.append(f"[CRITICAL] Database {SOURCE_DB} KHÔNG còn trong danh sách sau diễn tập")
    return alerts


def _drill_steps(
    dump: Path, source_counts: dict[str, int], target_db: str, runner: Runner
) -> list[str]:
    """Các bước có thể hỏng giữa chừng. Trả về cảnh báo; dọn dẹp do người gọi lo."""
    steps = [
        (
            "xoá DB nháp cũ",
            _psql("postgres", f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)'),
        ),
        ("tạo DB nháp", _psql("postgres", f'CREATE DATABASE "{target_db}"')),
        (
            "chép dump vào container",
            ["docker", "compose", "cp", str(dump), f"postgres:{CONTAINER_DUMP_PATH}"],
        ),
        (
            "CREATE EXTENSION timescaledb",
            _psql(target_db, "CREATE EXTENSION IF NOT EXISTS timescaledb"),
        ),
        ("timescaledb_pre_restore", _psql(target_db, "SELECT timescaledb_pre_restore()")),
    ]
    for label, cmd in steps:
        rc, _, err = runner(cmd)
        if rc != 0:
            return [f"[CRITICAL] Bước '{label}' thất bại: {err.strip()[:300]}"]

    rc, _, err = runner(
        _exec("pg_restore", "-U", SOURCE_DB, "-d", target_db, "--no-owner", CONTAINER_DUMP_PATH)
    )
    alerts = judge_pg_restore(rc, err)
    if alerts:
        return alerts

    rc, _, err = runner(_psql(target_db, "SELECT timescaledb_post_restore()"))
    if rc != 0:
        return [f"[CRITICAL] Bước 'timescaledb_post_restore' thất bại: {err.strip()[:300]}"]

    res_tables = _list_tables(runner, target_db)
    alerts = judge_tables(set(source_counts), res_tables)
    common = sorted(set(source_counts) & res_tables)
    res_counts = {t: _count(runner, target_db, t) for t in common}
    alerts += judge_counts({t: source_counts[t] for t in common}, res_counts)
    if not alerts:
        _print_safe(f"Diễn tập OK: {dump.name}, {len(common)} bảng >= bản kê lúc dump")
        for t in common:
            _print_safe(f"  {t}: bản kê={source_counts[t]:,} phục hồi={res_counts[t]:,}")
    return alerts


def run_drill(
    backup_dir: Path,
    target_db: str,
    runner: Runner,
    free_bytes: Callable[[], int],
) -> list[str]:
    guard_target_db(target_db)

    dump = find_latest_dump(backup_dir)
    if dump is None:
        return [f"[CRITICAL] Không tìm thấy bản dump DB nào trong {backup_dir} để diễn tập"]

    # Bản kê phải đọc được TRƯỚC khi đụng vào DB, và KHÔNG có đường lui về nguồn sống.
    try:
        source_counts = read_counts_file(dump)
    except CountsError as e:
        return [f"[CRITICAL] {e}"]

    size = dump.stat().st_size
    need = MIN_FREE_FACTOR * size
    free = free_bytes()
    if free < need:
        msg = (
            f"[CRITICAL] Không đủ đĩa để diễn tập: cần {need} byte ({MIN_FREE_FACTOR}x dump {size} byte), "
            f"còn trống {free} byte — không chạy tiếp"
        )
        return [msg]

    try:
        alerts = _drill_steps(dump, source_counts, target_db, runner)
    except Exception as e:
        alerts = [f"[CRITICAL] Diễn tập ném ngoại lệ {type(e).__name__}: {e}"]
    finally:
        # Dọn dù các bước trên hỏng hay ném ngoại lệ, rồi kiểm chứng đã dọn.
        cleanup_alerts = _cleanup(runner, target_db)
    return alerts + cleanup_alerts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diễn tập phục hồi thật bản sao lưu DB mới nhất.")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--target-db", default=DEFAULT_TARGET_DB)
    parser.add_argument("--dry-run", action="store_true", help="In thay vì gửi Telegram")
    args = parser.parse_args(argv)

    try:
        guard_target_db(args.target_db)
    except ConfigError as e:
        _print_safe(f"LỖI CẤU HÌNH: {e}")
        return 2

    repo = Path(__file__).resolve().parent.parent
    alerts = run_drill(
        backup_dir=Path(args.backup_dir),
        target_db=args.target_db,
        runner=default_runner,
        free_bytes=lambda: shutil.disk_usage(repo).free,
    )
    if not alerts:
        return 0
    msg = "\n".join(alerts)
    _print_safe(msg)
    if args.dry_run:
        _print_safe("[DRY-RUN] Không gửi Telegram thật.")
        return 1
    try:
        sent = send_telegram(msg)
    except Exception as e:
        _print_safe(f"LỖI: send_telegram ném {type(e).__name__}: {e}")
        return 2
    if sent:
        return 1
    _print_safe("LỖI: Cảnh báo cần gửi nhưng send_telegram trả về thất bại!")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
