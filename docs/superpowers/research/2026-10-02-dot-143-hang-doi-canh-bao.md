# Đợt 143 — hàng đợi gửi lại cho `trading.alerts.alert` (báo cáo)

Ngày 02/10/2026. Chưa commit, chưa push. Không build container, không đụng `.env`, không gửi Telegram thật.

## Đã sửa gì

| File | Thay đổi |
|---|---|
| `trading/alerts.py` | Thêm `AlertOutbox`, `start_outbox`, `stop_outbox`. `alert()` đổi đúng một chỗ: nếu hàng đợi đã bật thì luồng nền gọi `box.send_or_queue`, không thì gọi `send_telegram` như cũ. |
| `trading/collector/main.py` | Import `start_outbox` và một dòng `start_outbox("collector")` trong `main()`, ngay sau `_configure_logging()`. |
| `trading/engine/main.py` | Tương tự, `start_outbox("engine")`. |
| `tests/test_alert_outbox.py` | Mới, 12 test. |

Không đụng `trading/telegram.py`, `scripts/`, `DEPLOYMENT.md`.

## GitNexus

`impact` trên `alert` (upstream, độ sâu 2):

```
risk: CRITICAL | impactedCount: 41 | direct: 31 | processes_affected: 8 | modules_affected: 5
Tests 30, Scripts 5, Collector 3, Engine 2, Storage 1
```

**Cảnh báo CRITICAL đã nêu với người dùng.** Hợp đồng của `alert()` giữ nguyên: cùng chữ ký, vẫn ghi log ngay, vẫn trả `Thread | None`, không ném. Khi không gọi `start_outbox` thì mã chạy y như trước.

`detect_changes` (unstaged): `risk_level: medium`, 3 symbol (`_log`, `_LEVELS`, `alert`), 3 luồng (`Main → Alert`, `On_stream_message → Alert`, `Sync_account_data → Alert`). Đúng phạm vi dự kiến.

## Thiết kế đã cài

- Gửi hỏng (`send_telegram` trả `False` hoặc ném) → thêm một dòng `{"emitted_at": <ISO có múi giờ>, "text": ...}` vào `alert_outbox_<dịch vụ>.jsonl`.
- Một luồng nền mỗi tiến trình, chu kỳ 60 giây. Lần đầu chạy **ngay khi khởi động** để gửi phần tồn từ lần trước. Gửi theo thứ tự, dừng ở tin đầu tiên còn hỏng, xoá từng tin đã gửi.
- Tiền tố `[GỬI TRỄ — phát lúc HH:MM:SS dd/mm]` theo giờ VN (UTC+7).
- Tối đa 200 tin, đầy thì bỏ tin cũ nhất, đếm số bỏ, lần gửi thành công kế tiếp có dòng `(đã bỏ N cảnh báo cũ vì hàng đợi đầy)`.
- Một `threading.Lock` cho mọi đọc/ghi file, ghi lại file bằng file tạm rồi `os.replace`. Thêm một lock riêng để chỉ có một lần gửi lại chạy tại một thời điểm.
- Dòng hỏng (không phải JSON hợp lệ) được **thay bằng một mục cảnh báo** `[CANH BAO HANG DOI] ... co dong hong ...` kèm 200 ký tự đầu của dòng đó, rồi gửi như tin thường. Không bỏ lặng lẽ, không mất dòng tốt.
- Thư mục hàng đợi không tồn tại (máy dev Windows không có `/app/logs`) → `start_outbox` trả `None` và không bật gì, hành vi y như cũ.

## Số đo (nguyên văn)

Test mới + test cũ của `alerts`: `19 passed in 9.06s`.

Bộ đầy đủ, chạy khi không có pytest nào khác (đã kiểm `Get-CimInstance`, rỗng sau khi loại chính lệnh kiểm):

```
1718 passed in 99.17s (0:01:39)
ruff: All checks passed!
docker compose config -q: OK
```

1718 = 1706 + 12 test mới. Đợt 142 chưa đổi mốc trước khi tôi chạy.

### Phá thử (băm trước = băm sau = `5bb791cf70a321b9`)

1. Bỏ `self.enqueue(text)` khi gửi hỏng:
   ```
   E       FileNotFoundError: [Errno 2] No such file or directory: '...\alert_outbox_test.jsonl'
   FAILED tests/test_alert_outbox.py::test_gui_hong_thi_dung_mot_dong_co_emitted_at_va_noi_dung
   1 failed, 1 passed
   ```
2. Gửi lại từ cuối (`head = lines[-1]`):
   ```
   E       AssertionError: assert ['tin3', 'tin2', 'tin1'] == ['tin1', 'tin2', 'tin3']
   FAILED tests/test_alert_outbox.py::test_mang_hoi_lai_gui_dung_thu_tu_co_tien_to_va_file_rong
   ```
3. Bỏ dòng "đã bỏ N" (`if dropped:` → `if False:`):
   ```
   E       AssertionError: assert 'đã bỏ 3 cảnh báo cũ vì hàng đợi đầy' in '[GỬI TRỄ — phát lúc 13:45:55 02/10] [WARN] t3'
   FAILED tests/test_alert_outbox.py::test_qua_200_tin_bo_tin_cu_nhat_va_lan_gui_ke_tiep_co_dong_da_bo
   ```

Phá thử 1 đỏ bằng `FileNotFoundError` chứ không phải `AssertionError`, vì test đọc file không có. Vẫn là đỏ đúng chỗ, nhưng dòng đỏ không phải câu so sánh.

### Chạy thật (không mạng, hàm gửi giả hỏng 2 lần rồi được)

Script ở `scratchpad/demo_outbox.py`, không commit.

```
TRUOC: False
  [fake send #1] HONG: [CRITICAL] phát hiện máy chủ ngủ/gián đoạn 953s (ngoài giờ giao dịch)
SAU alert (gui hong lan 1) - noi dung file:
{"emitted_at": "2026-10-02T06:46:33.213927+00:00", "text": "[CRITICAL] phát hiện máy chủ ngủ/gián đoạn 953s (ngoài giờ giao dịch)"}

  [fake send #2] HONG: [GỬI TRỄ — phát lúc 13:46:33 02/10] [CRITICAL] ...
flush #1 -> 0 tin da gui; file con: True
  [fake send #3] OK: [GỬI TRỄ — phát lúc 13:46:33 02/10] [CRITICAL] ...
flush #2 -> 1 tin da gui; file con: False
```

## Đề xuất cho `DEPLOYMENT.md`

> **Hàng đợi cảnh báo gửi hỏng.** Khi Telegram không gửi được (mất mạng, DNS hỏng), `alert()` của collector và engine không bỏ cảnh báo nữa mà ghi vào `./logs/alert_outbox_collector.jsonl` và `./logs/alert_outbox_engine.jsonl` (trong container là `/app/logs`). Mỗi dòng là một JSON `{"emitted_at", "text"}`. Mỗi 60 giây tiến trình thử gửi lại theo thứ tự, tin gửi trễ có tiền tố `[GỬI TRỄ — phát lúc HH:MM:SS dd/mm]` (giờ VN). Hàng đợi giữ tối đa 200 tin; đầy thì bỏ tin cũ nhất và tin kế tiếp báo "đã bỏ N cảnh báo cũ". File rỗng thì tự biến mất. Đọc bằng `cat logs/alert_outbox_*.jsonl`. Xoá được khi dịch vụ đang dừng; xoá lúc đang chạy cũng an toàn nhưng các tin chưa gửi sẽ mất. File nằm ngoài vòng xoay log, nhưng bị chặn ở 200 dòng nên không phình. Chỉ có hiệu lực sau khi build lại image; script theo lịch không dùng cơ chế này (chúng đã thoát mã 2 khi gửi hỏng).

## Brief sai / lệch ở đâu

1. **Vị trí lời gọi.** Brief nói "đầu phần chạy". Tôi đặt trong `main()`, **không** trong `run()`, vì test gọi thẳng `run()` và sẽ sinh luồng và file hàng đợi trong thư mục thật. Trong `main()` thì chỉ chạy khi khởi động tiến trình thật.
2. **Bộ đếm "đã bỏ N" chỉ nằm trong bộ nhớ.** Khởi động lại giữa lúc hàng đợi vừa tràn thì số này mất; brief không đòi bền, tôi không làm. Tin cũ vẫn được gửi, chỉ mất dòng đếm.
3. **Ngữ nghĩa "ít nhất một lần".** Nếu Telegram nhận tin nhưng tiến trình chết trước khi xoá dòng khỏi file thì tin gửi lặp lần nữa sau khởi động. Chấp nhận được với cảnh báo, ghi lại để biết.
4. **`pyright` báo** `Thread | None` không gán được cho `on_critical: () -> None` ở `collector/main.py` (dòng `lambda: alert(...)`). Lỗi có từ trước, không phải do đợt này, tôi không sửa.
5. `collector/main.py` trong working tree là CRLF (đã có từ trước, `git ls-files --eol`: `i/lf w/crlf`). `git diff` vẫn chỉ 3 dòng đổi nên không gây nhiễu.

## Không kiểm được

- Đường thật trong container sau rebuild (quyền ghi `/app/logs` bằng uid 10001 theo brief là đã đo, tôi **không** đo lại).
- Telegram thật, tức là gửi trễ có tới điện thoại chủ dự án hay không.
- Hành vi khi mạng chập chờn thật (DNS lỗi như 12 lần trong 72 giờ). Test chỉ dùng hàm gửi giả; test `test_tai_hien_su_co_953s...` tái hiện **nội dung và giờ**, không tái hiện mạng.
- Luồng nền chạy thật mỗi 60 giây: test chỉ kiểm lần chạy đầu (`first_flush_done`), chu kỳ 60 giây không được đo.

---

## Audit của Claude (02/10/2026, chiều)

### A.1. Kết luận: NHẬN, nhưng **KHÔNG build lại image** cho tới khi đợt 144 sửa lỗi chặn hàng đợi.

Code làm đúng brief. Lỗi dưới đây nằm trong **thiết kế Claude viết trong brief** ("dừng ở tin đầu tiên còn hỏng"), không phải lỗi của agent.

### A.2. Lỗi chặn hàng đợi vĩnh viễn — Claude tái hiện trên code thật

`send_telegram` trả `False` cho **mọi** thất bại, cả mất mạng lẫn Telegram từ chối tin (HTTP 400, vd tin dài quá 4.096 ký tự). `flush()` dừng ở tin đầu còn hỏng. Vậy một tin **không bao giờ gửi được** ở đầu hàng đợi sẽ chặn mọi tin sau nó. Vì file nằm trên đĩa, khởi động lại cũng không gỡ được.

Claude dùng hàm gửi giả bắt chước đúng giới hạn của Telegram:

```
hang doi sau khi mat mang: 3
  lan gui lai 1..5: gui duoc 0, con 3
da toi dich: []
do dai tin dau khi gui lai (co tien to GUI TRE): 4106
```

Chi tiết đáng sợ nhất: tin đầu dài 4.070 ký tự, **gửi được** nếu mạng có. Nó chỉ hỏng vì mất mạng. Sau đó chính tiền tố `[GỬI TRỄ — ...]` đẩy nó lên 4.106 ký tự, và nó trở thành vĩnh viễn không gửi được. Tin `lenh that bi tu choi` xếp sau thì không bao giờ tới.

Rủi ro thực tế hiện thấp: cảnh báo dài nhất trong log collector 72 giờ qua là **261 ký tự** (49 cảnh báo); engine không có cảnh báo nào. Nhưng hậu quả là **toàn bộ** cảnh báo sau đó im lặng, nên phải sửa trước khi đưa vào chạy thật.

### A.3. Đường thật trong image — phần agent ghi "không kiểm được"

Claude build một image riêng (`trading-audit143:tmp`, xoá ngay sau đó), không đụng container đang chạy (StartedAt giữ nguyên):

- **[1] `/app/logs` ghi được, uid 10001:** `start_outbox -> BAT`; gửi lần 1 hỏng → `alert_outbox_collector.jsonl` xuất hiện; lần 2 hỏng; lần 3 tới đích với `[GỬI TRỄ — phát lúc 13:52:33 02/10]`; file biến mất. Đây cũng là bằng chứng **chu kỳ gửi lại thật sự lặp** (interval 1 giây trong phép thử), phần agent ghi là chưa kiểm.
- **[2] `/app/logs` không ghi được (tmpfs của root, 755):** `alert()` **không ném**, in `LOI: khong ghi duoc hang doi canh bao (PermissionError)`. Nhưng `start_outbox` vẫn trả `BAT`, và **mọi tin hỏng sau đó vẫn mất**, chỉ để lại một dòng in. Giao đợt 144: kiểm quyền ghi lúc khởi động và báo to.

### A.4. Các điểm agent tự nêu — đồng ý

- Gọi `start_outbox` trong `main()` thay vì `run()`: đúng, để test gọi `run()` không tạo file thật.
- Bộ đếm "đã bỏ N" mất khi khởi động lại; có thể gửi lặp một tin nếu tiến trình chết giữa "đã gửi" và "đã xoá". Đều chấp nhận được (thà lặp còn hơn mất).
- `impact` trên `alert` = CRITICAL (31 hàm gọi trực tiếp, gồm `real_orders.py`). Hợp đồng `alert()` giữ nguyên (cùng chữ ký, cùng kiểu trả về, không ném). Claude đã đọc toàn bộ diff `collector/main.py` và `engine/main.py`: đúng một dòng import và một dòng `start_outbox(...)` mỗi file.

