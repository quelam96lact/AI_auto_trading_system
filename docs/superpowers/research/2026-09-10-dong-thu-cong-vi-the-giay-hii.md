# Đóng thủ công vị thế giấy HII trong `engine_state` / `positions`

Ngày: 10/09/2026, 18:18.
Người thực hiện: Claude, theo quyết định trực tiếp của chủ dự án.
Loại thao tác: **UPDATE thủ công trên DB `trading` đang chạy** — không phải hành động của engine.

---

## 1. Vì sao phải làm

Sau khi bỏ HII khỏi `config/config.yaml` (commit `90aec3a`), engine không còn nhận bar HII
nữa. Nhưng state vẫn giữ **300 cổ phiếu HII**:

```
 symbol | qty |     avg_price
 AAA    | 400 |      7071.1588125
 HII    | 300 |       8726.110875
 IJC    | 400 | 7372.059187499999
```

Vị thế này sẽ **đóng băng vĩnh viễn**: không có bar thì không có mark-to-market, không có tín
hiệu bán, không bao giờ đóng được. Nó làm lệch NAV và mọi phép tính `unrealized_pnl` về sau.

`real_trading_enabled` là `false` — đây là vị thế **giấy**, không phải tiền thật. Không có
lệnh nào được gửi ra sàn.

## 2. Giá dùng để đóng

Giá đóng cửa cuối cùng của HII, kiểm chứng chéo hai nguồn độc lập trong DB:

| Nguồn | Giá trị |
|---|---:|
| `bars` — bar 5m cuối `2026-09-10 14:45:00+07` | **10.550** |
| `bars_daily` — `2026-09-10` | **10.550** |

Hai bảng khớp nhau nên không cần chọn giữa chúng.

## 3. Công thức — dùng lại đúng của `PaperBroker`, không tự nghĩ

Lấy nguyên nhánh SELL của `trading/paper_broker.py:146-151` và `:171-173`, với hằng số ở
`:12-14` (`FEE_RATE=0.0025`, `SELL_TAX_RATE=0.001`, `SLIPPAGE_BPS=5`):

```python
slip  = CLOSE_PRICE * (SLIPPAGE_BPS / 10_000)
price = CLOSE_PRICE - slip
gross = price * QTY
fee   = gross * FEE_RATE + gross * SELL_TAX_RATE
pnl   = (price - AVG_PRICE) * QTY - fee
cash  += gross - fee
```

Kết quả:

```
gia dong cua       : 10550.0
gia khop sau slip  : 10544.725
gross              : 3163417.5
phi + thue ban     : 11071.96125
gia von (avg_price): 8726.110875
pnl thuc hien      : 534512.27625
```

Lưu ý về `avg_price`: theo `paper_broker.py:157-165` (FEE-ALARM-1), `avg_price` **đã gồm phí
mua**, nên `pnl` tính như trên không bỏ sót phí vòng mua.

## 4. Thay đổi đã áp dụng

Chạy trong **một transaction** với `ON_ERROR_STOP=1`, sau khi đã `docker compose stop engine`
để engine không ghi đè state:

```sql
BEGIN;
UPDATE engine_state SET cash=94367687.69003572,
                        realized_pnl=144974.89003572706,
                        updated_at=now()
 WHERE id=1;
UPDATE positions SET qty=0, avg_price=0, updated_at=now() WHERE symbol='HII';
COMMIT;
```

| Trường | Trước | Sau |
|---|---:|---:|
| `cash` | 91.215.342,15128572 | **94.367.687,69003572** |
| `realized_pnl` | −389.537,38621427293 | **+144.974,89003572706** |
| `positions.HII.qty` | 300 | **0** |

**Không xoá dòng nào.** Đặt `qty=0, avg_price=0` chính là cách code tự biểu diễn vị thế đã
đóng (`paper_broker.py:175-176`), và `read_positions()` (`storage/db.py:189`) lọc
`WHERE qty > 0` nên dòng này bị bỏ qua khi khôi phục — đúng như mong muốn.

Đáng chú ý: `realized_pnl` chuyển từ **âm sang dương**. HII được mua ở giá vốn 8.726 và đóng
ở 10.550, lãi 534.512 đồng — đủ để lật toàn bộ khoản lỗ luỹ kế −389.537 của danh mục giấy.

## 5. Kiểm chứng sau khi bật lại engine

```
{"msg": "engine restored state", "cash": 94367687.69003572,
 "realized_pnl": 144974.89003572706, "positions": {"IJC": 400, "AAA": 400}}
```

HII biến mất khỏi `positions`; `cash` và `realized_pnl` khớp từng chữ số. Warm-up cả ba mã
(`HPG`, `IJC`, `AAA`) đều 201 bar tới `2026-09-10 14:45 VN`. Log không có `CRITICAL` hay
traceback.

## 6. Điều KHÔNG làm, và vì sao

**Không chèn dòng vào bảng `orders`.** Bảng đó đang giữ 18 lệnh **do engine thật sinh ra**
(15/07 → 03/09) và là dữ liệu dùng để đánh giá hệ thống. Thêm một dòng do người tạo tay vào
đó sẽ làm hỏng chính con số ta dựa vào để phán xét. Dấu vết của can thiệp này nằm ở báo cáo
đang đọc và ở commit tương ứng, không nằm trong bảng dữ liệu vận hành.
