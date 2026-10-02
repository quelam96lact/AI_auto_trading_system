"""Tests cho Brief 142 — Giám sát các job theo lịch 24/7 và giám sát heartbeat chéo.

Bao gồm:
- Kiểm tra tính đầy đủ của SCHEDULE_WATCH_JOBS và KHONG_CANH so với scripts/sched.sh.
- Kiểm tra hàm thuần evaluate_schedule_health:
  + job vừa chạy -> im;
  + quá ngưỡng 1 phút -> báo;
  + đang ngừng và lần trước đã báo -> im (không lặp);
  + chạy lại -> báo hồi phục một lần;
  + log có dòng SKIP: docker chua chay mới -> coi là còn chạy;
  + không có file log -> báo ngừng;
  + file trạng thái hỏng -> không chết và không nuốt job đang ngừng.
- Kiểm tra Việc 3 (evaluate_heartbeat_watch):
  + lúc 10:00 ngày giao dịch, cũ 16 phút -> báo;
  + lúc 10:00 Chủ nhật -> im;
  + lúc 07:00 ngày giao dịch -> im.
- Tái hiện sự cố thật ngày 02/10 với nguyên văn dòng log container-health lúc now = 10:20.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from scripts.container_health_check import evaluate_heartbeat_watch
from scripts.heartbeat_check import (
    KHONG_CANH,
    SCHEDULE_WATCH_JOBS,
    build_parser,
    evaluate_schedule_health,
    get_last_called_timestamp,
    load_schedule_state,
)
from trading.calendar_vn import TZ

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHED_SH = REPO_ROOT / "scripts" / "sched.sh"


def extract_sched_branches(sched_sh_path: Path) -> set[str]:
    """Trích xuất danh sách tất cả các tên nhánh trong lệnh case của sched.sh."""
    content = sched_sh_path.read_text(encoding="utf-8")
    m = re.search(r'case\s+["\']?\$\{1:-[^\n]*\s+in(.*?)esac', content, re.DOTALL)
    if not m:
        raise ValueError("Không tìm thấy khối case ${1:-} in trong sched.sh")
    case_body = m.group(1)
    branches = set()
    for line in case_body.splitlines():
        line = line.strip()
        # Nhánh có dạng `tên_nhánh)` nhưng loại trừ nhánh mặc định `*)`
        branch_match = re.match(r"^([a-zA-Z0-9_-]+)\)", line)
        if branch_match:
            name = branch_match.group(1)
            if name != "*":
                branches.add(name)
    return branches


def test_sched_branches_covered_in_watch_or_khong_canh():
    """Mọi nhánh trong sched.sh phải nằm trong SCHEDULE_WATCH_JOBS hoặc KHONG_CANH (không sót, không trùng)."""
    sched_branches = extract_sched_branches(SCHED_SH)
    assert len(sched_branches) == 16, f"Kỳ vọng 16 nhánh trong sched.sh, thực tế có {len(sched_branches)}: {sched_branches}"

    watch_branches = set(SCHEDULE_WATCH_JOBS.keys())
    skip_branches = set(KHONG_CANH.keys())

    # Không được có nhánh nào nằm ở cả 2 danh sách
    overlap = watch_branches & skip_branches
    assert not overlap, f"Các nhánh sau bị trùng ở cả SCHEDULE_WATCH_JOBS và KHONG_CANH: {overlap}"

    # Tổng 2 danh sách phải đúng bằng tập các nhánh trong sched.sh
    covered = watch_branches | skip_branches
    missing = sched_branches - covered
    assert not missing, f"Các nhánh trong sched.sh chưa được phân loại vào SCHEDULE_WATCH_JOBS hoặc KHONG_CANH: {missing}"

    extra = covered - sched_branches
    assert not extra, f"Có nhánh dư thừa không tồn tại trong sched.sh: {extra}"


def test_job_vua_chay_thi_im():
    """Job vừa chạy gần đây (trong ngưỡng) -> trạng thái 'ok', không sinh cảnh báo."""
    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    last_seen = now - timedelta(minutes=5)  # 5 phút trước, ngưỡng là 25 phút
    job_last_seen = {"container-health": (last_seen, None)}

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen, now, {}, watch_jobs={"container-health": SCHEDULE_WATCH_JOBS["container-health"]}
    )
    assert alerts == []
    assert new_state["container-health"]["status"] == "ok"
    assert new_state["container-health"]["last_called"] == last_seen.strftime("%Y-%m-%d %H:%M:%S")


def test_qua_nguong_1_phut_thi_bao():
    """Job quá ngưỡng 1 phút -> chuyển sang 'stale' và sinh cảnh báo CRITICAL."""
    cfg = SCHEDULE_WATCH_JOBS["container-health"]
    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    # Ngưỡng 25 phút = 1500s. Quá 1 phút = 26 phút = 1560s.
    last_seen = now - timedelta(seconds=cfg.max_age_seconds + 60)
    job_last_seen = {"container-health": (last_seen, None)}

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen, now, {}, watch_jobs={"container-health": cfg}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'container-health' NGỪNG CHẠY" in alerts[0]
    assert new_state["container-health"]["status"] == "stale"


def test_dang_ngung_va_lan_truoc_da_bao_thi_im_khong_lap():
    """Job vẫn đang ngừng nhưng lần trước đã ở trạng thái 'stale' -> im lặng (không lặp lại cảnh báo)."""
    cfg = SCHEDULE_WATCH_JOBS["container-health"]
    now = datetime(2026, 10, 2, 10, 5, 0, tzinfo=TZ)
    last_seen = now - timedelta(minutes=35)

    prev_state = {
        "container-health": {
            "status": "stale",
            "last_called": last_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "checked_at": "2026-10-02 10:00:00",
        }
    }
    job_last_seen = {"container-health": (last_seen, None)}

    alerts, new_state, info_logs = evaluate_schedule_health(
        job_last_seen, now, prev_state, watch_jobs={"container-health": cfg}
    )
    assert alerts == [], f"Kỳ vọng im lặng không spam, nhưng nhận được: {alerts}"
    assert new_state["container-health"]["status"] == "stale"
    assert any("vẫn ngừng chạy" in log for log in info_logs)


def test_chay_lai_bao_hoi_phuc_mot_lan():
    """Job từ 'stale' chạy lại thành 'ok' -> sinh cảnh báo INFO hồi phục đúng một lần."""
    cfg = SCHEDULE_WATCH_JOBS["container-health"]
    now = datetime(2026, 10, 2, 10, 10, 0, tzinfo=TZ)
    last_seen = now - timedelta(minutes=2)  # Mới chạy lại 2 phút trước

    prev_state = {
        "container-health": {
            "status": "stale",
            "last_called": "2026-10-02 09:30:00",
            "checked_at": "2026-10-02 10:05:00",
        }
    }
    job_last_seen = {"container-health": (last_seen, None)}

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen, now, prev_state, watch_jobs={"container-health": cfg}
    )
    assert len(alerts) == 1
    assert "[INFO] job theo lịch 'container-health' ĐÃ CHẠY LẠI" in alerts[0]
    assert new_state["container-health"]["status"] == "ok"


def test_log_chi_co_dong_skip_docker_chua_chay_moi_coi_la_con_chay(tmp_path: Path):
    """Dòng SKIP do run_if_docker_up.sh sinh ra vẫn chứng minh bộ lập lịch hoạt động -> tính là còn chạy."""
    log_file = tmp_path / "container-health.log"
    log_file.write_text("2026-10-02 09:55:00 container-health SKIP: docker chua chay\n", encoding="utf-8")

    dt, err = get_last_called_timestamp(str(log_file), "container-health")
    assert err is None
    assert dt == datetime(2026, 10, 2, 9, 55, 0, tzinfo=TZ)

    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {"container-health": (dt, err)}, now, {}, watch_jobs={"container-health": SCHEDULE_WATCH_JOBS["container-health"]}
    )
    assert alerts == []
    assert new_state["container-health"]["status"] == "ok"


def test_khong_co_file_log_bao_ngung():
    """Không tìm thấy file log -> coi là 'stale' và báo lỗi nêu rõ lý do."""
    fake_path = "D:/duong/dan/khong/ton/tai/test.log"
    dt, err = get_last_called_timestamp(fake_path, "container-health")
    assert dt is None
    assert "không tồn tại" in err

    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {"container-health": (dt, err)}, now, {}, watch_jobs={"container-health": SCHEDULE_WATCH_JOBS["container-health"]}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'container-health' NGỪNG CHẠY" in alerts[0]
    assert "không tồn tại" in alerts[0]
    assert new_state["container-health"]["status"] == "stale"


def test_file_trang_thai_hong_khong_chet_va_khong_nuot_job_dang_ngung(tmp_path: Path):
    """File trạng thái JSON bị hỏng -> không crash, trả về {} và KHÔNG im lặng nuốt job đang ngừng."""
    corrupted_file = tmp_path / ".schedule_health_state.json"
    corrupted_file.write_text("{ corrupted json content [][", encoding="utf-8")

    state = load_schedule_state(str(corrupted_file))
    assert state == {}

    # Khi state rỗng, nếu một job đang quá hạn thì phải báo động ngay, không được bỏ qua
    cfg = SCHEDULE_WATCH_JOBS["container-health"]
    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    last_seen = now - timedelta(hours=2)
    job_last_seen = {"container-health": (last_seen, None)}

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen, now, state, watch_jobs={"container-health": cfg}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'container-health' NGỪNG CHẠY" in alerts[0]
    assert new_state["container-health"]["status"] == "stale"


def test_heartbeat_watch_trong_va_ngoai_khung():
    """Việc 3: container-health canh heartbeat trong ngày giao dịch từ 08:15 đến 15:00."""
    # 1. Lúc 10:00 ngày giao dịch (Thứ Sáu 2026-10-02), heartbeat cũ 16 phút (> 15 phút) -> BÁO
    now_trading = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    last_seen_stale = now_trading - timedelta(minutes=16)
    alerts, record, _ = evaluate_heartbeat_watch(last_seen_stale, None, now_trading, None)
    assert len(alerts) == 1
    assert "[CRITICAL] heartbeat check NGỪNG CHẠY" in alerts[0]
    assert record["status"] == "stale"

    # 2. Lúc 10:00 Chủ nhật (2026-10-04), heartbeat cũ 16 phút -> IM (ngày nghỉ)
    now_sunday = datetime(2026, 10, 4, 10, 0, 0, tzinfo=TZ)
    alerts, record, _ = evaluate_heartbeat_watch(last_seen_stale, None, now_sunday, None)
    assert alerts == []
    assert record is None

    # 3. Lúc 07:00 sáng ngày giao dịch (2026-10-02), trước 08:15 -> IM (chưa vào khung canh)
    now_early = datetime(2026, 10, 2, 7, 0, 0, tzinfo=TZ)
    alerts, record, _ = evaluate_heartbeat_watch(last_seen_stale, None, now_early, None)
    assert alerts == []
    assert record is None


def test_tai_hien_dung_su_co_02_10(tmp_path: Path):
    """Tiêu chí 3: Tái hiện đúng sự cố 02/10 bằng nguyên văn các dòng cuối thật của container-health.log.

    Lúc now = 2026-10-02 10:20, dòng cuối là 2026-10-02 05:49:54 container-health start -> PHẢI BÁO.
    """
    raw_log = (
        "ALERT_EXIT=0\n"
        "2026-10-01 17:50:02 container-health SKIP: docker chua chay\n"
        "ALERT_EXIT=0\n"
        "2026-10-02 05:49:54 container-health start\n"
        "EXIT=0\n"
    )
    log_file = tmp_path / "container-health.log"
    log_file.write_text(raw_log, encoding="utf-8")

    dt, err = get_last_called_timestamp(str(log_file), "container-health")
    assert err is None
    assert dt == datetime(2026, 10, 2, 5, 49, 54, tzinfo=TZ)

    # Thời điểm Claude audit phát hiện lúc 10:20 sáng 02/10
    now_audit = datetime(2026, 10, 2, 10, 20, 0, tzinfo=TZ)
    cfg = SCHEDULE_WATCH_JOBS["container-health"]

    alerts, new_state, _ = evaluate_schedule_health(
        {"container-health": (dt, None)}, now_audit, {}, watch_jobs={"container-health": cfg}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'container-health' NGỪNG CHẠY" in alerts[0]
    assert "05:49:54" in alerts[0]
    assert "270 phút trước" in alerts[0]
    assert new_state["container-health"]["status"] == "stale"


def test_heartbeat_check_build_parser_has_dry_run():
    """heartbeat_check.py phải có cờ --dry-run phục vụ chạy an toàn và không ghi file trạng thái."""
    parser = build_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True
