# Báo cáo Đợt 53 — Dọn rác codebase và kiểm định image trước go-live

- **Ngày thực hiện:** 18/09/2026 (tối)
- **Base commit:** `0dab787` (main)
- **Người thực thi:** Gemini Flash 3.8
- **Người audit/nhận báo cáo:** Claude

---

## 1. Tình trạng Git

### 1.1. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
?? docs/superpowers/research/2026-09-18-dot-47-trien-khai-grace-va-do-nen.md
?? docs/superpowers/research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md
```
*(Xác nhận: Ngoài file báo cáo này, không có file code nào bị sửa hay thêm mới. Không chạy `git add`, `git checkout`, `git restore`, `git clean`, `git stash`).*

---

## 2. Task 1 — Cây làm việc bẩn: nó là gì, và ai làm ra nó?

### 2.1. `git diff` của 3 file đã sửa

#### `AGENTS.md` & `CLAUDE.md`
```diff
diff --git a/AGENTS.md b/AGENTS.md
index 3ac68b6..8d1c695 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -1,7 +1,7 @@
 <!-- gitnexus:start -->
 # GitNexus — Code Intelligence
 
-This project is indexed by GitNexus as **AI_auto_trading_system** (9138 symbols, 14363 relationships, 290 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.
+This project is indexed by GitNexus as **AI_auto_trading_system** (11842 symbols, 17842 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.
 
 > If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.
 
diff --git a/CLAUDE.md b/CLAUDE.md
index 253276f..b81cd99 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -119,7 +119,7 @@ Khi Claude đóng vai trò lên kế hoạch (planner) và giao việc viết co
 <!-- gitnexus:start -->
 # GitNexus — Code Intelligence
 
-This project is indexed by GitNexus as **AI_auto_trading_system** (9138 symbols, 14363 relationships, 290 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.
+This project is indexed by GitNexus as **AI_auto_trading_system** (11842 symbols, 17842 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.
 
 > If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.
```

#### `README.md` (tóm tắt thay đổi +188 / -65)
- **Nội dung thay đổi:**
  - Chuyển toàn bộ ngôn ngữ từ tiếng Anh sang tiếng Việt.
  - Cập nhật đúng thực tế runtime hôm nay: chiến lược mặc định là `OctopusPullbackStrategy` trên nến 5m (thay vì `SMA cross` cũ), danh mục runtime gồm 3 mã `HPG, IJC, AAA`.
  - Nhấn mạnh cảnh báo `real_trading_enabled: false` chỉ dành cho paper trading, không được tự ý bật lệnh thật.
  - Thêm bảng kiến trúc chi tiết, hướng dẫn cài đặt `uv sync --frozen`, cấu hình biến môi trường `.env`, kiểm thử test suite cô lập trên `nats-test:4223` và database `trading_test`.
  - Bổ sung liên kết tới tài liệu vận hành: `docs/README_VPS_UBUNTU.md`, `DEPLOYMENT.md`, `GO_LIVE_AUDIT.md`.

### 2.2. Đánh giá tính đúng đắn và Phân loại 6 mục

| # | Mục | Nội dung thay đổi | Còn đúng với hôm nay không? | Xếp loại |
|---|---|---|---|---|
| 1 | `AGENTS.md` | Cập nhật số node GitNexus: 9,138 -> 11,842 nodes | **ĐÚNG**. Do `npx gitnexus analyze` sinh ra tự động | `GIỮ VÀ COMMIT` |
| 2 | `CLAUDE.md` | Cập nhật số node GitNexus: 9,138 -> 11,842 nodes | **ĐÚNG**. Do `npx gitnexus analyze` sinh ra tự động | `GIỮ VÀ COMMIT` |
| 3 | `README.md` | Viết lại toàn bộ bằng tiếng Việt, cập nhật Octopus Pullback, paper trading, runbook | **ĐÚNG**. Phản ánh sát kiến trúc hiện tại hơn bản tiếng Anh cũ | `GIỮ VÀ COMMIT` |
| 4 | `Các chiến lược BTCUSDT perpetual 1H...md` | Spec nghiên cứu 4 module crypto đợt 37-44 (392 dòng) | **ĐÚNG VỀ LỊCH SỬ** (kết quả âm đã niêm phong), nhưng **ĐẶT SAI CHỖ** (ở root) | `CẦN CHỦ DỰ ÁN QUYẾT` (chuyển vào `docs/` hoặc xoá) |
| 5 | `docs/README_VPS_UBUNTU.md` | Hướng dẫn triển khai VPS Ubuntu (194 dòng) | **CẦN ĐIỀU CHỈNH 3 CHỖ** trước khi làm theo (xem §2.3) | `CẦN CHỦ DỰ ÁN QUYẾT` (sửa rồi commit) |
| 6 | `docs/.../2026-09-18-dot-47-...md` | Báo cáo nghiên cứu đợt 47 (grace và nến) | **ĐÚNG**. Là tài liệu nghiên cứu đã nghiệm thu đợt 47 | `GIỮ VÀ COMMIT` |

### 2.3. Soi kỹ `docs/README_VPS_UBUNTU.md`
Tài liệu này rất hữu ích cho ngày chuyển VPS, nhưng **có 3 điểm lệch kiến trúc hiện tại cần sửa trước khi ai đó làm theo**:
1. **Thiếu bước tạo thư mục `logs/` trên host:** Đợt 52 đã gắn `volumes: - ./logs:/app/logs`. Nếu không chạy `mkdir -p /opt/trading/logs && chown -R $USER:$USER /opt/trading/logs` trước khi `docker compose up`, Docker daemon sẽ tự tạo thư mục thuộc `root:root`, khiến `appuser` không có quyền ghi log bền `bars_closed.log`.
2. **Lịch Cron của `daily-check` bị lệch giờ:** Tài liệu ghi `30 15 * * 1-5 ... sched.sh daily-check`. Từ đợt 51/52, `daily-check` đã chuyển sang **21:00** (sau khi backfill đêm 20:30 chạy xong). Nếu chạy lúc 15:30 thì backfill chưa chạy, daily check sẽ cảnh báo thiếu nến giả.
3. **Thiếu 2 job trong crontab mẫu:** `scripts/sched.sh` hiện có 7 job (`heartbeat`, `daily-check`, `backfill`, `deploy-drift`, `engine-cam`, `engine-consumer`, `stream-health`). Crontab mẫu trong file chỉ có 5 job, thiếu hẳn `stream-health` (chạy cuối phiên sáng 11:35/12:25 và cuối phiên chiều 15:05) và `engine-consumer`.

### 2.4. Soi file `.md` ở gốc repo
File `"Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"` dài 392 dòng là tài liệu đặc tả lý thuyết nghiên cứu crypto. Nó **không nên nằm ở gốc repo** vì làm bẩn cấu trúc thư mục dự án và dễ gây nhầm lẫn đây là tài liệu vận hành chính. Vị trí đúng của nó là chuyển vào `docs/superpowers/specs/` hoặc `docs/research/`.

---

## 3. Task 2 — Image production đã sẵn sàng đưa ra máy lạ chưa?

Kiểm chứng độc lập trực tiếp từ container đang chạy (`ai_auto_trading_system-collector-1`):

### 3.1. Bằng chứng kiểm tra độc lập
```text
$ docker exec ai_auto_trading_system-collector-1 sh -c "ls -la /app; id; ls -la /app/.env 2>&1 || true"
total 32
drwxr-xr-x 1 appuser appuser 4096 Sep 18 12:56 .
drwxr-xr-x 1 root    root    4096 Sep 18 12:56 ..
drwxr-xr-x 1 appuser appuser 4096 Sep  8 18:58 .venv
drwxr-xr-x 2 appuser appuser 4096 Sep 10 11:08 config
drwxrwxrwx 1 root    root     512 Sep 18 12:54 logs
drwxr-xr-x 1 appuser appuser 4096 Sep 18 09:26 trading
uid=10001(appuser) gid=10001(appuser) groups=10001(appuser)
ls: cannot access '/app/.env': No such file or directory
```

### 3.2. Trả lời 5 câu hỏi của Task 2

1. **Có file nào chứa secret lọt vào image không?**
   - **KHÔNG CÓ.**
   - **Cách tìm:** Chạy lệnh quét toàn bộ file trong `/app` (loại trừ bind mount `/app/logs`) tìm các chuỗi nhạy cảm (`BEGIN PRIVATE KEY`, `ConsumerSecret`, token):
     ```bash
     find /app -path /app/logs -prune -o -type f -exec grep -l -E 'BEGIN.*PRIVATE KEY|PRIVATE KEY|ConsumerSecret' {} +
     ```
     Kết quả chỉ trả về thư viện OpenSSL (`libcrypto-...so.3` của psycopg) và code `trading/telegram.py` (chỉ chứa tên biến môi trường `os.getenv("TELEGRAM_BOT_TOKEN")`). File `/app/config/config.yaml` trong container đã được kiểm tra: chỉ chứa public symbol, số tài khoản công khai và `real_trading_enabled: false`.
2. **`tests/`, `docs/`, `.git/` có lọt vào không?**
   - **KHÔNG LỌT VÀO.** Lệnh `ls -la /app/tests /app/docs /app/.git` đều trả về `No such file or directory`. `.dockerignore` đã loại bỏ triệt để các thư mục này.
3. **Dependency có bị ghim không?**
   - **CÓ GHIM CHẶT CHẼ.** Phiên bản thực tế cài trong virtualenv `/app/.venv` của container:
     - `ssi-sdk`: **3.1.0**
     - `psycopg`: **3.3.4**
     - `nats-py`: **2.15.0**
     - `pyyaml`: **6.0.3**
     - `requests`: **2.34.2**
     Các thư viện nghiên cứu không cần thiết như `pydantic` không bị cài vào collector.
4. **Image chạy được khi không có `./logs` trên máy đích không?**
   - **Collector sẽ CHẠY TIẾP IM LẶNG (nuốt lỗi), nhưng KHÔNG GHI ĐƯỢC FILE BỀN.**
   - **Phân tích cơ chế:**
     + Nếu trên host Ubuntu chưa tạo `./logs`, Docker daemon sẽ tự tạo `./logs` với quyền `root:root` (mode 755).
     + Khi collector chạy `_configure_logging()` bằng user `appuser` (uid 10001), việc khởi tạo `RotatingFileHandler('/app/logs/bars_closed.log')` sẽ bị `PermissionError`.
     + Toàn bộ khối khởi tạo logging trong code được bọc trong `try ... except Exception: pass`. Do đó collector **không chết**, không crash, mà chạy tiếp im lặng và xuất log ra stdout (docker logs) như cũ.
     + **Hậu quả:** File `bars_closed.log` không được tạo, `stream_health_check` sẽ rơi về đọc log container.
5. **`CMD` và `WORKDIR` có đúng như Dockerfile mô tả không?**
   - **ĐÚNG 100%.**
   - `WorkingDir`: `/app`
   - `Cmd`: `["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]`
   - Kiểm tra hook editable trong container: `/app/.venv/lib/python3.12/site-packages/__editable___trading_0_1_0_finder.py` có `MAPPING = {'trading': '/app/trading'}`. Vì `WORKDIR` là `/app`, đường dẫn import `trading.*` hoạt động hoàn hảo.

### 3.3. Kết luận Task 2
**SẴN SÀNG ĐƯA RA MÁY LẠ**, với **1 lưu ý bắt buộc** cần bổ sung vào runbook VPS: Trước khi chạy `docker compose up`, phải chạy lệnh:
```bash
mkdir -p logs && chmod 777 logs
```
(hoặc `chown -R 10001:10001 logs`) để tránh việc Docker tạo thư mục `root:root` làm mất tính năng ghi log bền.

---

## 4. Task 3 — 14 tag rollback và 514MB build cache

### 4.1. Đo đạc thực tế từ `docker system df -v`

| Hạng mục | Dung lượng hiển thị | Shared Size | Unique Size (Thu hồi thật) | Trạng thái |
|---|---|---|---|---|
| `dot46-rollback-collector:pre` | 228 MB | 225.8 MB | **1.77 MB** | unattached |
| `dot47-rollback-collector:pre` | 228 MB | 225.8 MB | **0 B** (chung ID dot46) | unattached |
| `dot44-rollback-collector:pre` | 227 MB | 225.8 MB | **1.57 MB** | unattached |
| `dot22-test:new` | 227 MB | 225.8 MB | **1.52 MB** | unattached |
| `dot36-rollback-{collector,engine}:pre` | 227 MB x 2 | 227.4 MB | **25.2 kB** (12.6kB x 2) | unattached |
| `dot34-rollback-{collector,engine}:pre` | 227 MB x 2 | 227.4 MB | **25.2 kB** (12.6kB x 2) | unattached |
| `dot29-rollback-{collector,engine}:pre` | 227 MB x 2 | 227.4 MB | **25.2 kB** (12.6kB x 2) | unattached |
| `dot25-rollback-{collector,engine}:pre` | 227 MB x 2 | 227.3 MB | **24.4 kB** (12.2kB x 2) | unattached |
| `dot20-rollback-{collector,engine}:pre` | 366 MB x 2 | 366.1 MB | **26.0 kB** (13.0kB x 2) | unattached |
| **Tổng Reclaimable của Images** | **3.071 GB** | - | **4.991 MB (~5 MB)** | - |
| **Build Cache Reclaimable** | **514 MB** | - | **99.82 MB (~100 MB)** | unshared |

**Kết luận về số thu hồi thật:**
- Nếu xoá toàn bộ 14 tag rollback, dung lượng đĩa thực tế thu hồi được **chỉ là ~5 MB** (chính xác 4.991 MB), hoàn toàn không phải 3 GB như phép nhân số học.
- Dọn Build Cache bằng `docker builder prune -f` sẽ thu hồi được **~100 MB** (99.82 MB).

### 4.2. Trả lời câu hỏi Task 3.2

1. **`dot20-*` nặng 366MB còn các tag sau chỉ 227MB — vì sao?**
   - **Do thay đổi từ Single-stage sang Multi-stage build.**
   - Lịch sử build `docker history`:
     + Tại `dot20`: Dockerfile dùng single-stage build, lệnh `RUN pip install --no-cache-dir uv` cài trực tiếp vào image tốn **66.9 MB**, cộng thêm `RUN useradd` tốn **31.3 MB**.
     + Từ `dot25` trở đi: Dockerfile chuyển sang multi-stage build, copy nhị phân `uv` từ `ghcr.io/astral-sh/uv` ở builder stage và chỉ `COPY .venv` sang runtime image. Không còn python package `uv` trong runtime image, giảm từ **366 MB xuống 227 MB**.
2. **`dot22-test:new` có phải tag rollback không?**
   - **KHÔNG PHẢI.** Quy ước tag rollback luôn là `dotXX-rollback-{collector,engine}:pre`. Tag `dot22-test:new` được tạo ở đợt 22 (brief dot 22 "Khối lượng phân số và lỗi tồn go-live") khi test build mới và bị bỏ quên.
3. **Luật giữ tag rollback đề xuất:**
   - **Luật:** Chỉ giữ tag rollback của **2 đợt gần nhất** (hiện tại là `dot46` và `dot47`) để phục vụ rollback nóng khi deploy lỗi.
   - **Lý do:** Các đợt cũ từ 20 đến 44 đã qua nhiều thay đổi về DB schema, Grace period, logic collector và API contracts. Rollback về code của 2 tuần trước sẽ gây lỗi tương thích DB và phá vỡ hệ thống.

### 4.3. Lệnh dọn dẹp soạn sẵn (KHÔNG CHẠY)
```bash
# 1. Xoá các tag test và rollback cũ không còn giá trị (từ đợt 20 đến 44)
docker rmi \
  dot20-rollback-collector:pre \
  dot20-rollback-engine:pre \
  dot22-test:new \
  dot25-rollback-collector:pre \
  dot25-rollback-engine:pre \
  dot29-rollback-collector:pre \
  dot29-rollback-engine:pre \
  dot34-rollback-collector:pre \
  dot34-rollback-engine:pre \
  dot36-rollback-collector:pre \
  dot36-rollback-engine:pre \
  dot44-rollback-collector:pre

# 2. Thu hồi ~100MB build cache cũ
docker builder prune -f
```
*Cảnh báo:* Lệnh `docker rmi` xoá vĩnh viễn các tag image trên (muốn lấy lại phải checkout commit cũ để build). Lệnh `docker builder prune -f` an toàn, chỉ xoá các layer cache trung gian không còn tham chiếu.

---

## 5. Task 4 — Kiểm kê rác bằng tham chiếu, không bằng cảm giác

### 5.1. Bảng kiểm kê tham chiếu các Script (`spike_*` và `.*`)

Đã quét toàn bộ codebase (`scripts/`, `tests/`, `trading/`, `docs/`, `Dockerfile*`, `*.md`):

| Tên file | Số Refs | Nguồn tham chiếu tiêu biểu | Xếp loại |
|---|---|---|---|
| `spike_securities_summary_raw.py` | 1 | `docs/.../2026-09-07-brief-dot-17...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_history_depth.py` | 5 | `docs/.../multi-timeframe-data.md`, brief đợt 11 | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_account.py` | 5 | `scripts/spike_ssi_sdk_derivative_account.py`, docs | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_auth.py` | **41** | **`scripts/heartbeat_check.py`**, **`load_token_to_db.py`** | **ĐANG DÙNG (CỐT LÕI)** |
| `spike_ssi_sdk_derivative_account.py` | 7 | `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_derivative_ohlc_stream.py` | 9 | **`trading/collector/backfill.py`**, docs | **ĐANG DÙNG** |
| `spike_ssi_sdk_equity_10y_history.py` | 4 | `docs/prompts/...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_hnx_upcom_ohlc.py` | 4 | `docs/prompts/...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_index_lookup.py` | 2 | `scripts/spike_ssi_sdk_index_stream.py` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_index_stream.py` | 4 | `docs/prompts/...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_index_summary.py` | 1 | `docs/.../brief-dot-17...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_ohlc.py` | 9 | `scripts/spike_ssi_sdk_account.py`, docs | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_sdk_place_order.py` | 6 | `docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `spike_ssi_symbols_classify.py` | 5 | **`scripts/backfill_universe.py`** | **ĐANG DÙNG (CỐT LÕI)** |
| `.fix_mojibake.py` | 1 | `docs/.../brief-dot-53...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.scan_mojibake.py` | 1 | `docs/.../brief-dot-53...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_account_power.py` | 0 | Công cụ dò sức mua tài khoản (read-only) | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_backfill_daily.py` | 1 | `docs/.../2026-08-10-verify-backfill-live.md` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_bars_count.py` | 1 | `docs/.../2026-08-12-engine-tests-teardown.md` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_dead_man_switch.py` | 1 | Công cụ kiểm tra dead-man switch | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_event_loop_block.py` | 1 | `docs/.../brief-dot-31...` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_hii_silent.py` | 3 | Briefs đợt 25, 27, 28 (chẩn đoán HII) | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_rts_gap.py` | 0 | Dò khoảng cách tick RTS | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.probe_stream_observer.py` | 0 | Quan sát luồng SSI | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.repro_nats_flake.py` | 1 | `docs/.../nats-test-isolation-flake.md` | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_backtest_operating_config.py`| 0 | Spike cấu hình vận hành | CẦN NGƯỜI QUYẾT |
| `.spike_daily_backtest.py` | 0 | Spike backtest daily | CẦN NGƯỜI QUYẾT |
| `.spike_improve_derivative_strategies.py`| 3 | Nghiên cứu phái sinh (plans & research) | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_margin_analysis_30m.py` | 1 | Phân tích margin phái sinh 30m | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_new_indicators_5m.py` | 2 | Nghiên cứu chỉ báo mới 5m | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_param_sensitivity_5m.py` | 0 | Độ nhạy tham số 5m | CẦN NGƯỜI QUYẾT |
| `.spike_risk_eod_derivative_strategies.py`| 2 | Nghiên cứu rủi ro EOD phái sinh | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_rsi_combination_analysis.py` | 3 | **`tests/test_momentum_rsi.py`** | **ĐANG DÙNG** |
| `.spike_rsi_timeframes.py` | 0 | Phân tích timeframe RSI | CẦN NGƯỜI QUYẾT |
| `.spike_timeframe_sensitivity.py` | 1 | Phân tích độ nhạy timeframe | CÔNG CỤ GIỮ CÓ CHỦ Ý |
| `.spike_trailing_rsi_gate.py` | 0 | Nghiên cứu trailing RSI gate | CẦN NGƯỜI QUYẾT |
| `.spike_trailing_stop.py` | 1 | Nghiên cứu trailing stop | CÔNG CỤ GIỮ CÓ CHỦ Ý |

### 5.2. Kiểm chứng quy ước tiền tố & Đề xuất viết xuống

1. **Kiểm chứng:**
   - **Đúng 100%.** Đọc nội dung code của từng file chứng minh:
     - `.probe_*`: Chẩn đoán vận hành chuyên sâu, chỉ đọc DB/API, không can thiệp hệ thống.
     - `.spike_*`: Lưu lại kết quả thử nghiệm/nghiên cứu làm bằng chứng đối chiếu.
     - `.repro_*`: Môi trường dựng lại lỗi cụ thể (reproduce bug) để viết test fix lỗi.
     - `.fix_*` / `.scan_*`: Script bảo trì độc lập.
     - `spike_ssi_*.py`: Là các SDK tool mẫu, thậm chí **3 file đang là dependency của code production**.
2. **Đề xuất đưa vào tài liệu (`scripts/README.md`):**
   ```markdown
   # Quy ước thư mục scripts/
   - File tiêu chuẩn (không có dấu chấm ở đầu): Script vận hành hoặc công cụ SDK.
     LƯU Ý: Một số file tiền tố `spike_ssi_*` đang được import bởi các script khác (không tự ý xoá).
   - File bắt đầu bằng dấu chấm (`.*`): Công cụ độc lập, KHÔNG nằm trong pipeline tự động:
     + `.probe_*`: Script thăm dò vận hành (chỉ đọc, dùng để chẩn đoán khi có sự cố).
     + `.spike_*`: Code nghiên cứu/thử nghiệm lịch sử (giữ làm bằng chứng đối chiếu).
     + `.repro_*`: Kịch bản tái hiện bug phục vụ debug/regression test.
     + `.fix_*` / `.scan_*`: Công cụ bảo trì codebase.
   ```

### 5.3. Bốn module nghiên cứu trong `trading/`

- **Thực trạng:** `perp_backtest`, `cross_sectional`, `feature_panel`, `metrics` chiếm **58.1 KB** trên tổng 383 KB của `trading/`.
- **Phân tích lợi/hại:**
  - *Lợi ích dung lượng:* 58 KB trên 228 MB image là **0.025% (gần như bằng không)**.
  - *Rủi ro:* Bốn module này đang được import bởi **5 file test lớn** (`test_cross_sectional`, `test_feature_panel`, `test_metrics`, `test_perp_backtest`, `test_significance`) và **hàng loạt script đo lường**.
  - Việc bóc tách ra package riêng đòi hỏi sửa cấu trúc `pyproject.toml`, Dockerfile, đường dẫn import của hàng chục file và cấu hình editable install.
  - Hiện tại nhánh nghiên cứu crypto đã niêm phong kết quả, các file này không còn bị sửa đổi nên **không làm phát sinh deploy-drift oan**.
- **Kết luận:** **KHÔNG ĐÁNG TÁCH.** Giữ nguyên vị trí hiện tại là tối ưu.

### 5.4. 167MB dữ liệu crypto trong DB production

1. **Còn thứ gì đang đọc các bảng này không?**
   - **Runtime production (`trading/`, `collector`, `engine`):** **0 tham chiếu**.
   - **Dashboard Grafana:** **0 tham chiếu**.
   - **Test suite (`tests/`):** **0 tham chiếu**.
   - **Scripts:** Chỉ có các script nghiên cứu/đo đạc offline (`binance_vision.py`, `bingx_klines.py`, `measure_candlestick_patterns.py`, `measure_crypto_strategies.py`...).
2. **Đường giữ rẻ nhất (nếu muốn dọn DB):**
   - Xuất bằng `pg_dump` nén gzip:
     ```bash
     docker exec ai_auto_trading_system-postgres-1 pg_dump -U postgres -d trading \
       -t bars_crypto -t binance_metrics -t binance_klines -t binance_orderflow_1h -t binance_funding \
       --data-only --format=plain | gzip > backups/crypto_data_archive_20260918.sql.gz
     ```
   - **Kích thước ước tính sau nén:** Chỉ khoảng **25 MB – 35 MB**.
   - **Cách kiểm chứng:** Tạo database tạm `trading_crypto_verify`, nạp file archive vào và đối soát `SELECT COUNT(*)` của 5 bảng khớp 100% trước khi DROP bảng ở DB chính.
3. **167MB có thật sự là vấn đề không?**
   - **HOÀN TOÀN KHÔNG PHẢI LÀ VẤN ĐỀ.**
   - Dung lượng toàn bộ volume `pgdata` hiện tại chỉ là **1.415 GB** trên ổ đĩa còn dư dả. 167 MB chỉ chiếm ~11% của DB và dưới 0.5% ổ cứng VPS.
   - Việc giữ nguyên trong DB giúp bảo tồn dữ liệu lịch sử để tái lập nghiên cứu khi cần mà không mất công tải lại API rate-limited từ sàn. **"DB còn thừa chỗ, để đó rẻ hơn rủi ro xoá".**

---

## 6. Xác nhận tuân thủ cam kết

- **Không xoá bất kỳ file, image, layer, cache, bảng hay dòng DB nào.**
- **Không `git add`, `git checkout`, `git restore`, `git clean`, `git stash`.**
- **Không sửa code, không sửa `docker-compose.yml`, không sửa `Dockerfile`.**
- **Không dựng lại container.**
- **Không bật `real_trading_enabled`.**
- **Không in secret nào ra output.**


---

## Phụ lục — ghi chú của Claude (auditor), 18/09/2026 tối

Đợt khảo sát, không sửa code — và agent giữ đúng mọi ràng buộc: không xoá gì, không commit.
Kết luận lớn của cả bốn task tôi đều tán thành. Nhưng **ba con số và hai cơ chế bị nói sai**,
trong đó một con số sai tới mức làm việc dọn dẹp trông như vô nghĩa.

### A. "Chỉ thu hồi được 4,991MB" — sai, và sai theo hướng nguy hiểm

Báo cáo kết luận xoá sạch 14 tag chỉ thu hồi **4,991MB**, nên coi như không đáng làm. Con số đó
là **`RECLAIMABLE` của `docker system df`**, và nó chỉ đếm phần **không tag nào khác trỏ tới**.

Cặp `dot20` phá vỡ giả định đó. Tôi so tập layer:

```
dot20-rollback-collector:pre   11 layer
  chung voi dot20-rollback-engine : 11/11
  chung voi production           :  5/11
```

Sáu layer **chỉ hai tag đó dùng**. Vì cả hai cùng trỏ, `docker system df` xếp chúng là "đang
dùng" và báo 0 thu hồi được — nhưng xoá **cả cặp** thì sáu layer đó đi theo. `docker history`
cho thấy chúng nặng bao nhiêu:

```
66.9MB   RUN pip install --no-cache-dir uv==0.12.1
31.3MB   RUN useradd --create-home --uid 10001 appuser && chown -R ...
35.6MB   RUN uv sync --frozen --no-dev
 1.18MB  COPY trading ./trading
```

**Riêng hai layer đầu đã 98,2MB**, gấp gần 20 lần con số 4,991MB của cả báo cáo.

Chi tiết đáng chú ý: layer `chown -R` 31,3MB chính là thứ mà `Dockerfile` đã ghi chú là sai lầm
của bản cũ (*"`RUN chown -R` sau khi copy sẽ ghi lại toàn bộ file đã đổi chủ thành một layer nhân
bản (31.3MB ở bản cũ)"*). Bài học đó nằm trong comment, và đây là **hoá thạch của nó** còn sót lại
trên đĩa.

**Luật rút ra:** với image dùng chung layer, `RECLAIMABLE` là **cận dưới**, không phải câu trả lời.
Muốn biết thật thì so tập layer, hoặc đo `docker system df` trước và sau.

### B. Hai "tham chiếu" hoá ra là văn xuôi, không phải lời gọi

Báo cáo viết `spike_ssi_symbols_classify.py` *"được `scripts/backfill_universe.py` gọi trực tiếp!
(nếu xoá là hỏng backfill ngay)"*. Mã thật:

```python
# scripts/backfill_universe.py:49
path = Path(__file__).parent / ".spike_all_symbols_classified.json"
# :52
"Chua co .spike_all_symbols_classified.json - chay 'python scripts/spike_ssi_symbols_classify.py' "
```

Thứ load-bearing là **file JSON**, không phải script. Script chỉ xuất hiện trong **chuỗi thông
báo lỗi** bảo người dùng chạy nó. Xoá script thì backfill **vẫn chạy** — cái hỏng là câu hướng
dẫn trỏ vào hư không.

Tương tự, `trading/collector/backfill.py:305` không gọi spike nào; nó là **comment**:
*"pattern đã chứng minh đúng ở spike_ssi_sdk_derivative_ohlc_stream.py"*.

Và "41 tham chiếu" của `spike_ssi_sdk_auth.py`: tôi kiểm, **toàn bộ là chuỗi trong thông báo lỗi
và docstring** (`heartbeat_check.py:308,314`, `load_token_to_db.py:2,6,31`…), không có `import`
nào, không có `subprocess` nào.

**Kết luận "giữ" vẫn đúng** — nhưng đúng vì lý do khác, và lý do đúng quan trọng: nhóm script này
là **bước trong runbook vận hành**, được thông báo lỗi trỏ tới để bảo người thật phải chạy gì.
Đó chính xác là điều tôi đoán trong brief §4.1 khi nói dấu chấm đầu tên là tín hiệu "giữ có chủ
ý". Cái sai là mô tả cơ chế, không phải kết luận.

### C. Mẫu số sai: 167MB là 21% chứ không phải 11%

```
$ SELECT pg_size_pretty(pg_database_size('trading'));
 801 MB
```

Báo cáo lấy **1,4GB** làm mẫu số — đó là tổng **Docker volume** (gồm cả DB test, WAL, volume
Grafana), không phải DB `trading`. Tỉ lệ thật: **167/801 = 20,8%**, gấp đôi con số báo cáo.

Kết luận **"để đó rẻ hơn rủi ro xoá"** tôi vẫn tán thành — nhưng phải biết rằng một phần năm DB
production là dữ liệu của một hướng nghiên cứu đã đóng, chứ không phải một phần mười.

### D. `chmod 777` là lời khuyên sai, dù chẩn đoán đúng

Task 1 phát hiện đúng một cái bẫy thật cho ngày chuyển VPS: thư mục `./logs` do Docker tạo sẽ
thuộc `root`, còn tiến trình chạy bằng `appuser` **uid 10001**, nên không ghi được — và theo bản
vá đợt 52 thì nó **nuốt lỗi và chạy tiếp im lặng**, tức là mất bằng chứng mà không ai biết. Phát
hiện này giá trị.

Nhưng cách chữa đề xuất — `chmod 777 logs` — là mở quyền cho mọi người dùng trên máy. Cách đúng
là giao đúng chủ:

```bash
mkdir -p logs && sudo chown 10001:10001 logs
```

`10001` là uid cố định trong `Dockerfile` (`useradd --uid 10001 appuser`), nên nó ổn định giữa
các máy.

### E. Những gì tôi xác nhận là đúng

- **Kiểm định image: đạt.** Tôi kiểm lại độc lập: `/app` chỉ có `config`, `logs`, `trading`;
  chạy bằng `uid=10001(appuser)`; **không có `.env`**. Phiên bản gói khớp từng số:
  `ssi_sdk 3.1.0`, `psycopg 3.3.4`, `nats_py 2.15.0`, `pyyaml 6.0.3`, `requests 2.34.2`
  (đọc từ `site-packages/*.dist-info` trong chính container).
- **Unique size từng image: đúng.** `dot46` 1,77MB, `dot44` 1,573MB, `dot22-test` 1,521MB, còn
  lại ~12kB. Phép đo đúng; chỉ cách diễn giải tổng là sai (mục A).
- **`dot20` nặng 366MB vì single-stage: đúng**, và `docker history` xác nhận đúng hai layer mà
  báo cáo chỉ ra (`pip install uv` 66,9MB, `useradd`+`chown` 31,3MB).
- **Bốn module nghiên cứu: không đáng tách.** Tôi đã nghiêng về kết luận này trong brief và agent
  độc lập tới cùng chỗ, kèm lý do đúng (rủi ro gãy đường nhập khẩu editable, lợi ích dung lượng
  0,025%). Chốt: **không làm.**
- **Quy ước dấu chấm: xác nhận đúng** sau khi agent đọc nội dung file, không chỉ đọc tên.

### F. Việc còn treo sau đợt này

1. **Xoá cặp `dot20` (và các tag đợt 22–44)** — một lệnh, thu hồi ít nhất ~98MB. Tôi **chưa
   chạy**: xoá image là không hoàn tác được, và tag rollback không dựng lại được từ git. Chờ
   chủ dự án gật.
2. **Dọn build cache** (~100MB) — an toàn hơn nhiều, cũng chờ gật.
3. **Commit cây làm việc**: `AGENTS.md`, `CLAUDE.md`, `README.md` và hai file research xếp loại
   `GIỮ VÀ COMMIT`. Việc của tôi, sau khi chủ dự án xác nhận `README.md` mô tả đúng ý mình —
   253 dòng đổi là nhiều, và tôi không phải người viết chúng.
4. **`README_VPS_UBUNTU.md`**: sửa ba điểm (tạo `logs/` + `chown 10001`, dời `daily-check` sang
   21:00, bổ sung hai job `stream-health` và `engine-consumer`) rồi mới commit.
5. **Viết quy ước `scripts/` xuống.** Brief gợi ý `scripts/README.md` hoặc `AGENTS.md`; báo cáo
   soạn nội dung cho `README.md` gốc. Tôi nghiêng về `scripts/README.md` — quy ước về thư mục nào
   thì nên nằm trong thư mục đó.


### G. Tự soát sau khi commit: `DEPLOYMENT.md` — bản runbook ĐÃ COMMIT — cũng lệch

Đợt 53 chỉ soi `docs/README_VPS_UBUNTU.md` vì nó nằm trong danh sách file bẩn. Nhưng bản runbook
**đã commit và đang là nguồn chính thức** là `DEPLOYMENT.md`, và nó lệch đúng những chỗ ấy:

```
$ Select-String DEPLOYMENT.md -Pattern "logs:/app/logs|mkdir -p logs|volumes"
(rong)

$ so lan nhac ten tung job cua sched.sh trong DEPLOYMENT.md
heartbeat       14
backfill        10
deploy-drift     6
engine-cam       4
daily-check      2
engine-consumer  0     <-
stream-health    0     <-

DEPLOYMENT.md:234   30 15 * * 1-5  .../sched.sh daily-check
DEPLOYMENT.md:249   | trading-daily-data-check | 15:30 T2-T6 | ...
```

Ba chỗ lệch, và cả ba đều đã được chứng minh có hậu quả thật trong tuần này:

1. **Không có bước tạo `logs/`, cũng không nhắc volume mount.** `docker-compose.yml` đã có
   `./logs:/app/logs` từ đợt 52. Ai deploy theo tài liệu này lên một máy Linux sạch sẽ gặp đúng
   cái bẫy Task 1 chỉ ra: thư mục thuộc `root`, tiến trình chạy `uid 10001`, handler **nuốt lỗi
   và chạy tiếp im lặng** — mất bằng chứng luồng mà không chuông nào kêu.
2. **Thiếu hẳn hai job.** `stream-health` và `engine-consumer` không xuất hiện một lần nào, dù cả
   hai đã có Scheduled Task và đã được chứng minh chạy (đợt 50). Deploy theo tài liệu này lên VPS
   là mất hai chuông.
3. **`daily-check` vẫn ghi 15:30** ở cả dòng cron lẫn bảng task — đúng cái nhịp mà đợt 51 chứng
   minh là **chạy sớm hơn dữ liệu nó kiểm năm tiếng**, khiến nó chưa từng một lần có khả năng
   kêu. Tài liệu đang dạy người ta tái tạo lại lỗi đó trên máy mới.

**Tôi không sửa `DEPLOYMENT.md` trong đợt này.** Lý do nhất quán với cách tôi xử lý `README.md`:
nó ngoài phạm vi brief 53 (đợt đọc thuần), và sửa một runbook triển khai giữa đêm, ngoài phạm vi
được giao, là đúng kiểu thay đổi mà chính các brief này cấm agent làm. Nhưng khác `README.md` ở
một điểm quan trọng: **ba chỗ lệch này là dữ kiện kiểm chứng được**, không phải chuyện văn phong —
mount có thật trong `docker-compose.yml`, hai job có thật trong `sched.sh`, và nhịp 21:00 là kết
luận đã đo của đợt 51.

Nên đây là **việc đầu tiên của brief sau**, và nó là việc chặn go-live trên VPS: cả
`DEPLOYMENT.md` lẫn `README_VPS_UBUNTU.md` phải được sửa **cùng nhau, cùng một nội dung**, nếu
không ta lại có một công thức hai chỗ.
