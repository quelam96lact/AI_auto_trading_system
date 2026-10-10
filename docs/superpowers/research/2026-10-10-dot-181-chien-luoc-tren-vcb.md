# Đợt 181 — Kiểm bốn luật đã có trên riêng mã VCB, so với mua-và-giữ VCB

Base: main `25fa60d`. Ngày: 10/10/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-10-10-brief-dot-181-kiem-chien-luoc-tren-vcb.md`.
Khung: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md` — **giả thuyết thứ 8 của tháng 10** (mục H, vượt ngân sách mục F).

## 0. Kết luận

**KHÔNG luật nào trong bốn luật thắng việc giữ VCB 2017–2022.**

| # | Luật | n | TB ròng/lệnh | PF | Lợi suất gộp | So B&H VCB +203,19% | Cổng §1.3 |
|---|---|---|---|---|---|---|---|
| 1 | `octopus_pullback` (engine đang chạy) | 6 fill SELL ✗ | — | — | PnL **+37.326.082** | B&H cùng run **2.393.839.233** ✗ | **TRƯỢT** (n, PnL ≤ B&H) |
| 2 | Pullback trong xu hướng | 32 | **−1,1619%** | 0,6129 | **−35,28%** | ✗ | **TRƯỢT** (4/5 điều kiện) |
| 3 | Phá đỉnh Donchian 55/20 | 17 ✗ | +2,4558% ✓ | 1,7079 ✓ | **+32,18%** | ✗ | **TRƯỢT** (n, gộp ≤ B&H, p) |
| 4 | RSI(2) quá bán trên MA200 | 50 | **−0,4249%** | 0,6722 | **−21,58%** | ✗ | **TRƯỢT** (4/5 điều kiện) |

Mốc mua-và-giữ VCB 2017-01-03 → 2022-12-30: **gộp +203,19%**, CAGR **+20,35%**, drawdown lớn nhất **39,47%**.

## 1. Đối chiếu dự đoán §1.4 của Claude

Claude ghi trước: *"Không luật nào đạt. Cả bốn thua mua-và-giữ VCB ở điều kiện 4 (luật 1: PnL ≤ B&H)."*

**Đo đúng cả hai vế:** không luật nào đạt, **và đúng cơ chế** — cả bốn đều trượt điều kiện so với mua-và-giữ:

- Luật 1: PnL 37.326.082 so với B&H 2.393.839.233 ⇒ **kém 64,1 lần**.
- Luật 2: −35,28% so với +203,19%.
- Luật 3: +32,18% so với +203,19% — luật duy nhất có TB/lệnh > 0 **và** PF > 1,2, nhưng **n = 17 < 20** và gộp chỉ bằng ~1/6 mốc giữ.
- Luật 4: −21,58% so với +203,19%.

Không có vế nào của dự đoán bị sai. Điều đáng ghi thêm: **ba trên bốn luật còn lỗ tuyệt đối** (−35,28%, −21,58%, và luật 1 dương nhưng nhỏ) trong một cửa sổ mà mã đó tăng +203% — tức vấn đề không phải "kém B&H" mà là **luật cắt mất xu hướng tăng dài của chính mã đó**.

## 2. Output chạy thật — nguyên văn

```
$ set -a && . ./.env && set +a && export DB_DSN="${DB_DSN/localhost/127.0.0.1}"
$ uv run python scripts/measure_vcb_strategies.py        # EXIT=0
```

```
# VCB | san HOSE | 1749 nen 2016-01-04 -> 2022-12-30
# Bo 1 nen gia <= 0. Cong niem phong: nen >= 2023-01-01 thi nem loi.
# Luat 2-4: IS theo NGAY TIN HIEU (mac dinh tung script). Luat 1: run_backtest toan bo.
# Cong: n >= 20 | TB/lanh > 0 | PF > 1.2 | gop > B&H | p < 0.0125 (Bonferroni 0,05/4)
# Bootstrap 2000 lan, seed 42. Chi doc, khong ghi DB.

Moc mua-va-giu VCB 2017-01-03 -> 2022-12-30: gop +203.19% | CAGR +20.35% | drawdown lon nhat 39.47%

=== Luat 2-4 | Pullback trong xu huong ===
  n 32 | thang 31.2% | TB/lanh -1.1619% | PF 0.6129
  gop -35.28% | drawdown lon nhat 48.54% | ty le phien co vi the 22.3%
  p mot phia (bootstrap 2000) = 0.8550
    DAT  n_ge_20
    TRUOT  mean_positive
    TRUOT  pf_gt_1_2
    TRUOT  gross_gt_bh
    TRUOT  p_lt_00125
  => KHONG DAT

=== Luat 2-4 | Pha dinh Donchian 55/20 ===
  n 17 | thang 41.2% | TB/lanh +2.4558% | PF 1.7079
  gop +32.18% | drawdown lon nhat 36.98% | ty le phien co vi the 36.5%
  p mot phia (bootstrap 2000) = 0.2275
    TRUOT  n_ge_20
    DAT  mean_positive
    DAT  pf_gt_1_2
    TRUOT  gross_gt_bh
    TRUOT  p_lt_00125
  => KHONG DAT

=== Luat 2-4 | RSI(2) qua ban tren MA200 ===
  n 50 | thang 42.0% | TB/lanh -0.4249% | PF 0.6722
  gop -21.58% | drawdown lon nhat 27.00% | ty le phien co vi the 14.8%
  p mot phia (bootstrap 2000) = 0.8060
    DAT  n_ge_20
    TRUOT  mean_positive
    TRUOT  pf_gt_1_2
    TRUOT  gross_gt_bh
    TRUOT  p_lt_00125
  => KHONG DAT

=== Luat 1 | octopus_pullback (engine dang chay) ===
  so fill SELL 6 | win rate 83.3%
  PnL chien luoc 37,326,082 (realized 37,326,082 + unrealized 0)
  buy_and_hold_pnl 2,393,839,233 | max_drawdown 0.98%
    TRUOT  n_ge_20
    DAT  pnl_positive
    TRUOT  pnl_gt_bh
  => KHONG DAT

### Ket luan
  KHONG luat nao trong bon luat thang viec giu VCB 2017-2022.

### Canh bao bat buoc (brief §0)
  (1) Chon ma SAU KHI luat da truot tren toan thi truong la kieu cau ca kinh dien: voi ~1.200 ma,
      chac chan co vai ma ma luat 'thang' do may. VCB duoc chon vi chu du an hoi, KHONG phai vi du lieu.
  (2) Mau nho: mot ma trong 6 nam chi vai chuc lenh; cong >= 300 lenh cua spec KHONG the dat.
      Dot nay KHONG the dua luat nao toi von that. Ket qua tot nhat co the la 'dang do tiep tren
      nhom ngan hang', va do se la mot brief khac.
  (3) Chu du an dang gi 1.500 VCB ngoai he thong (dot 150). Phep do nay KHONG khuyen nghi gi ve so
      co phieu do.
```

## 3. Test, bốn phép phá, cổng kiểm

`tests/test_measure_vcb_strategies.py` — 8 ca theo §3, dữ liệu dựng tay, không chạm DB. Ca 1 kiểm
**cả ba luật** trả về đúng bằng lệnh khi gọi trực tiếp `simulate_symbol` của script gốc, và mỗi luật
phải sinh **ít nhất 1 lệnh** (nếu không thì phép so là vô nghĩa): cả ba điều này đều đúng ngay lượt
đầu, nên phép so không rỗng.

```
$ uv run pytest tests/test_measure_vcb_strategies.py -q          -> 8 passed in 0.48s
$ uv run pytest tests/test_measure_vcb_strategies.py tests/test_scripts_convention.py -q
                                                                 -> 11 passed
$ uv run python scripts/measure_vcb_strategies.py --help         -> chạy từ gốc repo OK
$ uv run ruff check trading tests scripts                        -> All checks passed!
```

| Phép phá | Test phải đỏ | Kết quả |
|---|---|---|
| (i) ngưỡng p đổi thành 0,05 (bỏ Bonferroni) | `test_cong_bien_moi_ca_truot_dung_mot_dieu_kien` | **đỏ** đúng test này (ca p = 0,03 lật thành ĐẠT) |
| (ii) `PF > 1,2` đổi thành `PF >= 1,2` | `test_cong_bien_moi_ca_truot_dung_mot_dieu_kien` | **đỏ** đúng test này (ca PF = 1,2 đúng bằng lật) |
| (iii) mốc mua-và-giữ dùng `close` phiên đầu thay vì `open` | `test_moc_mua_va_giu_dung_open_2017_va_close_2022` | **1 đỏ**, đúng test này |
| (iv) bỏ `validate_sealed_bars` (đọc thẳng `storage.read_daily_bars`) | `test_niem_phong_nen_2023_thi_nem_loi` | **1 đỏ**, đúng test này |

Khôi phục `cp` từ `%LOCALAPPDATA%\Temp\backup_dot181_measure_vcb_strategies.py` → `8 passed`, nội dung
file khớp nguyên bản từng byte, `sha256 = d35ea3cfaef1f577…`.

Số test toàn cục: **TRƯỚC 1858 passed / 154 deselected** (đo bằng lượt chạy nền khởi động *trước* khi
tạo hai file mới) → **SAU 1866 passed / 154 deselected** ⇒ chênh **đúng 8** = 8 test mới, 0 đỏ cả hai lượt.

`node .gitnexus/run.cjs detect-changes --scope all --repo .` → **"No changes detected."** Đọc đúng cách:
đợt này **không sửa một dòng nào của file có sẵn**; cả ba file đều MỚI và chưa được git theo dõi, mà
`detect-changes` chỉ nhìn phần đã theo dõi. "Không có gì để thấy", **không phải** "không có thay đổi".
(Không dùng `npx` — dùng `node .gitnexus/run.cjs` theo brief §4.)

## 4. GitNexus `impact` trước khi viết (chỉ import, KHÔNG sửa)

| Target | Kết quả |
|---|---|
| `Function:scripts/screen_pullback_trend.py:simulate_symbol` | **LOW** — impactedCount 5, direct 1 |
| `Function:scripts/screen_donchian_breakout.py:simulate_symbol` | **not found** ⇒ `risk: UNKNOWN` |
| `Function:scripts/screen_rsi2_reversion.py:simulate_symbol` | **not found** ⇒ `risk: UNKNOWN` |
| `run_backtest` | **CRITICAL** — impactedCount 132, direct 108 |

Hai "not found" là do chỉ số GitNexus chưa cập nhật hai script sinh ở đợt 175/177. Theo AGENTS.md,
`UNKNOWN` **không** phải an toàn — nên tôi tự xác nhận bằng cách khác: đọc thẳng chữ ký hàm trong hai
file đó (`screen_donchian_breakout.py:156`, `screen_rsi2_reversion.py:275`) và gọi đúng theo chữ ký
(`(bars, exchange, symbol)` và `(bars, symbol, exchange)` — **khác thứ tự**, đã có test ca 1 ghim).

`run_backtest` ở mức **CRITICAL** là ngưỡng cảnh báo của brief §2 ⇒ tôi **chỉ import**, không sửa
`trading/backtest.py` hay bất kỳ file nào khác. `git status` cuối cùng chỉ có ba file mới của đợt này.

## 5. Hai khác biệt với con số của Claude trong brief (đã đo, không đoán)

**(1) Số nến và nến giá ≤ 0.** Brief §1.1 ghi: *"VCB có 2.687 nến từ 2016-01-04, không nến giá ≤ 0"*.
Đo được: **1.749 nến** trong cửa sổ 2016-01-01 → 2022-12-30, và `read_bars` **bỏ 1 nến** giá ≤ 0.

Truy vấn trực tiếp `bars_daily` (2016–2022, chỉ đọc):

```
2018-01-24 00:00:00+07 | open 0 | high 0 | low 0 | close 26525.772 | volume 0
```

**Đúng 1 nến** VCB vi phạm, dạng `open=high=low=0` nhưng `close` thật — y hệt dạng 71.439 dòng bẩn đã
ghi nhận ở `bars_daily`. Vậy câu "không nến giá ≤ 0" **đúng nếu kiểm cột `close`** và **sai nếu kiểm
OHLC** — chính cái bẫy "`close ≤ 0` ≠ `OHLC ≤ 0`" đã ghi nhận trong dự án. Phần 2.687 so với 1.749:
hiệu 938 nến là phần **≥ 2023** — tôi **không đọc, không đếm** phần đó, nên 2.687 là số của brief,
không phải số tôi kiểm được.

**(2) Luật 1.** Brief §0 dẫn đợt 18: *8 lệnh, lãi 44,9 triệu*. Đo trên đúng cửa sổ brief chốt
(2016-01-01 → 2022-12-31, vốn 1 tỷ, `RiskManager` + `TrailingStopManager` như `measure_one`):
**6 fill SELL, PnL +37.326.082**. Lệch 2 lệnh và ~7,6 triệu. Tôi **không** điều tra thêm (§1.5 cấm thêm
việc ngoài thiết kế) — nêu ra để Claude đối chiếu; khả năng là khác cửa sổ hoặc khác vốn, **chưa kiểm**.

## 6. Brief mơ hồ ở đâu (những chỗ tôi phải tự diễn giải)

1. **§1.2 "tỷ lệ phiên có vị thế … so với số phiên trong cửa sổ"** — cửa sổ của *luật nào*? Ba luật có
   `IS_END` khác nhau (Donchian 31/10/2022; pullback và RSI2 30/11/2022). Tôi dùng **cửa sổ IS của
   chính luật đó** làm mẫu số.
2. **§1.1 "đọc bằng `read_bars(storage, "VCB")`"** — chữ ký hàm cần `from`/`to`; tôi để mặc định của
   chính script (2016-01-01 → 01/01/2023, hàm dùng `ts < end`).
3. **§1.3 luật 1 "PnL > `buy_and_hold_pnl`"** — `buy_and_hold_pnl` do `run_backtest` tính trên **toàn
   bộ nến truyền vào** (2016–2022), tức mốc khác mốc B&H 2017–2022 của luật 2–4. Tôi giữ đúng brief
   (không tính lại) và ghi rõ: **hai mốc B&H này không so trực tiếp được với nhau**.
4. **§1.2 p-value**: tôi hiện thực đúng công thức brief. Với n nhỏ, p bootstrap rất "đắt": Donchian có
   PF 1,71 nhưng p = 0,2275 — xa ngưỡng 0,0125. Nghĩa là **luật duy nhất có dấu hiệu tốt vẫn không có
   bằng chứng**, và điều đó không phải lỗi của phép đo.
5. **Bonferroni chia 4 nhưng chỉ 3 luật dùng p** (luật 1 không bootstrap) ⇒ ngưỡng chặt hơn mức cần.
   Tôi giữ nguyên như brief đã chốt, **không nới**.
6. **§3 ca 5 "mỗi ca chỉ trượt đúng một điều kiện"** — tôi làm cả ca `p = 0,03` (brief gợi ý "nếu cần")
   vì đó chính là ca làm phép phá (i) đỏ được.

## 7. Không kiểm được / hạn chế

1. **Mẫu nhỏ**: 17–50 lệnh một mã trong 6 năm ⇒ cổng ≥ 300 lệnh của spec **không thể** đạt. Đợt này
   không thể đưa luật nào tới vốn thật; kết quả tốt nhất có thể là "đáng đo tiếp trên nhóm ngân hàng".
2. **Câu cá do chọn mã**: VCB được chọn vì chủ dự án hỏi, sau khi cả bốn luật đã trượt trên toàn thị
   trường. Với ~1.200 mã, chắc chắn có vài mã "thắng" do may — nên ngay cả nếu có luật đạt ở đây thì
   cũng **không** phải bằng chứng.
3. **Chỉ có OHLC ngày**: không mô phỏng thanh khoản theo lệnh, không trần/sàn trong phiên.
4. **2023+ không còn sạch cho hai luật**: luật 3 đã nhìn 2023+ ở holdout đợt 175, luật 1 đã nhìn ở
   đợt 18 (brief §1.3).
5. **Mốc so sánh rất cao**: giữ VCB 2017–2022 cho +203,19% (CAGR 20,35%). Với một mã tăng như vậy,
   "thắng mua-và-giữ" gần như bất khả với luật ra vào từng phiên — kết luận "không luật nào thắng"
   không có nghĩa bốn luật vô dụng, mà có nghĩa **chúng không dùng được trên mã này**.
6. Không đọc nến VCB nào từ 01/01/2023; không ghi `docs/holdout-unlock-log.md`; không sửa file nào
   ngoài hai file mới; không commit/push; không ghi DB; không gọi API đặt lệnh; không chạy `sched.sh`.

## 8. Ba cảnh báo bắt buộc (brief §0) — chép lại, không bỏ

1. Chọn mã sau khi luật đã trượt trên toàn thị trường là kiểu câu cá kinh điển; VCB được chọn vì chủ
   dự án hỏi, **không** phải vì dữ liệu.
2. Mẫu nhỏ: một mã trong 6 năm chỉ vài chục lệnh; cổng ≥ 300 lệnh không thể đạt; đợt này **không thể**
   đưa luật nào tới vốn thật; kết quả tốt nhất có thể là "đáng đo tiếp trên nhóm ngân hàng", và đó sẽ
   là một brief khác.
3. Chủ dự án đang giữ 1.500 VCB ngoài hệ thống (đợt 150). Phép đo này **không** khuyến nghị gì về số
   cổ phiếu đó.

## 9. Câu chốt

Tôi không đọc nến VCB nào từ 01/01/2023. Phép đo này không đưa luật nào tới vốn thật và không khuyến
nghị gì về số VCB chủ dự án đang giữ.

## 10. Claude audit (10/10/2026)

- **Kiểm chạy lại:** 11 test (8 mới + quy ước) xanh, ruff sạch.
- **Tính lại độc lập:** Claude gọi thẳng ba hàm `simulate_symbol` gốc và `run_backtest` trên nến VCB đọc qua `read_bars`, không đi qua script của agent. **Khớp từng chữ số:**
  - mua-và-giữ +203,19%;
  - pullback 32 lệnh / −1,1619% / PF 0,6129 / −35,28%;
  - Donchian 17 / +2,4558% / 1,7079 / +32,18%;
  - RSI2 50 / −0,4249% / 0,6722 / −21,58%;
  - octopus 6 fill / +37.326.082 so với mua-và-giữ 2.393.839.233.
- **Hai khác biệt agent nêu:**
  1. "Không nến giá ≤ 0" trong brief là **sai của Claude**: lúc kiểm, Claude chỉ xem cột `close`. Agent đúng: có 1 nến OHLC = 0 ngày 2018-01-24, và `read_bars` đã loại nến này.
  2. Octopus 8 lệnh / 44,9 triệu của đợt 18 đo trên 2016-01-04 → 2026-08-13. Đợt này dừng ở 2022, nên 6 fill / 37,3 triệu là đúng, không phải lệch.
- **Kết luận giữ nguyên:** không luật nào thắng việc giữ VCB 2017–2022. Đây là phép đo âm thứ 20.

