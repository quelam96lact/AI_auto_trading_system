# Brief đợt 12 — BingX giai đoạn 1: nạp dữ liệu nến

Giao tối 02/09/2026. **Giai đoạn 2 (đo chiến lược) bị khoá** — lý do ở mục 6.

---

## 0. Dữ kiện đã kiểm chứng bằng gọi API thật (02/09, không dùng API key)

Đừng tin lại tài liệu ở những điểm này — đã đo:

| Điều | Tài liệu nói | **Thực tế đo được** |
|---|---|---|
| Xác thực cho `klines` | mâu thuẫn giữa hai trang | **KHÔNG cần API key** (`code = 0`) |
| Số nến tối đa mỗi lần | `max 1440` | **1000** — bốn lần gọi đều ≤ 1000 |
| Lịch sử `BTC-USDT` 1d | không nói | bắt đầu **2021-05-14** (~5,3 năm) |
| Tần suất | 1/s per IP | (chưa thử vượt — **đừng thử**) |

Endpoint:
```
GET https://open-api.bingx.com/openApi/swap/v3/quote/klines
    symbol=BTC-USDT  interval=1d  startTime=<ms>  endTime=<ms>  limit=<=1000
```

Nến trả về là **mảng trong mảng**:
`[openTime_ms, open, high, low, close, volume, closeTime_ms, quoteVolume, trades]`

Hành vi `startTime` đã đo: xin từ 2020-01-01 thì trả về **2021-05-14 → 2023-12-10**
(941 nến). Tức là nó tự bắt đầu từ nến cũ nhất có thật, rồi đi tới, và dừng ở
mức ~1000. **Không có nghĩa là thiếu dữ liệu** — nghĩa là phải phân trang.

---

## 1. Ràng buộc

- **Chỉ tạo/sửa trong `scripts/` và `tests/`.** Không chạm `trading/`,
  `config/config.yaml`, `scripts/heartbeat_check.py`. Chạm `trading/` ⇒ dựng
  lại container ⇒ làm bẩn phiên VN ngày 03/09.
- **Không đặt lệnh, không gọi endpoint giao dịch, không dùng API key.** Giai
  đoạn này chỉ đọc dữ liệu công khai. Nếu thấy mình cần key ⇒ **dừng, báo cáo**.
- **Không cài plugin skill của BingX** trong đợt này. Tài liệu đã trích đủ ở
  mục 0; cài code bên thứ ba là quyết định riêng của chủ dự án.
- **Tuyệt đối không vượt 1/s.** Ngủ ≥ 1,1 s giữa hai lệnh gọi. Nếu gặp lỗi
  `100410` (vượt tần suất): lùi theo cấp số nhân, **trần 600 s**, đúng khuôn
  `trading/collector/feed.py` (`f8e3392`). **Không gõ cửa dồn dập** — chính
  hành vi đó là thứ bản sửa 429 sinh ra để diệt.
- **Không `TRUNCATE`, không `DROP`, không xoá dòng** ở bất kỳ bảng nào đang có.
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. `.env` không sửa. Không in giá trị bí mật.
- Ngoài phạm vi thì báo cáo, không tự sửa.

---

## 2. Task 1 — `scripts/bingx_klines.py` (mới)

Nạp nến lịch sử từ BingX vào DB.

### Yêu cầu thiết kế

1. **Bảng MỚI, không dùng lại `bars` hay `bars_daily`.** Đề xuất tên
   `bars_crypto`. Lý do không phải sạch sẽ mà là **an toàn phép đo**: mọi kết
   luận về thị trường VN (`711683a`, `14a5ff3`) đều đo trên `bars_daily`; trộn
   dữ liệu crypto vào đó là mở đường cho một lần nhiễm bẩn không ai phát hiện.
   Cột nên có `interval` — cùng một mã có nhiều khung.
2. **Phân trang bằng `startTime`.** Cứ 1000 nến một lần, lấy `closeTime` của
   nến cuối làm `startTime` kế tiếp, tới khi hết. **Phải chống lặp vô hạn**:
   nếu một lượt trả về 0 nến hoặc nến cuối không tiến lên, dừng.
3. **Phát hiện mốc đầu của TỪNG mã, không giả định.** BTC bắt đầu 2021-05-14;
   mã niêm yết sau sẽ khác. Ghi mốc đầu thật vào báo cáo cho mỗi mã.
4. **UPSERT, không xoá-rồi-ghi.** Chạy lại phải an toàn.
5. Tham số dòng lệnh tối thiểu: `--symbols`, `--interval`, `--from`, `--to`.

### Phạm vi đợt này

**Chỉ khung `1d` và `1h`. Không nạp `5m`.** Tính từ số đã đo (1000 nến/lần,
1 lệnh/giây):

| Khung | 5,3 năm/1 mã | Lệnh gọi | 1 mã | 20 mã |
|---|---:|---:|---:|---:|
| 1d | ~1.935 | 2 | ~2 giây | ~1 phút |
| 1h | ~46.400 | 47 | ~50 giây | ~17 phút |
| 5m | ~557.000 | 557 | ~10 phút | ~3,3 giờ |

Bắt đầu với **20 cặp thanh khoản cao nhất** (lấy từ endpoint danh sách hợp
đồng, không tự nghĩ ra danh sách). 5m để giai đoạn sau nếu 1d/1h cho tín hiệu
đáng theo.

---

## 3. Task 2 — Test

`tests/test_bingx_klines.py`. **Tất định, không gọi mạng thật, không chạm DB.**
Dữ liệu mạng giả lập bằng cách chèn hàm fetch.

Bắt buộc bốn test:

1. `test_phan_trang_ghep_du_khong_trung` — hai trang liền nhau ghép lại đúng
   số nến, không nến nào lặp.
2. `test_dung_khi_khong_tien_len` — trang trả về nến cuối **không** mới hơn
   lần trước ⇒ dừng, không lặp vô hạn. *(Đây là test quan trọng nhất: một vòng
   lặp nạp dữ liệu không có điều kiện dừng sẽ gõ API 1 lần/giây mãi mãi và
   dẫn thẳng tới bị chặn.)*
3. `test_parse_nen_dung_thu_tu_truong` — mảng
   `[openTime, o, h, l, c, volume, closeTime, ...]` ánh xạ đúng; đặc biệt
   **không lẫn `close` với `closeTime`**.
4. `test_loi_tan_suat_thi_lui_dan_va_khong_ne` — gặp `100410` ⇒ lùi theo cấp
   số nhân, có trần, và **không** ném ra ngoài.

### Kiểm chứng phá hoại (bắt buộc)

Với test 2 và test 3: phá code cho đỏ, **dán nguyên văn output đỏ**, rồi khôi
phục. Phép phá đúng cho test 3 là đổi chỉ số `[4]` thành `[6]` — nếu test vẫn
xanh thì nó không kiểm được gì.

---

## 4. Task 3 — Nạp thật và báo cáo dữ liệu

Chạy nạp thật `1d` cho 20 cặp, rồi báo cáo:

- Số mã, tổng số nến, mốc đầu **của từng mã** (bảng).
- Số lệnh gọi đã dùng và tổng thời gian — đối chiếu với bảng ước lượng ở mục 2.
- Có mã nào lịch sử ngắn hơn 3 năm không (ảnh hưởng khả năng chia trong
  mẫu/ngoài mẫu sau này).
- Có lần nào dính `100410` không, và backoff xử lý ra sao.

**Không đo chiến lược trong đợt này.** Lý do ở mục 6.

---

## 5. Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | 4 test | `uv run pytest tests/test_bingx_klines.py -v` → 4 passed |
| 2 | Phá hoại | output đỏ nguyên văn test 2 và test 3 |
| 3 | Nạp thật 1d, 20 cặp | bảng mốc đầu từng mã + tổng số nến |
| 4 | Chạy lại an toàn | chạy lần hai ⇒ **không sinh dòng trùng** (UPSERT) |
| 5 | Không đụng bảng cũ | `SELECT count(*) FROM bars_daily` trước và sau **bằng nhau** |
| 6 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |

Tiêu chí 5 là tiêu chí quan trọng nhất về an toàn — chụp số trước khi bắt đầu.

---

## 6. Vì sao giai đoạn 2 (đo chiến lược) CHƯA giao

Đã kiểm: `trading/backtest.py:172` viết `broker = PaperBroker(capital)` —
**đóng cứng**, không nhận tham số phí. Nghĩa là mọi backtest hiện tại áp:

- `FEE_RATE = 0.0025` (0,25 % — phí chứng khoán VN)
- `SELL_TAX_RATE = 0.001` (0,1 % — **thuế bán, không tồn tại ở crypto**)
- `SETTLE_DAYS = 3` (T+2,5 — **crypto không có thanh toán bù trừ**)

`PaperBroker.__init__` *có* nhận `fee_rate`/`sell_tax_rate`/`slippage_bps`,
nhưng `SETTLE_DAYS` là hằng số mức module, và `run_backtest` không truyền gì
cả. Nên đo crypto bằng `run_backtest` hiện tại sẽ **âm thầm áp luật thị trường
Việt Nam lên dữ liệu crypto** — một chiến lược bị cấm bán trong 3 ngày và bị
trừ thuế bán không tồn tại. Con số ra sẽ sai mà trông vẫn hợp lý.

Sửa chỗ đó chạm `trading/` ⇒ phải sau 14:45 ngày 03/09, và nên gộp cùng B1
(hợp đồng chiến lược + sổ đăng ký) vì cùng động vào tầng đó.

**Giai đoạn 1 không bị chặn bởi điều này** — nạp dữ liệu không cần broker. Cứ
làm, dữ liệu sẽ sẵn khi tầng đo mở khoá.

---

## 7. Nhắc lại điều không thay đổi

Không chiến lược nào trong repo có lợi thế đo được. Việc nạp dữ liệu crypto
**không** phải bước đi tới giao dịch thật — nó là bước đi tới một **phép đo**.
Nếu phép đo đó nói "không", câu trả lời "không" cũng là kết quả thành công,
đúng như đợt 9 và đợt 10.
