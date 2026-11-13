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
    SCHEDULE_EXIT_POLICIES,
    SCHEDULE_WATCH_JOBS,
    JobExitPolicy,
    build_parser,
    evaluate_schedule_health,
    get_last_called_timestamp,
    get_last_run_exit_code,
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
    assert len(sched_branches) == 22, f"Kỳ vọng 22 nhánh trong sched.sh, thực tế có {len(sched_branches)}: {sched_branches}"

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


# =============================================================================
# Brief 156: Canh mã thoát cho các job theo lịch
# =============================================================================


def test_sched_branches_covered_in_exit_policies():
    """Việc 2 (Brief 156): Mọi nhánh trong sched.sh phải có chính sách mã thoát rõ ràng."""
    sched_branches = extract_sched_branches(SCHED_SH)
    assert len(sched_branches) == 22

    # universe-refresh chay qua scheduler daemon trong container, khong qua sched.sh
    policy_branches = set(SCHEDULE_EXIT_POLICIES.keys()) - {"universe-refresh"}
    missing = sched_branches - policy_branches
    assert not missing, f"Các nhánh sau trong sched.sh thiếu chính sách mã thoát trong SCHEDULE_EXIT_POLICIES: {missing}"

    extra = policy_branches - sched_branches
    assert not extra, f"Có nhánh dư thừa trong SCHEDULE_EXIT_POLICIES không tồn tại trong sched.sh: {extra}"

    for branch, policy in SCHEDULE_EXIT_POLICIES.items():
        assert isinstance(policy, JobExitPolicy)
        assert policy.branch == branch
        assert policy.log_file.endswith(".log")
        assert len(policy.label) > 0
        assert 0 in policy.normal_exit_codes, f"Nhánh {branch} phải coi mã 0 là mã bình thường"
        assert len(policy.reason) > 0, f"Nhánh {branch} phải có giải thích căn cứ dòng code và lý do"


def test_get_last_run_exit_code_reads_exit_code(tmp_path: Path):
    """Đọc đúng mốc thời gian và mã thoát cuối cùng khi job kết thúc."""
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2026-10-02 08:00:00 test-job start\n"
        "some log line\n"
        "EXIT=0\n"
        "2026-10-02 09:00:00 test-job start\n"
        "error happened\n"
        "EXIT=4\n",
        encoding="utf-8",
    )
    dt, code, err = get_last_run_exit_code(str(log_file), "test-job")
    assert err is None
    assert dt == datetime(2026, 10, 2, 9, 0, 0, tzinfo=TZ)
    assert code == 4


def test_get_last_run_exit_code_anchored_regex_avoids_alert_exit(tmp_path: Path):
    """Bẫy: regex ^EXIT= phải neo đầu dòng để không khớp nhầm ALERT_EXIT= trong output."""
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2026-10-02 08:00:00 test-job start\n"
        "[docker-down-alert] status ALERT_EXIT=1\n",
        encoding="utf-8",
    )
    dt, code, err = get_last_run_exit_code(str(log_file), "test-job")
    assert err is None
    assert dt == datetime(2026, 10, 2, 8, 0, 0, tzinfo=TZ)
    assert code is None  # Job đang chạy, không được đọc nhầm ALERT_EXIT=1 thành EXIT=1


def test_get_last_run_exit_code_running_job_is_not_failure(tmp_path: Path):
    """Job đang chạy (đã có start nhưng chưa có EXIT=) -> exit_code là None, không phải thất bại."""
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2026-10-02 08:40:02 orderbook-recorder start\n"
        "[08:40:11] Đang kết nối WebSocket SSI...\n",
        encoding="utf-8",
    )
    dt, code, err = get_last_run_exit_code(str(log_file), "orderbook-recorder")
    assert err is None
    assert dt == datetime(2026, 10, 2, 8, 40, 2, tzinfo=TZ)
    assert code is None


def test_get_last_run_exit_code_no_exit_line_is_silent(tmp_path: Path):
    """Log không có dòng EXIT= nào -> im lặng, không coi là thất bại."""
    log_file = tmp_path / "empty.log"
    log_file.write_text("", encoding="utf-8")
    dt, code, err = get_last_run_exit_code(str(log_file), "test-job")
    assert dt is None
    assert code is None
    assert "không tìm thấy dòng nào" in err


def test_exit_code_eval_normal_exit_is_silent():
    """Lần chạy cuối mã 0 (hoặc mã bình thường) -> im lặng."""
    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    job_exit_codes = {
        "orderbook-recorder": (now - timedelta(minutes=10), 0, None)
    }
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes=job_exit_codes
    )
    assert alerts == []
    assert new_state["orderbook-recorder"]["exit_status"] == "ok"
    assert new_state["orderbook-recorder"]["exit_code"] == 0


def test_exit_code_eval_unreported_failure_alerts_once():
    """Mã thất bại không ai báo -> sinh cảnh báo CRITICAL một lần."""
    now = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)
    run_dt = now - timedelta(minutes=10)
    job_exit_codes = {
        "orderbook-recorder": (run_dt, 4, None)
    }
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes=job_exit_codes
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'orderbook-recorder' THẤT BẠI" in alerts[0]
    assert "mã thoát 4" in alerts[0]
    assert new_state["orderbook-recorder"]["exit_status"] == "failed"
    assert new_state["orderbook-recorder"]["exit_code"] == 4


def test_exit_code_eval_repeated_failure_is_silent():
    """Lặp lại cùng mã thất bại -> im lặng (không gửi lặp)."""
    now = datetime(2026, 10, 2, 10, 5, 0, tzinfo=TZ)
    run_dt = now - timedelta(minutes=15)
    prev_state = {
        "orderbook-recorder": {
            "exit_status": "failed",
            "exit_code": 4,
            "checked_at": "2026-10-02 10:00:00",
        }
    }
    job_exit_codes = {
        "orderbook-recorder": (run_dt, 4, None)
    }
    alerts, new_state, info_logs = evaluate_schedule_health(
        {}, now, prev_state, watch_jobs={}, job_exit_codes=job_exit_codes
    )
    assert alerts == []
    assert new_state["orderbook-recorder"]["exit_status"] == "failed"
    assert any("vẫn thất bại" in log for log in info_logs)


def test_exit_code_eval_recovery_alerts_once():
    """Chạy lại thành công sau thất bại -> sinh cảnh báo INFO hồi phục một lần."""
    now = datetime(2026, 10, 2, 10, 10, 0, tzinfo=TZ)
    run_dt = now - timedelta(minutes=2)
    prev_state = {
        "orderbook-recorder": {
            "exit_status": "failed",
            "exit_code": 4,
            "checked_at": "2026-10-02 10:05:00",
        }
    }
    job_exit_codes = {
        "orderbook-recorder": (run_dt, 0, None)
    }
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, prev_state, watch_jobs={}, job_exit_codes=job_exit_codes
    )
    assert len(alerts) == 1
    assert "[INFO] job theo lịch 'orderbook-recorder' ĐÃ HỒI PHỤC" in alerts[0]
    assert "thành công (mã thoát 0)" in alerts[0]
    assert new_state["orderbook-recorder"]["exit_status"] == "ok"
    assert new_state["orderbook-recorder"]["exit_code"] == 0


def test_tai_hien_su_co_that_orderbook_recorder_exit_4(tmp_path: Path):
    """Bằng chứng 1: Tái hiện sự cố thật 29/09 của orderbook-recorder với nguyên văn log EXIT=4."""
    raw_log = (
        "2026-09-29 08:40:10 orderbook-recorder start\n"
        "2026-09-29 08:40:22.354 INFO [ssi_sdk.services.token_manager]: Access token set manually\n"
        "2026-09-29 08:40:24.325 INFO [ssi_sdk.services.token_manager]: Token refreshed successfully\n"
        "[08:40:22] Tự động xác định hợp đồng front-month VN30F: 41I1GA000\n"
        "[08:40:22] Khởi động máy ghi sổ lệnh 41I1GA000\n"
        "  File ghi nhận: data\\orderbook\\41I1GA000\\2026-09-29.jsonl.gz\n"
        "  Thời điểm tự dừng: 14:46:00 (giờ VN)\n"
        "2026-09-29 08:40:33.641 INFO [ssi_sdk.services.token_manager]: Access token set manually\n"
        "2026-09-29 08:40:34.089 INFO [ssi_sdk.services.token_manager]: Token refreshed successfully\n"
        "EXIT=4\n"
    )
    log_file = tmp_path / "orderbook-recorder.log"
    log_file.write_text(raw_log, encoding="utf-8")

    dt, code, err = get_last_run_exit_code(str(log_file), "orderbook-recorder")
    assert err is None
    assert code == 4
    assert dt == datetime(2026, 9, 29, 8, 40, 10, tzinfo=TZ)

    now = datetime(2026, 9, 29, 10, 0, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes={"orderbook-recorder": (dt, code, err)}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'orderbook-recorder' THẤT BẠI" in alerts[0]
    assert "mã thoát 4" in alerts[0]
    assert new_state["orderbook-recorder"]["exit_status"] == "failed"


def test_tai_hien_su_co_that_stream_health_exit_1(tmp_path: Path):
    """Bằng chứng 2: Tái hiện sự cố thật 18/09 của stream-health với nguyên văn log EXIT=1."""
    raw_log = (
        "2026-09-18 12:25:42 stream-health start\n"
        "WARN: do phu luong phien sang ngay 2026-09-18 dat 88.9% (72/81 nen), duoi nguong canh bao 90%\n"
        "EXIT=1\n"
        "2026-09-18 15:10:02 stream-health start\n"
        "WARN: do phu luong phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen), duoi nguong canh bao 90%\n"
        "EXIT=1\n"
    )
    log_file = tmp_path / "stream-health.log"
    log_file.write_text(raw_log, encoding="utf-8")

    dt, code, err = get_last_run_exit_code(str(log_file), "stream-health")
    assert err is None
    assert code == 1
    assert dt == datetime(2026, 9, 18, 15, 10, 2, tzinfo=TZ)

    now = datetime(2026, 9, 18, 16, 0, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes={"stream-health": (dt, code, err)}
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'stream-health' THẤT BẠI" in alerts[0]
    assert "mã thoát 1" in alerts[0]
    assert new_state["stream-health"]["exit_status"] == "failed"


def test_chong_nhan_doi_heartbeat_exit_1_im_lang(tmp_path: Path):
    """Test chống nhân đôi: heartbeat tự thoát 1 khi nó cảnh báo -> KHÔNG được sinh thêm cảnh báo."""
    raw_log = (
        "2026-10-02 10:00:00 heartbeat-check start\n"
        "[CRITICAL] service ngừng heartbeat quá 300s: collector\n"
        "EXIT=1\n"
    )
    log_file = tmp_path / "heartbeat.log"
    log_file.write_text(raw_log, encoding="utf-8")

    dt, code, err = get_last_run_exit_code(str(log_file), "heartbeat-check")
    assert err is None
    assert code == 1

    now = datetime(2026, 10, 2, 10, 5, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes={"heartbeat": (dt, code, err)}
    )
    assert alerts == [], "Heartbeat tự thoát 1 không được sinh thêm cảnh báo"
    assert new_state["heartbeat"]["exit_status"] == "ok"


def test_chong_nhan_doi_container_health_exit_2_docker_down_im_lang(tmp_path: Path):
    """Test chống nhân đôi: container-health thoát 2 lúc Docker không chạy -> KHÔNG được sinh thêm cảnh báo."""
    raw_log = (
        "2026-10-02 10:00:00 container-health start\n"
        "LỖI: Docker daemon không chạy hoặc không phản hồi trong 10s.\n"
        "EXIT=2\n"
    )
    log_file = tmp_path / "container-health.log"
    log_file.write_text(raw_log, encoding="utf-8")

    dt, code, err = get_last_run_exit_code(str(log_file), "container-health")
    assert err is None
    assert code == 2

    now = datetime(2026, 10, 2, 10, 5, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {}, now, {}, watch_jobs={}, job_exit_codes={"container-health": (dt, code, err)}
    )
    assert alerts == [], "container-health thoát 2 do Docker chết không được sinh thêm cảnh báo"
    assert new_state["container-health"]["exit_status"] == "ok"


# ==============================================================================
# Tests cho Đợt 217 (F1, F4): skip_counts_as_run & --schedule-watch-only
# ==============================================================================


def test_skip_counts_as_run_false_backup_stale_when_skips_only_after_old_start(tmp_path: Path):
    """Task 1 (F1): backup co start cach 60h va 3 dong SKIP -> bi tinh la stale va bao so lan SKIP."""
    raw_log = (
        "2026-10-01 02:00:00 backup start\n"
        "EXIT=0\n"
        "2026-10-02 02:00:00 backup SKIP: docker chua chay\n"
        "2026-10-03 02:00:00 backup SKIP: docker chua chay\n"
        "2026-10-03 10:00:00 backup SKIP: docker chua chay\n"
    )
    log_file = tmp_path / "backup.log"
    log_file.write_text(raw_log, encoding="utf-8")

    # 1. get_last_called_timestamp voi skip_counts_as_run=False
    res = get_last_called_timestamp(str(log_file), "backup", skip_counts_as_run=False)
    assert res[1] is None
    assert res[0] == datetime(2026, 10, 1, 2, 0, 0, tzinfo=TZ)
    assert res.skip_count == 3

    # 2. evaluate_schedule_health voi cfg backup (skip_counts_as_run=False)
    now = datetime(2026, 10, 3, 14, 0, 0, tzinfo=TZ)
    alerts, new_state, _ = evaluate_schedule_health(
        {"backup": res},
        now,
        {},
        watch_jobs={"backup": SCHEDULE_WATCH_JOBS["backup"]},
    )
    assert len(alerts) == 1
    assert "[CRITICAL] job theo lịch 'backup' NGỪNG CHẠY" in alerts[0]
    assert "lần chạy thật cuối cùng lúc 2026-10-01 02:00:00" in alerts[0]
    assert "đã có 3 lần SKIP kể từ đó" in alerts[0]
    assert new_state["backup"]["status"] == "stale"
    assert new_state["backup"]["skip_count"] == 3

    # 3. So sanh: neu job co skip_counts_as_run=True thi lay dong SKIP gan nhat (10:00) -> ok
    dt_any, err_any = get_last_called_timestamp(str(log_file), "backup", skip_counts_as_run=True)
    assert dt_any == datetime(2026, 10, 3, 10, 0, 0, tzinfo=TZ)
    dummy_cfg = SCHEDULE_WATCH_JOBS["backup"]._replace(skip_counts_as_run=True)
    alerts_true, new_state_true, _ = evaluate_schedule_health(
        {"backup": (dt_any, err_any)},
        now,
        {},
        watch_jobs={"backup": dummy_cfg},
    )
    assert alerts_true == []
    assert new_state_true["backup"]["status"] == "ok"


def _create_fresh_job_logs(logs_dir: Path, now_dt: datetime) -> None:
    """Tao cac file log gia 'vua chay' trong thu muc logs_dir de khong bi stale."""
    ts = (now_dt - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    for cfg in SCHEDULE_WATCH_JOBS.values():
        p = logs_dir / cfg.log_file
        if not p.exists():
            p.write_text(f"{ts} {cfg.label} start\nEXIT=0\n", encoding="utf-8")
    for policy in SCHEDULE_EXIT_POLICIES.values():
        p = logs_dir / policy.log_file
        if not p.exists():
            content = f"{ts} {policy.label} start\n"
            if policy.branch == "restore-drill":
                content += "Diễn tập OK: trading_fresh.dump, 32 bảng >= bản kê lúc dump\n"
            content += "EXIT=0\n"
            p.write_text(content, encoding="utf-8")


def test_schedule_watch_only_saturday_night_alerts_once(tmp_path: Path, monkeypatch):
    """Task 2 (F4): --schedule-watch-only chay 22:00 thu Bay, co job qua han -> bao dung 1 lan, lan 2 im."""
    import scripts.heartbeat_check as hc

    sat_night = datetime(2026, 10, 3, 22, 0, 0, tzinfo=TZ)  # Thu Bay

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return sat_night

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    sent_alerts = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_alerts.append(msg) or True)

    # Tao log tuoi cho moi job tru backup
    _create_fresh_job_logs(tmp_path, sat_night)
    # backup log co start 60h truoc
    old_ts = (sat_night - timedelta(hours=60)).strftime("%Y-%m-%d %H:%M:%S")
    (tmp_path / "backup.log").write_text(
        f"{old_ts} backup start\nEXIT=0\n", encoding="utf-8"
    )

    # Lan 1: co job stale -> thoat 1 va gui Telegram
    rc1 = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    assert rc1 == 1
    assert len(sent_alerts) == 1
    assert "backup" in sent_alerts[0]

    # Lan 2: van gio do, log khong doi -> trang thai stale da luu truoc do -> im lang, thoat 0
    rc2 = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    assert rc2 == 0
    assert len(sent_alerts) == 1, "Lan 2 khong duoc gui trung canh bao"


def test_schedule_watch_and_heartbeat_share_state_anti_duplication(tmp_path: Path, monkeypatch):
    """Lead adjustment 3: heartbeat trong phien bao X stale -> schedule-watch sau do KHONG bao lai X."""
    import scripts.heartbeat_check as hc

    # 10:00 thu Sau trong phien
    fri_10am = datetime(2026, 10, 2, 10, 0, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fri_10am

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    sent_alerts = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_alerts.append(msg) or True)

    # Tao log tuoi cho moi job tru backup
    _create_fresh_job_logs(tmp_path, fri_10am)
    old_ts = (fri_10am - timedelta(hours=60)).strftime("%Y-%m-%d %H:%M:%S")
    (tmp_path / "backup.log").write_text(
        f"{old_ts} backup start\nEXIT=0\n", encoding="utf-8"
    )

    # Heartbeat thuong trong phien (gia lap bang evaluate va save state giong heartbeat)
    prev_state = hc.load_schedule_state(str(tmp_path / hc.SCHEDULE_STATE_NAME))
    job_last_seen = {}
    for branch, job_cfg in SCHEDULE_WATCH_JOBS.items():
        log_path = str(tmp_path / job_cfg.log_file)
        job_last_seen[branch] = get_last_called_timestamp(
            log_path, job_cfg.label, skip_counts_as_run=job_cfg.skip_counts_as_run
        )
    sched_alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen,
        fri_10am,
        prev_state,
        watch_jobs=SCHEDULE_WATCH_JOBS,
        restore_drill_last_ok=hc.get_last_successful_restore_timestamp(
            str(tmp_path / "restore-drill.log")
        ),
    )
    assert len(sched_alerts) == 1
    assert "backup" in sched_alerts[0]
    hc.save_schedule_state(str(tmp_path / hc.SCHEDULE_STATE_NAME), new_state)

    # 10:07: schedule-watch chay bang cờ --schedule-watch-only dung CHUNG file state
    fri_1007 = datetime(2026, 10, 2, 10, 7, 0, tzinfo=TZ)
    FakeDatetime.now = staticmethod(lambda tz: fri_1007)

    rc = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    # backup da duoc heartbeat bao truoc do -> schedule-watch KHONG bao lai -> thoat 0
    assert rc == 0
    assert sent_alerts == [], "schedule-watch khong duoc gui trung canh bao ma heartbeat da bao"


def test_heartbeat_without_flag_saturday_night_exits_0(tmp_path: Path, monkeypatch):
    """Khong co co --schedule-watch-only thi 22:00 thu Bay return 0 ngay vi ngoai gio giao dich."""
    import scripts.heartbeat_check as hc

    sat_night = datetime(2026, 10, 3, 22, 0, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return sat_night

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    sent_alerts = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_alerts.append(msg) or True)

    _create_fresh_job_logs(tmp_path, sat_night)
    (tmp_path / "backup.log").write_text("old", encoding="utf-8")

    # Chay heartbeat khong co co --schedule-watch-only
    rc = hc.main(["--logs-dir", str(tmp_path)])
    assert rc == 0
    assert sent_alerts == []


def test_get_last_successful_restore_timestamp(tmp_path: Path):
    """Test trich xuat moc thoi gian dien tap phuc hoi thanh cong gan nhat."""
    from scripts.heartbeat_check import get_last_successful_restore_timestamp

    log_file = tmp_path / "restore-drill.log"

    # 1. File khong ton tai
    dt, reason = get_last_successful_restore_timestamp(str(log_file))
    assert dt is None
    assert "không tồn tại" in reason

    # 2. File chua tung co dong OK
    log_file.write_text(
        "2026-10-01 04:00:00 restore-drill start\n"
        "[CRITICAL] Bang thieu dong\n"
        "EXIT=1\n",
        encoding="utf-8",
    )
    dt, reason = get_last_successful_restore_timestamp(str(log_file))
    assert dt is None
    assert "chưa từng diễn tập thành công" in reason

    # 3. File co dong OK sau start
    log_file.write_text(
        "2026-10-01 04:00:00 restore-drill start\n"
        "Diễn tập OK: trading_20261001.dump, 32 bảng >= bản kê lúc dump\n"
        "EXIT=0\n",
        encoding="utf-8",
    )
    dt, reason = get_last_successful_restore_timestamp(str(log_file))
    assert dt == datetime(2026, 10, 1, 4, 0, 0, tzinfo=TZ)
    assert reason is None

    # 4. File co dong OK roi co SKIP
    log_file.write_text(
        "2026-10-01 04:00:00 restore-drill start\n"
        "Diễn tập OK: trading_20261001.dump, 32 bảng >= bản kê lúc dump\n"
        "EXIT=0\n"
        "2026-10-08 04:00:00 restore-drill SKIP: docker chua chay\n",
        encoding="utf-8",
    )
    dt, reason = get_last_successful_restore_timestamp(str(log_file))
    assert dt == datetime(2026, 10, 1, 4, 0, 0, tzinfo=TZ)
    assert reason is None

    # 5. File co dong OK cu, sau do co start loi (khong co OK)
    log_file.write_text(
        "2026-10-01 04:00:00 restore-drill start\n"
        "Diễn tập OK: trading_20261001.dump, 32 bảng >= bản kê lúc dump\n"
        "EXIT=0\n"
        "2026-10-08 04:00:00 restore-drill start\n"
        "[CRITICAL] Loi ket noi DB\n"
        "EXIT=1\n",
        encoding="utf-8",
    )
    dt, reason = get_last_successful_restore_timestamp(str(log_file))
    # Van tra ve moc OK cu (2026-10-01) vi lan start 2026-10-08 khong co dong OK
    assert dt == datetime(2026, 10, 1, 4, 0, 0, tzinfo=TZ)
    assert reason is None


def test_restore_drill_last_ok_8_days_no_alert():
    """Lần OK cuối cách đây 8 ngày (<= ngưỡng 9 ngày) -> không báo."""
    now = datetime(2026, 10, 10, 8, 0, 0, tzinfo=TZ)
    last_ok_dt = now - timedelta(days=8)

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state={},
        watch_jobs={},
        exit_policies={},
        restore_drill_last_ok=(last_ok_dt, None),
    )
    assert alerts == []
    assert new_state["restore-drill-ok"]["status"] == "ok"
    assert new_state["restore-drill-ok"]["last_called"] == last_ok_dt.strftime("%Y-%m-%d %H:%M:%S")


def test_restore_drill_last_ok_10_days_with_skip_alerts_once_then_silent(tmp_path: Path):
    """Lần OK cuối cách đây 10 ngày, sau đó có 1 dòng SKIP: báo đúng 1 lần, lần hai im."""
    from scripts.heartbeat_check import get_last_successful_restore_timestamp

    now = datetime(2026, 10, 15, 8, 0, 0, tzinfo=TZ)
    ok_dt = now - timedelta(days=10)

    log_file = tmp_path / "restore-drill.log"
    log_file.write_text(
        f"{ok_dt:%Y-%m-%d %H:%M:%S} restore-drill start\n"
        "Diễn tập OK: trading_dump.dump, 32 bảng >= bản kê lúc dump\n"
        "EXIT=0\n"
        f"{(ok_dt + timedelta(days=7)):%Y-%m-%d %H:%M:%S} restore-drill SKIP: docker chua chay\n",
        encoding="utf-8",
    )

    drill_ok = get_last_successful_restore_timestamp(str(log_file))
    assert drill_ok[0] == ok_dt

    # Lần 1: chưa có state -> báo CRITICAL
    alerts1, state1, _ = evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state={},
        watch_jobs={},
        exit_policies={},
        restore_drill_last_ok=drill_ok,
    )
    assert len(alerts1) == 1
    assert "[CRITICAL] diễn tập phục hồi 'restore-drill' QUÁ HẠN:" in alerts1[0]
    assert state1["restore-drill-ok"]["status"] == "stale"

    # Lần 2: chạy lại với state1 -> im lặng (chỉ ghi log info)
    alerts2, state2, info_logs2 = evaluate_schedule_health(
        job_last_seen={},
        now=now + timedelta(hours=1),
        previous_state=state1,
        watch_jobs={},
        exit_policies={},
        restore_drill_last_ok=drill_ok,
    )
    assert alerts2 == []
    assert state2["restore-drill-ok"]["status"] == "stale"
    assert any("restore-drill vẫn quá hạn diễn tập phục hồi" in i for i in info_logs2)


def test_restore_drill_failed_run_with_old_ok_10_days_alerts(tmp_path: Path):
    """Lần chạy cuối có start nhưng không có OK (lỗi), lần OK trước đó 10 ngày -> báo."""
    from scripts.heartbeat_check import get_last_successful_restore_timestamp

    now = datetime(2026, 10, 18, 8, 0, 0, tzinfo=TZ)
    ok_dt = now - timedelta(days=10)

    log_file = tmp_path / "restore-drill.log"
    log_file.write_text(
        f"{ok_dt:%Y-%m-%d %H:%M:%S} restore-drill start\n"
        "Diễn tập OK: trading_dump.dump, 32 bảng >= bản kê lúc dump\n"
        "EXIT=0\n"
        f"{(now - timedelta(days=2)):%Y-%m-%d %H:%M:%S} restore-drill start\n"
        "[CRITICAL] Phục hồi thiếu bảng\n"
        "EXIT=1\n",
        encoding="utf-8",
    )

    drill_ok = get_last_successful_restore_timestamp(str(log_file))
    assert drill_ok[0] == ok_dt

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state={},
        watch_jobs={},
        exit_policies={},
        restore_drill_last_ok=drill_ok,
    )
    assert len(alerts) == 1
    assert "[CRITICAL] diễn tập phục hồi 'restore-drill' QUÁ HẠN:" in alerts[0]
    assert new_state["restore-drill-ok"]["status"] == "stale"


def test_restore_drill_recovery_alert():
    """Từ stale chuyển sang ok -> phát cảnh báo hồi phục [INFO]."""
    now = datetime(2026, 10, 18, 8, 0, 0, tzinfo=TZ)
    last_ok_dt = now - timedelta(hours=2)  # mới diễn tập 2 giờ trước

    prev_state = {
        "restore-drill-ok": {
            "status": "stale",
            "last_called": (now - timedelta(days=12)).strftime("%Y-%m-%d %H:%M:%S"),
        }
    }

    alerts, new_state, _ = evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        exit_policies={},
        restore_drill_last_ok=(last_ok_dt, None),
    )
    assert len(alerts) == 1
    assert "[INFO] diễn tập phục hồi 'restore-drill' ĐÃ THÀNH CÔNG:" in alerts[0]
    assert new_state["restore-drill-ok"]["status"] == "ok"


# ==============================================================================
# Tests cho Brief 225: schedule-watch đọc mọi lần chạy mới và phát hiện tự hồi phục
# ==============================================================================


def test_dot225_self_healed_failure_emits_warn_and_advances_cursor(tmp_path: Path):
    """Test 1 (Brief đợt 225): Con trỏ ở 13:07. Log có EXIT=4 lúc 13:46 rồi EXIT=0 lúc 13:50 (container-health).
    Kỳ vọng: 1 [WARN] nêu mã 4 và 13:46:39, đồng thời con trỏ tiến tới 13:50.
    """
    import scripts.heartbeat_check as hc

    log_path = tmp_path / "container-health.log"
    log_path.write_text(
        "2026-11-13 13:46:39 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:50:57 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    prev_state = {
        "container-health": {
            "status": "ok",
            "exit_status": "ok",
            "exit_code": 0,
            "exit_seen_until": "2026-11-13 13:07:00",
        }
    }

    now = datetime(2026, 11, 13, 14, 7, 0, tzinfo=TZ)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "container-health")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"container-health": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "container-health")
        job_runs = None

    job_exit_codes = {"container-health": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"container-health": hc.SCHEDULE_EXIT_POLICIES["container-health"]},
        **kwargs,
    )

    assert len(alerts) == 1
    assert "[WARN]" in alerts[0]
    assert "container-health" in alerts[0]
    assert "tự hồi phục" in alerts[0]
    assert "mã 4" in alerts[0]
    assert "13:46:39" in alerts[0]
    assert new_state["container-health"]["exit_seen_until"] == "2026-11-13 13:50:57"


def test_dot225_second_check_without_new_runs_is_silent(tmp_path: Path):
    """Test 2 (Brief đợt 225): Như (1), nhưng chạy kiểm lần hai với state mới và không có lần chạy mới.
    Kỳ vọng: 0 tin.
    """
    import scripts.heartbeat_check as hc

    log_path = tmp_path / "container-health.log"
    log_path.write_text(
        "2026-11-13 13:46:39 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:50:57 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    state_after_test1 = {
        "container-health": {
            "status": "ok",
            "exit_status": "ok",
            "exit_code": 0,
            "exit_seen_until": "2026-11-13 13:50:57",
        }
    }

    now = datetime(2026, 11, 13, 15, 7, 0, tzinfo=TZ)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "container-health")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"container-health": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "container-health")
        job_runs = None

    job_exit_codes = {"container-health": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=state_after_test1,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"container-health": hc.SCHEDULE_EXIT_POLICIES["container-health"]},
        **kwargs,
    )

    assert alerts == []
    assert new_state["container-health"]["exit_seen_until"] == "2026-11-13 13:50:57"


def test_dot225_initial_run_without_cursor_does_not_alert_past_failures(tmp_path: Path):
    """Test 3 (Brief đợt 225): State không có con trỏ, log có 30 lần EXIT=2 (backfill) rồi EXIT=0.
    Kỳ vọng: 0 tin, và con trỏ được đặt.
    """
    import scripts.heartbeat_check as hc

    lines = []
    base_time = datetime(2026, 11, 9, 0, 0, 0, tzinfo=TZ)
    for i in range(30):
        t = base_time + timedelta(hours=i)
        lines.append(f"{t:%Y-%m-%d %H:%M:%S} backfill start\nEXIT=2\n")
    final_time = base_time + timedelta(hours=30)
    lines.append(f"{final_time:%Y-%m-%d %H:%M:%S} backfill start\nEXIT=0\n")

    log_path = tmp_path / "backfill.log"
    log_path.write_text("".join(lines), encoding="utf-8")

    prev_state = {}  # chưa từng có con trỏ

    now = final_time + timedelta(minutes=10)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "backfill")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"backfill": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "backfill")
        job_runs = None

    job_exit_codes = {"backfill": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"backfill": hc.SCHEDULE_EXIT_POLICIES["backfill"]},
        **kwargs,
    )

    assert alerts == []
    assert new_state["backfill"]["exit_status"] == "ok"
    assert new_state["backfill"].get("exit_seen_until") == final_time.strftime("%Y-%m-%d %H:%M:%S")


def test_dot225_repeated_failure_emits_single_critical_no_warn(tmp_path: Path):
    """Test 4 (Brief đợt 225): Lần chạy mới có EXIT=4, EXIT=4, rồi lần cuối EXIT=4.
    Kỳ vọng: đúng 1 CRITICAL như logic cũ, không kèm [WARN].
    """
    import scripts.heartbeat_check as hc

    log_path = tmp_path / "container-health.log"
    log_path.write_text(
        "2026-11-13 13:20:00 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:30:00 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:40:00 container-health start\n"
        "EXIT=4\n",
        encoding="utf-8",
    )

    prev_state = {
        "container-health": {
            "status": "ok",
            "exit_status": "ok",
            "exit_code": 0,
            "exit_seen_until": "2026-11-13 13:07:00",
        }
    }

    now = datetime(2026, 11, 13, 14, 7, 0, tzinfo=TZ)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "container-health")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"container-health": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "container-health")
        job_runs = None

    job_exit_codes = {"container-health": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"container-health": hc.SCHEDULE_EXIT_POLICIES["container-health"]},
        **kwargs,
    )

    assert len(alerts) == 1
    assert "[CRITICAL]" in alerts[0]
    assert "[WARN]" not in alerts[0]
    assert "mã thoát 4" in alerts[0]
    assert new_state["container-health"]["exit_status"] == "failed"
    assert new_state["container-health"].get("exit_seen_until") == "2026-11-13 13:40:00"


def test_dot225_two_branches_self_healed_emits_two_warns_single_telegram(tmp_path: Path, monkeypatch):
    """Test 5 (Brief đợt 225): Hai nhánh cùng có thất bại tự hồi phục.
    Kỳ vọng: 2 dòng [WARN], và main(--schedule-watch-only) gửi đúng 1 tin Telegram.
    """
    import scripts.heartbeat_check as hc

    now = datetime(2026, 11, 13, 14, 7, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz=None):
            return now

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    _create_fresh_job_logs(tmp_path, now)

    (tmp_path / "container-health.log").write_text(
        "2026-11-13 13:46:39 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:50:57 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    (tmp_path / "engine-cam.log").write_text(
        "2026-11-13 13:30:00 engine-cam start\n"
        "EXIT=2\n"
        "2026-11-13 13:45:00 engine-cam start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    state_file = tmp_path / hc.SCHEDULE_STATE_NAME
    hc.save_schedule_state(
        str(state_file),
        {
            "container-health": {
                "status": "ok",
                "exit_status": "ok",
                "exit_seen_until": "2026-11-13 13:07:00",
            },
            "engine-cam": {
                "status": "ok",
                "exit_status": "ok",
                "exit_seen_until": "2026-11-13 13:07:00",
            },
        },
    )

    sent_alerts = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_alerts.append(msg) or True)

    rc = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    assert rc == 1
    assert len(sent_alerts) == 1, "Kỳ vọng đúng 1 tin Telegram được gửi"
    assert "container-health" in sent_alerts[0]
    assert "engine-cam" in sent_alerts[0]
    assert sent_alerts[0].count("[WARN]") == 2


def test_dot225_failed_telegram_does_not_save_state_and_alerts_again(tmp_path: Path, monkeypatch):
    """Test 6 (Brief đợt 225): Gửi Telegram hỏng trong ca (1).
    Kỳ vọng: state không được lưu, và lần kiểm sau vẫn báo.
    """
    import scripts.heartbeat_check as hc

    now = datetime(2026, 11, 13, 14, 7, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz=None):
            return now

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    _create_fresh_job_logs(tmp_path, now)

    (tmp_path / "container-health.log").write_text(
        "2026-11-13 13:46:39 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:50:57 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    state_file = tmp_path / hc.SCHEDULE_STATE_NAME
    hc.save_schedule_state(
        str(state_file),
        {
            "container-health": {
                "status": "ok",
                "exit_status": "ok",
                "exit_seen_until": "2026-11-13 13:07:00",
            }
        },
    )

    sent_attempts = []
    # Gửi Telegram hỏng (return False)
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_attempts.append(msg) or False)

    rc1 = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    assert rc1 == 1
    assert len(sent_attempts) == 1

    # Kiểm tra state file không được cập nhật (con trỏ vẫn ở 13:07:00)
    st = hc.load_schedule_state(str(state_file))
    assert st["container-health"]["exit_seen_until"] == "2026-11-13 13:07:00"

    # Lần 2: sửa lại Telegram gửi thành công -> vẫn báo lại
    sent_attempts.clear()
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent_attempts.append(msg) or True)

    rc2 = hc.main(["--schedule-watch-only", "--logs-dir", str(tmp_path)])
    assert rc2 == 1
    assert len(sent_attempts) >= 1
    assert any("container-health" in s for s in sent_attempts)

    # Bây giờ state đã được lưu với con trỏ mới
    st2 = hc.load_schedule_state(str(state_file))
    assert st2["container-health"]["exit_seen_until"] == "2026-11-13 13:50:57"


def test_dot225_normal_exit_code_in_new_runs_is_silent(tmp_path: Path):
    """Test 7 (Brief đợt 225): Lần chạy mới thất bại bằng mã thuộc normal_exit_codes (container-health EXIT=1).
    Kỳ vọng: 0 tin.
    """
    import scripts.heartbeat_check as hc

    log_path = tmp_path / "container-health.log"
    log_path.write_text(
        "2026-11-13 13:30:00 container-health start\n"
        "EXIT=1\n"
        "2026-11-13 13:40:00 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    prev_state = {
        "container-health": {
            "status": "ok",
            "exit_status": "ok",
            "exit_seen_until": "2026-11-13 13:07:00",
        }
    }

    now = datetime(2026, 11, 13, 14, 7, 0, tzinfo=TZ)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "container-health")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"container-health": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "container-health")
        job_runs = None

    job_exit_codes = {"container-health": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"container-health": hc.SCHEDULE_EXIT_POLICIES["container-health"]},
        **kwargs,
    )

    assert alerts == []
    assert new_state["container-health"].get("exit_seen_until") == "2026-11-13 13:40:00"


def test_dot225_interleaved_skip_does_not_desync_or_match_alert_exit(tmp_path: Path):
    """Test 8 (Brief đợt 225): Có dòng SKIP xen giữa các lần chạy mới.
    Kỳ vọng: không làm lệch việc ghép EXIT= với start, và không có ALERT_EXIT= nào bị đọc thành EXIT=.
    """
    import scripts.heartbeat_check as hc

    log_path = tmp_path / "container-health.log"
    log_path.write_text(
        "2026-11-13 13:10:00 container-health start\n"
        "EXIT=4\n"
        "2026-11-13 13:20:00 container-health SKIP: docker chua chay\n"
        "ALERT_EXIT=1\n"
        "2026-11-13 13:30:00 container-health start\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    prev_state = {
        "container-health": {
            "status": "ok",
            "exit_status": "ok",
            "exit_seen_until": "2026-11-13 13:00:00",
        }
    }

    now = datetime(2026, 11, 13, 14, 0, 0, tzinfo=TZ)
    get_runs_fn = getattr(hc, "get_job_runs", None)
    if get_runs_fn is not None:
        runs, _ = get_runs_fn(str(log_path), "container-health")
        dt_last, code_last = runs[-1] if runs else (None, None)
        job_runs = {"container-health": runs}
    else:
        dt_last, code_last, _ = hc.get_last_run_exit_code(str(log_path), "container-health")
        job_runs = None

    job_exit_codes = {"container-health": (dt_last, code_last, None)}
    kwargs = {}
    if job_runs is not None:
        kwargs["job_runs"] = job_runs

    alerts, new_state, _ = hc.evaluate_schedule_health(
        job_last_seen={},
        now=now,
        previous_state=prev_state,
        watch_jobs={},
        job_exit_codes=job_exit_codes,
        exit_policies={"container-health": hc.SCHEDULE_EXIT_POLICIES["container-health"]},
        **kwargs,
    )

    assert len(alerts) == 1
    assert "[WARN]" in alerts[0]
    assert "13:10:00" in alerts[0]
    assert "mã 4" in alerts[0]
    assert "mã 1" not in alerts[0]
    assert new_state["container-health"].get("exit_seen_until") == "2026-11-13 13:30:00"




