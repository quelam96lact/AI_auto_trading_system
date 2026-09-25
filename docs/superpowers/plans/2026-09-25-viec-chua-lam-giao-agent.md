
# Việc chưa làm — file duy nhất giao agent (chốt 25/09/2026 23:48)

Người giao: Claude (planner/auditor). Người thực thi: **Gemini Flash 3.8**.
Base: main `70b2948`.

**Việc đầu tiên: `git pull`.** Ba việc dưới đây độc lập nhau, làm theo đúng thứ tự A → B → C.

Hôm nay là **thứ Sáu**. Phiên giao dịch tiếp theo là **thứ Hai 28/09**. Nghĩa là A và B làm được ngay
đêm nay hoặc cuối tuần, không phải chờ.

| Việc | Nội dung | Làm khi nào |
|---|---|---|
| **A** | Triển khai bản vá đợt 88 vào container | **Ngay đêm nay**, thị trường đã đóng |
| **B** | Đợt 89: vá số 0 im lặng ở chuông báo ký quỹ | Sau A, lúc nào cũng được |
| **C** | Đợt 90: làm chắc máy ghi sổ lệnh + lên lịch hằng ngày | Phải xong **trước 09:00 thứ Hai 28/09** |

---

## A — Triển khai bản vá đợt 88 (ĐÊM NAY)

Cổng go-live đang **[CHẶN]** tiêu chí 8: image cũ hơn commit chạm `trading/` **1 ngày 2 giờ**. Ba commit
chưa vào container: `32fbf80` (đợt 88, `account_sync.py`), `1095c37`, `6f83e03`.

**Quan trọng:** lỗi số 0 im lặng **vẫn đang tái diễn** cho tới khi triển khai — dòng thứ 12 sinh ra
24/09 lúc 23:04 chính là bằng chứng. Bản vá nằm trong git mà không nằm trong container thì chưa có tác dụng.

Làm theo **đúng** brief đợt 86 (`docs/superpowers/plans/2026-09-24-brief-dot-86-trien-khai-sau-phien.md`),
từ Bước 1 đến Bước 8, với ba điều chỉnh:

1. **Bỏ Bước 0 mục 2** (điều kiện "phải có dòng stream-health 15:10 của hôm nay"). Job 25/09 đã chạy xong
   lúc 15:10, không cần chờ nữa.
2. **Giá trị kỳ vọng ở Bước 1 đã đổi**: `collector:latest` = **`681fede19cf6`**, `engine:latest` =
   **`7fef8868bc2f`** (tôi đo lúc 23:48). Đây là giá trị phải thấy **trước** khi build.
3. **Bước 5 thêm một phép kiểm** cho bản vá đợt 88:
   ```powershell
   docker exec ai_auto_trading_system-collector-1 grep -c "_find_missing_balance_fields" /app/trading/collector/account_sync.py
   ```
   Phải ra **≥ 1**. Tôi đã kiểm trên container hiện tại: ra **0**. Nên phép kiểm này phân biệt được thật.

**Bước 6 khác đợt 86:** engine khởi động lại **sau giờ phiên thứ Sáu**, nên `warm-up ... until` phải là
**`2026-09-25 07:45:00+00:00`** (= 25/09 14:45 VN), và vòng chờ đợt 81 phải **thoát ngay** (không có dòng
"da co du lieu bars", không có CRITICAL chờ). Vị thế vẫn phải là `{"IJC": 400, "AAA": 400}`.

**Giữ nguyên toàn bộ điều kiện dừng và quy trình rollback của đợt 86.**

---

## B — Đợt 89: số 0 im lặng ở chuông báo ký quỹ

Brief đã có: `docs/superpowers/plans/2026-09-25-brief-dot-89-so-0-im-lang-o-chuong-bao-ky-quy.md`
(commit `2b0cc36`). Đọc và làm đúng như viết.

Nhắc lại hai chỗ dễ vấp, đừng bỏ qua:
- **Ca 6 phải viết TRƯỚC khi sửa** và phải xanh trên code cũ (tỷ lệ 10, cả ba ngưỡng thiếu → `CRITICAL`).
  Đó là bằng chứng lỗi tồn tại thật. Dán **cả hai** kết quả: trên code cũ và sau khi sửa.
- **Ca 2 là số 0 thật** (tài khoản chưa dùng ký quỹ) → phải **lưu bình thường, không WARN**. Kiểm thử phá
  hoại phải **giữ xanh** ca 1, 2, 7.

---

## C — Đợt 90: làm chắc máy ghi sổ lệnh, trước thứ Hai

Phiên pilot 25/09 chạy được nhưng lộ ba vấn đề. Việc này **phải xong trước 09:00 thứ Hai**, vì từ thứ
Hai là ghi thật hằng ngày, cần khoảng 20 phiên mới đủ để sàng lọc.

### C1 — Test cho nhánh tự kết nối lại

Nhánh này được viết **giữa phiên, dưới áp lực thời gian**, và **chưa có test nào** (vẫn đúng 5 test cũ).
Nó là thứ giữ cho cả kế hoạch 20 phiên không mất dữ liệu, nên không được để không có test.

Tách phần quyết định "có nên kết nối lại không" thành **hàm thuần**, rồi test:
1. Kết nối đang sống → **không** kết nối lại.
2. Kết nối đã đóng, chưa tới `--until` → **kết nối lại**.
3. Kết nối đã đóng, **đã quá** `--until` → **không** kết nối lại, dừng sạch. (Ca dễ sai: kết nối lại vô
   hạn sau giờ đóng cửa.)
4. Kết nối lại thất bại liên tiếp → có giới hạn số lần thử và **khoảng nghỉ tăng dần**, không quay tít.
5. **Kiểm thử phá hoại:** vô hiệu hoá điều kiện `--until` ở ca 3, xác nhận đúng ca 3 đỏ.

### C2 — Tách khoảng lặng thị trường khỏi thời gian máy ghi chết

Báo cáo 25/09 ghi "khoảng lặng dài nhất 3998,91 giây". Con số đó **không phải thị trường im** — nó là
67 phút **máy ghi chết** (10:00:33 → 11:07). Bộ đo đang lẫn lộn hai thứ khác hẳn nhau, và như vậy nó
không dùng được để đánh giá chất lượng dữ liệu.

Yêu cầu: máy ghi ghi lại **các quãng nó không kết nối** (mốc mất, mốc nối lại), rồi thống kê cuối phiên
báo **hai đại lượng riêng**:
- **Thời gian máy ghi mất kết nối**: tổng, và danh sách từng quãng.
- **Khoảng lặng thị trường**: chỉ tính trong các quãng máy ghi **đang** kết nối. Quãng mất kết nối phải bị
  **loại khỏi** phép đo này, đúng cách nghỉ trưa đang bị loại.

Test: dựng chuỗi có một quãng mất kết nối 600 giây và một khoảng lặng thật 15 giây → phải báo **đúng hai
con số riêng**, và khoảng lặng thị trường **không** được là 600. Kèm kiểm thử phá hoại.

### C3 — Lên lịch ghi hằng ngày

Hiện phải chạy tay. Thêm vào `scripts/sched.sh` (hoặc đúng cơ chế lịch dự án đang dùng — **đọc file đó
trước, bắt chước khuôn mẫu có sẵn, đừng phát minh cách mới**) một tác vụ:

- Khởi động máy ghi lúc **08:40** mỗi ngày giao dịch, `--until 14:46`.
- **Không chạy** cuối tuần và ngày lễ — dùng lại `is_trading_day()` từ `trading/calendar_vn.py`, không tự
  viết lại lịch.
- Ghi log ra `logs/orderbook-recorder.log` theo đúng khuôn mẫu log của các job khác.

**Mã hợp đồng KHÔNG được ghim cứng.** `41I1GA000` đáo hạn **15/10/2026**; sau đó phải là `41I1GB000`.
Ghim cứng là lặp lại đúng lỗi `derivative_backtest.py` đã mắc (mã hết hạn nằm trong code hơn một tháng).
Dùng lại `last_session_date_needed`-kiểu suy luận: chọn hợp đồng VN30 `41I1*` còn sống có `lastTradingDate`
gần nhất trong tương lai. Nếu cần danh sách hợp đồng, dùng lại hàm đã có ở
`scripts/measure_derivative_contract_volume.py` (`filter_living_contracts`, `identify_front_month`) —
**import lại, đừng chép**.

Test cho phần chọn mã: 14/10 → chọn `41I1GA000`; 16/10 → chọn `41I1GB000`.

---

## Ràng buộc chung

- Việc A **được phép** build và restart `collector` + `engine`. Đó là mục đích của nó. **Không** đụng
  `postgres`, `nats`, `nats-test`, `grafana`.
- Việc B và C **không** được restart/build container nào.
- **Không** gọi method đặt lệnh, trên bất kỳ tài khoản nào.
- **Không** xoá/sửa dòng nào trong DB. 12 dòng `nav = 0` là bằng chứng lịch sử.
- **Không** commit, **không** push. Tôi audit rồi commit.
- Nền hiện tại: **797 passed**, ruff sạch.

## Báo cáo cho Claude

Báo **theo từng việc A / B / C**, đừng gộp:
1. **A**: output từng bước 1→8 của đợt 86, gồm cả phép kiểm `_find_missing_balance_fields` và dòng
   `warm-up ... until`. Nếu đã rollback: nêu điều kiện dừng nào kích hoạt.
2. **B**: kết quả ca 6 **trên code cũ** và sau khi sửa; 8 nhóm test + kiểm thử phá hoại (ca nào đỏ, ca nào
   **vẫn xanh**).
3. **C**: kết quả test C1, C2, C3 + kiểm thử phá hoại; và **tên tác vụ lịch** đã thêm cùng khuôn mẫu bạn
   bắt chước.
4. `uv run pytest -m "not integration" -q` (nền **797**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng, kể cả ngoài phạm vi được hỏi.

---

## Ghi chú — việc KHÔNG giao, để chủ dự án thấy toàn cảnh

| Việc | Ai | Ghi chú |
|---|---|---|
| **Biểu phí phái sinh thật** | **chủ dự án** | Vẫn là thứ **chặn** duy nhất. Hướng phái sinh đã đi hết phần sàng lọc (không cần phí) và không tiến thêm được tới backtest. Cần nguồn từ SSI/HNX/VSD. |
| Sàng lọc đặc trưng dòng lệnh | tôi, sau ~20 phiên | Sớm nhất khoảng giữa tháng 10. Dùng đúng phương pháp đăng ký trước của đợt 85. |
| Lỗ giữa phiên: GAP-1 chỉ cảnh báo | chờ quyết | Hướng 2 brief 79, tôi không khuyến nghị |
| T3/T4: đặt+huỷ lệnh thật | **chủ dự án** | Cần phiên sống + quyết định |
| Nguyên nhân mất kết nối 10:00:33 ngày 25/09 | **không xác định** | Tôi đã tự bác bỏ giả thuyết "xoay token": sau khi nối lại, kết nối sống 3g39 trong khi token vẫn xoay liên tục. Một lần xảy ra thì chưa kết luận được. C1+C2 làm cho nó **không gây hại** thay vì đi tìm nguyên nhân. |
