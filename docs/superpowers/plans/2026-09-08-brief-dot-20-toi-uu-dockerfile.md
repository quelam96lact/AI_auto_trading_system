# Brief đợt 20 — Tối ưu Dockerfile + triển khai + dọn build cache

Ngày giao: 08/09/2026 (cập nhật cùng ngày: bổ sung Task 5 triển khai và Task 6 dọn cache —
chủ dự án đã quyết giao trọn gói cho agent, xem mục 7)
Base: `2216db6` (main), cây làm việc sạch, 609 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).
Đầu vào: `docs/superpowers/research/2026-09-08-docker-image-update-optimize-check-vps.md`
(đã audit, đã sửa hai con số sai — xem mục 1.2).

---

## 1. Vì sao đợt này

### 1.1. Ba vấn đề, xếp theo mức quan trọng thật

Dockerfile hiện tại (21 dòng, single-stage) có ba điểm chưa tối ưu. Thứ tự dưới đây
**không** giống thứ tự trong báo cáo đầu vào, vì báo cáo đó xếp sai trọng số:

**(A) Thứ tự layer sai — đây mới là vấn đề lớn nhất.**

```
Dockerfile:11   COPY pyproject.toml uv.lock ./
Dockerfile:12   COPY trading ./trading        <-- code
Dockerfile:13   COPY config ./config
Dockerfile:14   RUN uv sync --frozen --no-dev  <-- 35.6MB, cai dependency
```

`COPY trading` nằm **trước** `uv sync`. Docker vô hiệu hoá cache từ layer đầu tiên thay
đổi trở đi, nên **mỗi lần sửa một dòng code Python là toàn bộ layer cài dependency 35.6 MB
bị dựng lại**. Đây là nguyên nhân build chậm và là lý do build cache phình lên 5,47 GB
(xem brief đợt 19 mục 2). Nó ảnh hưởng mỗi lần deploy, không chỉ một lần.

**(B) Single-stage giữ lại `uv` — 66.9 MB.**

`docker history` cho thấy `RUN pip install --no-cache-dir uv==0.12.1` tạo layer **66.9 MB**.
`uv` chỉ cần lúc build để chạy `uv sync`; runtime chạy `python -m trading...` (dòng 21),
không dùng `uv`. Nhưng single-stage thì layer đó nằm lại vĩnh viễn trong image thành phẩm.

**(C) `RUN chown -R` nhân bản file — 31.3 MB.**

```
31.3MB  RUN /bin/sh -c useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
```

`chown -R` đổi metadata của mọi file trong `/app` (gồm cả `.venv`), và vì layer Docker là
copy-on-write, **toàn bộ file bị đổi chủ được ghi lại lần nữa** thành 31.3 MB. Dùng
`COPY --chown=` thì quyền được đặt ngay lúc copy, không sinh layer nhân bản.

Tổng dung lượng dự kiến giảm: **~98 MB** (66.9 + 31.3). Xem mục 1.2 về cách đọc con số này.

### 1.2. Hai con số trong báo cáo đầu vào đã bị sửa — đừng dùng bản cũ

Tôi đã audit báo cáo đầu vào và sửa hai chỗ sai. Nêu ở đây để agent không đọc lại bản cũ
ở đâu đó rồi lấy số sai:

1. **Độ trễ code so với image**: báo cáo ghi "~22 giờ", đúng là **~39 giờ**
   (06/09 07:45 +07 → 07/09 23:04 +07 = 39h19m). Báo cáo đọc nhầm ngày image.
2. **Mức tiết kiệm**: báo cáo ghi "~134MB tổng (2 image → ×2)". Sai. Tôi so bộ layer:

   ```
   so layer collector: 11
   so layer engine   : 11
   layer khac nhau   : 0
   ```

   Hai image **giống hệt nhau về filesystem**, chỉ khác metadata `CMD` (và compose ghi đè
   `command` cho cả hai service). Docker lưu một bản layer trên đĩa; registry cũng push
   một lần. Tiết kiệm là **một lần**, không nhân đôi.

→ Khi báo cáo kết quả, con số đúng để so là **kích thước một image**, không phải tổng hai.

### 1.3. Phạm vi đợt này — và ranh giới còn lại

Đợt này gồm **6 task, theo đúng thứ tự**, không được đảo:

| Task | Việc | Đụng vào stack thật? |
|---|---|---|
| 0 | Chụp mốc "trước" | Không |
| 1 | Viết lại `Dockerfile` | Không |
| 2 | 5 phép thử image mới không gãy | Không |
| 3 | Chứng minh cache layer đã sửa | Không |
| 4 | Đo mức giảm thật | Không |
| **5** | **Rebuild + triển khai collector/engine** | **CÓ — dừng và tạo lại 2 container** |
| **6** | **Dọn build cache** (gộp từ brief đợt 19 Task 2) | Không |

Task 0-4 là phần an toàn tuyệt đối. **Task 5 là ranh giới**: từ đây trở đi agent chạm vào
hệ thống đang chạy. Đọc mục 3 và Task 5 thật kỹ trước khi bước qua.

**Vẫn KHÔNG phải chuyện VPS.** `docker-compose.yml:42,65` dùng `build: .` cho cả engine lẫn
collector, nghĩa là **trên VPS sẽ build từ source tại chỗ**, không pull image từ máy này.
Đợt này làm cho mọi lần build ở mọi nơi nhanh và nhẹ hơn — không phải thao tác chuẩn bị
riêng cho VPS. Không cấu hình gì cho VPS trong đợt này.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không gọi SSI. Không in secret.
- `.env` không sửa, không commit. `config/config.yaml` **không sửa**.
- **`docker-compose.yml` không sửa.** Đợt này chỉ đụng `Dockerfile`.
- **`pyproject.toml` và `uv.lock` không sửa.** Nếu build đòi đổi lock → dừng, báo cáo.
- **Không sửa file Python nào.** Không sửa `trading/`, `tests/`, `scripts/`.
- **Trong Task 0-4: không dừng, không restart, không xoá container nào.** Xem mục 3.
- **Chỉ được restart đúng 2 container** `collector` và `engine`, đúng **một lần**, ở Task 5.
  **Không đụng** `postgres`, `nats`, `nats-test`, `grafana` — vì thế lệnh có `--no-deps`.
- **Nếu Task 5 thất bại: lùi theo mục Task 5.5, KHÔNG restart lại lần hai.** Xem mục 2.1.
- **Không xoá image nào**, kể cả image thử nghiệm `dot20-test:*` và image lùi
  `dot20-rollback-*`. Để lại, tôi audit xong mới dọn.
- **Không xoá volume, không `docker volume prune`, không `docker system prune`** (dù có `-a`
  hay không). Task 6 chỉ dùng đúng lệnh được ghi.
- **Không commit, không push.** Báo cáo lại, tôi commit.

### 2.1. Ràng buộc SSI — vì sao "chỉ một lần"

Log collector hiện tại cho thấy nó **đang gọi SSI thật**, mỗi vòng gồm refresh token rồi
`accountBalance` / `position` / `maxBuySell` cho **ba tài khoản** 0434221, 0434226, 0434228:

```
INFO [ssi_sdk.services.token_manager]: Token refreshed successfully
HTTP Request: GET .../trading/accountBalance?clientId=043422&accountNo=0434221 "HTTP/1.1 200 OK"
HTTP Request: GET .../trading/maxBuySell?accountNo=0434221&symbol=HII "HTTP/1.1 200 OK"
...
```

Mỗi lần restart collector là **một chu kỳ xác thực + một loạt request nữa** tới SSI. Ràng
buộc thường trực của dự án là *không cố tình gây 429, SSI chạy đúng một lần*. Vì vậy:

- Task 5 restart **đúng một lần**.
- Nếu container không lên: **đọc log, báo cáo, lùi image** — tuyệt đối **không** chạy
  `docker compose up -d` lặp lại để "thử lại xem sao". Restart lặp là cách nhanh nhất để ăn
  429 và làm hỏng token của cả ba tài khoản.
- Không tự chạy bất kỳ script nào trong `scripts/` có gọi SSI (`spike_ssi_*`, `probe_*`,
  `backfill_*`, `confirm_real_order.py`). Task 5.4 chỉ dùng script đọc DB/docker.
- Phát hiện ngoài phạm vi: báo cáo, không tự sửa.

**GitNexus:** `npx gitnexus analyze` trước và sau. Đợt này không sửa symbol Python nào nên
`gitnexus_impact` không áp dụng; vẫn chạy `gitnexus_detect_changes()` sau khi xong để xác
nhận **không có symbol nào bị ảnh hưởng** — đó chính là kết quả mong đợi. `analyze` sẽ tự
sửa dòng đếm trong `AGENTS.md`/`CLAUDE.md`; bình thường, đừng revert, đừng commit.

---

## 3. Nguyên tắc an toàn: chứng minh image mới chạy được TRƯỚC khi cho nó thay thế

`docker compose build` ghi đè `ai_auto_trading_system-collector:latest` — đúng tag mà
container đang chạy trỏ tới. Ghi đè xong là mất bản cũ, không có đường lùi.

Vì thế thứ tự của đợt này là: **build ra tag thử nghiệm riêng → kiểm chứng đủ 5 phép thử →
gắn nhãn lùi cho image cũ → mới cho phép ghi đè.**

Task 0-4 dùng tag tách biệt:

```powershell
docker build -t dot20-test:new .
```

Tag `dot20-test:*` không xuất hiện trong `docker-compose.yml`, không container nào dùng, nên
mọi thao tác lên nó là vô hại.

Kiểm chứng sau mỗi task 0-4: `docker ps` vẫn đúng 6 container `Up`, uptime **tăng lên**
(chứng tỏ không bị restart ngoài ý muốn).

### 3.1. Cổng thời gian — bắt buộc kiểm trước Task 5

Phiên giao dịch VN là 09:00-15:00. **Không được chạy Task 5 trong khoảng 08:45-15:15 giờ VN
các ngày trong tuần.** Trước khi bắt đầu Task 5, chạy:

```powershell
Get-Date -Format "yyyy-MM-dd HH:mm:ss dddd"
```

Chép output vào báo cáo. Nếu rơi vào cửa sổ cấm: **dừng lại, báo cáo, không làm Task 5 và
Task 6** — Task 0-4 vẫn nộp được, phần còn lại để lần sau.

(Tại thời điểm giao brief: 08/09/2026 21:29 thứ Ba — ngoài phiên, hợp lệ.)

---

## Task 0 — Chụp mốc "trước"

Trước khi sửa gì, build Dockerfile **hiện tại** ra tag riêng để có mốc so sánh công bằng
(cùng máy, cùng thời điểm, cùng context):

```powershell
docker build -t dot20-test:before .
docker images dot20-test:before --format "{{.Size}}"
docker history dot20-test:before --format "{{.Size}}`t{{.CreatedBy}}" --no-trunc
```

**Kiểm chứng:** chép nguyên văn cả hai output vào báo cáo. Đây là số "trước" duy nhất được
dùng để so sánh — **không** dùng `ai_auto_trading_system-collector:latest` (366MB) làm mốc,
vì image đó build từ code cũ hơn 39 giờ nên không so được sòng phẳng.

---

## Task 1 — Viết lại Dockerfile

### 1.1. Nội dung mới

Thay toàn bộ `Dockerfile` bằng nội dung dưới đây. **Giữ nguyên khối comment tiếng Việt về
uv/uv.lock** (dòng 4-8 hiện tại) — nó ghi lại một quyết định có lịch sử điều tra, không
phải rác.

```dockerfile
# ---- Stage build: co uv, co toolchain. Moi thu o day BI VUT DI. ----
FROM python:3.12-slim AS builder
WORKDIR /app

# uv + uv.lock thay cho `pip install .`: build phai TAI LAP DUOC. `pip install .`
# bo qua uv.lock, nen moi lan build lai co the keo ve phien ban ssi-sdk /
# ssi-fc-data khac voi phien ban da duoc kiem chung — hanh vi parser/stream doi
# ma khong ai biet. Repo nay co han lich su dieu tra hanh vi THAT cua SDK
# (xem PLAN_INDEX_STREAMING.md), khong duoc de dependency troi noi.
RUN pip install --no-cache-dir uv==0.12.1

# THU TU LAYER CO CHU DICH: cai dependency TRUOC khi copy code. Dependency chi
# doi khi pyproject/uv.lock doi (hiem); code doi moi ngay. Neu copy code truoc
# thi moi lan sua 1 dong Python la layer dependency 35.6MB bi dung lai tu dau.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Gio moi den code. Layer tren van hit cache khi chi co code doi.
COPY trading ./trading
COPY config ./config
RUN uv sync --frozen --no-dev

# ---- Stage runtime: khong co uv, khong co pip metadata cua uv. ----
FROM python:3.12-slim
WORKDIR /app

# Khong chay production bang root. Tao user TRUOC khi copy de dung --chown:
# `RUN chown -R` sau khi copy se ghi lai toan bo file da doi chu thanh mot
# layer nhan ban (31.3MB o ban cu).
RUN useradd --create-home --uid 10001 appuser

# WORKDIR PHAI la /app: `trading` duoc cai EDITABLE, file
# __editable__.trading-0.1.0.pth trong .venv tro cung vao /app/trading.
# Doi WORKDIR o stage nay se lam `import trading` gay.
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --from=builder --chown=appuser:appuser /app/trading ./trading
COPY --from=builder --chown=appuser:appuser /app/config ./config

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]
```

### 1.2. Ba điểm dễ làm sai — đọc kỹ

1. **`--no-install-project` ở lần `uv sync` đầu là bắt buộc.** Không có nó, uv sẽ cố cài
   chính package `trading` trong khi thư mục `trading/` chưa được copy vào → build lỗi.
2. **`WORKDIR /app` ở stage runtime không được đổi.** `trading` cài editable, file
   `__editable__.trading-0.1.0.pth` trỏ cứng vào `/app/trading`. Đổi WORKDIR thành
   `/srv` hay `/opt/app` sẽ khiến `import trading` gãy — và gãy lúc **chạy**, không phải
   lúc build, nên build vẫn xanh còn container thì chết. Task 2.4 bắt được lỗi này.
3. **`useradd` phải đặt TRƯỚC các dòng `COPY --chown`**, nếu không `--chown=appuser` sẽ
   thất bại vì user chưa tồn tại.

### 1.3. Kiểm chứng Task 1

```powershell
docker build -t dot20-test:new .
```

Build phải thành công, exit code 0. Chép output vào báo cáo (có thể rút gọn phần tải gói,
nhưng **giữ nguyên** dòng cuối và mọi dòng có chữ `ERROR`/`WARN`).

---

## Task 2 — Kiểm chứng image mới KHÔNG gãy

Đây là phần quan trọng nhất của đợt. Image nhỏ hơn mà chạy không được thì tệ hơn image to.

Chạy đúng 5 phép thử sau trên `dot20-test:new`. Mỗi phép thử chép nguyên văn output.

### 2.1. `uv` đã biến mất (chứng minh multi-stage có tác dụng)

```powershell
docker run --rm --entrypoint sh dot20-test:new -c "which uv || echo 'OK: khong co uv'"
```

Kỳ vọng: `OK: khong co uv`. Nếu vẫn thấy `/usr/local/bin/uv` → multi-stage chưa đúng.

### 2.2. `import trading` trỏ đúng chỗ

```powershell
docker run --rm --entrypoint sh dot20-test:new -c "python -c 'import trading; print(trading.__file__)'"
```

Kỳ vọng chính xác: `/app/trading/__init__.py`. Đây là phép thử bắt lỗi editable-install ở
mục 1.2 điểm 2.

### 2.3. Chạy đúng bằng appuser, không phải root

```powershell
docker run --rm --entrypoint sh dot20-test:new -c "id; stat -c '%U %n' /app /app/.venv /app/trading /app/config"
```

Kỳ vọng: `uid=10001(appuser)`, và cả 4 đường dẫn đều thuộc `appuser`.

### 2.4. Toàn bộ dependency runtime nạp được — phép thử mạnh nhất

Cả hai entrypoint đều có `if __name__ == "__main__":` và **không có lệnh nào ở cấp module
ngoài import + hằng số** (đã kiểm: `collector/main.py` chỉ có `EOD_HOUR, EOD_MINUTE = 15, 5`;
`engine/main.py` chỉ có `CAPITAL = 100_000_000.0`). Nên `import` chúng sẽ kéo toàn bộ cây
dependency thật (nats, psycopg, ssi_sdk, ssi_fc_data, yaml…) mà **không kết nối đi đâu, không
gọi SSI, không chạm DB**:

```powershell
docker run --rm --entrypoint sh dot20-test:new -c "python -c 'import trading.collector.main, trading.engine.main; print(\"OK: nap duoc ca hai entrypoint\")'"
```

Kỳ vọng: `OK: nap duoc ca hai entrypoint`. Bất kỳ `ModuleNotFoundError` nào ở đây nghĩa là
stage runtime thiếu thứ gì đó → dừng, báo cáo, **không tự thêm gói vào pyproject**.

### 2.5. `config/` có mặt

```powershell
docker run --rm --entrypoint sh dot20-test:new -c "ls -la /app/config"
```

Kỳ vọng: thấy `config.yaml`.

---

## Task 3 — Chứng minh cache layer thật sự đã được sửa

Task 1 giảm dung lượng; Task 3 chứng minh phần (A) — vấn đề lớn nhất — thật sự được giải
quyết. **Không bỏ qua task này**: nó là lý do chính của cả đợt.

### 3.1. Cách làm

Sửa một file Python bằng cách thêm một dòng trắng ở cuối, rồi build lại và xem layer
dependency có hit cache không:

```powershell
# Them mot dong trang o cuoi mot file code
Add-Content -Path "trading\storage\db.py" -Value ""

docker build -t dot20-test:new2 . 2>&1 | Tee-Object -Variable buildlog
$buildlog | Select-String -Pattern "CACHED|uv sync|COPY trading"

# HOAN TAC ngay lap tuc
git checkout -- trading/storage/db.py
git status --porcelain
```

### 3.2. Kiểm chứng

- Trong log build phải thấy dòng `uv sync --frozen --no-dev --no-install-project` được đánh
  dấu **`CACHED`**, còn `COPY trading ./trading` thì **không** CACHED.
- `git status --porcelain` sau `git checkout --` phải **không** liệt kê
  `trading/storage/db.py` (đã hoàn tác sạch).
- Chép nguyên văn phần log đã lọc + output `git status` vào báo cáo.

Nếu `uv sync --no-install-project` **không** CACHED thì thứ tự layer vẫn sai — dừng, báo cáo,
đừng tự sửa tiếp.

---

## Task 4 — Đo mức giảm thật

```powershell
docker images dot20-test:before --format "before: {{.Size}}"
docker images dot20-test:new    --format "new   : {{.Size}}"
docker history dot20-test:new --format "{{.Size}}`t{{.CreatedBy}}" --no-trunc
```

### Kiểm chứng

- Chép nguyên văn cả ba output.
- Trong `docker history` của bản mới **không được còn** dòng
  `pip install --no-cache-dir uv==0.12.1` (66.9MB) và **không được còn** layer
  `chown -R appuser:appuser /app` (31.3MB).
- Ghi lại mức giảm thực tế. Dự kiến ~98 MB, nhưng **báo cáo số đo được, không báo cáo số dự
  kiến.** Nếu lệch nhiều so với 98 MB thì cứ ghi đúng số đo và nói rõ là lệch — đừng làm
  tròn cho khớp brief.

---

---

## Task 5 — Rebuild và triển khai (BƯỚC ĐỤNG HỆ THỐNG THẬT)

Chỉ bước vào task này khi **cả Task 1-4 đã xanh** và **cổng thời gian mục 3.1 hợp lệ**. Nếu
bất kỳ phép thử nào ở Task 2 hoặc Task 3 thất bại: **dừng, báo cáo, không làm Task 5.**

### 5.1. Gắn nhãn lùi cho image đang chạy — làm TRƯỚC khi build

`docker compose build` sẽ ghi đè `:latest`. Gắn nhãn thứ hai cho image hiện tại để nó không
biến mất:

```powershell
docker tag ai_auto_trading_system-collector:latest dot20-rollback-collector:pre
docker tag ai_auto_trading_system-engine:latest    dot20-rollback-engine:pre
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | Select-String "dot20-rollback"
```

**Kiểm chứng:** phải thấy đủ 2 dòng, và image ID phải là `880dc8930dde` (collector) và
`212777849854` (engine). Nếu ID khác → có ai đó đã build lại trong lúc này, **dừng, báo cáo**.

Đây là bước không được bỏ. Không có nó thì mục 5.5 vô nghĩa.

### 5.2. Build

```powershell
docker compose build collector engine
```

**Kiểm chứng:** exit code 0. Chép dòng cuối và mọi dòng `ERROR`/`WARN`.

### 5.3. Triển khai — đúng một lần

```powershell
docker compose up -d --no-deps collector engine
```

`--no-deps` là bắt buộc: không có nó, compose có thể đụng cả `postgres` và `nats`.

**Kiểm chứng ngay:**

```powershell
docker ps --format "{{.Names}}|{{.Image}}|{{.Status}}"
```

Kỳ vọng: vẫn 6 container `Up`; `collector-1` và `engine-1` có uptime **vừa reset** (vài
giây/phút), 4 container còn lại giữ uptime cũ (~13+ giờ) — chứng tỏ `--no-deps` có tác dụng.

**Nếu container không lên `Up`: sang thẳng mục 5.5. KHÔNG chạy lại `up -d`.** Xem mục 2.1.

### 5.4. Xác nhận hệ thống còn sống

Chờ **90 giây** cho engine warm-up xong, rồi chạy đúng ba phép kiểm dưới đây.

**(a) Drift đã hết** — đây là bằng chứng chính của Task 5:

```powershell
uv run python scripts/deploy_drift_check.py
echo "exit code: $LASTEXITCODE"
```

Kỳ vọng **exit code 0**. Script này so mốc build image với commit gần nhất chạm `trading/`
(cả hai quy về epoch giây). Exit 1 nghĩa là vẫn còn lệch → báo cáo, đừng tự sửa.

**(b) Log hai container không có lỗi mới:**

```powershell
docker logs --tail 40 ai_auto_trading_system-collector-1
docker logs --tail 40 ai_auto_trading_system-engine-1
```

Chép nguyên văn cả hai.

> **QUAN TRỌNG — đọc trước khi hoảng.** Log engine **trước** đợt này đã có sẵn một traceback
> `psycopg_pool.PoolTimeout: pool initialization incomplete after 30.0 sec` tại
> `/app/trading/storage/db.py:54` lúc khởi động, rồi **tự hồi phục** và chạy tiếp bình thường:
>
> ```
> psycopg_pool.PoolTimeout: pool initialization incomplete after 30.0 sec
> {"level": "INFO", "msg": "engine restored state", "cash": 91215342.15, ...}
> {"level": "INFO", "msg": "warm-up HII xong", "bars": 201, ...}
> ```
>
> Đây là hiện tượng **có từ trước, không phải do đợt 20 gây ra**. Nếu nó xuất hiện lại và
> **theo sau là dòng `engine restored state`** thì hệ thống đang khoẻ — **báo cáo lại, đừng
> lùi image.** Chỉ coi là hỏng khi **không** có dòng `engine restored state` sau đó.

Dấu hiệu khoẻ cần tìm:
- Engine: có `engine restored state`, có `warm-up ... xong`.
- Collector: có `Token refreshed successfully`, không có traceback nào ngoài ghi chú trên.

**(c) Heartbeat:**

```powershell
uv run python scripts/heartbeat_check.py
echo "exit code: $LASTEXITCODE"
```

Exit 0 = ổn, 1 = đã gửi cảnh báo Telegram, 2 = sai cấu hình. Chép cả output lẫn exit code.
Exit 1 hoặc 2 → báo cáo, không tự sửa.

### 5.5. Cách lùi nếu hỏng

Chỉ dùng khi 5.3 không lên `Up`, hoặc 5.4(b) cho thấy engine **không** có
`engine restored state`:

```powershell
docker tag dot20-rollback-collector:pre ai_auto_trading_system-collector:latest
docker tag dot20-rollback-engine:pre    ai_auto_trading_system-engine:latest
docker compose up -d --no-deps collector engine
docker ps --format "{{.Names}}|{{.Status}}"
```

Sau khi lùi: **dừng toàn bộ đợt, không làm Task 6**, báo cáo đầy đủ log lỗi. Đây là lần
`up -d` thứ hai duy nhất được phép, và chỉ để lùi — không phải để thử lại.

---

## Task 6 — Dọn build cache (gộp từ brief đợt 19 Task 2)

Brief đợt 19 hoãn việc này với điều kiện "chỉ làm sau khi đã rebuild". Task 5 vừa rebuild
xong, nên điều kiện đã thoả. **Task này thay thế brief 19 Task 2 — đừng làm cả hai.**

Chỉ chạy khi Task 5 thành công (không phải đường lùi 5.5).

```powershell
docker system df
docker builder prune --filter until=168h -f
docker system df
```

`until=168h` giữ cache 7 ngày gần nhất, xoá phần cũ hơn. **Không dùng `-a`** — `-a` xoá cả
cache mà image hiện tại đang dùng.

**Kiểm chứng:**
- Chép `docker system df` trước và sau, nêu rõ dòng `Build Cache` đổi thế nào.
- `docker ps` vẫn 6 container `Up`, collector/engine giữ nguyên uptime từ Task 5 (không bị
  restart lần nữa).
- Con số thu hồi được là bao nhiêu thì báo đúng vậy — brief không đặt chỉ tiêu GB.

---

## 4. Rủi ro và cách lùi

| Việc | Rủi ro | Lùi thế nào |
|---|---|---|
| Sửa `Dockerfile` (Task 1) | Thấp — file trong git, chưa deploy | `git checkout -- Dockerfile` |
| Build `dot20-test:*` (Task 0-4) | Rất thấp — tag không nằm trong compose | `docker image rm dot20-test:*` (tôi làm sau khi audit) |
| Task 3 sửa `db.py` tạm | Thấp, nhưng **phải hoàn tác** | `git checkout -- trading/storage/db.py`, đã có sẵn trong Task 3.1 |
| **Task 5: ghi đè `:latest`** | **Trung bình** — mất bản image đang chạy | Nhãn `dot20-rollback-*:pre` gắn ở 5.1 |
| **Task 5: restart engine/collector** | **Trung bình** — gián đoạn 2 service, thêm 1 chu kỳ auth SSI | Mục 5.5, dùng đúng một lần |
| Task 6: dọn build cache | Rất thấp | Cache tự sinh lại ở lần build sau |

Hai điểm gãy tiềm ẩn đáng lo, và chỗ nào bắt được chúng:

1. **Editable install** (mục 1.2 điểm 2) — gãy lúc *chạy*, không gãy lúc *build*. Task 2.2 và
   2.4 tồn tại riêng để bắt đúng lỗi đó **trước** khi image được cho thay thế bản đang chạy.
   Đây chính là lý do Task 5 phải đứng sau Task 2, không được gộp.
2. **Restart trúng phiên giao dịch** — cổng thời gian mục 3.1 chặn.

Rủi ro **không** được nhận là "thấp" ở đây: Task 5 dừng engine đang giữ vị thế thật
(`positions: {"HII": 300, "IJC": 400, "AAA": 400}`, cash 91,2 triệu). Engine có khôi phục
trạng thái từ DB khi khởi động lại (`engine restored state`), nên đây là thao tác đã có
đường phục hồi — nhưng vẫn là thao tác lên hệ thống đang giữ tiền, không phải việc vặt.

---

## 5. Báo cáo nghiệm thu — đúng 9 mục, không thêm

1. `npx gitnexus analyze` trước: output ngắn gọn.
2. Task 0: output `docker images` + `docker history` của `dot20-test:before`.
3. Task 1: nội dung `Dockerfile` mới (nguyên văn) + `git diff Dockerfile` + kết quả build.
4. Task 2: output nguyên văn cả 5 phép thử 2.1-2.5.
5. Task 3: log build đã lọc (`CACHED`) + `git status --porcelain` sau khi hoàn tác.
6. Task 4: ba output đo dung lượng + mức giảm thực tế đo được.
7. Task 5: output `Get-Date` (cổng thời gian) + 5.1 nhãn lùi + 5.2 build + 5.3 `docker ps` +
   5.4 cả ba phép kiểm (a)(b)(c) kèm exit code. Nếu phải lùi: ghi rõ đã lùi và vì sao.
8. Task 6: `docker system df` trước/sau + `docker ps`.
9. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`.

Kỳ vọng ở mục 9: `git diff --stat HEAD` chỉ có **`Dockerfile`**, cộng `AGENTS.md`/`CLAUDE.md`
nếu `analyze` sửa dòng đếm. `gitnexus_detect_changes()` kỳ vọng **không symbol nào bị ảnh
hưởng** — đợt này không sửa code Python.

**Không viết kết luận, không khuyến nghị.** Báo cáo chỉ trình bày lệnh đã chạy và output thật.
Nếu phát hiện vấn đề ngoài phạm vi (ví dụ nguyên nhân `PoolTimeout`): **liệt kê ở mục riêng
cuối báo cáo, không tự sửa.**

---

## 6. Tiêu chí dừng — khi nào phải ngừng và báo cáo

Dừng ngay, không đi tiếp, ở bất kỳ tình huống nào sau đây:

| Tình huống | Dừng ở đâu |
|---|---|
| Task 1 build lỗi | Trước Task 2 |
| Bất kỳ phép thử nào trong 2.1-2.5 sai kỳ vọng | Trước Task 3 |
| Task 3: `uv sync --no-install-project` **không** CACHED | Trước Task 4 |
| Task 3: `git status` còn sót thay đổi `db.py` | Hoàn tác cho sạch rồi mới đi tiếp |
| Cổng thời gian 3.1 rơi vào 08:45-15:15 ngày làm việc | Trước Task 5 (nộp Task 0-4) |
| 5.1: image ID không khớp `880dc8930dde`/`212777849854` | Trước Task 5.2 |
| 5.3: container không lên `Up` | Sang 5.5 lùi, rồi dừng hẳn |
| 5.4(a): `deploy_drift_check.py` exit ≠ 0 | Sau 5.4, báo cáo, không làm Task 6 |
| 5.4(b): engine **không** có `engine restored state` | Sang 5.5 lùi, rồi dừng hẳn |
| 5.4(c): `heartbeat_check.py` exit 1 hoặc 2 | Báo cáo, không làm Task 6 |
| Bất kỳ lệnh nào đòi sửa `uv.lock`/`pyproject.toml` | Ngay tại đó |

Nguyên tắc chung: **thấy lạ thì dừng và báo, đừng tự sửa cho chạy được.** Một báo cáo dừng
giữa chừng có bằng chứng rõ ràng thì hữu ích hơn một báo cáo "đã xong" sau khi tự vá.

---

## 7. Ghi chú về thay đổi phạm vi

Bản đầu của brief này (sáng 08/09) chỉ có Task 0-4 và để phần triển khai lại cho chủ dự án,
với lý do: thời điểm restart engine là quyết định vận hành. Chủ dự án đã quyết giao trọn gói
cho agent, nên Task 5 và Task 6 được bổ sung.

Quyết định đó không làm rủi ro biến mất — nó chỉ được **chuyển thành ràng buộc kiểm chứng
được** thay vì thành một câu dặn miệng:

- Thời điểm restart → cổng thời gian mục 3.1.
- Mất image đang chạy → nhãn lùi 5.1 + đường lùi 5.5.
- Restart lặp gây 429 → mục 2.1, đúng một lần.
- Image mới gãy lúc chạy → Task 2 phải xanh trước khi được bước sang Task 5.

Brief đợt 19 (`2026-09-08-brief-dot-19-don-image-docker-cu.md`) vẫn còn giá trị ở **Task 1**
(xoá 10 image chết). **Task 2 của brief 19 đã được gộp vào Task 6 ở đây — không làm hai lần.**
