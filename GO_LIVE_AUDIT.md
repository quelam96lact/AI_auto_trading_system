# Audit go-live — 2026-08-13

Kiểm tra toàn tuyến: **lấy dữ liệu → sinh tín hiệu → đẩy lệnh lên sàn**.
Mọi kết luận dưới đây đều dựa trên code đã đọc hoặc số đo thật, không dựa vào
tài liệu cũ trong repo.

HEAD tại thời điểm audit: `2b6fd06`, nhánh `feature/data-layer`.

---

## Kết luận ngắn

**CHƯA sẵn sàng go-live.** Đường đặt lệnh thật hiện **không thể sinh ra một
lệnh nào**, vì hai lý do độc lập, mỗi lý do đủ để chặn hoàn toàn.

Tin tốt: kiến trúc an toàn (người bấm nút, không tự đặt lệnh), và cả hai lỗi
đều nằm ở cấu hình/vận hành chứ không phải thiết kế.

---

## Chặn số 1 — `real_order_capital` sai đơn vị: MỌI lệnh BUY bị từ chối

`config/config.yaml:8` đặt `real_order_capital: 21459`.
`trading/config.py:51` đọc thẳng: `float(raw["real_order_capital"])`, **không
nhân hệ số nào**. Giá trong DB là VND (VCB = 59.700).

Chạy thật bằng chính `RiskManager`:

```
real_order_capital = 21,459 VND
trần giá trị lệnh  = 4,292 VND   (max_order_value_pct = 0.20)
ngưỡng halt lỗ/ngày=   644 VND   (max_daily_loss_pct = 0.03)

VCB: BUY 100 @ 59,700 = 5,970,000 VND -> approve = False
TCB: BUY 100 @ 29,700 = 2,970,000 VND -> approve = False
HPG: BUY 100 @ 22,000 = 2,200,000 VND -> approve = False
```

Lệnh nhỏ nhất có thể (1 lô 100 cp HPG) vượt trần **512 lần**. Không có mã nào
trên HOSE/HNX rẻ tới mức lọt qua.

Con số 21459 gần như chắc chắn là **21.459 triệu đồng** viết theo đơn vị nghìn
(nếu vậy trần lệnh = 4.291.800đ, và 1 lô HPG = 2,2 triệu → được duyệt, hợp lý).

**Vì sao chưa ai phát hiện:** toàn bộ test dùng `real_order_capital=1_000_000_000.0`
(1 tỷ) hoặc `0` — xem `tests/test_real_orders.py:37`, `tests/test_confirm_real_order.py:38`,
`tests/test_engine_main.py:45`. **Không test nào chạy với giá trị thật trong
config.** `tests/test_config.py:36` có assert `== 21459` nhưng chỉ kiểm tra việc
đọc file, không kiểm tra hệ quả.

**Cần làm:** chủ dự án xác nhận số vốn thật rồi sửa `config/config.yaml`. Đây
là quyết định về tiền, không phải quyết định kỹ thuật — không ai được sửa hộ.

---

## Chặn số 2 — `account_position_snapshot` rỗng: MỌI lệnh SELL bị chặn

```sql
SELECT account_no, count(*) FROM account_position_snapshot GROUP BY 1;
-- (0 rows)
```

`trading/storage/db.py:481` `read_real_positions()` đọc bảng này. Rỗng → trả về
`{}` → trong `trading/real_orders.py:35-37`, `sellable = 0` → `return` ngay,
không bao giờ sinh lệnh SELL.

Bảng này do `trading/collector/account_sync.py::sync_account_data` ghi, chạy
trong `collector/main.py:100-103`. **Collector chưa từng chạy đủ lâu để đồng bộ
tài khoản.**

Hệ quả kép: nhánh BUY ở `real_orders.py:31` cũng dùng chính dữ liệu này để biết
"đã nắm giữ chưa". Rỗng nghĩa là hệ thống **luôn tưởng tài khoản không nắm giữ
gì** — nếu chặn số 1 được gỡ mà chặn này còn, hệ thống có thể mua trùng mã đang
có.

**Cần làm:** chạy collector một phiên đầy đủ, rồi xác minh bảng có dữ liệu
TRƯỚC khi bật `real_trading_enabled`.

---

## Rủi ro số 3 — Giao dịch thật KHÔNG có stop-loss

Đây không phải bug, mà là một đặc điểm thiết kế cần biết rõ trước khi bỏ tiền
thật vào.

- `TrailingStopManager` (ATR trailing stop, `sl_multiplier=2.0`) **chỉ được nối
  vào luồng paper** — `trading/engine/logic.py:47-54`.
- `trading/real_orders.py` chỉ phản ứng với crossover. Đường thoát duy nhất của
  một vị thế thật là **bear crossover của SMA 10/20**.
- Nếu giá sập giữa hai lần crossover, không có gì cắt lỗ.

Với bar 5 phút và SMA 20, độ trễ nhận biết đảo chiều có thể tới hàng chục phút.

**Cần làm:** hoặc chấp nhận có ý thức, hoặc nối trailing stop vào luồng thật
trước khi go-live. Đây là quyết định của chủ dự án.

---

## Rủi ro số 4 — Khởi động lại engine làm mất stop-loss của vị thế đang mở

Đây là **bug thật**, ảnh hưởng luồng paper (và sẽ ảnh hưởng luồng thật nếu
rủi ro số 3 được xử lý bằng cách nối trailing stop vào).

`TrailingStopManager._highest` là dict **thuần in-memory** (`trailing_stop.py:11`),
không lưu DB. Khi engine khởi động lại:

1. `engine/main.py:53,59` khôi phục vị thế từ DB → `broker.position_qty(sym) > 0`
2. `logic.py:48-49` gọi `trailing_stop.check(bar, atr)`
3. `trailing_stop.py:26-28` thấy `_highest` rỗng → **`return None`**
4. → stop-loss của vị thế đó bị **vô hiệu hoá vĩnh viễn**, cho đến khi vị thế
   được đóng và mở lại

Hệ thống không hề báo gì. Nó chỉ đơn giản là không còn cắt lỗ nữa.

`on_position_opened()` chỉ được gọi từ `logic.py:38` khi có BUY fill mới — nên
một vị thế khôi phục từ DB không bao giờ được đăng ký lại.

**Cần làm:** khôi phục `_highest` lúc khởi động (từ giá vào lệnh + giá cao nhất
kể từ đó), hoặc tối thiểu là cảnh báo khi có vị thế mở mà không có trailing state.

---

## Rủi ro số 5 — Sau khởi động lại, chiến lược "mù" khoảng 2 giờ

`SmaCrossStrategy._closes` cũng thuần in-memory (`sma_cross.py:24`), cần
`slow=20` bar cộng thêm 1 bar để có `prev_above` → **21 bar 5 phút ≈ 1h45'**.

Engine không nạp lịch sử từ bảng `bars` lúc khởi động. Nó chỉ dựa vào NATS phát
lại — mà consumer `engine` là **durable**, nên sau lần chạy đầu nó tiếp tục từ
vị trí cũ chứ không phát lại từ đầu.

Phiên giao dịch VN chỉ dài 4h15' (51 bar). Khởi động lại giữa phiên = mất gần
nửa phiên không có tín hiệu, **im lặng**.

**Cần làm:** nạp `slow + atr_period` bar gần nhất từ DB lúc khởi động. Không
gấp bằng 3 chặn trên nhưng nên có trước khi chạy tiền thật.

---

## Những gì ĐÃ tốt (đã kiểm chứng, không phải phỏng đoán)

| Hạng mục | Bằng chứng |
|---|---|
| Không tự động đặt lệnh | `real_orders.py:24-25` chỉ ghi DB + cảnh báo. Đặt lệnh là `scripts/confirm_real_order.py`, chạy tay, phải gõ `YES` |
| Kiểm tra sức mua trước khi đặt | `confirm_real_order.py:122-147` gọi `get_max_buy_sell_at_market_price`, huỷ lệnh nếu không đủ |
| Chặn lô lẻ | `confirm_real_order.py:84-91` từ chối BUY không chia hết 100 |
| Lệnh chờ có hạn | TTL 15 phút, tự hết hạn (`real_orders.py:11`, `engine/main.py:106-109`) |
| Cổng dry-run | `confirm_real_order.py:98` — `real_trading_enabled=false` thì không gọi API thật |
| Halt lỗ ngày sống sót qua restart | `engine/main.py:72` khôi phục từ DB |
| Không nhân đôi lệnh khi lỗi | `engine/main.py:194-199` — `term()` chứ không `nak()`, có lý do ghi rõ |
| SIGTERM thoát sạch | Đo thật: 0.44/0.43/0.47s, ExitCode 0 |
| Cảnh báo Telegram | Đã kiểm chứng end-to-end ở local, 7/7 tin tới nơi |
| Test suite | 242 passed, ruff sạch |

---

## Dữ liệu hiện tại

```
bars                 931,238 dòng   mới nhất 2026-08-07 14:55  (cũ 6 ngày)
bars_daily         2,969,304 dòng   mới nhất 2026-08-07
orders                     2 dòng   mới nhất 2026-07-15
pending_real_orders      208 dòng   TOÀN BỘ là symbol ENGT, status=expired
account_position_snapshot  0 dòng
```

`bars` cũ 6 ngày vì collector chưa chạy lại — cần backfill trước khi go-live.

**208 dòng `pending_real_orders` đều là rác từ test** (symbol `ENGT`, dòng mới
nhất sinh lúc 23:56 tối qua khi chạy integration suite). Đây đúng cùng loại vấn
đề với 26 message NATS đã sửa hôm qua: **test ghi vào bảng thật và không dọn**.
Cần cho test tự dọn.

---

## Rác trong repo

| Nhóm | Số file | Đề xuất |
|---|---|---|
| `PROMPT_EXECUTE_*.md` ở gốc | 32 | Chuyển vào `docs/prompts/` hoặc xoá — việc đã xong |
| `PLAN_*.md` ở gốc | 6 | Chuyển vào `docs/plans/` |
| `archive/` | 8 | Xoá |
| `DEPLOYMENT_READINESS.md` | 1 | **Xoá hoặc viết lại** — xem dưới |
| `scripts/spike_*.py` | 13 | Giữ (có giá trị tham khảo API SSI) nhưng nên gom vào `scripts/spikes/` |

38 file markdown nằm ngay ở thư mục gốc làm lu mờ `README.md` và `DEPLOYMENT.md`
— hai file người mới thực sự cần đọc.

### `DEPLOYMENT_READINESS.md` là rác nguy hiểm nhất

Không phải vì nó thừa, mà vì nó **khẳng định sai**:

- "Unit tests: 51/51 PASSING" → thực tế 242
- "`.env` committed to git (security risk)" → `.env` đã trong `.gitignore` từ lâu
- "Dead man's switch — ❌ missing" → đã có và đã kiểm chứng
- "CPU/Memory limits — ❌ missing" → `docker-compose.yml` đã có `mem_limit`/`cpus`
- "5432, 4222 should be internal only" → đã bind `127.0.0.1` rồi

Một người đọc file này sẽ đi sửa những thứ đã sửa rồi, và **tin rằng hệ thống
sẵn sàng hơn thực tế** — vì nó không hề nhắc tới 5 vấn đề nêu ở trên.

---

## Thứ tự đề xuất

1. **Chốt `real_order_capital`** (quyết định của chủ dự án — về tiền)
2. **Chạy collector một phiên đầy đủ**, xác minh `account_position_snapshot` có dữ liệu
3. **Quyết định về stop-loss cho lệnh thật** (rủi ro 3)
4. Sửa mất trailing stop sau restart (rủi ro 4)
5. Nạp lịch sử SMA lúc khởi động (rủi ro 5)
6. Cho test tự dọn `pending_real_orders`
7. Dọn rác repo + xoá/viết lại `DEPLOYMENT_READINESS.md`

Chỉ sau (1) và (2) mới có thể nói tới việc bật `real_trading_enabled: true`.
