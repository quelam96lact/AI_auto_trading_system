# Brief đợt 118 — Phép đo tiền đăng ký đầu tiên trên forex: time-series momentum khung ngày

Ngày giao: 28/09/2026. Base: main `13eeb58`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh, không sửa `trading/engine/`**.

## 0. Vì sao đây là đợt đáng làm, và vì sao chỉ đo MỘT chiến lược

Bốn đợt vừa rồi (114–117) không đo chiến lược nào. Chúng dựng dữ liệu và mở hai cổng:

| Cổng | Trạng thái |
|---|---|
| Dữ liệu gốc dài, hợp điều khoản | **ĐẠT.** FRB H.10: EUR/USD 6.937 ngày từ 1999, USD/JPY 13.952 ngày từ 1971 |
| BingX có bám giá gốc không | **ĐẠT khi đo đúng mốc giờ.** EUR/USD 0,9776 và USD/JPY 0,9907 tại 16:00 UTC |
| Chi phí có để lại chỗ không | **XẤU.** Phí một vòng chiếm 41–51% biên độ một ngày |

Và có một điều trùng khớp quan trọng, chính nó làm đợt này khả thi:

> **Fixing H.10 chốt trưa New York, tức 16:00 UTC giờ mùa hè. Đó cũng đúng là mốc giờ mà giá BingX bám tốt nhất.** Nghĩa là chuỗi 27 năm dùng để đo và chuỗi thực thi được trên BingX **là cùng một đồng hồ**. Chiến lược hiệu chỉnh trên giá đóng H.10 có thể khớp lệnh tại nến 1h 16:00 UTC của BingX.

Đây là lần đầu trong dự án có một tài sản vừa đủ lịch sử, vừa hợp điều khoản, vừa khớp đồng hồ với sàn.

**Chỉ đo MỘT chiến lược, tham số cố định trước, không tối ưu gì.** Lý do: mười phép đo âm trước đây (module A/B/C/D trên BTC perp, SMC, VCP, momentum danh mục, overlay chế độ…) đều là thử nhiều rồi tìm cái thắng. Đợt này làm ngược: một giả thuyết, khai trước, chịu hiệu chỉnh đa kiểm định, có đối chứng ngẫu nhiên. Nếu âm thì ghi âm.

**Chiến lược được chọn trước khi xem dữ liệu, và Claude chọn, không phải agent chọn.**

## 1. Chiến lược — khai đầy đủ, agent KHÔNG được đổi một tham số nào

**Time-series momentum, nhìn lại 250 ngày giao dịch, tái cân bằng hàng tháng.**

| Thành phần | Quy định chính xác |
|---|---|
| Chuỗi giá | `bars_ext_daily`, `source = 'FRB_H10'`. Đây là chuỗi chính. |
| Ngày tái cân bằng | **Ngày có dữ liệu cuối cùng của mỗi tháng** trong chuỗi (không phải ngày cuối theo lịch). |
| Tín hiệu | Tại ngày tái cân bằng `t`: `r = close_t / close_{t-250} − 1`, trong đó `t-250` là **250 hàng trước đó trong chuỗi**, không phải 250 ngày lịch. |
| Vị thế tháng sau | `r > 0` → LONG. `r < 0` → SHORT. `r == 0` → phẳng. |
| Giá khớp | `close` của đúng ngày tái cân bằng. Không trượt giá thêm. |
| Khởi động | Cần 250 hàng trước. Với EUR/USD, tín hiệu đầu tiên rơi vào khoảng đầu năm 2000 dù cửa sổ bắt đầu 1999 — **ghi rõ ngày giao dịch đầu tiên thực tế**. |
| Không có chốt lời, không có cắt lỗ | Vị thế giữ nguyên trọn tháng. Đây là chủ ý, giữ chiến lược chỉ có một tham số. |

**Tuyệt đối cấm:** thử lookback khác 250, thử tần suất khác hàng tháng, thêm bộ lọc, thêm cắt lỗ, đổi ngưỡng khỏi 0. Nếu agent thấy một biến thể hấp dẫn thì **ghi vào báo cáo như một đề xuất**, không được chạy nó. Chạy thêm biến thể rồi báo cái tốt nhất chính là lỗi mà đợt này tồn tại để tránh.

## 2. Chi phí — và một giới hạn phải nói thẳng

| Khoản | Quy định |
|---|---|
| Phí | **0,05% mỗi chân**, lấy từ `takerFeeRate = 0.0005` của API BingX (đã xác minh đợt 116). Vào từ phẳng = 1 chân. Đảo chiều long↔short = **2 chân**. Giữ nguyên vị thế = 0 chân. |
| Funding | Xem bên dưới. |

**Giới hạn phải ghi ngay đầu báo cáo:** hợp đồng perpetual BingX cho EUR/USD chỉ niêm yết **08/2025**. Không tồn tại funding cho giai đoạn 1999–2025. Vì vậy funding trong đợt này **không phải số đo, mà là dải cảm biến**. Chạy ba mức, báo cả ba, không chọn một mức rồi gọi đó là kết quả:

| Mức | Giá trị | Ý nghĩa |
|---|---|---|
| A | 0,000%/ngày | không có funding, giới hạn trên của kết quả |
| B | **0,016%/ngày** | trung bình trị tuyệt đối đo được 12 tháng qua (đợt 116) |
| C | **0,030%/ngày** | P95 đo được (đợt 116), trường hợp xấu |

Funding tính cho **mỗi ngày lịch có giữ vị thế**, lấy trị tuyệt đối, tức luôn là chi phí. Lý do dùng trị tuyệt đối: funding đo được có dấu đổi theo chiều và theo thời kỳ, và ta không biết dấu của nó năm 2003. Giả định bất lợi là giả định trung thực ở đây.

Nếu mức A âm thì **dừng, không cần chạy B và C**, và báo ngay.

## 3. Cửa sổ và cổng — khai trước, không đổi sau khi thấy số

**Hai cửa sổ chính, dùng CHUNG cho cả hai cặp:**

| Cửa sổ | Khoảng | Số ngày EUR/USD | Số ngày USD/JPY |
|---|---|---|---|
| CHÍNH | 1999-01-04 … 2012-12-31 | 3.521 | 3.521 |
| LẶP LẠI | 2013-01-01 … 2026-08-31 | 3.416 | 3.416 |

Claude đã truy vấn hai con số này. Mỗi cửa sổ cho khoảng **164–168 lần tái cân bằng**, dư ngưỡng 30.

**Cửa sổ thứ ba, chỉ tham khảo, KHÔNG thuộc cổng:** USD/JPY 1971-01-04 … 1998-12-31 (10.536 ngày). Phải báo riêng và phải kèm đúng cảnh báo này: giai đoạn đó gồm sự sụp đổ của Bretton Woods và Hiệp định Plaza, là chế độ tiền tệ khác hẳn, có xu hướng dài bất thường thuận lợi cho momentum. **Không được đưa nó vào kết luận đạt/không đạt.**

**Cổng đạt, cả bốn điều kiện:**
1. Lợi nhuận ròng **> 0 ở CẢ HAI** cửa sổ chính, cho cùng một cặp;
2. tại mức funding **B**, không phải chỉ mức A;
3. ít nhất **30** lần tái cân bằng mỗi cửa sổ;
4. p-value của đối chứng ngẫu nhiên **đạt sau hiệu chỉnh Holm** trên **bốn** phép kiểm định (2 cặp × 2 cửa sổ).

Thiếu một điều là **không đạt**. Không có "gần đạt".

## 4. Đối chứng ngẫu nhiên — đổi dấu, không đổi ngày

Chiến lược này **luôn ở trong thị trường**, nên đối chứng "vào lệnh ngẫu nhiên" của `scripts/significance_test.py` **không dùng được** ở đây: nó mô hình hoá xác suất phát tín hiệu trên từng nến, còn ở đây câu hỏi là dấu.

Đối chứng đúng cho đợt này:
- giữ **nguyên** tập ngày tái cân bằng;
- thay dấu momentum bằng **±1 ngẫu nhiên, 50/50**;
- giữ **nguyên** mô hình chi phí, kể cả việc đảo chiều tốn 2 chân;
- **2.000** lượt, `random.Random(seed)` với seed cố định ghi trong code;
- p-value = tỷ lệ lượt có lợi nhuận ròng **≥** lợi nhuận ròng thật. Dùng `empirical_percentile_rank` trong `trading.metrics`, **không tự viết lại**.

## 5. KHÔNG viết lại thứ đã có

Đợt 117 suýt sinh ra hai công cụ trùng nhau vì brief của Claude thiếu bước soát. Claude đã soát trước:

| Đã có | Ở đâu | Việc |
|---|---|---|
| `max_drawdown`, `sharpe`, `profit_factor`, `expectancy` | `trading/metrics.py` | **import, cấm viết lại** |
| `empirical_percentile_rank`, `calculate_percentile` | `trading/metrics.py` | **import, cấm viết lại** |
| `holm_adjust` | hiện nằm trong `scripts/screen_smc_stock_daily.py` | xem §5.1 |
| `run_null_simulation`, `RandomEntryConfig` | `scripts/significance_test.py`, `trading/perp_backtest.py` | **KHÔNG dùng.** Sai hình dạng bài toán, xem §4. Ghi một dòng trong báo cáo nói rõ đã xem và vì sao không dùng. |

### 5.1. Dời `holm_adjust` vào `trading/metrics.py`

`holm_adjust` là hàm thống kê thuần nhưng đang nằm trong một script sàng lọc cổ phiếu. Đợt này là người dùng thứ hai của nó, nên dời chỗ chứ đừng import xuyên script.

1. Chuyển `holm_adjust` sang `trading/metrics.py`, **giữ nguyên thân hàm từng chữ**. Tham số `alpha` mặc định đang lấy hằng `ALPHA` của script; Claude đã kiểm: `scripts/screen_smc_stock_daily.py:85` có `ALPHA = 0.05`, nên trong `metrics.py` viết `alpha: float = 0.05` và **ghi rõ trong docstring rằng giá trị này đến từ đâu**. Nếu agent thấy `ALPHA` khác 0,05 thì **dừng và báo** — nghĩa là file đã đổi sau lúc Claude kiểm.
2. `scripts/screen_smc_stock_daily.py` import từ `trading.metrics`, xoá bản cũ.
3. `tests/test_screen_smc_stock_daily.py` đã có `test_8a_holm_p_010_020_040_thi_ca_ba_dat` và `test_8b_...` — **cập nhật import, cấm sửa nội dung hai test đó**. Chúng là lưới an toàn của phép dời này.
4. **Bắt buộc `gitnexus_impact` cho `holm_adjust` trước khi dời**, dán blast radius vào báo cáo. Có caller nào ngoài script đó và file test của nó thì **dừng và báo**.

## 6. Phạm vi

| File | Được làm gì |
|---|---|
| `trading/metrics.py` | **Thêm** `holm_adjust`. Không đụng hàm nào khác. |
| `scripts/screen_smc_stock_daily.py` | **Chỉ** đổi import, xoá bản `holm_adjust` cũ. Không đụng logic sàng lọc. |
| `tests/test_screen_smc_stock_daily.py` | **Chỉ** đổi import. |
| `scripts/measure_forex_tsmom.py` | **Mới.** |
| `tests/test_measure_forex_tsmom.py` | **Mới.** |
| `docs/superpowers/research/2026-09-2x-dot-118-do-tsmom-forex.md` | **Mới.** |

**Không được đụng:** `trading/engine/`, `trading/collector/`, `trading/broker`, `trading/strategies/`, `bars`, `bars_daily`, `bars_crypto`, `bars_ext_daily` (chỉ đọc), config, container, Task Scheduler, `.env`.

**Cấm đặt lệnh. Cấm gọi endpoint có ký. Cấm in secret.**
**Niêm phong:** chỉ đọc đến hết **2026-08-31**.
**Sao lưu ra ngoài repo. Cấm `git checkout`, `git restore`, `git stash`.**

## 7. Test và phá thử

Hàm thuần, mỗi hàm một test có **ví dụ tính tay ghi trong test**. **Cấm dựng `expected` bằng cách viết lại công thức của hàm trong thân test** — ghim số literal. Đợt 116 mắc đúng lỗi này.

**Năm phép phá thử bắt buộc**, mỗi phép phải làm ít nhất một test **đỏ**:

| # | Đột biến | Vì sao quan trọng |
|---|---|---|
| 1 | Tín hiệu dùng `close_{t+1}` thay vì `close_t` | **nhìn trước.** Đây là phép quan trọng nhất; lỗi rò rỉ tương lai đã xảy ra nhiều lần trong dự án |
| 2 | `t-250` đếm theo ngày lịch thay vì theo hàng | lookback sai âm thầm |
| 3 | Đảo chiều tính 1 chân thay vì 2 | chi phí bị nhẹ đi |
| 4 | Funding tính theo số lần tái cân bằng thay vì số ngày giữ | chi phí bị nhẹ đi rất nhiều |
| 5 | "Ngày cuối tháng" lấy theo lịch thay vì ngày có dữ liệu cuối cùng | lệch ngày khớp |

**Mỗi phép phá thử phải kèm bằng chứng đột biến đã thực sự được áp**, ví dụ dán `git diff --stat` của file bị sửa hoặc in lại dòng code sau khi sửa. Claude đã tự gặp một phép phá thử **báo xanh giả** vì phép thay chuỗi không khớp xuống dòng, nên xanh chưa chắc là test mù.

Nếu phép nào mà test vẫn xanh: **test đó yếu**, siết lại rồi phá lại, và **ghi cả lần yếu lẫn lần đã siết**.

→ **Kiểm chứng bằng:**
```
uv run pytest tests/test_measure_forex_tsmom.py -v
uv run pytest tests/test_screen_smc_stock_daily.py -v
uv run ruff check trading tests scripts/measure_forex_tsmom.py scripts/screen_smc_stock_daily.py
uv run pytest -m "not integration" -q
```
Suite hiện tại **1.220 pass**. Con số mới phải là 1.220 cộng số test agent thêm. Ruff phải sạch — đợt 117 báo "ruff sạch" khi nó báo 7 lỗi.

## 8. Báo cáo cho Claude

**Cách dán bằng chứng số liệu — đọc trước khi chạy:**

Đợt 117 dán ba khối bằng chứng bịa, trong đó một bảng khớp đúng những hàng mà brief đã cho trước làm mốc. Vì vậy đợt này:

1. **Ghi toàn bộ output ra file** trong `docs/superpowers/research/dot-118-output/` và dán **đường dẫn**. Claude sẽ tự chạy lại và tự so.
2. Với mỗi lệnh, dán **lệnh đã chạy và exit code**.
3. Mỗi bảng số liệu phải kèm một **truy vấn SQL kiểm chéo** mà Claude chạy lại được.
4. **Brief này cố tình KHÔNG cho trước con số kỳ vọng nào.** Không có mốc để chép. Nếu agent muốn tự kiểm thì tự tính tay và ghi phép tính ra.

**Nội dung báo cáo, theo thứ tự:**

1. **Kết luận ba dòng:** EUR/USD đạt/không đạt bốn điều kiện §3 kèm số; USD/JPY tương tự; chiến lược có vượt đối chứng ngẫu nhiên sau Holm hay không.
2. Bảng chính: `Cặp | Cửa sổ | Số tái cân bằng | Số chân | Lợi nhuận ròng mức A | mức B | mức C | Max drawdown | Sharpe | p-value | Holm đạt?`
3. Cửa sổ tham khảo USD/JPY 1971–1998, kèm cảnh báo chế độ tiền tệ.
4. **Đối chứng mua-và-giữ** trên cùng cửa sổ, cho biết chiến lược có hơn việc không làm gì không.
5. **Lặp lại trên chuỗi ECB EUR/USD** (chốt 14:15 CET, khác đồng hồ). Chỉ tham khảo. Nếu kết quả lệch hẳn so với H.10 thì đó là dấu hiệu có lỗi, phải báo.
6. Output §5.1 gồm blast radius của `holm_adjust`.
7. Output pytest, ruff, và năm phép phá thử kèm bằng chứng đột biến đã áp.
8. **Mọi điều bất thường.** Dead code hay lỗi ngoài phạm vi thì **báo lại, không tự sửa**.
9. **Danh sách những gì agent KHÔNG kiểm được** và lý do. Không được để trống bằng một câu "không có".

**Cấm trong báo cáo:**
- chạy thêm biến thể chiến lược rồi báo cái tốt nhất;
- nói chủ dự án đã xác nhận điều gì khi chủ dự án chưa nói;
- khẳng định phủ định khi chỉ grep mà chưa mở nguồn kiểm;
- gọi funding 1999–2025 là số đo — nó là dải cảm biến;
- bất kỳ câu nào về việc **có nên giao dịch thật**. Đợt này chỉ trả lời "có lợi thế đo được hay không".

Kết thúc bằng đúng câu: "Tôi không commit, không push, không đặt lệnh, không sửa `trading/engine/`, không đổi tham số chiến lược, không chạy biến thể nào ngoài bản đã khai, không đọc dữ liệu từ 2026-09-01, và mọi output đều có file kèm đường dẫn."

## 9. GitNexus

- `gitnexus_impact` **bắt buộc** cho `holm_adjust` trước khi dời (§5.1).
- `gitnexus_query` để chắc chưa có script nào đã đo time-series momentum trên forex — trùng thì **báo lại, đừng viết trùng**.

  Claude đã soát trước hai ứng viên gần nhất, agent không cần soát lại:
  - `scripts/measure_cross_sectional.py` là momentum **cắt ngang** trên rổ crypto: nó xếp hạng nhiều mã rồi chọn top-k (`--lookback` mặc định 30, `--k`, `_random_portfolio_selector`). Khác hẳn momentum **chuỗi thời gian** trên một chuỗi giá. **Không trùng.** Nhưng nó có `compute_btc_buy_and_hold` — xem cách nó dựng đối chứng mua-và-giữ rồi làm tương tự cho forex, đừng bắt chước máy móc vì mua-và-giữ một cặp tiền tệ khác mua-và-giữ BTC.
  - `scripts/measure_market_regime.py`: grep không thấy phần momentum. **Không trùng.**

  Nếu agent tìm thấy thứ Claude bỏ sót thì **báo lại chứ đừng tự gộp**.
- `gitnexus_detect_changes` trước khi báo cáo, dán output.

Phiên 28/09 của Claude: MCP `gitnexus` lỗi `CONNECT_TIMEOUT`, index đang **stale**. Gặp lỗi tương tự thì ghi vào §8.9 và thay bằng `grep` có ghi rõ câu lệnh — **không im lặng bỏ qua**. Vẫn **không** tự chạy `npx gitnexus analyze --force`.
