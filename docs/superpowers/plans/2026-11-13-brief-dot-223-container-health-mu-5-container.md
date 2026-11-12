# Brief đợt 223: container-health mù 5/6 container từ đợt 218 (sửa template `docker inspect`)

Ngày 13/11/2026, 00:10. Người giao: Claude (Lead). Người làm: **Builder**.

## Bối cảnh (Researcher phát hiện 12/11 23:55, Lead đã tự tái hiện)

- `scripts/container_health_check.py`, hàm `inspect_container` (~dòng 191–200), dùng template:
  `{{.Id}} {{.RestartCount}} {{.State.Status}} {{.State.OOMKilled}} {{.State.StartedAt}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}`
- Trên Docker 29.9.2 (client và server), template này lỗi với **mọi container không có healthcheck**: collector, engine, scheduler, nats, grafana. Thông báo lỗi: `template parsing error: ... at <.State.Health>: map has no entry for key "Health"`. Chỉ postgres đọc được.
- **Nguyên nhân gốc (Lead đã đo):** `{{.Id}}` là tên khoá JSON, không phải tên trường Go (`ID`). Khi gặp nó, `docker inspect` chuyển sang render trên map JSON thô, và ở chế độ đó khoá thiếu là lỗi. Bằng chứng trên `nats-1`:
  - `{{.State.Status}} {{if .State.Health}}…` → OK, ra `none`.
  - `{{.Id}} {{if .State.Health}}…` → lỗi.
  - Template đầy đủ, đổi `.Id` thành `.ID` → OK trên nats (ra `none`) và trên postgres (ra `healthy`).
- **Hệ quả từ 09/11 16:40 đến nay:**
  - 5 container mang `status="missing"`, `read_error=...` trong `logs/.container_health_state.json`.
  - Lần đầu gửi `[CRITICAL]` ×5. Từ đó mỗi lần chạy chỉ ghi INFO "vẫn lỗi đọc … (đã báo)", rồi **`EXIT=0`**.
  - Restart, OOM hay dừng của 5 container này **không bị phát hiện**, trong khi `EXIT=0` trông như khoẻ. Đây đúng là lỗi ghi trong memory "hiển thị không phải kiểm tra".

## Việc phải làm

**Trước khi sửa:** chạy `gitnexus_impact` (hoặc `node .gitnexus/run.cjs impact "inspect_container" --direction upstream --repo .`) cho `inspect_container` và cho hàm đánh giá trạng thái (hàm có nhánh `if stat.read_error:`, ~dòng 305). Báo callers và mức rủi ro. **Không dùng `npx`.**

### 1. Sửa template: `.Id` thành `.ID`

- Chỉ đổi đúng chỗ đó.
- Kiểm chứng:
  - (a) test đơn vị khẳng định template không chứa `{{.Id}}`;
  - (b) test `@pytest.mark.integration` gọi thật `inspect_container("ai_auto_trading_system-nats-test-1")`, là container test không có healthcheck. Khẳng định `read_error is None`, `status == "running"`, `health_status == "none"`, `container_id` dài 64 ký tự. Test tự skip nếu không có docker hoặc container đó không chạy;
  - (c) chạy lệnh `docker inspect -f '<template mới>'` bằng tay trên nats-test-1 và postgres-1 (container thật, chỉ đọc), dán output vào báo cáo.

### 2. Lỗi đọc kéo dài không được ra `EXIT=0`

- Hiện tại: lỗi đọc mới thì gửi `[CRITICAL]` và `EXIT=1`; lỗi đọc **kéo dài** thì chỉ ghi INFO và `EXIT=0`.
- Yêu cầu:
  - lỗi kéo dài vẫn **không** gửi Telegram lần nữa (giữ chống lặp);
  - nhưng mã thoát phải **khác 0**, để `schedule-watch` và heartbeat thấy job đang hỏng.
- Trước khi chọn mã:
  - đọc bảng mã thoát hiện có (đợt 217 và 218: 1, 2, 3, 4);
  - đọc cách `schedule-watch` và heartbeat xử lý từng mã, để mã mới **không** sinh tin THẤT BẠI mỗi 10 phút. Mục tiêu là 1 tin khi bắt đầu hỏng, 1 tin khi chạy lại, giống mã 4 ở đợt 218;
  - nếu không tìm được mã nào thoả cả hai điều trên mà không phải sửa `schedule-watch`, **dừng lại báo Lead**, không tự sửa `schedule-watch`.
- Kiểm chứng: test (bằng `evaluate`/`main` với trạng thái giả, **không** ghi vào `logs/` thật) cho thấy:
  - lỗi đọc lần đầu: có cảnh báo, mã khác 0;
  - lỗi đọc lần 2 giống hệt: không cảnh báo, mã khác 0;
  - hết lỗi: mã 0.

### 3. Chuyển từ trạng thái mù sang đọc được không được báo động giả

- Trạng thái thật hiện tại:
  - `status="missing"`, `read_error` có giá trị, `id` cũ;
  - Id của collector, engine và scheduler đã đổi vì rebuild lúc 23:18 ngày 12/11.
- Viết test với trạng thái trước giống hệt dạng này (chép cấu trúc, không đọc file thật trong test). Hai trường hợp:
  - Id đổi;
  - Id giữ nguyên, `RestartCount` tăng.
- Khẳng định:
  - Id đổi: chỉ ghi INFO "đã được tạo lại", không có CRITICAL;
  - Id giữ nguyên, `RestartCount` tăng: **có** CRITICAL restart. Restart trong lúc mù vẫn phải được báo khi đọc lại được.

## Phạm vi

- **Được sửa:** `scripts/container_health_check.py`, `tests/test_container_health_check.py`.
- **Không đụng:**
  - `scripts/sched.sh`, `scripts/run_if_docker_up.sh`, script `schedule-watch` hay heartbeat;
  - Task Windows, `docker-compose.yml`, mọi file trong `trading/`.
- Giữ nguyên style. Không refactor xung quanh. Thấy vấn đề khác thì báo lại, không tự sửa.

## Cấm

- Chạy `sched.sh`, chạy `container_health_check` thật (kể cả `--dry-run` nếu nó ghi file trạng thái thật), hay gửi Telegram.
- Ghi vào `logs/` hoặc sửa `logs/.container_health_state.json`.
- Restart hoặc rebuild container.
- Commit, push, dùng `npx`.

## Tiêu chí hoàn thành (bằng chứng phải gửi)

1. Output của `gitnexus_impact` trước khi sửa và `gitnexus_detect_changes` sau khi sửa.
2. `uv run pytest tests/test_container_health_check.py -v`: danh sách test pass, **liệt kê đủ tên các test mới**. Kèm cả `-m integration` cho test (b).
3. `uv run pytest -m "not integration" -q`: tổng số pass/fail.
4. `uv run ruff check scripts tests`: sạch.
5. Output `docker inspect` của bước 1(c).
6. Mã thoát đã chọn ở bước 2, kèm trích đoạn code `schedule-watch`/heartbeat chứng minh nó không sinh tin mỗi 10 phút.

## Triển khai

Script chạy trên host (`uv run` qua Task Windows), không nằm trong image. Sau khi Lead audit và commit, lần chạy kế tiếp sẽ dùng code mới, không cần rebuild. Lead sẽ tự xem dòng log của lần chạy đầu tiên sau commit.
