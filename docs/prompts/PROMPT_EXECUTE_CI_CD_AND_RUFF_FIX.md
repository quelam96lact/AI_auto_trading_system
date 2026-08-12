# Prompt thực thi: CI/CD + fix ruff thiếu

**Dùng prompt này để giao việc cho 1 agent coding khác (Hermes) thực thi.**

**Đọc trước khi bắt đầu, theo đúng thứ tự:**
1. `docs/superpowers/specs/2026-08-08-ci-cd-and-ruff-fix-design.md` — spec đầy đủ, đã user duyệt.
2. `docs/superpowers/plans/2026-08-08-ci-cd-and-ruff-fix.md` — implementation plan đầy đủ, có sẵn code cụ thể cho 3 Task.

**Thực thi đúng theo plan ở trên, task theo task, bước theo bước.**

---

## ⚠️ Khác biệt so với plan doc — đọc kỹ

Plan doc có bước `git commit` ở cuối Task 1 và Task 2. **BỎ QUA các bước `git commit` đó** — quy ước dự án cho lần giao việc này:

**KHÔNG tự commit, không tự push.** Làm hết cả 3 Task, giữ nguyên working tree có diff, rồi báo cáo lại đầy đủ để Claude (planner) audit và tự tay commit.

## ⚠️ Giới hạn phạm vi

- Chỉ sửa `pyproject.toml` (đúng 1 dòng, dòng `dev = [...]`) và tạo mới `.github/workflows/ci.yml`.
- **KHÔNG sửa** `DEPLOYMENT.md`, `docker-compose.yml`, bất kỳ file nào trong `trading/`.
- **KHÔNG tự sửa lỗi lint** mà `ruff check` phát hiện trong code cũ (nếu có) — chỉ copy nguyên văn output vào báo cáo. Đây là phát hiện cần báo cáo, không phải việc được giao.
- **KHÔNG thêm** `[tool.ruff]` config hay `ruff format --check` — chỉ dùng default rule set, chỉ `ruff check`.
- Không cần chạy GitNexus impact check cho `.github/workflows/ci.yml` (không phải code Python, không nằm trong knowledge graph). Với dòng sửa `pyproject.toml`, không cần impact check riêng (chỉ là khai báo dependency, không phải symbol code) — chỉ cần chạy lại `uv run pytest -m "not integration" -v` để xác nhận không có gì hỏng (đã có trong plan, Task 1 Step 5 và Task 3 Step 1).

---

## Tiêu chí hoàn thành (kiểm chứng được)

1. `uv sync --extra dev` chạy sạch, không lỗi.
2. `uv run pytest -m "not integration" -v` — toàn bộ PASS (chạy 2 lần, sau Task 1 và sau Task 3 — không có gì đổi giữa 2 lần).
3. `uv run ruff check trading tests` chạy được (không còn lỗi `program not found`) — dù kết quả PASS sạch hay có lỗi lint thật trong code cũ, đều là kết quả hợp lệ; điều duy nhất KHÔNG được làm là tự sửa các lỗi lint đó.
4. `.github/workflows/ci.yml` là YAML hợp lệ (`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` không lỗi).
5. `git status --short` chỉ hiện đúng `pyproject.toml` (modified) + `.github/workflows/ci.yml` (untracked mới) — không có gì khác ngoài các file/thư mục vốn đã untracked từ trước (ví dụ `.1devtool/`, `.gitnexus_rpc.py` nếu có sẵn — không phải do task này tạo ra).

---

## Báo cáo lại (bắt buộc đủ)

1. Diff đầy đủ của `pyproject.toml` (1 dòng) + toàn bộ nội dung `.github/workflows/ci.yml`.
2. Output đầy đủ của `uv run pytest -m "not integration" -v` (lần chạy cuối, sau Task 3).
3. Output đầy đủ của `uv run ruff check trading tests` — dán nguyên văn, kể cả khi có lỗi lint (đừng tóm tắt, đừng nói "có vài lỗi nhỏ" — dán full output).
4. Output của `git status --short`.
5. Xác nhận rõ: workflow này **CHƯA từng được chạy thật trên GitHub** (vì không push) — CI xanh/đỏ thật sự chỉ biết được sau khi Claude audit xong và push.

**Không tự commit, không tự push.** Chờ Claude audit xong mới commit.
