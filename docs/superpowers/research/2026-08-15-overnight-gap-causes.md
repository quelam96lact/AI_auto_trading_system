# Truy nguồn 837 bước nhảy qua đêm trong `bars_daily`

Ngày: 2026-08-15. Base: `7fd3a36`, nhánh `feature/data-layer`.
Thực thi: Hermes. Audit + chạy lại độc lập: Claude.

Tài liệu này chốt một câu hỏi đã mở từ `a7c6c41`. Ghi cả những chỗ **đo sai rồi
phải sửa**, vì trong đợt này đã sai ba lần và mỗi lần đều theo cùng một kiểu.

---

## Câu trả lời ngắn

1. **Dữ liệu bẩn nằm tại NGUỒN SSI, không phải ở đường ingest của ta.** Đối chiếu
   từng dòng DB vs API SSI trên 9 mẫu: mọi ngày chung khớp 100% cả OHLC lẫn volume.
   Backfill lại sẽ ghi y hệt. Cơ chế loại trừ (`--emit-exclusions` /`--exclude-file`)
   là cách xử lý đúng, không phải giải pháp tạm.
2. **Bước nhảy xảy ra TẠI PHIÊN, không phải qua đêm.** Bar ngày t mở cửa đã ở mức
   +32% so với `close(t-1)`. Không có phiên giao dịch nào bị DB bỏ sót giữa hai dòng
   (kiểm 10/10 mẫu với cửa sổ ±10 ngày) — nên **không phải** lỗi bộ đếm ngày mở cửa.
3. **Cơ chế chính xác vẫn chưa biết** và cần lịch sự kiện doanh nghiệp (ngày GDKHQ,
   chuyển sàn, đấu giá) để chốt. Không suy đoán thêm.

## Phân loại 837 bước nhảy

| Nguyên nhân | Sự kiện | Mã |
|---|---:|---:|
| Trở lại sau đình chỉ dài (≥10 ngày mở cửa trống) | 233 | 145 |
| Bar thiếu trong DB (1–9 ngày mở cửa trống) | 106 | 87 |
| Chia tách mạnh đã biết (trùng 51 sự kiện `a7c6c41`) | 20 | 19 |
| Nghi chia tách tỉ lệ lẻ | 43 | 41 |
| Phiên đầu sau niêm yết mới | 13 | 12 |
| **Không giải thích được** | **422** | **228** |

## Bằng chứng cho kết luận (2)

10 mẫu trong cụm tỉ lệ 1,32–1,335, đo lại độc lập từ DB (đổi `ts` sang giờ HCM):

```
mã   ngày         close(t-1)     open        high      volume  open/pc  high/pc  O=H=L=C
HNB  2016-03-31   13.676,164  18.057,847  18.057,847     100   1,3204   1,3204   có
VNI  2016-05-30        3.400       4.500       4.500     400   1,3235   1,3235   có
VRG  2016-11-25    1.555,655   2.053,465   2.053,465     200   1,3200   1,3200   có
HU4  2017-02-17    1.985,275   2.161,743   2.647,032   2.300   1,0889   1,3333   không
S12  2017-04-28          600         600         800   2.800   1,0000   1,3333   không
KSV  2017-08-23    3.488,728   4.636,917   4.636,917     500   1,3291   1,3291   có
TUG  2018-04-26    2.641,827   3.522,435   3.522,435     600   1,3333   1,3333   không
IPA  2018-06-13    4.208,165   5.208,125   5.583,110     200   1,2376   1,3267   không
PTH  2018-10-08    3.001,274   3.972,275   3.972,275     100   1,3235   1,3235   có
VTA  2018-12-28        4.800       6.200       6.400   1.600   1,2917   1,3333   không
```

5/10 có `O=H=L=C` với volume 100–500 cổ (1–5 lô) — **cả phiên chỉ khớp đúng một lệnh
ở mức giá mới**. 10/10 có `high ≥ 1,32 × close(t-1)` ngay trong phiên.

Một quan sát chưa kết luận: 4/10 có tỉ lệ **đúng bằng 4/3** (HU4, S12, TUG, VTA), số
còn lại rơi vào 1,32 / 1,3235 / 1,3267 / 1,3291 — không phải phân số đơn giản nào.

## Ba lần đo sai trong đợt này — cùng một kiểu lỗi

Ghi lại vì đây mới là thứ có giá trị lâu dài.

1. **Bộ lọc volume so với TRUNG VỊ của chính mã đó** (`a7c6c41`). Mã chết có trung vị
   volume = 0 nên tỉ lệ ra `None` và lọt qua như "volume bình thường". Kết luận
   "bars_daily chưa điều chỉnh" sai vì thế.
2. **Matcher lưới p/m** (Hermes tự bắt được giữa chừng, tự bỏ). Lưới `p,m ≤ 200` sai số
   1,5% khớp được MỌI tỉ lệ trong [0,4 ; 1,5], nên 349/349 "khớp gộp cổ phiếu" đều là
   báo động giả.
3. **Đo bước giá thô trên giá đã back-adjust** (Claude, trong lúc audit). Kết luận "chỉ
   19/422 là artifact bước giá, trung vị giá 8.616đ" **không đáng tin**: 69% bar đã bị
   nhân hệ số back-adjust, nên một bước giá thô 100đ có thể thành 44đ hoặc 130đ tuỳ mã.
   So ngưỡng tuyệt đối với giá đã scale là sai đơn vị. Phần kết luận về **thanh khoản**
   thì vẫn đứng (trung vị khối lượng bên nhỏ hơn = 200 cổ, 309/422 có một bên ≤ 1.000
   cổ) — vì volume không bị adjust.

Mẫu số chung: **một ngưỡng được tính từ chính dữ liệu mà nó phải sàng lọc, hoặc áp lên
dữ liệu đã bị biến đổi đơn vị, sẽ lặng lẽ cho qua tất cả và tạo ra một kết luận trông
rất thuyết phục.** Kiểm giá trị tuyệt đối, và kiểm xem đơn vị có còn nguyên không.

## Hệ quả cho việc đo chiến lược

Lọc theo **thanh khoản** có căn cứ; lọc theo **giá** thì không (xem lỗi 3 — giá trong
bảng này không so sánh trực tiếp được giữa các mã). Cơ chế loại trừ hiện có đã đủ cho
mục đích đo.

## Còn mở

Cơ chế (B) cụ thể. Bước tiếp rẻ nhất nếu muốn chốt: lấy lịch sự kiện doanh nghiệp
(ngày GDKHQ / chuyển sàn) cho ~10 mã trên rồi đối chiếu ngày nhảy. Chưa làm.
