# Brief đợt 199 — Tự kiểm và nạp bù dữ liệu mỗi lần khởi động máy

Ngày: 27/10/2026. Người lập: Claude (planner). Agent thực thi: viết code + test, **không commit, không push**.

## 0. Bối cảnh và quyết định (đã đo, đọc DB chỉ-đọc 27/10)

**Yêu cầu chủ dự án:** "mỗi lần khởi động hệ thống tự check dữ liệu và nạp dữ liệu bổ sung; sau này triển khai trên Docker, VPS Ubuntu".

**Hiện trạng:**
- Ba job nạp đêm chạy trên host qua `scripts/sched.sh` → `scripts/run_if_docker_up.sh`:
  - `backfill` 20:30 (nến ngày);
  - `foreign-flow` 20:45 (khối ngoại);
  - `backfill-5m` 21:15 (nến 5 phút, đợt 198).
- Cả ba dùng cửa sổ trượt `BACKFILL_DAYS=7`. Chú thích trong `sched.sh` ghi rõ giới hạn: **máy tắt quá 7 ngày thì phần hỏng ở giữa KHÔNG tự vá**.
- Lỡ giờ chạy (máy tắt, Docker chết lúc 20:30) thì job ghi SKIP và **không chạy bù** (memory `docker-sap-lam-mat-ngay-nen`). Phải chờ tối hôm sau.
- Collector khi khởi động đã tự nạp bù 5 phút cho 3 mã stream (`run_backfill`, chỉ ghi `ts > last_bar_ts`). Phần đó **không đụng**.
- Bảng `backfill_progress`:
  - 1d có 1.593 dòng `ok`; 174 mã active đều có `attempted_until = 2026-10-27`.
  - 5m có 310 dòng; các mã active đều có `attempted_until = 2026-10-27`; 139 mã không active có `attempted_until` null (nạp tay 25/10).
- `foreign_flow_daily`: ngày cuối là 23/10. Task Windows `trading-foreign-flow` chưa đăng ký, nên 26/10 và 27/10 còn thiếu.

**Bẫy quan trọng nhất — đọc kỹ trước khi code.** `backfill_one` (`scripts/backfill_universe.py:84-101`) bỏ qua một mã khi `attempted_until >= to`, và **không nhìn `from`**. Hệ quả:
- Nếu bước nạp bù chạy lúc 10:00 sáng với `--to` = hôm nay thì mọi mã được ghi `attempted_until = hôm nay`.
- Tối đó, job 20:30 thấy `attempted_until >= to` và **bỏ qua toàn bộ**.
- Kết quả: nến ngày của hôm nay hoặc thiếu, hoặc là nến dở dang giữa phiên, **vĩnh viễn**, và không ai biết.

Vì vậy **ngày cuối của bước nạp bù không bao giờ được là ngày giao dịch hôm nay trước 21:30** (21:30 là sau job đêm cuối cùng lúc 21:15). Đây là bất biến số 1 của đợt này.

**Các cách hiểu đã cân nhắc:**
- **(A) Nạp bù bên trong container collector lúc khởi động.** Loại, vì:
  - collector khởi động lại rất thường xuyên (deploy, crash, `docker compose up`);
  - nó sẽ chặn stream trong lúc nạp;
  - chạy giữa phiên thì dính đúng bẫy trên.
- **(B) Một container one-shot trong compose.** Loại. Với `restart: "no"` nó không tự chạy lại khi reboot. Với `unless-stopped` thì nó chạy lặp vô hạn.
- **(C) CHỌN: thêm nhánh `catchup` trong `sched.sh`, gọi bằng `@reboot` của cron trên Ubuntu** (và task "khi đăng nhập" trên Windows lúc còn dùng laptop). Lý do:
  - Cùng một bảng job với mọi job khác (bài học `4ea4c8d`: một công thức, một nơi).
  - Heartbeat đã canh mã thoát qua `SCHEDULE_EXIT_POLICIES`. Bước nạp bù hỏng sẽ có tin CRITICAL **một lần**, không cần viết đường Telegram mới.
  - Docker trên VPS tự bật lại các service (`restart: unless-stopped`, DEPLOYMENT.md §5). Cron `@reboot` có thể chạy trước khi postgres lên, nên cổng Docker cần **chờ** thay vì SKIP ngay (xem §1.3).

**Giới hạn ghi rõ (không làm trong đợt này):** Docker daemon tự khởi động lại mà host không reboot (ví dụ `apt upgrade docker`) thì `@reboot` không chạy. Trường hợp đó vẫn có hai lớp đỡ: cửa sổ 7 ngày của job đêm và ba cảnh báo ngày-liền-trước của heartbeat (nến ngày, khối ngoại, 5 phút). Người vận hành có thể chạy tay `scripts/sched.sh catchup`.

## 1. Việc cần làm

### 1.1 `scripts/startup_catchup.py` (file MỚI)

Chạy bằng `python -m scripts.startup_catchup` (vì file import `scripts.backfill_universe`; xem chú thích `python -m` trong `run_if_docker_up.sh`).

**Hợp đồng `test_sched_args`:**
- Có `build_parser()`.
- Có `main(argv: list[str] | None = None) -> int`, với câu đầu tiên là `args = build_parser().parse_args(argv)`.

**Cờ:**
- `--config` (mặc định `config/config.yaml`).
- `--dry-run`: in kế hoạch và chạy bước kiểm, **không gọi** hàm nạp nào.
- `--max-days` (int, mặc định 90). SSI chỉ giữ khoảng 4 tháng nến 5 phút.

**Hàm thuần (đặt tên đúng như dưới để test gọi):**

1. `catchup_end(now: datetime, holidays) -> date`
   - Nếu `is_trading_day(now.date(), holidays)` và `now.time() >= time(21, 30)` thì trả `now.date()`.
   - Ngược lại trả `previous_trading_day(now.date(), holidays)`.
   - Dùng `trading.calendar_vn`. `now` là datetime có tz VN.

2. `plan_universe_start(progress: dict[str, dict | None], end: date, max_days: int, default_days: int = 7) -> tuple[date | None, bool]`
   - `progress` là map mã → kết quả `storage.get_backfill_progress(mã, timeframe)`.
   - Với mỗi mã, tính mốc:
     - `attempted_until` nếu `status == "ok"` và `attempted_until` khác None;
     - ngược lại `end - timedelta(days=default_days)`.
   - `start = min(các mốc)`.
   - Nếu `start >= end` (mọi mã đã hỏi tới `end`) thì trả `(None, False)`, nghĩa là không cần nạp.
   - Nếu `(end - start).days > max_days` thì trả `(end - timedelta(days=max_days), True)`. True nghĩa là "bị cắt".
   - Ngược lại trả `(start, False)`.
   - Lấy lại đúng ngày `attempted_until` (chồng một ngày) là cố ý. UPSERT nên vô hại.
   - `progress` rỗng thì trả `(end - timedelta(days=default_days), False)`.

3. `plan_foreign_flow_start(day_counts: dict[date, int], end: date, max_days: int) -> tuple[date | None, bool]`
   - `day_counts` là kết quả `storage.read_foreign_flow_day_counts(end - timedelta(days=max_days), end)`.
   - `last` = ngày lớn nhất có count > 0.
   - Không có `last` thì trả `(end - timedelta(days=max_days), True)`.
   - `last >= end` thì trả `(None, False)`.
   - Ngược lại trả `(last + timedelta(days=1), False)`.

4. `find_short_days(counts: dict[date, int], check_days: list[date], baseline_days: list[date], ratio: float = 0.8) -> list[date]`
   - `base = statistics.median([counts[d] for d in baseline_days if counts.get(d, 0) > 0])`.
   - Nếu danh sách đó rỗng thì mọi ngày trong `check_days` đều thiếu.
   - Trả các ngày `d` trong `check_days` có `counts.get(d, 0) < ratio * base`, theo thứ tự tăng dần.
   - Phép so là `<`, không phải `<=`.

**`main` — thứ tự:**

1. Đọc cấu hình: `cfg = load_config(args.config)`, `storage = Storage(cfg.db_dsn)`.

2. **Chờ DB sẵn sàng.** Thử `storage.read_active_universe()` tối đa 30 lần, mỗi lần cách 10 giây. Vẫn hỏng thì in `[catchup] DB chua san sang sau 300s` và `return 1`.
   - Lý do: container postgres "running" chưa có nghĩa là đã nhận kết nối ngay sau reboot.
   - Đưa hàm ngủ thành tham số (ví dụ `sleep=time.sleep`) để test không phải chờ thật.

3. `end = catchup_end(datetime.now(TZ), cfg.holidays)`. In `[catchup] ngay cuoi = {end}`.

4. **Nến ngày:**
   - Lấy danh sách mã: `symbols, *_ = resolve_use_universe_symbols(storage, cfg)` (import từ `scripts.backfill_universe`).
   - Tính `progress` bằng `get_backfill_progress(s, "1d")` cho từng mã.
   - Gọi `plan_universe_start`.
   - Nếu có `start` và không `--dry-run`, gọi:
     `backfill_universe.main(["--timeframe", "1d", "--from", start.isoformat(), "--to", end.isoformat(), "--use-universe", "--sleep-ms", "200"])`.

5. **Nến 5 phút:**
   - Danh sách mã như bước 4 nhưng **bỏ các mã trong `cfg.symbols`**, vì `progress` phải tính trên đúng tập mà `--skip-config-symbols` sẽ nạp.
   - Gọi `backfill_universe.main([... "--timeframe", "5m", ..., "--use-universe", "--skip-config-symbols", "--sleep-ms", "200"])`.

6. **Khối ngoại:** dùng `plan_foreign_flow_start`. Nếu có `start` và không `--dry-run`, gọi:
   `backfill_foreign_flow.main(["--from", start.isoformat(), "--to", end.isoformat()])`.
   Mã trả về khác 0 thì tính là lỗi.

7. **Cô lập lỗi:** mỗi bước 4–6 bọc `try/except Exception` riêng. Bước hỏng in `[catchup] LOI <buoc>: <TypeName>: <msg>` (cắt 300 ký tự) rồi **đi tiếp bước sau**.

8. **Bước kiểm:**
   - `check_from = min(các start đã lập kế hoạch khác None, end - timedelta(days=14))`.
   - `check_days` = các ngày giao dịch trong `[check_from, end]`. Dùng `is_trading_day` với `cfg.holidays`.
   - `baseline_days` = các ngày giao dịch trong `[end - timedelta(days=30), end]`.
   - Với từng nguồn, đọc counts trên `[min(check_from, end - 30 ngày), end]` rồi gọi `find_short_days`:
     - nến ngày: `storage.read_daily_active_symbol_day_counts` (hàm MỚI, §1.2);
     - nến 5 phút: `storage.read_5m_active_symbol_day_counts` (có sẵn từ đợt 198);
     - khối ngoại: `storage.read_foreign_flow_day_counts` (có sẵn).
   - In mỗi nguồn một dòng: `[kiem] 1d: N ngay, thieu: [...]` (danh sách rỗng nếu đủ).

9. **Mã thoát:**
   - `1` nếu có bất kỳ điều nào sau:
     - một bước lỗi;
     - một nguồn có ngày thiếu;
     - một kế hoạch bị cắt. Khi bị cắt, in `[catchup] CANH BAO: khoang hong vuot {max_days} ngay, can chay tay --from <ngay>`.
   - `0` nếu không có điều nào ở trên.
   - Mã 1 sẽ thành tin CRITICAL **một lần** qua `SCHEDULE_EXIT_POLICIES` (heartbeat báo khi chuyển trạng thái).

`print` dùng tiếng Việt không dấu, giống `backfill_universe.py`, và đặt `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` như file đó.

### 1.2 `trading/storage/db.py` — thêm MỘT method

`read_daily_active_symbol_day_counts(self, frm: date, to: date) -> dict[date, int]`. Làm y hệt `read_5m_active_symbol_day_counts` (dòng 1334), chỉ khác hai chỗ:
- đọc bảng `bars_daily` thay vì `bars`;
- cùng `JOIN symbol_universe ... is_active = true`, cùng ngày theo giờ VN, cùng khoảng ts có tz.

**Không dùng `read_daily_symbol_counts`**, vì hàm đó quét cả bảng và không lọc active.

Không sửa method nào khác trong `db.py`.

### 1.3 `scripts/run_if_docker_up.sh` — cổng Docker biết CHỜ

Ngay trước khối `if ! docker ps -q ...` ở bước 4, thêm vòng chờ **chỉ chạy khi `DOCKER_GATE_WAIT_SECONDS` > 0**:

```bash
WAIT="${DOCKER_GATE_WAIT_SECONDS:-0}"
POLL="${DOCKER_GATE_POLL_SECONDS:-5}"
waited=0
while [ "$waited" -lt "$WAIT" ] && ! docker ps -q \
    --filter name="$GATE_CONTAINER" \
    --filter status=running 2>/dev/null | grep -q .; do
  sleep "$POLL"
  waited=$((waited + POLL))
done
```

Yêu cầu:
- Giữ nguyên khối kiểm cũ ngay sau vòng chờ. Hết giờ chờ mà vẫn chưa chạy thì đi đúng nhánh SKIP + `docker_down_alert` như hiện nay.
- Mặc định `WAIT=0`, nên **mọi job khác không đổi hành vi**.
- Không đổi quy tắc tên container. Hai bản của quy tắc đó đã được ghi chú là ngoại lệ có chủ ý; không thêm bản thứ ba.

### 1.4 `scripts/sched.sh` — nhánh `catchup`

```bash
  catchup)
    shift || true
    export DOCKER_GATE_WAIT_SECONDS="${DOCKER_GATE_WAIT_SECONDS:-900}"
    exec "$RUN" catchup.log catchup \
      uv run python -m scripts.startup_catchup "$@"
    ;;
```

Thêm `scripts/sched.sh catchup` vào khối chú thích đầu file và vào dòng `dung:` của nhánh `*)`.

### 1.5 `scripts/heartbeat_check.py` — chỉ hai bảng

- `SCHEDULE_EXIT_POLICIES["catchup"]`:
  - `log_file="catchup.log"`, `label="catchup"`, `normal_exit_codes=frozenset({0})`;
  - `reason` nêu: mã 1 = có bước lỗi, ngày thiếu, hoặc khoảng hỏng vượt `--max-days`.
- `KHONG_CANH["catchup"]`, lý do: chỉ chạy khi khởi động máy, không có nhịp cố định nên không canh tuổi được; kết quả được canh bằng mã thoát.
- Sửa số trong chú thích: "13 nhánh" thành "14 nhánh"; "cả 18 nhánh" thành "cả 19 nhánh (… cập nhật đợt 199)".
- **Không** thêm hàm kiểm mới. Không sửa `main`.

### 1.6 `DEPLOYMENT.md`

- Khối cron §9: thêm
  ```
  # 9c. Tự kiểm + nạp bù khi khởi động máy (đợt 199). Chờ postgres tối đa 15 phút.
  @reboot cd /opt/trading && scripts/sched.sh catchup
  ```
  Dòng tham khảo ở §9.5 cũng thêm `# @reboot cd /opt/trading && scripts/sched.sh catchup`.
- Bảng task Windows: thêm hàng `` `trading-catchup` | khi đăng nhập Windows | cùng vbs, tham số `catchup` ``. Đổi "Mười tám" thành "Mười chín" (hai chỗ).
- Đổi "Cài đặt 18 cron job" thành "19".
- Bảng chạy bù §9.6: thêm hàng `catchup`:
  - chạy bù được: **Có**;
  - lệnh: `scripts/sched.sh catchup` (xem trước bằng `scripts/sched.sh catchup --dry-run`);
  - lưu ý: không bao giờ nạp ngày hôm nay trước 21:30; khoảng hỏng trên 90 ngày thì in lệnh chạy tay và thoát 1.
- §5 (Start the stack): thêm một câu. Sau khi stack dừng lâu (bảo trì, chuyển máy) mà host không reboot, chạy `scripts/sched.sh catchup` một lần.

### Không được đụng

- `scripts/backfill_universe.py`, `scripts/backfill_foreign_flow.py`: **không sửa một dòng**, chỉ import và gọi `main(argv)` / `resolve_use_universe_symbols`.
- `trading/collector/*`, `trading/engine/*`, `docker-compose.yml`, `scripts/run_hidden.vbs`.
- Logic skip `attempted_until` trong `backfill_one`.
- Gặp dead code hoặc vấn đề ngoài phạm vi thì **báo lại**, không tự sửa.

## 2. Phải giữ (đọc danh sách `def test_` trước và sau; số phải không giảm)

- `tests/test_backfill_universe.py`: cả 14 test, gồm 4 test `is_dirty_bar` của đợt 196 và 2 test `--skip-config-symbols` của đợt 198.
- `tests/test_heartbeat_prev_day_5m.py`: cả 15 test, gồm 4 test audit đợt 198 (`exactly_80_pct_silent`, `p_missing_counts_as_zero`, `baseline_excludes_p`, `uses_5_most_recent_days`).
- `tests/test_storage.py::test_read_5m_active_symbol_day_counts`, bản có mã `TEST_5M_D` (audit 198).
- `tests/test_run_if_docker_up.py`: mọi test hiện có phải pass **không sửa**. Đó là bằng chứng WAIT=0 không đổi hành vi.

## 3. TDD — bước và cách kiểm

1. **GitNexus trước khi sửa** (dùng `node .gitnexus/run.cjs`, không npx).
   - `impact` cho `Storage`, `SCHEDULE_EXIT_POLICIES`, `KHONG_CANH`.
   - Với `run_if_docker_up.sh`, grep người gọi.
   - Kiểm chứng bằng: dán nguyên văn kết quả vào báo cáo.

2. **Test hàm thuần** — file mới `tests/test_startup_catchup.py`. Viết test đỏ trước rồi mới code.
   - `catchup_end`:
     - (a) thứ Ba 27/10 21:29 → thứ Hai 26/10;
     - (b) thứ Ba 21:30 → thứ Ba 27/10;
     - (c) thứ Bảy 31/10 23:00 → thứ Sáu 30/10;
     - (d) thứ Hai 26/10 08:00 → thứ Sáu 23/10;
     - (e) holidays = {thứ Hai 02/11}, now = thứ Ba 03/11 10:00 → thứ Sáu 30/10.
   - `plan_universe_start`:
     - (f) mọi mã `attempted_until` = end → `(None, False)`;
     - (g) ba mã với ngày 20/10, 22/10, 26/10, end 27/10 → `(20/10, False)`;
     - (h) một mã có status `error`, một mã có progress None → mốc là `end - 7 ngày`;
     - (i) một mã có `attempted_until` cách end 120 ngày, max 90 → `(end - 90, True)`;
     - (j) đúng 90 ngày → không bị cắt;
     - (k) progress rỗng → `(end - 7, False)`.
   - `plan_foreign_flow_start`:
     - (l) last = 23/10, end = 27/10 → `(24/10, False)`;
     - (m) last = end → `(None, False)`;
     - (n) dict rỗng → `(end - 90, True)`;
     - (o) có ngày count 0 sau last → bị bỏ qua.
   - `find_short_days`:
     - (p) base 172, một ngày 137 → thiếu; 138 → đủ;
     - (q) đúng 80% (8/10) → đủ;
     - (r) ngày không có trong counts → thiếu;
     - (s) baseline toàn 0 → mọi ngày thiếu;
     - (t) trung vị chứ không phải min hay trung bình. Baseline [172, 172, 172, 3, 3] và ngày kiểm 150 → đủ.
   - Kiểm chứng bằng: test đỏ trước khi code, xanh sau.

3. **Test `main` với giả lập.**
   - Monkeypatch:
     - `load_config`, `Storage` (fake);
     - `backfill_universe.main` và `backfill_foreign_flow.main` (ghi lại argv);
     - đồng hồ `now`;
     - hàm ngủ.
   - **Không gọi SSI, không DB thật.**
   - Các ca:
     - (i) có khoảng trống cả ba nguồn: argv 1d chứa đúng `--timeframe 1d --from <start> --to <end> --use-universe`; argv 5m có thêm `--skip-config-symbols`; argv khối ngoại đúng `--from/--to`;
     - (ii) **bất biến số 1:** now = thứ Ba 27/10 10:00 thì **mọi** argv có `--to 2026-10-26`, không bao giờ là `2026-10-27`;
     - (iii) 5m: `progress` chỉ hỏi các mã không thuộc `cfg.symbols`. Cho mã stream `HPG` có `attempted_until` cũ 60 ngày thì `--from` 5m **không** bị kéo về 60 ngày;
     - (iv) kế hoạch None → hàm nạp tương ứng không được gọi;
     - (v) bước 1d ném exception → bước 5m và khối ngoại vẫn được gọi, stdout có `[catchup] LOI`, return 1;
     - (vi) `backfill_foreign_flow.main` trả 2 → return 1;
     - (vii) `--dry-run` → không hàm nạp nào được gọi, bước kiểm vẫn chạy;
     - (viii) bước kiểm có ngày thiếu → return 1; đủ hết và không lỗi → return 0;
     - (ix) bị cắt → return 1 và stdout có `can chay tay --from`;
     - (x) `read_active_universe` hỏng 2 lần rồi được → chạy tiếp; hỏng 30 lần → return 1, hàm ngủ được gọi 29 hoặc 30 lần, **không ngủ thật**.

4. **Test DB tích hợp** — `tests/test_storage.py::test_read_daily_active_symbol_day_counts`, mẫu y hệt test 5m của đợt 198.
   - A, B active; C không active; D active với một nến 21/10 17:30 UTC và một nến 21/10 16:30 UTC.
   - Kỳ vọng `{22/10: 3, 23/10: 1}` với A có nến 22/10 17:30 UTC.
   - Dùng mã `TEST_1D_*`, xoá trước và sau.
   - Kiểm chứng bằng: test xanh trên DB `trading_test`.

5. **Test cổng chờ** — trong `tests/test_run_if_docker_up.py`, thêm test mới, dùng lại khung `bin_dir` docker giả sẵn có.
   - (W1) docker giả trả "không chạy" 2 lần rồi "chạy", với `DOCKER_GATE_WAIT_SECONDS=10`, `DOCKER_GATE_POLL_SECONDS=0`. Kỳ vọng log có `start` + `EXIT=0`, không có SKIP.
   - (W2) luôn "không chạy", với `WAIT=2`, `POLL=1` → SKIP như cũ.
   - (W3) không đặt WAIT, docker "không chạy" lần đầu → SKIP ngay, docker giả chỉ bị gọi một lần cho cổng.
   - Docker giả đếm lần gọi bằng file đếm trong `tmp_path`.

6. **Hợp đồng.**
   - `test_sched_args` và `test_schedule_watch`: sửa số nhánh 18 → 19.
   - `test_deployment_doc` phải xanh với dòng `@reboot`.
   - Thêm `test_catchup_branch_flags` trong `test_sched_args.py`: nhánh có `python -m scripts.startup_catchup`, `DOCKER_GATE_WAIT_SECONDS` và `"$@"`.

7. **Phép phá — agent tự làm, ghi bảng "phép phá → test đỏ".** Khôi phục file gốc sau mỗi phép.
   - (a) `catchup_end` luôn trả `now.date()`;
   - (b) `>= time(21, 30)` đổi thành `>= time(15, 0)`;
   - (c) `plan_universe_start` dùng `max` thay `min`;
   - (d) bỏ nhánh `status == "ok"`;
   - (e) `>` max_days đổi thành `>=`;
   - (f) `plan_foreign_flow_start` trả `last` thay `last + 1`;
   - (g) `find_short_days` dùng `<=`;
   - (h) dùng `min` thay median;
   - (i) 5m không bỏ `cfg.symbols` khỏi `progress`;
   - (j) bỏ `try/except` của bước 1d;
   - (k) `--dry-run` vẫn gọi nạp;
   - (l) bỏ vòng thử DB;
   - (m) vòng chờ trong `run_if_docker_up.sh` bỏ điều kiện `docker ps` (chờ đủ WAIT rồi mới kiểm);
   - (n) SQL mới dùng `ts::date`;
   - (o) SQL mới bỏ `is_active`;
   - (p) bỏ `SCHEDULE_EXIT_POLICIES["catchup"]`;
   - (q) bỏ dòng `@reboot` trong DEPLOYMENT.md.
   - Kiểm chứng bằng: mỗi phép có ít nhất một test đỏ, ghi tên test.

8. **Toàn bộ suite:**
   - `uv run pytest -m "not integration" -q`;
   - test integration mới;
   - `uv run ruff check scripts trading tests`.
   - Kiểm chứng bằng: dán số passed trước và sau.

9. `node .gitnexus/run.cjs detect-changes --scope all --repo .` → dán nguyên văn.

## 4. Cấm

- Không commit, không push.
- Không chạy `scripts/sched.sh` (kể cả `catchup --dry-run`), không chạy `startup_catchup` thật.
- Không gọi SSI, không ghi hay đọc DB thật (chỉ DB test qua pytest).
- Không đăng ký hay sửa Task Scheduler, không sửa crontab.
- Không đọc `.env`.
- Không thêm cờ phá thử vào code sản phẩm. `DOCKER_GATE_POLL_SECONDS` là cấu hình chu kỳ, được phép.

## 5. Báo cáo

1. GitNexus trước và sau (nguyên văn).
2. Diff tóm tắt theo file, mỗi dòng truy về một mục §1.
3. Danh sách `def test_` mới **chép từ file** (không gõ lại), số passed trước và sau, bảng phép phá (a)–(q).
4. Chỗ mơ hồ đã gặp và cách xử lý.
5. Cam kết §4.

## 6. Claude làm sau báo cáo

1. **Audit:**
   - đối chiếu diff với §1;
   - tự đếm test;
   - tự chạy bộ phép phá riêng (khác danh sách §3.7);
   - detect-changes.
2. Commit + push (hook pre-push chạy full suite).
3. **Chạy `--dry-run` một lần trên máy thật** (chỉ đọc DB): `uv run python -m scripts.startup_catchup --dry-run` qua `run_if_docker_up.sh`. Kỳ vọng:
   - 1d và 5m: "không cần nạp";
   - khối ngoại: kế hoạch từ 24/10.
4. Chạy thật một lần ngoài giờ giao dịch:
   - lấp khối ngoại 26–27/10;
   - xác nhận EXIT=0;
   - đọc DB thấy `foreign_flow_daily` có 26/10.
5. Đăng ký task Windows `trading-catchup` với trigger khi đăng nhập (`-AtLogOn`), `ExecutionTimeLimit` 2 giờ, `DontStopIfGoingOnBatteries`.
6. Cập nhật memory `docker-sap-lam-mat-ngay-nen` và `trien-khai-that-la-vps-24-7`.
