# BÁO CÁO THỰC HIỆN BRIEF ĐỢT 10: ĐÁNH GIÁ SẴN SÀNG GO-LIVE & BỊT LỖ HỔNG AN TOÀN

**Ngày thực hiện:** 06/09/2026  
**Mục tiêu:** Thực hiện trọn vẹn 5 tasks trong `docs/superpowers/plans/2026-09-06-danh-gia-golive-va-brief-dot-10.md`, bịt các lỗ hổng an toàn vị thế/lệnh thật, dựng lại container sau drift check, thêm chuông nhắc cạn lịch nghỉ lễ và đo đạc Octopus Pullback trên chuỗi nến 5 phút.

---

## 1. TASK 1: ĐO OCTOPUS PULLBACK TRÊN CHUỖI NẾN 5M & SO SÁNH BAR NGÀY

Script thực thi: `scripts/measure_octopus_5m.py`  
Cấu hình đo: Vốn 100,000,000 VND / mã, Phí SSI 0.25%, Thuế 0.1%, Trượt 5 bps (chuẩn thước đo `trading/metrics.py`).

### Bảng số đối chiếu: Khung 5 phút (3 mã engine) vs Khung Ngày (rổ đầy đủ 1.308 mã)

> **Đính chính của Claude khi audit (06/09):** bảng dưới đây thay cho bảng gốc
> của agent, vốn có cột "Khung Ngày" ghi **54 lệnh** kèm đúng số PnL bất biến
> của rổ 1.308 mã (`−1.615.319.902`) — hai con số không thể đi cùng nhau (một
> rổ 3 mã không thể ra đúng PnL đến từng đồng của rổ 1.308 mã). Tự tính lại rổ
> ngày cho đúng 3 mã (HII/IJC/AAA, `FEE_RATE` 0,25%) ra **16 lệnh, −2.695.549
> VND** — khác cả hai con số cũ, và **không dùng con số này** vì nó trộn hai
> phạm vi khác nhau (3 mã vs 1.308 mã), gây hiểu lầm mức độ cải thiện. Bảng
> dưới đây là bảng **chính** do `measure_octopus_5m.py` tự in ra (đã tự chạy
> lại xác nhận khớp), so đúng khung 5 phút của 3 mã với bất biến đã chốt của
> rổ đầy đủ — không so lẫn phạm vi.

| Chỉ số | Khung Ngày (rổ đầy đủ 1.308 mã) | Khung 5 phút (3 mã engine) |
|---|---|---|
| **Tổng số mã** | 1.308 mã (439 mã sinh lệnh) | 3 mã (HII, IJC, AAA) |
| **Tổng số lệnh** | 1.514 lệnh | **12 lệnh** |
| **Tổng PnL** | −1.615.319.902 VND | **+787.149 VND** |
| **Profit Factor** | 0,74 | **1,47** |
| **Expectancy** | −1.068.152 VND/lệnh | **+65.596 VND/lệnh** |
| **Max Drawdown** | 0,1% (toàn bộ) / 0,4% (sinh lệnh) | **0,49%** |
| **Sharpe Ratio** | −0,96 | **0,63** |

### Chi tiết từng mã trên khung 5 phút:
- **HII (3,211 bars):** 1 lệnh (1W/0L, WR 100%), PnL: `+674,604 VND` (B&H: `+64,455,059 VND`), PF: N/A, Sharpe: 0.91, MaxDD: 0.4%.
- **IJC (4,719 bars):** 5 lệnh (2W/3L, WR 40%), PnL: `+65,774 VND` (B&H: `-29,209,276 VND`), PF: 1.05, Sharpe: 0.12, MaxDD: 1.2%.
- **AAA (4,597 bars):** 6 lệnh (3W/3L, WR 50%), PnL: `+46,771 VND` (B&H: `+1,146,249 VND`), PF: 1.13, Sharpe: 0.38, MaxDD: 0.9%.

### Đánh giá trung thực về cỡ mẫu:
- **Tổng số lệnh chỉ có 12 lệnh trên 12,527 thanh nến 5m** (tỷ lệ kích hoạt chỉ ~0.1% số nến, bình quân chỉ 4 lệnh/mã trong suốt chuỗi dữ liệu).
- Mặc dù kết quả 5m có PnL dương (+787K) và PF = 1.47 (tốt hơn khung Ngày lỗ nặng do không bị dính các chuỗi cắt lỗ trailing stop dài ngày), **cỡ mẫu 12 lệnh là QUÁ NHỎ**, không đạt ngưỡng tối thiểu thống kê ($\ge 30-50$ lệnh) để kết luận chiến lược có edge thực sự trên khung 5m.

---

## 2. TASK 2 & TASK 5: AN TOÀN ĐẶT LỆNH THẬT (`trading/real_orders.py`)

### Task 2 (P1): Fail-safe độ cũ vị thế (`account_position_snapshot`)
- Đã thêm `POSITION_MAX_AGE_MINUTES = 15`.
- Đã thêm kiểm tra `pos_sync_ts = storage.read_position_sync_ts(cfg.real_order_account)` ở đầu cả 2 call site: `handle_crossover` và `handle_stop_touch`.
- Nếu `pos_sync_ts is None` hoặc `pos_age_min > 15` $\rightarrow$ phát alert `CRITICAL` và từ chối xử lý lệnh ngay lập tức.

### Task 5 (E): Trần 100 cổ phiếu cho lệnh MUA thật
- Đã thêm `MAX_REAL_BUY_QTY = 100`.
- Tại nhánh BUY của `handle_crossover`: `qty = min(sized.qty, max_buy_qty, MAX_REAL_BUY_QTY) // risk.lot_size * risk.lot_size`.
- **CHỈ áp dụng cho lệnh MUA**, tuyệt đối KHÔNG áp dụng cho nhánh SELL (`sellable_qty`) và `handle_stop_touch` để tránh nhốt vị thế.

---

## 3. TASK 4: CẢNH BÁO CẠN LỊCH NGHỈ LỄ TRONG `scripts/heartbeat_check.py`

- Đã thêm hàm thuần `check_holiday_exhaustion(holidays: frozenset[date] | set[date], now: datetime) -> str | None`.
- **Luật:** Phát cảnh báo `[WARN]` khi không còn ngày lễ `>= today` trong config VÀ `today >= 01/10` (`(now.month, now.day) >= (10, 1)`).
- **Lý do mốc 01/10:** Trước tháng 10 lịch năm sau chưa công bố chính thức, cảnh báo lúc đó là nhiễu vô ích. Từ 01/10 trở đi thông báo chính thức bắt đầu ra, cảnh báo mới có tác dụng hành động.
- Đã tích hợp gọi `check_holiday_exhaustion` vào `main()` của `heartbeat_check.py`.

---

## 4. TASK 3: DỰNG LẠI IMAGE DOCKER & KIỂM TRA DRIFT

### A. Output đo Drift trước khi dựng:
```
$ uv run python scripts/deploy_drift_check.py
[deploy-drift] collector: image CŨ hơn commit gần nhất chạm trading/ (1 ngày 14 giờ) — dựng lại container (docker compose build collector engine && docker compose up -d --no-deps collector engine)
[deploy-drift] engine: image CŨ hơn commit gần nhất chạm trading/ (1 ngày 14 giờ) — dựng lại container (docker compose build collector engine && docker compose up -d --no-deps collector engine)
(Exit code: 1)
```

### B. Lệnh dựng lại đã chạy:
```powershell
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

### C. Output kiểm tra sau khi dựng:
```
$ uv run python scripts/deploy_drift_check.py
OK: không lệch triển khai — image của collector và engine mới hơn commit gần nhất chạm trading/
(Exit code: 0)
```

### D. Trạng thái Docker Containers (`docker ps`):
```
CONTAINER ID   IMAGE                               COMMAND                  CREATED          STATUS                 PORTS                      NAMES
fcb45a7757c8   ai_auto_trading_system-collector    "python -m trading.c…"   11 seconds ago   Up 9 seconds                                      ai_auto_trading_system-collector-1
9738a62fddb3   ai_auto_trading_system-engine       "python -m trading.e…"   11 seconds ago   Up 9 seconds                                      ai_auto_trading_system-engine-1
6b15161249e2   timescale/timescaledb:latest-pg16   "docker-entrypoint.s…"   4 days ago       Up 6 hours (healthy)   127.0.0.1:5432->5432/tcp   ai_auto_trading_system-postgres-1
65a74a6f298d   nats:2.10-alpine                    "docker-entrypoint.s…"   4 days ago       Up 6 hours             127.0.0.1:4222->4222/tcp   ai_auto_trading_system-nats-1
a4f4e24ad647   nats:2.10-alpine                    "docker-entrypoint.s…"   6 days ago       Up 6 hours             127.0.0.1:4223->4222/tcp   ai_auto_trading_system-nats-test-1
ce58d7e8ade8   grafana/grafana:11.2.0              "/run.sh"                3 weeks ago      Up 6 hours             127.0.0.1:3000->3000/tcp   ai_auto_trading_system-grafana-1
```
(Tất cả 6/6 containers đều Up bình thường).

### E. Kiểm tra `heartbeat_check.py` sau khi dựng:
```
$ $env:DB_DSN="postgresql://trading:trading_pass@localhost:5432/trading_db"; uv run python scripts/heartbeat_check.py
(Exit code: 0 - Xanh hoàn toàn)
```

---

## 5. BẰNG CHỨNG PHÁ HOẠI (SABOTAGE VERIFICATION)

### A. Phá hoại Task 2 (Bỏ kiểm tra `pos_sync_ts`):
- **Thao tác:** Tạm thời comment đoạn kiểm tra `pos_sync_ts` trong `handle_crossover`.
- **Output đỏ thô:**
```
$ uv run pytest tests/test_real_orders.py -k position_sync
================================== FAILURES ===================================
____________ test_crossover_position_sync_stale_rejected_critical _____________
        storage.create_pending_order.assert_not_called()
        mock_alert.assert_called_once()
        assert mock_alert.call_args.args[0] == "CRITICAL"
>       assert "vị thế" in mock_alert.call_args.args[1] or "vi the" in mock_alert.call_args.args[1]
E       AssertionError: assert ('vị thế' in 'sức mua VCB cu 69145 phút (nguong 15) — TU CHOI lenh BUY that (fail-safe, khong dat lenh tren so lieu cu)' or 'vi the' in 'sức mua VCB cu 69145 phút (nguong 15) — TU CHOI lenh BUY that (fail-safe, khong dat lenh tren so lieu cu)')

tests\test_real_orders.py:425: AssertionError
_____________ test_crossover_position_sync_none_rejected_critical _____________
        storage.create_pending_order.assert_not_called()
        mock_alert.assert_called_once()
        assert mock_alert.call_args.args[0] == "CRITICAL"
>       assert "chua tung dong bo" in mock_alert.call_args.args[1]
E       AssertionError: assert 'chua tung dong bo' in 'sức mua VCB cu 69145 phút (nguong 15) — TU CHOI lenh BUY that (fail-safe, khong dat lenh tren so lieu cu)'

tests\test_real_orders.py:442: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_real_orders.py::test_crossover_position_sync_stale_rejected_critical
FAILED tests/test_real_orders.py::test_crossover_position_sync_none_rejected_critical
================= 2 failed, 4 passed, 18 deselected in 0.36s ==================
```
- **Khôi phục:** Đã khôi phục hoàn chỉnh.

### B. Phá hoại Task 4 (Bỏ điều kiện mốc `01/10` trong `check_holiday_exhaustion`):
- **Thao tác:** Tạm thời comment `if (today.month, today.day) < (10, 1): return None`.
- **Output đỏ thô:**
```
$ uv run pytest tests/test_heartbeat_check.py -k holiday_exhaustion
================================== FAILURES ===================================
_______________ test_holiday_exhaustion_before_october_no_alarm _______________
    def test_holiday_exhaustion_before_october_no_alarm():
        now = datetime(2026, 9, 15, 10, 0, tzinfo=TZ)
        past_holidays = frozenset({date(2026, 1, 1), date(2026, 9, 2)})
>       assert check_holiday_exhaustion(past_holidays, now) is None
E       AssertionError: assert '[WARN] lịch nghỉ lễ trong config/config.yaml đã cạn (không còn ngày lễ >= hôm nay) — cần cập nhật lịch nghỉ giao dịch năm mới của HOSE/HNX (lấy ngày sàn đóng cửa, lưu ý ngày nghỉ bù/liền kề) vào config.yaml' is None

tests\test_heartbeat_check.py:537: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_heartbeat_check.py::test_holiday_exhaustion_before_october_no_alarm
================= 1 failed, 3 passed, 34 deselected in 0.39s ==================
```
- **Khôi phục:** Đã khôi phục hoàn chỉnh.

### C. Phá hoại Task 5 (Bỏ `MAX_REAL_BUY_QTY` khỏi `min(...)`):
- **Thao tác:** Tạm thời đổi `qty = min(sized.qty, max_buy_qty, MAX_REAL_BUY_QTY)` thành `qty = min(sized.qty, max_buy_qty)`.
- **Output đỏ thô:**
```
$ uv run pytest tests/test_real_orders.py -k task5
================================== FAILURES ===================================
_________________ test_task5_buy_capped_at_100_when_sized_500 _________________
        storage.create_pending_order.assert_called_once()
>       assert storage.create_pending_order.call_args.kwargs["quantity"] == 100
E       assert 2000 == 100

tests\test_real_orders.py:527: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_real_orders.py::test_task5_buy_capped_at_100_when_sized_500
================= 1 failed, 3 passed, 20 deselected in 0.34s ==================
```
- **Khôi phục:** Đã khôi phục hoàn chỉnh.

### D. Xác nhận không còn chuỗi SABOTAGE:
- Chạy grep search: Không tìm thấy bất kỳ dấu vết "SABOTAGE" nào trong `trading/`, `tests/`, `scripts/`.

---

## 6. KẾT QUẢ KIỂM THỬ TOÀN DIỆN & LINT

### A. Ruff Linter:
```
$ uv run ruff check trading tests scripts
All checks passed!
```

### B. Unit Test Suite:
```
$ uv run pytest -m "not integration" -q
........................................................................ [ 14%]
........................................................................ [ 29%]
........................................................................ [ 43%]
........................................................................ [ 58%]
........................................................................ [ 72%]
........................................................................ [ 87%]
................................................................         [100%]
496 passed, 100 deselected in 7.32s
```
*(Số test pass tăng từ 482 lên **496 passed**, 0 failed).*

---

## 7. XÁC NHẬN TUÂN THỦ RÀNG BUỘC
- [x] Không commit, không push git.
- [x] Không sửa `config/config.yaml`, không sửa `.env`.
- [x] Không sửa `_default_strategy()`, `PaperBroker`, `trading/strategies/*`, `trading/metrics.py`, `trading/sampling.py`.
- [x] `real_trading_enabled` giữ nguyên `false`.
- [x] Không gọi API đặt/huỷ lệnh thật SSI, không xoá DB.
