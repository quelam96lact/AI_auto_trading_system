
# Brief đợt 84 — Tách bảng phái sinh, dọn nến hỏng, và giết lớp lỗi "mã ghim cứng hết hạn"

Ngày giao: 24/09/2026.
Base: main `6f83e03`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh — bốn việc, đều do đợt 82/83 để lại

Đợt 83 dựng được `VN30F1M_CONT` và phân định đúng lưới nến 49 nến/phiên. Nhưng khi audit tôi tìm ra
bốn vấn đề, **ba trong đó do chính đợt 82/83 gây ra**:

1. **`bars` bị nhiễm.** Bảng `bars` nay có **350 mã, 11 mã phái sinh** (10 hợp đồng +
   `VN30F1M_CONT`); trước đợt 82 chỉ có 1. `scripts/measure_octopus_5m_universe.py:49-56` lấy
   **toàn bộ** `SELECT DISTINCT symbol FROM bars` làm universe, docstring ghi rõ *"Tuyệt đối không
   đọc config.yaml hay exclusions.txt"*. Chạy nó bây giờ sẽ áp `octopus_pullback` (chiến lược cổ
   phiếu theo nến ngày) lên hợp đồng tương lai chỉ số — đơn vị **điểm**, 100.000 VNĐ/điểm, mô hình
   phí khác hẳn — và **ra số sai trông như hợp lệ**.
2. **21 nến có `open=0` và `low=0` nhưng volume thật.** Bộ lọc `O=V=0` của đợt 83 trượt vì volume
   khác 0. Phân bố: `41I1GA000` 14 nến, `41I1G9000` 6, `41I1G8000` 1; **2 nến nằm trong
   `VN30F1M_CONT`**. `low=0` phá mọi phép tính biên độ/ATR, `open=0` phá mọi logic dùng giá mở.
3. **Chuỗi "118 phiên liên tục" không liên tục.** `06/07/2026` vắng hoàn toàn dù là ngày giao dịch
   thật (`bars_daily` có 914 mã ngày đó); `07/07/2026` chỉ có 1 nến (14:45). Lỗ ở **nguồn SSI**
   (`41I1G7000` tự nó không có nến 06/07) — không sửa được, nhưng đang bị **im lặng**.
4. **`derivative_backtest.py:19` vẫn ghim `41I1G8000`** đã đáo hạn 20/08. Việc này tôi đã hoãn hai
   lần; nay **không hoãn được nữa** vì Task 1 di chuyển dữ liệu sẽ làm hỏng chính đường đọc của nó
   (`derivative_backtest.py:178` gọi `storage.read_bars(DERIVATIVE_SYMBOL, ...)` trên bảng `bars`).

---

## 1. Ràng buộc

- Được sửa: `trading/storage/schema.sql`, `trading/storage/db.py` (**chỉ thêm**, không đổi hàm sẵn có),
  `trading/derivative_backtest.py`, `scripts/build_derivative_continuous_series.py`, và test tương ứng.
- **Không** sửa `scripts/measure_octopus_5m_universe.py`. Sau Task 1 nó tự sạch mà không cần đổi một
  dòng — đó chính là lý do chọn hướng tách bảng. Đừng đụng vào docstring "tuyệt đối không đọc
  exclusions" của nó, đó là quyết định có chủ ý của dự án.
- **Không** sửa `derivative_position.py`, `derivative_risk.py`, `collector/`, hai script spike.
- **Không** đặt lệnh. Không restart/build container. Không commit, không push.
- Nền hiện tại: **769 passed**, ruff sạch.

---

## Task 1 — Bảng `bars_derivative`, và di chuyển 11 mã ra khỏi `bars`

**Vì sao tách bảng chứ không lọc theo tiền tố:** dự án **đã có tiền lệ** — `bars_crypto` là bảng
riêng cho lớp tài sản khác, ghi bởi `scripts/bingx_klines.py` (`upsert_bars_crypto`), không đi qua
`db.py`. Phái sinh là lớp tài sản khác (đơn vị điểm, hệ số nhân 100.000, phí theo hợp đồng), và
`VN30F1M_CONT` còn là **dữ liệu dẫn xuất** — cả hai đều không thuộc bảng nến thô của cổ phiếu. Lọc
theo tiền tố chỉ vá một chỗ gọi; tách bảng chặn cả lớp lỗi.

1. Thêm bảng `bars_derivative` vào `schema.sql`, **cùng cấu trúc** `bars` (`symbol, ts, open, high,
   low, close, volume, source`), cùng khoá chính `(symbol, ts)`. Nếu `bars` là hypertable thì làm
   giống y như `bars` — **đọc `schema.sql` và bắt chước, đừng tự sáng tạo**.
2. Di chuyển **đúng 11 mã** (`41I1*` và `VN30F1M_CONT`) từ `bars` sang `bars_derivative`.
   **Quy trình bắt buộc, theo thứ tự:**
   a. Đếm và **ghi lại** số dòng từng mã trong `bars` **trước** khi làm gì.
   b. `INSERT INTO bars_derivative ... SELECT ... FROM bars WHERE ...`
   c. Đếm lại trong `bars_derivative`, **so từng mã** với bước (a). **Chỉ khi khớp tuyệt đối** mới
      sang bước (d).
   d. `DELETE FROM bars WHERE symbol IN (...)`.
   e. Xác nhận `bars` còn **339 mã** và **0 mã phái sinh**.
   Nếu bước (c) lệch một dòng: **DỪNG, không DELETE, báo cáo ngay.**
3. Thêm `Storage.read_derivative_bars(symbol, start, end)` vào `db.py` — **hàm mới, không sửa
   `read_bars`**.

**Kiểm chứng:** dán nguyên văn bảng đếm trước/sau từng mã, và truy vấn xác nhận `bars` sạch.

---

## Task 2 — Dọn 21 nến `open=0 / low=0`, theo quy tắc có căn cứ cấu trúc thị trường

**Không** xử lý đồng loạt. Tôi đã xem hai nến trong `VN30F1M_CONT` và chúng **khác bản chất**:

```
18/09 14:45   O=0  H=1970     L=0  C=1970     V=7.492    <- H == C
21/09 09:00   O=0  H=1977,3   L=0  C=1975,9   V=8.544    <- H != C
```

Quy tắc, dựa trên cấu trúc phiên phái sinh VN mà đợt 83 đã xác lập (49 nến: ATC là nến 14:45; nến
09:00 gộp khớp định kỳ ATO **và** phần đầu khớp liên tục):

- **Nến 14:45** là phiên khớp định kỳ ATC thuần → khớp tại **một giá duy nhất** → **sửa**
  `open = low = close`. Trước khi sửa phải **kiểm `high == close`**; nếu không bằng, **đừng sửa**,
  báo cáo nến đó riêng.
- **Mọi nến khác** (gồm 09:00) → **không suy ra được** `open`/`low` vì bar gộp nhiều mức giá →
  **XOÁ**, và **log từng nến bị xoá** (mã, ts, OHLCV nguyên gốc).

**Vì sao xoá chứ không sửa:** nến 21/09 09:00 có `H != C`, chứng minh nó **không** phải bar một giá.
Đặt `open = close` ở đó là **bịa dữ liệu**. 21 nến trên ~15.000 nến phái sinh là 0,14% — mất đi an
toàn hơn nhiều so với giữ một số 0 đầu độc mọi phép tính ATR.

Áp dụng cho **cả `bars_derivative` (11 mã) và `VN30F1M_CONT`**.

**Kiểm chứng:**
1. Trước khi làm: bảng liệt kê **toàn bộ** nến có `open=0 OR low=0 OR high=0 OR close=0`, kèm
   phân loại theo quy tắc trên (sửa / xoá). Dán nguyên văn.
2. Sau khi làm: truy vấn xác nhận **0 nến** còn `open=0 OR low=0 OR high=0 OR close=0` trong cả hai.
3. **Test đơn vị** cho hàm phân loại (thuần, không DB): ca `14:45 & H==C` → sửa; ca `14:45 & H!=C` →
   báo cáo, không sửa; ca `09:00` → xoá; ca nến bình thường → không đụng. **Kiểm thử phá hoại:** bỏ
   điều kiện `high == close`, xác nhận đúng test ca-2 đỏ.

---

## Task 3 — Chuỗi liên tục phải TỐ GIÁC lỗ, không được im lặng

`build_derivative_continuous_series.py` hiện dựng chuỗi có lỗ mà không nói gì — đợt 83 còn báo cáo
ngược rằng "toàn bộ 117 phiên đều đúng 49 nến". Đó là lỗi **im lặng**, đúng họ FEE-ALARM-2.

Thêm vào script một bước kiểm **sau khi** dựng chuỗi, in ra (và trả exit code khác 0 nếu có vấn đề):
1. **Phiên thiếu**: ngày giao dịch có trong `bars_daily` nhưng **không có** trong chuỗi. Dùng lại
   `is_trading_day()` từ `calendar_vn.py` để xác định ngày giao dịch — **không tự viết lại lịch**.
2. **Phiên không đủ nến**: số nến != 49, kèm số nến thật. (Phiên hôm nay đang chạy dở thì nêu rõ là
   phiên chưa xong, không tính là lỗi.)
3. Tổng kết: tổng phiên, số phiên đủ 49, số phiên thiếu, danh sách ngày có vấn đề.

**Tiêu chí hoàn thành:** chạy thật trên dữ liệu hiện có, script phải **tự nêu** `06/07/2026` (thiếu
phiên) và `07/07/2026` (1 nến). Nếu nó không nêu ra hai ngày này thì bước kiểm chưa hoạt động.

---

## Task 4 — Giết lớp lỗi "mã ghim cứng hết hạn"

`derivative_backtest.py:19` ghim `DERIVATIVE_SYMBOL = "41I1G8000"` (đáo hạn 20/08). Hợp đồng phái
sinh **roll mỗi tháng**, nên mọi hằng số mã hợp đồng đều sẽ hết hạn — vá bằng cách đổi sang mã mới
chỉ là hoãn lỗi thêm một tháng.

1. **Bỏ hằng số**, thay bằng tham số CLI `--symbol` **bắt buộc** (không mặc định). Ai chạy phải nói
   rõ đang đo hợp đồng nào — kể cả `VN30F1M_CONT`.
2. Đổi `derivative_backtest.py:178` từ `storage.read_bars(...)` sang
   `storage.read_derivative_bars(...)` (Task 1).
3. **Kiểm trước khi sửa:** `grep` xem `DERIVATIVE_SYMBOL` còn được dùng ở đâu (đặc biệt
   `tests/test_derivative_backtest.py`). Nếu test nào phụ thuộc, **báo cáo** trước khi đổi — đừng
   sửa kỳ vọng test để cho qua.
4. Nếu thiếu `--symbol` → lỗi rõ ràng, có test.

**Lưu ý:** `tests/test_derivative_backtest.py` đọc fixture `.spike_derivative_ohlc_5m_2m_sample.json`
chứ không qua DB, nên đổi đường đọc DB **không nên** ảnh hưởng nó. Nếu thực tế khác, nói ngay.

---

## 2. Không làm

- Không sửa `measure_octopus_5m_universe.py`, `derivative_position.py`, `derivative_risk.py`,
  `collector/`, script spike. Không xoá `.spike_*`.
- Không đổi hàm sẵn có trong `db.py` (chỉ thêm hàm mới).
- **Không DELETE khỏi `bars` trước khi đếm khớp** (Task 1 bước c).
- Không bịa `open`/`low` cho nến không suy ra được.
- Không backtest, không nghiên cứu chiến lược, không đụng biểu phí.
- Không restart/build container. Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: bảng đếm trước/sau từng mã (11 mã), xác nhận `bars` còn 339 mã / 0 phái sinh.
2. Task 2: bảng phân loại nến hỏng **trước** khi xử lý, truy vấn xác nhận 0 nến hỏng **sau**, log
   từng nến bị xoá, kết quả test + kiểm thử phá hoại.
3. Task 3: nguyên văn output bước kiểm, phải có `06/07` và `07/07`.
4. Task 4: kết quả `grep DERIVATIVE_SYMBOL`, và test cho trường hợp thiếu `--symbol`.
5. `uv run pytest -m "not integration" -q` (nền **769**), suite đầy đủ, `uv run ruff check trading
   tests scripts`.
6. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Đánh giá của tôi về "118 phiên có đủ không" — và một tin tốt

Tôi tự trả lời, không giao agent: **118 phiên (≈5.700 nến 5m, trải 5,7 tháng) KHÔNG đủ để chứng minh
một lợi thế, nhưng ĐỦ để sàng lọc xem có tín hiệu nào không.** Lý do: 5,7 tháng đi qua gần như một
chế độ thị trường duy nhất, nên không thể kiểm out-of-sample xuyên chế độ — mà đó chính là phép kiểm
đã giết quy tắc regime-timing ở đợt 64 (thua 10/11 năm). Một kết quả dương trên 5,7 tháng sẽ **không
đủ tin** để đặt tiền.

**Tin tốt: bước sàng lọc không cần biểu phí.** Sàng lọc tín hiệu dùng tương quan hạng Spearman giữa
đặc trưng và lợi nhuận tương lai (đúng bộ công cụ `leakage_audit.py` + `screen_vn_signal_candidates.py`
đã kiểm chứng ở đợt 71/72/76/77) — phép đo này **không liên quan chi phí**. Nghĩa là **cửa 3 mở được
một nửa trước cửa 2**: sau đợt 84, tôi có thể viết brief sàng lọc tín hiệu trên `VN30F1M_CONT` ngay,
và chỉ cần biểu phí khi nào sàng lọc cho kết quả dương và ta muốn backtest thật.

Nói thẳng kỳ vọng: dự án đã có **bốn** phép đo âm liên tiếp trên cổ phiếu VN và crypto. Tôi không kỳ
vọng phái sinh khác đi. Nhưng đây là lần đầu đo trên dữ liệu **intraday của công cụ thanh khoản nhất
thị trường** (99,37% khối lượng), nên nó là phép thử đáng làm — và nếu âm nữa thì đó là câu trả lời
dứt khoát cho câu hỏi ML, chứ không phải một thất bại.
