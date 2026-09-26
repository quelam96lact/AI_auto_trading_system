# Brief đợt 97 — Chuông kiểm dữ liệu kêu oan 4/5 ngày mỗi tuần, và hoãn mãi không leo thang

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `2af5d40`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.
Task 1–3 làm được ngay cuối tuần. Task 4 làm **chiều thứ Hai 28/09 sau 15:10**.
**Không** restart/build container. **Không** sửa máy ghi sổ lệnh. **Không** đụng Task Scheduler.

---

## 0. Vì sao

Nguyên tắc của repo: **"chuông kêu oan cũng là cùng một bệnh với chuông chết câm"**. Người nhận quen bỏ qua, rồi bỏ qua luôn lần kêu thật.

**Claude đã đo (DB thật, chỉ đọc):**
- `daily_data_check` báo WARN "sót bar daily" cho **POM** ngày 21/09 (thứ Hai) và 24/09 (thứ Năm). Hai ngày 22 và 23/09 không báo **chỉ vì Docker không chạy** lúc 21:00.
- `bars_daily` của POM trong 12 tuần gần nhất: **chỉ có nến vào thứ Sáu**, đều đặn tuần nào cũng có (25/09, 18/09, 11/09, 04/09, 28/08…). Đây là dấu hiệu của **cổ phiếu bị hạn chế giao dịch**: sàn chỉ cho giao dịch vào thứ Sáu.
- Trong 175 mã active, **chỉ có POM** mang dấu hiệu này (truy vấn 42 ngày gần nhất: mã không có nến nào ngoài thứ Sáu, hoặc có dưới 15 nến).

Hệ quả: chuông **sẽ kêu oan mỗi thứ Hai tới thứ Năm**, vô thời hạn.

Lỗ thứ hai, đã ghi nhận từ đợt 93 nhưng chưa giao: nếu `backfill-universe` hỏng lâu dài, `daily_data_check` cứ **hoãn** (WARN "backfill chưa xong") mỗi ngày và **không bao giờ báo đỏ**. Chuông không chết, nhưng nó nói "chờ đã" mãi mãi.

---

## 1. Ràng buộc chung

- **Được sửa:** `scripts/daily_data_check.py`, `tests/test_daily_data_check.py` (hoặc file test đang có của nó; tìm trước, không tạo trùng).
- **Được thêm:** một script thăm dò chỉ đọc ở Task 1. Đặt tên có tiền tố `spike_`, theo khuôn `scripts/spike_securities_summary_raw.py`.
- **Không được sửa:** `trading/`, collector, mọi script khác.
- Trước khi sửa: `gitnexus_impact` cho `evaluate_daily_completeness` và `main` của `daily_data_check.py`, dán kết quả. Nếu HIGH hoặc CRITICAL thì **dừng**.
- Sau khi sửa: `gitnexus_detect_changes()`, dán kết quả.
- Mọi lọc theo ngày trên `ts`: **bắt buộc** `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`. **Cấm** `ts::date`. Bẫy này đã cắn repo **4 lần**.
- Sao lưu ra **ngoài repo** trước khi phá hoại. **Cấm** `git checkout`, `git restore`, `git stash`.

---

## Task 1 — Thăm dò: SSI có trả trạng thái "hạn chế giao dịch" không? (CHỈ ĐỌC)

Gọi API dữ liệu SSI, lấy thông tin chứng khoán **thô** (trước khi SDK parse) cho **POM** và **HPG** (mã đối chứng, giao dịch bình thường). Dùng đường xác thực mà collector đang dùng; đi theo khuôn của `scripts/spike_securities_summary_raw.py` (token từ `ssi_auth_state`, httpx, không OTP).

Đầu tiên thử `get_securities_info_by_board` / securities details. Báo cáo:
1. **Toàn bộ tên trường** trong response thô của POM và HPG, đặt cạnh nhau.
2. Trường nào có giá trị **khác nhau** giữa POM và HPG mà có thể là trạng thái giao dịch (ví dụ status, tradingStatus, halt, restrict…). Dán nguyên giá trị.
3. Kết luận **một trong hai**: `CÓ TRƯỜNG` (ghi tên trường, giá trị cho POM, giá trị cho HPG) hoặc `KHÔNG CÓ`.

**Không đoán.** Một trường có tên gợi ý nhưng giá trị POM và HPG giống nhau thì **không phải** bằng chứng. Token hết hạn thì **dừng và báo**, không tự xoay token.

---

## Task 2 — Mã chỉ giao dịch thứ Sáu thì không bị tính là "sót" vào các ngày khác

**Nguồn sự thật, theo thứ tự:**
- Nếu Task 1 ra `CÓ TRƯỜNG`: **dừng ở đây, báo cáo, không làm Task 2.** Claude sẽ quyết có đưa lời gọi SSI vào job hằng đêm hay không. Việc đó thêm một phụ thuộc mạng vào chuông, nên cần cân nhắc riêng.
- Nếu Task 1 ra `KHÔNG CÓ`: làm Task 2 theo quy tắc dữ liệu dưới đây.

**Quy tắc (chốt sẵn, không tự đổi):**
- Một mã là **"chỉ-thứ-Sáu"** nếu trong **30 ngày giao dịch** gần nhất **trước** ngày kiểm tra, nó có **ít nhất 3 nến** và **mọi nến đều rơi vào thứ Sáu**. Ngày trong tuần tính theo **giờ VN**.
- Ngày kiểm tra **không phải thứ Sáu**: mã chỉ-thứ-Sáu **không** bị tính là sót, và **không** nằm trong mẫu số "Tổng số mã active".
- Ngày kiểm tra **là thứ Sáu**: mã chỉ-thứ-Sáu vẫn được kiểm như mọi mã khác. Thiếu thì **vẫn báo**.
- Báo cáo phải ghi rõ số mã được loại và tên của chúng, ví dụ `Loại 1 mã chỉ giao dịch thứ Sáu (POM)`. **Không được lặng lẽ loại.**
- Một mã **quay lại giao dịch bình thường** (có nến vào một ngày khác thứ Sáu trong cửa sổ) phải **tự động** ra khỏi nhóm này, không cần sửa danh sách tay.

**Tách thành một hàm thuần** (ví dụ `friday_only_symbols(bar_dates_by_symbol, check_date, holidays) -> set[str]`) để test không cần DB. Phần đọc DB nằm trong `main()`, là một truy vấn duy nhất lấy các cặp (mã, ngày VN) trong cửa sổ.

### Test Task 2 (viết trước, thấy đỏ, rồi mới sửa)

Ba tiêu chí bắt buộc với mọi công cụ phát hiện: (a) bắt được lỗi thật, (b) không báo oan, (c) mẫu số đúng.
1. **(b) Không báo oan:** POM có nến 6 thứ Sáu gần nhất; kiểm **thứ Hai** và POM thiếu → **exit 0**, không WARN.
2. **(a) Vẫn bắt thứ Sáu:** cùng lịch sử đó; kiểm **thứ Sáu** và POM thiếu → **WARN**, có tên POM.
3. **(a) Không làm mù mã thường:** HPG có nến mọi ngày; kiểm thứ Hai và HPG thiếu → **WARN**.
4. **(c) Mẫu số:** 175 mã, 1 mã chỉ-thứ-Sáu, kiểm thứ Hai → báo cáo ghi **174** mã được kiểm, và ghi rõ đã loại POM.
5. **Quay lại bình thường:** POM có thêm một nến thứ Ba trong cửa sổ → **không** còn là chỉ-thứ-Sáu.
6. **Quá ít dữ liệu:** mã chỉ có 2 nến, cả hai là thứ Sáu → **không** được coi là chỉ-thứ-Sáu (chưa đủ 3), vẫn kiểm bình thường.
7. **Ngày lễ:** cửa sổ 30 ngày giao dịch đếm bằng `trading.calendar_vn.is_trading_day` với `holidays`. **Không** viết lại hàm đếm ngày.

---

## Task 3 — Hoãn hai ngày giao dịch liên tiếp thì phải leo thang

Hiện tại: backfill chưa xong thì hoãn, WARN, exit 1. **Không có giới hạn.**

**Quy tắc (chốt sẵn):** nếu backfill **chưa xong cho ngày kiểm tra** VÀ **cũng chưa xong cho ngày giao dịch liền trước**, thì exit **2**, mức **CRITICAL**, với thông điệp nói rõ "backfill-universe không hoàn thành 2 ngày giao dịch liên tiếp". Chỉ một ngày thì giữ hành vi hoãn cũ.
- Dùng lại `check_backfill_completed(log_path, target_date)` cho ngày liền trước. **Không** viết hàm đọc log thứ hai.
- Ngày giao dịch liền trước tìm bằng `is_trading_day` với `holidays`.
- **Trước khi viết:** kiểm xem `logs/backfill.log` có giữ lịch sử nhiều ngày không, hay bị ghi đè mỗi lần chạy. Dán 20 dòng có chữ `DONE` hoặc `EXIT=` gần nhất. Nếu log **bị ghi đè**, thì không thể biết ngày hôm trước: **dừng Task 3, báo cáo**, không tự nghĩ ra nơi lưu trạng thái mới.

### Test Task 3
1. Hôm nay chưa xong, hôm qua xong → exit **1** (hoãn như cũ).
2. Hôm nay chưa xong, hôm qua cũng chưa xong → exit **2**, CRITICAL.
3. Hôm nay chưa xong, ngày liền trước là thứ Sáu vì hôm nay là thứ Hai: thứ Sáu chưa xong → exit **2**. Ca này chứng minh cách tìm "ngày giao dịch liền trước" bỏ qua cuối tuần.
4. Hôm nay xong → hành vi kiểm bình thường, không bị ảnh hưởng.

---

## Kiểm thử phá hoại (Task 2 và 3)

1. Bỏ điều kiện "ngày kiểm tra không phải thứ Sáu" (loại POM cả thứ Sáu) → test 2 của Task 2 phải đỏ.
2. Đổi ngưỡng "ít nhất 3 nến" thành 1 → test 6 phải đỏ.
3. Tính ngày trong tuần theo UTC thay vì giờ VN → phải có test đỏ. **Nếu không test nào đỏ thì thêm một test bắt được lỗi này.** Nến ngày của `bars_daily` lưu ở 00:00 giờ VN, tức 17:00 UTC **ngày hôm trước**: thứ Sáu sẽ thành thứ Năm.
4. Cho ngày liền trước luôn là "hôm qua theo lịch" → test 3 của Task 3 phải đỏ.
5. Khôi phục bằng bản sao, chạy lại, sạch.

---

## Kiểm chứng

```
uv run pytest -m "not integration" -q     # mốc: 876 passed
uv run ruff check trading tests scripts
```

Chạy thật một lần (chỉ đọc): `uv run python scripts/daily_data_check.py --date 2026-09-24` hoặc cờ tương đương đang có. Kết quả mong đợi: **không** còn WARN về POM, và báo cáo ghi rõ đã loại POM. Dán nguyên văn. Nếu script gửi Telegram ở chế độ chạy tay, **tìm cờ tắt gửi trước**; không có cờ thì **không chạy thật**, chỉ báo cáo.

---

## Task 4 — Chiều thứ Hai 28/09 sau 15:10: nghiệm thu đợt 96 (CHỈ BÁO CÁO, KHÔNG SỬA)

Gộp chung với nghiệm thu đợt 92 Task 3 cùng buổi chiều. Dán bằng chứng thô cho từng câu:
1. Engine có bán IJC 400 và AAA 400 ở những bar đầu tiên của phiên không? Dán các dòng trong bảng `orders` của ngày 28/09 (giờ VN).
2. Giá bán có gần mức dự báo không (IJC khoảng 6.720 hoặc giá mở cửa nếu mở thấp hơn stop; AAA khoảng 7.470)? `fill_price_on_touch` khớp ở `min(bar.open, stop)`.
3. Log engine có dòng WARN `khong tim thay ngay mua` nào không? (Phải **không** có.)
4. Log engine có dòng WARN `da cham stop ... nhung chua ban duoc` nào không? (Phải **không** có, vì cả hai đã settle.)
5. Sau khi bán, `positions` còn vị thế nào không?

Có gì khác dự báo thì **báo nguyên văn, không sửa, không đoán nguyên nhân.**

---

## Báo cáo cho Claude

1. GitNexus impact và detect_changes.
2. Task 1: bảng tên trường POM và HPG đặt cạnh nhau, và kết luận `CÓ TRƯỜNG` / `KHÔNG CÓ`.
3. Task 2 và 3: diff, danh sách test, kiểm thử phá hoại (tên test đỏ từng bước).
4. Nguyên văn lần chạy thật ngày 24/09.
5. Pytest và ruff.
6. Mọi điều thấy ngoài phạm vi: **báo cáo, không sửa.** Đặc biệt: nếu thấy mã active nào **không có nến nào** trong 30 ngày (bị đình chỉ hẳn), chỉ liệt kê. Đó là loại khác, chưa giao.
