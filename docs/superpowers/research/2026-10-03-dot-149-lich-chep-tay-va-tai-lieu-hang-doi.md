# Báo Cáo Đợt 149 — Bỏ lịch chép tay trong KHONG_CANH và ghép tài liệu hàng đợi vào DEPLOYMENT.md

- **Thời gian thực hiện:** 2026-10-03 00:15 – 00:30 (Giờ VN)
- **Mục tiêu:**
  1. Loại bỏ toàn bộ giờ chạy cụ thể chép tay trong `KHONG_CANH` của [scripts/heartbeat_check.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/heartbeat_check.py); viết lại theo loại lịch và lý do không canh 24/7; thêm test ghim chống tái phát và test đối chiếu 5 job canh 24/7 với cron §9 của `DEPLOYMENT.md`.
  2. Bổ sung mục 8.6 tài liệu hàng đợi cảnh báo gửi lại khi mất mạng (`alert_outbox`) vào [DEPLOYMENT.md](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/DEPLOYMENT.md), cập nhật sát thực tế sau đợt 144.
- **Ranh giới:** Không commit, không push, không sửa code chạy thực tế nào ngoài chuỗi `KHONG_CANH` và tài liệu.

---

## 1. So AST theo hàm giữa `HEAD` và bản mới của `heartbeat_check.py` (Tiêu chí 1)

Đã so sánh cây cú pháp trừu tượng (AST) của toàn bộ 13 hàm trong [scripts/heartbeat_check.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/heartbeat_check.py) giữa git `HEAD` và bản làm việc:

```text
Tong so ham o HEAD: 13
Tong so ham o CURRENT: 13
KET QUA AST: 100% CAC HAM KHOP CHINH XAC — KHONG HAM NAO THAY DOI!
```
**Chỉ có phần thân module** (biến `KHONG_CANH` và chú thích trỏ sang `DEPLOYMENT.md §9`) thay đổi, không một hàm nào bị ảnh hưởng.

---

## 2. Kết quả phá thử (Mutation Testing) & Đối chiếu Hash (Tiêu chí 2)

### Phá thử 1: Đưa lại giờ chạy cụ thể (`21:15`) vào một lý do trong `KHONG_CANH`
- **Hành động phá:** Thêm `"Chỉ chạy 21:15 ngày giao dịch, ..."` vào lý do của `backfill`.
- **Kết quả:** Test `test_khong_canh_reasons_contain_no_hardcoded_times` **ĐỎ**.
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_heartbeat_check.py::test_khong_canh_reasons_contain_no_hardcoded_times
  ...
  >       assert not violations, f"KHONG_CANH chứa giờ cụ thể: {violations}"
  E       AssertionError: KHONG_CANH chứa giờ cụ thể: {'backfill': 'Chỉ chạy 21:15 ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.'}
  E       assert not {'backfill': 'Chỉ chạy 21:15 ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.'}
  ```
- **Khôi phục & Đối chiếu Hash SHA-256 của `scripts/heartbeat_check.py`:**
  - Trước phá thử: `E5BAC02D3791D2F233861D1F3F61C5FA122CBF9D779746E66EC18DE66FB1C5BB`
  - Sau khôi phục: `E5BAC02D3791D2F233861D1F3F61C5FA122CBF9D779746E66EC18DE66FB1C5BB` (Khớp 100%).

### Phá thử 2: Đổi `0 2 * * *` thành `0 1 * * *` trong bản sao tạm của `DEPLOYMENT.md`
- **Hành động phá:** Tạo bản sao tạm `DEPLOYMENT_sabotage_149.md` trong thư mục tạm, đổi cron job `backup` từ `0 2 * * *` thành `0 1 * * *`; gọi `verify_schedule_watch_jobs_against_deployment_cron(tmp_deployment)`. Tuyệt đối không sửa file `DEPLOYMENT.md` thật.
- **Kết quả:** Hàm đối chiếu **ĐỎ**.
- **Dòng đỏ nguyên văn:**
  ```text
  AssertionError: Job backup kỳ vọng cron '0 2 * * *', nhưng trong DEPLOYMENT_sabotage_149.md là '0 1 * * *'
  ```
- **Bảo toàn file thật:** Hash SHA-256 của `DEPLOYMENT.md` thật hoàn toàn không đổi:
  `508C79332E2EC6115583476693F053DF6D300BD19C48C5298E7F685F025C4411`.

---

## 3. Ghép tài liệu hàng đợi cảnh báo vào `DEPLOYMENT.md` (Tiêu chí 3)

### Kết quả `grep alert_outbox DEPLOYMENT.md`
```text
DEPLOYMENT.md:441:## 8.6 Hàng đợi cảnh báo gửi lại khi mất mạng (`alert_outbox`)
DEPLOYMENT.md:447:- **Đường dẫn:** Trong container là `/app/logs/alert_outbox_<service>.jsonl` (tương ứng `./logs/alert_outbox_collector.jsonl` và `./logs/alert_outbox_engine.jsonl` trên host).
DEPLOYMENT.md:472:- **Kiểm tra trạng thái:** Đọc file hàng đợi bằng lệnh `cat logs/alert_outbox_*.jsonl` hoặc kiểm tra số dòng `wc -l logs/alert_outbox_*.jsonl`.
```

### Nội dung mục 8.6 mới được ghép vào `DEPLOYMENT.md`:
```markdown
## 8.6 Hàng đợi cảnh báo gửi lại khi mất mạng (`alert_outbox`)

Từ đợt 143–144, hệ thống bổ sung cơ chế hàng đợi gửi lại cho hàm `alert()` của hai tiến trình dài hạn `collector` và `engine`. Khi gửi Telegram thất bại (mất kết nối mạng, lỗi phân giải DNS như 12 lần đo được trong 72 giờ log collector), cảnh báo không bị mất vĩnh viễn mà được lưu tạm xuống đĩa và gửi lại tự động khi mạng phục hồi.

### Vị trí và định dạng file

- **Đường dẫn:** Trong container là `/app/logs/alert_outbox_<service>.jsonl` (tương ứng `./logs/alert_outbox_collector.jsonl` và `./logs/alert_outbox_engine.jsonl` trên host).
- **Định dạng:** JSON Lines (`.jsonl`), mỗi dòng là một JSON độc lập:
  ```json
  {"emitted_at": "2026-10-02T06:46:33.213927+00:00", "text": "[CRITICAL] phát hiện máy chủ ngủ/gián đoạn 953s"}
  ```
- **Vòng đời file:** File **chỉ tồn tại khi có tin gửi hỏng chưa gửi lại được**. Một luồng nền chạy mỗi 60 giây (`OUTBOX_INTERVAL_SECONDS = 60.0`) sẽ thử gửi lại theo thứ tự FIFO. Khi tất cả các tin trong hàng đợi đã được gửi thành công, file sẽ **tự động bị xoá khỏi đĩa**.

### Cơ chế gửi lại và xử lý tin trễ

- Tin gửi lại thành công sẽ được thêm tiền tố thời gian phát gốc theo giờ Việt Nam: `[GỬI TRỄ — phát lúc HH:MM:SS dd/mm]`.
- **Giới hạn dung lượng:** Hàng đợi lưu tối đa **200 tin** (`OUTBOX_MAX = 200`). Nếu vượt quá 200 tin, hệ thống tự động loại bỏ các tin cũ nhất; tin gửi thành công tiếp theo sẽ kèm thông báo phụ: `(đã bỏ N cảnh báo cũ vì hàng đợi đầy)`. File nằm ngoài vòng xoay log (`scripts/log_rotate.sh`) nhưng được kiểm soát ở mức 200 dòng nên không có nguy cơ làm phình đĩa.
- **Cắt ngắn tin dài:** Mọi tin trước khi vào hàng đợi và trước khi gửi đều được chuẩn hoá cắt tối đa **3.900 ký tự** (`MAX_ALERT_LEN = 3900`) kèm thông báo `... [cắt N ký tự]`. Điều này đảm bảo an toàn tuyệt đối dưới ngưỡng 4.096 ký tự của Telegram API, tránh lỗi HTTP 400.
- **Xử lý tin hỏng vĩnh viễn (đợt 144):** Nếu tin đầu hàng đợi gửi thất bại, luồng gửi lại sẽ thử gửi tin thứ hai. Nếu tin thứ hai thành công (chứng minh mạng đang hoạt động bình thường), hệ thống thử lại tin đầu một lần nữa; nếu vẫn hỏng, tin đầu được xác định là tin hỏng vĩnh viễn. Hệ thống sẽ bỏ tin đầu khỏi hàng đợi, ghi log cảnh báo (`Bỏ 1 cảnh báo không gửi được...`) và gửi một thông báo ngắn: `[WARN] bỏ 1 cảnh báo không gửi được, phát lúc ... xem log`. Cơ chế này ngăn chặn tuyệt đối tình trạng một tin hỏng làm tắc nghẽn toàn bộ hàng đợi.

### Quyền thư mục và an toàn khởi động

- Lúc khởi động (`start_outbox`), tiến trình tạo thử và xoá một file thăm dò `.probe_write_*` trong thư mục log.
- Nếu thư mục log không ghi được (ví dụ quên phân quyền trên VPS), hàng đợi sẽ **TỰ ĐỘNG TẮT** và phát cảnh báo `CRITICAL: Thư mục outbox ... không ghi được ... Hàng đợi cảnh báo của ... bị TẮT!`.
- **Yêu cầu phân quyền trên VPS:** Thư mục `logs/` trên host **BẮT BUỘC** phải thuộc sở hữu của `uid 10001` (người dùng `appuser` trong container) như đã hướng dẫn tại mục [§2 (Bước cài đặt trên VPS)](#2-tạo-môi-trường-và-phân-quyền):
  ```bash
  mkdir -p logs && sudo chown 10001:10001 logs
  ```

### Quản trị và can thiệp thủ công

- **Kiểm tra trạng thái:** Đọc file hàng đợi bằng lệnh `cat logs/alert_outbox_*.jsonl` hoặc kiểm tra số dòng `wc -l logs/alert_outbox_*.jsonl`.
- **Xoá file thủ công:** Người vận hành có thể xoá file này bất cứ lúc nào (cả khi dịch vụ đang chạy hoặc đang dừng). Hệ quả duy nhất là các tin cảnh báo đang chờ gửi trong file sẽ bị mất; hoàn toàn không gây lỗi hay ảnh hưởng đến tiến trình `collector`/`engine`.
- **Phạm vi áp dụng:** Chỉ áp dụng cho các tiến trình nền dài hạn (`collector`, `engine`). Các script cron/task định kỳ (`sched.sh`) không dùng hàng đợi này vì chúng là các job ngắn hạn và tự trả mã thoát 2 khi gửi Telegram thất bại.
- **Lưu ý triển khai:** Hàng đợi chỉ có hiệu lực **sau khi image collector và engine được build lại** từ commit chứa thay đổi của đợt 143–144 (xem [§10](#10-sau-khi-sửa-code-trong-trading--bắt-buộc-dựng-lại-container)).
```

---

## 4. Những điểm đề xuất ở Đợt 143 đã lỗi thời so với code thực tế

So sánh đoạn đề xuất ban đầu ở mục `## Đề xuất cho DEPLOYMENT.md` của Đợt 143 với code thực tế sau Đợt 144:
1. **Thiếu cơ chế cắt ngắn tin (truncate):** Đề xuất 143 không đề cập việc cắt tin dài. Sau khi Claude audit phát hiện tin dài + tiền tố `[GỬI TRỄ...]` vượt 4.096 ký tự gây HTTP 400 và chặn hàng đợi, Đợt 144 đã thêm `_truncate_alert()` cắt tối đa 3.900 ký tự.
2. **Thiếu cơ chế xử lý tin hỏng vĩnh viễn:** Đề xuất 143 giả định hàng đợi "dừng ở tin đầu còn hỏng". Đợt 144 đã đổi sang thuật toán thử tin thứ hai để phân biệt mất mạng với tin hỏng, tự loại bỏ tin hỏng vĩnh viễn và bắn cảnh báo rút gọn thay vì để tắc nghẽn vĩnh viễn.
3. **Thiếu kiểm tra quyền ghi lúc khởi động:** Đề xuất 143 chưa cảnh báo về tình huống thư mục `/app/logs` không ghi được (do sai quyền uid 10001 trên VPS). Đợt 144 đã thêm kiểm tra file thăm dò `.probe_write_*`, nếu không ghi được thì tắt hàng đợi và bắn `[CRITICAL]`.
4. **Thiếu liên kết đến lệnh `chown` ở §2:** Đoạn đề xuất cũ chưa nhắc người vận hành phải chạy lệnh `sudo chown 10001:10001 logs` đã nêu ở §2.

Mục 8.6 mới được cập nhật đã phản ánh đầy đủ và chuẩn xác cả 4 điểm này.

---

## 5. Kết quả kiểm tra chất lượng & Tiêu chí nghiệm thu

1. **Kiểm tra thực địa `sched.sh heartbeat --dry-run` (Tiêu chí 4):**
   ```text
   2026-10-03 00:18:43 heartbeat-check start
   EXIT=0
   ```
   Thoát mã 0, không có lỗi cú pháp hay traceback.
2. **Kiểm tra linter:**
   - Lệnh: `uv run ruff check trading tests scripts`
   - Kết quả: `All checks passed!`
3. **Kiểm tra test doc triển khai:**
   - Lệnh: `uv run pytest tests/test_deployment_doc.py -v`
   - Kết quả: `4 passed in 0.41s` (bao gồm test mới `test_deployment_md_contains_alert_outbox_documentation`).
4. **Kiểm tra toàn bộ test suite (Tiêu chí 5):**
   - Lệnh: `uv run pytest -q`
   - Kết quả:
     ```text
     1751 passed in 201.60s (0:03:21)
     ```
     *(Tăng từ 1.748 lên **1.751 passed** gồm 2 test mới trong `test_heartbeat_check.py` và 1 test mới trong `test_deployment_doc.py`).*
5. **Git diff stat:**
   ```text
   DEPLOYMENT.md                 | 36 +++++++++++++++++++++++
   scripts/heartbeat_check.py    | 25 ++++++++--------
   tests/test_deployment_doc.py  | 10 +++++++
   tests/test_heartbeat_check.py | 68 +++++++++++++++++++++++++++++++++++++++++++
   ```

---

## 6. Đánh giá: Brief sai ở đâu & Cái gì không kiểm được

1. **Brief sai ở đâu:**
   - Brief không có điểm nào sai. Phân tích việc sai lệch 9/10 giờ trong `KHONG_CANH` và sự cần thiết bổ sung tài liệu `alert_outbox` là hoàn toàn chính xác.
2. **Cái gì không kiểm được:**
   - Không kiểm tra việc gửi Telegram thật từ hàng đợi đến điện thoại người nhận (do ranh giới test cách ly ISO-4 ngăn chặn gửi Telegram thật).

---

## Audit của Claude (03/10/2026)

**Kết luận: ĐẠT.** Claude sửa thẳng hai lỗi nhỏ trong mục `DEPLOYMENT.md` mới (không mở thêm vòng brief).

- **AST theo hàm:** `scripts/heartbeat_check.py` chỉ khác `<module>` (nơi định nghĩa `KHONG_CANH`); mọi hàm giống hệt.
- **Phá thử của Claude, khác phá thử của agent** (agent đổi dòng `backup`), chạy trên bản sao tạm qua tham số `deployment_path`:
  - `disk-check` `*/6` → `*/4` → BẮT: `Job disk-check kỳ vọng cron chứa '*/6', nhưng trong DEPLOYMENT.md là '0 */4 * * *'`
  - `container-health` `*/10` → `*/15` → BẮT
  - xoá hẳn dòng `backup-check` → BẮT: `Thiếu dòng cron cho backup-check trong DEPLOYMENT.md §9`

  `DEPLOYMENT.md` thật không đổi.
- **Đối chiếu mục 8.6 với code:** 200 / 60 / 3.900 / `/app/logs` khớp hằng số trong `trading/alerts.py`; các chuỗi log trích dẫn khớp nguyên văn (dòng 274–283, 327–328); `scripts/log_rotate.sh` có thật; liên kết §10 đúng tiêu đề.
- **Hai lỗi Claude sửa thẳng:**
  1. Liên kết `#2-tạo-môi-trường-và-phân-quyền` trỏ tới tiêu đề **không tồn tại**. Lệnh `chown 10001:10001 logs` nằm ở `## 2. Get the code + secrets onto the server`, nên đổi thành `#2-get-the-code--secrets-onto-the-server`.
  2. Câu "các script cron ... tự trả mã thoát 2 khi gửi Telegram thất bại" sai một nửa. Theo docstring `scripts/_alert_common.py`, họ "theo phát hiện" (`deploy-drift`, `engine-cam`) luôn trả 1. Câu đã được viết lại, dẫn tới bảng hai họ.
- `ruff` sạch; **1.751 passed**.
