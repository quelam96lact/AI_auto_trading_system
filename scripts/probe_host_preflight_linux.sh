#!/usr/bin/env bash
# Chay host_preflight.py THAT trong mot container Linux DUNG MOT LAN (brief dot 139).
# Usage: scripts/probe_host_preflight_linux.sh [viec1|viec2|all]
#
# An toan: `docker run --rm` tu image cong khai, KHONG publish cong, KHONG --privileged, KHONG
# --network host, KHONG mount repo. Ma duoc dua vao bang tar cua cay lam viec, bo qua file bi
# .gitignore (gom .env that): container khong bao gio thay .env that — kich ban ben trong in
# `ls -la` thu muc goc TRUOC khi tao .env gia.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - \
  | MSYS_NO_PATHCONV=1 docker run --rm -i ubuntu:24.04 bash -c \
      'mkdir -p /opt/trading && tar -xf - -C /opt/trading && bash /opt/trading/scripts/host_preflight_linux_scenarios.sh "$0"' \
      "${1:-all}"
