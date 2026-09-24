# Brief đợt 85 — Sàng lọc tín hiệu trong phiên trên VN30F1M, và chặn bẫy múi giờ lần thứ năm

Ngày giao: 24/09/2026.
Base: main `73a5201`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh

Đợt 82–84 dựng được chuỗi liên tục `VN30F1M_CONT` trong bảng riêng `bars_derivative`, đã dọn nến
hỏng, và biết chính xác lỗ ở đâu (118 phiên, 03/04→24/09; thiếu 06/07; 07/07 chỉ 1 nến; 6 phiên 48
nến đều rơi vào tháng 8–9).

Brief này có **một việc chính** và **hai việc vệ sinh nhỏ**:

- **Task 3 (chính):** sàng lọc xem có đặc trưng trong phiên nào mang tín hiệu dự báo trên hợp đồng
  thanh khoản nhất thị trường (99,37% khối lượng). Bước này **không cần biểu phí** — tương quan hạng
  không liên quan chi phí. Đây là "nửa cửa 3" mở được trước cửa 2.
- **Task 1–2 (vệ sinh):** cái bẫy `date(ts)` lệch múi giờ đã cắn **bốn lần** (03/09, đợt 83, đợt 84
  hai chỗ). Hai lần sửa gần nhất (`1095c37`, `73a5201`) **không có test hồi quy** — không gì ngăn lần
  thứ năm.

---

## 1. Ràng buộc chung

- Được sửa/thêm: `scripts/build_derivative_continuous_series.py` (**chỉ** Task 1), một file test chặn
  bẫy mới (Task 2), `scripts/screen_vn30f_intraday.py` (**file mới**, Task 3) + test của nó.
- **Không** sửa `scripts/leakage_audit.py`, `scripts/audit_information.py`,
  `scripts/screen_vn_signal_candidates.py`. Task 3 **import và dùng lại** lõi đo của chúng — "một
  công thức, một chỗ". Không chép hàm, không viết lại tương quan hạng.
- **Không** sửa `trading/`. **Không** ghi gì vào DB trong Task 3 (chỉ đọc).
- **Không** đặt lệnh. **Không** restart/build container — phiên 24/09 đang chạy.
- Không thêm dependency. Không commit, không push.
- Nền hiện tại: **775 passed**, ruff sạch.

---

## Task 1 — Test hồi quy cho lỗi múi giờ trong script build

Lỗi ở `build_derivative_continuous_series.py` nằm trong câu SQL dựng "ngày giao dịch kỳ vọng" — và
câu đó đang nằm **bên trong `main_async`**, hàm còn gọi SSI, nên không test được.

1. Tách đúng câu truy vấn đó ra một hàm riêng, ví dụ
   `load_expected_trading_days(storage, lo: date, hi: date, holidays) -> list[date]`. **Chỉ di chuyển,
   không đổi logic** — `main_async` gọi hàm mới, kết quả phải y hệt.
2. Viết **integration test** (đánh dấu `integration`, chạy trên `trading_test`): chèn vào `bars_daily`
   hai dòng tại **00:00 giờ VN** — một cho **thứ Hai 2026-07-06**, một cho **thứ Sáu 2026-07-10** — rồi
   gọi hàm. Kỳ vọng trả về **đúng** `[2026-07-06, 2026-07-10]`.
   Đây là hai ngày dễ sai nhất: với `date(ts)` theo UTC, thứ Hai thành Chủ nhật (bị loại) và thứ Sáu
   thành thứ Năm (sai nhãn).
3. **Kiểm thử phá hoại:** tạm đổi truy vấn về `date(ts)`, xác nhận test **đỏ**, dán dòng lỗi. Khôi
   phục, xác nhận xanh.

---

## Task 2 — Test chặn bẫy `date(ts)` ở mọi nơi trong repo

Một test (không cần DB) quét mọi file `.py` trong `trading/` và `scripts/`, tìm **chuỗi SQL** chứa
`date(ts)` / `date(x.ts)` hoặc `ts::date` mà **không** quy về giờ VN, và báo đỏ nếu có.

**Lưu ý báo giả — đã có sẵn hai chỗ nhắc tới mẫu này một cách hợp lệ:**
- comment tôi viết ở `build_derivative_continuous_series.py` ("KHONG dung date(ts)...");
- docstring `trading/storage/db.py` quanh dòng 854 ("thay vì `ts::date`").
Test **không được** báo đỏ vì chúng. Gợi ý: dùng `tokenize` để chỉ xét token chuỗi, và chỉ coi là SQL
khi chuỗi chứa từ khoá SQL (`SELECT`/`WHERE`/`GROUP BY`/`FROM`). Bạn được chọn cách khác, nhưng phải
đạt đủ **ba** tiêu chí dưới.

**Tiêu chí hoàn thành — đủ cả ba, không chỉ một** (bài học trực tiếp từ đợt 84, xem mục 4):
1. **Bắt đúng:** test đơn vị cho hàm quét, trên chuỗi dựng tay: `"SELECT date(ts) FROM bars"` → bắt;
   `"SELECT ts::date FROM bars_daily"` → bắt; `"... WHERE date(b.ts) = %s"` → bắt.
2. **Không báo giả:** `"SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM bars_daily"` → **không**
   bắt; một comment `# KHONG dung date(ts)` → **không** bắt; một docstring nhắc `ts::date` mà không có
   từ khoá SQL → **không** bắt. **Và chạy trên repo hiện tại phải ra 0 vi phạm.**
3. **Mẫu số:** test in ra (hoặc assert) **số file đã quét và số chuỗi SQL đã kiểm**. Nếu con số đó là
   0 hoặc nhỏ bất thường, bộ quét đang không nhìn thấy gì — một bộ quét mù thì "0 vi phạm" là vô nghĩa.
   Để tham khảo: grep của tôi thấy khoảng 30 truy vấn quy đổi giờ VN trong repo.
4. **Kiểm thử phá hoại:** tạm chèn một câu `"SELECT date(ts) FROM bars"` vào một file script, xác nhận
   test repo **đỏ** và chỉ đúng file đó. Gỡ ra, xác nhận xanh.

---

## Task 3 — Sàng lọc tín hiệu trong phiên trên `VN30F1M_CONT`

### 3.1. Thiết kế đã đăng ký trước — KHÔNG được đổi, KHÔNG được thêm

Mọi lựa chọn dưới đây tôi chốt **trước** khi thấy dữ liệu. Được đổi sau khi thấy kết quả là cách chắc
chắn nhất để tự lừa mình. Nếu thấy một lựa chọn sai về kỹ thuật, **dừng và báo** — đừng tự sửa.

**Dữ liệu và niêm phong:**
- Nguồn: `bars_derivative`, symbol `VN30F1M_CONT`, đọc qua `Storage.read_derivative_bars`.
- **Tập đo (IS): 2026-04-03 → 2026-07-31.** Tôi đã tự đếm: **82 phiên, 3.970 nến** trước khi loại;
  sau khi loại 07/07 (1 nến) còn **81 phiên, 3.969 nến** (= 81 × 49). Đây là **mẫu số** bạn phải khớp
  — lệch là dấu hiệu nạp sai, dừng và báo.
- **Tập giữ lại: từ 2026-08-01 trở đi — KHÔNG ĐỌC, KHÔNG TÍNH.** Code phải `assert` nến lớn nhất được
  nạp < `2026-08-01 00:00 VN`, và phải có test cho assert đó. Tập này để dành cho một phép kiểm xác nhận
  **nếu** đợt này thấy tín hiệu. Đọc nó bây giờ là đốt nó.
- **Loại mọi phiên có số nến ≠ 49.** Trong IS, đó là 07/07 (1 nến); 06/07 vốn không có. Báo cáo phải
  liệt kê phiên nào bị loại.

**Đơn vị: ĐIỂM, không phải phần trăm.** Chuỗi được back-adjust bằng **hiệu số** (Panama, đợt 83), tức
đã dịch mức giá quá khứ tới −37,60 điểm. Hiệu giá giữa hai nến được bảo toàn tuyệt đối, **tỷ lệ phần
trăm thì không**. Nên mọi đặc trưng và mục tiêu tính bằng **hiệu số điểm**. Dùng phần trăm trên chuỗi
Panama là đo sai chính đại lượng mà back-adjust đã giữ đúng.

**Không vượt phiên.** Mọi đặc trưng chỉ dùng nến **trong cùng phiên, tại hoặc trước t**. Mọi mục tiêu
chỉ dùng nến **trong cùng phiên, sau t**. Không đủ nến trong phiên → `None`. Lý do: vượt phiên là trộn
khoảng trống qua đêm vào — một hiện tượng khác hẳn.

**Mục tiêu — 3 khung:** `fwd_h = close[t+h] − close[t]`, với `h ∈ {1, 3, 6}` nến (5, 15, 30 phút).

**Đặc trưng — đúng 6, không thêm:**

| Tên | Công thức (điểm) |
|---|---|
| `mom_1` | `close[t] − close[t−1]` |
| `mom_6` | `close[t] − close[t−6]` |
| `range_1` | `high[t] − low[t]` |
| `vol_ratio_12` | `volume[t] / trung bình(volume[t−12 … t−1])` — **không** gồm `t`, như đợt 76 |
| `dist_open` | `close[t] − open` của nến đầu phiên |
| `bar_index` | thứ tự nến trong phiên, 0…48 |

**Đối chứng (chốt an toàn) — phải qua trước khi đọc bất cứ số nào:** đặc trưng `intrabar =
close[t] − open[t]` so với quá khứ `ret_past_1 = close[t] − close[t−1]`. Hai đại lượng này gần như
cùng một chuyển động, nên `rho_truoc` phải **> 0,50**. Nếu không qua → đường ống bị lệch pha (off-by-one)
→ **dừng, báo cáo, không in bảng kết quả**. Dùng `compute_leakage_pair` như `check_intraday_control` ở
đợt 76.

**Ngưỡng và hiệu chỉnh đa so sánh — đọc kỹ, đây là chỗ dễ sai nhất:**
- Gọi `run_block_permutation_test` (`scripts/audit_information.py`) **đúng MỘT lần**, với
  `feature_names` = 6 đặc trưng và `target_names` = **cả 3 mục tiêu**. Hàm này lấy `max(|rho|)` qua
  **mọi** cặp trong mỗi lần hoán vị, nên ngưỡng P95 nó trả về **đã kiểm soát sai số toàn họ (FWER)**
  cho cả 18 cặp.
- **KHÔNG** gọi riêng cho từng mục tiêu — làm vậy thì mỗi ngưỡng chỉ kiểm soát 6 cặp và tổng thể không
  còn được kiểm soát.
- **KHÔNG** áp Bonferroni lên trên — ngưỡng đã hiệu chỉnh rồi, hiệu chỉnh thêm là đếm hai lần.
- `block_size_hours = 49`. **Tên tham số này nói dối**: nó đếm **số hàng**, không phải giờ (đã ghi nhận
  từ đợt 76). 49 hàng = đúng một phiên, giữ nguyên tự tương quan trong phiên.
- `n_permutations = 1000`, `seed = 42`.
- Gắn cờ từng cặp bằng `classify_signal(rho_sau, threshold)` từ `screen_vn_signal_candidates.py`.

### 3.2. Kiểm chứng

1. **Test công thức đặc trưng, tính tay:** một phiên giả 49 nến với giá dựng tay; kiểm từng đặc trưng
   ở ít nhất hai vị trí t, **bằng số tính tay**, kể cả vị trí đầu phiên phải ra `None`.
2. **Test không vượt phiên:** hai phiên liền nhau; mục tiêu `fwd_6` ở nến thứ 45 của phiên đầu phải là
   `None` (nếu tính sẽ lấn sang phiên sau); đặc trưng `mom_6` ở nến thứ 2 của phiên sau phải là `None`.
3. **Test niêm phong:** đưa vào một nến ngày 2026-08-03 → hàm nạp phải báo lỗi.
4. **Đối chứng dương trên dữ liệu giả:** dựng một đặc trưng **cố tình rò rỉ** (bằng chính `fwd_1` cộng
   nhiễu nhỏ) → sàng lọc phải gắn `CO_TIN_HIEU`. Chứng minh đường ống **có khả năng** thấy tín hiệu.
5. **Đối chứng âm:** đặc trưng nhiễu ngẫu nhiên thuần → phải `KHONG_TIN_HIEU`.
6. **Kiểm thử phá hoại:** dịch mục tiêu lệch một nến (dùng `close[t+h+1]`) trong test số 1, xác nhận
   test đỏ.

### 3.3. Báo cáo — chỉ số, cấm diễn giải

In nguyên văn:
- Số phiên IS, số phiên bị loại (kèm ngày), số nến dùng.
- `rho` đối chứng và kết quả chốt an toàn.
- Ngưỡng P95 FWER.
- Bảng 18 dòng: `đặc trưng | khung | rho_truoc | rho_sau | n_sau | cờ`.

**Cấm tuyệt đối:** không giải thích *vì sao* một đặc trưng có hoặc không có tín hiệu, không gợi ý chiến
lược, không đề xuất đặc trưng mới, không đọc tập giữ lại "để kiểm tra thêm". Diễn giải là việc của tôi —
đợt 77 đã cho thấy vì sao: một con số trông như phát hiện lớn đã chết khi hiệu chỉnh đa so sánh.

---

## 2. Không làm

- Không sửa `leakage_audit.py`, `audit_information.py`, `screen_vn_signal_candidates.py`, `trading/`.
- Không đổi thiết kế đã đăng ký ở 3.1. Không thêm đặc trưng, khung, hay tham số.
- Không đọc dữ liệu từ 2026-08-01. Không ghi vào DB.
- Không backtest, không tính lãi/lỗ, không đụng biểu phí.
- Không đặt lệnh. Không restart/build container. Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: tên hàm đã tách, kết quả integration test, dòng test đỏ khi phá hoại.
2. Task 2: số file quét và số chuỗi SQL kiểm; kết quả ba nhóm test; dòng đỏ khi phá hoại.
3. Task 3: toàn bộ mục 3.3 nguyên văn, cùng kết quả 6 nhóm test ở 3.2.
4. `uv run pytest -m "not integration" -q` (nền **775**), suite đầy đủ, `uv run ruff check trading tests
   scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Ghi chú của planner — không phải việc của agent

**Vì sao Task 2 có ba tiêu chí:** ở brief 84 tôi viết tiêu chí cho công cụ tố giác lỗ chỉ là "phải nêu
06/07 và 07/07". Agent đạt đúng tiêu chí đó trong khi công cụ không bao giờ kiểm thứ Sáu. Một công cụ
báo *mọi ngày đều lỗi* cũng qua được tiêu chí kiểu đó. Từ đợt này, mọi công cụ phát hiện phải chứng
minh cả **bắt đúng**, **không báo giả**, và **mẫu số đúng**.

**Kỳ vọng trung thực cho Task 3:** dự án đã có bốn phép đo âm liên tiếp (crypto, VN regime-timing, VN
kỹ thuật 3 mã, VN kỹ thuật 48 mã). Tôi không kỳ vọng phái sinh khác. Nhưng có hai lý do đây vẫn là phép
thử đáng làm: lần đầu đo ở tần suất **trong phiên** thay vì ngày, và trên công cụ **thanh khoản nhất**
thị trường — nơi nếu có vi cấu trúc khai thác được thì nó sẽ lộ ra trước tiên.

Nếu có cặp nào vượt ngưỡng: chưa phải lợi thế. Bước tiếp theo sẽ là kiểm xác nhận trên tập giữ lại
tháng 8–9 — mà muốn thế thì tập đó phải **còn nguyên**, đó là lý do niêm phong. Nếu không cặp nào vượt:
đó là phép đo âm thứ năm, và là câu trả lời dứt khoát rằng dữ liệu giá/khối lượng công khai không đủ
cho hướng này.
