# Brief cho Hermes — 2026-08-18

Base: `main` = `16518be`, working tree sạch, đã push. Không có nhánh nào khác.

Ba việc, làm theo thứ tự **C → B → A** (vặt trước, nặng sau — để nếu hết giờ thì
phần dở dang nằm ở việc tôi audit kỹ nhất).

Trước khi gõ dòng đầu tiên: chạy `gitnexus_context`/`gitnexus_impact` trên
`Storage.read_account_balance` và `trading/engine/main.py` — cả hai đều có
caller thật. Chạy `gitnexus_detect_changes` trước khi báo cáo xong.

---

## Task C — comment sai trong test (vặt, làm trước cho nóng máy)

`tests/test_derivative_backtest.py:475-484`, hàm
`test_real_captured_ohlc_sample_runs_end_to_end`.

Comment ghi *"File nay gitignored (du lieu that), khong commit - skip gon neu
khong co san thay vi fail."* — **không còn đúng**. Commit `cc8048e` (2026-08-18)
đã đưa `scripts/.spike_derivative_ohlc_5m_2m_sample.json` vào repo và gỡ dòng
tương ứng khỏi `.gitignore`. File giờ luôn tồn tại, nhánh `pytest.skip` là code
chết và comment nói ngược với thực tế.

Việc: sửa comment cho đúng hiện trạng, bỏ nhánh skip chết.

**Đừng** đụng phần thân test phía sau (logic dựng `Bar`, chạy backtest) — chỉ
phần đầu hàm.

Kiểm chứng: `uv run pytest tests/test_derivative_backtest.py -q` vẫn xanh, và
`uv run pytest -m "not integration" -q` vẫn ra **287 passed, 82 deselected**
(số này không được đổi — task C không thêm/bớt test nào).

---

## Task B — 7 file integration test chưa từng chạy trên CI

Hiện `.github/workflows/ci.yml` chạy `pytest -m "not integration"`. 7 file test
integration **chưa từng chạy ở đâu ngoài máy dev**.

Việc: thêm một job vào workflow chạy phần integration, dùng `services:` của
GitHub Actions.

Dữ kiện đã xác minh, dùng thẳng, đừng đoán lại:

- Postgres: `docker-compose.yml:3` dùng `timescale/timescaledb:latest-pg16`,
  user/pass/db = `trading`/`trading`/`trading`. Test **không** dùng DB đó — xem dưới.
- `tests/conftest.py:18-21`:
  - `TEST_DB_DSN`, mặc định `postgresql://trading:trading@127.0.0.1:5432/trading_test`
  - `TEST_NATS_URL`, mặc định `nats://127.0.0.1:4223`
- `conftest.py:27-29` **chặn cứng**: nếu tên DB không kết thúc bằng `_test` thì
  test tự từ chối chạy. Đừng tìm cách lách — đó là chốt chặn chống ghi đè DB thật.
- `conftest.py:52-66` tự tạo database `trading_test` + init schema nếu chưa có,
  bằng cách connect vào `/postgres` trên cùng instance. Nghĩa là service Postgres
  chỉ cần lên là đủ, không cần seed sẵn.
- NATS: `docker-compose.yml:32-36` dùng `nats:2.10-alpine`, lệnh `["-js", "-sd", "/data"]`
  (**bắt buộc `-js`** — JetStream; thiếu cờ này test sẽ chết khó hiểu).
  Trong compose nó map `4223:4222`; trên CI bạn tự chọn cổng, chỉ cần
  `TEST_NATS_URL` trỏ đúng.

Ràng buộc: **không được đổi `conftest.py`** để làm CI dễ xanh. Nếu test
integration bộc lộ lỗi thật, **báo cáo, đừng tự sửa** — đó là phát hiện có giá
trị, không phải chướng ngại.

Kiểm chứng: dán output CI thật (job xanh, số test integration đã chạy). Job cũ
(`not integration`) phải vẫn xanh và vẫn 287 passed.

---

## Task A — nối NAV làm vốn rủi ro (việc chính)

### Bối cảnh (đã xác minh hôm nay, tin được)

Bảng `account_nav_snapshot` **được ghi nhưng chưa ai đọc**:

- Schema: `trading/storage/*.sql:227-233` — `(account_no, ts, nav, unpriced_symbols text[])`,
  PK `(account_no, ts)`.
- Ghi: `Storage.record_nav` (`db.py:743`), gọi từ
  `trading/collector/account_sync.py:144` — collector ghi theo lịch, dữ liệu có thật.
- Đọc: **không có hàm nào**. Danh sách `read_*` trong `db.py` có
  `read_account_balance`, `read_buying_power`, `read_real_daily_pnl`… không có NAV.

Vì thế `engine/main.py:125` vẫn phải lấy vốn rủi ro từ
`read_account_balance()` = **tiền mặt rút được**. Chủ dự án đã quyết từ
2026-08-14: **vốn rủi ro = NAV** (1% rủi ro/lệnh phải là 1% của thứ mình thực sự
sở hữu, không phải 1% của thứ mình vay được).

### Việc

1. Thêm hàm đọc NAV vào `Storage`, đặt cạnh `read_account_balance` (`db.py:205`)
   và theo đúng style của nó. Trả về đủ ba thứ engine cần: `nav`, `ts`, và
   `unpriced_symbols` — **không được bỏ `unpriced`** (lý do ở mục dưới).
   Không có dòng nào → trả `None`, giống `read_account_balance`.

2. `engine/main.py:125-153`: đổi nguồn `real_capital` sang NAV, **giữ nguyên cả
   ba nhánh fail-safe của CAP-1**, không được rút gọn nhánh nào:
   - không đọc được → `real_capital = 0.0` + `CRITICAL` (fail-safe: `approve()`
     từ chối MỌI lệnh; **không được** rơi về `read_account_balance` cho "đỡ gắt")
   - cũ hơn 24h → vẫn dùng + `WARN` kèm tuổi
   - bình thường → `INFO` nêu số tiền + mốc thời gian
   - **thêm nhánh thứ tư**: `unpriced_symbols` không rỗng → `WARN` nêu rõ mã nào.
     Lý do phải cảnh báo mà vẫn dùng: `account_sync.py:122-126` tính mã không
     định giá được **thành 0**, nên NAV bị **tính hụt**. Hụt là an toàn (vốn rủi
     ro nhỏ hơn thực tế → đặt lệnh nhỏ hơn), nên vẫn dùng được; nhưng im lặng thì
     không chấp nhận được. Thực tế `0434226` có `unpriced: ['MIRHCM261']` (chứng
     quyền, không có dữ liệu giá) nên nhánh này sẽ chạy thật, không phải giả định.

3. Sửa hai comment giờ nói sai nguồn dữ liệu:
   - comment CAP-1 ngay trên dòng 125 (*"doc tu account_balance_snapshot"*)
   - comment GUARD-1 (`main.py:185-199`) cũng nhắc lại *"CAP-1: doc tu
     account_balance_snapshot"*

### Điều PHẢI hiểu trước khi sửa

`real_capital` chảy vào **hai** chỗ, đổi nguồn là đổi cả hai:
- `RiskManager(capital=real_capital)` (dòng 154) → quyết định **cỡ lệnh**
- `order_cap = real_capital * max_order_value_pct` trong GUARD-1 → quyết định
  cảnh báo "đường lệnh thật INERT"

Với tài khoản đang cấu hình `0434221`: NAV = withdrawable = **5.021.459** (bằng
nhau), nên hành vi thực tế gần như không đổi — đây là lý do làm lúc này an toàn.
Với `0434226`: capital nhảy từ **2.428.997** lên **197.222.417**, và GUARD-1 sẽ
thôi báo INERT. Đó chính là mục đích, không phải tác dụng phụ.

### TDD — bắt buộc, và phải phân biệt được

Viết test **ĐỎ trước**, dán output đỏ. Rồi làm xanh. Rồi **tự phá bản sửa** để
chứng minh test bắt được, dán cả output đỏ lần hai. Test không phân biệt được
thì coi như chưa có test.

Tối thiểu phải có test cho: đọc được NAV bình thường; không có dòng nào → capital
0 + CRITICAL; NAV cũ > 24h → WARN; `unpriced` không rỗng → WARN nêu đúng mã.

---

## RÀNG BUỘC — vi phạm là hỏng việc thật

- **KHÔNG commit, KHÔNG push.** Xong thì báo cáo, tôi audit rồi mới commit.
- **KHÔNG bật `real_trading_enabled`.** Nó đang `false` và phải giữ nguyên
  `false`. Task A làm cỡ lệnh thật lớn hơn — an toàn duy nhất hiện nay là cờ đó tắt.
- **KHÔNG sửa `config/config.yaml`.** Đặc biệt không đổi `real_order_account`
  từ `0434221` sang `0434226` — đó là thay đổi cấu hình nguy hiểm nhất repo này,
  và là quyết định của chủ dự án, không phải hệ quả của task A.
- **KHÔNG đụng**: `trading/real_orders.py`, `scripts/confirm_real_order.py`,
  `scripts/heartbeat_check.py` (dead-man's switch), `tests/conftest.py`.
- Postgres này **đang phục vụ collector + engine chạy thật**. Mọi truy vấn điều
  tra là READ-ONLY: không `INSERT`/`UPDATE`/`DELETE` lên bảng hệ thống, không đặt
  hay hủy lệnh. Test thì dùng `trading_test` như conftest đã ép.
- Token SSI đọc từ bảng `ssi_auth_state`. **Không xác thực OTP mới, không tạo
  credential mới.** Hết hạn thì DỪNG và báo cáo. Nếu có thao tác nào khiến SDK
  tự ghi đè token, **khai báo trong báo cáo** — đợt trước chuyện đó xảy ra và
  việc bạn chủ động khai là điều đúng, giữ nguyên thói quen đó.
- **Đừng chạy `ruff check --fix` theo wildcard.** Chỉ định đích danh file bạn
  đụng. `scripts/` giờ **nằm trong phạm vi lint** (commit `3191a8a`) và đang
  **sạch 0 lỗi** — con số đó phải giữ nguyên.
- Hook `pre-push` đã bật (`.githooks/pre-push`): nó chạy ruff + test trước mỗi
  push lên main. Bạn không push, nên không chạm tới, nhưng biết để khỏi ngạc nhiên.

## Kiểm chứng cuối (tất cả phải dán output THẬT, nguyên văn)

```
uv run ruff check trading tests scripts      # phải: All checks passed!
uv run pytest -m "not integration" -q        # phải: 287 + đúng số test bạn thêm
```

Task B thì thêm output job CI integration.

Báo cáo: dán output thật, đừng tóm tắt thành "pass". Việc nào không làm được thì
nói rõ vì sao — **đừng đoán bừa cho đủ**. Nếu phát hiện vấn đề ngoài phạm vi ba
task này, **báo cáo, đừng tự sửa**.
