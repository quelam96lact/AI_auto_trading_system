# Kế hoạch: bảng ghi nhận lần đồng bộ vị thế + timeout ngắn cho đọc token

Ngày giao: 2026-08-14 sáng. Nhánh: `feature/data-layer`. Base: `85e75f4`.

**KHÔNG commit, KHÔNG push.** `gitnexus_detect_changes` khi xong.

Hai quyết định của chủ dự án sáng nay: phần 1 chọn **phương án B**; phần 2 **làm**.

---

## CẢNH BÁO HIGH RISK — đọc kỹ trước khi viết dòng nào

`gitnexus_impact` trên `Storage.read_real_positions`: **HIGH**, 4 caller trực
tiếp:

```
scripts/confirm_real_order.py:confirm     <-- SCRIPT ĐẶT LỆNH LÊN SÀN
trading/real_orders.py:handle_crossover
trading/real_orders.py:handle_stop_touch
trading/engine/main.py:run
```

`confirm_real_order.py` dùng kết quả của hàm này để quyết định **bán bao nhiêu
cổ phiếu thật**. Một lỗi ở đây không làm test đỏ — nó bán sai số lượng trên
sàn.

**Vì vậy: nếu bạn thấy mình đang đoán, dừng lại và hỏi.**

## BỐI CẢNH VẬN HÀNH

Stack thật đang chạy, phiên giao dịch mở lúc **9:00**.

- **KHÔNG** restart/rebuild container.
- **KHÔNG** đụng `config/config.yaml`.
- Chạy `pytest` an toàn (đã tách hạ tầng từ `51eb353`); nhớ
  `docker compose --profile test up -d nats-test` nếu nó chưa chạy.

---

# PHẦN 1 — bảng `account_sync_log`

## Vấn đề (đã đo, không suy luận)

`save_account_positions` có `if not positions: return` (`db.py:367`).
`read_real_positions` đọc `ts = (SELECT max(ts) ...)` (`db.py:595`).

Bảng là chuỗi ảnh chụp: mỗi lần đồng bộ ghi một lô dòng cùng `ts`, bên đọc lấy
lô mới nhất. Cách này xử lý đúng việc "một mã đã bán hết" — ảnh chụp mới không
chứa mã đó nên nó biến mất.

Nhưng khi danh mục về **rỗng hoàn toàn**, không dòng nào được ghi, `max(ts)`
đứng nguyên ở lần cũ:

```
10:00  đồng bộ: VCB 1500       -> ghi 1 dòng ts=10:00
10:30  bán sạch VCB
10:35  đồng bộ: rỗng           -> KHÔNG ghi gì
       max(ts) vẫn 10:00 -> hệ thống vẫn thấy "VCB 1500", VĨNH VIỄN
```

Hai kiểu hại ngược chiều: nhánh BUY tưởng đang nắm giữ → bỏ qua tín hiệu mua,
im lặng. Nhánh SELL và `handle_stop_touch` tưởng có 1500 cp khả dụng → sinh
lệnh bán cổ phiếu không tồn tại.

Gốc rễ: **"không có dòng nào" mang hai nghĩa** — chưa đồng bộ bao giờ, hoặc đã
đồng bộ và rỗng. Phải ghi lại *sự kiện đồng bộ* mới phân biệt được.

## Thiết kế đã chốt (phương án B)

### 1. Bảng mới trong `trading/storage/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS account_sync_log (
  account_no text PRIMARY KEY,
  ts         timestamptz NOT NULL
);
```

**Chỉ lưu lần gần nhất, không lưu lịch sử.** Lịch sử nhịp đồng bộ đã có sẵn ở
`account_balance_snapshot` (cùng chu kỳ 5 phút); thêm một bảng tăng trưởng vô
hạn nữa là thừa.

### 2. `Storage.record_position_sync(account_no, ts)` — upsert

```sql
INSERT INTO account_sync_log (account_no, ts) VALUES (%s, %s)
ON CONFLICT (account_no) DO UPDATE SET ts = EXCLUDED.ts
```

### 3. `Storage.read_position_sync_ts(account_no) -> datetime | None`

### 4. `_sync_positions` gọi sau khi lấy dữ liệu THÀNH CÔNG

```python
positions = await portfolio.get_equity_positions(account_no)
rows = [...] if positions else []
storage.save_account_positions(account_no, ts, rows)   # tự no-op khi rỗng
storage.record_position_sync(account_no, ts)           # LUÔN chạy khi fetch OK
```

**Điểm mấu chốt:** `record_position_sync` phải chạy **cả khi danh mục rỗng**,
và **tuyệt đối không chạy khi fetch ném exception** — ghi một lần đồng bộ chưa
từng xảy ra còn tệ hơn không ghi.

Giữ nguyên guard `positions is None` về mặt ý nghĩa (rỗng là hợp lệ, không
alert, không ném) — chỉ đổi chỗ để `record_position_sync` vẫn chạy.

### 5. `read_real_positions` dùng mốc sync

```python
sync_ts = read_position_sync_ts(account_no)
if sync_ts is None:
    # DỮ LIỆU CŨ: chưa có bản ghi sync nào (bảng vừa thêm). Giữ NGUYÊN hành vi
    # cũ max(ts) để không đổi kết quả đột ngột cho dữ liệu đã có, và tự khỏi
    # sau lần đồng bộ đầu tiên (5 phút).
    -> như cũ
else:
    -> positions WHERE ts = sync_ts AND quantity > 0
```

`_sync_balance` và `_sync_positions` dùng **chung một `ts`** (`sync_account_data`
tính `now` một lần rồi truyền xuống), nên `ts = sync_ts` khớp chính xác.

Nhánh fallback là **có chủ đích**, không phải phòng xa thừa: nó giữ cho hành vi
không đổi đột ngột với dữ liệu đang có trong DB sản xuất.

## Kiểm chứng phần 1 (dán output THẬT)

1. **Ca gãy — trọng tâm của cả việc này.** Đồng bộ có VCB 1500 → đồng bộ lần
   hai với danh mục **rỗng** → `read_real_positions` trả **`{}`**.
   → **RED bắt buộc:** bỏ `record_position_sync` đi → test này phải FAIL (trả
   về VCB 1500 như cũ). Khôi phục → PASS.
2. **Không phá ca thường:** đồng bộ có VCB+HPG → đồng bộ chỉ còn VCB →
   `read_real_positions` trả đúng VCB, không còn HPG.
3. **Fallback dữ liệu cũ:** có dòng trong `account_position_snapshot` nhưng
   **không** có dòng `account_sync_log` → vẫn trả đúng như hành vi cũ.
4. **Không ghi khi fetch hỏng:** `get_equity_positions` ném → `account_sync_log`
   **không** có dòng mới cho tài khoản đó.
5. Đường tiền: chạy đủ test của `confirm_real_order.py` và `real_orders.py`,
   dán số. Không test nào được đổi kỳ vọng để "cho qua" — nếu một test cũ đỏ,
   **dừng và báo cáo**, đừng sửa test.

---

# PHẦN 2 — timeout ngắn khi đọc token

## Đính chính so với những gì tôi nói hôm qua

Tôi từng nói chỗ 30 giây nằm trong `sync_account_data` và đẩy lùi heartbeat.
**Sai.** `housekeeping_tick` gọi `storage.beat(timeout=5)` ngay đầu tick; DB
chết thì tick hỏng sau 5 giây và **không bao giờ chạy tới** `sync_account_data`.

Bốn dòng `after 30.00 sec` trong log đến từ `feed.py:163` — vòng kết nối lại
của luồng dữ liệu, một coroutine riêng, gọi `ensure_authenticated` →
`load_ssi_token()` → đọc DB với timeout mặc định 30 giây.

Nó ảnh hưởng **tốc độ nối lại stream**, không phải heartbeat. Và ngay cả ở đó
nó cũng không phải số hạng lớn nhất: `feed.py:174` có backoff nhân đôi tới trần
**60 giây**.

Chủ dự án đã biết điều này và vẫn chọn làm — đây là một dòng, cùng khuôn mẫu
đã dùng cho `beat()`.

## Phải làm

- `Storage.load_ssi_token(timeout: float | None = None)` — mặc định `None` giữ
  nguyên hành vi cho **mọi caller cũ**.
- `ensure_authenticated` (`ssi_auth.py:41`) truyền `timeout=5`.

## Kiểm chứng phần 2

1. Test: `load_ssi_token()` không truyền → `conn()` nhận `timeout=None`;
   truyền 5 → nhận 5. (Cùng khuôn mẫu test đã có cho `conn`/`beat`.)
2. `ensure_authenticated` gọi `load_ssi_token` với `timeout=5`.

**KHÔNG** đổi giá trị mặc định của pool. **KHÔNG** đụng backoff trong
`feed.py` — đó là thay đổi khác, chưa đo, chưa giao.

---

# Ràng buộc chung

- Sửa: `trading/storage/schema.sql`, `trading/storage/db.py`,
  `trading/collector/account_sync.py`, `trading/collector/ssi_auth.py`, và test.
- **KHÔNG** sửa `scripts/confirm_real_order.py`, `trading/real_orders.py`,
  `trading/risk.py`, `config/config.yaml`.
- **KHÔNG** bật `real_trading_enabled`.

# Toàn bộ

- `uv run pytest -q` → ≥ 273 + test mới.
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán risk + danh sách file.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Đặc biệt mục 5 phần 1 (fallback khi chưa có bản ghi sync):
nếu bạn cho rằng giữ hành vi cũ ở đó là sai — rằng "chưa biết" nên trả `{}` chứ
không phải trả vị thế cũ — **nói ra**. Đó là lựa chọn giữa hai kiểu sai và tôi
có thể đã chọn nhầm hướng.
