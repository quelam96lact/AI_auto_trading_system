#!/usr/bin/env bash
# CHAY BEN TRONG mot container ubuntu:24.04 dung mot lan (brief dot 139) — KHONG chay tren host.
# Dung qua scripts/probe_host_preflight_linux.sh. Dung cac trang thai DAT/HONG that cho tung phep
# cua host_preflight.py roi chay cong cu THAT duoi HAI danh tinh: root (crontab cua `sudo crontab -e`,
# tuc danh tinh cua cron §9) va `trader` (tai khoan thuong, nhu khi nguoi van hanh go lenh tay).
#
# Usage (trong container): bash host_preflight_linux_scenarios.sh [viec1|viec2|all]
set -u
GROUP="${1:-all}"
export DEBIAN_FRONTEND=noninteractive
REPO=/opt/trading

apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq cron logrotate iproute2 python3 python3-yaml tzdata sudo >/dev/null 2>&1 \
  || { echo "APT FAIL"; exit 3; }
useradd -m -s /bin/bash trader

cd "$REPO" || exit 3
echo "### BANG CHUNG KHONG CO .env THAT TRONG CONTAINER (ls -la thu muc goc repo, TRUOC khi tao .env gia)"
ls -la "$REPO"
if [ -e "$REPO/.env" ]; then echo "!!! CO .env TRONG CONTAINER — DUNG"; exit 4; fi
echo "### (het bang chung) — khong co .env. Tu day moi tao .env gia."
chown -R trader:trader "$REPO"

cat > /tmp/row.py <<'PY'
import json, sys
keys = sys.argv[1:]
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("   !!! KHONG PHAI JSON (cong cu chet?):")
    for ln in raw.splitlines()[:8]:
        print("   | " + ln)
    sys.exit(0)
rows = {r["key"]: r for r in data["results"]}
for k in keys:
    r = rows.get(k)
    print("   %-16s %-7s %s" % (k, r["status"] if r else "-", r["detail"] if r else "(khong co hang nay)"))
PY

as_user() { # as_user <user> <cmd>
  if [ "$1" = root ]; then bash -c "$2"; else su -s /bin/bash "$1" -c "$2"; fi
}

BAK=/srv/bak
pf_rows() { # pf_rows <label> <bakdir|-> <key>...
  local label="$1" bak="$2"; shift 2
  local u
  for u in root trader; do
    echo "  [$u] $label"
    local envs="PYTHONPATH=$REPO"
    [ "$bak" != "-" ] && envs="$envs TRADING_BACKUP_DIR=$bak"
    as_user "$u" "cd $REPO && env $envs python3 scripts/host_preflight.py --json 2>&1" | python3 /tmp/row.py "$@"
  done
}

cron_block() { # in cac dong cron that cua DEPLOYMENT.md §9 (bo chu thich)
  python3 - <<'PY'
text = open("/opt/trading/DEPLOYMENT.md", encoding="utf-8").read()
i = text.index("sudo crontab -e\n# Cài đặt đầy đủ")
j = text.index("```", i)
for ln in text[i:j].splitlines()[1:]:
    if ln.strip() and not ln.lstrip().startswith("#"):
        print(ln)
PY
}

good_state() {
  mkdir -p "$BAK" && chown trader:trader "$BAK" && chmod 755 "$BAK"
  cron_block > /tmp/root.cron && crontab -u root /tmp/root.cron
  crontab -u trader -r 2>/dev/null
  mkdir -p /etc/docker
  printf '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}\n' > /etc/docker/daemon.json
  chmod 644 /etc/docker/daemon.json
  mkdir -p /etc/logrotate.d && : > /etc/logrotate.d/trading
  printf 'A=1\n' > "$REPO/.env" && chown trader:trader "$REPO/.env" && chmod 600 "$REPO/.env"
  echo "Asia/Ho_Chi_Minh" > /etc/timezone
  chmod 755 "$REPO"/scripts/*.sh "$REPO/.githooks/pre-push"
}

scenario() { # scenario <tieu de> -- sau do ham tu thiet lap duoc goi boi nguoi goi
  echo
  echo "################ $1"
}

viec1() {
  echo "cron block (so dong cron that): $(cron_block | wc -l)"; cron_block | head -3

  good_state; scenario "BASELINE: moi thu tot (kỳ vọng ĐẠT ở ca nào danh tính cho phép)"
  pf_rows "baseline" "$BAK" cron docker_daemon logrotate env_perm env_crlf timezone exec_flags backup_dir ufw clock published_ports real_trading holidays_confirmed

  # ---- crontab
  good_state; scenario "CRON ĐẠT: crontab cua root = khoi DEPLOYMENT.md §9 (dong 452/995: sudo crontab -e)"
  pf_rows "cron dat" "$BAK" cron
  good_state; cron_block | grep -v 'sched.sh backup-check' > /tmp/x.cron; crontab -u root /tmp/x.cron
  scenario "CRON HỎNG: root thieu job backup-check"; pf_rows "thieu job" "$BAK" cron
  good_state; cron_block | grep -v '^CRON_TZ' > /tmp/x.cron; crontab -u root /tmp/x.cron
  scenario "CRON HỎNG: root thieu CRON_TZ"; pf_rows "thieu CRON_TZ" "$BAK" cron
  good_state; crontab -u root -r; cron_block > /tmp/t.cron; crontab -u trader /tmp/t.cron
  scenario "CRON: khoi cron nam o crontab cua TRADER, root KHONG co"; pf_rows "cron o trader" "$BAK" cron
  good_state; echo "trader ALL=(root) NOPASSWD: /usr/bin/crontab" > /etc/sudoers.d/trader; chmod 440 /etc/sudoers.d/trader
  scenario "CRON ĐẠT: root co khoi cron; trader co sudo -n crontab (tai khoan thuong doc duoc crontab cua root)"
  pf_rows "sudo -n ok" "$BAK" cron
  cron_block | grep -v 'sched.sh backup-check' > /tmp/x.cron; crontab -u root /tmp/x.cron
  scenario "CRON HỎNG: root thieu job backup-check; trader co sudo -n (phai HONG giong root)"
  pf_rows "sudo -n ok, thieu job" "$BAK" cron
  rm -f /etc/sudoers.d/trader

  # ---- daemon.json
  good_state; scenario "DAEMON ĐẠT: co max-size + max-file"; pf_rows "daemon dat" "$BAK" docker_daemon
  good_state; rm -f /etc/docker/daemon.json
  scenario "DAEMON HỎNG: thieu file"; pf_rows "thieu file" "$BAK" docker_daemon
  good_state; printf '{"log-driver": "json-file", "log-opts": ' > /etc/docker/daemon.json
  scenario "DAEMON HỎNG: JSON hong"; pf_rows "json hong" "$BAK" docker_daemon
  good_state; chmod 600 /etc/docker/daemon.json
  scenario "DAEMON: 0600 root — trader khong doc duoc (ky vong BO QUA neu trader)"; pf_rows "0600 root" "$BAK" docker_daemon

  # ---- logrotate
  good_state; scenario "LOGROTATE ĐẠT"; pf_rows "co file" "$BAK" logrotate
  good_state; rm -f /etc/logrotate.d/trading
  scenario "LOGROTATE HỎNG"; pf_rows "khong co" "$BAK" logrotate

  # ---- .env mode + CR
  good_state; chmod 600 "$REPO/.env"; scenario ".ENV ĐẠT: chmod 600"; pf_rows "600" "$BAK" env_perm env_crlf
  good_state; chmod 644 "$REPO/.env"; scenario ".ENV HỎNG: chmod 644"; pf_rows "644" "$BAK" env_perm env_crlf
  good_state; printf 'A=1\r\nB=2\r\n' > "$REPO/.env"; chown trader:trader "$REPO/.env"; chmod 600 "$REPO/.env"
  scenario ".ENV CR: hai dong CRLF (env_crlf ky vong HONG)"; pf_rows "crlf" "$BAK" env_perm env_crlf
  good_state; chown root:root "$REPO/.env"; chmod 600 "$REPO/.env"
  scenario ".ENV: thuoc root mode 600 — trader KHONG doc duoc (ky vong khong chet)"; pf_rows "env cua root" "$BAK" env_perm env_crlf

  # ---- timezone
  good_state; echo "Asia/Ho_Chi_Minh" > /etc/timezone; scenario "TIMEZONE ĐẠT"; pf_rows "HCM" "$BAK" timezone
  good_state; echo "Etc/UTC" > /etc/timezone; scenario "TIMEZONE HỎNG: Etc/UTC"; pf_rows "UTC" "$BAK" timezone

  # ---- co thuc thi
  good_state; scenario "EXEC ĐẠT: tat ca +x"; pf_rows "all +x" "$BAK" exec_flags
  good_state; chmod 644 "$REPO/scripts/sched.sh"; scenario "EXEC HỎNG: sched.sh mode 644"; pf_rows "644" "$BAK" exec_flags
  good_state; chmod 644 "$REPO/.githooks/pre-push"; scenario "EXEC HỎNG: pre-push mode 644"; pf_rows "pre-push 644" "$BAK" exec_flags
  good_state; chmod 411 "$REPO/scripts/sched.sh"
  scenario "EXEC LẠ: sched.sh mode 411 (chu so huu chi r; chi nhom/other co x) — os.access khac nhau theo danh tinh"; pf_rows "mode 411" "$BAK" exec_flags

  # ---- thu muc sao luu
  good_state; scenario "BACKUP_DIR ĐẠT: thu muc cua trader 755"; pf_rows "trader 755" "$BAK" backup_dir
  good_state; chown root:root "$BAK"; chmod 755 "$BAK"
  scenario "BACKUP_DIR: thu muc cua ROOT mode 755 (ky vong trader HONG; root?)"; pf_rows "root 755" "$BAK" backup_dir
  good_state; scenario "BACKUP_DIR HỎNG: khong ton tai"; pf_rows "khong ton tai" "/srv/khong-co" backup_dir
  good_state; scenario "BACKUP_DIR HỎNG: bien chua dat"; pf_rows "khong dat bien" "-" backup_dir

  # ---- BO QUA du kien
  good_state; scenario "DU KIEN VAN BO QUA: ufw va dong ho (timedatectl)"; pf_rows "ufw+clock" "$BAK" ufw clock

  # ---- phep 12 duong doc file compose
  good_state; scenario "PHEP 12 tren Linux, khong co Docker -> duong doc file compose"; pf_rows "compose file" "$BAK" published_ports
  good_state; sed -i 's#"127.0.0.1:5432:5432"#"0.0.0.0:5432:5432"#' "$REPO/docker-compose.yml"
  scenario "PHEP 12 HỎNG: ban sao compose trong container doi 5432 thanh 0.0.0.0"; pf_rows "0.0.0.0" "$BAK" published_ports
}

viec2() {
  good_state
  apt-get install -y -qq iproute2 >/dev/null 2>&1
  echo
  echo "################ DO ss -ltnH THAT (chuoi tho de dua vao test)"
  for bind in 0.0.0.0 127.0.0.1 :: ::1; do
    python3 -m http.server 3000 --bind "$bind" >/dev/null 2>&1 &
    pid=$!
    sleep 1
    echo "--- python3 -m http.server 3000 --bind $bind"
    ss -ltnH
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  done
  echo "--- khong chay gi"
  ss -ltnH
  cat > /tmp/sock.py <<'PY'
import socket, sys, time
mode = sys.argv[1]
if mode == "v6only":      # [::]:3000 (chi IPv6, khong dual-stack)
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    s.bind(("::", 3000))
elif mode == "lo":        # 127.0.0.53%lo:3000 nhu systemd-resolved (gan vao thiet bi lo)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"lo")
    s.bind(("127.0.0.53", 3000))
elif mode == "ip":        # dia chi that cua container
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((socket.gethostbyname(socket.gethostname()), 3000))
s.listen(5)
time.sleep(30)
PY
  for mode in v6only lo ip; do
    python3 /tmp/sock.py "$mode" >/dev/null 2>&1 &
    pid=$!; sleep 1
    echo "--- socket $mode (ss -ltnH)"
    ss -ltnH
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  done
  python3 -m http.server 3000 --bind 0.0.0.0 >/dev/null 2>&1 &
  pid=$!; sleep 1
  echo "--- ss -ltnHp (cot Process thua, chay duoi root)"
  ss -ltnHp
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  echo "--- ss -ltnH day du cot (cho dinh dang that)"
  python3 -m http.server 3000 --bind 0.0.0.0 >/dev/null 2>&1 &
  pid=$!; sleep 1; ss -ltn; kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null

  echo
  echo "################ PHEP 14 THAT (published_listening)"
  for bind in 0.0.0.0 127.0.0.1 :: ::1; do
    python3 -m http.server 3000 --bind "$bind" >/dev/null 2>&1 &
    pid=$!; sleep 1
    scenario "PHEP 14: http.server 3000 --bind $bind"; pf_rows "bind $bind" "$BAK" published_listening
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  done
  scenario "PHEP 14: khong chay gi"; pf_rows "khong nghe" "$BAK" published_listening
}

raw() {
  good_state
  echo
  echo "################ CHUOI THO THAT cua crontab -l / sudo -n (de dua vao test)"
  echo "--- trader: crontab -l (khong co crontab)"
  as_user trader "crontab -l; echo rc=\$?" 2>&1
  echo "--- root: crontab -l khi root khong co crontab"
  crontab -u root -r; as_user root "crontab -l; echo rc=\$?" 2>&1
  cron_block > /tmp/root.cron && crontab -u root /tmp/root.cron
  echo "--- trader: sudo -n crontab -l -u root (KHONG co sudoers)"
  as_user trader "sudo -n crontab -l -u root; echo rc=\$?" 2>&1
  echo "trader ALL=(root) NOPASSWD: /usr/bin/crontab" > /etc/sudoers.d/trader; chmod 440 /etc/sudoers.d/trader
  echo "--- trader: sudo -n crontab -l -u root (CO sudoers NOPASSWD crontab) — 4 dong dau"
  as_user trader "sudo -n crontab -l -u root 2>&1 | head -4; echo rc=\${PIPESTATUS[0]}"
  echo "--- trader: id"
  as_user trader "id"
  echo "--- os.access(X_OK) tren sched.sh mode 411 (cu phap cu cua cong cu): phu thuoc danh tinh"
  printf 'import os,sys\nprint(sys.argv[1], "os.access X_OK =", os.access("/opt/trading/scripts/sched.sh", os.X_OK))\n' > /tmp/acc.py
  chmod 411 "$REPO/scripts/sched.sh"
  as_user root "python3 /tmp/acc.py root"
  as_user trader "python3 /tmp/acc.py trader"
}

case "$GROUP" in
  raw) raw ;;
  viec1) viec1 ;;
  viec2) viec2 ;;
  all) viec1; viec2 ;;
  *) echo "dung: $0 [viec1|viec2|all]"; exit 2 ;;
esac
