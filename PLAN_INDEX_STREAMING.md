# Index streaming (VNINDEX/VN30) — kết luận điều tra 2026-08-07

**Trạng thái: KHÔNG TIẾP TỤC được với SDK/API hiện có.** Đã thử đủ 3 hướng
hợp lý, cả 3 đều thất bại, có bằng chứng thật (không phải đoán).

## Bối cảnh

`trading/collector/feed.py:146` và `main.py:63` có TODO chờ dữ liệu thật để
viết `IndexValue` mapping cho VNINDEX/VN30. Điều tra ngày 2026-08-07 (2 phiên,
sáng + chiều, đều trong giờ giao dịch thật) để lấy dữ liệu đó.

## 3 hướng đã thử — đều có bằng chứng thật, không phải giả định

### 1. `AsyncStreamingService.subscribe_index(["VNINDEX", "VN30"])`
Đọc source: chỉ là wrapper gọi `subscribe_symbol_trade` + `subscribe_symbol_quote`
+ `subscribe_symbol_room` — 3 kênh thiết kế cho chứng khoán **giao dịch được**
(có lệnh khớp, sổ lệnh bid/ask). Index không phải công cụ giao dịch trực tiếp
nên các kênh này không có gì để publish.

**Test thật:** 2 lần, cả sáng (11:34, có thể đã lỡ giờ) lẫn chiều (13:37, chắc
chắn giữa giờ giao dịch) — cả 2 lần chỉ nhận đúng 3 ack subscribe
(`"Subscribed to 2 topic(s)"` × 3, khớp 3 sub-call trade/quote/room), **0
message dữ liệu**. `subscribe_symbol()` generic (không phải riêng cho index)
có source giống hệt — xác nhận `subscribe_index()` không phải cơ chế đặc thù
cho index, chỉ là alias.

Mã `"VNINDEX"`/`"VN30"` xác nhận đúng thật qua `get_indexes()` (34 index có
sẵn, cả 2 mã đều có trong danh sách) — không phải lỗi sai mã như bug mã hợp
đồng phái sinh cũ.

### 2. `AsyncStreamingService.subscribe_symbol_ohlcv(["VNINDEX", "VN30"], Timeframe.MINUTE_1)`
Giả thuyết: kênh OHLCV (đã dùng thành công cho bar cổ phiếu trong
`trading/collector/feed.py`) hợp lý hơn cho "nến index" so với trade/quote.

**Test thật** (13:58, giữa giờ giao dịch): nhận **521 message thật trong 60s**
— nhưng KHÔNG phải nến của VNINDEX/VN30. Server trả về nến 1 phút của **hàng
loạt cổ phiếu thành viên** (VCB, TCB, HPG, ACB, VPB, MBB, VHM, VIC, VNM, SSI,
STB, và nhiều mã HOSE khác). Đọc source `_build_ohlcv_request`: SDK chỉ build
topic `f"trade.{symbol}@{interval}"` — không có logic đặc biệt. Kết luận:
**server SSI hiểu `"VNINDEX"`/`"VN30"` như tên board/nhóm** (subscribe toàn bộ
thành viên), không phải mã chỉ số đơn lẻ có nến riêng.

### 3. `AsyncMarketDataService.get_index_summary(index)` (REST, không phải stream)
**Test thật** (14:01, giữa giờ giao dịch): trả `200` thật, có `index_value`
(VNINDEX=1764.78, VN30=1902.79) — nhưng `trading_date: "2026/08/06"`, tức
**dữ liệu của phiên HÔM QUA**, dù gọi giữa giờ giao dịch hôm nay
(2026/08/07). Đây là tổng kết cuối ngày (EOD summary — có `total_trade`,
`total_match`, v.v., toàn field tổng-cả-ngày), không phải giá trị tức thời.

## Kết luận

Không có method nào trong `ssi-sdk` hiện tại (SDK version đã cài, xem
`PLAN_SSI_SDK_MIGRATION.md`) trả về giá trị index VNINDEX/VN30 theo thời gian
thực. Đây là giới hạn thật của API, không phải bug trong repo này.

## Việc KHÔNG làm (do kết luận trên)

- KHÔNG viết `IndexValue` production mapping trong `feed.py`/`main.py` — chưa
  có nguồn dữ liệu thật nào để map.
- KHÔNG xoá 2 TODO trong `feed.py:146`/`main.py:63` — vẫn đúng, chỉ cập nhật
  comment trỏ tới file này để người sau không điều tra lại từ đầu.

## Nếu vẫn cần dữ liệu index trong tương lai

1. Liên hệ SSI FastConnect hỗ trợ kỹ thuật hỏi thẳng: có endpoint/kênh nào
   khác cho giá trị index real-time không (ngoài `get_index_summary` EOD)?
2. Phương án thay thế không cần index trực tiếp: tự tính "VNINDEX xấp xỉ" từ
   tổng hợp giá các cổ phiếu thành phần đang stream được (phức tạp, sai số,
   không khuyến nghị trừ khi thật sự cần).
3. Chấp nhận không có dữ liệu index cho chiến lược — SmaCrossStrategy hiện
   tại không phụ thuộc index, chỉ cần khi có ý tưởng chiến lược mới cần nó.
