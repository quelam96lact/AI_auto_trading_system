# Brief đợt 181 — Kiểm bốn luật giao dịch đã có trên riêng mã VCB (ĐĂNG KÝ TRƯỚC)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.

## 0. Câu hỏi và cách Claude hiểu yêu cầu

Chủ dự án yêu cầu: *"kiểm tra chiến lược giao dịch trên mã VCB"*. Yêu cầu này có thể hiểu theo ba cách. Claude chọn cách (c).
- **(a)** Nghĩ ra luật mới riêng cho VCB. **Không chọn:** chỉ có một mã thì phải chọn tham số trên chính dữ liệu dùng để kiểm, tức là câu cá.
- **(b)** Chỉ chạy octopus (chiến lược engine đang dùng) trên VCB. **Không đủ:** đợt 18 đã chạy, ra 8 lệnh, lãi 44,9 triệu trong khi giữ VCB lãi 3,53 tỷ trên cùng vốn.
- **(c) Chọn:** áp **nguyên văn** bốn luật đã có code và đã đo trên toàn thị trường vào riêng VCB, rồi so với việc **cứ mua và giữ VCB**. Không đổi tham số nào.

**Câu hỏi:** có luật nào trong bốn luật dưới đây, chạy trên VCB, **thắng việc mua-và-giữ VCB** một cách đáng tin không?

| # | Luật | Code dùng lại (KHÔNG sửa) | Kết quả toàn thị trường |
|---|---|---|---|
| 1 | `octopus_pullback` (engine đang chạy) | `trading.backtest.STRATEGIES["octopus_pullback"]` + `run_backtest` | Âm (đợt 18, 171) |
| 2 | Pullback trong xu hướng | `scripts/screen_pullback_trend.py::simulate_symbol` | Âm (đợt 173) |
| 3 | Phá đỉnh Donchian 55/20 | `scripts/screen_donchian_breakout.py::simulate_symbol` | IS đạt, holdout trượt (đợt 175) |
| 4 | RSI(2) quá bán trên MA200 | `scripts/screen_rsi2_reversion.py::simulate_symbol` | Âm (đợt 177) |

**Ba cảnh báo phải chép vào báo cáo, không được bỏ:**
1. **Chọn mã sau khi luật đã trượt trên toàn thị trường là kiểu câu cá kinh điển.** Có khoảng 1.200 mã, nên chắc chắn có vài mã mà luật "thắng" do may. VCB được chọn vì chủ dự án hỏi, không phải vì dữ liệu. Báo cáo ghi rõ điều này.
2. **Mẫu nhỏ.** Một mã trong 6 năm chỉ cho vài chục lệnh. Cổng ≥ 300 lệnh của spec không thể đạt. Đợt này **không thể** đưa luật nào tới vốn thật. Kết quả tốt nhất có thể là "đáng đo tiếp trên nhóm ngân hàng", và đó sẽ là một brief khác.
3. Chủ dự án đang giữ 1.500 VCB ngoài hệ thống (đợt 150). Phép đo này **không** khuyến nghị gì về số cổ phiếu đó.

**Ngân sách mục F:** đây là giả thuyết thứ 8 của tháng 10 (trần 3). Claude đã ghi dòng spec H ngày 10/10 **trước** khi giao, theo tiền lệ các đợt 171/173/175/177. Kết quả mang cảnh báo đa so sánh.

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu và niêm phong
- **Nguồn:** chỉ VCB, `bars_daily`, đọc bằng `read_bars(storage, "VCB")` của `scripts/screen_pullback_trend.py`. Hàm này đọc 2016-01-01 → trước 2023-01-01 và gọi `validate_sealed_bars` trước. **Không** tháo cổng, **không** đọc nến từ 2023. Claude đã kiểm: VCB có 2.687 nến từ 2016-01-04, không nến giá ≤ 0, |log ret| lớn nhất 0,073 (không có chia tách chưa chỉnh).
- **Sàn:** lấy từ bản đồ sàn của `load_universe(storage, "exclusions.txt")`. Nếu VCB không có trong universe thì dừng và báo.
- **Cửa sổ:**
  - Luật 2–4 dùng nguyên các hằng `IS_START`/`IS_END` của từng script (lọc theo ngày tín hiệu), truyền nến 2016–2022 để làm nóng.
  - Luật 1 chạy `run_backtest` trên toàn bộ nến 2016-01-01 → 2022-12-31. Dùng `RiskManager(capital=1_000_000_000)` và `TrailingStopManager()` giống `scripts/measure_strategy.py::measure_one`.
- **Mốc mua-và-giữ VCB (luật 2–4):** mua ở `open` phiên đầu tiên ≥ 2017-01-01, bán ở `close` phiên cuối ≤ 2022-12-31, tính bằng `trading.stock_study.net_return` (đủ phí, thuế, trượt giá). **Luật 1:** so với `report.buy_and_hold_pnl` mà `run_backtest` tự tính, không tính lại.

### 1.2 Số liệu in cho mỗi luật
- **Luật 2–4:**
  - số lệnh n, tỷ lệ thắng, lãi ròng trung bình/lệnh, PF (tổng lãi / |tổng lỗ| trên `net`);
  - lợi suất gộp `Π(1+net_i) − 1` (một vị thế tại một thời điểm, tiền nhàn rỗi lãi 0);
  - drawdown lớn nhất của đường vốn gộp theo lệnh;
  - tỷ lệ phiên có vị thế, tính theo `hold` so với số phiên trong cửa sổ;
  - p một phía của lãi ròng trung bình/lệnh (bootstrap lại mẫu lệnh, 2.000 lần, `numpy.random.default_rng(42)`, p = tỷ lệ trung bình bootstrap của chuỗi đã trừ trung bình ≥ trung bình quan sát).
- **Luật 1:** số lệnh (số fill SELL, như đợt 18), PnL chiến lược = `realized_pnl + unrealized_pnl`, `buy_and_hold_pnl`, `win_rate`, `max_drawdown`. Không bootstrap.
- **Chung:** một dòng mốc mua-và-giữ VCB (lợi suất ròng tổng, CAGR, drawdown lớn nhất theo giá đóng cửa).

### 1.3 Cổng "đáng đo tiếp" (chốt trước, so sánh nghiêm ngặt)
**Luật 2–4** đạt khi hội đủ **cả năm** điều kiện:
1. n ≥ 20;
2. lãi ròng trung bình/lệnh > 0;
3. PF > 1,2;
4. lợi suất gộp > lợi suất mua-và-giữ VCB cùng cửa sổ;
5. p < 0,0125 (0,05 chia 4 luật, Bonferroni).

**Luật 1** đạt khi: số fill SELL ≥ 20, PnL > 0, **và** PnL > `buy_and_hold_pnl`.

Không luật nào đạt ⇒ kết luận "**không luật nào trong bốn luật thắng việc giữ VCB 2017–2022**". Có luật đạt ⇒ chỉ ghi "đáng đo tiếp", **dừng**, không mở 2023+, không đề xuất chạy thật. Lưu ý cho Claude: VCB 2023+ đã bị luật 1 (đợt 18) và luật 3 (holdout đợt 175) nhìn qua, nên không còn là tập sạch cho hai luật đó.

### 1.4 Dự đoán của Claude (ghi trước)
Không luật nào đạt. Cả bốn thua mua-và-giữ VCB ở điều kiện 4 (luật 1: PnL ≤ B&H).

### 1.5 Chống câu cá
- Không đổi tham số, không thêm luật, không thử mã khác, không đổi cửa sổ. **Chạy đúng một lần.** Chỉ được chạy lại khi phát hiện lỗi code, và phải khai trong báo cáo.
- Thêm số nào ngoài §1.2 thì ghi riêng ở mục "tự ý thêm", không dùng để kết luận.

## 2. Sản phẩm và phạm vi
- **Mới:** `scripts/measure_vcb_strategies.py` (chỉ đọc DB, có bootstrap `sys.path` như các script khác, chạy được `--help` từ gốc repo).
- **Mới:** `tests/test_measure_vcb_strategies.py`.
- **Mới:** `docs/superpowers/research/2026-10-10-dot-181-chien-luoc-tren-vcb.md`.
- **Không sửa bất kỳ file nào khác.** Đặc biệt không sửa ba script `screen_*`, `trading/backtest.py`, `trading/strategies/*`, `config/`, `docs/holdout-unlock-log.md`, spec.
- Gọi `simulate_symbol` của từng script **qua import**, không chép lại logic, không truyền tham số khác mặc định ngoài `bars`/`exchange`/`symbol`/`stats`.
- Ghi chú trong code: tiếng Việt không dấu.

## 3. Test (TDD, dữ liệu dựng tay, không chạm DB)
1. **Gọi đúng code gốc:** với một chuỗi nến tổng hợp có seed cố định (≥ 300 phiên, có xu hướng và nhịp điều chỉnh), danh sách lệnh do wrapper của từng luật 2–4 trả ra **bằng hệt** lệnh khi gọi trực tiếp `simulate_symbol` của script tương ứng.
2. **Lợi suất gộp và drawdown:** ba lệnh net +10%, −20%, +5%. Lợi suất gộp = 1,1 × 0,8 × 1,05 − 1 = −0,076. Drawdown lớn nhất = 20% (đỉnh 1,1 → 0,88). Sai số 1e-12.
3. **Mốc mua-và-giữ:** nến tay có phiên cuối 2016 (bỏ qua), phiên đầu 2017 open = 100, phiên cuối 2022 close = 150 ⇒ đúng bằng `net_return(100, 150)`. Thêm assert: **không** dùng close phiên đầu, cũng không dùng nến của năm 2016.
4. **Bootstrap p:**
   - 30 lệnh net đều +0,01 ⇒ p = 0;
   - 30 lệnh đối xứng quanh 0 (±0,01) ⇒ 0,3 < p < 0,7;
   - hai lần gọi cùng seed cho cùng p.
5. **Cổng §1.3:** bảng ca biên, mỗi ca chỉ trượt đúng một điều kiện:
   - n = 19;
   - trung bình = 0;
   - PF = 1,2 đúng bằng;
   - lợi suất gộp = B&H đúng bằng;
   - p = 0,0125 đúng bằng;
   - một ca đạt đủ cả năm;
   - luật 1: PnL > 0 nhưng = B&H ⇒ trượt.
6. **Niêm phong:** storage giả trả một nến 2023-01-03 cho VCB ⇒ đường đọc ném lỗi.

**Bốn phép phá bắt buộc.** Sao lưu file ra ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`. Mỗi phép phá phải làm đỏ đúng test nêu:

| Phép phá | Test phải đỏ |
|---|---|
| (i) ngưỡng p đổi thành 0,05 (bỏ Bonferroni) | ca 5 (p = 0,0125 phải trượt; dựng thêm ca p = 0,03 nếu cần để đỏ) |
| (ii) `PF > 1,2` đổi thành `PF >= 1,2` | ca 5 |
| (iii) mốc mua-và-giữ dùng close phiên đầu thay vì open | ca 3 |
| (iv) bỏ `validate_sealed_bars` / đọc thẳng `storage.read_daily_bars` không qua `read_bars` | ca 6 |

## 4. Cổng kiểm cuối
- **GitNexus** (chỉ `gitnexus ... -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs ...`, **không `npx`**):
  - trước khi viết: `impact simulate_symbol --direction upstream` cho cả ba script, cùng `impact run_backtest`. Báo mức rủi ro (chỉ import, không sửa);
  - sau khi viết: `detect-changes --scope all`. File mới chưa theo dõi nên "không thấy symbol" là bình thường; ghi rõ như vậy.
- `uv run pytest -m "not integration" -q` **trước** khi tạo file và **sau**: dán hai con số.
- `uv run pytest tests/test_measure_vcb_strategies.py tests/test_scripts_convention.py -v` xanh.
- `uv run ruff check trading tests scripts` sạch.
- `uv run python scripts/measure_vcb_strategies.py --help` chạy được từ gốc repo.
- Rồi chạy thật **một lần**: `uv run python scripts/measure_vcb_strategies.py`.

## 5. Bất biến
- **Không:** commit, push, bật `real_trading_enabled`, ghi DB, gọi API đặt lệnh SSI.
- **Không chạy:** `scripts/sched.sh`, `scripts/drill_place_cancel_order.py`.
- **Không đọc:** `.ssi_sdk_token.json`, `.env`.

## 6. Báo cáo cho Claude
- Output chạy thật **nguyên văn**.
- Bảng bốn luật × năm điều kiện, kèm đối chiếu với dự đoán §1.4.
- Bảng bốn phép phá, hai con số pytest trước/sau, output ruff, `impact` và `detect-changes`.
- Ba cảnh báo ở §0, và mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi không đọc nến VCB nào từ 01/01/2023. Phép đo này không đưa luật nào tới vốn thật và không khuyến nghị gì về số VCB chủ dự án đang giữ."*
