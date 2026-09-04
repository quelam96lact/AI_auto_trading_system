# Brief giao việc — đợt tối 04/09 (B1, B2, C-a, H)

Viết 02:30 ngày 04/09. Đây là **brief thi hành**, giao thẳng cho agent. Các plan
khác đêm nay là phân tích; file này là cái để làm.

**KHÔNG BẮT ĐẦU TRƯỚC 14:45 ngày 04/09.** Lý do ở mục 0.2 — không phải thủ tục.

---

## 0. Luật chung — đọc hết trước khi gõ dòng đầu tiên

### 0.1 Vai trò

Bạn **viết code và tự kiểm chứng**. Bạn **không commit, không push**. Claude
audit rồi mới commit. Báo cáo xong thì dừng, đừng tự dọn dẹp thêm.

### 0.2 Vì sao không được bắt đầu trước 14:45

Cả bốn gói đều chạm `trading/` ⇒ phải dựng lại image. Phiên 04/09 là **phép đo
thực địa duy nhất** của gói A (bản sửa thời-gian-thị-trường ngày 03/09): mốc
13:00 điện thoại có kêu giả nữa không. Dựng lại image trước hoặc trong phiên là
trộn hai biến vào một phép đo và mất cả hai.

### 0.3 An toàn — không có ngoại lệ

- `real_trading_enabled` giữ **`false`**. Không được bật, kể cả tạm thời.
- Không gọi API đặt lệnh / huỷ lệnh của SSI. Data API chỉ đọc.
- **Không in giá trị bí mật** ở bất cứ đâu (log, báo cáo, test). Được nêu tên
  biến, không được nêu giá trị.
- `.env` không nằm trong git — không sửa, không commit.
- Không `TRUNCATE`, không `DROP`, không xoá dòng. Chỉ nạp thêm.
- **Không sửa `config/config.yaml`** — nằm ngoài tay agent (xem mục 6).

### 0.4 Phạm vi phẫu thuật

- Mỗi gói có danh sách file **được sửa** và **không được đụng**. Mọi dòng bạn
  đổi phải truy ngược được về đúng gói của bạn.
- Giữ nguyên style code hiện có. Không "tiện thể" refactor xung quanh.
- Chỉ được xoá import/biến/hàm mà **chính thay đổi của bạn** làm thừa. **Không**
  xoá dead code có từ trước.
- Phát hiện gì ngoài phạm vi thì **báo cáo, không tự sửa**.

### 0.5 GitNexus

Chỉ số đang cũ (lần cuối: `ebfec3c`). Chạy `npx gitnexus analyze` trước.

Trước khi sửa **bất kỳ** hàm/lớp nào: `gitnexus_impact({target: "<tên>",
direction: "upstream"})`, và **ghi bán kính ảnh hưởng vào báo cáo**. Nếu ra
HIGH/CRITICAL thì **dừng và báo**, đừng tự đi tiếp.

### 0.6 Nền test — số mới, đừng dùng số cũ

```
uv run pytest -m "not integration" -q   ->  393 passed
uv run pytest -m integration -q          ->   97 passed   (cần: docker compose --profile test up -d nats-test)
```

**Cả hai đều phải xanh.** Tổng nền = **490, 0 đỏ**. Bộ integration chạy 16 giây;
bỏ qua nó là cách một test đỏ sống ba ngày mà không ai thấy (đã xảy ra tuần này).

### 0.7 Bốn gói KHÔNG dùng chung file — chạy song song được

| Gói | File sản phẩm |
|---|---|
| B1 | `trading/strategy.py`, `trading/strategies/*` |
| B2 | `trading/alerts.py`, 4 script trong `scripts/` |
| C-a | `trading/risk.py` |
| H | `trading/storage/db.py` |

Nếu chạy nhiều agent song song: **tuyệt đối không chạm file của gói khác**, kể
cả khi thấy nó sai.

---

## 1. GÓI B1 — hợp đồng chiến lược

### 1.1 Sự thật đã đo

`trading/strategy.py` khai `Strategy` Protocol gồm đúng ba hàm: `on_bar`,
`last_crossover`, `last_atr`. Nhưng engine gọi thêm **hai hàm nữa mà Protocol
không khai**: `warmup_bars` (`engine/main.py:81,82,86`) và `compute_crossover`
(`engine/main.py:91`).

Ma trận thật của năm chiến lược:

| Chiến lược | `on_bar`+`last_atr` | `last_crossover` | `warmup_bars` | `compute_crossover` | Nạp vào engine |
|---|---|---|---|---|---|
| `sma_cross` | ✓ | ✓ | ✓ | ✓ | được |
| `daily_breakout` | ✓ | ✓ | ✓ | ✓ | được |
| `octopus_pullback` | ✓ | **✗** | ✓ | ✓ | **chết** ở `logic.py:44` |
| `momentum_breakout` | ✓ | ✓ | **✗** | ✓ | chết ở `main.py:81` |
| `momentum_rsi` | ✓ | **✗** | **✗** | ✓ | chết hai chỗ |

`octopus_pullback` **đang nằm trong `STRATEGIES`** (`trading/backtest.py:290`),
backtest sạch, nhưng nạp vào engine sẽ `AttributeError` ngay bar đầu tiên.

### 1.2 Việc

1. Bổ sung `warmup_bars` và `compute_crossover` vào `Strategy` Protocol cho khớp
   thứ engine thật sự gọi.
2. Thêm `last_crossover` cho `octopus_pullback`.
3. **Conformance test:** mọi mục trong `STRATEGIES` phải thoả hợp đồng mà sổ
   đăng ký đó hứa.
4. Với `momentum_breakout` và `momentum_rsi`: **BÁO CÁO, ĐỪNG TỰ CHỌN.** Hai
   hướng đều hợp lý — bổ sung hàm thiếu, hay tuyên bố rõ chúng chỉ dùng cho
   backtest và không thuộc sổ đăng ký engine. Đây là quyết định thiết kế, không
   phải việc dọn dẹp.

### 1.3 Ràng buộc cứng — hai hợp đồng, không phải một

`derivative_backtest.py:57` chỉ dùng `compute_crossover` + `qty`. **Ép cả năm
chiến lược vào khuôn cổ phiếu sẽ phá đường phái sinh.** Các chiến lược momentum
**không phải** dead code — chúng có ba file test riêng.

### 1.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Conformance test | **đỏ trước, xanh sau** — dán nguyên văn cả hai output. Nếu nó xanh ngay từ đầu thì nó không kiểm gì cả |
| 2 | `octopus_pullback` nạp được engine | test dựng nó và đi đúng đường `engine/logic.py` bar đầu ⇒ không `AttributeError` |
| 3 | Đường phái sinh nguyên vẹn | `pytest tests/test_derivative_backtest.py -q` xanh; hợp đồng phái sinh **không** bị ép theo khuôn cổ phiếu |
| 4 | Không hồi quy | cả hai bộ, nền 393 + 97 |
| 5 | Lint | `ruff check trading tests scripts` sạch |

### 1.5 Phạm vi

- **Sửa:** `trading/strategy.py`, `trading/strategies/*`, `tests/`.
- **Không đụng:** `trading/engine/*`, `trading/backtest.py` (kể cả nội dung
  `STRATEGIES`), `config/config.yaml`, `trading/risk.py`, `trading/alerts.py`,
  `trading/storage/db.py`.

### 1.6 Việc đã bị RÚT khỏi B1 — đừng làm

Trường chọn chiến lược trong `Config` + đọc nó ở `engine/main.py:71`: **hoãn có
chủ ý.** Không chiến lược nào trong repo có lợi thế đo được, nên chưa có gì để
chọn. Xây cơ chế chọn trước khi có ứng viên là thêm rủi ro runtime thật để đổi
lấy khả năng chưa ai cần. Nếu bạn thấy cần nó để hoàn thành B1, **dừng và báo** —
đó là dấu hiệu tôi hiểu sai phạm vi.

---

## 2. GÓI B2 — gộp `_print_safe`

### 2.1 Sự thật đã đo

Ba bản gần như giống hệt (chỉ khác dấu tiếng Việt trong docstring):
`scripts/heartbeat_check.py:172`, `scripts/deploy_drift_check.py:126`,
`scripts/docker_down_alert.py:117`.

Hộ tiêu thụ thứ tư: `scripts/daily_data_check.py` dùng `print()` trần có dấu
tiếng Việt ở các dòng `102, 127, 132, 137, 139` — **đúng kiểu chết cp1252 ngày
01/09**.

Nhà mới: `trading/alerts.py` (16 dòng). Các script này **đã** import từ `trading`
(`deploy_drift_check.py:26 from trading.telegram import send_telegram`), nên
không thêm phụ thuộc mới.

### 2.2 Ràng buộc sống còn — FEE-ALARM-2

`heartbeat_check.py` là dead-man's switch. **Nó tuyệt đối không được ném.** Giữ
nguyên đủ ba lớp hiện có:

```
try: print(text)                                  -> return
except: try: print(text.encode("ascii","replace").decode("ascii"))
        except: pass
```

Và `main()` của mỗi script vẫn phải giữ `sys.stdout.reconfigure(...)` trong
`try/except` như hiện tại. **Một chuông chết lặng lẽ tệ hơn không có chuông.**

Gói này chỉ đổi **chỗ ở** của hàm in — **không** đổi *khi nào* chuông kêu.

### 2.3 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Một bản duy nhất | `grep -rn "def _print_safe" trading scripts` ra **đúng 1 dòng** |
| 2 | Vẫn không ném | test: ép `print` ném `UnicodeEncodeError` ⇒ hàm trả về êm; ép **cả hai** lần in ném ⇒ vẫn êm. Dán output |
| 3 | `daily_data_check` dùng hàm chung | 5 chỗ `print` nêu ở 2.1 đi qua hàm chung |
| 4 | Chuông không đổi hành vi | `pytest tests/test_heartbeat_check.py tests/test_docker_down_alert.py -q` xanh, **số test không giảm** |
| 5 | Không hồi quy | cả hai bộ, nền 393 + 97 |
| 6 | Lint | sạch |

### 2.4 Phạm vi

- **Sửa:** `trading/alerts.py`, `scripts/heartbeat_check.py`,
  `scripts/deploy_drift_check.py`, `scripts/docker_down_alert.py`,
  `scripts/daily_data_check.py`, `tests/`.
- **Không đụng:** logic quyết định cảnh báo (`bar_stale`, `token_expiry_status`,
  `in_bar_check_window`, `evaluate_daily_completeness`), `trading/calendar_vn.py`,
  `config/config.yaml`, file của ba gói kia.

### 2.5 Báo cáo kèm, không sửa

`trading/storage/db.py::read_account_balance` **không còn ai gọi** (đã grep
03/09: `account_sync` chuyển sang `read_account_balance_with_debt`, engine đọc
`read_nav` ở `engine/main.py:129`). **Giữ nguyên, không xoá** — đúng luật "báo
cáo, không tự dọn dead code". Nêu lại trong báo cáo để chủ dự án quyết.

---

## 3. GÓI C-a — `RiskManager` nhận đơn vị lô

### 3.1 Sự thật đã đo — đã chạy thật, không suy luận

`RiskManager.approve_sized` (`trading/risk.py:64`, phần sizing ở `99-108`) làm
tròn khối lượng xuống **bội 100** và từ chối `qty < 100`. Đó là luật lô sàn
HOSE. Crypto không có lô.

Chạy trực tiếp trên code hiện tại:

```
von=        100,000  gia= 60,000.00  -> None
von=  1,000,000,000  gia= 60,000.00  -> Signal(symbol='X', side='BUY', qty=3300)
von=        100,000  gia=      0.20  -> Signal(symbol='X', side='BUY', qty=50000)
```

Đo crypto hôm nay sẽ cho ra bảng trong đó **coin giá cao lặng lẽ biến mất, coin
giá thấp thì có số** — thiên lệch do công cụ tạo ra, và **không có gì trong đầu
ra báo là nó tồn tại**.

### 3.2 Việc

Thêm tham số **đơn vị lô** cho `RiskManager`, mặc định **100**. Ba chỗ dùng hằng
số 100 ở `risk.py:99-108` phải đọc từ tham số đó, **kể cả** điều kiện từ chối
`qty < 100`.

### 3.3 Ràng buộc cứng — mặc định BẤT BIẾN

Engine dựng `RiskManager` không truyền đơn vị lô ⇒ phải ra **đúng từng con số**
như hôm nay. Đây là ranh giới giữa gói này và phiên thứ Hai.

### 3.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tham số hoá | test: lô=1, vốn 100.000, giá 60.000, atr 1.500 ⇒ trả Signal `qty > 0` (hôm nay: **`None`**) |
| 2 | Mặc định bất biến | test khẳng định `RiskManager(capital=...)` không tham số vẫn làm tròn xuống bội 100 **và** từ chối `qty < 100` |
| 3 | Đo lại VN không đổi | `uv run python scripts/measure_strategy.py --strategy sma_cross --limit 3` trước/sau, **`diff` rỗng**, dán cả hai |
| 4 | Phá hoại | bỏ phần làm tròn theo lô ⇒ test 2 **đỏ**; dán nguyên văn; khôi phục |
| 5 | Không hồi quy | cả hai bộ, nền 393 + 97 |
| 6 | Lint | sạch |

### 3.5 Phạm vi

- **Sửa:** `trading/risk.py`, `tests/`.
- **Không đụng:** `trading/strategy.py` (**không** đổi `qty: int` sang số thực —
  việc lớn hơn nhiều, không cần cho một phép đo), `trading/engine/*`,
  `trading/backtest.py`, `trading/derivative_risk.py`, `config/config.yaml`.

---

## 4. GÓI H — mã trong cửa sổ thanh toán phải được nạp giá

### 4.1 Sự thật đã đo tối nay

FOX là khoản nắm giữ lớn nhất (1.100 cổ ≈ 33% danh mục). Nó bị định giá bằng giá
**28/08** suốt tới hôm nay.

Chuỗi nhân quả, đã xác minh từng mắt:

1. Lệnh hoán đổi ngày **28/08**: bán CAP, mua FOX. T+2 (31/08–02/09 nghỉ lễ) ⇒
   thanh toán **04/09**.
2. Suốt cửa sổ đó, `account_position_snapshot` cho FOX là
   `quantity = 0, cost_price = 65000`.
3. `Storage.read_real_positions` có `AND quantity > 0` trong **cả hai** nhánh
   SQL ⇒ FOX không được trả về.
4. `Storage.read_must_price_symbols` dựng danh sách "bắt buộc có giá" **từ**
   `read_real_positions` ⇒ FOX vô hình.
5. Backfill đêm chỉ nạp *174 mã thanh khoản + mã bắt buộc có giá* ⇒ FOX không
   được nạp bar suốt 5 phiên.

**Nên mọi lệnh mua đều vô hình với danh sách nạp giá đúng những ngày nó cần nhất.**

Và nó **im lặng**: kiểm tra tuổi giá đếm theo ngày giao dịch, 28/08 → 04/09 chỉ
là 2 ngày giao dịch ≤ 5, nên `unpriced_symbols` vẫn rỗng, không cảnh báo gì.

### 4.2 Cạm bẫy — sửa sai chỗ sẽ hỏng đường đặt lệnh THẬT

**Không được bỏ `quantity > 0` khỏi `read_real_positions`.** Đã grep — hàm đó
có **8 chỗ gọi trong mã sản phẩm**, không phải một hai:

```
trading/collector/account_sync.py:142   <- NAV
trading/collector/main.py:44
trading/engine/main.py:174
trading/engine/main.py:219
trading/real_orders.py:42               <- duong dat lenh THAT
trading/real_orders.py:174              <- duong dat lenh THAT
trading/storage/db.py:911               <- read_must_price_symbols (cho nay can sua)
scripts/confirm_real_order.py:168
```

Chỉ **một** trong tám chỗ đó cần hành vi mới. Bảy chỗ còn lại phải không đổi một
chữ số — trong đó hai chỗ nằm trên **đường đặt lệnh thật**
(`real_orders.py:76` cap SELL theo `sellable_qty`).

Docstring của chính hàm ghi rõ cái bẫy: nếu để mã đã bán hết hiện vĩnh viễn thì
nhánh SELL sinh lệnh bán cổ phiếu **không tồn tại**. Hai test đang canh cửa đó —
**đừng làm chúng đỏ, và đừng sửa chúng cho vừa code mới**:

```
tests/test_storage.py::test_read_real_positions_ignores_older_snapshot_for_sold_symbol
tests/test_storage.py::test_read_real_positions_reports_sellable_qty_lower_than_qty
```

**Hướng đề xuất:** thêm một **tham số** cho `read_real_positions` (mặc định
giữ nguyên hành vi hôm nay) để `read_must_price_symbols` — và **chỉ** nó — xin
thêm mã đang trong cửa sổ thanh toán. Một hàm, một truy vấn, một cờ. Đây là cách
duy nhất tôi thấy vừa sửa được vừa không phạm luật `4ea4c8d` (một công thức một
nơi) mà docstring của `read_must_price_symbols` nêu đích danh.

**Nếu bạn thấy cách gọn hơn, BÁO CÁO TRƯỚC KHI LÀM.**

### 4.3 Dấu hiệu nhận biết cửa sổ thanh toán — giả thuyết, phải tự kiểm

Quan sát trên toàn bộ lịch sử bảng: **đúng một mã** từng có
`quantity = 0 AND cost_price > 0`, và nó chính là FOX trong đúng cửa sổ
29/08 → 03/09. Mã đã bán xong (CAP hiện tại) có `quantity = 0, cost_price = 0`.

```
 symbol | so_ban_chup |     tu     |    den
--------+-------------+------------+------------
 FOX    |         643 | 2026-08-29 | 2026-09-03
```

**Đây là n = 1.** Nó gợi ý `cost_price > 0` là dấu hiệu đúng, **không chứng minh
được**. Tự truy vấn lại để xác nhận trước khi dựa vào nó, và nếu bạn tìm được
dấu hiệu chắc chắn hơn từ SSI thì **báo cáo và dùng cái đó**.

### 4.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tái hiện lỗi | test dựng đúng cảnh FOX (`quantity=0, cost_price=65000`) ⇒ `read_must_price_symbols` **thiếu** FOX. Test này phải **đỏ trên code hiện tại** |
| 2 | Sửa xong | cùng test ⇒ có FOX |
| 3 | **Đường SELL không đổi** | test khẳng định `read_real_positions(account)` mặc định **vẫn** loại mã `quantity = 0` — kể cả khi `cost_price > 0`. Và hai test canh cửa ở 4.2 vẫn xanh, **không bị sửa** |
| 4 | NAV không đổi | test: `compute_nav` / `_sync_nav` không đếm mã chưa về vào giá trị danh mục |
| 5 | Phá hoại | đảo mặc định của tham số mới ⇒ test 3 **đỏ**; dán nguyên văn; khôi phục |
| 6 | Không hồi quy | cả hai bộ, nền 393 + 97 |
| 7 | Lint | sạch |

**Tiêu chí 3 quan trọng ngang tiêu chí 2.** Sửa được việc nạp giá mà làm đường
bán thật nhìn thấy cổ phiếu chưa về là đổi một lỗ hổng lấy một lỗi tệ hơn nhiều.

### 4.5 Phạm vi

- **Sửa:** `trading/storage/db.py` (chỉ `read_real_positions` và
  `read_must_price_symbols`), `tests/`.
- **Không đụng:** `trading/collector/account_sync.py`, `trading/real_orders.py`,
  `scripts/backfill_universe.py`, `config/config.yaml`, file của ba gói kia.
- **Không** kéo `calendar_vn` vào `db.py` — tầng lưu trữ giữ trung lập thị
  trường (luật gói A).

---

## 5. Báo cáo — định dạng bắt buộc

Mỗi gói một báo cáo riêng, gồm đúng các phần sau:

1. **Bán kính ảnh hưởng** từ `gitnexus_impact` cho từng symbol đã sửa.
2. **Đã sửa gì**, theo từng file, kèm lý do từng thay đổi.
3. **Output test nguyên văn**: cả hai bộ (`not integration` và `integration`).
4. **Phá hoại**: lệnh phá, **output đỏ nguyên văn**, và xác nhận đã khôi phục
   (`grep -rn "SABOTAGE" trading scripts` rỗng).
5. **`gitnexus_detect_changes()`** trước khi báo xong.
6. **Ngoài phạm vi**: những gì bạn thấy nhưng **không** sửa.
7. **Câu hỏi** cần chủ dự án quyết (B1 chắc chắn có một — mục 1.2 điểm 4).

Không có phần 3 và 4 thì báo cáo **chưa được nhận**. "Đã xong" không phải bằng
chứng.

---

## 6. C3 — KHÔNG giao cho agent

Lịch nghỉ lễ 2026 nằm ở `config/config.yaml:9`, hiện chỉ có ba ngày:
`['2026-08-31', '2026-09-01', '2026-09-02']`.

**Chủ dự án cấp danh sách ngày, Claude sửa file.** Agent không được tự sinh ngày
lễ — đoán sai một ngày là chuông câm đúng ngày cần kêu, hoặc báo láo cả ngày.

---

## 7. Việc KHÔNG làm

| Việc | Vì sao |
|---|---|
| Bắt đầu trước 14:45 | mất phép đo thực địa của gói A |
| Tự commit / tự push | Claude audit rồi mới commit |
| Sửa `config/config.yaml` | ngoài tay agent |
| Bật `real_trading_enabled` | không đổi, không có ngoại lệ |
| Bỏ `quantity > 0` khỏi `read_real_positions` | phá đường bán thật (mục 4.2) |
| Đổi `Signal.qty` sang số thực | ngoài phạm vi C-a |
| Thêm trường chọn chiến lược vào `Config` | đã rút khỏi B1 có chủ ý (mục 1.6) |
| Đổi ngưỡng/thời điểm chuông báo | B2 chỉ đổi chỗ ở của hàm in |
| Xoá `read_account_balance` | báo cáo, không tự dọn dead code |
| Ép chiến lược phái sinh vào khuôn cổ phiếu | phá `derivative_backtest.py` |
| Chạm file của gói khác | bốn gói chạy song song |

---

## 8. Kết quả thi hành — audit 04/09 16:30

Bốn gói đã xong và đã push: `76952e6` (B1), `eb7433e` (B2), `01c47c8` (C-a),
`fafd531` (H). Bộ test **403 unit + 100 integration = 503** (nền 490 + 13), ruff
sạch, `grep -rn SABOTAGE trading scripts tests` rỗng.

### 8.1 Lỗi tìm được khi audit — đã sửa

**B1 khai sai kiểu `warmup_bars`.** Bản agent nộp khai `def warmup_bars(self) -> int`
tức method, nhưng `main.py:81,82,86` đọc `strategy.warmup_bars` **không ngoặc** và
cả ba strategy thật đều `@property`. Một strategy viết đúng theo chữ của hợp đồng
sẽ chết ở `main.py:82` với `'<' not supported between instances of 'int' and 'method'`,
và `isinstance()` **không bắt được** vì Protocol chỉ kiểm `hasattr`. Đã khai lại
thành `@property` và thêm `assert isinstance(warmup, int)` vào conformance test —
đó mới là chỗ bắt thật.

Bài học cho brief sau: một hợp đồng khai sai kiểu truy cập còn nguy hơn không có
hợp đồng, vì nó biến giả định sai thành văn bản chính thức.

### 8.2 Phép phá hoại lộ ra một lỗ hổng trong chính brief này

§4.2 nêu đích danh hai test canh cửa và cấm làm chúng đỏ. Nhưng khi đảo mặc định
`include_unsettled` thành `True`, **cả hai vẫn xanh** — không test nào trong chúng
seed hàng `quantity = 0, cost_price > 0`. Chúng không hề canh được tiêu chí 3.
Test mới `test_read_real_positions_mac_dinh_van_loai_ma_chua_ve` là chỗ duy nhất
bắt được.

### 8.3 Test phải ĐỔI Ý NGHĨA

`test_read_must_price_symbols_excludes_zero_qty` seed `quantity=0, cost_price=10.0`
rồi khẳng định phải loại — tức nó khẳng định đúng cái lỗi H sinh ra. Điều kiện loại
giờ là `cost_price = 0`. Cùng dạng với `sma_cross` hôm 03/09: khi test mã hóa một
quyết định đã bị đảo, sửa test cho khớp quyết định mới, không sửa code cho khớp test.

### 8.4 Dấu hiệu cửa sổ thanh toán — thêm một đối chứng âm

Đo lại 04/09 trên toàn bộ bảng: vẫn **đúng một mã** phía dương (FOX). Nhưng có
**hai** đối chứng âm chứ không phải một: CAP (đã bán) và `MIRHCM261` — cùng
`quantity = 0` đúng cửa sổ 29/08 đến 03/09 nhưng `cost_price = 0`. Vẫn là n = 1.

Kiểm lại trên ảnh chụp 03/09 22:00 giờ VN: FOX `cũ thấy = f` thành `mới thấy = t`,
`MIRHCM261` vẫn `f`. Lưu ý bẫy: `ts::date` quy đổi theo UTC, nên ảnh chụp gắn
nhãn "03/09" thực ra đã là 04/09 giờ VN và FOX đã về — phải lọc bằng
`ts AT TIME ZONE 'Asia/Ho_Chi_Minh'`.

### 8.5 Phát hiện NGOÀI PHẠM VI — báo, chưa sửa

**`trading/real_orders.py:100-101` là bản sao thứ hai của phép làm tròn lô**, số
100 cứng, áp SAU `approve_sized`:

```python
qty = min(sized.qty, max_buy_qty) // 100 * 100
if qty < 100:
```

Hôm nay không sai (đường này chỉ chạy cổ phiếu VN). Nhưng nó làm `lot_size` của
C-a **không** phải tham số duy nhất trên toàn hệ: đặt `lot_size=1` thì `risk.py`
tôn trọng còn dòng này lặng lẽ áp lại 100. Nằm trên đường đặt lệnh thật nên không
sửa kèm. **Việc tồn đọng mới — mục I.**

### 8.6 Còn treo

- **Chưa dựng lại image.** Cả bốn gói đều chạm `trading/`, engine đang chạy vẫn là
  mã cũ (chưa có `last_crossover` của octopus). Dựng lại = khởi động lại engine,
  chủ dự án quyết.
- Chỉ số GitNexus lại cũ sau đợt commit này — chạy `npx gitnexus analyze`.
- `detect-changes` báo **risk level: high** vì `read_real_positions` nằm trên luồng
  `Handle_crossover` và `_sync_nav`. Hành vi hai luồng đó không đổi theo cấu trúc
  (mặc định `False`) và đã có test canh.
