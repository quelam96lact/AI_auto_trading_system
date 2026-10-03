# Brief đợt 155 — gửi Telegram hỏng không được ăn mất trạng thái "đã báo"

## Bối cảnh — Claude đo ngày 03/10, chỉ đọc

Đợt 143–144 làm hàng đợi gửi lại cho `trading.alerts.alert`, tức **engine và collector**. Claude vừa kiểm:
`start_outbox` được gọi thật trong `main()` của cả hai (`trading/engine/main.py:837`,
`trading/collector/main.py:521`), nên nửa đó đã kín.

**Nửa còn lại chưa làm gì cả.** 16 job theo lịch gọi `trading.telegram.send_telegram` trực tiếp. Hàm đó
không ném, chỉ trả `False` khi hỏng. Không có hàng đợi, không có gửi lại.

### Bằng chứng 1 — một cảnh báo CRITICAL thật đã mất

`logs/heartbeat.log`, ngày **16/09 11:55**:

```
[CRITICAL] Docker khong chay luc 11:55 ngay giao dich 16/09.
Collector/engine deu dung. Khong co bar moi, khong co lenh.
Cac job giam sat dang bi bo qua — day la tin nhan DUY NHAT ban se nhan.
[docker-down-alert] gui Telegram loi: URLError: <urlopen error [Errno 11001] getaddrinfo failed>
```

Tin tự nhận là "tin nhắn DUY NHẤT bạn sẽ nhận", và nó không đi. Lần chạy 12:00 gửi lại được, nên lần đó
thoát hiểm — nhưng chỉ vì `docker-down-alert` báo lại **mỗi lần chạy** khi Docker còn chết. Đó là may, không
phải thiết kế. Lỗi DNS kiểu này có thật và lặp lại: log collector 30/09–02/10 có 8 lần
`Temporary failure in name resolution` / `No address associated with hostname`.

### Bằng chứng 2 — lỗi thật trong chính chuông báo chết câm

`scripts/heartbeat_check.py` có ba chỗ gọi `send_telegram` và **bỏ qua giá trị trả về** (dòng 486, 538,
627). Hai trong ba chỗ đó lưu trạng thái canh lịch **vô điều kiện** ngay sau đó (dòng 539 và 628):

```python
send_telegram("\n".join(messages))                        # 627: ket qua bi bo qua
save_schedule_state(sched_state_file, new_sched_state)    # 628: luu bat ke gui duoc hay khong
```

Phần canh lịch (đợt 142) **chỉ báo khi chuyển trạng thái**. Dòng 246–253: khi `prev_status == "stale"` thì
chỉ in INFO `"đã báo trước đó"`, **không** cảnh báo nữa.

Ghép hai điều đó lại:

1. Một job theo lịch ngừng chạy.
2. Heartbeat phát hiện, soạn CRITICAL, gửi — và lần gửi đó hỏng.
3. Trạng thái vẫn được lưu là `stale`.
4. Từ đó về sau, job chết đó **im lặng vĩnh viễn**.

Đây đúng là sự im lặng mà đợt 142 được tạo ra để chặn, và nó nằm trong chính công cụ đó.

### Khuôn đúng đã có trong repo

- `scripts/container_health_check.py:571–581`: `sent = send_telegram(...)`; chỉ `save_state` khi `sent`;
  hỏng thì in lý do và trả 2.
- `scripts/engine_consumer_check.py:178–179`: chỉ cập nhật `last_alert_ts` khi gửi được.
- `scripts/docker_down_alert.py:145–147`: chỉ `_write_last_alert` khi `ok`.

`heartbeat_check.py` là ngoại lệ. **Không viết khuôn mới** — làm theo ba chỗ trên.

## Việc 1 — `heartbeat_check` không được ăn mất trạng thái khi gửi hỏng

Sửa cả ba chỗ gửi trong `scripts/heartbeat_check.py`:
- nhận giá trị trả về của `send_telegram`;
- gửi hỏng (trả `False` hoặc ném) thì **không** gọi `save_schedule_state`, và in một dòng dấu vết nêu rõ
  rằng cảnh báo **chưa** tới được, theo giọng `alert_and_fail` trong `_alert_common.py`
  (`GUI TELEGRAM HONG: ...`). Dùng `_print_safe`, vì stdout của job bị chuyển hướng ra file log.
- **Giữ nguyên mã thoát** (nhánh có phát hiện vẫn trả 1). `heartbeat` thuộc họ "theo phát hiện"; đổi sang 2
  sẽ đổi nghĩa mà task Windows đang đọc. Việc 2 lo phần không mất tin.
- Nhánh không có cảnh báo (dòng 631–632) giữ nguyên: không gửi gì thì không có gì hỏng.

→ kiểm chứng bằng: test trong `tests/test_heartbeat_check.py`, dùng `tmp_path` cho `--logs-dir` và
`--state-file`:

| Ca | Dàn dựng | Phải thấy |
|---|---|---|
| A — gửi hỏng không ăn trạng thái | một job stale, `send_telegram` trả `False` | file trạng thái **không được tạo/đổi**; stdout có dấu vết gửi hỏng; mã thoát vẫn 1 |
| B — chạy lại vẫn báo | ngay sau ca A, `send_telegram` trả `True` | vẫn gửi CRITICAL `NGỪNG CHẠY` cho đúng job đó (không bị nuốt thành "đã báo trước đó"); lúc này trạng thái **được** lưu |
| C — gửi được thì giữ nguyên hành vi cũ | một job stale, gửi `True`, rồi chạy lần hai | lần hai **không** gửi lại (vẫn chống lặp như đợt 142) |
| D — `send_telegram` ném | `send_telegram` ném `URLError` | không chết, không lưu trạng thái, có dấu vết, mã thoát 1 |

Ca B là ca quan trọng nhất: nó chứng minh job chết không bị mất tiếng. Ca C chứng minh không làm hỏng cơ
chế chống spam.

## Việc 2 — hàng đợi gửi lại cho job theo lịch, dùng lại đợt 143/144

`trading.alerts.AlertOutbox` đã có `send_or_queue`, `flush`, `pending`, `enqueue`, và **chạy được đồng bộ**
mà không cần luồng nền. Luồng nền 60 giây của `start_outbox` vô dụng với job cron (tiến trình thoát ngay),
nên **không dùng** `start_outbox` ở đây.

Thêm một hàm dùng chung vào `scripts/_alert_common.py`:

```
send_with_outbox(text, send, outbox_path) -> bool
```

- tạo `AlertOutbox(outbox_path, send_fn=send)`;
- **gửi lại hàng tồn trước** (`flush()`), vì cron chính là cơ chế thử lại: heartbeat chạy mỗi 5 phút;
- rồi `send_or_queue(text)` cho tin mới;
- trả `True` khi tin **mới** đã đi, `False` khi nó bị xếp hàng;
- in số tin còn tồn (`pending()`) khi khác 0, để log nói được là đang nợ tin.

**Không sửa `trading/alerts.py`.** Nếu `AlertOutbox` thiếu thứ gì cần thiết thì **dừng và báo**, đừng sửa nó.

Người dùng đầu tiên là **`heartbeat_check.py`**, và chỉ nó trong đợt này:
- đường dẫn hàng đợi nằm trong `--logs-dir` (job chạy trên host, `./logs`). **Không** dùng
  `DEFAULT_OUTBOX_DIR` của `trading/alerts.py`: đó là `/app/logs`, đường dẫn trong container.
- tên file theo đúng khuôn đợt 143 (`alert_outbox_<tên>.jsonl`), tên dịch vụ riêng cho job theo lịch để
  không lẫn với file của engine/collector.
- Việc 1 vẫn giữ nguyên: tin bị xếp hàng nghĩa là **chưa** tới người, nên trạng thái canh lịch **không**
  được lưu. Chỉ khi hàng đợi báo đã gửi được thì mới lưu.

→ kiểm chứng bằng: test cho `send_with_outbox` (gửi được; gửi hỏng thì xếp hàng; lần sau gửi được thì tin cũ
đi trước tin mới), cộng một test đầu-cuối cho `heartbeat_check`: lần một gửi hỏng, lần hai gửi được thì
**người nhận được cả tin của lần một**. Mọi test dùng `tmp_path`.

**Các job còn lại để đợt sau**, ghi vào báo cáo chứ không làm bây giờ: `backup_check`, `disk_check`,
`restore_drill`, `daily_data_check`, `check_orderbook_daily`, `host_preflight` (nhóm mỗi ngày hoặc mỗi tuần,
nên mất tin là mất 24 giờ tới 7 ngày), và `docker_down_alert`, `container_health_check`,
`engine_consumer_check`, `deploy_drift_check`, `check_silent_engine` (nhóm chạy dày, cron đã thử lại giúp).

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không sửa task, không build/restart container, không gửi Telegram thật.
- **Chỉ sửa:** `scripts/heartbeat_check.py`, `scripts/_alert_common.py` (thêm một hàm), và test tương ứng.
  Không sửa `trading/alerts.py`, `trading/telegram.py`, hay 15 script còn lại.
- **`heartbeat_check.py` chạy thẳng từ cây làm việc**, mỗi 5 phút trong giờ giao dịch, và 08:00–15:00 thứ
  Hai 05/10 là phiên kế tiếp. Làm trong git worktree, chỉ chép vào repo chính **trước 08:00 thứ Hai**, và
  ngay sau khi chép thì chạy `scripts/sched.sh heartbeat --dry-run`, phải `EXIT=0`, không traceback.
- **Lưới an toàn đợt 148 sẽ chặn** mọi test ghi vào `logs/` thật. Đừng tìm cách lách nó; dùng `tmp_path`.
- **Không** tạo file hàng đợi thật trong `logs/` khi chạy thử. Hiện `logs/alert_outbox_*` **không tồn tại**
  (Claude đã kiểm); sau đợt này nó vẫn phải không tồn tại, vì chưa có lần gửi nào hỏng.
- GitNexus: `impact` cho `save_schedule_state` và `alert_and_fail` trước khi sửa; `detect_changes` sau khi
  sửa. Báo 0 thay đổi thì `npx gitnexus analyze` rồi đo lại.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. **AST theo hàm** (`HEAD` với bản mới): `heartbeat_check.py` chỉ `main` khác; `_alert_common.py` chỉ có
   thêm hàm mới, không hàm cũ nào khác. Dán kết quả.
2. **Phá thử**, mỗi lần ghi nguyên văn dòng đỏ, khôi phục, đối chiếu hash:
   - trả `save_schedule_state` về chỗ cũ (lưu vô điều kiện) → ca A và ca B đỏ;
   - bỏ `flush()` trong `send_with_outbox` → test "tin cũ đi trước tin mới" đỏ;
   - coi tin bị xếp hàng là đã gửi (trả `True`) → ca B đỏ.
3. **Chạy thật `scripts/sched.sh heartbeat --dry-run`**: `EXIT=0`. Dán dòng log. Ở `--dry-run` không được
   gửi gì và không được ghi trạng thái, như hiện nay.
4. `ruff` sạch. `uv run pytest -q` ≥ **1.763 passed** cộng số test mới, 0 failed.
5. `logs/alert_outbox_*` vẫn không tồn tại sau khi làm xong. Dán kết quả liệt kê.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-155-gui-hong-khong-an-mat-trang-thai.md`: số đo nguyên văn, danh
sách job còn lại kèm nhóm, brief sai ở đâu, cái gì không kiểm được.
