# Brief đợt 231: cho phép `symbols: []` (bỏ HPG, IJC, AAA khỏi cấu hình mà không nổ, không báo động giả)

Ngày 14/11/2026. Người giao: Claude (Lead). Người làm: **Builder**. Thứ tự: sau đợt 229; trước hoặc sau đợt 227 tuỳ Builder đang dở đâu, nhưng **không** chạy xen giữa lúc khám phá 227 đang chạy.

## Bối cảnh

- Chủ dự án quyết định 13/11: không giữ HPG, IJC, AAA trong `config/config.yaml`.
- Khảo sát đợt 230 (`docs/audit/2026-11-14-khao-sat-bo-3-ma-khoi-cau-hinh.md`, bảng R-0…R-24) cho thấy đổi `symbols: []` ngay sẽ có hai chỗ nổ và ba chỗ báo động giả. **Đọc toàn bộ báo cáo đó trước khi làm.** Số dòng trong brief này lấy từ báo cáo; tự kiểm lại vì file có thể đã lệch dòng sau đợt 225.
- Mọi bản sửa dưới đây phải là **no-op khi `symbols` còn 3 mã**. `config.yaml` **không** nằm trong phạm vi của Builder: Lead đổi sau cùng.

## Việc phải làm (mỗi mục: viết test tái hiện với danh sách rỗng, rồi sửa)

| # | File | Hành vi khi rỗng hiện nay | Hành vi phải có |
|---|---|---|---|
| 1 | `scripts/heartbeat_check.py` (R-12; khối đọc DB quanh `IN ({placeholders})`) | `IN ()` lỗi SQL → CRITICAL "không đọc được DB" mỗi 5 phút, bỏ luôn kiểm nhịp và sổ sách | Rỗng: **không** chạy truy vấn `max(ts)` và **bỏ qua** phép kiểm nến cũ (2A); mọi SELECT và phép kiểm khác (nhịp `collector`/`engine`, sổ sách, token, nến ngày hôm trước…) chạy y nguyên. In một dòng INFO ra stdout "symbols rỗng: bỏ qua kiểm nến stream" |
| 2 | `scripts/startup_catchup.py` (R-16; nhánh kiểm "ngày 0 nến", hai chỗ dùng `cfg.symbols`) | `--symbols ""` → `backfill_universe` rơi sang `load_symbols`, ghi đè `is_active=false` cho ~1.600 mã | Rỗng: dùng **danh sách dò** = 3 mã có `avg_value_20d` lớn nhất trong universe đang active (đọc qua hàm Storage có sẵn; nếu không có hàm trả kèm giá trị thì dừng và báo). Danh sách dò cũng rỗng (universe trống): **bỏ qua** bước kiểm, in lý do, **không** gọi `backfill_universe`. Không bao giờ gọi `backfill_universe` với `--symbols` rỗng |
| 3 | `scripts/backfill_universe.py` (R-16, phòng tuyến thứ hai) | `--symbols ""` bị coi như không truyền | Truyền `--symbols` mà sau khi tách không còn mã nào: in lỗi, thoát 2, **không** ghi gì. Phân biệt bằng `args.symbols is not None` |
| 4 | `trading/collector/main.py` (R-1, R-2, R-3) | Feed đăng ký `topics=[]`; watchdog tưởng feed chết: ≈23 CRITICAL + ≈69 WARN mỗi ngày; WARN "không nhận snapshot" | Rỗng: **không start feed**, watchdog coi như không trong giờ giao dịch (không stale, không restart), không cảnh báo "không snapshot". Một `alert("INFO", ...)` lúc khởi động nêu rõ collector chạy không stream. Nhịp `storage.beat("collector")`, backfill, đồng bộ tài khoản/NAV, giá cho mã đang giữ chạy y nguyên |
| 5 | `scripts/stream_health_check.py` (R-18) | 0 dòng "bars closed" → CRITICAL + EXIT=2 mỗi 15:10; mẫu số cứng 3 mã ở khoảng dòng 267 | Đọc `symbols` từ `config.yaml`. Rỗng: in "symbols rỗng: bỏ qua", thoát 0, không gửi Telegram. Không rỗng: mẫu số lấy từ cấu hình thay cho bộ cứng (với 3 mã hiện tại kết quả phải **y hệt** cũ; có test so sánh) |
| 6 | `scripts/check_silent_engine.py` (R-19) | Rỗng → EXIT=2 mỗi 15:15 → schedule-watch báo THẤT BẠI | Rỗng (và không truyền `--symbols`): in "symbols rỗng: bỏ qua", thoát 0 |

Không làm trong đợt này (đã cân nhắc, Lead quyết):

- **R-17** (lần nạp 5 phút đầu kéo cửa sổ 7 ngày và ghi đè nến stream của 3 mã bằng nến REST): chấp nhận. Cùng nguồn SSI, UPSERT, không mất dữ liệu.
- **R-14** (nhánh thử lại của `daily_data_check` bị bỏ qua khi rỗng): chấp nhận, ca hiếm.
- **R-6** (sức mua theo mã ngừng cập nhật): vô hại khi `real_trading_enabled: false`; ghi chú cho đợt engine thật.
- Thêm ngày nghỉ 2027 vào `holidays`: ngoài phạm vi (chủ dự án đã bỏ việc hỏi lịch nghỉ).

## Trước khi sửa

- GitNexus impact cho các hàm sẽ sửa trong `trading/collector/main.py` (`node .gitnexus/run.cjs impact <symbol> --direction upstream --repo .`). HIGH/CRITICAL thì báo Lead trước. `scripts/` không được index: grep caller. **Không npx.**
- Khoảng 15 test trong `tests/test_heartbeat_check.py` gọi `hc.main()` và đọc `config.yaml` **thật** (báo cáo 230, R-12). Chúng sẽ đổi hành vi khi Lead đổi cấu hình. Trong đợt này: cho các test đó **tiêm `symbols` giả** (theo đúng cách các test khác trong file đang giả cấu hình) để chúng không phụ thuộc nội dung `config.yaml` thật. Đây là sửa test cũ được phép; liệt kê tên từng test đã sửa và diff.
- `tests/test_startup_catchup.py::test_main_5m_progress_ignores_stream_symbols` và các test ghim 3 mã khác: **không** sửa nếu vẫn pass với cấu hình hiện tại. Liệt kê những test sẽ lật khi `symbols: []` để Lead xử lý lúc đổi cấu hình.

## Cách làm việc: BẮT BUỘC dùng worktree riêng

`heartbeat_check.py`, `stream_health_check.py`, `check_silent_engine.py` chạy thật từ thư mục chính.

- `git worktree add ../AI_auto_trading_system-dot231 -b dot231 <main mới nhất, sau khi 229 đã merge>`. Commit trong nhánh `dot231` thì được.
- Không sửa file nào trong thư mục chính.

## Phạm vi

- **Được sửa:** sáu file ở bảng trên và file test tương ứng (`tests/test_heartbeat_check.py`, `tests/test_startup_catchup.py`, `tests/test_backfill_universe.py`, `tests/test_collector_main.py`, `tests/test_stream_health_check.py` hoặc tên đúng của nó, `tests/test_silent_engine_guard.py`).
- **Không đụng:** `config/config.yaml`, `trading/config.py`, `trading/collector/feed.py`, `trading/collector/watchdog.py` (điều kiện đặt ở `main.py`, nơi dựng watchdog và start feed; nếu không làm được mà không sửa hai file kia thì dừng và báo), `trading/engine/`, `docker-compose.yml`, `Dockerfile`, `scripts/sched.sh`, `SCHEDULE_EXIT_POLICIES`.
- Giữ style, không refactor. Thấy vấn đề khác thì báo.

## Cấm

- Sửa `config.yaml` để thử; chạy `sched.sh` hay script kiểm tra thật lên `logs/`; gửi Telegram; ghi DB thật; gọi API SSI.
- `docker compose up/stop/build`. Commit lên `main`, push, `npx`.

## Tiêu chí hoàn thành (bằng chứng gửi Lead)

1. Output impact và grep caller.
2. Với **từng** mục 1–6: tên test mới, output **trên code cũ** (thất bại) và trên code mới (pass), chép nguyên văn. Test mục 2 phải khẳng định `backfill_universe` **không được gọi** với `--symbols` rỗng (kiểm tham số của lời gọi giả).
3. Test "no-op với 3 mã": mục 5 so kết quả cũ/mới trên cùng log giả; các mục khác bằng bộ test cũ còn pass.
4. `uv run pytest tests/test_heartbeat_check.py tests/test_startup_catchup.py tests/test_backfill_universe.py tests/test_collector_main.py tests/test_silent_engine_guard.py tests/test_schedule_watch.py -q` cùng file test stream-health.
5. `uv run pytest -m "not integration" -q`: tổng pass/fail. `uv run ruff check trading tests scripts`.
6. Danh sách test sẽ lật khi `symbols: []`.
7. `git -C <worktree> log --oneline main..dot231` và `diff --stat`.
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.

## Sau đợt này (Lead làm, ghi để Builder biết bối cảnh)

Audit → merge → đổi `config.yaml` thành `symbols: []` → build lại cả ba image (collector, engine, scheduler) ngoài giờ phiên → kiểm một phiên.
