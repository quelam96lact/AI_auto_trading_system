# Brief đợt 242: CONFIRM-1 bắt số dư "bụi" (account_balance ≈ 0 nhưng khác 0)

- **Ngày:** 15/11/2026. **Làm sau đợt 241.**
- **Lỗi:** từ 02/11, đêm khuya / cuối tuần SSI trả tài khoản margin `0434226` với `accountBalance ∈ {-165, -64, -55}`, `withdrawable = 0`, `totalDebt = 0`, danh mục giữ nguyên. CONFIRM-1 (`trading/collector/account_sync.py::_sync_balance`, đợt 124/164) chỉ bắt khi `accountBalance == 0.0` đúng tuyệt đối nên lọt; từ đợt 203 NAV dùng `account_balance` → NAV ghi 129,2tr thay vì ~204,8tr (13/11 23:20 → nay). Log collector từ 01/11 có **0** dòng CONFIRM-1.
- **Số đo (Researcher, DB `trading`, từ 01/10):** `0434226` có 606 dòng `|ab| < 1000 ∧ wd = 0 ∧ debt = 0`, **0 dòng** trong 09:00–15:30 ngày GD; mỗi đợt hồi về đúng số dư cũ (chênh = lãi/phí, hoặc tiền bán 1.000 BSR đợt 03→09/11). `0434221` có 1.902 dòng `ab = 0` **thật** (tài khoản không tiền, cả trong phiên) → phải ghi bình thường như hiện nay.

## 1. Sửa (chỉ `_sync_balance`)

1. Thêm hằng `BALANCE_DUST_VND = 1000.0` cạnh `CONFIRM_WINDOW_*`.
2. Điều kiện nghi ngờ đổi từ `acct_bal == 0.0 and total_debt == 0.0 and withdrawable == 0.0` thành `abs(acct_bal) < BALANCE_DUST_VND and total_debt == 0.0 and withdrawable == 0.0`.
3. "Dòng trước khác 0" mở rộng: nghi ngờ khi dòng trước có `withdrawable != 0` **hoặc** `total_debt != 0` (như cũ) **hoặc** `abs(account_balance trước) >= BALANCE_DUST_VND`. Lấy `account_balance` trước bằng `storage.read_balance_for_nav(account_no)` (đã có, phần tử [0]); không thêm hàm storage mới.
4. Phần còn lại giữ nguyên: hoãn nhịp đầu (WARN), ngoài cửa sổ giao dịch giữ chờ (INFO), xác nhận ở nhịp sau trong 09:00–15:30 ngày GD.

## 2. Phạm vi file

- **Sửa:** `trading/collector/account_sync.py` (chỉ `_sync_balance` + hằng), `tests/test_account_sync.py` (thêm test; **không xoá/sửa test cũ** — toàn bộ `test_b*`, `test_confirm1_*` phải giữ nguyên và xanh).
- **Không đụng:** `_sync_positions`, `_sync_nav`, `trading/storage/`, dữ liệu DB (không xoá dòng lịch sử sai — là quyết định của chủ dự án, ngoài phạm vi).
- Builder KHÔNG: commit/push, docker/rebuild collector, truy vấn DB, gọi API, `sched.sh`, `npx`.

## 3. Tiêu chí hoàn thành

1. Kiểm GitNexus `impact _sync_balance --direction upstream` trước khi sửa; báo risk.
2. Test mới (FakeStorage như các test hiện có), mỗi test nêu số liệu thật nguồn:
   - (a) **Tái hiện 13/11 23:20:** dòng trước `ab=75.614.394, wd=75.614.394, debt=0`; SSI trả `ab=-165, wd=0, debt=0` lúc 23:20 thứ Sáu → không ghi; nhịp 23:25 → không ghi; nhịp CN 15/11 13:47 (không phải ngày GD) → không ghi; nhịp thứ Hai 16/11 09:00 vẫn `-165` → ghi (xác nhận).
   - (b) Hồi phục: sau (a) nhịp 05:06 trả `ab=75.614.394` → ghi, cờ chờ xoá.
   - (c) `0434221` thật: dòng trước `ab=0, wd=0, debt=0`, SSI trả `ab=0` lúc 10:00 và lúc 23:00 → ghi ngay cả hai.
   - (d) Ngưỡng: `ab=-999` bị bắt; `ab=-1000` và `ab=1000` ghi bình thường (biên `<` nghiêm ngặt).
   - (e) Dòng trước chỉ có `ab` lớn (wd=0, debt=0, ab=50.000.000) → `ab=-64` bị hoãn (nhánh mới của bước 1.3).
3. **Phá thử:** đổi tạm điều kiện về `== 0.0` → test (a) phải đỏ; ghi output đỏ vào báo cáo rồi hoàn nguyên.
4. `uv run pytest tests/test_account_sync.py -v` xanh; `uv run pytest -m "not integration" -q` xanh; `uv run ruff check trading tests` sạch.
5. `gitnexus detect_changes` chỉ thấy `_sync_balance` (+ hằng) và test.
6. Báo cáo: diff, danh sách `def test_*` mới, output thô các bước 3–5.

## 4. Triển khai (Lead, không phải Builder)

Sau audit + commit: rebuild collector **sau 15:00 ngày GD**. Kiểm hai đêm: không dòng `account_nav_snapshot` nào của `0434226` < 150tr khi danh mục không đổi, và log có WARN `CONFIRM-1` ở mốc SSI trả bụi.
