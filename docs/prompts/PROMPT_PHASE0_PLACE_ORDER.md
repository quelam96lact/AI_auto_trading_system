# Prompt thực thi: Phase 0 — Đặt lệnh thật (đặt + huỷ 1 lệnh test)

**Dùng prompt này để tự chạy, hoặc đưa cho 1 phiên Claude Code khác chạy hộ.**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` — prompt này chỉ chạy **Phase 0** (xác nhận cơ chế đặt/huỷ lệnh hoạt động đúng), **KHÔNG phải** viết code production (Phase 1-4 còn chờ kết quả Phase 0 này).

---

## ⚠️ Trước khi chạy — hiểu rõ điều gì sẽ xảy ra

Script `scripts/spike_ssi_sdk_place_order.py` **có khả năng đặt 1 lệnh THẬT** lên sàn (tài khoản Cash `0434221`), sau đó huỷ ngay lập tức. Đây không phải dry-run.

**2 kết quả có thể xảy ra (cả 2 đều BÌNH THƯỜNG, không phải lỗi):**

| Kết quả | Ý nghĩa | Cần làm gì tiếp |
|---|---|---|
| Dừng ở Bước 1 với thông báo "sức mua < 1 lô" | Tài khoản không đủ ~5.3 triệu+ đồng để mua 1 lô VCB (số dư thật hiện ~21,459đ) — **kịch bản nhiều khả năng nhất** | Báo lại kết quả này cho Claude — vẫn xác nhận được cơ chế kiểm tra an toàn hoạt động đúng, dù chưa test được bước đặt+huỷ lệnh thật |
| Chạy hết 4 bước, đặt lệnh + huỷ thành công | Cần đã nạp đủ tiền hoặc test với mã rẻ hơn | Báo lại toàn bộ output (đặc biệt `status` trong `PlaceOrderResponse`/`CancelOrderResponse`) |

**Nếu muốn test trọn vẹn cả bước đặt+huỷ ngay hôm nay** (không bắt buộc): nạp thêm tiền vào tài khoản Cash `0434221` (đủ mua 1 lô mã rẻ, ví dụ mã dưới 5,000đ/cổ phiếu → cần ~500,000đ cho 100 cổ phiếu), rồi chạy với `--symbol <mã rẻ>`.

---

## Bước 1 — Chuẩn bị môi trường (PowerShell)

```powershell
# Nạp .env vào session hiện tại
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2].Trim('"').Trim("'")
    }
}
```

Xác nhận có đủ 3 biến (không in giá trị, chỉ kiểm tra tồn tại):
```powershell
foreach ($v in @("SSI_API_KEY","SSI_API_SECRET","SSI_PRIVATE_KEY")) {
    if (-not (Test-Path "Env:$v")) { Write-Host "!! THIẾU $v" } else { Write-Host "OK: $v có giá trị" }
}
```

## Bước 2 — Xác thực (lấy/refresh access_token)

```powershell
uv run --with ssi-sdk python scripts/spike_ssi_sdk_auth.py
```
Nếu refresh_token cũ (từ phiên trước) còn hạn (TTL 8 giờ, đo ở Phase 0 migration SDK), script sẽ tự refresh, không cần OTP. Nếu hết hạn, nhập OTP khi được hỏi (SSI gửi qua SMS/email).

## Bước 3 — Chạy Phase 0 spike (bước quan trọng nhất)

```powershell
uv run --with ssi-sdk python scripts/spike_ssi_sdk_place_order.py
```

(Mặc định: symbol=VCB, account=0434221. Muốn đổi: thêm `--symbol <mã>` hoặc `--account <số TK>`.)

## Bước 4 — Kiểm tra lại sau khi chạy (dù kết quả thế nào)

```powershell
# Xác nhận không có gì bất thường về số dư (nếu account_sync đã chạy gần đây)
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT * FROM account_balance_snapshot WHERE account_no = '0434221' ORDER BY ts DESC LIMIT 3;"
```
(Nếu chưa có docker/postgres chạy, bỏ qua bước này — không bắt buộc cho Phase 0.)

---

## Báo cáo lại cho Claude (bắt buộc, dù kết quả nào)

1. Dán toàn bộ output của Bước 3 (kể cả nếu dừng sớm ở "không đủ tiền").
2. Nếu chạy hết 4 bước: dán nội dung 3 file `scripts/.spike_max_buy_sell.json`, `.spike_place_order.json`, `.spike_cancel_order.json` (các file này đã gitignore, không tự lộ ra git — an toàn để dán vào chat nếu cần, nhưng cân nhắc che số dư/giá trị nhạy cảm nếu muốn).
3. Có gặp lỗi nào ngoài dự kiến không (401/403, lỗi ký request, response hình dạng khác `dataclasses.fields` đã liệt kê trong `PLAN_REAL_ORDER_PLACEMENT.md`)?

**Sau khi có kết quả này, Claude mới viết tiếp prompt thực thi Phase 1-4** (schema `pending_real_orders`, tái dùng `RiskManager`, script xác nhận thủ công, dry-run gate) — không viết trước để tránh dựa vào giả định chưa kiểm chứng.
