# Phase 4 — E2E Verification (SSI SDK mới, live trading)

**Mục đích:** Xác nhận collector chạy đúng với `ssi-sdk` mới trong 1 phiên giao dịch thật — điểm mở duy nhất còn lại của toàn bộ migration (`PLAN_SSI_SDK_MIGRATION.md`).

**Tái dùng runbook cũ** (`EXECUTE_TASK_3_TODAY.md`/`PLAN_TASK_3.md`), điều chỉnh cho khác biệt của SDK mới — xem mục "Khác gì so với Task 3 cũ" bên dưới.

---

## 3 câu hỏi Phase 4 phải trả lời (khác Task 3 cũ)

| # | Câu hỏi | Vì sao quan trọng |
|---|---|---|
| 1 | `access_token` (TTL 15 phút, đo ở Phase 0) có **tự refresh nhiều lần liên tục** trong phiên ~6 giờ mà không cần OTP thủ công không? | Task 3 cũ dùng SDK cũ không có khái niệm refresh_token — đây là rủi ro mới hoàn toàn của SDK mới, chưa test qua 1 phiên dài |
| 2 | `IntervalMessage.interval_time` format thật là gì — có đúng `"YYYY/MM/DD HH:mm:ss"` như `parse_interval_message()` đang giả định không? | `parser.py` docstring đã đánh dấu rõ đây là suy đoán chưa xác nhận (Phase 3) |
| 3 | Bar do SSI tự đóng qua `subscribe_symbol_ohlcv` có đúng ranh giới giờ VN không (mở 09:15, nghỉ trưa 11:30-13:00, đóng 14:45/ATC)? | Quyết định đã bỏ `BarAggregator` (Phase 3) dựa trên giả định này — nếu sai, phải khôi phục lại logic tự bucket |

**Nếu câu 2 hoặc 3 sai** → sửa `parse_interval_message()` theo dữ liệu thật (task nhỏ, không phải rollback toàn bộ). **Nếu câu 1 sai** (refresh không tự động, phải OTP giữa phiên) → vấn đề nghiêm trọng hơn, cần dừng và bàn lại kiến trúc auth.

---

## Khác gì so với Task 3 cũ (đọc trước khi làm theo runbook cũ)

1. **`.env` cần thêm `SSI_API_KEY`/`SSI_API_SECRET`** (đã có từ Phase 0, không phải làm lại) — `SSI_CONSUMER_ID`/`SSI_CONSUMER_SECRET` cũ **không còn được dùng** bởi collector (code mới hoàn toàn dùng `ssi-sdk`), nhưng để nguyên trong `.env` cũng không sao (không ai đọc nữa).
2. **`ssi_auth_state` phải có sẵn refresh_token còn hạn TRƯỚC khi start collector** — nếu bảng rỗng hoặc refresh_token đã hết hạn (TTL 8 giờ, đo ở Phase 0), collector sẽ crash ngay ở lần đầu gọi `ensure_authenticated()` (raise `RuntimeError` rõ ràng, xem `trading/collector/ssi_auth.py`). **Chạy bước 0 dưới đây trước** để nạp token mới nếu cần.
3. **Không còn `BarAggregator`/gap-recovery kiểu cũ trong luồng streaming** — bar tới thẳng từ `IntervalMessage`, không phải tự gom tick. Mục "gap recovery test" của Task 3 cũ (stop/restart collector giữa phiên) vẫn áp dụng được, nhưng cơ chế khác: backfill (Phase 2, đã xong) lấp gap qua REST, không phải qua buffer tick.
4. **Index (VNINDEX/VN30) sẽ KHÔNG có dữ liệu** trong lần chạy này — đã cố tình hoãn ở Phase 3 (TODO trong code), không phải bug mới.

---

## Bước 0 — Nạp lại `refresh_token` nếu cần (trước 08:55 VN)

`docker compose down -v` (bước 1 dưới) sẽ **xoá sạch DB**, bao gồm cả bảng `ssi_auth_state` đã lưu từ Phase 0 → **bắt buộc phải chạy lại bootstrap OTP** trước khi start collector, không thể tái dùng token cũ.

```powershell
# Nạp .env vào session (nếu terminal mới, chưa có biến môi trường)
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2].Trim('"').Trim("'")
    }
}

# Xin OTP + xác thực (SSI gửi qua SMS/email)
uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py
```

Script lưu token vào `scripts/.ssi_sdk_token.json` — **nhưng đây không phải nơi collector đọc**. Collector đọc từ bảng `ssi_auth_state` trong Postgres (`trading/storage/db.py::load_ssi_token`/`save_ssi_token`), do `ensure_authenticated()` tự quản lý.

**✅ Cầu nối đã viết xong:** `scripts/load_token_to_db.py` — đọc `scripts/.ssi_sdk_token.json`, ghi vào `ssi_auth_state` qua `Storage.save_ssi_token()`. Chạy sau bước xin OTP ở trên:
```powershell
uv run python scripts/load_token_to_db.py --config config/config.yaml
```
(Cần Postgres đang chạy — `docker compose up -d postgres` trước.)

---

## Chuẩn bị trước 08:55 VN

- [ ] `.env` có `SSI_API_KEY`/`SSI_API_SECRET` (đã có từ Phase 0)
- [ ] Chạy Bước 0 (xin OTP, lưu token) — **làm được tối hôm trước hoặc sáng sớm, không cần đúng lúc thị trường mở** (chỉ cần access_token còn hạn lúc 09:00 — TTL 15 phút nên **phải chạy Bước 0 sát giờ**, tốt nhất 08:55-08:58, không làm từ tối hôm trước vì access_token sẽ hết hạn, dù `ensure_authenticated()` sẽ tự `refresh()` bằng refresh_token 8 giờ nên thực ra chạy trước vài giờ vẫn ổn, chỉ access_token ban đầu hết hạn không sao)
- [ ] `docker compose build collector` (đảm bảo image có `ssi-sdk` mới nhất, không dùng cache cũ)

---

## 09:00-14:45 VN — Runbook (dựa trên `EXECUTE_TASK_3_TODAY.md`, điều chỉnh)

### Phase A: Setup (09:00-09:05)

**Lưu ý:** `down -v` xoá sạch volume Postgres (kể cả `ssi_auth_state` vừa nạp ở Bước 0) — nhưng **không xoá** `scripts/.ssi_sdk_token.json` trên máy (file cục bộ, ngoài Docker). Vì vậy **không cần xin OTP lại**, chỉ cần nạp lại cùng token đó vào DB mới.

```powershell
docker compose down -v
docker compose up -d postgres nats
# đợi postgres healthy (~10s)
uv run python scripts/load_token_to_db.py --config config/config.yaml
docker compose up -d collector
docker compose logs -f collector
```

### Phase B: Warm-up (09:00-09:30)
Theo dõi log, kỳ vọng thấy theo thứ tự:
1. `backfill start` → `backfill done` (Phase 2, REST OHLC qua `ssi-sdk`)
2. Kết nối WebSocket: log tương tự `"WebSocket connected to wss://stream.ssi.com.vn/ws/v3"` (đã thấy ở Phase 0 test ngoài giờ)
3. **Bar đầu tiên** — log `"bars closed"` với `n=...`, `symbols=[...]`

**Nếu (3) không xuất hiện trong 10 phút sau 09:15:** kiểm tra `docker compose logs collector | grep -i error` — khả năng cao là câu hỏi #2/#3 ở trên sai (format `interval_time` sai → `parse_interval_message()` trả `None` liên tục, không crash nhưng cũng không có bar nào được lưu). Đây là kịch bản **có khả năng xảy ra nhất** — chuẩn bị tinh thần debug live.

### Phase C: Theo dõi trong phiên (09:30-14:45)

**Mỗi 5 phút** (khớp ranh giới bar 5m: 09:35, 09:40...):
```powershell
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, ts, close, volume FROM bars ORDER BY ts DESC LIMIT 5;"
```

**Mỗi 30 phút — checklist đầy đủ:**
- [ ] Bar count mỗi symbol tăng đều (≈ 6 bar/30 phút × 3 symbol)
- [ ] Không trùng `(symbol, ts)`: `SELECT symbol, ts, COUNT(*) FROM bars GROUP BY symbol, ts HAVING COUNT(*) > 1;` (kỳ vọng rỗng)
- [ ] `docker compose logs collector | grep -i "SSIFeed connection error"` — đếm số lần reconnect (kỳ vọng 0 hoặc rất ít, có backoff nếu có)
- [ ] **Mới — riêng Phase 4:** `docker compose logs collector | grep -i "Authentication successful\|Token refreshed"` — đếm số lần refresh access_token (kỳ vọng ≥1 lần mỗi ~15 phút nếu SDK tự log; nếu không thấy log này nghĩa là cần thêm log — ghi chú lại, không phải lỗi nghiêm trọng)

**~14:30 (optional, gap recovery):**
```powershell
docker compose stop collector
# đợi 3-5 phút
docker compose start collector
docker compose logs collector | grep -i "backfill done"
```
Xác nhận: bar bị miss trong lúc dừng được backfill lại qua REST (Phase 2), không trùng lặp.

### Phase D: Tổng kết (sau 14:45)

```powershell
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, COUNT(*) as total, MIN(ts) as first, MAX(ts) as last FROM bars WHERE DATE(ts) = CURRENT_DATE GROUP BY symbol;"
docker compose logs collector | Select-String -Pattern "error|Error" | Measure-Object | Select-Object -ExpandProperty Count
```

**Trả lời 3 câu hỏi ở đầu file**, dựa trên log thu thập được:
1. Refresh tự động thành công mấy lần? Có lần nào phải can thiệp OTP giữa phiên không?
2. `trading_date`/`interval_time` thật lấy được từ log/DB — có khớp `"YYYY/MM/DD HH:mm:ss"` không?
3. Bar đầu tiên/cuối cùng mỗi ngày có đúng 09:15/14:45 không? Có gap ở giờ nghỉ trưa 11:30-13:00 không (kỳ vọng có, đúng)?

---

## Success criteria

| Tiêu chí | Ngưỡng |
|---|---|
| Bar collected | ≥ 40/symbol (tương đương Task 3 cũ) |
| Parser error | Đếm được cụ thể (khác Task 3 cũ — kỳ vọng 0, nhưng nếu câu hỏi #2 sai thì sẽ có, chấp nhận được nếu tìm ra nguyên nhân + sửa được) |
| Duplicate bar | 0 |
| Access token refresh | Tự động, 0 lần cần OTP thủ công giữa phiên |
| Gap recovery (nếu test) | Backfill lấp đúng, không trùng |

**Nếu tất cả pass → Migration SSI SDK hoàn tất, gỡ `ssi-fc-data`/`*Legacy` classes ở Phase 5.**
**Nếu câu hỏi #2/#3 sai nhưng sửa được nhanh (đổi format string trong `parse_interval_message`) → sửa, chạy lại phần còn của phiên, không phải huỷ toàn bộ.**

---

## Trạng thái chuẩn bị

✅ **Toàn bộ runbook đã sẵn sàng** — không còn mảnh nào thiếu. `scripts/load_token_to_db.py` đã viết + smoke test (syntax + import hợp lệ), không cần credentials thật để viết, chỉ cần khi bạn chạy thật.

**Thứ tự chạy Bước 0 (làm sát giờ, không làm từ tối hôm trước — xem lý do ở mục "Chuẩn bị trước 08:55"):**
```powershell
docker compose up -d postgres
uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py
uv run python scripts/load_token_to_db.py --config config/config.yaml
```
Sau đó mới sang Phase A (`docker compose down -v` sẽ xoá lại DB — chạy Bước 0 SAU khi `down -v`, không phải trước, xem thứ tự đúng trong Phase A).
