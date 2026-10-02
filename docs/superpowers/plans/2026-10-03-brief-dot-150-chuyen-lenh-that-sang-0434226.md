# Brief đợt 150 — chuyển tài khoản lệnh thật sang `0434226`, và chặn hai chỗ đổi tài khoản làm hỏng

**Quyết định của chủ dự án (03/10/2026):** `real_order_account` đổi từ `"0434221"` sang `"0434226"`.
Không bàn lại quyết định này. `real_trading_enabled` **vẫn là `false`**; đợt này không bật nó.

## Bối cảnh — Claude đo ngày 03/10, 01:21–01:41, từ DB thật

| | `0434221` | `0434226` |
|---|---|---|
| Loại | tiền mặt | margin |
| NAV | 5.022.111 | **196.267.831** |
| Nợ / rút được | 0 / 5.022.111 | **27.884.169 / 0** |
| Đang giữ | không | FOX 500, PHP 1400, SSI 1540, TCX 460, VCB 1500 |
| `max_buy_qty` HPG / IJC / AAA | 233 / 703 / 653 | 3399 / 10115 / 8025 |
| `margin_ratio_pct` HPG / IJC / AAA | 0 / 0 / 0 | 50 / 50 / 40 |

Phần nối dây đã có sẵn: mọi chỗ trong `trading/` đều đọc `cfg.real_order_account`; không có số tài
khoản viết cứng. `cfg.symbols = [HPG, IJC, AAA]` **không giao** với danh mục của `0434226`, nên đường
BÁN không chạm cổ phiếu đang giữ. GUARD-3 (`engine/main.py`) sẽ cảnh báo nếu sau này hai tập giao nhau.

Hệ quả đã biết, chủ dự án đã chấp nhận (ghi vào config ở Việc 1, không phải việc của agent quyết):
- `withdrawable = 0`, nên **mọi lệnh MUA là mua bằng tiền vay ký quỹ**.
- Vốn rủi ro tăng 39 lần. Kích thước lệnh mua vẫn bị chặn bởi `MAX_REAL_BUY_QTY = 100`
  (`trading/real_orders.py`).

Claude tìm ra **hai chỗ** mà việc đổi tài khoản sẽ làm hỏng. Đó là phần việc chính của đợt này.

### Lỗ 1 — NAV âm được dùng làm vốn, không ai báo

Ngày 30/09 lúc **01:45:16**, `account_nav_snapshot` ghi `0434226` có NAV = **−39.959.000**. Cơ chế
(Claude dựng lại từ ba bảng):
- 01:40: SSI trả danh mục rỗng → CONFIRM-1 hoãn, không ghi (đúng thiết kế).
- 01:45: rỗng lần hai liên tiếp → CONFIRM-1 **xác nhận rỗng**, gọi `record_position_sync`.
- `_sync_nav` thấy danh mục rỗng → NAV = 0 − nợ 39.959.000.
- 01:50: SSI trả lại đủ 6 mã.

Engine chỉ đọc NAV **một lần lúc khởi động** (`trading/engine/main.py`, khối `nav_row =
storage.read_nav(cfg.real_order_account)`). Engine khởi động ở những giờ không cố định: các dòng NAV mà
nó đọc lúc khởi động có mốc khoảng 07:54, 15:05 và 18:12 giờ VN. Nếu nó khởi động đúng lúc dòng NAV mới nhất ≤ 0:
- nhánh `else` coi đó là NAV hợp lệ và chỉ báo **INFO** `"NAV lam real capital"`;
- `RiskManager(capital=-39.959.000)`. Ở `trading/risk.py`, `daily_pnl <= -capital * max_daily_loss_pct`
  thành `0 <= +1.198.770`, tức là **đúng**, nên engine bị dừng giao dịch thật cả ngày vì "lỗ quá ngưỡng"
  khi chưa có lệnh nào. Nó an toàn theo nghĩa không đặt lệnh, nhưng tin duy nhất báo ra lại sai lý do,
  còn tin INFO trước đó thì xác nhận NAV âm là "vốn".

Với `0434221` lỗ này vô hại: tài khoản không có nợ nên NAV không âm. Với `0434226` thì có thể xảy ra.
Cổng go-live (`scripts/check_golive_gate.py`) đã FAIL khi `nav <= 0`. Engine phải theo cùng quy tắc.

### Lỗ 2 — 5 cảnh báo Telegram vô ích mỗi lần engine khởi động

Khối khôi phục trailing stop (`engine/main.py`, vòng `for sym, rpos in
storage.read_real_positions(cfg.real_order_account).items()`) báo **WARN** cho mỗi vị thế thật không có
BUY fill trong `real_order_fills`. Khối này chạy **cả khi `real_trading_enabled=false`**. WARN được gửi
Telegram (`_NOTIFY_LEVELS = {"WARN", "CRITICAL"}`). Với `0434226`, mỗi lần engine khởi động sẽ có 5 tin
(FOX, PHP, SSI, TCX, VCB). Cả 5 tin vô nghĩa: engine không bao giờ nhận nến của các mã ngoài
`cfg.symbols`, nên trailing stop cho chúng không bao giờ được dùng. Đây đúng là cái bẫy NOISE-1.

## Việc

### Việc 1 — đổi config
`config/config.yaml`: `real_order_account: "0434226"`. Thêm chú thích ngay trên dòng, gồm:
- ngày quyết định;
- NAV hai tài khoản lúc quyết định;
- "mọi lệnh MUA dùng vay ký quỹ (withdrawable = 0)";
- "trần `MAX_REAL_BUY_QTY`";
- "danh mục đang giữ không giao `cfg.symbols`; thêm mã vào `symbols` thì kiểm GUARD-3".

Theo đúng giọng các chú thích sẵn có trong file: tiếng Việt không dấu, ngắn.

→ kiểm chứng bằng: test mới khẳng định `real_order_account` (đọc từ chính `config/config.yaml`) nằm
trong `ssi_equity_accounts`. Tài khoản không được đồng bộ thì không có NAV, và engine sẽ có capital = 0.

### Việc 2 — engine từ chối NAV ≤ 0 (Lỗ 1)
Trong khối đọc NAV của `run()`, thêm nhánh: `nav_row` có NAV `<= 0` thì xử lý **y như nhánh `None`**:
- `real_capital = 0.0`;
- báo **CRITICAL**, nêu account, giá trị NAV và `ts` của dòng đó;
- KHÔNG rơi về số dư, KHÔNG lùi tìm dòng NAV dương cũ hơn. Lùi tìm là thêm một nguồn số liệu cũ mà không
  ai kiểm. Engine khởi động lại thì đọc lại.

Không sửa `account_sync.py` trong đợt này; lỗ CONFIRM-1 chịu được hai nhịp rỗng là việc riêng.

→ kiểm chứng bằng: test mới, mô phỏng theo `test_engine_critical_and_blocks_buy_when_no_nav`
(`tests/test_engine_main.py`):
- seed một dòng NAV = **−39.959.000** (số thật), cùng số dư lớn làm bẫy như test cũ;
- chạy tới crossover bull;
- khẳng định có CRITICAL nêu NAV ≤ 0 kèm giá trị, và `pending_real_orders` cho mã test = 0.

Thêm một ca NAV = 0. Hai test cũ cho NAV cũ và NAV bình thường phải vẫn xanh.

Lưu ý, **không** thêm khẳng định "không có risk halt". Với capital = 0, phép so `0 <= -0 × 3%` vẫn đúng,
nên nhánh `None` sẵn có **cũng** sinh `"REAL risk halt: max daily loss reached"` và lưu halt cho cả
ngày. Đó là hành vi cũ, nằm ngoài phạm vi đợt này. Giá trị của Việc 2 là có một CRITICAL nói **đúng lý do**
trước tin halt. Ghi vào báo cáo danh sách alert thật mà test thu được.

### Việc 3 — chỉ khôi phục trailing stop cho mã engine giao dịch (Lỗ 2)
Trong vòng khôi phục trailing stop thật:
- **chỉ xét `sym in cfg.symbols`**; logic với các mã này giữ nguyên, kể cả WARN khi thiếu fill;
- các vị thế ngoài `cfg.symbols` thì gom thành **một** dòng **INFO** liệt kê mã và số lượng (vd
  `"vi the that ngoai cfg.symbols, engine khong quan ly"`), để nhìn thấy được mà không gửi Telegram.

Không đổi `handle_stop_touch` hay `TrailingStopManager`.

→ kiểm chứng bằng: test mới seed vị thế thật của account test gồm:
- một mã **ngoài** `cfg.symbols`, không có fill;
- một mã **trong** `cfg.symbols`, không có fill.

Khẳng định: đúng một WARN "khong tai dung duoc trailing stop", và nó là của mã trong `cfg.symbols`; mã
ngoài chỉ xuất hiện trong INFO.

### Việc 4 — chữ đã lỗi thời
Chỉ sửa chữ, không đổi logic:
- `trading/collector/main.py`, docstring `held_symbols_for_pricing`: câu "quyet dinh chon tai khoan CHUA
  chot" → nêu đã chốt `0434226` ngày 03/10. Lý do đọc mọi tài khoản vẫn đúng (NAV từng tài khoản), giữ
  nguyên.
- `trading/real_orders.py`, docstring `handle_crossover`: "tài khoản Cash" → "tài khoản
  `real_order_account`".
- `scripts/check_real_order_readiness.py`: nhãn viết cứng `"0434221 (Đang cấu hình)"` / `"0434226 (Tài
  khoản lớn)"` → nhãn "đang cấu hình" phải lấy từ `real_order_account` trong config. Giữ nguyên các truy
  vấn so sánh hai tài khoản.

**Không sửa** (chỉ liệt kê trong báo cáo): `scripts/probe_account_balance_22h.py`,
`spike_ssi_sdk_place_order.py`, `drill_place_cancel_order.py` (ví dụ trong docstring),
`rehearse_confirm_gate.py`, mặc định `"0434221"` trong `check_golive_gate.py:500` và mọi thứ dưới `docs/`.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không build/restart container. Config được build vào image (chỉ `./logs`
  được mount), nên thay đổi chỉ có hiệu lực khi **Claude** build lại engine/collector sau audit.
- **KHÔNG** bật `real_trading_enabled`, không chạy bất cứ thứ gì có `--send`, không gửi Telegram thật.
  Mọi lần chạy chạm DB thật phải chỉ đọc. Lệnh nào gọi `alert()` thì trước đó tắt gửi:
  `trading.alerts._NOTIFY_LEVELS.clear()`.
- **Chỉ sửa:**
  - `config/config.yaml` (chỉ dòng `real_order_account` và chú thích của nó);
  - `trading/engine/main.py` (chỉ hai khối: đọc NAV và khôi phục trailing stop thật);
  - `trading/collector/main.py`, `trading/real_orders.py` (chỉ docstring);
  - `scripts/check_real_order_readiness.py` (chỉ nhãn);
  - test tương ứng.

  Không đụng `account_sync.py`, `risk.py`, `real_orders.handle_*` (ngoài docstring), `alerts.py`.
- **Làm trong git worktree.** Các script theo lịch chạy thẳng từ cây làm việc và có đọc `config.yaml`.
  Chỉ chép vào repo chính khi xong. Phiên giao dịch kế tiếp là **08:00 thứ Hai 05/10**; phải chép trước
  mốc đó, nếu không thì dừng và báo lại.
- **GitNexus trước khi sửa:** `npx --no-install gitnexus impact run --repo AI_auto_trading_system` (MCP
  thường chết). `run` gần như chắc chắn ra HIGH vì là điểm vào engine. Báo con số, rồi giữ phạm vi trong
  đúng hai khối đã nêu. Sau khi sửa thì chạy `detect_changes`; nếu nó báo 0 thay đổi, chạy `npx gitnexus
  analyze` rồi đo lại.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng. Bộ test integration cần `nats-test` (xem CLAUDE.md), không dùng NATS thật.

## Tiêu chí hoàn thành

1. **Diff khớp phạm vi.** So AST theo hàm (`HEAD` với bản mới):
   - `trading/engine/main.py`: chỉ `run` khác;
   - `real_orders.py` và `collector/main.py`: chỉ docstring khác. So AST **bỏ docstring** phải ra giống
     hệt.

   Dán kết quả.
2. **Phá thử.** Mỗi lần ghi nguyên văn dòng đỏ, khôi phục, rồi đối chiếu hash:
   - bỏ nhánh NAV ≤ 0 → test NAV âm đỏ;
   - đổi `<= 0` thành `< 0` → ca NAV = 0 đỏ;
   - bỏ lọc `cfg.symbols` → test trailing stop đỏ (thừa một WARN);
   - đặt `real_order_account: "0434228"` (tài khoản phái sinh) trong một **bản sao** config mà test đọc →
     test Việc 1 đỏ. Test phải nhận đường dẫn để làm được việc này; **không phá `config/config.yaml`
     thật**.
3. **Đọc thật, chỉ đọc**, từ DB thật (`127.0.0.1`, không dùng `localhost`). In:
   - dòng NAV mới nhất của `0434226`;
   - vị thế thật của nó;
   - giao giữa vị thế và `cfg.symbols` (kỳ vọng rỗng);
   - `max_buy_qty` mới nhất cho ba mã.

   Dán nguyên văn, kèm giờ đo.
4. `uv run python scripts/check_real_order_readiness.py` chạy được, và nhãn "đang cấu hình" nằm ở
   `0434226`. Nếu script có đường gửi Telegram thì tắt trước khi chạy.
5. `ruff` sạch. `uv run pytest -q` ≥ **1.751 passed** cộng số test mới, 0 failed.

## Báo cáo

Ghi vào `docs/superpowers/research/2026-10-03-dot-150-chuyen-lenh-that-sang-0434226.md`:
- số đo nguyên văn;
- kết quả GitNexus impact;
- danh sách chỗ còn ghi `0434221` mà agent không sửa;
- brief sai ở đâu;
- cái gì không kiểm được.
