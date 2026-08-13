# Kế hoạch: trả lại khả năng chạy unit test không cần Docker, + tài liệu & dọn dẹp

Ngày giao: 2026-08-13 tối. Nhánh: `feature/data-layer`. Base: `51eb353`.

**KHÔNG commit, KHÔNG push.**

---

## Việc A (HỒI QUY — quan trọng nhất, làm trước)

### Đo được, không phải suy luận

Docker đang TẮT. Tôi chạy:

```
uv run pytest -m "not integration" -q
-> 62 deselected, 198 errors in 136.67s
```

Cả `tests/test_trailing_stop.py` — thuần in-memory, không đụng DB — cũng chết
với `psycopg.errors.Connection...`.

Trước ISO-1 lệnh này chạy được không cần Docker. Nó là lệnh ghi trong
`README.md:52` **và** trong `CLAUDE.md` mục "Build, lint, test commands". ISO-1
đã làm hỏng nó, và mất 136 giây chỉ để báo lỗi.

### Nguyên nhân

`tests/conftest.py::_isolated_infra` là `@pytest.fixture(scope="session", autouse=True)`.
`autouse` nghĩa là MỌI test đều yêu cầu nó, kể cả test không đụng DB. Nó kết
nối Postgres ngay khi phiên bắt đầu.

Đây là lỗi của thiết kế ISO-1 — của tôi. Không phải lỗi ai thực thi.

### Phải làm

1. `_isolated_infra` **chỉ dựng hạ tầng khi phiên có ít nhất một test
   `integration` được thu thập.** Không có thì trả về ngay, không kết nối gì.
   Gợi ý: dùng `pytest_collection_modifyitems(session, config, items)` để đặt
   một cờ trên `session`/`config`, rồi fixture đọc cờ đó. Nếu bạn thấy cách
   khác gọn hơn, cứ dùng — miễn là **không** nuốt lỗi và **không** dùng
   try/except quanh phần kết nối.

2. `tests/test_collector_main.py::test_collector_stops_cleanly_when_stop_event_set`
   (dòng 157, dùng `TEST_DSN` ở dòng 167-169) là test **có** chạm DB thật
   nhưng **thiếu** marker. Thêm `@pytest.mark.integration` cho riêng test đó —
   **không** đặt `pytestmark` cấp module, vì các test còn lại trong file đó là
   unit thật.

   Tôi đã đối chiếu: 6 file có `pytestmark = pytest.mark.integration`, 7 file
   dùng `TEST_DSN`/`TEST_NATS_URL`. Chênh lệch đúng một chỗ này.

### Kiểm chứng

1. **Docker TẮT** → `uv run pytest -m "not integration" -q` → **pass**, không
   lỗi kết nối nào, và **nhanh** (giây, không phải 136 giây). Dán output +
   thời gian.
2. **Docker BẬT** + `docker compose --profile test up -d nats-test` →
   `uv run pytest -q` → **260 passed**. Số test tổng không đổi.
3. **Sức phân biệt (BẮT BUỘC).** Tắt Docker, khôi phục `autouse=True` không
   điều kiện → `pytest -m "not integration"` phải **lỗi lại**. Khôi phục →
   pass. Dán cả hai.
   Lý do bắt buộc: "fixture không chạy" là một sự vắng mặt, rất dễ pass rỗng.
4. Hàng rào an toàn của ISO-1 vẫn phải chặn: `TEST_DB_DSN` trỏ `trading` →
   Exit; `TEST_NATS_URL` cổng 4222 → Exit. **Đừng làm hỏng nó khi sửa.**

---

## Việc B — tài liệu

`README.md` mục "Local development (without Docker)" (khoảng dòng 49-55) hiện
liệt kê lệnh pytest mà **không** nói suite tích hợp cần hạ tầng riêng.

Thêm cho đúng sự thật sau việc A:
- unit test: `uv run pytest -m "not integration"` — **không cần Docker**
- suite đầy đủ: cần Postgres **và** `docker compose --profile test up -d nats-test`
- nói rõ vì sao có `nats-test`: test chạy trên DB `trading_test` + NATS 4223
  để không bao giờ đụng hệ thống thật (dẫn `docs/superpowers/plans/2026-08-13-test-isolation.md`)

**KHÔNG sửa `DEPLOYMENT.md`.** Đó là hướng dẫn triển khai VPS; không ai chạy
test trên VPS, thêm mục test vào đó là sai chỗ. Chỉ báo cáo nếu bạn thấy nó
nói điều gì SAI sau thay đổi này (ví dụ mục §5 "Start the stack").

**KHÔNG sửa `CLAUDE.md`.** Nó cũng chứa các lệnh test và có thể cần cập nhật,
nhưng đó là tài liệu điều phối của chủ dự án — báo cáo, đừng tự sửa.

---

## Việc C — dọn dẹp

Chỉ một thay đổi: thêm `.agents/` và `.codex/` vào `.gitignore`.

Lý do: chúng là thư mục cấu hình công cụ AI (skills / agents / hooks.json),
cùng loại với `.superpowers/` (dòng 6) và `.1devtool/` (dòng 42) vốn đã được
bỏ qua. Đặt cạnh hai dòng đó, kèm comment ngắn.

### HAI THỨ TUYỆT ĐỐI KHÔNG ĐỘNG VÀO

**1. `tổng hợp lại nội dung để tôi đưa vào xây dựng chiế.md` ở gốc repo.**
Tôi đã mở ra xem trước khi đề xuất bất cứ điều gì: đó là **tài liệu nghiên cứu
của chủ dự án** — bản xuất từ Perplexity, 115 dòng, về chiến lược giao dịch
HĐTL VN30 tại SSI (ký quỹ 17%, quy mô hợp đồng, công thức vốn). Không phải rác.
Không xoá, không di chuyển, không đổi tên, không thêm vào `.gitignore`.

**2. `scripts/spike_*.py` — KHÔNG chuyển vào `scripts/spikes/`.**
`GO_LIVE_AUDIT.md` có đề xuất chuyển, nhưng đề xuất đó đưa ra mà chưa kiểm
tham chiếu. Tôi đã kiểm:

```
trading/collector/ssi_auth.py:44
    "SSI refresh_token missing/expired — run scripts/spike_ssi_sdk_auth.py ..."
```

Đây là **thông báo lỗi trong code sản xuất** — dòng người vận hành đọc lúc xác
thực hỏng. Còn `ssi_auth.py:6,36`, `scripts/_ssi_spike_common.py` (4 chỗ) và 5
tài liệu trong `docs/plans-legacy/` cũng trỏ tới đường dẫn đó. Chuyển thư mục
biến tất cả thành đường dẫn chết. Bỏ hẳn ý này.

---

## Ràng buộc

- Sửa: `tests/conftest.py`, `tests/test_collector_main.py`, `README.md`,
  `.gitignore`.
- **KHÔNG** sửa gì trong `trading/`.
- **KHÔNG** sửa `DEPLOYMENT.md`, `CLAUDE.md`, `GO_LIVE_AUDIT.md`,
  `config/config.yaml`.
- Không đổi nội dung test nào; việc A chỉ thêm marker và đổi điều kiện chạy
  fixture.

## Toàn bộ

`uv run ruff check trading tests` → sạch. Dán output thật, không tóm tắt.

## Nếu thấy kế hoạch sai

Dừng và phản biện. Đặc biệt việc A: nếu bạn tìm được cách khiến unit test độc
lập Docker mà KHÔNG cần dựa vào marker `integration`, cách đó có thể bền hơn —
nói ra trước khi viết.
