"""Unit tests cho scripts/host_preflight.py (Brief 133).

Moi test dung su kien gia — khong can host that.
"""

from __future__ import annotations

import json
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
