# Kế hoạch: ba lỗ hổng triển khai còn lại

Ngày giao: 2026-08-14 tối muộn. Nhánh: `feature/data-layer`. Base: `317eeb1`.

**KHÔNG commit, KHÔNG push.**

---

## BỐI CẢNH VẬN HÀNH — cuối tuần, cửa sổ rộng

**Mai là thứ Bảy 15/08, không có phiên.** Phiên kế tiếp: thứ Hai 17/08, 9:00.

Nghĩa là không có áp lực thời gian, và việc rebuild container (nếu cần) có thể
làm bất cứ lúc nào — **nhưng người audit làm việc đó, không phải bạn.**

- **KHÔNG** restart/rebuild container, **KHÔNG** chạy `docker compose`.
- **KHÔNG** đụng `config/config.yaml`, **KHÔNG** bật `real_trading_enabled`.
- **KHÔNG** đụng dữ liệu sản xuất.

---

# VIỆC 1 — thông báo lỗi đang dạy sai quy trình (`trading/collector/ssi_auth.py:46-49`)

## Vấn đề, và vì sao nó đắt

```python
raise RuntimeError(
    "SSI refresh_token missing/expired — run scripts/spike_ssi_sdk_auth.py "
    "manually to re-authenticate with OTP, then re-run collector"
)
```

Sai **hai chỗ**:

1. **Bỏ mất bước `scripts/load_token_to_db.py`.** Collector đọc token từ **DB**
   (`ssi_auth_state`), KHÔNG đọc file `scripts/.ssi_sdk_token.json`. Script bridge
   đó là cầu nối **duy nhất** giữa hai nơi. Làm OTP mà quên bước này thì không có
   gì thay đổi.
2. **"then re-run collector" là thừa và gây hiểu lầm.** Collector tự nối lại khi
   DB có token hợp lệ — đã chứng minh 14/08: token nạp lúc 17:29:39, collector
   phục hồi lúc 17:30:16 (`Token refreshed successfully`) mà **không ai restart**.

Dòng này in ra ~180 lần trong log ngày 14/08. Nó là hướng dẫn vận hành được đọc
nhiều nhất trong hệ thống, và nó dạy sai. Bước 2 đã bị quên **hai lần** — lần gần
nhất khiến đồng bộ tài khoản chết 4 tiếng (13:39 → 17:30).

## Phải làm

Viết lại thông báo cho đúng **hai bước**, và bỏ lời khuyên restart. Nội dung
phải nêu rõ vì sao có bước 2 (collector đọc DB, không đọc file) — một câu ngắn,
vì người đọc dòng này đang lúc sự cố.

Tham chiếu văn phong: tin nhắn 2B trong `scripts/heartbeat_check.py` (`7700992`)
đã diễn đạt đúng — giữ nhất quán với nó.

## Ràng buộc việc 1

- **Chỉ** sửa chuỗi thông báo trong `trading/collector/ssi_auth.py`. KHÔNG đổi
  logic, KHÔNG đổi `timeout=5`, KHÔNG đụng `feed.py`.
- `gitnexus_impact` trên `ensure_authenticated` trước khi sửa.

## Kiểm chứng việc 1

1. **Kiểm trước khi sửa:** có test nào khẳng định chuỗi cũ không?
   `grep -rn "re-authenticate\|missing/expired" tests/`. Nếu có, cập nhật và
   **báo cáo rõ** — đừng để test đỏ rồi mới phát hiện.
2. Test khẳng định thông báo mới có nhắc **cả hai** script. Đây là điểm chính:
   nếu ai đó sau này rút gọn lại thành một bước, test phải đỏ.
3. Toàn bộ suite + ruff sạch.

---

# VIỆC 2 — runbook không có mục nào về token (`DEPLOYMENT.md`)

`DEPLOYMENT.md` có đủ 9 mục: prerequisites, secrets, tường lửa, TLS, khởi động,
backup, resource limits, xoay log, dead-man's switch.

**Không có mục nào về quy trình token.** `grep load_token_to_db DEPLOYMENT.md`
= 0 kết quả. Nó chỉ được nhắc trong một kế hoạch cũ (`docs/plans-legacy/`), một
file prompt, và `GO_LIVE_AUDIT.md` — không cái nào là runbook vận hành.

Đây là thao tác phải làm **mỗi ngày giao dịch**, và là nguyên nhân của hai sự cố.

## Phải làm

Thêm một mục mới vào `DEPLOYMENT.md` (đặt trước §9 dead-man's switch, vì §9 có
cảnh báo token nên đọc sau sẽ mạch lạc hơn). Nội dung:

- **Hai bước, đúng thứ tự:** `scripts/spike_ssi_sdk_auth.py` (nhập OTP) →
  `scripts/load_token_to_db.py`. Nêu rõ bước 2 là cầu nối duy nhất sang DB.
- **Vòng đời 8 giờ, KHÔNG được gia hạn** bằng việc làm mới access token. Đây là
  điều phản trực giác nhất và là gốc của sự cố 14/08.
- **Thời điểm nên làm: khung 8:00–9:00 ngày giao dịch.** Làm lúc 8:30 thì token
  chết ~16:30, phủ trọn phiên (9:00–14:45). Làm quá sớm sẽ chết giữa phiên chiều.
- **Không cần restart collector** — nó tự nối lại. Dẫn bằng chứng 14/08
  (17:29:39 nạp → 17:30:16 phục hồi).
- **CẢNH BÁO BẢO MẬT:** không dán nội dung file token vào chat/issue/log. Nếu
  cần báo cáo, chỉ dẫn `expires_at` / `refresh_token_expires_at`.
- Nhắc rằng cảnh báo 2B (§9) sẽ nhắc lúc 8:00–8:59 nếu quên — nhưng **chỉ khi
  cron đã được cài**.

**KHÔNG** hướng dẫn tự động hoá OTP. SSI yêu cầu OTP thủ công; đừng gợi ý cách
lách.

---

# VIỆC 3 — §8 "Log rotation" chỉ xoay một nửa số log

§8 cấu hình `log-driver` json-file cho Docker. Nhưng §6 và §9 tự tạo **hai file
log trên host** mà không có gì xoay chúng:

```
/var/log/trading-backup.log      (§6, cron 02:00 mỗi ngày)
/var/log/trading-heartbeat.log   (§9, cron mỗi 5 phút, 8 giờ/ngày, 5 ngày/tuần)
```

`grep -c logrotate DEPLOYMENT.md` = 0.

File heartbeat nhận ~96 lần chạy mỗi ngày giao dịch, ghi thêm mãi mãi. Một mục
tên "Log rotation" mà bỏ sót đúng những log do chính tài liệu này tạo ra là
thiếu sót thật.

## Phải làm

Thêm vào §8 một khối `logrotate` cho hai file đó. Giữ đơn giản: xoay theo tuần
hoặc theo kích thước, giữ vài bản, nén. **KHÔNG** phát minh gì phức tạp —
`/etc/logrotate.d/trading` với cấu hình tối thiểu là đủ.

Nêu rõ đây là cấu hình trên **host**, không phải trong container.

---

# Ràng buộc chung

- **Được sửa:** `trading/collector/ssi_auth.py` (chỉ chuỗi thông báo),
  `DEPLOYMENT.md`, test tương ứng.
- **KHÔNG đụng:** mọi file khác trong `trading/`, `scripts/`, `config/`,
  `docker-compose.yml`.

# Toàn bộ

- `uv run pytest -q` → 304 passed + test mới.
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán mức rủi ro + danh sách file.
- **KHÔNG commit, KHÔNG push.**

# Nếu thấy kế hoạch sai

Dừng và phản biện. Hai chỗ tôi có thể đã chọn nhầm:

1. **Việc 1 chỉ sửa chuỗi.** Có lập luận rằng nên tách hẳn hướng dẫn vận hành ra
   khỏi code và chỉ để thông báo trỏ tới runbook. Tôi chọn giữ hướng dẫn trong
   thông báo vì người đọc nó đang lúc sự cố và không muốn mở tài liệu. Nếu bạn
   thấy ngược lại — nói ra.
2. **Việc 3 dùng logrotate.** Nếu bạn biết cách gọn hơn phù hợp với phần còn lại
   của runbook — nói ra.
