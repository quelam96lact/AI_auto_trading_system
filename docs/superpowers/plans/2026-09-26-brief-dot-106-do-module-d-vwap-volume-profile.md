# Brief đợt 106 — Đo module D (VWAP + Volume Profile + Order Flow) trên BTCUSDT perp 1H

Ngày giao: 26/09/2026. Base: main `12178f1`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push**.

Nguồn: §7 trong file của chủ dự án `Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md` (gốc repo). File này **chỉ đọc**.

## 0. Vì sao đợt này

Các module khác của tài liệu đã đo xong, đều **không có lợi thế**:
- A (Donchian) và B (Bollinger): đợt 37–38 và đợt 105.
- C: đợt 44.

D là module cuối cùng. Đợt này đo D **một lần** theo thiết kế chốt trước. Kết quả D quyết định có xây đường lệnh BingX hay không.

**Không làm:** bộ chọn regime, gộp module, BingX API, tối ưu tham số.

## 1. Những gì đã có (Claude kiểm 26/09) — tái dùng, không viết lại

| Thứ | Ở đâu |
|---|---|
| Nến 1H BTCUSDT 2020-01-01 → 2026-08-31 (58.440 nến) | `binance_klines`, `interval='1h'` |
| Funding 2020 → 2026-08 | `binance_funding` |
| **Chưa có nến 5m** | phải nạp (bước 2) |
| `FlowRow`, `delta`, `buy_ratio`, `flow_valid`, `load_flow`, `load_funding`, `funding_cost`, `null_p_value`, hằng `CAPITAL`, `RISK_FRACTION`, `MAX_LEVERAGE`, `SLIPPAGE_BPS`, `NULL_ITERATIONS`, `MAIN_*`, `REPEAT_*` | `scripts/measure_perp_orderflow.py` (đợt 105). **Import, không chép.** |
| `EmaCalculator`, `AtrCalculator` | `trading/indicators.py` |
| `PerpTrade`, `RandomEntryConfig`, `is_dirty_bar` | `trading/perp_backtest.py`, `trading/data_quality.py` |
| Quy ước khớp lệnh: stop-entry gap thì khớp giá mở cửa; trượt giá bất lợi mỗi lần khớp; chạm SL và TP cùng nến thì tính SL trước; chỉ xét thoát lệnh từ nến **sau** nến vào; dừng theo thời gian thoát ở giá đóng cửa; khối lượng lệnh là `equity*risk/(R + 2*entry*fee)`, trần `max_leverage*equity/entry` | `trading/perp_backtest.py` dòng 198–470. **Giữ đúng các quy ước này** để so được với A/B. |
| `profit_factor`, `max_drawdown` | `trading/metrics.py` |

## 2. Định nghĩa chốt trước

Tài liệu §7 có nhiều chỗ hiểu được nhiều cách. Bảng dưới đây là **cách hiểu duy nhất** được đo. Không đổi sau khi thấy kết quả. Chỗ nào agent thấy tài liệu nói khác thì **ghi lại, không tự đổi**.

### 2.1. Chỉ báo, tính tại lúc đóng nến 1H `t` (UTC)

- **EMA20, EMA50, EMA200 và ATR14:** trên nến 1H.
- **VWAP_t:** `Σ(HLC3·volume) / Σ volume` trên các nến 1H **cùng ngày UTC** từ 00:00 đến hết `t`, với `HLC3 = (high+low+close)/3`.
  - Nếu ngày đó thiếu bất kỳ nến 1H nào từ 00:00 đến `t` → VWAP không hợp lệ.
- **Volume Profile cho ngày D:** dựng từ **toàn bộ nến 5m của ngày D-1**.
  - Hợp lệ khi và chỉ khi D-1 có **đủ 288** nến 5m.
  - `lo = min(low)`, `hi = max(high)` của D-1. Chia `[lo, hi]` thành **48 hàng** bằng nhau.
  - Khối lượng mỗi nến 5m gán **trọn** vào hàng chứa `HLC3` của nó. `HLC3 = hi` thì vào hàng trên cùng.
  - **POC:** hàng có khối lượng lớn nhất. Hoà thì lấy hàng **thấp nhất**.
  - **Value Area 70%:**
    - Bắt đầu từ POC, mỗi bước thêm **một** hàng kề: hàng ngay trên hoặc ngay dưới, chọn hàng có khối lượng lớn hơn. Hoà thì chọn hàng **trên**. Hết hàng một phía thì lấy phía còn lại.
    - Dừng khi tổng khối lượng ≥ 70% tổng ngày.
    - `VAH` = mép **trên** của hàng cao nhất trong VA; `VAL` = mép **dưới** của hàng thấp nhất.
  - `PH` (Profile High) = `hi`, `PL` (Profile Low) = `lo`.
- **Order Flow (nến 1H `t`):**
  - dùng `delta` và `buy_ratio` của đợt 105;
  - `mag_ok_t = |delta_t| >= median(|delta_{t-20}|, …, |delta_{t-1}|)`. Tử số là nến `t`; cửa sổ là **20 nến trước**, không gồm `t`.

### 2.2. Tín hiệu tại nến `t`

Không xét tín hiệu khi:
- `t` là nến **00:00 UTC** (tài liệu: "1H đầu UTC chưa đầy đủ");
- profile, VWAP hay chỉ báo chưa hợp lệ;
- đang có vị thế hoặc lệnh chờ;
- vừa đóng vị thế trong nến này.

`regime_long(x)` đúng tại nến `x` khi **cả năm** điều kiện đúng:
1. `close_x > EMA200_x`
2. `EMA20_x > EMA50_x`
3. `EMA20_x > EMA20_{x-3}`
4. `close_x > VWAP_x`
5. `close_x > VAH`

`regime_short` đối xứng: `<`, `<`, `<`, `<`, và `< VAL`.

`VAH` và `VAL` trong `regime(x)` là của profile dùng cho **ngày UTC của nến `x`**. Nếu `x` thuộc ngày hôm trước thì dùng profile của ngày đó; profile đó không hợp lệ thì `regime(x)` sai.

**LONG tại `t`** khi đúng **tất cả**:
1. `regime_long` đúng tại **ít nhất một** nến trong `{t-3, t-2, t-1}`.
2. **Chạm:** trong hai mức `L ∈ {VWAP_t, VAH}`, có ít nhất một mức thoả `|low_t − L| <= 0.25·ATR_t`. Cả hai cùng chạm thì chọn `L` **gần `close_t` hơn**.
3. **Xác nhận, trên chính nến `t`:**
   - `close_t > L`
   - `close_t > open_t`
   - `close_t > high_{t-1}`
   - `close_t > VAH` (acceptance ngoài vùng giá trị)
4. **Flow:**
   - `delta_t > 0`
   - `buy_ratio_t >= 0.55`
   - `mag_ok_t`

**SHORT** đối xứng:
- `L ∈ {VWAP_t, VAL}`, xét `|high_t − L|`;
- `close_t < L`, nến đỏ, `close_t < low_{t-1}`, `close_t < VAL`;
- `delta_t < 0`, `buy_ratio_t <= 0.45`, `mag_ok_t`.

**Cách hiểu đã chọn:** nến chạm và nến xác nhận là **cùng một nến**. Cách hiểu "chạm ở nến trước, xác nhận ở nến sau" **không** đo trong đợt này.

### 2.3. Vào lệnh

- **Lệnh chờ:**
  - LONG là buy-stop tại `high_t + 0.05·ATR_t`;
  - SHORT là sell-stop tại `low_t − 0.05·ATR_t`;
  - hiệu lực ở hai nến `t+1` và `t+2`, rồi hết hạn.
- **Giá khớp:** theo quy ước engine (gap thì khớp giá mở cửa), cộng trượt giá.
- **Stop:**
  - LONG `= min(low_t, L − 0.25·ATR_t)`
  - SHORT `= max(high_t, L + 0.25·ATR_t)`
- **Bộ lọc, xét lúc khớp với giá khớp thật.** Vi phạm thì **bỏ lệnh**, và đếm theo từng lý do:
  - `R < 0.20·ATR_t` hoặc `R > 1.50·ATR_t`, với `R = |entry − stop|`.
  - **Chi phí thực thi:** `entry·2·SLIPPAGE_BPS/1e4 > 0.15·R`. Tài liệu ghi "spread, slippage hoặc delay", nên **không** tính phí sàn vào đây.
  - **Vùng cản:**
    - LONG: `PH > entry` **và** `PH − entry < R`.
    - SHORT: `PL < entry` **và** `entry − PL < R`.
    - HVN/LVN: **tắt** (tài liệu: "chưa định nghĩa tái lập thì tắt").
- **Khối lượng:** theo công thức engine. Vị thế chia thành **2 chân** bằng nhau, mỗi chân `qty/2`.

### 2.4. Thoát lệnh

Xét từ nến `j` > nến khớp `k`. Mỗi nến `j` đi theo thứ tự dưới đây; bước nào xảy ra thì dừng xét nến đó.

1. **Stop.**
   - Với LONG: `low_j <= stop` → mọi chân còn mở thoát tại `min(open_j, stop)`.
   - Lý do thoát là `SL`, hoặc `BE` nếu stop đã dời về hoà vốn.
2. **TP1 (chưa chốt chân 1).**
   - Nếu `high_j >= entry + 1R`: chân 1 thoát tại `max(open_j, entry + 1R)`, lý do `TP1`.
   - Stop của chân 2 dời về `BE = entry·(1 + 2·fee_rate + 2·SLIPPAGE_BPS/1e4)`, **áp dụng từ nến `j+1`**.
3. **Sau khi đã chốt TP1 ở một nến trước:**
   - `high_j >= entry + 2R` → chân 2 thoát tại `max(open_j, entry + 2R)`, lý do `TP2`.
   - Nếu không: `close_j < EMA20_j` → chân 2 thoát tại `close_j`, lý do `EMA20`.
4. **Chưa chốt TP1 và `j − k >= 12`:** thoát toàn bộ tại `close_j`, lý do `TIME`.

SHORT đối xứng.

Mỗi chân là một `PerpTrade` riêng, gồm phí hai chiều trên `qty/2` và trượt giá mỗi lần thoát. `exit_reason` của `PerpTrade` được **mở rộng kiểu** thêm `"TP1"`, `"TP2"`, `"BE"`, `"EMA20"`. Đây là thay đổi duy nhất được phép trong `perp_backtest.py`.

Funding tính theo **từng chân** bằng `funding_cost` của đợt 105, với `notional = entry·qty_chân`.

### 2.5. Đối chứng ngẫu nhiên

- Tại mọi nến đủ điều kiện như §2.2 (trừ điều kiện tín hiệu), phát lệnh với xác suất `p`, chiều ngẫu nhiên.
- Lệnh ngẫu nhiên:
  - trigger `high_t + 0.05·ATR_t` (LONG) hoặc `low_t − 0.05·ATR_t` (SHORT);
  - stop `low_t − 0.25·ATR_t` hoặc `high_t + 0.25·ATR_t`;
  - **cùng** bộ lọc §2.3, **cùng** luật thoát §2.4.
- **Không** gọi `entry_filter`.
- Hiệu chỉnh `p` cho số lệnh trung bình của null lệch **không quá 10%** so với số lệnh thật (tối đa 5 vòng, mỗi vòng 50 lượt). In bảng các vòng hiệu chỉnh.
- N = 1000 cho **null A** (long 50%) và **null B** (khớp tỷ lệ long thật).
- `p = null_p_value(...)` trên `net_pnl` **trước funding**. Lấy **p lớn hơn** trong hai null.

### 2.6. Cửa sổ và tiêu chí

| Cửa sổ | Khoảng (UTC) | Vai trò |
|---|---|---|
| CHÍNH | 2020-01-01 → 2023-12-31 | Quyết định. D chưa từng chạy ở đâu. |
| LẶP LẠI | 2024-01-01 → 2026-08-31 | Kiểm tra lặp lại. |

Dữ liệu từ 2026-09-01 vẫn **niêm phong**.

D **CÓ LỢI THẾ** chỉ khi đạt **cả bốn** tiêu chí:
1. CHÍNH có ≥ 30 lệnh. **Một lệnh là một lần vào**, không đếm theo chân.
2. CHÍNH: `net_after_funding > 0`.
3. CHÍNH: `p <= 0.05`. Chỉ có một giả thuyết nên không cần Holm.
4. LẶP LẠI: `net_after_funding > 0`.

Nếu CHÍNH hỏng (1) hoặc (2) thì **không cần chạy** đối chứng; in `BỎ QUA` và lý do.

**Chỉ báo cáo:**
- ablation: flow tắt; bộ lọc chi phí tắt; bộ lọc vùng cản tắt;
- phân rã Long/Short, theo năm và theo `exit_reason`;
- mua-giữ BTC;
- số tín hiệu bị bỏ theo từng lý do.

## 3. Phạm vi file

| File | Được làm gì |
|---|---|
| `trading/perp_value_pullback.py` | **Mới.** Gồm các hàm thuần `vwap_series`, `build_volume_profile` (→ `DayProfile(poc, vah, val, ph, pl)`), `value_area`, và engine `run_value_pullback_backtest(bars_1h, profiles, *, fee_rate, slippage_bps, capital, risk_fraction, max_leverage, entry_filter=None, random_entry=None, use_cost_filter=True, use_barrier_filter=True)`. Engine trả về `PerpReport` hoặc một report cùng dạng, cộng các bộ đếm bỏ lệnh. |
| `tests/test_perp_value_pullback.py` | **Mới.** |
| `scripts/measure_perp_value_pullback.py` | **Mới.** Nạp 5m và 1h, dựng profile, dựng `entry_filter` cho flow (gồm `mag_ok`), chạy hai cửa sổ, ablation, null và kết luận. |
| `tests/test_measure_perp_value_pullback.py` | **Mới.** |
| `trading/perp_backtest.py` | **Chỉ** mở rộng `Literal` của `PerpTrade.exit_reason`. |
| `docs/superpowers/research/2026-09-2x-dot-106-do-module-d-vwap-volume-profile.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `measure_perp_orderflow.py` và `significance_test.py` (chỉ import);
- logic của `run_perp_backtest`;
- `trading/engine`, `trading/collector`, `trading/storage`;
- config, container, Task Scheduler, file chiến lược.

Thấy lỗi ngoài phạm vi thì báo lại, không sửa.

**Một công thức một chỗ:** không chép lại `delta`, `buy_ratio`, `funding_cost`, `null_p_value`, drawdown hay profit factor. Nếu thấy buộc phải chép thì **dừng lại và báo**.

## 4. Các bước

**GitNexus TRƯỚC khi sửa `perp_backtest.py`** (đợt 105 bạn chạy sau; lần này phải chạy trước):
- `gitnexus_impact({target: "PerpTrade", direction: "upstream"})`, dán kết quả. Gặp HIGH/CRITICAL thì dừng lại và báo.
- Cuối đợt chạy `gitnexus_detect_changes()` và dán kết quả.

1. **Nạp nến 5m:**
   ```
   uv run python scripts/binance_vision.py --mode klines --symbol BTCUSDT --interval 5m --from 2020-01-01 --to 2026-08-31
   ```
   → **Kiểm chứng bằng** SQL, dán output:
   - Số nến theo năm. Kỳ vọng: 2020 = 105.408; 2021–2023 = 105.120 mỗi năm; 2024 = 105.408; 2025 = 105.120; 2026 (01–08) = 69.984. Tổng **701.280**.
   - Số ngày có < 288 nến 5m.
   - Đối chiếu Σ volume 5m với Σ volume 1h theo từng giờ, dùng `date_trunc('hour', ts)`. In số giờ lệch > 0,1% và 5 giờ lệch nhiều nhất.

   Lệch thì **ghi nguyên văn, không tự lấp**. Không `--force`.

2. **Hàm thuần (TDD, viết test đỏ trước):**
   - `vwap_series`:
     - ví dụ tính tay 3 nến;
     - reset tại 00:00 UTC;
     - thiếu một nến trong ngày → các nến sau trong ngày đó không hợp lệ.
   - `build_volume_profile` và `value_area`:
     - ví dụ tính tay với **một** ngày nhỏ (tham số `rows` và `va_pct` truyền được; mặc định 48 và 0,70); POC, VAH và VAL khớp số tính tay;
     - test riêng cho luật hoà của POC, luật hoà khi mở rộng VA, và trường hợp hết hàng một phía;
     - `HLC3 = hi` vào hàng trên cùng.
   - Profile của ngày D **không đổi** khi sửa một nến 5m của ngày D. Nó đổi khi sửa nến của D-1.
   - D-1 có 287 nến → profile ngày D không hợp lệ.
   - `mag_ok`:
     - tính tay với tử số là `|delta_t|`, cửa sổ 20 nến trước;
     - sửa nến `t+1` không đổi kết quả tại `t`.

   → **Kiểm chứng bằng:** `uv run pytest tests/test_perp_value_pullback.py tests/test_measure_perp_value_pullback.py -v`.

3. **Engine (TDD).** Dựng chuỗi nến giả cho từng kịch bản sau. Mỗi kịch bản phải có ít nhất một test:
   - Tín hiệu LONG phát đúng tại `t`; sửa nến `t+1` không đổi việc tín hiệu có phát hay không.
   - Không có tín hiệu ở nến 00:00 UTC.
   - Thiếu một trong các điều kiện `regime`, chạm, xác nhận hoặc `close > VAH` thì không có tín hiệu (mỗi điều kiện một test).
   - Lệnh chờ hết hạn sau 2 nến.
   - Ba bộ lọc lúc khớp (R, chi phí, vùng cản): mỗi bộ lọc bỏ đúng lệnh và đếm đúng.
   - Luật thoát:
     - (a) chạm SL;
     - (b) TP1, rồi BE ở nến sau: chân 2 thoát tại `min(open, BE)` trừ trượt giá, lý do `BE`;
     - (c) TP1 rồi TP2;
     - (d) TP1 rồi `close < EMA20`;
     - (e) `TIME` sau 12 nến;
     - (f) SL và TP1 cùng nến → SL;
     - (g) TP1 và mức 2R cùng một nến → **chỉ** TP1 ở nến đó.
   - `entry_filter` luôn trả `False` → 0 lệnh. Có `random_entry` → `entry_filter` không được gọi (dùng spy).
   - Kịch bản SHORT đối xứng cho ít nhất (a) và (c).

   → **Kiểm chứng bằng:** toàn bộ test xanh.

4. **Phá thử.** Sao lưu **ra ngoài repo**, khôi phục từ bản sao lưu đó. **Cấm `git checkout`, `git restore`, `git stash`.** Mỗi phép phá dưới đây phải làm ít nhất một test đỏ:
   - (i) profile dùng nến của ngày D thay vì D-1;
   - (ii) cửa sổ của `mag_ok` gồm cả nến `t`;
   - (iii) đảo thứ tự: xét TP1 trước SL;
   - (iv) stop BE áp dụng ngay trong nến chốt TP1.

   Phép phá phải **thật sự vi phạm luật**. Đợt 105 bạn đã tự phát hiện một phép phá không vi phạm gì; kiểm lại trước khi kết luận "không bắt được".
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.

5. **Chạy đo:** `uv run python scripts/measure_perp_value_pullback.py`. Script in cho mỗi cửa sổ × biến thể (baseline, flow tắt, bộ lọc chi phí tắt, bộ lọc vùng cản tắt):
   - số lần vào lệnh, số chân;
   - số tín hiệu bị bỏ theo từng lý do (flow, R, chi phí, vùng cản, hết hạn);
   - `net_pnl`, funding, `net_after_funding`;
   - win rate theo lần vào, profit factor, max drawdown;
   - phân rã Long/Short, theo năm, theo `exit_reason`;
   - mua-giữ BTC.

   Tiếp theo là null theo §2.5 (hoặc `BỎ QUA` kèm lý do), và **một dòng kết luận** theo §2.6.
   → **Kiểm chứng bằng:** dán **nguyên văn** output. Lần chạy chính thức là **một lần duy nhất** trên code cuối. Sửa code sau khi đo thì phải đo lại và nói rõ.

6. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q`: không test cũ nào đỏ (mốc 1072 passed).
   - `uv run ruff check trading tests scripts/measure_perp_value_pullback.py`: sạch.

## 5. Báo cáo cho Claude

File `docs/superpowers/research/2026-09-2x-dot-106-do-module-d-vwap-volume-profile.md`, theo thứ tự:
1. Kết luận hai dòng.
2. Chỗ tài liệu §7 khác với §2 của brief (nếu có).
3. Số liệu nạp 5m và phần đối chiếu volume.
4. Output test.
5. Phá thử.
6. Output đo nguyên văn.
7. `gitnexus_impact` (chạy **trước** khi sửa) và `detect_changes`.
8. Những điều thấy ngoài phạm vi.

Không viết "có tiềm năng", "gần đạt" hay "đáng chú ý".

Kết thúc bằng câu: "Tôi không commit, không push, không đụng BingX API, không đọc dữ liệu từ 2026-09-01."
