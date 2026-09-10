# Brief đợt 32 — Dọn hai chỗ "một công thức, hai bản"

Ngày giao: 10/09/2026, 20:15.
Base: `a1d8932` (main, cây sạch).
Người giao: Claude (planner/auditor).

**Thứ tự:** chạy sau brief đợt 29 (bốn task ngày 11/09). Không xung đột với đợt 30/31 đã
xong. Brief này nhỏ — hai việc, cả hai đều là dọn dẹp, **không thêm tính năng nào**.

---

## 0. Vì sao hai việc này đáng làm bây giờ

Cả hai đều không gây lỗi hôm nay. Cả hai đều sẽ gây lỗi **im lặng** vào đúng lúc ta ít ngờ
nhất, và cả hai vẫn còn rẻ để sửa. Đó là toàn bộ lý do.

Dự án này có nguyên tắc **"một công thức, một chỗ"**. Hai chỗ dưới đây vừa phá nó — và cả hai
đều mới sinh ra trong ba đợt gần nhất, tức là vết nứt còn mới, chưa ai xây thêm lên trên.

---

## 1. Hai việc

| Task | Việc | Rủi ro nếu để nguyên |
|---|---|---|
| 1 | Bỏ số `5` gán cứng khi tính `lag_ms` phía collector | số đo nói dối mà không ai biết |
| 2 | Đưa câu SQL thô trong `real_orders.py` về tầng `Storage` | phá ranh giới tầng, thành tiền lệ |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB.
- Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.
- **Không đổi hành vi.** Đây là hai thay đổi **thuần cấu trúc**: sau khi sửa, hệ thống phải
  làm **đúng y hệt** những gì nó đang làm. Không sửa tiện tay thứ gì khác.
- **Không sửa** `BarLatch`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/logic.py`, `config/config.yaml`.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` copy từ terminal.
- **Không bịa tiêu chí.** Nếu thấy brief thiếu hoặc sai, **hỏi lại** — đừng tự thay bằng
  tiêu chí khác (đợt 29 đã làm thế một lần).

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_impact` cho `persist_bars` và
`handle_crossover`; `gitnexus_detect_changes()` khi xong. MCP `gitnexus` gần đây hay timeout —
**không kết nối được thì ghi rõ trong báo cáo**, đừng lặng lẽ bỏ qua rồi sửa code.

---

## Task 1 — Bỏ số `5` gán cứng khi tính `lag_ms`

### 1.1. Hiện trạng

Đợt 31 thêm `lag_ms` vào hai phía. Phía engine làm đúng, phía collector gán cứng:

```python
# trading/engine/main.py  — ĐÚNG
bar_close_ts = bar.ts + timedelta(minutes=cfg.bar_interval_minutes)

# trading/collector/main.py — GÁN CỨNG
max_close_ts = max(b.ts for b in bars) + timedelta(minutes=5)
```

Cùng một công thức ("khung này đóng lúc nào"), hai bản, một bản không đọc cấu hình.

### 1.2. Vì sao đáng sửa dù hôm nay nó cho kết quả đúng

`bar_interval_minutes` hiện là `5`, nên hai bản trùng khớp và không ai thấy gì. Nếu đổi khung
nến — thứ hoàn toàn có thể xảy ra, tôi đã nêu nó trong brief 31 §5 như một hướng giảm độ trễ
thật — thì `lag_ms` phía collector **vẫn chạy, vẫn ghi ra số, và số đó sai**.

Đây là loại hỏng tệ nhất: không nổ, không cảnh báo, chỉ âm thầm cho số sai. Mà `lag_ms` chính
là con số ta vừa dựng lên **để ra quyết định về độ trễ**.

### 1.3. Việc cần làm

`persist_bars` hiện là `persist_bars(storage, pub, bars)` (`collector/main.py:76`) và không
nhận `cfg`. Nhưng **không cần `cfg`** — `BarLatch` đã giữ sẵn giá trị đúng:

- `BarLatch.__init__` nhận `interval_seconds` và lưu `self.interval` (một `timedelta`).
- Ở `run()` nó được dựng bằng `BarLatch(interval_seconds=cfg.bar_interval_minutes * 60, ...)`.
- **Cả hai chỗ gọi `persist_bars` đều đã có `latch` trong tầm:**
  - `collector/main.py:160` — trong `on_stream_message`, `latch` là biến đóng của
    `make_stream_message_handler`.
  - `collector/main.py:197` — trong `housekeeping_tick`, `latch` là tham số.

Thêm một tham số khoảng thời gian cho `persist_bars` và truyền `latch.interval` từ cả hai chỗ
gọi. Dùng thẳng `timedelta` sẵn có của latch — **không** chuyển qua lại giữa phút và giây,
mỗi lần chuyển đổi là một chỗ để sai.

Đặt tham số **có giá trị mặc định** bằng đúng hành vi hiện tại, để mọi test cũ gọi
`persist_bars(storage, pub, bars)` không vỡ.

**Chỉ sửa `trading/collector/main.py`.**

### 1.4. Kiểm chứng

1. Test: `bar_interval_minutes = 5` → `lag_ms` giữ nguyên giá trị như trước khi sửa (không
   đổi hành vi).
2. Test: latch dựng với khoảng **1 phút** → `lag_ms` tính theo 1 phút, **không** theo 5.
   Đây là bài test mà code hiện tại **trượt** — viết nó trước, thấy nó đỏ, rồi mới sửa.
3. Test: `persist_bars` gọi theo kiểu cũ (không truyền khoảng) vẫn chạy đúng như cũ.
4. Xác nhận **cả hai** chỗ gọi (`:160` và `:197`) đều truyền `latch.interval` — nêu số dòng
   sau khi sửa.
5. Suite đầy đủ pass, ruff sạch, cổng cứng VN khớp từng chữ số.

---

## Task 2 — Đưa câu SQL thô về tầng `Storage`

### 2.1. Hiện trạng

Đợt 30 thêm lá chắn NAV, và nó nhúng thẳng SQL vào `trading/real_orders.py:37-43`:

```python
        with storage.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT ON (account_no) account_no, nav "
                "FROM account_nav_snapshot "
                "ORDER BY account_no, ts DESC"
            ).fetchall()
```

Tôi quét toàn bộ package `trading/`: **đây là câu SQL duy nhất nằm ngoài `trading/storage/`.**
Mọi code sản xuất khác đều đi qua phương thức có tên của `Storage` —
`read_real_positions`, `read_buying_power`, `read_position_sync_ts`, `read_positions`. Các file
dùng `storage.conn()` trực tiếp đều nằm trong `scripts/`, nơi đó là chuyện bình thường.

### 2.2. Vì sao đáng sửa

Tầng `Storage` tồn tại để SQL nằm một chỗ. Một ngoại lệ không giết ai — nhưng nó là **viên
gạch đầu tiên**, và lần sau người viết code sẽ thấy có tiền lệ. Sửa lúc còn đúng một chỗ thì
mất năm phút; sửa lúc đã có mười chỗ thì thành một đợt refactor.

### 2.3. Việc cần làm

Thêm vào `trading/storage/db.py` một phương thức đọc, đặt cạnh các phương thức đọc tài khoản
sẵn có (quanh `read_buying_power`, `read_position_sync_ts`), **theo đúng style của chúng**:
docstring một hai dòng nói rõ trả về gì, `with self.conn() as c:`, trả kiểu Python thuần.

Trả về ánh xạ `account_no -> nav` của bản ghi **mới nhất mỗi tài khoản** — đúng ngữ nghĩa câu
SQL hiện tại, không đổi.

Rồi trong `real_orders.py`, thay khối `with storage.conn()` bằng lời gọi phương thức đó. Phần
so sánh tỷ lệ, ngưỡng, và nội dung `alert` **giữ nguyên không đổi một chữ**.

Sau khi thay xong, `import` nào trong `real_orders.py` trở nên thừa **do chính thay đổi này**
thì xoá (được phép theo nguyên tắc 3). Không xoá gì khác.

**Chỉ sửa `trading/real_orders.py` và `trading/storage/db.py`.**

### 2.4. Kiểm chứng

1. Năm test lá chắn NAV của đợt 30 **vẫn pass nguyên vẹn, không sửa một dòng nào**. Đây là
   tiêu chí quan trọng nhất: thay đổi thuần cấu trúc thì test hành vi không được động tới.
2. Test mới cho phương thức `Storage`: nhiều bản ghi nhiều mốc thời gian cho cùng một tài
   khoản → chỉ trả về bản **mới nhất**.
3. Test: bảng rỗng → trả về ánh xạ rỗng, **không nổ**.
4. `grep` xác nhận trong `trading/` (ngoài `trading/storage/`) **không còn** câu `SELECT`,
   `INSERT`, hay `UPDATE` nào. Dán kết quả grep.
5. Suite đầy đủ pass, ruff sạch, cổng cứng VN khớp từng chữ số.

---

## 3. Báo cáo

Ngắn, đủ, đúng thứ tự. **Đừng dán toàn văn `git diff`** — dán `--stat` và con số.

1. `gitnexus_impact` cho `persist_bars` và `handle_crossover` (hoặc ghi rõ MCP timeout).
2. `git diff --stat`.
3. Task 1: kết quả năm tiêu chí. **Nói rõ bài test 1-phút đã đỏ trước khi sửa** — nếu nó xanh
   ngay từ đầu thì bài test đó sai, không phải code đúng.
4. Task 2: kết quả năm tiêu chí, kèm output `grep` của mục 4.
5. Ba dòng: số test pass, ruff, cổng cứng VN.
6. `git status --short`.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

**Không commit, không push.**

---

## 4. Điều KHÔNG thuộc phạm vi

- **Không** đổi `bar_interval_minutes`. Task 1 chỉ làm cho code **đọc** giá trị đó cho đúng;
  việc có đổi khung nến hay không là quyết định của chủ dự án (brief 31 §5).
- **Không** đổi ngưỡng `NAV_DISCREPANCY_RATIO_THRESHOLD`, không đổi nội dung cảnh báo, không
  đổi việc lá chắn chỉ nói mà không chặn lệnh.
- **Không** gom lô ghi DB. Đợt 31 Task 3 đã đo và kết luận ngưỡng cần can thiệp là từ ~100 mã;
  hiện có 3 mã. Chưa tới lúc.
- Ba việc lớn còn treo vẫn là **quyết định của chủ dự án**, không phải việc agent: Q-1 (không
  chiến lược nào có edge đo được), Q-2 (`0434221` NAV 5.021.712 vs `0434226` NAV 197.517.988),
  và cửa xác nhận lệnh thật 15 phút với 9/9 lệnh đã hết hạn.
