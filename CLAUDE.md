# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Active development:** AI auto-trading system for Vietnamese stocks (HOSE/HNX) using SSI FastConnect API.

**Completed:**
- Sub-project 4 (Monitoring): Telegram alerts + Grafana dashboards
- Sub-project 1 Task 10 (Collector): SSI real-time stream consumer with backfill, 5m bar aggregation, NATS publisher
- Sub-project 1 Phase 2 Tasks 1-2 (Data layer): SSI message fixtures + TDD parser (B/MI messages)

**In progress:**
- Sub-project 1 Phase 2 Task 3 (E2E verification): Awaiting next trading session for full integration test

## Build, lint, test commands

```bash
# Install dependencies
uv sync

# Run all unit tests (excluding integration tests)
uv run pytest -m "not integration" -v

# Run single test file
uv run pytest tests/test_parser.py -v

# Run single test
uv run pytest tests/test_parser.py::test_parse_b_string_envelope -v

# Lint with ruff
uv run ruff check trading tests

# Start collector service
docker compose up -d --build collector

# Start engine (paper trading)
docker compose up -d --build engine

# View logs
docker compose logs -f collector
docker compose logs -f engine
```

## High-level architecture

**Data flow: SSI stream → Collector → DB/NATS → Engine → PaperBroker**

- `trading/collector/`: SSI feed (real-time stream), parser (B/MI messages), backfill (REST API), aggregator (1m→5m bars)
- `trading/engine/`: Main loop, bar processing, strategy (SMA cross), risk management
- `trading/broker`: PaperBroker (simulates order fills with VN fees + slippage)
- `trading/storage/`: PostgreSQL + TimescaleDB (bars, orders, positions, PnL)
- `trading/bus/`: NATS JetStream publisher (bars → engine subscription)
- `trading/alerts/`: Structured logging + Telegram daemon threads (WARN/CRITICAL)
- `grafana/`: Dashboard (price, PnL, positions, heartbeat) with PostgreSQL datasource

**Key services:**
- postgres:5432 — TimescaleDB (hypertable for bars/orders/positions)
- nats:4222 — JetStream stream=BARS, subject=bars.ssi.{symbol}
- collector — Backfills + streams real-time ticks → bars → DB + NATS
- engine — Subscribes bars, runs strategy, executes orders → positions/PnL
- grafana:3000 — Live dashboards (admin/admin)

## Nguyên tắc lập kế hoạch khi giao việc coding cho agent AI khác

Khi Claude đóng vai trò lên kế hoạch (planner) và giao việc viết code cho agent AI khác thực thi, áp dụng các nguyên tắc sau:

### 1. Suy nghĩ trước khi lên kế hoạch — không giả định, không giấu sự mơ hồ

- Nêu rõ mọi giả định trong kế hoạch (ngôn ngữ, thư viện, cấu trúc dữ liệu đầu vào/đầu ra). Nếu không chắc, hỏi người dùng trước khi giao việc.
- Nếu yêu cầu có nhiều cách hiểu, liệt kê các cách hiểu đó trong kế hoạch thay vì tự chọn một cách và im lặng.
- Nếu có cách tiếp cận đơn giản hơn cách người dùng đề xuất, nói rõ trong kế hoạch và phản biện nếu cần.
- Nếu có phần chưa rõ ràng, kế hoạch phải dừng lại ở đó và ghi rõ câu hỏi cần làm rõ — không chuyển tiếp sự mơ hồ cho agent thực thi.

### 2. Đơn giản là trên hết — kế hoạch chỉ chứa những gì thực sự cần

- Mỗi bước trong kế hoạch phải trực tiếp phục vụ yêu cầu, không thêm tính năng, cấu hình, hay khả năng mở rộng chưa được yêu cầu.
- Không giao cho agent thực thi việc xử lý lỗi cho các tình huống không thể xảy ra.
- Nếu một bước có thể rút gọn, rút gọn trước khi giao.
- Tự hỏi: "Một kỹ sư senior có thấy kế hoạch này rườm rà không?" — nếu có, đơn giản hóa lại.

### 3. Phạm vi phẫu thuật — giới hạn rõ ràng những gì agent được đụng vào

- Với mỗi task giao cho agent, chỉ rõ: file/module nào được sửa, file/module nào **không** được đụng vào.
- Yêu cầu agent giữ nguyên style code hiện có, không "tiện thể" refactor code xung quanh, không dọn dẹp code không liên quan.
- Nếu agent phát hiện dead code hoặc vấn đề không thuộc phạm vi task, yêu cầu agent báo cáo lại thay vì tự ý xóa/sửa.
- Agent chỉ được xóa import/biến/hàm mà chính thay đổi của agent đó làm phát sinh thừa — không xóa dead code có từ trước trừ khi được giao rõ.
- Quy tắc kiểm tra: mọi dòng code agent thay đổi phải truy ngược được về đúng task được giao.

### 4. Thực thi theo mục tiêu — tiêu chí thành công phải kiểm chứng được

- Mỗi task giao cho agent phải có tiêu chí "hoàn thành" rõ ràng, không mơ hồ kiểu "làm cho nó chạy được".
  - "Thêm validation" → "Viết test cho input không hợp lệ, rồi làm cho test pass"
  - "Sửa bug" → "Viết test tái hiện bug, rồi làm cho test pass"
  - "Refactor X" → "Đảm bảo test trước và sau refactor đều pass, không đổi hành vi bên ngoài"
- Với task nhiều bước, kế hoạch phải trình bày dạng:
  ```
  1. [Bước] → kiểm chứng bằng: [cách kiểm tra]
  2. [Bước] → kiểm chứng bằng: [cách kiểm tra]
  3. [Bước] → kiểm chứng bằng: [cách kiểm tra]
  ```
- Tiêu chí kiểm chứng càng rõ, agent thực thi càng có thể tự lặp (loop) độc lập mà không cần hỏi lại liên tục. Tiêu chí mơ hồ buộc phải hỏi lại nhiều lần — coi đó là dấu hiệu kế hoạch chưa đạt.
- Sau khi agent báo cáo hoàn thành, Claude (planner) phải tự chạy/yêu cầu bằng chứng kiểm chứng (test pass, output cụ thể) trước khi chấp nhận kết quả — không tin tuyên bố "đã xong" khi chưa có bằng chứng.

**Đánh đổi:** Các nguyên tắc trên ưu tiên sự thận trọng và rõ ràng hơn tốc độ. Với task thực sự nhỏ và không mơ hồ, có thể rút gọn quy trình lập kế hoạch, nhưng vẫn phải giữ nguyên tắc 3 (phạm vi phẫu thuật) và nguyên tắc 4 (tiêu chí kiểm chứng).

### Phân vai giữa agent thực thi và Claude

- Mọi kế hoạch giao cho agent thực thi phải yêu cầu agent **kiểm tra GitNexus trước khi sửa code** (see AGENTS.md for GitNexus resources: `gitnexus_query`/`gitnexus_context` to understand code, `gitnexus_impact` before editing symbol, `gitnexus_detect_changes` after editing).
- Agent thực thi chỉ viết code và tự kiểm chứng theo tiêu chí đã định (nguyên tắc 4) — **không tự commit, không tự push**.
- Claude là người audit kết quả cuối cùng (đối chiếu với kế hoạch, chạy `gitnexus_detect_changes`, xem xét blast radius), rồi mới **commit và push lên GitHub**.
