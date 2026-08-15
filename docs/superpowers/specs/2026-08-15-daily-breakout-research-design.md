# Thiết kế — Nghiên cứu chiến lược breakout khung ngày

Ngày: 2026-08-15. Base: `7f51482`, nhánh `feature/data-layer`.

## Bối cảnh — vì sao có tài liệu này

Chủ dự án quyết định **từ bỏ `sma_cross`** (2026-08-15). Lưu ý cách đóng vấn đề:
đây là quyết định, **không phải bằng chứng**. Không ai chứng minh được nó vô
dụng — chỉ có 4 cấu hình trên 3 mã được đo, cỡ mẫu quá nhỏ để phân biệt "không
có biên lợi thế" với "xui".

Ba điều rút ra bắt buộc mang sang, và chúng là lý do tài liệu này chia làm hai
dự án con:

1. **Phải có mốc so sánh.** Cổ phiếu VN tăng mạnh 2016–2026, nên một chiến lược
   long-only có lãi trong kỳ đó là đang đo *thị trường*, không đo *chiến lược*.
   "Có lãi" vô nghĩa; "vượt mua-và-giữ trên cùng mã, cùng kỳ" mới có nghĩa.
2. **Cỡ mẫu quyết định kết luận.** 14–52 lệnh không tách nổi tín hiệu khỏi nhiễu.
   Quét tham số trên cỡ mẫu đó chắc chắn tạo ra một con số đẹp và sai.
3. **Dữ liệu bẩn là thật và ảnh hưởng lớn.** 68 dòng `OHLC ≤ 0` trong đúng 3 mã,
   và một bar hỏng (khớp giá 0) tạo ra 84% khoản lỗ của một cấu hình.

## Phát hiện quyết định — mọi số đo cũ đều phải bỏ

`grep -rn "sellable|T+2|settle" trading/broker/ trading/backtest.py` → **không
một dòng nào**.

`PaperBroker` cho phép bán ngay bar vừa mua. Nhưng `real_orders.py:35-37` cưỡng
chế **T+2,5** trên đường thật: mua hôm nay thì ~2,5 phiên sau mới bán được.

Nghĩa là mọi backtest dự án này từng chạy đều giả định một điều luật không cho
phép. Trên bar 5 phút, backtest cho thoát lệnh sau vài phút trong khi thực tế bị
khoá ~2,5 phiên — **các phép đo `sma_cross` không đo một chiến lược tồi, chúng đo
một chiến lược không thể giao dịch được.**

Đây là lý do Dự án con 1 phải làm TRƯỚC, và tại sao không được phép đo chiến lược
mới bằng bộ máy hiện tại.

---

# Dự án con 1 — Chuẩn đo

Không phụ thuộc chiến lược nào. Làm xong là mọi chiến lược sau đều trả lời được
câu "nó có biên lợi thế không".

## 1a. Mô phỏng T+2,5 trong `PaperBroker`

`PaperBroker` ghi nhớ ngày mua của từng lô. Lệnh SELL chỉ được khớp trên phần đã
settle; phần chưa settle bị từ chối.

- Quy ước settle: mua ngày D → bán được từ ngày **D+3** (làm tròn lên từ T+2,5,
  khớp cách `real_orders.py` đọc `sellable_qty` từ SSI). Dùng **ngày giao dịch**
  (số bar ngày), không dùng ngày lịch.
- Nhiều lô mua ở nhiều ngày khác nhau: settle độc lập theo từng lô (FIFO).

**Kiểm chứng:** test mua ngày D, thử bán ngày D+1 và D+2 → bị từ chối; bán ngày
D+3 → khớp. Test hai lô mua cách nhau, lô cũ settle trước.

## 1b. Mốc mua-và-giữ

Cùng mã, cùng kỳ, cùng vốn ban đầu, cùng biểu phí. Mua ở bar đầu, giữ tới bar
cuối, tính cả phí mua và phí bán.

Báo cáo backtest phải hiện **hai cột cạnh nhau** và một cột chênh lệch. Chiến
lược có lãi nhưng thua mua-và-giữ = **thất bại**, phải hiện rõ như vậy chứ không
để người đọc tự suy.

**Kiểm chứng:** test trên chuỗi giá tăng đều — mua-và-giữ phải thắng mọi chiến
lược có giao dịch (vì phí). Test trên chuỗi giá giảm đều — mua-và-giữ phải lỗ.

## 1c. Lọc dữ liệu bẩn, có báo cáo

Loại bar có `open/high/low/close <= 0`. Báo cáo số dòng bị loại theo từng mã
trong kết quả — im lặng lọc là che mất vấn đề dữ liệu.

**Kiểm chứng:** test với chuỗi có chèn bar `open=0` → bar đó bị loại, số dòng loại
được báo cáo đúng, và không có lệnh nào khớp ở giá 0.

---

# Dự án con 2 — Chiến lược breakout khung ngày

CHỈ bắt đầu sau khi Dự án con 1 xong và xanh.

## Tín hiệu

- **Vào:** giá đóng cửa vượt **đỉnh cao nhất N phiên** gần nhất (không tính bar
  hiện tại).
- **Ra:** giá đóng cửa thủng **đáy thấp nhất M phiên** gần nhất (không tính bar
  hiện tại).
- **Tham số khởi điểm: N=20, M=10.** Chọn TRƯỚC khi đo và **không được tinh
  chỉnh** trong lần đo đầu tiên.

Kỷ luật chống overfit: quét tham số chỉ được phép **sau** khi biết có biên lợi
thế hay không, và nếu quét thì phải báo cáo toàn bộ lưới kết quả chứ không chỉ ô
tốt nhất.

## Tái sử dụng, không viết lại

`RiskManager`, `TrailingStopManager`, biểu phí VN trong `PaperBroker` dùng lại
nguyên. Chiến lược mới chỉ thay phần sinh tín hiệu.

## Phạm vi đo

Toàn bộ **1.551 mã** trong `bars_daily` (2.969.328 dòng, 2016-01-03 → 2026-08-13),
không phải 3 mã. Mục đích là đủ số lệnh để kết luận, KHÔNG phải để giao dịch cả
1.551 mã. Chọn rổ giao dịch thật là quyết định riêng, làm sau, dựa trên số liệu.

---

# Ngoài phạm vi — cố ý không làm

- **Không quét tham số** trong lần đo đầu.
- **Không chọn mã theo kết quả** (chọn xong mới đo là tự lừa mình).
- **Không đụng** `trading/engine/`, `trading/real_orders.py`,
  `scripts/confirm_real_order.py`, `config/config.yaml`. Đây thuần là nghiên cứu
  ngoại tuyến cho tới khi có số liệu.
- **Không bật `real_trading_enabled`** trong bất kỳ hoàn cảnh nào.

# Giả định — nêu rõ, chưa kiểm

- Giá trong `bars_daily` **chưa xác nhận đã điều chỉnh chia tách/cổ tức**. Không
  tìm thấy bước nhảy qua đêm bất thường ngoài các bar rác đã biết, nhưng đó không
  phải bằng chứng đủ mạnh. Nếu chưa điều chỉnh, breakout sẽ sinh tín hiệu giả tại
  các ngày chia tách. **Cần kiểm trước khi tin kết quả** — đây là câu hỏi mở, ghi
  lại chứ không giả vờ đã giải quyết.

  > **ĐÃ KIỂM — 2026-08-15, `scripts/check_price_adjustment.py`.** Câu trả lời là
  > **ĐÃ điều chỉnh, nhưng KHÔNG trọn vẹn.**
  >
  > Bằng chứng trực tiếp: **69,4% bar (2.012.464/2.897.911) có giá KHÔNG tròn bước
  > giá sàn**, 1.108/1.551 mã có >=50% bar giá phân số. Sàn VN yết theo bước
  > 10/50/100 đồng, nên `close = 12657.375` (VCB 2016-01-04) chỉ có thể sinh ra từ
  > hệ số back-adjust. Giá thô sẽ tròn.
  >
  > Phần chưa trọn vẹn: **51 bước nhảy tỉ lệ chia tách trên 49 mã** vẫn còn nguyên
  > sau khi đã loại bar không khớp lệnh (vd ACC 2022-01-05: 37.156 -> 18.602, khối
  > lượng 510k và 203k hai bên — chia tách thật, chưa điều chỉnh).
  >
  > **ĐÍNH CHÍNH lần đo đầu (bản báo cáo nói "CHƯA điều chỉnh", 233 sự kiện/129
  > mã) — SAI.** Phần lớn số đó là cổ phiếu chết có `volume = 0` một hoặc cả hai
  > bên (SD8: 1.200 đứng im volume 0 suốt 5 phiên rồi bước xuống 800). Bar volume 0
  > là **giá tham chiếu treo, không phải giá thị trường** — bước nhảy giữa hai giá
  > như vậy không chứng minh được gì. Bộ lọc volume cũ không bắt được vì nó so với
  > volume TRUNG VỊ của chính mã đó, mà mã chết có trung vị cũng bằng 0 -> tỉ lệ
  > `None` -> lọt qua như "volume bình thường". Sửa bằng cách bắt buộc CÓ khớp lệnh
  > cả hai bên: 17.297 sự kiện bị phân loại lại, bằng chứng còn 233 -> 51.
  >
  > **Cách dùng:** đừng vứt cả bảng — loại đúng các mã hỏng.
  > `--emit-exclusions FILE` ghi ra 245 mã không đáng tin (49 chia tách chưa điều
  > chỉnh + 209 mã có >=5% bar rác), `measure_strategy.py --exclude-file FILE`
  > loại chúng trước khi đo.
  >
  > Còn mở, ghi lại chứ không giả vờ đã giải quyết: **837 bước nhảy >25% trên 367
  > mã** không khớp tỉ lệ chia tách nào và CÓ khớp lệnh hai bên. Nghi dữ liệu
  > backfill hỏng, chưa truy được nguồn.
- Quy ước settle D+3 là cách làm tròn thận trọng của T+2,5. Nếu SSI thực tế cho
  bán sớm hơn, phép đo sẽ hơi bi quan — chấp nhận được, vì sai theo hướng an toàn.

# Tiêu chí thành công của cả hai dự án con

Sau khi chạy, phải trả lời được ba câu bằng số, không bằng cảm nhận:

1. Breakout N=20/M=10 trên diện rộng, **sau khi trừ phí và tôn trọng T+2,5**, có
   vượt mua-và-giữ không?
2. Tổng số lệnh là bao nhiêu — đủ để kết luận, hay lại rơi vào bẫy cỡ mẫu nhỏ?
3. Bao nhiêu dòng dữ liệu bị loại vì bẩn, và có mã nào bẩn tới mức kết quả của nó
   không đáng tin không?

Nếu câu 1 là "không", đó là kết quả **hợp lệ và có giá trị** — nó đóng một hướng
bằng số liệu thay vì bằng cảm giác, điều mà `sma_cross` đã không làm được.
