# Báo cáo đợt 134 — `TRADING_BACKUP_DIR` vào `.env` và năm scheduled task

Không commit, không push. `.env` được sửa theo §0 của brief (chủ dự án cho phép); không đọc/in nội dung.

## 1. Việc 1 — `.env`

- Bản sao lưu: `D:/My_Vault_Obsidian/Project/_backups/env/envfile_20260929_2353.bak` (`cmp` khớp với `.env` trước khi sửa). Tên **không** phải `.env.<timestamp>.bak` như brief gợi ý vì hook `.agentignore` chặn mẫu tên đó; chủ dự án đã đồng ý đổi tên.
- Ghi bằng Python, chế độ byte, LF. Byte cuối `.env` **chưa** là `\n` nên đã thêm `\n` trước dòng mới.
- Ba con số đếm: `grep -c '^TRADING_BACKUP_DIR='` = **1**; `grep -cU $'\r'` = **0**; `wc -l` 24 → 26 (**chênh 2, không phải 1**: một `\n` bù cho dòng cuối cũ thiếu LF, một `\n` cho dòng mới; không phải lỗi).
- `sched.sh disk-check` → `EXIT=0`, log `2026-09-29 23:53:00 disk-check start` / `EXIT=0`, không còn dòng "Bo qua phep do thu muc sao luu".
- `sched.sh backup-check` → `EXIT=0`, log `2026-09-29 23:53:01 backup-check start` / `EXIT=0`, im lặng.

## 2. Việc 2 — năm task

Khuôn: `wscript.exe //B //Nologo "…\scripts\run_hidden.vbs" <job>`, principal như `trading-heartbeat-check` (user hiện tại, Interactive, `Limited`), `ExecutionTimeLimit` 10 phút, `MultipleInstances=IgnoreNew`. Không cần admin.

| Task | Trigger | StartWhenAvailable | LastTaskResult | Log mới |
|---|---|---|---|---|
| `trading-container-health` | Daily 00:00, lặp PT10M, PT23H59M | False | **0** | `container-health.log`: `23:53:32 container-health start` … `EXIT=0` |
| `trading-backup` | Daily 02:00 | True | **0** | `backup.log`: `Backup written to D:/…/_backups/db/trading_20260929_235344.dump (100M)`, `EXIT=0` |
| `trading-orderbook-backup` | Daily 02:30 | True | **2 — LỖI** | `orderbook-backup.log`: `tar: D\:/My_Vault_Obsidian/…/orderbook_20260929.tar.gz: Cannot write: Broken pipe` … `EXIT=2` |
| `trading-backup-check` | Daily 03:00 | True | **0** | `backup-check.log`: `23:54:41 backup-check start` / `EXIT=0` |
| `trading-disk-check` | Daily 00:00, lặp PT6H, PT23H59M | False | **0** | `disk-check.log`: `23:54:49 disk-check start` / `EXIT=0` |

Bản dump thật ~100 MB đã tạo trong `_backups/db` (`trading_20260929_235344.dump`, 104.653.897 byte), giữ lại.

Lựa chọn `-StartWhenAvailable=True` cho ba task ban đêm: laptop có thể ngủ 02:00–03:00, chạy bù khi bật lại tốt hơn bỏ một đêm. Chín task cũ đang `StartWhenAvailable=False`; không đổi. Thời lượng lặp đặt PT23H59M (không phải 24h) để không có lần chạy trùng lúc 00:00 hôm sau.

### Lỗi phát hiện — `orderbook-backup` (lỗi của đợt 132, chưa sửa)

`scripts/backup_orderbook.sh` gọi `tar -czf "$OUT_FILE"` với `OUT_FILE=D:/…`. GNU tar hiểu `D:/…` là **máy từ xa tên `D`**. Đợt 132 chỉ thử với đường dẫn `/tmp/...` nên không thấy. Xác minh: `tar -czf D:/… -T /dev/null` → `Cannot connect to D: resolve failed`; `tar --force-local -czf … -T /dev/null` chạy được. Cách sửa dự kiến: thêm `--force-local` vào cả hai lệnh `tar -czf` và `tar -tzf`. **Chưa sửa** vì brief này cấm động vào `scripts/` (trừ chú thích `.vbs`) — chờ quyết định của chủ dự án.

## 3. Đối chiếu

- `Get-ScheduledTask | ? TaskName -like 'trading-*'` = **14**.
- `sched.sh` có 14 nhãn job, đều có task (`backfill`→`trading-backfill-universe`, `daily-check`→`trading-daily-data-check`, còn lại trùng tên). Không job nào thiếu task; `host-preflight` chưa tồn tại (brief 133 chưa làm).
- Lưu ý ngoài phạm vi: `trading-orderbook-daily-check` có `LastTaskResult=1` và `trading-orderbook-recorder` có `1073807364` (đã có từ trước, không đụng).

## 4. Việc 3 — `run_hidden.vbs`

```
-'   voi <job> = heartbeat | daily-check | backfill | deploy-drift | engine-cam | engine-consumer | stream-health
+'   voi <job> = mot nhan case trong scripts/sched.sh (nguon duy nhat, khong chep lai danh sach o day)
```
Chỉ một dòng chú thích.

## 5. Tiêu chí chung

`uv run pytest -q` → **1476 passed**; `ruff check trading tests scripts` sạch; `grep -cU $'\r' .env` = 0; 14 task.

## 6. Không làm được / brief sai

- `orderbook-backup` **chưa đạt** tiêu chí `LastTaskResult=0` (lỗi tar ở trên).
- Brief kỳ vọng `wc -l` chênh đúng 1; thực tế chênh 2 vì `.env` thiếu LF cuối.
- Tên bản sao lưu `.env.<timestamp>.bak` bị `.agentignore` chặn.

## 7. Cập nhật 30/09 00:06 — đã sửa `orderbook-backup`

Chủ dự án cho phép sửa `scripts/backup_orderbook.sh` trong đợt này. Thêm `--force-local` vào `tar -czf` và `tar -tzf` (2 dòng đổi). Chạy lại `Start-ScheduledTask trading-orderbook-backup`: **`LastTaskResult=0`**, log `2026-09-30 00:06:01 orderbook-backup start` → `Orderbook backup written to D:/My_Vault_Obsidian/Project/_backups/db/orderbook_20260930.tar.gz (3 files, 15M)` → `EXIT=0`. Đây là lần chạy đầu (bootstrap, chưa có bản nào) nên gói cả 3 file hiện có (15.540.555 byte); các đêm sau chỉ gói file mới. Cả năm task giờ có `LastTaskResult=0`.

---

## Audit của Claude (30/09/2026, 00:15)

### A.1. Kết luận: ĐẠT. Và Claude báo động nhầm một lần — lỗi ở phép đo của Claude.

### A.2. Báo động nhầm của Claude: `grep -c` đếm DÒNG, không đếm ký tự

Claude chạy `grep -cU $'\r' .env`, thấy **26**, và kết luận `.env` đã bị nhiễm CRLF — tức là cái bẫy mà chính brief cảnh báo, và mọi job đã dừng. **Sai.** `grep -c` đếm **số dòng khớp**, không đếm số ký tự; ở đây nó khớp mọi dòng nên trả về đúng bằng số dòng của file (26). Bản sao lưu cũng ra "25" theo cùng cách, đáng lẽ đã đủ để Claude nghi ngờ phép đo thay vì nghi dữ liệu.

Đo lại ở mức **byte** mới ra sự thật:

```
.env         : 2503 byte | CR=  0 | LF= 26 | CRLF=  0
ban sao luu  : 2442 byte | CR=  0 | LF= 24 | CRLF=  0
```

`.env` **sạch**, agent làm đúng. Và một bằng chứng độc lập nữa mà Claude đã có sẵn nhưng suýt bỏ qua: chạy thật `scripts/sched.sh disk-check` cho **EXIT=0** — nếu `.env` thật sự có `\r` thì cổng `run_if_docker_up.sh:68` đã trả 2.

**Bài học:** câu hỏi về **byte** thì phải đo bằng **byte**. `grep -c` trả về một con số trông rất giống câu trả lời nhưng trả lời câu khác — cùng họ với [[dung-so-hai-tap-khong-ghep-cap]]. Và khi phép đo và hành vi thật mâu thuẫn nhau, nghi phép đo trước.

### A.3. Việc 1 — `.env`: đạt

| Kiểm (Claude đo lại, chỉ đếm, không đọc nội dung) | Kết quả |
|---|---|
| `^TRADING_BACKUP_DIR=` | **1** dòng |
| ký tự CR (đo byte) | **0** |
| byte cuối | `\n` |
| bản sao lưu trước khi sửa | `_backups/env/envfile_20260929_2353.bak`, cũng 0 CR |

Chênh lệch: 2442 → 2503 byte (+61), 24 → 26 dòng (+2). Brief ghi "+1 dòng"; thực tế là **một dòng trống ngăn cách + một dòng biến** (59 ký tự + `\n` = 60 byte, cộng 1 byte cho dòng trống). Lệch không đáng kể và dễ đọc hơn; chấp nhận.

Cổng mở lại đúng như mong đợi: `sched.sh disk-check` **EXIT=0** và không còn dòng "Bo qua phep do thu muc sao luu"; `sched.sh backup-check` **EXIT=0**, im lặng.

### A.4. Việc 2 — năm scheduled task: đạt

Claude tự đọc lại từ Task Scheduler, không tin báo cáo:

| Task | `LastTaskResult` | Trigger | StartWhenAvailable |
|---|---|---|---|
| `trading-container-health` | 0 | hằng ngày, lặp `PT10M` / `PT23H59M` | False |
| `trading-backup` | 0 | 02:00 | **True** |
| `trading-orderbook-backup` | 0 | 02:30 | **True** |
| `trading-backup-check` | 0 | 03:00 | **True** |
| `trading-disk-check` | 0 | hằng ngày, lặp `PT6H` / `PT23H59M` | False |

Cả năm đều `Execute=wscript.exe`, tham số trỏ `run_hidden.vbs <job>`, `RunLevel=Limited` — **đúng khuôn 9 task cũ, không cần quyền admin**. Tổng cộng **14** task `trading-*`.

**Bằng chứng thật, không chỉ "Ready":** cả năm file log đều có dòng `EXIT=0`, và hai bản sao lưu thật đã sinh ra:
- `trading_20260929_235344.dump` — **104.653.897 byte**, do task `backup` tạo lúc 23:53.
- `orderbook_20260930.tar.gz` — **15.540.555 byte**, lúc 00:06. Đây là lần đầu trong thư mục này nên gói cả 3 file (bootstrap), đúng thiết kế đợt 132; các đêm sau chỉ gói file mới.

### A.5. Thay đổi NGOÀI phạm vi brief: `scripts/backup_orderbook.sh`

Brief §5 chỉ cho sửa `.env`, scheduled task, và **chú thích** `run_hidden.vbs`. Agent còn sửa `backup_orderbook.sh` (thêm `--force-local` vào hai lệnh `tar`), và mục 7 của báo cáo ghi *"Chủ dự án cho phép sửa ... trong đợt này"*. **Claude không kiểm chứng được lời cho phép đó** — nó không có trong phần việc Claude nhận. Ghi lại đúng như vậy, không suy diễn thêm.

**Bản thân thay đổi thì ĐÚNG, và Claude đã tự tái lập lỗi:**

```
tar -czf "D:/.../x.tar.gz" ...
  tar (child): Cannot connect to D: resolve failed
  tar: Child returned status 128
tar --force-local -czf "D:/.../y.tar.gz" ...   -> OK, 128 byte
```

`tar` hiểu `D:/...` là `host:path` (đường dẫn máy từ xa). Lỗi này **chỉ lộ ra khi `TRADING_BACKUP_DIR` là đường dẫn Windows** — tức do chính đợt 134 tạo ra, nên nó nằm trong đường đi của việc 2 và phải sửa thì task mới chạy được.

**Có an toàn cho VPS không?** Claude kiểm trên `ubuntu:24.04`: `tar --force-local -czf ... && tar --force-local -tzf ...` chạy bình thường. GNU tar trên Linux chấp nhận cờ này, nên không có rủi ro khi chuyển máy.

**Đúng quy trình thì nên báo trước rồi mới sửa** (brief §7 mục 7 yêu cầu nêu chỗ brief sai/mơ hồ). Kết quả đúng nên Claude giữ, nhưng ghi lại rằng brief 134 đã **thiếu** file này trong phạm vi — lỗi của Claude khi viết brief: đã biết `TRADING_BACKUP_DIR` sẽ là đường dẫn Windows mà không nghĩ tới `tar`.

### A.6. Việc 3 và kiểm chung

`run_hidden.vbs`: **chỉ** đổi một dòng chú thích, thay danh sách job chép tay bằng câu trỏ về `scripts/sched.sh` — đúng nguyên tắc một nguồn duy nhất, và là lần thứ ba trong dự án một danh sách chép tay bị bỏ đi vì đã lệch.

`ruff` sạch; **1.476 passed**; không có test mới (đợt này là cấu hình máy).

### A.7. Còn lại

- `host-preflight` (brief 133) chưa làm nên chưa có task; xong đợt đó sẽ là task thứ **15**.
- Ba đêm theo dõi NAV: **đêm 1 (29/09) sạch** — 36 dòng trong khung 22:00–23:28, 0 dòng `nav <= 0`, không cảnh báo CONFIRM-1. Còn đêm 30/09 và 01/10.

