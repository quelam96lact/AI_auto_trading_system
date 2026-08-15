# NHIỆM VỤ: Dự án con 2 — Chiến lược breakout khung ngày + kiểm tra dữ liệu điều chỉnh

Repo: `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, nhánh `feature/data-layer`, base `4a61186`.

Đọc TRƯỚC khi viết code:
- `docs/superpowers/specs/2026-08-15-daily-breakout-research-design.md` (đặc tả gốc — đây là nguồn sự thật)
- `CLAUDE.md` (quy tắc dự án) và `AGENTS.md`
- `trading/backtest.py` (Dự án con 1 ĐÃ XONG ở `4a61186`: T+2,5 trong PaperBroker, mốc mua-và-giữ, lọc bar OHLC<=0 — DÙNG LẠI, KHÔNG viết lại)
- `trading/strategies/sma_cross.py` (mẫu interface: `compute_crossover(bar) -> "bull"|"bear"|None`, thuộc tính `.qty`, `.warmup_bars`)

Bắt buộc theo CLAUDE.md: chạy `gitnexus_impact` trước khi sửa bất kỳ symbol nào đang tồn tại,
và `gitnexus_detect_changes` sau khi sửa xong. Dùng `gitnexus_query`/`gitnexus_context` thay vì grep mù.

## Phạm vi phẫu thuật

ĐƯỢC tạo mới:
- `trading/strategies/daily_breakout.py`
- `tests/test_daily_breakout.py`
- `scripts/measure_daily_breakout.py` (runner đo diện rộng)
- `scripts/check_price_adjustment.py` (kiểm tra chia tách/cổ tức)

ĐƯỢC sửa (tối thiểu, chỉ đúng phần cần):
- `trading/backtest.py` — chỉ để đăng ký chiến lược mới vào `STRATEGIES`
- `tests/test_backtest_cli.py` — chỉ để thêm assert cho khoá mới

TUYỆT ĐỐI KHÔNG đụng: `trading/engine/`, `trading/real_orders.py`, `scripts/confirm_real_order.py`,
`config/config.yaml`, `trading/broker`, `trading/collector/`. Không bật `real_trading_enabled`.
Không refactor "tiện thể". Không xoá dead code có sẵn — nếu thấy, BÁO CÁO lại chứ đừng sửa.
KHÔNG commit, KHÔNG push — người giao việc sẽ audit rồi mới commit.

## Các bước và cách kiểm chứng

### Bước 0 — Kiểm giả định "giá đã điều chỉnh chia tách/cổ tức chưa"
Đặc tả nêu rõ đây là câu hỏi mở CHẶN việc tin vào kết quả: nếu `bars_daily` chưa điều chỉnh,
breakout sẽ sinh tín hiệu giả đúng vào ngày chia tách.

`scripts/check_price_adjustment.py`: quét `bars_daily`, tìm bước nhảy qua đêm bất thường
(ví dụ |close(t)/close(t-1) - 1| > 25% mà volume không bất thường tương ứng), loại bar rác
OHLC<=0 trước khi tính, và kiểm tra riêng các tỉ lệ đặc trưng của chia tách (~1/2, ~1/3, ~2/3, ~1/1,1).

→ Kiểm chứng bằng: chạy script, in ra SỐ LƯỢNG mã và ngày nghi ngờ + top 20 ví dụ cụ thể,
rồi viết một kết luận thẳng: "đã điều chỉnh" / "chưa điều chỉnh" / "không đủ bằng chứng".
Nếu là "chưa điều chỉnh" thì VẪN LÀM tiếp bước 1-3, nhưng phải ghi cảnh báo này lên đầu báo cáo cuối.

### Bước 1 — `DailyBreakoutStrategy` (TDD, viết test đỏ trước)
- Vào lệnh (`"bull"`): close vượt **đỉnh cao nhất N=20 phiên gần nhất, KHÔNG tính bar hiện tại**.
- Ra lệnh (`"bear"`): close thủng **đáy thấp nhất M=10 phiên gần nhất, KHÔNG tính bar hiện tại**.
- N=20, M=10 là tham số khởi điểm chốt TRƯỚC khi đo. **KHÔNG được tinh chỉnh** trong lần đo này.
- State theo từng symbol (giống `SmaCrossStrategy`), `warmup_bars = max(N, M) + 1`.
- Không đủ lịch sử → trả `None`, không đoán.

→ Kiểm chứng bằng: `uv run pytest tests/test_daily_breakout.py -v` xanh, với tối thiểu các test:
đủ/thiếu warmup; close = đúng đỉnh (không vượt) → KHÔNG vào lệnh; vượt đỉnh → "bull";
bar hiện tại không được tính vào cửa sổ; thủng đáy → "bear"; hai symbol không rò state sang nhau.

### Bước 2 — Đăng ký vào CLI backtest
Thêm `"daily_breakout"` vào `STRATEGIES` trong `trading/backtest.py`. Không đổi gì khác trong file đó.

→ Kiểm chứng bằng: `uv run pytest tests/test_backtest_cli.py -v` xanh và chạy thật được:
`uv run python -m trading.backtest --strategy daily_breakout --symbols VCB,HPG,TCB --from 2016-01-04 --to 2026-08-13 --tf 1d --capital 1000000000`

### Bước 3 — Đo diện rộng 1.551 mã (`scripts/measure_daily_breakout.py`)
QUYẾT ĐỊNH THIẾT KẾ đã chốt, làm đúng như vậy, đừng tự đổi:
- **Chạy ĐỘC LẬP TỪNG MÃ**, mỗi mã một `run_backtest()` riêng với CÙNG một số vốn
  (mặc định 1.000.000.000), rồi cộng dồn. KHÔNG chạy một danh mục chung 1.551 mã:
  vốn chung sẽ bị cạn và lặng lẽ chặn tín hiệu của các mã phía sau — đúng cái bẫy sizing
  đã từng làm hỏng phép đo `sma_cross` (xem `GO_LIVE_AUDIT.md`, mục "Luồng paper không thể mua").
- Đọc từng mã một từ `bars_daily` (2.969.328 dòng — KHÔNG nạp hết vào RAM một lần).
- Kỳ đo: 2016-01-04 → 2026-08-13, khung `1d`.

Báo cáo phải in ra, bằng SỐ, đúng ba câu hỏi trong đặc tả:
1. Tổng PnL chiến lược so với tổng PnL mua-và-giữ (cùng mã, cùng kỳ, cùng vốn, cùng phí) — và chênh lệch.
   Nếu thua mua-và-giữ thì in thẳng "THUA mua-và-giữ" chứ không để người đọc tự suy.
2. Tổng số lệnh (và số mã thực sự sinh lệnh) — đủ để kết luận hay lại rơi vào bẫy cỡ mẫu nhỏ.
3. Tổng số dòng bị loại vì bẩn (OHLC<=0), tách theo mã, và nêu rõ mã nào bẩn tới mức
   kết quả của nó không đáng tin.
Kèm phân phối theo mã (số mã thắng/thua mua-và-giữ, trung vị chênh lệch) — đừng chỉ có một con số tổng.

→ Kiểm chứng bằng: chạy thật script tới khi xong, dán output thật vào báo cáo.
Cần Postgres chạy (`docker compose up -d postgres`). LƯU Ý MÔI TRƯỜNG: trên Windows máy này,
DSN dùng `localhost` bị IPv6 làm mỗi lần kết nối mất ~130 giây — dùng `127.0.0.1`.

### Bước 4 — Không làm hỏng thứ đang chạy
→ Kiểm chứng bằng: `uv run pytest -m "not integration" -v` toàn bộ xanh
và `uv run ruff check trading tests scripts` sạch. Dán số liệu thật (X passed).

## NGOÀI PHẠM VI — cố ý không làm (đặc tả nói rõ)
- KHÔNG quét/tinh chỉnh tham số trong lần đo đầu.
- KHÔNG chọn mã dựa trên kết quả.
- KHÔNG chọn rổ giao dịch thật — đó là quyết định riêng, làm sau, dựa trên số liệu.

## Báo cáo cuối phải có
1. Kết luận bước 0 (dữ liệu đã điều chỉnh hay chưa) + bằng chứng.
2. Output thật của bước 3, trả lời 3 câu hỏi trên bằng số.
3. Output thật của `pytest` và `ruff`.
4. Danh sách file đã tạo/sửa + kết quả `gitnexus_detect_changes`.
5. Bất cứ thứ gì phát hiện ngoài phạm vi (dead code, bug) — BÁO CÁO, không tự sửa.

Nếu câu trả lời là "breakout KHÔNG vượt mua-và-giữ" thì đó là kết quả HỢP LỆ và có giá trị.
Đừng chỉnh tham số cho đẹp số. Báo cáo trung thực đúng cái đo được.
