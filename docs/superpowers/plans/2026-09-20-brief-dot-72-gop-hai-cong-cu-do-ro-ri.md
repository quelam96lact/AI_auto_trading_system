# Brief đợt 72 — Gộp hai công cụ đo rò rỉ thành một, sửa lỗi lập kế hoạch của tôi

Ngày giao: 20/09/2026, cập nhật 21/09/2026.
Base: main `563743a` (đã qua đợt 73/74/75 — không đụng gì tới
`scripts/leakage_audit.py` hay `scripts/probe_timestamp_semantics.py`, đã kiểm bằng `git log`
trước khi cập nhật brief này; nội dung nhiệm vụ dưới đây không đổi).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Đây là dọn hậu quả của một lỗi do tôi gây ra

Tôi viết brief đợt 71 (máy dò rò rỉ nhìn trước) mà **không kiểm lại đợt 42**. Hậu quả: repo giờ có
**hai công cụ trả lời cùng một câu hỏi**, bằng hai luật khác nhau:

| | `scripts/probe_timestamp_semantics.py` (đợt 42, 208 dòng) | `scripts/leakage_audit.py` (đợt 71, 449 dòng) |
|---|---|---|
| Tương quan | **Pearson** | **Spearman** |
| Đầu vào | cột **thô** từ DB | đầu ra **`build_feature_panel`** (9 đặc trưng) |
| Luật gắn cờ | bất đối xứng `\|corr_sau\|−\|corr_truoc\|` so ±0,03 (số cố định) | `rho_sau > rho_truoc` **và** vượt ngưỡng hoán vị khối |
| Đối chứng | kỳ vọng `delta` ≈ +0,75 | chốt cứng `>0,3`, ném `RuntimeError` |

Hai bản **có thể cho kết luận khác nhau trên cùng một đặc trưng**, vì luật ngưỡng khác nhau. Đó là
đúng loại nợ mà dự án này đã dọn nhiều lần ("một công thức, một chỗ"). Lần này người gây ra là tôi,
không phải agent — agent làm đúng brief tôi viết.

## 0.1. Việc KHÔNG làm trong đợt này, đã có kết quả rồi

**Đừng chạy lại kiểm toán 27 cặp.** Đợt 42 §3 đã làm đầy đủ *sau khi* vá rò rỉ: 9 đặc trưng × 3
chân trời, hoán vị khối 48h × **1.000 lần**, ngưỡng null P95 = **0,075288**, và **27/27 cặp KHÔNG
vượt ngưỡng** (|ρ| lớn nhất 0,062). Đối chứng dương `ctrl_cheat` = +0,9995, đối chứng âm
`ctrl_noise` = −0,0082 — phép đo tự chứng minh nó đủ nhạy.

Kết luận đó **đã đóng**. Đợt này chỉ dọn công cụ, không đo lại kết luận.

---

## 1. Ràng buộc

- **Không thêm dependency** (repo thuần Python).
- **Không sửa `trading/feature_panel.py`**, không sửa `scripts/audit_information.py`.
- **Không chạy lại kiểm toán 27 cặp** (mục 0.1).
- **Không đụng dữ liệu năm 2026** ngoài phần giá cần để gán nhãn forward-return cho hàng cuối kỳ
  IS — và **nói rõ trong báo cáo** bạn đọc tới mốc nào, vì sao. (Báo cáo đợt 71 từng khẳng định
  "không đụng 2026" trong khi code đọc tới `2026-01-02`; hành vi đúng, lời khẳng định sai.)
- Không commit, không push.

---

## Task 1 — Một lõi đo, một luật gắn cờ

### 1.1. Chọn luật, đóng băng

Giữ **luật của đợt 71** làm luật chính thức:

- Tương quan: **Spearman** (bền với ngoại lai và quan hệ phi tuyến đơn điệu — hợp dữ liệu tài
  chính hơn Pearson).
- Ngưỡng: **hoán vị khối**, không dùng số cố định ±0,03. Ngưỡng do dữ liệu quyết định, không do
  người chọn.
- Cờ: `NGHI_VAN` khi `rho_sau > rho_truoc` **và** `|rho_sau|` vượt ngưỡng; còn lại `SACH`.
- Chốt an toàn đối chứng **bắt buộc**, ném `RuntimeError` khi không đạt.

Ngưỡng ±0,03 của đợt 42 là số chọn tay; cách hoán vị thay thế nó bằng ngưỡng rút từ chính dữ liệu.
**Ghi rõ trong docstring rằng luật cũ đã bị thay và vì sao**, để người đọc bảng cũ của đợt 42 không
tưởng hai bên mâu thuẫn.

### 1.2. Giữ CẢ HAI đường vào

Đây là điểm dễ làm hỏng nhất. Hai công cụ khác nhau ở **đầu vào**, và **cả hai đều cần**:

- **cột thô từ DB** — dùng khi thẩm định một cột **mới, chưa được đưa vào feature panel**. Đây
  chính là ca dùng quan trọng nhất về sau: mỗi ứng viên đặc trưng mới phải qua cửa này *trước khi*
  vào panel.
- **đầu ra `build_feature_panel`** — dùng khi soát lại 9 đặc trưng đã có.

Gộp lõi đo (tính `rho_truoc`/`rho_sau`, chạy hoán vị, gắn cờ, chốt an toàn) vào **một** nơi; hai
đường vào chỉ là lớp mỏng chuẩn bị dữ liệu rồi gọi lõi đó.

### 1.3. Kết cục về file

Sau khi gộp: **chỉ còn một** công cụ chẩn đoán. Xoá hoặc biến `probe_timestamp_semantics.py` thành
lớp vỏ gọi lõi chung — **bạn chọn**, nhưng nêu rõ lý do trong báo cáo, và **không được để lại hai
bản lõi**.

Nếu xoá: kiểm trước xem có tài liệu/script nào tham chiếu tới nó không (grep cả `docs/`), và liệt
kê những chỗ đó trong báo cáo.

---

## Task 2 — Bằng chứng: công cụ gộp phải tái hiện CẢ HAI phát hiện lịch sử

Đây là tiêu chí nghiệm thu quan trọng nhất. Công cụ mới phải dựng lại được hai kết quả đã biết:

1. **Đối chứng** `delta` / `delta_norm` phải ra `rho_truoc` mạnh dương (đợt 42 đo Pearson
   **+0,7531**; đợt 71 đo Spearman **+0,6680** — hai thước khác nhau nên hai số khác nhau là bình
   thường, miễn **mạnh dương và vượt chốt 0,3**).
2. **`taker_ls_vol_ratio` ở `metric_lag_minutes=0`** phải bị gắn `NGHI_VAN`, và ở `lag=5` phải
   `SACH`. Đợt 71 đo được `rho_sau = +0,1743` ở lag=0 — **trùng khít con số đợt 41 từng tưởng là
   tín hiệu**. Công cụ gộp phải cho lại đúng bức tranh đó.

Nếu **không** tái hiện được, **dừng lại và báo cáo** — nghĩa là việc gộp đã làm đổi hành vi, và
đó là lỗi, không phải "kết quả mới".

**Lưu ý thời gian chạy:** tôi đã tự chạy `--compare-lag` ở đợt 71, mất **hơn 10 phút** (500 hoán vị
× 9 đặc trưng × 2 cấu hình, Python thuần). Hãy liệu số lần hoán vị cho hợp lý và **ghi rõ bạn dùng
bao nhiêu lần** — đợt 42 dùng 1.000, đợt 71 dùng 500.

---

## Task 3 — Test

Gộp hai bộ test hiện có, giữ **mọi** hành vi đã được kiểm:

1. Bốn test bắt buộc của đợt 71 (rò rỉ nhân tạo → `NGHI_VAN`; sạch nhân tạo → `SACH`; ngẫu nhiên →
   `SACH` với cả hai rho gần 0; chốt an toàn hỏng → `RuntimeError`).
2. Test của `probe_timestamp_semantics` (nếu có) — nếu một test cũ kiểm luật ±0,03 nay đã bị thay,
   **ghi rõ cũ → mới và vì sao**, đúng như tiền lệ đợt 56 §1.3b. Không lặng lẽ xoá test.
3. **Test mới**: cùng một chuỗi dữ liệu, đưa qua **cả hai đường vào** (cột thô và panel) → phải ra
   **cùng** `rho_truoc`/`rho_sau`. Đây là test chứng minh việc gộp thật sự cho một kết quả duy
   nhất, chứ không phải hai nhánh song song đội lốt.

`uv run pytest -m "not integration" -q` (hiện **717 passed, 118 deselected** — số này đã đổi hai
lần từ lúc brief viết, đừng dùng nó làm mốc so sánh cứng, chỉ dùng để biết bạn đứng ở baseline
nào; **con số đúng để báo cáo là con số bạn đọc được trên màn hình sau khi gộp**, không phải số
này) và `uv run ruff check trading tests scripts`.

---

## 4. Báo cáo cho Claude

1. `git diff` các file đụng tới; nói rõ số phận của `probe_timestamp_semantics.py` và lý do.
2. Danh sách nơi tham chiếu tới file bị xoá/đổi (grep cả `docs/`).
3. Bằng chứng Task 2 — hai phát hiện lịch sử được tái hiện, kèm số lần hoán vị đã dùng.
4. Bảng "test nào đổi, cũ → mới, vì sao" (nếu có).
5. Kết quả test đường-vào-kép (Task 3.3).
6. Tổng số test và `ruff`.
