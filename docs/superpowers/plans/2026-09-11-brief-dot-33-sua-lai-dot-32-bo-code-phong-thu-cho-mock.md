# Brief đợt 33 — Sửa lại đợt 32: bỏ code phòng thủ sinh ra để chiều mock

Ngày giao: 11/09/2026, 01:45.
Base: cây làm việc hiện tại (đợt 32 **chưa commit** — tôi giữ lại vì lý do dưới đây).
Người giao: Claude (planner/auditor).

**Brief này ngắn. Một việc.** Làm xong thì tôi commit cả đợt 32 lẫn đợt 33 trong một lần.

---

## 0. Lỗi này là của tôi, không phải của agent

Đợt 32 Task 2 tôi viết tiêu chí:

> *"Năm test lá chắn NAV của đợt 30 **vẫn pass nguyên vẹn, không sửa một dòng nào**. Đây là
> tiêu chí quan trọng nhất."*

**Tiêu chí đó sai.** Năm test ấy mock ở tầng `storage.conn().execute().fetchall()` — tức
chúng mock **đúng cái chi tiết triển khai mà Task 2 sinh ra để xoá đi**. Một bài test mock
thẳng vào thứ ta đang refactor bỏ thì **bắt buộc phải đổi**; đòi nó "pass nguyên vẹn" là đòi
một điều bất khả.

Agent làm đúng chữ tôi viết. Và để năm test cũ vẫn xanh mà không sửa chúng, nó phải **bẻ cong
code sản xuất** — đó là hệ quả trực tiếp của tiêu chí sai, không phải agent cẩu thả.

Tiêu chí lẽ ra phải là: *hành vi không đổi — năm test vẫn khẳng định đúng những điều cũ,
nhưng phần dựng mock phải chuyển từ `storage.conn()` sang `storage.read_latest_account_navs`.*

---

## 1. Việc phải sửa

### 1.1. `trading/real_orders.py` — bỏ nhánh gọi hai lần

```python
        nav_map = storage.read_latest_account_navs()
        if not isinstance(nav_map, dict):
            nav_map = Storage.read_latest_account_navs(storage)
```

Hai dòng cuối gọi **chính phương thức vừa gọi**, lần này không qua instance, để nó chạy thân
hàm thật với `self` là một `MagicMock` — nhờ đó chạm được `self.conn()` đã bị mock trong test
cũ. Đây là code tồn tại **chỉ để chiều mock**, không phục vụ tình huống thật nào: `Storage`
thật luôn trả `dict`.

Rút gọn còn đúng một lời gọi trong `try`.

### 1.2. `trading/storage/db.py:836-845` — bỏ phòng thủ cho tình huống không xảy ra

```python
        if not rows or not isinstance(rows, (list, tuple)):
            return {}
        result = {}
        for r in rows:
            if isinstance(r, (list, tuple)) and len(r) >= 2 and r[1] is not None:
                try:
                    result[str(r[0])] = float(r[1])
                except (TypeError, ValueError):
                    pass
        return result
```

`psycopg` `.fetchall()` **luôn** trả list; `isinstance(rows, (list, tuple))` là nhánh chết.
Mỗi hàng luôn có đúng hai cột vì chính câu `SELECT` ở ngay trên quy định thế; `len(r) >= 2`
và `isinstance(r, ...)` cũng là nhánh chết. `nav` là cột số của Postgres.

Đây là điều `CLAUDE.md` nguyên tắc 2 cấm thẳng: *"Không giao cho agent thực thi việc xử lý
lỗi cho các tình huống không thể xảy ra."*

Giữ lại **đúng một** phép kiểm có thật: bỏ qua hàng có `nav` là `NULL` (Postgres cho phép
`NULL`, nên đây là tình huống thật). Viết thành một biểu thức dict gọn, cùng style với các
phương thức đọc khác trong `db.py`.

Bảng rỗng → `.fetchall()` trả `[]` → dict rỗng, **không cần** dòng `if not rows` riêng.

### 1.3. `tests/test_real_orders.py` — chuyển mock lên đúng tầng

Năm test lá chắn NAV: thay khối dựng `storage.conn.return_value.__enter__...` bằng một dòng
đặt thẳng giá trị trả về của phương thức mới, ví dụ:

```python
    storage.read_latest_account_navs.return_value = {
        "0434221": 5_021_712.0,
        "0434226": 197_517_988.0,
    }
```

**Không đổi một dòng `assert` nào.** Chúng vẫn phải khẳng định đúng những điều cũ: có/không
có WARN, nội dung WARN chứa hai số tài khoản và hai NAV, chỉ cảnh báo một lần, không chặn
lệnh. Nếu phải sửa một `assert` để test xanh thì nghĩa là **hành vi đã đổi** — dừng lại và
báo cáo, đừng sửa `assert`.

## 2. Ràng buộc

- **Không đổi hành vi.** Đây vẫn là thay đổi thuần cấu trúc.
- **Không sửa** `NAV_DISCREPANCY_RATIO_THRESHOLD`, nội dung `alert`, hay việc lá chắn chỉ nói
  mà không chặn lệnh.
- **Không đụng** phần Task 1 của đợt 32 (`persist_bars` + `interval`) — phần đó **đúng**, tôi
  đã kiểm cả hai chỗ gọi truyền `latch.interval`.
- Chỉ sửa: `trading/real_orders.py`, `trading/storage/db.py`, `tests/test_real_orders.py`.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` copy từ terminal.

## 3. Kiểm chứng

1. `grep` xác nhận `real_orders.py` **không còn** chữ `isinstance` liên quan tới `nav_map`,
   và không còn gọi `Storage.read_latest_account_navs(storage)`. Dán kết quả.
2. `grep` xác nhận `db.py::read_latest_account_navs` không còn `isinstance`. Dán kết quả.
3. Năm test lá chắn NAV pass, **không `assert` nào bị sửa** — dán `git diff` của
   `tests/test_real_orders.py` để tôi tự đối chiếu từng dòng.
4. Hai test `Storage` của đợt 32 (bản ghi mới nhất, bảng rỗng) vẫn pass.
5. Suite đầy đủ pass (mốc hiện tại **654**), ruff sạch, cổng cứng VN khớp từng chữ số.

## 4. Ghi chú cho các brief sau — bài học tôi tự rút

Khi giao refactor, **không** viết tiêu chí kiểu *"test cũ không được sửa một dòng nào"* nếu
test cũ mock đúng cái đang bị refactor bỏ. Tiêu chí đúng là **"không `assert` nào bị sửa"** —
phần dựng mock được phép đổi, phần khẳng định hành vi thì không.

Ép giữ nguyên mock sẽ đẩy sự méo mó vào code sản xuất, và đó là chỗ đắt nhất để chứa nó.
