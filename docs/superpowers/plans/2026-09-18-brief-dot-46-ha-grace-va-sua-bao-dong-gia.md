# Brief đợt 46 — Hạ `grace`, và sửa chuông báo động giả

Ngày giao: 18/09/2026.
Base: `4206148` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Đây là phần còn nợ của brief 44 Task 2, cộng hai việc mà dữ liệu bốn phiên vừa rồi chỉ ra.

---

## 0. Dữ liệu đã có, và nó nói gì

Đo đạc của đợt 44 chạy đúng từ tối 14/09. Tôi kiểm log collector sáng nay:

```
tổng dòng log   : 12.605
bars closed     : 220      (220/220 đều có cột "snapshots" — đo đạc đợt 44 hoạt động)
late snapshot   : 48       (so với đúng 1 dòng hôm 14/09)
chuông im lặng  : 5
cảnh báo ngủ    : 0        (bốn phiên liền máy không ngủ)
```

### 0.1. Con số quyết định `grace`

```
late_ms:  n=48   min=33ms   trung vị=130ms   p90=2.957ms   max=3.194ms
```

**Snapshot muộn nhất trong bốn phiên là 3,194 giây.** `grace` đang là **60 giây** — gấp
**19 lần** mức muộn tệ nhất quan sát được.

Nhắc lại phân bố `lag_ms` hôm 14/09 để thấy cái giá của việc để `grace` rộng:

```
min=1,6s   p25=1,7s   trung vị=13,6s   p75=43,8s   p90=58,6s   max=78,3s
```

Nhánh chậm (đóng bằng `flush_due`) có độ trễ **gần như bằng chính `grace`**. Hạ `grace` cắt
thẳng vào đó.

### 0.2. Chuông im lặng đang báo động giả theo lịch

Năm lần kêu, quy về giờ Việt Nam:

```
15/09  09:02      17/09  09:02      18/09  09:02
15/09  14:32      17/09  14:32
```

Đúng **hai thời điểm cố định**: `09:02` (trước giờ khớp lệnh liên tục) và `14:32` (giữa phiên
ATC). Cả hai đều là lúc thị trường **không khớp lệnh liên tục**, nên SSI không gửi snapshot là
đúng — không có sự cố nào.

**Đây là lỗi thiết kế của tôi ở brief 44 §1.2.** Tôi viết *"trong giờ giao dịch"* và dùng
`is_trading_time`, nhưng hàm đó bao cả ATO và ATC. Một chuông kêu sai hai lần mỗi ngày sẽ bị
bỏ qua trong một tuần, và khi nó kêu thật thì không ai nhìn. Phải sửa trước khi nó thành nhiễu.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `scripts/measure_session_stream_metrics.py` | có sẵn | 1 — bổ sung cột, **không đổi phép tính cũ** |
| `trading/calendar_vn.py` | có sẵn | 2 — thêm hàm mới, **không sửa `is_trading_time`** |
| `trading/collector/main.py` | có sẵn | 2, 3 — dùng hàm mới; hạ `grace` |
| `tests/test_calendar_vn.py` | có sẵn | 2 — test mới |
| `tests/test_collector_latch.py` | có sẵn | 2 — test mới cho chuông |
| `docs/superpowers/research/2026-09-18-dot-46-*.md` | **mới** | báo cáo |

**Không sửa** `trading/collector/latch.py`, `trading/engine/*`, `trading/bus/*`,
`trading/storage/db.py`, `trading/alerts.py`, `config/config.yaml`, `scripts/measure_strategy.py`,
`scripts/stream_health_check.py`, và toàn bộ đường crypto.

Ràng buộc chung như các đợt trước: `real_trading_enabled` giữ `false`, không gọi mạng ngoài
việc collector tự chạy, **không `TRUNCATE`/`DROP`/xoá dòng trên DB**, không đụng NATS, không
xoá file, **không commit, không push**. Output copy từ terminal, thiếu thì ghi **"CHƯA LÀM"**.

---

## Task 1 — Báo cáo bốn phiên (phần nợ của brief 44 Task 2)

### 1.1. Bảng cho từng phiên 15, 16, 17, 18/09

| Chỉ số | Ghi chú |
|---|---|
| `lag_ms`: min, p25, trung vị, p75, p90, p95, max | và **số lần vượt 60s** |
| `late_ms`: n, trung vị, p90, max | |
| `snapshots` mỗi nến: min, trung vị, max | **mới có từ đợt 44** |
| Số nến chốt từ luồng | so với số dòng trong bảng `bars` cùng phiên |
| Khung nến **thiếu** | so với khung chuẩn phiên đó |
| Chuông im lặng | số lần, giờ Việt Nam |

Mọi mốc thời gian in ra **kèm giờ Việt Nam**, không in UTC trần.

### 1.2. Ba câu hỏi phải trả lời

1. **Khung nến thiếu có lặp lại không?** Ngày 14/09 mất `14:15` và `14:20`. Bốn phiên này có
   mất khung nào không, và có trùng giờ không?
2. **Khi một khung thiếu, có kèm chuông im lặng không?** Nếu có → SSI im. Nếu không → ta đánh rơi.
3. **`snapshots` mỗi nến bằng bao nhiêu?** Nếu nhiều nến chỉ có `1` snapshot thì việc chốt nến
   phụ thuộc nặng vào `flush_due`, và hạ `grace` sẽ có tác động lớn hơn dự kiến — nói rõ.

### 1.3. Kiểm chứng

Đối chiếu số nến đọc từ log với `SELECT count(*) FROM bars WHERE ...` cho từng phiên. Dán cả
hai con số. Truy vấn mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`.

---

## Task 2 — Chuông chỉ kêu trong giờ khớp lệnh liên tục

### 2.1. Hàm mới trong `trading/calendar_vn.py`

Thêm **hàm mới**, **không sửa `is_trading_time`** (nhiều chỗ khác đang dùng nó, kể cả chuông
máy ngủ của đợt 35):

```python
def is_continuous_matching(now: datetime, holidays) -> bool:
    """Đúng khi thị trường đang KHỚP LỆNH LIÊN TỤC — loại ATO và ATC."""
```

Khung giờ khớp lệnh liên tục của HOSE:

```
09:15 – 11:30      (sáng)
13:00 – 14:30      (chiều)
```

Loại: ATO `09:00–09:15`, nghỉ trưa `11:30–13:00`, ATC `14:30–14:45`, và mọi thứ ngoài giờ.

Dùng lại phép kiểm ngày nghỉ/cuối tuần sẵn có của `is_trading_time` — **không viết lại lịch
nghỉ**, không chép danh sách ngày lễ.

### 2.2. Chuông dùng hàm mới

Trong `housekeeping_tick`, đổi điều kiện của **riêng chuông im lặng** từ `is_trading_time`
sang `is_continuous_matching`.

**Không đụng chuông máy ngủ** — nó vẫn dùng `is_trading_time` như cũ, vì nó hỏi một câu khác
("máy có ngủ trong giờ giao dịch không") và câu đó bao cả ATO/ATC là đúng.

### 2.3. Kiểm chứng Task 2

1. Test `is_continuous_matching`: đúng tại `09:15`, `10:00`, `11:29`, `13:00`, `14:29`;
   **sai** tại `09:02`, `09:14`, `11:31`, `12:00`, `14:31`, `14:40`, `15:00`.
   Hai mốc `09:02` và `14:32` là **chính hai thời điểm chuông đã kêu sai** — phải sai.
2. Test: ngày nghỉ lễ và cuối tuần → sai ở mọi giờ.
3. Test chuông: im lặng 120s lúc `09:02` → **không** phát. Im lặng 120s lúc `10:00` → phát
   đúng một lần.
4. **Test chuông máy ngủ không đổi hành vi:** các test hiện có của nó pass nguyên vẹn, không
   sửa một `assert` nào.
5. `git diff` của `trading/calendar_vn.py` chỉ có phần **thêm**, không có dòng bị xoá.

---

## Task 3 — Hạ `grace` xuống **20 giây**

### 3.1. Quyết định và căn cứ

`grace_seconds=60` gán cứng ở `main.py:398` (và mặc định `latch.py:20`).

**Đổi giá trị truyền vào ở `main.py:398` thành `20`. Không đổi mặc định trong `latch.py`** —
giữ nguyên chữ ký để mọi test cũ của latch không đổi hành vi.

Căn cứ: snapshot muộn nhất đo được trong bốn phiên là **3,194 giây**. `20` giây là **hơn sáu
lần** mức đó. Tôi chọn 20 chứ không phải 5 hay 10 vì bốn phiên là mẫu nhỏ và chưa có phiên nào
thực sự căng; sáu lần biên là chỗ tôi thấy cân bằng giữa cắt đuôi độ trễ và giữ an toàn.

Đây là **quyết định của tôi**, không phải đề xuất của agent. Không tự đổi sang số khác.

### 3.2. Triển khai — ngoài giờ

Sau **15:00** hôm nay hoặc trước **08:45** thứ Hai 21/09. Lưu ảnh rollback trước:

```
docker tag <image collector hiện tại> dot46-rollback-collector:pre
```

Sau khi lên, dán:
- ID ảnh vừa build và ID ảnh container đang chạy (phải khớp).
- `docker exec <container> grep -n "grace_seconds" /app/trading/collector/main.py` — chứng minh
  giá trị `20` thật sự nằm trong container đang chạy.

### 3.3. Kiểm chứng Task 3 — phiên thứ Hai 21/09, sau 15:05

**Đây là phần quan trọng nhất, và nó có rủi ro thật: hạ `grace` có thể làm MẤT nến.**

Chạy lại đúng phép đo của Task 1 cho phiên 21/09 và so với nền bốn phiên:

1. **Khung nến thiếu:** phiên 21/09 **không được thiếu nhiều khung hơn** mức nền của bốn phiên
   15–18/09. Thiếu nhiều hơn → **hoàn nguyên về 60 giây ngay**, báo cáo, đừng chỉnh số khác.
2. **`late_ms` vượt 20 giây:** đếm số snapshot đến muộn hơn `grace` mới. Kỳ vọng **0**. Lớn hơn
   0 → nêu rõ, vì mỗi cái là một nến có thể đã bị chốt thiếu dữ liệu.
3. **`lag_ms`:** trung vị và p95 phải **giảm rõ** so với nền. Nêu cả hai bộ số cạnh nhau.

Nếu thứ Hai chưa tới khi báo cáo, ghi **"CHƯA LÀM — chưa tới phiên 21/09"** và giao lại phần này.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. **`git diff trading/calendar_vn.py`** — kỳ vọng chỉ có phần thêm.
3. Task 1: bốn bảng phiên, ba câu trả lời §1.2, đối chiếu số nến với DB.
4. Task 2: kết quả 5 tiêu chí.
5. Task 3: ID ảnh, output `grep -n`, và kết quả ba tiêu chí §3.3 (hoặc **"CHƯA LÀM"**).
6. Ba dòng: số test pass (mốc **752**), ruff, cổng cứng VN đủ bốn con số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không đổi `grace` sang giá trị khác 20.** Xem §3.1.
- **Không sửa `is_trading_time`** và **không đụng chuông máy ngủ**.
- **Không sửa `latch.py`.** Đợt 44 vừa động vào nó; giữ yên.
- **Không xoá dòng `TEST` trong bảng `orders`.** Tôi thấy nó khi audit đợt 45 và nó nên được
  dọn, nhưng xoá dòng trên DB production là việc cần chủ dự án đồng ý riêng, không phải việc
  tiện tay của một đợt khác.
- **Không đụng đường crypto.** Tám chiến lược, tám kết quả âm; 2026 vẫn niêm phong.
- **Không quyết định A/B/C** của đợt 45. Đó là quyết định của chủ dự án.

---

## 4. Việc của chủ dự án

1. **Quyết định A / B / C** (đợt 45) — lớn nhất còn lại của đường VN. Nhắc: lựa chọn A với rổ
   ba mã hiện tại nghĩa là **không giao dịch gì cả** (nến ngày cho 0 tín hiệu trong ba tháng),
   nên chọn A thì phải mở rộng rổ mã cùng lúc.
2. **`powercfg /change standby-timeout-dc 0`** — bốn phiên vừa rồi máy không ngủ lần nào, may
   hơn là chắc. Vẫn nên chạy.
3. **Đăng ký lịch** cho `scripts/stream_health_check.py` và chuông 2C.
4. **Q-2:** `0434221` (NAV 5.021.712) hay `0434226` (NAV 192.582.832)?
5. **9/9 lệnh hết hạn:** cảnh báo là `WARN` và có đi Telegram kèm lệnh xác nhận sẵn. Ông có
   nhận được không, và 15 phút có đủ không?
