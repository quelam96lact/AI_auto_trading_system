# Brief đợt 51 — Ba chuông mù, hai đêm không nạp, và một image bảy ngày tuổi

Ngày giao: 18/09/2026 (sau phiên).
Base: `4490e05` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Đợt này sinh ra từ một lần tôi tự đi kiểm tra trạng thái go-live chiều nay, **không** từ báo cáo
của agent. Bốn phát hiện, cả bốn đều là **hỏng âm thầm** — đúng hạng bệnh mà đợt 46 → 50 dành
để diệt, và cả bốn đều lọt qua toàn bộ mảng giám sát mà hôm nay tôi vừa tuyên bố là "coi như xong".

Tôi nói thẳng chỗ tôi sai: sáng nay tôi kết luận *"cả bảy job đều có Scheduled Task và đều đã
được chứng minh chạy được"*. Câu đó đúng về mặt chữ và **sai về mặt ý nghĩa**. "Chạy được" không
phải "kêu được khi có chuyện". Ba trong bảy job chiều nay lộ ra là không thể kêu, hoặc kêu xong
thì không ai nghe.

---

## 0. Bốn phát hiện, kèm bằng chứng thô

### 0.1. Dựng lại container xoá sạch tử số của `stream_health_check`

`stream_health_check` đếm tử số bằng cách đọc **log container** (dòng `bars closed`). Chiều nay
lúc 16:27 collector được dựng lại để triển khai `grace = 20`. Hệ quả, ngay bây giờ:

```
$ uv run python scripts/stream_health_check.py --date 2026-09-18 --session sang ...
dung: phien sang ngay 2026-09-18 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)
Exit code: 2

$ uv run python scripts/stream_health_check.py --date 2026-09-18 --session chieu ...
dung: phien chieu ngay 2026-09-18 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)
Exit code: 2

$ docker compose logs collector | Select-String "bars closed" | Measure-Object
Count: 0
```

Nhưng phiên hôm nay **không hỏng**. `logs/stream-health.log` — file nằm trên đĩa, sống sót —
ghi lại số đo thật lúc 12:25 và 15:10, trước khi dựng lại:

```
2026-09-18 12:25:42 stream-health start
WARN: do phu luong phien sang ngay 2026-09-18 dat 88.9% (72/81 nen), duoi nguong canh bao 90%
EXIT=1
2026-09-18 15:10:02 stream-health start
WARN: do phu luong phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen), duoi nguong canh bao 90%
EXIT=1
```

Nghĩa là: **một phiên lành, đo lúc 15:10 ra 89,5%, đo lại lúc 17:00 ra 0% và CRITICAL.** Cùng
một ngày, cùng một lệnh, khác nhau chỉ vì container bị dựng lại ở giữa.

Đây là lỗi nặng nhất trong bốn cái, vì nó **tự động hoá việc nói dối**: `deploy-drift` tồn tại
để *khuyến khích* dựng lại container, còn `stream-health` thì mất trí nhớ mỗi lần bị dựng lại.
Hai job trong cùng một `sched.sh` phá nhau.

Và chú ý chỗ này: DB **không** giúp được. `bars.source` luôn bằng `'ssi'`, không phân biệt
luồng thời gian thực với backfill:

```
 2026-09-18 | ssi    |   134
 2026-09-17 | ssi    |   138
 2026-09-16 | ssi    |   156   <- phien nay 100% backfill, van la 'ssi'
```

Số lần chốt nến và `snapshot_count` của đợt 44 hiện **chỉ tồn tại trong một dòng log INFO**
(`main.py:120-128`), không có bản sao nào trên đĩa hay trong DB.

### 0.2. `daily-data-check` chạy sớm hơn dữ liệu nó kiểm **năm tiếng**, nên chưa từng kêu được

Năm lần chạy theo lịch gần nhất, tất cả `exit 0`:

```
2026-09-14 15:30:02 ... KhÃ´ng cÃ³ mÃ£ nÃ o cÃ³ bar trong ngÃ y (ngÃ y nghá»‰ hoáº·c feed ngá»«ng...) EXIT=0
2026-09-15 15:30:02 ... (y het)                                                              EXIT=0
2026-09-16 15:30:02 daily-data-check SKIP: docker chua chay
2026-09-17 15:30:03 ... (y het)                                                              EXIT=0
2026-09-18 15:30:02 ... (y het)                                                              EXIT=0
```

Tôi chạy tay chính script đó, chính ngày đó, lúc 17:05:

```
$ uv run python scripts/daily_data_check.py --date 2026-09-18
[2026-09-18] CANH BAO: Sot bar daily sau phien!
Tong so ma active: 175
So ma co bar: 8
So ma THIEU bar (167 ma): ABB, ACB, ACV, ANV, BAF, ... (+152 ma nua)
EXIT=1
```

Nguyên nhân không nằm trong code mà nằm ở **nhịp**: bar daily của universe do backfill đêm ghi
lúc **20:30**, còn job kiểm chạy lúc **15:30**. Lúc 15:30 bảng luôn rỗng cho ngày hôm đó, script
rơi vào nhánh:

```python
# scripts/daily_data_check.py:66-72
if not present_symbols:
    return 0, set(), "Không có mã nào có bar trong ngày (ngày nghỉ hoặc feed ngừng toàn diện...)"
```

→ `exit 0`, mọi ngày, vĩnh viễn. **Job này chưa từng một lần có khả năng kêu.** Nhánh "nhường
Heartbeat 2A" được viết ra cho ngày nghỉ, nhưng vì nhịp sai nên nó nuốt luôn mọi ngày giao dịch.

*(Hai lần chạy tay của tôi ở trên đã gửi thật hai tin Telegram cho ngày 18/09 và 15/09. Đó là
cảnh báo đúng, không phải giả.)*

### 0.3. Backfill đêm bị giới hạn 10 phút giết — hai đêm không nạp, không ai biết

```
 ts         | so ma co bar_daily
------------+-------
 2026-09-14 |   174
 2026-09-15 |   174
 2026-09-16 |     8
 2026-09-17 |     8
 2026-09-18 |     8
```

Tám mã đó là do collector tự backfill 1d lúc khởi động, không phải job đêm. Job đêm:

```
LastRunTime = 2026-09-17 20:40:45   LastTaskResult = 1073807364
ExecutionTimeLimit = PT10M          Trigger = 20:30
```

`1073807364` = `0x40010004` = `STATUS_DBG_TERMINATE_PROCESS`. Chạy lúc 20:30, chết lúc 20:40:45
— **đúng mười phút**. Task Scheduler giết nó. Nó chết trước cả khi kịp ghi dòng `start` vào
`logs/backfill.log` (dòng cuối cùng trong file đó vẫn là 16/09 `SKIP: docker chua chay`).

Ngày 15/09 chạy lọt vì cửa sổ nạp ngắn. Sau hai đêm lỡ, cửa sổ dài ra, chạy lâu hơn, và càng
lỡ thì càng chắc chắn bị giết — **một vòng xoáy tự siết**. `BACKFILL_DAYS=7` nghĩa là còn
**bốn đêm** nữa trước khi phần hỏng ở giữa không tự vá được nữa.

### 0.4. Engine đang chạy code của bảy ngày trước, và chuông báo đúng đã kêu hai ngày liền

```
collector image built = 2026-09-18T09:26:49Z   (moi, grace=20 da song)
engine    image built = 2026-09-11T12:44:25Z   (bay ngay truoc)
commit gan nhat cham trading/ = 0b0491b  2026-09-18 12:43:14
```

`deploy-drift` phát hiện đúng và kêu đúng, hai sáng liên tiếp:

```
2026-09-17 08:00:08 ... engine: image CU hon commit gan nhat cham trading/ (2 ngay 21 gio) EXIT=1
2026-09-18 08:00:03 ... engine: image CU hon commit gan nhat cham trading/ (2 ngay 21 gio) EXIT=1
```

Chuông này **không mù**. Nó kêu đúng và không ai hành động. Đó là một hạng hỏng khác, và cách
chữa không phải viết thêm code.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `trading/collector/main.py` | có sẵn | 1 — ghi thêm bằng chứng chốt nến ra đĩa |
| `scripts/stream_health_check.py` | có sẵn | 1 — đọc nguồn bền, log là dự phòng |
| `tests/test_stream_health_check.py` | có sẵn | 1 — **chỉ thêm**, không sửa 11 test cũ |
| `scripts/daily_data_check.py` | có sẵn | 2 — bịt nhánh mù |
| `tests/test_daily_data_check.py` | có sẵn | 2 — **chỉ thêm** |
| `scripts/sched.sh` | có sẵn | 2 — không đổi lệnh, chỉ đổi chú thích nhịp nếu cần |
| `docs/superpowers/research/2026-09-18-dot-51-*.md` | **mới** | báo cáo |

**Không đụng:** `trading/storage/db.py`, bảng `bars`, `PaperBroker`, `trading/risk.py`,
`trading/strategies/*`, `trading/engine/logic.py`, `derivative_backtest`, `pattern_backtest`,
`scripts/heartbeat_check.py`, `scripts/backfill_universe.py`, `scripts/deploy_drift_check.py`.

Ràng buộc chung: `real_trading_enabled` giữ `false`, **không sửa** `config/config.yaml`; không
gọi SSI, không gọi BingX; không in secret; `.env` không sửa/không commit/không mở; **chỉ đọc DB**,
không `TRUNCATE`/`DROP`/`DELETE`; **không** `delete`/`purge`/`add`/`update` bất kỳ stream hay
consumer NATS nào (sự cố 13/08); **không dựng lại container**; không xoá file; **không commit,
không push**. Mọi truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`. Mọi `git diff`
trong báo cáo copy từ lệnh `git diff`, không gõ lại. Output thiếu thì ghi **"CHƯA LÀM"**,
**không bịa**. Chạy `npx gitnexus analyze` trước và sau; MCP gitnexus hay timeout — ghi rõ thay
vì im lặng bỏ qua. **Phép đo phải là bước cuối cùng.**

---

## Task 1 — Bằng chứng chốt nến phải sống lâu hơn container

### 1.1. Vấn đề phải giải, nói bằng một câu

Số lần chốt nến từ luồng thời gian thực hiện chỉ tồn tại trong log container, mà log container
bị xoá mỗi lần `docker compose up --build`. Cần một bản ghi **trên đĩa hoặc trong DB** sống sót
qua việc dựng lại.

### 1.2. Cách làm — chọn đường ít rủi ro nhất

**Ghi thêm một dòng vào file append-only trên đĩa**, ngay tại chỗ đang phát `alert("INFO", "bars closed", ...)`
trong `persist_bars` (`trading/collector/main.py`, khoảng dòng 113-128). Một dòng một lần chốt,
định dạng cố định, đủ để `stream_health_check` đếm lại:

```
<ISO ts chot, +07> <symbol> <so snapshot>
```

Ba điều **bắt buộc**, mỗi điều có lý do đã trả giá:

1. **Không bao giờ được ném.** `persist_bars` chạy qua `asyncio.create_task()` fire-and-forget;
   exception thoát ra sẽ bị asyncio nuốt thành "Task exception was never retrieved" — bar mất mà
   không ai biết. Đúng lời cảnh báo đã viết sẵn trong docstring của chính hàm đó. Bọc `try/except`
   riêng, hỏng thì nuốt, không chặn đường publish/ghi DB.
2. **Ghi sau khi đã publish và đã `write_bars` xong**, không được chen vào trước. Việc giao bar
   cho engine luôn được ưu tiên hơn việc ghi bằng chứng.
3. **Đường dẫn phải là volume đã mount sẵn**, tồn tại ngoài container. Đọc `docker-compose.yml`
   để xác định, **đừng đoán**. Nếu không có volume nào phù hợp: **dừng, báo cáo** — thêm volume
   là đổi `docker-compose.yml`, ngoài phạm vi đợt này và cần dựng lại container.

Sau đó `stream_health_check` lấy tử số theo thứ tự: **file bền trước, log container sau**, và
**in rõ nó đã dùng nguồn nào**. Không có file (phiên cũ) thì rơi về log y như hiện nay — tương
thích ngược tuyệt đối.

### 1.3. Kiểm chứng

1. Suite đầy đủ pass (mốc **771**), ruff sạch.
2. Ba test mới, **không sửa một `assert` nào** của 13 test cũ:
   - có file bền, không có log → đếm đúng, in nguồn `file`
   - không có file bền, có log → đếm đúng như cũ, in nguồn `log`
   - có cả hai → dùng file, và **nêu rõ trong test** con số nào được chọn

   (`tests/test_stream_health_check.py` hiện có **11** test; `tests/test_daily_data_check.py`
   hiện có **5**. Hai con số này là mốc — sau đợt này chúng chỉ được tăng.)
3. **Dữ liệu thật, dán nguyên văn** — bốn lượt này phải giữ nguyên kết quả cũ vì chúng rơi về log:

   | Lệnh | Kỳ vọng |
   |---|---|
   | `--date 2026-09-17 --session sang` | exit 2, **35,8%** (29/81) |
   | `--date 2026-09-15 --session sang` | exit 0, **93,8%** (76/81) |
   | `--date 2026-09-18 --session chieu` | **bỏ qua**, exit 0 (đợt 50) |
   | `--date 2026-09-19 --session sang` | ngày nghỉ → **bỏ qua**, exit 0 |

   Lệch → **dừng, báo cáo**, đừng sửa phép tính cho khớp.
4. **Không chạy được lượt nào chứng minh file bền trên dữ liệu thật** — collector phải chạy qua
   một phiên mới sinh ra file. Ghi **"CHƯA LÀM — chờ phiên 22/09"** và nêu rõ đó là phép đo
   quyết định. Đừng dựng lại container để ép nó sinh file.
5. Cổng cứng VN khớp từng chữ số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## Task 2 — `daily-data-check` phải có khả năng kêu

### 2.1. Hai việc tách bạch

**(a) Nhịp.** Job kiểm phải chạy **sau** backfill đêm, không phải trước. Đọc `scripts/sched.sh`
và xác định giờ đề xuất, có lý do từ dữ liệu: backfill khởi động 20:30 và lượt 15/09 mất bao lâu
(đo từ `logs/backfill.log`). **Soạn lệnh `Register-ScheduledTask` sửa nhịp, đừng tự đăng ký.**

**(b) Nhánh mù.** Nhánh `if not present_symbols: return 0` đúng cho ngày nghỉ và sai cho ngày
giao dịch. Sửa thành: **ngày giao dịch mà không mã nào có bar → `exit 2`**; ngày nghỉ → giữ
nguyên `exit 0` như cũ. Dùng lịch có sẵn trong `trading/calendar_vn.py` — **đọc code để chọn
đúng hàm**, đừng đoán tên.

### 2.2. Kiểm chứng

1. Test mới (**chỉ thêm**, không sửa test cũ):
   - ngày giao dịch + `present` rỗng → **exit 2**
   - ngày nghỉ (thứ Bảy) + `present` rỗng → **exit 0**, thông điệp cũ
   - `present` thiếu một phần → **exit 1** như cũ
2. Dữ liệu thật, dán nguyên văn:

   | Lệnh | Kỳ vọng |
   |---|---|
   | `--date 2026-09-18` | exit 1, **8/175 có bar, 167 thiếu** |
   | `--date 2026-09-15` | exit 1, **174/175, thiếu POM** |
   | `--date 2026-09-19` (thứ Bảy) | exit 0, nhánh ngày nghỉ |

   **Cảnh báo:** hai lượt đầu **gửi thật tin Telegram**. Đó là hành vi đúng của script, không
   phải lỗi — nhưng ghi rõ trong báo cáo là đã gửi mấy tin, để chủ dự án không tưởng có sự cố mới.
3. Suite đầy đủ pass, ruff sạch, cổng cứng VN khớp.

---

## Task 3 — Đo backfill đêm, và soạn lệnh nới giới hạn

**Chỉ đo và soạn lệnh. Không đăng ký, không sửa `backfill_universe.py`.**

1. Từ `logs/backfill.log`, đo **thời lượng thật** của lượt 15/09 (mốc `start` → `EXIT=`).
2. Chạy `scripts/sched.sh backfill` **một lần, ngay bây giờ** (ngoài phiên, an toàn), bấm giờ.
   Lượt này phải nạp bù **ba ngày** 16–18/09 nên là ước lượng tốt nhất cho trường hợp xấu.
   Nó **ghi DB** — đây là ngoại lệ **duy nhất** của ràng buộc "chỉ đọc DB" trong đợt này, và
   nó chỉ `UPSERT` vào `bars_daily`, đúng việc nó vẫn làm mỗi đêm.
3. Sau khi chạy xong, đo lại: `--date 2026-09-16/17/18` phải cho **174/175 mã** thay vì 8.
4. Soạn `Set-ScheduledTask` nới `ExecutionTimeLimit`, con số suy từ phép đo với biên an toàn
   rõ ràng (ghi rõ biên là bao nhiêu và vì sao). Theo đúng khuôn task đã đăng ký
   (`wscript.exe` + `run_hidden.vbs` **một tham số**, `//B //Nologo`, `UserId quelam`,
   `LogonType Interactive`, `RunLevel Limited`, `MultipleInstances IgnoreNew`, **không**
   `StartWhenAvailable`). Sai khuôn này chính là lỗi đợt 50 — hai lệnh soạn sẵn hỏng im lặng.
5. Trả lời một câu: **`MultipleInstances IgnoreNew` có gây rắc rối không** nếu một lượt chạy quá
   giờ trigger hôm sau? Đọc, đừng đoán.

---

## Task 4 — Engine bảy ngày tuổi: liệt kê, đừng triển khai

**Đọc thuần. Không dựng lại container.**

Liệt kê mọi commit chạm `trading/` từ `2026-09-11T12:44:25Z` đến nay **không** có trong image
engine đang chạy, và với mỗi commit trả lời: **nó có đổi hành vi engine không, hay chỉ chạm
collector/scripts/test?** Kết luận một trong hai:

- **Engine đang chạy khác code trong repo về mặt hành vi** — kèm danh sách khác chỗ nào.
- **Khác về hash nhưng không khác hành vi** — kèm lý do.

Đây là câu trả lời quyết định việc dựng lại engine có gấp hay không, và nó là **quyết định của
chủ dự án**, không phải của agent.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. `git diff` từng file đã sửa — kỳ vọng **chỉ thêm** ở hai file test.
3. Task 1: 5 tiêu chí, nguyên văn bốn lượt dữ liệu thật, và nêu rõ mục nào **"CHƯA LÀM"**.
4. Task 2: 3 tiêu chí, nguyên văn ba lượt, **số tin Telegram đã gửi**.
5. Task 3: hai phép đo thời lượng, ba lượt kiểm lại sau backfill, lệnh soạn sẵn, câu trả lời
   về `MultipleInstances`.
6. Task 4: danh sách commit + kết luận hai lựa chọn.
7. Ba dòng cuối: số test pass (mốc **771**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không dựng lại container nào**, kể cả engine. Task 4 chỉ liệt kê.
- **Không tự đăng ký hay sửa Scheduled Task.** Soạn lệnh rồi dừng.
- **Không sửa** `docker-compose.yml`. Nếu Task 1 cần volume mới → dừng, báo cáo.
- **Không đổi ngưỡng `0,90` / `0,50`.**
- **Không sửa** `backfill_universe.py` hay `deploy_drift_check.py`.
- **Không chạy `DELETE`** dòng `TEST` trong `orders`.
- **Không bật** `real_trading_enabled`.

---

## 4. Việc của chủ dự án

1. **Nền `grace = 60` của 18/09 đã cứu được** từ `logs/stream-health.log`: sáng **88,9%**
   (72/81), chiều **89,5%** (51/57). `grace = 20` đã sống từ 16:27 hôm nay. So sánh thứ Hai
   dùng **15, 17, 18/09** làm nền (bỏ 16/09 — phiên đó 100% backfill nên luôn "không thiếu nến").
   Lưu ý cả hai phiên hôm nay đều **dưới 90%**, thấp hơn dải lành 93,0–93,8% — nếu `grace = 20`
   không kéo lên thì vấn đề không nằm ở `grace`.
2. **Engine có dựng lại ngay không?** Chờ Task 4 trả lời rồi quyết.
3. **Cửa xác nhận 15 phút:** ông có nhận được `WARN` trên Telegram không? Hôm nay có **hai** tin
   WARN từ `stream-health` (12:25 và 15:10) cộng hai tin tôi vừa gây ra từ `daily_data_check`.
   Nếu bốn tin đó không tới máy ông thì chuỗi cảnh báo đứt ở đoạn cuối, và mọi thứ đợt 46-51
   làm đều vô nghĩa.
4. **Q-1:** có giao một đợt tìm chiến lược nữa không.
5. **`powercfg /change standby-timeout-dc 0`** và **chuyển VPS** — hai lần `SKIP: docker chua chay`
   trong `logs/backfill.log` (14/09, 16/09) là cùng một nguyên nhân.
