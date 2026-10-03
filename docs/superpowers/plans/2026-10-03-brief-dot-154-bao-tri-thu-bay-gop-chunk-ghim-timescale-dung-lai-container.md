# Brief đợt 154 — bảo trì thứ Bảy: gộp chunk `bars_daily`, ghim TimescaleDB, dựng lại container

## Quyền hạn đặc biệt của đợt này

Chủ dự án giao việc này cho agent ngày 03/10 ("Plan giao agent làm luôn"). Đợt này agent **được phép**
làm hai việc vốn chỉ Claude được làm, và **chỉ trong đợt này**:
- build lại image và tạo lại container của stack thật;
- chạy `scripts/merge_bars_daily_chunks.py --apply --i-am-claude-in-maintenance-window` trên DB `trading`.
  Cờ mang tên Claude, nhưng chủ dự án đã cho phép agent dùng nó cho đúng một lần chạy này. Ghi rõ điều đó
  trong báo cáo.

Mọi giới hạn khác vẫn giữ nguyên (xem cuối brief).

## Bối cảnh — Claude đo ngày 03/10, 09:20, chỉ đọc

| Thứ | Hiện trạng |
|---|---|
| `SHOW shared_buffers` | `256MB` (điều kiện tiên quyết của đợt 128: **đạt**) |
| Chunk `bars_daily` | **561**, mỗi chunk 7 ngày |
| `chunk_time_interval` | `bars`, `bars_daily`, `bars_derivative` đều 7 ngày |
| Bốn chỉ mục trùng khoá chính (đợt 128) | **còn đủ**: `idx_bars_crypto_sym_int_ts`, `idx_binance_klines_sym_int_ts`, `idx_binance_metrics_sym_ts`, `idx_binance_funding_sym_time` |
| `memory.events` của container postgres | `max 224`, `oom_kill 0`. Container chạy được khoảng 11 giờ. Sau bản sửa 29/09 con số này từng là 0 |
| TimescaleDB đang chạy | extension **2.27.2** |
| Image engine/collector | cũ hơn commit gần nhất chạm `trading/`. Các đợt 143, 144, 150, 151 **chưa có hiệu lực** |
| `docker-compose.yml:11` và `.github/workflows/ci.yml:59` | `timescale/timescaledb:latest-pg16`. Diễn tập đợt 153 cho thấy tag này giờ kéo về **2.30.2** |

Đọc trước:
- `docs/superpowers/plans/2026-09-29-brief-dot-128-gop-chunk-bars-daily-va-bo-chi-muc-trung.md`: §2 các
  bước, §3 cổng;
- phụ lục audit trong `docs/superpowers/research/2026-09-29-dot-128-gop-chunk-bars-daily.md`: lỗi
  `bridge_chunk_gaps` đã sửa; khoảng trống Tết 2023; `INTERVAL '1 year'` = 360 ngày;
- `DEPLOYMENT.md` §10 (quy trình dựng lại và quay về) và §11 Bước 5(a).

## Pha 1 — DB (stack đang chạy, chưa dựng lại gì)

Theo đúng thứ tự. Bước nào có điểm dừng mà không đạt thì **DỪNG CẢ ĐỢT**, không làm bước sau, và báo lại.

1. **Ghi mốc trước:**
   - `memory.events` (`max`, `oom_kill`) của container postgres;
   - `count(*)` và checksum `bars_daily` (công thức ở §3 brief 128);
   - số chunk;
   - Q1 và Q2 (§3 brief 128), mỗi truy vấn 3 lần, ghi trung vị planning/execution.

   Dán nguyên văn.
2. **Sao lưu và chứng minh phục hồi được:**
   - `scripts/sched.sh backup`, rồi `scripts/sched.sh restore-drill --dry-run`.
   - **Điểm dừng:** restore-drill không thoát 0, hoặc có bảng `phục_hồi < bản_kê` → DỪNG.
   - Bản sao lưu nằm trong thư mục sao lưu ngoài repo, như mọi đêm.
3. `SELECT set_chunk_time_interval('bars', INTERVAL '30 days')`, tương tự cho `bars_derivative`. Chỉ ảnh
   hưởng chunk mới. Kiểm lại bằng `timescaledb_information.dimensions`.
4. **Gộp chunk:**
   - Chạy dry-run trước: `scripts/merge_bars_daily_chunks.py --dsn <DSN 127.0.0.1>`. Dán kế hoạch. Đợt 128
     ra 560 → 12; giờ có 561 chunk, nên con số có thể khác một chút. Giải thích nếu khác.
   - Rồi chạy `--apply --i-am-claude-in-maintenance-window`.
   - Trong lúc chạy, cứ khoảng 1 phút đọc `memory.events` một lần. **Điểm dừng:** `oom_kill` tăng → DỪNG,
     báo ngay. Không thử lại.
   - Chạy `--apply` lần hai: phải là no-op.
5. `DROP INDEX CONCURRENTLY` bốn chỉ mục trùng, **từng lệnh một**; `CONCURRENTLY` không chạy được trong
   transaction. Rồi chạy `ANALYZE bars_daily, bars_crypto, binance_klines, binance_metrics, binance_funding`.
6. **Đo cổng §3 brief 128**, đủ mọi dòng trừ dòng pytest (chạy ở Pha 3):
   - số chunk ≤ 12;
   - count bằng và checksum bằng, tuyệt đối;
   - planning Q1/Q2 < 50 ms;
   - execution không quá 2 lần số trước.

   Không đạt một dòng thì báo **KHÔNG ĐẠT** kèm số đo. **Không** nới ngưỡng, **không** chạy lại để chọn số
   đẹp. Dữ liệu vẫn nguyên (count/checksum bằng) thì vẫn sang Pha 2; nếu count/checksum lệch thì **DỪNG** và
   báo, không tự khôi phục.

## Pha 2 — ghim TimescaleDB, build lại, tạo lại container

7. **Ghim tag:**
   - `docker pull timescale/timescaledb:2.27.2-pg16`;
   - chạy một container tạm từ image đó (`--rm`, không mount volume thật, không publish cổng), `CREATE
     EXTENSION timescaledb`, đọc `extversion`.
   - **Điểm dừng:** không ra `2.27.2` → DỪNG, không sửa compose.
   - Đạt thì sửa `docker-compose.yml:11` và `.github/workflows/ci.yml:59` sang `2.27.2-pg16`.
   - Sửa chú thích ở `DEPLOYMENT.md` §11 Bước 5(a): câu "compose dùng tag `latest-pg16`" giờ sai. Viết lại
     tối thiểu cho đúng: compose đã ghim; khi nâng phiên bản phải đổi tag và chạy `ALTER EXTENSION` có chủ
     đích. Giữ nguyên lệnh kiểm `extversion`.
8. **Dựng lại theo `DEPLOYMENT.md` §10, từng chữ:** gắn tag `:previous` rồi build `collector` và `engine`.
   Ghi lệnh nào trong §10 không chạy được nguyên văn trên Windows/Git Bash: đó là phát hiện.
9. **Tạo lại container:** `docker compose up -d`. Lệnh này tạo lại postgres (image ghim, giới hạn log),
   collector, engine, nats, grafana. **Không** đụng `nats-test`, vì nó thuộc profile `test`.
   - Ghi giờ bắt đầu và giờ kết thúc.
   - Tạo lại có thể sinh một cảnh báo thật từ job `container-health` (chạy mỗi 10 phút) nếu job rơi vào lúc
     container đang dừng. Đó là kỳ vọng; ghi lại nếu có, không cần chặn.
   - **Không** sửa scheduled task.

## Pha 3 — kiểm sau

10. Trên stack mới:
    - `SHOW shared_buffers` = `256MB`;
    - `extversion` = `2.27.2`;
    - `docker inspect` của postgres cho image `timescale/timescaledb:2.27.2-pg16` và log driver có
      `max-size`;
    - `memory.events` (giá trị mới sau khi tạo lại).
11. Log engine sau khởi động:
    - dòng `NAV lam real capital` với `account` = **`0434226`**;
    - không có `Traceback`;
    - hàng đợi cảnh báo (đợt 144) đã bật. Probe ghi **thành công thì im lặng**; chỉ khi hỏng mới in
      CRITICAL `Thư mục outbox ... không ghi được` (`trading/alerts.py`, khoảng dòng 320–335). Bằng chứng
      gồm hai phần:
      - log engine và collector **không** có chuỗi đó;
      - `docker exec <container> python -c "import trading.alerts as a; print(hasattr(a, 'AlertOutbox'))"`
        ra `True` cho cả hai container, tức image mới đã có code đợt 143.
12. **Collector ghi NAV lại:** chờ nhịp đồng bộ kế tiếp, khoảng 5 phút. Dòng `account_nav_snapshot` mới có
    `ts` sau giờ tạo lại.
13. `scripts/sched.sh deploy-drift` (job thật; hết lệch thì im lặng, thoát 0): không còn lệch. Chạy
    `PYTHONIOENCODING=utf-8 uv run python scripts/deploy_drift_check.py --help` trước để biết cờ. Claude
    đã chạy: script chỉ có `-h`; thiếu `PYTHONIOENCODING` thì `--help` sập vì cp1252, đừng nhầm là lỗi.
14. `uv run python scripts/check_golive_gate.py`: dán nguyên văn bảng.
    - Kỳ vọng mục 8 hết CHẶN.
    - Còn CHẶN mục nào khác thì ghi lại, không sửa.
15. `uv run pytest -q` (cần `nats-test`) ≥ **1.763 passed**, 0 failed. `ruff` sạch.

## Quay về khi hỏng

Engine hoặc collector không khởi động được sau bước 9:
- quay về theo `DEPLOYMENT.md` §10 "Quy trình quay về" (tag `:previous`);
- postgres không lên với image ghim thì trả `docker-compose.yml` về `latest-pg16` (image cũ 2.27.2 còn trong
  máy) và `docker compose up -d postgres`.

Ghi mọi bước quay về đã làm. **Không** xoá volume `pgdata` trong bất kỳ tình huống nào.

## Giới hạn (vẫn giữ)

- **KHÔNG commit, KHÔNG push.** Claude audit rồi commit thay đổi ở compose, CI và `DEPLOYMENT.md`.
- **KHÔNG** bật `real_trading_enabled`. Không chạy gì có `--send`. Không đọc giá trị `.env`. Không mở
  `scripts/.ssi_sdk_token.json`.
- **KHÔNG** `docker volume rm`, `docker system prune`, `DROP TABLE`, `TRUNCATE`, `DELETE` trên DB thật.
  Ngoại lệ duy nhất là phần `bridge_chunk_gaps` của script gộp, vốn tự xoá dòng tạm của chính nó trong
  transaction.
- Không sửa code trong `trading/` hay `scripts/`. Chỉ sửa ba file: `docker-compose.yml`, `ci.yml`,
  `DEPLOYMENT.md` (đúng chỗ đã nêu).
- **Cửa sổ:** làm xong trước **23:30 thứ Bảy 03/10**. Job `backup` chạy 02:00 Chủ nhật và
  `restore-drill` chạy 04:00. Chưa xong Pha 2 trước 23:30 thì dừng ở trạng thái ổn định gần nhất và báo.
- Không chạy khi có pytest khác đang chạy:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-154-bao-tri-thu-bay.md`. Mỗi bước gồm lệnh nguyên văn, mã thoát,
output. Thêm:
- bảng cổng §3 trước/sau;
- chuỗi `memory.events` theo thời gian;
- giờ bắt đầu/kết thúc dựng lại;
- bảng cổng go-live;
- mọi lệnh trong §10 không chạy nguyên văn được;
- brief sai ở đâu;
- cái gì không kiểm được.
