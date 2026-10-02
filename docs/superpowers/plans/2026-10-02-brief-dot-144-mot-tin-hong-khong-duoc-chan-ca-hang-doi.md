# Brief đợt 144 — một tin hỏng vĩnh viễn không được chặn cả hàng đợi cảnh báo

Việc nhỏ, sửa lỗi thiết kế do **Claude** viết trong brief đợt 143. Phải xong **trước** khi Claude build
lại image collector/engine.

## Vì sao — Claude tái hiện trên code thật đợt 143

`send_telegram` trả `False` cho **mọi** thất bại: mất mạng (tạm thời) và Telegram từ chối tin (vĩnh viễn,
vd HTTP 400 khi tin dài quá 4.096 ký tự). `AlertOutbox.flush()` dừng ở tin đầu tiên còn hỏng. Một tin
vĩnh viễn hỏng ở đầu hàng đợi vì thế chặn **mọi** tin sau nó, và vì file nằm trên đĩa nên khởi động lại
cũng không gỡ được.

Đo thật bằng hàm gửi giả bắt chước giới hạn 4.096 của Telegram:

```
hang doi sau khi mat mang: 3
  lan gui lai 1..5: gui duoc 0, con 3
da toi dich: []
do dai tin dau khi gui lai (co tien to GUI TRE): 4106
```

Tin đầu dài 4.070 ký tự, vốn gửi được nếu có mạng. Chính tiền tố `[GỬI TRỄ — ...]` đẩy nó qua giới hạn.
Tin `lenh that bi tu choi` xếp sau thì không bao giờ tới.

Lỗi thứ hai, cũng đo trong image thật: nếu `/app/logs` tồn tại nhưng **không ghi được**, `start_outbox`
vẫn bật. Mọi tin hỏng sau đó in `LOI: khong ghi duoc hang doi canh bao (PermissionError)` và mất, không
ai biết.

## Giới hạn

- **KHÔNG commit, KHÔNG push**, không build/restart container, không gửi Telegram thật.
- Chỉ sửa `trading/alerts.py` và `tests/test_alert_outbox.py`. **Không** đụng `trading/telegram.py`
  (hợp đồng `-> bool` giữ nguyên), `scripts/`, `DEPLOYMENT.md`.
- Đợt 142 có thể đang chạy song song: **không chạy hai bộ test đầy đủ cùng lúc**. Kiểm
  `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pytest' }` rỗng trước khi chạy
  `uv run pytest -q`; trong lúc làm thì chạy `-m "not integration"` cộng file test của mình.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc

1. **Không để độ dài tự tạo ra tin hỏng:** mọi văn bản đi qua `AlertOutbox`, cả lúc gửi lần đầu lẫn lúc
   gửi lại **sau khi đã gắn tiền tố và dòng "đã bỏ N"**, không được dài quá một ngưỡng an toàn dưới
   4.096 (đề xuất 3.900). Quá thì cắt và ghi rõ trong tin là đã cắt bao nhiêu ký tự. Không cắt im lặng.
   Chỉ áp dụng trong đường hàng đợi; đường `start_outbox` chưa bật thì giữ y như cũ.
2. **Tin đầu hỏng thì thử tin kế tiếp:** khi tin đầu hỏng, thử gửi tin thứ hai **một lần**.
   - Tin thứ hai cũng hỏng → coi là mất mạng; dừng như hiện nay, giữ nguyên thứ tự.
   - Tin thứ hai **được** → mạng đang có. **Thử lại tin đầu thêm một lần nữa** ngay lúc đó: mạng có thể chỉ
     chập đúng lúc gửi tin đầu (Claude tự soát ra lỗ này ở bản nháp đầu, khi tin đầu bị gỡ oan). Lần
     thử lại vẫn hỏng thì tin đầu mới là tin hỏng vĩnh viễn. Gỡ nó khỏi hàng đợi, ghi
     đầy đủ nội dung ra log, rồi gửi một dòng ngắn "bỏ 1 cảnh báo không gửi được, phát lúc …, xem log"
     (dòng này cũng qua hàng đợi nếu hỏng). Sau đó tiếp tục gửi phần còn lại theo thứ tự.
   - Hàng đợi chỉ còn một tin và nó hỏng → không biết là mạng hay tin. Giữ lại, thử lại chu kỳ sau. Đừng
     đoán.
3. **Kiểm quyền ghi lúc khởi động:** `start_outbox` thử tạo rồi xoá một file trong thư mục. Không được →
   **không bật**; ghi một dòng `CRITICAL` vào log và gửi thử **một** tin Telegram nói rõ hàng đợi cảnh
   báo của dịch vụ nào đang tắt và vì sao. Trả `None` như khi thư mục không tồn tại.

## Tiêu chí hoàn thành

1. Test mới, hàm gửi giả bắt chước Telegram (trả `False` khi `len(text) > 4096`, hoặc khi "mất mạng"):
   - tái hiện đúng ca A.2: tin 4.070 ký tự + hai tin thường, mất mạng rồi có mạng → **cả ba tới đích**,
     tin dài bị cắt và ghi rõ số ký tự đã cắt, không tin nào vượt 4.096;
   - một tin hỏng vĩnh viễn (hàm giả từ chối riêng nội dung đó) ở đầu, hai tin sau tốt → hai tin sau tới
     đích, tin hỏng bị gỡ khỏi file và có dòng "bỏ 1 cảnh báo không gửi được";
   - mất mạng hoàn toàn → không tin nào bị gỡ, thứ tự giữ nguyên (**không** coi mất mạng là tin hỏng);
   - tin đầu hỏng **một lần** rồi gửi được (mạng chập đúng lúc đó), tin thứ hai được → tin đầu **không**
     bị gỡ và tới đích;
   - hàng đợi chỉ một tin, nó hỏng → vẫn còn trong file sau `flush()`;
   - thư mục không ghi được → `start_outbox` trả `None`, có dòng CRITICAL, `alert()` vẫn không ném.
2. Mọi test đợt 143 vẫn xanh; nếu phải sửa test nào thì nói rõ vì sao.
3. **Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:**
   - bỏ bước cắt độ dài → ca A.2 đỏ;
   - bỏ bước thử tin kế tiếp → ca tin hỏng vĩnh viễn đỏ;
   - coi "tin thứ hai cũng hỏng" là tin đầu hỏng vĩnh viễn → ca mất mạng hoàn toàn đỏ (**đây là phá thử
     quan trọng nhất**: sai chỗ này thì một lần mất mạng sẽ xoá sạch hàng đợi).
4. `ruff` sạch; `uv run pytest -q` ≥ **1.718 passed** cộng số test mới (hoặc mốc mới nếu đợt 142 đã đổi
   trước, ghi số thật).

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-144-tin-hong-khong-chan-hang-doi.md`. Số đo nguyên văn; brief
sai ở đâu thì nói ra; cái gì không kiểm được thì ghi là không kiểm được.
