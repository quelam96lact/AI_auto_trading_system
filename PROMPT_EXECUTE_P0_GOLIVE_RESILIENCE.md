# Prompt thực thi: P0 Go-Live Resilience (4 task)

**Dùng prompt này để giao việc cho 1 agent coding khác thực thi.**

**Đọc trước khi bắt đầu:**
1. `docs/superpowers/plans/2026-08-09-p0-golive-resilience.md` — implementation
   plan đầy đủ, **có sẵn code cụ thể và test cụ thể cho cả 4 Task**. Đây là
   nguồn sự thật duy nhất về việc phải viết gì.
2. `CLAUDE.md` mục "GitNexus — Code Intelligence" — quy tắc bắt buộc trước khi
   sửa symbol.

**Thực thi đúng theo plan, task theo task, bước theo bước. Không đảo thứ tự
task** — Task 3 sửa cùng file với Task 2 và phụ thuộc vào việc Task 2 đã tách
xong `housekeeping_loop`.

---

## Bối cảnh (vì sao có việc này)

Audit go-live ngày 2026-08-09 phát hiện 4 lỗi resilience khiến hệ thống không
thể chạy tự động 24/7 trên VPS Ubuntu. Đây **không phải** tính năng mới, không
đổi hành vi giao dịch — chỉ làm cho hệ thống không chết/không mất dữ liệu im
lặng:

1. `trading/engine/main.py:88-129` — vòng lặp message không có try/except. Một
   message hỏng → engine chết → Docker restart → JetStream redeliver đúng
   message đó → chết lại. Crash loop vĩnh viễn, container vẫn trông như đang chạy.
2. `trading/collector/main.py:71-107` — `housekeeping()` không bọc `wd.check()`
   và `storage.beat()`. Postgres restart 5 giây là collector chết.
3. `trading/collector/main.py:63` — `asyncio.create_task(persist([bar]))`
   fire-and-forget: DB lỗi thì asyncio nuốt exception, **bar mất mà không có
   alert nào**.
4. Không có dead-man's switch. `heartbeat` được ghi vào DB nhưng không có alert
   rule nào (`grep -c "alert" grafana/.../trading.json` = 0). Service chết lúc
   10h sáng thì không ai biết.

---

## ⚠️ Quy tắc bắt buộc

### KHÔNG tự commit, không tự push

Làm hết cả 4 Task, giữ nguyên working tree có diff, rồi báo cáo đầy đủ để Claude
(planner) audit và tự tay commit. Plan doc đã viết đúng như vậy (Step cuối của
mỗi task là "báo cáo, KHÔNG commit") — không có bước `git commit` nào để làm.

### GitNexus — bắt buộc, không được bỏ

- **Trước khi sửa** `trading/engine/main.py::run` (Task 1) và
  `trading/collector/main.py::run` (Task 2 và Task 3 — chạy lại ở mỗi task vì
  file đã đổi): chạy `gitnexus_impact({target: "run", direction: "upstream"})`,
  dán nguyên văn kết quả vào báo cáo.
- Nếu kết quả là **HIGH hoặc CRITICAL** → **DỪNG LẠI, báo cáo, hỏi trước khi
  sửa.** Không được tự quyết định đi tiếp.
- Task 4 chỉ tạo file mới + sửa docs → không cần `gitnexus_impact`.
- **Sau khi sửa xong mỗi task**: chạy `gitnexus_detect_changes()`, dán kết quả.

### Giới hạn phạm vi (phẫu thuật)

Chỉ được đụng đúng 7 file này:

| File | Task |
|------|------|
| `trading/engine/main.py` | 1 |
| `tests/test_engine_main.py` | 1 |
| `trading/collector/main.py` | 2, 3 |
| `tests/test_collector_main.py` (tạo mới) | 2, 3 |
| `scripts/heartbeat_check.py` (tạo mới) | 4 |
| `tests/test_heartbeat_check.py` (tạo mới) | 4 |
| `DEPLOYMENT.md` | 4 |

- **KHÔNG sửa** `trading/engine/logic.py`, `trading/risk.py`,
  `trading/real_orders.py`, `trading/storage/db.py`, `trading/collector/feed.py`,
  `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `config/config.yaml`.
- **KHÔNG thêm dependency mới.** `msg.term()` đã có sẵn trong nats-py
  (`nats/aio/msg.py:148`), `psycopg` đã là dependency.
- **KHÔNG tạo** `scripts/__init__.py` — plan doc Task 4 Step 2 giải thích tại sao.
- **KHÔNG refactor** code xung quanh, không dọn dead code có sẵn, không đổi tên
  gì ngoài những gì plan ghi rõ.
- Chỉ được xóa import/biến thừa **do chính thay đổi của bạn làm phát sinh**.
- Giữ nguyên các comment tiếng Việt hiện có, đặc biệt khối comment về index
  streaming trong `on_stream_message` (plan Task 3 đã ghi rõ phải giữ).

### Phát hiện ngoài phạm vi → BÁO CÁO, KHÔNG SỬA

Plan doc có mục "Ngoài phạm vi kế hoạch này (cố ý không làm)" liệt kê các vấn đề
P1/P2 đã biết (bug `daily_pnl` tích lũy ở `trading/engine/logic.py:44`,
Dockerfile không dùng `uv.lock`, password Grafana `admin`, JetStream không giới
hạn retention…). **Đây là các quyết định đã cân nhắc, không phải sót.** Nếu bạn
thấy chúng — hoặc thấy vấn đề mới nào khác — thì ghi vào mục "Phát hiện ngoài
phạm vi" của báo cáo, tuyệt đối không tự sửa.

---

## Chuẩn bị môi trường

Task 1 dùng integration test, cần Postgres + NATS thật:

```bash
docker compose up -d postgres nats
docker compose ps    # cả 2 phải healthy/running trước khi chạy test Task 1
```

Task 2, 3, 4 là unit test thuần, không cần Docker.

**Baseline trước khi bắt đầu — chạy và ghi lại:**

```bash
uv run pytest -m "not integration" -q     # phải ra: 168 passed
uv run ruff check trading tests           # phải ra: All checks passed!
```

Nếu baseline **không** ra đúng 168 passed → DỪNG, báo cáo ngay, đừng bắt đầu sửa.

---

## Tiêu chí hoàn thành (kiểm chứng được, không mơ hồ)

Từng task có tiêu chí riêng trong plan doc. Tiêu chí nghiệm thu cuối cùng:

1. `uv run pytest -m "not integration" -q` → **177 passed** (168 baseline + 3
   Task 2 + 2 Task 3 + 4 Task 4). Số phải khớp chính xác.
2. `uv run pytest tests/test_engine_main.py -m integration -v` → **7 passed**
   (6 test cũ + 1 test mới của Task 1). Cần Docker đang chạy.
3. `uv run ruff check trading tests scripts` → `All checks passed!`
4. Với mỗi task: đã chạy TDD đúng thứ tự — test FAIL **trước** khi sửa code
   (phải dán được output FAIL, không được viết code trước rồi mới viết test).
5. `git status --short` chỉ hiện đúng 7 file trong bảng phạm vi ở trên, cộng với
   các file/thư mục vốn đã untracked từ trước (`.1devtool/`, `.gitnexus_rpc.py`,
   `scripts/.spike_*.py`, `.claude/worktrees/` — không phải do task này tạo).
6. Không có commit/push nào do bạn tạo ra.

---

## Báo cáo lại (bắt buộc đủ, không tóm tắt)

1. **Baseline**: output `uv run pytest -m "not integration" -q` và
   `uv run ruff check trading tests` chạy TRƯỚC khi sửa gì.
2. **Với từng Task 1→4**:
   - Output `gitnexus_impact` (Task 1, 2, 3) — dán nguyên văn, nêu rõ mức risk.
   - Output bước "chạy test để xác nhận FAIL" — dán nguyên văn dòng lỗi.
   - Diff đầy đủ của các file đã sửa/tạo trong task đó.
   - Output bước "chạy test để xác nhận PASS".
   - Output `gitnexus_detect_changes()`.
3. **Output cuối cùng, chạy lại một lượt sau khi xong cả 4 task:**
   - `uv run pytest -m "not integration" -q`
   - `uv run pytest tests/test_engine_main.py -m integration -v`
   - `uv run ruff check trading tests scripts`
   - `git status --short`
4. **Task 4 kiểm chứng thủ công**: output 2 lệnh chạy thật
   `scripts/heartbeat_check.py` (DSN đúng và DSN sai) kèm exit code, **và ghi rõ
   bạn chạy lúc mấy giờ (giờ VN)** — vì script tự thoát sớm (exit 0) ngoài giờ
   giao dịch 9:00-11:30 / 13:00-14:45 T2-T6, nên giờ chạy quyết định cách đọc
   kết quả.
5. **Phát hiện ngoài phạm vi**: liệt kê những gì bạn thấy nhưng cố ý không sửa.
6. **Xác nhận thẳng**: những gì CHƯA được kiểm chứng thật. Cụ thể, tối thiểu
   phải nói rõ: dead-man's switch của Task 4 **chưa từng được thử bằng cách
   thật sự giết một service** (`docker compose stop engine` rồi đợi >5 phút
   trong giờ giao dịch) — chỉ có unit test hàm thuần + chạy tay script. Đừng
   viết "đã hoạt động tốt" cho phần chưa thử.

Nếu có bước nào bạn không làm được, nói thẳng bước đó và lý do — làm đủ hết
những bước còn lại. **Đừng báo "đã xong" khi chưa có đủ bằng chứng ở trên.**

**Không tự commit, không tự push.** Chờ Claude audit xong mới commit.
