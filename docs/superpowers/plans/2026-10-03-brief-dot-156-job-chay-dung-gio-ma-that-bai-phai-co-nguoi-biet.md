# Brief đợt 156 — job chạy đúng giờ mà thất bại thì phải có người biết

## Bối cảnh

Đợt 142 làm phần canh lịch trong `heartbeat_check.py`: nó đọc log từng job và báo khi một job **ngừng
chạy**. Nó chỉ xét **mốc thời gian dòng log cuối**, không xét **job đó chạy xong ra sao**.

`scripts/run_if_docker_up.sh:124` đã ghi `EXIT=$RC` vào log của mỗi job sau mỗi lần chạy. Claude grep toàn
bộ `scripts/`: **không có ai đọc dòng đó để canh**. Chỗ duy nhất đọc `EXIT=` là
`daily_data_check.py:82`, và nó đọc log của job *backfill* để biết job kia đã xong, không phải để canh.

Hệ quả: **một job chạy đúng giờ nhưng thất bại thì vô hình**, trừ khi chính nó gửi được Telegram.

### Bằng chứng 1 — ngày mất 96% dữ liệu sổ lệnh, job không thể tự kêu

`logs/orderbook-recorder.log`, **29/09**: `EXIT=4`.

`scripts/record_vn30f_orderbook.py` chỉ tự thoát `0` hoặc `1` (dòng 854). **Mã 4 không đến từ code của
nó** — tiến trình bị **giết** từ bên ngoài (hôm đó task có `StopIfGoingOnBatteries=True`). Một tiến trình
bị giết **không thể gửi cảnh báo cho chính nó**, dù script có đường gửi qua `trading.alerts.alert`.

Đó chính là ngày mất khoảng 96% dữ liệu VN30F, và chủ dự án phát hiện muộn. Dấu vết duy nhất còn lại ngay
lúc đó là dòng `EXIT=4` trong log — không ai đọc. Bài học đã ghi khi đó là "kiểm `LastTaskResult`, đừng
dừng ở `State=Ready`"; đợt này là cách tự động hoá đúng bài học đó.

### Bằng chứng 2 — hai phát hiện thật về dữ liệu, không ai được báo

`logs/stream-health.log`, **18/09**:

```
WARN: do phu luong phien sang ngay 2026-09-18 dat 88.9% (72/81 nen), duoi nguong canh bao 90%
EXIT=1
WARN: do phu luong phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen), duoi nguong canh bao 90%
EXIT=1
```

`stream_health_check.py` **không gửi Telegram dòng nào** (Claude đã kiểm, cả `host_preflight.py` cũng
vậy). Hai lần thiếu nến luồng này chỉ nằm trong file log.

### Số đo mốc của Claude (03/10) — **phải tự đo lại, đừng tin bảng này**

Đếm `^EXIT=` trong `logs/*.log`, toàn bộ lịch sử:

| Job | Tổng lần | Khác 0 | Chi tiết |
|---|---|---|---|
| heartbeat | 1.587 | 160 | 157× `1`, 3× `2` |
| container-health | 335 | 17 | 17× `2` |
| engine-consumer | 595 | 1 | 1× `2` |
| deploy-drift | 20 | 10 | 8× `1`, 2× `2` |
| daily-data-check | 28 | 8 | 3× `1`, 5× `2` |
| stream-health | 14 | 4 | 2× `1`, 2× `2` |
| backup-check | 13 | 3 | 3× `1` |
| orderbook-backup | 8 | 2 | 1× `1`, 1× `2` |
| backup, disk-check, engine-cam, orderbook-daily-check, orderbook-recorder, restore-drill | | 1 mỗi job | gồm `EXIT=4` của orderbook-recorder |
| backfill, host-preflight | 22 / 8 | 0 | chưa lần nào khác 0 |

## Việc 1 — canh mã thoát, với chính sách riêng cho từng job

Mở rộng phần canh lịch trong `scripts/heartbeat_check.py`: ngoài "job có chạy không", thêm "lần chạy gần
nhất có thất bại không". Chỉ báo những mã thoát mà **không ai khác báo**.

**Không gộp "khác 0 là báo".** Ba lý do, đều đo được:
1. `heartbeat` tự thoát `1` **mỗi lần nó cảnh báo** — 157 lần. Canh chính nó sẽ nhân đôi mọi cảnh báo.
2. `container_health_check.py:497–499` thoát `2` khi Docker không chạy, và chú thích ghi rõ **"không cảnh
   báo ở đây"** vì `docker_down_alert.py` lo việc đó. 15 trong 17 lần `EXIT=2` của job này là ca đó.
3. Các job tự gửi Telegram khi phát hiện vấn đề thì canh thêm chỉ tạo tin trùng.

**Agent phải tự lập bảng chính sách**, bằng cách **đọc từng script** và ghi lý do một câu cho mỗi job:
- mã nào là "bình thường" (vd `0`, hoặc `1` khi chính job đã gửi Telegram cho phát hiện đó);
- mã nào là "không ai báo" → heartbeat phải báo.

Claude **cố ý không cho sẵn bảng này**. Bài học đợt 142: Claude từng chép tay 10 giờ chạy vào code, 9 cái
sai, và không ai phát hiện trong một đợt audit. Bảng nào chép từ brief sẽ không được kiểm. Nếu đọc script mà
vẫn không kết luận được một mã thoát nghĩa là gì thì **ghi "chưa rõ" và không canh**, rồi báo lại — đừng đoán.

Khuôn báo giống đợt 142: **chỉ báo khi chuyển trạng thái** (thất bại lần đầu báo một lần; chạy lại thành
công báo hồi phục một lần), dùng chính file trạng thái canh lịch đang có.

→ kiểm chứng bằng:
- test hàm thuần cho phần đọc mã thoát: lần chạy cuối mã 0 → im; mã "không ai báo" → báo một lần; lặp lại
  cùng mã → im; chạy lại thành công → báo hồi phục một lần; log không có dòng `EXIT=` nào → **im lặng**, không
  coi là thất bại;
- test **tái hiện hai sự cố thật**, dùng nguyên văn các dòng log ở hai bằng chứng trên: `EXIT=4` của
  orderbook-recorder 29/09, và `EXIT=1` của stream-health 18/09. Cả hai phải nổ cảnh báo;
- test **chống nhân đôi**: với `heartbeat` tự thoát `1`, và với `container-health` thoát `2` lúc Docker
  không chạy, heartbeat **không được** sinh thêm cảnh báo.

## Việc 2 — ghim để không ai bỏ sót job mới

Theo đúng khuôn test của đợt 142 ("mọi nhánh `sched.sh` phải thuộc `SCHEDULE_WATCH_JOBS` hoặc `KHONG_CANH`"):
thêm một test khẳng định **mọi nhánh của `sched.sh` đều có chính sách mã thoát rõ ràng** — hoặc được canh,
hoặc được ghi lý do không canh. Thêm nhánh mới mà quên khai báo thì test đỏ.

→ kiểm chứng bằng: phá thử xoá chính sách của một nhánh → test đỏ và **nêu đúng tên nhánh** đó.

## Cái bẫy phải tránh (Claude đã đo)

- **`grep "EXIT="` khớp cả `ALERT_EXIT=`.** `run_if_docker_up.sh:116` ghi `ALERT_EXIT=$?` cho nhánh gửi
  cảnh báo Docker-chết. Trong `logs/heartbeat.log`: `EXIT=` khớp 1.864 dòng, `^EXIT=` khớp 1.587, và
  `ALERT_EXIT=` có 277 — vừa đúng tổng. Phải neo đầu dòng.
- **Phải gắn mã thoát vào đúng lần chạy.** Lấy dòng `EXIT=` **sau** mốc chạy gần nhất của job đó. Một job
  đang chạy (đã có dòng mở đầu, chưa có `EXIT=`) **không phải** thất bại.
- **`host-preflight` và `restore-drill` chưa có task Windows** (Claude vừa liệt kê: đang có 14 task
  `trading-*`). Log của chúng chỉ từ các lần chạy tay. Đừng để thiếu task biến thành báo động giả.
- **Mã thoát `2` mang hai nghĩa khác nhau** tuỳ job: "gửi Telegram hỏng" (họ theo gửi được, xem docstring
  `_alert_common.py`) và "không đo được" (`container-health` khi Docker chết). Đọc từng script, đừng suy từ
  con số.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không sửa task, không build/restart container, không gửi Telegram thật.
- **Chỉ sửa:** `scripts/heartbeat_check.py` và test tương ứng. Không sửa `run_if_docker_up.sh`,
  `sched.sh`, `_alert_common.py`, `trading/alerts.py`, hay 15 script job còn lại.
- **Không đổi mã thoát của `heartbeat_check.py`** (họ "theo phát hiện", trả 1) — task Windows đang đọc nó.
- **Giữ nguyên hành vi đợt 155:** gửi hỏng thì **không** lưu trạng thái canh lịch. Chính sách mã thoát mới
  dùng chung file trạng thái đó, nên nó cũng phải chịu cùng quy tắc.
- **`heartbeat_check.py` chạy thẳng từ cây làm việc**, mỗi 5 phút trong giờ giao dịch. Làm trong git
  worktree; chỉ chép vào repo chính **trước 08:00 thứ Hai 05/10**, rồi chạy ngay
  `scripts/sched.sh heartbeat --dry-run` (phải `EXIT=0`, không traceback).
- **Lưới an toàn đợt 148 sẽ chặn** test ghi vào `logs/` thật. Dùng `tmp_path`, đừng lách lưới.
- GitNexus: `impact` cho phần canh lịch trước khi sửa, `detect_changes` sau khi sửa; báo 0 thay đổi thì
  `npx gitnexus analyze` rồi đo lại.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. **AST theo hàm** (`HEAD` với bản mới): chỉ phần canh lịch và `main` của `heartbeat_check.py` đổi, cộng
   các hàm mới. Dán kết quả.
2. **Bảng chính sách mã thoát cho cả 16 nhánh**, mỗi dòng có lý do một câu và **số dòng code** làm căn cứ.
3. **Phá thử**, mỗi lần ghi nguyên văn dòng đỏ, khôi phục, đối chiếu hash:
   - dùng `EXIT=` không neo đầu dòng → test phải đỏ vì đọc nhầm `ALERT_EXIT=`;
   - bỏ điều kiện chuyển trạng thái → test "lặp lại cùng mã thì im" đỏ;
   - canh cả mã `1` của chính `heartbeat` → test chống nhân đôi đỏ;
   - xoá chính sách của một nhánh → test bao phủ đỏ, nêu đúng tên nhánh.
4. **Chạy thật** `scripts/sched.sh heartbeat --dry-run` trên log thật của máy này: `EXIT=0`. Dán phần in ra
   liên quan tới mã thoát. Nếu nó phát hiện thất bại thật nào trong log hiện tại thì dán ra — đó là số đo,
   không phải lỗi.
5. `ruff` sạch. `uv run pytest -q` ≥ **1.775 passed** cộng số test mới, 0 failed.
6. `logs/alert_outbox_*` và `logs/.schedule_health_state.json` vẫn **không tồn tại** sau khi làm xong.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-156-canh-ma-thoat-job-theo-lich.md`: bảng chính sách kèm căn cứ,
số đo nguyên văn, brief sai ở đâu, cái gì không kiểm được.
