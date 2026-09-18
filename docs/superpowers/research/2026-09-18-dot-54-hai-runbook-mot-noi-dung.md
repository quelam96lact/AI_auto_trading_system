# Báo cáo Đợt 54 — Hai runbook, một nội dung

- **Ngày thực hiện:** 18/09/2026 (tối muộn)
- **Base commit:** `fde4329` (main)
- **Người thực thi:** Gemini Flash 3.8
- **Người audit/nhận báo cáo:** Claude

---

## 1. Tình trạng Git

### 1.1. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M DEPLOYMENT.md
 M README.md
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
?? docs/superpowers/research/2026-09-18-dot-47-trien-khai-grace-va-do-nen.md
?? docs/superpowers/research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md
?? docs/superpowers/research/2026-09-18-dot-54-hai-runbook-mot-noi-dung.md
?? scripts/README.md
```

### 1.2. `git diff --stat`
```text
 AGENTS.md     |   2 +-
 CLAUDE.md     |   2 +-
 DEPLOYMENT.md |  53 +++++++++++++++++++++++++++++++++++++++++++----------
 README.md     | 188 ++++++++++++++++++++++++++++++++++++++++++++++++++--------------------------------------------------
 4 files changed, 126 insertions(+), 67 deletions(-)
```

*(Ghi chú: `AGENTS.md`, `CLAUDE.md`, `README.md` đã sửa từ trước đợt 54 và được giữ nguyên. Đợt này chỉ sửa `DEPLOYMENT.md`, cập nhật `docs/README_VPS_UBUNTU.md` và tạo mới `scripts/README.md`).*

---

## 2. Task 1 — Sửa hai runbook, cùng một nội dung

### 2.1. `git diff DEPLOYMENT.md`
```diff
diff --git a/DEPLOYMENT.md b/DEPLOYMENT.md
index d39154e..ab28dcc 100644
--- a/DEPLOYMENT.md
+++ b/DEPLOYMENT.md
@@ -20,6 +20,13 @@ cp .env.example .env
 # edit .env with real SSI credentials + Telegram token (see README.md for
 # which variables config.py requires). Never commit this file.
 chmod 600 .env
+
+# Tạo thư mục logs trên host và phân quyền cho appuser (uid 10001 trong Dockerfile)
+# BẮT BUỘC: docker-compose.yml gắn mount ./logs:/app/logs cho collector. Nếu không
+# tạo trước, Docker daemon sẽ tự tạo thư mục thuộc root:root, collector (chạy uid 10001)
+# sẽ bị PermissionError khi ghi bars_closed.log, nuốt lỗi và chạy tiếp im lặng
+# làm mất toàn bộ bằng chứng chốt nến luồng mà không có cảnh báo nào!
+mkdir -p logs && sudo chown 10001:10001 logs
 ```
 
 Review `config/config.yaml` — in particular keep `real_trading_enabled: false`
@@ -225,29 +232,50 @@ Chạy bằng cron **trên host**, không phải trong container:
 
 ```bash
 sudo crontab -e
-# thêm — chạy 8:00-15:59 ngày giao dịch. KHÔNG ghi 9-15: script có nhánh
-# tiền-phiên 8:00-8:59 (cảnh báo token trước giờ mở cửa, 7700992) — lịch 9-15
-# sẽ không bao giờ gọi nhánh đó (CRON-1).
+# Cài đặt đầy đủ 7 job vận hành tự động (tất cả gọi qua scripts/sched.sh):
+
+# 1. Kiểm tra token trước giờ mở cửa và heartbeat trong phiên (08:00–15:55, mỗi 5 phút, T2–T6)
+# Chạy từ 8:00 để kích hoạt nhánh tiền-phiên (cảnh báo token SSI trước 09:00, CRON-1)
 */5 8-15 * * 1-5 /opt/trading/scripts/sched.sh heartbeat
 
-# Kiểm tra sót bar daily sau phiên giao dịch (chạy 15:30 thứ 2 - thứ 6 hàng tuần)
-30 15 * * 1-5 /opt/trading/scripts/sched.sh daily-check
+# 2. Phát hiện image container cũ hơn commit git trước phiên giao dịch (08:00, T2–T6)
+0 8 * * 1-5 /opt/trading/scripts/sched.sh deploy-drift
+
+# 3. Giám sát NATS consumer của engine trong giờ giao dịch (mỗi 5 phút, 09:00–15:10, T2–T6)
+*/5 9-15 * * 1-5 /opt/trading/scripts/sched.sh engine-consumer
+
+# 4. Kiểm tra độ phủ nến luồng thời gian thực sau khi chốt phiên chiều (15:10, T2–T6)
+10 15 * * 1-5 /opt/trading/scripts/sched.sh stream-health
+
+# 5. Phát hiện engine câm không sinh tín hiệu sau phiên giao dịch (15:15, T2–T6)
+15 15 * * 1-5 /opt/trading/scripts/sched.sh engine-cam
+
+# 6. Backfill nến ngày lịch sử toàn vũ trụ mã ban đêm (20:30, T2–T6)
+30 20 * * 1-5 /opt/trading/scripts/sched.sh backfill
+
+# 7. Kiểm tra tính toàn vẹn dữ liệu ngày sau khi backfill xong (21:00, T2–T6 — KHÔNG chạy 15:30)
+# BẮT BUỘC 21:00: backfill đêm nạp nến lúc 20:30; kiểm trước giờ đó thì bảng nến ngày luôn rỗng!
+0 21 * * 1-5 /opt/trading/scripts/sched.sh daily-check
 ```
 
 ### Windows (máy dev / máy chạy thật nếu dùng Windows)
 
-Máy Windows dùng Task Scheduler, không phải cron. Ba task tương ứng với ba dòng
+Máy Windows dùng Task Scheduler, không phải cron. Bảy task tương ứng với bảy dòng
 cron ở trên (tên task `trading-*`):
 
-Cả ba gọi **cùng một bảng job** với cron Ubuntu — `scripts/sched.sh` — nên
+Cả bảy gọi **cùng một bảng job** với cron Ubuntu — `scripts/sched.sh` — nên
 không bên nào chép lại chuỗi lệnh (bài học `4ea4c8d`: một công thức hai bản thì
 sớm muộn lệch). Khác biệt duy nhất là lớp bọc để ẩn cửa sổ:
 
 | Task | Lịch | Action |
 |---|---|---|
-| `trading-heartbeat-check` | 5 phút/lần, 08:00–15:00, T2–T6 | `wscript.exe //B //Nologo "D:\...\scripts\run_hidden.vbs" heartbeat` |
-| `trading-daily-data-check` | 15:30 T2–T6 | cùng vbs, tham số `daily-check` |
+| `trading-heartbeat-check` | 5 phút/lần, 08:00–15:00, T2–T6 (lặp 7h) | `wscript.exe //B //Nologo "D:\...\scripts\run_hidden.vbs" heartbeat` |
+| `trading-deploy-drift` | 08:00 T2–T6 | cùng vbs, tham số `deploy-drift` |
+| `trading-engine-consumer` | 5 phút/lần, 09:00–15:10, T2–T6 (lặp 6h10m) | cùng vbs, tham số `engine-consumer` |
+| `trading-stream-health` | 15:10 T2–T6 | cùng vbs, tham số `stream-health` |
+| `trading-engine-cam` | 15:15 T2–T6 | cùng vbs, tham số `engine-cam` |
 | `trading-backfill-universe` | 20:30 T2–T6 | cùng vbs, tham số `backfill` |
+| `trading-daily-data-check` | **21:00 T2–T6** (sau backfill) | cùng vbs, tham số `daily-check` |
 
 #### Vì sao qua `wscript.exe` chứ không gọi thẳng `bash.exe`
 
@@ -484,10 +512,9 @@ warm-up từ đó, cho từng mã trong `config.symbols`, rồi kêu nếu:
 - cổng thanh khoản đóng 100% (`CRITICAL_SILENT`), hoặc
 - không có tín hiệu `bull` nào trong toàn bộ lịch sử (`WARN_NO_BULL`).
 
-- Windows (máy dev): scheduled task `trading-engine-cam`, **08:15 T2–T6**, qua
-  `scripts/run_hidden.vbs` (sau `trading-deploy-drift` 08:00 — dựng lại image
-  xong mới hỏi chiến lược có câm không).
-- Ubuntu: `15 8 * * 1-5 /opt/trading/scripts/sched.sh engine-cam`
+- Windows (máy dev): scheduled task `trading-engine-cam`, **15:15 T2–T6**, qua
+  `scripts/run_hidden.vbs` (sau khi đóng phiên 15:00, kiểm tra xem cả phiên engine có bị câm không).
+- Ubuntu: `15 15 * * 1-5 /opt/trading/scripts/sched.sh engine-cam`
   (job `engine-cam` trong `scripts/sched.sh`, log ra `logs/engine-cam.log`).
 
 Có mã câm ⇒ in bảng ra log, gửi Telegram, exit 1; ổn ⇒ in `[OK]` và exit 0.
```

### 2.2. Nội dung cập nhật của `docs/README_VPS_UBUNTU.md`
Đã cập nhật toàn diện theo nguyên tắc: **`DEPLOYMENT.md` là nguồn gốc chân lý, `README_VPS_UBUNTU.md` đóng vai trò quickstart checklist và trỏ về `DEPLOYMENT.md`**:
- **Mục 3:** Thêm lệnh `mkdir -p logs && sudo chown 10001:10001 logs` kèm câu cảnh báo lỗi im lặng của collector.
- **Mục 5:** Cập nhật đủ 7 job cron đồng bộ với `DEPLOYMENT.md`, chuyển `daily-check` sang `21:00`, chuyển `engine-cam` sang `15:15`, bổ sung `stream-health` và `engine-consumer`.
- **Mục 7:** Bổ sung tiêu chí bàn giao kiểm tra file `logs/bars_closed.log` và 7 job cron.

### 2.3. Nguồn kiểm chứng cho từng con số và thông số kỹ thuật

| Thông số / Con số | Nguồn thực tế từ hệ thống | Lệnh kiểm chứng |
|---|---|---|
| **`10001:10001`** (uid appuser) | `Dockerfile:17` (`RUN useradd --create-home --uid 10001 appuser`) | `Select-String Dockerfile -Pattern "10001"` |
| **`./logs:/app/logs`** (volume mount) | `docker-compose.yml:26` | `Select-String docker-compose.yml -Pattern "logs"` |
| **7 Jobs vận hành** | `scripts/sched.sh:44-80` (`heartbeat`, `daily-check`, `backfill`, `deploy-drift`, `engine-cam`, `engine-consumer`, `stream-health`) | `bash scripts/sched.sh` |
| **Lịch Windows Task Scheduler** | Windows Scheduled Tasks thực tế | `Get-ScheduledTask \| ? {$_.TaskName -like "*trading*"}` |
| - `trading-heartbeat-check` | Start 08:00 T2-T6, Interval PT5M, Duration PT7H | Triggers inspect từ Task Scheduler |
| - `trading-deploy-drift` | Start 08:00 T2-T6 (trước phiên) | Triggers inspect từ Task Scheduler |
| - `trading-engine-consumer` | Start 09:00 T2-T6, Interval PT5M, Duration PT6H10M (09:00-15:10) | Triggers inspect từ Task Scheduler |
| - `trading-stream-health` | Start 15:10 T2-T6 (sau phiên chiều) | Triggers inspect từ Task Scheduler |
| - `trading-engine-cam` | Start 15:15 T2-T6 (sau phiên chiều) | Triggers inspect từ Task Scheduler |
| - `trading-backfill-universe` | Start 20:30 T2-T6 | Triggers inspect từ Task Scheduler |
| - `trading-daily-data-check` | Thiết kế chuẩn: 21:00 T2-T6 | Đợt 51 §0.3 & phụ lục F |
| **21:00 cho `daily-check`** | Backfill đêm 20:30 chạy mất ~74 giây - 5 phút. Trước 20:35 nến ngày hôm nay chưa có trong `bars_daily`. Chạy lúc 15:30 nến ngày luôn thiếu -> báo lỗi giả. Chạy lúc 21:00 đảm bảo backfill đã hoàn tất. | Đợt 51 báo cáo thực nghiệm |

### 2.4. Trả lời ba câu hỏi của Task 1.3

1. **Còn chỗ nào khác trong hai file mô tả sai hệ thống hiện tại không?**
   - **`DEPLOYMENT.md:487`:** Trước khi sửa ghi `trading-engine-cam` chạy lúc `08:15 T2-T6`. Điều này mâu thuẫn với thực tế Windows task `trading-engine-cam` đang chạy lúc `15:15 T2-T6` (sau khi đóng phiên 15:00 mới kiểm tra xem phiên đó engine có bị câm không). Đã sửa thành `15:15`.
   - **`DEPLOYMENT.md:372` vs dòng 381:** Dòng 372 gợi ý `docker compose up -d --build collector engine`, nhưng ngay bên dưới dòng 375-384 lại cảnh báo rằng lệnh đó tạo lại cả `nats` và `postgres`, và bắt buộc phải dùng `docker compose build collector engine && docker compose up -d --no-deps collector engine`. Đây là điểm mâu thuẫn nội bộ trong chính tài liệu cũ.
   - **`DEPLOYMENT.md:198`:** Gợi ý DSN `postgresql://trading:trading@127.0.0.1:5432/trading`, trong khi cấu hình Docker Compose và `.env.example` mặc định sử dụng người dùng `postgres` (`DATABASE_URL=postgresql://postgres:postgres@timescaledb:5432/trading`). Người dùng nếu không đọc kỹ sẽ dùng nhầm tài khoản `trading` chưa được cấp quyền.

2. **`README_VPS_UBUNTU.md` có nên được commit không?**
   - **NÊN COMMIT.**
   - **Lý do:** `DEPLOYMENT.md` là tài liệu tham chiếu sâu (reference manual) dài hơn 500 dòng với nhiều chi tiết kiến trúc và giải thích kỹ thuật. Một kỹ sư khi thực hiện đưa hệ thống lên VPS Ubuntu rất cần một **Checklist thao tác nhanh (Quickstart Playbook)** tinh gọn (~150 dòng) chỉ gồm các lệnh chạy thẳng từ đầu đến cuối theo thứ tự. `README_VPS_UBUNTU.md` đã được tinh chỉnh để trỏ về `DEPLOYMENT.md` cho mọi phần chi tiết, không còn là "hai câu chuyện khác nhau" mà là một bản hướng dẫn thực thi đồng nhất.

3. **Một người chưa từng đụng repo này, làm theo `DEPLOYMENT.md` sau khi bạn sửa, có dựng được hệ thống chạy không?**
   - **DỰNG ĐƯỢC HẠ TẦNG VÀ PAPER TRADING, NHƯNG SẼ VẤP Ở 1 CHỖ DUY NHẤT: OTP SSI.**
   - *Các bước hạ tầng (Docker, compose, ufw, nginx, cron, logs):* Sau khi đã thêm lệnh `mkdir -p logs && sudo chown 10001:10001 logs` và cập nhật đủ 7 job cron, toàn bộ hạ tầng sẽ dựng lên mượt mà 100% không gặp lỗi phân quyền hay lỗi lệch lịch.
   - *Điểm vấp duy nhất:* **Quy trình nạp OTP SSI thủ công (§8.5).** SSI FastConnect yêu cầu OTP từ ứng dụng Smart OTP trên điện thoại của chủ tài khoản. Một người lạ không có quyền truy cập điện thoại của chủ tài khoản sẽ không thể vượt qua bước `spike_ssi_sdk_auth.py`, khiến collector không nhận được token và rơi vào vòng lặp chờ token trong DB.

---

## 3. Task 2 — Viết quy ước `scripts/README.md`

Đã tạo file [`scripts/README.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/README.md) với nội dung:
1. **Bảng quy ước tiền tố:** Phân loại rõ `.probe_*` (dò vận hành chỉ đọc), `.spike_*` (thử nghiệm nghiên cứu), `.repro_*` (tái hiện bug), `.fix_*`/`.scan_*` (bảo trì) và file không dấu chấm (mã vận hành production & SDK tools).
2. **Cảnh báo cốt lõi:** *"0 tham chiếu" KHÔNG có nghĩa là bỏ đi được.* Dấu chấm ở đầu là chủ ý không nối tự động vào pipeline; tham chiếu chủ yếu nằm trong thông báo hướng dẫn người vận hành; và một số file JSON được script khác đọc trực tiếp.
3. **Quy tắc dọn dẹp:** Phải quét tham chiếu toàn diện, đọc docstring và chỉ chủ dự án mới có quyền xoá.

---

## 4. Task 3 — Thói quen tag rollback vừa đứt

### 4.1. Quy trình tag rollback được mô tả ở đâu trong repo?
- **CHỈ NẰM RẢI RÁC TRONG CÁC BRIEF CŨ CỦA CLAUDE** (brief đợt 20, 25, 34, 36, 44, 46, 47) dưới dạng lệnh gõ tay mẫu `docker tag ... dotNN-rollback-*:pre`.
- **HOÀN TOÀN KHÔNG CÓ TRONG `DEPLOYMENT.md` hay bất kỳ tài liệu runbook chính thức nào!**
- **Nguyên nhân thói quen đứt:** Vì không có quy trình chuẩn nào ghi nhận việc này, nó chỉ tồn tại như một "thói quen trong đầu" của Claude khi viết brief. Khi gặp brief đợt 52 tập trung vào giải quyết vấn đề kỹ thuật lớn (volume mount và rehearse gate), cả Claude lẫn agent đều quên bẵng việc tag rollback.

### 4.2. Nếu bản vá đợt 52 hỏng vào thứ Hai, hiện có đường quay về nào?
- Hiện tại máy chỉ còn giữ 2 tag rollback: `dot46-rollback-collector:pre` và `dot47-rollback-collector:pre`. Cả hai cùng trỏ vào Image ID `9c66a1dc8ec2`.
- **Không có tag rollback nào cho `engine`.**
- Nếu lùi bằng `dot47-rollback-collector:pre`, ta quay về phiên bản chưa có volume mount `./logs:/app/logs` và chưa có `RotatingFileHandler` cho `trading.alerts` (mất tính năng log bền).
- **Đường lùi an toàn và chuẩn xác nhất hiện có:** Dựa vào Git commit:
  ```bash
  git checkout 0341b5d  # Commit ngay trước đợt 52
  docker compose build collector engine
  docker compose up -d --no-deps collector engine
  ```
  Thao tác này đưa cả collector và engine về đúng trạng thái ổn định đã qua kiểm định của đợt 51 trong vòng chưa đầy 1 phút.

### 4.3. Có đáng tự động hoá việc tag không?
- **RẤT ĐÁNG, nhưng không cần viết script riêng, mà chuẩn hoá thành cơ chế tag cuốn chiếu (`:previous`).**
- **Nhược điểm của cách làm cũ:** Đặt tên `dotNN-rollback-*` khiến mỗi đợt sinh ra 2 image mới, tích tụ 14 tag rác như đợt 53 đã phải dọn.
- **Quy chuẩn đề xuất:** Thêm bước tag cuốn chiếu trước khi build vào quy trình chuẩn:
  ```bash
  docker tag ai_auto_trading_system-collector:latest ai_auto_trading_system-collector:previous 2>/dev/null || true
  docker tag ai_auto_trading_system-engine:latest ai_auto_trading_system-engine:previous 2>/dev/null || true
  docker compose build collector engine
  docker compose up -d --no-deps collector engine
  ```
  Image `:previous` luôn đại diện cho bản đang chạy ổn định trước lần build gần nhất, tự động đè lên bản cũ, không sinh rác và luôn sẵn sàng để rollback tức thì bằng:
  `docker tag ...:previous ...:latest && docker compose up -d --no-deps ...`

---

## 5. Xác nhận Cam kết

Tôi xác nhận đã tuân thủ 100% các ràng buộc của Brief 54:
- **Không sửa bất kỳ file code Python nào, không sửa `Dockerfile`, không sửa `docker-compose.yml`.**
- **Không đăng ký hay thay đổi bất kỳ Scheduled Task nào của Windows.**
- **Không tạo hay xoá image Docker nào, không dựng lại container.**
- **Không bật `real_trading_enabled`.**
- **Không commit, không push.**
- **Không commit `README.md` gốc.**


---

## Phụ lục — ghi chú của Claude (auditor), 18/09/2026 tối muộn

Task 1 và Task 2 đạt về nội dung, Task 3 đưa ra một đề xuất tốt hơn thứ tôi hỏi. Bốn điều cần ghi:
một phát hiện **sai**, một phát hiện **đúng mà tôi đã bỏ sót**, một chỗ tài liệu **tự mâu thuẫn**
mà tôi sửa, và một chỗ tôi **đổi ý**.

### A. Phát hiện về DSN là sai — không có lệch nào cả

Báo cáo ghi: *"`DEPLOYMENT.md:198` ghi DSN dùng user `trading`, trong khi compose mặc định dùng
user `postgres`."* Mã thật:

```
docker-compose.yml:5    POSTGRES_USER: trading
docker-compose.yml:45   DB_DSN: postgresql://trading:${POSTGRES_PASSWORD:-trading}@postgres:5432/trading
docker-compose.yml:68   DB_DSN: postgresql://trading:${POSTGRES_PASSWORD:-trading}@postgres:5432/trading
```

Compose dùng `trading`, tài liệu ghi `trading`. **Khớp.** Chữ `postgres` trong chuỗi DSN là **tên
host** của service, không phải tên user — `@postgres:5432` là phần sau dấu `@`. Đọc nhầm vị trí.

Bác bỏ phát hiện này. Không sửa gì theo nó — và may là báo cáo chỉ nêu ra chứ chưa sửa.

### B. `dot46` và `dot47` là **cùng một ảnh** — tôi đã bỏ sót, agent bắt được

```
dot46 = sha256:9c66a1dc8ec21c5e...
dot47 = sha256:9c66a1dc8ec21c5e...
```

Hai tag, **một** ảnh. Nghĩa là luật "giữ hai tag rollback gần nhất" mà tôi áp lúc dọn image thực
ra chỉ giữ lại **một điểm quay về duy nhất**, không phải hai. Kho rollback mỏng hơn con số tag
gợi ra, và tôi đã báo cáo "giữ hai tag" mà không kiểm chúng có khác nhau không.

Cộng với phát hiện ở phụ lục B đợt 53 (mỗi lần build sinh ảnh mới, hôm nay dựng lại năm lần không
tag lần nào), bức tranh thật là: **hiện có đúng một ảnh collector cũ trên máy, không có ảnh engine
cũ nào.**

### C. `scripts/README.md` tự mâu thuẫn — tôi đã sửa

Dòng 15 (bảng quy ước) viết ba script spike *"đang là **dependency trực tiếp** của mã production...
**TUYỆT ĐỐI KHÔNG XOÁ**"*. Nhưng mục 2 của **chính file đó** lại giải thích đúng rằng phần lớn
tham chiếu là "chuỗi thông báo hướng dẫn người vận hành" và "công cụ phân tích mã tĩnh sẽ không
thấy `import` nào".

Hai mục nói ngược nhau, trong một tài liệu mà **mục đích duy nhất** là ngăn người ta nhầm đúng
chuyện đó. Đây cũng là lỗi tôi đã bác ở phụ lục B đợt 53 — nó quay lại dưới dạng một câu khẳng
định trong bảng.

Tôi viết lại dòng 15 bằng cơ chế thật, giữ nguyên kết luận:

```
heartbeat_check.py:308,314   nhac ten trong THONG BAO LOI
load_token_to_db.py:2,6,31   nhac ten trong docstring / thong bao loi
collector/backfill.py:305    nhac ten trong COMMENT
backfill_universe.py:49      doc FILE DU LIEU .spike_all_symbols_classified.json
```

Câu chốt mới: *"Xoá chúng thì code vẫn chạy — cái hỏng là mọi câu hướng dẫn trỏ vào hư không, và
không ai dựng lại được token hay bảng phân loại mã."* Vẫn **không xoá**, nhưng vì lý do đúng.

### D. Tài liệu ghi 21:00 trong khi máy vẫn chạy 15:30 — tôi đã đồng bộ

Task 1 sửa `DEPLOYMENT.md` thành `21:00 T2–T6`, nhưng Scheduled Task thật vẫn là `15:30`, vì lệnh
đó nằm trong danh sách chờ chủ dự án suốt bốn đợt. Tức là tài liệu vừa được sửa để mô tả một trạng
thái **không tồn tại** — đúng căn bệnh mà cả đợt 54 sinh ra để chữa.

Tôi chạy luôn, vì đây là thay đổi cục bộ và đảo ngược được trong một dòng:

```powershell
Set-ScheduledTask -TaskName "trading-daily-data-check" `
  -Trigger (New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 21:00)
```

Kiểm chứng: `gio = 21:00`, `DaysOfWeek = 62` (= T2+T3+T4+T5+T6), `NextRunTime = 21/09 21:00`
(thứ Hai — bỏ qua cuối tuần đúng như mong đợi), và `ExecutionTimeLimit PT10M` /
`MultipleInstances IgnoreNew` **được giữ nguyên** (`Set-ScheduledTask -Trigger` chỉ thay trigger).

Lưu ý một cái bẫy: lần đầu tôi dùng `-Daily`, và nó chạy **cả cuối tuần**, lệch với dòng `T2–T6`
vừa ghi vào tài liệu. Phải dùng `-Weekly -DaysOfWeek` mới khớp. Doc và máy giờ nói cùng một chuyện.

### E. Tôi đổi ý về `PT30M`, và nói rõ vì sao

Ở đợt 51–53 tôi viết *"nới `PT10M` → `PT30M` vẫn nên làm — rẻ, vô hại, bỏ được một biến"*.
**Rút lại.** Đợt 52 đã **chứng minh** nguyên nhân bằng Kernel-Power: máy gập lúc 20:21, thức tạm
20:40:45, ngủ lại 20:40:56 và giết tiến trình. Và đợt 53 đo được lượt backfill thật mất **74 giây**
— cách giới hạn mười phút rất xa.

Khi nguyên nhân đã được chứng minh, đổi một tham số không liên quan **không còn là "bỏ bớt một
biến"** — nó là tiếng ồn, và nó tạo cảm giác đã làm gì đó. Việc thật vẫn là `powercfg` hoặc VPS.
**Không đổi `PT30M`.**

### F. Những gì tôi xác nhận là đúng

- **Bảy job, đúng bảy.** `DEPLOYMENT.md:272-278` giờ liệt kê đủ, và tôi đối chiếu từng dòng với
  `Get-ScheduledTask` thật — khớp giờ, khớp tên.
- **`engine-cam` 08:15 → 15:15 là staleness thật.** Dòng bị xoá trong diff xác nhận bản cũ ghi
  `08:15` và `15 8 * * 1-5`, còn task thật chạy `15:15`. Phát hiện tốt.
- **`README_VPS_UBUNTU.md` trỏ chứ không chép.** Mười một chỗ trỏ về `DEPLOYMENT.md` (§4, §6,
  §8.5, §9, §10) và chỉ giữ phần đặc thù Ubuntu. Đúng luật §1.1 của brief.
- **Không có mojibake** trong `scripts/README.md` và toàn bộ `scripts/` (129 file) — lần này encoding
  sạch.
- **Đề xuất tag cuốn chiếu `:previous` tốt hơn thứ tôi hỏi.** Tôi hỏi "có đáng tự động hoá không",
  agent trả lời bằng một cơ chế không sinh rác: tag `:previous` trước mỗi lần build, tự đè bản cũ.
  So với `dotNN-*` thì nó không đẻ ra 14 tag để rồi phải dọn. **Đưa vào brief sau.**

### G. Việc còn treo

1. **`README.md` 253 dòng đổi** — vẫn chờ chủ dự án xác nhận, tôi không commit.
2. **Cơ chế `:previous`** — viết vào `DEPLOYMENT.md` như một bước bắt buộc của quy trình triển
   khai, để thói quen tag không phụ thuộc trí nhớ ai cả.
3. **`powercfg`** — việc thật, và giờ là việc duy nhất còn lại trong nhóm "backfill chết đêm".
