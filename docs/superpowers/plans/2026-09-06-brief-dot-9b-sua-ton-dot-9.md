# Brief đợt 9b — Sửa tồn của đợt 9

**Người giao:** Claude (planner/auditor) · **Ngày:** 2026-09-06
**Nguồn:** audit đợt 9. Deliverable đợt 9 **chưa được commit** vì cổng cứng thủng.

---

## 0. NGUYÊN NHÂN GỐC — VÀ MỘT PHẦN LỖI THUỘC VỀ BRIEF ĐỢT 9

### 0.1. Repo đang có HAI mức phí VN mâu thuẫn nhau

| Mức | Ở đâu | Nguồn |
|---|---|---|
| **0,25%** (`FEE_RATE`) | `paper_broker.py:12`, dùng bởi `run_backtest` khi `fee_rate=None` | **Có nguồn:** biểu phí SSI lệnh online, GD < 100 triệu/ngày, hiệu lực 10/10/2025, đã gồm phí Sở (link ngay trong comment `paper_broker.py:8-11`) |
| **0,15%** | literal trong các script hybrid gọi `run_pattern_backtest` | **Không có nguồn nào trong repo** |

### 0.2. Brief đợt 9 của tôi nói sai, và đó là một phần nguyên nhân

Brief đợt 9 §0.1 viết: *"Chi phí trên cổ phiếu VN — **Đã đạt.** Phí 0,15% + thuế
bán 0,1% + trượt giá 5bps có trong các script đo VN."*

Tôi đọc con số 0,15% từ script hybrid rồi khẳng định như thể đó là mô hình chi
phí VN của dự án. **Đường `run_backtest` dùng 0,25%, không phải 0,15%.** Agent
nhiều khả năng đã tin câu đó và hardcode `0.0015` vào cả hai script hard-gate.
Đây là lỗi của brief, không phải chỉ lỗi của người thực thi — ghi lại để không
lặp lại.

### 0.3. Hậu quả đo được

Trước đợt 9, hai script hard-gate gọi `run_backtest(...)` **không truyền phí** →
mặc định `None` → `backtest.py:190` resolve về `FEE_RATE = 0,0025`. Đợt 9 thêm
tham số tường minh nhưng khai `0.0015` → phí thấp hơn 40% → cổng cứng trôi:

| | Đúng (bất biến) | Sau đợt 9 |
|---|---:|---:|
| Octopus baseline | 1.514 lệnh / **−1.615.319.902** | 1.523 lệnh / **−1.204.739.189** |
| Octopus combo | 11.316 lệnh / **−9.826.136.733** | 12.414 lệnh / **−7.772.262.431** |

Cả số lệnh lẫn PnL đều lệch. Tôi tự chạy lại độc lập cả hai, không lấy từ báo cáo.

---

## 1. NHIỆM VỤ

### Task 1 — Sửa lệch phí bằng cách BỎ HẲN literal (chặn commit)

Trong `scripts/measure_octopus_matched_basket.py` và
`scripts/measure_octopus_combo_matched_basket.py`:

```python
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
...
fee_rate = FEE_RATE * cost_multiplier
sell_tax_rate = SELL_TAX_RATE * cost_multiplier
slippage_bps = SLIPPAGE_BPS * cost_multiplier
```

**Cấm viết lại con số dưới dạng literal.** Lý do phải hiểu, không chỉ làm theo:
với `cost_multiplier=1.0` thì cách này tái lập cổng cứng **do cấu trúc**, không
phải do may mắn gõ đúng số. Đây đúng nguyên tắc "một công thức một chỗ" đã dùng
cho SPEC-1c (`39240a2`) và `DailyLiquidityTracker`.

Giữ nguyên `--cost-multiplier` — nó vẫn hoạt động, chỉ là nhân lên từ hằng số
thật thay vì từ số gõ tay.

### Task 2 — Chạy lại và dán số THẬT

Sau Task 1, chạy lại và dán **output thô, không tóm tắt**:

- `measure_octopus_matched_basket.py` → phải ra đúng
  `−1.615.319.902 / 1.514 lệnh / 439 mã / 748 mã đủ TK`
- `measure_octopus_combo_matched_basket.py` → phải ra đúng
  `−9.826.136.733 / 11.316 lệnh / 653 mã`

**Mọi bảng số đo trong báo cáo đợt 9 đều phải làm lại**, vì chúng được tính ở
mức phí sai. Profit Factor, expectancy, max drawdown, Sharpe của phần VN hiện
đều là số ở phí 0,15%.

### Task 3 — Dán lại output đỏ sabotage từ TEST CÓ THẬT

Bốn output đỏ trong báo cáo đợt 9 trích dẫn bốn tên test **không tồn tại**:

| Báo cáo ghi | Tên thật trong file đã giao |
|---|---|
| `test_profit_factor_no_losses` | `test_profit_factor_basic_and_edge_cases` |
| `test_sharpe_requires_periods_per_year` | `test_sharpe_requires_periods_per_year_no_default` |
| `test_load_bars_holdout_locked` | `test_holdout_locked_by_mechanism_raises_permission_error` |
| `test_cost_parameters_required` | `test_run_pattern_backtest_requires_explicit_fees` |

Tôi đã tự tay phá hoại lại cả bốn trên đúng code đã giao — **cả bốn đều đỏ thật**,
nên bản thân test không rỗng. Vấn đề là báo cáo dán output từ một bản nháp cũ rồi
không chạy lại. Chạy lại và dán đúng output của các test hiện có.

### Task 4 — Nối `trading/sampling.py` vào thực tế

`grep -rn "filter_bars_by_split" scripts/` hiện **rỗng**. Module tồn tại, có
test, nhưng **không script nào gọi**. Nghĩa là hôm nay chạy quét lưới kiểu cũ
vẫn không có gì chặn — đúng vấn đề đợt 9 sinh ra để chặn.

Nối vào **ít nhất** `scripts/param_sensitivity.py` và một script đo:

- thêm `--split {train,validation,holdout,all}` (mặc định `train`);
- thêm `--unlock-holdout` và `--unlock-reason`;
- gọi `filter_bars_by_split` **ngay sau khi nạp bar, trước mọi tính toán**;
- không có cờ mà `--split` chạm holdout → `PermissionError` như module đã làm.

Kiểm chứng: chạy thật với `--split holdout` không cờ → phải chết; có cờ →
chạy được và ghi thêm một dòng vào `docs/holdout-unlock-log.md`.

### Task 5 — Dọn dòng log holdout vô nghĩa

`docs/holdout-unlock-log.md` đang có sẵn một dòng
`UNKNOWN | DEFAULT | Holdout evaluation`. Nó không cho biết ai mở, mở để làm gì —
đánh bại đúng mục đích của log.

Giải thích dòng đó từ đâu ra. Nếu là do chạy thử trong lúc phát triển thì xoá
và ghi chú rõ trong báo cáo; nếu là một lần thật sự đọc dữ liệu holdout thì
**giữ lại** và bổ sung thông tin thật.

---

## 2. VIỆC PHẢI BÁO CÁO, KHÔNG TỰ QUYẾT

**Hai mức phí VN mâu thuẫn (§0.1).** Các script hybrid gọi `run_pattern_backtest`
đang dùng 0,15% — thấp hơn 40% so với biểu phí SSI có nguồn (0,25%). Nghĩa là
**mọi con số cổ phiếu VN trong các báo cáo hybrid đợt 6-8 đều lạc quan hơn thực
tế.** (Hướng kết luận không đổi — chúng đều lỗ — nhưng độ lớn thì sai.)

Yêu cầu:

1. **Đo tác động:** chạy lại một cấu hình hybrid VN đại diện ở cả 0,0015 và
   0,0025, báo cáo chênh lệch.
2. **KHÔNG tự đổi mặc định** của `run_pattern_backtest` hay các script hybrid.
   Chủ dự án cần biết mình đang ở bậc phí nào trước khi ta đổi số hàng loạt.
3. Không viết lại kết luận của các báo cáo cũ.

---

## 3. PHẠM VI PHẪU THUẬT

**Được sửa:**
- `scripts/measure_octopus_matched_basket.py`,
  `scripts/measure_octopus_combo_matched_basket.py` — Task 1
- `scripts/param_sensitivity.py` + một script đo — Task 4
- `docs/holdout-unlock-log.md` — Task 5
- `docs/superpowers/research/2026-09-06-dot-9-...-report.md` — viết lại số

**Cấm đụng:**
- `trading/metrics.py`, `trading/sampling.py` — **đã đạt, đừng sửa.** Tôi đã tự
  phá hoại kiểm chứng: `max_drawdown` khớp đúng `backtest.py:242-247` từng dòng,
  `sharpe` không có mặc định, khoá holdout raise thật, test tính tay đúng.
- `trading/pattern_backtest.py` — guard chi phí đã đúng, đã kiểm chứng
- `paper_broker.py`, `run_backtest`, `trading/strategies/*`, `config/config.yaml`
- Không đổi mặc định phí của đường hybrid (§2)

**Không commit, không push.**

---

## 4. TIÊU CHÍ HOÀN THÀNH

| # | Kiểm chứng bằng |
|---|---|
| 1 | Tìm literal phí trong hai script hard-gate → **không còn dòng nào**; thay vào đó là `from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS` |
| 2 | Hai cổng cứng ra đúng số ở §1 Task 2, dán output thô |
| 3 | Bốn output đỏ sabotage khớp tên test có thật |
| 4 | `--split holdout` không cờ → chết; có cờ → chạy + ghi log |
| 5 | `uv run pytest -m "not integration" -q` (hiện 482) + `ruff check` sạch |

Tôi sẽ tự chạy lại cả hai cổng cứng và tự phá hoại lại khi nghiệm thu — như đã
làm ở đợt này. Đừng dán số chưa chạy.
