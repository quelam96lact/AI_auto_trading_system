# Brief đợt 128 — gộp chunk `bars_daily` (560 → ~11) và bỏ 4 chỉ mục trùng

**Base commit:** HEAD lúc nhận brief (sau đợt 127).
**Người thực thi:** agent (phần code và diễn tập trên DB **nháp**). **Người chạy trên DB thật, audit, commit, push:** Claude, trong **cửa sổ bảo trì cuối tuần**.

---

## §0. Bối cảnh — số đo của Claude ngày 29/09 (chỉ đọc)

DB `trading` nặng 985 MB. Với cỡ này, **gần như mọi thứ đã đủ nhanh**. Truy vấn cửa sổ gần của engine và daily-check chạy **2 ms**; tham số Postgres hợp lý (`shared_buffers` ≈ 1,9 GB, `random_page_cost` 1,1). **Không** cần nén, partition thêm, hay đổi CSDL.

Có đúng hai chỗ hỏng:

**1. `bars_daily` bị chia 560 chunk × 7 ngày** (mặc định của `create_hypertable`, `trading/storage/schema.sql:41`). Mỗi chunk chỉ khoảng 0,85 MB. Mọi truy vấn **không giới hạn thời gian** phải lập kế hoạch qua cả 560 chunk:

| Truy vấn | Planning | Execution |
|---|---|---|
| `SELECT ts, close FROM bars_daily WHERE symbol='FPT' ORDER BY ts` (kiểu script đo; 2.680 dòng), 3 lần | **503 / 490 / 446 ms** | 27 / 27 / 28 ms |
| `read_last_close` (`trading/storage/db.py:362`, gọi trong `compute_nav` **mỗi lần đồng bộ, mỗi mã**), 2 lần | **404 / 527 ms** | 11 / 7 ms |
| Cửa sổ 30 ngày gần nhất | 1,1 ms | 2,1 ms |
| Để so: `bars` (5 phút, 26 chunk), cùng kiểu `read_last_close` | 16–21 ms | 0,4–7 ms |

Tức là **94% thời gian** của mỗi truy vấn đọc lịch sử là lập kế hoạch. Collector trả nó ở mỗi nhịp đồng bộ NAV; các script đo trả nó ở mỗi mã (1.554 mã × ~0,47 s ≈ 12 phút chỉ để lập kế hoạch). Trên VPS có ít CPU hơn máy này, con số sẽ tệ hơn.

**2. Bốn chỉ mục trùng khít khoá chính**, tổng **73 MB**, làm mỗi lần ghi phải cập nhật hai cây giống hệt nhau:

| Bảng | Khoá chính | Chỉ mục trùng | Nơi tạo |
|---|---|---|---|
| `bars_crypto` | `(symbol, interval, ts)` | `idx_bars_crypto_sym_int_ts` (33 MB) | `scripts/bingx_klines.py` (hàm tạo bảng, khoảng dòng 56) |
| `binance_klines` | `(symbol, interval, ts)` | `idx_binance_klines_sym_int_ts` (31 MB) | `scripts/binance_vision.py` (~62) |
| `binance_metrics` | `(symbol, ts)` | `idx_binance_metrics_sym_ts` (8,8 MB) | `scripts/binance_vision.py` (~88) |
| `binance_funding` | `(symbol, funding_time)` | `idx_binance_funding_sym_time` | `scripts/binance_vision.py` (~74) |

Claude đã đọc quanh cả bốn chỗ: **không có chú thích** nào giải thích lý do. Nếu agent thấy một lý do mà Claude bỏ sót, **dừng và báo**.

**Đã kiểm, không có:** view, continuous aggregate, khoá ngoại, trigger, hay job Timescale nào phụ thuộc `bars_daily`; test cũng không nhắc tên các chỉ mục trên. **TimescaleDB 2.27.2 có sẵn** `merge_chunks(regclass[])`, `merge_chunks_concurrently(regclass[])` và `set_chunk_time_interval`. Vậy **không cần** dựng bảng mới rồi đổi tên.

---

## §1. Việc agent làm (code và DB nháp, không đụng DB `trading`)

### 1a. `trading/storage/schema.sql`

- `bars_daily`: thêm `chunk_time_interval => INTERVAL '1 year'` vào `create_hypertable`. Ước lượng khoảng 390 nghìn dòng/năm, tức khoảng 60 MB một chunk: đủ lớn để ít chunk, đủ nhỏ để nằm gọn trong bộ nhớ.
- `bars` và `bars_derivative`: thêm `chunk_time_interval => INTERVAL '30 days'`. Hiện tại chưa hỏng (16–21 ms), nhưng sẽ thành `bars_daily` thứ hai sau vài năm 24/7 trên VPS.
- `if_not_exists => TRUE` khiến dòng này **không** đổi gì trên DB đã có, nên §2 vẫn cần. Ghi chú ngắn ngay tại chỗ, trỏ về brief này.

### 1b. Bỏ 4 lệnh `CREATE INDEX` trùng

Xoá đúng bốn lệnh trong `scripts/bingx_klines.py` và `scripts/binance_vision.py`. **Không** đụng phần còn lại của các hàm tạo bảng. Chạy `npx gitnexus impact <tên hàm tạo bảng> --repo AI_auto_trading_system` cho từng hàm trước khi sửa.

### 1c. Script bảo trì `scripts/merge_bars_daily_chunks.py`

- **Mặc định chỉ in kế hoạch** (dry-run): danh sách nhóm chunk theo **năm của `range_start`**, số chunk mỗi nhóm, và tổng số chunk trước → sau. Chỉ thực thi khi có `--apply`.
- Tham số `--dsn` là **bắt buộc**, không mặc định. Script tự từ chối nếu tên DB là `trading` mà **thiếu** `--i-am-claude-in-maintenance-window`. Mục đích: một lần gõ nhầm của agent không chạm được DB thật.
- Làm theo đúng thứ tự:
  1. `set_chunk_time_interval('bars_daily', INTERVAL '1 year')`;
  2. `merge_chunks` từng nhóm năm, **mỗi nhóm một transaction**;
  3. in thời gian của từng nhóm.
- Chạy lần hai phải là **no-op** (idempotent).
- **Trước khi viết**, đọc tài liệu và chữ ký của `merge_chunks` trong 2.27.2 (`\df+ merge_chunks`), và kiểm **trên DB nháp**:
  - chunk phải liền kề hay không;
  - lock gì, và giữ bao lâu;
  - chunk gộp vượt `chunk_time_interval` có được không;
  - bản `concurrently` khác gì.
  Ghi kết quả vào báo cáo. Nếu `merge_chunks` không làm được việc này, **dừng và báo**, **không** tự chuyển sang cách dựng bảng mới rồi đổi tên.

### 1d. Diễn tập trên DB nháp `rehearsal128`

1. `CREATE DATABASE rehearsal128` trong cùng container postgres (giống `trading_test` của bộ test), rồi `CREATE EXTENSION timescaledb`.
2. Tạo `bars_daily` bằng **đúng khối DDL cũ**: 7 ngày, **không** dùng `schema.sql` đã sửa. Chép dữ liệu bằng `COPY ... TO STDOUT | psql -d rehearsal128 -c "COPY bars_daily FROM STDIN"`, chạy **trong** container (`docker compose exec -T postgres sh -c '...'`), không qua đường ống PowerShell. `COPY` từ DB `trading` là **đọc**.
3. **Kiểm bố cục trước khi gộp:** số chunk phải bằng **560**, bằng DB thật. Khác thì bố cục không tái lập được, nên số đo phía sau không đại diện cho DB thật. Dừng và báo.
4. Tạo lại `bars_daily_ts_idx (ts DESC)` như DB thật. Kiểm `\d bars_daily` giống DB thật.
5. **Ghi mốc trước** (xem §3): số dòng, checksum, planning và execution của 2 truy vấn mốc (mỗi truy vấn 3 lần).
6. Chạy script: dry-run, rồi `--apply`, rồi `--apply` lần hai (phải no-op).
7. **Ghi mốc sau.** So với cổng §3.
8. **Giả lập người ghi sau khi gộp:** chèn một dòng cho `ts` = ngày mai (chunk **mới** phải có khoảng 1 năm) và một dòng giữa năm 2020 (phải rơi vào chunk đã gộp). Đọc lại cả hai, rồi xoá cả hai.
9. `DROP DATABASE rehearsal128`. Kiểm `\l` không còn.

### 1e. Bộ test

`uv run pytest -q` đầy đủ. Bộ test tạo `trading_test` từ `schema.sql` **đã sửa**, nên đây là phép kiểm rằng DDL mới chạy được.

---

## §2. Việc Claude làm trên DB thật (KHÔNG phải agent), cửa sổ thứ Bảy 03/10

1. Sao lưu `pg_dump -Fc` **ra ngoài repo**, đếm dòng mốc.
2. `set_chunk_time_interval` cho `bars` và `bars_derivative` (30 ngày; chỉ ảnh hưởng chunk mới).
3. `scripts/merge_bars_daily_chunks.py --dsn ... --apply --i-am-claude-in-maintenance-window`.
4. `DROP INDEX CONCURRENTLY` bốn chỉ mục trùng.
5. Đo lại cổng §3 trên DB thật; kiểm NAV snapshot kế tiếp của collector có ghi bình thường.
6. `ANALYZE bars_daily, bars_crypto, binance_klines, binance_metrics, binance_funding`.

Làm cuối tuần vì trong ngày giao dịch collector **có ghi** `bars_daily`, và job nạp đêm (20:30) cũng ghi.

---

## §3. Cổng — đăng ký trước, đo một lần

Hai truy vấn mốc:
- **Q1:** `SELECT ts, close FROM bars_daily WHERE symbol='FPT' ORDER BY ts`
- **Q2:** `SELECT close FROM bars_daily WHERE symbol='FPT' AND close > 0 ORDER BY ts DESC LIMIT 1`

Mỗi truy vấn chạy 3 lần; lấy **trung vị** của `Planning Time` và `Execution Time` từ `EXPLAIN (ANALYZE, SUMMARY ON, TIMING OFF, COSTS OFF)`.

| Điều kiện | Ngưỡng |
|---|---|
| Số chunk `bars_daily` sau gộp | **≤ 12** |
| `count(*)` trước = sau | bằng tuyệt đối |
| Checksum `sum(hashtextextended(symbol \|\| ts::text \|\| open::text \|\| high::text \|\| low::text \|\| close::text \|\| volume::text \|\| source, 0))` trước = sau | bằng tuyệt đối |
| Planning Q1 và Q2 (trung vị) | **< 50 ms** mỗi truy vấn |
| Execution Q1 và Q2 (trung vị) | **≤ 2 ×** trước gộp |
| `--apply` lần hai | không gộp gì, số chunk giữ nguyên |
| Chunk mới sau gộp (dòng ngày mai ở 1d.8) | `range_end - range_start` ≈ 1 năm |
| `uv run pytest -q` đầy đủ (nats-test chạy) | ≥ số passed hiện tại, 0 failed |

Không đạt một dòng nào thì báo **KHÔNG ĐẠT** kèm số đo. **Không** nới ngưỡng, **không** chạy lại để chọn lần đẹp.

---

## §4. Phạm vi

**Được sửa/tạo:** `trading/storage/schema.sql` (chỉ ba lời gọi `create_hypertable`); `scripts/bingx_klines.py`, `scripts/binance_vision.py` (chỉ xoá bốn lệnh `CREATE INDEX` trùng); `scripts/merge_bars_daily_chunks.py` (mới) và test của nó nếu cần (phần tính nhóm theo năm test được mà không cần DB); báo cáo `docs/superpowers/research/2026-09-2x-dot-128-gop-chunk-bars-daily.md`.

**KHÔNG được đụng:** DB `trading` (chỉ **đọc**: `EXPLAIN`, `show_chunks`, `COPY ... TO STDOUT`); `trading/storage/db.py` (không thêm giới hạn thời gian vào truy vấn: gộp chunk giải quyết tận gốc, còn đổi truy vấn là đổi hành vi); mọi container đang chạy; `DEPLOYMENT.md`.

## §5. Điều cấm

- **Không ghi, không `ALTER`, không `DROP` gì trên DB `trading`.** Mọi thao tác ghi chỉ trên `rehearsal128`, và phải xoá nó khi xong.
- **Không commit, không push.** Không rebuild, không restart container.
- Không đọc `.env` thật; lấy DSN theo cách `scripts/_db_common.py::resolve_dsn` đang làm.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Nếu đợt 127 (diễn tập Docker, 15:00–20:00) đang chạy, **chờ** nó dọn xong rồi mới làm 1d: cả hai cùng tranh CPU và đĩa của máy đang chạy phiên thật.

## §6. Báo cáo phải có

1. Diff của 1a, 1b, 1c; output `gitnexus impact` và `detect-changes`.
2. Kết quả tìm hiểu `merge_chunks` ở 1c: loại lock, thời gian giữ lock đo được trên `rehearsal128`, và có nên dùng bản `concurrently` không.
3. **Nguyên văn** mọi số đo của 1d và bảng cổng §3, kể cả số chunk trước gộp (phải là 560).
4. Thời gian chạy `--apply` từng nhóm năm, để Claude biết cần cửa sổ dài bao nhiêu.
5. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích quanh các dòng sửa), **báo ngay**.
