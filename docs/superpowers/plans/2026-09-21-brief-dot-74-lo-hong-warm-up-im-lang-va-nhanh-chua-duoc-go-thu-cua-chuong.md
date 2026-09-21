# Brief đợt 74 — Lỗ hổng warm-up im lặng, và nửa quả chuông chưa từng được gõ thử

Ngày giao: 21/09/2026 (thứ Hai, trong phiên).
Base: main `9c2c992`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

> **Thứ tự: đợt 74 → rồi đợt 72.** Brief 72 (gộp hai công cụ đo rò rỉ) vẫn nguyên giá trị,
> nhưng phát hiện dưới đây đo được **trong phiên hôm nay** và ảnh hưởng tới mọi lần khởi động lại
> giữa phiên — nên làm trước.

---

## 0. Đợt 73 đã xong và đã commit

Tôi tự chạy lại, không tin báo cáo:

| | DB không với tới được | Suite đầy đủ |
|---|---|---|
| Trước | 2 failed, 713 passed, 114 deselected, **284,13s** | — |
| Sau | 0 failed, **713 passed, 116 deselected, 9,92s** | **829 passed** |

713 + 116 = 829 — không mất test nào, chỉ đổi chỗ. Nhãn gắn ở **cấp hàm**, đúng như brief yêu cầu
(file còn `test_1`/`test_2` chạy trên dữ liệu tổng hợp, gắn cả file là làm hỏng). `gitnexus
detect_changes`: risk low, 0 affected process. Đã commit + push `9c2c992`.

**Task 4 (ý kiến chống tái phát) vẫn để mở** — quyết sau phiên, không làm trong đợt này.

---

## 1. Việc đo được hôm nay, 21/09, trong phiên thật

### 1.1. Tin tốt: cơ chế ghi log bền vững ĐẠT

`logs/engine_alerts.log` có **85 dòng của hôm nay**, đang ghi tiếp tới 13:15. Đây là phiên đầu tiên
cơ chế durable handler chạy trọn vẹn. Tiêu chí đọc đặt ra từ đợt 70 đã thỏa: log không còn chỉ nằm
trong `docker logs`.

### 1.2. Tin xấu thứ nhất: Docker Desktop tắt đêm thứ hai liên tiếp

`logs/.docker_down_last_alert` ghi 09:05 hôm nay. **Chuông kêu đúng** — nhưng phục hồi là thủ công,
và stack chỉ lên lúc **09:32:16, tức 17 phút sau giờ mở cửa 09:15**.

### 1.3. Tin xấu thứ hai — cái quan trọng: warm-up chạy TRƯỚC backfill

Bằng chứng, từ `logs/engine_alerts.log` và `docker compose logs collector`, cùng một mốc thời gian:

```
02:32:15.159  warm-up HPG xong  bars=201  until=2026-09-18 07:45:00+00   <- THỨ SÁU
02:32:15.206  warm-up IJC xong  bars=201  until=2026-09-18 07:45:00+00
02:32:15.218  warm-up AAA xong  bars=201  until=2026-09-18 07:45:00+00
02:32:17.355  backfill done  counts={"HPG": 4, "IJC": 4, "AAA": 4}       <- 2,1 GIÂY SAU
```

Bảng `bars` **có đủ** các nến 09:15 / 09:20 / 09:25 của hôm nay (27 dòng, 3 mã × 9 nến trong giờ
đầu). Nhưng nến đầu tiên engine xử lý hôm nay là **09:30**.

Ba nến đó vào DB bằng **backfill**, và `trading/collector/backfill.py` **không publish lên NATS**
(grep `publish|nats|bus` trên file: rỗng). Nên engine không bao giờ nhìn thấy chúng — không qua
warm-up (warm-up đã chạy xong trước đó 2,1 giây), cũng không qua luồng live.

Và `trading/engine/main.py:396-414` có rào chặn bar **lùi hoặc trùng** thời gian, nhưng **không có
rào nào chặn bar nhảy cóc**: nến nhảy từ thứ Sáu 14:45 thẳng tới 09:30 hôm nay được nhận **im
lặng**, không một dòng WARN.

**Vì sao đây không phải chuyện nhỏ.** Hôm nay thiệt hại là 3 nến trên cửa sổ 201 nến — về số học
gần như không đổi gì. Nhưng cơ chế thì sai ở mọi quy mô: khởi động lại lúc 14:00 thì cửa sổ chỉ báo
thiếu **~55 nến của chính phiên đang chạy**, và engine vẫn im lặng y hệt. Chỉ báo bị tính trên một
cửa sổ có lỗ, mà không ai biết là có lỗ.

### 1.4. Tin xấu thứ ba, và tôi nói thẳng giới hạn của nó

`logs/engine_alerts.log` **chưa từng mang một WARNING nào** kể từ khi ra đời 19/09 — grep
`WARNING|CRITICAL|ERROR` trên cả file trả về rỗng.

**Nhưng đó KHÔNG phải bằng chứng hỏng.** Tôi đã kiểm tiếp: `docker compose logs engine` từ 19/09
cũng không có WARN nào — tức **chưa có WARN nào xảy ra để mà ghi**. Vắng mặt ở đây là vắng mặt của
sự kiện, không phải của cơ chế.

Vấn đề thật nằm chỗ khác, và nằm trong test. `DurableAlertFilter` có **hai nhánh**:

```python
if record.name.startswith("trading.alerts"):
    return True                              # nhánh 1
return record.levelno >= logging.WARNING     # nhánh 2
```

`tests/test_logging_setup.py` kiểm nhánh 1 rất kỹ — nhưng nó kiểm bằng hàm `alert()`, mà `alert()`
ghi qua chính logger `trading.alerts`. Nghĩa là **mọi test hiện có đều dừng ở dòng đầu tiên của
filter**. Nhánh 2 — bản ghi WARNING từ một logger khác trong cây `trading.*` — **chưa từng được
kiểm một lần nào**. Nhánh phủ định (INFO từ logger khác phải **không** được ghi) cũng vậy.

Theo FEE-ALARM-2: chuông chưa bao giờ được gõ thử thì chưa được coi là chuông.

---

## 2. Ràng buộc

- **Không rebuild, không deploy, không `docker compose up` gì trước 14:45** (phiên đang chạy). Sửa
  code cứ sửa, nhưng container đang chạy không được đụng tới.
- **Không tắt / khởi động lại Docker.**
- Không đổi `docker-compose.yml`, không đổi thứ tự khởi động service trong đợt này (xem Task 3).
- Không sửa `trading/collector/backfill.py`.
- Không tự vá lỗ hổng ở Task 1 — **chỉ phát hiện và báo động**. Lý do ở §3.1.
- Không commit, không push.

---

## Task 1 — Engine phải kêu lên khi cửa sổ chỉ báo của nó có lỗ

**Không** tự động nạp bù. Chỉ phát hiện và báo động.

### 1.1. Việc phải làm

Trong `trading/engine/main.py`, ở chỗ xử lý **nến live đầu tiên của mỗi mã** sau khi warm-up xong:
so `bar.ts` với `warmed_until[sym]`. Nếu khoảng cách **lớn hơn một bước nến** (tức có nến nằm giữa
mà engine chưa hề thấy), phát `alert("WARN", ...)` nêu rõ: mã, mốc warm-up kết thúc, mốc nến đến,
và **số nến bị thiếu**.

Chỉ kiểm **một lần cho mỗi mã** — nến live đầu tiên. Từ nến thứ hai trở đi cửa sổ đã liền mạch,
kiểm tiếp là ồn vô ích.

### 1.2. Công cụ đã có sẵn — dùng lại, đừng viết bản thứ hai

**Nghỉ trưa và cuối tuần không phải là lỗ.** Đếm số nến thiếu bằng phép chia thời gian thuần túy
thì **mọi phiên sáng đều báo động giả** — mà báo động giả giết chuông báo nhanh hơn cả không có
chuông.

Dự án **đã có** đúng công cụ cần: `trading/calendar_vn.py`.

- `market_minutes_between(start, end, holidays, sessions)` — đếm **phút trong phiên**, đã bỏ qua
  nghỉ trưa, cuối tuần, ngày lễ (dòng 45-79).
- `CONTINUOUS_SESSIONS = [(09:15, 11:30), (13:00, 14:30)]` (dòng 82) — **đây** mới là khung khớp
  với lưới nến, **không phải** `SESSIONS` (bắt đầu 09:00, gồm cả ATO, sẽ cho kết quả sai).
- Ngày nghỉ lấy từ `cfg.holidays` (`trading/config.py:14`), đúng nguồn mà collector đang dùng.

**"Một công thức, một chỗ": không được viết lại lịch phiên.** Nếu bạn thấy cần một hàm mới trong
`calendar_vn.py`, được — nhưng phải dùng lại `is_trading_day`/`market_minutes_between` bên trong,
không chép logic.

### 1.3. Cạm bẫy tôi đã đo được và bạn sẽ vấp: **nến ATC 14:45**

Tôi đã đếm lưới nến thật của HPG chiều thứ Sáu 18/09:

```
11:00 11:05 11:10 11:15 11:20 11:25 | 13:00 ... 14:20 14:25 | 14:45
```

Ba điều rút ra, đều đã kiểm bằng dữ liệu chứ không suy đoán:

1. `ts` của nến là **mốc BẮT ĐẦU** của khoảng 5 phút (nến 11:25 phủ 11:25–11:30).
2. Phiên sáng kết thúc ở nến 11:25, phiên chiều ở nến 14:25 — **khớp đúng** `CONTINUOUS_SESSIONS`.
3. **Nhưng có thêm một nến ATC ở 14:45**, và không có 14:30/14:35/14:40. Nến ATC **nằm ngoài**
   `CONTINUOUS_SESSIONS`, nên nó **phá lưới đều**.

Hậu quả cụ thể, tôi đã tính ra để bạn đối chiếu: với `warmed_until` = thứ Sáu **14:45** (nến ATC)
và nến live đầu tiên = thứ Hai **09:30**, `market_minutes_between` trả về **15 phút**. Công thức
ngây thơ `15/5 − 1 = 2` cho ra **2**, trong khi số nến thiếu thật là **3** (09:15, 09:20, 09:25) —
lệch đúng một nến, vì quãng từ nến ATC tới hết phiên không được tính.

Công thức phải **đúng cả hai ca**: liền mạch trong phiên (11:20 → 11:25 ⇒ 0 nến thiếu) và ca
qua-ATC ở trên (⇒ 3). Bạn tự chọn cách xử lý ATC, nhưng **cả hai con số phải ra đúng**, và phải
giải thích cách xử lý trong báo cáo.

### 1.4. Chuyện nhỏ nhưng đừng bỏ sót

Mã nào **không** warm-up được (`warmed_until` không có khóa đó — xem `main.py:141-148`) thì bỏ qua,
vì nó đã có WARN riêng rồi. Đừng báo động hai lần cho cùng một chuyện.

### 1.5. Kiểm chứng

Bốn test, dùng đúng các mốc dưới đây (đều là mốc thật, lấy từ dữ liệu hôm nay và thứ Sáu 18/09):

1. **Tái hiện đúng tình huống sáng nay**: `warmed_until` = 18/09 **14:45**, nến live đầu =
   21/09 **09:30** → **đúng 3 nến thiếu** và phát WARN nêu rõ mã + hai mốc + số nến thiếu.
2. **Không báo động giả** — ba ca, cả ba phải **im lặng**:
   - 18/09 14:45 → 21/09 **09:15** (liền mạch qua cuối tuần, kể cả qua nến ATC);
   - **11:25 → 13:00** cùng ngày (liền mạch qua nghỉ trưa);
   - **11:20 → 11:25** (liền mạch trong phiên — ca tầm thường, nhưng là ca dễ làm hỏng công thức
     nhất).
3. **Chỉ kêu một lần**: sau WARN ở nến đầu, các nến sau không phát thêm WARN nào.
4. `uv run pytest -m "not integration" -q` xanh, và **nói rõ số test trước → sau**.

Nếu ca 1 và ca 2 không cùng lúc đúng được bằng một công thức, **dừng lại và báo cáo** — đừng nhét
thêm điều kiện đặc biệt cho tới khi test xanh. Công thức phải giải thích được.

---

## Task 2 — Gõ thử nửa quả chuông chưa ai gõ

Thêm vào `tests/test_logging_setup.py` **hai** test, không hơn:

1. **Nhánh 2, ca khẳng định**: ghi một bản ghi `WARNING` qua một logger **không phải**
   `trading.alerts` — ví dụ `logging.getLogger("trading.engine")` — rồi khẳng định nội dung đó
   **có** trong file log. Đây chính là đường mà một cảnh báo thật sẽ đi, và chưa ai từng đi thử.
2. **Nhánh 2, ca phủ định**: ghi một bản ghi `INFO` qua cùng logger đó, khẳng định nội dung đó
   **không** có trong file. Bộ lọc phải lọc; nếu nó cho qua tất thì file log sẽ ngập rác và cảnh
   báo thật chìm nghỉm.

**Không** đổi một dòng nào trong `trading/logging_setup.py`. Nếu một trong hai test đỏ thì **đó là
phát hiện**, không phải cớ để sửa code cho test xanh — báo cáo lại, tôi quyết.

**Kỷ luật test phá hoại** (bắt buộc, dự án này luôn làm): sau khi hai test xanh, **đảo ngược nhánh
2** trong `DurableAlertFilter` (đổi `>= logging.WARNING` thành `return False`), chạy lại, xác nhận
**đúng test 1 đỏ**, rồi **khôi phục nguyên trạng** và xác nhận lại xanh. Dán cả ba kết quả. Test
không bao giờ đỏ được thì không chứng minh được gì.

---

## Task 3 — Nêu ý kiến, KHÔNG làm

Hai câu, trả lời ngắn gọn trong báo cáo:

1. **Thứ tự khởi động.** Warm-up của engine chạy trước khi backfill của collector ghi xong (§1.3).
   Nên xử lý ở đâu: engine chờ tín hiệu "backfill xong"? engine nạp lại warm-up khi phát hiện lỗ?
   collector publish nến backfill lên NATS? hay chấp nhận và chỉ báo động (tức dừng ở Task 1)?
   Nêu ưu/nhược mỗi hướng, **chọn một** và nói vì sao.
2. **Docker Desktop tắt hai đêm liên tiếp.** Đây là chuyện của máy chủ, không phải của repo — nên
   tôi không giao sửa. Nhưng nếu bạn thấy có gì **trong repo** đáng làm (ví dụ giờ chạy của
   `docker_down_alert` hiện chỉ 08:00–15:00 ngày giao dịch, nên đêm nó tắt thì không ai biết), nói
   ra. Nêu thôi.

**Không triển khai hướng nào ở Task 3.**

---

## 4. Không làm

- Không tự nạp bù nến thiếu, không đụng backfill, không đụng docker-compose.
- Không rebuild/redeploy trước 14:45.
- Không viết bản thứ hai của lịch phiên giao dịch.
- Không sửa `trading/logging_setup.py`.
- Không commit, không push.

## 5. Báo cáo cho Claude

1. `git diff` đầy đủ.
2. Task 1: bốn kết quả kiểm chứng ở 1.5, kèm số test trước → sau. Nói rõ **cách xử lý nến ATC**
   trong công thức đếm, và dùng lại hàm nào của `trading/calendar_vn.py`.
3. Task 2: hai test mới, **và ba kết quả của bước phá hoại** (xanh → đảo nhánh, đúng 1 đỏ → khôi
   phục, xanh).
4. `uv run ruff check trading tests` sạch.
5. Task 3: ý kiến, ngắn.
6. Bất cứ điều gì trong brief này mà bạn **đo ra khác** với tôi — báo đúng cái bạn đo được. Tôi chỉ
   chạy một lần và có thể sót.
