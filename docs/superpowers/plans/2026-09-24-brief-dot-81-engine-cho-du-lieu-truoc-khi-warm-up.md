# Brief đợt 81 — Vá gốc: engine chờ đủ dữ liệu rồi mới warm-up

Ngày giao: 24/09/2026.
Base: main `411af9b`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh và giả định tôi đang dựa vào

Tối 23/09 engine khởi động lúc 22:10:38 và warm-up xong **trước khi** collector nạp xong backfill
lúc 22:16 — nên cửa sổ chỉ báo dừng ở 22/09 14:45 trong khi DB sắp có đủ nến 23/09. Đợt 80 đã chữa
triệu chứng bằng tay (restart engine). Đợt này vá gốc.

Tôi đã nêu ba hướng ở brief 79 và **đề xuất hướng (1)**; chủ dự án bảo viết tiếp nên tôi hiểu là
chọn hướng (1). **Nếu hiểu sai, dừng lại và báo — đừng làm tiếp.**

**Hai điều tôi đã tự kiểm chứng trước khi giao, không phải giả định:**

1. Vòng warm-up hiện tại (`trading/engine/main.py:166-185`) gọi
   `storage.read_last_bars(sym, strategy.warmup_bars)` rồi lấy `hist[-1].ts` — **không hề kiểm dữ
   liệu có mới hay không**. Đây chính là chỗ cần chèn.
2. Engine đăng ký NATS bằng consumer **durable** (`main.py:334-338`:
   `durable="engine"`, `DeliverPolicy.ALL`). Nên **hoãn warm-up vài phút KHÔNG làm mất nến live** —
   JetStream phát lại, và `main.py:426` đã xử lý bar quá khứ/trùng warm-up. **Nếu không có tính chất
   này thì cả hướng (1) sẽ sai**; bạn hãy tự xác nhận lại trước khi code.

---

## 1. Ràng buộc

- Được sửa: `trading/engine/main.py`, `tests/test_engine_main.py`, và (nếu cần hàm thuần mới)
  `tests/test_engine_gap1.py`.
- **Không** sửa `trading/collector/`, **không** sửa `trading/storage/db.py`, **không** đụng
  `count_warmup_gap()` và khối GAP-1 hiện có.
- **Không** thêm cơ chế bắt tay giữa hai service (không NATS signal mới, không bảng cờ trong DB).
  Engine tự kiểm DB là đủ — đó là lý do hướng (1) rẻ.
- Không thêm dependency.
- Không commit, không push.
- Nền hiện tại: **750 passed**, ruff sạch.

### ĐÍNH CHÍNH 24/09 07:45 — ràng buộc bổ sung, đọc trước khi làm bất cứ gì

Brief này chạy **trong lúc phiên 24/09 đang diễn ra**. Đợt 80 đã cho phép bạn `docker compose
restart engine`; **đợt này KHÔNG.** Cụ thể, cấm tuyệt đối trong suốt đợt 81:

- **Không** `docker compose restart / stop / up / build` bất kỳ service nào — kể cả `engine`, kể cả
  để "xem vòng chờ chạy thật". Engine đang giữ vị thế IJC 400 / AAA 400 và đang xử lý nến live;
  restart giữa phiên sẽ tạo đúng cái lỗ warm-up mà brief này được viết ra để vá.
- **Không** chạy bất cứ gì ghi vào DB thật (`trading`). Test dùng `trading_test` + NATS 4223 như
  `CLAUDE.md` mô tả — đó là môi trường duy nhất được phép.
- Toàn bộ kiểm chứng của đợt này là **test**, không phải quan sát hệ thống đang chạy. Nếu bạn thấy
  cần quan sát thật mới chứng minh được, **báo lại** — đừng tự làm.

Việc triển khai (build image + restart) là của Claude/chủ dự án, làm **sau 15:00 khi phiên đã đóng**.
Nghĩa là code bạn sửa hôm nay **không** ảnh hưởng phiên đang chạy — và đó là điều tốt, không phải
thiếu sót.
- Chạy `gitnexus_impact` trên `run()` trước khi sửa. MCP GitNexus phiên trước **không kết nối
  được**; nếu vẫn vậy, ghi rõ đã thử và không dùng được — **không im lặng bỏ qua**.

---

## Task 1 — Hàm thuần: phiên hoàn tất gần nhất cần có dữ liệu tới ngày nào

Viết hàm thuần (không I/O) trong `trading/engine/main.py`, cạnh `count_warmup_gap()`:

```python
def last_session_date_needed(now: datetime, holidays: frozenset) -> date:
    """Ngày của phiên giao dịch gần nhất mà DB PHẢI có nến, tính tại thời điểm now."""
```

Quy tắc — dùng lại `is_trading_day()` từ `trading/calendar_vn.py`, **không tự viết lại lịch**:
- Nếu hôm nay là ngày giao dịch **và** `now >= 15:00 VN` → trả về hôm nay.
- Ngược lại → lùi về ngày giao dịch gần nhất trước đó.

**Vì sao 15:00 chứ không phải 14:45:** nến cuối phiên có `ts = 14:45` nhưng chỉ đóng lúc 14:50, và
collector cần thêm chút thời gian để ghi. 15:00 là 14:45 + một nến + biên.

**Cấm dùng lại `STREAM_COVERAGE_READY_TIME` (15:25) của `check_golive_gate.py`** — con số đó tồn tại
vì job `stream-health` chạy 15:10, **lý do hoàn toàn khác**. Hai hằng số trùng mục đích mới nên gộp;
hai hằng số trùng giá trị mà khác lý do thì gộp là sai. Khai báo riêng, chú thích rõ lý do.

**Kiểm chứng (test thuần, tính tay):**
1. Thứ Tư 23/09 lúc 22:00 → trả về **23/09**.
2. Thứ Tư 23/09 lúc 14:50 → trả về **22/09** (chưa qua 15:00).
3. Thứ Hai 28/09 lúc 08:30 → trả về **25/09** (thứ Sáu — nhảy qua cuối tuần).
4. Thứ Bảy 26/09 lúc 10:00 → trả về **25/09**.
5. Một ca có ngày lễ trong `holidays` → nhảy qua đúng ngày lễ đó.

---

## Task 2 — Chèn vòng chờ trước warm-up

Trong `run()`, **trước** vòng warm-up ở `main.py:166`, thêm bước: chờ cho tới khi **mọi mã** trong
`cfg.symbols` đều có nến của ngày `last_session_date_needed(...)` trong bảng `bars`.

**So sánh ở mức NGÀY, không ở mức nến.** Lý do: 23/09 IJC chỉ có 44 nến trong khi HPG/AAA có 46 —
thiếu nến lẻ giữa phiên là bình thường (không có giao dịch), còn lỗi ta đang vá là **thiếu trọn một
phiên**. So ở mức nến sẽ đẻ ra báo động giả; so ở mức ngày bắt đúng lỗi thật.

Hành vi:
- Vòng lặp: kiểm tra → nếu đủ, thoát ngay (trường hợp thường gặp, **không được làm chậm khởi động
  bình thường**); nếu thiếu, ngủ rồi thử lại.
- Hết thời gian chờ mà vẫn thiếu → **CRITICAL** (không phải WARN), nêu rõ mã nào thiếu và ngày nào,
  rồi **vẫn chạy tiếp** warm-up. Engine không bao giờ được treo vĩnh viễn vì chờ dữ liệu — nhưng
  cũng tuyệt đối không được đi tiếp trong im lặng. (FEE-ALARM-2.)
- Chờ thành công sau ít nhất một vòng → **INFO** nêu đã chờ bao lâu.

**Tham số hoá để test được — đây là ngoại lệ có lý do, không phải thêm cấu hình thừa:** `run()` nhận
thêm `warmup_wait_timeout_sec: float = 600` và `warmup_wait_sleep=asyncio.sleep`. Không có hai tham
số này thì hoặc test phải ngủ thật (chậm), hoặc phải test hàm rời khỏi `run()` (sân khấu — đúng lỗi
đợt 75 đã mắc). Mặc định 600s ≈ gấp đôi 6 phút backfill thực đo tối 23/09.

**Cảnh báo về hồi quy:** các test sẵn có trong `tests/test_engine_main.py` đều gọi `run()`. Nếu
fixture của chúng không có nến của ngày "phiên gần nhất", vòng chờ mới sẽ kích hoạt và làm suite
chậm hoặc đỏ. Xử lý bằng cách truyền `warmup_wait_timeout_sec=0` trong các test cũ **không liên
quan** — và nói rõ trong báo cáo bạn đã sửa những test nào, vì sao. Không được đổi kỳ vọng của test
cũ để cho qua.

**Kiểm chứng:**
1. **Ca vá đúng lỗi thật (bắt buộc):** dựng DB test có nến tới 22/09 14:45, đặt `now` = 23/09 22:10,
   và một `sleep` giả mà **lần gọi đầu tiên sẽ chèn thêm nến 23/09 vào DB** (mô phỏng backfill xong
   muộn). Kỳ vọng: warm-up kết thúc với `warmed_until` = **23/09 14:45**, không phải 22/09 14:45.
   Đây là test tái hiện đúng sự cố 23/09 — thiếu nó thì đợt này vô nghĩa.
2. Ca thường: DB đã đủ dữ liệu → **không gọi `sleep` lần nào** (assert số lần gọi = 0), khởi động
   không chậm đi.
3. Ca hết giờ: DB không bao giờ đủ, `warmup_wait_timeout_sec` nhỏ → có đúng một alert **CRITICAL**
   nêu tên mã thiếu, và warm-up **vẫn chạy**.
4. **Kiểm thử phá hoại:** vô hiệu hóa vòng chờ (`if False:`), chạy lại suite, xác nhận **đúng test
   số 1 và số 3** đỏ (dán số lượng). Khôi phục, xác nhận sạch. Nếu vô hiệu hóa mà không test nào đỏ
   → test là sân khấu, viết lại.

---

## Task 3 — Xác nhận GAP-1 không bị ảnh hưởng

Vòng chờ mới và GAP-1 giải quyết hai thời điểm khác nhau (trước warm-up / lúc nến live đầu tiên).
Chúng phải cùng tồn tại, không cái nào che cái nào.

1. Chạy riêng toàn bộ test GAP-1 (`tests/test_engine_gap1.py` và hai test GAP-1 trong
   `tests/test_engine_main.py`) — phải **xanh nguyên**, không sửa một dòng nào trong đó.
2. Nói rõ trong báo cáo: sau đợt này, ca nào sẽ do vòng chờ bắt, ca nào vẫn do GAP-1 bắt.

---

## 2. Không làm

- Không sửa collector, không sửa `db.py`, không đụng `count_warmup_gap()` hay khối GAP-1.
- Không thêm bắt tay giữa hai service.
- Không đổi kỳ vọng của test cũ để cho qua.
- Không tự nới `warmup_bars` hay đụng chiến lược.
- Không commit, không push.

## 3. Báo cáo cho Claude

1. Xác nhận (hoặc bác bỏ) tính chất durable consumer ở `main.py:334-338`.
2. Task 1: 5 test thuần, nguyên văn kết quả.
3. Task 2: dòng test **đỏ trước khi sửa** cho ca số 1, rồi xanh sau khi sửa, rồi kết quả kiểm thử
   phá hoại (số test đỏ). Danh sách test cũ bạn đã truyền `warmup_wait_timeout_sec=0` và lý do.
4. Task 3: kết quả test GAP-1 và phân định ca nào thuộc cơ chế nào.
5. `uv run pytest -m "not integration" -q` (nền **750**), suite đầy đủ, và
   `uv run ruff check trading tests scripts`.
6. Bất kỳ điều gì khác thường — nói thẳng, kể cả ngoài phạm vi.

---

## 4. Ngoài phạm vi, đã biết, chưa giao

- **`nav = 0` trong khung 22h VN** (đợt 80): nguyên nhân gốc ở `account_balance_snapshot`, không
  phải `compute_nav`. Chưa vá vì chưa biết SSI thực sự trả về gì trong khung đó. Cổng go-live đã
  chặn `nav <= 0` nên không còn nguy hiểm trước mắt.
- **Docker Desktop tự khởi động lại**: chủ dự án đã chọn bỏ qua. Không đưa vào brief.
