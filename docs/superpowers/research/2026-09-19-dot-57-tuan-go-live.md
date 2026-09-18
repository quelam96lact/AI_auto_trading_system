# Báo Cáo Đợt 57: Chuẩn Bị Tuần Go-Live 22–26/09/2026

**Ngày thực hiện:** 2026-09-19  
**Người thực hiện:** Senior Dev / AI Assistant  
**Kế hoạch:** `docs/superpowers/plans/2026-09-19-brief-dot-57-tuan-go-live.md`  

---

## 1. Git Status & Diff Stat

### `git status --short`
```text
 M README.md
 M scripts/docker_down_alert.py
 M scripts/engine_consumer_check.py
 M tests/test_docker_down_alert.py
 M tests/test_engine_consumer_check.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? scripts/check_golive_gate.py
?? tests/test_check_golive_gate.py
```

### `git diff --stat` (đối với các file thuộc phạm vi Đợt 57)
```text
 scripts/docker_down_alert.py        |   8 +-
 scripts/engine_consumer_check.py    |   4 +-
 tests/test_docker_down_alert.py     |  20 ++++
 tests/test_engine_consumer_check.py |  38 ++++++++
 4 files changed, 64 insertions(+), 6 deletions(-)
```

---

## 2. Task 1 — Đọc Bài Kiểm Đặt/Huỷ Lệnh (`scripts/spike_ssi_sdk_place_order.py`)

*Ghi chú: Script chỉ được đọc và khảo sát; KHÔNG chạy, KHÔNG sửa.*

### 2.1. Trả Lời 5 Câu Hỏi Cụ Thể

1. **Khối lệnh try/finally:**
   - Script có khối `try/finally` từ dòng 104 đến 154 (`finally` huỷ lệnh tại dòng 138-154).
   - **Xác nhận:** Nếu dòng `time.sleep(10)` (dòng 135) bị ngắt bởi `KeyboardInterrupt` (Ctrl+C), khối `finally` **VẪN CHẠY**, lệnh huỷ **VẪN ĐƯỢC PHÁT ĐI** tới SSI SDK (`client.cancel_order(...)`).
   - **Rủi ro:** Nếu người dùng nhấn Ctrl+C hai lần liên tiếp quá nhanh khiến Python ngắt ngay trong lúc `client.cancel_order()` đang truyền HTTP, lệnh huỷ có thể bị gián đoạn. Ngoài ra nếu rớt mạng Internet đúng lúc sleep, `cancel_order` sẽ ném Exception và để lại lệnh treo trên sàn (cần huỷ tay qua app SSI Web/Mobile).

2. **Cách tính giá trần/sàn & rủi ro khớp ngoài ý muốn:**
   - Dòng 74: `price = round(price * 0.93, -2) if side.upper() == "B" else round(price * 1.07, -2)`
   - Script lấy giá tham chiếu gần nhất và nhân `0.93` (giảm 7% - sát sàn HOSE) khi MUA, hoặc nhân `1.07` (tăng 7% - sát trần HOSE) khi BÁN.
   - **Rủi ro:** Script **KHÔNG** tra cứu bảng giá trực tiếp (order book / realtime bid-ask) để kiểm tra xem ở mức giá sàn có người đang bán tháo MP đè vào hay không. Tuy nhiên, vì đặt lệnh MUA ở sát giá SÀN (`-7%`) trong phiên bình thường, xác suất khớp ngay lập tức là rất thấp, trừ phi cổ phiếu hôm đó đang bị bán tháo chất sàn la liệt.

3. **Tác động tới NAV (5.021.712 đ):**
   - Giá đóng cửa phiên gần nhất (18/09/2026):
     - **VCB:** Close 59.900 đ. Giá đặt mua kiểm tra (-7% làm tròn 100đ): `55.700 đ`. Tiền cần mua 100 cp: `5.570.000 đ` > NAV (5.021.712 đ) -> **SSI từ chối do vượt quá sức mua**.
     - **HPG:** Close 21.550 đ. Giá đặt mua kiểm tra (-7% làm tròn 100đ): `20.000 đ`. Tiền cần mua 100 cp: `2.000.000 đ` (chiếm ~39.8% NAV).
     - **IJC:** Close 6.920 đ. Giá đặt mua kiểm tra (-7% làm tròn 100đ): `6.400 đ`. Tiền cần mua 100 cp: `640.000 đ` (chiếm ~12.7% NAV).
     - **AAA:** Close 7.260 đ. Giá đặt mua kiểm tra (-7% làm tròn 100đ): `6.800 đ`. Tiền cần mua 100 cp: `680.000 đ` (chiếm ~13.5% NAV).
   - Nếu lệnh khớp ngoài ý muốn:
     - Với **IJC** hoặc **AAA**: Tài khoản giữ 100 cp giá trị ~640k–680k đ, NAV còn lại ~4,34 triệu đ tiền mặt. Hệ thống vẫn còn >85% NAV tiền mặt, hoàn toàn không bị kẹt vốn lớn, T+2.5 có thể bán ra bình thường.
     - Với **HPG**: Mất 2.000.000 đ tiền mặt (40% NAV), rủi ro cao hơn IJC/AAA nếu giá rơi tiếp.

4. **Khung giờ chạy an toàn:**
   - **Khung giờ khuyến nghị:** **09:30 – 10:30** hoặc **13:15 – 14:00**.
   - **Lý do:** Đây là các khung giờ khớp lệnh liên tục ổn định của sàn HOSE/HNX.
   - **Tuyệt đối TRÁNH:**
     - Ngoài giờ giao dịch (trước 09:00, 11:30–13:00, sau 15:00): Sàn đóng cửa, SSI Core sẽ từ chối nhận lệnh hoặc đẩy vào hàng đợi lệnh phiên kế tiếp, không test được chu trình huỷ tức thì.
     - Phiên ATO (09:00 – 09:15) & Phiên ATC (14:30 – 14:45): Quy định của Sở giao dịch là **nghiêm cấm huỷ/sửa lệnh** trong phiên định kỳ mở/đóng cửa. Nếu đặt vào lúc này, lệnh huỷ ở khối `finally` sẽ bị từ chối 100%.

5. **Lệnh huỷ có chắc chắn thành công?**
   - **Không chắc chắn 100%.**
   - Các trường hợp thất bại:
     1. Lệnh vô tình đã khớp trước khi lệnh huỷ tới nơi (nếu cổ phiếu bị quét sàn). Khi đã khớp (Fully Filled), lệnh huỷ sẽ bị báo lỗi `Order already matched / invalid status`.
     2. Rớt mạng Internet, lỗi kết nối DNS/TLS với SSI API gateway trong 10 giây sleep.
     3. Đặt vào các khung giờ không cho phép huỷ lệnh (ATO/ATC/ngoài phiên).

### 2.2. Kết Luận & Lệnh Chính Xác Cho T3

- **Hai lựa chọn:**
  - **Lựa chọn A: KHÔNG CHẠY** bài kiểm này nếu chủ dự án không muốn chịu bất kỳ rủi ro phát sinh khớp lệnh nào (vì đã có unit tests mô phỏng mock API).
  - **Lựa chọn B: CHẠY** để nghiệm thu kết nối thật với SSI Core trước phiên go-live, **nhưng PHẢI đổi symbol sang AAA hoặc IJC** (thay vì VCB bị thiếu sức mua hoặc HPG vốn lớn), và phải chạy trong phiên khớp lệnh liên tục sáng T3 (09:30 - 10:30).
- **Lệnh chính xác chạy ở T3 (nếu chọn Chạy):**
  ```bash
  uv run python scripts/spike_ssi_sdk_place_order.py --symbol AAA --account 0434221
  ```
  *(Giải thích: Mã AAA có thị giá ~7.200 đ, đặt mua 100 cp giá sàn ~6.800 đ chỉ tốn 680.000 đ, sức mua tài khoản hiện có 4.390.000 đ đủ thoải mái; nếu có rủi ro khớp hy hữu cũng chỉ chiếm 13% NAV).*

---

## 3. Task 2 — Chữa Lỗi Chuông Tự Khoá Miệng Sau Khi Gửi Trượt

### 3.1. Phân Tích & GitNexus Impact Analysis
- Trước khi sửa `scripts/docker_down_alert.py` và `scripts/engine_consumer_check.py`, đã tiến hành phân tích luồng gọi:
  - `docker_down_alert.py`: `run_alert` nhận `send=send_telegram`. Trước đây `send_telegram` ném ngoại lệ -> bắt ở `except` -> thoát không ghi stamp file. Khi Đợt 56 đổi `send_telegram` trả `False`, nhánh `except` chết, code rơi xuống `_write_last_alert` -> chuông bị câm.
  - `engine_consumer_check.py`: Dòng 175-177 cập nhật vô điều kiện `new_state["last_alert_ts"] = now.timestamp()` sau `send_telegram(alert_msg)`. Nếu mạng lỗi trả `False`, cooldown 15 phút vẫn kích hoạt.
- **Blast Radius:** Chỉ tác động cục bộ tới luồng cảnh báo của 2 script giám sát; không ảnh hưởng tới engine, collector hay storage.

### 3.2. Chi Tiết Git Diff Code

```diff
--- a/scripts/docker_down_alert.py
+++ b/scripts/docker_down_alert.py
@@ -131,11 +131,15 @@ def run_alert(
         # thi van con ban ghi o log (khuon heartbeat_check).
         _print_safe(msg)
         try:
-            send(msg)
+            ok = send(msg)
+            if ok is not False:
+                _write_last_alert(now, stamp_file)
+            else:
+                _print_safe("[docker-down-alert] gui Telegram that bai: send tra ve False")
+                return 0
         except Exception as e:
             _print_safe(f"[docker-down-alert] gui Telegram loi: {type(e).__name__}: {e}")
             return 0
-        _write_last_alert(now, stamp_file)
         return 0
     except Exception as e:
         # Lop ngoai cung: loi khong lo truoc (vi du load config hong) cung

--- a/scripts/engine_consumer_check.py
+++ b/scripts/engine_consumer_check.py
@@ -173,8 +173,8 @@ def run_check(
         _print_safe(alert_msg)
 
         if cooldown_elapsed >= ALERT_COOLDOWN_SECONDS:
-            send_telegram(alert_msg)
-            new_state["last_alert_ts"] = now.timestamp()
+            if send_telegram(alert_msg):
+                new_state["last_alert_ts"] = now.timestamp()
         else:
             _print_safe(f"[engine-consumer] Đang trong thời gian chống spam ({cooldown_elapsed:.0f}s < {ALERT_COOLDOWN_SECONDS}s), chưa gửi lại.")
```

### 3.3. Bằng Chứng Test Phân Biệt Được (Negative & Positive Testing)
Đã bổ sung 4 unit tests mới:
- `test_gui_telegram_that_bai_khong_ghi_dau_stamp` & `test_gui_telegram_thanh_cong_ghi_dau_stamp` trong `tests/test_docker_down_alert.py`.
- `test_send_telegram_failure_does_not_update_last_alert_ts` & `test_send_telegram_success_updates_last_alert_ts` trong `tests/test_engine_consumer_check.py`.

**Chứng minh phân biệt được (Negative testing experiment):**
- Khi tạm thời khôi phục lại code cũ (ghi nhận timestamp bất chấp gửi trượt):
  - Test `test_gui_telegram_that_bai_khong_ghi_dau_stamp` lập tức **FAILED** (do stamp file bị tạo).
  - Test `test_send_telegram_failure_does_not_update_last_alert_ts` lập tức **FAILED** (do `last_alert_ts > 0`).
- Khi khôi phục bản vá chuẩn: Toàn bộ test **PASSED 100%**.

---

## 4. Task 3 — Cổng Kiểm Định Trước Khi Bật Cờ (`scripts/check_golive_gate.py`)

### 4.1. Kiến Trúc Script
- Tạo mới `scripts/check_golive_gate.py` và `tests/test_check_golive_gate.py`.
- **Nguyên tắc thiết kế:**
  - Tách hàm thuần đánh giá logic: `evaluate_golive_gate(config_enabled, nav, min_qty_by_symbol, pos_age_sec, bp_age_sec, stream_coverage, stream_summary, telegram_ok, drift_ok, drift_msg, real_fills_count)`.
  - Tái sử dụng logic kiểm định hiện có (`check_deploy_drift` từ `scripts/deploy_drift_check.py`, kiểm tra cấu hình telegram từ biến môi trường, đọc log coverage mới nhất).
  - Hoàn toàn chỉ đọc DB và file log; không gọi API SSI, không đặt/huỷ lệnh, không gửi tin nhắn Telegram thật.
  - Phân loại 3 mã thoát rõ ràng:
    - Exit 0: Toàn bộ tiêu chí đạt / đủ điều kiện an toàn để bật cờ.
    - Exit 1: Có cảnh báo (ví dụ độ phủ stream < 90% nhưng các lá chắn an toàn vẫn tươi).
    - Exit 2: Chặn tuyệt đối (sức mua không đủ, lá chắn vị thế/sức mua quá hạn > 15m, thiếu biến telegram, hoặc lệch image container deploy drift).

### 4.2. Nguyên Văn Một Lượt Chạy Thật Trên Môi Trường

```text
=========================================================================================================
 BẢNG KIỂM ĐỊNH CỔNG GO-LIVE (GOLIVE GATE CHECK) — 2026-09-19 06:34:37 (VN)
 Tài khoản: 0434221 | Danh mục: HPG, IJC, AAA
=========================================================================================================
#   | Tiêu chí                         | Trạng thái đo được             | Kết luận | Ghi chú               
---------------------------------------------------------------------------------------------------------
1   | real_trading_enabled (Cờ chính)  | False                          | [THÔNG TIN] | Đang là false (chuẩn bị bật sang true vào T5 sau khi pass cổng)
2   | Tài khoản & NAV                  | 5,021,712 VND                  | [ĐẠT]      | Tài khoản cấu hình: 0434221
3   | Sức mua tối thiểu                | HPG: 217cp, IJC: 676cp, AAA: 645cp | [ĐẠT]      | Đạt điều kiện tối thiểu 1 lô HOSE/HNX cho toàn bộ danh mục
4   | Lá chắn độ tươi vị thế           | 3m 17s                         | [ĐẠT]      | Vị thế tươi mới, sẵn sàng cho lệnh thật
5   | Lá chắn độ tươi sức mua          | 3m 17s                         | [ĐẠT]      | Sức mua tươi mới, sẵn sàng cho lệnh thật
6   | Độ phủ luồng phiên gần nhất      | 89.5%                          | [CẢNH BÁO] | Hơi thấp (< 90%): WARN: do phu luong phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen), duoi nguong canh bao 90%
7   | Đường truyền Telegram            | ĐÃ CẤU HÌNH                    | [ĐẠT]      | Không gửi tin kiểm tra, chỉ kiểm cấu hình môi trường
8   | Lệch triển khai (Image vs Git)   | LỆCH / LỖI                     | [CHẶN]     | [deploy-drift] collector: image CŨ hơn commit gần nhất chạm trading/ (6 giờ 45 phút) — dựng lại container (docker compose build collector engine && docker compose up -d --no-deps collector engine); [deploy-drift] engine: image CŨ hơn commit gần nhất chạm trading/ (6 giờ 45 phút) — dựng lại container (docker compose build collector engine && docker compose up -d --no-deps collector engine)
9   | Lịch sử lệnh thật đã khớp        | 0 lệnh                         | [THÔNG TIN] | Số lệnh đã ghi nhận trong bảng real_order_fills
=========================================================================================================
>>> KẾT LUẬN: KHÔNG ĐƯỢC BẬT (EXIT 2) — CÁC LÁ CHẮN AN TOÀN ĐANG BỊ TỪ CHỐI HOẶC HỎNG.
    Nếu phát sinh lệnh thật tại thời điểm này, hệ thống sẽ chặn lệnh để bảo toàn vốn.
=========================================================================================================
EXIT_CODE: 2
```

*Nhận xét kết quả:*
- Cổng đã phát hiện chính xác:
  - Sức mua và NAV đủ điều kiện.
  - Cảnh báo độ phủ stream chiều 18/09 (89.5%).
  - Chặn go-live (Exit 2) do Tiêu chí 8: Container Docker hiện chưa được rebuild sau các commit sửa đổi codebase (theo quy định không build container trong Đợt 57). Điều này bảo đảm không thể có sự cố chạy code cũ trên image mới hoặc ngược lại vào ngày go-live.

---

## 5. Kiểm Định Tổng Thể Codebase

1. **Pytest test suite:**
   - **801 passed in 47.73s** (Vượt mốc 792 trước đó; thêm 2 test `docker_down_alert`, 2 test `engine_consumer_check`, 5 test `check_golive_gate`).
2. **Ruff linter:**
   - `uv run ruff check trading tests scripts` -> **All checks passed!**
3. **Cổng cứng VN (`scripts/measure_strategy.py`):**
   - Lệnh chạy: `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt`
   - Bốn con số cổng cứng:
     - **Tổng PnL chiến lược:** `-1,615,319,902`
     - **Tổng PnL mua-và-giữ:** `1,897,587,481,903`
     - **Chênh lệch (strat - BH):** `-1,899,202,801,806`
     - **Tổng số lệnh (SELL fills):** `1,514`
     - *(Dữ liệu bẩn giữ nguyên: 10.459 dòng trên 740 mã)*

---

## 6. Tuân Thủ Ràng Buộc Kỷ Luật
- `real_trading_enabled`: Giữ nguyên `false`.
- Không commit, không push git.
- Không sửa `config/config.yaml`, không sửa hay hiển thị `.env`.
- Không gọi API SSI đặt hay huỷ bất kỳ lệnh thật nào.
- Dữ liệu và bảng đo trung thực 100% từ terminal.


---

## Phụ lục — ghi chú của Claude (auditor), 19/09/2026

Ba task đạt. Task 1 **sửa được một chỗ sai trong kế hoạch của tôi**, và tôi đã triển khai bản vá
đợt 56 ra container bằng chính cơ chế đợt 54 viết ra.

### A. Những gì tôi tự chạy lại

```
801 passed in 36.39s   |  ruff: All checks passed!
cong cung VN: strat -1,615,319,902 | BH 1,897,587,481,903 | 1,514 lenh | 439 ma   <- khop
check_golive_gate.py  -> EXIT=2 (chan dung vi lech trien khai)
```

Hai bản vá chuông đúng và tối thiểu: `engine_consumer_check` đổi đúng hai dòng
(`if send_telegram(...): new_state[...]`), `docker_down_alert` chuyển `_write_last_alert` vào
nhánh gửi-thành-công.

### B. Task 1 sửa một chỗ tôi viết sai trong lịch tuần

Tôi xếp T3 là **"ngoài phiên"**. Báo cáo chỉ ra điều tôi không nghĩ tới: **lệnh chỉ huỷ được
trong phiên khớp lệnh liên tục** — sàn cấm huỷ/sửa trong ATO/ATC, và một lệnh đặt ngoài giờ thì
không huỷ kịp, nó **nằm lại qua đêm**. Với một bài kiểm mà toàn bộ an toàn dựa vào "huỷ ngay",
đặt ngoài giờ là bỏ mất chính cái van an toàn đó.

Khung đúng: **09:30–10:30** hoặc **13:15–14:00**. Tôi đã sửa bảng lịch trong brief.

### C. Và chọn mã là một cải thiện thật, không phải chi tiết

Tôi kiểm lại giá đóng cửa 18/09 rồi tự tính:

| Mã | Giá đóng | Giá đặt (93%) | 100 cp tốn | % NAV (5.021.712đ) |
|---|---|---|---|---|
| **VCB** (mặc định của script) | 59.900 | 55.707 | **5.570.700** | **111% — SSI từ chối** |
| HPG | 21.550 | 20.041 | 2.004.150 | 40% |
| IJC | 6.920 | 6.435 | 643.560 | 13% |
| **AAA** (đề xuất) | 7.260 | 6.751 | **675.180** | **13%** |

Chạy với mặc định `VCB` thì bài kiểm **chết ngay ở bước 1** vì không đủ sức mua — và ta sẽ không
biết `place_limit_order` có chạy được hay không. Đề xuất `--symbol AAA` là đúng, và lý do đúng:
nếu lệnh lỡ khớp, tài khoản vẫn còn **87% NAV** tiền mặt.

### D. Tôi triển khai bản vá đợt 56 — lần đầu dùng `:previous`

Cổng chặn `EXIT=2` vì image cũ hơn commit chạm `trading/` **6 giờ 45 phút** — đó chính là đợt 56
(`telegram.py`, `calendar_vn.py`). Container đang chạy **không có** bản vá `send_telegram`, tức
là thứ tuần go-live dựa vào.

Đây là dịp đầu tiên dùng cơ chế `:previous` mà đợt 54 viết vào `DEPLOYMENT.md`:

```
docker tag ...-collector:latest ...-collector:previous   -> 250fd4221613
docker tag ...-engine:latest    ...-engine:previous      -> d6133ff8b9ba
docker compose build collector engine
docker compose up -d --no-deps --force-recreate collector engine
```

Kiểm chứng **hai lớp**, đúng bài học 18/09 (so ID thôi là chưa đủ):

```
collector: run == tag  -> True      grep "FEE-ALARM-2" trong /app/trading/telegram.py   -> 1
engine   : run == tag  -> True      grep "def is_trading_day" trong calendar_vn.py      -> 1
check_golive_gate.py   -> EXIT=1    (muc 8 "Lech trien khai" da chuyen sang DAT)
```

Và `logs/bars_closed.log` đi từ 14 lên **16 dòng** — sống sót qua lần dựng lại **thứ tư**.

Giờ đã có điểm lùi thật: `:previous` trỏ đúng bộ image chạy tốt trước khi triển khai.

### E. Một chỗ lỏng có chủ ý, ghi lại để không ai tưởng là sơ ý

`docker_down_alert` dùng `if ok is not False` chứ không phải `if ok:`. Lý do: bốn test cũ truyền
`send=sent.append`, mà `list.append` trả `None` — `if ok:` sẽ làm chúng đổ, và brief bảo "chỉ
thêm test, không sửa test cũ".

Trong production hai cách **hoàn toàn như nhau**, vì `send_telegram` sau đợt 56 luôn trả `bool`
đúng nghĩa. Khác biệt chỉ lộ ra nếu ai đó truyền một hàm gửi khác trả `None` khi hỏng — lúc đó
`is not False` sẽ đóng dấu nhầm.

Cách dọn đúng là đổi bốn fake cũ thành `lambda t: (sent.append(t), True)[1]` rồi siết thành
`if ok:`. **Không làm tối nay** — nó đụng test cũ ngoài phạm vi, và hành vi production không đổi.

### F. Cổng go-live còn một cảnh báo, và nó sẽ tự hết

Mục 6 báo `89.5%` — đó là **độ phủ phiên chiều 18/09, đo ở `grace = 60`**. Thứ Hai 22/09 là phiên
đầu tiên chạy `grace = 20`, nên con số này sẽ được thay bằng số mới. Không phải việc phải chữa,
là việc phải **đo**.

### G. Việc còn treo

1. **Hai việc của chủ dự án trước 20:00 Chủ nhật:** `powercfg` và `holidays`. Không đổi.
2. **T3 chạy trong phiên 09:30–10:30 với `--symbol AAA`** — đã sửa vào brief.
3. Siết `is not False` thành `if ok:` (mục E) — sau tuần go-live.


### H. Tự soát: cảnh báo của đợt 56 **không tới được nơi bền** khi chạy trong container

Câu hỏi "đủ hay chỉ vừa đủ cho test xanh" chỉ đúng một chỗ.

Đợt 56 thêm `logger.warning(...)` vào `send_telegram` để việc gửi trượt **thôi im lặng**. Đợt 52
làm log bền bằng cách gắn `RotatingFileHandler` vào một logger. Nhưng hai đợt gắn vào **hai
logger khác nhau**:

```
trading/collector/main.py:526   alerts_logger = logging.getLogger("trading.alerts")   <- handler ben
trading/telegram.py:7           logger = logging.getLogger(__name__)  # = "trading.telegram"
```

Trong cây logger của Python, `trading.telegram` và `trading.alerts` là **anh em**, không phải cha
con — bản ghi của cái này **không** chảy qua handler của cái kia. Kiểm trong container:

```
telegram la con cua alerts?  ->  False
```

Hệ quả, chia theo nơi chạy:

| Chạy ở đâu | Cảnh báo gửi trượt đi đâu | Bền không |
|---|---|---|
| Script trên host (`daily-check`, `engine-consumer`, `docker-down-alert`) | `logs/*.log` qua `run_if_docker_up.sh` | **Bền** |
| **Trong container** (collector, engine) | stderr → `docker logs` | **Mất khi dựng lại** |

Và container bị dựng lại **bốn lần trong hai ngày**. Nên đúng cái dòng cảnh báo mà đợt 56 sinh ra
để ta thấy được, khi nó xảy ra trong collector, sẽ biến mất ở lần triển khai kế tiếp.

**Chưa cắn ai** — `docker-compose.yml` truyền `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` vào cả hai
container, nên nhánh "thiếu biến" không chạy; và 16 dòng trong `bars_closed.log` hiện đều là
alert bình thường. Nhưng nhánh "lỗi mạng" thì **đã chạy thật** hai lần (14/09, 16/09), và nếu nó
chạy trong container thì ta mất dấu.

**Cách chữa nhỏ hơn vẻ ngoài:** gắn handler vào logger `"trading"` thay vì `"trading.alerts"` —
một chuỗi, và cả hai logger con đều được phủ. Nhưng nó **đổi thứ chảy vào file** (mọi logger dưới
`trading.` chứ không riêng alerts), nên phải cân nhắc khối lượng và xoay vòng trước khi làm.
Đủ lớn để cần một brief, đủ nhỏ để không gấp.

**Không làm tối nay:** `trading/collector/main.py` là file collector đang chạy, và thứ Hai 22/09
là phép đo quyết định của đợt 52. Cùng lý do đã hoãn việc gom `is_trading_day` — đo xong đã.

Ghi vào việc của brief sau, **sau** phép đo T2.
