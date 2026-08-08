# Spec: CI (.github/workflows) + fix ruff thiếu trong pyproject.toml

**Ngày viết:** 2026-08-08
**Phạm vi:** 1 workflow GitHub Actions chạy test + lint trên mọi push và mọi
PR về `main`, cộng thêm `ruff` vào `pyproject.toml` dev deps (hiện thiếu,
làm lệnh `uv run ruff check trading tests` đã document trong `CLAUDE.md` bị
lỗi `program not found`). Chốt phạm vi qua buổi brainstorming ngắn với user
ngày 2026-08-08 (task nhỏ, không mơ hồ).

## Vì sao

`DEPLOYMENT.md` đã ghi rõ "CI/CD — no `.github/workflows` yet; deployment
above is manual" — đây là khoảng trống thật, chưa có bất kỳ CI nào chạy test
tự động khi push/PR. Song song đó, `CLAUDE.md` document lệnh
`uv run ruff check trading tests` nhưng `pyproject.toml`'s `dev` optional-
dependencies chỉ có `pytest`/`pytest-asyncio` — `ruff` chưa từng được thêm,
nên lệnh lint documented không chạy được trên máy sạch (`uv sync --extra
dev` không cài `ruff`). Cả 2 việc đều không cần credential thật, code-only,
agent làm được ngay.

## Quyết định

- **Trigger:** mọi `push` (mọi nhánh) + mọi `pull_request` nhắm vào `main`
  — bắt lỗi sớm kể cả khi đang push thẳng lên feature branch (nhánh hiện tại
  `feature/data-layer`), không chờ tới lúc mở PR.
- **1 job duy nhất**, `ubuntu-latest`, Python 3.11 (khớp `requires-python =
  ">=3.11"` trong `pyproject.toml` — không cần ma trận nhiều version, dự án
  chỉ target 1 version).
- **Cài `uv` qua action `astral-sh/setup-uv`** (action chính thức của
  Astral, không tự viết script cài uv qua `curl`).
- **`uv sync --extra dev`** rồi 2 bước kiểm tra:
  1. `uv run pytest -m "not integration" -v` — **không chạy integration
     test** trong CI vì integration test cần Postgres/NATS thật đang chạy
     (`tests/test_storage.py` và tương tự đã đánh dấu
     `pytestmark = pytest.mark.integration`), GitHub-hosted runner không có
     sẵn — đúng quy ước `-m "not integration"` dự án đã dùng ở local
     (`CLAUDE.md`'s documented test command).
  2. `uv run ruff check trading tests`.
- **`ruff` thêm vào mảng `dev` trong `pyproject.toml`** (`"ruff>=0.6"`).
  **Không thêm `[tool.ruff]` config tuỳ chỉnh** — dùng default rule set của
  ruff, tránh việc phải tune rule không thuộc phạm vi task này. Nếu chạy
  `ruff check` với default rules phát hiện lỗi có sẵn trong code cũ, đó là
  phát hiện cần **báo cáo lại**, không phải việc tự sửa hàng loạt trong
  task này (đúng nguyên tắc phạm vi phẫu thuật — xem mục "Ngoài phạm vi").
- **Không thêm `ruff format --check`** — `CLAUDE.md` chỉ document `ruff
  check`, không mở rộng thêm việc chưa được yêu cầu.
- **Không sửa `DEPLOYMENT.md`'s dòng "CI/CD — no `.github/workflows` yet"**
  trong phạm vi spec này để tránh lấn sang việc dọn doc không liên quan —
  nếu Claude (planner) audit thấy hợp lý, tự cập nhật dòng đó sau khi
  workflow đã chạy xanh, không phải việc giao cho agent thực thi.

## Giả định cần nêu rõ (không giấu)

- `uv sync --extra dev` cài được `ssi-fc-data`/`ssi-sdk` trên
  GitHub-hosted runner mà không cần credential nào — cả 2 đều là gói pip
  công khai, không phải private package cần auth. Nếu agent thực thi gặp
  lỗi cài đặt khác khi thực sự chạy workflow (không thể verify cục bộ
  100% vì cần chạy trên GitHub Actions thật), **báo cáo lại thay vì tự
  đoán cách vá**.
- Repo hiện KHÔNG có `[tool.ruff]` section — mặc định ruff sẽ dùng rule set
  mặc định của nó (không phải rule set rỗng). Chấp nhận được vì task này
  không yêu cầu tune rule cụ thể nào.

## Thiết kế

### `.github/workflows/ci.yml` (mới)

```yaml
name: CI

on:
  push:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: uv sync --extra dev
      - run: uv run pytest -m "not integration" -v
      - run: uv run ruff check trading tests
```

### `pyproject.toml` — sửa dòng `dev` (dòng 14)

```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.6"]
```

## Testing / kiểm chứng

- Không có "test tự động cho CI" theo nghĩa unit test — kiểm chứng bằng
  cách thực sự đẩy workflow lên GitHub và xem nó chạy xanh (agent thực thi
  không tự push được theo quy ước dự án — xem phần "Báo cáo lại" trong
  PROMPT_EXECUTE sẽ viết ở bước plan). Trước khi có kết quả CI thật, agent
  thực thi phải **verify được cục bộ tối đa có thể**:
  - `uv sync --extra dev` chạy sạch cục bộ (xác nhận `ruff` cài được, có
    mặt trong `uv.lock`/venv).
  - `uv run pytest -m "not integration" -v` chạy sạch cục bộ, pass hết
    (không đổi hành vi gì, chỉ thêm workflow file — không có lý do test
    fail).
  - `uv run ruff check trading tests` chạy được cục bộ (không còn lỗi
    `program not found`) — nếu nó báo cáo lỗi lint trong code cũ, ghi lại
    **nguyên văn danh sách lỗi** vào báo cáo, không tự sửa.
  - `.github/workflows/ci.yml` là YAML hợp lệ — kiểm bằng
    `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`.

## Ngoài phạm vi (nói rõ)

- Sửa/dọn lỗi lint mà `ruff check` phát hiện trong code cũ (nếu có) — chỉ
  báo cáo lại.
- `ruff format` / `[tool.ruff]` tuning.
- Thêm workflow build/deploy Docker image, thêm badge CI vào README.md.
- Sửa dòng "CI/CD — no `.github/workflows` yet" trong `DEPLOYMENT.md`.
- Bất kỳ thay đổi nào tới `trading/`, `docker-compose.yml`, hay các file
  không liên quan tới CI/lint.
