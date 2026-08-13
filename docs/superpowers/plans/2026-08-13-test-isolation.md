# Kế hoạch: tách test ra DB và NATS riêng

Ngày giao: 2026-08-13 chiều. Nhánh: `feature/data-layer`. Base: `e20e647`.

**KHÔNG commit, KHÔNG push.** `gitnexus_impact` trước khi sửa symbol,
`gitnexus_detect_changes` khi xong.

Chủ dự án đã duyệt việc này ngày 2026-08-13.

---

## Vì sao làm — sự cố thật, không phải giả định

Sáng 13/08, suite test chạy trên đúng DB và đúng NATS mà hệ thống thật đang
phục vụ. Hậu quả đo được:

- `engine_state` id=1 của engine THẬT bị ghi đè bằng dữ liệu test
  (`cash = 99.999.990` — đúng giá trị `write_engine_state(100_000_000 - 10.0, 0.0)`
  trong fixture)
- durable consumer `engine` trên NATS **bị xoá** — engine thật mất đường nhận
  bar mà heartbeat vẫn tươi, nhìn ngoài tưởng khoẻ
- stream `BARS` bị purge

Và cùng nguyên nhân đó sinh ra flake đã theo đuổi từ 2026-08-10: engine
subscribe `bars.>`, nên **bất kỳ** nguồn nào publish vào `BARS` trong lúc test
chạy đều ăn budget `max_messages` → crossover ở bar 21 không tới → `KeyError: 'ENGT'`.

Số đo: hai suite chạy song song = **10 phút 46 giây + fail**; một suite chạy
một mình = **14,6 giây + 260 passed**. Chênh 44 lần.

**Kết luận: vá teardown KHÔNG sửa được gì** — chỉ làm flake hiếm đi và khó chẩn
đoán hơn. Phải tách hạ tầng.

---

## Thiết kế đã chốt — và vì sao không chọn cách khác

### 1. NATS: server RIÊNG (cổng 4223), KHÔNG phải stream riêng

Tôi đã cân nhắc dùng stream riêng (`BARS_TEST`) và loại bỏ: JetStream **từ chối
hai stream có subject chồng nhau**. Stream test cũng cần `bars.>` vì
`trading/engine/main.py:141` hardcode `sub = await js.subscribe("bars.>", ...)`.
Muốn đổi subject thì phải sửa cả engine lẫn publisher — tức là **sửa code sản
xuất để phục vụ test**, đúng thứ cần tránh.

Server riêng giải quyết trọn vẹn mà **không đụng một dòng code sản xuất nào**.

Thêm service `nats-test` vào `docker-compose.yml`:
- bind `127.0.0.1:4223:4222`
- jetstream bật, **volume riêng** (không dùng chung `natsdata`)
- `profiles: ["test"]` — để `docker compose up -d` thường **không** khởi động nó.
  Chạy test thì `docker compose --profile test up -d nats-test`.

### 2. Postgres: DATABASE riêng `trading_test`, cùng instance

Không cần container thứ hai. `trading/storage/schema.sql` tự chạy
`CREATE EXTENSION IF NOT EXISTS timescaledb`, nên một database trống là đủ —
chỉ cần `CREATE DATABASE` trước rồi gọi `init_schema()`.

### 3. `tests/conftest.py` — hiện chưa tồn tại, tạo mới

Chứa:
- `TEST_DSN` = env `TEST_DB_DSN`, mặc định
  `postgresql://trading:trading@127.0.0.1:5432/trading_test`
- `TEST_NATS_URL` = env `TEST_NATS_URL`, mặc định `nats://127.0.0.1:4223`
- fixture session-scoped `autouse=True`: tạo database `trading_test` nếu chưa
  có (kết nối vào database `postgres`, autocommit, `CREATE DATABASE`), rồi
  `Storage(TEST_DSN).init_schema()`.

### 4. HÀNG RÀO AN TOÀN — phần quan trọng nhất của kế hoạch này

Trong cùng fixture session-scoped, **từ chối chạy** nếu cấu hình trỏ vào hạ
tầng sản xuất:

- `TEST_DSN` mà tên database **không** kết thúc bằng `_test` → `pytest.exit()`
  với thông điệp nói rõ: "test đang trỏ vào DB sản xuất, dừng lại".
- `TEST_NATS_URL` mà cổng là `4222` → `pytest.exit()` tương tự.

Đây không phải trang trí. Đây là thứ biến sự cố sáng nay từ "có thể xảy ra lại"
thành "không thể xảy ra". Ai đó set `TEST_DB_DSN` trỏ nhầm vào `trading` sẽ bị
chặn ngay ở dòng đầu tiên thay vì phát hiện ra sau khi đã ghi đè state thật.

Dùng `pytest.exit()` (dừng cả phiên) chứ **không** `pytest.skip()` — skip im
lặng là đúng thứ đã che giấu vấn đề này bấy lâu.

### 5. Sửa các file test đang hardcode

Thay hằng số bằng import từ `conftest`. Danh sách đầy đủ đã rà:

| File | Dòng | Hiện tại |
|---|---|---|
| `tests/test_engine_main.py` | 20, 40, 115, 149 | DSN + `nats://127.0.0.1:4222` |
| `tests/test_storage.py` | 10 | DSN |
| `tests/test_dashboard_queries.py` | 11 | DSN |
| `tests/test_backtest_cli.py` | 14 | DSN |
| `tests/test_collector_main.py` | 166 | DSN hardcode, **không** đọc env |
| `tests/test_publisher.py` | 15, 20, 49, 60 | `nats://127.0.0.1:4222` |

`tests/test_config.py:12` và `tests/test_confirm_real_order.py:15` dùng DSN giả
(`postgresql://t:t@localhost:5432/trading`) chỉ để `load_config` không nổ —
**KHÔNG kết nối thật, KHÔNG đụng vào.**

---

## Ràng buộc

- Sửa: `docker-compose.yml`, `tests/conftest.py` (mới), 6 file test ở bảng trên.
- **KHÔNG** sửa bất kỳ file nào trong `trading/`. Nếu bạn thấy mình cần sửa code
  sản xuất để test tách được, **dừng lại và báo cáo** — nghĩa là thiết kế của
  tôi sai.
- **KHÔNG** sửa `config/config.yaml`.
- Giữ nguyên nội dung từng test; đây là thay đổi hạ tầng, không đổi hành vi test.
- `stream="BARS"` trong test **giữ nguyên tên** — nó nằm trên server khác nên
  không xung đột. Đừng đổi tên stream, đổi là thêm nhiễu vô ích.

---

## Kiểm chứng — dán output THẬT

1. `docker compose --profile test up -d nats-test` → container chạy, cổng 4223.
   → kiểm chứng bằng: `docker compose ps`

2. `uv run pytest -q` → **260 passed**, không giảm test nào.

3. **BÀI KIỂM TRA QUYẾT ĐỊNH — tái hiện đúng sự cố sáng nay:**
   - Ghi lại `SELECT * FROM engine_state` trên DB **sản xuất** (`trading`)
   - Chạy `uv run pytest -q` trong lúc **collector và engine thật đang chạy**
   - Sau khi xong, đọc lại `engine_state` trên DB sản xuất → **phải giống hệt**
   - Và `consumer info BARS engine` trên NATS 4222 → **phải còn sống**
   Dán cả trước lẫn sau. Đây là bằng chứng duy nhất đáng kể của cả kế hoạch.

4. **Sức phân biệt của hàng rào (BẮT BUỘC).** Đặt
   `TEST_DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading` rồi chạy
   pytest → **phải dừng ngay** với thông điệp về DB sản xuất, không được chạy
   một test nào. Dán output.
   Làm tương tự với `TEST_NATS_URL=nats://127.0.0.1:4222`.

5. `uv run ruff check trading tests` → sạch.

---

## Ghi chú vận hành cho người sau

Sau thay đổi này, `README.md`/`DEPLOYMENT.md` có thể cần một dòng nói rằng chạy
test cần `--profile test`. **Đừng tự sửa hai file đó** — báo cáo lại, tôi sẽ
quyết định viết gì.

---

## Nếu thấy kế hoạch sai

Dừng và phản biện trước khi viết code. Đặc biệt mục 1: nếu bạn tìm được cách
tách stream mà **không** phải sửa code sản xuất, cách đó tốt hơn cách của tôi —
nói ra.
