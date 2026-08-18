# Plan (Antigravity): tách "lỗi thu thập" khỏi "không có giao dịch"

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. Chạy `gitnexus_context` trên
> `trading/data_quality.py` trước khi sửa, `gitnexus_detect_changes` trước khi
> báo cáo. **KHÔNG commit, KHÔNG push.**

## Vì sao — và đây là lỗi của tôi (planner), không phải của bạn

Công cụ bạn viết (`4272730`) đo **đúng**. Tôi đã tự kiểm và mọi con số khớp
tuyệt đối: 0 cặp `(symbol, ngày)` trùng trên 2.969.366 dòng; khoảng `[11, 635]`
trống hoàn toàn; mọi ngưỡng từ 11 đến 635 đều cho cùng 2.647 phiên.

Vấn đề nằm ở **plan của tôi**, không phải ở code của bạn.

Plan cũ viết: *"Định nghĩa 'thiếu' rõ ràng: có phiên mà không có bar."* Với bar
5 phút tôi đã nhận ra định nghĩa đó sai cho mã ít thanh khoản (không có lệnh
khớp thì không có bar, đó là bình thường) và loại bar 5m khỏi phạm vi vì lý do
đó. Rồi tôi **giả định sai rằng bar NGÀY không dính cùng vấn đề**.

Nó dính. Bằng chứng — mã "thiếu giữa" nhiều nhất:

```
TET  HNX  avg_value_20d = 23,8tr   254 bar / 10 năm, 42 khoảng trống >20 ngày
QST  HNX  avg_value_20d = 11,3tr
SDC  HNX  avg_value_20d =  1,6tr
MCC  HNX  avg_value_20d =  2,0tr
```

Ngưỡng thanh khoản của chiến lược là **2 tỷ**. Những mã này thấp hơn 100-1000
lần. Chúng **không giao dịch** nhiều phiên — không có bar là **đúng**, không
phải mất dữ liệu.

Hệ quả: con số tiêu đề *"chỉ 97/1551 mã (6,3%) đầy đủ, thiếu 495.097 phiên"*
**không dùng để ra quyết định được**. Nghe như thảm họa, nhưng phần lớn là mã
chết thanh khoản mà chiến lược không bao giờ đụng tới.

## Việc

Thêm một phân biệt nữa để báo cáo trở nên hành động được: **lỗi thu thập** khác
**không có giao dịch**.

## Tín hiệu phân biệt — có sẵn trong dữ liệu, không cần nguồn ngoài

Cùng một cơ chế đồng thuận bạn đã dùng cho phiên, áp cho lỗ hổng:

- Ngày X thiếu ở **một** mã trong khi gần như cả thị trường có bar → mã đó
  **không giao dịch** ngày đó. Đặc trưng riêng lẻ.
- Ngày X thiếu ở **nhiều mã cùng lúc** → **lỗi thu thập**. Đặc trưng tương quan.

Đây chính là chỗ mạnh của phương pháp đồng thuận: nó đã tự hiệu chỉnh cho phiên,
và tự hiệu chỉnh được luôn cho nguyên nhân lỗ hổng.

**Ngưỡng phân định phải ĐO, không được đoán** — giống hệt cách bạn làm với ngưỡng
100 ở đợt trước, và tôi mong bạn giữ đúng kỷ luật đó.

## Ngoài phạm vi (đừng làm)

- Không tự vá dữ liệu, không gọi backfill. Plan này chỉ ĐO và PHÂN LOẠI.
- Không dựng lịch nghỉ lễ.
- **Không đụng `scripts/backfill_universe.py`** — Hermes đang sửa file đó cùng
  lúc (backfill ghi nhận độ phủ nó không có). Chạm vào là hai luồng giẫm nhau.
- Không đổi cách suy phiên giao dịch (ngưỡng đồng thuận) — nó đã được kiểm và
  ổn định trên dải rộng 60 lần.

## Global constraints

- **Chỉ được sửa/thêm:** `trading/data_quality.py`, `tests/test_data_quality.py`,
  `scripts/check_data_completeness.py`, và file CSV báo cáo nó sinh ra.
- **KHÔNG đụng:** `scripts/backfill_universe.py`, `scripts/daily_data_check.py`,
  `trading/collector/`, `scripts/heartbeat_check.py`, `config/config.yaml`,
  `tests/conftest.py`, `trading/storage/db.py` (nếu cần hàm đọc mới, **báo cáo**
  — Hermes có thể đang chạm file đó).
- Postgres đang phục vụ collector + engine chạy thật. **READ-ONLY tuyệt đối.**
- `scripts/` nằm trong phạm vi lint và đang **sạch 0 lỗi** — giữ nguyên.
- Base: `main` = `4272730` (công việc đợt trước của bạn đã merge).

---

## Các bước

### Task 1 — đo phân bố "một ngày thiếu ở bao nhiêu mã"

Với mỗi phiên giao dịch đã suy được, đếm **bao nhiêu mã đang trong đời sống**
(đã niêm yết, chưa hủy) mà **không có bar** phiên đó.

Kỳ vọng của tôi — nêu ra để bạn bác bỏ nếu dữ liệu nói khác: phần lớn phiên có
một số lượng nền ổn định các mã vắng mặt (mã ít thanh khoản, ngày nào cũng vắng),
và một số ít phiên vọt lên hẳn (lỗi thu thập).

Việc: dán phân bố thật. Nếu có phân tách rõ, chọn ngưỡng nằm trong khoảng trống
và nói rõ lý do. **Nếu KHÔNG có phân tách rõ** → giả định của tôi lại sai lần
nữa → **DỪNG và BÁO CÁO**, đừng tự chế biến thể. Bạn đã làm đúng việc này ở
ngưỡng 100; làm lại lần nữa.

→ **Kiểm chứng:** dán số liệu phân bố + ngưỡng đã chọn + lý do. Kèm kiểm tính
ổn định: kết quả có đổi nhiều không khi ngưỡng đổi (như dải 11-635 lần trước bất
biến).

### Task 2 — phân loại lỗ hổng theo nguyên nhân

Mở rộng `data_quality.py`: mỗi phiên thiếu của mỗi mã được gán một trong hai
loại, dựa trên ngưỡng đo được ở Task 1.

Giữ nguyên các phân biệt cũ (thiếu giữa / thiếu đuôi / bar rác) — **thêm** chiều
nguyên nhân, đừng thay thế.

→ **Kiểm chứng (TDD, đỏ trước):** test tối thiểu phải phủ — một mã vắng lẻ loi
trong khi cả thị trường có bar → "không giao dịch"; một ngày mà rất nhiều mã cùng
vắng → "lỗi thu thập" cho tất cả; ranh giới quanh đúng ngưỡng.
Sau khi xanh, **tự phá bản sửa** để chứng minh test bắt được — và như bài học
đợt trước, **sabotage phải nhắm vào điều plan này yêu cầu** (phân biệt được hai
nguyên nhân), không phải vào dòng bạn vừa viết. Dán cả hai output đỏ.

### Task 3 — sửa con số vô nghĩa >100%

9 mã đang có `completeness_lifespan_pct > 100` (AAA 100.08, TCX 103.52, HCM
100.26...). Nguyên nhân: chúng là mã collector real-time đang ghi, nên có bar
**vượt quá phiên đồng thuận cuối cùng** (2026-08-07), trong khi `expected` chỉ
đếm tới đó.

Sửa sao cho không bao giờ ra số vô nghĩa. Cách xử lý bạn tự chọn — nêu rõ đã
chọn gì và vì sao.

→ **Kiểm chứng:** test cho trường hợp mã có bar vượt phiên cuối; chạy lại CLI,
xác nhận không còn mã nào >100%.

### Task 4 — chạy lại và trả lời câu hỏi gốc CHO ĐÚNG

Chạy lại CLI trên toàn bộ dữ liệu, xuất báo cáo mới.

Rồi trả lời câu hỏi thật sự quan trọng, thứ mà báo cáo cũ không trả lời được:

**Trong số mã mà chiến lược THỰC SỰ có thể giao dịch (`avg_value_20d >= 2 tỷ` —
ngưỡng thanh khoản trong `OctopusPullbackStrategy`), bao nhiêu mã có lỗ hổng do
LỖI THU THẬP?**

Đó mới là con số quyết định có tin được backtest hay không. Mã thanh khoản 1,6
triệu VND/phiên thiếu 2.000 phiên thì không ảnh hưởng gì tới một chiến lược
không bao giờ mua nó.

→ **Kiểm chứng:** dán output thật, tách bạch hai nhóm (đủ thanh khoản / không),
và trong nhóm đủ thanh khoản thì tách theo nguyên nhân lỗ hổng.

---

## Kiểm chứng cuối

```
uv run ruff check trading tests scripts      # All checks passed!
uv run pytest -m "not integration" -q        # 300 + đúng số test bạn thêm
uv run pytest -m "integration" -q            # 84 + đúng số test bạn thêm
```
(integration cần `TEST_DB_DSN` trỏ `trading_test` + `TEST_NATS_URL` cổng 4223)

Báo cáo: dán output THẬT nguyên văn. Việc nào không làm được thì nói rõ vì sao —
**đừng đoán bừa cho đủ**. Phát hiện vấn đề ngoài phạm vi thì **báo cáo, đừng tự
sửa**.
