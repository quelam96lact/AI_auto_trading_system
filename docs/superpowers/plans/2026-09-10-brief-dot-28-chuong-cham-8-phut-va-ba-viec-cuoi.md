# Brief đợt 28 — Chuông kêu chậm 8 phút, và ba việc cuối

Ngày giao: 10/09/2026, 10:40.
Base: `58aadc3` (main, cây sạch).
Người giao: Claude (planner/auditor).

Đợt 27 đã nghiệm thu và commit: chuông 2C hết chết câm, `BarLatch` hết phát lại khung đã
chốt. 640 test pass, ruff sạch, cổng cứng VN tái lập chính xác.

Brief này đóng nốt **một lỗi tôi đo được khi audit** cộng ba việc của đợt 26/27 chưa làm.

---

## 1. Bốn việc

| Task | Việc | Khi nào |
|---|---|---|
| 1 | Chuông 2C mất **489,5 giây** mới kêu khi NATS chết | ngay |
| 2 | Kết luận HII câm bằng số | ngay |
| 3 | Đọc message thô phiên 10/09 | **sau 15:05** |
| 4 | Triển khai image mới | **sau 15:05**, sau khi Task 1–3 xong |

Ràng buộc của đợt 26/27 giữ nguyên toàn bộ. Nhắc lại phần dễ quên: `real_trading_enabled`
giữ `false`; không gọi SSI/BingX; `config/config.yaml` không sửa; không `TRUNCATE`/`DROP`;
**không `delete`/`purge`/`add`/`update` stream hay consumer NATS**; không xoá file;
**không commit, không push**; mọi `git diff` copy từ terminal.

---

## Task 1 — Chuông kêu sau 8 phút 10 giây thì không còn là chuông

### 1.1. Bằng chứng đo được

Tôi đặt `NATS_URL` trỏ vào một cổng đóng (mô phỏng NATS chết — đúng tình huống chuông sinh ra
để phát hiện) và bấm giờ:

```
ConnectionRefusedError: [WinError 1225] The remote computer refused the network connection
[engine-consumer] LỖI: Không thể kết nối NATS hoặc đọc consumer 'engine': nats: no servers available
exit 1
THOI GIAN: 489.5 giay
```

Chuông **có** kêu (exit 1, đường `send_telegram` thông) — nhưng sau **8 phút 10 giây**.

### 1.2. Nguyên nhân

`nats-py` mặc định (`.venv/Lib/site-packages/nats/aio/client.py`):

```
DEFAULT_RECONNECT_TIME_WAIT = 2  # in seconds
DEFAULT_MAX_RECONNECT_ATTEMPTS = 60
```

`allow_reconnect` mặc định `True`, nên mỗi lời gọi `nats.connect` thử lại 60 lần × 2 giây =
120 giây trước khi chịu ném lỗi. `engine_consumer_check.py:43,45` gọi **hai lần** (URL chính
rồi URL dự phòng) → khoảng 489 giây.

`connect_timeout=3` mà agent đặt **không có tác dụng gì** ở đây: nó giới hạn thời gian một
lần bắt tay TCP, không giới hạn số lần thử lại.

### 1.3. Vì sao đây là lỗi thật, không phải chuyện nhỏ

Chuông này sinh ra để phát hiện **đúng** tình huống NATS/consumer có vấn đề. Nhưng đúng lúc
đó nó lại chậm nhất. Hệ quả cụ thể:

- Chạy bằng scheduled task 5 phút/lần → các lần chạy **chồng lên nhau**, mỗi lần treo 8 phút.
- Scheduled task nào đặt timeout dưới 8 phút → chuông **bị giết trước khi kịp kêu**, và ta
  quay lại đúng trạng thái chết câm mà đợt 27 vừa sửa.

Đây vẫn là bài học `51ff6de`, chỉ đổi hình dạng: chuông không chết vì thiếu phụ thuộc nữa,
mà chết vì thư viện thử lại quá lâu.

### 1.4. Việc cần làm

Trong `scripts/engine_consumer_check.py`, cả hai lời gọi `nats.connect`: tắt hẳn cơ chế thử
lại — truyền `allow_reconnect=False` (hoặc `max_reconnect_attempts=0`) cùng với
`connect_timeout` đang có. Chuông chỉ cần một lần thử dứt khoát; NATS chết thì kêu ngay, đó
là toàn bộ nhiệm vụ của nó.

Làm **cùng việc đó** cho `scripts/replay_stream_check.py:65` (đang `connect_timeout=5`, cũng
sẽ treo 2 phút) — Task 3 dùng script này, không nên ngồi chờ vô ích.

**Không sửa** `scripts/probe_engine_consumer.py` và các file `.probe_*.py` / `.repro_*.py`:
đó là công cụ chẩn đoán chạy tay, có người ngồi xem, không phải chuông tự động.
**Không sửa** `trading/bus/publisher.py` — collector là dịch vụ chạy dài, **cần** thử lại;
tắt thử lại ở đó sẽ biến một cú nấc mạng thành mất dữ liệu.

### 1.5. Kiểm chứng — tiêu chí thành công

1. **Phép đo thật, có bấm giờ:** đặt `NATS_URL=nats://127.0.0.1:59999` (cổng đóng), chạy
   `scripts/engine_consumer_check.py --force`, đo thời gian tường.
   → Phải trả exit 1 trong **dưới 30 giây**. Dán nguyên văn output + thời gian đo được.
2. Đặt lại `NATS_URL` đúng, chạy lại → exit 0, đọc được `seq` và `bars_today` như thường.
3. Lặp mục 1 cho `replay_stream_check.py` → thoát trong dưới 30 giây.
4. Toàn bộ suite pass, ruff sạch, cổng cứng VN khớp từng chữ số.

---

## Task 2 — Kết luận HII câm bằng số

Đã giao ở đợt 26 (Task 6) và đợt 27 (Task 4), **cả hai lần đều không có kết quả trong báo
cáo**. Lần này làm cho xong.

`scripts/.probe_hii_silent.py` đã có sẵn. **Chỉ `SELECT`, chỉ báo cáo, không sửa một dòng code
nào.** Câu hỏi: điều kiện nào trong `octopus_pullback` không bao giờ thoả với phân bố giá của
HII, trong khi IJC thì thoả. Trả lời bằng số ở **từng tầng điều kiện** — bao nhiêu bar qua
được tầng 1, tầng 2, tầng 3, tầng 4 — chứ không phải một câu kết luận chung chung.

Nếu chưa làm được thì ghi thẳng "CHƯA LÀM" kèm lý do. Đừng bỏ trống lần thứ ba.

---

## Task 3 — Đọc message thô phiên 10/09 (**sau 15:05**)

Nguyên văn Task 3 của đợt 26, chưa thực hiện. Dùng `scripts/replay_stream_check.py` đã có
(sau khi sửa theo Task 1), **không viết lại**.

Tiêu chí: tỷ lệ message/bar của phiên 10/09 phải **lớn hơn 1 rõ rệt** (dự kiến 5–9×),
`volume` trong cùng khung tăng đơn điệu. Nếu ra ≈ 1,0 thì **dừng, báo cáo ngay**.

Đây là phép đo **trước khi sửa**, phải chạy **trước** Task 4 — sau khi triển khai thì không
còn phiên "trước khi sửa" nào để so sánh nữa. Ghi rõ dải seq đã đọc.

---

## Task 4 — Triển khai (**sau 15:05**, sau khi Task 1–3 xong)

Image đang chạy vẫn là `41371bc92882` dựng ngày 08/09. **Bản sửa lỗi nến chưa đóng vẫn chưa
lên sóng** — engine lúc này vẫn đang chạy chiến lược trên nến chưa đóng.

```
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

1. `uv run python scripts/deploy_drift_check.py` → **exit 0**.
2. `docker compose logs --tail=50 collector` và `engine` → không `CRITICAL`, không traceback.
3. Ghi lại `docker ps` và image ID mới.
4. Sau khi dựng lại, chạy `scripts/engine_consumer_check.py` một lần → ghi kết quả.

Kiểm chứng bản sửa thực sự hiệu quả (tỷ lệ message/bar về ≈ 1,0) là việc của **phiên 11/09**,
thuộc đợt sau. **Không** tự ý chạy collector ngoài giờ để ép ra số.

Giữ `dot20-rollback-collector:pre` và `dot20-rollback-engine:pre`. **Không xoá.**

---

## 5. Báo cáo — ngắn, và đừng để bị cắt

Báo cáo đợt 26 **và** đợt 27 đều bị cắt giữa chừng (đợt 26 cụt ở tiêu chí 5 Task 1; đợt 27
cụt ở mục 4 "Ruff Linter → All ch"). Cả hai lần tôi đều phải tự chạy lại toàn bộ mới nghiệm
thu được.

**Đừng dán lại toàn văn `git diff` và output dài.** Dán con số và kết luận. Cụ thể, theo thứ
tự:

1. Output + **thời gian đo được** của Task 1.5 mục 1 và mục 3.
2. `git diff --stat` (không cần toàn văn diff cho brief nhỏ này).
3. Kết quả từng tiêu chí Task 1, pass/fail.
4. Số test pass + ruff + cổng cứng VN — ba dòng, không cần dán output đầy đủ.
5. Kết luận Task 2 theo từng tầng điều kiện.
6. Bảng Task 3: tỷ lệ message/bar phiên 10/09 + dải seq.
7. Bằng chứng triển khai Task 4.
8. `git status --short`.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do — hữu ích hơn một báo cáo dài cụt đuôi.

**Không commit, không push.**

---

## 6. Ngoài phạm vi — quyết định của chủ dự án

Không đổi so với đợt 27. Nhắc lại điều quan trọng nhất: phép đo đợt 26 cho thấy **mua-và-giữ
BTC +122,42 USDT (+24,5%) trong khi cả bốn chiến lược đều lỗ 15–21 USDT**, và ở VN cổng cứng
là **−1,6 tỷ so với mua-và-giữ +1.897 tỷ**. Không chiến lược nào có edge đo được.

Q-1 (có go-live hay không) là **quyết định của chủ dự án**. Cùng nhóm: Q-2, Q-3, Q-5, Q-7,
chuyển VPS, scheduled task cho chuông 2C, Docker autostart. Thấy thứ gì chặn việc →
**báo cáo, không tự quyết**.
