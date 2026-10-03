# Brief đợt 158 — gom `DEFAULT_LOGS_DIR` và tên file hàng đợi về một chỗ

## Vì sao

Claude tự rà sau đợt 157 và thấy mình để trùng lặp mọc lại, đúng thứ đợt 152 vừa dọn.

Năm script giờ mỗi cái tự định nghĩa `DEFAULT_LOGS_DIR`, và **chúng không viết giống nhau**:

```
scripts/backup_check.py:50      DEFAULT_LOGS_DIR = os.path.join(
scripts/disk_check.py:43        DEFAULT_LOGS_DIR = os.path.join(
scripts/heartbeat_check.py:84   DEFAULT_LOGS_DIR = os.path.join(
scripts/restore_drill.py:65     DEFAULT_LOGS_DIR = os.path.join(
scripts/daily_data_check.py:35  DEFAULT_LOGS_DIR = str(Path(__file__).resolve().parents[1] / "logs")
```

Bốn bản dùng `os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")`, bản thứ
năm dùng `pathlib`. Cùng một giá trị, hai cách viết — **đã bắt đầu lệch**. Đợt 152 gom sáu bản sao của
`_load_dotenv` vì đúng lý do này; để nguyên thì vài đợt nữa sẽ có bản thứ sáu, thứ bảy.

Thêm nữa, mỗi script tự khai một hằng số tên file hàng đợi (`OUTBOX_NAME`), và cả năm đều theo cùng một
khuôn `alert_outbox_<tên-job>.jsonl`. Khuôn đó xứng đáng có một chỗ duy nhất, vì `DEPLOYMENT.md` §8.6 mô tả
nó như một quy ước.

**Đợt này không đổi một hành vi nào.** Mọi đường dẫn tính ra phải y hệt trước.

## Việc 1 — một nguồn duy nhất cho thư mục logs

Thêm vào `scripts/_db_common.py` (nơi đã giữ `load_dotenv` và `resolve_dsn` dùng chung — **đúng chỗ theo
tiền lệ đợt 152**):

- một hằng số hoặc hàm trả **thư mục logs ở gốc repo**, tính từ vị trí file, không từ thư mục đang đứng.

Rồi năm script trên dùng nó thay cho bản riêng. **Phải giữ nguyên tên `DEFAULT_LOGS_DIR` trong từng module** (gán bằng giá trị dùng
chung). Claude đã kiểm: `tests/test_heartbeat_check.py` tham chiếu `hc.DEFAULT_LOGS_DIR` ở dòng 677, 683 và
724, và `hc.HEARTBEAT_OUTBOX_NAME` ở dòng 937, 1013, 1043. Xoá tên khỏi module là làm vỡ các test đó.

→ kiểm chứng bằng: một test khẳng định cả năm module cho ra **cùng một** đường dẫn, và đường dẫn đó bằng
`<gốc repo>/logs`. Thêm một test chạy từ **thư mục khác** (đổi `cwd` sang `tmp_path`) mà giá trị không đổi —
đó là tính chất thật sự quan trọng, vì job cron chạy với `cwd` do `sched.sh` đặt.

## Việc 2 — một nguồn duy nhất cho tên file hàng đợi

Thêm một hàm vào `scripts/_alert_common.py` (nơi đã có `send_with_outbox`) trả đường dẫn hàng đợi cho một
job, theo khuôn `alert_outbox_<tên-job>.jsonl`.

Năm script dùng nó. **Tên file tính ra phải không đổi**, gồm cả `heartbeat` (hiện là
`alert_outbox_heartbeat.jsonl`, lấy từ `HEARTBEAT_OUTBOX_NAME`).

→ kiểm chứng bằng: test liệt kê năm job và khẳng định tên file **nguyên văn** như hiện tại. Viết thẳng năm
tên mong đợi vào test, đừng sinh lại bằng cùng công thức — nếu test dùng lại chính công thức đang kiểm thì
nó không chứng minh gì (bài học đợt 157: phép ghim trùng số với lỗi thì vô hiệu).

## Việc 3 — chứng minh không đổi hành vi

Trước khi sửa, ghi lại đường dẫn hàng đợi và `DEFAULT_LOGS_DIR` của cả năm script bằng cách import module
và in ra. Sau khi sửa, in lại. **Hai bảng phải trùng từng ký tự.** Dán cả hai vào báo cáo.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không sửa task, không build/restart container, không gửi Telegram thật.
- **Chỉ sửa:** `scripts/_db_common.py`, `scripts/_alert_common.py`, và năm script
  (`heartbeat_check.py`, `backup_check.py`, `disk_check.py`, `restore_drill.py`, `daily_data_check.py`),
  cùng test tương ứng. **Không** sửa `trading/alerts.py`, `sched.sh`, `run_if_docker_up.sh`.
- **Không đổi mã thoát của bất kỳ job nào.** Bảng chính sách đợt 156 và phép ghim đợt 157 dựa vào chúng.
- **`_db_common.py` được 69 file trong `scripts/` import** (Claude đếm 04/10). Chỉ **thêm**, không đổi và không xoá thứ gì đang
  có trong đó. Nếu thấy cần đổi, **dừng và báo**.
- **Năm job này chạy theo lịch từ cây làm việc.** Làm trong git worktree. Chép vào repo chính **ngoài** các
  mốc: 00/06/12/18 giờ (`disk-check`), 02:00 và 03:00 (`backup`, `backup-check`), 21:00 (`daily-check`),
  04:00 Chủ nhật (`restore-drill`), và **ngoài 08:00–15:00 ngày giao dịch** (`heartbeat` mỗi 5 phút).
  Phiên kế tiếp là **thứ Hai 05/10**. An toàn nhất: chép trong hôm nay, Chủ nhật 04/10, tránh các mốc trên.
- Sau khi chép, chạy ngay và dán mã thoát: `scripts/sched.sh heartbeat --dry-run`,
  `scripts/sched.sh backup-check --dry-run`, `scripts/sched.sh disk-check --dry-run`. Không traceback.
- **Lưới an toàn đợt 148 chặn** test ghi vào `logs/` thật. Dùng `tmp_path`.
- Sau khi xong, `logs/alert_outbox_*` phải **không tồn tại**. Dán kết quả.
- GitNexus: `impact` cho `load_dotenv`/`resolve_dsn` trước khi sửa (chỉ để biết blast radius),
  `detect_changes` sau khi sửa. MCP chết thì dùng CLI `npx --no-install gitnexus ... --repo
  AI_auto_trading_system`; vẫn không được thì ghi "không chạy được" và thay bằng so AST theo hàm.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. `grep -rn "DEFAULT_LOGS_DIR = " scripts/*.py` chỉ còn **một** dòng định nghĩa thật (các module khác gán
   lại từ nguồn chung thì nêu rõ). Dán kết quả.
2. **Bảng trước/sau của Việc 3 trùng từng ký tự.**
3. **AST theo hàm**: ở năm script, **không hàm nào** đổi — chỉ phần thân module (import và hằng số). Đây là
   tiêu chí mạnh nhất của đợt này; nếu một hàm nào đổi thì phạm vi đã sai.
4. **Phá thử**, mỗi lần ghi nguyên văn dòng đỏ, khôi phục, đối chiếu hash:
   - đổi nguồn chung thành đường dẫn tương đối theo `cwd` → test "chạy từ thư mục khác" đỏ;
   - đổi khuôn tên file (vd bỏ dấu gạch) → test tên nguyên văn đỏ, nêu đúng job nào.
5. `ruff` sạch. `uv run pytest -q` ≥ **1.813 passed** cộng số test mới, 0 failed.

## Báo cáo

`docs/superpowers/research/2026-10-04-dot-158-gom-duong-dan-logs.md`: hai bảng trước/sau, kết quả AST, brief
sai ở đâu, cái gì không kiểm được.
