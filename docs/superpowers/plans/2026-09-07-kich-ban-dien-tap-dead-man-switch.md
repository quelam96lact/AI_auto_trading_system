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

---

# KẾT QUẢ — D1 ĐẠT, ĐÓNG (07/09/2026)

Claude tự đọc lại dấu vết trên hệ thống, không dựa vào báo cáo.

## Bốn mốc

```
Chặng A: nhận được tin (10:06)
Giờ tắt Docker:        10:06:37
Giờ nhận tin Telegram: 10:10:05
Giờ bật lại Docker:    10:10:27
Độ trễ phát hiện:      3 phút 28 giây  (thiết kế: ≤ 10 phút)
```

**Kết quả: "Tin về trong ≤ 10 phút" — Đạt.** Mốc trễ thật **3 phút 28 giây**
là con số tham chiếu cho lần sau.

## Bằng chứng tự kiểm

`logs/heartbeat.log`:

```
2026-09-07 10:10:05 heartbeat-check SKIP: docker chua chay
[CRITICAL] Docker khong chay luc 10:10 ngay giao dich 07/09.
Collector/engine deu dung. Khong co bar moi, khong co lenh.
Cac job giam sat dang bi bo qua — day la tin nhan DUY NHAT ban se nhan.
ALERT_EXIT=0
2026-09-07 10:15:04 heartbeat-check start
EXIT=0
```

- `ALERT_EXIT=0` ⇒ gửi Telegram **thành công**, không phải gửi hụt im lặng.
- `logs/.docker_down_last_alert` = `1788750607` = **10:10:07 giờ VN** — khớp.
- 10:15:04 `EXIT=0` ⇒ chu kỳ kế tiếp đã sạch, hệ thống phục hồi.

## Chuông token cũng kêu đúng — phát hiện thêm, ngoài kịch bản

Cùng file log cho thấy một sự kiện thứ hai mà báo cáo diễn tập không nêu:

```
09:50, 09:55, 10:00  [WARN]     token SSI sắp hết hạn (10:02 07/09)
10:05                [CRITICAL] token SSI đã hết hạn hoặc không có trong DB
```

Token hết hạn 10:02, chuông cảnh báo trước 3 nhịp rồi báo CRITICAL. Đối chiếu
DB: `refresh_token_expires_at` = **18:05:51**, trừ 8 giờ vòng đời ⇒ OTP được
làm lúc **~10:05:51**, tức ngay sau tiếng chuông. **Chuông kêu → người xử lý →
hệ thống hồi phục.** Đây là bằng chứng thứ hai, không nằm trong kịch bản, rằng
lớp cảnh báo hoạt động thật.

## §4 của kịch bản — kiểm lỗ hổng bar: KHÔNG mất bar nào

Bước này kịch bản bắt buộc ("đừng bỏ qua") và báo cáo diễn tập đã bỏ qua.
Claude tự kiểm. Bar 5 phút của 3 mã trong ngày 07/09:

| Mốc | Số mã có bar | Nhận xét |
|---|---|---|
| 09:15 → 09:50 | 3/3 | đủ |
| **09:55** | 2/3 (thiếu HII) | **trước lúc tắt Docker 10 phút** |
| 10:00 | 3/3 | đủ |
| **10:05** | 2/3 (thiếu HII) | trùng khoảng tắt |
| **10:10** | 3/3 | đủ — dù đây là bucket chứa phần lớn thời gian tắt |
| 10:15 | 3/3 | đủ |
| 10:20 | 2/3 | bar đang hình thành lúc đo, không phải lỗ hổng |

**Kết luận: diễn tập không gây mất bar nào phát hiện được.** Lý do tin được
điều đó: mẫu "thiếu HII" xuất hiện ở **09:55, trước khi tắt Docker**, nên nó
độc lập với diễn tập. Và đợt 12 (07/09) đã chứng minh bar chỉ tồn tại khi có
**cú khớp thật** — HII là mã mỏng nhất trong rổ (đợt 10: 0 tín hiệu bull trên
3.211 bar). Nên hai chỗ thiếu HII là bản chất thanh khoản, không phải mất dữ
liệu. **Không cần backfill bù.**

## D1 đóng

Lần đầu tiên chuông báo của hệ thống này có bằng chứng là **kêu thật**, đo được
độ trễ thật, và người nhận đã phản ứng đúng trong cùng phiên.
