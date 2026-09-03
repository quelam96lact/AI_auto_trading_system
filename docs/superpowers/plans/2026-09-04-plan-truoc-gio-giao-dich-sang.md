# Plan trước giờ giao dịch sáng 04/09

Viết 02:00 ngày 04/09. Mọi số đã đo trong đêm, không phỏng đoán.

**Việc duy nhất thật sự quan trọng hôm nay: 13:00 điện thoại KHÔNG được kêu.**
Đó là phép đo thực địa duy nhất của gói A. Mọi thứ khác trong plan này tồn tại
để phép đo đó không bị nhiễu.

---

## 0. CẢNH BÁO ĐỎ — mốc nghiệm thu NAV đã ĐỔI

Plan hôm qua và mọi tài liệu trước ghi mốc nghiệm thu là **131.580.152**.

**Con số đó nay SAI.** Không phải vì code hỏng — vì **danh mục đã đổi**. Nếu
sáng mai nhìn thấy ~199 triệu rồi tưởng gói A hỏng thì sẽ dựng lại container
giữa lúc không cần, và mất luôn phép đo 13:00.

Đã đo, so hai thời điểm trên `account_position_snapshot` (tài khoản 0434226):

| Mã | 03/09 lúc 11:29 | Hiện tại |
|---|---|---|
| CAP | 1.200 | **0** |
| FOX | 0 | **1.100** |
| HCM | 1.000 | 1.000 |
| SSI | 1.200 | 1.200 |
| TCX | 160 | 160 |
| VCB | 1.500 | 1.500 |

Và nợ giảm mạnh trong đêm:

```
2026-09-03 22:00:00  total_debt = 68.607.848
2026-09-04 00:29:35  total_debt = 17.308.028
```

**Đây là một lệnh hoán đổi ngày 28/08 (bán CAP, mua FOX) vừa THANH TOÁN xong
đêm nay, không phải giao dịch chiều 03/09.** Bản đầu của plan này đoán sai
nguyên nhân; chủ dự án đã đính chính và dữ liệu xác nhận:

- FOX có `cost_price = 65.000` **ngay từ bản chụp đầu tiên 29/08 21:25** — lệnh
  mua đã tồn tại từ 28/08.
- `quantity` của FOX = 0 suốt 29/08 → 03/09, chỉ lật thành 1.100 lúc
  **00:29:35** đêm nay — **đúng khoảnh khắc** CAP lật 1.200 → 0. Hai chân của
  cùng một lệnh, thanh toán cùng lúc.
- Nợ giảm **51.299.820**, xấp xỉ giá trị CAP đã bán.

**Lịch T+2 khớp chính xác:** 28/08 là thứ Sáu; 31/08, 01/09, 02/09 đều là ngày
nghỉ lễ đã khai trong `config.yaml`. Nên 03/09 = T+1, **04/09 = T+2**.

**Hệ quả cần theo dõi hôm nay:** `sellable_quantity` của FOX hiện **= 0**, và sẽ
lật thành **1.100 vào khoảng 13:00** hôm nay khi thanh toán hoàn tất. Đây là mốc
kiểm chứng được, thêm vào mục 5.

### Mốc nghiệm thu mới

```
cổ phiếu 216.214.000  −  nợ 17.308.028  =  198.905.972
```

Đây là số **tính theo giá đóng cửa 03/09**. Trong phiên nó sẽ trôi theo giá thật
— đó là đúng, không phải lỗi. Điều phải đúng là **hình dạng**, không phải con số
lẻ:

| Phải thấy | Không được thấy |
|---|---|
| NAV 0434226 ≈ **199 triệu**, trôi theo giá | NAV = **0** (lỗi cũ đã sửa) |
| `unpriced_symbols` = **`{}`** rỗng | `{FOX,HCM,SSI,TCX,VCB}` hay bất kỳ mã nào |
| NAV 0434221 ≈ **5.021.712**, gần như đứng yên | đổi lớn |

**Nếu NAV = 0 hoặc `unpriced_symbols` khác rỗng ⇒ gói A hỏng thật, báo ngay.**

---

## 1. Trạng thái đã đo lúc 01:00–02:00

| Hạng mục | Đo được | Đánh giá |
|---|---|---|
| Container | 6/6 **Up** (`collector engine postgres nats nats-test grafana`) | tốt |
| Token SSI | `updated_at = 00:29:38`, chuỗi refresh **tự chạy** | tốt |
| Lệch triển khai | `deploy_drift_check` → **OK**, EXIT=0 | tốt |
| 4 chuông (Task Scheduler) | `trading-heartbeat-check`, `-daily-data-check`, `-backfill-universe`, `-deploy-drift` đều **Ready** | tốt |
| Bar hôm nay | 0 (chưa tới phiên) | đúng |
| Heartbeat log | dòng cuối `2026-09-03 15:00:13`, EXIT=0 | đúng |
| Bộ test | **393 + 97 = 490 xanh, 0 đỏ** | tốt |
| NAV 0434221 | 5.021.712, `unpriced = {}` | đúng |
| NAV 0434226 | 199.785.972 → **198.905.972** sau khi vá giá FOX | xem mục 2 |

Không cần chạy tay quy trình token buổi sáng **nếu máy không tắt**. Chỉ chạy
`spike_ssi_sdk_auth.py` → `load_token_to_db.py` khi sáng dậy thấy Docker đã tắt.

---

## 2. Phát hiện 1 — FOX bị định giá bằng giá cũ 1 tuần (ĐÃ VÁ)

FOX là **khoản nắm giữ lớn nhất** của danh mục (1.100 cổ ≈ 70,7 triệu ≈ **33%**).
Nhưng `bars_daily` không có bar 03/09 cho FOX — giá mới nhất là **28/08**.

Nguyên nhân — và đây **là** một lỗ hổng cấu trúc, không phải trùng hợp về
thời điểm như bản đầu của plan này viết:

- Backfill hằng đêm chạy trên *174 mã thanh khoản + 8 mã bắt buộc có giá*, không
  phải toàn bộ 965 mã (`logs/backfill.log`: `[load] 174 ma thanh khoan + 8 ma
  bat buoc co gia (1 ngoai universe) = 175 ma`).
- `Storage.read_must_price_symbols` dựng danh sách "bắt buộc có giá" từ
  `read_real_positions`, mà hàm đó — theo đúng docstring của nó — **chỉ trả mã
  có `quantity > 0`**.
- Một lệnh mua T+2 có `quantity = 0` **trong suốt cửa sổ thanh toán**. Nên
  **mọi mã vừa mua đều vô hình với danh sách bắt buộc có giá cho tới khi thanh
  toán xong** — đúng những ngày nó cần được nạp giá nhất.

FOX chịu trọn 5 phiên như vậy (29/08 → 03/09). Và đến khi nó hiện ra lúc
00:29:35, backfill đêm **đã chạy xong từ 21:40** — nên phiên đầu tiên NAV tính
đến FOX lại là phiên dùng giá cũ nhất.

Đây không phải lỗi của backfill, cũng không phải lỗi của gói A. Nó là hệ quả của
việc lấy "đang nắm giữ" theo `quantity > 0` ở một thị trường T+2.

**Điều nguy hiểm là nó im lặng:** kiểm tra tuổi giá của gói A tính theo **ngày
giao dịch**, mà 31/08–02/09 là nghỉ lễ, nên 28/08 → 04/09 chỉ là **2 ngày giao
dịch** ≤ 5. Vị từ cho qua, `unpriced_symbols` vẫn rỗng, **không có cảnh báo
nào** — trong khi 33% danh mục đang được định giá bằng giá một tuần trước.

**Đã vá lúc 01:01** (nạp bổ sung, không xoá gì):

```
uv run python scripts/backfill_universe.py --timeframe 1d \
    --from 2026-09-03 --to 2026-09-03 --symbols FOX
DONE: ok=1 skip=0 err=0 / 1
```

Kết quả: FOX 03/09 = **64.300** (trước đó dùng 65.100 của 28/08). Giá trị danh
mục 217.094.000 → **216.214.000**.

**Việc còn lại — KHÔNG làm hôm nay:** vá này chữa triệu chứng của hôm nay,
không chữa cơ chế. **Mọi lệnh mua mã ngoài rổ 174 đều sẽ lặp lại y hệt**, vì
mọi lệnh mua đều đi qua cửa sổ T+2 với `quantity = 0`. Ghi thành mục tồn đọng
mới:

> **H — mã đang trong cửa sổ thanh toán phải được nạp giá.**
> `read_must_price_symbols` cần tính cả mã đã mua nhưng chưa về (`quantity = 0`
> mà `cost_price > 0`, hoặc đọc từ nguồn khác). Chạm `trading/storage/db.py`
> ⇒ vào image ⇒ đi cùng đợt tối nay hoặc cuối tuần, **không phải hôm nay**.
> Lưu ý khi làm: `read_real_positions` là **một nguồn duy nhất** theo luật
> `4ea4c8d` — sửa ở đó hay thêm hàm mới là một quyết định cần cân nhắc, không
> được viết truy vấn `account_position_snapshot` thứ hai.

---

## 3. Phát hiện 2 — chuông #3 chạy trước dữ liệu 5 tiếng, **mù cấu trúc**

Đã đo lịch chạy thật:

```
trading-daily-data-check   -> 15:30
trading-backfill-universe  -> 20:30
```

`scripts/daily_data_check.py` kiểm **bar daily** của các mã active. Nhưng bar
daily chỉ được nạp bởi backfill lúc **20:30**. Nên lúc 15:30 bảng `bars_daily`
**luôn** chưa có dữ liệu của ngày hôm đó.

Bằng chứng — ngày 03/09 là phiên giao dịch đầy đủ (134 bar, 3 mã):

```
2026-09-03 15:30:02 daily-data-check start
[2026-09-03] Không có mã nào có bar trong ngày (ngày nghỉ hoặc feed ngừng toàn
diện — nhường Heartbeat 2A).
EXIT=0
```

Nó rơi vào nhánh "cả thị trường không có bar ⇒ nhường 2A" và thoát 0. **Nhánh đó
là nhánh duy nhất nó từng đi trong ngày giao dịch bình thường.** Chuông #3 chưa
bao giờ thực sự kiểm được điều nó sinh ra để kiểm.

Đây **đúng hình dạng** với chuông giả 13:00 mà gói A vừa chữa: một cái đo đúng
công thức nhưng sai thời điểm/đại lượng.

**Đề xuất (quyết định của chủ dự án, không tự làm):** dời
`trading-daily-data-check` sang **sau** backfill — ví dụ 21:30. Đây là đổi lịch
Task Scheduler, **không sửa code, không vào image**, nên làm được bất kỳ lúc
nào, kể cả trước phiên. Nhưng nó là chuông báo, nên tôi không tự đổi.

---

## 4. Việc làm trước 09:00 — danh sách ngắn

| Giờ | Việc | Cách biết là xong |
|---|---|---|
| — | *(đã xong đêm nay)* vá giá FOX | `bars_daily` FOX có ngày 03/09 = 64.300 |
| **trước 08:00** | Xác nhận Docker đang chạy | `docker ps` ra **6** container |
| 08:00 | Để chuông `deploy-drift` tự chạy | không có tin Telegram nào |
| **chỉ khi Docker đã tắt** | Nạp token 2 bước theo `DEPLOYMENT.md §8.5` | `ssi_auth_state.updated_at` là của sáng nay |
| ~08:45 | Ghi lại NAV trước phiên để so | `account_nav_snapshot` dòng mới nhất |

**Không có gì khác.** Danh sách ngắn là có chủ ý: hôm nay là ngày **quan sát**,
không phải ngày triển khai.

---

## 5. Theo dõi trong phiên — mốc và ý nghĩa

| Giờ | Chờ gì | Nếu sai thì sao |
|---|---|---|
| **09:00–09:16** | Cửa sổ mù đã biết: feed chết thật sẽ chỉ báo lúc ~09:16, không phải 09:00 | Đây là **đánh đổi có chủ ý** của gói A, không phải lỗi. Đừng "sửa" |
| 09:00–09:15 | Bar đầu tiên vào `bars` | Không có bar sau 09:16 ⇒ chuông 2A phải kêu |
| ~09:05 | NAV 0434226 ≈ 199 triệu, `unpriced = {}` | NAV = 0 hoặc `unpriced` khác rỗng ⇒ **gói A hỏng, báo ngay** |
| 11:30–13:00 | Nghỉ trưa — **im lặng là đúng** | — |
| **13:00** | **Điện thoại KHÔNG kêu.** Đây là phép đo | Kêu CRITICAL ⇒ gói A chưa chữa được, giữ nguyên log để phân tích |
| 13:00–13:15 | Bar quay lại sau nghỉ trưa | — |
| **~13:00** | FOX `sellable_quantity` lật **0 → 1.100** (T+2 của lệnh mua 28/08) | Nếu tới 14:45 vẫn = 0 ⇒ hỏi SSI, không phải lỗi hệ thống |
| 14:45 | Phiên đóng, đếm bar/lệnh | — |

Mốc 13:00 là điểm mấu chốt: hôm 03/09 lúc 13:00:03 chuông kêu CRITICAL giả (bar
cuối 11:25, cách 95 phút đồng hồ nhưng **0 phút thị trường**). Gói A đổi đại
lượng đo từ phút đồng hồ sang phút trong phiên. Hôm nay là lần đầu nó gặp 13:00
thật.

---

## 6. Việc KHÔNG làm hôm nay

| Việc | Vì sao |
|---|---|
| Dựng lại container | mất phép đo 13:00 — lý do tồn tại của cả ngày hôm nay |
| Sửa bất cứ gì trong `trading/` hoặc `config/config.yaml` | vào image ⇒ như trên |
| B1, B2, C3, C-a | đã xếp sau 14:45, gộp **một** lần dựng lại |
| D1 diễn tập dead-man's switch | cấm rõ ràng: không phải phiên 04/09 |
| "Sửa" cửa sổ mù 09:00–09:16 | đánh đổi có chủ ý, đã ghi trong commit `80dd0be` |
| Tự đổi lịch chuông #3 | là chuông báo — chờ chủ dự án quyết (mục 3) |
| Nới ngưỡng chuông vì bất cứ lý do gì | che triệu chứng |
| Bật `real_trading_enabled` | không đổi |

---

## 7. Nếu có sự cố — thứ tự xử lý

1. **Feed chết** (như 09:11 hôm qua): `docker compose restart collector` —
   **restart, KHÔNG build**. Hôm qua cách này đã tự backfill lại đầu phiên,
   không để lỗ bar.
2. **NAV = 0 hoặc `unpriced` khác rỗng:** không sửa code trong phiên. Chụp lại
   `account_nav_snapshot` + `account_balance_snapshot` + log collector, xử lý
   sau 14:45.
3. **Chuông kêu lúc 13:00:** giữ nguyên `logs/heartbeat.log`, không xoá, không
   sửa. Đó là dữ liệu của phép đo.

Nguyên tắc chung: hôm nay **quan sát và ghi chép**, không sửa. Cửa sổ sửa mở lúc
14:45.
