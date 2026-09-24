# Brief đợt 82 — Xác định hợp đồng phái sinh VN khối lượng lớn nhất, bằng số đo chứ không bằng quan sát

Ngày giao: 24/09/2026.
Base: main `41acd82`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Yêu cầu của chủ dự án và tình trạng thật của repo

Chủ dự án chốt phạm vi: **phái sinh VN chỉ nghiên cứu hợp đồng có khối lượng giao dịch lớn nhất.**
Đây là brief **bước 1** — xác định *hợp đồng nào* và *lấy dữ liệu của nó*. Nghiên cứu chiến lược là
đợt sau, **không** nằm trong brief này.

Tôi đã tự đọc repo trước khi giao. Phân hệ phái sinh **đã tồn tại khá đầy đủ**, đừng viết lại:

- `trading/derivative_position.py`, `derivative_risk.py`, `derivative_backtest.py`,
  `collector/derivative_sync.py`; ba bảng `derivative_{balance,margin,position}_snapshot`.
- `scripts/spike_ssi_sdk_derivative_account.py` → sinh
  `scripts/.spike_derivative_contract_symbol.json` (**mã hợp đồng thật, không hardcode**).
- `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` → đọc file đó, gọi `get_ohlc_1minute()`.
  **Cả hai script này TUYỆT ĐỐI KHÔNG ĐƯỢC XOÁ** (xem `scripts/README.md:14`).

**Ba sự thật làm nên brief này:**

1. `trading/derivative_backtest.py:19` ghim cứng `DERIVATIVE_SYMBOL = "41I1G8000"`. Hợp đồng này
   **đã đáo hạn 20/08/2026** — hơn một tháng trước. Spec
   `docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md:70-71` đã **chủ động
   hoãn** việc roll và ghi rõ "khi hợp đồng gần đáo hạn (2026-08-20), mã front-month kế tiếp phải
   được cập nhật". Hạn đó đã trôi qua mà không ai cập nhật.
2. Dữ liệu nến 5 phút trong bảng `bars` cho `41I1G8000` chỉ có **1.014 nến, 19/06 → 24/07**. Không
   có nến nào cho hợp đồng đang sống hiện nay. **Không có dữ liệu thì không nghiên cứu được gì.**
3. Danh sách 8 mã ứng viên trong `.spike_derivative_contract_symbol.json` là **chụp ngày 26/07**, và
   trong đó **hai mã đã đáo hạn** (`...G8000` hết 20/08, `...G9000` hết 17/09). Mọi trường
   `openInterest` và `settlementPrice` đều **null** — nghĩa là **API không trả về OI/khối lượng qua
   đường này**.

**Cơ sở duy nhất hiện có cho câu "hợp đồng nào lớn nhất"** là một bảng OI **chép tay từ UI SSI ngày
26/07**, ở `scripts/spike_ssi_sdk_derivative_account.py:38-47`:

```
41I1G8000: 39.352   41I1G9000: 1.140   41I1GC000: 843   41I1H3000: 36
41I2G8000:     68   41I2G9000:    19   41I2GC000:  42   41I2H3000:  6
```

Số này **gợi ý rất mạnh** rằng front-month VN30 áp đảo (39.352 so với 1.140 — gấp ~34 lần). Nhưng
nó là **quan sát mắt trên UI, không phải số đo tái lập được**, và đã cũ 2 tháng. Việc của đợt này là
**biến nó thành số đo**.

---

## 1. Ràng buộc

- Được thêm mới: **một** script `scripts/measure_derivative_contract_volume.py` + test của nó.
- **Không** sửa `trading/derivative_backtest.py` (kể cả để bỏ mã ghim cứng đã hết hạn — xem mục 4).
- **Không** sửa `trading/collector/`, **không** sửa `trading/storage/db.py`, **không** sửa hai script
  spike đã có, **không** xoá bất kỳ file `.spike_*`.
- **TUYỆT ĐỐI KHÔNG** gọi bất kỳ method đặt lệnh nào của SSI SDK. Tài khoản phái sinh `0434228`
  chưa bao giờ được nạp tiền và chưa bao giờ giao dịch — giữ đúng như vậy.
- **Không** ghi vào ba bảng `derivative_*_snapshot`.
- **Không** `docker compose restart / stop / up / build` bất kỳ service nào. Phiên 24/09 đang chạy,
  engine đang giữ vị thế IJC 400 / AAA 400. Việc triển khai là của Claude, sau 15:00.
- Không thêm dependency. Không commit, không push.
- Nền hiện tại: **755 passed**, ruff sạch.

---

## Task 1 — Danh sách hợp đồng VN30 đang sống **hôm nay**

Danh sách lưu trong `.spike_derivative_contract_symbol.json` đã cũ và có mã hết hạn. Lấy danh sách
tươi.

1. Chạy lại `scripts/spike_ssi_sdk_derivative_account.py` **hoặc** viết phần đọc trong script mới —
   tuỳ bạn, nhưng **nói rõ đã chọn cách nào và vì sao**. Nếu chạy lại script cũ, nó sẽ ghi đè file
   `.spike_*`: **sao lưu bản cũ trước** (đổi tên thêm hậu tố `.20260726`), vì bản cũ là bằng chứng
   lịch sử của bảng OI 26/07.
2. Với mỗi mã trả về, ghi lại: `symbol`, `firstTradingDate`, `lastTradingDate`.
3. Lọc ra các mã **còn sống tại 24/09/2026** (`lastTradingDate >= 2026-09-24`).
4. Nêu rõ **mã nào là front-month** theo định nghĩa: `lastTradingDate` gần nhất trong tương lai.

**Điều tôi chưa biết và bạn phải trả lời bằng bằng chứng, không suy đoán:** tiền tố `41I1` và `41I2`
khác nhau ở cái gì (hai chỉ số cơ sở khác nhau? hai quy mô hợp đồng khác nhau?). Nếu API không nói,
**ghi là "không xác định được từ API"** — đừng đoán từ tên mã.

**Tiêu chí hoàn thành:** bảng đầy đủ các mã kèm ngày giao dịch cuối, và danh sách mã còn sống.

---

## Task 2 — Đo khối lượng thật, xếp hạng, xác nhận hay bác bỏ giả thuyết front-month

Đây là phần cốt lõi. Viết `scripts/measure_derivative_contract_volume.py`.

1. Với **mỗi mã còn sống** ở Task 1, lấy dữ liệu OHLC **có trường khối lượng** cho **20 phiên giao
   dịch gần nhất**. Dùng lại đúng đường gọi SSI mà `trading/collector/backfill.py` đang dùng cho nến
   ngày — **không tự phát minh endpoint mới**. Báo cáo ghi rõ đã gọi endpoint/method nào.
2. Tính cho từng mã: **tổng khối lượng**, khối lượng trung vị/phiên, và **tỷ trọng %** trên tổng
   khối lượng của tất cả các mã còn sống.
3. In bảng xếp hạng giảm dần theo tổng khối lượng.
4. Kết luận **một dòng**: mã nào có khối lượng lớn nhất, và nó chiếm bao nhiêu %.

**Đối chiếu bắt buộc:** so kết quả với bảng OI chép tay 26/07 ở
`spike_ssi_sdk_derivative_account.py:38-47`. Thứ tự có khớp không? Nếu **không** khớp, đó là phát
hiện quan trọng — nói thẳng, đừng làm nhẹ đi để cho "khớp với kỳ vọng của Claude".

**Tiêu chí hoàn thành + test:** ≥3 test đơn vị cho phần *tính toán* (tổng, trung vị, tỷ trọng, xếp
hạng), dữ liệu dựng tay và kết quả **tính tay** — không dùng chính script sinh ra kỳ vọng. Tách hàm
tính thuần khỏi phần gọi mạng để test được mà không cần SSI.

**Không làm:** không nghiên cứu chiến lược, không tính chỉ báo, không backtest. Chỉ đo khối lượng.

---

## Task 3 — Nạp nến 5 phút cho hợp đồng thắng, để đợt sau có dữ liệu

Chỉ làm **sau khi** Task 2 đã chỉ ra mã thắng, và **chỉ cho đúng một mã đó** — đúng phạm vi chủ dự
án đã chốt. Không nạp cho F2M/F1Q/F2Q.

1. Nạp nến 5 phút của mã đó vào bảng `bars` cho toàn bộ khoảng thời gian API cho phép, dùng lại
   đường backfill có sẵn.
2. Sau khi nạp, truy vấn và dán: `symbol`, số nến, ngày đầu, ngày cuối.
3. Kiểm tính hợp lý: số nến mỗi phiên có gần mức kỳ vọng của phiên phái sinh VN không? **Lưu ý phiên
   phái sinh KHÁC phiên cổ phiếu** (phái sinh có phiên ATC và giờ khác) — nếu bạn không chắc lưới
   nến chuẩn của phái sinh là gì, **nói là chưa chắc**, đừng tự dựng con số kỳ vọng rồi kết luận
   "khớp".

**Nếu API không cho lấy đủ lịch sử:** báo lại số liệu thật lấy được và dừng. Không bù bằng dữ liệu
suy diễn, không nội suy, không lấy nến của hợp đồng đã đáo hạn để "vá" vào.

---

## 2. Không làm

- Không đặt lệnh, không gọi method giao dịch nào.
- Không sửa `derivative_backtest.py`, `collector/`, `db.py`, hai script spike.
- Không xoá file `.spike_*` nào (sao lưu trước nếu bị ghi đè).
- Không nghiên cứu chiến lược, không backtest trong đợt này.
- Không nạp dữ liệu cho hợp đồng không phải mã thắng.
- Không restart/build container. Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: bảng mã + ngày giao dịch cuối, danh sách mã còn sống, mã front-month. Trả lời (hoặc nói
   rõ không xác định được) về khác biệt `41I1` / `41I2`.
2. Task 2: endpoint đã dùng, bảng xếp hạng khối lượng nguyên văn, kết luận một dòng, và đối chiếu
   với bảng OI 26/07. Kết quả test tính tay.
3. Task 3: truy vấn `bars` sau khi nạp, nguyên văn.
4. `uv run pytest -m "not integration" -q` (nền **755**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Nợ đã biết, cố ý KHÔNG giao trong đợt này

`trading/derivative_backtest.py:19` vẫn ghim cứng `41I1G8000` đã đáo hạn. Tôi **không** giao sửa
trong đợt này vì `tests/test_derivative_backtest.py` đọc fixture
`scripts/.spike_derivative_ohlc_5m_2m_sample.json` gắn với chính mã đó — đổi mã là đổi cả bộ dữ liệu
kiểm thử, một việc riêng đủ lớn để có brief riêng, và phải làm **sau khi** biết mã thắng là gì.

Ghi nhận thẳng: đây là **nợ quá hạn**, không phải phát hiện mới. Spec 08/08 đã hẹn cập nhật trước
20/08 và việc đó không xảy ra. Sau đợt 82 tôi sẽ viết brief trả nợ này.
