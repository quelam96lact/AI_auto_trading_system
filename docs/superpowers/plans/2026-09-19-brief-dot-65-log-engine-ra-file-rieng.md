# Brief đợt 65 — Đưa log bền vững của engine ra file RIÊNG, không làm bẩn bằng chứng phiên 22/09

Ngày giao: 19/09/2026 (thứ Bảy).
Base: main hiện tại (`9b4fb3f`, đã gồm đợt 63 và 64).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Brief này KHÔNG tiếp tục việc gì

Đợt 64 đã đóng dòng việc "buy-and-hold có nhịp": chiến lược chỉ thắng B&H **1/11 năm**, toàn bộ
khoản lãi vượt trội trong mẫu dồn vào đúng một năm (2022). Đó là kết luận cuối, **không tinh chỉnh
thêm, không đo lại, không thử ngưỡng khác** — làm vậy chính là overfit thêm một lớp. Việc có nên
đặt hàng một cuộc tìm chiến lược mới hay không là quyết định của chủ dự án, không thuộc brief này.

Brief này chỉ làm nốt **một việc đợt 63 cố ý bỏ dở**, và nó gấp vì liên quan trực tiếp tới phép đo
quyết định sáng thứ Hai 22/09.

---

## 1. Vì sao gấp — đọc kỹ, đây là lý do tồn tại của brief

Đợt 63 đã tạo `trading/logging_setup.py::attach_durable_alert_handler()` và cho **cả** collector
lẫn engine gọi nó. Nhưng:

1. **Phần engine hiện đang chết lâm sàng.** `docker-compose.yml` chỉ có
   `volumes: [./logs:/app/logs]` cho service `collector`; service `engine` **không có mount nào**.
   Hàm tự kiểm `if not path.is_dir(): return`, nên trong container engine nó lặng lẽ không làm gì.
   Cảnh báo Telegram gửi trượt từ `real_orders.py`/engine vẫn bốc hơi khi container dựng lại —
   đúng cái lỗ đợt 58 mục C đã chỉ ra, chưa hề được bịt.

2. **Nhưng thêm mount một cách ngây thơ thì còn tệ hơn để nguyên.** Cả hai container đều gọi
   `attach_durable_alert_handler()` **không tham số**, tức cùng mặc định
   `filename="bars_closed.log"`. Nếu engine được mount vào cùng `./logs`, sẽ có **hai tiến trình
   hệ điều hành độc lập cùng chạy `RotatingFileHandler` trên đúng một file**. Mỗi tiến trình tự
   đếm kích thước và tự xoay vòng, không biết tiến trình kia tồn tại. Khi engine chạm ngưỡng 5MB
   trước, nó đổi tên `bars_closed.log` → `bars_closed.log.1` **ngay dưới chân collector**:
   collector vẫn giữ file handle cũ nên tiếp tục ghi vào cái file vừa bị đổi tên, trong khi
   `stream_health_check.py` đọc `logs/bars_closed.log` mới tinh, gần như rỗng.

3. **Hậu quả cụ thể, không phải giả định:** `stream_health_check.py` lấy
   `logs/bars_closed.log` làm **nguồn ưu tiên số 2, trên cả `docker compose logs`** (xem mục
   "Brief 52 Task 1.3: Thứ tự ưu tiên nguồn log" trong file đó). Một lần xoay vòng lệch pha đúng
   sáng 22/09 là đủ biến một phiên lành thành `0 nến / exit 2` — đúng kiểu hỏng mà chính đợt 52 đã
   ghi cảnh báo trong code ("bien mot phien lanh 93,8% thanh '0 nen / exit 2'").

   Lưu ý cho chính xác, đừng nói quá khi báo cáo: `count_stream_bars_closed` chỉ đếm dòng có chuỗi
   `"bars closed"`, nên alert JSON của engine **không** bị đếm nhầm thành nến. Rủi ro nằm ở **xoay
   vòng tranh chấp**, không nằm ở đếm nhầm.

**Kết luận thiết kế, đóng băng:** engine ghi ra **file riêng**, `engine_alerts.log`. Cùng thư mục
host `./logs` là được — khác tên file thì hai `RotatingFileHandler` có trạng thái xoay vòng độc
lập, không giẫm chân nhau.

---

## 2. Ràng buộc

Không đổi `trading/logging_setup.py` (tham số `filename` đã có sẵn, dùng đúng nó). Không đổi
đường ghi của collector (`bars_closed.log` giữ nguyên tuyệt đối). Không bật
`real_trading_enabled`. Không sửa `config/config.yaml`. **Không commit, không push.**

---

## Task 1 — Engine ghi ra `engine_alerts.log`

### 1.1. `trading/engine/main.py`

Trong `_configure_logging()`, đổi lời gọi thành:

```python
attach_durable_alert_handler(filename="engine_alerts.log")
```

Chỉ đổi đúng lời gọi này. Không đụng `logging.basicConfig` phía trên, không đụng `main()`.

### 1.2. `docker-compose.yml`

Thêm cho service `engine` (và **chỉ** service `engine`) mount giống collector đang có:

```yaml
    volumes:
      - ./logs:/app/logs
```

Không đổi bất kỳ dòng nào khác của file này — không đổi `mem_limit`, `cpus`, `environment`,
`depends_on`, và **không đụng** khối của `collector`.

### 1.3. Kiểm chứng

`docker-compose.yml` sau khi sửa phải có **đúng hai** service mang mount `./logs:/app/logs`
(engine và collector). Dán kết quả:

```powershell
Select-String -Path docker-compose.yml -Pattern "logs:/app/logs" -Context 6,0
```

---

## Task 2 — Test chứng minh hai file tách biệt

Thêm vào `tests/test_logging_setup.py` (giữ nguyên 2 test đã có, chỉ **thêm**):

1. **Test tên file tuỳ biến**: gọi `attach_durable_alert_handler(log_dir=tmp_path,
   filename="engine_alerts.log")`, log một CRITICAL qua `alert()`, khẳng định
   `tmp_path/"engine_alerts.log"` tồn tại và có nội dung, **và** `tmp_path/"bars_closed.log"`
   **không** tồn tại. Đây là điểm mấu chốt của cả brief: chứng minh log engine không rơi vào file
   bằng chứng của collector.

2. **Test idempotent với tên file khác**: gọi hàm hai lần với `filename="engine_alerts.log"`,
   khẳng định logger `"trading.alerts"` vẫn chỉ có **đúng một** handler tên `"trading-alerts-file"`.

   **Ghi lại phát hiện, đừng tự sửa:** guard chống trùng của hàm dựa trên **tên handler**, mà tên
   đó là hằng số `HANDLER_NAME` dùng chung cho mọi tên file. Nghĩa là trong **cùng một tiến trình**,
   gọi hàm lần hai với `filename` khác sẽ **không** gắn thêm handler thứ hai — file thứ hai không
   bao giờ được tạo. Điều này **không gây lỗi ở production** (collector và engine là hai tiến
   trình/container tách biệt, mỗi bên chỉ gọi một lần, một tên), nhưng nó là một cạm bẫy thật nếu
   sau này có ai gọi hai lần trong một tiến trình. Hãy viết test phản ánh **hành vi thật đang có**
   (một handler), và **báo cáo cạm bẫy này cho Claude** trong mục nhận xét — **không tự đổi
   `logging_setup.py`** để "sửa" nó, vì đổi khoá guard là thay đổi hợp đồng, phải do Claude quyết.

3. Chạy `uv run pytest tests/test_logging_setup.py -v`, dán nguyên văn.

---

## Task 3 — Đồng bộ tài liệu triển khai (chỉ những dòng trở thành SAI)

Việc thêm mount cho engine làm một số câu trong runbook sai sự thật:

- `DEPLOYMENT.md:25` (tham khảo, tự xác nhận lại số dòng) hiện ghi mount `./logs:/app/logs` là
  **"cho collector"** — sau thay đổi này không còn đúng.
- `docs/README_VPS_UBUNTU.md` là runbook song sinh, đợt 54 đã thống nhất **hai file một nội dung**
  — nếu nó có câu tương ứng, sửa **cùng lúc**, đừng để hai bản lệch nhau trở lại.

Sửa **tối thiểu**: chỉ những câu trở thành sai (nói mount chỉ dành cho collector), và bổ sung một
câu ngắn cho biết engine ghi `logs/engine_alerts.log`. **Không viết lại mục, không dọn dẹp văn
phong, không đụng phần khác của hai file.**

Lệnh `mkdir -p logs && sudo chown 10001:10001 logs` **không đổi** — engine chạy cùng image nên
cùng uid `10001`, không cần bước phân quyền mới. Đừng thêm bước thừa.

---

## Task 4 — Báo cáo trạng thái container, KHÔNG deploy

Chạy và dán nguyên văn, **chỉ đọc, không sửa gì**:

```powershell
docker compose ps
```

**Tuyệt đối không** chạy `docker compose build`, `up`, `restart`, `down`, không dựng lại image,
không khởi động lại service nào. Việc dựng lại và xác minh hai lớp (image-ID + grep chuỗi code
trong container đang chạy, quy ước đợt 58) là của Claude, làm sau khi audit, có chủ đích chọn thời
điểm còn đệm trước sáng thứ Hai.

---

## 3. Không làm

- **Không tiếp tục/tinh chỉnh chiến lược đợt 64** (đã đóng — xem mục 0).
- **Không đổi `trading/logging_setup.py`** — kể cả khi thấy cạm bẫy guard ở Task 2.2.
- **Không đổi đường ghi hay tên file của collector.**
- **Không đụng `.probe_dead_man_switch.py`** (bỏ dấu chấm) và **không che `chat_id` trong probe** —
  cả hai đã hẹn "sau tuần go-live", giữ đúng hẹn.
- **Không deploy, không build, không restart** (Task 4).
- Không commit, không push.

---

## 4. Báo cáo cho Claude

1. `git diff trading/engine/main.py` — đúng một dòng đổi.
2. `git diff docker-compose.yml` — chỉ thêm 2 dòng vào service `engine`.
3. Output `Select-String` ở mục 1.3.
4. `git diff tests/test_logging_setup.py` + output pytest của file đó.
5. `git diff DEPLOYMENT.md docs/README_VPS_UBUNTU.md` — chỉ những câu trở thành sai.
6. Nhận xét về cạm bẫy guard theo `HANDLER_NAME` (Task 2.2) — mô tả, không tự sửa.
7. `docker compose ps` (Task 4).
8. `uv run pytest -m "not integration" -q` — báo tổng số test (hiện là 703, sẽ tăng thêm số test
   mới của Task 2).
9. `uv run ruff check trading tests scripts` sạch.
