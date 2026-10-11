# Brief đợt 183b — Ngưỡng imbalance tương đối cho E3 crypto (sửa TRƯỚC khi đo)

Ngày: 11/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Nền: commit `da88c6e` (đợt 183 đã audit). Đo vẫn từ **01/11/2026**. Đợt này **không** tính sự kiện hay mục tiêu nào trên dữ liệu thật.

## 0. Vì sao

Khi audit 183, Claude đếm đặc trưng trên dữ liệu thật (ghi chú ở brief 183 §1.2):
- bước 2 bps cho mỗi nến 5 phút chỉ khoảng **5–6 mức giá**;
- mỗi mức có hàng triệu USDT, nên `min_vol = 50.000 USDT` gần như luôn đạt;
- kết quả: **92–96% nến có imbalance cả hai phía**, và E3 suy biến.

Footprint trong video (ES/NQ) có khoảng 10–20 mức mỗi nến, và imbalance là chuyện hiếm. Đợt này sửa **hai thứ, chỉ cho E3 crypto**:
1. bước giá nhỏ hơn;
2. ngưỡng imbalance tương đối, đặt theo các ngày trước, giống cách E2 đặt ngưỡng delta.

Lý do sửa chỉ là độ phổ biến của đặc trưng. **Chưa ai thấy kết quả lãi/lỗ nào.**

**Đây là lần sửa duy nhất.** Nếu sau sửa E3 vẫn suy biến theo quy tắc §1.4, E3 bị loại khỏi crypto, **không** chỉnh ngưỡng lần nữa.

E1, E2, khung funding, cửa sổ, hurdle, cổng ngày, Bonferroni **giữ nguyên** brief 183.

## 1. Thiết kế (đăng ký trước, không đổi sau khi thấy số)

### 1.1 Bước footprint
- `step = max(0,1; round(open × 0,0001; 1))`, tức khoảng 1 bp theo giá mở cửa của chính nến.
- Ví dụ: open 60.000 ⇒ 6,0; open 7.123,4 ⇒ 0,7; open 100 ⇒ 0,1.
- `k = floor(price / step)`, `close_k = floor(close / step)` như cũ.

### 1.2 Lưu footprint đầy đủ (thay cho cột ask/bid k)
- **Đầu ra mới:** `data/crypto_footprint_v2/BTCUSDT/<YYYY-MM>.csv.gz`. **Không** ghi đè thư mục v1.
- **Cột:** `ts, open, high, low, close, buy, sell, delta, n_trades, step, close_k, fp`.
- `fp` là chuỗi `k:buy_usdt:sell_usdt` nối bằng `|`, sắp theo k tăng dần, giá trị USDT làm tròn số nguyên.
  - Ví dụ: `10001:250000:0|10002:1200000:300000`.
  - Nến trống: `fp` rỗng.
- Bỏ các cột `ask_k_min/max`, `bid_k_min/max`. Imbalance được tính lúc đo (§1.3).
- Chạy lại an toàn như 183: đủ số dòng **và** header có cột `fp` thì bỏ qua.

### 1.3 Ngưỡng imbalance tương đối (tính lúc đo, không nhìn trước)

**Gom mẫu:** với mỗi ngày UTC D, pool là mọi giá trị `buy_usdt[k] > 0` và `sell_usdt[k] > 0` ở mọi mức của mọi nến có giao dịch trong **5 ngày UTC có dữ liệu ngay trước D**. Ngày D không thuộc pool.

**Ngưỡng:**
- `min_vol(D)` = p90 của pool;
- `denom_floor(D)` = p50 của pool;
- dùng `calculate_percentile` của `scripts/screen_vn30f_orderflow.py`, cùng hàm E2 đang dùng.

**Áp ngưỡng:**
- Imbalance của mỗi nến ngày D tính bằng `imbalance_levels(fp, ratio=3, min_vol=min_vol(D), denom_floor=denom_floor(D))` của 182 (import, không sửa).
- Từ đó ra `ask_k_min/max`, `bid_k_min/max` đưa vào `BarSummary`.
- 5 ngày đầu (2023-01-01 → 05) không có ngưỡng ⇒ các trường imbalance = `None`, nên không có E3.

### 1.4 Quy tắc suy biến (đếm đặc trưng, làm NGAY, trước 01/11)
- Trên cửa sổ CHÍNH (2023–2024), đếm tỷ lệ nến có giao dịch theo bốn nhóm: chỉ ask, chỉ bid, cả hai, không có.
- Nếu tỷ lệ **"cả hai" > 50%**:
  - E3 bị **loại** khỏi crypto, còn 4 cặp;
  - Bonferroni **vẫn** 0,05/6, không được nới;
  - công cụ đo in "E3 LOẠI (suy biến)" thay cho dòng E3.
- Quy tắc này phải nằm trong code, như một hằng `E3_DEGENERATE_BOTH_SHARE = 0.5`, và được kiểm khi đo.

## 2. Việc agent làm

**A. `scripts/build_crypto_footprint.py`:**
- đổi bước theo §1.1;
- lưu cột `fp` theo §1.2;
- đổi thư mục mặc định sang v2;
- bỏ gọi `imbalance_levels` ở bước dựng.

**B. `scripts/screen_crypto_orderflow.py`:**
- `load_crypto_footprint_bars` đọc định dạng v2. Gặp file không có cột `fp` ⇒ `ValueError` nói rõ "định dạng v1".
- Thêm `apply_relative_imbalance(bars_with_fp)` theo §1.3. Hàm này trả `BarSummary` có trường imbalance.
- Thêm `imbalance_prevalence(bars, start, end)`: trả số nến của bốn nhóm.
- Pipeline áp quy tắc §1.4 trước khi đánh giá E3.
- Thư mục mặc định đổi sang v2.

**C. Lệnh đếm phổ biến: `scripts/build_crypto_footprint.py --prevalence`.**
- Đọc thư mục v2, gọi `apply_relative_imbalance` và `imbalance_prevalence`, in bảng theo tháng và tổng cửa sổ CHÍNH.
- Lệnh này **chỉ** gọi hai hàm trên. **Không** gọi bộ phát hiện E1/E2/E3, không tính mục tiêu.
- Code phải thể hiện được điều đó: test kiểm bằng mock rằng `detect_e*_events` và `calculate_event_targets` không bị gọi.
- **Không** thêm bất kỳ đường nào qua cổng ngày của công cụ đo.

**Chạy thật:**
1. dựng lại 2023-01 → 2026-08 vào v2, ở chế độ nền (vài giờ);
2. sau đó chạy `--prevalence` một lần và dán bảng.

**Không sửa:** `screen_vn30f_orderflow.py`, `binance_orderflow.py`, `seal.py`, mọi file khác. Không xoá thư mục v1; Claude sẽ quyết sau. Ghi chú trong code: tiếng Việt không dấu.

**Cấm cờ phá hoại trong code chạy thật** (`enforce_*`, `invert_*`, `bypass_*`…). Phép phá làm bằng cách sửa bản sao file rồi khôi phục.

## 3. Test (dữ liệu dựng tay, trong `tmp_path`)

Cập nhật test 1, 2, 11, 12 cũ cho định dạng v2, **giữ nguyên ý của từng ca**. Ca 1 phần imbalance chuyển sang test 13. Thêm các ca sau:

13. **Ngưỡng tương đối không nhìn trước.** Dựng 6 ngày:
    - ngày 6 có một mức khổng lồ;
    - assert `min_vol` của ngày 6 chỉ tính từ ngày 1–5;
    - đổi giá trị của ngày 6 thì ngưỡng ngày 6 không đổi;
    - ngày 1–5 không có imbalance (`None`).
14. **Áp ngưỡng:** một nến tay với pool biết trước:
    - p90 = 100.000, p50 = 20.000;
    - mức có `buy` 90.000 không phải imbalance (dưới p90);
    - mức `buy` 120.000 với `sell[k−1]` 0 là imbalance (mẫu số chạm sàn 20.000, 120.000 ≥ 60.000);
    - mức `buy` 150.000 với `sell[k−1]` 60.000 không phải imbalance (150.000 < 180.000).
15. **Chuỗi `fp`:** ghi rồi đọc lại cho ra đúng dict; nến trống ⇒ `fp` rỗng; file v1 ⇒ `ValueError` có chữ "v1".
16. **Quy tắc suy biến:**
    - dữ liệu dựng có 51% nến "cả hai" ⇒ pipeline đánh dấu E3 LOẠI, không gọi đánh giá E3 (mock), Bonferroni ở CHÍNH vẫn 0,05/6;
    - 50% đúng bằng ⇒ E3 được giữ.
17. **`--prevalence` không chạm sự kiện:** chạy trên thư mục tạm; mock `detect_e1/e2/e3_events` và `calculate_event_targets` đều `assert_not_called`; output có bảng bốn nhóm.

**Bốn phép phá bắt buộc** (sao lưu ngoài repo, khôi phục bằng `cp`, so `sha256`; cấm `git checkout/restore/stash`):

| Phép phá | Test phải đỏ |
|---|---|
| (xi) pool ngưỡng gồm cả ngày D | 13 |
| (xii) bước 2 bps thay vì 1 bp | 2 |
| (xiii) "cả hai" dùng `>=` thay vì `>` 0,5 | 16 |
| (xiv) `--prevalence` gọi `detect_e3_events` | 17 |

## 4. Cổng kiểm cuối
- **GitNexus** (`node .gitnexus/run.cjs …` hoặc `gitnexus … -r AI_auto_trading_system`, không `npx`):
  - `impact` upstream cho `aggregate_aggtrades_to_5m_bars`, `process_month`, `load_crypto_footprint_bars`, `run_crypto_screening_pipeline` trước khi sửa;
  - `detect-changes --scope all` sau khi sửa.
- `uv run pytest -m "not integration" -q` trước và sau: dán hai con số. `uv run ruff check trading tests scripts` sạch.
- `uv run python scripts/screen_crypto_orderflow.py` hôm nay vẫn in thông báo cổng ngày và trả 2.
- Bảng dựng v2 theo tháng: số nến, số nến có giao dịch, dung lượng, **trung vị số mức `fp` mỗi nến**.
- Bảng `--prevalence` theo tháng, cộng dòng tổng CHÍNH, và phán quyết E3 giữ hay LOẠI.

## 5. Bất biến
- **Không:** commit, push, ghi DB, đặt lệnh, gọi API BingX, chạy `scripts/sched.sh` hay script drill.
- **Không đọc:** `.ssi_sdk_token.json`, `.env`, `data/orderbook/`.
- **Mạng:** chỉ GET tới `data.binance.vision`, nghỉ ≥ 1,05 giây giữa các lượt.

## 6. Báo cáo cho Claude
- pytest trước/sau, ruff, output cổng ngày.
- Bảng bốn phép phá, `impact`, `detect-changes`.
- Bảng dựng v2 và bảng `--prevalence`.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi chưa tính sự kiện hay mục tiêu nào trên dữ liệu thật; phép đo chạy từ 01/11/2026."*
