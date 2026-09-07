# Đánh giá sẵn sàng go-live theo 4 lớp + Brief đợt 15

Ngày: 07/09/2026 (thứ Hai, phiên giao dịch bình thường)
HEAD lúc đo: `e244af6`, cây làm việc sạch.
Người viết: Claude (planner/auditor). Mọi con số dưới đây do tôi tự truy vấn/chạy lại
trong phiên này, không lấy từ báo cáo cũ.

---

## 0. Cách tôi đo — và giới hạn của phép đo

- Truy vấn DB `trading` trực tiếp qua `docker exec ... psql -U trading` (chỉ SELECT).
- `schtasks /query /v` để đọc lịch chạy thật, đối chiếu với `logs/*.log`.
- `uv run pytest -q -m "not integration"` và `uv run ruff check trading tests scripts`.
- `uv run python scripts/deploy_drift_check.py` chạy tay.
- Đọc mã nguồn tại chỗ cho các đường đi tôi khẳng định.

**Không đo được trong phiên này (nói rõ để không ai tưởng đã kiểm):**
- Không gọi SSI lần nào (giữ đúng ràng buộc, tránh 429).
- MCP `gitnexus` **không kết nối được** phiên này (CONNECT_TIMEOUT), nên tôi không chạy
  được `gitnexus_impact`. Phần blast radius dưới đây tôi suy từ `grep` toàn repo — yếu hơn.
- Chưa quan sát được mốc 03:05 sáng mai (xem L1-2), nên nhánh tự xác thực lại chưa có
  bằng chứng vận hành.

---

## 1. Kết luận một dòng

**Chưa sẵn sàng go-live.** Ba lớp đầu (lấy dữ liệu, xử lý, quản trị) về cơ bản đứng được;
**lớp gửi lệnh thì chưa từng chạy một lần nào tới đích** — và lý do không phải lỗi kỹ
thuật mà là ba thứ lệch nhau: tài khoản cấu hình trống, rổ mã theo dõi không trùng danh
mục thật, và cơ chế xác nhận thủ công 15 phút chưa từng được ai bấm.

---

## 2. Lớp 1 — Lấy dữ liệu giao dịch

### Đang chạy được

| Đo | Kết quả |
|---|---|
| `bars` (5m) | 934.343 dòng, 310 mã, bar mới nhất **07/09 14:45** |
| `bars_daily` | 2.983.261 dòng, 1.554 mã |
| Heartbeat | collector 07/09 19:31:16, engine 19:31:25 — cả hai còn thở |
| Bar 5m hôm nay | AAA 44, IJC 43, HII 39 (trần lý thuyết HOSE = 46, đợt 12 xác lập) |
| `account_position_snapshot` | 12.516 dòng, đồng bộ lần cuối 07/09 19:26 |

Số bar 39–44/46 là **bình thường**, không phải hỏng: đợt 12 đã chứng minh bar thiếu là
khung 5 phút không có khớp lệnh. HII thấp nhất — khớp với việc HII vốn ít thanh khoản nhất
trong rổ.

### L1-1 — Rổ dữ liệu thời gian thực chỉ có 3 mã

`config/config.yaml` → `symbols: [HII, IJC, AAA]`. 310 mã trong `bars` là **dữ liệu nạp
lịch sử**, không phải luồng thật. `symbol_universe` có 1.595 mã.

Đây không phải lỗi — là lựa chọn. Nhưng phải nói thẳng hệ quả: **mọi kết luận về vận hành
thật hiện chỉ có hiệu lực trên 3 mã**, và không mã nào trong 3 mã đó nằm trong danh mục
thật (xem L3-1).

### L1-2 — Vòng đời token SSI: chưa có bằng chứng vận hành cho nhánh tự xác thực lại

Đo trực tiếp `ssi_auth_state` lúc 19:31:55 hôm nay:

```
access_token  hết hạn: 07/09/2026 19:46:19 +07  (còn ~15 phút)
refresh_token hết hạn: 08/09/2026 03:05:10 +07  (còn ~7,5 giờ)
```

`refresh_token` **chết lúc 03:05 sáng mai, trước giờ mở cửa 09:00.**

Tôi đã đọc `trading/collector/ssi_auth.py:36-65` và phải **đính chính một hiểu sai cũ của
chính tôi**: khi `refresh_token` hết hạn, module tự gọi `authenticate(otp=None)` — api_key/
api_secret đủ scope `trading:*:*`, `data:*:*`, `stream:*:*` nên **không cần OTP**. Chỉ khi
lời gọi đó thất bại mới cần người chạy `scripts/spike_ssi_sdk_auth.py` nhập OTP tay.

Nghĩa là giả định "phải nhập OTP tay mỗi sáng" — thứ tôi từng coi là rào cản lớn nhất của
việc chuyển VPS — **có thể sai**. Nhưng tôi cũng không có bằng chứng nó đúng: `ssi_auth_state`
chỉ có 1 dòng bị ghi đè, không lưu lịch sử, nên **không thể chứng minh nhánh này đã từng
chạy qua một mốc hết hạn thật**. Đây là ẩn số quan trọng nhất còn lại của lớp 1, và nó chỉ
cần **một buổi sáng quan sát**, không cần code (xem mục 7, việc O-1).

Mạng an toàn có sẵn: `heartbeat_check.token_expiry_status` báo WARN khi còn <60 phút,
CRITICAL khi đã hết hạn; job heartbeat chạy 5 phút/lần từ 08:00. Nếu 03:05 hỏng thì
08:00 sẽ có Telegram CRITICAL — trước giờ mở cửa 1 tiếng.

---

## 3. Lớp 2 — Xử lý dữ liệu

### L2-1 — Engine gần như câm (đã biết, nay có số)

`orders` có 18 dòng, dòng mới nhất **03/09**. Hai phiên 04/09 và 07/09 có bar 5m chảy đủ
nhưng **không sinh lệnh giấy nào**.

`engine_state`: cash 91.215.342, realized −389.537, cập nhật 03/09 02:20 UTC.

Đây khớp với ghi chú trong CLAUDE.md (octopus hiệu chỉnh theo bar ngày, chạy trên bar 5m
thì gần như không phát tín hiệu). Không phải hồi quy mới.

### L2-2 — Không có chuông riêng cho "engine câm"

`scripts/check_silent_engine.py` tồn tại, `scripts/sched.sh` đã có nhánh `engine-cam`,
nhưng `schtasks` **không có task nào gọi nó**. Bốn task trading hiện có:
`trading-backfill-universe`, `trading-daily-data-check`, `trading-deploy-drift`,
`trading-heartbeat-check`.

Hệ quả: engine im 4 phiên liền cũng không ai được báo. Đây là mục còn lại của C2, và nó là
**việc của chủ dự án** (tạo task cần chạm Task Scheduler), không giao agent được.

### L2-3 — `bars_daily` hôm nay mới có 8 mã — chưa phải lỗi

| Ngày | Số mã trong `bars_daily` |
|---|---|
| 25/08 | 916 |
| 26/08 | 912 |
| 27/08 | 862 |
| 28/08 | 965 |
| 03/09 | 175 |
| 04/09 | 175 |
| 07/09 | **8** |

Tụt 965 → 175 là **đúng thiết kế** (tách vai universe, đã kết luận ở đợt 14). Còn 8 mã của
hôm nay là vì `trading-backfill-universe` **chưa chạy** — lịch 20:30, tôi đo lúc 19:31.
Không kết luận gì thêm được đêm nay; sáng mai nhìn lại phải thấy ~175.

---

## 4. Lớp 3 — Gửi lệnh giao dịch

**Đây là lớp yếu nhất, và là lý do chính trả lời "chưa".**

### L3-1 — Tài khoản cấu hình trống; tiền nằm ở tài khoản khác

`config/config.yaml` → `real_order_account: "0434221"`.

Đo `account_position_snapshot` gộp theo tài khoản:

```
0434226 | 12516 dòng | mới nhất 07/09 19:26:13
(0434221: KHÔNG CÓ DÒNG NÀO)
```

Và `account_sync_log` có **cả hai** tài khoản ở cùng mốc 07/09 19:26:13 — nghĩa là 0434221
**đã được đồng bộ và thật sự rỗng**, chứ không phải "chưa đồng bộ bao giờ". Cơ chế
SYNC-LOG-1 đang hoạt động đúng và đang nói thật.

Danh mục thật (0434226, ảnh chụp mới nhất):

| Mã | SL | Giá vốn | Bán được |
|---|---|---|---|
| FOX | 1.100 | 65.000 | 1.100 |
| HCM | 1.000 | 24.296 | 1.000 |
| SSI | 1.200 | 19.875 | 1.200 |
| TCX | 160 | 41.339 | 160 |
| VCB | 1.500 | 60.706 | 1.500 |

≈ **217,3 triệu VND theo giá vốn.**

Hai điều phải nhìn cùng lúc:

1. `real_order_account` trỏ vào tài khoản rỗng → `read_real_positions()` trả `{}` →
   nhánh BÁN không bao giờ có gì để bán. Đây chính là mục J, nhưng bây giờ đã biết
   **nguyên nhân gốc không nằm ở logic chiến lược mà ở một dòng cấu hình.**
2. **Kể cả đổi sang 0434226 cũng chưa đủ**: không mã nào trong FOX/HCM/SSI/TCX/VCB nằm
   trong `symbols: [HII, IJC, AAA]`. Engine không nhìn thấy chúng, nên vẫn không quản lý
   được danh mục thật.

Muốn hệ thống thực sự chạm được tiền thật thì phải sửa **cả hai**, và đó là quyết định của
chủ dự án chứ không phải việc agent tự ý làm.

### L3-2 — 9/9 lệnh chờ đều hết hạn; chưa một lệnh nào tới SSI

`pending_real_orders`: 9 dòng, **tất cả `status = 'expired'`**, mới nhất 04/09 (IJC BUY
100 @ 7.330). `real_order_fills`: **0 dòng**.

Nghĩa là: đường sinh lệnh có chạy, nhưng bước xác nhận thủ công
(`scripts/confirm_real_order.py`) **chưa từng được bấm lần nào**, và TTL 15 phút
(`real_orders.py:11 PENDING_ORDER_TTL_MINUTES = 15`) đã dọn sạch.

Đây là phát hiện thiết kế, không phải bug: **cơ chế người-xác-nhận với TTL 15 phút chỉ hoạt
động khi có người ngồi canh màn hình trong giờ giao dịch.** Tỷ lệ tới đích thực đo được
đến hôm nay là **0/9**. Nếu mục tiêu là chạy không người trực trên VPS thì mô hình này
tự mâu thuẫn — hoặc bỏ xác nhận tay, hoặc chấp nhận có người trực, hoặc nới TTL. Ba
hướng đó khác nhau về rủi ro rất nhiều, nên tôi để chủ dự án chọn.

### L3-3 — Đặt lệnh xong là ghi nhận như đã khớp, và không ai đối soát lại

`scripts/confirm_real_order.py:166-189`: ngay sau khi `place_limit_order` trả về, code ghi
một dòng `real_order_fills` với `status="placed"`, `price = giá đặt`, `fee` = **ước lượng**
`FEE_RATE_ESTIMATE = 0.0025`.

Nhãn `"placed"` là trung thực. Vấn đề nằm ở phía đọc:

- `db.py:265-279 read_real_highest_since_buy` — lọc `status IN ('placed','filled')`, tức
  **coi lệnh mới đặt là đã có hiệu lực**. Có chú thích, là lựa chọn có chủ ý.
- `db.py:816-832 read_real_daily_pnl` — **không lọc status gì cả**, `SUM(pnl)` trên mọi dòng.

Và `grep` toàn repo: **chỉ có một chỗ ghi vào `real_order_fills`** (`write_real_order_fill`,
gọi từ đúng `confirm_real_order.py:178`). **Không có vòng đối soát nào** hỏi lại SSI xem
lệnh khớp chưa, khớp bao nhiêu, hay đã bị huỷ — không chỗ nào cập nhật `status` từ
`'placed'` sang `'filled'`/`'cancelled'`.

Chính lược đồ DB tự tố cáo điều đó. Ràng buộc trên bảng:

```
"real_order_fills_status_check" CHECK (status = ANY (ARRAY['placed','cancelled','filled']))
```

Ba trạng thái đã được dự trù từ đầu, nhưng **chỉ một trạng thái từng được ghi**. Vòng đối
soát rõ ràng là đã nằm trong ý định thiết kế và chưa bao giờ được xây.

Hệ quả cụ thể, theo hướng nguy hiểm: `real_orders.py:115` dùng `read_real_daily_pnl` làm
**cầu dao lỗ trong ngày**. Một lệnh BÁN đặt ở giá P ghi ngay `pnl = (P − giá vốn) × qty`
dù có khớp hay không. Lãi ảo của một lệnh không bao giờ khớp sẽ **che bớt lỗ thật** và
giữ cầu dao mở lâu hơn mức đáng.

Hiện chưa gây thiệt hại: `real_order_fills` rỗng, `real_trading_enabled: false`. Nhưng đây
là thứ sẽ nổ đúng vào ngày bật thật.

Phần "thiếu vòng đối soát" là **việc lớn, cần API trạng thái lệnh của SSI** → đưa vào mục
quyết định (mục 7), không giao đợt này. Phần **`read_real_daily_pnl` thiếu lọc status** thì
nhỏ, gọn, sửa được ngay → Task 2 của brief.

---

## 5. Lớp 4 — Quản trị hệ thống

### Đang tốt

- 502 test xanh, `ruff` sạch trên `trading tests scripts` (tôi tự chạy lại).
- Heartbeat 5 phút/lần, 08:00–15:00, phủ trọn hai phiên.
- Chuông Docker-chết (D1) đã có bằng chứng kêu thật: `logs/deploy-drift.log` 03/09 có
  `SKIP: docker chua chay` + CRITICAL + `ALERT_EXIT=0`.
- Đường sao lưu/phục hồi đã kiểm hết, kể cả ống nhị phân trên host Windows (đợt 13 + 14).

### L4-1 — Mã thoát của mọi job giám sát bị nuốt (phát hiện mới, có bằng chứng đối khớp)

`scripts/run_if_docker_up.sh` kết thúc bằng:

```bash
"$@" >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
```

Dòng cuối là `echo`, **luôn thành công** → script luôn thoát 0, bất kể job bên trong đúng
hay sai. `run_hidden.vbs` thì có truyền `rc` đàng hoàng (`WScript.Quit rc`), nên lỗi nằm
đúng ở đây.

Bằng chứng đối khớp, cùng một lần chạy 08:00 hôm nay:

| Nguồn | Nói gì |
|---|---|
| `logs/deploy-drift.log` | `2026-09-07 08:00:03 deploy-drift start` … `EXIT=1` |
| `schtasks /query /tn trading-deploy-drift` | `Last Result: 0` |

Job **thất bại** mà Task Scheduler ghi **thành công**.

Mức độ: Telegram vẫn kêu (tôi đã đọc `deploy_drift_check._alert` → `alert_and_fail(...,
send_telegram)`), nên đây không phải câm hoàn toàn. Nhưng:

- Lịch sử `Last Result` của cả 4 task là **vô nghĩa**, xanh vĩnh viễn.
- Trên Ubuntu, **cron gửi mail khi job thoát khác 0** — kênh đó đang chết sẵn trước khi
  chuyển VPS. `DEPLOYMENT.md` lại hướng dẫn dùng cron.

→ Task 1 của brief.

Lưu ý khi sửa: nhánh SKIP (Docker chưa chạy) thoát 0 là **có chủ ý** — "bỏ qua" không phải
"thất bại", và nhánh đó đã có `docker_down_alert` riêng. Không được đổi nhánh đó.

### L4-2 — Lệch triển khai 14 phút vẫn còn (chưa ai làm)

Tôi chạy tay `scripts/deploy_drift_check.py` lúc 19:2x hôm nay, thoát 1:

```
[deploy-drift] collector: image CŨ hơn commit gần nhất chạm trading/ (14 phút)
[deploy-drift] engine: image CŨ hơn commit gần nhất chạm trading/ (14 phút)
```

`docker images`: collector và engine đều dựng **06/09 07:45:03**. Container đang chạy
đúng image cũ đó.

Nghĩa là container đang chạy **có thể thiếu** chốt an toàn vị thế ôi (P1) và mức trần
`MAX_REAL_BUY_QTY = 100`. Với `real_trading_enabled: false` thì chưa nguy hiểm, nhưng
không được bật thật khi lệch còn đó.

### L4-3 — Docker Desktop chưa tự khởi động

`logs/deploy-drift.log` cho thấy 02/09 và 03/09 đều `SKIP: docker chua chay` lúc 08:00, và
hôm nay container mới `Up 11 minutes` lúc tôi đo (19:31). Mục C2 còn lại, việc của chủ dự án.

Đây cũng là lý do phải nhìn L4-1 nghiêm hơn: khi Docker tắt, **mọi** job giám sát đều SKIP
và thoát 0 — không phân biệt được "hệ thống khoẻ" với "hệ thống không được kiểm".

---

## 6. Bảng tổng hợp

| Lớp | Trạng thái | Chặn go-live? |
|---|---|---|
| 1. Lấy dữ liệu | Chạy được, ổn định trên 3 mã | Không — nhưng L1-2 (token qua mốc 03:05) chưa có bằng chứng |
| 2. Xử lý dữ liệu | Chạy, nhưng gần như không sinh tín hiệu | Không chặn kỹ thuật; chặn về **ý nghĩa** (Tier 1: không có edge đo được) |
| 3. Gửi lệnh | **Chưa từng chạm đích một lần nào** | **CÓ — chặn cứng** (L3-1, L3-2, L3-3) |
| 4. Quản trị | Chuông tốt, mã thoát hỏng, lệch image chưa gỡ | **CÓ — L4-2 phải gỡ trước khi bật thật** |

---

## 7. Brief đợt 15 — giao agent

### Ràng buộc chung (giữ nguyên, không thương lượng)

- `real_trading_enabled` giữ `false`. Không bật kể cả tạm thời.
- **Không gọi API đặt lệnh/huỷ lệnh SSI.** Đợt này **không gọi SSI lần nào cả**, kể cả API
  dữ liệu — hai task dưới đây không cần.
- Không in giá trị secret ra bất kỳ đâu.
- `.env` không được sửa, không được commit.
- `config/config.yaml` **không được sửa** — kể cả `real_order_account`, kể cả khi đã đọc
  mục L3-1 và thấy nó sai. Đó là quyết định của chủ dự án.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB `trading`.
- Không sửa định nghĩa `PaperBroker`, `run_backtest`, `derivative_backtest`.
- **Agent KHÔNG commit, KHÔNG push.** Claude audit xong mới commit.
- **Chỉ sửa đúng các file được nêu tên dưới đây.** Phát hiện ngoài phạm vi thì **báo cáo,
  không tự sửa** — đợt 13 đã từng viết đè `probe_bars_5m_completeness.py` (481 → 184 dòng)
  mà không báo, tôi phải khôi phục tay. Đừng lặp lại.
- Trước khi sửa symbol: chạy `gitnexus_impact`; sau khi sửa: `gitnexus_detect_changes`.
  **Phiên của tôi hôm nay MCP gitnexus timeout** — nếu bên bạn cũng vậy thì **nói rõ trong
  báo cáo là không chạy được**, đừng im lặng bỏ qua và cũng đừng bịa kết quả.

---

### Task 1 — Trả lại mã thoát thật cho `run_if_docker_up.sh`

**File được sửa:** `scripts/run_if_docker_up.sh` — **chỉ** file này. Repo không có khung
test cho shell script; bằng chứng của task này là 4 phép chạy tay ở dưới, không thêm file
test nào.

**Vấn đề:** xem L4-1. Job thoát 1, Task Scheduler ghi 0.

**Yêu cầu:**

1. Job chạy thật (nhánh Docker đang lên): script phải thoát **đúng mã thoát của job**.
   Dòng `EXIT=<mã>` trong log phải khớp với mã thoát của chính script.
2. Nhánh **SKIP** (không có `.env`, hoặc Docker chưa chạy) **giữ nguyên `exit 0`**. Đây là
   hành vi có chủ ý, không được đổi. Dòng `ALERT_EXIT=` vẫn phải ghi như cũ.
3. Không đổi bất cứ thứ gì khác trong file: thứ tự nạp `.env`, xoay log, `PYTHONIOENCODING`,
   cách suy ra `PROJECT_NAME`, các khối chú thích.

**Kiểm chứng — phải dán output thô của cả 4 phép, không tóm tắt:**

| # | Phép | Phải thấy |
|---|---|---|
| 1.1 | Chạy job giả thất bại: `scripts/run_if_docker_up.sh t1.log t1 bash -c 'exit 3'` rồi `echo $?` | in `3`; `logs/t1.log` có `EXIT=3` |
| 1.2 | `scripts/run_if_docker_up.sh t2.log t2 bash -c 'exit 0'` rồi `echo $?` | in `0`; `logs/t2.log` có `EXIT=0` |
| 1.3 | Nhánh SKIP: `DOCKER_GATE_CONTAINER=khong-ton-tai scripts/run_if_docker_up.sh t3.log t3 echo hi` rồi `echo $?` | in `0`; log có `SKIP: docker chua chay` và `ALERT_EXIT=` |
| 1.4 | Chạy job thật đang lỗi: `scripts/sched.sh deploy-drift` rồi `echo $?` | in `1` (lệch image chưa gỡ); log có `EXIT=1` |

**Biết trước với phép 1.4:** `sched.sh deploy-drift` **sẽ gửi một tin Telegram thật** về
lệch image. Đó là cảnh báo **đúng** cho một tình trạng **có thật** (L4-2), không phải tin
thử — cứ để nó gửi, và ghi vào báo cáo là đã gửi để chủ dự án không tưởng là tin lạ. Phép
1.4 cũng ghi vào `logs/deploy-drift.log` thật; **đừng xoá dòng nào trong file log đó**.

**Bắt buộc với phép 1.3:** chạy **ngoài khung 09:00–15:00** để `docker_down_alert.py` tự
quyết định không gửi. Trong báo cáo phải nói rõ đã chạy lúc mấy giờ và **xác nhận không có
tin Telegram nào được gửi**. Không được gửi tin thử vào nhóm cảnh báo thật.

**Dọn dẹp:** xoá `logs/t1.log`, `logs/t2.log`, `logs/t3.log` sau khi dán bằng chứng.

**Không được làm:** không đổi `run_hidden.vbs`, không đổi `sched.sh`, không đụng
`schtasks` (tạo/sửa/xoá task là việc của chủ dự án).

---

### Task 2 — `read_real_daily_pnl` phải lọc status như chỗ còn lại

**File được sửa:** `trading/storage/db.py`, `tests/test_storage.py`.

**Vấn đề:** xem L3-3. `read_real_highest_since_buy` (db.py:276) lọc
`status IN ('placed','filled')`; `read_real_daily_pnl` (db.py:828) **không lọc gì**. Hai
chỗ cùng đọc một bảng với hai định nghĩa "fill có hiệu lực" khác nhau.

**Yêu cầu:**

1. Đặt **một** hằng số cấp module trong `trading/storage/db.py`, ví dụ
   `EFFECTIVE_FILL_STATUSES = ("placed", "filled")`, kèm chú thích ngắn nói rõ vì sao
   `'placed'` được tính là có hiệu lực (chưa có vòng đối soát khớp lệnh — dẫn tới mục
   L3-3 của plan này).
2. Dùng hằng số đó ở **cả hai** truy vấn. Đây là "một công thức, một chỗ" (tiền lệ `4ea4c8d`).
3. Giữ nguyên phần quy đổi múi giờ `AT TIME ZONE 'Asia/Ho_Chi_Minh'` trong
   `read_real_daily_pnl` — đó là bản vá cũ, đừng vô tình làm hỏng.

**Trước khi sửa, tự kiểm và ghi vào báo cáo:** `real_order_fills` hiện có **0 dòng** (tôi đã
đo 07/09). Vậy thay đổi này **không đổi kết quả trên dữ liệu đang có** — nếu bạn đo ra khác
0 thì dừng lại và báo, đừng sửa tiếp.

**Kiểm chứng:**

1. Viết test mới trong `tests/test_storage.py`: ghi 3 dòng `real_order_fills` cùng ngày —
   một `'placed'` pnl=+100, một `'filled'` pnl=+200, một `'cancelled'` pnl=+9999 — rồi
   khẳng định `read_real_daily_pnl` trả về `300.0`, **không** phải `10299.0`.
   → Kiểm chứng bằng: test này **đỏ trên mã cũ**, xanh trên mã mới. Phải dán cả hai lần chạy.
   Test viết theo đúng khuôn các test sẵn có ở `tests/test_storage.py:228-273`, tức chạy
   trên DB **`trading_test`**. Tuyệt đối không trỏ vào DB `trading` — bảng thật đang có 0
   dòng và phải giữ nguyên 0 dòng sau khi bạn xong.
2. Toàn bộ suite xanh: `uv run pytest -q` (có `docker compose --profile test up -d nats-test`).
3. `uv run ruff check trading tests scripts` sạch.
4. **Phá hoại có chủ đích:** bỏ bộ lọc status ra khỏi `read_real_daily_pnl`, chạy lại, dán
   **tên test đỏ thật** + dòng lỗi. Rồi khôi phục, chạy lại xanh, và chạy
   `grep -rn "SABOTAGE" .` cho ra rỗng.

**Không được làm:** không đổi `write_real_order_fill`, không đổi `confirm_real_order.py`,
không thêm vòng đối soát trạng thái lệnh (việc lớn, đang chờ chủ dự án quyết — mục Q-3).

---

### Báo cáo nghiệm thu phải có

- Output thô của từng phép kiểm ở trên, **nguyên văn**, không tóm tắt, không tự gõ lại bảng.
  (Đợt 10 và đợt 14 đều từng có bảng bịa trong báo cáo dù code đúng. Tôi sẽ chạy lại và đối
  chiếu từng con số.)
- Giờ chạy phép 1.3 + xác nhận không gửi Telegram.
- `git status --short` và `git diff --stat` — để tôi thấy đúng những file được phép sửa.
- Nếu `gitnexus` không kết nối được: nói thẳng.

---

## 8. Việc của chủ dự án (không giao agent được)

| # | Việc | Vì sao gấp |
|---|---|---|
| **O-1** | Sáng mai kiểm token: khoảng 08:05 đọc lại `ssi_auth_state` xem `refresh_token_expires_at` đã nhảy qua mốc mới chưa, và kiểm hộp Telegram có CRITICAL token không | Đây là **phép thử một lần, miễn phí, tự chạy** trả lời câu hỏi lớn nhất còn lại của việc chuyển VPS: hệ thống có tự xác thực lại được không người trực (L1-2) |
| **O-2** | `docker compose build collector engine && docker compose up -d --no-deps collector engine` | Gỡ lệch 14 phút (L4-2). Container đang chạy có thể thiếu P1 và trần `MAX_REAL_BUY_QTY` |
| **O-3** | Tạo scheduled task `trading-engine-cam` gọi `sched.sh engine-cam` | Engine im 4 phiên liền mà không ai được báo (L2-2) |
| **O-4** | Bật Docker Desktop tự khởi động cùng Windows | Docker tắt = mọi job giám sát SKIP (L4-3) |

---

## 9. Quyết định đang treo (của chủ dự án)

| # | Quyết định | Trạng thái dữ liệu |
|---|---|---|
| **Q-1** | **Tier 1 — chiến lược.** Đóng lại, hay thiết kế lại? | Cả ba đường đã đóng bằng số đo: khung ngày PF 0,74 (1.514 lệnh); 5m toàn rổ PF 0,47 (574 lệnh); nới tham số 5m bất khả thi vì dữ liệu (SSI chỉ ~150 ngày intraday). Không còn phép đo nào để chờ |
| **Q-2** | **Tài khoản + rổ mã.** Đổi `real_order_account` sang 0434226, **và** đưa danh mục thật vào `symbols`? | Đo được: 0434221 rỗng; 0434226 giữ ~217,3 tr; không mã nào trùng rổ. Phải sửa cả hai mới có tác dụng — sửa một nửa thì vẫn không quản được gì (L3-1) |
| **Q-3** | **Mô hình xác nhận lệnh.** Giữ xác nhận tay TTL 15', bỏ, hay nới? Và có làm vòng đối soát khớp lệnh không? | Đo được: 0/9 lệnh từng tới đích. Không có vòng đối soát → cầu dao lỗ trong ngày chạy trên lãi/lỗ giả định (L3-2, L3-3) |
| **Q-4** | **Chuyển VPS Ubuntu.** | Đường dữ liệu đã kiểm xong (đợt 13 + 14). Sau O-1 thì rào cản OTP có thể biến mất. Nhưng Task 1 đợt này phải xong trước — cron Ubuntu dựa vào mã thoát, mà mã thoát đang bị nuốt (L4-1) |
| **Q-5** | Lịch nghỉ lễ 2027 | `check_holiday_exhaustion` tự cảnh báo từ 01/10. Chưa gấp |

**Thứ tự tôi đề nghị:** Q-1 trước hết. Nếu Tier 1 đóng thì Q-2 và Q-3 tự tan — không cần
quyết định gì về đường gửi lệnh cho một chiến lược không dùng nữa. Đừng đầu tư vào lớp 3
trước khi biết lớp 2 có đáng chạy không.
