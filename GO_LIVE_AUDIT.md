# Audit go-live — 2026-08-13

Kiểm tra toàn tuyến: **lấy dữ liệu → sinh tín hiệu → đẩy lệnh lên sàn**.
Mọi kết luận dưới đây đều dựa trên code đã đọc hoặc số đo thật, không dựa vào
tài liệu cũ trong repo.

HEAD tại thời điểm audit: `2b6fd06`, nhánh `feature/data-layer`.

> **Tài liệu này là bản ghi theo thời điểm.** Phần thân giữ nguyên như lúc
> audit; những chỗ về sau chứng minh là **sai** hoặc **đã xử lý** được đính
> chính tại chỗ bằng khối `> ĐÍNH CHÍNH`. Không xoá kết luận cũ — biết mình đã
> sai ở đâu cũng là thông tin.

---

## Trạng thái — cập nhật 2026-08-13, 22:45

| Mục | Lúc audit | Bây giờ |
|---|---|---|
| Chặn 1 — vốn đặt lệnh | "sai đơn vị" | **Chẩn đoán sai.** 21459 là số dư THẬT. Vẫn chặn, vì vốn thiếu chứ không phải cấu hình sai |
| Chặn 2 — `account_position_snapshot` rỗng | "collector chưa chạy đủ lâu" | **Chẩn đoán sai.** Là bug code, đã sửa `e20e647`. Bảng có dữ liệu thật |
| Rủi ro 3 — lệnh thật không có stop-loss | mở | **Đã nối** `ff3a26b` (cảnh báo chạm stop, không phải cắt lỗ tự động) |
| Rủi ro 4 — restart mất trailing stop | mở | **Đã sửa** `7b5d6aa` |
| Rủi ro 5 — restart làm chiến lược mù ~1h45' | mở | **Đã sửa** `2665d48` |
| `real_order_capital` trong config | `21459` (khoá cố ý) | **Bỏ hẳn khỏi config** `63e6028` — engine đọc số dư thật từ `account_balance_snapshot` (withdrawable). Lớp khoá còn lại: `real_trading_enabled: false` |
| Rổ mã giao dịch | `[VCB, HPG, TCB]` | **Đổi sang `[HII, IJC, AAA]`** `63e6028` — VCB/HPG/TCB đều vượt trần 1 lô với số dư ~5 triệu |
| Test ghi vào bảng thật | nêu ở mục "Dữ liệu hiện tại" | **Đã tách hạ tầng** `51eb353` |

**Mọi rào cản KỸ THUẬT trong bản audit này đã gỡ.** Thứ còn chặn go-live không
còn là code — là **vốn**. Xem "Chặn số 1" bên dưới.

---

## Kết luận ngắn

**CHƯA sẵn sàng go-live.** Đường đặt lệnh thật hiện **không thể sinh ra một
lệnh nào**, vì hai lý do độc lập, mỗi lý do đủ để chặn hoàn toàn.

Tin tốt: kiến trúc an toàn (người bấm nút, không tự đặt lệnh), và cả hai lỗi
đều nằm ở cấu hình/vận hành chứ không phải thiết kế.

---

## Quyết định của chủ dự án — 2026-08-13

**1. Giữ nguyên `real_order_capital: 21459` → khoá hẳn đường đặt lệnh thật.**

Đây là **quyết định có ý thức**, không phải sót. Hệ quả: `RiskManager.approve()`
từ chối mọi lệnh BUY, nên `real_orders.handle_crossover()` không bao giờ sinh
lệnh. Đường đặt lệnh thật là code chết, cố ý.

Rủi ro của cách khoá này (ghi lại để người sau không đạp phải): khoá **ngầm**
qua một con số vốn phi lý, chồng lên khoá **tường minh** `real_trading_enabled:
false`. Ai đó bật `real_trading_enabled: true` sẽ thấy hệ thống im lặng không
làm gì và không hiểu tại sao; hoặc tệ hơn, "sửa" capital cho hợp lý mà không
biết rằng làm vậy là mở khoá giao dịch thật.

Giảm thiểu: engine cảnh báo `CRITICAL` lúc khởi động nếu `real_trading_enabled`
là `true` mà trần giá trị lệnh không mua nổi một lô của bất kỳ mã nào trong
`symbols`. Khi `real_trading_enabled=false` thì im lặng — vì khi đó tình trạng
này chính là trạng thái mong muốn.

**2. Nối trailing stop vào luồng thật trước khi go-live** (xem rủi ro 3).

> **ĐÍNH CHÍNH — con số 21459 không phi lý.** Nó là **số dư thật** của tài
> khoản `0434221` (đo qua API SSI, `accountBalance` = `withdrawable` = 21.459).
> Vậy đây không phải "khoá ngầm bằng một con số vô lý" — nó chỉ đơn giản phản
> ánh đúng số tiền trong tài khoản. Phần cảnh báo `CRITICAL` vẫn có giá trị,
> nhưng lý do tồn tại của nó khác với những gì viết ở trên.

---

## Chặn số 1 — `real_order_capital` sai đơn vị: MỌI lệnh BUY bị từ chối

> **ĐÍNH CHÍNH 2026-08-13 — TIÊU ĐỀ NÀY SAI. Không có lỗi đơn vị nào.**
>
> Đo trực tiếp qua API SSI (`EP_ACCOUNT_BALANCE`, chỉ đọc):
>
> ```
> 0434221:  accountBalance 21.459     withdrawable 21.459
> ```
>
> `21459` là **số dư thật** của tài khoản, không phải "21,459 triệu viết theo
> đơn vị nghìn". Toàn bộ đoạn suy đoán về đơn vị bên dưới là **sai**.
>
> **Chặn vẫn còn, nhưng vì lý do khác: tài khoản không đủ tiền.**
>
> Chiều 2026-08-13 chủ dự án chuyển 5 triệu từ `0434226` sang. Số dư mới:
> `5.021.459` (và `0434226` giảm đúng 5 triệu, còn `2.429.181`).
>
> Vẫn không mua nổi một lô:
>
> ```
> trần giá trị lệnh = 5.021.459 × 0,20 = 1.004.292 VND
> lô rẻ nhất        = HPG 100 × 22.150 = 2.215.000 VND
> ```
>
> **Vốn tối thiểu để mua nổi 1 lô** (theo giá đóng cửa 2026-08-13):
>
> | Mã | Giá | 1 lô | Vốn tối thiểu |
> |---|---|---|---|
> | HPG | 22.150 | 2.215.000 | **11.075.000** |
> | TCB | 32.000 | 3.200.000 | **16.000.000** |
> | VCB | 60.100 | 6.010.000 | **30.050.000** |
>
> Muốn giao dịch cả ba mã trong `config.symbols` cần khoảng **30 triệu**.
>
> **Và một chi tiết dễ sập bẫy:** `RiskManager(capital=cfg.real_order_capital)`
> đọc **con số trong `config/config.yaml`**, không đọc số dư thật từ SSI. Nạp
> tiền vào tài khoản **không thay đổi gì** cho tới khi con số trong config được
> cập nhật.

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

~~Con số 21459 gần như chắc chắn là **21.459 triệu đồng** viết theo đơn vị nghìn~~
— **sai, xem đính chính ở đầu mục.**

**Vì sao chưa ai phát hiện:** toàn bộ test dùng `real_order_capital=1_000_000_000.0`
(1 tỷ) hoặc `0` — xem `tests/test_real_orders.py:37`, `tests/test_confirm_real_order.py:38`,
`tests/test_engine_main.py:45`. **Không test nào chạy với giá trị thật trong
config.** `tests/test_config.py:36` có assert `== 21459` nhưng chỉ kiểm tra việc
đọc file, không kiểm tra hệ quả.

**Cần làm:** chủ dự án xác nhận số vốn thật rồi sửa `config/config.yaml`. Đây
là quyết định về tiền, không phải quyết định kỹ thuật — không ai được sửa hộ.

---

## Chặn số 2 — `account_position_snapshot` rỗng: MỌI lệnh SELL bị chặn

> **ĐÍNH CHÍNH 2026-08-13 — nguyên nhân chẩn đoán SAI, và sự thật lớn hơn.**
>
> Không phải "collector chưa chạy đủ lâu". Đó là **bug code**, lộ ra ngay lần
> đầu bật lại stack: API trả HTTP 200 rồi crash lúc parse.
>
> ```
> GET .../trading/position?accountNo=0434221 "HTTP/1.1 200 OK"
> {"level": "WARN", "msg": "account sync failed, skipping",
>  "error": "'NoneType' object is not iterable"}
> ```
>
> SDK trả `None` cho danh mục rỗng (`ssi_sdk/models/portfolio.py:322,336`;
> docstring của chính SDK: *"absent or empty sections yield None"*) dù annotation
> ghi `-> list[EquityPosition]`. `0434221` đang rỗng nên đây là đường chạy **mặc
> định**, không phải hiếm.
>
> **Thiệt hại kèm theo nghiêm trọng hơn bug gốc:** exception thoát khỏi vòng
> `for account_no`, nên `0434226` **không bao giờ được đồng bộ**. Sửa xong
> (`e20e647`) thì lộ ra:
>
> ```
> account_balance_snapshot:  0434226  7.429.181 VND   <-- LẦN ĐẦU XUẤT HIỆN
>                            0434221     21.459 VND
> account_position_snapshot: 6 dòng, TẤT CẢ thuộc 0434226
>   CAP 1200 | HCM 1000 | SSI 1200 | TCX 160 | VCB 1500 | MIRHCM261 1000
> ```
>
> Tài khoản `0434226` đang nắm khoảng **200 triệu VND cổ phiếu thật**, và hệ
> thống chưa bao giờ nhìn thấy nó.
>
> **CẢNH BÁO cho người sau:** `config.real_order_account` trỏ vào `0434221`
> (rỗng). Tiền và cổ phiếu nằm ở `0434226`. **VCB vừa nằm trong
> `config.symbols` vừa được nắm thật 1500 cp ở `0434226`** — nếu ai đó đổi
> `real_order_account` sang `0434226`, logic crossover và trailing stop sẽ bắt
> đầu sinh lệnh SELL lên một vị thế thật ~91 triệu. Đây là thay đổi cấu hình
> nguy hiểm nhất hiện có trong repo.
>
> Lưu ý: `read_real_positions("0434221")` **vẫn** trả `{}` vì tài khoản đó
> không có vị thế nào. Chặn SELL cho tài khoản đang cấu hình vẫn còn — nhưng
> giờ là do tài khoản trống, không phải do bảng trống.

```sql
SELECT account_no, count(*) FROM account_position_snapshot GROUP BY 1;
-- (0 rows)
```

`trading/storage/db.py:481` `read_real_positions()` đọc bảng này. Rỗng → trả về
`{}` → trong `trading/real_orders.py:35-37`, `sellable = 0` → `return` ngay,
không bao giờ sinh lệnh SELL.

Bảng này do `trading/collector/account_sync.py::sync_account_data` ghi, chạy
trong `collector/main.py:100-103`. ~~**Collector chưa từng chạy đủ lâu để đồng bộ
tài khoản.**~~ — **sai, xem đính chính ở đầu mục.**

Hệ quả kép: nhánh BUY ở `real_orders.py:31` cũng dùng chính dữ liệu này để biết
"đã nắm giữ chưa". Rỗng nghĩa là hệ thống **luôn tưởng tài khoản không nắm giữ
gì** — nếu chặn số 1 được gỡ mà chặn này còn, hệ thống có thể mua trùng mã đang
có.

**Cần làm:** chạy collector một phiên đầy đủ, rồi xác minh bảng có dữ liệu
TRƯỚC khi bật `real_trading_enabled`.

---

## Rủi ro số 3 — Giao dịch thật KHÔNG có stop-loss

> **ĐÃ XỬ LÝ — `ff3a26b`.** Chủ dự án chọn nối trailing stop vào luồng thật.
> `real_orders.handle_stop_touch()` chạy mỗi bar, khởi tạo tracking cho vị thế
> mở giữa phiên, dùng `sellable_qty` (T+2,5), không sinh lệnh trùng.
>
> **Vẫn KHÔNG phải cắt lỗ tự động.** Nó chỉ ghi một lệnh SELL chờ xác nhận +
> cảnh báo; đặt lệnh vẫn là `scripts/confirm_real_order.py` chạy tay, phải gõ
> `YES` trong 15 phút. Người vận hành vắng mặt = lệnh hết hạn, vị thế nguyên.
> Ai tin nhầm rằng đã có phanh tự động sẽ nguy hiểm hơn là không có tính năng.

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

> **ĐÃ SỬA — `7b5d6aa`.** Engine tái dựng `_highest` lúc khởi động cho cả luồng
> paper (`read_highest_since_buy`) lẫn luồng thật (`read_real_highest_since_buy`,
> lọc theo `account_no`). Không tái dựng được → `alert("WARN")` nêu rõ mã, không
> im lặng.

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

> **ĐÃ SỬA — `2665d48`.** Engine nạp `SmaCrossStrategy.warmup_bars`
> (`max(slow, atr_period) + 1` — số bar do chiến lược quyết, không hardcode)
> từ bảng `bars` lúc khởi động, bằng `compute_crossover()` chứ không qua
> `process_bar()` nên bar lịch sử không đi qua broker. Thiếu lịch sử → `WARN`
> nêu rõ mã.
>
> Kèm một cái bẫy phải chặn: consumer `engine` là **durable**, khi restart
> JetStream giao lại bar chưa ack — mà bar đó cũng vừa được warm-up nạp. Không
> chặn thì cùng một bar vào `_closes` hai lần, lệch cửa sổ MA, biến chiến lược
> "mù" thành chiến lược **sai**. Đã chặn bằng `warmed_until[symbol]`.

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

## Phát hiện thêm sau bản audit gốc

### Test ghi đè state của hệ thống thật — đã tách (`51eb353`)

Suite chạy trên **đúng DB và đúng NATS** mà hệ thống thật đang phục vụ. Đo
được: `engine_state` của engine thật bị ghi đè bằng dữ liệu test, durable
consumer `engine` **bị xoá** (engine mất đường nhận bar mà heartbeat vẫn tươi
— nhìn ngoài tưởng khoẻ), stream `BARS` bị purge.

Cùng nguyên nhân đó sinh ra flake theo đuổi từ 2026-08-10: engine subscribe
`bars.>` nên bất kỳ nguồn nào publish vào `BARS` lúc test chạy đều ăn budget
`max_messages`. Đo: hai suite song song = **10 phút 46 + fail**; một suite =
**14,6 giây + 260 passed**.

Đã tách: DB `trading_test` + NATS riêng cổng 4223 (`--profile test`), kèm hàng
rào `pytest.exit()` từ chối chạy nếu trỏ vào hạ tầng sản xuất.

### Access token in nguyên văn ra log — đã bịt (`e20e647`)

`ssi_sdk/transport/websocket_client.py:76` log `Authorization: Bearer <token>`
plaintext ở mức INFO. Token sống 15 phút nhưng log được giữ lâu hơn nhiều.

### Token lưu ở HAI nơi và chúng lệch nhau

`spike_ssi_sdk_auth.py` (OTP) ghi `scripts/.ssi_sdk_token.json`; collector đọc
bảng `ssi_auth_state` trong Postgres và **không bao giờ đọc file**.
`scripts/load_token_to_db.py` là cầu nối duy nhất.

Bỏ qua bước đó thì DB giữ token cũ trong khi file đã mới, và **thông báo lỗi
dẫn người ta đi sai hướng**: nó bảo "chạy lại `spike_ssi_sdk_auth.py`" trong
khi làm OTP lại không thay đổi gì. Đây là nguyên nhân collector chết 5 ngày
(07/08 → 13/08).

### Dead-man's switch đã thử thật (B2, 2026-08-13 phiên chiều)

Giết collector 13:51:32, phục hồi 13:57:22:

- stack khoẻ → `exit 0` (không kêu oan)
- chết 35s (dưới ngưỡng 300) → `exit 0` (ngưỡng có tác dụng)
- chết 320s → `exit 1`, `stale = ['collector']`, engine lag 42s **không bị tố nhầm**
- phục hồi → `exit 0`, bar lấp đầy

**Chứng minh:** logic phát hiện chạy đúng.
**KHÔNG chứng minh:** nó đang được lên lịch chạy. `DEPLOYMENT.md` §9 nói dùng
cron trên host; máy dev là Windows không có cron. **Trên VPS phải kiểm riêng.**

### Collector phục hồi heartbeat chậm sau gián đoạn DB — cải thiện một phần

Dừng postgres 4 phút rồi bật lại: trước `~90s`, sau `2665d48` đo được `44–61s`
(dao động theo pha chu kỳ). Kỳ vọng đặt ra là ≤40s — **chưa đạt**.

Nguyên nhân phần còn lại đã tìm ra, log có cả hai loại timeout:

```
6 x "couldn't get a connection after 5.00 sec"    <- beat(), đã sửa
4 x "couldn't get a connection after 30.00 sec"   <- còn nguyên
```

Chỗ 30 giây còn lại là `ensure_authenticated()` đọc token từ DB trong
`sync_account_data`, chạy cùng tick ngay sau `beat()` — không chặn cú beat
nhưng đẩy lùi tick kế tiếp. **Chưa sửa**: biên so với ngưỡng 300s đã tăng từ
3,3 lên ~5 lần, và sửa tiếp sẽ chạm vào đường xác thực SSI.

### `save_account_positions` bỏ qua danh mục rỗng — CHƯA SỬA

`db.py:330` có `if not positions: return`. Khi tài khoản bán hết sạch danh mục,
snapshot rỗng **không bao giờ được ghi**, nên `read_real_positions()` (đọc
`max(ts)`) **vĩnh viễn trả về vị thế cũ** — hệ thống tưởng vẫn đang nắm giữ.

Trớ trêu là docstring `db.py:549-551` giải thích rất kỹ rằng họ *cố ý* không
correlate theo symbol để tránh đúng chuyện đó.

Hiện chưa gây hại vì tài khoản cấu hình đang rỗng. Nó thành nguy hiểm đúng vào
lúc bắt đầu giao dịch thật. Sửa là **quyết định thiết kế** (ghi dòng sentinel?
bảng "lần sync cuối" riêng?), không phải một guard — để chủ dự án quyết.

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
| Test suite | ~~242 passed~~ → **265 passed**, ruff sạch |
| Đường ống E2E | Đo 2026-08-13: SSI → collector → DB + NATS → engine, `delivered = ack_floor`, `pending 0`, `redelivered 0` |

---

## Dữ liệu hiện tại

> **CẬP NHẬT 2026-08-13, 22:45** — số liệu gốc bên dưới đã cũ.
>
> ```
> bars (13/08)              49 bar/mã cho VCB/HPG/TCB, 09:00 → 14:45, KHÔNG thủng
>                           (49 = 30 phiên sáng + 18 phiên chiều + 1 bar ATC 14:45;
>                            14:30–14:40 không có bar là ĐÚNG — đó là phiên ATC)
> account_position_snapshot 6 dòng, tất cả của 0434226 (dữ liệu thật)
> pending_real_orders       0 dòng rác — fixture đã tự dọn (7b5d6aa, 51eb353)
> ssi_auth_state            refresh token hết hạn 17:43 ngày 13/08
> ```
>
> `symbol_universe` (302 mã) vẫn cũ từ 07/08 — cần token SSI sống để backfill.
> Chỉ ảnh hưởng `screen_liquidity.py`, không ảnh hưởng ba mã đang giao dịch.

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

> **ĐÃ XỬ LÝ phần lớn (`a013b28`)** — gốc repo giờ chỉ còn `README.md`,
> `DEPLOYMENT.md`, `CLAUDE.md`, `AGENTS.md`, `GO_LIVE_AUDIT.md`.
> `PROMPT_EXECUTE_*.md` → `docs/prompts/`; `PLAN_*.md` → `docs/plans-legacy/`;
> `archive/` và `DEPLOYMENT_READINESS.md` đã xoá.
>
> **MỘT ĐỀ XUẤT DƯỚI ĐÂY LÀ SAI — ĐỪNG LÀM THEO:** gom `scripts/spike_*.py` vào
> `scripts/spikes/`. Đề xuất đó đưa ra mà chưa kiểm tham chiếu.
> `trading/collector/ssi_auth.py:44` là một **thông báo lỗi trong code sản
> xuất** trỏ thẳng tới đường dẫn đó — dòng người vận hành đọc đúng lúc xác thực
> hỏng. Cộng thêm `ssi_auth.py:6,36`, `scripts/_ssi_spike_common.py` (4 chỗ) và
> 5 tài liệu trong `docs/plans-legacy/`. Chuyển thư mục biến tất cả thành đường
> dẫn chết.

| Nhóm | Số file | Đề xuất |
|---|---|---|
| `PROMPT_EXECUTE_*.md` ở gốc | 32 | Chuyển vào `docs/prompts/` hoặc xoá — việc đã xong |
| `PLAN_*.md` ở gốc | 6 | Chuyển vào `docs/plans/` |
| `archive/` | 8 | Xoá |
| `DEPLOYMENT_READINESS.md` | 1 | **Xoá hoặc viết lại** — xem dưới |
| `scripts/spike_*.py` | 13 | ~~gom vào `scripts/spikes/`~~ — **KHÔNG, xem đính chính** |

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

> Chính vì lý do này mà tài liệu bạn đang đọc được đính chính chứ không bị xoá
> phần sai: một bản audit khẳng định sai còn nguy hiểm hơn không có audit.

---

## Luồng paper không thể mua — phát hiện 13/08 khuya (`95b84d9`)

> ĐÍNH CHÍNH quan trọng: phát hiện này lật ngược giả định "mọi rào cản kỹ
> thuật đã gỡ". Luồng PAPER không thể mua về mặt số học — không phải do vốn.

approve_sized áp hai luật chống nhau:
```
qty        = capital * risk_pct / (atr * atr_multiplier)      # 0,01 va 2,0
rang buoc:   ref_price * qty <= capital * max_order_value_pct # 0,20
Thay qty vao, CAPITAL TRIET TIEU ca hai ve:
  ref_price / atr <= 40   <=>   atr / ref_price >= 2,5%
```

ATR/giá CAO NHẤT từng đạt trên bar 5 phút:
```
  HII 2,003%  |  IJC 1,350%  |  AAA 0,937%   -> KHONG bar nao dat 2,5%
```

Điều này giải thích vì sao `orders` chỉ có 1 dòng từ 15/07 và engine chạy
trọn phiên 13/08 sinh 0 lệnh. Crossover CÓ xảy ra (9–56 lần mỗi mã qua được
bộ lọc ATR) rồi bị vứt im lặng ở khâu sizing.

Đường lệnh THẬT không dính: `real_orders.handle_crossover()` gọi `approve()`
với `qty=100` cố định, chỉ kiểm trần 20%.

Đã sửa bằng `qty = min(qty_atr, qty_cap)`, kèm đánh đổi: khi vướng trần,
rủi ro mỗi lệnh nhỏ hơn `risk_pct` — không còn là hằng số, nhưng chỉ nhỏ đi.

## Backtest sau khi gỡ bế tắc

sma_cross, 5m, 2026-04-03 -> 2026-08-07, không chỉnh một tham số nào:
```
  HII,IJC,AAA / 5.021.459    24 lenh  win  8,3%  PnL   -153.067   MaxDD 3,8%
  HII,IJC,AAA / 1 ty         16 lenh  win  6,2%  PnL -32.571.418  MaxDD 4,1%
  VCB,HPG,TCB / 5.021.459     0 lenh  (1 lo VCB ~6tr > tran 1,004tr — dung so hoc)
  VCB,HPG,TCB / 1 ty         17 lenh  win 52,9%  PnL  -6.094.804  MaxDD 1,9%
```

Cả bốn cấu hình đều lỗ.

Hai quan sát, chưa kết luận:
- lỗ trung bình mỗi lệnh RUN 1 = -6.378 trên lệnh ~860.000 = -0,74%; phí vòng
  khứ hồi VN ~0,3-0,4% cộng slippage chiếm phần lớn con số đó
- RUN 2 có ít giao dịch hơn RUN 1 (16 vs 24) dù vốn gấp 200 lần
## Thứ tự đề xuất

> **CẬP NHẬT 2026-08-13, 22:45 — mục 3, 4, 5, 6, 7 đã xong.** Còn lại:
>
> 1. **Chốt `real_order_capital`** — chặn duy nhất còn lại, và là quyết định về
>    tiền. Cần ~11 triệu cho HPG, ~30 triệu cho cả ba mã. Nhớ: engine đọc con số
>    trong config, **không** đọc số dư thật.
> 2. **Quyết định về `real_order_account`** — `0434221` (rỗng) hay `0434226`
>    (có ~200 triệu cổ phiếu thật, trong đó 1500 VCB trùng `config.symbols`).
> 3. **Quyết định cách sửa `save_account_positions`** với danh mục rỗng.
> 4. **Kiểm cron dead-man's switch trên VPS** — chưa từng xác minh ở đó.
> 5. Chạy một phiên đầy đủ với token còn hạn, xác minh `account_position_snapshot`
>    cập nhật liên tục **TRƯỚC** khi bật `real_trading_enabled`.
>
> Chỉ sau (1), (2), (5) mới có thể nói tới việc bật `real_trading_enabled: true`.

> **CẬP NHẬT 2026-08-14 — câu chốt trên không còn đúng:** Câu hỏi chặn đường bây giờ không phải "khi nào bật tiền thật" mà là "chiến lược này có biên lợi thế không" — vì nó đã được đo là lỗ trên 4 tháng dữ liệu gần nhất.

1. **Chốt `real_order_capital`** (quyết định của chủ dự án — về tiền)
2. **Chạy collector một phiên đầy đủ**, xác minh `account_position_snapshot` có dữ liệu
3. **Quyết định về stop-loss cho lệnh thật** (rủi ro 3)
4. Sửa mất trailing stop sau restart (rủi ro 4)
5. Nạp lịch sử SMA lúc khởi động (rủi ro 5)
6. Cho test tự dọn `pending_real_orders`
7. Dọn rác repo + xoá/viết lại `DEPLOYMENT_READINESS.md`

Chỉ sau (1) và (2) mới có thể nói tới việc bật `real_trading_enabled: true`.
