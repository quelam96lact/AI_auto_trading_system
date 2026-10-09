# Brief đợt 170, vòng 2 — Lập danh sách mã đã chết CHỈ từ SSI (bỏ nguồn web)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao vòng 1 không được nhận

Claude kiểm ngẫu nhiên 2 trong 24 URL nguồn của vòng 1, và **cả hai đều sai**:
- `vietstock.vn/2022/08/ros-chinh-thuc-bi-huy-niem-yet-tu-0509-830-994324.htm` là bài về BCTC quý 4/2020 của SVI, không liên quan ROS.
- `cafef.vn/hvg-bi-huy-niem-yet-bat-buoc-tren-hose-tu-5-8-20200707173204895.chn` trả 404.

Thêm 3 mã (PTM, SLC, CNH) chỉ có `https://hnx.vn` (trang chủ). Vì vậy mọi cột nguồn, ngày hủy và lý do hủy của vòng 1 bị coi là **không kiểm chứng được**, và script nhúng các URL đó **không được commit**. Brief vòng 1 cấm "tự nhớ hay đoán"; URL không trỏ đúng bài là vi phạm điều đó.

**Phần vòng 1 vẫn có giá trị** (Claude kiểm lại trên DB):
- 11/24 mã (ATA, CDO, PTM, ORS, DID, RIC, FTM, PXI, PXS, VIE, APP) **đã có sẵn** trong `bars_daily`. Chúng bị hủy ở HOSE/HNX nhưng chuyển sang UPCoM và vẫn giao dịch, nên không phải nguồn của thiên lệch sống sót.
- 13/24 mã **thiếu** trong `bars_daily`: BGM, CNH, GTN, HVG, KDF, KHB, KSA, MNC, PME, ROS, SDE, SDI, SLC. **SSI trả nến lịch sử cho cả 13.**
- Tiêu chí "≥ 100 nến năm cuối" của brief vòng 1 đo mức giao dịch, không đo SSI có dữ liệu hay không. Đó là lỗi của Claude; vòng 2 bỏ tiêu chí này.
- Mục §1.4 vòng 1 chọn THN, nhưng THN có nến cuối 27/07/2026, không phải trước 30/06/2022. Claude kiểm lại: hiện **không** mã nào trong `bars_daily` có nến cuối trước 30/06/2022.

## 1. Cách mới: dò mã bằng chính SSI, không dùng nguồn ngoài
Ý tưởng: SSI trả nến cho mã đã chết nếu hỏi đúng tên. Vậy hỏi **mọi** mã 3 chữ cái, rồi lấy những mã có nến trong 2016–2022 nhưng không có trong `bars_daily`.

1. **Sửa `scripts/probe_ssi_delisted_coverage.py`:** xóa toàn bộ danh sách 24 mã và URL nhúng sẵn. Không còn dòng `http` nào trong file.
2. **Không gian dò:** mọi mã gồm đúng 3 chữ cái `A–Z`, tức 26³ = 17.576 mã.
   - Mã có chữ số (ví dụ L14, VC3, D2D) **không** dò ở vòng này. Ghi là điểm mù đã biết, và đếm xem `bars_daily` hiện có bao nhiêu mã cổ phiếu dạng đó để biết điểm mù lớn cỡ nào.
3. **Mỗi mã một lần gọi** `daily_ohlc(mã, 2016-01-01, 2022-12-31)`, đúng đường gọi repo đang dùng. API trả tối đa 1000 nến **mới nhất** trong khung. Đủ để biết mã có tồn tại trong 2016–2022 không, và với mã chết trước 2022 thì lấy được nến cuối.
   - Ghi cho mỗi mã có nến: số nến, ngày đầu, ngày cuối (trong khung).
4. **Nhịp gọi:** tối đa **1 lần gọi mỗi giây**. Toàn bộ khoảng 5 giờ.
   - **Phải chạy tiếp được sau khi bị ngắt:** ghi tiến độ ra file ngoài repo, ví dụ `data/probe_delisted/` (thư mục `data/` không vào git; kiểm `.gitignore`). Chạy lại thì bỏ qua mã đã có kết quả.
   - Token sống khoảng 15 phút: làm mới theo cách repo đang làm. Lỗi 429 thì lùi lại rồi thử tiếp mã đó, không bỏ qua.
5. **Agent chỉ chạy thử khối `A**`** (676 mã, khoảng 11 phút) **ngoài giờ phiên** (sau 15:00) để kiểm đường ống. **Claude chạy toàn bộ** qua đêm.
6. **Báo cáo** (script in ra, từ file tiến độ):
   - S = các mã có ≥ 1 nến trong 2016–2022.
   - **Độ nhạy (đối chứng dương):** mọi mã 3 chữ cái đang có trong `bars_daily` và có nến trong 2016–2022 phải nằm trong S. Báo số lọt/tổng. Lọt > 0 thì liệt kê.
   - **Mã thiếu** = S trừ các mã trong `bars_daily`. Mỗi mã: số nến, ngày đầu, ngày cuối. Chia hai nhóm: ngày cuối trước 30/06/2022 (chết trong IS) và còn lại.
   - Đối chiếu 13 mã ở §0: mã nào **không** nằm trong "mã thiếu" thì liệt kê và giải thích.

## 2. Phạm vi
- **Được sửa/thêm:** `scripts/probe_ssi_delisted_coverage.py`, `tests/test_probe_ssi_delisted_coverage.py`. Không file nào khác.
- **Không ghi DB.** Không chạy `backfill_universe.py` hay `sched.sh`. Không gọi API giao dịch. **Không** dùng nguồn web nào.
- Chạy thật **chỉ ngoài giờ phiên** (sau 15:00 hoặc trước 08:45), để không tranh giới hạn tần suất với collector.
- GitNexus: chạy `npx gitnexus analyze` trước; `detect_changes` sau khi xong.

## 3. Kiểm chứng (client giả, không gọi mạng)
1. Sinh đúng 17.576 mã, không trùng, đúng thứ tự.
2. Chạy tiếp: file tiến độ có sẵn 100 mã → chỉ gọi API cho các mã còn lại.
3. Lỗi 429 cho một mã → thử lại mã đó, kết quả cuối có mã đó.
4. Tính "mã thiếu" và độ nhạy đúng trên tập giả dựng tay.
5. Nhịp gọi: đồng hồ giả, 10 lần gọi không xảy ra nhanh hơn 1 lần mỗi giây.
6. Không có lời gọi ghi DB nào (spy).
7. File script không chứa chuỗi `http`.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ đọc file tiến độ → test 2 đỏ.
- Bỏ thử lại khi 429 → test 3 đỏ.
- Bỏ giới hạn nhịp → test 5 đỏ.

```
uv run pytest tests/test_probe_ssi_delisted_coverage.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 7 test xanh, ba bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ test không có test mới đỏ, ruff sạch, `detect_changes` chỉ gồm hai file.
- Đã chạy thử khối `A**` ngoài giờ phiên và dán output nguyên văn: số mã có nến, độ nhạy trong khối A, danh sách mã thiếu bắt đầu bằng A.
- Lệnh chạy toàn bộ cho Claude, kèm thời gian ước tính.

## 5. Báo cáo cho Claude
Output pytest/ruff, bảng phá hoại, `detect_changes`, output chạy thử khối A, số mã cổ phiếu có chữ số trong `bars_daily`, và mọi chỗ phải tự diễn giải.
