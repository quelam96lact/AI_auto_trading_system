# Plan 2026-08-10 — Kiểm chứng bản fix chunking daily trên API SSI thật

## Việc này CHẶN ở chỗ chủ dự án, không phải ở bạn

Token trong DB đã chết (đo lúc 21:25 ngày 2026-08-10):

```
expires_at:               HET HAN -935.2 phut
refresh_token_expires_at: HET HAN -470.2 phut
```

Refresh token hết hạn ~7,8 tiếng trước. OTP gửi về máy chủ dự án nên bạn KHÔNG
lấy được. **Đừng chạy bước 3 khi chưa được báo là token đã sống lại** — chạy chỉ
tổ nhận `AuthenticationError` rồi tưởng code hỏng.

Bước 1 và 2 làm được ngay, không cần token.

## Bối cảnh — vì sao phải kiểm chứng

Commit `69fa41e` sửa `_paged_daily` (`trading/collector/backfill.py:264-286`):
SSI chặn 1000 dòng/call và trả về **cửa sổ mới nhất**, im lặng bỏ phần cũ. Xin
10 năm thì chỉ nhận 2021-2025 mà không có lỗi nào. Bản fix chia thành chunk 366
ngày.

Bản fix này **chưa từng được gọi lên API thật**. Bằng chứng hiện có chỉ là unit
test dựng trên hành vi API đã đo. Đó chính là lỗ hổng cần bịt.

## Vì sao KHÔNG làm theo quy trình 4a/4b/4c trong RUNBOOK_OTP_AUTH.txt

Runbook bảo `DELETE FROM bars_daily WHERE symbol='VCB'` rồi backfill lại. Nó
được viết khi tôi tưởng còn mã chưa backfill. Tôi vừa kiểm tra DB: **toàn bộ vũ
trụ mã đã có dữ liệu từ 2016 rồi**, mọi mã `status='ok'`. Ví dụ AAA: 2.642 dòng
từ 2016-01-03. Nên quy trình đó bắt buộc phải xoá dữ liệu thật mới có ý nghĩa.

Không cần thiết. Đọc code:

- `daily_ohlc()` (`backfill.py:259-262`) chỉ **trả về** list[Bar].
- Việc ghi DB nằm ở hàm gọi: `storage.write_daily(...)` (`backfill.py:336`).

Nên gọi thẳng `client.daily_ohlc(...)` kiểm chứng đúng code path cần kiểm
(`daily_ohlc` → `_paged_daily` → `_fetch_with_reauth`) mà **không ghi một dòng
nào vào DB**. Không xoá, không mất dữ liệu, chạy lại bao nhiêu lần cũng được.

---

## Bước 1 — Viết script dò (KHÔNG cần token, làm ngay)

Tạo `scripts/.probe_backfill_daily.py` (dấu chấm đầu tên → đã gitignore từ
commit `2f630d7`, pytest không thu gom).

Script phải:

1. Dựng `Config` qua `load_config` và `Storage(cfg.db_dsn)` như
   `scripts/backfill_universe.py` đang làm — `SSIRestClient(cfg, storage)` cần
   storage để đọc refresh_token. Đọc file đó để lấy đúng cách khởi tạo, đừng
   đoán.
2. Gọi `await client.daily_ohlc(symbol, date(2016,1,1), date(2025,12,31))`.
3. In ra, KHÔNG ghi DB:
   - tổng số bar trả về
   - ngày cũ nhất, ngày mới nhất
   - số bar theo từng năm (đây là thứ chỉ đích danh chunking có chạy không)
4. Nhận `--symbol` từ dòng lệnh, mặc định `AAM`.

**TUYỆT ĐỐI KHÔNG gọi `storage.write_daily`, `write_bars`, hay bất kỳ lệnh
DELETE/UPDATE/INSERT nào.** Script này chỉ đọc.

→ kiểm chứng bước 1: `uv run python scripts/.probe_backfill_daily.py --help`
   chạy được, và `grep -n "write_daily\|write_bars\|DELETE\|INSERT\|UPDATE"`
   trên file trả về rỗng. Paste cả hai.

## Bước 2 — Ghi lại trạng thái DB trước (KHÔNG cần token)

```
docker compose exec -T postgres psql -U trading -d trading -c "SELECT count(*) FROM bars_daily WHERE symbol='AAM';"
```

Paste con số. Cuối bước 3 sẽ chạy lại đúng lệnh này để chứng minh script không
đụng vào DB.

## Bước 3 — CHẠY THẬT (chỉ khi tôi báo token đã sống)

```
uv run python scripts/.probe_backfill_daily.py --symbol AAM
```

**ĐẠT:**
- năm cũ nhất là 2016
- mỗi năm khoảng 240-252 bar (số phiên một năm của HOSE)
- tổng khoảng 2.400-2.600

**HỎNG (đúng bug cũ quay lại):**
- năm cũ nhất rơi vào 2021-2022
- tổng đúng chằn 1.000
→ báo NGAY, đừng sửa gì cả.

Rồi chạy lại lệnh đếm ở bước 2 — con số phải **y hệt**. Paste cả hai lần.

→ Paste TOÀN BỘ output thật, kể cả khi hỏng. Đặc biệt: nếu thấy
  `AuthenticationError` thì đó là token, KHÔNG phải bug chunking — báo lại,
  đừng kết luận gì về bản fix.

## Bước 4 (chỉ làm nếu bước 3 ĐẠT) — thử re-auth trên job dài

Bug thứ hai đã sửa: client xác thực một lần rồi cache, job chạy quá ~15 phút
chết bằng 401. Chỉ kiểm chứng được bằng job dài hơn 15 phút.

Chạy script dò cho ~20 mã liên tiếp trong một tiến trình (thêm cờ `--symbols`
nhận danh sách, hoặc lặp trong Python — KHÔNG lặp bằng shell, vì mỗi lần chạy
lại là một tiến trình mới, không tái hiện được điều kiện cache).

**ĐẠT:** chạy hết, không có 401 nào.
**HỎNG:** xuất hiện `AuthenticationError` / `Authentication failed: 401`.

Nếu refresh token (~8 giờ) hết giữa chừng thì job dừng với lỗi rõ ràng đòi chạy
lại OTP — đó là **hành vi cố ý**, không phải bug. Báo lại, đừng gọi nó là lỗi.

## Phạm vi phẫu thuật

**Được tạo:** `scripts/.probe_backfill_daily.py` (file mới, đã gitignore).

**CẤM sửa:** `trading/collector/backfill.py` và mọi file trong `trading/`,
`scripts/backfill_universe.py`, `RUNBOOK_OTP_AUTH.txt`, `tests/**`. Nhiệm vụ này
là ĐO, không phải sửa. Nếu đo ra hỏng thì báo, tôi lên kế hoạch sửa riêng.

**CẤM tuyệt đối:** mọi lệnh DELETE/UPDATE/INSERT/TRUNCATE trên Postgres. Mọi
`storage.write_*`. Chạm vào dữ liệu phái sinh, đặc biệt mã `41I1G8000` trong
bảng `bars`. Chạy `scripts/backfill_universe.py`. Commit, push.

**CẤM tuyệt đối:** mở, in, hay paste nội dung file token cục bộ trong `scripts/`.
Chỉ được nhắc tới `expires_at` / `refresh_token_expires_at`.

## Dừng lại và hỏi nếu

- Bước 3 ra kết quả HỎNG → báo, đừng sửa code.
- Gặp `AuthenticationError` → báo, đó là vấn đề token.
- Thấy cần ghi vào DB để kiểm chứng → dừng, hỏi tôi. Gần như chắc chắn là không cần.
