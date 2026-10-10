# Brief đợt 174 — Báo cáo hiệu suất tài khoản thật từ lịch sử lệnh SSI (chỉ đọc)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao

Ngày 09/10 chủ dự án hỏi cách cải thiện hiệu suất giao dịch. Claude ước tính chi phí giao dịch của tài khoản `0434226` khoảng **8% NAV/năm** (29/08 → 08/10: 505,5 triệu giá trị mua+bán, NAV trung bình 191 triệu). Ước tính đó **dựng lại giao dịch từ thay đổi vị thế hằng ngày**: ngày lệch ±1 phiên, giá dùng là giá đóng cửa thay vì giá khớp, không biết lệnh nào khớp một phần.

SDK có `AsyncPortfolioService.get_historical_orders(account_no, from_date, to_date)` (repo đã dùng ở `trading/collector/account_sync.py`, phần đối soát lệnh). Mỗi `Order` có `symbol`, `side`, `filled_quantity`, `avg_price`, `input_time`, `status`. Đủ để tính **chính xác** giá trị khớp, phí, thuế và lãi/lỗ từng vòng.

**Đây không phải giả thuyết chiến lược**, nên không tính ngân sách spec mục F. Báo cáo này đo những gì đã xảy ra.

## 1. Việc làm

### Phần A — Thăm dò (chỉ đọc, một lần)
1. Gọi `get_historical_orders` cho `0434226`, từ 2026-08-01 tới hôm nay, qua đường xác thực sẵn có của repo. **Đi hết mọi trang**: SDK có `page`/`size`; kiểm `total_orders` khớp số lệnh lấy về.
2. Báo:
   - tổng số lệnh, số lệnh theo `status`;
   - ngày lệnh sớm nhất và muộn nhất;
   - lịch sử lùi được bao xa: thử thêm `from_date` = 2026-01-01 và 2025-01-01; ghi số lệnh hoặc lỗi.
3. **Đối chiếu với vị thế:** Claude đã thấy từ `account_position_snapshot` các thay đổi sau (ngày theo snapshot, có thể lệch ±1 phiên): CTD +500 (khoảng 05/10), CTD +300 (khoảng 06/10), CTD +400 (khoảng 07/10), VCB −1.000 và TCX −400 (khoảng 07/10), SSI −1.540 (khoảng 03–06/10). Lịch sử lệnh có những lệnh này không?
   - Câu hỏi then chốt: **lệnh chủ dự án đặt tay trên app SSI có nằm trong lịch sử API không.** Có thì tiếp Phần B. Không thì dừng và báo.
   → **kiểm chứng bằng:** bảng thăm dò trong báo cáo cho Claude. In mã, phía, khối lượng khớp, giá khớp, ngày. **Không in** số tài khoản khác, token hay khóa.

### Phần B — Script báo cáo (chỉ đọc, chỉ in ra màn hình)
4. `scripts/report_real_account_performance.py --account 0434226 --from YYYY-MM-DD [--to YYYY-MM-DD]`:
   - chỉ dùng lệnh có `filled_quantity > 0`; giá trị khớp = `filled_quantity × avg_price`;
   - **phí** = `FEE_RATE × giá trị khớp` mỗi chiều; **thuế bán** = `SELL_TAX_RATE × giá trị khớp` của lệnh bán. **Import** từ `trading/paper_broker.py`, không gõ lại số;
   - **vòng mua-bán** theo FIFO từng mã. Mỗi vòng: ngày vào, ngày ra, số ngày giữ, lãi/lỗ ròng (sau phí, thuế), lãi/lỗ % trên vốn vào. Vị thế còn mở cuối kỳ: liệt kê riêng, **không** tính lãi/lỗ;
   - bán vượt số đã mua trong kỳ (cổ phiếu mua trước `--from`) → báo riêng "bán không có giá vốn trong kỳ", không đoán giá vốn.
5. In ra:
   - (a) tổng giá trị mua, bán; tổng phí, thuế;
   - (b) số vòng, tỷ lệ vòng lãi, lãi/lỗ ròng tổng và trung bình mỗi vòng, trung vị số ngày giữ;
   - (c) phí + thuế / tổng lãi/lỗ gộp (chi phí ăn bao nhiêu phần lợi nhuận);
   - (d) bảng theo tháng.

   **Không** tính lợi nhuận theo thời gian hay NAV: thiếu dữ liệu nạp/rút, và NAV còn lỗi T+2 (đợt 167).

## 2. Phạm vi
- **Được thêm:** `scripts/report_real_account_performance.py`, `tests/test_report_real_account_performance.py`.
- **Không sửa:** mọi file khác. **Không ghi DB, không ghi file** ngoài stdout. Không gọi API đặt/hủy lệnh hay API nào có tác dụng ghi. Không chạy `scripts/sched.sh`.
- Chạy trực tiếp `python scripts/...` phải import được `scripts.*` (khuôn `_ROOT`/`sys.path` của `scripts/screen_ml_cross_section.py`).
- GitNexus: gọi `gitnexus ...` hoặc `node .gitnexus/run.cjs ...` (thêm `-r AI_auto_trading_system`). **Không dùng `npx gitnexus`**: ngày 10/10, `npx` kéo bản khác và làm hỏng index. Chạy `context` cho `get_historical_orders` (đường gọi trong `account_sync.py`) trước khi viết; `detect-changes` sau khi xong.

## 3. Kiểm chứng (TDD; lệnh giả, không gọi mạng)
1. Mua 1.000 @ 10.000 rồi bán 1.000 @ 11.000 → một vòng; lãi ròng tính tay đúng tới đồng (gồm phí hai chiều và thuế bán).
2. FIFO: mua 500 @ 10.000, mua 500 @ 12.000, bán 700 @ 13.000 → vòng dùng 500 lô đầu + 200 lô sau; còn mở 300 @ 12.000.
3. Lệnh `filled_quantity = 0` hoặc trạng thái hủy không khớp → bị bỏ.
4. Khớp một phần: `quantity 1.000`, `filled_quantity 400` → chỉ tính 400.
5. Bán khi chưa có giá vốn trong kỳ → vào mục riêng, không vào lãi/lỗ.
6. Phân trang: client giả trả 3 trang → lấy đủ, số lệnh khớp `total_orders`.
7. Không có lời gọi ghi nào (spy trên client và `Storage`).

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ thuế bán → test 1 đỏ.
- Đổi FIFO thành LIFO → test 2 đỏ.
- Chỉ lấy trang đầu → test 6 đỏ.

```
uv run pytest tests/test_report_real_account_performance.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- Phần A: bảng thăm dò, gồm câu trả lời có/không cho câu hỏi "lệnh đặt tay có trong lịch sử API".
- Phần B (chỉ khi A trả lời "có"): 7 test xanh, ba bước phá hoại đỏ đúng test, bộ test không có test mới đỏ (dán số trước/sau), ruff sạch, `detect-changes` chỉ gồm hai file mới.
- Chạy thật một lần cho `0434226` từ 2026-08-01 và dán **output đầy đủ** vào báo cáo cho Claude.

## 5. Báo cáo cho Claude
Bảng thăm dò, output pytest/ruff, bảng phá hoại, `detect-changes`, output chạy thật, và mọi chỗ phải tự diễn giải (ví dụ múi giờ của `input_time`, cách hiểu từng `status`).
