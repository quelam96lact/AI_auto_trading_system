# Kế hoạch: nạp lịch sử SMA lúc khởi động (rủi ro 5) + collector phục hồi nhanh sau gián đoạn DB

Ngày giao: 2026-08-13 tối. Nhánh: `feature/data-layer`. Base: `f1a410f`.

**KHÔNG commit, KHÔNG push.** `gitnexus_detect_changes` khi xong.

Hai việc **độc lập**. Làm xong việc A hãy làm việc B; đừng trộn vào một lượt sửa.

---

# VIỆC A — Rủi ro 5: engine mù ~1h45' sau khi khởi động lại

Đây là mục cuối cùng chưa làm trong `GO_LIVE_AUDIT.md`.

## Vấn đề

`SmaCrossStrategy._closes` là `deque` in-memory (`sma_cross.py:24`). Engine
**không** nạp lịch sử từ bảng `bars` lúc khởi động. Nó chỉ trông vào NATS phát
lại, mà consumer `engine` là **durable** nên sau lần chạy đầu nó tiếp tục từ vị
trí cũ chứ không phát lại từ đầu.

Cần `slow=20` close để tính được MA, cộng **một bar nữa** để `_prev_above` thoát
khỏi `None` (đọc `compute_crossover`: lần đầu đủ 20 bar vẫn trả `None` vì
`prev_above is None`). Vậy **21 bar 5 phút ≈ 1h45'**, trong một phiên chỉ dài
4h15'. Và nó **im lặng** — không cảnh báo gì.

`gitnexus_impact` trên `trading/engine/main.py::run`: **LOW**, chỉ `main()` gọi.

## Thiết kế đã chốt

### 1. Thêm `Storage.read_last_bars(symbol, n) -> list[Bar]`

Trả về `n` bar gần nhất của symbol, **sắp xếp tăng dần theo `ts`** (thứ tự thời
gian, vì ta sẽ nạp tuần tự vào chiến lược). Method mới → không có caller cũ nào
bị ảnh hưởng.

### 2. Chiến lược tự khai báo cần bao nhiêu bar

Thêm thuộc tính `SmaCrossStrategy.warmup_bars` trả về
`max(self.slow, self._atr.period) + 1`.

Vì sao không hardcode 21 ở `main.py`: `slow` và `atr_period` là tham số của
chiến lược. Ai đó đổi `atr_period=30` mà `main.py` vẫn nạp 21 bar thì ATR không
bao giờ sẵn sàng, và **hỏng im lặng**. Con số phải do chính chiến lược quyết.

Nếu `AtrCalculator` chưa lộ `period` ra ngoài, thêm cho nó — đừng đọc thuộc tính
private từ `SmaCrossStrategy`.

### 3. Nạp bằng `compute_crossover()`, KHÔNG dùng `process_bar()`

`compute_crossover()` chỉ cập nhật state kỹ thuật (MA + ATR), **không** sinh
lệnh. `process_bar()` thì đi qua broker và có thể tạo fill — tuyệt đối không
dùng cho bar lịch sử.

Docstring của `compute_crossover` ghi "CHỈ được gọi đúng 1 lần/bar/symbol". Nạp
warm-up tuân thủ điều đó: mỗi bar lịch sử gọi đúng một lần. Xem mục 4.

### 4. CHỐNG NẠP TRÙNG — phần dễ sai nhất

Sau khi nạp, ghi lại `warmed_until[symbol] = ts của bar cuối cùng đã nạp`.

Consumer `engine` là durable: khi engine khởi động lại, JetStream **giao lại các
bar chưa ack** — mà những bar đó cũng nằm trong DB nên vừa được nạp. Không chặn
thì cùng một bar vào `_closes` **hai lần**, làm lệch cửa sổ MA. Đó là biến chiến
lược "mù" thành chiến lược "sai", tệ hơn.

Trong vòng lặp message của `run()`: nếu `bar.ts <= warmed_until.get(bar.symbol)`
thì **bỏ qua toàn bộ xử lý bar đó** (vẫn `ack`, vì state đã phản ánh nó rồi).
Kèm comment nói rõ lý do.

### 5. Không nạp đủ thì phải KÊU

Nếu DB có ít hơn `warmup_bars` bar cho một symbol → `alert("WARN", ...)` nêu rõ
symbol và số bar nạp được, nói rõ rằng mã đó **vẫn đang mù**. Đây chính là cái
"im lặng" mà rủi ro 5 nói tới — sửa mà vẫn im lặng thì chưa sửa.

Nạp đủ → `alert("INFO", ...)` kèm số bar mỗi mã.

## Ràng buộc việc A

- Sửa: `trading/engine/main.py`, `trading/storage/db.py`,
  `trading/strategies/sma_cross.py`, `trading/indicators.py` (chỉ nếu cần lộ
  `period`).
- **KHÔNG** sửa `trading/engine/logic.py` — không đổi chữ ký `process_bar`.
- **KHÔNG** đụng `config/config.yaml`.

## Kiểm chứng việc A (dán output THẬT)

1. **Nạp xong là bắn được ngay.** Seed đủ `warmup_bars` bar vào DB sao cho bar
   sống kế tiếp tạo crossover → engine sinh lệnh **ngay từ bar đầu tiên** nhận
   qua NATS.
   → **RED bắt buộc:** bỏ phần nạp đi, cùng kịch bản → **không** có lệnh nào.
2. **Không nạp trùng.** Nạp warm-up xong, publish lại đúng những bar vừa nạp
   (ts cũ) → chiến lược **không** ăn chúng lần hai. Kiểm bằng trạng thái/kết quả
   quan sát được từ bên ngoài, đừng chọc vào `_closes`.
   → **RED bắt buộc:** bỏ điều kiện `warmed_until` → test phải fail.
3. **Thiếu lịch sử thì kêu.** DB chỉ có vài bar → có `WARN` nêu đúng symbol và
   số bar. Không có `WARN` là fail.
4. **Warm-up không sinh lệnh.** Bar lịch sử chứa cả bull lẫn bear crossover →
   sau khi khởi động, `orders` **không** có dòng nào sinh từ chúng.

---

# VIỆC B — Collector phục hồi heartbeat chậm sau gián đoạn DB

## Số đo thật (tôi đo tối nay)

Dừng `postgres` 4 phút rồi bật lại → collector mất **~90 giây** mới đập
heartbeat trở lại. Log: `PoolTimeout: couldn't get a connection after 30.00 sec`,
lặp lại.

Nó **có** tự phục hồi, đúng thiết kế. Nhưng ngưỡng cảnh báo của dead-man's
switch là 300s — biên chỉ 3,3 lần.

## Nguyên nhân

`ConnectionPool` mặc định `timeout=30`. Khi DB chết, `pool.connection()` chặn
30 giây rồi ném `PoolTimeout`. `housekeeping_tick` gọi `storage.beat()` sớm →
tick tốn 30s, rồi vòng lặp ngủ tiếp 30s.

## Quyết định của chủ dự án (2026-08-13)

`gitnexus_impact` trên `_get_pool`: **CRITICAL** — 59 symbol, 29 luồng, 6 module,
gồm cả đường đặt lệnh thật. Vì vậy **KHÔNG** hạ `timeout` toàn cục.

Thay vào đó: `Storage.conn()` nhận tham số `timeout` **tuỳ chọn**, mặc định
`None` (= giữ nguyên hành vi 30s). Chỉ đường housekeeping của collector truyền
timeout ngắn.

```python
@contextmanager
def conn(self, timeout: float | None = None):
    with _get_pool(self.dsn).connection(timeout=timeout) as c:
        yield c
```

`beat()` cần một đường truyền timeout xuống (thêm tham số tuỳ chọn cho `beat`,
mặc định giữ nguyên). Mọi caller cũ **không đổi một dòng nào** — đó là lý do
chọn cách này.

Timeout ngắn dùng **5 giây**.

## Ràng buộc việc B

- Sửa: `trading/storage/db.py`, `trading/collector/main.py`.
- **KHÔNG** đổi giá trị mặc định của pool. **KHÔNG** đổi `sleep_seconds=30` của
  `housekeeping_loop`.
- **KHÔNG** đụng đường đặt lệnh thật (`real_orders.py`, `confirm_real_order.py`).
- Mọi caller `conn()` hiện có phải giữ nguyên hành vi — đó là điều kiện khiến
  thay đổi này an toàn dù `conn()` có 59 symbol phụ thuộc.

## Kiểm chứng việc B (dán output THẬT)

1. **Đo lại đúng kịch bản tôi đã đo**, để so sánh được:
   - `docker compose stop postgres`, chờ **4 phút**
   - `docker compose start postgres`, bấm giờ tới khi
     `SELECT round(EXTRACT(epoch FROM now()-last_seen)) FROM heartbeat WHERE service='collector'`
     nhỏ hơn 60
   - **Trước: ~90 giây. Kỳ vọng sau: ≤ ~40 giây.** Dán con số thật, kể cả khi
     không đạt kỳ vọng.
   - Nhớ `docker compose up -d --build collector` để container chạy code mới,
     nếu không bạn đang đo lại code cũ.
2. **Mặc định không đổi.** Test: `conn()` không truyền timeout → vẫn dùng hành
   vi cũ. Đây là điều khiến bán kính ảnh hưởng bằng không, phải có test.
3. Suite đầy đủ vẫn xanh sau khi collector bị dừng/bật (không để lại rác).

---

# Toàn bộ

- `uv run pytest -q` → ≥ 260 + test mới.
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán risk + danh sách file.

Dán output thật, không tóm tắt, không diễn giải.

# Nếu thấy kế hoạch sai

Dừng và phản biện trước khi viết code. Đặc biệt việc A mục 4 (chống nạp trùng):
nếu bạn tìm được lý do rằng JetStream **không** thể giao lại bar đã có trong DB,
nói ra — khi đó mục 4 là thừa và tôi muốn biết.
