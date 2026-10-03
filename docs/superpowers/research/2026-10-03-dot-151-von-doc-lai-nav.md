# Báo Cáo Nghiên Cứu & Kiểm Chứng Đợt 151: Vốn Lệnh Thật Đọc Lại NAV & Vốn $\le$ 0 Không Tự Sinh Halt Lỗ Ngày

- **Ngày thực hiện:** 2026-10-03
- **Kế hoạch:** `docs/superpowers/plans/2026-10-03-brief-dot-151-von-lenh-that-doc-lai-nav-va-von-0-khong-phai-lo.md`
- **Môi trường thực thi:** Git worktree `AI_auto_trading_system_wt151` (branch `brief-151`), sau khi kiểm chứng toàn diện đã đồng bộ về repo chính.
- **Ràng buộc an toàn:** TUYỆT ĐỐI KHÔNG commit, KHÔNG push; `real_trading_enabled` giữ nguyên `false`.

---

## 1. Số Đo Nguyên Văn

### 1.1. Baseline Trước Khi Sửa
- **Full test suite trước Brief 151:** `1755 passed`
- **Bộ 8 file risk & backtest đối chứng vốn > 0:**
  `tests/test_derivative_risk.py`, `tests/test_fractional_risk.py`, `tests/test_risk.py`, `tests/test_backtest.py`, `tests/test_backtest_cli.py`, `tests/test_derivative_backtest.py`, `tests/test_pattern_backtest.py`, `tests/test_perp_backtest.py`:
  - Trước khi sửa: **116 passed**
  - Sau khi thêm 2 test mới của Việc 1: **118 passed in 1.10s** (116 baseline giữ nguyên 100%, 2 test mới passed).

### 1.2. Kiểm Tra AST Theo Hàm
Đối chiếu `HEAD` với bản mới:
- `trading/risk.py`: Chỉ 3 hàm thay đổi:
  - `RiskManager._halt_check`: thêm kiểm tra `if self.capital <= 0: return False` trước ngưỡng lỗ ngày.
  - `RiskManager.approve`: khi BUY và `self.capital <= 0`, đặt `self.last_reject_reason = "vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh"` và trả `False`.
  - `RiskManager.approve_sized`: đặt sau `_halt_check` và sau SELL; khi BUY và `self.capital <= 0`, đặt cùng lý do và trả `None`.
- `trading/engine/main.py`: Chỉ thêm hàm cấp module `real_capital_from_nav` và cập nhật hàm `run`:
  - Khối khởi động dùng `real_capital_from_nav(nav_row)`, lưu `last_nav_valid` và `last_nav_capital`.
  - Trong `on_real_crossover`, đọc lại NAV trước `handle_crossover`, cập nhật `real_risk.capital` và xử lý thông báo chuyển trạng thái.

### 1.3. Kết Quả Unit Tests Việc 1 (`tests/test_risk.py`)
```text
tests/test_risk.py::test_risk_manager_zero_capital_rejects_buy_without_halting PASSED [ 50%]
tests/test_risk.py::test_risk_manager_negative_capital_rejects_buy_without_halting PASSED [100%]
====================== 2 passed, 23 deselected in 0.11s =======================
```

### 1.4. Kết Quả Integration Tests Việc 2 (`tests/test_engine_main.py`)
```text
tests/test_engine_main.py::test_real_crossover_nav_reread_recovery PASSED [ 33%]
tests/test_engine_main.py::test_real_crossover_nav_reread_breaks_midway PASSED [ 66%]
tests/test_engine_main.py::test_real_crossover_nav_reread_stays_broken_silent PASSED [100%]
====================== 3 passed, 61 deselected in 2.01s =======================
```

### 1.5. Bộ Test Suite Đầy Đủ Sau Khi Chép Về Repo Chính
- `uv run ruff check trading tests scripts`:
  ```text
  All checks passed!
  ```
- Tiến trình nền kiểm tra trước khi chạy suite:
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }
  # Kết quả: rỗng
  ```
- `uv run pytest -q`:
  ```text
  1760 passed in 75.13s (0:01:15)
  ```
  (1755 passed baseline + 2 unit tests Việc 1 + 3 integration tests Việc 2 = 1760 passed, 0 failed).

---

## 2. Phá Thử (Mutation Testing)

Các file được đo SHA-256 baseline trước khi phá thử:
- `trading/risk.py`: `626603E728B55DDD109D317687053303D44B04F7A6300824F9BFCB0A8CB18E95`
- `trading/engine/main.py`: `1B22543B950AD96101E6CE9316FA5247ECEAD87037E2E2EB8D1F415093F15968`
- `tests/test_risk.py`: `9568ED5825FB6ACB7B09463F3251C469F0FEFAA2F4C42B3323134669F5267EBD`
- `tests/test_engine_main.py`: `6DD133CBDAF6359A23310929E2DF7156761AC887A9951843ADF528085C543746`

### Ca 1: Bỏ nhánh `capital <= 0` trong `_halt_check`
- **Thao tác:** Xóa `if self.capital <= 0: return False` trong `trading/risk.py:_halt_check`.
- **Dòng đỏ nguyên văn:**
  ```text
  tests\test_risk.py:330: AssertionError: assert ('halt lỗ ngày' is not None and 'vốn' in 'halt lỗ ngày')
  FAILED tests/test_risk.py::test_risk_manager_zero_capital_rejects_buy_without_halting
  FAILED tests/test_risk.py::test_risk_manager_negative_capital_rejects_buy_without_halting
  ```
- **Khôi phục:** Phục hồi `trading/risk.py`.
- **Đối chiếu SHA-256 sau phục hồi:** `626603E728B55DDD109D317687053303D44B04F7A6300824F9BFCB0A8CB18E95` (trùng khớp hoàn toàn).

### Ca 2: Bỏ dòng gán `real_risk.capital` trong `on_real_crossover`
- **Thao tác:** Comment out `real_risk.capital = curr_capital` trong nhánh phục hồi của `trading/engine/main.py:on_real_crossover`.
- **Dòng đỏ nguyên văn:**
  ```text
  tests\test_engine_main.py:2308: AssertionError: Ca A phai sinh 1 lenh BUY that, thuc te pending=0, engine_alerts=[...], real_alerts=[('INFO', 'lenh that bi tu choi', {'symbol': 'ENGT', 'side': 'BUY', 'reason': 'vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh'})]
  assert 0 == 1
   +  where 0 = _count_pending_buys(<trading.storage.db.Storage object at 0x0000022CB555D810>)
  FAILED tests/test_engine_main.py::test_real_crossover_nav_reread_recovery
  ```
- **Khôi phục:** Phục hồi `trading/engine/main.py`.
- **Đối chiếu SHA-256 sau phục hồi:** `1B22543B950AD96101E6CE9316FA5247ECEAD87037E2E2EB8D1F415093F15968` (trùng khớp hoàn toàn).

### Ca 3: Bỏ điều kiện "chỉ báo khi trạng thái đổi" trong `on_real_crossover`
- **Thao tác:** Đổi `if last_nav_valid and not curr_valid:` thành `if not curr_valid:` (luôn alert CRITICAL mỗi lần crossover gặp NAV hỏng, không phụ thuộc trạng thái trước).
- **Dòng đỏ nguyên văn:**
  ```text
  tests\test_engine_main.py:2439: AssertionError: Ca C phai co dung 1 CRITICAL NAV (luc khoi dong, crossover im lang): [...]
  assert 2 == 1
   +  where 2 = len([('CRITICAL', 'NAV khong hop le (<= 0): -39,959,000 — real capital = 0, MOI lenh that bi tu choi (fail-safe)', {'account': 'ACC_RTS', 'nav': -39959000.0, 'ts': '2026-10-03 04:05:53.088172+07:00'}), ('CRITICAL', 'NAV chuyen sang khong hop le: NAV khong hop le (<= 0): -39,959,000 (ts=2026-10-03 04:05:53.088172+07:00) — real capital = 0, MOI lenh that bi tu choi (fail-safe)', {'account': 'ACC_RTS'})])
  FAILED tests/test_engine_main.py::test_real_crossover_nav_reread_stays_broken_silent
  ```
- **Khôi phục:** Phục hồi `trading/engine/main.py`.
- **Đối chiếu SHA-256 sau phục hồi:** `1B22543B950AD96101E6CE9316FA5247ECEAD87037E2E2EB8D1F415093F15968` (trùng khớp hoàn toàn).

### Ca 4: Đổi `<= 0` thành `< 0` trong `RiskManager`
- **Thao tác:** Thay thế `self.capital <= 0` thành `self.capital < 0` trong `_halt_check`, `approve` và `approve_sized`.
- **Dòng đỏ nguyên văn:**
  ```text
  tests\test_risk.py:330: AssertionError: assert ('halt lỗ ngày' is not None and 'vốn' in 'halt lỗ ngày')
  FAILED tests/test_risk.py::test_risk_manager_zero_capital_rejects_buy_without_halting
  ```
- **Khôi phục:** Phục hồi `trading/risk.py`.
- **Đối chiếu SHA-256 sau phục hồi:** `626603E728B55DDD109D317687053303D44B04F7A6300824F9BFCB0A8CB18E95` (trùng khớp hoàn toàn).

---

## 3. Danh Sách Alert ĐẦY ĐỦ Của Ca A, B, C

*(Dưới đây là danh sách bắt được từ cả hai kênh `trading.engine.main.alert` [ENGINE] và `trading.real_orders.alert` [REAL_ORDERS], in nguyên văn đầy đủ từng alert không cắt dòng).*

### Ca A: Hồi phục (Khởi động NAV −39.959.000 $\to$ Crossover NAV 100.000.000)
Tổng cộng: 32 alerts
```text
[ENGINE] INFO: engine starting fresh | fields={'capital': 100000000.0}
[ENGINE] CRITICAL: het thoi gian cho du lieu bars truoc warm-up — van chay tiep | fields={'missing_symbols': ['ENGT'], 'needed_date': '2026-10-02', 'timeout_sec': 0}
[ENGINE] WARN: warm-up ENGT thieu lich su: chi co 0/21 bar trong bang bars — ma nay VAN DANG MU | fields={'symbol': 'ENGT'}
[ENGINE] CRITICAL: NAV khong hop le (<= 0): -39,959,000 — real capital = 0, MOI lenh that bi tu choi (fail-safe) | fields={'account': 'ACC_RTS', 'nav': -39959000.0, 'ts': '2026-10-03 04:00:00+07:00'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:00:00+07:00', 'lag_ms': 6893314168.49}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:15:00+07:00', 'lag_ms': 6892414186.01}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:30:00+07:00', 'lag_ms': 6891514200.51}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:45:00+07:00', 'lag_ms': 6890614218.35}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:00:00+07:00', 'lag_ms': 6889714232.09}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:15:00+07:00', 'lag_ms': 6888814248.62}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:30:00+07:00', 'lag_ms': 6887914262.55}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:45:00+07:00', 'lag_ms': 6887014277.92}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:00:00+07:00', 'lag_ms': 6886114291.35}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:15:00+07:00', 'lag_ms': 6885214304.61}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:30:00+07:00', 'lag_ms': 6884314323.38}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:45:00+07:00', 'lag_ms': 6883414340.35}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:00:00+07:00', 'lag_ms': 6882514358.53}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:15:00+07:00', 'lag_ms': 6881614382.42}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:30:00+07:00', 'lag_ms': 6880714396.85}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:45:00+07:00', 'lag_ms': 6879814410.73}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:00:00+07:00', 'lag_ms': 6878914425.77}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:15:00+07:00', 'lag_ms': 6878014438.8}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:30:00+07:00', 'lag_ms': 6877114451.75}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:45:00+07:00', 'lag_ms': 6876214465.97}
[ENGINE] WARN: NAV hop le tro lai — real capital = 100,000,000 | fields={'account': 'ACC_RTS', 'capital': 100000000.0}
[REAL_ORDERS] WARN: real order pending confirmation | fields={'id': 4492, 'symbol': 'ENGT', 'side': 'BUY', 'qty': 100, 'price': 20.0, 'expires_in_minutes': 15, 'confirm_cmd': 'uv run python scripts/confirm_real_order.py 4492'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:00:00+07:00', 'lag_ms': 6875314502.84}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:15:00+07:00', 'lag_ms': 6874414518.14}
[ENGINE] INFO: order filled | fields={'symbol': 'ENGT', 'side': 'BUY', 'qty': 700000, 'price': 20.01, 'pnl': None}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:30:00+07:00', 'lag_ms': 6873514548.6}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:45:00+07:00', 'lag_ms': 6872614561.17}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T15:00:00+07:00', 'lag_ms': 6871714576.23}
```

### Ca B: Hỏng giữa chừng (Khởi động NAV 100.000.000 $\to$ Crossover NAV −39.959.000)
Tổng cộng: 32 alerts
```text
[ENGINE] INFO: engine starting fresh | fields={'capital': 100000000.0}
[ENGINE] CRITICAL: het thoi gian cho du lieu bars truoc warm-up — van chay tiep | fields={'missing_symbols': ['ENGT'], 'needed_date': '2026-10-02', 'timeout_sec': 0}
[ENGINE] WARN: warm-up ENGT thieu lich su: chi co 0/21 bar trong bang bars — ma nay VAN DANG MU | fields={'symbol': 'ENGT'}
[ENGINE] INFO: NAV lam real capital | fields={'account': 'ACC_RTS', 'nav': 100000000.0, 'ts': '2026-10-03 04:00:00+07:00'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:00:00+07:00', 'lag_ms': 6893314674.51}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:15:00+07:00', 'lag_ms': 6892414688.11}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:30:00+07:00', 'lag_ms': 6891514700.72}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:45:00+07:00', 'lag_ms': 6890614716.64}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:00:00+07:00', 'lag_ms': 6889714730.09}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:15:00+07:00', 'lag_ms': 6888814743.41}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:30:00+07:00', 'lag_ms': 6887914756.17}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:45:00+07:00', 'lag_ms': 6887014769.13}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:00:00+07:00', 'lag_ms': 6886114783.73}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:15:00+07:00', 'lag_ms': 6885214797.2}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:30:00+07:00', 'lag_ms': 6884314809.42}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:45:00+07:00', 'lag_ms': 6883414824.73}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:00:00+07:00', 'lag_ms': 6882514837.62}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:15:00+07:00', 'lag_ms': 6881614850.13}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:30:00+07:00', 'lag_ms': 6880714862.82}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:45:00+07:00', 'lag_ms': 6879814878.16}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:00:00+07:00', 'lag_ms': 6878914891.04}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:15:00+07:00', 'lag_ms': 6878014903.58}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:30:00+07:00', 'lag_ms': 6877114919.25}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:45:00+07:00', 'lag_ms': 6876214931.9}
[ENGINE] CRITICAL: NAV chuyen sang khong hop le: NAV khong hop le (<= 0): -39,959,000 (ts=2026-10-03 04:00:00+07:00) — real capital = 0, MOI lenh that bi tu choi (fail-safe) | fields={'account': 'ACC_RTS'}
[REAL_ORDERS] INFO: lenh that bi tu choi | fields={'symbol': 'ENGT', 'side': 'BUY', 'reason': 'vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:00:00+07:00', 'lag_ms': 6875314959.67}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:15:00+07:00', 'lag_ms': 6874414974.91}
[ENGINE] INFO: order filled | fields={'symbol': 'ENGT', 'side': 'BUY', 'qty': 700000, 'price': 20.01, 'pnl': None}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:30:00+07:00', 'lag_ms': 6873515005.3}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:45:00+07:00', 'lag_ms': 6872615018.71}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T15:00:00+07:00', 'lag_ms': 6871715033.71}
```

### Ca C: Hỏng suốt (Khởi động NAV −39.959.000 $\to$ Crossover NAV −39.959.000)
Tổng cộng: 31 alerts
```text
[ENGINE] INFO: engine starting fresh | fields={'capital': 100000000.0}
[ENGINE] CRITICAL: het thoi gian cho du lieu bars truoc warm-up — van chay tiep | fields={'missing_symbols': ['ENGT'], 'needed_date': '2026-10-02', 'timeout_sec': 0}
[ENGINE] WARN: warm-up ENGT thieu lich su: chi co 0/21 bar trong bang bars — ma nay VAN DANG MU | fields={'symbol': 'ENGT'}
[ENGINE] CRITICAL: NAV khong hop le (<= 0): -39,959,000 — real capital = 0, MOI lenh that bi tu choi (fail-safe) | fields={'account': 'ACC_RTS', 'nav': -39959000.0, 'ts': '2026-10-03 04:00:00+07:00'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:00:00+07:00', 'lag_ms': 6893315130.94}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:15:00+07:00', 'lag_ms': 6892415146.49}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:30:00+07:00', 'lag_ms': 6891515161.11}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T09:45:00+07:00', 'lag_ms': 6890615175.94}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:00:00+07:00', 'lag_ms': 6889715189.01}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:15:00+07:00', 'lag_ms': 6888815201.64}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:30:00+07:00', 'lag_ms': 6887915216.35}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T10:45:00+07:00', 'lag_ms': 6887015230.29}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:00:00+07:00', 'lag_ms': 6886115243.23}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:15:00+07:00', 'lag_ms': 6885215255.83}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:30:00+07:00', 'lag_ms': 6884315268.05}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T11:45:00+07:00', 'lag_ms': 6883415283.13}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:00:00+07:00', 'lag_ms': 6882515295.9}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:15:00+07:00', 'lag_ms': 6881615310.67}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:30:00+07:00', 'lag_ms': 6880715323.37}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T12:45:00+07:00', 'lag_ms': 6879815337.73}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:00:00+07:00', 'lag_ms': 6878915350.87}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:15:00+07:00', 'lag_ms': 6878015363.74}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:30:00+07:00', 'lag_ms': 6877115378.07}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T13:45:00+07:00', 'lag_ms': 6876215394.34}
[REAL_ORDERS] INFO: lenh that bi tu choi | fields={'symbol': 'ENGT', 'side': 'BUY', 'reason': 'vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh'}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:00:00+07:00', 'lag_ms': 6875315421.59}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:15:00+07:00', 'lag_ms': 6874415434.89}
[ENGINE] INFO: order filled | fields={'symbol': 'ENGT', 'side': 'BUY', 'qty': 700000, 'price': 20.01, 'pnl': None}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:30:00+07:00', 'lag_ms': 6873515471.72}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T14:45:00+07:00', 'lag_ms': 6872615488.11}
[ENGINE] INFO: bar processed | fields={'symbol': 'ENGT', 'ts': '2026-07-15T15:00:00+07:00', 'lag_ms': 6871715500.38}
```

---

## 4. GitNexus Impact Analysis

### Trước Khi Sửa
- `Method:trading/risk.py:RiskManager._halt_check#2`: CRITICAL, impactedCount: 19
- `Method:trading/risk.py:RiskManager.approve#5`: LOW, impactedCount: 1
- `Method:trading/risk.py:RiskManager.approve_sized#6`: CRITICAL, impactedCount: 18
- `Function:trading/engine/main.py:run`: LOW, impactedCount: 4

### Sau Khi Sửa (`detect-changes`)
```text
Changes: 4 files, 21 symbols
Affected processes: 1
Risk level: medium

Changed symbols:
  loop, msg, bar, last_ts, warm_cutoff, wu, missing, _install_stop_handlers,
  _on_signal, _default_strategy, run (trading/engine/main.py)
  RiskManager, held_symbols, qty_cap, qty, ... (trading/risk.py)

Affected execution flows:
  • Main → _get_pool (5 steps) — changed: run
```
Không phát sinh bất kỳ symbol ngoài ý muốn hay execution flow không lường trước nào.

---

## 5. Brief Sai Ở Đâu

1. **Về kịch bản phá thử Ca 1:**
   - Brief ghi: *"bỏ nhánh `capital <= 0` trong `_halt_check` → test Việc 1 đỏ, và ca A đỏ (có halt, pending = 0)"*.
   - **Thực tế:** Test Việc 1 đỏ (vì unit test kiểm tra trực tiếp việc gọi `approve_sized` với `capital <= 0`, khi bỏ nhánh này `_halt_check` sẽ so sánh `0.0 <= -0.0` hoặc `0.0 <= -(-39.959.000 * 0.03)` dẫn đến tự kích hoạt halt lỗ ngày).
   - Tuy nhiên, **Ca A không đỏ khi bỏ nhánh này**: Trong Ca A, tại thời điểm crossover, `read_nav` đã trả về NAV phục hồi là 100.000.000 (`curr_capital = 100.000.000 > 0`). Vốn đã được cập nhật thành số dương trước khi gọi `approve_sized`, và từ bar 0 đến 19 không có crossover nào nên `approve_sized` chưa từng được gọi lúc vốn $\le 0$. Do đó `_halt_check` chỉ được gọi lúc vốn đã là 100.000.000 nên Ca A vẫn sinh lệnh và pass. Nhận định trong brief rằng Ca A sẽ đỏ là suy luận chưa tính đến việc crossover chỉ xảy ra sau khi vốn đã phục hồi.
2. **Về cách thức monkeypatch trong integration test:**
   - Brief ghi: *"Dùng `monkeypatch` cho `storage.read_nav` trả chuỗi giá trị..."*.
   - **Thực tế:** Trong `trading/engine/main.py`, hàm `run()` tự khởi tạo instance riêng: `storage = Storage(cfg.db_dsn)`. Nếu dùng `monkeypatch.setattr(storage, "read_nav", ...)` trên fixture `storage` được inject vào test function, instance nội bộ của `run()` sẽ không bị ảnh hưởng và vẫn gọi DB thật (gây lỗi do bảng trống). Phải monkeypatch trên cấp lớp: `monkeypatch.setattr(Storage, "read_nav", fake_read_nav)`.

---

## 6. Cái Gì Không Kiểm Được

1. **Khớp lệnh & kết nối mạng thực tế với SSI:**
   - Mọi thử nghiệm đều thực hiện qua mock / JetStream test độc lập cổng 4223 (`nats-test`) và DB Postgres `trading_test`.
   - `real_trading_enabled` vẫn duy trì nghiêm ngặt ở giá trị `false`, do đó không có kết nối nào được gửi ra máy chủ SSI thật và không có tin nhắn Telegram thật nào được phát ra (được kiểm soát bởi các hàng rào cách ly `ISO-4`, `ISO-5`).
2. **Hành vi luồng nền khi chạy liên tục nhiều ngày:**
   - Test chỉ mô phỏng chuỗi 25 bars trong một phiên thử nghiệm cụ thể (chuyển trạng thái NAV giữa lúc khởi động và bar crossover thứ 21). Hành vi kéo dài qua nhiều phiên giao dịch liên tiếp cần được theo dõi thực tế khi hệ thống vận hành.

---

## Audit của Claude (03/10/2026)

### A.1. Kết luận: ĐẠT, kèm hai test Claude thêm cho hai hành vi chưa được ghim.

### A.2. Phạm vi
AST theo hàm:
- `risk.py`: `_halt_check`, `approve`, `approve_sized` (lớp `RiskManager` khác vì chứa ba hàm này).
- `engine/main.py`: `run`, `on_real_crossover` (lồng trong `run`) và hàm mới `real_capital_from_nav`.

Không có gì ngoài phạm vi. Hai mục "brief sai" ở §5 đều đúng:
- Ca A không thể đỏ khi bỏ nhánh `_halt_check`, vì lúc crossover diễn ra vốn đã hồi phục.
- Phải patch `Storage.read_nav` ở cấp lớp, vì `run()` tự tạo instance riêng.

### A.3. Phá thử của Claude

| Phá thử | Kết quả trước khi Claude thêm test |
|---|---|
| Bỏ kiểm `vốn <= 0` trong `approve_sized` (giữ `_halt_check`) | 2 test `test_risk` đỏ |
| Hợp lệ → hỏng mà không hạ vốn về 0 | Ca B đỏ |
| `_halt_check` với vốn ≤ 0 trả `True` | 2 test `test_risk` đỏ |
| **Bỏ `last_nav_valid = True` ở nhánh hồi phục** | **xanh hết**: WARN "hop le tro lai" sẽ lặp ở mọi crossover sau |
| **Thêm `raise` vào nhánh except của `on_real_crossover`** | **90 passed**: lỗi DB khi đọc lại NAV làm rơi crossover, không test nào thấy |

Claude thêm hai test vào `tests/test_engine_main.py`:
- `test_real_crossover_nav_reread_recovery_warns_once`: giá lên rồi xuống, tạo hai crossover; NAV hỏng lúc
  khởi động, hợp lệ ở mọi lần đọc sau; WARN hồi phục đúng một lần. Với phá thử thứ tư: `assert 2 == 1`.
- `test_real_crossover_nav_reread_db_error_keeps_capital`: khởi động hợp lệ, đọc lại thì
  `ConnectionError`; phải có WARN và vẫn sinh 1 lệnh BUY. Với phá thử thứ năm: `pending 0 == 1`.

Hash `trading/engine/main.py` sau mọi lần khôi phục: `1b22543b950ad961`.

Lần đầu Claude thử `raise` bằng một chuỗi khớp **hai** chỗ, nên phép thay rơi vào chỗ khác. Claude đã làm lại,
nhắm đúng thông điệp của nhánh except.

### A.4. Hiệu lực
Mã chạy trong image. Chỉ có hiệu lực sau khi Claude build lại engine.

