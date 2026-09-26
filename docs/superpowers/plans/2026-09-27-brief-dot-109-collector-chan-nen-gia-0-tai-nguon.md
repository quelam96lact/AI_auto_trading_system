# Brief đợt 109 — Collector chặn nến giá 0 ngay tại nguồn ghi

Ngày giao: Chủ nhật 27/09/2026. Base: main `a5eda8c`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không build hay restart container, không ghi DB thật**.

Ngày chủ nhật không có phiên, nên được phép sửa collector. Claude triển khai **sau 15:40 thứ Hai 28/09**, gộp chung lần rebuild với đợt 107–108.

## 0. Vì sao

Đợt 108 đã chặn nến giá 0 ở **engine**. Nhưng collector vẫn **ghi** chúng vào `bars` và **phát** chúng lên NATS:
- 261 dòng đã nằm trong DB từ 13/08 đến 16/09;
- không có commit nào tắt nguồn sinh ra chúng.

Hệ quả: `bars` tiếp tục nhiễm bẩn cho mọi phép đo, Grafana, bộ kiểm dữ liệu và mọi chỗ khác đọc `bars` mà không lọc.

**Đường ghi thật (Claude đã kiểm 27/09).** Mục Task B của báo cáo đợt 108 truy **sai** đường ghi:
- `trading/collector/aggregator.py::BarAggregator` **không có caller nào** trong `trading/`. Đây là code chết.
- Đường ghi thật của luồng realtime:
  1. `collector/main.py::make_stream_message_handler`, hàm `on_stream_message` (dòng ~153): `bar = parse_interval_message(msg)`;
  2. `wd.beat()`;
  3. `persist_snapshot(storage, bar)`: ghi DB **mỗi snapshot**;
  4. `latch.offer(bar)`;
  5. `persist_bars(...)`: publish NATS và ghi DB.
- Đường backfill: `collector/backfill.py::run_backfill` dòng 354–359, `intraday = [...]` rồi `storage.write_bars(intraday)`.

## 1. Phạm vi

| Chỗ | Làm gì |
|---|---|
| `on_stream_message` | Sau khi parse ra `bar`, và **sau** `wd.beat()`: nhận được message nghĩa là luồng vẫn sống, nên giữ nguyên nhịp tim. Nếu `is_dirty_bar(bar)` thì **không** `persist_snapshot`, **không** `latch.offer`, rồi `return`. Phát **WARN một lần cho mỗi (mã, ngày)**, nêu mã, `ts`, OHLC. Tập đã báo giữ trong closure của `make_stream_message_handler`, xoá khi sang ngày mới, **không** phình mãi. |
| `run_backfill`, nhánh intraday | Lọc `is_dirty_bar` khỏi `intraday` **trước** `write_bars`. Nếu có bar bị bỏ: một WARN cho mỗi mã trong lượt chạy, nêu số bar bỏ và `ts` đầu/cuối. `counts[sym]` đếm số bar **đã ghi**. |

Luật **chỉ** là `trading.data_quality.is_dirty_bar`. Không chép điều kiện `<= 0` sang chỗ khác. Không thêm điều kiện vào SQL.

**Không được đụng:**
- `write_daily` và nhánh `daily_only`: `bars_daily` có dạng bẩn khác (open = 0 nhưng close thật), NAV có thể phụ thuộc vào close. **Chỉ báo lại.**
- `aggregator.py`: code chết, **chỉ báo**, không xoá.
- `latch.py`, `parser.py`, storage, engine, config, `docker-compose.yml`, Task Scheduler.

Thấy lỗi ngoài phạm vi thì báo, không sửa.

## 2. Các bước

**GitNexus TRƯỚC khi sửa.** Dùng CLI nếu MCP không kết nối được. Chạy `npx gitnexus impact <symbol> --repo AI_auto_trading_system` cho `make_stream_message_handler` và `run_backfill`, rồi dán kết quả. Nếu HIGH hoặc CRITICAL thì **dừng lại và báo**. Cuối đợt chạy `npx gitnexus detect-changes --scope all --repo AI_auto_trading_system` và dán kết quả.

1. **Test luồng realtime (TDD, viết test đỏ trước).** Theo khuôn test sẵn có của `make_stream_message_handler` trong `tests/test_collector_main.py`. Cho handler một message có OHLC = 0, kiểm:
   - `storage.write_bars` **không** được gọi;
   - `latch` không nhận bar;
   - NATS không publish;
   - `wd.beat()` **có** được gọi.

   Thêm các trường hợp:
   - hai message bẩn cùng mã cùng ngày → **một** WARN;
   - sang ngày khác → WARN lại;
   - message sạch ngay sau đó → đi đúng đường cũ.

   → **Kiểm chứng bằng:** pytest.

2. **Test backfill (TDD).** Dùng client giả trả 3 bar intraday, trong đó 1 bar bẩn, kiểm:
   - `write_bars` nhận đúng 2 bar;
   - `counts[sym] == 2`;
   - có một WARN nêu số 1.

   Không có bar bẩn → không WARN.
   → **Kiểm chứng bằng:** pytest.

3. **Phá thử.** Sao lưu **ra ngoài repo** rồi khôi phục từ bản sao lưu. **Cấm `git checkout`, `git restore`, `git stash`.** Mỗi phép phá phải làm ít nhất một test đỏ:
   - (i) đặt kiểm bẩn **sau** `persist_snapshot`;
   - (ii) đặt kiểm bẩn **trước** `wd.beat()`;
   - (iii) bỏ lọc ở backfill.

   Phép phá phải thật sự vi phạm luật.
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.

4. **Chỉ đọc: kiểm `stream-health` và cổng go-live có đếm theo khung ATO/ATC không.** Nếu có, việc bỏ nến 0 ở 09:00–09:10 và 14:30–14:40 có làm lệch con số độ phủ không? Trích dẫn dòng code và trả lời có hoặc không. `calendar_vn.py:101` (`CONTINUOUS_SESSIONS`) và `is_continuous_matching` (dòng 104) đã loại ATO/ATC; hãy xác nhận các thước đo độ phủ dùng đúng định nghĩa đó.
   → **Kiểm chứng bằng:** trích dẫn dòng code.

5. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q` (mốc 1126)
   - `uv run pytest -m integration -q` (mốc 137)
   - `uv run ruff check trading tests`

## 3. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận ngắn.
2. Output test đỏ rồi xanh.
3. Phá thử.
4. Kết quả bước 4.
5. `gitnexus impact` (chạy trước khi sửa) và `detect-changes`.
6. Những điều thấy ngoài phạm vi, **bắt buộc** gồm `aggregator.py` và `bars_daily`.

Kết thúc bằng câu: "Tôi không commit, không push, không build hay restart container, không ghi DB thật."
