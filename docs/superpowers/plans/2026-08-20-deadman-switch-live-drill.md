# Diễn tập dead-man's switch trên phiên thật — 2026-08-20 (thứ Năm)

Base main = b962e0f. Người thực thi: Antigravity. Người audit + commit: Claude.

## Vì sao việc này phải chạy TRONG giờ giao dịch

`scripts/heartbeat_check.py` tự thoát sớm ngoài giờ giao dịch (`is_trading_time()`),
và cả ba nhánh cảnh báo của nó đều định nghĩa trên dòng dữ liệu đang chảy:

- heartbeat cũ: `last_seen` quá `DEFAULT_MAX_AGE_SECONDS = 300`
- 2A "dữ liệu ngừng chảy": không bar mới trong `DEFAULT_STALE_BAR_MINUTES = 15`
- 2B "token SSI sắp hết hạn" — KHÔNG nằm trong phạm vi lần này (xem "Không làm")

Ba nhánh này mới chỉ xanh trong unit test. Chưa ai từng giết service thật rồi xem
Telegram có kêu không. Ghi nhận từ 2026-08-09: "Dead-man's switch still never
exercised by actually killing a service."

## QUYẾT ĐỊNH CẦN CHỦ DỰ ÁN DUYỆT TRƯỚC KHI GÕ LỆNH ĐẦU TIÊN

Diễn tập này **cố ý làm mất dữ liệu thật**: collector dừng 20 phút giữa phiên,
3 mã HII/IJC/AAA sẽ thiếu ~4 bar 5 phút. Đó chính là phép đo (Task 3 đo xem hệ
thống có tự vá không), không phải tác dụng phụ.

Chấp nhận được vì: `real_trading_enabled: false`, engine chỉ chạy paper, không có
lệnh thật nào bị lỡ. Nhưng đây vẫn là hành động lên hệ thống ĐANG CHẠY THẬT —
không tự ý làm khi chưa có "duyệt".

Cảnh báo Telegram sẽ được gửi THẬT tới chat của chủ dự án. Đó là mục đích.

## Lịch chạy (giờ VN, phiên sáng 09:00-11:30)

| Giờ | Việc | Kiểm chứng bằng |
|---|---|---|
| 09:15 | Task 1 — chụp trạng thái nền | bảng heartbeat + bar mới nhất, dán nguyên văn |
| 09:30 | Task 2 — `docker compose stop collector` | `docker compose ps` cho thấy collector đã dừng |
| 09:36 | Task 2 — chạy `heartbeat_check.py` lần 1 | exit code 1 + Telegram nhận được cảnh báo heartbeat |
| 09:47 | Task 2 — chạy lần 2 (đã quá 15 phút không bar) | exit 1 + cảnh báo 2A "dữ liệu ngừng chảy" |
| 09:50 | Task 3 — `docker compose start collector` | log `backfill start` |
| 09:58 | Task 3 — chạy `heartbeat_check.py` lần 3 | exit 0, KHÔNG còn cảnh báo |
| 10:30 | Task 3 — đếm bar trong cửa sổ 09:30-09:50 | SQL, so với 3 mã × 4 khung |
| 15:10 | Task 4 — sau EOD repair job (15:05) | đếm lại đúng cửa sổ đó |

Nếu bỏ lỡ mốc giờ nào thì GHI RÕ giờ thật đã chạy, đừng viết lại cho khớp bảng.

---

## Task 1 — Chụp trạng thái nền TRƯỚC khi phá

Chạy trên host (không phải trong container):

```
uv run python scripts/heartbeat_check.py; echo "exit=$?"
```

```sql
SELECT service, last_seen FROM heartbeat ORDER BY 1;
SELECT symbol, count(*), max(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')
FROM bars WHERE ts >= '2026-08-20' GROUP BY 1 ORDER BY 1;
```

**Tiêu chí ĐẠT:** exit code 0 và bar đang về cho cả 3 mã. Nếu đã đỏ sẵn từ đầu
thì **DỪNG, BÁO CÁO** — không diễn tập trên hệ thống đang hỏng, vì không tách
được cảnh báo do mình tạo ra khỏi cảnh báo có sẵn.

## Task 2 — Giết collector, xác nhận chuông kêu

```
docker compose stop collector
```

Chạy `heartbeat_check.py` tại **09:36** (đã quá ngưỡng 300s) và **09:47**
(đã quá 15 phút không bar). Với mỗi lần: dán exit code, dán nguyên văn stdout,
và dán/chụp nội dung tin Telegram nhận được.

**Tiêu chí ĐẠT — cả ba phải đúng, thiếu một là chưa đạt:**
1. Lần 09:36: exit 1, có nhắc tên `collector` trong cảnh báo.
2. Lần 09:47: exit 1, có nhánh 2A (bar ngừng chảy).
3. Telegram nhận được thật — không chấp nhận "script bảo đã gửi".

**Nếu chuông KHÔNG kêu:** đó là phát hiện quan trọng nhất của cả buổi. Khởi động
lại collector NGAY (đừng kéo dài lỗ hổng dữ liệu để điều tra), rồi điều tra
offline sau phiên. Báo cáo rõ nhánh nào câm.

## Task 3 — Bật lại, đo xem hệ thống có tự vá lỗ hổng không

```
docker compose start collector
docker compose logs --since 5m collector | tail -50
```

Chạy `heartbeat_check.py` lúc 09:58 → **tiêu chí ĐẠT: exit 0**.

Lúc 10:30, đếm bar đúng cửa sổ đã tắt:

```sql
SELECT symbol, count(*) FROM bars
WHERE ts >= '2026-08-20 09:30+07' AND ts < '2026-08-20 09:50+07'
GROUP BY 1 ORDER BY 1;
```

Kỳ vọng nếu tự vá hoàn toàn: 4 bar/mã (09:30, 09:35, 09:40, 09:45). Mã ít khớp
lệnh có thể thiếu khung một cách chính đáng — nên **đối chiếu với chính 3 mã đó
ở cửa sổ 09:00-09:30 cùng ngày** để biết mức nền, đừng so với con số lý thuyết.

**Đây là ĐO, không phải PASS/FAIL.** Kết quả nào cũng là kết quả thật; ghi con số,
đừng phán "hệ thống tự phục hồi tốt" nếu số không nói thế.

## Task 4 — Sau EOD repair job (chạy 15:05)

Lúc 15:10 chạy lại đúng câu SQL trên. So sánh trước/sau EOD.

**Câu hỏi cần trả lời bằng số:** lỗ hổng do mất kết nối giữa phiên được vá bởi
(a) backfill lúc khởi động, (b) EOD repair job, (c) không được vá?

Câu trả lời (c) là một lỗ hổng go-live thật và phải được nêu bật trong báo cáo,
không chôn ở cuối.

---

## KHÔNG được làm

- KHÔNG sửa bất kỳ file code nào. Đây là plan CHẠY và ĐO, không viết code.
  Nếu phát hiện bug cần sửa → BÁO CÁO, để phiên sau sửa theo TDD.
- KHÔNG commit, KHÔNG push.
- KHÔNG bật `real_trading_enabled`.
- KHÔNG kiểm nhánh 2B (token SSI) — cách duy nhất để kiểm là làm hỏng token của
  collector đang chạy thật, rủi ro không tương xứng. Vẫn là nhánh chưa được kiểm
  ngoài đời; ghi nhận vậy trong báo cáo.
- KHÔNG dừng `engine`, `postgres`, `nats`. Chỉ `collector`.
- KHÔNG kéo dài cửa sổ tắt quá 20 phút vì bất cứ lý do gì. Quá 09:50 mà chưa
  start lại → start lại trước, điều tra sau.
- KHÔNG chạy backfill thủ công trong lúc diễn tập — sẽ làm hỏng phép đo Task 3/4.

## Báo cáo

Dán output THẬT nguyên văn (exit code, stdout, SQL, ảnh/nội dung Telegram).
Tách bạch "đã kiểm chứng bằng chạy thật" và "suy luận". Việc nào không làm được
thì nói rõ vì sao — đừng đoán cho đủ mục.
