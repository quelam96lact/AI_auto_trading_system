# Brief đợt 95 — Biểu phí phái sinh có nguồn: thuế và phí VSD

**Giao cho:** Gemini Flash 3.8
**Người audit, commit, push:** Claude. Agent KHÔNG commit, KHÔNG push.
**Chạy được:** ngay, cuối tuần. Không đụng container, không đụng máy ghi sổ lệnh, không đụng Task Scheduler.

---

## Vì sao có đợt này

`DERIVATIVE_FEE_PER_CONTRACT = 8_250.0` (`trading/derivative_position.py:16`) là việc chặn duy nhất của nhánh phái sinh. Chủ tài khoản đã đưa nguồn, và Claude đã đọc **HTML gốc** của các trang SSI (không qua tóm tắt). Kết quả đối chiếu:

**Đã xác nhận, không cần làm lại:**

| Thành phần | Mức | Nguồn |
|---|---|---|
| Phí dịch vụ SSI, dưới 100 HĐ/ngày | **3.000 đ/HĐ** | SSI, "Biểu giá dịch vụ giao dịch **có chuyên viên TVCK**", hiệu lực 10/10/2025 |
| Phí trả HNX | **2.700 đ/HĐ/giao dịch** | cùng trang |
| Phí bù trừ trả VSDC | **2.550 đ/hợp đồng vị thế** | cùng trang |
| Quản lý tài sản ký quỹ trả VSDC | 0,0024%/tháng, tối thiểu 100.000 đ, tối đa 1.600.000 đ | cùng trang |

URL: `https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan`

Chủ tài khoản xác nhận ngày 26/09: tài khoản dùng gói **có chuyên viên TVCK**. Vì vậy 3.000 đ là đúng. (Gói "chủ động" là 2.000 đ. Không dùng số đó.)

**Không dùng trang cũ.** Trang `.../bieu-gia-dich-vu-ap-dung-cho-tkgd-chung-khoan-phai-sinh` có hiệu lực **01/01/2022**, đã bị thay. Trang đó ghi phí VSD là "2,550 đồng/hợp đồng/tài khoản/ngày Hoặc 2.550 đồng/hợp đồng thế vị". Trang mới chỉ ghi "2,550 đồng/hợp đồng vị thế". Hai câu chữ khác nhau là lý do có Task 1b.

**Hai lỗ hổng thật trong mô hình phí hiện tại:**

1. **Thuế TNCN trên giao dịch phái sinh không được mô hình.** Không có trên trang SSI vì đó là thuế, không phải phí. Thuế tỷ lệ theo giá trị hợp đồng, còn mọi phí khác tính cố định theo hợp đồng. Nếu công thức thuế như Claude nhớ (chưa kiểm chứng, **không được dùng làm nguồn**) thì thuế có thể **lớn hơn tổng các phí còn lại cộng lại**. Đây là thành phần quan trọng nhất và hiện đang bằng 0.
2. **Phí VSD đang bị tính hai lần mỗi vòng.** Code cộng 2.550 vào cả lúc mở lẫn lúc đóng, tức 5.100 đ/vòng. Nhưng đơn vị ghi là "hợp đồng **vị thế**", không phải "hợp đồng/giao dịch" như phí HNX. Ghi chú trong code đã tự thừa nhận: "CHƯA xác nhận rõ tính theo lượt hay theo ngày giữ vị thế".

Phí quản lý ký quỹ là phí cố định theo tháng, không theo giao dịch. **Không mô hình vào broker.** Chỉ ghi vào tài liệu nguồn ở Task 1.

---

## Trước khi sửa code

Chạy GitNexus. Báo cáo cả ba kết quả:

- `gitnexus_impact({target: "DerivativePaperBroker", direction: "upstream"})`
- `gitnexus_impact({target: "open_long", direction: "upstream"})` (và `open_short`, `close` trong `trading/derivative_position.py`)
- Nếu có kết quả HIGH hoặc CRITICAL: **dừng và báo cáo**, không sửa.

Sau khi sửa: `gitnexus_detect_changes()` và dán kết quả.

---

## Task 1 — Nghiên cứu có nguồn. KHÔNG sửa code.

**Đầu ra:** tạo file `docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md`.

Với mỗi mục dưới đây, ghi: số hiệu văn bản, điều/khoản, URL, **trích nguyên văn** câu chứa con số hoặc công thức, ngày hiệu lực, và trạng thái `RESOLVED` hoặc `UNRESOLVED`.

**1a. Thuế TNCN trên giao dịch hợp đồng tương lai chỉ số.** Cần trả lời đủ bốn câu:
- Thuế suất là bao nhiêu?
- **Cơ sở tính thuế** là gì? Viết công thức chính xác như văn bản ghi. Có nhân tỷ lệ ký quỹ ban đầu không? Có chia 2 không?
- Thu **mỗi lần chuyển nhượng** (cả lệnh mở lẫn lệnh đóng) hay chỉ một chiều?
- Văn bản gốc hiện hành là văn bản nào, và đã bị sửa đổi chưa? Kiểm xem có văn bản sửa đổi mới hơn không.

**1b. Phí bù trừ / quản lý vị thế 2.550 đ trả VSDC.** Cần trả lời:
- Tính trên **vị thế còn mở cuối ngày** hay trên **mỗi hợp đồng giao dịch**?
- Một vòng mở và đóng **trong cùng phiên** có bị thu không? Nếu có thì bao nhiêu lần?
- Giữ qua đêm N ngày thì thu bao nhiêu lần?

**1c. Tỷ lệ ký quỹ ban đầu hiện hành của VN30F.** **Chỉ làm nếu** công thức 1a có dùng tỷ lệ này. Lấy từ thông báo của VSDC, ghi ngày áp dụng.

**Quy tắc nguồn:**
- **Nguồn gốc được chấp nhận:** văn bản pháp luật (thuvienphapluat.vn, vbpl.vn, chinhphu.vn, mof.gov.vn), trang của VSDC (vsd.vn), HNX (hnx.vn), SSI.
- Bài báo, blog, bài của công ty chứng khoán khác **chỉ dùng để tìm ra văn bản gốc**, không bao giờ làm nguồn của con số.
- Không tìm được văn bản gốc thì ghi `UNRESOLVED` kèm những gì đã thử. **Không đoán. Không lấy số "phổ biến trên mạng".**
- Nếu thấy thêm một khoản chi phí giao dịch nào khác (ví dụ VAT trên phí), **ghi vào file và báo cáo**, không mô hình.

**Kiểm chứng Task 1:** file tồn tại; mỗi mục có trích nguyên văn và URL; mỗi mục có trạng thái rõ ràng.

### CỬA DỪNG sau Task 1

Chỉ làm Task 2 nếu **cả 1a và 1b đều `RESOLVED`** (và 1c `RESOLVED` nếu 1a cần nó).

Nếu có bất kỳ mục nào `UNRESOLVED`: **dừng, báo cáo Task 1, không làm Task 2.** Cửa dừng này do Claude mở, agent không tự mở. Không có lý lẽ nào như "số này phổ biến nên chắc đúng" được chấp nhận.

---

## Task 2 — Sửa mô hình phí trong `trading/derivative_position.py`

**Chỉ được sửa:** `trading/derivative_position.py`, `tests/test_derivative_position.py`, và các literal phí trong test liệt kê ở mục "Test hiện có" bên dưới.

**Không được đụng:** `trading/derivative_backtest.py`, `trading/paper_broker.py`, mọi file trong `scripts/`, mọi file khác.

### Cấu trúc phí mới

Tách phí thành ba thành phần, mỗi thành phần một hằng số **có ghi chú nguồn trỏ tới file ở Task 1**:

1. **Phí theo mỗi lượt** (mở hoặc đóng): 3.000 + 2.700 = **5.700 đ/HĐ**. Giữ tên `DERIVATIVE_FEE_PER_CONTRACT` cho số này, vì `scripts/.spike_improve_derivative_strategies.py` đang import tên đó. Không đổi tên.
2. **Phí VSD 2.550 đ**: hằng số riêng. Cách thu **theo đúng kết quả 1b**:
   - Nếu 1b cho biết thu theo vị thế/ngày: thu **một lần lúc mở**. Ghi rõ trong comment rằng giữ qua đêm N ngày bị **tính thiếu (N−1) × 2.550 đ**, vì broker không có khái niệm ngày. **Không** thêm khái niệm ngày vào broker.
   - Nếu 1b cho biết thu theo mỗi hợp đồng giao dịch: thu cả lúc mở lẫn lúc đóng như hiện tại.
   - Nếu 1b cho biết vòng trong phiên không bị thu: **vẫn thu một lần lúc mở** (bảo thủ) và ghi rõ trong comment rằng đây là ước lượng bảo thủ.
3. **Thuế TNCN**: một hàm thuần duy nhất trong cùng file, ví dụ `derivative_trade_tax(price, qty, ...) -> float`, cài **đúng công thức nguyên văn ở 1a**. Tính theo `price` của lượt đó, **không** theo `avg_price`. Thu theo đúng số chiều ở 1a.

`Fill.fee` của mỗi lượt = tổng mọi thành phần thu ở lượt đó (phí + VSD nếu có + thuế). `open_fee`, `realized_pnl`, `cash` giữ đúng cơ chế DERIV-FEE-1 hiện tại: phí mở ghi vào `open_fee`, không gộp vào `avg_price`.

Thêm tham số mới vào `DerivativePaperBroker.__init__` **có giá trị mặc định** là các hằng số mới, để `derivative_backtest.py:49` (`DerivativePaperBroker(capital)`) chạy không cần sửa.

### Test cần viết (TDD: viết test trước, thấy đỏ, rồi mới sửa)

Mọi con số kỳ vọng phải **tính tay từ công thức trích ở Task 1**, ghi phép tính trong docstring của test. Không lấy số từ chính code đang test.

1. `derivative_trade_tax` với một giá cụ thể (ví dụ 1.900,0 điểm, 1 HĐ) trả đúng số tính tay.
2. Thuế tỷ lệ theo giá: giá gấp đôi thì thuế gấp đôi (nếu công thức là tuyến tính theo giá).
3. Một vòng long mở rồi đóng: `realized_pnl` = lãi gộp − (tổng mọi thành phần của cả hai lượt), khớp số tính tay.
4. Một vòng short: tương tự.
5. Phí VSD thu **đúng số lần** theo 1b.
6. `DerivativePaperBroker(capital)` không truyền gì vẫn dùng đúng các hằng số mới.

### Test hiện có dùng literal phí

Các chỗ sau đang ghim số 8.250:
- `tests/test_derivative_backtest.py:13` (`FEE = 8_250.0`)
- `tests/test_momentum_rsi.py:130` (`19_081_500.0 - 18 * 8_250.0`)
- `tests/test_derivative_position.py` (dùng `FEE` truyền tường minh)

Với mỗi chỗ:
- Nếu test truyền phí **tường minh** vào broker thì nó đang test cơ chế, không phải biểu phí. **Giữ nguyên.**
- Nếu test dựa vào **giá trị mặc định** và hỏng vì biểu phí đổi: được sửa **chỉ con số kỳ vọng**, và phải ghi phép tính tay mới ngay cạnh. Liệt kê từng test đã sửa trong báo cáo, kèm số cũ, số mới, phép tính.
- **Không** sửa bất kỳ assertion nào khác, không đổi logic test.

### Kiểm thử phá hoại (bắt buộc, báo cáo đủ)

1. Cho `derivative_trade_tax` trả 0 → phải thấy **đúng** các test thuế đỏ, và các test không liên quan vẫn xanh. Liệt kê tên test đỏ.
2. Cho phí VSD thu ở cả hai lượt (hoặc ngược lại, tuỳ kết quả 1b) → test 5 phải đỏ.
3. Khôi phục, chạy lại, sạch.

### Kiểm chứng Task 2

```
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```

Dán dòng tổng kết. Mốc hiện tại: **845 passed**. Số mới phải bằng 845 cộng số test thêm.

---

## Task 3 — Báo cáo tác động. KHÔNG chạy lại backtest.

Tính và báo cáo **chi phí một vòng mở-đóng 1 HĐ**, cũ và mới, theo hai đơn vị:
- VND
- **Điểm chỉ số** (chia cho hệ số nhân 100.000)

Dùng một giá tham chiếu cụ thể: giá đóng cửa gần nhất của `VN30F1M_CONT` trong bảng `bars_derivative`. Dán câu SQL và kết quả. Nếu dùng `ts` để lọc ngày, dùng `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`, không dùng `ts::date`.

Chỉ tính bằng hàm vừa viết ở Task 2. Không chép công thức ra script riêng.

**Không** chạy lại backtest phái sinh nào. **Không** kết luận gì về chiến lược.

---

## Báo cáo phải có

1. Kết quả GitNexus impact và detect_changes.
2. Task 1: đường dẫn file, và với mỗi mục 1a/1b/1c: trạng thái và câu trích nguyên văn.
3. Nếu dừng ở cửa: dừng ở mục nào, đã thử những nguồn nào.
4. Task 2: diff của `trading/derivative_position.py`; danh sách test mới; danh sách test cũ đã sửa số kèm phép tính.
5. Kiểm thử phá hoại: tên các test đỏ ở mỗi bước.
6. Dòng tổng kết pytest và ruff.
7. Task 3: bảng chi phí một vòng, cũ và mới, VND và điểm; câu SQL.
8. Mọi điều phát hiện ngoài phạm vi: **báo cáo, không sửa.**
