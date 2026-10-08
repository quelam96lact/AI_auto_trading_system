# Brief đợt 163, vòng 3 — Sửa lỗi niêm phong của công cụ đo đợt 162

Ngày: 08/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

Bản nộp đợt 163 vòng 2 CHƯA được chấp nhận: còn một lỗi niêm phong và hai chỗ nhỏ. Sửa đúng ba mục dưới, không làm gì thêm.

Tài liệu gốc (đọc lại trước khi sửa):
- `docs/superpowers/plans/2026-10-04-brief-dot-162-sang-loc-so-lenh-vn30f-dang-ky-truoc.md` (gồm §8)
- `docs/superpowers/plans/2026-10-08-brief-dot-163-dung-san-cong-cu-do-dot-162-tren-du-lieu-tong-hop.md`

## Phạm vi
- Chỉ sửa `scripts/screen_vn30f_orderbook.py` và `tests/test_screen_vn30f_orderbook.py`.
- CẤM mở/đọc/liệt kê nội dung `data/orderbook/`; cấm chạy CLI của script trên thư mục thật; cấm chạy `scripts/sched.sh`.
- Không commit, không push. Không tạo file báo cáo trong repo; báo cáo gửi qua chat.
- Chạy GitNexus `impact` trước khi sửa từng hàm, `detect_changes` sau khi xong.

## 1. Lỗi chính: tập niêm phong bị đọc trước khi kiểm điều kiện và ghi log

Hiện tại `main()` (khoảng dòng 706) gọi `load_all_sessions(..., holdout_pair=<cặp>)`. Hàm này gọi `build_minute_features` cho MỌI phiên ≥ 01/12/2026 trước khi `run_screening` kiểm 3 điều kiện mở niêm phong và ghi log. Hậu quả: chỉ cần truyền cờ `--unlock-holdout-pair` là tập niêm phong đã bị đọc, kể cả khi lần mở bị từ chối. Test `test_thu_tu_ghi_log_truoc_doc_holdout_sau` không bắt được vì nó gọi thẳng `run_screening` với phiên dựng sẵn.

Sửa theo đúng thứ tự:
- a. `load_all_sessions` LUÔN bỏ qua phiên ≥ 01/12/2026 (không mở file, không gọi `build_minute_features`), bất kể cờ. Xóa tham số `holdout_pair` của hàm này.
- b. `main()` chạy trọn phép đo IS như hiện tại.
- c. Nếu có cờ mở niêm phong, kiểm 3 điều kiện:
  - tên cặp thuộc 9 cặp;
  - cặp đó có nhãn ĐÁNG KỂ ở IS;
  - có ≥ 30 FILE phiên ≥ 01/12/2026 trên đĩa (chỉ đếm theo tên file, KHÔNG mở file).

  Thiếu một điều kiện → từ chối, mã thoát khác 0, KHÔNG ghi log, KHÔNG đọc phiên niêm phong.
- d. Đủ cả ba → ghi log → rồi mới gọi một hàm riêng đọc và dựng bảng các phiên niêm phong.
- e. Sau khi đọc, nếu số phiên HỢP LỆ (≥ 90% phút dùng được) < 30 → dừng, báo "KHÔNG ĐỦ PHIÊN NIÊM PHONG HỢP LỆ", không in kết quả cặp. Lần mở này vẫn tính là đã dùng (log đã ghi).
- f. P90 và chi phí vẫn lấy từ IS, không đổi.

Test (viết trước, thấy đỏ rồi mới sửa code):
- Test ở mức `main()`, dùng thư mục `tmp_path` có cấu trúc `<mã>/<ngày>.jsonl.gz` với phiên IS và phiên ≥ 01/12. Giả lập `build_minute_features` và hàm ghi log, ghi lại thứ tự gọi. Khẳng định:
  - (i) không có cờ → `build_minute_features` không bao giờ được gọi với ngày ≥ 01/12;
  - (ii) có cờ nhưng bị từ chối (cặp chưa ĐÁNG KỂ) → không ghi log, không gọi `build_minute_features` với ngày ≥ 01/12;
  - (iii) có cờ và đủ điều kiện → lời gọi ghi log đứng TRƯỚC lời gọi `build_minute_features` đầu tiên cho ngày ≥ 01/12.

  Để IS ra ĐÁNG KỂ trong test, được giả lập `evaluate_pairs` hoặc phần IS của `run_screening`.
- Test (e): có đủ 30 file nhưng dưới 30 phiên hợp lệ → dừng đúng thông báo, không có kết quả cặp.

## 2. Bỏ nhánh file nằm ngay thư mục gốc

Trong `load_all_sessions` (khoảng dòng 586–592) có nhánh đọc file `.jsonl.gz` nằm ngay `data_dir` và gán mã cứng `"VN30F"`. Bỏ nhánh đó. File nằm ngay `data_dir` (không trong thư mục con `<mã>`) → bỏ qua và in cảnh báo, không tự gán mã. Thêm test.

## 3. Bỏ cờ CLI `--unlock-log-path`

Log mở niêm phong trên CLI luôn là `docs/holdout-unlock-log.md`. Giữ tham số `unlock_log_path` ở mức hàm để test dùng `tmp_path`; test không bao giờ ghi vào file log thật. Thêm test: `main(args=["--unlock-log-path", "x"])` bị argparse từ chối (`SystemExit`).

## Kiểm thử phá hoại

Sao lưu file ra ngoài repo trước khi phá; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ:
1. Đưa lời gọi đọc phiên niêm phong lên trước khi ghi log → test (iii) đỏ.
2. Cho `load_all_sessions` đọc cả phiên ≥ 01/12 → test (i) đỏ.
3. Bỏ điều kiện "cặp phải ĐÁNG KỂ ở IS" → test (ii) đỏ.
4. Thêm lại cờ `--unlock-log-path` → test `SystemExit` đỏ.

## Kiểm chứng hoàn thành

```
uv run pytest tests/test_screen_vn30f_orderbook.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

Hoàn thành khi: mọi test xanh, 4 bước phá hoại bước nào cũng làm đỏ đúng test đã nêu, bộ đầy đủ không có test mới đỏ (dán số passed; lần trước là 1750 passed, 150 deselected), ruff sạch, `detect_changes` chỉ gồm hai file trên.

## Báo cáo nộp lại (đủ năm mục)
1. Output pytest (file đợt 163 và bộ đầy đủ) và ruff.
2. Bảng 4 bước phá hoại: bước, thay đổi, tên test đỏ.
3. Output `detect_changes`.
4. Một câu xác nhận: "Tôi không mở file nào trong `data/orderbook/`."
5. Mọi chỗ agent phải tự diễn giải; không im lặng chọn.
