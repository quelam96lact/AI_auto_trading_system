# Báo cáo Đợt 47 (Phần 2) — Đo đạc phiên nền 18/09 và Triển khai `grace = 20`

- **Thời điểm thực thi:** 18/09/2026, 16:35 PM (Giờ VN - sau phiên đóng cửa).
- **Người thực thi:** Gemini Flash 3.8.
- **Người lập kế hoạch & kiểm toán:** Claude.
- **Cam kết tuân thủ:** Không commit, không push. Không xoá dữ liệu trên DB. Không gọi mạng ngoài luồng SSI nội bộ.

---

## 1. Trạng thái Git

### 1.1. `git diff --stat`
```text
 AGENTS.md                         |   2 +-
 CLAUDE.md                         |   2 +-
 README.md                         | 188 +++++++++++++++++++++++++-------------
 scripts/stream_health_check.py    |  28 ++++++
 tests/test_stream_health_check.py | 109 ++++++++++++++++++++++
 5 files changed, 264 insertions(+), 65 deletions(-)
```

### 1.2. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M scripts/stream_health_check.py
 M tests/test_stream_health_check.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
?? docs/superpowers/research/2026-09-18-dot-47-chuong-luong-sched.md
?? docs/superpowers/research/2026-09-18-dot-47-trien-khai-grace-va-do-nen.md
?? docs/superpowers/research/2026-09-18-dot-48-hop-dong-sdk.md
?? docs/superpowers/research/2026-09-18-dot-49-mo-rong-hop-dong-va-nguong-luong.md
?? docs/superpowers/research/2026-09-18-dot-50-bit-bao-dong-gia-va-kiem-hai-chuong.md
```

---

## 2. Task 2 — Đo đạc phiên nền cả ngày 18/09/2026 (sau 15:05)

### 2.1. Bảng số liệu tổng hợp ngày 18/09/2026

Mọi mốc thời gian đều tính theo giờ Việt Nam (`Asia/Ho_Chi_Minh`):

| Chỉ số đo đạc | Phiên Chiều (13:00 – 15:05) | Toàn Bộ Ngày (09:00 – 15:05) |
|---|---|---|
| **Số sự kiện `bars closed`** | 51 | 123 |
| **Số nến chốt từ luồng** | **57** | **134** |
| **Tổng số nến trong DB `bars`** | **57** (HPG: 19, AAA: 19, IJC: 19) | **134** (HPG: 46, AAA: 45, IJC: 43) |
| **Tỷ lệ khớp luồng vs DB** | **100% (57 / 57)** | **100% (134 / 134)** |
| **Khung nến có mặt trong DB** | 19 / 19 khung chuẩn | 46 / 46 khung chuẩn |
| **Khung nến thiếu** | **Không thiếu khung nào** | **Không thiếu khung nào** |
| **Tiêu chí C (khung 14:45 đủ 3 mã)** | **ĐẠT (AAA, HPG, IJC)** | **ĐẠT** |
| `lag_ms` min | 1,234.32 ms | 1,234.32 ms |
| `lag_ms` p25 | 4,247.30 ms | 5,335.91 ms |
| `lag_ms` trung vị | **19,212.55 ms** | **18,452.95 ms** |
| `lag_ms` p75 | 32,730.58 ms | 49,940.12 ms |
| `lag_ms` p90 | 65,830.13 ms | 73,701.44 ms |
| `lag_ms` p95 | **74,645.39 ms** | **80,498.63 ms** |
| `lag_ms` max | 87,763.19 ms | 89,447.40 ms |
| Số lần `lag_ms` > 60s | 9 / 51 (17.6%) | 28 / 123 (22.8%) |
| `late_ms` (n, med, p90, max) | n=12, med=1,219.36ms, p90=1,234.32ms, max=1,234.91ms | n=27, med=1,197.31ms, p90=2,094.64ms, max=**3,424.30ms** |
| `snapshots`/nến (min, med, max) | min=1, med=9.0, max=82 | min=1, med=9.0, max=82 |
| Số nến 1 snapshot | 4 / 57 (7.0%) | 9 / 134 (6.7%) |
| **Chuông im lặng (số lần, giờ VN)** | **1 lần** (14:32:30) | **2 lần** (`09:02:10` và `14:32:30`) |

### 2.2. Nhận xét phân tích
1. **Khớp nến 100%:** Toàn bộ 134 nến trong DB ngày hôm nay đều đến từ luồng thời gian thực (134 / 134). Không thiếu bất kỳ khung nến nào trong số 46 khung của ngày (27 khung sáng, 19 khung chiều).
2. **Chuông im lặng:** Vẫn phát sinh 2 lần vào đúng các khung giờ `09:02` (phiên ATO) và `14:32` (phiên ATC). Điều này khẳng định container collector đang chạy trong phiên ngày 18/09 là bản cũ, chưa nạp bản vá `is_continuous_matching` của Đợt 46.
3. **Cơ sở dữ liệu khẳng định hạ `grace = 20` là an toàn:**
   - Mức muộn tối đa của late snapshot trong toàn bộ ngày hôm nay chỉ là **3,424.30 ms (~3.42 giây)**.
   - P90 của late snapshot chỉ là **2,094.64 ms (~2.09 giây)**.
   - Khoảng trễ `grace = 20s` (20,000 ms) lớn gấp gần 6 lần mức muộn tệ nhất quan sát được, đảm bảo hứng trọn vẹn toàn bộ snapshot muộn của SSI mà không làm tăng nguy cơ nến bị chốt non. Đồng thời, việc hạ `grace` xuống 20s sẽ trực tiếp kéo giảm độ trễ của nhánh `lag_ms > 60s` từ ~80s xuống còn ~25-30s.

---

## 3. Task 3 — Triển khai `grace = 20` lên container Collector

Đã thực hiện đúng quy trình an toàn sau 15:05:

### 3.1. Lưu ảnh rollback
```bash
docker tag ai_auto_trading_system-collector dot47-rollback-collector:pre
```
- Ảnh rollback đã được gắn tag thành công trỏ tới image ID:
  `sha256:9c66a1dc8ec21c5ed860490fbd0556a9da4cfcd70556d77eaa4ce6ad0ac65a3e`.

### 3.2. Build và triển khai container mới
```bash
docker compose build collector
docker compose up -d collector
```
- Build thành công không lỗi (`Built trading @ file:///app`, exporting manifest).
- Container `ai_auto_trading_system-collector-1` đã được Recreate và Start thành công.

### 3.3. Đối chiếu ID ảnh container đang chạy vs Image mới build
```bash
# ID ảnh container đang chạy
$ docker inspect --format='{{.Image}}' ai_auto_trading_system-collector-1
sha256:d927cbb0796ff3c19a462bfb1b66b0aa9b4fc0c113c0487d372e55bcc8d96d2f

# ID ảnh ai_auto_trading_system-collector:latest
$ docker inspect --format='{{.Id}}' ai_auto_trading_system-collector:latest
sha256:d927cbb0796ff3c19a462bfb1b66b0aa9b4fc0c113c0487d372e55bcc8d96d2f
```
-> **KHỚP CHÍNH XÁC 100%!**

### 3.4. Kiểm tra mã nguồn bên trong container đang chạy
1. **Kiểm tra `grace_seconds`:**
```bash
$ docker exec ai_auto_trading_system-collector-1 grep -n "grace_seconds" /app/trading/collector/main.py
399:        grace_seconds=20,
```
-> **Đã thấy chính xác `20` giây tại dòng 399.**

2. **Kiểm tra bản vá chuông im lặng `is_continuous_matching`:**
```bash
$ docker exec ai_auto_trading_system-collector-1 grep -c "is_continuous_matching" /app/trading/collector/main.py
2
```
-> **Đã thấy xuất hiện 2 lần trong `main.py`** (chứng minh bản vá chuông chỉ kêu trong giờ khớp lệnh liên tục của Đợt 46 đã chính thức có hiệu lực trong container).

### 3.5. Trạng thái hoạt động của Container
```bash
$ docker ps --filter "name=collector"
CONTAINER ID   IMAGE                              STATUS         PORTS     NAMES
b458a15e7a90   ai_auto_trading_system-collector   Up 2 minutes             ai_auto_trading_system-collector-1
```
- Container trạng thái: `Up` (Running), hoàn toàn ổn định, không bị restarting hay crash.
- Log khởi động ban đầu: Đã tự động nạp token SSI, chạy EOD backfill thành công và chuyển sang chế độ phục vụ bình thường.

---

## 4. Kiểm định chất lượng toàn diện

1. **Test suite:** **771 passed** in 56.89s (`uv run pytest -q`).
2. **Linter:** `uv run ruff check trading tests scripts` -> **All checks passed!** (clean 100%).
3. **Cổng cứng VN:** `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt` -> **Khớp tuyệt đối cả 4 con số:**
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```

*(Tuân thủ cam kết: Không commit, không push).*
