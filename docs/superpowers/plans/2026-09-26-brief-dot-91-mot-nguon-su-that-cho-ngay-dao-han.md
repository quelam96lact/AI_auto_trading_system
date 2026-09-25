# Brief đợt 91 — Một nguồn sự thật cho ngày đáo hạn, và chuông cho ca chọn sai mã

Ngày giao: 26/09/2026 (thứ Bảy).
Base: main `e73cccf`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Phải xong trước 08:40 thứ Hai 28/09** — đó là lúc tác vụ hẹn giờ tự chạy lần đầu.

---

## 0. Vì sao có brief này

Sau khi commit đợt 90 tôi tự soát và thấy repo nay có **ba cách khác nhau** để biết một hợp đồng đáo hạn
ngày nào:

| Nguồn | Cách biết | Ai dùng |
|---|---|---|
| `scripts/build_derivative_continuous_series.py:46,52,…` | **ghim cứng** `last_trading_date=date(2026, 4, 16)` | dựng chuỗi lịch sử, chạy tay |
| `scripts/measure_derivative_contract_volume.py:183,193` | **lấy từ SSI** (`securitiesByBoard` → `lastTradingDate`) | đo khối lượng, chạy tay |
| `scripts/record_vn30f_orderbook.py:98,131` | **tự tính** `get_third_thursday()` | **máy ghi, tự chạy mỗi sáng** |

Đây là vi phạm "một công thức, một chỗ", và ba nguồn **có thể mâu thuẫn**. Nguồn thứ ba là nguồn duy nhất
**tự chạy không ai trông**, nên nó là nguồn phải sửa.

**Quy tắc tự tính hiện tại không sai — tôi đã đối chiếu 5 hợp đồng thật** (20/08, 17/09, 15/10, 19/11,
17/12), khớp cả 5. Nhưng nó có **hai lỗ đã biết**, và cả hai **tự biến mất** nếu lấy từ SSI:

1. `year_codes = {2026: "G", 2027: "H", 2028: "I"}` — hết 2028 thì danh sách rỗng → `ValueError` → máy ghi
   chết. Đúng lớp lỗi "thứ ghim cứng rồi hết hạn" mà dự án đã mắc ở `derivative_backtest.py` hơn một tháng.
2. **Không xử lý ngày lễ.** Nếu thứ Năm thứ ba trùng ngày lễ, HNX đổi ngày đáo hạn; công thức không biết,
   SSI thì biết.

**Hậu quả nếu chọn sai mã:** máy ghi sẽ ghi một hợp đồng **không phải front-month**, tức chỉ khoảng 0,2%
khối lượng. File vẫn được tạo, vẫn đọc được, vẫn trông "thành công" — nhưng dữ liệu vô dụng. Đây là loại
hỏng tệ nhất: **im lặng và trông như ổn.**

---

## 1. Ràng buộc

- Được sửa: `scripts/record_vn30f_orderbook.py` và `tests/test_record_vn30f_orderbook.py`.
- **Không** sửa `build_derivative_continuous_series.py`. Danh sách ghim cứng ở đó là **dữ liệu lịch sử** đã
  dùng để dựng `VN30F1M_CONT`; đổi nó là làm chuỗi đã dựng không tái lập được. Chỉ thêm **một dòng chú
  thích** nói rõ nó là bản chụp lịch sử, không phải nguồn sự thật cho code chạy thật.
- **Không** sửa `measure_derivative_contract_volume.py` — nó đã là nguồn đúng, chỉ cần dùng lại.
- **Không** restart/build container. **Không** đặt lệnh. Không commit, không push.
- Nền hiện tại: **811 passed**, ruff sạch.

### Ràng buộc mới về khôi phục sau kiểm thử phá hoại — đọc kỹ

Đêm 25/09, `README.md` bị ghi lại lúc 00:17 và **mất khoảng 188 dòng thay đổi chưa commit** (tồn tại từ
13/08). Nhiều khả năng do một lệnh `git checkout` diện rộng trong chu kỳ phá hoại rồi khôi phục. Không cứu
được: không có stash, `git fsck --lost-found` ra 0 blob.

**Từ nay khi kiểm thử phá hoại:** sao lưu **đúng file sẽ sửa** ra ngoài repo trước, rồi khôi phục bằng cách
copy bản sao lưu đó lại. **TUYỆT ĐỐI KHÔNG** dùng `git checkout .`, `git checkout -- .`, `git restore .`,
`git stash`, hay bất kỳ lệnh tác động lên nhiều file. Repo luôn có thay đổi chưa commit của chủ dự án.

---

## Task 1 — Lấy ngày đáo hạn từ SSI, tự tính chỉ còn là đường lùi

1. Máy ghi lấy danh sách hợp đồng **từ SSI**, dùng lại `discover_derivative_contracts` (hoặc đúng hàm đang
   có) từ `scripts/measure_derivative_contract_volume.py` — **import lại, đừng chép**. Rồi vẫn dùng
   `filter_living_contracts` + `identify_front_month` như hiện nay.
2. **Giữ `get_third_thursday` làm đường lùi**, chỉ dùng khi gọi SSI thất bại (mất mạng, SSI lỗi). Khi rơi
   vào đường lùi, phát **WARN** nêu rõ: đã dùng công thức tự tính, mã chọn được là gì, và lý do không lấy
   được từ SSI. Máy ghi **vẫn chạy** — có dữ liệu còn hơn không, nhưng không được im lặng.
3. Nếu **cả hai** đường đều không cho ra mã → dừng sạch với lỗi rõ ràng, **không** ghi file rỗng.

**Kiểm chứng:**
- Lấy được từ SSI (giả lập hàm trả danh sách có `lastTradingDate` thật) → chọn đúng mã, **không** WARN.
- SSI lỗi (giả lập ném exception) → rơi về tự tính, chọn đúng mã, **có đúng 1 WARN** nêu lý do.
- **Ca phân biệt hai nguồn (bắt buộc):** dựng danh sách SSI trong đó một hợp đồng có `lastTradingDate`
  **khác** thứ Năm thứ ba (mô phỏng ngày lễ đẩy lịch) → phải chọn theo **SSI**, không theo công thức. Ca
  này chứng minh việc đổi nguồn có tác dụng thật, không chỉ là đổi code.
- Cả hai đường thất bại → nổ với lỗi rõ, không tạo file.
- **Kiểm thử phá hoại:** đảo thứ tự ưu tiên (tự tính trước, SSI sau), xác nhận **đúng ca phân biệt** đỏ.

---

## Task 2 — Chuông cho ca ghi sai mã

Chọn đúng mã là chưa đủ; phải phát hiện được khi đã chọn sai. Front-month có khoảng **29 tin QUOTE mỗi
giây** (đo thật phiên 25/09: 620.962 QUOTE / ~4,7 giờ); hợp đồng không phải front-month chỉ chừng 0,2%
lượng đó.

Yêu cầu: sau **10 phút đầu** kể từ khi vào giờ khớp lệnh liên tục, máy ghi tự kiểm số tin đã nhận. Nếu
thấp bất thường so với mức của front-month → phát **WARN** nêu rõ số tin đếm được, mã đang ghi, và cảnh
báo "có thể đang ghi sai hợp đồng". **Vẫn tiếp tục ghi** (biết đâu thị trường thật sự trầm), nhưng không
được im lặng.

Ngưỡng: bạn chọn, nhưng phải **nói rõ trong báo cáo đã chọn số nào và vì sao**, và phải đủ thấp để không
báo giả vào phiên trầm. Gợi ý điểm neo: dưới **1.000 tin QUOTE trong 10 phút** là bất thường rõ rệt
(front-month thật cho khoảng 17.000).

**Kiểm chứng:** hàm quyết định phải là **hàm thuần** (nhận số tin + số phút, trả về có cảnh báo hay không),
test tính tay cho ca bình thường, ca thấp bất thường, và ca chưa đủ 10 phút (chưa kết luận). Kèm kiểm thử
phá hoại.

---

## 2. Không làm

- Không sửa `build_derivative_continuous_series.py` (ngoài một dòng chú thích) và
  `measure_derivative_contract_volume.py`.
- Không bỏ `get_third_thursday` — nó là đường lùi hợp lệ.
- Không dùng `git checkout`/`git restore`/`git stash` diện rộng.
- Không restart/build container, không đặt lệnh, không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: kết quả 4 ca test + kiểm thử phá hoại, **đặc biệt dán ca phân biệt hai nguồn**.
2. Task 2: ngưỡng đã chọn và lý do; kết quả test + kiểm thử phá hoại.
3. Xác nhận đã sao lưu file ra ngoài repo khi phá hoại, và **không** dùng lệnh git diện rộng.
4. `uv run pytest -m "not integration" -q` (nền **811**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Ghi chú của planner

**Brief đợt 87 nay có một câu đã lỗi thời:** nó ghi `--symbol` là "bắt buộc, không mặc định". Đợt 90 đổi
thành tuỳ chọn + tự suy ra mã, vì tác vụ hẹn giờ cần chạy không tham số. Tôi **đồng ý** với việc đổi đó —
ý định gốc là "không ghim cứng mã", và tự suy ra vẫn giữ đúng ý định. Ghi lại đây để người đọc brief 87 về
sau không tưởng là agent làm sai.

**Việc chặn duy nhất vẫn là biểu phí phái sinh** — cần chủ dự án lấy từ SSI/HNX/VSD kèm nguồn. Không có nó
thì hướng phái sinh dừng ở sàng lọc, không đi tới backtest được.
