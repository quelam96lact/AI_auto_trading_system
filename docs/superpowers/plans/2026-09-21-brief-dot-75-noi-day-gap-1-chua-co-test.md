# Brief đợt 75 — Phần nối dây của GAP-1 chưa có một test nào

Ngày giao: 21/09/2026 (thứ Hai, sau phiên).
Base: main `2702d20`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

> **Thứ tự: đợt 75 → rồi đợt 72.** Đợt 75 nhỏ (một test), làm trước cho gọn.

---

## 0. Đợt 74: cái gì đã vào, cái gì tôi đã gỡ, và tôi sai chỗ nào

### 0.1. Đã commit (`2702d20`)

`count_warmup_gap()` + logic GAP-1 trong `run()`. Bốn ca đo đều đúng, dùng lại
`market_minutes_between` + `CONTINUOUS_SESSIONS` chứ không viết bản thứ hai của lịch phiên. Cách xử
lý nến ATC (lấy `warmed_until + 5 phút` làm điểm bắt đầu) là đúng và gọn hơn cái tôi nghĩ trong
đầu. Tốt.

713 → **717 passed**, 116 deselected, ruff sạch.

### 0.2. **Tôi sai** ở brief 74 mục 1.4 — đã tự hoàn tác

Tôi khẳng định "nhánh 2 của `DurableAlertFilter` chưa từng được kiểm một lần nào". **Sai.**
`test_ba_duong_log_va_loc_on` (đợt 66 Task 3, `tests/test_logging_setup.py:99`) đã phủ **cả hai
chiều** từ trước: WARNING từ `trading.telegram` và `trading.engine.real_orders` phải vào file, INFO
từ `trading.collector.main` phải bị chặn.

Tôi grep `attach_durable_alert_handler`, **thấy dòng 108 của chính test đó trong kết quả**, rồi chỉ
đọc dòng 44–73 và khẳng định một điều phủ định về cả file. Đây là lần thứ hai trong phiên này tôi
đặt hàng trùng (lần trước: brief 71 trùng đợt 42).

Hai test bạn viết theo yêu cầu sai đó đã được gỡ. **Việc bạn làm không sai** — và bước test phá
hoại bạn chạy vẫn có giá trị: đảo nhánh 2 làm **2 test đỏ**, tức nhánh 2 **có** được gác. Bạn cũng
đã báo trung thực rằng một test cũ cũng đỏ; chỉ là chưa rút ra kết luận rằng tiền đề của tôi sai.
**Lần sau gặp dấu hiệu kiểu đó, nói thẳng: "brief sai ở chỗ này."** Bạn được phép, và nên.

### 0.3. Đã gỡ `test_gap1_ca3_chi_warn_mot_lan` — nó là sân khấu

Test đó tự gọi `engine_main.alert()` rồi tự đếm mình đã gọi một lần. Nó **không hề chạm tới**
`_warmup_gap_checked` trong `run()`.

Tôi kiểm bằng test phá hoại: đổi `if bar.symbol not in _warmup_gap_checked:` thành `if False:` —
tức **xóa sạch toàn bộ khối GAP-1 khỏi đường chạy** — rồi chạy lại:

```
720 passed, 116 deselected
```

**Không một test nào đỏ.** Toàn bộ phần nối dây không có test. Đó là việc của brief này.

### 0.4. Ba con số trong báo cáo của bạn sai

"4 test GAP-1" (thật ra file có 5), "+5" (thật ra +7), mốc "715 →" (thật ra 713). Không ảnh hưởng
kết quả, nhưng đó là lấy kỳ vọng thay cho phép đo. **Số trong báo cáo phải là số bạn vừa đọc được
trên màn hình**, không phải số bạn nghĩ sẽ ra.

---

## Task 1 — Test thật cho phần nối dây GAP-1

### 1.1. Khung đã có sẵn

`tests/test_engine_main.py` **đã có** khung gọi `run()` thật (storage + NATS test, `max_messages`,
`monkeypatch`). Xem các test có sẵn như `test_engine_alerts_critical_on_risk_halt` (dòng ~283) để
theo đúng lối: bơm bar vào stream, monkeypatch những gì cần, gọi `run(...)`, rồi khẳng định trên
alert bắt được. **Dùng lại khung đó, đừng dựng khung mới.**

Test này **cần DB + NATS** → nhớ gắn nhãn `integration` cho đúng (bài học đợt 73).

### 1.2. Phải khẳng định được ba điều

1. **Có lỗ thì kêu**: `warmed_until` cách nến live đầu tiên một quãng có nến ở giữa → phát **đúng
   một** WARN, và WARN đó mang `symbol`, `warmed_until`, `first_live_ts`, `missing_bars` đúng giá
   trị.
2. **Liền mạch thì im**: nến live đầu tiên liền ngay sau `warmed_until` → **không** WARN GAP-1 nào.
3. **Chỉ kêu một lần cho mỗi mã**: sau nến đầu, xử lý thêm ít nhất hai nến nữa của **cùng mã** →
   tổng số WARN GAP-1 vẫn là 1. Đây chính là phần `_warmup_gap_checked` mà test cũ không chạm tới.

Lọc alert theo dấu hiệu riêng của GAP-1 (ví dụ có khóa `missing_bars`), đừng đếm mọi WARN — engine
phát WARN vì nhiều lý do khác, đếm tất sẽ ra test giòn.

### 1.3. Kiểm chứng — bắt buộc có bước phá hoại

Sau khi test xanh, làm **đúng** phép thử tôi đã làm:

1. Đổi `if bar.symbol not in _warmup_gap_checked:` thành `if False:` trong `trading/engine/main.py`.
2. Chạy lại suite đầy đủ. **Phải có test đỏ** — nếu vẫn xanh hết thì test của bạn cũng là sân khấu,
   viết lại.
3. Khôi phục nguyên trạng, xác nhận xanh.

Dán cả ba kết quả, kèm **tên** test đã đỏ ở bước 2.

---

## 2. Không làm

- **Không đụng `count_warmup_gap()`** — nó đã đúng và đã có 4 test.
- **Không "sửa" điểm mù nến ATC.** Tôi đã đo và chấp nhận: nếu chính nến ATC 14:45 bị bỏ qua thì
  hàm đếm ra 0 (`c(T6 14:25 → T2 09:15) = 0` trong khi thật ra thiếu nến ATC). Đếm **thiếu** tối đa
  1 nến, và **không bao giờ báo động giả**. Lệch về phía im lặng ở đây là đánh đổi có chủ ý; đổi nó
  sẽ mở đường cho báo động giả, mà báo động giả giết chuông nhanh hơn cả không có chuông.
- Không đụng `tests/test_logging_setup.py` — đã trở về nguyên trạng, đúng như nó nên có.
- **Không "hợp nhất" GAP-1 với `fetch_expected_bars_from_db()`** trong
  `scripts/stream_health_check.py`. Tôi đã kiểm: chúng **không** trùng công thức. Hàm kia lấy mẫu
  số **từ chính dữ liệu** (đếm số khung nến khác nhau có trong bảng `bars`, Brief 49 §2.2), còn
  GAP-1 tính **từ lịch phiên**. Hai cái trả lời hai câu khác nhau: một đo **luồng dữ liệu**, một đo
  **cửa sổ của engine**.

  Chúng **được phép mâu thuẫn**, và sáng nay đúng là mâu thuẫn: DB có đủ 27/27 nến (stream health
  100%), trong khi cửa sổ engine thiếu 3 nến. Đó **không phải lỗi** — đó là hai phép đo khác nhau
  cùng đúng. Đừng ai đi "hòa giải" hai con số này.
- Không tự vá lỗ warm-up (vẫn chỉ báo hiệu). Hướng xử lý thứ tự khởi động là việc của chủ dự án.
- Không rebuild, không deploy, không commit, không push.

## 3. Báo cáo cho Claude

1. `git diff` đầy đủ.
2. Ba khẳng định ở 1.2 — nói rõ test nào phủ điều nào.
3. **Ba kết quả của bước phá hoại** ở 1.3, kèm tên test đã đỏ.
4. Số test trước → sau, **đọc từ màn hình**, cả suite mặc định lẫn suite đầy đủ.
5. `uv run ruff check trading tests` sạch.
6. Bất cứ chỗ nào brief này sai hoặc bạn đo ra khác — **nói thẳng ra**, như mục 0.2.
