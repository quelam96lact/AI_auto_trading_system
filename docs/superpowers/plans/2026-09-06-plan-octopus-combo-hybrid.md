# Kế hoạch Triển khai & Đo lường Chiến lược Lai Octopus + Combo (Hybrid Strategy)

**Ngày lập**: 2026-09-06  
**Mục tiêu**: Kết hợp sức mạnh sàng lọc xu hướng/thanh khoản/pullback của Octopus với cơ chế khớp lệnh STOP bảo vệ giá của Combo Candlestick, giải quyết triệt để vấn đề "bắt dao rơi" và "đu đỉnh giả" (false breakout).

---

## 1. Động Lực & Cơ Sở Lý Thuyết

| Thành phần | Octopus Nguyên Bản | Combo Nguyên Bản | Octopus + Combo Hybrid |
| :--- | :--- | :--- | :--- |
| **Lọc Xu hướng** | $\text{Close} > \text{EMA}(200)$ | $\text{Close} > \text{MA}(20)$ | $\text{Close} > \text{EMA}(200) \land \text{Close} > \text{MA}(20)$ |
| **Lọc Pullback** | $\ge 2$ nến đỏ trong 5 phiên | Không lọc pullback | $\ge 2$ nến đỏ trong 5 phiên |
| **Nến Kích hoạt** | EMA9 cắt lên EMA21 & MACD>0 | Nến xanh & MACD>0 | Nến xanh + EMA9>EMA21 & MACD>0 |
| **Cơ chế Vào lệnh** | Mua trực tiếp tại **Open** phiên sau | Lệnh chờ **BUY STOP** $= \text{High} + x$ | Lệnh chờ **BUY STOP** $= \text{High} + x$ |
| **Lọc Thanh khoản** | $\ge 2\text{ tỷ VND/ngày}$ | Không lọc thanh khoản | $\ge 2\text{ tỷ VND/ngày}$ (`DailyLiquidityTracker`) |
| **Chặn Lỗ (SL)** | Trailing Stop $2.0 \times \text{ATR}$ | $\text{SL} = \text{Low} - x$ | $\text{SL} = \text{Low} - x$ (hoặc Trailing Stop) |

---

## 2. Đặc Tả Thuật Toán Chi Tiết (5 Tầng Logic)

1. **Tầng 1 (Thanh khoản gộp theo ngày)**:  
   Bình quân giá trị giao dịch 20 ngày đã đóng trước đó $\ge 2\text{ tỷ VND}$ (dùng `DailyLiquidityTracker`).
2. **Tầng 2 (Xu hướng vĩ mô)**:  
   $\text{Close} > \text{EMA}(200)$ và $\text{Close} > \text{MA}(20)$.
3. **Tầng 3 (Vùng điều chỉnh Pullback)**:  
   Có ít nhất 2 nến đỏ ($\text{Close} < \text{Open}$) trong 5 phiên trước bar hiện tại.
4. **Tầng 4 (Tín hiệu đảo chiều)**:  
   - Bar hiện tại là nến XANH ($\text{Close} > \text{Open}$).
   - $\text{EMA}(9) > \text{EMA}(21)$ (hoặc cắt lên) và $\text{MACD Histogram} > 0$.
5. **Tầng 5 (Vào lệnh có điều kiện)**:  
   - Đặt lệnh chờ **$\text{BUY STOP} = \text{High} + 0.1 \times \text{ATR}(5)$**.
   - Cắt lỗ ban đầu: $\text{SL} = \text{Low} - 0.1 \times \text{ATR}(5)$.
   - Chốt lời: $\text{TP} = \text{Entry} + k_{\text{TP}} \times \text{ATR}(5)$ (quét $k_{\text{TP}} \in [1.5, 2.0, 2.3, 2.6]$).
   - Chỉ khớp lệnh tại phiên sau nếu $\text{High}_{\text{next}} \ge \text{BUY STOP}$. Nếu không chạm đỉnh $\rightarrow$ lệnh STOP tự động huỷ bỏ.

---

## 3. Các Bước Triển Khai

- [x] **Bước 1: Lập Plan Chi tiết** (`docs/superpowers/plans/2026-09-06-plan-octopus-combo-hybrid.md`).
- [ ] **Bước 2: Cập nhật Engine Backtest** (`trading/pattern_backtest.py`):
  - Bổ sung cấu hình `strategy_name="octopus_combo"`.
  - Tích hợp `DailyLiquidityTracker`, `EmaCalculator(200, 9, 21)`, bộ đếm nến đỏ và BUY STOP.
- [ ] **Bước 3: Viết Unit Test** (`tests/test_pattern_backtest.py`):
  - Test đầy đủ các kịch bản: tín hiệu hợp lệ, thiếu thanh khoản, thiếu nến đỏ, nến đỏ không vượt đỉnh (lệnh huỷ), nến vượt đỉnh (khớp lệnh thành công).
- [ ] **Bước 4: Viết Script Đo lường Diện rộng** (`scripts/measure_octopus_combo_hybrid.py`):
  - Chạy so sánh trên 1.308 mã VN stock (`bars_daily`) và 20 cặp Crypto (`bars_crypto` 1D/1H).
  - So sánh trực tiếp 3 mô hình: Octopus Gốc vs Combo Gốc vs Hybrid.
  - Đo lường 2 giả định SL/TP (sl_first=True/False) và tỷ lệ vi phạm T+2.5.
- [ ] **Bước 5: Kiểm thử Hồi quy An toàn**:
  - Chạy lại baseline Octopus matched basket (đảm bảo giữ nguyên kết quả chuẩn).
  - Chạy toàn bộ test suite và linter ruff.
- [ ] **Bước 6: Biên soạn Báo cáo Nghiên cứu Tổng hợp** (`docs/superpowers/research/2026-09-06-bao-cao-octopus-combo-hybrid.md`).

---

## 4. Ràng Buộc Kỹ Thuật & An Toàn
1. Không sửa `PaperBroker`, `run_backtest`, `config/config.yaml`.
2. Giữ nguyên `real_trading_enabled: false`.
3. Không commit, không push (chờ bàn giao và Claude audit).
