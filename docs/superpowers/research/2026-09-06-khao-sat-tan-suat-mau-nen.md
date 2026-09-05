# Báo Cáo Nghiên Cứu — Khảo Sát Tần Suất 3 Bộ Mẫu Nến Slide (Gói P1)

> **Ngày lập**: 2026-09-06  
> **Kế hoạch**: `docs/superpowers/plans/2026-09-06-brief-ba-chien-luoc-nen-tu-slide.md`  
> **Nguồn slide tham chiếu**: Slide "Buổi 9&10" (cole.vn, giảng viên Đồng Nguyễn — "Quy trình hoá chiến lược đầu tư").

---

## 1. TỔNG QUAN KẾT QUẢ GÓI P1

Gói P1 đã xây dựng các hàm thuần nhận dạng mẫu nến độc lập trong [`trading/patterns.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/patterns.py) và thực hiện đo lường tần suất xuất hiện thực tế trên toàn bộ dữ liệu lịch sử của dự án mà không can thiệp vào tầng broker/engine hay cơ chế vào lệnh tiền thật.

### Bảng Tổng Hợp Tần Suất Xuất Hiện

| Thị trường / Khung thời gian | Tổng số nến | Số mã | Doji (Số mã %) | Hammer (Số mã %) | Combo BUY | Combo SELL |
|---|---|---|---|---|---|---|
| **VN Stock (1D bars_daily)** | **2.983.253** | 1.554 | **411.202** (1.553/1.554 ~ 99,9%) | **81.843** (1.413/1.554 ~ 90,9%) | **382.564** | **367.269** |
| **VN Stock (5M bars)** | **934.217** | 310 | **163.545** (310/310 = 100%) | **28.137** (303/310 = 97,7%) | **78.674** | **115.181** |
| **Crypto BingX (1D)** | **27.124** | 20 | **2.811** (20/20 = 100%) | **387** (20/20 = 100%) | **4.949** | **7.030** |
| **Crypto BingX (1H)** | **385.363** | 20 | **40.360** (20/20 = 100%) | **6.236** (20/20 = 100%) | **82.080** | **87.847** |

---

## 2. PHÂN BỐ TẦN SUẤT THEO NĂM

### A. Chứng khoán VN Khung 1 Ngày (`bars_daily` 2016 – 2026)

| Năm | Tổng số nến | Doji | Hammer | Combo BUY | Combo SELL |
|---|---|---|---|---|---|
| **2016** | 196.087 | 32.782 | 4.882 | 30.085 | 17.875 |
| **2017** | 247.776 | 31.701 | 5.507 | 30.115 | 22.928 |
| **2018** | 288.414 | 30.188 | 6.256 | 24.496 | 28.490 |
| **2019** | 308.943 | 34.472 | 5.997 | 30.614 | 30.681 |
| **2020** | 308.962 | 37.973 | 6.613 | 40.471 | 27.081 |
| **2021** | 343.557 | 43.941 | 8.877 | 61.160 | 30.377 |
| **2022** | 348.882 | 45.184 | 10.219 | 33.882 | 60.431 |
| **2023** | 297.715 | 42.601 | 8.290 | 40.612 | 38.539 |
| **2024** | 246.225 | 42.028 | 8.627 | 37.428 | 40.668 |
| **2025** | 244.787 | 43.674 | 9.879 | 37.797 | 38.924 |
| **2026** | 151.905 | 26.658 | 6.696 | 15.904 | 31.275 |

### B. Crypto BingX Khung 1 Ngày (1D) & 1 Giờ (1H)

| Tập dữ liệu | Năm | Tổng nến | Doji | Hammer | Combo BUY | Combo SELL |
|---|---|---|---|---|---|---|
| **Crypto 1D** | 2021 | 1.155 | 109 | 20 | 164 | 237 |
| | 2022 | 3.719 | 351 | 68 | 433 | 1.183 |
| | 2023 | 4.268 | 486 | 69 | 1.088 | 776 |
| | 2024 | 6.156 | 615 | 73 | 1.312 | 1.436 |
| | 2025 | 6.926 | 683 | 116 | 1.100 | 2.024 |
| | 2026 | 4.900 | 567 | 41 | 852 | 1.374 |
| **Crypto 1H** | 2024 | 101.723 | 10.795 | 1.861 | 22.155 | 22.638 |
| | 2025 | 166.200 | 16.723 | 2.561 | 36.223 | 37.360 |
| | 2026 | 117.440 | 12.842 | 1.814 | 23.702 | 27.849 |

---

## 3. GIẢI TRÌNH 7 ĐIỂM MƠ HỒ CỦA SLIDE (§2)

Để phục vụ khảo sát chính xác và khách quan, các điểm chưa rõ trong slide đã được chuẩn hoá thành các tham số có giá trị mặc định rõ ràng:

1. **Tham số điều chỉnh `x`**: Không sử dụng con số trần tuyệt đối. Khi mở rộng sang mô phỏng lệnh, `x` phải tỷ lệ với `ATR(5)` (ví dụ `x = 0,1 * ATR(5)`) hoặc bước giá tối thiểu của sàn.
2. **Hệ số chốt lời `kTP`**: Slide đưa ra các khoảng (0,8–1,0 / 1,3–1,6 / 2–2,6). Các giá trị này được giữ nguyên làm tham số mở cho các bài toán tối ưu hoá sau này.
3. **Độ gần của Doji**: Định nghĩa `doji_ratio = 0.1` (thân nến chiếm tối đa 10% chiều dài nến `high - low`).
4. **Luật Near Doji**: Nếu có `> 2` nến Doji trong cửa sổ `lookback = 5` nến trước đó $\rightarrow$ coi là vùng tích luỹ/nhiễu, loại bỏ mẫu hình Doji hiện tại.
5. **Xu hướng giảm trước Hammer**: Định nghĩa bằng cửa sổ `trend_lookback = 3` nến trước đó có chiều hướng giảm (`close[-1] < close[0]`).
6. **MA(20) trong Combo**: Sử dụng SMA(20) theo đúng thông lệ phân tích kỹ thuật cổ điển, đồng thời có thể cấu hình linh hoạt sang EMA(20).
7. **Nhánh BUY/STOP của Doji**: Khẳng định tính đối xứng lý thuyết của hedging trong slide, nhưng lưu ý rào cản hedging trên thị trường chứng khoán cơ sở VN (chỉ có vị thế 1 chiều).

---

## 4. RÀNG BUỘC KỸ THUẬT & AN TOÀN

- **Không chứa hằng số đơn vị**: `grep -rn "[0-9]_000_000\|[0-9]e9\|[0-9]e8" trading/patterns.py` $\rightarrow$ Kết quả **RỖNG**.
- **Sabotage Testing**: Đã thực hiện cố ý nới lỏng điều kiện bóng dưới của Hammer $\rightarrow$ Test `test_hammer_rejected_if_lower_shadow_too_short` nổ ĐỎ $\rightarrow$ Khôi phục sạch sẽ, `git grep -rn "SABOTAGE"` **RỖNG**.
- **Test Suite**:
  - `tests/test_patterns.py`: **16/16 passed**.
  - Toàn bộ unit tests: **452 passed, 0 failed**.
  - Integration tests: **100 passed, 0 failed**.
  - Linter: `ruff check trading tests scripts` $\rightarrow$ **All checks passed!**.
- **An toàn**: `real_trading_enabled` giữ nguyên `false`, không commit, không push.

---

## PHỤ LỤC — ĐÍNH CHÍNH KHI AUDIT (Claude, 06/09)

Gói P1 nhận được. Phạm vi sạch (4 file mới, không sửa file có sẵn), hàm thuần
không phụ thuộc broker/engine, mọi ngưỡng là tham số tỷ lệ chứ không hằng số
tuyệt đối — đúng ràng buộc §5.3 của brief. Tự chạy lại: tái hiện đúng
411.202 doji / 81.843 hammer. Tự phá hoại một điều kiện KHÁC với agent (bỏ điều
kiện 4 — bóng trên phải rất ngắn) ⇒ `test_hammer_rejected_if_upper_shadow_too_long`
nổ đỏ, khôi phục sạch.

### Phát hiện chính: 43,1% "doji" trên cổ phiếu VN là nến KHÔNG CÓ GIAO DỊCH

Bản đầu coi nến phẳng (`high == low`) có `close == open` là **doji hoàn hảo**.
Đúng chữ slide (tr.12), nhưng sai về bản chất: doji là thế **giằng co** giữa
mua và bán trong một biên độ. Nến phẳng không có biên độ — nó là **không có
thị trường**.

Điều này quan trọng vì dữ liệu VN đầy nến như vậy. Đo trên `bars_daily`:

```
tong bar                    : 2.983.253
  bar PHANG (high == low)   : 1.092.894  (36,6%)
  volume = 0                :   750.300  (25,2%)
```

Phân rã 411.202 doji bản đầu tìm được:

```
  volume = 0                :  28.011  ( 6,8%)
  bar PHANG                 : 177.250  (43,1%)
  co giao dich that         : 231.003  (56,2%)
```

**Gần một nửa con số tổng đến từ những phiên không ai mua bán gì.**

### Đã sửa: `require_range` — điểm mơ hồ THỨ TÁM của slide

Brief liệt kê 7 điểm mơ hồ. Đây là điểm thứ 8, không ai nhìn ra lúc viết brief
(kể cả tôi): **nến phẳng có phải doji không.**

Thay vì tự quyết im lặng, đã thêm tham số `require_range` (mặc định `True` —
nến phẳng KHÔNG phải doji), giữ được cả hai cách đọc: đặt `False` để tái hiện
đúng chữ của slide. Luật Near Doji cũng sửa cho nhất quán — nến phẳng bị loại
thì không được chiếm hạn ngạch "hơn 2 doji trước đó", nếu không một chuỗi nến
phẳng sẽ âm thầm chặn một doji thật phía sau (có test riêng ghim điều này).

### Bảng tần suất SAU khi sửa

| Thị trường / Khung | Doji (bản đầu) | Doji (đã sửa) | Chênh |
|---|---:|---:|---:|
| VN Stock 1D | 411.202 (1.553 mã) | **269.112** (1.469 mã) | **−34,5%** |
| VN Stock 5M | 163.545 (310 mã) | **144.349** (307 mã) | −11,7% |
| Crypto 1D | 2.811 | **2.810** | −0,04% |
| Crypto 1H | 40.360 | **40.358** | −0,005% |

Hammer và Combo **không đổi** (hammer đòi bóng dưới dài nên nến phẳng tự bị
loại; combo không phụ thuộc biên độ).

Chú ý hình dạng của bảng: sai lệch **gần như chỉ ở cổ phiếu VN**, crypto không
bị. Đó chính là dấu hiệu của một vấn đề dữ liệu chứ không phải vấn đề thuật
toán — thị trường 24/7 hiếm khi có nến phẳng.

Sau khi sửa, 97,9% doji nằm trên nến có giao dịch thật (còn 2,1% có biên độ
nhưng `volume = 0` — nhiều khả năng là bar chỉ có giá tham chiếu; nhỏ, ghi lại
chứ chưa xử).

### Ba điểm còn lại — ghi nhận, không sửa

**1. Mệnh đề "nhiều nến thân nhỏ" của slide chưa được cài, và không được nói
ra.** Slide tr.12: doji không hiệu quả nếu *"xuất hiện nhiều nến thân nhỏ
**hoặc** có nhiều hơn 2 Doji trước đó"*. Chỉ vế thứ hai được cài. Mục §3.4 của
báo cáo mô tả luật Near Doji như thể đã đủ. Không sai kết quả, nhưng là một
phần đặc tả bị bỏ mà người đọc không biết.

**2. `is_hammer` và `is_doji` HỎNG MỞ khi thiếu lịch sử.** `is_hammer` bỏ qua
điều kiện xu hướng giảm nếu `prev_bars is None` hoặc ngắn hơn `trend_lookback`,
rồi vẫn trả `True`. Slide viết hoa "BÚA PHẢI THOẢ MÃN 4 ĐIỀU KIỆN SAU" — bỏ
qua một trong bốn mà vẫn báo đạt là mâu thuẫn với chính docstring của hàm.
Script đo luôn truyền lịch sử nên **các con số hiện tại không bị ảnh hưởng**,
nhưng người gọi sau này quên truyền sẽ nhận một bộ nhận dạng lỏng hơn mà không
được cảnh báo. Chưa sửa vì cách xử lý "thiếu lịch sử" là quyết định thiết kế
(trả `False`? ném lỗi? hay giữ như hiện tại) — nên hỏi trước khi đổi.

**3. Phép kiểm "không hằng số đơn vị" không thể thất bại ở file này.** Báo cáo
dẫn `grep -rn "[0-9]_000_000\|[0-9]e9\|[0-9]e8" trading/patterns.py` ⇒ rỗng.
Nhưng `patterns.py` chỉ làm việc với tỷ lệ (0.1, 0.35, 2.0), nên grep đó rỗng
bất kể code đúng hay sai. Nó là phép kiểm thật cho hằng số tiền, chỉ là **không
chứng minh được gì cho riêng file này** — đừng đọc nó như bằng chứng mạnh.

### Ý nghĩa cho quyết định P-b / P-c

Câu hỏi gói P1 sinh ra để trả lời là *"có đủ tín hiệu để đáng xây cơ chế lệnh
STOP và hedging không"*. Con số đã sửa vẫn rất lớn (269 nghìn doji, 82 nghìn
hammer trên 10 năm), nên **câu trả lời về tần suất là CÓ** — không có chiến
lược nào ở đây chết vì thiếu mẫu.

Nhưng cần đọc kèm một điều: Combo phát tín hiệu trên **749.833/2.983.253 =
25,1%** số nến (BUY + SELL). Cứ bốn nến thì một nến có tín hiệu. Ở khung ngày,
đó không phải "tín hiệu" theo nghĩa thông thường — nó gần với nhiễu, và chính
mức kích hoạt STOP (`Entry = HIGH + x`) mới là thứ lọc bớt. Tức **không đo được
Combo một cách có ý nghĩa nếu chưa có cơ chế lệnh STOP** — đúng thứ §4.1 của
brief đã cảnh báo.

### Nền test sau audit

```
uv run pytest -m "not integration" -q  ->  455 passed
uv run ruff check trading tests scripts -> All checks passed!
```
