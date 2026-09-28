# Brief đợt 119 — Bảng điểm SEPA (Minervini Trend Template) dạng hiển thị, cộng hạng RS còn thiếu

Ngày giao: 28/09/2026. Base: main `4afa68b`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh, không sửa `trading/`**.

## 0. Điều phải đọc trước: bảy tiêu chí này ĐÃ CÓ, và đã được đo, và đã âm

Claude soát trước khi viết brief. **Bảy tiêu chí trong bảng điểm chủ dự án gửi đã được cài đặt sẵn**, tiền đăng ký, trong `scripts/screen_vcp_daily.py`:

| Dòng trong bảng điểm | Hằng đã có trong code |
|---|---|
| Giá trên MA150 và MA200 | `c1_close_tren_sma150_200` |
| MA150 trên MA200 | `c2_sma150_tren_sma200` |
| MA200 hướng lên ≥ 1 tháng | `c3_sma200_di_len` |
| MA50 trên cả MA150 và MA200 | `c4_sma50_tren_sma150_200` |
| Giá trên MA50 | `c5_close_tren_sma50` |
| Giá ≥ 30% trên đáy 52 tuần | `c6_cach_day_252_nen` |
| Giá trong 25% của đỉnh 52 tuần | `c7_gan_dinh_252_nen` |

Trùng cả bảy, cùng ngữ nghĩa. Kèm theo đó đã có `rolling_mean`, `rolling_max`, `rolling_min`, `clean_bars`, `bar_date`, `trend_conditions`, `trend_filter_ok`.

**Và bảy tiêu chí đó chính là bộ lọc xu hướng bên trong phép sàng lọc VCP đã được đo ở đợt 99.** Commit `19432af`: *"sàng lọc VCP cổ phiếu nến ngày — thua rõ đối chứng cùng ngày, phép đo âm thứ bảy"*.

Vì vậy đợt này **không phải** đi tìm lợi thế, và **không được** kết luận gì về lợi thế. Đợt này làm đúng một việc: chủ dự án muốn một **bảng điểm để xem hằng ngày**, và thứ đang thiếu là phần **hiển thị** cùng **tiêu chí thứ tám (RS)**, chứ không phải bảy tiêu chí kia.

**Cấm tuyệt đối trong đợt này:** tính lợi nhuận, tính lợi suất tương lai, xếp hạng "mã tốt nhất", hay bất kỳ câu nào hàm ý điểm cao thì nên mua. Bảng điểm là **mô tả trạng thái kỹ thuật**, đúng như dòng chú thích trong bảng chủ dự án gửi.

## 1. Thứ thật sự còn thiếu

| # | Còn thiếu | Ghi chú |
|---|---|---|
| 1 | **Đầu ra dạng bảng điểm** `n/7` kèm đạt/không đạt từng dòng | Code hiện tại chỉ `AND` bảy điều kiện thành một boolean (`trend_filter_ok`), không xuất điểm |
| 2 | **Hai con số biên** trong bảng: % trên đáy 52 tuần, % cách đỉnh 52 tuần | Hiện chỉ có boolean, không có số |
| 3 | **Tiêu chí thứ tám: RS (bảng gọi là SM) ≥ 70** | Chưa cài đặt ở đâu trong repo |
| 4 | **Chạy được trên dữ liệu hiện tại** | `screen_vcp_daily.py` chốt cứng `READ_TO = 2023-01-01` và có `validate_sealed_bars` raise khi gặp dữ liệu sau niêm phong |

## 2. Dữ liệu — Claude đã kiểm, agent không phải kiểm lại

| Việc | Sự thật đã kiểm 28/09 |
|---|---|
| Lược đồ `bars_daily` | `symbol text, ts timestamptz, open, high, low, close, volume bigint, source text`. **Không có cột `date`.** |
| **Bẫy múi giờ** | `ts` lưu **00:00 giờ VN**, tức `2026-09-24 17:00+00` là phiên VN **25/09**. `ts::date` theo UTC **lệch một ngày**. Phải dùng `bar_date()` đã có sẵn trong `screen_vcp_daily.py`, hàm đó xử lý đúng và có ghi chú. |
| Phiên mới nhất | **Thứ Sáu 25/09/2026.** Chưa có nến của hôm nay 28/09. |
| Độ phủ | `bars_daily` có 560 bảng con nhưng **chỉ khoảng 175 mã** có nến trong tháng 9/2026. |
| `symbol_universe` | `symbol, exchange, avg_value_20d, avg_volume_20d, is_active, updated_at`. HOSE 431, HNX 302, UPCOM 862. |
| BFC | 2.679 nến từ 2016-01-03, giá đóng phiên 25/09 là **48.350**. |

### 2.1. Bảng điểm chủ dự án gửi KHÔNG tái lập được từ dữ liệu của ta — và đây là lý do

Claude tự tính BFC tại phiên 25/09:

| Chỉ số | Claude tính (25/09) | Bảng chủ dự án gửi |
|---|---|---|
| % trên đáy 252 nến | **29,9%** | 35,7% |
| % cách đỉnh 252 nến | **33,6%** | 30,6% |
| MA50 / MA150 / MA200 | 48.071,2 / 53.686,7 / 51.058,5 | — |

Giải ngược từ hai con số của bảng thì giá đóng phải khoảng **50.500**, trong khi nến mới nhất của ta là 48.350. Chênh +4,4%. Cả hai con số lệch **đúng theo hướng mà một giá cao hơn sẽ gây ra**, và đỉnh 252 nến suy ra từ bảng (≈72.779) khớp đỉnh Claude đo (72.816) trong sai số làm tròn.

**Kết luận: bảng của chủ dự án dùng giá trong phiên hôm nay 28/09, còn `bars_daily` chưa có nến hôm nay.**

Hệ quả cho agent:
- **KHÔNG được** dùng 35,7% và 30,6% làm mốc kiểm thử. Chúng không thuộc phiên 25/09.
- Thay vào đó, mốc kiểm thử là **con số Claude đã tính ở trên cho phiên 25/09**. Nếu agent tính ra khác, **dừng và báo lệch bao nhiêu**, đừng chỉnh cho khớp.
- Cũng kiểm được cả hai cách hiểu "52 tuần": Claude đã chạy cả **252 nến** và **365 ngày lịch**, và với BFC **hai cách ra cùng kết quả**, nên không phân biệt được bằng mã này. Chọn **252 nến** để nhất quán với `RANGE_WINDOW = 252` đã có, và **ghi rõ đã chọn cách nào**.

## 3. Tiêu chí thứ tám (RS/SM) — Claude khai định nghĩa, agent không được tự chọn

Bảng của chủ dự án viết "SM ≥ 70 (mã ngoài rổ Radar, chưa có RS)", tức công cụ đó chỉ tính RS cho một rổ riêng. Ta phải có định nghĩa của mình.

**Định nghĩa dùng cho đợt này, khai trước:**

```
RS_raw = 0,4 × (P/P_63  − 1)
       + 0,2 × (P/P_126 − 1)
       + 0,2 × (P/P_189 − 1)
       + 0,2 × (P/P_252 − 1)
```

trong đó `P_k` là giá đóng cửa **k nến trước** trong chuỗi của chính mã đó. Sau đó `RS_rank` = **phân vị của `RS_raw` trong vũ trụ đủ điều kiện tại đúng phiên đó**, đổi ra thang 1–99.

**Ba điều phải ghi rõ trong báo cáo, không được bỏ:**
1. Đây là **xấp xỉ theo trọng số thường được công bố**, **KHÔNG phải** RS Rating của IBD — công thức của IBD là độc quyền và ta không có nó. Cấm gọi nó là "RS Rating của IBD".
2. `RS_rank` **chỉ so được trong vũ trụ đã dùng**. Phải in **số mã trong vũ trụ** cạnh mỗi hạng. Vũ trụ 175 mã cho ra hạng khác hẳn vũ trụ 1.595 mã.
3. Mã không đủ 252 nến sạch thì **không có RS**, in `–` đúng như bảng của chủ dự án, **không được gán 0 hay 50**. Gán số là bịa ra một hạng.

**Vũ trụ đủ điều kiện, khai trước:** mã có ít nhất **252 nến sạch** tính đến phiên đang xét, và `is_active = true` trong `symbol_universe`. Không thêm điều kiện thanh khoản nào khác ở đợt này — thêm bộ lọc là thêm tham số chưa khai.

**Điểm tổng vẫn là `n/7`**, không phải `n/8`, đúng như bảng chủ dự án gửi (4/7). RS in thành một dòng riêng có trạng thái đạt / không đạt / `–`.

## 4. Niêm phong — chỗ này phải rõ, đừng lách

Cổ phiếu từ **2023-01-01** là holdout niêm phong (`SEALED_START` trong `screen_vcp_daily.py`). Một bảng điểm cho hôm nay **buộc phải đọc dữ liệu sau niêm phong**.

**Cách xử lý đã quyết, agent làm đúng thế:**
- Công cụ đợt này là **hiển thị mô tả**, được phép đọc dữ liệu hiện tại.
- Nó phải in **một dòng cảnh báo nổi bật** ở đầu output: đang đọc dữ liệu sau mốc niêm phong 2023-01-01, và số này **không dùng được cho bất kỳ phép đo hiệu năng nào**.
- Nó **tuyệt đối không** tính lợi suất tương lai, không tính thắng/thua, không tính bất kỳ thống kê hiệu năng nào. Không có `forward_return`, không có `pnl`, không có `win_rate` trong file này.
- **Không sửa** `SEALED_START`, `READ_FROM`, `READ_TO`, hay `validate_sealed_bars` trong `screen_vcp_daily.py`. Script mới tự đọc DB, và **không gọi** `validate_sealed_bars`.

Nếu agent thấy cách nào khiến bảng điểm vô tình dùng được để đo hiệu năng, **báo lại**, đừng tự dựng.

## 5. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/score_sepa_daily.py` | **Mới.** Toàn bộ việc của đợt này. |
| `tests/test_score_sepa_daily.py` | **Mới.** |
| `docs/superpowers/research/2026-09-2x-dot-119-bang-diem-sepa.md` | **Mới.** Báo cáo. |
| `docs/superpowers/research/dot-119-output/` | **Mới.** Output ghi ra file. |

**`scripts/screen_vcp_daily.py`: CHỈ ĐỌC, cấm sửa một dòng.** Nó đang là thư viện dùng chung cho `screen_smc_stock_daily.py` và `screen_momentum_portfolio.py` (nợ kỹ thuật đã ghi ở đợt 102, commit `39c049e`). Sửa nó là chạm vào ba script. Script mới phải **import** từ nó:

```python
from scripts.screen_vcp_daily import (
    bar_date, clean_bars, rolling_max, rolling_mean, rolling_min, trend_conditions,
)
```

Nếu cần một hàm mà nó không xuất ra được, **dừng và báo** — Claude quyết, có thể phải trả nợ kỹ thuật kia trước.

**Không được đụng:** `trading/`, `bars`, `bars_daily`, `bars_crypto`, `bars_ext_daily` (chỉ đọc), `symbol_universe` (chỉ đọc), các script khác, config, container, Task Scheduler, `.env`.

**Sao lưu ra ngoài repo. Cấm `git checkout`, `git restore`, `git stash`.**

## 6. Các bước

1. **Bảng điểm một mã.** `--symbol BFC --as-of 2026-09-25` in đúng tám dòng như bảng chủ dự án gửi, cộng điểm `n/7`, cộng hai con số biên.
   → **Kiểm chứng bằng:** khớp bảng Claude đã tính ở §2.1 cho BFC phiên 25/09. Lệch thì dừng và báo.

2. **Bảng điểm nhiều mã.** Không có `--symbol` thì chạy toàn bộ vũ trụ đủ điều kiện tại phiên mới nhất, in bảng: `Mã | Điểm n/7 | c1..c7 | % trên đáy | % cách đỉnh | RS_rank | Số mã trong vũ trụ`.
   → **Kiểm chứng bằng:** dán số mã đủ điều kiện và số mã bị loại kèm lý do loại (thiếu nến / không `is_active` / nến bẩn).

3. **Kiểm chéo bằng tay, không dùng script.** Chọn **3 mã** khác BFC. Với mỗi mã, lấy tay giá đóng, MA50, MA150, MA200 từ DB bằng SQL, tự đối chiếu từng điều kiện, rồi so với output. Dán cả ba phép.

4. **Test.** Hàm thuần, ví dụ tính tay ghi trong test, **cấm dựng `expected` bằng cách viết lại công thức trong thân test**.

   **Bốn phép phá thử bắt buộc**, mỗi phép phải làm ít nhất một test **đỏ**, và **phải kèm bằng chứng đột biến đã thực sự được áp** (in lại dòng code sau khi sửa, hoặc `git diff`):
   1. Dùng `ts::date` thay cho `bar_date()` → lệch một ngày → đỏ.
   2. Đổi trọng số RS từ `0,4/0,2/0,2/0,2` sang `0,25` đều → đỏ.
   3. Mã thiếu 252 nến được gán `RS_rank = 50` thay vì `–` → đỏ.
   4. Đổi "% cách đỉnh" từ `1 − P/đỉnh` sang `đỉnh/P − 1` → đỏ.

   Phép nào mà test vẫn xanh thì **test đó yếu**: siết lại rồi phá lại, **ghi cả lần yếu lẫn lần đã siết**.

   → **Kiểm chứng bằng:**
   ```
   uv run pytest tests/test_score_sepa_daily.py -v
   uv run pytest -m "not integration" -q
   uv run ruff check trading tests scripts/score_sepa_daily.py
   ```
   Suite hiện tại **1.227 pass**. Con số mới phải là 1.227 cộng số test agent thêm. Ruff phải sạch.

## 7. Báo cáo cho Claude

**Ghi toàn bộ output ra `docs/superpowers/research/dot-119-output/` và dán đường dẫn.** Mỗi lệnh kèm **exit code**. Mỗi bảng số liệu kèm **truy vấn SQL kiểm chéo mà Claude chạy lại được** — nhớ `bars_daily` không có cột `date`, và `ts` lệch một ngày so với phiên VN; truy vấn nào dùng `time` hoặc `ts::date` là sai.

Theo thứ tự:
1. **Kết luận hai dòng:** bảng điểm BFC phiên 25/09 có khớp số Claude tính không; RS chạy được trên bao nhiêu mã.
2. Output bước 1, 2, 3 nguyên văn.
3. Output pytest, ruff, bốn phép phá thử kèm bằng chứng đột biến.
4. **Mọi điều bất thường.** Dead code hay lỗi ngoài phạm vi thì **báo lại, không tự sửa**.
5. **Danh sách những gì agent KHÔNG kiểm được** và lý do. Không được để trống.

**Cấm trong báo cáo:**
- bất kỳ con số lợi nhuận, lợi suất tương lai, thắng/thua nào;
- bất kỳ câu nào hàm ý điểm cao thì nên mua, hoặc mã nào "đáng chú ý";
- gọi RS của ta là RS Rating của IBD;
- nói chủ dự án đã xác nhận điều gì khi chủ dự án chưa nói;
- khẳng định phủ định khi chỉ grep mà chưa mở nguồn kiểm.

Kết thúc bằng đúng câu: "Tôi không commit, không push, không đặt lệnh, không sửa `screen_vcp_daily.py` hay `trading/`, không tính bất kỳ số hiệu năng nào, không gán hạng RS cho mã thiếu dữ liệu, và mọi output đều có file kèm đường dẫn."

## 8. GitNexus

- `gitnexus_impact` cho `trend_conditions`, `bar_date`, `rolling_mean` **trước khi import**, để biết blast radius nếu sau này phải sửa. Dán vào báo cáo. Đợt này **không sửa** chúng, nên không cần dừng vì rủi ro cao — chỉ cần ghi lại.
- `gitnexus_query` để chắc chưa có script nào xuất bảng điểm SEPA. Claude đã soát: chỉ `screen_vcp_daily.py` có bảy điều kiện, và nó dùng chúng làm bộ lọc nhị phân, **không xuất điểm**. Tìm thấy thứ Claude bỏ sót thì **báo lại chứ đừng tự gộp**.
- `gitnexus_detect_changes` trước khi báo cáo, dán output.

Phiên 28/09 của Claude: MCP `gitnexus` lỗi `CONNECT_TIMEOUT`, index **stale**. Gặp lỗi tương tự thì ghi vào §7.5 và thay bằng `grep` có ghi rõ câu lệnh, **không im lặng bỏ qua**. Vẫn **không** tự chạy `npx gitnexus analyze --force`.

## 9. Việc KHÔNG thuộc đợt này

Câu "điểm SEPA cao có dự báo được lợi suất không" là một **phép đo riêng**, phải tiền đăng ký, phải dùng **chỉ dữ liệu trước 2023** để giữ holdout, và phải có đối chứng cùng ngày như đợt 99 đã làm. Đợt này **không** trả lời câu đó, và không được nói gì theo hướng đó.
