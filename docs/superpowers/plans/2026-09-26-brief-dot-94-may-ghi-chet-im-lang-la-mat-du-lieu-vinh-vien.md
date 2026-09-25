
# Brief đợt 94 — Máy ghi chết im lặng là mất dữ liệu vĩnh viễn

Ngày giao: 26/09/2026 (thứ Bảy).
Base: main `0b296f4`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Nên xong trước 08:40 thứ Hai 28/09** — đó là lần chạy tự động đầu tiên.

---

## 0. Khoảng trống, và vì sao nó nghiêm trọng hơn ở máy ghi

Tôi soát đường báo động của máy ghi. Hai cảnh báo trong nó (rơi về đường lùi, lưu lượng thấp) **có** tới
Telegram — `alert()` ở `trading/alerts.py:33-40` bắn Telegram cho mức WARN/CRITICAL. Chỗ đó ổn.

Nhưng nếu **tiến trình chết** thì không có gì cả. `scripts/run_if_docker_up.sh:104-106`:

```bash
RC=$?
echo "EXIT=$RC" >> "$LOG"
exit "$RC"
```

Nó **ghi** mã lỗi và truyền lên Task Scheduler, **không báo** ai. Đường Telegram duy nhất của lớp bọc này
là `docker_down_alert.py`, chỉ cho ca Docker không chạy.

Vậy nếu 08:41 thứ Hai máy ghi chết vì một traceback: log có `EXIT=1`, Task Scheduler ghi
`LastTaskResult=1`, và **không ai được thông báo**. Việc thu 20 phiên dừng im lặng.

**Vì sao ở máy ghi thì nghiêm trọng hơn các job khác:**

| Job khác | Máy ghi |
|---|---|
| Chạy lại mỗi 5 phút (heartbeat) hoặc mỗi ngày, lần sau bù được | Chạy **một lần mỗi ngày** |
| Dữ liệu vẫn nằm ở SSI, backfill lấy lại được | **SSI không lưu lịch sử sổ lệnh** — phiên đã trôi là mất vĩnh viễn |
| Hỏng = chậm biết | Hỏng = **mất một phiên không thể lấy lại** |

Đây chính là loại lỗi FEE-ALARM-2 nhắm tới, và nó nằm ở chỗ cái giá phải trả là cao nhất.

**Không sửa `run_if_docker_up.sh` để báo mọi mã khác 0.** Nhiều job dùng mã thoát khác 0 làm **tín hiệu có
chủ ý** và đã tự bắn Telegram rồi: `stream-health` thoát 1 khi độ phủ thấp, `daily_data_check` thoát 1/2,
`check_golive_gate` thoát 2. Báo thêm ở lớp bọc là bắn trùng và sẽ thành ồn.

---

## 1. Ràng buộc

- Được sửa: `scripts/record_vn30f_orderbook.py` (Task 1), `scripts/sched.sh` (Task 2), và các file test
  tương ứng. Được thêm: **một** script kiểm tra ở Task 2.
- **Không** sửa `run_if_docker_up.sh`, **không** sửa `trading/`, **không** sửa
  `verify_orderbook_file.py` (Task 2 **dùng lại** nó).
- **Không** restart/build container. **Không** đặt lệnh. Không commit, không push.
- Khôi phục sau kiểm thử phá hoại: sao lưu đúng file ra **ngoài** repo rồi copy lại. **Không**
  `git checkout`/`restore`/`stash` diện rộng.
- Nền hiện tại: **830 passed**, ruff sạch.

---

## Task 1 — Máy ghi phải kêu khi nó chết

1. **Kiểm trước:** máy ghi hiện đã có `try/except` ở tầng ngoài cùng chưa? Báo cáo tình trạng thật trước
   khi sửa.
2. Bọc toàn bộ phần thân chạy bằng `try/except Exception`, và khi có lỗi chưa xử lý → `alert("CRITICAL", ...)`
   nêu **loại lỗi, thông điệp, mã hợp đồng, và số tin đã ghi được tới lúc đó**, rồi thoát khác 0.
   Số tin đã ghi là thông tin quan trọng: nó cho biết mất cả phiên hay chỉ mất phần cuối.
3. **Dừng sớm ngoài ý muốn cũng phải kêu:** nếu tiến trình kết thúc mà **chưa tới `--until`** và **không**
   phải vì ngày không giao dịch → `alert("CRITICAL", ...)` nêu giờ dừng thật so với giờ đáng lẽ dừng.
   Đây là ca bắt được nhiều thứ mà `try/except` không bắt: bị kill, hết bộ nhớ, vòng kết nối lại bỏ cuộc.
4. **Không** kêu khi: hôm nay không phải ngày giao dịch (thoát 0 bình thường), hoặc dừng đúng `--until`.

**Kiểm chứng — tách hàm thuần quyết định "có nên báo dừng sớm không", test không cần mạng:**
- Dừng đúng `--until` → **không** báo.
- Dừng trước `--until` 3 giờ, là ngày giao dịch → **báo CRITICAL**.
- Không phải ngày giao dịch → **không** báo, dù dừng "sớm".
- **Ca biên:** dừng sau `--until` vài giây (bình thường, do làm tròn) → **không** báo.
- Lỗi chưa xử lý → có đúng 1 alert CRITICAL, và nêu đúng số tin đã ghi.
- **Kiểm thử phá hoại:** bỏ điều kiện ngày giao dịch, xác nhận **đúng ca 3** đỏ.

---

## Task 2 — Lớp thứ hai: kiểm mỗi chiều xem hôm nay có thu được dữ liệu không

Task 1 chỉ bắt được khi tiến trình **đã chạy rồi chết**. Nó **không** bắt được ca tiến trình **không bao giờ
khởi động** (Task Scheduler không chạy, Docker tắt, `.env` mất). Cần một lớp độc lập.

Viết `scripts/check_orderbook_daily.py`:
1. Nếu hôm nay **không** phải ngày giao dịch → thoát 0 im lặng (dùng `is_trading_day`, **không** tự viết lịch).
2. Xác định mã front-month hôm nay và đường dẫn file kỳ vọng
   `data/orderbook/<symbol>/<hôm nay>.jsonl.gz`.
3. **File không tồn tại** → `alert("CRITICAL", ...)` nêu rõ hôm nay là ngày giao dịch mà không có file nào.
   Thoát 2.
4. File tồn tại → **gọi lại `verify_orderbook_file.py`** (import hàm, **đừng chép logic**). Không đạt →
   `alert("WARN", ...)` nêu lý do không đạt (độ phủ bao nhiêu, thiếu mấy ô). Thoát 1.
5. Đạt → in tóm tắt, thoát 0, **không** bắn Telegram. Ngày thường không được có tin.

Thêm vào `sched.sh` một dispatcher `orderbook-daily-check`, bắt chước đúng khuôn mẫu các job có sẵn, log ra
`logs/orderbook-daily-check.log`.

**Giờ chạy: 15:30.** Lý do: sau khi máy ghi dừng (14:46) và sau khi `stream-health` chạy (15:10), nên không
đua với job nào — **đúng bài học đợt 92 Task 4**, nơi hai job đua nhau 42 giây và sinh ra một báo động đỏ sai.

**Tạo tác vụ Windows** `trading-orderbook-daily-check`, thứ Hai đến thứ Sáu 15:30, cùng khuôn mẫu
`wscript.exe //B //Nologo run_hidden.vbs`.

**Kiểm chứng:**
- Test hàm thuần: ngày không giao dịch → im lặng; file thiếu → CRITICAL + thoát 2; file có nhưng không đạt →
  WARN + thoát 1; file đạt → im lặng + thoát 0.
- **Chạy thử thật hôm nay (thứ Bảy):** phải thoát 0 im lặng, và tạo được log.
- Xác nhận tác vụ mới: `DaysOfWeek`, giờ, `NextRunTime` là **28/09 15:30**.
- Kiểm thử phá hoại: bỏ nhánh "file không tồn tại", xác nhận đúng test đó đỏ.

---

## 2. Không làm

- Không sửa `run_if_docker_up.sh` (báo mọi mã khác 0 sẽ bắn trùng với các job đã tự báo).
- Không sửa `verify_orderbook_file.py` — Task 2 import và dùng lại.
- Không sửa `trading/`. Không dùng lệnh git diện rộng.
- Không restart/build container, không đặt lệnh, không commit, không push.

## 3. Báo cáo cho Claude

1. **Task 1**: tình trạng `try/except` **trước** khi sửa; kết quả 5 nhóm test + kiểm thử phá hoại.
2. **Task 2**: kết quả test; output chạy thử thứ Bảy; thông tin tác vụ mới (`DaysOfWeek`, `NextRunTime`);
   kết quả kiểm thử phá hoại.
3. Xác nhận sao lưu ra ngoài repo, không dùng lệnh git diện rộng.
4. `uv run pytest -m "not integration" -q` (nền **830**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Ghi chú của planner

**Hai lớp cho cùng một lỗi là có chủ ý.** Task 1 bắt "chạy rồi chết", Task 2 bắt "không bao giờ chạy".
Không lớp nào bắt được cả hai. Cùng lý lẽ với đợt 92, nơi chuông trong tiến trình và công cụ đọc file sau
cùng bổ sung cho nhau.

**Thứ tự ưu tiên nếu không kịp cả hai trước thứ Hai:** làm **Task 2 trước**. Nó bắt được nhiều ca hơn (gồm
cả ca Task 1 bắt được, vì chết giữa phiên sẽ để lại file thiếu độ phủ), và nó không đụng vào máy ghi — thứ
sẽ chạy thật sáng thứ Hai. Sửa máy ghi ngay trước lần chạy tự động đầu tiên là thêm rủi ro vào đúng lúc
không nên.

**Việc chặn duy nhất vẫn là biểu phí phái sinh** — cần chủ dự án lấy từ SSI/HNX/VSD kèm nguồn.
