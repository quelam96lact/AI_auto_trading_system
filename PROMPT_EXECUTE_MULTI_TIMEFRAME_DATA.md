# Prompt thực thi: dữ liệu lịch sử 3 sàn VN, đa khung thời gian

**Dùng prompt này để giao việc cho 1 agent coding khác thực thi.**

**Đọc trước, theo thứ tự:**
1. `docs/superpowers/plans/2026-08-09-multi-timeframe-data.md` — plan đầy đủ 7
   Task, có sẵn code và test cụ thể. **Nguồn sự thật duy nhất.**
2. `CLAUDE.md` mục "GitNexus — Code Intelligence".

---

## Mục tiêu (user đã chốt 2026-08-09)

| Khung | Nguồn | Lưu DB? |
|---|---|---|
| 1d — sâu **tối đa API cho (~10 năm)**, cả trước và sau 31/12/2025 | SSI daily | **Có** — `bars_daily` |
| 5m — từ **01/01/2026** | SSI intraday | **Có** — `bars` |
| 10m, 15m, 30m, 1h, 4h | tính từ **5m** | Không |
| 1w, 1M | tính từ **1d** | Không |

- Phạm vi mã: **toàn bộ HOSE + HNX + UPCOM**, nhưng 5m chỉ lấy cho tập mã
  **qua bộ lọc thanh khoản** (Task 6 — ngưỡng do user chốt, không phải bạn).
- **KHÔNG tạo bảng `bars_1h`.** 1h suy ra từ 5m.
- **Dữ liệu phái sinh giữ nguyên** — mã `41I1G8000` trong `bars` KHÔNG được xoá.
- **Streaming real-time KHÔNG đổi** — collector vẫn chỉ stream `config.symbols`.

## Thứ tự thực thi

```
Task 1 (schema) ─┐
Task 2 (resample)─┼─ độc lập, làm được ngay
Task 3 (CLI) ─────┘  (Task 3 cần Task 2 xong trước)

Task 4 (đo độ sâu API)  ──> Task 5 (backfill 1d)  ──> Task 6 (lọc thanh khoản)  ──> Task 7 (backfill 5m)
```

Task 4 là **cổng chặn** cho 5 và 7: không biết SSI trả dữ liệu sâu tới đâu thì
mọi tham số ngày đều là bịa.

---

## ⚠️ Quy tắc bắt buộc

### KHÔNG tự commit, không tự push
Xong mỗi Task thì báo cáo kèm bằng chứng rồi dừng. Claude audit và commit.

### DỪNG LẠI HỎI ở Task 6
Task 6 Step 1 in bảng phân bố số mã theo nhiều ngưỡng thanh khoản. **Dán bảng
đó vào báo cáo và DỪNG, chờ user chọn ngưỡng** trước khi ghi `is_active`.
Ngưỡng quyết định khối lượng Task 7 (mỗi mã ≈ 7 request API) — đây là quyết định
của user. Đừng tự chọn rồi chạy tiếp.

### GitNexus
`gitnexus_impact({target, direction: "upstream"})` trước khi sửa `init_schema`
(Task 1), `resample_bars`/`_bucket` (Task 2), `main` trong `backtest.py`
(Task 3). Dán nguyên văn. **HIGH/CRITICAL → DỪNG, hỏi.**
`gitnexus_detect_changes()` sau mỗi Task có sửa file.

### KHÔNG chạy `ruff --fix` ở bất kỳ đâu
Chỉ `ruff check`. Lỗi có sẵn trong `scripts/` → dán nguyên văn, **không sửa**.
(Đợt trước `--fix` đã âm thầm sửa 3 file ngoài phạm vi.)

### Kiểm tra `git diff --stat` sau mỗi lần dùng Edit tool
Hook PostToolUse chạy formatter và **reformat cả file**. Đợt trước một sửa đổi
1 dòng biến thành diff 65 dòng. Thấy churn thì `git checkout` file rồi áp lại
bằng `sed`/script Python qua Bash (không kích hoạt hook).

### Postgres: `127.0.0.1`, KHÔNG BAO GIỜ `localhost`
Trên máy này `localhost` → `::1` → **~130 giây mỗi lần connect**, và `Storage`
mở connection mới cho mỗi query → cả job/test treo.

### Job dài: chạy nền, có checkpoint
Task 5 và 7 chạy **nhiều giờ**. Chạy nền, đừng chờ đồng bộ. Bị ngắt thì chạy
lại đúng lệnh — checkpoint (`backfill_progress`) lo phần còn lại. Nếu bạn thấy
mình sắp chạy lại từ đầu, tức là checkpoint hỏng — sửa nó trước.

---

## Chuẩn bị

```bash
docker compose up -d postgres nats
uv run pytest -m "not integration" -q     # phải ra: 178 passed
uv run ruff check trading tests           # phải ra: All checks passed!
```
Baseline sai → DỪNG, báo lại.

Task 4, 5, 7 cần **credential SSI thật**. Thiếu → làm Task 1, 2, 3 trước (không
cần credential), rồi báo rõ phần nào bị chặn và vì sao. **Đừng bịa số.**

---

## Điểm dễ sai — đọc kỹ

1. **Con số `24` / `16` / `5` trong test regression Task 2 đã tính tay từ lưới
   46 slot thật.** Chạy ra khác thì **ĐỪNG sửa số cho khớp** — đó là giấu bug.
   Tính lại từ lưới ghi trong plan, đối chiếu. Còn lệch → phát hiện thật, báo cáo.

2. **4h ra 2 bar/phiên, không phải 1.** Neo bucket theo nửa đêm giờ VN (ranh
   giới 08:00 ôm phiên sáng, 12:00 ôm phiên chiều). Không tự đổi sang neo epoch UTC.

3. **Kết quả 5m/10m/15m/1h phải KHÔNG ĐỔI** sau khi sửa resample. Test
   regression khoá điều này — nó fail nghĩa là cách sửa của bạn sai, không phải
   test sai.

4. **1d/1w/1M không resample bằng phút.** Phiên VN chỉ chiếm phần nhỏ của ngày
   và bar ATC nằm lệch (14:45, sau khoảng trống 14:30–14:40).

5. **Task 3: khung ≤ 4h đọc bảng `bars`; khung ≥ 1d đọc `bars_daily`.** Trước
   đây mọi thứ đọc từ `bars` — đó là lý do phải thêm `_TF_SPEC` có cả bảng nguồn.

6. **Task 5/7: lỗi một mã KHÔNG được giết cả job.** try/except quanh **từng
   mã**, ghi `status='error'` rồi đi tiếp. Đúng bài học commit `ed017c9`: trước
   đây một mã lỗi làm hỏng cả vòng lặp và không ai biết.

7. **`write_bars`/`write_daily` đã UPSERT theo `(symbol, ts)`** nên chạy lại an
   toàn, không nhân bản dữ liệu. Đừng tự thêm logic chống trùng.

8. **Có mã lỗi là bình thường** (huỷ niêm yết, mã mới, mã ngừng giao dịch).
   Liệt kê ra trong báo cáo, **đừng giấu và đừng cố sửa cho bằng hết**.

---

## Tiêu chí hoàn thành

1. `uv run pytest -m "not integration" -q` → **183 passed** (178 + 5 test mới).
2. `uv run ruff check trading tests` → `All checks passed!`
3. Task 1, 2, 3: có output test **FAIL trước khi sửa code** (dán được).
4. `bars_daily` là hypertable, có ≥ 1.000 mã.
5. Chạy lại `backfill_universe` lần 2 → bỏ qua mã đã `ok` (chứng minh checkpoint).
6. `symbol_universe.is_active` đúng theo ngưỡng **user đã chốt**.
7. Bảng số bar theo 9 khung (Task 7 Step 3), kèm đánh giá đạt/không đạt ngưỡng
   ≥ 100 bar từng khung.
8. Dung lượng `bars` và `bars_daily` (Task 7 Step 4).
9. Không có commit/push nào do bạn tạo.

---

## Báo cáo lại (đủ, không tóm tắt)

1. **Baseline** trước khi sửa gì.
2. **Task 1, 2, 3**: `gitnexus_impact` → output test FAIL → diff đầy đủ →
   output test PASS → `gitnexus_detect_changes()` → `git diff --stat`.
3. **Task 4**: output spike dán nguyên văn + nội dung file findings. Nêu rõ
   **ngày sớm nhất có bar 5m** và **ngày sớm nhất có bar 1d**, số mã mỗi sàn.
4. **Task 5**: lệnh đã chạy với tham số nào, thời gian chạy, số mã/số dòng
   `bars_daily`, số mã lỗi + 5 lỗi đầu.
5. **Task 6**: bảng phân bố ngưỡng — rồi **DỪNG chờ user**.
6. **Task 7**: bảng số bar 9 khung + dung lượng đĩa.
7. **Phát hiện ngoài phạm vi** — báo cáo, không sửa. Đã biết trước, **không
   phải việc của bạn**: `run_backtest()` thiếu tham số `capital` ở
   `tests/test_backtest_cli.py`; 2 test fail sẵn ở `tests/test_engine_main.py`.
8. **Nói thẳng những gì CHƯA kiểm chứng được.** Đặc biệt: nếu SSI không trả 5m
   về tới 01/01/2026 thì nói rõ mốc thật sự sớm nhất — đó là kết quả hợp lệ,
   không phải thất bại, và user cần biết để điều chỉnh kỳ vọng.

**Không tự commit, không tự push.** Chờ Claude audit.
