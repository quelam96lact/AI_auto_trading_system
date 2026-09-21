# Brief đợt 77 — Mở rộng sàng lọc tín hiệu ra nhiều mã, kiểm tỷ lệ trúng so với ngẫu nhiên

Ngày giao: 21/09/2026 (thứ Hai, sau phiên).
Base: main `c4f6dad`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao đợt này, sau khi đợt 76 đã cho kết luận âm

Đợt 76 sàng lọc 6 đặc trưng kỹ thuật trên đúng 3 mã (HPG/IJC/AAA) — 18/18 KHÔNG TÍN HIỆU. Nhưng 3
mã là mẫu rất nhỏ để nói "đặc trưng này vô dụng trên toàn bộ cổ phiếu VN" — có thể HPG/IJC/AAA chỉ
là ba mã không hợp với các đặc trưng đó, trong khi đặc trưng vẫn có ích trên mã khác. Dự án đã có
tiền lệ dùng cỡ mẫu lớn để tránh đúng bẫy này (đợt 64 kiểm regime-timing trên 1.308 mã × 11 năm,
không chỉ vài mã).

Đợt này **không đổi phương pháp đo** (đã đóng ở đợt 76) — chỉ chạy đúng công cụ đó trên một **tập
mã rộng hơn nhiều**, rồi hỏi một câu khác: *"trong số nhiều mã độc lập, đặc trưng nào trúng
`CO_TIN_HIEU` nhiều hơn mức ngẫu nhiên sẽ cho?"* Đây là câu hỏi thống kê khác — không phải chạy lại
để "tìm được số đẹp hơn".

---

## 1. Ràng buộc

- **Không sửa `scripts/screen_vn_signal_candidates.py`** — dùng nguyên hàm `screen_symbol()`,
  chỉ gọi nó nhiều lần với mã khác nhau. Nếu bạn thấy cần sửa hàm đó để chạy hàng loạt tiện hơn
  (ví dụ thêm tham số), **được phép**, nhưng phải giữ nguyên hành vi khi gọi cho 1 mã (không đổi
  kết quả của đợt 76 — kiểm lại bằng cách chạy lại đúng 3 mã HPG/IJC/AAA, phải ra **cùng** số như
  đợt 76 đã ghi).
- **Không đổi 6 đặc trưng, không đổi công thức gắn cờ, không đổi cách tính ngưỡng hoán vị** (Spearman
  + hoán vị khối theo ngày giao dịch + FWER cho 6 đặc trưng — nguyên xi đợt 76).
- **Không thêm dependency.**
- IS = 2016-01-01 → 2025-12-31, 2026 niêm phong — như đợt 76.
- Không commit, không push.

---

## Task 1 — Chọn tập mã: 50 mã thanh khoản cao nhất, không phải mã tuỳ ý

**Không** chọn ngẫu nhiên, không chọn mã "trông quen". Tiêu chí: 50 mã có **giá trị giao dịch bình
quân ngày cao nhất** trong khoảng IS (2016-2025), sau khi loại 246 mã trong `exclusions.txt` (đúng
danh sách đợt 61/64 đã dùng — dữ liệu điều chỉnh không đáng tin cho các mã đó).

Viết truy vấn (hoặc script phụ trợ) tính `AVG(close * volume)` mỗi mã trên `bars_daily` trong
khoảng IS, loại mã trong `exclusions.txt`, lấy 50 mã đứng đầu. **In danh sách 50 mã đó và giá trị
bình quân của từng mã ra báo cáo** — đây là bằng chứng bạn chọn đúng tiêu chí, không phải bịa.

**HPG/IJC/AAA gần như chắc chắn không nằm trong 50 mã thanh khoản cao nhất** (chúng được chọn cho
live vì lý do khác — xem `config/config.yaml` dòng 1-5). Không sao — mục tiêu đợt này là một mẫu
**độc lập, rộng**, không phải xác nhận lại 3 mã cũ.

---

## Task 2 — Chạy sàng lọc cho cả 50 mã, xử lý lỗi từng mã riêng biệt

Gọi `screen_symbol()` (hoặc phiên bản đã tách tham số của bạn) cho từng mã trong 50 mã.

**Bắt buộc: một mã lỗi không được làm hỏng cả lô.** `screen_symbol()` ném `RuntimeError` nếu chốt
an toàn đối chứng thất bại, và `ValueError` nếu không đủ dữ liệu (ít hơn 50 nến IS). Với tập 50 mã
thanh khoản cao, khả năng cao gặp ít nhất một mã có lịch sử ngắn hơn 10 năm (niêm yết muộn) hoặc dữ
liệu bất thường. Bọc từng mã trong `try/except`, **ghi lại mã nào bị loại và vì sao** (không âm
thầm bỏ qua), tiếp tục với mã kế tiếp.

Số lần hoán vị: giữ 500 như đợt 76 nếu thời gian chạy chấp nhận được (đợt 76 đo ~10s/mã cho 500 lần
→ 50 mã ước ~8-9 phút). Nếu bạn thấy quá lâu, giảm xuống nhưng **nêu rõ số đã dùng và lý do**.

---

## Task 3 — Tổng hợp: tỷ lệ trúng có bất thường so với ngẫu nhiên không?

Đây là phần trả lời câu hỏi thật của đợt này.

### 3.1. Đếm

Với mỗi đặc trưng trong 6 đặc trưng, đếm: trong số N mã sàng lọc thành công (N ≤ 50, sau khi loại
mã lỗi ở Task 2), có bao nhiêu mã gắn cờ `CO_TIN_HIEU`.

### 3.2. So với kỳ vọng ngẫu nhiên

Ngưỡng hoán vị khối P95 nghĩa là: **nếu đặc trưng thật sự không có thông tin gì**, xác suất một mã
bất kỳ trúng `CO_TIN_HIEU` là ~5% (đúng định nghĩa của P95). Với N mã độc lập, số mã trúng "do may
rủi" kỳ vọng ≈ `0,05 × N`, và dao động quanh đó theo phân phối nhị thức.

Với mỗi đặc trưng, tính:
- Số mã trúng thực tế.
- Số mã trúng kỳ vọng nếu hoàn toàn ngẫu nhiên (`0,05 × N`).
- Có "trúng nhiều bất thường" không — dùng phép kiểm nhị thức đơn giản (ví dụ: xác suất quan sát
  được ≥ số trúng thực tế nếu tỷ lệ nền thật sự là 5%, tính bằng công thức nhị thức tay hoặc
  `scipy` **nếu đã có sẵn trong dependency** — nếu chưa có, tự viết công thức nhị thức bằng Python
  thuần, đừng thêm `scipy` chỉ vì việc này).

**Không cần độ chính xác thống kê hàn lâm** — đây là phép sàng bước hai, không phải kết luận cuối
cùng. Mục tiêu là phân biệt "0-3/50 mã trúng, đúng như nhiễu" với "10+/50 mã trúng, đáng nhìn kỹ
hơn".

### 3.3. Báo cáo trung thực, không tự ý mở rộng thêm

- Nếu **mọi đặc trưng** đều có tỷ lệ trúng ≈ 5% (trong khoảng dao động bình thường của nhiễu): kết
  luận nhất quán với đợt 76 — ghi nhận, **không tìm cách "cứu" bằng cách đổi chân trời hay ngưỡng**.
- Nếu **một đặc trưng nào đó** có tỷ lệ trúng cao bất thường (ví dụ >15-20% trên 50 mã): đây là
  phát hiện đáng báo cáo chi tiết — liệt kê **đúng những mã nào** trúng, để tôi tự kiểm tra có
  điểm chung nào giữa chúng không (cùng ngành? cùng thanh khoản? cùng giai đoạn niêm yết?). **Không
  tự suy diễn nguyên nhân, không tự mở rộng sang bước xác nhận tiếp** — chỉ liệt kê sự kiện.

---

## Task 4 — Test

1. Test tái hiện: chạy `screen_symbol()` cho đúng 3 mã HPG/IJC/AAA với cùng tham số đợt 76, khẳng
   định ra **cùng** `rho_sau`/ngưỡng/cờ như đợt 76 đã công bố (dán số so sánh cạnh nhau trong báo
   cáo). Nếu khác, đó là bạn đã vô tình đổi hành vi hàm gốc — dừng lại, tìm nguyên nhân trước khi
   đi tiếp.
2. Test hàm đếm tỷ lệ trúng / so kỳ vọng nhị thức (Task 3.2) trên dữ liệu tổng hợp có đáp số biết
   trước (ví dụ: dựng 100 "mã giả" với xác suất trúng đúng 5% theo thiết kế, xác nhận hàm không báo
   "bất thường"; dựng 100 mã giả với 30% trúng, xác nhận hàm báo "bất thường").
3. `uv run pytest -m "not integration" -q` và `uv run ruff check scripts tests trading` — số test
   trước → sau, đọc từ màn hình.

---

## 2. Không làm

- Không đổi phương pháp đo của đợt 76 (đặc trưng, công thức gắn cờ, cách tính ngưỡng).
- Không tự ý thêm chân trời dự báo khác (`fwd_ret_5d`...) — nếu muốn, phải xin trước, không phải
  sau khi thấy 18/18 hay N/50 không ra gì.
- Không tự suy diễn nguyên nhân nếu phát hiện tỷ lệ trúng bất thường — chỉ liệt kê sự kiện.
- Không thêm dependency (kể cả `scipy` — tự viết công thức nhị thức).
- Không commit, không push.

## 3. Báo cáo cho Claude

1. `git diff` / danh sách file mới.
2. Danh sách 50 mã đã chọn kèm giá trị giao dịch bình quân — bằng chứng tiêu chí chọn đúng.
3. Danh sách mã bị loại ở Task 2 (nếu có) kèm lý do.
4. Test tái hiện Task 4.1 — số so sánh cạnh nhau với đợt 76.
5. Bảng tổng hợp Task 3: 6 đặc trưng × (số mã trúng / N / kỳ vọng ngẫu nhiên / có bất thường không).
6. Nếu có đặc trưng bất thường: danh sách mã cụ thể trúng, không suy diễn thêm.
7. Số test trước → sau đọc từ màn hình, `ruff` sạch.
