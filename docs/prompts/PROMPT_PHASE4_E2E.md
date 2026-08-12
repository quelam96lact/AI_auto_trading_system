# Prompt thực thi: Phase 4 E2E Verification (ssi-sdk mới, live trading)

**Dùng prompt này khi có phiên giao dịch tiếp theo mở (09:00-14:45 VN).** Đọc trước `PLAN_PHASE4_E2E.md` và `PLAN_SSI_SDK_MIGRATION.md` nếu cần thêm bối cảnh — prompt này tự chứa đủ để chạy độc lập.

---

## Mục tiêu

Xác nhận collector chạy đúng với `ssi-sdk` mới (thay `ssi_fc_data`) trong 1 phiên giao dịch thật. Trả lời dứt điểm 3 câu hỏi còn mở của migration:

1. `access_token` (TTL 15 phút) có tự refresh liên tục suốt phiên (~6 giờ) mà **không cần OTP thủ công** không?
2. `IntervalMessage.interval_time` format thật có đúng `"YYYY/MM/DD HH:mm:ss"` như `parse_interval_message()` (trading/collector/parser.py) đang giả định không?
3. SSI tự đóng bar 5 phút qua `subscribe_symbol_ohlcv` có đúng ranh giới phiên VN không (mở 09:15, nghỉ trưa 11:30-13:00, đóng 14:45/ATC)?

---

## ⚠️ Nếu phát hiện cần sửa code (câu hỏi #2/#3 sai)

Đây là phiên chạy thật, có thể phát hiện bug cần fix ngay trong phiên (vd sai format `interval_time`). Nếu vậy:
- **Vẫn phải theo đúng quy trình của repo** (xem `CLAUDE.md`): chạy `gitnexus_impact` trước khi sửa `parse_interval_message`/symbol liên quan, sửa fix nhỏ gọn (không refactor thêm), viết/sửa test tương ứng, chạy `gitnexus_detect_changes()` sau khi xong.
- **Không tự commit/push** — dừng lại, báo cáo phát hiện + fix đề xuất, để được audit trước khi commit (giống toàn bộ Phase 0-3 trước đó).
- Nếu fix đơn giản (đổi 1 format string) và có thể verify ngay bằng dữ liệu thật đang chảy qua — có thể sửa + deploy lại collector ngay trong phiên để tiếp tục thu thập dữ liệu đúng, nhưng commit vẫn chờ audit.

---

## Bước 0 — Chuẩn bị (08:50-08:58 VN, sát giờ mở phiên)

**Lý do làm sát giờ:** `access_token` TTL chỉ 15 phút — làm quá sớm sẽ hết hạn trước khi collector kịp dùng lần đầu (dù `ensure_authenticated()` sẽ tự `refresh()` được, không sao nếu trễ vài phút, nhưng tốt nhất làm sát giờ để giảm biến số).

```powershell
# 1. Nạp .env vào session hiện tại
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2].Trim('"').Trim("'")
    }
}

# 2. Start Postgres (cần chạy trước để load_token_to_db.py ghi được)
docker compose up -d postgres
Start-Sleep -Seconds 8

# 3. Xin OTP + xác thực (SSI gửi qua SMS/email — người vận hành tự nhập OTP khi được hỏi)
uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py

# 4. Nạp token vừa xác thực vào bảng ssi_auth_state
uv run python scripts/load_token_to_db.py --config config/config.yaml
```

Xác nhận bước 4 in ra `"Đã nạp token vào ssi_auth_state"` + `refresh_token_expires_at` (kỳ vọng ~8 giờ sau thời điểm hiện tại). Nếu lỗi ở bước 3 (400/401 từ SSI) — dừng lại, không phải lỗi code, kiểm tra `SSI_API_KEY`/`SSI_API_SECRET` trong `.env` còn hợp lệ không (có thể đã bị revoke/đổi từ Phase 0).

---

## Phase A — Setup (09:00-09:05)

**Lưu ý quan trọng:** `down -v` xoá Postgres volume (kể cả `ssi_auth_state` vừa nạp) — nhưng KHÔNG xoá `scripts/.ssi_sdk_token.json` trên máy. Vì vậy nạp lại DB bằng đúng token đã có, **không cần xin OTP lần 2**.

```powershell
docker compose down -v
docker compose up -d postgres nats
Start-Sleep -Seconds 10
uv run python scripts/load_token_to_db.py --config config/config.yaml
docker compose build collector   # đảm bảo image có code Phase 3 mới nhất, không dùng cache cũ
docker compose up -d collector
docker compose logs -f collector
```

---

## Phase B — Warm-up (09:00-09:30)

Theo dõi log, kỳ vọng theo thứ tự:
1. `{"level": "INFO", "msg": "backfill start"}` → `"backfill done"` (REST OHLC qua `ssi-sdk`, đã verify Phase 2)
2. `INFO [ssi_sdk.transport.websocket]: WebSocket connected to wss://stream.ssi.com.vn/ws/v3`
3. `DATA RAW: {'method': 'subscribe', 'channel': 'DATA', 'status': 'ok', ...}` (subscribe ACK)
4. **Bar đầu tiên** — log `"bars closed"` với `n=...`, `symbols=[...]` (đây là bằng chứng câu hỏi #2 + #3 đúng)

**Nếu (4) không xuất hiện trong 10 phút sau 09:15 (bar 5m đầu tiên đóng lúc 09:20 sớm nhất):**
```powershell
docker compose logs collector | Select-String -Pattern "error|Error"
```
Khả năng cao nhất: `parse_interval_message()` trả `None` liên tục do format `interval_time` sai (câu hỏi #2). Không crash, chỉ im lặng bỏ qua — phải soi kỹ log DEBUG hoặc thêm log tạm thời để bắt được raw `IntervalMessage` thật, xác nhận field đúng, sửa `parser.py` theo đúng format thật tìm được (xem mục "Nếu phát hiện cần sửa code" ở trên).

---

## Phase C — Theo dõi trong phiên (09:30-14:45)

**Mỗi 5 phút:**
```powershell
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, ts, close, volume FROM bars ORDER BY ts DESC LIMIT 5;"
```

**Mỗi 30 phút — checklist:**
```powershell
# Bar count per symbol trong 30 phút qua (kỳ vọng ~6/symbol)
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, COUNT(*) FROM bars WHERE ts > NOW() - INTERVAL '30 minutes' GROUP BY symbol;"

# Duplicate check (kỳ vọng rỗng)
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, ts, COUNT(*) FROM bars GROUP BY symbol, ts HAVING COUNT(*) > 1;"

# Reconnect count (kỳ vọng thấp/0)
docker compose logs collector | Select-String -Pattern "SSIFeed connection error"

# Token refresh — câu hỏi #1 (kỳ vọng thấy log định kỳ, KHÔNG có lỗi 401/auth giữa phiên)
docker compose logs collector | Select-String -Pattern "Authentication successful|Token refreshed|refresh_token missing"
```

Nếu thấy `"refresh_token missing/expired"` trong log → **câu hỏi #1 thất bại nghiêm trọng** — collector sẽ crash backfill/feed cho tới khi có OTP mới. Đây không phải fix nhỏ, dừng lại báo cáo ngay, không tự ý thiết kế lại auth flow giữa phiên.

**~14:30 (optional — gap recovery test):**
```powershell
docker compose stop collector
Start-Sleep -Seconds 180
docker compose start collector
docker compose logs collector | Select-String -Pattern "backfill done"
```
Xác nhận bar bị miss trong lúc dừng được backfill lại (Phase 2), không trùng lặp (check lại duplicate query ở trên).

---

## Phase D — Tổng kết (sau 14:45)

```powershell
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT symbol, COUNT(*) as total, MIN(ts) as first, MAX(ts) as last FROM bars WHERE DATE(ts) = CURRENT_DATE GROUP BY symbol;"
docker compose logs collector | Select-String -Pattern "error|Error" | Measure-Object | Select-Object -ExpandProperty Count
docker compose logs collector | Select-String -Pattern "Token refreshed" | Measure-Object | Select-Object -ExpandProperty Count
```

---

## Success criteria

| Tiêu chí | Ngưỡng |
|---|---|
| Bar collected | ≥ 40/symbol (3 symbol: VCB, HPG, TCB) |
| Parser error trả `None` do format sai | 0 (nếu >0, đã tìm và sửa được nguyên nhân trong phiên) |
| Duplicate bar `(symbol, ts)` | 0 |
| Access token refresh giữa phiên | Tự động, 0 lần cần OTP thủ công |
| Bar đầu/cuối trong ngày | ≈ 09:15 / 14:45, có gap đúng giờ nghỉ trưa |
| Gap recovery (nếu test) | Backfill lấp đúng, không trùng |

---

## Báo cáo cuối (bắt buộc, kể cả pass hay fail)

1. Trả lời rõ 3 câu hỏi ở đầu prompt — dựa trên bằng chứng cụ thể (log/query output), không suy đoán.
2. Tổng bar/symbol, tổng lỗi, tổng lần refresh token.
3. Nếu có sửa code trong phiên: diff, lý do, kết quả `gitnexus_detect_changes()` — **để Claude (planner) audit trước khi commit**, không tự commit.
4. Nếu PASS toàn bộ 3 câu hỏi ≥2 phiên liên tiếp (phiên này + 1 phiên sau, không nhất thiết liên tiếp ngày) → đề xuất Phase 5 (gỡ `ssi-fc-data`, xoá `*Legacy` classes).
