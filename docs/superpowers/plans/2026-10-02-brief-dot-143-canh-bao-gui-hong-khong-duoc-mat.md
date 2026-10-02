# Brief đợt 143 — cảnh báo gửi hỏng không được mất: hàng đợi gửi lại cho `trading.alerts.alert`

Đợt này chạy **song song** với đợt 142, do một agent khác làm. Hai đợt **không được đụng file của
nhau**; xem mục Giới hạn.

## Vì sao — số đo thật từ log collector 72 giờ qua (29/09–02/10)

`trading/alerts.py::alert()` mở một luồng chạy nền gọi `send_telegram` **đúng một lần** và bỏ kết quả.
Gửi hỏng là cảnh báo **mất vĩnh viễn**. Trong 72 giờ, collector ghi **12 lần**
`Loi khi gui tin Telegram: URLError: <urlopen error [Errno -2] Name or service not known>`. Ví dụ, giờ
UTC, nguyên văn:

```
2026-10-02T00:35:36.112Z {"level": "CRITICAL", "msg": "phát hiện máy chủ ngủ/gián đoạn 953s (ngoài giờ giao dịch) từ 07:19:13 đến 07:35:36", ...}
2026-10-02T00:35:36.406Z Loi khi gui tin Telegram: URLError: <urlopen error [Errno -2] Name or service not known>
2026-10-02T00:35:36.454Z Loi khi gui tin Telegram: URLError: <urlopen error [Errno -2] Name or service not known>
2026-10-02T00:35:37.001Z Loi khi gui tin Telegram: URLError: <urlopen error [Errno -2] Name or service not known>
```

Chủ dự án **không bao giờ nhận** cảnh báo đó. Đây là lỗi cấu trúc, không phải xui: cảnh báo "máy vừa
ngủ / mất kết nối" phát ra **đúng lúc mạng kém nhất**, ngay khi vừa thức. `alert()` có khoảng 90 chỗ
gọi trong `trading/`, gồm `collector/main.py`, `account_sync.py`, `engine/logic.py`, và
**`real_orders.py`** (14 chỗ, đường lệnh thật). Một cảnh báo về lệnh thật bị nuốt vì mạng chập một giây
là không chấp nhận được trước go-live.

Các script theo lịch **không** thuộc diện này. Chúng gọi `send_telegram` trực tiếp, đọc giá trị trả về,
thoát mã 2 khi gửi hỏng, và chỉ lưu trạng thái khi gửi được, nên lần chạy sau sẽ báo lại. Đừng đụng
vào chúng.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không restart/rebuild container. Không sửa `.env`, không sửa
  scheduled task.
- **KHÔNG gửi Telegram thật.** Mọi test dùng hàm gửi giả được tiêm vào.
- **Chỉ được sửa:** `trading/alerts.py`, `trading/collector/main.py` và `trading/engine/main.py` (mỗi
  file **đúng một lời gọi khởi động** hàng đợi, xem Việc 3), cùng test mới `tests/test_alert_outbox.py`.
- **KHÔNG đụng** (đợt 142 đang sửa, hoặc ngoài phạm vi): `trading/telegram.py` (giữ nguyên hợp đồng
  `send_telegram -> bool`, các script dựa vào nó), mọi file trong `scripts/`, `DEPLOYMENT.md`,
  `tests/test_heartbeat_check.py`, `tests/test_container_health_check.py`. Phần tài liệu vận hành thì
  viết vào báo cáo; Claude sẽ ghép vào `DEPLOYMENT.md` sau khi cả hai đợt xong.
- Code trong `trading/` chỉ có hiệu lực sau khi image được build lại. Việc đó Claude làm; agent không
  build. Sau khi Claude commit, `deploy-drift` sẽ báo lệch triển khai cho tới khi rebuild. Đó là đúng
  việc của nó, không phải lỗi.
- GitNexus: `impact` trên `alert` **trước khi sửa** và dán kết quả (nhiều nơi gọi — đây là thay đổi rộng
  nhất trong đợt). `detect_changes` sau khi sửa.

## Thiết kế

1. **Hợp đồng của `alert()` giữ nguyên**: cùng chữ ký, vẫn ghi log ngay, vẫn trả `Thread | None`, và
   **không bao giờ ném** (nguyên tắc chuông chết-người: `_print_safe` trong cùng file giải thích vì
   sao).
2. Gửi hỏng (`send_telegram` trả `False` hoặc ném) → nối một dòng JSON vào file hàng đợi:
   `{"emitted_at": <ISO có múi giờ>, "text": <nội dung>}`.
3. Một luồng chạy nền duy nhất cho mỗi tiến trình, cứ **60 giây** thử gửi lại hàng đợi **theo thứ tự**.
   Mỗi tin gửi lại có tiền tố nói rõ đây là tin trễ và giờ phát gốc, vd
   `[GỬI TRỄ — phát lúc 07:35:36 02/10] ...`. Dừng ở tin đầu tiên còn hỏng (giữ thứ tự, không bỏ cách).
   Gửi được tin nào thì xoá tin đó khỏi file.
4. **Bền qua khởi động lại:** file nằm dưới `/app/logs` (đã đo: thư mục này gắn ra `./logs` trên host,
   ghi được bằng uid 10001 trong cả collector lẫn engine). Collector và engine dùng **hai file riêng**,
   để hai tiến trình không tranh ghi một file.
5. **Có giới hạn:** tối đa 200 tin. Đầy thì bỏ tin **cũ nhất**, đếm số tin đã bỏ, và lần gửi lại thành
   công kế tiếp phải kèm một dòng "đã bỏ N cảnh báo cũ vì hàng đợi đầy". Không im lặng bỏ.
6. Ghi file an toàn khi có nhiều luồng: một `threading.Lock` cho mọi thao tác đọc/ghi hàng đợi; ghi lại
   cả file thì ghi ra file tạm rồi đổi tên.
7. Không gọi khởi động (vd chạy `alert()` từ script hay từ test) thì hành vi **y như hiện nay**: gửi một
   lần, hỏng thì thôi, không tạo file nào.

## Việc

1. Cài thiết kế trên trong `trading/alerts.py`, kèm một hàm khởi động nhận **tên dịch vụ** và **thư mục**
   (mặc định thư mục log của tiến trình). Hàm này tạo luồng gửi lại và gửi ngay những gì còn tồn từ lần
   chạy trước.
2. Hàm gửi và đồng hồ phải **tiêm được**, để test không gọi mạng và không phải chờ 60 giây thật.
3. Thêm đúng **một** lời gọi hàm khởi động ở đầu phần chạy của `trading/collector/main.py` và của
   `trading/engine/main.py`. Không đổi gì khác trong hai file đó.

## Tiêu chí hoàn thành

1. `tests/test_alert_outbox.py`, với hàm gửi giả:
   - gửi được ngay → không có file hàng đợi;
   - gửi hỏng → đúng một dòng trong file, có `emitted_at` và nội dung;
   - hàm gửi **ném ngoại lệ** → `alert()` không ném, tin vào hàng đợi;
   - mạng hồi lại → các tin gửi đúng thứ tự, có tiền tố giờ phát gốc, file rỗng sau đó;
   - tin thứ 2 trong 3 vẫn hỏng → tin 1 đi, tin 2 và 3 ở lại, đúng thứ tự;
   - **khởi động lại:** dựng một file hàng đợi có sẵn, gọi hàm khởi động → các tin cũ được gửi;
   - quá 200 tin → bỏ tin cũ nhất, và lần gửi thành công kế tiếp có dòng "đã bỏ N";
   - file hàng đợi hỏng (một dòng không phải JSON) → không chết, không mất các dòng tốt, và dòng hỏng
     được báo, không lặng lẽ bỏ;
   - không gọi khởi động → hành vi y như cũ, không tạo file;
   - hai luồng cùng gọi `alert()` khi mạng hỏng → không mất tin, không hỏng file.
2. **Tái hiện đúng sự cố:** một test dùng nguyên văn nội dung cảnh báo `phát hiện máy chủ ngủ/gián đoạn
   953s ...` ở trên, hàm gửi hỏng 3 lần rồi được → tin tới đích với tiền tố
   `phát lúc 07:35:36 02/10` (giờ VN).
3. **Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:**
   - bỏ bước ghi vào hàng đợi khi gửi hỏng → test "gửi hỏng" đỏ;
   - gửi lại không theo thứ tự (vd đảo danh sách) → test thứ tự đỏ;
   - bỏ dòng "đã bỏ N" → test hàng đợi đầy đỏ.
4. Chạy thật **không cần mạng và không gửi Telegram**: một đoạn script nhỏ (để trong báo cáo, không
   commit) gọi hàm khởi động với thư mục tạm và hàm gửi giả hỏng 2 lần rồi được, chạy `alert("CRITICAL", ...)`,
   và in nội dung file hàng đợi trước/sau. Dán đầu ra.
5. `docker compose config -q` sạch. `ruff` sạch; `uv run pytest -q` ≥ **1.706 passed** cộng số test mới.
   Nếu đợt 142 đã đổi số mốc trước khi bạn xong thì ghi số thật và nói rõ.

## ⚠ Chạy song song với một agent khác — đừng chạy hai bộ test đầy đủ cùng lúc

Đợt 142 và đợt 143 do hai agent làm cùng lúc trên một máy. Cả hai dùng chung DB `trading_test` và NATS
cổng 4223. Hai lần `uv run pytest -q` (có integration) chạy chồng nhau sẽ tranh nhau một stream NATS và
sinh **lỗi giả**, trông y như test chập chờn (đã gặp 13/08: 10 phút 46 giây và đỏ lung tung thay vì 14,6
giây và xanh).

- Trong lúc làm: chạy `uv run pytest -q -m "not integration"`, cộng file test của chính mình.
- Chỉ chạy bộ đầy đủ khi **không có pytest nào khác đang chạy**:
  `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pytest' }` phải rỗng ngay trước đó.
- Gặp lỗi integration lạ thì kiểm điều này **trước** khi nghi code của mình.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-143-hang-doi-canh-bao.md`:

- Kết quả `gitnexus impact` trên `alert`.
- Đoạn văn đề xuất cho `DEPLOYMENT.md`: file hàng đợi ở đâu, đọc thế nào, xoá được không.
- Số đo dán nguyên văn.
- Brief sai ở đâu thì nói ra.
- Cái gì không kiểm được (đường thật trong container sau rebuild, Telegram thật) thì ghi là **không
  kiểm được**. Claude sẽ kiểm sau khi rebuild.
