# Đánh giá sẵn sàng chuyển VPS Ubuntu (C1) + Brief đợt 13

Người viết: Claude (planner/auditor) | Ngày: 2026-09-07 | HEAD: `dc601b1`
Cách làm: tự đọc code và tự đo trên hệ thống đang chạy, **không** dựa vào
`DEPLOYMENT.md` như nguồn sự thật — chính nó là một trong những thứ cần kiểm.

---

## 0. KẾT LUẬN

**Hạ tầng gần sẵn sàng hơn tôi tưởng — nhưng có một lỗi sẽ làm chuông báo kêu
láo ngay đêm đầu, và một rủi ro mất dữ liệu vĩnh viễn nếu làm sai thứ tự.**

Và cần nói thẳng một điều trước: **chuyển sang VPS không gỡ được chặn Tier 1.**
Chiến lược vẫn chưa có lợi thế đo được (đợt 11: PF 0,47 trên 574 lệnh khung 5m,
PF 0,74 trên 1.514 lệnh khung ngày). VPS chỉ đổi *chỗ chạy*, không đổi *thứ
chạy*. Việc chuyển VPS đáng làm vì máy dev Windows không phải chỗ để chạy 24/7,
nhưng đừng nhầm nó là một bước tiến tới go-live thật.

---

## 1. NHỮNG GÌ ĐÃ SẴN SÀNG — tự kiểm, không phải đọc tài liệu

Ghi ra để không ai tốn công làm lại:

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| `docker-compose.yml` | **Đạt** | Postgres/NATS/Grafana đều bind `127.0.0.1` (không hở ra internet); cả 6 service có `restart: unless-stopped`; có `mem_limit`/`cpus`. Đây là hình dạng production, không phải compose dev. |
| Tầng lập lịch đa nền tảng | **Đạt, thiết kế tốt** | `sched.sh` là bảng job DUY NHẤT, cả Windows Task Scheduler lẫn cron Ubuntu đều gọi qua nó (`sched.sh` đầu file ghi rõ lý do: "một công thức hai bản thì sớm muộn lệch"). `run_if_docker_up.sh` + `log_rotate.sh` đều bash thuần. |
| `run_hidden.vbs` | **Không phải rủi ro** | Windows-only đúng thiết kế, chính file tự ghi "Ubuntu gọi thẳng `scripts/sched.sh` trong cron, không cần file này". Ubuntu không đụng tới. |
| Kết thúc dòng (CRLF) | **Đạt** | `.gitattributes` có `*.sh text eol=lf`; `git ls-files --eol` xác nhận cả 4 script `.sh` đều `i/lf` trong index. Checkout trên Ubuntu sẽ ra LF — **không** dính lỗi kinh điển `\r: command not found`. |
| Đường dẫn Windows lẫn trong code chạy thật | **Sạch** | Quét `trading/` và `scripts/*.py`: không có `C:\`, `schtasks`, `Program Files` nào. Chỗ duy nhất là `run_hidden.vbs:33` — Windows-only đúng thiết kế. |
| `DEPLOYMENT.md` | **Có, khá đầy đủ** | 475 dòng, đủ §1 prereq → §10 dựng lại container: firewall ufw, TLS nginx+certbot, backup+restore, logrotate, quy trình OTP hằng ngày, cron heartbeat/daily-check/backfill, cảnh báo lệch triển khai. |
| `scripts/backup_db.sh` | **Có** | `pg_dump` trong container → gzip → tự xoá bản > 14 ngày. |

---

## 2. BA VẤN ĐỀ ĐÃ XÁC MINH

### F1 — Tên container hardcode sẽ làm MỌI job giám sát chết câm *và* bắn báo động giả (NGHIÊM TRỌNG)

Đây là lỗi cụ thể nhất, và nó vỡ theo kiểu tệ nhất: **không im lặng, mà kêu sai.**

Hai chỗ hardcode tên container theo tên thư mục của máy dev:

- `scripts/run_if_docker_up.sh:77`:
  `GATE_CONTAINER="${DOCKER_GATE_CONTAINER:-ai_auto_trading_system-postgres-1}"`
- `scripts/deploy_drift_check.py:167`:
  `svc: _image_created_epoch(f"ai_auto_trading_system-{svc}-1") for svc in SERVICES`

Docker Compose đặt tên container theo **tên thư mục chứa** `docker-compose.yml`.
Đây không phải suy luận — tôi đã đọc nhãn của chính container đang chạy:

```
$ docker inspect ai_auto_trading_system-postgres-1 --format "{{json .Config.Labels}}"
"com.docker.compose.project"            : "ai_auto_trading_system"
"com.docker.compose.project.working_dir": "D:\\My_Vault_Obsidian\\Project\\AI_auto_trading_system"
```

Tên project **đúng bằng tên thư mục viết thường**. Mà `DEPLOYMENT.md` §2 hướng dẫn:

```bash
git clone <this-repo-url> /opt/trading
```

→ thư mục `trading` → project `trading` → container thành **`trading-postgres-1`**,
không khớp chuỗi hardcode. Cùng cơ chế đó cũng có nghĩa: **bất kỳ ai clone vào
thư mục tên khác** (kể cả trên Windows) đều dính lỗi này, không riêng VPS.

**Chuỗi hậu quả (đọc kỹ, đây không phải phiền toái nhỏ):**

1. Cổng Docker trong `run_if_docker_up.sh` không tìm thấy container → coi như
   **Docker chưa chạy**, trong khi Docker đang chạy hoàn toàn bình thường.
2. Mọi job giám sát (heartbeat, daily-check, backfill, deploy-drift, engine-cam)
   **không bao giờ chạy** — chỉ ghi dòng `SKIP: docker chua chay`.
3. Tệ hơn: nhánh Docker-chết gọi `scripts/docker_down_alert.py`, nên hệ thống sẽ
   **bắn Telegram báo "Docker chết"** mỗi 5 phút trong giờ giao dịch (trừ chống
   spam 30 phút) — trong khi Docker vẫn sống.

Điểm 3 chính là loại lỗi dự án này đã tốn nhiều công để dọn: kịch bản diễn tập
D1 mở đầu bằng "một chuông chưa từng kêu thử thì không phải chuông", và plan
03/09 đã từng ưu tiên sửa gấp một CRITICAL giả lúc 13:00 vì "một cảnh báo giả
mỗi ngày là cỗ máy sinh ra thói quen bỏ qua cảnh báo". Cấu hình VPS theo đúng
`DEPLOYMENT.md` hiện tại sẽ tạo ra chính cỗ máy đó, ở mức mỗi 30 phút.

Có đường thoát sẵn cho một nửa vấn đề: `DOCKER_GATE_CONTAINER` là biến môi
trường ghi đè được. Nhưng `deploy_drift_check.py:167` thì **không có** lối
thoát tương đương — nó hardcode cứng.

### F2 — `DEPLOYMENT.md` tự mâu thuẫn với chính nó

Cùng một tài liệu: §2 bảo clone vào `/opt/trading`, nhưng các lệnh kiểm chứng ở
§10 lại dùng tên container của máy dev:

- dòng 385–389: `docker exec ai_auto_trading_system-collector-1 sh -c ...`
- dòng 407: `docker inspect -f '{{.Image}}' ai_auto_trading_system-collector-1`
- dòng 267: `ai_auto_trading_system-postgres-1`

Người làm theo tài liệu sẽ gặp `No such container` ở mọi bước kiểm chứng, đúng
lúc cần tài liệu nhất.

### F3 — Dữ liệu 5 phút KHÔNG tái tạo được, và bản sao lưu CHƯA TỪNG ĐƯỢC KIỂM

Đây là rủi ro mất mát vĩnh viễn, và nó nối thẳng với phát hiện của đợt 11.

- Bảng `bars` (5m) bắt đầu **03/04/2026**. Đợt 11 đã đo: **SSI chỉ cho lùi ~150
  ngày** bar 5 phút (150 ngày còn 46 bar, 180 ngày trả 0 bar).
- Hôm nay 07/09, mốc 150 ngày rơi vào ~10/04. Nghĩa là **dựng VPS với DB rỗng
  rồi backfill lại sẽ mất vĩnh viễn phần 03/04→10/04**, và mỗi ngày trôi qua mất
  thêm một ngày nữa.
- Vậy nên **bắt buộc phải pg_dump/restore, không được backfill lại.** DB hiện
  **738 MB** (tự đo hôm nay).

Nhưng bản sao lưu ấy chưa ai kiểm, và có một cái bẫy đã ghi nhận thật:

> `pg_dump -t bars_daily --data-only` cho ra **file rỗng 486 byte**. Đây là
> hypertable TimescaleDB với 556 chunk, bảng cha không giữ dòng nào.

`backup_db.sh` dùng dump **toàn DB** (không `-t`, không `--data-only`) nên *về
lý thuyết* có bao gồm các chunk trong `_timescaledb_internal` — nhưng **lý
thuyết không phải bằng chứng**, và đây là bản sao duy nhất của dữ liệu mà SSI
không phục vụ lại được. Chính `DEPLOYMENT.md` §6 đã viết:

> "Test the restore path at least once against a scratch database before relying
> on it — an untested backup is not a backup."

Câu đó đúng, và **chưa ai làm.**

---

## 3. BRIEF ĐỢT 13

Hai task. Task 1 quan trọng hơn Task 2 — nếu chỉ làm được một, làm Task 1.

### Task 1 — Chứng minh bản sao lưu thật sự phục hồi được (ưu tiên cao nhất)

**Mục tiêu:** trả lời dứt khoát: `backup_db.sh` có tạo ra bản sao **phục hồi
được đầy đủ** không, hay dính bẫy hypertable rỗng?

**Chạy trên máy Windows này vẫn có giá trị — không phải phép thử giả.** Cả
`pg_dump` lẫn `psql` đều chạy **bên trong container Postgres (Linux)**, nên cơ
chế dump/restore của TimescaleDB được kiểm đúng như trên VPS. Thứ khác biệt giữa
hai môi trường chỉ là lớp vỏ gọi lệnh, không phải thứ đang kiểm. (Trên Windows
có thể cần Git Bash để chạy `backup_db.sh` — bình thường, không phải lỗi.)

**File được sửa/tạo**
- **TẠO MỚI:** `scripts/verify_backup_restore.py` — kịch bản kiểm chứng, chạy
  được lặp lại.
- **KHÔNG SỬA:** `scripts/backup_db.sh` (đang kiểm nó, sửa là mất đối tượng
  kiểm), `trading/**`, `docker-compose.yml`, `config/config.yaml`.

**Ràng buộc an toàn — đọc kỹ, đây là DB thật đang chạy**
- **CẤM tuyệt đối** mọi thao tác ghi/xoá lên database `trading`. Không
  `TRUNCATE`, không `DROP`, không `DELETE`, không `UPDATE`.
- Phục hồi vào **database scratch riêng** trong cùng container, tên
  `trading_restore_test`. `CREATE DATABASE` là thao tác cộng thêm, an toàn.
- Được phép `DROP DATABASE trading_restore_test` khi dọn — **chỉ đúng database
  đó**, do chính task này tạo ra. Nếu vì lý do gì mà biến tên bị rỗng, phải
  dừng, không được để lệnh DROP chạy với tên trống.
- Không đụng volume `pgdata`.

**Các bước → kiểm chứng bằng**
1. Chạy `scripts/backup_db.sh` ra thư mục tạm → kiểm chứng bằng: file `.sql.gz`
   tồn tại, in kích thước. **File < 1 MB là dấu hiệu dính bẫy hypertable** (DB
   thật 738 MB) — nếu vậy dừng lại và báo cáo ngay, đó chính là câu trả lời.
2. `CREATE DATABASE trading_restore_test`, phục hồi bản dump vào đó → kiểm chứng
   bằng: lệnh chạy xong, ghi lại **toàn bộ** cảnh báo/lỗi của `psql` (đừng nuốt
   — cảnh báo TimescaleDB ở bước này chính là thứ cần biết).
3. Đếm số dòng **từng bảng** ở cả hai bên (DB thật và bản phục hồi) → kiểm chứng
   bằng: bảng đối chiếu. Tối thiểu phải có: `bars`, `bars_daily`, `orders`,
   `positions`, `heartbeat`, `ssi_auth_state`, `symbol_universe`,
   `account_position_snapshot`, `account_buying_power`, `backfill_progress`.

   **Mốc cứng là "hai bên khớp nhau", KHÔNG phải khớp số tôi viết ra.** Lý do:
   collector và cron backfill vẫn đang chạy, nên số dòng có thể tăng hợp lệ giữa
   lúc tôi viết brief và lúc task chạy. Vì vậy phải **đếm bên nguồn ngay tại
   thời điểm chạy** (đọc số ngay trước khi dump), rồi so với bên phục hồi. Lệch
   một dòng cũng phải nêu.

   Số tôi tự đo lúc 07/09 để tham chiếu (nếu lệch nhiều so với số này thì nói
   rõ, có thể là dấu hiệu khác): `bars` = **934.217**, `bars_daily` =
   **2.983.253**.
4. Kiểm hypertable phục hồi có còn là hypertable không (không chỉ có dòng):
   `SELECT * FROM timescaledb_information.hypertables` ở cả hai bên, so số chunk.
5. Dọn: `DROP DATABASE trading_restore_test` → kiểm chứng bằng: `\l` không còn
   nó; DB `trading` vẫn nguyên (đếm lại `bars` = 934.217).

**Nếu phát hiện bản sao lưu KHÔNG đầy đủ:** dừng, báo cáo, **không tự sửa
`backup_db.sh`**. Sửa quy trình sao lưu là brief riêng — vì lúc đó phải quyết
định giữa `pg_dump -Fc`, `timescaledb_pre_restore()`, hay dump theo `\copy` từng
bảng, và đó là quyết định kiến trúc chứ không phải sửa lặt vặt.

### Task 2 — Gỡ tên container hardcode (F1) và đồng bộ `DEPLOYMENT.md` (F2)

**File được sửa**
- `scripts/run_if_docker_up.sh` (dòng 77)
- `scripts/deploy_drift_check.py` (dòng 167 và chỗ liên quan)
- `DEPLOYMENT.md` (các dòng dùng tên container máy dev: 267, 385–389, 407 — tự
  quét lại toàn file, đừng tin ba số này là đủ)
- **TẠO MỚI:** test cho phần Python trong `tests/`
- **KHÔNG SỬA:** `docker-compose.yml`, `config/config.yaml`, `trading/**`

**Cách làm — bắt buộc theo hướng này**
- Suy ra tiền tố project **từ môi trường, không hardcode**: đọc biến
  `COMPOSE_PROJECT_NAME` nếu có, nếu không thì lấy từ tên thư mục repo
  (chuẩn hoá về chữ thường như Docker Compose làm). Giữ nguyên khả năng ghi đè
  bằng `DOCKER_GATE_CONTAINER` đã có.
- **MỘT CÔNG THỨC MỘT CHỖ**: bash và Python đang cần *cùng* quy tắc đặt tên. Đây
  đúng chỗ dễ đẻ ra hai bản lệch nhau — chính `sched.sh` đã có nguyên đoạn ghi
  lý do tránh điều đó. Nếu không gộp được về một nguồn, **phải nói rõ trong báo
  cáo tại sao không gộp được**, đừng lặng lẽ viết hai bản.
- Không đổi hành vi khi tên khớp — máy dev hiện tại phải chạy y như cũ.

**Kiểm chứng — phải chứng minh cả hai chiều**
1. **Chiều dương (không hồi quy):** trên máy này, `scripts/deploy_drift_check.py`
   vẫn đọc được mốc build của cả `collector` và `engine` (không ra "KHÔNG đọc
   được image build"). Dán output.
2. **Chiều âm (đúng cái đang vỡ):** giả lập tên project khác — đặt
   `COMPOSE_PROJECT_NAME=trading` (hoặc tương đương) và chứng minh code **trước
   khi sửa** thì trượt, **sau khi sửa** thì tìm đúng. Dán cả hai output.
3. Test cho hàm suy ra tên container: có `COMPOSE_PROJECT_NAME`, không có nó,
   và có `DOCKER_GATE_CONTAINER` ghi đè. Dán tên test THẬT
   (`grep -n "^def test_"`).
4. Tự phá hoại: làm hàm suy tên trả về sai, chứng minh test đỏ, khôi phục,
   `grep -rn "SABOTAGE"` rỗng.
5. `uv run ruff check trading tests scripts` sạch;
   `uv run pytest -m "not integration" -q` xanh, nêu số test trước/sau.
6. Quét lại `DEPLOYMENT.md`: không còn dòng nào hardcode
   `ai_auto_trading_system-` mà không kèm giải thích. Dán kết quả grep.

---

## 4. RÀNG BUỘC ĐỨNG (cả hai task)

- `real_trading_enabled` giữ `false`. Không bật, kể cả tạm.
- Không gọi API đặt/huỷ lệnh SSI.
- Không in giá trị secret. Không sửa/commit `.env`.
- **Agent KHÔNG commit, KHÔNG push.** Claude audit rồi mới commit.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB `trading` (ngoại lệ duy nhất đã nêu
  ở Task 1: database scratch do chính task tạo ra).
- `config/config.yaml` không được sửa.
- Phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.
- Trước khi sửa symbol: `gitnexus_impact`; sau khi sửa: `gitnexus_detect_changes`.

---

## 5. NHỮNG GÌ CHỈ CHỦ DỰ ÁN QUYẾT ĐƯỢC — không giao agent

| Việc | Vì sao là của anh |
|---|---|
| **OTP thủ công mỗi ngày giao dịch** | `DEPLOYMENT.md` §8.5: refresh token sống 8 giờ, **không gia hạn được**, và "KHÔNG tự động hoá OTP — SSI yêu cầu OTP thủ công". Trên VPS nghĩa là **SSH vào máy mỗi sáng 8:00–9:00**, mỗi ngày giao dịch, không có đường vòng. Đây là ràng buộc vận hành thật cần chấp nhận trước khi chuyển, không phải thứ code gỡ được. |
| **Thuê VPS, tên miền, TLS** | Hạ tầng cần tài khoản và tiền. `DEPLOYMENT.md` §4 ghi rõ repo không kèm cấu hình nginx vì chưa có tên miền. |
| **Thứ tự chuyển: dump → dựng → restore → mới bật cron** | Phải làm đúng thứ tự này vì F3. Đừng để cron backfill chạy trên DB rỗng trước khi restore xong — nó sẽ "lấp" bằng dữ liệu SSI chỉ có ~150 ngày và làm mờ mất việc phần cũ đã mất. |
| **Có chuyển VPS bây giờ không** | Chặn Tier 1 (chiến lược chưa có edge) vẫn nguyên. Chuyển VPS là việc hạ tầng hợp lý cho vận hành 24/7, nhưng không đưa hệ thống gần go-live thật hơn. |

---

## 6. CỐ Ý KHÔNG GIAO

- **Sửa `backup_db.sh`** — chờ kết quả Task 1. Sửa trước khi biết nó có hỏng
  không là đoán mò.
- **Viết script tự động hoá chuyển VPS** — chưa có VPS, viết ra không kiểm
  chứng được, và một script triển khai chưa từng chạy thật thì nguy hiểm hơn là
  làm tay theo tài liệu.
- **Cấu hình nginx/TLS** — phụ thuộc tên miền chưa có.
- **Đụng vào quyết định Tier 1, nhánh BÁN (J), đa tài khoản, `real_order_account`**
  — đang hoãn theo quyết định của chủ dự án.
