# Brief đợt 190b: job nạp khối ngoại hằng đêm + heartbeat kiểm kết quả

- Người lập: Claude (planner), 24/10/2026. Agent thực thi: viết code + test, **không commit, không push**.
- Tiếp nối brief 190 (commit `d795ea4`, sửa `d3ffd41`). Đây là việc **hạ tầng dữ liệu**, không tốn ngân sách giả thuyết. Phép khám phá vẫn là brief 191, mở từ 01/11.
- Mục tiêu: bảng `foreign_flow_daily` tự cập nhật mỗi tối ngày giao dịch. Nếu job không chạy thì sáng hôm sau phải có tin, không im lặng.

## 0. Sự thật đã đo (Claude, 23–24/10)

1. `scripts/backfill_foreign_flow.py` đã chạy thật ngày 22/10, trong container:
   - `rows=4829 kept=1557 bad_row=0 net_mismatch=0`;
   - VCB, HPG, E1VFVN30 khớp fixture từng trường;
   - `close_price` khớp `bars_daily` ở 173/173 mã;
   - 38 mã của `symbol_universe` không có dòng nào, và cả 38 đều có `is_active=f`.
2. Lần chạy thật đầu tiên chết vì `Config.from_yaml` không tồn tại. Test cũ luôn tiêm storage giả nên không đi qua nhánh đó. Claude đã sửa thành `load_config` và thêm test `test_backfill_foreign_flow_main_loads_real_config_path`.
3. Job lịch chạy **trên host** qua `scripts/sched.sh` → `scripts/run_if_docker_up.sh`:
   - wrapper nạp `.env` và đổi `localhost` thành `127.0.0.1`;
   - `.venv` trên host đã có `ssi_fc_data`.
   - `backfill_universe.py` cũng gọi SSI theo đúng cách này. Xem nhánh `backfill` trong `sched.sh` và `BACKFILL_DAYS=7`.
4. Các test hợp đồng sẽ đỏ nếu thêm nhánh `sched.sh` mà làm thiếu:
   - `tests/test_sched_args.py`:
     - `main` phải có **đúng một** tham số `argv`;
     - câu lệnh đầu tiên của `main` phải là `args = build_parser().parse_args(argv)`, không nằm trong if hay try;
     - script phải có `build_parser()`, từ chối cờ lạ, và nhánh phải chuyển tiếp `"$@"`.
   - `tests/test_schedule_watch.py`: mỗi nhánh phải có trong `SCHEDULE_EXIT_POLICIES`, và có trong `SCHEDULE_WATCH_JOBS` hoặc `KHONG_CANH` của `scripts/heartbeat_check.py`.
   - `tests/test_deployment_doc.py`: dòng cron trong `DEPLOYMENT.md` phải khớp các nhánh của `sched.sh`.
5. Đêm 19, 20 và 23/10 job `backfill` báo `SKIP: docker chua chay`. Khối ngoại cũng sẽ gặp như vậy, nên phải kiểm **kết quả** chứ không chỉ canh job. Đây là khuôn của đợt 160: `prev_day_bars_alert` trong `heartbeat_check.py`.

## 1. Thiết kế (đã chốt)

**Nhánh mới** `foreign-flow` trong `scripts/sched.sh`:

```bash
  foreign-flow)
    shift || true
    exec "$RUN" foreign-flow.log foreign-flow \
      uv run python scripts/backfill_foreign_flow.py \
      --from "$(date -d "$BACKFILL_DAYS days ago" +%F)" \
      --to "$(date +%F)" \
      "$@"
    ;;
```

- Cửa sổ trượt 7 ngày, dùng chung `BACKFILL_DAYS`:
  - upsert nên chạy lại không nhân đôi;
  - một phiên bị lỡ, hoặc có số chưa chốt ở lần chạy trước, sẽ được nạp lại ở lần sau;
  - mỗi lần chạy khoảng 5 × 7 lệnh gọi × 1,1 giây, dưới 1 phút.
- Lịch: **20:45 T2–T6**. Lịch nằm ngoài code, trong `DEPLOYMENT.md` và Task Scheduler; Claude đăng ký task sau audit.
- Thêm nhánh vào danh sách ở đầu file và vào dòng `dung:` của `*)`.

**`scripts/backfill_foreign_flow.py`**: tách để qua được test hợp đồng, không đổi hành vi.
- `build_parser() -> argparse.ArgumentParser`, gồm đúng các cờ hiện có.
- `def main(argv: list[str] | None = None) -> int:` có câu đầu `args = build_parser().parse_args(argv)`, rồi `return run(args)`.
- `def run(args, client=None, storage=None) -> int:` chứa toàn bộ thân `main` hiện tại.
- Test hiện có chuyển sang gọi `run(build_parser().parse_args([...]), client=..., storage=...)`, hoặc `main([...])` kèm monkeypatch `load_config`/`Storage`/`build_legacy_client`. **Assert giữ nguyên.**

**`scripts/heartbeat_check.py`**: thêm hai mục cấu hình và một phép kiểm.
- `SCHEDULE_EXIT_POLICIES["foreign-flow"]`:
  - `log_file="foreign-flow.log"`, `label="foreign-flow"`, `normal_exit_codes=frozenset({0})`;
  - `reason` nêu đúng dòng code của mã thoát 1, 2, 3 trong `backfill_foreign_flow.py` và ghi rõ "script không gửi Telegram".
- `KHONG_CANH["foreign-flow"]`: lý do giống `backfill`, tức chỉ chạy buổi tối ngày giao dịch. Kết quả được kiểm gián tiếp bằng phép kiểm dưới đây.
- Hàm mới `prev_day_foreign_flow_alert(storage, now, holidays, alerted_for) -> tuple[str | None, str]`, theo khuôn `prev_day_bars_alert`:
  - `P = previous_trading_day(now.date(), holidays)`. Nếu `alerted_for == P` thì trả `(None, P)`.
  - `n_P` = số dòng `foreign_flow_daily` có `trading_date = P`.
  - `base` = **trung vị** số dòng mỗi ngày của tối đa 5 ngày có dữ liệu gần nhất **trước** P. Không có ngày nào trước P (bảng rỗng) thì trả `(None, P)` và không báo, để tránh báo giả trước khi nạp lịch sử.
  - Nếu `n_P < 0.8 * base` thì gửi tin `[WARN] khối ngoại ngày {P}: {n_P} dòng (trung vị 5 phiên trước {base}) — Khắc phục: ./scripts/sched.sh foreign-flow (idempotent)`. Ngược lại trả `(None, P)`.
  - Mức WARN, không phải CRITICAL: đây là dữ liệu nghiên cứu, không chặn giao dịch.
- Gọi hàm trong `main`, ngay sau khối đợt 160, cũng nằm trong `if in_check_window:`:
  - dùng file trạng thái riêng `logs/.prev_day_foreign_flow_state.json` qua `load_json_state`/`save_json_state`;
  - `--dry-run` thì không ghi trạng thái;
  - bọc `try/except` và in ra **stderr** giống hệt khối đợt 160. Phép kiểm mới hỏng không được làm chết các phép kiểm khác.

**`trading/storage/db.py`**: thêm đúng một method `read_foreign_flow_day_counts(frm: date, to: date) -> dict[date, int]`, dùng `SELECT trading_date, count(*) ... GROUP BY 1`.

**`DEPLOYMENT.md`**:
- thêm dòng cron `45 20 * * 1-5 cd /opt/trading && scripts/sched.sh foreign-flow` ở cả hai chỗ đang liệt kê cron;
- thêm hàng `trading-foreign-flow | 20:45 T2–T6 | cùng vbs, tham số foreign-flow` vào bảng Windows;
- sửa "Mười sáu"/"mười sáu" thành "Mười bảy"/"mười bảy" ở đoạn nói số task;
- thêm hàng vào bảng §9.6 (job chạy bù được) nếu bảng đó liệt kê từng job.

## 2. Phạm vi file

**Được sửa:** `scripts/sched.sh`, `scripts/backfill_foreign_flow.py`, `scripts/heartbeat_check.py`, `trading/storage/db.py`, `DEPLOYMENT.md`, `tests/test_foreign_flow.py`, cùng một file test mới `tests/test_heartbeat_foreign_flow.py`. Test integration của method mới thì thêm vào `tests/test_storage.py`.

**Không được đụng:** `trading/collector/foreign_flow.py`, `run_if_docker_up.sh`, `run_hidden.vbs`, các nhánh `sched.sh` khác, các phép kiểm heartbeat khác, collector, engine, `schema.sql`.

**Các sửa của Claude phải giữ** (bài học đợt 183b: agent viết lại từ bản trước audit):
1. `backfill_foreign_flow.py` dùng `load_config`, không dùng `Config.from_yaml`.
2. `foreign_flow._call_daily_stock_price` chỉ gọi `client.daily_stock_price(None, req)`, không có nhánh bắt `TypeError`.
3. `foreign_flow._make_stock_price_req` không có `except` trả dict.
4. Các test sau phải còn nguyên tên, còn nguyên assert, và vẫn xanh:
   - `test_parse_daily_stock_price_fixture_vcb_hpg`
   - `test_parse_daily_stock_price_bad_symbol_rejected`
   - `test_parse_daily_stock_price_missing_field_bad_row`
   - `test_parse_daily_stock_price_net_mismatch_kept_and_counted`
   - `test_parse_daily_stock_price_trading_date_day_month_order`
   - `test_fetch_day_pagination_called_page_3`
   - `test_fetch_day_nodatafound_returns_empty`
   - `test_fetch_day_retry_success`
   - `test_fetch_day_retry_failure_raises`
   - `test_fetch_day_sleep_callable`
   - `test_backfill_foreign_flow_main_success`
   - `test_backfill_foreign_flow_main_api_error_exit_2`
   - `test_backfill_foreign_flow_main_loads_real_config_path`
   - `test_backfill_foreign_flow_main_empty_universe_exit_3`
   - `test_foreign_flow_storage_roundtrip_upsert_and_read`

**Ràng buộc:**
- Không gọi API thật.
- Không ghi DB thật; test integration chỉ dùng `trading_test`.
- **Không chạy `scripts/sched.sh`** dưới bất kỳ hình thức nào, kể cả để thử cờ lạ (bài học đợt 156).
- Không đăng ký hay sửa task Windows. Không restart container. Không mở `.env`.
- Test heartbeat **không được ghi** vào `logs/` thật (bài học đợt 142). File trạng thái phải nằm trong `tmp_path`, và hàm nhận `Storage` giả.

## 3. Các bước (TDD)

1. **Tách `main`/`run`/`build_parser`** → kiểm chứng bằng: 15 test ở §2 xanh; `uv run pytest tests/test_sched_args.py -q` xanh **sau khi** thêm nhánh ở bước 2 (khi đó script được tham số hoá vào test).
2. **Nhánh `sched.sh` + hai mục heartbeat + `DEPLOYMENT.md`** → kiểm chứng bằng: `uv run pytest tests/test_sched_args.py tests/test_schedule_watch.py tests/test_deployment_doc.py tests/test_scripts_convention.py -q` xanh.
3. **`read_foreign_flow_day_counts`** (integration, `trading_test`): 3 ngày có 2/1/0 dòng → trả `{d1: 2, d2: 1}`, không có khoá cho ngày 0 dòng.
4. **`prev_day_foreign_flow_alert`** với `Storage` giả và `now` cố định, ví dụ thứ Ba 27/10/2026 lúc 09:00, P = 26/10:
   - `n_P = 1550`, 5 phiên trước đều 1557: không báo.
   - `n_P = 0`: báo, tin chứa `2026-10-26` và `sched.sh foreign-flow`.
   - `n_P = 1000`, 5 phiên trước đều 1557: báo, vì 1000 < 0,8 × 1557.
   - `n_P = 1300`: không báo, vì 1300 ≥ 1245,6.
   - Trung vị chứ không phải min: 5 phiên trước `[1557, 1557, 1557, 1557, 10]` và `n_P = 1000` thì vẫn báo.
   - `alerted_for == "2026-10-26"`: không báo.
   - Bảng rỗng trước P: không báo.
   - `now` là thứ Hai 26/10 thì P = thứ Sáu 23/10 (qua cuối tuần).
5. **Nối vào `main`** → kiểm chứng bằng test gọi `main(["--dry-run"])` của heartbeat với môi trường giả. Theo khuôn test đợt 160 trong `tests/test_heartbeat_prev_day_bars.py`: monkeypatch `Storage`, giờ và đường dẫn `logs_dir` sang `tmp_path`.
   - (i) Khối khối ngoại ném exception thì tin của phép kiểm khác vẫn ra stdout, và stderr có `[WARN] heartbeat khong kiem duoc khoi ngoai`.
   - (ii) `--dry-run` không tạo file trạng thái.
6. **Phép phá.** Mỗi phép phải làm đỏ ít nhất một test **gọi code sản phẩm**. Phá xong khôi phục, ghi lệnh và kết quả vào báo cáo.
   - (a) Bỏ `"$@"` khỏi nhánh `foreign-flow`.
   - (b) Xoá `SCHEDULE_EXIT_POLICIES["foreign-flow"]`.
   - (c) Xoá `KHONG_CANH["foreign-flow"]`.
   - (d) Bọc câu `parse_args` của `main` trong `if argv is not None:`.
   - (e) Đổi trung vị thành `min`.
   - (f) Bỏ kiểm `alerted_for`.
   - (g) Bỏ `try/except` quanh khối khối ngoại trong `main`.
   - (h) Xoá dòng cron `foreign-flow` trong `DEPLOYMENT.md`.
   - (i) Bỏ nhánh "không có ngày nào trước P thì không báo": test bảng rỗng phải đỏ.

   Không có cờ phá thử trong code sản phẩm.
7. **Toàn suite** → kiểm chứng bằng:
   - `uv run pytest -m "not integration" -q`: không đỏ thêm; ghi số passed trước và sau (trước là 1992 sau `d3ffd41`; agent tự đo lại).
   - `uv run ruff check trading tests scripts/backfill_foreign_flow.py scripts/heartbeat_check.py` sạch.

## 4. GitNexus (bắt buộc)

- Dùng `gitnexus` hoặc `node .gitnexus/run.cjs`, **không npx**.
- Trước khi sửa:
  - `context` cho `prev_day_bars_alert` và `main` trong `scripts/heartbeat_check.py`;
  - `impact --direction upstream` cho `main` của `heartbeat_check.py`, và cho `main` của `backfill_foreign_flow.py`;
  - HIGH/CRITICAL thì báo trong báo cáo, UNKNOWN thì grep xác nhận.
- Sau khi sửa: `detect-changes --scope all`, dán nguyên văn phần tóm tắt.

## 5. Báo cáo agent phải nộp

1. Nguyên văn kết quả GitNexus trước và sau khi sửa.
2. Diff tóm tắt theo file. Mọi dòng phải truy ngược được về §1.
3. Danh sách `def test_` của `tests/test_foreign_flow.py` sau khi sửa, để Claude so với §2. Thêm test mới, số passed trước/sau, bảng phép phá (a)–(i) kèm test bị đỏ.
4. Chỗ mơ hồ đã gặp. Nếu có lựa chọn ảnh hưởng tin cảnh báo hay dữ liệu mà brief chưa quy định, **dừng và hỏi**.
5. Cam kết: không gọi API thật, không ghi DB thật, không chạy `sched.sh`, không đụng Task Scheduler, không commit/push.

## 6. Claude làm sau khi nhận báo cáo

1. **Audit:**
   - đối chiếu diff với §2;
   - so danh sách `def test_` với §2;
   - chạy lại toàn suite và (a)–(i);
   - xác nhận ba sửa của Claude vẫn còn.
2. **Đo giờ SSI công bố số trong ngày:** tối thứ Hai 26/10 lúc khoảng 20:40, gọi chỉ đọc `DailyStockPrice` ngày 26/10.
   - Có dữ liệu thì giữ lịch 20:45.
   - Rỗng thì đo lại lúc 23:00 và 07:30 sáng hôm sau, rồi dời lịch sang mốc sớm nhất đã có số. Nhớ sửa `DEPLOYMENT.md` cho khớp. Code không đổi vì cửa sổ 7 ngày phủ cả hai cách.
3. **Đăng ký `trading-foreign-flow`:**
   - chép cấu hình XML của `trading-backfill-universe`, chỉ đổi giờ và tham số `foreign-flow`;
   - chạy thử bằng `schtasks /run`;
   - kiểm `Last Run Time` khác rỗng và `logs/foreign-flow.log` có `EXIT=0`.
4. Sáng ngày giao dịch kế tiếp: xác nhận heartbeat im lặng khi đủ dòng.
5. Commit, push, cập nhật memory.
