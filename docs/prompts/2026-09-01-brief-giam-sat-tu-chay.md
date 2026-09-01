# Brief 2026-09-01 — Làm cho giám sát tự chạy và chứng minh nó kêu

Dành cho agent thực thi. Tự chứa: đọc file này là đủ để làm, không cần hỏi lại
bối cảnh. Kế hoạch đầy đủ ở `docs/superpowers/plans/2026-09-01-golive-giam-sat-va-du-lieu.md`.

---

## 1. Chuyện đã xảy ra (đo ngày 01/09/2026, không phải suy đoán)

Hệ thống **không chạy suốt phiên giao dịch thứ Hai 31/08**, mất trọn một phiên
dữ liệu, và **không một cảnh báo nào phát ra**.

| Đo | Kết quả | Cách đo lại |
|---|---|---|
| Container khởi động lại | 31/08 18:08 UTC = 01/09 01:08 giờ VN | `docker inspect -f '{{.State.StartedAt}}' ai_auto_trading_system-collector-1` |
| Log collector khung phiên 31/08 | 0 dòng | `docker logs --since 2026-08-31T01:50:00 --until 2026-08-31T08:00:00 ai_auto_trading_system-collector-1 \| wc -l` |
| `bars_daily` mới nhất | 2026-08-28 | `SELECT max((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) FROM bars_daily;` |
| `bars` 5m mới nhất | 2026-08-28 14:45 giờ VN | `SELECT symbol, max(ts) FROM bars WHERE symbol IN ('HII','IJC','AAA') GROUP BY 1;` |
| Lịch chạy tự động | **không có cái nào** | `schtasks /query /fo LIST` |

Nguyên nhân: `scripts/heartbeat_check.py` (chuông báo 2A/2B/2C/2D) **chưa từng
được cài vào lịch chạy ở đâu cả**. Code đúng, có test đầy đủ — chỉ chưa bao giờ
được gọi.

**Việc của bạn không phải viết thêm chuông. Là làm cho chuông có sẵn thật sự kêu.**

---

## 2. Môi trường

- Windows 11. Có sẵn **PowerShell** và **Git Bash**. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- `docker compose` đang chạy: postgres, nats, nats-test, collector, engine, grafana.
- Truy vấn DB nhanh nhất:
  `docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "..."`
- **Chạy script Python cần DB: `DB_DSN` phải dùng `127.0.0.1`, KHÔNG dùng
  `localhost`.** Trên máy này `localhost` phân giải ra IPv6 trước và mỗi lần kết
  nối treo ~30 giây. Đây là bẫy đã mất thời gian một lần rồi.
- Các script **không tự đọc `.env`**. Trong Git Bash:
  `set -a && . ./.env && set +a` trước khi chạy.
- `.env` có đủ `SSI_*`, `DB_DSN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
  **Không in giá trị của chúng ra bất cứ đâu** — báo cáo chỉ được nhắc tên biến.
- Lệnh chạy quá **10 phút** sẽ bị cắt. Việc dài phải chạy tách rời
  (`Start-Process` trong PowerShell) rồi theo dõi file log.

### Một điều phải biết trước khi hoảng

`heartbeat_check.py` **thoát ngay với mã 0 khi ngoài giờ giao dịch**
(`scripts/heartbeat_check.py:160-166`) — chỉ chạy thật trong 09:00–14:45 và
khung 08:00–08:59 các ngày trong tuần.

Và khi bạn chạy nó lần đầu, **cảnh báo 2A "dữ liệu ngừng chảy" sẽ nổ ngay** — vì
bar mới nhất đúng là từ 28/08. **Đó là cảnh báo ĐÚNG, không phải dương tính giả.
Không được "sửa" nó cho im.** Nó im lại khi Task C nạp xong dữ liệu.

---

## 3. Task A — Chứng minh chuỗi cảnh báo chạy được đầu-tới-cuối

> **CỔNG CHẶN: chỉ được bắt đầu Task A khi chủ dự án nói rõ "chạy diễn tập".**
> Task này **dừng collector thật giữa phiên** và làm mất vài phút dữ liệu.
> Chưa có câu đó thì làm Task B và C trước.

Phải làm trong giờ giao dịch. Hôm nay 01/09 là phiên; **02/09 nghỉ lễ Quốc khánh**;
phiên kế tiếp là 03/09.

1. Chạy `heartbeat_check.py` ở trạng thái bình thường. Ghi lại **nguyên văn**
   output và exit code.
   → *Kỳ vọng:* 2A nổ (xem mục 2 ở trên). Ghi nhận, đi tiếp.

2. `docker compose stop collector`. **Ghi mốc giờ chính xác.**

3. Chờ **quá 5 phút** (`DEFAULT_MAX_AGE_SECONDS = 300`). Chạy lại
   `heartbeat_check.py`.
   → *Kiểm chứng:* exit code 1, **và một tin nhắn Telegram THẬT tới máy chủ dự
   án** nói collector ngừng đập heartbeat.

4. `docker compose start collector`. Chờ heartbeat xanh lại, chạy lần nữa.
   → *Kiểm chứng:* cảnh báo về collector biến mất.

5. Báo cáo: dán **nguyên văn nội dung tin nhắn Telegram**, kèm ba mốc giờ (dừng,
   nhận tin, khởi động lại).

**Nếu không nhận được tin nhắn nào:** DỪNG LẠI. Báo cáo ngay, **không tự sửa
code cho nó gửi được**. Chuỗi cảnh báo hỏng là phát hiện quan trọng nhất của cả
đợt này — nó phải được chủ dự án nhìn thấy nguyên trạng.

**Ràng buộc:** chỉ dừng `collector`. **KHÔNG** dừng `engine`, `postgres`, `nats`.
Diễn tập đúng **một lần**. Dữ liệu thiếu do dừng sẽ vá ở Task C.

---

## 4. Task B — Cài lịch để nó tự chạy (không cần cổng chặn)

Máy này là Windows nên dùng **Task Scheduler**, không phải cron. `DEPLOYMENT.md`
§9 và §11 đã có sẵn dòng cron cho Ubuntu — **giữ nguyên chúng**, chỉ bổ sung
phần Windows song song.

1. Tạo scheduled task chạy `scripts/heartbeat_check.py` **5 phút/lần, 08:00–15:00,
   thứ 2–thứ 6**. Ghi log ra file.
2. Tạo scheduled task chạy `scripts/daily_data_check.py` lúc **15:30 thứ 2–thứ 6**.
3. Tạo scheduled task chạy `scripts/backfill_universe.py --timeframe 1d` lúc
   **20:30 thứ 2–thứ 6** để `bars_daily` tự tiến. (Xem `DEPLOYMENT.md:255` cho
   dạng tham số đã dùng trên Ubuntu.)

→ **Kiểm chứng — bắt buộc là bằng chứng ĐÃ CHẠY, không phải ĐÃ TẠO:**
`schtasks /query /fo LIST /v` in ra task **và** `Last Run Time` khác rỗng,
**và** file log có dòng mới sau ít nhất một chu kỳ. "Đã tạo task" không tính là
xong — đó đúng là kiểu nhầm lẫn đã dẫn tới sự cố mục 1.

→ Cập nhật `DEPLOYMENT.md`: thêm mục Windows Task Scheduler đặt cạnh mục cron
Ubuntu, để lần dựng VPS không phải nghĩ lại.

**Phạm vi được sửa:** `DEPLOYMENT.md`. **KHÔNG sửa** code trong `trading/` hay
`scripts/` — các script đã đúng.

---

## 5. Task C — Dữ liệu

1. **Trả lời bằng số: 31/08 có phải phiên giao dịch không?** Gọi SSI lấy daily
   OHLC cho 5–10 mã thanh khoản cao (VD VCB, HPG, FPT, SSI, MBB) khoảng
   28/08 → 01/09.
   - Mọi mã đều có bar 31/08 ⇒ ta đã bỏ lỡ một phiên thật ⇒ làm bước 2.
   - Mọi mã đều không có ⇒ 31/08 là ngày nghỉ ⇒ **không có gì để vá**, ghi kết
     luận rồi bỏ qua bước 2.
   → *Kiểm chứng:* bảng mã × ngày, dán nguyên văn.
   → **Cảnh báo tiền lệ:** hai lần trước đã kết luận nhầm rằng 07/08 và 28/08
     "thiếu vì job chưa chạy", trong khi thật ra SSI không hề có dữ liệu ngày đó.
     Đừng suy từ việc bảng trống ra việc job hỏng.

2. Nếu thiếu thật: nạp bằng
   `scripts/backfill_universe.py --timeframe 1d --from <ngày thiếu> --to <ngày thiếu>`.
   → *Kiểm chứng:* `max(ts)` của `bars_daily` sau khi nạp; **chạy lại lần hai
   phải không đổi số dòng** (UPSERT idempotent).

3. Sau 14:45 hôm nay: xác nhận phiên hôm nay đã thu được.
   → *Kiểm chứng:* `SELECT symbol, max(ts) FROM bars WHERE symbol IN
   ('HII','IJC','AAA') GROUP BY 1;` phải cho 14:45 giờ VN ngày 01/09.

**Ràng buộc dữ liệu:**
- Chỉ gọi API **dữ liệu**, read-only. Không đặt lệnh, không huỷ lệnh.
- **Không `TRUNCATE`, không `DROP`, không xoá dòng nào.** Chỉ nạp thêm.
- `bars_daily` là hypertable TimescaleDB (556 chunk). `pg_dump -t bars_daily
  --data-only` cho ra file **RỖNG 486 byte** — nếu cần sao lưu thì dùng
  `\copy (SELECT ...) TO STDOUT WITH CSV HEADER` và **kiểm số dòng** trước khi
  tin vào bản sao lưu đó.

---

## 6. Cấm — áp dụng cho cả ba task

- **Không commit, không push.** Claude audit rồi mới commit.
- **Không bật `real_trading_enabled`**, không sửa `config/config.yaml`.
- Không gọi API đặt/huỷ lệnh SSI.
- Không in giá trị secret ra báo cáo hay log.
- Không sửa `scripts/heartbeat_check.py` — nó đã đúng và đã có test.
- Nếu phát hiện vấn đề ngoài phạm vi: **báo cáo**, đừng tự sửa.

## 7. Báo cáo cuối

Với mỗi task: đã làm gì, output kiểm chứng **dán nguyên văn** (không tóm tắt
thành chữ "pass" hay "đã chạy"), việc nào không làm được và vì sao. Không đoán.

Riêng Task A: không có ảnh/nội dung tin nhắn Telegram thật thì task đó **chưa
xong**, dù mọi thứ khác đã chạy.
