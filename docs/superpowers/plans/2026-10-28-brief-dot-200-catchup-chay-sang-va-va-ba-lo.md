# Brief đợt 200: catchup chạy thêm mỗi sáng và vá ba lỗ còn lại của đợt 199

Ngày: 28/10/2026. Planner: Claude. Người thực thi: agent.
Nền: đợt 199 (commit `6dc40a7`, `61ac16a`): `scripts/startup_catchup.py` và nhánh `sched.sh catchup`.

**Agent KHÔNG commit, KHÔNG push.** Claude audit rồi mới commit.

## 0. Vì sao có đợt này

Đợt 199 đã chạy thật ngày 28/10 lúc 05:29, EXIT=0, lấp được khối ngoại 26–27/10. Khi audit và vận hành, Claude thấy ba lỗ:

| # | Lỗ | Hậu quả |
|---|---|---|
| L1 | `catchup` chỉ chạy khi host reboot (`@reboot` / AtLogOn). | Docker daemon khởi động lại mà host không reboot, hoặc stack bị `docker compose down` vài ngày, thì không có gì nạp bù theo DB. Chỉ còn cửa sổ 7 ngày của các job đêm. |
| L2 | `scripts/sched.sh catchup --dry-run` ghi vào `logs/catchup.log` thật, label `catchup`. Khi còn ngày thiếu, dry-run thoát 1. DEPLOYMENT.md §9.6 lại đang **khuyên** chạy đúng lệnh này để xem trước. | Heartbeat đọc `EXIT=1` thành CRITICAL giả. Ngược lại, một lần dry-run `EXIT=0` sẽ xóa trạng thái CRITICAL của một lần chạy thật đang hỏng. Đây là bẫy đã gặp ở đợt 156 (memory `pha-thu-qua-sched-sh-ghi-log-that`). |
| L3 | Khi bị cắt 90 ngày, dòng `can chay tay --from <ngay>` in **mốc đã cắt** (`end − 90`), không in ngày bắt đầu thật của khoảng hỏng. | Người vận hành chạy tay theo đúng dòng đó vẫn hở phần trước mốc cắt, mà không biết. |

**Cách làm đã chọn:**
- **L1:** thêm một lượt chạy theo lịch **06:40 thứ Hai–thứ Sáu**, dùng cùng nhánh `catchup`.
  - Lý do: job tính cửa sổ từ DB và idempotent. Khi không có gì để nạp, nó chỉ đọc DB rồi thoát 0, rất nhẹ.
  - 06:40 là trước phiên, sau backup 02:00–03:00.
  - Bất biến 21:30 của đợt 199 vẫn giữ: lúc 06:40, ngày cuối luôn là phiên trước.
  - **Bỏ** phương án hook theo sự kiện Docker (systemd unit, `docker events`): phức tạp hơn, lại khác nhau giữa Ubuntu và Windows.
- **L2:** **sửa ở `sched.sh`**: có `--dry-run` thì ghi vào `catchup-dryrun.log`, label `catchup-dryrun`. Heartbeat không đọc log này. Mã thoát của dry-run **giữ nguyên**, vì người chạy tay cần nó.
- **L3:** in ngày bắt đầu thật.

## 1. Việc cần làm

**Bắt buộc trước khi sửa:**
- Kiểm GitNexus: `node .gitnexus/run.cjs impact <symbol> --direction upstream --repo .` cho `main` của `scripts/startup_catchup.py` và `plan_universe_start`.
- Ghi nguyên văn kết quả vào báo cáo. Kết quả `UNKNOWN` thì xác nhận lại bằng grep.
- Dùng `node .gitnexus/run.cjs`, **không** dùng `npx`.

### 1.1 `scripts/sched.sh`: nhánh `catchup` tách log khi dry-run (L2)

- Giữ dòng `export DOCKER_GATE_WAIT_SECONDS="${DOCKER_GATE_WAIT_SECONDS:-900}"`.
- Trước `exec`, duyệt `"$@"`. Có đối số đúng bằng `--dry-run` thì log là `catchup-dryrun.log`, label là `catchup-dryrun`. Nếu không thì giữ `catchup.log` / `catchup`.
- Viết bằng bash thuần (`for a in "$@"; do ...; done`), không thêm công cụ ngoài.
- **Kiểm trước:** các test đọc nhánh `sched.sh` (`tests/test_sched_args.py::parse_sched_branches`, `tests/test_schedule_watch.py`, `tests/test_deployment_doc.py`) có cần thấy tên log nguyên văn trên dòng `exec` không. Nếu có test nào hỏng vì log là biến:
  - **dừng lại và báo**;
  - **không** sửa test cũ cho vừa.

### 1.2 `scripts/startup_catchup.py`: in ngày bắt đầu thật khi bị cắt (L3)

**Không đổi** chữ ký và giá trị trả về của `plan_universe_start` và `plan_foreign_flow_start`, vì 20 test (a)–(t) của đợt 199 ghim chúng.

Trong `main`, khi một kế hoạch bị cắt, dòng cảnh báo phải chứa ngày bắt đầu thật:
- **Nến ngày / nến 5 phút:**
  - ngày bắt đầu thật là ngày nhỏ nhất trong các `attempted_until` của mã có `status == "ok"` trong `progress` của bước đó;
  - mã không `ok` thì vẫn tính `end − 7` như `plan_universe_start`, nhưng ngày này không bao giờ nhỏ hơn mốc cắt nên không ảnh hưởng.
  - Viết một hàm thuần nhỏ `gap_origin(progress, end, default_days=7) -> date` dùng **cùng** quy tắc chọn ngưỡng với `plan_universe_start`.
  - Hai hàm phải dùng chung một chỗ tính ngưỡng (tách hàm nội bộ `_thresholds`). Không chép quy tắc hai lần.
- **Khối ngoại:** khi bị cắt là do không có dòng nào trong `max_days` ngày. In:
  `[catchup] CANH BAO: khoi ngoai khong co du lieu trong {max_days} ngay, can chay tay --from <ngay cuoi co du lieu hoac 2020-02-26>`.
  - Ngày cuối có dữ liệu lấy bằng **một** câu đọc mới hoặc có sẵn. Ưu tiên tìm trong `Storage` một hàm có sẵn trả max `trading_date` của `foreign_flow_daily`.
  - Không có hàm sẵn thì thêm `read_foreign_flow_last_date() -> date | None` (`SELECT max(trading_date) FROM foreign_flow_daily`).
  - Kết quả `None` thì in `2020-02-26`, ngày đầu của nguồn SSI.
- Dòng cảnh báo nến ngày / nến 5 phút giữ dạng cũ `khoang hong vuot {max_days} ngay, can chay tay --from <ngay>`. `<ngay>` giờ là ngày bắt đầu thật.

### 1.3 `scripts/heartbeat_check.py`

- `KHONG_CANH["catchup"]`: sửa lý do thành chạy khi khởi động máy và 06:40 các ngày giao dịch. Tuổi phụ thuộc ngày nghỉ, cuối tuần và lần reboot, nên không canh tuổi; kết quả canh bằng mã thoát.
- **Không** thêm nhánh mới. `catchup-dryrun` không phải nhánh `sched.sh`, nên không vào `SCHEDULE_EXIT_POLICIES` hay `KHONG_CANH`.
- Nếu một test đòi mọi label xuất hiện trong `sched.sh` phải có policy: **dừng lại và báo**.

### 1.4 `DEPLOYMENT.md`

- Khối cron §9: thêm `40 6 * * 1-5 cd /opt/trading && scripts/sched.sh catchup`, ghi chú `(đợt 200)` cạnh dòng `@reboot`.
  - Sửa "Cài đặt 19 cron job" thành **20**: số dòng cron tăng, số nhánh không đổi.
- Bảng Windows: dòng `trading-catchup` sửa cột giờ thành `khi đăng nhập Windows + 06:40 T2–T6`.
  - **Không** đổi "Mười chín task": vẫn một task, chỉ thêm trigger.
- §9.5 (khối ghi chú tham khảo có `# @reboot ...`): thêm dòng tương ứng.
- §9.6, dòng `catchup`: thay "Xem trước bằng `scripts/sched.sh catchup --dry-run`" bằng câu nêu rằng dry-run ghi vào `catchup-dryrun.log` nên an toàn với heartbeat.
- §5: giữ câu đợt 199, thêm "lượt 06:40 sáng hôm sau cũng tự nạp".

### Không được đụng

- `scripts/backfill_universe.py`, `scripts/backfill_foreign_flow.py`, `scripts/run_if_docker_up.sh`.
- Collector, engine, `docker-compose.yml`, `run_hidden.vbs`.
- Mọi logic khác của `startup_catchup.py`: đường nạp, bất biến 21:30, bước kiểm, chờ DB.
- Thấy vấn đề ngoài phạm vi thì **báo**, không sửa.

## 2. Bắt buộc giữ (audit sẽ đếm)

- `tests/test_startup_catchup.py`: đủ **34** `def test_` hiện có, không xóa, không nới assert. Trong đó có 5 test Claude thêm khi audit đợt 199:
  - `test_main_foreign_flow_non_zero_exit_alone_fails`
  - `test_main_short_day_only_in_foreign_flow_returns_1`
  - `test_main_week_long_outage_flagged_against_30_day_baseline`
  - `test_main_clamped_5m_only_returns_1`
  - dòng assert `[ke hoach]` trong `test_main_dry_run_skips_all_loads_runs_checks`
- `test_main_clamped_plan_prints_warning_and_returns_1`: được phép **thêm** assert về ngày thật, không được bỏ assert cũ.
- `tests/test_run_if_docker_up.py`: 7 test, giữ nguyên.
- `tests/test_sched_args.py::test_catchup_branch_flags`: giữ assert `DOCKER_GATE_WAIT_SECONDS="${DOCKER_GATE_WAIT_SECONDS:-900}"`.
- `tests/test_heartbeat_prev_day_5m.py`: 15 test. `tests/test_backfill_universe.py`: 14 test.

## 3. TDD: viết test đỏ trước, rồi sửa cho xanh

### 3.1 `sched.sh` (L2)

Thêm vào `tests/test_sched_args.py`:
- (A) Nhánh `catchup` có chuỗi `catchup-dryrun.log` và `catchup-dryrun`.
- (B) Test chạy thật nhánh bằng bash với `RUN` giả. Theo đúng cách các test sẵn có giả `run_if_docker_up.sh` (tìm trong `tests/test_sched_args.py` / `tests/test_run_if_docker_up.py`; không có cách sẵn thì dùng thư mục tạm chứa bản sao `sched.sh` và một `run_if_docker_up.sh` giả in `$1 $2` ra file).
  - `catchup --dry-run` → giả nhận `catchup-dryrun.log catchup-dryrun`.
  - `catchup` (không cờ) → `catchup.log catchup`.
  - `catchup --max-days 30` → `catchup.log catchup`, vì chỉ đúng `--dry-run` mới đổi log.
  - **Không** được gọi `scripts/sched.sh` thật trong repo theo cách ghi vào `logs/` thật.
  - Nếu không dựng được (B) mà không chạm `logs/` thật: bỏ (B), ghi rõ lý do trong báo cáo, và chỉ giữ (A).

### 3.2 `gap_origin` và cảnh báo (L3)

Thêm vào `tests/test_startup_catchup.py`:
- (C) `gap_origin`:
  - ba mã `ok` với 01/06, 10/07, 26/10 → 01/06;
  - có mã `error` → mã đó tính `end − 7`, không kéo xuống dưới.
- (D) Đối chiếu: với cùng `progress`, khi `plan_universe_start` **không** bị cắt thì `gap_origin(...) == start`. Chạy trên vài bộ dữ liệu.
- (E) `main`, nến ngày cắt 120 ngày (`attempted_until = end − 120`): stdout có `can chay tay --from <end−120>`, **không** có `--from <end−90>`.
- (F) `main`, nến 5 phút cắt: tương tự (E).
- (G) `main`, khối ngoại không có dữ liệu trong 90 ngày, ngày cuối có dữ liệu là 01/05/2026: stdout có `khoi ngoai khong co du lieu trong 90 ngay, can chay tay --from 2026-05-01`, return 1.
- (H) Như (G), nhưng không có dữ liệu nào: `--from 2020-02-26`.
- Nếu thêm method `Storage` mới: thêm một test integration trong `tests/test_storage.py`, chạy trên DB `trading_test` như các test sẵn có.
  - Dữ liệu có hai ngày, kết quả là ngày lớn hơn.
  - Bảng rỗng của các mã test thì ra `None`. Nếu bảng chung có dữ liệu khác, dùng mã test riêng và ghi rõ cách cô lập.

### 3.3 Tài liệu

- `tests/test_deployment_doc.py` phải xanh.
- Thêm một assert, vào `test_deployment_doc.py` hoặc `test_sched_args.py`, tùy chỗ hợp với cách viết sẵn: khối cron có **cả** `@reboot ... sched.sh catchup` **và** `40 6 * * 1-5 ... sched.sh catchup`.

### 3.4 Phép phá: agent tự chạy rồi khôi phục

Mỗi phép phải làm đỏ ít nhất một test. Ghi vào bảng tên test đỏ.

| # | Phép phá |
|---|---|
| (a) | `sched.sh`: luôn dùng `catchup.log` kể cả có `--dry-run` |
| (b) | `sched.sh`: đổi log khi gặp **bất kỳ** đối số nào |
| (c) | `gap_origin` dùng `max` thay `min` |
| (d) | Cảnh báo nến ngày in lại `start_1d` (mốc cắt) |
| (e) | Cảnh báo nến 5 phút in lại `start_5m` |
| (f) | Khối ngoại in `end − max_days` thay ngày cuối có dữ liệu |
| (g) | Khối ngoại không có dữ liệu thì in ngày khác `2020-02-26` |
| (h) | Bỏ dòng `40 6 * * 1-5` trong DEPLOYMENT.md |
| (i) | `gap_origin` bỏ nhánh mã không `ok` (bỏ qua mã đó) |

Khôi phục sau mỗi phép. `git diff` cuối cùng chỉ còn thay đổi thật.

## 4. Cấm

- Không commit, không push.
- Không chạy `scripts/sched.sh` thật, kể cả `--dry-run`. Không chạy `startup_catchup` thật ngoài test.
- Không gọi SSI. Không đọc hoặc ghi DB thật; chỉ dùng `trading_test` qua fixture.
- Không đụng Task Scheduler hay crontab. Không đọc `.env`.
- Không thêm cờ phá thử vào code sản phẩm.

## 5. Báo cáo cho Claude

1. Nguyên văn GitNexus `impact` (trước khi sửa) và `detect-changes --scope all` (sau khi sửa).
2. Diff tóm tắt theo file, mỗi thay đổi truy về mục §1.x.
3. Danh sách `def test_` mới, **chép từ file**; số passed trước và sau của `uv run pytest -m "not integration" -q`, cộng các test integration mới.
4. Bảng phép phá (a)–(i), kèm tên test đỏ.
5. Chỗ mơ hồ đã gặp và cách xử lý; mọi chỗ "dừng lại và báo".
6. Cam kết đã tuân thủ §4.

## 6. Claude làm sau báo cáo

- Audit:
  - đếm danh sách test bắt buộc giữ;
  - tự chạy phép phá riêng;
  - `detect-changes`;
  - đọc diff `sched.sh` bằng mắt;
  - kiểm `git status` của `logs/`: không có `catchup-dryrun.log` mới do agent tạo.
- Commit, push.
- Trên máy thật:
  - chạy `scripts/sched.sh catchup --dry-run` một lần, kiểm nó ghi vào `logs/catchup-dryrun.log` và `logs/catchup.log` không đổi;
  - thêm trigger Weekly T2–T6 06:40 vào task `trading-catchup` có sẵn, giữ trigger AtLogOn;
  - sáng hôm sau đọc `logs/catchup.log`: phải có lượt 06:40 với EXIT=0.
- Cập nhật memory `docker-sap-lam-mat-ngay-nen` (lỗ L1 đã đóng) và `pha-thu-qua-sched-sh-ghi-log-that` (catchup dry-run đã tách log).
