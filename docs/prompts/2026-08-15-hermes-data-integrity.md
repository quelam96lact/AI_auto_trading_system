# NHIỆM VỤ: Truy nguồn dữ liệu bẩn trong `bars_daily` (điều tra, KHÔNG sửa dữ liệu)

Repo: `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, nhánh `feature/data-layer`, base `f9bd2c5`.

## Bối cảnh — đọc trước, đừng đo lại từ đầu

Đã kiểm và đã chốt ở `a7c6c41` (đọc commit message đó + `scripts/check_price_adjustment.py`):

- `bars_daily` **ĐÃ** được back-adjust (69,4% bar có giá không tròn bước giá sàn).
  Đừng điều tra lại câu hỏi "đã điều chỉnh chưa" — đã có câu trả lời.
- Còn **51 sự kiện chia tách chưa điều chỉnh trên 49 mã** (vd ACC 2022-01-05:
  37.156 → 18.602, khối lượng 510k/203k hai bên).
- Còn **837 bước nhảy qua đêm >25% trên 367 mã** KHÔNG khớp tỉ lệ chia tách nào và
  CÓ khớp lệnh cả hai bên. Đây là thứ chưa ai giải thích được. Ví dụ: IME 2016-01-18
  4.608 → 6.025 (+30,8%), HNB 2016-03-31 13.676 → 18.058 (+32%).
- Bài học đã trả giá: bar `volume = 0` là **giá tham chiếu treo, không phải giá thị
  trường**. Mọi phép đếm phải loại chúng trước, nếu không kết luận sẽ ngược.

Sinh danh sách mã xấu bằng:
`uv run python scripts/check_price_adjustment.py --emit-exclusions /tmp/exclude.txt`

## RÀNG BUỘC AN TOÀN — đọc kỹ, đây là DB đang chạy thật

Postgres này đang phục vụ `collector` và `engine` chạy live (`docker compose ps`).

- **TUYỆT ĐỐI KHÔNG** `UPDATE` / `DELETE` / `INSERT` vào `bars_daily`, `bars`, hay
  bất kỳ bảng nào của hệ thống. Nhiệm vụ này **chỉ đọc**.
- Nếu cần lưu kết quả trung gian, ghi ra file trong `scripts/` hoặc bảng MỚI có tiền
  tố `research_`, và nói rõ trong báo cáo.
- Không đụng `trading/engine/`, `trading/real_orders.py`, `scripts/confirm_real_order.py`,
  `config/config.yaml`, `trading/collector/` (trừ ĐỌC để hiểu).
- KHÔNG commit, KHÔNG push. KHÔNG bật `real_trading_enabled`.

## Bước 1 — Phân loại 837 bước nhảy: cái nào là dữ liệu hỏng, cái nào hợp lệ?

Đừng gọi tất cả là "dữ liệu hỏng" — có ít nhất 4 nguyên nhân hợp lệ cần loại trừ
TRƯỚC, và mỗi cái phải kiểm bằng dữ liệu chứ không bằng suy đoán:

1. **Phiên giao dịch đầu tiên sau niêm yết mới** — biên độ ±20% (HOSE) / ±30% (HNX)
   / ±40% (UPCoM), không phải ±7/10/15%.
2. **Phiên đầu sau khi được giao dịch trở lại** sau thời gian dài bị đình chỉ —
   cũng dùng biên độ rộng.
3. **Bar bị THIẾU trong DB** — nếu phiên t-1 không có bar, `close(t-1)` mà script
   lấy thực ra là của phiên t-3, và "bước nhảy qua đêm" là tích luỹ nhiều phiên.
   Kiểm bằng lịch giao dịch (`trading/calendar_vn.py`), không bằng ngày lịch.
4. **Chia tách với tỉ lệ lẻ** không nằm trong tập {1:2, 1:3, 2:3} đang kiểm
   (vd 10:11, 100:15) — nghĩa là bộ tỉ lệ hiện tại quá hẹp, không phải dữ liệu hỏng.

→ **Kiểm chứng:** một script (hoặc mở rộng `check_price_adjustment.py`) in ra bảng
phân loại: mỗi nguyên nhân bao nhiêu sự kiện / bao nhiêu mã, và **phần còn lại
không giải thích được** là bao nhiêu. Dán số thật. Nếu sau khi loại 4 nhóm trên mà
phần dư còn rất nhỏ thì kết luận đúng là "dữ liệu về cơ bản lành, script cũ quá thô"
— đó là kết quả hợp lệ, đừng cố tìm cho ra lỗi.

## Bước 2 — Đối chiếu với API SSI: dữ liệu hỏng từ nguồn hay từ đường ingest của ta?

Câu hỏi quyết định: cùng một mã/ngày, SSI trả về gì SO VỚI thứ đang nằm trong DB?

- Chọn **5–10 ví dụ** từ phần "không giải thích được" ở Bước 1, cộng thêm **ACC
  2022-01-05** (chia tách chưa điều chỉnh đã biết).
- Gọi API SSI đọc lịch sử ngày cho đúng cửa sổ đó rồi so từng dòng với DB.
- **Token:** collector đang chạy và giữ token sống trong bảng `ssi_auth_state` —
  dùng đường đó (xem `trading/collector/ssi_auth.py`), KHÔNG cần OTP mới, KHÔNG tạo
  credential mới. Nếu token hết hạn thì DỪNG và báo cáo, đừng tự đi làm OTP.

Ba kết cục có thể, phải nói rõ rơi vào cái nào:
- (a) SSI trả **giống hệt** DB → dữ liệu hỏng từ nguồn, ta không sửa được bằng backfill.
- (b) SSI trả **khác** DB → lỗi ở đường ingest của ta (`trading/collector/backfill.py`
  hoặc parser). Đây là bug thật, chỉ rõ dòng nào.
- (c) SSI có tham số/endpoint trả giá đã điều chỉnh mà ta chưa dùng → nói rõ tên
  tham số, kèm bằng chứng gọi thật.

→ **Kiểm chứng:** bảng so sánh từng dòng (ngày | OHLC trong DB | OHLC từ SSI | khớp?),
dán output thật. **Không suy đoán hành vi SSI SDK** — quy tắc của dự án này là luôn
kiểm bằng dữ liệu thật.

## Bước 3 — Đề xuất, KHÔNG tự thi hành

Dựa trên (a)/(b)/(c), đề xuất đúng một hướng xử lý và nói rõ đánh đổi:
- Nếu (b): mô tả bug + cách sửa, kèm test tái hiện. **Chưa sửa dữ liệu.**
- Nếu (a): 49 mã kia coi như không cứu được → giữ nguyên cơ chế loại trừ hiện có.
- Nếu (c): mô tả cách tái backfill an toàn, nhưng **không chạy** — ghi đè dữ liệu
  đang phục vụ hệ thống live là quyết định của chủ dự án.

## Môi trường (đã kiểm hộ, khỏi mất thời gian)

- Postgres đang chạy, `bars_daily` 2.969.328 dòng. DSN dùng `127.0.0.1`, **KHÔNG**
  `localhost` (IPv6 trên máy Windows này làm mỗi kết nối mất ~130s → script như treo).
- Console Windows là cp1252: script in tiếng Việt sẽ ném `UnicodeEncodeError` **sau
  khi đã chạy xong** và mất sạch kết quả. Thêm `sys.stdout.reconfigure(encoding="utf-8")`
  như hai script hiện có.
- Có hook chạy formatter sau mỗi lần Edit và nó reformat CẢ FILE. Chạy
  `git diff --stat` sau khi sửa và revert phần phình ra ngoài phạm vi.
- Chạy `gitnexus_impact` trước khi sửa symbol đang tồn tại, `gitnexus_detect_changes` sau.

## Báo cáo cuối phải có

1. Bảng phân loại 837 bước nhảy theo nguyên nhân + con số "không giải thích được" còn lại.
2. Bảng đối chiếu DB vs SSI cho các ví dụ đã chọn, và kết cục (a)/(b)/(c).
3. Đề xuất xử lý kèm đánh đổi.
4. Output thật của `uv run pytest -m "not integration"` và `uv run ruff check trading tests scripts`
   (ruff hiện có 8 lỗi PRE-EXISTING ở scripts ngoài phạm vi — đừng sửa, chỉ đừng thêm lỗi mới).
5. Xác nhận không có câu lệnh ghi nào chạm vào bảng của hệ thống.

Nếu kết luận là "dữ liệu về cơ bản lành, không có gì để sửa" — đó là kết quả tốt và
hợp lệ. Báo cáo trung thực đúng cái đo được, đừng nặn ra vấn đề để có việc làm.
