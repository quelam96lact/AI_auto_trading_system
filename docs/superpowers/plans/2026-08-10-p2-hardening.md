# Plan 2026-08-10 — P2: test xanh trở lại, shutdown sạch, connection pooling

Ba việc tồn đọng từ đợt audit go-live. Thứ tự trong plan là **bắt buộc**: Task 1
trước, vì tới khi integration suite còn đỏ thì không có baseline nào để phát hiện
regression do Task 2/3 gây ra.

## Đánh giá mức độ cần thiết (đọc trước khi làm)

- **Task 1 (test)** — thuần lợi, không rủi ro sản xuất. Làm chắc chắn.
- **Task 2 (SIGTERM)** — sửa một lỗi đúng nghĩa, không phải dọn dẹp: xem phân
  tích ở Task 2. Đáng làm.
- **Task 3 (pool)** — cải thiện thật nhưng **không cấp bách**. Ở tải hiện tại
  (nến 5 phút, 3 mã streaming) connection-per-query không gây vấn đề đo được;
  nó chỉ từng thành thảm hoạ khi cộng hưởng với bug `localhost`/IPv6 (đã sửa).
  Đổi lại phải thêm dependency và nhận thêm các chế độ hỏng mới (connection ôi,
  pool cạn) vào một hệ thống giao dịch. Tôi vẫn làm vì được giao, nhưng nếu phải
  bỏ bớt một task thì bỏ task này chứ không phải Task 2.

---

## Task 1 — Sửa 3 integration test hỏng sẵn

**Cả 3 đều là fixture cũ so với tính năng thêm sau, KHÔNG phải bug code.** Tôi đã
truy nguyên nhân từng cái (đo thật, không suy đoán). Đừng "sửa" code sản xuất để
chiều test.

### 1a. `tests/test_backtest_cli.py::test_read_resample_replay_is_deterministic_from_real_db`

Lỗi: `TypeError: run_backtest() missing 1 required positional argument: 'capital'`.
`run_backtest` giờ nhận `(bars, strategy, risk, trailing_stop, capital)` —
`trailing_stop` được thêm sau, test vẫn truyền 4 đối số nên `capital` nuốt mất
vị trí của `trailing_stop`.

Sửa: truyền `TrailingStopManager()` đúng vị trí thứ 4.

→ kiểm chứng: test PASS, và `r1 == r2` (tính xác định) vẫn đúng.

### 1b. `tests/test_engine_main.py::test_engine_persists_fill_and_restores_state_on_next_run`

Lỗi: `assert 700000 == 100`. Test viết trước khi có ATR sizing; giờ
`approve_sized` tính qty theo `risk_pct * capital / (atr * atr_multiplier)`,
với fixture này ra 700.000 chứ không phải `strategy.qty = 100`.

Sửa: **đừng thay 100 bằng 700000.** Con số đó là hệ quả của công thức sizing;
hard-code lại sẽ vỡ y hệt lần sau khi ai đó chỉnh `risk_pct` hoặc `atr_period`.
Test này tên là "persists fill and restores state" — điều nó cần khẳng định là
qty đọc lại từ DB **bằng đúng qty đã ghi**, không phải một hằng số. Đọc qty thật
sau lần chạy đầu, rồi assert lần chạy sau khôi phục đúng giá trị đó, và
`qty > 0`.

→ kiểm chứng: test PASS; và PASS luôn khi đổi `risk_pct` sang 0.02 (thử tay rồi
trả lại) — nếu đổi tham số làm test đỏ thì bạn vẫn đang hard-code.

### 1c. `tests/test_engine_main.py::test_engine_alerts_critical_on_risk_halt`

Lỗi: `alerts_seen` chỉ có `('INFO', 'engine starting fresh')`.

Nguyên nhân (đã đo, đừng đoán lại): bộ lọc ATR% trong
`SmaCrossStrategy.compute_crossover` ép crossover về `None` khi
`atr / close < atr_pct_threshold` (0.005). Fixture dùng giá 90.000 → 95.000:
ATR sau cú nhảy ≈ 357, `357 / 95.000 = 0,0038 < 0,005` → **không có crossover
nào**, nên `approve_sized` được gọi **0 lần**, nên `_halt_check` không bao giờ
chạy. Tôi đã instrument và xác nhận con số 0 này.

Cơ chế halt vẫn đúng và đã có unit test phủ
(`test_halts_all_trading_for_rest_of_day_after_max_loss`,
`test_approve_sized_shares_halt_state_with_approve`). Việc còn thiếu ở tầng
engine chỉ là **dây nối**: khi `risk.halted_date` chuyển trạng thái thì engine
phải phát CRITICAL.

Sửa: test dây nối, đừng cố dựng lại chuỗi giá làm halt tự nhiên. Đã có tiền lệ
ngay trong chính file này —
`test_engine_run_persists_real_risk_halt_on_transition` monkeypatch
`handle_crossover` để set `risk_arg.halted_date` rồi assert alert. Làm điều
tương đương cho luồng paper: ép `RiskManager.approve_sized` set `halted_date`
(monkeypatch ở cấp class hoặc module) rồi assert engine phát
`("CRITICAL", "risk halt: max daily loss reached")`.

Nếu bạn tìm được cách dựng fixture giá làm halt xảy ra tự nhiên mà vẫn ổn định
(không phụ thuộc trailing stop bắn đúng thời điểm), cứ đề xuất — nhưng phải nói
rõ và đừng làm test mong manh.

→ kiểm chứng: test PASS. Và test phải THẤT BẠI nếu xoá nhánh alert CRITICAL
trong `engine/main.py` — thử xoá tạm để chứng minh test có tác dụng, rồi khôi
phục. Paste cả hai kết quả.

### Tiêu chí Task 1

`uv run pytest -m integration -q` → **42 passed, 0 failed**.
Chạy mất ~19 giây khi cả postgres lẫn nats đang chạy; nếu lâu hơn nhiều nghĩa là
một service chưa lên (`docker compose up -d postgres nats`).

---

## Task 2 — Xử lý SIGTERM (engine + collector)

### Tại sao đây là bug, không phải dọn dẹp

`docker compose stop` gửi SIGTERM. Python mặc định chết ngay: `finally` không
chạy, task đang dở bị cắt.

**Engine:** nếu SIGTERM tới sau khi `process_bar` đã mutate broker và
`persist_fills` đã ghi DB, nhưng TRƯỚC `msg.ack()`, thì JetStream sẽ giao lại
message đó sau `ack_wait`. Lần chạy sau engine khôi phục state từ DB rồi xử lý
LẠI đúng nến ấy → **lệnh trùng và PnL tính hai lần**. Đây chính xác là kịch bản
mà comment `term()` trong `main.py:142-145` đã cảnh báo, chỉ khác đường vào.
Mỗi lần deploy là một lần quay xổ số.

**Collector:** `persist_bars` chạy fire-and-forget qua `asyncio.create_task`.
SIGTERM giữa chừng làm mất nến đã đóng mà không ai biết — không alert, không log.

### Việc cần làm

Cả hai service: bắt SIGTERM/SIGINT → set cờ dừng → **kết thúc công việc đang
làm** → thoát sạch.

- `trading/engine/main.py::run` — vòng lặp thoát ở ranh giới message (sau
  `ack()`/`term()`), không cắt giữa. `finally` hiện có (`nc.close()`) giữ nguyên.
- `trading/collector/main.py::run` — dừng `housekeeping_loop`, `await feed.stop()`,
  chờ các task `persist_bars` đang chạy xong (dùng một set theo dõi task, có
  timeout — vd 10 giây — rồi alert WARN nếu vẫn còn), `await pub.close()`.

**Chi tiết bắt buộc — Windows:** `loop.add_signal_handler` ném
`NotImplementedError` trên Windows (nơi bạn đang dev), chỉ chạy trên Linux (nơi
sản xuất chạy). Dùng `add_signal_handler` và fallback sang `signal.signal` khi
`NotImplementedError`. **Đừng viết test dựa vào việc gửi signal thật** — test
phần logic: cờ dừng đã set thì vòng lặp thoát ở ranh giới message và không bỏ
sót ack.

→ kiểm chứng bằng:
1. Unit test: engine đang xử lý dở, set cờ dừng → vòng lặp thoát SAU khi ack
   message hiện tại, không phải trước. Assert message đã được ack.
2. Unit test: collector set cờ dừng → `feed.stop()` được gọi, `pub.close()` được
   gọi, và task `persist_bars` đang chạy được chờ xong (không bị bỏ rơi).
3. Integration hiện có vẫn xanh (42 passed) — `run(max_messages=N)` phải giữ
   nguyên hành vi cũ.

**KHÔNG đụng** logic `term()`/`ack()` hiện tại, không đổi cách xử lý poison
message, không đổi `max_messages`.

---

## Task 3 — Connection pooling cho `Storage`

`Storage.conn()` mở `psycopg.connect(self.dsn)` MỚI cho từng query. Đọc lại phần
"Đánh giá mức độ cần thiết" ở đầu plan trước khi làm.

### Việc cần làm

- Thêm dependency `psycopg-pool` vào `pyproject.toml` (cùng nhà với psycopg,
  không phải thư viện bên thứ ba lạ). Cập nhật `uv.lock`.
- `Storage.conn()` lấy connection từ pool thay vì tự connect. **Giữ nguyên chữ
  ký và ngữ nghĩa** — `with storage.conn() as c:` phải commit khi thoát sạch y
  như hiện tại, để KHÔNG call site nào phải sửa.
- Pool dùng chung ở **cấp module, khoá theo DSN**, không phải một pool cho mỗi
  instance `Storage`. Lý do: test tạo hàng chục đối tượng `Storage`; mỗi cái một
  pool sẽ ngốn hết connection của Postgres. Kích thước nhỏ (vd `min_size=1,
  max_size=8`).

→ kiểm chứng bằng:
1. Unit test: hai `Storage` khác nhau cùng DSN dùng CHUNG một pool (đúng cái bẫy
   trên).
2. Integration đầy đủ vẫn 42 passed.
3. Đo trước/sau: thời gian chạy `pytest -m integration` (hiện ~19 giây). Báo cả
   hai số. Không cần nhanh hơn, nhưng **không được chậm đi**.
4. Postgres restart giữa chừng không làm hỏng vĩnh viễn: dừng container postgres,
   khởi động lại, rồi gọi lại một query — phải hoạt động (pool tự thay
   connection chết). Đây là chế độ hỏng MỚI mà pool mang lại, phải chứng minh nó
   được xử lý. Paste kết quả.

---

## Phạm vi phẫu thuật (toàn bộ plan)

**Được sửa:** `tests/test_backtest_cli.py`, `tests/test_engine_main.py`,
`trading/engine/main.py`, `trading/collector/main.py`, `trading/storage/db.py`,
`pyproject.toml`, `uv.lock`, và các file test mới cho Task 2/3.

**KHÔNG đụng:** `trading/risk.py`, `trading/strategies/sma_cross.py`,
`trading/engine/logic.py`, `trading/backtest.py`, `trading/collector/backfill.py`,
`trading/collector/feed.py`, schema SQL, docker-compose, Dockerfile.

**KHÔNG chạy `ruff check --fix`.** 7 lỗi ruff có sẵn dưới `scripts/` để nguyên.
**KHÔNG commit, KHÔNG push.**

## Dừng lại và hỏi nếu

- Task 1c không thể làm ổn định bằng cách monkeypatch — nói rõ vướng gì.
- Task 3 làm bất kỳ integration test nào đỏ — dừng, báo, đừng sửa test để chiều
  pool.
