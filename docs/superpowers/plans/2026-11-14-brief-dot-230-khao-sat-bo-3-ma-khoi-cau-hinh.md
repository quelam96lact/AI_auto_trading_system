# Brief đợt 230: khảo sát việc bỏ HPG, IJC, AAA khỏi `config.yaml` (CHỈ ĐỌC)

Ngày 14/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**. Chỉ đọc code, test, log và DB (SELECT). Không sửa gì. Đợt 226 vẫn ưu tiên trong cửa sổ 01:45–03:15.

## Bối cảnh

Chủ dự án quyết định tối 13/11: **không giữ** HPG, IJC, AAA trong cấu hình. Các quyết định khác cho engine mới: phạm vi khoảng 293 mã đang hoạt động; paper khớp ở giá mở cửa T+1, ghi nhận tối T+1; sổ paper mới 100 triệu trong bảng riêng, giữ nguyên sổ cũ.

Báo cáo đợt 228 mục B.4 đã liệt kê ai đọc `symbols`. Đợt này đi tiếp một bước: xác định **chính xác phải sửa gì** để `symbols: []` là cấu hình hợp lệ và hệ thống chạy sạch, không báo động giả, không mất dữ liệu đang cần.

Trạng thái đích Lead dự kiến (thấy sai thì nêu):

- `symbols: []`. Collector không stream cổ phiếu nào; vẫn làm các việc khác (chỉ số, đồng bộ tài khoản/NAV, backfill).
- Ba mã cũ được nạp nến 5 phút mỗi tối như mọi mã khác trong universe (`startup_catchup` đã làm vậy với mã ngoài `cfg.symbols`).
- Engine chạy với cờ `ENGINE_STRATEGY_DISABLED` (đợt 229) cho tới khi engine nến ngày thay thế.

## Câu hỏi phải trả lời

Với **từng** nơi đọc `cfg.symbols` hoặc `cfg["symbols"]` (lấy danh sách B.4 làm điểm xuất phát, grep lại cho đủ cả `trading/`, `scripts/`, `tests/`, `grafana/`):

1. Với danh sách rỗng, code hiện tại làm gì: chạy đúng, lỗi, treo, hay báo động giả? Ghi `file:dòng` và lý do. Đánh dấu **[đọc]** hay **[suy luận]**.
2. Sửa nhỏ nhất để chạy đúng là gì (mô tả, không viết code).
3. Test nào đang ghim hành vi với 3 mã và sẽ phải đổi.

Các điểm bắt buộc xét:

- **Collector:** vòng stream khi không có mã cổ phiếu (`feed.py`, `main.py`); nó còn stream chỉ số không; heartbeat của collector còn được ghi không; backfill lúc khởi động; `account_sync.py:59` (sức mua theo mã) khi rỗng; watchdog trong `config.yaml` có coi "không có tick" là sự cố không.
- **Engine (với cờ đợt 229):** vòng chờ dữ liệu `main.py:243-271` và warm-up `:280-312` khi rỗng; consumer NATS `bars.>` khi không còn ai publish; `engine_consumer_check.py` khi không có tin mới.
- **Job giám sát:** `heartbeat_check.py` (2A nến cũ, `IN ()`), `stream_health_check.py` (độ phủ nến của mã nào), `check_silent_engine.py`, `daily_data_check.py` (mã bắt buộc có giá), `measure_session_stream_metrics.py` và mọi job trong `SCHEDULE_EXIT_POLICIES` có đọc `symbols`; `morning-summary`; `deploy-drift`.
- **Nạp dữ liệu:** `startup_catchup.py`, `backfill_universe.py`: ba mã cũ có tự vào diện nạp 5 phút hằng tối không; có khoảng trống dữ liệu nào ở ngày chuyển không (nến 5 phút của 3 mã trong ngày chuyển do ai ghi).
- **Grafana:** bảng nào lọc cứng theo 3 mã.
- **Bảng orderbook/VN30F** và các phần không liên quan: xác nhận không đọc `symbols`.

## Cấm

- Không sửa file nào ngoài báo cáo. Không commit, không push, không `npx`.
- Không dừng/restart container, không chạy `sched.sh`, không chạy script kiểm tra thật (kể cả dry-run). Không sửa `config.yaml` để thử.
- Không ghi DB. Không gọi API SSI/DNSE/BingX. Không gửi Telegram. Không đọc file token SDK hay `.env`.
- Không mở `data/research227/`, không đọc `scripts/research227_*`.

## Tiêu chí hoàn thành

Báo cáo `docs/audit/2026-11-14-khao-sat-bo-3-ma-khoi-cau-hinh.md`:

1. Một bảng: nơi đọc | `file:dòng` | hành vi khi rỗng | sửa nhỏ nhất | test bị ảnh hưởng.
2. Thứ tự sửa và deploy an toàn (cái gì phải sửa trước khi đổi `config.yaml`; image nào phải build lại).
3. Danh sách "đã grep, không liên quan" và "chưa kiểm".
4. Rủi ro còn lại và câu hỏi cho Lead.

Nhắn Lead khi xong.
