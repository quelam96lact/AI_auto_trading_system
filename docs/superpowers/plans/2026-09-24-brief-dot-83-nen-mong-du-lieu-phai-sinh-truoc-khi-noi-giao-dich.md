# Brief đợt 83 — Nền móng dữ liệu phái sinh, bước bắt buộc trước khi nói tới giao dịch

Ngày giao: 24/09/2026.
Base: main `5d88abb`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao brief này KHÔNG phải brief giao dịch

Chủ dự án muốn tiến tới **giao dịch** hợp đồng phái sinh. Tôi nói thẳng con đường thật, không rút
ngắn giả tạo: từ chỗ đang đứng tới chỗ đặt lệnh còn **ba cửa**, và cửa đầu chưa mở.

| Cửa | Nội dung | Trạng thái |
|---|---|---|
| 1 | **Dữ liệu** dùng được: lưới nến đồng nhất + chuỗi liên tục qua các kỳ roll | **CHƯA** — brief này |
| 2 | **Chi phí** có nguồn: biểu phí thật, không phải placeholder | **CHƯA** — việc của chủ dự án, mục 4 |
| 3 | **Lợi thế** đo được: backtest có kết quả dương sau chi phí | **CHƯA** — đợt sau, sau cửa 1+2 |

Ba lý do cửa 1 đang đóng, đều là số tôi tự đo ở đợt 82:

1. **Dữ liệu không đồng nhất.** 928 nến của `41I1GA000`: 22 phiên có 49 nến (`13:00→14:25` rồi nhảy
   `14:45`, bắt đầu 09:00), riêng 22/09 và 23/09 có 55 nến (thêm `14:30/14:35/14:40` và
   `08:45/08:50/08:55`). Lưới 49 nến khớp quy ước ATC của VN — tôi đối chứng HPG ở cả ba phiên 21,
   22, 23/09 đều `14:25 → 14:45`, **không bao giờ** có 14:30–14:40. Mọi chỉ báo 5m tính xuyên qua
   ranh giới 22/09 là đang so hai thứ khác nhau.
2. **Lịch sử quá ngắn.** `41I1GA000` sống từ 21/08, mới 24 phiên. Hợp đồng phái sinh VN **roll mỗi
   tháng**, nên một hợp đồng đơn lẻ vĩnh viễn không bao giờ có đủ lịch sử để backtest. Cần **chuỗi
   liên tục nối qua nhiều kỳ**.
3. **Repo không có một dòng nào về nối chuỗi.** Tôi đã grep toàn bộ `trading/`:
   `derivative_backtest.py:18` ghi thẳng `# KHONG tu dong roll - xem spec`. Đây là phần phải làm mới.

**Không có ba thứ này thì mọi con số backtest phái sinh sẽ là số ảo.** Dự án đã có 4 phép đo âm độc
lập (crypto, VN regime-timing, VN technical 3 mã, VN technical 48 mã) — đừng thêm phép đo thứ 5 trên
dữ liệu hỏng rồi tưởng là tìm ra vàng.

---

## 1. Ràng buộc

- Được sửa/thêm: `trading/derivative_series.py` (**file mới**), `tests/test_derivative_series.py`
  (**file mới**), và **một** script `scripts/build_derivative_continuous_series.py` + test của nó.
- **Không** sửa `trading/derivative_backtest.py`, `derivative_position.py`, `derivative_risk.py`,
  `collector/`, `storage/db.py`, hai script spike. Không xoá file `.spike_*`.
- **TUYỆT ĐỐI KHÔNG** gọi method đặt lệnh nào. Tài khoản `0434228` chưa bao giờ nạp tiền/giao dịch.
- **Không ghi đè** nến hợp đồng gốc trong bảng `bars`. Chuỗi liên tục là **dữ liệu dẫn xuất**, phải
  nằm ở symbol riêng (xem Task 3) — nếu mất, phải dựng lại được từ nến gốc.
- **Không** `docker compose restart / stop / up / build`. Triển khai là việc của Claude.
- Không thêm dependency. Không commit, không push.
- Nền hiện tại: **761 passed**, ruff sạch.

---

## Task 1 — Lưới nến phái sinh: xác định bằng thực nghiệm, không bằng suy luận

Đợt 82 kết luận sai chỗ này (gọi 2 phiên lạ là "chuẩn", 22 phiên đúng là "thiếu"). Lần này đo tử tế.

1. **Lấy lại** dữ liệu 5m của `41I1GA000` cho hai phiên 21/09 (49 nến) và 23/09 (55 nến) từ API,
   **không đọc DB**. So với những gì đang có trong `bars`:
   - Nếu lần lấy lại cho 21/09 **vẫn** thiếu 14:30–14:40 → đó là dữ liệu SSI thật, không phải lỗi nạp.
   - Nếu lần lấy lại cho 21/09 **nay có** 14:30–14:40 → dữ liệu trong DB bị thiếu do thời điểm nạp,
     và toàn bộ 22 phiên cũ phải nạp lại.
   **Đây là phép thử phân định. Làm trước mọi thứ khác.**
2. Lấy thêm cùng hai phiên đó cho **một mã cổ phiếu** (ví dụ HPG) qua đúng đường API đó, để biết sự
   khác biệt là do *phái sinh vs cổ phiếu* hay do *phiên gần vs phiên xa*.
3. Kết luận: lưới nến đúng của phái sinh VN là gì, **và bạn biết điều đó nhờ bằng chứng nào**.
   Nếu hai phép thử trên không đủ để phân định, **nói rõ là chưa phân định được** và nêu cần thêm gì.
   **Tuyệt đối không dựng lại "lưới chuẩn" từ suy luận về giờ giao dịch rồi tuyên bố khớp** — đó đúng
   là lỗi đợt 82.

**Tiêu chí hoàn thành:** bảng so sánh nguyên văn (giờ nến từ API vs giờ nến trong DB) cho cả hai
phiên, cả hai loại mã, kèm kết luận có dẫn chứng.

---

## Task 2 — Có bao nhiêu lịch sử thật lấy được?

1. Liệt kê mọi hợp đồng **VN30** (`41I1*`) mà API còn trả về dữ liệu, kể cả đã đáo hạn — lùi càng xa
   càng tốt.
2. Với mỗi hợp đồng: số phiên, ngày đầu, ngày cuối có dữ liệu 5m.
3. Nạp nến 5m của tất cả các hợp đồng đó vào `bars` (mỗi hợp đồng giữ symbol riêng của nó — **không**
   trộn). Đã có sẵn `41I1G8000` (1.014 nến, 19/06→24/07) và `41I1GA000` (928 nến) — kiểm xem có nạp
   bù được phần thiếu của `41I1G8000` sau 24/07 không.
4. Báo cáo **tổng số phiên liên tục** có thể ghép được từ các hợp đồng này.

**Cấm:** không nội suy, không sinh nến giả, không lấy nến hợp đồng này vá cho hợp đồng khác. Nếu API
chỉ cho vài tháng, **báo đúng con số đó** — "lịch sử ngắn" là một kết luận hợp lệ và quan trọng.

---

## Task 3 — Chuỗi liên tục: quy tắc roll và back-adjust

Viết `trading/derivative_series.py` với các **hàm thuần**, test được không cần DB/mạng.

**Hai quyết định tôi chốt sẵn, không để bạn tự chọn:**

**(a) Quy tắc roll:** chuyển sang hợp đồng tháng kế tiếp **vào cuối phiên của ngày giao dịch cuối
cùng** của hợp đồng đang giữ (`lastTradingDate`). Lý do chọn quy tắc đơn giản này: nó xác định được
chỉ từ metadata hợp đồng, không cần dữ liệu khối lượng, nên **tái lập được** và không đổi khi dữ liệu
đổi. Đợt 82 đã đo: front-month chiếm 99,37% khối lượng, nên roll sớm hơn không đem lại gì.

**(b) Phương pháp back-adjust: HIỆU SỐ (panama), không phải tỷ lệ.** Lý do: lãi/lỗ phái sinh là
**tuyến tính theo điểm** — mỗi điểm đúng bằng `DERIVATIVE_CONTRACT_MULTIPLIER` = 100.000 VNĐ
(`derivative_position.py:22`, đặc tả công khai HNX). Điều chỉnh theo tỷ lệ sẽ làm sai lệch giá trị
tiền của một điểm, tức làm sai chính đại lượng mà chiến lược và quản trị rủi ro dùng. Cụ thể: tại mỗi
mốc roll, tính `gap = giá_hợp_đồng_mới − giá_hợp_đồng_cũ` tại nến cuối cùng **cả hai đều có**, rồi
**cộng dồn** `gap` vào toàn bộ dữ liệu quá khứ.

**Yêu cầu hàm:**
- `build_roll_schedule(contracts) -> list[(symbol, start, end)]` — lịch roll từ metadata hợp đồng.
- `stitch_continuous(bars_by_symbol, roll_schedule) -> list[Bar]` — chuỗi đã back-adjust bằng hiệu số.
- Chuỗi kết quả ghi vào `bars` dưới symbol riêng **`VN30F1M_CONT`**, và phải ghi kèm ở đâu đó (docstring
  hoặc research doc) **giá trị gap tại từng mốc roll**, để người sau dựng lại được.

**Kiểm chứng — test tính tay, không dùng chính code sinh kỳ vọng:**
1. Hai hợp đồng, roll một lần, gap = +5 điểm: toàn bộ nến của hợp đồng cũ phải được **cộng 5**, nến
   hợp đồng mới **không đổi**. Kiểm từng giá trị OHLC bằng số tính tay.
2. Ba hợp đồng, roll hai lần, gap +5 rồi −3: phần xa nhất phải cộng dồn **+2**. Đây là ca dễ sai nhất
   (cộng dồn, không phải cộng riêng lẻ) — bắt buộc có.
3. **Tính bất biến quan trọng nhất:** với mọi cặp nến liền nhau **trong cùng một hợp đồng**, hiệu giá
   trước và sau khi back-adjust phải **y nguyên**. Back-adjust chỉ được dịch mức, không được đổi biến
   động. Test bằng số cụ thể.
4. Ca không có nến chồng lấn tại mốc roll → phải báo lỗi rõ ràng, **không** âm thầm gap = 0.
5. **Kiểm thử phá hoại:** đổi cộng dồn thành cộng riêng lẻ (bỏ tích luỹ), xác nhận **đúng test số 2**
   đỏ. Rồi bỏ back-adjust hoàn toàn, xác nhận test 1 và 2 đỏ mà test 3 **vẫn xanh** (vì không dịch
   thì hiệu số nội bộ cũng không đổi) — nếu test 3 cũng đỏ thì nó đang kiểm sai thứ.

---

## 2. Không làm

- Không đặt lệnh, không gọi method giao dịch.
- Không backtest, không tính chỉ báo, không nghiên cứu chiến lược trong đợt này.
- Không sửa `derivative_backtest.py` / `derivative_position.py` / `derivative_risk.py` / `collector/`
  / `db.py` / script spike. Không xoá `.spike_*`.
- Không ghi đè nến hợp đồng gốc. Không nội suy, không sinh nến giả.
- Không restart/build container. Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: bảng so sánh giờ nến API vs DB cho 21/09 và 23/09, cả phái sinh và cổ phiếu; kết luận về
   lưới nến kèm dẫn chứng — hoặc nói rõ chưa phân định được.
2. Task 2: bảng hợp đồng `41I1*` + số phiên/ngày đầu/ngày cuối; tổng số phiên ghép được.
3. Task 3: kết quả 5 nhóm test (nguyên văn), gap tại từng mốc roll, và truy vấn `bars` cho
   `VN30F1M_CONT` sau khi ghi.
4. `uv run pytest -m "not integration" -q` (nền **761**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Việc của chủ dự án, KHÔNG giao agent

**Biểu phí phái sinh thật.** `derivative_position.py:13-16` tự ghi rõ
`DERIVATIVE_FEE_PER_CONTRACT = 8_250.0` là **"ước tính bậc thấp nhất... placeholder CHƯA xác nhận"**.
Phái sinh VN còn có phí quản lý vị thế qua đêm (VSD), phí giao dịch sở, và lãi ký quỹ — không có mục
nào trong đó ở trong code.

Tôi **không** giao agent đi tra biểu phí. Lý do cụ thể: memory dự án ghi lại rằng một `connector.py`
và "Task 31" từng được **bịa ra** nguyên xi, và rằng một con số phí không nguồn (`0.0015` thay vì
`0.0025`) từng **làm sai cả hai hard gate**. Biểu phí là loại số mà đoán sai thì mọi kết luận
lãi/lỗ sau đó đều vô giá trị — nó phải đến từ SSI/HNX/VSD qua tay bác, kèm nguồn.

Cửa 2 không mở được bằng agent. Trước khi có biểu phí có nguồn, tôi sẽ **không** viết brief backtest
phái sinh — vì kết quả sẽ không dùng được để quyết định gì.
