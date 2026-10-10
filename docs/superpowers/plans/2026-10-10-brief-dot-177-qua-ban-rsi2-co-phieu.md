# Brief đợt 177 — Mua quá bán RSI(2) trong xu hướng tăng, cổ phiếu VN nến ngày (ĐĂNG KÝ TRƯỚC)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. **Giả thuyết thứ 7 của tháng 10**, vượt ngân sách mục F (spec mục H, dòng 10/10 về đợt 177).

## 0. Câu hỏi, kỳ vọng trước, và điều KHÔNG hỏi

**Yêu cầu của chủ dự án (10/10):** "tìm thêm chiến lược giao dịch mới", giao dịch trên tín hiệu kỹ thuật. Claude chọn **đảo chiều ngắn hạn kiểu Connors RSI(2)**, vì:
- đây là họ tín hiệu kỹ thuật **ngược chiều** với mọi họ đã đo âm (phá đỉnh, momentum, pullback chờ bật lên);
- đợt 102 cho thấy nhóm thua đánh bại nhóm thắng ở VN, tức có dấu hiệu đảo chiều;
- đợt 173 bị chết vì chờ "bật lên" mới mua, nên lãi còn lại quá nhỏ. Ở đây mua ngay khi đang quá bán.

**Câu hỏi:** mua mã đang trên MA200 ngay khi RSI(2) xuống rất thấp, bán khi giá vượt MA5 hoặc sau tối đa 10 phiên. Lợi nhuận mỗi lệnh sau phí có **vượt thị trường cùng khoảng thời gian** không?

**Kỳ vọng trước của Claude: âm, nhưng ít chắc hơn các lần trước.**
- Lý do âm: giữ ngắn nên chi phí 0,76%/vòng ăn phần lớn lãi.
- Lý do có thể dương: VN có dấu hiệu đảo chiều (đợt 102).

**Cảnh báo bắt buộc trong báo cáo:**
- Thiếu mã đã hủy niêm yết thổi phồng chiến lược "mua khi giảm" **nhiều nhất**: mã giảm rồi chết đã biến mất khỏi dữ liệu.
- Tập 2023+ đã mở một lần cho họ phá đỉnh (đợt 175). Nó vẫn là ngoài mẫu với họ quá bán này, nhưng là lần mở thứ hai của cùng tập.

**Không hỏi:** có dùng vốn thật được không.

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu, universe, niêm phong
Giống hệt đợt 175 §1.1: `read_bars` của `scripts/screen_pullback_trend.py` (có cổng niêm phong), `load_universe(storage, "exclusions.txt")`, `stock_symbols`. **IS = tín hiệu 2017-01-01 → 2022-11-30**; 2016 dùng để làm nóng MA200. In cảnh báo thiên lệch sống sót.

### 1.2 RSI(2), định nghĩa chốt
- `Δ_i = close[i] − close[i−1]`, `U_i = max(Δ_i, 0)`, `D_i = max(−Δ_i, 0)`.
- Làm trơn Wilder chu kỳ n = 2:
  - khởi tạo ở i = 2: `AU = (U_1 + U_2)/2`, `AD = (D_1 + D_2)/2`;
  - sau đó `AU_i = (AU_{i−1}·(n−1) + U_i)/n`, tương tự `AD`.
- `RSI = 100` khi `AD = 0`; ngược lại `RSI = 100 − 100/(1 + AU/AD)`.
- Tính trên toàn chuỗi `close` của mã (từ nến đầu tiên đọc được), chỉ dùng dữ liệu ≤ i.

### 1.3 Tín hiệu mua (tại CLOSE phiên t)
Đủ cả bốn điều kiện:
1. `liquidity_ok(bars, t, window=20, min_turnover=2 tỷ)`;
2. `close[t] > MA200[t]` (trung bình close đơn giản 200 phiên kết thúc tại t);
3. `RSI2[t] < 10`;
4. không đang giữ mã đó. Phiên thoát cũng tính là đang giữ.

### 1.4 Vào lệnh
OPEN phiên t+1, `entry_status(bars, t, exchange) == "ok"`, ngược lại bỏ tín hiệu. E = t+1.

### 1.5 Thoát lệnh (kiểm tại CLOSE mỗi phiên d ≥ E, kể cả E)
Theo thứ tự ưu tiên:
1. **Hồi phục:** `close[d] > MA5[d]` (trung bình close 5 phiên kết thúc tại d);
2. **Hết giờ:** d = E + 9 (giữ tối đa 10 phiên).

**Không có cắt lỗ giá**, đúng thiết kế gốc của Connors. Rủi ro đuôi được báo ở §1.7.

T+2: phiên thoát = `max(d+1, E+2)`. Điều kiện chạm ở E hay E+1 vẫn được ghi nhận, chỉ bán muộn. Thoát rơi vào nến khối lượng 0 thì lùi tiếp tới phiên có giao dịch. Lợi nhuận lệnh = `net_return(open[E], close[exit])`.

### 1.6 Mốc so sánh và phép thử
Import nguyên văn từ `scripts/screen_pullback_trend.py`: `ew_returns_by_date`, `excess_of_trade`, `monthly_excess`, `evaluate`. **ĐẠT** khi cả bốn điều kiện của `evaluate`:
1. ≥ 300 lệnh;
2. p < 0,05 một phía và trung bình vượt trội tháng > 0;
3. TB ròng mỗi lệnh ≥ 0,5 × cost_rt;
4. profit factor ròng > 1,2.

Dưới 300 lệnh: **THIẾU SỨC MẠNH**.

**Thêm một điều kiện thứ năm, chốt trước vì bài học đợt 175** (IS đạt nhờ vài lệnh đầu cơ và thị trường tăng):
5. **Vượt trội trung bình tính theo trọng số lệnh > 0 sau khi bỏ 1% lệnh có lợi nhuận ròng cao nhất.**

Cả năm điều kiện đều phải đạt.

### 1.7 Báo thêm (mô tả)
- phân phối số ngày giữ; tỷ lệ thoát theo lý do;
- số vị thế mở đồng thời theo ngày (min/trung vị/max);
- kết quả theo năm (số lệnh, TB ròng, TB vượt trội);
- 10 lệnh lỗ nặng nhất (mã, ngày, lợi nhuận) và tỷ lệ lệnh lỗ hơn 10%;
- số tín hiệu bị bỏ vì giá trần.

### 1.8 Kỷ luật chạy
Chạy IS thật **một lần**. Lỗi code buộc chạy lại thì báo cả hai lần. Cấm đổi bất kỳ con số nào ở §1.2–§1.6 (2, 10, MA200, MA5, 10 phiên, 2 tỷ), thêm cắt lỗ hay bộ lọc.

## 2. Phạm vi
- **Được thêm:** `scripts/screen_rsi2_reversion.py`, `tests/test_screen_rsi2_reversion.py`, báo cáo `docs/superpowers/research/2026-10-10-dot-177-qua-ban-rsi2.md`.
- **Được import, không sửa:** `scripts/screen_pullback_trend.py`, `scripts/screen_donchian_breakout.py`, `scripts/screen_momentum_portfolio.py`, `trading/stock_study.py`, `trading/paper_broker.py`, `trading/metrics.py`.
- **Không sửa:** mọi file khác. **Chỉ đọc DB.** Cấm chạy `scripts/sched.sh`. Không đụng các file của đợt 176 nếu đợt đó đang làm song song.
- Khuôn `_ROOT`/`sys.path` như `scripts/screen_donchian_breakout.py`; `--help` chạy được từ gốc repo.
- **GitNexus:** `gitnexus <lệnh> -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs`, **không `npx`**. Chạy `context` cho `evaluate`, `excess_of_trade`, `entry_status` trước khi viết; `detect-changes --scope all` sau. Ghi rõ: file mới chưa được git theo dõi nên "No changes" là bình thường.

## 3. Kiểm chứng — TDD trên nến dựng tay, không đọc DB
**Dữ liệu dựng tay phải có ngày tín hiệu NẰM TRONG IS (2017–2022).** Agent đợt 173 và 175 đều mắc lỗi dựng dữ liệu năm 2016 nên mọi test ra "0 lệnh".
1. **RSI(2) tính tay:** chuỗi close `[10, 11, 10.5, 10, 9]` → RSI tại từng phiên khớp giá trị tính tay ghi sẵn trong test (sai số 1e-9). Chuỗi chỉ tăng → 100.
2. **Tín hiệu:** mã trên MA200, ba phiên giảm liên tiếp đưa RSI2 < 10 → đúng một tín hiệu đúng ngày. Cùng chuỗi nhưng dưới MA200 → không có.
3. **Không nhìn tương lai:** sửa mọi nến sau t → tín hiệu tại t không đổi.
4. **Giá trần:** open t+1 ở giá trần → không có lệnh.
5. **Hai lý do thoát:** chuỗi hồi lên trên MA5 ở phiên E+3 → thoát close E+4 lý do hồi phục; chuỗi đi ngang dưới MA5 → thoát close E+10 lý do hết giờ.
6. **T+2:** close[E] đã > MA5[E] → lý do hồi phục, thoát ở close E+2.
7. **Một vị thế mỗi mã:** tín hiệu trong lúc giữ bị bỏ; tín hiệu ngay sau phiên thoát được nhận.
8. **Niêm phong:** nến ≥ 01/01/2023 thì hàm đọc ném lỗi.
9. **Điều kiện 5:**
   - 100 lệnh, trong đó một lệnh +500% và 99 lệnh vượt trội −0,1% → điều kiện 5 KHÔNG đạt;
   - 100 lệnh đều vượt trội +0,5% → đạt.
10. **Đối chứng:**
   - dương: sau tín hiệu giá hồi 5% trong 3 phiên → ĐẠT điều kiện 2–5;
   - âm: sau tín hiệu giá đi ngẫu nhiên, `random.Random(7)` → không ĐẠT.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Khởi tạo RSI bằng SMA cả chuỗi thay vì Wilder → test 1 đỏ.
- Dùng `close[t+1]` để tính RSI tại t → test 3 đỏ.
- Bỏ kiểm điều kiện thoát ở phiên E → test 6 đỏ.
- Không bỏ 1% lệnh lãi nhất ở điều kiện 5 → test 9 đỏ.

```
uv run pytest tests/test_screen_rsi2_reversion.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 10 test xanh; bốn bước phá hoại đỏ đúng test. Toàn bộ bộ test không có test mới đỏ (dán số trước/sau). Ruff sạch.
- `--help` chạy được. Phép đo IS chạy **một lần**. Báo cáo có:
  - bảng năm điều kiện (p, KTC);
  - mọi mục §1.7;
  - đối chiếu với kỳ vọng trước của Claude;
  - cảnh báo đa so sánh (7 giả thuyết trong tháng 10, khoảng 30% có một p < 0,05 do may) và thiên lệch sống sót.

## 5. Quy tắc đọc kết quả
- **KHÔNG ĐẠT:** ghi "Quá bán RSI(2) trên MA200, thoát MA5 / 10 phiên: KHÔNG có lợi thế trên IS 2017–2022", phép đo âm thứ 19.
- **ĐẠT:** Claude kiểm độc lập trên toàn universe, rồi mở niêm phong **một lần** (tín hiệu 2023-01 → 09/2026), ghi `docs/holdout-unlock-log.md` trước khi chạy và lặp lại đủ năm điều kiện.

## 6. Báo cáo cho Claude
1. Output pytest/ruff, bảng phá hoại, `detect-changes`.
2. Lệnh chạy IS và **output đầy đủ, nguyên văn**.
3. Câu xác nhận: "Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`."
4. Mọi chỗ brief mơ hồ phải tự diễn giải.
