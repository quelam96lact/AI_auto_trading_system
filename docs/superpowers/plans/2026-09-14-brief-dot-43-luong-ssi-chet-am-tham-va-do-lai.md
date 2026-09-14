# Brief đợt 43 — Luồng SSI chết âm thầm, backfill che mất, và phép đo bị lỡ hai phiên

Ngày giao: 14/09/2026, 12:15.
Base: `2de5a0a` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Brief này có phần chạy theo giờ. Đọc §1 trước, nó bắt đầu lúc 13:00 hôm nay.**

---

## 0. Điều tôi phát hiện lúc 12:04 hôm nay

Tôi định nghiệm thu brief 36 Task 3 chiều nay. Khi kiểm tình hình phiên sáng thì thấy chuyện khác.

### 0.1. Phiên sáng nay không có một nến nào từ luồng thời gian thực

Bảng `bars` có đủ 27 nến mỗi mã, 09:15 → 11:25, không thủng. Nhìn DB thì **mọi thứ hoàn hảo**.

Nhưng log collector, dòng cuối cùng của phiên sáng:

```json
{"level": "INFO", "msg": "backfill start"}
{"level": "INFO", "msg": "backfill done", "counts": {"HPG": 27, "IJC": 27, "AAA": 27}}
```

**27 nến mỗi mã — đúng bằng số nến trong DB — đến từ backfill.** Luồng thời gian thực đóng góp
**không**.

Bằng chứng phụ: trong **6.810 dòng log** trải từ `11/09 12:44` tới `14/09 12:04` — phủ cả chiều
thứ Sáu lẫn sáng nay — **không có một dòng `bars closed` nào**. `persist_bars` chỉ được gọi từ
`on_stream_message` và `housekeeping_tick`; nó chưa từng chạy. Kéo theo **không có `lag_ms`,
không có `late snapshot`**.

Và đo đạc **không hề thiếu**. Tôi kiểm code bên trong container đang chạy:

```
docker inspect → image sha256:b9d6f245a201…   (đúng bản đợt 36)
docker exec … grep -c "late snapshot" /app/trading/collector/main.py → 1
docker exec … grep -c "bars closed"   /app/trading/collector/main.py → 1
```

Code có đủ. Nó chỉ chưa bao giờ được gọi tới.

### 0.2. Chuỗi nguyên nhân

```
Máy ngủ nhiều lần cuối tuần  →  DNS trong Docker chết khi tỉnh
                             →  SSIFeed không nối được
                             →  làm mới token thất bại vì DNS chết
                             →  refresh_token hết hạn
                             →  luồng thời gian thực CHẾT
                             →  backfill vẫn chạy, DB vẫn đầy, không ai biết
```

Chuông phát hiện máy ngủ của đợt 35 **đã làm đúng việc** và bắt được sáu lần:

```
11/09 20:04→22:42   9.421s
12/09 15:00→15:15     854s
12/09 20:46→21:47   3.629s
13/09 07:53→08:01     436s
13/09 08:13→08:22     534s
13/09 08:26→15:31  25.442s   (hơn 7 tiếng)
```

Tất cả đều `"in_trading_hours": false` — đúng, vì là cuối tuần. Chuông không sai. Nhưng **không
ai nối được từ "máy đã ngủ" sang "luồng SSI đã chết"**, và đó chính là lỗ hổng.

Lỗi SSIFeed trong log, theo đúng thứ tự:

```
SSIFeed connection error: [Errno -5] No address associated with hostname
SSIFeed connection error: [Errno -2] Name or service not known
SSIFeed connection error: SSI refresh_token missing/expired và tự authenticate() thất bại …
```

### 0.3. Tin tốt: token đã tự lành lúc 12:06 hôm nay

```
ssi_auth_state.updated_at = 2026-09-14 12:06:20+07   access ✓   refresh ✓ (424 ký tự)
```

Container khởi động lại lúc `11:55` và làm mới token thành công lúc `12:06`, sau khi mạng trở
lại. **Hiện tại token hợp lệ.** Nghĩa là phiên chiều 13:00 **có thể** chạy được — nhưng chưa ai
chứng minh điều đó, và đó là việc đầu tiên của brief này.

### 0.4. Vì sao đây là lỗ hổng giám sát nghiêm trọng nhất từ trước tới nay

Mọi phép kiểm hiện có đều **xanh** trong khi luồng đã chết hai phiên:

| Phép kiểm | Trạng thái | Vì sao mù |
|---|---|---|
| Số nến trong `bars` | ✅ đủ 27/mã | backfill lấp đầy |
| `heartbeat_check` | ✅ | có nến mới, đúng giờ |
| Chuông 2C (consumer JetStream) | — chưa đăng ký lịch | và nó đo consumer, không đo nguồn |
| Chuông máy ngủ (đợt 35) | ✅ kêu đúng | nhưng báo "ngoài giờ", không ai nối sang luồng |

Hệ thống **không có cách nào biết** "nến này đến từ luồng hay từ backfill". Đó là Task 3, và nó
là thứ đáng giá nhất của đợt này bất kể chiều nay ra sao.

---

## 1. Task 1 — Xác minh luồng lúc 13:00 (LÀM TRƯỚC, THEO GIỜ)

Phiên chiều: **13:00 → 14:45**. Nến 5 phút đầu tiên đóng lúc **13:05**.

### 1.1. Việc

Từ **13:06**, theo dõi log collector, tìm dòng `"bars closed"`:

```
docker compose logs collector --since 10m | Select-String -SimpleMatch "bars closed"
```

- **Có dòng đó trước 13:15** → luồng sống. Ghi lại `lag_ms` của nó. Sang Task 2.
- **Không có tới 13:15** → luồng vẫn chết. **DỪNG NGAY, báo cáo cho Claude**, kèm 20 dòng log
  gần nhất có chữ `SSIFeed`. **Không tự sửa, không restart, không chạy script xác thực nào.**

### 1.2. Ba điều cấm tuyệt đối ở Task 1

1. **Không `docker compose restart` hay `up --build` trong phiên.** Ràng buộc có từ lâu, và
   hôm nay càng đúng: restart giữa phiên sẽ mất chính dữ liệu ta đang cần đo.
2. **Không chạy `scripts/spike_ssi_sdk_auth.py`.** Nó cần người gõ OTP. Đó là việc của chủ dự
   án, không phải của agent.
3. **Không sửa `.env`, không in token, không in bất kỳ chuỗi bí mật nào.** Khi dán log, che
   mọi chuỗi dài trông như token.

### 1.3. Kiểm chứng Task 1

Dán nguyên văn:
- Dòng `bars closed` đầu tiên của phiên chiều (hoặc ghi rõ **"KHÔNG CÓ"**).
- Số dòng `bars closed` và số dòng `late snapshot` tính tới 13:15.

---

## 2. Task 2 — Phép đo của brief 36 Task 3 (sau 15:05)

**Chỉ làm nếu Task 1 xác nhận luồng sống.** Nếu luồng chết, ghi **"CHƯA LÀM — luồng không
delivery"** và bỏ qua toàn bộ Task 2.

### 2.1. Điều kiện tiên quyết — kiểm trước, đừng kết luận vội

Xác nhận phiên chiều **không có khoảng chết**: không có dòng CRITICAL máy ngủ nào với
`"in_trading_hours": true`, và log có hoạt động liên tục từ 13:00 tới 14:45.

**Nếu có khoảng chết → dừng, báo cáo, ĐỪNG kết luận tiêu chí B/C trượt.** Một phiên bị ngắt thì
số liệu không nói lên điều gì về chốt nến.

### 2.2. Bốn số phải đo

1. **Tiêu chí B** — số nến duy nhất trong phiên chiều, phải **khớp số dòng trong `bars`** cho
   cùng khoảng. Nêu cả hai con số.
2. **Tiêu chí C** — khung `14:45` có mặt đủ **cả ba mã** `HPG`, `IJC`, `AAA`.
3. **Phân bố `lag_ms`** của phiên chiều: min, p25, trung vị, p75, p90, p95, max.
   Mốc so sánh ngày 11/09: trung vị `14.318`, p95 `68.822`.
4. **Phân bố `late_ms`** từ các dòng `late snapshot`: trung vị, p95, max, **và tỷ lệ phần trăm
   snapshot đến muộn** trên tổng số snapshot nhận được.

Mọi mốc thời gian in ra **kèm hậu tố giờ Việt Nam**. Đợt 28/29 đã một lần in giờ UTC mà không
nói, làm tôi đọc nhầm 06:30 thành 13:30.

### 2.3. Về `grace` — đo, đừng chỉnh

`grace` hiện là **60 giây**. Brief 36 để ngỏ việc chỉnh nó **sau khi có số**.

**Đợt này vẫn không chỉnh.** Báo cáo phân bố `late_ms` và **đề xuất** một giá trị kèm lý do.
Tôi quyết định, vì đây là tham số ảnh hưởng trực tiếp tới việc nến có bị chốt thiếu dữ liệu hay
không, và một phiên dữ liệu là quá ít để đổi nó.

---

## 3. Task 3 — Bịt lỗ hổng: cảnh báo khi phiên không có nến từ luồng

**Đây là phần đáng giá nhất của đợt, và nó không phụ thuộc chiều nay ra sao. Làm cả khi Task 2
bị bỏ.**

### 3.1. Vấn đề, nói gọn

Hệ thống không phân biệt được nến đến từ **luồng thời gian thực** hay từ **backfill**. Nên
"luồng chết nhưng DB đầy" là trạng thái **hoàn toàn im lặng**. Nó đã kéo dài hai phiên.

### 3.2. Việc

Thêm một script kiểm tra độc lập: `scripts/stream_health_check.py`.

Nó **đọc log của container collector** (không đọc DB — DB chính là thứ đang nói dối) và trả lời
đúng một câu: *trong phiên giao dịch vừa rồi, có bao nhiêu nến được chốt từ luồng?*

```
uv run python scripts/stream_health_check.py [--session sang|chieu] [--date YYYY-MM-DD]
```

- Đếm số dòng `"bars closed"` trong khoảng phiên.
- **0 dòng → in `dung: ...` và `exit 2`**, đúng khuôn `scripts/engine_consumer_check.py` và
  `scripts/sched.sh` đã dùng (đọc hai file đó trước để giữ nguyên style — **không sửa chúng**).
- Có dòng → in số nến và `exit 0`.

Ngưỡng cảnh báo: **0 nến từ luồng trong một phiên là CRITICAL**. Không đặt ngưỡng mềm nào khác
— ta chưa biết mức bình thường, và một ngưỡng đoán bừa sẽ tệ hơn không có.

### 3.3. Phạm vi

- **Chỉ tạo mới:** `scripts/stream_health_check.py`, `tests/test_stream_health_check.py`.
- **Không sửa** `trading/collector/*`, `scripts/sched.sh`, `scripts/engine_consumer_check.py`,
  `scripts/heartbeat_check.py`, `trading/alerts.py`, hay bất kỳ file nào của đường crypto.
- **Không đăng ký scheduled task.** Việc gắn vào lịch là của chủ dự án, như chuông 2C.

### 3.4. Kiểm chứng Task 3

Test đọc log từ **chuỗi dựng sẵn trong test**, không gọi `docker`:

1. Log có 3 dòng `bars closed` trong khoảng phiên → `exit 0`, in đúng số 3.
2. Log **không** có dòng nào trong khoảng phiên → `exit 2`, thông điệp mở đầu bằng `dung:`.
3. Log có dòng `bars closed` nhưng **ngoài** khoảng phiên → vẫn `exit 2`. Đây là bài test bắt
   đúng tình huống hôm nay: backfill chạy sau phiên không được tính là luồng sống.
4. Log chỉ có `backfill done` mà không có `bars closed` → `exit 2`. Tình huống thật của sáng nay.
5. Ruff sạch, suite đầy đủ pass (mốc hiện tại **728**), **cổng cứng VN khớp từng chữ số**:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## 4. Ràng buộc chung

- `real_trading_enabled` giữ `false`. Không gọi BingX, không gọi Binance. Không gọi SSI ngoài
  việc **đọc log** (bản thân collector tự gọi, đó là chuyện của nó).
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Không đụng NATS: không `delete`, `purge`, `add`,
  `update` stream hay consumer nào.
- **Không dựng lại container trong phiên.** Sau 14:45 cũng không, trừ khi tôi giao rõ.
- `.env` không sửa, không mở, không in. `config/config.yaml` không sửa.
- Không xoá file. **Không commit, không push.**
- Mọi output dán vào báo cáo copy từ terminal. Thiếu thì ghi **"CHƯA LÀM"** kèm lý do,
  **không bịa**.
- **GitNexus:** MCP hiện **không kết nối được** (timeout). Chạy `npx gitnexus analyze` bằng CLI
  trước và sau; nếu CLI cũng hỏng thì **ghi rõ trong báo cáo**, đừng lặng lẽ bỏ qua.

---

## 5. Báo cáo cho Claude

1. Task 1: dòng `bars closed` đầu tiên của phiên chiều, hoặc **"KHÔNG CÓ"** kèm 20 dòng log
   `SSIFeed` gần nhất.
2. Task 2: bốn số ở §2.2, hoặc **"CHƯA LÀM"** kèm lý do. Kèm đề xuất `grace` và lý do.
3. Task 3: kết quả 5 tiêu chí, `git diff --stat`, `git status --short`.
4. Ba dòng: số test pass (mốc **728**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 6. Việc của chủ dự án, agent không làm được

Nhắc lại, vì sự cố hôm nay là hệ quả trực tiếp của việc thứ nhất:

1. **`powercfg /change standby-timeout-dc 0`** — máy đã ngủ **sáu lần** từ thứ Sáu tới nay, một
   lần hơn bảy tiếng. Mỗi lần tỉnh là một lần DNS chết và luồng SSI có thể không nối lại được.
   Đây là gốc của toàn bộ sự cố hai phiên vừa rồi.
2. **Chuyển VPS.** Sự cố hôm nay là lần thứ hai trong bốn ngày. Không còn là "nên làm".
3. **Đăng ký scheduled task cho chuông 2C**, và sau đợt này là cả `stream_health_check`.
4. **Nếu Task 1 báo luồng chết:** chạy `scripts/spike_ssi_sdk_auth.py` (nhập OTP) rồi
   `scripts/load_token_to_db.py`. Bước thứ hai là **cầu nối duy nhất** sang DB — collector đọc
   token từ DB, không đọc file. Bỏ bước đó thì OTP vô nghĩa.
