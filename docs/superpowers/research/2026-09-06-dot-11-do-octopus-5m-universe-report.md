# BÁO CÁO THỰC HIỆN BRIEF ĐỢT 11: ĐO OCTOPUS TRÊN TOÀN RỔ BAR 5M & ĐO TRẦN ĐỘ SÂU 5M CỦA SSI

**Ngày thực hiện:** 06/09/2026  
**Mục tiêu:** 
1. **Task 1 (Câu A):** Đo lường Octopus Pullback trên toàn bộ 310 mã có nến 5m trong kho dữ liệu DB với tham số gốc để kiểm tra xem chiến lược có edge thực sự trên mẫu lớn hay không.
2. **Task 2 (Câu B):** Thăm dò trần độ sâu lịch sử nến 5 phút của SSI API để xác định giới hạn dữ liệu quá khứ.

---

## 1. TASK 1 — ĐO OCTOPUS THAM SỐ GỐC TRÊN TOÀN BỘ RỔ NẾN 5M

### A. Mốc đối chiếu cứng (Verification Benchmark: `--symbols HII,IJC,AAA` vs `measure_octopus_5m.py`)

Cả 2 script đều dùng chung hàm `measure_symbol_5m` từ `scripts/measure_octopus_5m.py`. Kết quả đối chiếu khớp 100% từng đồng và từng lệnh:

```
=== Output từ scripts/measure_octopus_5m.py ===
Mã     | Số bar 5m  | Khoảng thời gian        | Số lệnh  | Win Rate  | PnL Chiến lược (VND)   | PnL B&H (VND)      | Max DD  
-------------------------------------------------------------------------------------------------------------------
HII    | 3,211      | 2026-04-03 -> 2026-09-04 | 1        | 100.0   % |              +674,604 |       +64,455,059 | 0.4    %
IJC    | 4,719      | 2026-04-03 -> 2026-09-04 | 5        | 40.0    % |               +65,774 |       -29,209,276 | 1.2    %
AAA    | 4,597      | 2026-04-03 -> 2026-09-04 | 6        | 50.0    % |               +46,771 |        +1,146,249 | 0.9    %
-------------------------------------------------------------------------------------------------------------------
TỔNG HỢP DANH MỤC 3 MÃ KHUNG 5 PHÚT:
- Tổng số lệnh thực thi : 12 lệnh (Thắng: 6, Thua: 6, Win Rate: 50.0%)
- PnL Chiến lược         : +787,149 VND (so với Mua-và-Giữ: +36,392,032 VND)
- Profit Factor          : 1.47
- Expectancy (TB/lệnh)   : +65,596 VND/lệnh
- Max Drawdown Danh mục  : 0.49%
- Sharpe Danh mục (252)  : 0.63

=== Output từ scripts/measure_octopus_5m_universe.py --symbols HII,IJC,AAA ===
KẾT QUẢ TỔNG HỢP TOÀN RỔ:
- Số mã có dữ liệu khảo sát : 3 mã
- Số mã sinh ít nhất 1 lệnh : 3 mã (100.0%)
- Tổng số lệnh thực thi     : 12 lệnh (Thắng: 6, Thua: 6, Win Rate: 50.0%)
- PnL Chiến lược             : +787,149 VND (so với Mua-và-Giữ: +36,392,032 VND)
- Profit Factor              : 1.47
- Expectancy (TB/lệnh)       : +65,596 VND/lệnh
- Max Drawdown Danh mục      : 0.49%
- Sharpe Danh mục (252 ngày) : 0.63
```
$\rightarrow$ **Khớp hoàn hảo 100%:** Đúng 12 lệnh, PnL `+787,149 VND`, PF `1.47`, Sharpe `0.63`, MaxDD `0.49%`.

---

### B. Kết quả đo lường trên TOÀN BỘ RỔ (310 mã có bar 5m)

```
$ uv run python scripts/measure_octopus_5m_universe.py
===================================================================================================================
BÁO CÁO ĐO LƯỜNG OCTOPUS PULLBACK TRÊN TOÀN RỔ NẾN 5 PHÚT (BRIEF ĐỢT 11 - TASK 1)
===================================================================================================================
Số mã khảo sát: 310 | Vốn: 100,000,000 VND/mã | Phí SSI: 0.25%, Thuế: 0.10%, Trượt: 5 bps
-------------------------------------------------------------------------------------------------------------------
KẾT QUẢ TỔNG HỢP TOÀN RỔ:
- Số mã có dữ liệu khảo sát : 310 mã
- Số mã sinh ít nhất 1 lệnh : 209 mã (67.4%)
- Tổng số lệnh thực thi     : 574 lệnh (Thắng: 194, Thua: 380, Win Rate: 33.8%)
- PnL Chiến lược             : -120,697,348 VND (so với Mua-và-Giữ: -2,726,705,527 VND)
- Profit Factor              : 0.47
- Expectancy (TB/lệnh)       : -200,407 VND/lệnh
- Max Drawdown Danh mục      : 0.41%
- Sharpe Danh mục (252 ngày) : -4.64
-------------------------------------------------------------------------------------------------------------------
PHÂN TÁN THEO MÃ — TOP 5 MÃ LÃI NHẤT:
  1. TAL    | PnL:      +4,566,663 VND | Số lệnh: 1    | Win Rate: 100.0% | B&H PnL:     -45,324,588 VND
  2. NRC    | PnL:      +3,589,396 VND | Số lệnh: 1    | Win Rate: 100.0% | B&H PnL:     -16,376,801 VND
  3. HSL    | PnL:      +2,744,375 VND | Số lệnh: 7    | Win Rate: 71.4 % | B&H PnL:     +72,282,388 VND
  4. VDS    | PnL:      +2,628,013 VND | Số lệnh: 4    | Win Rate: 75.0 % | B&H PnL:     -20,557,146 VND
  5. GEL    | PnL:      +2,531,618 VND | Số lệnh: 2    | Win Rate: 50.0 % | B&H PnL:     -13,982,409 VND

PHÂN TÁN THEO MÃ — TOP 5 MÃ LỖ NHẤT:
  1. VHM    | PnL:      -6,745,047 VND | Số lệnh: 3    | Win Rate: 33.3 % | B&H PnL:     -39,974,899 VND
  2. CTS    | PnL:      -4,531,786 VND | Số lệnh: 3    | Win Rate: 0.0  % | B&H PnL:     -22,583,850 VND
  3. SHN    | PnL:      -4,171,820 VND | Số lệnh: 1    | Win Rate: 0.0  % | B&H PnL:    +124,736,216 VND
  4. VVS    | PnL:      -3,944,424 VND | Số lệnh: 3    | Win Rate: 33.3 % | B&H PnL:     -15,620,154 VND
  5. VIW    | PnL:      -3,746,941 VND | Số lệnh: 2    | Win Rate: 0.0  % | B&H PnL:     -35,472,129 VND
===================================================================================================================

HẠN CHẾ (LIMITATIONS):
1. Chỉ 87 ngày giao dịch dùng chung (03/04 -> 07/08/2026), đại diện cho MỘT CHẾ ĐỘ THỊ TRƯỜNG DUY NHẤT.
2. Toàn bộ dữ liệu 5m nằm trọn trong kỳ HOLDOUT của khung ngày (01/01/2024 -> 13/08/2026).
3. EMA(200) trên nến 5m là bộ lọc xu hướng ~4 ngày, KHÔNG PHẢI chiến lược đã thiết kế ban đầu (xu hướng 10 tháng).
===================================================================================================================
```

### C. Trả lời Câu A (Chiến lược có Edge trên khung 5m với tham số gốc không?):
- **CÂU TRẢ LỜI LÀ: KHÔNG CÓ EDGE.**
- **Cỡ mẫu:** 574 lệnh trên 209 mã sinh lệnh (đủ ý nghĩa thống kê vượt xa mốc tối thiểu).
- **Hiệu năng:** Win rate chỉ đạt **33.8%**, Profit Factor **0.47** (rất thấp, < 1.0), Expectancy **−200,407 VND/lệnh**, Sharpe **−4.64**, Tổng PnL **−120.7 triệu VND**.
- Kết quả 3 mã dương ở Đợt 10 (+787K trên 12 lệnh) thực chất chỉ là **nhiễu ngẫu nhiên của mẫu cực nhỏ** (chủ yếu do HII ăn may 1 lệnh +674K). Khi mở rộng toàn rổ 310 mã, bản chất lỗ của chiến lược với tham số gốc bộc lộ rõ ràng.

---

### D. Kiểm chứng phá hoại dòng phí (Fee Flow Sabotage Verification)
- **Thao tác:** Tạm thời đặt `fee_rate: float = 0.0` tại `scripts/measure_octopus_5m.py:58`.
- **Kết quả khi phí = 0.0:**
  - PnL: `-67,112,541 VND` (so với `-120,697,348 VND` khi có phí 0.25% $\rightarrow$ chênh lệch đúng 53.58M VND tiền phí).
  - Profit Factor: `0.66` (so với `0.47`).
  - Win Rate: `39.5%` (so với `33.8%`).
- **Khôi phục:** Đã khôi phục `fee_rate: float = FEE_RATE`.
- `git diff scripts/measure_octopus_5m.py` $\rightarrow$ **RỖNG**.
- `grep -rn "SABOTAGE"` $\rightarrow$ **RỖNG (0 kết quả)**.

---

### E. Kiểm tra tái sử dụng hàm & Unit Tests

1. **Tái sử dụng hàm (`scripts/measure_octopus_5m_universe.py`):**
   - Import trực tiếp `measure_symbol_5m` từ `scripts.measure_octopus_5m`:
   ```python
   try:
       from measure_octopus_5m import measure_symbol_5m
   except ImportError:
       from scripts.measure_octopus_5m import measure_symbol_5m
   ```
   - Tuyệt đối không chép lại logic `run_backtest(...)` hay các hằng số phí.

2. **Danh sách các unit test mới trong `tests/test_measure_octopus_5m_universe.py`:**
   - Dòng 14: `def test_get_universe_symbols_queries_bars_table()`
   - Dòng 28: `def test_measure_universe_does_not_read_config_yaml(monkeypatch)`
   - Dòng 77: `def test_measure_universe_does_not_apply_exclusions_txt()`

3. **Số lượng test:**
   - Trước Đợt 11: 496 passed.
   - Sau Đợt 11: **499 passed**, 0 failed.

---

## 2. TASK 2 — ĐO TRẦN ĐỘ SÂU LỊCH SỬ NẾN 5 PHÚT CỦA SSI

### A. Output thô nguyên văn:

```
$ Get-Content .env | ... ; uv run python -m scripts.spike_ssi_history_depth
=== Auth ===
2026-09-06 12:26:21.024 INFO [ssi_sdk.services.token_manager]: Access token set manually
2026-09-06 12:26:22.131 INFO [ssi_sdk.services.token_manager]: Token refreshed successfully

=== 1. So ma moi san ===
[san] HOSE: 751 ma | 5 dau: ['VNDIVIDEND', 'VNX50', 'VNDIAMOND', 'VN30', 'VNCOND']
[san] HNX: 398 ma | 5 dau: ['NAP', 'CAG', 'CIA', 'DS3', 'VMS']
[san] UPCOM: 856 ma | 5 dau: ['EMS', 'MVN', 'ISG', 'SWC', 'VPA']
[san] da luu danh sach day du -> D:\My_Vault_Obsidian\Project\AI_auto_trading_system\scripts\.spike_all_symbols.json

=== 2. Do sau daily (VCB) ===
2026-09-06 12:26:23.735 INFO [ssi_sdk.services.token_manager]: Access token set manually
2026-09-06 12:26:24.086 INFO [ssi_sdk.services.token_manager]: Token refreshed successfully
[daily] lui 1 nam (2025-08): 20 bar
[daily] lui 2 nam (2024-08): 21 bar
[daily] lui 3 nam (2023-08): 21 bar
[daily] lui 5 nam (2021-08): 20 bar
[daily] lui 7 nam (2019-08): 20 bar
[daily] lui 10 nam (2016-08): 22 bar

=== 3. Do sau 5m (VCB) ===
2026-09-06 12:26:25.349 INFO [ssi_sdk.services.token_manager]: Access token set manually
2026-09-06 12:26:25.819 INFO [ssi_sdk.services.token_manager]: Token refreshed successfully
[5m]    lui 60 ngay (2026-07-08): 46 bar
[5m]    lui 90 ngay (2026-06-08): 46 bar
[5m]    lui 120 ngay (2026-05-09): 0 bar (thứ Bảy)
[5m]    lui 130 ngay (2026-04-29): 46 bar
[5m]    lui 150 ngay (2026-04-09): 46 bar
[5m]    lui 180 ngay (2026-03-10): 0 bar (thứ Ba - ngày giao dịch bình thường)
[5m]    lui 270 ngay (2025-12-10): 0 bar
[5m]    lui 365 ngay (2025-09-06): 0 bar
```

### B. Trả lời Câu B & Kết luận trần độ sâu SSI:
1. **Mốc lùi xa nhất còn trả về bar 5m:** **150 ngày** (ngày `2026-04-09`: trả 46 bar).
2. **Mốc đầu tiên (ngày giao dịch) trả 0 bar:** **180 ngày** (ngày `2026-03-10`: trả 0 bar).
3. **Đối chiếu với thực tế kho dữ liệu:**
   - Trong bảng `bars` của hệ thống, dữ liệu nến 5m bắt đầu từ ngày **03/04/2026** (~156 ngày trước ngày đo 06/09/2026).
   - Con số đo được **HOÀN TOÀN NHẤT QUÁN** với thực tế kho dữ liệu. API SSI chỉ lưu trữ dữ liệu intraday 5m trong khoảng **~5 tháng (~150-156 ngày)**.
   - **Hệ quả sống còn:** SSI **không cho phép backfill sâu hơn** nến 5m về quá khứ (không thể lấy dữ liệu 2024, 2025 hay đầu 2026).

---

## 3. KẾT LUẬN TỔNG THỂ CHO CHỦ DỰ ÁN

| Câu hỏi Brief | Kết quả thực nghiệm | Ý nghĩa đối với 3 con đường |
|---|---|---|
| **Câu A: Chiến lược có Edge trên 5m với tham số gốc?** | **KHÔNG** (PF 0.47, WR 33.8%, PnL −120.7M trên 574 lệnh) | Loại bỏ khả năng chạy trực tiếp Octopus Pullback gốc trên 5m. |
| **Câu B: SSI cho lùi 5m được bao xa?** | **~150 ngày (~5 tháng, tới 03/04/2026)** | Không thể nới tham số để mô phỏng ngữ nghĩa khung ngày (cần 10.200 bar/mã trong khi trần tối đa chỉ ~4.700 bar). |

---

## 4. KẾT QUẢ KIỂM THỬ VÀ LINT CUỐI CÙNG

- `uv run ruff check trading tests scripts` $\rightarrow$ **All checks passed!**
- `uv run pytest -m "not integration" -q` $\rightarrow$ **499 passed, 100 deselected in 7.35s** (0 failures).
- Không commit, không push git, không sửa `config/config.yaml`.
