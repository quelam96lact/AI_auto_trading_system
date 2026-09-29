# Brief đợt 124 — dọn lỗi tồn: rò token SSI, NAV sai trong khung bảo trì SSI, bẫy đường dẫn rỗng, pre-push bỏ sót test đường tiền thật

**Base commit:** `09cf20e`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.

Bốn phần **độc lập**, mỗi phần có cổng kiểm riêng. Làm theo thứ tự A → B → C → D. Một phần kẹt thì **báo lại và làm tiếp phần sau**, đừng dừng cả đợt. Claude nghiệm thu từng phần riêng.

| Phần | Việc | Nằm trên đường tiền thật? | Vì sao đáng làm |
|---|---|---|---|
| A | Bịt rò token SSI ra log của bộ ghi sổ lệnh | không (log) | token có scope `trading:*:*`, bị ghi ra đĩa **mỗi sáng** |
| B | Không ghi danh mục rỗng / số dư bằng 0 **đột ngột** do SSI trả trong khung bảo trì | **có** (NAV, vị thế) | 28/09 ghi NAV = 0 và NAV = **−31 triệu** cho tài khoản thật đang có ~193 triệu |
| C | `load_universe("")` đọc nhầm thư mục hiện hành | không (thư viện đo) | bẫy đã làm agent đợt 120 phải né bằng tên file giả |
| D | Pre-push chạy cả test integration khi hạ tầng test sẵn | không (quy trình) | hiện **142 test integration**, gồm mọi test đường tiền thật, không chạy trước khi push lên `main` |

---

## Phần A — bịt rò token SSI ra log ở bộ ghi sổ lệnh

### A.0. Chuyện gì đang xảy ra

Mỗi sáng lúc 08:40, task `trading-orderbook-recorder` chạy `scripts/record_vn30f_orderbook.py`. Khi mở WebSocket, SDK SSI ghi ra `logs/orderbook-recorder.log` một dòng mức INFO chứa **nguyên header `Authorization: Bearer <JWT>`**. Token có scope `trading:*:*` và liệt kê cả ba tài khoản.

| Kiểm (Claude, 29/09) | Kết quả |
|---|---|
| Số dòng chứa token trong `logs/` | 1, chỉ trong `orderbook-recorder.log` |
| `logs/` có bị git bỏ qua | có (`.gitignore:35`), nên token **chưa từng lên GitHub** |
| Log docker của collector | 0 dòng, nhờ bản sửa **LOG-1** |
| Hạn của token bị lộ | 15 phút (`exp − iat = 900`), đã hết hạn |

**Bản sửa đã có sẵn, chỉ là không được dùng chung.** `trading/collector/main.py::_configure_logging` có:

```python
# LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
...
logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
```

`record_vn30f_orderbook.py` (brief 87/90) ra đời sau LOG-1 nên không có dòng này.

Claude đã đọc mã nguồn SDK (`.venv/Lib/site-packages/ssi_sdk/`):

| Vị trí | Mức | Nội dung |
|---|---|---|
| `transport/websocket_client.py:76` | INFO | header WebSocket — **chính dòng đã lộ** |
| `transport/websocket_client.py:278` | DEBUG | header WebSocket |
| `transport/rest_client.py:30` | DEBUG | nguyên thân phản hồi HTTP; với endpoint xác thực thì đó **là token** |

Hai dòng đầu thuộc logger `ssi_sdk.transport.websocket`, nên `setLevel(WARNING)` chặn cả hai. Dòng thứ ba chỉ lộ khi bật DEBUG; trong code chạy theo lịch **không** chỗ nào bật.

### A.1. Việc phải làm

1. **Đưa LOG-1 thành một hàm dùng chung** trong `trading/logging_setup.py`, ví dụ `silence_ssi_sdk_secrets()`. **Chuyển nguyên** khối chú thích LOG-1 từ `collector/main.py`: chú thích đó giải thích vì sao dùng `setLevel` chứ **không** dùng bộ lọc regex, và vì sao **không** đụng `ssi_sdk.services.token_manager`. Giữ nguyên quyết định đó. `collector/main.py::_configure_logging` gọi hàm mới thay cho dòng `setLevel` cũ.
2. **Gọi nó trong `record_vn30f_orderbook.py`**, **sau** mọi chỗ cấu hình logging khác và **trước** khi tạo `AsyncStream`. SDK có thể tự cấu hình logging khi khởi tạo `Config` / `AsyncAuth`; nếu gọi quá sớm, `setLevel` có thể bị đè. Kiểm chuyện này bằng test ở bước 3, đừng suy đoán.
3. **Test** theo khuôn `tests/test_collector_logging.py`: dựng cấu hình logging **giống hệt** đường chạy thật của bộ ghi, phát một bản ghi INFO qua logger `ssi_sdk.transport.websocket` chứa chuỗi giả `Authorization: Bearer TEST.JWT.TOKEN`, rồi khẳng định chuỗi đó **không** xuất hiện ở handler, file hay stream nào. Không dùng token thật, không mở kết nối mạng.
4. **Xoá token trong log cũ:** trong `logs/`, thay mọi chuỗi JWT đứng sau `Bearer ` bằng `[REDACTED]`. **Không in token, không ghi token vào báo cáo.** Chỉ báo **số dòng** trước và sau. Không sao lưu các file log này, vì bản sao lưu sẽ giữ lại chính token cần xoá.

### A.2. Cổng

```
1. uv run pytest tests/test_collector_logging.py -v      → xanh, test cũ KHÔNG bị sửa
2. test mới của bước 3                                  → xanh
3. Đếm "Bearer ey" trong logs/ (chỉ in SỐ ĐẾM)          → trước ≥ 1, sau = 0
4. grep "ssi_sdk.transport.websocket" toàn repo         → chỉ còn dòng setLevel trong hàm mới + test
```

| Phá thử | Đột biến | Phải RED |
|---|---|---|
| A1 | Bỏ lời gọi hàm mới trong `record_vn30f_orderbook.py` | test bước 3 |
| A2 | Trong hàm mới, đổi `logging.WARNING` thành `logging.INFO` | test bước 3 **và** `test_collector_logging.py` |

A2 chứng minh cả hai đường chạy đi qua **cùng một** hàm. Nếu chỉ một test đỏ, một đường vẫn còn giữ bản sao riêng.

**Không được đụng:** `scripts/_ssi_spike_common.py` và các script `spike_ssi_sdk_*`. Chúng **cố ý** bật `log_level="DEBUG"` (docstring `make_config` giải thích: bug `APIError.response_body` luôn `None` của ssi-sdk 3.1.0). Chủ dự án chạy tay, in ra console. **Báo lại** mức rò của chúng, **không sửa**. `scripts/.ssi_sdk_token.json`: **không mở, không đọc, không in.**

---

## Phần B — không ghi danh mục rỗng / số dư bằng 0 đột ngột do SSI trả trong khung bảo trì

### B.0. Bằng chứng (Claude đo trên DB thật, 29/09)

Tài khoản margin `0434226` (nơi có tiền thật), quanh 23:18 ngày 28/09:

| Giờ VN | `account_balance` | `total_debt` | Số dòng vị thế | NAV ghi |
|---|---|---|---|---|
| 23:16:18 | −31.226.549 | 31.225.333 | 6 mã / 5.060 cp | 193.133.667 |
| **23:18:52** | **0** | **0** | **0** | **0** |
| **23:23:56** | −31.234.541 | 31.233.279 | **0** | **−31.233.279** |
| 23:29:16 | −31.234.541 | 31.233.279 | 6 mã / 5.060 cp | 193.125.721 |

Tài khoản `0434221` cũng ra NAV = 0 lúc 23:18:52. Cả hai lần đều có `unpriced_symbols` **rỗng**, nên **không có cảnh báo nào**.

**Mẫu hình lặp lại:** trong toàn bộ lịch sử `account_balance_snapshot`, dòng có **cả ba** trường = 0 xuất hiện **đúng 14 lần ở mỗi tài khoản**, tức luôn **cả hai tài khoản cùng một lúc**. Số dư thật của hai tài khoản độc lập không thể cùng về 0 đồng thời 14 lần; đây là lỗi phía SSI. `0434221` **chưa từng** có dòng vị thế nào, khớp với tình huống b3.

**Đây KHÔNG phải lỗi đã vá ở đợt 88** (`32fbf80`). Bản vá đó chặn trường số dư **bị thiếu**. Ở đây trường **có mặt nhưng bằng 0**, và danh sách vị thế là `None`. Bản vá đợt 88 cố ý ghi "số 0 thật". Nó đã nằm trong container từ 26/09, nên hai dòng 28/09 xảy ra **sau** khi bản vá có hiệu lực.

Khung giờ khớp với cửa sổ bảo trì SSI đã ghi nhận (22:00 đến khoảng 23:30 VN). 23:18 cũng trùng lúc Claude khởi động lại collector, nên chưa tách được hoàn toàn hai nguyên nhân. Thiết kế dưới đây đúng cho cả hai.

### B.1. Cơ chế trong code

- `account_sync.py::_sync_positions`: SSI trả `None` thì thành `rows = []`, rồi `record_position_sync(account_no, ts)`, tức ghi nhận là **"đã đồng bộ và không nắm gì"** (SYNC-LOG-1). `read_real_positions` từ đó trả `{}`.
- `account_sync.py::_sync_balance`: đã chặn trường thiếu (`REQUIRED_BALANCE_FIELDS`), nhưng ba trường cùng bằng 0 vẫn được ghi.
- `_sync_nav`: NAV = `withdrawable − total_debt + Σ(qty × giá)`. Vị thế rỗng thì cho ra 0 − 31 triệu = **−31 triệu**. Số dư bằng 0 thì cho ra 0.

**Danh mục rỗng LÀ trạng thái hợp lệ:** `0434221` rỗng thật từ lâu (chú thích SYNC-1 ở dòng 97–103). Nên **không được** chặn "rỗng". Chỉ chặn **chuyển đột ngột từ có sang không**.

### B.2. Thiết kế đã chốt — xác nhận hai lần liên tiếp

**Vị thế:** trong `_sync_positions`, khi SSI trả danh mục **rỗng** **và** snapshot gần nhất đã lưu của tài khoản đó **không rỗng**, đó là "rỗng đột ngột":

- **Lần đầu:** **không** ghi, **không** gọi `record_position_sync`; `alert("WARN", ...)` nêu `account_no` và số mã của snapshot trước. Đánh dấu "đang chờ xác nhận" cho tài khoản đó.
- **Lần đồng bộ kế tiếp vẫn rỗng:** ghi bình thường (gồm `record_position_sync`), gỡ dấu, `alert("WARN", ...)` "xác nhận danh mục rỗng".
- **Lần kế tiếp không rỗng:** gỡ dấu, ghi bình thường.

**Số dư:** trong `_sync_balance`, khi cả ba trường `accountBalance`, `totalDebt`, `withdrawable` **cùng bằng 0** **và** dòng số dư gần nhất đã lưu có ít nhất một trường khác 0, áp **cùng** quy tắc xác nhận hai lần.

**Hệ quả:** trong lần bị hoãn, `_sync_nav` đọc snapshot **trước đó** (số dư và/hoặc vị thế cũ 5 phút), nên NAV giữ đúng giá trị thật thay vì 0 hoặc −31 triệu.

**Dấu "đang chờ xác nhận"** giữ trong bộ nhớ tiến trình collector (ví dụ một `dict` cấp module, theo `account_no` và loại). Collector khởi động lại thì mất dấu, nên lần rỗng đầu tiên sau khởi động lại sẽ bị hoãn thêm một nhịp. Đó là hướng **an toàn**, chấp nhận được. Test phải reset được trạng thái này.

**Cái giá, phải ghi vào docstring:** khi chủ tài khoản bán sạch danh mục thật, hệ thống ghi nhận chậm **một nhịp đồng bộ** (~5 phút). Trong 5 phút đó, đường lệnh thật vẫn tưởng còn vị thế. Nếu nó sinh lệnh SELL thì SSI từ chối vì không có cổ phiếu, nên không mất tiền. Ngược lại, không có quy tắc này thì một cú rỗng giả trong phiên sẽ làm NAV âm, và cổng vốn chặn **mọi** lệnh BUY.

**Không** chặn theo khung giờ (ví dụ "bỏ qua 22:00–23:30"): khung đó đã từng phải nới một lần (memory NAV-0: 23:04 nằm ngoài khung ban đầu), và dòng 26/09 lúc 00:57 cũng nằm ngoài. Quy tắc theo **dữ liệu** bền hơn quy tắc theo **giờ**.

### B.3. Test (fake portfolio / fake storage, không cần SSI)

| # | Tình huống | Phải |
|---|---|---|
| b1 | snapshot trước 6 mã, SSI trả `None` | **không** ghi vị thế, **không** gọi `record_position_sync`, có WARN |
| b2 | như b1, rồi lần sau SSI vẫn `None` | lần 2 ghi + `record_position_sync` + WARN "xác nhận" |
| b3 | tài khoản **luôn** rỗng (snapshot trước rỗng), SSI trả `None` | ghi **ngay** lần đầu (giữ hành vi SYNC-1 cho `0434221`) |
| b4 | như b1, rồi lần sau SSI trả 6 mã | gỡ dấu, ghi 6 mã |
| b5 | số dư trước khác 0, SSI trả ba trường = 0 | **không** ghi số dư lần đầu, có WARN |
| b6 | tái hiện đúng 23:23:56: số dư thật, vị thế `None`, snapshot trước 6 mã | NAV được ghi **bằng** NAV tính từ 6 mã cũ, **không** bằng `−total_debt` |
| b7 | số dư thật với đúng một trường = 0 (ví dụ `withdrawable = 0` của tài khoản margin) | ghi **bình thường**: quy tắc chỉ bắt khi **cả ba** cùng = 0 |

b7 quan trọng: `0434226` là tài khoản margin, có `withdrawable = 0` **thật** ở phần lớn thời gian (4.970 trên 5.498 dòng số dư; chỉ 528 dòng khác 0, đo 29/09). Bắt nhầm nó là chặn đứng đồng bộ số dư của tài khoản có tiền.

| Phá thử | Đột biến | Phải RED |
|---|---|---|
| B1 | Bỏ điều kiện "snapshot trước không rỗng", tức hoãn mọi lần rỗng | b3 |
| B2 | Ghi ngay lần đầu (bỏ hoãn) | b1, b6 |
| B3 | Điều kiện số dư đổi từ "cả ba = 0" thành "bất kỳ trường nào = 0" | b7 |

### B.4. Kiểm trên hệ thống thật — Claude làm sau khi commit và rebuild

Ba đêm liên tiếp sau khi triển khai, Claude đếm `account_nav_snapshot` có `nav <= 0` từ 22:00 đến 01:30. Kỳ vọng: 0 dòng, và nếu SSI vẫn trả rỗng thì log collector phải có WARN "chờ xác nhận". **Agent không rebuild, không restart collector.**

---

## Phần C — `load_universe("")` đọc nhầm thư mục hiện hành

`trading/stock_study.py::load_universe(storage, exclude_file="exclusions.txt")` gọi `pathlib.Path(exclude_file).exists()`. Trên Windows, `Path("").exists()` trả `True` (trỏ vào `.`), rồi `read_text` ném `PermissionError`. Agent đợt 120 phải né bằng cách truyền tên file không tồn tại `__no_exclusions__.tmp`.

**Việc:** `exclude_file` là `None` hoặc chuỗi rỗng thì **không loại mã nào** và **không chạm filesystem**. Giữ nguyên mặc định `"exclusions.txt"`. Không đổi hành vi khi `exclude_file` là đường dẫn thật.

**Không** sửa cách né trong `measure_sepa_score_edge.py`: nó vẫn đúng, và sửa nó thì phải chứng minh lại đầu ra đợt 120/123 trùng hash.

**Cổng:** test `load_universe(storage, exclude_file="")` và `exclude_file=None` trả đủ vũ trụ, không ném lỗi. Phá thử C1: bỏ nhánh mới, test phải RED với `PermissionError` (trên Windows).

---

## Phần D — pre-push chạy cả test integration khi hạ tầng test sẵn

**Hiện trạng** (`.githooks/pre-push`, được quản lý trong repo qua `core.hooksPath=.githooks`): chạy `ruff check trading tests scripts` rồi `pytest -m "not integration" -q`. Ở đợt 121 và 123 con số đó là 1.260 passed, **142 deselected**. 142 test bị bỏ gồm mọi test cần DB: `compute_nav`, `read_last_close`, GUARD-1, vị thế…

**Việc:**
- Nếu container `nats-test` **đang chạy** (kiểm bằng `docker ps`; xem `CLAUDE.md` mục "Suite day du"), chạy **toàn bộ** `uv run pytest -q`.
- Nếu không, chạy `-m "not integration"` như cũ, **nhưng in cảnh báo rõ ràng**: số test integration bị bỏ, nói rõ đó gồm test đường tiền thật, và lệnh để bật hạ tầng (`docker compose --profile test up -d nats-test`). **Không chặn push** trong trường hợp này: bắt bật Docker chỉ để đẩy một thay đổi tài liệu là quá tay.
- Giữ nguyên bước ruff và điều kiện chỉ áp cho `refs/heads/main`.

**Cổng:** chạy hook bằng tay (không push), đưa vào stdin một dòng giả `refs/heads/main 0 refs/heads/main 0`, trong hai trạng thái: `nats-test` đang chạy (phải thấy số passed ≥ 1.402 và không có dòng `deselected`), và `nats-test` đã dừng (phải thấy dòng cảnh báo). Nộp output nguyên văn cả hai. Được phép `docker compose --profile test stop nats-test` rồi `up -d nats-test` để kiểm, **chỉ** với `nats-test`; **cấm** đụng mọi container khác.

---

## Tiêu chí chung cho cả đợt

```
uv run pytest -q   (TOÀN BỘ, không lọc marker)   → ≥ 1.402 passed + số test mới, 0 failed
uv run ruff check trading tests scripts          → sạch (đúng lệnh pre-push đang dùng)
gitnexus impact cho _sync_positions, _sync_balance, load_universe (CLI, --repo AI_auto_trading_system)
gitnexus detect-changes --repo AI_auto_trading_system
```

Phần B chạm đường NAV và vị thế của lệnh thật, nên `gitnexus impact` gần như chắc chắn báo HIGH. Việc của bạn là **báo**, không phải né.

## Phạm vi

**Được sửa:** `trading/logging_setup.py`, `trading/collector/main.py` (chỉ `_configure_logging`), `scripts/record_vn30f_orderbook.py`, `trading/collector/account_sync.py` (chỉ `_sync_positions`, `_sync_balance` và trạng thái chờ xác nhận), `trading/stock_study.py` (chỉ `load_universe`), `.githooks/pre-push`, các file test mới hoặc liên quan, và `logs/` (chỉ bước A.1.4).

**KHÔNG được đụng:** `_sync_nav`, `compute_nav`, `read_real_positions`, `record_position_sync`, `real_orders.py`, `engine/`; các script spike; `.venv/`; `exclusions.txt`; mọi scheduled task của Windows.

## Điều cấm

- **Không commit, không push.** Không rebuild, không restart engine hay collector (Claude làm sau khi commit, **ngoài giờ phiên**).
- **Không chạy `record_vn30f_orderbook.py`**, không mở kết nối SSI thật.
- Không đặt, sửa, huỷ lệnh; không bật `real_trading_enabled`; không chạy `--send`.
- **Không in, không ghi lại bất kỳ token, key, secret nào.** Chỉ báo số đếm.
- Không đọc nội dung `.env`. Cấm `git checkout`, `git restore`, `git stash`.
- **Không tạo, sửa, xoá scheduled task** (việc của chủ dự án).

## Báo cáo phải có

1. Với mỗi phần A–D: diff, output nguyên văn của cổng, và bảng phá thử với thông điệp lỗi thật.
2. Phần nào kẹt, kẹt ở đâu.
3. Chỗ nào brief sai hoặc mơ hồ. Brief của Claude đã sai ở các đợt 118, 120 và 122.

---

## Phụ lục — việc của CHỦ DỰ ÁN, không giao agent

**Đã bỏ khỏi đợt này mọi việc về NGUỒN** (cấu hình pin của scheduled task, máy ngủ làm Docker dừng): hệ thống chạy thật sẽ ở **VPS 24/7**, chỉ dừng khi bảo trì cuối tuần; laptop hiện tại là môi trường tạm (chủ dự án chốt 29/09/2026).

### P.1. Script spike bật DEBUG

Xem Phần A: chúng in cả phản hồi xác thực (tức token) ra console khi chạy. Có tắt hay không là quyết định của chủ dự án.

---

## Đã cân nhắc và KHÔNG đưa vào đợt này

| Việc | Vì sao không |
|---|---|
| Gộp mốc niêm phong forex/crypto về một hằng số | **Rút lại.** Mỗi con số là cận đọc **đã tiền đăng ký** của một đợt đo, chỉ tình cờ bằng mốc niêm phong. Gộp lại thì ngày dời mốc, mọi phép đo cũ chạy lại sẽ lặng lẽ đọc holdout. Hiện trạng lặp nhưng an toàn. |
| Lỗ nến khi Docker restart **giữa** phiên (memory warm-up) | Đợt 81 đã vá phần khởi động; phần giữa phiên hiện được **cảnh báo** (GAP-1), chưa tự vá. Tự vá cần thiết kế (backfill publish NATS hoặc engine tự nạp), không phải việc dọn dẹp. |
| Lỗ hổng "vị thế không kiểm tuổi" (memory 30/08) | **Đã vá** sau đó: `real_orders.py:93/251` kiểm tuổi; `heartbeat_check.py` nhánh 2D báo sau 15 phút; cổng go-live kiểm. Memory đó đã cũ, Claude sẽ cập nhật. |
