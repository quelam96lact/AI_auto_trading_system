# Brief đợt 54 — Hai runbook, một nội dung

Ngày giao: 18/09/2026 (tối muộn).
Base: `fde4329` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Việc dọn image đã xong — tôi làm, không giao

Chủ dự án đã đồng ý, nên tôi chạy luôn thay vì viết thành task. Đo trước và sau:

```
TRUOC          Images 18   3.071GB   |  Build Cache  514MB
SAU            Images  6   2.848GB   |  Build Cache  229.4MB
```

| | Thu hồi |
|---|---|
| Xoá 12 tag rollback (đợt 20, 22, 25, 29, 34, 36, 44) | **223MB** |
| `docker builder prune -f` | **284,7MB** |
| **Tổng** | **507,7MB** |

Giữ lại `dot46-rollback-collector:pre` và `dot47-rollback-collector:pre` theo đúng luật giữ mà
đợt 53 đề xuất (hai đợt gần nhất).

**Con số 4,991MB của báo cáo đợt 53 sai 45 lần.** Nguyên nhân đã ghi ở phụ lục A đợt 53: đó là
`RECLAIMABLE` của `docker system df`, chỉ đếm phần không tag nào khác trỏ tới — nên nó bỏ sót
toàn bộ layer mà **cặp** `dot20` cùng dùng. Số đúng chỉ hiện ra khi đo trước/sau thật.

Kiểm chứng sau khi xoá: sáu container còn nguyên, `deploy_drift_check.py` → `exit 0`,
`logs/bars_closed.log` vẫn ghi bình thường.

### 0.1. Và một thói quen vừa đứt mà chưa ai để ý

Các đợt trước đều gắn tag `dotNN-rollback-*:pre` **trước khi** triển khai. Hôm nay tôi dựng lại
collector và engine **bốn lần** mà **không tag lần nào**. Nếu bản vá đợt 52 hoá ra hỏng vào thứ
Hai, không có ảnh "trước đó" để quay về — chỉ còn cách build lại từ commit cũ.

Việc này thuộc Task 3 dưới đây.

---

## 1. Bối cảnh: hai runbook nói hai chuyện khác nhau

Repo có **hai** tài liệu triển khai:

| File | Trạng thái | Vai |
|---|---|---|
| `DEPLOYMENT.md` | **đã commit** | Nguồn chính thức |
| `docs/README_VPS_UBUNTU.md` | **chưa theo dõi** | Hướng dẫn riêng cho VPS Ubuntu |

Cả hai đều lệch so với hệ thống thật, và lệch **cùng ba chỗ** — vì cùng được viết trước đợt 51–52:

```
$ Select-String DEPLOYMENT.md -Pattern "logs:/app/logs|mkdir -p logs|volumes"
(rong)

$ so lan nhac ten tung job cua sched.sh trong DEPLOYMENT.md
heartbeat 14 | backfill 10 | deploy-drift 6 | engine-cam 4 | daily-check 2
engine-consumer 0   <-
stream-health   0   <-

DEPLOYMENT.md:234   30 15 * * 1-5  .../sched.sh daily-check
DEPLOYMENT.md:249   | trading-daily-data-check | 15:30 T2-T6 | ...
```

Ba chỗ lệch, cả ba đều đã trả giá thật trong tuần này:

1. **Không có bước tạo `logs/`, không nhắc volume mount.** `docker-compose.yml` đã có
   `./logs:/app/logs` từ đợt 52. Deploy theo tài liệu này lên máy Linux sạch: thư mục thuộc
   `root`, tiến trình chạy `uid 10001`, handler **nuốt lỗi và chạy tiếp im lặng** — mất bằng
   chứng luồng mà không chuông nào kêu.
2. **Thiếu hẳn `stream-health` và `engine-consumer`.** Cả hai đã có Scheduled Task và đã được
   chứng minh chạy từ đợt 50. Deploy theo tài liệu này là **mất hai chuông**.
3. **`daily-check` vẫn ghi 15:30.** Đợt 51 chứng minh nhịp đó chạy **sớm hơn dữ liệu nó kiểm năm
   tiếng**, khiến job chưa từng một lần có khả năng kêu. Tài liệu đang dạy người ta tái tạo lại
   lỗi đó trên máy mới.

**Đây là việc chặn go-live trên VPS.** Không phải chuyện văn phong: mount có thật trong
`docker-compose.yml`, hai job có thật trong `sched.sh`, nhịp 21:00 là kết luận đã đo.

---

## 2. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `DEPLOYMENT.md` | có sẵn | 1 |
| `docs/README_VPS_UBUNTU.md` | chưa theo dõi | 1 |
| `scripts/README.md` | **mới** | 2 |
| `docs/superpowers/research/2026-09-18-dot-54-*.md` | **mới** | báo cáo |

**Không đụng code.** Nếu bạn thấy mình đang sửa `.py`, `Dockerfile` hay `docker-compose.yml`:
dừng lại, đó không phải đợt này.

Ràng buộc chung: `real_trading_enabled` giữ `false`; không sửa `config/config.yaml`; không gọi
SSI/BingX; không in secret; `.env` không sửa/không commit/**không mở**; **chỉ đọc DB**; **không**
`delete`/`purge`/`add`/`update` stream hay consumer NATS nào; **không dựng lại container**;
**không xoá file, không xoá image**; **không commit, không push**. Mọi `git diff` trong báo cáo
copy từ lệnh. Thiếu thì ghi **"CHƯA LÀM"**, **không bịa** — đợt 52 có hai dòng kiểm chứng không
phải output thật, đừng lặp lại.

---

## Task 1 — Sửa hai runbook, cùng một nội dung

### 1.1. Luật quan trọng nhất của task này

Hai file phải **khớp nhau về sự thật**. Nếu `DEPLOYMENT.md` nói tạo `logs/` bằng cách A và
`README_VPS_UBUNTU.md` nói cách B, ta vừa tạo ra **một công thức hai chỗ** — đúng bệnh `4ea4c8d`
mà repo này đã trả giá nhiều lần.

Cách tránh: **`DEPLOYMENT.md` là nguồn, `README_VPS_UBUNTU.md` trỏ về nó** cho những phần chung,
chỉ giữ riêng phần thật sự đặc thù Ubuntu/VPS (cron thay vì Task Scheduler, systemd, firewall).
Nếu bạn thấy mình chép một đoạn sang file kia: **đừng chép, hãy trỏ**.

### 1.2. Ba chỗ phải sửa

**(a) Thư mục `logs/` và volume mount.**

```bash
mkdir -p logs && sudo chown 10001:10001 logs
```

`10001` là uid cố định trong `Dockerfile` (`useradd --uid 10001 appuser`) nên ổn định giữa các
máy. **Không dùng `chmod 777`** — báo cáo đợt 53 đề xuất thế, đó là mở quyền cho mọi người dùng
trên máy, không phải cách chữa.

Nêu rõ **vì sao** phải làm bước này, một câu: thiếu nó thì collector **không báo lỗi**, nó chạy
tiếp và im lặng không ghi bằng chứng. Người đọc runbook phải hiểu đây không phải bước trang trí.

**(b) Bảy job, không phải năm.** Cập nhật cả dòng cron mẫu lẫn bảng Scheduled Task để có đủ:
`heartbeat`, `daily-check`, `backfill`, `deploy-drift`, `engine-cam`, `engine-consumer`,
`stream-health`.

Nhịp của từng job phải **đọc từ `scripts/sched.sh` và từ Scheduled Task đang chạy thật**, không
chép từ tài liệu cũ. Riêng `engine-consumer` có nhịp khác hẳn các job còn lại (nó chỉ cảnh báo
trong giờ giao dịch) — đợt 50 đã xác định nhịp đúng, tra lại thay vì đoán.

**(c) `daily-check` sang 21:00**, ở **cả** dòng cron lẫn bảng task, ở **cả hai** file. Kèm một
câu lý do: backfill đêm ghi bar daily lúc 20:30, kiểm trước đó thì bảng luôn rỗng.

### 1.3. Ba câu phải trả lời trong báo cáo

1. **Còn chỗ nào khác trong hai file mô tả sai hệ thống hiện tại không?** Hai file này viết trước
   đợt 46–52. Đọc hết, đối chiếu với `docker-compose.yml`, `scripts/sched.sh`,
   `trading/collector/main.py`. Liệt kê mọi chỗ lệch bạn tìm được, kể cả chỗ bạn **không** sửa.
2. **`README_VPS_UBUNTU.md` có nên được commit không?** Nó đang chưa theo dõi. Nêu ý kiến: giữ
   thành file riêng, gộp vào `DEPLOYMENT.md`, hay bỏ?
3. **Một người chưa từng đụng repo này, làm theo `DEPLOYMENT.md` sau khi bạn sửa, có dựng được hệ
   thống chạy không?** Đi qua từng bước và nói chỗ nào họ sẽ vấp. Đây là câu kiểm tra thật sự của
   một runbook.

### 1.4. Kiểm chứng

Tài liệu không có test, nên bằng chứng phải là **đối chiếu**:

- Với mỗi con số/lệnh bạn viết vào tài liệu, dán **lệnh đọc ra nó** từ hệ thống thật
  (`Select-String scripts/sched.sh ...`, `Get-ScheduledTask ...`, `docker inspect ...`).
- **Không được có con số nào trong tài liệu mà bạn không chỉ được nguồn.**

---

## Task 2 — Viết quy ước `scripts/` xuống

Đợt 53 xác nhận `scripts/` có quy ước đặt tên thật, đã kiểm bằng cách đọc nội dung file chứ không
chỉ đọc tên:

| Tiền tố | Số file | Ý nghĩa |
|---|---|---|
| `.probe_*` | 8 | Dò một câu hỏi vận hành, giữ lại để lặp lại được phép đo |
| `.spike_*` | 12 | Thử nghiệm nghiên cứu, giữ làm bằng chứng cho một kết luận |
| `.repro_*` | 1 | Tái hiện một lỗi cụ thể |
| `.fix_` / `.scan_` | 2 | Công cụ bảo trì |
| không dấu chấm | — | Công cụ vận hành, được `sched.sh`/tests/tài liệu gọi |

Nhưng nó **chưa được viết xuống đâu cả**, nên đợt sau lại có người gọi nó là rác — lần trước
suýt là tôi.

Tạo `scripts/README.md`: một bảng như trên, cộng **một dòng cảnh báo** rút từ chính đợt 53:

> "0 tham chiếu" **không** có nghĩa là bỏ đi được. Phần lớn tham chiếu tới nhóm dấu chấm là
> **chuỗi trong thông báo lỗi** bảo người vận hành phải chạy gì — `grep` thấy chúng nhưng không
> có `import` nào. Ví dụ: `backfill_universe.py` đọc **file JSON**
> `.spike_all_symbols_classified.json`, còn tên script chỉ xuất hiện trong câu thông báo lỗi.

Ngắn thôi — một trang. Đừng liệt kê từng file: danh sách sẽ lỗi thời, quy ước thì không.

---

## 3. Task 3 — Trả lời một câu về thói quen vừa đứt

**Chỉ đọc và trả lời. Không tạo tag, không dựng lại gì.**

Hôm nay collector và engine được dựng lại **bốn lần** mà **không tag `dotNN-rollback-*:pre` lần
nào**, trong khi các đợt trước đều tag. Trả lời ba câu:

1. **Quy trình tag rollback được mô tả ở đâu** trong repo — `DEPLOYMENT.md`, brief cũ, hay không
   ở đâu cả? Nếu không ở đâu cả thì đó chính là lý do nó đứt.
2. **Nếu bản vá đợt 52 hỏng vào thứ Hai, hiện có đường quay về nào?** Nêu chính xác các bước
   bằng thứ đang có trên máy (`dot46`/`dot47` là ảnh của đợt nào, quay về đó mất những gì).
3. **Có đáng tự động hoá việc tag không**, hay tag thủ công trước mỗi lần triển khai là đủ?
   Nêu ý kiến kèm lý do. **Đừng viết script** — chỉ trả lời.

---

## 4. Báo cáo cho Claude

1. `git status --short`, `git diff --stat`.
2. `git diff DEPLOYMENT.md` và nội dung mới của `README_VPS_UBUNTU.md`.
3. Task 1: ba chỗ sửa, ba câu trả lời, và **nguồn cho từng con số**.
4. Task 2: nội dung `scripts/README.md`.
5. Task 3: ba câu trả lời.
6. Một dòng xác nhận: **không đụng code, không xoá gì, không commit, không push.**

Đợt này **không có mốc test** vì không đổi code. Nếu cần chạy `pytest` để trả lời câu nào, cứ
chạy và nói rõ vì sao.

---

## 5. Điều KHÔNG thuộc phạm vi

- **Không sửa code**, `Dockerfile`, `docker-compose.yml`, `scripts/*.py`, `scripts/sched.sh`.
- **Không tạo hay xoá tag image**, không dựng lại container.
- **Không đăng ký hay sửa Scheduled Task** — chỉ đọc để lấy nhịp thật.
- **Không bật `real_trading_enabled`.**
- **Không commit `README.md` gốc** — 253 dòng đổi đang chờ chủ dự án xác nhận, không phải việc
  của đợt này.

---

## 6. Việc của chủ dự án

1. **Hai lệnh Scheduled Task vẫn treo từ đợt 51.** Lệnh thứ hai là việc chặn:
   ```powershell
   Set-ScheduledTask -TaskName "trading-daily-data-check" `
     -Trigger (New-ScheduledTaskTrigger -Daily -At 21:00)
   ```
2. **`powercfg /change standby-timeout-dc 0`** — đợt 52 đã truy ra chắc chắn đây là nguyên nhân
   gốc của backfill chết, không còn là giả thuyết.
3. **Phiên 22/09 là phép đo quyết định của đợt 52**: `logs/bars_closed.log` phải sống qua cuối
   tuần và chứa dòng `bars closed` thật.
4. **`README.md` 253 dòng đổi** — xác nhận nó mô tả đúng ý ông rồi tôi commit.
5. **Diễn tập cửa xác nhận** (script sẵn từ đợt 52). Vẫn là cái chặn go-live kỹ thuật duy nhất
   còn lại.
6. **Ông có nhận được cảnh báo Telegram không?** Hỏi lần thứ năm. Nếu chuỗi đứt ở đoạn cuối thì
   toàn bộ đợt 46–54 không cứu được gì.
7. **Q-1** và **`DELETE` dòng `TEST`** trong `orders`.
