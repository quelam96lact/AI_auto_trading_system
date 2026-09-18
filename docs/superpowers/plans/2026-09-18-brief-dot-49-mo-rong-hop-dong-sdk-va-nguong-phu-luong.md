# Brief đợt 49 — Mở rộng hợp đồng SDK, ngưỡng phủ luồng, và nhánh chết cuối cùng

Ngày giao: 18/09/2026.
Base: `4c17c35` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Ba việc, đều là **đọc thuần hoặc chỉ sửa file trong repo** — chạy được bất kỳ lúc nào, kể cả
trong phiên. Không dựng lại container, không gọi mạng, không ghi DB.

**Không xung đột với brief 47 Task 2/3** (đo phiên nền rồi triển khai `grace = 20`, sau 15:05
hôm nay) — khác hoàn toàn tập file.

---

## 0. Ba việc, và vì sao chúng còn tồn

### 0.1. Lưới chắn hợp đồng SDK mới phủ một nửa — lỗi của tôi

Đợt 48 dựng `tests/test_ssi_sdk_contract.py`, nhưng bảng bề mặt phụ thuộc tôi viết trong
brief 48 §1.2 **thiếu bốn chỗ**. Agent quét ra và **báo cáo thay vì tự thêm** — đúng nguyên tắc:

| File | Ký hiệu chưa có lưới chắn |
|---|---|
| `trading/collector/backfill.py` | `ssi_sdk.AsyncData`, `ssi_sdk.exceptions.AuthenticationError` |
| `trading/collector/derivative_sync.py` | `ssi_sdk.services.portfolio.AsyncPortfolioService` |
| `scripts/_ssi_spike_common.py` | `Config`, `AsyncAuth`, `SSIError`, `Token` |
| `tests/test_backfill.py` | `ssi_sdk.models.OHLCData`, `ssi_sdk.exceptions.AuthenticationError` |

Backfill hỏng thì thấy ngay (nến thiếu), nên nó không gấp bằng đường đặt lệnh. Nhưng để lưới
chắn nửa vời thì lần sau không ai biết nó phủ tới đâu.

### 0.2. `stream_health_check` không thấy suy giảm một phần

Đợt 47 chứng minh công cụ phân biệt được phiên tốt với phiên chết. Nhưng phiên **17/09 mất 40%**
nến luồng và nó trả `exit 0`:

| Ngày | Nến trong `bars` | Chốt từ **luồng** | Phủ | Công cụ nói |
|---|---|---|---|---|
| 15/09 | 136 | 129 | ~95% | `exit 0` ✅ |
| **16/09** | 156 | **0** | **0%** | `exit 2` ✅ |
| **17/09** | 138 | **82** | **~59%** | `exit 0` ❌ |

Ở brief 47 tôi **cố ý cấm** thêm ngưỡng mềm, lý do ghi rõ: *"ta chưa biết mức bình thường"*.
Giờ ta biết: bốn phiên cho thấy phiên lành nằm quanh **95%**, phiên suy giảm ở **59%**, phiên
chết ở **0%**. Đủ dữ liệu để đặt ngưỡng.

### 0.3. Nhánh chết cuối cùng

```
trading/collector/main.py:235   holidays = getattr(cfg, "holidays", frozenset())
trading/config.py:14            holidays: set[date]        <- field BẮT BUỘC, không mặc định
```

`cfg.holidays` **luôn tồn tại**, nên giá trị mặc định `frozenset()` là nhánh không bao giờ
chạy. Đây là lần thứ tư của mẫu này (đợt 32, 33, 34, 35 đã dọn ba lần trước); tôi gom nó lại
chờ một đợt rảnh, và giờ là lúc.

`CLAUDE.md` nguyên tắc 2 cấm thẳng: *"Không giao cho agent thực thi việc xử lý lỗi cho các tình
huống không thể xảy ra."*

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `tests/test_ssi_sdk_contract.py` | có sẵn | 1 — thêm test, **không sửa 6 test cũ** |
| `scripts/stream_health_check.py` | có sẵn | 2 — thêm cờ, **mặc định giữ hành vi cũ** |
| `tests/test_stream_health_check.py` | có sẵn | 2 — thêm test, **không sửa 5 test cũ** |
| `scripts/sched.sh` | có sẵn | 2 — truyền cờ ngưỡng |
| `trading/collector/main.py` | có sẵn | 3 — bỏ một `getattr` |
| `scripts/check_orders_hygiene.py` | **mới** | 3 — báo cáo mã lạ, **không xoá** |
| `docs/superpowers/research/2026-09-18-dot-49-*.md` | **mới** | báo cáo |

**Không sửa** `scripts/confirm_real_order.py`, `trading/real_orders.py`, `trading/collector/latch.py`,
`trading/calendar_vn.py`, `trading/config.py`, `config/config.yaml`, `.env`, và toàn bộ đường crypto.

Ràng buộc chung: `real_trading_enabled` giữ `false`; **không dựng lại container**; không gọi
mạng; **chỉ đọc DB, không `INSERT`/`UPDATE`/`DELETE`**; không đụng NATS; không xoá file;
**không commit, không push**. Output copy từ terminal, thiếu thì ghi **"CHƯA LÀM"**.

---

## Task 1 — Mở rộng hợp đồng SDK

### 1.1. Việc

Thêm test cho **bốn nhóm ký hiệu** ở §0.1. Với mỗi ký hiệu: khẳng định import được. Với mỗi
**phương thức mà code thực sự gọi**: khẳng định chữ ký đúng tên và **đúng thứ tự** tham số,
theo đúng khuôn `test_2` đã có (`list(sig.parameters.keys()) == [...]`).

**Trước khi viết test cho một phương thức, phải xác định code gọi nó thế nào.** Đọc file gọi,
tìm lời gọi thật, rồi mới viết kỳ vọng. **Không đoán chữ ký từ tên phương thức.**

### 1.2. Ràng buộc — giống đợt 48, nhắc lại vì dễ quên

- **Không khởi tạo client** (`AsyncData(...)`, `AsyncAuth(...)`, `AsyncPortfolioService(...)`).
- **Không `await`** bất kỳ phương thức SDK nào.
- **Không đọc `.env`**, không dùng thông tin xác thực.
- Chỉ `inspect`, `hasattr`, `getattr` trên **lớp** và **module**.

Nếu một ký hiệu chỉ kiểm được bằng cách khởi tạo → **đừng kiểm, báo cáo lại**.

### 1.3. Kiểm chứng

1. **Sáu test cũ của `test_ssi_sdk_contract.py` pass nguyên vẹn, không sửa một `assert` nào.**
   Dán `git diff` của file đó — tôi kỳ vọng chỉ có phần **thêm**.
2. Test mới chạy được **không cần** Docker, DB, hay mạng. Nêu rõ đã xác nhận.
3. **Một bảng liệt kê: ký hiệu nào giờ đã có lưới chắn, ký hiệu nào vẫn chưa và vì sao.** Sau
   đợt này tôi muốn biết chính xác lưới chắn phủ tới đâu — đó là thứ đợt 48 còn thiếu.

---

## Task 2 — Ngưỡng phủ luồng cho `stream_health_check`

### 2.1. Thiết kế — bổ sung, không đổi hành vi mặc định

Thêm một cờ **tuỳ chọn**:

```
--min-coverage-warn 0.90      (mặc định: TẮT)
--min-coverage-crit 0.50      (mặc định: TẮT)
```

**Không truyền cờ → hành vi y hệt hiện tại** (chỉ kiểm nhị phân 0 nến). Đó là điều bảo đảm
năm test cũ không đổi.

### 2.2. Cách tính độ phủ

```
tử số  = tổng n của các dòng "bars closed" trong khoảng phiên      (từ LOG)
mẫu số = (số khung nến khác nhau có trong bảng `bars` cho phiên đó)
         × (số mã trong khoảng đó)                                  (từ DB)
phủ    = tử số / mẫu số
```

**Vì sao dùng DB làm mẫu số dù brief 43 nói "đừng tin DB":** DB nói dối về **nguồn gốc** của
nến, không nói dối về **khung nào tồn tại**. Log cho biết nến nào đến từ luồng; DB cho biết
tổng số nến đáng lẽ phải có. Chính phép so đó đã phơi ra ngày 16/09 và 17/09 — nêu lý do này
vào docstring để người sau không "sửa" nó về đọc-log-thuần.

**Trường hợp biên phải ghi rõ trong báo cáo:** nếu cả backfill cũng không chạy thì mẫu số cũng
nhỏ và độ phủ trông vẫn đẹp. Công cụ **không** phát hiện được tình huống đó — đó là việc của
`heartbeat_check`. Ghi thành giới hạn đã biết, **đừng cố xử lý**.

### 2.3. Mã thoát

| Độ phủ | Mức | Exit |
|---|---|---|
| `< 0.50` **hoặc** 0 nến | CRITICAL | **2** |
| `0.50 ≤ phủ < 0.90` | WARN | **1** |
| `≥ 0.90` | OK | **0** |

`WARN` đủ, không cần `CRITICAL`: `_NOTIFY_LEVELS = {"WARN", "CRITICAL"}` nên cả hai đều tới
Telegram. Ngưỡng `0,90` và `0,50` là **quyết định của tôi** dựa trên bốn phiên ở §0.2
(95% lành / 59% suy giảm / 0% chết). Không tự đổi sang số khác.

### 2.4. Gắn vào `sched.sh`

Nhánh `stream-health)` truyền **sẵn** hai cờ, vì Scheduled Task gọi `run_hidden.vbs stream-health`
không có tham số thêm. Giữ `"$@"` ở cuối để vẫn ghi đè được khi gọi tay.

### 2.5. Kiểm chứng

1. **Năm test cũ pass nguyên vẹn, không sửa một `assert` nào.** Dán `git diff` của
   `tests/test_stream_health_check.py` — kỳ vọng chỉ có phần thêm.
2. Test mới, dùng log và số liệu dựng sẵn trong test (không gọi `docker`):
   phủ `0,95` → exit 0; phủ `0,59` → exit 1 kèm chữ `WARN`; phủ `0,20` → exit 2; **0 nến → exit 2**
   (vẫn như cũ).
3. **Kiểm bằng dữ liệu thật — ba phiên đã biết đáp án:**
   - `--date 2026-09-16` → **exit 2** (0%)
   - `--date 2026-09-17` → **exit 1** (~59%) ← đây là trường hợp đợt 47 để lọt
   - `--date 2026-09-15` → **exit 0** (~95%)

   Dán nguyên văn cả ba, kèm con số độ phủ. Nếu 17/09 **không** ra exit 1 thì phép tính độ phủ
   sai — **dừng, báo cáo**.
4. Không truyền cờ → cả ba ngày đều trả đúng như trước đợt này (16/09 exit 2, còn lại exit 0).

---


### 2.6. BỔ SUNG 18/09 — phiên mặc định phải tường minh

Tôi đăng ký Scheduled Task `trading-stream-health` lúc 12:14 và kích hoạt thử. Kết quả:

```
2026-09-18 12:14:36 stream-health start
dung: phien chieu ngay 2026-09-18 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)
EXIT=2
```

Chạy lúc 12:14 (nghỉ trưa), công cụ tự chọn **phiên chiều** — phiên chưa diễn ra — nên 0 nến và
kêu CRITICAL. Ở 15:10 thì đúng, nhưng **bất kỳ lượt chạy bù nào cũng sẽ báo động giả**, và đó
chính là bệnh đợt 46 vừa chữa.

Vì vậy tôi đã **tắt `StartWhenAvailable`** trên task, khớp đúng bốn task đang chạy được. Cái
giá: máy ngủ lúc 15:10 thì mất luôn lượt kiểm hôm đó.

**Việc cần làm trong Task 2:** làm phiên mặc định **an toàn với lượt chạy muộn**. Quy tắc:

- Nếu `--session` không được truyền, chọn **phiên gần nhất ĐÃ KẾT THÚC** tại thời điểm chạy,
  không phải phiên theo mốc giờ hiện tại.
- Chạy trước `11:30` → phiên chiều **hôm trước**. Chạy `11:30`–`15:05` → phiên sáng hôm nay.
  Chạy sau `15:05` → phiên chiều hôm nay.
- **Không bao giờ** chọn một phiên chưa kết thúc. Nếu không có phiên nào đã kết thúc trong
  vòng 24 giờ (cuối tuần, ngày lễ) → in một dòng `bo qua: ...` và **`exit 0`**, không phải
  `exit 2`. Cuối tuần không có luồng là bình thường.

**Ba tổ hợp tham số, mỗi tổ hợp một hành vi — chốt rõ ở đây để không phải đoán:**

| Tham số | Hành vi |
|---|---|
| `--date` **và** `--session` | kiểm đúng phiên đó của đúng ngày đó (như hiện tại, không đổi) |
| `--date` mà **không** `--session` | kiểm **cả ngày** — cộng nến luồng của hai phiên, mẫu số là toàn bộ khung nến trong ngày |
| **cả hai đều thiếu** | chọn **phiên gần nhất đã kết thúc** theo quy tắc trên — đây là đường mà Scheduled Task đi |

Con số kiểm chứng ở §2.5 mục 3 (`0%` / `~59%` / `~95%`) là số **cả ngày**, nên hàng thứ hai
của bảng trên phải cho đúng ba con số đó.

Test bắt buộc: giả mốc `12:14` thứ Sáu → chọn **phiên sáng thứ Sáu**, không phải phiên chiều.
Giả mốc `10:00` thứ Bảy → `exit 0` với thông điệp bỏ qua.

Sau khi Task 2 xong, tôi sẽ bật lại `StartWhenAvailable`.
---

## Task 3 — Nhánh chết và vệ sinh bảng `orders`

### 3.1. Bỏ `getattr` ở `main.py:235`

Đổi `holidays = getattr(cfg, "holidays", frozenset())` thành `holidays = cfg.holidays`.

**Chỉ một dòng.** Không đụng gì khác trong hàm. `Config.holidays` là field bắt buộc
(`config.py:14`), nên đây là thay đổi thuần cấu trúc, không đổi hành vi.

Kiểm chứng: toàn bộ test của `main.py` và `calendar` pass nguyên vẹn, **không sửa một `assert`
nào**; ruff sạch; và `grep -rn 'getattr(cfg' trading/` trả về **rỗng** — dán kết quả.

### 3.2. `scripts/check_orders_hygiene.py` — báo cáo, KHÔNG xoá

Bảng `orders` hiện có: `IJC 7`, `AAA 5`, `HII 5`, **`TEST 1`**.

Script chỉ đọc, in một bảng: mã, số dòng, mốc đầu/cuối, và phân loại:

- **trong `config.symbols`** — bình thường
- **không trong config nhưng có trong `bars_daily`** — lịch sử hợp lệ (ví dụ `HII`, bỏ khỏi
  cấu hình ngày 10/09)
- **không phải mã thật** — nghi là dấu vết test (ví dụ `TEST`)

Kết thúc bằng **câu lệnh `DELETE` soạn sẵn** cho nhóm thứ ba, in ra như văn bản kèm dòng
cảnh báo, để chủ dự án tự chạy nếu đồng ý.

**Agent không chạy `DELETE`.** Không có ngoại lệ. Xoá dòng trên DB production cần chủ dự án
đồng ý riêng.

Kiểm chứng: đối chiếu số dòng với `SELECT symbol, count(*) FROM orders GROUP BY 1;` — dán cả
truy vấn lẫn kết quả. Chạy hai lần cho output giống hệt.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. **`git diff` của `tests/test_ssi_sdk_contract.py` và `tests/test_stream_health_check.py`** —
   kỳ vọng chỉ có phần thêm.
3. Task 1: kết quả ba tiêu chí, **kèm bảng lưới chắn phủ tới đâu**.
4. Task 2: kết quả bốn tiêu chí, **nguyên văn ba lượt chạy dữ liệu thật kèm độ phủ**.
5. Task 3: `git diff trading/collector/main.py` (kỳ vọng 1 dòng), output `grep -rn 'getattr(cfg'`,
   bảng vệ sinh `orders`, và câu `DELETE` soạn sẵn.
6. Ba dòng: số test pass (mốc **761**), ruff, cổng cứng VN đủ bốn con số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không chạy `DELETE`** trên bảng nào. Xem §3.2.
- **Không đổi ngưỡng `0,90` / `0,50`** sang số khác.
- **Không đổi hành vi mặc định** của `stream_health_check` — không truyền cờ thì phải y như cũ.
- **Không đụng container**, không triển khai gì. `grace = 20` là brief 47 Task 3.
- **Không sửa `confirm_real_order.py`** hay `real_orders.py`. Đợt 48 chỉ kiểm, đợt này cũng vậy.
- **Không bật `real_trading_enabled`.**
- **Không quyết định A/B/C** — đã gác lại, nó không chặn gì khi Q-1 chưa có lời giải.

---

## 4. Việc của chủ dự án

1. **Đăng ký Scheduled Task cho `stream-health`** — lệnh soạn sẵn ở đợt 47. Sau đợt này nó còn
   bắt được cả suy giảm một phần, nên giá trị cao hơn nữa.
2. **Cửa xác nhận 15 phút:** ông có nhận được cảnh báo Telegram không, và 15 phút có đủ không?
3. **Q-1:** có muốn tôi giao một đợt tìm chiến lược nữa, hay dừng hướng đó? Bộ công cụ đo
   (đối chứng ngẫu nhiên, hiệu chỉnh đa phép kiểm, ngưỡng chi phí) đã sẵn sàng và rẻ.
4. **`powercfg /change standby-timeout-dc 0`** và **chuyển VPS**.
5. **`DELETE` dòng `TEST`** trong `orders`, nếu ông đồng ý sau khi đọc báo cáo Task 3.
