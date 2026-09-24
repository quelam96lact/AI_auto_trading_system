# Brief đợt 87 — Mở hướng sổ lệnh VN30F1M: thăm dò an toàn và ghi thử một phiên

Ngày giao: 24/09/2026 (tối). **Thực hiện trong phiên 25/09/2026 (thứ Sáu), bắt đầu 09:03 giờ VN.**
Base: main `79708f5`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao chọn hướng này

Dự án đã có **năm phép đo âm liên tiếp**: crypto, VN regime-timing, VN kỹ thuật 3 mã, VN kỹ thuật 48 mã,
và VN30F1M trong phiên (đợt 85, 18/18 không tín hiệu). Cả năm đều dùng **giá và khối lượng đã gộp thành
nến**. Chưa phép đo nào chạm tới **sổ lệnh** hay **dòng lệnh có chiều**.

Tối 24/09 tôi đọc file luồng thật mà một spike cũ đã ghi trong phiên 07/08
(`scripts/.spike_derivative_stream_sample.jsonl`, 1,39 MB, 13:40–13:42, mã `41I1G8000`). SSI **có**
phát hai loại dữ liệu đó cho hợp đồng phái sinh:

```
QUOTE: {"bid_prices": [1909.7, 1909.6, ... 10 bước], "bid_volumes": [16, 15, ...],
        "ask_prices":  [1910, 1910.1, ... 10 bước],   "ask_volumes": [3, 4, ...]}
TRADE: {"price": 1910, "quantity": 1, "side": "B", "total_volume": 164182}
```

- 3.471 QUOTE trong 120 giây, tức **~29 tin/giây**, luôn đủ **10 bước giá** mỗi bên.
- 397 TRADE trong 120 giây, tức **~3,3 lệnh/giây**, trường `side` là `B`/`S` (chiều chủ động).
- Ước tính một phiên có khoảng **470 nghìn QUOTE và 54 nghìn TRADE**.

**Vì sao phải bắt đầu ghi ngay:** loại dữ liệu này gần như chắc chắn **không có lịch sử** để tải về.
Muốn đo được thì phải tự ghi từ hôm nay, và cần khoảng **20 phiên** mới đủ để sàng lọc. Mỗi ngày chưa ghi
là một ngày dữ liệu mất vĩnh viễn.

**Đây mới là bước 1.** Đợt này không đo tín hiệu. Nó chỉ trả lời: (a) có ghi được **mà không làm hỏng
collector đang chạy thật** không, và (b) ghi một phiên đầy đủ trông như thế nào.

---

## 1. Hai rủi ro chưa ai biết câu trả lời

Đây là lý do Task 1 phải làm trước và có điều kiện dừng cứng.

**Rủi ro A — Kết nối luồng thứ hai có đá kết nối của collector không?** Collector đang giữ một kết nối
luồng tới SSI. Máy ghi sẽ mở kết nối **thứ hai** cùng tài khoản. Nếu SSI chỉ cho một phiên luồng mỗi tài
khoản, collector sẽ bị ngắt **giữa phiên**. Tôi đã kiểm spike 07/08 (chạy song song với collector): nến
13:25–14:00 của HPG/IJC/AAA có đủ, **nhưng không chứng minh được gì**, vì log `bars_closed.log` không lưu
tới ngày đó, và nến trong DB có thể đến từ đợt nạp lại toàn bộ 30/08. **Chưa biết.**

**Rủi ro B — Máy ghi làm mới token có làm hỏng token của collector không?** Token SSI nằm ở hai chỗ và
hay lệch nhau (memory `dev-env-gotchas` mục 7): spike dùng file `scripts/.ssi_sdk_token.json` qua
`_ssi_spike_common.make_auth()`, còn collector đọc bảng `ssi_auth_state` trong Postgres. Nếu SSI xoay
vòng refresh token (mỗi token chỉ dùng một lần), máy ghi làm mới token có thể khiến token collector đang
giữ **mất hiệu lực**. **Chưa biết.**

---

## 2. Ràng buộc

- **Không** sửa `trading/`, **không** sửa hay restart collector/engine hay bất kỳ container nào.
- **Không** sửa `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` và **không dùng nó nguyên trạng**: nó
  đọc mã hợp đồng từ `.spike_derivative_contract_symbol.json`, mà file đó **vẫn ghi `41I1G8000` đã đáo
  hạn 20/08**. Chạy nguyên trạng sẽ subscribe vào mã chết, ghi file rỗng, và dẫn tới kết luận sai là
  "không có dữ liệu".
- **Không** ghi dữ liệu sổ lệnh vào Postgres. Khoảng 500 nghìn tin mỗi phiên, ghi ra file nén.
- **Không** gọi bất kỳ method đặt lệnh nào.
- Không thêm dependency. Không commit, không push.
- Nền hiện tại: **785 passed**, ruff sạch.

---

## Task 0 — Tối 24/09: viết máy ghi (chưa chạy thật)

Viết `scripts/record_vn30f_orderbook.py`:

- Tham số **bắt buộc** `--symbol` (không mặc định, không đọc file `.spike_*`: bài học đợt 84, mọi mã
  hợp đồng ghim cứng đều sẽ hết hạn) và `--until HH:MM` (giờ VN, máy ghi tự dừng).
- Subscribe `subscribe_symbol([symbol])`, như spike đã dùng.
- Ghi **nguyên văn** mọi tin QUOTE/TRADE ra `data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz`, mỗi dòng
  thêm trường `recv_ts` (giờ máy nhận, có múi giờ).
- **Thêm dòng `/data/` vào `.gitignore`.** Tôi đã kiểm: hiện `git check-ignore data/orderbook/x.jsonl.gz`
  trả exit 1, tức **chưa** bị bỏ qua. Mỗi phiên sinh ra hàng trăm MB, không được lọt vào git. Kiểm lại
  bằng đúng lệnh đó sau khi thêm: phải ra exit 0.
- Khi dừng, in thống kê: số tin mỗi loại, kích thước file, **khoảng lặng dài nhất** giữa hai tin liên
  tiếp trong giờ phiên, và danh sách mọi khoảng lặng > 10 giây.

**Test (không cần mạng/SSI):** tách hàm thuần cho (1) phân loại tin, (2) dò khoảng lặng, (3) đặt tên file
theo ngày giờ VN. Mỗi hàm có test tính tay. Riêng dò khoảng lặng phải đạt **đủ ba tiêu chí** cho công cụ
phát hiện (memory `tieu-chi-kiem-cong-cu-phat-hien`):
1. **Bắt đúng:** chuỗi dựng tay có khoảng lặng 15 giây thì phải báo.
2. **Không báo giả:** khoảng nghỉ trưa 11:30–13:00 **không** được tính là khoảng lặng.
3. **Mẫu số:** in ra tổng số tin đã xét.

---

## Task 1 — 25/09, 09:03: thăm dò 2 phút, có giám sát collector

**Điều kiện tiên quyết** (thiếu một cái thì DỪNG): `Get-Date` ≥ 09:03 và ≤ 09:30 ngày 25/09; cả 6 container
đang `Up`.

1. Ghi lại mốc thời điểm T0.
2. Chạy máy ghi **2 phút**: `--symbol 41I1GA000 --until <T0+2 phút>`.
3. **Trong suốt và 10 phút sau** thăm dò, theo dõi collector:
   - `docker logs ai_auto_trading_system-collector-1 --since <T0>` — tìm `SSIFeed connection error`,
     `connection`, `refresh`, `401`, `403`, `auth`, `WARN`, `ERROR`, `CRITICAL`. Dán **mọi** dòng khớp.
   - `logs\bars_closed.log` — các nến 09:05, 09:10, 09:15 của HPG/IJC/AAA phải đóng bình thường, `lag_ms`
     dán nguyên văn. (Nhắc: nến cổ phiếu bắt đầu 09:15, phái sinh 09:00.)
4. Output thống kê của máy ghi.

**Điều kiện DỪNG — gặp một cái là KHÔNG sang Task 2, chỉ báo cáo:**
- Collector có bất kỳ dòng ngắt kết nối hoặc lỗi auth trong khung T0 → T0+12 phút.
- Nến cổ phiếu trong khung đó bị thiếu, hoặc `lag_ms` vọt bất thường (> 60 giây).
- Máy ghi nhận **0** tin QUOTE (nghĩa là subscribe sai mã hoặc sai kênh).

Nếu thăm dò làm collector bị ngắt: **không cố sửa, không restart gì cả.** Collector có sẵn cơ chế tự kết
nối lại. Chỉ ghi lại chính xác bao lâu thì nó hồi phục.

---

## Task 2 — 25/09: ghi thử phần còn lại của phiên (chỉ khi Task 1 sạch)

1. Khởi động máy ghi ngay sau Task 1: `--symbol 41I1GA000 --until 14:46`.
   Chấp nhận mất đoạn 09:00 → lúc khởi động, vì đây là phiên thử.
2. **Giữa phiên, lúc ~11:00 và ~14:00**, kiểm lại collector như Task 1 bước 3. Thấy dấu hiệu ở điều kiện
   dừng → **dừng máy ghi ngay** (Ctrl+C), ghi mốc giờ, báo cáo.
3. Sau 15:10, đọc `logs\stream-health.log`: độ phủ luồng collector phiên 25/09 **phải vẫn 100%**. Thấp
   hơn thì đó là bằng chứng máy ghi đã gây hại, **dù** log collector không có lỗi.

---

## 3. Không làm

- Không sửa `trading/`, collector, engine, spike cũ. Không restart container.
- Không ghi sổ lệnh vào Postgres.
- Không tính đặc trưng, không đo tín hiệu, không backtest. Chỉ ghi và thống kê.
- Không lên lịch chạy tự động hằng ngày. Việc đó để sau, khi pilot đã sạch.
- Không đặt lệnh. Không commit, không push.

## 4. Báo cáo cho Claude

1. Task 0: code máy ghi, kết quả test, và output `git check-ignore -v data/orderbook/x.jsonl.gz` sau khi
   sửa `.gitignore`.
2. Task 1: T0, output máy ghi, **mọi** dòng log collector khớp mẫu (hoặc nói rõ "0 dòng"), `lag_ms` các
   nến 09:05–09:15.
3. Task 2: thống kê cuối phiên (số tin mỗi loại, dung lượng file, mọi khoảng lặng > 10 giây), hai lần kiểm
   giữa phiên, và dòng `stream-health` 25/09 nguyên văn.
4. `uv run pytest -m "not integration" -q` (nền **785**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường. Nói thẳng.

---

## 5. Ghi chú của planner — không phải việc của agent

**Kế hoạch dài hơn, để chủ dự án thấy trước:** nếu pilot 25/09 sạch, bước tiếp theo là lên lịch ghi hằng
ngày và xử lý roll (hợp đồng tháng 10 `41I1GA000` đáo hạn **15/10**, sau đó là `41I1GB000`). Sau khoảng
**20 phiên** (tức khoảng giữa đến cuối tháng 10), sàng lọc các đặc trưng dòng lệnh (chênh lệch khối lượng
mua/bán ở sổ lệnh, dòng lệnh chủ động có chiều) bằng đúng phương pháp đăng ký trước của đợt 85.

**Kỳ vọng trung thực:** vi cấu trúc sổ lệnh là nơi hợp lý nhất để còn sót một tín hiệu mà năm phép đo trước
chưa thấy. Nhưng tín hiệu kiểu này thường chỉ sống vài giây, nhỏ hơn chi phí giao dịch, và cần độ trễ thấp
mà hệ thống hiện chưa có (đợt 79 đo độ trễ collector trung vị ~12 giây). Nên kể cả sàng lọc dương cũng chưa
chắc giao dịch được. Mục đích của hướng này là **trả lời dứt khoát** câu hỏi "có tín hiệu nào không", chứ
không phải hứa hẹn lợi nhuận.

**Nếu chủ dự án không muốn theo hướng này:** dừng sau đợt 87 là hợp lý. Máy ghi không đụng vào hệ thống đang
chạy, và bỏ đi không để lại gì.
