# Brief đợt 56 — Chặng cuối của chuỗi cảnh báo

Ngày giao: 19/09/2026 (thứ Bảy).
Base: `ebe110c` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Sáu đợt liền tôi hỏi một câu mà không ai trả lời được

*"Ông có nhận được cảnh báo Telegram không?"* — hỏi ở đợt 51, 52, 53, 54, 55. Chưa có lời đáp.

Hôm nay tôi thôi hỏi và đi tìm. Kết quả: **chặng cuối của chuỗi cảnh báo chưa bao giờ được kiểm,
và nó hỏng theo ba kiểu khác nhau, cả ba đều không ai biết.**

### 0.1. Bằng chứng: đã có tin không tới, và không ai hay

```
logs/heartbeat.log:1752   gan moc "2026-09-14 14:25:03 heartbeat-check start"
logs/heartbeat.log:2089   gan moc "2026-09-16 11:55:16 heartbeat-check SKIP: docker chua chay"
  [docker-down-alert] gui Telegram loi: URLError: <urlopen error [Errno 11001] getaddrinfo failed>

Traceback (most recent call last):
  File "scripts/heartbeat_check.py", line 347, in main
    send_telegram("\n".join(messages))
  File "trading/telegram.py", line 19, in send_telegram
    urllib.request.urlopen(req, timeout=5)
```

Bốn lần thất bại, tất cả trong `heartbeat.log`. Đáng chú ý nhất là lần **14/09 lúc 14:25 — trong
phiên**: một cảnh báo thật đã cố phát, tin **không tới**, và `heartbeat_check` **sập** thay vì
báo rằng nó không gửi được.

### 0.2. Ba kiểu hỏng, cùng một hàm

```python
# trading/telegram.py — toan bo phan than
def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return                                    # (A)
    ...
    urllib.request.urlopen(req, timeout=5)        # (B) (C)
```

**(A) Thiếu biến môi trường → im lặng trả về.** Không một dòng log. Đây là **công tắc tắt toàn bộ
hệ cảnh báo**, và nó không phát ra tiếng nào. Trên VPS, nếu cron không nạp `.env`, mọi chuông của
đợt 46–55 biến mất mà `exit 0` vẫn đẹp.

**(B) Ném lỗi ra ngoài.** Tám nơi gọi `send_telegram`, **bảy nơi không bọc `try`**:

```
scripts/daily_data_check.py:151
scripts/engine_consumer_check.py:132, :147, :176
scripts/heartbeat_check.py:231, :261, :347
scripts/docker_down_alert.py:120        <- noi DUY NHAT lam dung, xem §1.2b
```

Mạng trục trặc → **script sập**. Tôi kiểm chứng điều đó chứ không suy đoán: sau traceback
14/09 14:25, `logs/heartbeat.log` ghi `EXIT=1`; lượt 14:30 sau đó mới `EXIT=0`. Cảnh báo lúc
14:25 **không tới ai**, và vết duy nhất nó để lại là một cú sập.

**(C) Không đọc phản hồi.** `urlopen` trả về response rồi bị vứt. Telegram trả `{"ok": false, ...}`
trong vài trường hợp mà HTTP vẫn 200. Nên ngay cả probe hiện có (`scripts/.probe_dead_man_switch.py`)
cũng chỉ nói được *"Da goi xong, KHONG nem loi"* và phải nhờ người **mở điện thoại ra xem** —
đó chính là lý do câu hỏi của tôi sáu đợt liền không tự trả lời được.

Và đường thứ tám, qua `alert()`:

```python
# trading/alerts.py:37
threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
```

Lỗi trong luồng nền bị in ra stderr rồi trôi. Tiến trình chạy tiếp, `exit 0`.

**Tổng kết: gửi được thì không ai xác nhận, gửi hỏng thì hoặc im lặng hoặc làm sập script.**
Không có trạng thái thứ ba là "không gửi được, và tôi nói cho anh biết".

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `trading/telegram.py` | có sẵn | 1 |
| `tests/test_telegram.py` | **có sẵn** | 1 — được phép sửa, xem §1.3b |
| `trading/calendar_vn.py` | có sẵn | 3 — **chỉ thêm** |
| `scripts/daily_data_check.py` | có sẵn | 3 |
| `scripts/stream_health_check.py` | có sẵn | 3 |
| `tests/test_calendar.py` | có sẵn | 3 — **chỉ thêm** |
| `docs/superpowers/research/2026-09-19-dot-56-*.md` | **mới** | báo cáo |

**Task 2 không sửa file nào** — lập bảng.

**Không đụng:** `scripts/heartbeat_check.py` (cấm sửa), `scripts/engine_consumer_check.py`,
`scripts/docker_down_alert.py`, `trading/alerts.py`, `PaperBroker`, `trading/risk.py`,
`trading/strategies/*`, `trading/engine/logic.py`, `config/config.yaml`.

Ràng buộc chung: `real_trading_enabled` giữ `false`; không gọi SSI/BingX; **không in secret**
(kể cả một phần token); `.env` không sửa/không commit/**không mở để đọc giá trị**; **chỉ đọc DB**;
**không** `delete`/`purge`/`add`/`update` stream hay consumer NATS nào; **không dựng lại
container, không build image**; **không đăng ký hay sửa Scheduled Task**; không xoá file; **không
commit, không push**. Mọi `git diff` copy từ lệnh. Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

**Thêm một ràng buộc riêng đợt này: KHÔNG gửi tin Telegram thật trừ Task 1.4, và ở đó đúng
một tin.** Tuần này đã có năm tin do kiểm thử; đừng làm chủ dự án quen với việc bỏ qua chúng.

---

## Task 1 — `send_telegram` phải nói được "tôi không gửi được"

### 1.1. Hợp đồng mới

```python
def send_telegram(text: str) -> bool:
    """True = Telegram xac nhan da nhan. False = khong gui duoc (da ghi log ly do)."""
```

Ba điều **bắt buộc**:

1. **Không bao giờ ném.** Bảy trong tám nơi gọi không bọc `try` — hôm 14/09 điều đó làm sập
   `heartbeat_check` (`EXIT=1`). Hàm này bắt mọi exception, trả `False`.
2. **Thiếu token/chat_id → ghi log mức cảnh báo rồi trả `False`**, không im lặng trả về. Đây là
   thay đổi quan trọng nhất của cả task.
3. **Đọc phản hồi và kiểm `ok`.** Telegram trả JSON có trường `ok`. `ok != true` → `False`.

### 1.2. Cái bẫy phải tránh, nói trước để khỏi mất một vòng

**Đừng báo lỗi bằng `alert()`.** `trading/alerts.py:37` gọi `send_telegram` từ trong `alert()`;
nếu `send_telegram` thất bại rồi gọi ngược `alert()` thì thành **đệ quy vô hạn**, và nó sẽ nổ ở
đúng lúc tệ nhất — lúc mạng đang hỏng.

Dùng `logging` trần (`logging.getLogger(__name__).warning(...)`). Nhờ bản vá đợt 52, log của
collector đã chảy ra `/app/logs/bars_closed.log`, nên một dòng `logging` ở đây **tự động bền**.

**Và không in token.** Khi báo thiếu biến, nói *tên biến nào thiếu*, không nói giá trị, không
nói cả bốn ký tự cuối.

### 1.2b. Khuôn đã có sẵn trong repo — chép hình dạng, đừng tự nghĩ

`scripts/docker_down_alert.py:116-140` đã giải đúng bài này từ đợt 8, kèm tên nguyên tắc:

```python
def run_alert(now, holidays, send=send_telegram, stamp_file=SPAM_GUARD_FILE) -> int:
    """Mot lan kiem: quyet dinh, keu neu can. KHONG BAO GIO nem — chuong bao
    chet cam con te hon khong co chuong bao (FEE-ALARM-2). Tra 0 luon."""
    try:
        ...
        # In ly do ra stdout TRUOC khi gui — neu send_telegram nem exception
        # thi van con ban ghi o log (khuon heartbeat_check).
        _print_safe(msg)
        try:
            send(msg)
        except Exception as e:
            _print_safe(f"[docker-down-alert] gui Telegram loi: {type(e).__name__}: {e}")
            return 0
        ...
    except Exception as e:      # lop ngoai cung
        ...
```

Bốn điều nó làm đúng, và bạn phải giữ đủ bốn:

1. **Nguyên tắc có tên: `FEE-ALARM-2` — "chuông báo chết câm còn tệ hơn không có chuông báo".**
   Dùng lại đúng tên đó trong docstring của `send_telegram` để hai chỗ tra được về nhau.
2. **Ghi lý do TRƯỚC khi gửi.** Nếu việc gửi nổ thì bản ghi vẫn còn. Đây là thứ đã cứu ta hôm
   14/09 — không có nó thì cảnh báo 14:25 biến mất không dấu vết.
3. **`try` trong (quanh việc gửi) và `try` ngoài (lớp cuối).**
4. **`send=send_telegram` là tham số tiêm được**, nên test được mà không chạm mạng.

Đây cũng là lý do `docker_down_alert` là nơi **duy nhất** trong tám nơi để lại dòng
`"gui Telegram loi: URLError: ..."` trong log thay vì sập. Nó đã chứng minh khuôn này hoạt động
trên sự cố thật.

**Task 1 không thay thế khuôn đó** — nó bổ sung ở tầng dưới: `send_telegram` thôi ném, nên **bảy
nơi còn lại** được chữa một lượt mà không phải sửa bảy file (phần lớn nằm trong danh sách cấm).

### 1.3. Blast radius — làm trước khi sửa

`gitnexus_impact({target: "send_telegram", direction: "upstream"})`. Nó có 8 nơi gọi (7 script +
`alerts.py`). Nếu kết quả HIGH/CRITICAL: **báo cáo trước, đừng sửa rồi báo sau**.

Đổi kiểu trả về từ `None` sang `bool` là **tương thích ngược** với mọi nơi gọi hiện tại (không
nơi nào dùng giá trị trả về). Xác nhận điều đó bằng cách đọc cả 8 chỗ, và **nói rõ trong báo cáo**
là bạn đã đọc.

### 1.3b. Hai test cũ đang khoá đúng hợp đồng bạn sắp đổi — đọc trước khi gõ

`tests/test_telegram.py` **đã tồn tại** với hai test, và một trong hai sẽ vỡ nếu bạn không lường
trước:

```
test_telegram.py:7   test_noop_when_env_not_set      assert calls == []
test_telegram.py:16  test_sends_request_when_env_set  bat url/body/timeout qua urlopen gia
```

- Test thứ nhất **vẫn đúng** dưới hợp đồng mới: thiếu env thì vẫn không gọi `urlopen`. Chỉ thêm
  phần trả `False` và ghi log. **Không cần sửa.**
- Test thứ hai **sẽ vỡ**: nó thay `urlopen` bằng một hàm giả chỉ ghi lại tham số. Hợp đồng mới
  bắt bạn **đọc phản hồi** (`resp.read()` rồi `json.loads`), mà hàm giả đó không trả thứ đọc
  được.

Đây là tình huống **được phép sửa test cũ**, vì chính hợp đồng đang đổi — nhưng phải theo luật:

1. Sửa **tối thiểu**: chỉ làm hàm giả trả về một phản hồi đọc được. **Không** đổi ba `assert` về
   `url`, `body`, `timeout` — chúng vẫn phải đúng nguyên văn.
2. **Không đụng `tests/test_telegram_isolation.py`.** Nó là thứ bảo đảm cả suite không bao giờ
   gửi tin thật.
3. Dán `git diff tests/test_telegram.py` và nói rõ từng dòng đổi để làm gì.

**Và một hệ quả cần lường:** `test_telegram_isolation.py` chứng minh biến môi trường Telegram bị
**vô hiệu hoá trên toàn suite**. Nghĩa là sau Task 1, **mọi** test nào chạm `alert()` sẽ đi vào
đúng nhánh "thiếu token" và sinh một dòng log cảnh báo. Điều đó không làm hỏng test, nhưng nếu nó
làm output suite ồn tới mức khó đọc, hãy nói ra trong báo cáo thay vì âm thầm hạ mức log xuống
`debug` — hạ mức là làm hỏng chính thứ task này sinh ra để chữa.

### 1.4. Kiểm chứng

1. Suite đầy đủ pass (mốc **786**), ruff sạch.
2. Test mới (`tests/test_telegram.py`), **giả lập `urlopen`, không chạm mạng**:
   - thiếu `TELEGRAM_BOT_TOKEN` → trả `False` **và** có bản ghi log; **không ném**
   - `urlopen` ném `URLError` → trả `False`, **không ném**
   - phản hồi `{"ok": false}` → trả `False`
   - phản hồi `{"ok": true}` → trả `True`
   - **không test nào được để lọt một lời gọi mạng thật**
3. **Chứng minh test phân biệt được:** khôi phục tạm hành vi cũ ở nhánh (A) — `return` trần —
   rồi xác nhận test "thiếu token" **đổ**. Khôi phục, `git diff` của file đó phải **rỗng**.
4. **Một lần gửi thật, đúng một tin.** Chạy `scripts/.probe_dead_man_switch.py` **Phần A** (đã có
   sẵn, đừng viết script mới) và dán nguyên văn kết quả. Với hợp đồng mới, kết quả phải nói được
   **gửi thành công hay không** — không còn phải nhờ người mở điện thoại ra xem.

   Nếu `.env` chưa nạp vào shell: docstring của probe có sẵn đoạn nạp. **Đừng mở `.env` để đọc
   giá trị**, chỉ nạp vào biến môi trường.

---

## Task 2 — Bảng: mỗi chuông có thể bị nuốt ở đâu?

**Đọc thuần. Không sửa file nào.**

Bảy job trong `sched.sh`. Với **mỗi** job, lần theo đường từ "điều kiện đúng" tới "tin trên điện
thoại" và điền:

| Job | Phát cảnh báo bằng gì | Có bọc `try` quanh việc gửi không | Nếu gửi hỏng thì sao | Có ghi lại dấu vết không |
|---|---|---|---|---|

Ba cột cuối là phần có giá trị. Ví dụ đã biết để bạn đối chiếu cách làm:
`heartbeat_check.py:347` gọi thẳng, không bọc, gửi hỏng → **script sập**, dấu vết là traceback
trong `logs/heartbeat.log`.

Sau bảng, trả lời hai câu:

1. **Job nào hỏng im lặng nhất?** Tức là: gửi hỏng mà không để lại dấu vết nào trong
   `logs/*.log` lẫn log container.
2. **Sau Task 1, job nào vẫn còn lỗ?** Task 1 chỉ sửa `send_telegram`. Một script gọi nó, nhận
   `False`, rồi **bỏ qua giá trị trả về** thì vẫn `exit 0` như không có gì. Liệt kê chính xác
   những chỗ đó — **đừng sửa chúng**, phần lớn nằm trong danh sách cấm.

---

## Task 3 — `is_trading_day` về đúng nhà

Đợt 55 đếm được **ba** nơi tự chế cùng một vị từ:

```
scripts/docker_down_alert.py:73    probe = now.replace(hour=10, ...)         -> in_bar_check_window
scripts/daily_data_check.py:139    combine(date, time(10, 0))                -> is_trading_time
scripts/stream_health_check.py:405 combine(date, time(10, 0))                -> is_trading_time
```

Gốc: `trading/calendar_vn.py` có `is_trading_time` và `is_continuous_matching` (đều cấp **giây**)
nhưng **không có vị từ cấp NGÀY**.

### 3.1. Việc

Thêm vào `trading/calendar_vn.py` — **thuần bổ sung, không sửa hàm nào đang có**:

```python
def is_trading_day(d: date, holidays: set[date] | frozenset = frozenset()) -> bool:
```

Rồi cho **hai** chỗ gọi nó: `daily_data_check.py` và `stream_health_check.py`.

**Không đụng `docker_down_alert.py`.** Nó dùng `in_bar_check_window` của `heartbeat_check.py` —
file cấm sửa — và cách nó viết có chủ đích: docstring nói rõ nó cố tình hỏi lại chính
`heartbeat_check` để nếu định nghĩa ngày giao dịch đổi thì nó tự theo. Chạm vào là phá một quyết
định đã cân nhắc. **Ghi nó vào báo cáo như chỗ thứ ba còn lại, kèm lý do không gom.**

### 3.2. Kiểm chứng

1. Test mới trong `tests/test_calendar.py` (**chỉ thêm**): thứ Bảy → `False`; Chủ Nhật → `False`;
   ngày lễ trong danh sách → `False`; ngày thường không lễ → `True`.
2. **Hai chỗ gọi phải giữ nguyên hành vi.** Chạy lại chính bốn lượt dữ liệu thật của đợt 55 và
   **phải ra y hệt**:

   | Lệnh | Kỳ vọng |
   |---|---|
   | `stream_health_check.py --date 2026-09-12 --session sang` | `bo qua: ... la ngay nghi`, exit 0 |
   | `stream_health_check.py --date 2026-09-19 --session sang` | `bo qua: ... la ngay nghi`, exit 0 |
   | `stream_health_check.py --date 2026-09-18 --session sang` | exit 2, `0 nen [nguon: log]` |
   | `daily_data_check.py --date 2026-09-19` | exit 0, nhánh ngày nghỉ |

   Lệch bất kỳ dòng nào → **dừng, báo cáo**. Đây là refactor: hành vi bên ngoài **không được đổi**.
3. Sau khi gom, `grep` lại và xác nhận chỉ còn **một** nơi định nghĩa vị từ này (cộng
   `docker_down_alert` đứng riêng có lý do).

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: `gitnexus_impact` của `send_telegram`, `git diff trading/telegram.py`, 4 tiêu chí,
   **bằng chứng test phân biệt được**, và nguyên văn lần gửi thật.
3. Task 2: bảng bảy job + hai câu trả lời.
4. Task 3: `git diff` ba file, bốn lượt dữ liệu thật nguyên văn, kết quả `grep` sau khi gom.
5. Ba dòng: số test pass (mốc **786**), ruff, cổng cứng VN đủ bốn con số
   (`-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`).

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không sửa** `heartbeat_check.py`, `engine_consumer_check.py`, `docker_down_alert.py`,
  `trading/alerts.py`. Task 2 chỉ lập bảng; phát hiện lỗ thì báo cáo.
- **Không gửi quá một tin Telegram** (Task 1.4).
- **Không in secret**, kể cả một phần token.
- **Không dựng lại container, không build image, không sửa Scheduled Task.**
- **Không đổi hành vi bên ngoài ở Task 3** — đó là refactor, không phải sửa lỗi.
- **Không commit `README.md`.**

---

## 4. Việc của chủ dự án

1. **`config/config.yaml: holidays` chỉ còn ngày đã qua** (`2026-08-31`, `09-01`, `09-02`). Sau
   khi đợt 55 nối dây xong, danh sách này là thứ **duy nhất** chặn báo động giả ngày lễ giữa
   tuần. Cần bổ sung lịch nghỉ còn lại 2026 và 2027. Agent không được sửa `config.yaml`.
2. **`powercfg /change standby-timeout-dc 0`** — trước tối Chủ nhật. Nếu máy ngủ thì backfill
   20:30 lại chết và thứ Hai lại thiếu dữ liệu, đúng chuỗi đã xảy ra đêm 17/09.
3. **Phiên 22/09** — giao thức bốn bước đã sẵn ở báo cáo đợt 55.
4. **`README.md` 253 dòng đổi** — xác nhận rồi tôi commit.
5. **Diễn tập cửa xác nhận lệnh thật** — vẫn là cái chặn go-live kỹ thuật duy nhất còn lại.
6. **Q-1** và **`DELETE` dòng `TEST`** trong `orders`.

Lần này tôi **không** hỏi lại câu Telegram. Task 1.4 sẽ tự trả lời nó.
