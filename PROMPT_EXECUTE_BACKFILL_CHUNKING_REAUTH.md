# Task: sửa 2 bug tiềm ẩn trong `trading/collector/backfill.py`

Kế hoạch đầy đủ: `docs/superpowers/plans/2026-08-10-backfill-daily-chunking-reauth.md`
— **đọc hết trước khi gõ dòng code đầu tiên.** Dưới đây là bản tóm tắt, không
thay thế kế hoạch.

## Việc cần làm

Commit `cfa0821` đã workaround 2 bug trong `scripts/backfill_universe.py` thay vì
sửa nơi phát sinh, vì lúc đó đang chạy job dài. Job xong rồi — sửa tận gốc và gỡ
workaround.

1. **`SSIRestClient.daily_ohlc()` không chunk theo ngày.** SSI chặn 1000 dòng/call
   và trả cửa sổ *mới nhất*, âm thầm bỏ phần cũ. Yêu cầu 10 năm → chỉ nhận
   2021–2025. `_paged_intraday()` ngay bên dưới đã chunk 7 ngày cho intraday;
   làm điều tương tự cho daily với **366 ngày/chunk**.

2. **`SSIRestClient` xác thực một lần rồi cache.** access_token sống ~15 phút;
   job dài chết bằng 401 (đã xảy ra thật: 1.191 lỗi sau ~1 giờ). Thêm re-auth
   **đúng một lần** khi gặp `ssi_sdk.exceptions.AuthenticationError` (SDK dùng
   class này cho cả 401 lẫn 403 — đã xác minh ở `rest_client.py:31-42`, không
   cần dò `status_code`).

3. Gỡ workaround trong `scripts/backfill_universe.py`: xoá `fetch_daily()` +
   `MAX_RANGE_DAYS`, và bỏ việc dựng lại client mỗi 25 mã trong `run()`.

## Bắt buộc

- **GitNexus trước khi sửa:** `gitnexus_impact` trên `daily_ohlc` và `_ensure_data`,
  báo cáo blast radius. HIGH/CRITICAL → dừng, hỏi tôi. Sau khi sửa:
  `gitnexus_detect_changes()`.
- **TDD thật:** viết test → chạy → **paste output RED** → mới implement. Test RED
  phải fail vì đúng cái bug đang nhắm, không phải vì import/typo. Không có output
  RED thì tôi coi như task chưa làm.
- **Chỉ 3 file** được thay đổi: `trading/collector/backfill.py` (chỉ class
  `SSIRestClient`), `scripts/backfill_universe.py`, `tests/test_backfill.py`.
  `git status` cuối cùng phải chứng minh điều đó.
- **KHÔNG chạy `ruff check --fix`** — chỉ `ruff check`. 7 lỗi ruff có sẵn dưới
  `scripts/` không thuộc phạm vi, để nguyên. Không "tiện tay" dọn code xung quanh.
- **KHÔNG đụng** `SSIRestClientLegacy`, `run_backfill`, `main`,
  `trading/collector/ssi_auth.py`, các script khác, hay streaming real-time.
- **Không sửa test có sẵn.** `test_paged_intraday_dedupes_when_ssi_page_index_overlaps`
  gọi `client._paged_intraday(fake_data, ...)` — giữ nguyên signature đó.
- **Không commit, không push.** Tôi audit rồi tôi commit.

## Xong khi

1. `uv run pytest -m "not integration" -v` PASS, **≥ 187 test** (baseline 183 + 4 mới).
2. Output RED của cả 2 nhóm test mới đã được paste.
3. `uv run ruff check trading tests scripts/backfill_universe.py` sạch.
4. `scripts/backfill_universe.py` không còn `fetch_daily`, `MAX_RANGE_DAYS`, hay
   logic dựng lại client theo lô 25 — và comment/docstring mô tả chúng cũng đã
   được cập nhật (để lại sẽ thành sai).
5. `gitnexus_detect_changes()` cho thấy phạm vi ảnh hưởng nằm trong 3 file trên.

## Một test đặc biệt quan trọng

`test_reauth_is_attempted_only_once`: fake luôn raise 401 → `AuthenticationError`
phải **thoát ra ngoài**, không bị nuốt, không retry vô hạn, và số lần re-auth
đúng bằng 1. Lý do: nếu chính refresh_token hết hạn (~8 giờ) thì không retry nào
cứu được — hệ thống phải fail to và rõ để người vận hành biết mà chạy lại OTP.
Một vòng retry im lặng ở đây sẽ biến "cần OTP" thành "job treo".

## Nếu phát hiện vấn đề ngoài phạm vi

Báo lại cho tôi, đừng tự sửa.
