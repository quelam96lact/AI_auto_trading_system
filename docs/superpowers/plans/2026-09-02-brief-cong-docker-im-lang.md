# Brief đợt 8 — Cổng Docker đang giết chuông báo trong im lặng

Viết 02/09/2026, ngày lễ Quốc khánh, ~15 giờ trước phiên 03/09.

---

## 0. Phát hiện buộc phải viết brief này

Hôm nay (02/09) Docker tắt cả ngày. Đo được:

```
tong SKIP: 85  |  tong dong: 325     (logs/heartbeat.log)
2026-09-02 08:00:02 deploy-drift    SKIP: docker chua chay
2026-09-02 15:30:01 daily-data-check SKIP: docker chua chay
```

**85 lần bỏ qua liên tiếp. Không một tin Telegram nào.**

Hôm nay là ngày lễ nên im lặng đó vô hại. Nhưng cổng Docker
(`scripts/run_if_docker_up.sh`, `8ba0238`, do chính đợt trước dựng) không
biết hôm nay là ngày lễ — nó im vì **Docker tắt**, không phải vì **ngày
nghỉ**. Cùng một sự im lặng đó sẽ xảy ra y hệt lúc 09:00 ngày 03/09 nếu
Docker Desktop chưa được bật.

Kịch bản 03/09 nếu không sửa: không có collector ⇒ không có bar ⇒ không có
giao dịch ⇒ và **không có cảnh báo nào nói rằng không có gì đang chạy**.
Dòng `SKIP` nằm trong một file log không ai mở.

Đây đúng bài học FEE-ALARM-2: *một dead-man's switch chết câm còn tệ hơn
không có dead-man's switch*, vì nó tạo cảm giác đang được canh. Cổng Docker
hôm qua đổi một loại tiếng ồn (lỗi kết nối DB) lấy một loại im lặng nguy
hiểm hơn. Phải trả lại tiếng kêu cho trường hợp này.

### Vì sao việc này làm được, và làm được ngay hôm nay

`trading/telegram.py:8` — `send_telegram` chỉ dùng `urllib` + hai biến môi
trường. **Không chạm DB, không chạm Docker.** Nghĩa là đúng lúc Docker
chết, đường báo động vẫn còn sống. Không có lý do kỹ thuật nào để im.

---

## 1. Ràng buộc — đọc trước khi gõ dòng đầu tiên

- **Không sửa bất kỳ file nào trong `trading/`.** Được phép `import` từ đó
  (chỉ đọc), không được sửa. Đây là điều kiện để phiên 03/09 vẫn là phép đo
  sạch: không đổi image, không dựng lại container.
- **Không sửa `scripts/heartbeat_check.py`.** Nó đã bị sửa ba lần trong
  ngày 01/09 và một lần đã làm chuông chết câm (`ed17539` → `51ff6de`).
  Được `import` từ nó, không được sửa nó.
- **Không sửa `config/config.yaml`.**
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API đặt/huỷ lệnh SSI.
- Không in giá trị bí mật ra bất cứ đâu (được phép nhắc tên biến).
- `.env` không nằm trong git — không sửa, không commit.
- Việc phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.

---

## 2. Task 1 — `scripts/docker_down_alert.py` (file mới)

Một script độc lập, chạy được khi Docker đã chết. Nhiệm vụ: quyết định
**có nên kêu không**, và kêu.

### Quy tắc quyết định

| Tình huống | Hành vi |
|---|---|
| Trong khung 08:00–15:00, ngày giao dịch (T2–T6, không phải ngày lễ) | **GỬI Telegram** |
| Ngoài khung giờ, hoặc T7/CN, hoặc ngày lễ trong `config.yaml` | im lặng, thoát 0 |
| Đã gửi trong vòng 30 phút gần nhất | im lặng, thoát 0 (chống spam) |

Khung 08:00–15:00 T2–T6 là **đúng khung của scheduled task heartbeat** — xem
`DEPLOYMENT.md:225`. Không tự nghĩ ra khung khác.

### Yêu cầu bắt buộc

1. **Dùng lại logic ngày lễ đang có, không chép lại.** `heartbeat_check.py`
   đã có `in_bar_check_window(ts, holidays)` (dòng 76) và cách nạp
   `holidays` từ `config.yaml` (dòng 217–219). Bài học `4ea4c8d`: một công
   thức hai nơi thì sớm muộn lệch — và lệch ở đây nghĩa là hai chuông bất
   đồng về "hôm nay có phải ngày giao dịch không".
   → *Trước khi import, kiểm tra `heartbeat_check.py` an toàn khi import*
   (không chạy việc gì ở mức module). Nếu **không** an toàn: **dừng lại,
   báo cáo**, đừng tự ý cấu trúc lại `heartbeat_check.py` — nó nằm ngoài
   phạm vi và là file nhạy cảm nhất trong repo.

2. **Không bao giờ được ném exception.** Đây là chuông báo. `main()` bọc
   toàn bộ trong `try/except Exception`, hỏng thì in dấu vết rồi trả 0.
   Gửi Telegram hỏng cũng phải để lại dấu vết ở stdout (khuôn `_alert` của
   `scripts/deploy_drift_check.py`).

3. **Chống spam bằng file dấu**: `logs/.docker_down_last_alert` chứa epoch
   lần gửi cuối. Đọc hỏng/không có ⇒ coi như chưa từng gửi (fail-safe
   nghiêng về **kêu**, không nghiêng về im).

4. **In an toàn**: dùng khuôn `_print_safe` như hai script kia. stdout bị
   chuyển hướng ra file nên Windows chọn cp1252; một ký tự tiếng Việt
   ngoài bảng đó giết cả tiến trình — đã xảy ra thật 01/09.

### Nội dung tin nhắn

Phải trả lời được "cái gì đang không chạy và hậu quả là gì", ví dụ:

```
[CRITICAL] Docker khong chay luc 09:15 ngay giao dich 03/09.
Collector/engine deu dung. Khong co bar moi, khong co lenh.
Cac job giam sat dang bi bo qua — day la tin nhan DUY NHAT ban se nhan.
```

Câu cuối là phần quan trọng nhất: nói rõ đây không phải cảnh báo trong một
chuỗi, mà là cái duy nhất.

---

## 3. Task 2 — Nối vào cổng, và sửa thứ tự nạp `.env`

Trong `scripts/run_if_docker_up.sh`:

**Vấn đề thứ tự:** hiện `.env` được nạp **sau** phép kiểm Docker. Nhánh
Docker-chết thoát trước khi `TELEGRAM_BOT_TOKEN` tồn tại, nên
`send_telegram` sẽ lặng lẽ `return` ở dòng 12 (`if not token ... return`)
— gửi hụt mà không báo lỗi. **Phải nạp `.env` trước khi kiểm Docker.**

Thứ tự mới:
1. `.env` không tồn tại ⇒ ghi SKIP, thoát 0 (giữ nguyên hành vi cũ).
2. Nạp `.env`, đặt `PYTHONIOENCODING=utf-8`.
3. Kiểm Docker. Nếu chết ⇒ ghi dòng SKIP **như cũ** rồi gọi
   `docker_down_alert.py`, ghi kết quả vào cùng file log, thoát 0.
4. Docker sống ⇒ chạy job như cũ, không đổi gì.

**Không xoá dòng `SKIP` cũ.** Nó là bằng chứng lịch sử; tin Telegram là thứ
thêm vào, không phải thứ thay thế.

**Một thay đổi nhỏ để kiểm chứng được:** cho tên container lấy từ biến môi
trường có mặc định —
`${DOCKER_GATE_CONTAINER:-ai_auto_trading_system-postgres-1}`. Lý do không
phải "cho linh hoạt" mà là: **không có nó thì không thể chứng minh nhánh
Docker-chết hoạt động mà không phải tắt Docker thật** — và tắt Docker thật
đêm trước phiên 03/09 là việc không nên làm.

---

## 4. Task 3 — Test, và tiêu chí hoàn thành

File mới `tests/test_docker_down_alert.py`. Test **tất định**: không
`sleep`, không so giờ tường (đồng hồ Windows ~15,6 ms làm test giờ tường
chập chờn — đã dính 01/09). Truyền `now` vào hàm, `monkeypatch` phần gửi.

Bắt buộc có bốn test:

1. `test_gio_giao_dich_docker_chet_thi_keu` → có gửi.
2. `test_ngay_le_thi_im` — dùng đúng `2026-09-02` trong `config.yaml`.
3. `test_da_gui_trong_30_phut_thi_im` — file dấu mới ⇒ không gửi lần hai.
4. `test_gui_hong_khong_lam_chet_script` — `send_telegram` ném exception ⇒
   hàm vẫn trả 0 và **để lại dấu vết ở stdout**.

### Kiểm chứng phá hoại (bắt buộc, theo lệ dự án)

Với test 1 và test 4: cố tình phá code cho test đỏ, **dán nguyên văn output
đỏ vào báo cáo**, rồi khôi phục. Test không chứng minh được là nó biết bắt
lỗi thì không tính là test.

### Tiêu chí hoàn thành — kiểm chứng được, không mơ hồ

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Viết `docker_down_alert.py` | `uv run python scripts/docker_down_alert.py` chạy được khi Docker **đang lên**, không gửi gì (vì Docker sống thì gate không gọi tới nó — chạy tay để chắc nó không nổ) |
| 2 | Bốn test | `uv run pytest tests/test_docker_down_alert.py -v` → 4 passed |
| 3 | Phá hoại | output đỏ nguyên văn của test 1 và test 4 trong báo cáo |
| 4 | Nối vào cổng | `DOCKER_GATE_CONTAINER=khong-ton-tai scripts/run_if_docker_up.sh test-gate.log test-gate echo hi` → `logs/test-gate.log` có dòng SKIP **và** một tin Telegram thật tới máy chủ dự án (nếu đang trong khung giờ; nếu ngoài khung thì phải **không** có tin — nói rõ trong báo cáo là bạn kiểm ở tình huống nào) |
| 5 | Không hồi quy | `scripts/run_if_docker_up.sh test-gate2.log test-gate2 echo hi` (Docker đang lên) → log có `start`, `hi`, `EXIT=0` |
| 6 | Suite sạch | `uv run pytest -m "not integration" -q` → không có test nào đỏ thêm so với trước |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |

Xoá `logs/test-gate*.log` sau khi xong.

---

## 5. Việc KHÔNG làm trong đợt này

- **Không gộp `_print_safe`** (task C1). Vẫn hoãn tới sau phiên 03/09 vì lý
  do cũ: sửa chuông báo khi không quan sát được nó kêu là làm mù.
- **Không sửa `heartbeat_check.py`** kể cả khi thấy chỗ đáng sửa.
- **Không đụng `trading/`** ⇒ không dựng lại container.
- **Không tra lịch nghỉ lễ 2026** — chủ dự án đã yêu cầu bỏ.
- **Không tự bật/tắt Docker Desktop.**

---

## 6. Hai việc thuộc quyết định của chủ dự án, không giao agent

1. **Bật Docker Desktop tự khởi động cùng Windows.** Hôm nay chứng minh
   Docker không tự lên. Bản sửa trên khiến ta *biết* khi nó chết; nó không
   khiến Docker *sống*. Sáng 03/09 vẫn phải bật Docker bằng tay trước 08:00.
2. **VPS Ubuntu (B3)** — vẫn chờ quyết định hạ tầng, không phải task kỹ thuật.

Ghi thêm để không quên: `logs/heartbeat.log` nay thêm ~85 dòng mỗi ngày
Docker tắt. Xoay log trên Windows (B2) vẫn chưa cấp bách, nhưng con số đã
đổi so với lần đo trước.
