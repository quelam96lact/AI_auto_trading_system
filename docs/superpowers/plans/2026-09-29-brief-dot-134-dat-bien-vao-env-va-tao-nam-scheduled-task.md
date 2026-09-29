# Brief đợt 134 — đặt `TRADING_BACKUP_DIR` vào `.env` và tạo năm scheduled task

**Base commit:** `4a9a39b`.
**Người thực thi:** agent. **Claude:** audit, commit, push (đợt này gần như không có gì để commit — xem §5).

---

## §0. Hai giới hạn được chủ dự án BỎ cho đợt này

Từ trước tới nay brief nào cũng ghi *"không sửa `.env` thật"* và *"tạo scheduled task là việc của chủ dự án"*. **Chủ dự án yêu cầu giao cả hai cho agent trong đợt này** (29/09). Ghi lại để không ai tưởng brief này phá quy tắc:

- Agent **được** thêm đúng **một** dòng vào `.env`, theo cách ở §1 (không đọc, không in nội dung).
- Agent **được** tạo scheduled task, theo §2.
- **Các giới hạn khác giữ nguyên:** không commit/push, không đặt lệnh, không gửi Telegram thật, không đọc *giá trị* của bất kỳ biến nào trong `.env`.

---

## §1. Việc 1 — thêm `TRADING_BACKUP_DIR` vào `.env`

Cần dòng: `TRADING_BACKUP_DIR=D:/My_Vault_Obsidian/Project/_backups/db`

Không có nó, ba job hỏng đúng như đợt 132 đã đo: `backup-check` gửi cảnh báo giả mỗi ngày, `disk-check` thoát 2 và không kiểm đĩa, `orderbook-backup` chết ở `mkdir /var`.

### BẪY PHẢI TRÁNH — thêm sai một ký tự là **cả 15 job dừng**

`run_if_docker_up.sh` (đợt 126) thoát **2** nếu `.env` chứa **bất kỳ** ký tự `\r`. Mọi job đều đi qua cổng đó. Trên Windows, `Add-Content` / `Out-File` / `>>` mặc định ghi `\r\n` — **một lần thêm dòng kiểu đó sẽ làm mọi job ngừng chạy**, và triệu chứng duy nhất là `EXIT=2` trong log.

**Bắt buộc:**
1. **Sao lưu `.env` trước** ra ngoài repo (ví dụ `D:/My_Vault_Obsidian/Project/_backups/env/.env.<timestamp>.bak`). Đây là lưới an toàn duy nhất nếu bước ghi làm hỏng file.
2. Thêm bằng cách ghi **byte**, xuống dòng **LF**, ví dụ Python:
   `open(p, "ab").write(b"TRADING_BACKUP_DIR=D:/My_Vault_Obsidian/Project/_backups/db\n")`
   Trước khi thêm, kiểm byte cuối file **đã là** `\n` chưa; chưa thì thêm `\n` trước.
3. **Không đọc, không in nội dung `.env`.** Không `cat`, không `Get-Content`, không dán vào báo cáo.

### Kiểm (chỉ được dùng phép ĐẾM, không in nội dung)

```
grep -c '^TRADING_BACKUP_DIR=' .env      -> phai la 1 (khong nhieu hon: them hai lan la sai)
grep -cU $'\r' .env                       -> phai la 0   (QUAN TRONG NHAT)
wc -l .env  truoc va sau                  -> chenh dung 1
```

Rồi chứng minh cổng vẫn mở: `scripts/sched.sh disk-check` phải **thoát 0** (không còn dòng "Bo qua phep do thu muc sao luu"), và `scripts/sched.sh backup-check` phải **thoát 0 và im lặng**.

Nếu `grep -cU $'\r'` ra khác 0: **phục hồi ngay từ bản sao lưu ở bước 1**, rồi báo lại. Đừng cố sửa tại chỗ.

---

## §2. Việc 2 — tạo năm scheduled task

### Khuôn phải theo đúng 9 task đang có

Claude đã đọc `trading-heartbeat-check`:

```
Execute   : wscript.exe
Arguments : //B //Nologo "D:\My_Vault_Obsidian\Project\AI_auto_trading_system\scripts\run_hidden.vbs" <job>
RunLevel  : Limited      UserId: quelam      LogonType: Interactive
TaskPath  : \
```

**`run_hidden.vbs` nhận ĐÚNG MỘT tham số** (dòng 18: `If WScript.Arguments.Count <> 1 Then WScript.Quit 2`), nên **không thể** truyền đường dẫn thư mục qua task. Đó chính là lý do việc 1 phải làm trước. Chuỗi thấy được biến: `run_hidden.vbs` → `bash -lc sched.sh` → `run_if_docker_up.sh` (nạp `.env`) → job.

**Không dùng quyền admin.** Chín task hiện có đều `Limited` + `Interactive`, tạo được mà không cần elevated — giữ đúng vậy (chú thích đầu `run_hidden.vbs` giải thích vì sao không dùng S4U).

### Năm task

| Tên task | Lịch | Tham số |
|---|---|---|
| `trading-container-health` | mỗi **10 phút**, 24/7 | `container-health` |
| `trading-backup` | **02:00** hằng ngày | `backup` |
| `trading-orderbook-backup` | **02:30** hằng ngày | `orderbook-backup` |
| `trading-backup-check` | **03:00** hằng ngày | `backup-check` |
| `trading-disk-check` | mỗi **6 giờ**, 24/7 | `disk-check` |

Hai task 24/7 dùng trigger ngày kèm lặp (`-RepetitionInterval`), `-RepetitionDuration` đủ 24 giờ. Ba task còn lại là trigger ngày một lần.

**Đặt `-StartWhenAvailable`** cho ba task ban đêm: laptop có thể ngủ/tắt lúc 02:00–03:00, và bỏ hẳn một đêm sao lưu thì `backup-check` sẽ kêu (đúng), nhưng chạy bù khi máy bật lại thì tốt hơn. Nêu rõ lựa chọn này trong báo cáo, kèm việc 9 task cũ đang đặt `StartWhenAvailable=False`.

### Kiểm — task đăng ký xong KHÔNG có nghĩa là nó chạy được

Bài học `docker-sap-lam-mat-ngay-nen`: một task sai đường dẫn vẫn "Ready" và im lặng không bao giờ làm gì. Vì vậy với **mỗi** task:

1. `Start-ScheduledTask` để chạy ngay một lần.
2. Chờ xong, rồi đọc `(Get-ScheduledTaskInfo <ten>).LastTaskResult` — phải là **0**.
3. Mở **file log tương ứng** trong `logs/` và chứng minh có dòng mới **của lần chạy này** (so mốc thời gian): `container-health.log`, `backup.log`, `orderbook-backup.log`, `backup-check.log`, `disk-check.log`.
4. Dán nguyên văn cả ba bằng chứng cho từng task.

**Dự kiến:** `trading-backup` sẽ tạo một bản dump khoảng 100 MB thật trong `_backups/db` — đúng ý, giữ lại. `orderbook-backup` có thể in "nothing to back up" nếu bản sao lưu sổ lệnh gần nhất đã bao trùm các file hiện có; đó **không** phải lỗi, nhưng phải nói rõ là trường hợp nào.

### Đối chiếu cuối

- `Get-ScheduledTask | ? TaskName -like 'trading-*'` phải ra **14** task.
- Đối chiếu tập tham số của 14 task với tập job của `scripts/sched.sh`: nêu rõ job nào **có trong `sched.sh` mà chưa có task** và vì sao (dự kiến: `host-preflight` chưa tồn tại — brief 133 chưa làm; `stream-health` đã có task).

---

## §3. Việc 3 — cập nhật chú thích đã lạc hậu trong `run_hidden.vbs`

Dòng 12 liệt kê job hợp lệ và **đang thiếu** nhiều job thêm từ các đợt sau (`orderbook-recorder`, `orderbook-daily-check`, `container-health`, `backup`, `backup-check`, `orderbook-backup`, `disk-check`). Sửa thành câu trỏ về nguồn duy nhất — `scripts/sched.sh` — thay vì chép lại danh sách lần nữa (danh sách chép tay đã lệch hai lần trong dự án này: `README_VPS_UBUNTU.md` đợt 131 và chính dòng này).

**Chỉ sửa chú thích**, không đổi một dòng code nào của `.vbs`.

---

## §4. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)   → ≥ 1.476 passed, 0 failed
uv run ruff check trading tests scripts        → sạch
grep -cU $'\r' .env                             → 0
Get-ScheduledTask trading-*                     → 14 task
```

Không có test mới trong đợt này (việc này là cấu hình máy, không phải code).

## §5. Phạm vi

**Được sửa:** `.env` (**đúng một dòng thêm**, theo §1); scheduled task của Windows; `scripts/run_hidden.vbs` (**chỉ chú thích**); báo cáo `docs/superpowers/research/2026-09-29-dot-134-env-va-scheduled-task.md`.

**KHÔNG được đụng:** mọi file khác trong repo; `trading/`; `scripts/` (trừ chú thích `.vbs`); `docker-compose.yml`; `DEPLOYMENT.md`; 9 task `trading-*` **đã có** (không sửa, không xoá, không đổi lịch); container đang chạy; các file trong `_backups/` (chỉ được **thêm**).

## §6. Điều cấm

- **Không commit, không push.**
- **Không đọc, không in giá trị bất kỳ biến nào trong `.env`.** Chỉ dùng `grep -c`.
- Không xoá hay sửa 9 task cũ. Không cần quyền admin — nếu một bước đòi elevated, **dừng và báo**, đừng tìm đường lách.
- Không gửi Telegram thật; không kết nối SSI; không đặt lệnh; không `--send`; không bật `real_trading_enabled`.
- Không rebuild, không restart container.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- **Không chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`** (việc của Claude thứ Bảy).

## §7. Báo cáo phải có

1. Việc 1: đường dẫn bản sao lưu `.env`, và **ba con số đếm** (`^TRADING_BACKUP_DIR=` = 1, `\r` = 0, `wc -l` chênh 1). **Không dán nội dung `.env`.**
2. Việc 1: `sched.sh disk-check` và `sched.sh backup-check` sau khi thêm biến — mã thoát và dòng log, nguyên văn.
3. Việc 2: với **mỗi** trong năm task — định nghĩa (Execute/Arguments/trigger), `LastTaskResult`, và dòng log mới có mốc thời gian khớp. Nguyên văn.
4. Việc 2: số task `trading-*` cuối cùng, và bảng đối chiếu với tập job của `sched.sh` (job nào chưa có task, vì sao).
5. Việc 3: diff của `run_hidden.vbs`.
6. Những gì **không** làm được, và vì sao (ví dụ bước nào đòi quyền admin).
7. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào**, báo ngay.
