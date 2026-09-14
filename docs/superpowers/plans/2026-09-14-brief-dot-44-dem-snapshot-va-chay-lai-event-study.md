# Brief đợt 44 — Đếm snapshot để hết mù, và chạy lại event study cho đúng

Ngày giao: 14/09/2026.
Base: `23662db` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Ba task, hai đường độc lập. Task 1 và 2 là đường VN, Task 3 là đường crypto. Không xung đột file.

---

## 0. Bối cảnh — hai điều tôi đo được sau khi nghiệm thu đợt 43

### 0.1. Ta không thể phân biệt "SSI không gửi" với "ta đánh rơi"

Phiên chiều 14/09, quy về giờ Việt Nam, chuỗi chốt nến từ luồng:

```
14:05  (lag 46,6s)
14:10  (lag 65,8s — chốt lúc 14:16:05)
       ...im lặng 15 phút, không một dòng log...
14:25  (lag 78,3s — chốt lúc 14:31:18)
14:45  (lag 66,2s — chốt lúc 14:51:06)
```

Khung **14:15** và **14:20** không có nến, dù có mặt ở cả bốn phiên trước (08, 09, 10, 11).

Tổng `n` của các dòng `bars closed` là **51 = 17 × 3** — mọi nến buổi chiều đều đến từ luồng,
không có backfill nào chen vào. Nên hai khung kia không phải bị ghi đè; chúng **chưa từng tồn tại**.

**Và ta không có cách nào biết vì sao.** Snapshot thô của SSI **không được lưu ở đâu cả**:
stream NATS `BARS` chứa **nến đã chốt**, không chứa snapshot; log chỉ ghi snapshot khi nó tới
muộn. Nên câu hỏi *"SSI có gửi snapshot cho khung 14:15 không"* **không trả lời được bằng dữ
liệu đang có** — cả ngày chỉ có **một** dòng `late snapshot`, và nó thuộc khung 14:25.

Đây cùng hạng với lỗ hổng tôi tìm ra sáng nay (backfill che mất luồng chết): hệ thống **mù một
cách im lặng** trước phân biệt quan trọng nhất của chính nó. Task 1 bịt chỗ đó.

### 0.2. Phân bố `lag_ms` lưỡng đỉnh — và đó mới là thứ quyết định `grace`

```
n=45   min=1,6s   p25=1,7s   trung vị=13,6s   p75=43,8s   p90=58,6s   max=78,3s   | >60s: 4 lần
```

`min` và `p25` đều ~1,6 giây rồi nhảy vọt. Đó là chữ ký của **hai cơ chế đóng nến khác nhau**:

| Cơ chế | Khi nào | Độ trễ |
|---|---|---|
| Snapshot của khung **kế tiếp** tới → đóng khung cũ | mã giao dịch dày | **~1,6s** |
| `flush_due` hết `grace` = 60s | mã thưa, hoặc cuối phiên | **43–78s** |

Nghĩa là ở nhánh chậm, **độ trễ gần như bằng chính `grace`**. Hạ `grace` sẽ cắt thẳng vào cái
đuôi đó. Nhưng đổi lại, snapshot nào tới sau `grace` sẽ bị bỏ.

Cả ngày **đúng một** snapshot tới muộn: `HPG`, khung `14:25`, muộn **1,615 giây**.

Một mẫu duy nhất. **Quá ít để chốt `grace`**, và đó là lý do Task 2 là đo tiếp chứ không phải
chỉnh. Nhưng nó gợi ý mạnh rằng `60s` đang rộng hơn mức cần rất nhiều — và Task 1 sẽ cho biết
chính xác.

### 0.3. Event study đợt 42 phải chạy lại

Ba chân trời được thử, đúng một cái vượt ngưỡng theo từng chân trời. Xác suất ít nhất một cái
vượt do may rủi là `1 − 0,95³ ≈ 14%`. Ngưỡng đúng là phân vị 95 của **giá trị lớn nhất**.

Và trước cả thống kê: lợi thế **+12,85 điểm cơ bản** mỗi sự kiện, phí taker một vòng **10 điểm
cơ bản**. Còn lại **~2,85 điểm cơ bản** trước trượt giá và funding.

Lỗi ở cách tôi viết tiêu chí brief 42 §4.2. Task 3 sửa cả hai chỗ.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `trading/collector/latch.py` | có sẵn | 1 — đếm snapshot mỗi bucket |
| `trading/collector/main.py` | có sẵn | 1 — in số đếm + chuông im lặng |
| `tests/test_latch.py` | có sẵn | 1 — test mới, **không sửa test cũ** |
| `scripts/event_study_module_c.py` | có sẵn | 3 — thống kê giá trị lớn nhất + ngưỡng chi phí |
| `tests/test_event_study.py` | có sẵn | 3 |
| `docs/superpowers/research/2026-09-15-dot-44-*.md` | **mới** | báo cáo |

**Không sửa** `trading/engine/*`, `trading/bus/*`, `trading/storage/db.py`, `trading/alerts.py`,
`scripts/stream_health_check.py`, `scripts/measure_session_stream_metrics.py`,
`trading/feature_panel.py`, `scripts/audit_information.py`, `scripts/probe_timestamp_semantics.py`,
`config/config.yaml`, `.env`.

Ràng buộc chung như đợt 43: `real_trading_enabled` giữ `false`, không gọi SSI/BingX/Binance,
không đụng NATS (không `delete`/`purge`/`add`/`update` stream hay consumer), không
`TRUNCATE`/`DROP`, không xoá file, **không commit, không push**. Mọi output copy từ terminal,
thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

---

## Task 1 — Đếm snapshot, và chuông im lặng trong phiên

**Đây là code đường chạy thật của hệ thống giao dịch. Phẫu thuật, không hơn một dòng thừa.**

### 1.1. Đếm snapshot mỗi bucket

Trong `BarLatch`, đếm số snapshot đã nhận cho mỗi `(symbol, bucket)` đang giữ. Khi bucket đóng,
trả kèm số đếm đó.

Trong `persist_bars`, thêm số đếm vào alert `bars closed` đã có:

```json
{"level": "INFO", "msg": "bars closed", "n": 1, "symbols": ["HPG"], "lag_ms": 1634.96, "snapshots": [12]}
```

`snapshots` là danh sách song song với `symbols`, cùng thứ tự.

**Ràng buộc tuyệt đối:** đây là thay đổi **thuần quan sát**. Không đổi điều kiện đóng bucket,
không đổi `grace`, không đổi `flush_due`, không đổi `_last_closed_ts`, không đổi thứ tự gì.
Sau thay đổi, hệ thống phải chốt **đúng những nến cũ, vào đúng lúc cũ**.

### 1.2. Chuông im lặng trong phiên

Thêm một cảnh báo trong `housekeeping_tick`: nếu **trong giờ giao dịch** mà **không snapshot nào
của bất kỳ mã nào** tới trong **120 giây** liên tiếp, phát:

```
alert("WARN", "khong nhan snapshot nao trong N giay (trong phien)", seconds=..., last_snapshot_ts=...)
```

Ngưỡng `120s` = hai lần khung nến 60s của `grace`. Chỉ phát **một lần** cho mỗi đợt im lặng
(giống `_warned_nav_discrepancy_accounts` của `real_orders.py`) — không spam mỗi tick.

**Dùng lại `is_trading_time(now, holidays)` sẵn có.** Không viết lại lịch phiên.

Chuông này sẽ trả lời trực tiếp câu hỏi của §0.1: khoảng 14:16→14:31 hôm nay là SSI im, hay ta
đánh rơi.

### 1.3. Kiểm chứng Task 1

1. **Toàn bộ test hiện có của `tests/test_latch.py` pass, không sửa một `assert` nào.** Dán
   `git diff` của file đó — tôi kỳ vọng chỉ có **phần thêm mới**, không có dòng bị xoá.
2. Test: ba snapshot vào cùng một bucket, bucket đóng → `snapshots` trả về `3`.
3. Test: bucket đóng bằng `flush_due` cũng trả đúng số đếm.
4. Test: số đếm **reset** khi sang bucket mới — bucket thứ hai không cộng dồn bucket thứ nhất.
5. Test: **hành vi đóng nến không đổi** — dựng lại đúng kịch bản của test đợt 36 (ba snapshot
   khung A, một snapshot khung B) và khẳng định `pub.publish` vẫn được gọi **đúng một lần**,
   với đúng giá trị cũ.
6. Test chuông im lặng: giả lập 120s không snapshot **trong giờ** → phát đúng một WARN; lặp
   thêm tick nữa → **không** phát thêm. Ngoài giờ → **không** phát.
7. Suite đầy đủ pass (mốc hiện tại **741**), ruff sạch, **cổng cứng VN khớp từng chữ số**:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

### 1.4. Triển khai — ngoài giờ giao dịch

**Không dựng lại container trong phiên.** Build và `up -d` chỉ sau **15:00** hoặc trước
**08:45** giờ Việt Nam.

Trước khi build, lưu ảnh rollback theo đúng khuôn các đợt trước:

```
docker tag <image collector hiện tại> dot44-rollback-collector:pre
```

Sau khi triển khai, dán:
- ID ảnh đang chạy và ID ảnh vừa build (phải khớp).
- Kết quả `docker exec <container> grep -c "snapshots" /app/trading/collector/main.py` — chứng
  minh code mới thật sự nằm trong container đang chạy. *(Đợt 40–43 tôi đã một lần phải tự kiểm
  điều này; từ nay nó là tiêu chí.)*

---

## Task 2 — Đo thêm ba phiên, chưa chỉnh `grace`

**Không sửa code. Không chỉnh tham số.**

### 2.1. Việc

Sau mỗi phiên **thứ Ba 15/09, thứ Tư 16/09, thứ Năm 17/09** (chạy sau 15:05), dùng công cụ
sẵn có của đợt 43 để lấy:

- Phân bố `lag_ms`: min, p25, trung vị, p75, p90, p95, max, và **số lần vượt 60s**.
- Phân bố `late_ms` và **tổng số dòng `late snapshot`**.
- **Mới có từ Task 1:** phân bố số `snapshots` mỗi nến — min, trung vị, max.
- Danh sách khung nến **thiếu** so với khung chuẩn của phiên, nếu có.
- Có dòng WARN "không nhận snapshot nào" nào không, và vào lúc nào.

### 2.2. Câu hỏi ba phiên này phải trả lời

1. Khung nến thiếu có **lặp lại** không, hay 14/09 là ngoại lệ?
2. Khi một khung thiếu, có kèm WARN im lặng không? (SSI im) — hay không có WARN? (ta đánh rơi)
3. Phân bố `late_ms` trên nhiều mẫu hơn: **snapshot muộn nhất là bao nhiêu giây?** Đây là con
   số duy nhất quyết định `grace` an toàn tối thiểu.

### 2.3. Vẫn không chốt `grace`

Báo cáo số và **đề xuất** kèm lý do. Tôi quyết định, sau khi có đủ bốn phiên. Một tham số điều
khiển việc nến có bị chốt thiếu dữ liệu hay không thì không đổi dựa trên một phiên.

---

## Task 3 — Chạy lại event study cho đúng

### 3.1. Sửa một: thống kê giá trị lớn nhất

Hiện `scripts/event_study_module_c.py` so lợi suất mỗi chân trời với phân vị 95 null **của
riêng chân trời đó**. Sai, vì ba phép kiểm.

Thay bằng: mỗi lần hoán vị, tính lợi suất trung bình cho **cả ba chân trời**, quy mỗi cái thành
**phân vị thực nghiệm** trong phân phối riêng của nó, rồi lấy **giá trị lớn nhất trong ba**.
Lặp 1000 lần → phân phối null của thống kê lớn nhất. Kết quả thật vượt khi **phân vị lớn nhất
của nó** vượt **phân vị 95 của phân phối đó**.

Dùng `calculate_percentile` và `empirical_percentile_rank` **import từ `trading.metrics`**.
Không viết lại.

**Nếu chạy cả chiều SHORT** thì thống kê lớn nhất tính trên **sáu** phép kiểm (2 chiều × 3 chân
trời), và phải báo cáo cả sáu.

### 3.2. Sửa hai: ngưỡng chi phí, khai báo trước

Thêm một điều kiện **trước** mọi phép kiểm thống kê:

```
loi_the_rong = loi_suat_TB_su_kien - loi_suat_khong_dieu_kien - chi_phi_vong_lenh
chi_phi_vong_lenh = 2 * BINGX_PERP_TAKER = 0.0010 = 10 điểm cơ bản
```

Import `BINGX_PERP_TAKER` từ `trading.crypto_fees`. **Không gõ lại con số.**

In `loi_the_rong` cho cả ba chân trời. **Âm thì kết luận là âm, bất kể phân vị.** Một lợi thế
không bù nổi phí không phải là lợi thế.

### 3.3. Tiêu chí chốt trước — thay thế §4.2 của brief 42

**Cả bốn** phải đúng:

1. Số sự kiện **≥ 30**, **và**
2. `loi_the_rong > 0` ở ít nhất một chân trời, **và**
3. Phân vị lớn nhất của kết quả thật **vượt phân vị 95** của phân phối null giá trị lớn nhất, **và**
4. Chân trời thoả (2) và chân trời thoả (3) là **cùng một chân trời**.

Điều 4 để chặn việc lấy chân trời này cho ý nghĩa thống kê và chân trời kia cho lợi nhuận.

Thiếu một điều → **kết quả âm**. Không nới điều kiện, không bỏ vế, không kéo dài cửa sổ.
**2026 vẫn niêm phong.**

### 3.4. Kiểm chứng Task 3

1. Bốn test hiện có của `tests/test_event_study.py` vẫn pass. Test đối chứng dương/âm có thể
   phải sửa ngưỡng vì phương pháp đổi — **chỉ sửa phần ngưỡng, không sửa phần dựng dữ liệu**,
   và dán `git diff`.
2. Test mới: `loi_the_rong` bằng đúng `chênh lệch − 0.0010`, tính lại trong test.
3. Test mới: một chân trời có phân vị cao nhưng `loi_the_rong` âm → kết luận **âm**.
4. **Đối chứng dương vẫn phải xanh:** chuỗi tổng hợp có lợi thế lớn hơn hẳn phí → vượt cả bốn
   điều kiện.
5. Chạy thật và báo cáo: số sự kiện, ba dòng `loi_the_rong`, phân vị lớn nhất, ngưỡng, kết luận.
   Tôi kỳ vọng kết quả **âm** — nếu nó vẫn dương, dán đủ số để tôi tự kiểm.

---

## 4. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. **`git diff tests/test_latch.py`** — kỳ vọng chỉ có phần thêm.
3. Task 1: kết quả 7 tiêu chí, ID ảnh, và output lệnh `grep -c` bên trong container.
4. Task 2: bảng ba phiên (hoặc **"CHƯA LÀM — chưa tới phiên"** nếu chạy brief trước 15/09).
5. Task 3: kết quả 5 tiêu chí, bảng đầy đủ, kết luận theo §3.3.
6. Ba dòng: số test pass (mốc **741**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 5. Điều KHÔNG thuộc phạm vi

- **Không chỉnh `grace`.** Đo, đề xuất, dừng. Xem §2.3.
- **Không đổi hành vi chốt nến.** Task 1 thuần quan sát. Nếu một test cũ của `latch` phải sửa
  để xanh → **dừng, báo cáo**: nghĩa là đã đổi hành vi.
- **Không đụng dữ liệu 2026** bên crypto.
- **Không** thêm đặc trưng, không thử biến thể điều kiện module C.
- **Không** dựng lại container trong phiên.
- Ba việc của chủ dự án: **`powercfg /change standby-timeout-dc 0`** (gốc sự cố hai phiên tuần
  trước, vẫn chưa chạy), đăng ký lịch cho `stream_health_check` và chuông 2C, và chuyển VPS.
