# Prompt thực thi: Derivative (VN30F1M) paper-trading — Phase 1

**Dùng prompt này để giao việc cho 1 agent coding khác (Hermes) thực thi.**

**Đọc trước khi bắt đầu, theo đúng thứ tự:**
1. `docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md` — spec đầy đủ, đã user duyệt, giải thích **vì sao** mỗi quyết định thiết kế được chọn.
2. `docs/superpowers/plans/2026-08-08-derivative-paper-trading-phase1.md` — implementation plan đầy đủ, có sẵn code cụ thể cho từng bước (TDD: viết test fail → implement → test pass), 4 Task.

**Thực thi đúng theo plan ở trên, task theo task, bước theo bước — không tự sáng tạo thêm.** Prompt này chỉ bổ sung các ràng buộc/quy trình bắt buộc riêng cho lần giao việc này (khác quy ước mặc định trong plan).

---

## ⚠️ Khác biệt so với plan doc — đọc kỹ

Plan doc (`docs/superpowers/plans/2026-08-08-derivative-paper-trading-phase1.md`) viết theo khuôn `superpowers:writing-plans`, mỗi Task kết thúc bằng bước `git commit`. **BỎ QUA các bước `git commit` đó trong plan** — lần giao việc này áp dụng quy ước cũ của dự án:

**KHÔNG tự commit, không tự push bất kỳ thay đổi nào.** Làm hết cả 4 Task trong 1 lượt (test viết trước, chạy fail, code, chạy pass — đúng thứ tự TDD của plan), giữ nguyên working tree có diff, rồi báo cáo lại đầy đủ (xem mục "Báo cáo lại" cuối file) để Claude (planner) audit và tự tay commit.

## ⚠️ Giới hạn phạm vi — đọc kỹ trước khi bắt đầu

**Đây là paper-trading (mô phỏng), KHÔNG phải tiền thật** — nhưng vẫn phải theo đúng phạm vi phẫu thuật đã chốt trong spec:

- **Tuyệt đối KHÔNG gọi/import** `place_order`, `place_limit_order`, `cancel_order`, `AsyncTrading`, `AsyncTradingService` ở bất kỳ file nào bạn tạo/sửa.
- **KHÔNG sửa** các file sau (chỉ được *đọc*/*import* từ chúng nếu plan yêu cầu, ví dụ import `BacktestReport` từ `trading/backtest.py`):
  - `trading/strategies/sma_cross.py`
  - `trading/paper_broker.py`
  - `trading/risk.py`
  - `trading/backtest.py`
  - `trading/engine/*` (toàn bộ thư mục)
  - `trading/collector/derivative_sync.py`
- **KHÔNG thêm** ATR position sizing hay trailing stop cho phái sinh — Phase 1 chỉ dùng `qty=1` cố định, thoát vị thế chỉ theo crossover (đúng như plan).
- **KHÔNG** tự động roll hợp đồng — hardcode `"41I1G8000"` đúng như plan, không thêm logic đoán mã hợp đồng kế tiếp.
- Nếu thấy điều gì trong code hiện có (dead code, vấn đề không liên quan) — **báo cáo lại, không tự ý sửa/dọn**.

**Trước khi sửa bất kỳ file nào đã tồn tại từ trước** (không áp dụng cho 6 file mới hoàn toàn ở Task 1-3, vì đó là symbol mới chưa từng có caller) — chạy `gitnexus_impact({target: "<tên symbol>", direction: "upstream"})`, báo cáo blast radius trước khi sửa. Task 3, Step 1 của plan đã có sẵn lệnh GitNexus cụ thể cần chạy — làm đúng bước đó.

**Sau khi xong toàn bộ 4 Task:** chạy `gitnexus_detect_changes()` (Task 4, Step... plan đã có bước này ở cuối Task 3 và nhắc lại tinh thần ở Task 4) — xác nhận thay đổi chỉ ảnh hưởng đúng 3 module mới + file test tương ứng, không đụng 6 file/thư mục bị cấm ở trên.

---

## Tiêu chí hoàn thành (kiểm chứng được, không mơ hồ)

1. `uv run pytest tests/test_derivative_position.py tests/test_derivative_risk.py tests/test_derivative_backtest.py -v` — toàn bộ PASS (test đọc dữ liệu thật `scripts/.spike_derivative_ohlc_5m_2m_sample.json` được phép SKIP nếu file không có sẵn trong môi trường của bạn — đó là dữ liệu gitignored, không phải lỗi).
2. `uv run pytest -m "not integration" -v` — toàn bộ suite pass, không phá bất kỳ test nào khác đang có.
3. `git diff main...HEAD --stat -- trading/strategies/sma_cross.py trading/paper_broker.py trading/risk.py trading/backtest.py trading/engine/ trading/collector/derivative_sync.py` — output rỗng.
4. `grep -rn "place_order\|place_limit_order\|cancel_order\|AsyncTrading" trading/derivative_position.py trading/derivative_risk.py trading/derivative_backtest.py` — không match nào.
5. `gitnexus_detect_changes()` — phạm vi thay đổi khớp đúng 3 module mới.

---

## Báo cáo lại (bắt buộc đủ 5 mục)

1. Diff đầy đủ của 3 file mới (`trading/derivative_position.py`, `trading/derivative_risk.py`, `trading/derivative_backtest.py`) + 3 file test mới.
2. Output đầy đủ của `uv run pytest -m "not integration" -v` (toàn bộ suite).
3. Output đầy đủ của `uv run pytest tests/test_derivative_position.py tests/test_derivative_risk.py tests/test_derivative_backtest.py -v` — nói rõ test dữ liệu thật đã PASS hay SKIP.
4. Kết quả `gitnexus_detect_changes()`.
5. Xác nhận bằng output thật của 2 lệnh kiểm chứng #3 và #4 ở mục "Tiêu chí hoàn thành" (không phải chỉ nói "đã kiểm tra" — dán output thật).

**Không tự commit, không tự push.** Chờ Claude audit xong mới commit.
