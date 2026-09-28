# Brief đợt 116 — Hoàn tất phép đo độ bám của forex perp BingX, và đo chi phí giữ vị thế

Ngày giao: 28/09/2026 (thứ Hai). Base: main `b9a5a04`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh, không sửa `trading/`**.

## 0. Vì sao đợt này làm được hôm nay mà Chủ nhật không làm được

Đợt 115 để hở đúng một chỗ: **không đo được độ bám của hai mã forex**, vì chạy vào Chủ nhật, lúc đó BingX gắn `status=25` cho toàn nhóm forex và cả hai endpoint klines và fundingRate đều trả `109415: is pause currently`.

Hôm nay là thứ Hai. Claude đã kiểm lúc 08:09 giờ VN, và ghi lại **bằng chứng** để agent không phải đoán:

| Kiểm tra | Kết quả Claude thấy lúc 08:09 ngày 28/09 |
|---|---|
| `GET /openApi/swap/v2/quote/contracts` | `NCFXEUR2USD-USDT` `status=1`, `NCFXUSD2JPY-USDT` `status=1`, `takerFeeRate=0.0005` cả hai |
| `GET /openApi/swap/v3/quote/klines?symbol=NCFXEUR2USD-USDT&interval=1d&limit=5` | `code=0`, có dữ liệu, nến mới nhất `time=1790553600000` |
| `GET /openApi/swap/v2/quote/fundingRate?symbol=NCFXEUR2USD-USDT&limit=5` | `code=0`, `fundingRate=0.00004`, các mốc cách nhau **28 800 000 ms = 8 giờ** |
| `bars_crypto` | **0 nến** cho cả hai mã forex, ở cả `1d` và `1h` |
| `bars_ext_daily` | ECB EURUSD 7 082 dòng (từ 1999-01-04); FRB_H10 EURUSD 6 937 dòng (từ 1999-01-04); FRB_H10 USDJPY 13 952 dòng (từ 1971-01-04) |

Nghĩa là: forex là **tài sản duy nhất** có cả hai điều kiện — lịch sử gốc dài và nguồn hợp điều khoản (xem `2026-09-27-dot-115-du-lieu-dai-han-tai-san-goc.md`). Vàng, S&P 500, NASDAQ 100 đều bị điều khoản chặn, nên đã bỏ.

**Đợt này vẫn CHƯA đo chiến lược.** Đợt này trả lời hai câu hỏi cổng:
1. Giá perp BingX có **bám** giá gốc không? Nếu không, 27 năm lịch sử EUR/USD là vô dụng với BingX.
2. Chi phí một vòng (phí taker + funding) **chiếm bao nhiêu phần** biên độ một ngày của forex? Nếu chi phí ăn hết biên độ, khỏi cần đo chiến lược.

Cả hai đều là phép đo, không phải phán xét. **Không kết luận "đáng giao dịch" hay "có lợi nhuận".**

## 1. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/bingx_klines.py` | **Chỉ chạy**, không sửa. Hỏng với mã NCFX thì **dừng và báo**, không tự sửa. |
| `scripts/check_bingx_tracking.py` | **Chỉ chạy**, không sửa. Script này đã có sẵn từ đợt 115, đã có `compare_date_alignments` so cả ba cách căn ngày `shift = 0, +1, −1`. Nếu phải sửa mới chạy được thì **dừng và báo**, Claude sửa. |
| `scripts/measure_forex_perp_cost.py` | **Mới.** Task B. Chỉ đọc DB và endpoint công khai không ký. |
| `tests/test_measure_forex_perp_cost.py` | **Mới.** |
| `docs/superpowers/research/2026-09-28-dot-116-do-bam-va-chi-phi-forex-perp.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `trading/` — kể cả một dòng;
- `bars`, `bars_daily`, `bars_ext_daily`: **chỉ đọc**;
- `bars_crypto`: chỉ được ghi **qua `bingx_klines.py`**, không viết SQL `INSERT`/`UPDATE`/`DELETE` thủ công;
- config, container, Task Scheduler, `.env`.

**Cấm gọi endpoint có ký. Cấm đặt/huỷ/sửa lệnh. Cấm in secret.**

**Niêm phong:** chỉ nạp và chỉ đọc dữ liệu **đến hết 2026-08-31**. Dữ liệu từ 2026-09-01 là holdout.

**Sao lưu ra ngoài repo trước khi sửa file. Cấm `git checkout`, `git restore`, `git stash`.**

---

## Task A — Nạp nến forex và đo độ bám

### A1. Nạp

```
uv run python scripts/bingx_klines.py --symbols NCFXEUR2USD-USDT,NCFXUSD2JPY-USDT --interval 1d --to 2026-08-31
uv run python scripts/bingx_klines.py --symbols NCFXEUR2USD-USDT,NCFXUSD2JPY-USDT --interval 1h --to 2026-08-31
```

→ **Kiểm chứng bằng:** dán nguyên văn output, rồi dán kết quả truy vấn:

```sql
SELECT symbol, interval, count(*), min(ts)::date, max(ts)::date
FROM bars_crypto WHERE symbol LIKE 'NCFX%' GROUP BY 1,2 ORDER BY 1,2;
```

**Kỳ vọng thô** (để đối chiếu, không phải để ép số): niêm yết 27–28/08/2025 đến 31/08/2026 là khoảng 12 tháng; forex nghỉ cuối tuần nên nến 1d nên vào khoảng **255–270**, không phải ~365. Nếu ra ~365 thì BingX đang vẽ nến cả cuối tuần — **ghi lại, đừng bỏ qua**.

Nếu một trong hai mã lại trả `109415` thì ghi lại giờ VN chính xác, mã lỗi nguyên văn, và **dừng mã đó**, làm tiếp mã còn lại.

### A2. Kiểm chất lượng nến vừa nạp

Với mỗi mã, mỗi khung, báo:
- số nến bẩn theo `trading.data_quality.is_dirty_bar` (chỉ **đọc** hàm, không sửa);
- số nến `volume = 0`;
- số ngày trùng lặp;
- khoảng trống dài nhất tính bằng giờ, và khoảng trống đó có rơi vào cuối tuần không.

→ **Kiểm chứng bằng:** bảng số liệu kèm câu lệnh SQL đã chạy.

### A3. Đo độ bám

```
uv run python scripts/check_bingx_tracking.py
```

→ **Kiểm chứng bằng:** dán **toàn bộ** output. Bảng chính phải có, cho mỗi cặp (tài sản × nguồn ngoài):

`Tài sản | Nguồn | Số ngày khớp | Basis trung vị | Basis P5–P95 | max |basis| | Tương quan lợi suất ngày | Tracking error năm | Số ngày |basis| > 1% | shift tốt nhất (0/+1/−1)`

Ba cặp phải có số thật: EUR/USD × FRB_H10, EUR/USD × ECB, USD/JPY × FRB_H10.

**Bắt buộc báo `shift` tốt nhất và tương quan của cả ba `shift`**, không chỉ cái tốt nhất. Lý do: giá gốc là fixing (H.10 chốt trưa New York, ECB chốt 14:15 CET) còn nến 1d BingX chốt 00:00 UTC, nên lệch một ngày là chuyện có thể xảy ra thật. Nếu `shift = +1` hoặc `−1` cho tương quan cao hơn `shift = 0`, **nói thẳng ra**, đừng chọn im lặng.

**Kiểm tra chéo bắt buộc — làm bằng tay, không dùng script:**
Chọn **3 ngày cụ thể** trong khoảng khớp (ghi rõ ngày). Với mỗi ngày, lấy tay `close` của BingX và `close` của FRB_H10 từ DB, tính `basis = a/b − 1` bằng máy tính tay, rồi so với số script in ra. Dán cả ba phép tính.
Đây là chốt chống lỗi ghép ngày lệch: script tự đo mình thì không phát hiện được.

### A4. Phân loại (chỉ phân loại, không kết luận)

Theo đúng ngưỡng brief 115, một tài sản được đánh dấu **"đủ để đo tiếp"** khi thoả **cả ba**:
- ≥ 10 năm dữ liệu gốc từ nguồn được phép;
- tương quan lợi suất ngày với BingX **≥ 0,95**;
- |basis| trung vị **≤ 0,5%**.

Ghi rõ đạt hay không đạt từng điều kiện, kèm số.

---

## Task B — Chi phí giữ vị thế forex perp

Đây là phần **viết code mới**, làm theo TDD: test trước, hàm thuần, ví dụ tính tay.

### B1. Dữ liệu cần lấy

1. **`takerFeeRate` và `makerFeeRate`** — từ `GET /openApi/swap/v2/quote/contracts`. **Lấy từ API, cấm đoán, cấm hằng số cứng.**
2. **Lịch sử funding** — từ `GET /openApi/swap/v2/quote/fundingRate?symbol={symbol}&limit=1000`. Endpoint này Claude đã xác nhận trả `code=0` cho `NCFXEUR2USD-USDT` lúc 08:09 hôm nay.
   Phân trang nếu endpoint hỗ trợ `startTime`/`endTime`; **kiểm tài liệu chính thức BingX và ghi URL tài liệu**, đừng đoán tên tham số. Nếu không phân trang được thì ghi rõ **lịch sử funding chỉ lùi được đến ngày nào** và **không ngoại suy** ra cả năm.
3. **Nến 1d** của hai mã (vừa nạp ở A1) và chuỗi gốc trong `bars_ext_daily`.

### B2. Các con số phải tính (hàm thuần, mỗi hàm một test có ví dụ tính tay)

Với mỗi mã forex perp:

| Chỉ số | Định nghĩa chính xác |
|---|---|
| Chu kỳ funding | Trung vị khoảng cách giữa các `fundingTime` liên tiếp, đổi ra giờ. Báo cả số mốc lệch khỏi trung vị. |
| Funding trung bình | Trung bình `fundingRate` (có dấu) và trung bình `|fundingRate|`, cả hai đổi ra **%/ngày** = rate × (24 / chu kỳ giờ). |
| Funding P5 / P95 | Theo %/ngày. |
| Phí một vòng taker | `2 × takerFeeRate`, tính bằng %. |
| Biên độ ngày của tài sản gốc | Trung vị `|lợi suất ngày|` của chuỗi gốc (`bars_ext_daily`), trên **toàn bộ** lịch sử được phép, tính bằng %. Đây là mẫu số. |
| Biên độ ngày của perp BingX | Cùng phép đo, trên nến 1d BingX, chỉ trên khoảng BingX có dữ liệu. Báo riêng để so với dòng trên. |
| **phí vòng / biên độ ngày gốc** | Tỷ lệ %. |
| **chi phí giữ H ngày / biên độ ngày gốc** | Với `H = 1, 3, 5, 10` ngày: `(2 × takerFeeRate + H × funding_trung_bình_tuyệt_đối_theo_ngày) / biên_độ_ngày`. Đây là con số quan trọng nhất của Task B. |

Thêm một bảng **ATR14 của nến 1d**, tính theo % giá, cho hai mã BingX, để so với trung vị `|lợi suất ngày|`. Nếu hai số này lệch nhau quá 2 lần thì ghi lại, có thể là dấu hiệu nến cuối tuần hoặc nến bẩn.

**Hướng dấu của funding phải nói rõ:** `fundingRate > 0` nghĩa là bên Long trả bên Short. Trong bảng chi phí ở trên dùng **trị tuyệt đối**, vì chiến lược có thể vào cả hai chiều; nhưng phải báo **riêng** funding có dấu, để biết một chiều được trả tiền và chiều kia phải trả.

### B3. Test và phá thử

- Test cho từng hàm thuần ở B2, mỗi hàm một ví dụ **tính tay ghi rõ trong docstring hoặc comment của test**.
- **Ba phép phá thử bắt buộc**, mỗi phép phải làm ít nhất một test **đỏ**. Dán output đỏ của cả ba:
  1. Đổi quy đổi funding sang %/ngày từ `× (24/chu_kỳ)` thành `× chu_kỳ` → test phải đỏ.
  2. Đổi phí một vòng từ `2 × taker` thành `1 × taker` → test phải đỏ.
  3. Đổi trung vị `|lợi suất ngày|` thành trung bình có dấu (gần 0 với forex) → test phải đỏ.
- Nếu một phép phá thử mà test vẫn xanh: **test đó yếu**, phải siết test rồi phá lại. Ghi lại cả lần yếu và lần đã siết. Không được lặng lẽ sửa.

→ **Kiểm chứng bằng:**
```
uv run pytest tests/test_measure_forex_perp_cost.py -v
uv run ruff check trading tests scripts/measure_forex_perp_cost.py
```
Dán nguyên văn cả hai.

### B4. Cấm hằng số vô nguồn

Mọi con số về phí, chu kỳ funding, bước giá, khối lượng tối thiểu phải đến từ **API hoặc tài liệu chính thức**, kèm URL trong báo cáo. Đây là lỗi đã xảy ra nhiều lần trong dự án này: `FEE_RATE` từng là hằng số vô nguồn và phá cả hai cổng go-live. Nếu API không trả trường nào thì viết "**không có, chưa xác minh**" — **tuyệt đối không mặc định về 0 hay về một giá trị "an toàn"**. Thiếu trường thì **raise lỗi**, đừng `.get(key, 0)`.

---

## 2. Báo cáo cho Claude

Theo thứ tự:

1. **Kết luận ba dòng, không hơn:**
   - dòng 1: EUR/USD đạt/không đạt ba ngưỡng ở A4, kèm ba con số;
   - dòng 2: USD/JPY tương tự;
   - dòng 3: chi phí giữ 5 ngày chiếm bao nhiêu % biên độ một ngày, cho mỗi mã.
2. Output Task A nguyên văn: A1, A2, A3, kèm ba phép tính tay ở A3.
3. Bảng Task B, kèm URL tài liệu cho từng hằng số.
4. Output pytest và ruff, kèm ba lần phá thử.
5. **Mọi điều bất thường**, kể cả cảnh báo nhỏ, kể cả điều agent thấy mà brief không hỏi. Nếu thấy dead code hoặc lỗi ngoài phạm vi thì **báo lại, không tự sửa**.
6. **Danh sách những gì agent KHÔNG kiểm được** và lý do. Mục này không được để trống bằng một câu "không có".

**Cấm hẳn trong báo cáo:**
- khẳng định chủ dự án đã xác nhận điều gì, khi chủ dự án chưa nói. Lỗi này đã xảy ra ở đợt 111;
- khẳng định phủ định kiểu "không có X" khi chỉ grep mà chưa mở nguồn để kiểm;
- bất kỳ câu nào về lợi nhuận, về chiến lược, về việc có nên giao dịch.

Kết thúc bằng đúng câu: "Tôi không commit, không push, không đặt lệnh, không gọi endpoint có ký, không sửa `trading/`, không đọc dữ liệu từ 2026-09-01, và mọi hằng số phí/funding trong báo cáo đều có URL nguồn."

---

## 3. GitNexus

Đợt này **không sửa symbol nào đang tồn tại**: Task A chỉ chạy script có sẵn, Task B chỉ tạo file mới và **đọc** `trading.data_quality.is_dirty_bar`. Vì vậy không cần `gitnexus_impact`.

Nhưng vẫn phải làm hai việc:
- chạy `gitnexus_query` để chắc chắn chưa có script nào trong repo đã đo funding hoặc đo chi phí/biên độ cho perp — nếu có thì **báo lại, đừng viết trùng**; đợt 84 và đợt "leakage diagnostic" đã từng sinh ra hai công cụ trùng nhau vì brief của Claude thiếu bước này;
- chạy `gitnexus_detect_changes` trước khi báo cáo, và dán output. Nếu nó cho thấy có symbol cũ bị ảnh hưởng thì **dừng và báo** — nghĩa là phạm vi đã bị vượt.

Lưu ý: trong phiên của Claude hôm nay MCP `gitnexus` bị lỗi kết nối (`CONNECT_TIMEOUT`). Nếu agent cũng gặp lỗi đó thì ghi vào mục "không kiểm được" ở §2.6, và thay bằng `grep` có ghi rõ câu lệnh — không được im lặng bỏ qua.
