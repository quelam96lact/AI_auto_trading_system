# Runbook Diễn tập Đặt và Huỷ Lệnh Thật BingX Perpetual (Brief 112)

> **Cập nhật:** 27/09/2026 (Brief đợt 112).
> **Người thực thi:** Chủ dự án trực tiếp thực hiện trong terminal sau khi Claude audit.
> ⛔ **LUẬT TỐI THƯỢNG:** Agent TUYỆT ĐỐI KHÔNG chạy `--send`, không tự ý gửi bất kỳ lệnh thật nào lên sàn. Mọi lệnh thật do chủ tài khoản tự tay bấm.

---

## 0. Mục tiêu và phạm vi

Diễn tập theo đúng khuôn mẫu diễn tập lệnh thật SSI (đợt 100):
1. Đặt **01 lệnh giới hạn (LIMIT BUY)** nhỏ nhất có thể, ở mức giá **xa thị trường (-5%)** để không khớp;
2. Đọc lại trạng thái lệnh qua API;
3. Huỷ ngay lập tức trên sàn;
4. Xác nhận trạng thái lệnh đã chuyển sang `CANCELED`.

Mục tiêu là chứng minh toàn bộ chu trình kỹ thuật (kết nối, giờ server, chữ ký HMAC-SHA256, API key có quyền Trade, đặt và huỷ lệnh) hoạt động chuẩn xác từ đầu đến cuối với mức rủi ro tiệm cận bằng 0.

---

## 1. Cơ chế API Key: MỘT Key duy nhất (Quyết định ngày 27/09/2026)

Key cấu hình trong `.env` sử dụng tên biến viết hoa toàn bộ:
- `BINGX_API_KEY`
- `BINGX_API_SECRET`

Theo xác nhận của chủ dự án:
- Key **CÓ QUYỀN Trade** (giao dịch Perpetual Futures);
- Key **ĐÃ TẮT QUYỀN Withdraw** (không thể rút tiền);
- Key **ĐÃ BẬT IP Whitelist** (chỉ IP được duyệt mới gọi được API có ký).

> [!WARNING] CỰC KỲ QUAN TRỌNG KHI ĐỔI MÁY / ĐỔI MẠNG:
> BingX kiểm tra IP whitelist rất nghiêm ngặt đối với mọi endpoint có chữ ký HMAC.
> Nếu bạn **đổi mạng internet** (IP công cộng thay đổi) hoặc **chuyển mã nguồn sang VPS Ubuntu**, bạn **BẮT BUỘC PHẢI VÀO TRANG QUẢN LÝ API BINGX ĐỂ CẬP NHẬT IP WHITELIST**.
> Nếu không cập nhật, mọi request có ký sẽ bị sàn từ chối với HTTP 403 (mã lỗi `100410: IP not whitelisted`).

---

## 2. Các lá chắn an toàn cứng trong Script

Mọi thông số được kiểm soát chặt chẽ trong code (`scripts/bingx_drill_place_cancel.py`):
- **Trần danh nghĩa tối đa:** Cứng **20 USDT** (`MAX_NOTIONAL_USDT = 20.0`).
- **Khối lượng đặt:** Đúng khối lượng tối thiểu của sàn = **0.0001 BTC** (`tradeMinQuantity`).
- **Giá đặt an toàn:** Bằng giá thị trường × **(1 − 5%)**, làm tròn **xuống** (floor) theo bước giá 0.1 USDT (`tickSize`). Thấp hơn giá thị trường 5% đảm bảo không bị khớp trong vài giây trước khi huỷ.
- **Cờ Post-Only:** Bật `timeInForce: PostOnly` làm lớp phòng hộ kỹ thuật chống khớp ngay (nếu vô tình chạm giá ask thì sàn sẽ tự từ chối lệnh).
- **Kiểm tra độ lệch đồng hồ:** Phải nằm trong ngưỡng an toàn `abs(offset) <= 2500 ms` so với `recvWindow = 5000 ms`.
- **Kiểm tra vị thế & lệnh chờ:** Bắt buộc **0 có vị thế mở** và **0 có lệnh chờ** trên mã `BTC-USDT`.
- **Kiểm tra ký quỹ:** Ký quỹ khả dụng phải `available_margin >= 2 * estimated_margin`.

> [!NOTE] Lưu ý số dư khả dụng khi chạy thật:
> Giá trị danh nghĩa lệnh 0.0001 BTC ở giá ~80.200 USDT là ~8.02 USDT. Ký quỹ ước tính (tính an toàn 1x) là ~8.02 USDT.
> Điều kiện an toàn 2× ký quỹ đòi hỏi tài khoản Perpetual có tối thiểu **~16.05 USDT khả dụng**.
> Nếu số dư ví Perpetual hiện tại thấp hơn ngưỡng này (ví dụ đang có ~8.08 USDT), lệnh chạy thật `--send` sẽ dừng an toàn. Chủ dự án cần chuyển thêm ~8–10 USDT vào ví Perpetual trước khi bấm chạy thật.

---

## 3. Các bước diễn tập chi tiết

### Bước 1: Chạy thử (Dry-Run — Chỉ đọc)

Chạy lệnh trong terminal (mặc định không có `--send` là chạy thử):
```bash
uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env live
```

Script sẽ kết nối sàn BingX, kiểm tra giờ server, lấy giá ticker, thông số hợp đồng và số dư ví, sau đó in bảng kế hoạch lệnh:

```text
======================================================================
 KẾ HOẠCH LỆNH DIỄN TẬP BINGX PERPETUAL (DRILL ORDER PLAN)
======================================================================
 Môi trường:        LIVE (LIVE REAL MONEY)
 Mã hợp đồng:       BTC-USDT
 Chiều lệnh:        BUY (Long)
 Loại lệnh:         LIMIT (PostOnly)
 Giá thị trường:    84465.6
 Giá đặt diễn tập:  80242.3 (thấp hơn thị trường 5.00%)
 Bước giá:          0.1
 Khối lượng đặt:    0.0001 BTC (khối lượng tối thiểu)
 Giá trị danh nghĩa: 8.0242 USDT (trần an toàn: 20.0 USDT)
 Ký quỹ ước tính:   8.0242 USDT
 Ký quỹ khả dụng:   8.0778 USDT
 Độ lệch đồng hồ:   -1318 ms
======================================================================

[CHẠY THỬ / DRY-RUN] Hoàn tất lập kế hoạch. KHÔNG gửi bất kỳ lệnh nào lên sàn.
(Dùng cờ '--send' và '--env live' để kích hoạt gửi lệnh thật sau khi audit).
```

### Bước 2: Kiểm tra kỹ bảng kế hoạch

Chủ tài khoản đối chiếu các thông số:
1. Môi trường có đúng là `LIVE` không?
2. Giá thị trường có khớp tương đối với bảng giá trên App BingX không?
3. Giá đặt có thấp hơn thị trường đúng 5% không?
4. Khối lượng có đúng là 0.0001 BTC không?
5. Độ lệch đồng hồ có nằm trong khoảng an toàn (dưới ±2500 ms) không?

### Bước 3: Chạy thật với cờ `--send` (Chủ dự án tự tay bấm)

Khi đã sẵn sàng và kiểm tra số dư khả dụng đủ (>= 16.05 USDT), chạy:
```bash
uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env live --send
```

Script sẽ in lại kế hoạch và dừng lại yêu cầu người vận hành xác nhận:
```text
Gõ YES để GỬI LỆNH: 
```

- Gõ chính xác: `YES` rồi nhấn `Enter`.
- (Gõ bất kỳ chữ nào khác như `yes`, `y` hoặc để trống sẽ huỷ an toàn ngay lập tức).
- Script sẽ:
  1. Gửi lệnh `place_limit_order` (LIMIT BUY 0.0001 BTC @ giá -5%, PostOnly).
  2. In `order_id`, `client_order_id`.
  3. Thăm dò trạng thái lệnh (phải là `NEW` hoặc `PENDING`).
  4. Gửi yêu cầu huỷ `cancel_order`.
  5. Đọc lại trạng thái cho đến khi xác nhận `CANCELED`.
  6. Ghi audit log vào file JSON tại thư mục `logs/bingx_drill_<timestamp>.json`.

### Bước 4: Đối chiếu trực quan trên ứng dụng BingX

Ngay sau khi script hoàn tất:
1. Mở App BingX trên điện thoại hoặc trình duyệt web.
2. Vào mục **Hợp đồng vĩnh viễn (Perpetual Futures)** -> **Lịch sử lệnh (Order History)**.
3. Xác nhận:
   - Thấy lệnh `BUY LIMIT 0.0001 BTC-USDT` ở mức giá đặt.
   - Trạng thái lệnh ghi rõ: **Đã huỷ (Canceled)**.
4. Chuyển sang tab **Vị thế (Positions)**:
   - Xác nhận **KHÔNG CÓ VỊ THẾ NÀO ĐANG MỞ**.

---

## 4. Xử lý sự cố và ý nghĩa từng mã thoát (Exit Codes)

| Mã Exit | Ý nghĩa | Hành động của người vận hành |
|---|---|---|
| **0** | **Thành công (OK)** | Chu trình hoàn hảo: Chạy thử thành công HOẶC lệnh thật đã được đặt rồi huỷ sạch sẽ và xác nhận `CANCELED` trên sàn. Không cần làm gì thêm. |
| **1** | **Dừng ở khâu tiền kiểm hoặc không tìm thấy lệnh** | Vi phạm an toàn trước khi gửi (lệch đồng hồ quá lớn, có lệnh chờ/vị thế mở, thiếu ký quỹ, thiếu cờ `--env live`), HOẶC gửi xong nhưng API không tìm thấy lệnh sau 3 lần thăm dò.<br>-> Đọc thông báo lỗi trên terminal. Nếu là lỗi sau gửi: mở app BingX đối chiếu tay trong mục Lịch sử lệnh. |
| **2** | **CẢNH BÁO NGUY CẤP (CRITICAL)** | Có 3 tình huống xảy ra:<br>1. Ngoại lệ mạng sau khi gửi -> không rõ lệnh đã lên sàn chưa;<br>2. Lệnh bị khớp một phần hoặc toàn bộ (`FILLED`);<br>3. Gửi lệnh huỷ thất bại hoặc lệnh vẫn còn treo (`NEW/PENDING`). |

### Hướng dẫn hành động khẩn cấp khi gặp Exit 2:

Khi gặp Exit 2, terminal sẽ in khối cảnh báo đỏ `CẢNH BÁO NGHIÊM TRỌNG — BINGX DRILL!` và phát alert `CRITICAL`:

1. **Trường hợp lệnh còn treo:**
   - Mở ngay App BingX -> Tab Lệnh đang chờ (Open Orders).
   - Tìm lệnh mua 0.0001 BTC đang treo -> **Bấm Huỷ bằng tay ngay lập tức**.
2. **Trường hợp lệnh đã khớp (vô cùng hy hữu):**
   - Script cố ý **KHÔNG TỰ Ý ĐÓNG LỆNH** để tránh gửi thêm lệnh market không kiểm soát.
   - Mở App BingX -> Tab Vị thế (Positions).
   - Thấy vị thế Long 0.0001 BTC (~8 USD) -> **Bấm "Đóng nhanh" hoặc "Thị trường" (Market Close)** để đóng vị thế bằng tay.
   - Vì khối lượng chỉ là 0.0001 BTC và mua ở giá thấp hơn thị trường 5%, thiệt hại tài chính nếu có chỉ là vài cent (dưới 0.1 USDT).

---

## 5. Môi trường Demo VST (`--env demo`)

BingX cung cấp domain `https://open-api-vst.bingx.com` cho giao dịch tiền ảo VST:
- Lệnh: `uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env demo`
- **Key hiện tại DÙNG ĐƯỢC trên VST** (Claude kiểm thật 27/09: cùng `BINGX_API_KEY` đọc được số dư VST 80.002,16 VST). Bản nháp đầu của runbook ghi ngược lại, nhưng đó là suy đoán chưa kiểm.
- **Thứ tự bắt buộc: chạy `--env demo --send` TRƯỚC, đạt exit 0, rồi mới chạy live.** Demo dùng tiền ảo nên kiểm được đường POST đặt lệnh (chữ ký POST chưa được kiểm thật ở đợt 112; GET và DELETE đã kiểm) mà không có rủi ro.

## 8. Bài học từ lần diễn tập demo thật (Claude, 27/09/2026)

Đạt, exit 0: orderId `2104035039902699520`, đặt → `PENDING` → huỷ → `CANCELLED`. Sau đó 0 lệnh chờ, 0 vị thế.

1. **Tài khoản ở Hedge mode** (`dualSidePosition: "true"`, cả demo lẫn live). Gửi `positionSide=BOTH` thì bị từ chối với mã 109400. Script giờ **đọc chế độ vị thế trước**, rồi chọn `LONG` (Hedge) hoặc `BOTH` (One-way).
2. **Sàn trả `CANCELLED` (hai chữ L)**, không phải `CANCELED`. Bản đầu của script vì vậy báo động giả "LỆNH CÒN TREO" trên một lệnh đã huỷ xong.
3. **PostOnly KHÔNG được áp dụng**: sàn trả `postOnly: false` dù đã gửi `timeInForce=PostOnly`. Lệnh thực chất là LIMIT thường, và **chỉ còn giá thấp hơn thị trường 5% bảo vệ** khỏi bị khớp. Chưa tìm được tham số post-only đúng có nguồn; không đoán.
4. **Gõ YES qua pipe:** PowerShell 5.1 chèn BOM (`﻿YES`), nên cổng YES từ chối, và đó là **đúng**. Nếu phải pipe thì dùng `cmd /c "echo YES| uv run python ..."`. Tốt nhất là chạy tay rồi tự gõ.
5. Đòn bẩy mặc định trên demo là **20X** (theo `raw.leverage`). Script không đổi đòn bẩy.
6. **Sàn từ chối** (HTTP 200 kèm `code != 0`) nghĩa là **không có lệnh nào được tạo**: script thoát với mã 1 và in thông báo từ chối. Còn **mất kết nối hoặc timeout** mới là "KHÔNG RÕ LỆNH ĐÃ LÊN SÀN CHƯA" (CRITICAL, mã 2).

## 9. Đòn bẩy và ký quỹ — không cần nạp thêm tiền (Claude, 27/09/2026)

- Script tính **ký quỹ = giá trị danh nghĩa ÷ đòn bẩy đang đặt trên sàn**. Đòn bẩy đọc qua `GET /openApi/swap/v2/trade/leverage`, script **không đổi** nó. Bản trước tính theo x1, nên đòi khoảng 16 USDT.
- **Bắt buộc ISOLATED**, đọc qua `GET /openApi/swap/v2/trade/marginType`. Nếu là CROSSED thì script dừng, vì khi đó cả ví phải chịu lỗ.
- **Trần đòn bẩy cho diễn tập là x50.** Nếu đòn bẩy đang đặt cao hơn thì script dừng, và chủ dự án chỉnh lại trong app.
- **Số đọc ngày 27/09:**

  | | Đòn bẩy | Chế độ | Ký quỹ lệnh diễn tập |
  |---|---|---|---|
  | Live | x50 (tối đa x150) | ISOLATED | ≈ 0,16 USDT |
  | Demo | x20 | ISOLATED | ≈ 0,40 USDT |

  Live qua được cổng 2× với số dư 8,08 USDT, nên **không cần nạp thêm**.
- **Lỗ tối đa nếu lệnh diễn tập lỡ khớp** chỉ bằng ký quỹ của lệnh, khoảng 0,16 USDT ở x50, cộng phí. Muốn khớp thì giá phải giảm 5% trong vài giây giữa lúc đặt và lúc huỷ.
- Demo chạy lại sau khi sửa: orderId `2104037388096376832`, PENDING → CANCELLED, exit 0.
