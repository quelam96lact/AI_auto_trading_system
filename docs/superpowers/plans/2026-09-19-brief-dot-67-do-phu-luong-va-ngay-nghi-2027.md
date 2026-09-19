# Brief đợt 67 — Truy nguyên 6 nến thiếu của phiên 18/09, và vá lỗ ngày nghỉ 2027

Ngày giao: 19/09/2026 (thứ Bảy).
Base: main hiện tại (`36775a7`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

> **Thứ tự:** brief đợt 66 (chuyển handler lên logger `trading`) làm **trước**, brief này làm sau.
> Hai brief không đụng chung file nào, nhưng làm lần lượt thì audit gọn hơn.

---

## 0. Hai việc này từ đâu ra

Hôm nay tôi chạy `scripts/check_golive_gate.py` để đánh giá mức sẵn sàng go-live. Bảng kiểm trả
`EXIT 2` với một mục **CẢNH BÁO** chưa ai truy nguyên, và tôi đọc lại `config/config.yaml` thì
thấy một lỗ đã được ghi chú từ lâu nhưng chưa vá. Đây là hai việc đó.

**Không** thuộc brief này: lệch triển khai (mục 8 của bảng kiểm) — tôi tự dựng lại image sau khi
audit đợt 66, không giao agent. Và **không** đụng gì tới chiến lược giao dịch.

---

## Task 1 — Vì sao phiên chiều 18/09 chỉ có 51/57 nến?

### 1.1. Sự việc

`check_golive_gate.py` báo:

```
6 | Độ phủ luồng phiên gần nhất | 89.5% | [CẢNH BÁO]
    WARN: do phu luong phien chieu ngay 2026-09-18 dat 89.5% (51/57 nen),
    duoi nguong canh bao 90%
```

Thiếu **6 nến**. Đây là phiên giao dịch gần nhất trước phép đo quyết định sáng thứ Hai 22/09, nên
phải hiểu nguyên nhân **trước** khi lấy phép đo đó làm căn cứ kết luận.

### 1.2. Đây là điều tra, KHÔNG phải sửa lỗi

**Chưa biết có lỗi hay không.** Có ít nhất ba khả năng, và kết luận phải dựa vào dữ liệu chứ
không phải phỏng đoán:

- (a) **Bình thường, không phải lỗi**: trong 5 phút đó không mã nào khớp lệnh nên không có nến để
  chốt — với mã thanh khoản mỏng thì đây là hành vi đúng.
- (b) **Luồng đứt ngắn**: feed SSI rớt vài phút rồi nối lại.
- (c) **Lỗi gom nến/chốt nến**: nến có dữ liệu nhưng không được chốt hoặc không được ghi.

Nhiệm vụ của bạn là **xác định cái nào**, kèm bằng chứng. Nếu là (a), kết luận "không phải lỗi" là
một kết quả hợp lệ và tốt — **đừng bịa ra một bản vá để tỏ ra có làm việc**.

### 1.3. Cách làm

1. Xác định chính xác **6 khung 5 phút nào** bị thiếu trong phiên chiều 18/09 (13:00–14:30).
   So bộ khung kỳ vọng với các mốc `ts` thực có trong bảng `bars` cho ba mã `HPG, IJC, AAA`.
2. Với mỗi khung thiếu, đối chiếu:
   - bảng `bars` có bar của mã nào ở khung đó không (thiếu cả ba mã hay chỉ một mã?);
   - log collector quanh mốc đó (`logs/bars_closed.log` và `docker compose logs collector`) —
     có dòng `bars closed` nào không, có dấu hiệu rớt kết nối/khởi động lại không.
3. Kiểm tra xem 6 khung đó có **liền nhau** không (liền nhau ⇒ nghiêng về (b) đứt luồng; rải rác
   ⇒ nghiêng về (a) không có khớp lệnh).
4. Nếu nghiêng về (a): kiểm chứng bằng dữ liệu độc lập — bảng `bars_daily` hoặc khối lượng khớp
   của ba mã hôm đó, cho thấy thanh khoản thực sự mỏng ở các khung ấy.

### 1.4. Báo cáo

Một bảng: khung thiếu | mã nào thiếu | có dòng log nào không | kết luận khả năng (a)/(b)/(c).
Kết thúc bằng **một câu** kết luận, và nếu là (b) hoặc (c) thì **mô tả lỗi, đề xuất hướng sửa,
nhưng ĐỪNG sửa** — quay lại xin brief. Việc sửa đường gom nến ngay trước phép đo thứ Hai là điều
tôi không cho phép làm vội.

---

## Task 2 — Ngày nghỉ 2027: vá phần chắc chắn, đánh dấu rõ phần chưa chắc

### 2.1. Sự việc

`config/config.yaml` hiện có đúng ba ngày, kèm chính lời tự thú trong file:

```yaml
# Danh sach nay CHUA day du cho phan con lai cua 2026 (chua tra lich nghi le).
holidays: ['2026-08-31', '2026-09-01', '2026-09-02']
```

Tôi đã tra: **từ 19/09/2026 đến hết 31/12/2026 Việt Nam không còn ngày nghỉ lễ chính thức nào**
(lễ cuối cùng của năm là 02/09 đã có trong danh sách). Nghĩa là lỗ này **chưa cắn trong năm nay**,
nhưng sẽ cắn ngay **01/01/2027** — và hậu quả đã từng xảy ra thật: ngày 01/09/2026 chuông 2A nổ
mỗi 5 phút suốt cả ngày vì ngày lễ không có trong danh sách (xem `heartbeat_check.py:94-97`).

### 2.2. Chỉ thêm ngày CHẮC CHẮN

Thêm vào `holidays` bốn ngày nghỉ **cố định theo dương lịch** của 2027, là những ngày không phụ
thuộc lịch âm nên chắc chắn đúng:

- `2027-01-01` — Tết Dương lịch
- `2027-04-30` — Giải phóng miền Nam
- `2027-05-01` — Quốc tế Lao động
- `2027-09-02` — Quốc khánh

### 2.3. TUYỆT ĐỐI không tự suy ra ngày âm lịch

**Không** thêm Tết Nguyên đán 2027 và Giỗ Tổ Hùng Vương (10/3 âm lịch) — hai dịp này theo lịch âm,
và quan trọng hơn: **số ngày nghỉ và ngày nghỉ bù do Chính phủ công bố hằng năm**, không suy ra
được bằng công thức. Tự tính ra rồi ghi vào file là đưa số sai vào một nơi mà mọi chuông báo đều
tin — đúng kiểu lỗi mà cả dự án này đang phòng.

Thay vào đó, **thêm một dòng chú thích** ngay trên danh sách, ghi rõ: còn thiếu Tết Nguyên đán
2027 và Giỗ Tổ Hùng Vương 2027, phải lấy từ thông báo chính thức của Chính phủ, chủ dự án bổ sung
trước **31/12/2026**.

### 2.4. Kiểm chứng

1. `uv run python -c "import yaml; print(yaml.safe_load(open('config/config.yaml', encoding='utf-8'))['holidays'])"`
   — dán kết quả, phải ra đủ 7 ngày.
2. Chứng minh danh sách mới thực sự có tác dụng: viết một test (hoặc chạy một đoạn kiểm) cho thấy
   `is_trading_day(date(2027, 1, 1), holidays)` trả `False` khi nạp `holidays` từ config, trong khi
   trước thay đổi trả `True`. Dán cả hai kết quả.
3. `uv run pytest -m "not integration" -q` — hiện là 705 (hoặc số mới sau đợt 66), không test nào
   đỏ thêm.

---

## 3. Không làm

- **Không sửa đường gom nến/chốt nến** dù Task 1 tìm ra lỗi — báo cáo, xin brief mới.
- **Không tự thêm ngày âm lịch 2027.**
- **Không đụng chiến lược giao dịch**, không đổi `symbols`, không bật `real_trading_enabled`.
- **Không dựng lại image, không restart container** (việc của Claude).
- Không commit, không push.

---

## 4. Báo cáo cho Claude

1. Bảng truy nguyên 6 khung thiếu + câu kết luận (Task 1.4).
2. `git diff config/config.yaml`.
3. Hai kết quả kiểm chứng ở Task 2.4 (trước/sau).
4. `uv run pytest -m "not integration" -q` và `uv run ruff check trading tests scripts`.
