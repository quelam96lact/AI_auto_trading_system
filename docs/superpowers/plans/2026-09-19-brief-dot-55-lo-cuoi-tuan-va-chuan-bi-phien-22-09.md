# Brief đợt 55 — Lỗ cuối tuần, tag cuốn chiếu, và chuẩn bị phép đo 22/09

Ngày giao: 19/09/2026 (thứ Bảy).
Base: `0d5b0b5` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Hôm nay là **thứ Bảy** — không có phiên, nên mọi việc dưới đây chạy được thoải mái. Nhưng Task 4
là **chuẩn bị** cho thứ Hai, không phải đo ngay: phép đo thật chỉ tồn tại vào 22/09.

---

## 0. Bốn việc, và vì sao chúng đứng cùng nhau

| # | Việc | Nguồn |
|---|---|---|
| 1 | `stream_health_check` vẫn kêu oan cho ngày nghỉ khi truyền tham số tường minh | Phụ lục C đợt 52 |
| 2 | Thói quen gắn tag rollback đã đứt; cơ chế `:previous` chưa được viết vào đâu | Task 3 đợt 54 |
| 3 | Lịch chạy có **hai bản** và hai bản đã lệch | Phụ lục H đợt 54 |
| 4 | Phiên 22/09 là phép đo quyết định của đợt 52 — cần giao thức trước, không phải ứng biến | Đợt 52 |

Ba việc đầu đều là **một công thức hai chỗ** ở ba tầng khác nhau: tầng nhánh điều kiện (1), tầng
quy trình triển khai (2), tầng lịch (3). Đó là lý do chúng đi chung một đợt.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `scripts/stream_health_check.py` | có sẵn | 1 |
| `tests/test_stream_health_check.py` | có sẵn | 1 — **chỉ thêm**, không sửa 15 test cũ |
| `DEPLOYMENT.md` | có sẵn | 2 |
| `docs/superpowers/research/2026-09-19-dot-55-*.md` | **mới** | báo cáo |

**Task 3 và Task 4 không sửa file nào** — khảo sát và soạn giao thức.

Ràng buộc chung: `real_trading_enabled` giữ `false`; không sửa `config/config.yaml`; không gọi
SSI/BingX; không in secret; `.env` không sửa/không commit/**không mở**; **chỉ đọc DB**; **không**
`delete`/`purge`/`add`/`update` stream hay consumer NATS nào; **không dựng lại container, không
build image, không tạo/xoá tag image**; **không đăng ký hay sửa Scheduled Task**; không xoá file;
**không commit, không push**. Mọi `git diff` copy từ lệnh. Thiếu thì ghi **"CHƯA LÀM"**, **không
bịa** — đợt 52 có hai dòng kiểm chứng không phải output thật, đừng lặp lại.

---

## Task 1 — Ngày nghỉ truyền tường minh vẫn phải im

### 1.1. Lỗ còn lại

Đường **mặc định** (không tham số) đã im đúng — đây là đường Scheduled Task đi:

```
$ uv run python scripts/stream_health_check.py
bo qua: khong co phien giao dich nao ket thuc trong vong 24 gio (ngay nghi/cuoi tuan)
Exit code: 0
```

Đường **tham số tường minh** thì không, kể cả với một thứ Bảy **đã qua**:

```
$ uv run python scripts/stream_health_check.py --date 2026-09-12 --session sang
dung: phien sang ngay 2026-09-12 khong co dong 'bars closed' nao ... (0 nen) [nguon: log]
Exit code: 2
```

Nguyên nhân cấu trúc: `resolve_target_session` (dòng 131–156) xử lý cuối tuần **chỉ cho việc tự
chọn phiên**, còn `is_session_ended` (dòng 174) chỉ trả lời "đã kết thúc chưa". **Không ai hỏi
"ngày đó có phải ngày giao dịch không"** khi ngày do người dùng truyền vào.

Đây đúng hình dạng cái lỗ đợt 50 đã bịt cho nhánh "chưa kết thúc" — cùng chỗ, khác nhánh.

### 1.1b. Và một lỗ nặng hơn mà tôi chỉ thấy khi soát lại brief này

Tôi viết ở trên rằng đường mặc định "đã im đúng". **Đúng với cuối tuần, sai với ngày lễ.**

```python
# scripts/stream_health_check.py:131-133
def resolve_target_session(now_vn: datetime, holidays: set[date] | None = None) -> ...
# :145
    check_holidays = holidays or set()
# :148
    if now_vn.weekday() in (5, 6) or current_date in check_holidays:

# nhung cho goi, dong 367:
    resolved = resolve_target_session(now_vn)        # <- KHONG truyen holidays
```

`holidays` **không bao giờ được truyền vào**, nên `check_holidays` luôn rỗng và vế
`current_date in check_holidays` **không bao giờ đúng**. Nhánh ngày lễ là **code chết** — lần
thứ sáu của mẫu này trong repo.

Hậu quả cụ thể: một ngày lễ rơi vào **ngày thường** (ví dụ 02/09 Quốc khánh), Scheduled Task chạy
lúc 15:10 sẽ đi lọt qua cửa cuối tuần (vì là thứ Ba/thứ Tư), `is_session_ended` bảo "đã qua
15:05", rồi đo và thấy 0 nến → **`exit 2`, CRITICAL, Telegram**. Một báo động giả **được bảo đảm**
vào mọi ngày lễ giữa tuần.

Và còn một lớp thứ hai: `config/config.yaml` hiện chỉ liệt kê
`holidays: ['2026-08-31', '2026-09-01', '2026-09-02']` — **toàn ngày đã qua**. Nên kể cả sau khi
nối dây xong, sẽ không có ngày lễ tương lai nào được bảo vệ. Phần đó là **việc của chủ dự án**
(không sửa `config.yaml`), nhưng báo cáo phải nêu.

**Task 1 vì vậy gồm hai việc, không phải một:**

| | Việc |
|---|---|
| (a) | Nối dây `holidays` từ config vào `resolve_target_session` — chữa nhánh chết |
| (b) | Thêm cửa "ngày nghỉ" cho đường tham số tường minh — lỗ ở §1.1 |

Cả hai dùng **cùng một nguồn ngày lễ**. Nếu bạn thấy mình đọc config ở hai chỗ khác nhau, đó là
dấu hiệu làm sai.

### 1.2. Luật

Sau khi đã xác định `(ngày, phiên)` — **dù tường minh hay mặc định** — hỏi thêm: **ngày đó có
phải ngày giao dịch không?** Không phải → in `bo qua: ... la ngay nghi` và **`exit 0`**.

Thứ tự ba cửa, ghi rõ trong code bằng một comment ngắn:

```
1. ngay nghi?        -> bo qua, exit 0
2. phien chua xong?  -> bo qua, exit 0     (dot 50)
3. do do phu luong                          (dot 47/49)
```

Dùng lịch có sẵn trong `trading/calendar_vn.py` — **đọc code để chọn đúng hàm**, đừng đoán tên.
Lưu ý `is_trading_time` nhận một `datetime` chứ không phải `date`; đợt 51 đã giải bài này trong
`daily_data_check.py`, xem cách ở đó rồi quyết định — và nếu bạn thấy cách đó **lặp lại ở chỗ thứ
ba**, hãy nói ra (xem Task 3, cùng một bệnh).

### 1.3. Kiểm chứng

1. Suite đầy đủ pass (mốc **782**), ruff sạch.
2. **Bốn** test mới, **không sửa một `assert` nào** của 15 test cũ:
   - `resolve_target_session` **nhận được** ngày lễ: gọi nó với `holidays` chứa `now_vn.date()`
     → trả `None`. Test này canh nhánh chết ở §1.1b; nếu ai gỡ việc nối dây, nó phải đổ.
   - `--date <thứ Bảy đã qua> --session sang` → `bo qua`, **exit 0**
   - `--date 2026-09-01 --session sang` → `bo qua`, **exit 0**
     (ngày lễ có thật trong `config/config.yaml`: `['2026-08-31', '2026-09-01', '2026-09-02']`;
     chọn ngày lễ rơi vào **ngày thường** để test phân biệt được nhánh lễ với nhánh cuối tuần)
   - `--date <ngày giao dịch đã qua> --session sang` → **đo bình thường**, không bỏ qua
3. **Dữ liệu thật, dán nguyên văn:**

   | Lệnh | Kỳ vọng |
   |---|---|
   | `--date 2026-09-12 --session sang` | `bo qua`, exit 0 ← chính ca lỗi |
   | `--date 2026-09-19 --session sang` | `bo qua`, exit 0 (hôm nay, thứ Bảy) |
   | không tham số | `bo qua`, exit 0 (giữ nguyên hành vi) |
   | `--date 2026-09-18 --session sang` | **đo**, không bỏ qua |

   Lượt cuối hiện cho `exit 2 "0 nen"` vì log container đã bị xoá ba lần hôm 18/09 — **đó là kết
   quả đúng cho hôm nay**, đừng sửa gì để nó ra số đẹp. Điều phải đúng là nó **đi tới bước đo**
   chứ không rơi vào nhánh bỏ qua.
4. **Chứng minh test phân biệt được:** tạm gỡ cửa số 1, chạy lại, xác nhận test mới **đổ**, rồi
   khôi phục và xác nhận `git diff` của file đó **rỗng**. Dán cả hai kết quả. Một phép kiểm báo
   "sạch" mà chưa chứng minh là còn phân biệt được thì "sạch" chỉ là cách nói khác của "câm".

---

## Task 2 — Viết cơ chế `:previous` vào `DEPLOYMENT.md`

Đợt 54 đề xuất tag cuốn chiếu thay cho `dotNN-rollback-*`. Tôi tán thành: nó không đẻ ra 14 tag
để rồi phải dọn (hôm 18/09 tôi dọn 12 tag, thu hồi 223MB).

### 2.1. Vì sao phải viết xuống, không phải vì sao phải làm

Ngày 18/09 collector và engine được dựng lại **năm lần**, **không tag lần nào**. Lý do không phải
ai lười: **quy trình đó không tồn tại trong bất kỳ runbook nào**, nó chỉ nằm rải rác trong các
brief cũ. Thứ chỉ sống trong trí nhớ thì sẽ đứt.

Hai sự thật làm việc này gấp hơn vẻ ngoài:

- **Mỗi lần build sinh ảnh mới** kể cả khi mã nguồn không đổi (phụ lục B đợt 53). Không tag trước
  thì ảnh cũ mất tag ngay, chỉ còn sống nhờ container đang chạy — dựng lại lần nữa là mất hẳn.
- **`dot46` và `dot47` là cùng một ảnh** (`9c66a1dc8ec2`). Nên hiện có đúng **một** ảnh collector
  cũ trên máy, và **không có ảnh engine cũ nào**.

### 2.2. Việc

Thêm vào `DEPLOYMENT.md`, trong phần triển khai, thành **bước bắt buộc trước khi build**:

```bash
docker tag ai_auto_trading_system-collector:latest ai_auto_trading_system-collector:previous 2>/dev/null || true
docker tag ai_auto_trading_system-engine:latest    ai_auto_trading_system-engine:previous    2>/dev/null || true
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

Kèm **quy trình quay về** — đây mới là phần có giá trị, và nó phải nói rõ một điều: quay về ảnh
`:previous` **không** đổi `docker-compose.yml`, nên volume mount `./logs:/app/logs` **vẫn còn**;
thứ mất đi là phần **mã** của lần triển khai vừa rồi.

Và ghi rõ **phép kiểm sau mỗi lần triển khai**, rút từ bài học 18/09:

```bash
docker inspect -f "{{.Image}}" ai_auto_trading_system-collector-1
docker image inspect ai_auto_trading_system-collector --format "{{.Id}}"
# hai chuoi phai bang nhau — VA grep mot chuoi dac trung cua chinh ban va
# ben trong container: bang nhau chi chung minh container khop tag,
# KHONG chung minh tag khop ma nguon (18/09 da dinh dung bay nay)
```

**Không chạy lệnh nào trong số này.** Viết tài liệu, dừng.

### 2.3. Một câu phải trả lời

`:previous` chỉ giữ **một** bậc lùi. Nếu hai lần triển khai liên tiếp cùng hỏng thì sao? Nêu ý
kiến ngắn: chấp nhận một bậc là đủ, hay cần `:previous` + `:previous2`? Có lý lẽ cho cả hai —
tôi muốn nghe bạn chọn và vì sao.

---

## Task 3 — Nhịp chạy nên sống ở đâu?

**Khảo sát và đề xuất. Không sửa Scheduled Task, không sửa `sched.sh`.**

`DEPLOYMENT.md` khẳng định cả bảy job "gọi **cùng một bảng job** với cron Ubuntu". Đúng về
**lệnh**, sai về **nhịp**:

| Job | Ubuntu cron | Windows task | Lệch |
|---|---|---|---|
| `heartbeat` | `*/5 8-15` → 08:00–**15:55** | `PT5M/PT7H` → 08:00–**15:00** | +55 phút |
| `engine-consumer` | `*/5 9-15` → 09:00–**15:55** | `PT5M/PT6H10M` → 09:00–**15:10** | +45 phút |

Năm job còn lại chạy một lần nên khớp tuyệt đối.

Trả lời bốn câu:

1. **Bên nào đúng?** Đọc `heartbeat_check.py` và `engine_consumer_check.py` để biết chúng tự chặn
   theo giờ thế nào, rồi nói lượt chạy sau 15:00 có ích gì không — hay chỉ thêm dòng log.
2. **Có nên gom nhịp vào `sched.sh`** (nơi đã giữ "job X chạy lệnh gì") để hai nền đọc cùng một
   chỗ? Nêu cách làm cụ thể nếu có, hoặc nói rõ vì sao không làm được.
3. **Nếu không gom được**, đề xuất cách rẻ nhất để hai bản không lệch tiếp — ví dụ một bảng duy
   nhất trong `DEPLOYMENT.md` mà cả cron lẫn Task Scheduler đều phải khớp, kèm cách kiểm.
4. **Chênh lệch hiện tại có đáng sửa ngay không?** Nói thẳng. "Không đáng, chỉ cần ghi rõ là cố
   ý" là một câu trả lời hợp lệ và tôi muốn nghe nếu đó là kết luận.

---

## Task 4 — Giao thức đo phiên 22/09

**Soạn giao thức, không đo. Không có gì để đo hôm nay.**

Thứ Hai 22/09 là phiên đầu tiên có đủ ba thứ cùng lúc: `grace = 20` đã sống, `bars_closed.log`
đã gắn volume, và `daily-data-check` đã dời sang 21:00. Đây là phép đo quyết định của đợt 52.

### 4.1. Nền so sánh — chỉ dùng số còn bằng chứng

`logs/stream-health.log` là thứ duy nhất sống sót qua các lần dựng lại container:

```
OK:   phien sang ngay 2026-09-15 co 76 lan chot nen              (76/81 = 93,8%)
WARN: phien sang ngay 2026-09-18 dat 88.9% (72/81 nen)
WARN: phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen)
```

Ba con số này đo ở `grace = 60`. Con số 17/09 (35,8% sáng) **có trong báo cáo đợt 49–50 nhưng
không tái lập được nữa** — log container đã mất. Nêu nó như tư liệu, **đừng dùng làm nền**.

**Bỏ 16/09** khỏi mọi so sánh: phiên đó 100% backfill nên luôn "không thiếu nến".

### 4.2. Giao thức phải soạn

Một danh sách chạy được, theo thứ tự, cho thứ Hai:

1. **Trước phiên (≈08:30):** kiểm gì để biết hệ thống sẵn sàng — nêu lệnh và kỳ vọng.
2. **Sau phiên sáng (≈11:35):** đo gì.
3. **Sau phiên chiều (≈15:10):** đo gì.
4. **Tối (≈21:05):** `daily-data-check` chạy lần đầu ở nhịp mới — kiểm gì để biết nó **thật sự
   kêu được**, chứ không phải im vì lý do khác.

Với mỗi bước: **lệnh chính xác**, **kỳ vọng**, và **ngưỡng để gọi là hỏng**.

### 4.3. Ba câu hỏi phép đo phải trả lời được

1. **`bars_closed.log` có sống qua cuối tuần không, và có chứa dòng `bars closed` thật không?**
   Hôm nay (19/09, 01:15) file có **14 dòng** và **0 dòng `bars closed`** — toàn bộ là alert vận
   hành (`backfill start/done`, `eod pricing`), vì chưa có phiên nào chạy từ lúc gắn volume.
   Con số này **còn tăng** trong lúc collector chạy, nên hãy đo lại khi bạn bắt đầu và ghi mốc của
   chính bạn, kèm giờ đo. Điều phải đúng vào thứ Hai không phải "nhiều dòng hơn" mà là **xuất hiện
   dòng `bars closed` đầu tiên**.
2. **`grace = 20` có kéo độ phủ lên khỏi 88,9% / 89,5% không?**
3. **Nếu không kéo lên thì sao?** Đợt 52 đã dự đoán: bốn nến thiếu của 18/09 là do **cạn thanh
   khoản**, không phải luồng hỏng, nên `grace` không chữa được. Nêu rõ **dấu hiệu nào** ở thứ Hai
   sẽ xác nhận hoặc bác bỏ dự đoán đó — quyết định trước khi thấy số liệu, không phải sau.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: `git diff` hai file (kỳ vọng **chỉ thêm** ở file test), bốn lượt dữ liệu thật nguyên
   văn, và **bằng chứng test phân biệt được** (gỡ cửa → đổ → khôi phục → diff rỗng).
3. Task 2: `git diff DEPLOYMENT.md`, và câu trả lời về `:previous2`.
4. Task 3: bốn câu trả lời, kèm lệnh đọc ra từng con số.
5. Task 4: giao thức bốn bước, ba câu trả lời, và **số dòng `bars_closed.log` hôm nay**.
6. Ba dòng: số test pass (mốc **782**), ruff, cổng cứng VN đủ bốn con số
   (`-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`).

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không dựng lại container, không build image, không tạo/xoá tag.** Task 2 chỉ viết tài liệu.
- **Không đăng ký hay sửa Scheduled Task.** Task 3 chỉ khảo sát.
- **Không đo phiên 22/09 hôm nay** — chưa có gì để đo.
- **Không sửa** `heartbeat_check.py`, `engine_consumer_check.py`, `sched.sh`.
- **Không commit `README.md`** — 253 dòng vẫn chờ chủ dự án.
- **Không bật `real_trading_enabled`.**

---

## 4. Việc của chủ dự án

1. **`config/config.yaml: holidays` chỉ còn ngày đã qua** — `['2026-08-31', '2026-09-01',
   '2026-09-02']`. Sau khi Task 1 nối dây xong, danh sách này là thứ duy nhất chặn báo động giả
   vào ngày lễ giữa tuần, và nó đang **rỗng về tương lai**. Cần ông bổ sung lịch nghỉ còn lại của
   2026 và của 2027 (Tết Dương lịch, Tết Nguyên đán, Giỗ Tổ, 30/4, 1/5, 2/9). Agent **không được
   sửa `config.yaml`**, nên việc này chỉ ông làm được.
2. **`powercfg /change standby-timeout-dc 0`.** Đây giờ là việc duy nhất còn lại trong nhóm
   "backfill chết đêm", và nguyên nhân đã được chứng minh bằng Kernel-Power ở đợt 52 — không còn
   là giả thuyết. Nếu máy ngủ tối Chủ nhật thì backfill 20:30 lại chết và thứ Hai lại thiếu dữ
   liệu.
3. **`README.md` 253 dòng đổi** — xác nhận đúng ý ông rồi tôi commit.
4. **Diễn tập cửa xác nhận** (`scripts/rehearse_confirm_gate.py`, sẵn từ đợt 52). Vẫn là cái chặn
   go-live kỹ thuật duy nhất còn lại.
5. **Ông có nhận được cảnh báo Telegram không?** Hỏi lần thứ sáu. Nếu chuỗi đứt ở đoạn cuối thì
   toàn bộ đợt 46–55 không cứu được gì.
6. **Q-1** và **`DELETE` dòng `TEST`** trong `orders`.
