# Brief đợt 53 — Dọn rác codebase và kiểm định image trước go-live

Ngày giao: 18/09/2026 (tối).
Base: `eec6975` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Luật xuyên suốt đợt này

**Đếm tham chiếu trước khi gọi bất cứ thứ gì là rác.**

Tôi khảo sát trước khi viết brief, và hai lần suýt xếp nhầm thứ đang được dùng vào loại bỏ đi:

```
$ Select-String scripts/sched.sh tests/*.py -Pattern "spike_"
10 tham chieu            <- script "spike" KHONG phai deu la mo coi

$ Select-String Dockerfile docs/*.md *.md -Pattern "PLAN_INDEX_STREAMING"
Dockerfile:9             <- comment giai thich VI SAO dung uv.lock
DEPLOYMENT.md:26, :476
GO_LIVE_AUDIT.md:452, :460
README_VPS_UBUNTU.md:192
```

`docs/plans-legacy/` trông như thư mục chết. Nó **không** chết: chính `Dockerfile` trỏ vào đó để
giải thích vì sao build phải dùng `uv.lock`. Xoá nó là làm mù một quyết định kiến trúc.

Nên đợt này: **agent không xoá bất cứ thứ gì.** Đo, đếm tham chiếu, phân loại, soạn lệnh. Việc
xoá là của tôi sau khi đọc báo cáo.

### 0.1. Những gì tôi đã đo

| Hạng mục | Số đo | Nguồn |
|---|---|---|
| Image production | `collector` **228MB**, `engine` **228MB** | `docker images` |
| Tag rollback tồn đọng | **14 tag**, đợt 20 → 47, 227–366MB/tag | `docker images` |
| Build cache | **514MB** (99,82MB thu hồi được) | `docker system df` |
| Bảng dữ liệu crypto | **~167MB** (`bars_crypto` 114MB, `binance_metrics` 44MB, `binance_klines` 5,2MB, `binance_orderflow_1h` 3,7MB, `binance_funding` 0,5MB) | `pg_total_relation_size` |
| Module nghiên cứu trong `trading/` | `perp_backtest` 28,9KB, `cross_sectional` 13,1KB, `feature_panel` 10,4KB, `metrics` 5,7KB — **0 nơi production import** | grep import |
| Cây làm việc bẩn | 3 file `.md` sửa chưa commit (README **+188/−65**), 3 file chưa theo dõi | `git status` |
| Script dấu chấm / spike | 23 + 14 | `scripts/` |

### 0.2. Một điều tôi phải nói trước để không ai kỳ vọng sai

`perp_backtest + cross_sectional + feature_panel + metrics` = **58,1KB** trên tổng **383KB** của
`trading/`. Trên một image **228MB**, dọn hết chúng đi tiết kiệm **gần như bằng không**.

Nên **đừng** làm việc này vì dung lượng. Nếu có lý do thì lý do là **phạm vi ảnh hưởng**: mã
nghiên cứu nằm trong cùng gói với mã chạy tiền thật, nên mọi thay đổi ở đó đều lọt vào image
production và làm `deploy-drift` kêu. Đó là một lập luận thật nhưng **nhỏ**, và tôi nói rõ nó nhỏ.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `docs/superpowers/research/2026-09-18-dot-53-*.md` | **mới** | báo cáo |

**Đợt này không sửa một dòng code nào.** Nếu bạn thấy mình đang gõ code: dừng lại, đọc lại brief.

Ràng buộc chung: **KHÔNG xoá file, KHÔNG xoá image, KHÔNG `docker prune`, KHÔNG `git checkout`/
`git restore`/`git clean`** — mọi thao tác huỷ đều soạn lệnh rồi dừng. `real_trading_enabled` giữ
`false`; không sửa `config/config.yaml`; không gọi SSI/BingX; không in secret; `.env` không sửa,
không commit, **không mở**; **chỉ đọc DB**; **không** `delete`/`purge`/`add`/`update` stream hay
consumer NATS nào; **không dựng lại container** (đợt 52 vừa triển khai xong, để yên); **không
commit, không push**. Mọi truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`. Output
copy từ terminal, thiếu thì ghi **"CHƯA LÀM"**, **không bịa** — đợt 52 có hai dòng kiểm chứng
không phải output thật, đừng lặp lại.

---

## Task 1 — Cây làm việc bẩn: nó là gì, và ai làm ra nó?

Sáu mục dưới đây đã nằm trong cây làm việc suốt nhiều phiên mà chưa ai quyết:

```
 M AGENTS.md                                                    (2 dong)
 M CLAUDE.md                                                    (2 dong)
 M README.md                                                    (+188 / -65)
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"   (goc repo)
?? docs/README_VPS_UBUNTU.md                                    (7,3KB, sua 12/09)
?? docs/superpowers/research/2026-09-18-dot-47-...md             (7,4KB, sua 18/09 16:34)
```

Với **từng mục**, trả lời:

1. **Nội dung đổi cái gì** — dán `git diff` cho ba file đã sửa. `README.md` đổi 253 dòng, nói rõ
   nó nói thêm/bớt điều gì về cách vận hành hệ thống.
2. **Nó còn đúng không** so với trạng thái hôm nay (sau đợt 46–52)? Đây mới là câu quan trọng.
   Một README mô tả sai cách hệ thống chạy còn tệ hơn không có README.
3. **Xếp loại**: `GIỮ VÀ COMMIT` / `BỎ` / `CẦN CHỦ DỰ ÁN QUYẾT`.

Chú ý riêng hai file:

- **`docs/README_VPS_UBUNTU.md`** liên quan trực tiếp tới việc **chuyển VPS** đang treo trong
  danh sách của chủ dự án. Đọc kỹ: nội dung của nó có còn khớp kiến trúc hiện tại không
  (`./logs:/app/logs` mới thêm ở đợt 52, bảy job trong `sched.sh`, `run_hidden.vbs` chỉ chạy trên
  Windows)? Nêu rõ **chỗ nào cần sửa trước khi ai đó làm theo**. Đừng sửa — liệt kê.
- **File `.md` ở gốc repo** là tài liệu nguồn của loạt nghiên cứu crypto (đợt 37–44, tám kết quả
  âm). Nó có nên nằm ở gốc repo không, hay thuộc `docs/`?

**Không chạy `git add`, `git checkout`, `git restore`, `git clean`.** Phân loại rồi dừng.

---

## Task 2 — Image production đã sẵn sàng đưa ra máy lạ chưa?

Sắp chuyển VPS. Trước khi image này chạy trên một máy không phải máy chủ dự án, phải biết chắc
nó mang theo những gì.

Tôi đã kiểm bốn điều và **cả bốn đều đạt** — việc của bạn là **kiểm chứng lại độc lập** (đừng
chép số của tôi) rồi làm tiếp phần còn thiếu:

```
$ docker exec ...-collector-1 sh -c "ls /app; id; ls -la /app/.env"
config  logs  trading
uid=10001(appuser) gid=10001(appuser)
ls: cannot access '/app/.env': No such file or directory
```

Phần còn thiếu, trả lời bằng bằng chứng từ **chính image đang chạy**, không phải từ `.dockerignore`:

1. **Có file nào chứa secret lọt vào image không?** Tìm trong `/app` các chuỗi có hình dạng token
   / khoá riêng. **Báo cáo phải nói "có/không" và cách tìm — TUYỆT ĐỐI không in nội dung tìm
   thấy.** Nếu tìm thấy gì: dừng ngay, báo một dòng, không dán.
2. **`tests/`, `docs/`, `.git/` có lọt vào không?**
3. **Dependency có bị ghim không?** `uv.lock` quyết định, nhưng kiểm trong image: liệt kê vài gói
   cốt lõi (`ssi-sdk`, `psycopg`, `nats-py`) kèm phiên bản thật đang cài.
4. **Image chạy được khi không có `./logs` trên máy đích không?** Đợt 52 thêm mount `./logs:/app/logs`.
   Trên VPS mới, thư mục đó chưa tồn tại. Đọc code và trả lời: collector sẽ **chết**, **cảnh báo**,
   hay **chạy tiếp im lặng**? Đây là câu có hậu quả thật cho ngày chuyển VPS.
5. **`CMD` và `WORKDIR`** có đúng như Dockerfile mô tả không? Dockerfile có ghi chú rằng `WORKDIR`
   **phải** là `/app` vì `trading` được cài editable — xác nhận điều đó đúng trong image thật.

Kết luận một trong hai: **SẴN SÀNG ĐƯA RA MÁY LẠ** hoặc **CHƯA**, kèm danh sách phải sửa.

---

## Task 3 — 14 tag rollback và 514MB build cache

```
dot20-rollback-collector:pre   366MB   12 ngay
dot20-rollback-engine:pre      366MB   12 ngay
dot22-test:new                 227MB    9 ngay
dot25-rollback-{collector,engine}:pre   227MB   9 ngay
dot29-rollback-{collector,engine}:pre   227MB   8 ngay
dot34-rollback-{collector,engine}:pre   227MB   8 ngay
dot36-rollback-{collector,engine}:pre   227MB   7 ngay
dot44-rollback-collector:pre   227MB    7 ngay
dot46-rollback-collector:pre   228MB    4 ngay
dot47-rollback-collector:pre   228MB    4 ngay
```

### 3.1. Đo thật, đừng nhân

`docker system df` nói tổng 3,071GB nhưng **chỉ 4,991MB thu hồi được**. Lý do: các image này
**dùng chung layer**. Nhân 14 × 228MB rồi hứa "tiết kiệm 3GB" là sai.

Đo cho đúng:

1. `docker system df -v` để thấy dung lượng **thực sự riêng** của từng image.
2. Nêu con số **sẽ thu hồi được thật** nếu xoá các tag đề xuất — và nói rõ bạn suy ra nó bằng cách
   nào. Nếu không đo được chính xác: ghi **"CHƯA ĐỦ DỮ LIỆU"** kèm lý do, đừng ước lượng bừa.

### 3.2. Giữ cái nào

Tag rollback tồn tại để quay về khi một lần triển khai hỏng. Đề xuất một **luật giữ** rõ ràng
(ví dụ: giữ N tag gần nhất, hoặc giữ tag của lần triển khai đang chạy) và **nêu lý do**, rồi áp
luật đó vào danh sách trên.

Trả lời thêm hai câu:

- **`dot20-*` nặng 366MB còn các tag sau chỉ 227MB — vì sao?** Nếu vì base image đổi, nói rõ đổi gì.
- **`dot22-test:new` có phải tag rollback không**, hay là thứ khác lạc vào?

### 3.3. Soạn lệnh, đừng chạy

Soạn lệnh `docker rmi` cho đúng danh sách đề xuất, và lệnh dọn build cache. **Không chạy.**
Nêu rõ lệnh nào không thể hoàn tác.

**Cảnh báo:** `docker system prune -a` sẽ xoá cả image đang dùng bởi container đã dừng và mọi
tag rollback. **Không đề xuất lệnh đó.**

---

## Task 4 — Kiểm kê rác bằng tham chiếu, không bằng cảm giác

### 4.1. Script

`scripts/` có **23 file dấu chấm** và **14 file `spike_*`**. Với mỗi file, đếm tham chiếu từ:
`scripts/sched.sh`, `tests/`, `trading/`, `docs/`, và các script khác.

Trả về **một bảng**: tên file → số tham chiếu → nguồn tham chiếu → xếp loại
(`ĐANG DÙNG` / `MỒ CÔI` / `CẦN NGƯỜI QUYẾT`).

Tôi đã đếm được **10 tham chiếu tới `spike_`** từ `sched.sh` và `tests/` — nên **danh sách mồ côi
chắc chắn ngắn hơn bạn tưởng**. Nếu bảng của bạn cho ra "tất cả đều mồ côi", bạn đã đếm sai.

### 4.2. Module nghiên cứu trong `trading/`

Bốn module `perp_backtest`, `cross_sectional`, `feature_panel`, `metrics` có **0 nơi production
import**. Nhưng chúng **được `scripts/` và `tests/` dùng**, nên chúng **không phải code chết** —
chúng là code nghiên cứu nằm nhầm chỗ.

Trả lời: **có đáng tách chúng ra khỏi gói `trading` không?** Cân nhắc rõ hai phía:

- **Lợi:** thay đổi mã nghiên cứu không còn làm image production lệch, `deploy-drift` bớt kêu oan.
- **Hại:** `Dockerfile` ghi rõ `trading` được cài **editable** và `__editable__.trading-0.1.0.pth`
  trỏ cứng vào `/app/trading`; đổi cấu trúc gói là đụng vào đường nhập khẩu của **mọi thứ**.
  Và lợi ích dung lượng là **58KB trên 228MB — bằng không**.

Tôi nghiêng về **không làm**, nhưng muốn nghe lập luận của bạn dựa trên code. Nếu bạn cũng kết
luận không làm: nói thẳng "không đáng", đó là một kết luận hợp lệ và tôi muốn nó được ghi lại.

### 4.3. 167MB dữ liệu crypto trong DB production

```
bars_crypto           114 MB
binance_metrics        44 MB
binance_klines        5160 kB
binance_orderflow_1h  3656 kB
binance_funding        488 kB
```

Đây là dữ liệu của loạt nghiên cứu đợt 37–44 — **tám kết quả âm, 2026 đã niêm phong**.

**Không xoá. Không `DROP`. Không `TRUNCATE`.** Ràng buộc này tuyệt đối.

Việc của bạn là trả lời để chủ dự án quyết:

1. **Còn thứ gì đang đọc các bảng này không?** Đếm tham chiếu trong `trading/`, `scripts/`, `tests/`,
   `grafana/`.
2. **Nếu muốn giữ mà không chiếm chỗ trong DB production, đường nào rẻ nhất?** Xuất ra file rồi
   mới xoá là một đường — nêu lệnh xuất, kích thước ước tính, và **cách kiểm chứng bản xuất đọc
   lại được** trước khi bất kỳ ai xoá gì.
3. **167MB có thật sự là vấn đề không?** Nói thẳng. Nếu câu trả lời là "không, DB còn thừa chỗ,
   để đó rẻ hơn rủi ro xoá" thì đó là kết luận đúng và tôi muốn nghe.

---

## 2. Báo cáo cho Claude

1. `git status --short` (kỳ vọng **không đổi** so với lúc bắt đầu — bạn không sửa gì).
2. Task 1: ba `git diff` + bảng phân loại sáu mục.
3. Task 2: năm câu trả lời kèm output thật từ image; kết luận hai lựa chọn.
4. Task 3: số thu hồi thật, luật giữ kèm lý do, hai câu hỏi phụ, lệnh soạn sẵn.
5. Task 4: bảng script, lập luận về bốn module, ba câu trả lời về dữ liệu crypto.
6. Một dòng xác nhận: **không xoá gì, không commit, không push, không dựng lại container.**

Đợt này **không có mốc test** vì không đổi code. Nếu bạn thấy cần chạy `pytest` để trả lời câu
nào, cứ chạy và nói rõ vì sao — nhưng đừng chạy chỉ để báo cáo có số.

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không xoá file, image, layer, cache, bảng, dòng DB nào.** Soạn lệnh rồi dừng.
- **Không `git add` / `checkout` / `restore` / `clean` / `stash`.**
- **Không sửa code, không sửa `docker-compose.yml`, không sửa `Dockerfile`.**
- **Không dựng lại container** — đợt 52 vừa triển khai, để yên tới thứ Hai.
- **Không bật `real_trading_enabled`.**
- **Không in nội dung bất kỳ thứ gì trông giống secret**, kể cả để chứng minh là đã tìm.

---

## 4. Việc của chủ dự án

1. **Hai lệnh Scheduled Task còn treo từ đợt 51** — lệnh thứ hai (dời `daily-data-check` sang
   21:00) vẫn là việc chặn: không có nó thì bản vá vẫn không kêu được.
2. **Phiên 22/09 là phép đo quyết định của đợt 52**: `logs/bars_closed.log` phải sống qua cuối
   tuần và chứa dòng `bars closed` thật. Hôm nay mới chứng minh được cơ chế, chưa chứng minh
   được nội dung.
3. **`powercfg /change standby-timeout-dc 0`.** Đợt 52 đã truy ra chắc chắn: máy gập lúc 20:21,
   thức tạm 20:40:45, ngủ lại 20:40:56 và giết tiến trình backfill. Đây **là** nguyên nhân gốc,
   không còn là giả thuyết.
4. **Chuyển VPS** — đọc kết luận Task 1 về `README_VPS_UBUNTU.md` và Task 2 câu 4 trước khi làm.
5. **Diễn tập cửa xác nhận** (script đã sẵn từ đợt 52). Vẫn là cái chặn go-live kỹ thuật duy nhất
   còn lại.
6. **Ông có nhận được cảnh báo Telegram không?** Câu này đã hỏi ba đợt liền và chưa có lời đáp.
   Nếu chuỗi cảnh báo đứt ở đoạn cuối thì toàn bộ công việc đợt 46–53 không cứu được gì.
7. **Q-1** và **`DELETE` dòng `TEST`** trong `orders`.
