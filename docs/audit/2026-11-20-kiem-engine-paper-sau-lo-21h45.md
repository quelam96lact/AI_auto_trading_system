# Kiểm chỉ đọc engine paper (`daily-engine`) sau lỡ job 21:45 ngày 19/11

Người kiểm: Researcher. Chỉ đọc — không sửa code/cấu hình, không ghi DB, không dừng/khởi động lại container, không đọc `.env`/token.

Quy ước: **[đo]** = số lấy từ lệnh chỉ đọc tại thời điểm kiểm (~23:33–23:34 giờ VN, 20/11/2026, trên `HEAD` `358c066`); **[đọc]** = đối chiếu từ mã nguồn (`file:dòng`); **[suy luận]** = suy ra từ log và mã nguồn.

---

## 0. Tóm tắt cho Lead

1. **Vì sao lỡ lô 21:45 ngày 19/11 (và cả 20/11):** Docker tắt từ khoảng sau `18:05` ngày 19/11 đến `23:09:23` ngày 20/11 (`2026-11-19 21:45:48 container-health SKIP: docker chua chay`; các container hiện tại mới khởi động lúc `2026-11-20T16:09:23Z`) **[đo]**. Vì vậy cả hai phiên bản `evening_jobs` 21:45 ngày 19/11 và 20/11 đều không chạy.
2. **Cơ chế chạy bù khi khởi động (đợt 246) đã hoạt động đúng:** Sau khi Docker lên lúc `23:09:23` ngày 20/11, `scheduler` chạy `run_startup`:
   - `catchup` thử lần 1 lúc `23:09:31` gặp `rc=2` (Postgres đang recovery), tự thử lại sau 300 s và hoàn tất lúc `23:21:38` (`EXIT=0`, `dur=423.88s`), nạp đủ `1d`, `5m`, `foreign-flow` (`thieu: []`) **[đo]**.
   - Ngay sau đó, `daily-engine --through-yesterday` chạy lúc `23:21:38` → `23:21:49` (`EXIT=0`, `dur=11.39s`) **[đo]**.
3. **Trạng thái sổ `paper_daily_*` hiện tại (đã khớp tới hết phiên `2026-11-19`):**
   - `paper_daily_state`: `strategy = etf_deposit`, `capital = 100,000,000`, `cash = 100,015,965.36`, `realized_pnl = 15,965.36`, `last_processed_date = 2026-11-19` **[đo]**.
   - `paper_daily_nav`: 1 dòng (`2026-11-19`), `nav = 100,015,965.36`, `market_value = 0`, `n_positions = 0`, `interest = 15,965.36` **[đo]**.
   - `paper_daily_orders`: 1 lệnh chờ (`id=1`, `created_date=2026-11-19`, `E1VFVN30`, `BUY 400`, `status=pending`) **[đo]**.
   - `paper_daily_lots`: 0 dòng **[đo]**.
   - Toàn bộ phép tính lãi 1 ngày (`6%/năm`) và khối lượng lệnh `400` cổ phiếu khớp chính xác công thức trong `core.py` và `strategy.py`; các bất biến kế toán đều cân **[đo]**.
4. **Điểm còn chờ (bình thường theo thiết kế `--through-yesterday`):** Phiên `2026-11-20` đã có đủ nến trong `bars_daily` (`288/289` mã active = `99.7% >= 90%`; `E1VFVN30` có `open=32,200, close=32,500`), nhưng chưa được xử lý vì `run_startup` dùng `--through-yesterday` (`2026-11-19`) và Docker bật sau 21:45. Lệnh `BUY 400 E1VFVN30` sẽ khớp vào giá mở cửa phiên `2026-11-20` ở lần chạy `daily-engine` kế tiếp không có `--through-yesterday` (lịch tự động kế tiếp là thứ Hai `2026-11-23 21:45`, hoặc chạy tay nếu Lead muốn cập nhật ngay cuối tuần).

---

## 1. Trạng thái container, image và mốc thời gian

### 1.1. Trạng thái Docker & deploy-drift [đo]

Lệnh: `docker ps -a`, `docker inspect`, `docker image inspect`, `git log -1 -- trading/ scripts/`.

| Thành phần | Trạng thái / Thời điểm | Ghi chú |
|---|---|---|
| `HEAD` hiện tại | `358c066` (`2026-11-19 06:45:58 +07:00`) | Đã gồm `aca2fbc` (đợt 246) và `358c066` (đợt 247) |
| Image `scheduler`, `collector`, `engine` | Tạo lúc `2026-11-18T23:46:18Z` (`2026-11-19 06:46:18 +07:00`) | Mới hơn commit code gần nhất 20 s — không lệch triển khai |
| `scheduler`, `collector`, `postgres` (healthy), `nats`, `grafana` | `StartedAt = 2026-11-20T16:09:23Z` (`23:09:23 +07:00`) | Đang chạy bình thường |
| `engine` (container cũ) | `Exited (0)` từ `2026-11-14T19:07:32Z` | Đã dừng từ trước theo đợt 235 |

### 1.2. Diễn biến log 19/11 → 20/11 [đo]

- `logs/container-health.log`:
  - `2026-11-19 18:05:49 container-health start` (Docker còn chạy).
  - `2026-11-19 21:45:48 container-health SKIP: docker chua chay` → Docker tắt trong khoảng `18:05`–`21:45` ngày 19/11, tiếp tục tắt suốt ngày 20/11 (`schedule-watch`, `heartbeat-check`, `deploy-drift` đều ghi `SKIP: docker chua chay`).
- `logs/daily-engine.log`:
  - `2026-11-19 06:30:10` → `06:30:15` (`EXIT=0`, `dur=4.48s`).
  - `2026-11-19 06:46:38` → `06:46:41` (`EXIT=0`, `dur=2.87s`).
  - Không có lượt chạy lúc `21:45` ngày 19/11 và `21:45` ngày 20/11 (do Docker tắt).
  - `2026-11-20 23:21:38` → `23:21:49` (`EXIT=0`, `dur=11.39s`).
- `docker logs ai_auto_trading_system-scheduler-1` + `logs/catchup.log`:
  - `2026-11-20 23:09:31 VN` (`16:09:31Z`): `run_startup` gọi `catchup` lần 1 → `rc=2` (`FATAL: the database system is not yet accepting connections / Consistent recovery state has not been yet reached`).
  - Scheduler tự thử lại sau 300 s (`lan 2/3`) → hoàn tất `23:21:38 VN` (`EXIT=0`, `dur=423.88s`), kiểm tra sau nạp: `1d: 11 ngay, thieu: []`, `5m: 11 ngay, thieu: []`, `foreign-flow: 11 ngay, thieu: []`.
  - Ngay sau đó `run_startup` (`trading/scheduler/main.py:380-396`) gọi `python -m trading.daily_engine.runner --through-yesterday` → `EXIT=0`, `dur=11.39s`.
  - Mốc lịch kế tiếp được scheduler ghi nhận: `2026-11-23T06:40:00+07:00 (morning_catchup)`.

---

## 2. Kiểm tra dữ liệu `bars_daily` và sổ `paper_daily_*`

### 2.1. Độ phủ dữ liệu `bars_daily` [đo]

Active universe (`SELECT count(*) FROM symbol_universe WHERE is_active = true`): **289 mã**.

| Ngày VN | Số mã active có nến (`bars_daily`) | Tỷ lệ (ngưỡng sẵn sàng ≥ 90%) | `E1VFVN30` (O / H / L / C / Vol) |
|---|---:|---|---|
| `2026-11-18` | 284 / 289 | 98.3% (đạt) | `33100 / 33100 / 31500 / 32600 / 1,321,600` |
| `2026-11-19` | 283 / 289 | 97.9% (đạt) | `32600 / 32600 / 32120 / 32390 / 381,100` |
| `2026-11-20` | 288 / 289 | 99.7% (đạt) | `32200 / 32500 / 31680 / 32500 / 1,527,300` |

### 2.2. Trạng thái 4 bảng `paper_daily_*` [đo]

- **`paper_daily_state`** (`id = 1`):
  - `strategy`: `etf_deposit` (khớp `DAILY_ENGINE_STRATEGY: "etf_deposit"` tại `docker-compose.yml:140`).
  - `capital`: `100,000,000`
  - `cash`: `100,015,965.35874529`
  - `realized_pnl`: `15,965.358745284597`
  - `last_processed_date`: `2026-11-19`
  - `updated_at`: `2026-11-20 16:21:48.92076+00` (`23:21:48.92 +07:00`)
- **`paper_daily_nav`** (1 dòng):
  - `date = 2026-11-19`, `cash = 100,015,965.35874529`, `market_value = 0`, `nav = 100,015,965.35874529`, `n_positions = 0`, `interest = 15,965.358745284597`.
- **`paper_daily_orders`** (1 dòng):
  - `id = 1`, `strategy = etf_deposit`, `created_date = 2026-11-19`, `exec_date = NULL`, `symbol = E1VFVN30`, `side = BUY`, `qty = 400`, `filled_qty = 0`, `status = pending`.
- **`paper_daily_lots`**: `0` dòng.

### 2.3. Đối chiếu công thức và bất biến kế toán [đọc + đo]

1. **Khởi tạo & lãi tiền mặt (`trading/daily_engine/core.py:79-89`, `runner.py:114-117`):**
   - Với `interest = 15,965.358745284597` trên `cash = 100,000,000` ở `cash_rate = 0.06`, ta có `100,000,000 × (1.06^(1/365) − 1) = 15,965.358745284597` (đúng 1 ngày dương lịch) **[suy luận khớp đo]**: sổ đã được khởi tạo trước đó tại `last_processed_date = 2026-11-18` (trong lần chạy `2026-11-19 06:30`/`06:46`), và lượt `23:21` ngày 20/11 đã xử lý xong phiên `2026-11-19`.
2. **Khối lượng lệnh `etf_deposit` (`trading/daily_engine/strategy.py:88-93`):**
   - `target = floor(0.15 × 100,015,965.35874529 / 32,390 / 100) × 100 = floor(4.631798...) × 100 = 400` cổ phiếu `E1VFVN30` — khớp đúng dòng lệnh `id=1` đang `pending`.
3. **Bất biến kế toán:**
   - `paper_daily_state.cash == paper_daily_nav(2026-11-19).cash` (`100,015,965.35874529`).
   - `capital + realized_pnl == cash + giá_vốn_lot` (`100,000,000 + 15,965.358745284597 = 100,015,965.358745284597`, lệch làm tròn float64 `~5e-9`, `lot = 0`).
   - `nav == cash + market_value` (`100,015,965.35874529 + 0`).
   - `n_positions == 0` khớp `paper_daily_lots` rỗng.

---

## 3. Kết luận & ghi chú vận hành

- Không phát hiện lỗi dữ liệu, lỗi logic hay lệch triển khai ở `daily-engine` sau khi máy bật lại tối 20/11.
- Sổ `paper_daily_*` hiện dừng ở `2026-11-19` đúng theo cờ `--through-yesterday` của `run_startup`. Phiên `2026-11-20` đã sẵn sàng trong `bars_daily` (`288/289`) và sẽ tự động khớp lệnh `BUY 400 E1VFVN30` tại giá mở cửa `2026-11-20` (`32,200`) trong lần chạy `daily-engine` tiếp theo (lịch `evening_jobs` tối thứ Hai `2026-11-23 21:45`, hoặc chạy tay nếu cần cập nhật trước cuối tuần).
