# Brief đợt 34 — Triển khai trước phiên, sửa chuông kêu sai, đo kiểm chứng sau phiên

Ngày giao: 11/09/2026, 07:45.
Base: `fb68fda` (main, cây sạch).
Người giao: Claude (planner/auditor).

**Brief này thay thế phần còn lại của brief đợt 29** (Task 1 và Task 4 của đợt đó). Hai task
kia của đợt 29 (gắn chuông vào `sched.sh`, kết luận HII) đã xong và đã commit.

---

## 0. Cổng thời gian — đọc trước tiên, hôm nay có ba mốc

| Mốc | Việc | Vì sao đúng mốc đó |
|---|---|---|
| **trước 08:45** | Task 1 — triển khai bản đã commit | cửa sổ an toàn duy nhất trước khi phiên mở 09:00 |
| trong phiên | Task 2 — sửa chuông 2C kêu sai | chỉ sửa script chạy trên host, **không** dựng lại container |
| **sau 15:05** | Task 3 — đo kiểm chứng | phải đợi phiên đóng mới đủ dải seq |

> **Nếu đã quá 08:45 khi bạn đọc brief này: BỎ QUA Task 1, ghi "CHƯA LÀM — quá cổng giờ".**
> Tuyệt đối không dựng lại container trong phiên. Task 1 sẽ chuyển sang sau 15:05, và ta mất
> dữ liệu `lag_ms` của hôm nay — chấp nhận được, mất một phiên còn hơn mất cả phiên.

---

## Task 1 — Triển khai bản đã commit (**trước 08:45**)

### 1.1. Hiện trạng

```
[deploy-drift] collector: image CŨ hơn commit gần nhất chạm trading/ (7 giờ 48 phút)
[deploy-drift] engine:    image CŨ hơn commit gần nhất chạm trading/ (7 giờ 48 phút)
exit=1
```

Tôi kiểm trực tiếp bên trong container đang chạy:

```
co lag_ms: False
co interval param: False
engine co lag_ms: False
```

Ba thay đổi đã commit nhưng **chưa lên sóng**:

- `a1d8932` — publish NATS trước, ghi DB sau; thêm `lag_ms` cả hai phía.
- `fb68fda` — `persist_bars` đọc khung nến từ `latch.interval`; SQL NAV về tầng `Storage`.

Nếu không triển khai trước phiên, hôm nay **không có số liệu `lag_ms` nào** — mà đó chính là
phép đo brief 31 Task 2 dựng lên và hẹn "đợt sau", tức hôm nay.

### 1.2. Đánh đổi, và vì sao tôi vẫn khuyên triển khai

**Lý lẽ chống:** hôm nay là phiên **đầu tiên** kiểm chứng `BarLatch`. Thêm biến vào một phiên
kiểm chứng là đi ngược kỷ luật tôi vẫn giữ. Nếu Task 3 trượt, ta không biết tại `BarLatch`
hay tại bản mới.

**Lý lẽ ủng hộ, và tôi thấy nó nặng hơn:**

- Thay đổi **không đụng `BarLatch`** — cái quyết định *bao nhiêu* message được phát. Nó chỉ
  đổi **thứ tự** publish so với ghi DB, không đổi **cái gì** được publish. Tiêu chí Task 3
  đếm message và bar duy nhất, nên vẫn hợp lệ.
- Bản này đã qua 654 test, ruff sạch, cổng cứng VN khớp từng chữ số.
- 08:45 là ngoài giờ giao dịch — cửa sổ an toàn thật sự.
- Không triển khai thì `lag_ms` phải đợi tới thứ Hai.

**Một trường hợp duy nhất thứ tự mới có thể đổi số đếm:** nếu ghi DB hỏng. Trước đây DB hỏng
thì không publish; giờ publish rồi mới hỏng → có thêm message. Nhưng nhánh đó phát
`CRITICAL` nên sẽ nhìn thấy ngay. Task 3 phải kiểm log `CRITICAL` để loại trừ khả năng này.

### 1.3. Việc cần làm

```
docker tag ai_auto_trading_system-collector:latest dot34-rollback-collector:pre
docker tag ai_auto_trading_system-engine:latest    dot34-rollback-engine:pre
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

### 1.4. Kiểm chứng — làm đủ, đừng bỏ bước nào

1. `uv run python scripts/deploy_drift_check.py` → **exit 0**.
2. Xác nhận code mới **nằm trong container đang chạy**, không chỉ trong git:
   ```
   docker exec ai_auto_trading_system-collector-1 python -c "import inspect, trading.collector.main as m; s=inspect.getsource(m); print('lag_ms:', 'lag_ms' in s, '| interval:', 'interval: timedelta' in s)"
   docker exec ai_auto_trading_system-engine-1 python -c "import inspect, trading.engine.main as m; print('lag_ms:', 'lag_ms' in inspect.getsource(m))"
   ```
   Cả ba phải `True`. Dán nguyên văn output.
3. `docker compose logs --tail=50 collector` và `engine` → không `CRITICAL`, không traceback.
4. Xác nhận engine warm-up đủ **ba mã** `HPG`, `IJC`, `AAA`. Dán dòng log.
5. Ghi lại `docker ps` và image ID mới.

Giữ `dot20-rollback-*`, `dot25-rollback-*`, `dot29-rollback-*`. **Không xoá tag nào.**

---

## Task 2 — Chuông 2C báo động giả sau mỗi lần backfill

Nguyên văn Task 4 của brief đợt 29, chưa làm. **Làm được trong phiên** vì
`engine_consumer_check.py` chạy trên host qua `sched.sh`, **không nằm trong container** — sửa
nó không cần dựng lại gì.

### 2.1. Bằng chứng

Tối 10/09, sau khi dựng lại collector, chuông kêu:

```
🚨 CHUÔNG 2C (Engine Consumer): engine dừng tiêu thụ bar:
DB tăng 46 bar nhưng stream_seq không đổi (27279 <= 27279)
```

Engine hoàn toàn khoẻ — vừa warm-up xong, `num_pending` bằng 0. Thứ làm DB tăng 46 bar là
**backfill**, không phải stream.

### 2.2. Nguyên nhân

Bảng `bars` có **hai nguồn ghi**, chỉ một đi qua NATS:

| Đường ghi | Ghi DB | Publish NATS |
|---|---|---|
| Stream (`persist_bars`) | có | **có** |
| Backfill (`backfill.py:359` — `storage.write_bars(intraday)`) | có | **không** |

Quy tắc số 2 của chuông giả định *"DB tăng ⇒ stream phải tiến"*. Sai, vì backfill chạy **mỗi
lần collector khởi động** cộng lịch nạp hằng đêm.

### 2.3. Vì sao phải sửa trước khi đăng ký scheduled task

Chuông báo động giả nguy hiểm hơn chuông câm: người ta tắt nó, hoặc quen bỏ qua, rồi bỏ qua
luôn lần kêu thật. Đợt 27 và 28 đã tốn hai vòng để chuông này kêu được — đừng để nó tự huỷ uy
tín ngay tuần đầu.

Tôi đã kiểm lúc 07:35 hôm nay: **scheduled task chưa được đăng ký**, nên chưa có spam. Sửa
trước, đăng ký sau.

### 2.4. Việc cần làm

Bỏ hẳn phép so sánh với số bar trong DB. Câu hỏi đúng là **"consumer có theo kịp stream
không"** — hỏi thẳng JetStream, không mượn DB làm trung gian:

- `js.stream_info("BARS").state.last_seq` — stream đã có tới đâu.
- `consumer_info.delivered.stream_seq` — engine đã nhận tới đâu.
- Kêu khi `last_seq` **tiến lên** giữa hai lần chạy mà `delivered.stream_seq` **không** tiến,
  và khoảng cách `last_seq - delivered.stream_seq` vượt ngưỡng.

Miễn nhiễm hoàn toàn với backfill vì backfill không chạm vào stream. Cả hai đều là lệnh
**đọc** — giữ nguyên ràng buộc không `add`/`update`/`delete`/`purge`.

Giữ nguyên quy tắc số 1 (`num_pending >= ngưỡng`) — vẫn đúng và độc lập.

`read_today_bars_count()` sau khi không còn ai dùng thì **xoá** (dead code do chính thay đổi
này sinh ra). Nếu vẫn muốn giữ số bar trong thông điệp cho dễ đọc thì giữ, nhưng **không được
dùng nó để quyết định có kêu hay không** — ghi rõ bằng một dòng chú thích.

**Chỉ sửa** `scripts/engine_consumer_check.py` và `tests/test_engine_consumer_check.py`.

### 2.5. Kiểm chứng

1. **Tái hiện lỗi trước khi sửa:** test bơm `last_seq` không đổi + `bars_today` tăng →
   **không** kêu. Viết test này trước, thấy nó **đỏ**, rồi mới sửa. Nếu nó xanh ngay từ đầu
   thì test sai, không phải code đúng.
2. Test: `last_seq` tiến, `delivered.stream_seq` đứng im, khoảng cách vượt ngưỡng → **kêu**.
3. Test: cả hai cùng tiến → **không kêu**.
4. Chạy thật ngay sau một lần backfill → **không kêu**. Dán output + exit code.
5. Test cũ vẫn pass. **Không `assert` nào bị sửa** — phần dựng mock được phép đổi (bài học
   đợt 33).
6. Suite đầy đủ pass (mốc hiện tại **654**), ruff sạch.

---

## Task 3 — Đo kiểm chứng (**sau 15:05**)

Đây là phép đo quyết định: `BarLatch` có thật sự hoạt động trên dữ liệu sống hay không.

Dùng `scripts/replay_stream_check.py` đã có. **Không viết lại script.**

### 3.1. Bốn tiêu chí, phải đạt CẢ BỐN

**A — tỷ lệ message/bar về ≈ 1,0.** Đọc dải seq của phiên 11/09, tính
`tổng message / số (symbol, ts) duy nhất`. Đạt khi **≤ 1,10**. Ghi rõ dải seq.

Mốc "trước khi sửa" để so sánh: **09/09 = 7,17×** và **10/09 = 8,36×**.

**B — số bar KHÔNG được giảm.** Tiêu chí chống hồi quy, và là tiêu chí tôi quan tâm nhất.

> Một bản sửa hỏng cũng cho tỷ lệ đẹp: nếu `flush_due` không chạy hoặc `BarLatch` nuốt bar
> thì số message giảm mạnh và tỷ lệ vẫn về 1,0 — nhưng ta **mất dữ liệu**. **Tỷ lệ 1,0 một
> mình không chứng minh được gì.**

Danh mục đã đổi `HII → HPG` từ 18:15 ngày 10/09. HII trước đây **thiếu bar** ở những phút
không giao dịch nên hai mốc 120 và 131 bị nó kéo xuống; HPG thanh khoản gấp bội nên số bar
dự kiến **tăng**, tiệm cận trần lý thuyết ~46 khung × 3 mã ≈ 138.

→ Đạt khi số bar duy nhất **≥ 131** và không vượt trần lý thuyết. **Giảm** so với 131 là dấu
hiệu mất bar — dừng, báo cáo ngay, **không tự sửa, không tự lùi**.

Đối chiếu chéo với DB, ghim múi giờ:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT symbol, count(*) FROM bars
WHERE ts >= DATE '2026-09-11' AND ts < DATE '2026-09-12'
GROUP BY symbol ORDER BY symbol;
```

Số bar trong DB và số `(symbol, ts)` duy nhất trong stream phải **khớp nhau**.

**C — khung cuối phiên phải có mặt.** Đây là chỗ `flush_due` được kiểm chứng trong môi trường
thật, không phải trong test.

Khung 14:45 **không bao giờ có snapshot kế tiếp** để kích hoạt chốt — nó chỉ được phát nhờ
`flush_due`. Kiểm tra: trong dải seq phiên 11/09 có message cho `ts = 2026-09-11 14:45:00+07`
của **cả ba mã** không? Thiếu nghĩa là `flush_due` **không chạy trong production** dù test
xanh. Báo cáo ngay.

**D — log không có cảnh báo bất thường dồn dập.** Đếm số thật, đừng ghi "không có gì bất
thường":

```
docker compose logs --since 2026-09-11T09:00:00 collector | grep -c "already closed frame"
docker compose logs --since 2026-09-11T09:00:00 engine    | grep -c "non-advancing bar"
docker compose logs --since 2026-09-11T09:00:00 collector | grep -c "CRITICAL"
```

Vài cái lẻ tẻ là bình thường. Hàng chục là dấu hiệu `BarLatch` hoặc rào chắn engine đang đánh
nhầm. Dòng thứ ba loại trừ khả năng thứ tự publish mới làm sai số đếm (xem §1.2).

### 3.2. Bảng `lag_ms` đầu tiên — chỉ làm được nếu Task 1 đã chạy

Trích từ log, lập bảng trung vị / p95 / max cho cả hai phía:

```
docker compose logs --since 2026-09-11T09:00:00 collector | grep "bars closed"
docker compose logs --since 2026-09-11T09:00:00 engine    | grep "bar processed"
```

Đây là lần đầu ta biết **thật sự** một bar mất bao lâu từ lúc khung đóng tới lúc engine xử lý
xong. Nếu Task 1 không chạy (quá cổng giờ), ghi "CHƯA LÀM" và bỏ mục này.

### 3.3. Nếu A đạt nhưng B hoặc C trượt

**Dừng. Báo cáo. Không tự sửa, không tự lùi.** Đó là tình huống bản sửa đổi một lỗi lấy một
lỗi tệ hơn — mất bar nguy hiểm hơn bar lặp, vì bar lặp đã có rào chắn engine chặn, còn bar
mất thì không ai biết.

Đường lùi có sẵn: `dot34-rollback-collector:pre` / `dot34-rollback-engine:pre`. Quyết định
lùi là của tôi, không phải của agent.

---

## 4. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 3 chỉ `SELECT`.
- **Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.** Task 3 chỉ dùng
  `js.get_msg()` và `js.stream_info()`; Task 2 chỉ dùng `js.stream_info()` và
  `js.consumer_info()`.
- **Không dựng lại container ngoài Task 1**, và Task 1 chỉ được chạy trước 08:45.
- **Không sửa** `BarLatch`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/logic.py`, `scripts/heartbeat_check.py`.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` và mọi số đo **copy từ terminal**, không gõ lại.
- **Không bịa tiêu chí.** Đợt 29 từng trả về một bảng tiêu chí hoàn toàn khác brief, mô tả
  bar 1 phút và phiên 09:15–14:45 — hệ thống này dùng bar 5 phút, phiên 09:00–15:00. Thấy
  brief thiếu hoặc sai thì **hỏi lại**.

**GitNexus:** `npx gitnexus analyze` trước và sau. MCP `gitnexus` hiện **không kết nối được**
(timeout) — ghi rõ điều đó trong báo cáo thay vì im lặng bỏ qua.

---

## 5. Báo cáo

Ngắn, đủ, đúng thứ tự. **Đừng dán toàn văn `git diff`** — dán `--stat` và con số.

1. Task 1: exit code drift, output ba lệnh `docker exec` kiểm code trong container, image ID
   mới. Nếu quá cổng giờ: **"CHƯA LÀM — quá 08:45"**.
2. Task 2: kết quả sáu tiêu chí, nói rõ **bài test tái hiện đã đỏ trước khi sửa**.
3. Task 3: bảng bốn tiêu chí A/B/C/D với con số thật, dải seq, bảng đối chiếu stream vs DB.
4. Bảng `lag_ms` (hoặc "CHƯA LÀM" nếu Task 1 không chạy).
5. Ba dòng: số test pass, ruff, cổng cứng VN.
6. `git status --short`.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

**Không commit, không push.**

---

## 6. Ngoài phạm vi — quyết định của chủ dự án

- **Q-1:** không chiến lược nào có edge đo được. VN: `-1.615.319.902` so với mua-và-giữ
  `+1.897.587.481.903`. Crypto 1h/30x: cả bốn chiến lược lỗ 15–21 USDT vs mua-và-giữ BTC
  `+122,42`.
- **Q-2:** `0434221` NAV 5.021.712 (đang cấu hình) vs `0434226` NAV 197.517.988 + 5 vị thế
  thật. Hệ thống giờ tự cảnh báo `ratio=39.33`.
- **Q-3:** cửa xác nhận 15 phút, 9/9 lệnh đã hết hạn, `real_order_fills` rỗng. Có tự động hoá
  không, hay trực phiên?
- **Đăng ký scheduled task cho chuông 2C** — chỉ sau khi Task 2 xong.
- Chuyển VPS, Docker autostart, `risk_pct` cho 30x.

Thấy thứ gì trong nhóm này chặn việc → **báo cáo, không tự quyết**.
