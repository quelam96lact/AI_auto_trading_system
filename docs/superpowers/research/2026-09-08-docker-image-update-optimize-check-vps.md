# Báo cáo: Docker image đã cập nhật mới nhất và tối ưu để deploy VPS Ubuntu chưa?

**Ngày:** 2026-09-08
**Phạm vi:** Chỉ đọc/kiểm chứng (`git log`, `docker inspect`, `docker history`) — không build, không sửa, không deploy.

## Kết luận ngắn gọn

**CHƯA sẵn sàng deploy** — image đang chạy hiện tại **cũ hơn code trong git HEAD**, phải rebuild trước. Dockerfile có 1 điểm tối ưu chưa làm (không chặn deploy).

## 1. Image đang chạy KHÔNG chứa code mới nhất

| Việc | Bằng chứng |
|---|---|
| Image `ai_auto_trading_system-collector:latest` / `-engine:latest` build lúc | `2026-09-06T00:45:03Z` (`docker inspect ... --format '{{.Created}}'`) |
| File `trading/storage/db.py` — được `COPY trading ./trading` vào image (`Dockerfile:12`) — sửa sau đó | commit `0d2b439` "fix(dot 17): mat xich universe vao git, don rac phi, dan nhan spike", `2026-09-07 23:04:41 +0700` (`git log -1 --format="%H %ai %s" -- trading/`) |
| Khoảng cách | ~39 giờ code mới hơn image đang chạy (06/09 07:45 +07 → 07/09 23:04 +07 = 39h19m) |

→ Container collector/engine hiện tại (kể cả trên VPS nếu đã deploy, hoặc local) **không có** bản sửa mới nhất của `db.py`. Trước khi deploy/redeploy lên VPS Ubuntu **bắt buộc** phải:

```bash
docker compose build collector engine
docker compose up -d collector engine
```

Việc "dọn build cache" ở Brief Đợt 19 hoãn Task 2 là đúng logic ("chưa rebuild thì đừng dọn cache để rebuild sau nhanh hơn") — nhưng bản thân đó chỉ nói về cache thừa, không có nghĩa là image hiện tại đã cập nhật đủ code. Hai việc khác nhau.

## 2. Dockerfile chưa tối ưu — thiếu multi-stage build

Bằng chứng từ `docker history ai_auto_trading_system-collector:latest --no-trunc`:

```
66.9MB  RUN pip install --no-cache-dir uv==0.12.1
35.6MB  RUN uv sync --frozen --no-dev
```

`uv` (66.9MB layer) chỉ cần lúc **build** để chạy `uv sync` (`Dockerfile:14`), nhưng vì Dockerfile là **single-stage** nên `uv` + pip metadata bị giữ **vĩnh viễn** trong image thành phẩm dù runtime chỉ cần `python -m trading....` (`Dockerfile:21`).

**Đề xuất (chưa làm, không chặn go-live):**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.1
COPY pyproject.toml uv.lock ./
COPY trading ./trading
COPY config ./config
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/trading ./trading
COPY --from=builder /app/config ./config
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]
```

Giảm ước tính **~66.9MB một lần** (không phải ×2). Đã kiểm chứng bằng
`docker inspect --format '{{range .RootFS.Layers}}...'`: collector và engine có **11 layer
giống hệt nhau, 0 layer khác biệt** — chúng chỉ khác metadata `CMD`, còn compose ghi đè
`command` cho từng service. Docker lưu một bản layer trên đĩa và registry cũng chỉ push
một lần, nên tiết kiệm không nhân đôi.

## 3. Điểm đã đúng — không cần sửa

| Việc | Bằng chứng |
|---|---|
| `.dockerignore` loại đúng `.env`, `.git`, `tests`, `docs`, `archive` — không leak secret vào build context | nội dung `.dockerignore` (đọc trực tiếp) |
| Lockfile pin, build tái lập được | `Dockerfile:14` `uv sync --frozen --no-dev` |
| Không chạy container bằng root | `Dockerfile:18-19` `useradd --uid 10001 appuser` + `USER appuser` |
| postgres/nats/grafana không public ra internet | `docker-compose.yml:8,21,87` đều bind `127.0.0.1:...` |
| Resource limit có sẵn cho từng service | `docker-compose.yml` mọi service đều có `mem_limit`/`cpus` |

## Việc cần làm trước khi deploy VPS (theo thứ tự)

1. `docker compose build collector engine` — lấy đúng `db.py` mới nhất (bắt buộc, không tùy chọn).
2. (Tùy chọn, không chặn) Áp dụng multi-stage build ở trên để giảm kích thước image.
3. Sau rebuild: `docker compose up -d`, xác nhận `docker inspect <container> --format '{{.Created}}'` mới hơn commit `0d2b439`.
