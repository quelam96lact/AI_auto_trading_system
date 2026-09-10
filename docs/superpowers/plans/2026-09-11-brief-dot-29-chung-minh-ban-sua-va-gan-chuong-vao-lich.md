# Brief đợt 29 — Chứng minh bản sửa có hiệu lực, gắn chuông 2C vào lịch, làm lại kết luận HII

Ngày giao: 10/09/2026, 17:20.
Base: `ebbe425` (main, cây sạch).
Người giao: Claude (planner/auditor).

Đợt 28 đã đóng: chuông 2C kêu trong 5,19 giây thay vì 489,5 giây; bản sửa nến chưa đóng đã
triển khai lúc 16:44 ngày 10/09 (collector `0118d94a6010`, engine `2a8d32201eb5`).

Brief này làm ba việc còn lại. Việc số 1 là quan trọng nhất và **chỉ làm được vào phiên
11/09**.

---

## 0. Trạng thái hiện tại — đọc trước

Bản sửa **đã triển khai nhưng CHƯA được chứng minh là có hiệu lực**. Ta mới xác minh code
nằm vật lý trong container, chưa xác minh nó làm đúng việc trên dữ liệu sống.

Mốc "trước khi sửa", đo bằng message thô, hai phiên độc lập:

| Phiên | Message | Bar duy nhất | Tỷ lệ |
|---|---:|---:|---:|
| 09/09 | 860 | 120 | 7,17× |
| 10/09 | 1.095 | 131 | 8,36× |

---

## 1. Ba việc

| Task | Việc | Khi nào |
|---|---|---|
| 1 | Chứng minh bản sửa có hiệu lực trên phiên 11/09 | **sau 15:05 ngày 11/09** |
| 2 | Gắn chuông 2C vào lịch tự chạy | ngay |
| 3 | Làm lại kết luận HII cho đúng | ngay |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc đợt 26/27/28. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**. `.env` không sửa, không mở, không in.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 1 và Task 3 chỉ `SELECT`.
- **Không `delete`/`purge`/`add`/`update` bất kỳ stream hay consumer NATS nào.** Task 1 chỉ
  dùng `js.get_msg()` và `js.stream_info()`.
- **Không dựng lại container, không `docker compose build/up`** trong brief này. Bản sửa
  đang chạy chính là thứ cần đo — dựng lại là mất phiên đo.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` copy từ terminal, không gõ lại.
- Phát hiện ngoài phạm vi: **báo cáo, không tự sửa**.

---

## Task 1 — Chứng minh bản sửa có hiệu lực (**sau 15:05 ngày 11/09**)

Dùng `scripts/replay_stream_check.py` đã có. **Không viết lại script.**

### 1.1. Bốn tiêu chí, phải đạt CẢ BỐN

**Tiêu chí A — tỷ lệ message/bar về ≈ 1,0.**
Đọc dải seq của phiên 11/09, tính `tổng message / số (symbol, ts) duy nhất`.
→ Đạt khi tỷ lệ **≤ 1,10**. Ghi rõ dải seq đã đọc.

> **CẬP NHẬT 10/09 18:20 — danh mục đã đổi, mốc so sánh đổi theo.** Chủ dự án quyết định bỏ
> HII. `config/config.yaml` giờ là `[HPG, IJC, AAA]`, image đã dựng lại và triển khai lúc
> 18:15. Hệ quả cho tiêu chí B: HII trước đây **thiếu bar** ở những phút không có giao dịch,
> nên hai mốc 120 và 131 đã bị HII kéo xuống. HPG thanh khoản gấp bội nên số bar dự kiến
> **tăng**, tiệm cận trần lý thuyết ~46 khung/phiên × 3 mã ≈ 138. Vì vậy tiêu chí B đọc là:
> số bar **≥ 131** và không vượt trần lý thuyết. Nếu **giảm** so với 131 thì đó là dấu hiệu
> mất bar — dừng và báo cáo.

**Tiêu chí B — số bar KHÔNG được giảm.** Đây là tiêu chí chống hồi quy, và là tiêu chí tôi
quan tâm nhất.

> Một bản sửa hỏng cũng cho tỷ lệ đẹp: nếu `flush_due` không bao giờ chạy, hoặc `BarLatch`
> nuốt bar, thì số message giảm mạnh và tỷ lệ vẫn về 1,0 — nhưng ta **mất dữ liệu**. Tỷ lệ
> 1,0 một mình **không chứng minh được gì**.

Đếm số `(symbol, ts)` duy nhất của phiên 11/09 và so với hai phiên trước (120 và 131).
→ Đạt khi số bar duy nhất nằm trong khoảng **hợp lý so với 120–131** (cùng 3 mã, cùng độ dài
phiên). Giảm quá 15% là **dấu hiệu mất bar** → dừng, báo cáo ngay, đừng tự sửa.

Đối chiếu chéo với DB, ghim múi giờ:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT symbol, count(*) FROM bars
WHERE ts >= DATE '2026-09-11' AND ts < DATE '2026-09-12'
GROUP BY symbol ORDER BY symbol;
```

Số bar trong DB và số `(symbol, ts)` duy nhất trong stream phải **khớp nhau**. Lệch là có
vấn đề.

**Tiêu chí C — khung cuối phiên phải có mặt.** Đây là chỗ `flush_due` được kiểm chứng trong
môi trường thật, không phải trong test.

Khung 5 phút cuối cùng của phiên (14:45) **không bao giờ có snapshot kế tiếp** để kích hoạt
chốt — nó chỉ được phát nhờ `flush_due`. Kiểm tra: trong dải seq phiên 11/09, có message cho
`ts = 2026-09-11 14:45:00+07` của **cả ba mã** không?
→ Thiếu khung này nghĩa là `flush_due` **không chạy trong production**, dù test xanh. Báo cáo
ngay, đây là lỗi nghiêm trọng.

**Tiêu chí D — log không có cảnh báo bất thường dồn dập.**

```
docker compose logs --since 2026-09-11T09:00:00 collector | grep -c "already closed frame"
docker compose logs --since 2026-09-11T09:00:00 engine    | grep -c "non-advancing bar"
```

Vài cái lẻ tẻ là bình thường (snapshot đến muộn có thật). **Hàng chục hoặc hàng trăm** là dấu
hiệu `BarLatch` hoặc rào chắn engine đang đánh nhầm. Ghi con số thật vào báo cáo, đừng ghi
"không có gì bất thường".

### 1.2. Nếu tiêu chí A đạt nhưng B hoặc C trượt

**Dừng lại. Báo cáo. Không tự sửa.** Đó là tình huống bản sửa đổi một lỗi lấy một lỗi tệ hơn
— mất bar còn nguy hiểm hơn bar lặp, vì bar lặp thì rào chắn engine đã chặn, còn bar mất thì
không ai biết.

Đường lùi có sẵn nếu cần: `dot25-rollback-collector:pre` (`41371bc92882`) và
`dot25-rollback-engine:pre` (`93aed2cfc8f7`). **Không tự ý lùi** — báo cáo để tôi quyết.

---

## Task 2 — Gắn chuông 2C vào lịch tự chạy

### 2.1. Vì sao

Hai đợt vừa rồi sửa chuông 2C từ chết câm (`load_config` đòi `SSI_*`, `send_telegram` sai số
tham số) thành kêu trong 5 giây. Nhưng tôi vừa kiểm tra máy này:

```
trading-backfill-universe   Ready
trading-daily-data-check    Ready
trading-deploy-drift        Ready
trading-heartbeat-check     Ready
```

**Không có task nào gọi `engine_consumer_check.py`.** Một cái chuông không ai bấm thì vẫn là
im lặng — đúng khoảng trống mà đợt 24 đã chứng minh là có thật: `heartbeat` engine vẫn tươi
trong khi không ai giám sát engine có thực sự tiêu thụ bar hay không.

### 2.2. Việc cần làm

**Bước 1 — thêm job vào `scripts/sched.sh`.** File này là "một chỗ duy nhất định nghĩa job X
chạy lệnh gì" (bài học `4ea4c8d`: một công thức hai bản thì sớm muộn lệch). Thêm nhánh
`engine-consumer` vào `case`, theo **đúng khuôn** của các nhánh sẵn có:

```bash
  engine-consumer)
    exec "$RUN" engine-consumer.log engine-consumer \
      uv run python scripts/engine_consumer_check.py
    ;;
```

Cập nhật cả dòng `dung:` ở nhánh `*)` và khối chú thích đầu file cho khớp.

**Bước 2 — cập nhật `scripts/run_hidden.vbs`.** Dòng 12 liệt kê job hợp lệ
(`heartbeat | daily-check | backfill`) đã lạc hậu — thiếu cả `deploy-drift` và `engine-cam`
đang có thật trong `sched.sh`. Sửa chú thích cho đúng thực tế, **chỉ chú thích, không đổi
logic**.

**Bước 3 — soạn lệnh đăng ký, KHÔNG tự chạy.** Viết vào báo cáo lệnh PowerShell đăng ký task,
theo đúng khuôn `trading-heartbeat-check` (đã đọc từ máy thật):

- `Execute`: `wscript.exe`
- `Arguments`: `//B //Nologo "<REPO>\scripts\run_hidden.vbs" engine-consumer`
- Lặp mỗi **5 phút**, kéo dài **7 giờ**, bắt đầu **08:00** (giống heartbeat).
- `Principal`: user `quelam`, `RunLevel Limited`, `LogonType Interactive`.

> **Không tự chạy `Register-ScheduledTask`.** Đây là thay đổi ngoài repo, chạm vào lịch hệ
> thống của máy chủ dự án. Soạn lệnh, dán vào báo cáo, để chủ dự án tự chạy.

### 2.3. Kiểm chứng

1. `bash scripts/sched.sh` không đối số → in ra danh sách job **có** `engine-consumer`.
2. `bash scripts/sched.sh engine-consumer` chạy thật → ghi được `engine-consumer.log`, và
   script thoát bằng exit code hợp lệ (0 hoặc 1). Dán output.
3. `bash scripts/sched.sh khong-ton-tai` → exit 2, thông báo dùng đúng.
4. Toàn bộ suite pass, ruff sạch.

**Không sửa** `scripts/run_if_docker_up.sh`, `scripts/heartbeat_check.py`, hay bất kỳ job nào
đang có.

---

## Task 3 — Làm lại kết luận HII cho đúng

Báo cáo đợt 28 có bảng số đúng nhưng kết luận sai trọng tâm. Hai chỗ phải sửa:

### 3.1. Mốc thời gian đang hiển thị UTC

Báo cáo ghi bốn bar `2026-06-01 06:30`, `2026-06-02 03:15`, `2026-09-08 02:20`,
`2026-09-08 02:50`. Không giờ nào trong số đó nằm trong phiên VN. Tôi tra DB:

```
 vn_time                |      utc_time       | close
 2026-06-01 13:30:00+07 | 2026-06-01 06:30:00 |  6020
 2026-06-02 10:15:00+07 | 2026-06-02 03:15:00 |  6030
 2026-09-08 09:20:00+07 | 2026-09-08 02:20:00 |  9010
 2026-09-08 09:50:00+07 | 2026-09-08 02:50:00 |  9050
```

Dữ liệu đúng, hiển thị sai. Đây lặp lại **đúng** bài học đã ghi ở brief 22 §6. Mọi truy vấn
trong task này phải mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`.

### 3.2. "Nút thắt là lệch pha EMA Cross vs MACD" — chưa đúng trọng tâm

Đọc lại chính bảng của báo cáo đợt 28:

| | HII | IJC | AAA |
|---|---:|---:|---:|
| Tỷ lệ giao cắt (tầng 3) | **2,5%** | 2,6% | 2,6% |
| Bar dùng được | **1.461** | 3.950 | 3.835 |

**Tỷ lệ giao cắt của HII gần như bằng hai mã kia.** Tầng 3 không phải chỗ HII khác biệt.
Khác biệt thật nằm ở số bar dùng được — và tôi đã tra tổng số bar thô:

```
 symbol | tong_bar | bar_dau    | bar_cuoi
 AAA    |     4757 | 2026-04-03 | 2026-09-10
 HII    |     3351 | 2026-04-03 | 2026-09-10
 IJC    |     4878 | 2026-04-03 | 2026-09-10
```

HII còn **1.461/3.351 bar dùng được — mất 57%**, trong khi IJC mất 19%. Với 36 ứng viên giao
cắt × ~11% qua MACD × tỷ lệ pullback, kỳ vọng ra **dưới 1 tín hiệu**. Con số 0 là kết quả của
**mẫu nhỏ**, chưa đủ để kết luận HII bị chặn về mặt cấu trúc.

### 3.3. Câu hỏi phải trả lời

Đây là câu hỏi quyết định HII có nên nằm trong danh mục hay không:

1. **Vì sao HII mất 57% bar** trong khi IJC mất 19%? Cổng nào loại chúng — thanh khoản, hay
   thiếu bar trong DB, hay warm-up? Trả lời bằng số: bao nhiêu bar bị loại bởi từng nguyên
   nhân.
2. Nếu là **cổng thanh khoản**: HII có bao giờ đạt ngưỡng một cách ổn định không, hay chỉ
   lác đác? Nếu chỉ lác đác thì HII **không nên nằm trong danh mục** — đó là kết luận cần nói
   thẳng.
3. Giữ nguyên bảng 4 tầng đã có (nó đúng), nhưng **đổi mốc giờ sang giờ VN** và viết lại phần
   kết luận cho khớp với số liệu.

**Chỉ `SELECT`, chỉ báo cáo, không sửa một dòng code nào.** `config/config.yaml` không sửa —
việc bỏ HII khỏi danh mục là **quyết định của chủ dự án**, agent chỉ đưa bằng chứng.

---

## 4. Báo cáo

Ngắn, đủ, đúng thứ tự. **Đừng dán toàn văn `git diff` và output dài** — dán con số và kết
luận.

1. Task 1: bảng bốn tiêu chí A/B/C/D, mỗi tiêu chí một dòng kết quả + con số thật. Kèm dải
   seq và bảng đối chiếu số bar stream vs DB.
2. Task 2: `git diff --stat`, output ba phép kiểm chứng, và **lệnh đăng ký scheduled task**
   soạn sẵn (chưa chạy).
3. Task 3: bảng 4 tầng với **giờ VN**, số liệu trả lời ba câu hỏi ở §3.3, kết luận viết lại.
4. Ba dòng: số test pass, ruff, cổng cứng VN.
5. `git status --short`.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

**Không commit, không push.**

---

## 5. Ngoài phạm vi — quyết định của chủ dự án

Không đổi. Nhắc lại điều lớn nhất, vì nó là thứ duy nhất thực sự chặn go-live:

**Không chiến lược nào có edge đo được.** VN: chiến lược `-1.615.319.902` so với mua-và-giữ
`+1.897.587.481.903`. Crypto 1h/30x: cả bốn chiến lược lỗ 15–21 USDT trong khi mua-và-giữ BTC
`+122,42` USDT (+24,5%).

Cùng nhóm quyết định: Q-2 (tiền ở `0434226` nhưng cấu hình trỏ `0434221`), Q-3 (xác nhận lệnh
+ đối soát), Q-5 (10/13 ngày lễ chưa khai), Q-7 (`risk_pct` cho 30x thật), chuyển VPS, chạy
lệnh đăng ký scheduled task ở Task 2, Docker autostart, và có bỏ HII khỏi danh mục hay không
sau khi có kết luận Task 3.

Thấy thứ gì trong nhóm này chặn việc → **báo cáo, không tự quyết**.
