# Brief đợt 183 — Order flow trên BTCUSDT perp theo footprint (ĐĂNG KÝ TRƯỚC; dựng dữ liệu ngay, đo từ 01/11/2026)

Ngày: 11/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
**Điều kiện bắt đầu:** đợt 182 **và 182b** đã được Claude audit và commit. 182b thêm `block_end_fn` cho `calculate_event_targets`: đợt này truyền hàm "hết khung 8 giờ funding". Đợt này **import** các hàm phát hiện sự kiện của `scripts/screen_vn30f_orderflow.py`, xem §2 của brief 182.

## 0. Yêu cầu và cách hiểu

**Chủ dự án (11/10):** "Tôi muốn áp dụng [order flow theo video Fractal Flow] cho giao dịch phái sinh, forex và crypto; chứng khoán tôi sẽ tìm nguồn dữ liệu."

| Thị trường | Xử lý |
|---|---|
| Phái sinh VN30F | Đợt 182, đo từ 01/12. |
| **Crypto** | **Đợt này.** Binance Vision có toàn bộ lịch sử lệnh khớp (`aggTrades`) kèm bên chủ động (`is_buyer_maker`). Repo đã tải nguồn này ở đợt 40: `scripts/binance_orderflow.py`, khoảng 6 phút cho một tháng BTCUSDT. |
| Forex | **Không làm trong đợt này.** Forex giao ngay không có sàn tập trung, nên không có khối lượng chủ động thật; chính video cũng nói điều này. Nguồn thật duy nhất là hợp đồng tương lai FX của CME, phải mua dữ liệu, và đó là quyết định của chủ dự án. Lệnh khớp của perp forex trên BingX chỉ phản ánh người dùng BingX, không phải thị trường FX. |
| Chứng khoán | Chủ dự án tự tìm nguồn. |

**Thiết kế:** giữ **nguyên văn ba sự kiện của brief 182 v2**:
- E1: phân kỳ CVD;
- E2: phân kỳ delta trong nến, d = dấu delta;
- E3: bộ đôi hấp thụ → khởi xướng.

Đợt này chỉ đổi những thứ bắt buộc phải đổi khi sang BTC: bước giá của footprint, ngưỡng khối lượng, phiên/khung, chi phí, và cửa sổ.

**Ngân sách mục F:** tháng 10 đã dùng 9 giả thuyết, trần là 3.
- **Phần đo** của đợt này tính là **giả thuyết thứ 1 của tháng 11**. Công cụ có cổng ngày, **từ chối đo trước 2026-11-01**.
- **Phần dựng dữ liệu** (tải và gộp nến) làm ngay. Nó không tính mục tiêu nào nên không phải là phép thử.

**Đã biết:** đợt 105 dùng `taker_buy` của nến 1 giờ làm bộ lọc cho Donchian/Bollinger, và kết quả âm. Đợt này khác ở hai điểm: dùng footprint theo mức giá, và nến 5 phút.

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu và niêm phong
- **Nguồn:** `https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-YYYY-MM.zip`, kèm `.CHECKSUM`. Đối chiếu SHA256, đọc zip theo luồng, xoá zip sau khi gộp. Tái dùng `download_file_to_path`, `fetch_checksum_text`, `calculate_file_sha256` của `scripts/binance_orderflow.py` (**import, không sửa**).
- **Phạm vi:** tháng 2023-01 → 2026-08.
- **Niêm phong:** dùng `CRYPTO_SEALED_MAX_TS` của `scripts/seal.py`.
  - Tháng ≥ 2026-09 bị từ chối **trước khi tải**.
  - Một dòng có `transact_time` > mốc niêm phong ⇒ ném lỗi, không lặng lẽ bỏ qua.
- **Bên chủ động:** `is_buyer_maker = false` ⇒ **mua** chủ động; `true` ⇒ bán chủ động. Đây là quy ước đã ghi ở `binance_orderflow.py`.
- **Đầu ra dựng dữ liệu:** `data/crypto_footprint/BTCUSDT/<YYYY-MM>.csv.gz`, mỗi dòng là một nến 5 phút **tóm tắt**. Thư mục `data/` đã nằm trong `.gitignore`. **Không ghi DB.**

### 1.2 Nến footprint 5 phút
- **Nến** `[ts, ts+5 phút)` theo `transact_time` (ms, UTC). Mốc `:05:00.000` thuộc nến mới.
- **Trường cơ bản:** OHLC; `buy`/`sell` là Σ khối lượng BTC; `delta = buy − sell`; `n_trades`.
- **Bước footprint của nến:** `step = max(0,1; round(open × 0,0002; 1))`, tức khoảng 2 bps theo **giá mở cửa của chính nến**. Dùng `open` để không nhìn trước. Ví dụ: open 60.000 ⇒ 12,0; open 7.123,4 ⇒ 1,4.
- **Mức giá:** `k = floor(price / step)`; `close_k = floor(close / step)`.
- **Imbalance** tính theo **giá trị USDT** (giá × khối lượng) tại mỗi mức, dùng `imbalance_levels` của 182 với `ratio = 3`, `min_vol = 50.000`, `denom_floor = 10.000`:
  - ask tại k: `buy_usdt[k] ≥ 3 × max(sell_usdt[k−1], 10.000)` và `buy_usdt[k] ≥ 50.000`;
  - bid đối xứng.
  - Hai hằng 10.000 và 50.000 do Claude chốt trước khi ai thấy dữ liệu. Chúng đóng vai "1 hợp đồng" và "5 hợp đồng" của VN30F.
- **File tóm tắt** lưu: `ts`, OHLC, `buy`, `sell`, `delta`, `n_trades`, `step`, `close_k`, `ask_k_min`, `ask_k_max`, `bid_k_min`, `bid_k_max` (trống nếu không có imbalance). **Không** lưu footprint đầy đủ.
- **Phiên và khung:**
  - **phiên** = ngày UTC (CVD reset lúc 00:00, khối bootstrap, cửa sổ E1, ngưỡng E2 tính trên 5 ngày trước);
  - **khung** = ba khúc 8 giờ giữa các mốc funding: 00–08, 08–16, 16–24 UTC.
  - Mục tiêu không vắt qua mốc funding, nên **không cần mô hình funding**.

> **Ghi chú audit 11/10 (Claude), trước mọi phép đo. Chỉ đếm đặc trưng, chưa tính sự kiện hay mục tiêu nào.**
>
> Kiểm dữ liệu thật ba tháng 2023-01, 2024-06 và 2025-06:
> - mỗi nến chỉ trải khoảng 5–6 mức giá (trung vị);
> - 92–96% nến có imbalance **cả ask lẫn bid**;
> - chỉ khoảng 0–3 nến mỗi tháng không có imbalance nào.
>
> Ngưỡng `min_vol = 50.000 USDT` quá thấp so với khối lượng mỗi mức của BTC, nên "imbalance" không còn là tín hiệu hiếm như trong video.
> - **E3 suy biến:** chỉ còn ~4% nến thỏa "không có imbalance phía ngược".
> - E1 và E2 không dùng imbalance, nên không bị ảnh hưởng.
>
> Quyết định: E3 cho crypto sẽ được sửa ngưỡng bằng **brief 183b** trước 01/11, ghi vào spec H trước khi đo. Lý do sửa chỉ là độ phổ biến của đặc trưng, không phải kết quả. Nếu 183b không xong trước 01/11, E3 vẫn đo theo ngưỡng cũ, và phải báo kèm ghi chú này.

### 1.3 Sự kiện, mục tiêu, chồng lấn
- **Sự kiện:** E1/E2/E3 đúng định nghĩa §1.3 brief 182 v2, gọi chính hàm của 182 trên nến tóm tắt.
- **Mục tiêu:** `y = d × (P(t_end + H) / close_t − 1)`, tính theo **tỷ lệ**, H ∈ {15, 30} phút.
  - `P(x)` = `close` của nến có giao dịch gần nhất kết thúc ≤ x.
  - Bỏ sự kiện nếu `t_end + H` > hết khung chứa nó (bằng thì giữ, như 182).
- **Không chồng lấn** như 182. Tổng cộng **6 cặp**.

### 1.4 Cửa sổ và cổng
- **CHÍNH:** 2023-01-01 → 2024-12-31. **LẶP LẠI:** 2025-01-01 → 2026-08-31. Ngưỡng E2 được dùng các ngày ngay trước, kể cả khi những ngày đó thuộc cửa sổ trước.
- **Kiểm đối chứng trước** (cửa sổ CHÍNH): Spearman ρ(delta, close − open cùng nến) > 0,3. Không đạt ⇒ in "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN" và dừng.
- **ĐẠT ở CHÍNH**, theo từng cặp:
  1. ≥ 100 sự kiện, mỗi hướng ≥ 30;
  2. bootstrap theo khối **ngày UTC**, 2.000 lần, seed 42, p một phía < **0,05/6**;
  3. trung bình y ≥ **1,5 × (0,0010 + 0,0004) = 0,0021**. Trong đó 0,0010 là phí taker BingX 0,05% × 2 chiều, 0,0004 là trượt giá 2 bps × 2 chiều.
- **ĐẠT cuối cùng:** cặp đạt ở CHÍNH, **và** ở LẶP LẠI có trung bình y ≥ 0,0021 với p < 0,05/k, trong đó k là số cặp đạt ở CHÍNH.
- **In ra:** số của cả 6 cặp ở **cả hai** cửa sổ, nhưng phán quyết chỉ theo quy tắc trên.
- **Không đảo chiều sau khi thấy số**, như 182.
- **Không có đường tới lệnh thật.** Kết quả tốt nhất là một tờ trình để chủ dự án quyết có chạy giấy trên BingX hay không.
- **Lưu ý:** tín hiệu đo trên Binance nhưng sàn giao dịch dự kiến là BingX. Ở chân trời 15–30 phút, độ lệch giá giữa hai sàn nhỏ hơn nhiều so với ngưỡng 0,21%. Nếu có cặp ĐẠT, đây là điều phải kiểm tiếp.

### 1.5 Dự đoán của Claude (ghi trước)
Không cặp nào ĐẠT. BTC di chuyển trung bình theo một hướng sau 15–30 phút cỡ vài bps, còn ngưỡng là 21 bps. E3 với ngưỡng 50.000 USDT có thể sinh rất nhiều sự kiện; điều đó không đổi dự đoán.

## 2. Việc agent làm BÂY GIỜ

**A. `scripts/build_crypto_footprint.py` (mới):** tải và gộp như §1.1–§1.2. Hành vi:
- chạy lại an toàn: tháng đã có file với đủ số dòng thì bỏ qua;
- `--from YYYY-MM --to YYYY-MM`;
- không tính sự kiện hay mục tiêu.

Hàm imbalance phải là `imbalance_levels` import từ `scripts/screen_vn30f_orderflow.py`, không viết lại.

**Chạy thật:** chạy A cho 2023-01 → 2026-08 ở chế độ nền. Dự kiến vài giờ: 44 tháng, mỗi tháng khoảng 6–10 phút.

Báo cáo theo từng tháng:
- số nến và số nến có giao dịch, so với kỳ vọng 288 × số ngày;
- tháng thiếu;
- dung lượng file.

Chỉ đếm, **không** tính hay in bất kỳ thống kê sự kiện/mục tiêu nào.

**B. `scripts/screen_crypto_orderflow.py` (mới):** đọc file tóm tắt, gán `session_id`/`block_id`, gọi bộ phát hiện của 182, rồi tính mục tiêu, bootstrap và cổng §1.4. `main()` có **cổng ngày**:
- today (giờ VN, tham số tiêm được) < 2026-11-01 ⇒ in thông báo và `return 2` **trước khi mở file nào**;
- agent **không** tạm tắt cổng để thử.

**C. Tests:** `tests/test_build_crypto_footprint.py`, `tests/test_screen_crypto_orderflow.py`.

**Không sửa** bất kỳ file nào khác, kể cả `binance_orderflow.py`, `seal.py`, `screen_vn30f_orderflow.py`. Nếu cần sửa 182 thì dừng và báo Claude. Ghi chú trong code: tiếng Việt không dấu.

## 3. Test (TDD, chỉ dữ liệu dựng tay)

1. **Gộp aggTrades:** các dòng CSV tay. Assert:
   - `is_buyer_maker = false` vào `buy`, `true` vào `sell`;
   - OHLC đúng;
   - dòng lúc `:05:00.000` thuộc nến sau;
   - imbalance chéo theo USDT đúng ở từng mức, gồm ca dưới sàn 50.000 và ca mẫu số chạm sàn 10.000.
2. **Bước footprint:**
   - open 60.000 ⇒ 12,0; open 7.123,4 ⇒ 1,4; open 100 ⇒ 0,1;
   - có một nến mà `open` và `close` cho **bước khác nhau**, và kết quả phải theo `open`.
3. **Niêm phong:**
   - `--to 2026-09` ⇒ từ chối, hàm tải (mock) **không** được gọi;
   - file chứa một dòng `transact_time` = 2026-09-01 00:00:00.000 UTC ⇒ ném lỗi.
4. **Khung funding:**
   - sự kiện `t_end` 07:50, H = 15 ⇒ bỏ;
   - `t_end` 07:45, H = 15 ⇒ giữ, và `P` lấy close nến 07:55;
   - E3 với t−1 = nến 07:55 và t = nến 08:00 ⇒ không có sự kiện;
   - CVD của nến 00:00 = delta của chính nó.
5. **Tái dùng:** `screen_crypto_orderflow` dùng **đúng đối tượng hàm** của 182 (`is`) cho E1/E2/E3 và `imbalance_levels`.
6. **Mục tiêu:** y đúng dấu và tính theo tỷ lệ. Hurdle = 0,0021, sai số 1e-12.
7. **Cổng ngày:** 2026-10-31 ⇒ `return 2`, loader (mock) không được gọi; 2026-11-01 ⇒ đi tiếp.
8. **Phán quyết:**
   - cặp đạt CHÍNH nhưng LẶP LẠI có trung bình < hurdle ⇒ **không** ĐẠT;
   - hai cặp đạt CHÍNH ⇒ ngưỡng p ở LẶP LẠI là 0,05/2;
   - ρ đối chứng = 0,3 đúng bằng ⇒ dừng.
9. **Bootstrap theo ngày:** khối là ngày UTC. Dùng bẫy hai khối như ca 11 của 182.

**Sáu phép phá bắt buộc.** Sao lưu file ra ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`.

| Phép phá | Test phải đỏ |
|---|---|
| (i) đảo `is_buyer_maker` | ca 1 |
| (ii) bước footprint lấy theo `close` thay vì `open` | ca 2 |
| (iii) bỏ kiểm niêm phong theo dòng | ca 3 |
| (iv) khung = ngày UTC thay vì 8 giờ | ca 4 |
| (v) bỏ cổng ngày | ca 7 |
| (vi) bỏ điều kiện LẶP LẠI | ca 8 |

## 4. Cổng kiểm cuối
- **GitNexus** (chỉ `gitnexus ... -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs ...`, **không `npx`**):
  - trước khi viết: `impact` upstream cho `download_file_to_path`, `calculate_file_sha256`, `imbalance_levels`. `UNKNOWN` thì tự xác nhận bằng cách đọc file;
  - sau khi viết: `detect-changes --scope all`.
- `uv run pytest -m "not integration" -q` trước và sau: dán hai con số.
- Hai file test mới cùng `tests/test_scripts_convention.py` xanh. `uv run ruff check trading tests scripts` sạch.
- `--help` của hai script chạy được từ gốc repo.
- `uv run python scripts/screen_crypto_orderflow.py` hôm nay in thông báo cổng ngày và trả 2. Dán output.
- Bảng dựng dữ liệu theo tháng ở §2.A.

## 5. Bất biến
- **Không:** commit, push, ghi DB, đặt lệnh, gọi API BingX.
- **Không đọc:** `.ssi_sdk_token.json`, `.env`, `data/orderbook/`.
- **Không chạy:** `scripts/sched.sh`, mọi script drill.
- **Mạng:** chỉ GET tới `data.binance.vision`, nghỉ ≥ 1,05 giây giữa các lượt như `binance_orderflow.py`.

## 6. Báo cáo cho Claude
- Output pytest (trước/sau), ruff, `--help`, cổng ngày.
- Bảng sáu phép phá, `impact` và `detect-changes`.
- Bảng dựng dữ liệu theo tháng.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi chưa tính sự kiện hay mục tiêu nào trên dữ liệu thật; phép đo chạy từ 01/11/2026 theo §1."*
