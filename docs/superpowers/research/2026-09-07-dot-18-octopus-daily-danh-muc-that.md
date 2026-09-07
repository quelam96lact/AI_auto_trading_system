# Báo cáo kết quả đo octopus_pullback trên 5 mã danh mục thật

Ngày: 07/09/2026 (08/09/2026)
Lệnh chạy: `uv run python scripts/measure_strategy.py --strategy octopus_pullback --symbols FOX,HCM,SSI,TCX,VCB`
Kỳ đo: 2016-01-04 -> 2026-08-13 (mặc định của `measure_strategy.py`)
Vốn: 1.000.000.000 VND / mã

---

## Output nguyên văn

```text
==============================================================================
ĐO DIỆN RỘNG — OCTOPUS_PULLBACK (khung 1d, T+2,5, có phí)
Lọc thanh khoản: rolling-20 close*volume >= 2,000,000,000 (point-in-time, trong strategy)
Kỳ đo: 2016-01-04 -> 2026-08-13 | vốn MỖI MÃ: 1,000,000,000 | số mã: 5
==============================================================================

[1] TỔNG PNL — CHIẾN LƯỢC vs MUA-VÀ-GIỮ (cùng mã, cùng kỳ, cùng vốn, cùng phí)
  Tổng PnL chiến lược :         14,964,927
  Tổng PnL mua-và-giữ :     18,010,441,854
  Chênh lệch (strat - BH): -17,995,476,928
  KẾT LUẬN: THUA mua-và-giữ — không có biên lợi thế trên diện rộng.

[2] CỠ MẪU
  Tổng số lệnh (SELL fills): 33
  Số mã thực sự sinh lệnh  : 4/5
  Số mã TỪNG đủ thanh khoản: 5/5 (100.0% nếu n>0)
  CẢNH BÁO: tổng lệnh < 300 — kết luận dễ rơi vào bẫy cỡ mẫu nhỏ.

[3] DỮ LIỆU BẨN (OHLC<=0)
  Tổng số dòng bị loại: 24 trên 4 mã
  Top 10 mã bẩn nhất:
    FOX          21 dòng  (0.9% số bar của mã)
    HCM           1 dòng  (0.0% số bar của mã)
    SSI           1 dòng  (0.0% số bar của mã)
    VCB           1 dòng  (0.0% số bar của mã)
  Không mã nào đạt ngưỡng bar rác >= 5%.

[4] PHÂN PHỐI THEO MÃ
  Số mã thắng mua-và-giữ : 1
  Số mã thua mua-và-giữ  : 4
  Số mã hòa (diff = 0)   : 0
  Trung vị chênh lệch (strat - BH)/mã : -3,484,528,534
  Trung vị PnL chiến lược/mã          : 0
  Trung vị PnL mua-và-giữ/mã          : 3,529,462,222
  Tỷ lệ mã thắng BH: 20.0%

==============================================================================
TỔNG: strat 14,964,927 | BH 18,010,441,854 | diff -17,995,476,928 | lệnh 33 | mã sinh lệnh 4 | mã đủ thanh khoản 5 | dòng bẩn 24
```

---

## 1. Số đo tổng hợp

- **Tổng PnL chiến lược**: +14.964.927 VND (trên tổng vốn giả định 5 tỷ đồng, 1 tỷ/mã).
- **Tổng PnL mua-và-giữ**: +18.010.441.854 VND.
- **Chênh lệch (Chiến lược − Mua-và-giữ)**: −17.995.476.928 VND.
- **Tổng số lệnh (SELL fills)**: 33 lệnh.
- **Số mã thực sự sinh lệnh**: 4 / 5 mã (FOX, HCM, SSI, VCB có lệnh; TCX không có lệnh).
- **Số mã từng đủ thanh khoản (`liquid=True`)**: 5 / 5 mã (100%).

---

## 2. Bảng từng mã (5 dòng)

| Symbol | Số lệnh (SELL fills) | PnL chiến lược (VND) | PnL mua-và-giữ (VND) | Chênh lệch (Strat − BH) (VND) | Đạt ngưỡng thanh khoản (`liquid`) |
|---|---|---|---|---|---|
| **FOX** | 2 | +18.543.976 | +5.618.860.573 | −5.600.316.597 | True |
| **HCM** | 15 | −27.462.621 | +5.899.277.952 | −5.926.740.573 | True |
| **SSI** | 8 | −21.050.117 | +2.995.808.879 | −3.016.858.995 | True |
| **TCX** | 0 | 0 | −32.967.772 | +32.967.772 | True |
| **VCB** | 8 | +44.933.688 | +3.529.462.222 | −3.484.528.534 | True |

---

## 3. Đối chiếu với các baseline đã có

| Đợt đo | Rổ mã đo | Số mã | Số lệnh (SELL fills) | Tổng PnL chiến lược (VND) |
|---|---|---|---|---|
| **Đợt 4** | Toàn bộ cổ phiếu lọc thanh khoản (rổ chung, 1d) | 439 mã sinh lệnh / 1.308 mã | 1.514 | −1.615.319.902 |
| **Đợt 11** | Rổ 5m chung | 310 mã | 574 | PF 0,47 (thua lỗ) |
| **Đợt 18** (hiện tại) | Đúng 5 mã danh mục thật tài khoản 0434226 (1d) | 4 mã sinh lệnh / 5 mã | 33 | +14.964.927 |