# Brief giao việc — đợt 3 (M, P, L)

Viết 04/09 tối, sau khi I và C-b đã xong và đã push (`932cca5`).

## Ý chính của brief này

Bốn việc còn tồn đọng — **J, K, F, C3** — đều là **quyết định của chủ dự án**,
không phải việc code. Nhưng ba trong bốn cái đó đang chờ vì thiếu số liệu, chứ
không phải vì khó nghĩ.

Nên hai gói đầu của brief này **không sửa hành vi gì cả**: chúng đi đo, để quyết
định được đưa ra trên số liệu thay vì trực giác.

| Gói | Mục đích | Gỡ nút cho |
|---|---|---|
| **M** | Bảng độ nhạy ngưỡng thanh khoản trên crypto | **K** |
| **P** | BingX có dữ liệu spot cho rổ này không | **F** |
| **L** | Dọn `read_account_balance` đã chết | — |

**J không có trong brief này.** Xem §5.

---

## 0. Luật chung — đọc hết trước khi gõ dòng đầu tiên

### 0.1 Vai trò

Agent **viết code và tự kiểm chứng**. Agent **không commit, không push**. Claude
audit rồi mới commit. Báo cáo không có bằng chứng thô thì không được nhận.

### 0.2 An toàn — không có ngoại lệ

- `real_trading_enabled` giữ `false`. **Không bật, kể cả tạm thời.**
- Không gọi API đặt lệnh hay huỷ lệnh của SSI. Data API chỉ đọc.
- Không in giá trị bí mật ở bất kỳ đâu. Báo cáo chỉ nêu **tên biến**.
- `.env` không nằm trong git — không sửa, không commit.
- Không `TRUNCATE`, không `DROP`, không xoá dòng dữ liệu. Chỉ nạp thêm.
- `config/config.yaml` agent **không được sửa**.
- BingX: không dùng API key, không chạm endpoint đặt lệnh, **không vượt
  1 request/giây**, không cố ý kích 429. Không cài plugin skill BingX bên thứ ba.

### 0.3 Phạm vi phẫu thuật

Mỗi gói ghi rõ được sửa gì và không được đụng gì. Giữ nguyên style xung quanh.
Không "tiện thể" refactor. Phát hiện ngoài phạm vi thì **báo cáo, không sửa**.
Agent chỉ được xoá import/biến/hàm mà **chính thay đổi của mình** làm thừa.
Ngoại lệ duy nhất: gói L được giao xoá dead code **có tên cụ thể** — và chỉ cái tên đó.

### 0.4 Bài học bắt buộc đọc từ đợt trước

Đợt 2 có một agent làm đúng cả bốn cảnh báo được giao, rồi vẫn sập bẫy thứ năm:
`octopus_pullback.py:76` mang hằng số `2_000_000_000.0` — 2 tỷ **đồng** — và phép
đo áp nó lên dữ liệu **USDT**, chặn gần hết rổ. Kết quả là một câu sai
("octopus không kích hoạt trên crypto") đứng trong báo cáo.

**Quy tắc rút ra, áp cho mọi gói từ nay:** trước khi đo trên thị trường khác VN,
chạy

```
grep -rn "[0-9]_000_000\|[0-9]e9\|[0-9]e8" trading/
```

và **liệt kê trong báo cáo** từng hằng số tìm được cùng đơn vị của nó. Danh sách
rỗng cũng phải ghi là rỗng.

### 0.5 GitNexus

Chỉ số đang cũ. Chạy `npx gitnexus analyze --repo AI_auto_trading_system` **trước
khi sửa**. `gitnexus_impact` trước khi sửa mỗi symbol, `gitnexus_detect_changes`
trước khi báo xong.

### 0.6 Nền test — số mới

```
uv run pytest -m "not integration" -q   ->  409 passed
docker compose --profile test up -d nats-test
uv run pytest -m integration -q         ->  100 passed
uv run ruff check trading tests scripts ->  All checks passed
```

### 0.7 Ba gói không dùng chung file — chạy song song được

| Gói | File sản phẩm | Chạm image? |
|---|---|---|
| **M** | `scripts/` + `tests/` | Không |
| **P** | `scripts/` + `tests/` | Không |
| **L** | `trading/storage/db.py` + 3 comment | **Có** |

---

## 1. GÓI M — bảng độ nhạy ngưỡng thanh khoản (gỡ nút cho K)

### 1.1 Sự thật đã đo

`octopus_pullback.py:76` đặt `min_avg_value_20 = 2_000_000_000.0` (2 tỷ VND).
Áp lên dữ liệu USDT thì nó chặn gần hết rổ. Đã đo, cùng dữ liệu cùng tham số,
chỉ đổi ngưỡng:

```
===== KHUNG 1D — 20 ma =====
  nguong=2e9 (mac dinh)  lenh=    1  PnL=      -829.14  B&H=   247,749.94
  nguong=0               lenh=   46  PnL=    -6,380.49  B&H=   247,749.94

===== KHUNG 1H — 20 ma =====
  nguong=2e9 (mac dinh)  lenh=    0  PnL=         0.00  B&H=   146,685.11
  nguong=0               lenh=  545  PnL=   -53,539.84  B&H=   146,685.11
```

Hai đầu mút đã biết. **Cái chưa biết là ở giữa** — và chủ dự án cần khúc giữa đó
để chọn một con số cho USDT.

### 1.2 Việc

Một script trong `scripts/` in bảng độ nhạy: với mỗi ngưỡng trong một dải, báo
**số mã lọt cổng**, **số lệnh**, **PnL**, cho cả hai khung 1d và 1h.

Dải đề nghị (agent được đề xuất dải khác nếu có lý do, nêu trong báo cáo):
`0, 1e5, 1e6, 1e7, 1e8, 5e8, 1e9, 2e9`.

Tiêm ngưỡng bằng `OctopusPullbackStrategy(min_avg_value_20=...)` — tham số đã có
sẵn trong `__init__`, **không sửa `trading/`**.

### 1.3 Ràng buộc cứng

- **Chỉ đo, không quyết.** Không chọn ngưỡng "đúng", không sửa mặc định trong
  `trading/strategies/octopus_pullback.py`. Kết luận của gói này là **một cái bảng**,
  không phải một con số.
- Giữ nguyên bốn cảnh báo của đợt trước trong báo cáo: vốn USDT, `lot_size=1` là
  giả định, **chưa trừ phí**, thiên lệch sống sót.
- Dùng lại `read_crypto_bars` và `run_backtest` — **không viết lại vòng đo**
  (bài học `4ea4c8d`: một công thức một nơi).

### 1.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tiêm được ngưỡng | test: hai instance khác `min_avg_value_20` cho **số lệnh khác nhau** trên cùng bộ nến dựng sẵn |
| 2 | Hai đầu mút khớp | chạy thật, ngưỡng `2e9` và `0` phải **tái hiện đúng** bốn con số ở §1.1. Lệch là dấu hiệu vòng đo bị viết lại sai |
| 3 | Bảng độ nhạy | dán **nguyên văn** bảng cho cả 1d và 1h |
| 4 | Đơn điệu | ngưỡng tăng ⇒ số mã lọt **không tăng**. Nếu thấy ngược, **dừng và báo cáo** — đó là dấu hiệu lỗi, không phải phát hiện |
| 5 | Quét hằng số | dán kết quả `grep` ở §0.4 |
| 6 | Không hồi quy | 409 + 100 |
| 7 | Lint | sạch |

### 1.5 Phạm vi

- **Sửa:** `scripts/` (script mới), `tests/`.
- **Không đụng:** `trading/` toàn bộ — đặc biệt `octopus_pullback.py`;
  `scripts/measure_crypto_strategies.py` (của gói C-b, đã đóng);
  `scripts/bingx_klines.py`; `config/config.yaml`.
- **Không** nạp lại `bars_crypto`.

---

## 2. GÓI P — BingX có dữ liệu spot cho rổ này không (gỡ nút cho F)

### 2.1 Vì sao gói này tồn tại

Câu hỏi F là "spot hay perpetual, có đòn bẩy không". Nó đang chặn mọi thứ phía sau.

Dữ liệu đã nạp lấy từ `/openApi/swap/v3/quote/klines` — tức **perpetual swap**.
Nếu chủ dự án chọn spot thì 412.487 nến hiện có **không dùng được**.

Nhưng câu hỏi đó dễ trả lời hơn nhiều nếu biết trước: **BingX có cho lấy klines
spot công khai cho đúng 20 mã này không, và lịch sử lùi được tới đâu.** Nếu không
có thì quyết định coi như đã xong.

### 2.2 Việc

Một script thăm dò trong `scripts/`, chỉ đọc, báo cáo cho từng mã trong rổ 20:
spot có sẵn không, khung nào, nến sớm nhất là ngày nào, số nến lấy được.

### 2.3 Ràng buộc cứng

- **Không đoán endpoint.** Tra tài liệu công khai của BingX. Nếu không chắc,
  **báo cáo là không chắc** kèm thứ đã thử — đừng bịa URL rồi kết luận "không có".
- **Không API key.** Chỉ endpoint công khai.
- **Không quá 1 request/giây.** Có `sleep`, có backoff. Không cố ý kích 429.
- **KHÔNG ghi vào `bars_crypto`.** Gói này chỉ thăm dò và báo cáo. Nếu cần lưu
  thì lưu ra file tạm ngoài repo, không tạo bảng mới, không sửa bảng cũ.
- Không so sánh chiến lược, không backtest. Đây là câu hỏi "có dữ liệu không",
  không phải "chiến lược chạy thế nào".

### 2.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tôn trọng giới hạn tần suất | test: hàm gọi mạng được mock, khẳng định có `sleep >= 1.0s` giữa hai lần gọi liên tiếp |
| 2 | Thất bại không làm chết script | test: mock trả 429 và trả JSON rác ⇒ script báo lỗi cho mã đó rồi **đi tiếp**, không ném ra ngoài |
| 3 | Chạy thật | dán **nguyên văn** bảng 20 mã |
| 4 | Trung thực | mã nào không lấy được phải hiện trong bảng là "không lấy được", **không được lặng lẽ bỏ khỏi bảng** |
| 5 | Không hồi quy | 409 + 100 |
| 6 | Lint | sạch |

### 2.5 Phạm vi

- **Sửa:** `scripts/` (script mới), `tests/`.
- **Không đụng:** `trading/`, `scripts/bingx_klines.py`,
  `scripts/measure_crypto_strategies.py`, `config/config.yaml`, bảng `bars_crypto`.

---

## 3. GÓI L — dọn `read_account_balance` đã chết

### 3.1 Sự thật đã đo

`Storage.read_account_balance` (`trading/storage/db.py:214`) **không còn chỗ gọi
nào** trong mã sản phẩm lẫn test. Chỉ `read_account_balance_with_debt` được dùng
(`collector/account_sync.py:135`).

**Nhưng có một cái bẫy.** Ba chỗ nhắc tên nó như "con đường đã cố tình không đi":

```
trading/engine/main.py:149   # MỌI lệnh, KHÔNG rơi về read_account_balance cho "đỡ gắt"
trading/storage/db.py:232    (debt), read_account_balance chi tra withdrawable
trading/storage/db.py:251    ve read_account_balance cho "do gat"
tests/test_engine_main.py:699,708  (docstring + comment, cùng ý)
```

Xoá hàm mà để nguyên các comment đó thì tài liệu trỏ vào một cái tên không còn
tồn tại — tệ hơn hiện trạng.

### 3.2 Việc

1. Xoá `Storage.read_account_balance`.
2. Viết lại 5 chỗ nhắc trên sao cho chúng mô tả **hành vi** chứ không gọi tên một
   symbol đã xoá. Ví dụ: "không rơi về số dư khả dụng cho đỡ gắt". **Giữ nguyên
   ý nghĩa của quyết định an toàn** — đây là tài liệu về một lựa chọn có chủ đích,
   không phải rác.

### 3.3 Ràng buộc cứng

- **Chỉ xoá đúng hàm này.** Không xoá `read_account_balance_with_debt`. Không
  đụng dead code khác dù có thấy — báo cáo thôi.
- Không đổi hành vi gì cả. Đây là gói xoá, không phải gói sửa.
- Nếu trong lúc làm phát hiện hàm **có** chỗ gọi mà tôi bỏ sót, **dừng lại và báo
  cáo** — đừng xoá.

### 3.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Xác nhận đã chết | dán nguyên văn `grep -rn "read_account_balance\b" --include=*.py trading scripts tests \| grep -v _with_debt` **trước** khi xoá |
| 2 | Xoá xong | cùng lệnh grep ⇒ không còn dòng nào trỏ tới symbol đã xoá |
| 3 | Hành vi không đổi | 409 + 100, **không sửa test nào** để làm chúng xanh |
| 4 | Tài liệu còn nghĩa | đọc lại 5 chỗ đã viết lại, mỗi chỗ vẫn nói được vì sao không rơi về số dư khả dụng |
| 5 | Lint | sạch |

### 3.5 Phạm vi

- **Sửa:** `trading/storage/db.py`, `trading/engine/main.py` (chỉ comment dòng 149),
  `tests/test_engine_main.py` (chỉ docstring/comment dòng 699, 708).
- **Không đụng:** logic của bất kỳ hàm nào, `config/config.yaml`, file của M và P.

---

## 4. Báo cáo — định dạng bắt buộc

1. **Đã làm gì** — theo từng file, kèm số dòng.
2. **Quyết định đã chọn** — mọi chỗ có hai cách hiểu, chọn cách nào, vì sao.
3. **Output test nguyên văn** — cả hai bộ, cả `ruff`. Không tóm tắt.
4. **Kết quả `grep` hằng số** ở §0.4 (gói M bắt buộc; hai gói kia ghi "không áp dụng").
5. **Phát hiện ngoài phạm vi** — báo, không sửa.
6. **Điều còn chưa chắc** — nói ra, đừng giấu.

Mục 3 **không thương lượng**. "Đã xong" không phải bằng chứng.

Gói M và P là gói **đo**: bảng số liệu thô chính là sản phẩm. Đừng rút gọn bảng,
đừng chỉ đưa kết luận.

---

## 5. KHÔNG giao cho agent

**J — octopus chỉ MUA thật, không bao giờ BÁN thật.** Đã xác nhận lại hôm nay:
`process_bar` cho tín hiệu SELL của `on_bar` đi qua `approve_sized` → `broker.submit`,
tức **PaperBroker**; đường lệnh thật chỉ nhận qua `on_crossover`. Vì octopus chỉ
phát `None`/`"bull"`, tỷ lệ lệnh thoát mà đường thật bỏ lỡ là **100%** — không cần
đo thêm, con số đã biết.

Có hai hướng sửa khác hẳn nhau (nối tín hiệu SELL của `on_bar` vào `real_orders`,
hay giữ sma_cross cho đường thật và dùng octopus thuần cho chạy giấy). **Chủ dự án
chọn hướng, rồi mới viết brief.** Hôm nay chưa cháy vì `real_trading_enabled: false`.

**K, F** — hai gói M và P sinh ra để phục vụ đúng hai quyết định này. Đợi số liệu.

**C3 — lịch nghỉ lễ 2026.** Chủ dự án cấp ngày, Claude sửa `config.yaml`.
**Agent không được bịa ngày lễ.**

**E, C1, C2** — vốn engine đọc nhầm tài khoản, VPS Ubuntu, Docker tự khởi động.
Quyết định của chủ dự án.

**D1 — diễn tập dead-man's switch.** Cần một phiên thật và điện thoại của chủ dự án.

---

## 6. Việc KHÔNG làm

- Không bật `real_trading_enabled`, kể cả để thử.
- Không sửa `config/config.yaml`.
- Không sửa mặc định `min_avg_value_20` — gói M chỉ đo.
- Không thêm crypto vào `trading/backtest.py::_TF_SPEC`.
- Không nạp lại `bars_crypto`, không xoá dòng nào của nó, không tạo bảng mới.
- Không đoán endpoint BingX, không đoán phí, không đoán ngày nghỉ lễ.
- Không đụng `trading/risk.py`, `trading/strategy.py`, `trading/real_orders.py` —
  ba chỗ đó đã đóng ở các đợt trước.
- Không commit, không push.
