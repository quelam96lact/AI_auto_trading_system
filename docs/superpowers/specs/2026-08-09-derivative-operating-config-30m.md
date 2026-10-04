# Spec: Cấu hình vận hành phái sinh vốn 30tr + xác minh biểu phí SSI

> **CẢNH BÁO (rà soát 04/10/2026): các con số backtest trong tài liệu này KHÔNG phải bằng chứng
> về lợi thế của cấu hình. Đừng dùng "+60%" làm cơ sở cho quyết định nào.** Lý do:
>
> 1. **Mẫu nhỏ và chọn trên chính mẫu đó:** 2 tháng (1.493 nến 5 phút), 21 lệnh; cấu hình "CHỐT"
>    được chọn từ 4 biến thể chạy trên cùng dữ liệu. Chưa có kiểm chứng ngoài mẫu.
> 2. **Chi phí thiếu:** tính phí 8.250 đồng/lượt, chưa có thuế TNCN (đợt 95, 26/09: khoảng 16
>    nghìn đồng/lượt, chiếm khoảng 2/3 tổng chi phí) và chưa có spread (đợt 93/98: trung vị 0,2
>    điểm). Chi phí khứ hồi thực khoảng 0,49 điểm cộng 0,2 điểm spread, so với 0,165 điểm đã tính.
>    Ước tính thiếu khoảng 0,5 điểm mỗi vòng, tức khoảng 1,1 triệu đồng trên 21 lệnh, nhỏ so với
>    +17,5 triệu: **chi phí không phải lỗ hổng chính, việc chọn cấu hình trên mẫu nhỏ mới là**.
> 3. **Khớp lệnh lạc quan:** backtest khớp tại giá đóng của chính nến sinh tín hiệu, không trượt
>    giá (xem `spread_points` trong `run_derivative_backtest` để thêm spread; độ lạc quan "khớp
>    cùng nến" vẫn còn).
> 4. **Các phép đo sau đó đều âm:** sáu phép đo liên tiếp (đợt 85 về VN30F1M trong phiên: 18/18
>    không tín hiệu; đợt 98 về SMC: 8/9 cặp không đạt) chưa tìm ra tín hiệu nào trả nổi chi phí thật.
> 5. **Checklist mục 4: hai việc quan trọng vẫn chưa làm:** paper trading tối thiểu 50 lệnh, và
>    kiểm chứng ngoài mẫu. (Ô về mô hình hóa thuế TNCN đã được làm ở đợt 95 nhưng chưa được tick.)
>
> Nội dung còn lại giữ nguyên làm hồ sơ lịch sử (biểu phí, ràng buộc ký quỹ D+ vẫn là tham khảo hữu ích).


**Ngày viết:** 2026-08-09
**Bối cảnh:** User chốt cấu hình vận hành cho tài khoản phái sinh khởi đầu
**30,000,000 VND**, dựa trên chuỗi nghiên cứu/backtest đã audit (multiplier
fix → fee thật → SL/TP → risk 2% + 2-loss + EOD 14:20 giữ lãi → daily-loss
theo ngày + ngưỡng giữ lãi). Spec này: (1) kết quả xác minh biểu phí SSI từ
nguồn chính thức, (2) cấu hình vận hành chốt, (3) checklist trước khi dùng
vốn thật. KHÔNG đặt lệnh thật — vẫn paper, đúng tinh thần spec phase1.

---

## 1. Xác minh biểu phí SSI (nguồn chính thức, 2026-08-09)

Nguồn: trang biểu phí SSI (qua r.jina.ai — SSI chặn truy cập trực tiếp):
`ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan`
(giao dịch thường) và `.../bieu-gia-dich-vu-giao-dich-chu-dong` (D+ / giao
dịch chủ động). Đối chiếu thêm: thuvienchungkhoan.vn, vfs.com.vn.

| Khoản phí | Giao dịch THƯỜNG | Giao dịch CHỦ ĐỘNG (D+) | Ghi chú |
|---|---|---|---|
| Phí dịch vụ SSI (<100 HĐ/ngày, Online) | **3,000đ** | **2,000đ** | Bậc 100-300: 2,000/1,500; >300: 1,000/500 |
| Trả HNX | **2,700đ/HĐ/giao dịch** | 2,700đ | Như nhau |
| Bù trừ VSD | **2,550đ/HĐ vị thế** | 2,550đ | VFS ghi 2,550đ/HĐ/TK/NGÀY — mơ hồ lượt vs ngày giữ |
| **TỔNG / lượt** | **8,250đ** ✓ | **7,250đ** ✓ | Khớp hằng số repo / khớp file user |
| Quản lý tài sản ký quỹ trả VSDC | 0.0024% giá trị lũy kế số dư | như nhau | CHƯA mô hình trong engine |
| Thuế TNCN | ~0.1% (theo công thức phổ biến) | như nhau | CHƯA mô hình |
| Ký quỹ cơ sở | 17% giá trị HĐ (mức VSDC) | — | Xác nhận bởi nhiều nguồn |

**Kết luận xác minh:**
1. `DERIVATIVE_FEE_PER_CONTRACT = 8,250` (commit 31abd04) **KHỚP CHÍNH XÁC**
   biểu phí giao dịch thường <100 HĐ/ngày: 3,000 + 2,700 + 2,550. ✓
2. Số "7,250đ/lượt" trong file user **KHỚP biểu phí D+** (2,000 + 2,700 +
   2,550). Nếu vận hành qua D+ (bắt buộc với vốn 30tr — xem mục 2), phí thực
   tế thấp hơn 1,000đ/lượt so với backtest → backtest hơi BI QUAN (an toàn).
3. Lưu ý file user ghi "SSI D+ hiển thị phí dịch vụ 7.000 đồng" — chênh 250đ
   so với 7,250 tính được; có thể iBoard hiển thị khác/tròn số — cần xác
   nhận trên màn hình thực tế.
4. **Xác nhận từ SSI iBoard (ảnh chụp user, 2026-08-09, 2 ảnh giống nhau —
   OCR Windows):**
   - Ký quỹ ban đầu D+ với VN30: **3% (trong ngày) / 6% (qua đêm)** ✓ khớp
     file user (VN100 cũng 3%/6%).
   - Phí dịch vụ hiển thị: **7.000 đồng** (cả trong ngày lẫn qua đêm) ✓ khớp
     file user. LƯU Ý: chênh 250đ so với 7,250 tính từ biểu phí công khai
     (2,000+2,700+2,550) — iBoard là nguồn vận hành thực tế, xem là 7,000.
   - Số vị thế tối đa/tài khoản: VN30: 300; VN100: 20.
   - Ngưỡng sử dụng ký quỹ: trong ngày 66% (tỷ lệ tối đa khuyến cáo — file
     user: "không xem 66% là mức nên dùng"), [80% cảnh báo], 100% ép đóng;
     qua đêm 98%/99%/100%.
   - **Lãi suất qua đêm: KHÔNG hiển thị trong 2 ảnh** — vẫn CHƯA xác nhận
     con số 0.0487%/ngày; cần xem màn hình chi tiết D+ khác nếu muốn chốt.
5. Phí chưa mô hình (rủi ro chi phí thực > backtest): phí quản lý ký quỹ
   0.0024%, thuế TNCN. LƯU Ý: VSD bù trừ **2,550đ/hợp đồng (per lượt giao
   dịch)** — đã xác nhận với user 2026-08-09, KHÔNG tính theo ngày giữ →
   giữ qua đêm không phát sinh thêm phí VSD.

## 2. Ràng buộc margin với vốn 30tr

- Base margin 17% @1900 = **32.3tr > 30tr** → KHÔNG đủ giữ qua đêm ở margin
  cơ sở tại giá hiện hành (1796-2022 trong sample).
- D+ intraday 3% = 5.7tr ✓, D+ qua đêm 6% = 11.4tr ✓ (đệm ~2.6x, thỏa
  khuyến nghị 1.25-1.5x của file user).
- **Kết luận: vốn 30tr CHỈ khả thi qua D+** (đòn bẩy ~5x intraday). Hệ quả:
  (a) phí/lượt là 7,250 (nếu xác nhận D+); (b) giữ qua đêm chịu lãi D+
  ~0.0487%/ngày trên phần tài trợ (~87k/đêm @1900, giả định chưa confirm);
  (c) ngưỡng "giữ lãi qua đêm" 1.0 điểm (100,000đ) đủ bù ~1 đêm D+ + phí đóng.

## 3. Cấu hình vận hành CHỐT (backtest đã kiểm chứng, sample 2 tháng)

| Thành phần | Giá trị | Nguồn |
|---|---|---|
| Chiến lược | `MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001)` | research 2026-08-08 (entry) |
| Vốn / số HĐ | 30,000,000 / **1 HĐ tối đa** | file user + margin |
| Risk | max_daily_loss_pct=0.02 (600k/ngày), max_consecutive_losses=2, tính theo NGÀY | plan 2026-08-09 (đã fix) |
| EOD | `intraday_close_time=time(14,20)`, `eod_keep_min_profit_points=1.0` | plan 2026-08-09 + tinh chỉnh user |
| SL/TP | TẮT (không SL, không TP) — EOD đã cắt lỗ cuối phiên, SL làm giảm avgW | backtest 30tr mục dưới |
| Phí (engine) | 8,250đ/lượt (giữ nguyên — conservative; đổi 7,250 khi xác nhận D+ và chuyển hằng số) | mục 1 |

**Backtest 30tr (2 tháng, 1493 bars 5m):**

| Config | Trd | Win% | PnL | Ret | MaxDD |
|---|---|---|---|---|---|
| Không EOD, không SL | 15 | 46.7% | 9,766,250 | +34.51% | **17.0%** |
| **EOD 14:20 ngưỡng 1.0 (CHỐT)** | 21 | 52.4% | 17,476,750 | **+60.05%** | **9.8%** |
| SL=5, không EOD | 25 | 32.0% | 15,293,750 | +51.36% | 13.3% |
| SL=5 + EOD ngưỡng 1.0 | 27 | 33.3% | 14,497,250 | +49.95% | 12.9% |

Lý do chốt EOD ngưỡng 1.0: MaxDD thấp nhất (9.8% ≈ 2.94tr — chấp nhận
được với 30tr), PnL cao nhất; SL=5 không cải thiện MaxDD khi đã có EOD.

## 4. Checklist TRƯỚC khi dùng vốn thật (thứ tự ưu tiên)

- [x] Xác nhận trên SSI iBoard: ký quỹ D+ **3% trong ngày / 6% qua đêm**
      ✓, phí dịch vụ **7.000đ** ✓ (chênh 250đ so với 7,250 tính từ biểu phí
      — iBoard là nguồn vận hành), số vị thế tối đa 300/20 ✓. Lãi suất qua
      đêm CHƯA hiển thị trong ảnh — cần xem màn hình chi tiết D+ nếu muốn.
- [x] Quyết định hằng số phí: **GIỮ 8,250** (user chốt 2026-08-09 —
      conservative; chênh lệch với D+ thực tế chỉ ~1,000-1,250đ/lượt ≈
      0.0125 điểm, không đáng kể so với biến động giá). Nếu sau này muốn
      chính xác theo D+ (7,000 iBoard / 7,250 biểu phí): plan TDD riêng.
- [x] Làm rõ VSD bù trừ: **2,550đ/hợp đồng (per lượt)** — user xác nhận
      2026-08-09, KHÔNG tính theo ngày giữ → giữ qua đêm không phát sinh
      thêm phí VSD (chỉ có lãi D+ qua đêm).
- [ ] Paper trading ít nhất 50 lệnh (theo file user) với đúng cấu hình trên,
      đối chiếu backtest trước khi vào tiền thật.
- [ ] Out-of-sample / dữ liệu dài hơn 2 tháng trước khi coi kết quả là bền vững.
- [ ] Cân nhắc mô hình hóa chi phí bổ sung (phí ký quỹ 0.0024%, thuế TNCN)
      nếu muốn báo cáo PnL ròng sát thực tế — plan TDD riêng nếu làm.

## 5. Ngoài phạm vi

- Đặt lệnh thật / wire vào live engine (đúng spec phase1: paper-only).
- Mô hình margin đầy đủ trong broker (17%, margin call) — đã flag từ plan
  2026-08-09, cần spec riêng.
- Thay đổi hằng số phí trong engine — chỉ thực hiện sau khi xác nhận D+ ở
  checklist, kèm plan TDD riêng.
