# Brief đợt 52 — Bốn cái chặn go-live, theo đúng thứ tự chúng chặn

Ngày giao: 18/09/2026 (tối).
Base: `0341b5d` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Cái gì thật sự đang chặn go-live

Tôi liệt kê hết, rồi nói rõ cái nào đợt này làm được và cái nào không.

| # | Chặn | Ai giải được |
|---|---|---|
| 1 | Chiến lược **chưa có lợi thế đo được** (Q-1) | **Chủ dự án.** Tám chiến lược crypto âm, cổng cứng VN âm. Không phải việc của agent |
| 2 | **Cửa xác nhận lệnh thật chưa từng chạy một lần nào** | Một nửa agent (dựng bài diễn tập), một nửa chủ dự án (diễn tập thật) |
| 3 | **Bằng chứng luồng không sống sót qua một lần dựng lại container** | **Agent.** Task 1 |
| 4 | **Độ phủ luồng dưới dải lành** (88,9% / 89,5% so với 93,0–93,8%) | **Agent đo**, `grace = 20` đã sống nên thứ Hai mới có lời giải |
| 5 | Máy ngủ / chuyển VPS | **Chủ dự án** |

Đợt này làm số **3, 2, 4** và một việc nhỏ số 4b. Số 1 và 5 không phải việc của agent, và tôi
**không** giả vờ rằng làm xong đợt này là go-live được.

### 0.1. Cửa xác nhận: chín lần gọi, không lần nào có người nghe

```
 status  | count |              dau              |             cuoi
---------+-------+-------------------------------+-------------------------------
 expired |     9 | 2026-08-14 09:20:18+07        | 2026-09-04 09:20:17+07
```

Chín dòng, **toàn bộ `expired`**, không dòng nào `confirmed`, `placed` hay `failed`. Bảng
`real_order_fills` **rỗng**.

Thiết kế là: engine phát hiện tín hiệu → ghi `pending_real_orders` (TTL **15 phút**) → phát
`WARN` kèm câu lệnh `uv run python scripts/confirm_real_order.py <id>` → **người** chạy lệnh đó
và gõ `YES`. Với `real_trading_enabled: false` thì toàn bộ đường đi vẫn chạy đủ, chỉ bước cuối
(`confirm_real_order.py:98`) in "SẼ đặt lệnh" thay vì gọi SSI.

Nghĩa là: **ngay cả ở chế độ chạy khô, cửa này chưa từng mở một lần nào.** Đó không phải lỗi
code — chín test trong `tests/test_confirm_real_order.py` phủ cả nhánh khô lẫn nhánh thật. Đó là
việc **chưa ai diễn tập**.

Và `confirm_real_order.py:75` từ chối đơn đã hết hạn, nên **không thể dùng chín dòng cũ để tập**.

### 0.2. Bằng chứng luồng bị xoá hai lần trong một ngày

Hôm nay collector bị dựng lại **hai lần** (16:27 triển khai `grace = 20`, 17:51 build ảnh mới).
Mỗi lần, toàn bộ dòng `bars closed` biến mất, và `stream_health_check` lập tức báo `exit 2`
"0 nến" cho một phiên thật ra lành. Đợt 51 Task 1 đã dừng đúng chỗ vì collector **không có
volume nào**:

```
$ docker inspect ai_auto_trading_system-collector-1 --format "{{json .Mounts}}"
[]
```

Chừng nào chưa gắn volume, mọi con số phủ luồng đều có hạn dùng bằng lần dựng lại kế tiếp.

### 0.3. Lỗ hổng nến 18/09 — lần này đo từ DB, không đo từ log

Log container mất rồi, nhưng bảng `bars` thì còn. Nó cho thấy **lỗ thật, backfill không vá được**:

```
 symbol | sang | chieu        (ky vong 27 | 18)
--------+------+-------
 AAA    |   26 |    18
 HPG    |   27 |    18
 IJC    |   24 |    18

   moc    |   ma con lai
----------+---------
 10:30:00 | HPG,IJC        <- thieu AAA
 11:10:00 | AAA,HPG        <- thieu IJC
 11:15:00 | AAA,HPG        <- thieu IJC
 11:25:00 | AAA,HPG        <- thieu IJC
```

Bốn nến thiếu **hẳn**, sau cả backfill. Ba trong bốn là IJC, ba mốc liền nhau quanh 11:10–11:25.
Đây là manh mối tốt hơn con số phần trăm, và nó **không phụ thuộc log container**.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `docker-compose.yml` | có sẵn | 1 — **chỉ thêm khối `volumes` cho `collector`** |
| `trading/collector/main.py` | có sẵn | 1 — ghi thêm dòng bằng chứng |
| `scripts/stream_health_check.py` | có sẵn | 1 — đọc nguồn bền trước, log sau |
| `tests/test_stream_health_check.py` | có sẵn | 1 — **chỉ thêm**, không sửa 11 test cũ |
| `scripts/rehearse_confirm_gate.py` | **mới** | 2 |
| `tests/test_rehearse_confirm_gate.py` | **mới** | 2 |
| `scripts/deploy_drift_check.py` | có sẵn | 4 — **chỉ sửa chuỗi thông điệp** |
| `tests/test_deploy_drift_check.py` | có sẵn | 4 — **chỉ thêm** |
| `docs/superpowers/research/2026-09-18-dot-52-*.md` | **mới** | báo cáo |

**Không đụng:** `trading/storage/db.py`, bảng `bars`, `trading/real_orders.py`,
`scripts/confirm_real_order.py`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
`trading/engine/logic.py`, `derivative_backtest`, `pattern_backtest`,
`scripts/heartbeat_check.py`, `scripts/backfill_universe.py`, `config/config.yaml`.

Ràng buộc chung: `real_trading_enabled` giữ **`false`** — đợt này **tuyệt đối không bật**, kể cả
"để thử"; không gọi SSI, không gọi BingX; không in secret; `.env` không sửa/không commit/không
mở; **chỉ đọc DB `trading`**, không `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`DROP` (Task 2 làm
việc trên DB **`trading_test`**, xem §Task 2); **không** `delete`/`purge`/`add`/`update` bất kỳ
stream hay consumer NATS nào (sự cố 13/08); không xoá file; **không commit, không push**. Mọi
truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`. Mọi `git diff` trong báo cáo
copy từ lệnh `git diff`. Output thiếu thì ghi **"CHƯA LÀM"**, **không bịa**. Chạy
`npx gitnexus analyze` trước và sau; MCP gitnexus hay timeout — ghi rõ thay vì im lặng bỏ qua.
**Phép đo phải là bước cuối cùng.**

**Cửa sổ thời gian cho Task 1:** chỉ được dựng lại container **sau 15:05 hoặc trước 08:30**.
Nếu bạn đang đọc brief này trong giờ 09:00–15:05 của một ngày giao dịch: **làm Task 2, 3, 4
trước, để Task 1 lại**, và ghi rõ trong báo cáo.

---

## Task 1 — Bằng chứng chốt nến sống sót qua dựng lại container

### 1.1. Gắn volume

Thêm vào service `collector` trong `docker-compose.yml`, **chỉ khối này, không đụng gì khác**:

```yaml
    volumes:
      - ./logs:/app/logs
```

`./logs` đã tồn tại và đang chứa log của các job lịch (`run_if_docker_up.sh` tạo nó). Dùng lại
thư mục đó, **đừng tạo thư mục mới**.

**Kiểm ngay hai điều trước khi đi tiếp**, vì cả hai đều làm hỏng âm thầm nếu sai:
1. Tiến trình trong container **ghi được** vào `/app/logs` (quyền). Chứng minh bằng một lần ghi
   thật, không suy luận.
2. Container **không xoá** nội dung `./logs` sẵn có khi mount.

Sai bất kỳ điều nào → **dừng, báo cáo**, đừng chữa bằng cách đổi quyền hệ thống.

### 1.2. Ghi bằng chứng

Tại chỗ đang phát `alert("INFO", "bars closed", ...)` trong `persist_bars`
(`trading/collector/main.py`, khoảng dòng 113–128), ghi thêm một dòng vào
`/app/logs/bars_closed.log`, mỗi lần chốt một dòng:

```
<ISO ts chot, +07> <symbol> <so snapshot>
```

Ba điều **bắt buộc**, mỗi điều đã có người trả giá:

1. **Không bao giờ được ném.** `persist_bars` chạy qua `asyncio.create_task()` fire-and-forget —
   exception thoát ra bị asyncio nuốt thành "Task exception was never retrieved", bar mất mà
   không ai biết. Chính docstring của hàm đó đã cảnh báo. Bọc `try/except` riêng, hỏng thì nuốt.
2. **Ghi sau khi đã `publish` và `write_bars` xong.** Giao bar cho engine luôn ưu tiên hơn ghi
   bằng chứng.
3. **Mở–ghi–đóng từng lần**, không giữ file handle mở suốt đời tiến trình. Giữ handle thì khi
   file bị xoay vòng hoặc thư mục bị thay, tiến trình ghi vào chỗ không ai đọc — im lặng.

### 1.3. `stream_health_check` đọc nguồn bền trước

Thứ tự: **file bền trước, log container sau**, và **in rõ đã dùng nguồn nào**. Không có file
(mọi phiên trước hôm nay) → rơi về log y như hiện nay. Tương thích ngược tuyệt đối.

### 1.4. Kiểm chứng

1. Suite đầy đủ pass (mốc **774**), ruff sạch.
2. Ba test mới, **không sửa một `assert` nào** của 11 test cũ:
   - có file bền, không có log → đếm đúng, in nguồn `file`
   - không có file bền, có log → đếm đúng như cũ, in nguồn `log`
   - có cả hai → dùng file, và **nêu rõ trong test** con số nào được chọn
3. **Dữ liệu thật, dán nguyên văn** — bốn lượt này rơi về log nên phải giữ nguyên kết quả cũ:

   | Lệnh | Kỳ vọng |
   |---|---|
   | `--date 2026-09-17 --session sang` | exit 2, **35,8%** (29/81) |
   | `--date 2026-09-15 --session sang` | exit 0, **93,8%** (76/81) |
   | `--date 2026-09-18 --session chieu` | **bỏ qua**, exit 0 |
   | `--date 2026-09-19 --session sang` | ngày nghỉ → **bỏ qua**, exit 0 |

   Lệch → **dừng, báo cáo**, đừng sửa phép tính cho khớp.
4. **Phép thử quyết định — làm cho bằng được:**
   - dựng lại collector (đúng cửa sổ thời gian ở §1), đợi vài phút
   - **xác nhận container chạy đúng image vừa build** — so
     `docker inspect -f "{{.Image}}" ai_auto_trading_system-collector-1` với
     `docker image inspect ai_auto_trading_system-collector --format "{{.Id}}"`.
     **Hai chuỗi phải bằng nhau.** Hôm nay 18/09 `docker compose up -d` đã **bỏ qua** collector
     một lần dù image đã đổi, và chỉ `--force-recreate` mới chữa được. Đừng tin dòng chữ compose in.
   - **dựng lại lần nữa**, rồi kiểm `./logs/bars_closed.log` **vẫn còn nội dung cũ**.

   Đây là toàn bộ lý do Task 1 tồn tại. Không chứng minh được điều này thì Task 1 **chưa xong**,
   dù code đã viết.
5. Cổng cứng VN khớp từng chữ số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## Task 2 — Dựng bài diễn tập cho cửa xác nhận lệnh thật

Mục tiêu: để chủ dự án **tập mở cửa** mà **không chạm DB thật, không chạm SSI, không bật cờ**.

### 2.1. Vì sao cần một script riêng

Chín đơn cũ đều hết hạn, và `confirm_real_order.py:75` từ chối đơn hết hạn — đúng như nó nên
làm. Nên không có cách nào tập trên dữ liệu sẵn có. Cần dựng một đơn mới, **trong DB
`trading_test`**, rồi đi hết đường.

### 2.2. `scripts/rehearse_confirm_gate.py`

Một script, làm đúng bốn việc, **chỉ trên `trading_test`**:

1. Tạo một dòng `pending_real_orders` giống hệt hình dạng dòng thật (nhìn dòng `id=1226` làm
   mẫu: `0434221`, `IJC`, `BUY`, `100`, `7330`), TTL 15 phút.
2. In ra **đúng câu lệnh** mà người dùng sẽ phải gõ, kèm `order_id`.
3. Chạy `confirm()` với `confirm_input="YES"` và `real_trading_enabled=false`, in nguyên văn
   kết quả.
4. In trạng thái dòng đó sau khi chạy.

**Hàng rào cứng, phải có, và phải có test chứng minh nó chặn:** script **từ chối chạy** nếu DSN
không trỏ tới `trading_test`, và **từ chối chạy** nếu `real_trading_enabled` là `true`. Một
script diễn tập chạy nhầm vào DB thật là đúng loại tai nạn 13/08. Không có hàng rào thì đừng
viết script.

### 2.3. Năm câu phải trả lời trong báo cáo

1. **Dòng `WARN` mà engine phát ra trông như thế nào?** Dán nguyên văn từ code, gồm cả câu lệnh
   xác nhận và `order_id`. Người nhận Telegram có đủ thông tin để hành động ngay không, hay
   phải mở máy tra thêm?
2. **15 phút bắt đầu đếm từ lúc nào** — lúc ghi DB hay lúc Telegram gửi xong? Chênh lệch bao
   nhiêu? Đọc code, đừng đoán.
3. **Chín đơn cũ được sinh vào những giờ nào?** Có nằm trong giờ làm việc không? (Tôi đã đo:
   09:20, 09:20, 09:21, 09:33, 13:42, 13:52, 13:54, 13:57, 13:59 — hãy tự kiểm lại và đối chiếu.)
4. **Nếu người dùng gõ `YES` ở phút thứ 16 thì sao?** Thông điệp từ chối có nói rõ "đã hết hạn,
   chờ tín hiệu sau" không, hay nó khó hiểu?
5. **Có đường nào để đơn tự hết hạn mà không ai được báo không?** Tức là: khi một đơn chuyển
   `pending` → `expired`, có cảnh báo nào không? Nếu **không** thì đó là một chuông thiếu — báo
   cáo, **đừng tự thêm**.

### 2.4. Kiểm chứng

1. Test mới cho hàng rào: DSN không phải `trading_test` → **từ chối**; `real_trading_enabled=true`
   → **từ chối**. Hai test này quan trọng hơn phần còn lại của script.
2. Chạy thật một lượt trên `trading_test`, dán **nguyên văn** toàn bộ output.
3. Xác nhận **bảng `pending_real_orders` trong DB `trading` không thêm dòng nào**: đếm trước và
   sau, cả hai phải là **9**.

---

## Task 3 — Bốn nến thiếu của 18/09, đo từ DB

**Đọc thuần. Không sửa file nào.**

Backfill đã chạy và vẫn thiếu bốn nến. Trả lời ba câu:

1. **Bốn nến đó có thật sự không tồn tại ở SSI, hay backfill bỏ sót?** Đừng gọi SSI để kiểm —
   hãy trả lời bằng cách đọc code backfill và nêu rõ đường nào dẫn tới việc một nến trong phiên
   không được nạp. Nếu không kết luận được từ code: ghi **"CHƯA ĐỦ DỮ LIỆU"** và nêu phép đo
   còn thiếu.
2. **Ba nến IJC thiếu liền nhau (11:10, 11:15, 11:25) có phải cùng một sự kiện không?** Đối
   chiếu với `bars` của các mã khác cùng mốc, và với `heartbeat`.
3. **Lỗ này thuộc loại `grace` chữa được không?** `grace` chỉ quyết định *chờ bao lâu trước khi
   chốt một nến*. Nếu nến thiếu vì **không có tick nào**, `grace = 20` không chữa được gì và
   con số thứ Hai sẽ **không** cải thiện. Nói thẳng dự đoán của bạn kèm lý do — thứ Hai ta đối
   chiếu.

So sánh nền dùng **15, 17, 18/09**. **Bỏ 16/09** — phiên đó 100% backfill nên luôn "không thiếu
nến", đưa vào là tự lừa mình.

---

## Task 4 — Sửa lời `deploy-drift`, và truy nguyên nhân backfill bị giết

### 4.1. Lời cảnh báo đang gây hiểu nhầm

Hôm nay 18/09 lúc 17:51, sau khi build ảnh mới, `deploy-drift` in:

```
[deploy-drift] collector: KHÔNG đọc được image build — container không chạy hoặc không có image
```

Sự thật khác hẳn: container **đang chạy**, nhưng image mà nó tham chiếu **đã bị xoá**
(`docker inspect <id>` → `no such object`) vì build mới đã thay tag. Ba tình huống rất khác nhau
đang bị gộp thành một câu:

- container không chạy
- container chạy, image còn, đọc được
- **container chạy, image đã biến mất** ← tình huống thật hôm nay, và là tình huống nguy hiểm
  nhất vì nó nghĩa là **đang chạy code không ai truy được**

Tách ba nhánh, mỗi nhánh một thông điệp riêng. **Chỉ sửa chuỗi và nhánh phân loại** — không đổi
mã thoát, không đổi ngưỡng, không đổi cách so mốc build.

Kiểm chứng: test mới cho nhánh "image biến mất" (**chỉ thêm**), và chạy thật
`uv run python scripts/deploy_drift_check.py` — hiện tại phải ra `exit 0`.

### 4.2. Vì sao backfill đêm 17/09 bị giết

Tôi đã **rút lại** chẩn đoán "PT10M giết nó" của brief 51 §0.3 — xem phụ lục F của báo cáo đợt
51. Sự thật đã biết:

```
Trigger            = 20:30:00
LastRunTime        = 2026-09-17 20:40:45   (gio BAT DAU, muon 10 phut 45 giay)
LastTaskResult     = 1073807364 = 0x40010004 STATUS_DBG_TERMINATE_PROCESS
StartWhenAvailable = False
NumberOfMissedRuns = 0
Thoi luong that    = 74 giay cho 175 ma (do chieu 18/09)
```

Đọc **Task Scheduler Operational log** cho task `trading-backfill-universe` đêm 17/09
(`Microsoft-Windows-TaskScheduler/Operational`, các Event ID quanh `100/102/103/111/201/203/329`)
và trả lời: **ai chấm dứt tiến trình, lúc nào, vì sao?** Nếu log đã bị xoay vòng mất: ghi
**"CHƯA ĐỦ DỮ LIỆU"** và nêu rõ cần bật gì để lần sau bắt được.

Giả thuyết hiện tại của tôi là **máy ngủ** — hãy kiểm nó, đừng mặc định nó đúng. Nếu đúng thì
`PT30M` không chữa được gì và việc cần làm là `powercfg` / VPS.

**Không đăng ký, không sửa Scheduled Task nào.**

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. `git diff` từng file — kỳ vọng **chỉ thêm** ở các file test và ở `docker-compose.yml`.
3. Task 1: 5 tiêu chí, **nguyên văn phép thử dựng lại hai lần** ở mục 1.4.4, và hai chuỗi
   image ID để chứng minh container chạy đúng ảnh.
4. Task 2: nguyên văn một lượt diễn tập, hai test hàng rào, và **số dòng `pending_real_orders`
   trong DB `trading` trước/sau (phải là 9/9)**, cùng năm câu trả lời.
5. Task 3: ba câu trả lời kèm truy vấn đã dùng.
6. Task 4: `git diff` của `deploy_drift_check.py`, output chạy thật, và kết luận về Event Log.
7. Ba dòng cuối: số test pass (mốc **774**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không bật `real_trading_enabled`**, không chạm `config/config.yaml`.
- **Không `INSERT`/`UPDATE`/`DELETE`** trên DB `trading`. Task 2 chỉ dùng `trading_test`.
- **Không sửa** `confirm_real_order.py` hay `trading/real_orders.py`. Phát hiện lỗi → báo cáo.
- **Không tự thêm chuông** cho đơn hết hạn (Task 2 câu 5) — báo cáo là đủ.
- **Không đăng ký, không sửa Scheduled Task.**
- **Không đổi ngưỡng `0,90` / `0,50`.**
- **Không chạy `DELETE`** dòng `TEST` trong `orders`.
- **Không dựng lại container trong giờ 08:30–15:05** ngày giao dịch.

---

## 4. Việc của chủ dự án

1. **Hai lệnh còn treo từ đợt 51** — lệnh thứ hai quan trọng hơn, không có nó thì bản vá
   `daily-data-check` vẫn không kêu được:
   ```powershell
   $Task = Get-ScheduledTask -TaskName "trading-backfill-universe"
   $Task.Settings.ExecutionTimeLimit = "PT30M"
   Set-ScheduledTask -InputObject $Task

   Set-ScheduledTask -TaskName "trading-daily-data-check" `
     -Trigger (New-ScheduledTaskTrigger -Daily -At 21:00)
   ```
2. **Diễn tập cửa xác nhận**, sau khi Task 2 xong. Đây là việc **chỉ ông làm được**, và nó là
   cái chặn go-live thật sự duy nhất còn lại thuộc về kỹ thuật. Câu hỏi cần trả lời bằng trải
   nghiệm, không bằng suy luận: **ông có kịp 15 phút không?**
3. **Ông có nhận được cảnh báo Telegram không?** Hôm nay 18/09 có **năm** tin thật (hai từ
   `stream-health` lúc 12:25 và 15:10, ba từ `daily_data_check` do tôi chạy kiểm). Nếu không đủ
   năm, chuỗi cảnh báo đứt ở đoạn cuối và mọi việc đợt 46–52 đều vô nghĩa.
4. **`powercfg /change standby-timeout-dc 0`** và **chuyển VPS**. Sau Task 4.2 thì đây nhiều
   khả năng là nguyên nhân gốc chứ không phải việc phụ.
5. **Q-1:** có giao một đợt tìm chiến lược nữa không. Bộ công cụ đo đã sẵn và rẻ — cái thiếu là
   một ý tưởng đáng đo.
6. **`DELETE` dòng `TEST`** trong `orders`, nếu ông đồng ý.
