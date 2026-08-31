# Plan 2026-09-01 — Định cỡ lệnh thật theo NAV, và chuẩn bị đổi tài khoản đặt lệnh

Giao cho agent thực thi. Người lập plan (Claude) audit kết quả rồi mới commit/push.

---

## 0. Bối cảnh — số đo thật, không phải giả định

Đo trên DB production lúc 2026-09-01, mốc dữ liệu mới nhất `2026-08-31 23:17 UTC`
(≈ 06:17 giờ VN sáng nay). Mọi kết luận dưới đây có truy vấn kèm theo.

| | 0434221 (**đang cấu hình**) | 0434226 |
|---|---|---|
| NAV (`account_nav_snapshot`) | **5.021.459** | **200.188.000** |
| Trần lệnh = NAV × 20% | 1.004.292 | 40.037.600 |
| Sức mua AAA / HII / IJC (cp) | 666 / 532 / 632 | 9.675 / 4.841 / 10.807 |
| margin_ratio | 0% | 40–50% |
| Số dòng `account_position_snapshot` | **0** | 4.303 |
| Danh mục thật | (rỗng) | VCB 1.500, HCM 1.000, SSI 1.200, TCX 160, CAP 1.200 |

Ba sự thật rút ra:

1. **`account_buying_power` sống và tươi.** 2.982 dòng, nhịp ~5 phút, từ 15/08.
   `max_buy_qty` SSI **có** trả về (ghi chú cũ "sức mua tài khoản margin không đo
   được" chỉ đúng cho trường `purchase_power` — trường đó rỗng thật).
   `Storage.read_buying_power()` đọc bảng này, **0 caller**.

2. **Nhánh BUY thật không hề định cỡ.** `trading/real_orders.py:12` đặt
   `BUY_QTY = 100` cứng; `risk.approve()` chỉ duyệt/từ chối chứ không resize.
   Toàn bộ chuỗi NAV → `RiskManager` → `max_order_value_pct` → sức mua chảy vào
   một lệnh mua đúng 1 lô. Với 0434226 thì đó là 100 trên sức mua 10.807.
   Nhánh paper (`engine/logic.py:69`) thì ngược lại — nó gọi `approve_sized()`.

3. **`config.symbols = [HII, IJC, AAA]` không giao với danh mục thật của 0434226**
   (VCB/HCM/SSI/TCX/CAP). Nên đổi tài khoản **một mình nó** không làm nhánh SELL
   chạm được cổ phiếu thật. Nhưng điều ngược lại là một rủi ro chìm thật sự: chỉ
   cần ai đó thêm `VCB` vào `symbols`, một crossover "bear" sẽ sinh lệnh bán
   **1.500 VCB thật** mà không có bước nào nói ra điều đó.

Đã kiểm và **không** phải vấn đề: `account_sync_log` có dòng cho cả 2 tài khoản,
nên chuông 2D (`heartbeat_check.py`, commit `ebfec3c`) đang đúng — 0434221 là
"đã đồng bộ, danh mục rỗng", không phải "chưa từng đồng bộ".

---

## 1. Giả định (nêu ra để bị phản bác, không giấu)

1. `real_trading_enabled` giữ nguyên `false` trong suốt task. **Agent không được
   bật, kể cả tạm thời để thử.**
2. Không sửa `config/config.yaml`. Việc đổi `real_order_account` là quyết định
   của chủ dự án, không phải của agent — task 2 chỉ dựng rào chắn và bằng chứng.
3. Lô giao dịch = 100 cp (HOSE/HNX). Giá tính bằng VND/cp.
4. Chiến lược sinh crossover vẫn là `SmaCrossStrategy` (`engine/main.py:71`).
5. Ngưỡng "dữ liệu cũ" cho sức mua lấy **15 phút**, cùng lý lẽ với chuông 2A/2D:
   nhịp đồng bộ đo được là ~5 phút, 15 = 3× nhịp. Nếu agent đo lại thấy nhịp
   khác, **báo cáo trước khi tự đổi số**.

---

## 2. Task 1 — Lệnh BUY thật định cỡ theo NAV, trần cứng là sức mua SSI

### Phạm vi phẫu thuật

**Được sửa:** `trading/real_orders.py`, `trading/storage/db.py` (chỉ
`read_buying_power`), `trading/engine/main.py` (chỉ chỗ truyền tham số vào
`handle_crossover`), `trading/risk.py` (chỉ docstring `approve_sized`),
`tests/test_real_orders.py`, `tests/test_storage.py`.

**KHÔNG được đụng:** `engine/logic.py`, `backtest.py`, `paper_broker.py`,
`collector/*`, `config/config.yaml`, `schema.sql`, phần thân thuật toán trong
`approve_sized()`.

### Ràng buộc quan trọng nhất

`approve_sized()` đã chứa đúng phép toán cần dùng (ATR sizing + trần 20%).
**Tái dùng nó, tuyệt đối không chép lại công thức sang `real_orders.py`.** Đây là
cái bẫy đã sập hai lần trong repo này — commit `4ea4c8d` sinh ra vì "một công
thức tồn tại ở hai bản, tính trên hai tập bar khác nhau". Docstring hiện tại của
`approve_sized` ghi *"KHÔNG dùng cho real_orders.py"*; đó là quyết định cũ đang
được thay đổi có chủ ý — sửa dòng docstring đó cho khớp thực tế mới, đừng để lại
lời chú thích nói ngược.

Trần sức mua áp **sau** `approve_sized`, trong `real_orders.py`:

```
qty = min(qty_from_approve_sized, max_buy_qty)  ->  làm tròn xuống bội 100
```

### Các bước, mỗi bước kèm cách kiểm chứng

1. **`Storage.read_buying_power` trả thêm mốc thời gian.** Đổi kiểu trả về thành
   `(max_buy_qty, max_sell_qty, margin_ratio_pct, ts) | None`. Hàm này đang 0
   caller nên đổi chữ ký là an toàn — chạy `gitnexus_impact` để tự xác nhận điều
   đó thay vì tin plan.
   → *Kiểm chứng:* test trong `tests/test_storage.py` ghi 2 dòng cùng
   `(account, symbol)` khác `ts`, đọc ra phải là dòng mới nhất **kèm đúng `ts`**.

2. **Fail-safe khi không có/cũ sức mua.** Trong `handle_crossover`, nhánh BUY:
   không có dòng nào → từ chối lệnh + `alert("CRITICAL", ...)`; `ts` cũ hơn 15
   phút → từ chối + `alert("CRITICAL", ...)`. Đi theo đúng khuôn mẫu fail-safe đã
   chốt cho NAV ở `engine/main.py:122-136` (thiếu dữ liệu ⇒ từ chối, **không** rơi
   về giá trị "cho đỡ gắt").
   → *Kiểm chứng:* 2 test, mỗi test khẳng định (a) không có pending order nào
   được tạo, (b) alert phát ra đúng mức CRITICAL. Đồng hồ phải tiêm được vào test
   — **không** gọi `datetime.now()` trần trong hàm.

3. **Định cỡ.** BUY: gọi `risk.approve_sized(signal, bar.close, atr, ...)` rồi
   kẹp trần `max_buy_qty`. `atr` lấy từ `strategy.last_atr(bar.symbol)`; hiện
   `handle_crossover` không nhận `strategy` — truyền `atr` (một `float | None`)
   vào từ closure `on_real_crossover` ở `engine/main.py:251`, **đừng** kéo cả
   object strategy vào `real_orders.py`.
   → *Kiểm chứng:* test với `qty_atr=1000, qty_cap=800, max_buy_qty=550` phải ra
   **500** (min rồi làm tròn xuống lô), không phải 550 và không phải 800.

4. **SELL không đổi.** Nhánh "bear" vẫn dùng `sellable_qty`, không đi qua sức mua.
   → *Kiểm chứng:* test SELL cho `sellable_qty=137` vẫn ra đúng 137 kể cả khi
   `max_buy_qty=0`.

5. **Chứng minh đường BUY thật KHÔNG chết về mặt số học.** Đây là bước bắt buộc,
   không phải bước phụ: paper trading từng **không thể mua nổi trong 4 tháng** vì
   hai luật rủi ro nhân nhau thành điều kiện bất khả (SIZE-1, sửa ở `95b84d9`).
   → *Kiểm chứng:* hai test dùng **số thật trong mục 0**: NAV `5_021_459` và NAV
   `200_188_000`, giá AAA `7030`, ATR lấy từ một giá trị hợp lý ghi rõ trong test.
   Cả hai phải sinh ra `qty >= 100`. Nếu test NAV 5tr **không** ra nổi 1 lô, đó là
   phát hiện — **báo cáo, đừng nới luật cho test xanh.**

6. **Sabotage (bắt buộc, để chứng minh test có răng).** Đổi `min(...)` thành
   `max(...)` ở bước 3 → test bước 3 phải ĐỎ. Đổi ngưỡng 15 phút thành 15 ngày →
   test bước 2 phải ĐỎ. Khôi phục nguyên trạng, chạy lại cho xanh.
   → *Kiểm chứng:* dán nguyên văn output đỏ của cả hai lần phá vào báo cáo.

---

## 3. Task 2 — Rào chắn trước khi đổi `real_order_account` (KHÔNG sửa config)

Mục tiêu: khi chủ dự án đổi một dòng config, hệ thống phải **nói ra** nó vừa
được trao quyền bán những cổ phiếu thật nào. Hiện tại nó im lặng.

### Phạm vi phẫu thuật

**Được sửa:** `trading/engine/main.py` (chỉ khối khởi động, cạnh GUARD-1 ở dòng
~186-212), `tests/test_engine_main.py`.
**KHÔNG được đụng:** `config/config.yaml`, `real_orders.py`, `collector/*`.

### Các bước

1. **GUARD-3 — công bố quyền bán.** Lúc khởi động, khi `real_trading_enabled`
   là true: lấy giao của `cfg.symbols` với danh mục thật của
   `cfg.real_order_account` (`storage.read_real_positions`). Giao khác rỗng →
   `alert("WARN", ...)` liệt kê từng mã + khối lượng + `sellable_qty`, nói thẳng
   rằng engine có thể sinh lệnh BÁN số cổ phiếu này. Giao rỗng → im lặng.
   Đặt cạnh GUARD-1 và theo đúng khuôn mẫu của nó, kể cả điều kiện
   `if cfg.real_trading_enabled` (bẫy NOISE-1: cảnh báo khi trading đang tắt chỉ
   là tiếng ồn).
   → *Kiểm chứng:* 3 test — (a) giao rỗng ⇒ không alert; (b) giao có VCB 1.500 ⇒
   alert WARN chứa `VCB` và `1500`; (c) `real_trading_enabled=false` ⇒ không alert
   dù giao khác rỗng.

2. **Đối chiếu toàn tuyến với 0434226, chỉ đọc.** Với mỗi hàm khoá theo
   `account_no` mà đường lệnh thật dùng — `read_nav`, `read_real_positions`,
   `read_real_daily_pnl`, `read_real_highest_since_buy`, `has_active_pending_sell`,
   `read_position_sync_ts` — chạy thử trên DB thật với `0434226` và ghi lại kết
   quả. Mục đích: tìm hàm nào trả rỗng/None trong khi lẽ ra phải có dữ liệu.
   → *Kiểm chứng:* bảng 6 dòng trong báo cáo, mỗi dòng có truy vấn và kết quả
   nguyên văn. **Read-only tuyệt đối** — không INSERT/UPDATE/DELETE, không gọi
   API SSI.
   → *Đã biết trước, dùng để đối chiếu:* `read_real_highest_since_buy` sẽ không
   có gì cho VCB vì `real_order_fills` không chứa lệnh mua ngoài hệ thống — đó là
   hành vi đúng đã có cảnh báo ở `engine/main.py:174-185`, **không phải bug cần sửa.**

3. **Không đổi config.** Kết thúc task, báo cáo nêu rõ: đổi `real_order_account`
   sang `0434226` sẽ kéo trần lệnh từ 1.004.292 lên 40.037.600 VND (40×), và nêu
   những gì bước 2 tìm thấy. Quyết định là của chủ dự án.

---

## 4. KHÔNG giao — `SSIRestClientLegacy`

`trading/collector/backfill.py:81`, ~70 dòng, 0 caller. Docstring của chính nó
đặt điều kiện giữ: *"KHÔNG xoá tới khi Phase 4 E2E ổn định ≥2 phiên"*, và
`CLAUDE.md` vẫn ghi E2E đang chờ phiên giao dịch. Xoá nó kéo theo
`parse_daily_response`, `_f`, `_row_ts`. **Agent không được đụng vào file này.**
Gỡ nó cũng không bỏ được dependency `ssi-fc-data` — `collector/feed.py:20` (luồng
stream live) vẫn dùng.

---

## 5. Ràng buộc chung cho agent

- **Trước khi sửa bất kỳ symbol nào:** `gitnexus_impact({target, direction:"upstream"})`,
  báo cáo blast radius. Sau khi sửa: `gitnexus_detect_changes()`.
  (Nếu MCP GitNexus không kết nối được — đã xảy ra — nói rõ trong báo cáo và
  thay bằng grep toàn repo, đừng im lặng bỏ qua bước này.)
- **Không commit, không push.** Claude audit rồi mới commit.
- **Không bật `real_trading_enabled`.** Không gọi API đặt lệnh/hủy lệnh SSI.
- **Không chạy backfill**, không gửi Telegram thật.
- Giữ style code hiện có (chú thích tiếng Việt, tên biến hiện hành). Không nhân
  tiện refactor code xung quanh. Chỉ xoá import/biến do chính thay đổi này làm
  thừa; dead code có sẵn thì **báo cáo**, không tự xoá.
- Mọi dòng thay đổi phải truy ngược được về một bước cụ thể ở trên.

## 6. Tiêu chí hoàn thành

- `uv run pytest -m "not integration" -q` xanh (hiện tại: 322 passed).
- `uv run ruff check trading tests scripts` sạch.
- Output sabotage (mục 2 bước 6) dán nguyên văn — không tóm tắt thành "đã thử".
- Bảng 6 dòng của task 2 bước 2, kèm truy vấn.
- Nói rõ việc nào không làm được và vì sao. Không đoán.
