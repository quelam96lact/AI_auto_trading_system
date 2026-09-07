# Brief đợt 16 — Tầng hổng của đường lệnh thật

Ngày giao: 07/09/2026
Base: `bdfc102` (main), cây làm việc sạch.
Người giao: Claude (planner/auditor).

Brief này **tự chứa**. Tôi đã tự chẩn đoán xong nguyên nhân trước khi viết — bạn không
phải đi dò lại từ đầu.

---

## 1. Bối cảnh — chuyện gì đã xảy ra

Khi audit đợt 15 tôi chạy **toàn bộ** suite (`uv run pytest -q`) và thấy:

```
7 failed, 596 passed
```

Cả 7 đều ở `tests/test_engine_main.py`, cả 7 đều thuộc nhánh **BÁN thật** (real stop touch).

**Không phải do đợt 15.** Tôi đã stash thay đổi và chạy lại trên HEAD sạch: vẫn đúng 7 test
đỏ y nguyên.

Vì sao không ai thấy: các đợt gần đây (kể cả tôi) đều báo "502 test xanh", mà 502 là con số
của `pytest -m "not integration"` — tập con **không** có integration. Và commit `d0a97f5`
đã ghi sẵn từ trước: *"83 test integration chua tung chay o dau ngoai may dev"*. Nên loại
hỏng này mục rữa im lặng được rất lâu.

---

## 2. Nguyên nhân — đã chẩn đoán xong, có bằng chứng

Chạy `uv run pytest tests/test_engine_main.py::test_real_stop_touch_creates_pending_sell -q -l`
và đọc biến cục bộ lúc đỏ:

```
alerts_seen = [('CRITICAL', 'khong co dong vi the (account_position_snapshot) cho tai khoan
ACC_RTS — TU CHOI xu ly stop touch cho ENGT (fail-safe, chua tung dong bo vi the)')]
```

Chuỗi nhân quả:

1. `trading/real_orders.py:206-215` (chốt an toàn P1, vào repo ở `fb57469` — đợt 10) gọi
   `storage.read_position_sync_ts(account)`; nếu `None` thì **CRITICAL và `return`**.
2. `trading/storage/db.py:692-699` — `read_position_sync_ts` đọc **chỉ** bảng
   `account_sync_log`.
3. Người ghi bảng đó là `record_position_sync` (`db.py:680-690`), một hàm **riêng**.
4. Helper của test — `tests/test_engine_main.py:785-789` `_seed_real_position()` — chỉ gọi
   `save_account_positions()`, tức **chỉ ghi `account_position_snapshot`, không bao giờ ghi
   `account_sync_log`**.

Nên kể từ lúc P1 vào repo, mọi test stop-touch đều bị chính chốt an toàn chặn ở dòng 215 và
không bao giờ đi tới phần logic nó định kiểm.

**Kết luận: đây là mục rữa của bộ đồ nghề test, KHÔNG phải lỗi sản xuất.** Trong vận hành
thật, `trading/collector/account_sync.py` ghi cả hai bảng, nên đường thật không dính bẫy
này. Đừng "sửa" `real_orders.py` để test xanh — P1 đang làm đúng việc của nó.

### 2.1. Hệ quả nghiêm trọng hơn cái test đỏ

Tôi rà toàn bộ assertion về `pending_real_orders` trong `tests/test_engine_main.py`:

| Dòng | Khẳng định | Nghĩa |
|---|---|---|
| 725 | `n == 0` | fail-safe NAV chặn — khẳng định **không** có lệnh |
| 822, 853, 905, 937, 1002, 1029 | `_count_pending_sells(...) == 1` | SELL — **cả 6 đang đỏ** |
| 877 | `_count_pending_sells(...) == 0` | chưa settle — khẳng định **không** có lệnh |
| 363 | status == "expired" | vòng đời, không phải sinh lệnh |

Hai điều rút ra:

- **Không có một test nào khẳng định lệnh BUY thật được tạo ra.** Toàn bộ khẳng định
  "dương" của đường lệnh thật nằm ở nhánh SELL — và nhánh đó đang đỏ.
- **Hai nhánh CRITICAL của P1 (`chưa từng đồng bộ` và `vị thế quá cũ`) không có test nào
  cả** — ở cả `handle_stop_touch` lẫn `handle_crossover`. Thứ duy nhất đang "chạm" vào
  chúng là 7 test đỏ **do tai nạn**. Sửa xong 7 test đó mà không thêm gì thì P1 sẽ từ
  "được kiểm nhầm" thành "không được kiểm gì cả" — tệ hơn hiện tại.

*(Các test trong `tests/test_heartbeat_check.py` có tên giống nhưng kiểm hàm khác —
`heartbeat_check.position_sync_stale`, không phải P1 trong `real_orders.py`. Đừng nhầm hai
thứ đó là một.)*

---

## 3. Ràng buộc

- `real_trading_enabled` giữ `false`. Không bật, kể cả trong test thủ công.
- **Không gọi SSI một lần nào.** Đợt này thuần test, không cần mạng.
- Không in secret. `.env` không sửa, không commit. `config/config.yaml` không sửa.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB `trading`. Test chạy trên `trading_test`.
- **KHÔNG commit, KHÔNG push.** Tôi audit xong mới commit.

### Ràng buộc quan trọng nhất của đợt này

> **Không được sửa một dòng mã sản xuất nào.**

Cụ thể: không sửa `trading/real_orders.py`, `trading/storage/db.py`,
`trading/engine/*`, `trading/trailing_stop.py`, `trading/risk.py`. Đợt này **chỉ** đụng
`tests/`.

Nếu một test không thể xanh mà không sửa mã sản xuất, thì **đó là một phát hiện, không phải
một việc cần làm**: dừng lại, ghi vào báo cáo đúng chỗ nào chặn và vì sao, rồi chuyển sang
task tiếp theo. **Tuyệt đối không nới lỏng chốt an toàn để test xanh.** Đây là cả điểm của
đợt 16 — chúng ta đang đo xem mã sản xuất có được kiểm không, chứ không phải làm cho bảng
điểm đẹp.

Phát hiện ngoài phạm vi: báo cáo, không tự sửa. Chỉ sửa file được nêu tên.

### GitNexus

1. **Trước khi gõ dòng đầu:** `npx gitnexus analyze` (khớp với `bdfc102`).
2. `gitnexus_impact` cho symbol bạn chạm. Đợt này chỉ chạm test nên nhiều khả năng rủi ro
   thấp — vẫn phải chạy và dán kết quả.
3. **Sau khi xong:** `npx gitnexus analyze` lần nữa + `gitnexus_detect_changes()`.

`analyze` **sẽ tự sửa `AGENTS.md` và `CLAUDE.md`** (dòng đếm symbol trong khối
`<!-- gitnexus:start -->`). Đó là hành vi bình thường của công cụ, **không phải bạn vi phạm
phạm vi** — đừng revert, đừng commit, chỉ liệt kê trong `git status` kèm ghi chú.

Nếu MCP gitnexus không kết nối được (phiên của tôi hôm nay timeout): vẫn chạy `analyze`
bằng CLI, và nói thẳng phần MCP không chạy được. **Đừng bịa kết quả.**

---

## Task 1 — Làm 7 test stop-touch chạy thật, không nới chốt an toàn

**File được sửa:** `tests/test_engine_main.py`. Chỉ file này.

### Yêu cầu

Sửa helper `_seed_real_position()` (dòng 785-789) để nó **cũng** gọi
`storage.record_position_sync(account, <mốc>)` — tức mô phỏng đúng thứ vận hành thật làm
(`account_sync.py` ghi cả hai bảng).

### Chọn mốc thời gian — đọc kỹ, ở đây có bẫy

Có hai cách, và **tôi yêu cầu cách thứ hai**:

**Cách A (ĐỪNG dùng): đóng băng `real_orders._now` về thế giới 2026-07-15 của fixture.**
Nghe thì sạch hơn, nhưng sẽ làm đỏ `test_real_stop_touch_no_duplicate_pending`. Lý do:
`Storage.has_active_pending_sell` (`db.py:281-290`) lọc bằng `expires_at > now()` — `now()`
của **PostgreSQL**, tức đồng hồ thật, không phải `_now` của Python. Đóng băng `_now` về
15/07/2026 thì lệnh chờ sinh ra có `expires_at` nằm ở quá khứ so với DB, chốt chặn trùng
mất hiệu lực, và lần gọi thứ hai sẽ đẻ ra lệnh thứ hai.

**Cách B (dùng cách này): ghi mốc đồng bộ bằng `datetime.now(TZ)`.**
Giữ nguyên mốc bar ở thế giới 2026-07-15 như hiện tại; chỉ riêng mốc **đồng bộ vị thế** là
thời gian thật. Khi đó tuổi vị thế ≈ 0 phút, dưới ngưỡng 15 phút của
`POSITION_MAX_AGE_MINUTES`, và `expires_at` do `_now` sinh ra vẫn ăn khớp với `now()` của
DB. Đây cũng đúng tinh thần thật: mốc đồng bộ là "vừa mới lấy về", còn mốc bar là dữ liệu
thị trường.

Nếu bạn tìm ra cách thứ ba sạch hơn cả hai mà **không** đụng mã sản xuất, cứ làm — nhưng
phải giải thích trong báo cáo vì sao nó không dính bẫy `now()` ở trên.

### Kiểm chứng

1. `uv run pytest tests/test_engine_main.py -q` → **36/36 xanh** (hiện tại 7 đỏ / 29 xanh).
   Dán cả hai lần chạy: trước khi sửa và sau khi sửa.
2. Với **từng** test trong 6 test khẳng định `== 1`, xác nhận nó xanh vì **đi hết đường
   logic**, không phải vì tình cờ. Cách kiểm: chạy với `-l` và dán `alerts_seen` của ít
   nhất `test_real_stop_touch_creates_pending_sell` và
   `test_real_stop_touch_falls_back_to_avg_price`, cho thấy **không còn** dòng CRITICAL
   `TU CHOI xu ly stop touch`.
3. `test_real_stop_touch_no_duplicate_pending` phải xanh — đây là test dính bẫy `now()`.
   Nếu nó đỏ thì bạn đã chọn cách A.
4. `uv run pytest -q` (toàn bộ suite) → **0 failed** *tại thời điểm kết thúc Task 1*. Dán
   dòng tổng kết. (Task 3 có thể để lại đúng một test đỏ có chủ đích — xem mục đó; nhưng
   sau Task 1 thì suite phải sạch hoàn toàn, đó là mốc để biết Task 1 đã xong.)

### Không được làm

Không đổi nội dung khẳng định của 7 test (`== 1`, `== 0`, các assert về `sellable_qty`,
về WARN). Không thêm `skip`/`xfail` cho bất kỳ test nào. Không đụng mã sản xuất.

---

## Task 2 — Cho P1 lớp kiểm thật, thay vì kiểm nhầm

**File được sửa:** `tests/test_engine_main.py`. Chỉ file này.

### Vì sao

Task 1 gỡ bỏ thứ duy nhất đang chạm vào hai nhánh CRITICAL của P1. Nếu dừng ở Task 1 thì
P1 — chốt an toàn ngăn hệ thống đặt lệnh trên số liệu vị thế cũ — sẽ **không còn một test
nào**. Task 2 biến lớp kiểm tai nạn đó thành lớp kiểm có chủ đích.

### Yêu cầu — 4 test mới

Đặt cạnh nhóm stop-touch sẵn có, theo đúng khuôn các test xung quanh (dùng `RTS_ACCOUNT`,
`monkeypatch` `trading.real_orders.alert` vào `alerts_seen` như các test hiện có).

| # | Hàm | Tình huống | Phải khẳng định |
|---|---|---|---|
| 2.1 | `handle_stop_touch` | có vị thế trong snapshot nhưng **chưa từng** `record_position_sync` | không sinh pending SELL nào **và** có alert `CRITICAL` chứa `chua tung dong bo` |
| 2.2 | `handle_stop_touch` | có `record_position_sync` nhưng mốc **cũ hơn 15 phút** | không sinh pending SELL nào **và** có alert `CRITICAL` chứa `TU CHOI xu ly stop touch` |
| 2.3 | `handle_crossover` | chưa từng `record_position_sync` | không sinh pending nào **và** có alert `CRITICAL` |
| 2.4 | `handle_crossover` | mốc đồng bộ cũ hơn 15 phút | không sinh pending nào **và** có alert `CRITICAL` |

Với 2.2 và 2.4, cách sạch nhất là ghi mốc đồng bộ = `datetime.now(TZ) - timedelta(minutes=30)`
— không cần đụng `_now`.

**Đừng hard-code số 15 vào test.** Import `POSITION_MAX_AGE_MINUTES` từ
`trading.real_orders` và tính mốc từ nó. Nếu ai đó đổi ngưỡng, test phải đi theo chứ không
gãy — "một công thức, một chỗ" (tiền lệ `4ea4c8d`).

`handle_crossover` cần nhiều điều kiện đầu vào hơn `handle_stop_touch` (NAV, sức mua…).
Nếu 2.3/2.4 phình to quá mức hợp lý — bạn phải dựng hơn ~15 dòng seed — thì **dừng lại,
làm xong 2.1/2.2, và báo cáo rõ vướng ở đâu**. Đừng đẻ ra một cái giàn giáo khổng lồ chỉ để
chạm vào một câu `return`.

**Mẹo về thứ tự:** Task 3 buộc phải dựng đủ điều kiện tiền đề cho `handle_crossover` rồi.
Nếu bạn làm Task 3 trước, cái helper seed đó dùng lại được cho 2.3/2.4 gần như miễn phí —
và khi đó điều khoản "dừng lại" ở trên không còn cần đến. Tuỳ bạn chọn thứ tự; tôi chỉ
đánh số cho dễ gọi tên, không bắt làm tuần tự.

### Kiểm chứng

Mỗi test mới phải **đỏ khi chốt bị gỡ**. Với từng nhánh:

1. Sabotage: trong `trading/real_orders.py`, đổi `return` của nhánh đang kiểm thành `pass`
   (hoặc bỏ hẳn khối `if`), chạy lại, **dán tên test đỏ thật + dòng assert lỗi**.
2. Khôi phục bằng cách **đảo ngược đúng chỗ vừa sửa** — **không dùng `git checkout --`**.
   (Tôi vừa tự bắn vào chân mình đúng chỗ này khi audit đợt 15: `git checkout --` để gỡ
   sabotage đã xoá luôn phần việc chưa commit. Học từ đó.)
3. Sau khi khôi phục: `git diff trading/real_orders.py` phải **rỗng**, và
   `grep -rn "SABOTAGE" .` không ra kết quả nào trong mã nguồn.

---

## Task 3 — Một lớp kiểm dương cho đường MUA thật

**File được sửa:** `tests/test_engine_main.py`. Chỉ file này.

### Vì sao

Xem bảng ở mục 2.1: **không có test nào khẳng định lệnh BUY thật được tạo ra.** Đường sinh
lệnh mua — thứ sẽ tiêu tiền thật vào ngày bật `real_trading_enabled` — chưa từng được một
test nào chứng minh là chạy.

### Yêu cầu

**Đúng một** test: `handle_crossover` với tín hiệu mua và **mọi điều kiện tiền đề được thoả**
(vị thế đã đồng bộ tươi, NAV có, sức mua có, chưa halt) → khẳng định `pending_real_orders`
có **đúng một** dòng `side = 'BUY'` cho `RTS_ACCOUNT`, với `quantity > 0` và
`quantity <= MAX_REAL_BUY_QTY` (import hằng số từ `trading.real_orders`, đừng gõ 100).

Viết một helper `_count_pending_buys()` song song với `_count_pending_sells()` sẵn có.

### Nếu không xanh được

Rất có thể test này **không xanh ngay**, vì đường BUY chưa từng được kiểm nên có thể có
điều kiện tiền đề mà không ai còn nhớ.

**Trong trường hợp đó: KHÔNG sửa `real_orders.py`.** Hãy:

1. Chạy với `-l`, dán `alerts_seen` cho thấy **chính xác** chốt nào chặn.
2. Ghi vào báo cáo: chốt nào, ở dòng nào, cần điều kiện gì.
3. Để test lại dưới dạng **đỏ** — đừng xoá, đừng `xfail`, đừng nới điều kiện khẳng định cho
   vừa với thực tế.

Một test đỏ nói đúng sự thật thì có giá trị hơn hẳn một test xanh nói dối. Tôi cần biết
đường BUY thật đang ở tình trạng nào — **đó mới là sản phẩm của Task 3**, không phải màu
xanh.

---

## 4. Báo cáo nghiệm thu phải có

1. `uv run pytest tests/test_engine_main.py -q` — **trước** và **sau**, output thô.
2. `uv run pytest -q` (toàn bộ suite) — output thô dòng tổng kết. **Bắt buộc**, không được
   thay bằng `-m "not integration"`. Đây đúng là chỗ báo cáo đợt 15 đã bỏ qua rồi vẫn tuyên
   bố hoàn thành 100%.
3. `uv run pytest -q -m "not integration"` — để đối chiếu, phải vẫn là 502.
4. `uv run ruff check trading tests scripts` — sạch.
5. `alerts_seen` đã dán ở Task 1 mục 2 và (nếu có) Task 3.
6. Output sabotage của **từng** test mới ở Task 2, nguyên văn, kèm tên test đỏ.
7. `git diff trading/` phải **rỗng** — bằng chứng không đụng mã sản xuất. Dán nguyên câu
   lệnh và kết quả rỗng.
8. `git status --short` và `git diff --stat`. File được phép xuất hiện: **chỉ**
   `tests/test_engine_main.py`, cộng `AGENTS.md` + `CLAUDE.md` (do `analyze` sinh ra). Bất
   cứ file nào khác đều là lỗi — báo cáo, đừng tự dọn.
9. GitNexus: cả hai lần `analyze`, `gitnexus_impact`, `gitnexus_detect_changes` — hoặc nói
   thẳng phần nào không chạy được.
10. Phát hiện ngoài phạm vi: liệt kê, không sửa.

**Output thô, nguyên văn. Không tự gõ lại bảng số liệu.** Đợt 10 và đợt 14 đều từng có bảng
bịa trong báo cáo dù code hoàn toàn đúng; tôi sẽ chạy lại tất cả và đối chiếu.

---

## 5. Tiêu chí "xong"

- [ ] `npx gitnexus analyze` đã chạy trước và sau.
- [ ] `_seed_real_position` ghi cả `account_sync_log`, dùng cách B (hoặc cách khác có giải
      thích vì sao không dính bẫy `now()` của DB).
- [ ] `tests/test_engine_main.py` 36/36 xanh; `test_real_stop_touch_no_duplicate_pending`
      nằm trong số đó.
- [ ] `alerts_seen` chứng minh không còn CRITICAL `TU CHOI` ở các test stop-touch.
- [ ] 4 test P1 mới (hoặc 2, kèm lý do dừng), mỗi cái có sabotage đỏ riêng.
- [ ] Test BUY dương đã viết — **xanh hoặc đỏ đều được**, miễn là báo cáo nói rõ tình trạng
      và chốt nào chặn.
- [ ] `uv run pytest -q` toàn bộ suite: 0 failed **hoặc** chỉ còn đúng test BUY của Task 3
      đỏ, nêu rõ.
- [ ] `git diff trading/` rỗng.
- [ ] `grep -rn "SABOTAGE" .` không ra kết quả trong mã nguồn.
- [ ] ruff sạch.
- [ ] Chưa commit, chưa push.
