# Brief đợt 20 — Tối ưu Dockerfile: thứ tự layer, multi-stage, COPY --chown

Ngày giao: 08/09/2026
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

### 1.3. Đợt này KHÔNG phải việc gì

- **Không phải deploy.** Không `docker compose up`, không restart container nào.
- **Không phải rebuild stack đang chạy.** Việc "image cũ hơn code ~39 giờ" là việc riêng,
  của chủ dự án, làm sau và làm có chủ đích — xem mục 6.
- **Không phải chuyện VPS.** `docker-compose.yml:42,65` dùng `build: .` cho cả engine lẫn
  collector, nghĩa là **trên VPS sẽ build từ source tại chỗ**, không pull image từ máy này.
  Nên đợt này làm cho mọi lần build ở mọi nơi nhanh và nhẹ hơn — không phải thao tác chuẩn
  bị riêng cho VPS.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không gọi SSI. Không in secret.
- `.env` không sửa, không commit. `config/config.yaml` **không sửa**.
- **`docker-compose.yml` không sửa.** Đợt này chỉ đụng `Dockerfile`.
- **`pyproject.toml` và `uv.lock` không sửa.** Nếu build đòi đổi lock → dừng, báo cáo.
- **Không sửa file Python nào.** Không sửa `trading/`, `tests/`, `scripts/`.
- **Không dừng, không restart, không xoá container nào.** 6 container đang `Up`; engine và
  collector đang chạy liên tục. Xem mục 3 về cách build mà không đụng chúng.
- **Không xoá image nào.** Kể cả image thử nghiệm của chính đợt này — để lại, tôi audit xong
  mới dọn.
- **Không chạy `docker builder prune`** (đó là brief đợt 19, có điều kiện riêng).
- **Không commit, không push.** Báo cáo lại, tôi commit.
- Phát hiện ngoài phạm vi: báo cáo, không tự sửa.

**GitNexus:** `npx gitnexus analyze` trước và sau. Đợt này không sửa symbol Python nào nên
`gitnexus_impact` không áp dụng; vẫn chạy `gitnexus_detect_changes()` sau khi xong để xác
nhận **không có symbol nào bị ảnh hưởng** — đó chính là kết quả mong đợi. `analyze` sẽ tự
sửa dòng đếm trong `AGENTS.md`/`CLAUDE.md`; bình thường, đừng revert, đừng commit.

---

## 3. Nguyên tắc an toàn: build ra tag riêng, không đụng stack đang chạy

`docker compose build` sẽ ghi đè `ai_auto_trading_system-collector:latest` — tag mà
container đang chạy trỏ tới. **Không làm thế trong đợt này.**

Thay vào đó, build ra một tag thử nghiệm tách biệt:

```powershell
docker build -t dot20-test:new .
```

Tag `dot20-test:new` không xuất hiện trong `docker-compose.yml`, không container nào dùng,
nên mọi thao tác lên nó là vô hại. Stack đang chạy không bị chạm tới.

Kiểm chứng ràng buộc này sau mỗi task: `docker ps` phải vẫn cho đúng 6 container `Up` với
uptime **tăng lên** (chứng tỏ không bị restart).

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

## 4. Rủi ro và cách lùi

| Việc | Rủi ro | Lùi thế nào |
|---|---|---|
| Sửa `Dockerfile` | Thấp — file đã trong git, chưa deploy | `git checkout -- Dockerfile` |
| Build `dot20-test:*` | Rất thấp — tag không nằm trong compose | `docker image rm dot20-test:before dot20-test:new dot20-test:new2` (chỉ tôi làm, sau khi audit) |
| Task 3 sửa `db.py` tạm | Thấp, nhưng **phải hoàn tác** | `git checkout -- trading/storage/db.py`, đã có trong Task 3.1 |
| Stack đang chạy | Không có — đợt này không `compose up`, không restart | — |

Điểm gãy tiềm ẩn duy nhất đáng lo là **editable install** (mục 1.2 điểm 2): nó gãy lúc
chạy chứ không gãy lúc build. Task 2.2 và 2.4 tồn tại riêng để bắt đúng lỗi đó **trước** khi
image này được đưa vào dùng thật.

---

## 5. Báo cáo nghiệm thu — đúng 6 mục, không thêm

1. `npx gitnexus analyze` trước: output ngắn gọn.
2. Task 0: output `docker images` + `docker history` của `dot20-test:before`.
3. Task 1: nội dung `Dockerfile` mới (nguyên văn) + `git diff Dockerfile` + kết quả build.
4. Task 2: output nguyên văn cả 5 phép thử 2.1-2.5.
5. Task 3: log build đã lọc (`CACHED`) + `git status --porcelain` sau khi hoàn tác.
6. Task 4: ba output đo dung lượng + mức giảm thực tế đo được.

Kèm cuối báo cáo: `git status` và `git diff --stat HEAD` (kỳ vọng: **chỉ** `Dockerfile`, cộng
`AGENTS.md`/`CLAUDE.md` nếu `analyze` sửa dòng đếm), `gitnexus_detect_changes()`, và xác nhận
`docker ps` vẫn 6 container `Up`.

**Không viết kết luận, không khuyến nghị, không đề xuất deploy.** Việc quyết định khi nào
rebuild stack thật là của chủ dự án — mục 6.

---

## 6. Việc KHÔNG giao — dành cho chủ dự án

Sau khi tôi audit và commit đợt này, `Dockerfile` mới nằm trong git nhưng **stack đang chạy
vẫn dùng image cũ (build 06/09, cũ hơn code ~39 giờ)**. Để đưa vào dùng thật:

```powershell
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

Việc này **dừng và tạo lại** container collector + engine đang chạy. Đó là lý do nó không
nằm trong brief: thời điểm restart engine là quyết định vận hành, không phải việc agent tự
chọn — nhất là khi nó đang chạy liên tục và phiên giao dịch có giờ cố định.

Sau khi rebuild xong mới đến lượt **brief đợt 19 Task 2** (dọn build cache) — đúng thứ tự
đã ghi ở đó.
