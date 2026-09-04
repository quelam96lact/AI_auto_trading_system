# Plan xử lý tồn đọng — sau phiên 03/09

Viết 15:50 ngày 03/09, sau khi `trading/` mở khoá. Mọi số dưới đây đã đo, không
phỏng đoán.

---

## 0. Ràng buộc định đoạt thứ tự: **mai 04/09 là phiên giao dịch**

Đây là điều quan trọng nhất và nó không phải kỹ thuật, mà là lịch. Mọi thay đổi
chạm `trading/` đều phải dựng lại container, tức **mai lại là "phiên đầu tiên
chạy image mới"** — đúng tình huống hôm nay vừa tìm ra hai lỗi.

Hai lựa chọn, và tôi khuyến nghị rõ ràng:

| | Sửa tối nay | Chờ tới tối thứ Sáu |
|---|---|---|
| Được | hết chuông giả 13:00; NAV thôi ghi sai mỗi 5 phút | mai là phiên sạch, không thêm biến |
| Mất | mai lại là phiên "image mới" | thêm một ngày chuông kêu láo + NAV sai |

**Khuyến nghị: sửa tối nay, nhưng CHỈ gói A và B dưới đây.** Lý do quyết định là
chuông báo: một CRITICAL giả **mỗi ngày lúc 13:00** là cỗ máy sinh ra thói quen
bỏ qua cảnh báo. Dead-man's switch mất giá trị đúng vào lúc người ta thôi tin
nó. Để thêm một ngày là trả giá đắt hơn rủi ro dựng lại image.

**Rủi ro phải nói thẳng:** mai vẫn là phiên chạy image mới. Nhưng gói A và B
**không chạm một dòng nào** trên đường dữ liệu (feed, parser, aggregator, NATS)
— đúng phần đã hỏng sáng nay. Đó là khác biệt kiểm chứng được, không phải lời
trấn an: nếu mai stream lại đứt, nguyên nhân **không thể** là hai gói này.

**B1, B2 và BingX giai đoạn 2 KHÔNG làm tối nay** — lý do ở mục 4.

---

## 1. Bảng tồn đọng sau hôm nay

| Mã | Việc | Chạm gì | Khi nào |
|---|---|---|---|
| **A** | Thời gian thị trường: NAV + chuông 13:00 | `trading/` + `scripts/` | **tối nay** |
| **B** | `run_backtest` nhận tham số phí/thanh toán | `trading/` (không chạm engine) | **tối nay** |
| **B1** | Hợp đồng chiến lược + sổ đăng ký + conformance test | `trading/` (chạm engine) | tối thứ Sáu |
| **B2** | Gộp `_print_safe` vào `trading/alerts.py` | `trading/` + 3 script | tối thứ Sáu |
| **C** | BingX giai đoạn 2 — đo chiến lược trên crypto | ~~chỉ `scripts/`~~ **SAI — xem mục 5** | cuối tuần |
| **D1** | Diễn tập dead-man's switch | không sửa code | phiên KHÔNG phải 04/09 |
| **E** | Vốn engine lấy từ 0434221 trong khi tiền ở 0434226 | `config.yaml` | chờ chủ dự án |
| **I** | `real_orders.py:100` là bản sao thứ hai của phép làm tròn lô (100 cứng) | `trading/real_orders.py` — **đường đặt lệnh thật** | trước khi C-b dùng `lot_size != 100` |

**Cập nhật 04/09 tối:** A, B, B1, B2 và C-a đã xong và đã push. H (mã trong cửa
sổ thanh toán T+2 phải được nạp giá) cũng xong — `fafd531`. Nền test mới:
**403 unit + 100 integration**. Xem `2026-09-04-brief-giao-viec-dot-toi-04-09.md`
mục 8 để biết kết quả audit và hai phát hiện mới.

**Mục I sinh ra từ đợt này.** C-a làm `lot_size` thành tham số của
`RiskManager`, nhưng `real_orders.py:100` vẫn `// 100 * 100` cứng và áp SAU
`approve_sized`. Hôm nay không sai (đường này chỉ chạy cổ phiếu VN), nhưng ai
đặt `lot_size=1` sẽ thấy `risk.py` tôn trọng còn dòng kia lặng lẽ áp lại 100 —
đúng kiểu con số sai mà nhìn vẫn hợp lý. Phải xử trước khi gói C-b dựa vào
`lot_size`.

---

## 2. GÓI A — thời gian thị trường (agent A, tối nay)

### 2.1 Vì sao gộp hai lỗi vào một gói

Hôm nay tìm được hai lỗi trông khác nhau nhưng **cùng một hình dạng**:

| Chỗ | Đang đếm | Phải đếm |
|---|---|---|
| `trading/storage/db.py:751` | ngày **lịch** (`(now - ts).days`) | ngày **giao dịch** |
| `scripts/heartbeat_check.py:102` | phút **đồng hồ** | phút **trong phiên** |

Tách thành hai bản vá riêng là sinh ra hai công thức cho cùng một khái niệm —
đúng thứ kỷ luật một-công-thức-một-nơi (`4ea4c8d`) sinh ra để diệt. **Một hàm
chung, hai chỗ gọi.**

### 2.2 Nhà của hàm chung: `trading/calendar_vn.py`

Module này đã giữ `SESSIONS` và `is_trading_time` — nó là nơi duy nhất biết
phiên VN dài bao lâu. Thêm vào đây, không tạo module mới.

Hai hàm cần có (tên do agent chọn, miễn nói đúng việc):

- số **ngày giao dịch** giữa hai mốc, có tính ngày lễ
- số **phút trong phiên** giữa hai mốc, có tính nghỉ trưa và ngày lễ

### 2.3 QUAN TRỌNG — không được import `calendar_vn` vào `db.py`

`trading/storage/db.py` hiện **trung lập với thị trường** (khảo sát BingX mục 5
đã đo). Kéo lịch VN vào tầng lưu trữ là chặn đường crypto 24/7 sau này.

`compute_nav` đã nhận `price_fn` là hàm tiêm vào — **theo đúng khuôn đó**: tiêm
thêm một hàm/vị từ tính tuổi giá, để tri thức về lịch VN nằm ở
`trading/collector/account_sync.py` (vốn đã gắn chặt SSI/VN). `db.py` không được
biết ngày lễ là gì.

Nếu agent thấy cách khác gọn hơn mà vẫn giữ `db.py` trung lập, **báo cáo trước
khi làm**, đừng tự đổi hướng.

### 2.4 Ràng buộc sống còn — `heartbeat_check.py` là dead-man's switch

**FEE-ALARM-2 nguyên vẹn: nó không bao giờ được ném exception.** Một chuông chết
lặng lẽ tệ hơn không có chuông. Mọi đường mới thêm vào phải nằm trong lớp bảo vệ
sẵn có; nếu hàm mới có thể ném, chỗ gọi phải nuốt và **vẫn kêu**, không được im.

Không đổi ngưỡng `DEFAULT_STALE_BAR_MINUTES` (15 phút). Việc ở đây là **đổi đại
lượng đo**, không phải nới ngưỡng. Nới ngưỡng là che triệu chứng và sẽ hở lại ở
09:00 cũng như phiên đầu sau ngày lễ.

### 2.5 Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Hàm chung + test | test riêng cho: qua nghỉ trưa, qua đêm, qua cuối tuần, qua ngày lễ |
| 2 | Chuông 13:00 hết kêu giả | test tái hiện **đúng** 13:00:03 ngày 03/09 (bar cuối 11:25) ⇒ **không** CRITICAL |
| 3 | Chuông vẫn kêu khi feed chết thật | test: 13:00 mà bar cuối là 09:30 ⇒ **vẫn** CRITICAL |
| 4 | NAV 0434226 ra số đúng | chạy lại `_sync_nav`, NAV ≈ **131.580.152**, `unpriced_symbols` **rỗng** |
| 5 | NAV 0434221 KHÔNG đổi | vẫn `5.021.459`, `unpriced_symbols` rỗng (xem 2.6) |
| 6 | Phá hoại | với test 2 và test 3: phá code cho đỏ, **dán nguyên văn output đỏ**, khôi phục |
| 7 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm (nền: 370 passed) |
| 8 | Lint | `uv run ruff check trading tests scripts` sạch |

**Tiêu chí 3 quan trọng ngang tiêu chí 2.** Sửa cho chuông thôi kêu giả mà làm
nó câm luôn khi feed chết thật là đổi một lỗi lấy một lỗi tệ hơn nhiều.

### 2.6 Hai cạm bẫy đã biết — đọc trước khi sửa

**(a) Nợ và giá phải sửa CÙNG LÚC.** `account_sync.py:143` truyền `debt=0.0`
cứng, trong khi `total_debt = 68.607.848` **đã nằm sẵn** trong
`account_balance_snapshot`. Nhưng sửa riêng phần nợ cho NAV = 0 − 68,6tr =
**âm 68,6 triệu**, tệ hơn hiện tại vì số âm sâu có thể chạm logic rủi ro. Sửa cả
hai lớp trong một lần.

Số nghiệm thu (tính từ DB, giá đóng cửa 28/08): cổ phiếu 200.188.000 − nợ
68.607.848 = **131.580.152**, xê dịch theo giá 04/09.

**(b) 0434221 KHÔNG có lỗi — đừng "sửa" nó.** Đã đo hai lần (10:20 và cuối
phiên): `unpriced_symbols` của 0434221 **rỗng**, và `account_position_snapshot`
cho thấy 0434221 **không giữ mã thật nào** (toàn bộ ở 0434226). NAV = 5.021.459
= `withdrawable` là **đúng**. HII 300 là vị thế **giấy**, không đi qua
`compute_nav`. Có tài liệu trước đây nói HII bị loại khỏi định giá — **sai**, đã
đính chính.

### 2.7 Phạm vi phẫu thuật

- **Được sửa:** `trading/calendar_vn.py`, `trading/collector/account_sync.py`,
  `scripts/heartbeat_check.py`, `tests/`.
- **Chỉ được sửa `db.py` nếu** việc đó làm `compute_nav` **bớt** biết về lịch,
  không phải biết thêm.
- **Không đụng:** `config/config.yaml`, `trading/engine/*`, `trading/collector/`
  (ngoài `account_sync.py`), `trading/broker.py`, `trading/paper_broker.py`.
- Không commit, không push. Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không in giá trị bí mật. Ngoài phạm vi thì
  **báo cáo, không tự sửa**.

---

## 3. GÓI B — `run_backtest` nhận tham số phí (agent B, tối nay)

### 3.1 Vì sao gói này an toàn để chạy song song

Đã kiểm bằng grep: **engine không import `trading/backtest.py`** — chỉ `scripts/`
và `derivative_backtest.py` dùng. Nên sửa `backtest.py` không thể ảnh hưởng
phiên 04/09.

Nhưng engine **có** import `trading/paper_broker.py`. Đó là ranh giới của gói
này, và nó là ràng buộc cứng ở 3.3.

Hai gói A và B **không dùng chung file nào** ⇒ chạy song song không đụng nhau.

### 3.2 Việc

`trading/backtest.py:172` viết `broker = PaperBroker(capital)` — đóng cứng. Nên
mọi backtest đều áp luật thị trường VN: `FEE_RATE = 0.0025`,
`SELL_TAX_RATE = 0.001` (thuế bán), `SETTLE_DAYS = 3` (T+2,5).

Đo crypto bằng hàm này sẽ **âm thầm áp thuế bán và chu kỳ thanh toán không tồn
tại** lên dữ liệu crypto. Con số ra sẽ sai mà trông vẫn hợp lý — kiểu hỏng tệ
nhất.

Việc: cho `run_backtest` nhận được phí/thuế/số ngày thanh toán, **mặc định
giữ nguyên đúng giá trị VN hiện tại**. `SETTLE_DAYS` đang là hằng số mức module
trong `paper_broker.py` — đó là chỗ khó thật sự của gói này, không phải phần
truyền tham số.

### 3.3 Ràng buộc cứng — hành vi mặc định phải BẤT BIẾN

Engine dùng `PaperBroker`. Nếu mặc định đổi dù chỉ một chữ số, phiên 04/09 chạy
khác hôm nay và ta mất khả năng so sánh.

**Tiêu chí:** chạy lại backtest cũ với tham số mặc định phải ra **đúng từng con
số** như trước khi sửa. Cách kiểm chứng bắt buộc:

1. Trước khi sửa: chạy một backtest, **lưu lại output đầy đủ**.
2. Sau khi sửa: chạy đúng lệnh đó, **so từng dòng**, phải trùng khít.
3. Dán cả hai output vào báo cáo.

Không chấp nhận "kết quả tương đương" — phải **bằng nhau**.

### 3.4 Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tham số hoá phí/thuế/thanh toán | test: truyền phí crypto (không thuế bán, thanh toán tức thì) ⇒ số khác; mặc định ⇒ số cũ |
| 2 | Mặc định bất biến | hai output backtest trước/sau, trùng khít từng dòng |
| 3 | `SETTLE_DAYS` không còn chặn | test: đặt thanh toán = 0 ⇒ bán được ngay trong ngày mua |
| 4 | Engine không đổi hành vi | `PaperBroker()` không tham số vẫn ra đúng phí/thuế/T+3 VN — có test khẳng định |
| 5 | Không hồi quy | `uv run pytest -m "not integration" -q` (nền: 370 passed) |
| 6 | Lint | `uv run ruff check trading tests scripts` sạch |

**Tiêu chí 4 là tiêu chí an toàn.** Nó là thứ đứng giữa gói này và phiên mai.

### 3.5 Phạm vi phẫu thuật

- **Được sửa:** `trading/backtest.py`, `trading/paper_broker.py`, `tests/`.
- **Không đụng:** `trading/engine/*`, `trading/collector/*`,
  `trading/calendar_vn.py`, `scripts/heartbeat_check.py`,
  `scripts/account_sync*`, `config/config.yaml`.
- **Không đo chiến lược trên crypto trong gói này** — đó là gói C, và nó cần
  phép đo có kỷ luật riêng (đóng băng quy tắc trước, kỳ ngoài mẫu niêm phong).
- Không commit, không push.

---

## 4. Vì sao B1 và B2 KHÔNG làm tối nay

Không phải vì thiếu thời gian, mà vì hai lý do cụ thể:

**B2 đụng file với gói A.** Gộp `_print_safe` phải sửa `scripts/heartbeat_check.py`
— đúng file gói A đang sửa. Ba bản hiện ở
`scripts/heartbeat_check.py:164`, `scripts/deploy_drift_check.py:126`,
`scripts/docker_down_alert.py:117`, cộng `daily_data_check.py` là hộ tiêu thụ
thứ tư. Chạy song song hai agent trên cùng một dead-man's switch là tự chuốc lấy
xung đột ở đúng file không được phép sai.

**B1 đổi cách engine nạp chiến lược.** `octopus_pullback` thiếu `last_crossover`
— backtest sạch nhưng nạp vào engine chết ngay bar đầu (`engine/logic.py:44` gọi
không điều kiện). Thêm trường chọn chiến lược vào `Config` cũng đổi đường nạp
cấu hình. Đây là thay đổi **có rủi ro runtime thật**, và nó xứng đáng có cả cuối
tuần để kiểm, không phải một đêm trước phiên.

Nhắc lại điều dễ quên: repo có **hai** hợp đồng chiến lược (cổ phiếu và phái
sinh), không phải một cái bị thiếu. `derivative_backtest.py:57` chỉ dùng
`compute_crossover` + `qty`. Ép cả năm chiến lược vào một khuôn sẽ phá đường
phái sinh — và các chiến lược momentum **không phải** dead code, chúng có ba file
test riêng.

**Lịch: tối thứ Sáu 04/09, sau 14:45.** Khi đó có trọn cuối tuần để kiểm trước
phiên thứ Hai.

---

## 5. Gói C — BingX giai đoạn 2 (cuối tuần, sau gói B)

Dữ liệu đã sẵn: `bars_crypto` có **27.124 nến 1d** và **385.363 nến 1h** cho 20
cặp. Không cần nạp thêm gì.

Chặn duy nhất là gói B. Sau khi B xong, gói C **chỉ chạm `scripts/`**.

> **ĐÍNH CHÍNH 04/09 — câu trên SAI, giữ lại để không ai lặp lại.**
> `RiskManager.approve_sized` (`trading/risk.py:99-108`) làm tròn khối lượng
> xuống bội **100** (lô HOSE) và từ chối lệnh < 100. Đã chạy thật: vốn 100.000
> USD, BTC giá 60.000 ⇒ trả **`None`** — lệnh bị từ chối **im lặng**, còn coin
> giá thấp thì vẫn có số. Đo crypto trên code hiện tại cho ra bảng thiên lệch
> mà không có gì báo. Gói C **phải tách đôi**: C-a chạm `trading/risk.py` (vào
> image), C-b mới chỉ chạm `scripts/`.
> Chi tiết: `2026-09-04-plan-bingx-giai-doan-2-do-chien-luoc.md` mục 2 và 4.

Kỷ luật đo bắt buộc giữ nguyên — chính ba chốt này đã bắt được một quy tắc lãi
+1,11 tỷ trong mẫu hoá ra lỗ −8,82 tỷ ngoài mẫu:

1. Đóng băng ngưỡng **trước** khi nhìn kết quả.
2. Kỳ ngoài mẫu **niêm phong**, chỉ chạy một lần.
3. Con số phải **tái lập được** khi chạy lại.

Thêm một điều riêng của crypto, không có ở cổ phiếu VN: **phí funding của hợp
đồng vĩnh cửu**. Bỏ qua nó sẽ làm kết quả đẹp giả tạo với vị thế giữ lâu. Nếu
đo trên perpetual mà chưa mô hình hoá funding, phải **ghi rõ trong báo cáo** là
con số chưa trừ funding — đừng để nó im lặng.

**Nhắc lại điều không đổi:** không chiến lược nào trong repo có lợi thế đo được.
Gói C là một **phép đo**, không phải bước đi tới giao dịch thật. Nếu phép đo nói
"không", đó cũng là kết quả thành công.

---

## 6. D1 — diễn tập dead-man's switch (cần một phiên, KHÔNG phải 04/09)

`2026-08-20-deadman-switch-live-drill.md` viết 20/08, **chưa từng chạy**. Nó đòi
giết collector giữa phiên để xem chuông có kêu không.

**Không làm 04/09** vì mai đã là phiên chạy image mới sau gói A/B — trộn hai
biến vào một phiên là mất cả hai phép đo.

Thêm một lý do mới có từ hôm nay: gói A **sửa chính logic chuông báo**. Diễn tập
trước khi bản sửa đó được một phiên thật xác nhận là diễn tập trên nền chưa chắc
chắn. Thứ tự đúng: A lên → 04/09 xác nhận A đúng → tuần sau diễn tập.

---

## 7. Chờ chủ dự án quyết — không nên để agent tự chọn

| Mã | Việc | Vì sao gấp dần |
|---|---|---|
| **C2** | Docker Desktop tự khởi động | 02/09 và 03/09 đều phải bật tay; chuông Docker của đợt 8 hôm nay **kêu thật lần đầu** lúc 08:00 — nó đang làm đúng việc che cho một quy trình thủ công |
| **C3** | Lịch nghỉ lễ 2026 | ngày lễ chưa khai làm chuông 2A báo láo cả ngày |
| **C1** | VPS Ubuntu | `sched.sh` và `DEPLOYMENT.md §1–§10` đã sẵn |
| **E** | Vốn engine: 0434221 (5tr) hay 0434226 (tiền thật) | vô hại khi `real_trading_enabled=false`, **phải xong trước khi bật thật** |
| **F** | Phạm vi BingX: spot hay perpetual? có đòn bẩy không? | quyết định này định hình gói C và mọi thứ sau nó |

Câu hỏi F đáng trả lời sớm nhất: **"không dùng đòn bẩy"** làm toàn bộ đường
crypto nhỏ đi rất nhiều (không thanh lý, không margin, gần với cổ phiếu).

---

## 8. Việc KHÔNG làm

| Việc | Vì sao |
|---|---|
| Bật `real_trading_enabled` | Không chiến lược nào có lợi thế đo được. Không đổi |
| Nới ngưỡng chuông báo để hết kêu giả | Che triệu chứng; sẽ hở lại ở 09:00 và sau ngày lễ |
| Sửa NAV bằng cách bỏ kiểm tra tuổi giá | Bỏ fail-safe; NAV tính hụt mà không ai biết còn tệ hơn NAV không tính |
| Import `calendar_vn` vào `db.py` | Chặn đường crypto 24/7 sau này |
| Gộp `_print_safe` tối nay | Đụng file với gói A |
| Đo chiến lược crypto trước khi gói B xong | Sẽ âm thầm áp thuế bán VN lên crypto |

---

## 9. Thứ tự tóm tắt

```
Tối nay 03/09   A (thời gian thị trường) ∥ B (tham số phí)   → Claude audit → dựng lại
Sáng 04/09      xác nhận A: 13:00 không kêu giả, NAV 0434226 ≈ 131,58tr
Tối 04/09       B1 (hợp đồng chiến lược) + B2 (gộp _print_safe)
Cuối tuần       C (BingX giai đoạn 2 — đo, không dựng)
Tuần sau        D1 diễn tập dead-man's switch
Bất kỳ lúc nào  chủ dự án trả lời C1/C2/C3/E/F
```

Mốc kiểm chứng thật của gói A không phải là test xanh, mà là **13:00 ngày 04/09
điện thoại không kêu, trong khi 09:11 hôm nay nó đã kêu đúng lúc feed chết**.
Chuông báo chỉ chứng minh được ngoài thực địa.
