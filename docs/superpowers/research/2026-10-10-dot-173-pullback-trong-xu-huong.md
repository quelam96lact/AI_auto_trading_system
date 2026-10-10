# Đợt 173 — Pullback trong xu hướng, giữ 2–4 tuần, cổ phiếu VN nến ngày

Base: main `8be8f74`. Ngày: 10/10/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-10-10-brief-dot-173-pullback-trong-xu-huong-giu-2-4-tuan.md`.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.

## 0. Kết luận

**KHÔNG ĐẠT.** Cả ba điều kiện có thể trượt đều trượt; chỉ điều kiện số lượng lệnh là đạt.

```
### §1.6 Bon dieu kien
  (1) >= 300 lenh           : 9239            -> DAT
  (2) p < 0,05 & TB > 0     : p = 0.9960, TB vuot troi/thang = -0.5110% (KTC95 [-0.7511%; -0.1468%]) -> KHONG DAT
  (3) TB rong >= 0,5*cost_rt: TB rong = -0.0446%, 0,5*cost_rt = 0.3800% (cost_rt = 0.7600%) -> KHONG DAT
  (4) profit factor rong>1,2: PF = 0.9869 -> KHONG DAT
  => KHONG DAT
```

Phép đo âm thứ 17. **Không mở niêm phong** (theo §5 của brief).

Theo §5: "Pullback trong xu hướng (giữ ≤ 20 phiên, cắt lỗ 8%): KHÔNG có lợi thế trên IS 2017–2022".

## 1. So với kỳ vọng trước của Claude — khớp, và vì sao

Claude kỳ vọng **âm**, với hai lý do: octopus (cũng là pullback trong xu hướng) vừa âm ở đợt 171, và
momentum 12−1 tháng thua có ý nghĩa ở đợt 102. Kết quả **khớp kỳ vọng**, nhưng cơ chế đáng ghi lại vì
nó khác chỗ người ta hay đoán:

- Luật chơi **có** hoạt động đúng như thiết kế: 67,6% lệnh thoát vì **chốt lời** (về lại đỉnh 20 phiên),
  trung vị giữ **3 phiên**. Đây không phải chiến lược "không bao giờ chạy".
- Nhưng **lợi nhuận ròng trung bình mỗi lệnh = −0,0446%** trong khi một vòng phí+thuế+trượt giá là
  **0,76%**. Tức là chuyển động giá trung bình của lệnh **không đủ trả chi phí**, chứ không phải
  "tín hiệu sai hướng" hay "thua vì vài lệnh lớn".
- **Vượt trội so với thị trường là âm và rất chắc**: −0,5110%/tháng, KTC95 [−0,7511%; −0,1468%],
  p = 0,9960. Khoảng tin cậy **không chứa 0** — nghĩa là "không có lợi thế" ở đây là kết luận có bằng
  chứng, không phải "thiếu dữ liệu để kết luận" (9239 lệnh, 72 tháng).
- Ngay cả **trước phí**, gộp theo năm cũng cho thấy tính chu kỳ là ảo giác: 2017 +0,291%, 2018 −1,559%,
  2019 −0,549%, 2020 +0,991%, 2021 +0,535%, 2022 −1,949%.

## 2. Lệnh chạy IS và output đầy đủ, nguyên văn

```
$ set -a && . ./.env && set +a && export DB_DSN="${DB_DSN/localhost/127.0.0.1}"
$ uv run python scripts/screen_pullback_trend.py        # EXIT=0, 37,9s
```

```
# Universe: 1554 ma trong bars_daily, 1308 sau exclusions.txt, 1284 la ma co phieu (bo 24 khong phai co phieu, 246 ma trong exclusions)
# CANH BAO thien lech song sot: KHONG co ma da huy niem yet trong bars_daily. Moi so sanh chi trong CUNG universe nay, khong so voi ETF.
# Niem phong: doc toi 2023-01-01, nem loi voi nen >= 2023-01-01. IS = tin hieu 2017-01-01 -> 2022-11-30.
# Doc 1284 ma, bo 10441 nen gia <= 0, 1208 ma co du lieu dung duoc
# So lenh IS: 9239 | so thang co lenh: 72

### §1.6 Bon dieu kien
  (1) >= 300 lenh           : 9239            -> DAT
  (2) p < 0,05 & TB > 0     : p = 0.9960, TB vuot troi/thang = -0.5110% (KTC95 [-0.7511%; -0.1468%]) -> KHONG DAT
  (3) TB rong >= 0,5*cost_rt: TB rong = -0.0446%, 0,5*cost_rt = 0.3800% (cost_rt = 0.7600%) -> KHONG DAT
  (4) profit factor rong>1,2: PF = 0.9869 -> KHONG DAT
  => KHONG DAT

### §1.7 Mo ta
  So ngay giu: min 2 | trung vi 3 | max 26 | TB 6.50
  Thoat vi STOP:  2069 (22.4%)
  Thoat vi TP  :  6247 (67.6%)
  Thoat vi TIME:   923 (10.0%)
  Vi the mo dong thoi (theo ngay): min 1 | trung vi 30 | max 208 (tb 44.54)
  Theo nam vao lenh (n, TB rong, tong rong):
    2017:  904 lenh, TB +0.291%, tong +263.30%
    2018:  655 lenh, TB -1.559%, tong -1021.09%
    2019:  679 lenh, TB -0.549%, tong -372.81%
    2020: 1162 lenh, TB +0.991%, tong +1151.32%
    2021: 4407 lenh, TB +0.535%, tong +2359.01%
    2022: 1432 lenh, TB -1.949%, tong -2791.53%
  Tin hieu bi bo vi vao lenh: {'ceiling': 80, 'zero_volume': 24}
  TB do sau dieu chinh: 9.05%
# Xong sau 37.9s
```

Số mã: **1.284** mã cổ phiếu trong universe (1.208 mã có dữ liệu dùng được), **9.239 lệnh** trên 72 tháng.

**Cảnh báo đa so sánh:** đây là giả thuyết thứ **5 của tháng 10** và vượt ngân sách mục F (chủ dự án cho
phép ngày 10/10, spec mục H). Phép đo này **không** dùng `holm_adjust` vì chỉ có một giả thuyết chính;
nhưng khi đặt cạnh chuỗi 17 phép đo âm của dự án thì p = 0,9960 không cần hiệu chỉnh gì để kết luận âm —
vấn đề của nó là âm, không phải "gần ngưỡng".

**Cảnh báo thiên lệch sống sót:** `bars_daily` **không có mã đã hủy niêm yết** (chủ dự án quyết định
10/10). Mọi con số ở trên vì vậy bị **lạc quan giả tạo** — nhưng theo hướng có lợi cho chiến lược, tức
kết luận KHÔNG ĐẠT là kết luận *bền* trước thiên lệch này: bỏ đi phần đuôi xấu của vũ trụ mà vẫn âm thì
thêm nó vào chỉ âm hơn. Script in cảnh báo này ngay đầu output.

## 3. TDD: 10 test, và bảng phá hoại

`tests/test_screen_pullback_trend.py` — dữ liệu dựng tay, không đọc DB. Chín ca theo §3 của brief
(ca 9 "đối chứng dương/âm" tách thành hai test, nên tổng là **10**):

```
$ uv run pytest tests/test_screen_pullback_trend.py -q
10 passed in 0.77s
$ uv run pytest tests/test_screen_pullback_trend.py tests/test_scripts_convention.py -v
13 passed
$ python scripts/screen_pullback_trend.py --help      # chay tu thu muc goc repo: OK
```

| Phép phá | Test phải đỏ | Kết quả |
|---|---|---|
| (i) dùng `close[t+1]` trong điều kiện bật lên | `test_sua_nen_sau_t_khong_doi_tin_hieu_tai_t` | **7 đỏ**, gồm đúng test này (đỏ cả dây vì tín hiệu đổi ở nhiều chuỗi) |
| (ii) bỏ ràng buộc T+2 | `test_cat_lo_ngay_phien_vao_khong_thoat_som_hon_E_cong_2` | **1 đỏ**, đúng test này |
| (iii) cho phép nhiều vị thế cùng mã | `test_tin_hieu_thu_hai_trong_luc_dang_giu_bi_bo` | **2 đỏ**, gồm đúng test này |
| (iv) thoát ở close phiên chạm thay vì phiên sau | `test_ba_ly_do_thoat_dung_ly_do_va_dung_phien` | **2 đỏ**, gồm đúng test này |

Sau khôi phục `cp` từ `%LOCALAPPDATA%\Temp\backup_dot173_screen_pullback_trend.py`:
`10 passed`, nội dung file **khớp nguyên bản từng byte**, `sha256 = fbce77c0a72e7ed2…`.

### Bốn lỗi trong chính bộ test của tôi, bị chính lượt chạy bắt

1. **Phép thử "sửa nến sau t" vô nghĩa**: tôi đặt t = nến CUỐI nên vòng lặp sửa nến sau t **rỗng** ⇒
   test xanh mà không kiểm gì. Sửa: thêm 30 nến sau tín hiệu và lấy t = nến có tín hiệu.
2. **Dữ liệu dựng tay không đủ thanh khoản**: close ~120 × 2.000.000 cp = 240 triệu < 2 tỷ ⇒
   `liquidity_ok` chặn sạch, mọi test tín hiệu đỏ. Sửa khối lượng lên 20.000.000.
3. **`opens=` truyền lệch một phiên** (`open[i] = close[i]` thay vì `close[i-1]`) làm giá vào lệnh sai
   ⇒ cú cắt lỗ không bao giờ chạm ⇒ phép phá (ii) "không bắt được gì". Sửa: dùng quy ước mặc định.
4. **Đối chứng dương không có lệnh thua** ⇒ `profit_factor` trả `None` (chia cho 0) ⇒ điều kiện (4)
   không thể đạt. Sửa: cứ 4 chu kỳ có 1 chu kỳ thua, và nến thoát của chu kỳ thua phải nằm **dưới** giá vốn.

(4) là bài học đáng nhớ: một phép phá "không bắt được gì" gần như luôn nghĩa là phép phá đặt sai chỗ
hoặc test đang cười vào chỗ khác — không phải "code đã chắc".

## 4. Số test toàn cục và ruff

```
uv run pytest -m "not integration" -q
  TRƯỚC (bản sao nguyên vẹn HEAD, dựng ngoài repo bằng `git archive HEAD`): 1804 passed, 154 deselected
  SAU   (cây làm việc hiện tại)                                          : 1814 passed, 154 deselected
uv run ruff check trading tests scripts  -> All checks passed!
```

Chênh **đúng 10** = 10 test mới. Không có test nào đỏ ở cả hai lượt.

`gitnexus detect_changes`: **không chạy được** —
`Error: LadybugDB unavailable for ai_auto_trading_system ... Database file version: 42, Current build
storage version: 40`. `gitnexus analyze` (brief §2 yêu cầu chạy trước) thì **chạy xong**: 81,3s,
14.965 node / 27.001 cạnh. Còn `gitnexus context` cho các hàm dùng lại cũng trả cùng lỗi phiên bản, nên
tôi thay bằng `grep` callsite như brief cho phép:

```
scripts/screen_momentum_portfolio.py:178  liquidity_ok(bars, i_f + 1, window=..., min_turnover=...)
scripts/measure_sepa_score_edge.py:469    entry_status(bars, t, ex) != "ok"
scripts/measure_sepa_score_edge.py:484    net_return(entry_open, bars[t + k].close)
```

**Cảnh báo về `git status`:** chỉ có HAI file mới của tôi (`scripts/screen_pullback_trend.py`,
`tests/test_screen_pullback_trend.py`) cộng báo cáo này. Nhưng `npx gitnexus analyze` (brief bắt buộc
chạy) **đã sửa `AGENTS.md`/`CLAUDE.md` và tạo `.claude/skills/*`**. Tôi đã khôi phục: `AGENTS.md` sạch,
các `SKILL.md` khôi phục từ HEAD, và `CLAUDE.md` ghi lại **đúng nội dung HEAD** (kiểm bằng hash:
`git show HEAD:CLAUDE.md` và bản trên đĩa đều `e0ae7ef072c02601`, 161 dòng, `git diff` **rỗng**) —
`git status` vẫn in ` M CLAUDE.md` vì git cấu hình worktree CRLF còn file đang ở LF. Đây là **nhiễu
EOL, không phải thay đổi nội dung**, nhưng tôi nêu ra chứ không im.

## 5. Brief mơ hồ ở đâu (mọi chỗ tôi phải tự diễn giải, không im lặng chọn)

1. **Cửa sổ thanh khoản lệch một phiên.** §1.2 điều kiện 1 ghi "20 phiên **kết thúc tại t**", nhưng
   `liquidity_ok(bars, t, ...)` (brief chỉ định dùng) tính 20 phiên **TRƯỚC t** (`t-20..t-1`). Brief chốt
   dùng `liquidity_ok` nên tôi dùng nguyên hàm đó, **không** kéo cửa sổ dịch đi một phiên.
2. **Thoát "hết giờ" tốn 21 phiên chứ không 20.** §1.4 ghi thoát ở **CLOSE phiên d+1** cho cả ba lý do,
   kể cả hết giờ (d = E+19) ⇒ lệnh thực sự đóng ở close **E+20**, tức 20 phiên *sau* phiên vào lệnh.
   Tôi theo câu chữ §1.4. Đo thật còn thấy `max = 26 phiên`: nến thoát rơi vào nến `volume == 0` thì
   luật "lùi tới phiên kế tiếp có giao dịch" đẩy thêm.
3. **"Nến không có giao dịch"** — dữ liệu ngày không có khái niệm nghỉ giữa phiên, tôi nhận diện bằng
   `volume == 0`.
4. **Ngày thiếu `EW_ret`** (không mã nào đủ thanh khoản) — tôi coi như 0, không bỏ ngày khỏi tích, để
   mốc không bị phóng đại.
5. **Đối chứng âm §3.9 "đi ngẫu nhiên quanh mốc"** — "ngẫu nhiên" không có seed trong brief; tôi dùng
   chuỗi xác định ±0,2% quanh giá vốn (không dùng `random`) để test không chớp chờn.
6. **Số test**: brief ghi "9 test", ca 9 tách dương/âm nên bộ thật có 10. Cả 9 ca đều có mặt.
7. **`npx gitnexus analyze` có tác dụng phụ** (sửa `AGENTS.md`/`CLAUDE.md`, tạo `.claude/skills/*`) —
   brief không lường điều này; xem §4.

## 6. Những gì KHÔNG kiểm được

1. **Khớp lệnh trong phiên**: dữ liệu chỉ có OHLC ngày. Lệnh được mô hình ở đúng `open` phiên t+1, và
   `entry_status` chỉ bắt được giá trần / volume 0 / thiếu nến — không có trần-sàn trong phiên, không
   có trượt giá theo khối lượng. Với 9.239 lệnh và thanh khoản mục tiêu ≥ 2 tỷ/phiên thì đây là hạn chế
   thật nhưng **không đủ sức đảo dấu** một mức vượt trội −0,51%/tháng.
2. **Thiên lệch sống sót**: không có mã hủy niêm yết ⇒ kết quả lạc quan hơn sự thật (xem §2).
3. **Vốn**: số vị thế mở đồng thời trung vị 30, **tối đa 208**. Brief không chốt vốn định cỡ, nên con số
   này chỉ để biết cần bao nhiêu vốn; kết quả **không** phụ thuộc vào việc có đủ vốn hay không (tỷ lệ
   vượt trội và lợi nhuận ròng mỗi lệnh là số bình quân, không phải số tuyệt đối theo danh mục).
4. **Không mô phỏng được NAV/premium của ETF** — vô can ở đây vì đo trên cổ phiếu, không phải ETF.
5. **Không mở niêm phong, không ghi `docs/holdout-unlock-log.md`**: đúng theo §5 vì kết quả KHÔNG ĐẠT.

Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`.

---

## Audit của Claude (10/10/2026)

**Lỗi ngữ nghĩa đã sửa (chạy lại lần 2).** Brief §1.4 viết "kiểm tại CLOSE mỗi phiên d ≥ E … phiên thoát không sớm hơn E+2", tức điều kiện chạm ngay phiên E vẫn được ghi nhận, chỉ là bán muộn tới E+2. Code nộp lần đầu (`_find_exit`, `if d >= E + 1`) **bỏ qua hẳn** mọi điều kiện chạm ở phiên E, và không khai ra trong 7 chỗ tự diễn giải. Claude phát hiện bằng cách viết lại độc lập quy tắc từ brief cho HPG/VNM/FPT. Ca VNM vào 05/12/2017: phiên E đóng cửa đã về lại đỉnh cũ (TP), code cũ bỏ qua, hôm sau rơi thành STOP −8,04%; đúng brief là TP, thoát E+2, −9,07%. Sửa: `x = max(d + 1, E + 2)`, kiểm từ d = E. Thêm test `test_cham_ngay_phien_E_van_duoc_ghi_nhan_thoat_o_E_cong_2` (đỏ trước khi sửa, xanh sau).

**Kiểm độc lập sau khi sửa:** HPG 40/40, VNM 15/15, FPT 35/35 lệnh khớp chính xác (ngày vào, ngày ra, lý do, lãi/lỗ ròng tới 6 chữ số).

**Kết quả lần 2 (thay cho các con số lần 1 ở trên):**

| | Lần 1 (code cũ) | **Lần 2 (đúng brief)** |
|---|---|---|
| Số lệnh IS | 9.239 | **9.356** |
| Vượt thị trường TB/tháng | −0,511% | **−0,468%** (KTC95 [−0,744%; −0,137%]), p = 0,996 |
| Lãi ròng TB mỗi lệnh | −0,045% | **−0,075%** (ngưỡng 0,38%) |
| PF ròng | 0,987 | **0,978** |
| Thoát: STOP / TP / TIME | — / 67,6% / — | 19,5% / **70,7%** / 9,8% |
| Số phiên giữ (trung vị) | 3 | **2** |
| Kết luận | KHÔNG ĐẠT | **KHÔNG ĐẠT** |

Theo năm (lần 2, lãi ròng TB mỗi lệnh): 2017 +0,21% · 2018 −1,55% · 2019 −0,51% · 2020 +0,95% · 2021 +0,47% (4.472 lệnh) · 2022 −1,89%. Chiến lược chỉ có lãi trong năm thị trường tăng mạnh, và vẫn thua thị trường cùng khoảng giữ.

**Cơ chế:** 70,7% lệnh thoát vì "về lại đỉnh cũ", trung vị chỉ giữ 2 phiên (mức tối thiểu do T+2). Thiết kế đo độ sâu điều chỉnh bằng close thấp nhất của 5 phiên **trước** t, nên phiên bật lên thường đã gần đỉnh cũ, và lệnh chốt lời gần như ngay lập tức. Mỗi vòng mất 0,76% chi phí cho một chuyển động giá nhỏ hơn thế. Đây là điểm yếu của **thiết kế Claude đặt**, ghi lại để giả thuyết sau không lặp lại. Nó không phải lý do để chỉnh quy tắc rồi đo lại trên cùng dữ liệu (spec mục G).

**Kết luận:** Pullback trong xu hướng (giữ ≤ 20 phiên, cắt lỗ 8%): **KHÔNG có lợi thế trên IS 2017–2022**. Phép đo âm thứ 17. Không mở niêm phong.

**Ngoài phạm vi (agent đã khai):** `npx gitnexus analyze` sửa `AGENTS.md`/`CLAUDE.md` và tạo `.claude/skills/*`; agent đã khôi phục. GitNexus báo lệch phiên bản DB (42 so với 40), nên `detect_changes`/`context` không chạy được. Cần cài lại GitNexus cùng phiên bản; việc này chưa giao.
