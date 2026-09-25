# Brief đợt 92 — Thử chuỗi lịch end-to-end, và công cụ nghiệm thu file sổ lệnh

Ngày giao: 26/09/2026 (thứ Bảy).
Base: main `f54666c`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Task 1 làm HÔM NAY (thứ Bảy) — đây là cửa sổ an toàn duy nhất.** Task 2 làm cuối tuần. Task 3 chạy
chiều thứ Hai.

---

## 0. Hai khoảng trống tôi tìm ra khi soát lại

**Khoảng trống 1 — chuỗi lịch chưa từng chạy thật.** Tôi kiểm lúc 05:06 hôm nay:

```
LastRunTime    : 11/30/1999 12:00:00 AM     <- chua bao gio chay
LastTaskResult : 267011                     <- "task has not yet run"
NextRunTime    : 9/28/2026 8:40:00 AM
logs/orderbook-recorder.log                 <- KHONG TON TAI
```

Đợt 90 chỉ thử `scripts/sched.sh orderbook-recorder` **trực tiếp**. Chuỗi thật còn ba tầng nữa chưa ai
chạy: `Task Scheduler → wscript.exe → run_hidden.vbs → sched.sh`. Nếu một tầng truyền tham số sai, **thứ
Hai 08:40 sẽ hỏng và không ai biết** — tác vụ chạy ẩn, không có cửa sổ, và log thì chưa từng được tạo nên
không có gì để so.

**Hôm nay là thứ Bảy, nên đây là cửa sổ thử hoàn hảo:** máy ghi sẽ tự nhận ra không phải ngày giao dịch,
in dòng bỏ qua rồi thoát 0. Không kết nối SSI, không ghi dữ liệu, không rủi ro — nhưng **chứng minh được
cả bốn tầng thông nhau**.

**Khoảng trống 2 — không có cách nghiệm thu file đã ghi.** Máy ghi in thống kê **khi kết thúc bình thường**.
Nếu tiến trình chết giữa phiên (đã xảy ra hôm 25/09), thống kê mất theo. Sau thứ Hai sẽ có 2 file và không
có công cụ nào trả lời được câu quan trọng nhất: **file này có dùng được không?**

---

## 1. Ràng buộc

- Được thêm: `scripts/verify_orderbook_file.py` (**file mới**) + test của nó.
- Được sửa: **không file nào** trong `trading/`. Nếu thấy cần, dừng và báo.
- **Không** sửa `record_vn30f_orderbook.py`, `sched.sh`, hay tác vụ hẹn giờ (Task 1 chỉ **chạy thử**, không
  sửa; trừ khi phát hiện lỗi — xem Task 1 mục 4).
- **Không** restart/build container. **Không** đặt lệnh. Không commit, không push.
- **Khôi phục sau kiểm thử phá hoại:** sao lưu đúng file sẽ sửa ra **ngoài** repo rồi copy lại. **Tuyệt đối
  không** `git checkout` / `git restore` / `git stash` diện rộng (quy tắc từ đợt 91, sau vụ mất 188 dòng
  `README.md`).
- Nền hiện tại: **819 passed**, ruff sạch.

---

## Task 1 — HÔM NAY: kích hoạt tác vụ hẹn giờ bằng tay, kiểm cả bốn tầng

1. Ghi lại trạng thái trước: `Get-ScheduledTaskInfo -TaskName "trading-orderbook-recorder"`.
2. Kích hoạt: `Start-ScheduledTask -TaskName "trading-orderbook-recorder"`.
3. Đợi tối đa 2 phút, rồi kiểm **đủ bốn điều**:
   - `Get-ScheduledTaskInfo` → `LastRunTime` nay là **hôm nay**, và `LastTaskResult` là **0**.
   - `logs/orderbook-recorder.log` **đã được tạo**, và nội dung có dòng nói **hôm nay không phải ngày giao
     dịch** (thứ Bảy).
   - **Không** có file nào mới trong `data/orderbook/` (không được ghi dữ liệu ngày không giao dịch).
   - Collector và engine **không bị ảnh hưởng**: `docker ps` vẫn 6 container, và `docker logs collector
     --since 5m` không có dòng lỗi mới.
4. **Nếu bất kỳ điều nào trong bốn điều trên sai:** đó chính là lỗi mà việc thử này sinh ra để bắt. Sửa
   **chỗ nhỏ nhất** làm nó đúng (thường là truyền tham số trong `run_hidden.vbs` hoặc `sched.sh`), rồi
   **chạy lại từ bước 2** cho tới khi cả bốn điều đúng. Báo cáo rõ đã sửa gì và vì sao.

**Tiêu chí hoàn thành:** `LastTaskResult = 0`, log tồn tại và nói đúng lý do bỏ qua, không có file dữ liệu,
container không bị ảnh hưởng.

---

## Task 2 — Công cụ nghiệm thu file sổ lệnh

Viết `scripts/verify_orderbook_file.py`, nhận đường dẫn một file `.jsonl.gz` và **chỉ đọc** (không mạng,
không DB, không sửa file). In báo cáo và trả **exit code khác 0** nếu file không đạt.

Báo cáo phải có:
1. **Mã và ngày** đọc được từ dữ liệu (không suy từ tên file — tên file có thể sai).
2. **Số tin theo loại** (QUOTE / TRADE / khác), và số dòng **không parse được** (nếu có).
3. **Mốc đầu và mốc cuối** theo `recv_ts`.
4. **Độ phủ phiên:** chia giờ khớp lệnh liên tục thành các ô 5 phút, đếm bao nhiêu ô **có ít nhất 1 tin**.
   In dạng `x/y ô (z%)`. Nghỉ trưa không tính vào mẫu số — dùng lại khuôn mẫu loại nghỉ trưa đã có trong
   `record_vn30f_orderbook.py`.
5. **Danh sách ô trống** (nếu có), để biết mất dữ liệu ở đâu chứ không chỉ mất bao nhiêu.

**Ba tiêu chí đạt/không đạt** — trả exit 1 nếu vi phạm bất kỳ:
- Có dòng không parse được.
- Độ phủ dưới **90%** số ô.
- **Mã ghi được không phải front-month của ngày đó.** Đây là tiêu chí quan trọng nhất: nó bắt hậu kiểm ca
  ghi sai hợp đồng, thứ mà chuông 10 phút của đợt 91 có thể bỏ lọt nếu nó không chạy. Dùng lại
  `resolve_front_month_symbol` (nó nhận `as_of`) — **import lại, đừng chép**. Không gọi được SSI thì nói rõ
  là **không kiểm được tiêu chí này**, đừng coi là đạt.

**Kiểm chứng — tách hàm thuần, test không cần mạng/file thật:**
1. Đủ tin, phủ 100% → đạt, exit 0.
2. Thiếu vài ô, phủ 85% → **không đạt**, và **nêu đúng các ô trống**.
3. Có 1 dòng rác không parse được → **không đạt**, đếm đúng 1.
4. **Ca biên:** file chỉ có tin ngoài giờ khớp lệnh liên tục (ví dụ toàn tin ATO 08:45–08:55) → độ phủ
   **0%**, không đạt, và **không nổ** (chia cho 0, `max()` trên rỗng).
5. Đếm ô đúng: nghỉ trưa **không** nằm trong mẫu số.
6. **Kiểm thử phá hoại:** bỏ điều kiện phủ < 90%, xác nhận đúng ca 2 đỏ.

**Chạy thật trên file đã có:** `data/orderbook/41I1GA000/2026-09-25.jsonl.gz` (705.329 tin). Dán nguyên văn
báo cáo. **Kỳ vọng file này KHÔNG ĐẠT** — nó mất 67 phút vì cú ngắt kết nối 10:00→11:07, nên độ phủ sẽ
dưới 90%. Nếu nó báo ĐẠT thì công cụ đang không đo đúng thứ nó nói.

---

## Task 3 — Chiều thứ Hai: nghiệm thu phiên tự động đầu tiên

Sau **15:10** thứ Hai 28/09:
1. Chạy `verify_orderbook_file.py` trên file thứ Hai. Dán nguyên văn.
2. Dán `logs/orderbook-recorder.log` phần của thứ Hai.
3. Dán mọi dòng WARN trong log máy ghi — **đặc biệt** chuông lưu lượng thấp của đợt 91 và cảnh báo đường lùi
   khi không lấy được mã từ SSI.
4. Dòng `stream-health` của 28/09: độ phủ luồng collector **vẫn phải 100%**.
5. `Get-ScheduledTaskInfo` → `LastTaskResult` của lần chạy 08:40.

**Không tự sửa gì trong Task 3.** Đây là nghiệm thu; thấy gì lạ thì báo, tôi quyết.

---

## 2. Không làm

- Không sửa `trading/`, không sửa `record_vn30f_orderbook.py` / `sched.sh` (trừ khi Task 1 mục 4 bắt buộc).
- Không sửa hay xoá file dữ liệu đã ghi.
- Không dùng lệnh git diện rộng.
- Không restart/build container, không đặt lệnh, không commit, không push.

## 3. Báo cáo cho Claude

1. **Task 1**: trạng thái trước/sau, cả bốn điều kiểm, và đã sửa gì nếu có.
2. **Task 2**: kết quả 6 nhóm test + kiểm thử phá hoại; **nguyên văn báo cáo chạy trên file 25/09** và
   kết luận đạt/không đạt của nó.
3. **Task 3** (thứ Hai): năm mục ở trên, nguyên văn.
4. `uv run pytest -m "not integration" -q` (nền **819**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Ghi chú của planner

**Vì sao Task 2 phải kiểm lại mã hợp đồng dù đợt 91 đã có chuông:** chuông đợt 91 chạy **trong** tiến trình
máy ghi. Nếu máy ghi chết trước mốc 10 phút, hoặc chuông không kích hoạt vì lý do nào đó, sẽ không có ai
nói gì cả. Một công cụ **đọc file sau cùng** không phụ thuộc vào tiến trình đã chết là lớp bảo vệ độc lập.
Hai lớp cho cùng một lỗi là có chủ ý, không phải trùng lặp.

**Việc chặn duy nhất vẫn là biểu phí phái sinh** — cần chủ dự án lấy từ SSI/HNX/VSD kèm nguồn. Trước khi có
nó, hướng phái sinh dừng ở sàng lọc tín hiệu, không đi tới backtest được. Việc thu dữ liệu sổ lệnh (20 phiên,
tới khoảng giữa tháng 10) chạy song song và **không** chờ biểu phí.
