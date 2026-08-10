# Plan 2026-08-10 — Sửa tận gốc 2 bug tiềm ẩn trong `trading/collector/backfill.py`

## Bối cảnh

Commit `cfa0821` đã ghi rõ: hai bug dưới đây được **workaround trong
`scripts/backfill_universe.py`** thay vì sửa ở nơi phát sinh, để tránh đụng code
dùng chung với collector live giữa lúc đang chạy job dài. Job đã xong. Giờ sửa
tử tế và gỡ workaround.

### Bug 1 — `SSIRestClient.daily_ohlc()` không chunk theo ngày

`backfill.py:226-233`: một lời gọi duy nhất cho cả khoảng `frm..to`. Mọi endpoint
OHLC của SSI chặn 1000 dòng/call và trả về **cửa sổ mới nhất**, âm thầm bỏ phần
cũ. Đo thật 2026-08-09: yêu cầu 10 năm trong 1 call chỉ trả 1000 bar của
2021–2025, mất im lặng 2016–2020.

Trớ trêu là `_paged_intraday()` ngay bên dưới (`backfill.py:240-262`) đã chunk 7
ngày kèm comment giải thích `page` không phải cursor (commit `95f563f`) — cùng
bài học, chưa bao giờ áp cho daily.

### Bug 2 — `SSIRestClient` xác thực một lần rồi cache, không tự re-auth

`_ensure_data()` (`backfill.py:202-210`) gọi `ensure_authenticated` đúng một lần
rồi giữ `self._data`. access_token sống ~15 phút. Mọi job chạy lâu hơn thế chết
bằng 401. Đã xảy ra thật: lần chạy đầu của backfill toàn sàn chết sau ~1 giờ với
1.191 lỗi xác thực.

Đã xác minh trong SDK (`.venv/.../ssi_sdk/transport/rest_client.py:31-42`):
**cả 401 và 403 đều raise `ssi_sdk.exceptions.AuthenticationError`** — bắt đúng
một class này là đủ, không cần dò `status_code`. 429 raise `RateLimitError`
riêng, không liên quan tới việc re-auth.

## Giả định (nêu rõ, không giấu)

- `ensure_authenticated()` gọi `token_manager.refresh()` **không điều kiện** mỗi
  lần được gọi, nên dựng lại client = có access_token mới. Đây là điều làm cho
  cách sửa "reset + ensure lại" hoạt động; nếu sau này hàm đó thành lazy
  (chỉ refresh khi sắp hết hạn) thì phải xem lại chỗ này.
- refresh_token sống ~8 giờ. Nếu chính refresh_token hết hạn thì `ensure_authenticated`
  raise `RuntimeError` yêu cầu chạy OTP thủ công — retry không cứu được, và
  **không được** retry loop vô hạn ở đó.
- 366 ngày/chunk cho daily là an toàn: 1 năm ≈ 250 phiên, dưới trần 1000 (đo thật
  2026-08-09: chunk 1 năm trả 2016=251, 2018=248, 2021=250 bar).

## Phạm vi phẫu thuật

**ĐƯỢC sửa — và chỉ 3 file này:**
- `trading/collector/backfill.py` — chỉ class `SSIRestClient`
- `scripts/backfill_universe.py` — gỡ workaround
- `tests/test_backfill.py` — thêm test mới

**KHÔNG được đụng:**
- `SSIRestClientLegacy` (giữ nguyên làm rollback reference, xem docstring của nó)
- `run_backfill()`, `main()`, `parse_intraday_response()`, `parse_daily_response()`,
  `_ohlc_rows_to_bars()`, `_parse_trading_date()`
- `trading/collector/ssi_auth.py` — logic auth giữ nguyên, chỉ *gọi lại* nó
- `scripts/backfill_history.py`, `scripts/screen_liquidity.py`, mọi script khác
- Streaming real-time của collector
- **KHÔNG chạy `ruff check --fix`.** Chỉ `ruff check`. 7 lỗi ruff có sẵn dưới
  `scripts/` là của người khác, để nguyên.
- Không sửa test có sẵn. Đặc biệt `test_paged_intraday_dedupes_when_ssi_page_index_overlaps`
  gọi `client._paged_intraday(fake_data, ...)` — **giữ nguyên signature** đó.

## Các bước

### Bước 0 — GitNexus trước khi sửa (bắt buộc, CLAUDE.md)

```
gitnexus_impact({target: "daily_ohlc", direction: "upstream"})
gitnexus_impact({target: "_ensure_data", direction: "upstream"})
```
Báo cáo blast radius. Nếu HIGH/CRITICAL thì **dừng và hỏi** trước khi sửa.

→ kiểm chứng bằng: dán output impact vào báo cáo.

### Bước 1 (RED) — Test cho bug chunking daily

Thêm vào `tests/test_backfill.py` một fake mô phỏng **đúng hành vi thật đã đo**
của SSI: trần 1000 dòng, trả cửa sổ *mới nhất* khi khoảng ngày quá rộng. Đã có
sẵn `FakeMarketData` cho intraday làm mẫu — viết `FakeMarketDataDailyCapped`
tương tự cho `get_ohlc_1day_historical`.

Test `test_daily_ohlc_chunks_and_keeps_oldest_rows`:
- sinh dữ liệu daily giả 2016-01-01 → 2025-12-31, ~250 bar/năm (chỉ ngày trong tuần)
- gọi `await client.daily_ohlc("VCB", date(2016,1,1), date(2025,12,31))`
- assert **bar cũ nhất (2016) có trong kết quả** — đây là điều bug làm mất
- assert tổng số bar bằng đúng số bar đã sinh (không mất, không trùng)

→ kiểm chứng bằng: chạy test, **paste output RED**. Test phải fail với thông
điệp cho thấy thiếu dữ liệu 2016, KHÔNG phải fail vì lỗi import/typo.

### Bước 2 (GREEN) — Chunk daily trong client

Trong `SSIRestClient`, thêm `_paged_daily()` theo đúng khuôn `_paged_intraday()`:
hằng số `_DAILY_CHUNK_DAYS = 366` (kèm comment ghi số đo thật ở trên), lặp chunk,
dedupe theo `r.trading_date`. `daily_ohlc()` gọi nó thay cho một call trần trụi.

→ kiểm chứng bằng: test Bước 1 PASS; toàn bộ `tests/test_backfill.py` vẫn PASS.

### Bước 3 (RED) — Test cho bug re-auth

Ba test, dùng fake raise `ssi_sdk.exceptions.AuthenticationError`:

1. `test_intraday_reauth_once_after_401_then_succeeds` — call đầu raise 401, call
   sau thành công → `daily_ohlc`/`intraday_ohlc` trả về dữ liệu đúng, và
   `_ensure_data` được gọi lại (đếm số lần).
2. `test_daily_ohlc_also_reauths_on_401` — đảm bảo đường daily cũng đi qua helper,
   không chỉ intraday.
3. `test_reauth_is_attempted_only_once` — fake luôn raise 401 → `AuthenticationError`
   **thoát ra ngoài** (không nuốt, không retry vô hạn), và số lần re-auth đúng
   bằng 1. Đây là test quan trọng nhất: refresh_token hết hạn thật thì phải fail
   to và rõ, để người vận hành biết mà chạy OTP.

→ kiểm chứng bằng: paste output RED của cả 3.

### Bước 4 (GREEN) — Re-auth một lần trong client

Thêm vào `SSIRestClient`:
- `_reset_auth()` — đóng auth cũ (bọc try/except, đóng lỗi không được che mất lỗi
  gốc), gán `self._auth = self._data = None`
- `_fetch_with_reauth(self, data, method: str, *args, **kwargs)` — gọi
  `getattr(data.market_data, method)(...)`; nếu `AuthenticationError` thì
  `_reset_auth()` → `_ensure_data()` → thử **lại đúng một lần** trên `data` mới.
  Lần thứ hai lỗi thì để exception bay ra.

Cả `_paged_daily` và `_paged_intraday` gọi API qua helper này.

**Lưu ý thiết kế** (đừng làm khác mà không báo): retry ở cấp **từng chunk**, không
bọc cả vòng lặp — 401 giữa chừng chỉ mất lại 1 chunk chứ không chạy lại từ đầu.
Và vì `_paged_*` vẫn nhận `data` làm tham số, fake trong test có sẵn không gọi
`_ensure_data` chừng nào không có 401 → test cũ không vỡ.

→ kiểm chứng bằng: 3 test Bước 3 PASS; `uv run pytest -m "not integration" -v`
toàn bộ PASS (baseline hiện tại: **183 passed**, không được ít hơn).

### Bước 5 — Gỡ workaround trong `scripts/backfill_universe.py`

- Xoá `fetch_daily()` và hằng `MAX_RANGE_DAYS`; `backfill_one` gọi thẳng
  `await client.daily_ohlc(symbol, frm, to)`.
- Trong `run()`: tạo `SSIRestClient` **một lần**, bỏ logic dựng lại mỗi 25 mã
  (`i % 25 == 1`). Sửa luôn comment ở đầu hàm cho khớp thực tế mới — comment cũ
  mô tả workaround đã biến mất, để lại sẽ thành sai.
- Cập nhật docstring đầu file (dòng nói "Chunk daily ≤ 30 ngày/call") cho đúng.

→ kiểm chứng bằng:
```
uv run python -c "import scripts.backfill_universe"     # import sạch
uv run ruff check trading tests scripts/backfill_universe.py
```
`ruff check` trên **đúng file này** phải sạch (không quét cả `scripts/`, vì ở đó
có 7 lỗi có sẵn không thuộc phạm vi task).

### Bước 6 — GitNexus sau khi sửa

```
gitnexus_detect_changes()
```
→ kiểm chứng bằng: dán output; phạm vi ảnh hưởng phải nằm trong 3 file đã liệt kê.

## Tiêu chí hoàn thành

1. Toàn bộ unit test PASS, số test ≥ 183 + 4 test mới.
2. Output RED của Bước 1 và Bước 3 đã được paste (bằng chứng test thật sự bắt bug).
3. `ruff check trading tests scripts/backfill_universe.py` sạch.
4. `scripts/backfill_universe.py` không còn `fetch_daily`, không còn `MAX_RANGE_DAYS`,
   không còn dựng lại client theo lô 25.
5. Không file nào ngoài 3 file trong phạm vi bị thay đổi (`git status` chứng minh).

## KHÔNG làm trong task này

- Không chạy job backfill thật lên SSI. Xác thực có thể đã hết hạn, và việc
  kiểm chứng trên dữ liệu sống là phần của tôi (planner), không phải của agent.
- Không tự commit, không tự push.
