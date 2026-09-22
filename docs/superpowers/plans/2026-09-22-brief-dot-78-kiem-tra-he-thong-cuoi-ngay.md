# Brief đợt 78 — Kiểm tra sức khỏe hệ thống cuối ngày 22/09/2026 (thứ Ba)

Ngày giao: 22/09/2026 (thứ Ba), **chạy SAU khi phiên đóng cửa (sau 15:00 VN)**.
Base: main `35b1274`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh — chỉ để bạn biết, không phải việc phải sửa

Sáng nay lúc ~07:45 VN (trước giờ mở cửa), toàn bộ container (kể cả postgres/nats/grafana, không
chỉ collector/engine) restart đồng loạt dù máy **không** reboot (uptime máy từ 18/09). Nhiều khả
năng Docker Desktop tự khởi động lại — cùng loại sự cố đã xảy ra hai đêm 19→20 và 20→21/09, nhưng
lần này phục hồi **trước** giờ mở cửa nên không ảnh hưởng phiên. Cổng go-live lúc 07:51 báo
**EXIT 0**, warm-up nạp đúng tới phiên đóng cửa hôm qua (21/09 14:45 VN).

Đây là ngày đầu tiên chạy trọn vẹn với **GAP-1** (đợt 74/75) sau khi đã được nối test đầy đủ, và là
dịp đầu tiên có thể quan sát nó hoạt động thật trên một cú restart thật (nếu warm-up có lỗ do
restart sáng nay).

**Đây là brief kiểm tra, không phải brief sửa lỗi.** Nếu phát hiện gì bất thường, ghi lại đầy đủ
bằng chứng và báo cáo — không tự sửa trong đợt này trừ khi brief nói rõ.

---

## 1. Ràng buộc

- **Chạy sau 15:00 VN hôm nay** — nhiều mục cần dữ liệu cả phiên mới có ý nghĩa.
- Chỉ đọc log/DB, **không** khởi động lại container, không sửa code, không sửa config.
- Không commit, không push.

---

## Task 1 — GAP-1 có kêu đúng lúc không, và nếu kêu thì đúng hay báo động giả

1. `Select-String -Path logs\engine_alerts.log -Pattern "GAP-1"` (hoặc lệnh tương đương) — lấy toàn
   bộ dòng WARN GAP-1 phát sinh **hôm nay** (22/09).
2. Với mỗi dòng tìm được: đối chiếu `warmed_until` và `first_live_ts` trong nội dung cảnh báo với
   log khởi động thật (`engine_alerts.log` quanh mốc engine restart sáng nay, ~07:45 VN) và với
   lưới nến thật trên `bars` (dùng `docker exec ... psql` đọc `bars` quanh khung 21/09 14:45 →
   22/09 09:15, giống cách brief 74 đã kiểm chứng thủ công).
3. Kết luận: nếu **không có** dòng GAP-1 nào — nói rõ vì sao hợp lý (ví dụ: restart sáng nay xảy ra
   trước phiên, không có nến nào bị bỏ lỡ giữa 14:45 hôm qua và 09:15 hôm nay, đúng ca "liền mạch
   qua cuối tuần/qua đêm" mà đợt 74 đã thiết kế để im lặng). Nếu **có** dòng GAP-1 — xác nhận số
   nến thiếu nó báo có khớp với thực tế đếm được trên `bars` không.

---

## Task 2 — Deploy drift và luồng cảnh báo bền vững

1. `Get-Content logs\deploy-drift.log -Tail 15` — xác nhận job 08:00 hôm nay **chạy** (không
   `SKIP: docker chua chay` như 21/09), và kết quả (khớp hay lệch).
2. `Get-Content logs\engine_alerts.log` — lọc các dòng của hôm nay, xác nhận log **liên tục cả
   ngày** (không có khoảng trống bất thường dài hơn vài phút giữa các lần ghi trong giờ phiên
   09:00-14:45), đúng tiêu chí "cơ chế ghi log bền vững" đã xác nhận lần đầu ở 21/09.
3. Đếm số dòng WARN/CRITICAL hôm nay (nếu có), liệt kê nguyên văn — không chỉ nói "có X dòng".

---

## Task 3 — Cổng go-live cuối ngày, và tín hiệu/lệnh thật trong phiên

1. Chạy `uv run python scripts/check_golive_gate.py` sau 15:00 — dán nguyên văn kết quả.
2. Chạy `uv run python scripts/check_silent_engine.py` — xác nhận cả 3 mã vẫn "Hoạt động" (không
   ai bất ngờ câm lại), dán số bull/bear hiện tại, so với đợt 74 (HPG 6, IJC 6, AAA 10 bull).
3. Truy vấn `orders` cho hôm nay (`ts::date = '2026-09-22'`) — có lệnh mới nào không. Nếu có, dán
   nguyên dòng. Nếu không, đó là bình thường (engine đang giữ vị thế IJC/AAA từ 03/09, chỉ chờ tín
   hiệu thoát) — không suy diễn thêm.

---

## Task 4 — Bất kỳ điều gì khác thường, nói thẳng

Nếu phát hiện dòng log lạ, số liệu không khớp kỳ vọng, hoặc bất kỳ dấu hiệu nào không nằm trong 3
Task trên — **báo cáo, đừng bỏ qua vì "không thuộc phạm vi được hỏi"**.

---

## 2. Không làm

- Không khởi động lại/tắt bất kỳ container nào.
- Không sửa code, không sửa config, không sửa test.
- Không tự ý kết luận nguyên nhân Docker Desktop tự khởi động lại (việc của bác, đã ghi nhận và
  chọn bỏ qua).
- Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: có/không GAP-1 hôm nay, kèm bằng chứng đối chiếu `bars`.
2. Task 2: deploy-drift hôm nay, tính liên tục của `engine_alerts.log`, danh sách WARN/CRITICAL
   nguyên văn (nếu có).
3. Task 3: nguyên văn `check_golive_gate.py` + `check_silent_engine.py`, và lệnh mới hôm nay (nếu
   có).
4. Task 4: bất cứ điều gì khác thường.
