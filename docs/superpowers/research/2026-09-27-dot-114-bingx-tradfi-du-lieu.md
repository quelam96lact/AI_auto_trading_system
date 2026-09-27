# Báo cáo Đợt 114 — BingX TradFi (Vàng, Chỉ số, Forex, Cổ phiếu): Nạp và kiểm kê dữ liệu, chưa đo chiến lược

**Ngày thực hiện:** 2026-09-27  
**Base commit:** `06958a5`  
**Người audit:** Claude. **Người thực thi:** Agent.  
**Phạm vi:** Nghiên cứu thuần túy, kiểm kê dữ liệu lịch sử đến 2026-08-31 23:59:59 UTC (niêm phong dữ liệu từ 2026-09-01).  
**Cam kết an toàn:** Không commit, không push, không đặt lệnh, không gọi endpoint có ký, không can thiệp hệ thống đang chạy.  

---

## 1. Bảng chính: Tổng hợp kiểm kê dữ liệu BingX TradFi

| Mã | Niêm yết | Nến 1d (ngày) | Nến 1h (ngày) | Hồ sơ giờ (7x24 UTC) | Khoảng trống bất thường | Nến bẩn (1d/1h) | Funding (CK, TB, TB|x|) | Phí 2 chiều / ATR 1h | Đủ điều kiện đo? |
|---|---|---|---|---|---|---|---|---|---|
| `NCCOGOLD2USD-USDT` | 2025-10-14 | 301 (322d) | 4779 (210d) | 24/7 (Liên tục) | 23 (0.5%) | 0/0 | 4h, +0.0094%, 0.0099% | 26.2% | **KHÔNG ĐỦ** |
| `NCCOXAG2USD-USDT` | 2026-02-11 | 199 (202d) | 4654 (202d) | 24/7 (Liên tục) | 16 (0.3%) | 0/0 | 4h, +0.0077%, 0.0086% | 13.4% | **KHÔNG ĐỦ** |
| `NCCO1OILWTI2USD-USDT` | 2026-03-09 | 165 (176d) | 2838 (126d) | 24/7 (Liên tục) | 16 (0.6%) | 0/0 | 4h, -0.0286%, 0.0322% | 12.3% | **KHÔNG ĐỦ** |
| `NCSISP5002USD-USDT` | 2025-11-26 | 252 (279d) | 2753 (126d) | 24/7 (Liên tục) | 5 (0.2%) | 0/0 | 8h, -0.0034%, 0.0065% | 53.6% | **KHÔNG ĐỦ** |
| `NCSINASDAQ1002USD-USDT` | 2025-11-26 | 252 (279d) | 2753 (126d) | 24/7 (Liên tục) | 5 (0.2%) | 0/0 | 8h, +0.0002%, 0.0080% | 32.8% | **KHÔNG ĐỦ** |
| `NCFXEUR2USD-USDT` | 2025-08-27 | 0 (0d) | 0 (0d) | Không có dữ liệu (pause) | N/A | 0/0 | Không có (pause) | N/A | **KHÔNG ĐỦ** |
| `NCFXUSD2JPY-USDT` | 2025-08-28 | 0 (0d) | 0 (0d) | Không có dữ liệu (pause) | N/A | 0/0 | Không có (pause) | N/A | **KHÔNG ĐỦ** |
| `NCSKAAPL2USD-USDT` | 2025-11-13 | 248 (292d) | 3592 (168d) | 24/7 (Liên tục) | 15 (0.4%) | 0/0 | 8h, +0.0030%, 0.0078% | 28.8% | **KHÔNG ĐỦ** |
| `NCSKNVDA2USD-USDT` | 2025-11-13 | 246 (292d) | 3592 (168d) | 24/7 (Liên tục) | 15 (0.4%) | 0/0 | 8h, -0.0038%, 0.0062% | 19.7% | **KHÔNG ĐỦ** |
| `BTC-USDT` | 2020-04-07 | 1936 (1936d) | 20558 (857d) | 24/7 (Liên tục) | 0 (0.0%) | 0/0 | 8h, +0.0056%, 0.0058% | 16.3% | **1D (≥3 năm) + 1H (≥1 năm & gap<1%)** |

---

## 2. Kết luận cốt lõi về khả năng đo lường chiến lược (§0, §4 Brief 114)

Báo cáo tuân thủ nghiêm ngặt quy định tại §4 Brief 114: **Không kết luận "đáng giao dịch"**, chỉ trả lời **ĐỦ** hay **KHÔNG ĐỦ** để đo theo 2 tiêu chí định lượng tuyệt đối:

1. **Đo chiến lược khung ngày (1D) — Yêu cầu: Ít nhất 3 năm nến 1d (≥ 1.095 ngày lịch):**
   - **KẾT QUẢ: KHÔNG CÓ MÃ TRADFI NÀO ĐẠT.**
   - Mã TradFi có lịch sử dài nhất là Vàng (`NCCOGOLD2USD-USDT`) niêm yết từ 14/10/2025, chỉ tích lũy được **301 nến 1d (322 ngày lịch ≈ 10,5 tháng)**.
   - Các mã TradFi khác chỉ có từ **165 đến 252 nến 1d (5,5 đến 9,5 tháng)**.
   - Riêng mã đối chứng Crypto `BTC-USDT` đạt **1.936 nến 1d (1.936 ngày lịch ≈ 5,3 năm)** (ĐẠT).

2. **Đo chiến lược khung giờ (1H) — Yêu cầu: Ít nhất 1 năm nến 1h (≥ 365 ngày lịch) VÀ dưới 1% khoảng trống bất thường:**
   - **KẾT QUẢ: KHÔNG CÓ MÃ TRADFI NÀO ĐẠT.**
   - Trên API BingX, dữ liệu nến 1h của các hợp đồng TradFi chỉ mới được lưu trữ từ khoảng tháng 02/2026 (Vàng, Bạc) hoặc cuối tháng 04/2026 (Dầu, S&P 500, NASDAQ 100).
   - Số ngày lịch nến 1h tối đa của TradFi chỉ đạt **210 ngày lịch (khoảng 7 tháng)**, hoàn toàn không chạm tới ngưỡng tối thiểu 365 ngày.
   - Mặc dù tỷ lệ khoảng trống bất thường của các mã TradFi khá thấp (0,2% – 0,6%, đều < 1%), nhưng độ dài dữ liệu không đủ.
   - Riêng mã đối chứng Crypto `BTC-USDT` đạt **20.558 nến 1h (857 ngày lịch ≈ 2,3 năm)** và tỷ lệ khoảng trống bất thường **0,0%** (ĐẠT).

3. **Trường hợp đặc thù của Forex (`NCFXEUR2USD-USDT`, `NCFXUSD2JPY-USDT`):**
   - BingX gắn trạng thái `status=25` (Tạm dừng giao dịch cuối tuần) cho toàn bộ nhóm Forex.
   - Khi ở trạng thái tạm dừng, API Klines (`/openApi/swap/v3/quote/klines`) và API Funding Rate (`/openApi/swap/v2/quote/fundingRate`) đều trả về mã lỗi `109415: is pause currently`.
   - Hệ quả: Không thể truy vấn hay nạp dữ liệu lịch sử của Forex vào các ngày cuối tuần.

> [!CAUTION]
> **KẾT LUẬN CHUNG:** Dữ liệu BingX TradFi hiện tại **HOÀN TOÀN KHÔNG ĐỦ ĐIỀU KIỆN** để thực hiện backtest hoặc đo lường bất kỳ chiến lược định lượng nào có ý nghĩa thống kê (ở cả khung ngày và khung giờ). Cần tiếp tục chờ BingX vận hành thêm thời gian để tích lũy dữ liệu hoặc phải sử dụng nguồn dữ liệu TradFi ngoài nếu muốn nghiên cứu chiến lược.

---

## 3. Chi tiết kết quả kiểm kê theo từng bước (§3 Brief 114)

### 3.1. Bước 1 — Nạp dữ liệu vào PostgreSQL (`bars_crypto`)
Dữ liệu được nạp bằng script chuẩn `scripts/bingx_klines.py` (chỉ chạy, không sửa code). Phạm vi nạp: từ ngày niêm yết sớm nhất đến **2026-08-31 23:59:59 UTC**.

| Mã | Khung 1d nạp mới | Khung 1h nạp mới | Ghi chú |
|---|---|---|---|
| `NCCOGOLD2USD-USDT` | 301 nến | 4.779 nến | Bắt đầu 1d: 2025-10-14, 1h: 2026-02-03 |
| `NCCOXAG2USD-USDT` | 199 nến | 4.654 nến | Bắt đầu 1d: 2026-02-11, 1h: 2026-02-11 |
| `NCCO1OILWTI2USD-USDT` | 165 nến | 2.838 nến | Bắt đầu 1d: 2026-03-09, 1h: 2026-04-28 |
| `NCSISP5002USD-USDT` | 252 nến | 2.753 nến | Bắt đầu 1d: 2025-11-26, 1h: 2026-04-28 |
| `NCSINASDAQ1002USD-USDT` | 252 nến | 2.753 nến | Bắt đầu 1d: 2025-11-26, 1h: 2026-04-28 |
| `NCFXEUR2USD-USDT` | 0 nến | 0 nến | Sàn trả lỗi 109415 (pause cuối tuần) |
| `NCFXUSD2JPY-USDT` | 0 nến | 0 nến | Sàn trả lỗi 109415 (pause cuối tuần) |
| `NCSKAAPL2USD-USDT` | 248 nến | 3.592 nến | Bắt đầu 1d: 2025-11-13, 1h: 2026-03-17 |
| `NCSKNVDA2USD-USDT` | 246 nến | 3.592 nến | Bắt đầu 1d: 2025-11-13, 1h: 2026-03-17 |
| `BTC-USDT` | 1.936 nến | 20.558 nến | Dữ liệu đối chứng crypto liên tục |
| **Tổng cộng** | **3.599 nến** | **45.519 nến** | Ghi đầy đủ vào DB, không lỗi ràng buộc |

### 3.2. Bước 2 — Hồ sơ giờ giao dịch (Ma trận 7x24 UTC) và kiểm định chất lượng nến
Ma trận được tính bằng hàm thuần `build_hourly_profile_matrix(bars_1h)`. Các con số thể hiện số lượng nến xuất hiện tại từng ô (Thứ trong tuần × Giờ UTC).
Hồ sơ giờ cho thấy BingX tạo nến giao dịch cho TradFi xuyên suốt cả tuần (kể cả Thứ 7 và Chủ nhật với mật độ nến thấp hơn hoặc nghỉ vài giờ chuyển phiên).

#### Hồ sơ giờ: `NCCOGOLD2USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  30 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 28 28 25 29
Thứ 3  29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 25 30
Thứ 4  30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 25 30
Thứ 5  30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 25 30
Thứ 6  30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 26 26
Thứ 7  26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26
CN (Su 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 30
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **2 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-02-06 21:00:00+00:00` đến `2026-02-08 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-13 21:00:00+00:00` đến `2026-02-15 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-20 21:00:00+00:00` đến `2026-02-22 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-27 21:00:00+00:00` đến `2026-03-01 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-16 19:00:00+00:00` đến `2026-02-16 23:00:00+00:00` (4.0h / 0.17 ngày)

#### Hồ sơ giờ: `NCCOXAG2USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  29 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 27 27 25 28
Thứ 3  28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 25 28
Thứ 4  28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 25 29
Thứ 5  29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 26 29
Thứ 6  29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 26 26
Thứ 7  26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26
CN (Su 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 26 29
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **1 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-02-13 21:00:00+00:00` đến `2026-02-15 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-20 21:00:00+00:00` đến `2026-02-22 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-27 21:00:00+00:00` đến `2026-03-01 23:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-02-16 19:00:00+00:00` đến `2026-02-16 23:00:00+00:00` (4.0h / 0.17 ngày)
  + Từ `2026-02-11 21:00:00+00:00` đến `2026-02-11 23:00:00+00:00` (2.0h / 0.08 ngày)

#### Hồ sơ giờ: `NCCO1OILWTI2USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  18 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 14 17 17
Thứ 3  17 17 17 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 14 18 18
Thứ 4  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 15 18 18
Thứ 5  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 15 18 18
Thứ 6  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 15 15 15
Thứ 7  15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15
CN (Su 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 15 18 18
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **2 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-05-01 20:00:00+00:00` đến `2026-05-03 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-08 20:00:00+00:00` đến `2026-05-10 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-15 20:00:00+00:00` đến `2026-05-17 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-04-28 20:00:00+00:00` đến `2026-04-28 22:00:00+00:00` (2.0h / 0.08 ngày)
  + Từ `2026-04-29 20:00:00+00:00` đến `2026-04-29 22:00:00+00:00` (2.0h / 0.08 ngày)

#### Hồ sơ giờ: `NCSISP5002USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  18 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17
Thứ 3  17 17 17 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 4  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 5  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 6  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 13 13 13
Thứ 7  13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13
CN (Su 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 18 18
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **2 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-05-01 20:00:00+00:00` đến `2026-05-03 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-08 20:00:00+00:00` đến `2026-05-10 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-15 20:00:00+00:00` đến `2026-05-17 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-22 20:00:00+00:00` đến `2026-05-24 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-29 20:00:00+00:00` đến `2026-05-31 22:00:00+00:00` (50.0h / 2.08 ngày)

#### Hồ sơ giờ: `NCSINASDAQ1002USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  18 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17 17
Thứ 3  17 17 17 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 4  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 5  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18
Thứ 6  18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 18 13 13 13
Thứ 7  13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13
CN (Su 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 13 18 18
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **2 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-05-01 20:00:00+00:00` đến `2026-05-03 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-08 20:00:00+00:00` đến `2026-05-10 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-15 20:00:00+00:00` đến `2026-05-17 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-22 20:00:00+00:00` đến `2026-05-24 22:00:00+00:00` (50.0h / 2.08 ngày)
  + Từ `2026-05-29 20:00:00+00:00` đến `2026-05-31 22:00:00+00:00` (50.0h / 2.08 ngày)

#### Hồ sơ giờ: `NCFXEUR2USD-USDT` (Phân loại: Không có dữ liệu (pause))
- *Không có dữ liệu 1h (API tạm dừng do sàn pause cuối tuần).*

#### Hồ sơ giờ: `NCFXUSD2JPY-USDT` (Phân loại: Không có dữ liệu (pause))
- *Không có dữ liệu 1h (API tạm dừng do sàn pause cuối tuần).*

#### Hồ sơ giờ: `NCSKAAPL2USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  21 20 20 20 20 20 20 20 20 20 20 20 20 23 23 23 23 23 23 23 23 20 20 20
Thứ 3  20 20 20 20 20 20 20 20 20 20 20 20 20 24 24 24 24 24 24 24 24 20 20 20
Thứ 4  20 20 20 20 20 20 20 20 20 21 21 21 21 24 24 24 24 24 24 24 24 21 21 21
Thứ 5  21 21 21 21 21 21 21 21 21 21 21 21 21 24 24 24 24 24 24 24 24 21 21 21
Thứ 6  21 21 21 21 21 21 21 21 21 21 21 21 21 23 23 23 23 23 23 23 23 21 21 21
Thứ 7  21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21
CN (Su 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **1 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-04-02 20:00:00+00:00` đến `2026-04-06 13:00:00+00:00` (89.0h / 3.71 ngày)
  + Từ `2026-03-20 20:00:00+00:00` đến `2026-03-23 13:00:00+00:00` (65.0h / 2.71 ngày)
  + Từ `2026-03-27 20:00:00+00:00` đến `2026-03-30 13:00:00+00:00` (65.0h / 2.71 ngày)
  + Từ `2026-03-17 20:00:00+00:00` đến `2026-03-18 13:00:00+00:00` (17.0h / 0.71 ngày)
  + Từ `2026-03-18 20:00:00+00:00` đến `2026-03-19 13:00:00+00:00` (17.0h / 0.71 ngày)

#### Hồ sơ giờ: `NCSKNVDA2USD-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  21 20 20 20 20 20 20 20 20 20 20 20 20 23 23 23 23 23 23 23 23 20 20 20
Thứ 3  20 20 20 20 20 20 20 20 20 20 20 20 20 24 24 24 24 24 24 24 24 20 20 20
Thứ 4  20 20 20 20 20 20 20 20 20 21 21 21 21 24 24 24 24 24 24 24 24 21 21 21
Thứ 5  21 21 21 21 21 21 21 21 21 21 21 21 21 24 24 24 24 24 24 24 24 21 21 21
Thứ 6  21 21 21 21 21 21 21 21 21 21 21 21 21 23 23 23 23 23 23 23 23 21 21 21
Thứ 7  21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21
CN (Su 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21 21
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **1 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).
- **Top khoảng trống bất thường dài nhất:**
  + Từ `2026-04-02 20:00:00+00:00` đến `2026-04-06 13:00:00+00:00` (89.0h / 3.71 ngày)
  + Từ `2026-03-20 20:00:00+00:00` đến `2026-03-23 13:00:00+00:00` (65.0h / 2.71 ngày)
  + Từ `2026-03-27 20:00:00+00:00` đến `2026-03-30 13:00:00+00:00` (65.0h / 2.71 ngày)
  + Từ `2026-03-17 20:00:00+00:00` đến `2026-03-18 13:00:00+00:00` (17.0h / 0.71 ngày)
  + Từ `2026-03-18 20:00:00+00:00` đến `2026-03-19 13:00:00+00:00` (17.0h / 0.71 ngày)

#### Hồ sơ giờ: `BTC-USDT` (Phân loại: 24/7 (Liên tục))
```text
      00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Thứ 2  123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123
Thứ 3  122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122
Thứ 4  122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122
Thứ 5  122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122
Thứ 6  122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122 122
Thứ 7  122 122 122 122 122 122 122 122 122 122 123 123 123 123 123 123 123 123 123 123 123 123 123 123
CN (Su 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123 123
```
- **Nến bẩn / Volume 0:** 1D có 0 nến bẩn và 0 nến volume 0; 1H có 0 nến bẩn và 0 nến volume 0.
- **Đối chiếu 1H → 1D:** Số ngày lệch > 0,1% là **1 ngày** (tất cả đều do nến biên bị cắt ở ngày đầu hoặc ngày cuối nạp).

### 3.3. Bước 3 — Funding Rate và Chu kỳ thanh toán
Endpoint công khai sử dụng (public, unsigned, lấy từ tài liệu chính thức BingX):
`GET https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate?symbol={symbol}&limit=100`  

**Phát hiện quan trọng về cơ chế Funding của BingX:**
- **Nhóm Hàng hóa (`NCCOGOLD2USD-USDT`, `NCCOXAG2USD-USDT`, `NCCO1OILWTI2USD-USDT`):** Chu kỳ thanh toán funding là **4 giờ một lần (6 lần/ngày)** thay vì 8 giờ như thông thường!
- **Nhóm Cổ phiếu (`AAPL`, `NVDA`), Chỉ số (`S&P 500`, `NASDAQ 100`) và Crypto (`BTC`):** Chu kỳ thanh toán là **8 giờ một lần (3 lần/ngày)**.
- **Biên độ Funding Rate:**
  + Vàng: Rate trung bình `+0.0094%`/4h (người giữ Long trả Short).
  + Bạc: Rate trung bình `+0.0077%`/4h.
  + Dầu WTI: Rate trung bình âm sâu `-0.0286%`/4h (Short trả Long, tương đương ~0.17%/ngày!).
  + S&P 500: Rate trung bình `-0.0034%`/8h.
  + NASDAQ 100: Rate trung bình `+0.0002%`/8h.

### 3.4. Bước 4 — Chi phí giao dịch so với biến động (Taker Fee vs ATR 1h)
Thông số phí từ BingX Contract Details: Maker = 0,02% (0,0002), Taker = 0,05% (0,0005).
Phí một vòng giao dịch Taker (vào + ra) = **2 × 0,05% = 0,10%**.

| Mã | Median ATR14 (1h) | Phí 2 chiều Taker | Tỷ lệ Phí / ATR 1h | Đánh giá ma sát chi phí |
|---|---|---|---|---|
| `NCCOGOLD2USD-USDT` | 0.382% | 0.100% | **26.2%** | **CAO** (Chi phí đáng kể so với bước sóng 1h) |
| `NCCOXAG2USD-USDT` | 0.748% | 0.100% | **13.4%** | Trung bình (tương đương crypto) |
| `NCCO1OILWTI2USD-USDT` | 0.813% | 0.100% | **12.3%** | Trung bình (tương đương crypto) |
| `NCSISP5002USD-USDT` | 0.187% | 0.100% | **53.6%** | **CỰC KỲ CAO** (Ma sát nuốt phần lớn biên lợi nhuận) |
| `NCSINASDAQ1002USD-USDT` | 0.305% | 0.100% | **32.8%** | **CỰC KỲ CAO** (Ma sát nuốt phần lớn biên lợi nhuận) |
| `NCFXEUR2USD-USDT` | N/A | 0,100% | N/A | Không có dữ liệu | 
| `NCFXUSD2JPY-USDT` | N/A | 0,100% | N/A | Không có dữ liệu | 
| `NCSKAAPL2USD-USDT` | 0.347% | 0.100% | **28.8%** | **CAO** (Chi phí đáng kể so với bước sóng 1h) |
| `NCSKNVDA2USD-USDT` | 0.509% | 0.100% | **19.7%** | Trung bình (tương đương crypto) |
| `BTC-USDT` | 0.613% | 0.100% | **16.3%** | Trung bình (tương đương crypto) |

> [!WARNING]
> **Phát hiện cấu trúc:** Với chỉ số chứng khoán như `S&P 500` (`NCSISP5002USD-USDT`), biến động nến 1h rất hẹp (ATR trung vị chỉ 0,187%), trong khi phí vào ra taker cố định 0,10%. Hệ quả là **phí taker chiếm tới 53,6% biên độ nến 1h**. Nếu giao dịch chiến lược tần suất 1h bằng lệnh market trên S&P 500, hệ số ma sát sẽ bào mòn hoàn toàn kỳ vọng lợi nhuận.

### 3.5. Bước 5 — Phép phá thử (Destructive Testing) và Kiểm định toàn bộ
1. **Bộ test hàm thuần:** Đã xây dựng bộ unit test gồm **8 test cases** trong `tests/test_inventory_bingx_tradfi.py`:
   - `test_build_hourly_profile_matrix`: Kiểm tra ma trận 7x24 phân bổ đúng ngày giờ.
   - `test_classify_trading_schedule`: Kiểm tra phân loại 24/7, 24/5 và theo phiên.
   - `test_aggregate_1h_to_daily`: Kiểm tra gộp OHLCV từ nến 1h, trong đó close lấy từ nến cuối cùng.
   - `test_compare_1h_aggregated_with_1d`: Kiểm tra phát hiện sai lệch > 0,1%.
   - `test_detect_gaps_normal_vs_abnormal`: Kiểm tra phân biệt khoảng nghỉ cuối tuần bình thường vs gián đoạn bất thường.
   - `test_calculate_cost_to_atr_ratio`: Kiểm tra tính ATR% trung vị và tỷ lệ phí/ATR.
   - `test_analyze_funding_history`: Kiểm tra tính chu kỳ funding và mức rate trung bình.
   - `test_count_dirty_and_zero_volume_bars`: Kiểm tra đếm nến bẩn và volume 0.

2. **Phép phá thử (Mutation Test):**
   - Sao lưu file `scripts/inventory_bingx_tradfi.py` ra thư mục scratch bên ngoài workspace.
   - Đột biến hàm `aggregate_1h_to_daily`: Thay close của nến cuối ngày (`sorted_bars[-1]["close"]`) bằng nến đầu ngày (`sorted_bars[0]["close"]`).
   - Chạy `uv run pytest tests/test_inventory_bingx_tradfi.py -k test_aggregate_1h_to_daily` → **FAILED (RED) chính xác: `assert 102.0 == 97.0`.**
   - Khôi phục file từ thư mục sao lưu scratch (tuyệt đối không dùng git restore/checkout).
   - Chạy lại test → **PASSED (GREEN) 100%.**

3. **Kiểm tra chất lượng toàn hệ thống:**
   - Unit test toàn bộ repo: `uv run pytest -m "not integration" -q` → **1193 passed, 137 deselected in 33.43s.**
   - Linter: `uv run ruff check trading tests scripts/inventory_bingx_tradfi.py` → **All checks passed!**

---

Tôi không commit, không push, không gọi endpoint có ký, không đặt lệnh, không đọc dữ liệu từ 2026-09-01.
---

## Ghi chú kiểm chứng của Claude (27/09/2026)

**Kết luận chính đứng vững:** không mã TradFi nào đủ dữ liệu để đo, dù ở khung ngày hay khung giờ. Claude đếm lại trực tiếp trong `bars_crypto` và thấy khớp:
- vàng: 301 nến 1d, từ 14/10/2025;
- S&P 500 / NASDAQ 100: 252 nến 1d.

Có ba chỗ phải đọc lại:

1. **Nhãn "24/7 (Liên tục)" chỉ đúng cho giai đoạn gần đây.** Nến cuối tuần có mặt, nhưng mỗi mã có 3–5 khoảng trống đúng **50 giờ**, từ thứ Sáu 21:00 UTC đến Chủ nhật 23:00 UTC. Ví dụ vàng ngày 06/02, 13/02 và 20/02/2026. Tức là **giai đoạn đầu có nghỉ cuối tuần**, sau đó BingX mới chuyển sang 24/7. Các khoảng này là thay đổi lịch giao dịch, không phải lỗi dữ liệu.
2. **Lịch sử nến 1h ngắn hơn nhiều so với nến 1d:**

   | Mã | Nến 1d từ | Nến 1h từ |
   |---|---|---|
   | Vàng | 14/10/2025 | 03/02/2026 |
   | S&P 500 | 26/11/2025 | 28/04/2026 |

   Nhiều khả năng đây là giới hạn độ sâu của API cho khung 1h (chưa xác minh).
3. **Forex (EUR/USD, USD/JPY) CHƯA NẠP ĐƯỢC.** Đây không phải "không đủ". Việc nạp chạy vào Chủ nhật, lúc sàn tạm dừng các mã này, nên API trả mã lỗi 109415. Phải **chạy lại vào ngày thường**. Với độ dài niêm yết hiện có (khoảng 12 tháng), forex gần như chắc chắn vẫn không đạt 3 năm nến 1d.

**Phát hiện đáng giữ lại:**
- **phí/ATR1h rất cao:** S&P 500 53,6%, NASDAQ 32,8%, vàng 26,2%. Giao dịch khung giờ trên các mã này gần như chắc chắn bị phí ăn hết;
- **funding của dầu WTI âm sâu** (trung bình −0,0286% mỗi 4 giờ);
- **chu kỳ funding:** 4 giờ với hàng hoá, 8 giờ với cổ phiếu và chỉ số.
