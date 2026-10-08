# Brief đợt 163 — Dựng sẵn công cụ đo của đợt 162 trên dữ liệu tổng hợp, KHÔNG đọc file sổ lệnh thật

Ngày: 08/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Thiết kế đo: `docs/superpowers/plans/2026-10-04-brief-dot-162-sang-loc-so-lenh-vn30f-dang-ky-truoc.md` (đọc hết trước khi làm, kể cả §8 mới thêm hôm nay).
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.

---

## 0. Vì sao làm bây giờ, khi phép đo chỉ được chạy từ tháng 12

Đợt 162 ghi "giao việc sau mốc §2". Tôi đổi ý vì một lý do cụ thể: khi soạn brief này tôi đọc hai công cụ mà đợt 162 bắt dùng lại, và **cả hai đều không chạy đúng nguyên trạng trên dữ liệu 1 phút** (§1). Nếu chờ tới tháng 12 mới phát hiện, ta phải sửa thiết kế **sau khi** IS đã đóng, đúng lúc dễ bị cám dỗ chỉnh theo dữ liệu nhất. Dựng công cụ bây giờ trên dữ liệu tổng hợp thì mọi quyết định thiết kế được khóa trước khi có ai nhìn thấy một con số.

Điều kiện để việc này không phá đăng ký trước: **agent không mở, không đọc, không dựng bảng từ bất kỳ file nào trong `data/orderbook/`**, kể cả "chỉ để thử đường ống". Mọi test dùng phiên dựng tay hoặc file `.jsonl.gz` giả tạo trong thư mục tạm của test.

## 1. Hai lỗ hổng đã xác nhận (Claude đọc code 08/10, không phải phỏng đoán)

**1a. Hoán vị khối không bám theo phiên.** `run_block_permutation_test` (`scripts/audit_information.py:206`) cắt khối theo **số hàng** (`block_size_hours` hàng liên tiếp), không theo nhãn phiên. Đợt 162 §1.4 đòi "khối = 1 phiên". Nếu bỏ các phút thiếu QUOTE khỏi danh sách hàng (như §1.1 viết), mỗi phiên còn số hàng khác nhau và khối 240 hàng sẽ cắt ngang hai phiên.

→ **Quyết định (ghi vào 162 §8):** giữ **đủ lưới 240 phút cho mọi phiên**, phút thiếu QUOTE vẫn có hàng nhưng đặc trưng là `None`; Spearman chỉ dùng cặp có đủ hai giá trị. Khi đó mọi khối dài đúng 240 hàng và trùng biên phiên, nên được dùng lại `run_block_permutation_test` với `block_size_hours=240`, `feature_names`/`target_names` truyền tường minh. Tỷ lệ loại vẫn báo như cũ. Nếu agent thấy hàm đó **không** bỏ qua `None` khi tính rho (đọc code, không đoán), dừng và báo, không tự viết hàm hoán vị khác.

**1b. Biến đối chứng không có sẵn cho dữ liệu sổ lệnh.** `check_control_variable` (`scripts/leakage_audit.py:216`) mặc định đòi cột `delta_norm`/`delta` và `ret_past_1h`/`fwd_ret_1h`; bảng 1 phút của đợt 93 không có cột nào trong số đó.

→ **Quyết định (ghi vào 162 §8):** biến đối chứng là `ofi` của phút `t`, so với thay đổi mid **cùng phút** `mid_close(t) − mid_close(t−1)` (cột `mid_chg_same_1m`). OFI là dòng lệnh trong chính phút đó nên phải tương quan dương mạnh với giá cùng phút; không thấy thì đường ống đang hỏng. Gọi `check_control_variable(rows, control_feature="ofi", past_ret_col="mid_chg_same_1m", future_ret_col=<cột mid h=1 của §1.4>)`, ngưỡng mặc định `CONTROL_MIN_RHO_TRUOC = 0.3`. Trượt → script dừng, **không in** rho của 9 cặp.
Tiền đề (Claude đã đọc, `build_orderbook_features.py:218-258`): `ofi` là tổng khối lượng TRADE có dấu **trong** phút `t`, phút không có TRADE thì `ofi = 0` và không bao giờ `None`. Lưới là `session_minutes(d)` đủ 240 phút. Agent đọc lại và xác nhận; khác thế → dừng và báo.

## 2. Phạm vi
- **Được thêm:** `scripts/screen_vn30f_orderbook.py`, `tests/test_screen_vn30f_orderbook.py`.
- **Được import, không sửa:** `scripts/build_orderbook_features.py`, `scripts/audit_information.py`, `scripts/leakage_audit.py`, `trading/derivative_position.py`, `trading/calendar_vn.py`.
- **Không sửa:** mọi file khác, kể cả brief 162 (Claude tự sửa). Thấy vấn đề ngoài phạm vi → báo cáo, không tự sửa, không xóa code cũ.
- **Cấm:** đọc/liệt kê nội dung `data/orderbook/`; chạy CLI của script mới trên thư mục thật; chạy `scripts/sched.sh` (bài học đợt 156: chạy thử qua sched.sh ghi vào log thật).
- GitNexus: index đang cũ → chạy `npx gitnexus analyze` trước. `context` cho `build_minute_features`, `session_minutes`, `run_block_permutation_test`, `check_control_variable`, `derivative_side_cost` trước khi viết; `detect_changes` sau khi xong, dán kết quả.

## 3. Script phải làm gì
Đúng mọi định nghĩa ở 162 §1.1–§1.6 (độ trễ một phút, giá thực thi bid/ask, spread trong mục tiêu, không qua phiên, ngưỡng P90 chỉ từ IS, chọn sự kiện độc lập tham lam, ngưỡng kinh tế 1,5 × chi phí từ `derivative_side_cost`, nhãn THIẾU SỨC MẠNH), cộng thêm:
- **Cổng ngày (chống nhìn trước):** `main()` từ chối chạy, mã thoát khác 0, **trước khi mở bất kỳ file nào**, nếu ngày hiện tại (giờ VN) ≤ 30/11/2026. Logic nhận `today` làm tham số để test được; CLI **không** có cờ ghi đè ngày.
- **Cổng phiên hợp lệ:** phiên hợp lệ = ≥ 90% phút trên lưới 240 có đủ đặc trưng (`MinuteRow.usable()`). Dưới 40 phiên hợp lệ trong IS → dừng, không in rho.
- **Niêm phong:** phiên ≥ 01/12/2026 chỉ được đọc khi có cờ mở niêm phong tường minh kèm tên đúng một cặp; cờ đó ghi một dòng vào `docs/holdout-unlock-log.md` **trước** khi đọc. Trong test, đường dẫn log phải là file tạm (bài học đợt 142: test ghi đè file trạng thái thật).
- Báo cáo in ra: mã hợp đồng từng phiên, số phiên hợp lệ/bị loại, tỷ lệ phút loại, rho control, ngưỡng P95, rồi bảng 9 cặp (rho, m, chi phí, số sự kiện độc lập tổng/mua/bán, nhãn).

## 4. Kiểm chứng — TDD, thấy đỏ rồi mới viết code
Chín test của 162 §4 (giữ nguyên nội dung), cộng:

10. **Khối trùng phiên:** dữ liệu 3 phiên, mỗi phiên vài phút `None`: số hàng mỗi phiên đúng 240, và mọi khối của hoán vị bắt đầu ở phút 09:00 của một phiên.
11. **None không vào rho:** thêm một phút `None` vào giữa không làm đổi rho so với bỏ hẳn phút đó.
12. **Control:** phiên tổng hợp có `ofi` cùng dấu với thay đổi mid cùng phút → qua; xáo `ofi` ngẫu nhiên → trượt, và script **không in** bảng 9 cặp.
13. **Cổng ngày:** `today = 30/11/2026` → dừng, không hàm đọc file nào được gọi (dùng giả lập để khẳng định không có lời gọi); `today = 01/12/2026` → đi tiếp.
14. **Chi phí lấy từ hàm, không gắn cứng:** giả lập `derivative_side_cost` trả giá trị khác → ngưỡng kinh tế đổi theo.

Kiểm thử phá hoại (sao lưu file ra ngoài repo, cấm `git checkout/restore/stash`), báo tên test đỏ từng bước:
- bỏ độ trễ một phút → test 1 đỏ; tính P90 trên toàn bộ dữ liệu → test 3 đỏ; cộng spread hai lần → test 2 đỏ (từ 162);
- bỏ phút `None` khỏi lưới → test 10 đỏ; bỏ cổng ngày → test 13 đỏ; gắn cứng 0,49 điểm → test 14 đỏ.

```
uv run pytest tests/test_screen_vn30f_orderbook.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```
Hoàn thành khi: 14 test xanh, sáu bước phá hoại mỗi bước làm đúng test đã nêu đỏ, bộ đầy đủ không có test mới đỏ (dán số passed trước/sau), ruff sạch, `detect_changes` chỉ gồm hai file mới.

## 5. Báo cáo cho Claude
1. Kết quả đọc code cho hai tiền đề ở §1 (rho có bỏ `None` không; `ofi` là dòng trong phút không), kèm số dòng.
2. Output pytest/ruff, bảng sáu bước phá hoại.
3. `detect_changes`.
4. Xác nhận bằng một câu: "Tôi không mở file nào trong `data/orderbook/`."
5. Mọi chỗ 162 mơ hồ mà agent phải tự diễn giải: liệt kê, không im lặng chọn.

## 6. Việc Claude làm, không giao agent
- 08/10: đã nạp bù `bars_daily` 01→07/10 (Docker tắt các tối 02–07/10, cả backfill lẫn backup đều SKIP), chạy backup DB + sổ lệnh, `backup-check` EXIT=0.
- Sửa brief 162 thêm §8 (hai quyết định ở §1 + phiên 01/10 mất vĩnh viễn).
- Audit kết quả agent, commit, push.

## 7. Cần chủ dự án (không chặn việc hôm nay)
- **Bảng kê phí phái sinh thật** (162 §7): phải đối chiếu với `derivative_side_cost` **trước** tháng 12. Một lệnh đã khớp bất kỳ là đủ.
- Ghi nhận: phiên 01/10 không có file sổ lệnh (máy tắt cả phiên). IS còn dự kiến khoảng 46 phiên so với ngưỡng 40; mất thêm ~6 phiên nữa là phải lùi mốc.
