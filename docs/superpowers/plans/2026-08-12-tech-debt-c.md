# Kế hoạch: dọn nợ kỹ thuật C1–C3

Ngày giao: 2026-08-12. Nhánh: `feature/data-layer`. Base: `d264233`.

## Quy tắc chung (bắt buộc)

- **Không commit, không push.** Claude audit rồi mới commit.
- Chạy `gitnexus_impact({target, direction: "upstream"})` trước khi sửa bất kỳ
  symbol nào; chạy `gitnexus_detect_changes()` khi xong. Báo cáo lại blast radius.
- Giữ nguyên style hiện có. Không "tiện thể" refactor. Không xóa dead code có
  từ trước. Mọi dòng thay đổi phải truy ngược được về đúng task dưới đây.
- File **không được đụng**: `.agentignore`, `.env`, `scripts/.probe_*.py`,
  `scripts/.spike_*.py`, file `.md` tiếng Việt ở gốc repo, mọi thứ trong
  `archive/`.
- Chạy integration test cần Postgres + NATS đang chạy ở local. **Không** chạy
  suite integration khi máy đang phục vụ stack thật.

---

## C2 — `test_publish_roundtrip` để lại rác trong stream BARS

**Làm trước C1.** C2 nhiều khả năng là điều kiện cần của C1.

### Sự thật đã đo được (không cần đo lại)

- `tests/test_publisher.py::test_publish_roundtrip` publish vào stream `BARS`
  và **không dọn**. Sau mỗi lần chạy suite, stream `BARS` còn đúng **26
  message** — số này ổn định qua 3 lần chạy liên tiếp, không tăng dần.
- Hệ quả: isolation của **mọi** engine test phụ thuộc vào đúng một lần purge
  trong fixture `reset_stream_and_durable_consumer` (`tests/test_engine_main.py`)
  thành công. Đó là một điểm gãy đơn.

### Ngõ cụt đã loại trừ — ĐỪNG đi lại

Không thể tách sang stream riêng theo kiểu `test_connect_applies_retention_limits`
làm với `BARSLIMIT`. Lý do: `BarPublisher.publish()` hardcode subject
`f"bars.ssi.{bar.symbol}"` (`trading/bus/publisher.py:45`). Stream mới muốn bắt
được message đó thì phải khai báo subject chồng lấn `bars.>` với stream `BARS`,
và JetStream từ chối overlapping subjects. Đổi `publish()` để subject cấu hình
được là **ngoài phạm vi** — không làm.

### Việc cần làm

Cho `test_publish_roundtrip` tự dọn phần nó tạo ra, sao cho stream `BARS` sau
khi test chạy xong có số message đúng bằng số message trước khi nó chạy.

Ràng buộc:
- Phải dọn **kể cả khi assert fail** (dùng `try/finally` hoặc fixture) — nếu chỉ
  dọn ở cuối hàm thì một test fail sẽ để lại rác và làm hỏng test kế tiếp.
- Không đụng `trading/bus/publisher.py`.
- Không đụng `tests/test_engine_main.py`.

### Kiểm chứng (phải làm đủ cả 3, báo cáo output thật)

1. **Đo trước/sau.** Viết một đoạn đo (có thể là script tạm `scripts/.probe_*.py`,
   nhớ file đó đã gitignored) đọc `js.stream_info("BARS").state.messages`.
   Trình tự: xóa hẳn stream `BARS` → chạy `uv run pytest tests/test_publisher.py -v`
   → đo. **Kỳ vọng: 0 message.**
   → kiểm chứng bằng: dán số đo thật, không phải suy luận từ code.

2. **Chạy 3 lần liên tiếp, số không đổi.** Chạy `tests/test_publisher.py` ba lần
   liên tiếp, đo sau mỗi lần. **Kỳ vọng: 0, 0, 0.**
   → kiểm chứng bằng: dán cả ba số.

3. **Sức phân biệt của phép dọn (BẮT BUỘC — bước này chứng minh test không pass
   một cách rỗng).** Cố ý phá phần dọn (comment nó đi), chạy lại, xác nhận số
   message > 0. Khôi phục, chạy lại, xác nhận về 0.
   → kiểm chứng bằng: dán số đo ở cả hai trạng thái.

4. Toàn bộ suite unit vẫn xanh: `uv run pytest -m "not integration" -v`.
5. `uv run ruff check trading tests`.

---

## C1 — Root cause của flake NATS

### Sự thật đã có (không cần lặp lại)

- Commit `d264233^..d62384d` chỉ làm fixture **tự tố cáo** khi purge không sạch
  (raise `AssertionError` kèm số message còn lại). Nó **không** sửa nguyên nhân.
- Giả thuyết "purge trả OK nhưng message vẫn còn" **đã bị loại trừ**: 0/200 và
  0/300 lần purge tuần tự thất bại.
- Guard trong fixture đã được chứng minh có sức phân biệt (sabotage → `DID NOT
  RAISE AssertionError`).

### Việc cần làm

Sau khi C2 xong, chạy lại toàn bộ suite integration **10 lần liên tiếp** và ghi
nhận có còn flake không.

- **Nếu hết flake:** kết luận nguyên nhân là rác từ `test_publish_roundtrip`,
  dán bằng chứng (10/10 xanh), và **dừng ở đây**. Ghi lại kết luận.
- **Nếu còn flake:** dán **nguyên văn** thông báo lỗi (fixture giờ đã in ra số
  message còn lại). Sau đó điều tra tiếp, nhưng **giới hạn 1 giả thuyết**: nêu
  giả thuyết, thiết kế một phép đo phân biệt được đúng/sai, chạy nó, báo cáo.
  Không sửa code production. Không đoán mò nhiều vòng.

### Quy tắc chống tự lừa (đọc kỹ)

Không kết luận "đã sửa" từ việc **không thấy** flake trong vài lần chạy. Flake
là hiện tượng xác suất. Nếu không đưa ra được cơ chế giải thích *tại sao* nó
hết, hãy nói thẳng "chưa biết nguyên nhân, chỉ quan sát thấy 10/10 xanh" — đó
là một báo cáo **đúng**, không phải một thất bại.

### Kiểm chứng

→ Dán kết quả 10 lần chạy dưới dạng đếm được (vd `10 passed` × 10, hoặc
  `9 passed / 1 failed` kèm nguyên văn lỗi lần fail).

---

## C3 — `::date` không đổi timezone trong `screen_liquidity.py`

### Sự thật đã kiểm chứng (ĐỌC KỸ — phần lớn cảnh báo ban đầu là báo động sai)

- Grafana dashboard **KHÔNG có vấn đề**. Đã đọc cả 7 `rawSql` trong
  `grafana/provisioning/dashboards/trading.json` — không query nào dùng `::date`.
  **Không đụng file này.**
- `trading/storage/db.py:502-512` **đã đúng rồi** — dùng
  `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` kèm comment giải thích lý do.
  Đây là **pattern mẫu** cần noi theo. **Không đụng file này.**
- Chỗ duy nhất còn lại: `scripts/screen_liquidity.py` dòng **35** và **52**.
- **Đây KHÔNG phải lỗi logic.** Session timezone là UTC, bar ngày lưu ở nửa đêm
  giờ VN = 17:00 UTC hôm trước, nên `::date` trả về ngày lùi 1. Nhưng **cả
  `total_max` (dòng 35) lẫn `max_ts` (dòng 52) đều lệch đúng 1 ngày như nhau**,
  mà `is_stale()` chỉ so sánh hai giá trị đó với nhau → kết quả không đổi.
  Đây là lỗi **hiển thị và nhất quán**, không phải lỗi hành vi.

### Việc cần làm

Sửa hai chỗ đó dùng `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`, theo đúng
pattern ở `db.py:512`.

**KHÔNG** viết test khẳng định hành vi lọc thay đổi — nó không thay đổi. Nếu
bạn viết được một test mà nó fail *trước* khi sửa, nghĩa là phân tích trên của
tôi sai: **dừng lại và báo cáo**, đừng tự sửa theo hướng khác.

### Kiểm chứng

1. Đọc lại `db.py:502-512`, xác nhận đã dùng đúng cùng một dạng biểu thức.
   → kiểm chứng bằng: dán hai dòng SQL trước/sau để đối chiếu.
2. Chạy `screen_liquidity.py` với DB thật (chỉ đọc, script có ghi
   `is_active` — **chạy ở chế độ không ghi nếu script có cờ đó; nếu không có
   cờ, ĐỪNG chạy, chỉ báo cáo**) và so ngày in ra trước/sau.
   → kỳ vọng: ngày sau khi sửa **muộn hơn đúng 1 ngày** so với trước.
3. `uv run ruff check scripts/screen_liquidity.py`.

---

## Thứ tự thực hiện

C2 → C1 → C3. C3 độc lập, có thể làm bất cứ lúc nào.

## Báo cáo cuối

Với mỗi mục C1/C2/C3, nêu rõ: đã làm gì, output kiểm chứng **thật** (dán vào),
và mục nào **chưa** đạt tiêu chí. Nếu một tiêu chí không đạt được, nói thẳng —
đừng hạ chuẩn tiêu chí để tuyên bố hoàn thành.
