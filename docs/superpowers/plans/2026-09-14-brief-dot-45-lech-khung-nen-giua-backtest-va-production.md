# Brief đợt 45 — Lệch khung nến giữa backtest và production

Ngày giao: 14/09/2026.
Base: `f191f01` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Đợt này KHÔNG sửa chiến lược, KHÔNG đổi cấu hình, KHÔNG sửa engine.** Nó chỉ đo một con số
mà cả dự án chưa bao giờ đo, rồi đặt quyết định lên bàn chủ dự án.

---

## 0. Vì sao đợt này, thay vì đường lệnh thật

### 0.1. Đường lệnh thật không phải điểm chặn — nó chỉ là chỗ triệu chứng lộ ra

Tôi kiểm trạng thái hôm nay:

```
pending_real_orders : 9 lệnh, TẤT CẢ expired, 0 lệnh có ssi_order_id
real_order_fills    : 0 dòng
lệnh gần nhất       : 04/09  (mười ngày trước)
```

Chưa một lệnh nào từng được gửi tới SSI.

Tôi đã kiểm một giả thuyết và **nó sai**: tôi ngờ rằng cảnh báo "lệnh chờ xác nhận" ở mức
`INFO` nên không bao giờ tới Telegram (`_NOTIFY_LEVELS = {"WARN", "CRITICAL"}`). Thực tế nó là
`WARN` (`real_orders.py:209-219`), có kèm cả `confirm_cmd` đầy đủ. **Chủ dự án đã được báo.**
Vì sao 9/9 hết hạn là câu hỏi cho chủ dự án, không phải cho agent.

### 0.2. Con số thật sự đáng lo

```
Lệnh giấy 30 ngày qua : 7
Lệnh giấy gần nhất    : 03/09  (mười một ngày trước)
```

**Engine gần như câm.** Nếu chiến lược gần như không phát tín hiệu thì mọi thứ dựng quanh
đường lệnh thật — cửa xác nhận, TTL, lá chắn NAV — đều là bọc quanh một nguồn không chảy.

### 0.3. Và đây là lý do, chưa ai đo

```
trading/strategies/octopus_pullback.py:
    "Xu hướng tăng: close > EMA(200)"
    "binh_quan_20(t) = trung bình của 20 phiên gần nhất"
    "bars_daily là giá ĐÃ back-adjust..."

config/config.yaml:
    bar_interval_minutes: 5
```

**Mọi ngưỡng của chiến lược được hiệu chỉnh theo PHIÊN. Production nạp nến 5 PHÚT.**

`EMA(200)` trên nến ngày là xu hướng khoảng **10 tháng**. Trên nến 5 phút, 200 nến là
`200 × 5 = 1000 phút ≈ 16,7 giờ`, mà một phiên VN chỉ có khoảng 4,75 giờ giao dịch — tức
**khoảng 3,4 phiên**.

Đó không phải "cùng một chiến lược chạy nhanh hơn". Đó là **hai chỉ báo khác nhau**.

### 0.4. Hệ quả nặng nhất: cổng cứng chưa bao giờ mô tả production

Cổng cứng VN mà tôi bắt chạy ở **mọi** đợt từ 37 tới 44:

```
uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt
-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã
```

là một backtest trên **`bars_daily`**. Nó là một cổng hồi quy tốt — nó bắt được mọi thay đổi
ngoài ý muốn, và nó đã làm đúng việc đó suốt tám đợt.

Nhưng nó **chưa bao giờ mô tả thứ engine đang chạy**. Con số `1.514 lệnh` là của chiến lược
trên nến ngày. Engine trên nến 5 phút cho **7 lệnh trong 30 ngày**.

Ghi chú trong `CLAUDE.md` có nhắc phần này — *"ngưỡng thanh khoản từng bị tính sai theo N bar
thay vì N ngày khiến engine gần như câm trên bar 5 phút — gói K (06/09) đã sửa phần lớn"* —
nhưng gói K chỉ sửa **bộ lọc thanh khoản**. Các tham số còn lại (`EMA(200)`, cửa sổ pullback,
ATR) chưa ai rà.

**Đợt này đo cho hết, rồi để chủ dự án quyết.**

---

## 1. Phạm vi

| File | Trạng thái | Việc |
|---|---|---|
| `scripts/compare_timeframe_mismatch.py` | **mới** | công cụ đo |
| `tests/test_compare_timeframe_mismatch.py` | **mới** | test |
| `docs/superpowers/research/2026-09-15-dot-45-lech-khung-nen.md` | **mới** | kết quả + bảng quyết định |

**Không sửa file có sẵn nào.** Đặc biệt **không đụng**:
`trading/strategies/*`, `trading/engine/*`, `trading/collector/*`, `config/config.yaml`,
`scripts/measure_strategy.py`, `trading/risk.py`, `trading/paper_broker.py`, `trading/backtest.py`.

Được import: `trading.strategies.octopus_pullback`, `trading.models.Bar`,
`trading.indicators.*`, `scripts._db_common.resolve_dsn`, `trading.storage.db.Storage`.

**Chỉ đọc DB.** Không ghi, không tạo bảng. Không gọi mạng. `real_trading_enabled` giữ `false`.
Không dựng lại container. Không xoá file. **Không commit, không push.** Thiếu thì ghi
**"CHƯA LÀM"**, **không bịa**.

**Docker vừa mất kết nối một lần lúc tôi soạn brief này** (`failed to connect to the docker API`)
rồi tự phục hồi. Nếu gặp lại: chờ, kiểm `docker ps`, **không** restart container nào.

---

## Task 1 — Bảng đơn vị tham số

Đọc `trading/strategies/octopus_pullback.py` và lập bảng **mọi** tham số có tính chất cửa sổ
thời gian:

| Tham số | Giá trị | Đơn vị theo mã nguồn | Ý nghĩa trên nến NGÀY | Ý nghĩa thật trên nến 5 PHÚT |
|---|---|---|---|---|
| ví dụ `EMA(200)` | 200 | số **bar** | ~200 phiên ≈ 10 tháng | 1000 phút ≈ **3,4 phiên** |
| … | | | | |

Quy đổi dùng **4,75 giờ giao dịch mỗi phiên** (09:15–11:30 và 13:00–14:45 = 2,25 + 1,75 = 4 giờ;
cộng ATC thành ~4,25 — **dùng 4,0 giờ = 48 nến 5 phút mỗi phiên** và ghi rõ giả định này).

**Không đoán.** Tham số nào đọc mã không chắc là đếm theo bar hay theo ngày thì ghi
**"CHƯA XÁC ĐỊNH"** kèm số dòng, để tôi tự đọc. Thà thiếu còn hơn sai.

Nêu rõ tham số nào **đã** được gói K (06/09) sửa sang đếm theo ngày, và tham số nào **chưa**.

---

## Task 2 — Đếm tín hiệu: nến ngày so với nến 5 phút

### 2.1. Việc

Với **ba mã production** `HPG`, `IJC`, `AAA`, trên khoảng **2026-06-01 → 2026-09-12**:

1. Chạy `octopus_pullback` trên **`bars_daily`** → đếm số tín hiệu `bull`/`bear`.
2. Chạy **cùng chiến lược, cùng tham số** trên **`bars`** (nến 5 phút) → đếm số tín hiệu.
3. Đối chiếu với **số lệnh giấy thật** trong bảng `orders` cùng khoảng.

Mọi truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`.

### 2.2. Bảng phải in

| Mã | Số nến ngày | Tín hiệu trên nến ngày | Số nến 5 phút | Tín hiệu trên nến 5 phút | Lệnh giấy thật |
|---|---|---|---|---|---|

Cộng một dòng tổng.

### 2.3. Và một bảng chẩn đoán: vế nào chặn

Trên nến 5 phút, với mỗi mã, đếm **số bar thoả từng điều kiện riêng lẻ** của chiến lược
(xu hướng EMA, pullback, thanh khoản, …), theo đúng khuôn bảng "số giờ thoả từng vế" mà
`scripts/event_study_module_c.py` đã làm cho module C.

Mục đích: biết **vế nào** làm engine câm. Nếu `close > EMA(200)` thoả 60% số bar mà tổng tín
hiệu vẫn bằng 0 thì vế chặn nằm chỗ khác.

Đây là chẩn đoán, **không** phải lý do để chỉnh tham số ở đợt này.

### 2.4. Kiểm chứng Task 2

1. Số nến ngày và số nến 5 phút đọc được khớp với truy vấn `count(*)` trực tiếp trên DB. Dán cả hai.
2. Số lệnh giấy khớp `SELECT count(*) FROM orders WHERE ts ...`. Dán truy vấn và kết quả.
3. **Chiến lược được khởi tạo y hệt cách engine khởi tạo nó.** Đọc `_default_strategy()` trong
   `trading/engine/main.py` và dùng **đúng** tham số đó. Nếu engine truyền tham số mà công cụ
   đo không truyền, mọi con số sẽ vô nghĩa — nêu rõ bạn đã đối chiếu.
4. Chạy hai lần cho kết quả giống hệt.
5. Suite đầy đủ pass (mốc hiện tại **748**), ruff sạch, **cổng cứng VN khớp từng chữ số**:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## Task 3 — Bảng quyết định cho chủ dự án

Trong file nghiên cứu, kết thúc bằng một mục **"Ba lựa chọn"**, mỗi lựa chọn nêu **chi phí và
điều phải chấp nhận**. Không khuyến nghị — đây là quyết định của chủ dự án.

| Lựa chọn | Nghĩa là gì | Phải chấp nhận điều gì |
|---|---|---|
| **A. Engine chạy nến ngày** | engine tiêu thụ `bars_daily`, mỗi phiên một quyết định | mất hoàn toàn khả năng phản ứng trong phiên; toàn bộ hạ tầng độ trễ của đợt 31–44 thành thừa |
| **B. Hiệu chỉnh lại cho nến 5 phút** | giữ khung 5 phút, chọn lại mọi tham số cho khung đó | mọi backtest hiện có **vô giá trị**, phải làm lại từ đầu — và theo đúng kỷ luật đợt 38 (đối chứng ngẫu nhiên) và đợt 41 (hiệu chỉnh đa phép kiểm) |
| **C. Giữ nguyên** | chấp nhận engine là một chiến lược **khác** với thứ đã backtest | không có số liệu nào mô tả thứ đang chạy; cổng cứng vẫn là cổng hồi quy tốt nhưng không phải bằng chứng về hiệu quả |

Với mỗi lựa chọn, nêu **con số cụ thể từ Task 2** làm căn cứ, không nói chung chung.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: bảng đơn vị tham số đầy đủ, kèm các ô **"CHƯA XÁC ĐỊNH"** nếu có.
3. Task 2: hai bảng, năm tiêu chí kiểm chứng, và **xác nhận đã đối chiếu `_default_strategy()`**.
4. Task 3: bảng ba lựa chọn kèm số.
5. Ba dòng: số test pass (mốc **748**), ruff, cổng cứng VN đủ bốn con số.
6. Đường dẫn file nghiên cứu mới.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không chỉnh một tham số nào** của `octopus_pullback`. Đo, báo cáo, dừng.
- **Không đổi `bar_interval_minutes`.** Đó là quyết định của chủ dự án sau khi đọc Task 3.
- **Không sửa engine, không sửa cổng cứng.** Cổng cứng vẫn là cổng hồi quy và giữ nguyên vai
  trò đó — đợt này chỉ nói rõ nó **không** phải bằng chứng về production.
- **Không đụng đường lệnh thật**, không đổi TTL, không đổi cửa xác nhận. Xem §0.1.
- **Không đụng đường crypto.** Tám chiến lược, tám kết quả âm; 2026 vẫn niêm phong.
- **Không chạy brief 44 Task 2** — nó có lịch riêng, sau 15:05 các ngày 15, 16, 17/09.

---

## 4. Việc của chủ dự án

1. **`powercfg /change standby-timeout-dc 0`** — vẫn chưa chạy. Docker đã mất kết nối một lần
   trong lúc tôi soạn brief này. Ba phiên đo `grace` (15–17/09) phụ thuộc vào máy không ngủ.
2. **Đăng ký lịch** cho `scripts/stream_health_check.py` và chuông 2C.
3. **Chuyển VPS.**
4. **Q-2:** giao dịch trên `0434221` (NAV 5.021.712) hay `0434226` (NAV 192.582.832)?
5. **9/9 lệnh hết hạn:** cảnh báo là `WARN` và có đi Telegram kèm lệnh xác nhận sẵn. Ông có
   nhận được không, và 15 phút có đủ không? Câu trả lời quyết định cửa xác nhận nên đổi thế nào.
6. **Sau đợt này: chọn A, B hay C ở §Task 3.** Đây là quyết định lớn nhất còn lại của đường VN.
