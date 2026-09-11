# Brief đợt 35 — Máy chủ ngủ giữa phiên, dựng chuông bắt việc đó, và đo lại

Ngày giao: 11/09/2026, 19:20.
Base: `7194138` (main, cây sạch).
Người giao: Claude (planner/auditor).

---

## 0. Phiên 11/09 mất 88 phút, và nguyên nhân KHÔNG phải lỗi code

Báo cáo đợt 34 ghi tiêu chí B và C **trượt**, và quy cho "sự cố DNS/kết nối mạng". Tôi đào
tiếp và tìm ra nguyên nhân thật. Nó nghiêm trọng hơn nhiều.

### 0.1. Bằng chứng

Trong khoảng **13:32:30 → 15:00** giờ VN:

```
Tong so dong log collector : 0
Tong so dong log engine    : 0
```

**Không một dòng nào.** Watchdog lẽ ra phải ghi `feed stale, forcing reconnect` mỗi 180 giây
— nó ghi con số không. Một sự cố DNS đơn thuần không thể làm cả hai tiến trình câm lặng như
thế.

Nhật ký nguồn của Windows cho câu trả lời:

```
13:28:04  Power source change.
13:32:07  The system is entering Modern Standby
13:32:23  Connectivity state in standby: Disconnected, Reason: Adaptive Connected Standby
13:46:49  The system is exiting Modern Standby
13:47:00  Connectivity state in standby: Disconnected, Reason: Policy Setting
```

Và cấu hình nguồn hiện tại:

```
Current AC Power Setting Index: 0x00000000   (cam nguon: khong bao gio ngu)
Current DC Power Setting Index: 0x000000b4   (dung pin: ngu sau 180 giay)
```

### 0.2. Chuỗi nhân quả, khép kín

1. **13:28:04** — máy chuyển sang dùng pin (rút điện, hoặc điện lưới chập).
2. **13:32:07** — đúng 180 giây sau, Windows đưa máy vào Modern Standby theo đúng cấu hình.
3. **13:32:21** — mạng ngắt. `SSIFeed connection error: Name or service not known` là **tiếng
   thở cuối** của tiến trình trước khi đóng băng, không phải nguyên nhân.
4. **13:32 → 15:00** — toàn bộ hệ thống đóng băng. Không thu bar, không chạy chiến lược,
   không cảnh báo.

### 0.3. Điều này nói gì

**Giám sát không bắt được, vì giám sát cũng đang ngủ.** Chuông 2A, chuông 2C, watchdog,
dead-man switch — tất cả đều chạy trên chính cái máy vừa thiếp đi. Không một cái nào kêu.
Ta chỉ biết vì tôi ngồi đọc log ngược.

Đây là **điểm mù lớn nhất của hệ thống hiện tại**, và nó không nằm trong code.

Phần đáng mừng: **EOD backfill đã bù đủ**. DB có đúng 46 bar/mã tới 14:45 cho cả ba mã. Không
mất dữ liệu, chỉ mất khả năng giao dịch thời gian thực trong 88 phút.

### 0.4. Vậy `BarLatch` thì sao — nó ĐẠT

Đừng để sự cố này che mất kết quả chính. Tôi chạy lại độc lập trên dải seq 27.280 → 27.381:

```
doc duoc      : 102 / 102 message
so bar duy nhat: 102
trung binh message / bar : 1.00
phat 1 lan : 102 bar
```

**Mỗi bar phát đúng một lần**, so với 7,17× (09/09) và 8,36× (10/09). Lỗi nến chưa đóng đã
tắt hẳn.

Và tiêu chí C — mà đợt 34 ghi là trượt — **thực ra đạt**. Ba message cuối cùng:

```
seq 27379 : HPG @ 2026-09-11T13:30:00+07:00
seq 27380 : IJC @ 2026-09-11T13:30:00+07:00
seq 27381 : AAA @ 2026-09-11T13:30:00+07:00
```

Khung 13:30 đang mở khi máy ngủ, **không bao giờ có snapshot kế tiếp**. Cơ chế duy nhất phát
được nó là `flush_due` — tức `flush_due` **đã chạy trong production**, đúng điều C sinh ra để
kiểm, chỉ ở 13:30 thay vì 14:45 và trong điều kiện khắc nghiệt hơn.

Tiêu chí B (số bar ≥ 131) trượt thuần tuý vì mất 88 phút phiên, không phải vì `BarLatch` nuốt
bar.

---

## 1. Ba việc

| Task | Việc | Khi nào |
|---|---|---|
| 1 | Chuông phát hiện máy vừa ngủ dậy | ngay |
| 2 | Đo lại tiêu chí B và C trên một phiên trọn vẹn | **sau 15:05 thứ Hai 14/09** |
| 3 | Dọn ba nhánh chết (lần thứ ba lặp mẫu này) | ngay |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. Không gọi SSI, không gọi BingX.
- `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 2 chỉ `SELECT`.
- Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.
- **Không sửa cấu hình nguồn của Windows.** Xem §6 — đó là quyết định của chủ dự án.
- **Không sửa** `BarLatch`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/logic.py`, `scripts/heartbeat_check.py`.
- Không xoá file. **Không commit, không push.**
- Mọi `git diff` và mọi số đo **copy từ terminal**.

**GitNexus:** MCP hiện **không kết nối được** (timeout). Chạy `npx gitnexus analyze` qua
terminal và ghi rõ MCP timeout trong báo cáo.

---

## Task 1 — Chuông phát hiện máy vừa ngủ dậy

### 1.1. Ý tưởng, và giới hạn thật thà của nó

Khi máy ngủ, **không cảnh báo nào phát được** — cả hệ thống đóng băng. Ta **không thể** báo
lúc đang ngủ. Nhưng ta **có thể** báo ngay khi tỉnh: *"vừa có một khoảng chết N phút trong
giờ giao dịch"*.

Nói rõ giới hạn này trong docstring: đây là **phát hiện sau sự việc**, không phải phòng ngừa.
Phòng ngừa nằm ở §6 và là việc của chủ dự án. Đừng để ai đọc code rồi tưởng đã an toàn.

### 1.2. Cách phát hiện

Đồng hồ **đơn điệu** (`time.monotonic()`) và đồng hồ **tường** (`datetime.now(TZ)`) trôi cùng
nhịp khi tiến trình chạy bình thường. Khi máy ngủ, đồng hồ tường **nhảy vọt** còn đồng hồ đơn
điệu thì không (trên Windows/Linux, `monotonic` không tính thời gian ngủ).

Trong `housekeeping_tick` (`trading/collector/main.py`) — vòng đã chạy mỗi 30 giây sẵn, **không
thêm vòng lặp mới, không thêm thư viện**:

- Nhớ cặp `(monotonic, wall)` của lần tick trước.
- Mỗi tick, tính `drift = Δwall − Δmonotonic`.
- `drift` vượt ngưỡng → phát `alert("CRITICAL", ...)` nêu rõ: khoảng chết bao nhiêu giây, từ
  mốc nào tới mốc nào, và **có nằm trong giờ giao dịch hay không** (dùng `is_trading_time`
  sẵn có).

Ngưỡng: **120 giây**, đặt thành hằng số có tên kèm một dòng chú thích giải thích con số, theo
đúng kiểu `POSITION_MAX_AGE_MINUTES` và `BUYING_POWER_MAX_AGE_MINUTES` đang có.

Vì sao 120: nhịp tick là 30 giây, nên drift bình thường dưới một giây. 120 giây đủ xa để
không báo nhầm khi máy bận, đủ gần để bắt mọi lần ngủ thật (lần này là 88 phút).

**Chỉ sửa** `trading/collector/main.py` và `tests/test_collector_main.py`.

### 1.3. Kiểm chứng

1. Test: hai tick liên tiếp bình thường (drift ~0) → **không** cảnh báo.
2. Test: tiêm đồng hồ sao cho `Δwall = 5400s` còn `Δmonotonic = 30s`, thời điểm nằm **trong**
   giờ giao dịch → **có** CRITICAL, nội dung chứa số giây chết và ghi rõ "trong giờ giao dịch".
3. Test: cùng drift đó nhưng **ngoài** giờ giao dịch → vẫn cảnh báo nhưng ghi rõ "ngoài giờ
   giao dịch" (máy ngủ ban đêm là bình thường, không được im nhưng cũng không được báo như
   nhau).
4. Test: tick **đầu tiên** (chưa có mốc trước) → không cảnh báo, không nổ.
5. Suite đầy đủ pass (mốc hiện tại **657**), ruff sạch, cổng cứng VN khớp từng chữ số.

> **Cổng cứng VN là phép backtest**, không phải một bộ test. Chạy:
> `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt`
> và đối chiếu bốn con số `-1.615.319.902 | BH 1.897.587.481.903 | 1.514 lệnh | 439 mã`.
> Báo cáo đợt 34 ghi "cổng cứng 15/15 passed" — đó là một bộ test khác, không phải cổng cứng.

---

## Task 2 — Đo lại tiêu chí B và C (**sau 15:05 thứ Hai 14/09**)

Tiêu chí A đã đạt dứt điểm (1,00×), **không cần đo lại**. Chỉ đo lại B và C trên một phiên
không bị gián đoạn.

Dùng `scripts/replay_stream_check.py` đã có. **Không viết lại.**

**B — số bar.** Đếm `(symbol, ts)` duy nhất trong dải seq của phiên 14/09.
→ Đạt khi **≥ 131** và không vượt trần lý thuyết (~46 khung × 3 mã ≈ 138).
Đối chiếu chéo với DB, ghim múi giờ:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT symbol, count(*) FROM bars
WHERE ts >= DATE '2026-09-14' AND ts < DATE '2026-09-15'
GROUP BY symbol ORDER BY symbol;
```

Số trong stream và số trong DB phải **khớp**. Lệch nghĩa là có bar vào DB mà không qua NATS —
báo cáo ngay.

**C — khung 14:45 phải có mặt cho cả ba mã** trong stream.

**Điều kiện tiên quyết:** trước khi đo, xác nhận **không có khoảng chết nào** trong phiên —
dùng chính chuông của Task 1, cộng đếm số dòng log:

```
docker compose logs --since 2026-09-14T02:00:00Z --until 2026-09-14T08:10:00Z collector | Measure-Object
```

Nếu có khoảng chết: **dừng, báo cáo, đừng kết luận B/C trượt**. Bài học hôm nay là đừng quy
lỗi cho code khi nguyên nhân nằm ở hạ tầng.

Kèm bảng `lag_ms` của phiên 14/09 (trung vị / p95 / max, cả hai phía), để so với phiên 11/09:
collector trung vị 14,4 giây và engine 15,8 giây — nhưng số đó lấy trên phiên đứt đoạn nên
chỉ là tham khảo.

---

## Task 3 — Dọn ba nhánh chết

Mẫu này đã xuất hiện **ba đợt liên tiếp** (32, 33, 34). Dọn nốt lần cuối.

`scripts/engine_consumer_check.py`:

```python
# dòng 58
stream_last_seq = s_info.state.last_seq if hasattr(s_info, "state") else getattr(s_info, "last_seq", 0)

# dòng 144-148
if isinstance(info_res, tuple):
    info, stream_last_seq = info_res
else:
    info = info_res
    stream_last_seq = getattr(info, "stream_last_seq", 0)
```

Cả hai là nhánh chết: `read_nats_consumer_info` **luôn** trả tuple (dòng 59 `return info,
stream_last_seq`), và `js.stream_info()` **luôn** trả object có `.state`. Lần này thậm chí
không phải để chiều mock — tôi đã kiểm, cả bảy chỗ mock trong test đều trả tuple.

Rút gọn còn phép gán thẳng. **Không đổi hành vi.**

**Kiểm chứng:** tám test của `test_engine_consumer_check.py` vẫn pass, **không `assert` nào bị
sửa**; suite đầy đủ pass; ruff sạch.

---

## 3. Báo cáo

Ngắn, đủ, đúng thứ tự. Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

1. `git diff --stat`.
2. Task 1: kết quả năm tiêu chí, pass/fail từng mục.
3. Task 3: kết quả kiểm chứng.
4. Task 2 (thứ Hai): bảng B và C với số thật, dải seq, bảng đối chiếu stream vs DB, **kèm
   bằng chứng phiên không có khoảng chết**. Bảng `lag_ms`.
5. Ba dòng: số test pass, ruff, **cổng cứng VN bằng bốn con số** (không phải "15/15 passed").
6. `git status --short`.

**Không commit, không push.**

---

## 4. Điều chỉ chủ dự án quyết được — và một việc nên làm ngay hôm nay

### 4.1. Máy ngủ giữa phiên (mới, và là điểm chặn go-live)

Hệ thống giao dịch đang chạy trên một laptop có Modern Standby. Hôm nay nó ngủ **giữa phiên**
và không ai biết cho tới khi tôi đọc log ngược.

Nguyên nhân trực tiếp: máy chuyển sang dùng pin lúc 13:28, và cấu hình `DC = 180 giây` cho
ngủ sau 3 phút. Trên nguồn AC thì `= 0` (không bao giờ ngủ) — nên chỉ cần **rút điện một lần**
là mất phiên.

Hai hướng, tôi **không tự làm** vì cả hai đụng cấu hình máy:

- **Vá tạm, một lệnh, làm được ngay:** `powercfg /change standby-timeout-dc 0`
  — không ngủ kể cả khi dùng pin. Rẻ, nhưng laptop vẫn có thể tắt vì hết pin, và vẫn phải mở
  nắp máy suốt phiên.
- **Sửa tận gốc:** chuyển sang VPS. Việc này đã nằm trong danh sách treo nhiều đợt; sự cố hôm
  nay biến nó từ "nên làm" thành **"phải làm trước khi go-live"**. Một hệ thống giao dịch tiền
  thật không thể chạy trên máy có thể ngủ, hết pin, hoặc bị đóng nắp.

### 4.2. Không đổi so với các đợt trước

- **Q-1:** không chiến lược nào có edge đo được. VN `-1.615.319.902` so với mua-và-giữ
  `+1.897.587.481.903`; crypto 1h/30x cả bốn chiến lược lỗ 15–21 USDT so với mua-và-giữ BTC
  `+122,42`.
- **Q-2:** `0434221` NAV 5.021.712 (đang cấu hình) vs `0434226` NAV 197.517.988 + 5 vị thế
  thật. Hệ thống nay tự cảnh báo `ratio=39.33`.
- **Q-3:** cửa xác nhận 15 phút, 9/9 lệnh đã hết hạn, `real_order_fills` rỗng. Tự động hoá
  hay trực phiên? Cộng thêm số liệu mới: `lag_ms` trung vị 14–16 giây, p95 tới 86 giây —
  tín hiệu đến chậm hơn khung nến khá nhiều trước cả khi tính cửa 15 phút.
- **Đăng ký scheduled task cho chuông 2C:** giờ **làm được rồi** — lỗi báo động giả đã sửa và
  đã kiểm chứng ở đợt 34. Lệnh đã soạn sẵn trong báo cáo đợt 29.
- Q-5 ngày lễ (mốc tiếp theo 01/01/2027), Q-7 `risk_pct` cho 30x.

Thấy thứ gì trong nhóm này chặn việc → **báo cáo, không tự quyết**.
