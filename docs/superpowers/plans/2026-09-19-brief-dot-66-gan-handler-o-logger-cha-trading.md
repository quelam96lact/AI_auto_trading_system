# Brief đợt 66 — Chuyển handler log bền vững lên logger cha `trading`, đóng nốt lỗ đợt 58

Ngày giao: 19/09/2026 (thứ Bảy).
Base: main hiện tại (`3c2d63f`, đã gồm đợt 65).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Đây là sửa lỗi lập kế hoạch của tôi, không phải lỗi của agent

Đợt 58 mục C kết luận: bản vá log bền cho engine **phải gắn ở logger cha `"trading"`**, và nói
thẳng *"sửa một lần cho cả logger lẫn container, đừng vá riêng lẻ"*. Nhưng brief đợt 63 và đợt 65
của tôi lại chỉ định `"trading.alerts"` — tôi chép theo khuôn collector của đợt 52 mà không đối
chiếu lại kết luận đợt 58. Agent làm đúng brief; brief sai.

Hậu quả, tôi đo được bằng thực nghiệm khi audit đợt 65:

| Đường log | Logger | Vào file bền vững? |
|---|---|---|
| `alert()` | `trading.alerts` | **Có** |
| Telegram gửi trượt (`telegram.py:29/47/50`) | `trading.telegram` | **Không** |
| Cảnh báo engine (`real_orders.py`, …) | `trading.engine.*` | **Không** |

`trading.telegram` là **anh em** của `trading.alerts`, không phải con — handler gắn ở
`trading.alerts` không bao giờ nhận được bản ghi của nó. Hai đường sau vẫn rơi ra `stderr`, tức
vẫn bốc hơi khi dựng lại container. Nghĩa là: đợt 65 có cải thiện thật (engine có bằng chứng bền
cho `alert()`), nhưng **lỗ đợt 58 vẫn chưa đóng** — ta vẫn không có bằng chứng bền về việc tin
Telegram gửi được hay trượt.

---

## 1. Vì sao không chỉ đổi một chữ

Đổi `"trading.alerts"` → `"trading"` là một chữ, nhưng hệ quả thì không nhỏ: logger `"trading"`
nhận bản ghi của **mọi** module `trading.*`, mà handler đang đặt `setLevel(logging.INFO)`.
Collector sinh rất nhiều INFO. Gắn thẳng lên `"trading"` ở mức INFO sẽ làm
`logs/bars_closed.log` phình nhanh, xoay vòng liên tục, và **cắt cụt chính cửa sổ bằng chứng**
mà phép đo sáng thứ Hai 22/09 dựa vào. Đó là lý do tôi không tự sửa lúc audit đợt 65.

**Thiết kế đóng băng — không tự diễn giải thêm:** gắn handler ở logger `"trading"`, kèm một
filter cho qua:

- **mọi** bản ghi từ logger `trading.alerts` (giữ nguyên hành vi hiện tại, bằng chứng chốt nến
  không đổi một dòng nào);
- bản ghi mức **WARNING trở lên** từ mọi logger `trading.*` khác.

Cách này đóng lỗ cho **cả hai** container bằng **một** thay đổi (đúng tinh thần đợt 58), và giữ
lượng ghi thêm ở mức tối thiểu vì WARNING là sự kiện hiếm.

---

## 2. Ràng buộc

Không đổi tên file của collector (`bars_closed.log`) và của engine (`engine_alerts.log`). Không
đổi `maxBytes`/`backupCount`/formatter. Không sửa `trading/telegram.py`, `trading/alerts.py`.
Không bật `real_trading_enabled`. **Không deploy, không build, không restart container.** Không
commit, không push.

---

## Task 1 — Kiểm tra tiền đề trước khi sửa

Trước khi đụng code, xác nhận và báo cáo:

1. Không module nào đặt `propagate = False` trên cây `trading.*` (nếu có, bản ghi sẽ không lên tới
   logger cha và cả thiết kế này hỏng):
   ```powershell
   Select-String -Path trading\*.py, trading\**\*.py -Pattern "propagate"
   ```
2. **Không có** thông điệp log mức WARNING/ERROR nào chứa chuỗi `"bars closed"` — vì
   `stream_health_check.count_stream_bars_closed` đếm đúng chuỗi đó, một dòng WARNING lọt vào có
   chứa cụm này sẽ **làm sai phép đo thứ Hai**:
   ```powershell
   Select-String -Path trading\*.py, trading\**\*.py, scripts\*.py -Pattern "bars closed"
   ```
   Báo cáo từng chỗ tìm được và mức log của nó. Nếu phát hiện một chỗ WARNING+ có chứa cụm này,
   **DỪNG LẠI, báo cáo, đừng sửa gì** — thiết kế phải đổi.

---

## Task 2 — Sửa `trading/logging_setup.py`

### 2.1. Filter

Thêm một filter (class nhỏ hoặc hàm, tuỳ style hiện có của file):

- `record.name` bắt đầu bằng `"trading.alerts"` → cho qua, bất kể mức.
- ngược lại → chỉ cho qua khi `record.levelno >= logging.WARNING`.

### 2.2. Gắn ở logger cha

- Đổi `logging.getLogger("trading.alerts")` thành `logging.getLogger("trading")`.
- Guard chống gắn trùng phải kiểm trên **đúng logger đang gắn** (`"trading"`), không phải logger cũ.
- Gắn filter ở 2.1 vào handler.
- **Giữ nguyên** `handler.setLevel(logging.INFO)` — việc lọc mức do filter lo, để INFO ở handler
  thì bản ghi INFO của `trading.alerts` mới đi qua được.

### 2.3. Không làm trong task này

- **Không đổi cách đánh khoá của guard** (vẫn theo `HANDLER_NAME`). Cạm bẫy "gọi lần hai với
  `filename` khác trong cùng tiến trình thì file thứ hai không được tạo" đã biết, đã ghi nhận ở
  đợt 65, và **không hề xảy ra ở production** (mỗi container là một tiến trình, gọi đúng một lần).
  Giữ nguyên, đừng tiện tay sửa.
- Không đổi `DEFAULT_LOG_DIR`, `DEFAULT_LOG_FILE`, `MAX_BYTES`, `BACKUP_COUNT`, `HANDLER_NAME`.

---

## Task 3 — Test chứng minh đóng được lỗ

Thêm vào `tests/test_logging_setup.py` (giữ nguyên 4 test đã có):

1. **Test ba đường log** — đây là test cốt lõi của cả brief. Gắn handler vào `tmp_path`, rồi lần
   lượt phát:
   - `logging.getLogger("trading.alerts").critical(...)` → **phải** có trong file;
   - `logging.getLogger("trading.telegram").warning(...)` → **phải** có trong file (đây chính là
     đường Telegram gửi trượt, trước đợt 66 bị mất);
   - `logging.getLogger("trading.engine.real_orders").warning(...)` → **phải** có trong file.
2. **Test lọc ồn**: `logging.getLogger("trading.collector.main").info(...)` → **không** được có
   trong file (chứng minh filter chặn INFO của module không phải `alerts`, giữ file khỏi phình).
3. **Test bằng chứng cũ không đổi**: `alert("CRITICAL", ...)` vẫn ghi đúng như trước (4 test cũ
   phải vẫn xanh, không sửa chúng).

**Chứng minh test phân biệt được:** tạm gắn lại handler ở `"trading.alerts"` như cũ, chạy test ở
mục 1 → phải **ĐỎ** đúng ở dòng `trading.telegram`. Khôi phục, chạy lại → **XANH**. Dán nguyên văn
cả hai lần.

---

## Task 4 — Cập nhật chú thích đã trở thành sai

`trading/logging_setup.py` hiện có docstring/chú thích nói handler gắn vào logger
`"trading.alerts"`. Sau đợt 66 câu đó sai — sửa cho khớp code thật. Chỉ sửa câu sai, không viết
lại cả docstring.

Kiểm tra luôn `trading/collector/main.py` chỗ gọi hàm (đợt 63 để lại chú thích
`# Brief 52 / Brief 63: Gắn RotatingFileHandler vào logger "trading.alerts"`) — sửa cho đúng.

---

## 5. Báo cáo cho Claude

1. Kết quả hai lệnh kiểm tra tiền đề (Task 1), dán nguyên văn.
2. `git diff trading/logging_setup.py`.
3. `git diff tests/test_logging_setup.py` + output pytest của file đó.
4. Bằng chứng test phân biệt được (Task 3), dán nguyên văn cả lần đỏ lẫn lần xanh.
5. `git diff` các chú thích sửa ở Task 4.
6. `uv run pytest -m "not integration" -q` — hiện là 705, báo số mới.
7. `uv run ruff check trading tests scripts` sạch.
8. **Không commit, không push, không deploy.**
