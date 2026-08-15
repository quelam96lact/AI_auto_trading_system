# Truy nguồn 837 bước nhảy qua đêm trong `bars_daily`

Ngày: 2026-08-15. Base: `7fd3a36`, nhánh `feature/data-layer`.
Thực thi: Hermes. Audit + chạy lại độc lập: Claude.

Tài liệu này chốt một câu hỏi đã mở từ `a7c6c41`. Ghi cả những chỗ **đo sai rồi
phải sửa**, vì trong đợt này đã sai ba lần và mỗi lần đều theo cùng một kiểu.

---

## Câu trả lời ngắn

1. **Đường ingest được minh oan: DB khớp API SSI từng dòng.** Đối chiếu
   từng dòng DB vs API SSI trên 9 mẫu: mọi ngày chung khớp 100% cả OHLC lẫn volume.
   Backfill lại sẽ ghi y hệt. Cơ chế loại trừ (`--emit-exclusions` /`--exclude-file`)
   là cách xử lý đúng, không phải giải pháp tạm.
2. **Bước nhảy xảy ra TẠI PHIÊN, không phải qua đêm.** Bar ngày t mở cửa đã ở mức
   +32% so với `close(t-1)`. Không có phiên giao dịch nào bị DB bỏ sót giữa hai dòng
   (kiểm 10/10 mẫu với cửa sổ ±10 ngày) — nên **không phải** lỗi bộ đếm ngày mở cửa.
3. **Cơ chế đã chốt (mục cuối tài liệu): quy tắc giá tham chiếu của UPCoM**, không
   phải sự kiện doanh nghiệp và cũng không phải dữ liệu hỏng. 214/228 mã trong phần dư
   là UPCOM, nơi giá tham chiếu lấy theo **bình quân phiên trước** chứ không phải giá
   đóng cửa — nên với mã khớp 2–6 lô, `close(t)/close(t-1)` vượt 25% là hợp lệ.
   **Tiền đề của chính bộ dò bước nhảy mới là thứ sai**, không phải dữ liệu.

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

## ĐÃ CHỐT — cơ chế (B) là quy tắc giá tham chiếu của UPCoM, KHÔNG phải sự kiện doanh nghiệp

Bổ sung 2026-08-15, sau khi đo `refPrice` qua `securitiesSummary` của SSI.

**Không cần lịch sự kiện doanh nghiệp.** API trả `priceChangePercentage`, suy ra
`refPrice(t) = close(t) / (1 + pct/100)`. Công thức được kiểm chứng độc lập trên một
phiên bình thường (HNB 2016-03-30: suy ra 15.470,77 so với `close(t-1)` = 15.468,67,
lệch 0,014%).

Kết quả 8 mã có dữ liệu: **8/8 đều có `refPrice(t) ≠ close(t-1)`** — tham chiếu bị
đặt lại. (KSV và IPA không xác định được: API trả `priceChangePercentage = null` cho
toàn chuỗi hai mã này.)

**Nhưng nguyên nhân KHÔNG phải sự kiện doanh nghiệp.** Sự kiện doanh nghiệp luôn kéo
giá tham chiếu **xuống**; ở đây `refPrice(t)` cao hơn `close(t-1)` 15–38% ở cả 8 mã.
Đo tiếp thì lộ ra cái đúng:

```
mã   phiên t-1: open      close     KL     refPrice(t)   ref / tb(open,close)
HNB  17.725,902  13.676,164    200      15.729,83          0,9982
PTH   3.972,275   3.001,274    200       3.487,51          0,9998
TUG   3.522,435   2.641,827    200       3.081,75          1,0001
VRG   2.053,465   1.555,655    200       1.804,45          1,0001
```

`refPrice(t)` **gần như đúng bằng giá bình quân của phiên trước**, và nằm trong khoảng
cao–thấp của phiên trước ở 7/8 mã.

Và mảnh ghép cuối: **8/8 mã này đều thuộc UPCOM**, còn trong toàn bộ phần dư 422 thì
**214/228 mã (94%) là UPCOM** (10 HOSE, 4 HNX).

UPCoM lấy giá tham chiếu là **bình quân gia quyền của phiên liền trước**, không phải giá
đóng cửa phiên trước như HOSE/HNX. Với mã chỉ khớp 2–6 lô, giá bình quân nằm rất xa giá
đóng cửa, nên biên độ ±15% của phiên sau được neo ở một mức khác hẳn — và
`close(t)/close(t-1)` vượt 25% **hoàn toàn hợp lệ, không cần bất kỳ sự kiện nào**.

### Hệ quả: 422 bar này KHÔNG bẩn

Tiền đề của cả bộ dò bước nhảy — *"biên độ tối đa ±15% nên một phiên không thể nhảy
25%"* — **sai với UPCoM**, vì biên độ ở đó không neo vào giá đóng cửa phiên trước. Dữ
liệu đúng; phép đo của chúng ta mới là thứ sai.

Vẫn nên loại các mã này khi đo chiến lược, nhưng **vì lý do khác**: chúng khớp 2–6 lô
một phiên, tức là không giao dịch được, chứ không phải vì dữ liệu hỏng.

Lưu ý về hệ số: tỉ lệ đo được (1,15–1,38) là giữa hai giá **đã back-adjust**, nên không
đọc nó như hệ số điều chỉnh thô của bất kỳ sự kiện nào.

## Còn mở

KSV và IPA (đều HNX) chưa xác định được vì API không trả `priceChangePercentage`. Hai
mã trên 228 — không đáng đào tiếp trừ khi có lý do khác.
