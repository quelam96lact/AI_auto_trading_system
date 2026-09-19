# Audit đợt 61 — TỪ CHỐI: chiến lược dùng đòn vay ảo không có thật trong tài khoản thật

**Kết luận: KHÔNG chấp nhận báo cáo đợt 61. Không commit. Con số +1.463,55 tỷ (trong mẫu) và
+323,72 tỷ (ngoài mẫu) của "buy-and-hold có nhịp" không đáng tin — cả PnL lẫn max drawdown.**

---

## 1. Lỗi, nói bằng một câu

`simulate_symbol_regime_hold` trong `scripts/measure_regime_hold.py` tính **`qty`
(số cổ phiếu mỗi lần mua) đúng MỘT LẦN ở đầu kỳ 10 năm**, rồi dùng lại y nguyên con số đó cho
**mọi lần mua lại sau này** — bất kể `cash` hiện có còn bao nhiêu. Khi giá lúc mua lại cao hơn
đáng kể so với lúc bán, việc mua đủ `qty` cũ khiến **`cash` bị âm** — nghĩa là chương trình cho
phép mua cổ phiếu bằng tiền không tồn tại. Đó là đòn bẩy ảo, miễn phí, không giới hạn — thứ không
tài khoản chứng khoán thật nào cấp cho ai.

## 2. Bằng chứng — không suy luận, đo trực tiếp

Dựng một mã giả với đúng hình dạng "bán lúc giá thấp, mua lại lúc giá đã phục hồi cao" — chính
kịch bản mà báo cáo tự mô tả là nguyên nhân thua lỗ ngoài mẫu ("whipsaw... bán ra đúng đáy hoảng
loạn... rồi phải mua lại ở giá cao khi thị trường đã bật tăng"):

```
qty co dinh tinh MOT LAN duy nhat o dau ky: 99700 cp (gia ngay 1 = 10)

2026-01-01: MUA 99700 cp @ 10 -> chi 999,992      | CASH SAU KHI MUA = 8
2026-01-04: BAN 99700 cp @ 10 -> thu 993,014       | CASH SAU KHI BAN = 993,021
2026-01-07: MUA 99700 cp @ 30 -> chi 2,999,977     | CASH SAU KHI MUA = -2,006,955

*** CASH AM: -2,006,955 VND (-200.7% so voi von goc 1.000.000) ***
```

Với vốn ban đầu 1 triệu, sau một lần mua lại ở giá cao, `cash` âm **hơn hai lần** vốn gốc. Chương
trình vẫn tiếp tục chạy như không có chuyện gì — nó không kiểm `cash >= cost` trước khi mua.

## 3. Vì sao bốn test đều xanh mà không bắt được lỗi này

`tests/test_regime_hold.py::test_mua_ban_dung_gia_va_phi` — test duy nhất kiểm hai lần giao
dịch — dùng kịch bản **bán ở 12.0, mua lại ở 11.0 (THẤP hơn)**. Test đó tự tay tính lại bằng đúng
công thức có lỗi (dùng `qty` cố định từ giá ngày đầu) rồi so khớp với code — nên nó **xác nhận
lỗi là đúng thiết kế**, không phát hiện ra nó. Không test nào dựng kịch bản giá mua lại cao hơn
giá bán, và không test nào khẳng định `cash` không bao giờ âm.

## 4. Tôi phải nhận một phần lỗi này

Brief đợt 61 mục 2.3 viết: *"giữ nguyên số lượng cổ phiếu tính từ lần mua gần nhất"* — câu đó mơ
hồ giữa hai cách đọc:

- (a) mỗi lần mua, tính lại `qty` theo `cash` đang có tại thời điểm đó, rồi giữ `qty` đó không
  đổi cho tới lần bán tiếp theo (đúng cách một tài khoản thật hoạt động);
- (b) dùng đúng `qty` đã tính từ **lần mua đầu tiên của cả kỳ 10 năm**, không bao giờ tính lại
  (cách agent đã hiểu và làm).

Tôi không tách rõ hai cách đọc này khi viết brief, dù đã cảnh báo đúng ngay bên cạnh câu đó rằng
"kết quả sẽ lệch mà không ai biết lệch bao nhiêu" nếu chọn sai cách. Sự mơ hồ đó là lỗi của tôi,
không phải của agent — agent làm đúng một cách đọc hợp lệ của một câu viết chưa đủ rõ.

## 5. Ảnh hưởng: cả PnL lẫn max drawdown đều không dùng được

- **Mua-và-giữ thuần** (không đổi trạng thái, không mua lại) — **không bị ảnh hưởng**. Số
  +1.007,12 tỷ (trong mẫu) và +657,94 tỷ (ngoài mẫu) vẫn đúng, khớp đợt 9.
- **"Buy-and-hold có nhịp"** — bị ảnh hưởng ở **mọi lần mua lại sau lần đầu tiên** (23 lần trong
  mẫu, 20 lần ngoài mẫu, trừ lần mua đầu mỗi kỳ). Không chỉ PnL sai mà **max drawdown cũng sai**:
  ngay sau một lần mua lại có đòn vay ảo, giá trị danh mục thật ra đang chịu rủi ro lớn hơn nhiều
  so với vốn thật đang có, nhưng đường vốn báo cáo không phản ánh điều đó.

Không thể sửa bằng cách trừ đi một con số ước lượng — phải chạy lại từ đầu với công thức đúng.

## 6. Việc cần làm — xem brief đợt 62
