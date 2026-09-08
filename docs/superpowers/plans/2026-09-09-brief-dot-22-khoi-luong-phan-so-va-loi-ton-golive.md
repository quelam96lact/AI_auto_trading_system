# Brief đợt 22 — Khối lượng phân số cho crypto 1H + lỗi tồn chuẩn bị go-live

Ngày giao: 09/09/2026
Base: `7cbc24b` (main), cây làm việc sạch, 609 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).
Quyết định chủ dự án: **giao dịch crypto khung 1H**, vốn thật dưới 500 USDT, đòn bẩy trên
3x, tự động có cầu dao (chốt 08/09, xem brief 21 Phần C).

---

## 1. Chốt chặn phải mở trước mọi thứ khác

Trước khi viết brief này tôi kiểm một câu hỏi: hệ thống hiện tại, ở vốn thật dự kiến, sinh
được bao nhiêu lệnh trên khung 1H?

### 1.1. Số đo — tôi tự chạy, không phải suy đoán

```
=== 1H, von 500 USDT (von that du kien) ===
daily_breakout     |  +0.00 |  +0.00 | 0 lenh
octopus_combo      |  +0.00 |  +0.00 | 0 lenh
octopus_pullback   |  +0.00 |  +0.00 | 0 lenh
sma_cross          |  +0.00 |  +0.00 | 0 lenh

=== 1H, von 5.000 USDT ===
daily_breakout     |  +0.00 | -630.28 | 0 lenh
octopus_combo      |  +0.00 | -630.28 | 0 lenh
octopus_pullback   |  +0.00 | -630.28 | 0 lenh
sma_cross          |  +0.00 | -630.28 | 0 lenh
```

**Ở vốn 500 USDT: 0 lệnh, cả bốn chiến lược, cả hai mã. Ngay cả mua-và-giữ cũng ra 0,00** —
tức là không mua nổi một đơn vị nào. Ở 5.000 USDT vẫn 0 lệnh chiến lược; mua-và-giữ ra
−630,28 vì mua được 1 ETH.

**Hệ thống crypto 1H, dựng đúng theo thiết kế hiện tại, sẽ câm hoàn toàn ở vốn dự kiến.**

### 1.2. Nguyên nhân — đọc được từ code, không phải phỏng đoán

`trading/risk.py:103-105`:

```python
qty_atr = int(
    (self.capital * self.risk_pct / (atr * self.atr_multiplier))
    // self.lot_size
)
```

với `risk_pct = 0.01` (dòng 14) và `lot_size: int = 100` (dòng 19).

Với vốn 500 USDT, ngân sách rủi ro mỗi lệnh là **5 USDT**. Giá BTC trong kỳ đo 1H đi từ
62.766,1 lên 125.977,4; ETH từ 3.112,92 lên 4.933,86. `qty` là **số nguyên**, nên
`floor(5 / (ATR × mult))` luôn bằng **0**. Không có lệnh nào ra đời.

Thêm một tầng chặn nữa: `max_order_value_pct = 0.20` (dòng 12) — giá trị lệnh không được
vượt 20% vốn. Ở 500 USDT tức là 100 USDT, nhỏ hơn giá một đơn vị BTC hay ETH rất nhiều.

### 1.3. Và nó đã bóp méo chính báo cáo đợt 21

Đợt 21 báo "BTC-USDT sinh 0 lệnh ở mọi chiến lược khung 1H". Điều đó **đúng nhưng không phải
vì chiến lược không có tín hiệu** — mà vì BTC không sizing được ở vốn 100.000 USDT với
`lot_size = 1` (1 đơn vị BTC ≥ 62.766 USDT > 20% của 100.000).

Nâng vốn lên 10.000.000 USDT để BTC sizing được, cùng dữ liệu, cùng khung 1H:

| Chiến lược | Lệnh | PnL chiến lược | PnL mua-và-giữ |
|---|---:|---:|---:|
| daily_breakout | 35 | −308.189,03 | +2.448.331,49 |
| octopus_combo | 51 | −302.884,87 | +2.448.331,49 |
| octopus_pullback | 17 | −150.538,00 | +2.448.331,49 |
| sma_cross | 50 | −324.124,75 | +2.448.331,49 |

**BTC có tín hiệu, và cả bốn chiến lược đều lỗ trên BTC** — khoảng −1,5% đến −3,2% vốn,
trong khi mua-và-giữ +24,5%. Con số "0 lệnh" của đợt 21 đã che mất sự thật này.

Đây là lỗi của phép đo, không phải của agent đợt 21 — brief đợt 21 do tôi viết đã ghim
`--capital 100000` mà không kiểm xem mức vốn đó có sizing được BTC không.

### 1.4. Vì vậy đợt này KHÔNG xây đường lệnh BingX

Brief 21 Phần C xếp bước 3 là "ký request + đường chỉ đọc". **Bước đó phải lùi lại.** Xây
đường đặt lệnh cho một hệ thống không thể sinh lệnh là xây cho một cái không bao giờ chạy.

Đợt này làm đúng một việc ở phía crypto: **mở chốt chặn khối lượng phân số**, rồi đo lại ở
mức vốn thật. Xong mới quay về lộ trình Phần C.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi.
- **Không gọi SSI. Không gọi BingX** (kể cả endpoint công khai) — đợt này không cần dữ liệu
  mới, `bars_crypto` đã đủ tới 08/09.
- **Không tạo, không dùng API key BingX.** Không thêm biến vào `.env`, không mở `.env`.
- **Không viết đường đặt lệnh, không viết broker crypto.** Đó là bước 4-6 Phần C brief 21.
- Không in secret. `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 4 chỉ `SELECT`.
- **Không sửa** `PaperBroker`, `run_backtest`, `derivative_backtest`, `pattern_backtest`,
  `trading/strategies/*`.
- `trading/risk.py` **được sửa**, nhưng chỉ theo đúng Task 1 và phải giữ nguyên hành vi
  chứng khoán VN — xem 1.2 tiêu chí bất biến.
- Chỉ sửa file được nêu tên. Phát hiện ngoài phạm vi: báo cáo, không tự sửa.
- **Không xoá file nào, không commit, không push.**
- **Không kết luận thay chủ dự án.**

**GitNexus:** `npx gitnexus analyze` trước và sau. **`gitnexus_impact` cho `RiskManager` và
`size_buy` là bắt buộc** — đây là symbol nằm trên đường lệnh thật của chứng khoán VN, phải
báo blast radius trước khi sửa.

---

# PHẦN A — KHỐI LƯỢNG PHÂN SỐ

## Task 1 — Cho `RiskManager` hỗ trợ khối lượng phân số

### 1.1. Việc

Hiện `lot_size: int = 100` và `qty` là số nguyên. Chứng khoán VN đúng là giao dịch theo lô
100 và số nguyên — **không được đổi điều đó**. Nhưng crypto giao dịch theo bước phân số
(BingX: BTC 0,0001 / ETH 0,001 — con số này **chưa được xác minh từ API**, xem Task 3).

Yêu cầu: `RiskManager` chấp nhận `lot_size` là số thực, và `qty` trả về là số thực khi
`lot_size` là số thực. Cách làm cụ thể do agent chọn, nhưng phải thoả **cả bốn** tiêu chí ở
1.2, và phải giữ style code hiện có.

Gợi ý hướng đi (không bắt buộc): đổi kiểu `lot_size` thành `float`, thay
`int(x // lot_size)` bằng phép làm tròn xuống theo bội của `lot_size` không ép về `int`, và
giữ nguyên ngưỡng từ chối khi `qty < lot_size`.

**Cạm bẫy số thực:** `0.1 + 0.2 != 0.3` trong dấu phẩy động. Làm tròn xuống theo bội của
`0.0001` bằng phép chia trực tiếp sẽ sinh sai số kiểu `0.00019999999`. Agent phải xử lý
việc này và **viết một test riêng cho nó** (xem 1.2 tiêu chí 4).

### 1.2. Bốn tiêu chí — cả bốn đều phải xanh

**Tiêu chí 1 — Bất biến chứng khoán VN (quan trọng nhất).** Mọi test hiện có phải xanh
không sửa một dòng test nào. Đặc biệt `tests/test_real_orders.py` và test nào đụng
`lot_size=100`. Nếu agent thấy "cần sửa test cho hợp" ⇒ **dừng, báo cáo** — đó là dấu hiệu
hành vi VN đã bị đổi.

**Tiêu chí 2 — Tái hiện lỗi trước khi sửa.** Viết test **thất bại trên code hiện tại**:
`RiskManager(capital=500, lot_size=0.0001)` với ATR và giá của BTC phải sinh `qty > 0`.
Chạy trên code cũ, chụp lại `AssertionError`, dán vào báo cáo. Rồi mới sửa cho nó xanh.

**Tiêu chí 3 — Trần 20% vẫn có hiệu lực với số thực.** Test: `capital=500`,
`max_order_value_pct=0.20`, giá 125.977 ⇒ giá trị lệnh không được vượt 100 USDT.

**Tiêu chí 4 — Bước khối lượng chính xác.** Test: với `lot_size=0.0001`, mọi `qty` trả về
phải là bội đúng của `0.0001` khi kiểm bằng `round(qty / 0.0001) * 0.0001` với dung sai
`1e-9`. Test này tồn tại riêng để bắt cạm bẫy dấu phẩy động ở 1.1.

### 1.3. Kiểm chứng

- `uv run pytest -q` → **609 + số test mới**, 0 failed.
- `uv run ruff check trading tests scripts` sạch.
- `git diff trading/risk.py` — dán nguyên văn.
- `gitnexus_impact` cho `RiskManager` và `size_buy`, dán blast radius.
- Xác nhận `git diff` **rỗng** cho: `trading/paper_broker.py`, `trading/real_orders.py`,
  `trading/engine/main.py`, `config/config.yaml`.

---

## Task 2 — Cho `measure_crypto_strategies.py` nhận `--lot-size` phân số

### 2.1. Việc

`scripts/measure_crypto_strategies.py:313` hiện là:

```python
ap.add_argument("--lot-size", type=int, default=1, help="Kích thước lô (mặc định 1)")
```

`type=int` khiến không thể truyền `0.0001`. Đổi sang `type=float`, cập nhật `help`, và cập
nhật **mục 2 của docstring** (hiện ghi `lot_size = 1 (giả định...)`) cho khớp.

Giữ mặc định là `1` để mọi lệnh đã chạy ở đợt 21 tái lập được y nguyên.

### 2.2. Kiểm chứng — tái lập đợt 21 phải khớp tuyệt đối

Chạy lại đúng lệnh của đợt 21 và so với số đã ghi trong
`docs/superpowers/research/2026-09-08-dot-21-do-btc-eth-co-phi.md`:

```powershell
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 1.0
```

Phải ra **đúng** các số này, không sai một chữ số:

```
daily_breakout     |  -3,383.38 | -4,673.33 | 37 lenh
octopus_combo      |  -3,059.50 | -4,673.33 | 22 lenh
octopus_pullback   |    -334.57 | -4,673.33 |  2 lenh
sma_cross          |  -3,020.14 | -4,673.33 | 22 lenh
```

Lệch bất kỳ chữ số nào ⇒ Task 1 đã làm đổi hành vi ⇒ **dừng, báo cáo**.

---

## Task 3 — Tra bước khối lượng THẬT của BingX

### 3.1. Vì sao

Con số "BTC 0,0001 / ETH 0,001" xuất hiện trong báo cáo đợt 13 và được nhắc lại nhiều lần,
nhưng **chưa ai xác minh từ nguồn**. Cả Task 1 và Task 4 phụ thuộc vào nó. Đo bằng một con
số nghe lại là lặp đúng lỗi đã làm hỏng phép đo đợt 21.

### 3.2. Việc — và giới hạn

Endpoint đặc tả hợp đồng của BingX (`/openApi/swap/v2/quote/contracts` hoặc tương đương)
**là endpoint công khai, không cần API key**. Nhưng mục 2 cấm gọi BingX ở đợt này.

Vì vậy Task 3 **không gọi mạng**. Việc của agent:

1. Tra trong tài liệu BingX công khai (`bingx.com/en/support/` hoặc trang API docs) bước
   khối lượng tối thiểu và giá trị lệnh tối thiểu của `BTC-USDT` và `ETH-USDT` perpetual.
2. **Ghi rõ nguồn**: URL và ngày truy cập.
3. Nếu không tìm được nguồn chắc chắn: **ghi "chưa xác minh được"**, và Task 4 dùng
   `0.0001`/`0.001` với nhãn **"giả định, chưa xác minh"** ở mọi bảng.

**Cấm tuyệt đối:** ghi một con số mà không kèm nguồn hoặc không kèm nhãn "giả định".

---

## Task 4 — Đo lại khung 1H ở mức vốn THẬT

### 4.1. Sáu lần chạy

Dùng `--lot-size` phân số từ Task 1-3. Nếu Task 3 không xác minh được, dùng `0.0001` cho
BTC và `0.001` cho ETH và ghi nhãn giả định.

Vì hai mã có bước khác nhau, **chạy riêng từng mã**:

```powershell
# BTC-USDT, buoc 0.0001
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --cost-multiplier 2.0

# ETH-USDT, buoc 0.001
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --cost-multiplier 2.0
```

### 4.2. Điều PHẢI kiểm trước khi tin bất kỳ con số nào

**Số lệnh phải > 0.** Nếu vẫn ra 0 lệnh thì Task 1 chưa giải quyết được vấn đề, và mọi con
số PnL đều vô nghĩa. Trường hợp đó: **dừng, báo cáo số lệnh bằng 0**, không trình bày PnL
như một kết quả.

### 4.3. Kiểm chứng

- Chép **nguyên văn** cả 6 output.
- Giữ nguyên mọi dòng `CẢNH BÁO` về cỡ mẫu.
- Ghi rõ mỗi bảng dùng `--lot-size` bao nhiêu và con số đó **đã xác minh hay giả định**.

---

## Task 5 — Báo cáo crypto

Tạo `docs/superpowers/research/2026-09-09-dot-22-do-1h-von-that.md`, **đúng 4 mục**:

1. Output nguyên văn 6 lần chạy.
2. Bảng tổng hợp (mã × mức phí × chiến lược): số lệnh, PnL chiến lược, PnL mua-và-giữ.
3. Bảng đối chiếu ba mức vốn trên **cùng khung 1H**, để thấy vốn bóp méo phép đo thế nào:

   | Vốn | lot_size | BTC: lệnh | ETH: lệnh | Ghi chú |
   |---|---|---|---|---|
   | 100.000 | 1 (nguyên) | 0 | 22-37 | Số của đợt 21 |
   | 10.000.000 | 1 (nguyên) | 17-51 | — | Claude đo 09/09, chứng minh BTC có tín hiệu |
   | 500 | phân số | (điền) | (điền) | Đợt này |

4. Hạn chế đã biết — bắt buộc đủ năm điều:
   - Funding chưa mô hình hoá.
   - Bước khối lượng **đã xác minh hay giả định** (theo Task 3).
   - Chỉ 2 mã, cỡ mẫu nhỏ.
   - Khung 1H chỉ có dữ liệu từ 2024-04-27.
   - **Đòn bẩy chưa vào phép đo.** Chủ dự án chốt trên 3x, nhưng phép đo này không mô phỏng
     ký quỹ hay thanh lý. Vốn 500 USDT ở 3x tương đương giá trị danh nghĩa ~1.500 USDT, và
     một nhịp ngược 33% sẽ quét sạch tài khoản — điều mà bảng PnL không thể hiện.

**Không viết kết luận, không khuyến nghị.**

---

# PHẦN B — LỖI TỒN CHUẨN BỊ GO-LIVE

## Task 6 — Làm rõ `2026-01-02`: ngày nghỉ hay lỗ hổng dữ liệu

### 6.1. Bối cảnh

Đợt 21 báo 12 ngày làm việc không có bar. Tôi chạy lại thì ra **13** — agent bỏ sót
`2026-01-02` (thứ Sáu), và đó là dòng duy nhất không trùng ngày lễ phổ biến nào.

**Bẫy múi giờ, ghi lại để không lặp:** `ts::date` phụ thuộc `TimeZone` của phiên. Với `UTC`
câu SQL ra **46 dòng** (mọi thứ Sáu đều rỗng — giả tạo do dời múi giờ); với
`Asia/Ho_Chi_Minh` ra **13 dòng**. Mọi truy vấn ngày tháng trên `bars_daily` **phải** ghim
múi giờ.

### 6.2. Việc

Xác định `2026-01-02` là ngày nghỉ thật hay lỗ hổng dữ liệu, bằng **ba nguồn trong hệ
thống** — không đoán:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
-- 1. Bar 5 phut hom do co khong?
SELECT count(*), count(DISTINCT symbol) FROM bars WHERE ts::date = '2026-01-02';
-- 2. Chi so co khong? (ngay nghi thi VNINDEX cung khong co)
SELECT * FROM index_values WHERE ts::date = '2026-01-02';
-- 3. Backfill co ghi nhan da chay ngay do khong?
SELECT * FROM backfill_progress WHERE updated_at::date BETWEEN '2026-01-01' AND '2026-01-05';
```

Và đối chiếu các ngày liền kề (`2025-12-31`, `2026-01-05`) làm mốc so sánh.

**Kết luận cho phép đưa ra:** chỉ hai khả năng, kèm bằng chứng — "không có dữ liệu ở cả ba
nguồn ⇒ nhiều khả năng là ngày nghỉ" hoặc "có dữ liệu ở nguồn X ⇒ là lỗ hổng của
`bars_daily`". **Không được tự thêm vào `config.yaml`** dù kết luận là gì.

### 6.3. Kiểm chứng

Chép nguyên văn output cả bốn truy vấn + bảng đối chiếu + kết luận kèm bằng chứng.
`git diff config/config.yaml` rỗng.

---

## Task 7 — Kiểm engine có còn câm không

### 7.1. Vì sao

`CLAUDE.md` ghi gói K (06/09) đã sửa phần lớn lỗi "engine câm", nhưng **HII vẫn câm vì lý do
khác**. Trước go-live cần biết trạng thái hiện tại, và repo đã có sẵn công cụ.

Phần A của đợt này vừa chứng minh cùng một lớp lỗi trên crypto: **ngưỡng sizing hiệu chỉnh
cho một quy mô vốn, áp lên quy mô khác, làm hệ thống câm mà không báo lỗi.** Đáng kiểm xem
đường VN có đang dính biến thể nào của lỗi đó không.

### 7.2. Việc

```powershell
uv run python scripts/check_silent_engine.py --config config/config.yaml
```

Chỉ **chạy và báo cáo**. Không sửa gì dựa trên kết quả — nếu phát hiện câm, đó là đầu vào
cho một brief riêng.

### 7.3. Kiểm chứng

Output nguyên văn + exit code. Nếu script cần tham số khác: đọc `--help`, ghi lệnh thật.

---

## Task 8 — `/app` thuộc root trong image Docker

### 8.1. Việc

Đợt 20 phát hiện: trong image mới, `/app` thuộc `root` còn `.venv`/`trading`/`config` thuộc
`appuser`. Không gây hại hiện tại (ứng dụng không ghi vào `/app`), nhưng lệch với ý định của
`Dockerfile`.

Sửa: cho `/app` thuộc `appuser`. Một dòng, đặt **sau** `useradd` và **trước** các `COPY`.

### 8.2. Kiểm chứng — build ra tag riêng, KHÔNG đụng stack đang chạy

```powershell
docker build -t dot22-test:new .
docker run --rm --entrypoint sh dot22-test:new -c "id; stat -c '%U %n' /app /app/.venv /app/trading /app/config"
docker run --rm --entrypoint python dot22-test:new -c "import trading.collector.main, trading.engine.main; print('OK')"
docker images dot22-test:new --format "{{.Size}}"
```

- Cả **bốn** đường dẫn phải thuộc `appuser`.
- Import cả hai entrypoint phải OK.
- Kích thước không được tăng quá 2 MB so với 227 MB.
- `docker ps` vẫn 6 container `Up`, **không container nào bị restart**.
- **Không** `docker compose build`, **không** `docker compose up`. Triển khai là việc riêng.

---

## 3. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Task 1: phải sửa test cũ mới xanh | Ngay — dấu hiệu đã đổi hành vi VN |
| Task 1: `gitnexus_impact` báo HIGH/CRITICAL | Báo cáo blast radius, chờ tôi duyệt |
| Task 2: tái lập đợt 21 lệch dù một chữ số | Ngay |
| Task 3: không tìm được nguồn | Không dừng — ghi "chưa xác minh", đi tiếp |
| Task 4: vẫn 0 lệnh | Dừng, báo cáo 0 lệnh, **không trình bày PnL** |
| Task 6: cần sửa `config.yaml` | Ngay — task chỉ đọc |
| Task 8: kích thước image tăng > 2 MB | Báo cáo, không tự tối ưu thêm |
| Bất kỳ lúc nào cần gọi BingX hoặc SSI | Ngay |

---

## 4. Báo cáo nghiệm thu — đúng 10 mục

1. `npx gitnexus analyze` trước.
2. Task 1: `gitnexus_impact` + test tái hiện lỗi (ảnh chụp `AssertionError` trên code cũ) +
   `git diff trading/risk.py` + 4 tiêu chí + pytest/ruff.
3. Task 2: `git diff` + tái lập đợt 21 khớp tuyệt đối.
4. Task 3: bước khối lượng + **nguồn và ngày truy cập**, hoặc "chưa xác minh được".
5. Task 4: output nguyên văn 6 lần chạy.
6. Task 5: đường dẫn + nội dung file báo cáo.
7. Task 6: 4 truy vấn + kết luận kèm bằng chứng + `git diff config.yaml` rỗng.
8. Task 7: output + exit code.
9. Task 8: 4 output Docker + `docker ps`.
10. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`, pytest, ruff.

Kỳ vọng mục 10: chỉ `trading/risk.py`, `scripts/measure_crypto_strategies.py`, `Dockerfile`,
file test mới, file báo cáo mới, cộng `AGENTS.md`/`CLAUDE.md`. **Không** `config/config.yaml`,
**không** `trading/paper_broker.py`, **không** `trading/real_orders.py`.

---

## 5. Việc KHÔNG thuộc đợt này

- **Không** viết đường đặt lệnh BingX, không tạo API key, không gọi BingX.
- **Không** triển khai image mới (Task 8 chỉ build ra tag thử nghiệm).
- **Không** điền `holidays` (Task 6 chỉ điều tra).
- **Không** sửa engine dù Task 7 phát hiện câm.
- **Không** quyết định có giao dịch BTC/ETH hay không.

## 6. Sau đợt này

Nếu Task 4 cho ra số lệnh > 0, chủ dự án có lần đầu tiên một phép đo **ở đúng mức vốn thật,
đúng khung 1H, đúng bước khối lượng**. Đó mới là dữ liệu để quyết cổng bước 2 của Phần C
brief 21 — cổng mà đợt 21 chưa đủ dữ liệu để mở.

Nếu Task 4 vẫn ra 0 lệnh, kết luận thay đổi hẳn: **vốn 500 USDT là quá nhỏ cho họ chiến lược
này ở khung 1H**, và lựa chọn còn lại là tăng vốn hoặc đổi cách sizing — cả hai đều là quyết
định của chủ dự án, không phải việc agent tự chọn.
