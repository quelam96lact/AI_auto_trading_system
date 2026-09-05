# Đánh giá sẵn sàng go-live (06/09) + Brief đợt 10

**Người đánh giá:** Claude (planner/auditor) · **Ngày:** 2026-09-06
**Cách làm:** tự chạy lại các phép kiểm trên hệ thống đang chạy, không dựa vào
tài liệu cũ. `GO_LIVE_AUDIT.md` là bản 13/08, phần lớn nội dung đã lỗi thời.

---

## 0. KẾT LUẬN

**Chưa sẵn sàng. Và chặn số một không phải việc kỹ thuật — không agent nào code
được nó đi.**

Hạ tầng thì lành: 6 container chạy 5 giờ liên tục, 482 test xanh, chốt chặn
`real_trading_enabled` có test bảo vệ, đường lệnh thật có fail-safe sức mua và
**không tự đặt lệnh** (engine chỉ ghi DB + cảnh báo; người dùng chạy
`scripts/confirm_real_order.py` thủ công). Đó là thiết kế an toàn, giữ nguyên.

Nhưng thứ chạy trên hạ tầng đó thì chưa chứng minh được gì.

---

## 1. TẦNG 1 — CHẶN BẤT KỂ KỸ THUẬT

### 1.1 Chiến lược đang chạy đã được đo là LỖ

Đo lại hôm nay bằng bộ số đo mới (đợt 9), phí VN đã đúng 0,25%:

| | Octopus Pullback (chiến lược chạy thật) |
|---|---:|
| PnL | **−1.615.319.902 VND** |
| Profit Factor | **0,74** |
| Expectancy/lệnh | **−1.068.152 VND** |
| Sharpe (252 kỳ) | **−0,96** |

Ngưỡng để *quyết định giao dịch* là PF ≥ 1,3. Đang ở 0,74 — không phải gần đạt,
mà là mỗi đồng lãi đi kèm 1,35 đồng lỗ. Các phương án khác còn tệ hơn:
octopus_combo −9,83 tỷ, ba chiến lược nến đều lỗ, hybrid thì "lãi" hoá ra là
sản phẩm của phí = 0 và quét lưới trong mẫu.

### 1.2 Engine gần như câm — và câm ở đúng khung nó đang chạy

`scripts/check_silent_engine.py` chạy hôm nay:

```
HII : 3.211 bar 5m, cổng mở 1.342 bar (41,8%),  0 bull / 0 bear  [WARN_NO_BULL]
IJC : 4.719 bar 5m, cổng mở 3.818 bar (80,9%),  6 bull / 0 bear  [OK]
AAA : 4.597 bar 5m, cổng mở 3.702 bar (80,5%),  6 bull / 0 bear  [OK]
```

Thoát CRITICAL. Chú ý cái mà nhãn `[OK]` che mất: IJC và AAA sinh **6 tín hiệu
trên gần 4.700 bar** — cỡ 0,13%. Đây không phải chiến lược đang hoạt động, đây
là chiến lược gần như đứng yên.

**Và toàn bộ con số ở §1.1 là bar NGÀY.** Khung 5 phút — cái engine thật sự ăn —
**chưa có phép đo nào**. Bật tiền thật lúc này là trả phí thật để chạy một chiến
lược hoặc đã đo là lỗ, hoặc chưa từng đo ở khung nó đang chạy.

---

## 2. TẦNG 2 — CHẶN CỨNG NẾU VẪN MUỐN BẬT CỜ

| Mã | Vấn đề | Bằng chứng |
|---|---|---|
| **J** | Đường lệnh thật **chỉ MUA, không bao giờ BÁN** | `real_orders.py:46` rẽ `"bull"`, `:75` rẽ `"bear"`; octopus không bao giờ phát `"bear"` (xác nhận: 0 bear trên cả 3 mã). `tests/test_real_trading_guard.py` (9 test) chặn — bật cờ mà chưa xử J thì suite đỏ. |
| **E** | Tài khoản/vốn | Đã làm rõ 06/09: 0434226 là **margin**, NAV **199.545.980**, không phải "tài khoản rỗng". Nhưng chuyển engine từ 0434221 (NAV 5.021.712) sang nó **đồng thời là quyết định nhân quy mô lệnh ~40 lần**. |
| **P1** | `account_position_snapshot` **không có kiểm tra độ cũ**, ở **hai** call site | `real_orders.py:42` (`handle_crossover`) và `:174` (`handle_stop_touch`) đều gọi `read_real_positions()` rồi dùng thẳng kết quả. Nhánh BUY có fail-safe độ cũ cho sức mua (`BUYING_POWER_MAX_AGE_MINUTES = 15`, `:15` và `:64`), nhánh vị thế thì không có gì tương đương. |

---

## 3. TẦNG 3 — VẬN HÀNH

| Mã | Việc | Trạng thái đo hôm nay |
|---|---|---|
| — | Lệch triển khai | image **cũ hơn code 1 ngày 14 giờ** — engine đang chạy không có thay đổi đợt 8/9/9b |
| **C3** | Lịch nghỉ lễ | config còn đúng 3 ngày (31/08, 01/09, 02/09) — **đều đã qua**. Không phải thiếu 2026 (VN hết lễ sau 02/09), nhưng **từ 01/01/2027 lịch rỗng hoàn toàn** |
| **C1** | VPS Ubuntu | `DEPLOYMENT.md` sẵn, chưa thực hiện — vẫn chạy trên máy dev Windows |
| **C2** | Docker tự khởi động | vẫn bật tay |
| **D1** | Diễn tập dead-man's switch | **chưa từng diễn tập** — chuông chưa bao giờ được chứng minh là kêu thật |

---

# BRIEF ĐỢT 10

## Mục tiêu

Không phải "chuẩn bị bật cờ". Mục tiêu là: **đo cho biết thứ đang chạy tốt hay
xấu**, và **bịt các lỗ hổng an toàn** để nếu sau này tìm được chiến lược có lợi
thế thì bệ đã sẵn.

Nếu agent thấy mình đang làm việc gì khiến hệ thống *gần hơn* tới việc bật tiền
thật mà chưa qua §1 — **dừng và báo cáo**.

---

## Task 1 — Đo octopus trên bar 5 PHÚT (giá trị cao nhất)

Đây là lỗ hổng lớn nhất còn lại: chiến lược chạy thật ở khung 5m, mọi con số
đều là bar ngày.

- Dùng `run_backtest` với `--tf 5m` (`_TF_SPEC` đã hỗ trợ, đọc từ bảng `bars`).
- Rổ mã: đúng ba mã engine đang chạy (`config.symbols`), vì `bars` 5m chỉ có
  các mã đó.
- **Bắt buộc dùng `trading/metrics.py`** — báo cáo đủ PnL, Profit Factor,
  expectancy, max drawdown danh mục, Sharpe. `periods_per_year` cho bar 5m:
  tự tính từ số bar/phiên × số phiên/năm, **ghi rõ cách tính**, không đoán.
- Đặt **cạnh** số bar ngày (−1.615.319.902 / PF 0,74 / Sharpe −0,96).

**Cảnh báo về cỡ mẫu:** IJC/AAA chỉ 6 tín hiệu, HII 0. Nhiều khả năng kết quả
là "quá ít lệnh để nói được gì". **Đó là một kết luận hợp lệ và phải báo đúng
như thế** — không nới tham số cho ra nhiều lệnh hơn rồi báo cáo con số đẹp. Nới
tham số là việc khác, cần quyết định riêng của chủ dự án.

**Kiểm chứng:** bảng số + câu trả lời rõ ràng cho "cỡ mẫu có đủ để kết luận
không, và vì sao".

## Task 2 — Fail-safe độ cũ cho `account_position_snapshot` (P1)

Khuôn theo đúng fail-safe sức mua đã có trong cùng file — **đọc
`real_orders.py:51-73` trước, chép khuôn, không sáng tạo dạng khác**:

- Thêm hằng số độ cũ tối đa cho vị thế, đặt cạnh `BUYING_POWER_MAX_AGE_MINUTES`
  (`:15`).
- **Cả hai call site**: `handle_crossover` (`:42`, nhánh SELL) và
  `handle_stop_touch` (`:174`). Thiếu dòng vị thế **hoặc** dòng quá cũ ⇒
  **từ chối + CRITICAL**, không rơi về giá trị "cho dễ gật".
- Không đụng nhánh BUY (đã có fail-safe riêng).

**Nguồn thời gian đã có sẵn — KHÔNG đổi chữ ký hàm nào.** `read_real_positions()`
trả `dict[str, RealPosition]` không kèm mốc thời gian, nhưng
`Storage.read_position_sync_ts(account_no) -> datetime | None`
(`db.py:686-693`) đã tồn tại và trả đúng mốc lần đồng bộ vị thế gần nhất
(`None` = chưa bao giờ đồng bộ). Dùng hàm đó.

`read_real_positions` có **13 nơi gọi** — đổi chữ ký của nó là bán kính ảnh
hưởng lớn không cần thiết. Chỉ gọi thêm `read_position_sync_ts` tại hai chỗ
trong `real_orders.py`.

Lưu ý ngữ nghĩa: `None` nghĩa là **chưa từng đồng bộ**, phải xử như "không có
dữ liệu" ⇒ từ chối + CRITICAL, **không** coi là "mới tinh".

**Kiểm chứng:** test cho ba trường hợp trên **mỗi** call site — vị thế tươi
(cho qua), vị thế quá cũ (từ chối + CRITICAL), không có dòng vị thế (từ chối +
CRITICAL). Kèm phá hoại: bỏ kiểm tra ⇒ test phải đỏ, dán output thô, khôi phục,
`grep -rn "SABOTAGE"` rỗng.

## Task 3 — Dựng lại image (lệch 1 ngày 14 giờ)

```
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

**Kiểm chứng:** `uv run python scripts/deploy_drift_check.py` không còn cảnh báo;
`docker ps` cả 6 container Up; `scripts/heartbeat_check.py` xanh sau khi dựng lại.

**Cấm** đụng `config/config.yaml` trong lúc dựng lại.

## Task 4 — Docker tự khởi động (C2)

`restart: unless-stopped` cho các service trong `docker-compose.yml`.

**Kiểm chứng:** `docker inspect` từng container cho thấy RestartPolicy đúng.
Nêu rõ trong báo cáo rằng việc này **không** làm container tự chạy sau khi khởi
động lại máy nếu Docker Desktop chưa được đặt tự khởi động — đó là thao tác trên
máy người dùng, **không tự làm**, chỉ ghi hướng dẫn.

---

## VIỆC KHÔNG GIAO CHO AGENT — cần chủ dự án

| Mã | Vì sao không giao được |
|---|---|
| **§1 chiến lược** | Không phải lỗi code. Cần quyết định: đo lại toàn bộ (đang làm), đổi họ chiến lược, hay dừng săn |
| **J** | Nối đường SELL là thay đổi hành vi tiền thật — cần chủ dự án chọn hướng trước |
| **E** | Chuyển sang 0434226 = nhân lệnh ~40 lần. Quyết định tiền, không phải kỹ thuật |
| **C3** | Lịch lễ 2027 **phải có nguồn chính thức**. Cấm đoán ngày lễ (ràng buộc thường trực). Chưa gấp — ràng buộc từ 01/01/2027 |
| **C1** | Chuyển sang VPS Ubuntu — quyết định hạ tầng + chi phí |
| **D1** | Diễn tập dead-man's switch cần một phiên giao dịch thật, chủ dự án hẹn lịch |

---

## PHẠM VI PHẪU THUẬT

**Được sửa:** `trading/real_orders.py` (chỉ Task 2), test tương ứng,
`docker-compose.yml` (chỉ `restart:`), script đo mới cho Task 1.

**Cấm đụng:** `config/config.yaml`, `.env`, `real_trading_enabled` (giữ `false`
— **không bật dù chỉ để thử**), `_default_strategy()`, `run_backtest`,
`PaperBroker`, `trading/strategies/*`, `trading/metrics.py`, `trading/sampling.py`.
Không gọi API đặt/huỷ lệnh SSI. Không `TRUNCATE`/`DROP`/xoá dòng.

**Không commit, không push.** Claude audit rồi mới commit.

## BÁO CÁO NỘP LẠI

- Bảng Task 1 đặt cạnh số bar ngày, kèm kết luận trung thực về cỡ mẫu.
- Output thô Task 3 (`deploy_drift_check`, `docker ps`, `heartbeat_check`).
- Output đỏ phá hoại Task 2 + xác nhận `grep` rỗng.
- `uv run pytest -m "not integration" -q` (hiện 482) và `ruff check`.
- Bất cứ chỗ nào brief này sai hoặc mâu thuẫn: **báo lại, đừng tự quyết**.
