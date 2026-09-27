# Brief đợt 114 — BingX TradFi (vàng, chỉ số, forex, cổ phiếu): nạp và kiểm kê dữ liệu, **chưa đo chiến lược**

Ngày giao: 27/09/2026. Base: main `73f093a`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh**.

## 0. Vì sao, và vì sao chưa đo chiến lược

Claude kiểm qua API ngày 27/09 (Chủ nhật). BingX có 614 hợp đồng perpetual phi crypto, ký quỹ USDT, gồm bốn nhóm:

| Tiền tố | Nhóm | Số hợp đồng |
|---|---|---|
| `NCSK` | cổ phiếu | 521 |
| `NCFX` | forex | 42 |
| `NCCO` | hàng hoá | 33 |
| `NCSI` | chỉ số | 18 |

Trạng thái hợp đồng:
- `status=25` nghĩa là **tạm dừng**. API trả mã lỗi 109415 "is pause currently"; ví dụ EUR/USD vào cuối tuần.
- `status=1` là đang giao dịch.

Vàng (`NCCOGOLD2USD-USDT`) **niêm yết từ khoảng 14/10/2025** (`launchTime` 1760424900000), nên lịch sử chỉ khoảng **1 năm**.

Trước khi đặt hàng đo bất kỳ chiến lược nào, phải biết:
- lịch sử có dài không;
- nến có liên tục không;
- giờ giao dịch thế nào;
- funding ra sao.

Nếu dữ liệu quá ngắn hoặc lủng thì không đo được gì có ý nghĩa. **Đợt này chỉ trả lời "dữ liệu có đủ để đo không".**

## 1. Rổ mã (Claude chọn, agent xác nhận mã tồn tại)

| Nhóm | Mã |
|---|---|
| Vàng | `NCCOGOLD2USD-USDT` |
| Bạc | `NCCOXAG2USD-USDT` |
| Dầu WTI | `NCCO1OILWTI2USD-USDT` |
| S&P 500 | `NCSISP5002USD-USDT` |
| NASDAQ 100 | `NCSINASDAQ1002USD-USDT` |
| EUR/USD | `NCFXEUR2USD-USDT` |
| USD/JPY | `NCFXUSD2JPY-USDT` |
| Apple | `NCSKAAPL2USD-USDT` |
| NVIDIA | `NCSKNVDA2USD-USDT` |

Thêm `BTC-USDT` làm **đối chứng**, vì mã này đã biết là liên tục 24/7.

**Ngày niêm yết (`launchTime`, Claude kiểm 27/09):**

| Mã | Niêm yết | Tới 2026-08-31 |
|---|---|---|
| EUR/USD | 27/08/2025 | ≈ 12 tháng |
| USD/JPY | 28/08/2025 | ≈ 12 tháng |
| Vàng | 14/10/2025 | ≈ 10,5 tháng |
| AAPL | 13/11/2025 | ≈ 9,5 tháng |
| S&P 500 / NASDAQ 100 | 26/11/2025 | ≈ 9 tháng |
| Bạc | 11/02/2026 | ≈ 6,5 tháng |
| WTI | 09/03/2026 | ≈ 6 tháng |

**Dự kiến trước:**
- **không mã nào** đạt ngưỡng 3 năm nến 1d;
- chỉ vài mã có thể chạm ngưỡng 1 năm nến 1h.

Đây là điều **cần đo cho chắc**, không phải lý do để bỏ bước. Báo cáo phải ghi đúng con số đo được.

## 2. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/bingx_klines.py` | **Chỉ chạy**, không sửa. Script đã có `--symbols`, `--interval 1d/1h`, `--from`, `--to`, và ghi vào bảng `bars_crypto`. Nếu nó hỏng với mã NC thì **dừng lại và báo**, không tự sửa. |
| `scripts/inventory_bingx_tradfi.py` | **Mới.** Chỉ đọc DB và API công khai; in các bảng ở §3. |
| `tests/test_inventory_bingx_tradfi.py` | **Mới.** Test các hàm thuần. |
| `docs/superpowers/research/2026-09-2x-dot-114-bingx-tradfi-du-lieu.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `trading/`;
- các script khác;
- config, container, Task Scheduler.

Không gọi endpoint nào cần ký. Không đặt lệnh.

## 3. Các bước

1. **Nạp dữ liệu.** Chạy `bingx_klines.py` cho rổ ở §1, khung `1d` và `1h`, từ ngày niêm yết (hoặc càng sớm càng tốt) đến **2026-08-31**. Dữ liệu từ 2026-09-01 được niêm phong như với crypto.
   → **Kiểm chứng bằng:** dán số nến đã ghi cho mỗi mã và mỗi khung.

2. **Kiểm kê, dùng hàm thuần có test.** Với mỗi mã và mỗi khung:
   - Nến đầu, nến cuối, tổng số nến, số ngày lịch.
   - **Hồ sơ giờ giao dịch** (khung 1h): số nến theo **thứ trong tuần (UTC) × giờ (UTC)**, in dạng bảng 7×24. Dùng bảng này để suy ra mã giao dịch 24/7, 24/5, hay theo phiên sở giao dịch. **Không** đoán giờ phiên từ bên ngoài.
   - **Khoảng trống:** số lần hai nến liên tiếp cách nhau hơn một khung, trừ các khoảng trống trùng với khoảng nghỉ "bình thường" suy ra từ bảng 7×24. Liệt kê 10 khoảng trống bất thường dài nhất.
   - Nến bẩn theo `trading.data_quality.is_dirty_bar`, và nến có `volume = 0`: đếm số lượng.
   - **Đối chiếu 1h → 1d:** gộp nến 1h thành ngày UTC rồi so với nến 1d (close, high, low). In số ngày lệch quá 0,1%.

3. **Funding.** Dùng endpoint lịch sử funding công khai của BingX; lấy **từ tài liệu chính thức**, ghi URL. Với mỗi mã:
   - số mốc funding;
   - khoảng cách giữa các mốc (8h? khác?);
   - trung bình và trung bình trị tuyệt đối của funding rate.

   Nếu endpoint không trả dữ liệu cho mã NC thì ghi "không có", không đoán.

4. **Chi phí so với biến động** (để biết phí có "nuốt" hết biên lời không). Với mỗi mã, tính:
   - ATR14 trung vị của khung 1h, dưới dạng % giá;
   - **phí một vòng taker**: 2 × `takerFeeRate`, lấy từ API contracts, không đoán;
   - tỷ lệ `phí / ATR1h`.

5. **Test.** Viết test cho các hàm thuần: bảng 7×24, phát hiện khoảng trống, gộp 1h → 1d, tỷ lệ phí/ATR. Mỗi hàm có ví dụ tính tay. Phá thử ít nhất một hàm: đổi phép gộp 1h → 1d sang lấy close của nến **đầu** ngày thì test phải đỏ. Sao lưu ra ngoài repo; **cấm `git checkout`, `git restore`, `git stash`.**
   → **Kiểm chứng bằng:** pytest, cộng `uv run ruff check trading tests scripts/inventory_bingx_tradfi.py`.

## 4. Báo cáo cho Claude

**Bảng chính ở đầu báo cáo:**

`Mã | Niêm yết | Số nến 1d | Số nến 1h | Hồ sơ giờ (24/7, 24/5, phiên…) | Khoảng trống bất thường | Nến bẩn | Funding (chu kỳ, TB) | Phí/ATR1h`

Sau bảng chính là toàn bộ output và bảng 7×24 của từng mã.

**Không kết luận "đáng giao dịch".** Chỉ được kết luận dữ liệu **đủ** hay **không đủ** để đo, theo đúng hai ngưỡng sau:
- **đủ để đo chiến lược khung ngày:** ít nhất 3 năm nến 1d;
- **đủ để đo chiến lược khung giờ:** ít nhất 1 năm nến 1h, và dưới 1% khoảng trống bất thường.

Kết thúc bằng câu: "Tôi không commit, không push, không gọi endpoint có ký, không đặt lệnh, không đọc dữ liệu từ 2026-09-01."
