# Brief đợt 182 — Order flow VN30F theo footprint (ĐĂNG KÝ TRƯỚC; dựng công cụ trên dữ liệu tổng hợp, đo tháng 12)

> **Sửa 11/10/2026 (đợt 185, commit `3c19786`):** IS/holdout không còn theo mốc ngày 30/11 / 01/12. IS = 40 phiên hợp lệ đầu tiên kể từ 25/09 (theo quy tắc hợp lệ của công cụ này), holdout = các phiên sau phiên hợp lệ thứ 40. Công cụ trả 2 khi chưa đủ 40. Mọi tiêu chí khác giữ nguyên. Xem brief đợt 185 và spec H.

Ngày: 11/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. Làm theo khuôn của đợt 162/163.

## 0. Yêu cầu, những gì Claude kiểm được, và cách hiểu

**Chủ dự án (11/10)** gửi link danh sách phát YouTube "tổng hợp về order flow" và yêu cầu triển khai.
- Danh sách phát **ở chế độ riêng tư**: YouTube trả về "The playlist does not exist".
- Claude chỉ đọc được tên video mở đầu: *"Master ORDER FLOW TRADING in Less than ONE HOUR!"* (kênh Fractal Flow – Pro Trading Strategies). Claude **không xem được nội dung**.
- Bản v1 của brief vì vậy dùng ba khái niệm order flow kinh điển.

**Bản v2 (11/10, cùng ngày, TRƯỚC khi agent viết dòng code nào và trước khi ai mở dữ liệu):** chủ dự án gửi bản tóm tắt nội dung video (`order_flow_trading_guide.md`, file ngoài repo). Claude đối chiếu và sửa §1.3 cho khớp video:

| Video nói | v1 | v2 |
|---|---|---|
| §5.2: phân kỳ CVD — giá đỉnh cao hơn, CVD đỉnh thấp hơn (cạn kiệt mua), và đối xứng | E1 | **Giữ E1.** Chỉ làm dạng "cạn kiệt"; dạng "hấp thụ" trên CVD (giá đỉnh thấp hơn, CVD đỉnh cao hơn) không đưa vào để giữ 6 cặp |
| §6.2: nến giảm mà delta dương ⇒ người bán bị hấp thụ ⇒ **tăng**; ví dụ Dow Jones đi đúng chiều này | E2 làm **ngược chiều** (delta > 0, nến giảm ⇒ bán) | **E2 đảo chiều theo video**: d = dấu của delta. Giữ ngưỡng \|delta\| ≥ p90 của 5 phiên trước để loại nến delta lặt vặt |
| §6.1: bộ đôi đảo chiều — nến t−1 **hấp thụ** (đóng cửa phía sau imbalance), nến t **khởi xướng** chiều ngược lại; imbalance chéo 3:1 | E3 chỉ là "≥ 3 mức imbalance liên tiếp", không xét giá đóng cửa | **E3 thay bằng bộ đôi hấp thụ → khởi xướng** của video |

Phần video **không** đưa vào, kèm lý do:
- **Đọc DOM / sổ lệnh chờ:** chính video khuyên không dùng (spoofing, iceberg). Mất cân bằng sổ lệnh top1/top5 đã nằm trong đợt 162.
- **Ngữ cảnh "tại ngưỡng cản"** (POC, Value Area, trendline, pitchfork): video không cho quy tắc định lượng. Chọn tham số cho nó là tự bịa, và lọc thêm sẽ không đủ 100 sự kiện trong ~40 phiên. Hệ quả: kết quả âm ở đây **không** bác được phiên bản có ngữ cảnh. Phiên bản đó, nếu muốn, là một giả thuyết riêng.
- **Khung 1 giờ** như ví dụ E-mini: VN30F chỉ có 4 nến 1 giờ mỗi phiên, không thể đủ mẫu. Dùng nến 5 phút.
- **Lưu ý nguồn:** bản tóm tắt là tài liệu thứ cấp, Claude không xem được video để đối chiếu. Chiều của E2 dựa vào §6.2 và ví dụ 2 của bản tóm tắt.

**Dữ liệu có thật (Claude đã kiểm 11/10, chỉ đếm, không tính mục tiêu nào):**
- **Nguồn:** máy ghi sổ lệnh VN30F (`scripts/record_vn30f_orderbook.py`, tự chuyển sang hợp đồng tháng gần nhất), lưu tại `data/orderbook/<mã>/<ngày>.jsonl.gz`.
- **Tin khớp lệnh (`TRADE`)** có `trading_time` (theo giây), `price`, `quantity` và `side` ∈ {B, S, U}. B/S là **bên chủ động**, đúng thứ order flow cần. Phiên 25/09 có 1.394 tin `U`, khối lượng 0, là tin chỉ báo. Các phiên khác gần như chỉ có B/S, khoảng 87–127 nghìn tin khớp mỗi phiên.
- **Số phiên dùng được tới 09/10: 9.**
  - 29/09: file bị cắt cụt (máy ghi chết).
  - 01/10: không có file (`orderbook-recorder SKIP: docker chua chay`).
- **Cổ phiếu không làm được order flow:** collector chỉ lưu nến OHLCV, không lưu từng lệnh khớp. Đợt này chỉ làm VN30F.

**Đã có gì trong repo (không làm lại):**
- **Đợt 162 (đã đăng ký, chờ tháng 12)** đã có OFI = Σ(khối lượng B) − Σ(khối lượng S) theo phút, cùng mất cân bằng top1/top5 của sổ lệnh, ở các chân trời 1/5/15 phút. **Delta theo phút chính là OFI của 162**, nên đợt này **không** đo lại delta trần.
- **Đợt 105:** order flow trên BTC perp 1h là âm.

**Ba sự kiện order flow MỚI (không trùng 162):** phân kỳ CVD, phân kỳ delta trong nến, bộ đôi hấp thụ → khởi xướng trên footprint. Ba sự kiện này được đo trên **cùng tập IS và holdout của 162**.

**Ngân sách mục F:** đây là giả thuyết thứ 9 của tháng 10. Claude ghi dòng spec H **trước** khi giao. Kết quả mang cảnh báo đa so sánh. Lời giải thích quan trọng nhất: cùng dữ liệu với 162 nghĩa là tổng số cặp được thử trên tập này là 9 + 6 = 15.

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu, phiên, niêm phong
- **Tập IS:** phiên 2026-09-25 → 2026-11-30. **Holdout:** từ 2026-12-01. Giống hệt hằng của `scripts/screen_vn30f_orderbook.py`: **import** các hằng đó, không gõ lại.
- **Phiên hợp lệ:** file giải nén đọc hết, không `EOFError`, và ≥ 90% số nến 5 phút trong khung liên tục có ít nhất một tin khớp. Cần **≥ 40 phiên IS hợp lệ** (`MIN_IS_SESSIONS` của 162). Thiếu thì công cụ in "KHÔNG ĐỦ PHIÊN" và dừng, **không nới**.
- **Khung liên tục:** 09:00–11:30 và 13:00–14:30, giờ của sàn theo `trading_time`, **không** theo `recv_ts`. Bỏ 14:30–14:45 (ATC) và mọi tin ngoài khung, nhưng đếm riêng. Dùng lại `MORNING_START`, `MORNING_END`, `AFTERNOON_START` của máy ghi và `CONTINUOUS_AFTERNOON_END` của `build_orderbook_features.py`.
- **Tin dùng:** `classify_message(msg) == "TRADE"`, `side` ∈ {B, S}, `quantity > 0`. Tin `U` hoặc khối lượng 0 bị loại và **đếm, in ra**.
- **Cổng ngày:** công cụ **từ chối chạy phần đo** khi ngày hôm nay (giờ VN) < 2026-12-01, giống cổng của 162. Phải từ chối **trước khi mở bất kỳ file nào**.
- **Holdout:** mở tối đa **một** cặp, theo đúng ba điều kiện của 162: cặp thuộc 6 cặp ở §1.3, cặp ĐẠT ở IS, và có ≥ 30 phiên holdout hợp lệ. Phải ghi `docs/holdout-unlock-log.md` **trước** khi đọc file holdout. Holdout của 162 và 182 là hai lần mở **riêng**, mỗi lần một dòng log.

### 1.2 Nến footprint 5 phút (mỗi phiên 48 nến: 30 sáng + 18 chiều)
Với mỗi nến:
- `open/high/low/close` = giá của tin khớp đầu, cao nhất, thấp nhất, cuối trong nến (thứ tự theo `trading_time`, rồi đến thứ tự trong file);
- `buy` = Σ khối lượng B, `sell` = Σ khối lượng S, `delta = buy − sell`;
- `fp[p] = (buy_p, sell_p)` tại từng mức giá p. Bước giá VN30F là **0,1 điểm**; mức giá được làm tròn về bội số 0,1 bằng số nguyên `round(p*10)`, không dùng so sánh float;
- `cvd` = delta cộng dồn từ nến đầu phiên. **Mỗi phiên reset về 0.**

Nến không có tin khớp: giữ ô với `buy = sell = 0`, giá là None, và **không sinh sự kiện**.

### 1.3 Ba sự kiện × hai chân trời = 6 cặp (chốt trước)
Mỗi sự kiện có hướng d ∈ {+1 mua, −1 bán} và được xét **tại cuối nến t**.

| Mã | Sự kiện | Định nghĩa |
|---|---|---|
| E1 | **Phân kỳ CVD** | Bán (d = −1): `close_t` **lớn hơn hẳn** mọi `close` của 11 nến trước **trong cùng phiên** (cần đủ 11 nến có giá), **và** `cvd_t` **nhỏ hơn** max `cvd` của 11 nến đó. Mua (d = +1): đối xứng (close thấp hơn hẳn, cvd lớn hơn min). |
| E2 | **Phân kỳ delta trong nến** (video §6.2) | `|delta_t|` ≥ phân vị 90% của `|delta|` mọi nến có giao dịch trong **5 phiên hợp lệ liền trước** (không gồm phiên hiện tại; phiên chưa đủ 5 phiên trước thì không xét). `delta_t > 0` và `close_t < open_t` (**nhỏ hơn hẳn**) ⇒ **mua**, d = +1 (bên bán bị hấp thụ). `delta_t < 0` và `close_t > open_t` ⇒ **bán**, d = −1. Tức **d = dấu của delta**. `close_t = open_t` ⇒ không có sự kiện. |
| E3 | **Bộ đôi hấp thụ → khởi xướng** (video §6.1) | Xem định nghĩa imbalance và quy tắc bên dưới bảng. |

**Imbalance chéo trong một nến** (k = `round(p*10)`, tức mức giá theo bước 0,1):
- **Ask imbalance** tại k: `buy[k] ≥ 3 × max(sell[k−1], 1)` **và** `buy[k] ≥ 5`.
- **Bid imbalance** tại k: `sell[k] ≥ 3 × max(buy[k+1], 1)` **và** `sell[k] ≥ 5`.
- So **chéo** (mua ở p với bán ở p − 0,1; bán ở p với mua ở p + 0,1), **không** so cùng mức. Mức không có giao dịch tính là 0.

**Trạng thái của một nến** (cần ít nhất một imbalance cùng phía):
- **Hấp thụ mua** (bên mua bị hấp thụ): có ask imbalance, và `close < giá ask imbalance THẤP nhất` (nhỏ hơn hẳn).
- **Hấp thụ bán**: có bid imbalance, và `close > giá bid imbalance CAO nhất` (lớn hơn hẳn).
- **Khởi xướng mua:** có ask imbalance, `close ≥ giá ask imbalance CAO nhất`, và nến **không** có bid imbalance nào.
- **Khởi xướng bán:** có bid imbalance, `close ≤ giá bid imbalance THẤP nhất`, và nến **không** có ask imbalance nào.
- Khởi xướng dùng `≥`/`≤` vì imbalance thường nằm đúng ở đỉnh/đáy nến, nơi giá đóng cửa trùng mức đó.

**Sự kiện E3, xét tại cuối nến t:**
- Nến t−1 **hấp thụ bán** và nến t **khởi xướng mua** ⇒ d = +1.
- Nến t−1 **hấp thụ mua** và nến t **khởi xướng bán** ⇒ d = −1.
- t−1 và t phải là hai nến 5 phút **liền nhau trong cùng một khung liên tục**: không ghép 11:25 với 13:00, không ghép qua phiên. Cả hai nến phải có giao dịch.
- Hai chiều loại trừ nhau theo định nghĩa: khởi xướng mua cấm bid imbalance, khởi xướng bán lại cần nó.

**Mục tiêu:** `y = d × (P(t_end + H) − close_t)`, tính bằng điểm, H ∈ {15, 30} phút.
- `t_end` là mốc kết thúc nến t. `P(x)` là giá tin khớp cuối cùng có `trading_time ≤ x`.
- Bỏ sự kiện nếu `t_end + H` vượt quá kết thúc khung đang chứa nó (11:30 hoặc 14:30). Không vắt qua nghỉ trưa, không qua đêm.

**Không chồng lấn:** trong cùng một cặp (sự kiện, H), sự kiện mới chỉ được nhận khi `t_end` ≥ `t_end` của sự kiện được nhận trước + H. Hai hướng dùng chung đồng hồ này.

### 1.4 Thống kê và cổng ĐẠT ở IS (cho từng cặp)
1. **Đủ mẫu:** ≥ 100 sự kiện độc lập (`MIN_INDEP_EVENTS`), mỗi hướng ≥ 30 (`MIN_SIDE_EVENTS`).
2. **Có ý nghĩa thống kê:** p một phía < **0,05/6 = 0,00833**.
   - Bootstrap theo **khối phiên**: lấy lại các phiên có hoàn lại, 2.000 lần, `numpy.random.default_rng(42)`.
   - Thống kê là trung bình y trên mọi sự kiện của các phiên được lấy. Bootstrap trên y đã trừ trung bình.
   - p = tỷ lệ trung bình bootstrap ≥ trung bình quan sát.
3. **Đủ bù chi phí:** trung bình y ≥ **1,5 × (chi phí hai chiều + 0,2 điểm)**.
   - Chi phí hai chiều dùng `compute_roundtrip_cost(giá trung vị close của IS)` import từ `scripts/screen_vn30f_orderbook.py`.
   - 0,2 điểm là trượt giá: một bước giá mỗi chiều, vì order flow vào và ra bằng lệnh thị trường. **Đợt này chặt hơn 162 ở điểm này, có chủ ý.**
4. **Kiểm đối chứng trước khi đo (không chạm tương lai):** Spearman ρ giữa `delta_t` và `close_t − open_t` **cùng nến** trên IS phải > 0,3 (`CONTROL_MIN_RHO`). Không đạt nghĩa là `side` không phải bên chủ động, nên công cụ in "DỮ LIỆU SIDE KHÔNG ĐÁNG TIN" và dừng.

Một cặp **ĐẠT** khi đủ 1 + 2 + 3.

**Tiêu chí holdout.** Brief v1/v2 bỏ sót mục này. Claude bổ sung ngày 11/10 khi audit 182b, trước khi ai mở dữ liệu.
- **Cách tính:** cặp duy nhất được mở ĐẠT holdout khi p một phía **< 0,05** (không chia 6, vì chỉ mở một cặp) **và** trung bình y ≥ hurdle của IS. Đây là tiêu chí của đợt 162.
- **Không đòi ≥ 100 sự kiện:** khoảng 30 phiên không thể đủ số đó. Nếu đòi, holdout sẽ trượt vì thiếu mẫu chứ không phải vì không có lợi thế.
- **Ngưỡng E2:** ở 5 phiên holdout đầu, ngưỡng E2 lấy từ 5 phiên IS cuối. Đó vẫn là quá khứ. Kết quả tốt nhất có thể là: một cặp được mở holdout. **Không có đường tới lệnh thật**: giao dịch phái sinh thật cần quyết định riêng của chủ dự án và một brief riêng.

### 1.5 Dự đoán của Claude (ghi trước)
Không cặp nào đạt điều kiện 3. Nếu có cặp đạt điều kiện 2, nhiều khả năng là E1 hoặc E2 ở H = 15, và biên độ nhỏ hơn chi phí cộng trượt giá. E3 có nguy cơ **không đủ 100 sự kiện**; khi đó công cụ báo "KHÔNG ĐỦ MẪU" cho E3, không nới định nghĩa.

**Không đảo chiều sau khi thấy số.** Nếu trung bình y của một cặp âm rõ, tức chiều ngược với video mới đúng, thì công cụ chỉ in số đó để **mô tả**. Cặp đó không thành ĐẠT, và chiều ngược lại là một giả thuyết mới, cần dòng spec H riêng.

## 2. Việc agent làm BÂY GIỜ (11/10): dựng công cụ và test trên dữ liệu tổng hợp, KHÔNG đo

- **Mới:** `scripts/screen_vn30f_orderflow.py` gồm:
  - hàm thuần cho §1.2–§1.4 (dựng nến footprint, CVD, ba bộ phát hiện sự kiện, mục tiêu, lọc không chồng lấn, bootstrap, cổng);
  - `main()` có cổng ngày §1.1. Cổng hoạt động như sau: đọc ngày hôm nay qua một tham số tiêm được (mặc định `datetime.now(TZ).date()`); nếu ngày < 2026-12-01 thì in thông báo và `return 2` **trước** khi liệt kê hay mở file.
- **Tách hàm để đợt 183 (crypto) dùng lại nguyên văn** (thêm 11/10). Hai lớp:
  1. `imbalance_levels(fp, ratio=3, min_vol=5, denom_floor=1)` → `(ask_ks, bid_ks)`, với k là chỉ số mức giá nguyên.
  2. Bộ phát hiện E1/E2/E3, hàm mục tiêu và lọc chồng lấn chỉ nhận **danh sách nến tóm tắt**: `session_id`, `block_id`, `t_end`, open/high/low/close, `close_k`, delta, cvd, `ask_k_min/max`, `bid_k_min/max`. Chúng **không** đọc `fp` trực tiếp.
  - `session_id` là phiên (CVD reset, cửa sổ E1, ngưỡng E2, khối bootstrap). `block_id` là khung liên tục (E3 liền nhau, mục tiêu không vắt qua).
  - Với VN30F: phiên = ngày, khung = sáng/chiều. Mặc định của tham số là giá trị VN30F; hành vi ở §1 không đổi.
- **Mới:** `tests/test_screen_vn30f_orderflow.py`.
- **Import, không sửa:**
  - `scripts/build_orderbook_features.py`: `iter_file_messages`, `session_date_from_filename`, `parse_trading_time`, `CONTINUOUS_AFTERNOON_END`;
  - `scripts/record_vn30f_orderbook.py`: `classify_message`, hằng khung phiên;
  - `scripts/screen_vn30f_orderbook.py`: hằng ngày IS/holdout, `MIN_*`, `ECONOMIC_HURDLE_FACTOR`, `CONTROL_MIN_RHO`, `compute_roundtrip_cost`.
- **Không sửa bất kỳ file nào khác.** Không chạm `data/orderbook/`: **không mở, không liệt kê, không đếm file thật**. Không ghi `docs/holdout-unlock-log.md`.
- Ghi chú trong code: tiếng Việt không dấu.

**Giới hạn rõ ràng:** công cụ này **không** chạy trên dữ liệu thật trước 01/12. Agent **không** được tạm tắt cổng ngày để "thử cho biết".

## 3. Test (TDD, chỉ dữ liệu dựng tay hoặc seed cố định)

1. **Dựng nến:** một danh sách tin tay có các trường hợp sau:
   - tin B/S ở nhiều mức giá;
   - một tin `U` và một tin khối lượng 0;
   - một tin lúc 14:35 (ATC);
   - một tin có `recv_ts` rơi sang nến sau nhưng `trading_time` thuộc nến trước.

   Assert đủ các điểm sau: buy/sell/delta/OHLC từng nến khớp số tính tay; `fp` đúng ở từng mức; tin `U`/khối lượng 0/ATC bị loại và được đếm đúng; tin xếp theo `trading_time`.
2. **CVD reset:** hai phiên liền nhau, CVD nến đầu phiên 2 = delta của chính nến đó.
3. **E1:**
   - chuỗi dựng sẵn kích hoạt **đúng** ở nến dự kiến;
   - close **bằng** max 11 nến trước thì **không** kích hoạt (so sánh nghiêm ngặt);
   - nến thứ 11 của phiên (chưa đủ 11 nến trước) thì không kích hoạt;
   - không dùng nến của phiên trước.
4. **E2:**
   - ngưỡng chỉ lấy từ 5 phiên trước;
   - thêm một nến |delta| khổng lồ **sau** nến t trong cùng phiên thì ngưỡng của t **không đổi**;
   - phiên thứ 5 (chỉ có 4 phiên trước) không sinh sự kiện;
   - **chiều:** nến giảm có delta dương lớn ⇒ d = **+1**; nến tăng có delta âm lớn ⇒ d = **−1**;
   - `close = open` với |delta| lớn ⇒ không có sự kiện.
5. **Imbalance và E3:**
   - **bẫy cùng mức:** dựng nến mà so cùng mức thì có ask imbalance, nhưng so chéo thì không ⇒ không có imbalance;
   - `buy[k] = 4` (dưới sàn 5) ⇒ không có imbalance;
   - giá 1935,3 và 1935,4 được coi là liền kề (kiểm làm tròn số nguyên);
   - **bộ đôi mua đúng:** nến t−1 hấp thụ bán, nến t khởi xướng mua ⇒ đúng một sự kiện d = +1 tại cuối nến t. Ca đối xứng cho d = −1;
   - nến t có thêm một bid imbalance ⇒ không còn khởi xướng mua ⇒ không có sự kiện;
   - `close_{t−1}` **bằng** giá bid imbalance cao nhất ⇒ không phải hấp thụ (so sánh nghiêm ngặt) ⇒ không có sự kiện;
   - `close_t` **bằng** giá ask imbalance cao nhất ⇒ vẫn là khởi xướng ⇒ có sự kiện;
   - t−1 là nến 11:25 và t là nến 13:00 ⇒ không có sự kiện.
6. **Mục tiêu và chồng lấn:**
   - y đúng dấu theo d;
   - `P(x)` lấy tin cuối có `trading_time ≤ x`;
   - sự kiện lúc 11:20 với H = 15 bị bỏ;
   - hai sự kiện cách nhau < H thì chỉ nhận cái đầu.
7. **Cổng ngày:** today = 2026-11-30 ⇒ `main` trả 2, và hàm liệt kê/mở file (mock) **không được gọi lần nào**. today = 2026-12-01 ⇒ đi tiếp và gọi mock.
8. **Holdout:** gọi đường đọc holdout khi log chưa có dòng của đợt 182 ⇒ ném lỗi. Dùng file log tạm trong `tmp_path`, **không** đụng log thật.
9. **Ngưỡng chi phí:** tại giá 1.900, hurdle = 1,5 × (`compute_roundtrip_cost(1900)` + 0,2), sai số 1e-12.
10. **Cổng §1.4:** ca biên cho từng điều kiện, mỗi ca chỉ trượt đúng một:
    - 99 sự kiện;
    - một hướng chỉ có 29;
    - p = 0,00833… đúng bằng ngưỡng (phải trượt);
    - trung bình đúng bằng hurdle (phải đạt, vì điều kiện là ≥);
    - ρ đối chứng = 0,3 đúng bằng (phải dừng, vì điều kiện là > 0,3).
11. **Bootstrap:**
    - mọi y = +1 ⇒ p = 0;
    - y đối xứng ⇒ 0,3 < p < 0,7;
    - cùng seed cho cùng p;
    - lấy lại theo **phiên**, không theo sự kiện. Hàm bootstrap phải trả cả mảng trung bình bootstrap (`(p, means)`). Dựng 2 phiên: phiên A có 100 sự kiện y = +1, phiên B có 1 sự kiện y = −50.
      - Lấy lại theo phiên thì mỗi lần rút chỉ có ba tổ hợp {A,A}, {B,B}, {A,B}, nên `len(set(np.round(means, 9))) ≤ 3`.
      - Lấy lại theo sự kiện thì cho hàng chục giá trị khác nhau.

**Sáu phép phá bắt buộc.** Sao lưu file ra ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`. Mỗi phép phá phải làm đỏ đúng test nêu:

| Phép phá | Test phải đỏ |
|---|---|
| (i) gom nến theo `recv_ts` thay vì `trading_time` | ca 1 |
| (ii) imbalance so **cùng mức** thay vì chéo | ca 5 |
| (iii) ngưỡng E2 gồm cả phiên hiện tại | ca 4 |
| (iv) bỏ cổng ngày | ca 7 |
| (v) bootstrap lấy lại theo sự kiện thay vì theo phiên | ca 11 |
| (vi) E2 đảo về chiều của v1 (delta > 0 và nến giảm ⇒ bán) | ca 4 |

## 4. Cổng kiểm cuối
- **GitNexus** (chỉ `gitnexus ... -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs ...`, **không `npx`**):
  - trước khi viết: `impact` cho `iter_file_messages`, `classify_message` và `compute_roundtrip_cost`, chiều upstream. Báo mức rủi ro (chỉ import). `UNKNOWN` thì tự xác nhận bằng cách đọc file, không coi là an toàn;
  - sau khi viết: `detect-changes --scope all`. File mới chưa theo dõi nên "không thấy symbol" là bình thường; ghi rõ như vậy.
- `uv run pytest -m "not integration" -q` trước và sau: dán hai con số.
- `uv run pytest tests/test_screen_vn30f_orderflow.py tests/test_scripts_convention.py -v` xanh.
- `uv run ruff check trading tests scripts` sạch.
- `uv run python scripts/screen_vn30f_orderflow.py --help` chạy được từ gốc repo.
- `uv run python scripts/screen_vn30f_orderflow.py` hôm nay phải in thông báo cổng ngày và trả mã 2. Dán output.

## 5. Bất biến
- **Không:** commit, push, ghi DB, gọi API SSI, đặt lệnh.
- **Không chạy:** `scripts/sched.sh`, máy ghi sổ lệnh, `scripts/drill_place_cancel_order.py`.
- **Không đọc:** `.ssi_sdk_token.json`, `.env`, bất kỳ file nào trong `data/orderbook/`.

## 6. Báo cáo cho Claude
- Output pytest (trước/sau), ruff, `--help`, output cổng ngày.
- Bảng sáu phép phá, kết quả `impact` và `detect-changes`.
- Mục "brief mơ hồ ở đâu", và mọi chỗ agent phải tự diễn giải.
- Câu chốt: *"Tôi không mở file nào trong data/orderbook/. Công cụ chưa đo gì; phép đo thật chạy từ 01/12/2026 theo §1."*
