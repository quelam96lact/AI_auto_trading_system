# Brief đợt 13 — BingX: nạp khung 1h (phần còn lại của giai đoạn 1)

Giao tối 02/09/2026. Kế thừa `scripts/bingx_klines.py` đã có, đã audit
(`4d91afd`).

---

## 0. Vì sao có brief này

Brief đợt 12 xin cả `1d` **và** `1h` (mục 2, bảng ước lượng). Agent đợt 12
làm đúng và đầy đủ phần `1d` (27.124 nến, 20 mã, đã audit) nhưng báo cáo chỉ
có `1d`. `1h` là phần còn lại trong phạm vi đã duyệt, chưa ai làm — không phải
việc mới.

**Không viết lại `bingx_klines.py`.** Nó đã hỗ trợ `--interval 1h` sẵn
(`choices=["1d", "1h", "5m"]`). Việc là **chạy**, không phải **sửa** — trừ khi
bạn phát hiện một lỗi thật khi chạy thử.

---

## 1. Ràng buộc (giữ nguyên từ brief đợt 12)

- Chỉ chạy `scripts/bingx_klines.py` đã có. Nếu cần sửa, chỉ sửa trong
  `scripts/` và `tests/`. Không chạm `trading/`, `config/config.yaml`,
  `scripts/heartbeat_check.py`.
- Không dùng API key, không đặt lệnh.
- Tuyệt đối không vượt 1/s. Script đã có backoff — không tắt, không rút ngắn.
- Không `TRUNCATE`/`DROP`/xoá dòng ở bảng nào.
- Không commit, không push. Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Ngoài phạm vi thì báo cáo, không tự sửa.

---

## 2. Việc

Chạy nạp `1h` cho **đúng 20 mã đã có trong `bars_crypto`** (dùng lại danh sách
động từ `get_top_crypto_symbols`, đừng gõ tay 20 mã — danh sách có thể đã đổi
kể từ đợt 12 vì nó xếp theo thanh khoản).

Ước lượng từ brief gốc: ~47 lệnh gọi/mã, ~50 giây/mã, **~17 phút cho 20 mã**.
Nếu thực tế lệch xa con số này (quá 30 phút hoặc dưới 5 phút), báo cáo con số
thật và một dòng giải thích — đừng im lặng chấp nhận sai lệch lớn.

Trước khi chạy thật cho cả 20 mã: chạy thử **một mã** (`BTC-USDT`), xác nhận
số nến và khoảng thời gian hợp lý, rồi mới chạy hàng loạt. Nếu mã đầu tiên bất
thường (số nến bằng 0, hoặc lỗi), dừng và báo cáo trước khi chạy tiếp 19 mã
còn lại.

---

## 3. Kiểm chứng an toàn (bắt buộc, không đổi so với đợt 12)

- **Chụp số trước khi chạy:**
  `SELECT count(*) FROM bars_crypto WHERE interval='1d'` — phải **không đổi**
  sau khi nạp `1h` (hai khung độc lập, không được ghi đè lẫn nhau).
- **Chụp số `bars_daily` trước/sau** — vẫn phải bằng nhau, đúng kỷ luật cũ.
- Chạy lại nạp `1h` cho một mã bất kỳ lần thứ hai: tổng số nến `1h` của mã đó
  **không đổi** (UPSERT, không trùng).

---

## 4. Không cần test mới

`tests/test_bingx_klines.py` đã kiểm hành vi phân trang/parse/backoff — hành
vi đó không phụ thuộc khung thời gian. Không cần viết test riêng cho `1h`.
Chỉ chạy lại suite để chắc không hồi quy:

```
uv run pytest -m "not integration" -q
```

---

## 5. Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Chạy thử 1 mã trước | báo cáo số nến + khoảng thời gian của `BTC-USDT` |
| 2 | Nạp `1h` cho 20 mã | bảng số nến/mã, tổng lệnh gọi, tổng thời gian |
| 3 | Khung `1d` không đổi | đếm trước/sau bằng nhau |
| 4 | `bars_daily` không đổi | đếm trước/sau bằng nhau |
| 5 | Chạy lại 1 mã, không trùng | đếm trước/sau lần chạy lại bằng nhau |
| 6 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |

---

## 6. Sau việc này

Dữ liệu `1d` + `1h` cho 20 mã là đủ để giai đoạn 2 (đo chiến lược) bắt đầu
ngay khi nó mở khoá — không cần nạp gì thêm trước đó. **Không tự ý bắt đầu
giai đoạn 2** dù dữ liệu đã sẵn: `run_backtest` vẫn đóng cứng phí/thuế/T+3 của
thị trường VN, và sửa chỗ đó chạm `trading/` nên phải chờ B1 mở khoá sau
14:45 ngày 03/09.
