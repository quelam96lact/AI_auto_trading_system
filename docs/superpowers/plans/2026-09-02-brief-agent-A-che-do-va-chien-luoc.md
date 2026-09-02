# Brief — Agent A (người đã làm đợt 9: chế độ thị trường)

Giao tối 02/09/2026. Hai phần, **phần 2 bị khoá thời gian**.

Bạn được giao tiếp phần này vì bạn đã ở sâu trong `market_regime.py`,
`STRATEGIES` và `trading/backtest.py` — không ai đọc lại từ đầu rẻ hơn bạn.

**Trước hết: báo cáo đợt 9 của bạn đã được audit và CHẤP NHẬN.** Chạy lại độc
lập Task 3 cho **8/8 con số tái lập đúng đến từng đồng**, kể cả
`−666.801.741.520`. Đã commit `658589c`. Việc bạn báo cáo con số ngoài mẫu xấu
thay vì quay lại chỉnh ngưỡng chính là chốt chặn quan trọng nhất của brief, và
nó đã giữ. Ghi chú audit nằm ở Mục 7 của báo cáo — đọc trước khi làm phần 1.

---

## PHẦN 1 — Làm ngay (chỉ `scripts/`, `tests/`, `docs/`)

### Ràng buộc

- Chỉ sửa `scripts/market_regime.py`, `scripts/measure_market_regime.py`,
  `tests/test_market_regime.py`, và báo cáo đợt 9.
- **Không chạm `trading/`, `config/config.yaml`, `scripts/heartbeat_check.py`.**
  Chạm `trading/` ⇒ dựng lại container ⇒ làm bẩn phiên 03/09.
- **Không đổi ngưỡng 0,40/0,60, không đổi kỳ trong mẫu / ngoài mẫu.**
  Sửa khiếm khuyết ≠ dò lại tham số.
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API đặt/huỷ lệnh SSI.
- Không `TRUNCATE`/`DROP`/xoá dòng — chỉ đọc `bars_daily`.
- Không in giá trị bí mật. `.env` không sửa.
- Ngoài phạm vi thì báo cáo, không tự sửa.

### A1 — Tín hiệu BÁN bị chặn nhầm

`measure_market_regime.py` chỉ lấy signal từ chiến lược đang active, nên khi
`rule[regime] == "NONE"` thì `signal = None`. Nhưng cả ba chiến lược cổ phiếu
dùng chính `Signal(..., "SELL", held)` để **thoát** vị thế
(`trading/strategies/daily_breakout.py:87`). Hệ quả: vị thế mở trong `RISK_ON`,
khi thị trường chuyển `NEUTRAL`, **chỉ còn thoát được bằng trailing stop** —
không bao giờ thoát theo luật của chiến lược. Trái với chính docstring của hàm
("không mở vị thế mới").

**Sửa:** chế độ `NONE` chặn **BUY**, cho **SELL** đi qua. Vị thế đang mở tiếp
tục được quản lý bởi chiến lược đã mở nó.

→ *Kiểm chứng:* test `test_che_do_none_chan_mua_nhung_khong_chan_ban` — dựng
chuỗi bar tay, ép một tín hiệu SELL rơi vào ngày `NEUTRAL`, khẳng định vị thế
**có** đóng. Phá hoại: bỏ bản sửa ⇒ test phải đỏ, dán output đỏ nguyên văn.

### A2 — 199 phiên `RISK_OFF` đầu chuỗi là hiện vật

Từ 2016-01-04 đến 2016-10-19 breadth **đúng bằng 0** — không phải thị trường
xấu mà vì chưa mã nào đủ 200 phiên lịch sử; 2016-10-20 nhảy thẳng lên 0,489.
Đó là **199/688 = 28,9%** toàn bộ số phiên `RISK_OFF`, nằm trọn trong kỳ trong
mẫu.

**Sửa:** mẫu số (số mã đủ 200 phiên) dưới **50** ⇒ breadth **không xác định**,
ghi `regime = UNKNOWN`. Ngày `UNKNOWN` bị loại khỏi mọi thống kê, và quy tắc
chuyển đổi không giao dịch trong những ngày đó.

Vì sao `UNKNOWN` chứ không cắt ngắn chuỗi: **"không biết" và "thị trường xấu"
là hai trạng thái khác nhau.** Hệ thống này đã trả giá một lần vì lẫn "im vì
ngày nghỉ" với "im vì hỏng" (sự cố 01/09) — đừng lặp lại khuôn đó.

→ *Kiểm chứng:* test `test_khong_du_mau_thi_UNKNOWN` (49 mã ⇒ `UNKNOWN`;
50 mã ⇒ phân loại bình thường). Phá hoại: hạ ngưỡng về 0 ⇒ test đỏ.

### A3 — Chạy lại, giữ nguyên quy tắc đã đóng băng

Chạy lại Task 2 và Task 3 với **đúng quy tắc cũ** (`RISK_ON → daily_breakout`,
còn lại không giao dịch). Cập nhật `2026-09-02-breadth-daily.csv`, **thêm Mục 8**
vào báo cáo với bảng đối chiếu trước/sau. **Không sửa Mục 1–7** — đó là bản ghi
của phép đo cũ, giữ nguyên để đối chiếu được.

**Kỳ vọng nêu trước khi chạy:** −8,83 tỷ sẽ **bớt xấu** (vì SELL hết bị chặn).
Nếu kết quả **đảo dấu thành dương và vượt mua-và-giữ** thì **DỪNG LẠI và báo
cáo** — đó là dấu hiệu bản sửa làm sai điều gì đó, không phải phát hiện lợi thế.
Khoảng cách đang là −666,80 tỷ; không bản sửa nào đóng nổi khoảng đó.

### Tiêu chí hoàn thành phần 1

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | A1 | test mới xanh + output đỏ nguyên văn khi bỏ bản sửa |
| 2 | A2 | test mới xanh + output đỏ nguyên văn khi hạ ngưỡng về 0 |
| 3 | Chuỗi breadth mới | `UNKNOWN` = 199 phiên, `RISK_OFF` còn 489 |
| 4 | A3 | bảng trước/sau ở Mục 8 + lệnh chạy lại chính xác |
| 5 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 6 | Lint | `uv run ruff check trading tests scripts` sạch |

Mọi con số phải kèm lệnh chạy lại. Số không tái lập được thì không tính.

---

## PHẦN 2 — KHOÁ tới sau 14:45 ngày 03/09

**Không bắt đầu trước mốc đó.** Phần này chạm `trading/` ⇒ dựng lại container
⇒ huỷ phép đo phiên đầu tiên chạy code mới. Chờ Claude bật đèn.

### B1 — Hợp đồng chiến lược và sổ đăng ký

**Repo có HAI hợp đồng, không phải một cái bị thiếu.** Đây là đính chính một
nhận định sai của Claude ngày 02/09 — `momentum_breakout` và `momentum_rsi`
**không phải code chết**, chúng thuộc đường phái sinh và có ba file test riêng.

| Hợp đồng | Ai gọi | Đòi gì |
|---|---|---|
| Cổ phiếu | `engine/logic.py`, `engine/main.py`, `backtest.py` | `on_bar`, `last_crossover`, `last_atr`, `warmup_bars`, `compute_crossover` |
| Phái sinh | `derivative_backtest.py:57` | `compute_crossover`, `qty` |

Một "hợp đồng thống nhất" ép cả năm chiến lược vào một khuôn **sẽ phá đường
phái sinh**. Thiết kế phải tôn trọng hai hợp đồng.

Việc cần làm:

1. `Protocol` ở `trading/strategy.py` khai **đủ** hợp đồng cổ phiếu — hiện
   thiếu `warmup_bars` và `compute_crossover`, hai thứ `engine/main.py:81,91`
   thật sự gọi. Protocol đang mô tả sai chính thứ nó tự nhận là mô tả.
2. `octopus_pullback` thiếu `last_crossover` ⇒ nạp vào engine chết ngay bar đầu
   (`logic.py:44` gọi vô điều kiện). Nó backtest sạch — đúng bẫy "đo xong đem
   triển khai thì nổ".
3. **Một test bắt buộc mọi chiến lược trong sổ đăng ký phải thoả hợp đồng của
   sổ đó.** Đây mới là thứ khiến việc chọn chiến lược an toàn — không phải
   trường config.
4. Trường chọn chiến lược trong `Config` + `config.yaml`, thay cho
   `SmaCrossStrategy()` đóng cứng ở `engine/main.py:71`.
5. Test đỏ `test_cli_registry_no_longer_offers_sma_cross`: nó khẳng định
   `sma_cross` đã gỡ có chủ ý (`11d1c7b`); Claude thêm lại ở `711683a` để đo
   và không xử lý mâu thuẫn. Câu hỏi đúng là **"sổ đăng ký có nên chứa
   `sma_cross` không"**, không phải "sửa cho test xanh". Nếu bạn thấy câu trả
   lời không hiển nhiên, **hỏi lại thay vì tự quyết**.

**Sau khi sửa: BẮT BUỘC dựng lại container** (`DEPLOYMENT.md §10`) và xác nhận
bằng grep chữ ký, không chỉ bằng test. Đây chính là lỗi đã để collector/engine
chạy image 15/08 suốt hai tuần.
