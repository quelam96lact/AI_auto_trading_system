# Kế hoạch: khôi phục trailing stop sau restart + test tự dọn pending orders

Ngày giao: 2026-08-13. Nhánh: `feature/data-layer`. Base: `2b6fd06`.
KHÔNG commit, KHÔNG push. Chạy `gitnexus_impact` trước khi sửa symbol,
`gitnexus_detect_changes` khi xong.

Bối cảnh đầy đủ: `GO_LIVE_AUDIT.md` (rủi ro 4 và mục "Dữ liệu hiện tại").

---

# TASK A — Trailing stop bị vô hiệu hoá sau khi engine restart

## Bug (đã truy, không phải suy đoán)

`TrailingStopManager._highest` là dict thuần in-memory (`trading/trailing_stop.py:11`).
Khi engine khởi động lại:

1. `engine/main.py:53,59` khôi phục vị thế từ DB → `broker.position_qty(sym) > 0`
2. `logic.py:48-49` gọi `trailing_stop.check(bar, atr)`
3. `trailing_stop.py:26-28` thấy `_highest` rỗng → **`return None`**
4. → stop-loss của vị thế đó bị vô hiệu hoá **vĩnh viễn**, im lặng, cho tới khi
   vị thế được đóng và mở lại

`on_position_opened()` chỉ được gọi từ `logic.py:38` khi có BUY fill MỚI, nên
vị thế khôi phục từ DB không bao giờ được đăng ký lại.

## Cách sửa đã chọn — và vì sao

Tái dựng `_highest` lúc khởi động từ dữ liệu đã có trong DB:

- Thời điểm vào lệnh: `SELECT max(ts) FROM orders WHERE symbol = %s AND side = 'BUY'`
  (bảng `orders` có `ts`, `symbol`, `side` — xem `schema.sql:62-72`)
- Đỉnh giá kể từ đó: `SELECT max(high) FROM bars WHERE symbol = %s AND ts >= %s`

**Phương án đã cân nhắc và LOẠI:**

- *Đặt `_highest = avg_price`*: đơn giản hơn nhưng **under-protect**. Nếu giá đã
  chạy lên rồi mới restart, stop tính từ giá vào lệnh sẽ thấp hơn stop đúng →
  giữ vị thế lâu hơn mức chiến lược cho phép. Sai lệch theo hướng nguy hiểm.
- *Ghi `_highest` xuống DB mỗi bar*: chính xác nhất nhưng thêm một lượt ghi DB
  vào hot path cho một giá trị tái dựng được. Không đáng.

## Việc cần làm

1. **`trading/storage/db.py`**: thêm một method đọc, đặt cạnh các method đọc
   hiện có, theo đúng style sẵn có (docstring tiếng Việt giải thích *tại sao*,
   không chỉ *cái gì*). Trả về đỉnh giá kể từ lần BUY gần nhất, hoặc `None` nếu
   không đủ dữ liệu.

2. **`trading/engine/main.py`**: sau khi khôi phục `positions` (dòng 53) và tạo
   `trailing_stop` (dòng 70), với mỗi vị thế có `qty > 0`, nạp lại `_highest`.

3. **Không im lặng khi thất bại.** Nếu không tái dựng được (không có BUY fill,
   hoặc không có bar nào từ đó tới nay), **phải `alert("WARN", ...)`** nêu rõ
   symbol và việc vị thế đó đang không có trailing stop. Im lặng chính là bản
   chất của bug này — đừng tái tạo nó dưới dạng khác.

4. **Không dùng đường tắt qua `_highest`.** `TrailingStopManager` đã có
   `on_position_opened(symbol, fill_price)` — dùng nó, đừng chọc thẳng vào
   `_highest` từ `main.py`. Nếu API hiện có không đủ diễn đạt, hãy **báo cáo**
   thay vì tự thêm method mới.

## Kiểm chứng (dán output THẬT)

1. **Test tái hiện bug TRƯỚC khi sửa.** Viết test: seed một vị thế mở + BUY fill
   + vài bar có giá cao hơn, chạy `run()`, xác nhận trailing stop **có** hoạt
   động. Test này phải **FAIL trên code hiện tại**.
   → Dán output FAILED trước khi sửa. Đây là bằng chứng test có ý nghĩa.
   → Nếu nó PASS ngay từ đầu: **DỪNG LẠI và báo cáo** — nghĩa là tôi phân tích
     sai và cần xem lại trước khi đụng code.
2. Sau khi sửa, test đó PASS. → Dán output.
3. Test cho nhánh cảnh báo: vị thế mở nhưng không có BUY fill → có `alert("WARN")`.
4. `uv run pytest -q` (kỳ vọng ≥ 242 passed) + `uv run ruff check trading tests`.

---

# TASK B — Test ghi vào `pending_real_orders` mà không dọn

## Sự thật đã đo

```
SELECT status, symbol, count(*) FROM pending_real_orders GROUP BY 1,2;
 expired | ENGT | 208
```

Toàn bộ 208 dòng là symbol `ENGT` — rác từ integration test, tích luỹ từ
2026-07-26 tới 2026-08-12. Đúng cùng loại vấn đề với 26 message NATS đã sửa
hôm qua: **test ghi vào bảng thật và không dọn**.

Fixture `storage` ở `tests/test_engine_main.py:50-59` đã dọn `positions`,
`orders`, `engine_state`, `real_risk_state` — nhưng **quên `pending_real_orders`**.

## Việc cần làm

1. Bổ sung dọn `pending_real_orders` cho symbol `ENGT` vào fixture đó.
2. **Dọn cả ở teardown, không chỉ setup.** Bài học từ `9d829f0`: dọn-chỉ-trước
   nghĩa là rác vẫn nằm lại sau khi suite chạy xong, và isolation phụ thuộc vào
   đúng một lần dọn ở lần chạy kế tiếp.
3. **Kiểm tra các file test KHÁC** có ghi vào `pending_real_orders` bằng
   `Storage` thật không (gợi ý: `tests/test_confirm_real_order.py`). Nếu có, xử
   lý tương tự. Nếu chúng dùng mock thì không cần đụng — **báo cáo bạn đã kiểm
   tra file nào và kết luận gì**.
4. **Không** tự tay `DELETE` 208 dòng cũ trong DB dev. Việc đó tôi làm, sau khi
   audit xong — đừng đụng dữ liệu ngoài phạm vi test.

## Kiểm chứng (dán output THẬT)

1. Đếm trước: `SELECT count(*) FROM pending_real_orders WHERE symbol = 'ENGT'`.
2. Chạy `uv run pytest -q` (full suite), đếm lại.
   → **Kỳ vọng: con số KHÔNG tăng.**
3. Chạy full suite thêm 2 lần nữa, đếm sau mỗi lần.
   → **Kỳ vọng: giữ nguyên, không tăng.**
4. **Sức phân biệt (BẮT BUỘC).** Bỏ phần dọn đi, chạy **full suite**, xác nhận
   số dòng **tăng lên**. Khôi phục, xác nhận không tăng nữa.
   → Nhắc lại bài học: phép đo phải chạy trên đúng phạm vi mà kết luận nói tới.
     Kết luận là "sau full suite không còn rác" → phải đo sau full suite.
5. `uv run pytest -q` + `uv run ruff check trading tests`.

---

## Không được làm

- Không commit, không push.
- Không chạy collector.
- Không `DELETE` dữ liệu DB ngoài phạm vi test.
- Không sửa `config/config.yaml` (đặc biệt `real_order_capital` — đó là quyết
  định về tiền của chủ dự án).
- Không đụng `GO_LIVE_AUDIT.md`.
- Không dọn rác markdown ở thư mục gốc — tôi đang làm song song, sẽ đụng nhau.
