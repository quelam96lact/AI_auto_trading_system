# Brief đợt 47 — Gắn chuông luồng vào lịch, và triển khai `grace = 20`

Ngày giao: 18/09/2026, 10:30.
Base: `a98646f` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Brief này chạy trong ngày hôm nay, theo giờ.** Đọc §1 trước — có ba mốc thời gian cố định.

---

## 0. Vì sao gấp

Năm phiên gần nhất, **hai phiên luồng chết hoàn toàn và một phiên mất 40%**, không lần nào có
cảnh báo:

| Ngày | Nến trong `bars` | Chốt từ **luồng** | Từ backfill |
|---|---|---|---|
| 14/09 (sáng) | 27/mã | **0** | toàn bộ |
| 15/09 | 136 | 129 | 7 |
| **16/09** | **156** | **0** | **toàn bộ phiên** |
| 17/09 | 138 | 82 | **56 (40%)** |

Mọi phép kiểm hiện có đều xanh trong lúc đó, vì backfill lấp đầy `bars` và `heartbeat` thấy
nến mới đúng giờ. Hệ thống **mù đúng chỗ quan trọng nhất**.

`scripts/stream_health_check.py` được dựng ở đợt 43 **đúng để bắt tình huống này**. Nó nằm
trong repo từ 14/09 và **chưa chạy lần nào**, vì chưa ai gắn nó vào lịch.

Trong các brief trước tôi luôn ghi *"đăng ký lịch là việc của chủ dự án"*. Điều đó đúng với
bước cuối (đăng ký Scheduled Task trên máy), nhưng **sai ở bước trước đó**: `scripts/sched.sh`
đã là nơi tập trung mọi job định kỳ, và thêm một job vào đó là việc trong repo, agent làm được.
Đợt 29 đã thêm `engine-consumer` đúng theo cách này. Tôi đã bỏ sót, và cái giá là hai phiên
mất luồng không ai biết.

---

## 1. Ba mốc thời gian hôm nay

| Mốc | Việc | Ghi chú |
|---|---|---|
| **Ngay bây giờ** | Task 1 — thêm job `stream-health` vào `sched.sh` | Chỉ sửa file trong repo, **không** đụng container |
| **Sau 15:05** | Task 2 — đo phiên 18/09 | Đây là **phiên nền cuối cùng** với `grace = 60` |
| **Sau khi Task 2 xong** | Task 3 — triển khai `grace = 20` | Ngoài phiên, có rollback |

**Thứ tự này bắt buộc.** Đo trước, đổi sau — nếu triển khai trước khi đo thì mất luôn phiên nền
cuối cùng, và tiêu chí nghiệm thu thứ Hai không còn gì để so.

---

## Task 1 — Thêm job `stream-health` vào `scripts/sched.sh`

### 1.1. Việc

`sched.sh` hiện có sáu job: `heartbeat`, `daily-check`, `backfill`, `deploy-drift`,
`engine-cam`, `engine-consumer`. Thêm job thứ bảy:

```
stream-health)   -> chạy scripts/stream_health_check.py
```

Theo **đúng khuôn của `engine-consumer)`** — đọc nhánh đó trước và giữ nguyên style: cách
truyền tham số, cách bắt mã thoát, cách in thông điệp. Cập nhật cả dòng `usage` và phần chú
thích đầu file, đúng như đợt 29 đã làm.

**Không sửa sáu job có sẵn.** Không đổi `usage` của chúng, không đổi thứ tự.

### 1.2. Kiểm chứng bằng dữ liệu THẬT — phần quan trọng nhất

Công cụ này chưa từng chạy. Trước khi gắn nó vào lịch, phải chứng minh nó **phân biệt được**
phiên tốt với phiên hỏng, và ta đang có sẵn cả hai trong log:

1. **Đối chứng dương (phiên hỏng):** chạy cho **16/09** → phải in `dung: ...` và **`exit 2`**.
   Đây là phiên luồng chết hoàn toàn. Nếu nó trả `exit 0` thì công cụ vô dụng và mọi việc gắn
   lịch là vô nghĩa — **dừng, báo cáo**.
2. **Đối chứng âm (phiên tốt):** chạy cho **15/09** → phải `exit 0` và in số nến hợp lý
   (129 nến chốt từ luồng).
3. Chạy cho **17/09** — phiên mất 40%. Nêu nó trả gì. Tôi **không** đặt kỳ vọng trước ở đây:
   ngưỡng hiện tại là "0 nến từ luồng = CRITICAL", nên 82 nến sẽ qua. Báo cáo con số và nói rõ
   công cụ **không** bắt được suy giảm một phần. Đó là giới hạn đã biết, ghi lại, **đừng tự
   thêm ngưỡng mềm** — ta chưa biết mức bình thường.
4. Chạy qua `sched.sh stream-health` (không gọi thẳng script) → cùng kết quả.
5. Năm test hiện có của `tests/test_stream_health_check.py` pass nguyên vẹn, **không sửa một
   `assert` nào**.

### 1.3. Lệnh đăng ký lịch — soạn sẵn, KHÔNG tự chạy

In ra **lệnh đăng ký Scheduled Task hoàn chỉnh** để chủ dự án chỉ việc dán, theo đúng khuôn
lệnh đã soạn cho chuông 2C ở báo cáo đợt 29. Đề xuất chạy **15:10 mỗi ngày làm việc** — sau
khi phiên đóng và sau khi backfill cuối phiên đã xong.

**Agent không tự đăng ký Scheduled Task.** Đó vẫn là việc của chủ dự án.

---

## Task 2 — Đo phiên 18/09 (sau 15:05)

**Phiên nền cuối cùng với `grace = 60`.** Sau hôm nay không còn cơ hội đo lại.

Dùng `scripts/measure_session_stream_metrics.py` (đã bổ sung cột ở đợt 46), lấy đúng bộ chỉ số
của brief 46 §1.1 cho **cả ngày 18/09**:

- `lag_ms`: min, p25, trung vị, p75, p90, p95, max, **và số lần vượt 60s**
- `late_ms`: n, trung vị, p90, max
- `snapshots` mỗi nến: min, trung vị, max, và **tỷ lệ nến chỉ có 1 snapshot**
- **Số nến chốt từ luồng so với số dòng trong `bars`** — nêu cả hai, đây là chỗ ngày 16/09 lộ ra
- Khung nến thiếu, nếu có
- Chuông im lặng: số lần, giờ Việt Nam

Truy vấn DB mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`. Mọi mốc in ra kèm giờ Việt Nam.

**Chuông im lặng hôm nay phải khác hôm qua:** bản mới chỉ kêu trong giờ khớp lệnh liên tục.
Nếu vẫn thấy dòng lúc `09:02` hoặc `14:32` thì bản vá đợt 46 **chưa** vào container — nói rõ.
*(Lưu ý: bản vá đó cũng chưa triển khai tính tới lúc tôi giao brief này, nên rất có thể vẫn
còn. Ghi nhận trung thực, đừng ngạc nhiên.)*

---

## Task 3 — Triển khai `grace = 20` (sau khi Task 2 xong)

`grace_seconds=20` đã nằm trong mã nguồn từ đợt 46 nhưng **chưa triển khai**. Container đang
chạy vẫn là bản `grace=60`.

### 3.1. Việc

1. Lưu ảnh rollback: `docker tag <image collector hiện tại> dot47-rollback-collector:pre`
2. `docker compose build collector` rồi `docker compose up -d collector`
3. Dán ID ảnh vừa build và ID ảnh container đang chạy — **phải khớp**
4. `docker exec <container> grep -n "grace_seconds" /app/trading/collector/main.py` — phải thấy `20`
5. `docker exec <container> grep -c "is_continuous_matching" /app/trading/collector/main.py` —
   chứng minh bản vá chuông của đợt 46 cũng đã vào

### 3.2. Ràng buộc

- **Chỉ làm sau 15:00**, và chỉ sau khi Task 2 đã lấy xong số liệu.
- Sau khi `up -d`, chờ và xác nhận container `running`, không `restarting`.
- Nếu build hỏng hoặc container không lên: `docker tag dot47-rollback-collector:pre` ngược lại,
  khởi động lại bản cũ, **báo cáo ngay**, không tự sửa.

---

## 2. Ràng buộc chung

- `real_trading_enabled` giữ `false`. Không gọi SSI/BingX/Binance.
- **Không đụng container trước 15:00.** Task 1 chỉ sửa file trong repo.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Không đụng NATS.
- Không sửa `trading/collector/latch.py`, `trading/calendar_vn.py`,
  `scripts/stream_health_check.py`, `config/config.yaml`, `.env`, và toàn bộ đường crypto.
- Không xoá file. **Không commit, không push.**
- Output copy từ terminal. Thiếu thì ghi **"CHƯA LÀM"** kèm lý do, **không bịa**.
- **Không xoá dòng `TEST` trong bảng `orders`** — vẫn chờ chủ dự án đồng ý riêng.

---

## 3. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`, và **`git diff scripts/sched.sh`**.
2. Task 1: năm tiêu chí §1.2, **nói rõ đối chứng dương (16/09 → exit 2) đã xanh**, kèm lệnh
   đăng ký lịch soạn sẵn.
3. Task 2: bảng đầy đủ phiên 18/09, **kèm số nến chốt từ luồng so với `bars`**.
4. Task 3: ID ảnh, output hai lệnh `grep`, trạng thái container.
5. Ba dòng: số test pass (mốc **755**), ruff, cổng cứng VN đủ bốn con số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

**Không commit, không push.**

---

## 4. Điều KHÔNG thuộc phạm vi

- **Không tự đăng ký Scheduled Task.** Soạn lệnh, dừng.
- **Không thêm ngưỡng mềm** cho `stream_health_check`. Xem §1.2 mục 3.
- **Không đổi `grace` sang số khác 20.**
- **Không nghiệm thu `grace = 20`** — việc đó là phiên thứ Hai 21/09 sau 15:05, và khi so nền
  **phải dùng phiên có luồng thật (15, 17, 18/09), không dùng 16/09**: một phiên toàn backfill
  luôn "không thiếu khung" vì backfill lấp đầy mọi thứ.
- **Không quyết định A/B/C** của đợt 45.

---

## 5. Việc của chủ dự án

1. **Đăng ký Scheduled Task cho `stream-health`** ngay khi agent đưa lệnh — đây là việc gấp
   nhất hiện nay. Hai phiên mất luồng không ai biết.
2. **Đăng ký Scheduled Task cho chuông 2C** (`engine-consumer`) — lệnh đã soạn từ đợt 29.
3. **`powercfg /change standby-timeout-dc 0`**.
4. **Quyết định A / B / C** của đợt 45 — nhắc lại: lựa chọn A với rổ ba mã hiện tại nghĩa là
   **không giao dịch gì cả**.
5. **Q-2** và **câu hỏi 9/9 lệnh hết hạn** (cảnh báo là `WARN`, có đi Telegram, kèm lệnh xác
   nhận sẵn — ông có nhận được không, và 15 phút có đủ không?).
