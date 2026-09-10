# Brief đợt 31 — Tối ưu độ trễ đường giao dịch

Ngày giao: 10/09/2026, 19:30.
Base: `88bb048` (main, cây sạch).
Người giao: Claude (planner/auditor).

**Thứ tự:** chạy sau brief đợt 29 (bốn task ngày 11/09) và đợt 30. Task 2 sửa cùng file
`collector/main.py` mà đợt 29 đang đo, nên **không được triển khai bản sửa này trước khi đợt
29 Task 1 đo xong** — nếu không sẽ mất mốc so sánh.

---

## 0. Đo trước khi tối ưu — và kết quả đo đổi hẳn thứ tự ưu tiên

Tôi đo từng chặng trên DB test và NATS test (không chạm hệ thống thật), 40 lượt mỗi chặng:

```
storage.write_bars (dong bo)  n=40  trung vi    8.16 ms | p95  10.79 ms | max  13.49 ms
pub.publish (NATS)            n=40  trung vi    1.35 ms | p95   2.01 ms | max   2.17 ms
persist_bars = DB roi NATS    n=40  trung vi    8.61 ms | p95   9.62 ms | max   9.69 ms
```

**Ghi DB chiếm 85,8% thời gian của `persist_bars`.** Và vì `persist_bars` ghi DB **trước**
rồi mới publish (`collector/main.py:83-85`), engine phải chờ Postgres commit xong mới nhìn
thấy bar.

### 0.1. Nhưng phải đặt con số đó cạnh thang đo thật

| Chặng | Thời gian | So với một khung 5 phút |
|---|---:|---:|
| Ghi DB chặn publish | ~8 ms | 0,003% |
| Publish NATS | ~1,4 ms | 0,0005% |
| **Khung nến 5 phút** | **300.000 ms** | 100% |
| **Cửa xác nhận lệnh thật thủ công** | **900.000 ms** | 300% |

Toàn bộ độ trễ có thể tối ưu được trong code là **~10 ms**, trên một đường mà con người phải
gõ `YES` trong vòng **900 giây** (`real_orders.py:11`, `PENDING_ORDER_TTL_MINUTES = 15`).

**Nói thẳng:** rút 8 ms không đổi được kết quả giao dịch nào của hệ thống này. Nếu mục tiêu
thật là "tín hiệu tới tay nhanh hơn", thì thứ cần bàn là **cửa xác nhận thủ công 15 phút** và
**độ dài khung nến**, cả hai đều là quyết định của chủ dự án chứ không phải việc tối ưu code.

Tôi vẫn giao ba task dưới đây vì chúng đúng và rẻ — nhưng chúng là **dọn dẹp kỹ thuật**, không
phải đòn bẩy hiệu năng. Đừng kỳ vọng thấy khác biệt trên bảng PnL.

### 0.2. Thay đổi độ trễ LỚN NHẤT vừa xảy ra hôm nay, và nó cố ý

`BarLatch` triển khai lúc 16:44 ngày 10/09 làm engine **chỉ nhận bar khi khung đã đóng**,
thay vì nhận ngay snapshot đầu tiên của khung đang hình thành. Xét thuần về thời gian, tín
hiệu giờ đến **muộn hơn tới 5 phút**.

Đó là **đúng, không phải hồi quy**. Trước đây engine phản ứng nhanh trên dữ liệu **sai** —
chạy chiến lược trung bình 7 lần trên cùng một cây nến với giá close tạm thời. Nhanh mà sai
thì không phải là nhanh. **Không được "tối ưu" bằng cách quay lại hành vi cũ.**

---

## 1. Ba việc

| Task | Việc | Thu được |
|---|---|---|
| 1 | Publish NATS **trước**, ghi DB sau | ~8 ms mỗi bar |
| 2 | Đo độ trễ đầu-cuối thật, có số liệu | không đoán nữa |
| 3 | Đánh giá việc chặn event loop — **chỉ đo, không sửa** | dữ liệu cho quyết định sau |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB.
- **Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.** Mọi phép đo trên NATS
  phải dùng `nats-test` (cổng 4223) hoặc lệnh đọc.
- **Không sửa** `BarLatch`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/logic.py`.
- **Không quay lại hành vi publish snapshot chưa đóng** (xem §0.2).
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` copy từ terminal. Mọi số đo copy từ output thật.
- **Phép đo phải là bước CUỐI CÙNG** — đo xong rồi sửa code thì số đo vô giá trị (bài học đợt
  22: báo cáo −12,24 nhưng chạy lại ra −15,58).

---

## Task 1 — Publish NATS trước, ghi DB sau

### 1.1. Hiện trạng

`trading/collector/main.py:82-86`:

```python
    try:
        storage.write_bars(bars)
        for b in bars:
            await pub.publish(b)
        alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])
```

Engine — người tiêu thụ duy nhất quan tâm tới độ trễ — phải chờ Postgres commit (8,16 ms
trung vị, p95 10,79 ms) trước khi bar rời khỏi collector.

### 1.2. Vì sao đảo thứ tự là an toàn

Engine **không đọc DB trong vòng lặp xử lý bar**. Nó chỉ đọc DB một lần lúc warm-up
(`engine/main.py`, `warmed_until`). Bar đến qua NATS mang đủ dữ liệu trong payload
(`bus/publisher.py:43-45` — `asdict(bar)` + `ts` isoformat). Nên publish trước khi ghi DB
**không tạo ra tình huống engine đọc phải dữ liệu chưa có**.

### 1.3. Việc cần làm

Đảo thứ tự trong `persist_bars`: publish trước, `write_bars` sau. Giữ nguyên mọi thứ khác —
vẫn trong `try`, vẫn `alert` CRITICAL khi hỏng, vẫn không bao giờ ném.

**Một điều bắt buộc phải xử lý, đừng bỏ qua:** đảo thứ tự làm đổi ngữ nghĩa lỗi. Trước đây
DB hỏng thì bar **không** ra NATS. Giờ DB hỏng thì bar **đã** ra NATS rồi — engine đã hành
động trên một bar không có trong DB. Thông điệp `CRITICAL` hiện tại ghi *"bar persist/publish
failed, bars dropped"* — chữ **"dropped" sẽ thành sai**. Phải phân biệt hai nhánh hỏng:

- Publish hỏng → bar chưa tới engine. Đây mới là "dropped".
- Publish xong nhưng ghi DB hỏng → engine **đã** thấy bar, DB thiếu. Nội dung cảnh báo phải
  nói đúng điều đó, vì cách xử lý sự cố khác hẳn nhau.

Chỉ sửa `trading/collector/main.py`.

### 1.4. Kiểm chứng

1. Test: `pub.publish` được gọi **trước** `storage.write_bars` (dùng mock ghi lại thứ tự).
2. Test: publish ném lỗi → `alert` CRITICAL, nội dung nói bar **chưa tới** engine.
3. Test: publish thành công nhưng `write_bars` ném lỗi → `alert` CRITICAL, nội dung nói bar
   **đã tới** engine nhưng DB thiếu; và **không** dùng chữ "dropped".
4. Test cũ của `persist_bars` vẫn pass (sửa nếu chúng khẳng định thứ tự cũ — ghi rõ đã sửa
   test nào và vì sao).
5. Suite đầy đủ pass, ruff sạch, cổng cứng VN khớp từng chữ số.

---

## Task 2 — Đo độ trễ đầu-cuối thật

Hiện ta **không biết** một bar mất bao lâu từ lúc SSI gửi tới lúc engine xử lý xong. Mọi con
số ở §0 là đo từng chặng rời rạc trong môi trường test, không phải đường thật.

### 2.1. Việc cần làm

Thêm số đo vào hai chỗ **đã có sẵn `alert`** — không thêm phụ thuộc mới, không thêm thư viện,
không thêm bảng DB:

1. Trong `persist_bars` (`collector/main.py`): thêm vào `alert("INFO", "bars closed", ...)`
   một trường `lag_ms` = khoảng cách từ **thời điểm đóng khung** (`bar.ts + interval`) tới
   lúc publish xong. Đây là "bar đóng xong bao lâu thì engine thấy được".
2. Phía engine: ở chỗ đã xử lý xong một bar, ghi `lag_ms` tương tự (từ `bar.ts + interval`
   tới lúc `process_bar` trả về).

Dùng `datetime.now(TZ)` sẵn có; không đưa thêm đồng hồ mới. Nếu giá trị âm (lệch đồng hồ),
vẫn ghi ra — **không im lặng kẹp về 0**, vì đồng hồ lệch là vấn đề thật cần nhìn thấy.

### 2.2. Kiểm chứng

1. Test: `lag_ms` xuất hiện trong payload alert và có giá trị đúng với đồng hồ tiêm vào.
2. Test: đồng hồ lệch cho giá trị âm → vẫn ghi ra, không bị kẹp.
3. Sau khi triển khai, chạy một phiên rồi trích log: bảng `lag_ms` trung vị / p95 / max cho
   collector và engine. **Phép đo này thuộc đợt sau**, brief này chỉ cần đấu dây và test.
4. Suite pass, ruff sạch.

---

## Task 3 — Chặn event loop: CHỈ ĐO, KHÔNG SỬA

### 3.1. Hiện tượng

`storage.write_bars` là lời gọi **đồng bộ** nằm trong hàm `async`. Trong lúc nó chạy, event
loop của collector **đứng hoàn toàn** — không nhận được message SSI mới, không publish được
gì khác.

Đo được: 8,16 ms mỗi lần ghi. Mà từ đợt 26, **mỗi snapshot đều ghi DB** (`persist_snapshot`),
và mỗi cây nến có trung bình ~7 snapshot:

```
7 x 8.16 ms = 57.15 ms khoa event loop / bar / ma
```

Với 3 mã là khoảng 170 ms mỗi chu kỳ 5 phút. Nhỏ, nhưng nó tăng tuyến tính theo số mã: 30 mã
sẽ là ~1,7 giây mỗi khung.

### 3.2. Vì sao KHÔNG sửa trong đợt này

Cách sửa hiển nhiên là đẩy `write_bars` sang thread (`asyncio.to_thread`). Nhưng kết nối
psycopg **không an toàn khi dùng chung giữa các thread**, và `Storage` hiện chia sẻ kết nối.
Làm ẩu ở đây đổi một vấn đề hiệu năng 57 ms lấy một lỗi hỏng dữ liệu ngẫu nhiên — trên đường
ghi bar của một hệ thống giao dịch.

**Không có gì trong hệ thống này đang chịu thiệt vì 170 ms.** Nên: đo, ghi lại, quyết sau.

### 3.3. Việc cần làm

Viết `scripts/.probe_event_loop_block.py` (dùng quy ước `.probe_*` của `.gitignore:23`), đo
và báo cáo:

1. Thời gian `write_bars` cho 1, 3, 10, 30 bar một lần gọi — ghi DB **theo lô** có rẻ hơn
   ghi lẻ không? Nếu rẻ hơn nhiều thì đó là hướng sửa **an toàn hơn** thread.
2. Với số mã hiện tại (3) và giả định 7 snapshot/bar: tổng thời gian chặn mỗi khung.
3. Ngoại suy cho 10, 30, 100 mã. Nêu rõ đây là **ngoại suy**, không phải đo.
4. Kết luận: ngưỡng số mã nào thì việc chặn này bắt đầu thành vấn đề thật.

**Chỉ đo. Không sửa `Storage`, không sửa `persist_snapshot`, không đụng thread.**

---

## 3. Điều KHÔNG được làm nhân danh "giảm độ trễ"

Ghi rõ ở đây vì đây là loại brief dễ bị hiểu thành "làm mọi thứ cho nhanh":

- **Không** bỏ `BarLatch` hay quay lại publish snapshot chưa đóng. Xem §0.2.
- **Không** bỏ ghi DB cho snapshot — Grafana đang dùng để hiện giá nhúc nhích trong khung.
- **Không** giảm `PENDING_ORDER_TTL_MINUTES` để "lệnh đi nhanh hơn". Rút ngắn cửa xác nhận
  chỉ làm **nhiều lệnh hết hạn hơn** — 9/9 lệnh đã hết hạn ở mức 15 phút rồi.
- **Không** bỏ `await` hay chuyển sang fire-and-forget cho `pub.publish` để "khỏi chờ". Mất
  `await` là mất luôn khả năng biết publish có thành công không.
- **Không** đổi `sub.next_msg(timeout=60)` ở `engine/main.py:365`. Đó là timeout chờ, không
  phải nhịp poll — engine đã hoàn toàn hướng sự kiện, giảm số này không làm nó nhanh hơn một
  micro giây nào.

---

## 4. Báo cáo

Ngắn, đủ, đúng thứ tự. Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

1. `git diff --stat`.
2. Task 1: kết quả năm tiêu chí, pass/fail từng mục. Trích nội dung hai thông điệp CRITICAL
   mới.
3. Task 2: kết quả ba tiêu chí.
4. Task 3: bốn bảng số + kết luận ngưỡng số mã.
5. Ba dòng: số test pass, ruff, cổng cứng VN.
6. `git status --short`.

**Không commit, không push.**

---

## 5. Thứ thật sự quyết định độ trễ — và nó không nằm trong code

Để chủ dự án có số mà quyết:

| Nguồn độ trễ | Độ lớn | Ai đổi được |
|---|---:|---|
| Cửa xác nhận lệnh thật thủ công | **900.000 ms** | chủ dự án (tự động hoá? trực phiên?) |
| Khung nến 5 phút | **300.000 ms** | chủ dự án (đổi `bar_interval_minutes`?) |
| `flush_due` grace cho khung cuối phiên | 60.000 ms | có thể chỉnh, chỉ ảnh hưởng bar 14:45 |
| Ghi DB chặn publish | 8 ms | **Task 1 của brief này** |
| Publish NATS | 1,4 ms | không đáng động |

Ba dòng đầu lớn hơn hai dòng cuối **từ bốn tới sáu bậc độ lớn**. Nếu mục tiêu là giao dịch
nhanh hơn thật sự, cuộc bàn đúng là về ba dòng đầu — và cả ba đều là quyết định về cách vận
hành, không phải về code.
