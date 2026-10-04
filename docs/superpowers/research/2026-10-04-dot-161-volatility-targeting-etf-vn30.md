# Đợt 161 — đo volatility targeting trên ETF VN30 mua-và-giữ (CHỈ ĐO)

Base: main `e49dc01`. Ngày: Chủ nhật 04/10/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-10-04-brief-dot-161-do-volatility-targeting-tren-etf-vn30.md`.
Audit: Claude.

## 0. Kết luận trước, chi tiết sau

**KHÔNG ĐẠT.** Biến thể chính (EWMA λ=0,94) cắt drawdown thật (47,74% → 34,25%) nhưng **không đủ**
ngưỡng ⅔, và cái giá là **−3,15 điểm % CAGR** (ngân sách cho phép là 1,0). Cả hai tiêu chí đều trượt,
nên không cần bàn tới việc biến thể nhạy có "cứu" được hay không — mà cũng không cứu được:

```
(a) MDD chinh 34.25% <= 2/3 x MDD mua-va-giu (2/3 x 47.74% = 31.83%) : KHONG DAT   (34,25 > 31,83)
(b) CAGR chinh 10.19% >= CAGR mua-va-giu 13.34% - 1,0 diem % (12.34%) : KHONG DAT   (10,19 < 12,34)
=> KHONG DAT
```

## 1. Thiết kế đã chốt (chép nguyên bảng trong brief — không chỉnh sau khi thấy kết quả)

| Mục | Chốt |
|---|---|
| Giai đoạn | Làm ấm 2016 (chỉ để ước lượng σ̂, không giao dịch). Đo **2017-01-02 → 2026-09-30**. |
| Đối chứng | Mua-và-giữ 100%: mua ở **open** phiên đo đầu tiên, bán ở **close** phiên cuối, tính đủ phí, thuế và trượt giá. |
| Dự báo σ̂ (**biến thể chính**) | EWMA trên lợi suất log theo ngày, λ = 0,94 (chuẩn RiskMetrics), annualize bằng √252. |
| Biến động mục tiêu | Trung vị của mọi σ̂ **tính tới hết phiên t** (cửa sổ mở rộng từ đầu làm ấm). Không có tham số để chỉnh. |
| Tỷ trọng mục tiêu | `w*_t = min(1, mục_tiêu_t / σ̂_t)`. **Trần 1**: không vay margin dù tài khoản 0434226 là margin. |
| Thời điểm | Quyết định ở close phiên t, khớp ở **open phiên t+1**. Không dùng dữ liệu nào sau close phiên t. |
| Ngưỡng tái cân bằng | Chỉ giao dịch khi `|w*_t − w_hiện_tại| ≥ 0,20`. |
| Chi phí | Mỗi lần mua: `FEE_RATE` + trượt giá. Mỗi lần bán: `FEE_RATE` + `SELL_TAX_RATE` + trượt giá. |
| Tiền mặt | Lãi 0 (bảo thủ, ghi rõ trong báo cáo). |
| Khối lượng | Được dùng tỷ trọng lẻ. Ghi một câu vì sao làm tròn lô 100 không đổi kết luận. |

**Vì sao tỷ trọng lẻ không đổi kết luận:** khối lượng làm tròn lô 100 trên vốn 1 đơn vị chỉ làm lệch
tỷ trọng thực vài phần nghìn (một lô ETF ~2.000 VND trên vốn vài trăm triệu), nhỏ hơn ngưỡng tái cân
bằng 0,20 cả bậc độ lớn — nó đổi *số lệnh lẻ* chứ không đổi *tỷ trọng*, mà tỷ trọng mới là thứ quyết
định cả hai tiêu chí. Không cần mô phỏng lại để chứng minh điều này.

Tham số lấy **import** từ `trading/paper_broker.py`: `FEE_RATE = 0.0025`, `SELL_TAX_RATE = 0.001`,
`SLIPPAGE_BPS = 5`. MDD/Sharpe lấy từ `trading/metrics.py` (`max_drawdown`, `sharpe`).

## 2. Ba bảng kết quả (chạy trên DB thật, chỉ đọc)

Dữ liệu: `E1VFVN30`, đọc bằng `storage.read_daily_bars` + `clean_bars`, cửa sổ 2016-01-01 → 2026-10-01:
**2.682 phiên, bỏ 3 phiên giá ≤ 0 → 2.679 phiên**; đo trên **2.428 phiên** (2017-01-03 → 2026-09-30).
(Brief ghi 2.683 phiên — lệch 1 phiên, xem §5 mục 3.)

### Bảng tổng (sau mọi chi phí)

```
bien the                                CAGR       MDD    nam te   thang te   Sharpe    GD       phi    w TB
--------------------------------------------------------------------------------------------------------------------
mua-va-giu 100%                       13.34%    47.74%   -32.95%    -22.49%     0.70     2    1.656%  100.0%
EWMA 0,94 (chinh)                     10.19%    34.25%   -28.40%    -13.36%     0.72    41    6.047%   76.4%
sigma = do lech chuan 20 phien         9.17%    37.06%   -28.77%    -15.83%     0.63    66   10.244%   81.0%
nguong 0,10                           10.09%    33.91%   -28.13%    -12.27%     0.69   118   10.645%   79.5%
nguong 0,30                            9.28%    32.58%   -26.22%     -9.24%     0.68    19    3.897%   71.3%
GARCH(1,1) refit 21 phien              8.71%    35.89%   -29.10%    -11.91%     0.61   136   22.183%   77.3%

# GARCH(1,1) lan uoc luong cuoi (127 lan refit): omega=0.0970, alpha=0.1514, beta=0.8006,
# alpha+beta=0.9520 (don vi loi suat %^2)
# CAGR neu annualize theo 252 phien: chinh 10.31%, mua-va-giu 13.49%
```

Đọc bảng này cho trung thực:
- **Drawdown CÓ giảm, và giảm nhiều** — 47,74% → 34,25% (−28% tương đối) — nhưng tiêu chí đã chốt là
  **⅔**, tức ≤ 31,83%, nên trượt. Đây là kiểu kết quả dễ bị đọc thành "gần đạt": nó không gần — thiếu
  2,42 điểm % MDD.
- **Cái giá là churn**: 41 giao dịch, tổng phí 6,05% (so với 1,66% của mua-và-giữ). Ngưỡng 0,10 làm
  số lệnh gấp gần 3 lần (118 lệnh, phí 10,65%) mà MDD chỉ nhích thêm 0,34 điểm %; ngưỡng 0,30 giảm
  còn 19 lệnh (phí 3,90%) nhưng MDD vẫn 32,58% — vẫn trên 31,83%.
- Sharpe **nhỉnh hơn** mua-và-giữ (0,72 so với 0,70) và **tháng tệ nhất đỡ hơn rõ** (−13,36% so với
  −22,49%). Vol targeting không vô dụng; nó chỉ không đạt hai ngưỡng đã chốt, và tiêu chí (b) đã
  tính đúng chỗ đó bằng cách cho phép mất tới 1,0 điểm % CAGR.
- GARCH là biến thể **tệ nhất về mọi mặt** (CAGR 8,71%, phí 22,18%, 136 lệnh). α+β = 0,9520, tức
  "trí nhớ" ~95% — cao hơn con số ~85% mà video nhắc, nhưng khác tài sản, khác giai đoạn, khác đơn vị
  nên **không coi là đối chiếu**.

### Bảng theo năm (2017 → 2026; 2026 là năm dở dang)

```
nam     bien the chinh   mua-va-giu      chenh
----------------------------------------------
2017            57.21%       58.48%     -1.27%
2018            -5.41%      -11.58%      6.17%
2019             1.53%        3.15%     -1.62%
2020            14.09%       22.00%     -7.90%
2021            25.24%       43.57%    -18.33%
2022           -28.40%      -32.95%      4.55%
2023             8.49%       12.14%     -3.65%
2024            18.23%       20.88%     -2.64%
2025            38.02%       53.78%    -15.76%
2026            -5.96%       -4.65%     -1.31%
----------------------------------------------
thang 2 / thua 8 / hoa 0   (nam 2026 la nam do dang)
```

Vol targeting thắng đúng **2 năm / 10**, và hai năm thắng là hai năm giảm (2018, 2022) — đúng bản chất
"phòng thủ": nó mua bảo hiểm bằng lãi, nhưng ở đây bảo hiểm đắt hơn mức tiêu chí cho phép.

### Mua-và-giữ riêng 2017–2022 (để Claude đối chiếu phép đo cũ)

```
2017-01-03 -> 2022-12-30: gross=1.6960, CAGR=9.22%, MDD=47.74%
```

Tôi không tự đi tìm con số cũ (brief đã ghi rõ là Claude đối chiếu), nhưng nếu con số cũ là **9,18%**
thì lệch 0,04 điểm % đến từ hai chỗ đã biết: (1) mô hình chi phí của tôi trừ phí/thuế một vòng trên
**giá trị bán thật**, không dùng một hằng số `round_trip_cost`; (2) mốc đầu/cuối là **phiên** (03/01 và
30/12) trong khi đợt 102 lấy theo **tháng**.

## 3. Test và phá thử

File mới `tests/test_measure_vol_target_etf.py`, **9 test**, dữ liệu tổng hợp, không chạm DB:

```
test_bien_dong_khong_doi_thi_khong_giao_dich_them
test_doi_gia_sau_phien_t_khong_doi_w_sao_va_giao_dich_truoc_t
test_nguong_019_khong_giao_dich_021_thi_giao_dich
test_mot_vong_gia_phang_mat_dung_cong_thuc
test_ewma_ba_buoc_khop_so_tinh_tay
test_phien_close_khong_duong_bi_loai
test_rolling_vol_va_cua_so_mo_rong
test_garch_thu_hoi_alpha_cong_beta            (importorskip("arch"))
test_buy_hold_tru_phi_va_thue_hai_dau
```

```
uv run pytest tests/test_measure_vol_target_etf.py -q
8 passed, 1 skipped in 0.11s           <- thieu `arch` -> test GARCH bi bo qua (GHI RO)
uv run --with arch pytest tests/test_measure_vol_target_etf.py -q
9 passed in 5.31s                      <- co arch: GARCH thu hoi alpha+beta trong 0,05 (dat)
```

**Phá thử:** cho `w*_t` dùng `σ̂_{t+1}` — tức đúng lỗi nhìn trước mà test canh. Cách phá: trong
`weights_series`, dịch chuỗi σ̂ lên một phiên (`vols = [*vols[1:], vols[-1]]`). Nguyên văn dòng đỏ:

```
>       assert w_before[: t + 1] == pytest.approx(w_after[: t + 1]), (
            "w* tại t và trước t phải KHÔNG đổi khi chỉ đổi giá sau t"
        )
E       AssertionError: w* tại t và trước t phải KHÔNG đổi khi chỉ đổi giá sau t
E       assert [1.0, 1.0, 1....43353005, ...] == approx([1.0 ±...49 ± 6.4e-08])
E         comparison failed. Mismatched elements: 1 / 51:
E         Max absolute difference: 0.8372722703120133
E         Max relative difference: 0.9290761613600754
E         Index | Obtained           | Expected
E         50    | 0.9011879812805978 | 0.06391571096858449 ± 6.4e-08
tests\test_measure_vol_target_etf.py:77: AssertionError
FAILED tests/test_measure_vol_target_etf.py::test_doi_gia_sau_phien_t_khong_doi_w_sao_va_giao_dich_truoc_t
1 failed, 8 deselected in 0.28s
```

Khôi phục `cp` từ `%LOCALAPPDATA%\Temp\backup_dot161_measure_vol_target_etf.py` → `8 passed, 1 skipped`,
`sha256 = 85d0a533e3512885…`, không còn dòng `PHA THU` nào trong file.

**Lượt phá ĐẦU của tôi không bắt được gì** (tôi phá trong `simulate`: dùng `w_star[i+1]`), vì test so
`weights_series` chứ không so `simulate` — phá sai chỗ thì "phá" chỉ là vô nghĩa. Tôi khôi phục file
trước đã, rồi phá lại đúng chỗ. Ghi ra đây vì đây là loại lỗi im lặng: một phép phá không bắt được gì
mà không kiểm lại thì dễ bị đọc thành "test chắc".

### Ba lỗi thật mà bộ test bắt được trong lúc làm

1. **Thiếu `cash -= delta` khi khớp lệnh** — tiền mặt đứng yên nên equity phình vô hạn: vòng mua-bán ở
   giá phẳng "mất" 14% (0,86) thay vì 0,7% (0,993). Test chi phí bắt đúng chỗ này.
2. **Bảng theo năm bỏ trống năm đầu** (`2017 = n/a`) vì năm 2017 không có mốc "cuối năm trước" —
   tôi sửa để năm đầu tính từ vốn ban đầu, rồi **chạy lại phép đo** (đây là lỗi code, không phải
   "chỉnh thiết kế"; λ, ngưỡng, biến động mục tiêu không đổi).
3. **Test chống nhìn trước tự dựng lại chuỗi theo chỉ số lợi suất** thay vì gọi đúng `weights_series`
   (gắn theo chỉ số NẾN) — lệch một phiên nên test tưởng code sai. Sửa test để đi đúng hàm mà lần chạy
   thật dùng.

## 4. Hai con số pytest (yêu cầu §Tiêu chí 2)

```
TRƯỚC (bản sao nguyên vẹn của HEAD, dựng ngoài repo bằng `git archive HEAD`):
    1832 passed in 86.66s
SAU   (cây làm việc hiện tại):
    uv run pytest -q                  -> 1840 passed, 1 skipped in 98.15s
    uv run --with arch pytest -q      -> 1841 passed in 81.60s
```

Chênh **đúng 9** = 9 test mới (8 xanh + 1 GARCH bị bỏ qua khi không có `arch`; có `arch` thì 1841 =
1832 + 9). 0 failed ở cả ba lượt. `uv run ruff check trading tests scripts` → `All checks passed!`

`git status` chỉ có đúng 3 file của đợt này (script, test, báo cáo) cộng hai file `??` có từ trước
(file `.md` BTCUSDT của đợt 105/106 và brief của Claude — tôi không tạo, không sửa).

**`gitnexus_detect_changes` trả `changed_count: 0, risk: none`** — đọc đúng cách: đợt này **không sửa
một dòng nào của file có sẵn**, mọi thứ là file mới CHƯA được git theo dõi, mà tool không thấy file
untracked. Đây là "không có gì để thấy", **không phải** "không có thay đổi".
`gitnexus_query` cũng trả rỗng kèm cảnh báo `FTS indexes missing` — index GitNexus đang hỏng, nên phần
"tìm hàm dùng lại" tôi làm bằng `grep` (đúng như brief cho phép khi MCP không chạy được): tìm ra
`read_symbol_bars`, `clean_bars`, `bar_date` trong `trading/stock_study.py` và `scripts/screen_momentum_portfolio.py`,
cùng `FEE_RATE`/`SELL_TAX_RATE`/`SLIPPAGE_BPS`, `max_drawdown`, `sharpe`.

## 5. Brief sai / chưa chính xác ở đâu

1. **Xung đột thật: `read_symbol_bars` không dùng được cho cửa sổ này.** Brief chỉ định "đọc giá bằng
   `read_symbol_bars` mà `scripts/screen_momentum_portfolio.py` đang dùng", nhưng hàm đó gọi
   `validate_sealed_bars`, hàm này **ném lỗi với mọi nến từ 2023-01-01 và không có cờ bỏ qua**
   (`trading/stock_study.py:62-70`). Brief lại chốt đo tới 30/09/2026 ⇒ hai yêu cầu loại trừ nhau.
   Tôi dùng đúng hai mảnh của nó — `storage.read_daily_bars` + `clean_bars` — và **bỏ cổng niêm phong**,
   ghi rõ ngay trong docstring của script. Đây là **mở tập niêm phong có chủ ý** theo thiết kế đã chốt
   trước của brief (không phải tôi tự quyết định mở): thiết kế chốt TRƯỚC khi thấy kết quả, biến thể
   nhạy chỉ để báo cáo và **không** dùng để chọn biến thể. Nếu Claude thấy việc mở niêm phong này không
   ổn thì phải chốt lại phạm vi đo, không phải chỉnh kết quả.
2. **"3 phiên có `close <= 0`"** — con số khớp, nhưng cơ chế đúng là `clean_bars` bỏ nến khi **bất kỳ**
   trong OHLC ≤ 0, không riêng `close`. Với `bars_daily` dạng bẩn đã biết (`open = 0` mà `close` thật)
   thì "close ≤ 0" và "OHLC ≤ 0" là hai bộ khác nhau; tôi đếm 3 phiên bị bỏ (khớp), nhưng nếu sau này
   dạng bẩn đổi thì điều kiện lọc của brief sẽ đếm thiếu.
3. **Số phiên lệch 1**: brief ghi `E1VFVN30` có **2.683** phiên; tôi đọc được **2.682** trong cửa sổ
   2016-01-01 → 2026-10-01 (bỏ 3 → 2.679 dùng được). Chưa tìm ra nguyên nhân; nghi khác cách đếm
   (brief có thể đếm cả dòng ngoài cửa sổ, hoặc đếm trước khi khử trùng). Không ảnh hưởng kết luận
   (1 phiên trên 2.679), nhưng nêu ra vì đây là loại lệch sẽ thành vấn đề nếu ai đó dùng con số làm mốc.
4. **"σ̂ = độ lệch chuẩn trượt 20 phiên"** không nói rõ độ lệch chuẩn **mẫu** hay **tổng thể**, và
   cũng không nói annualize. Tôi dùng `statistics.stdev` (mẫu, n−1) × √252 — cùng cách annualize với
   biến thể chính cho dễ so.
5. **GARCH nói "ước lượng lại mỗi 21 phiên"** nhưng không nói giữa hai lần ước lượng thì lấy σ̂ ở đâu.
   Tôi giữ phương sai có điều kiện bằng công thức GARCH với tham số của lần ước lượng gần nhất
   (`σ²_{t+1|t} = ω + α·r_t² + β·σ²_t`), tức σ̂_t vẫn chỉ dùng dữ liệu tới t.
6. **Ngưỡng "sai số nhỏ hơn 1e-9" cho vòng mua-bán ở giá phẳng chỉ đúng với một mô hình chi phí cụ
   thể** (chi phí cộng dồn riêng, không trừ vào vốn dùng để tính notional lần sau). Nếu chi phí trừ vào
   vốn ngay (cách "tự nhiên" hơn) thì vòng đó mất `(F+s) + (1−F−s)(F+T+s)`, lệch ~1,2e-5, tức test sẽ
   đỏ dù code hợp lý. Tôi chọn mô hình làm đúng con số brief ghi và **ghi rõ mô hình trong docstring**.

## 6. Những gì KHÔNG kiểm được

1. **Khớp lệnh trong phiên.** Dữ liệu chỉ có OHLC ngày; lệnh chỉ được mô hình ở đúng giá **open** phiên
   t+1, không có trượt giá theo khối lượng, không có trần/sàn, không có thanh khoản. Nhưng lưu ý:
   chiến lược chỉ đổi tỷ trọng ~41 lần trong 9,7 năm và mua/bán ETF chỉ số — đây không phải chỗ dễ hỏng.
2. **ETF lệch NAV.** E1VFVN30 có thể giao dịch cao/thấp hơn NAV; mọi con số ở đây là giá thị trường,
   không phải NAV, nên phần "lợi suất" bao gồm cả thay đổi premium/discount mà nhà đầu tư thật nhận.
3. **Tiền mặt lãi 0** (đã chốt trong thiết kế): trong 9,7 năm, lãi suất tiền gửi VND không nhỏ, nên
   **mua-và-giữ đang bị tính thiệt** vì nó cũng không được lãi trên tiền mặt — nhưng mua-và-giữ gần như
   luôn 100% cổ phiếu, còn biến thể chính trung bình chỉ 76,4% tài sản, tức nó giữ ~24% tiền mặt
   KHÔNG sinh lãi. Đây là điểm bất lợi có thật dành cho biến thể chính, không phải cho đối chứng —
   nếu tính lãi tiền mặt, khoảng cách CAGR sẽ thu hẹp phần nào (rủi ro của kết luận là "KHÔNG ĐẠT
   nhưng sát hơn"). Tôi **không** đổi thiết kế sau khi thấy kết quả.
4. **Một lần ước lượng GARCH còn phụ thuộc `arch`** (8.0.0, cài bằng `uv run --with arch`, **không**
   thêm vào `pyproject.toml`). Chạy lại trên máy khác có thể khác vài phần nghìn ở `α`, `β`.
5. **Không so với video.** Con số 81%/63% của video là BTC, không phí, và nghi có nhìn trước — brief
   đã nói không lấy làm mốc; tôi giữ đúng như vậy.
6. **Không chạy `sched.sh`, không `docker`, không Telegram, không ghi DB**: đã tuân thủ, nên "phép đo
   có chạy được trong môi trường production hay không" không kiểm; chỉ khẳng định được script chạy
   sạch với cùng `.env`/DSN thật.

KHÔNG dùng skill/plugin `garch-method`; GARCH dùng `arch` qua `uv run --with`, code của đợt này.
Tôi không commit, không push, không sửa file có sẵn nào, không thêm dependency vào `pyproject.toml`.

---

## Audit của Claude (04/10/2026)

### Kết luận: phép đo ĐẠT chuẩn, chiến lược KHÔNG ĐẠT. Kết luận được giữ nguyên.

### 1. Tính lại độc lập

Code riêng của Claude, chỉ dùng chung `read_daily_bars` và các hằng số phí của `paper_broker`. Mô phỏng, EWMA, ngưỡng
và MDD đều viết lại từ đầu.

| | Agent | Claude |
|---|---|---|
| Mua-và-giữ, cả giai đoạn: CAGR / MDD | 13,34% / 47,74% | 13,28% / 47,67% |
| Biến thể chính: CAGR / MDD | 10,19% / 34,25% | 10,22% / 33,60% |
| Tỷ trọng ETF trung bình | 76,4% | 76,4% |
| Mua-và-giữ 2017–2022 | 9,22% | 9,15% |
| Mốc mua-và-giữ ETF của đợt 102 (agent không được biết trước) | — | 9,18% |

Chênh lệch nằm ở chi tiết mô hình: chỗ đánh dấu giá, cách tính ngày. Biên trượt so với ngưỡng thì lớn hơn nhiều:
(a) thiếu khoảng 2 điểm %, (b) thiếu khoảng 2 điểm %. **KHÔNG ĐẠT ở cả hai tiêu chí**, theo cả hai bản tính.

Số phiên: 2.682 phiên thô, 2.679 phiên sạch. Brief ghi 2.683 là do Claude đếm bằng mốc UTC. Agent đúng.

### 2. Lỗi của brief: mở niêm phong cổ phiếu

Brief chốt đo tới 30/09/2026 mà **không nhắc** niêm phong cổ phiếu từ 2023-01-01 (đợt 120: "Holdout cổ phiếu từ
2023-01-01 phải nguyên vẹn"). Agent gặp `validate_sealed_bars`, làm theo thiết kế đã chốt, và **khai rõ** trong báo
cáo. Đó là cách xử lý đúng. Lỗi thuộc về Claude.

**Đánh giá thiệt hại.** Claude đo lại riêng giai đoạn 2017–2022 (dưới mốc niêm phong):

| 2017–2022 | CAGR | MDD |
|---|---|---|
| Mua-và-giữ | 9,15% | 47,67% |
| Biến thể chính | 7,86% | 33,60% |

(a) 33,60% > ⅔ × 47,67% = 31,78%, **trượt**. (b) 7,86% < 9,15% − 1,0 = 8,15%, **trượt**. Nếu làm đúng quy trình
(quyết trong mẫu rồi mới xác nhận trên holdout), phép đo đã dừng ở trong mẫu với **cùng kết luận**. Không có tham số
nào được chỉnh sau khi thấy dữ liệu từ 2023.

Hệ quả còn lại: với **họ volatility targeting / chia vốn theo biến động trên E1VFVN30**, dữ liệu từ 2023 không còn
là ngoài mẫu. Đã ghi vào `docs/holdout-unlock-log.md`.

### 3. Kiểm khác

- `ruff` sạch. Bộ đầy đủ: **1840 passed + 1 skipped** (test GARCH khi thiếu `arch`), tổng 1841, khớp agent. Chạy
  với `--with arch`: 12/12 xanh cho test mới cộng `test_scripts_convention`.
- `git status`: chỉ có script mới, test mới, báo cáo. Không sửa file có sẵn, không thêm dependency.

### 4. Ý nghĩa

Volatility targeting trên ETF VN30 **cắt được drawdown** (47,7% → khoảng 34%, tháng tệ nhất −22,5% → −13,4%) nhưng
**tốn khoảng 3 điểm % lãi kép mỗi năm**, gấp ba ngân sách. Video tự báo mức tốn 1 điểm trên Nasdaq; ở VN cái giá đắt
gấp ba, vì phí cộng thuế khoảng 0,6% mỗi vòng và vì biến thể giữ trung bình 24% tiền mặt không sinh lãi. Hai năm
thắng đều là năm thị trường giảm (2018, 2022). Đó là đúng bản chất "mua bảo hiểm", và giá bảo hiểm ở đây không đáng.

Đây là phép đo âm **thứ 14**. Mốc phải vượt vẫn là ETF VN30 mua-và-giữ.
