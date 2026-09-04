# Brief giao việc — tồn đọng sau đợt 04/09 (I, C-b)

Viết 04/09 ~17:30, sau khi A, B, B1, B2, C-a, H đã xong và engine đã chuyển sang
octopus (`5a750f6`).

**Chỉ có HAI gói giao được cho agent.** Phần còn lại của bảng tồn đọng không phải
vì khó, mà vì chúng là quyết định của chủ dự án hoặc cần một phiên giao dịch thật
— xem §4. Đừng giao chúng cho agent, và đừng để agent "tiện tay" làm.

---

## 0. Luật chung — đọc hết trước khi gõ dòng đầu tiên

### 0.1 Vai trò

Agent **viết code và tự kiểm chứng**. Agent **không commit, không push**. Claude
audit rồi mới commit. Báo cáo không có bằng chứng thô thì không được nhận.

### 0.2 An toàn — không có ngoại lệ

- `real_trading_enabled` giữ `false`. **Không bật, kể cả tạm thời.**
- Không gọi API đặt lệnh hay huỷ lệnh của SSI. Data API chỉ đọc.
- Không in giá trị bí mật ở bất kỳ đâu. Báo cáo chỉ được nêu **tên biến**.
- `.env` không nằm trong git — không sửa, không commit.
- Không `TRUNCATE`, không `DROP`, không xoá dòng. Chỉ nạp thêm.
- `config/config.yaml` agent **không được sửa**.
- BingX: không dùng API key, không chạm endpoint đặt lệnh, **không vượt 1 request/giây**,
  không cố ý kích 429. Không cài plugin skill BingX của bên thứ ba.

### 0.3 Phạm vi phẫu thuật

Mỗi gói ghi rõ **được sửa gì** và **không được đụng gì**. Giữ nguyên style xung
quanh. Không "tiện thể" refactor. Phát hiện ngoài phạm vi thì **báo cáo, không sửa**.
Agent chỉ được xoá import/biến/hàm mà **chính thay đổi của mình** làm thừa — không
xoá dead code có từ trước.

### 0.4 GitNexus

Chỉ số đang cũ. Chạy `npx gitnexus analyze` **trước khi sửa** (repo này index dưới
tên `AI_auto_trading_system`; máy có nhiều repo nên CLI cần `--repo`). Chạy
`gitnexus_impact` trước khi sửa mỗi symbol, `gitnexus_detect_changes` trước khi báo xong.

### 0.5 Nền test — số mới

```
uv run pytest -m "not integration" -q   ->  404 passed
docker compose --profile test up -d nats-test
uv run pytest -m integration -q         ->  100 passed
uv run ruff check trading tests scripts ->  All checks passed
```

Dùng số này, đừng dùng số cũ trong các plan trước (393 / 403 đều đã lỗi thời).

### 0.6 Hai gói không dùng chung file — chạy song song được

| Gói | File sản phẩm | Chạm image? |
|---|---|---|
| **I** | `trading/real_orders.py` | **Có** — phải dựng lại container |
| **C-b** | `scripts/` + `tests/` | **Không** |

C-b không phụ thuộc I (xem §2.1). Chạy đồng thời được.

---

## 1. GÓI I — `real_orders.py` còn một bản sao của phép làm tròn lô

### 1.1 Sự thật đã đo

Gói C-a (`01c47c8`) làm `lot_size` thành tham số của `RiskManager`: cả phép làm
tròn xuống lẫn ngưỡng từ chối đều đọc từ nó. Nhưng `trading/real_orders.py:100-101`
vẫn giữ một bản sao riêng, số 100 cứng, áp **sau** `approve_sized`:

```python
# Tran CUNG suc mua SSI, ap SAU approve_sized — lam tron xuong boi 100
qty = min(sized.qty, max_buy_qty) // 100 * 100
if qty < 100:
```

Hôm nay **không sai** — đường này chỉ chạy cổ phiếu VN, lô đúng là 100. Vấn đề là
nó làm lời hứa của C-a thành nửa vời: đặt `lot_size = 1` thì `risk.py` tôn trọng
còn dòng này lặng lẽ áp lại 100. Đúng dạng "con số sai mà nhìn vẫn hợp lý" mà cả
đợt này sinh ra để diệt.

**Tin tốt:** `handle_crossover` đã nhận sẵn `risk: RiskManager` làm tham số thứ ba
(`real_orders.py:20`). Không cần đổi chữ ký hàm, không cần kéo thêm gì vào.

### 1.2 Việc

Thay hai chỗ hằng số 100 ở `real_orders.py:100-101` bằng `risk.lot_size`.

**Chỉ vậy.** Không đụng nhánh `"bear"` (dòng 75-79), không đụng `sellable_qty`,
không đụng logic trần sức mua.

### 1.3 Ràng buộc cứng

- **Hành vi mặc định phải bất biến.** `RiskManager` mặc định `lot_size = 100`, nên
  mọi đường cổ phiếu VN phải cho ra **đúng con số cũ**. Đây là đường đặt lệnh thật
  — sai ở đây là sai bằng tiền.
- Không đổi chữ ký `handle_crossover`.
- Không sửa `trading/risk.py` (gói C-a đã xong, đừng mở lại).

### 1.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tái hiện | test: `handle_crossover` với `RiskManager(lot_size=1)` và một `max_buy_qty` không chia hết 100 ⇒ qty **không** bị làm tròn về bội 100. Test này phải **đỏ trên code hiện tại** |
| 2 | Sửa xong | cùng test ⇒ xanh |
| 3 | **Mặc định bất biến** | test: `lot_size` mặc định ⇒ qty vẫn là bội 100 và vẫn từ chối khi `< 100`. Mọi test `real_orders` hiện có vẫn xanh, **không bị sửa** |
| 4 | Phá hoại | đổi `risk.lot_size` thành hằng 1 ⇒ test 3 **đỏ**; dán nguyên văn output đỏ; khôi phục; `grep -rn "SABOTAGE" trading scripts tests` rỗng |
| 5 | Không hồi quy | cả hai bộ, nền 404 + 100 |
| 6 | Lint | sạch |

**Tiêu chí 3 quan trọng ngang tiêu chí 2.**

### 1.5 Phạm vi

- **Sửa:** `trading/real_orders.py` (chỉ dòng 100-101), `tests/`.
- **Không đụng:** `trading/risk.py`, `trading/engine/*`, `config/config.yaml`,
  bất cứ gì thuộc gói C-b.

---

## 2. GÓI C-b — đo chiến lược trên dữ liệu crypto

### 2.1 Sự thật đã đo — hai giả định cũ của tôi đã SAI, đọc kỹ

**(a) Dữ liệu đã nạp xong rồi.** Tôi từng viết C-b là "thu thập + đo". Không phải:
`scripts/bingx_klines.py` đã tồn tại, có test (`tests/test_bingx_klines.py`), và
bảng `bars_crypto` **đã có dữ liệu**:

```
 so_ma | so_bar |     tu     |    den     | khung
-------+--------+------------+------------+-------
    20 | 412487 | 2021-05-14 | 2026-09-02 | 1d,1h
```

Việc còn lại thuần tuý là **đo**, không phải nạp. Đừng nạp lại.

**(b) Gói I KHÔNG chặn C-b.** Tôi ghi trong bảng tồn đọng là "I phải xong trước
khi C-b dùng `lot_size != 100`" — **sai**. `backtest.py:225` chỉ gọi
`risk.approve_sized`; nó không đi qua `real_orders.py` chút nào. C-b chạy được ngay.

**(c) C-a đã thật sự mở đường.** Đã chạy, không suy luận:

```
gia= 60000.0 atr=1500.0 lot=100 -> TU CHOI: qty sau cap < 1 lo (qty_atr=0, qty_cap=0)
gia= 60000.0 atr=1500.0 lot=  1 -> qty=33
gia=  3000.0 atr=  80.0 lot=100 -> qty=600
gia=     0.5 atr=  0.02 lot=100 -> qty=2500000
```

Với lô 100, tài sản giá cao **biến mất hoàn toàn** khỏi bảng đo trong khi tài sản
giá rẻ lọt qua với 2,5 triệu đơn vị. Đó không phải ít số liệu hơn — đó là **thiên
lệch chọn mẫu im lặng**. Nay đã sửa được.

### 2.2 Chỗ chưa có: không ai đọc `bars_crypto`

`scripts/bingx_klines.py` **ghi** bảng đó, nhưng không có mã nào **đọc** nó.
`_TF_SPEC` trong `trading/backtest.py` chỉ biết `bars` và `bars_daily`.

**Không thêm crypto vào `_TF_SPEC`.** Làm vậy là kéo C-b vào image và mất đi cái
lợi lớn nhất của gói này (chạy được bất cứ lúc nào, không cần dựng lại container).
Viết hàm đọc `bars_crypto` **trong `scripts/`**, rồi truyền list `Bar` vào
`run_backtest` — nó nhận list, không tự truy vấn.

### 2.3 Việc

Một script đo trong `scripts/`, đọc `bars_crypto`, chạy các chiến lược trong
`STRATEGIES` qua `run_backtest`, in bảng kết quả theo từng mã và tổng hợp.

### 2.4 Ràng buộc cứng — bốn cái bẫy đã biết

**(1) Đơn vị tiền.** Giá trong `bars_crypto` là **USDT**. `RiskManager(capital=...)`
mặc định trong repo này là VND (100.000.000). Trộn hai đơn vị cho ra con số vô
nghĩa mà nhìn vẫn hợp lý. **Chọn một số vốn tính bằng USDT và ghi rõ trong báo cáo.**

**(2) Lô.** Dùng `lot_size=1` và **nói rõ trong báo cáo rằng đó là giả định**.
BingX có bước khối lượng riêng cho từng cặp — **đừng đoán**. Nếu cần con số thật
thì lấy từ endpoint công khai và dẫn nguồn, hoặc để nguyên 1 và ghi chú.

**(3) Phí.** **Không đoán phí BingX.** Gói B đã làm `run_backtest` nhận
`fee_rate` / `sell_tax_rate` / `slippage_bps` / `settle_days` (mặc định `None`).
Chạy **không phí** và ghi rõ "chưa tính phí" còn hơn cắm một con số bịa. Kết quả
chưa trừ phí là kết quả **lạc quan**, phải nói ra.

**(4) Thiên lệch sống sót.** 20 mã này là top theo khối lượng **hiện tại**. Đo lùi
về 2021 trên tập chọn theo tiêu chí của 2026 là thiên lệch sống sót kinh điển: các
đồng đã chết không có mặt. **Phải ghi câu này trong báo cáo**, không được để người
đọc tự suy ra.

Thêm: `run_backtest` dùng `calendar_vn` **chỉ để lấy `TZ`** (đã kiểm: dòng 273,
324, 325) — nó sẽ **không** âm thầm vứt nến 24/7 của crypto. Nhưng lệch múi giờ
có thể đẩy nến lệch một nhịp; kiểm bằng cách đếm số nến vào ra phải bằng nhau.

### 2.5 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Đọc được | test: hàm đọc trả đúng số nến cho một mã/khung đã biết; số đếm khớp truy vấn SQL trực tiếp |
| 2 | Không mất nến | test: `len(bars_vào) == len(bars_ra)` qua đường TZ — chống lệch một nhịp |
| 3 | Đo chạy | chạy thật, dán **nguyên văn** bảng kết quả 20 mã |
| 4 | Lô có tác dụng | dán kết quả cùng một mã giá cao với `lot_size=100` và `lot_size=1` cạnh nhau — phải khác nhau, chứng minh thiên lệch đã hết |
| 5 | Bốn cảnh báo | báo cáo có đủ bốn câu: đơn vị USDT, lô là giả định, **chưa trừ phí**, thiên lệch sống sót |
| 6 | Không hồi quy | cả hai bộ, nền 404 + 100 |
| 7 | Lint | sạch |

### 2.6 Phạm vi

- **Sửa:** `scripts/` (script mới), `tests/`.
- **Không đụng:** `trading/backtest.py` (đặc biệt `_TF_SPEC`), `trading/risk.py`,
  `trading/strategies/*`, `config/config.yaml`, `scripts/bingx_klines.py`,
  `trading/real_orders.py` (gói I).
- **Không** nạp lại `bars_crypto`. Nếu thấy thiếu dữ liệu thì **báo cáo**, đừng tự nạp.

---

## 3. Báo cáo — định dạng bắt buộc

1. **Đã làm gì** — theo từng file, kèm số dòng.
2. **Quyết định đã chọn** — mọi chỗ có hai cách hiểu, chọn cách nào, vì sao.
3. **Output test nguyên văn** — cả hai bộ, cả `ruff`. Không tóm tắt.
4. **Output đỏ của phép phá hoại nguyên văn**, cộng `grep -rn "SABOTAGE" trading scripts tests` rỗng.
5. **Phát hiện ngoài phạm vi** — báo, không sửa.
6. **Điều còn chưa chắc** — nói ra, đừng giấu.

Mục 3 và 4 **không thương lượng**. "Đã xong" không phải bằng chứng.

---

## 4. KHÔNG giao cho agent — và vì sao

| Mã | Vì sao không phải việc của agent |
|---|---|
| **J** | Octopus không phát `"bear"` ⇒ bật giao dịch thật sẽ **chỉ mua, không bán**. Sửa được theo hai hướng khác hẳn nhau (nối SELL của `on_bar` vào `real_orders`, hay giữ sma_cross cho đường thật). Đây là **quyết định thiết kế**, chủ dự án chọn hướng rồi mới giao. |
| **C3** | Lịch nghỉ lễ 2026. Chủ dự án cấp ngày, Claude sửa `config.yaml`. **Agent không được bịa ngày lễ.** |
| **D1** | Diễn tập dead-man's switch — cần một phiên thật và cái điện thoại của chủ dự án. Không phải việc code. |
| **E** | Vốn engine đọc 0434221 (5.021.712) trong khi tiền ở 0434226. Đổi tài khoản là quyết định về tiền. |
| **C1, C2, F** | VPS Ubuntu, Docker tự khởi động, phạm vi BingX (spot hay perpetual, có đòn bẩy không). Chủ dự án quyết. |

**Về F, có một dữ kiện mới:** dữ liệu đã nạp lấy từ endpoint
`/openApi/swap/v3/quote/klines` — tức **perpetual swap**, không phải spot. Nếu câu
trả lời của chủ dự án là "spot, không đòn bẩy" thì tập dữ liệu hiện có **không
khớp** và C-b phải đo lại trên dữ liệu khác. Đây là lý do nên trả lời F sớm.

Một mục nhỏ chưa xếp: `Storage.read_account_balance` (`db.py:214`) hiện **không
còn chỗ gọi nào** trong mã sản phẩm — chỉ `read_account_balance_with_debt` được
dùng. Là dead code, nhưng luật cấm agent xoá dead code có từ trước, nên nếu muốn
dọn thì phải giao thành task riêng. Chưa gấp.

---

## 5. Việc KHÔNG làm

- Không bật `real_trading_enabled`, kể cả để thử.
- Không sửa `config/config.yaml`.
- Không thêm crypto vào `trading/backtest.py::_TF_SPEC`.
- Không nạp lại `bars_crypto`, không xoá dòng nào của nó.
- Không đoán phí BingX, không đoán bước khối lượng, không đoán ngày nghỉ lễ.
- Không đụng `trading/risk.py` hay `trading/strategy.py` — hai gói đó đã đóng.
- Không commit, không push.
