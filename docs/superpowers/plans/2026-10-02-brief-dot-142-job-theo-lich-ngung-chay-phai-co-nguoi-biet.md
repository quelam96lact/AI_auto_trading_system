# Brief đợt 142 — một job theo lịch NGỪNG CHẠY thì phải có người biết

## Vì sao — sự cố thật ngày 02/10/2026

`trading-container-health` (mỗi 10 phút, 24/7) và `trading-disk-check` (mỗi 6 giờ) **không tự chạy
lần nào trong cả ngày 02/10, kể cả lúc phiên đang chạy**. Không có gì báo cả. Claude chỉ tình cờ thấy
khi audit đợt 140, lúc 10:20.

Nguyên nhân đã đo:
- Đây là **hai task duy nhất** dùng trigger hằng ngày neo lúc **00:00** có lặp lại, với
  `StartWhenAvailable=False`. Cả hai có `NumberOfMissedRuns=1`.
- Đêm 01/10 máy ngủ từ 17:56 đến 05:21, trượt đúng mốc 00:00, nên chuỗi lặp của ngày 02/10 không khởi
  động. Mọi lần Task Scheduler gọi sau đó (05:37, 10:07, 10:17:47, 11:07) đều trả `0x800710E0` trước
  khi wrapper kịp ghi một dòng log.
- Mọi task khác vẫn chạy, vì chúng hoặc neo vào giờ máy thức, hoặc có `StartWhenAvailable=True`
  (`backup`, `backup-check`, `orderbook-backup`).

Có hai lỗi tách biệt:
1. **Cấu hình** hai task sai (Việc 1). Chủ dự án đã cho phép sửa **riêng hai task này, riêng cài đặt
   này**, trong đợt này.
2. **Lỗ im lặng**: một job giám sát chết thì không ai giám sát nó. Trên VPS dùng cron, lỗi trigger này
   không còn. Nhưng một dòng cron bị xoá nhầm, hay cron daemon chết, sẽ cho đúng triệu chứng đó: im
   lặng (Việc 2 và 3). Họ lỗi quen thuộc của dự án: [[golive-gate-den-xanh-gia]].

## ⚠ Giới hạn — đọc kỹ, đợt này đụng vào chuông đang chạy

- **Lịch chạy THẲNG từ cây làm việc.** Mỗi lần lưu `scripts/heartbeat_check.py` hay
  `scripts/container_health_check.py` vào repo chính là có hiệu lực ngay ở lần chạy lịch kế tiếp.
  Heartbeat chạy mỗi 5 phút 08:00–15:00 ngày giao dịch, và là công tắc chết-người của cả hệ thống. Một
  lỗi cú pháp ở đó giữa phiên là hệ thống mất chuông. Vì vậy:
  - **Viết và test trong một git worktree riêng**: `git worktree add --detach <thư mục nháp> HEAD`.
    Không sửa hai file đó trong repo chính cho tới khi Việc 5 cho phép.
  - **Chỉ chép code vào repo chính ngoài khung 08:00–15:10 của ngày giao dịch** (hoặc vào ngày nghỉ),
    và chỉ sau khi `pytest` đầy đủ đã xanh **trong worktree**.
  - Xong thì `git worktree remove --force` và dán `git worktree list` để chứng minh đã dọn.
- **KHÔNG commit, KHÔNG push.** Không restart container, không sửa `.env`.
- **Task Scheduler:** chỉ được đổi **đúng một cài đặt**, `StartWhenAvailable=True`, trên **đúng hai task**
  `trading-container-health` và `trading-disk-check`. Không đổi trigger, lệnh, tài khoản chạy, hay bất
  kỳ task nào khác.
- **KHÔNG gửi Telegram thật** trong lúc làm. Mọi lần chạy thật phải có `--dry-run`. Lưu ý: ngay lúc viết
  brief này `container-health` **đang thật sự** ngừng chạy, nên một phép kiểm đúng sẽ báo thật.
- Chỉ sửa: `scripts/heartbeat_check.py`, `scripts/container_health_check.py`, test tương ứng, và đúng
  các dòng liên quan trong `DEPLOYMENT.md`. Không đổi các phép kiểm hiện có của hai script đó.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc 1 — bật `StartWhenAvailable` cho hai task

1. Trước khi sửa: xuất XML của hai task (`Export-ScheduledTask`) ra thư mục nháp ngoài repo.
2. Đặt `StartWhenAvailable=True` trên đúng hai task.
3. Xuất XML lần nữa, `diff` hai bản: **chỉ** dòng `<StartWhenAvailable>` được phép khác. Dán diff.

Ghi rõ trong báo cáo: hiệu quả thật chỉ kiểm được vào **lần sau máy ngủ qua 00:00**. Claude sẽ kiểm vào
sáng hôm sau, bằng `NumberOfMissedRuns` và dòng log đầu ngày.

## Việc 2 — heartbeat canh các job 24/7 có còn chạy không

`run_if_docker_up.sh` ghi một dòng có giờ cho **mỗi lần** job được gọi, kể cả khi Docker tắt
(`<YYYY-MM-DD HH:MM:SS> <nhãn> start` hoặc `... SKIP: ...`). Vậy "lần cuối job được gọi" = dòng có
giờ cuối cùng mang đúng nhãn của job trong `logs/<file>.log`. Tên file log và nhãn lấy từ chính dòng
`exec "$RUN" <file log> <nhãn>` của `sched.sh`. Lưu ý: dòng SKIP cũng tính là đã được gọi, vì phép này
kiểm **bộ lập lịch**, không kiểm Docker; Docker tắt đã có chuông riêng.

1. Một bảng kỳ vọng trong `heartbeat_check.py`, khoá theo tên nhánh `sched.sh`. Với mỗi job: tuổi tối
   đa của lần gọi gần nhất. Tối thiểu năm job chạy 24/7:

   | Job | Lịch | Ngưỡng đề xuất |
   |---|---|---|
   | `container-health` | mỗi 10 phút | 25 phút |
   | `disk-check` | mỗi 6 giờ (00/06/12/18) | 6 giờ 30 phút |
   | `backup` | 02:00 hằng ngày | 26 giờ |
   | `orderbook-backup` | 02:30 hằng ngày | 26 giờ |
   | `backup-check` | 03:00 hằng ngày | 26 giờ |

   Chính sách: job chu kỳ ≥ 6 giờ phải bị bắt ngay khi **lỡ MỘT lần**; job 10 phút được phép lỡ một lần (bắt từ lần lỡ thứ hai). Claude đã tự soát và sửa ngưỡng `disk-check` của chính mình: bản nháp đầu đề xuất 12 giờ 30 phút, mà lỡ lần 06:00 thì tuổi lớn nhất trong khung heartbeat chỉ khoảng 12 giờ, tức không bao giờ báo.

   **Tự kiểm lại từng ngưỡng** với lịch thật (`Get-ScheduledTask`) và với khung giờ heartbeat chạy
   (08:00–15:00). Viết cạnh mỗi dòng một câu số học, kiểu đợt 131 đã làm cho ngưỡng 23 giờ: "chạy
   đúng thì tuổi lớn nhất là X, lỡ một lần thì là Y > ngưỡng". Ngưỡng nào sai thì sửa và nói rõ.
2. **Mọi** nhánh `sched.sh` phải nằm trong bảng kỳ vọng **hoặc** trong một danh sách `KHONG_CANH`, mỗi
   dòng kèm lý do một câu (vd job chỉ chạy ngày giao dịch buổi tối, cần lịch giao dịch mới canh đúng).
   Test đọc `sched.sh` và đỏ nếu có nhánh nằm ngoài cả hai. Như vậy job thêm về sau buộc người viết
   phải quyết định.
3. **Chỉ báo khi chuyển trạng thái:** báo một lần khi job từ "còn chạy" sang "ngừng", và một lần khi nó
   chạy lại. Heartbeat chạy mỗi 5 phút; báo mỗi lần là 84 tin một ngày. Lưu trạng thái vào một file
   cạnh file trạng thái của `container_health_check.py`, theo đúng cách file đó làm. Đọc trạng thái
   lỗi hoặc thiếu thì coi như lần chạy đầu, và **không** im lặng nuốt một job đang ngừng.
4. Không tìm thấy file log, hoặc file không có dòng nào mang đúng nhãn → coi là **ngừng**, nêu rõ lý do.
   Không bao giờ coi là "còn chạy".
5. Thêm `--dry-run` cho `heartbeat_check.py`: in cảnh báo thay vì gửi Telegram, và **không ghi file
   trạng thái**. Đây là cách duy nhất để chạy thật an toàn trong đợt này.

## Việc 3 — ai canh heartbeat

Heartbeat không tự canh được chính nó. `container_health_check.py` chạy 24/7 thì canh: **trong ngày giao
dịch** (dùng `trading.calendar_vn`), từ 08:15 đến 15:00, nếu lần gọi gần nhất của nhãn heartbeat cũ hơn
**15 phút** thì báo. Vẫn chỉ báo khi chuyển trạng thái, dùng file trạng thái sẵn có của nó. Ngoài khung
đó thì không đánh giá.

## Tiêu chí hoàn thành

1. Việc 1: diff XML chỉ khác `<StartWhenAvailable>`, cho cả hai task.
2. Test hàm thuần (đầu vào là chuỗi log giả và `now` tiêm vào):
   - job vừa chạy → im;
   - quá ngưỡng 1 phút → báo;
   - đang ngừng và lần trước đã báo → im (không lặp);
   - chạy lại → báo hồi phục một lần;
   - log chỉ có dòng `SKIP: docker chua chay` mới → coi là còn chạy;
   - không có file log → báo ngừng;
   - file trạng thái hỏng → không chết, và không nuốt một job đang ngừng;
   - Việc 3: heartbeat cũ 16 phút lúc 10:00 ngày giao dịch → báo; lúc 10:00 Chủ nhật → im; lúc 07:00
     ngày giao dịch → im.
3. **Tái hiện đúng sự cố 02/10:** một test dùng **nguyên văn** các dòng cuối thật của
   `logs/container-health.log` ngày 02/10 (dòng `2026-10-02 05:49:54 container-health start`), với
   `now = 2026-10-02 10:20` → phải báo `container-health`.
4. **Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:**
   - bỏ điều kiện "chỉ báo khi chuyển trạng thái" → test "không lặp" đỏ;
   - coi "không có file log" là còn chạy → test tương ứng đỏ;
   - bỏ một nhánh `sched.sh` khỏi cả bảng lẫn `KHONG_CANH` → test đọc `sched.sh` đỏ.
5. Chạy thật, **sau khi đã chép code vào repo chính và ngoài giờ phiên**:
   `scripts/sched.sh heartbeat --dry-run`. Kỳ vọng in đúng tình trạng thật lúc chạy, **không gửi
   Telegram**, không ghi file trạng thái. Dán log. Nếu `container-health` vẫn đang ngừng lúc đó, dòng
   cảnh báo của nó phải có mặt. Nếu dòng đó **không** có mặt thì đó là lỗi của đợt này; điều tra trước
   khi báo xong.
6. `ruff` sạch; `uv run pytest -q` ≥ **1.706 passed** cộng số test mới, chạy cả trong worktree lẫn sau khi
   chép vào repo chính.
7. Dán `git worktree list` cuối cùng: chỉ còn repo chính.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-142-job-ngung-chay.md`:

- Giờ chép code vào repo chính (phải ngoài khung phiên).
- Bảng ngưỡng kèm câu số học.
- Số đo dán nguyên văn.
- Brief sai ở đâu thì nói ra.
- Cái gì không kiểm được (đặc biệt Việc 1 trên máy ngủ thật) thì ghi là **không kiểm được**.
