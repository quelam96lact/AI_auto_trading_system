# Brief đợt 63 — Dọn `is_trading_day` trùng lặp, siết `docker_down_alert`, logger bền vững cho engine

Ngày giao: 19/09/2026 (thứ Bảy, khuya).
Base: main hiện tại (đợt 62 đã merge tại `e1f786b`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao làm bây giờ, không chờ như đã định

Ba việc trong brief này (Task 1, 2, 3) đều đã được **cố tình hoãn** ở đợt 57/58 với lý do
tường minh: "để sau phép đo grace=20 thứ Hai 22/09, không thêm biến số trước khi đo." Hôm nay
(19/09) tôi hỏi lại chủ dự án có nên tiếp tục chờ không — chủ dự án chọn **làm ngay bây giờ**,
biết rõ rủi ro trên. Ghi lại đây để không ai đọc code sau này tưởng tôi quên nguyên tắc trình tự
đã tự đặt ra.

Vì vậy: **Task 3 (logger) không được đụng tới bất kỳ container đang chạy nào (local hay VPS)** —
chỉ code + test. Build lại image, deploy, và xác minh hai lớp (image-ID + grep code trong
container đang chạy, quy ước đã lập ở đợt 58) do Claude quyết định thời điểm, tách biệt hoàn
toàn khỏi việc thực thi brief này.

## Ràng buộc chung

Không sửa `config/config.yaml`, không bật `real_trading_enabled`, không đụng
`trading/engine/logic.py`/strategy/risk. Không commit, không push.

---

## Task 1 — Dọn `is_trading_day` trùng lặp (7 chỗ, 2 file)

### 1.1. `trading/calendar_vn.py` — đây là việc đã bị hoãn ở đợt 57

Bốn hàm trong CHÍNH file định nghĩa `is_trading_day` lại tự suy lại điều kiện
`weekday() >= 5 or date in holidays` thay vì gọi `is_trading_day()` đã có sẵn ngay phía trên:

| Hàm | Dòng (tham khảo, có thể lệch nếu file đã đổi) | Biểu thức trùng |
|---|---|---|
| `is_trading_time` | ~10 | `ts.weekday() >= 5 or ts.date() in holidays` |
| `trading_days_between` | ~39 | `d.weekday() < 5 and d not in holidays` |
| `market_minutes_between` | ~72 | `day.weekday() < 5 and day not in holidays` |
| `is_continuous_matching` | ~91 | `ts.weekday() >= 5 or ts.date() in holidays` |

Sửa cả 4 để gọi `is_trading_day(ts.date(), holidays)` (hoặc biến ngày cục bộ tương ứng: `d`,
`day`) thay vì tự viết lại điều kiện. **Không đổi chữ ký hàm, không đổi hành vi quan sát được** —
đây là refactor thuần tuý, không phải sửa lỗi.

**Trước khi sửa mỗi hàm**: chạy `gitnexus_impact({target: "<tên hàm>", direction: "upstream"})`
và báo cáo blast radius. Nếu GitNexus MCP không kết nối được lúc bạn chạy, tự liệt kê toàn bộ nơi
gọi bằng grep (`is_trading_time\(|trading_days_between\(|market_minutes_between\(|is_continuous_matching\(`
trên toàn repo) và ghi rõ trong báo cáo bạn đã làm thủ công vì MCP không khả dụng — đừng bỏ qua
bước này im lặng.

### 1.2. `scripts/heartbeat_check.py` — phát hiện MỚI hôm nay (19/09), chưa từng nằm trong brief nào trước

Ba chỗ hand-roll cùng điều kiện thay vì gọi hàm dùng chung:

- `in_bar_check_window()`, dòng ~80: `if ts.weekday() >= 5 or ts.date() in holidays: return False`
- Khối tính `pre_market` trong hàm kiểm token (dòng ~143-147):
  ```python
  pre_market = (
      time(8, 0) <= t < time(9, 0)
      and now_tz.weekday() < 5
      and now_tz.date() not in holidays
  )
  ```
- Khối tính `pre_market` tương tự trong `main()` (dòng ~239-243), cùng công thức.

Thay cả 3 bằng gọi `is_trading_day(ts.date(), holidays)` / `is_trading_day(now_tz.date(), holidays)`
từ `trading.calendar_vn` (thêm import nếu file chưa import). **Trước khi sửa**: tự grep lại
`weekday\(\) *(>=|<) *5` trong đúng file này để xác nhận đúng 3 chỗ như trên — nếu thấy khác (số
lượng hoặc vị trí), báo cáo lại, đừng tự ý coi là đúng theo brief.

### 1.3. Kiểm chứng

Đây là refactor **không đổi hành vi**, nên không thêm test mới. Tiêu chí duy nhất:

```bash
uv run pytest -m "not integration" -q
```

phải ra **đúng** `699 passed, 113 deselected` — không hơn, không kém, không test nào đổi từ pass
sang fail hay ngược lại. Nếu số liệu khác đi, dừng lại — nghĩa là refactor đã vô tình đổi hành vi,
báo cáo ngay, đừng tự sửa test cho khớp.

---

## Task 2 — Siết `docker_down_alert.py`: `if ok is not False` → `if ok:`

### 2.1. Đọc trước

`docs/superpowers/plans/2026-09-19-brief-dot-57-tuan-go-live.md` mục "E. Một chỗ lỏng có chủ ý" —
hiểu tại sao đợt 57 cố tình để `is not False` thay vì `if ok:` (4 test cũ truyền
`send=sent.append`, `list.append` trả `None`, `if ok:` sẽ coi `None` là thất bại và làm 4 test đó
đổ, trong khi brief đợt 57 khi đó cấm sửa test cũ).

### 2.2. Sửa 4 test cũ trong `tests/test_docker_down_alert.py`

Các test đang gọi `run_alert(..., send=sent.append, ...)`. Đổi callable giả để trả về `bool`
tường minh thay vì dựa vào `list.append` trả `None`, ví dụ:

```python
def _fake_send(sent):
    def _send(msg):
        sent.append(msg)
        return True
    return _send
```

rồi gọi `send=_fake_send(sent)`. **Không đổi ý nghĩa hay kịch bản của 4 test này** — chỉ đổi cách
hàm giả trả kết quả, để tương thích với `if ok:` sắp siết ở bước sau.

### 2.3. Siết điều kiện

Đổi `scripts/docker_down_alert.py:135` (tham khảo, có thể lệch dòng):
`if ok is not False:` → `if ok:`.

### 2.4. Kiểm chứng — bắt buộc chứng minh phân biệt được

1. Toàn bộ `tests/test_docker_down_alert.py` xanh (4 test cũ đã sửa cách gọi + 2 test mới của
   đợt 57 không đổi).
2. Chứng minh khác biệt hành vi thật sự tồn tại: viết một test tạm/thử nghiệm (không cần giữ lại
   trong bộ test chính thức, nhưng phải dán nguyên văn output vào báo cáo) truyền
   `send=lambda msg: None` (mô phỏng đúng hợp đồng cũ mơ hồ) — xác nhận với `if ok:` mới,
   `None` bị coi là THẤT BẠI (không ghi stamp), khác với hành vi `is not False` cũ vốn coi `None`
   là THÀNH CÔNG. Đây chính là điểm brief đợt 57 mục E đã ghi là "lỏng có chủ ý", giờ được siết
   lại.

---

## Task 3 — Logger `"trading"` bền vững cho CẢ collector lẫn engine

### 3.1. Đọc khuôn mẫu đã đúng

`trading/collector/main.py` hàm `_configure_logging()` (khoảng dòng 480-534) — pattern đã kiểm
chứng ở đợt 52: `RotatingFileHandler` gắn vào logger `"trading.alerts"`, `maxBytes=5MB`,
`backupCount=5`, formatter ISO-8601 UTC kết thúc bằng `Z`, guard chống gắn trùng bằng tên handler
`"trading-alerts-file"`, bọc try/except toàn bộ (không bao giờ được ném), chỉ gắn khi có volume
mount `/app/logs` (đang chạy trong container).

### 3.2. Trích thành hàm dùng chung — KHÔNG copy-paste lần hai

Tạo file mới `trading/logging_setup.py`, chuyển đúng logic gắn `RotatingFileHandler` (giữ nguyên
mọi tham số/hành vi đã liệt kê ở 3.1) vào một hàm, ví dụ:

```python
def attach_durable_alert_handler(log_dir: str = "/app/logs") -> None:
    ...
```

Đây là điểm mấu chốt của task: sắp có **hai nơi gọi** (collector + engine) cùng cần logic này —
nếu copy-paste nguyên khối vào `engine/main.py` thì chính task "dọn trùng lặp" này lại tạo ra một
chỗ trùng lặp mới. Một công thức, một chỗ.

### 3.3. `trading/collector/main.py._configure_logging()`

Gọi `attach_durable_alert_handler()` thay cho logic inline hiện có. Refactor thuần — hành vi
không đổi.

### 3.4. `trading/engine/main.py`

Hiện tại chỉ có `logging.basicConfig(level=logging.INFO, format="%(message)s")` trần trong
`main()` (dòng ~490), **không có** `_configure_logging()` riêng, **không có** `RotatingFileHandler`
nào — đây là lý do cảnh báo Telegram thất bại từ `real_orders.py`/engine biến mất hoàn toàn khi
container restart (phát hiện ghi ở đợt 58 mục C). Thêm hàm `_configure_logging()` tương tự
collector, gọi `attach_durable_alert_handler()` dùng chung, gọi hàm này trong `main()` trước
`asyncio.run(...)`.

### 3.5. Kiểm chứng — bắt buộc

1. **Test idempotency**: gọi `attach_durable_alert_handler()` hai lần liên tiếp trong cùng
   process (mô phỏng container logging setup chạy lại), xác nhận `logging.getLogger("trading.alerts")`
   chỉ có **đúng một** handler tên `"trading-alerts-file"` sau hai lần gọi — không nhân đôi.
2. **Test bền vững thật sự ghi được**: gọi hàm với `log_dir` trỏ vào `tmp_path` (không đụng
   `/app/logs` thật), log một dòng CRITICAL qua logger con của `"trading.alerts"` (hoặc
   `"trading.telegram"` nếu đó là logger thực tế phát cảnh báo — xác nhận lại cây logger trước khi
   viết test), xác nhận dòng đó xuất hiện trong file trong `tmp_path`.
3. `uv run pytest -m "not integration" -q` toàn bộ xanh, báo rõ số test mới thêm (từ 699 lên bao
   nhiêu).
4. `uv run ruff check trading tests scripts` sạch.

### 3.6. KHÔNG làm trong task này

- Không deploy, không restart, không rebuild image cho bất kỳ container nào (local hay VPS).
- Không đổi `docker-compose.yml`.
- Việc đưa file log engine vào cùng volume mount nào, tần suất `stream_health_check.py` đọc thêm
  nguồn mới — đó là một quyết định vận hành riêng, để Claude cân nhắc sau khi audit code này.

---

## Báo cáo cho Claude

1. `git diff trading/calendar_vn.py` — xác nhận cả 4 hàm chỉ đổi đúng dòng gọi `is_trading_day`,
   không đổi gì khác.
2. `git diff scripts/heartbeat_check.py` — xác nhận đúng 3 chỗ.
3. Kết quả `pytest` Task 1: đúng `699 passed, 113 deselected`.
4. `git diff scripts/docker_down_alert.py`, `git diff tests/test_docker_down_alert.py`.
5. Bằng chứng phân biệt được của Task 2 (mục 2.4.2), dán nguyên văn output.
6. `git diff` (hoặc toàn văn file mới) cho `trading/logging_setup.py`,
   `trading/collector/main.py`, `trading/engine/main.py`.
7. Bằng chứng hai test mới của Task 3 (mục 3.5.1, 3.5.2), dán nguyên văn output pass.
8. Tổng số test cuối cùng, `ruff check` sạch.
9. **Không commit, không push.**
