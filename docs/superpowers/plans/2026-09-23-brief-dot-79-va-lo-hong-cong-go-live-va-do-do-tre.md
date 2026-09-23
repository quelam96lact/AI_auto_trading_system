# Brief đợt 79 — Vá hai lỗ hổng cổng go-live, và đo độ trễ xử lý trước khi tối ưu

Ngày giao: 23/09/2026 (thứ Tư, tối).
Base: main `24851f0`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh — vì sao có brief này

Chủ dự án hỏi hệ thống có sẵn sàng go-live 24/09 không. Tôi tự kiểm tra và phát hiện **hôm nay
23/09 toàn bộ stack đã chết suốt cả phiên giao dịch**, nhưng cổng go-live vẫn báo **EXIT 0 — ĐỦ
ĐIỀU KIỆN**. Bằng chứng nguyên văn tôi tự thu được:

- `logs/deploy-drift.log`: `2026-09-23 11:01:40 deploy-drift SKIP: docker chua chay` kèm
  `[CRITICAL] Docker khong chay luc 11:03 ngay giao dich 23/09.`
- `logs/engine_alerts.log`: dòng cuối trước khi chết là `2026-09-22T07:50:35Z` (= 22/09 14:50 VN),
  dòng tiếp theo là `2026-09-23T15:10:37Z` (= 23/09 **22:10 VN**). Engine không xử lý một nến nào
  của phiên 23/09.
- Dù vậy `scripts/check_golive_gate.py` chạy lúc 22:14 VN vẫn cho tiêu chí 6 trạng thái **[ĐẠT]**
  với ghi chú `100.0% (do luc 22/09 15:10, 1 ngay truoc)`, và tổng kết EXIT 0.

**Đây đúng loại lỗi FEE-ALARM-2: chuông báo chết câm còn tệ hơn không có chuông báo.** Cổng go-live
là công cụ có thẩm quyền cao nhất để quyết định bật tiền thật; nó vừa cho đèn xanh vào đúng ngày hệ
thống chết trắng một phiên.

Ngoài ra, chuỗi log khởi động tối nay lộ thêm một điều kiện **đang sai ngay lúc này**:

```
2026-09-23T15:10:38Z  warm-up HPG xong  bars=201  until="2026-09-22 07:45:00+00:00"   (= 22/09 14:45 VN)
2026-09-23T15:16:xx   backfill done     counts={"HPG": 46, "IJC": 44, "AAA": 46}      (nến của 23/09)
```

Warm-up chạy **trước** backfill 5,5 phút, nên cửa sổ chỉ báo trong bộ nhớ engine hiện dừng ở 22/09
14:45, trong khi DB đã có đủ nến 23/09. Đây chính là ca [[warm-up-chay-truoc-backfill]] mà GAP-1
(đợt 74/75) được thiết kế để **phát hiện** — nhưng GAP-1 chỉ cảnh báo, không tự vá.

---

## 1. Ràng buộc

- Chỉ đụng vào: `scripts/check_golive_gate.py`, `tests/test_check_golive_gate.py`, và **một script
  đo mới** ở Task 3.
- **Không** sửa `trading/engine/main.py`, **không** sửa `trading/collector/main.py`, **không** đụng
  logic GAP-1, **không** đụng warm-up. (Xem mục 4 — đó là quyết định của chủ dự án, chưa giao.)
- Không thêm dependency mới (không scipy, không pandas nếu repo chưa có).
- Không khởi động lại/tắt container.
- Không commit, không push.
- Kiểm GitNexus trước khi sửa: `gitnexus_impact` trên hàm bị sửa, `gitnexus_detect_changes` sau khi
  sửa. Nếu MCP GitNexus không kết nối được, ghi rõ trong báo cáo là đã thử và không dùng được —
  **không im lặng bỏ qua**.

---

## Task 1 — Tiêu chí 6 phải chết khi số đo không thuộc phiên giao dịch gần nhất

**Lỗi hiện tại (tôi đã đọc code, không suy đoán):** trong `build_gate_items()`,
`scripts/check_golive_gate.py:271-317`, biến `stream_age_sec` **chỉ được dùng để ghép chuỗi hiển
thị** (`measured_val_str`, dòng 274-286). Nhánh PASS/WARN/FAIL ở dòng 288/298/308 quyết định
**duy nhất** bằng `stream_coverage >= 0.90`. Tuổi của số đo không hề tham gia vào kết luận. Vì vậy
một số đo từ phiên bất kỳ trong quá khứ vẫn cho [ĐẠT].

**Yêu cầu:** tiêu chí 6 phải **FAIL** nếu số đo độ phủ không đến từ phiên giao dịch hoàn tất gần
nhất, bất kể độ phủ cao bao nhiêu.

Định nghĩa "phiên giao dịch hoàn tất gần nhất" — dùng lại `is_trading_day()` có sẵn trong
`trading/calendar_vn.py:16`, **không tự viết lại lịch** ("một công thức, một chỗ"):
- Lấy thời điểm chạy cổng. Lùi dần từng ngày về quá khứ, ngày đầu tiên thỏa `is_trading_day()` **và**
  đã qua 14:45 VN chính là phiên hoàn tất gần nhất.
- Nếu `stream_measured_at.date()` khác ngày đó → **FAIL**.

Ghi chú FAIL phải nói rõ hai ngày để người đọc hiểu ngay, ví dụ:
`Số đo từ phiên 22/09 nhưng phiên hoàn tất gần nhất là 23/09 — không có dữ liệu luồng cho phiên gần nhất.`

**Kiểm chứng:**
1. Viết test **trước**: dựng `stream_measured_at` = 22/09, thời điểm chạy = 23/09 22:14, coverage =
   1.0 → kỳ vọng tiêu chí 6 có `status == "FAIL"` và exit code tổng là 2.
2. Chạy test → **phải đỏ** trước khi sửa. Dán nguyên văn dòng fail.
3. Sửa code → test xanh.
4. Test giữ ca đúng: `stream_measured_at` cùng ngày với phiên gần nhất, coverage 1.0 → vẫn PASS.
5. Test ca cuối tuần: chạy cổng sáng thứ Hai, số đo từ thứ Sáu → **PASS** (thứ Bảy/Chủ nhật không
   phải phiên). Đây là ca dễ làm sai nhất — bắt buộc phải có test riêng.
6. **Kiểm thử phá hoại:** sau khi xong, tạm đổi điều kiện mới thành `if False:`, chạy lại suite,
   xác nhận **đúng những test mới viết** fail (dán số lượng). Khôi phục, xác nhận sạch. Nếu vô
   hiệu hóa mà không test nào đỏ → test là sân khấu, phải viết lại.

---

## Task 2 — Tiêu chí 2 (NAV) không có lá chắn độ tươi

**Lỗi hiện tại:** `scripts/check_golive_gate.py:179-199` cho tiêu chí 2 trạng thái PASS chỉ cần
`nav is not None`. Không hề kiểm tuổi bản ghi. Tối nay cổng báo NAV `5,021,712 VND` là **[ĐẠT]**,
trong khi chính engine ghi WARN cho đúng con số đó:

```
{"level": "WARN", "msg": "NAV cu hon 24h (28.0h) - van dung de tinh rui ro", "nav": 5021712.0,
 "ts": "2026-09-22 11:13:10.869293+00:00"}
```

Hai công cụ nói ngược nhau về cùng một số liệu — cổng go-live đang dễ dãi hơn engine.

**Yêu cầu:** tiêu chí 2 nhận thêm tuổi bản ghi NAV và:
- WARN nếu NAV cũ hơn 24h (khớp đúng ngưỡng engine đang dùng — **tìm hằng số đó trong
  `trading/` và dùng lại, không chép số 24 vào chỗ mới**).
- Vẫn PASS nếu tươi hơn 24h.
- Vẫn FAIL nếu không có bản ghi nào (giữ nguyên hành vi cũ).

Dùng WARN chứ không FAIL, vì engine vẫn chạy được với NAV cũ — nhưng người bật tiền thật phải nhìn
thấy nó, không được để nó lẫn vào màu xanh.

**Kiểm chứng:** cùng quy trình Task 1 — test đỏ trước, sửa, xanh sau, cộng kiểm thử phá hoại. Thêm
test biên: đúng 24h (làm rõ trong test bạn chọn `>` hay `>=`, và giữ nhất quán với engine).

---

## Task 3 — Đo độ trễ, **chỉ đo, chưa tối ưu**

Chủ dự án muốn tối ưu hiệu suất xử lý. Tôi đã đo sơ bộ từ log có sẵn và kết quả **bác bỏ giả định
rằng nút thắt nằm ở engine**:

| Nguồn | n | p50 | p90 | max |
|---|---|---|---|---|
| `logs/bars_closed.log` (collector: đóng nến → publish xong) | 230 | 8.778s | 38.877s | 61.215s |
| `logs/engine_alerts.log` (engine: đóng nến → xử lý xong) | 259 | 13.741s | 40.435s | 61.215s |

Cả hai đo cùng một mốc gốc (`bar.ts + interval`, xem `collector/main.py:117-118` và
`engine/main.py:487-491`), nên hiệu số chính là phần engine cộng thêm: **~5s ở trung vị, ~1,5s ở
p90, và gần như 0 ở max** (61,215s ở cả hai — toàn bộ độ trễ tệ nhất sinh ra trước khi engine nhận
được nến).

**Kết luận sơ bộ: tối ưu code chiến lược/engine gần như vô ích. Nút thắt nằm phía collector.**
Nhưng tôi chưa biết *ở đâu trong collector* — và tôi không giao việc tối ưu mù.

**Yêu cầu:** viết `scripts/measure_bar_latency.py` — script **chỉ đọc log, chỉ in số, không sửa gì**:
1. Đọc `logs/bars_closed.log` và `logs/engine_alerts.log`, ghép theo `(symbol, ts)`.
2. Với mỗi nến ghép được, in ra: độ trễ collector, độ trễ engine, và hiệu số (phần engine cộng thêm).
3. In phân vị p50/p90/p99/max cho cả ba đại lượng, kèm `n`.
4. Tách số liệu **theo từng mã** — log cho thấy HPG thường ~1-3s còn IJC/AAA chậm hơn 15-40s trên
   cùng một nến. Xác nhận bằng số xem mẫu hình đó có thật và ổn định không.
5. Tách theo giờ trong phiên (mở cửa / giữa phiên / ATC) xem độ trễ có cụm lại ở khung nào không.

**Tiêu chí hoàn thành:** script chạy được, in bảng số; kèm ≥3 test đơn vị cho phần tính phân vị và
phần ghép cặp (dữ liệu dựng tay, kết quả tính tay — không dùng chính script để sinh kỳ vọng).

**Cấm tuyệt đối trong đợt này:**
- **Không** sửa collector để "cho nhanh hơn".
- **Không** tự kết luận nguyên nhân độ trễ. Báo cáo số, để tôi đọc. Đợt 77 đã cho thấy vì sao:
  một con số p=0,0317 trông như phát hiện lớn, nhưng chết khi hiệu chỉnh đa so sánh. Diễn giải là
  việc của tôi.

---

## 2. Không làm

- Không sửa `trading/engine/main.py`, `trading/collector/main.py`, không đụng GAP-1, không đụng
  thứ tự warm-up/backfill.
- Không "tiện thể" refactor `check_golive_gate.py` ngoài hai tiêu chí được giao.
- Không xóa dead code có sẵn từ trước.
- Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: dán nguyên văn dòng test **đỏ trước khi sửa**, rồi kết quả xanh sau khi sửa, rồi kết quả
   kiểm thử phá hoại (số test đỏ khi vô hiệu hóa).
2. Task 2: tương tự, kèm tên + vị trí hằng số 24h bạn dùng lại từ `trading/`.
3. Task 3: nguyên văn bảng số script in ra.
4. Số test trước/sau (`uv run pytest -m "not integration" -q`, nền hiện tại là **735 passed**), và
   `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng, kể cả khi ngoài phạm vi.

---

## 4. Việc KHÔNG giao agent — cần chủ dự án quyết

Nguyên nhân gốc của sự cố tối nay là **warm-up chạy trước khi backfill xong**. GAP-1 phát hiện
nhưng không vá. Có ít nhất ba hướng xử lý, khác nhau về rủi ro, và tôi không tự chọn thay chủ dự án:

1. **Engine chờ backfill xong rồi mới warm-up** — sạch nhất, nhưng thêm một phụ thuộc thứ tự giữa
   hai service vốn đang độc lập, và cần định nghĩa "chờ bao lâu thì bỏ cuộc".
2. **Khi GAP-1 phát hiện lỗ, engine tự nạp lại warm-up** — vá đúng chỗ đau, nhưng biến GAP-1 từ
   cảnh báo thành hành động, làm nó khó kiểm chứng hơn nhiều.
3. **Không sửa code, thêm quy trình vận hành**: luôn khởi động lại engine trước 09:00 mỗi phiên.
   Rẻ nhất, nhưng phụ thuộc con người — và chính sự phụ thuộc đó vừa làm mất nguyên phiên 23/09.

Cần chủ dự án chọn hướng trước khi tôi viết brief tiếp.
