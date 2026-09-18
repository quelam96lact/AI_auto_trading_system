# Brief đợt 50 — Bịt đường báo động giả cuối, và kiểm hai chuông chưa gắn lịch

Ngày giao: 18/09/2026.
Base: `0b0491b` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Hai việc, **đọc thuần hoặc chỉ sửa file trong repo** — chạy được bất kỳ lúc nào, kể cả trong
phiên. Không dựng lại container, không gọi mạng ngoài JetStream cục bộ (chỉ đọc), không ghi DB.

**Không xung đột brief 47 Task 2/3** (sau 15:05: đo phiên nền rồi triển khai `grace = 20`).

---

## 0. Bối cảnh

### 0.1. Đường báo động giả cuối của `stream_health_check`

Đợt 49 bịt được đường 12:14 (bộ chọn phiên mặc định), nhưng tôi tìm ra còn một đường nữa:

```
$ uv run python scripts/stream_health_check.py --date 2026-09-18 --session chieu ...
dung: phien chieu ngay 2026-09-18 khong co dong 'bars closed' nao ... (0 nen)
Exit code: 2
```

Phiên chiều hôm nay **chưa diễn ra**. Bộ chọn phiên của đợt 49 tránh được chuyện này **khi
không truyền tham số**, nhưng tham số tường minh đi thẳng qua cửa bảo vệ.

Scheduled Task không đi đường này nên không nguy hiểm ngay. Nhưng người chạy tay rất dễ gặp,
và mỗi cảnh báo giả là một bước tới chỗ **mọi** cảnh báo bị bỏ qua — đúng bệnh đợt 46.

### 0.2. Hai chuông nằm trong `sched.sh` mà chưa từng chạy

`sched.sh` có bảy job; năm job đã có Scheduled Task. Hai job còn lại **chưa từng chạy lần nào**:

| Job | Script | Nó hỏi gì |
|---|---|---|
| `engine-cam` | `scripts/check_silent_engine.py` | Engine có "câm" không — cổng thanh khoản đóng 100%, hoặc không sinh tín hiệu MUA nào |
| `engine-consumer` | `scripts/engine_consumer_check.py` | Engine có đang tiêu thụ bar thật từ JetStream không (chuông 2C) |

Tôi **cố ý chưa gắn chúng vào lịch**: một chuông chưa kiểm mà kêu sai sẽ làm hỏng cả những
chuông đúng. Đợt 47 đã chứng minh `stream_health_check` bằng chính lịch sử hỏng trước khi gắn
lịch; hai cái này phải qua cùng một cửa.

### 0.3. Và một điều về nhịp chạy mà tôi suýt làm sai

`engine_consumer_check.py` **chỉ cảnh báo khi đang trong giờ giao dịch** (`is_trading_time`),
ngoài phiên thì `exit 0`. Nên nếu gắn nó vào lịch **15:10** như `stream-health` thì nó sẽ
**luôn luôn `exit 0`** và không bao giờ phát hiện được gì.

Hai chuông này cần nhịp **khác hẳn** `stream-health`, và Task 2 phải xác định nhịp đúng bằng
cách đọc code chứ không đoán.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `scripts/stream_health_check.py` | có sẵn | 1 — chặn phiên chưa kết thúc |
| `tests/test_stream_health_check.py` | có sẵn | 1 — thêm test, **không sửa 9 test cũ** |
| `docs/superpowers/research/2026-09-18-dot-50-*.md` | **mới** | báo cáo |

Task 2 là **kiểm chứng thuần** — không sửa file nào. Nếu phát hiện lỗi trong hai script chuông:
**báo cáo, đừng sửa.** Sửa một chuông cần brief riêng với đủ ràng buộc.

Ràng buộc chung: `real_trading_enabled` giữ `false`; **không dựng lại container**; **chỉ đọc
DB**; **không `delete`/`purge`/`add`/`update`** bất kỳ stream hay consumer NATS nào — chỉ đọc;
không xoá file; **không commit, không push**. Output copy từ terminal, thiếu thì ghi
**"CHƯA LÀM"**, **không bịa**.

---

## Task 1 — Phiên chưa kết thúc thì bỏ qua, không kêu

### 1.1. Luật

Sau khi đã xác định được `(ngày, phiên)` cần kiểm — dù do người dùng truyền tường minh hay do
bộ chọn mặc định — kiểm tiếp: **phiên đó đã kết thúc chưa** tại thời điểm chạy.

Chưa kết thúc → in `bo qua: ...` và **`exit 0`**, đúng như nhánh cuối tuần đợt 49 đã làm.
**Không** `exit 2`.

Mốc kết thúc: phiên sáng xong lúc **11:30**, phiên chiều xong lúc **15:05**. Chế độ **cả ngày**
(`--date` không kèm `--session`) coi là xong khi **phiên chiều** đã xong.

### 1.2. Kiểm chứng

1. **Chín test cũ pass nguyên vẹn, không sửa một `assert` nào.** Dán `git diff` của
   `tests/test_stream_health_check.py` — kỳ vọng chỉ có phần **thêm**.
2. Test mới, mốc thời gian giả lập trong test:
   - `--date <hôm nay> --session chieu` chạy lúc `12:00` → `bo qua`, **exit 0**
   - `--date <hôm nay> --session sang` chạy lúc `12:00` → **kiểm bình thường** (sáng đã xong)
   - `--date <hôm nay>` (cả ngày) chạy lúc `12:00` → `bo qua`, **exit 0**
   - `--date <hôm qua> --session chieu` → **kiểm bình thường**
3. **Kiểm bằng dữ liệu thật, bốn lượt, dán nguyên văn:**

   | Lệnh | Kỳ vọng |
   |---|---|
   | `--date 2026-09-18 --session chieu` | `bo qua`, exit 0 ← chính ca lỗi |
   | `--date 2026-09-18 --session sang` | exit 1, **88,9%** (72/81) |
   | `--date 2026-09-17 --session sang` | exit 2, **35,8%** (29/81) |
   | `--date 2026-09-15 --session sang` | exit 0, **93,8%** (76/81) |

   Ba con số cuối là số tôi tự đo. Lệch → **dừng, báo cáo**, đừng sửa phép tính cho khớp.
4. Suite đầy đủ pass (mốc **769**), ruff sạch, **cổng cứng VN khớp từng chữ số**:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## Task 2 — Kiểm hai chuông, và xác định nhịp chạy đúng

**Không sửa hai script. Chỉ chạy, đọc, và báo cáo.**

### 2.1. Với mỗi chuông, trả lời năm câu

1. **Nó hỏi gì?** Một câu, bằng lời của bạn, sau khi đọc code.
2. **Điều kiện kêu là gì?** Liệt kê từng vế, kèm số dòng.
3. **Mã thoát nghĩa là gì?** `0` / `1` / `2` tương ứng trạng thái nào.
4. **Nhịp chạy đúng là gì, và vì sao?** Đọc code để biết nó có tự giới hạn theo giờ giao dịch
   không, có cơ chế chống spam không, và chu kỳ chống spam bao lâu. **Không đoán.**
5. **Chạy nó bây giờ ra gì?** Dán nguyên văn output và mã thoát.

### 2.2. Đối chứng — phần quan trọng nhất

Đợt 47 chứng minh `stream_health_check` bằng cách chạy nó trên một ngày hỏng thật (16/09) và
một ngày lành thật (15/09). Làm điều tương đương cho hai chuông này, **trong khả năng cho phép**:

**`engine-cam`** — ta có sẵn đáp án từ đợt 45: trên nến 5 phút, ba mã production sinh
**17 tín hiệu bull / 9.611 bar**, và cổng thanh khoản mở **100%** số bar. Nên chuông này
**phải báo KHÔNG câm**. Nếu nó báo "câm" thì hoặc nó hỏng, hoặc nó đo thứ khác với đợt 45 —
**điều tra và báo cáo, đừng sửa**.

**`engine-consumer`** — chỉ kêu trong giờ giao dịch. Nêu rõ:
- Chạy **ngoài** giờ → kỳ vọng `exit 0` im lặng. Xác nhận.
- Chạy **trong** giờ (nếu còn kịp phiên chiều hôm nay) → dán output.
- Nếu không kịp, ghi **"CHƯA LÀM — ngoài giờ"** và nêu rõ cần chạy lại trong phiên.

**Tuyệt đối chỉ đọc JetStream.** Không `delete`, `purge`, `add`, `update` stream hay consumer
nào. Sự cố 13/08 (một suite test đã xoá durable consumer của engine thật và purge stream
`BARS`) là lý do ràng buộc này tồn tại.

### 2.3. Kết luận phải đưa ra

Với mỗi chuông, một trong ba:

- **SẴN SÀNG GẮN LỊCH** — kèm nhịp đề xuất và lý do từ code.
- **CHƯA SẴN SÀNG** — kèm điều cần sửa trước.
- **CHƯA ĐỦ DỮ LIỆU** — kèm phép đo còn thiếu.

Và **soạn sẵn lệnh `Register-ScheduledTask`** cho chuông nào kết luận là sẵn sàng, theo đúng
khuôn task `trading-stream-health` đã đăng ký hôm nay (`wscript.exe` + `run_hidden.vbs`,
`UserId quelam`, `LogonType Interactive`, `RunLevel Limited`, `ExecutionTimeLimit PT10M`,
`MultipleInstances IgnoreNew`, **không** `StartWhenAvailable`).

**Agent không tự đăng ký Scheduled Task.** Soạn lệnh, dừng.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. **`git diff tests/test_stream_health_check.py`** — kỳ vọng chỉ có phần thêm.
3. Task 1: kết quả 4 tiêu chí, **nguyên văn bốn lượt chạy dữ liệu thật**.
4. Task 2: với mỗi chuông — năm câu trả lời, kết quả đối chứng, kết luận ba lựa chọn, và lệnh
   đăng ký soạn sẵn nếu sẵn sàng.
5. Ba dòng: số test pass (mốc **769**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không sửa** `check_silent_engine.py` hay `engine_consumer_check.py`. Phát hiện lỗi thì
  báo cáo.
- **Không tự đăng ký Scheduled Task.**
- **Không ghi gì lên NATS.** Chỉ đọc.
- **Không đụng container**, không triển khai gì. `grace = 20` là brief 47 Task 3.
- **Không đổi ngưỡng `0,90` / `0,50`** của đợt 49 — bốn phiên cho thấy dải lành `93,0–93,8%`
  nên ngưỡng đang đúng.
- **Không chạy `DELETE`** dòng `TEST` trong `orders`.
- **Không quyết định A/B/C** — đã gác, không chặn gì khi Q-1 chưa có lời giải.

---

## 4. Việc của chủ dự án

1. **Sau đợt này: đăng ký nốt hai chuông** nếu chúng được kết luận sẵn sàng. Khi đó cả bảy job
   trong `sched.sh` đều có lịch, và mảng giám sát coi như xong.
2. **Cửa xác nhận 15 phút:** ông có nhận được cảnh báo `WARN` trên Telegram không, và 15 phút
   có đủ không? Đây là điểm chặn go-live ngang hàng với Q-1 và chỉ ông trả lời được.
3. **Q-1:** có muốn tôi giao một đợt tìm chiến lược nữa không? Bộ công cụ đo (đối chứng ngẫu
   nhiên, hiệu chỉnh đa phép kiểm theo họ, ngưỡng chi phí) đã sẵn và rẻ — cái thiếu là một ý
   tưởng đáng đo, không phải công cụ.
4. **`powercfg /change standby-timeout-dc 0`** và **chuyển VPS**.
5. **`DELETE` dòng `TEST`** trong `orders`, nếu ông đồng ý sau khi đọc báo cáo đợt 49.
