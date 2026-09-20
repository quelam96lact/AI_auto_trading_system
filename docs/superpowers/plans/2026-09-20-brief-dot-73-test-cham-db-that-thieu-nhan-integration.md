# Brief đợt 73 — Test chạm DB thật mà thiếu nhãn `integration`, chặn mọi lần push

Ngày giao: 20/09/2026 (Chủ nhật).
Base: main hiện tại (`b8d98ed`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

> **Thứ tự: làm đợt 73 TRƯỚC đợt 72.** Brief 72 (gộp công cụ đo rò rỉ) vẫn còn nguyên giá trị,
> nhưng lỗi trong brief này **chặn mọi lần push**, kể cả push sửa tài liệu — nên phải gỡ trước.

---

## 0. Sự việc, đo được chứ không suy đoán

Sáng nay Docker Desktop tự tắt qua đêm. Hệ quả **không** chỉ là stack chết — mà là **không ai push
được gì cả**:

```
pre-push: TEST DO -> huy push.
```

Chạy lại suite mặc định với DB không truy cập được:

```
FAILED tests/test_compare_timeframe_mismatch.py::test_3_deterministic_reproducibility_on_real_db
FAILED tests/test_compare_timeframe_mismatch.py::test_4_direct_db_counts_match_comparison_counts
2 failed, 713 passed, 114 deselected in 284.13s (0:04:44)
```

Hai điều cùng lúc:

1. Hai test này gọi thẳng `psycopg.connect(resolve_dsn(None))`
   (`tests/test_compare_timeframe_mismatch.py:76` và `:98`) nhưng file **không có**
   `pytestmark = pytest.mark.integration`. Nên chúng lọt vào suite `-m "not integration"` — đúng
   suite mà pre-push hook chạy.
2. Suite phình từ **~20 giây lên 284 giây** vì ngồi chờ timeout kết nối.

Nghĩa là: **hễ Docker chết là toàn bộ việc push đóng băng.** Ngay trước phiên giao dịch thì đó là
lúc tệ nhất để mất khả năng sửa và triển khai.

## 0.1. Cạm bẫy phải tránh — đừng gắn nhãn hàng loạt

Tôi đã grep `psycopg\.connect|resolve_dsn\(|Storage\(` trên `tests/`: **17 file khớp mẫu, 11 file
thiếu nhãn**. Nhưng khi DB chết thì **chỉ 2 file đỏ**. Tức 9 file còn lại chạm các ký hiệu đó
nhưng **không thật sự mở kết nối** (dùng mock, monkeypatch, hoặc nằm ở nhánh không được gọi).

**Gắn nhãn `integration` cho cả 11 file là làm hỏng, không phải sửa** — nó đẩy những test đơn vị
đang chạy tốt ra khỏi suite mặc định, làm mất độ phủ mà không ai nhận ra. Phải phân biệt bằng
**thực nghiệm**, không bằng mẫu văn bản.

---

## 1. Ràng buộc

- **Không sửa `pre-push` hook** để nó bỏ qua test. Chuông không được tắt tiếng — đó là nguyên tắc
  FEE-ALARM-2 của dự án.
- **Không đổi logic nghiệp vụ** của bất kỳ test nào; chỉ gắn/không gắn nhãn.
- **Không tắt Docker** để thử nghiệm (phiên giao dịch sáng mai — xem mục 2.1 để biết cách thử an
  toàn).
- Không commit, không push.

---

## Task 1 — Phân biệt bằng thực nghiệm, không bằng grep

### 1.1. Cách thử an toàn, KHÔNG được tắt Docker

Trỏ DSN vào một cổng không có ai nghe, kèm timeout ngắn, rồi chạy suite mặc định. **Tôi đã tự chạy
lệnh này trước khi giao** (PowerShell):

```powershell
$env:TEST_DB_DSN='postgresql://trading:trading@127.0.0.1:59999/trading_test'
$env:PGCONNECT_TIMEOUT='2'
uv run pytest -m "not integration" -q
Remove-Item Env:\TEST_DB_DSN, Env:\PGCONNECT_TIMEOUT
```

Cổng `59999` không có dịch vụ nào. Cách này mô phỏng đúng tình huống "DB không với tới được" mà
**không đụng tới Docker đang chạy**.

**Cạm bẫy tôi đã vấp, ghi lại để bạn khỏi mất thời gian:** đừng nhét `?connect_timeout=2` vào
chuỗi DSN. `tests/conftest.py:28` cắt DSN theo `/` rồi kiểm đuôi `_test`; chuỗi truy vấn làm đuôi
thành `trading_test?connect_timeout=2` nên hàng rào **từ chối chạy cả phiên**. Phải dùng biến môi
trường `PGCONNECT_TIMEOUT` của libpq như trên. **Đừng lách hàng rào đó** — nó đang làm đúng việc
của nó.

### 1.2. Kết quả cần có

Danh sách **chính xác** những test đỏ khi DB không với tới được. Đó — và chỉ đó — là tập cần gắn
nhãn.

Kết quả tôi đo được khi chạy lệnh trên:

```
FAILED tests/test_compare_timeframe_mismatch.py::test_3_deterministic_reproducibility_on_real_db
FAILED tests/test_compare_timeframe_mismatch.py::test_4_direct_db_counts_match_comparison_counts
2 failed, 713 passed, 114 deselected in 28.45s
```

**Đúng 2 test, cùng một file** — trong khi grep khớp tới 11 file. Đó là bằng chứng cho mục 0.1:
9 file kia chạm các ký hiệu DB nhưng không thật sự mở kết nối.

Việc của bạn là **xác nhận lại**, không phải tin tôi. Nếu con số bạn đo khác, **báo cáo đúng cái
bạn đo được** — tôi chỉ chạy một lần, có thể sót.

---

## Task 2 — Gắn nhãn đúng tập đó, và chỉ tập đó

Với mỗi test/file được xác định ở Task 1:

1. Thêm `pytestmark = pytest.mark.integration` ở cấp module **nếu cả file đều cần DB**, hoặc
   `@pytest.mark.integration` trên từng test **nếu chỉ vài test cần** — chọn cái hẹp hơn, đừng
   quét cả file khi chỉ hai hàm có lỗi.
2. Với `tests/test_compare_timeframe_mismatch.py`: tên hai test đã ghi rõ `..._on_real_db` và
   `..._direct_db_counts...`. Chúng **vốn là test integration bị dán nhầm nhãn** — gắn nhãn là
   *sửa nhãn sai*, không phải giảm độ phủ. Nói rõ điều này trong báo cáo.
3. **Kiểm tra file đó còn test nào KHÔNG cần DB không.** Nếu có, đừng gắn ở cấp module — sẽ đẩy
   nhầm chúng ra khỏi suite mặc định.

---

## Task 3 — Kiểm chứng

1. **Suite mặc định phải xanh khi DB không với tới được** — chạy lại đúng lệnh ở 1.1, phải ra
   `0 failed`, và **thời gian phải về lại mức ~20 giây** (không còn ngồi chờ timeout). Dán cả số
   test lẫn thời gian.
2. **Suite mặc định với DB bình thường vẫn xanh**, và **tổng số test không giảm** ngoài đúng số
   test vừa chuyển sang `integration`. Báo rõ: trước `715 passed / 114 deselected`, sau là bao
   nhiêu — hai con số phải cộng lại không đổi.
3. **Suite đầy đủ vẫn chạy được các test vừa gắn nhãn**:
   ```bash
   docker compose --profile test up -d nats-test
   uv run pytest -q
   ```
   Xác nhận các test vừa gắn nhãn **có chạy và xanh** ở đây — tức chúng chỉ đổi chỗ, không biến
   mất.

---

## Task 4 — Nêu ý kiến về chống tái phát (chỉ nêu, KHÔNG làm trong đợt này)

Ba Task trên sửa **triệu chứng**: hai test đang thiếu nhãn sẽ được gắn nhãn. Nhưng **không có gì
ngăn test tiếp theo** được viết ra mà quên nhãn — và lỗi y hệt sẽ quay lại, cũng vào đúng một lúc
tệ như sáng nay (Docker chết + cần push gấp).

Trong báo cáo, nêu ý kiến ngắn: nên chặn tái phát bằng cách nào? Vài hướng để bạn cân nhắc, không
phải để làm ngay:

- một test canh: trong suite mặc định, bọc `psycopg.connect` để nó **ném lỗi**, rồi khẳng định cả
  suite vẫn xanh — tức chứng minh không test không-integration nào mở kết nối thật;
- hoặc một `conftest` hook đếm số lần kết nối thật trong suite mặc định và báo đỏ nếu > 0;
- hoặc chấp nhận rủi ro và chỉ ghi vào tài liệu.

**Không triển khai hướng nào trong đợt 73.** Lý do: sáng mai có phiên giao dịch và là phép đo
quyết định; thêm một cơ chế mới vào đường chạy test ngay lúc này là thêm biến số không cần thiết.
Tôi sẽ quyết sau phiên, dựa trên ý kiến của bạn.

---

## 4. Không làm

- Không sửa pre-push hook, không thêm `--continue-on-error`, không `-p no:cacheprovider` để né.
- Không gắn nhãn cho file chỉ khớp grep mà không thật sự đỏ (mục 0.1).
- Không đổi nội dung kiểm thử của bất kỳ test nào.
- Không tắt/khởi động lại Docker.
- Không commit, không push.

## 5. Báo cáo cho Claude

1. Danh sách test đỏ khi DB không với tới được (Task 1.2), kèm đối chiếu 11 file khớp grep.
2. `git diff tests/` — chỉ có dòng nhãn, không có dòng logic.
3. Ba kết quả kiểm chứng ở Task 3, kèm **thời gian chạy** của mục 1.
4. Với mỗi file gắn nhãn cấp module: xác nhận file đó **không** còn test nào không cần DB.
5. Ý kiến về chống tái phát (Task 4) — nêu, không làm.
