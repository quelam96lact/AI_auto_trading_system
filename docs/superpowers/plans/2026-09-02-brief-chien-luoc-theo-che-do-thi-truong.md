# Brief đợt 9 — Chiến lược theo chế độ thị trường, giai đoạn 1: ĐO

Viết 02/09/2026. Yêu cầu của chủ dự án: tuỳ chỉnh chiến lược giao dịch theo
trạng thái/giai đoạn thị trường.

---

## 0. Vì sao brief này chỉ đo, không dựng

Chuyển chiến lược theo chế độ thị trường **không tự nó tạo lợi thế**. Ba
chiến lược hiện có đều thua mua-và-giữ (`711683a`, đo lại 01/09). Ghép ba
thứ thua bằng một quy tắc chuyển đổi hoàn toàn có thể ra một thứ thua.

Nguy hiểm thật không nằm ở kỹ thuật mà ở **khớp quá khứ (overfitting)**: với
3 chiến lược và vô số cách định nghĩa "chế độ", chắc chắn tồn tại một quy
tắc khớp đẹp với 10 năm đã qua. Tìm ra nó rất dễ, và nó sẽ vẽ một đường vốn
thuyết phục. Dự án này đã hai lần nhận số liệu không tái lập được trong
tuần vừa rồi (báo cáo đợt 3 đo trong giờ nghỉ trưa; đợt 4 lệch 113/103/23 so
với 61/72/25 khi chạy lại).

Nên: **đo trước, dựng sau.** Phần engine chỉ khởi động nếu con số sống sót
kỳ ngoài mẫu. Nếu không sống sót, kết quả của brief này là một câu trả lời
"không" có bằng chứng — đó cũng là thành công, không phải thất bại.

### Hai dữ kiện đã kiểm chứng 02/09

**Dữ liệu đủ.** `bars_daily`: 1.554 mã, 2.982.903 bar, 2016-01-04 →
2026-08-28; trên 900 mã ngay từ 2016. Thừa để chia trong mẫu / ngoài mẫu.

**Không có chỉ số.** `config.yaml` khai `indices: [VNINDEX, VN30]` nhưng
truy vấn `bars_daily` cho hai mã này trả về **0 dòng**. Không thể định nghĩa
chế độ theo VNINDEX. Phải dựng thước đo từ chính rổ cổ phiếu — xem Task 1.

---

## 1. Ràng buộc — đọc trước khi gõ dòng đầu tiên

- **Không sửa bất kỳ file nào trong `trading/`.** Được `import` (chỉ đọc).
  Lý do cứng: chạm `trading/` ⇒ phải dựng lại container ⇒ làm bẩn phép đo
  phiên 03/09 **và** khiến `deploy_drift_check` báo lệch. Toàn bộ code của
  brief này nằm trong `scripts/` và `tests/`, đúng khuôn `measure_strategy.py`.
- **Không sửa `config/config.yaml`.**
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API đặt/huỷ lệnh SSI.
  API dữ liệu chỉ đọc.
- **Không `TRUNCATE`, không `DROP`, không xoá dòng.** Chỉ đọc `bars_daily`.
  Nếu cần ghi kết quả thì ghi ra file CSV/JSON trong `docs/`, không ghi DB.
- Không in giá trị bí mật (được phép nhắc tên biến). `.env` không sửa.
- Phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.
- `bars_daily` là hypertable TimescaleDB: `pg_dump -t --data-only` ra file
  rỗng 486 byte. Muốn trích thì `\copy (SELECT ...) TO STDOUT WITH CSV HEADER`
  và **đối chiếu số dòng**.

---

## 2. Task 1 — Định nghĩa chế độ thị trường, đo được và tái lập được

File mới: `scripts/market_regime.py`.

Vì không có VNINDEX, dựng thước đo **độ rộng thị trường (breadth)** từ chính
`bars_daily`. Định nghĩa đề xuất — dùng đúng cái này, đừng tự đổi:

> **breadth(d)** = tỷ lệ mã có `close(d) > SMA200(close, d)`, tính trên các
> mã có đủ 200 phiên lịch sử tính tới ngày `d`.

Rồi chia ba chế độ bằng ngưỡng **cố định, đặt trước, không tinh chỉnh**:

| Chế độ | Điều kiện |
|---|---|
| `RISK_ON` | breadth ≥ 0,60 |
| `NEUTRAL` | 0,40 ≤ breadth < 0,60 |
| `RISK_OFF` | breadth < 0,40 |

Hai ngưỡng 0,40/0,60 là **giả định có chủ ý**, không phải kết quả tối ưu
hoá. Ghi rõ trong báo cáo rằng chúng được chọn trước khi nhìn kết quả. Nếu
sau này ai đó muốn dò ngưỡng tốt nhất, đó chính là hành vi sinh ra số liệu
dối — không làm trong brief này.

**Bắt buộc:**
- Hàm thuần: `compute_breadth(bars_by_symbol, as_of) -> float` và
  `classify_regime(breadth) -> str`, tách khỏi phần đọc DB, để test được
  mà không cần DB.
- Chống nhìn trộm tương lai (look-ahead): breadth ngày `d` chỉ được dùng
  dữ liệu **tới hết ngày `d`**. Nếu quyết định giao dịch ngày `d` thì phải
  dùng `breadth(d-1)`. **Đây là lỗi dễ mắc nhất và nó làm mọi con số đẹp
  lên một cách giả tạo** — phải có test riêng cho nó (xem Task 4).
- Loại 245 mã back-adjust hỏng như `measure_strategy.py` đang làm (xem
  `ever_liquid` và bộ lọc hiện có, dùng lại chứ đừng viết lại).

**Đầu ra kiểm chứng được:** một file `docs/superpowers/research/2026-09-02-breadth-daily.csv`
gồm `date,breadth,regime` cho 2016-01-04 → 2026-08-28, kèm bảng đếm số phiên
mỗi chế độ. Nếu một chế độ chiếm dưới 10% số phiên, **dừng lại và báo cáo** —
nghĩa là ngưỡng phân loại vô dụng, và đó là phát hiện chứ không phải lỗi.

---

## 3. Task 2 — Đo từng chiến lược theo từng chế độ, CHỈ trên kỳ trong mẫu

**Kỳ trong mẫu: 2016-01-04 → 2022-12-31.**
**Kỳ ngoài mẫu: 2023-01-01 → 2026-08-28. TUYỆT ĐỐI KHÔNG ĐỘNG TỚI Ở TASK NÀY.**

Với mỗi chiến lược trong `STRATEGIES` (`daily_breakout`, `octopus_pullback`,
`sma_cross`), chạy backtest trên kỳ trong mẫu và **quy kết từng giao dịch về
chế độ tại ngày mở lệnh**. Dùng lại `run_backtest` của `trading/backtest.py`,
không viết lại vòng lặp backtest.

Đầu ra: một bảng 3×3.

```
chien luoc        RISK_ON        NEUTRAL        RISK_OFF
daily_breakout    <PnL, so lenh, ty le thang>   ...
octopus_pullback  ...
sma_cross         ...
```

Kèm hai mốc so sánh **bắt buộc phải có**, nếu không bảng trên vô nghĩa:
1. Mua-và-giữ cùng kỳ, cùng rổ mã.
2. Chiến lược đơn tốt nhất chạy suốt kỳ, không chuyển đổi.

---

## 4. Task 3 — Quy tắc chuyển đổi: đóng băng rồi mới thử ngoài mẫu

1. Từ bảng Task 2, viết ra **một** quy tắc chuyển đổi, dạng
   `regime -> ten_chien_luoc` (hoặc `KHONG_GIAO_DICH`). Ví dụ:
   `RISK_ON -> daily_breakout, NEUTRAL -> KHONG_GIAO_DICH, RISK_OFF -> KHONG_GIAO_DICH`.
2. **Ghi quy tắc đó vào báo cáo TRƯỚC khi chạy kỳ ngoài mẫu.** Đây là bước
   quan trọng nhất của cả brief. Viết ra rồi mới chạy.
3. Chạy đúng quy tắc đã đóng băng trên **kỳ ngoài mẫu 2023 → 2026-08**.
4. So với ba mốc: mua-và-giữ, chiến lược đơn tốt nhất, và chính quy tắc đó
   trên kỳ trong mẫu.

**Cấm tuyệt đối:** nhìn kết quả ngoài mẫu rồi quay lại sửa ngưỡng breadth,
sửa quy tắc, hay đổi kỳ. Nếu ngoài mẫu cho kết quả xấu thì **báo cáo con số
xấu đó**. Một quy tắc thất bại ngoài mẫu là thông tin có giá trị; một quy
tắc được chỉnh cho đẹp là thông tin sai lệch và tốn tiền thật về sau.

Nếu bạn thấy mình muốn thử quy tắc thứ hai: được, nhưng phải **khai báo cả
hai** trong báo cáo, kèm số lần đã thử. Thử 10 quy tắc rồi chỉ báo cáo cái
tốt nhất là dối, dù mỗi bước đều đúng kỹ thuật.

---

## 5. Task 4 — Test

File mới `tests/test_market_regime.py`. Tất định, không chạm DB, không
`sleep`, không so giờ tường (đồng hồ Windows ~15,6 ms làm test giờ tường
chập chờn — đã dính 01/09).

Bắt buộc bốn test:

1. `test_breadth_dem_dung` — rổ dựng tay, 3/5 mã trên MA200 ⇒ breadth = 0,6.
2. `test_phan_loai_dung_nguong` — 0,60 ⇒ `RISK_ON`; 0,5999 ⇒ `NEUTRAL`;
   0,40 ⇒ `NEUTRAL`; 0,3999 ⇒ `RISK_OFF`. Kiểm đúng hai biên.
3. `test_khong_nhin_trom_tuong_lai` — thêm bar của ngày `d+1` vào dữ liệu
   **không được làm đổi** `breadth(d)`. Đây là test quan trọng nhất file này.
4. `test_ma_thieu_lich_su_bi_loai` — mã có dưới 200 phiên không được tính
   vào mẫu số.

### Kiểm chứng phá hoại (bắt buộc, theo lệ dự án)

Với test 1 và test 3: cố tình phá code cho test đỏ, **dán nguyên văn output
đỏ vào báo cáo**, rồi khôi phục. Riêng test 3, cách phá đúng là cho hàm
breadth dùng cả bar tương lai — nếu test vẫn xanh thì test đó vô dụng và
phải viết lại.

---

## 6. Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | `market_regime.py` | `uv run pytest tests/test_market_regime.py -v` → 4 passed |
| 2 | Phá hoại | output đỏ nguyên văn test 1 và test 3 trong báo cáo |
| 3 | Chuỗi breadth | file CSV 2016→2026-08 + bảng đếm số phiên mỗi chế độ |
| 4 | Bảng 3×3 kỳ trong mẫu | bảng + 2 mốc so sánh, kèm lệnh đã chạy để tái lập |
| 5 | Quy tắc đóng băng | ghi trong báo cáo **trước** mục kết quả ngoài mẫu |
| 6 | Kết quả ngoài mẫu | so với 3 mốc, kể cả khi xấu |
| 7 | Không hồi quy | `uv run pytest -m "not integration" -q` — xem mục 8 trước |
| 8 | Lint | `uv run ruff check trading tests scripts` sạch |

Mọi con số trong báo cáo phải kèm **lệnh chính xác để chạy lại**. Số không
tái lập được thì không tính — đây là lý do hai báo cáo tuần trước bị bác.

---

## 7. Việc KHÔNG làm

- **Không đụng `trading/`**, kể cả thêm file mới (sẽ kích cảnh báo lệch
  triển khai).
- **Không sửa engine.** Việc nối chế độ vào engine là giai đoạn 2, chỉ khởi
  động nếu Task 3 sống sót — xem mục 8.
- **Không thêm chiến lược mới.** Chỉ dùng 3 cái đã đăng ký.
- **Không dò tìm ngưỡng breadth tối ưu.**
- **Không sửa `test_backtest_cli.py`** dù thấy nó đỏ — xem mục 8.

---

## 8. Hai thứ Claude nợ, đã biết, agent đừng đụng

**Một test đang đỏ, không phải do bạn:**

```
FAILED tests/test_backtest_cli.py::test_cli_registry_no_longer_offers_sma_cross
assert 'sma_cross' not in {... 'sma_cross': ...}
```

Test này khẳng định `sma_cross` đã gỡ có chủ ý (`11d1c7b`). Claude thêm nó
trở lại ở `711683a` (01/09) để đo lại và không xử lý mâu thuẫn. Ở bước 7,
đối chiếu là **không có test nào đỏ THÊM** ngoài cái này.

**Đường ống chiến lược đang đứt giữa backtest và engine.** Đo được 02/09:

```
chien luoc         backtest   engine   thieu gi cho engine
sma_cross          OK         OK       []
daily_breakout     OK         OK       []
octopus_pullback   OK         HONG     ['last_crossover']
momentum_breakout  HONG       HONG     ['on_bar', 'warmup_bars']
momentum_rsi       HONG       HONG     ['on_bar', 'warmup_bars']
```

`octopus_pullback` backtest sạch nhưng nạp vào engine sẽ chết ngay bar đầu:
`engine/logic.py:44` gọi `last_crossover` vô điều kiện mỗi bar. Ngoài ra
`engine/main.py:71` đóng cứng `SmaCrossStrategy()`, `Config` không có trường
chiến lược, và `Protocol` ở `trading/strategy.py` khai thiếu `warmup_bars`
với `compute_crossover` — hai thứ `engine/main.py:81,91` thật sự gọi.

Đây là **giai đoạn 2**, chạm `trading/`, nên phải sau phiên 03/09. Ghi ở đây
để agent biết vì sao brief này dừng ở đo, và để không ai tưởng là sót.
