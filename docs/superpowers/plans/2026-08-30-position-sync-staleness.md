# 2D — cảnh báo khi vị thế ngừng đồng bộ

Ngày 2026-08-30 (chủ nhật, thị trường đóng). Đo trên DB thật tại `b962e0f`.

## Vấn đề

Đường đặt lệnh THẬT đọc vị thế qua `Storage.read_real_positions()`
(`trading/storage/db.py:615-652`) → bảng `account_position_snapshot`, mỗi bar,
không cache. Bảng đó do `trading/collector/account_sync.py` ghi lại từ API SSI.

`trading/collector/main.py:135-137` bắt exception của `sync_account_data()` và
bắn WARN. Nhưng **không có gì đo TUỔI của bảng đó**. Nếu sync chạy thành công
mà trả dữ liệu cũ, hoặc một lỗi logic không ném exception, thì hệ thống đặt
lệnh BUY/SELL trên vị thế sai và không ai được báo.

`bars` đã có lớp này (2A, ngưỡng 15 phút). Vị thế thì chưa. Đây đúng lớp hỏng
âm thầm mà FEE-ALARM-1/2B đặt tên riêng cho token SSI — vị thế chưa từng có.

## Giả định (nêu rõ, không giấu)

1. Ngưỡng lấy từ ĐO THẬT, không bịa: `account_sync_log` + 8 mốc liên tiếp của
   `account_position_snapshot` cho nhịp **5 phút 05 giây**, rất đều (7 dòng
   mỗi mốc). Đặt ngưỡng **15 phút = ~3x nhịp đo được** — cùng hệ số an toàn
   mà 2A đã dùng. Nếu người thực thi đo lại thấy nhịp khác, DỪNG và báo.
2. Tài khoản cần canh là `real_order_account` trong `config/config.yaml` —
   đúng tài khoản mà `read_real_positions()` dùng. `main()` đã đọc file này
   sẵn cho `symbols`, dùng lại cùng một lần đọc.
3. Không cần cửa sổ thời gian riêng: `main()` đã chặn ngoài giờ giao dịch ở
   đầu hàm (dòng 141-147). 2C cũng không có cửa sổ riêng — theo đúng tiền lệ đó.
4. Mức cảnh báo **CRITICAL**, không phải WARN: bảng này nằm trên đường tiền
   thật ra thị trường, ngang 2A.

## Phạm vi phẫu thuật

ĐƯỢC sửa — chỉ hai file:
- `scripts/heartbeat_check.py`
- `tests/test_heartbeat_check.py`

KHÔNG được đụng: toàn bộ `trading/**`, các script khác, `config/`,
`docker-compose.yml`, `DEPLOYMENT.md`. Không refactor 2A/2B/2C. Không dọn code
cũ. Không xoá dead code có sẵn từ trước.

Dùng LẠI `Storage.read_position_sync_ts()` (`db.py:666-673`) — KHÔNG viết truy
vấn SQL mới. Đây là tiền lệ 2B đã dùng lại `Storage.load_ssi_token()`.

## Các bước — mỗi bước kèm cách kiểm chứng

1. Chạy `gitnexus_impact({target: "main", direction: "upstream"})` cho
   `scripts/heartbeat_check.py` và báo blast radius trước khi sửa.
   → kiểm chứng bằng: dán kết quả impact vào báo cáo.

2. Viết test TRƯỚC cho hàm thuần `position_sync_stale(sync_ts, now, stale_minutes)`,
   phủ 4 trường hợp: (a) mới đồng bộ → False; (b) quá ngưỡng → True;
   (c) `sync_ts=None` (chưa từng đồng bộ) → True và KHÔNG ném exception;
   (d) đúng ngay mốc ngưỡng → xác định rõ biên và khẳng định trong test.
   → kiểm chứng bằng: `uv run pytest tests/test_heartbeat_check.py -q` ĐỎ,
     dán output thật.

3. Viết hàm cho test xanh.
   → kiểm chứng bằng: cùng lệnh trên XANH, dán output thật.

4. Viết test cho phần nối vào `main()`: khi vị thế quá cũ thì có đúng một
   tin nhắn `[CRITICAL]` chứa tên tài khoản và số phút, và khi chưa từng đồng
   bộ thì có tin nhắn riêng KHÔNG dựng `now - sync_ts` (bài học FEE-ALARM-2
   Lỗi 1: chuông báo tuyệt đối không được ném exception đúng lúc cần nhất).
   → kiểm chứng bằng: test ĐỎ trước, XANH sau, dán cả hai output.

5. Kiểm chứng phá hoại: sửa tạm ngưỡng thành một giá trị vô lý (ví dụ 9999
   phút), chạy lại, xác nhận test 2(b) ĐỎ — chứng minh test thật sự bắt được,
   không phải xanh giả. Rồi HOÀN NGUYÊN.
   → kiểm chứng bằng: dán output đỏ của bước phá hoại và output xanh sau khi
     hoàn nguyên.

6. Toàn bộ suite + lint không hồi quy.
   → kiểm chứng bằng: `uv run pytest -m "not integration" -q` (nền hiện tại:
     **311 passed, 84 deselected**) và `uv run ruff check trading tests scripts`
     ("All checks passed!"). Dán cả hai.

7. Chạy `gitnexus_detect_changes()`.
   → kiểm chứng bằng: dán kết quả, xác nhận chỉ đúng 2 file trong phạm vi.

## Không được làm

- KHÔNG commit, KHÔNG push. Lead audit rồi mới commit.
- KHÔNG chạy backfill, KHÔNG gọi API SSI, KHÔNG bật `real_trading_enabled`.
- KHÔNG gửi Telegram thật khi test (dùng mock như các test 2A/2B/2C đang làm).
- Nếu phát hiện vấn đề ngoài phạm vi: BÁO CÁO, không tự sửa.
