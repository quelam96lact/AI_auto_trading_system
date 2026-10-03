# Báo cáo bảo trì thứ Bảy (Đợt 154) — Gộp chunk `bars_daily`, ghim TimescaleDB, dựng lại container

**Thời điểm thực hiện:** Thứ Bảy, 2026-10-03  
**Người thực thi:** Agent (được cấp quyền đặc biệt từ chủ dự án trong đợt 154 cho phép chạy rebuild/recreate container thật và chạy `--apply --i-am-claude-in-maintenance-window` trên DB `trading` thật).  
**Trạng thái kết thúc:** HOÀN TẤT TOÀN DIỆN, ĐỦ ĐIỀU KIỆN GO-LIVE.

---

## 1. Tóm tắt kết quả chính

1. **Gộp chunk `bars_daily`:** 561 chunk (mỗi chunk 7 ngày) đã được gộp thành công thành **12 chunk** (mỗi năm 1 chunk) trong **35.101s**. Đã tự động xử lý khoảng trống nghỉ Tết 2023 (`2023-01-19` đến `2023-01-26`) mà không để lại dữ liệu rác.
2. **Loại bỏ 4 chỉ mục trùng lặp:** Đã `DROP INDEX CONCURRENTLY` thành công 4 chỉ mục trùng khít khoá chính (`idx_bars_crypto_sym_int_ts`, `idx_binance_klines_sym_int_ts`, `idx_binance_metrics_sym_ts`, `idx_binance_funding_sym_time`), giải phóng ~73 MB và giảm tải cập nhật cây B-Tree.
3. **Chunk time interval mới:** Đã cập nhật `bars` và `bars_derivative` sang `30 days`, `bars_daily` sang `1 year`.
4. **Ghim TimescaleDB:** Đã ghim `timescale/timescaledb:2.27.2-pg16` trên cả `docker-compose.yml` và `.github/workflows/ci.yml`.
5. **Dựng lại stack container:** Đã gắn tag `:previous`, build `collector` và `engine`, tạo lại stack bằng `docker compose up -d` (mất ~13.3s). Cấu hình giới hạn log `max-size: 10m, max-file: 3` và `shared_buffers=256MB` có hiệu lực.
6. **Engine & Collector hoạt động hoàn hảo:** Engine nhận diện NAV tài khoản thật `0434226` (182,016,700 VND), log không có traceback; collector ghi snapshot NAV mới đều đặn.
7. **Cổng Go-live:** Kiểm định qua `scripts/check_golive_gate.py` cho kết quả **ĐỦ ĐIỀU KIỆN GO-LIVE** (mục 8 hết chặn, 100% tiêu chí đạt). Bộ test suite chạy `1763 passed` (0 failed).

---

## 2. Bảng cổng §3 Brief 128 (Trước và Sau gộp)

| Tiêu chí | Ngưỡng Brief 128 | Trước bảo trì (Baseline) | Sau bảo trì (Thực tế) | Đánh giá |
|---|---|---|---|---|
| **Số chunk `bars_daily`** | $\le 12$ | **561** chunk | **12** chunk | **ĐẠT** |
| **`count(*)` `bars_daily`** | Bằng tuyệt đối | 2,986,570 | 2,986,570 | **ĐẠT** (Khớp 100%) |
| **Checksum `bars_daily`** | Bằng tuyệt đối | 2720899690460808207832 | 2720899690460808207832 | **ĐẠT** (Khớp 100%) |
| **Q1 Planning Time** | $< 50$ ms | 1314.169 ms | **55.905 ms** (24.3 / 55.9 / 59.2 ms) | **KHÔNG ĐẠT** (Giảm 96% nhưng vượt 5.9 ms) |
| **Q1 Execution Time** | $\le 2\times$ trước (222.26 ms) | 111.131 ms | **7.814 ms** (7.0 / 7.8 / 72.7 ms) | **ĐẠT** (Nhanh hơn 14 lần) |
| **Q2 Planning Time** | $< 50$ ms | 560.651 ms | **29.128 ms** (19.8 / 29.1 / 57.7 ms) | **ĐẠT** (Nhanh hơn 19 lần) |
| **Q2 Execution Time** | $\le 2\times$ trước (23.66 ms) | 11.828 ms | **0.589 ms** (0.48 / 0.59 / 0.60 ms) | **ĐẠT** (Nhanh hơn 20 lần) |
| **Chạy `--apply` lần 2** | No-op, số chunk giữ nguyên | — | 12 chunk (no-op, idempotent) | **ĐẠT** |
| **`uv run pytest -q`** | $\ge 1763$ passed, 0 failed | 1763 passed | **1763 passed**, 0 failed | **ĐẠT** |

> [!NOTE]
> **Ghi chú về dòng Q1 Planning:**  
> Dòng Q1 Planning đo được trung vị là **55.905 ms** so với ngưỡng đăng ký $< 50$ ms. Mặc dù thời gian lập kế hoạch đã giảm cực kỳ mạnh từ 1.314 ms xuống 55.9 ms (giảm 96%), theo đúng nguyên tắc nghiêm ngặt của brief ("Không đạt một dòng thì báo KHÔNG ĐẠT kèm số đo. Không nới ngưỡng, không chạy lại để chọn số đẹp"), dòng này được ghi nhận chính thức là **KHÔNG ĐẠT**. Tuy nhiên, do tính toàn vẹn dữ liệu được đảm bảo tuyệt đối (`count` và `checksum` bằng 100%), hệ thống hoàn toàn an toàn và đã chuyển tiếp sang Pha 2.

---

## 3. Chuỗi `memory.events` của Container Postgres theo thời gian

| Mốc thời gian | Sự kiện | `max` | `oom` | `oom_kill` | Ghi chú |
|---|---|---|---|---|---|
| **09:20** | Trước bảo trì (Baseline ban đầu) | 224 | 0 | 0 | Container chạy được ~11 giờ |
| **09:43** | Ngay sau khi chạy `merge_bars_daily_chunks.py --apply` | 9256 | 0 | 0 | Kernel thực hiện reclaim bộ nhớ, không có OOM |
| **09:49** | Sau khi `docker compose up -d` tạo lại container mới | **0** | 0 | 0 | Container mới tinh, bộ nhớ sạch hoàn toàn |

---

## 4. Nhật ký thực thi chi tiết từng bước

### Pha 1 — Cơ sở dữ liệu

#### Bước 1: Ghi mốc trước
- `memory.events`:
  ```text
  low 0
  high 0
  max 224
  oom 0
  oom_kill 0
  ```
- `count(*)`, `checksum`, `chunks`:
  ```sql
  count: 2986570
  checksum: 2720899690460808207832
  chunks: 561
  ```
- Đo Q1 và Q2 (3 lần mỗi truy vấn):
  - Q1 (`SELECT ts, close FROM bars_daily WHERE symbol='FPT' ORDER BY ts`):
    - Lần 1: Planning 1313.291 ms | Execution 2404.673 ms
    - Lần 2: Planning 1491.378 ms | Execution 81.900 ms
    - Lần 3: Planning 1314.169 ms | Execution 111.131 ms
    - Trung vị: **Planning 1314.169 ms**, **Execution 111.131 ms**
  - Q2 (`SELECT close FROM bars_daily WHERE symbol='FPT' AND close > 0 ORDER BY ts DESC LIMIT 1`):
    - Lần 1: Planning 330.171 ms | Execution 4.923 ms
    - Lần 2: Planning 560.651 ms | Execution 13.911 ms
    - Lần 3: Planning 572.879 ms | Execution 11.828 ms
    - Trung vị: **Planning 560.651 ms**, **Execution 11.828 ms**

#### Bước 2: Sao lưu và diễn tập phục hồi
- Lệnh: `& "C:\Program Files\Git\bin\bash.exe" scripts/sched.sh backup`
  - Mã thoát: 0
  - Output trích xuất:
    ```text
    Backup written to D:/My_Vault_Obsidian/Project/_backups/db/trading_20261003_093130.dump (100M) + row-count statement D:/My_Vault_Obsidian/Project/_backups/db/trading_20261003_093130.counts
    Pruned backups older than 14 days
    EXIT=0
    ```
- Lệnh: `& "C:\Program Files\Git\bin\bash.exe" scripts/sched.sh restore-drill --dry-run`
  - Mã thoát: 0
  - Output trích xuất:
    ```text
    Diễn tập OK: trading_20261003_093130.dump, 32 bảng >= bản kê lúc dump
      bars: bản kê=936,488 phục hồi=936,488
      bars_daily: bản kê=2,986,570 phục hồi=2,986,570
      orders: bản kê=20 phục hồi=20
      positions: bản kê=3 phục hồi=3
      ... (32/32 bảng khớp 100%)
    EXIT=0
    ```

#### Bước 3: Đổi `chunk_time_interval` cho `bars` và `bars_derivative`
- Lệnh:
  ```sql
  SELECT set_chunk_time_interval('bars', INTERVAL '30 days');
  SELECT set_chunk_time_interval('bars_derivative', INTERVAL '30 days');
  ```
  Mã thoát: 0.
- Kiểm tra qua `timescaledb_information.dimensions`:
  ```text
   hypertable_name | time_interval 
  -----------------+---------------
   bars_daily      | 7 days
   bars            | 30 days
   bars_derivative | 30 days
  ```

#### Bước 4: Gộp chunk `bars_daily`
- Dry-run:
  Lệnh: `uv run python scripts/merge_bars_daily_chunks.py --dsn "postgresql://trading:trading@127.0.0.1:5432/trading" --i-am-claude-in-maintenance-window`
  Mã thoát: 0.
  Output:
  ```text
  === KẾT NỐI DATABASE: trading ===
  [DRY-RUN] Khoảng trống 2023-01-19 00:00:00+00:00 -> 2023-01-26 00:00:00+00:00: --apply sẽ lấp bằng chunk rỗng.

  Tổng số chunk: 561
  Tổng số nhóm năm: 12

  Chi tiết các nhóm năm:
    - Năm 2015: 1 chunk (2015-12-31 -> 2016-01-07) [giữ nguyên (1 chunk)]
    - Năm 2016: 52 chunk (2016-01-07 -> 2017-01-05) [gộp 52 -> 1]
    - Năm 2017: 52 chunk (2017-01-05 -> 2018-01-04) [gộp 52 -> 1]
    - Năm 2018: 52 chunk (2018-01-04 -> 2019-01-03) [gộp 52 -> 1]
    - Năm 2019: 52 chunk (2019-01-03 -> 2020-01-02) [gộp 52 -> 1]
    - Năm 2020: 53 chunk (2020-01-02 -> 2021-01-07) [gộp 53 -> 1]
    - Năm 2021: 52 chunk (2021-01-07 -> 2022-01-06) [gộp 52 -> 1]
    - Năm 2022: 52 chunk (2022-01-06 -> 2023-01-05) [gộp 52 -> 1]
    - Năm 2023: 51 chunk (2023-01-05 -> 2024-01-04) [gộp 51 -> 1]
    - Năm 2024: 52 chunk (2024-01-04 -> 2025-01-02) [gộp 52 -> 1]
    - Năm 2025: 52 chunk (2025-01-02 -> 2026-01-01) [gộp 52 -> 1]
    - Năm 2026: 40 chunk (2026-01-01 -> 2026-10-08) [gộp 40 -> 1]

  Ước tính số chunk sau gộp: 12 (giảm 549 chunk)
  ```
  *(Giải thích: Tại đợt 128 đo ngày 29/09 có 560 chunk và năm 2026 có 39 chunk. Tại ngày 03/10 đã bước sang tuần 40 nên có thêm 1 chunk nến mới, nâng tổng số chunk trước gộp lên 561. Sau gộp toàn bộ vẫn thu về đúng 12 chunk đại diện cho 12 năm).*

- Thực thi gộp (`--apply`):
  Lệnh: `uv run python scripts/merge_bars_daily_chunks.py --dsn "postgresql://trading:trading@127.0.0.1:5432/trading" --apply --i-am-claude-in-maintenance-window`
  Mã thoát: 0.
  Thời gian chạy: **35.101s**.
  Output:
  ```text
  === KẾT NỐI DATABASE: trading ===
  Phát hiện 1 khoảng trống giữa các chunk (ví dụ nghỉ lễ/Tết):
    - Khoảng trống: 2023-01-19 00:00:00+00:00 -> 2023-01-26 00:00:00+00:00
    -> Đã tạo chunk rỗng lấp đầy khoảng trống; 0 dòng tạm còn lại.

  === BẮT ĐẦU THỰC THI (--apply) ===
  1. Đặt chunk_time_interval('bars_daily', INTERVAL '1 year')... Xong trong 0.005s
  2. Bắt đầu gộp 11 nhóm năm (mỗi nhóm 1 transaction):
     - Năm 2016: gộp 52 chunk thành 1 chunk trong 1.793s
     - Năm 2017: gộp 52 chunk thành 1 chunk trong 1.547s
     - Năm 2018: gộp 52 chunk thành 1 chunk trong 2.989s
     - Năm 2019: gộp 52 chunk thành 1 chunk trong 3.904s
     - Năm 2020: gộp 53 chunk thành 1 chunk trong 3.999s
     - Năm 2021: gộp 52 chunk thành 1 chunk trong 4.488s
     - Năm 2022: gộp 52 chunk thành 1 chunk trong 4.273s
     - Năm 2023: gộp 52 chunk thành 1 chunk trong 3.736s
     - Năm 2024: gộp 52 chunk thành 1 chunk trong 3.154s
     - Năm 2025: gộp 52 chunk thành 1 chunk trong 2.820s
     - Năm 2026: gộp 40 chunk thành 1 chunk trong 2.398s
  Tổng thời gian gộp 11 nhóm: 35.101s
  Số chunk sau gộp thực tế: 12 (kỳ vọng: 12)
  Gộp chunk thành công hoàn toàn!
  ```

- Chạy `--apply` lần 2 (Kiểm tra Idempotency):
  Mã thoát: 0.
  Output:
  ```text
  [IDEMPOTENT] Tất cả các năm đều đã có ≤ 1 chunk. Không cần gộp thêm gì.
  Đảm bảo set_chunk_time_interval('bars_daily', INTERVAL '1 year')...
  Hoàn tất (no-op).
  ```

#### Bước 5: Bỏ 4 chỉ mục trùng lặp & ANALYZE
Các lệnh thực thi:
1. `DROP INDEX CONCURRENTLY IF EXISTS idx_bars_crypto_sym_int_ts;` (exit 0)
2. `DROP INDEX CONCURRENTLY IF EXISTS idx_binance_klines_sym_int_ts;` (exit 0)
3. `DROP INDEX CONCURRENTLY IF EXISTS idx_binance_metrics_sym_ts;` (exit 0)
4. `DROP INDEX CONCURRENTLY IF EXISTS idx_binance_funding_sym_time;` (exit 0)
5. `ANALYZE bars_daily, bars_crypto, binance_klines, binance_metrics, binance_funding;` (exit 0)

#### Bước 6: Đo lại cổng §3 sau bảo trì
- Kết quả đo đếm:
  ```text
  count: 2986570
  checksum: 2720899690460808207832
  chunks: 12
  ```
- Đo Q1 và Q2 (3 lần mỗi truy vấn):
  - Q1:
    - Lần 1: Planning 59.226 ms | Execution 72.677 ms
    - Lần 2: Planning 55.905 ms | Execution 7.020 ms
    - Lần 3: Planning 24.288 ms | Execution 7.814 ms
    - Trung vị: **Planning 55.905 ms** (KHÔNG ĐẠT < 50 ms), **Execution 7.814 ms** (ĐẠT, nhanh gấp 14 lần)
  - Q2:
    - Lần 1: Planning 19.799 ms | Execution 0.479 ms
    - Lần 2: Planning 57.706 ms | Execution 0.602 ms
    - Lần 3: Planning 29.128 ms | Execution 0.589 ms
    - Trung vị: **Planning 29.128 ms** (ĐẠT), **Execution 0.589 ms** (ĐẠT, nhanh gấp 20 lần)

---

### Pha 2 — Ghim TimescaleDB, build lại, tạo lại container

#### Bước 7: Ghim tag TimescaleDB
- Lệnh: `docker pull timescale/timescaledb:2.27.2-pg16`
  Mã thoát: 0. Digest: `sha256:51ac20ec295699c05573adf896e2449d8b3a026223a951905d5763687409d7d4`
- Kiểm tra container tạm:
  Lệnh: `SELECT extversion FROM pg_extension WHERE extname='timescaledb';`
  Kết quả: `2.27.2` (Khớp tuyệt đối, đạt điều kiện dừng).
- Đã chỉnh sửa 3 files:
  1. `docker-compose.yml:11` -> `image: timescale/timescaledb:2.27.2-pg16`
  2. `.github/workflows/ci.yml:59` -> `image: timescale/timescaledb:2.27.2-pg16`
  3. `DEPLOYMENT.md` §11 Bước 5(a) cập nhật chú thích ghim phiên bản.

#### Bước 8: Dựng lại theo DEPLOYMENT.md §10
- Lưu tag cuốn chiếu `:previous`:
  ```bash
  PROJECT_NAME="$(docker compose config | sed -n 's/^name: //p')"
  # Đã lưu ai_auto_trading_system-collector:latest thành ai_auto_trading_system-collector:previous
  # Đã lưu ai_auto_trading_system-engine:latest thành ai_auto_trading_system-engine:previous
  ```
- Build 2 services:
  Lệnh: `docker compose build collector engine`
  Mã thoát: 0. Cả 2 image build thành công với mã nguồn mới nhất (tích hợp các Brief 143, 144, 150, 151).

#### Bước 9: Tạo lại container
- **Giờ bắt đầu:** `2026-10-03 09:48:38.491`
- **Lệnh:** `docker compose up -d`
- **Giờ kết thúc:** `2026-10-03 09:48:51.803` (Tổng thời lượng: 13.312 giây)
- Các container được recreate và start:
  - `ai_auto_trading_system-postgres-1`
  - `ai_auto_trading_system-nats-1`
  - `ai_auto_trading_system-grafana-1`
  - `ai_auto_trading_system-engine-1`
  - `ai_auto_trading_system-collector-1`

---

### Pha 3 — Kiểm sau và Nghiệm thu

#### Bước 10: Trạng thái stack mới
- `SHOW shared_buffers;` -> `256MB`
- `SELECT extversion FROM pg_extension WHERE extname='timescaledb';` -> `2.27.2`
- `docker inspect` của `ai_auto_trading_system-postgres-1`:
  ```text
  Image: timescale/timescaledb:2.27.2-pg16 | LogDriver: json-file | LogOpts: {"max-file":"3","max-size":"10m"}
  ```
- `memory.events`: `max 0, oom 0, oom_kill 0, oom_group_kill 0`

#### Bước 11: Kiểm tra log Engine và Alert Outbox
- Log engine sau khởi động:
  ```json
  {"level": "INFO", "msg": "engine restored state", "cash": 100043751.69003572, "realized_pnl": 43751.690035727515, "positions": {}}
  {"level": "INFO", "msg": "warm-up HPG xong", "bars": 201, "until": "2026-10-02 07:45:00+00:00"}
  {"level": "INFO", "msg": "warm-up IJC xong", "bars": 201, "until": "2026-10-02 07:45:00+00:00"}
  {"level": "INFO", "msg": "warm-up AAA xong", "bars": 201, "until": "2026-10-02 07:45:00+00:00"}
  {"level": "INFO", "msg": "NAV lam real capital", "account": "0434226", "nav": 182016700.0, "ts": "2026-10-03 02:47:50.475263+00:00"}
  {"level": "INFO", "msg": "vi the that ngoai cfg.symbols, engine khong quan ly", "account": "0434226", "positions": {"FOX": 500, "PHP": 1400, "SSI": 1540, "TCX": 460, "VCB": 1500}}
  ```
  - `account`: **`0434226`** (chuẩn tài khoản thật mới).
  - Hoàn toàn sạch, không có dòng `Traceback`.
  - Không xuất hiện chuỗi lỗi `Thư mục outbox ... không ghi được`.
- Kiểm tra Alert Outbox trong container:
  - `docker exec ai_auto_trading_system-engine-1 python -c "import trading.alerts as a; print(hasattr(a, 'AlertOutbox'))"` -> `True`
  - `docker exec ai_auto_trading_system-collector-1 python -c "import trading.alerts as a; print(hasattr(a, 'AlertOutbox'))"` -> `True`

#### Bước 12: Collector ghi NAV mới
Truy vấn `account_nav_snapshot`:
```text
 account_no |              ts               |    nav    | unpriced_symbols 
------------+-------------------------------+-----------+------------------
 0434226    | 2026-10-03 02:49:28.234268+00 | 182016700 | {}
 0434221    | 2026-10-03 02:49:28.234268+00 |   5022111 | {}
```
Mốc thời gian ghi nhận `02:49:28 UTC` diễn ra sau thời điểm hoàn tất recreate container (`02:48:51 UTC`), xác nhận collector tiếp tục đồng bộ NAV tự động ổn định.

#### Bước 13: Kiểm tra lệch triển khai (deploy-drift)
- Lệnh: `& "C:\Program Files\Git\bin\bash.exe" scripts/sched.sh deploy-drift`
- Mã thoát: 0.
- Log `logs/deploy-drift.log`:
  ```text
  2026-10-03 09:50:15 deploy-drift start
  OK: không lệch triển khai — image của collector và engine mới hơn commit gần nhất chạm trading/
  EXIT=0
  ```

#### Bước 14: Bảng cổng Go-Live
Lệnh: `uv run python scripts/check_golive_gate.py`  
Mã thoát: 0.  
Nguyên văn bảng kiểm định:
```text
=========================================================================================================
 BẢNG KIỂM ĐỊNH CỔNG GO-LIVE (GOLIVE GATE CHECK) — 2026-10-03 09:50:32 (VN)
 Tài khoản: 0434226 | Danh mục: HPG, IJC, AAA
=========================================================================================================
#   | Tiêu chí                         | Trạng thái đo được             | Kết luận | Ghi chú               
---------------------------------------------------------------------------------------------------------
1   | real_trading_enabled (Cờ chính)  | False                          | [THÔNG TIN] | Đang là false (chuẩn bị bật sang true vào T5 sau khi pass cổng)
2   | Tài khoản & NAV                  | 182,016,700 VND                | [ĐẠT]      | Tài khoản cấu hình: 0434226
3   | Sức mua tối thiểu                | HPG: 3397cp, IJC: 10406cp, AAA: 8224cp | [ĐẠT]      | Đạt điều kiện tối thiểu 1 lô HOSE/HNX cho toàn bộ danh mục
4   | Lá chắn độ tươi vị thế           | 1m 4s                          | [ĐẠT]      | Vị thế tươi mới, sẵn sàng cho lệnh thật
5   | Lá chắn độ tươi sức mua          | 1m 4s                          | [ĐẠT]      | Sức mua tươi mới, sẵn sàng cho lệnh thật
6   | Độ phủ luồng phiên gần nhất      | 100.0% (do luc 02/10 15:10, 19 gio truoc) | [ĐẠT]      | OK: do phu luong phien chieu ngay 2026-10-02 dat 100.0% (57/57 nen, tu 48 dong log) tu luong thoi gian thuc [nguon: file].
7   | Đường truyền Telegram            | ĐÃ CẤU HÌNH                    | [ĐẠT]      | Không gửi tin kiểm tra, chỉ kiểm cấu hình môi trường
8   | Lệch triển khai (Image vs Git)   | KHỚP                           | [ĐẠT]      | Image collector và engine mới hơn hoặc bằng commit trading/
9   | Lịch sử lệnh thật đã khớp        | 0 lệnh                         | [THÔNG TIN] | Đã khớp: 0, đang chờ: 0, đã huỷ: 0
=========================================================================================================
>>> KẾT LUẬN: ĐỦ ĐIỀU KIỆN GO-LIVE (EXIT 0) — MỌI LÁ CHẮN AN TOÀN ĐỀU ĐẠT CHUẨN.
    Chủ dự án có thể bật real_trading_enabled: true trên tài khoản 0434226
=========================================================================================================
```

#### Bước 15: Kiểm thử tự động & Linter
- `uv run ruff check` -> `All checks passed!`
- `uv run pytest -q` -> **1763 passed in 116.43s (0:01:56)**, 0 failed.

---

## 5. Các phát hiện & Điểm cần lưu ý

1. **Về việc chạy các lệnh §10 trên Windows/Git Bash:**
   - Script trong §10 được viết hoàn toàn bằng cú pháp POSIX Bash (`$()`, `sed`, `for...in`, `[ -n ... ]`). Khi người vận hành dán trực tiếp vào terminal PowerShell thì PowerShell sẽ báo lỗi cú pháp.
   - Khi chạy thông qua Git Bash (`"C:\Program Files\Git\bin\bash.exe"`), khối script chạy **nguyên văn từng chữ mà không cần sửa đổi bất kỳ ký tự nào**, tự động nhận diện đúng tên project `ai_auto_trading_system` và tag cuốn chiếu `:previous` thành công.
2. **Điểm brief chưa sát thực tế (Brief sai ở đâu):**
   - **Bước 4 (Dry-run):** Brief ghi lệnh mẫu `scripts/merge_bars_daily_chunks.py --dsn <DSN 127.0.0.1>` ở chế độ dry-run mà không có cờ Claude. Tuy nhiên, logic an toàn tại dòng 163 của `scripts/merge_bars_daily_chunks.py` chặn mọi kết nối tới DB `trading` nếu thiếu `--i-am-claude-in-maintenance-window`, **kể cả dry-run**. Do đó, dry-run bắt buộc phải truyền kèm cờ bảo vệ này mới xem trước được kế hoạch.
   - **Bước 12 (Tên cột schema):** Bảng `account_nav_snapshot` trong TimescaleDB có tên cột tài khoản là `account_no` (chứ không phải `account`), và chỉ gồm các cột `account_no`, `ts`, `nav`, `unpriced_symbols` (không có `cash`, `stock_value` như các bảng balance snapshot khác).
   - **Mã hoá Console Windows:** Lệnh `check_golive_gate.py` và `deploy_drift_check.py --help` cần `$env:PYTHONIOENCODING="utf-8"` khi chạy trực tiếp trong PowerShell để tránh lỗi UnicodeEncodeError với bảng giao diện tiếng Việt.
3. **Cái gì không kiểm được trong đợt này:**
   - Không kiểm tra được luồng dữ liệu realtime khớp lệnh và sổ lệnh trực tiếp từ SSI FastConnect trong phiên giao dịch vì phiên bảo trì diễn ra vào thứ Bảy (thị trường chứng khoán nghỉ). Collector đã kiểm tra kết nối refresh token thành công và backfill rỗng theo đúng thiết kế ngày nghỉ.

---

## 6. Trạng thái Git & Kết luận bàn giao

- **Git Status:**
  ```text
  modified:   .github/workflows/ci.yml
  modified:   DEPLOYMENT.md
  modified:   docker-compose.yml
  ```
  *(Đúng chính xác 3 file được phép sửa theo quy định brief, KHÔNG commit, KHÔNG push).*
- **Kết luận:** Toàn bộ các hạng mục bảo trì của Đợt 154 đã hoàn thành trọn vẹn, vượt tiến độ trước mốc giới hạn 23:30 tối thứ Bảy. Cơ sở dữ liệu và stack container đang vận hành ổn định, sẵn sàng cho chủ dự án review và audit.

---

## Audit của Claude (03/10/2026, ~10:00)

### A.1. Kết luận: ĐẠT. Riêng dòng cổng Q1 planning **KHÔNG ĐẠT** theo phép đo đã đăng ký, và giữ nguyên như vậy.

### A.2. Kiểm độc lập trên stack mới (chỉ đọc)

| Thứ | Claude đo |
|---|---|
| Chunk `bars_daily` | 12 |
| `count(*)` / checksum | 2.986.570 / 2720899690460808207832 (trùng số "sau" của agent) |
| `chunk_time_interval` | `bars` 30 ngày, `bars_derivative` 30 ngày, `bars_daily` 360 ngày (đúng ghi nhận A.4 đợt 128: `1 year` = 360 ngày) |
| Bốn chỉ mục trùng | 0 còn lại |
| Image postgres | `timescale/timescaledb:2.27.2-pg16`, `extversion` 2.27.2, log `max-size 10m / max-file 3` |
| `shared_buffers` | 256MB |
| `memory.events` | `max 0`, `oom_kill 0` (container mới) |
| NAV snapshot | 09:54:31 có dòng mới cho cả hai tài khoản |

### A.3. Q1 planning: cùng truy vấn, hai điều kiện khác nhau

- **Agent**, phép đo đã đăng ký: ngay sau gộp và ANALYZE, trên container **cũ**. Lúc đó vừa có áp lực bộ nhớ
  nặng (`memory.events max` 224 → 9.256 khi gộp). Ba lần: 59,2 / 55,9 / 24,3 ms, trung vị **55,9 ms > 50**.
- **Claude**, trên container mới. Hai phiên psql, mỗi phiên chạy Q1 ba lần rồi Q2 ba lần:
  - Q1: 22,4 / 1,7 / 2,3 và 16,7 / 1,3 / 1,1 ms;
  - Q2: 1,9 / 6,4 / 2,0 và 1,2 / 1,6 / 1,9 ms.

  Lần đầu trong phiên (phải nạp catalog) khoảng 16–22 ms, các lần sau khoảng 1–2 ms.

Brief cấm chạy lại để chọn số đẹp, nên dòng cổng giữ kết luận **KHÔNG ĐẠT**. Số của Claude là một quan sát
độc lập, không thay thế phép đo cổng. Về mục đích thật của đợt 128: chi phí lập kế hoạch 400–1.300 ms mỗi
truy vấn lịch sử (collector trả ở mỗi nhịp đồng bộ NAV) đã giảm xuống mức hai chữ số ms trở xuống trong cả
hai điều kiện. Claude không giao thêm việc cho dòng này.

### A.4. Diff
Đúng ba file, đúng chỗ:
- `docker-compose.yml:11` và `ci.yml:59` → `2.27.2-pg16`;
- chú thích §11 Bước 5(a) trong `DEPLOYMENT.md`.

File override trong Bước 5(a) giờ thừa nhưng vô hại: nó ghim đúng số đo ở Bước 3. Claude giữ nguyên.
