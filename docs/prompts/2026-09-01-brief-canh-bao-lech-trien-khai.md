# Brief 2026-09-01 (đợt 7) — Cảnh báo lệch triển khai: code đã sửa mà stack vẫn chạy bản cũ

Dành cho agent thực thi. Tự chứa: đọc file này là đủ để làm.

---

## 1. Vấn đề — đã xảy ra thật, không phải giả định

Từ **15/08 đến 01/09/2026**, `collector` và `engine` chạy image build ngày
15/08. Mọi thay đổi trong `trading/` suốt hai tuần — sizing lệnh thật theo NAV,
GUARD-3, bản sửa watchdog, backoff 429 — **chưa từng chạy**. Không ai biết, kể
cả khi có người kiểm tra "bản sửa đã hoạt động chưa" và kết luận sai vì đang
quan sát code cũ.

`DEPLOYMENT.md §10` (commit `b70c42e`) đã có phép kiểm phát hiện được chuyện này:

```bash
C=$(git log -1 --format=%ct -- trading/)
I=$(date -d "$(docker inspect -f '{{.Created}}' \
     $(docker inspect -f '{{.Image}}' ai_auto_trading_system-collector-1))" +%s)
[ "$I" -ge "$C" ] && echo 'OK: da trien khai' || echo 'CANH BAO: image CU hon commit'
```

**Nhưng nó vẫn cần có người nhớ chạy.** Đó đúng là kiểu phụ thuộc đã gây ra sự
cố gốc: `heartbeat_check.py` viết xong từ lâu, có test đầy đủ, và chưa từng
được cài lịch — công sức nhiều tháng bằng 0 về mặt vận hành cho tới 01/09.

**Việc của bạn: làm cho phép kiểm đó tự kêu.**

---

## 2. Quyết định thiết kế đã chốt — làm đúng, đừng tự đổi

**Viết một script MỚI, `scripts/deploy_drift_check.py`. KHÔNG thêm nhánh vào
`scripts/heartbeat_check.py`.**

Lý do, phải hiểu chứ đừng chỉ tuân theo: `heartbeat_check` là dead-man's switch.
Hiện nó chỉ phụ thuộc **DB + config**. Cho nó gọi thêm `docker` và `git` là mở
rộng đáng kể bề mặt phụ thuộc của chính cái chuông báo — mỗi phụ thuộc mới là
một cách mới để chuông chết câm. Ngày 01/09 đã có một lần như vậy: một lệnh
`print()` thêm vào đã ném `UnicodeEncodeError` và giết chuông báo 5 lần liên
tiếp giữa lúc cần nhất (commit `51ff6de`).

Lệch triển khai **không khẩn cấp theo phút** như service chết. Nó xứng đáng có
chuông riêng, chạy một lần mỗi ngày, hỏng thì không kéo theo cái gì.

---

## 3. Môi trường

- Windows 11, PowerShell + Git Bash. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- `git pull` trước khi làm. HEAD hiện tại: `b70c42e`.
- `docker` và `git` đều gọi được từ Git Bash trên host (đã kiểm).
- Script chạy qua `scripts/run_if_docker_up.sh` — wrapper đã lo `.env`,
  `DB_DSN`, và `PYTHONIOENCODING=utf-8`.
- Lệnh quá 10 phút bị cắt.
- **Không in giá trị secret ra bất cứ đâu.**

---

## 4. Phạm vi phẫu thuật

**Được tạo mới:** `scripts/deploy_drift_check.py`,
`tests/test_deploy_drift_check.py`.

**Được sửa:** `scripts/sched.sh` (thêm đúng một mục vào bảng job),
`DEPLOYMENT.md` (một đoạn ngắn).

**KHÔNG được đụng:** `scripts/heartbeat_check.py` (xem mục 2 — đây là điểm cốt
lõi của brief, không phải gợi ý), `trading/**` toàn bộ, `config/config.yaml`,
`scripts/run_if_docker_up.sh`, `scripts/run_hidden.vbs`,
`scripts/backfill_universe.py`, `scripts/daily_data_check.py`.

> `trading/telegram.py` nằm trong vùng cấm sửa nhưng **bắt buộc dùng lại**:
> `from trading.telegram import send_telegram`. Không viết hàm gửi Telegram mới
> (bài học `4ea4c8d`: một công thức hai bản thì sớm muộn lệch).

---

## 5. Task A — Tách phần tính toán ra khỏi phần I/O

Đây là điều kiện để test được mà không cần Docker.

Viết một hàm **thuần tuý**, không I/O:

```python
def drift_report(commit_epoch: int, images: dict[str, int | None]) -> list[str]
```

- `images`: `{"collector": <epoch build>, "engine": <epoch build>}`; giá trị
  `None` = không đọc được (container không chạy / không có image).
- Trả về danh sách thông điệp cảnh báo; **rỗng = mọi thứ ổn**.

**Phải soi CẢ HAI service.** Đo thật 01/09: `collector` và `engine` là **hai
image khác nhau** (sha256 khác nhau) dù được build trong cùng một lệnh. Suy từ
một cái ra cái kia là sai.

Quy tắc:
- image cũ hơn commit ⇒ cảnh báo, **nêu rõ lệch bao nhiêu** (giờ hoặc ngày) và
  service nào.
- `None` ⇒ cảnh báo riêng ("không đọc được image"), **không** im lặng coi như ổn
  (tiền lệ fail-safe của dự án: thiếu dữ liệu thì từ chối + báo, không bao giờ
  rơi về giá trị dễ dãi — xem `engine/main.py:122-136`).

→ **Kiểm chứng** (`tests/test_deploy_drift_check.py`), không cần Docker:
- cả hai image mới hơn commit ⇒ danh sách **rỗng**
- chỉ `engine` cũ hơn ⇒ đúng **một** cảnh báo, có chữ `engine`, không có
  `collector`
- cả hai cũ hơn ⇒ **hai** cảnh báo
- một image `None` ⇒ có cảnh báo, và **không** bị coi là ổn
- image **bằng đúng** commit_epoch ⇒ coi là ổn (build ngay sau commit)

## 6. Task B — Phần I/O và cảnh báo

Phần đọc thật:
- `commit_epoch`: `git log -1 --format=%ct -- trading/`
- `image_epoch` mỗi service: `docker inspect` lấy `.Image` rồi `.Created`, đổi
  sang epoch.

**Bẫy bắt buộc tránh, đã gặp thật 01/09:** `git log --format=%cI` in giờ theo
**múi địa phương** (`+07:00`) còn `docker inspect` in **UTC** (`Z`). So hai
chuỗi ISO đó bằng toán tử chuỗi cho kết quả **NGƯỢC**:

```
commit 2026-09-01T18:51:10+07:00  (= 11:51:10Z)
image  2026-09-01T13:33:33Z
-> doc thanh "image cu hon"   SAI: image moi hon 1 gio 42 phut
```

**Dùng epoch (`%ct`) cho cả hai phía. Không so chuỗi ISO.**

Hành vi:
- Có cảnh báo ⇒ **in ra stdout TRƯỚC**, rồi `send_telegram`, exit **1**.
- Không có ⇒ exit **0**, in một dòng ngắn xác nhận đã kiểm.
- **In không được phép làm chết script.** Dùng lại đúng khuôn `_print_safe` của
  `scripts/heartbeat_check.py:153` (bọc `print` trong try/except, hạ cấp sang
  ascii). Lý do ở mục 2.

→ **Kiểm chứng thật:** chạy script trên máy này. Hiện tại image (01/09 13:33Z)
mới hơn commit cuối chạm `trading/` nên **kỳ vọng exit 0**. Dán nguyên văn
output.

→ **Kiểm chứng chiều báo động** — bắt buộc, vì một phép kiểm không bao giờ kêu
thì vô dụng: tạm truyền mốc commit mới hơn image (ví dụ commit cuối của **toàn
repo** thay vì chỉ `trading/`) và cho thấy nó **có** kêu. Dán nguyên văn.
**Không** commit thay đổi tạm đó.

## 7. Task C — Cắm vào lịch

1. Thêm job vào `scripts/sched.sh` (bảng job đã có `heartbeat`, `daily-check`,
   `backfill`) — đặt tên `deploy-drift`, log ra `logs/deploy-drift.log`, đi qua
   `run_if_docker_up.sh` như các job khác.
2. Tạo scheduled task Windows chạy **08:00 T2–T6**, qua
   `scripts/run_hidden.vbs` như ba task hiện có (`wscript.exe //B //Nologo
   "...\run_hidden.vbs" deploy-drift`).

Vì sao 08:00: trước giờ mở cửa 09:00. Biết stack đang chạy code cũ **trước**
phiên thì còn kịp xử lý; biết lúc 15:00 thì đã mất một phiên.

→ **Kiểm chứng — bắt buộc là bằng chứng ĐÃ CHẠY, không phải ĐÃ TẠO:**
`schtasks /run /tn <ten>` rồi dán nguyên văn phần mới của `logs/deploy-drift.log`.
"Đã tạo task" không tính — đó đúng là kiểu nhầm lẫn đã dẫn tới sự cố ở mục 1.

3. `DEPLOYMENT.md`: thêm một đoạn ngắn vào §10 nói job này tồn tại, chạy lúc
   nào, và dòng cron Ubuntu tương đương (`0 8 * * 1-5 /opt/trading/scripts/sched.sh deploy-drift`).

## 8. Sabotage (bắt buộc)

Đảo điều kiện so sánh trong `drift_report` (`<` thành `>` hoặc bỏ nhánh `None`)
⇒ test tương ứng phải **ĐỎ**. Khôi phục, chạy lại cho xanh. **Dán nguyên văn
output đỏ.** Test không đỏ khi phá ⇒ test đó không kiểm gì cả.

## 9. Cấm

- **Không commit, không push.** Claude audit rồi mới commit.
- **Không sửa `scripts/heartbeat_check.py`** — trọng tâm thiết kế, xem mục 2.
- **Không sửa gì trong `trading/`.** Không viết hàm gửi Telegram mới.
- **Không bật `real_trading_enabled`** (đã có kết luận `711683a`: engine chỉ
  chạy paper). Không sửa `config/config.yaml`.
- Không gọi API đặt/huỷ lệnh SSI.
- **Không dựng lại container, không `docker compose down/up`.** Task này chỉ
  ĐỌC trạng thái Docker.
- Không `TRUNCATE`, không `DROP`, không xoá dòng nào trong DB (task này không
  đụng DB).
- Không in giá trị secret.
- Vấn đề ngoài phạm vi: **báo cáo**, không tự sửa.
- Trước khi sửa symbol nào: `gitnexus_impact`. Sau khi sửa:
  `gitnexus_detect_changes`, đối chiếu với mục 4.

## 10. Tiêu chí hoàn thành

- Task A: 5 ca test xanh, hàm thuần tuý không I/O.
- Task B: output thật (exit 0) **và** output chiều báo động, cả hai dán nguyên
  văn.
- Task C: `logs/deploy-drift.log` có dòng thật sau khi task chạy; đoạn
  `DEPLOYMENT.md` đã thêm; dòng cron Ubuntu tương đương.
- Output sabotage dán nguyên văn.
- `uv run pytest -m "not integration" -q` xanh (hiện tại: **340 passed**).
- `uv run ruff check trading tests scripts` sạch.
- **Chạy full-suite 2 lần** và xác nhận cùng kết quả — test mới không được chớp
  chờn (đợt 5 đã có 3 test đo đồng hồ thật, hai lần chạy cho hai test khác nhau
  đỏ). Nếu bạn thấy mình đang nới ngưỡng cho test hết đỏ: **dừng lại**, gần như
  luôn nghĩa là đang đo sai đại lượng.

> Nhắc lại điều đã nói ở các brief trước, vì nó vẫn đúng: báo cáo sẽ được kiểm
> bằng cách **chạy lại và đối chiếu số**. Trước khi viết "đã kiểm chứng", tự hỏi:
> *phép đo này có cho ra kết quả này ngay cả khi bản sửa không tồn tại không?*
> Nếu có — nó không kiểm chứng gì cả. **"Chưa đo được" luôn là câu trả lời chấp
> nhận được; một phép đo bịa thì không.**
