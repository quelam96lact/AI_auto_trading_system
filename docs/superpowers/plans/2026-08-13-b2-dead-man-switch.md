# Kế hoạch B2: thử dead-man's switch bằng cách thật sự giết collector

Ngày giao: 2026-08-13, phiên chiều (13:00–14:45). Base: `e20e647`.

**KHÔNG viết code. KHÔNG commit.** Đây là bài kiểm tra vận hành trên hệ thống
thật, không phải task lập trình. Nếu bạn thấy mình đang sửa file trong
`trading/` hoặc `scripts/`, bạn đã đi sai.

---

## Vì sao phải làm trong giờ giao dịch

`scripts/heartbeat_check.py` **cố ý chỉ cảnh báo trong phiên** — nó gọi
`is_trading_time(now)` và thoát im lặng ngoài giờ, để tránh spam đêm và cuối
tuần. Ngoài phiên thì mọi thứ đều "stale" một cách hợp lệ, nên không thể phân
biệt được switch chạy đúng hay hỏng.

Ngưỡng: `DEFAULT_MAX_AGE_SECONDS = 300`. Phải để collector chết **hơn 5 phút**
thì mới kích hoạt.

Đây là thứ duy nhất trong danh sách còn lại bị ràng buộc bởi giờ giao dịch.

## Điều bài test này CHỨNG MINH và KHÔNG chứng minh

**Chứng minh:** logic phát hiện chạy đúng — nhận ra collector chết, gọi đúng
tên service, gửi được Telegram, và không kêu oan khi mọi thứ khoẻ.

**KHÔNG chứng minh:** rằng nó đang được lên lịch chạy. `DEPLOYMENT.md` §9 nói
chạy bằng cron trên host; máy dev là Windows, không có cron. Đừng viết bất kỳ
câu nào ngụ ý "dead-man's switch đã hoạt động trong sản xuất" — nó mới chỉ
được chứng minh là **hoạt động khi được gọi**.

---

## Các bước — mỗi bước kèm cách kiểm chứng

Chạy trên HOST (không phải trong container), với
`DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading`.

1. **Chuẩn (không kêu oan).** Stack đang khoẻ → chạy
   `uv run python scripts/heartbeat_check.py`
   → kiểm chứng: **exit code 0**, không có Telegram nào được gửi.
   Đây là nửa quan trọng của bài test: một cái switch luôn kêu thì vô dụng
   ngang một cái không bao giờ kêu.

2. **Ghi mốc trước khi giết.** `SELECT service, last_seen FROM heartbeat` —
   dán ra. Ghi lại giờ hệ thống.

3. **Giết collector.** `docker compose stop collector`
   → kiểm chứng: `docker compose ps` không còn collector.
   Engine để NGUYÊN — nó phải tiếp tục đập, để chứng minh script chỉ tố đúng
   service chết chứ không tố bừa cả hai.

4. **Chờ hơn 5 phút.** Trong lúc chờ, chạy `heartbeat_check.py` **một lần ở
   khoảng phút thứ 2–3**
   → kiểm chứng: vẫn **exit 0** (chưa quá ngưỡng 300s). Bước này chứng minh
   ngưỡng thật sự có tác dụng, không phải hễ khác là kêu.

5. **Sau 5 phút, chạy lại.**
   → kiểm chứng: **exit code 1**, stdout nêu rõ `collector`, **KHÔNG** nêu
   `engine`, và **có tin nhắn Telegram thật đến máy chủ dự án**.
   Dán nguyên văn stdout và nội dung Telegram.

6. **PHỤC HỒI — BẮT BUỘC, không được bỏ.**
   `docker compose start collector`, chờ tới khi
   `SELECT round(EXTRACT(epoch FROM now()-last_seen)) FROM heartbeat WHERE service='collector'`
   nhỏ hơn 60.
   → kiểm chứng: chạy lại `heartbeat_check.py` → **exit 0**.
   Và `SELECT count(*), max(ts AT TIME ZONE 'Asia/Ho_Chi_Minh') FROM bars WHERE
   (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = CURRENT_DATE AND symbol='VCB'`
   → bar phải chảy tiếp. Khoảng trống lúc collector chết sẽ được backfill lấp
   khi khởi động lại (đã chứng minh hai lần hôm nay).

**Nếu bất cứ bước nào lệch kỳ vọng: DỪNG, phục hồi collector trước (bước 6),
rồi mới báo cáo.** Không được để hệ thống nằm chết trong lúc đi điều tra.

---

## Ràng buộc

- **KHÔNG** đụng `docker compose stop engine`, `nats`, `postgres`.
- **KHÔNG** sửa `config/config.yaml`, không đổi `HEARTBEAT_MAX_AGE_SECONDS` cho
  nhanh — chờ đủ 5 phút thật. Rút ngắn ngưỡng là test một hệ thống khác với hệ
  thống sẽ chạy thật.
- **KHÔNG** chạy `pytest` trong lúc làm B2 — suite sẽ đụng vào cùng DB/NATS và
  làm hỏng bằng chứng (đúng sự cố sáng nay).
- Phiên đóng **14:45**. Nếu tới 14:30 mà chưa xong bước 5, bỏ dở và làm bước 6
  ngay — phục hồi quan trọng hơn hoàn thành.

## Ghi chú

Chủ dự án sẽ nhận cảnh báo Telegram thật ở bước 5. Đó là dự kiến, không phải sự
cố. Nói rõ trong báo cáo là cảnh báo đó do bài test sinh ra.
