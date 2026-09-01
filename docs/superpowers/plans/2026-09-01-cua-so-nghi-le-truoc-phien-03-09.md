# Plan — Cửa sổ ngoài giờ giao dịch: từ 01/09 22:00 đến 03/09 09:00

Viết cuối ngày 01/09/2026, sau khi stack được dựng lại lần đầu kể từ 15/08.

---

## 0. Bối cảnh quyết định thứ tự

**Phiên 03/09 là lần đầu tiên toàn bộ `trading/` chạy code hiện tại.** Từ 15/08
đến 01/09 container chạy image cũ; mọi thứ sửa trong hai tuần — sizing lệnh
thật theo NAV, GUARD-3, watchdog, backoff 429 — hôm nay mới thực sự nằm trong
image (`f047541`, image build `2026-09-01T13:33:33Z`).

Điều đó định đoạt nguyên tắc của cả cửa sổ này:

> **03/09 phải là một phép đo sạch.** Mỗi thay đổi chạm đường giao dịch từ giờ
> tới lúc đó là thêm một biến vào phép đo. Nếu 03/09 có chuyện, ta cần trả lời
> được "code nào gây ra" — mà bây giờ câu trả lời đang gọn: đúng cái vừa dựng.

Nên plan này **không phải danh sách càng làm nhiều càng tốt**. Việc có giá trị
nhất trong cửa sổ này là **chuẩn bị quan sát**, không phải sửa thêm.

### Lịch cứng

| Mốc | Việc |
|---|---|
| 02/09 cả ngày | nghỉ lễ Quốc khánh (đã có trong `config.yaml`) |
| 02/09 08:00 | `trading-deploy-drift` chạy — kỳ vọng OK |
| 02/09 15:30 | `trading-daily-data-check` — kỳ vọng im (nhường 2A) |
| 02/09 20:30 | `trading-backfill-universe` — kỳ vọng 0 bar mới |
| **03/09 08:00–09:00** | khung tiền-phiên: **nạp token SSI** (thủ công, bắt buộc) |
| **03/09 09:00** | phiên đầu tiên chạy code mới |

---

## 1. Task A — Danh sách kiểm trước phiên 03/09 (ưu tiên cao nhất)

Không sửa gì. Chỉ đọc và xác nhận. Mục tiêu: **không để 03/09 là lúc đầu tiên
phát hiện có thứ hỏng.**

1. **Token SSI còn hạn tới hết phiên?** `refresh_token` sống 8 giờ và không gia
   hạn được. Nạp lúc 08:30 thì chết ~16:30, phủ trọn 09:00–14:45. Quy trình hai
   bước ở `DEPLOYMENT.md §8.5` — bước thứ hai (`load_token_to_db.py`) là cầu nối
   sang DB và **chính nó hay bị quên** (sự cố 14/08).
   → *Kiểm chứng:* `heartbeat_check` chạy trong khung 08:00–08:59 sẽ tự nhắc nếu
   quên. Đừng dựa vào trí nhớ.

2. **Bốn scheduled task còn sống và trỏ đúng?**
   → *Kiểm chứng:* `schtasks /query /fo LIST /v | findstr trading` — cả bốn có
   `Next Run Time` thuộc 03/09, và `Last Result` = 0.

3. **Container vẫn chạy image 01/09?**
   → *Kiểm chứng:* để `trading-deploy-drift` trả lời — nó chạy 08:00 và sẽ kêu
   nếu lệch. Đây chính là việc nó sinh ra để làm; đừng kiểm tay rồi bỏ qua nó.

4. **`bars_daily` đã có 28/08 và không có 31/08–02/09?**
   → *Kiểm chứng:* `SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, count(*)
   FROM bars_daily WHERE ts >= '2026-08-24' GROUP BY 1 ORDER BY 1;`
   Kỳ vọng: 24–28/08 mỗi ngày 850–980 mã; 31/08 trở đi trống.

5. **`real_trading_enabled` vẫn `false`.**
   → *Kiểm chứng:* đọc `config/config.yaml`. Kết luận `711683a` chưa thay đổi:
   không chiến lược nào thắng mua-và-giữ, engine chỉ chạy paper.

**Làm khi nào:** sáng 03/09, khung 08:00–08:55. Không sớm hơn — token nạp sớm
quá sẽ chết giữa phiên chiều.

---

## 2. Task B — Việc an toàn tuyệt đối, làm lúc nào cũng được

Chung một tính chất: **không chạm đường giao dịch**, nên không làm bẩn phép đo
03/09.

### B1. Quyết 4 file untracked

```
.claude/skills/source-command-git-commit/
docs/prompts/.hermes-report-2026-08-18-backfill.md
docs/prompts/2026-08-20-brief-antigravity-deadman-drill.txt
docs/superpowers/plans/2026-08-20-deadman-switch-live-drill.md
```

Ba file sau là brief/plan của một đợt diễn tập 20/08 chưa từng chạy. Giữ (có giá
trị lịch sử) hay `.gitignore` (giảm nhiễu) — **quyết định của chủ dự án**, không
phải việc suy đoán. Đây là thứ duy nhất trong plan này cần một câu trả lời chứ
không cần một phép đo.

### B2. Xoay log trên Windows

`DEPLOYMENT.md §8` có logrotate cho Ubuntu, **không có gì cho Windows**. Đo hiện
tại: `logs/heartbeat.log` 240 dòng / 8,6 KB sau một ngày ⇒ ~3 MB/năm. **Chưa
cấp bách**, ghi lại để không quên chứ không phải việc của cửa sổ này.

### B3. Chuẩn bị VPS Ubuntu

Việc lớn nhất còn lại, và hoàn toàn không đụng máy này. `scripts/sched.sh` đã
dùng chung cho cả cron Ubuntu, `DEPLOYMENT.md` đã có đủ §1–§10. Cần một quyết
định hạ tầng (nhà cung cấp, domain, thời điểm) trước khi thành task kỹ thuật.

---

## 3. Task C — Hoãn tới SAU phiên 03/09, có lý do

### C1. Gộp `_print_safe` vào `trading/alerts.py`

`_print_safe` hiện có **hai bản** — `scripts/heartbeat_check.py` và
`scripts/deploy_drift_check.py`. Đã diff: **thân hàm giống hệt nhau**, chỉ
docstring khác; chưa lệch hành vi. Nhưng đây là hàm an toàn của chuông báo, và
`4ea4c8d` đã dạy: một công thức hai nơi thì sớm muộn lệch.

**Vì sao hoãn, không phải vì sao bỏ:** gộp lại nghĩa là sửa `heartbeat_check.py`
lần thứ ba trong một ngày — cái dead-man's switch đã chết câm một lần sáng nay
vì đúng một dòng `print()` thêm vào (`51ff6de`). Và hôm nay là ngày nghỉ nên
chuông đang im **hợp lệ**, tức không có tín hiệu thực địa nào để xác nhận nó còn
kêu sau khi sửa. Sửa một chuông báo mà không quan sát được nó kêu là làm mù.

→ **Điều kiện mở:** sau khi phiên 03/09 cho thấy chuỗi cảnh báo hoạt động bình
thường trên code mới. Lúc đó có phiên thật để kiểm chứng.

### C2. Kiểm chứng backoff 429 — không lên lịch được

Chỉ xảy ra khi có 429 thật, và brief đợt 5 **cấm cố tình gây ra** (gõ cửa dồn
dập chính là hành vi bản sửa sinh ra để diệt). Hành vi đã được kiểm bằng test
tất định (`[2, 4, 8, 16, 32, 64] … max 600s`). Ghi vào sổ chờ, không phải task.

---

## 4. Việc KHÔNG làm trong cửa sổ này, và vì sao

- **Không sửa gì trong `trading/`.** Mọi thay đổi ở đó đòi dựng lại container,
  và làm vậy ngay trước phiên đầu tiên chạy code mới là tự huỷ phép đo.
- **Không đổi `config/config.yaml`** ngoài trường hợp khẩn cấp.
- **Không bật `real_trading_enabled`.**
- **Không tra lịch nghỉ lễ 2026** — chủ dự án đã yêu cầu bỏ. Hệ quả còn treo,
  đã ghi trong `config.yaml`: mọi ngày lễ chưa khai báo sẽ làm 2A báo láo cả
  ngày. Chấp nhận có ý thức, không phải quên.

---

## 5. Điều đáng quan sát nhất ngày 03/09

Không phải "có lỗi không", mà là **ba dòng log chưa từng xuất hiện trên stack
này trong giờ giao dịch**:

1. `NAV lam real capital` — sizing theo NAV chạy trong phiên thật lần đầu.
2. `feed stale, forcing reconnect` — nếu có, giờ nó chỉ kêu khi **thật sự**
   disconnect được (cờ `_connected`, `f8e3392`). Kêu nhiều = tín hiệu thật, khác
   hẳn tiếng ồn trước đây.
3. Bar 5m về đều trong `bars` — thứ chưa xảy ra kể từ 28/08.

Nếu cả ba đúng, phiên 03/09 đóng lại câu hỏi "code mới có chạy được không" và
mở cổng cho C1.
