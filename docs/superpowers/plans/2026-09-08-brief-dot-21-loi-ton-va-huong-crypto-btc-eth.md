# Brief đợt 21 — Lỗi tồn còn mở + bước đầu tiên của hướng crypto BTC/ETH

Ngày giao: 08/09/2026
Base: `4d4ee10` (main), cây làm việc sạch, 609 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).

---

## 1. Trước hết: ba việc tôi tưởng còn mở, kiểm lại thì ĐÃ ĐÓNG

Tôi kiểm từng mục trong danh sách tồn thay vì tin trí nhớ. Ba mục sau **không giao**,
vì đã được sửa ở các đợt trước:

| Việc | Tưởng là | Thực tế |
|---|---|---|
| `_print_safe` có 3 bản trùng (mã B2) | Còn mở | **Đã gộp.** `git grep "def _print_safe"` chỉ ra **một** dòng: `trading/alerts.py:12` |
| Snapshot vị thế không có kiểm tra độ cũ | Còn mở | **Đã có fail-safe.** `trading/real_orders.py:16` ghi rõ "Brief dot 10 Task 2 (P1): Fail-safe do cu cho vi the", kèm hai nhánh báo lỗi ở dòng 54 và 210 |
| `measure_crypto_strategies.py` đo không trừ phí | Còn mở | **Đã trừ phí.** Dòng 96 và 262: `fee_rate: float = BINGX_PERP_TAKER`. Chỉ có **docstring dòng 8 là cũ**, vẫn ghi `fee_rate=0.0` — xem Task 1 |

Rút ra: danh sách lỗi tồn thật sự còn mở **ngắn hơn nhiều** so với những gì được nhắc lại
qua các đợt. Phần lớn đã đóng ở đợt 10-17. Đợt này vì thế nhẹ ở phần sửa lỗi và nặng ở
phần đo lường crypto.

---

## 2. Nói thẳng về "bắt đầu giao dịch BTC/ETH"

Chủ dự án nêu định hướng bắt đầu giao dịch cặp BTC và ETH. Trước khi lập kế hoạch, có ba
sự thật phải đặt lên bàn — không phải để phản đối định hướng, mà để kế hoạch đi đúng bước.

### 2.1. Repo hiện KHÔNG có bất kỳ đường đặt lệnh BingX nào

```
git grep -i "bingx" -- trading/ scripts/  |  lọc order|trade|place|auth|sign|api_key
=> rỗng
```

Thứ đang có chỉ là **klines công khai** (`scripts/bingx_klines.py`, endpoint
`/openApi/swap/v3/quote/klines`, không cần API key). Không có ký request, không có
xác thực, không có đặt/huỷ lệnh, không có đồng bộ vị thế, không có broker perpetual.

Nghĩa là khoảng cách từ "có dữ liệu" tới "giao dịch thật" còn nguyên vẹn — không phải một
brief làm xong.

### 2.2. Mọi con số crypto DƯƠNG đã có đều chưa đứng vững

Báo cáo hybrid (`2026-09-06-bao-cao-octopus-combo-hybrid.md` §2.2) nêu con số hấp dẫn:

| Mô hình | Tổng lệnh | PnL Net | So Buy & Hold |
|---|---:|---:|---|
| Buy & Hold baseline | — | +146.744,65 USDT | baseline |
| Hybrid (kTP=2,3), Long-only | 8.357 | +775.184,95 USDT | "Gấp 5,28× B&H" |

Hai lý do chưa dùng được:

**(a) Phí ăn hết phần lãi.** Docstring `trading/crypto_fees.py` đã ghi sẵn phép tính này:
phí tính trên **giá trị danh nghĩa**, vốn 100.000 USDT/mã ⇒ một vòng mua-bán tốn ~100 USDT.
Với 8.357 lệnh thì riêng phí đã cỡ **~835.700 USDT** — lớn hơn chính con số lãi +775.184.
Chưa kể **funding** của hợp đồng vĩnh cửu, thứ mà `crypto_fees.py` ghi rõ là **hạn chế đã
biết, chưa mô hình hoá**, và thường bất lợi cho phía LONG trong thị trường tăng.

**(b) Đợt 8 đã chứng minh bằng thực nghiệm rằng lãi đó không đến từ bộ lọc tín hiệu.**
Trích nguyên văn kết luận audit đợt 8
(`2026-09-06-dot-8-octopus-combo-registry-report.md` §3):

> "Điều này chứng minh bằng thực nghiệm — không chỉ bằng lập luận — rằng lợi nhuận dương
> được quảng cáo trong các báo cáo hybrid phụ thuộc hoàn toàn vào cơ chế khớp lệnh
> BUY STOP/SL/TP cố định, không phải vào bản thân bộ lọc tín hiệu."

Khi đo trung thực qua `run_backtest`, `octopus_combo` lỗ **−9.826.136.733 VND**, nặng hơn
cả octopus gốc (−1.615.319.902).

### 2.3. Dữ liệu crypto đang cũ 6 ngày

`bars_crypto` có 20 mã, cả `1d` lẫn `1h`, nhưng **`max(ts) = 2026-09-02`** trên mọi mã.
Hôm nay 08/09. Riêng BTC/ETH:

```
BTC-USDT | 1d | 1938 nến | 2021-05-14 -> 2026-09-02
BTC-USDT | 1h | 20598    | 2024-04-27 -> 2026-09-02
ETH-USDT | 1d | 1935     | 2021-05-14 -> 2026-09-02
ETH-USDT | 1h | 20598    | 2024-04-27 -> 2026-09-02
```

Lưu ý tên mã: repo dùng **`BTC-USDT`/`ETH-USDT` có gạch nối** (quy ước BingX), không phải
`BTCUSDT`. Mọi lệnh trong brief này dùng đúng dạng có gạch nối.

### 2.4. Vì vậy đợt này làm bước 1, không phải bước cuối

Lộ trình tới giao dịch crypto thật, để chủ dự án thấy toàn cảnh. **Chi tiết từng bước ở
Phần C.**

| Bước | Việc | Trạng thái |
|---|---|---|
| **1** | **Đo BTC + ETH riêng, có phí, có kiểm tra độ nhạy chi phí** | **Đợt này (Task 4-5)** |
| 2 | Cổng quyết định của chủ dự án: có đi tiếp không | Chờ bước 1 |
| 3 | Ký request HMAC + đường **chỉ đọc** (số dư, vị thế, đặc tả hợp đồng) | Brief riêng |
| 4 | Mô hình hoá funding + broker perpetual (paper) | Brief riêng |
| 5 | Cầu dao, rủi ro đòn bẩy, chạy **shadow mode** 24/7 không gửi lệnh | Brief riêng |
| 6 | Bật lệnh thật, vốn dưới 500 USDT, hạn mức cứng | Brief riêng |

Đợt này **chỉ làm bước 1**, và bước 1 **không cần viết dòng code chiến lược nào** — vì
`measure_crypto_strategies.py` đã có sẵn `--symbols`, đã mặc định trừ phí taker, và đã có
`--cost-multiplier` để thử độ nhạy. Đây là phép đo, không phải xây dựng.

Lý do làm bước 1 trước, và làm đúng cách này: nó lặp lại chính xác cách đợt 18 đã làm với
5 mã danh mục thật — đo trước, quyết sau, và đo trên **đúng rổ mã sẽ giao dịch** thay vì rổ
20 mã chung.

---

## 3. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi.
- **Không gọi SSI.** Đợt này không đụng gì tới chứng khoán VN ngoài Task 1 và Task 2.
- **BingX: chỉ gọi endpoint klines công khai** (`bingx_klines.py` đã có sẵn). Không tạo API
  key, không ký request, không gọi bất kỳ endpoint tài khoản/đặt lệnh nào.
- **Tôn trọng rate limit**: `bingx_klines.py` đã có sleep ≥1,1s và backoff trần 600s — không
  sửa các hằng số đó, không chạy song song nhiều tiến trình nạp.
- Không in secret. `.env` không sửa, không commit.
- **`config/config.yaml` không sửa** (kể cả dòng `holidays` — xem Task 3).
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 2 chỉ `UPSERT` vào `bars_crypto` qua
  script có sẵn; Task 4 chỉ `SELECT`.
- **Không sửa** `PaperBroker`, `run_backtest`, `derivative_backtest`, `pattern_backtest`,
  `trading/strategies/*`, `trading/crypto_fees.py`.
- Chỉ sửa file được nêu tên. Phát hiện ngoài phạm vi: báo cáo, không tự sửa.
- **Không xoá file nào, không commit, không push.**
- **Không kết luận thay chủ dự án.** Báo cáo chỉ trình bày số đo. Không viết "nên giao dịch
  BTC" hay "nên bỏ crypto" — đó là việc của chủ dự án sau khi có số.

**GitNexus:** `npx gitnexus analyze` trước và sau. `gitnexus_impact` cho symbol bị chạm ở
Task 1 và Task 3. `gitnexus_detect_changes()` khi xong.

---

# PHẦN A — LỖI TỒN CÒN MỞ

Ba task nhỏ, độc lập nhau, không cái nào chạm đường chạy thật.

## Task 1 — Sửa docstring sai của `measure_crypto_strategies.py`

### 1.1. Vấn đề

Dòng 8 của docstring ghi:

```
3. Phí: fee_rate=0.0, sell_tax_rate=0.0, slippage_bps=0.0, settle_days=0 (chưa trừ phí — kết quả lạc quan).
```

Nhưng code thật (dòng 96 và 262) đã là `fee_rate: float = BINGX_PERP_TAKER`. Docstring này
là tàn dư từ đợt 13, và nó **nguy hiểm hơn một comment cũ bình thường**: bất kỳ ai đọc file
này để hiểu con số đo được sẽ tưởng kết quả chưa trừ phí, rồi tự trừ phí lần nữa trong đầu.

### 1.2. Việc

Sửa **đúng mục 3 của docstring** cho khớp code thật: nêu `fee_rate = BINGX_PERP_TAKER`
(BingX perpetual VIP0 taker 0,05%), `sell_tax_rate=0.0`, `settle_days=0`, và giữ nguyên
cảnh báo rằng **funding chưa được mô hình hoá**. Không sửa mục 1, 2, 4. Không sửa code.

### 1.3. Kiểm chứng

- `git diff scripts/measure_crypto_strategies.py` chỉ có thay đổi trong khối docstring,
  **0 dòng code**.
- `uv run ruff check scripts` sạch.
- Dán diff vào báo cáo.

---

## Task 2 — Nạp bù dữ liệu crypto tới hiện tại

### 2.1. Việc

`bars_crypto` dừng ở `2026-09-02`. Nạp bù bằng script có sẵn, **chỉ hai mã của đợt này**:

```powershell
uv run python scripts/bingx_klines.py --symbols BTC-USDT,ETH-USDT --interval 1d
uv run python scripts/bingx_klines.py --symbols BTC-USDT,ETH-USDT --interval 1h
```

Nếu tham số CLI của script khác với dạng trên: **đọc `--help` và dùng đúng tham số của nó,
ghi lại lệnh thật đã chạy** — không sửa script cho khớp brief.

Script đã UPSERT an toàn khi chạy lại, nên chạy trùng ngày không hỏng dữ liệu.

### 2.2. Kiểm chứng

```sql
SELECT symbol, interval, count(*) n, min(ts)::date tu, max(ts)::date den
FROM bars_crypto WHERE symbol IN ('BTC-USDT','ETH-USDT')
GROUP BY symbol, interval ORDER BY symbol, interval;
```

- `max(ts)` phải tiến tới gần 08/09/2026 (nến ngày hôm nay có thể chưa đóng — chấp nhận).
- `min(ts)` **không được đổi** so với số ở mục 2.3 của brief (1d từ 2021-05-14; 1h từ
  2024-04-27). Nếu `min(ts)` lùi hoặc tiến ⇒ script đã ghi đè quá khứ, **dừng, báo cáo**.
- Số nến chỉ được **tăng**, không giảm.
- Chép nguyên văn bảng trước và sau.

---

## Task 3 — Lịch nghỉ lễ: báo cáo, KHÔNG tự điền

### 3.1. Vấn đề

`config/config.yaml` hiện có:

```yaml
# Danh sach nay CHUA day du cho phan con lai cua 2026 (chua tra lich nghi le).
holidays: ['2026-08-31', '2026-09-01', '2026-09-02']
```

Chính comment trong file tự thú là chưa đủ. Hệ quả đã biết: ngày lễ chưa khai báo làm cảnh
báo 2A ("dữ liệu ngừng chảy") của `heartbeat_check.py` kêu sai suốt ngày hôm đó.

### 3.2. Việc — và giới hạn của nó

**Agent KHÔNG được tự điền ngày lễ.** Ngày nghỉ lễ là dữ kiện pháp lý do nhà nước công bố;
đoán sai thì hoặc chuông kêu oan, hoặc tệ hơn, hệ thống im lặng vào một ngày thật sự có
giao dịch. Đây cũng là lý do `config/config.yaml` nằm trong danh sách cấm sửa ở mục 3.

Việc của agent chỉ gồm hai phần, đều là **đọc và báo cáo**:

1. Chạy đoạn SQL dưới đây để tìm **các ngày làm việc (T2-T6) từ 01/01/2026 tới hôm nay mà
   `bars_daily` có 0 mã** — tức ứng viên ngày nghỉ, suy ra từ dữ liệu thật:

   ```sql
   WITH days AS (
     SELECT generate_series('2026-01-01'::date, CURRENT_DATE, '1 day')::date d
   )
   SELECT d.d, EXTRACT(ISODOW FROM d.d) dow, COALESCE(c.n, 0) so_ma
   FROM days d
   LEFT JOIN (SELECT ts::date dd, count(DISTINCT symbol) n FROM bars_daily GROUP BY 1) c
     ON c.dd = d.d
   WHERE EXTRACT(ISODOW FROM d.d) < 6 AND COALESCE(c.n, 0) = 0
   ORDER BY d.d;
   ```

2. Trình bày kết quả thành bảng, **đánh dấu rõ** ngày nào đã có trong `holidays` và ngày nào
   chưa. Không kết luận ngày đó là lễ — chỉ nói "không có bar, chưa khai báo".

### 3.3. Kiểm chứng

- `git diff config/config.yaml` **rỗng**.
- Bảng kết quả trong báo cáo, kèm câu SQL đã chạy.

---

# PHẦN B — BƯỚC 1 CỦA HƯỚNG CRYPTO

## Task 4 — Đo BTC-USDT và ETH-USDT, có phí, có độ nhạy chi phí

### 4.1. Vì sao đo riêng hai mã

Mọi số crypto đã có đều đo trên **rổ 20 mã**. Nếu định hướng là giao dịch **đúng BTC và
ETH**, thì con số của rổ 20 mã không trả lời được câu hỏi đó — y hệt bài học đợt 18, nơi
octopus đo trên 439 mã ra âm nhưng đo trên đúng 5 mã danh mục thật lại ra dương.

Không suy ra được theo chiều nào cả. Phải đo.

### 4.2. Sáu lần chạy — không thêm, không bớt

Hai khung × ba mức chi phí. **Mọi lệnh chạy sau khi Task 2 đã nạp bù xong.**

```powershell
# Khung ngay
uv run python scripts/measure_crypto_strategies.py --interval 1d --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1d --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1d --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 2.0

# Khung 1 gio
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT,ETH-USDT --capital 100000 --cost-multiplier 2.0
```

`--cost-multiplier` nhân hệ số lên phí gốc. Ý nghĩa: `1.0` là BingX VIP0 taker đúng như công
bố; `1.5` và `2.0` là biên an toàn cho **funding chưa mô hình hoá + trượt giá**. Nếu kết quả
chỉ dương ở `1.0` và âm ở `1.5`, thì "edge" đó mỏng hơn phần chi phí chưa đo được — đó là
thông tin quan trọng hơn cả con số ở `1.0`.

**Không tự thêm mã, không tự đổi `--capital`, không tự thêm `--strategy`** (để mặc định
`all` để thấy cả ba chiến lược). Không chạy `--compare-lot-size`.

### 4.3. Kiểm chứng

- Chép **nguyên văn** output của cả 6 lần chạy vào báo cáo. Không tóm tắt, không làm tròn.
- Nếu một lần chạy báo `CẢNH BÁO` về cỡ mẫu nhỏ (như đợt 18 từng gặp với 33 lệnh),
  **giữ nguyên dòng cảnh báo đó trong báo cáo** — không cắt đi.

---

## Task 5 — Viết báo cáo kết quả

Tạo `docs/superpowers/research/2026-09-08-dot-21-do-btc-eth-co-phi.md`.

**Đúng bốn mục, không thêm mục thứ năm:**

1. **Output nguyên văn** cả 6 lần chạy (khối ```text).
2. **Bảng tổng hợp**: mỗi dòng là một tổ hợp (mã × khung × cost-multiplier × chiến lược),
   các cột: số lệnh, PnL chiến lược, PnL mua-và-giữ, chênh lệch.
3. **Bảng so sánh với các baseline đã có** — chỉ điền số, không bình luận:

   | Đợt | Đo trên | Khung | Phí | Kết quả |
   |---|---|---|---|---|
   | 13 | 20 mã crypto | 1d/1h | (điền từ báo cáo đợt 13) | |
   | hybrid | 20 mã crypto | 1h | **fee_rate=0** | +775.184,95 USDT / 8.357 lệnh |
   | **21** | **BTC-USDT, ETH-USDT** | 1d + 1h | taker ×1,0/1,5/2,0 | (điền) |

4. **Hạn chế đã biết của phép đo này** — bắt buộc nêu đủ bốn điều, không được bỏ điều nào:
   - **Funding chưa mô hình hoá** (`trading/crypto_fees.py` ghi rõ; bất lợi cho LONG trong
     thị trường tăng).
   - `lot_size = 1` là **giả định**, không phải bước khối lượng thật của BingX
     (BTC 0,0001 / ETH 0,001).
   - Chỉ 2 mã ⇒ cỡ mẫu nhỏ, dễ rơi vào bẫy ngẫu nhiên.
   - Khung `1h` chỉ có dữ liệu từ 2024-04-27, ngắn hơn khung `1d` (từ 2021-05-14) — hai
     khung **không so trực tiếp được với nhau**.

**Không viết mục "kết luận" hay "khuyến nghị".** Mục 4 là hạn chế, không phải kết luận.

---

## 4. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Task 2: `min(ts)` của `bars_crypto` thay đổi | Ngay, trước Task 4 |
| Task 2: BingX trả 429 / lỗi 100410 | Để script tự backoff. Nếu vẫn hỏng sau backoff: dừng, **không chạy lại tay** |
| Task 2: số nến giảm | Ngay |
| Task 3: cần sửa `config.yaml` mới làm tiếp được | Ngay — task đó cố ý chỉ đọc |
| Task 4: script đòi sửa code mới chạy được | Ngay, báo cáo, không tự sửa |
| Bất kỳ lúc nào cần API key BingX | Ngay — đợt này chỉ dùng endpoint công khai |

Nguyên tắc: **thấy lạ thì dừng và báo, đừng tự sửa cho chạy được.**

---

## 5. Báo cáo nghiệm thu — đúng 7 mục

1. `npx gitnexus analyze` trước.
2. Task 1: `git diff scripts/measure_crypto_strategies.py` + ruff.
3. Task 2: bảng `bars_crypto` trước/sau + lệnh thật đã chạy.
4. Task 3: SQL + bảng ngày không có bar + xác nhận `git diff config/config.yaml` rỗng.
5. Task 4: output nguyên văn cả 6 lần chạy.
6. Task 5: đường dẫn file báo cáo + nội dung nguyên văn.
7. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`, `uv run pytest -q`,
   `uv run ruff check trading tests scripts`.

Kỳ vọng mục 7: `git diff --stat HEAD` chỉ có `scripts/measure_crypto_strategies.py`
(docstring), file báo cáo mới, cộng `AGENTS.md`/`CLAUDE.md` nếu `analyze` sửa dòng đếm.
**Không** có `config/config.yaml`, **không** có file nào trong `trading/`.

---

## 6. Việc KHÔNG thuộc đợt này

Để tránh phình phạm vi, ghi rõ những gì **không** làm ở đây:

- **Không** viết broker perpetual, không viết đường đặt lệnh BingX (bước 3-6, Phần C).
- **Không** mô hình hoá funding (bước 4) — đợt này chỉ *nêu* nó như hạn chế.
- **Không** quyết định BTC/ETH có edge hay không — đó là quyết định của chủ dự án sau khi
  có số, giống hệt cách Tier 1 và Q-2 đang chờ.
- **Không** đụng `symbols`/`real_order_account` trong `config.yaml` (Q-2 vẫn treo).
- **Không** điền lịch nghỉ lễ (Task 3 chỉ báo cáo).
- **Không** chạm `.env`, không thêm biến BingX (xem Phần C §C.2).

---

# PHẦN C — LỘ TRÌNH TỚI GIAO DỊCH THẬT TRÊN BINGX

Phần này **không phải việc của đợt 21**. Nó là bản thiết kế đường đi, để mỗi bước sau có một
brief riêng và một cổng phải qua. Viết ra ở đây để không ai — kể cả tôi — nhảy cóc.

## C.1. Bốn quyết định chủ dự án đã chốt (08/09/2026)

| Quyết định | Chốt | Hệ quả thiết kế |
|---|---|---|
| Đòn bẩy | **Trên 3x** | Bắt buộc có module giá thanh lý + ký quỹ duy trì + chuông báo tiệm cận. Đây là tầng rủi ro repo chưa từng có cho crypto |
| Mô hình xác nhận | **Tự động, có cầu dao** | Không dùng lại `pending_real_orders` (mô hình người xác nhận của SSI). Cần cầu dao thay cho con người |
| Vốn khởi điểm | **Dưới 500 USDT** | Mọi hạn mức cứng neo theo con số này |
| API key | **Đã tạo trên sàn** | Nhưng **chưa có trong `.env`** — xem C.2 |

### Nói thẳng một lần, rồi thôi

Vốn dưới 500 USDT, đòn bẩy trên 3x, chạy tự động, trên một chiến lược **chưa có edge nào đo
được** — kết cục nhiều khả năng nhất là mất phần lớn số vốn đó. Điều này không có nghĩa là
sai. Nó có nghĩa là **mục tiêu thật của giai đoạn này là kiểm chứng đường lệnh, không phải
kiếm lời**, và 500 USDT là học phí cho việc đó.

Nhận đúng mục tiêu thì thiết kế mới đúng: mọi thứ dưới đây tối ưu cho **tính đúng đắn của
đường lệnh và các chốt an toàn**, không tối ưu cho lợi nhuận. Nếu sau vài tháng đường lệnh
chạy sạch mà PnL âm đúng như dự đoán, **đó vẫn là một đợt thành công** — vì thứ thu được là
một đường lệnh đã được chứng minh, dùng lại được khi nào có chiến lược thật sự có edge.

## C.2. API key — việc của chủ dự án, agent không được làm thay

`.env` hiện có 10 biến, **không biến nào là BingX**:

```
SSI_CONSUMER_ID, SSI_CONSUMER_SECRET, SSI_API_KEY, SSI_API_SECRET, SSI_PRIVATE_KEY,
DB_DSN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD
```

(`.env` đã được `.gitignore:4` loại trừ — đã kiểm.)

**Chủ dự án tự thêm** hai biến `BINGX_API_KEY` và `BINGX_API_SECRET`. Agent **không được**
mở, sửa, hay in nội dung `.env` trong bất kỳ bước nào.

**Ba điều kiện của key, chủ dự án tự kiểm trên giao diện BingX trước bước 3:**

1. **KHÔNG bật quyền rút tiền (withdraw).** Đây là điều kiện quan trọng nhất. Key bị lộ mà
   không có quyền rút thì thiệt hại giới hạn ở giao dịch sai; có quyền rút thì mất sạch.
2. **Khoá theo IP** nếu BingX cho phép — IP của máy chạy engine.
3. Chỉ bật quyền **perpetual futures**, không bật spot nếu không dùng.

Agent **không được tự kiểm quyền rút tiền bằng cách gọi thử endpoint rút tiền.** Bước 3 chỉ
xác nhận gián tiếp: gọi được endpoint đọc số dư là đủ chứng minh key hợp lệ.

## C.3. Bước 2 — Cổng quyết định (chủ dự án, không phải agent)

Sau khi có số của Task 4-5 đợt này, chủ dự án quyết một trong ba:

- **Đi tiếp** với chiến lược đã đo, chấp nhận số liệu như nó là.
- **Đi tiếp nhưng đổi chiến lược** — khi đó phải đo lại chiến lược mới trước, quay về bước 1.
- **Dừng** hướng crypto.

Không bước nào của C.4 trở đi được bắt đầu trước khi cổng này có câu trả lời.

## C.4. Bước 3 — Ký request + đường CHỈ ĐỌC

Brief riêng. Nội dung dự kiến:

- Module `trading/crypto/bingx_client.py`: ký HMAC-SHA256 theo đặc tả BingX, đọc key từ biến
  môi trường (**không** hằng số, **không** đọc file `.env` trực tiếp — dùng `os.environ`).
- Chỉ ba endpoint đọc: số dư, vị thế đang mở, **đặc tả hợp đồng** (`contracts`).
- **Cấm tuyệt đối** mọi endpoint đặt/huỷ/sửa lệnh trong bước này. Không có ngoại lệ.

**Cổng phải qua:**

- Gọi được cả ba endpoint, in ra số dư thật (làm tròn, không in key).
- **Báo cáo đặc tả thật của BTC-USDT và ETH-USDT**: khối lượng tối thiểu, bước khối lượng,
  giá trị lệnh tối thiểu, đòn bẩy tối đa cho phép. Báo cáo đợt 13 có nhắc "BTC 0,0001 /
  ETH 0,001" nhưng đó là **số nghe lại, chưa xác minh** — bước này phải lấy từ API và ghi rõ.
- Test có mock cho phần ký, không gọi mạng trong `pytest`.
- Xác nhận không có dòng nào gọi endpoint giao dịch: `git grep` các từ khoá `order`, `trade`,
  `position/close` trong module mới phải chỉ ra endpoint đọc.

## C.5. Bước 4 — Funding + broker perpetual (paper)

Brief riêng. Hai việc, làm đúng thứ tự:

**(a) Mô hình hoá funding.** Hiện `trading/crypto_fees.py` ghi rõ funding là *hạn chế đã
biết, chưa mô hình hoá*. Với đòn bẩy trên 3x và chạy 24/7, funding không còn là sai số nhỏ.
Cần: nạp lịch sử funding rate từ BingX vào bảng riêng, và cho `run_backtest` (hoặc một hàm
bọc ngoài) trừ funding theo số chu kỳ vị thế sống qua.

**(b) `CryptoPaperBroker`.** Mô phỏng khớp lệnh perpetual: không T+, có chiều short, có đòn
bẩy, có phí taker hai chiều, có funding. **Không sửa `PaperBroker`** hiện có — đó là đường
chứng khoán VN, nằm trong danh sách cấm sửa của mọi brief.

**Cổng phải qua:** đo lại BTC/ETH **có funding**, đặt cạnh số của đợt 21 (chưa có funding).
Chênh lệch giữa hai lần đo chính là cái giá của việc trước đây bỏ qua funding — con số đó
phải được ghi lại.

## C.6. Bước 5 — Cầu dao, rủi ro đòn bẩy, và SHADOW MODE

Đây là bước quan trọng nhất của cả lộ trình, và là bước dễ bị bỏ qua nhất.

**(a) Bảng DB riêng.** Không dùng lại `pending_real_orders` — bảng đó có cột `ssi_order_id`
và mô hình trạng thái của SSI. Cần `crypto_orders` và `crypto_positions` riêng.

**(b) Cầu dao — khác SSI ở một điểm cốt lõi.** `real_risk_state.halted_date` là kiểu `date`,
hợp lý cho thị trường có phiên. Crypto chạy 24/7 nên cầu dao phải là **`halted_until`
timestamptz**, và trần lỗ phải tính trên **cửa sổ trượt 24 giờ**, không theo ngày lịch.

**(c) Năm hạn mức cứng, đặt trong code, không đặt trong config** — để một dòng YAML gõ nhầm
không thể mở khoá:

| Hạn mức | Vì sao |
|---|---|
| Trần giá trị danh nghĩa tổng | Chốt chặn cuối. Một lỗi tính size không được phép mở vị thế 50x |
| Trần đòn bẩy | Ép ở phía mình, không tin cấu hình trên sàn |
| Trần lỗ 24 giờ trượt | Kích cầu dao, dừng vào lệnh mới |
| Trần số lệnh 24 giờ | Bắt vòng lặp lỗi sinh lệnh liên tục |
| Trần số lệnh liên tiếp thua | Dừng sớm khi chiến lược lệch pha thị trường |

**(d) Giá thanh lý.** Với đòn bẩy trên 3x, phải tính và ghi giá thanh lý cho mọi vị thế mở,
kèm chuông Telegram khi giá tiệm cận. `trading/derivative_risk.py` có sẵn cho phái sinh VN —
**đọc để tham khảo cách làm, không tái sử dụng trực tiếp** (VN30F khác perpetual về ký quỹ).

**(e) SHADOW MODE — chạy thật, không gửi lệnh.** Bật engine crypto chạy 24/7 trên dữ liệu
thật, sinh lệnh thật, ghi đầy đủ vào `crypto_orders` với trạng thái `shadow`, **nhưng không
gọi endpoint đặt lệnh**. Chạy tối thiểu **hai tuần liên tục**.

**Cổng phải qua trước khi được bật lệnh thật:**

- Shadow mode chạy ≥14 ngày không gián đoạn.
- Không lệnh shadow nào vi phạm bất kỳ hạn mức nào ở (c).
- Đối chiếu: PnL shadow tính tay khớp PnL backtest cùng kỳ, sai số giải thích được.
- Cầu dao đã được **thử kích có chủ đích** trong shadow (ép vượt trần lỗ giả lập) và đã dừng
  đúng.
- Chuông thanh lý đã kêu đúng ít nhất một lần trong thử nghiệm.

Bước này bắt gần hết lỗi đường lệnh mà không tốn một đồng nào. Bỏ qua nó để "tiết kiệm hai
tuần" là đổi hai tuần lấy toàn bộ số vốn.

## C.7. Bước 6 — Bật lệnh thật

Brief riêng, và là brief duy nhất trong lộ trình đụng tiền thật.

- Cờ `crypto_trading_enabled` mặc định **`false`**, mở tay, mô phỏng đúng cách
  `real_trading_enabled` đang bảo vệ đường SSI.
- Vốn nạp lên sàn **dưới 500 USDT**, và trần giá trị danh nghĩa ở C.6(c) neo theo con số này.
- **Mọi lệnh thật gửi một chuông Telegram**, không gộp, không tóm tắt.
- Tuần đầu: chủ dự án xem log mỗi ngày. Không phải vì không tin hệ thống, mà vì tuần đầu là
  lúc duy nhất phát hiện được lệch giữa shadow và thật khi thiệt hại còn nhỏ.
- Có sẵn quy trình **dừng khẩn**: một lệnh, đóng hết vị thế, tắt cờ. Viết ra và **thử trước**
  ở shadow, không phải viết lúc đang hoảng.

## C.8. Ba việc lộ trình này CỐ Ý không làm

1. **Không tối ưu tham số cho tới khi đường lệnh chạy sạch.** Tối ưu trên một đường lệnh còn
   lỗi là tối ưu vào nhiễu.
2. **Không mở rộng quá BTC và ETH** trong toàn bộ lộ trình. Thêm mã là thêm bề mặt lỗi, mà
   mục tiêu giai đoạn này là chứng minh đường lệnh.
3. **Không đụng gì tới đường SSI.** Hai hệ thống chạy song song, không dùng chung bảng, không
   dùng chung cầu dao, không dùng chung broker. Một sự cố bên crypto không được phép làm dừng
   đường chứng khoán VN, và ngược lại.
