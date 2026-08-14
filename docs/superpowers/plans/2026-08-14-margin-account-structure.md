# Kế hoạch: mô hình hoá tài khoản margin — sức mua và tài sản ròng

Ngày giao: 2026-08-14 tối muộn. Nhánh: `feature/data-layer`. Base: `e775463`.

**KHÔNG commit, KHÔNG push.**

Đây là **phần 1/2**. Phần này chỉ **THU THẬP và TÍNH**, chưa nối vào đường đặt
lệnh. Phần 2 (dùng NAV làm `capital`, chặn theo `max_buy_quantity`) giao sau khi
chủ dự án nhìn thấy số thật.

---

## BỐI CẢNH — vì sao việc này cần

Chủ dự án cho biết **0434226 là tài khoản margin, căn theo sức mua**. Mô hình
hiện tại của hệ thống sai với loại tài khoản này.

Tôi đã gọi API thật (chỉ đọc) để kiểm, `get_max_buy_sell_at_market_price`:

```
                 max_buy   margin_ratio      (gia ~)
0434221  HII         527        0%           tien mat 5.021.459
         IJC         608        0%
         AAA         648        0%
0434226  HII       6.660        0%           tien mat 2.429.135
         IJC      13.999       50%
         AAA      12.952       40%
```

0434226 mua được **gấp 12–26 lần** 0434221 dù ít tiền mặt hơn — nhờ danh mục
~200 triệu làm tài sản đảm bảo.

**Hai điều bất ngờ, đã đo, đừng làm lại:**

1. `purchase_power` trả về **chuỗi RỖNG** ở cả hai tài khoản. **KHÔNG dùng
   trường này.** Tín hiệu dùng được là `max_buy_quantity`.
2. `margin_ratio` là **chuỗi** dạng `'50%'`, và **khác nhau theo từng mã**
   (HII 0% — không được cấp margin trên tài khoản này).

## Quyết định của chủ dự án (2026-08-14)

`capital` để tính rủi ro = **tài sản ròng** = tiền mặt + giá trị cổ phiếu đang
giữ − nợ.

Lý do: rủi ro 1% mỗi lệnh phải là 1% của số tiền **thực sự sở hữu**, không phải
1% của số tiền vay được.

**Phân biệt hai đại lượng khác loại — đây là gốc của cả kế hoạch:**

- **Sức chứa** (mua tối đa được bao nhiêu): `max_buy_quantity`, **theo từng mã**,
  do sàn quyết. Dùng làm **trần cứng**.
- **Vốn rủi ro** (nên mua bao nhiêu): **một** con số cho cả tài khoản = NAV.

Lấy sức mua làm `capital` là lỗi khái niệm — `RiskManager` nhận một số, còn sức
mua thì khác nhau theo từng mã.

---

# VIỆC 1 — bảng lưu sức mua

## Schema mới trong `trading/storage/schema.sql`

Lưu theo (account_no, symbol, ts) — chuỗi ảnh chụp giống các bảng account khác:

```sql
CREATE TABLE IF NOT EXISTS account_buying_power (
  account_no   text NOT NULL,
  symbol       text NOT NULL,
  ts           timestamptz NOT NULL,
  max_buy_qty  integer NOT NULL,
  max_sell_qty integer NOT NULL,
  margin_ratio_pct double precision,   -- NULL khi không parse được
  PRIMARY KEY (account_no, symbol, ts)
);
```

**KHÔNG lưu `purchase_power`** — đã đo là rỗng, lưu một cột luôn rỗng chỉ làm
người sau tưởng nó có nghĩa.

`margin_ratio_pct` cho phép NULL: chuỗi `'50%'` → `50.0`; nếu SSI trả dạng lạ
thì NULL chứ **đừng đoán**.

## Đồng bộ trong `trading/collector/account_sync.py`

Thêm `_sync_buying_power(...)`, gọi trong cùng vòng lặp tài khoản đang có, cho
**mỗi mã trong `cfg.symbols`**.

Số lời gọi: 2 tài khoản × 3 mã = 6 mỗi chu kỳ 5 phút. Chấp nhận được.

**Xử lý lỗi giống hệt khuôn mẫu đang có**: một mã lỗi thì `alert("WARN", ...)`
rồi `continue`, không làm hỏng cả vòng đồng bộ. Đừng phát minh cách khác.

---

# VIỆC 2 — tính tài sản ròng (NAV)

## Vấn đề đã đo: giá cũ và tài sản không định giá được

```
ma đang giữ ở 0434226, bar ngày mới nhất:
  CAP  06/08   HCM  06/08   SSI  06/08   TCX  06/08   (cũ 8 ngày)
  VCB  11/08                                          (cũ 3 ngày)
  MIRHCM261  KHÔNG CÓ BAR NÀO  (chứng quyền, cost_price=0, sellable=0)
```

## Nguyên tắc: cái gì không định giá được thì tính BẰNG 0

Đây là hướng an toàn — NAV thấp hơn thực tế → lệnh nhỏ hơn → không bao giờ đặt
lệnh lớn hơn mức tài sản thật cho phép. Ngược lại thì nguy hiểm.

Viết hàm thuần trong `trading/storage/db.py` hoặc module mới (bạn chọn, nêu lý
do), nhận vào: tiền mặt, nợ, danh sách vị thế, hàm lấy giá — trả về NAV **và**
danh sách mã không định giá được.

Quy tắc:

- Có giá và giá **không cũ hơn `MAX_PRICE_AGE_DAYS`** (đề xuất 5 ngày giao dịch,
  bạn phản biện nếu thấy sai) → tính vào NAV.
- Không có giá, hoặc giá cũ hơn ngưỡng → **tính 0**, và tên mã vào danh sách
  "không định giá được".
- NAV = tiền mặt + Σ(qty × giá) − nợ.

## Cảnh báo

Nếu danh sách "không định giá được" khác rỗng → `alert("WARN", ...)` nêu rõ
**mã nào** và **vì sao** (không có giá / giá cũ bao nhiêu ngày). Không im lặng.

Đây là điểm mấu chốt: NAV tính hụt mà không ai biết thì tệ hơn NAV không tính.

## Lưu NAV

Thêm cột hoặc bảng để lưu NAV theo (account_no, ts) — **bạn đề xuất**, kèm lý do
chọn thêm cột vào `account_balance_snapshot` hay bảng riêng. Nêu rõ đánh đổi.

---

# Ràng buộc

- **Được sửa:** `trading/storage/schema.sql`, `trading/storage/db.py`,
  `trading/collector/account_sync.py`, module mới nếu cần, và test.
- **KHÔNG đụng:** `trading/risk.py`, `trading/engine/main.py`,
  `trading/real_orders.py`, `scripts/confirm_real_order.py`,
  `config/config.yaml`, `trading/paper_broker.py`.
  **Phần 1 KHÔNG nối vào đường đặt lệnh.** Nếu bạn thấy mình đang sửa cách tính
  cỡ lệnh — dừng lại, đó là phần 2.
- **KHÔNG** bật `real_trading_enabled`. **KHÔNG** restart container.
- **KHÔNG** gọi API đặt lệnh. `get_max_buy_sell_at_market_price` là chỉ đọc — chỉ
  dùng nó.

# Kiểm chứng

1. **NAV — ca cốt lõi:** vị thế có giá tươi → tính đúng; một mã không có giá →
   **tính 0** và có trong danh sách cảnh báo; một mã giá quá cũ → **tính 0** và
   có trong danh sách. Ba ca riêng, đừng gộp.
2. **RED bắt buộc:** bỏ nhánh "không định giá được thì tính 0" (cho nó dùng
   `cost_price` thay thế) → test phải ĐỎ. Đây là nhánh an toàn quan trọng nhất.
3. `_sync_buying_power`: một mã ném lỗi → WARN + tiếp tục các mã còn lại, không
   làm hỏng cả vòng đồng bộ.
4. `margin_ratio` `'50%'` → `50.0`; chuỗi lạ → `None` (không đoán).
5. Toàn bộ suite + ruff sạch. **Test cũ đỏ thì DỪNG và báo cáo.**
6. `gitnexus_impact` trên `sync_account_data` trước khi sửa.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Ba chỗ tôi có thể đã chọn nhầm:

1. **Ngưỡng 5 ngày giao dịch.** Giá 06/08 (cũ 8 ngày) sẽ bị loại, tức NAV của
   0434226 tụt từ ~205 triệu xuống chỉ còn tiền mặt + VCB ≈ 92 triệu. Đó là hệ
   quả LỚN. Nếu bạn thấy nên nới ngưỡng, hoặc nên nạp giá tươi cho các mã đang
   giữ thay vì loại chúng — **nói ra**, đây là chỗ tôi ít chắc nhất.
2. **Tính 0 thay vì dùng `cost_price`.** `cost_price` luôn có sẵn và gần đúng.
   Tôi chọn 0 vì giá vốn không phải giá trị hiện tại và có thể cao hơn thực tế
   rất nhiều. Nếu bạn thấy lập luận này sai — nói ra.
3. **Đồng bộ sức mua cho `cfg.symbols` thôi**, không cho các mã đang giữ. Nghĩa
   là ta biết mua được bao nhiêu HII/IJC/AAA nhưng không biết bán được bao nhiêu
   CAP/HCM/... Với phần 1 thì đủ, nhưng nếu bạn thấy thiếu — nói ra.
