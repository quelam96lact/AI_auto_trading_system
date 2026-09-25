
# Brief đợt 93 — Thăm dò khả thi: dữ liệu sổ lệnh có dựng được đặc trưng không?

Ngày giao: 26/09/2026 (thứ Bảy).
Base: main `82d60d1`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Không phụ thuộc giờ thị trường — làm được ngay, cuối tuần. **Độc lập với đợt 92 Task 3** (nghiệm thu
chiều thứ Hai), hai việc không đụng nhau.

---

## 0. Vì sao làm bây giờ, không đợi đủ 20 phiên

Kế hoạch hiện tại: thu khoảng **20 phiên** (tới giữa tháng 10) rồi mới sàng lọc tín hiệu. Rủi ro của kế
hoạch đó: nếu dữ liệu **thiếu một thứ cốt yếu** để dựng đặc trưng, ta chỉ phát hiện sau **ba tuần**.

Hiện đã có **một phiên thật** (705.329 tin, 25/09). Đủ để trả lời câu hỏi khả thi — **không** đủ để đo
tín hiệu. Đây là phép thử đường ống trên mẫu nhỏ trước khi đầu tư dài, không phải phép đo.

**Điều tôi muốn biết:** từ dữ liệu này có dựng được một bảng đặc trùng theo lưới thời gian đều, với tỷ lệ
thiếu dữ liệu biết rõ, hay không? Nếu không thì phải sửa **máy ghi** ngay tuần này, trước khi thu thêm.

---

## 1. Ràng buộc

- Được thêm: `scripts/build_orderbook_features.py` (**file mới**) + test của nó.
- **Không** sửa `trading/`, không sửa máy ghi, không sửa công cụ nghiệm thu.
- **Chỉ đọc** file `.gz` đã có. Không ghi vào DB. Không gọi SSI (không cần).
- **Không** restart/build container. **Không** đặt lệnh. Không commit, không push.
- Khôi phục sau kiểm thử phá hoại: sao lưu đúng file ra **ngoài** repo rồi copy lại. **Không**
  `git checkout`/`restore`/`stash` diện rộng.
- Nền hiện tại: **830 passed**, ruff sạch.

---

## Task 1 — Dựng bảng đặc trưng theo lưới 1 phút

Đọc `data/orderbook/41I1GA000/2026-09-25.jsonl.gz`, gộp về **lưới 1 phút** trong giờ khớp lệnh liên tục.
Mỗi hàng là một phút, các cột:

| Cột | Tính từ | Công thức |
|---|---|---|
| `minute` | — | mốc phút (giờ VN) |
| `n_quote`, `n_trade` | đếm | số tin mỗi loại trong phút đó |
| `mid_close` | QUOTE **cuối** phút | `(bid_prices[0] + ask_prices[0]) / 2` |
| `spread` | QUOTE cuối phút | `ask_prices[0] − bid_prices[0]` |
| `imb_top1` | QUOTE cuối phút | `(bid_volumes[0] − ask_volumes[0]) / (bid_volumes[0] + ask_volumes[0])` |
| `imb_top5` | QUOTE cuối phút | như trên nhưng tổng 5 bước giá đầu mỗi bên |
| `ofi` | **toàn bộ** TRADE trong phút | `Σ(qty khi side='B') − Σ(qty khi side='S')` |
| `trade_qty` | TRADE | tổng `quantity` trong phút |

**Ba quyết định tôi chốt sẵn, đừng tự đổi:**

1. **Đơn vị điểm, không phần trăm** — giống đợt 85. Sổ lệnh phái sinh tính theo điểm, mỗi điểm 100.000 VNĐ.
2. **QUOTE cuối phút, không phải trung bình** — đây là ảnh chụp trạng thái sổ lệnh tại thời điểm quyết định.
   Trung bình hoá sổ lệnh trong một phút là trộn nhiều trạng thái không cùng tồn tại.
3. **`imb` chuẩn hoá về khoảng [−1, 1]** bằng cách chia cho tổng, để so sánh được giữa các phút có độ dày
   sổ lệnh rất khác nhau.

**Phút không có QUOTE nào** → các cột từ QUOTE là `None` (**không** nội suy, **không** lấy phút trước).
Phút không có TRADE → `ofi = 0`, `trade_qty = 0` (không có lệnh khớp là **giá trị thật**, khác với không
có dữ liệu).

---

## Task 2 — Báo cáo chất lượng, đây mới là sản phẩm chính

In ra:
1. **Số hàng** dựng được, và khoảng thời gian bao phủ.
2. **Tỷ lệ thiếu từng cột** (bao nhiêu % hàng có `None`).
3. **Số phút liên tiếp thiếu dài nhất**, kèm mốc bắt đầu — kỳ vọng nó bắt được đúng 67 phút mất kết nối
   10:00→11:07.
4. **Thống kê mô tả** mỗi cột số: min / trung vị / max. Mục đích là **phát hiện giá trị vô lý**, không phải
   để phân tích: `spread` âm là không thể; `imb` ngoài [−1, 1] là sai công thức; `mid_close` lệch xa vùng
   1900–2000 là sai đọc dữ liệu.
5. **Số hàng dùng được** = hàng có **đủ** `mid_close`, `imb_top5`, `ofi`. Đây là con số quyết định: nhân với
   20 phiên sẽ cho biết mẫu cuối cùng lớn cỡ nào.

---

## 3. CẤM — quan trọng nhất của brief này

**Không tính tương quan, không đo tín hiệu, không kiểm định gì.** Một phiên là vô nghĩa về mặt thống kê, và
nhìn vào tương quan trên một phiên là cách chắc chắn nhất để tự lừa mình. Đợt 85 đã cho thấy một con số
trông như phát hiện lớn chết ngay khi hiệu chỉnh đa so sánh.

**Không tự thêm đặc trưng** ngoài 8 cột trên. Danh sách đặc trưng cho phép đo thật sẽ được **đăng ký trước**
trong brief sàng lọc, sau khi có đủ phiên — đúng cách đợt 85 đã làm.

**Không kết luận dữ liệu "tốt" hay "hứa hẹn".** Chỉ báo cáo con số.

---

## 4. Kiểm chứng

Test trên dữ liệu **dựng tay**, không dùng file thật:
1. Một phút có 3 QUOTE và 2 TRADE → kiểm **từng cột bằng số tính tay**, gồm cả việc `mid_close` lấy đúng
   QUOTE **cuối**, không phải đầu hay trung bình.
2. `ofi` có dấu đúng: 1 lệnh B 10 và 1 lệnh S 4 → `ofi = 6`, `trade_qty = 14`.
3. Phút không có QUOTE → cột QUOTE là `None`; phút không có TRADE → `ofi = 0` (**không** phải `None`).
   Ca này phân biệt "không có dữ liệu" với "không có giao dịch" — dễ sai nhất.
4. `imb_top1` ở hai biên: chỉ có bên mua → `+1`; chỉ có bên bán → `−1`; cân bằng → `0`.
5. **Ca biên chia cho 0:** cả `bid_volumes[0]` và `ask_volumes[0]` đều 0 → `imb` là `None`, **không nổ**.
6. Dò khoảng thiếu: chuỗi dựng tay có 5 phút trống liên tiếp → báo đúng 5 và đúng mốc bắt đầu.
7. **Kiểm thử phá hoại:** đổi `mid_close` sang lấy QUOTE **đầu** phút, xác nhận đúng ca 1 đỏ.

**Chạy thật trên file 25/09** và dán nguyên văn toàn bộ báo cáo Task 2.

---

## 5. Báo cáo cho Claude

1. Kết quả 7 nhóm test + kiểm thử phá hoại.
2. **Nguyên văn** báo cáo chất lượng chạy trên file 25/09.
3. Xác nhận đã sao lưu ra ngoài repo khi phá hoại, không dùng lệnh git diện rộng.
4. `uv run pytest -m "not integration" -q` (nền **830**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — **đặc biệt** nếu bạn thấy dữ liệu thiếu thứ gì cần cho 8 cột trên. Đó chính
   là câu hỏi của brief này, nên phát hiện kiểu đó là **kết quả có giá trị**, không phải thất bại.

---

## 6. Ghi chú của planner — việc chưa giao

**Roll hợp đồng 15/10.** `41I1GA000` đáo hạn 15/10; từ 16/10 máy ghi sẽ tự chuyển sang `41I1GB000`. Dữ liệu
sổ lệnh khi đó trải hai hợp đồng có mức giá lệch nhau — cùng bài toán panama như nến. **Chưa giao**, vì đặc
trưng ở đây (`imb`, `ofi`, `spread`) là **đại lượng tương đối trong từng phút**, nên có thể không cần nối
mức giá; chỉ `mid_close` mới cần. Sẽ quyết sau khi có báo cáo đợt 93.

**Leo thang cho `daily_data_check`.** Nếu `backfill-universe` hỏng lâu dài thì trình kiểm tra hoãn mãi và chỉ
phát WARN, không bao giờ báo đỏ. Chưa có cơ chế leo thang sau N ngày hoãn liên tiếp. Ghi nhận, chưa giao.

**Việc chặn duy nhất vẫn là biểu phí phái sinh** — cần chủ dự án lấy từ SSI/HNX/VSD kèm nguồn. Việc thu và
xử lý dữ liệu sổ lệnh **không** chờ biểu phí; chỉ bước backtest mới cần.
