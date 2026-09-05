# Brief giao việc — đợt 5 (Q, R, S)

Viết 05/09, sau `6b77245`. Thứ Bảy, không có phiên.

## 0. Trạng thái: đợt 4 chưa ai nhận

`2026-09-05-brief-giao-viec-dot-4.md` (viết sáng nay) đã đặc tả **gói Q** và
**gói R**. Từ lúc đó tới giờ repo không có commit nào chạm `trading/`,
`scripts/` hay `tests/` — nghĩa là **Q và R vẫn còn nguyên, giao được ngay**.

Đợt 5 **không viết lại** hai gói đó. Tài liệu này chỉ làm hai việc:

1. Thêm **gói S** — một cái chốt an toàn cho mục tồn đọng J, làm được **mà không
   cần** chủ dự án trả lời câu hỏi §1 của đợt 4.
2. Nói rõ thứ tự giao và chỗ ba gói có thể giẫm chân nhau.

**Luật chung — vai trò, an toàn, phạm vi phẫu thuật, luật đơn vị, nền test,
GitNexus — nằm ở §2 của brief đợt 4. Áp dụng nguyên văn, không nhắc lại ở đây.**

---

## 1. GÓI S — chốt an toàn cho mục J (test-only, không chạm `trading/`)

### 1.1 Vì sao gói này làm được ngay, dù J đang chờ quyết định

Mục J nói: `octopus_pullback` không bao giờ phát `"bear"`, mà
`real_orders.py:46,75` rẽ nhánh đúng theo `"bull"`/`"bear"`. Nên nếu ai đó bật
`real_trading_enabled` trong khi engine chạy octopus, hệ thống **đặt lệnh MUA
thật và không bao giờ đặt lệnh BÁN thật**.

**Sửa** J là quyết định thiết kế (nối đường thoát lệnh thật vào tín hiệu SELL
của `on_bar`, hay đổi chiến lược) — của chủ dự án. Nhưng **chặn** J thì không:
dù chọn hướng nào, việc "bật tiền thật trong khi chiến lược chỉ mua một chiều"
cũng phải nổ ngay ở test, chứ không phải nổ ngoài thị trường.

Hôm nay điều duy nhất ngăn tai nạn đó là **một dòng `false` trong config và trí
nhớ của con người**. Trí nhớ hết hạn. Test thì không.

### 1.2 Việc

Một file test mới: `tests/test_real_trading_guard.py`.

**Tách làm hai phần — phần thứ hai mới là phần quan trọng.**

**(a) Hàm thuần để kiểm được cả hai chiều.** Đừng viết thẳng một `assert` đọc
config. Viết một hàm nhỏ trong chính file test, đại ý:

```
def _vi_pham_J(real_trading_enabled: bool, phat_duoc_bear: bool) -> bool
```

rồi test nó với **cả bốn tổ hợp**. Như vậy chốt an toàn tự chứng minh được là nó
biết kêu — không cần sửa `config/config.yaml` để thử (và **cấm** sửa).

**(b) Phép dò `phat_duoc_bear`.** Cho chiến lược ăn một chuỗi bar tất định
(tăng đủ dài để qua `warmup_bars`, rồi giảm sâu), gọi `compute_crossover` từng
bar, ghi lại có lần nào trả `"bear"` không.

**(c) Chốt chống mục ruỗng — bắt buộc.** Chính phép dò ở (b) phải được ghim:

- chạy trên `SmaCrossStrategy` ⇒ **phải** ra `"bear"`;
- chạy trên `_default_strategy()` (octopus) ⇒ **phải không** ra `"bear"`.

Không có (c) thì một ngày nào đó chuỗi bar không còn sinh tín hiệu nữa, phép dò
lặng lẽ trả `False` cho mọi chiến lược, chốt an toàn thành đồ trang trí mà suite
vẫn xanh. Đây là kịch bản hỏng nguy hiểm nhất của cả gói — **(c) là tiêu chí
quan trọng hơn (a)**.

**(d) Chốt thật.** Lấy `real_trading_enabled` từ `config/config.yaml`, dò
`_default_strategy()`, rồi khẳng định không vi phạm. Thông điệp khi hỏng phải
nói ra mục J và hậu quả ("chỉ MUA thật, không BÁN thật"), đừng chỉ `assert False`.

**Đọc bằng `yaml.safe_load` trực tiếp, KHÔNG dùng `load_config`.** Đã thử:
`load_config('config/config.yaml')` không có biến môi trường thì ném
`KeyError: 'DB_DSN'` — nó còn đòi `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`,
`SSI_API_KEY`, `SSI_API_SECRET`, `SSI_PRIVATE_KEY` (`trading/config.py:40-48`).
`tests/test_config.py` lách bằng `monkeypatch`, nhưng gói S **không được đi
đường đó**: kéo cả một rổ tên biến bí mật vào một test chỉ cần đúng một giá trị
bool là thừa và tạo tiền lệ xấu. Khoá cần canh nằm ở **file config**, đọc thẳng
đúng khoá đó là đúng độ hạt.

### 1.3 Ràng buộc cứng

- **Không sửa `trading/` một dòng nào.** Kể cả `engine/main.py` (đang chờ §1 đợt
  4), kể cả `real_orders.py`.
- **Không sửa `config/config.yaml`** — kể cả tạm thời để thử chốt. Đó chính là
  lý do (a) tách hàm thuần ra.
- Không sửa `tests/test_strategy_conformance.py` — gói S dùng file riêng.
- Đường dẫn tới `config/config.yaml` phải suy từ vị trí file test
  (`Path(__file__).parent.parent`), **không** từ thư mục đang đứng — nếu không
  test chỉ xanh khi chạy từ gốc repo.
- Test phải chạy được **không cần Docker/DB/NATS và không cần biến môi trường
  nào**: nó nằm trong lượt `-m "not integration"`. Không `monkeypatch` biến bí
  mật — xem (d).

### 1.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Hàm thuần đúng cả 4 tổ hợp | dán output test |
| 2 | Phép dò không mục ruỗng | sma_cross ra `"bear"`, octopus không — dán output |
| 3 | Chốt thật xanh với config hiện tại | dán output |
| 4 | **Phá hoại có kiểm soát** | tạm cho phép dò trả `False` cho sma_cross (hoặc cho hàm thuần trả `False` cứng) ⇒ **phải đỏ**. Dán nguyên văn output đỏ, khôi phục, rồi `grep -rn "SABOTAGE" tests/` trả rỗng |
| 5 | Không hồi quy | 413+ unit (tuỳ số test viết) + 100 integration |
| 6 | Lint | `uv run ruff check trading tests scripts` sạch |

**Tiêu chí 4 áp cho cả hai chốt** — chốt (c) và chốt (d). Một chốt an toàn chưa
từng thấy đỏ là một chốt an toàn chưa được kiểm.

### 1.5 Phạm vi

- **Sửa:** chỉ `tests/test_real_trading_guard.py` (file mới).
- **Không đụng:** `trading/` toàn bộ, `config/`, `scripts/`, mọi file test khác.

---

## 2. Thứ tự giao và chỗ giẫm chân

| Gói | Sản phẩm | Chạm image? | Chạy song song được? |
|---|---|---|---|
| **Q** | `scripts/` (script mới) + `tests/` (file mới) | Không | Có |
| **R** | `docs/superpowers/research/` | Không | Có |
| **S** | `tests/test_real_trading_guard.py` | Không | Có |

Ba gói không dùng chung file nào — giao song song được. **Một điều kiện:** gói Q
phải đặt test của nó vào **file mới**, không nhét vào file của gói S.

Cả ba đều **không chạm `trading/`**, nên không gói nào bắt dựng lại image.

Nếu chỉ giao được một gói: **S trước**. Q và R sinh thêm hiểu biết; S bịt một
đường hỏng có thật liên quan tới tiền thật.

---

## 3. Vẫn là việc của chủ dự án, không giao agent

Không đổi so với §6 đợt 4: **§1** (giữ octopus hay không), **J** (hướng sửa —
gói S chỉ *chặn*, không *sửa*), **K**, **F**, **C3**, **E**, **C1**, **C2**,
**D1** (cần phiên thật, sớm nhất thứ Hai 07/09).

---

## 4. Việc của Claude

Image vẫn cũ hơn commit gần nhất chạm `trading/` (`bb8d340`, gói L). Ba gói đợt
5 không làm thay đổi điều đó. Vẫn nên chờ trả lời §1 đợt 4 rồi dựng một lần.
