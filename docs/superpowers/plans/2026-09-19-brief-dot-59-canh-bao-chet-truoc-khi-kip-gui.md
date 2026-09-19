# Brief đợt 59 — Cảnh báo chết trước khi kịp gửi

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: `c559773` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Phát hiện: cảnh báo quan trọng nhất của tuần go-live gần như chắc chắn không bao giờ tới

### 0.1. Mã

```python
# scripts/confirm_real_order.py:206-210
except Exception as exc:
    storage.update_pending_order_status(order_id, "failed")
    traceback.print_exc()
    alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
    sys.exit(1)                      # <- NGAY LAP TUC

# trading/alerts.py:37
threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
```

`alert()` đẩy việc gửi sang một luồng **daemon** rồi trả về ngay. Dòng kế tiếp là `sys.exit(1)`.
Luồng daemon **bị giết khi tiến trình thoát** — Python không chờ nó. `send_telegram` có timeout
5 giây; nó có gần như **không** thời gian nào.

### 0.2. Tôi không suy luận — tôi đo

Dựng đúng hình dạng đó (luồng daemon ngủ 1 giây rồi ghi file, `sys.exit(1)` ngay sau khi start):

```
$ uv run python demo_daemon.py
exit=1

=== luong daemon co kip chay khong? ===
KHONG - luong bi giet truoc khi xong
```

### 0.3. Và repo **đã biết** điều này — chỉ là biết ở sai chỗ

```python
# scripts/.probe_dead_man_switch.py:104
time.sleep(2)  # nhuong CPU cho thread gui Telegram cua alert() kip chay

# scripts/.probe_dead_man_switch.py:107
time.sleep(3)  # "Doi them 3s cho cac thread Telegram con lai..."
```

Người viết probe **đã gặp đúng vấn đề này** và vá bằng `sleep`. Nhưng bản vá nằm trong một công
cụ chẩn đoán, còn `confirm_real_order.py` — nơi có tiền thật — thì **không có gì cả**.

### 0.4. Ba cảnh báo bị ảnh hưởng, và cả ba đều quan trọng

| Dòng | Mức | Thoát ở đâu | Nội dung | Mất đi thì sao |
|---|---|---|---|---|
| `:138` | **CRITICAL** | `sys.exit(1)` ở `:147` | `real order aborted - insufficient real buying/selling power` | Lá chắn sức mua **đã chặn** một lệnh thật, không ai được báo |
| `:195` | WARN | hết hàm → tiến trình đóng | `REAL order placed` | Lệnh thật **đã lên sàn** mà không có xác nhận ngoài terminal |
| `:209` | **CRITICAL** | `sys.exit(1)` ở `:210` | `real order placement FAILED` | Lệnh thật **hỏng** mà chủ dự án không biết. Đơn đã `failed` trong DB, nhưng không ai được báo |

**Ba chỗ, không phải hai.** `:138` và `:209` có cùng hình dạng chính xác: `alert(CRITICAL)` rồi
`sys.exit(1)` ngay sau. `:195` không gọi `sys.exit` nhưng hàm kết thúc ngay sau đó
(`finally` → `asyncio.run` trả về → `main()` hết), nên nó đua với việc đóng tiến trình y hệt.

Chỗ thứ tư — `:105` — là mức **INFO**, không gửi Telegram (`_NOTIFY_LEVELS` chỉ có `WARN` và
`CRITICAL`), nên **không dính**.

**Đây là thứ chặn T5.** Bật cờ mà cảnh báo "đặt lệnh thất bại" không bao giờ tới là đi ngược
toàn bộ việc đợt 46–58 đã làm.

### 0.5. Nghịch lý đáng ghi

Các script gọi **thẳng** `send_telegram` (`heartbeat_check`, `daily_data_check`,
`engine_consumer_check`, `docker_down_alert`) đều **đồng bộ** → chúng **không** dính lỗi này.
Chỉ script dùng API "gọn hơn" là `alert()` mới dính. Đường dùng đúng chuẩn lại là đường hỏng.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `trading/alerts.py` | có sẵn — **gỡ cấm riêng cho Task 1**, chỉ thêm | 1 |
| `scripts/confirm_real_order.py` | có sẵn — **gỡ cấm riêng cho Task 1** | 1 |
| `tests/test_alerts.py` | có sẵn | 1 — **chỉ thêm** |
| `scripts/.probe_dead_man_switch.py` → `scripts/probe_dead_man_switch.py` | đổi tên | 2 |
| `scripts/README.md` | có sẵn | 2 |
| `docs/superpowers/research/2026-09-19-dot-59-*.md` | **mới** | báo cáo |

**Không đụng:** `trading/collector/main.py`, `trading/calendar_vn.py` (phép đo thứ Hai phụ thuộc),
`trading/real_orders.py`, `trading/telegram.py`, `scripts/heartbeat_check.py`,
`scripts/spike_ssi_sdk_place_order.py`, `config/config.yaml`, `.gitignore`, `PaperBroker`,
`trading/risk.py`, `trading/strategies/*`, `trading/engine/logic.py`.

Ràng buộc chung: `real_trading_enabled` giữ **`false`**; **không gọi SSI, không đặt/huỷ lệnh**;
**không gửi tin Telegram thật**; không in secret; `.env` không sửa/không mở; **chỉ đọc DB**;
không đụng stream/consumer NATS; **không dựng lại container, không build image**; **không đăng
ký/sửa Scheduled Task**; **không commit, không push**. Mọi `git diff` copy từ lệnh. Thiếu thì ghi
**"CHƯA LÀM"**, **không bịa**.

---

## Task 1 — Cho người gọi cơ hội chờ, mà không đổi hành vi của ai

### 1.1. Vì sao không dùng `sleep`, và không chuyển sang đồng bộ

Hai cách hiển nhiên đều sai:

- **`time.sleep(3)` trước `sys.exit`** — như probe làm. Chạy được, nhưng là đoán: ngủ thừa thì
  chậm, ngủ thiếu thì vẫn mất tin, và không ai biết nó đã gửi được hay chưa.
- **Làm `alert()` đồng bộ** — sẽ chặn vòng lặp sự kiện của engine tối đa 5 giây mỗi cảnh báo.
  Đợt 58 Task 3 đã nêu đúng rủi ro này: ứ nến NATS. **Không được làm.**

### 1.2. Cách làm: `alert()` trả về luồng

```python
def alert(level: str, msg: str, **fields) -> threading.Thread | None:
    ...
    t = threading.Thread(target=send_telegram, args=(text,), daemon=True)
    t.start()
    return t
    # muc INFO (khong gui) -> tra None
```

**Đây là thay đổi thuần bổ sung.** Hiện `alert()` trả `None` và **không nơi nào dùng giá trị trả
về** — 35 điểm gọi trong `trading/`, cộng các script. Tiến trình dài (collector, engine) bỏ qua
giá trị trả về → **hành vi không đổi một chút nào**, kể cả Monday.

Rồi `confirm_real_order.py` dùng nó ở **cả ba** chỗ `WARN`/`CRITICAL` (`:138`, `:195`, `:209`):

```python
t = alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
if t is not None:
    t.join(timeout=6)        # 5s timeout cua send_telegram + bien
sys.exit(1)
```

`join` có timeout nên **không bao giờ treo vô hạn** — kể cả khi mạng chết hẳn.

### 1.3. Bài học đợt 57 phải áp dụng ở đây

Khi đổi hợp đồng một hàm, câu hỏi không chỉ là *"ai dùng giá trị trả về?"* mà còn *"ai dựa vào
hành vi cũ?"*. Đợt 56 đổi `send_telegram` thôi ném và làm hỏng `docker_down_alert` vì tôi chỉ hỏi
câu đầu.

Lần này hỏi cả hai, và **trả lời trong báo cáo**:

1. Có nơi nào gán kết quả của `alert()` không? (`grep` và dán kết quả)
2. Có nơi nào **dựa vào việc `alert()` trả về ngay lập tức** không — tức là nếu ai đó vô ý `join`
   trong tiến trình dài thì sẽ hỏng ở đâu?
3. Chạy `gitnexus_impact` trên `alert`. Nếu HIGH/CRITICAL: **báo cáo trước, đừng sửa rồi báo sau**.

### 1.4. Kiểm chứng

1. Suite đầy đủ pass (mốc **804**), ruff sạch.
2. Test mới trong `tests/test_alerts.py` (**chỉ thêm**):
   - `alert("CRITICAL", ...)` trả về một `Thread` **còn sống hoặc đã xong**, không phải `None`
   - `alert("INFO", ...)` trả `None` (không gửi thì không có luồng)
   - `join()` trên kết quả đó **kết thúc** trong thời gian hợp lý với `send_telegram` giả
   - **Không test nào chạm mạng thật.**
3. **Chứng minh test phân biệt được:** tạm đổi `alert()` về `return None`, test phải đổ; khôi
   phục, `git diff` khớp đúng phần định sửa.
4. **Phép thử quyết định — tái hiện chính lỗi này:** viết một kịch bản nhỏ (trong báo cáo, không
   cần thành file trong repo) dùng `alert()` thật với `send_telegram` bị thay bằng hàm giả ghi
   file sau 1 giây, rồi `sys.exit()`:
   - **không** `join` → file **không** xuất hiện (tái hiện lỗi)
   - **có** `join` → file **xuất hiện** (bản vá ăn)

   Dán cả hai kết quả. Không chứng minh được cặp này thì Task 1 **chưa xong**, dù test xanh.

---

## Task 2 — Đưa công cụ diễn tập lên được VPS, và sửa câu mô tả sai

Đợt 58 kết luận: `.probe_dead_man_switch.py` **cần trên VPS** (T4 dùng nó), nhưng `.gitignore:23`
loại mọi `scripts/.probe_*.py`. Đề xuất đã chốt: **bỏ dấu chấm** thay vì mở thêm ngoại lệ.

### 2.1. Việc

1. **Đổi tên** `scripts/.probe_dead_man_switch.py` → `scripts/probe_dead_man_switch.py`.
   Dùng `git mv` nếu được; file hiện **chưa được theo dõi** nên có thể phải `git add` sau khi đổi
   tên — nói rõ bạn đã làm cách nào.
2. **Sửa mọi tham chiếu tới tên cũ.** `grep` toàn repo trước khi đổi và sau khi đổi, dán cả hai.
3. **Áp câu thay thế cho `scripts/README.md`** mà chính báo cáo đợt 58 đã soạn — nói đúng cả hai
   nửa: dấu chấm = giữ có chủ ý **và** không ship. Thêm một dòng nêu ngoại lệ: công cụ cần trên
   VPS thì **không mang dấu chấm**.
4. **Trả hai file về đúng luật:** `scripts/.fix_mojibake.py` và `scripts/.scan_mojibake.py` đang
   được theo dõi trái `.gitignore` vì tôi `git add` tường minh hôm 18/09.

   **Soạn lệnh `git rm --cached`, đừng chạy.** Đây là thay đổi chỉ-số-hoá (file vẫn nằm trên đĩa)
   nhưng nó **xoá file khỏi repo từ commit sau**, nên chủ dự án quyết. Nêu rõ đánh đổi: bỏ theo
   dõi thì máy mới không có công cụ dò/sửa mojibake — mà lỗi mojibake **đã xảy ra thật** ngày
   18/09.

   Nếu bạn cho rằng nên **giữ** chúng trong git (và thay vào đó bỏ dấu chấm như mục 1), nói thẳng
   — đó là một kết luận hợp lệ và có lẽ nhất quán hơn.

### 2.2. Kiểm chứng

- `probe_dead_man_switch.py` **có trong `git status`** (tức là không còn bị `.gitignore` nuốt).
- `grep` tên cũ toàn repo → **rỗng**, trừ các file báo cáo lịch sử trong `docs/` (không sửa docs cũ).
- Suite pass, ruff sạch.
- **Không chạy probe** (nó gửi Telegram thật — để dành cho T4).

---

## Task 3 — Còn CLI ngắn hạn nào dính lỗi mục 0 không?

**Đọc thuần.** Task 1 chỉ chữa `confirm_real_order.py`. Tìm xem còn ai.

Tiêu chí: một script **kết thúc nhanh** (CLI, job theo lịch) mà gọi `alert()` ở mức `WARN`/
`CRITICAL` rồi thoát mà không chờ.

Tôi đã tìm sơ bộ và thấy hai nhóm, hãy kiểm lại và mở rộng:

```
scripts/confirm_real_order.py   :138 :195 :209   <- Task 1 chua (:105 la INFO, khong dinh)
scripts/.probe_dead_man_switch.py :74 :80             <- da co sleep, khong phai lo
```

Trả lời:

1. Còn script nào khác không? Với mỗi cái: nó có thoát ngay sau `alert()` không?
2. Tôi đã xác định `:105` là `INFO` (không gửi → không dính) và `:138` là `CRITICAL` +
   `sys.exit(1)` (dính, đã đưa vào Task 1). **Kiểm lại kết luận này** — nếu bạn thấy khác, nói ra
   trước khi sửa.
3. `trading/engine/main.py` và `trading/collector/main.py` có dính không? Giải thích **vì sao
   không** (nếu đúng là không) — câu trả lời phải nói tới vòng đời tiến trình, không phải cảm giác.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: ba câu trả lời mục 1.3, `git diff` hai file, bốn tiêu chí mục 1.4, **đặc biệt là cặp
   kết quả có/không `join`**.
3. Task 2: kết quả `grep` trước/sau, `git status` chứng minh file mới được theo dõi, lệnh
   `git rm --cached` soạn sẵn, câu README mới.
4. Task 3: ba câu trả lời.
5. Ba dòng: số test pass (mốc **804**), ruff, cổng cứng VN đủ bốn con số
   (`-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`).

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không làm `alert()` đồng bộ** — mục 1.1.
- **Không thêm `sleep`** ở bất kỳ đâu trong code production.
- **Không sửa** `trading/real_orders.py` (14 cảnh báo của nó chạy trong engine, tiến trình dài,
  không dính lỗi này).
- **Không vá log bền cho engine** — việc riêng, sau phép đo thứ Hai, phạm vi là **cả container
  engine** chứ không riêng đường lệnh thật (phụ lục F đợt 58).
- **Không gom `is_trading_day`**, **không siết `is not False`** — vẫn hoãn tới sau thứ Hai.
- **Không chạy probe**, không gửi Telegram.

---

## 4. Việc của chủ dự án

1. **`powercfg /change standby-timeout-dc 0`** và **`holidays` vào `config.yaml`** — trước 20:00
   Chủ nhật. Nhắc lần thứ ba vì cả hai đều chặn phép đo thứ Hai.
2. **Quyết hai file mojibake** (Task 2 mục 4): bỏ theo dõi cho đúng luật, hay bỏ dấu chấm để giữ?
3. **T3 thứ Ba 09:30–10:30:** `uv run python scripts/spike_ssi_sdk_place_order.py --symbol AAA --account 0434221`.
4. **T5 chỉ bật cờ sau khi Task 1 xong.** Nếu đợt này không hoàn thành, **lùi T5** — bật cờ với
   cảnh báo "đặt lệnh thất bại" không bao giờ tới là điều tôi không khuyến nghị.
