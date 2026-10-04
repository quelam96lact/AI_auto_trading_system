# Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow

> **Phạm vi và cảnh báo:** Tài liệu này là khung nghiên cứu và quản trị rủi ro để xây dựng backtest cho BTCUSDT perpetual trên khung 1H. Tài liệu không cung cấp tín hiệu hiện tại, không dự báo giá, không phải khuyến nghị mua hoặc bán và không cam kết lợi nhuận. Giao dịch futures có thể làm mất toàn bộ hoặc vượt số vốn ký quỹ tùy cơ chế sản phẩm, đòn bẩy, thanh lý và quy định của sàn.

## 1. Kết luận điều hành

Bốn chiến lược trong tài liệu nên được xem là **các module có điều kiện**, không phải bốn nguồn tín hiệu để cộng điểm tùy ý. Module breakout Donchian phù hợp với giai đoạn giá thoát vùng tích lũy kèm mở rộng biến động. Module mean reversion Bollinger phù hợp với thị trường đi ngang có biên độ tương đối ổn định. Module Funding–OI–Liquidation + EMA Pullback tìm một cú reset đòn bẩy trước khi giao dịch tiếp diễn theo xu hướng. Module VWAP + Volume Profile + Order Flow dùng vị trí giá so với giá trị giao dịch của ngày trước để tìm pullback thuận xu hướng.

Không có cơ sở để mặc định một module luôn có lợi thế. ATR chỉ đo cường độ biến động, không xác định hướng; open interest chỉ đo số hợp đồng còn mở, không cho biết bên Long hay Short; funding là khoản thanh toán giữa các bên của hợp đồng vĩnh cửu, không phải tín hiệu đảo chiều; còn delta từ giao dịch khớp chủ động là **proxy** phụ thuộc quy ước maker flag và venue. Vì vậy, mọi kết luận phải dựa trên kết quả net-of-cost của kiểm định ngoài mẫu, không dựa trên một đường vốn đẹp trong mẫu.

Khuyến nghị nghiên cứu là xây một **bộ chọn chế độ thị trường** trước khi phát tín hiệu. Chỉ bật module range mean reversion khi điều kiện range đạt. Chỉ bật các module trend-following khi EMA, độ dốc, vị trí giá và Order Flow cùng hướng. Breakout và pullback có thể được kiểm định độc lập hoặc làm trigger bổ sung cho chiến lược EMA hiện có, nhưng không được đếm cùng một chuyển động là hai giao dịch nếu đang dùng chung ngân sách rủi ro.

## 2. Nguyên tắc chung và quy ước dữ liệu

### 2.1. Thời điểm, venue và chống look-ahead

Tất cả dữ liệu phải gắn với **UTC**, một hợp đồng BTCUSDT perpetual cụ thể và một venue cụ thể. Nến 1H chỉ được dùng sau khi đóng hoàn toàn. Một tín hiệu được tính tại giá đóng của bar `t`; lệnh sớm nhất được đặt từ bar `t+1`. Không dùng high, low, volume, funding, open interest, liquidation hoặc order-flow của phần nến chưa đóng.

Donchian, Bollinger, ATR, EMA, ADX, VWAP và Volume Profile đều phải được tính bằng dữ liệu sẵn có tại thời điểm quyết định. Với Donchian breakout, 20 nến dùng để tạo `Upper20` và `Lower20` là **20 nến trước** nến tín hiệu; không đưa chính nến breakout vào biên. Với Volume Profile, chỉ dùng toàn bộ dữ liệu intraday của ngày UTC đã hoàn tất trước đó. Với rolling percentile hoặc median, cửa sổ chỉ chứa các quan sát quá khứ.

Khi dữ liệu OHLC chỉ cho biết một nến chạm cả entry và stop hoặc cả entry và take-profit mà không biết thứ tự, dùng giả định bảo thủ: stop xảy ra trước. Dữ liệu missing, duplicate, timestamp lệch, feed bị ngắt, maintenance và aggregate-trade/order-book gap phải được ghi log và loại khỏi bar liên quan; không nội suy delta, OFI hoặc depth bằng số 0 mà không gắn cờ chất lượng dữ liệu.

### 2.2. Order Flow và giới hạn diễn giải

Trên Binance, aggregate trade có trường `m`: `m=true` nghĩa là buyer là market maker. Theo quy ước đó, có thể tính:

```text
taker_buy_volume  = tổng q khi m = false
taker_sell_volume = tổng q khi m = true
delta             = taker_buy_volume - taker_sell_volume
buy_ratio         = taker_buy_volume / (taker_buy_volume + taker_sell_volume)
```

Quy ước phải được kiểm tra lại nếu đổi venue hoặc nguồn dữ liệu. Delta của aggregate trades là trade-delta proxy, không phải OFI L2 đầy đủ. OFI cần dữ liệu thay đổi tại bid/ask và phụ thuộc market depth; nghiên cứu microstructure không chứng minh rằng quan hệ trên một thị trường khác sẽ chuyển nguyên vẹn sang BTCUSDT 1H [1] [2]. Binance cũng lưu ý RPI orders có thể được gộp vào khối lượng nhưng không có tag riêng trong một số dữ liệu, vì vậy cần ghi rõ cách xử lý khi tái lập kết quả [3].

Local order book và depth chủ yếu dùng để kiểm tra spread, khả năng khớp, market impact và mô hình hóa slippage. Không dùng snapshot hiện tại làm tín hiệu lịch sử nếu không có snapshot đã lưu cùng timestamp. Với backtest không có L2, phải gọi đúng tên là `trade-delta` hoặc `CVD proxy`, không gọi là OFI.

### 2.3. Chi phí và mô phỏng khớp lệnh

PnL phải là PnL sau phí maker/taker, spread, slippage, funding và partial fill. Stop không bảo đảm khớp đúng giá trong gap, nến biến động hoặc order book mỏng. Với stop-entry, cần mô phỏng trường hợp nến kế tiếp mở vượt trigger, giá chạm trigger rồi trượt, hoặc giá chạy quá xa trước khi khớp. Với next-open, cần mô phỏng bất lợi khi `Open_{t+1}` lệch xa close tín hiệu.

Funding mặc định thường được nhắc đến theo chu kỳ 8 giờ, nhưng interval và thông số cụ thể phụ thuộc contract specification và có thể thay đổi [4]. Backtest phải dùng timestamp settlement thực tế của hợp đồng. Binance cho biết liquidation được kích hoạt theo Mark Price, không chỉ Last Price [5]. Vì thế, stop, liquidation buffer và giá trị rủi ro phải được mô phỏng với Mark Price khi dữ liệu cho phép.

### 2.4. Quản trị vốn chung

Rủi ro danh nghĩa khởi đầu cho mỗi giao dịch là **0,25%–0,50% equity**. Với entry `E`, stop `S`, phí và slippage ước tính trên mỗi đơn vị là `C`, có thể dùng:

```text
risk_budget = equity * risk_fraction
quantity    = risk_budget / (abs(E - S) + C)
```

Sau đó áp giới hạn notional, leverage, margin ratio, số vị thế đồng thời và giới hạn lỗ ngày/tuần. Không dùng stop gần liquidation. Giá thanh lý phải được kiểm tra theo Mark Price, và nên yêu cầu khoảng cách từ liquidation đến stop lớn hơn một buffer cố định, chẳng hạn ít nhất 2R trong biến thể nghiên cứu Funding–OI–Liquidation. Đây là giả định kiểm định, không phải mức phù hợp cho mọi tài khoản.

Chỉ một vị thế BTCUSDT cho mỗi module hoặc cho toàn bộ danh mục, tùy thiết kế backtest đã công bố trước. Không pyramiding trong phiên bản đầu. Nếu breakout, Trend-Pullback EMA và VWAP pullback cùng hướng trong cùng vùng thời gian, chúng phải chia sẻ một trần rủi ro; không mở ba lệnh rồi gọi là ba tín hiệu độc lập.

## 3. Bảng so sánh nhanh

| Chiến lược | Giả thuyết chính | Trạng thái phù hợp | Trigger Long | Trigger Short | Rủi ro đặc thù | Không nên dùng khi |
|---|---|---|---|---|---|---|
| **A. Donchian Breakout + ATR Expansion** | Giá thoát khỏi biên 20 nến với biến động và delta xác nhận tăng | Breakout khỏi tích lũy, trend mới hình thành | Close > Upper20, ATR mở rộng, CLV cao, delta dương | Close < Lower20, ATR mở rộng, CLV thấp, delta âm | False breakout, đuổi giá, slippage trong shock | ATR quá cao, nến đã mở rộng, spread/depth xấu, funding cực đoan |
| **B. Bollinger Mean Reversion** | Rejection tại biên trong regime range quay về đường giữa | Đi ngang, ADX thấp, bandwidth trung vị | Chạm/xuyên Lower rồi đóng lại bên trong và nến xanh | Chạm/xuyên Upper rồi đóng lại bên trong và nến đỏ | Bắt dao rơi khi trend tiếp diễn, band walk | Đóng ngoài band, squeeze, bandwidth quá rộng hoặc trend rõ |
| **C. Funding–OI–Liquidation + EMA Pullback** | Deleveraging/flush làm sạch vị thế rồi xu hướng tái chiếm EMA | Trend có cú reset forced-close | Liquidation SELL lớn, OI giảm, đóng lại trên EMA20, delta dương | Liquidation BUY lớn, OI giảm, đóng lại dưới EMA20, delta âm | ForceOrder không đầy đủ, flush là continuation, OI không có hướng | Thiếu dữ liệu liquidation, funding chưa settle, giá đã chạy xa EMA |
| **D. VWAP + Volume Profile + OF** | Giá thuận xu hướng hồi về vùng giá trị rồi tiếp diễn với taker flow xác nhận | Trend có acceptance ngoài VAH/VAL | Close trên EMA/VWAP/VAH, pullback chạm VWAP/VAH, delta dương | Close dưới EMA/VWAP/VAL, pullback chạm VWAP/VAL, delta âm | Profile phụ thuộc tham số, delta proxy, cản POC/HVN | Profile chưa hoàn tất, giá trong value area, mục tiêu bị cản |

Các chiến lược B, C và D không nên được gộp bằng cách cộng điểm chủ quan. B là module ngược xu hướng có điều kiện. C và D là module thuận xu hướng. Khi regime classifier không chắc chắn, phương án an toàn trong backtest là **no-trade**, không phải chọn tất cả.

## 4. Chiến lược A — Donchian Breakout và Volatility Expansion

### 4.1. Logic

Chiến lược dùng kênh Donchian 20 nến để nhận diện giá phá đỉnh hoặc đáy gần đây. ATR14 đo biến động, còn median ATR14 của 50 nến trước tạo baseline để nhận diện expansion. ATR không xác định hướng; hướng được kiểm tra bằng vị trí đóng cửa trong nến, trạng thái EMA và Order Flow. Tư duy trend-following dài hạn có thể cung cấp bối cảnh về việc giá có xu hướng tiếp diễn, nhưng nghiên cứu futures nhiều thị trường và horizon dài không phải bằng chứng riêng cho BTCUSDT 1H [6] [7].

### 4.2. Biến và điều kiện Long/Short

| Thành phần | Long | Short |
|---|---|---|
| Kênh | `close_t > Upper20_t`, với Upper20 là highest high của 20 nến trước | `close_t < Lower20_t`, với Lower20 là lowest low của 20 nến trước |
| Expansion | `ATR14_t / median(ATR14, 50 nến trước) >= 1,20` và `ATR14_t > ATR14_{t-1}` | Giống Long |
| Biên độ | `high_t - low_t >= 1,0 * ATR14_t` | Giống Long |
| Close-location-value | `(close-low)/(high-low) >= 0,65` | `(close-low)/(high-low) <= 0,35` |
| EMA trend-complement, nếu bật | `EMA50 > EMA200` | `EMA50 < EMA200` |
| Order Flow kết hợp | Delta breakout dương và `taker-buy quote / total quote >= 0,55` | Delta breakout âm và tỷ lệ taker-buy quote `<= 0,45` |

Nếu `high = low`, CLV không được xem là hợp lệ. Bản standalone phải được chạy riêng với EMA filter tắt. Bản kết hợp khuyến nghị chỉ giao dịch cùng hướng EMA50/EMA200 và yêu cầu delta/taker ratio xác nhận. Không coi rising OI, funding, volume hoặc delta đơn lẻ là bằng chứng chắc chắn.

### 4.3. Entry, stop và thoát

Sau khi nến tín hiệu đóng, Long đặt buy-stop tại:

```text
trigger_long = Upper20 + 0,05 * ATR14
```

Short đặt sell-stop tại:

```text
trigger_short = Lower20 - 0,05 * ATR14
```

Lệnh hết hạn sau hai nến 1H. Nếu giá chạy quá `0,50 * ATR14` khỏi trigger trước khi khớp, hủy để tránh đuổi giá. Backtest phải so sánh ít nhất hai biến thể: vào tại `next-open` và stop-entry. Hai biến thể phải được báo cáo riêng, vì chênh lệch execution có thể lớn trong nến breakout.

Với Long, stop ban đầu nằm dưới mức thấp hơn giữa `breakout low - 0,25*ATR14` và `entry - 1,5*ATR14`. Với Short, stop nằm trên mức cao hơn giữa `breakout high + 0,25*ATR14` và `entry + 1,5*ATR14`. Công thức này tạo khoảng cách tối thiểu khoảng 1,5R theo ATR; cần viết rõ định nghĩa R trong code để tránh nhầm giữa R và ATR.

Chốt 50% tại `+1,5R`. Phần còn lại dùng chandelier trail `2,5*ATR14` tính từ đỉnh kể từ entry đối với Long hoặc từ đáy đối với Short. Có thể thoát thêm khi nến đóng xuyên EMA50 hoặc Donchian đối diện. Fixed target `2R` là một biến thể so sánh cố định, không được chọn sau khi biết kết quả tốt nhất.

### 4.4. Bộ lọc và trường hợp không dùng

Bỏ qua breakout nếu ATR ratio từ 50 nến trước đạt hoặc vượt `2,50`, vì có thể là shock hoặc liquidation cascade. Bỏ qua nếu range nến lớn hơn `2,0*ATR14`, hoặc close đã cách trigger quá xa. Các ngưỡng này là tham số nhạy cảm, không phải quy luật phổ quát.

Không vào khi spread, depth khả dụng hoặc estimated slippage vượt ngân sách. Không vào khi funding dự kiến bất lợi ở mức cực đoan hoặc interval vừa thay đổi. Không vào trong maintenance, đứt feed, nến thiếu/duplicate hoặc aggregate trade/order book không liên tục. Không mở khi margin ratio hoặc leverage tiến gần giới hạn nội bộ.

### 4.5. Khi phù hợp và khi thất bại

Module A phù hợp để kiểm định trong giai đoạn bandwidth thoát khỏi vùng tích lũy, volume và taker flow tăng, nhưng giá chưa tạo một nến shock quá lớn. Module thường dễ thất bại trong thị trường whipsaw quanh Upper20/Lower20, khi thanh khoản bị quét hai chiều hoặc khi một tin tức tạo gap vượt trigger rồi đảo chiều. ATR expansion chỉ nói rằng biên độ tăng, không bảo đảm breakout là thật.

## 5. Chiến lược B — Bollinger Mean Reversion trong vùng giá

### 5.1. Logic và regime bắt buộc

Bollinger Bands mô tả giá tương đối cao hoặc thấp quanh trung bình; việc chạm band không tự nó là tín hiệu, vì giá có thể đi dọc band trong xu hướng [8] [9]. Do đó, chiến lược chỉ được bật trong range regime:

```text
M_t       = SMA(close, 20)
SD_t      = độ lệch chuẩn mẫu 20
Upper_t   = M_t + 2*SD_t
Lower_t   = M_t - 2*SD_t
%B_t      = (close_t - Lower_t)/(Upper_t - Lower_t)
```

Điều kiện range bắt buộc là `ADX14 < 20`, độ thay đổi EMA50 trong ba nến nhỏ hơn `0,50*ATR14`, khoảng cách EMA50 đến EMA200 không quá `0,75*ATR14`, và BandWidth nằm trong phân vị 20–80 của 240 bar gần nhất. Giá trị ADX dưới 20 và các phân vị chỉ là điểm xuất phát để kiểm định, không phải tiêu chuẩn phổ quát.

### 5.2. Điều kiện Long và Short

| Thành phần | Long | Short |
|---|---|---|
| Rejection | `Low_t <= Lower_t` và `Close_t > Lower_t` | `High_t >= Upper_t` và `Close_t < Upper_t` |
| Màu nến | `Close_t > Open_t` | `Close_t < Open_t` |
| Vị trí tương đối | `%B_t <= 0,25` | `%B_t >= 0,75` |
| Entry | `Open_{t+1}`, nếu không lệch bất lợi quá `0,25*ATR_t` so với `Close_t` | Đối xứng |
| Mục tiêu | `min(M_t, Entry + 1,25R)` | `max(M_t, Entry - 1,25R)` |

Không mua chỉ vì giá chạm Lower và không bán chỉ vì giá chạm Upper. Nến phải đóng trở lại bên trong band và thể hiện rejection. Nếu nến tín hiệu đóng hẳn ngoài band, bỏ qua vì đó có thể là continuation hoặc band walk.

### 5.3. Stop, time stop và Order Flow

Stop Long là `Low_t - 0,25*ATR_t`; stop Short là `High_t + 0,25*ATR_t`. Bỏ trade nếu `R < 0,60*ATR_t` hoặc `R > 2,00*ATR_t`. Chỉ nhận lệnh nếu khoảng cách từ entry tới đường giữa ít nhất `0,80R`. Nếu sau 12 nến chưa chạm stop hoặc take-profit, đóng theo giá thị trường.

Order Flow là bộ lọc xác nhận. Với dữ liệu trade/L2 5 phút hoặc 15 phút trong bar t, Long yêu cầu OFI tổng dương và `OFI_z >= +0,50`; Short yêu cầu `OFI_z <= -0,50`. Nếu chỉ có trade prints, dùng signed-volume delta hoặc CVD nhưng phải chạy thành biến thể riêng. Không được suy diễn OFI từ màu nến hoặc OHLCV rồi gọi đó là L2 OFI.

### 5.4. Kết hợp với Trend-Pullback EMA + Order Flow

Bộ chọn chế độ phải chạy trước. Nếu EMA50 > EMA200, slope EMA50 dương và ADX >= 20, tắt module mean reversion, chuyển quyền ưu tiên cho Trend-Pullback EMA với OFI cùng chiều. Nếu điều kiện trend đảo ngược, xử lý đối xứng. Chỉ bật module B khi điều kiện range đạt; không cộng điểm hai module mâu thuẫn rồi vào lệnh.

### 5.5. Bộ lọc và trường hợp không dùng

Không vào khi BandWidth dưới phân vị 20 vì squeeze có thể chuyển thành breakout, hoặc trên phân vị 80 vì thị trường đang ở jump regime. Không vào khi spread/market impact ước tính vượt `0,10%` giá hoặc thanh khoản không đủ. Không vào trong cửa sổ khoảng `±15 phút` quanh funding dự kiến nếu backtest chưa mô phỏng chính xác; nếu giữ qua settlement, trừ funding thực tế.

Không vào khi funding dự kiến cực đoan, khi có sự kiện lớn hoặc khi OFI stale. Không thay dữ liệu OFI thiếu bằng 0 mà không gắn cờ. Với dữ liệu thiếu liquidation không liên quan trực tiếp module B, không cố gắng bổ sung bằng proxy không được định nghĩa.

### 5.6. Khi phù hợp và khi thất bại

Module B phù hợp khi ADX thấp, EMA phẳng, BandWidth trung vị và các lần xuyên band bị từ chối nhanh. Module dễ thất bại khi thị trường chuyển từ range sang trend, khi tin tức làm nến đóng ngoài band, hoặc khi một cú liquidation tạo ra range lớn hơn giới hạn. Nghiên cứu Bitcoin về mean reversion/mean-aversion có kết quả không đồng nhất và thường dùng đặc tả, giai đoạn hoặc tần suất khác 1H; không suy diễn kết quả đó thành lợi thế hiện tại [10] [11].

## 6. Chiến lược C — Funding–OI–Liquidation + EMA Pullback + Order Flow

### 6.1. Logic

Module C tìm một lần deleveraging có thể quan sát được, sau đó đợi giá tái chiếm EMA và flow xác nhận. Funding được dùng để nhận diện mức độ crowded và tính chi phí. OI là số hợp đồng còn mở; OI không tự phân biệt Long và Short [12]. Liquidation là điều kiện bối cảnh reset đòn bẩy, không phải bằng chứng chắc chắn rằng giá phải đảo chiều.

### 6.2. Điều kiện Long và Short

| Thành phần | Long | Short |
|---|---|---|
| Trend | `close > EMA50`, `EMA20 > EMA50`, `EMA50_t > EMA50_{t-3}` | Các điều kiện đảo ngược |
| Funding | zFunding `< +1,0`; ưu tiên `<= -0,5` hoặc funding `<= 0` | zFunding `> -1,0`; ưu tiên `>= +0,5` hoặc funding `>= 0` |
| Liquidation | Tổng notional liquidation SELL trong bar >= percentile 90 của 30 ngày | Tổng notional liquidation BUY trong bar >= percentile 90 của 30 ngày |
| OI | `OI_t/OI_{t-3} - 1 <= -0,015` | Giống Long |
| Nến xác nhận | Đóng trên EMA20 và midpoint của nến flush | Đóng dưới EMA20 và midpoint của nến squeeze |
| Order Flow | Delta1H/total volume > 0, CVD hiện tại > CVD 3 nến trước | Delta1H/total volume < 0, CVD hiện tại < CVD 3 nến trước |

Funding phải là funding đã settle gần nhất và z-score trên 90 ngày các lần settle của cùng hợp đồng. Nếu lịch settlement thay đổi, dùng timestamp thực tế. Không dùng predicted funding tương lai như funding đã thực trả.

ForceOrder của Binance là snapshot giới hạn, có thể tối đa một liquidation order mỗi symbol trong mỗi 1000 ms. Nó không phải toàn bộ liquidation volume của thị trường [13] [14]. Nếu không có dữ liệu liquidation đầy đủ để tính percentile, phải loại trade hoặc gắn nhãn một biến thể proxy riêng. Không thay bằng một giá trị hiện tại tùy ý.

### 6.3. Entry, stop và take-profit

Sau khi trend, funding, liquidation–OI và flow cùng đúng tại close t, Long đặt buy-stop tại high của nến xác nhận cộng `0,05*ATR14`; lệnh hết hạn sau một bar. Short đặt sell-stop tại low nến xác nhận trừ `0,05*ATR14`; cũng hết hạn sau một bar.

Stop Long nằm dưới đáy pullback/flush thấp nhất trừ `0,20*ATR14`, với khoảng cách tối thiểu `1,20*ATR14` từ entry. Stop Short đối xứng. Chốt 50% tại `1R`; phần còn lại chốt tại `2R` hoặc thoát khi nến đóng ngược EMA20, theo một quy tắc cố định của từng biến thể. Sau TP1, dời stop phần còn lại về entry cộng/trừ chi phí và funding dự kiến. Không dời stop để nới rủi ro.

### 6.4. Bộ lọc và trường hợp không dùng

Chỉ giao dịch khi có ít nhất 30 ngày lịch sử để tính percentile liquidation và 90 ngày để tính funding z-score. Bỏ qua khi dữ liệu liquidation, OI, funding hoặc trade bị thiếu. Kiểm tra spread, depth và size sao cho market impact không vượt ngưỡng đã backtest. Tránh funding settlement nếu timestamp payment chưa được mô phỏng.

Không vào khi giá đã chạy quá `1,0*ATR14` khỏi EMA20 tại lúc kích hoạt, hoặc nến xác nhận có range trên `3*ATR14`. Không dùng dữ liệu liquidation của sàn A với OI của sàn B nếu không có phép tổng hợp và weighting được định nghĩa trước. Bộ lọc 4H cùng chiều là một biến thể riêng, không trộn kết quả với bản không có bộ lọc.

### 6.5. Khi phù hợp và khi thất bại

Module C phù hợp khi một flush lớn đi cùng OI giảm, giá nhanh chóng tái chiếm EMA và delta đổi hướng. Module thất bại khi liquidation snapshot bỏ sót phần lớn sự kiện, khi OI giảm do nhiều cơ chế khác nhau, hoặc khi flush chỉ là giai đoạn đầu của xu hướng tiếp diễn. Một funding âm không tự động là Long signal, cũng như funding dương không tự động là Short signal [4] [12].

## 7. Chiến lược D — VWAP + Volume Profile + Trend Pullback + Order Flow

### 7.1. Logic và chỉ báo

Module D dùng EMA để xác định hướng, VWAP phiên UTC để xác định giá trung bình theo volume, và Volume Profile của ngày UTC hoàn tất trước đó để xác định vùng giá trị. VWAP là chỉ báo trễ và phụ thuộc anchor [15]. Volume Profile là mô tả phản ứng đã xảy ra; POC, VAH và VAL phụ thuộc khoảng thời gian, lower-timeframe data và tỷ lệ value area [16]. Do đó, các mức này là bối cảnh và vùng kiểm tra, không phải dự báo chắc chắn.

Thiết lập baseline:

```text
EMA20, EMA50, EMA200, ATR14 trên 1H
VWAP: reset lúc 00:00 UTC, giá mặc định HLC3
Volume Profile: ngày UTC trước, 48 rows, Value Area 70%
```

### 7.2. Điều kiện Long và Short

| Thành phần | Long | Short |
|---|---|---|
| Regime | `close > EMA200`, `EMA20 > EMA50`, EMA20 hiện tại > EMA20 ba nến trước, close > VWAP và close > VAH | Đảo ngược: close < EMA200, EMA20 < EMA50, slope âm, close < VWAP và close < VAL |
| Vùng pullback | Trong tối đa 3 nến sau regime, low chạm VWAP hoặc VAH trong sai số `0,25*ATR14` | High chạm VWAP hoặc VAL trong sai số `0,25*ATR14` |
| Xác nhận | Đóng trên mức được chạm, nến xanh, close > high nến trước | Đóng dưới mức được chạm, nến đỏ, close < low nến trước |
| Order Flow | Delta1H > 0, buy-ratio >= 0,55, và abs(delta) >= median abs(delta) của 20 nến trước | Delta1H < 0, buy-ratio <= 0,45, cùng điều kiện magnitude |
| Entry | Buy-stop tại high nến xác nhận + `0,05*ATR14`, hiệu lực 2 nến | Sell-stop tại low nến xác nhận - `0,05*ATR14`, hiệu lực 2 nến |

Nếu cả VWAP và VAH hoặc cả VWAP và VAL được chạm, chọn mức gần hơn với close nến xác nhận. Không trade nếu close nằm trong vùng VAL–VAH của profile ngày trước, vì khi đó giá chưa chứng minh acceptance ngoài vùng giá trị.

### 7.3. Stop, mục tiêu và bộ lọc

Stop Long là `min(low nến xác nhận, mức pullback - 0,25*ATR14)`. Stop Short là `max(high nến xác nhận, mức pullback + 0,25*ATR14)`. Bỏ trade nếu khoảng cách stop đến entry nhỏ hơn `0,20*ATR14` hoặc lớn hơn `1,50*ATR14`. Chốt 50% tại `1R`; chỉ sau khi TP1 khớp mới dời stop phần còn lại về entry cộng/trừ chi phí. Chốt phần còn lại tại `2R` hoặc khi nến đóng ngược EMA20. Nếu sau 12 nến chưa đạt 1R, đóng toàn bộ.

Không vào nếu profile/VWAP chưa hoàn tất hoặc 1H đầu UTC có dữ liệu trade chưa đầy đủ. Bỏ qua khi spread, slippage hoặc delay làm chi phí vào/ra vượt `0,15R`. Không vào nếu entry quá gần Profile High, Profile Low hoặc HVN đối diện khiến còn chưa đủ 1R tới vùng cản. Nếu thuật toán HVN/LVN chưa được định nghĩa tái lập, để filter này tắt trong baseline và kiểm thử riêng.

Có thể kiểm định thêm biến thể bỏ trade nếu POC/HVN của profile trước nằm giữa entry và 2R. Không được tự ý dùng HVN hoặc LVN trong một phiên bản mà cách phân loại vùng chưa được định nghĩa thống nhất.

### 7.4. Khi phù hợp và khi thất bại

Module D phù hợp khi giá đã acceptance ngoài VAH/VAL, EMA đồng hướng, pullback giữ được VWAP hoặc edge của value area và taker flow tái xác nhận. Module dễ thất bại khi anchor UTC không đại diện cho nhịp thanh khoản, khi profile được xây từ lower-timeframe thiếu dữ liệu, khi giá quay lại vùng value hoặc khi delta chỉ phản ánh một venue. Các nghiên cứu OFI/trade-flow trên thị trường khác cung cấp bối cảnh microstructure, không phải bằng chứng riêng cho BTCUSDT 1H [1] [2] [17].

## 8. Ma trận chọn chiến lược theo trạng thái thị trường

Bộ chọn regime nên được xác định bằng dữ liệu tại thời điểm t và giữ nguyên trong phiên bản backtest. Ma trận dưới đây là quy tắc ưu tiên nghiên cứu, không phải lời hứa rằng chiến lược được chọn sẽ có lợi nhuận.

| Dấu hiệu regime tại bar đóng | Module ưu tiên kiểm định | Module có thể chạy phụ | Module nên tắt | Lý do |
|---|---|---|---|---|
| ADX < 20, EMA50 phẳng, BandWidth phân vị 20–80, giá quay lại trong band | B. Bollinger MR | Price-only ablation | C và D nếu trend filter không đạt | Range rejection có điều kiện, tránh bắt breakout |
| Giá đóng trên Upper20/ dưới Lower20, ATR ratio 1,20–2,50, range không vượt 2 ATR, CLV và delta cùng hướng | A. Donchian Breakout | D nếu đã có acceptance ngoài VAH/VAL | B | Expansion cần tiếp diễn, không mean-revert ngay |
| Funding không quá crowded, liquidation percentile cao, OI giảm >=1,5% trong 3 giờ, giá tái chiếm EMA | C. Funding–OI–Liquidation | D nếu value context đồng hướng | B | Deleveraging có xác nhận, nhưng cần dữ liệu liquidation đầy đủ |
| EMA20/50/200 đồng hướng, close ngoài VWAP và VAH/VAL, profile ngày trước hoàn tất | D. VWAP + VP + OF | A nếu đồng thời có breakout hợp lệ | B | Pullback về vùng giá trị có flow xác nhận |
| ATR ratio >=2,50, range >2 ATR, gap lớn, spread/depth xấu, funding cực đoan | No-trade | Không | Tất cả | Shock/liquidation và execution risk cao |
| Trend filter và range filter mâu thuẫn, dữ liệu OFI/OI stale | No-trade hoặc price-only research label | Chỉ ablation đã định trước | Module cần dữ liệu thiếu | Không bù dữ liệu bằng giả định tùy ý |

Trong thực tế, nên lưu nhãn `range-MR`, `breakout`, `deleveraging-pullback` hoặc `value-pullback` cho từng giao dịch. Không dùng một trade để đánh giá đồng thời nhiều module. Nếu một tín hiệu breakout xuất hiện khi đang có Trend-Pullback EMA cùng hướng, chỉ chọn một trigger hoặc áp một trần rủi ro tổng; không cộng hai mức rủi ro.

## 9. Kế hoạch backtest có thể tái lập

### 9.1. Chuẩn hóa dữ liệu

Bước đầu là cố định venue, hợp đồng, timezone UTC, phí, funding schedule, tick size, lot size, maker/taker fee và quy tắc Mark Price. Lưu các bảng dữ liệu riêng cho OHLCV 1H, aggregate trades, funding đã settle, OI, liquidation events và order book/depth có timestamp. Binance cung cấp REST/WebSocket cho dữ liệu market futures, nhưng endpoint và giới hạn dữ liệu phải được kiểm tra theo phiên bản API đang dùng [3] [18].

Mỗi bar phải có cờ chất lượng dữ liệu. Cờ này ghi missingness, duplicate, timestamp lệch, feed reconnect, maintenance, stale depth và độ trễ. Không dùng dữ liệu hiện tại để hồi lấp dữ liệu lịch sử. Nếu dữ liệu liquidation chỉ là forceOrder snapshot, ghi rõ coverage và không diễn giải thành tổng liquidation thị trường [13].

### 9.2. Engine sự kiện và mô phỏng lệnh

Engine nên xử lý theo thứ tự:

1. Đóng bar `t` và tạo chỉ báo chỉ từ dữ liệu trước và tại close `t`.
2. Kiểm tra filter dữ liệu, funding window, spread/depth và regime.
3. Đặt next-open hoặc stop-entry từ bar kế tiếp theo đúng phiên bản.
4. Mô phỏng gap khi mở vượt trigger, hết hạn lệnh, partial fill và slippage.
5. Sau khi khớp, mô phỏng stop, TP, chandelier, EMA exit và time stop theo Mark Price nếu được yêu cầu.
6. Trừ phí, funding đúng timestamp settlement và chi phí execution vào equity.
7. Ghi entry reason, module, version, risk budget, fill assumption và trạng thái dữ liệu.

Với A, so sánh riêng `next-open` và stop-entry. Với B, so sánh entry next-open và quy tắc bỏ lệnh khi gap bất lợi trên `0,25*ATR`. Với C, không vào ngay trong liquidation candle; cần nến xác nhận. Với D, profile ngày trước phải hoàn tất trước khi tạo tín hiệu.

### 9.3. Thiết kế mẫu theo thời gian

Không tối ưu trên toàn bộ mẫu. Một thiết kế tối thiểu gồm:

| Tập dữ liệu | Mục đích | Quy tắc |
|---|---|---|
| In-sample | Xây giả thuyết và chọn rất ít tham số | Không được xem OOS |
| Validation | Chọn trong một họ biến thể đã định trước | Không thay đổi tiêu chí sau khi xem kết quả |
| Test/OOS | Đánh giá cuối cùng | Niêm phong trước khi chạy |
| Walk-forward | Kiểm tra tính ổn định theo thời gian | Lặp train–validate–test theo thứ tự thời gian |

Phải kiểm tra nhiều regime bull, bear, sideways, shock và giai đoạn thanh khoản khác nhau. Các kỳ nghiên cứu futures dài hạn hoặc nghiên cứu Bitcoin tuần không chứng minh lợi thế cho BTCUSDT 1H; khác biệt horizon, venue, phí và microstructure phải được giữ nguyên trong diễn giải [6] [10] [11].

### 9.4. Biến thể và ablation

Mỗi module phải có biến thể ablation để biết thành phần nào thực sự đóng góp:

| Module | Baseline | Ablation nên chạy |
|---|---|---|
| A | Donchian + ATR + EMA + trade-delta | Tắt EMA; tắt Order Flow; next-open thay stop-entry; threshold ATR 1,20 và vùng lân cận; target 2R thay chandelier |
| B | Bollinger + ADX/range + OFI | Price-only; tắt ADX; tắt OFI; thay time stop 12 bar; thay ngưỡng band trong một lưới nhỏ đã định trước |
| C | Funding + OI + liquidation + EMA + delta | Tắt funding; tắt OI; proxy liquidation riêng; trade-delta thay L2; trend 4H bật/tắt |
| D | EMA + VWAP + profile + delta | Tắt profile; tắt VWAP; price-only; thay anchor UTC ngày/tuần trong biến thể riêng; tắt magnitude median |

Không được chọn bộ lọc vì nó cải thiện kết quả trên cùng tập test. Mục tiêu của ablation là đo mức đóng góp và kiểm tra over-filtering. Nếu thêm một filter làm số trade giảm mạnh nhưng expectancy không ổn định, đó không phải bằng chứng filter tốt.

### 9.5. Chỉ số phải báo cáo

Báo cáo tối thiểu gồm trade count, expectancy sau phí/funding, average win/loss, win rate, profit factor, net return, max drawdown, thời gian hồi phục, Sharpe hoặc Sortino, exposure, thời gian giữ lệnh, tail loss, phí, funding cost, slippage cost, partial fill rate và phân phối theo regime. Với futures, phải báo cáo thêm margin usage, notional, leverage, khoảng cách liquidation–stop và số lần stop bị gap.

Kết quả cần được phân rã theo Long/Short, module, năm hoặc giai đoạn, giờ UTC, funding regime, volatility bucket, spread bucket và chất lượng dữ liệu. Không đánh giá chỉ bằng net return. Một chiến lược có lợi nhuận cao nhưng tail loss, drawdown hoặc execution sensitivity lớn có thể không phù hợp để triển khai.

## 10. Cách tránh overfitting và data snooping

Các số 20, 50, 1,20, 2,50, 2,5 ATR, 0,55/0,45, 12 bar, percentile 90 và 1,5% OI chỉ là **giả thuyết khởi đầu**. Rủi ro data-snooping tăng khi chọn nhiều tham số trên cùng một mẫu. Quy trình nên khóa trước chiến lược, biến thể, thước đo chính và tiêu chí loại bỏ.

Không quét một lưới tham số quá rộng rồi chọn đỉnh equity curve. Thay vào đó, kiểm tra một vùng lân cận hợp lý quanh tham số baseline và xem bề mặt kết quả có phẳng hay chỉ có một đỉnh hẹp. Một tham số chỉ đáng tin hơn khi hiệu quả không biến mất với thay đổi nhỏ về lookback, ATR buffer, delta threshold, phí hoặc slippage.

Không dùng cùng một bar để vừa tạo trigger vừa tính fill lý tưởng. Không dùng funding tương lai, OI sửa đổi sau, percentile rolling có dữ liệu tương lai hoặc profile đang hình thành. Không lấy giá thanh lý hiển thị như stop-loss; liquidation là cơ chế riêng theo Mark Price và maintenance margin [5].

Có thể dùng block bootstrap, permutation hoặc reality-check style test để kiểm tra liệu expectancy có vượt nhiễu sau khi đã thử nhiều biến thể. Cần giữ lại một tập OOS chưa chạm đến cho đánh giá cuối cùng. Sau OOS, không chỉnh tham số rồi vẫn gọi kết quả là OOS.

## 11. Cảnh báo rủi ro trọng yếu

**False breakout và whipsaw.** Breakout 1H có thể đảo chiều ngay cả khi ATR tăng. Biên độ cao không có hướng và một nến đóng gần đỉnh/đáy không bảo đảm thanh khoản sau đó tiếp diễn.

**Execution và gap.** Stop có thể trượt trong biến động mạnh, đứt kết nối hoặc order book mỏng. Backtest khớp đúng stop, TP và trigger thường đánh giá quá cao kết quả. Cần stress test spread, slippage, adverse selection và partial fill.

**Funding và liquidation.** Funding có thể thay đổi interval và mức phí. Liquidation theo Mark Price có thể khác Last Price; giá thanh lý hiển thị và giá thanh lý thực tế có thể lệch trong biến động lớn [4] [5]. Không dùng đòn bẩy đến gần vùng thanh lý.

**Order Flow không toàn thị trường.** Dữ liệu một sàn không đại diện toàn bộ BTC. Maker flag, RPI, hidden liquidity, spoofing, latency, missing events và phân mảnh venue có thể làm delta hoặc OFI sai [2] [3] [17].

**OI và liquidation không có hướng tự thân.** OI chỉ là tổng hợp hợp đồng mở. OI giảm không chứng minh rằng một loại vị thế cụ thể đã bị đóng. ForceOrder snapshot cũng không phải sổ cái đầy đủ liquidation. Mọi diễn giải phải được kiểm định riêng [12] [13].

**Phi tĩnh và thay đổi cấu trúc.** BTC có volatility clustering, jumps, thay đổi phí, thay đổi thanh khoản, thay đổi quy tắc sàn và thay đổi hành vi trader. Một kết quả tốt trong bull market có thể không lặp lại trong range hoặc shock.

**Rủi ro vận hành và đối tác.** API, oracle, mark price, ADL, maintenance, mất kết nối, lỗi dữ liệu, counterparty và quy định địa phương đều có thể làm kết quả khác backtest. Paper trading hoặc testnet chỉ kiểm tra một phần rủi ro, không loại bỏ rủi ro thật.

## 12. Kết luận

Bốn module bổ sung nên được triển khai theo thứ tự: chuẩn hóa dữ liệu và execution engine; chạy từng module standalone; chạy các ablation EMA/Order Flow/OI/profile; sau đó mới xây bộ chọn regime và danh mục có trần rủi ro chung. EMA + Order Flow nên giữ vai trò nền tảng cho nhận diện xu hướng và xác nhận, thay vì dùng toàn bộ chỉ báo để tạo một điểm số chủ quan.

Donchian breakout trả lời câu hỏi liệu giá có thoát biên cùng expansion hay không. Bollinger mean reversion trả lời liệu một rejection có xảy ra trong range hay không. Funding–OI–Liquidation pullback kiểm tra liệu một cú reset đòn bẩy có được tái chiếm EMA và flow xác nhận hay không. VWAP–Volume Profile pullback kiểm tra liệu giá có acceptance ngoài vùng giá trị rồi hồi về vùng tham chiếu để tiếp diễn hay không.

Không module nào được coi là tín hiệu chắc chắn. Chỉ một backtest walk-forward, ngoài mẫu, net-of-cost, có mô phỏng Mark Price, funding, slippage, gap, partial fill và tail risk mới có thể cho biết giả thuyết có đáng nghiên cứu tiếp hay không. Nếu dữ liệu không đủ để tái lập điều kiện, quyết định đúng là **no-trade hoặc loại mẫu**, không phải tự ý thay thế bằng một proxy không được công bố.

## References

[1]: https://arxiv.org/abs/1011.6402 "The Price Impact of Order Book Events — Cont, Kukanov và Stoikov"

[2]: https://ideas.repec.org/a/spr/digfin/v1y2019i1d10.1007_s42521-019-00007-w.html "Order flow analysis of cryptocurrency markets — Eduard Silantyev"

[3]: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market "Binance Developers — USDⓈ-M Futures Aggregate Trade Streams"

[4]: https://www.binance.com/en/support/faq/detail/360033525031 "Binance Futures — Introduction to Binance Futures Funding Rates"

[5]: https://www.binance.com/en/support/faq/detail/360033525271 "Binance Futures — Binance Futures Liquidation Protocols"

[6]: https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf "Time Series Momentum — Moskowitz, Ooi và Pedersen"

[7]: https://www.grahamcapital.com/blog/trend-following-primer/ "Trend-Following Primer — Graham Capital Management"

[8]: https://www.bollingerbands.com/bollinger-band-rules "Bollinger Bands Rules — John Bollinger"

[9]: https://www.bollingerbands.com/ "Bollinger Bands — John Bollinger official overview"

[10]: https://www.mdpi.com/2227-9091/8/2/44 "Technical Analysis on the Bitcoin Market: Trading Opportunities or Investors’ Pitfall? — Risks (MDPI)"

[11]: https://www.sciencedirect.com/science/article/abs/pii/S1544612319306415 "Testing for mean reversion in Bitcoin returns with Gibbs-sampling-augmented randomization"

[12]: https://ledgerjournal.org/ojs/ledger/article/view/325 "Reconciling Open Interest with Traded Volume in Perpetual Swaps — Giagkiozis và Said"

[13]: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market "Binance Developers — USDⓈ-M Futures WebSocket Market Streams"

[14]: https://www.binance.com/en/academy/glossary/forced-liquidation "Binance Academy — Forced Liquidation glossary"

[15]: https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/ "TradingView — Volume Weighted Average Price (VWAP)"

[16]: https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/ "TradingView — Volume profile indicators: basic concepts"

[17]: https://www.sciencedirect.com/science/article/pii/S1386418126000029 "Order flow and cryptocurrency returns — Anastasopoulos và cộng sự"

[18]: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data "Binance Developers — USDⓈ-M Futures REST Market Data API"

[19]: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr "Fidelity Learning Center — Average True Range (ATR)"

[20]: https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest.html "CME Group — Introduction to Futures: Open Interest"

[21]: https://www.binance.com/en/support/faq/what-is-funding-rate-and-how-is-it-calculated-in-binance-futures-360033525031 "Binance Support — What Is Funding Rate and How Is It Calculated in Binance Futures?"

[22]: https://www.interactivebrokers.com/campus/trading-lessons/bollinger-bands/ "Interactive Brokers Campus — Bollinger Bands"

[23]: https://www.binance.com/en/academy/articles/what-are-funding-rates-in-crypto-markets "Binance Academy — What Are Funding Rates in Crypto Markets?"

[24]: https://www.coinbase.com/learn/perpetual-futures/understanding-funding-rates-in-perpetual-futures "Coinbase Learn — Understanding Funding Rates in Perpetual Futures and Their Impact"
