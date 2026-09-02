# Báo cáo Đợt 12 — BingX Giai đoạn 1: Nạp Dữ liệu Nến Lịch sử

Ngày thực hiện: **02/09/2026 (Tối)**.  
Kế hoạch thực thi: [`docs/superpowers/plans/2026-09-02-brief-bingx-giai-doan-1-du-lieu.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/plans/2026-09-02-brief-bingx-giai-doan-1-du-lieu.md).

---

## 1. Tổng quan & Thống kê Thu thập Dữ liệu (Khung 1D, 20 cặp)

- **Bảng dữ liệu đích:** `bars_crypto` (độc lập hoàn toàn với `bars_daily` và `bars` của thị trường VN).
- **Endpoint sử dụng:** `https://open-api.bingx.com/openApi/swap/v3/quote/klines` (Public API, không cần API key).
- **Tổng số nến đã nạp:** **27.124 nến 1d** across 20 cặp USDT-M perpetual thanh khoản cao nhất.
- **Tổng số request API:** 35 requests.
- **Tổng thời gian nạp:** **44,7 giây** (nghỉ an toàn $\ge 1,1\text{ s}$ giữa các request).
- **Tình trạng lỗi:** **0 lỗi 100410** (không lần nào bị chạm rate limit).

### Bảng Chi tiết 20 Cặp Crypto Thu thập Được

| # | Cặp giao dịch (Symbol) | Số nến 1D | Mốc đầu (Earliest) | Mốc cuối (Latest) | Độ dài lịch sử | Đánh giá $\ge 3$ năm | Số calls |
|---|---|---:|:---:|:---:|---:|:---:|---:|
| 1 | **BTC-USDT** | 1.938 | 2021-05-14 | 2026-09-02 | 5,3 năm | **ĐỦ** | 2 |
| 2 | **ETH-USDT** | 1.935 | 2021-05-14 | 2026-09-02 | 5,3 năm | **ĐỦ** | 2 |
| 3 | **ADA-USDT** | 1.920 | 2021-06-01 | 2026-09-02 | 5,3 năm | **ĐỦ** | 2 |
| 4 | **XRP-USDT** | 1.920 | 2021-06-01 | 2026-09-02 | 5,3 năm | **ĐỦ** | 2 |
| 5 | **SOL-USDT** | 1.764 | 2021-11-04 | 2026-09-02 | 4,8 năm | **ĐỦ** | 2 |
| 6 | **AAVE-USDT** | 1.759 | 2021-11-09 | 2026-09-02 | 4,8 năm | **ĐỦ** | 2 |
| 7 | **DOGE-USDT** | 1.759 | 2021-11-09 | 2026-09-02 | 4,8 năm | **ĐỦ** | 2 |
| 8 | **UNI-USDT** | 1.759 | 2021-11-09 | 2026-09-02 | 4,8 năm | **ĐỦ** | 2 |
| 9 | **TRX-USDT** | 1.752 | 2021-11-16 | 2026-09-02 | 4,8 năm | **ĐỦ** | 2 |
| 10 | **CRV-USDT** | 1.661 | 2022-02-15 | 2026-09-02 | 4,5 năm | **ĐỦ** | 2 |
| 11 | **LDO-USDT** | 1.192 | 2022-07-24 | 2026-09-02 | 4,1 năm | **ĐỦ** | 2 |
| 12 | **ORDI-USDT** | 1.214 | 2023-05-08 | 2026-09-02 | 3,3 năm | **ĐỦ** | 2 |
| 13 | **1000PEPE-USDT** | 1.075 | 2023-09-24 | 2026-09-02 | 2,9 năm | *Ngắn (< 3 năm)* | 2 |
| 14 | **ARB-USDT** | 1.075 | 2023-09-24 | 2026-09-02 | 2,9 năm | *Ngắn (< 3 năm)* | 2 |
| 15 | **KAS-USDT** | 1.059 | 2023-10-10 | 2026-09-02 | 2,9 năm | *Ngắn (< 3 năm)* | 2 |
| 16 | **TAO-USDT** | 947 | 2024-01-30 | 2026-09-02 | 2,6 năm | *Ngắn (< 3 năm)* | 1 |
| 17 | **STRK-USDT** | 926 | 2024-02-20 | 2026-09-02 | 2,5 năm | *Ngắn (< 3 năm)* | 1 |
| 18 | **HYPE-USDT** | 623 | 2024-12-19 | 2026-09-02 | 1,7 năm | *Ngắn (< 3 năm)* | 1 |
| 19 | **XAUT-USDT** | 518 | 2025-04-03 | 2026-09-02 | 1,4 năm | *Ngắn (< 3 năm)* | 1 |
| 20 | **ZEC-USDT** | 328 | 2025-10-10 | 2026-09-02 | 0,9 năm | *Ngắn (< 3 năm)* | 1 |
| | **Tổng cộng** | **27.124** | | | | **12 đủ / 8 ngắn** | **35** |

---

## 2. Nhận xét Về Dữ liệu cho Giai đoạn Tiếp theo

1. **Khả năng phân chia Trong mẫu / Ngoài mẫu (In-Sample / Out-of-Sample):**
   - **12/20 cặp** có độ sâu lịch sử từ 3,3 năm đến 5,3 năm (bắt đầu từ tháng 5/2021 đến giữa 2023). Các cặp này hoàn toàn đủ điều kiện để chia kỳ:
     - *Trong mẫu:* 2021-05 → 2023-12 (~2,6 năm).
     - *Ngoài mẫu:* 2024-01 → 2026-08 (~2,7 năm).
   - **8/20 cặp** niêm yết sau (2023–2025) có lịch sử dưới 3 năm. Khi thực hiện đo chiến lược (Giai đoạn 2), rổ đo cần phân biệt rõ rổ cặp cốt lõi ($\ge 3$ năm) và rổ cặp mới để tránh bias kỳ đo.

2. **So sánh với ước tính ban đầu trong Brief:**
   - Ước tính trong Brief: 20 mã khung 1d cần ~40 calls và ~1 phút.
   - Thực tế đo được: **35 calls và 44,7 giây** — hoàn toàn khớp với mô hình tốc độ và an toàn rate-limit.

---

## 3. Kiểm chứng An toàn Cơ sở Dữ liệu

### 3.1. Cô lập bảng cũ `bars_daily`
- **Số lượng dòng `bars_daily` trước khi bắt đầu:** `2.982.903`
- **Số lượng dòng `bars_daily` sau khi hoàn thành:** `2.982.903`
- $\rightarrow$ **Tuyệt đối không có sự xáo trộn hay ghi đè vào dữ liệu chứng khoán VN.**

### 3.2. Kiểm tra tính Idempotent (Chạy lại an toàn)
- Chạy lần 1: Nạp `27.124` nến vào bảng `bars_crypto`.
- Chạy lần 2 (lặp lại hoàn toàn cùng tham số): `SELECT count(*) FROM bars_crypto` vẫn cho kết quả đúng **`27.124` nến** (0 dòng trùng lặp nhờ cơ chế `ON CONFLICT (symbol, interval, ts) DO UPDATE`).

---

## 4. Kiểm chứng Phá hoại (Destructive Testing)

File test: [`tests/test_bingx_klines.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_bingx_klines.py) (4 passed).

### 4.1. Phá hoại Test 2 (`test_dung_khi_khong_tien_len`)
Vô hiệu hóa điều kiện ngắt vòng lặp khi `min_ms >= prev_min_ms` (mô phỏng lỗi lặp vô hạn khi API trả về nến cũ đứng yên):
```
================================== FAILURES ===================================
________________________ test_dung_khi_khong_tien_len _________________________
    # Phải dừng ở lần gọi thứ 2 khi phát hiện min_time không tiến lên
>   assert calls == 2
E   assert 11 == 2

tests\test_bingx_klines.py:107: AssertionError
============================== 1 failed in 0.27s ==============================
```

### 4.2. Phá hoại Test 3 (`test_parse_nen_dung_thu_tu_truong`)
Thay đổi chỉ số nạp `close` từ vị trí `[4]` sang `[6]` (`closeTime`):
```
================================== FAILURES ===================================
______________________ test_parse_nen_dung_thu_tu_truong ______________________
    # Kiểm tra giá
    assert pytest.approx(parsed["open"], rel=1e-6) == 100.5
    assert pytest.approx(parsed["high"], rel=1e-6) == 115.0
    assert pytest.approx(parsed["low"], rel=1e-6) == 95.2
>   assert pytest.approx(parsed["close"], rel=1e-6) == 108.7
E   assert 1577923199000.0 ± 1.6e+06 == 108.7
E     
E     comparison failed
E     Obtained: 108.7
E     Expected: 1577923199000.0 ± 1.6e+06

tests\test_bingx_klines.py:143: AssertionError
============================== 1 failed in 0.23s ==============================
```

---

## 5. Bảng Đối chiếu Tiêu chí Hoàn thành (Checklist Đợt 12)

| # | Tiêu chí | Trạng thái | Chi tiết kiểm chứng |
|---|---|:---:|---|
| 1 | 4 Unit tests | **ĐẠT** | `uv run pytest tests/test_bingx_klines.py -v` $\rightarrow$ 4 passed in 0.26s |
| 2 | Kiểm chứng phá hoại | **ĐẠT** | Output đỏ nguyên văn test 2 (`assert 11 == 2`) và test 3 (`assert 1577923199000.0 == 108.7`) ghi tại Mục 4 |
| 3 | Nạp thật 1d cho 20 cặp | **ĐẠT** | 27.124 nến 1d lưu vào `bars_crypto`, chi tiết từng mã tại Mục 1 |
| 4 | Chạy lại an toàn (Idempotent) | **ĐẠT** | Chạy lần 2 số dòng `bars_crypto` giữ nguyên 27.124 (UPSERT sạch) |
| 5 | Không chạm bảng cũ | **ĐẠT** | `SELECT count(*) FROM bars_daily` = 2.982.903 trước và sau không đổi |
| 6 | Không hồi quy test suite | **ĐẠT** | `uv run pytest -m "not integration" -q` $\rightarrow$ 370 passed, 97 deselected |
| 7 | Linter sạch | **ĐẠT** | `uv run ruff check trading tests scripts` $\rightarrow$ All checks passed! |
| 8 | Ràng buộc an toàn | **ĐẠT** | Không sửa `trading/`, không chạm `config/config.yaml`, không gọi API key, không commit/push |

---

## 6. ĐỢT 13: NẠP DỮ LIỆU KHUNG 1H (HOÀN TẤT GIAI ĐOẠN 1)

Ngày thực hiện: **02/09/2026 (Đêm)**.  
Kế hoạch thực thi: [`docs/superpowers/plans/2026-09-02-brief-bingx-nap-khung-1h.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/plans/2026-09-02-brief-bingx-nap-khung-1h.md).

### 6.1. Quy trình Thực hiện
1. **Chụp số DB trước khi chạy:**
   - `bars_crypto (1d)`: `27.124`
   - `bars_crypto (1h)`: `0`
   - `bars_daily`: `2.982.903`
2. **Chạy thử 1 mã (`BTC-USDT`):**
   ```bash
   uv run python scripts/bingx_klines.py --symbols BTC-USDT --interval 1h
   ```
   - Thu thập được **20.598 nến 1h** (từ `2024-04-27 10:00` đến `2026-09-02 15:00`, độ sâu ~2,4 năm) trong 21 calls và 37,2 giây.
   - Chạy lại lần 2 cho `BTC-USDT`: Tổng số nến `1h` trong DB vẫn giữ nguyên **20.598 nến** (idempotent chuẩn xác).
3. **Chạy nạp toàn bộ 20 cặp:**
   ```bash
   uv run python scripts/bingx_klines.py --interval 1h --limit-symbols 20
   ```
   - Tổng số nến 1h đã nạp: **385.363 nến**.
   - Tổng số calls API: **393 calls**.
   - Tổng thời gian thực tế: **693,5 giây (~11,6 phút)** — nhanh hơn mức ước tính ban đầu (~17 phút) do độ sâu nến 1h của sàn BingX giới hạn tối đa ở mức ~20.598 nến (~2,4 năm) thay vì 5 năm như khung 1d.

### 6.2. Bảng Thống kê Dữ liệu Khung 1H của 20 Cặp

| # | Cặp giao dịch (Symbol) | Số nến 1H | Mốc đầu (Earliest) | Mốc cuối (Latest) | Độ dài (ngày) | Số calls |
|---|---|---:|:---:|:---:|---:|---:|
| 1 | **BTC-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 2 | **ETH-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 3 | **ADA-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 4 | **XRP-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 5 | **SOL-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 6 | **AAVE-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 7 | **DOGE-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 8 | **UNI-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 9 | **TRX-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 10 | **CRV-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 11 | **LDO-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 12 | **ORDI-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 13 | **1000PEPE-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 14 | **ARB-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 15 | **KAS-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 16 | **TAO-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 17 | **STRK-USDT** | 20.598 | 2024-04-27 10:00 | 2026-09-02 15:00 | 858,2 ngày | 21 |
| 18 | **HYPE-USDT** | 14.933 | 2024-12-19 11:00 | 2026-09-02 15:00 | 622,2 ngày | 15 |
| 19 | **XAUT-USDT** | 12.410 | 2025-04-03 14:00 | 2026-09-02 15:00 | 517,0 ngày | 13 |
| 20 | **ZEC-USDT** | 7.854 | 2025-10-10 10:00 | 2026-09-02 15:00 | 327,2 ngày | 8 |
| | **Tổng cộng** | **385.363** | | | | **393** |

### 6.3. Kiểm chứng An toàn & Tiêu chí Hoàn thành Đợt 13

| # | Tiêu chí | Trạng thái | Chi tiết kiểm chứng |
|---|---|:---:|---|
| 1 | Chạy thử 1 mã trước | **ĐẠT** | `BTC-USDT` chạy trong 37,2s, nạp 20.598 nến, độ sâu từ `2024-04-27` |
| 2 | Nạp `1h` cho 20 mã | **ĐẠT** | 385.363 nến 1h lưu vào `bars_crypto`, 393 calls, 11,6 phút |
| 3 | Khung `1d` không đổi | **ĐẠT** | `SELECT count(*) FROM bars_crypto WHERE interval = '1d'` trước và sau đều là **`27.124`** |
| 4 | `bars_daily` không đổi | **ĐẠT** | `SELECT count(*) FROM bars_daily` trước và sau đều là **`2.982.903`** |
| 5 | Chạy lại 1 mã không trùng | **ĐẠT** | Rerun `ETH-USDT` trên khung 1h, tổng số nến 1h vẫn là **`385.363`** |
| 6 | Không hồi quy test | **ĐẠT** | `uv run pytest -m "not integration" -q` $\rightarrow$ **370 passed, 97 deselected** |
| 7 | Linter sạch | **ĐẠT** | `uv run ruff check trading tests scripts` $\rightarrow$ **All checks passed!** |
| 8 | Ràng buộc an toàn | **ĐẠT** | Không sửa `trading/`, không bật `real_trading_enabled`, không commit/push |

