# Brief đợt 151 — vốn lệnh thật phải đọc lại NAV, và vốn 0 không được tính là "lỗ quá ngưỡng"

## Bối cảnh

Đợt 150 (`9e9bdef`) chuyển lệnh thật sang tài khoản margin `0434226`. Engine giờ từ chối NAV ≤ 0 lúc
khởi động (CRITICAL, vốn = 0). Audit đợt 150 còn để lại hai vấn đề nối nhau.

**1. Vốn bị đóng băng từ lúc khởi động.**
- `trading/engine/main.py::run` đọc NAV **một lần** rồi tạo `real_risk = RiskManager(capital=real_capital)`.
  Sau đó không đọc lại nữa.
- Engine khởi động ở giờ bất kỳ. Nếu lần khởi động rơi vào lúc dòng NAV mới nhất hỏng, vốn = 0 cho tới lần
  khởi động sau, dù 5 phút sau NAV đã đúng lại.
- Ngược lại, NAV của tài khoản margin thay đổi theo giá và nợ, nhưng vốn rủi ro vẫn đứng yên ở con số lúc
  khởi động.

**2. Vốn 0 tự sinh "halt lỗ ngày".** `trading/risk.py::_halt_check` so
`daily_pnl <= -self.capital * self.max_daily_loss_pct`. Với vốn 0 thì phép so thành `0 <= 0`, tức là đúng.
Claude đã chạy kịch bản NAV −39.959.000 và bắt được chuỗi alert sau:

```
main CRITICAL  NAV khong hop le (<= 0): -39,959,000 — real capital = 0, MOI lenh that bi tu choi (fail-safe)
ro   INFO      lenh that bi tu choi   reason=halt lỗ ngày
main CRITICAL  REAL risk halt: max daily loss reached
```

Hậu quả:
- `save_real_risk_halt` lưu halt vào DB cho cả ngày. Engine khởi động lại với NAV đúng thì vẫn đọc halt đó
  (`real_risk.halted_date = storage.read_real_risk_halt()`). Kết quả là mất trọn một ngày lệnh MUA thật.
- Người vận hành nhận tin "lỗ quá ngưỡng" trong khi chưa có lệnh nào.
- Đường BÁN thật hiện chỉ đi qua `handle_stop_touch`. Hàm này không qua `RiskManager` (octopus không phát
  "bear", xem docstring `_default_strategy`), nên halt không chặn đường thoát. Brief này không đổi chỗ đó.

**Vì sao KHÔNG sửa CONFIRM-1 trong đợt này.** Nguồn NAV hỏng là SSI trả danh mục rỗng ban đêm. Log
collector ghi ba lần (giờ VN):

| Thời điểm | Số nhịp rỗng | Kết quả |
|---|---|---|
| 30/09 01:40 | 2 | CONFIRM-1 xác nhận nhầm, NAV −39.959.000 |
| 01/10 01:44 | 1 | CONFIRM-1 chặn được |
| 03/10 01:52 | 1 | CONFIRM-1 chặn được |

Nâng ngưỡng xác nhận lên 3 nhịp chỉ đẩy giới hạn từ 2 lên 3 nhịp, không có gì bảo đảm. Sau đợt 150, NAV
hỏng chỉ gây hại qua hai đường nói trên. Bịt hai đường đó thì một dòng NAV hỏng chỉ còn làm hỏng vài phút,
không làm mất cả ngày.

## Việc

### Việc 1 — `RiskManager`: vốn ≤ 0 nghĩa là "không tính được", không phải "lỗ"
Trong `trading/risk.py`:
- **`_halt_check`:** khi `self.capital <= 0`, **không** so ngưỡng lỗ và **không** đặt `halted_date`. Chỉ
  trả `self.halted_date == today`, tức là giữ halt đã có từ trước.
- **`approve_sized`, nhánh BUY:** khi `self.capital <= 0`, trả `None` với `last_reject_reason` nêu rõ vốn
  ≤ 0 (vd `"vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh"`). Đặt kiểm tra này **sau**
  `_halt_check` và **sau** nhánh SELL.
- **`approve`, nhánh BUY:** đã tự từ chối vì trần giá trị bằng 0. Thêm cùng lý do rõ ràng như trên, đặt
  trước phép so trần.
- **SELL** đi qua như cũ.
- Với vốn > 0, hành vi **không đổi một ký tự**.

`RiskManager` được dùng chung bởi paper, lệnh thật và backtest. Paper và backtest luôn có vốn > 0.

→ kiểm chứng bằng: test đơn vị với vốn 0 và vốn −39.959.000, `daily_pnl = 0`:
- `approve_sized` BUY → `None`, lý do chứa "vốn", `halted_date is None`;
- `approve` BUY → `False`, cùng điều kiện;
- `approve` SELL → `True`;
- đặt `halted_date = today` từ trước thì BUY và SELL vẫn bị chặn: halt cũ được tôn trọng.

Toàn bộ test `risk`/`backtest` cũ phải xanh nguyên.

### Việc 2 — engine đọc lại NAV mỗi lần có crossover thật
Trong `trading/engine/main.py`:
- **Tách** phần "từ `nav_row` ra vốn" thành một hàm cấp module (vd
  `real_capital_from_nav(nav_row) -> tuple[float, str | None]`). Hàm trả `(vốn, vấn_đề)`:
  - không có dòng → `(0.0, "<mô tả>")`;
  - NAV ≤ 0 → `(0.0, "<mô tả kèm giá trị và ts>")`;
  - bình thường → `(nav, None)`.
- **Khối khởi động** dùng hàm này để lấy vốn. **Mọi alert lúc khởi động giữ nguyên từng chữ**: test cũ ghim
  chúng (`khong doc duoc NAV`, `NAV khong hop le (<= 0)`, WARN NAV cũ > 24h, WARN `unpriced`, INFO `NAV
  lam real capital`).
- **Trong `on_real_crossover`, trước `handle_crossover`:** đọc `storage.read_nav(cfg.real_order_account)`,
  qua cùng hàm, rồi gán `real_risk.capital`. Chỉ báo khi **trạng thái đổi**, lưu trạng thái trong closure:
  - hợp lệ → hỏng: **CRITICAL** một lần, nêu vấn đề;
  - hỏng → hợp lệ: **WARN** một lần, `"NAV hop le tro lai — real capital = <số>"`. Dùng WARN để tin này lên
    Telegram: người đã nhận CRITICAL phải biết là đã hết;
  - hỏng → vẫn hỏng: im lặng;
  - hợp lệ, số đổi: **INFO** cũ → mới.

  Trạng thái ban đầu của closure là kết quả lúc khởi động. Nhờ vậy, khởi động hỏng rồi crossover đầu tiên
  vẫn hỏng thì không lặp lại CRITICAL.
- Không làm gì khác: không đọc lại ở mỗi bar, không thêm vòng lặp nền, không đụng GUARD-1/GUARD-3 (chúng chỉ
  chạy lúc khởi động và giữ nguyên).
- Lỗi DB khi đọc lại: giữ vốn đang có, báo **WARN**, không ném. Theo khuôn `idle_maintenance`: lỗi DB tạm
  thời không được giết engine. Không được nuốt lỗi im lặng.

→ kiểm chứng bằng: test tích hợp theo khuôn các test `run(...)` sẵn có trong `tests/test_engine_main.py`.
Dùng `monkeypatch` cho `storage.read_nav` trả **chuỗi** giá trị: lần đầu (khởi động) một dòng, lần sau
(crossover) dòng khác.

| Ca | Khởi động | Lúc crossover | Phải thấy |
|---|---|---|---|
| A — hồi phục | NAV −39.959.000 | NAV 100.000.000 mới | `pending_real_orders` BUY = **1**; có WARN "hop le tro lai"; **không** có `REAL risk halt`; `read_real_risk_halt()` là `None` |
| B — hỏng giữa chừng | NAV 100.000.000 | NAV −39.959.000 | pending = 0; đúng **một** CRITICAL NAV; **không** có `REAL risk halt` |
| C — hỏng suốt | NAV −39.959.000 | NAV −39.959.000 | pending = 0; CRITICAL NAV đúng **một** lần (lúc khởi động); không có halt |

**Bắt buộc có đối chứng dương:** trong ca A, khẳng định pending = 1 chứng minh điều kiện tiên quyết (sức
mua, đồng bộ vị thế…) đủ để sinh lệnh. Nếu cần seed thêm thì seed, theo
`test_real_crossover_creates_pending_buy`. Khẳng định "pending = 0" ở ca B và C chỉ có nghĩa khi ca A cho
ra 1.

Bắt alert ở **cả** `trading.engine.main.alert` lẫn `trading.real_orders.alert`. Tin halt đi qua module thứ
nhất, lý do từ chối qua module thứ hai. Khi dán vào báo cáo, **dán đầy đủ, không cắt bằng `...`**.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không build/restart container (engine chạy từ image; Claude build sau
  audit). Không bật `real_trading_enabled`, không gửi Telegram thật, không chạy gì có `--send`.
- **Chỉ sửa:** `trading/risk.py` (`_halt_check`, `approve`, `approve_sized`); `trading/engine/main.py`
  (hàm mới, khối đọc NAV lúc khởi động, `on_real_crossover`); test tương ứng.
- **Không đụng:**
  - `account_sync.py` (CONFIRM-1);
  - `real_orders.py`;
  - `handle_stop_touch`;
  - `storage`;
  - `logic.py` (luồng paper).
- **GitNexus trước khi sửa:** `npx --no-install gitnexus impact _halt_check --repo AI_auto_trading_system`,
  tương tự cho `approve`, `approve_sized`, `run`. `_halt_check` dùng chung paper/thật/backtest nên có thể
  ra HIGH. Báo con số, giữ thay đổi trong nhánh `capital <= 0`. Sau khi sửa thì chạy `detect_changes`; nếu
  nó báo 0 thay đổi, chạy `npx gitnexus analyze` rồi đo lại.
- Làm trong git worktree, chép vào repo chính trước **08:00 thứ Hai 05/10**. Mã `trading/` không chạy từ
  cây làm việc, nhưng giữ thói quen.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng. Test tích hợp dùng `nats-test`.

## Tiêu chí hoàn thành

1. **AST theo hàm** (`HEAD` với bản mới):
   - `risk.py`: chỉ `_halt_check`, `approve`, `approve_sized` khác;
   - `engine/main.py`: chỉ `run` khác, cộng thêm hàm mới.

   Dán kết quả.
2. **Phá thử.** Mỗi lần ghi nguyên văn dòng đỏ, khôi phục, rồi đối chiếu hash:
   - bỏ nhánh `capital <= 0` trong `_halt_check` → test Việc 1 đỏ, và ca A đỏ (có halt, pending = 0);
   - bỏ dòng gán `real_risk.capital` trong `on_real_crossover` → ca A đỏ;
   - bỏ điều kiện "chỉ báo khi trạng thái đổi" → ca C đỏ (CRITICAL lặp);
   - đổi `<= 0` thành `< 0` trong `RiskManager` → ca vốn 0 của Việc 1 đỏ.
3. **Đối chứng không đổi hành vi với vốn > 0:** chạy `tests/test_risk.py`, `test_fractional_risk.py`, `test_derivative_risk.py` và các `test_*backtest*.py` trước và sau;
   số passed bằng nhau.
4. `ruff` sạch. `uv run pytest -q` ≥ **1.755 passed** cộng số test mới, 0 failed.

## Báo cáo

Ghi vào `docs/superpowers/research/2026-10-03-dot-151-von-doc-lai-nav.md`:
- số đo nguyên văn;
- danh sách alert **đầy đủ** của ca A, B, C;
- GitNexus impact;
- brief sai ở đâu;
- cái gì không kiểm được.
