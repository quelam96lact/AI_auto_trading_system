# Brief đợt 104 — Nghiệm thu ngày giao dịch tự động đầu tiên (thứ Hai 28/09/2026)

Ngày giao: 26/09/2026. Base: main `6eb8e3a`.
Người audit: Claude. Người thực thi: agent. **CHỈ BÁO CÁO. KHÔNG SỬA GÌ.**

Brief này **thay thế** hai mục nghiệm thu cũ và gom chúng vào một chỗ:
- đợt 92 Task 3 (máy ghi sổ lệnh);
- đợt 97 Task 4 (engine bán IJC/AAA theo đợt 96).

Nó cũng thêm các điểm của đợt 93, 97 và 103 mà hai brief cũ chưa có.

## Luật

- **Không sửa code, cấu hình, Task Scheduler. Không restart/build container. Không đặt lệnh.**
- Chỉ đọc: log, bảng DB (`SELECT`), `Get-ScheduledTaskInfo`, và các script **chỉ đọc** được nêu tên dưới đây.
- Mỗi mục dán **bằng chứng thô** (dòng log, kết quả truy vấn, output nguyên văn). Không tóm tắt thay cho bằng chứng.
- Thấy gì khác với "Kỳ vọng": ghi **nguyên văn**, **không** đoán nguyên nhân, **không** sửa. Claude quyết.
- Mọi lọc theo ngày trên `ts`: `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`, **không** dùng `ts::date`.

Có hai lượt báo cáo: **Lượt A sau 15:40**, **Lượt B sau 21:15** (hoặc sáng thứ Ba nếu không kịp).

---

## Lượt A — sau 15:40 thứ Hai 28/09

### A1. Máy ghi sổ lệnh VN30F (lần chạy tự động đầu tiên)
1. `Get-ScheduledTaskInfo -TaskName trading-orderbook-recorder`: `LastRunTime`, `LastTaskResult`. **Kỳ vọng:** chạy lúc ~08:40, kết quả 0.
2. Phần của ngày 28/09 trong `logs/orderbook-recorder.log`: dòng bắt đầu, mã hợp đồng đã chọn, dòng kết thúc và thống kê. **Kỳ vọng:** mã `41I1GA000`, lấy từ SSI (không phải đường lùi).
3. **Mọi** dòng WARN/CRITICAL của máy ghi hôm đó, đặc biệt chuông lưu lượng thấp (đợt 91), cảnh báo đường lùi khi không lấy được mã, và cảnh báo dừng sớm (đợt 94). **Kỳ vọng:** không có.
4. `uv run python scripts/verify_orderbook_file.py <file 28/09>`: dán nguyên văn. **Kỳ vọng:** đạt cả ba tiêu chí.
5. `uv run python scripts/build_orderbook_features.py <file 28/09>`: dán nguyên văn. **Kỳ vọng:**
   - lưới 240 ô;
   - có tin ngay từ **09:00** (25/09 trống 09:00–09:02 vì máy ghi bật muộn; hôm nay máy ghi bật 08:40);
   - không có giá trị vô lý;
   - "Tin ngoài khung" khác 0 (các tin ATC 14:30–14:45).

   So con số "hàng dùng được" với 171/240 của 25/09.

### A2. Kiểm tra sau phiên của máy ghi (15:30)
6. `Get-ScheduledTaskInfo -TaskName trading-orderbook-daily-check` và phần log của 28/09. **Kỳ vọng:** kết quả 0, im lặng (file đạt).

### A3. Engine paper (đợt 96)
7. Bảng `orders` ngày 28/09 (giờ VN): dán mọi dòng. **Kỳ vọng:** SELL IJC 400 và SELL AAA 400 ở **những bar đầu tiên** của phiên. Giá ≈ `min(open, stop)`: IJC stop ≈ 7.359, AAA stop ≈ 7.860; cả hai đang dưới stop nên giá thường là giá mở cửa.
8. Log engine ngày 28/09: có dòng WARN `khong tim thay ngay mua` không? **Kỳ vọng: không.**
9. Có dòng WARN `da cham stop ... nhung chua ban duoc` không? **Kỳ vọng: không** (cả hai đã settle).
10. `SELECT * FROM positions WHERE qty > 0`. **Kỳ vọng:** không còn IJC/AAA (trừ khi có lệnh mua mới trong ngày; khi đó ghi rõ).
11. Output của `trading-engine-cam` lúc 15:15 (`logs/engine-cam.log`, phần 28/09). Chỉ dán, không diễn giải.

### A4. Đồng bộ tài khoản và đối soát lệnh thật (đợt 103)
12. Log collector ngày 28/09: mọi dòng chứa `account sync failed`, `đối soát`, `lệnh thật`. **Kỳ vọng:** không có `account sync failed`. Không có dòng đối soát nào vì chưa có lệnh thật (`real_order_fills` rỗng).
13. `SELECT status, count(*) FROM real_order_fills GROUP BY 1`. **Kỳ vọng:** rỗng.

### A5. Luồng dữ liệu và các tác vụ khác
14. Dòng `stream-health` của 28/09 (15:10). **Kỳ vọng:** độ phủ luồng collector ≥ 90% (các ngày tốt là 98–100%).
15. `Get-ScheduledTaskInfo` cho **mọi** tác vụ `trading-*`: bảng `TaskName | LastRunTime | LastTaskResult`. **Kỳ vọng:** các tác vụ đã chạy hôm nay đều ra 0.
16. `uv run python scripts/check_golive_gate.py`: dán nguyên văn. **Kỳ vọng:** EXIT 0; tiêu chí 9 ghi "Đã khớp: 0, đang chờ: 0, đã huỷ: 0".

---

## Lượt B — sau 21:15 thứ Hai (hoặc sáng thứ Ba)

17. `logs/backfill.log` phần 28/09: dòng `DONE:` và `EXIT=`. `Get-ScheduledTaskInfo -TaskName trading-backfill-universe`.
18. `logs/daily-data-check.log` phần 28/09 và `Get-ScheduledTaskInfo -TaskName trading-daily-data-check`. **Kỳ vọng:** thứ Hai nên có dòng `Loại 1 mã chỉ giao dịch thứ Sáu (POM)` (đợt 97), và exit 0. Có mã khác bị báo thiếu thì dán nguyên văn.
    - Nếu `daily-data-check` chạy **trước** khi backfill xong: ghi rõ thứ tự thời gian của hai tác vụ, và dòng "hoãn phán quyết" nếu có.

---

## Báo cáo cho Claude

Một bảng tổng hợp ở đầu: `Mục | Kỳ vọng | Thực tế | Khớp? (có/không)`, rồi bằng chứng thô cho từng mục. Mục nào **không khớp** thì đưa lên đầu báo cáo.

**Không sửa gì.** Kết thúc bằng câu: "Tôi không sửa code, cấu hình, lịch hay container nào."
