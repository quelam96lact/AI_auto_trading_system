# Brief đợt 96 — Vị thế khôi phục sau restart không bao giờ bán được, và cắt lỗ im lặng

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `3ba1498`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.
Làm được ngay cuối tuần. **Không** restart/build container. Việc dựng lại image do Claude làm **sau** khi commit.

---

## 0. Bối cảnh: chủ dự án chọn "go-live kỹ thuật cỡ nhỏ"

Mục tiêu là chạy thông đường lệnh thật với cỡ nhỏ, **chấp nhận lỗ nhỏ**, để kiểm đường ống. Mục tiêu **không phải** kiếm lời. Chiến lược đang chạy đã được đo là lỗ (đợt 11: PF 0,47 trên 310 mã, nến 5 phút). Brief này **không** sửa chiến lược.

Điều kiện để go-live kỹ thuật an toàn: **mọi vị thế phải thoát được khi chạm stop.** Hiện tại điều đó **sai**, và sai **im lặng**.

---

## 1. Lỗi đã được Claude tái hiện

**Hiện tượng:** engine paper giữ IJC 400 (mua 03/09 giá 7.354) và AAA 400 (mua 03/09) suốt **23 ngày**. IJC hiện 6.720, tức **−8,6%**. Mức trailing stop chỉ cách đỉnh khoảng 2×ATR 5 phút (≈0,44%), nên IJC đã chạm stop từ lâu. Không có lệnh bán nào, và không có cảnh báo nào. Trình kiểm "engine câm" vẫn báo `[OK]`.

**Nguyên nhân (đọc code và chạy thật):**

1. `PaperBroker.restore()` (`trading/paper_broker.py:189-212`) không biết ngày mua. Nó coi vị thế khôi phục như mua ở `day_index=0`, tức **ngày giao dịch đầu tiên sau khi khởi động lại**.
2. `_trade_days` chỉ nằm trong bộ nhớ. Muốn bán cần `today - 0 >= settle_days (3)`, tức **một tiến trình phải sống liền ≥ 3 ngày giao dịch**.
3. Engine đã khởi động lại **11 lần trong 7 ngày** (19/09 → 25/09, theo `logs/engine_alerts.log`, dòng "engine restored state"), nên điều kiện ở mục 2 **không bao giờ đạt**.
4. Khi chạm stop, `force_exit` trả `qty=0`. `logic.py:61-62` **cố ý không cảnh báo** ("tránh nhiễu"). Kết quả là stop chạm mỗi ngày, không bán được, và không ai biết.

**Tái hiện của Claude** (`PaperBroker.restore` với IJC 400, mỗi ngày một tiến trình mới):

```
22/09 (tiến trình mới): force_exit qty = 0
23/09 (tiến trình mới): force_exit qty = 0
24/09 (tiến trình mới): force_exit qty = 0
25/09 (tiến trình mới): force_exit qty = 0
đối chứng, 1 tiến trình sống liền 22→25/09: 25/09 sellable = 400
```

**Vì sao chặn go-live kỹ thuật:** đường lệnh **thật** dùng `sellable_qty` của SSI (`real_orders.py:306`) nên không dính lỗi này. Nhưng paper là nơi ta quan sát hành vi trước khi bật tiền thật. Một paper book bị đóng băng không cho biết gì. Ngoài ra, lớp "chạm stop mà không bán được thì im lặng" cũng là thứ không được phép tồn tại ở đường thật.

---

## 2. Trước khi sửa

Chạy GitNexus và **dán kết quả**:
- `gitnexus_impact({target: "restore", direction: "upstream"})` (`PaperBroker.restore`)
- `gitnexus_impact({target: "process_bar", direction: "upstream"})`
- `gitnexus_impact({target: "run", direction: "upstream"})` (`trading/engine/main.py`)

Nếu có HIGH hoặc CRITICAL: **dừng, báo cáo**, không sửa.

---

## Task 1 — Vị thế khôi phục phải tính T+ theo **ngày mua thật**

**Được sửa:** `trading/paper_broker.py`, `trading/storage/db.py` (**chỉ thêm** 1 hàm), `trading/engine/main.py` (**chỉ** chỗ gọi `PaperBroker.restore`), và test.
**Không được sửa:** `real_orders.py`, `trailing_stop.py`, `backtest.py`, chiến lược, mọi file khác.

### 1a. Hàm đọc ngày mua — `trading/storage/db.py`

Thêm `read_last_buy_date(symbol) -> date | None`: ngày (giờ VN) của BUY fill **gần nhất** trong bảng `orders`.

- **Bắt buộc** `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`. **Cấm** `ts::date` hay `date(ts)`: cái bẫy múi giờ này đã cắn repo này **4 lần**.
- Dùng lệnh BUY **gần nhất** là **bảo thủ**: nếu mua nhiều lần, lấy lần muộn nhất thì không bao giờ bán sớm hơn luật cho phép.
- Không có BUY nào thì trả `None`.

### 1b. `PaperBroker.restore` nhận ngày mua

Thêm hai tham số **có mặc định**: `buy_dates: dict[str, date] | None = None` và `holidays: frozenset = frozenset()`. Khi không truyền, hành vi phải **giống hệt hiện tại** (backtest và mọi chỗ gọi khác không đổi).

Quy tắc, **không tự đổi**:
- Ngày giao dịch đầu tiên sau khi khởi động (bar đầu tiên, ngày `T`) chưa biết lúc `restore`. Vì vậy lô có `buy_date` phải được **quy đổi lười**: lần đầu `_day_index` thêm ngày `T` vào `_trade_days`, đặt `day_index` của lô = `-k`, với `k` = **số ngày giao dịch `d` thỏa `buy_date < d <= T`**. Đếm bằng `trading.calendar_vn.is_trading_day(d, holidays)`, **không** viết lại hàm đếm ngày.
- Claude đã kiểm: warm-up **không** đi qua broker, nó chỉ gọi `strategy.compute_crossover` (`main.py:250`). Vì vậy lần đầu `_day_index` được gọi luôn là một **bar sống**, và `T` đúng là ngày giao dịch thật.
- Kiểm tra: mua ngày D, `settle_days=3` → bán được đúng từ ngày giao dịch thứ 3 sau D. Đây chính là ngữ nghĩa đang có khi tiến trình sống liền.
- Lô **không có** `buy_date` (không tìm thấy BUY) thì giữ hành vi hiện tại (`day_index=0`).

### 1c. `main.py` truyền ngày mua

Tại chỗ gọi `PaperBroker.restore` (`main.py:186`): với mỗi vị thế `qty > 0`, gọi `storage.read_last_buy_date(sym)`, rồi truyền `buy_dates` và `cfg.holidays`.
- Mã nào **không có** ngày mua: `alert("WARN", ...)` nêu rõ mã, và nói rằng vị thế sẽ bị khóa 3 ngày giao dịch theo cách bảo thủ. **Không được im lặng.** Làm theo khuôn WARN của RESTORE-1 ngay bên dưới (`main.py:263-275`).

### Test Task 1 (viết trước, thấy đỏ, rồi mới sửa)

1. **Tái hiện lỗi:** restore IJC với `buy_dates={"IJC": date(2026,9,3)}`; bar đầu tiên ngày 22/09 → `force_exit` bán được **400**. (Trên code cũ phải ra 0.)
2. **Biên T+:** mua thứ Năm 17/09. Bar đầu tiên thứ Hai 21/09 (k=2) → **0**. Bar đầu tiên thứ Ba 22/09 (k=3) → **400**. Ghi phép đếm ngày trong docstring.
3. **Ngày lễ được đếm đúng:** mua 17/09, `holidays={date(2026,9,21)}`, bar đầu tiên 22/09 → k=2 → **0**.
4. **Không có ngày mua:** hành vi cũ (`day_index=0`), bán được sau 3 ngày giao dịch trong cùng tiến trình.
5. **Không truyền gì:** `PaperBroker.restore(cap, cash, pnl, positions)` cho kết quả giống hệt trước khi sửa.
6. `read_last_buy_date` là test integration, chạy trên DB test (`trading_test`), gắn nhãn `integration` như các test DB khác. Phải có một ca **BUY lúc 00:30 giờ VN**, tức UTC còn là ngày hôm trước. Hàm phải trả **ngày VN**. Ca này bắt đúng cái bẫy múi giờ.

---

## Task 2 — Chạm stop mà không bán được thì **phải kêu**, một lần mỗi ngày

**Được sửa:** `trading/engine/logic.py` (nhánh `forced.qty == 0`, dòng 61-62) và test.

Hiện tại nhánh này im lặng để tránh "mỗi bar chạm là một cảnh báo". Lo đó đúng, nhưng cách giải là **khử trùng lặp**, không phải im lặng.
- Khi `forced.qty == 0`: `alert("WARN", ...)` nêu mã, giá stop, và lý do "chưa settle T+2,5". **Chỉ một lần mỗi mã mỗi ngày.** Theo dõi trong `day_state`: nó đã có và đã reset theo ngày ở `logic.py:31-33`. Thêm một tập, ví dụ `day_state["stop_blocked_alerted"]`, và reset cùng chỗ.
- Câu chữ theo khuôn của đường thật (`real_orders.py:308-313`) để hai đường nói cùng một ngôn ngữ.

### Test Task 2

1. Chạm stop khi chưa settle, 5 bar liên tiếp cùng ngày → **đúng 1** WARN.
2. Sang ngày mới, vẫn chạm, vẫn chưa settle → thêm **đúng 1** WARN.
3. Chạm stop khi **đã** settle → bán, **không** có WARN "chưa bán được".

Dùng cách bắt `alert` đang có trong các test của `logic.py`. Tìm trong `tests/` trước; không tự chế cơ chế mới.

---

## 3. Kiểm thử phá hoại (bắt buộc)

Sao lưu file ra **ngoài repo** trước. **Cấm** `git checkout`, `git restore`, `git stash`.
1. Cho `restore` bỏ qua `buy_dates` → test Task 1 số 1 và 2 phải đỏ.
2. Đổi phép đếm thành `buy_date <= d <= T` (sai một ngày) → test biên số 2 phải đỏ.
3. Bỏ khử trùng lặp → test Task 2 số 1 phải đỏ.
4. Khôi phục, chạy lại, sạch.

Báo cáo tên các test đỏ ở mỗi bước.

---

## 4. Kiểm chứng tổng

```
uv run pytest -m "not integration" -q     # mốc hiện tại: 868 passed
uv run ruff check trading tests scripts
```

Chạy thêm test integration của `read_last_buy_date` trên DB test (`docker compose --profile test up -d nats-test` nếu cần, xem `CLAUDE.md`). **Không** chạm DB thật.

Sau khi sửa: `gitnexus_detect_changes()`, dán kết quả.

---

## 5. Báo cáo cho Claude

1. Kết quả GitNexus impact và detect_changes.
2. Diff của từng file.
3. Danh sách test mới; kiểm thử phá hoại (tên test đỏ từng bước).
4. Dòng tổng kết pytest và ruff, cùng kết quả test integration.
5. **Dự báo, không làm:** với code mới, bar đầu tiên thứ Hai 28/09, IJC và AAA có bán được không? IJC có chạm stop không? Tính bằng dữ liệu thật trong `bars` và `orders`, chỉ **đọc**. Paper sẽ ghi nhận một khoản lỗ thật, và Claude cần biết trước để không nhầm là sự cố.
6. Mọi điều thấy ngoài phạm vi: **báo cáo, không sửa.**

---

## 6. Việc KHÔNG giao (ghi để khỏi hỏi lại)

- **Dựng lại image** (cổng go-live đang chặn ở tiêu chí 8 vì image cũ hơn commit đợt 95): Claude làm **sau** khi commit đợt này. Dựng trước thì lại lệch ngay.
- **Chiến lược:** chốt lời ≈2×ATR 5 phút (0,44–0,66%) **nhỏ hơn** phí khứ hồi cổ phiếu 0,60%. Trailing stop ở đường thật cũng chỉ cách đỉnh chừng đó, nên sẽ kích hoạt vì nhiễu. Với go-live kỹ thuật, chủ dự án đã chấp nhận lỗ nhỏ. **Không** sửa tham số, vì sửa mà không đo là tự lừa mình.
- **T3/T4 (đặt và hủy lệnh thật):** việc của chủ dự án, cần phiên sống. Mọi lệnh thật đều qua `scripts/confirm_real_order.py`, người vận hành phải gõ YES trong 15 phút.
- **Cùng loại lỗi "mất trạng thái khi restart", ở chỗ khác:** `OctopusPullbackStrategy._tp` (`octopus_pullback.py:218-223`) là dict chỉ nằm trong bộ nhớ, tính từ `bar.open` của **bar đầu tiên sau restart**, không phải giá vào lệnh. Mỗi lần restart, mức chốt lời bị neo lại theo giá hôm đó. Chưa giao, vì hai lý do: sửa cần cho `Context` biết giá vốn (đổi giao diện chiến lược, ngoài phạm vi), và vị thế vẫn thoát được qua trailing stop nên không bị kẹt. Nếu sau này dùng lại chiến lược có chốt lời thì phải sửa trước.
- **Vì sao engine khởi động lại 11 lần trong 7 ngày:** chưa điều tra. Brief này làm cho restart **vô hại**, không làm nó **ít đi**.
