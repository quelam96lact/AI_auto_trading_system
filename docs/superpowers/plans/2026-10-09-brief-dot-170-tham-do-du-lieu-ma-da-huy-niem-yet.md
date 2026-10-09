# Brief đợt 170 — Thăm dò: SSI có giá lịch sử của mã đã hủy niêm yết không (chỉ đọc, không ghi DB)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao

Đợt 169 phát hiện `bars_daily` gần như chỉ có mã còn sống: **1/1.208** mã cổ phiếu có nến cuối trước 30/06/2022. Gốc rễ nằm ở cách dựng universe. Danh sách mã lấy từ `get_securities_info_by_board` (mã **đang** niêm yết, xem `ssi-fastconnect` facts), rồi `scripts/backfill_universe.py` nạp giá ngày cho đúng các mã đó. Mã đã hủy niêm yết chưa bao giờ được hỏi tới.

Hệ quả: mọi phép đo chọn cổ phiếu (đợt 99–102, SEPA, 169) đều bị thổi phồng so với ETF. **Muốn cải thiện chiến lược cổ phiếu, việc đầu tiên là dữ liệu đúng.** Đây là việc làm sạch dữ liệu, không phải giả thuyết chiến lược, nên không tính vào ngân sách spec mục F.

**Câu hỏi duy nhất của đợt này:** API dữ liệu SSI có trả nến ngày lịch sử cho mã đã hủy niêm yết không, và đủ tới mức nào? **Chưa** nạp gì vào DB.

## 1. Việc làm
1. **Danh sách mã đã hủy niêm yết 2017–2022, có nguồn.** Lập danh sách **ít nhất 20** mã cổ phiếu đã hủy niêm yết trên HOSE, HNX hoặc UPCoM trong 2017–2022.
   - Mỗi mã ghi: sàn, ngày hủy, lý do nếu có, và **URL nguồn**. Ưu tiên thông báo chính thức của HOSE/HNX/VSD; nguồn báo tài chính chỉ dùng khi không có, và ghi rõ.
   - **Không được tự nhớ hay đoán mã.** Mã nào không có URL thì không đưa vào.
   - Loại trừ: mã chỉ **chuyển sàn** (ví dụ HOSE → UPCoM vẫn giao dịch) và mã đổi tên/sáp nhập đổi mã. Liệt kê riêng các mã này nếu gặp, vì chúng là trường hợp khác.
   → **kiểm chứng bằng:** bảng trong báo cáo, mỗi dòng có URL.
2. **Hỏi SSI cho từng mã** bằng đúng đường gọi giá ngày repo đang dùng (`trading/collector/backfill.py`, `daily_ohlc`). Khung ngày: 366 ngày kết thúc tại ngày hủy niêm yết (giới hạn 1000 dòng mỗi lần gọi, xem facts SSI). Ghi số nến trả về, ngày đầu, ngày cuối.
   - Cùng lúc, kiểm `get_securities_info_by_board` cho HOSE/HNX/UPCOM: mã đó có xuất hiện không.
   → **kiểm chứng bằng:** bảng thứ hai, một dòng mỗi mã.
3. **Đối chứng dương:** cùng cách gọi cho 3 mã đang niêm yết (VCB, HPG, FPT) trên khung 2021, phải ra khoảng 250 nến. Không ra thì đường gọi đang hỏng; dừng và báo trước khi kết luận về mã đã hủy.
4. **Một mã của chính DB:** tìm mã duy nhất trong `bars_daily` có nến cuối trước 30/06/2022 (chỉ đọc). Ghi nó là mã gì, có nằm trong danh sách hủy niêm yết không, và dữ liệu đến từ đâu nếu tra được trong `git log`.

## 2. Phạm vi
- **Được thêm:** `scripts/probe_ssi_delisted_coverage.py` (chỉ đọc API SSI và DB, in kết quả, không ghi gì), `tests/test_probe_ssi_delisted_coverage.py`. Test cần nhắc tên script để qua quy ước `scripts/` (đợt 159).
- **Không sửa:** mọi file khác. **Không ghi DB.** Không chạy `scripts/backfill_universe.py` hay `scripts/sched.sh`. Không gọi API giao dịch.
- Gọi API chậm: tối đa 1 lần gọi mỗi giây (lỗi "Rate limit exceeded" từng xuất hiện 08/10). Token sống khoảng 15 phút; làm mới theo cách repo đang làm.
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `context` cho `daily_ohlc` và `get_securities_info_by_board` trước khi viết; `detect_changes` sau khi xong.

## 3. Kiểm chứng
Test không gọi mạng; dùng client giả.
1. Mã có nến → bảng ghi đúng số nến, ngày đầu, ngày cuối.
2. Mã trả 0 nến → ghi "0", không ném lỗi, không dừng cả vòng.
3. API ném lỗi (giả lập 429/401) cho một mã → ghi lỗi cho mã đó, các mã khác vẫn chạy.
4. Script không gọi bất kỳ hàm ghi DB nào (giả lập `Storage` không có phương thức ghi, hoặc kiểm bằng spy).

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ bắt lỗi theo từng mã → test 3 đỏ.
- Cho script gọi `write_daily` → test 4 đỏ.

```
uv run pytest tests/test_probe_ssi_delisted_coverage.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- Test xanh, hai bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ test không có test mới đỏ (mốc 09/10: `1941` test tổng); ruff sạch; `detect_changes` chỉ gồm hai file mới.
- Đã chạy thăm dò thật **một lần** và báo cáo có đủ: bảng §1.1 (có URL), bảng §1.2, đối chứng dương §1.3, kết quả §1.4.
- **Tỷ lệ phủ:** số mã đã hủy có ≥ 100 nến ngày trong năm cuối, trên tổng số mã đã hủy trong danh sách.

## 5. Quy tắc đọc kết quả (chốt trước)
- **Phủ ≥ 80%** → Claude soạn brief tiếp: nạp các mã đã hủy vào `bars_daily` có đánh dấu, rồi đo lại EW 2017–2022 có và không có chúng để biết thiên lệch lớn bao nhiêu.
- **Phủ < 80%** → ghi "SSI không đủ dữ liệu mã đã hủy niêm yết". Mọi phép đo chọn cổ phiếu sau này phải mang cảnh báo thiên lệch sống sót và chỉ so với EW cùng universe. Claude cân nhắc nguồn khác (phải kiểm điều khoản, xem bộ nhớ "nguồn dữ liệu ngoài và điều khoản").

## 6. Báo cáo cho Claude
1. Hai bảng §1.1, §1.2, đối chứng dương, kết quả §1.4, tỷ lệ phủ.
2. Output pytest/ruff, bảng phá hoại, `detect_changes`.
3. Lệnh đã chạy và output thăm dò nguyên văn (không in token hay khóa).
4. Mọi chỗ phải tự diễn giải; không im lặng chọn.
