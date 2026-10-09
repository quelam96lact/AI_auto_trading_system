# Brief đợt 171 — Tối ưu tham số `octopus_pullback` trên nến ngày, walk-forward (ĐĂNG KÝ TRƯỚC)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. Đây là **giả thuyết thứ 4 của tháng 10**, vượt ngân sách mục F; chủ dự án cho phép ngày 09/10 (spec mục H).

**Phép đo thật CHƯA được chạy** cho tới khi Claude báo dữ liệu mã đã hủy niêm yết đã nạp vào `bars_daily` (đợt 170 → đợt nạp tiếp theo). Agent viết code và test ngay; Claude ra lệnh chạy.

---

## 0. Bối cảnh, kỳ vọng trước, và điều KHÔNG hỏi

- `octopus_pullback` là chiến lược engine đang chạy. Số đo đã có: rổ 310 mã nến 5 phút **574 lệnh, PF 0,47** (đợt 11); nến ngày **thua mua-và-giữ** (đợt 18). Tham số `k_TP` từng được tối ưu (06/09) mà không ra lợi thế.
- **Octopus đã nhìn dữ liệu 2023+**: đợt 18 đo 2016 → 08/2026, và nhật ký niêm phong ghi mở cho OctopusPullback ngày 06/09. Vì vậy **không còn tập niêm phong sạch trong quá khứ**. Thiết kế dưới đây chọn tham số trên 2016–2019, kiểm trên 2020–2022, và **không đọc nến từ 2023** (giữ cho không làm bẩn thêm).
- **Kỳ vọng trước của Claude: âm.** Bộ tham số chọn trên 2016–2019 nhiều khả năng không giữ được thứ hạng ở 2020–2022 (dấu hiệu khớp nhiễu). Nếu một bộ tham số làm một chiến lược PF 0,47 thành có lời thì đáng nghi trước khi đáng mừng.
- **Không hỏi:** có dùng vốn thật được không. Qua mọi cửa ở đây chỉ mở đường tới paper forward.

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu và universe
- `bars_daily`, đọc **tới 31/12/2022**; nến ≥ 01/01/2023 thì ném lỗi (`validate_sealed_bars`, `trading/stock_study.py`).
- Universe: `load_universe(storage, "exclusions.txt")`, chỉ mã cổ phiếu (`is_stock_symbol` của `scripts/screen_momentum_portfolio.py`). **Gồm cả mã đã hủy niêm yết** khi chúng có trong `bars_daily`. Báo số mã có nến cuối trước 30/06/2022 (phải > 0 sau đợt nạp; bằng 0 thì dừng, báo Claude).
- Lọc thanh khoản: giữ nguyên lọc của chính chiến lược (`min_avg_value_20 = 2 tỷ`, point-in-time). Không thêm lọc nào khác.

### 1.2 Động cơ backtest
Dùng đúng đường của `scripts/measure_strategy.py`: `run_backtest` (`trading/backtest.py`) từng mã, `RiskManager(capital=capital)`, `TrailingStopManager()` mặc định, vốn **1 tỷ mỗi mã**, phí/thuế/trượt giá và T+2,5 theo mặc định của `run_backtest` (import từ `trading/paper_broker.py`). **Import**, không chép lại.

### 1.3 Lưới tham số (12 bộ, cố định; các tham số khác giữ mặc định)
| Tham số | Giá trị |
|---|---|
| `tp_atr_mult` | 1,5 / **2,0** / 3,0 |
| `pullback_window` | **5** / 10 |
| `ema_trend` | 100 / **200** |

Bộ **mặc định** = (2,0; 5; 200), in đậm. Không thêm giá trị nào, không thêm tham số nào.

### 1.4 Chia giai đoạn
- **Chọn:** 2016-01-01 → 2019-12-31. **Kiểm:** 2020-01-01 → 2022-12-31.
- Mỗi giai đoạn chạy **riêng**, vốn mới, không mang vị thế qua. Chỉ báo tín hiệu cần warm-up `ema_trend` phiên, nên đọc thêm nến **trước** ngày bắt đầu đủ để làm nóng, nhưng **không** tính lệnh/PnL trước ngày bắt đầu. Agent dùng cơ chế warm-up sẵn có nếu `run_backtest` có; nếu không thì báo cách đã làm.

### 1.5 Chỉ số (mỗi bộ × mỗi giai đoạn, cộng dồn mọi mã)
Tổng lệnh (lệnh bán đã khớp), tỷ lệ thắng, **profit factor ròng** (tổng lời / tổng lỗ, sau phí), tổng PnL ròng, PnL ròng / tổng vốn đã cấp, và PnL mua-và-giữ cùng mã, cùng vốn, cùng giai đoạn.

### 1.6 Quy tắc chọn (trên giai đoạn CHỌN, chốt)
Trong các bộ có **≥ 300 lệnh** ở 2016–2019, chọn bộ có **PF ròng cao nhất**. Hòa thì chọn bộ gần mặc định hơn (khác ít tham số hơn). Không bộ nào ≥ 300 lệnh thì ghi **THIẾU SỨC MẠNH**, dừng, không kiểm.

### 1.7 Phép kiểm (trên giai đoạn KIỂM, chạy MỘT lần cho cả 12 bộ)
Bộ được chọn **ĐẠT** khi đủ cả năm:
1. ≥ 100 lệnh ở 2020–2022;
2. PF ròng > 1,2;
3. PnL ròng > 0;
4. PF ròng cao hơn bộ mặc định ở 2020–2022;
5. **Xếp hạng PF của bộ được chọn ở 2020–2022 nằm trong top 3/12.** Bộ thắng ở giai đoạn chọn rơi xuống giữa bảng ở giai đoạn kiểm là dấu hiệu khớp nhiễu.

Báo thêm (mô tả): tương quan hạng Spearman giữa PF giai đoạn chọn và PF giai đoạn kiểm trên 12 bộ. Âm hoặc gần 0 nghĩa là thứ hạng tham số không bền.

### 1.8 Kỷ luật chạy
Chạy thật **một lần** sau khi Claude cho phép. Lỗi code buộc chạy lại thì báo cả hai lần. Cấm đổi lưới, quy tắc chọn, ngưỡng, giai đoạn, vốn, hay thêm lọc.

## 2. Phạm vi
- **Được thêm:** `scripts/optimize_octopus_walk_forward.py`, `tests/test_optimize_octopus_walk_forward.py`, báo cáo `docs/superpowers/research/2026-10-09-dot-171-toi-uu-tham-so-octopus.md` (chỉ sau khi chạy thật).
- **Được import, không sửa:** `scripts/measure_strategy.py`, `trading/backtest.py`, `trading/strategies/octopus_pullback.py`, `trading/stock_study.py`, `scripts/screen_momentum_portfolio.py`, `trading/paper_broker.py`.
- **Không sửa:** mọi file khác, kể cả tham số mặc định của chiến lược đang chạy trong engine. **Chỉ đọc DB.** Cấm chạy `scripts/sched.sh`.
- Không sửa `scripts/optimize_octopus_combo_hybrid.py` (công cụ cũ, đợt 06/09); thấy trùng lặp thì báo.
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `context` cho `run_backtest`, `measure_one`, `OctopusPullbackStrategy`; `detect_changes` sau khi xong.

## 3. Kiểm chứng — TDD trên nến dựng tay, không đọc DB
1. **Lưới:** sinh đúng 12 bộ, có bộ mặc định, không trùng.
2. **Tham số thật sự đi vào chiến lược:** dựng chiến lược với `tp_atr_mult=3.0` → thuộc tính của đối tượng đúng 3.0; hai bộ khác `tp_atr_mult` cho ra lệnh khác nhau trên cùng chuỗi nến có xu hướng (nến dựng tay).
3. **Không tính lệnh trong warm-up:** chuỗi nến có tín hiệu trước ngày bắt đầu → không có lệnh/PnL nào trước ngày bắt đầu.
4. **Quy tắc chọn:** bảng giả 12 bộ → chọn đúng bộ PF cao nhất trong các bộ ≥ 300 lệnh; hòa thì chọn bộ gần mặc định; không bộ nào đủ lệnh thì trả "THIẾU SỨC MẠNH".
5. **Năm điều kiện ĐẠT:** mỗi điều kiện có một ca giả lập làm nó trượt, còn bốn điều kiện kia đạt → kết luận KHÔNG ĐẠT.
6. **Niêm phong:** có nến ≥ 01/01/2023 thì hàm đọc ném lỗi.
7. **Giai đoạn kiểm không ảnh hưởng việc chọn:** đổi kết quả mọi bộ ở 2020–2022 → bộ được chọn không đổi.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Chọn theo PnL giai đoạn kiểm thay vì PF giai đoạn chọn → test 7 đỏ.
- Bỏ điều kiện top 3/12 → test 5 đỏ.
- Tính lệnh trong warm-up → test 3 đỏ.

```
uv run pytest tests/test_optimize_octopus_walk_forward.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi (phần agent)
- 7 test xanh, ba bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ test không có test mới đỏ, ruff sạch, `detect_changes` chỉ gồm hai file mới.
- Thời gian chạy ước tính (chạy thử **một** bộ tham số trên **10 mã** giai đoạn chọn, chỉ để đo thời gian; **không** in hay báo kết quả PnL của lần thử).
- Lệnh chạy thật cho Claude.

## 5. Quy tắc đọc kết quả
- **KHÔNG ĐẠT** → ghi "Tối ưu tham số octopus_pullback (12 bộ, walk-forward 2016–2019/2020–2022): KHÔNG có bộ tham số bền". Phép đo âm thứ 16. Đề xuất chủ dự án ngừng phát triển octopus.
- **ĐẠT** → kèm cảnh báo đa so sánh (12 bộ, giả thuyết thứ 4 trong tháng). Bước sau là **paper forward** bộ đó song song với bộ mặc định, ≥ 50 lệnh hoặc ≥ 3 tháng (spec mục E). **Không** đổi tham số engine cho tới khi paper forward qua.

## 6. Báo cáo cho Claude (phần agent)
Output pytest/ruff, bảng phá hoại, `detect_changes`, thời gian ước tính, lệnh chạy thật, cách xử lý warm-up, và mọi chỗ phải tự diễn giải.
