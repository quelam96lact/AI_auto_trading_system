# Brief đợt 14 — Mắt xích cuối của đường dữ liệu VPS + nguyên nhân mất bar 06-07/07

Người viết: Claude (planner) | Ngày: 2026-09-07 | HEAD: `14d9fa5`

---

## 0. Tình hình sau khi D1 đóng và đợt 13 xong

Tự kiểm hôm nay, không đọc tài liệu cũ:

| | |
|---|---|
| **D1 (dead-man's switch)** | **ĐÓNG** — chuông kêu thật, độ trễ 3'28", chuông token cũng kêu đúng và được xử lý trong phiên |
| **Đợt 13** | Xong — bản sao lưu đã chứng minh phục hồi được (55,5 MB, 15/15 bảng, hypertable khớp); tên container hardcode đã gỡ |
| **Lệch triển khai 14 phút** | **VẪN CÒN** — `deploy_drift_check.py` vẫn báo. Việc của chủ dự án, diễn tập đã xong nên không còn lý do hoãn |
| **`trading-engine-cam`** | **CHƯA TẠO** — `schtasks` chỉ có 4 task: backfill-universe, daily-data-check, deploy-drift, heartbeat-check. Đây là mục còn lại của C2 |
| **`bars_daily` độ phủ** | Tụt từ ~965 mã (28/08) xuống **175 mã** (03/09 trở đi) — **đúng thiết kế** sau khi tách vai universe, không phải hỏng. Hệ quả cần nhớ: mọi phép đo rổ đầy đủ 1.308 mã **không tái lập được** trên dữ liệu sau 02/09 |
| Ngày lễ 31/08, 01/09, 02/09 | Vắng trong `bars_daily` là **đúng** — đã khai trong `config.yaml` |

Hai việc giao được cho agent, nêu ở dưới. Việc còn lại là của chủ dự án
(rebuild image, tạo task `trading-engine-cam`, quyết định Tier 1 / VPS).

---

## 1. Task 1 — Kiểm mắt xích CUỐI CÙNG chưa test của đường dữ liệu VPS

### Vì sao task này tồn tại

Đợt 13 chứng minh `pg_dump` của TimescaleDB **không** dính bẫy hypertable rỗng.
Nhưng nó chứng minh bằng cách chạy dump **bên trong container** — nó **không
chạy `scripts/backup_db.sh`**. Tôi đã tự ghi hạn chế này vào báo cáo đợt 13.

Chỗ chưa test lại đúng là chỗ sẽ dùng thật khi chuyển VPS:

```bash
# backup_db.sh dòng 17 — dữ liệu đi qua ỐNG trên HOST rồi mới thành file
docker compose exec -T postgres pg_dump -U trading trading | gzip > "$OUT_FILE"
```

Kịch bản chuyển VPS là: **dump trên máy Windows này → mang file sang VPS →
restore**. Nghĩa là cái ống trên host Windows nằm ngay giữa đường, và nếu nó
làm hỏng luồng nhị phân (chuyện có thật với chuyển hướng trên Windows) thì
file dump hỏng **im lặng** — chỉ phát hiện khi restore, tức là lúc dữ liệu gốc
có thể đã không còn.

Đây là dữ liệu 5 phút mà **SSI không phục vụ lại được** (đợt 11: trần ~150
ngày). Không được đoán, phải đo.

### File được sửa/tạo
- **TẠO MỚI:** `scripts/verify_backup_file_roundtrip.py`
- **KHÔNG SỬA:** `scripts/backup_db.sh` (đang kiểm nó — sửa là mất đối tượng
  kiểm), `scripts/verify_backup_restore.py` (đợt 13, đã audit), `trading/**`,
  `docker-compose.yml`, `config/config.yaml`.

### DÙNG LẠI, KHÔNG CHÉP
`scripts/verify_backup_restore.py` (đợt 13) đã có sẵn: `run_docker_exec`,
`exec_psql`, `query_count`, `TABLES_TO_CHECK`, `COUNT_FAILED`, và quy tắc
"không đo được ⇒ THẤT BẠI". **Import và dùng lại**, tuyệt đối không gõ lại.
Nếu thấy mình đang viết lại vòng lặp đối chiếu số dòng ⇒ đã đi sai hướng.

Khác biệt duy nhất của task này: bản dump đến từ **file trên host do
`backup_db.sh` tạo ra**, thay vì file trong container.

### Ràng buộc an toàn — DB thật đang chạy
- **CẤM** mọi thao tác ghi/xoá lên database `trading`.
- Phục hồi vào scratch DB riêng, tên **`trading_roundtrip_test`** (tên KHÁC
  đợt 13 để hai phép kiểm không giẫm chân nhau nếu chạy song song).
- Được `DROP DATABASE trading_roundtrip_test` khi dọn — **chỉ đúng tên đó**,
  và phải có chốt chặn tên như `verify_backup_restore.py:236` đã làm
  (`if SCRATCH_DB and SCRATCH_DB == "..."` trước khi phát lệnh DROP).
- Không đụng volume `pgdata`.

### Các bước → kiểm chứng bằng
1. Chạy **chính `scripts/backup_db.sh`** (qua Git Bash), xuất ra thư mục tạm
   → kiểm chứng: file `.sql.gz` tồn tại trên host, in kích thước.
   **Đối chiếu với 55,5 MB của đợt 13** — lệch nhiều là dấu hiệu ống hỏng.
2. Kiểm tính toàn vẹn của file **trước khi** restore: `gzip -t` (kiểm CRC).
   → kiểm chứng: `gzip -t` thoát 0. **Đây là phép bắt hỏng-do-ống rẻ nhất**;
   nếu nó trượt thì dừng, đã có câu trả lời.
3. Đưa file từ host vào container rồi restore vào `trading_roundtrip_test`
   → kiểm chứng: ghi lại **toàn bộ** cảnh báo psql, không nuốt.
4. Đối chiếu số dòng + hypertable/chunk hai bên, **dùng lại** hàm của đợt 13
   → kiểm chứng: bảng đối chiếu; "không đo được" phải là THẤT BẠI.
5. Dọn: DROP scratch DB, xoá file tạm → kiểm chứng: `trading` còn nguyên
   (đếm lại `bars`), scratch DB biến mất.

### Nếu file hỏng
**Dừng, báo cáo, KHÔNG tự sửa `backup_db.sh`.** Lúc đó phải chọn giữa
`pg_dump -Fc` ghi thẳng ra volume, hay dump trong container rồi `docker cp` —
đó là quyết định kiến trúc, không phải sửa lặt vặt.

---

## 2. Task 2 — Nguyên nhân mất bar 5m ngày 06/07 và 07/07/2026

### Vì sao và tại sao BÂY GIỜ

Đợt 12 tìm ra hai ngày mất thật trong kỳ backfill toàn rổ:
- **06/07/2026**: 0 bar 5m toàn thị trường (trong khi `bars_daily` có 914 mã)
- **07/07/2026**: chỉ 349 bar, hầu hết mã chỉ còn đúng 1 bar khớp đóng cửa

Đợt 12 kết luận "cơ chế KHÔNG xác định được khi chỉ đọc — cần đối chiếu log
backfill hoặc fetch thử". Hôm nay tôi kiểm hai đường đó:

- **Đường log: ĐÃ CHẾT.** `logs/backfill.log` chỉ còn từ 01/09/2026 (xoay log
  theo kích thước đã cuốn mất tháng 7). Không còn bằng chứng.
- **Đường fetch thử: CÒN KỊP, NHƯNG CÓ HẠN.** 07/07 cách hôm nay ~62 ngày,
  vẫn nằm trong trần ~150 ngày của SSI (đợt 11). **Cửa sổ này đóng dần mỗi
  ngày** — qua khoảng đầu tháng 12 thì không còn hỏi được nữa.

Giá trị thật của task này **không phải** để cứu 2 ngày (đợt 12 đã tính:
ảnh hưởng ~2%, không lật kết luận nào). Giá trị là biết **cơ chế đó có thể
tái diễn không**. Nếu backfill từng nuốt trọn một phiên mà không ai biết, nó
sẽ làm lại — và lần sau có thể rơi vào lúc quan trọng hơn.

### Câu hỏi phải trả lời
**Dữ liệu 5m ngày 06/07 và 07/07 có tồn tại ở SSI không?**
- **Có** ⇒ backfill của ta đã hỏng/bỏ sót ⇒ là **bug, có thể tái diễn** ⇒ cần
  brief riêng để truy và vá.
- **Không** ⇒ thiếu tại nguồn, giống hệt hai phiên `2026-08-07` và
  `2026-08-28` mà SSI vốn không có (đã ghi nhận trước đây) ⇒ **không phải lỗi
  của ta**, đóng hồ sơ.

### File được sửa/tạo
- **TẠO MỚI:** `scripts/probe_ssi_5m_0607.py`
- **KHÔNG SỬA:** `trading/collector/**`, `scripts/backfill_universe.py`,
  `scripts/probe_bars_5m_completeness.py` (đợt 12, đã audit — **file này từng
  bị viết đè trái phép ở đợt 13, đừng lặp lại**), `config/config.yaml`.

### Ràng buộc riêng — đọc kỹ
- **CHỈ ĐỌC. TUYỆT ĐỐI KHÔNG nạp gì vào `bars`.** Fetch về, đếm, in ra, rồi
  thôi. Việc có backfill bù hay không là quyết định riêng, sau khi có câu trả
  lời.
- API dữ liệu SSI **chỉ đọc**; không đụng endpoint đặt/huỷ lệnh.
- Dùng lại `SSIRestClient` trong `trading/collector/backfill.py`, **không tự
  viết HTTP call mới** (khuôn giống `scripts/spike_ssi_history_depth.py`).
- Task này **được phép** dùng `trading.config.load_config` + `ensure_authenticated`
  — **ngoại lệ có chủ ý** của lệnh cấm `load_config` ở các brief đo lường, vì
  ở đây bắt buộc phải xác thực SSI thật. Nhớ nạp `.env` trước (`set -a && . ./.env`),
  nếu không `load_config` sẽ `KeyError`.
- Fetch **3 mã** (đề xuất: VCB, IJC, và một mã UPCOM như MSR) × **3 ngày**
  (06/07, 07/07, và ngày đối chứng dương ở mục kiểm chứng) = **9 lượt gọi**.
  Đủ kết luận, không cần hơn. **Không quét cả rổ.**
- Nếu token hết hạn / cần OTP: **dừng, báo cáo**, không tự xoay xở. Việc OTP
  là của chủ dự án (`DEPLOYMENT.md` §8.5).
- Chạy **một lần**. SSI đã từng trả 429.

### Kiểm chứng
1. Dán output thô: mỗi mã × mỗi ngày trả về **bao nhiêu bar**.
2. **Đối chứng dương bắt buộc:** fetch thêm **một ngày kế cận chắc chắn có dữ
   liệu** (ví dụ 08/07 hoặc 03/07) cho cùng các mã đó. Nếu ngày đối chứng cũng
   trả 0 bar thì phép thử **vô nghĩa** — nghĩa là đang hỏi sai cách chứ không
   phải SSI thiếu dữ liệu. Không có bước này thì kết luận "SSI không có" không
   đứng vững.
3. Kết luận một câu theo đúng hai nhánh ở trên. **Nếu kết quả mập mờ thì nói
   là mập mờ** — không bẻ cong cho khớp giả thuyết nào.
4. `uv run ruff check scripts` sạch.

---

## 3. Ràng buộc đứng (cả hai task)

- `real_trading_enabled` giữ `false`. Không bật, kể cả tạm.
- Không gọi API đặt/huỷ lệnh SSI. Không in giá trị secret. Không sửa `.env`.
- **Agent KHÔNG commit, KHÔNG push.** Claude audit rồi mới commit.
- Không `TRUNCATE`/`DROP`/xoá dòng trên `trading` (ngoại lệ duy nhất: scratch
  DB do chính Task 1 tạo). Không nạp gì vào `bars`/`bars_daily`.
- `config/config.yaml` không được sửa.
- **Chỉ sửa file mà task được giao nêu tên.** Đợt 13 đã viết đè
  `probe_bars_5m_completeness.py` (481 → 184 dòng) ngoài phạm vi và không báo
  cáo; tôi đã phải khôi phục. Đừng lặp lại.
- Phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.
- Trước khi sửa symbol: `gitnexus_impact`; sau khi sửa: `gitnexus_detect_changes`.

---

## 4. Báo cáo nộp lại phải có

| Mục | Bằng chứng bắt buộc |
|---|---|
| Task 1 | Kích thước file host + kết quả `gzip -t` + bảng đối chiếu số dòng/chunk + xác nhận `trading` nguyên vẹn và scratch DB đã xoá |
| Task 1 — dùng lại | `git diff` cho thấy **import** hàm của `verify_backup_restore.py`, không chép lại |
| Task 2 | Output thô từng mã × từng ngày, **kèm ngày đối chứng dương**, và kết luận theo đúng hai nhánh |
| Chung | `ruff` sạch; `git status` chỉ có file trong phạm vi được giao |

**Về bằng chứng "đỏ":** tôi sẽ tự phá hoại lại trên đúng code được giao và tự
đối chiếu tên test bằng `grep -n "^def test_"`. Chép tên từ file thật.

---

## 5. Cố ý KHÔNG giao

- **Backfill bù 06-07/07** — chờ Task 2 trả lời trước. Nạp dữ liệu khi chưa
  biết nguyên nhân là cách tốt để giấu bug.
- **Truy và vá bug backfill** — chỉ mở nếu Task 2 kết luận "SSI có dữ liệu".
- **Sửa `backup_db.sh`** — chỉ mở nếu Task 1 kết luận file hỏng.
- **Nhóm mã mỏng của đợt 12** (AFX, APH, BCE... 87 ngày mà 0 ngày đủ bar) —
  giá trị thấp, và đợt 12 đã nêu là cần nguồn cú khớp mới phân biệt được.
- **Tier 1, nhánh BÁN (J), đa tài khoản, `real_order_account`, chuyển VPS** —
  đang chờ quyết định của chủ dự án.
