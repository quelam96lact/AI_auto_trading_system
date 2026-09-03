# Plan — việc làm được ngoài giờ giao dịch

Viết 00:45 ngày 04/09, trước phiên. Mọi số dưới đây đã đo tối nay, không phỏng
đoán. Thay thế mục 9 của `2026-09-03-plan-xu-ly-ton-dong.md` về mặt thứ tự.

---

## 0. Ranh giới thật không phải đồng hồ — mà là **image**

Câu hỏi "làm được ngoài giờ giao dịch không?" thực ra là câu hỏi sai. Đo trực
tiếp:

`Dockerfile` chỉ `COPY` ba thứ: `pyproject.toml uv.lock`, **`trading`**,
**`config`**. `scripts/` **không nằm trong image** — nó chạy trên host qua Task
Scheduler. Và `scripts/deploy_drift_check.py:80` chỉ so mốc build image với
`git log -1 -- trading/`.

**Hệ quả kiểm chứng được:**

| Chạm gì | Cần dựng lại? | Ảnh hưởng phiên đang tới? |
|---|---|---|
| `scripts/`, `tests/`, `docs/` | Không | **Không thể** |
| `trading/` | Có | Có — phiên sau là "phiên đầu chạy image mới" |
| `config/config.yaml` | **Có** (được `COPY` vào image, `trading/config.py:38` đọc) | Có |

Điều thứ ba là đính chính: tôi từng xếp lịch nghỉ lễ (C3) là việc miễn phí. Sai
— nó vào image y hệt `trading/`.

---

## 1. Bảng phân loại tồn đọng

| Mã | Việc | Chạm | Làm được trước phiên 04/09? |
|---|---|---|---|
| **C** | BingX giai đoạn 2 — đo chiến lược | chỉ `scripts/` | Được (nhưng xem 2.1) |
| **G** | Chạy bộ test integration | không sửa gì | **Đã làm — xem mục 2.2** |
| — | Viết brief, audit chỉ-đọc | `docs/` | Được |
| **C2** | Docker Desktop tự khởi động | thiết lập OS | Được |
| **C1/E/F** | quyết định của chủ dự án | không code | Được |
| **B1** | hợp đồng chiến lược | `trading/` | **Không** — tối nay sau 14:45 |
| **B2** | gộp `_print_safe` | `trading/` + `scripts/` | **Không** — tối nay sau 14:45 |
| **C3** | lịch nghỉ lễ 2026 | `config/config.yaml` | **Không** — tối nay sau 14:45 |
| — | xác nhận gói A lúc 13:00 | cần phiên sống | **Bất khả ngoài giờ** |
| **D1** | diễn tập dead-man's switch | cần phiên sống, KHÔNG phải 04/09 | **Bất khả ngoài giờ** |

Lý do cấm B1/B2/C3 trước phiên hôm nay không đổi: **13:00 hôm nay là phép đo
thực địa duy nhất của gói A.** Dựng lại image lần nữa trước đó là trộn hai biến
vào một phiên và mất luôn phép đo. Ba việc này gộp thành **một** lần dựng lại
tối nay, không phải ba.

---

## 2. Việc ngoài giờ đã làm tối nay

### 2.1 Trạng thái hệ thống trước phiên — đã đo

- 6 container **Up**, gồm `collector`, `engine`, `postgres`, `nats`, `grafana`.
- `ssi_auth_state`: `updated_at = 00:29:38 VN`, access token hết hạn `00:44:38`.
  Chuỗi refresh **đang sống và tự chạy**.

**Nên quy trình tay hai bước buổi sáng (`spike_ssi_sdk_auth.py` →
`load_token_to_db.py`) có thể KHÔNG cần chạy** — nếu máy không tắt và container
không dừng từ giờ tới 09:00, token tự refresh như 03/09 (T1 lúc 08:59). Chỉ làm
tay nếu sáng dậy thấy Docker đã tắt.

Gói **C** hợp lệ về kỹ thuật ngay lúc này, nhưng **không nên bắt đầu lúc nửa
đêm**: nó là phép đo đòi kỷ luật (đóng băng ngưỡng trước, kỳ ngoài mẫu niêm
phong, số phải tái lập được). Bắt đầu mệt là cách chắc chắn nhất phá chính kỷ
luật đó. Nó cũng còn treo ở quyết định **F**: phần spot chạy được không cần F,
phần perpetual thì không — và nếu đo perpetual mà chưa mô hình hoá funding thì
**phải ghi rõ trong báo cáo**.

### 2.2 Phát hiện: có một test ĐỎ đang nấp trong bộ integration

Chưa ai từng chạy `-m integration` vì thói quen hàng ngày là `-m "not
integration"`. Tôi chạy tối nay:

```
uv run pytest -m integration -q
1 failed, 96 passed, 393 deselected in 16.01s
```

Nền thật của repo: **489 test, 488 xanh, 1 đỏ.**

Test đỏ là `tests/test_backtest_cli.py:38`:

```
def test_cli_registry_no_longer_offers_sma_cross():
    assert "sma_cross" not in STRATEGIES
E   AssertionError: assert 'sma_cross' not in {'daily_breakout': ..., 'octopus_pullback': ..., 'sma_cross': ...}
```

Nó **không phải bug**. Nó là một test khẳng định quyết định ngày 15/08, còn
`trading/backtest.py:290` ghi rõ quyết định đó đã **bị đảo ngược có chủ ý** ngày
01/09 (đợt 4 Task 0: sma_cross được thêm lại vào sổ **để đo**, không phải để
chạy thật). Test cũ không ai sửa vì `pytestmark = pytest.mark.integration` ở
đầu file làm nó biến mất khỏi mọi lần chạy.

**Đây là lỗ hổng kỷ luật, không phải lỗi code:** một cái marker đủ để một test
đỏ sống sót ba ngày mà không ai thấy. Xử lý ở B1 (mục 3.1) và ở mục 5.

---

## 3. Gói tối nay sau 14:45 — B1 + B2 + C3, **một** lần dựng lại

Ba việc, gộp một commit-và-dựng để phiên thứ Hai chỉ có một biến mới. Cuối tuần
là thời gian kiểm.

### 3.1 B1 — hợp đồng chiến lược (đã thu hẹp, xem 3.2)

**Sự thật đã đo.** `trading/strategy.py:20` khai `Strategy` Protocol gồm đúng ba
hàm: `on_bar`, `last_crossover`, `last_atr`. Nhưng engine gọi thêm hai hàm nữa
mà Protocol **không** khai: `warmup_bars` (`engine/main.py:81,82,86`) và
`compute_crossover` (`engine/main.py:91`).

Ma trận thật của năm chiến lược:

| Chiến lược | `on_bar`+`last_atr` | `last_crossover` | `warmup_bars` | `compute_crossover` | Nạp vào engine? |
|---|---|---|---|---|---|
| `sma_cross` | ✓ | ✓ | ✓ | ✓ | **được** |
| `daily_breakout` | ✓ | ✓ | ✓ | ✓ | **được** |
| `octopus_pullback` | ✓ | **✗** | ✓ | ✓ | **chết** ở `logic.py:44` |
| `momentum_breakout` | ✓ | ✓ | **✗** | ✓ | chết ở `main.py:81` |
| `momentum_rsi` | ✓ | **✗** | **✗** | ✓ | chết hai chỗ |

`octopus_pullback` **đang nằm trong `STRATEGIES`** và backtest sạch — nhưng nạp
vào engine sẽ `AttributeError` ngay bar đầu tiên. Đó là cái bẫy B1 tồn tại để
đóng.

**Việc:**

1. Bổ sung `warmup_bars` và `compute_crossover` vào `Strategy` Protocol cho
   khớp thứ engine thật sự gọi.
2. Thêm `last_crossover` cho `octopus_pullback` (và quyết định — **báo cáo, đừng
   tự chọn** — với hai chiến lược momentum: bổ sung, hay tuyên bố rõ chúng chỉ
   dùng cho backtest).
3. **Conformance test:** mọi mục trong `STRATEGIES` phải thoả đúng hợp đồng mà
   sổ đăng ký đó hứa. Test phải **đỏ trên code hiện tại** trước khi bước 2 làm
   nó xanh — nếu nó xanh ngay từ đầu thì nó không kiểm gì cả.
4. Sửa `test_cli_registry_no_longer_offers_sma_cross` cho khớp quyết định 01/09
   (đảo khẳng định + đổi tên + ghi lý do). **Không** gỡ `sma_cross` khỏi sổ để
   test cũ xanh lại — đó là sửa thực tại cho vừa cái test.

**Ràng buộc cứng — hai hợp đồng, không phải một.** `derivative_backtest.py:57`
chỉ dùng `compute_crossover` + `qty`. Ép cả năm chiến lược vào khuôn cổ phiếu sẽ
phá đường phái sinh. Các chiến lược momentum **không phải** dead code — chúng có
ba file test riêng.

**Phạm vi:** `trading/strategy.py`, `trading/strategies/*`, `tests/`.
**Không đụng:** `trading/engine/*`, `config/config.yaml`, `trading/backtest.py`
(ngoài việc không đổi nội dung `STRATEGIES`).

### 3.2 B1b — trường chọn chiến lược trong `Config`: **hoãn, không làm**

Kế hoạch cũ gộp cả việc thêm trường chiến lược vào `Config` và đọc nó ở
`engine/main.py:71` (đang đóng cứng `SmaCrossStrategy()`).

**Tôi rút việc này ra và đề nghị hoãn.** Lý do: nó chỉ có giá trị khi ta muốn
đổi chiến lược đang chạy — mà **không chiến lược nào trong repo có lợi thế đo
được**, nên chưa có chiến lược nào xứng đáng được chọn. Xây cơ chế chọn trước
khi có thứ để chọn là thêm một đường nạp cấu hình có rủi ro runtime thật, đổi
lấy một khả năng chưa ai cần.

Làm nó khi gói C (hoặc một phép đo khác) sinh ra ứng viên thứ hai thật sự.

### 3.3 B2 — gộp `_print_safe`

Ba bản đã xác nhận bằng grep: `scripts/heartbeat_check.py:172`,
`scripts/deploy_drift_check.py:126`, `scripts/docker_down_alert.py:117`. Thân
hàm giống nhau; chỉ khác dấu tiếng Việt trong docstring.

Hộ tiêu thụ thứ tư: `scripts/daily_data_check.py` dùng `print()` trần với dấu
tiếng Việt ở các dòng `102, 127, 132, 137, 139` — **đúng kiểu chết cp1252 ngày
01/09**. Đưa nó dùng hàm chung luôn.

Nhà mới: `trading/alerts.py` (16 dòng). Các script này **đã** import từ
`trading` rồi (`deploy_drift_check.py:26 from trading.telegram import
send_telegram`), nên không thêm phụ thuộc mới.

**Ràng buộc sống còn — FEE-ALARM-2.** Hàm gộp tuyệt đối không được ném, kể cả
đường lui ASCII. Và phải giữ nguyên hai lớp bảo vệ hiện có: `try: print(text)` →
`except: print(text.encode("ascii","replace"))` → `except: pass`. Một chuông
chết lặng lẽ tệ hơn không có chuông.

**Kèm theo:** `read_account_balance` trong `trading/storage/db.py` giờ không còn
ai gọi (đã grep 03/09). **Báo cáo, không xoá** — chờ chủ dự án quyết cùng đợt.

**Phạm vi:** `trading/alerts.py`, bốn script trên, `tests/`.
**Không đụng:** logic chuông báo (chỉ đổi *chỗ ở* của hàm in, không đổi *khi
nào* kêu).

### 3.4 C3 — lịch nghỉ lễ 2026

`config/config.yaml:9` hiện chỉ có ba ngày:
`['2026-08-31', '2026-09-01', '2026-09-02']`.

Ngày lễ chưa khai làm chuông 2A báo láo suốt ngày đó (đúng sự cố 01/09).

**Chỗ mơ hồ, không được đoán:** tôi không có lịch nghỉ lễ chính thức 2026 đã
kiểm chứng. **Chủ dự án cấp danh sách ngày**, Claude sửa file. Agent **không
được** tự sinh ngày lễ — sai một ngày là chuông câm đúng ngày cần kêu, hoặc kêu
láo cả ngày.

`config/config.yaml` vẫn nằm ngoài tầm tay agent theo luật cũ.

### 3.5 Tiêu chí hoàn thành gói tối nay

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Protocol khớp thực tế | conformance test **đỏ trước, xanh sau** — dán cả hai output |
| 2 | `octopus_pullback` nạp được engine | test dựng nó rồi gọi đúng đường `logic.py` bar đầu ⇒ không `AttributeError` |
| 3 | Không phá đường phái sinh | test phái sinh cũ vẫn xanh, hợp đồng phái sinh **không** bị ép theo khuôn cổ phiếu |
| 4 | `_print_safe` vẫn không ném | phá: cho `print` ném `UnicodeEncodeError` ⇒ hàm vẫn trả về êm, **dán output** |
| 5 | Chuông không đổi hành vi | test heartbeat cũ xanh nguyên, số lượng không giảm |
| 6 | Không hồi quy — **cả hai bộ** | `pytest -m "not integration" -q` **và** `pytest -m integration -q`; nền: **393 + 96 xanh, 0 đỏ** |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |
| 8 | Phạm vi | `git diff --stat` chỉ gồm file đã liệt kê ở 3.1/3.3 |

**Tiêu chí 6 là điểm mới và là cái quan trọng nhất của plan này.** Từ nay số nền
là **489**, không phải 393.

---

## 4. Việc bất khả ngoài giờ — đừng cố

| Việc | Vì sao |
|---|---|
| Xác nhận gói A: 13:00 điện thoại **không** kêu | chuông chỉ chứng minh được ngoài thực địa |
| Xác nhận NAV 0434226 giữ đúng giữa phiên (≈131,58tr, `unpriced` rỗng) | cần giá sống |
| Quan sát cửa sổ mù 15 phút đầu phiên sáng | cần mốc 09:00–09:16 thật |
| **D1** diễn tập dead-man's switch | cần phiên sống, và **KHÔNG phải 04/09** |

---

## 5. Thay đổi thói quen — hệ quả của mục 2.2

Từ nay, **trước mỗi commit chạm `trading/`**, chạy cả hai bộ:

```
uv run pytest -m "not integration" -q     # 393
uv run pytest -m integration -q           # 96  (cần: docker compose --profile test up -d nats-test)
```

Bộ integration chạy 16 giây. Cái giá của việc bỏ qua nó là một test đỏ sống ba
ngày mà không ai biết.

---

## 6. Việc KHÔNG làm

| Việc | Vì sao |
|---|---|
| Dựng lại image trước 09:00 hôm nay | mất phép đo thực địa duy nhất của gói A |
| Gỡ `sma_cross` khỏi `STRATEGIES` cho test cũ xanh | sửa thực tại cho vừa cái test; quyết định 01/09 là có chủ ý |
| Thêm trường chọn chiến lược vào `Config` | chưa có chiến lược nào xứng đáng được chọn (3.2) |
| Agent tự khai ngày nghỉ lễ 2026 | đoán sai = chuông câm đúng ngày cần kêu |
| Xoá `read_account_balance` | báo cáo, không tự dọn dead code |
| Bật `real_trading_enabled` | không chiến lược nào có lợi thế đo được. Không đổi |
| Bắt đầu gói C lúc nửa đêm | phép đo cần kỷ luật; mệt là cách phá kỷ luật |

---

## 7. Thứ tự

```
Bây giờ 00:45   để máy chạy — token tự refresh, không đụng image
Sáng 04/09      chỉ chạy tay token NẾU Docker đã tắt
13:00 04/09     xác nhận gói A — mốc kiểm chứng thật
Sau 14:45       B1 + B2 + C3 → một commit → MỘT lần dựng lại
Cuối tuần       kiểm gói tối nay + gói C (BingX, chỉ scripts/)
Tuần sau        D1 diễn tập dead-man's switch
Bất kỳ lúc nào  chủ dự án trả lời C1/C2/C3/E/F — F chặn gói C
```
