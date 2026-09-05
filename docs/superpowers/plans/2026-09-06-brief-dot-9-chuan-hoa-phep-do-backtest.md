# Brief đợt 9 — Chuẩn hoá phép đo backtest: làm cho nó có khả năng phát hiện thất bại

**Người giao:** Claude (planner/auditor) · **Ngày:** 2026-09-06
**Nguồn:** checklist 5 nhóm của chủ dự án về điều kiện tin tưởng một chiến lược
đã backtest.

---

## 0. ĐỌC TRƯỚC — PHẠM VI THẬT SỰ CỦA ĐỢT NÀY

### 0.1. Ba việc trong checklist ĐÃ ĐẠT, không giao lại

Đã tự kiểm chứng trước khi viết brief, đừng tốn công làm lại:

| Mục checklist | Trạng thái thật |
|---|---|
| Survivorship bias | **Đã đạt.** `bars_daily` có 1.554 mã, trong đó **76 mã đã ngừng giao dịch trước 2026-01-01** — mã hủy niêm yết vẫn nằm trong rổ. `exclusions.txt` (246 mã) lọc **chất lượng điều chỉnh giá**, không phải lọc mã chết. 1.554 − 246 = 1.308 khớp số các báo cáo. |
| Look-ahead trên bộ lọc thanh khoản | **Đã đạt.** `DailyLiquidityTracker` tính point-in-time trên N **ngày đã đóng**, cố ý không dùng ảnh chụp `symbol_universe.avg_value_20d` (xem `octopus_pullback.py:22-25`). |
| Chi phí trên cổ phiếu VN | **Đã đạt.** Phí 0,15% + thuế bán 0,1% + trượt giá 5bps có trong các script đo VN. |

### 0.2. Nhóm 5 của checklist NẰM NGOÀI đợt này

Paper trade / micro-live 10-30 lệnh, kill-switch, người giám sát giờ giao dịch,
vào lệnh theo bậc 10-25% — đây là **vận hành go-live**, không phải phương pháp
backtest. Chúng còn đang bị chặn bởi hai quyết định chưa có của chủ dự án
(**E**: tài khoản/vốn cho bot; **J**: hướng đấu nối đường SELL thật). Đợt này
không đụng tới. Sẽ là brief riêng khi E và J có lời giải.

### 0.3. Cảnh báo về ngưỡng — đọc kỹ, đây là chỗ dễ hỏng nhất

Checklist nêu các ngưỡng quyết định: Profit Factor ≥ 1,3; Sharpe ngoài mẫu ≥
40-50% trong mẫu; win rate live lệch ≤ ±15%. **Những ngưỡng đó là điều kiện để
quyết định GIAO DỊCH, không phải mục tiêu để chiến lược đạt được.**

Hiện **không chiến lược nào trong repo đến gần các ngưỡng đó** — tất cả đều lỗ:
octopus −1,6 tỷ; octopus_combo −9,8 tỷ; ba chiến lược nến đều lỗ ở mọi tham số
đã quét.

**Việc của đợt này là làm cho những con số đó tồn tại và đáng tin, KHÔNG phải
đi tìm một cấu hình đạt ngưỡng.** Nếu agent thấy mình đang chỉnh tham số để
Profit Factor vượt 1,3 thì đó chính là cái sai đã tạo ra "lãi +4 tỷ" giả ở đợt
trước (`2026-09-06-tong-hop-ban-giao-claude-audit.md` §3b). **Dừng lại và báo
cáo, đừng chỉnh.**

---

## 1. CHẨN ĐOÁN — VÌ SAO PHẢI SỬA

Bốn lỗ hổng cụ thể, đã có bằng chứng trong chính repo này:

1. **Không có tách mẫu.** `optimize_octopus_combo_hybrid.py` quét lưới rồi chọn
   đỉnh PnL **trên chính bộ dữ liệu dùng để đo**. Không có tập holdout nào tồn
   tại trong repo (`grep` cho `holdout|walk_forward|out_of_sample` → rỗng).
2. **Không có số đo phát hiện được thất bại.** `BacktestReport` chỉ có
   `realized_pnl`, `win_rate`, `trades`, `max_drawdown`, `buy_and_hold_pnl`.
   **Không có Profit Factor, không có Sharpe, không có expectancy.** Vì thế
   "lãi 2,13 tỷ, win rate 40,5%" trông ổn trong khi thực chất không ổn.
3. **`max_drawdown` đã có nhưng bị bỏ rơi.** `run_backtest` tính nó
   (`backtest.py:257`), rồi mọi script tổng hợp rổ đều **không in ra**. Số đo
   quan trọng nhất về khả năng sống sót bị mất ở tầng tổng hợp.
4. **Chi phí = 0 là giá trị mặc định.** `run_pattern_backtest` khai
   `fee_rate: float = 0.0, slippage_bps: float = 0.0`. Toàn bộ số crypto trong
   4 báo cáo hybrid dùng đúng mặc định này mà không ai nhận ra. **Sai sót im
   lặng, không báo lỗi.**

---

## 2. NHIỆM VỤ

Ba giai đoạn, làm tuần tự. Không nhảy cóc — giai đoạn 2 cần đầu ra của 1.

### GIAI ĐOẠN 1 — Số đo (`trading/metrics.py`, file mới)

**MỘT CÔNG THỨC MỘT CHỖ.** Repo này đã từng có **năm** bản chép tay của cùng
một luật (SPEC-1c, đã gộp ở `39240a2`). Không lặp lại: mọi script đo phải gọi
module này, cấm tự tính lại.

Hàm thuần (pure), nhận vào danh sách lệnh / chuỗi PnL, không đụng DB:

| Hàm | Định nghĩa | Ghi chú bắt buộc |
|---|---|---|
| `profit_factor(pnls)` | tổng lãi các lệnh thắng / trị tuyệt đối tổng lỗ các lệnh thua | Trả `None` khi không có lệnh thua (không trả `inf`) |
| `expectancy(pnls)` | PnL trung bình mỗi lệnh | |
| `max_drawdown(equity_curve)` | sụt giảm sâu nhất từ đỉnh, theo **tỷ lệ** | Phải khớp định nghĩa `backtest.py` đang dùng — đọc trước, đừng định nghĩa lại kiểu khác |
| `sharpe(daily_returns, periods_per_year)` | trung bình/độ lệch chuẩn × căn bậc hai số kỳ | `periods_per_year` là **tham số bắt buộc**, không mặc định — VN 252, crypto 1H khác hẳn. Đây đúng loại bẫy đơn vị đã dính 6 lần trong dự án. |
| `portfolio_equity_curve(per_symbol_pnl_by_date, capital_per_symbol)` | gộp PnL theo **ngày** thành một đường cong vốn của cả rổ | Xem cảnh báo §2.1 |

#### 2.1. Cảnh báo bắt buộc ghi vào docstring `portfolio_equity_curve`

Các script hiện chạy **mỗi mã một lần với TOÀN BỘ vốn** rồi cộng PnL. Cộng như
thế **không phải một danh mục thật** — nó là 1.308 tài khoản song song, mỗi tài
khoản 1 tỷ. Đường cong vốn gộp lại chỉ hợp lệ với diễn giải "rổ đều vốn, không
mô phỏng ràng buộc vốn chung, không mô phỏng tranh chấp tiền giữa các mã".

**Ghi rõ hạn chế này trong docstring.** Mô phỏng ràng buộc vốn chung là việc
lớn hơn, **ngoài phạm vi đợt này** — nêu ra, đừng tự làm.

#### 2.2. Đưa số đo vào các báo cáo rổ

Thêm vào bảng đầu ra của `measure_octopus_matched_basket.py` và
`measure_octopus_combo_matched_basket.py`: Profit Factor, expectancy/lệnh,
**max drawdown danh mục**, Sharpe. Giữ nguyên mọi cột đang có.

**Cổng cứng:** sau khi sửa, hai script này vẫn phải in ra **đúng**
`−1.615.319.902 / 1.514 lệnh / 439 mã / 748 mã đủ TK` và
`−9.826.136.733 / 11.316 lệnh / 653 mã`. Lệch một đồng là hỏng.

### GIAI ĐOẠN 1b — Áp thước đo lên CẢ HAI thị trường

**Quyết định của chủ dự án (06/09):** không tạo chiến lược mới; dùng thước đo
mới **đo lại toàn bộ những gì đã có, trên cả VN lẫn crypto, với PHÍ THẬT.**

Vì vậy các số đo ở §2.2 phải được đưa vào **cả** nhóm script crypto
(`measure_crypto_strategies.py`, `measure_octopus_combo_hybrid.py`), không chỉ
hai script VN.

#### 2.2b. Phí BingX — ĐẦU VÀO BẮT BUỘC, CẤM ĐOÁN

Ràng buộc thường trực của dự án: **không đoán phí BingX, bước khối lượng,
endpoint, hay ngày nghỉ lễ.** Toàn bộ số crypto hiện có tính `fee_rate=0.0`, và
với 13.612–27.571 lệnh thì phí quyết định dấu của kết quả — đây không phải chi
tiết phụ, nó là toàn bộ câu trả lời.

Do đó:

- Biểu phí BingX phải được **chủ dự án cung cấp**, hoặc lấy từ nguồn chính thức
  mà chủ dự án chỉ định. Agent **không được tự điền một con số nào.**
- Trong khi chưa có: vẫn chạy được, nhưng **bắt buộc** in ở đầu mọi bảng crypto
  dòng `PHÍ = 0 — SỐ DANH NGHĨA, KHÔNG PHẢI LỢI NHUẬN`, và không được rút bất
  kỳ kết luận nào từ các bảng đó.
- Chuẩn bị sẵn để khi có số thật thì chỉ cần truyền tham số, không phải sửa code.

### GIAI ĐOẠN 2 — Kỷ luật ngoài mẫu (`trading/sampling.py` + `scripts/`)

#### 2.3. Tách mẫu theo THỜI GIAN

Dữ liệu `bars_daily`: 2016-01-04 → 2026-08-13 (~10,6 năm).

| Tập | Kỳ | Dùng để |
|---|---|---|
| Train | 2016-01-04 → 2022-06-30 | phát triển, quét tham số thoải mái |
| Validation | 2022-07-01 → 2023-12-31 | chọn cấu hình cuối cùng |
| **Holdout** | **2024-01-01 → 2026-08-13** | **kiểm đúng MỘT lần** |

Chia theo thời gian, **không** chia ngẫu nhiên theo mã — chuỗi thời gian tài
chính không được xáo trộn.

#### 2.4. Khoá holdout bằng CƠ CHẾ, không bằng lời hứa

"Chỉ kiểm tra đúng một lần" mà chỉ dựa vào kỷ luật con người thì sẽ bị vi phạm.
Yêu cầu:

- Hàm nạp dữ liệu **từ chối** trả về bar trong kỳ holdout, trừ khi truyền cờ
  `--unlock-holdout` một cách tường minh.
- Mỗi lần mở khoá phải **ghi một dòng** vào `docs/holdout-unlock-log.md`: ngày,
  chiến lược, cấu hình cụ thể, lý do. Ghi nối tiếp, không sửa dòng cũ.
- Test: gọi hàm nạp với kỳ chồng lấn holdout mà không có cờ → phải `raise`.

#### 2.5. Đếm số tổ hợp đã thử

Mọi script quét lưới phải ghi tổng số tổ hợp đã đánh giá vào đầu ra. Không có
con số này thì không thể "khấu trừ" Sharpe (deflated Sharpe) — và không thể
biết một kết quả đẹp là thật hay là hệ quả của việc thử 200 lần.

Đợt này **chỉ cần đếm và in ra**. Công thức deflated Sharpe để đợt sau.

#### 2.6. Kiểm định độ nhạy tham số

Script mới `scripts/param_sensitivity.py`: với một cấu hình gốc, thay đổi
**từng** tham số ±20% (giữ nguyên các tham số khác), in bảng kết quả lân cận.

Quy tắc đánh giá, in kèm trong đầu ra:
- PnL **đổi dấu** trong vùng ±20% → **MONG MANH**;
- PnL đổi > 50% → **MONG MANH**;
- ngược lại → ổn định.

Đây chính là phép kiểm mà `k_tp=4,0` của đợt trước đã trượt: nó là đỉnh của một
đường cong, không phải trung tâm của một vùng bằng phẳng.

### GIAI ĐOẠN 3 — Chi phí (nhỏ nhưng quan trọng nhất)

#### 2.7. Biến chi phí = 0 từ "im lặng" thành "phải nói ra"

Trong `trading/pattern_backtest.py`, đổi:

```python
fee_rate: float = 0.0,
slippage_bps: float = 0.0,
```

thành `float | None = None`, và **raise `ValueError`** với thông báo rõ ràng
nếu gọi mà không truyền. Đo với phí bằng 0 vẫn **được phép** — nhưng phải viết
`fee_rate=0.0` một cách tường minh, để nó xuất hiện trong code review và trong
báo cáo.

Sửa mọi nơi gọi (`measure_octopus_combo_hybrid.py`,
`optimize_octopus_combo_hybrid.py`, `tests/test_pattern_backtest.py`) để truyền
tường minh. **Giữ nguyên giá trị đang dùng** — đợt này không đổi con số nào,
chỉ đổi cách khai báo. Kết quả đo phải không đổi.

#### 2.8. Stress test chi phí

Thêm cờ `--cost-multiplier` (mặc định 1,0) cho các script đo. Chạy và báo cáo ở
1,0× / 1,5× / 2,0× cho các chiến lược đang có. Chiến lược nào chết ở 1,5× thì
biên lợi thế của nó (nếu có) mỏng hơn sai số của chính giả định chi phí.

---

## 3. TIÊU CHÍ HOÀN THÀNH

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | `trading/metrics.py` | Test đơn vị cho từng hàm với số **tính tay được**: ví dụ `profit_factor([+100,+50,-60]) == 2.5`; `max_drawdown` trên chuỗi dựng sẵn; `profit_factor` không có lệnh thua → `None` |
| 2 | Sharpe không có `periods_per_year` mặc định | Gọi thiếu tham số → `TypeError` |
| 3 | Số đo vào báo cáo rổ | Hai script in thêm 4 cột mới |
| 4 | **Không trôi cổng cứng** | `measure_octopus_matched_basket.py` → `−1.615.319.902 / 1.514 / 439 / 748`; `measure_octopus_combo_matched_basket.py` → `−9.826.136.733 / 11.316 / 653` |
| 5 | Khoá holdout | Test: nạp kỳ chồng lấn holdout không cờ → `raise`; có cờ → chạy được và ghi log |
| 6 | Độ nhạy tham số | Chạy trên `octopus_pullback`, in bảng ±20% kèm nhãn MONG MANH/ổn định |
| 7 | Chi phí phải khai báo | Gọi `run_pattern_backtest` thiếu `fee_rate` → `ValueError`; sau khi sửa hết nơi gọi, **kết quả đo không đổi** |
| 8 | Stress chi phí | Bảng 1,0× / 1,5× / 2,0× |
| 9 | Nền xanh | `uv run pytest -m "not integration" -q` (hiện 473) và `uv run ruff check trading tests scripts` |

**Chứng minh test không rỗng:** với tiêu chí 1, 2, 5, 7 — cố ý phá, dán **output
đỏ thô**, khôi phục, `grep -rn "SABOTAGE" trading tests scripts` phải rỗng.

---

## 4. PHẠM VI PHẪU THUẬT

**Được tạo/sửa:**
- `trading/metrics.py`, `trading/sampling.py` (mới)
- `tests/test_metrics.py`, `tests/test_sampling.py` (mới)
- `scripts/param_sensitivity.py` (mới)
- `scripts/measure_octopus_matched_basket.py`,
  `scripts/measure_octopus_combo_matched_basket.py`,
  `scripts/measure_crypto_strategies.py`,
  `scripts/measure_octopus_combo_hybrid.py` — **chỉ thêm cột**, không đổi logic đo
- `trading/pattern_backtest.py` — **chỉ** chữ ký chi phí ở §2.7
- Các nơi gọi bị ảnh hưởng bởi §2.7
- `docs/holdout-unlock-log.md` (mới)

**Cấm đụng:**
- `run_backtest`, `PaperBroker`, `derivative_backtest`, `TrailingStopManager`
- `trading/engine/`, `_default_strategy()`, `config/config.yaml`, `.env`
- `trading/strategies/*` — **không sửa một chiến lược nào ở đợt này.** Đây là
  đợt sửa **thước đo**, không phải sửa **thứ được đo**. Trộn hai việc lại thì
  không còn biết số thay đổi vì thước hay vì chiến lược.
- `_TF_SPEC`; không `TRUNCATE`/`DROP`/xoá dòng; không nạp lại `bars_crypto`

**Không commit, không push.** Claude audit rồi mới commit.

---

## 5. NHỮNG CÂU HỎI PHẢI BÁO LẠI, KHÔNG TỰ QUYẾT

1. Nếu định nghĩa `max_drawdown` trong `metrics.py` không khớp được với
   `backtest.py:257` — **báo lại**, đừng chọn bừa một định nghĩa.
2. Nếu thêm cột làm lệch cổng cứng dù chỉ một đồng — **dừng, báo lại**. Đó là
   dấu hiệu việc "chỉ thêm cột" đã chạm vào đường tính toán.
3. Nếu ranh giới tách mẫu ở §2.3 làm tập validation có quá ít lệnh để nói được
   điều gì — **báo lại con số**, đừng tự dời ranh giới.

---

## 6. BÁO CÁO NỘP LẠI

- Bảng số đo mới cho `octopus_pullback` và `octopus_combo` (đủ 4 cột mới).
- Bảng độ nhạy ±20% kèm nhãn.
- Bảng stress chi phí 1,0×/1,5×/2,0×.
- Output thô tiêu chí 4 và 9 (dán nguyên, không tóm tắt).
- Output đỏ thô từng lần phá hoại + xác nhận `grep` rỗng.
- **Không kết luận chiến lược nào "đạt" hay "nên chạy".** Đợt này chỉ giao thước
  đo. Kết luận là việc của lượt audit sau.
