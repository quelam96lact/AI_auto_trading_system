#!/usr/bin/env bash
# Xoay log theo KICH THUOC cho cac file trong logs/ ma dam scheduled task ghi.
#
# Brief agent B 02/09/2026, phan 1. DEPLOYMENT.md §8 chi co logrotate cho
# Ubuntu, khong co gi cho Windows. File nay la MOT CONG THUC MOT NOI (4ea4c8d):
# run_if_docker_up.sh source no truoc khi ghi, va Windows Task Scheduler VA
# cron Ubuntu deu goi job qua run_if_docker_up.sh — nen khong can ban Ubuntu
# rieng. Xoay theo KICH THUOC, khong theo ngay: ngay nghi khong sinh log, xoay
# theo ngay se tao mot dong file rong (brief phan 1, yeu cau 2).
#
# So lieu (do 02/09/2026): heartbeat.log ~8,6 KB/ngay thuong, cong ~85 dong
# SKIP (~5 KB) moi ngay Docker tat => ~14 KB/ngay cao nhat. 1 MB = 2-3 thang
# log lien tuc; giu 5 ban cu = hon 1 nam hoi cuu truoc khi ban cu nhat bi xoa
# (~6 MB/file toi da, 4 file ~ 24 MB — khong dang ke).
#
# QUAN TRONG — khong bao gio lam hong viec ghi log: moi loi xoay (dia day, file
# bi khoa boi tien trinh khac — chuyen thuong tren Windows) deu bi NUOT. Uu
# tien: mat ban xoay con hon mat dong log (brief phan 1, yeu cau 3).
#
# Dung truc tiep (test / chay tay):  LOG_MAX_BYTES=<n> scripts/log_rotate.sh <file>
# Dung qua run_if_docker_up.sh:    (file duoc source, ham rotate_log co san)

LOG_MAX_BYTES="${LOG_MAX_BYTES:-1048576}"  # 1 MB — xoay khi vuot
LOG_KEEP="${LOG_KEEP:-5}"                  # giu 5 ban cu: .1 (moi nhat) .. .5

rotate_log() {
  local f="$1" size i
  [ -f "$f" ] || return 0
  size=$(wc -c < "$f" 2>/dev/null) || size=0
  [ "$size" -lt "$LOG_MAX_BYTES" ] && return 0
  # Xoa ban cu nhat truoc (nuot loi), roi dich .i -> .i+1, moi ban dich lui mot.
  # -T (no-target-directory): neu dich la thu muc (bat thuong), mv CHET thay vi
  # nhet file vao trong thu muc — chet la an toan: file goc con nguyen, dong
  # log moi van ghi tiep vao file goc.
  rm -f "$f.$LOG_KEEP" 2>/dev/null || true
  i=$((LOG_KEEP - 1))
  while [ "$i" -ge 1 ]; do
    [ -e "$f.$i" ] && mv -fT "$f.$i" "$f.$((i + 1))" 2>/dev/null || true
    i=$((i - 1))
  done
  # Xoay file chinh sang .1. Neu that bai (bi khoa / dia day / .1 la thu muc):
  # nuot loi, file goc giu nguyen — caller ghi dong moi vao file goc la xong.
  mv -fT "$f" "$f.1" 2>/dev/null || true
  return 0
}

# Chay truc tiep (khong phai source): xoay dung mot file.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  rotate_log "${1:?dung: scripts/log_rotate.sh <file-log>}"
fi
