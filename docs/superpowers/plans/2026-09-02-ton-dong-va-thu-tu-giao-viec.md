# Tồn đọng sau 02/09 — thứ tự giao việc

Viết tối 02/09/2026, sau khi đóng đợt 8 (`0c9c85b`) và đợt 9 (`658589c`).
Cây làm việc sạch, đã push.

---

## 0. Cái chốt định đoạt thứ tự

**Phiên 03/09 là lần đầu toàn bộ `trading/` chạy code hiện tại.** Mọi thay đổi
chạm `trading/` đều đòi dựng lại container, và dựng lại ngay trước phiên đó là
tự huỷ phép đo. Nên tồn đọng chia làm hai nhóm theo đúng một tiêu chí: **có
chạm `trading/` hay không.**

| Nhóm | Giao khi nào |
|---|---|
| A — chỉ `scripts/`, `tests/`, `docs/` | **ngay, tối nay** |
| B — chạm `trading/` | **sau khi phiên 03/09 đóng cửa (14:45)** |
| C — chờ quyết định của chủ dự án | không phải việc của agent |
| D — ghi sổ, không lên lịch được | — |

---

## 1. Sáng 03/09, 08:00–08:55 — việc của chủ dự án, không giao agent

1. **Bật Docker Desktop.** 02/09 chứng minh nó không tự lên. Chuông mới
   (`0c9c85b`) khiến ta *biết* khi Docker chết, không khiến nó *sống*.
2. **Nạp token SSI hai bước** (`DEPLOYMENT.md §8.5`). Bước hai
   (`load_token_to_db.py`) là cầu nối sang DB và **chính nó hay bị quên**
   (sự cố 14/08). Nạp 08:30 ⇒ hết hạn ~16:30, phủ trọn phiên.
3. Để `trading-deploy-drift` (08:00) trả lời câu hỏi ảnh có lệch không.

**Ba dòng log đáng nhìn trong phiên:** `NAV lam real capital`;
`feed stale, forcing reconnect` (giờ chỉ kêu khi thật sự disconnect được —
cờ `_connected`, `f8e3392`); và bar 5m về đều trong `bars`.

---

## 2. NHÓM A — Brief đợt 10: sửa hai khiếm khuyết của phép đo chế độ

Giao được ngay. Không chạm `trading/` ⇒ không dựng lại container ⇒ không làm
bẩn phiên 03/09.

### Ràng buộc

- Chỉ sửa `scripts/market_regime.py`, `scripts/measure_market_regime.py`,
  `tests/test_market_regime.py`. **Không chạm `trading/`,
  `config/config.yaml`, `scripts/heartbeat_check.py`.**
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API đặt/huỷ lệnh SSI.
- Không `TRUNCATE`/`DROP`/xoá dòng — chỉ đọc `bars_daily`.
- Không in giá trị bí mật. `.env` không sửa.
- **Không đổi ngưỡng 0,40/0,60 và không đổi kỳ trong mẫu / ngoài mẫu.**
  Sửa khiếm khuyết ≠ dò lại tham số. Ai đổi ngưỡng lúc này là đang chỉnh cho
  số đẹp lên.
- Phát hiện ngoài phạm vi thì báo cáo, không tự sửa.

### A1 — Tín hiệu BÁN bị chặn nhầm (Mục 7.1 của báo cáo đợt 9)

`measure_market_regime.py` chỉ lấy signal từ chiến lược đang active, nên khi
`rule[regime] == "NONE"` thì `signal = None`. Nhưng cả ba chiến lược cổ phiếu
dùng chính `Signal(..., "SELL", held)` để **thoát** vị thế
(`trading/strategies/daily_breakout.py:87`). Hệ quả: vị thế mở trong `RISK_ON`
khi thị trường chuyển `NEUTRAL` **chỉ còn thoát được bằng trailing stop**.

Trái với chính docstring của hàm ("không mở vị thế mới").

**Sửa:** khi chế độ là `NONE`, chặn **BUY**, cho **SELL** đi qua. Vị thế đang
mở tiếp tục được quản lý bởi chiến lược đã mở nó.

→ *Kiểm chứng:* test mới `test_che_do_none_chan_mua_nhung_khong_chan_ban` —
dựng chuỗi bar tay, ép một tín hiệu SELL rơi vào ngày `NEUTRAL`, khẳng định
vị thế **có** đóng. Phá hoại: bỏ bản sửa ⇒ test phải đỏ, dán output đỏ.

### A2 — 199 phiên `RISK_OFF` đầu chuỗi là hiện vật (Mục 7.2)

Từ 2016-01-04 đến 2016-10-19 breadth **đúng bằng 0** — không phải thị trường
xấu mà vì chưa mã nào đủ 200 phiên lịch sử; 2016-10-20 nhảy thẳng lên 0,489.
Đó là **199/688 = 28,9%** toàn bộ số phiên `RISK_OFF`.

**Sửa:** khi mẫu số (số mã đủ 200 phiên) dưới một ngưỡng tối thiểu, breadth
là **không xác định** — ghi `regime = UNKNOWN` chứ không phải `RISK_OFF`.
Ngưỡng đề xuất: **50 mã**. Ngày `UNKNOWN` bị loại khỏi mọi thống kê và quy
tắc chuyển đổi không giao dịch trong những ngày đó.

Lý do chọn `UNKNOWN` thay vì cắt ngắn chuỗi: "không biết" và "thị trường xấu"
là hai trạng thái khác nhau, và hệ thống này đã một lần trả giá vì lẫn lộn
"im vì ngày nghỉ" với "im vì hỏng".

→ *Kiểm chứng:* test `test_khong_du_mau_thi_UNKNOWN` (49 mã ⇒ `UNKNOWN`,
50 mã ⇒ phân loại bình thường). Phá hoại: hạ ngưỡng về 0 ⇒ test đỏ.

### A3 — Chạy lại và ghi đè kết quả

Chạy lại cả Task 2 và Task 3 sau khi sửa, **giữ nguyên quy tắc đã đóng băng**
(`RISK_ON → daily_breakout`, còn lại không giao dịch). Cập nhật
`2026-09-02-breadth-daily.csv` và **thêm mục 8 vào báo cáo** với bảng đối
chiếu trước/sau. Không sửa Mục 1–7 — chúng là bản ghi của phép đo cũ.

**Kỳ vọng đã nêu trước:** −8,83 tỷ sẽ **bớt xấu** (vì SELL hết bị chặn). Nếu
kết quả đảo dấu thành dương và vượt mua-và-giữ thì **dừng lại và báo cáo** —
đó là dấu hiệu bản sửa làm sai điều gì đó, không phải phát hiện lợi thế.

### Tiêu chí hoàn thành nhóm A

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | A1 | test mới xanh + output đỏ nguyên văn khi bỏ bản sửa |
| 2 | A2 | test mới xanh + output đỏ nguyên văn khi hạ ngưỡng về 0 |
| 3 | Chuỗi breadth mới | số phiên `UNKNOWN` = 199, `RISK_OFF` còn 489 |
| 4 | A3 | bảng trước/sau ở Mục 8, kèm lệnh chạy lại chính xác |
| 5 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 6 | Lint | `uv run ruff check trading tests scripts` sạch |

---

## 3. NHÓM B — sau 14:45 ngày 03/09

### B1 — Hợp đồng chiến lược và sổ đăng ký (việc lớn nhất còn lại)

**Đính chính một nhận định sai của Claude ngày 02/09:** `momentum_breakout` và
`momentum_rsi` **không phải code chết**. Chúng thuộc đường **phái sinh**, dùng
hợp đồng khác: `derivative_backtest.py:57` chỉ gọi `compute_crossover` và
`strategy.qty` — không cần `on_bar`, không cần `warmup_bars`. Chúng có ba file
test riêng (`test_momentum_breakout_strategy.py`, `test_momentum_rsi.py`,
`test_momentum_breakout_derivative_integration.py`).

**Repo có HAI hợp đồng, không phải một cái bị thiếu.** Bản thiết kế phải tôn
trọng điều đó — một "hợp đồng thống nhất" ép cả năm chiến lược vào một khuôn
sẽ phá đường phái sinh.

| Hợp đồng | Ai gọi | Đòi gì |
|---|---|---|
| Cổ phiếu | `engine/logic.py`, `engine/main.py`, `backtest.py` | `on_bar`, `last_crossover`, `last_atr`, `warmup_bars`, `compute_crossover` |
| Phái sinh | `derivative_backtest.py` | `compute_crossover`, `qty` |

Việc cần làm:

1. **`Protocol` ở `trading/strategy.py` khai đủ hợp đồng cổ phiếu** — hiện
   thiếu `warmup_bars` và `compute_crossover`, hai thứ `engine/main.py:81,91`
   thật sự gọi. Protocol đang mô tả sai chính thứ nó tự nhận là mô tả.
2. **`octopus_pullback` thiếu `last_crossover`** ⇒ nạp vào engine sẽ chết ngay
   bar đầu (`logic.py:44` gọi vô điều kiện, mỗi bar). Nó backtest sạch, nên
   đây đúng là bẫy "đo xong đem triển khai thì nổ".
3. **Một test bắt buộc mọi chiến lược trong sổ đăng ký phải thoả hợp đồng của
   sổ đó.** Đây mới là thứ khiến việc chọn chiến lược an toàn — không phải
   trường config.
4. **Trường chọn chiến lược trong `Config` + `config.yaml`**, thay cho
   `SmaCrossStrategy()` đóng cứng ở `engine/main.py:71`.
5. **Giải quyết test đỏ** `test_cli_registry_no_longer_offers_sma_cross`.
   Nó khẳng định `sma_cross` đã gỡ có chủ ý (`11d1c7b`); Claude thêm lại ở
   `711683a` để đo và không xử lý mâu thuẫn. Câu hỏi đúng là "sổ đăng ký có
   nên chứa `sma_cross` không", không phải "sửa cho test xanh".

**Sau khi sửa: BẮT BUỘC dựng lại container** (`DEPLOYMENT.md §10`) và xác
nhận bằng grep chữ ký, không chỉ bằng test.

### B2 — Gộp `_print_safe`

Nay có **ba bản**: `heartbeat_check.py`, `deploy_drift_check.py`,
`docker_down_alert.py`. Bài học `4ea4c8d`: một công thức ba nơi thì chắc chắn
lệch. Gộp vào `trading/alerts.py`.

**Vì sao vẫn hoãn tới sau 03/09:** đây là hàm an toàn của chuông báo, và
chuông đã chết câm một lần vì đúng một dòng `print()` (`ed17539` → `51ff6de`).
Sửa chuông khi chưa quan sát được nó kêu trên code mới là làm mù. Sau phiên
03/09 sẽ có tín hiệu thực địa.

---

## 4. NHÓM C — chờ quyết định của chủ dự án

| | Việc | Ghi chú |
|---|---|---|
| C1 | **VPS Ubuntu** | `sched.sh` đã dùng chung cho cron, `DEPLOYMENT.md` đủ §1–§10. Cần chọn nhà cung cấp/thời điểm trước khi thành task kỹ thuật. |
| C2 | **Docker Desktop tự khởi động** | 02/09 chứng minh nó không tự lên. Một ô tick, nhưng là máy của chủ dự án. |
| C3 | **Lịch nghỉ lễ 2026** | Đã yêu cầu bỏ. Hệ quả còn treo: ngày lễ chưa khai báo sẽ làm 2A báo láo cả ngày. Chấp nhận có ý thức. |

---

## 5. NHÓM D — ghi sổ, không lên lịch được

- **Kiểm chứng backoff 429 thực địa.** Chỉ xảy ra khi có 429 thật, và cố tình
  gây ra là chính hành vi bản sửa sinh ra để diệt. Hành vi đã có test tất định
  (`[2, 4, 8, 16, 32, 64] … max 600s`).
- **Xoay log Windows.** `DEPLOYMENT.md §8` có logrotate cho Ubuntu, không có
  gì cho Windows. Ngày Docker tắt thêm ~85 dòng SKIP. Vẫn chưa cấp bách.

---

## 6. Thứ tự đề nghị

1. **Tối nay:** giao nhóm A (đợt 10).
2. **Sáng 03/09 08:00–08:55:** chủ dự án làm mục 1. Không giao agent gì chạm
   `trading/` trước 14:45.
3. **Chiều 03/09 sau 14:45:** giao B1, rồi B2. B1 trước vì B2 cần tín hiệu
   thực địa từ phiên vừa đóng.
4. C và D chờ quyết định, không xếp lịch.
