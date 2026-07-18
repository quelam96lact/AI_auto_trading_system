# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is not yet started — it currently contains only git metadata (no source code, README, configuration, or dependency manifests). There is nothing to build, lint, or test yet, and no architecture to document.

Per project memory (`ssi-fastconnect-api-facts`), this project is expected to become an AI auto-trading system integrating with the SSI FastConnect API. Verify current API facts against that memory file before relying on it, since it flagged that some prior assumptions (a "Task 31" and an existing `connector.py`) were fabricated and not actually present in the codebase.

## Next steps for future Claude instances

When source code is added to this repository, update this file with:
1. Build, lint, and test commands (including how to run a single test).
2. High-level architecture — module boundaries, data flow, and how major components interact.

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

- Mọi kế hoạch giao cho agent thực thi phải yêu cầu agent **kiểm tra GitNexus trước khi sửa code** (xem phần "GitNexus — Code Intelligence" bên dưới: `gitnexus_query`/`gitnexus_context` để hiểu code, `gitnexus_impact` trước khi sửa symbol, `gitnexus_detect_changes` sau khi sửa).
- Agent thực thi chỉ viết code và tự kiểm chứng theo tiêu chí đã định (nguyên tắc 4) — **không tự commit, không tự push**.
- Claude là người audit kết quả cuối cùng (đối chiếu với kế hoạch, chạy `gitnexus_detect_changes`, xem xét blast radius), rồi mới **commit và push lên GitHub**.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **AI_auto_trading_system** (135 symbols, 170 relationships, 0 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
