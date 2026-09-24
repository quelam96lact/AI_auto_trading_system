# Brief đợt 86 — Triển khai đợt 81/83/84 lên container, sau khi phiên 24/09 đóng

Ngày giao: 24/09/2026. **Chỉ bắt đầu từ 15:15 giờ VN.**
Base: main `f3a4bf0`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao cần, và vì sao phải đợi tới 15:15

Cổng go-live đang **[CHẶN]** ở tiêu chí 8:

```
8 | Lệch triển khai | LỆCH / LỖI | [CHẶN] | collector: image CŨ hơn commit gần nhất chạm trading/ ...
                                              engine: image CŨ hơn commit gần nhất chạm trading/ ...
```

Ba commit đã chạm `trading/` nhưng chưa có trong container đang chạy:

| Commit | Nội dung | Ảnh hưởng runtime |
|---|---|---|
| `41acd82` (đợt 81) | engine chờ đủ dữ liệu rồi mới warm-up | **engine** |
| `6f83e03` (đợt 83) | `trading/derivative_series.py` | không (chỉ script dùng) |
| `1095c37` (đợt 84) | `db.py` thêm `read/write_derivative_bars`; `schema.sql` thêm bảng `bars_derivative` | **cả collector lẫn engine** (cùng import `db.py`) |

`schema.sql` dùng `CREATE TABLE IF NOT EXISTS` và bảng `bars_derivative` **đã có sẵn** trong DB (đợt 84
đã tạo) → khởi động lại sẽ **không** đụng dữ liệu.

**Vì sao 15:15:**
- Phiên đóng 14:45. Khởi động lại engine giữa phiên tạo lỗ warm-up — và vòng chờ đợt 81 **không** vá
  được ca giữa phiên (đã ghi nhận).
- Tác vụ Windows `trading-stream-health` chạy **15:10** để đo độ phủ luồng phiên hôm nay. Để nó chạy
  xong trên collector cũ, **rồi** mới đụng tới container.
- Cổng go-live chỉ coi phiên hôm nay là "hoàn tất" cho tiêu chí 6 từ **15:25**
  (`STREAM_COVERAGE_READY_TIME`, đợt 80). Bước chạy cổng ở cuối phải làm **sau 15:25**.

---

## 1. Ràng buộc

- **Chỉ** đụng hai service `collector` và `engine`. **Không** restart/stop `postgres`, `nats`,
  `nats-test`, `grafana`.
- **Không** sửa code, config, hay dữ liệu DB. Đây là brief **vận hành**, không phải brief code.
- **Không** đặt lệnh.
- Không commit, không push.
- Gặp bất kỳ điều kiện dừng nào ở mục 3 → **rollback theo mục 4, rồi báo cáo**. Không tự "sửa cho chạy".

---

## 2. Các bước — làm đúng thứ tự, dán nguyên văn output từng bước

### Bước 0 — Điều kiện tiên quyết. Thiếu một cái → DỪNG, không làm tiếp.

1. `Get-Date` — phải **≥ 15:15** giờ VN ngày 24/09/2026.
2. `Get-Content logs\stream-health.log -Tail 4` — phải có dòng `2026-09-24 15:10:... stream-health start`
   và dòng kết quả của phiên 24/09 ngay sau. Chưa có → job chưa chạy → **đợi, không làm tiếp**.
3. `git log --oneline -1` — phải là `f3a4bf0` (hoặc mới hơn nhưng **chỉ** khác ở `docs/`).
4. `git status --short trading/` — phải **rỗng**. Có thay đổi chưa commit trong `trading/` → DỪNG
   (build sẽ đóng gói code chưa được audit).

### Bước 1 — Ghi lại trạng thái trước

```powershell
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}}" | Select-String ai_auto_trading_system
docker ps --format "{{.Names}} {{.Image}} {{.Status}}"
```

Kỳ vọng: `collector:latest` = **`214acb385930`**, `engine:latest` = **`f57d9de184aa`** (tôi đo lúc 12:43).
Khác → ghi lại con số thật và báo, nhưng vẫn làm tiếp nếu Bước 0 đạt.

### Bước 2 — Đặt điểm rollback

```powershell
docker tag ai_auto_trading_system-collector:latest ai_auto_trading_system-collector:previous
docker tag ai_auto_trading_system-engine:latest    ai_auto_trading_system-engine:previous
```

Kiểm: `:previous` giờ phải mang **đúng ID** của `:latest` ở Bước 1. Không khớp → DỪNG (chưa có đường lui).

### Bước 3 — Build và khởi động

```powershell
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

### Bước 4 — Kiểm lớp 1: container đang chạy image MỚI

1. `docker images ...` như Bước 1 — `:latest` của cả hai phải có **ID mới, khác** Bước 1.
2. `docker ps --format "{{.Names}} {{.Image}} {{.Status}}"` — collector và engine `Up` vài giây/phút;
   **postgres/nats/grafana vẫn giữ uptime cũ** (bằng chứng không đụng nhầm).
3. `docker inspect ai_auto_trading_system-engine-1 --format "{{.Image}}"` (và collector) — phải trùng ID
   mới.

### Bước 5 — Kiểm lớp 2: code mới THẬT SỰ nằm trong container

Image mới chưa chắc chứa code mới (cache build). Kiểm trực tiếp bên trong:

```powershell
docker exec ai_auto_trading_system-engine-1    grep -c "def last_session_date_needed" /app/trading/engine/main.py
docker exec ai_auto_trading_system-engine-1    grep -c "SESSION_DATA_READY_TIME" /app/trading/engine/main.py
docker exec ai_auto_trading_system-engine-1    grep -c "def write_derivative_bars" /app/trading/storage/db.py
docker exec ai_auto_trading_system-collector-1 grep -c "def write_derivative_bars" /app/trading/storage/db.py
```

Mỗi lệnh phải ra **≥ 1**. Ra 0 → DỪNG, rollback.

**Bằng chứng đây là phép kiểm phân biệt được thật, không phải thủ tục:** lúc 12:4x tôi đã chạy đúng lệnh
này trên container **cũ** — `last_session_date_needed` ra **0**, còn `count_warmup_gap` (đợt 74) ra **1**.
Đường dẫn `/app/trading` đã xác nhận qua `Dockerfile` (`WORKDIR /app`, `COPY ... /app/trading`). Nên sau
triển khai, con số phải đổi từ **0 → ≥1**; vẫn 0 nghĩa là build dùng cache cũ.

### Bước 6 — Kiểm hành vi: lần chạy thật đầu tiên của vòng chờ đợt 81

Đọc `logs\engine_alerts.log`, **chỉ các dòng sau thời điểm khởi động lại**:

1. `engine restored state` → `positions` phải đúng **`{"IJC": 400, "AAA": 400}`**.
2. Ba dòng `warm-up ... xong` → `until` phải là **`2026-09-24 07:45:00+00:00`** (= 24/09 14:45 VN) cho
   **cả ba** mã.
3. **Kỳ vọng KHÔNG có** dòng `da co du lieu bars cho phien gan nhat sau khi cho` và **KHÔNG có** dòng
   CRITICAL `het thoi gian cho du lieu bars`. Lý do: khởi động sau 15:00 thì `needed_date` = 24/09, mà
   nến 24/09 đã được collector ghi trực tiếp suốt phiên → vòng chờ phải thoát ngay lập tức.
   **Nếu có một trong hai dòng đó, báo nguyên văn** — đó là phát hiện, không tự giải thích.
4. **Không** có dòng `GAP-1` nào (chưa có nến live nào sau warm-up vì đã ngoài giờ).

### Bước 7 — Kiểm collector không làm nhiễm lại `bars`

```sql
SELECT count(DISTINCT symbol) FROM bars;                                   -- kỳ vọng 339
SELECT count(DISTINCT symbol) FROM bars WHERE symbol LIKE '41I%' OR symbol LIKE 'VN30F%';  -- kỳ vọng 0
```

Cộng thêm: `docker logs ai_auto_trading_system-collector-1 --since 10m` — dán các dòng `backfill`, và
**mọi** dòng WARN/ERROR/CRITICAL nếu có.

### Bước 8 — Chạy cổng go-live, SAU 15:25

`Get-Date` phải **≥ 15:25**, rồi `uv run python scripts/check_golive_gate.py` — dán **nguyên văn** toàn
bộ bảng và EXIT.

Kỳ vọng:
- **Tiêu chí 8 → KHỚP**. Đây là mục đích chính của cả đợt.
- **Tiêu chí 6** → số đo từ phiên **24/09** (không còn "22/09 … 1 ngày trước").
- Tổng thể **nếu** mọi tiêu chí khác cũng đạt thì EXIT 0 — nhưng **không được coi đó là yêu cầu**. Tiêu
  chí nào không đạt thì **báo nguyên văn, không sửa**.

---

## 3. Điều kiện DỪNG → rollback ngay (mục 4)

- Bước 5 ra 0 ở bất kỳ lệnh nào.
- Bước 6: `positions` khác `{"IJC": 400, "AAA": 400}`, hoặc `until` khác `2026-09-24 07:45:00+00:00`, hoặc
  engine không khởi động được / khởi động lại liên tục.
- Bước 7: `bars` có mã phái sinh.
- Container collector hoặc engine không ở trạng thái `Up` sau 2 phút.

**Không** thuộc điều kiện dừng: có dòng "đã chờ"/CRITICAL chờ ở Bước 6.3 (báo cáo là đủ), hoặc cổng ở Bước
8 báo tiêu chí khác ngoài 8 chưa đạt.

## 4. Rollback

```powershell
docker tag ai_auto_trading_system-collector:previous ai_auto_trading_system-collector:latest
docker tag ai_auto_trading_system-engine:previous    ai_auto_trading_system-engine:latest
docker compose up -d --no-deps --no-build collector engine
```

Rồi làm lại Bước 4.3 để xác nhận container đã quay về đúng ID ở Bước 1, và Bước 6.1–6.2 để xác nhận vị
thế và warm-up.

---

## 5. Báo cáo cho Claude

Nguyên văn output của **từng bước 0 → 8**, không tóm tắt. Nếu đã rollback: nêu điều kiện dừng nào kích
hoạt và output của mục 4. Bất kỳ điều gì khác thường — nói thẳng.
