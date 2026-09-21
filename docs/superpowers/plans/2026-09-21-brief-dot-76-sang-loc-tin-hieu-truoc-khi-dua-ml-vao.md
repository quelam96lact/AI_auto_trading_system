# Brief đợt 76 — Sàng lọc tín hiệu kỹ thuật cho 3 mã đang chạy sống, bước đầu trước ML

Ngày giao: 21/09/2026 (thứ Hai, sau phiên).
Base: main `b52f788`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao brief này, và vì sao không phải "chọn crypto hay VN"

Chủ dự án đặt câu hỏi: đưa ML vào crypto hay VN stocks? Tôi không tự chọn hộ — nhưng có bằng chứng
đo được khiến câu hỏi đó **chưa cần trả lời ngay**, vì cả hai nhánh đang có sẵn đều đã bị đóng bởi
chính phép đo của dự án:

- **Crypto**: đợt 42 §3 đo 27/27 cặp (9 đặc trưng phi giá × 3 chân trời) **không vượt ngưỡng hoán
  vị** — bộ đặc trưng hiện có rỗng thông tin. Đã đóng, không đo lại (xem
  [[crypto-nonprice-features-have-no-signal]] nếu bạn có quyền đọc memory; nếu không, xem
  `docs/superpowers/research/2026-09-12-dot-42-sua-can-dong-va-event-study.md`).
- **VN stocks (regime-timing theo độ rộng thị trường)**: đợt 64 kiểm định theo từng năm (2016–2026,
  sau khi đợt 62 sửa lỗi đòn bẩy ảo) — **thua buy-and-hold thuần 10/11 năm**. Đã đóng.
- **VN stocks (chiến lược octopus_pullback đang chạy sống)**: các backtest trước đây đều thua trước
  phí (ghi nhận từ trước phiên này).

Ba lần đo, ba kết luận âm. Trước khi bàn "ML nên dùng model gì" hay "thêm thư viện nào vào Docker",
câu hỏi phải trả lời trước là: **có tồn tại MỘT đặc trưng nào — ở bất kỳ đâu trong dữ liệu VN stocks
hiện có — mang tín hiệu dự đoán thật, đo được bằng chính công cụ đã kiểm chứng của dự án?** Nếu
không, ML không có gì để học — không mô hình nào tạo ra thông tin từ hư vô.

Đợt này **không xây ML**. Nó chỉ chạy phép sàng đã có (đợt 71/72, thống nhất tại
`scripts/leakage_audit.py`) trên một tập đặc trưng kỹ thuật đơn giản, cho đúng 3 mã đang có **vị
thế thật, đang chạy sống**: HPG, IJC, AAA. Không mở rộng ra rổ 1.308 mã — đó là quyết định lớn hơn,
để sau nếu bước này ra tín hiệu dương.

---

## 1. Ràng buộc

- **Không thêm dependency** (repo thuần Python; quyết định thư viện ML vẫn còn treo, không nằm
  trong phạm vi đợt này).
- **Không sửa `trading/`**. Đây là script nghiên cứu độc lập, không đụng production code.
- **Không sửa `scripts/leakage_audit.py`** — chỉ **import và dùng lại** các hàm lõi của nó
  (`compute_leakage_pair`, `run_block_permutation_test` từ `scripts/audit_information.py`). Xem
  mục 2.2 — đây là điểm dễ nhầm nhất của brief này.
- **Không mở rộng ra ngoài 3 mã HPG/IJC/AAA.**
- **Không tính bất kỳ đặc trưng nào dùng dữ liệu của ngày `t` trở về sau để suy ra giá trị "biết
  trước" cho ngày `t`** — mọi đặc trưng tại ngày `t` chỉ được dùng dữ liệu có tới hết phiên `t`
  (không dùng giá/khối lượng của `t+1` trở đi).
- Dữ liệu: `bars_daily`, IS = 2016-01-01 → 2025-12-31 (khớp quy ước đợt 61/64), **2026 niêm
  phong** — không đọc.
- Không commit, không push.

---

## 2. Task 1 — Script sàng lọc, dùng lại lõi đã kiểm chứng

### 2.1. File mới

`scripts/screen_vn_signal_candidates.py` (tên tự chọn được, miễn rõ nghĩa) + test tương ứng.

### 2.2. Đây LÀ "sàng lọc tín hiệu", KHÔNG PHẢI "dò rò rỉ" — đừng lẫn hai khái niệm

`scripts/leakage_audit.py` được xây để trả lời "đặc trưng này có bị gắn nhãn sai (nhìn thấy tương
lai) không?" — nó gắn cờ `NGHI_VAN` khi `rho_sau > rho_truoc` **và** `|rho_sau|` vượt ngưỡng. Đó là
so sánh **bất đối xứng trước/sau**.

Câu hỏi ở đây khác: "**đặc trưng này có tương quan thật với lợi suất tương lai không, hay chỉ là
nhiễu?**" — không quan tâm nó có tương quan với quá khứ nhiều hơn hay ít hơn. Vì vậy:

- **Dùng lại** `compute_leakage_pair()` để tính `rho_sau` (và `rho_truoc` để tham khảo, không dùng
  để gắn cờ).
- **Dùng lại** `run_block_permutation_test()` để lấy ngưỡng null P95 của `max(|rho|)`.
- **KHÔNG dùng** `classify_leakage()` — hàm đó trả lời câu hỏi khác. Tự viết một hàm gắn cờ mới,
  đơn giản: `CO_TIN_HIEU` khi `|rho_sau| > threshold`, ngược lại `KHONG_TIN_HIEU`.

Nếu bạn thấy cách viết lại này trùng lặp với `classify_leakage`, đó là **có chủ ý** — hai câu hỏi
khác nhau xứng đáng hai hàm khác nhau, dù dùng chung nguyên liệu đo (`rho_sau`, `threshold`). Đừng
sửa `classify_leakage` để nó làm cả hai việc.

### 2.3. `run_block_permutation_test` — tham số `block_size_hours` đặt tên sai cho ca này

Đọc kỹ trước khi dùng: tham số đó **không thực sự tính theo giờ đồng hồ** — nó chia `panel_rows`
thành các khối **theo SỐ HÀNG liên tiếp**. Tên `_hours` chỉ đúng vì dữ liệu crypto là hàng-giờ. Với
`bars_daily`, mỗi hàng là một **ngày giao dịch**, nên khi bạn truyền `block_size_hours=20`, nó tạo
khối **20 ngày giao dịch liên tiếp** — không phải 20 giờ.

Chọn kích thước khối (tính theo ngày giao dịch) đủ lớn để bảo toàn tự tương quan ngắn hạn của lợi
suất (momentum tuần/tháng), nhưng đừng chọn tuỳ tiện — **nêu rõ trong báo cáo bạn chọn bao nhiêu
ngày và vì sao** (ví dụ: ~20 ngày giao dịch ≈ 1 tháng, theo đúng quy ước 48 giờ ≈ 2 ngày mà crypto
đã dùng — bạn có thể chọn số khác nếu có lý do, miễn nói rõ).

### 2.4. Đặc trưng ứng viên — tính từ `bars_daily`, không cần nguồn dữ liệu mới

Tính cho mỗi mã, mỗi ngày giao dịch `t`, chỉ dùng dữ liệu tới hết phiên `t`:

| Đặc trưng | Công thức |
|---|---|
| `mom_5d` | `close[t]/close[t-5] - 1` |
| `mom_20d` | `close[t]/close[t-20] - 1` |
| `vol_ratio_20d` | `volume[t] / mean(volume[t-20..t-1])` |
| `rsi_14` | RSI chuẩn 14 ngày, tính tới hết `t` |
| `dist_from_sma20` | `close[t] / SMA20(close[t-19..t]) - 1` |
| `realized_vol_20d` | độ lệch chuẩn lợi suất ngày trong `[t-19..t]` |

**Đối chứng (kiểm tra phép đo không hỏng):** `intraday_ret = (close[t] - open[t]) / open[t]`. Kỳ
vọng: tương quan **mạnh dương** với `ret_past_1d = close[t]/close[t-1] - 1` (cả hai cùng mô tả biến
động giá trong ngày `t`, dù không trùng tuyệt đối — gap qua đêm là phần khác biệt). Nêu ngưỡng bạn
coi là "đạt" cho đối chứng này (ví dụ >0,5) và giải thích vì sao chọn mức đó — không có mốc lịch sử
để so như crypto's +0,75, vì đây là phép đo mới.

**Mục tiêu:** `fwd_ret_1d[t] = close[t+1]/close[t] - 1`.

### 2.5. Cách chạy — theo TỪNG MÃ riêng, không gộp cross-sectional

Chạy phép đo (bao gồm hoán vị khối) **riêng cho từng mã** (HPG, IJC, AAA), mỗi mã là một chuỗi thời
gian độc lập — **giống hệt cách crypto tool xử lý BTCUSDT** (một chuỗi, không trộn nhiều mã vào
một panel). Đừng gộp 3 mã thành một bảng dài rồi hoán vị chung — hoán vị khối khi đó sẽ trộn cấu
trúc tự tương quan của các mã khác nhau vào một ngưỡng, và ngưỡng đó không còn ý nghĩa cho từng mã.

Với mỗi mã: chạy `run_block_permutation_test` với `feature_names` = toàn bộ 6 đặc trưng bảng trên
→ ngưỡng P95 của `max(|rho_sau|)` đã tự động điều chỉnh cho nhiều phép so sánh (đúng quy ước FWER
project đã dùng ở đợt 42/71). Số lần hoán vị: bạn tự chọn, nêu rõ trong báo cáo (tối thiểu 500, như
đợt 71 dùng để cân bằng thời gian chạy).

---

## Task 2 — Test

1. **Ba test tổng hợp** tương tự `test_leakage_audit.py` (đặc trưng rò rỉ/ngẫu nhiên nhân tạo), áp
   dụng cho hàm gắn cờ mới `CO_TIN_HIEU`/`KHONG_TIN_HIEU`:
   - đặc trưng = `fwd_ret_1d + nhiễu nhỏ` → `CO_TIN_HIEU` (rho_sau rất cao).
   - đặc trưng ngẫu nhiên độc lập (seed cố định) → `KHONG_TIN_HIEU`, `|rho_sau|` nhỏ.
2. **Test cho từng công thức đặc trưng** (`mom_5d`, `rsi_14`, v.v.) trên chuỗi giá tổng hợp có kết
   quả tính tay được — xác nhận không có ô nào đọc dữ liệu từ `t+1` trở đi (dùng kỹ thuật tương tự
   test phá hoại của đợt 61: cố tình cho một đặc trưng đọc lố sang tương lai, xác nhận test bắt
   được).
3. `uv run pytest -m "not integration" -q` và `uv run ruff check trading tests scripts` — dán số
   test trước → sau, đọc từ màn hình.

---

## Task 3 — Chạy thật, báo cáo trung thực

Chạy script cho cả 3 mã. Với mỗi mã, mỗi đặc trưng: in `rho_truoc`, `rho_sau`, ngưỡng hoán vị, cờ
`CO_TIN_HIEU`/`KHONG_TIN_HIEU`. In riêng kết quả đối chứng.

**Không diễn giải quá kết quả:**

- Nếu **tất cả** đều `KHONG_TIN_HIEU`: đó là kết luận hợp lệ và nhất quán với đợt 42/64 — **ghi
  nhận, không cố tìm cách "cứu" một đặc trưng nào bằng cách đổi ngưỡng hay đổi chân trời sau khi đã
  thấy kết quả**. Nếu muốn thử chân trời khác (`fwd_ret_5d` chẳng hạn), phải nêu **trước khi chạy**,
  không phải chọn sau khi thấy `fwd_ret_1d` không ra gì (đó là data snooping).
- Nếu **có** đặc trưng nào `CO_TIN_HIEU`: đây **không phải** "đã tìm ra alpha, có thể xây ML ngay".
  Một phép đo dương ở bước sàng lọc thô cần xác nhận thêm (walk-forward, ngoài mẫu 2026, nhiều mã
  hơn) trước khi tin. Báo cáo, không tự ý làm thêm bước xác nhận đó trong đợt này — đó là quyết
  định của tôi sau khi thấy kết quả.

---

## 3. Không làm

- Không mở rộng ra ngoài 3 mã HPG/IJC/AAA.
- Không sửa `scripts/leakage_audit.py`, không sửa `trading/`.
- Không thêm dependency, không đụng Docker/`pyproject.toml`.
- Không tự ý đổi ngưỡng/chân trời sau khi đã thấy kết quả để "tìm ra tín hiệu".
- Không tự triển khai bước xác nhận tiếp theo nếu tìm thấy `CO_TIN_HIEU` — chỉ báo cáo.
- Không commit, không push.

## 4. Báo cáo cho Claude

1. `git diff` / danh sách file mới.
2. Giải thích rõ: vì sao KHÔNG dùng `classify_leakage`, hàm gắn cờ mới định nghĩa thế nào.
3. Kích thước khối hoán vị đã chọn (theo ngày giao dịch) và lý do; số lần hoán vị đã dùng.
4. Bảng đầy đủ: 3 mã × 6 đặc trưng, `rho_truoc`/`rho_sau`/ngưỡng/cờ, kèm kết quả đối chứng mỗi mã.
5. Kết quả Task 2 — cả ba loại test, số test trước → sau đọc từ màn hình, `ruff` sạch.
6. Kết luận thuần mô tả (không khuyến nghị hướng ML) — để tôi quyết bước tiếp theo.
