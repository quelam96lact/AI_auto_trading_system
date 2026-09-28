# Brief đợt 120 — Điểm SEPA có dự báo được lợi suất không: phép đo tiền đăng ký, chỉ dữ liệu trước 2023

Ngày giao: 28/09/2026. Base: main `fe9ac1e`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh, không sửa `trading/`**.

## 0. Vì sao, và vì sao đợt này KHÔNG phải chạy lại đợt 99

Đợt 119 đã dựng bảng điểm SEPA để xem hằng ngày. Nó **chỉ mô tả trạng thái kỹ thuật** — chưa ai đo xem điểm cao có ý nghĩa gì.

Đợt 99 đã đo **phép sàng lọc VCP** và kết quả âm: *"thua rõ đối chứng cùng ngày, phép đo âm thứ bảy"* (commit `19432af`). Nhưng đợt 99 đo một thứ khác: nó đòi **cả bảy điều kiện xu hướng cùng đạt, CỘNG nền VCP, CỘNG nến phá vỡ**. Câu hỏi của đợt này khác:

1. **Điểm 0–7 có đơn điệu không?** Điểm càng cao thì lợi suất vượt trội càng cao?
2. **RS ≥ 70 có thêm được gì** trong nhóm đã đạt 7/7?

Đó là hai câu chưa ai đo. Trả lời được thì biết bảng điểm đợt 119 là công cụ hay chỉ là đồ trang trí.

**Đợt này chỉ dùng dữ liệu trước 2023.** Holdout cổ phiếu từ 2023-01-01 phải nguyên vẹn, vì nó là thứ duy nhất còn lại để kiểm chứng sau này.

## 1. KHÔNG viết lại thứ đã có — đây là phần lớn nhất của brief

Claude soát trước: **toàn bộ máy đo đã nằm trong `scripts/screen_vcp_daily.py`.** Agent phải `import`, không viết lại một hàm nào trong bảng dưới:

| Hàm đã có | Việc |
|---|---|
| `trend_conditions` | bảy điều kiện xu hướng |
| `rolling_mean`, `rolling_max`, `rolling_min` | đường trung bình, đỉnh/đáy cửa sổ |
| `clean_bars`, `bar_date`, `validate_sealed_bars`, `in_is` | làm sạch nến, ngày giờ VN, **bắt buộc giữ niêm phong** |
| `liquidity_ok` | ngưỡng thanh khoản đã đăng ký (`MIN_TURNOVER_VND = 1e9`, cửa sổ 20) |
| `apply_cooldown` | giãn sự kiện, `COOLDOWN_BARS = 20` |
| `entry_status`, `is_ceiling_open`, `limit_rate` | vào lệnh ở mở cửa hôm sau, **loại phiên mở trần** |
| `net_return`, `compute_targets` | lợi suất kỳ hạn `TARGET_KS = (5, 10, 20)` |
| **`basket_baseline`, `excess_for_event`** | **đối chứng cùng ngày** — trái tim của phép đo |
| **`bootstrap_by_month`** | bootstrap khối theo tháng, `N_BOOTSTRAP = 2000`, `BOOTSTRAP_SEED = 42` |
| `compact_control_series`, `load_universe` | nạp dữ liệu |
| `_describe`, `_percentile` | thống kê mô tả |

Và từ `trading/metrics.py`: `holm_adjust`, `empirical_percentile_rank`, `max_drawdown`.

**`scripts/screen_vcp_daily.py`: CHỈ ĐỌC, cấm sửa một dòng.** Cần một hàm mà nó không xuất ra được thì **dừng và báo**.

### 1.1. Nợ kỹ thuật đang phình ra, và Claude nói rõ là mình đang làm nó nặng thêm

`screen_vcp_daily.py` **là một script, không phải thư viện**, nhưng nó đang bị import từ:

| Người dùng | Từ đợt |
|---|---|
| `scripts/screen_smc_stock_daily.py` | đợt 101 |
| `scripts/screen_momentum_portfolio.py` | — |
| `scripts/score_sepa_daily.py` | đợt 119 |
| **`scripts/measure_sepa_score_edge.py`** | **đợt này — người thứ tư** |

Cộng 5 file test cũng import trực tiếp từ nó. Nợ này đã được ghi từ đợt 102 (commit `39c049e`: *"screen_vcp_daily đang làm thư viện chung cho ba script sàng lọc"*), và brief này **làm nó nặng thêm** bằng cách thêm người dùng thứ tư rồi lại viết "cấm sửa nó" — tức vừa dựa vào nó vừa đóng băng nó.

**Agent KHÔNG được trả nợ này ở đợt này.** Lý do: dời các hàm thuần sang `trading/` sẽ chạm vào 4 script và 5 file test cùng lúc, cần phân tích ảnh hưởng riêng, và trộn nó vào một phép đo tiền đăng ký sẽ làm không ai biết kết quả đo thay đổi vì dữ liệu hay vì refactor. Hai việc phải tách.

**Việc agent PHẢI làm:** ghi vào báo cáo một mục ngắn xác nhận đã đọc phần này, và nếu trong lúc import thấy hàm nào **không dùng được nếu không sửa** thì nêu tên hàm đó. Đó là dữ kiện để Claude quyết đợt trả nợ.

Claude ghi nhận đây là **ứng viên brief tiếp theo** sau đợt 120: dời `bar_date`, `clean_bars`, `rolling_*`, `trend_conditions`, `liquidity_ok`, `net_return`, `compute_targets`, `basket_baseline`, `excess_for_event`, `bootstrap_by_month` sang một module trong `trading/`, cập nhật 4 script và 5 file test, không đổi hành vi, và chốt bằng việc chạy lại `screen_vcp_daily.py` cho ra **y nguyên** số của đợt 99.

Mọi hằng số đã đăng ký ở trên **giữ nguyên, cấm đổi**: đổi một hằng số là biến phép đo tiền đăng ký thành phép đo có tinh chỉnh.

## 2. Thứ thật sự phải viết mới

Chỉ ba thứ:

1. **Định nghĩa sự kiện theo điểm** (thay cho nền VCP + phá vỡ của đợt 99).
2. **Phân nhóm theo điểm 0–7** và tính lợi suất vượt trội từng nhóm.
3. **Tách theo RS** trong nhóm 7/7.

### 2.1. Sự kiện — Claude khai trước, agent không được chọn

**Sự kiện chính (được gated):** ngày `t` mà điểm **chuyển thành 7/7**, tức điểm tại `t-1` nhỏ hơn 7 và điểm tại `t` bằng 7. Sau đó áp `apply_cooldown(20)`.

Lý do khai thế: 7/7 là một **trạng thái kéo dài**, một mã có thể ở 7/7 suốt 200 phiên. Nếu tính mỗi ngày 7/7 là một sự kiện thì mẫu bị một nhúm mã dài hạn chiếm hết, và bootstrap theo tháng cũng không cứu được.

**Biến thể chỉ để báo cáo, KHÔNG gated:** mọi ngày ở 7/7, vẫn áp `apply_cooldown(20)`. Báo song song để biết cách định nghĩa có làm đổi kết luận hay không. **Không được** lấy biến thể nào tốt hơn rồi báo nó là kết quả chính.

### 2.2. Loại các mã có dữ liệu điều chỉnh giá không tin cậy

Dùng `exclusions.txt` ở gốc repo (246 mã, sinh bởi `scripts/check_price_adjustment.py --emit-exclusions`). Với những mã đó, một split chưa điều chỉnh làm lệch cả MA150/MA200 lẫn đáy/đỉnh 52 tuần, nên điểm SEPA của chúng sai.

**Phải báo cả hai:**
- kết quả **có loại** 246 mã — đây là kết quả chính;
- kết quả **không loại** — chỉ để biết việc loại có đổi kết luận hay không, và để biết liệu đợt 99 có bị ảnh hưởng.

Kèm số sự kiện mất đi khi loại.

Nếu `exclusions.txt` không đọc được thì **dừng và báo**, đừng chạy tiếp coi như mọi mã đều sạch.

## 3. Cửa sổ, cổng, và kiểm định — khai trước

**Cửa sổ tín hiệu:** dùng đúng hai hằng đã đăng ký trong `screen_vcp_daily.py`:
`IS_SIGNAL_START = 2016-01-04`, `IS_SIGNAL_END = 2022-11-30`. **Cấm đổi.**

**Niêm phong:** đọc dữ liệu qua `READ_FROM`/`READ_TO` đã có, và **gọi `validate_sealed_bars`** để nó tự chặn nếu lỡ nạp dữ liệu sau 2023-01-01. Đây là đợt đo, khác đợt 119 — ở đây niêm phong phải được thực thi, không phải chỉ cảnh báo.

**Giả thuyết chính, một cái duy nhất được gated:**

> Lợi suất vượt trội so với đối chứng cùng ngày của nhóm sự kiện 7/7, tại `K = 20`, **lớn hơn 0**.

**Cổng đạt, cả bốn điều kiện:**
1. trung vị lợi suất vượt trội tại `K = 20` **> 0**;
2. ít nhất `MIN_EVENTS = 100` sự kiện hợp lệ;
3. khoảng tin cậy bootstrap khối theo tháng **không chứa 0** (`CI_LOW_PCT = 2.5`, `CI_HIGH_PCT = 97.5`);
4. đạt sau **Holm** trên số phép kiểm định thực sự chạy ở §3.1.

Thiếu một điều là **không đạt**. Không có "gần đạt".

### 3.1. Đếm phép kiểm định cho Holm — phải trung thực

Phép gated là **một**: nhóm 7/7 tại `K = 20`.

Các thứ sau là **thứ cấp, chỉ báo cáo, không đưa vào Holm và không được gọi là đạt**:
- nhóm điểm 0, 1, …, 6 (kiểm tính đơn điệu);
- `K = 5` và `K = 10`;
- tách RS ≥ 70 so với RS < 70 trong nhóm 7/7;
- biến thể sự kiện ở §2.1.

Nếu agent muốn đưa thêm phép nào vào cổng thì **phải dừng và hỏi Claude trước khi chạy**, vì thêm phép là đổi mẫu số Holm.

## 4. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/measure_sepa_score_edge.py` | **Mới.** Toàn bộ việc của đợt này. |
| `tests/test_measure_sepa_score_edge.py` | **Mới.** |
| `docs/superpowers/research/2026-09-2x-dot-120-do-diem-sepa.md` | **Mới.** Báo cáo. |
| `docs/superpowers/research/dot-120-output/` | **Mới.** Output ghi ra file. |

**Không được đụng:** `scripts/screen_vcp_daily.py`, `scripts/score_sepa_daily.py`, `trading/`, `bars`, `bars_daily` (chỉ đọc), `symbol_universe` (chỉ đọc), `exclusions.txt` (chỉ đọc), các script khác, config, container, Task Scheduler, `.env`.

**Sao lưu ra ngoài repo. Cấm `git checkout`, `git restore`, `git stash`.**

## 5. Test và phá thử

Hàm thuần, ví dụ tính tay ghi trong test. **Cấm dựng `expected` bằng cách viết lại công thức trong thân test** — ghim số literal.

**Năm phép phá thử bắt buộc**, mỗi phép phải làm ít nhất một test **đỏ**, và **phải kèm bằng chứng đột biến đã thực sự được áp** (in lại dòng code sau khi sửa, hoặc `git diff`):

| # | Đột biến | Vì sao |
|---|---|---|
| 1 | Điểm tại `t` tính từ nến `t+1` | **nhìn trước** — quan trọng nhất |
| 2 | Sự kiện = mọi ngày 7/7, bỏ điều kiện chuyển trạng thái | đổi định nghĩa đã khai |
| 3 | Bỏ `excess_for_event`, dùng lợi suất thô thay vì trừ đối chứng cùng ngày | mất đối chứng thì kết quả chỉ là xu hướng thị trường |
| 4 | Bỏ `apply_cooldown` | sự kiện chồng chéo, mẫu bị một nhúm mã chiếm |
| 5 | Bỏ lọc `exclusions.txt` | mã dữ liệu sai lọt vào |

Phép nào mà test vẫn xanh thì **test đó yếu**: siết lại rồi phá lại, **ghi cả lần yếu lẫn lần đã siết**.

→ **Kiểm chứng bằng:**
```
uv run pytest tests/test_measure_sepa_score_edge.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts/measure_sepa_score_edge.py
```
Suite hiện tại **1.237 pass**. Con số mới phải là 1.237 cộng số test agent thêm. Ruff phải sạch.

## 6. Báo cáo cho Claude

**Ghi toàn bộ output ra `docs/superpowers/research/dot-120-output/` và dán đường dẫn.** Mỗi lệnh kèm **exit code**. Mỗi bảng số liệu kèm **truy vấn SQL kiểm chéo mà Claude chạy lại được** — nhớ `bars_daily` **không có cột `date`**, và `ts` lưu 00:00 giờ VN nên `ts::date` lệch một ngày; truy vấn nào dùng `ts::date` là sai.

**Brief này CỐ Ý không cho trước con số kỳ vọng nào.** Không có mốc để chép. Claude sẽ tự chạy lại và tự so.

Theo thứ tự:
1. **Kết luận ba dòng:** nhóm 7/7 tại K=20 đạt/không đạt bốn điều kiện §3 kèm số; điểm có đơn điệu không; RS có thêm được gì không.
2. Bảng chính: `Nhóm điểm | Số sự kiện | Trung vị vượt trội K=20 | CI bootstrap | Đạt cổng? | K=5 | K=10`.
3. Bảng RS trong nhóm 7/7.
4. Bảng có loại / không loại 246 mã, kèm số sự kiện mất đi.
5. Biến thể sự kiện ở §2.1.
6. Output pytest, ruff, năm phép phá thử kèm bằng chứng đột biến.
7. **Mọi điều bất thường.** Dead code hay lỗi ngoài phạm vi thì **báo lại, không tự sửa**.
8. **Danh sách những gì agent KHÔNG kiểm được** và lý do. Không được để trống.

**Cấm trong báo cáo:**
- chạy thêm biến thể rồi báo cái tốt nhất;
- gọi một phép thứ cấp là "đạt";
- đọc hay nhắc tới dữ liệu từ 2023-01-01 trở đi;
- nói chủ dự án đã xác nhận điều gì khi chủ dự án chưa nói;
- bất kỳ câu nào về việc **có nên giao dịch thật**. Đợt này chỉ trả lời "có lợi thế đo được hay không".

Kết thúc bằng đúng câu: "Tôi không commit, không push, không đặt lệnh, không sửa `screen_vcp_daily.py` hay `trading/`, không đổi hằng số đã đăng ký, không đọc dữ liệu từ 2023-01-01, không đưa phép thứ cấp vào cổng, và mọi output đều có file kèm đường dẫn."

## 7. GitNexus

- `gitnexus_impact` cho `basket_baseline`, `excess_for_event`, `bootstrap_by_month` **trước khi import**; dán blast radius. Đợt này **không sửa** chúng nên không cần dừng vì rủi ro cao, chỉ cần ghi lại.
- `gitnexus_query` để chắc chưa có script nào đo lợi thế theo **điểm** SEPA. Claude đã soát: đợt 99 đo phép sàng lọc VCP (bảy điều kiện + nền + phá vỡ) chứ **không** đo theo nhóm điểm; `score_sepa_daily.py` chỉ hiển thị, không đo. Tìm thấy thứ Claude bỏ sót thì **báo lại chứ đừng tự gộp**.
- `gitnexus_detect_changes` trước khi báo cáo, dán output.

Phiên 28/09 của Claude: MCP `gitnexus` lỗi `CONNECT_TIMEOUT`, index **stale**. Gặp lỗi tương tự thì ghi vào §6.8 và thay bằng `grep` có ghi rõ câu lệnh, **không im lặng bỏ qua**. Vẫn **không** tự chạy `npx gitnexus analyze --force`.

## 8. Dự đoán của Claude, ghi trước để sau đối chiếu

Claude nghĩ **không đạt**, vì đợt 99 đã cho thấy bảy điều kiện này cộng thêm nền và phá vỡ vẫn thua đối chứng cùng ngày, và mười một phép đo trước đều âm. Nhưng dự đoán của Claude đã sai hai lần trong hai ngày (vàng ở đợt 117, EUR/USD ở đợt 118), nên **đây chỉ là dự đoán, không phải kết quả mong muốn**. Brief không nói cho agent biết Claude nghĩ gì — mục này để chủ dự án đọc.

## 9. Việc KHÔNG thuộc đợt này

- **Câu hỏi mở còn treo:** có nên loại 246 mã không tin cậy khỏi **vũ trụ xếp hạng RS** trong `score_sepa_daily.py` hay không. Loại sẽ đổi hạng của cả 167 mã. Đó là quyết định thiết kế cần khai trước, và **không** thuộc đợt này.
- Bảng điểm chạy trong phiên: cần nguồn giá trong phiên, không phải `bars_daily`. Chưa được yêu cầu.
