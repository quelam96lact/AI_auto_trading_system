# Báo cáo kỹ thuật Đợt 63 — Dọn `is_trading_day` và Logger bền vững

- **Ngày thực hiện:** 19/09/2026
- **Người thực thi:** Gemini Flash 3.8
- **Người bàn giao & kiểm định:** Claude (auditor)
- **Base commit:** `177575c`

---

## 1. Task 1 — Dọn 7 chỗ trùng `is_trading_day`

### 1.1. Thay đổi thực hiện
Thay thế toàn bộ các đoạn mã tự kiểm tra ngày giao dịch thủ công bằng hàm duy nhất `is_trading_day(d)` trong `trading/calendar_vn.py`.

1. **`trading/calendar_vn.py` (4 vị trí):**
   - `is_trading_time(dt)`:
     - Cũ: `if dt.weekday() >= 5: return False` và `if d in VIETNAM_HOLIDAYS_SET: return False`
     - Mới: `if not is_trading_day(d): return False`
   - `trading_days_between(start, end)`:
     - Cũ: `if cur.weekday() < 5 and cur not in VIETNAM_HOLIDAYS_SET:`
     - Mới: `if is_trading_day(cur):`
   - `market_minutes_between(start, end)`:
     - Cũ: `if cur.weekday() < 5 and cur not in VIETNAM_HOLIDAYS_SET:`
     - Mới: `if is_trading_day(cur):`
   - `is_continuous_matching(dt)`:
     - Cũ: `if dt.weekday() >= 5: return False` và `if d in VIETNAM_HOLIDAYS_SET: return False`
     - Mới: `if not is_trading_day(d): return False`

2. **`scripts/heartbeat_check.py` (3 vị trí):**
   - Đổi import: `from trading.calendar_vn import is_trading_day` (đồng thời giữ nguyên `_print_safe`).
   - `in_bar_check_window(now)`:
     - Cũ: `if now.weekday() >= 5 or now.date() in VIETNAM_HOLIDAYS_SET: return False`
     - Mới: `if not is_trading_day(now.date()): return False`
   - `token_expiry_status(now)`:
     - Cũ: `is_trading_day = (now.weekday() < 5 and now.date() not in VIETNAM_HOLIDAYS_SET)`
     - Mới: `is_td = is_trading_day(now.date())`
   - `main()`:
     - Cũ: `is_trading_day = (now.weekday() < 5 and now.date() not in VIETNAM_HOLIDAYS_SET)`
     - Mới: `is_td = is_trading_day(now.date())`

### 1.2. Blast Radius & Độc lập kiểm chứng
- Grep toàn bộ codebase xác nhận không còn chỗ nào tự check `weekday() < 5 and ... not in VIETNAM_HOLIDAYS_SET` ngoài chính định nghĩa `is_trading_day`.
- Kết quả test: `uv run pytest -m "not integration" -q` đạt **699 passed, 113 deselected** (bảo toàn 100% test cũ).

---

## 2. Task 2 — Siết chặt điều kiện thành công trong `docker_down_alert.py`

### 2.1. Phân tích lỗ hổng & Sửa đổi
- **Vấn đề:** Trong `scripts/docker_down_alert.py`, hàm `send_telegram_alert(...)` trả về `bool` (`True` nếu thành công, `False` nếu thất bại). Tuy nhiên, dòng 60 cũ kiểm tra:
  ```python
  if ok is not False:
  ```
  Nếu mock `send` trả về `None`, `ok` là `None` -> `ok is not False` đánh giá thành `True`, dẫn tới coi như gửi thành công và ghi file stamp, dập tắt cảnh báo kế tiếp.
- **Khắc phục:** Đổi thành:
  ```python
  if ok:
  ```
- **Cập nhật tests:** Trong `tests/test_docker_down_alert.py`, 4 test cũ dùng `_fake_send` không trả về giá trị (mặc định trả về `None`), đã được sửa thành `return True`.

### 2.2. Bằng chứng phá hoại (Test phân biệt được)
Thêm test mới `test_send_tra_none_bi_coi_la_that_bai(tmp_path)`:
```python
def test_send_tra_none_bi_coi_la_that_bai(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp.txt"
    sent: list[str] = []

    def _send_none(msg: str) -> None:
        sent.append(msg)
        return None

    ok = send_down_alert_debounced(
        services=["collector"],
        send=_send_none,
        stamp_path=stamp,
        debounce_seconds=300,
    )
    assert not ok, "send tra ve None phai bi coi la that bai"
    assert not stamp.exists(), "That bai thi khong duoc ghi stamp"
```

- **Khi chạy trên code cũ (`if ok is not False:`): ĐỎ (FAILED)**
```text
FAILED tests/test_docker_down_alert.py::test_send_tra_none_bi_coi_la_that_bai - AssertionError: send tra ve None phai bi coi la that bai
assert not True
```

- **Khi chạy trên code mới (`if ok:`): XANH (PASSED)**
```text
tests/test_docker_down_alert.py::test_send_tra_none_bi_coi_la_that_bai PASSED [100%]
7 passed in 0.18s
```

---

## 3. Task 3 — Trích xuất Logger dùng chung bền vững

### 3.1. Thiết kế module mới `trading/logging_setup.py`
Tạo hàm cấu hình logger tập trung:
```python
def attach_durable_alert_handler(
    log_dir: str = "/app/logs",
    filename: str = "bars_closed.log",
    logger_name: str | None = None,
) -> logging.Handler | None:
```
Đặc tính kỹ thuật:
- Đảm bảo tính idempotent: Không gắn trùng RotatingFileHandler nếu logger đã có handler trỏ tới cùng tệp.
- Tạo thư mục cha an toàn với fallback: Bọc trong `try...except OSError` kèm cảnh báo nhẹ vào console, không crash ứng dụng nếu thiếu quyền ghi thư mục.
- Định dạng chuẩn: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- Dung lượng xoay vòng: `maxBytes=5_000_000` (5MB), `backupCount=5`.

### 3.2. Tích hợp Collector & Engine
- **Collector (`trading/collector/main.py`):**
  Refactor `_configure_logging()` gọi `attach_durable_alert_handler()`.
- **Engine (`trading/engine/main.py`):**
  Bổ sung hàm `_configure_logging()` gọi `attach_durable_alert_handler()`, được kích hoạt ngay trước `asyncio.run(main())`.

### 3.3. Unit tests `tests/test_logging_setup.py`
1. `test_attach_durable_alert_handler_idempotent`: Gọi 2 lần liên tiếp không tạo ra 2 handler trùng lặp.
2. `test_attach_durable_alert_handler_writes_log`: Ghi nhận log message đúng vào file đích.
Kết quả: 2/2 tests PASSED.
Tổng test suite tăng từ **699 passed lên 702 passed**.
