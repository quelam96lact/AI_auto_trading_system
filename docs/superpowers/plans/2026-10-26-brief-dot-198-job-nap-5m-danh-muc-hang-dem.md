# Brief đợt 198: job nạp nến 5 phút cho cả danh mục mỗi tối + heartbeat kiểm kết quả

- **Người lập:** Claude (planner), 26/10/2026.
- **Agent thực thi:** viết code và test, **không commit, không push**.
- **Loại việc:** hạ tầng dữ liệu, không tốn ngân sách giả thuyết.
- **Mục tiêu:**
  - bảng `bars` (5 phút) có đủ các mã thanh khoản sau mỗi ngày giao dịch, không chỉ 3 mã collector đang stream;
  - job không chạy thì sáng hôm sau phải có tin, không im lặng.

## 0. Sự thật đã đo (Claude, 25–26/10, chỉ đọc)

1. **Collector chỉ stream `cfg.symbols` = `[HPG, IJC, AAA]`:**
   - `trading/collector/feed.py:14` dựng kênh `B:HPG-IJC-AAA`;
   - HII có bar cuối 10/09, tức không còn được stream;
   - các mã khác chỉ có 5 phút nhờ nạp tay: 03/04 → 07/08, và 10/08 → 23/10 (nạp ngày 25/10, 296 mã ngày 23/10);
   - từ 24/10 trở đi, chỉ 3 mã có nến 5 phút.
2. **`symbol_universe`:** 174 mã `is_active`, trên 1.595 mã. Trong 300 mã có nến 5 phút 10–23/10, 172 mã đang active; 2 mã active không có nến 5 phút.
3. **`scripts/backfill_universe.py --timeframe 5m`:**
   - đã lọc nến giá 0 từ đợt 196 (`255b2d8`);
   - UPSERT theo `(symbol, ts)`, chunk 7 ngày;
   - nhánh `--use-universe` trả về hợp của mã active và mã bắt buộc có giá (`cfg.symbols` + mã đang nắm giữ);
   - lần nạp ngày 25/10 (303 mã × 76 ngày) mất 675 giây; cửa sổ 7 ngày sẽ ngắn hơn nhiều.
4. **Collector cố ý không ghi đè nến stream:** `run_backfill` chỉ ghi `b.ts > last_bar_ts` (`trading/collector/backfill.py:352-357`). Job mới phải giữ nguyên tắc này cho 3 mã đang stream, vì engine đọc lại các nến đó. Cách làm là bỏ `cfg.symbols` khỏi danh sách của job.
5. **Job lịch chạy trên host** qua `scripts/sched.sh` → `scripts/run_if_docker_up.sh`, giống nhánh `backfill` (1d) lúc 20:30.
6. **Các test hợp đồng sẽ đỏ nếu thêm nhánh `sched.sh` mà làm thiếu** (đã gặp ở đợt 190b):
   - `tests/test_sched_args.py`: nhánh phải chuyển tiếp `"$@"`; script phải có `build_parser()` và `main(argv)` đúng khuôn. `backfill_universe.py` đã đạt khuôn này.
   - `tests/test_schedule_watch.py`: mỗi nhánh phải có trong `SCHEDULE_EXIT_POLICIES`, và có trong `SCHEDULE_WATCH_JOBS` hoặc `KHONG_CANH`.
   - `tests/test_deployment_doc.py`: dòng cron trong `DEPLOYMENT.md` phải khớp các nhánh của `sched.sh`.
7. **Đã có job tối bị `SKIP: docker chua chay`** (19, 20 và 23/10). Vì vậy phải kiểm **kết quả** sáng hôm sau, theo khuôn `prev_day_foreign_flow_alert` (đợt 190b).

### Vì sao không mở rộng stream của collector

"Collector ghi đủ danh mục" có hai cách hiểu. Claude chọn cách (B) vì những lý do sau:
- **(A) Thêm ~170 mã vào kênh stream:**
  - mọi nến sẽ được publish lên NATS `bars.ssi.*` và đổ vào engine đang giao dịch thật, kéo theo thay đổi hành vi engine;
  - phải deploy collector, chỉ được làm ngoài giờ;
  - rủi ro giới hạn kênh của SSI chưa đo.
- **(B) Job REST mỗi tối:** dùng lại script đã có và đã có test. Đường giao dịch thật không đổi. Kết quả cho nghiên cứu như nhau, vì nghiên cứu chỉ cần nến trong DB, không cần nến theo thời gian thực.

## 1. Thiết kế (đã chốt)

### 1.1 `scripts/backfill_universe.py`: thêm đúng một cờ

- Cờ `--skip-config-symbols` (`action="store_true"`, help không dấu): bỏ mọi mã trong `cfg.symbols` khỏi danh sách **sau khi** đã chọn danh sách (`--symbols`, `--use-universe` hoặc file).
- Đặt trong `main()`, ngay trước lời gọi `run(...)`:
  - tính `kept = [s for s in symbols if s not in set(cfg.symbols)]`;
  - in `[load] bo {n} ma collector dang stream: {danh sach}`;
  - truyền `kept` vào `run`.
- Không có cờ thì hành vi y nguyên. Job 1d hằng đêm không đổi.

### 1.2 Nhánh mới `backfill-5m` trong `scripts/sched.sh`

```bash
  backfill-5m)
    shift || true
    exec "$RUN" backfill-5m.log backfill-5m \
      uv run python scripts/backfill_universe.py \
      --timeframe 5m \
      --from "$(date -d "$BACKFILL_DAYS days ago" +%F)" \
      --to "$(date +%F)" \
      --use-universe --skip-config-symbols --sleep-ms 200 \
      "$@"
    ;;
```

- **Cửa sổ trượt 7 ngày** dùng chung `BACKFILL_DAYS`. Một tối bị lỡ, hay SSI chưa có đủ số của ngày hôm đó lúc job chạy, thì sẽ được nạp lại ở lần sau. UPSERT nên không sinh dòng thừa.
- **Lịch: 21:15 T2–T6**, sau `daily-check` 21:00, để không chồng lời gọi SSI với job 1d (20:30) và job khối ngoại (20:45). Lịch nằm trong `DEPLOYMENT.md` và Task Scheduler; Claude đăng ký task sau khi audit.
- Thêm nhánh vào danh sách ở đầu file và vào dòng `dung:` của `*)`.

### 1.3 `scripts/heartbeat_check.py`

- **`SCHEDULE_EXIT_POLICIES["backfill-5m"]`:**
  - `log_file="backfill-5m.log"`, `label="backfill-5m"`, `normal_exit_codes=frozenset({0})`;
  - `reason` theo khuôn mục `backfill`, nêu "script không gửi Telegram".
- **`KHONG_CANH["backfill-5m"]`:** lý do giống `backfill`, kèm câu "kết quả được kiểm GIÁN TIẾP (đợt 198)".
- **Sửa các chú thích đếm nhánh cho khớp số mới:** "12 nhánh" và "cả 17 nhánh". Chỉ sửa số, không sửa chữ khác.
- **Hàm mới** `prev_day_5m_alert(storage, now, holidays, alerted_for) -> tuple[str | None, str]`, chép khuôn `prev_day_foreign_flow_alert`:
  - `P = previous_trading_day(now.date(), holidays)`. Nếu `alerted_for` bằng P (dạng ISO hoặc `date`) thì trả `(None, P)`.
  - `counts = storage.read_5m_active_symbol_day_counts(P - 30 ngày, P)`, rồi `n_P = counts.get(P, 0)`.
  - `base` = **trung vị** của tối đa 5 ngày có dữ liệu gần nhất **trước** P. Không có ngày nào trước P thì trả `(None, P)`.
  - Nếu `n_P < 0.8 * base` thì gửi tin `[WARN] nến 5 phút ngày {P}: {n_P} mã thanh khoản (trung vị 5 phiên trước {base}) — Khắc phục: ./scripts/sched.sh backfill-5m (idempotent)`. Ngược lại trả `(None, P)`.
  - Mức WARN: đây là dữ liệu nghiên cứu, không chặn giao dịch.
- **Gọi trong `main`**, ngay sau khối khối ngoại (đợt 190b), cũng nằm trong `if in_check_window:`:
  - dùng file trạng thái riêng `logs/.prev_day_5m_state.json` qua `load_json_state`/`save_json_state`;
  - `--dry-run` thì không ghi trạng thái;
  - bọc `try/except` và in ra **stderr** `[WARN] heartbeat khong kiem duoc nen 5 phut: ...`, giống hệt khối khối ngoại.

### 1.4 `trading/storage/db.py`: thêm đúng một method

`read_5m_active_symbol_day_counts(frm: date, to: date) -> dict[date, int]`
- Đếm **số mã khác nhau** trong `bars` theo **ngày giờ Việt Nam**, chỉ tính mã có `symbol_universe.is_active = true`.
- **Ngày phải tính theo giờ VN, không phải UTC.** Memory `chay-bu-job-theo-ngay` ghi `ts::date` lệch một ngày vì `ts` lưu theo UTC. Dùng `(b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`.
- Lọc khoảng bằng `ts` để dùng index: `b.ts >= <00:00 VN của frm>` và `b.ts < <00:00 VN của to + 1 ngày>`, truyền vào datetime có múi giờ (`trading.calendar_vn.TZ`).
- Chỉ đếm mã active vì tập 5 phút cũ có ~300 mã, còn job chỉ nạp ~174 mã. Đếm mọi mã thì trung vị cũ (296) sẽ làm tin báo giả ngay tuần đầu.
- Ngày không có mã nào thì không có khoá trong dict.

### 1.5 `DEPLOYMENT.md`

- Thêm dòng cron `15 21 * * 1-5 cd /opt/trading && scripts/sched.sh backfill-5m` ở **cả hai** chỗ đang liệt kê cron, ngay sau dòng `daily-check`.
- Thêm hàng `trading-backfill-5m | 21:15 T2–T6 | cùng vbs, tham số backfill-5m` vào bảng Windows, sau hàng `trading-daily-data-check`.
- Sửa "Mười bảy"/"mười bảy" thành "Mười tám"/"mười tám" ở đoạn nói số task.
- Thêm hàng `backfill-5m` vào bảng §9.6 (job chạy bù được), theo đúng mẫu hàng `backfill`.

## 2. Phạm vi file

**Được sửa:**
- `scripts/backfill_universe.py`: chỉ cờ mới và vài dòng trong `main()`;
- `scripts/sched.sh`, `scripts/heartbeat_check.py`, `trading/storage/db.py` (một method), `DEPLOYMENT.md`;
- test: `tests/test_backfill_universe.py`, file mới `tests/test_heartbeat_prev_day_5m.py`, và `tests/test_storage.py` cho test integration của method mới.

**Không được đụng:**
- collector (`trading/collector/*`), engine, `config/config.yaml`, `schema.sql`;
- `run_if_docker_up.sh`, `run_hidden.vbs`;
- các nhánh `sched.sh` khác và `BACKFILL_DAYS`;
- các phép kiểm heartbeat khác;
- `backfill_one` và `run` trong `backfill_universe.py`.

**Phải giữ nguyên tên, nguyên assert, và vẫn xanh** (bài học đợt 183b):
- 12 test của `tests/test_backfill_universe.py`, gồm 4 test đợt 196:
  - `test_5m_drops_dirty_bars_before_write`
  - `test_5m_last_done_date_ignores_dirty_bars`
  - `test_5m_all_dirty_does_not_advance_last_done_date`
  - `test_1d_still_writes_zero_price_bars_unchanged`
- 11 test của `tests/test_heartbeat_foreign_flow.py`.
- Dòng lọc `is_dirty_bar` trong nhánh 5m của `backfill_one` (đợt 196) phải còn nguyên.

**Ràng buộc:**
- Không gọi API thật. Không ghi DB thật; test integration chỉ dùng `trading_test`.
- **Không chạy `scripts/sched.sh`** dưới bất kỳ hình thức nào, kể cả để thử cờ lạ (bài học đợt 156).
- Không đăng ký hay sửa task Windows. Không restart container. Không mở `.env`.
- Test heartbeat **không được ghi** vào `logs/` thật (bài học đợt 142): file trạng thái nằm trong `tmp_path`, `Storage` là đồ giả.

## 3. Các bước (TDD)

1. **Cờ `--skip-config-symbols`.** Test gọi `main([...])` của `backfill_universe` với monkeypatch:
   - `load_config` trả về cfg giả có `symbols=["HPG","IJC","AAA"]`;
   - `Storage` giả, có `init_schema` và hai hàm đọc cho `resolve_use_universe_symbols`;
   - `run` giả ghi lại danh sách mã nhận được, và không gọi SSI.

   Viết các test sau:
   - `test_skip_config_symbols_removes_stream_symbols`: universe `[AAA, FPT, HPG, VCB]` cùng cờ thì `run` nhận `[FPT, VCB]`, stdout chứa `bo 2 ma collector`.
   - `test_without_skip_flag_list_unchanged`: không có cờ thì `run` nhận đủ 4 mã.

   → kiểm chứng bằng: cả hai đỏ trước khi sửa, xanh sau khi sửa; 12 test cũ xanh.
2. **Nhánh `sched.sh`, hai mục heartbeat, `DEPLOYMENT.md`** → kiểm chứng bằng: `uv run pytest tests/test_sched_args.py tests/test_schedule_watch.py tests/test_deployment_doc.py tests/test_scripts_convention.py -q` xanh.
3. **`read_5m_active_symbol_day_counts`** (integration, `trading_test`). Dữ liệu mẫu:
   - mã active `A` có bar `2026-10-22 02:15 UTC` và `2026-10-22 07:45 UTC`;
   - mã active `B` có bar `2026-10-22 03:00 UTC`;
   - mã **không** active `C` có bar `2026-10-22 03:00 UTC`;
   - mã `A` có bar `2026-10-22 17:30 UTC`, tức 00:30 ngày 23/10 giờ VN.

   Kết quả mong đợi: `{2026-10-22: 2, 2026-10-23: 1}`. Đếm mã chứ không đếm bar; mã không active không được tính; ngày theo giờ VN.
4. **`prev_day_5m_alert`** với `Storage` giả và `now` là thứ Ba 27/10/2026 lúc 09:00, nên P = 26/10:
   - `n_P = 170`, 5 phiên trước đều 172: không báo.
   - `n_P = 3`, 5 phiên trước đều 172: báo; tin chứa `2026-10-26` và `sched.sh backfill-5m`.
   - Biên ngưỡng, 5 phiên trước đều 172, nên 0,8 × 172 = 137,6:
     - `n_P = 138`: không báo;
     - `n_P = 137`: báo.
   - Trung vị chứ không phải min: 5 phiên trước `[172, 172, 172, 172, 3]` và `n_P = 100` thì vẫn báo.
   - `alerted_for == "2026-10-26"`: không báo.
   - Không có ngày nào trước P: không báo.
   - `now` là thứ Hai 26/10 thì P = thứ Sáu 23/10.
5. **Nối vào `main`** theo khuôn `tests/test_heartbeat_foreign_flow.py`, ba test cuối:
   - (i) khối 5 phút ném exception thì phép kiểm khác vẫn chạy, và stderr có `[WARN] heartbeat khong kiem duoc nen 5 phut`;
   - (ii) `--dry-run` không tạo `.prev_day_5m_state.json`;
   - (iii) có tin báo thì file trạng thái ghi P.
6. **Phép phá.** Mỗi phép phải làm đỏ ít nhất một test **gọi code sản phẩm**. Phá xong khôi phục, ghi lệnh và kết quả vào báo cáo.
   - (a) Bỏ `"$@"` khỏi nhánh `backfill-5m`.
   - (b) Bỏ `--skip-config-symbols` khỏi nhánh `backfill-5m`. Cần một test đọc `sched.sh` và assert nhánh `backfill-5m` có đủ `--timeframe 5m`, `--use-universe` và `--skip-config-symbols`.
   - (c) Cờ được parse nhưng không áp dụng: truyền `symbols` thay vì `kept` vào `run`.
   - (d) Xoá `SCHEDULE_EXIT_POLICIES["backfill-5m"]`.
   - (e) Xoá `KHONG_CANH["backfill-5m"]`.
   - (f) Đổi trung vị thành `min`.
   - (g) Bỏ kiểm `alerted_for`.
   - (h) Bỏ `try/except` quanh khối 5 phút trong `main`.
   - (i) Xoá dòng cron `backfill-5m` trong `DEPLOYMENT.md`.
   - (j) Trong SQL, đổi ngày VN thành `b.ts::date`.
   - (k) Bỏ điều kiện `is_active` trong SQL.
   - (l) Đổi `count(DISTINCT b.symbol)` thành `count(*)`.

   (j), (k), (l) là test integration, cần `nats-test` và Postgres test đang chạy như `CLAUDE.md` mô tả. Nếu môi trường test không chạy được, ghi rõ trong báo cáo và **dừng**, không bỏ qua.

   Không có cờ phá thử trong code sản phẩm.
7. **Toàn suite** → kiểm chứng bằng:
   - `uv run pytest -m "not integration" -q`: không đỏ thêm; ghi số passed trước và sau;
   - `uv run pytest tests/test_storage.py -q -k 5m`, chạy integration;
   - `uv run ruff check trading tests scripts/backfill_universe.py scripts/heartbeat_check.py` sạch;
   - `uv run pyright scripts/backfill_universe.py scripts/heartbeat_check.py trading/storage/db.py`: ghi rõ lỗi nào có từ trước, kiểm bằng `git stash`.

## 4. GitNexus (bắt buộc)

- Dùng `gitnexus` hoặc `node .gitnexus/run.cjs`, **không npx**.
- **Trước khi sửa:**
  - `context` cho `prev_day_foreign_flow_alert` và `resolve_use_universe_symbols`;
  - `impact --direction upstream` cho `main` của `heartbeat_check.py` và `main` của `backfill_universe.py`.
  - Lưu ý: mọi script đều có hàm `main` nên index hay nối nhầm. Đợt 197 đã gặp CRITICAL 263 symbol là dương tính giả. Gặp HIGH/CRITICAL thì báo nguyên văn, kèm danh sách caller ở độ sâu 1, rồi grep xác nhận. Gặp UNKNOWN thì grep xác nhận.
- **Sau khi sửa:** `detect-changes --scope all`, dán nguyên văn phần tóm tắt.

## 5. Báo cáo agent phải nộp

1. Nguyên văn kết quả GitNexus trước và sau khi sửa.
2. Diff tóm tắt theo file. Mọi dòng phải truy ngược được về §1.
3. Danh sách `def test_` mới theo từng file; số passed trước và sau; bảng phép phá (a)–(l) kèm test bị đỏ.
4. Chỗ mơ hồ đã gặp. Nếu có lựa chọn ảnh hưởng tin cảnh báo hay dữ liệu mà brief chưa quy định, **dừng và hỏi**.
5. Cam kết: không gọi API thật, không ghi DB thật, không chạy `sched.sh`, không đụng Task Scheduler, không đọc `.env`, không commit/push.

## 6. Claude làm sau khi nhận báo cáo

1. **Audit:**
   - đối chiếu diff với §2;
   - tự đếm `def test_` (trước: 12 trong `test_backfill_universe.py`, 11 trong `test_heartbeat_foreign_flow.py`);
   - chạy lại toàn suite, integration, và (a)–(l);
   - xác nhận dòng lọc `is_dirty_bar` của đợt 196 còn nguyên.
2. **Commit, push.**
3. **Đăng ký `trading-backfill-5m`:**
   - chép cấu hình XML của `trading-backfill-universe`, chỉ đổi giờ (21:15) và tham số `backfill-5m`;
   - chạy một lần bằng `schtasks /run` **ngoài giờ giao dịch**. Lần đầu, cửa sổ 7 ngày đã phủ khoảng hở từ 24/10.
   - kiểm `logs/backfill-5m.log` có `EXIT=0`, `err=0` hoặc gần 0, và 3 mã stream không có trong danh sách;
   - kiểm bằng DB chỉ đọc: số mã active có nến 5 phút cho từng phiên từ 26/10 trở lại ~172, và nến của HPG/IJC/AAA không đổi (so `count` và `max(ts)` trước/sau).
4. **Sáng ngày giao dịch kế tiếp:** xác nhận heartbeat im lặng khi đủ mã.
5. **Cập nhật memory** `du-lieu-5m-rong-chi-den-07-08`: hết khoảng hở từ 24/10, ghi tên job.
