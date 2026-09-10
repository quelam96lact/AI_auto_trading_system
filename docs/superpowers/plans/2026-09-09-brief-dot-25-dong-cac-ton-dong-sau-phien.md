# Brief đợt 25 — Đóng tồn đọng: benchmark, chuông 2C, triển khai, và HII câm

> **ĐÃ BỊ THAY THẾ (10/09/2026) — brief này chưa từng được thực thi.**
> Bốn task dưới đây vẫn còn giá trị nhưng thứ tự ưu tiên đã đổi, vì sáng 10/09 đã xác nhận
> dứt điểm lỗi bar chưa đóng. **Agent phải thực hiện theo bản mới:**
> `2026-09-10-brief-dot-26-sua-bar-chua-dong-va-dong-ton-dong.md`.
> Bản mới trỏ ngược về đây để lấy chi tiết Task 1/2/3/4 (thành Task 4/5/7/6).

Ngày giao: 09/09/2026
Base: `3322aaa` (main). Cây làm việc có `scripts/probe_engine_consumer.py` của đợt 24 (chưa
commit — tôi sẽ commit khi nghiệm thu đợt 24).
Người giao: Claude (planner/auditor).

---

## 0. CỔNG THỜI GIAN — đọc trước tiên

**Đợt 24 đang chạy quan sát trong phiên, tới 15:00 hôm nay.** Brief này **chạm vào hệ thống**
(Task 3 dựng lại container), nên:

> **Không bắt đầu Task 3 trước khi đợt 24 nộp báo cáo và tôi xác nhận đã đóng.**

Task 1, 2, 4 chỉ sửa `trading/backtest.py`, thêm script mới, và đọc DB — **không** restart gì,
nên làm được song song. Nhưng **không chạy `docker compose build/up`** cho tới khi đợt 24 xong.

Nếu bắt đầu sau 15:00 thì cả bốn task đều thoải mái.

---

## 1. Bốn việc, và vì sao đúng bốn việc này

| Task | Việc | Vì sao bây giờ |
|---|---|---|
| 1 | `_buy_and_hold` hỗ trợ khối lượng phân số | Bảng số crypto đợt 23 **không trả lời được câu hỏi quan trọng nhất** vì cột benchmark toàn `+0,00` |
| 2 | Chuông 2C — giám sát engine tiêu thụ bar | Khoảng trống chuông báo mà đợt 24 vừa chứng minh là có thật |
| 3 | Triển khai image mới | Drift **5 giờ 07 phút**, `deploy_drift_check.py` exit 1 |
| 4 | Điều tra HII câm (chỉ đọc, chỉ báo cáo) | Đợt 22 xác nhận HII 0 tín hiệu bull / 3.287 bar dù cổng mở 43,1% |

**Không** gộp thêm việc gì khác. Ba quyết định lớn (Tier 1, Q-2, Q-3), `risk_pct` cho 30x, và
lịch nghỉ lễ đều là **quyết định của chủ dự án**, không phải việc agent.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi.
- **Không gọi SSI, không gọi BingX.**
- `config/config.yaml` **không sửa** (kể cả `holidays` — xem §6).
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 4 chỉ `SELECT`.
- **Không sửa** `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `trading/engine/main.py`, `scripts/heartbeat_check.py` (lý do ở Task 2.2).
- **Không xoá, không sửa** `scripts/probe_engine_consumer.py` của đợt 24 ngoài phần Task 2
  cho phép.
- **Không commit, không push.**
- Phát hiện ngoài phạm vi: **báo cáo, không tự sửa**.
- **Mọi `git diff` trong báo cáo phải copy từ lệnh `git diff`**, không gõ lại. Tôi đối chiếu
  từng dòng ngữ cảnh với file thật.

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_impact` cho `_buy_and_hold`;
`gitnexus_detect_changes()` khi xong. MCP `gitnexus` gần đây hay timeout — **không kết nối
được thì ghi rõ trong báo cáo**, đừng lặng lẽ bỏ qua rồi sửa code.

---

## Task 1 — `_buy_and_hold` hỗ trợ khối lượng phân số

### 1.1. Lỗi

`trading/backtest.py:95`:

```python
qty = int(per_symbol // (buy_price * (1 + fee_rate)))  # phi mua trong gia von
if qty <= 0:
    continue
```

Số nguyên, **không biết `lot_size`**. Với vốn 500 USDT và BTC 62.766:
`int(500 // 62766) = 0` ⇒ `continue` ⇒ benchmark bằng **0,00**.

Hệ quả: cả 8 lượt đo của đợt 23 có cột "PnL Mua-và-Giữ" toàn `+0,00`. Bảng đó **không trả lời
được** câu hỏi quan trọng nhất — chiến lược có thắng nổi việc chỉ mua và giữ không. Ở đợt 21
với vốn 100.000, mua-và-giữ BTC khung 1h là **+15.495 USDT** trong khi mọi chiến lược đều lỗ.

Đây đúng lớp lỗi đã sửa cho `RiskManager` ở đợt 22, chỉ là **hàm benchmark chưa được sửa
theo**.

### 1.2. Việc

Cho `_buy_and_hold` nhận `lot_size` và làm tròn xuống theo bội của nó, **dùng lại đúng cách đã
làm ở `RiskManager.size_buy`** (đợt 22): `math.floor(x / lot_size + 1e-9)` rồi
`round(..., 8)`. Một công thức, một chỗ — không tự chế cách làm tròn thứ hai.

Truyền `lot_size` từ `run_backtest` xuống, và từ `measure_crypto_strategies.py` xuống.
**Mặc định `lot_size = 1`** để mọi phép đo cũ tái lập y nguyên.

### 1.3. Ba tiêu chí

1. **Bất biến VN.** Cổng cứng `-1.615.319.902 | 1.514 lệnh | 439 mã` khớp tuyệt đối. Mọi test
   hiện có xanh **không sửa một dòng test nào**. Phải sửa test ⇒ **dừng, báo cáo**.
2. **Test tái hiện lỗi.** `_buy_and_hold` với `per_symbol=500`, giá 62.766, `lot_size=0.0001`
   phải cho `qty > 0` và PnL ≠ 0. Chạy trên code hiện tại phải **ĐỎ**; chụp `AssertionError`
   dán vào báo cáo trước khi sửa.
3. **Test `lot_size=1` không đổi gì.** Cùng đầu vào, `lot_size=1` cho kết quả y hệt trước khi
   sửa.

### 1.4. Đo lại — làm CUỐI CÙNG trong Task 1

Sau khi ba tiêu chí xanh, chạy lại **đúng 8 lượt của đợt 23** (6 chính + 2 đối chứng, xem
`2026-09-09-brief-dot-23-...md` §2.2) và **ghi đè**
`docs/superpowers/research/2026-09-09-dot-22-do-1h-30x-von-that.md` với số mới có cột
benchmark thật.

**Không sửa code sau khi đã chạy.** Đây là nguyên nhân số đợt 22 không tái lập được.

Kiểm chứng: mọi cột "PnL Mua-và-Giữ" phải **khác 0**. Còn `+0,00` ⇒ chưa sửa xong.

---

## Task 2 — Chuông 2C: engine có đang tiêu thụ bar không

### 2.1. Khoảng trống

Đợt 24 xác nhận: `storage.beat("engine")` nằm trong `idle_maintenance()`
(`engine/main.py:340-344`) nên chạy **theo nhịp thời gian**; chuông 2A giám sát bar trong DB
tức **đầu ra của collector**. Nếu đường NATS → engine đứt thì **cả hai chuông đều xanh** trong
khi engine không giao dịch gì.

### 2.2. Phải là script RIÊNG, không nhét vào `heartbeat_check.py`

Docstring `scripts/deploy_drift_check.py` đã ghi rõ bài học `51ff6de`:

> "KHÔNG thêm vào heartbeat_check.py — chuông đó chỉ được phụ thuộc DB + config; docker/git là
> mở rộng bề mặt phụ thuộc của chính cái chuông báo. **Một phụ thuộc mới là một cách mới để
> chuông chết câm.**"

NATS là một phụ thuộc mới. Vậy 2C đi theo đúng khuôn `deploy_drift_check.py` /
`docker_down_alert.py`: **file riêng, hỏng thì không kéo theo gì**.

Tạo `scripts/engine_consumer_check.py`. **Không sửa `heartbeat_check.py`.**

### 2.3. Logic

Dùng lại phần đọc của `scripts/probe_engine_consumer.py` (đợt 24) —
`js.consumer_info("BARS", "engine")`. Được phép **tách phần đọc đó thành hàm dùng chung** để
hai script không chép nhau, nhưng **không đổi hành vi** của probe.

Cảnh báo khi **cả ba** điều kiện cùng đúng (để không kêu oan ngoài phiên):

1. Đang trong giờ giao dịch — dùng `trading.calendar_vn.is_trading_time`, truyền `holidays` từ
   config như các chuông khác.
2. `num_pending` vượt ngưỡng, **hoặc** `delivered.stream_seq` **không đổi** so với lần chạy
   trước trong khi số bar trong DB **đã tăng**.
3. Đã qua thời gian chống spam.

Ngưỡng và cách nhớ lần chạy trước: agent chọn, nhưng **phải đơn giản** và ghi rõ lý do trong
docstring. Gợi ý: ghi lần chạy trước ra một file trong `logs/` như
`logs/.docker_down_last_alert` đang làm — **không** tạo bảng DB mới.

Exit code theo đúng khuôn hiện có: `0` = ổn, `1` = đã gửi cảnh báo, `2` = sai cấu hình.

### 2.4. Ràng buộc an toàn — nhắc lại vì đây là NATS

**Chỉ đọc.** Cấm `delete`, `purge`, `add_consumer`, `update_consumer`, `publish`, `subscribe`.
Sự cố **13/08**: suite test đã xoá durable consumer của engine thật, purge stream `BARS`, ghi
đè `engine_state`. Agent phải `grep` file mình vừa viết và dán kết quả chứng minh sạch.

### 2.5. Test

- Consumer khoẻ (`num_pending=0`, seq tiến) ⇒ exit 0, không gửi gì.
- `num_pending` vượt ngưỡng **trong giờ giao dịch** ⇒ exit 1, có gọi gửi cảnh báo.
- Cùng tình huống nhưng **ngoài giờ giao dịch** ⇒ exit 0, **không** gửi.
- Không kết nối được NATS ⇒ exit 2 hoặc 1 (agent chọn, ghi rõ), **không** crash không thông báo.

Test dùng mock, **không kết nối NATS thật trong `pytest`**.

### 2.6. KHÔNG làm trong đợt này

Không tạo scheduled task Windows, không sửa `sched.sh`. Đưa chuông vào lịch chạy là việc vận
hành của chủ dự án, sau khi script đã có test.

---

## Task 3 — Triển khai image mới (SAU khi đợt 24 đóng)

### 3.1. Hiện trạng

`deploy_drift_check.py` exit **1**: image đang chạy `41371bc92882` build **08/09 21:38**, cũ
hơn commit gần nhất chạm `trading/` **5 giờ 07 phút**. Thay đổi chưa được triển khai:
`trading/risk.py` (phân số + đòn bẩy), `trading/backtest.py` (thanh lý), `Dockerfile` (`/app`
thuộc `appuser`), cộng Task 1 của đợt này.

**Rủi ro thấp:** cổng cứng VN đã chứng minh hành vi chứng khoán VN không đổi (`leverage` mặc
định `1.0`, `lot_size` mặc định `100`). Nhưng drift vẫn phải đóng.

### 3.2. Làm đúng khuôn đợt 20 Task 5

1. **Cổng thời gian:** ngoài 08:45–15:15 ngày làm việc. Chạy
   `Get-Date -Format "yyyy-MM-dd HH:mm:ss dddd"`, chép vào báo cáo. Rơi vào cửa sổ cấm ⇒
   **dừng, nộp Task 1/2/4, để Task 3 lần sau**.
2. **Gắn nhãn lùi trước khi ghi đè:**
   ```powershell
   docker tag ai_auto_trading_system-collector:latest dot25-rollback-collector:pre
   docker tag ai_auto_trading_system-engine:latest    dot25-rollback-engine:pre
   ```
   Kiểm image ID phải là `41371bc92882` / `93aed2cfc8f7`. Khác ⇒ **dừng, báo cáo**.
3. `docker compose build collector engine`
4. `docker compose up -d --no-deps collector engine` — **đúng một lần**.
5. Chờ **90 giây**, rồi kiểm ba thứ:
   - `uv run python scripts/deploy_drift_check.py` ⇒ **exit 0**.
   - `docker logs --tail 40` cho cả hai container.
   - `uv run python scripts/heartbeat_check.py` (cần `DB_DSN` trong môi trường) ⇒ exit 0.

**Đọc trước khi hoảng:** log engine có thể xuất hiện `psycopg_pool.PoolTimeout` lúc khởi động
rồi tự hồi phục. Đây là hiện tượng **có từ trước**. Nếu theo sau là dòng
`engine restored state` thì hệ thống khoẻ — báo cáo, **đừng lùi image**. Chỉ coi là hỏng khi
**không** có dòng đó.

**Restart đúng một lần.** Container không lên ⇒ lùi bằng `dot25-rollback-*:pre` rồi
`up -d --no-deps` (lần thứ hai duy nhất được phép, chỉ để lùi), sau đó **dừng hẳn**, báo cáo.
Collector gọi SSI mỗi vòng — restart lặp là cách nhanh nhất ăn 429 và hỏng token cả ba tài
khoản.

---

## Task 4 — Vì sao HII câm: điều tra, CHỈ ĐỌC, CHỈ BÁO CÁO

### 4.1. Hiện trạng

`scripts/check_silent_engine.py` (đợt 22) cho:

```
HII | 3,287 bar | BQ 81,580,388 đ | cổng mở 1,418 bar (43.1%) | 0 bull / 0 bear | [WARN_NO_BULL]
IJC | 4,805 bar | cổng mở 81.2% | 6 bull | [OK]
AAA | 4,684 bar | cổng mở 80.9% | 6 bull | [OK]
```

Cổng thanh khoản của HII **mở 43,1%** — nên đây **không** phải lỗi đơn vị thanh khoản (gói K
06/09 đã sửa cái đó). Nguyên nhân nằm ở **điều kiện tín hiệu**, chưa ai truy ra.

### 4.2. Việc

Trên 1.418 bar mà cổng HII **đang mở**, đếm xem **tầng nào của `octopus_pullback` chặn**. Bốn
tầng (xem `trading/strategies/octopus_pullback.py`):

| Tầng | Đếm |
|---|---|
| Xu hướng: `close > EMA200` và `close > MA20` | bao nhiêu bar đạt |
| Nhịp hồi: ≥2 nến đỏ trong 5 phiên trước | bao nhiêu bar đạt |
| Đảo chiều: nến xanh + `EMA9 > EMA21` | bao nhiêu bar đạt |
| MACD hist > 0 | bao nhiêu bar đạt |

Viết script **chỉ đọc** `scripts/.probe_hii_silent.py` (tiền tố `.` theo đúng quy ước probe
sẵn có trong `scripts/`). Đọc `bars` từ DB, dùng lại chính lớp chiến lược — **không chép lại
công thức**, không sửa `trading/strategies/*`.

Làm cùng phép đếm cho **IJC** để có mốc so sánh: tầng nào ở HII rơi mạnh hơn IJC.

### 4.3. Kiểm chứng

- Bảng 4 tầng × 2 mã (HII, IJC), số bar đạt từng tầng và tỷ lệ.
- Nêu **tầng nào là nút thắt** của HII, kèm số.
- **Không đề xuất sửa chiến lược.** Sửa hay không là quyết định của chủ dự án, và nó dính tới
  Tier 1 đang treo.
- `git diff` cho `trading/` (ngoài `backtest.py` của Task 1) phải **rỗng**.

---

## 3. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Task 1: phải sửa test cũ mới xanh | Ngay |
| Task 1: cổng cứng VN lệch một chữ số | Ngay |
| Task 1: test tiêu chí 2 không ĐỎ trên code hiện tại | Ngay — test chưa tái hiện đúng lỗi |
| Task 1: sau khi đo lại vẫn còn cột benchmark `+0,00` | Ngay |
| Phải sửa code sau khi đã chạy phép đo Task 1.4 | Chạy lại **cả 8 lượt** |
| Task 2: cần sửa `heartbeat_check.py` | Ngay — xem 2.2 |
| Task 2: cần gọi hàm NATS có tác dụng phụ | Ngay |
| Task 3: đợt 24 chưa đóng | Không được bắt đầu Task 3 |
| Task 3: cổng thời gian rơi vào 08:45–15:15 | Hoãn Task 3 |
| Task 3: image ID không khớp `41371bc92882`/`93aed2cfc8f7` | Ngay |
| Task 3: container không lên | Lùi, rồi dừng hẳn |
| Task 4: cần sửa `trading/strategies/*` | Ngay |
| Cần gọi SSI hoặc BingX | Ngay |

---

## 4. Báo cáo nghiệm thu — đúng 7 mục

1. `gitnexus_impact` cho `_buy_and_hold` (hoặc ghi rõ MCP hỏng).
2. Task 1: `AssertionError` trên code chưa sửa + `git diff` copy nguyên văn + 3 tiêu chí +
   cổng cứng VN.
3. Task 1.4: output nguyên văn 8 lượt, **chỉ rõ cột benchmark giờ khác 0**.
4. Task 2: nội dung script + `grep` chứng minh chỉ đọc + 4 test + pytest/ruff.
5. Task 3: `Get-Date` + nhãn lùi + build + `docker ps` + `deploy_drift_check` exit 0 +
   `heartbeat_check` exit + log hai container.
6. Task 4: bảng 4 tầng × 2 mã + nút thắt của HII.
7. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`, `uv run pytest -q`,
   `uv run ruff check trading tests scripts`.

Kỳ vọng mục 7: `trading/backtest.py`, `scripts/measure_crypto_strategies.py`,
`scripts/engine_consumer_check.py` (mới), `scripts/.probe_hii_silent.py` (mới),
`scripts/probe_engine_consumer.py` (đợt 24, có thể đổi nếu tách hàm dùng chung), file test
mới, file báo cáo đã ghi đè, cộng `AGENTS.md`/`CLAUDE.md`. **Không** `config/config.yaml`,
**không** `trading/risk.py`, **không** `trading/engine/main.py`, **không**
`scripts/heartbeat_check.py`.

---

## 5. Việc KHÔNG thuộc đợt này

- **Không** viết đường đặt lệnh BingX.
- **Không** mô hình hoá funding.
- **Không** sửa chiến lược dù Task 4 tìm ra nút thắt.
- **Không** đưa chuông 2C vào lịch chạy (Task 2.6).
- **Không** điền `holidays`.
- **Không** đổi `risk_pct`.

---

## 6. Việc của chủ dự án, không giao được

Ghi lại để không trôi:

| Mã | Việc | Vì sao không giao |
|---|---|---|
| **Q-1** | Tier 1 — chiến lược không có edge đo được | Quyết định |
| **Q-2** | `real_order_account` 0434221 rỗng, tiền ở 0434226; `symbols` lệch danh mục thật | Quyết định |
| **Q-3** | Mô hình xác nhận lệnh + vòng đối soát | Quyết định |
| **Q-5** | Lịch nghỉ lễ — 10/13 ngày chưa khai báo | Dữ kiện pháp lý, agent đoán sai thì hoặc chuông kêu oan, hoặc bịt chuông vào ngày thật sự có giao dịch. Bằng chứng ba nguồn cho `2026-01-02` đã có ở đợt 23 |
| **Q-7** | `risk_pct` cho đòn bẩy 30x | Đợt 23 chứng minh 30x gần như vô tác dụng vì mô hình ATR chặn ở ~1x. Muốn dùng 30x thật phải nâng `risk_pct` lên ~25–30%, và ở mức đó một cú ngược bằng một ATR ăn phần lớn tài khoản |
| — | Scheduled task cho chuông 2C | Vận hành |
| — | Docker tự khởi động cùng Windows | Vận hành |
| — | VPS Ubuntu | Quyết định |
