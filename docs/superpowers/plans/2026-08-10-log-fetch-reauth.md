# Plan 2026-08-10 — Log dòng khi `_fetch_with_reauth` re-auth thành công

## Cảnh báo blast radius (bắt buộc đọc trước khi sửa)

`gitnexus_impact(_fetch_with_reauth, upstream)` báo **risk CRITICAL**: 8 symbol
phụ thuộc, 5 execution flow đi qua (`backfill_universe.py::run`,
`backfill_history.py::main/_run`, hai script spike). Mức CRITICAL này đến từ
**số lượng nơi gọi tới**, không phải từ bản chất thay đổi — thay đổi ở đây chỉ
là thêm một dòng log bên trong nhánh `except` đã tồn tại sẵn, không đổi luồng
điều khiển, không đổi tham số vào/ra. Vẫn phải tôn trọng nguyên tắc CLAUDE.md:
báo lại cho tôi (đã báo trong plan này) và **tuyệt đối không nới rộng phạm vi
sửa** ra ngoài đúng nhánh `except` đó.

## Bối cảnh

`trading/collector/backfill.py::SSIRestClient._fetch_with_reauth` (dòng
223-241) bắt `AuthenticationError`, gọi `_reset_auth()` rồi thử lại — nhưng
không log gì khi việc đó thành công. Lần kiểm chứng job 900 mã ngày
2026-08-10 (xem `RUNBOOK_OTP_AUTH.txt`, mục Bước 5) phải suy luận đường này có
chạy hay không bằng cách suy diễn gián tiếp từ cặp log
`Access token set manually` + `Token refreshed successfully` do
`ensure_authenticated()` phát ra — một chuỗi suy luận 5 bước, dựng lại mỗi lần
cần xác nhận. Một dòng log tại đúng chỗ xảy ra sẽ làm việc đó hiển nhiên.

## Việc cần làm

Trong `_fetch_with_reauth` (`trading/collector/backfill.py:223-241`), thêm
**đúng một dòng log** ngay sau khi retry thành công trong nhánh
`except AuthenticationError`, trước dòng `return rows, data`. Dùng logger đã có
sẵn trong module này — kiểm tra đầu file có `import logging` /
`logger = logging.getLogger(...)` chưa; nếu chưa có thì thêm theo đúng cách các
module khác trong `trading/collector/` đang làm (xem `feed.py` hoặc
`account_sync.py` để giữ cùng quy ước), đừng bịa cách mới.

Nội dung log: mức `INFO` (không phải WARNING — đây là phục hồi bình thường,
không phải sự cố), nêu rõ đây là re-auth-và-retry thành công, và nêu tên
`method` đang gọi (biến `method` đã có sẵn trong hàm). Ví dụ ý tưởng, không bắt
buộc đúng chữ:

```python
logger.info("re-authenticated after AuthenticationError, retrying %s", method)
```

Đặt đúng vị trí: sau `data = await self._ensure_data()`, có thể trước hoặc sau
dòng `rows = await getattr(...)` thứ hai — miễn là chỉ log khi retry đã thực sự
diễn ra (tức bên trong nhánh `except`, không phải nhánh `try` bình thường).

## KHÔNG được làm

- Không đổi bất kỳ dòng nào khác trong `_fetch_with_reauth`, `_reset_auth`,
  `_ensure_data`, `_paged_daily`, `_paged_intraday`.
- Không đổi số lần retry (vẫn đúng một lần, theo đúng docstring hiện tại).
- Không thêm log ở nhánh `try` bình thường (khi không có lỗi) — sẽ làm log ồn
  vô ích trên mọi lượt gọi thành công.
- Không đổi cấp log của dòng `except Exception: pass` khi đóng auth cũ trong
  `_reset_auth` — đó là hành vi cố ý ("lỗi đóng auth cũ không được nuốt mất lỗi
  gốc 401"), không thuộc phạm vi việc này.
- Không sửa file nào khác ngoài `trading/collector/backfill.py`.
- Không ruff --fix trên toàn file. Không commit, không push.

## Kiểm chứng — cả 3 bước, paste output thật

1. **`gitnexus_impact` trước khi sửa** — đã chạy ở trên, đã ghi vào plan này.
   Không cần chạy lại trừ khi bạn đổi target khác `_fetch_with_reauth`.

2. **Unit test hiện có vẫn xanh** — đây là hàm có test riêng
   (`tests/test_backfill.py` hoặc tương đương, tìm bằng
   `grep -rn "_fetch_with_reauth\|fetch_with_reauth" tests/`):
   ```
   uv run pytest tests/ -k "reauth or backfill" -v
   ```
   Paste output đầy đủ, không chỉ dòng cuối.

3. **Test mới xác nhận dòng log thật sự xuất hiện đúng lúc.** Viết một test
   nhỏ: giả lập `market_data.<method>` raise `AuthenticationError` ở lần gọi
   đầu rồi trả kết quả ở lần gọi thứ hai (theo đúng kiểu mock các test
   `_fetch_with_reauth` hiện có đang dùng — đọc chúng trước khi viết, đừng dựng
   lại từ đầu), dùng `caplog` để bắt log `INFO`, assert log đó xuất hiện và
   chứa đúng `method`. Đồng thời assert KHÔNG có dòng log đó khi gọi thành công
   ngay lần đầu (không có lỗi).
   → paste test PASS.

4. `uv run pytest -q` toàn bộ suite — vẫn 240+ passed (số chính xác tùy số test
   mới bạn thêm), không có test nào khác đỏ.

5. `uv run ruff check trading tests` — All checks passed.

6. `gitnexus_detect_changes()` sau khi sửa — paste risk level và
   affected_processes. Nếu risk KHÔNG PHẢI "low" thì dừng lại, báo cáo, đừng tự
   quyết là ổn.

## Phạm vi phẫu thuật

**Được sửa:** `trading/collector/backfill.py` (chỉ đúng nhánh `except` trong
`_fetch_with_reauth`, cộng import logging nếu module chưa có).
**Được tạo/sửa:** file test tương ứng để thêm test log (tìm file test đang
cover `_fetch_with_reauth`, sửa đúng file đó — không tạo file test mới trừ khi
không tìm thấy file nào cover hàm này, trường hợp đó báo lại trước khi tạo).

**CẤM đụng:** mọi file khác trong `trading/`, `scripts/**`, `RUNBOOK_OTP_AUTH.txt`.

**CẤM:** commit, push, ruff --fix.

## Dừng lại và hỏi nếu

- Không tìm thấy quy ước logging nào trong `trading/collector/` để theo.
- Không tìm thấy file test nào cover `_fetch_with_reauth` sẵn có.
- `gitnexus_detect_changes` sau khi sửa báo risk khác "low".
