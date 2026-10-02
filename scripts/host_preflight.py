"""Kiểm các bước LÀM TAY trên host mà không gì khác kiểm (brief đợt 133).

`DEPLOYMENT.md` bắt làm hàng chục bước tay trên host (cron, daemon.json, logrotate,
chmod 600 .env, múi giờ, ufw, thư mục sao lưu...). `check_golive_gate.py` chỉ kiểm
TRẠNG THÁI ỨNG DỤNG, nên quên một bước là im lặng. Công cụ này in một bảng, mỗi dòng
là một bước.

NGUYÊN TẮC: KHÔNG BAO GIỜ báo ĐẠT cho thứ không đo được. Ba trạng thái:
  ĐẠT / HỎNG / BỎ QUA (kèm lý do). Trên Windows `ufw`, `crontab`, `logrotate`,
  `systemd` không có -> BỎ QUA, không phải ĐẠT. Khoá thiếu trong sự kiện cũng là
  BỎ QUA. Một cổng từng báo đèn xanh giả đúng ngày hệ thống chết cả phiên.

Hàm quyết định `evaluate` THUẦN (nhận sự kiện đã đo); phần đọc host tách riêng ở
`collect_facts`. Chỉ ĐỌC: không sửa .env, không cài cron, không đổi múi giờ.
Không in bí mật: chỉ đếm `\\r` và đọc quyền file .env, không in giá trị.

Mã thoát: 0 không có HỎNG (kể cả toàn BỎ QUA — nhưng bảng cảnh báo rõ "không kiểm
được gì"); 1 có HỎNG; 2 sai cấu hình chính công cụ (không đọc được repo).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from trading.calendar_vn import TZ as VN_TZ

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OK = "ĐẠT"
FAIL = "HỎNG"
SKIP = "BỎ QUA"

_GB = 1024**3
DEFAULT_MIN_FREE_GB = 10.0
DEFAULT_MIN_TOTAL_GB = 40.0  # DEPLOYMENT.md §7: VPS tối thiểu ~40 GB
TZ = "Asia/Ho_Chi_Minh"
CLOSED_PORTS = (5432, 3000)  # Postgres, Grafana: không được mở ra ngoài
HOLIDAYS_MIN_DAYS = 60  # lịch nghỉ phải được xác nhận tới ít nhất hôm nay + 60 ngày
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
UFW_NOTE = (
    "LƯU Ý: ufw KHÔNG chi phối cổng do Docker publish (Docker chèn luật iptables riêng, đi vòng "
    "qua ufw) — ĐẠT ở đây không có nghĩa cổng đã kín; xem phép kiểm published_ports"
)


@dataclass(frozen=True)
class Result:
    key: str
    name: str
    status: str
    detail: str


def _skip(key: str, name: str, fact: dict | None) -> Result | None:
    """Sự kiện thiếu hoặc mang `skip` -> BỎ QUA. Không bao giờ ĐẠT."""
    if not fact:
        return Result(key, name, SKIP, "không đo được (không có sự kiện)")
    if "skip" in fact:
        return Result(key, name, SKIP, str(fact["skip"]) or "không đo được")
    return None


def _check_backup_dir(f: dict | None) -> Result:
    key, name = "backup_dir", "TRADING_BACKUP_DIR có mặt, thư mục tồn tại và ghi được"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("env_set"):
        return Result(
            key,
            name,
            FAIL,
            "biến TRADING_BACKUP_DIR chưa có trong môi trường (chạy qua scripts/sched.sh để nạp .env)",
        )
    if not f.get("exists"):
        return Result(key, name, FAIL, f"thư mục không tồn tại: {f.get('path')}")
    if not f.get("writable"):
        return Result(key, name, FAIL, f"thư mục không ghi được: {f.get('path')}")
    return Result(key, name, OK, str(f.get("path")))


def _cron_active_lines(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def _check_cron(f: dict | None, jobs: set[str]) -> Result:
    key, name = "cron", "crontab có đủ job của sched.sh và CRON_TZ"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if f.get("rc") != 0:
        return Result(
            key, name, FAIL, "người dùng chưa có crontab (crontab -l thất bại)"
        )
    lines = _cron_active_lines(str(f.get("text", "")))
    present = {
        m for ln in lines for m in re.findall(r"sched\.sh\s+([a-zA-Z0-9_-]+)", ln)
    }
    problems = []
    missing = sorted(jobs - present)
    if missing:
        problems.append(f"thiếu job: {', '.join(missing)}")
    if not any(re.fullmatch(rf"CRON_TZ\s*=\s*{re.escape(TZ)}", ln) for ln in lines):
        problems.append(f"thiếu dòng CRON_TZ={TZ}")
    if problems:
        return Result(key, name, FAIL, "; ".join(problems))
    src = f.get("source")
    return Result(
        key, name, OK, f"đủ {len(jobs)} job và CRON_TZ" + (f" ({src})" if src else "")
    )


def _check_docker_daemon(f: dict | None) -> Result:
    key, name = (
        "docker_daemon",
        "/etc/docker/daemon.json giới hạn log (max-size, max-file)",
    )
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("exists"):
        return Result(key, name, FAIL, "không có /etc/docker/daemon.json")
    data = f.get("data")
    if not isinstance(data, dict):
        return Result(key, name, FAIL, "daemon.json không phân tích được (JSON hỏng)")
    opts = data.get("log-opts") or {}
    missing = [k for k in ("max-size", "max-file") if k not in opts]
    if missing:
        return Result(key, name, FAIL, f"log-opts thiếu: {', '.join(missing)}")
    return Result(
        key, name, OK, f"max-size={opts['max-size']}, max-file={opts['max-file']}"
    )


def _check_logrotate(f: dict | None) -> Result:
    key, name = "logrotate", "/etc/logrotate.d/trading tồn tại"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("exists"):
        return Result(key, name, FAIL, "không có /etc/logrotate.d/trading")
    return Result(key, name, OK, "có file")


def _check_env_perm(f: dict | None) -> Result:
    key, name = "env_perm", ".env mode 600"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("exists"):
        return Result(key, name, FAIL, "không tìm thấy .env")
    mode = int(f.get("mode", 0)) & 0o777
    if mode != 0o600:
        return Result(key, name, FAIL, f"mode {oct(mode)} (cần 0o600)")
    return Result(key, name, OK, "0o600")


def _check_env_crlf(f: dict | None) -> Result:
    key, name = "env_crlf", ".env không có ký tự \\r"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("exists"):
        return Result(key, name, FAIL, "không tìm thấy .env")
    n = int(f.get("cr_count", 0))
    if n:
        return Result(
            key, name, FAIL, f"{n} ký tự \\r (mọi giá trị, kể cả token, dính \\r)"
        )
    return Result(key, name, OK, "0 ký tự \\r")


def _check_timezone(f: dict | None) -> Result:
    key, name = "timezone", f"múi giờ hệ thống {TZ}"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if f.get("value") != TZ:
        return Result(key, name, FAIL, f"múi giờ là {f.get('value')!r}")
    return Result(key, name, OK, TZ)


def _check_ufw(f: dict | None) -> Result:
    key, name = "ufw", "ufw bật, Postgres 5432 / Grafana 3000 không mở ra ngoài"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    text = str(f.get("text", ""))
    if not re.search(r"^Status:\s*active", text, re.MULTILINE | re.IGNORECASE):
        return Result(key, name, FAIL, f"ufw không ở trạng thái active. {UFW_NOTE}")
    opened = []
    for ln in text.splitlines():
        parts = ln.split()
        if not parts or "ALLOW" not in ln or "Anywhere" not in ln:
            continue
        head = re.match(r"(\d+)", parts[0])
        if head and int(head.group(1)) in CLOSED_PORTS:
            opened.append(head.group(1))
    if opened:
        return Result(
            key,
            name,
            FAIL,
            f"cổng mở cho mọi nguồn: {', '.join(sorted(set(opened)))}. {UFW_NOTE}",
        )
    return Result(
        key, name, OK, f"active, không cổng cấm nào mở cho mọi nguồn. {UFW_NOTE}"
    )


def _check_published_ports(f: dict | None) -> Result:
    key, name = "published_ports", "mọi cổng Docker publish bind 127.0.0.1"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    src = (
        "nguồn: docker compose config"
        if f.get("source") == "compose"
        else "nguồn: đọc trực tiếp từ file compose, KHÔNG qua docker compose"
    )
    bad = [
        f"{p['service']}:{p.get('published') or p.get('target')} (bind {p.get('host_ip') or 'mọi giao diện'})"
        for p in f.get("ports", [])
        if (p.get("host_ip") or "") not in LOOPBACK
    ]
    if bad:
        return Result(key, name, FAIL, f"cổng lộ ra ngoài: {', '.join(bad)} ({src})")
    return Result(
        key, name, OK, f"{len(f.get('ports', []))} cổng, tất cả bind loopback ({src})"
    )


def parse_ss_listen(text: str) -> list[tuple[str, int]]:
    """Đầu ra THẬT của `ss -ltnH` (đã bắt trong container Linux, đợt 139) -> [(địa chỉ, cổng)].

    Dạng thật: `0.0.0.0:3000`, `127.0.0.1:3000`, `*:3000` (dual-stack), `[::]:3000`, `[::1]:3000`,
    `127.0.0.53%lo:3000`, `172.17.0.2:3000`, và có thể có cột Process thừa (`users:((...))`).
    Địa chỉ đứng ở cột thứ 4; ngoặc vuông và hậu tố `%iface` được bỏ."""
    out: list[tuple[str, int]] = []
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) < 5 or parts[0] != "LISTEN":
            continue
        addr, _, port = parts[3].rpartition(":")
        if not port.isdigit():
            continue
        out.append((addr.strip("[]").split("%", 1)[0], int(port)))
    return out


def _is_loopback(addr: str) -> bool:
    """`*`, `::`, `0.0.0.0` và mọi thứ không phân tích được đều KHÔNG phải loopback."""
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def listening_ports(published: dict | None) -> tuple[list[int], str]:
    """Cổng cần xét: các cổng publish mà phép 12 đọc được; phép 12 BỎ QUA thì dùng CLOSED_PORTS."""
    if published and "skip" not in published:
        ports = sorted(
            {int(p.get("published") or p.get("target")) for p in published.get("ports", []) if p.get("published") or p.get("target")}
        )
        if ports:
            return ports, "các cổng publish của compose"
    return sorted(CLOSED_PORTS), "CLOSED_PORTS (phép 12 không đọc được cổng publish)"


def _check_published_listening(f: dict | None) -> Result:
    """Cổng ĐANG NGHE thật. Kiểm LỘ CỔNG, không kiểm sống/chết (đã có `container-health`).

    Phép 12 chỉ đọc CẤU HÌNH compose; container chưa tạo lại theo compose mới, hoặc một Postgres cài
    thẳng trên host, lọt qua phép 12 — phép này nhìn socket thật."""
    key, name = "published_listening", "cổng đang nghe thật (ss -ltnH) không lộ ra ngoài loopback"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    ports = set(f.get("ports", []))
    listening = [(a, p) for a, p in parse_ss_listen(str(f.get("ss_text", ""))) if p in ports]
    exposed = [(a, p) for a, p in listening if not _is_loopback(a)]
    if exposed:
        detail = ", ".join(f"{p} trên {a}" for a, p in sorted(exposed, key=lambda x: x[1]))
        return Result(key, name, FAIL, f"cổng đang nghe NGOÀI loopback: {detail}")
    if not listening:
        return Result(
            key,
            name,
            OK,
            f"không có tiến trình nào nghe trên các cổng {sorted(ports)} — container có đang chạy không? "
            "(phép này kiểm lộ cổng, không kiểm sống/chết; xem container-health)",
        )
    return Result(
        key, name, OK, "đang nghe chỉ trên loopback: " + ", ".join(f"{p} ({a})" for a, p in sorted(listening, key=lambda x: x[1]))
    )


def _check_holidays_confirmed(f: dict | None, today: date) -> Result:
    """Đã CÓ NGƯỜI XÁC NHẬN lịch nghỉ tới ngày nào (khoá `holidays_confirmed_through`).

    KHÔNG đo bằng max(holidays): max hiện là 2027-09-02 nên phép kiểm kiểu "danh sách có vươn
    tới 60 ngày nữa không" sẽ ĐẠT trong khi Tết 2027 vẫn khuyết (đèn xanh giả)."""
    key, name = (
        "holidays_confirmed",
        f"lịch nghỉ được xác nhận tới ≥ hôm nay + {HOLIDAYS_MIN_DAYS} ngày",
    )
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("found"):
        return Result(
            key,
            name,
            FAIL,
            "config/config.yaml thiếu khoá holidays_confirmed_through (chủ dự án điền)",
        )
    raw = str(f.get("value"))
    try:
        confirmed = date.fromisoformat(raw)
    except ValueError:
        return Result(
            key,
            name,
            FAIL,
            f"holidays_confirmed_through={raw!r} không phải ngày YYYY-MM-DD",
        )
    remaining = (confirmed - today).days
    if confirmed < today + timedelta(days=HOLIDAYS_MIN_DAYS):
        return Result(
            key,
            name,
            FAIL,
            f"holidays_confirmed_through={confirmed.isoformat()} chỉ còn {remaining} ngày "
            f"(cần ≥ {HOLIDAYS_MIN_DAYS}): cập nhật `holidays` và `holidays_confirmed_through` "
            "trong config/config.yaml theo thông báo của Chính phủ",
        )
    return Result(
        key, name, OK, f"xác nhận tới {confirmed.isoformat()}, còn {remaining} ngày"
    )


def _check_disk(f: dict | None, min_free_gb: float, min_total_gb: float) -> Result:
    key, name = (
        "disk",
        f"đĩa: trống ≥ {min_free_gb:.0f} GB và tổng ≥ {min_total_gb:.0f} GB",
    )
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    free = f["free_bytes"] / _GB
    total = f["total_bytes"] / _GB
    problems = []
    if free < min_free_gb:
        problems.append(f"còn trống {free:.1f} GB")
    if total < min_total_gb:
        problems.append(
            f"tổng {total:.1f} GB (VPS tối thiểu ~{min_total_gb:.0f} GB, xem §7)"
        )
    if problems:
        return Result(key, name, FAIL, "; ".join(problems))
    return Result(key, name, OK, f"trống {free:.1f} GB / tổng {total:.1f} GB")


def _check_exec_flags(f: dict | None) -> Result:
    key, name = "exec_flags", "scripts/*.sh và .githooks/pre-push thực thi được"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    bad = list(f.get("nonexec", []))
    if bad:
        return Result(key, name, FAIL, f"thiếu cờ thực thi: {', '.join(bad)}")
    return Result(key, name, OK, "tất cả thực thi được")


def _check_real_trading(f: dict | None) -> Result:
    key, name = "real_trading", "config.yaml: real_trading_enabled: false"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("found"):
        return Result(key, name, FAIL, "không thấy khoá real_trading_enabled")
    if str(f.get("value")).lower() != "false":
        return Result(key, name, FAIL, f"real_trading_enabled = {f.get('value')}")
    return Result(key, name, OK, "false")


def _check_clock(f: dict | None) -> Result:
    key, name = "clock", "đồng hồ hệ thống đồng bộ"
    if (r := _skip(key, name, f)) is not None:
        return r
    assert f is not None
    if not f.get("synced"):
        return Result(key, name, FAIL, "System clock synchronized: no")
    return Result(key, name, OK, "đã đồng bộ")


def evaluate(
    facts: dict,
    sched_jobs: set[str],
    min_free_gb: float = DEFAULT_MIN_FREE_GB,
    min_total_gb: float = DEFAULT_MIN_TOTAL_GB,
    today: date | None = None,
) -> list[Result]:
    """Hàm quyết định thuần: sự kiện đã đo -> danh sách kết quả.

    `today` tiêm được để test không phụ thuộc ngày thật."""
    today = today or datetime.now(VN_TZ).date()
    return [
        _check_backup_dir(facts.get("backup_dir")),
        _check_cron(facts.get("cron"), sched_jobs),
        _check_docker_daemon(facts.get("docker_daemon")),
        _check_logrotate(facts.get("logrotate")),
        _check_env_perm(facts.get("env_perm")),
        _check_env_crlf(facts.get("env_crlf")),
        _check_timezone(facts.get("timezone")),
        _check_ufw(facts.get("ufw")),
        _check_disk(facts.get("disk"), min_free_gb, min_total_gb),
        _check_exec_flags(facts.get("exec_flags")),
        _check_real_trading(facts.get("real_trading")),
        _check_clock(facts.get("clock")),
        _check_published_ports(facts.get("published_ports")),
        _check_holidays_confirmed(facts.get("holidays_confirmed"), today),
        _check_published_listening(facts.get("published_listening")),
    ]


def summarize(results: list[Result]) -> dict:
    counts = {OK: 0, FAIL: 0, SKIP: 0}
    for r in results:
        counts[r.status] += 1
    return {
        "counts": counts,
        # Toàn BỎ QUA: exit 0 nhưng KHÔNG được đọc thành "mọi thứ ổn".
        "nothing_measured": counts[OK] == 0 and counts[FAIL] == 0,
    }


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.status == FAIL for r in results) else 0


# ---------------------------------------------------------------- đọc host


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _run(cmd: list[str]) -> tuple[int, str, str] | None:
    """Chạy lệnh chỉ-đọc. None nếu lệnh không có / không chạy được."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except Exception:
        return None
    return p.returncode, p.stdout, p.stderr


def sched_job_labels(sched_sh: Path) -> set[str]:
    """Tập job suy từ chính sched.sh (cùng cách với tests/test_deployment_doc.py)."""
    text = sched_sh.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*([a-zA-Z0-9_-]+)\)", text, re.MULTILINE)) - {"*"}


def _timedatectl(prop: str) -> str | None:
    res = _run(["timedatectl", "show", "-p", prop, "--value"])
    if res is None or res[0] != 0:
        return None
    return res[1].strip()


def parse_port_spec(spec: str) -> tuple[str | None, str | None, str]:
    """`[ip:]published:target[/proto]` -> (host_ip|None, published|None, target)."""
    spec = spec.split("/", 1)[0]
    ip: str | None = None
    if spec.startswith("["):
        end = spec.index("]")
        ip = spec[1:end]
        spec = spec[end + 2 :]  # bỏ "]:"
        parts = spec.split(":")
    else:
        parts = spec.split(":")
        if len(parts) == 3:
            ip, parts = parts[0], parts[1:]
    if len(parts) == 1:
        return ip, None, parts[0]
    return ip, parts[0], parts[1]


def collect_published_ports(repo: Path, runner=None) -> dict:
    """Cổng Docker publish. Ưu tiên `docker compose config` (đã gộp override — trên VPS
    §11 Bước 5 tạo một file override); không gọi được thì đọc THẲNG file compose và ghi
    nguồn. Chỉ BỎ QUA khi không đọc được cả hai: đây là phép kiểm an ninh, Docker chưa
    chạy không phải lý do để bỏ qua."""
    runner = runner or _run
    ports: list[dict] = []
    try:
        res = runner(
            ["docker", "compose", "--profile", "*", "config", "--format", "json"]
        )
        if res is not None and res[0] == 0:
            services = json.loads(res[1]).get("services", {})
            for svc, cfg in services.items():
                for p in (cfg or {}).get("ports") or []:
                    ports.append(
                        {
                            "service": svc,
                            "host_ip": p.get("host_ip"),
                            "published": p.get("published"),
                            "target": p.get("target"),
                        }
                    )
            return {"source": "compose", "ports": ports}
    except Exception:
        ports = []

    files = [
        repo / n
        for n in (
            "docker-compose.yml",
            "docker-compose.override.yml",
            "docker-compose.override.yaml",
        )
        if (repo / n).is_file()
    ]
    if not files:
        return {
            "skip": "không gọi được docker compose và không có file docker-compose*.yml để đọc"
        }
    try:
        for fp in files:
            data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            for svc, cfg in (data.get("services") or {}).items():
                for p in (cfg or {}).get("ports") or []:
                    if isinstance(p, dict):
                        ports.append(
                            {
                                "service": svc,
                                "host_ip": p.get("host_ip"),
                                "published": p.get("published"),
                                "target": p.get("target"),
                            }
                        )
                    else:
                        ip, pub, tgt = parse_port_spec(str(p))
                        ports.append(
                            {
                                "service": svc,
                                "host_ip": ip,
                                "published": pub,
                                "target": tgt,
                            }
                        )
    except Exception as e:
        return {
            "skip": f"không gọi được docker compose và không đọc được file compose: {type(e).__name__}"
        }
    return {"source": "file", "ports": ports}


def _euid() -> int | None:
    return os.geteuid() if hasattr(os, "geteuid") else None


def is_executable_mode(mode: int) -> bool:
    """Có BẤT KỲ bit x nào -> thực thi được (root/cron chạy được). Đo bit chứ không dùng
    `os.access(X_OK)`: hàm đó phụ thuộc danh tính (mode 010: root ĐẠT, chủ sở hữu thì không), nên lần
    chạy tay và lần chạy cron cho hai kết quả khác nhau (đo thật đợt 139)."""
    return bool(mode & 0o111)


def collect_cron(runner=None, euid: int | None = None) -> dict:
    """Crontab mà cron §9 thật sự dùng: của ROOT (DEPLOYMENT.md cài bằng `sudo crontab -e`).

    `crontab -l` chỉ đọc crontab của TÀI KHOẢN ĐANG CHẠY nên chạy tay như tài liệu dạy (không sudo) sẽ
    đọc nhầm crontab rỗng và báo HỎNG oan (đo thật đợt 139: `no crontab for trader`, exit 1). Không phải
    root thì thử `sudo -n crontab -l -u root`; không đọc được thì BỎ QUA kèm cách chạy lại, không HỎNG."""
    runner = runner or _run
    own = runner(["crontab", "-l"])
    if own is None:
        return {"skip": "không có lệnh crontab trên hệ này"}
    if euid in (0, None):
        return {"rc": own[0], "text": own[1]}
    via_sudo = runner(["sudo", "-n", "crontab", "-l", "-u", "root"])
    if via_sudo is not None and via_sudo[0] == 0:
        return {"rc": 0, "text": via_sudo[1], "source": "crontab của root, đọc qua sudo -n"}
    if own[0] == 0:
        return {
            "rc": 0,
            "text": own[1],
            "source": "crontab của tài khoản này, không phải root — cron §9 cài ở crontab của root",
        }
    return {
        "skip": (
            "tài khoản này không có crontab và không đọc được crontab của root (sudo -n không khả dụng); "
            "cron §9 cài ở crontab của root (`sudo crontab -e`) — chạy lại bằng `sudo scripts/sched.sh host-preflight`"
        )
    }


def collect_facts(repo: Path) -> dict:
    facts: dict = {}
    linux = _is_linux()

    # 1. thư mục sao lưu — đọc biến môi trường, KHÔNG đọc .env
    bdir = os.environ.get("TRADING_BACKUP_DIR")
    facts["backup_dir"] = {
        "env_set": bool(bdir),
        "path": bdir or "",
        "exists": bool(bdir) and Path(bdir).is_dir(),
        "writable": bool(bdir) and Path(bdir).is_dir() and os.access(bdir, os.W_OK),
    }

    # 2. crontab
    facts["cron"] = collect_cron(euid=_euid())

    # 3. daemon.json / 4. logrotate
    if not linux:
        facts["docker_daemon"] = {
            "skip": "không phải Linux (daemon.json của máy chủ nằm ở /etc/docker)"
        }
        facts["logrotate"] = {"skip": "không phải Linux (không có logrotate)"}
    else:
        try:
            facts["docker_daemon"] = {
                "exists": True,
                "data": json.loads(
                    Path("/etc/docker/daemon.json").read_text(encoding="utf-8")
                ),
            }
        except FileNotFoundError:
            facts["docker_daemon"] = {"exists": False}
        except PermissionError:
            facts["docker_daemon"] = {
                "skip": "không đọc được /etc/docker/daemon.json (quyền)"
            }
        except ValueError:
            facts["docker_daemon"] = {"exists": True, "data": None}
        facts["logrotate"] = {"exists": Path("/etc/logrotate.d/trading").exists()}

    # 5. .env: quyền file và ĐẾM \r (không đọc giá trị ra ngoài)
    env = repo / ".env"
    if not env.is_file():
        facts["env_perm"] = {"exists": False}
        facts["env_crlf"] = {"exists": False}
    else:
        facts["env_perm"] = (
            {"exists": True, "mode": env.stat().st_mode & 0o777}
            if linux
            else {"skip": "không phải Linux (Windows không có mode 600)"}
        )
        try:
            facts["env_crlf"] = {"exists": True, "cr_count": env.read_bytes().count(b"\r")}
        except PermissionError:
            facts["env_crlf"] = {
                "skip": "không đọc được .env (quyền): chạy lại bằng tài khoản sở hữu nó hoặc bằng sudo"
            }

    # 6. múi giờ / 11. đồng hồ
    tz = _timedatectl("Timezone")
    if tz is None and linux and Path("/etc/timezone").is_file():
        tz = Path("/etc/timezone").read_text(encoding="utf-8").strip()
    facts["timezone"] = (
        {"value": tz}
        if tz
        else {"skip": "không có timedatectl hay /etc/timezone trên hệ này"}
    )
    synced = _timedatectl("NTPSynchronized")
    facts["clock"] = (
        {"synced": synced == "yes"}
        if synced
        else {"skip": "không có timedatectl trên hệ này"}
    )

    # 7. ufw
    res = _run(["ufw", "status"])
    if res is None:
        facts["ufw"] = {"skip": "không có ufw trên hệ này"}
    elif res[0] != 0:
        facts["ufw"] = {
            "skip": f"ufw status không chạy được (thường cần root): {res[2].strip()[:80]}"
        }
    else:
        facts["ufw"] = {"text": res[1]}

    # 8. đĩa
    try:
        u = shutil.disk_usage(repo)
        facts["disk"] = {"free_bytes": u.free, "total_bytes": u.total}
    except OSError as e:
        facts["disk"] = {"skip": f"không đọc được dung lượng đĩa: {e}"}

    # 9. cờ thực thi
    if not linux:
        facts["exec_flags"] = {
            "skip": "không phải Linux (Windows không có bit thực thi)"
        }
    else:
        files = sorted((repo / "scripts").glob("*.sh")) + [
            repo / ".githooks" / "pre-push"
        ]
        facts["exec_flags"] = {
            "nonexec": [
                str(p.relative_to(repo))
                for p in files
                if p.exists() and not is_executable_mode(p.stat().st_mode)
            ]
        }

    # 10. real_trading_enabled
    cfg = repo / "config" / "config.yaml"
    try:
        m = re.search(
            r"^real_trading_enabled:\s*([A-Za-z]+)",
            cfg.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        facts["real_trading"] = {"found": bool(m), "value": m.group(1) if m else ""}
    except OSError as e:
        facts["real_trading"] = {"skip": f"không đọc được config/config.yaml: {e}"}

    # 13. lịch nghỉ đã được xác nhận tới đâu (đọc khoá, không suy từ max(holidays))
    try:
        raw_cfg = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        if not isinstance(raw_cfg, dict):
            raise TypeError("config.yaml không phải mapping")
        v = raw_cfg.get("holidays_confirmed_through")
        facts["holidays_confirmed"] = {
            "found": v is not None,
            "value": "" if v is None else str(v),
        }
    except (OSError, TypeError, yaml.YAMLError) as e:
        facts["holidays_confirmed"] = {
            "skip": f"không đọc được config/config.yaml: {e}"
        }

    # 12. cổng Docker publish (bỏ qua ufw): chạy compose trong repo
    cwd = os.getcwd()
    try:
        os.chdir(repo)
        facts["published_ports"] = collect_published_ports(repo)
    finally:
        os.chdir(cwd)

    # 14. cổng ĐANG NGHE thật (ss -ltnH), trên các cổng mà phép 12 đọc được
    ports, ports_src = listening_ports(facts.get("published_ports"))
    if not linux:
        facts["published_listening"] = {"skip": "không phải Linux (ss -ltnH chỉ có trên Linux)"}
    else:
        ss = _run(["ss", "-ltnH"])
        if ss is None:
            facts["published_listening"] = {"skip": "không có lệnh ss trên hệ này"}
        elif ss[0] != 0:
            facts["published_listening"] = {"skip": f"ss -ltnH lỗi: {ss[2].strip()[:80]}"}
        else:
            facts["published_listening"] = {"ss_text": ss[1], "ports": ports, "ports_source": ports_src}

    return facts


def render_table(results: list[Result], euid: int | None = None) -> str:
    s = summarize(results)
    lines = [f"{'TRẠNG THÁI':<8} {'PHÉP KIỂM':<62} CHI TIẾT"]
    for r in results:
        lines.append(f"{r.status:<8} {r.name:<62} {r.detail}")
    c = s["counts"]
    lines.append("")
    lines.append(f"Tổng kết: {c[OK]} {OK}, {c[FAIL]} {FAIL}, {c[SKIP]} {SKIP}")
    if s["nothing_measured"]:
        lines.append(
            "CẢNH BÁO: KHÔNG KIỂM ĐƯỢC GÌ CẢ — toàn BỎ QUA. Đây KHÔNG phải kết quả tốt; chạy lại trên host thật."
        )
    elif c[SKIP]:
        lines.append(
            f"Lưu ý: {c[SKIP]} phép kiểm BỎ QUA chưa được xác nhận — không tính là {OK}."
        )
    if euid not in (None, 0):
        lines.append(
            f"Chạy dưới uid={euid} (không phải root). Cron §9 chạy dưới root: các phép phụ thuộc danh tính "
            "(crontab, thư mục sao lưu ghi được) đo theo tài khoản này; chạy lại bằng "
            "`sudo scripts/sched.sh host-preflight` để khớp với cron."
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kiểm các bước làm tay trên host (chỉ đọc)."
    )
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB)
    parser.add_argument("--min-total-gb", type=float, default=DEFAULT_MIN_TOTAL_GB)
    parser.add_argument("--json", action="store_true", help="Xuất JSON máy đọc được")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo = Path(args.repo)
    sched = repo / "scripts" / "sched.sh"
    if not sched.is_file():
        print(f"LỖI CẤU HÌNH: không đọc được {sched}", file=sys.stderr)
        return 2
    try:
        jobs = sched_job_labels(sched)
    except OSError as e:
        print(f"LỖI CẤU HÌNH: không đọc được {sched}: {e}", file=sys.stderr)
        return 2
    euid = _euid()
    results = evaluate(collect_facts(repo), jobs, args.min_free_gb, args.min_total_gb)

    if args.json:
        print(
            json.dumps(
                {
                    "results": [asdict(r) for r in results],
                    "euid": euid,
                    **summarize(results),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(render_table(results, euid))
    return exit_code(results)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
