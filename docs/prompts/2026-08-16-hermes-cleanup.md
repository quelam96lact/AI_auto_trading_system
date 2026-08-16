# Giao Hermes — 3 việc tồn (2026-08-16)

Ba việc độc lập nhau, làm theo thứ tự A → B → C. B là việc thật (sửa một sai
lệch đang có), A là dọn dẹp, C là điều tra read-only.

## Ràng buộc chung — đọc trước khi gõ dòng code đầu tiên

- **KHÔNG commit, KHÔNG push.** Làm xong báo cáo lại, Claude audit rồi mới commit.
- **KHÔNG đụng:** `trading/engine/`, `trading/real_orders.py`,
  `scripts/confirm_real_order.py`, `config/config.yaml`,
  `scripts/heartbeat_check.py` (đây là dead-man's switch, chủ dự án loại trừ
  khỏi đợt này).
- **Postgres này đang phục vụ collector + engine chạy thật.** Mọi truy vấn
  trong task C là READ-ONLY: không `INSERT`/`UPDATE`/`DELETE` trên bảng hệ thống.
- **KHÔNG bật `real_trading_enabled`.** KHÔNG xác thực OTP mới, không tạo
  credential mới. Token SSI đọc từ bảng `ssi_auth_state`; nếu hết hạn thì DỪNG
  và báo cáo, không tự làm mới.
- Chạy `gitnexus_impact({target: "<symbol>", direction: "upstream"})` trước khi
  sửa bất kỳ hàm nào; `gitnexus_detect_changes()` sau khi sửa xong.
- Giữ nguyên style hiện có. Chỉ xóa import/biến mà chính thay đổi của bạn làm
  thừa ra. Thấy vấn đề ngoài phạm vi thì **báo cáo**, đừng tự sửa.
- Ruff hiện có đúng **8 lỗi pre-existing** trong `scripts/`. Đừng chạy
  `ruff check --fix scripts/*.py` — nó sẽ lan sang file ngoài phạm vi. Chỉ fix
  file bạn đụng, và chỉ định đích danh file đó.

---

## Task A — hai script còn tự giải DSN

`scripts/_db_common.py` đã có `resolve_dsn(override=None)`, 6 script khác đã
dùng. Còn sót hai chỗ:

| File | Dòng | Hiện tại | Hành vi lỗi hiện tại |
|---|---|---|---|
| `scripts/backfill_spike_data_to_db.py` | 110 | `dsn = os.environ["DB_DSN"]` | `KeyError` trần |
| `scripts/load_token_to_db.py` | 25 | `os.environ.get` + tự in lỗi | `SystemExit(1)` |

Đổi cả hai sang `from _db_common import resolve_dsn` rồi `dsn = resolve_dsn()`.
Không thêm cờ `--dsn` (hai script này không có argparse — đừng tiện tay thêm).

Cái được: cả hai hiện **không** nạp `.env` và **không** vá `localhost` →
`127.0.0.1`. Trên máy Windows này DSN dùng `localhost` khiến mỗi kết nối mất
~130 giây vì IPv6.

Xóa import `os` / `urlparse` nếu thay đổi này làm chúng thành thừa — kiểm bằng
ruff, đừng đoán.

**Kiểm chứng:**
1. `uv run python scripts/load_token_to_db.py` khi KHÔNG có `DB_DSN` và KHÔNG có
   `.env` → thoát mã 1 kèm thông điệp của `resolve_dsn`. Ghi lại output thật.
2. Có `.env` → script đọc được DSN mà không cần export biến môi trường thủ công.
   Với `load_token_to_db.py`, dừng ngay ở bước "chưa có file token" là ĐỦ để
   chứng minh DSN đã giải xong — **không** cần chạy tới bước ghi DB.
3. `uv run ruff check scripts/backfill_spike_data_to_db.py scripts/load_token_to_db.py`
   sạch.

---

## Task B — một công thức thanh khoản, hiện đang có hai bản LỆCH NHAU

Đây không phải dọn dẹp cho gọn. Hai bản đang tính trên hai tập bar khác nhau:

- `trading/backtest.py:70-75` loại sạch bar OHLC≤0 **trước khi** strategy nhìn
  thấy bar nào. Nên cửa sổ của `OctopusPullbackStrategy._liquidity_ok`
  (`octopus_pullback.py:111`) KHÔNG BAO GIỜ chứa bar rác.
- `scripts/measure_strategy.py::ever_liquid` (dòng 76-93) gặp bar rác thì vẫn
  `vals.append(...)` rồi mới `continue` — bar rác NẰM TRONG cửa sổ, kéo bình
  quân lệch đi.

Hệ quả: dòng "số mã TỪNG đủ thanh khoản" trong báo cáo đo không khớp với tập mã
strategy thực sự nhận. Có 971 mã chứa bar OHLC≤0 nên đây không phải trường hợp
hiếm.

**Việc cần làm:** đưa về MỘT nguồn sự thật, và bản gộp phải theo hành vi của
strategy (bỏ hẳn bar rác khỏi cửa sổ), vì đó là hành vi đúng — bar rác không
phải phiên giao dịch thật.

Hai bản có hình dạng khác nhau (strategy: có state, mỗi symbol một deque, gọi
từng bar; script: không state, duyệt cả list). **Tự chọn cách gộp** — hàm thuần
nhận iterable giá trị, hay cách khác — nhưng phải nêu rõ lựa chọn và lý do
trong báo cáo. Đừng ép script phải khởi tạo cả một strategy chỉ để hỏi thanh
khoản.

Giữ nguyên: `maxlen = window + 1` rồi loại phần tử cuối (đây là bản đã sửa lỗi
off-by-one, cửa sổ phải là `window` phiên TRƯỚC bar hiện tại — đừng vô tình
làm hỏng lại).

**Kiểm chứng — theo đúng thứ tự, đây là tiêu chí nghiêm nhất của task này:**

1. **Viết test ĐỎ TRƯỚC** tái hiện sai lệch: một chuỗi bar có xen bar OHLC≤0 sao
   cho `ever_liquid` hiện tại và `_liquidity_ok` hiện tại cho ra KHÁC nhau. Test
   này phải FAIL trên code hiện tại. Dán output đỏ vào báo cáo.
2. Gộp về một nguồn → test xanh.
3. **Chứng minh test có tính phân biệt:** sửa tạm bản gộp về hành vi cũ (cho bar
   rác vào cửa sổ) → test phải FAIL lại. Hoàn nguyên. Dán cả hai output. Test
   không phân biệt được thì coi như chưa có test.
4. `uv run pytest -m "not integration" -q` → phải là **286 passed** cộng đúng số
   test bạn thêm; 82 deselected.
5. **Chạy lại phép đo và giải thích chênh lệch:**
   ```
   uv run python scripts/measure_strategy.py --strategy octopus_pullback --limit 30
   ```
   Số PnL/lệnh/mã phải **y hệt** trước đó (thay đổi này KHÔNG được đụng vào
   backtest). Riêng dòng "số mã TỪNG đủ thanh khoản" ĐƯỢC PHÉP đổi — nếu đổi,
   nói rõ đổi từ bao nhiêu sang bao nhiêu và vì sao con số mới mới là con số
   đúng. Nếu KHÔNG đổi, kiểm xem 30 mã đầu có mã nào chứa bar rác không, rồi
   nói rõ vì sao không đổi.

---

## Task C — `real_order_account`: điều tra, KHÔNG sửa

`config/config.yaml:8` đang là `real_order_account: "0434221"`. Nghi vấn: tiền
và cổ phiếu thật nằm ở **0434226**, không phải 0434221. Đây là thay đổi cấu hình
nguy hiểm nhất trong repo nên **tuyệt đối không sửa file** — chỉ thu thập bằng
chứng để chủ dự án quyết.

Trả lời bằng SỐ, mỗi câu kèm nguồn (truy vấn nào / API nào / file:dòng nào):

1. 0434221 và 0434226 mỗi tài khoản hiện có gì: tiền mặt, danh mục cổ phiếu
   (mã + khối lượng), loại tài khoản (thường / margin).
2. Danh mục 0434226 giao nhau với `config.symbols` ở những mã nào, khối lượng
   bao nhiêu? (Đã biết có ~1500 VCB — xác nhận và liệt kê đủ.)
3. Nếu đổi sang 0434226 rồi `real_trading_enabled: true`, lệnh SELL đầu tiên có
   thể chạm vào cổ phiếu đang nắm thật không? Chỉ ra đường đi trong code
   (file:dòng) từ config tới lệnh đặt.
4. 0434226 là tài khoản margin: sức mua (`purchase_power`) trả về gì? Ghi
   nguyên văn response. Nếu rỗng, nói rõ rỗng — chỗ nào trong code đang giả định
   nó có giá trị?

**Ràng buộc C:** read-only tuyệt đối. Không đặt lệnh, không hủy lệnh, không gọi
`AsyncTrading` ngoài truy vấn tra cứu. Token hết hạn → DỪNG, báo cáo, không tự
làm mới.

---

## Báo cáo cuối

Với mỗi task: đã sửa file nào (đường dẫn + dòng), output kiểm chứng THẬT (dán
nguyên văn, không tóm tắt thành "pass"), `gitnexus_detect_changes()` cho thấy
những symbol nào bị chạm. Việc nào không làm được thì nói rõ vì sao, đừng đoán
bừa cho đủ.
