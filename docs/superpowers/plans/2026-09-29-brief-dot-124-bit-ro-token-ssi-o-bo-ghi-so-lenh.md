# Brief đợt 124 — bịt rò token SSI ra log ở bộ ghi sổ lệnh VN30F, dùng chung bản sửa LOG-1 của collector

**Base commit:** `3f8e362`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.

---

## §0. Chuyện gì đang xảy ra

Mỗi sáng lúc 08:40, task `trading-orderbook-recorder` chạy `scripts/record_vn30f_orderbook.py`. Khi mở WebSocket, SDK SSI ghi ra `logs/orderbook-recorder.log` một dòng mức INFO chứa **nguyên header `Authorization: Bearer <JWT>`**. Token đó có scope `trading:*:*` và liệt kê cả ba tài khoản.

Claude phát hiện điều này ngày 29/09 khi đọc log để điều tra mã lỗi `0x8007042B` của task. Mức độ hiện tại:

| Kiểm | Kết quả |
|---|---|
| Số dòng chứa token trong `logs/` | 1, chỉ trong `orderbook-recorder.log` |
| `logs/` có bị git bỏ qua không | có (`.gitignore:35`), nên token **chưa từng lên GitHub** |
| Log docker của collector | 0 dòng, vì collector đã có bản sửa **LOG-1** |
| Hạn của token bị lộ | 15 phút (`exp − iat = 900`), cấp 28/09 08:40, **đã hết hạn** |

**Bản sửa đã có sẵn, chỉ là không được dùng chung.** `trading/collector/main.py::_configure_logging` có:

```python
# LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
...
logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
```

`record_vn30f_orderbook.py` (brief 87/90) ra đời sau LOG-1 nên không có dòng này. Lỗi quen thuộc: sửa ở một nơi, không lan sang nơi khác.

### §0.1. Claude đã đọc mã nguồn SDK — hai điểm rò, cùng một logger

Trong `.venv/Lib/site-packages/ssi_sdk/`:

| Vị trí | Mức | Nội dung |
|---|---|---|
| `transport/websocket_client.py:76` | INFO | `"Connecting to WebSocket with headers: %s", self._headers` — **chính dòng đã lộ** |
| `transport/websocket_client.py:278` | DEBUG | `"Connecting to WebSocket with headers: %s", header` |
| `transport/rest_client.py:30` | DEBUG | `"Received response: %s %s", response.status_code, response.text` — thân phản hồi của endpoint xác thực **chính là token** |

Hai dòng đầu thuộc logger `ssi_sdk.transport.websocket`, nên `setLevel(WARNING)` chặn được cả hai. Dòng thứ ba chỉ lộ khi có ai bật DEBUG; trong code chạy thật **không** chỗ nào bật (grep `level=logging.DEBUG`, `setLevel(logging.DEBUG)` trong `trading/` và `scripts/` chỉ thấy `scripts/_ssi_spike_common.py`, xem §3).

---

## §1. Việc phải làm

### Bước 1 — đưa LOG-1 thành một hàm dùng chung

Tạo trong `trading/logging_setup.py` (module đã có, đang chứa cấu hình logging của dự án) **một** hàm, ví dụ:

```python
def silence_ssi_sdk_secrets() -> None:
    """LOG-1: ... (chuyển nguyên chú thích từ collector/main.py sang đây)"""
    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
```

- **Chuyển nguyên** khối chú thích LOG-1 hiện có trong `collector/main.py::_configure_logging`. Chú thích đó giải thích vì sao dùng `setLevel` chứ **không** dùng bộ lọc regex, và vì sao **không** đụng `ssi_sdk.services.token_manager`. Đó là quyết định thiết kế có lý do; **giữ nguyên**, đừng đổi sang regex.
- `collector/main.py::_configure_logging` gọi hàm mới **thay cho** dòng `setLevel` cũ. Hành vi collector không đổi.

→ **Kiểm bằng:** `tests/test_collector_logging.py` hiện có vẫn xanh, không sửa assertion nào của nó.

### Bước 2 — gọi nó trong bộ ghi sổ lệnh

Trong `scripts/record_vn30f_orderbook.py`, gọi `silence_ssi_sdk_secrets()` **sau** mọi chỗ cấu hình logging khác, và **trước** khi tạo `AsyncStream`.

Thứ tự quan trọng. SDK có thể tự cấu hình logging khi khởi tạo `Config` / `AsyncAuth`, ví dụ đặt lại mức của logger. Nếu vậy thì một lời gọi `setLevel` đặt quá sớm sẽ bị đè. **Tự kiểm chuyện này** bằng test ở Bước 3, không suy đoán.

→ **Kiểm bằng:** test ở Bước 3.

### Bước 3 — test chứng minh token không ra log

Viết test theo khuôn `tests/test_collector_logging.py`: dựng cấu hình logging **giống hệt** đường chạy thật của `record_vn30f_orderbook.py` (gồm cả phần SDK tự cấu hình nếu có), phát một bản ghi mức INFO qua logger `ssi_sdk.transport.websocket` có chứa chuỗi giả `Authorization: Bearer TEST.JWT.TOKEN`, rồi khẳng định chuỗi đó **không** xuất hiện ở handler/file/stream nào.

Không dùng token thật. Không mở kết nối mạng.

### Bước 4 — xoá token còn nằm trong log cũ

Trong `logs/` (kể cả file đã xoay vòng nếu có), thay mọi chuỗi JWT đứng sau `Bearer ` bằng `[REDACTED]`. Chỉ thay đúng phần token, giữ nguyên phần còn lại của dòng.

- **Không in token ra màn hình, không ghi token vào báo cáo.** Chỉ báo **số dòng** trước và sau: trước ≥ 1, sau = 0.
- Không cần sao lưu các file log này: sao lưu sẽ giữ lại chính token cần xoá, và token đã hết hạn.

---

## §2. Tiêu chí hoàn thành

```
1. uv run pytest tests/test_collector_logging.py -v        → xanh, test cũ KHÔNG bị sửa
2. uv run pytest <test mới của Bước 3> -v                  → xanh
3. uv run pytest -q   (TOÀN BỘ, không lọc marker)          → ≥ 1.402 passed, 0 failed
4. uv run ruff check trading tests scripts/record_vn30f_orderbook.py   → sạch
5. Đếm "Bearer ey" trong logs/ (chỉ in SỐ ĐẾM): trước ≥ 1, sau = 0
6. grep "ssi_sdk.transport.websocket" toàn repo: chỉ còn dòng setLevel trong
   hàm mới ở trading/logging_setup.py, cộng test. Không còn bản sao nào.
```

### §2.1. Hai phép phá thử bắt buộc

| # | Đột biến | Phải RED |
|---|---|---|
| 1 | Bỏ lời gọi `silence_ssi_sdk_secrets()` trong `record_vn30f_orderbook.py` | test Bước 3 |
| 2 | Trong hàm mới, đổi `logging.WARNING` thành `logging.INFO` | test Bước 3 **và** `test_collector_logging.py` |

Phép 2 chứng minh cả hai đường chạy thật sự đi qua **cùng một** hàm. Nếu chỉ một test đỏ, nghĩa là một đường vẫn đang giữ bản sao riêng.

Như các đợt trước: file có thể là CRLF, nên in `changed=True` và grep lại sau mỗi đột biến. Phục hồi bằng bản sao lưu tạo **sau** khi code đã xong.

### §2.2. Kiểm trên đường chạy thật — do Claude làm, không phải agent

Sáng hôm sau khi commit, task 08:40 sẽ tự chạy bộ ghi. Claude sẽ đếm `Bearer ey` trong `logs/orderbook-recorder.log` sau phiên. Phải bằng 0, **và** job kiểm 15:30 vẫn phải báo ĐẠT (bộ ghi vẫn ghi đủ dữ liệu). **Agent không tự chạy bộ ghi**: nó mở kết nối stream thật tới SSI.

---

## §3. Phạm vi

**Được sửa:** `trading/logging_setup.py`, `trading/collector/main.py` (chỉ `_configure_logging`), `scripts/record_vn30f_orderbook.py`, một file test mới, và các file trong `logs/` (chỉ Bước 4).

**KHÔNG được đụng:**
- `scripts/_ssi_spike_common.py` và bốn script `spike_ssi_sdk_*` mở `AsyncStream`. Chúng **cố ý** bật `log_level="DEBUG"`: docstring `make_config` giải thích đó là cách duy nhất xem nội dung lỗi thật từ SSI, do bug `APIError.response_body` luôn `None` của ssi-sdk 3.1.0. Chúng do chủ dự án chạy tay, in ra console, không theo lịch. **Báo lại** mức rò của chúng (DEBUG thì lộ cả `rest_client.py:30`), **không sửa**. Có sửa hay không là quyết định của chủ dự án.
- `scripts/.ssi_sdk_token.json`: **không mở, không đọc, không in.** Nó đã bị git bỏ qua và chưa từng được commit.
- Mọi file trong `.venv/` (không vá SDK).
- Mọi thứ khác.

---

## §4. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container (collector đổi nên Claude sẽ rebuild sau khi commit).
- **Không chạy `record_vn30f_orderbook.py`**, không mở kết nối SSI thật dưới bất kỳ hình thức nào.
- Không đặt, sửa, huỷ lệnh; không bật `real_trading_enabled`; không chạy `--send`.
- **Không in, không ghi lại bất kỳ token, key, secret nào**, kể cả token đã hết hạn và kể cả trong báo cáo. Chỉ báo số đếm.
- Không đọc nội dung `.env`.
- Cấm `git checkout`, `git restore`, `git stash`.

---

## §5. Giả định của tôi — sai thì dừng và báo

1. `setLevel(WARNING)` trên logger `ssi_sdk.transport.websocket` chặn được cả `websocket_client.py:76` (INFO) và `:278` (DEBUG). Căn cứ: cả hai gọi `logger.info` / `logger.debug` của cùng module. Nếu module đó dùng tên logger khác, test Bước 3 sẽ lộ ra.
2. SDK không đặt lại mức logger **sau** khi bộ ghi đã gọi `silence_ssi_sdk_secrets()`. Chưa kiểm; test Bước 3 phải dựng đúng thứ tự khởi tạo thật để phát hiện nếu có.
3. Không có đường chạy **theo lịch** nào khác mở WebSocket SSI ngoài collector và bộ ghi. Căn cứ: grep `AsyncStream` chỉ thấy `collector/feed.py`, `record_vn30f_orderbook.py` và bốn script spike.
