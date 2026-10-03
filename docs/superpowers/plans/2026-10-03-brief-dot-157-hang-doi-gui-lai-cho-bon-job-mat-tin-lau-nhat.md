# Brief đợt 157 — hàng đợi gửi lại cho bốn job mất tin lâu nhất

## Bối cảnh

Đợt 155 làm hàng đợi gửi lại cho job theo lịch và nối cho **một** job: `heartbeat`. Hàm dùng chung đã có:
`scripts/_alert_common.py::send_with_outbox(text, send, outbox_path) -> bool` — gửi lại hàng tồn trước
(`flush`), rồi `send_or_queue` tin mới, trả `True` chỉ khi tin **mới** đã đi thật. Cron là cơ chế thử lại.

Đợt này nối cho bốn job còn lại **mất tin lâu nhất**:

| Job | Lịch | Mất một tin nghĩa là im lặng bao lâu |
|---|---|---|
| `daily-check` | 21:00 hằng ngày | 24 giờ — và đây là cảnh báo thiếu nến của cả phiên |
| `backup-check` | 03:00 hằng ngày | 24 giờ |
| `disk-check` | mỗi 6 giờ | 6 giờ |
| `restore-drill` | 04:00 Chủ nhật | **7 ngày** |

**Không làm trong đợt này** (lý do, không phải quên):
- `container-health` (10 phút), `engine-consumer` (5 phút), `deploy-drift`, `engine-cam`: cron thử lại
  nhanh, nên mất một tin là mất vài phút.
- `orderbook-recorder`, `orderbook-daily-check`: gửi qua `trading.alerts.alert()`, không phải
  `send_telegram` trực tiếp — cách nối khác, để đợt sau.

## Ràng buộc quan trọng nhất: **không được đổi mã thoát**

Đợt 156 (`cb2b56f`) vừa dựng bảng chính sách mã thoát cho 16 nhánh, và heartbeat canh theo đúng các mã đó.
Nếu đợt này đổi nghĩa mã thoát, bảng kia thành sai ngay.

Quy tắc, áp cho cả bốn job: **tin bị xếp hàng vẫn là tin CHƯA tới người.** Giữ y nguyên ý nghĩa hiện tại:

| Job | Hiện tại | Sau đợt này |
|---|---|---|
| `backup_check`, `disk_check`, `restore_drill` | `sent = send_telegram(msg)`; `sent` → trả 1; hỏng → trả **2** | thay bằng `send_with_outbox(...)`; trả `True` → 1; **xếp hàng → vẫn trả 2** |
| `daily_data_check` | `if send_telegram(...)` in "Đã gửi"/"KHÔNG gửi được", rồi thoát `code` bất kể | thay bằng `send_with_outbox(...)`; **giữ nguyên `code`**; đổi dòng in cho đúng ba trạng thái |

Đây là tương tác **có lợi** giữa hai đợt, phải nói rõ trong báo cáo: tin được hàng đợi giữ lại, **và**
heartbeat báo cho chủ dự án rằng job đó chưa gửi được (vì mã 2 nằm ngoài diện "bình thường" của ba job đầu
trong bảng đợt 156). Hai lớp, không trùng nhau.

Với `daily_data_check`, mã thoát **không** đổi theo việc gửi được hay không — đó là hành vi sẵn có. Đừng sửa.

**Một chỗ Claude đã sửa trước khi giao đợt này, để agent không hiểu nhầm:** mã 2 của `daily-check` mang
**hai** nghĩa, đo được trong `logs/daily-data-check.log`:
- 02/10 05:47 và 05:53 — sự cố dữ liệu nặng (0 mã có bar), và script **đã gửi Telegram thành công**;
- 02/10 09:33 và 09:42 — argparse chặn cờ lạ, **không ai báo**.

Bảng đợt 156 canh mã 2 của job này, nên ca thứ nhất sẽ có tin trùng. Claude đã viết lại phần lý do trong
`SCHEDULE_EXIT_POLICIES` cho đúng sự thật và ghi rõ đây là đánh đổi có chủ đích. **Đợt này không sửa chỗ đó**,
chỉ cần biết để đừng "dọn" nó.

## Việc 1 — thêm `--logs-dir` cho bốn script

**Không script nào trong bốn script này có `--logs-dir`** (Claude đã kiểm: cả bốn đều 0). Cần nó cho hai
việc: lấy đường dẫn hàng đợi, và để test trỏ vào `tmp_path`.

- Thêm `--logs-dir` theo đúng khuôn của `scripts/heartbeat_check.py` (có `DEFAULT_LOGS_DIR` suy từ vị trí
  file, không viết cứng).
- Tên file hàng đợi: `alert_outbox_<tên-job>.jsonl`, cùng khuôn đợt 143/155.
- Đường dẫn hàng đợi nằm **trên host**, trong `--logs-dir`. **Không** dùng `DEFAULT_OUTBOX_DIR` của
  `trading/alerts.py` (`/app/logs`, đường dẫn trong container).

## Việc 2 — nối `send_with_outbox` vào bốn chỗ gửi

Thay đúng bốn lời gọi: `backup_check.py:416`, `disk_check.py:189`, `restore_drill.py:369`,
`daily_data_check.py:304` (số dòng của `HEAD`; tự tìm lại, đừng tin số).

- **Không sửa `_alert_common.py`.** Nếu `send_with_outbox` thiếu gì thì **dừng và báo**.
- **Không sửa `trading/alerts.py`.**
- Giữ nguyên mọi dòng in hiện có về lý do cảnh báo. Thêm dòng nói rõ khi tin bị **xếp hàng** (khác với
  "gửi hỏng, mất luôn" — giờ nó không mất nữa).
- `--dry-run` của job nào có cờ đó phải **không** gửi và **không** tạo file hàng đợi, như hiện nay.

→ kiểm chứng bằng, cho **mỗi** job trong bốn job:

| Ca | Dàn dựng | Phải thấy |
|---|---|---|
| 1 | gửi được | mã thoát y như trước; **không** có file hàng đợi |
| 2 | gửi hỏng | mã thoát **y như trước** (2 với ba job đầu; `code` với `daily-check`); có file hàng đợi chứa đúng tin đó |
| 3 | ngay sau ca 2, lần chạy kế gửi được | người nhận được **tin cũ trước**, rồi tin mới; file hàng đợi **tự xoá** |
| 4 | `--dry-run` (job nào có) | không gửi, không tạo file hàng đợi |

Ca 3 là ca chứng minh giá trị của cả đợt. Mọi test dùng `tmp_path`.

## Việc 3 — ghim quy tắc, để đợt sau không phá

Thêm **một** test khẳng định: với cả bốn job, khi `send_with_outbox` trả `False` (tin bị xếp hàng), mã thoát
**không** đổi so với khi chưa có hàng đợi. Nêu rõ trong docstring test rằng bảng chính sách của đợt 156 phụ
thuộc vào điều này.

→ kiểm chứng bằng: phá thử coi "xếp hàng" là "đã gửi" (cho trả 1 thay vì 2) → test này đỏ, **và** cho biết
nó làm sai bảng đợt 156.

## Một thiết kế Claude đã cân nhắc và BÁC BỎ — đừng tự làm

Dùng **một file hàng đợi chung** cho mọi job theo lịch thì hấp dẫn: tin hỏng của `restore-drill` (7 ngày
mới chạy lại) sẽ được `container-health` gửi lại sau 10 phút. **Không làm.** `AlertOutbox` chỉ có
`threading.Lock` — khoá trong một tiến trình, không phải khoá file. Các job chạy chồng giờ nhau
(`engine-consumer` mỗi 5 phút, `container-health` mỗi 10 phút), nên file chung cần khoá file thật, là hạ
tầng mới và rủi ro mới. Đổi lại, cái giá phải ghi rõ trong báo cáo: **một tin hỏng của job hằng ngày phải
chờ tới lần chạy hôm sau**, và của `restore-drill` là tới Chủ nhật sau.

Nếu agent thấy một cách làm file chung **an toàn** mà Claude bỏ sót thì **báo lại, đừng tự làm**.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không sửa task, không build/restart container, không gửi Telegram thật,
  không chạy gì có `--send`.
- **Chỉ sửa:** `scripts/backup_check.py`, `scripts/disk_check.py`, `scripts/restore_drill.py`,
  `scripts/daily_data_check.py`, và test tương ứng. **Không** sửa `_alert_common.py`, `trading/alerts.py`,
  `heartbeat_check.py`, `sched.sh`, `run_if_docker_up.sh`.
- **`restore_drill` chạy thật trên DB:** chỉ được chạy nó ở chế độ khôi phục vào DB nháp như hiện tại.
  **Không** chạm DB `trading`. Nếu phải chạy thật để nghiệm thu thì dùng `--dry-run`.
- **Bốn job này chạy theo lịch từ cây làm việc**, gồm `backup-check` 03:00 và `disk-check` mỗi 6 giờ — tức
  **có thể chạy ngay trong lúc agent đang sửa**. Làm trong git worktree. Chỉ chép vào repo chính khi đã xong
  và test xanh, và **tránh các mốc 00/06/12/18 giờ cùng 03:00**. Sau khi chép, chạy ngay
  `scripts/sched.sh backup-check --dry-run` và `scripts/sched.sh disk-check --dry-run`, cả hai phải không
  traceback. Dán mã thoát.
- **Lưới an toàn đợt 148 chặn** test ghi vào `logs/` thật. Dùng `tmp_path`, đừng lách lưới.
- Sau khi xong, `logs/alert_outbox_*` phải **không tồn tại** (chưa có lần gửi nào hỏng). Dán kết quả.
- GitNexus: `impact` cho bốn hàm `main` trước khi sửa, `detect_changes` sau khi sửa; báo 0 thay đổi thì
  `npx gitnexus analyze` rồi đo lại.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. **AST theo hàm** (`HEAD` với bản mới): mỗi script chỉ `main` (và hàm dựng parser nếu có) đổi. Dán kết quả.
2. **Bảng bốn ca × bốn job** ở Việc 2, kèm mã thoát đo được của từng ca.
3. **Phá thử**, mỗi lần ghi nguyên văn dòng đỏ, khôi phục, đối chiếu hash:
   - coi "xếp hàng" là "đã gửi" → test Việc 3 đỏ;
   - bỏ `--logs-dir`, quay về đường dẫn cứng → test dùng `tmp_path` đỏ;
   - bỏ phần gửi lại hàng tồn → ca 3 đỏ ở ít nhất một job.
4. **Chạy thật** hai lệnh `--dry-run` nêu ở Giới hạn. Dán nguyên văn.
5. `ruff` sạch. `uv run pytest -q` ≥ **1.788 passed** cộng số test mới, 0 failed.
6. `logs/alert_outbox_*` không tồn tại.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-157-hang-doi-cho-bon-job.md`: bảng ca kiểm, cái giá của thiết kế
file riêng (tin hằng ngày chờ 24 giờ, `restore-drill` chờ 7 ngày), tương tác với bảng mã thoát đợt 156,
brief sai ở đâu, cái gì không kiểm được.
