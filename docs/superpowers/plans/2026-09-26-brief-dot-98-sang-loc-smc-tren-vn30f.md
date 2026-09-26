# Brief đợt 98 — Sàng lọc SMC (Smart Money Concepts) trên VN30F1M, đăng ký trước

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `fe2691b`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.
Làm được ngay cuối tuần. Chỉ **đọc** DB. **Không** đụng container, máy ghi sổ lệnh, Task Scheduler.

---

## 0. Câu hỏi, và điều brief này KHÔNG hỏi

**Câu hỏi:** ba khái niệm SMC có thể định nghĩa thành quy tắc máy (quét thanh khoản, phá cấu trúc, khoảng trống giá) có dự báo được biến động giá VN30F1M trong vài nến 5 phút tiếp theo không? Nếu có, biến động đó có **lớn hơn chi phí giao dịch** không?

**Không hỏi:** SMC "thật" có hiệu quả không. SMC gốc dựa vào phán đoán của người giao dịch, và hệ thống tự động không chạy được phán đoán. **Phiên bản máy chạy được là phiên bản duy nhất ta giao dịch được**, nên đó là phiên bản được đo.

**Vì sao VN30F, không phải cổ phiếu:** SMC là kỹ thuật trong phiên, cần cả chiều mua lẫn bán. Cổ phiếu VN có T+2,5, không bán khống, và phí khứ hồi 0,60%. VN30F có T+0, mua và bán đều được, và chi phí khoảng 0,5 điểm mỗi vòng (đợt 95).

**Kỳ vọng trước của Claude:** nhiều khả năng âm, vì đợt 85 đo momentum, biên độ nến và khoảng cách tới giá mở trên đúng dữ liệu này và được 18/18 không tín hiệu. "Phá cấu trúc" về bản chất gần momentum. Brief vẫn được làm vì một kết quả âm có thiết kế chặt đáng giá hơn việc tin lời quảng cáo. **Kết quả âm là kết quả hợp lệ, không phải thất bại của agent.**

---

## 1. Thiết kế ĐĂNG KÝ TRƯỚC — mọi tham số chốt ở đây, KHÔNG được đổi

Đổi bất kỳ tham số nào sau khi đã thấy dữ liệu là **tự lừa mình**. Mỗi lần thử một bộ tham số là thêm một phép so sánh mà hiệu chỉnh đa so sánh không tính tới. **Chạy phép đo thật ĐÚNG MỘT LẦN.** Nếu có lỗi code phải chạy lại, báo cáo **cả hai** lần chạy và nói rõ lỗi gì.

### 1.1 Dữ liệu (dùng lại hoàn toàn của đợt 85)

- Nguồn: `bars_derivative`, mã `VN30F1M_CONT`, đọc qua `load_is_bars()` của `scripts/screen_vn30f_intraday.py`. Hàm này đã áp niêm phong.
- IS: 03/04 → 31/07/2026. **Tập từ 01/08 trở đi vẫn niêm phong, KHÔNG đọc**, kể cả khi kết quả dương (xem §4).
- **Bỏ nến ATC 14:45** (phụ lục 26/09 của brief 85: ATC là cơ chế khớp khác). Mỗi phiên còn **48 nến** khớp lệnh liên tục. Lọc phiên bằng `filter_and_group_sessions(bars, expected_bars_per_session=48)`.
- Mốc tái lập (Claude đã chạy 26/09): **81 phiên, 3.888 hàng**.

### 1.2 Ba sự kiện SMC — định nghĩa chính xác

Mỗi sự kiện là một cột nhận giá trị **+1 / −1 / 0** tại nến `t`, **chỉ dùng nến ≤ t trong CÙNG phiên**. Không vượt phiên, không nhìn tương lai. Nến chưa đủ lịch sử thì là `None` (không phải 0).

**(a) `sweep` — quét thanh khoản rồi quay đầu.** Với `N = 12` (1 giờ), cần `t ≥ N`:
- `H = max(high[t-12 .. t-1])`, `L = min(low[t-12 .. t-1])`.
- `high[t] > H` **và** `close[t] < H` → **−1** (quét đỉnh, SMC đoán giá giảm).
- `low[t] < L` **và** `close[t] > L` → **+1** (quét đáy, SMC đoán giá tăng).
- Cả hai cùng xảy ra trong một nến (nến "râu hai đầu") → **0**, và đếm riêng số lần.
- Còn lại → 0.

**(b) `bos` — phá cấu trúc.** Đỉnh/đáy dao động (swing) theo **fractal k = 2**:
- Nến `j` là swing high nếu `high[j]` **lớn hơn hẳn** high của `j-2, j-1, j+1, j+2`. Swing low đối xứng với low.
- **Swing tại `j` chỉ được BIẾT từ nến `j+2`.** Tại nến `t`, chỉ dùng các swing có `j + 2 ≤ t`. **Đây là chỗ dễ nhìn trộm tương lai nhất của cả brief**, xem test §3.2.
- `S_h` = swing high đã xác nhận **gần nhất** tính tới `t−1`; `S_l` tương tự.
- `close[t-1] ≤ S_h` **và** `close[t] > S_h` → **+1**. `close[t-1] ≥ S_l` **và** `close[t] < S_l` → **−1**.
- Chưa có swing đã xác nhận → `None`. Không có phá cấu trúc → 0.

**(c) `fvg` — khoảng trống giá 3 nến.** Cần `t ≥ 2`:
- `low[t] > high[t-2]` → **+1**. `high[t] < low[t-2]` → **−1**. Còn lại → 0.

**Không đo order block.** Nó không có định nghĩa chặt duy nhất, và mỗi cách hiểu là một phép so sánh thêm.

### 1.3 Mục tiêu, và cách đo

- Mục tiêu: `fwd_1`, `fwd_3`, `fwd_6` (đơn vị **điểm**), đúng như đợt 85, trong cùng phiên.
- **Dùng lại, không chép:** hàng cơ sở lấy từ `compute_session_features_and_targets()` của `screen_vn30f_intraday.py`. Hàm này đã trả `fwd_1/3/6`, `ret_past_1`, `intrabar`. Chỉ **thêm** ba cột `sweep`, `bos`, `fvg` vào mỗi hàng.
- **Thống kê:** 3 sự kiện × 3 mục tiêu = **9 cặp**.
  - Chốt an toàn: `check_control_variable(rows, control_feature="intrabar", past_ret_col="ret_past_1", future_ret_col="fwd_1", min_rho=0.50)`. **Trượt thì dừng**, không in kết quả.
  - Ngưỡng FWER: gọi `run_block_permutation_test(panel_rows=rows, n_permutations=1000, block_size_hours=48, seed=42, feature_names=["sweep","bos","fvg"], target_names=["fwd_1","fwd_3","fwd_6"])` **ĐÚNG MỘT LẦN** cho cả 9 cặp. Ngưỡng P95 của max|rho| đã hiệu chỉnh đa so sánh. **Không** cộng thêm Bonferroni. (Tham số tên `block_size_hours` nhưng thực ra đếm **số hàng**; 48 hàng = 1 phiên.)
  - Mỗi cặp: `compute_leakage_pair(feat, ret_past_1, fwd)` cho `rho_truoc`, `rho_sau`, `n_sau`; `classify_signal(rho_sau, threshold)`.
- **Vì sao Spearman trên cột ba giá trị vẫn hợp lệ:** cột thưa (phần lớn là 0) làm rho nhỏ, nhưng phân phối null được hoán vị trên **chính cột thưa đó**, nên ngưỡng cũng thưa theo. Phép thử không lệch; chỉ có sức mạnh (power) phụ thuộc số sự kiện. Vì vậy phải báo số sự kiện (§1.4).

### 1.4 Ngưỡng kinh tế — điều kiện thứ hai, độc lập với thống kê

Với mỗi cặp, tính **biến động trung bình theo hướng sự kiện**: `m = trung bình của (fwd_k × dấu_sự_kiện)` trên các nến có sự kiện ≠ 0.

- Chi phí một vòng tính bằng **điểm**: `(derivative_side_cost(P, 1, opening=True) + derivative_side_cost(P, 1, opening=False)) / DERIVATIVE_CONTRACT_MULTIPLIER`, với `P` = **trung vị giá đóng cửa của IS**. **Dùng hàm của `trading/derivative_position.py`, không viết lại số 0,5.**
- Một cặp chỉ **ĐÁNG KỂ** khi **cả hai**: `classify_signal == "CO_TIN_HIEU"` **VÀ** `|m| > chi phí một vòng`.
- **Báo số sự kiện** cho từng cột: số +1, số −1, số nến "râu hai đầu" của `sweep`. Cột nào có **dưới 30** sự kiện ở một dấu thì ghi `IT_SU_KIEN — sức mạnh thấp`. Không kết luận âm hay dương cho cột đó.

---

## 2. Phạm vi

- **Được thêm:** `scripts/screen_vn30f_smc.py`, `tests/test_screen_vn30f_smc.py`.
- **Không được sửa:** `scripts/screen_vn30f_intraday.py`, `scripts/audit_information.py`, `scripts/leakage_audit.py`, `scripts/screen_vn_signal_candidates.py`, `trading/`, mọi file khác. Chỉ **import** từ chúng.
- **Cấm:** thêm sự kiện, đổi `N` hay `k`, thêm khung mục tiêu, thử "biến thể cho đẹp", đọc tập từ 01/08.
- Không commit, không push.
- Trước khi viết: `gitnexus_context` cho `compute_session_features_and_targets` và `run_block_permutation_test` để hiểu đầu vào/đầu ra. Sau khi viết: `gitnexus_detect_changes()`, dán kết quả. Hai file mới nên không cần `impact`.

---

## 3. Kiểm chứng (TDD: viết test trước, thấy đỏ, rồi mới viết code)

Test trên **phiên dựng tay**, không dùng DB.

### 3.1 Từng sự kiện, số tính tay
1. `sweep`: 12 nến có high tối đa 100; nến 13 high 101, close 99,5 → **−1**. Close 100,5 → **0**. Ca đối xứng cho +1. Ca râu hai đầu → **0**.
2. `bos`: dựng một swing high rõ ở `j`. Tại `t = j+1` swing **chưa** được biết → không được dùng. Tại `t ≥ j+2`, close vượt swing → **+1**. Ca đối xứng cho −1.
3. `fvg`: `low[t] = 105`, `high[t-2] = 104` → **+1**. `low[t] = 104` → **0** (bằng thì không phải khoảng trống). Ca đối xứng cho −1.
4. Thiếu lịch sử (`t < 12` với sweep, `t < 2` với fvg, chưa có swing với bos) → **`None`**, không phải 0.

### 3.2 Chống nhìn trộm tương lai — test quan trọng nhất
5. **Bất biến theo tương lai:** với một phiên bất kỳ, tính cả ba cột. Sau đó **sửa tùy ý mọi nến sau `t`** và tính lại. Cả ba cột tại nến `≤ t` phải **giống hệt**. Chạy cho **mọi** `t` trong phiên. Nếu `bos` dùng swing chưa xác nhận, test này phải bắt được.
6. **Không vượt phiên:** hai phiên nối nhau. Nến đầu phiên 2 không được dùng nến của phiên 1 (sweep của nến 0–11 phiên 2 phải là `None`).

### 3.3 Đường ống
7. Nến 14:45 bị loại: phiên dựng tay 49 nến (có 14:45) → sau lọc còn 48.
8. Ba cột được **thêm vào** hàng của `compute_session_features_and_targets()`, các cột cũ giữ nguyên giá trị (so từng khóa).
9. `m` (§1.4) tính đúng dấu: sự kiện −1 và `fwd = −2` → đóng góp **+2**.

### 3.4 Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo** trước. **Cấm** `git checkout`, `git restore`, `git stash`.
- Cho `bos` dùng swing ngay tại `j` (bỏ điều kiện `j+2 ≤ t`) → test 5 **phải đỏ**.
- Cho `sweep` dùng `high[t-12 .. t]` (gồm cả nến `t`) → test 1 phải đỏ.
- Cho `fvg` dùng `≥` thay cho `>` → test 3 phải đỏ.
- Khôi phục, chạy lại, sạch. Báo tên các test đỏ ở mỗi bước.

### 3.5 Tổng
```
uv run pytest -m "not integration" -q     # mốc: 891 passed
uv run ruff check trading tests scripts
```

---

## 4. Chạy thật, và quy tắc đọc kết quả

Chạy `uv run python scripts/screen_vn30f_smc.py` **một lần**. In theo đúng khuôn của đợt 85:
- số phiên, số hàng (phải là **81 / 3.888**; khác thì **dừng và báo**, không chạy tiếp);
- rho đối chứng và kết quả chốt an toàn;
- ngưỡng P95 FWER;
- bảng 9 dòng: sự kiện | mục tiêu | rho_truoc | rho_sau | n_sau | cờ thống kê | `m` (điểm) | chi phí (điểm) | **ĐÁNG KỂ / KHÔNG**;
- bảng số sự kiện theo §1.4.

**Đọc kết quả, không tự diễn giải thêm:**
- Không cặp nào ĐÁNG KỂ → ghi **"SMC dạng máy: KHÔNG có lợi thế sau chi phí trên VN30F1M IS"**. Đây là phép đo âm thứ sáu.
- Có cặp ĐÁNG KỂ → **KHÔNG mở tập niêm phong**, **KHÔNG xây chiến lược**. Chỉ báo cáo. Claude sẽ quyết có mở tập từ 01/08 hay không, và mở một lần duy nhất cho đúng cặp đó.
- Có cặp qua thống kê nhưng `|m|` dưới chi phí → ghi rõ là **"có thông tin nhưng không đủ trả phí"**. Không làm tròn thành "có tín hiệu".

---

## 5. Báo cáo cho Claude

1. GitNexus context và detect_changes.
2. Danh sách test, kiểm thử phá hoại (tên test đỏ từng bước).
3. Pytest và ruff.
4. **Nguyên văn** toàn bộ output của lần chạy thật. Nếu chạy hơn một lần, dán **tất cả** kèm lý do.
5. Mọi điều thấy ngoài phạm vi: **báo cáo, không sửa.**

---

## 6. Ghi chú của planner — chưa giao

- **Kiểm quét thanh khoản bằng sổ lệnh thật:** SMC nói "thanh khoản" là lệnh dừng nằm chờ quanh đỉnh/đáy. Sổ lệnh 10 bước giá ghi từ 25/09 cho phép đo thẳng điều đó, thay vì đoán từ hình nến. Cần khoảng 20 phiên (giữa tháng 10). Sẽ giao sau, và **chỉ nếu** đợt 98 không cho thấy `sweep` hoàn toàn vô nghĩa.
- **SMC trên cổ phiếu nến ngày:** chỉ chiều mua, có benchmark buy-and-hold. Chưa giao, vì phí 0,60% và không bán khống khiến kỳ vọng còn thấp hơn.
