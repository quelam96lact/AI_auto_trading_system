# Brief đợt 11 — Đo Octopus trên TOÀN RỔ bar 5 phút + đo trần độ sâu 5m của SSI

Ngày viết: 2026-09-06 | HEAD khi viết: `fb57469` | Người viết: Claude (planner)

---

## 0. Brief này phục vụ cái gì

Đợt 10 đo Octopus trên bar 5 phút cho đúng 3 mã trong `config/config.yaml` và ra
**12 lệnh / ~12.500 bar** — quá nhỏ để kết luận bất cứ điều gì. Chủ dự án đang
đứng trước 3 đường: (1) nới tham số cho khung 5m, (2) quay về bar NGÀY, (3) bỏ
họ chiến lược này.

**Brief này KHÔNG chọn hộ. Nó chỉ đi lấy hai con số còn thiếu để chọn.**

Đường (2) thực ra **đã có câu trả lời rồi, là KHÔNG**: khung ngày trên rổ đầy đủ
1.308 mã cho PF 0,74 / Sharpe −0,96 / −1.615.319.902 VND trên 1.514 lệnh của 439
mã sinh lệnh. Cỡ mẫu đó thừa sức kết luận, và nó lỗ. Nên brief này không giao
việc đo lại khung ngày — sẽ là lãng phí.

Còn lại đường (1) và (3), và cả hai đều chờ đúng hai câu hỏi:

- **Câu A:** trên khung 5m, với tham số GỐC, rổ đủ lớn, chiến lược có edge không?
- **Câu B:** SSI cho lùi bar 5 phút được bao xa? (quyết định đường (1) có khả thi
  về mặt dữ liệu hay không)

---

## 1. Sự thật về kho dữ liệu — đã đo, không phải giả định

Tôi đã truy vấn trực tiếp trước khi viết brief. Số liệu tại `fb57469`:

| Bảng | Số mã | Khoảng thời gian | Số bar |
|---|---|---|---|
| `bars` (5 phút) | **310** | 03/04/2026 → 04/09/2026, **104 ngày giao dịch** | 934.217 |
| `bars_daily` | 1.554 | 03/01/2016 → 03/09/2026 | 2.983.253 |

Phân bố ngày kết thúc của 310 mã trong `bars`:

| Ngày cuối | Số mã |
|---|---|
| 07/08/2026 | **294** |
| 13/08/2026 | 3 |
| 04/09/2026 | 3 (đúng rổ HII/IJC/AAA đang stream) |
| rải rác 19/06 → 05/08 | 10 |

→ **Cửa sổ dùng chung cho phần lớn rổ là 03/04 → 07/08/2026 = 87 ngày giao dịch**,
trung bình 3.004 bar/mã (min 1, max 4.616).

### Ba hệ quả phải nói thẳng, vì chúng đóng khung mọi kết luận sau này

**(a) Toàn bộ dữ liệu 5m nằm gọn trong kỳ Holdout của `trading/sampling.py`.**
Holdout daily là 01/01/2024 → 13/08/2026; dữ liệu 5m là 03/04 → 04/09/2026. Nghĩa
là cơ chế chia tập train/validation/holdout của đợt 9 **không áp được lên khung
5m** — không phải vì code sai, mà vì không có dữ liệu 5m nào nằm ngoài kỳ đó.

**(b) Vì vậy brief này CỐ Ý không tạo cơ chế chia tập riêng cho 5m.** Lý do phải
ghi rõ để sau này không ai tưởng là sót:
- Task 1 **không quét tham số** — chỉ đo đúng bộ tham số gốc. Không có tìm kiếm
  thì không có kênh overfit, nên không cần holdout để bảo vệ.
- 87 ngày, trừ ~20 ngày warmup của `DailyLiquidityTracker`, còn ~67 ngày. Cắt đôi
  nữa thì mỗi nửa mất ý nghĩa thống kê. Chia tập ở đây là nghi lễ, không phải kỷ luật.
- **Nếu sau này chủ dự án cho phép quét tham số trên 5m, PHẢI có brief riêng dựng
  cơ chế khoá trước** — không được quét chay trên số liệu của Task 1.

**(c) Trên bar 5m, Octopus KHÔNG còn là chiến lược đã thiết kế.** Đây là phép tính
số học, không phải ý kiến:

| Chỉ báo | Ý nghĩa trên bar NGÀY | Trên bar 5m thành ra | Số bar cần nếu muốn giữ nguyên ngữ nghĩa ngày |
|---|---|---|---|
| EMA(200) — lọc xu hướng | xu hướng 200 phiên (~10 tháng) | xu hướng **~4 ngày** | 200 × 51 = **10.200 bar** |
| EMA(9)/EMA(21) — cắt nhau | 9/21 phiên | ~1 giờ / ~2 giờ | 459 / 1.071 bar |
| MACD(12/26/9) | 12/26 phiên | ~1 / ~2 giờ | 612 / 1.326 bar |

Mã nhiều bar nhất trong kho có **4.719 bar**. Cần 10.200 bar chỉ riêng để warmup
EMA(200) theo ngữ nghĩa ngày. **Chênh hơn gấp đôi.** Tức là: chạy Octopus với ngữ
nghĩa gốc trên dữ liệu 5m hiện có là **bất khả thi về mặt dữ liệu**, không phải
khó — là không thể.

Nên Task 1 đo cái gì? Đo **đúng thứ engine đang thực sự chạy hôm nay**: EMA(200)
trên bar 5m, tức bộ lọc xu hướng 4 ngày. Đó là câu hỏi vận hành đúng đắn, và câu
trả lời của nó áp thẳng vào quyết định đường (1)/(3). Hạn chế này phải được ghi
nguyên văn vào báo cáo, không được lờ đi.

---

## 2. Giả định của brief (nêu rõ, không giấu)

1. `bars` là nến 5 phút. (Căn cứ: `scripts/measure_octopus_5m.py` đọc `storage.read_bars`
   và quy ước 51 bar/ngày.) **Lưu ý một chênh lệch tôi chưa giải thích được và
   không bịa lý do:** mã dày nhất là IJC có 4.719 bar / 104 ngày ≈ **45 bar/ngày**,
   thấp hơn 51 khoảng 12%. Giả thuyết hợp lý nhất là phiên nào không có khớp lệnh
   thì không sinh bar, nhưng **tôi chưa đo để xác nhận**. Nếu agent thấy dấu hiệu
   `bars` không phải 5 phút thuần thì **dừng và báo cáo**, đừng đo tiếp trên giả
   định sai.
2. **`exclusions.txt` KHÔNG áp dụng cho khung 5m.** Danh sách 245 mã đó sinh ra từ
   vấn đề *back-adjust của `bars_daily`*. `bars` là giá intraday thô. Áp nhầm sẽ
   vứt bỏ dữ liệu tốt. Nhiều script đo khung ngày có dùng file này — **đừng bắt
   chước sang script mới**.
3. Vốn 100.000.000 VND/mã, giống `measure_octopus_5m.py`, để hai script so được với nhau.
4. Chi phí: `FEE_RATE` (0,25%), `SELL_TAX_RATE` (0,1%), `SLIPPAGE_BPS` (5) —
   **import từ `trading.paper_broker`, tuyệt đối không gõ lại số**. Đợt 9 đã một
   lần gõ tay `0.0015` và làm vỡ cả hai bất biến cứng.

---

## 3. Task 1 — Đo Octopus tham số gốc trên toàn bộ rổ có bar 5m

### Mục tiêu
Trả lời Câu A với cỡ mẫu đủ: thay vì 3 mã / 12 lệnh, đo **cả 310 mã** có dữ liệu
trong `bars`.

### File được sửa / tạo
- **TẠO MỚI:** `scripts/measure_octopus_5m_universe.py`
- **TẠO MỚI:** `tests/test_measure_octopus_5m_universe.py`
- **KHÔNG ĐỤNG:** `scripts/measure_octopus_5m.py` (là mốc đối chiếu của Task 1 —
  sửa nó là mất mốc; **ngoại lệ duy nhất** là phá hoại tạm ở tiêu chí kiểm chứng
  số 4, phải trả lại nguyên trạng), `trading/backtest.py`, `trading/paper_broker.py`,
  `trading/metrics.py`, `trading/sampling.py`, `trading/strategies/octopus_pullback.py`,
  `config/config.yaml`.

### MỘT CÔNG THỨC, MỘT CHỖ — bắt buộc, đọc trước khi gõ dòng nào

`scripts/measure_octopus_5m.py:52` đã có sẵn `measure_symbol_5m(storage, symbol,
frm, to, capital, ...)` làm **đúng** phần đo một mã mà task này cần.

**Script mới PHẢI import và dùng lại hàm đó, TUYỆT ĐỐI không chép lại logic đo:**

```python
try:
    from measure_octopus_5m import measure_symbol_5m
except ImportError:
    from scripts.measure_octopus_5m import measure_symbol_5m
```

(Import module này an toàn: mọi thứ nặng đều nằm trong `main()` sau
`if __name__ == "__main__"`.)

Phần code MỚI của script chỉ gồm: liệt kê mã từ `bars`, vòng lặp qua các mã, và
**tầng tổng hợp danh mục** (gộp PnL, pool trade PnL, `portfolio_equity_curve`,
PF/expectancy/MDD/Sharpe, phân tán top/bottom). Nếu agent thấy mình đang gõ lại
`run_backtest(...)` với `fee_rate=...` thì **đã đi sai hướng** — dừng lại và
import.

Lý do không thương lượng: dự án này đã một lần trả giá vì gõ lại hằng số phí thay
vì import (`0.0015` của đợt 9 làm vỡ cả hai bất biến cứng), và
`DailyLiquidityTracker.current_avg()` có nguyên một đoạn docstring giải thích tại
sao hai chỗ tính cùng một công thức là lỗi. Đừng lặp lại lần thứ ba.

### Cách viết — bắt buộc, tránh bẫy đã sập nhiều lần
- **CẤM dùng `trading.config.load_config` và CẤM gọi CLI `python -m trading.backtest`.**
  `load_config` đòi `DB_DSN` + 5 biến môi trường SSI, thiếu là `KeyError` ngay.
  Đây là bẫy đã làm hỏng brief của chính tôi ba lần. Lấy DSN y hệt
  `scripts/measure_octopus_5m.py`: `resolve_dsn` từ `scripts/_db_common.py`, rồi
  `Storage(...)`. (Việc đọc bar là của `measure_symbol_5m` — script mới **không**
  gọi `storage.read_bars` trực tiếp.)
- Lấy danh sách mã bằng `SELECT DISTINCT symbol FROM bars ORDER BY symbol`
  (không đọc `config.yaml` — đây là toàn rổ, không phải rổ engine).
- **Không truyền override nào** vào `measure_symbol_5m` ngoài `capital`: để nguyên
  `fee_rate` / `sell_tax_rate` / `slippage_bps` mặc định (chúng đã trỏ sẵn vào
  `FEE_RATE` / `SELL_TAX_RATE` / `SLIPPAGE_BPS`). Tham số chiến lược cũng để
  nguyên mặc định — không nới, không tinh chỉnh, không quét.
- Thước đo tầng danh mục lấy từ `trading.metrics`: `profit_factor`, `expectancy`,
  `max_drawdown`, `sharpe`, `portfolio_equity_curve`. **Không tự viết lại công thức.**
- `sharpe` không có giá trị mặc định cho `periods_per_year` — cố ý. Gộp PnL theo
  NGÀY rồi truyền `periods_per_year=252.0`, giống `measure_octopus_5m.py:189`.
- Có cờ `--symbols HII,IJC,AAA` để giới hạn rổ (phục vụ tiêu chí kiểm chứng dưới đây).

### Phải in ra
1. Số mã có dữ liệu / số mã **sinh ít nhất 1 lệnh**. (Không đòi "số mã bị chặn bởi
   cổng thanh khoản" — `measure_symbol_5m` không trả về thông tin đó, và sửa nó để
   lấy được là vi phạm "KHÔNG ĐỤNG" ở trên.)
2. Tổng số lệnh, win rate, PnL chiến lược, PnL mua-và-giữ.
3. Profit factor, expectancy, max drawdown danh mục, Sharpe(252).
4. **Phân tán theo mã**: PnL của 5 mã lãi nhất và 5 mã lỗ nhất. (Một tổng số dương
   do đúng 1 mã kéo lên thì không phải edge — phải nhìn thấy được điều đó.)
5. Khối "HẠN CHẾ" in nguyên văn 3 ý: (i) chỉ 87 ngày giao dịch, **một chế độ thị
   trường duy nhất**; (ii) toàn bộ nằm trong kỳ holdout của khung ngày; (iii)
   EMA(200) trên 5m là bộ lọc xu hướng ~4 ngày, **không phải chiến lược đã thiết kế**.

### Tiêu chí kiểm chứng (verify được, không mơ hồ)
1. **Mốc đối chiếu cứng — quan trọng nhất.** Chạy
   `uv run python scripts/measure_octopus_5m_universe.py --symbols HII,IJC,AAA`
   phải ra **đúng 12 lệnh và PnL +787.149 VND**, khớp `measure_octopus_5m.py`.
   Lệch một đồng nghĩa là script mới sai ở đâu đó — **phải tìm ra và sửa, không
   được giải thích cho qua**. Dán output thô của CẢ HAI script cạnh nhau.
   *Mốc này kiểm cái gì:* vì phần đo một mã dùng chung hàm, nó **không** kiểm lại
   phép đo — nó kiểm **tầng mới**: liệt kê mã, vòng lặp, gộp PnL, pool trade PnL,
   `portfolio_equity_curve`, và PF/expectancy/MDD/Sharpe ở mức danh mục. Đó đúng
   là chỗ dễ sai nhất của task này.
2. Chạy toàn rổ, dán output thô đầy đủ.
3. Test: viết test chứng minh script **không** áp `exclusions.txt` và **không** đọc
   `config.yaml` để lấy rổ mã (đây đúng là hai lỗi dễ mắc nhất của task này).
4. Tự phá hoại để chứng minh phí thật sự chảy vào phép đo: **tạm thời** đổi mặc
   định `fee_rate: float = FEE_RATE` thành `0.0` tại `measure_octopus_5m.py:58`,
   chạy lại toàn rổ, chứng minh tổng PnL đổi số, rồi **khôi phục nguyên trạng**.
   Đây là **ngoại lệ duy nhất** của lệnh "KHÔNG ĐỤNG `measure_octopus_5m.py`" —
   "không đụng" nghĩa là không để lại thay đổi nào, phá hoại tạm rồi trả lại thì
   được. Dán số trước/sau. Khi nộp: `git diff scripts/measure_octopus_5m.py` phải
   **rỗng**, và `grep -rn "SABOTAGE"` phải rỗng.
5. `uv run ruff check trading tests scripts` sạch. `uv run pytest -m "not integration" -q` xanh.

---

## 4. Task 2 — Đo trần độ sâu lịch sử 5 phút của SSI

### Mục tiêu
Trả lời Câu B. Đây là câu hỏi sinh tử của đường (1): nếu SSI chỉ cho lùi ~4 tháng
thì kho 5m **không bao giờ** đủ sâu để chạy Octopus với ngữ nghĩa gốc, và đường (1)
chỉ còn nghĩa là "thiết kế một chiến lược 5m khác", chứ không phải "nới tham số".

**Nghi vấn đã có:** `bars` bắt đầu đúng 03/04/2026, và
`scripts/spike_ssi_history_depth.py:29` có `INTRADAY_BACK_DAYS = [125, 128, 129, 130]`
— dấu vết của một lần dò nhị phân đã chạm biên quanh 128 ngày. Rất khớp với việc
kho bắt đầu từ 03/04. Nhưng **suy luận khớp không phải là số đo** — phải đo.

### File được sửa
- **SỬA DUY NHẤT 1 DÒNG:** `scripts/spike_ssi_history_depth.py:29`, đổi
  `INTRADAY_BACK_DAYS` thành thang rộng hơn: `[60, 90, 120, 130, 150, 180, 270, 365]`.
- **KHÔNG đụng bất cứ dòng nào khác của file đó**, không đụng `trading/collector/`.

### Cách chạy
```
uv run python -m scripts.spike_ssi_history_depth
```

### Ràng buộc riêng của task này (đọc kỹ)
- Script gọi **API dữ liệu SSI, chỉ đọc**. Tuyệt đối không đụng tới bất kỳ endpoint
  đặt lệnh / huỷ lệnh nào.
- Script gọi `load_config` và `ensure_authenticated` — **đây là ngoại lệ có chủ ý**
  của quy tắc "cấm load_config" ở Task 1, vì nó cần xác thực SSI thật.
- **Nếu token hết hạn / cần OTP: DỪNG LẠI, báo cáo, không tự xoay xở.** Việc lấy
  OTP là của chủ dự án (`RUNBOOK_OTP_AUTH.txt`). Không tự chạy
  `scripts/load_token_to_db.py`, không tự sửa `.env`, không in ra giá trị token.
- Không nạp gì vào `bars` / `bars_daily`. Task này chỉ đọc và in.
- Chạy đúng **một lần**. Không lặp để "cho chắc" — SSI đã từng trả 429.

### Tiêu chí kiểm chứng
1. Dán output thô nguyên văn phần `=== 3. Do sau 5m (VCB) ===`.
2. Kết luận một câu: **mốc lùi xa nhất còn trả về bar là bao nhiêu ngày**, và mốc
   đầu tiên trả 0 bar / báo lỗi là bao nhiêu ngày.
3. Đối chiếu với thực tế kho: giải thích con số đo được có nhất quán với việc
   `bars` bắt đầu từ 03/04/2026 hay không. Nếu **không** nhất quán thì nói thẳng
   là không nhất quán — đừng bẻ cong cho khớp.
4. Khôi phục `INTRADAY_BACK_DAYS` về giá trị cũ `[125, 128, 129, 130]` trước khi
   nộp, HOẶC giữ thang mới và nói rõ là cố ý giữ. Chọn một, ghi rõ.

---

## 5. Ràng buộc đứng (áp cho cả hai task, không được vi phạm)

- `real_trading_enabled` giữ nguyên `false`. Không bật, kể cả tạm thời.
- Không gọi API đặt lệnh / huỷ lệnh SSI. API dữ liệu chỉ đọc.
- Không in giá trị secret. `.env` không được sửa, không được commit.
- **Agent KHÔNG commit, KHÔNG push.** Claude audit rồi mới commit.
- Không `TRUNCATE` / `DROP` / xoá dòng. Không nạp thêm gì vào `bars`, `bars_daily`.
- `config/config.yaml` **không được sửa**.
- Không sửa định nghĩa `PaperBroker`, `run_backtest`, `derivative_backtest`
  (gọi `run_backtest` thì được và là chuyện bình thường).
- Phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.
- Chỉ được xoá import/biến/hàm mà chính thay đổi của mình làm thừa.
- Trước khi sửa symbol nào: chạy `gitnexus_impact` và báo blast radius. Sau khi
  sửa: `gitnexus_detect_changes`.

---

## 6. Báo cáo nộp lại phải có

| Mục | Bằng chứng bắt buộc |
|---|---|
| Task 1 — mốc đối chiếu | Output thô của `--symbols HII,IJC,AAA` **và** của `measure_octopus_5m.py`, đặt cạnh nhau, chỉ rõ 12 lệnh / +787.149 VND khớp |
| Task 1 — toàn rổ | Output thô đầy đủ: số mã, số mã sinh lệnh, tổng lệnh, PF, expectancy, MDD, Sharpe, top/bottom 5 mã |
| Task 1 — phá hoại phí | Số PnL khi `fee_rate=0.0` vs `FEE_RATE`, + `git diff scripts/measure_octopus_5m.py` **rỗng**, + `grep -rn "SABOTAGE"` rỗng |
| Task 1 — dùng lại hàm | `git diff` cho thấy script mới **import** `measure_symbol_5m` chứ không chép lại `run_backtest(...)` |
| Task 1 — test | Tên **thật** của từng test mới (`grep -n "^def test_"`), số test trước/sau |
| Task 2 | Output thô phần độ sâu 5m + kết luận mốc biên + đối chiếu với 03/04/2026 |
| Chung | `ruff` sạch, `pytest -m "not integration"` xanh, kèm số test |

**Về bằng chứng "đỏ":** đã bốn lần agent dán tên test không tồn tại trong file test
thật. Tôi sẽ tự phá hoại lại trên đúng code được giao và tự đối chiếu tên test bằng
`grep -n "^def test_"`. Dán tên test sai không làm task trượt, nhưng làm mất toàn
bộ giá trị của phần bằng chứng — nên hãy chép tên từ file thật.

---

## 7. Cái brief này CỐ Ý không giao

Ghi ra để không ai tưởng là sót:

- **Quét/nới tham số trên 5m** — chưa được phép. Phải có kết quả Task 1 trước, và
  nếu quét thì cần brief riêng dựng cơ chế khoá (xem mục 1b).
- **Đo lại khung ngày** — đã có câu trả lời, PF 0,74 trên 1.514 lệnh. Đo lại là lãng phí.
- **Nhánh BÁN (J)**, **đa tài khoản**, **đổi `real_order_account` 0434221 → 0434226** —
  chủ dự án đã hoãn hoặc chưa quyết. `config.yaml` ngoài tầm với của agent.
- **Backfill sâu thêm bar 5m** — phụ thuộc kết quả Task 2. Nếu SSI chặn ở ~128 ngày
  thì không có gì để backfill.
