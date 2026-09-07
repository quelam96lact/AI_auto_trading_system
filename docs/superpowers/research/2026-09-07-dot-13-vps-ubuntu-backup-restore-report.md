# Báo Cáo Nghiệm Thu Brief Đợt 13: Kiểm Chứng Sao Lưu / Phục Hồi TimescaleDB & Gỡ Hardcode Tên Container (F1, F2)

**Thời gian thực hiện**: 2026-09-07  
**Người thực hiện**: Agent thực thi  
**Mục tiêu**: Thực hiện đầy đủ 2 task kỹ thuật theo yêu cầu tại `docs/superpowers/plans/2026-09-07-danh-gia-san-sang-vps-ubuntu-va-brief-dot-13.md` để chuẩn bị go-live hệ thống an toàn trên VPS Ubuntu.

---

## TỔNG KẾT KẾT QUẢ THỰC HIỆN

| Task | Mục tiêu | Trạng thái | Ghi chú |
|---|---|---|---|
| **Task 1** | Kiểm chứng sao lưu & phục hồi TimescaleDB | **ĐẠT** | Dump 55.50 MB (> 1 MB, không dính bẫy hypertable rỗng). **15/15 bảng** khớp số dòng tuyệt đối (sau đính chính `pnl_daily`, xem §3); 3/3 hypertables & chunks khớp 100%. |

> **Phạm vi Task 1 — nói rõ cái ĐÃ và CHƯA kiểm (Claude bổ sung khi audit).**
> `scripts/verify_backup_restore.py` **không chạy `scripts/backup_db.sh`**, mà
> tự phát lại lệnh dump bên trong container (`pg_dump -U trading trading |
> gzip`). Lệnh đó **giống hệt** phần lõi của `backup_db.sh`, nên câu hỏi chính
> — *pg_dump có dính bẫy hypertable rỗng không* — đã được trả lời dứt khoát và
> đúng.
>
> Phần **chưa** kiểm: lớp vỏ của chính `backup_db.sh` — ghi file ra host qua
> ống `docker compose exec ... | gzip > file`, `mkdir -p`, và dọn bản cũ bằng
> `find -mtime`. Trên Ubuntu ống nhị phân này bình thường; nêu ra để không ai
> đọc nhầm thành "đã kiểm toàn bộ `backup_db.sh`".
| **Task 2** | Gỡ hardcode tên container F1 (`run_if_docker_up.sh`, `deploy_drift_check.py`) & Đồng bộ `DEPLOYMENT.md` (F2) | **ĐẠT (PASS 100%)** | Đã chuyển sang cơ chế suy ra từ `COMPOSE_PROJECT_NAME` / repo basename. Đã kiểm chứng chiều dương, chiều âm, sabotage test và unit tests. |

---

## CHI TIẾT TASK 1: KIỂM CHỨNG SAO LƯU & PHỤC HỒI TIMESCALEDB

### 1. Kịch bản thực thi an toàn
- **Ràng buộc an toàn**: Database thật `trading` chỉ đọc (read-only). Phục hồi vào database scratch độc lập `trading_restore_test` trong container TimescaleDB đang chạy.
- **Script kiểm chứng tự động hóa**: `scripts/verify_backup_restore.py`.

### 2. Kích thước bản dump
- **File dump**: `/tmp/trading_verify_backup.sql.gz`
- **Kích thước thực tế**: **58,195,007 bytes (~55.50 MB)**.
- **Đánh giá bẫy Hypertable**: File dump > 1 MB (đạt chuẩn) $\rightarrow$ **KHÔNG bị dính bẫy hypertable rỗng của pg_dump thông thường**. Toàn bộ dữ liệu trong các chunk được dump đầy đủ.

### 3. Bảng đối chiếu số dòng từng bảng (Source vs Restored)

| Tên bảng | Source (`trading`) | Restored (`trading_restore_test`) | Trạng thái đối chiếu |
|---|---|---|---|
| `bars` | **934,217** | **934,217** | **KHỚP 100%** |
| `bars_daily` | **2,983,253** | **2,983,253** | **KHỚP 100%** |
| `orders` | **18** | **18** | **KHỚP 100%** |
| `positions` | **3** | **3** | **KHỚP 100%** |
| `heartbeat` | **2** | **2** | **KHỚP 100%** |
| `ssi_auth_state` | **1** | **1** | **KHỚP 100%** |
| `symbol_universe` | **1,595** | **1,595** | **KHỚP 100%** |
| `account_position_snapshot` | **12,031** | **12,031** | **KHỚP 100%** |
| `account_buying_power` | **10,848** | **10,848** | **KHỚP 100%** |
| `backfill_progress` | **1,902** | **1,902** | **KHỚP 100%** |
| `account_balance_snapshot` | **4,028** | **4,028** | **KHỚP 100%** |
| `account_nav_snapshot` | **3,616** | **3,616** | **KHỚP 100%** |
| `account_sync_log` | **2** | **2** | **KHỚP 100%** |
| `pnl_daily` | **4** | **4** | **KHỚP 100%** (xem đính chính bên dưới) |
| `engine_state` | **1** | **1** | **KHỚP 100%** |

> **ĐÍNH CHÍNH — Claude bổ sung khi audit (07/09).** Bảng trên ban đầu **thiếu
> một dòng**, và cái thiếu đó che một lỗi thật:
>
> `TABLES_TO_CHECK` ghi tên bảng là `daily_pnl`, nhưng tên thật trong schema là
> **`pnl_daily`**. Query hỏi một bảng không tồn tại → `query_count` trả `-1` ở
> **cả hai** bên → phép so `-1 == -1` cho ra "KHỚP". Tức là bảng PnL thật
> **chưa từng được kiểm**, mà báo cáo vẫn hiện "khớp 100%".
>
> Hai thứ đã sửa trong `scripts/verify_backup_restore.py`:
> 1. Đúng tên bảng `pnl_daily`.
> 2. `-1` (không đọc được số dòng) giờ là **THẤT BẠI**, không còn được tính là
>    khớp — in `KHONG DO DUOC`. Hai bên bằng nhau *vì cùng không đo được* thì
>    không chứng minh điều gì cả. Đây đúng nguyên tắc mà `drift_report()` trong
>    `deploy_drift_check.py` đã theo từ trước: thiếu dữ liệu thì từ chối và báo,
>    không bao giờ rơi về giá trị dễ dãi.
>
> Claude đã tự chạy lại sau khi sửa: `pnl_daily` = **4 dòng, khớp hai bên** —
> giờ mới là kiểm thật. Kết luận tổng thể của Task 1 **không đổi**.

### 4. Kiểm tra cấu trúc Hypertables & Chunks
Truy vấn: `SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;`
- **Source (`trading`)**:
  - `bars`: 23 chunks
  - `bars_daily`: 557 chunks
- **Restored (`trading_restore_test`)**:
  - `bars`: 23 chunks
  - `bars_daily`: 557 chunks
- **Kết luận**: Hypertables được khôi phục nguyên vẹn cấu trúc và đầy đủ từng chunk.

### 5. Dọn dẹp & Xác nhận DB gốc nguyên vẹn
- Đã thực thi `DROP DATABASE trading_restore_test;` thành công.
- Đã kiểm tra lại database `trading` gốc: `bars` = **934,217** dòng (toàn vẹn 100%).

---

## CHI TIẾT TASK 2: GỠ HARDCODE TÊN CONTAINER (F1) & ĐỒNG BỘ DEPLOYMENT.MD (F2)

### 1. Các file đã chỉnh sửa
- `scripts/run_if_docker_up.sh`:
  - Đọc `PROJECT_NAME` qua `${COMPOSE_PROJECT_NAME:-$(basename "$REPO" | tr '[:upper:]' '[:lower:]' | sed -e 's/[^a-z0-9_-]/_/g')}`.
  - Cổng container mặc định: `GATE_CONTAINER="${DOCKER_GATE_CONTAINER:-$PROJECT_NAME-postgres-1}"`.
- `scripts/deploy_drift_check.py`:
  - Thêm hàm chuẩn hóa `get_container_name(service: str, project_name: str | None = None) -> str`.
  - Đọc `COMPOSE_PROJECT_NAME` từ `os.environ`, nếu không có thì lấy `repo_dir.name.lower().replace("-", "_").replace(" ", "_")`.
- `DEPLOYMENT.md`:
  - Cập nhật §8.4 (Kiểm tra cổng Docker Compose) và §10 (Kiểm tra container đang chạy) để phản ánh cơ chế tên container động theo `COMPOSE_PROJECT_NAME` / repo basename.
- `tests/test_deploy_drift_check.py`:
  - Bổ sung 3 test cases cho logic tên container.

### 2. Bằng chứng thực nghiệm (Empirical Proofs)

#### A. Chiều dương (Không hồi quy trên máy hiện tại)
Lệnh: `uv run python scripts/deploy_drift_check.py`
```text
=== KẾT QUẢ KIỂM TRA LỆCH MÃ NGUỒN VỚI IMAGE CONTAINER ===
Mốc commit HEAD hiện tại: 2026-09-07 01:21:49+00:00 (ec1ef77)

- collector : Image build lúc 2026-09-06 20:53:57+00:00 -> [CẢNH BÁO: CẦN REBUILD] Image cũ hơn commit hiện tại 4 giờ 27 phút
- engine    : Image build lúc 2026-09-06 20:54:02+00:00 -> [CẢNH BÁO: CẦN REBUILD] Image cũ hơn commit hiện tại 4 giờ 27 phút
```
-> `deploy_drift_check.py` đọc đúng image timestamps của container `ai_auto_trading_system-collector-1` và `ai_auto_trading_system-engine-1` (không ra lỗi "KHÔNG đọc được image build").

#### B. Chiều âm (Khi cấu hình tên project khác)
Lệnh giả lập: `$env:COMPOSE_PROJECT_NAME="trading"; uv run python scripts/deploy_drift_check.py`
```text
- collector : Image build lúc KHÔNG đọc được image build -> [CẢNH BÁO: CẦN REBUILD] Chưa build image hoặc không đọc được metadata
- engine    : Image build lúc KHÔNG đọc được image build -> [CẢNH BÁO: CẦN REBUILD] Chưa build image hoặc không đọc được metadata
```
-> Khi gán `COMPOSE_PROJECT_NAME=trading`, script tìm `trading-collector-1` thay vì `ai_auto_trading_system-collector-1` -> Hành vi đúng thiết kế khi chạy trên môi trường khác biệt.

#### C. Unit Tests & Danh sách Test thực tế
Lệnh: `grep -n "^def test_" tests/test_deploy_drift_check.py`
```text
13:def test_all_images_newer_than_commit_is_ok():
18:def test_engine_older_warns_engine_only():
30:def test_both_older_warns_both_services():
37:def test_none_image_is_a_warning_not_ok():
45:def test_image_equal_to_commit_is_ok():
58:def test_git_that_bai_van_phai_keu(monkeypatch):
75:def test_gui_telegram_hong_van_de_lai_dau_vet(monkeypatch, capsys):
96:def test_get_container_name_default_repo_basename(monkeypatch):
103:def test_get_container_name_with_env_compose_project_name(monkeypatch):
110:def test_get_container_name_with_explicit_project_name():
```

#### D. Kiểm chứng Sabotage (Tự phá hoại)
- Khi cố tình sửa `get_container_name` trả về `"sabotage_container"`:
  ```text
  FAILED tests/test_deploy_drift_check.py::test_get_container_name_default_repo_basename - AssertionError: assert 'sabotage_container' == 'my_repo-collector-1'
  FAILED tests/test_deploy_drift_check.py::test_get_container_name_with_env_compose_project_name - AssertionError: assert 'sabotage_container' == 'custom_prj-collector-1'
  FAILED tests/test_deploy_drift_check.py::test_get_container_name_with_explicit_project_name - AssertionError: assert 'sabotage_container' == 'prod_app-engine-1'
  3 failed, 499 passed in 10.96s
  ```
- Khôi phục code gốc -> 502 passed (100% XANH).
- Quét chuỗi `SABOTAGE`:
  `grep -rn "SABOTAGE" trading tests scripts` -> Kết quả: Rỗng (exit code 1).

#### E. Quét lại `DEPLOYMENT.md`
Lệnh: `grep -n "ai_auto_trading_system-" DEPLOYMENT.md`
```text
268:trên VPS hoặc `ai_auto_trading_system-postgres-1` trên máy dev) đang chạy hay không:
```
-> Chỉ còn 1 dòng duy nhất giải thích sự khác biệt giữa VPS và máy dev, không còn câu lệnh shell nào bị hardcode cố định.

> **"MỘT CÔNG THỨC MỘT CHỖ" — quyết định và lý do (Claude bổ sung khi audit).**
> Brief đợt 13 yêu cầu bash và Python dùng **chung một** quy tắc đặt tên, hoặc
> **nói rõ tại sao không gộp được**. Báo cáo gốc im lặng về điểm này, nên ghi
> lại ở đây.
>
> **Quyết định: cố ý giữ HAI bản, và đã dán nhãn chéo ở cả hai file.**
> Lý do: cổng Docker trong `run_if_docker_up.sh` phải chạy được **ngay cả khi
> Python/uv hỏng** — đó đúng là lúc cần nó nhất. Gọi Python để hỏi tên container
> sẽ biến một lỗi Python thành kết luận "Docker chết", tức thêm một cách mới để
> chuông chết câm (bài học `51ff6de`, đã ghi trong chính docstring của
> `deploy_drift_check.py`). Đánh đổi này đắt hơn lợi ích của việc gộp.
>
> Bù lại rủi ro lệch: cả hai file giờ có comment trỏ sang nhau và ghi rõ "đổi
> một bản thì PHẢI đổi bản kia". Claude đã tự đối chiếu output hai bản
> (07/09): cùng cho ra `ai_auto_trading_system-postgres-1`.

---

## CHẤT LƯỢNG MÃ NGUỒN VÀ KIỂM THỬ TOÀN CỤC

1. **Ruff Linter**:
   - `uv run ruff check trading tests scripts` -> **All checks passed! (0 errors)**.
2. **Pytest Suite**:
   - `uv run pytest -m "not integration" -q` -> **502 passed, 100 deselected in 11.60s**.
3. **Ràng buộc an toàn**:
   - `real_trading_enabled`: `false` (Giữ nguyên).
   - `config/config.yaml`: Không chỉnh sửa.
   - Database `trading`: Nguyên vẹn 100%, không bị ảnh hưởng.
   - Không thực hiện commit/push git tự ý (chờ Claude audit và chỉ đạo của User).
