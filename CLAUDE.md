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

# Suite day du (gom integration) — can Postgres + NATS RIENG cho test
docker compose --profile test up -d nats-test
uv run pytest -q
# (test chay tren DB trading_test + NATS 4223 de khong bao gio dung he thong that)

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
- `trading/engine/`: Main loop, bar processing, strategy (octopus_pullback từ 04/09, trước đó SMA cross — xem `_default_strategy()`; ngưỡng thanh khoản từng bị tính sai theo N bar thay vì N ngày khiến engine gần như câm trên bar 5 phút — **gói K (06/09) đã sửa phần lớn: IJC/AAA hết câm, HII vẫn câm vì lý do khác (điều kiện tín hiệu), không phải lỗi đơn vị nữa**, xem `2026-09-06-master-audit-report-dot-6.md`), risk management
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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **AI_auto_trading_system** (19500 symbols, 29192 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/AI_auto_trading_system/context` | Codebase overview, check index freshness |
| `gitnexus://repo/AI_auto_trading_system/clusters` | All functional areas |
| `gitnexus://repo/AI_auto_trading_system/processes` | All execution flows |
| `gitnexus://repo/AI_auto_trading_system/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
