# Báo Cáo Đợt 58: Gợn Sóng Chưa Hết, và Thứ Không Lên Được VPS

**Ngày thực hiện:** 2026-09-19 (thứ Bảy)  
**Người thực hiện:** Gemini Flash 3.8 / Senior Dev  
**Người giao & kiểm định:** Claude (planner/auditor)  
**Kế hoạch:** `docs/superpowers/plans/2026-09-19-brief-dot-58-gon-song-va-thu-khong-len-vps.md`  
**Base commit:** `39c6364`  

---

## 1. Trạng Thái Mã Nguồn & Thay Đổi

### `git status --short`
```text
 M README.md
 M scripts/_alert_common.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/superpowers/research/2026-09-19-dot-58-gon-song-va-thu-khong-len-vps.md
?? tests/test_alert_common.py
```

### `git diff --stat` (đối với code sửa ở Đợt 58)
```text
 scripts/_alert_common.py | 4 +++-
 1 file changed, 3 insertions(+), 1 deletion(-)
```

---

## 2. Task 1 — Nơi Thứ Ba Của Gợn Sóng Đợt 56 (`scripts/_alert_common.py`)

### 2.1. Phân Tích & GitNexus Blast Radius
- `alert_and_fail` trong `scripts/_alert_common.py` là khuôn chuông tự kêu chung cho:
  - `scripts/deploy_drift_check.py` (dòng 155): `return alert_and_fail("[deploy-drift]", messages, send_telegram)`
  - `scripts/check_silent_engine.py` (dòng 141): `return alert_and_fail("[engine-cam]", messages, send_telegram)`
- Trước đây khi `send_telegram` ném exception, khối `except Exception as e` bắt lỗi và in `f"{prefix} GUI TELEGRAM HONG: ..."`. Khi Đợt 56 đổi `send_telegram` thành trả `False` thay vì ném exception, khối `except` thành code chết, làm mất dấu vết cảnh báo gửi hỏng trên 2 chuông này.
- **Blast Radius:** Rất thấp (LOW). Chỉ ảnh hưởng tới nhánh in log khi gửi thất bại của `[deploy-drift]` và `[engine-cam]`. Hàm luôn giữ nguyên `return 1` và giữ thứ tự in nội dung cảnh báo ban đầu trước khi gửi (`_print_safe(text)`).

### 2.2. Chi Tiết `git diff scripts/_alert_common.py`
```diff
diff --git a/scripts/_alert_common.py b/scripts/_alert_common.py
index 218db1a..ffc7ed6 100644
--- a/scripts/_alert_common.py
+++ b/scripts/_alert_common.py
@@ -30,7 +30,9 @@ def alert_and_fail(
     text = "\n".join(messages)
     _print_safe(text)
     try:
-        send(text)
+        ok = send(text)
+        if ok is False:
+            _print_safe(f"{prefix} GUI TELEGRAM HONG: send tra ve False")
     except Exception as e:
         _print_safe(f"{prefix} GUI TELEGRAM HONG: {type(e).__name__}: {e}")
     return 1
```

### 2.3. Ba Unit Tests Mới (`tests/test_alert_common.py`)
Đã tạo file mới `tests/test_alert_common.py` với 3 test cases:
1. `test_send_tra_false_in_gui_telegram_hong_va_tra_1`: `send` trả `False` -> stdout có dòng `[test-alert] GUI TELEGRAM HONG: send tra ve False`, trả về mã `1`.
2. `test_send_nem_exception_in_gui_telegram_hong_va_tra_1`: `send` ném ngoại lệ -> stdout có dòng `[test-alert] GUI TELEGRAM HONG: ConnectionResetError: Connection lost to Telegram`, trả về mã `1`.
3. `test_send_tra_true_khong_in_gui_telegram_hong_va_tra_1`: `send` trả `True` -> stdout in thông điệp cảnh báo ban đầu nhưng **KHÔNG** chứa `GUI TELEGRAM HONG`, trả về mã `1`.

### 2.4. Bằng Chứng Test Phân Biệt Được (Negative Test Experiment)
- **Thử nghiệm:** Tạm thời xóa nhánh `if ok is False: ...` trong `scripts/_alert_common.py` (khôi phục code cũ).
- **Kết quả:** `test_send_tra_false_in_gui_telegram_hong_va_tra_1` **LẬP TỨC ĐỔ (FAILED)**:
  ```text
  FAILED tests/test_alert_common.py::test_send_tra_false_in_gui_telegram_hong_va_tra_1 -
  AssertionError: assert '[test-alert] GUI TELEGRAM HONG: send tra ve False' in 'canh bao 1\ncanh bao 2\n'
  ```
- Khi khôi phục bản vá: Bộ test pass 100% (3/3 passed).

### 2.5. Kết Quả Grep Lại Toàn Repo
Quét toàn bộ repo tìm các nơi bọc `try/except` quanh lời gọi gửi Telegram (`send_telegram` hoặc `send`):
- `scripts/docker_down_alert.py:134`: Đã sửa ở Đợt 57 (`if ok is not False: _write_last_alert ... else: in thất bại`).
- `scripts/_alert_common.py:33`: Đã sửa ở Đợt 58 (`if ok is False: in thất bại`).
- `scripts/engine_consumer_check.py:147`: Nằm trong `except` của lỗi đọc NATS, không bọc try/except quanh `send_telegram`.
- Nơi duy nhất còn bọc `try: send_telegram(...) except Exception:` là:
  - **`scripts/.probe_dead_man_switch.py:48-58`**: Dòng 49 gọi `send_telegram`, dòng 50 kiểm `if ok:` / `else:`, nhưng vẫn bọc trong `try/except Exception as e`. Đúng như dự báo của Claude trong brief.

---

## 3. Task 2 — Mười Chín Công Cụ Không Lên Được VPS

### 3.1. Bảng Phân Loại 23 Dot-File `.py` Trong `scripts/`

| STT | Tên file | Trạng thái Git | Phân loại | Lý do & Căn cứ |
|:---:|---|:---:|:---:|---|
| 1 | `.probe_dead_man_switch.py` | Untracked | **CẦN TRÊN VPS** | Dùng diễn tập kiểm tra đường truyền Telegram và dead-man switch tại chỗ trên VPS (bước T4 tuần go-live). |
| 2 | `.probe_account_power.py` | Untracked | `chỉ cần máy dev` | Dò sức mua API SSI trực tiếp qua collector container; vận hành production đã có `check_real_order_readiness.py` và `check_golive_gate.py` đọc DB. |
| 3 | `.probe_backfill_daily.py` | Untracked | `chỉ cần máy dev` | Kiểm tra chunking daily trực tiếp với SSI API; production dùng collector định kỳ. |
| 4 | `.probe_bars_count.py` | Untracked | `chỉ cần máy dev` | Script 500 bytes đếm message stream NATS khi dev integration test. |
| 5 | `.probe_event_loop_block.py` | Untracked | `chỉ cần máy dev` | Đo thời gian chặn event loop `write_bars` (Brief 31 Task 3). Đã xong. |
| 6 | `.probe_rts_gap.py` | Untracked | `chỉ cần máy dev` | Khảo sát RTS giữa phiên; đã chuyển hóa thành test case `test_trailing_stop.py`. |
| 7 | `.probe_stream_observer.py` | Untracked | `chỉ cần máy dev` | Bắt message ephemeral stream BARS khi nghi ngờ NATS flake. |
| 8 | `.scan_mojibake.py` | **Tracked** (add nhầm) | `chỉ cần máy dev` | Quét encoding mã nguồn repo; chỉ dùng khi dev soạn thảo code. |
| 9 | `.fix_mojibake.py` | **Tracked** (add nhầm) | `chỉ cần máy dev` | Gỡ lỗi font tiếng Việt nhiều lớp; việc đã xong, repo đã sạch. |
| 10 | `.probe_hii_silent.py` | Untracked | `đã hết dùng` | Điều tra mã HII câm ở Brief 25-28. Nguyên nhân đã rõ, case đã đóng. |
| 11 | `.repro_nats_flake.py` | Untracked | `đã hết dùng` | Tái hiện flake của fixture NATS cũ; đã được fix bằng teardown chuẩn. |
| 12 | `.spike_backtest_operating_config.py` | Untracked | `đã hết dùng` | Vết nghiên cứu phái sinh VN30F 5m (09/08/2026). |
| 13 | `.spike_daily_backtest.py` | Untracked | `đã hết dùng` | Vết nghiên cứu backtest LEDGER-1 khung ngày. |
| 14 | `.spike_improve_derivative_strategies.py` | Untracked | `đã hết dùng` | Vết nghiên cứu 2 chiến lược phái sinh. |
| 15 | `.spike_margin_analysis_30m.py` | Untracked | `đã hết dùng` | Vết nghiên cứu ký quỹ phái sinh VN30F. |
| 16 | `.spike_new_indicators_5m.py` | Untracked | `đã hết dùng` | Vết thử nghiệm EMA/RSI trên phái sinh 5m. |
| 17 | `.spike_param_sensitivity_5m.py` | Untracked | `đã hết dùng` | Vết đo độ nhạy tham số phái sinh. |
| 18 | `.spike_risk_eod_derivative_strategies.py` | Untracked | `đã hết dùng` | Vết thử nghiệm rủi ro EOD phái sinh 14:20. |
| 19 | `.spike_rsi_combination_analysis.py` | Untracked | `đã hết dùng` | Vết phân tích RSI 70/30 phái sinh. |
| 20 | `.spike_rsi_timeframes.py` | Untracked | `đã hết dùng` | Vết phân tích RSI trên khung 10m/15m phái sinh. |
| 21 | `.spike_timeframe_sensitivity.py` | Untracked | `đã hết dùng` | Vết đo độ nhạy đa khung thời gian phái sinh. |
| 22 | `.spike_trailing_rsi_gate.py` | Untracked | `đã hết dùng` | Vết nghiên cứu trailing stop gated bởi RSI phái sinh. |
| 23 | `.spike_trailing_stop.py` | Untracked | `đã hết dùng` | Vết nghiên cứu ATR trailing stop phái sinh. |

### 3.2. Ba Câu Trả Lời Về Việc Xử Lý Dot-File

1. **`.probe_dead_man_switch.py` xử lý thế nào?**
   - **Lựa chọn 1 (Mở ngoại lệ `.gitignore`):** Thêm `!scripts/.probe_dead_man_switch.py` vào `.gitignore`.
     - *Ưu điểm:* Giữ nguyên tên gọi và đường dẫn trong các tài liệu/hướng dẫn đã soạn.
     - *Nhược điểm:* `.gitignore` phải gánh thêm ngoại lệ lẻ tẻ; tên file có dấu chấm dễ gây nhầm lẫn là file tạm/file ẩn.
   - **Lựa chọn 2 (Đổi thành script chuẩn không dấu chấm: `scripts/probe_dead_man_switch.py`):**
     - *Ưu điểm:* Thống nhất với kiến trúc của toàn bộ các công cụ vận hành khác (`spike_ssi_sdk_auth.py`, `check_golive_gate.py`, `confirm_real_order.py`). Mọi công cụ cần ship lên VPS đều là script chính thức không dấu chấm. Tự động được git track mà không cần sửa `.gitignore`.
     - *Nhược điểm:* Cần cập nhật một số câu lệnh trong runbook/tài liệu tham chiếu.
   - **Khuyến nghị:** Chọn **Lựa chọn 2** sau tuần go-live. Trong tuần này nếu cần chạy diễn tập T4 ngay trên VPS, có thể tạm thời áp dụng **Lựa chọn 1** hoặc copy thủ công.

2. **Hai file thêm sai luật (`.fix_mojibake.py`, `.scan_mojibake.py`):**
   - **Khuyến nghị:** **Trả về đúng luật.** Dùng `git rm --cached scripts/.fix_mojibake.py scripts/.scan_mojibake.py` để rút khỏi git tracking nhưng vẫn giữ file trên ổ cứng máy dev. Hai file này thuần túy phục vụ dev bảo trì text encoding trên máy cá nhân, không có lý do gì để ship vào git repository và đẩy lên VPS production.

3. **Câu thay thế soạn sẵn cho `scripts/README.md` (chỉ soạn, KHÔNG sửa file):**
   > *"1. **Dấu chấm đầu tên mang hai ý nghĩa bắt buộc: 'giữ có chủ ý cho môi trường dev, không nối vào pipeline' VÀ 'không ship vào git / không đưa lên VPS production'** (được tự động loại trừ bởi `.gitignore`). Mọi công cụ chẩn đoán hoặc vận hành cần thiết trên môi trường VPS PHẢI là script chính thức không mang dấu chấm đầu tên (hoặc được mở ngoại lệ tường minh trong `.gitignore`)."*

---

## 4. Task 3 — Đường Lệnh Thật Báo Bằng `alert()`, và `alert()` Nuốt Kết Quả

### 4.1. Mười Bốn Cảnh Báo Đi Qua `alert()` Trong `trading/real_orders.py`

| Dòng | Mức | Thông điệp cảnh báo | Tác động khi mất tin Telegram |
|:---:|:---:|---|---|
| 53 | `WARN` | Cảnh báo tài khoản cấu hình có NAV nhỏ hơn đáng kể (>10x) so với tài khoản khác | Mất cảnh báo cấu hình nhầm tài khoản, không chặn lệnh |
| 95 | `CRITICAL` | Không có snapshot vị thế -> từ chối xử lý lệnh thật cho symbol (fail-safe) | Lệnh bị chặn trong DB, người dùng không biết để kiểm tra sync vị thế |
| 105 | `CRITICAL` | Snapshot vị thế quá cũ (> 15 phút) -> từ chối xử lý lệnh thật | Lệnh bị chặn trong DB, người dùng không biết để kiểm tra sync vị thế |
| 130 | `CRITICAL` | Không có snapshot sức mua -> từ chối lệnh BUY thật | Lệnh BUY bị chặn trong DB, người dùng không biết |
| 141 | `CRITICAL` | Snapshot sức mua quá cũ (> 15 phút) -> từ chối lệnh BUY thật | Lệnh BUY bị chặn trong DB, người dùng không biết |
| 167 | `INFO` | Lệnh thật bị từ chối bởi Risk Manager (hạn mức ngày/drawdown) | Chỉ ghi log, không gửi Telegram |
| 178 | `INFO` | Sức mua không đủ 1 lô tối thiểu | Chỉ ghi log, không gửi Telegram |
| 191 | `INFO` | Lệnh bán bị từ chối bởi Risk Manager | Chỉ ghi log, không gửi Telegram |
| **209** | **`WARN`** | **`real order pending confirmation`** (Lệnh MUA mới cần người duyệt) | **MẤT CƠ HỘI HÀNH ĐỘNG**: Người dùng không nhận được `confirm_cmd`. Sau 15 phút lệnh hết hạn (`EXPIRED`)! |
| 253 | `CRITICAL` | Stop touch: không có snapshot vị thế -> từ chối | Lệnh cắt lỗ bị chặn, người dùng không biết |
| 263 | `CRITICAL` | Stop touch: snapshot vị thế quá cũ (> 15 phút) -> từ chối | Lệnh cắt lỗ bị chặn, người dùng không biết |
| 293 | `WARN` | Vị thế mới không có BUY fill trong real_order_fills -> fallback giá vốn | Mất log cảnh báo định giá trailing stop |
| 308 | `WARN` | Chạm stop nhưng chưa bán được (chưa settle T+2.5, sellable_qty=0) | Mất log cảnh báo kẹt hàng chưa về |
| **328** | **`WARN`** | **`REAL STOP TOUCH: pending SELL cho xac nhan`** (Cắt lỗ cần người duyệt) | **MẤT CƠ HỘI HÀNH ĐỘNG**: Người dùng không nhận được thông báo để bấm nút cắt lỗ. Đơn hết hạn sau 15 phút! |

**Kết luận:** Hai cảnh báo sống còn làm người dùng **mất hoàn toàn cơ hội hành động** nếu tin Telegram bị nuốt chính là **Dòng 209 (Pending BUY)** và **Dòng 328 (Pending SELL Stop Touch)**. Cả hai đều có thời hạn xác nhận nghiêm ngặt trong 15 phút (`PENDING_ORDER_TTL_MINUTES = 15`).

### 4.2. Dấu Vết Khi `send_telegram` Trả `False` Trong Luồng Nền
- `trading/alerts.py:37`: Gọi `threading.Thread(target=send_telegram, args=(text,), daemon=True).start()`. Luồng nền ném kết quả trả về vào hư vô (không biến nào hứng giá trị `bool`).
- Trong `trading/telegram.py`:
  - Dòng 7: `logger = logging.getLogger(__name__)` (tên logger là `"trading.telegram"`).
  - Khi gửi thất bại, hàm gọi `logger.warning(...)`.
- **Cây Logger & Đích đến:**
  - `trading.telegram` và `trading.alerts` là **hai logger anh em** ngang hàng, cùng là con của root logger. Bản ghi của `trading.telegram` **KHÔNG BAO GIỜ** chảy qua handler của `trading.alerts`.
  - Trong `trading/engine/main.py`, chỉ có `logging.basicConfig(level=logging.INFO, format="%(message)s")` gắn `StreamHandler` vào root logger.
  - Do đó, log warning gửi trượt Telegram chỉ xuất hiện tại **`stderr` của tiến trình container engine**, được Docker gom vào file log cục bộ của daemon (`docker logs engine`).
  - **Hoàn toàn không có file log bền nào trên host filesystem ghi lại sự kiện này.** Nếu container engine bị khởi động lại hoặc rebuild, toàn bộ dấu vết này biến mất.

### 4.3. Cách Chữa & Đánh Đổi

- **Phương án A: Chạy đồng bộ (Synchronous) cho mức hành động:**
  - `alert()` chạy đồng bộ `ok = send_telegram(text)` cho mức cần hành động (hoặc khi có `confirm_cmd`) và trả `bool` về cho `real_orders.py`.
  - *Ưu điểm:* `real_orders.py` biết ngay tin đã gửi được chưa để cập nhật trạng thái hoặc cảnh báo lặp lại.
  - *Nơi nó sẽ hỏng:* **Hỏng ở độ trễ (latency blocking).** `send_telegram` có timeout 5 giây qua Internet. Nếu mạng lag hoặc DNS nghẽn, event loop xử lý nến của engine bị đứng hình tới 5 giây, gây ứ đọng nến trên stream NATS. Ngoài ra, nếu chỉ áp dụng cho `CRITICAL` mà quên `WARN` thì 2 cảnh báo ở dòng 209 và 328 (vốn là `WARN`) vẫn bị nuốt.
- **Phương án B: Bọc luồng nền có Callback ghi nhận DB (`pending_real_orders`):**
  - Giữ luồng nền không chặn engine, nhưng khi `send_telegram` trả `False`, callback ghi cờ `telegram_notified = False` vào bảng `pending_real_orders` trong Postgres.
  - Đồng thời script giám sát định kỳ (hoặc heartbeat) kiểm tra nếu có pending order chưa được notify thì gửi bù.
  - *Ưu điểm:* Không chặn luồng realtime của engine, log bền vững trong DB.
  - *Nơi nó sẽ hỏng:* Vẫn có độ trễ nếu cơ chế gửi bù bị chậm nhịp so với TTL 15 phút.

### 4.4. Việc Này Có Chặn Go-Live Không?
- **Nói thẳng: KHÔNG CHẶN GO-LIVE tuần 22–26/09.**
- **Lập luận:**
  1. **Nguyên tắc an toàn vốn tuyệt đối (Fail-safe by design):** Nếu Telegram bị rớt mạng và người vận hành không nhận được tin, lệnh trong `pending_real_orders` sẽ tự động hết hạn (EXPIRED) sau 15 phút. **Không bao giờ có chuyện lệnh tiền thật tự động gửi lên sàn SSI khi chưa có sự xác nhận của con người.** Hệ thống thà bỏ lỡ cơ hội khớp lệnh (missed trade) còn hơn đặt lệnh sai. Vốn được bảo toàn an toàn 100%.
  2. **Quy trình trực chiến của người vận hành:** Trong tuần đầu go-live (đặc biệt T5–T6 khi bật cờ), người vận hành phải túc trực trước màn hình, theo dõi bảng điều khiển và kiểm tra database trực tiếp, không phó mặc hoàn toàn cho tin nhắn điện thoại.
  3. **Giữ ổn định tối đa trước go-live:** `trading/alerts.py` và `trading/real_orders.py` là các file cốt lõi đang hoạt động ổn định. Việc sửa kiến trúc luồng alert ngay sát phiên T5 tiềm ẩn nguy cơ sinh lỗi hồi quy (regression) cao hơn nhiều so với rủi ro rớt mạng tạm thời của Telegram.

---

## 5. Kiểm Định Tổng Thể Codebase (Ba Dòng Đo)

1. **Bộ kiểm thử Pytest:**
   - **804 passed in 62.32s** (Mốc cũ 801; bổ sung 3 unit tests mới cho `test_alert_common.py`).
2. **Ruff Linter:**
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

## 6. Tuân Thủ Kỷ Luật
- `real_trading_enabled`: Giữ nguyên `false`.
- Không commit, không push git.
- Không sửa `config/config.yaml`, không sửa `.env`.
- Không gọi API SSI, không đặt/huỷ lệnh thật.
- Không gửi bất kỳ tin nhắn Telegram thật nào trong đợt này.


---

## Phụ lục — ghi chú của Claude (auditor), 19/09/2026 (kiểm chứng lại sau đổi model sang Sonnet 5)

Ba task đạt, kiểm chứng độc lập từng con số — không có gì phải sửa lần này.

### A. Task 1 — kiểm lại bằng cách tự gỡ hàng rào

```
git diff --numstat scripts/_alert_common.py  ->  3   1
```

Khớp đúng "3 insertions(+), 1 deletion(-)" báo cáo nêu.

Tôi tự gỡ nhánh `if ok is False: ...` (không dùng bản của agent, tự sửa lại), chạy:

```
FAILED tests/test_alert_common.py::test_send_tra_false_in_gui_telegram_hong_va_tra_1
1 failed, 2 passed
```

Rồi khôi phục, `git diff --numstat` quay lại đúng `3  1` như ban đầu. Test **thật sự phân biệt
được**, không phải câu chuyện suông trong báo cáo.

`grep` lại xác nhận `.probe_dead_man_switch.py:48-58` là chỗ duy nhất còn `try/except` quanh
`send_telegram` — và đọc thấy nó **đã** kiểm `ok` đúng trước khi vào nhánh `except`, nên nhánh đó
giờ chỉ là code chết vô hại, không phải lỗ như `_alert_common.py` từng là. Đúng khoanh vùng của
báo cáo.

### B. Task 2 — đếm lại toàn bộ, khớp tuyệt đối

```
tong dot-file .py tren dia : 23   (dem lai bang PowerShell, khong tin so cu)
duoc git theo doi          :  4   (.fix_mojibake.py, .scan_mojibake.py, 2 file .json)
```

Liệt kê tên từng file rồi tự cộng ba nhóm của báo cáo: `1 + 8 + 14 = 23`. Khớp, và tên file trong
từng nhóm đúng với danh sách thật trên đĩa — không có file nào bị xếp nhầm nhóm hay bị bỏ sót.

Đề xuất "không đáng giữ dấu chấm cho `.probe_dead_man_switch.py`, chuyển thành script thường" là
lựa chọn nhất quán với câu hỏi hẹp mà tôi đặt lại ở phụ lục trước — nó **là** một ngoại lệ thật sự
cần dùng ở VPS (T4), nên đưa nó ra khỏi diện "không ship" thay vì mở thêm một dòng `!` nữa trong
`.gitignore` là gọn hơn. Câu thay thế soạn cho `scripts/README.md` diễn đạt đúng cả hai ý (giữ có
chủ ý + không ship), sẵn sàng dùng khi có brief sửa file đó.

### C. Task 3 — mọi con số khớp, và tôi tìm thêm được một bậc nặng hơn báo cáo nói

```
$ grep "alert(" trading/real_orders.py | wc -l   -> 14      (khop chinh xac)
dong 209 : alert("WARN", "real order pending confirmation", ...)      <- khop
dong 328 : alert("WARN", "REAL STOP TOUCH: pending SELL cho xac nhan...")  <- khop
```

Logger claim cũng đúng: `trading/engine/main.py:490` chỉ có
`logging.basicConfig(level=logging.INFO, ...)` gắn vào root logger, không có
`RotatingFileHandler` nào.

**Nhưng đây là chỗ tôi đào thêm được một bậc:** báo cáo giải thích lý do mất dấu vết là
*"`trading.telegram` và `trading.alerts` là hai logger anh em"* — đúng, nhưng chưa phải lý do sâu
nhất. `real_orders.py` chỉ được `trading/engine/main.py` import (không phải collector), và bản vá
log bền của đợt 52 **chỉ gắn vào `trading/collector/main.py`** — engine không có, chưa từng có.

Nghĩa là: **kể cả khi hai logger đó là cha con**, cảnh báo từ `real_orders.py` vẫn mất, vì
container engine không có `RotatingFileHandler` nào cả, không riêng gì `trading.telegram`. Đây
không phải một lỗi khác — nó là **cùng một lỗ, sâu hơn một bậc**: dot 52 chỉ vá một nửa hệ thống
(collector), và đường lệnh thật lại nằm ở nửa chưa vá (engine).

Kết luận "không chặn go-live tuần này" của báo cáo vẫn đứng vững — cơ chế hết hạn 15 phút là an
toàn thật (không đơn nào tự khớp), nên mất cảnh báo chỉ làm mất **cơ hội hành động kịp lúc**, không
làm mất tiền. Nhưng bậc sâu hơn này đáng ghi vào việc "sau tuần go-live": nếu áp bản vá log bền
cho engine, phải làm theo đúng khuôn `trading.alerts` + `logger "trading"` mà mục H đợt 57 đã đề
xuất — sửa một lần cho cả logger lẫn container, đừng vá riêng lẻ.

### D. Ba dòng kiểm định — chạy lại độc lập

```
801 -> 804 passed (dung 3 test moi)
ruff: All checks passed!
TONG: strat -1,615,319,902 | BH 1,897,587,481,903 | lenh 1,514 | ma sinh lenh 439   <- khop
```

### E. Việc còn treo, cập nhật lại

1. Hai việc chủ dự án trước 20:00 Chủ nhật: `powercfg`, `holidays` — không đổi.
2. Sau phép đo thứ Hai: logger `"trading"` cho **cả collector lẫn engine** (mục C mở rộng phạm
   vi so với mục H đợt 57 — trước đó tôi chỉ nói tới collector).
3. `.probe_dead_man_switch.py` → cân nhắc bỏ dấu chấm, thành script thường (mục B).
4. Hai file tôi thêm sai luật (`.fix_mojibake.py`, `.scan_mojibake.py`) — `git rm --cached` hoặc
   giữ nguyên có chủ ý, chủ dự án quyết.


### F. Tự soát: phạm vi mục C hẹp hơn thực tế — không phải chỉ 14 cảnh báo của `real_orders.py`

Mục C ở trên viết như thể lỗ "engine không có log bền" chỉ ảnh hưởng đường lệnh thật. Đếm lại
toàn bộ `alert()` chạy trong container engine:

```
trading/real_orders.py    14 loi goi   (WARN)
trading/engine/main.py    20 loi goi   (INFO/WARN/CRITICAL)
trading/engine/logic.py    1 loi goi
                          --
                          35 loi goi TRONG CUNG MOT CONTAINER khong co RotatingFileHandler nao
```

Bốn trong số 20 dòng của `engine/main.py` là **CRITICAL**, và ít nhất một dòng nghiêm trọng thật:

```python
# trading/engine/main.py:190-195
alert(
    "CRITICAL",
    "khong doc duoc NAV (account_nav_snapshot khong co dong cho tai khoan nay) "
    "— real capital = 0, MOI lenh that bi tu choi (fail-safe, khong roi ve "
    "account_balance_snapshot)",
    ...
)
```

Đây là lá chắn NAV — đúng cơ chế `check_golive_gate.py` (đợt 57) vừa đo. Nếu nó kêu và Telegram
trượt đúng lúc, không chỉ mất "cơ hội hành động" như với đơn chờ xác nhận — nó mất luôn **bằng
chứng vì sao mọi lệnh thật bị từ chối**, không ai debug lại được sau khi container dựng lại.

Và dòng `engine/main.py:332` chính là cảnh báo *"real pending orders expired without
confirmation"* — cảnh báo mà brief 57 Task 2 vừa chữa lỗi đóng dấu chống spam cho nó
(`engine_consumer_check.py` là job khác, không phải nguồn phát cảnh báo này; nguồn phát nằm ở
đây, trong engine). Việc chữa lỗi đóng dấu không giúp gì nếu bản thân tiến trình phát ra nó
không có nơi ghi bền.

**Kết luận không đổi, phạm vi thì có:** việc vá log bền cho engine (đã ghi ở mục C, và mục H đợt
57) không phải "vá thêm cho đường lệnh thật" — nó là vá cho **toàn bộ 35 điểm cảnh báo của
engine**, kể cả những cảnh báo không liên quan gì tới tiền thật. Không đổi mức ưu tiên (vẫn sau
phép đo thứ Hai), nhưng khi viết brief cho việc đó, phạm vi phải ghi đúng là "container engine",
không phải "đường lệnh thật".
