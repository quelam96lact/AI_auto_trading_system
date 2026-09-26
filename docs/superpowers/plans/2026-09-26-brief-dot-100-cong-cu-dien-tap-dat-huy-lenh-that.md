# Brief đợt 100 — Làm mới công cụ diễn tập "đặt rồi huỷ một lệnh thật" (T3) — KHÔNG gửi lệnh

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `19432af`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.

## ⛔ Luật tối thượng của brief này

**Agent KHÔNG ĐƯỢC gửi bất kỳ lệnh thật nào lên sàn**, dưới mọi hình thức. Cụ thể:
- **Không** chạy script với cờ `--send`.
- **Không** gọi `place_limit_order` hay `cancel_order` thật trong test hay trong lần chạy thử.
- **Không** sửa `config.yaml` (`real_trading_enabled` giữ `false`).

Người bấm nút gửi lệnh thật là **chủ tài khoản**, trong một phiên sống, sau khi Claude đã audit xong. Được phép: các lệnh **chỉ đọc** tới SSI (sức mua, giá lịch sử) trong lần chạy thử ở §3.

---

## 0. Vì sao

Chủ dự án đã chọn **go-live kỹ thuật cỡ nhỏ**. Bước tiếp theo là **T3**: đặt một lệnh giới hạn thật, xa giá thị trường, rồi huỷ ngay, để chứng minh đường xác thực, ký lệnh, đặt và huỷ lệnh chạy đúng với tiền thật.

Công cụ cho T3 đã có (`scripts/spike_ssi_sdk_place_order.py`, từ khoảng đợt 30), nhưng Claude đọc lại và thấy nó **không dùng được nữa**:

1. **Xác thực qua `make_auth()`.** Đây là đường OTP cũ đã gây hai sự cố thật, và dự án đã bỏ. Đường hiện hành là `trading.collector.ssi_auth.ensure_authenticated(cfg, storage)` (token trong DB), đúng như `scripts/confirm_real_order.py:118` đang dùng.
2. **Giá đặt có thể dưới giá sàn, nên sàn sẽ từ chối lệnh và buổi diễn tập hỏng.**
   - Script lấy "giá đóng cửa gần nhất" từ dữ liệu ngày. Nếu chạy trong phiên, đó là **giá hiện tại**, không phải **giá tham chiếu**.
   - Sau đó nó nhân 0,93 rồi **làm tròn** tới 100 đồng. Ví dụ: tham chiếu 12.300 → 11.439 → làm tròn thành **11.400**, thấp hơn giá sàn 11.450.
3. **Mặc định tài khoản `0434221` được gắn cứng.** Chủ tài khoản chưa xác nhận lệnh thật đi vào 0434221 hay 0434226, nên tài khoản phải là lựa chọn **tường minh** mỗi lần chạy.
4. **Không có chế độ chạy thử.** Chạy là đặt lệnh thật ngay; không có bước gõ YES như `confirm_real_order.py`.
5. **Không có đường xử lý khi huỷ thất bại.** Nếu `cancel_order` lỗi, lệnh thật vẫn treo trên sàn mà không ai được báo.

---

## Task 1 — Công cụ mới `scripts/drill_place_cancel_order.py`

**Tạo file mới.** **Không** sửa `confirm_real_order.py`, `real_orders.py`, `trading/`.

### 1.1 Hành vi (chốt sẵn, không tự đổi)

**Tham số:**
- `--account` là **bắt buộc**, không có mặc định. Thiếu thì thoát mã 2 **trước khi** gọi mạng.
- `--symbol`, mặc định `VCB`.
- `--send`: không có cờ này thì chỉ **chạy thử**.

**Các bước, theo đúng thứ tự:**
1. **Xác thực:** `ensure_authenticated(cfg, storage)`, rồi `auth.config.private_key = cfg.ssi_private_key`, rồi `AsyncTrading(auth)`. Chép đúng khuôn `confirm_real_order.py:117-120`.
2. **Chỉ nhận mã HOSE hoặc HNX.** Đọc sàn từ `symbol_universe.exchange`. Mã UPCOM hoặc không rõ sàn thì **dừng**, vì giá tham chiếu UPCOM là giá bình quân phiên trước, không phải giá đóng cửa.
3. **Sức mua (chỉ đọc):** `get_max_buy_sell_at_market_price(account, symbol)`. Nếu `max_buy_quantity < 100` thì **dừng**, in rõ thiếu bao nhiêu. Không cố đặt lệnh chắc chắn thất bại.
4. **Giá tham chiếu (chỉ đọc):** lấy dữ liệu ngày **thô từ SSI** (`AsyncData ... get_ohlc_1day_historical`, như script cũ). Giá tham chiếu = giá đóng cửa của **phiên gần nhất có ngày nhỏ hơn hôm nay (giờ VN)**. **Không** dùng `bars_daily`: bảng đó đã điều chỉnh ngược nên giá không phải giá thật. Không tìm được thì **dừng**.
5. **Giá đặt:** hàm thuần `drill_price(ref, exchange) -> int`, ví dụ trong mã giả:
   - `band = 0,07` (HOSE) hoặc `0,10` (HNX).
   - `floor = ceil_to_tick(ref × (1 − band))`: sàn làm tròn **lên** bước giá.
   - `price = ceil_to_tick(ref × (1 − band + 0,01))`: cao hơn sàn khoảng 1%, vẫn cách tham chiếu khoảng 6% với HOSE, nên gần như không thể khớp trong vài giây.
   - Bắt buộc: `floor ≤ price < ref`. Sai thì **dừng**.
   - **Bước giá:** HOSE: giá < 10.000 thì 10 đồng; 10.000–49.950 thì 50 đồng; ≥ 50.000 thì 100 đồng. HNX: 100 đồng. **Ghi nguồn** (quy chế giao dịch của HOSE và HNX) trong docstring. Nếu agent tìm thấy nguồn gốc nói khác, **dừng và báo**, không tự chọn.
6. **In kế hoạch lệnh:** tài khoản, mã, sàn, giá tham chiếu, giá sàn, giá đặt, khối lượng 100, và `max_buy_quantity`.
   - **Không có `--send`:** in `[CHẠY THỬ] không gửi lệnh`, thoát mã 0.
7. **Có `--send`:** in kế hoạch lệnh rồi hỏi `Gõ YES để GỬI LỆNH THẬT:`. Khác `YES` (phân biệt hoa thường) thì huỷ và thoát 0. Theo khuôn của `confirm_real_order.py`.
8. **Đặt lệnh:** `place_limit_order(account, symbol, OrderSide.BUY, 100, price)`. In và lưu phản hồi.
9. **Huỷ ngay:** `cancel_order(account, client_request_id)`.
   - Nếu `cancel_order` **ném lỗi** hoặc phản hồi cho thấy **không** huỷ được: in khối **CẢNH BÁO NGHIÊM TRỌNG** gồm mã lệnh, tài khoản, mã, giá, và câu *"LỆNH THẬT CÓ THỂ ĐANG TREO — HUỶ TAY NGAY TRÊN iBoard/ứng dụng SSI"*; gọi `alert("CRITICAL", ...)`; thoát mã **2**.
10. **Xác nhận trạng thái sau khi huỷ:** tìm trong SDK một hàm đọc sổ lệnh hoặc trạng thái lệnh (tên có thể là order book / order history). Nếu có, đọc lại và in trạng thái của lệnh vừa huỷ. **Nếu SDK không có hàm đó, ghi rõ trong báo cáo**; không tự viết lời gọi HTTP.
11. Lưu phản hồi của bước 8–10 vào **một** file JSON trong `logs/` (tên có ngày giờ). **Không** ghi token hay khoá bí mật.

**Tiêm phụ thuộc cho test:** hàm chính nhận `trading_client`, `data_client` và `input_fn` làm tham số tuỳ chọn, như `confirm_real_order.py` đang làm với `max_buy_sell_fn`.

### 1.2 Vô hiệu hoá script cũ

Trong `scripts/spike_ssi_sdk_place_order.py`: đầu `main()` in *"ĐÃ THAY bằng scripts/drill_place_cancel_order.py (đợt 100) — script này dùng xác thực cũ và có thể đặt giá dưới sàn"*, rồi `sys.exit(1)`. **Không** xoá file. Đây là thay đổi **duy nhất** được phép trong file đó.

---

## Task 2 — Cập nhật runbook `docs/superpowers/runbooks/dien-tap-lenh-that.md`

Giữ cấu trúc, cập nhật cho khớp thực tế ngày 26/09:
- **Bước 0, trước mọi thứ:** chủ tài khoản **chọn và ghi ra** tài khoản sẽ dùng (0434221 hay 0434226), kèm lý do.
- **Pre-flight:** thêm "cổng go-live `uv run python scripts/check_golive_gate.py` trả EXIT 0".
  - Danh sách container phải lấy theo `docker compose ps` **thật** hôm nay. Agent chạy lệnh đó và chép kết quả, **không** đoán.
- **Khung giờ:** phiên khớp lệnh liên tục của cổ phiếu, tránh ATO và ATC. Riêng cổ phiếu: sáng 09:15–11:30, chiều 13:00–14:30.
- **T3:** các lệnh chính xác theo thứ tự:
  1. Chạy thử: `uv run python scripts/drill_place_cancel_order.py --account <TK> --symbol <MÃ>`.
  2. Đọc kế hoạch lệnh.
  3. Chạy lại có `--send`, rồi gõ YES.
  4. Đối chiếu trên iBoard: lệnh xuất hiện rồi ở trạng thái đã huỷ.
- **Nếu huỷ thất bại:** huỷ tay trên iBoard; nếu lệnh **đã khớp**, đó là 100 cổ phiếu mua ở giá thấp hơn tham chiếu khoảng 6%. Bán được từ **T+2,5**. Không hoảng: rủi ro tối đa là biến động giá của 100 cổ phiếu.
- **T4 (sau khi T3 đạt):** đường lệnh của hệ thống (`pending_real_orders` → `confirm_real_order.py`). Chỉ trỏ tới phần runbook đang có, **không** viết lại.
- Ghi ngày cập nhật và "các thay đổi so với bản trước" ở đầu file.

---

## 3. Kiểm chứng

### 3.1 Test (TDD, viết trước, thấy đỏ) — `tests/test_drill_place_cancel_order.py`

Dùng client giả. **Không** test nào được gọi SSI thật.

1. **Chốt an toàn quan trọng nhất:** không có `--send` thì `place_limit_order` và `cancel_order` của client giả **không bao giờ** được gọi. Kiểm bằng bộ đếm lời gọi = 0.
2. Có `--send` nhưng `input_fn` trả `"yes"`, `""`, hoặc `"YES "` (có khoảng trắng) → **không** gửi. Chỉ `"YES"` mới gửi.
3. Thiếu `--account` → thoát khác 0, và client giả **không** bị gọi hàm nào.
4. `max_buy_quantity = 99` → dừng, không gửi.
5. Mã UPCOM hoặc sàn không rõ → dừng, không gửi.
6. **Giá đặt, tính tay:**
   - HOSE ref 12.300: sàn = ceil50(11.439) = **11.450**; giá = ceil50(12.300 × 0,94 = 11.562) = **11.600**. Kiểm `11.450 ≤ 11.600 < 12.300`.
   - HOSE ref 9.870: bước 10 đồng. Tính tay trong docstring.
   - HOSE ref 52.000: bước 100 đồng.
   - HNX ref 20.000: `band = 0,10`, bước 100.
   - Biên bước giá: ref mà `ref × 0,94` rơi đúng 10.000 hoặc 50.000.
7. **Giá tham chiếu:** dữ liệu giả có nến hôm nay (giá 13.000) và hôm qua (giá 12.300); chạy "hôm nay" → ref phải là **12.300**. Ca này bắt đúng lỗi của script cũ.
8. **Huỷ thất bại:** `cancel_order` giả ném lỗi → thoát mã **2**, có `alert("CRITICAL", ...)`, và output chứa "HUỶ TAY".
9. Script cũ: gọi `main()` của `spike_ssi_sdk_place_order.py` → thoát 1 và **không** gọi mạng.

### 3.2 Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo**. **Cấm** `git checkout`, `git restore`, `git stash`.
- Bỏ điều kiện `--send` (luôn gửi) → test 1 **phải đỏ**.
- So YES không phân biệt hoa thường → test 2 đỏ.
- Làm tròn xuống thay vì lên → test 6 đỏ.
- Lấy nến cuối cùng làm tham chiếu → test 7 đỏ.
- Nuốt lỗi của `cancel_order` → test 8 đỏ.
- Khôi phục, chạy lại, sạch. Báo tên test đỏ từng bước.

### 3.3 Chạy thử thật, CHỈ ĐỌC (một lần)

```
uv run python scripts/drill_place_cancel_order.py --account 0434221 --symbol VCB
```
**Không có `--send`.** Hôm nay là thứ Bảy nên "phiên gần nhất trước hôm nay" là thứ Sáu 25/09. Dán nguyên văn output. Kiểm tay: giá tham chiếu in ra phải bằng giá đóng cửa VCB ngày 25/09 theo SSI.

Tài khoản 0434221 ở đây chỉ là **cấu hình hiện tại**, dùng cho lần chạy thử. Nó **không** phải quyết định T3 sẽ dùng tài khoản nào.

### 3.4 Tổng
```
uv run pytest -m "not integration" -q     # mốc: 947 passed
uv run ruff check trading tests scripts
```
Trước khi viết: `gitnexus_context` cho `ensure_authenticated` và `confirm_real_order`. Sau khi viết: `gitnexus_detect_changes()`.

---

## 4. Báo cáo cho Claude

1. GitNexus context và detect_changes.
2. Diff của `spike_ssi_sdk_place_order.py` (chỉ phần vô hiệu hoá) và của runbook.
3. Test; kiểm thử phá hoại (tên test đỏ từng bước).
4. Nguồn của quy tắc bước giá.
5. SDK có hay không có hàm đọc trạng thái lệnh (§1.1 bước 10).
6. Output nguyên văn của lần chạy thử §3.3.
7. Pytest và ruff.
8. **Xác nhận bằng một câu:** "Tôi không chạy `--send` và không gọi `place_limit_order`/`cancel_order` thật."
9. Mọi điều ngoài phạm vi: **báo cáo, không sửa.**
