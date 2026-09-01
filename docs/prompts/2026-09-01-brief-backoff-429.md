# Brief 2026-09-01 (đợt 5) — Backoff đủ dài cho 429, và chỉ dấu "đã nối" phải nói thật

Dành cho agent thực thi. Tự chứa: đọc file này là đủ để làm.

Đây là **lỗ hổng vận hành duy nhất còn hở**. Không gấp — nhưng nếu 429 rơi vào
một phiên giao dịch thật, hệ thống có thể tự nhốt mình ngoài cửa cả phiên.

---

## 1. Chuyện đã xảy ra, và chuyện đã KHÔNG xảy ra

Sáng 01/09/2026, collector bị SSI từ chối kết nối WebSocket **440 lần** với
HTTP 429 trong khoảng 2 giờ. REST vẫn 200 bình thường.

**Nó không gây thiệt hại**, vì 01/09 là ngày nghỉ lễ — không có phiên nào để
mất. Đó là may, không phải thiết kế. Brief này tồn tại để lần sau không phải
trông vào may.

### Đã đo, không phải suy đoán (Task A của brief đợt 3)

| Đo | Kết quả |
|---|---|
| Số lần 429 | 440 trong ~2 giờ |
| Nhịp giữa các lần `SSIFeed connection error` | 34 lỗi / 52,5 phút; gap **93–108s**, trung vị **95s**, 33/33 gap nằm trong 90–120s |
| Phép thử im lặng | dừng collector 12:00:18 → im **10 phút** → **một** nỗ lực WS đơn lẻ lúc 12:10:31 → **CONNECT OK trong 1 giây**, subscribe OK |
| Client khác giữ chỗ | không có (mọi kết nối tới `stream.ssi.com.vn` đều từ chính collector) |

**Kết luận đã chốt: rate-limit do chính ta gây ra.** Không phải phía SSI khoá
tài khoản, không phải kết nối zombie. Im 10 phút là gỡ được.

### Vì sao 95 giây là con số chết người

Ba tầng thử lại xếp chồng:

- `ssi-sdk` tự thử **5 lần** mỗi lần `connect()` (backoff nội bộ 2/4/8/16s ≈ 30s).
- `SSIFeed._run` (`trading/collector/feed.py:180`) nhân đôi backoff, **trần 60s**.
- Cộng lại: một vòng ≈ 95 giây, và **mỗi vòng gõ cửa SSI 5 lần**.

Tức ~190 lần gõ cửa mỗi giờ, liên tục. Trần 60s là **đúng thiết kế cho lỗi
mạng thoáng qua**, nhưng sai hoàn toàn cho một cánh cửa đang khoá 10 phút:
backoff bò lên trần rồi đứng đó, không bao giờ đủ dài để rate-limit hết hạn.

> Bản sửa đợt 3 (`ed17539`) **cố ý không đụng backoff** — vì Task A1 chứng minh
> backoff *không bị reset*, và brief đợt 3 chỉ cho sửa cái đã chứng minh là sai.
> Đó là quyết định đúng theo brief đó. Nhưng brief đợt 3 hỏi thiếu một câu:
> *"backoff chạy đúng thiết kế — nhưng thiết kế có đủ không?"* Brief này hỏi câu đó.

---

## 2. Lỗi thứ hai: `_stream is not None` không có nghĩa là "đã nối"

`trading/collector/feed.py`:

```
154:   self._stream = AsyncStream(self._auth)     <-- gán ở ĐÂY
156:   await self._stream.streaming.connect()     <-- mới nối ở ĐÂY
174:   self._stream = None                        (finally)
```

`restart()` (dòng 134) trả `True` khi `self._stream is not None`. Nhưng
`_stream` được gán **trước** `connect()`. Nên trong suốt cửa sổ ~30 giây mà SDK
đang thử 5 lần, `_stream` đã khác None trong khi **chưa nối được gì** —
`restart()` vẫn trả `True`, và `_restart_feed_and_alert`
(`trading/collector/main.py:23`) vẫn kêu `"feed stale, forcing reconnect"`.

Bản sửa đợt 3 làm chuông **bớt** nói dối, chưa làm nó **hết** nói dối.

---

## 3. Môi trường

- Windows 11, PowerShell + Git Bash. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- `docker compose` đang chạy. Truy vấn DB:
  `docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "..."`
- **`DB_DSN` phải dùng `127.0.0.1`, KHÔNG `localhost`** (localhost ra IPv6 trước,
  treo ~30s mỗi lần).
- Chạy script cần env: `set -a && . ./.env && set +a`, hoặc dùng
  `scripts/run_if_docker_up.sh` (đã lo `.env`, `DB_DSN`, `PYTHONIOENCODING`).
- Lệnh quá 10 phút bị cắt — việc dài chạy tách rời, theo dõi file log.
- Test đầy đủ cần NATS riêng: `docker compose --profile test up -d nats-test`.
- Không in giá trị secret ra bất cứ đâu.

---

## 4. Phạm vi phẫu thuật

**Được sửa:** `trading/collector/feed.py`, `trading/collector/main.py`,
`tests/test_feed.py`, `tests/test_collector_main.py`.

**KHÔNG được đụng:** `trading/engine/*`, `trading/real_orders.py`,
`trading/risk.py`, `trading/storage/db.py`, `trading/backtest.py`,
`trading/strategies/*`, `config/config.yaml`, `scripts/*` (cả
`heartbeat_check.py`, `sched.sh`, `run_if_docker_up.sh`, `run_hidden.vbs`),
và các scheduled task đã cài.

> `config/config.yaml` nằm trong danh sách cấm **kể cả khi** bạn thấy nên thêm
> tham số cấu hình mới cho backoff. Nếu bạn cho rằng cần, **báo cáo đề xuất** —
> chủ dự án quyết. Hằng số trong code là chấp nhận được cho task này.

---

## 5. Task A — Backoff riêng cho 429, đủ dài để rate-limit hết hạn

Vấn đề: mọi lỗi kết nối hiện dùng chung một thang backoff trần 60s. Một lỗi
mạng thoáng qua và một rate-limit 10 phút **không cùng loại**, không được xử
lý như nhau.

**Yêu cầu:** khi nguyên nhân thất bại là **429**, backoff phải đi tới thang
**phút**, đủ để vượt qua cửa sổ rate-limit đã đo (**10 phút là mốc duy nhất có
số**). Lỗi khác giữ nguyên hành vi hiện tại — **không đổi trần 60s cho chúng**.

Ba điều phải tự quyết và nói rõ lý do trong báo cáo:

1. **Nhận biết 429 thế nào.** Exception từ SDK là gì, chuỗi lỗi ra sao. Đã biết:
   thông điệp chứa `server rejected WebSocket connection: HTTP 429`. Bám chuỗi
   text là mong manh — nếu SDK có kiểu exception hoặc mã trạng thái dùng được
   thì dùng cái đó và nói rõ; nếu không có thì bám chuỗi **và ghi rõ đó là điểm
   mong manh**, đừng giả vờ nó chắc chắn.
2. **Thang backoff bao nhiêu.** Nêu con số và căn cứ. Mốc duy nhất có bằng
   chứng là 10 phút im lặng thì nối được. Đừng chọn số đẹp rồi tìm lý do sau.
3. **Có trần trên không**, và điều gì reset nó (nối thành công? sang phiên mới?).

→ **Kiểm chứng (test, dùng đồng hồ/stream giả kiểu đã có sẵn trong
`tests/test_feed.py`):**
- Lỗi 429 liên tiếp ⇒ khoảng chờ **tăng tới thang phút**, không dừng ở 60s.
- Lỗi **không phải** 429 ⇒ khoảng chờ giữ nguyên hành vi cũ (trần 60s).
- Nối thành công ⇒ backoff reset đúng như quy tắc bạn đã nêu ở (3).

Test phải khẳng định **khoảng chờ thực tế**, không phải khẳng định code trông
ra sao.

---

## 6. Task B — `restart()` chỉ được trả `True` khi thật sự đã nối

Sửa để chỉ dấu nói đúng sự thật: phân biệt **"đã tạo object stream"** với
**"đã `connect()` xong"**. Cách làm tuỳ bạn (một cờ đặt sau `connect()`, hoặc
chỉ gán `self._stream` sau khi nối xong — cân nhắc kỹ cái thứ hai vì `stop()`
và `restart()` đang dựa vào `_stream` để ngắt kết nối đang treo).

→ **Kiểm chứng:**
- Chưa từng nối (`_stream` None) ⇒ `restart()` trả `False`, không kêu. *(test này
  đã có, phải tiếp tục xanh)*
- **Đang trong `connect()` chưa xong** ⇒ `restart()` trả `False`, **không kêu**.
  Đây là ca mới, là trọng tâm của Task B.
- Đã nối xong ⇒ `restart()` trả `True`, có `disconnect()`, có kêu.

---

## 7. Task C — Kiểm chứng thực địa

Test xanh **không đủ**. Bài học ngày 01/09: bản sửa `ed17539` có test xanh, có
sabotage đỏ, có ruff sạch — và vẫn giết chuông báo trên máy thật, vì môi trường
test không giống môi trường chạy (`capsys` bắt stdout bằng utf-8, còn scheduled
task ghi ra file bằng cp1252).

1. Khởi động lại collector, theo dõi **15 phút**, dán bảng mốc giờ mọi dòng
   `SSIFeed connection error` và `feed stale, forcing reconnect`.
   → Ngày thường (không 429): nhịp phải **không xấu đi** so với hiện tại.
2. **Không được cố tình gây ra 429 để thử.** Gõ cửa SSI dồn dập để tái hiện
   rate-limit là đúng cái hành vi brief này sinh ra để diệt. Nếu 429 tự xảy ra
   trong lúc bạn làm thì dán log lại — đó là quà. Nếu không, nói rõ **chưa quan
   sát được 429 thật sau khi sửa**, và đó là kết cục hợp lệ.

---

## 8. Sabotage (bắt buộc, mỗi thay đổi một lần)

Phá lại đúng chỗ vừa sửa, chạy test, **dán nguyên văn output ĐỎ**, khôi phục,
chạy lại cho xanh. Test không đỏ khi phá ⇒ test đó không kiểm gì cả ⇒ viết lại
test, đừng viết lại báo cáo.

---

## 9. Cấm

- **Không commit, không push.** Claude audit rồi mới commit.
- **Không bật `real_trading_enabled`.** Đã có kết luận `711683a`: không chiến
  lược nào thắng mua-và-giữ, engine chỉ chạy paper. Không có lý do nào để bật.
- Không sửa `config/config.yaml`.
- Không gọi API đặt/huỷ lệnh SSI.
- **Không cố tình gây 429** (xem Task C2).
- Không `TRUNCATE`, không `DROP`, không xoá dòng nào trong DB.
- Không in giá trị secret.
- Phát hiện ngoài phạm vi: **báo cáo**, không tự sửa.
- Trước khi sửa symbol nào: `gitnexus_impact`, nói ra blast radius. Sau khi sửa:
  `gitnexus_detect_changes`, đối chiếu với mục 4.

---

## 10. Tiêu chí hoàn thành

- Task A: ba quyết định (nhận biết 429 / thang backoff / trần và reset) nêu rõ
  kèm căn cứ; ba test hành vi xanh.
- Task B: ba ca kiểm chứng, đặc biệt ca **"đang connect chưa xong"**.
- Task C: bảng mốc giờ 15 phút quan sát thật; nói thẳng nếu chưa quan sát được
  429 sau khi sửa.
- Output sabotage dán nguyên văn.
- `uv run pytest -m "not integration" -q` xanh (hiện tại: **336 passed**).
- `uv run ruff check trading tests scripts` sạch.
- Việc nào không làm được thì nói rõ vì sao.

> **Một điều cuối, đọc kỹ.** Ngày 01/09 có hai báo cáo agent chứa số **không tái
> lập được** — một cái kết luận "feed đã hồi" dựa trên dữ liệu đo trong giờ nghỉ
> trưa, một cái đưa ra cả bảng số cùng lời giải thích hợp lý cho một hiện tượng
> không tồn tại. Cả hai đều bị bắt bằng cách **chạy lại và đối chiếu số**.
> Báo cáo của bạn sẽ được kiểm theo đúng cách đó. Số nào bạn không thật sự chạy
> ra thì đừng viết vào — nói "chưa đo được" luôn là câu trả lời chấp nhận được.
