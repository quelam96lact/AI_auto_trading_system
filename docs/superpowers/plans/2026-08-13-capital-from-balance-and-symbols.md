# Kế hoạch: vốn đặt lệnh đọc từ số dư thật + đổi rổ mã sang HII/IJC/AAA

Ngày giao: 2026-08-13 tối. Nhánh: `feature/data-layer`. Base: `edaf026`.

**KHÔNG commit, KHÔNG push.** `gitnexus_detect_changes` khi xong.

Hai quyết định của chủ dự án hôm nay:
1. `real_order_capital` **bỏ hẳn khỏi config**, engine đọc **số dư thật**.
2. Rổ mã đổi từ `[VCB, HPG, TCB]` sang **`[HII, IJC, AAA]`**.

---

## CẢNH BÁO BẮT BUỘC ĐỌC TRƯỚC

`gitnexus_impact` trên `Class:trading/config.py:Config`: **HIGH** — 15 file
import trực tiếp. Đã đối chiếu bằng grep: chỉ `trading/engine/main.py` thật sự
**đọc** `real_order_capital`; 14 file còn lại chỉ import kiểu `Config`. Đường
đặt lệnh thật (`scripts/confirm_real_order.py`) **không** dùng capital — nó
kiểm tra sức mua trực tiếp qua `get_max_buy_sell_at_market_price` tại thời điểm
xác nhận. Đã grep để chắc.

**Thay đổi này gỡ bỏ một lớp khoá an toàn** mà chủ dự án cố ý dựng lên sáng
13/08 (ghi trong `GO_LIVE_AUDIT.md`). Sau đây hệ thống tự động dùng bất kỳ số
tiền nào có trong tài khoản. Lớp khoá còn lại chỉ là `real_trading_enabled:
false`. Chủ dự án đã được cảnh báo và vẫn chọn phương án này — ghi lại để người
sau không tưởng là sót.

---

# VIỆC A — vốn đặt lệnh đọc từ số dư thật

## A1. `Storage.read_account_balance(account_no)`

Trả về dòng **mới nhất** của `account_balance_snapshot` cho tài khoản đó:
`(withdrawable, ts)` hoặc `None` nếu chưa có dòng nào.

Dùng **`withdrawable`**, không dùng `account_balance`. Lý do: đó là tiền thật
sự dùng được — `account_balance` có thể bao gồm phần đang bị giữ. Hôm nay hai
số bằng nhau ở cả hai tài khoản, nhưng chúng **có thể lệch** (xem `0434226`:
`holdSubscription = 2.500.000`). Chọn số bảo thủ hơn.

Method mới → không caller cũ nào bị ảnh hưởng.

## A2. `engine/main.py` — thay `cfg.real_order_capital`

```
real_risk = RiskManager(capital=<số dư đọc được>)
```

Ba nhánh, **không nhánh nào được im lặng**:

| Tình huống | Xử lý |
|---|---|
| Không có dòng nào | `capital = 0` + `alert("CRITICAL", ...)` nêu rõ tài khoản. `capital=0` khiến `approve()` từ chối mọi lệnh — **fail-safe**, không được rơi về một giá trị dễ dãi |
| Có nhưng cũ hơn 24 giờ | **Vẫn dùng**, nhưng `alert("WARN", ...)` kèm tuổi của dữ liệu |
| Bình thường | `alert("INFO", ...)` nêu rõ **số tiền** và **mốc thời gian** |

Nhánh INFO không phải trang trí: người vận hành phải nhìn được hệ thống đang
tính rủi ro trên con số nào. Một hệ thống đặt lệnh bằng tiền thật mà không nói
nó nghĩ mình có bao nhiêu tiền là không chấp nhận được.

## A3. GUARD-1 dùng số dư thật

Khối cảnh báo `CRITICAL` "duong dat lenh that INERT" (`engine/main.py:~149`)
hiện tính `cfg.real_order_capital * max_order_value_pct`. Đổi sang dùng chính
số dư vừa đọc. Guard này **có ý nghĩa hơn** sau thay đổi, không kém đi.

Comment ở đó đang giải thích chuyện "chủ dự án cố ý giữ capital=21459 để khoá"
— chuyện đó **không còn đúng**. Viết lại comment cho khớp thực tế.

## A4. Bỏ `real_order_capital` khỏi `Config`

- `trading/config.py:26` (field) và `:51` (đọc từ YAML)
- `config/config.yaml:8`

## A5. Cập nhật test

Cơ học ở hầu hết chỗ (bỏ tham số). **Trừ nhóm GUARD-1** trong
`tests/test_engine_main.py` (dòng ~518-601): chúng đang truyền
`make_cfg(real_order_capital=...)` để điều khiển guard. Sau thay đổi, guard đọc
DB — nên các test đó phải **seed `account_balance_snapshot`** thay vì truyền
tham số. Đây là viết lại thật, không phải đổi tên.

`tests/test_config.py:21,36` assert `real_order_capital == 21459` → bỏ.

## Kiểm chứng việc A (dán output THẬT)

1. Seed `account_balance_snapshot` = 5.021.459 → engine khởi động → `INFO` nêu
   đúng số tiền + mốc thời gian; `RiskManager` nhận đúng số đó.
2. **Không có dòng nào** → `CRITICAL` + `capital = 0` → một lệnh BUY bất kỳ bị
   `approve()` từ chối.
   → **RED bắt buộc:** đổi nhánh fallback thành một số dễ dãi (vd giữ nguyên
   1 tỷ) → test này phải FAIL. Khôi phục → PASS. Lý do bắt buộc: "fail-safe"
   là khẳng định một sự **vắng mặt** (không có lệnh nào lọt), rất dễ pass rỗng.
3. Dữ liệu cũ hơn 24h → **vẫn chạy** nhưng có `WARN` kèm tuổi.
4. GUARD-1: số dư nhỏ + `real_trading_enabled=True` → `CRITICAL` INERT.
   Số dư nhỏ + `real_trading_enabled=False` → **im lặng**.
   → **RED bắt buộc:** thay điều kiện `if cfg.real_trading_enabled:` bằng
   `if True:` → test im lặng phải FAIL. (Bước này đã cứu một lần ở `1e801ec`.)

---

# VIỆC B — đổi rổ mã sang HII, IJC, AAA

`config/config.yaml:1`: `symbols: [HII, IJC, AAA]`

## Vì sao ba mã này (số đo, không phải cảm tính)

Trần lệnh = số dư × `max_order_value_pct` = `5.021.459 × 0,20 = 1.004.292đ`.
Một lô = 100 cp → **giá phải ≤ ~10.042đ/cp**.

| Mã | Giá (07/08) | 1 lô | Thanh khoản | Biên an toàn |
|---|---|---|---|---|
| HII | 8.600 | 860.000 | 13,6 tỷ/ngày | 14% |
| IJC | 7.420 | 742.000 | 11,7 tỷ/ngày | 26% |
| AAA | 7.150 | 715.000 | 9,2 tỷ/ngày | 29% |

VCB/HPG/TCB đều vượt trần (2,17–5,95 triệu/lô). **VSC cũng vượt** (14.650 →
1.465.000/lô) — chủ dự án nêu VSC làm ví dụ nhưng số liệu cho thấy nó không lọt.

Các mã sát trần (HHS 9.750, VFS 9.700) bị loại có chủ đích: giá nhích lên vài
phần trăm là lệnh bị từ chối, và bị từ chối **im lặng**.

## KHÔNG được làm trong việc B

- **KHÔNG** sửa `grafana/provisioning/dashboards/trading.json`. Panel "Giá
  (VCB)" hardcode `WHERE symbol = 'VCB'` (dòng 8, 14) nên sẽ đứng hình sau thay
  đổi. **Báo cáo, đừng tự sửa** — chủ dự án quyết muốn panel theo mã nào, hay
  tham số hoá.
- **KHÔNG** xoá dữ liệu `bars` của VCB/HPG/TCB. Giữ nguyên.
- **KHÔNG** đụng `scripts/record_fixtures.py`, `scripts/spike_ssi_*.py` (có
  hardcode VCB nhưng là công cụ một lần, không ảnh hưởng vận hành).

## Điều PHẢI ghi vào báo cáo, không phải bug

Bar của HII/IJC/AAA trong DB hiện cũ từ **07/08**. Khi collector khởi động lại
với rổ mã mới, `run_backfill` sẽ lấp 08/08→13/08 cho chúng. Nhưng **engine và
collector khởi động độc lập** — nếu engine warm-up trước khi backfill xong, nó
dựng SMA trên dữ liệu 6 ngày trước.

Không phải bug (SMA 20 phiên vốn không đòi hỏi liên tục theo lịch — cuối tuần
tạo khoảng trống mỗi tuần), nhưng nghĩa là **bar sống đầu tiên có thể tạo
crossover ngay**. Với `real_trading_enabled: false` thì vô hại và quan sát
được.

**Ghi rõ trong báo cáo** rằng thứ tự khởi động đúng là: collector trước (chờ
`backfill done`), engine sau.

---

# Ràng buộc chung

- Sửa: `trading/config.py`, `trading/engine/main.py`, `trading/storage/db.py`,
  `config/config.yaml`, và các file test bị ảnh hưởng.
- **KHÔNG** sửa `scripts/confirm_real_order.py`, `trading/real_orders.py`,
  `trading/risk.py` — đường tiền không nằm trong phạm vi việc này.
- **KHÔNG** bật `real_trading_enabled`. Nó phải giữ nguyên `false`.

# Toàn bộ

- `uv run pytest -q` → ≥ 265 (một số test đổi, tổng có thể xê dịch — nêu rõ).
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán risk + danh sách file.

# Nếu thấy kế hoạch sai

Dừng và phản biện trước khi viết code. Đặc biệt A2: nếu bạn cho rằng fallback
`capital = 0` khi không đọc được số dư là quá khắt khe (vd engine khởi động
trước lần sync đầu tiên trong ngày sẽ bị chặn), **nói ra** — đó là đánh đổi
thật và tôi có thể đã chọn sai.
