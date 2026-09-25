# Lịch chạy hôm nay 25/09/2026 (thứ Sáu) — file duy nhất giao agent

Người giao: Claude (planner/auditor). Người thực thi: **Gemini Flash 3.8**.
Base: main `d3c1b86`.

---

## 0. Đọc cái này trước — có brief đã bị sửa sau khi bạn nhận

Báo cáo Task 0 của bạn ghi kế hoạch sáng nay là **đi thẳng vào 09:03**. Đó là **bản brief cũ**. Đêm qua
tôi đã thêm **Task 0b** vào brief 87 (commit `d3c1b86`).

**Việc đầu tiên: `git pull`, rồi đọc lại hai file này từ đầu.** Đừng làm theo bản bạn đang giữ.

| Brief | File | Trạng thái |
|---|---|---|
| Đợt 87 | `docs/superpowers/plans/2026-09-24-brief-dot-87-mo-huong-so-lenh-vn30f.md` | **Task 0 XONG, đã audit + commit `5a85205` — KHÔNG làm lại.** Còn Task 0b, 1, 2. |
| Đợt 88 | `docs/superpowers/plans/2026-09-24-brief-dot-88-va-loi-so-0-im-lang-o-dong-bo-tai-khoan.md` | Chưa làm gì. Task 1 đêm qua **đã bỏ sót**. |

---

## 1. Việc đêm qua bỏ sót, và vì sao không chặn

Đợt 88 Task 1 (quan sát tài khoản trong khung 22:06–22:51) **không chạy** — tôi kiểm lúc 06:47 sáng nay:
không có `scripts/probe_account_balance_22h.py`, không có thư mục `data/`.

Không sao cả, vì hai lý do:
- Hiện tượng chỉ xảy ra khoảng **8/37 đêm**, nên đêm qua khả năng cao cũng không có gì để bắt.
- **Task 2 của đợt 88 không phụ thuộc Task 1.** Lỗi `float(equity.get("withdrawable") or 0)` biến trường
  thiếu thành số 0 là **chứng minh được từ code**, không cần bắt tận tay. Brief 88 đã ghi rõ điều này.

Task 1 dời sang **22:00 tối nay**, và chỉ còn vai trò **xác nhận** trường nào bị thiếu, không còn là điều
kiện để vá.

---

## 2. Lịch chạy — làm đúng thứ tự

| Khung giờ | Việc | Nguồn |
|---|---|---|
| **Bây giờ → 08:20** | **Đợt 88 Task 2 + Task 3**: vá lỗi số 0 im lặng, đếm lại mẫu số | brief 88 |
| **08:20 → 08:40** | **Đợt 87 Task 0b**: chạy thử máy ghi 90 giây | brief 87 |
| 09:03 → 09:05 | Đợt 87 Task 1: thăm dò 2 phút + giám sát collector | brief 87 |
| 09:05 → 14:46 | Đợt 87 Task 2: ghi thử phần còn lại của phiên | brief 87 |
| Sau 15:10 | Đọc `logs/stream-health.log`: độ phủ phiên 25/09 phải **vẫn 100%** | brief 87 Task 2 bước 3 |
| **22:00 → 23:00** | Đợt 88 Task 1: quan sát khung 22h (làm lại phần bỏ sót) | brief 88 |

**Vì sao đợt 88 Task 2 làm trước:** nó không cần thị trường, và từ giờ tới 08:20 là khoảng thời gian duy
nhất hôm nay không có việc phụ thuộc giờ. Đừng để trống khoảng này rồi tối mới làm.

---

## 3. Ba cửa dừng — vi phạm thì DỪNG, báo cáo, không tự chữa

1. **Task 0b lỗi mà không sửa kịp trước 09:00** → **bỏ Task 1 và Task 2 hôm nay**. Mất một phiên dữ liệu
   còn hơn dành cả phiên để gỡ lỗi. Vẫn làm đợt 88 Task 1 tối nay.
2. **Task 1 thấy collector bị ngắt kết nối hoặc lỗi auth**, hoặc nến cổ phiếu 09:05–09:15 thiếu, hoặc
   `lag_ms` > 60 giây → **không sang Task 2**. Không restart gì cả, collector tự kết nối lại; chỉ ghi lại
   bao lâu thì nó hồi phục.
3. **Độ phủ luồng phiên 25/09 sau 15:10 thấp hơn 100%** → đó là bằng chứng máy ghi gây hại, **dù** log
   collector không có lỗi. Báo ngay.

---

## 4. Hai chỗ tôi đã biết là dễ sai, đừng vấp

**Đợt 88 Task 2 — ca test dễ sai nhất là "số 0 thật":** `withdrawable = 0` và `totalDebt = 0` **có mặt
thật** trong phản hồi thì phải **ghi bình thường**, không WARN. Bản vá chặn luôn cả số 0 hợp lệ là sai
kiểu khác. Kiểm thử phá hoại phải làm đỏ đúng các ca **thiếu trường** (2, 3, 4, 6) và **giữ xanh** ca 1
và ca 5.

**Đợt 87 Task 0b — file rỗng tin là BÌNH THƯỜNG:** chạy lúc 08:30 thì thị trường chưa khớp lệnh, nên file
`.gz` gần như không có tin nào. Điều cần kiểm là file **tồn tại và đọc lại được**, và thống kê **không nổ
khi số tin bằng 0** (chia cho 0, `max()` trên danh sách rỗng). Đừng báo "lỗi, không có dữ liệu".

---

## 5. Ràng buộc chung cho cả ngày

- **Không** restart / build / stop bất kỳ container nào. Collector và engine đang chạy thật, engine đang
  giữ vị thế IJC 400 / AAA 400.
- **Không** gọi method đặt lệnh nào, trên bất kỳ tài khoản nào.
- **Không** ghi sổ lệnh vào Postgres. Ngoại lệ duy nhất và là việc đúng: `ensure_authenticated` tự ghi
  token vào `ssi_auth_state`, y như collector vẫn làm.
- **Không** xoá hay sửa dòng nào đã có trong DB. 11 dòng `nav = 0` là bằng chứng lịch sử.
- **Không** commit, **không** push. Tôi audit rồi commit.
- Nền hiện tại: **790 passed**, ruff sạch.

---

## 6. Báo cáo cho Claude

Báo **theo từng đợt**, đừng gộp:
1. **Đợt 88**: kết quả 7 nhóm test + kiểm thử phá hoại (test nào đỏ, test nào **vẫn xanh**), và truy vấn
   đếm ở Task 3 (`dong_0` phải **vẫn là 11**).
2. **Đợt 87 Task 0b**: bốn xác nhận, và đã sửa gì nếu có.
3. **Đợt 87 Task 1**: T0, output máy ghi, **mọi** dòng log collector khớp mẫu (hoặc nói rõ "0 dòng"),
   `lag_ms` các nến 09:05–09:15.
4. **Đợt 87 Task 2**: thống kê cuối phiên, hai lần kiểm giữa phiên, dòng `stream-health` 25/09 nguyên văn.
5. **Đợt 88 Task 1 (tối)**: số lần gọi, và **kết quả thật** — bắt được bất thường (kèm danh sách khoá +
   giá trị thô) hay không. Nói thẳng nếu không bắt được; đó là kết quả hợp lệ.
6. `uv run pytest -m "not integration" -q` và `uv run ruff check trading tests scripts`.
7. Bất kỳ điều gì khác thường. Nói thẳng, kể cả khi ngoài phạm vi được hỏi.
