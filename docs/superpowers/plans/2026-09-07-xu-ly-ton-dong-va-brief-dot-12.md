# Xử lý tồn đọng 07/09/2026 + Brief đợt 12

Người viết: Claude (planner) | HEAD lúc viết: `874689e`

---

## 0. Ba việc tồn của hôm nay — chỉ MỘT giao được cho agent

Tôi đã tự kiểm hệ thống trước khi viết, không suy đoán. Có 3 việc, nhưng khác
loại — gộp chung sẽ sai vai:

| # | Việc | Ai làm | Vì sao |
|---|---|---|---|
| 1 | **D1 — diễn tập dead-man's switch** | **Chủ dự án** | Đúng ngày đã hẹn (07/09). Kịch bản đã có sẵn từ 06/09: `docs/superpowers/plans/2026-09-07-kich-ban-dien-tap-dead-man-switch.md`. Cần thao tác Docker thật trên máy — theo quyết định C2, đây là việc "chủ dự án tự khởi động docker", không giao agent. |
| 2 | **Lệch triển khai (deploy drift) — MỚI phát hiện hôm nay** | **Chủ dự án** | `deploy_drift_check.py` báo image collector/engine **cũ hơn commit `fb57469` (đợt 10) đúng 14 phút**. Nghĩa là container đang chạy **thiếu** phần cuối của đợt 10: rất có thể thiếu fail-safe độ cũ vị thế (P1) và trần 100 cổ phiếu (Task 5) — hai thứ đợt 10 vừa thêm vào `real_orders.py`. Rebuild là thao tác Docker, cùng loại với #1 → chủ dự án làm, **nhưng đừng làm cùng lúc với diễn tập D1** (dễ lẫn nguyên nhân nếu cả hai xảy ra trong một cửa sổ). Khuyến nghị: rebuild **trước khi bắt đầu Chặng B của D1**, để diễn tập chạy trên image đã cập nhật, rồi mới tắt/bật cho diễn tập. |
| 3 | **Một chênh lệch dữ liệu chưa giải thích ở đợt 11** | **Agent** (brief dưới đây) | Brief đợt 11 đã cảnh báo trước và agent không phản hồi — xem mục 1. |

Việc 1 và 2 không cần brief — đã đủ thông tin ở bảng trên, chủ dự án tự thực hiện.
Phần còn lại của tài liệu này là brief cho việc 3.

---

## 1. Vì sao việc 3 cần làm — không phải fabricate ra việc

Brief đợt 11 (`d6dbda0`) đã viết rõ:

> "Một chênh lệch tôi chưa giải thích được và không bịa lý do: IJC có 4.719 bar /
> 104 ngày ≈ 45 bar/ngày, thấp hơn quy ước 51 khoảng 12%. [...] Nếu agent thấy
> dấu hiệu `bars` không phải 5 phút thuần thì dừng và báo cáo."

Báo cáo đợt 11 (`874689e`) **không nhắc gì tới điều này** — không xác nhận, không
bác bỏ. Tôi tự đào tiếp hôm nay và thấy vấn đề còn cụ thể hơn ban đầu tưởng, đáng
để điều tra riêng:

**Phân bố số bar/ngày của IJC (310 ngày dữ liệu, mẫu tự kiểm):**

| Số bar/ngày | Số ngày |
|---|---|
| 1 | 1 |
| 41 | 3 |
| 42 | 2 |
| 43 | 4 |
| 44 | 10 |
| **46** | **47** (phổ biến nhất) |
| 48 | 1 |
| 49 | 3 |
| 50 | 1 |
| 51 | 4 (đúng lý thuyết) |
| 52 | 4 (**vượt** 51 — về mặt lý thuyết là không thể nếu đúng 1 phiên VN) |

Và bar đầu ngày của một phiên điển hình (05/08/2026) là **09:15 giờ VN**
(`02:15 UTC`), không phải 09:00 — thiếu ngay 3 bar mở đầu.

**Ba điều này cùng chỉ một hướng:** `bars` (5m) không hoàn chỉnh theo một cách có
hệ thống, không phải nhiễu ngẫu nhiên. Có 52-bar-ngày (vượt lý thuyết) gợi ý còn
có khả năng trùng lặp hoặc lẫn dữ liệu, không chỉ thiếu.

**Mức độ nghiêm trọng với kết luận đợt 11:** tôi **không** cho rằng phát hiện này
đủ sức đổi kết luận "không có edge" (PF 0,47 quá xa ngưỡng 1,3 để một vài phần
trăm bar thiếu lật ngược). Nhưng nó làm giảm độ tin của **chính con số cỡ mẫu**
(574 lệnh có thể lẽ ra là ~620 lệnh nếu đủ bar), và ảnh hưởng trực tiếp tới quy
ước `periods_per_year cho Sharpe` nếu ngày nào cũng thiếu bar hệ thống. Cần biết
rõ trước khi dùng số đợt 11 làm căn cứ cho quyết định Tier 1.

---

## 2. Brief đợt 12 — Task duy nhất: điều tra độ đầy đủ của `bars` (5m)

### Mục tiêu
Trả lời: **thiếu/thừa bar là do đâu**, và **có hệ thống hay ngẫu nhiên**. Đây là
task **điều tra, không phải sửa**. Không backfill, không đổi schema, không đổi
logic aggregator trong task này.

### File được đọc / tạo
- **TẠO MỚI:** `scripts/probe_bars_5m_completeness.py` (script chỉ đọc, in báo cáo).
- **KHÔNG SỬA:** bất cứ file nào trong `trading/`, `trading/collector/`,
  `trading/bus/`. Đây là điều tra, không phải vá.
- Được đọc (không sửa) để hiểu logic hiện có: `trading/collector/aggregator.py`
  (nếu tồn tại — tự tìm bằng `gitnexus_query` hoặc `grep`, đừng đoán tên file),
  `trading/collector/backfill.py`.

### Phải trả lời — bốn câu hỏi cụ thể
1. **Bar đầu ngày:** trên toàn bộ 310 mã, bar đầu tiên mỗi ngày là mấy giờ (VN)?
   Phân bố ra sao — luôn là 09:15, hay dao động? Nếu luôn trễ đúng 15 phút, đó là
   dấu hiệu hệ thống (ví dụ: warmup của collector, hoặc quy ước "bar 5m gắn nhãn
   theo giờ đóng nên bar 09:00-09:05 mang nhãn 09:05" — **kiểm tra giả thuyết này
   trước khi kết luận là bug**, đối chiếu với cách `trading/collector/aggregator.py`
   gắn nhãn timestamp).
2. **Ngày có > 51 bar (vượt lý thuyết):** liệt kê toàn bộ, kiểm có bản ghi trùng
   `(symbol, ts)` hay không (`SELECT symbol, ts, count(*) FROM bars GROUP BY
   symbol, ts HAVING count(*) > 1`).
3. **Phân bố số bar/ngày toàn rổ 310 mã** (không chỉ IJC) — bảng tần suất giống
   mục 1 ở trên nhưng cho toàn bộ, để biết đây là vấn đề của một mã hay hệ thống.
4. **Nếu tìm ra nguyên nhân cụ thể** (vd: lỗi timezone, lệch nhãn bar, khoảng dừng
   backfill), nêu rõ; **nếu không tìm ra**, nói thẳng là không tìm ra — không suy
   diễn cho có kết luận.

### Ràng buộc
- Đây là **task đọc dữ liệu, không sửa dữ liệu**: không `UPDATE`/`DELETE`/`INSERT`
  vào `bars`.
- Không kết luận thay tôi về việc "có cần backfill lại không" — chỉ báo cáo sự
  thật quan sát được. Quyết định backfill (nếu cần) sẽ là brief riêng, sau khi có
  nguyên nhân.
- Trước khi đọc code aggregator: `gitnexus_context` hoặc `gitnexus_query` để định
  vị đúng file, tránh đoán nhầm.
- Không commit, không push. Không đụng `config/config.yaml`.

### Tiêu chí kiểm chứng
1. Dán output thô đầy đủ của script cho cả 4 câu hỏi.
2. Nếu giả thuyết "nhãn bar theo giờ đóng" đúng, chứng minh bằng cách trích dẫn
   đúng dòng code trong aggregator gắn nhãn timestamp, không chỉ suy luận bằng lời.
3. Nếu tìm thấy bản ghi trùng `(symbol, ts)`, dán ví dụ cụ thể (symbol, ts, giá trị
   hai bản ghi khác nhau ở đâu).
4. `uv run ruff check scripts` sạch cho file mới.

---

## 3. Cái brief này CỐ Ý không giao

- **Backfill lại dữ liệu 5m** — chờ biết nguyên nhân trước, tránh backfill sai lần hai.
- **Sửa aggregator/collector** — ngoài phạm vi điều tra; nếu tìm ra bug thật,
  báo cáo lại để tôi viết brief sửa riêng, có kiểm chứng trước/sau đầy đủ.
- **Đo lại đợt 11 với dữ liệu đã lọc/sửa** — chưa cần, vì kết luận "không có edge"
  đủ khoảng cách an toàn (PF 0,47 vs ngưỡng 1,3) để không phụ thuộc vào việc này.
