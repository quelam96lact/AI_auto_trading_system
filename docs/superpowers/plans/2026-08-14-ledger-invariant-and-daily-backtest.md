# Kế hoạch: bất biến sổ sách, Fill.pnl nhất quán, và backtest khung ngày

Ngày giao: 2026-08-14 tối muộn. Nhánh: `feature/data-layer`. Base: `2982900`.

**KHÔNG commit, KHÔNG push.**

Ba việc **độc lập**. Việc 1 và 3 quan trọng; việc 2 là dọn nợ, để cuối.

---

## BỐI CẢNH VẬN HÀNH

Phiên đã đóng. Engine vừa được rebuild (chạy code mới, `realized_pnl` đã sửa
thành −328.798,31). Collector vẫn chạy code cũ hơn — **có chủ đích**, nhánh
fallback đã kiểm là an toàn.

- **KHÔNG** restart/rebuild container nào.
- **KHÔNG** đụng `config/config.yaml`, **KHÔNG** bật `real_trading_enabled`.
- **KHÔNG** đụng dữ liệu phái sinh. Mã `41I1G8000` giữ nguyên.
- **KHÔNG** ghi/xoá dữ liệu sản xuất. Việc 3 chỉ ĐỌC `bars_daily`.
- Chạy `pytest` an toàn. Nếu suite chạy lâu gấp 3-4 lần bình thường (~20s) thì
  **nghi ngay có suite khác chạy chồng** — chờ, đừng đi tìm lỗi trong code.

---

# VIỆC 1 — cảnh báo khi hai sổ sách lệch nhau

## Vì sao đây là việc giá trị nhất trong ba việc

Hai lỗi sửa hôm nay (`6664cd9` cổ phiếu, `2982900` phái sinh) **giống hệt nhau**:
`cash` đúng, `realized_pnl` sai, hai sổ lệch. Cả hai sống nhiều tháng.

Chúng sống lâu không phải vì khó tìm — mà vì **không có gì kiểm tra rằng hai sổ
phải khớp**. Lỗi chỉ lộ ra khi luồng giấy chạy thật một phiên rồi có người ngồi
đối chiếu tay.

## Bất biến (đúng LUÔN, không chỉ khi phẳng)

```
cash + Σ(avg_price × qty) − CAPITAL  ==  realized_pnl
```

Chứng minh từ `paper_broker.py` sau bản sửa `6664cd9`:

```
BUY :  cash −= gross + fee ; giá vốn += gross + fee   -> tổng KHÔNG đổi, realized không đổi  ✓
SELL:  cash += gross_s − fee_s ; giá vốn −= avg×qty
       realized += gross_s − fee_s − avg×qty          -> hai vế đổi bằng nhau  ✓
```

Đã đối chiếu với DB sản xuất ngay lúc viết kế hoạch:

```
99.671.201,69 + 0 − 100.000.000 = −328.798,31 = realized_pnl   ✓ khớp
```

## Phải làm

Thêm **2C** vào `scripts/heartbeat_check.py`, cùng khuôn mẫu 2A/2B: **hàm thuần
+ `main()` mỏng**, test được mà không cần DB.

Đọc từ DB: `engine_state` (`cash`, `realized_pnl`) và `positions`
(`symbol`, `qty`, `avg_price`). So với bất biến trên. Lệch quá dung sai →
`CRITICAL`, tin nhắn nêu **cả ba số** (vế trái, vế phải, độ lệch) để người đọc
biết lệch bao nhiêu mà không phải mở DB.

### CAPITAL — chỗ dễ sai nhất, đọc kỹ

`CAPITAL = 100_000_000.0` đang nằm ở `trading/engine/main.py:22`.

**KHÔNG chép số đó sang `heartbeat_check.py`.** Tôi vừa mới phải ghi vào commit
trước rằng giờ phiên bị lặp ở hai nơi là một món nợ — đừng tạo thêm món thứ hai,
và món này còn tệ hơn: nếu hai nơi lệch nhau thì cảnh báo sẽ báo láo mãi mãi
hoặc im mãi mãi.

Ưu tiên: import từ `trading.engine.main`.

**NHƯNG kiểm trước khi import:** `engine/main.py` có thể chạy code ở mức module
(kết nối DB/NATS, tạo đối tượng). Một script cron mà import vào lại khởi động
thứ gì đó là hỏng. **Tự kiểm điều này.** Nếu import không an toàn, **DỪNG và
báo cáo phương án tối thiểu bạn đề xuất** (ví dụ chuyển hằng số sang một module
dùng chung) — **đừng tự ý tái cấu trúc** `trading/`.

### Dung sai

Số thực tích luỹ sai số làm tròn qua nhiều lệnh. Chọn một dung sai và **nói rõ
căn cứ**. Nó phải đủ lỏng để không báo láo vì làm tròn, và đủ chặt để bắt được
một khoản lệch cỡ tiền phí (hàng nghìn đồng). Nếu bạn thấy ngưỡng tôi ngụ ý là
sai, nói ra.

## Kiểm chứng việc 1

1. Khớp → không báo.
2. Lệch quá dung sai → báo, tin nhắn chứa đủ ba số.
3. **Vị thế đang mở** (qty > 0) vẫn khớp — đây là ca dễ làm sai nhất, vì bất
   biến gồm cả giá vốn của vị thế mở, không phải chỉ đúng khi phẳng.
4. **RED bắt buộc:** dựng lại đúng lỗi lịch sử — `realized_pnl = −209.381,13`,
   `cash = 99.671.201,69`, không vị thế nào mở → **phải BÁO**, và độ lệch phải
   ra đúng **119.417,18**. Đây là ca chứng minh cảnh báo này sẽ bắt được chính
   con bug đã xảy ra. Dán số.
5. Test đi qua **đường dựng tin nhắn** trong `main()`, không chỉ hàm thuần —
   bài học từ FEE-ALARM-2 (`max_ts=None` làm chuông báo tự chết vì test chỉ gọi
   hàm thuần).
6. Không phá 2A/2B: toàn bộ test cũ của `heartbeat_check` vẫn xanh.

---

# VIỆC 2 — `Fill.pnl` đang mang hai nghĩa

Sau `6664cd9` và `2982900`:

- **cổ phiếu:** `Fill.pnl` **gồm** phí mua (vì `avg_price` đã cộng phí)
- **phái sinh:** `Fill.pnl` **không gồm** phí mở (phí mở chỉ vào `realized_pnl`)

Cùng một trường, hai nghĩa. Hiện vô hại — Fill phái sinh không được ghi vào bảng
`orders` (đã kiểm). Nhưng nếu sau này nối broker phái sinh vào storage, cột
`orders.pnl` sẽ chứa hai nghĩa trong cùng một bảng, và không ai phát hiện được
bằng mắt.

## Phải làm

`DerivativePaperBroker.close` trả `Fill` với `pnl` **gồm cả phí mở**, để hai lớp
cùng nghĩa "lãi/lỗ trọn vòng của lần đóng này".

**BẮT BUỘC kiểm trước khi sửa:** có chỗ nào cộng dồn `fill.pnl` để ra
`realized_pnl` không? Nếu có, đổi `Fill.pnl` sẽ **đếm phí mở hai lần**. Tự tìm,
dán bằng chứng đã tìm. Nếu có double-count, **DỪNG và báo cáo**.

## Kiểm chứng việc 2

1. `close_fill.pnl == realized_pnl` của vòng đó (long và short).
2. `report.realized_pnl` **không đổi** so với trước việc 2 — nếu nó đổi thì bạn
   vừa đếm hai lần. Chạy lại sample thật, dán số, phải y hệt `2982900`.
3. **RED bắt buộc** cho thay đổi này.
4. Test cũ nào khẳng định `close_fill.pnl` theo nghĩa cũ thì phải đổi — nhưng
   **báo cáo rõ từng cái**, và nói thẳng vì sao bạn cho là phải đổi.

---

# VIỆC 3 — backtest khung NGÀY (đo, không sửa chiến lược)

## Mục đích

Câu hỏi chặn go-live: **chiến lược có biên lợi thế không?** Bốn tháng bar 5 phút
nói KHÔNG, và lỗ **cả trước phí**. Giả thuyết chưa kiểm: giao cắt SMA là công cụ
bắt xu hướng, bar 5 phút phần lớn là nhiễu.

Dữ liệu đã có sẵn, **không cần tải gì**: `bars_daily` — 1.551 mã, 2.969.328
dòng, 2016-01-03 → 2026-08-13. HII 2.287 / IJC 2.652 / AAA 2.647 bar ngày.

## Phải làm

Viết script thăm dò trong `scripts/` theo đúng quy ước sẵn có (`.spike_*.py`),
**chỉ ĐỌC** `bars_daily`.

Chạy `run_backtest` **KHÔNG chỉnh một tham số nào** của chiến lược/rủi ro —
đúng cấu hình đang dùng, chỉ đổi nguồn bar:

```
rổ mã:   HII,IJC,AAA   và   VCB,HPG,TCB
vốn:     5.021.459     và   1.000.000.000
kỳ:      (a) 2026-04-03 -> 2026-08-07  (cùng kỳ với bản 5 phút, để so trực tiếp)
         (b) toàn bộ 10,5 năm          (đây mới là phép đo đáng quan tâm)
```

Báo cáo **chỉ chép số**, mỗi dòng: số lệnh · tỉ lệ thắng · **PnL gộp trước phí**
· phí+thuế · PnL ròng · MaxDD.

Cột **PnL gộp trước phí** là cột quyết định — nó tách "tín hiệu có đúng không"
khỏi "phí có ăn hết không". Đừng bỏ.

**KHÔNG** nhận định, **KHÔNG** khuyến nghị, **KHÔNG** đề xuất tối ưu tham số.
Nếu bạn thấy mình đang viết một câu mà không chỉ được nó lấy số từ đâu, xoá câu đó.

## Hai thứ phải kiểm và BÁO CÁO, đừng lặng lẽ bỏ qua

1. **Giá trong `bars_daily` đã điều chỉnh chưa?** Nếu chưa điều chỉnh chia
   tách/cổ tức, một backtest 10 năm sẽ dính những cú nhảy giá giả và **con số
   không đáng tin**. Tự kiểm (ví dụ: tìm bước nhảy giá bất thường qua đêm trên
   một mã đã từng chia tách). Nếu chưa điều chỉnh — **nói thẳng ngay đầu báo
   cáo**, đừng trình số như thể chúng chắc chắn.

2. **`atr_pct_threshold` được đặt cho bar 5 phút.** Trên bar ngày, ATR/giá lớn
   hơn hẳn nên bộ lọc sẽ cho qua nhiều hơn. **KHÔNG chỉnh nó** — nhưng ghi rõ
   quan sát này trong báo cáo, kèm ATR/giá trung bình đo được trên bar ngày so
   với bar 5 phút.

## Kiểm chứng việc 3

- Số bar nạp cho mỗi mã, mỗi kỳ (chứng minh nạp đúng dữ liệu).
- Warm-up đủ: SMA chậm cần bao nhiêu bar, kỳ (a) có đủ không — nếu **không đủ**
  thì nói rõ thay vì trình một kết quả rỗng như thể có ý nghĩa.
- Script chạy lại được, kết quả ổn định giữa hai lần chạy.
- Suite + ruff vẫn sạch (việc này không sửa `trading/`).

---

# Toàn bộ

- `uv run pytest -q` → ≥ 298 + test mới, không test cũ nào đỏ ngoài các test đã
  báo cáo ở việc 2.
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán mức rủi ro + danh sách file.
- **KHÔNG commit, KHÔNG push.**

# Nếu thấy kế hoạch sai

Dừng và phản biện. Ba chỗ tôi có thể đã chọn nhầm:

1. **Việc 1 đặt trong `heartbeat_check.py`.** Đây là kiểm tra tính ĐÚNG ĐẮN chứ
   không phải tính SỐNG CÒN, mà file này là dead-man's switch. Nếu bạn cho rằng
   nó thuộc chỗ khác — nói ra.
2. **Việc 2 có đáng làm không.** Nó là dọn nợ cho một tình huống chưa xảy ra.
   Nếu bạn thấy churn không xứng, nói ra và tôi bỏ.
3. **Việc 3, giữ nguyên mọi tham số.** Có lập luận rằng so sánh công bằng thì
   phải chỉnh tham số theo khung thời gian. Tôi cố ý KHÔNG chỉnh, để phép đo này
   trả lời đúng một câu hỏi hẹp. Nếu bạn cho là vô nghĩa nếu không chỉnh — nói ra.
