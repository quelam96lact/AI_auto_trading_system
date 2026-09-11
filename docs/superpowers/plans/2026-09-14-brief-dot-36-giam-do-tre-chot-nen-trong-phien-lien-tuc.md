# Brief đợt 36 — Giảm độ trễ chốt nến trong phiên khớp lệnh liên tục

Ngày giao: 11/09/2026, 20:10.
Base: `d306928` (main, cây sạch).
Người giao: Claude (planner/auditor).

---

## 0. Đo trước, và lần này CÓ một đòn bẩy thật

Brief đợt 31 tôi đo và kết luận: độ trễ trong code chỉ ~3,5 ms, không đáng tối ưu so với
khung nến 300.000 ms. **Kết luận đó vẫn đúng** — và vẫn không phải chỗ cần động vào.

Nhưng đợt 34 đã cắm `lag_ms` vào sản xuất, và phiên 11/09 cho ta **số liệu thật đầu tiên**.
Nó lộ ra một khoảng trễ hoàn toàn khác, lớn hơn bốn bậc độ lớn, và **sửa được**.

### 0.1. Số đo thật, 97 bar của phiên 11/09

`lag_ms` = khoảng từ lúc **khung nến đóng** (`ts + 5 phút`) tới lúc bar được publish ra NATS:

```
min      :    2.354 ms
p25      :    5.417 ms
trung vi :   14.318 ms
p75      :   35.369 ms
p90      :   59.384 ms
p95      :   68.822 ms
max      :   88.570 ms
```

| Dải | Số bar |
|---|---:|
| < 5 giây | 1 |
| 5–30 giây | 71 |
| 30–70 giây | 21 |
| 70–100 giây | 4 |

**Trung vị 14,3 giây. p95 gần 69 giây.** Đây không phải thời gian xử lý — CPU chỉ tốn ~3,5 ms.
Đây là thời gian **ngồi chờ**.

### 0.2. Vì sao phải chờ — hệ quả trực tiếp của `BarLatch`

`BarLatch.offer()` chốt khung A **chỉ khi một snapshot của khung B tới**. Nghĩa là độ trễ
bằng đúng **thời gian từ mốc đóng khung tới lệnh khớp đầu tiên của khung kế tiếp**. Mã càng
ít giao dịch thì chờ càng lâu.

Đường thứ hai là `flush_due`, chốt tại `ts + interval + grace`, với `grace = 60 giây` và
`housekeeping_tick` chạy mỗi **30 giây**. Nên khung nào không có giao dịch kế tiếp phải đợi
tới **60–90 giây**. Bốn bar ở dải 70–100 giây gần như chắc chắn là nhóm này.

Đây là cái giá của bản sửa đợt 26, và **cái giá đó đúng** — thà chậm mà đúng còn hơn nhanh mà
chạy chiến lược trên nến chưa đóng 7 lần. Nhưng cái giá hiện đang **cao hơn mức cần thiết**.

### 0.3. Đòn bẩy: khung đã đóng theo đồng hồ thì không cần chờ giao dịch

Khi `now >= ts + interval`, khung đó **đã đóng về mặt thời gian**. Ta không cần đợi một giao
dịch của khung sau mới biết điều đó. `grace` tồn tại chỉ để hứng **snapshot đến muộn** — tức
snapshot của khung A mà SSI gửi sau khi khung A đã hết.

Nên câu hỏi quyết định là: **SSI gửi snapshot muộn nhất bao lâu sau mốc đóng khung?**

- Nếu thường dưới 2–3 giây → `grace` 60 giây là thừa gấp hai mươi lần, và ta đang tự trả
  thêm hàng chục giây độ trễ cho mọi cây nến.
- Nếu có thể muộn 30 giây → `grace` phải giữ lớn, và đòn bẩy này nhỏ hơn nhiều.

**Ta chưa có số liệu đó.** Sau khi `BarLatch` lên sóng, NATS chỉ còn một message mỗi khung —
lịch sử snapshot không còn nhìn thấy được từ stream nữa.

> **Vì vậy brief này KHÔNG chỉnh `grace`.** Chỉnh mù là đúng loại sai lầm vừa mất hai đợt để
> sửa. Task 2 đo, đợt sau mới chỉnh.

---

## 1. Ba việc

| Task | Việc | Khi nào |
|---|---|---|
| 1 | Triển khai bản đã commit (chuông phát hiện máy ngủ) | **ngay, ngoài giờ** |
| 2 | Đo độ muộn của snapshot — chỉ đo, không chỉnh | ngay (mã), chạy thứ Hai |
| 3 | Đo lại tiêu chí B và C | **sau 15:05 thứ Hai 14/09** |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 3 chỉ `SELECT`.
- Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.
- **KHÔNG đổi `grace_seconds`, KHÔNG đổi nhịp `housekeeping_tick`, KHÔNG đổi logic
  `BarLatch`** trong đợt này. Task 2 chỉ quan sát.
- **Không quay lại publish snapshot chưa đóng** dưới bất kỳ danh nghĩa "giảm độ trễ" nào.
- **Không sửa** `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/logic.py`, `scripts/heartbeat_check.py`.
- **Không dựng lại container ngoài Task 1**, và Task 1 phải chạy ngoài giờ giao dịch.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` và mọi số đo **copy từ terminal**.
- **Cổng cứng VN là phép backtest**, không phải bộ test:
  `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt`
  → đối chiếu `-1.615.319.902 | BH 1.897.587.481.903 | 1.514 lệnh | 439 mã`.

**GitNexus:** MCP đang timeout — chạy `npx gitnexus analyze` qua terminal và **ghi rõ MCP
timeout** trong báo cáo.

---

## Task 1 — Triển khai bản đã commit (**ngay, ngoài giờ giao dịch**)

Chuông phát hiện máy ngủ (đợt 35) đã commit nhưng **chưa chạy** — nó nằm trong
`trading/collector/main.py`, mà code được nung vào image. Nếu không dựng lại, thứ Hai máy ngủ
lần nữa ta vẫn không biết.

```
docker tag ai_auto_trading_system-collector:latest dot36-rollback-collector:pre
docker tag ai_auto_trading_system-engine:latest    dot36-rollback-engine:pre
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

### Kiểm chứng

1. `uv run python scripts/deploy_drift_check.py` → **exit 0**.
2. Xác nhận code mới **nằm trong container đang chạy**:
   ```
   docker exec ai_auto_trading_system-collector-1 python -c "import inspect, trading.collector.main as m; print('drift detector:', 'CLOCK_DRIFT_THRESHOLD_SECONDS' in inspect.getsource(m))"
   ```
   Phải `True`. Dán nguyên văn.
3. `docker compose logs --tail=50 collector` và `engine` → không `CRITICAL`, không traceback.
4. Engine warm-up đủ ba mã `HPG`, `IJC`, `AAA`. Dán dòng log.
5. Ghi lại `docker ps` và image ID mới. Giữ mọi tag rollback cũ, **không xoá**.

---

## Task 2 — Đo độ muộn của snapshot (**chỉ đo, không chỉnh**)

### 2.1. Câu hỏi cần trả lời bằng số

Với mỗi snapshot SSI gửi tới, đo `arrival_lateness = now − (bar.ts + interval)`:

- Giá trị **âm** → snapshot tới khi khung còn đang mở. Đây là đa số, bình thường.
- Giá trị **dương** → snapshot của một khung **đã hết giờ**. Đây chính là thứ `grace` sinh ra
  để hứng, và là con số ta cần.

Cần: phân bố của phần **dương** — trung vị, p95, max, và **bao nhiêu phần trăm** snapshot rơi
vào đó.

### 2.2. Việc cần làm

Trong `on_stream_message` (`trading/collector/main.py`), sau khi `parse_interval_message` trả
về bar hợp lệ: nếu `arrival_lateness > 0`, ghi `alert("INFO", "late snapshot", ...)` kèm
`symbol`, `bar_ts`, và `late_ms`.

- Dùng `datetime.now(TZ)` và `latch.interval` đã có — **không thêm đồng hồ mới, không thêm
  thư viện, không thêm bảng DB**.
- Mức `INFO` nên **không bắn Telegram** (`_NOTIFY_LEVELS` chỉ gồm `WARN`/`CRITICAL`) — đã
  kiểm, không sinh spam.
- **Chỉ ghi khi dương.** Snapshot đến khi khung còn mở là chuyện bình thường, ghi hết sẽ làm
  ngập log (~7 snapshot mỗi nến mỗi mã).

**Chỉ sửa** `trading/collector/main.py` và `tests/test_collector_main.py`.

**KHÔNG đổi hành vi chốt nến.** `BarLatch` giữ nguyên, `grace` giữ nguyên 60 giây,
`housekeeping_tick` giữ nguyên nhịp 30 giây. Đây thuần tuý là quan sát.

### 2.3. Kiểm chứng

1. Test: snapshot tới khi khung **còn mở** (`late_ms < 0`) → **không** ghi log.
2. Test: snapshot tới **sau** mốc đóng khung → **có** log `late snapshot` với `late_ms` đúng
   giá trị đồng hồ tiêm vào.
3. Test: hành vi chốt nến **không đổi** — bơm lại đúng kịch bản 3 snapshot khung A + 1
   snapshot khung B, `pub.publish` vẫn gọi **đúng 1 lần** với giá trị của snapshot thứ 3.
   Đây là tiêu chí quan trọng nhất của task: quan sát không được làm đổi hành vi.
4. Suite đầy đủ pass (mốc hiện tại **661**), ruff sạch, cổng cứng VN khớp từng chữ số.

### 2.4. Sau khi triển khai — thu số liệu thứ Hai

Task này **không** yêu cầu triển khai lại. Nếu Task 1 đã dựng image mới thì gộp luôn Task 2
vào cùng lần dựng đó (cùng ngoài giờ, cùng một lần build). Nếu Task 2 làm xong sau khi Task 1
đã dựng: **để tới ngoài giờ thứ Hai mới dựng lại**, đừng dựng giữa phiên.

Ghi rõ trong báo cáo: Task 2 đã kịp vào image nào.

---

## Task 3 — Đo lại tiêu chí B và C (**sau 15:05 thứ Hai 14/09**)

Nguyên văn Task 2 của brief đợt 35. Tiêu chí A đã đạt dứt điểm (1,00×), **không đo lại**.

Dùng `scripts/replay_stream_check.py` đã có. **Không viết lại.**

**Điều kiện tiên quyết — làm trước, đừng bỏ qua:** xác nhận phiên **không có khoảng chết**.

```
docker compose logs --since 2026-09-14T02:00:00Z --until 2026-09-14T08:10:00Z collector | Measure-Object
```

Cộng với: có dòng `phát hiện máy chủ ngủ/gián đoạn` nào không (chuông Task 1). Nếu có khoảng
chết → **dừng, báo cáo, đừng kết luận B/C trượt**. Bài học 11/09: đừng quy lỗi cho code khi
nguyên nhân nằm ở hạ tầng.

**B — số bar.** Đếm `(symbol, ts)` duy nhất trong dải seq phiên 14/09.
→ Đạt khi **≥ 131** và không vượt trần lý thuyết (~46 khung × 3 mã ≈ 138).

Đối chiếu chéo với DB, ghim múi giờ:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT symbol, count(*) FROM bars
WHERE ts >= DATE '2026-09-14' AND ts < DATE '2026-09-15'
GROUP BY symbol ORDER BY symbol;
```

Số trong stream và số trong DB phải **khớp**.

**C — khung 14:45 có mặt cho cả ba mã** trong stream.

### 3.1. Kèm hai bảng số

1. **`lag_ms` phiên 14/09** — trung vị / p25 / p75 / p90 / p95 / max, cả collector và engine.
   So với phiên 11/09 (trung vị 14.318 ms, p95 68.822 ms, max 88.570 ms).
2. **`late snapshot` phiên 14/09** (nếu Task 2 đã kịp vào image) — trung vị / p95 / max của
   `late_ms`, và **tỷ lệ phần trăm** snapshot đến muộn trên tổng số snapshot.

Bảng thứ hai là đầu vào để đợt sau quyết `grace` nên bằng bao nhiêu. **Đừng tự chỉnh trong
đợt này** — chỉ đưa số và nêu khuyến nghị.

---

## 4. Báo cáo

Ngắn, đủ, đúng thứ tự. Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

1. `git diff --stat`.
2. Task 1: exit code drift, output lệnh `docker exec`, image ID mới.
3. Task 2: kết quả bốn tiêu chí; nói rõ Task 2 đã vào image nào.
4. Task 3 (thứ Hai): bằng chứng phiên không có khoảng chết → bảng B và C → hai bảng số ở §3.1.
5. Ba dòng: số test pass, ruff, **cổng cứng VN bằng bốn con số**.
6. `git status --short`.

**Không commit, không push.**

---

## 5. Điều cần nói thẳng về "giảm thời gian xử lý"

Để không ai kỳ vọng nhầm, đây là toàn cảnh độ trễ, đo thật:

| Nguồn | Độ lớn | Sửa được không |
|---|---:|---|
| Cửa xác nhận lệnh thật thủ công | **900.000 ms** | quyết định của chủ dự án |
| Khung nến 5 phút | **300.000 ms** | quyết định của chủ dự án |
| **Chờ chốt nến (trung vị)** | **14.318 ms** | **có — sau khi Task 2 đo xong** |
| Chờ chốt nến (p95) | 68.822 ms | có, cùng chỗ |
| Ghi DB chặn publish | 3,3 ms | đã sửa ở đợt 31 |
| Publish NATS | 0,2 ms | không đáng động |

Thời gian **xử lý** của code đã ở mức vài mili giây và không còn gì để vắt. Thứ còn lại đáng
kể là **thời gian chờ chốt nến** — 14 giây trung vị, gần 69 giây ở p95. Đó mới là mục tiêu
thật, và Task 2 là bước đo bắt buộc trước khi chạm vào nó.

Hai dòng đầu bảng vẫn lớn hơn mọi thứ khác **bốn bậc độ lớn**. Nếu mục tiêu là giao dịch
nhanh hơn thật sự, cuộc bàn đúng vẫn là về hai dòng đó.

## 6. Ngoài phạm vi — quyết định của chủ dự án

- **Máy ngủ giữa phiên (điểm chặn go-live mới).** `powercfg /change standby-timeout-dc 0` là
  vá tạm một lệnh; chuyển VPS là sửa tận gốc. Sự cố 11/09 mất 88 phút phiên.
- **Đăng ký scheduled task cho chuông 2C** — làm được rồi, lỗi báo động giả đã sửa ở đợt 34.
- **Q-1:** không chiến lược nào có edge đo được.
- **Q-2:** `0434221` NAV 5.021.712 vs `0434226` NAV 197.517.988; hệ thống nay tự cảnh báo
  `ratio=39.33`.
- **Q-3:** cửa xác nhận 15 phút, 9/9 lệnh đã hết hạn, `real_order_fills` rỗng.
- Q-5 ngày lễ (mốc tiếp theo 01/01/2027), Q-7 `risk_pct` cho 30x.

Thấy thứ gì trong nhóm này chặn việc → **báo cáo, không tự quyết**.
