# Brief đợt 19 — Dọn image Docker cũ không dùng nữa

Ngày giao: 08/09/2026
Base: `18fa6e7` (main), cây làm việc sạch.
Người giao: Claude (planner/auditor).

---

## 1. Vì sao đợt này, và nó KHÔNG phải việc gì

Đây là việc O-5 trong danh sách tồn từ đợt 17: dọn image Docker cũ. Đợt này **không đụng
một dòng code nào**, không sửa file nào trong repo, không có test nào phải chạy. Nó là
việc vận hành máy trạm, và điều duy nhất khiến nó cần một brief là vì lệnh dọn Docker
sai một chữ thì xoá luôn thứ đang chạy tiền thật.

Nói thẳng: **`docker system prune -a` là lệnh bị cấm trong đợt này.** Lý do ở mục 4.

---

## 2. Hiện trạng đo được (08/09/2026)

`docker system df`:

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          20        8         6.977GB   1.298GB (18%)
Containers      10        6         9.167MB   249.9kB (2%)
Local Volumes   7         7         1.466GB   0B (0%)
Build Cache     182       0         5.472GB   4.207GB
```

Hai điều đáng chú ý ngay:

1. **Build cache (4,207 GB) lớn hơn image chết (1,298 GB) hơn ba lần.** Nếu mục tiêu là
   lấy lại dung lượng ổ, phần thưởng lớn nhất không nằm ở chỗ anh nghĩ.
2. **Không có image dangling nào** (`docker images -f dangling=true` trả về rỗng). Nên
   `docker image prune` (không `-a`) sẽ không dọn được gì cả — đừng dùng.

Container đang sống (không được đụng vào image của chúng):

```
ai_auto_trading_system-collector-1   ai_auto_trading_system-collector      Up 13 hours
ai_auto_trading_system-engine-1      ai_auto_trading_system-engine         Up 13 hours
ai_auto_trading_system-postgres-1    timescale/timescaledb:latest-pg16     Up 13 hours (healthy)
ai_auto_trading_system-nats-1        nats:2.10-alpine                      Up 13 hours
ai_auto_trading_system-nats-test-1   nats:2.10-alpine                      Up 13 hours
ai_auto_trading_system-grafana-1     grafana/grafana:11.2.0                Up 13 hours
```

Container đã tắt, **thuộc dự án khác** (xem mục 5):

```
infra-grafana-1      grafana/grafana:10.4.0             Exited (137) 8 weeks ago
infra-timescaledb-1  timescale/timescaledb:latest-pg16  Exited (0)   8 weeks ago
infra-clickhouse-1   clickhouse/clickhouse-server:23.8  Exited (137) 8 weeks ago
infra-prometheus-1   prom/prometheus:v2.51.0            Exited (0)   8 weeks ago
```

---

## 3. Ràng buộc

- **Không dừng, không restart, không xoá** 6 container đang `Up`. Engine và collector đang
  chạy 13 tiếng liên tục; dừng chúng là làm gãy phiên chạy, không phải dọn dẹp.
- **Không đụng volume.** `docker volume rm`, `docker volume prune` — cấm tuyệt đối. Trong
  7 volume có `ai_auto_trading_system_pgdata` (toàn bộ DB `trading`, bao gồm `bars_daily`
  đã nạp lại 30/08) và 4 volume `infra_*` của dự án khác.
- **Không đụng network.** `docker network prune` — không cần, không làm.
- Không sửa `docker-compose.yml`, không sửa file nào trong repo.
- **Không commit, không push.** Đợt này gần như chắc chắn không sinh thay đổi git nào;
  nếu có (ví dụ `npx gitnexus analyze` sửa dòng đếm), báo cáo lại, để tôi commit.
- Nếu bất kỳ lệnh nào báo lỗi hoặc hỏi xác nhận ngoài dự kiến: **dừng, báo cáo**, không tự
  thêm `-f` để vượt qua.

---

## 4. Lệnh bị CẤM và vì sao

| Lệnh | Vì sao cấm |
|---|---|
| `docker system prune -a` | `-a` xoá mọi image không gắn với container **đang chạy**. Nó sẽ xoá luôn `grafana/grafana:10.4.0`, `clickhouse/clickhouse-server:23.8`, `prom/prometheus:v2.51.0` (dự án khác) và cả `clickhouse/clickhouse-server:24`. Tổng ~3 GB phải tải lại qua mạng. |
| `docker system prune --volumes` | Xoá volume. Xem mục 3. |
| `docker volume prune` / `docker volume rm` | Như trên. `infra_*` hiện không có container nào đang chạy → chúng bị coi là "unused" và sẽ bị xoá thật. |
| `docker image prune -a` | Cùng lý do với `system prune -a`. |
| `docker builder prune -a` | `-a` xoá cả cache đang được image hiện tại dùng (1,265 GB đang active). Dùng bản có `--filter` ở Task 2. |

Nguyên tắc chung của đợt này: **xoá theo danh sách chỉ định đích danh, không xoá theo
lệnh quét.** Danh sách 10 image ở Task 1 là danh sách đóng.

---

## Task 1 — Xoá 10 image chết theo tên đích danh

### 1.1. Bằng chứng chúng đã chết

Ba lớp kiểm tra, cả ba đều âm tính:

1. **Không container nào tham chiếu.** Đối chiếu `docker ps -a` ở mục 2 — không tên nào
   trong 10 image dưới đây xuất hiện.
2. **Không file nào trong repo tham chiếu.** `git grep -E
   "autotrading-(engine|strategy|ssi-connector)|autotradingcheck|ssi-connector:dev"` trả
   về exit code 1 (không khớp dòng nào).
3. **`docker-compose.yml` không tham chiếu.** File chỉ khai báo 6 service:
   `postgres` (`timescale/timescaledb:latest-pg16`), `nats` và `nats-test`
   (`nats:2.10-alpine`), `engine` và `collector` (`build: .`), `grafana`
   (`grafana/grafana:11.2.0`).

Chúng là tàn dư của lần đặt tên cũ (07/06/2026) và một image dev lẻ (12/07/2026), từ
trước khi dự án đổi sang tên `ai_auto_trading_system-*`.

### 1.2. Danh sách đóng — 10 image

| # | Repository:Tag | Image ID | Size | Ngày tạo |
|---|---|---|---|---|
| 1 | `autotradingcheck-ssi-connector:latest` | `9f6fba6e8029` | 232MB | 07/06/2026 |
| 2 | `autotrading-engine:latest` | `0b6652943f1d` | 21.3MB | 07/06/2026 |
| 3 | `autotrading-engine:local` | `e25cf1186b3d` | 21.3MB | 07/06/2026 |
| 4 | `autotrading-engine:root-check` | `653990f130f0` | 21.3MB | 07/06/2026 |
| 5 | `autotrading-ssi-connector:local` | `1d182ee8a031` | 232MB | 07/06/2026 |
| 6 | `autotrading-ssi-connector:root-check` | `5b804e0e3876` | 232MB | 07/06/2026 |
| 7 | `autotrading-strategy:latest` | `36f6cc19ba3f` | 359MB | 07/06/2026 |
| 8 | `autotrading-strategy:local` | `18568fb775f6` | 359MB | 07/06/2026 |
| 9 | `autotrading-strategy:root-check` | `bccf7e0afb68` | 359MB | 07/06/2026 |
| 10 | `ssi-connector:dev` | `c6e9b76eb1f9` | 231MB | 12/07/2026 |

**Cảnh báo về con số:** cộng cột Size ra ~2,07 GB, nhưng `docker system df` chỉ báo
`RECLAIMABLE 1.298GB`. Chênh lệch là do các image này **dùng chung layer** với nhau và
với image đang sống. Con số đúng để kỳ vọng là **~1,3 GB**, không phải 2,07 GB. Nếu sau
khi xoá mà chỉ lấy lại được ~1,3 GB thì đó là **đúng**, không phải lỗi.

### 1.3. Lệnh

Xoá theo `repository:tag`, **không** theo image ID — ID có thể trùng giữa nhiều tag và
xoá theo ID sẽ kéo theo tag mà brief này không liệt kê.

```powershell
docker image rm autotradingcheck-ssi-connector:latest `
                autotrading-engine:latest `
                autotrading-engine:local `
                autotrading-engine:root-check `
                autotrading-ssi-connector:local `
                autotrading-ssi-connector:root-check `
                autotrading-strategy:latest `
                autotrading-strategy:local `
                autotrading-strategy:root-check `
                ssi-connector:dev
```

Không thêm `-f`. Nếu Docker từ chối xoá một image nào đó vì "image is being used by
container X", **dừng lại và báo cáo tên container X** — nghĩa là mục 1.1 có lỗ hổng và
brief này sai, phải sửa brief chứ không phải ép xoá.

### 1.4. Kiểm chứng

- `docker images` → không còn dòng nào bắt đầu bằng `autotrading`, `autotradingcheck`,
  hoặc `ssi-connector`. Còn đúng **10 image**.
- `docker system df` → dòng `Images` cho `TOTAL 10`, `ACTIVE 8`.
- `docker ps` → vẫn đúng 6 container `Up`, cùng thời gian uptime tăng lên (không bị
  restart).
- Chép nguyên văn output cả ba lệnh vào báo cáo.

---

## Task 2 — Dọn build cache (chỉ làm SAU khi rebuild image)

### 2.1. Thứ tự quan trọng — đọc kỹ

Trong danh sách việc tồn còn có: **rebuild image collector/engine** (deploy drift 14
phút). Build cache tồn tại chính là để lần rebuild đó nhanh.

→ **Nếu chưa rebuild: đừng chạy Task 2.** Rebuild trước, dọn cache sau. Dọn trước chỉ
biến một lần build 2 phút thành một lần build 10 phút, đổi lấy đúng số GB như nhau.

Nếu chủ dự án xác nhận đã rebuild xong (hoặc chấp nhận build chậm), làm tiếp 2.2.

### 2.2. Lệnh

Dùng filter thời gian, **không** dùng `-a`:

```powershell
docker builder prune --filter until=168h -f
```

`until=168h` = giữ lại cache của 7 ngày gần nhất (build gần nhất là 06/09), xoá phần cũ
hơn. Đây là lựa chọn bảo thủ: nó **sẽ không** thu hồi hết 4,207 GB. Con số thu về thực tế
là bao nhiêu thì cứ báo cáo đúng như vậy — brief này không đặt chỉ tiêu GB.

### 2.3. Kiểm chứng

- `docker system df` trước và sau, chép cả hai vào báo cáo, nêu rõ dòng `Build Cache`
  thay đổi thế nào.
- `docker ps` → vẫn 6 container `Up`.

---

## 5. Phần KHÔNG làm — chuyển thành câu hỏi cho chủ dự án

Có một cụm tài nguyên nữa chiếm chỗ, nhưng **agent không được đụng vào**:

- 4 container `infra-*` đã tắt 8 tuần.
- 4 volume `infra_clickhouse_data`, `infra_grafana_data`, `infra_prometheus_data`,
  `infra_timescale_data` (nằm trong tổng 1,466 GB volume).
- 4 image chỉ phục vụ chúng: `clickhouse/clickhouse-server:23.8`,
  `clickhouse/clickhouse-server:24` (không container nào dùng), `grafana/grafana:10.4.0`,
  `prom/prometheus:v2.51.0` — cộng lại ~3,1 GB.

Lý do không đụng: **thư mục `infra/` không tồn tại trong repo này.** Compose project tên
`infra` thuộc về một dự án khác trên cùng máy. Xoá volume của nó là xoá dữ liệu mà repo
này không có cách nào khôi phục, và không có gì trong repo cho biết dữ liệu đó còn giá
trị hay không.

→ **Q-6 (mới, cho chủ dự án):** cụm `infra` có còn dùng không? Nếu không, đó là ~3,1 GB
image + tối đa 1,466 GB volume. Nhưng đây là quyết định của anh, và phải làm từ thư mục
gốc của dự án `infra` chứ không phải từ đây.

Ngoài ra `alpine:latest` (13 MB) không container nào dùng — để lại, quá nhỏ và hay dùng
làm base ad-hoc.

---

## 6. Báo cáo nghiệm thu — đúng 4 mục, không thêm

1. Output nguyên văn `docker images` + `docker system df` + `docker ps` **trước** khi làm.
2. Lệnh Task 1 đã chạy + output nguyên văn của nó.
3. Output nguyên văn `docker images` + `docker system df` + `docker ps` **sau** Task 1.
4. Task 2: đã chạy hay chưa (và nếu chưa thì vì lý do "chưa rebuild"), kèm output nếu có.

Không viết kết luận, không khuyến nghị, không đề xuất dọn thêm gì. Nếu phát hiện thứ gì
đáng dọn ngoài danh sách — **liệt kê ra trong mục riêng cuối báo cáo, không tự xoá.**

---

## 7. Đánh giá rủi ro

| Hạng mục | Rủi ro | Khôi phục nếu sai |
|---|---|---|
| Task 1 (10 image) | Thấp | Không khôi phục được, nhưng cũng không cần: không file nào trong repo build ra chúng nữa. Mất là mất hẳn — và đó là mục đích. |
| Task 2 (build cache) | Rất thấp | Cache tự sinh lại ở lần build sau. Chỉ mất thời gian. |
| Mục 5 (`infra`) | **Cao** | Volume xoá là mất dữ liệu vĩnh viễn. Vì thế không giao. |

Một điểm cần nói thẳng: **đợt này không đem lại giá trị gì cho hệ thống giao dịch.** Nó
chỉ lấy lại dung lượng ổ. Nếu ổ đĩa chưa chật, việc này có thể để đó — ba quyết định lớn
(Tier 1, Q-2, Q-3) mới là thứ đang chặn go-live.
