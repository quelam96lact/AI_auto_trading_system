# Brief đợt 209 — nạp bù và kiểm tra nến không phụ thuộc danh sách ngày nghỉ

Ngày: 02/11/2026. Người giao: Claude (Lead). Người làm: Builder.

## Mục tiêu (lời chủ dự án)

"Hệ thống tự động bổ sung nến thiếu khi khởi động server, không phụ thuộc vào việc biết trước ngày holiday."

## Hiện trạng (Lead đã kiểm chứng ngày 02/11)

- `scripts/startup_catchup.py` đã tự nạp bù theo mốc `attempted_until` của từng mã. Dải nạp là ngày lịch, nên ngày nghỉ chỉ trả rỗng, không hại gì. Bằng chứng: ngày 01/11 lúc 13:43, job tự nạp 27→30/10 sau đợt Docker tắt. **Không đụng phần nạp này**, trừ những thay đổi ghi rõ bên dưới.
- **Lỗ A:** bước kiểm (dòng 315–336) chọn `check_days` bằng `is_trading_day(cur, cfg.holidays)`. Ngày nghỉ không có trong danh sách sẽ có 0 nến, nên bị coi là "thiếu", job thoát 1 và gây báo động oan trong 14 ngày. Tái hiện: `find_short_days({2/11..6/11 trừ 5/11: 170}, [2..6/11], ...)` cho ra `[2026-11-05]`.
- **Lỗ B:** ngày thiếu một phần thì không bao giờ được nạp lại. Lý do: `backfill_one` bỏ qua mã khi `attempted_until >= to`, và bước kiểm chỉ báo động chứ không nạp bù.
- **Lỗ C:** `scripts/daily_data_check.py`, trong `evaluate_daily_completeness`, xử lý một ngày thường không có trong danh sách nghỉ, `present_symbols` rỗng và backfill đã xong như sau: trả mã 2 (CRITICAL). Với ngày nghỉ không có trong danh sách, đây là báo động oan.

## Nguyên tắc

Ngày giao dịch do **dữ liệu SSI** quyết định, không do danh sách ngày nghỉ. Danh sách `cfg.holidays` vẫn được giữ và vẫn loại ngày như hiện nay, vì thừa thì không hại. Nhưng **không có chỗ nào được phép cần danh sách này mới đúng**.

Một ngày thường (thứ Hai–thứ Sáu) là **ngày không giao dịch** khi đồng thời thỏa ba điều kiện:
- sau khi **hỏi lại SSI** nến 1d của `cfg.symbols` cho đúng ngày đó (bỏ qua mốc resume),
- bars_daily vẫn không có dòng nào của bất kỳ mã active nào trong ngày đó,
- và lần hỏi lại không lỗi.

Nếu lần hỏi lại lỗi, ngày đó vẫn bị tính là thiếu. Không bao giờ được coi lỗi là ngày nghỉ.

Vì ngày nào còn 0 nến cũng được hỏi lại ở mỗi lần chạy, trường hợp "SSI chưa chốt dữ liệu lúc 21:45" sẽ tự lành ở lần chạy 06:40 sáng hôm sau.

## Giả định (Builder phải kiểm, sai thì DỪNG và báo)

1. `backfill_universe.main([... "--symbols", "A,B", ...])` không gọi `load_symbols` và không ghi `is_active`. Kiểm bằng cách đọc nhánh `--symbols` trong `main`.
2. `backfill_foreign_flow.main(["--from", d1, "--to", d2])` hỏi lại SSI cho cả dải và UPSERT, nghĩa là chạy lại an toàn và không bỏ qua theo mốc. Đọc code để xác nhận. Nếu nó có cơ chế bỏ qua, DỪNG và báo.
3. `cfg.symbols` (HPG, IJC, AAA) là mã active. Nếu một mã không active, phép "vẫn 0 dòng mã active" vẫn đúng, vì đếm trên toàn bộ mã active chứ không riêng `cfg.symbols`.

## Phạm vi

Được sửa:
- `scripts/backfill_universe.py`
- `scripts/startup_catchup.py`
- `scripts/daily_data_check.py`
- các test tương ứng: `tests/test_backfill_universe.py`, `tests/test_startup_catchup.py`, `tests/test_daily_data_check.py` (theo tên file thật)

KHÔNG đụng:
- `trading/calendar_vn.py`, `config/config.yaml`, `trading/scheduler/main.py`, `scripts/refresh_universe.py`, `scripts/heartbeat_check.py`
- `catchup_end`, `plan_universe_start`, `gap_origin`, `plan_foreign_flow_start`, `find_short_days`: giữ nguyên chữ ký và hành vi
- bất kỳ code nào ngoài danh sách được sửa. Thấy vấn đề khác thì báo, không sửa.

Bắt buộc dùng GitNexus:
- Trước khi sửa: chạy `node .gitnexus/run.cjs analyze --index-only` (index đang cũ, ví dụ không thấy `backfill_one`), rồi `impact` upstream cho `backfill_one`, `main` (startup_catchup), `evaluate_daily_completeness` và hàm gọi nó trong daily_data_check. Báo lại callers và mức risk.
- Sau khi sửa: chạy `detect-changes --scope all`.
- Dùng `gitnexus` hoặc `node .gitnexus/run.cjs`, không dùng npx.

Không commit, không push.

Không chạy `sched.sh`. Không chạy script thật để "kiểm cổng". Test không được ghi file thật trong `logs/`.

## Các bước

### 1. `backfill_universe --force`

- Thêm cờ `--force`. Khi bật, `backfill_one` không bỏ qua theo `attempted_until`.
- Khi `--force` cập nhật progress, **không được kéo lùi mốc**:
  - `attempted_until` = max(cũ, `to`)
  - `last_done_date` = max(cũ, ngày nến thật mới nhất), trường hợp nào là None thì lấy giá trị còn lại.
- Khi không có `--force`, hành vi giữ nguyên từng byte.

Kiểm chứng bằng test:
- (a) có `--force`, `attempted_until` cũ = 30/10, nạp `--from 20/10 --to 20/10`: client được gọi, và `attempted_until` vẫn là 30/10.
- (b) không có `--force`, cùng trạng thái đó: mã bị bỏ qua, client không được gọi. Test này đã có thì giữ.
- (c) có `--force` mà lỗi: status 'error' như hiện nay.

### 2. `startup_catchup`: xác định ngày không giao dịch bằng dữ liệu (lỗ A)

Viết hàm thuần:

```
weekday_candidates(frm, to, holidays) -> list[date]
```
Trả về các ngày thứ Hai–thứ Sáu trong [frm, to] mà không nằm trong `holidays`.

Trong `main`, thay cách lập `check_days` và `baseline_days` như sau:
1. Lấy các ứng viên.
2. Các ứng viên có `counts_1d.get(d, 0) == 0` là "ngày 0 nến".
3. Nếu có ngày 0 nến và **không** `--dry-run`, gọi **một** lần `backfill_universe.main(["--timeframe","1d","--from",min,"--to",max,"--symbols",",".join(cfg.symbols),"--force","--sleep-ms","200"])`.
   - Lệnh trả mã khác 0/None hoặc ném lỗi: `has_error = True`, và mọi ngày 0 nến vẫn là ngày giao dịch (sẽ bị báo thiếu).
4. Nếu không lỗi, đọc lại counts. Ngày nào vẫn 0 là ngày không giao dịch: loại khỏi `check_days` và `baseline_days`, rồi in `[kiem] ngay khong giao dich theo SSI (bo qua): [...]`.
5. Khi `--dry-run`: không gọi SSI. In `[kiem] ngay 0 nen chua xac minh (dry-run): [...]`, và các ngày đó vẫn tính là ngày giao dịch.

Kiểm chứng bằng test:
- (d) Một ngày thường không có trong `holidays`, 0 nến, và lần hỏi lại vẫn 0. Kết quả: không có trong `thieu`, có dòng "ngay khong giao dich", rc 0 (nếu không còn gì khác sai), và lần hỏi lại được gọi đúng tham số `--symbols HPG,IJC,AAA --force --from d --to d`.
- (e) Lần hỏi lại có nến (SSI mới chốt dữ liệu). Kết quả: ngày đó là ngày giao dịch, được kiểm như thường.
- (f) Lần hỏi lại ném lỗi. Kết quả: ngày đó trong `thieu`, rc 1.
- (g) Dry-run: không gọi `backfill_universe.main` để hỏi lại.
- (h) Không có ngày 0 nến: không gọi hỏi lại.

### 3. `startup_catchup`: nạp lại ngày thiếu một phần (lỗ B)

Sau bước 2, nếu không `--dry-run` và có `short_1d`, `short_5m` hoặc `short_ff`, nạp lại **một lần** cho từng tập dữ liệu, với dải [min(short), max(short)] của chính tập đó:
- 1d: `backfill_universe.main(["--timeframe","1d","--from",..,"--to",..,"--use-universe","--force","--sleep-ms","200"])`
- 5m: như dòng nạp 5m hiện có, thêm `"--force"` (giữ `--skip-config-symbols`)
- foreign-flow: `backfill_foreign_flow.main(["--from",..,"--to",..])`

Lỗi xử lý như các bước nạp hiện có (`has_error`, in `[catchup] LOI ...`).

Sau đó đọc lại counts và tính lại `short_*`. Chỉ phần còn thiếu sau khi nạp lại mới được in và mới làm rc 1. Thêm một dòng in: `[nap lai] 1d: <dai> | 5m: <dai> | foreign-flow: <dai>`, tập nào không cần thì ghi "khong".

Kiểm chứng bằng test:
- (i) Thiếu một phần, nạp lại xong thì đủ. Kết quả: rc 0, lần nạp lại có `--force`.
- (j) Nạp lại xong vẫn thiếu. Kết quả: rc 1, ngày đó trong `thieu`.
- (k) Không thiếu: không gọi nạp lại.
- (l) Dry-run: không nạp lại.

### 4. `daily_data_check` (lỗ C)

Ở nhánh "ngày thường, 0 mã có nến, backfill đã xong" (đang trả mã 2): trước khi trả 2, hỏi lại SSI nến 1d của `cfg.symbols` cho đúng `target_date` với `--force`.
- Lấy lại `present_symbols` mà vẫn rỗng, và lần hỏi lại không lỗi: trả mã 0 với thông điệp "Ngày <d> không có giao dịch theo SSI (không có trong danh sách ngày nghỉ)".
- Lần hỏi lại có nến: đánh giá lại như thường.
- Lần hỏi lại lỗi: giữ mã 2.

Giữ `evaluate_daily_completeness` là hàm thuần. Lần hỏi lại phải nằm ở hàm gọi nó, có thể tiêm vào để test.

Kiểm chứng bằng test:
- (m) Hỏi lại vẫn rỗng: mã 0, thông điệp đúng.
- (n) Hỏi lại có nến: đánh giá lại.
- (o) Hỏi lại lỗi: mã 2.
- (p) Ngày có trong `holidays`: không hỏi lại, hành vi như cũ.

### 5. Kiểm tổng

- `uv run pytest -m "not integration" -q`: toàn bộ pass. Báo số passed trước và sau.
- `uv run ruff check trading tests scripts`: sạch.
- `detect-changes --scope all`: dán kết quả. Nếu báo "critical" do trùng tên `main`, chứng minh bằng grep.
- Liệt kê từng `def test_` mới, kèm chữ cái (a)–(p) mà nó phủ.

## Báo cáo

Gửi lại cho Lead:
- diff tóm tắt theo file
- kết quả 3 giả định
- kết quả impact và detect-changes
- danh sách test
- output pytest và ruff
