# Brief đợt 173 — Pullback trong xu hướng, giữ 2–4 tuần, cổ phiếu VN nến ngày (ĐĂNG KÝ TRƯỚC)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. **Giả thuyết thứ 5 của tháng 10**, vượt ngân sách mục F; chủ dự án cho phép ngày 10/10 (spec mục H).

## 0. Câu hỏi, kỳ vọng trước, và điều KHÔNG hỏi

**Yêu cầu của chủ dự án:** chiến lược giữ vài tuần đến 1 tháng, giao dịch chủ động chứ không mua-và-giữ. Chủ dự án chọn hướng **pullback trong xu hướng**. Các quy tắc cụ thể ở §1 do Claude đặt, chốt trước khi ai nhìn dữ liệu.

**Câu hỏi:** mua cổ phiếu đang trong xu hướng tăng dài hạn ngay khi nó bật lên sau một nhịp điều chỉnh, giữ tối đa 20 phiên, có cắt lỗ và chốt lời, thì lợi nhuận mỗi lệnh sau phí có **vượt thị trường cùng khoảng thời gian** không?

**Kỳ vọng trước của Claude: âm.** Lý do cụ thể:
- Octopus, cũng là một dạng pullback trong xu hướng, vừa âm ở đợt 171: không bộ tham số nào có PF ≥ 1 trên 2016–2019.
- Momentum 12−1 tháng thua có ý nghĩa (đợt 102), tức "đang tăng" không phải lợi thế ở VN giai đoạn này.

Điểm khác với octopus: đây là quy tắc trên nến ngày, thời gian giữ cố định, so sánh **từng lệnh** với thị trường cùng khoảng thời gian.

**Không hỏi:** có dùng vốn thật được không. Qua IS chỉ mở đường tới bước mở niêm phong (§5).

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu, universe, niêm phong
- `bars_daily`, `load_universe(storage, "exclusions.txt")`, chỉ mã cổ phiếu (`stock_symbols` của `scripts/screen_momentum_portfolio.py`). Bỏ nến giá ≤ 0 (`clean_bars`). Ngày theo giờ VN (`bar_date`).
- **Niêm phong:** đọc tới 31/12/2022; nến ≥ 01/01/2023 thì ném lỗi (`validate_sealed_bars`). **IS = mọi tín hiệu có ngày tín hiệu trong 2017-01-01 → 2022-11-30** (2016 dùng để làm nóng MA200; tín hiệu cuối cách 31/12/2022 đủ 20 phiên để đóng lệnh).
- **Thiên lệch sống sót:** chủ dự án quyết định không dùng mã đã hủy niêm yết (spec H 10/10). Script in cảnh báo; chỉ so với thị trường cùng universe, không so với ETF.

### 1.2 Tín hiệu mua (tính tại CLOSE phiên t, chỉ dùng dữ liệu ≤ t)
Đủ cả năm điều kiện:
1. **Thanh khoản:** trung bình `close × volume` 20 phiên kết thúc tại t ≥ **2 tỷ** (`liquidity_ok`).
2. **Xu hướng dài hạn:** `close[t] > MA200[t]` và `MA50[t] > MA200[t]` (trung bình close đơn giản).
3. **Có nhịp điều chỉnh:** `H20` = close cao nhất trong 20 phiên kết thúc tại t−1. Độ sâu `1 − min(close[t−5..t−1]) / H20` nằm trong **[5%, 15%]**.
4. **Bật lên:** `close[t] > high[t−1]`.
5. **Không đang giữ** mã đó (mỗi mã tối đa một vị thế mở; tín hiệu trong lúc đang giữ thì bỏ).

### 1.3 Vào lệnh
Mua ở **OPEN phiên t+1**. Dùng `entry_status(bars, t, exchange)`: khác `"ok"` (mở cửa giá trần, khối lượng 0, không có nến) thì bỏ tín hiệu, không thay mã khác. Gọi E = chỉ số nến vào lệnh (t+1).

### 1.4 Thoát lệnh (kiểm tại CLOSE mỗi phiên d ≥ E, thoát ở CLOSE phiên d+1)
Điều kiện đầu tiên xảy ra:
1. **Cắt lỗ:** `close[d] ≤ open[E] × 0,92` (−8%).
2. **Chốt lời:** `close[d] ≥ H20` của tín hiệu (về lại đỉnh 20 phiên trước nhịp điều chỉnh).
3. **Hết giờ:** d = E + 19 (giữ tối đa 20 phiên).

Ràng buộc T+2: phiên thoát không sớm hơn E+2. Thoát rơi vào nến không có giao dịch thì thoát ở CLOSE phiên kế tiếp có giao dịch. Lợi nhuận lệnh = `net_return(open[E], close[exit])` (`trading/stock_study.py`, đã gồm phí, thuế, trượt giá import từ `paper_broker`).

### 1.5 Mốc so sánh từng lệnh (thị trường cùng khoảng thời gian)
`EW_ret(d)` = trung bình cộng `close[d]/close[d−1] − 1` của mọi mã đủ điều kiện thanh khoản ở phiên d (điều kiện 1 của §1.2). Lợi nhuận mốc của một lệnh = `∏(1 + EW_ret(d)) − 1` với d từ E tới phiên thoát, **không trừ phí**. **Vượt trội của lệnh** = lợi nhuận ròng lệnh − lợi nhuận mốc.

### 1.6 Phép thử (chốt)
- Gom lệnh theo **tháng vào lệnh**; mỗi tháng lấy **trung bình vượt trội** của các lệnh vào trong tháng (tháng không có lệnh thì bỏ). Ra chuỗi theo tháng.
- `block_bootstrap` của đợt 102 trên chuỗi đó: khối 3 tháng, 2.000 lần, `seed=42`.
- **ĐẠT** khi cả bốn:
  1. **≥ 300 lệnh** trong IS;
  2. **p < 0,05 một phía**, trung bình vượt trội tháng > 0;
  3. **trung bình lợi nhuận ròng mỗi lệnh ≥ 0,5 × cost_rt**, với `cost_rt = 2·FEE_RATE + SELL_TAX_RATE + 2·SLIPPAGE_BPS/10.000`. Tương đương lợi nhuận gộp ≥ 1,5 lần chi phí, theo spec mục B hàng "alpha";
  4. **profit factor ròng > 1,2** (tổng lời / tổng lỗ của lợi nhuận ròng từng lệnh).
- Dưới 300 lệnh: nhãn **THIẾU SỨC MẠNH**, không kết luận.

### 1.7 Báo thêm (mô tả)
Phân phối số ngày giữ; tỷ lệ thoát theo từng lý do (cắt lỗ / chốt lời / hết giờ); số vị thế mở đồng thời (min/trung vị/max theo ngày; con số này cho biết cần bao nhiêu vốn); kết quả theo năm; số tín hiệu bị bỏ vì giá trần.

### 1.8 Kỷ luật chạy
Agent chạy phép đo IS thật **một lần**. Lỗi code buộc chạy lại thì báo cả hai lần. Cấm đổi bất kỳ con số nào ở §1.2–§1.6 (2 tỷ, MA50/200, 5–15%, 20 phiên, −8%, 20 phiên giữ), thêm điều kiện hay bộ lọc.

## 2. Phạm vi
- **Được thêm:** `scripts/screen_pullback_trend.py`, `tests/test_screen_pullback_trend.py`, báo cáo `docs/superpowers/research/2026-10-10-dot-173-pullback-trong-xu-huong.md`.
- **Được import, không sửa:** `scripts/screen_momentum_portfolio.py`, `trading/stock_study.py`, `trading/paper_broker.py`, `trading/metrics.py`.
- **Không sửa:** mọi file khác, kể cả engine và chiến lược đang chạy. **Chỉ đọc DB.** Cấm chạy `scripts/sched.sh`.
- Chạy trực tiếp `python scripts/...` phải import được `scripts.*`: dùng khuôn `_ROOT`/`sys.path` của `scripts/screen_ml_cross_section.py` (lỗi này đã xảy ra ở đợt 171).
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `context` cho các hàm dùng lại; `detect_changes` sau khi xong.

## 3. Kiểm chứng — TDD trên nến dựng tay, không đọc DB
1. **Tín hiệu đúng:** dựng chuỗi có xu hướng tăng, điều chỉnh 10%, rồi một phiên đóng cửa trên đỉnh phiên trước → đúng một tín hiệu đúng ngày. Điều chỉnh 3% hoặc 20% → không có tín hiệu.
2. **Không nhìn tương lai:** sửa mọi nến sau t → tín hiệu tại t không đổi.
3. **Vào ở open t+1, loại giá trần:** open t+1 ở giá trần → không có lệnh.
4. **Ba lý do thoát:** ba chuỗi dựng tay lần lượt chạm −8%, chạm H20, và đi ngang → thoát đúng lý do, đúng phiên (close của phiên sau phiên chạm).
5. **T+2:** chạm cắt lỗ ngay phiên E → thoát không sớm hơn close E+2.
6. **Một vị thế mỗi mã:** tín hiệu thứ hai trong lúc đang giữ bị bỏ.
7. **Vượt trội:** mốc EW dựng tay +3% trong khoảng giữ, lệnh ròng +5% → vượt trội đúng +2%.
8. **Niêm phong:** có nến ≥ 01/01/2023 thì hàm đọc ném lỗi.
9. **Đối chứng dương:** dữ liệu tổng hợp mà mọi mã sau khi bật lên đều tăng tiếp 10% → ĐẠT điều kiện 2–4. **Đối chứng âm:** sau khi bật lên thì đi ngẫu nhiên quanh mốc → không ĐẠT.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Dùng `close[t+1]` trong điều kiện bật lên → test 2 đỏ.
- Bỏ ràng buộc T+2 → test 5 đỏ.
- Cho phép nhiều vị thế cùng mã → test 6 đỏ.
- Thoát ở close phiên chạm thay vì phiên sau → test 4 đỏ.

```
uv run pytest tests/test_screen_pullback_trend.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 9 test xanh, bốn bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ test không có test mới đỏ (dán số trước/sau), ruff sạch, `detect_changes` chỉ gồm ba file mới.
- `python scripts/screen_pullback_trend.py --help` chạy được từ thư mục gốc repo.
- Phép đo IS thật đã chạy **một lần**. Báo cáo có: số mã, số lệnh, bảng §1.6 (bốn điều kiện, p, KTC), mọi mục §1.7, đối chiếu kỳ vọng trước của Claude, và cảnh báo đa so sánh + thiên lệch sống sót.

## 5. Quy tắc đọc kết quả
- KHÔNG ĐẠT → ghi "Pullback trong xu hướng (giữ ≤ 20 phiên, cắt lỗ 8%): KHÔNG có lợi thế trên IS 2017–2022", phép đo âm thứ 17. Không mở niêm phong.
- ĐẠT → Claude mở niêm phong **một lần** (2023-01 → 09/2026), ghi `docs/holdout-unlock-log.md`, lặp lại đủ bốn điều kiện. Qua thì mới bàn tới paper forward (spec mục E).

## 6. Báo cáo cho Claude
1. Output pytest/ruff, bảng phá hoại, `detect_changes`.
2. Lệnh chạy IS và **output đầy đủ, nguyên văn**.
3. Một câu xác nhận: "Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`."
4. Mọi chỗ brief mơ hồ mà agent phải tự diễn giải; không im lặng chọn.
