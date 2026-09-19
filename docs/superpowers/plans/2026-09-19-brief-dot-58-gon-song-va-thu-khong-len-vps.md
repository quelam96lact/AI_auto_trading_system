# Brief đợt 58 — Gợn sóng chưa hết, và thứ không lên được VPS

Ngày giao: 19/09/2026 (thứ Bảy).
Base: `39c6364` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Ba việc, cả ba chạm tuần go-live 22–26/09. **Không đụng file mà phép đo thứ Hai phụ thuộc**
(`trading/collector/main.py`, `trading/calendar_vn.py`) — ba việc hoãn lại ở đợt 57 vẫn hoãn.

---

## Task 1 — Nơi thứ ba của gợn sóng đợt 56

Đợt 56 làm `send_telegram` thôi ném. Đợt 57 tìm ra và chữa **hai** nơi dựa vào việc nó ném.
Còn **một**:

```python
# scripts/_alert_common.py:31-35
try:
    send(text)
except Exception as e:
    _print_safe(f"{prefix} GUI TELEGRAM HONG: {type(e).__name__}: {e}")
return 1
```

`send_telegram` không ném nữa → nhánh `except` là **code chết** → dòng `GUI TELEGRAM HONG`
**không bao giờ in nữa**. `alert_and_fail` là khuôn chung của **`deploy-drift`** và
**`engine-cam`** (đợt 57 Task 2 đã lập bảng), nên hai chuông đó vừa mất câu báo "gửi trượt".

Không có hàng rào chống spam ở đây nên không có lỗi đóng dấu — thiệt hại thuần là **mất dấu vết**.

### 1.1. Việc

`send` là `Callable[[str], object]`, nên xử đúng cả hai đời hợp đồng:

```
send tra False        -> in "<prefix> GUI TELEGRAM HONG: send tra ve False"
send nem (hop dong cu) -> giu nguyen nhanh except
con lai               -> coi nhu gui duoc
```

**Chỉ sửa khối đó.** Không đổi `return 1`, không đổi `_print_safe(text)` chạy trước (khuôn
`FEE-ALARM-2`), không refactor gì khác.

### 1.2. Kiểm chứng

1. Test mới (**chỉ thêm**): `send` trả `False` → có dòng `GUI TELEGRAM HONG`, vẫn trả `1`;
   `send` ném → vẫn có dòng đó; `send` trả `True` → **không** có dòng đó.
2. **Chứng minh test phân biệt được:** tạm bỏ nhánh `False`, test phải đổ; khôi phục, `git diff`
   khớp đúng phần định sửa.
3. Sau Task 1, **grep lại toàn repo** xem còn chỗ nào bọc `try/except` quanh một lời gọi gửi
   Telegram mà chỉ bắt exception. Dán kết quả. Kỳ vọng còn đúng một chỗ:
   `scripts/.probe_dead_man_switch.py` — xem Task 2, đừng sửa vội.

---

## Task 2 — Mười chín công cụ không lên được VPS

### 2.1. Phát hiện

`scripts/README.md` (đợt 54) mô tả quy ước dấu chấm là *"giữ có chủ ý, không nối tự động vào
pipeline"*. Đúng một nửa. Nửa còn lại:

```
.gitignore:21   scripts/.spike_*.py
.gitignore:22   scripts/.repro_*.py
.gitignore:23   scripts/.probe_*.py

tong dot-file .py tren dia : 23
duoc git theo doi          :  4   (.fix_mojibake.py, .scan_mojibake.py,
                                    va hai file .json duoc "!" mo ngoai le)
```

**Dấu chấm không chỉ nghĩa là "giữ có chủ ý" — nó nghĩa là KHÔNG SHIP.** Mười chín công cụ chỉ
tồn tại trên máy này.

Hậu quả cụ thể cho tuần go-live:

- **`scripts/.probe_dead_man_switch.py`** là thứ ta dùng ở đợt 56 để chứng minh Telegram tới nơi,
  và là thứ T4 cần để diễn tập. **Nó không có trên bản clone mới, không có trên VPS.**
- Bản sửa của nó ở đợt 56 (kiểm `ok` thay vì chỉ "không ném") **chỉ nằm trên máy này** và sẽ mất
  nếu clone lại.
- Hai file **tôi** thêm hôm 18/09 (`.fix_mojibake.py`, `.scan_mojibake.py`) đang được theo dõi
  **vì tôi `git add` tường minh**, tức là tôi đã **phá luật `.gitignore` mà không biết**. Hai
  file đó đang ở trạng thái không nhất quán với 19 file anh em.

### 2.2. Và một chỗ dễ nhầm phải nói rõ

Có **hai họ tên gần giống nhau**, khác hẳn về việc ship:

| Họ | Ví dụ | Trong git? | Vai |
|---|---|---|---|
| `spike_*.py` (**không** dấu chấm) | `spike_ssi_sdk_auth.py` | **CÓ** | Bước trong runbook vận hành |
| `.spike_*.py` (**có** dấu chấm) | `.spike_daily_backtest.py` | **KHÔNG** | Vết nghiên cứu |

Đợt 53 đếm "10 tham chiếu tới `spike_`" — toàn bộ thuộc họ **thứ nhất**. Đừng lẫn hai họ.

### 2.3. Việc

**Không xoá, không thêm vào git, không sửa `.gitignore` trong đợt này.** Trả lời để chủ dự án
quyết:

1. **Ba nhóm nào cần lên VPS, nhóm nào không?** Đi qua 23 file, phân thành:
   `CẦN TRÊN VPS` / `chỉ cần trên máy dev` / `đã hết dùng`. Với nhóm đầu, nêu **vì sao** —
   phải trỏ được tới một câu trong runbook hoặc một bước trong tuần go-live.
2. **`.probe_dead_man_switch.py` xử lý thế nào?** Nó vừa là công cụ chẩn đoán vừa là bước T4.
   Nêu hai lựa chọn kèm đánh đổi: đưa vào git (đổi `.gitignore`) hay chuyển thành script thường
   không dấu chấm.
3. **Hai file tôi thêm sai luật** — giữ trong git, hay trả về đúng luật? Nêu ý kiến.
4. **`scripts/README.md` phải sửa câu nào?** Soạn câu thay thế nói đúng cả hai nửa: dấu chấm =
   giữ có chủ ý **và** không ship. **Soạn, đừng sửa file.**

---

## Task 3 — Đường lệnh thật báo bằng `alert()`, và `alert()` nuốt kết quả

**Đọc thuần. Không sửa. `trading/alerts.py` và `trading/real_orders.py` đều cấm sửa.**

`trading/real_orders.py` phát cảnh báo **14 lần**, tất cả qua `alert()`, không lần nào gọi thẳng
`send_telegram`. Mà `alert()` làm thế này:

```python
# trading/alerts.py:37
threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
```

Giá trị trả về của `send_telegram` — thứ đợt 56 sinh ra — **rơi vào luồng nền và biến mất**.

Nghĩa là: tuần sau, khi engine sinh một tín hiệu thật và ghi `pending_real_orders`, nó phát
`WARN "real order pending confirmation"` kèm câu lệnh xác nhận. **Nếu Telegram hỏng lúc đó, tin
không tới, không ai biết, và đơn tự hết hạn sau 15 phút.** Đúng kịch bản đã xảy ra chín lần
từ 14/08 tới 04/09.

Trả lời bốn câu:

1. **Có bao nhiêu cảnh báo trên đường lệnh thật đi qua `alert()`?** Liệt kê từng dòng
   `real_orders.py` kèm mức (`WARN`/`CRITICAL`) và nói cái nào **mất đi thì người dùng mất cơ hội
   hành động**.
2. **Nếu `send_telegram` trả `False` trong luồng nền thì còn dấu vết ở đâu?** Lần theo tới cùng:
   logger nào, handler nào, file nào. Nhớ kết luận mục H đợt 57 — `trading.telegram` **không**
   phải con của `trading.alerts`.
3. **Cách chữa rẻ nhất là gì?** Nêu **hai** phương án kèm đánh đổi. Gợi ý một hướng để đối chiếu,
   không phải để chép: `alert()` có thể chạy đồng bộ cho riêng mức `CRITICAL` và trả kết quả,
   giữ luồng nền cho `WARN`. Nói rõ phương án bạn chọn **sẽ hỏng ở đâu**.
4. **Việc này có chặn go-live không?** Nói thẳng. "Không chặn vì cửa xác nhận vốn cần người chủ
   động" là một câu trả lời hợp lệ nếu bạn lập luận được.

**Không sửa gì.** Đây là đầu vào cho quyết định của chủ dự án trước T5.

---

## 2. Phạm vi và ràng buộc

| File | Trạng thái | Task |
|---|---|---|
| `scripts/_alert_common.py` | có sẵn | 1 |
| `tests/test_alert_common.py` | **mới** (chưa tồn tại — đã kiểm) | 1 |
| `docs/superpowers/research/2026-09-19-dot-58-*.md` | **mới** | báo cáo |

**Task 2 và 3 không sửa file nào.**

**Không đụng:** `trading/collector/main.py`, `trading/calendar_vn.py` (phép đo thứ Hai phụ thuộc),
`trading/alerts.py`, `trading/real_orders.py`, `trading/telegram.py`, `scripts/heartbeat_check.py`,
`scripts/spike_ssi_sdk_place_order.py`, `scripts/confirm_real_order.py`, `.gitignore`,
`scripts/README.md`, `config/config.yaml`, `PaperBroker`, `trading/risk.py`,
`trading/strategies/*`, `trading/engine/logic.py`.

Ràng buộc chung: `real_trading_enabled` giữ **`false`**; **không gọi SSI, không đặt/huỷ lệnh**;
**không gửi tin Telegram nào** (đợt này không cần); không in secret; `.env` không sửa/không mở;
**chỉ đọc DB**; **không** đụng stream/consumer NATS; **không dựng lại container, không build
image, không tạo/xoá tag**; **không đăng ký/sửa Scheduled Task**; không xoá file; **không commit,
không push**. Mọi `git diff` copy từ lệnh. Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

---

## 3. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: `git diff scripts/_alert_common.py`, ba test, bằng chứng test phân biệt được, kết quả
   grep lại toàn repo.
3. Task 2: bảng phân loại 23 file, ba câu trả lời, câu thay thế soạn sẵn cho `scripts/README.md`.
4. Task 3: bốn câu trả lời.
5. Ba dòng: số test pass (mốc **801**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 4. Việc của chủ dự án

1. **`powercfg /change standby-timeout-dc 0`** và **`holidays` vào `config.yaml`** — trước 20:00
   Chủ nhật. Không đổi từ đợt 57, và vẫn là hai việc chặn phép đo thứ Hai.
2. **T3 thứ Ba 09:30–10:30:** `uv run python scripts/spike_ssi_sdk_place_order.py --symbol AAA --account 0434221`.
3. **T4 thứ Tư:** diễn tập cửa xác nhận, **bấm giờ**. Lưu ý Task 2: công cụ diễn tập hiện **không
   có trong git** — nếu ông định làm trên máy khác thì đọc kết luận Task 2 trước.
4. **Sau phép đo thứ Hai**, ba việc đã hoãn: logger `"trading"` (mục H đợt 57), gom
   `is_trading_day` (mục G đợt 56), siết `is not False` (mục E đợt 57).
