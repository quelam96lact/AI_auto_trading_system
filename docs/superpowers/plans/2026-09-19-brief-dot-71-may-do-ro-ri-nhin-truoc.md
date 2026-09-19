# Brief đợt 71 — Máy dò rò rỉ nhìn trước, bước chuẩn bị bắt buộc trước khi đưa ML vào

Ngày giao: 19/09/2026 (tối).
Base: main hiện tại (`3f5a46b`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao đây là việc đầu tiên, không phải việc "xây mô hình"

Chủ dự án muốn chuẩn bị đưa machine learning vào hệ thống. Trước khi thêm **năng lực mô hình**,
phải thêm **cái chặn năng lực đó tìm ra tín hiệu giả**. Lý do không phải lý thuyết — dự án này đã
bị đúng một lần, và suýt tin:

Đợt 41 kiểm toán 9 đặc trưng phi giá × 3 biến mục tiêu, có hoán vị khối 48h và hiệu chỉnh đa phép
kiểm. Hai cặp "vượt ngưỡng" (`taker_ls_vol_ratio × fwd_ret_1h`, ρ = +0,1743). Sau đó **chính tôi
phải bác bỏ kết quả của mình**: đó là **rò rỉ nhìn trước**, do luật căn dòng trong brief tôi viết
sai với một biến dòng chảy được gán nhãn theo **thời điểm bắt đầu** cửa sổ. Giá trị tại `T` mô tả
`[T, T+5 phút)` — tức đã chứa 5 phút đầu của chính cửa sổ lợi suất tương lai.

Bắt được là nhờ một phép chẩn đoán làm **bằng tay**, sau khi sự việc đã rồi:

```
               cột                | giờ SAU T | giờ TRƯỚC T
----------------------------------+-----------+-------------
 sum_taker_long_short_vol_ratio   |  +0.1275  |   -0.0333   <- nghi van
 (doi chung) delta cua chinh ta   |  +0.7531  |   +0.0466   <- lanh manh
```

**Lập luận quyết định của đợt 41:** một biến dòng chảy nhìn về quá khứ **bắt buộc** phải tương
quan mạnh dương với lợi suất **cùng kỳ** — áp lực mua đẩy giá lên, đó là cơ học. Biến của ta cho
`+0,7531`. Biến của Binance cho `−0,0333` với giờ trước và `+0,1275` với giờ sau: nó **không mô tả
quá khứ**.

Phép chẩn đoán đó hiện **chỉ tồn tại trong một tài liệu**. Không có công cụ, không có test, không
ai chạy lại được. Với ML thì số đặc trưng sẽ tăng nhiều lần, và mô hình sẽ **tự động tìm và khai
thác đúng loại rò rỉ này** rồi cho ra một con số trong mẫu rất đẹp. Nên việc đầu tiên là biến phép
chẩn đoán ấy thành công cụ chạy được và kiểm được.

**Đợt này KHÔNG huấn luyện mô hình nào, KHÔNG thêm thư viện ML nào.**

---

## 1. Đọc trước

- `docs/superpowers/research/2026-09-12-dot-41-kiem-toan-thong-tin.md` — **đọc mục 8 trước tiên**
  (phần bác bỏ), đó là nguồn của toàn bộ brief này.
- `trading/feature_panel.py` — docstring đầu file mô tả luật căn dòng và 9 đặc trưng.
- `scripts/audit_information.py` — đã có sẵn Spearman và khung hoán vị khối.

## 2. Ràng buộc

- **Không thêm dependency** (repo hiện không có numpy/pandas/sklearn — giữ nguyên thuần Python).
- **Không sửa `trading/feature_panel.py`** trong đợt này.
- **Không huấn luyện mô hình.**
- **Dùng lại Spearman đã có, đừng tạo bản thứ ba.** Tôi đã grep trước khi giao: hiện **đã có hai**
  bản trong repo —
  - `scripts/audit_information.py::fast_spearman_rank_correlation` — **dùng bản này**, nó có test
    riêng (`tests/test_audit_information.py`) và xử lý đúng trường hợp trùng hạng (ties);
  - `scripts/binance_orderflow.py:530::spearman_corr` — bản cục bộ nằm lồng trong một hàm, **không
    dùng**.

  Việc gộp hai bản này là nợ kỹ thuật **có thật nhưng ngoài phạm vi đợt 71** — ghi nhận trong báo
  cáo, đừng tiện tay sửa. Khung hoán vị khối cũng lấy từ `audit_information.py`; nếu không import
  được sạch thì **báo cáo lại, đừng chép công thức sang file mới**.
- Không commit, không push.

---

## Task 1 — `scripts/leakage_audit.py`: đo hai phía của mốc thời gian

### 1.1. Phép đo, đóng băng

Với một chuỗi đặc trưng khoá theo `ts` và chuỗi giá nến 1h, tính **hai** hệ số Spearman:

- `rho_truoc` = tương quan giữa `feature[T]` và lợi suất của giờ **kết thúc** tại `T`
  (tức `close(T)/close(T-1h) - 1`).
- `rho_sau` = tương quan giữa `feature[T]` và lợi suất của giờ **bắt đầu** tại `T`
  (tức `close(T+1h)/close(T) - 1`).

### 1.2. Quy tắc gắn cờ, đóng băng

- **`NGHI_VAN`** khi `rho_sau > rho_truoc` **và** `|rho_sau|` vượt ngưỡng ý nghĩa từ hoán vị khối.
  Nghĩa là: đặc trưng "biết" về tương lai nhiều hơn về quá khứ.
- **`SACH`** khi không thoả điều kiện trên.
- Luôn in **cả hai** con số, **không** chỉ in cờ. Người đọc phải tự thấy được khoảng cách.

**Đây là phép sàng, không phải phép chứng minh.** `SACH` nghĩa là "không thấy dấu hiệu rò rỉ bằng
phép này", **không** nghĩa là "chắc chắn không rò rỉ". Ghi đúng câu đó vào docstring — đừng để ai
đọc kết quả rồi tưởng đã được bảo chứng.

### 1.3. Biến đối chứng bắt buộc

Mỗi lần chạy phải kèm **ít nhất một** biến đối chứng có ngữ nghĩa thời gian không mơ hồ
(`delta_norm` của chính ta — nến giờ `H` gộp giao dịch trong `[H, H+1h)`). Nếu đối chứng **không**
cho `rho_truoc` mạnh dương như đợt 41 đo được (+0,7531), thì **chính phép đo đang hỏng**, không
phải dữ liệu — dừng lại và báo cáo, đừng đọc kết quả của các biến khác.

Đây là chốt an toàn quan trọng nhất của công cụ: một cái thước phải tự chứng minh nó đo đúng trước
khi ta tin số nó đưa ra.

---

## Task 2 — Chạy trên cả 9 đặc trưng hiện có

Chạy trên đúng kỳ in-sample của đợt 41 (`2024-01-01` → `2025-12-31` UTC, **năm 2026 giữ niêm
phong, không đụng**). Xuất bảng:

```
dac trung | rho_truoc | rho_sau | nguong hoan vi | co | ghi chu
```

**Câu hỏi cần trả lời rõ:** `trading/feature_panel.py` có tham số `metric_lag_minutes` (mặc định
5). Nó có phải là bản vá cho chính lỗi đợt 41 không? Nếu đúng, thì `taker_ls_vol_ratio` bây giờ
phải được gắn cờ **`SACH`**, trong khi nếu chạy với `metric_lag_minutes=0` thì phải ra
**`NGHI_VAN`**. **Chạy cả hai cấu hình và đặt cạnh nhau** — đó vừa là câu trả lời, vừa là bằng
chứng công cụ hoạt động trên dữ liệu thật.

Nếu kết quả không như trên, **báo cáo đúng cái bạn đo được**, đừng uốn theo kỳ vọng của tôi.

---

## Task 3 — Test chứng minh máy dò phân biệt được

Trong `tests/test_leakage_audit.py`:

1. **Đặc trưng rò rỉ nhân tạo**: dựng feature bằng đúng lợi suất tương lai (cộng chút nhiễu) →
   phải bị gắn `NGHI_VAN`.
2. **Đặc trưng sạch nhân tạo**: dựng feature bằng lợi suất **quá khứ** → phải được gắn `SACH`.
3. **Đặc trưng vô nghĩa**: chuỗi ngẫu nhiên độc lập (seed cố định) → phải `SACH`, và cả hai `rho`
   đều gần 0.
4. **Chốt an toàn ở 1.3**: dựng trường hợp đối chứng hỏng, xác nhận công cụ **dừng và báo**, không
   lặng lẽ trả kết quả.

Chạy `uv run pytest -m "not integration" -q` (hiện 709) và `uv run ruff check trading tests scripts`.

---

## 3. Không làm

- Không huấn luyện mô hình, không thêm numpy/pandas/sklearn.
- Không sửa `trading/feature_panel.py`, không sửa `audit_information.py`.
- **Không đụng dữ liệu năm 2026** (kỳ niêm phong của đợt 41). Nếu thấy cám dỗ "kiểm thử nhanh trên
  2026", **dừng lại** — mở niêm phong là hành động một chiều, phá hỏng vĩnh viễn giá trị của kỳ
  ngoài mẫu.
- Không commit, không push.

## 4. Báo cáo cho Claude

1. `git diff` / toàn văn `scripts/leakage_audit.py` và `tests/test_leakage_audit.py`.
2. Bảng 9 đặc trưng ở Task 2, **hai cấu hình đặt cạnh nhau** (`metric_lag_minutes` 5 và 0).
3. Giá trị `rho_truoc` của biến đối chứng — và khẳng định nó mạnh dương (nếu không, dừng).
4. Kết quả 4 test ở Task 3, nguyên văn.
5. Xác nhận không đụng dữ liệu 2026 và không thêm dependency nào (`git diff pyproject.toml` rỗng).
