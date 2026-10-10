# Brief đợt 180 — Ma trận tương quan của rổ mã đang chạy (ĐĂNG KÝ TRƯỚC, phép đo MÔ TẢ)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.

**Đây KHÔNG phải một giả thuyết chiến lược ⇒ đề nghị KHÔNG tính vào ngân sách mục F** (tháng 10 đã dùng 7 giả
thuyết, trần 3). Lý do: không chọn luật giao dịch nào, không tối ưu tham số nào, không tính p-value cho chiến
lược nào, không sinh tín hiệu nào. Đây là một phép **mô tả rủi ro** của cấu hình đang chạy. Nếu Claude đọc khác,
xin **chặn brief** — đây là điểm cần quyết ở §7(a).

---

## 0. Câu hỏi, vì sao bây giờ, và điều KHÔNG hỏi

**Yêu cầu của chủ dự án (10/10, sau đợt 175):** *"Suy nghĩ xem có áp dụng matrix vào trading được không."*

Tôi đã tra ba nghĩa của "matrix" trong chính repo này trước khi trả lời:

| Nghĩa | Trạng thái trong repo | Bằng chứng |
|---|---|---|
| Ma trận đặc trưng + học máy | **Đã thử, đã âm** | đợt 169: 11 đặc trưng mặt cắt × 60 tháng, Ridge + LightGBM, p = 0,42 (phép đo âm thứ 15) |
| Ma trận trạng thái thị trường (Markov) | **Nền đã có, chưa dùng làm ma trận** | `scripts/measure_regime_hold.py`, regime RISK_ON/NEUTRAL/RISK_OFF (đợt 61/62) |
| **Ma trận tương quan / hiệp phương sai** | **CHƯA BAO GIỜ tính** | `grep -rn "\.corr()\|corrcoef\|np\.cov\|eig" trading/ scripts/` → **0 dòng** |

Đợt này làm nghĩa thứ ba, vì đó là lỗ thật và vì nó thuộc **quản trị rủi ro**, không phải đi tìm alpha mới.

**Câu hỏi:** rổ đang chạy `symbols: [HPG, IJC, AAA]` (config dòng 6) có **thực sự là ba cược độc lập** không?
Nếu không, hệ thống đang chấp nhận rủi ro lớn hơn con số "1%/lệnh" mà nó tin.

**Căn cứ (đã đọc code, không suy đoán):** `trading/risk.py` chỉ có bốn ràng buộc:
`max_positions = 5` (dòng 12, dùng ở 69/147), `max_order_value_pct = 0,20` (dòng 13),
`max_daily_loss_pct = 0,03` (dòng 14), `risk_pct = 0,01` với qty theo ATR (dòng 87–90).
`grep -n "correl\|tuong quan\|sector\|nganh" trading/risk.py` → **rỗng**. Không có ràng buộc tương quan,
không có ràng buộc ngành, không có đa dạng hóa nào ngoài số lượng vị thế.

**Vì sao đáng đo:** nếu tương quan đôi trung bình ρ̄ ≈ 0,8, ba lệnh "1% rủi ro" là **một cược ≈ 2,6–2,8%**, và
một phiên thị trường xấu có thể chạm `max_daily_loss_pct = 3%` ⇒ **halt cả ngày**. Đó là hệ quả vận hành,
không phải chuyện học thuật.

**Lịch sử rổ (config dòng 1–5):** HII bị loại 10/09/2026 vì **thanh khoản** (chỉ 38/108 phiên đủ 2 tỷ; GTGD
dao động 15,3 triệu – 30 tỷ), thay bằng HPG (100% phiên đạt ngưỡng). Tức tiêu chí chọn mã tới nay là **thanh
khoản**; **tương quan chưa từng là tiêu chí, cũng chưa từng được đo**.

**Không hỏi:** có dùng vốn thật được không; có đổi rổ mã không; có sửa định cỡ rủi ro không.
Ba việc đó thuộc quyết định riêng, phải có brief riêng (§7).

---

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu, universe, niêm phong
Giống hệt đợt 173/175 §1.1:
- `bars_daily`, `load_universe(storage, "exclusions.txt")`, chỉ mã cổ phiếu, bỏ nến giá ≤ 0.
- Đọc bằng `read_bars` trong `scripts/screen_pullback_trend.py` — hàm này gọi `validate_sealed_bars` **trước**,
  ném lỗi với mọi nến ≥ 01/01/2023. Cổng này **không được tháo**.
- **Cửa sổ chính A (mặc định, không chạm niêm phong): 2017-01-01 → 2022-12-31.**
- **Cửa sổ phụ B (CHỈ khi Claude cho phép): 2023-01-01 → nến cuối cùng.** Đây là **lần mở niêm phong thứ 5**;
  `docs/holdout-unlock-log.md` hiện có 4 lần (gần nhất: đợt 175, do Claude mở). Nếu Claude cho phép cửa sổ B,
  Claude ghi log (hoặc nói rõ để agent ghi theo mẫu), **trước** khi agent chạy. Cửa sổ B tồn tại vì câu hỏi
  "rủi ro của rổ **hôm nay**" chỉ trả lời được bằng dữ liệu gần đây — nhưng tôi không tự quyết việc mở niêm phong.

### 1.2 Định nghĩa (chốt trước)
- Lợi suất **log** theo phiên: `ln(close[d] / close[d−1])`, close đã điều chỉnh (bars_daily phần lớn đã
  back-adjust; xem §1.6).
- Chỉ dùng phiên mà **cả ba mã đều có nến hợp lệ** (giá > 0). Ghép theo **NGÀY**, không ghép theo chỉ số.
- Yêu cầu tối thiểu **250 phiên** chung; thiếu thì báo cáo ghi rõ và dừng (không nới).

### 1.3 Sáu số liệu phải in ra (và CHỈ sáu nhóm này)
1. **ρ̄** = trung bình ba hệ số tương quan Pearson đôi; kèm **Spearman** như biến thể bền (in cả hai).
2. **Ma trận tương quan 3×3** và **ba trị riêng** λ₁ ≥ λ₂ ≥ λ₃.
3. **Số cược hiệu dụng** `PR = (Σλ)² / Σλ²`. Với ma trận tương quan 3×3 thì Σλ = 3 ⇒ `PR = 9 / Σλ²`.
   In kèm biến thể độ vênh entropy của trị riêng chuẩn hóa (chỉ để đối chiếu, không dùng kết luận).
4. **Mốc so sánh bắt buộc:** ρ̄ của **toàn bộ mã cổ phiếu đủ dữ liệu** trong cùng cửa sổ (trung bình mọi cặp).
   Không có mốc này thì "ρ̄ = 0,75" vô nghĩa: phải biết nó cao hay thấp **so với chính thị trường**.
5. **Số phiên cả ba cùng giảm**, và trong **10 phiên tệ nhất** của chỉ số chuẩn (VNINDEX nếu có trong
   `bars_daily`, nếu không thì lợi suất mua đều toàn thị trường), cả ba cùng giảm bao nhiêu phiên.
6. **Ước lượng mất mát một phiên nếu cả ba cùng chạm dừng lỗ**, so với `max_daily_loss_pct = 3%`:
   dùng đúng công thức định cỡ của hệ thống (dòng 87–90 `risk.py`), ATR = trung bình thật 20 phiên của mỗi mã.
   Đây là **số mô tả**, KHÔNG phải mô phỏng giao dịch; báo cáo phải ghi rõ chữ này.

### 1.4 Ngưỡng diễn giải chốt TRƯỚC (để tôi không được nói lại cho vừa mắt)
- ρ̄ < 0,50 → không tập trung đáng kể; 0,50 ≤ ρ̄ < 0,70 → vừa; ρ̄ ≥ 0,70 → cao.
- PR ≥ 2,5 → gần ba cược độc lập; 2,0 ≤ PR < 2,5 → vừa; PR < 2,0 → ba vị thế chỉ còn **≤ 2 cược**.
- Kết luận **"rổ tập trung đáng lo"** chỉ khi hội **cả hai**: ρ̄ ≥ 0,70 **và** PR < 2,0 — **hoặc** ρ̄ cao hơn
  mốc so sánh ở (4) một cách rõ rệt (chênh ≥ 0,10) kèm PR < 2,0. Mọi tổ hợp khác phải viết là "chưa kết luận được".
- Trước khi chạy, tôi ghi vào nháp (và dán vào báo cáo) dự đoán của mình: **ρ̄ ≈ 0,6–0,8, PR ≈ 1,8–2,4** —
  để có cái đối chiếu, đúng kiểu các đợt trước.

### 1.5 Điều KHÔNG được làm (chống câu cá)
- Không chọn lại rổ mã, không lọc mã, không đổi tham số, không chạy bất kỳ backtest chiến lược nào.
- Không thêm số liệu ngoài §1.3 (muốn thêm ⇒ báo cáo ghi vào "đã tự ý thêm gì", không trộn vào kết luận).
- **Chạy đúng MỘT lần.** Ngoại lệ duy nhất như các đợt trước: phát hiện **lỗi code** thì được chạy lại và phải
  khai báo rõ trong báo cáo.

### 1.6 Dữ liệu bẩn đã biết (xử lý chốt trước)
- `bars_daily` đã back-adjust phần lớn, nhưng còn **51 chia tách chưa chỉnh / 49 mã** (ghi nhận từ trước).
- Chốt trước: đếm số phiên có `|log ret| > 0,5` của ba mã (nghi chia tách chưa chỉnh) và **in ra**;
  nếu > 0, in thêm **bản tính lại đã loại các phiên đó** (biến thể bền). Báo cáo phải nêu **cả hai** con số,
  không chọn cái đẹp hơn.
- `bars` (nến 5m) có 261 dòng OHLC = 0 (đã chặn tại nguồn ở đợt 109, chưa xóa) — **không liên quan** đợt này
  vì chỉ đọc `bars_daily`.

### 1.7 Phí
Không áp dụng — không có giao dịch nào. Báo cáo phải ghi rõ để không ai đọc nhầm đây là kết quả có phí.

---

## 2. Bất biến (như mọi brief)

KHÔNG commit, KHÔNG push, KHÔNG bật `real_trading_enabled`, KHÔNG sửa `config/`, KHÔNG TRUNCATE/DROP,
KHÔNG gọi API đặt lệnh SSI. Chỉ đọc dữ liệu. Ghi chú trong code: tiếng Việt không dấu.

---

## 3. Test (TDD — viết test TRƯỚC, dữ liệu dựng tay, không chạm DB)

Tám ca, tất cả dùng chuỗi tổng hợp có `seed` cố định (không dùng `random` trần):

1. **Hai chuỗi giống hệt** → Pearson = 1,0 (dung sai 1e-12), và với ba chuỗi giống hệt → λ = (3,0,0) ⇒ **PR = 1,0**.
2. **Ba chuỗi độc lập** (seed cố định, 2.000 phiên) → |ρ̄| < 0,10 và **PR ≥ 2,5**.
3. **Ma trận biết trước**: hai chuỗi giống nhau + một chuỗi độc lập → λ ≈ (2, 1, 0) ⇒ **PR ≈ 1,8** (dung sai 0,05).
4. **Bẫy giá-vs-lợi-suất**: hàm tính tương quan phải nhận **lợi suất**. Test này ghim hợp đồng: nếu ai đó truyền
   giá vào, chuỗi "độc lập" ở ca 2 vẫn ra ρ ≈ 0,9 ⇒ ca 2 phải đỏ. (Đây cũng là phép phá (i) ở §4.)
5. **Lệch ngày**: dịch một chuỗi đúng **1 phiên** → |ρ| giảm rõ (test ghim việc ghép theo NGÀY, không theo chỉ số).
   Dữ liệu dựng phải có ít nhất 2 mã và **nhiều hơn 1 phiên ở đuôi** để phép dịch có nghĩa.
6. **Phiên thiếu**: dữ liệu có lỗ (mỗi mã thiếu ngày khác nhau) → số phiên dùng được = số ngày **cả ba cùng có**,
   và hàm không được nội suy, không forward-fill.
7. **Cổng niêm phong**: gọi đường đọc với nến ≥ 2023-01-01 → **ném lỗi** (không được lặng lẽ đọc).
8. **PR đúng công thức**: ma trận đơn vị 3×3 (ba chuỗi trực giao) → **PR = 3,0** (kiểm trần), và PR bất biến
   khi đảo thứ tự mã.

---

## 4. Bốn phép phá bắt buộc (sao lưu ra NGOÀI repo, `cp` khôi phục, so `sha256`)

| Phép phá | Test phải đỏ |
|---|---|
| (i) tính tương quan trên **GIÁ** thay vì lợi suất | ca 2 (ba chuỗi độc lập) |
| (ii) ghép theo **chỉ số** mảng thay vì theo ngày | ca 5 (lệch ngày) |
| (iii) PR tính bằng công thức sai `Σλ² / Σλ` | ca 8 (ma trận đơn vị) |
| (iv) tháo cổng niêm phong | ca 7 (niêm phong) |

Yêu cầu: mỗi phép phá phải nằm trên **đúng hàm mà test gọi**, phải làm **đúng** test đã nêu đỏ, và sau khi
khôi phục phải xanh lại + file y nguyên từng byte. Script phá hoại ở scratch, không nằm trong repo.

---

## 5. Cổng kiểm cuối

- `uv run ruff check trading tests scripts` → sạch.
- `uv run pytest -m "not integration"` **TRƯỚC** (bản sao nguyên vẹn `HEAD` dựng ngoài repo bằng
  `git archive HEAD`) và **SAU** — hai con số thật, không suy ra.
- `uv run pytest tests/test_scripts_convention.py` xanh; `uv run python scripts/measure_basket_correlation.py --help`
  chạy được **từ thư mục gốc repo** (bootstrap `sys.path`).
- `node .gitnexus/run.cjs detect-changes --scope all --repo .` — lưu ý: file MỚI chưa theo dõi ⇒
  "No changes detected" nghĩa là "không có gì để thấy", **không phải** "không đổi".

---

## 6. Sản phẩm

- `scripts/measure_basket_correlation.py` (mới, chỉ đọc).
- `tests/test_measure_basket_correlation.py` (mới, 8 ca).
- `docs/superpowers/research/2026-10-10-dot-180-ma-tran-tuong-quan.md` — phải có: output **nguyên văn**,
  dự đoán trước ở §1.4, bảng bốn phép phá, hai con số pytest TRƯỚC/SAU, và mục **"brief mơ hồ ở đâu"**.
- Báo cáo phải kết bằng câu chốt phạm vi: *phép đo này KHÔNG thay đổi rổ mã, KHÔNG thay đổi định cỡ rủi ro,
  KHÔNG mở đường tới vốn thật; nếu số liệu cho thấy tập trung thì việc sửa là brief riêng (§7).*
- Không ghi `docs/holdout-unlock-log.md` trừ khi Claude cho phép cửa sổ B và giao việc ghi.
- Báo cáo cũng phải có câu: *"Tôi không đọc nến nào từ 01/01/2023"* **hoặc** ghi rõ cửa sổ B đã được Claude
  cho phép kèm số dòng log.

---

## 7. Hai điểm cần Claude quyết TRƯỚC khi agent chạy

**(a) Phép đo này có tính vào ngân sách mục F không?** Tôi cho là **không** (mô tả rủi ro, không phải giả
thuyết chiến lược — lý do ở đầu brief). Nếu Claude cho là có, xin chặn; tháng 10 đã 7/3.

**(b) Có cho phép cửa sổ phụ B (2023-01-01 → nay) không?** Nếu không, đợt này chỉ chạy cửa sổ A (2017–2022)
và báo cáo phải nói rõ: "tương quan 2017–2022, KHÔNG phải tương quan của rổ hôm nay". Đó là một hạn chế thật,
không được lấp.

**Nếu (sau này) số liệu cho thấy tập trung, ba hướng sửa — mỗi hướng một brief riêng, KHÔNG tự làm:**
1. Giới hạn số vị thế mỗi cụm tương quan (thêm một trần vào `risk.py`, cạnh `max_positions`).
2. Định cỡ theo rủi ro **danh mục** thay vì từng lệnh (risk parity / HRP — cần cả ma trận hiệp phương sai,
   không chỉ ma trận tương quan).
3. Chọn rổ theo **cả** thanh khoản **và** tương quan (đụng vào `config.symbols` ⇒ có GUARD-3, và là thay đổi
   hành vi hệ thống thật ⇒ phải diễn tập paper trước).

Mọi hướng trong ba hướng này thay đổi hành vi hệ thống đang chạy ⇒ không nằm trong quyền của brief này.

---

## 8. Claude duyệt (10/10/2026) — các mục dưới đây THAY THẾ chỗ mâu thuẫn ở trên

Claude đã kiểm các căn cứ:
- `config/config.yaml:6` `symbols: [HPG, IJC, AAA]`;
- `trading/risk.py:12-16`: `max_positions` 5, `max_order_value_pct` 0,20, `max_daily_loss_pct` 0,03, `risk_pct` 0,01, `atr_multiplier` 2,0;
- không có mã tương quan nào trong `trading/`;
- cả ba mã có trong `bars_daily` 2016-01 → 2026-10-08 và không nằm trong `exclusions.txt`;
- **`VNINDEX` KHÔNG có trong `bars_daily`**, nên mốc ở §1.3(5) dùng lợi suất mua đều toàn thị trường.

**§7(a) Ngân sách F:** đồng ý **không tính**. Đây là phép mô tả rủi ro, không chọn luật, không có p-value cho chiến lược.

**§7(b) Cửa sổ B:** **cho phép.** Câu hỏi là rủi ro của rổ hôm nay, và phép đo không chọn hay chỉnh luật nào. Claude đã ghi dòng mở niêm phong vào `docs/holdout-unlock-log.md` trước khi agent chạy. Agent **không** ghi log.
- Cửa sổ A đọc bằng `read_bars` (có cổng niêm phong).
- Cửa sổ B đọc bằng `storage.read_daily_bars(sym, 2023-01-01, 2026-10-01)` rồi `clean_bars`, trong **một hàm riêng tên rõ ràng** (`read_bars_window_b`). Không sửa hay tháo `read_bars`.
- Báo cáo in A và B riêng, không gộp.

**Sửa §3 ca 4 và phép phá (i):** hai random walk độc lập **không** chắc cho ρ ≈ 0,9 trên giá; dấu và độ lớn là ngẫu nhiên theo seed, nên phép phá (i) có thể không làm đỏ test. Thay bằng:
- dựng ba chuỗi giá `100·exp(0,002·t + nhiễu độc lập)` với seed cố định, 2.000 phiên. Tương quan lợi suất phải có |ρ̄| < 0,10; tương quan trên giá thì gần 1 vì cùng xu hướng;
- ca 4 assert `|ρ̄| < 0,10` trên chuỗi này;
- phép phá (i) (dùng giá thay lợi suất) phải làm **ca 4** đỏ.

**Thay §1.3(6):** "ba lệnh 1% cùng chạm dừng lỗ = 3%" đúng bằng ngưỡng **theo cấu tạo**, nên không cho thông tin gì. Thay bằng phép mô tả sau:
- mỗi phiên d, tỷ trọng mã i: `w_i = min(risk_pct / (atr_multiplier · ATR20_i[d−1] / close_i[d−1]), max_order_value_pct)`. ATR20 là trung bình true range 20 phiên kết thúc tại d−1; tham số import từ `RiskManager`, không gõ lại;
- lỗ rổ phiên d = `−Σ w_i · (close_i[d]/close_i[d−1] − 1)`, giả định cả ba cùng đang mở;
- in max, phân vị 99%, số phiên lỗ rổ > `max_daily_loss_pct`. Đây là số mô tả, không phải mô phỏng giao dịch, không có phí;
- thêm ca test 9: `w_i` và lỗ rổ trên nến dựng tay khớp số tính tay (sai số 1e-9).

**§1.6:** bỏ con số "51 chia tách / 49 mã" (chưa kiểm). Giữ quy tắc: đếm phiên `|log ret| > 0,5` của ba mã, in cả bản gốc và bản đã loại các phiên đó.

**§5:** bỏ yêu cầu dựng bản sao bằng `git archive`. Chạy `uv run pytest -m "not integration" -q` một lần trước khi tạo file và một lần sau, dán hai con số.

**GitNexus:** chỉ dùng `gitnexus ...` hoặc `node .gitnexus/run.cjs ...`, **không `npx`**.
