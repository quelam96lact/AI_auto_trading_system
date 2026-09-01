# Plan 2026-09-01 (đợt 2) — Giám sát phải tự chạy, dữ liệu phải tự tiến

Viết sau khi đo trạng thái hệ thống lúc 07:11 ngày 01/09/2026.

---

## 0. Phát hiện chính: hệ thống mất trọn một phiên và không có gì báo

| Đo | Kết quả | Nguồn |
|---|---|---|
| Container khởi động lại | `2026-08-31T18:08 UTC` = **01/09 01:08 giờ VN** | `docker inspect .State.StartedAt` |
| Log collector trong khung phiên thứ Hai 31/08 (02:00–07:45 UTC) | **0 dòng** | `docker logs --since/--until` |
| `bars_daily` mới nhất | **2026-08-28**, 1.554 mã | truy vấn DB |
| `bars` 5m mới nhất (HII/IJC/AAA) | **2026-08-28 14:45 giờ VN** | truy vấn DB |
| Cron / Scheduled Task trên máy này | **không có cái nào** | `crontab -l`, `schtasks /query` |
| Heartbeat hiện tại | collector + engine đều tươi (01/09 07:12) | bảng `heartbeat` |

Ghép lại: hệ thống **không chạy suốt phiên thứ Hai 31/08**, mất trọn một phiên
dữ liệu, và **không một cảnh báo nào phát ra** — vì `scripts/heartbeat_check.py`
chưa từng được cài vào lịch chạy ở đâu cả.

Đây không phải lỗi code. Toàn bộ chuông 2A/2B/2C/2D đã viết và đã có test đều
đúng; chúng chỉ chưa bao giờ được gọi. Công sức nhiều tháng xây lưới an toàn
hiện đang bằng 0 về mặt vận hành.

### Hệ quả dây chuyền đã đo được

`bars_daily` **chỉ tiến khi có người chạy backfill bằng tay**. Collector chỉ ghi
`bars` 5m (`backfill.py:349,360` chạy lúc khởi động, lần gần nhất trả
`{HII: 0, IJC: 0, AAA: 0}`). Trong khi đó:

- `daily_breakout` — chiến lược duy nhất còn trong registry — chạy trên khung 1d,
  tức đọc `bars_daily`.
- NAV (`account_sync.py:120-149`) định giá danh mục từ `bars_daily`/`bars`, và có
  fail-safe: **giá cũ hơn 5 phiên ⇒ tính 0 + WARN**.

Nên nếu không ai nạp dữ liệu, trong khoảng một tuần NAV sẽ tự xẹp dần về đúng
phần tiền mặt — kèm cảnh báo, không im lặng, nhưng vẫn sai. Và NAV vừa trở thành
**số nhân kích thước lệnh thật** (commit `6159d39`).

Đã thấy tận mắt trong log: `{"msg": "NAV tinh thieu: mot so ma khong dinh gia
duoc (tinh 0)", "symbols": "CAP", "nav": 148348000.0}` — có lúc còn thiếu tới 5/7
mã (`CAP,HCM,MIRHCM261,SSI,TCX`, NAV rớt xuống 91.978.997).

### Mâu thuẫn còn treo, không phải việc của plan này nhưng phải nói ra

`engine/main.py:71` chạy `SmaCrossStrategy()` — đúng chiến lược mà chủ dự án đã
**gỡ khỏi registry backtest ngày 15/08** vì lỗ trên cả 4 cấu hình *trước khi*
tính phí. Engine live đang chạy thứ chính dự án tuyên bố là không có lợi thế.

---

## 1. Giả định

1. `real_trading_enabled` giữ `false` cho tới khi task 3 có kết luận.
2. Máy Windows này là môi trường chạy hiện tại; VPS Ubuntu chưa tồn tại. Plan
   dùng Task Scheduler của Windows, và ghi rõ dòng cron tương đương cho VPS.
3. Hôm nay 01/09 là phiên giao dịch; **02/09 là nghỉ lễ Quốc khánh**
   (`config.yaml: holidays: ['2026-09-02']`). Phiên kế tiếp sau hôm nay là 03/09.
4. Chưa xác minh 31/08 là ngày nghỉ hay ngày giao dịch mà ta bỏ lỡ — **Task 2
   bước 1 phải trả lời câu này bằng dữ liệu SSI, không đoán.**

---

## 2. Task 1 — Làm cho giám sát tự chạy, rồi CHỨNG MINH nó kêu

Đây là việc quan trọng nhất trong plan. Không viết thêm chuông nào.

### Bước

1. **Cài lịch chạy `heartbeat_check.py`** mỗi 15 phút trong giờ giao dịch
   (09:00–15:00 giờ VN, thứ 2–6).
   → *Kiểm chứng:* `schtasks /query /fo LIST | findstr trading` in ra task; và
   sau một chu kỳ, có log chứng minh nó đã chạy thật (không phải chỉ "đã tạo").

2. **Cài lịch chạy backfill hằng ngày** sau giờ đóng cửa (15:30 giờ VN) để
   `bars_daily` tự tiến.
   → *Kiểm chứng:* chạy tay một lần trước, đối chiếu `max(ts)` của `bars_daily`
   tăng đúng 1 phiên; rồi để lịch chạy và kiểm lại hôm sau.

3. **DIỄN TẬP dead-man's switch — bước không được bỏ.** Giữa phiên, dừng
   `collector` bằng `docker compose stop collector`, chờ quá ngưỡng, xác nhận
   **Telegram thật** tới máy. Rồi khởi động lại và xác nhận cảnh báo dừng.
   → *Kiểm chứng:* dán nội dung tin nhắn Telegram + mốc giờ dừng và mốc giờ nhận.
   Không có tin nhắn ⇒ task này CHƯA xong, bất kể cron đã cài.
   → *Cửa sổ thời gian:* hôm nay 01/09 (mở cửa 09:00), hoặc 03/09. **02/09 nghỉ lễ.**

4. Ghi lại vào `DEPLOYMENT.md`: dòng lịch Windows đã dùng **và** dòng cron Ubuntu
   tương đương, để lần dựng VPS không phải nghĩ lại.

**Phạm vi:** `DEPLOYMENT.md`, và cấu hình lịch trên máy (không phải file trong repo).
**KHÔNG đụng:** code trong `trading/`, `scripts/heartbeat_check.py` (nó đã đúng).

---

## 3. Task 2 — Vá lỗ hổng 31/08 và xác nhận hôm nay thu được

1. **Trả lời bằng dữ liệu: 31/08 có phải phiên giao dịch không?** Gọi SSI lấy
   daily OHLC cho 5–10 mã thanh khoản cao trong khoảng 28/08–01/09. Có dữ liệu
   ⇒ ta đã bỏ lỡ một phiên thật; không có dữ liệu ở mọi mã ⇒ đó là ngày nghỉ và
   không có gì để vá.
   → *Kiểm chứng:* bảng mã × ngày, dán nguyên văn.
   → *Lưu ý:* trước đây đã có tiền lệ — 07/08 và 28/08 từng bị đọc nhầm là "thiếu
   do chưa chạy job", hoá ra SSI không hề có dữ liệu. Đừng lặp lại lỗi đó.

2. Nếu có dữ liệu: nạp phiên thiếu bằng `scripts/backfill_universe.py`, phạm vi
   hẹp đúng khoảng ngày thiếu.
   → *Kiểm chứng:* `max(ts)` của `bars_daily` sau khi nạp; chạy lại lần hai phải
   **không đổi số dòng** (UPSERT idempotent).

3. Xác nhận phiên hôm nay được thu: sau 14:45, `bars` phải có bar 5m của
   HII/IJC/AAA tới 14:45.
   → *Kiểm chứng:* truy vấn `max(ts)` theo mã.

**Ràng buộc:** chỉ gọi API dữ liệu (read-only). Không đặt/huỷ lệnh. Không
`TRUNCATE`, không xoá bảng — lần nạp lại toàn bộ hôm 30/08 đã có bài học:
`pg_dump -t bars_daily --data-only` trên hypertable cho ra file RỖNG 486 byte.

---

## 4. Task 3 — Chặn go-live thật: engine đang chạy chiến lược không có lợi thế

Không phải task code. Là một phép đo và một quyết định.

1. Đo `daily_breakout` và `octopus_pullback` **so với mua-và-giữ trên đúng cùng
   mã, cùng kỳ, cùng phí** (`scripts/measure_strategy.py`, và panel Grafana
   `backtest-explorer` từ commit `b0f91d7` đã vẽ đường mua-và-giữ THẬT — không
   phải đường nội suy thẳng).
   → *Kiểm chứng:* bảng: chiến lược | số mã | kỳ | lợi nhuận | mua-và-giữ cùng kỳ
   | max drawdown. "Có lãi" một mình nó vô nghĩa — cổ phiếu VN đã tăng suốt
   2016–2026.

2. Ba kết cục có thể, chọn một, không để lửng:
   - Có chiến lược thắng mua-và-giữ ⇒ đổi `engine/main.py:71` sang nó (task riêng).
   - Không có ⇒ ghi nhận rõ ràng: **engine chỉ chạy paper để hoàn thiện hạ tầng,
     không bật tiền thật.** Đây là kết cục hợp lệ, không phải thất bại.
   - Chưa đủ dữ liệu để kết luận ⇒ nói rõ thiếu gì.

---

## 5. Task 4 — Hoãn: đổi `real_order_account`

Chưa làm cho tới khi task 1–3 xong. Lý do đã có số: đổi sang `0434226` vừa nhân
NAV lên 40× vừa — sau commit `6159d39` — nhân kích thước lệnh lên **56×**
(100 cp → 5.600 cp AAA, tức 703.000 → 39,4 triệu VND/lệnh). Bật thứ đó lên khi
giám sát chưa từng chứng minh là kêu được thì không phải dũng cảm, là mù.

GUARD-3 (commit `6159d39`) đã dựng sẵn: lúc đổi, engine sẽ nói ra nó vừa được
trao quyền bán những cổ phiếu thật nào.

---

## 6. Ràng buộc chung

- Không commit, không push — Claude audit rồi commit.
- Không bật `real_trading_enabled`. Không gọi API đặt/huỷ lệnh SSI.
- Không sửa `config/config.yaml`.
- Việc nào không làm được thì nói rõ vì sao. Không đoán, không tóm tắt bằng chứng
  thành chữ "pass".
