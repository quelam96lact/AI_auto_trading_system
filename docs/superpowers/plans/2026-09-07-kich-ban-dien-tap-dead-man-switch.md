# Kịch bản diễn tập dead-man's switch (D1) — Thứ Hai 07/09/2026

**Người soạn:** Claude · **Người thực hiện:** chủ dự án (thao tác trên máy thật)
**Quyết định:** chủ dự án chọn 07/09 sau khi tôi chỉ ra 06/09 là **Chủ nhật**,
sàn đóng cửa, không diễn tập được thứ cần một phiên thật.

---

## 0. Vì sao phải diễn tập

Chuông báo im lặng **chưa bao giờ được chứng minh là kêu thật**. Nó được viết
sau sự cố 02/09: Docker chết ⇒ mọi job giám sát bị bỏ qua, chỉ ghi dòng `SKIP`
vào file log không ai mở — **85 lần SKIP liên tiếp, không một tin Telegram nào**
(`docker_down_alert.py:4-7`).

Một chuông chưa từng kêu thử thì không phải chuông, chỉ là code trông giống
chuông.

## 1. Hiện trạng đã kiểm (06/09)

| | |
|---|---|
| Scheduled task kích hoạt | `trading-heartbeat-check` — **State: Ready** |
| Nhịp chạy | **mỗi 5 phút** (`PT5M`), kéo dài 7 giờ (`PT7H`) từ **08:00** |
| Ngày chạy | T2–T6 (`DaysOfWeek = 62`) |
| Lần chạy gần nhất | 04/09/2026 15:00 — `LastTaskResult: 0` (thành công) |
| **Lần chạy kế tiếp** | **07/09/2026 08:00** |
| Khung cho phép kêu | 08:00–15:00 (`ALERT_START`/`ALERT_END`) |
| Chống spam | **30 phút** — chỉ một tin mỗi 30 phút |

`real_trading_enabled: false` ⇒ **không có rủi ro đặt lệnh** trong suốt diễn tập.

---

## 2. Diễn tập hai chặng

Tách làm hai để nếu thất bại thì biết **hỏng ở đâu**, thay vì chỉ biết "không
thấy tin nhắn".

### Chặng A — Telegram có gửi được không (làm trước, an toàn tuyệt đối)

Không đụng Docker. Chỉ kiểm đường gửi tin.

```bash
uv run python -c "from trading.telegram import send_telegram; send_telegram('DIEN TAP D1 - chang A - kiem duong gui')"
```

- **Có tin về điện thoại** ⇒ đường Telegram sống, sang chặng B.
- **Không có tin** ⇒ dừng lại. Nguyên nhân gần như chắc chắn là thiếu
  `TELEGRAM_BOT_TOKEN` hoặc `TELEGRAM_CHAT_ID` trong môi trường —
  `telegram.py:10-12` **im lặng return** khi thiếu, không báo lỗi. Sửa xong hãy
  làm chặng B, đừng bỏ qua.

> Chú ý: `send_telegram` im lặng khi thiếu biến môi trường. Đó chính là kiểu lỗi
> khiến chuông không kêu mà không ai biết — nên chặng A tồn tại.

### Chặng B — Chuông có tự kêu khi Docker chết không (diễn tập thật)

**Thời điểm: sau 09:30**, để đã có vài chu kỳ heartbeat chạy thành công trước đó
(có nền để so sánh).

1. **Ghi giờ chính xác** rồi tắt Docker:
   ```bash
   docker compose stop
   ```
2. **Chờ tối đa 10 phút.** Nhịp là 5 phút nên lần chạy kế tiếp phải rơi vào
   trong khoảng này.
3. **Ghi lại:** tin Telegram có về không, và **cách lúc tắt bao nhiêu phút**.
4. Bật lại ngay:
   ```bash
   docker compose start
   ```
5. Xác nhận phục hồi:
   ```bash
   docker ps
   uv run python scripts/heartbeat_check.py
   ```

---

## 3. Bốn kết quả có thể, và ý nghĩa

| Kết quả | Nghĩa là |
|---|---|
| Tin về trong ≤ 10 phút | **Đạt.** Chuông hoạt động. Ghi lại độ trễ thật làm mốc |
| Tin về nhưng > 10 phút | Chuông sống nhưng chậm hơn thiết kế — điều tra scheduled task có bị bỏ nhịp không |
| Không có tin, chặng A đã đạt | **Hỏng ở cổng** — `run_if_docker_up.sh` không rẽ đúng sang nhánh Docker-chết. Đây là lỗi nghiêm trọng, báo lại ngay |
| Không có tin, chặng A cũng trượt | Thiếu cấu hình Telegram. Sửa rồi diễn tập lại |

---

## 4. Cái giá phải trả, biết trước

Tắt Docker giữa phiên ⇒ collector **mất bar trong khoảng đó** (5–10 phút, tức
1–2 bar 5 phút của 3 mã). Sau khi bật lại, kiểm tra và bù nếu cần:

```bash
uv run python scripts/heartbeat_check.py
```

Nếu có lỗ hổng bar, chạy backfill cho đúng ngày hôm đó. **Đừng bỏ qua bước
này** — lỗ hổng dữ liệu im lặng chính là loại vấn đề dự án này đã tốn nhiều
công để dọn.

## 5. Điều KHÔNG làm

- **Không** bật `real_trading_enabled` để "diễn tập cho giống thật".
- **Không** kéo dài quá 10 phút — mất càng nhiều bar càng phải bù nhiều.
- **Không** diễn tập lại trong vòng 30 phút: chống spam sẽ nuốt tin thứ hai và
  bạn sẽ kết luận sai là chuông hỏng.

## 6. Nộp lại cho tôi

Chỉ cần bốn dòng:

```
Chặng A: có / không nhận được tin
Giờ tắt Docker:        HH:MM
Giờ nhận tin Telegram: HH:MM  (hoặc: không nhận được)
Giờ bật lại Docker:    HH:MM
```

Tôi sẽ ghi kết quả vào tài liệu, và nếu đạt thì D1 đóng — lần đầu tiên chuông
báo của hệ thống này có bằng chứng là kêu thật.
