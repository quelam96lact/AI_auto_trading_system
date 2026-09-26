# Brief đợt 102 — Momentum danh mục trên cổ phiếu VN (12−1 tháng, giữ 1 tháng), đăng ký trước

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `cd08f4e`.
Người giao, audit, commit, push: Claude. Người thực thi: agent. Agent **KHÔNG** commit, **KHÔNG** push.
Làm được ngay cuối tuần. Chỉ **đọc** DB. **Không** đụng container, máy ghi sổ lệnh, Task Scheduler, `trading/`, và mọi file có sẵn.

---

## 0. Vì sao, và khác gì tám đợt trước

Tám đợt trước đo **tín hiệu điểm vào** (SMC, VCP, chỉ báo) và cả tám đều âm. Đợt này đo một thứ **khác loại**: một **danh mục xoay vòng hằng tháng**.
- Mỗi cuối tháng, xếp hạng mọi cổ phiếu đủ thanh khoản theo mức tăng **12 tháng qua, bỏ tháng gần nhất** ("momentum 12−1").
- Mua đều tỷ trọng nhóm **10% mạnh nhất**, giữ **một tháng**, rồi làm lại.

**Vì sao chọn momentum:** trong các hiệu ứng thị trường đã công bố, momentum 12−1 có bằng chứng rộng nhất, trên nhiều nước và nhiều thập kỷ. Nó cũng hợp với ràng buộc VN: chỉ mua, giữ lâu hơn T+2,5, trên nhiều mã. Chủ dự án chọn hướng này ngày 26/09.

**Điều không biết trước:** momentum có thể **không** có ở VN. Thị trường nhỏ, nhà đầu tư cá nhân chiếm đa số, và có nghiên cứu cho thấy thị trường mới nổi hay bị đảo chiều ngắn hạn. **Kết quả âm là kết quả hợp lệ.**

---

## 1. Thiết kế ĐĂNG KÝ TRƯỚC — mọi tham số chốt ở đây, KHÔNG được đổi

**Chạy phép đo thật ĐÚNG MỘT LẦN.** Có lỗi code phải chạy lại thì dán **tất cả** các lần kèm lý do. **Không** thử cửa sổ khác (6−1, 3−1…), **không** thử nhóm khác (5%, 20%…), **không** đổi tần suất xoay vòng.

### 1.1 Dữ liệu và vũ trụ

- Như đợt 99: `exclusions.txt`, bỏ nến OHLC ≤ 0, múi giờ VN; đọc từ 2016-01-01.
- **Niêm phong từ 2023-01-01:** code phải ném lỗi. Dùng lại `validate_sealed_bars` của `scripts/screen_vcp_daily.py`.
- **Chỉ cổ phiếu:** chỉ giữ mã có **đúng 3 ký tự, mỗi ký tự là chữ in hoa hoặc chữ số** (`A–Z`, `0–9`). Mã cổ phiếu VN **có thể chứa chữ số** (`L14`, `C47`, `VC3`, `PV2`, `D2D`…), nên **không** được lọc theo "chỉ chữ cái". ETF (`E1VFVN30`, `FUEVFVND`) và chứng quyền (`CHPG2301`…) đều dài hơn 3 ký tự, nên bị loại. Báo số mã bị loại theo quy tắc này và liệt kê 20 mã đầu. **Mốc Claude đã đo (26/09):** quy tắc này loại đúng **24 mã**, cả 24 là ETF/quỹ (`E1VFVN30`, `FUE…`, `FUC…`); và **125** cổ phiếu thật có chữ số trong mã được **giữ**. Kết quả khác thì dừng và báo.

### 1.2 Lịch xoay vòng

- **Ngày xếp hạng `F`:** phiên giao dịch **cuối cùng** của mỗi tháng dương lịch (giờ VN), xác định từ **chính dữ liệu** (ngày lớn nhất có nến của bất kỳ mã nào trong tháng).
- **Tháng giữ:** tháng kế tiếp. **Vào** ở giá mở cửa phiên đầu tiên của tháng giữ; **ra** ở giá đóng cửa phiên cuối cùng của tháng giữ.
- **IS:** ngày xếp hạng từ **2016-12-30** (cần 252 phiên lịch sử) tới **2022-11-30**; tức tháng giữ từ **01/2017 tới 12/2022**, khoảng **72 tháng**.

### 1.3 Điều kiện được xếp hạng tại `F` (tất cả phải đúng)

1. Có nến tại `F`.
2. Thanh khoản: trung bình `close × volume` của **20 nến cuối, tính tới hết `F`**, ≥ **1 tỷ đồng**. Dùng lại `liquidity_ok(bars, t_F + 1, min_turnover=1e9)`: hàm này lấy 20 nến **trước** chỉ số truyền vào.
3. Lịch sử: chính mã đó có nến ở chỉ số `t_F − 252` và `t_F − 21`, **và** ngày của nến `t_F − 252` không sớm hơn `F − 400 ngày lịch`. Điều kiện sau loại mã từng tạm ngừng lâu, vì với những mã đó 252 nến không còn là 12 tháng.

**Điểm momentum:** `mom = close[t_F − 21] / close[t_F − 252] − 1`. Bỏ 21 phiên gần nhất (≈ 1 tháng) là quy ước chuẩn, vì tháng gần nhất hay đảo chiều.

### 1.4 Danh mục

- **Danh mục thắng (`WIN`):** 10% mã có `mom` cao nhất, làm tròn **lên**, tối thiểu 10 mã. Nếu số mã đủ điều kiện dưới 100 thì **bỏ tháng đó**, đếm và báo.
- **Đối chứng chính (`EW`):** **toàn bộ** mã đủ điều kiện §1.3 tại cùng `F`, đều tỷ trọng. Đây là "mua bừa cổ phiếu đủ thanh khoản", cùng vũ trụ và cùng quy ước.
- **Chỉ mô tả, không dùng để kết luận:**
  - **`LOSE`:** 10% `mom` thấp nhất. Chênh `WIN − LOSE` cho biết momentum có tồn tại hay không; không bán khống được nên không giao dịch được phần `LOSE`.
  - **`VN30ETF`:** mua và giữ `E1VFVN30` từ giá mở cửa phiên đầu tháng 01/2017 tới giá đóng cửa phiên cuối tháng 12/2022, trừ chi phí một vòng.

### 1.5 Lợi nhuận và chi phí

- **Lợi nhuận gộp của một mã trong tháng giữ:** `close(phiên cuối tháng) / open(phiên đầu tháng) − 1`.
  - Mã **mở cửa ở giá trần** phiên đầu tháng (theo sàn, như đợt 99; dùng `is_ceiling_open`) thì **không mua được**: loại khỏi danh mục tháng đó, đếm và báo. **Không** thay bằng mã khác.
  - Mã **không có nến** nào sau phiên đầu tháng: dùng giá đóng cửa của phiên cuối cùng **có** nến trong tháng; nếu không có phiên nào, loại, đếm và báo.
- **Lợi nhuận gộp của danh mục** = trung bình đều tỷ trọng của các mã trong danh mục.
- **Chi phí theo vòng quay:**
  - `turnover(M)` = tỷ lệ mã trong danh mục tháng `M` **không** có trong danh mục tháng `M−1` (tháng đầu = 1,0).
  - `cost_rt = 2 × FEE_RATE + SELL_TAX_RATE + 2 × SLIPPAGE_BPS / 10_000`, **import** hằng số từ `trading/paper_broker.py`.
  - `net(M) = gross(M) − turnover(M) × cost_rt`.
  - Áp **cùng công thức** cho `WIN`, `EW`, `LOSE`. Ghi rõ đây là xấp xỉ: mã được giữ tiếp sang tháng sau vẫn bị tính lợi nhuận từ giá mở cửa đầu tháng, nên bỏ qua khoảng qua đêm ở ranh giới tháng.

### 1.6 Kiểm định — MỘT phép thử chính

- **Chuỗi vượt trội tháng:** `excess(M) = net_WIN(M) − net_EW(M)`.
- **Chính:** trung bình `excess > 0`, kiểm một phía. Dùng **bootstrap theo khối 3 tháng liên tiếp** (lấy mẫu có hoàn lại các khối 3 tháng liền nhau, đủ tổng độ dài chuỗi), 2.000 lần, `seed = 42`. `p` = tỷ lệ mẫu có trung bình ≤ 0.
  - `bootstrap_by_month` của đợt 99 lấy mẫu **từng tháng độc lập**. Ở đây mỗi tháng chỉ có **một** giá trị và các tháng liền nhau có thể tương quan, nên phải dùng **khối liền nhau**. Viết hàm mới trong file của đợt này; **không** sửa `screen_vcp_daily.py`.
- **Kết luận "CÓ LỢI THẾ" khi cả ba:**
  (a) `p < 0,05`;
  (b) trung bình `net_WIN > 0`;
  (c) **trung vị** `excess > 0`.
- Dưới 60 tháng hợp lệ thì ghi `IT_THANG` và không kết luận.

---

## 2. Phạm vi

- **Được thêm:** `scripts/screen_momentum_portfolio.py`, `tests/test_screen_momentum_portfolio.py`.
- **Chỉ import, không sửa:**
  - từ `scripts/screen_vcp_daily.py`: `load_universe`, `clean_bars`, `validate_sealed_bars`, `liquidity_ok`, `is_ceiling_open`, `bar_date`;
  - `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` từ `trading/paper_broker.py`;
  - `resolve_dsn` từ `scripts/_db_common.py`, `Storage`, `TZ`.
- **Cấm** chép lại các hàm trên. Không dùng lại được thì **dừng và báo**.
- Không pandas/numpy (repo không có).
- Sau khi viết: `gitnexus_detect_changes()`, và ghi rõ nếu kết quả là "none" do file mới chưa vào index.

---

## 3. Kiểm chứng (TDD: viết test trước, thấy đỏ, rồi mới viết code)

Test trên dữ liệu dựng tay. Nến dựng tay giá thấp nên **truyền ngưỡng thanh khoản nhỏ** vào test hình dạng. **Bắt buộc:** một test ghim rằng lần chạy thật dùng **1 tỷ**, và một test chứng minh mã dưới ngưỡng **không** được xếp hạng.

1. **Ngày xếp hạng:** ngày cuối tháng không phải phiên giao dịch (ví dụ 31/12 là Chủ nhật) → `F` là phiên cuối cùng **có nến**.
2. **Điểm momentum:** chuỗi dựng tay → `mom` đúng bằng `close[t−21]/close[t−252] − 1`, tính tay trong docstring. **Nến 20 phiên cuối trước `F` không được ảnh hưởng tới `mom`**: sửa chúng thì `mom` giữ nguyên.
3. **Chống nhìn trộm tương lai — quan trọng nhất:** sửa tùy ý mọi nến **sau `F`**. Tập mã đủ điều kiện, điểm `mom` và danh mục `WIN` tại `F` phải **giữ nguyên**. Chỉ lợi nhuận tháng giữ được phép đổi.
4. **Lịch sử có khoảng trống:** mã có nến `t_F − 252` nhưng ngày của nó sớm hơn `F − 400 ngày` → **không** đủ điều kiện.
5. **Chỉ cổ phiếu:** `E1VFVN30`, `FUEVFVND`, `CHPG2301`, `hpg` (chữ thường) → bị loại; `HPG`, `VCB`, `L14`, `VC3`, `D2D` → **giữ**. Ca `L14`/`VC3` bắt lỗi lọc "chỉ chữ cái".
6. **Cỡ danh mục:** 250 mã đủ điều kiện → `WIN` có 25 mã; 101 mã → 11 (làm tròn lên); 99 mã → **bỏ tháng**.
7. **Mở trần:** mã trong `WIN` mở trần phiên đầu tháng → bị loại khỏi tháng đó, **không** được thay.
8. **Chi phí theo vòng quay:** danh mục tháng trước {A, B, C, D}, tháng này {A, B, E, F} → `turnover = 0,5`, `net = gross − 0,5 × cost_rt`, với `cost_rt` tính từ hằng số import. Test phải **đỏ** nếu ai đó gõ tay 0,006.
9. **Bootstrap khối 3 tháng:** với `seed` cố định cho kết quả tất định. Mỗi mẫu gồm các **khối liền nhau** (kiểm bằng một chuỗi dựng tay có giá trị đánh số tăng dần).
10. **Niêm phong:** nến ngày 2023-01-03 giờ VN → ném lỗi.
11. **Múi giờ:** nến `ts = 2022-11-30 17:00 UTC` là ngày **01/12** giờ VN, nên thuộc **tháng 12**, không phải tháng 11.

### Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo**. **Cấm** `git checkout`, `git restore`, `git stash`.
- Tính `mom` bằng `close[t_F]` thay cho `close[t_F − 21]` → test 2 đỏ.
- Xếp hạng bằng dữ liệu **sau** `F` (ví dụ dùng giá đóng cửa của phiên đầu tháng giữ) → test 3 đỏ.
- Bỏ điều kiện 400 ngày → test 4 đỏ.
- Thay mã mở trần bằng mã kế tiếp → test 7 đỏ.
- Tính chi phí với `turnover = 1` mọi tháng → test 8 đỏ.
- Bootstrap từng tháng độc lập → test 9 đỏ.
- Khôi phục, chạy lại, sạch. Báo tên test đỏ từng bước.

### Tổng
```
uv run pytest -m "not integration" -q     # mốc: 1009 passed
uv run ruff check trading tests scripts
```

---

## 4. Chạy thật và đọc kết quả

`uv run python scripts/screen_momentum_portfolio.py`, **một lần**. In:
1. Vũ trụ: tổng số mã, số bị loại theo `exclusions.txt`, số bị loại vì không phải mã 3 chữ cái (kèm 20 mã đầu).
2. Số tháng hợp lệ, và số tháng bị bỏ kèm lý do; số mã đủ điều kiện mỗi tháng (nhỏ nhất, trung vị, lớn nhất); cỡ `WIN`.
3. Với `WIN`, `EW`, `LOSE`: lợi nhuận tháng trung bình và trung vị (gộp và ròng); **lợi nhuận kép năm (CAGR)** ròng; độ sụt vốn lớn nhất (max drawdown); tỷ lệ tháng dương; vòng quay trung bình.
4. `VN30ETF`: lợi nhuận kép năm ròng cho cả giai đoạn.
5. Chênh `WIN − LOSE` (mô tả): trung bình tháng, tỷ lệ tháng dương.
6. Phép thử chính: trung bình `excess`, KTC 95%, `p`, trung vị `excess`, và kết luận theo §1.6.
7. **Theo năm** (2017 … 2022): lợi nhuận ròng của `WIN` và `EW`. Mục đích là thấy kết quả có dồn vào một năm hay không.
8. Số lần loại vì mở trần, vì thiếu nến, và thời gian chạy.

**Quy tắc đọc, không tự diễn giải thêm:**
- Không đạt §1.6 → ghi **"Momentum 12−1 danh mục tháng: KHÔNG vượt được mua-đều cổ phiếu đủ thanh khoản, sau chi phí."**
- Đạt §1.6 → **KHÔNG mở tập từ 2023**, **KHÔNG xây chiến lược**. Chỉ báo cáo. Claude quyết có mở tập niêm phong hay không, và mở một lần.

---

## 5. Báo cáo cho Claude

1. detect_changes.
2. Test; kiểm thử phá hoại (tên test đỏ từng bước).
3. Pytest và ruff.
4. **Nguyên văn** toàn bộ output của lần chạy thật (mọi lần, nếu có chạy lại).
5. Mọi quyết định nhỏ agent phải tự chọn vì brief chưa nói: liệt kê rõ từng cái.
6. Mọi điều ngoài phạm vi: **báo cáo, không sửa.**

---

## 6. Hạn chế đã biết (ghi trong báo cáo, không tự sửa)

- **Thiên lệch sống sót toàn phần:** dữ liệu 2016–2022 không có mã hủy niêm yết (đợt 99). Nó làm cả `WIN` lẫn `EW` đẹp hơn thật. Phép so hai danh mục trong cùng vũ trụ ít bị ảnh hưởng hơn, nhưng momentum hay **tránh được** các mã sắp hủy niêm yết (vì chúng thường đang giảm mạnh), nên thiếu các mã đó có thể làm `LOSE` và `EW` **đẹp hơn thật**, tức làm lợi thế của `WIN` trông **nhỏ hơn thật**.
- **Giá đã điều chỉnh ngược:** tỷ số giá trong một mã vẫn đúng. Riêng ngưỡng thanh khoản tuyệt đối lệch ở các năm cũ (như đợt 99).
- **Chi phí xấp xỉ theo vòng quay** (§1.5).


---

## 7. Kết quả và audit của Claude (26/09)

**Chạy đúng một lần** (145,4 giây); log gốc `run_dot102.log` khớp báo cáo.

| Danh mục | TB tháng ròng | Trung vị tháng ròng | CAGR ròng | Sụt vốn lớn nhất | Vòng quay |
|---|---|---|---|---|---|
| WIN (10% mạnh nhất) | −0,12% | +0,81% | **−6,96%** | 63,6% | 0,338 |
| EW (mua đều) | +0,90% | +0,46% | **+6,52%** | 53,6% | 0,126 |
| LOSE (mô tả) | +0,06% | −0,62% | −6,42% | 69,7% | 0,407 |
| ETF `E1VFVN30` mua-giữ (mô tả) | | | **+9,18%** | | |

- Vượt trội tháng WIN − EW: **−1,02%**, KTC 95% [−1,81%; −0,26%] (**hoàn toàn dưới 0**), p = 0,9945, trung vị −1,49%. **Không đạt cả ba điều kiện.**
- WIN thua EW ở 5/6 năm; chênh WIN − LOSE âm (−0,18%/tháng). Trong 2017–2022, cổ phiếu tăng mạnh 12 tháng qua **không** tiếp tục tăng mạnh hơn.
- WIN có trung vị tháng cao hơn EW nhưng trung bình thấp hơn: đuôi lỗ rất nặng (2018, 2022).

**Kết luận: Momentum 12−1 danh mục tháng KHÔNG vượt được mua-đều cổ phiếu đủ thanh khoản, sau chi phí. Đây là phép đo âm thứ chín, và là lần đầu một phép đo *danh mục* thua có ý nghĩa thống kê.**

**Claude tính lại độc lập** ba tháng (03/2018, 06/2020, 05/2022) bằng code riêng: tìm ngày theo lịch, lọc thanh khoản, tính momentum, top 10% và lợi nhuận giữ, chỉ dùng chung hàm đọc DB. Kết quả **khớp tới 5 chữ số thập phân** với agent: số mã đủ điều kiện 151/235/369, và WIN/EW −0,11256/−0,07768, −0,08241/−0,05855, −0,21475/−0,15661.

**Sai sót của brief (agent phát hiện, đúng):** từ 2016-01-04 tới 2016-12-30 chỉ có **251** phiên, nên tháng xếp hạng 12/2016 không đủ 252 phiên và bị bỏ. Kết quả là 71 tháng chứ không phải 72; vẫn ≥ 60 nên vẫn kết luận được. Dòng in "(2016, 12) đến (2022, 11)" là biên của cửa sổ, không phải các tháng đã dùng; lỗi này chỉ ở phần trình bày, số liệu không bị ảnh hưởng.

**Điều đáng nói nhất cho chủ dự án:** trong 2017–2022, **mua và giữ ETF VN30 (+9,18%/năm ròng) thắng mọi thứ đã đo**, kể cả mua đều toàn thị trường (+6,52%). Đây là mốc mà bất kỳ chiến lược chủ động nào cũng phải vượt.