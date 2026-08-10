# Plan 2026-08-10 — Flake NATS: `assert []` trong test_engine_main

## Triệu chứng

```
FAILED tests/test_engine_main.py::test_engine_run_restores_real_risk_halt_on_startup
E   assert []
```

Tần suất ~1/8 trong full suite, không tái hiện được khi chạy riêng file. Đã xuất
hiện ít nhất một lần trong loạt đo ngày 2026-08-10.

## Cơ chế — ĐÃ TÁI HIỆN TẤT ĐỊNH, không phải giả thuyết

`signals_seen` rỗng nghĩa là `handle_crossover` chưa bao giờ được gọi. Nguyên
nhân: engine tiêu thụ **message cũ còn sót trong stream BARS** (do test trước để
lại), dùng hết hạn mức `max_messages=25` trước khi chạm tới 25 nến của chính test
này, nên chuỗi giá không bao giờ tạo ra crossover.

Tôi ép đúng điều kiện đó và đo:

```
stale= 0 purge= True -> signals_seen=1  PASS
stale= 5 purge= True -> signals_seen=1  PASS
stale= 5 purge=False -> signals_seen=0  FAIL  <- đúng `assert []`
stale=25 purge=False -> signals_seen=0  FAIL  <- đúng `assert []`
```

Script repro: `scripts/.repro_nats_flake.py` — chạy bằng
`uv run python scripts/.repro_nats_flake.py`. File có dấu chấm đầu tên nên
pytest không thu gom; KHÔNG commit nó.

## Chỗ hỏng

`tests/test_engine_main.py:61-73`:

```python
@pytest.fixture(autouse=True)
async def reset_stream_and_durable_consumer():
    ...
    try:
        await js.delete_consumer("BARS", "engine")
    except Exception:
        pass
    try:
        await js.purge_stream("BARS")
    except Exception:
        pass
```

Nuốt **mọi** exception và **không hề kiểm tra** việc reset có thành công không.
Khi purge không ăn, test vẫn chạy tiếp trên state bẩn rồi chết ở một assert
cách đó 200 dòng, không có manh mối nào.

## Điều CHƯA biết — và đừng giả vờ là đã biết

Tôi tái hiện được **hậu quả**, chưa tái hiện được **nguyên nhân gốc**: tại sao
purge thỉnh thoảng không ăn. Vài khả năng chưa loại trừ:

- `purge_stream` ném lỗi thật (bị nuốt nên không ai thấy).
- Message tới **sau** lúc purge, do một publisher của test trước chưa flush xong.
  `tests/test_collector_main.py` (chạy trước test_engine_main theo alphabet) cũng
  publish vào cùng stream BARS.
- Timing của JetStream khi container vừa khởi động.

**Nhiệm vụ này KHÔNG yêu cầu bạn tìm ra nguyên nhân gốc.** Nó yêu cầu làm cho
lỗi không còn xảy ra được, và nếu có xảy ra thì phải hiện ra ngay chỗ thật.

## Các bước

### Bước 1 (RED) — Dựng lại repro trong suite

Viết test tái hiện đúng điều kiện: để lại message cũ trong stream rồi chạy kịch
bản của `test_engine_run_restores_real_risk_halt_on_startup`.

→ kiểm chứng: test FAIL với `signals_seen == 0`, **paste output RED**. Nếu nó
không fail thì bạn chưa dựng đúng điều kiện — dừng lại và báo, đừng đi tiếp.

### Bước 2 (GREEN) — Cách ly test khỏi state toàn cục

Làm cho test **không thể** ăn nhầm message của test khác. Hai hướng, chọn một và
nói rõ lý do:

- **(a) Mỗi test một symbol riêng** (vd `ENGT_RESTORE`, `ENGT_HALT`...). Engine
  subscribe `bars.>` nên vẫn nhận hết — nên cách này một mình CHƯA đủ, phải kèm
  lọc hoặc durable riêng.
- **(b) Mỗi test một durable consumer riêng + subject riêng.** `run()` đang
  hard-code `durable="engine"` và `"bars.>"`. Nếu đổi thì phải đổi ở
  `trading/engine/main.py` — **hỏi tôi trước**, vì đó là code sản xuất và tôi
  không muốn đổi tên durable của production chỉ để chiều test.

Nếu cả hai đều cần đụng code sản xuất, **dừng lại và báo** kèm đề xuất; tôi
quyết.

→ kiểm chứng: repro ở Bước 1 chuyển sang PASS, và nó PASS vì test được cách ly
chứ không phải vì bạn nới lỏng assert.

### Bước 3 — Làm cho lỗi reset hiện ra ngay

Sửa fixture: **không nuốt lỗi**. Sau khi reset xong phải xác nhận stream thật sự
rỗng (đọc lại stream info / message count) và fail ngay tại fixture nếu không.

Lý do: kể cả sau Bước 2, còn nhiều nguồn bẩn khác. Một fixture nuốt lỗi biến sự
cố hạ tầng thành một assert khó hiểu ở tận đâu. Đây là phần giá trị nhất của
task này, ngay cả khi nguyên nhân gốc không bao giờ tìm ra.

Giữ lại việc bỏ qua lỗi "consumer không tồn tại" — đó là trạng thái hợp lệ ở lần
chạy đầu. Chỉ bắt đúng loại lỗi đó, đừng dùng `except Exception` trần.

→ kiểm chứng: cố tình để lại message trong stream rồi chạy → fixture phải fail
với thông điệp nói rõ stream chưa rỗng, KHÔNG phải `assert []`. Paste output.

### Bước 4 — Đo lại

`uv run pytest -q` **≥ 15 lần liên tiếp**, ghi ra file (`>> log 2>&1`), paste kết
quả từng lần.

**Đọc kỹ:** 15 lần xanh KHÔNG chứng minh flake đã hết — flake này chạy ~1/8 nên
15 lần sạch vẫn còn khoảng 14% khả năng bỏ sót. Báo cáo phải nói đúng điều đó,
đừng viết "đã sửa xong flake". Giá trị thật nằm ở Bước 2 (cách ly) và Bước 3
(lỗi hiện ra ngay), không nằm ở chuỗi xanh.

## Phạm vi phẫu thuật

**Được sửa:** `tests/test_engine_main.py`, và file test mới nếu cần.

**KHÔNG đụng** `trading/engine/main.py` hay bất kỳ code sản xuất nào **mà không
hỏi tôi trước**. Nếu cách ly bắt buộc phải đổi `durable=` hoặc subject thì dừng
lại và đề xuất.

**KHÔNG đụng** `tests/test_collector_main.py`, `tests/test_publisher.py` — nếu
bạn thấy chúng cũng làm bẩn stream thì **báo cáo**, đừng tự sửa.

**KHÔNG chạy `ruff check --fix`.** KHÔNG commit, KHÔNG push.

## Dừng lại và hỏi nếu

- Bước 1 không tái hiện được.
- Bước 2 bắt buộc phải đổi code sản xuất.
- Bạn phát hiện nguyên nhân gốc thật sự của việc purge không ăn — đó là tin tốt,
  báo ngay, có thể sẽ đổi hướng cả kế hoạch.
