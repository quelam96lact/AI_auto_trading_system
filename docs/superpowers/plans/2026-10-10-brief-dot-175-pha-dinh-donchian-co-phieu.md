# Brief đợt 175 — Phá đỉnh Donchian 55/20, cổ phiếu VN nến ngày (ĐĂNG KÝ TRƯỚC)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. **Giả thuyết thứ 6 của tháng 10**, vượt ngân sách mục F (spec mục H, dòng 10/10 về đợt 175).

## 0. Câu hỏi, kỳ vọng trước, và điều KHÔNG hỏi

**Yêu cầu của chủ dự án (10/10):** "tìm chiến lược tối ưu khác", "Tôi muốn giao dịch trên tín hiệu kĩ thuật". Trước đó (đợt 173) chủ dự án muốn giữ vài tuần đến 1 tháng, không mua-và-giữ. Claude chọn **phá đỉnh Donchian**, vì đây là họ tín hiệu kỹ thuật lớn duy nhất chưa đo trên cổ phiếu VN. Đợt 37 chỉ đo Donchian trên crypto. Các họ đã đo âm: SMA cắt nhau, VCP, SMC, SEPA, octopus, pullback trong xu hướng, RSI/momentum làm đặc trưng.

**Câu hỏi:** mua khi giá đóng cửa vượt đỉnh 55 phiên, bán khi thủng đáy 20 phiên, có cắt lỗ và giới hạn thời gian giữ. Lợi nhuận mỗi lệnh sau phí có **vượt thị trường cùng khoảng thời gian** không?

**Kỳ vọng trước của Claude: âm.** Lý do:
- Momentum 12−1 tháng thua có ý nghĩa ở VN (đợt 102). Nhóm thua còn đánh bại nhóm thắng.
- VCP và SEPA, hai dạng mua khi phá nền, đều âm (đợt 99, 123).

Điểm khác: đây là phá đỉnh thuần theo giá, có thoát lệnh theo kênh đáy (trailing), không cần mẫu hình nền.

**Không hỏi:** có dùng vốn thật được không. Qua IS chỉ mở đường tới bước mở niêm phong (§5).

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu, universe, niêm phong
Giống hệt đợt 173 §1.1:
- `bars_daily`, `load_universe(storage, "exclusions.txt")`, chỉ mã cổ phiếu (`stock_symbols`), bỏ nến giá ≤ 0.
- Đọc bằng `read_bars` của `scripts/screen_pullback_trend.py`, hàm này kiểm niêm phong trước (`validate_sealed_bars`). Nến ≥ 01/01/2023 thì ném lỗi.
- **IS = mọi tín hiệu có ngày tín hiệu trong 2017-01-01 → 2022-10-31.** Tín hiệu cuối cách 31/12/2022 đủ 40 phiên để đóng lệnh. Năm 2016 dùng để làm nóng.
- **Thiên lệch sống sót:** không dùng mã đã hủy niêm yết (spec H 10/10). Script in cảnh báo; chỉ so với thị trường cùng universe.

### 1.2 Tín hiệu mua (tính tại CLOSE phiên t, chỉ dùng dữ liệu ≤ t)
Đủ cả ba điều kiện:
1. **Thanh khoản:** `liquidity_ok(bars, t, window=20, min_turnover=2 tỷ)`.
2. **Phá đỉnh:** `close[t] > max(high[t−55..t−1])`. Cần đủ 55 nến trước t.
3. **Không đang giữ** mã đó (mỗi mã tối đa một vị thế; tín hiệu trong lúc giữ thì bỏ). Phiên thoát lệnh cũng tính là đang giữ.

### 1.3 Vào lệnh
Mua ở **OPEN phiên t+1**. Dùng `entry_status(bars, t, exchange)`: khác `"ok"` thì bỏ tín hiệu. Gọi E = t+1.

### 1.4 Thoát lệnh (kiểm tại CLOSE mỗi phiên d ≥ E, kể cả E; thoát ở CLOSE phiên d+1)
Điều kiện đầu tiên xảy ra, theo thứ tự ưu tiên:
1. **Cắt lỗ:** `close[d] ≤ open[E] × 0,90` (−10%).
2. **Thủng kênh đáy:** `close[d] < min(low[d−20..d−1])`. Cửa sổ trượt theo d, có thể lùi trước E.
3. **Hết giờ:** d = E + 39 (giữ tối đa 40 phiên, khoảng 2 tháng).

Ràng buộc T+2: phiên thoát = `max(d+1, E+2)`. Điều kiện chạm ở phiên E hay E+1 vẫn được ghi nhận, chỉ bán muộn tới E+2. **Đây là lỗi agent đợt 173 từng mắc: không được bỏ qua điều kiện chạm ở phiên E.** Thoát rơi vào nến khối lượng 0 thì thoát ở CLOSE phiên kế tiếp có giao dịch. Lợi nhuận lệnh = `net_return(open[E], close[exit])`.

### 1.5 Mốc so sánh và phép thử
Dùng lại **nguyên văn** từ `scripts/screen_pullback_trend.py`, import, không chép lại:
- `ew_returns_by_date`, `excess_of_trade`, `monthly_excess`, `evaluate`.

Trong đó:
- Vượt trội = lợi nhuận ròng của lệnh − lợi nhuận mua đều mọi mã đủ thanh khoản trong cùng khoảng giữ.
- Chuỗi vượt trội theo tháng vào lệnh.
- Bootstrap khối 3 tháng, 2.000 lần, `seed=42`.

**ĐẠT** khi cả bốn điều kiện của `evaluate`:
1. ≥ 300 lệnh;
2. p < 0,05 một phía và trung bình > 0;
3. lợi nhuận ròng trung bình mỗi lệnh ≥ 0,5 × cost_rt;
4. profit factor ròng > 1,2.

Dưới 300 lệnh thì nhãn **THIẾU SỨC MẠNH**.

### 1.6 Báo thêm (mô tả)
- phân phối số ngày giữ (min/trung vị/trung bình/max);
- tỷ lệ thoát theo lý do (cắt lỗ / kênh đáy / hết giờ);
- số vị thế mở đồng thời theo ngày (min/trung vị/max);
- kết quả theo năm (số lệnh, lợi nhuận ròng TB, vượt trội TB);
- số tín hiệu bị bỏ vì giá trần.

### 1.7 Kỷ luật chạy
Agent chạy phép đo IS thật **một lần**. Lỗi code buộc chạy lại thì báo cả hai lần. Cấm đổi bất kỳ con số nào ở §1.2–§1.5 (55, 20, 2 tỷ, −10%, 40 phiên), thêm điều kiện hay bộ lọc (kể cả MA200).

## 2. Phạm vi
- **Được thêm:**
  - `scripts/screen_donchian_breakout.py`;
  - `tests/test_screen_donchian_breakout.py`;
  - báo cáo `docs/superpowers/research/2026-10-10-dot-175-pha-dinh-donchian.md`.
- **Được import, không sửa:** `scripts/screen_pullback_trend.py`, `scripts/screen_momentum_portfolio.py`, `trading/stock_study.py`, `trading/paper_broker.py`, `trading/metrics.py`.
- **Không sửa:** mọi file khác, kể cả engine và chiến lược đang chạy. **Chỉ đọc DB.** Cấm chạy `scripts/sched.sh`.
- Khuôn `_ROOT`/`sys.path` như `scripts/screen_pullback_trend.py`, để `python scripts/screen_donchian_breakout.py --help` chạy được từ gốc repo.
- **GitNexus:** gọi `gitnexus <lệnh> -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs <lệnh> --repo .`. **Không dùng `npx gitnexus`** (ngày 10/10, `npx` kéo bản khác và làm hỏng index). Chạy `context` cho `evaluate`, `excess_of_trade`, `entry_status` trước khi viết; `detect-changes --scope all` sau khi xong.

## 3. Kiểm chứng — TDD trên nến dựng tay, không đọc DB
1. **Tín hiệu đúng:** chuỗi đi ngang 60 phiên rồi một phiên đóng cửa vượt đỉnh 55 phiên → đúng một tín hiệu đúng ngày. Đóng cửa bằng đúng đỉnh (không vượt) → không có.
2. **Không nhìn tương lai:** sửa mọi nến sau t → tín hiệu tại t không đổi.
3. **Vào ở open t+1, loại giá trần:** open t+1 ở giá trần → không có lệnh.
4. **Ba lý do thoát:** ba chuỗi dựng tay lần lượt chạm −10%, thủng đáy 20 phiên, và tăng đều 40 phiên → đúng lý do, đúng phiên thoát (close của phiên sau phiên chạm; hết giờ ở close E+40).
5. **Ưu tiên:** cùng một phiên chạm cả cắt lỗ và thủng kênh → lý do là cắt lỗ.
6. **T+2:** chạm cắt lỗ ngay phiên E → lý do cắt lỗ, thoát ở close E+2 (không phải trễ hơn, không bị bỏ qua).
7. **Một vị thế mỗi mã:** tín hiệu thứ hai trong lúc đang giữ bị bỏ; tín hiệu ngay sau phiên thoát được nhận.
8. **Niêm phong:** có nến ≥ 01/01/2023 thì hàm đọc ném lỗi.
9. **Đối chứng dương:** dữ liệu tổng hợp mà sau phá đỉnh giá tăng tiếp 15% rồi gãy → ĐẠT điều kiện 2–4. **Đối chứng âm:** sau phá đỉnh giá đi ngẫu nhiên quanh mốc → không ĐẠT.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Dùng `high[t]` trong cửa sổ đỉnh (55 phiên kết thúc tại t thay vì t−1) → test 1 đỏ.
- Bỏ qua điều kiện chạm ở phiên E (vòng kiểm bắt đầu từ E+2) → test 6 đỏ.
- Đảo thứ tự ưu tiên cắt lỗ / kênh đáy → test 5 đỏ.
- Thoát ở close phiên chạm thay vì phiên sau → test 4 đỏ.

```
uv run pytest tests/test_screen_donchian_breakout.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 9 test xanh; bốn bước phá hoại, mỗi bước làm đỏ đúng test đã nêu.
- Bộ test không có test mới đỏ (dán số trước/sau), ruff sạch, `detect-changes` chỉ gồm ba file mới.
- `python scripts/screen_donchian_breakout.py --help` chạy được từ gốc repo.
- Phép đo IS thật đã chạy **một lần**. Báo cáo có:
  - số mã, số lệnh, bảng bốn điều kiện (p, KTC);
  - mọi mục §1.6;
  - đối chiếu với kỳ vọng trước của Claude;
  - cảnh báo đa so sánh (6 giả thuyết trong tháng 10) và thiên lệch sống sót.

## 5. Quy tắc đọc kết quả
- **KHÔNG ĐẠT:** ghi "Phá đỉnh Donchian 55/20 (cắt lỗ 10%, giữ ≤ 40 phiên): KHÔNG có lợi thế trên IS 2017–2022", phép đo âm thứ 18. Không mở niêm phong.
- **ĐẠT:** Claude mở niêm phong **một lần** (2023-01 → 09/2026), ghi `docs/holdout-unlock-log.md`, lặp lại đủ bốn điều kiện. Qua thì mới bàn tới paper forward (spec mục E).

## 6. Báo cáo cho Claude
1. Output pytest/ruff, bảng phá hoại, `detect-changes`.
2. Lệnh chạy IS và **output đầy đủ, nguyên văn**.
3. Một câu xác nhận: "Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`."
4. Mọi chỗ brief mơ hồ mà agent phải tự diễn giải; không im lặng chọn.
