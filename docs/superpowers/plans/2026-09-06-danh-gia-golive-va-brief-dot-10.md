# Đánh giá sẵn sàng go-live (06/09) + Brief đợt 10

**Người đánh giá:** Claude (planner/auditor) · **Ngày:** 2026-09-06
**Cách làm:** tự chạy lại các phép kiểm trên hệ thống đang chạy, không dựa vào
tài liệu cũ. `GO_LIVE_AUDIT.md` là bản 13/08, phần lớn nội dung đã lỗi thời.

---

## 0. KẾT LUẬN

**Chưa sẵn sàng. Và chặn số một không phải việc kỹ thuật — không agent nào code
được nó đi.**

Hạ tầng thì lành: 6 container chạy 5 giờ liên tục, 482 test xanh, chốt chặn
`real_trading_enabled` có test bảo vệ, đường lệnh thật có fail-safe sức mua và
**không tự đặt lệnh** (engine chỉ ghi DB + cảnh báo; người dùng chạy
`scripts/confirm_real_order.py` thủ công). Đó là thiết kế an toàn, giữ nguyên.

Nhưng thứ chạy trên hạ tầng đó thì chưa chứng minh được gì.

---

## 1. TẦNG 1 — CHẶN BẤT KỂ KỸ THUẬT

### 1.1 Chiến lược đang chạy đã được đo là LỖ

Đo lại hôm nay bằng bộ số đo mới (đợt 9), phí VN đã đúng 0,25%:

| | Octopus Pullback (chiến lược chạy thật) |
|---|---:|
| PnL | **−1.615.319.902 VND** |
| Profit Factor | **0,74** |
| Expectancy/lệnh | **−1.068.152 VND** |
| Sharpe (252 kỳ) | **−0,96** |

Ngưỡng để *quyết định giao dịch* là PF ≥ 1,3. Đang ở 0,74 — không phải gần đạt,
mà là mỗi đồng lãi đi kèm 1,35 đồng lỗ. Các phương án khác còn tệ hơn:
octopus_combo −9,83 tỷ, ba chiến lược nến đều lỗ, hybrid thì "lãi" hoá ra là
sản phẩm của phí = 0 và quét lưới trong mẫu.

### 1.2 Engine gần như câm — và câm ở đúng khung nó đang chạy

`scripts/check_silent_engine.py` chạy hôm nay:

```
HII : 3.211 bar 5m, cổng mở 1.342 bar (41,8%),  0 bull / 0 bear  [WARN_NO_BULL]
IJC : 4.719 bar 5m, cổng mở 3.818 bar (80,9%),  6 bull / 0 bear  [OK]
AAA : 4.597 bar 5m, cổng mở 3.702 bar (80,5%),  6 bull / 0 bear  [OK]
```

Thoát CRITICAL. Chú ý cái mà nhãn `[OK]` che mất: IJC và AAA sinh **6 tín hiệu
trên gần 4.700 bar** — cỡ 0,13%. Đây không phải chiến lược đang hoạt động, đây
là chiến lược gần như đứng yên.

**Và toàn bộ con số ở §1.1 là bar NGÀY.** Khung 5 phút — cái engine thật sự ăn —
**chưa có phép đo nào**. Bật tiền thật lúc này là trả phí thật để chạy một chiến
lược hoặc đã đo là lỗ, hoặc chưa từng đo ở khung nó đang chạy.

---

## 2. TẦNG 2 — CHẶN CỨNG NẾU VẪN MUỐN BẬT CỜ

| Mã | Vấn đề | Bằng chứng |
|---|---|---|
| **J** | Đường lệnh thật **chỉ MUA, không bao giờ BÁN** | `real_orders.py:46` rẽ `"bull"`, `:75` rẽ `"bear"`; octopus không bao giờ phát `"bear"` (xác nhận: 0 bear trên cả 3 mã). `tests/test_real_trading_guard.py` (9 test) chặn — bật cờ mà chưa xử J thì suite đỏ. |
| **E** | Tài khoản/vốn | Đã làm rõ 06/09: 0434226 là **margin**, NAV **199.545.980**, không phải "tài khoản rỗng". Nhưng chuyển engine từ 0434221 (NAV 5.021.712) sang nó **đồng thời là quyết định nhân quy mô lệnh ~40 lần**. |
| **P1** | `account_position_snapshot` **không có kiểm tra độ cũ**, ở **hai** call site | `real_orders.py:42` (`handle_crossover`) và `:174` (`handle_stop_touch`) đều gọi `read_real_positions()` rồi dùng thẳng kết quả. Nhánh BUY có fail-safe độ cũ cho sức mua (`BUYING_POWER_MAX_AGE_MINUTES = 15`, `:15` và `:64`), nhánh vị thế thì không có gì tương đương. |

---

## 3. TẦNG 3 — VẬN HÀNH

| Mã | Việc | Trạng thái đo hôm nay |
|---|---|---|
| — | Lệch triển khai | image **cũ hơn code 1 ngày 14 giờ** — engine đang chạy không có thay đổi đợt 8/9/9b |
| **C3** | Lịch nghỉ lễ | config còn đúng 3 ngày (31/08, 01/09, 02/09) — **đều đã qua**. Không phải thiếu 2026 (VN hết lễ sau 02/09), nhưng **từ 01/01/2027 lịch rỗng hoàn toàn** |
| **C1** | VPS Ubuntu | `DEPLOYMENT.md` sẵn, chưa thực hiện — vẫn chạy trên máy dev Windows |
| **C2** | Docker tự khởi động | vẫn bật tay |
| **D1** | Diễn tập dead-man's switch | **chưa từng diễn tập** — chuông chưa bao giờ được chứng minh là kêu thật |

---

# BRIEF ĐỢT 10

## Mục tiêu

Không phải "chuẩn bị bật cờ". Mục tiêu là: **đo cho biết thứ đang chạy tốt hay
xấu**, và **bịt các lỗ hổng an toàn** để nếu sau này tìm được chiến lược có lợi
thế thì bệ đã sẵn.

Nếu agent thấy mình đang làm việc gì khiến hệ thống *gần hơn* tới việc bật tiền
thật mà chưa qua §1 — **dừng và báo cáo**.

---

## Task 1 — Đo octopus trên bar 5 PHÚT (giá trị cao nhất)

Đây là lỗ hổng lớn nhất còn lại: chiến lược chạy thật ở khung 5m, mọi con số
đều là bar ngày.

- **Viết script mới trong `scripts/`, ĐỪNG dùng CLI `python -m trading.backtest`.**
  CLI đó gọi `load_config` (`backtest.py:322`) mà `trading/config.py` đọc
  `os.environ["DB_DSN"]` cùng 5 biến SSI — thiếu là `KeyError`, không liên quan
  gì tới phép đo. Script mới:
  - gọi thẳng `run_backtest(...)` như `measure_octopus_matched_basket.py` làm;
  - lấy DSN bằng `resolve_dsn` từ `scripts/_db_common.py`;
  - đọc bar 5m bằng `storage.read_bars(symbol, frm, to)` (bảng `bars` — đúng
    nguồn mà `_TF_SPEC["5m"]` trỏ tới);
  - lấy danh sách mã bằng `yaml.safe_load` trên `config/config.yaml`, **không**
    qua `load_config`.
- Rổ mã: đúng ba mã engine đang chạy (khoá `symbols` trong config), vì bảng
  `bars` 5m chỉ có các mã đó.
- Chi phí: dùng `FEE_RATE`/`SELL_TAX_RATE`/`SLIPPAGE_BPS` import từ
  `trading.paper_broker` — **không gõ lại số**. Đây là cùng lỗi đã làm trôi cổng
  cứng ở đợt 9.
- **Bắt buộc dùng `trading/metrics.py`** — báo cáo đủ PnL, Profit Factor,
  expectancy, max drawdown danh mục, Sharpe. `periods_per_year` cho bar 5m:
  tự tính từ số bar/phiên × số phiên/năm, **ghi rõ cách tính**, không đoán.
- Đặt **cạnh** số bar ngày (−1.615.319.902 / PF 0,74 / Sharpe −0,96).

**Cảnh báo về cỡ mẫu:** IJC/AAA chỉ 6 tín hiệu, HII 0. Nhiều khả năng kết quả
là "quá ít lệnh để nói được gì". **Đó là một kết luận hợp lệ và phải báo đúng
như thế** — không nới tham số cho ra nhiều lệnh hơn rồi báo cáo con số đẹp. Nới
tham số là việc khác, cần quyết định riêng của chủ dự án.

**Kiểm chứng:** bảng số + câu trả lời rõ ràng cho "cỡ mẫu có đủ để kết luận
không, và vì sao".

## Task 2 — Fail-safe độ cũ cho `account_position_snapshot` (P1)

Khuôn theo đúng fail-safe sức mua đã có trong cùng file — **đọc
`real_orders.py:51-73` trước, chép khuôn, không sáng tạo dạng khác**:

- Thêm hằng số độ cũ tối đa cho vị thế, đặt cạnh `BUYING_POWER_MAX_AGE_MINUTES`
  (`:15`).
- **Cả hai call site**: `handle_crossover` (`:42`, nhánh SELL) và
  `handle_stop_touch` (`:174`). Thiếu dòng vị thế **hoặc** dòng quá cũ ⇒
  **từ chối + CRITICAL**, không rơi về giá trị "cho dễ gật".
- Không đụng nhánh BUY (đã có fail-safe riêng).

**Nguồn thời gian đã có sẵn — KHÔNG đổi chữ ký hàm nào.** `read_real_positions()`
trả `dict[str, RealPosition]` không kèm mốc thời gian, nhưng
`Storage.read_position_sync_ts(account_no) -> datetime | None`
(`db.py:686-693`) đã tồn tại và trả đúng mốc lần đồng bộ vị thế gần nhất
(`None` = chưa bao giờ đồng bộ). Dùng hàm đó.

`read_real_positions` có **13 nơi gọi** — đổi chữ ký của nó là bán kính ảnh
hưởng lớn không cần thiết. Chỉ gọi thêm `read_position_sync_ts` tại hai chỗ
trong `real_orders.py`.

Lưu ý ngữ nghĩa: `None` nghĩa là **chưa từng đồng bộ**, phải xử như "không có
dữ liệu" ⇒ từ chối + CRITICAL, **không** coi là "mới tinh".

**Kiểm chứng:** test cho ba trường hợp trên **mỗi** call site — vị thế tươi
(cho qua), vị thế quá cũ (từ chối + CRITICAL), không có dòng vị thế (từ chối +
CRITICAL). Kèm phá hoại: bỏ kiểm tra ⇒ test phải đỏ, dán output thô, khôi phục,
`grep -rn "SABOTAGE"` rỗng.

## Task 3 — Dựng lại image

Image đang cũ hơn code (đo 06/09: lệch 1 ngày 14 giờ — con số này sẽ khác khi
bạn chạy, **đọc lại bằng lệnh dưới** thay vì tin số trong brief).

```
uv run python scripts/deploy_drift_check.py     # ghi lại con số TRƯỚC khi dựng
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

**Kiểm chứng:** `deploy_drift_check.py` **không còn cảnh báo** sau khi dựng;
`docker ps` cả 6 container Up; `scripts/heartbeat_check.py` xanh.

**Cấm** đụng `config/config.yaml` trong lúc dựng lại.

> **Lưu ý phối hợp:** chủ dự án đã hẹn diễn tập dead-man's switch **sáng T2
> 07/09** (`2026-09-07-kich-ban-dien-tap-dead-man-switch.md`). Nếu task này chạy
> trùng buổi đó thì dựng lại image sẽ làm container khởi động lại giữa chừng và
> **làm hỏng kết quả diễn tập**. Làm Task 3 **trước 08:00 hoặc sau 15:00** ngày
> 07/09, hoặc vào ngày khác.

## ~~Task 4 — Docker tự khởi động (C2)~~ — ĐÃ CÓ SẴN, KHÔNG LÀM

**Đính chính của người viết brief (06/09, sau khi kiểm lại):** tôi đã định giao
việc thêm `restart: unless-stopped`. Kiểm tra thì **cả 6 service trong
`docker-compose.yml` đều đã có sẵn** (dòng 15, 23, 37, 61, 80, 95). Giao việc
này là bắt agent làm lại thứ đã xong.

Phần **thật sự** còn thiếu của C2 nằm ngoài repo, trên máy người dùng, và
**agent không được tự làm**:

- Docker Desktop chưa được đặt tự khởi động cùng Windows — không có
  `restart:` nào cứu được nếu bản thân Docker không chạy.
- Scheduled task `trading-engine-cam` **chưa tồn tại** (kiểm bằng
  `schtasks /query /tn "trading-engine-cam"` → không tìm thấy). Lệnh tạo đã ghi
  sẵn trong `DEPLOYMENT.md`.

Cả hai là thao tác thay đổi máy của chủ dự án ⇒ **chỉ nhắc trong báo cáo, không
tự chạy.**

---

## Task 4 (thay thế) — Cảnh báo khi lịch nghỉ lễ đã cạn

### Bối cảnh — vì sao KHÔNG bỏ `holidays` khỏi config

Chủ dự án hỏi 06/09: lịch 2027 phải crawl từ báo, nếu không được thì bỏ khỏi
config? **Trả lời: không bỏ.** Lý do đã kiểm chứng:

1. **Lịch 2027 chưa công bố chính thức.** Thủ tướng quyết hằng năm, Bộ Nội vụ
   thường thông báo tháng 10–12 năm trước. Mọi bài báo hiện tại đều ghi "dự
   kiến". Crawl bây giờ = lấy phương án đề xuất làm lịch chặn giao dịch, đúng
   loại đoán bị cấm.
2. **Config hiện tại KHÔNG sai.** Việt Nam hết ngày lễ luật định sau 02/09/2026;
   ngày kế tiếp là 01/01/2027. Ba dòng còn lại là đúng-và-đã-dùng-hết.
3. **Bỏ đi sẽ gây nhiễu chuông báo.** `holidays` chảy vào
   `calendar_vn.is_trading_time()` → `aggregator.py:29`,
   `collector/main.py:247`, `heartbeat_check.py`, `docker_down_alert.py`, và
   `trading_days_between()` (`account_sync.py:154`). Không có lịch thì ngày lễ
   bị coi là phiên giao dịch, chờ tick không tới, chuông kêu oan.
   **Đây không phải giả thuyết:** `heartbeat_check.py:95` ghi lại chính sự cố
   đó — *"ngày 01/09 (nghỉ Quốc khánh) 2A nổ mỗi 5 phút suốt"*.

Chế độ hỏng thật ở đây là **con người quên cập nhật**, không phải code sai. Nên
việc cần làm là biến "quên" thành "hệ thống tự nhắc".

### Việc

Thêm vào `scripts/heartbeat_check.py` một kiểm tra: **lịch nghỉ lễ đã cạn.**

- Hàm **thuần** (nhận `holidays`, `now`, trả về bool hoặc thông điệp) để test
  được không cần DB — khuôn giống `in_bar_check_window` / `bar_stale` sẵn có
  trong cùng file.
- Luật: **cảnh báo WARN khi không còn ngày lễ nào `>= hôm nay` trong config
  VÀ hôm nay đã qua 01/10.**
- Vì sao có mốc 01/10, không cảnh báo quanh năm: trước tháng 10 thì lịch năm sau
  chưa công bố, cảnh báo lúc đó là nhiễu vô ích vì **không ai hành động được**.
  Từ 01/10 trở đi thì thông báo chính thức bắt đầu ra, cảnh báo mới có chỗ để
  hành động. Ghi lý do này vào docstring.
- Thông điệp phải nói rõ **phải làm gì**: lịch nghỉ giao dịch của HOSE/HNX là
  nguồn đúng (cần ngày *sàn đóng cửa*, không phải ngày nghỉ công — hai thứ này
  lệch nhau ở ngày nghỉ bù và ngày liền kề Quốc khánh).
- Mức **WARN**, không phải CRITICAL: lịch thiếu không làm đặt sai lệnh, nó chỉ
  gây báo động giả.

**Cấm** sửa `config/config.yaml` (kể cả thêm khoá mới) — nếu thấy cần đổi cấu
trúc config thì **báo lại**, đừng tự làm.

**Kiểm chứng:**

| Trường hợp | Kỳ vọng |
|---|---|
| `now` = 15/09/2026, lịch chỉ có ngày đã qua | **không** cảnh báo (chưa tới 01/10) |
| `now` = 02/10/2026, lịch chỉ có ngày đã qua | **có** cảnh báo |
| `now` = 02/10/2026, lịch có 01/01/2027 | **không** cảnh báo |
| `now` = 02/10/2026, lịch rỗng hoàn toàn | **có** cảnh báo |

Kèm phá hoại: bỏ điều kiện mốc 01/10 ⇒ trường hợp 1 phải đỏ. Dán output thô,
khôi phục, `grep -rn "SABOTAGE"` rỗng.

---

## Task 5 — Trần 100 cổ phiếu cho lệnh MUA thật (nửa an toàn của E)

### Quyết định của chủ dự án 06/09 và cách tôi tách nó

Chủ dự án chốt: *"dùng tất cả tài khoản có khả năng giao dịch, tạm thời ở mức
100 cổ phiếu"*. Việc này có **hai nửa** với mức rủi ro rất khác nhau:

1. **Trần 100 cổ phiếu** — thuần an toàn, rẻ, hữu ích bất kể sau này dùng tài
   khoản nào. **Làm ở đợt này.**
2. **Đa tài khoản** — `real_order_account` hiện là **một chuỗi duy nhất**, dùng
   ở **32 chỗ**. Đổi thành nhiều tài khoản là thay đổi kiến trúc đúng đường code
   nhạy cảm nhất repo. **HOÃN** tới khi J có lời giải — chủ dự án đã đồng ý
   06/09. Lý do: J đang hoãn nghĩa là đường lệnh thật **chỉ MUA, không bao giờ
   BÁN**; dựng năng lực mua-không-bán trên *nhiều* tài khoản là nhân rộng đúng
   cái nửa nguy hiểm.

**Task này chỉ làm nửa 1. Cấm đụng vào `real_order_account`.**

### Việc

Trong `trading/real_orders.py`, nhánh BUY:

- Thêm hằng số đặt tên (ví dụ `MAX_REAL_BUY_QTY = 100`) cạnh
  `BUYING_POWER_MAX_AGE_MINUTES` (`:15`), kèm bình luận nói rõ đây là **trần
  tạm thời do chủ dự án đặt 06/09 cho giai đoạn thử**, không phải giới hạn kỹ
  thuật.
- Áp vào **chuỗi kẹp trần đã có**, đặt cùng chỗ với trần sức mua hiện tại:
  ```python
  qty = min(sized.qty, max_buy_qty) // risk.lot_size * risk.lot_size
  ```
  ⇒ thêm `MAX_REAL_BUY_QTY` vào `min(...)`. **Không** viết một nhánh kẹp riêng
  ở chỗ khác — một trần một chỗ.
- Lưu ý: `risk.lot_size` = 100 trên HOSE, nên trần này thực tế nghĩa là **đúng
  một lô mỗi lệnh mua**.

### CHỈ áp cho MUA — không áp cho BÁN

Đây là điểm dễ làm sai nhất, ghi rõ trong bình luận code:

Kẹp trần lệnh BÁN là **nguy hiểm**. Nếu tài khoản đang giữ 500 cổ phiếu và cần
thoát, trần 100 sẽ nhốt 400 cổ phiếu còn lại trong vị thế. Trần này là để giới
hạn *mức độ phơi nhiễm mới*, không phải để giới hạn đường thoát. Nhánh SELL
(`:75`) và `handle_stop_touch` (`:146`) **giữ nguyên**, tiếp tục dùng
`sellable_qty`.

### Kiểm chứng

| Trường hợp | Kỳ vọng |
|---|---|
| `approve_sized` trả 500, `max_buy_qty` = 5.000 | lệnh BUY ra **100** |
| `approve_sized` trả 50 | ra **0** (làm tròn xuống bội 100) — không phải 50 |
| `max_buy_qty` = 0 | ra **0**, trần mới không làm hỏng fail-safe sức mua sẵn có |
| Nhánh SELL với `sellable_qty` = 500 | ra **500**, **không** bị kẹp |

Phá hoại: bỏ `MAX_REAL_BUY_QTY` khỏi `min(...)` ⇒ trường hợp 1 phải đỏ. Dán
output thô, khôi phục, `grep -rn "SABOTAGE"` rỗng.

---

## VIỆC KHÔNG GIAO CHO AGENT — cần chủ dự án

| Mã | Vì sao không giao được |
|---|---|
| **§1 chiến lược** | Không phải lỗi code. Cần quyết định: đo lại toàn bộ (đang làm), đổi họ chiến lược, hay dừng săn |
| **J** | ~~Chờ quyết~~ — **chủ dự án HOÃN (06/09)** |
| **E** | ~~Chờ quyết~~ — **đã quyết 06/09**, tách hai nửa: trần 100 cp làm ngay (Task 5), đa tài khoản hoãn tới khi J xong |
| **C1** | ~~Chờ quyết~~ — **đã quyết 06/09**: chuyển VPS Ubuntu khi hệ thống đủ sẵn sàng giao dịch, chưa phải bây giờ |
| **C2** | ~~Chờ quyết~~ — **đã quyết 06/09**: chủ dự án **tự khởi động Docker** khi cần. Không cần autostart, không cần scheduled task cho việc này |
| **D1** | ~~Chờ quyết~~ — **đã hẹn: Thứ Hai 07/09**. Kịch bản ở `2026-09-07-kich-ban-dien-tap-dead-man-switch.md` |
| **C3** | ~~Chờ quyết~~ — **đã có hướng 06/09**: chưa công bố chính thức (Bộ Nội vụ ra tháng 10–12), nên **chờ**, không crawl báo. Task 4 thêm chuông nhắc từ 01/10. Nguồn đúng khi có: thông báo lịch nghỉ **giao dịch** của HOSE/HNX |
| **C1** | Chuyển sang VPS Ubuntu — quyết định hạ tầng + chi phí |
| **D1** | Diễn tập dead-man's switch cần một phiên giao dịch thật, chủ dự án hẹn lịch |

---

## PHẠM VI PHẪU THUẬT

**Được sửa, theo từng task:**

| Task | File được đụng |
|---|---|
| 1 | script đo mới trong `scripts/` |
| 2 | `trading/real_orders.py` + test |
| 3 | không sửa file nào — chỉ chạy lệnh dựng lại image |
| 4 | `scripts/heartbeat_check.py` + test |
| 5 | `trading/real_orders.py` + test |

**Lưu ý:** Task 2 và Task 5 **cùng sửa `trading/real_orders.py`**. Làm tuần tự,
đừng để hai thay đổi giẫm lên nhau. Cả hai đều thêm hằng số cạnh
`BUYING_POWER_MAX_AGE_MINUTES` (`:15`).

**Cấm đụng:** `config/config.yaml` (kể cả thêm khoá mới), `.env`,
`real_trading_enabled` (giữ `false` — **không bật dù chỉ để thử**),
`real_order_account` (đa tài khoản đã HOÃN — xem Task 5),
`_default_strategy()`, `run_backtest`, `PaperBroker`, `trading/strategies/*`,
`trading/metrics.py`, `trading/sampling.py`, `trading/crypto_fees.py`,
`trading/paper_broker.py`. Không gọi API đặt/huỷ lệnh SSI.
Không `TRUNCATE`/`DROP`/xoá dòng.

**Không commit, không push.** Claude audit rồi mới commit.

## BÁO CÁO NỘP LẠI

- **Task 1:** bảng số đặt cạnh số bar ngày (`−1.615.319.902` / PF 0,74 /
  Sharpe −0,96), kèm kết luận trung thực về cỡ mẫu.
- **Task 3:** output thô `deploy_drift_check`, `docker ps`, `heartbeat_check`.
- **Task 2, 4, 5:** output đỏ thô của **từng** lần phá hoại (mỗi task một lần),
  kèm xác nhận `grep -rn "SABOTAGE" trading tests scripts` rỗng sau khi khôi phục.
- `uv run pytest -m "not integration" -q` (hiện **482**) và
  `uv run ruff check trading tests scripts`.
- Bất cứ chỗ nào brief này sai hoặc mâu thuẫn: **báo lại, đừng tự quyết.**
