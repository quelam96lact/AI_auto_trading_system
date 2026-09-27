# Brief đợt 115 — Dữ liệu dài hạn của tài sản gốc (vàng, S&P 500, NASDAQ 100, EUR/USD, USD/JPY) và độ bám của BingX

Ngày giao: 27/09/2026. Base: main `7e38577`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh**.

## 0. Vì sao

Đợt 114 đã xác định: BingX TradFi **không đủ lịch sử** để đo. Mã có lịch sử dài nhất là vàng, chỉ 301 nến 1d. Hướng còn lại là tách hai việc:
1. **Đo chiến lược trên lịch sử dài của tài sản gốc**, lấy từ nguồn bên ngoài, ít nhất 10 năm nến ngày;
2. **Kiểm tra giá perpetual trên BingX có bám sát giá gốc không** trong khoảng thời gian hai nguồn cùng có dữ liệu.

Nếu (2) không đạt, kết quả của (1) không chuyển sang BingX được.

**Đợt này chỉ làm dữ liệu và (2). Chưa đo chiến lược.**

Chỉ dùng **khung ngày**. Đợt 114 cho thấy phí một vòng taker chiếm 26–54% ATR của nến 1h, nên khung giờ trên các mã này gần như chắc chắn bị phí ăn hết.

## 1. Tài sản, và mã BingX tương ứng

| Tài sản | Mã BingX (đợt 114) |
|---|---|
| Vàng (XAU/USD spot) | `NCCOGOLD2USD-USDT` |
| S&P 500 | `NCSISP5002USD-USDT` |
| NASDAQ 100 | `NCSINASDAQ1002USD-USDT` |
| EUR/USD | `NCFXEUR2USD-USDT` |
| USD/JPY | `NCFXUSD2JPY-USDT` |

## 2. Chọn nguồn. Đây là bước quyết định, KHÔNG đoán

Với **từng** tài sản, agent tìm ít nhất một nguồn **miễn phí, tải được bằng chương trình, và điều khoản cho phép dùng cá nhân/nghiên cứu**. Ghi cho mỗi nguồn:

| Cột | Yêu cầu |
|---|---|
| Nguồn và URL tải | URL cụ thể |
| **URL điều khoản sử dụng** | Kèm **trích nguyên văn** câu cho phép hoặc cấm |
| Chuỗi là gì | Giá đóng cửa spot, fixing, hay chỉ số? Giờ chốt? |
| Độ dài lịch sử | Năm bắt đầu |
| Hạn chế đã biết | Ví dụ chỉ cho 10 năm gần nhất, đã ngừng cập nhật, có lỗ ngày lễ |

Quy tắc:
- **Không dùng** nguồn mà điều khoản cấm tải tự động hoặc cấm tái sử dụng, dù kỹ thuật tải được (ví dụ gọi API không chính thức).
- Nguồn nào có điều khoản mơ hồ thì ghi "mơ hồ" và **không nạp**, chờ Claude và chủ dự án quyết.
- **Không khẳng định** một nguồn có hoặc không có chuỗi dữ liệu nào đó khi chưa mở trang nguồn để kiểm. Ghi URL đã kiểm.
- Ưu tiên nguồn chính thức: ngân hàng trung ương, cơ quan thống kê, hoặc nhà cung cấp chỉ số.

**Nếu một tài sản không có nguồn đạt yêu cầu thì bỏ tài sản đó và ghi lý do.** Không hạ chuẩn.

## 3. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/load_external_daily.py` | **Mới.** Tải từ các nguồn đã duyệt ở §2 và ghi vào bảng **mới** `bars_ext_daily (source, symbol, date, close, [open, high, low nếu nguồn có], PRIMARY KEY (source, symbol, date))`. Chỉ tạo bảng, không đụng bảng khác. |
| `scripts/check_bingx_tracking.py` | **Mới.** So `bars_ext_daily` với nến 1d của BingX trong `bars_crypto`. |
| `tests/test_load_external_daily.py`, `tests/test_check_bingx_tracking.py` | **Mới.** |
| `docs/superpowers/research/2026-09-2x-dot-115-du-lieu-dai-han-tai-san-goc.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `trading/`;
- các script khác;
- `bars`, `bars_daily`, `bars_crypto`: **chỉ đọc**;
- config, container, Task Scheduler.

**Niêm phong:** chỉ nạp dữ liệu đến **2026-08-31**, như các đợt trước.

## 4. Các bước

1. **Bảng nguồn theo §2.**
   → **Kiểm chứng bằng:** bảng kèm URL và trích dẫn điều khoản. Claude sẽ tự mở từng URL để đối chiếu.

2. **Nạp.** Chỉ nạp từ các nguồn được đánh dấu "cho phép".
   → **Kiểm chứng bằng:** với mỗi chuỗi, dán số dòng, ngày đầu, ngày cuối, số ngày giá ≤ 0, số ngày trùng, và khoảng trống dài nhất tính theo ngày làm việc.

3. **Kiểm tra độ bám của BingX** (hàm thuần có test). Với mỗi tài sản, trên các ngày cả hai nguồn cùng có dữ liệu, tính:
   - `basis_t = close_BingX_t / close_gốc_t − 1`: trung vị, P5, P95, max |basis|;
   - tương quan lợi suất ngày (Pearson) giữa hai chuỗi;
   - **tracking error** = độ lệch chuẩn năm hoá của hiệu lợi suất ngày;
   - số ngày |basis| > 1%.

   **Căn ngày:** nến 1d của BingX mốc 00:00 UTC, còn giá gốc có giờ chốt riêng. Ghi rõ đã căn ngày thế nào. Chạy cả hai cách căn, cùng ngày và lệch một ngày, rồi báo cách nào tương quan cao hơn. **Không** tự chọn im lặng.

   Nếu chưa có nến 1d của EUR/USD và USD/JPY (đợt 114 chạy vào Chủ nhật), chạy lại `scripts/bingx_klines.py` cho hai mã đó **vào ngày thường**. Nếu vẫn bị tạm dừng thì ghi lại, không ép.

4. **Test.** Viết test cho basis, tương quan, tracking error và căn ngày, mỗi hàm có ví dụ tính tay. Phá thử: căn ngày lệch sai hướng thì test phải đỏ. Sao lưu ra ngoài repo; **cấm `git checkout`, `git restore`, `git stash`.**
   → **Kiểm chứng bằng:** pytest và `uv run ruff check trading tests scripts/load_external_daily.py scripts/check_bingx_tracking.py`.

## 5. Báo cáo cho Claude

**Bảng chính ở đầu báo cáo:**

`Tài sản | Nguồn (điều khoản) | Năm bắt đầu | Số ngày | Basis trung vị (P5–P95) | Tương quan lợi suất | Tracking error năm | Căn ngày tốt hơn`

**Tiêu chí, chỉ để phân loại:** một tài sản được đánh dấu **"đủ để đo tiếp"** khi thoả **cả ba**:
- có ít nhất 10 năm dữ liệu gốc từ nguồn được phép;
- tương quan lợi suất ngày với BingX ≥ 0,95;
- |basis| trung vị ≤ 0,5%.

Không kết luận gì về lợi nhuận hay chiến lược.

Kết thúc bằng câu: "Tôi không commit, không push, không đặt lệnh, không dùng nguồn có điều khoản cấm hoặc mơ hồ, không nạp dữ liệu từ 2026-09-01."
