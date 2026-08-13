# Kế hoạch: gỡ bế tắc sizing của luồng paper + làm mọi lần từ chối lên tiếng

Ngày giao: 2026-08-13 khuya. Nhánh: `feature/data-layer`. Base: `63e6028`.

**KHÔNG commit, KHÔNG push.** `gitnexus_detect_changes` khi xong.

---

## CẢNH BÁO HIGH RISK

`gitnexus_impact` trên `Method:trading/risk.py:RiskManager.approve_sized`:
**HIGH** — 2 caller trực tiếp (`run_backtest`, `process_bar`), 3 luồng thực
thi. Đây là lõi paper trading.

**Và một hệ quả phải nói trước:** sau thay đổi này engine paper sẽ **thực sự
bắt đầu giao dịch**. `positions`, `orders`, `pnl_daily` sẽ bắt đầu chuyển động
trên stack thật. Đó là mục đích, nhưng đừng ngạc nhiên khi thấy nó.

---

## Phát hiện — đo được, không suy luận

`run_backtest` cho **0 giao dịch** trên 4 tháng bar 5 phút, với **cả hai** rổ mã
(HII/IJC/AAA và VCB/HPG/TCB), ở **cả** vốn 5.021.459 lẫn 1.000.000.000.

Vốn và mã đều không đổi kết quả — đó là manh mối. `approve_sized()` áp hai luật
chống nhau:

```
qty        = capital * risk_pct / (atr * atr_multiplier)     # 0,01 và 2,0
ràng buộc:   ref_price * qty <= capital * max_order_value_pct # 0,20
```

Thay `qty` vào, **capital triệt tiêu ở cả hai vế**:

```
ref_price / atr <= 40   <=>   atr / ref_price >= 2,5%
```

BUY chỉ được duyệt khi ATR ≥ 2,5% giá — bất kể tài khoản có bao nhiêu tiền.

Đo ATR/giá **cao nhất từng đạt** trên bar 5 phút:

| Mã | Max | Số bar ≥ 2,5% |
|---|---|---|
| HII | 2,003% | **0** |
| IJC | 1,350% | **0** |
| AAA | 0,937% | **0** |

Cái bẫy thứ hai: `atr_pct_threshold = 0,005` cho crossover lọt qua ở 0,5%, rồi
sizing giết nó ở 2,5%. Giữa hai con số đó tín hiệu chết **im lặng**.

Điều này giải thích triệu chứng chưa ai nối lại: `orders` chỉ có 1 dòng từ
15/07, và engine chạy trọn phiên 13/08 sinh 0 lệnh. Crossover CÓ xảy ra (9–56
lần mỗi mã qua được bộ lọc ATR) rồi bị vứt ở khâu sizing.

**Đường lệnh THẬT không dính:** `real_orders.handle_crossover()` gọi `approve()`
dùng `qty=100` cố định, chỉ kiểm trần 20%. HII: 860.000 ≤ 1.004.292 → qua.

---

# VIỆC 1 — cap `qty` cho vừa trần, thay vì từ chối thẳng

## Quyết định của chủ dự án (2026-08-13)

Trong ba hướng (nới `max_order_value_pct` / giảm `atr_multiplier` / cap `qty`),
chọn **cap `qty`**. Lý do: nó **không nới rủi ro** — trần 20% giữ nguyên, chỉ
thôi vứt bỏ tín hiệu.

## Phải làm

Trong `approve_sized`, nhánh BUY:

```python
qty_atr = int((capital * risk_pct / (atr * atr_multiplier)) // 100) * 100
qty_cap = int((capital * max_order_value_pct / ref_price) // 100) * 100
qty = min(qty_atr, qty_cap)
if qty < 100:
    -> từ chối, kèm lý do (xem việc 2)
```

`min()` là điểm mấu chốt: khối lượng **không bao giờ vượt** mức ATR sizing cho
phép, **cũng không bao giờ vượt** trần giá trị lệnh. Hai bất biến cũ đều giữ.

Sau đó khối kiểm tra `order_value > capital * max_order_value_pct` trở nên
**không bao giờ đúng** — `qty_cap` đã bảo đảm. Xoá nó và ghi comment nói rõ vì
sao nó thừa, đừng để lại code chết.

**KHÔNG đụng** `risk_pct`, `atr_multiplier`, `max_order_value_pct`,
`max_positions`, `max_daily_loss_pct`. Không đụng `atr_pct_threshold` trong
`sma_cross.py`. Đây là sửa logic, **không phải chỉnh tham số**.

---

# VIỆC 2 — mọi lần từ chối phải nói được lý do

`approve_sized` trả `None` ở 6 chỗ khác nhau và `approve` trả `False` ở 3 chỗ,
không phân biệt. Một hệ thống giao dịch vứt tín hiệu mà không nói vì sao thì
không gỡ lỗi được — **chính nó vừa giấu lỗi ở việc 1 suốt nhiều tuần**.

## Thiết kế đã chốt

Thêm `RiskManager.last_reject_reason: str | None`. Mỗi đường từ chối đặt một
chuỗi ngắn, cụ thể, **có số**:

- `"halt lỗ ngày"` 
- `"ATR không hợp lệ (atr=None hoặc <=0)"`
- `"qty sau cap < 1 lô (qty_atr=X, qty_cap=Y)"`
- `"đã đủ max_positions (N)"`
- ... (đặt tên theo đúng nhánh, kèm con số thực tế)

Mỗi lần duyệt **thành công** phải đặt lại `None` — không để lý do cũ vương lại
gây hiểu nhầm.

Vì sao dùng thuộc tính chứ không đổi kiểu trả về: `approve_sized` có 2 caller
sản xuất và `approve` có thêm caller ở đường tiền; đổi chữ ký làm blast radius
phình ra không cần thiết. Thuộc tính giữ chữ ký nguyên vẹn.

**KHÔNG** import `alert` vào `risk.py` — giữ `risk.py` thuần logic, không phụ
thuộc hạ tầng cảnh báo. Việc ghi log là của caller.

## Caller ghi log

- `trading/engine/logic.py`: khi `approve_sized` trả `None` mà có signal →
  `alert("INFO", ...)` kèm `risk.last_reject_reason`, symbol, side.
- `trading/real_orders.py`: khi `approve()` trả `False` → tương tự.

Mức **INFO**, không phải WARN: từ chối là chuyện bình thường (halt, đủ vị
thế...). WARN cho việc bình thường sẽ tạo mỏi cảnh báo, đúng cái bẫy NOISE-1 đã
sửa ở `1e801ec`.

---

# VIỆC 3 — backtest lại sau khi sửa

Chạy `python -m trading.backtest` (cần nạp `.env` cho `load_config`):

```
--strategy sma_cross --tf 5m --from 2026-04-03 --to 2026-08-07
```

Bốn lần chạy, dán **nguyên văn** output:

| # | symbols | capital |
|---|---|---|
| 1 | HII,IJC,AAA | 5021459 |
| 2 | HII,IJC,AAA | 1000000000 |
| 3 | VCB,HPG,TCB | 5021459 |
| 4 | VCB,HPG,TCB | 1000000000 |

## ĐIỀU TUYỆT ĐỐI KHÔNG ĐƯỢC LÀM

**KHÔNG chỉnh bất kỳ tham số nào để kết quả đẹp hơn.** Không đổi
`atr_pct_threshold`, `risk_pct`, `atr_multiplier`, `fast`, `slow`,
`sl_multiplier`, khung thời gian, hay khoảng ngày.

Nếu backtest cho thấy chiến lược **thua lỗ**, đó là kết quả đúng và phải báo
nguyên vẹn. Mục tiêu của việc này là **biết sự thật**, không phải tạo ra một
con số dễ nhìn. Một chiến lược lỗ mà ta biết là lỗ thì an toàn hơn một chiến
lược lỗ được tinh chỉnh cho tới khi đường cong quá khứ đẹp.

---

# Ràng buộc

- Sửa: `trading/risk.py`, `trading/engine/logic.py`, `trading/real_orders.py`,
  và test tương ứng.
- **KHÔNG** sửa `trading/strategies/sma_cross.py`, `config/config.yaml`,
  `trading/backtest.py` (chỉ chạy, không sửa).
- **KHÔNG** bật `real_trading_enabled`.

# Kiểm chứng (dán output THẬT)

1. **Test cốt lõi:** ATR/giá = 1% (dưới ngưỡng 2,5% cũ) → BUY **được duyệt**,
   `qty` là bội của 100, và `ref_price * qty <= capital * 0,20`.
   → **RED bắt buộc:** khôi phục logic cũ (bỏ `qty_cap`) → test FAIL.
2. **Không được giao dịch to hơn mức ATR cho phép:** ATR rất nhỏ khiến
   `qty_atr` lớn → `qty` phải bằng `qty_cap`; ATR lớn khiến `qty_atr` nhỏ →
   `qty` phải bằng `qty_atr`. Hai chiều, hai test.
3. **Vẫn từ chối khi đúng phải từ chối:** giá cao tới mức 1 lô đã vượt trần →
   `None`, và `last_reject_reason` nêu rõ cả `qty_atr` lẫn `qty_cap`.
4. **Mỗi nhánh từ chối đặt đúng lý do**, và duyệt thành công **xoá** lý do cũ.
5. Bốn backtest ở việc 3.
6. `uv run pytest -q` (≥ 268 + test mới) + `uv run ruff check trading tests`.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Đặc biệt việc 1: nếu bạn cho rằng `min(qty_atr, qty_cap)`
phá vỡ ý nghĩa của ATR sizing (rủi ro mỗi lệnh không còn hằng số), **nói ra** —
đó là đánh đổi thật và chủ dự án cần biết trước khi tiền thật đi qua đường này.
