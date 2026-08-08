# Spec: Sửa 48 lỗi ruff có sẵn (phát hiện bởi CI mới thêm)

**Ngày viết:** 2026-08-08
**Phạm vi:** Xử lý 48 lỗi `ruff check trading tests` đã phát hiện sau khi
CI được thêm (xem
`docs/superpowers/specs/2026-08-08-ci-cd-and-ruff-fix-design.md`). Chốt
phạm vi qua buổi brainstorming với user ngày 2026-08-08, sau khi đọc thật
từng nhóm lỗi trong code (không đoán).

## Vì sao

CI mới thêm chạy `ruff check trading tests` với rule set mặc định của
ruff, phát hiện 48 lỗi có sẵn trong code cũ (không phải do CI/ruff task
gây ra — task đó cố tình không sửa, chỉ báo cáo). Để CI xanh mà không
rewrite các pattern cố ý của hệ thống live, cần phân loại rõ: lỗi nào là
bug/style thật nên sửa, lỗi nào là pattern cố ý nên suppress bằng config.

## Đã xác nhận bằng cách đọc code thật (không đoán)

- **BLE001 (8 lỗi, `except Exception` trần)** — `trading/collector/backfill.py:283`,
  `feed.py:80,160`, `main.py:33,85,89`, `tests/test_engine_main.py:60,64` —
  6 lỗi trong code production đều **cố ý**: `backfill.py`/`main.py` catch
  rồi `alert(...)` + tiếp tục (không crash collector vì 1 lỗi lạ, đúng
  nguyên tắc resilience đã áp dụng nhiều lần trong dự án — ví dụ fix DoS
  `ZeroDivisionError` ở ATR filter); `feed.py` catch để trigger reconnect.
  2 lỗi còn lại ở `test_engine_main.py:60,64` là code dọn dẹp NATS
  JetStream giữa các test (xem S110 ngay dưới — cùng 2 dòng, 2 rule cùng
  fire). Riêng `trading/collector/ssi_auth.py:61` cũng có `except
  Exception:` nhưng catch để cleanup (`await auth.close()`) rồi `raise`
  lại — ruff KHÔNG flag dòng này (không phải blind-swallow), không nằm
  trong 8 lỗi BLE001, chỉ nêu thêm làm ví dụ cho cùng nguyên tắc resilience
  của dự án.
- **S110 (2 lỗi, `try`/`except`/`pass` không log)** — cả 2 ở
  `tests/test_engine_main.py:60,64` (cùng 2 dòng vừa nêu ở BLE001), code
  dọn dẹp NATS JetStream giữa các test (`delete_consumer`/`purge_stream`
  có thể lỗi nếu chưa tồn tại) — vô hại, không ảnh hưởng gì tới hệ thống
  live.
- **DTZ007/DTZ001 (9 lỗi, naive datetime)** — `trading/collector/backfill.py:68,72,163,165`,
  `parser.py:29`, + test tương ứng — pattern nhất quán toàn dự án: SSI trả
  về chuỗi giờ VN không kèm timezone, code parse bằng `strptime()` (naive)
  rồi `.replace(tzinfo=TZ)` ngay dòng sau — đây là cách làm ĐÚNG cho dữ
  liệu không có tz trong chuỗi gốc, không phải bug.
- **B023 (1 lỗi, `feed.py:78`)** — closure `lambda e: dead.set()` bên trong
  vòng `while` tái gán biến `dead` mỗi vòng lặp. Đọc kỹ control flow: an
  toàn về hành vi (vòng lặp chờ đồng bộ `while not (dead.is_set() or
  self._stop.is_set())` trước khi sang vòng kế, nên lambda luôn được gọi
  đúng object `dead` của vòng hiện tại) — nhưng vẫn đáng sửa vì rẻ, không
  rủi ro, và làm rõ ý định (closure liền kề `_closed` trong cùng file đã
  dùng đúng pattern default-arg `dead=dead` để tránh đúng vấn đề này).
- **Còn lại (29 lỗi: SIM117 ×9, I001 ×7, UP035 ×3, F401 ×3, UP041 ×1, SIM103
  ×1, SIM102 ×1, RUF012 ×1, F841 ×1, C408 ×1, B023 ×1)** — thuần style/dọn
  code, không đổi hành vi khi sửa đúng theo gợi ý của ruff. `RUF012` (1 lỗi,
  `tests/test_feed.py:57`, `FakeStreaming.instances = []`) chỉ cần thêm
  annotation `typing.ClassVar[list]` — biến này là spy/tracker dùng chung
  giữa các instance trong test, giữ nguyên hành vi, chỉ khai báo rõ ý định.

## Quyết định

1. **Sửa 29 lỗi "an toàn"** (SIM117 ×9, I001 ×7, UP035 ×3, F401 ×3, UP041
   ×1, SIM103 ×1, SIM102 ×1, RUF012 ×1, F841 ×1, C408 ×1, B023 ×1) bằng
   `ruff check --fix` cho các lỗi có đánh dấu `[*]` tự động sửa được, phần
   còn lại (SIM102/103/117, B023, RUF012, F841) sửa thủ công theo đúng gợi
   ý của ruff, KHÔNG đổi hành vi.
2. **Suppress 19 lỗi "cố ý"** (BLE001 ×8, S110 ×2, DTZ007 ×8, DTZ001 ×1)
   bằng `[tool.ruff.lint] ignore = [...]` trong `pyproject.toml`, **kèm
   comment giải thích lý do từng rule bị ignore** (không ignore âm thầm) —
   KHÔNG rewrite exception-handling hay datetime-parsing logic trong
   `trading/collector/*`.
3. **Sau khi sửa xong, `ruff check trading tests` phải trả về exit code 0**
   (CI workflow đã thêm trước đó sẽ chuyển xanh).
4. **Không đổi hành vi runtime nào** — toàn bộ 133 test hiện có phải tiếp
   tục pass nguyên vẹn sau mỗi bước sửa.

## Thiết kế

### `pyproject.toml` — thêm section `[tool.ruff.lint]`

```toml
[tool.ruff.lint]
# BLE001/S110: except Exception trần là pattern CỐ Ý cho resilience của hệ
# thống trading live (collector/feed không được crash vì 1 lỗi lạ) - xem
# docs/superpowers/specs/2026-08-08-fix-preexisting-ruff-findings-design.md.
# DTZ007/DTZ001: parse chuỗi giờ VN không có tz (SSI trả về vậy) bằng
# strptime() (naive) rồi .replace(tzinfo=TZ) ngay sau - cách làm đúng cho
# dữ liệu không có tz trong chuỗi gốc, không phải bug.
ignore = ["BLE001", "S110", "DTZ007", "DTZ001"]
```

### Sửa 34 lỗi style — theo từng nhóm file (không gộp file không liên quan)

- `uv run ruff check --fix trading tests` trước để tự động sửa mọi lỗi có
  đánh dấu `[*]` (I001, UP035, UP041, F401 — trừ trường hợp unused import
  cần xoá thủ công nếu `--fix` không tự tin xử lý biến đang dùng gần đó).
- Chạy lại `uv run ruff check trading tests` xem còn lại gì (dự kiến:
  SIM102, SIM103, SIM117, C408, B023, F841 — các rule không tự sửa được
  hoặc cần review) — sửa thủ công từng lỗi theo đúng gợi ý hiển thị của
  ruff (ruff luôn in kèm code gợi ý sửa trong message `help:`).
- Sau mỗi nhóm sửa (tự động, rồi thủ công), chạy lại
  `uv run pytest -m "not integration" -v` để xác nhận không đổi hành vi.

## Testing / kiểm chứng

- `uv run ruff check trading tests` → exit code 0, không output lỗi nào.
- `uv run pytest -m "not integration" -v` → toàn bộ pass, số lượng test
  không đổi (133, trừ khi 1 số test thay đổi tên biến do sửa F841 — không
  được xoá/đổi ý nghĩa test nào).
- `git diff` review thủ công: mỗi file bị sửa chỉ có thay đổi khớp đúng 1
  trong 2 nhóm ở trên (style fix hoặc `pyproject.toml`'s `ignore` list) —
  không có thay đổi logic nào lọt vào.

## Ngoài phạm vi (nói rõ)

- Rewrite `except Exception` thành exception type cụ thể hơn ở
  `trading/collector/*` — cố ý giữ nguyên, xem lý do ở mục "Đã xác nhận".
- Rewrite datetime parsing để tự nhét `%z` vào `strptime()` — chuỗi gốc từ
  SSI không có tz, không thể làm vậy mà không đổi logic.
- Thêm log cho 2 chỗ `except`/`pass` trong test cleanup (S110) — vô hại,
  không đáng công sửa cho code dọn dẹp test.
- Bất kỳ thay đổi hành vi runtime nào — task này chỉ sửa style/suppress
  config, không sửa bug, không thêm tính năng.
