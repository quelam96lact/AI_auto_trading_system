"""Unit tests cho scripts/host_preflight.py (Brief 133).

Moi test dung su kien gia — khong can host that.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.host_preflight import (
    FAIL,
    OK,
    SKIP,
    Result,
    collect_published_ports,
    evaluate,
    exit_code,
    main,
    parse_port_spec,
    summarize,
)

GB = 1024**3
JOBS = {"heartbeat", "backup", "host-preflight"}

CRON_OK = "CRON_TZ=Asia/Ho_Chi_Minh\n" + "\n".join(
    f"0 * * * * cd /opt/trading && scripts/sched.sh {j}" for j in sorted(JOBS)
)
DAEMON_OK = {
    "log-driver": "json-file",
    "log-opts": {"max-size": "10m", "max-file": "3"},
}
UFW_OK = "Status: active\n\nTo   Action  From\n22/tcp  ALLOW  Anywhere\n443/tcp  ALLOW  Anywhere\n"


def good_facts() -> dict:
    return {
        "backup_dir": {"env_set": True, "path": "/b", "exists": True, "writable": True},
        "cron": {"rc": 0, "text": CRON_OK},
        "docker_daemon": {"exists": True, "data": DAEMON_OK},
        "logrotate": {"exists": True},
        "env_perm": {"exists": True, "mode": 0o600},
        "env_crlf": {"exists": True, "cr_count": 0},
        "timezone": {"value": "Asia/Ho_Chi_Minh"},
        "ufw": {"text": UFW_OK},
        "disk": {"free_bytes": 50 * GB, "total_bytes": 80 * GB},
        "exec_flags": {"nonexec": []},
        "real_trading": {"found": True, "value": "false"},
        "clock": {"synced": True},
        "holidays_confirmed": {"found": True, "value": "2999-12-31"},
        "published_listening": {"ss_text": "", "ports": [5432, 3000], "ports_source": "CLOSED_PORTS"},
        "published_ports": {
            "source": "compose",
            "ports": [
                {"service": "postgres", "host_ip": "127.0.0.1", "published": "5432", "target": 5432},
                {"service": "grafana", "host_ip": "127.0.0.1", "published": "3000", "target": 3000},
            ],
        },
    }


def status_of(results: list[Result], key: str) -> str:
    return next(r.status for r in results if r.key == key)


def run(mut) -> list[Result]:
    facts = good_facts()
    mut(facts)
    return evaluate(facts, JOBS)


def test_tat_ca_tot_thi_toan_dat():
    results = evaluate(good_facts(), JOBS)
    assert {r.status for r in results} == {OK}
    assert exit_code(results) == 0


# 1. backup_dir
def test_backup_dir_thieu_bien_hong():
    r = run(lambda f: f["backup_dir"].update(env_set=False))
    assert status_of(r, "backup_dir") == FAIL


def test_backup_dir_khong_ton_tai_hong():
    r = run(lambda f: f["backup_dir"].update(exists=False))
    assert status_of(r, "backup_dir") == FAIL


def test_backup_dir_khong_ghi_duoc_hong():
    r = run(lambda f: f["backup_dir"].update(writable=False))
    assert status_of(r, "backup_dir") == FAIL


# 2. cron
def test_cron_thieu_mot_job_hong_va_neu_ten_job():
    r = run(
        lambda f: f["cron"].update(
            text=CRON_OK.replace("sched.sh backup", "sched.sh xxx")
        )
    )
    res = next(x for x in r if x.key == "cron")
    assert res.status == FAIL
    assert "backup" in res.detail


def test_cron_thieu_cron_tz_hong():
    r = run(
        lambda f: f["cron"].update(text=CRON_OK.replace("CRON_TZ=Asia/Ho_Chi_Minh", ""))
    )
    assert status_of(r, "cron") == FAIL


def test_cron_dong_bi_comment_khong_tinh():
    text = CRON_OK.replace(
        "0 * * * * cd /opt/trading && scripts/sched.sh heartbeat",
        "# scripts/sched.sh heartbeat",
    )
    assert status_of(run(lambda f: f["cron"].update(text=text)), "cron") == FAIL


def test_cron_khong_co_crontab_hong():
    r = run(lambda f: f["cron"].update(rc=1, text=""))
    assert status_of(r, "cron") == FAIL


def test_cron_khong_do_duoc_bo_qua_kem_ly_do():
    r = run(lambda f: f.__setitem__("cron", {"skip": "khong co crontab tren he nay"}))
    res = next(x for x in r if x.key == "cron")
    assert res.status == SKIP
    assert "crontab" in res.detail


# 3. docker daemon
def test_daemon_thieu_log_opts_hong():
    r = run(lambda f: f["docker_daemon"].update(data={"log-driver": "json-file"}))
    assert status_of(r, "docker_daemon") == FAIL


def test_daemon_thieu_max_file_hong():
    r = run(lambda f: f["docker_daemon"].update(data={"log-opts": {"max-size": "10m"}}))
    assert status_of(r, "docker_daemon") == FAIL


def test_daemon_khong_co_file_hong():
    r = run(lambda f: f.__setitem__("docker_daemon", {"exists": False}))
    assert status_of(r, "docker_daemon") == FAIL


def test_daemon_khong_doc_duoc_quyen_bo_qua():
    r = run(
        lambda f: f.__setitem__(
            "docker_daemon", {"skip": "khong doc duoc daemon.json (quyen)"}
        )
    )
    assert status_of(r, "docker_daemon") == SKIP


# 4. logrotate
def test_logrotate_thieu_hong():
    assert (
        status_of(run(lambda f: f["logrotate"].update(exists=False)), "logrotate")
        == FAIL
    )


def test_logrotate_bo_qua():
    r = run(lambda f: f.__setitem__("logrotate", {"skip": "khong phai Linux"}))
    assert status_of(r, "logrotate") == SKIP


# 5. .env
def test_env_mode_sai_hong():
    assert (
        status_of(run(lambda f: f["env_perm"].update(mode=0o644)), "env_perm") == FAIL
    )


def test_env_mode_bo_qua_tren_windows():
    r = run(lambda f: f.__setitem__("env_perm", {"skip": "Windows khong co mode 600"}))
    assert status_of(r, "env_perm") == SKIP


def test_env_thieu_file_hong():
    assert (
        status_of(run(lambda f: f["env_perm"].update(exists=False)), "env_perm") == FAIL
    )
    assert (
        status_of(run(lambda f: f["env_crlf"].update(exists=False)), "env_crlf") == FAIL
    )


def test_env_co_cr_hong_va_khong_lo_gia_tri():
    r = run(lambda f: f["env_crlf"].update(cr_count=3))
    res = next(x for x in r if x.key == "env_crlf")
    assert res.status == FAIL
    assert "3" in res.detail


# 6. timezone
def test_timezone_sai_hong():
    assert (
        status_of(run(lambda f: f["timezone"].update(value="UTC")), "timezone") == FAIL
    )


def test_timezone_bo_qua():
    r = run(lambda f: f.__setitem__("timezone", {"skip": "khong co timedatectl"}))
    assert status_of(r, "timezone") == SKIP


# 7. ufw
def test_ufw_tat_hong():
    r = run(lambda f: f["ufw"].update(text="Status: inactive\n"))
    assert status_of(r, "ufw") == FAIL


def test_ufw_mo_postgres_ra_ngoai_hong():
    r = run(lambda f: f["ufw"].update(text=UFW_OK + "5432/tcp  ALLOW  Anywhere\n"))
    assert status_of(r, "ufw") == FAIL


def test_ufw_mo_grafana_ra_ngoai_hong():
    r = run(lambda f: f["ufw"].update(text=UFW_OK + "3000  ALLOW  Anywhere\n"))
    assert status_of(r, "ufw") == FAIL


def test_ufw_mo_cong_cho_mot_ip_cu_the_khong_hong():
    r = run(lambda f: f["ufw"].update(text=UFW_OK + "3000/tcp  ALLOW  10.0.0.5\n"))
    assert status_of(r, "ufw") == OK


def test_ufw_khong_co_bo_qua():
    r = run(lambda f: f.__setitem__("ufw", {"skip": "khong co ufw tren he nay"}))
    res = next(x for x in r if x.key == "ufw")
    assert res.status == SKIP
    assert "ufw" in res.detail


# 8. disk
def test_disk_con_it_hong():
    assert status_of(run(lambda f: f["disk"].update(free_bytes=5 * GB)), "disk") == FAIL


def test_disk_tong_nho_hon_40gb_hong():
    r = run(lambda f: f["disk"].update(free_bytes=30 * GB, total_bytes=35 * GB))
    assert status_of(r, "disk") == FAIL


def test_disk_bo_qua():
    r = run(lambda f: f.__setitem__("disk", {"skip": "khong doc duoc dia"}))
    assert status_of(r, "disk") == SKIP


# 9. exec flags
def test_exec_flags_thieu_hong_va_neu_ten():
    r = run(lambda f: f["exec_flags"].update(nonexec=["scripts/x.sh"]))
    res = next(x for x in r if x.key == "exec_flags")
    assert res.status == FAIL
    assert "scripts/x.sh" in res.detail


def test_exec_flags_bo_qua_tren_windows():
    r = run(
        lambda f: f.__setitem__("exec_flags", {"skip": "Windows khong co bit thuc thi"})
    )
    assert status_of(r, "exec_flags") == SKIP


# 10. real_trading
def test_real_trading_true_hong():
    assert (
        status_of(run(lambda f: f["real_trading"].update(value="true")), "real_trading")
        == FAIL
    )


def test_real_trading_khong_thay_khoa_hong():
    assert (
        status_of(run(lambda f: f["real_trading"].update(found=False)), "real_trading")
        == FAIL
    )


def test_real_trading_bo_qua():
    r = run(lambda f: f.__setitem__("real_trading", {"skip": "khong doc duoc config"}))
    assert status_of(r, "real_trading") == SKIP


# 11. clock
def test_clock_khong_dong_bo_hong():
    assert status_of(run(lambda f: f["clock"].update(synced=False)), "clock") == FAIL


def test_clock_bo_qua():
    r = run(lambda f: f.__setitem__("clock", {"skip": "khong co timedatectl"}))
    assert status_of(r, "clock") == SKIP


# Chong bao dep
def test_su_kien_thieu_khong_bao_dat():
    """Khoa khong co trong facts = khong do duoc = BO QUA, KHONG BAO GIO la DAT."""
    results = evaluate({}, JOBS)
    assert {r.status for r in results} == {SKIP}
    assert all(r.detail for r in results)


def test_khong_do_duoc_gi_ca_thoat_0_nhung_canh_bao_ro():
    facts = {k: {"skip": f"khong do duoc {k}"} for k in good_facts()}
    results = evaluate(facts, JOBS)
    assert {r.status for r in results} == {SKIP}
    assert exit_code(results) == 0
    s = summarize(results)
    assert s["nothing_measured"] is True
    assert s["counts"] == {OK: 0, FAIL: 0, SKIP: len(results)}


def test_skip_khong_bi_dem_la_dat():
    results = evaluate({"clock": {"skip": "x"}}, JOBS)
    s = summarize(results)
    assert s["counts"][OK] == 0
    assert s["nothing_measured"] is True


def test_co_hong_thi_thoat_1_du_co_bo_qua():
    facts = good_facts()
    facts["clock"] = {"skip": "x"}
    facts["timezone"] = {"value": "UTC"}
    results = evaluate(facts, JOBS)
    assert exit_code(results) == 1
    assert summarize(results)["nothing_measured"] is False


def test_bo_qua_khong_lam_thoat_khac_0():
    facts = good_facts()
    facts["clock"] = {"skip": "x"}
    assert exit_code(evaluate(facts, JOBS)) == 0


# main
def test_main_sai_cau_hinh_repo_thoat_2(tmp_path):
    assert main(["--repo", str(tmp_path / "khong-co")]) == 2


def test_main_json_hop_le_va_khong_lo_gia_tri_env(tmp_path, capsys):
    repo = tmp_path
    (repo / "scripts").mkdir()
    (repo / "scripts" / "sched.sh").write_text(
        'case "$1" in\n  heartbeat)\n    ;;\n  *)\n    ;;\nesac\n'
    )
    (repo / "config").mkdir()
    (repo / "config" / "config.yaml").write_text("real_trading_enabled: false\n")
    (repo / ".env").write_bytes(b"SECRET_TOKEN=hunter2-super-secret\n")
    rc = main(["--repo", str(repo), "--json"])
    out = capsys.readouterr().out
    assert "hunter2-super-secret" not in out
    assert "SECRET_TOKEN" not in out
    data = json.loads(out)
    assert set(data) >= {"results", "counts", "nothing_measured"}
    assert rc in (0, 1)


def test_main_dem_cr_that_trong_env(tmp_path, capsys):
    repo = Path(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "sched.sh").write_text(
        'case "$1" in\n  heartbeat)\n    ;;\nesac\n'
    )
    (repo / ".env").write_bytes(b"A=1\r\nB=2\r\n")
    rc = main(["--repo", str(repo), "--json"])
    data = json.loads(capsys.readouterr().out)
    env_crlf = next(r for r in data["results"] if r["key"] == "env_crlf")
    assert env_crlf["status"] == FAIL
    assert rc == 1


# 12. published_ports (dot 135): kiem THANG cong Docker publish, khong tin ufw
def _ports(*items, source="compose"):
    return {
        "source": source,
        "ports": [
            {"service": svc, "host_ip": ip, "published": pub, "target": pub} for svc, ip, pub in items
        ],
    }


def test_ports_tat_ca_loopback_dat():
    r = run(lambda f: f.__setitem__("published_ports", _ports(("postgres", "127.0.0.1", "5432"), ("nats", "::1", "4222"))))
    assert status_of(r, "published_ports") == OK


def test_ports_mot_cong_0_0_0_0_hong_va_neu_service():
    r = run(lambda f: f.__setitem__("published_ports", _ports(("grafana", "127.0.0.1", "3000"), ("postgres", "0.0.0.0", "5432"))))
    res = next(x for x in r if x.key == "published_ports")
    assert res.status == FAIL
    assert "postgres" in res.detail and "5432" in res.detail
    assert "grafana" not in res.detail


def test_ports_ipv6_moi_giao_dien_hong():
    r = run(lambda f: f.__setitem__("published_ports", _ports(("postgres", "::", "5432"))))
    assert status_of(r, "published_ports") == FAIL


def test_ports_khong_ghi_dia_chi_hong():
    for ip in (None, ""):
        r = run(lambda f, ip=ip: f.__setitem__("published_ports", _ports(("postgres", ip, "5432"))))
        assert status_of(r, "published_ports") == FAIL


def test_ports_doc_tu_file_van_ket_luan_va_ghi_nguon():
    r = run(lambda f: f.__setitem__("published_ports", _ports(("postgres", "0.0.0.0", "5432"), source="file")))
    res = next(x for x in r if x.key == "published_ports")
    assert res.status == FAIL
    assert "file" in res.detail
    ok = run(lambda f: f.__setitem__("published_ports", _ports(("postgres", "127.0.0.1", "5432"), source="file")))
    res_ok = next(x for x in ok if x.key == "published_ports")
    assert res_ok.status == OK
    assert "file" in res_ok.detail


def test_ports_khong_doc_duoc_gi_bo_qua_kem_ly_do():
    r = run(lambda f: f.__setitem__("published_ports", {"skip": "không có docker compose lẫn file compose"}))
    res = next(x for x in r if x.key == "published_ports")
    assert res.status == SKIP
    assert "compose" in res.detail


def test_ufw_dat_phai_noi_ro_khong_chi_phoi_cong_docker():
    res = next(x for x in evaluate(good_facts(), JOBS) if x.key == "ufw")
    assert res.status == OK
    assert "Docker" in res.detail and "published_ports" in res.detail


def test_parse_port_spec():
    assert parse_port_spec("127.0.0.1:5432:5432") == ("127.0.0.1", "5432", "5432")
    assert parse_port_spec("5432:5432") == (None, "5432", "5432")
    assert parse_port_spec("5432") == (None, None, "5432")
    assert parse_port_spec("0.0.0.0:3000:3000/tcp") == ("0.0.0.0", "3000", "3000")
    assert parse_port_spec("[::1]:4222:4222") == ("::1", "4222", "4222")
    assert parse_port_spec("[::]:4222:4222") == ("::", "4222", "4222")


def _no_docker(cmd):
    return None


def test_collect_ports_compose_vang_doc_tu_file_va_gop_override(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  postgres:\n"
        '    ports: ["127.0.0.1:5432:5432"]\n'
        "  grafana:\n"
        '    ports: ["3000:3000"]\n',
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.override.yml").write_text(
        "services:\n"
        "  postgres:\n"
        '    ports: ["0.0.0.0:5433:5432"]\n',
        encoding="utf-8",
    )
    got = collect_published_ports(tmp_path, runner=_no_docker)
    assert got["source"] == "file"
    pairs = {(p["service"], p["host_ip"], p["published"]) for p in got["ports"]}
    assert ("postgres", "127.0.0.1", "5432") in pairs
    assert ("postgres", "0.0.0.0", "5433") in pairs  # override khong bi bo sot
    assert ("grafana", None, "3000") in pairs
    r = run(lambda f: f.__setitem__("published_ports", got))
    assert status_of(r, "published_ports") == FAIL


def test_collect_ports_khong_compose_khong_file_bo_qua(tmp_path):
    got = collect_published_ports(tmp_path, runner=_no_docker)
    assert got.get("skip")


def test_collect_ports_qua_compose_config_json(tmp_path):
    payload = json.dumps(
        {"services": {"postgres": {"ports": [{"host_ip": "127.0.0.1", "published": "5432", "target": 5432}]}, "engine": {}}}
    )
    got = collect_published_ports(tmp_path, runner=lambda cmd: (0, payload, ""))
    assert got["source"] == "compose"
    assert got["ports"] == [{"service": "postgres", "host_ip": "127.0.0.1", "published": "5432", "target": 5432}]


# 13. holidays_confirmed (dot 136): da CO NGUOI XAC NHAN lich nghi toi ngay nao.
# KHONG do bang max(holidays): max hien la 2027-09-02 nen se DAT trong khi Tet 2027 van khuyet.
TODAY = date(2026, 9, 30)


def _hc(value, today=TODAY):
    facts = good_facts()
    facts["holidays_confirmed"] = value
    return next(x for x in evaluate(facts, JOBS, today=today) if x.key == "holidays_confirmed")


def test_holidays_con_du_ngay_dat_va_nem_so_ngay_con_lai():
    r = _hc({"found": True, "value": "2026-12-31"})
    assert r.status == OK
    assert "92" in r.detail


def test_holidays_sat_han_hong_nem_gia_tri_va_viec_can_lam():
    r = _hc({"found": True, "value": "2026-12-31"}, today=date(2026, 11, 2))  # con 59 ngay
    assert r.status == FAIL
    assert "2026-12-31" in r.detail and "config.yaml" in r.detail


def test_holidays_dung_ranh_gioi_60_ngay():
    assert _hc({"found": True, "value": "2026-12-31"}, today=date(2026, 11, 1)).status == OK  # con 60
    assert _hc({"found": True, "value": "2026-12-31"}, today=date(2026, 11, 2)).status == FAIL  # con 59


def test_holidays_da_qua_han_hong():
    assert _hc({"found": True, "value": "2026-12-31"}, today=date(2027, 1, 5)).status == FAIL


def test_holidays_thieu_khoa_hong_khong_phai_bo_qua():
    assert _hc({"found": False, "value": ""}).status == FAIL


def test_holidays_gia_tri_khong_phan_tich_duoc_hong():
    assert _hc({"found": True, "value": "khong-phai-ngay"}).status == FAIL


def test_holidays_khong_doc_duoc_file_bo_qua_kem_ly_do():
    r = _hc({"skip": "không đọc được config/config.yaml"})
    assert r.status == SKIP and "config.yaml" in r.detail


def _repo_with_config(tmp_path, text):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "sched.sh").write_text('case "$1" in\n  heartbeat)\n    ;;\nesac\n')
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(text)
    return tmp_path


def test_collect_khong_do_bang_max_holidays(tmp_path, capsys):
    """holidays voi toi 2027-09-02 nhung xac nhan chi toi 2026-10-15 -> van HONG (khong DAT vi max)."""
    repo = _repo_with_config(
        tmp_path,
        "real_trading_enabled: false\nholidays: ['2026-09-02', '2027-09-02']\nholidays_confirmed_through: '2026-10-15'\n",
    )
    main(["--repo", str(repo), "--json"])
    data = json.loads(capsys.readouterr().out)
    row = next(r for r in data["results"] if r["key"] == "holidays_confirmed")
    assert row["status"] == FAIL
    assert "2026-10-15" in row["detail"]


def test_collect_doc_duoc_ngay_khong_dat_trong_dau_nhay(tmp_path, capsys):
    repo = _repo_with_config(tmp_path, "holidays_confirmed_through: 2999-12-31\n")
    main(["--repo", str(repo), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "holidays_confirmed")
    assert row["status"] == OK


def test_collect_thieu_khoa_trong_config_hong(tmp_path, capsys):
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")
    main(["--repo", str(repo), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "holidays_confirmed")
    assert row["status"] == FAIL


def test_collect_khong_co_config_bo_qua(tmp_path, capsys):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "sched.sh").write_text('case "$1" in\n  heartbeat)\n    ;;\nesac\n')
    main(["--repo", str(tmp_path), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "holidays_confirmed")
    assert row["status"] == SKIP


# ---------------------------------------------------------------------------
# Dot 139: cac ca bat duoc khi chay THAT trong container Linux duoi hai danh tinh (root / trader).
# Chuoi dau ra THAT cua `crontab -l` / `sudo -n` lay tu container ubuntu:24.04:
#   trader: `crontab -l`                       -> stderr "no crontab for trader", rc=1
#   trader: `sudo -n crontab -l -u root` (khong sudoers) -> stderr "sudo: a password is required", rc=1
# ---------------------------------------------------------------------------
from scripts.host_preflight import (
    collect_cron,
    is_executable_mode,
    render_table,
)

REAL_NO_CRONTAB = (1, "", "no crontab for trader\n")
REAL_SUDO_DENIED = (1, "", "sudo: a password is required\n")


def _runner(table):
    def run_(cmd):
        return table.get(tuple(cmd))

    return run_


CRON_CMD = ("crontab", "-l")
SUDO_ROOT_CMD = ("sudo", "-n", "crontab", "-l", "-u", "root")


def _cron_result(facts):
    return next(x for x in evaluate({"cron": facts}, JOBS, today=TODAY) if x.key == "cron")


def test_cron_root_doc_crontab_cua_chinh_no():
    f = collect_cron(_runner({CRON_CMD: (0, CRON_OK, "")}), euid=0)
    assert _cron_result(f).status == OK


def test_cron_root_khong_co_crontab_van_HONG():
    f = collect_cron(_runner({CRON_CMD: (1, "", "no crontab for root\n")}), euid=0)
    assert _cron_result(f).status == FAIL


def test_cron_tai_khoan_thuong_khong_co_crontab_khong_co_sudo_la_BO_QUA_khong_phai_HONG_oan():
    """Phat hien that: chay tay nhu tai lieu day (khong sudo) -> crontab -l doc nham crontab cua
    tai khoan thuong (rong) va bao HONG oan. Khong do duoc crontab cua root thi phai BO QUA."""
    f = collect_cron(_runner({CRON_CMD: REAL_NO_CRONTAB, SUDO_ROOT_CMD: REAL_SUDO_DENIED}), euid=1001)
    res = _cron_result(f)
    assert res.status == SKIP
    assert "root" in res.detail and "sudo" in res.detail


def test_cron_tai_khoan_thuong_khong_co_lenh_sudo_cung_BO_QUA():
    f = collect_cron(_runner({CRON_CMD: REAL_NO_CRONTAB}), euid=1001)  # sudo -> None (khong co)
    assert _cron_result(f).status == SKIP


def test_cron_tai_khoan_thuong_sudo_khong_mat_khau_doc_duoc_crontab_cua_root():
    f = collect_cron(_runner({CRON_CMD: REAL_NO_CRONTAB, SUDO_ROOT_CMD: (0, CRON_OK, "")}), euid=1001)
    res = _cron_result(f)
    assert res.status == OK
    assert "root" in res.detail


def test_cron_tai_khoan_thuong_sudo_doc_duoc_nhung_thieu_job_van_HONG():
    bad = CRON_OK.replace("sched.sh backup", "sched.sh xxx")
    f = collect_cron(_runner({CRON_CMD: REAL_NO_CRONTAB, SUDO_ROOT_CMD: (0, bad, "")}), euid=1001)
    assert _cron_result(f).status == FAIL


def test_cron_tai_khoan_thuong_co_crontab_rieng_day_du_thi_dat_kem_ghi_chu():
    f = collect_cron(_runner({CRON_CMD: (0, CRON_OK, ""), SUDO_ROOT_CMD: REAL_SUDO_DENIED}), euid=1001)
    res = _cron_result(f)
    assert res.status == OK
    assert "không phải root" in res.detail


def test_cron_khong_co_lenh_crontab_bo_qua():
    assert _cron_result(collect_cron(_runner({}), euid=0)).status == SKIP


def test_is_executable_mode_do_bit_khong_phu_thuoc_danh_tinh():
    """Phat hien that: os.access(X_OK) cho mode 010 ra DAT duoi root nhung khong duoi chu so huu.
    Do thang bit: co BAT KY bit x nao -> thuc thi duoc (root/cron chay duoc)."""
    assert is_executable_mode(0o755) and is_executable_mode(0o100)
    assert is_executable_mode(0o010) and is_executable_mode(0o001)
    assert not is_executable_mode(0o644) and not is_executable_mode(0o000)


def test_render_table_canh_bao_khi_khong_chay_duoi_root():
    text = render_table(evaluate(good_facts(), JOBS, today=TODAY), euid=1001)
    assert "uid=1001" in text and "root" in text and "sudo" in text


def test_render_table_khong_canh_bao_khi_la_root_hoac_khong_ro():
    results = evaluate(good_facts(), JOBS, today=TODAY)
    assert "uid=" not in render_table(results, euid=0)
    assert "uid=" not in render_table(results)


def test_main_env_khong_doc_duoc_quyen_khong_chet_ma_BO_QUA(tmp_path, capsys, monkeypatch):
    """Phat hien that: .env thuoc root mode 600, chay duoi trader -> PermissionError, cong cu chet
    voi traceback. Phai thanh BO QUA kem ly do."""
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")
    (repo / ".env").write_bytes(b"A=1\n")
    real = Path.read_bytes

    def deny(self):
        if self.name == ".env":
            raise PermissionError(13, "Permission denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    rc = main(["--repo", str(repo), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "env_crlf")
    assert row["status"] == SKIP and "quyền" in row["detail"]
    assert rc in (0, 1)


def test_main_sched_sh_khong_doc_duoc_thoat_2_khong_traceback(tmp_path, capsys, monkeypatch):
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")

    def boom(_path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("scripts.host_preflight.sched_job_labels", boom)
    assert main(["--repo", str(repo), "--json"]) == 2
    assert "sched.sh" in capsys.readouterr().err


def test_main_json_co_truong_euid(tmp_path, capsys):
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")
    main(["--repo", str(repo), "--json"])
    assert "euid" in json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# Phep 14 (dot 139): cong DANG NGHE that (ss -ltnH). Chuoi dau ra THAT bat duoc trong container
# ubuntu:24.04 (iproute2), khong tu bia dinh dang.
# ---------------------------------------------------------------------------
from scripts.host_preflight import listening_ports, parse_ss_listen

SS_V4_ALL = "LISTEN 0      5      0.0.0.0:3000 0.0.0.0:*\n"
SS_V4_LO = "LISTEN 0      5      127.0.0.1:3000 0.0.0.0:*\n"
SS_V6_DUAL = "LISTEN 0      5      *:3000 *:*\n"  # http.server --bind ::  (dual-stack)
SS_V6_LO = "LISTEN 0      5      [::1]:3000 [::]:*\n"
SS_V6_ONLY = "LISTEN 0      5      [::]:3000 [::]:*\n"  # socket IPV6_V6ONLY bind ::
SS_IFACE_LO = "LISTEN 0      5      127.0.0.53%lo:3000 0.0.0.0:*\n"  # nhu systemd-resolved
SS_REAL_IP = "LISTEN 0      5      172.17.0.2:3000 0.0.0.0:*\n"
SS_EXTRA_COL = 'LISTEN 0      5      0.0.0.0:3000 0.0.0.0:* users:(("python3",pid=3164,fd=3))\n'
SS_NOTHING = ""


def _pl(ss_text, ports=(5432, 3000), source="CLOSED_PORTS"):
    facts = good_facts()
    facts["published_listening"] = {"ss_text": ss_text, "ports": list(ports), "ports_source": source}
    return next(x for x in evaluate(facts, JOBS, today=TODAY) if x.key == "published_listening")


def test_ss_loopback_v4_dat():
    assert _pl(SS_V4_LO).status == OK


def test_ss_loopback_v6_ngoac_vuong_dat():
    assert _pl(SS_V6_LO).status == OK


def test_ss_iface_lo_van_la_loopback_dat():
    assert _pl(SS_IFACE_LO).status == OK


def test_ss_0_0_0_0_hong_nem_cong_va_dia_chi():
    r = _pl(SS_V4_ALL)
    assert r.status == FAIL
    assert "3000" in r.detail and "0.0.0.0" in r.detail


def test_ss_sao_dual_stack_hong():
    r = _pl(SS_V6_DUAL)
    assert r.status == FAIL and "*" in r.detail


def test_ss_v6_moi_giao_dien_ngoac_vuong_hong():
    """[::] khong phai loopback — pha thu coi no la loopback phai lam test nay do."""
    r = _pl(SS_V6_ONLY)
    assert r.status == FAIL and "::" in r.detail


def test_ss_ip_that_hong():
    r = _pl(SS_REAL_IP)
    assert r.status == FAIL and "172.17.0.2" in r.detail


def test_ss_co_cot_process_thua_van_phan_tich_dung():
    assert _pl(SS_EXTRA_COL).status == FAIL


def test_ss_khong_nghe_gi_dat_nhung_noi_thang_khong_co_tien_trinh():
    r = _pl(SS_NOTHING)
    assert r.status == OK
    assert "không có tiến trình nào nghe" in r.detail and "container có đang chạy không" in r.detail


def test_ss_chi_xet_cac_cong_cua_du_an_khong_xet_cong_khac():
    other = "LISTEN 0      128    0.0.0.0:22 0.0.0.0:*\n"
    assert _pl(other + SS_V4_LO).status == OK


def test_ss_nhieu_dong_mot_loopback_mot_lo_ra_ngoai_van_hong():
    r = _pl(SS_V4_LO + "LISTEN 0      5      0.0.0.0:5432 0.0.0.0:*\n")
    assert r.status == FAIL and "5432" in r.detail


def test_ss_khong_co_lenh_ss_bo_qua():
    facts = good_facts()
    facts["published_listening"] = {"skip": "không có lệnh ss trên hệ này"}
    r = next(x for x in evaluate(facts, JOBS, today=TODAY) if x.key == "published_listening")
    assert r.status == SKIP and "ss" in r.detail


def test_parse_ss_listen_tach_dia_chi_va_cong():
    text = SS_V4_ALL + SS_V6_LO + SS_V6_DUAL + SS_IFACE_LO + SS_EXTRA_COL + "rac khong phai dong LISTEN\n"
    assert parse_ss_listen(text) == [
        ("0.0.0.0", 3000),
        ("::1", 3000),
        ("*", 3000),
        ("127.0.0.53", 3000),
        ("0.0.0.0", 3000),
    ]


def test_listening_ports_lay_tu_phep_12_hoac_CLOSED_PORTS():
    pub = {"source": "compose", "ports": [{"service": "postgres", "published": "5432", "target": 5432},
                                           {"service": "nats-test", "published": "4223", "target": 4222}]}
    assert listening_ports(pub) == ([4223, 5432], "các cổng publish của compose")
    ports, src = listening_ports({"skip": "không đọc được"})
    assert ports == [3000, 5432] and "CLOSED_PORTS" in src
    assert listening_ports(None)[1].startswith("CLOSED_PORTS")


def test_collect_ss_khong_phai_linux_bo_qua(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("scripts.host_preflight._is_linux", lambda: False)
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")
    main(["--repo", str(repo), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "published_listening")
    assert row["status"] == SKIP and "Linux" in row["detail"]


def test_collect_ss_co_ss_chay_that_qua_runner_gia(tmp_path, capsys, monkeypatch):
    repo = _repo_with_config(tmp_path, "real_trading_enabled: false\n")
    (repo / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    ports: ['0.0.0.0:5432:5432']\n", encoding="utf-8"
    )
    monkeypatch.setattr("scripts.host_preflight._is_linux", lambda: True)
    real_run = __import__("scripts.host_preflight", fromlist=["_run"])._run

    def fake_run(cmd):
        if cmd[:2] == ["ss", "-ltnH"]:
            return 0, "LISTEN 0      4096   0.0.0.0:5432 0.0.0.0:*\n", ""
        if cmd[0] == "docker":
            return None
        return real_run(cmd)

    monkeypatch.setattr("scripts.host_preflight._run", fake_run)
    main(["--repo", str(repo), "--json"])
    row = next(r for r in json.loads(capsys.readouterr().out)["results"] if r["key"] == "published_listening")
    assert row["status"] == FAIL and "5432" in row["detail"]
