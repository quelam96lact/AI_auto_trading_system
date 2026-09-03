# Brief vòng bổ sung — test cho **nối dây** NAV (không phải cho công thức)

Giao 18:10 ngày 03/09, sau audit gói A + B. Việc nhỏ, làm xong tối nay, rồi
Claude commit và dựng lại container.

**Gói A và gói B đều đúng. Không sửa lại code đã viết.** Việc duy nhất ở đây là
bịt một lỗ hổng kiểm chứng mà audit tìm ra.

---

## 0. Lỗ hổng — tôi tự phá và chứng minh được

Tôi phá code theo đúng hai lỗi gốc mà gói A vừa sửa. **Cả hai đều lọt qua toàn
bộ 391 test.**

**Phá 1 — trả lại lỗi lớp nợ** (`account_sync.py`):

```python
storage.compute_nav(withdrawable, 0.0, {...}, ...)   # thay total_debt bang 0.0
```
⇒ `391 passed`. Đây **đúng là con bug** làm NAV = 0 suốt phiên hôm nay.

**Phá 2 — trả lại lỗi lớp tuổi giá** (`account_sync.py`):

```python
price_fn, ts,          # bo price_age_ok=price_age_ok -> ve dem ngay LICH
```
⇒ `391 passed`. Đây **đúng là con bug** loại 5 mã khỏi định giá.

### Vì sao lọt

- `tests/test_account_sync.py:205` **stub thẳng `_sync_nav`**
  (`lambda *a, **k: _noop()`) — hợp lệ cho test đó (nó kiểm SYNC-1), nhưng
  không có test nào khác chạm `_sync_nav`.
- `tests/test_nav_vn_market_time.py` gọi `Storage.compute_nav` **trực tiếp**,
  truyền nợ và vị từ vào như tham số.

Nên bộ test đang khoá **công thức**, còn bug thì nằm ở **nối dây**. Cụ thể:
`test_debt_that_thay_vi_0_margin_account_ra_nav_dung` **cũng sẽ xanh trên code
cũ chưa sửa** — vì `compute_nav` cũ vốn đã nhận tham số nợ đúng; chỗ sai là
người gọi truyền `0.0`.

Chú thích ở `test_account_sync.py:203` nói *"2 hàm mới có test riêng"* — với
`_sync_nav` thì **không đúng**.

**Đây chính là hình dạng sai lầm dự án đã trả giá nhiều lần:** kiểm cái dễ kiểm
(hàm thuần) thay vì cái đã hỏng (đường nối). Nửa chuông báo của gói A **có**
kiểm chứng phá hoại và tôi đã tự xác nhận nó bắt lỗi thật; nửa NAV thì không có
gì cả.

---

## 1. Việc — hai test khoá đường nối `_sync_nav`

Thêm vào `tests/` (file nào tuỳ bạn chọn, gợi ý `test_nav_vn_market_time.py`).
Test phải gọi **`account_sync._sync_nav`**, không gọi `Storage.compute_nav`.

| # | Test | Phải đỏ khi | Phải xanh khi |
|---|---|---|---|
| 1 | `_sync_nav` truyền **nợ thật** | đổi `total_debt` → `0.0` | code hiện tại |
| 2 | `_sync_nav` truyền **vị từ tuổi giá** | bỏ `price_age_ok=...` | code hiện tại |

Gợi ý cách dựng (không bắt buộc theo): `Storage` giả có
`read_account_balance_with_debt` trả `withdrawable=0, total_debt=68_607_848`,
`read_real_positions` trả một mã, `read_latest_bar` trả giá ngày 28/08; bắt
`record_nav` để đọc `nav` và `unpriced` thay vì ghi DB. Không chạm DB thật,
không đánh dấu `integration`.

Với test 2, mốc thời gian phải là **28/08 → 03/09**: 6 ngày lịch (lỗi cũ ⇒ loại,
`unpriced` không rỗng) nhưng 1 ngày giao dịch (đúng ⇒ `unpriced` rỗng). Chọn mốc
khác sẽ không phân biệt được hai hành vi.

---

## 2. Kiểm chứng phá hoại — bắt buộc, đúng hai phép phá ở mục 0

Không tự nghĩ phép phá khác. Dùng **đúng** hai phép trên, vì đó là hai con bug
thật đã xảy ra:

1. Phá 1 (`total_debt` → `0.0`) ⇒ test 1 **đỏ**. Dán nguyên văn output đỏ.
2. Phá 2 (bỏ `price_age_ok`) ⇒ test 2 **đỏ**. Dán nguyên văn output đỏ.
3. Khôi phục. `grep -rn "SABOTAGE" trading scripts` phải ra rỗng.

---

## 3. Sửa một chú thích sai

`tests/test_account_sync.py:203` nói *"2 hàm mới có test riêng"*. Sau vòng này
câu đó mới đúng. **Chỉ sửa chú thích cho khớp thực tế** — không đụng phần stub
(nó hợp lệ), không đụng logic test cũ.

---

## 4. Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Hai test nối dây | `uv run pytest tests/test_nav_vn_market_time.py -v` |
| 2 | Phá hoại ×2 | output đỏ nguyên văn, đúng hai phép ở mục 2 |
| 3 | Không hồi quy | `uv run pytest -m "not integration" -q` ≥ 393 passed |
| 4 | Lint | `uv run ruff check trading tests scripts` sạch |
| 5 | Phạm vi | `git diff --stat -- trading scripts` **không đổi so với trước vòng này** |

**Tiêu chí 5 quan trọng:** vòng này **chỉ thêm test** và sửa một dòng chú thích.
Nếu bạn thấy cần sửa code sản phẩm để test được, **dừng và báo cáo** — đó là dấu
hiệu thiết kế cần bàn, không phải việc tự quyết.

---

## 5. Ba điều audit đã xác nhận — không cần làm lại

1. **NAV đúng ngoài thực địa.** Tôi tự chạy `_sync_nav` qua đường sản phẩm trên
   DB thật (chặn `record_nav`, không ghi): `0434226 = 131.580.152`,
   `unpriced = RỖNG`; `0434221 = 5.021.459` không đổi. Khớp từng đồng.
2. **Chuông báo bắt lỗi thật.** Tôi tự phá `market_minutes_between` cho trả phút
   đồng hồ ⇒ 2 test đỏ. Nửa này của gói A **đã** được khoá đúng.
3. **Gói B bất biến.** Tôi chạy `measure_strategy --limit 3` (mẫu khác mẫu
   `--limit 1` của bạn) trên `git stash` trước/sau ⇒ **diff rỗng**, exit 0.

---

## 6. Hai điều ghi nhận, KHÔNG sửa trong vòng này

**(a) Cửa sổ mù 15 phút đầu phiên sáng — hệ quả có chủ ý, cần chủ dự án biết.**
Tôi đo trực tiếp: feed chết thật từ trước ngày lễ, lúc **09:10** `bar_stale`
trả `False` (không kêu); tới **09:16** mới `True`. Hôm nay chuông kêu lúc
09:00:09 cho một cái chết thật — với code mới nó sẽ kêu lúc 09:16, **chậm hơn
16 phút**.

Đây là **đánh đổi đúng**, không phải lỗi: code cũ kêu ở 09:00 **mọi buổi sáng**
bất kể feed sống hay chết (bar mới nhất luôn là của hôm trước), tức nó báo giả
mỗi ngày — chỉ là log chỉ có 01/09 và 03/09 nên chưa ai thấy quy luật. Gói A
đóng luôn cả hai cửa báo giả (09:00 và 13:00), nhiều hơn plan yêu cầu. Nhưng cái
giá là 15 phút mù lúc mở cửa, và điều đó phải được **ghi rõ** chứ không nằm im.

**(b) `read_account_balance` giờ không còn ai gọi.** Đã grep: `account_sync`
chuyển sang `read_account_balance_with_debt`, còn engine đọc `read_nav` chứ
không đọc số dư (`engine/main.py:129`). Nên lý do *"hàm cũ vẫn nguyên cho
engine"* trong báo cáo là **không đúng** — nó nguyên vẹn vì không ai dùng nữa.

**Giữ nguyên, không xoá** — đúng quy tắc "báo cáo, không tự dọn dead code". Ghi
vào sổ để B2 xử lý cùng đợt gộp `_print_safe`.
