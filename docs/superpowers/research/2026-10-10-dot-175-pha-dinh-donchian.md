# Đợt 175 — Phá đỉnh Donchian 55/20, cổ phiếu VN nến ngày

Base: main `bf3b00a`. Ngày: 10/10/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-10-10-brief-dot-175-pha-dinh-donchian-co-phieu.md`.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.

## 0. Kết luận — ĐẠT, nhưng đây là kết quả ĐẠT mỏng nhất có thể, và tôi nêu hết chỗ mỏng

```
### §1.5 Bon dieu kien
  (1) >= 300 lenh           : 3173            -> DAT
  (2) p < 0,05 & TB > 0     : p = 0.0365, TB vuot troi/thang = +0.7964% (KTC95 [-0.0622%; +1.8326%]) -> DAT
  (3) TB rong >= 0,5*cost_rt: TB rong = +3.1015%, 0,5*cost_rt = 0.3800% (cost_rt = 0.7600%) -> DAT
  (4) profit factor rong>1,2: PF = 1.4894 -> DAT
  => DAT
```

Theo §5: **ĐẠT** ⇒ phần mở niêm phong **thuộc về Claude**, một lần (2023-01 → 09/2026), và phải ghi
`docs/holdout-unlock-log.md`. Tôi không làm việc đó.

**Năm điều phải đọc kèm con số ĐẠT này, không được tách rời:**

1. **KTC95 của vượt trội theo tháng CHỨA 0** ([−0,0622%; +1,8326%]) trong khi p một phía = 0,0365.
   Bốn điều kiện đã chốt chỉ đòi p một phía, nên theo luật là ĐẠT — nhưng theo KTC hai phía thì
   "khác 0" chưa đạt mức 95%. Hai con số này không mâu thuẫn về mặt kỹ thuật (p một phía ≈ 3,65%
   nằm sát ngưỡng nên phân vị 2,5% chỉ hơi dưới 0), nhưng người đọc phải biết: biên an toàn gần bằng 0.
2. **Đây là giả thuyết thứ 6 của tháng 10.** Với 6 giả thuyết độc lập, xác suất có ít nhất một cái ra
   p < 0,05 **do may mắn** ≈ 26%. Con số 0,0365 một mình vì vậy **không** phải bằng chứng mạnh; nó chỉ
   vượt ngưỡng đã chốt trước. Đây không phải lỗi của phép đo — là điều phải nói ra.
3. **Thiên lệch sống sót đẩy kết quả LÊN.** `bars_daily` không có mã đã hủy niêm yết, nên vũ trụ này
   là vũ trụ "sống sót" — với chiến lược mua-khi-phá-đỉnh thì thiên lệch này **ủng hộ** chiến lược.
   Kết luận KHÔNG ĐẠT trước đây thì bền trước thiên lệch; kết luận **ĐẠT** thì **không** bền: dữ liệu
   thật (có mã hủy niêm yết) sẽ kém hơn, không tốt hơn.
4. **Lợi thế không ổn định theo thời gian.** Vượt trội trung bình theo năm:
   2017 **+3,138%**, 2018 **+0,822%**, 2019 **+0,807%**, 2020 **−0,825%**, 2021 **−0,097%**, 2022 **−0,308%**.
   Ba năm dương đầu gánh toàn bộ kết quả; ba năm cuối của IS đều **âm**. Một lợi thế chỉ sống ở 2017–2019
   là câu chuyện "thị trường mới nổi giai đoạn đầu", không phải "sàn VN có lợi thế tín hiệu kỹ thuật".
5. Tôi **không** kiểm định lại thêm gì sau khi thấy số (không đổi 55/20, không đổi cắt lỗ 10%, không
   thêm MA200 hay bộ lọc nào) — đúng §1.7.

## 1. Đối chiếu kỳ vọng trước của Claude

Claude kỳ vọng **âm**, với hai lý do: momentum 12−1 tháng thua có ý nghĩa ở VN (đợt 102), và VCP/SEPA
(hai dạng mua khi phá nền) đều âm (đợt 99, 123).

**Kết quả đo không khớp kỳ vọng đó**: IS cho ĐẠT theo luật đã chốt. Điều đáng chú ý là *cơ chế* khác
hẳn nhóm đã đo âm:
- Trung vị giữ **31 phiên**, 39,0% lệnh chạy hết 40 phiên ⇒ đây là chiến lược theo xu hướng **chậm**,
  không phải "vào nhanh ra nhanh" như pullback đợt 173 (trung vị giữ 3 phiên).
- 37,3% lệnh thoát bằng **cắt lỗ** −10%, tức chấp nhận bị quét thường xuyên để giữ phần đuôi dài;
  lợi nhuận ròng trung bình +3,10%/lệnh lớn hơn nhiều so với mức phí 0,76%/vòng.
- Ở đợt 173, tôi đo được "chuyển động trung bình của lệnh không đủ trả phí" (−0,0446%/lệnh). Ở đây
  thì có (+3,10%/lệnh). Hai chiến lược khác nhau về **độ dài giữ**, và đó là chỗ khác biệt.

Vì vậy tôi báo thẳng: kỳ vọng âm của brief **không thành hiện thực** ở IS, nhưng toàn bộ mục 0 nói rõ
vì sao tôi vẫn khuyên đọc kết quả này như **một ứng viên mỏng**, không phải một chiến lược đã chứng minh.

## 2. Lệnh chạy IS và output đầy đủ, nguyên văn

```
$ set -a && . ./.env && set +a && export DB_DSN="${DB_DSN/localhost/127.0.0.1}"
$ uv run python scripts/screen_donchian_breakout.py      # EXIT=0, 39,8s
```

```
# Universe: 1554 ma trong bars_daily, 1308 sau exclusions.txt, 1284 la ma co phieu (bo 24 khong phai co phieu, 246 ma trong exclusions)
# CANH BAO thien lech song sot: KHONG co ma da huy niem yet trong bars_daily. Moi so sanh chi trong CUNG universe nay, khong so voi ETF.
# Niem phong: doc toi 2023-01-01, nem loi voi nen >= 2023-01-01. IS = tin hieu 2017-01-01 -> 2022-10-31.
# Doc 1284 ma, bo 10441 nen gia <= 0, 1208 ma co du lieu dung duoc
# So lenh IS: 3173 | so thang co lenh: 71

### §1.5 Bon dieu kien
  (1) >= 300 lenh           : 3173            -> DAT
  (2) p < 0,05 & TB > 0     : p = 0.0365, TB vuot troi/thang = +0.7964% (KTC95 [-0.0622%; +1.8326%]) -> DAT
  (3) TB rong >= 0,5*cost_rt: TB rong = +3.1015%, 0,5*cost_rt = 0.3800% (cost_rt = 0.7600%) -> DAT
  (4) profit factor rong>1,2: PF = 1.4894 -> DAT
  => DAT

### §1.6 Mo ta
  So ngay giu: min 2 | trung vi 31 | max 42 | TB 26.68
  Thoat vi STOP   :  1184 (37.3%)
  Thoat vi CHANNEL:   751 (23.7%)
  Thoat vi TIME   :  1238 (39.0%)
  Vi the mo dong thoi (theo ngay): min 1 | trung vi 40 | max 301 (tb 58.17)
  Theo nam vao lenh (n, TB rong, tong rong, TB vuot troi):
    2017:  367 lenh, TB +6.393%, tong +2346.22%, vuot troi TB +3.138%
    2018:  284 lenh, TB -2.785%, tong -790.94%, vuot troi TB +0.822%
    2019:  297 lenh, TB -0.463%, tong -137.64%, vuot troi TB +0.807%
    2020:  592 lenh, TB +6.436%, tong +3809.84%, vuot troi TB -0.825%
    2021: 1234 lenh, TB +6.390%, tong +7884.76%, vuot troi TB -0.097%
    2022:  399 lenh, TB -8.199%, tong -3271.21%, vuot troi TB -0.308%
  Tin hieu bi bo vi vao lenh: {'ceiling': 76, 'zero_volume': 25}
# Xong sau 39.8s
```

Số mã: **1.284** mã cổ phiếu trong universe (1.208 mã có dữ liệu dùng được), **3.173 lệnh** / 71 tháng.
Số vị thế mở đồng thời trung vị **40**, tối đa **301** — con số này nói chiến lược cần rất nhiều vốn
nếu chạy toàn vũ trụ (brief không chốt vốn định cỡ, nên đây chỉ là mô tả).

**Cảnh báo đa so sánh:** 6 giả thuyết trong tháng 10, vượt ngân sách mục F (spec mục H cho phép
ngày 10/10). Đây là lý do thứ nhất trong mục 0 để không đọc 0,0365 như bằng chứng mạnh.

**Cảnh báo thiên lệch sống sót:** không có mã đã hủy niêm yết ⇒ vũ trụ sống sót ⇒ **ủng hộ** chiến
lược phá đỉnh. Kết luận ĐẠT vì thế là **cận trên**, không phải cận dưới. Script in cảnh báo ngay đầu.

## 3. TDD: 10 test, bảng phá hoại, và các cổng

`tests/test_screen_donchian_breakout.py` — dữ liệu dựng tay, không đọc DB. Chín ca theo §3 (ca 9
"đối chứng dương/âm" tách thành hai test ⇒ tổng **10**).

```
$ uv run pytest tests/test_screen_donchian_breakout.py tests/test_scripts_convention.py -v
13 passed
$ uv run pytest tests/test_screen_donchian_breakout.py -q
10 passed in 1.98s
$ python scripts/screen_donchian_breakout.py --help        # chay tu goc repo: OK
```

| Phép phá | Test phải đỏ | Kết quả |
|---|---|---|
| (i) dùng `high[t]` trong cửa sổ đỉnh (55 phiên kết thúc tại t thay vì t−1) | `test_tin_hieu_pha_dinh_dung_ngay_va_khong_tinh_nen_t` | **8 đỏ**, gồm đúng test này |
| (ii) bỏ qua điều kiện chạm ở phiên E, E+1 (vòng kiểm bắt đầu từ E+2) | `test_cham_cat_lo_ngay_phien_E_thi_thoat_o_close_E_cong_2` | **1 đỏ**, đúng test này |
| (iii) đảo thứ tự ưu tiên cắt lỗ / kênh đáy | `test_cung_phien_cham_ca_cat_lo_va_thung_kenh_thi_ly_do_la_cat_lo` | **3 đỏ**, gồm đúng test này |
| (iv) thoát ở close phiên chạm thay vì phiên sau | `test_ba_ly_do_thoat_dung_ly_do_va_dung_phien` | **1 đỏ**, đúng test này |

Khôi phục `cp` từ `%LOCALAPPDATA%\Temp\backup_dot175_screen_donchian_breakout.py` → `10 passed`,
nội dung file khớp nguyên bản từng byte, `sha256 = 38ff6f6c96573fd2…`.

## 4. Số test toàn cục, ruff, detect-changes

```
uv run pytest -m "not integration" -q
  TRƯỚC (bản sao nguyên vẹn HEAD, `git archive HEAD` dựng ngoài repo): 1822 passed, 154 deselected
  SAU   (cây làm việc hiện tại)                                      : 1832 passed, 154 deselected
uv run ruff check trading tests scripts   -> All checks passed!
```

Chênh **đúng 10** = 10 test mới, 0 test đỏ ở cả hai lượt.

`node .gitnexus/run.cjs detect-changes --scope all --repo .` → **"No changes detected."** Đọc đúng
cách: đợt này **không sửa một dòng nào của file có sẵn**; cả ba file đều là file MỚI chưa được git
theo dõi, mà `detect-changes` chỉ nhìn phần đã theo dõi. Đây là "không có gì để thấy", **không phải**
"không có thay đổi". (Brief đã dặn đúng: **không** dùng `npx gitnexus` — tôi dùng `node .gitnexus/run.cjs`.)

`context` cho ba hàm dùng lại đều chạy được qua CLI mới, nhưng `evaluate` **trùng tên** với
`scripts/host_preflight.py:evaluate` nên phải gọi bằng uid
`Function:scripts/screen_pullback_trend.py:evaluate`; hai hàm kia (`excess_of_trade`,
`trading/stock_study.py:entry_status`) trả bình thường.

## 5. Brief mơ hồ ở đâu (mọi chỗ tôi phải tự diễn giải)

1. **§1.4 tự mâu thuẫn.** Câu đầu: "thoát ở CLOSE phiên d+1". Câu sau: "Ràng buộc T+2: phiên thoát =
   `max(d+1, E+2)`". Hai câu này khác nhau khi d = E (d+1 = E+1 < E+2). Tôi theo câu sau (T+2 thắng),
   và **vẫn ghi nhận** điều kiện chạm ở phiên E — đúng như brief dặn, đây là lỗi agent đợt 173 từng mắc.
2. **"Thủng kênh đáy" khi d < 20**: không đủ 20 nến trước d thì tôi **không xét** điều kiện đó (không
   co cửa sổ lại). Brief không nói.
3. **Đỉnh tham chiếu**: §1.2 ghi `max(high[t−55..t−1])`, tức **không** tính nến t. Tôi làm đúng chữ, và
   có test riêng cho trường hợp "đóng cửa bằng đúng đỉnh thì không tính là phá đỉnh".
4. **Số phiên giữ tối đa**: hết giờ ở d = E+39 nhưng phiên thoát = max(d+1, E+2) = E+40 ⇒ 40 phiên
   **sau** phiên vào lệnh. Khớp câu "giữ tối đa 40 phiên". Đo thật thấy `max = 42` vì luật "nến khối
   lượng 0 thì lùi tiếp" cộng thêm 2 phiên.
5. **"Đi ngẫu nhiên" của đối chứng âm**: brief không cho seed; tôi dùng chuỗi xác định (±0,2% quanh giá
   vốn) để test không chớp chờn, không dùng `random`.
6. **Số test**: brief ghi "9 test", ca 9 tách dương/âm nên bộ thật có **10**. Cả 9 ca đều có mặt.
7. **KTC95 chứa 0 nhưng p một phía = 0,0365**: brief chỉ chốt p một phía trong bốn điều kiện, không nói
   phải làm gì khi KTC hai phía chứa 0. Tôi **không** tự thêm điều kiện (sẽ là đổi luật sau khi thấy số);
   tôi báo cả hai con số ở mục 0 để Claude quyết khi mở niêm phong.

## 6. Những gì KHÔNG kiểm được

1. **Khớp lệnh trong phiên**: chỉ có OHLC ngày; `entry_status` bắt được giá trần / khối lượng 0 / thiếu
   nến, không có trần-sàn trong phiên, không trượt giá theo khối lượng. Với 3.173 lệnh và thanh khoản
   ≥ 2 tỷ/phiên, đây là hạn chế thật — đặc biệt vì **kết quả lần này là ĐẠT**, tức sai số ở đây có thể
   lật kết luận (ở các đợt âm thì nó không lật được).
2. **Thiên lệch sống sót**: xem mục 0 điều 3 — với kết quả ĐẠT, đây là **hạn chế nghiêm trọng nhất**.
3. **Không mô phỏng được khối lượng lệnh khớp thật** (thanh khoản theo ngày, không theo lệnh), nên
   "vượt trội +0,80%/tháng" là con số lý thuyết của mô hình, không phải con số giao dịch được.
4. **Vốn**: trung vị 40 vị thế mở đồng thời, tối đa 301 — brief không chốt vốn; kết quả không phụ thuộc
   vào vốn (các số là bình quân mỗi lệnh), nhưng chạy thật với vốn nhỏ sẽ **không** vào được hết tín hiệu.
5. **Không mở niêm phong, không ghi `docs/holdout-unlock-log.md`** — việc đó thuộc Claude (§5).

Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`.

---

## Audit của Claude (10/10/2026) — KẾT LUẬN CUỐI: KHÔNG ĐẠT (phép đo âm thứ 18)

### 1. Kiểm độc lập IS
Claude viết lại quy tắc từ brief, không dùng code của agent, và chạy trên toàn universe. Kết quả khớp **3.173/3.173 lệnh**: cùng ngày vào, ngày ra, lý do, lợi nhuận ròng tới 8 chữ số, 0 mã lệch. TB ròng 3,1015%, PF 1,4894, khớp. Test 10/10 xanh. Claude không tìm thấy lỗi code.

### 2. Vì sao IS "ĐẠT" yếu hơn con số
- **Lời tập trung vào vài lệnh đầu cơ năm 2021:** CEO +407%, API +242%, PVL +213%, TGG +183%… Bỏ 31 lệnh lãi nhất (1%) thì TB ròng còn 1,76%, PF còn 1,27.
- **Điều kiện 3 và 4 đo lợi nhuận tuyệt đối,** nên ăn theo thị trường tăng (2017, 2020, 2021). Phép đo đúng là vượt trội. Tính theo trọng số lệnh, vượt trội chỉ +0,28%. Ba năm 2020–2022 (2.225/3.173 lệnh) đều âm. Chuỗi theo tháng đạt p 0,036 vì các tháng 2017–2019, dù ít lệnh, có trọng số ngang tháng 2021.
- **Ẩn giả định thuận lợi:** lệnh cắt lỗ giả định bán được ở close. Thực tế mã đầu cơ có thể nằm sàn trắng bên mua nhiều phiên. Các mã đã hủy niêm yết (sập rồi biến mất) không có trong dữ liệu.

### 3. Mở niêm phong MỘT lần (ghi `docs/holdout-unlock-log.md` trước khi chạy)
Cùng quy tắc, cùng code `simulate_symbol`/`evaluate`. Tín hiệu 2023-01-01 → 2026-07-31, nến tới 30/09/2026:

| Điều kiện | Holdout | |
|---|---|---|
| (1) ≥ 300 lệnh | 2.389 | ĐẠT |
| (2) p < 0,05, TB > 0 | vượt trội/tháng **−0,45%**, p 0,758, KTC [−1,33%; +0,65%] | **KHÔNG** |
| (3) TB ròng ≥ 0,38% | +0,18% | **KHÔNG** |
| (4) PF > 1,2 | 1,03 | **KHÔNG** |

Theo năm, vượt trội TB: 2023 −1,73%, 2024 +0,61%, 2025 −0,75%, 2026 −1,32%. Bỏ 1% lệnh lãi nhất thì TB ròng −0,74%.

**Kết luận:** "Phá đỉnh Donchian 55/20 (cắt lỗ 10%, giữ ≤ 40 phiên): KHÔNG có lợi thế ngoài mẫu." Kết quả IS đúng với cảnh báo đa so sánh của agent (≈26% có một p < 0,05 do may trong 6 giả thuyết). Tập 2023+ nay đã dùng cho họ phá đỉnh/Donchian: không đo lại họ này bằng cách chỉnh 55/20/10%/40.
