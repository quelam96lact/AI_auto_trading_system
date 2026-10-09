# Brief đợt 168 — Watchdog feed không báo nhầm trong ATO/ATC

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vấn đề (Claude đã đo, không phải phỏng đoán)

`logs/bars_closed.log`, đếm theo giờ UTC, từ 02/10 tới 09/10:

| Giờ VN | Tin | Số ngày |
|---|---|---|
| 09:00, 09:03, 09:06, 09:09, 09:12 | WARN `feed stale, forcing reconnect` | 10–11 |
| 09:06 | CRITICAL `feed stale beyond max failures` | mọi ngày giao dịch |
| 14:33, 14:36, 14:39, 14:42 | WARN `feed stale, forcing reconnect` | 12 |
| 14:39 | CRITICAL `feed stale beyond max failures` | mọi ngày giao dịch |
| 13:00 | không có | — |

Tức khoảng **11 tin Telegram báo nhầm mỗi ngày giao dịch** (WARN và CRITICAL đều gửi Telegram, `trading/alerts.py:_NOTIFY_LEVELS`). Chủ dự án nhận CRITICAL hai lần mỗi ngày vào đúng giờ thị trường mở và đóng, nên CRITICAL thật cũng sẽ bị lờ đi.

**Nguyên nhân:** `trading/collector/main.py` (khoảng dòng 448–456) dựng `Watchdog` với `is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays)`. `is_trading_time` dùng `SESSIONS` = 09:00–11:30 và 13:00–14:45, tức **gồm cả ATO 09:00–09:15 và ATC 14:30–14:45**. Trong hai khung đó cổ phiếu không khớp liên tục nên không có tick là bình thường. `trading/calendar_vn.py` đã có `is_continuous_matching` (`CONTINUOUS_SESSIONS` = 09:15–11:30, 13:00–14:30) cho đúng mục đích này.

**Bẫy thứ hai khi chỉ đổi hàm:** `Watchdog.check()` (`trading/collector/watchdog.py`) ngoài giờ thì `return` sớm mà **không** cập nhật `_last_beat`. Nên ở nhịp kiểm đầu tiên sau khi vào khung (09:15, 13:00), `now - _last_beat` là khoảng cách từ tick cuối của khung trước. Nếu nhịp kiểm đến trước tick đầu tiên, watchdog báo stale ngay. Hôm nay 13:00 không báo nhầm, có lẽ vì tick tới trước nhịp kiểm, nhưng đó là may chứ không phải thiết kế.

## 1. Việc làm
1. **Test trước** (§3), thấy đỏ trên code hiện tại.
2. `trading/collector/main.py`: `is_trading_fn` dùng `is_continuous_matching(ts, cfg.holidays)` thay cho `is_trading_time`. Chỉ đổi đúng chỗ dựng `Watchdog`. Các chỗ khác trong `main.py` đang dùng `is_trading_time` (ví dụ phát hiện máy ngủ, khoảng dòng 263–270) **giữ nguyên**.
3. `trading/collector/watchdog.py`: khi `check()` chạy ngoài khung, đặt `_last_beat = now` (và `_failures = 0`) trước khi `return`. Nhờ vậy khi vào khung, watchdog cần đủ `stale_seconds` không có tick mới báo.
   → **kiểm chứng bằng:** test §3 xanh, test cũ của `tests/test_watchdog.py` xanh mà không sửa kỳ vọng.

## 2. Phạm vi
- **Được sửa:** `trading/collector/watchdog.py`, đúng một biểu thức `is_trading_fn` trong `trading/collector/main.py`, `tests/test_watchdog.py`, và test của `collector/main` nếu cần test nối dây (dùng file test hiện có).
- **Không sửa:** `trading/calendar_vn.py`, `config/config.yaml` (giữ `stale_seconds: 180`, `max_failures: 3`), mức cảnh báo, nội dung tin, mọi file khác.
- **Không** build hay khởi động lại container; Claude triển khai ngoài giờ phiên.
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `impact` cho `Watchdog.check` và hàm trong `main.py` chứa chỗ dựng `Watchdog`, dán mức rủi ro. Chạy `detect_changes` sau khi xong.

## 3. Kiểm chứng (đồng hồ giả, không ngủ thật)
Dùng `now_fn` giả với `stale_seconds=180`, `max_failures=3`, và `is_continuous_matching` thật với một ngày giao dịch (ví dụ thứ Năm 08/10/2026).

1. **ATO im lặng:** tick cuối lúc 14:30 hôm trước. `check()` mỗi 30 giây từ 09:00 tới 09:14:30, không có `beat()` → `on_stale` và `on_critical` **không** được gọi.
2. **Vào phiên liên tục không báo ngay:** tiếp test 1, `check()` lúc 09:15:00 và 09:17:30 không có `beat()` → không báo. Lúc 09:18:30 (quá 180 giây kể từ 09:15) → `on_stale` một lần.
3. **Chết thật trong phiên vẫn bắt được:** `beat()` lúc 10:00, rồi `check()` mỗi 30 giây không có tick → `on_stale` ở lần đầu quá 180 giây, `on_critical` sau đúng 3 lần stale (giữ hành vi `test_stale_then_critical_after_max_failures`).
4. **ATC im lặng:** `beat()` lúc 14:29:50, `check()` từ 14:30 tới 14:45 → không báo.
5. **Nghỉ trưa:** `beat()` lúc 11:29:50, `check()` từ 11:30 tới 12:59:30 → không báo; 13:00:00 và 13:02:30 không báo; 13:03:30 không có tick → `on_stale` một lần.
6. **Nối dây:** một test khẳng định `Watchdog` trong `collector/main` nhận hàm cho kết quả **False** lúc 09:05 và 14:35 của ngày giao dịch, **True** lúc 10:00. Cách kiểm do agent chọn (giả lập `Watchdog` để bắt tham số, hoặc tách lambda ra hàm có tên), miễn test đỏ khi `main.py` dùng lại `is_trading_time`.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Đổi lại `is_trading_time` trong `main.py` → test 6 đỏ.
- Bỏ dòng đặt lại `_last_beat` ngoài khung → test 2 hoặc 5 đỏ.
- Đổi `>` thành `>=` trong phép so `stale` → báo tên test đỏ, hoặc nói rõ nếu không test nào đỏ (khi đó đó là điểm mù, ghi lại, không cần sửa).

```
uv run pytest tests/test_watchdog.py -v
docker compose --profile test up -d nats-test
uv run pytest -q
uv run ruff check trading tests scripts
```

**Hoàn thành khi:**
- 6 test mới/sửa xanh, test cũ của watchdog xanh không đổi kỳ vọng, các bước phá hoại cho kết quả như nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 09/10: `1926 passed`; dán số trước và sau.
- ruff sạch.
- `detect_changes` chỉ gồm các file ở §2, cộng dòng thống kê GitNexus nếu `analyze` tự sửa `AGENTS.md`/`CLAUDE.md`.

## 4. Báo cáo cho Claude
1. Kết quả `impact` kèm mức rủi ro.
2. Output pytest/ruff, bảng phá hoại.
3. Output `detect_changes`.
4. Mọi chỗ phải tự diễn giải; không im lặng chọn.

## 5. Việc Claude làm sau khi duyệt
Triển khai cùng đợt 167 (build lại `collector` ngoài giờ phiên). Phiên kế tiếp, đếm trong log: số WARN `forcing reconnect` và CRITICAL `beyond max failures` trong 09:00–09:20 và 14:25–14:50 phải bằng 0.
