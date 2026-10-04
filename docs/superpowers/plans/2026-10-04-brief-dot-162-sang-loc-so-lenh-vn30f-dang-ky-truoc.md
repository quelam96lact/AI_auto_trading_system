# Brief đợt 162 — Sàng lọc đặc trưng sổ lệnh VN30F, ĐĂNG KÝ TRƯỚC (giả thuyết số 1 của tháng 10/2026)

Ngày: 04/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md` (vốn rủi ro 100 triệu, MDD 7%, backtest ≤ 4,7%, hurdle 9%/năm).

**Brief này chưa chạy được ngay.** Dữ liệu chưa đủ phiên (xem §2). Mục đích của file này là **khóa mọi tham số trước khi nhìn dữ liệu**. Ngày giao việc thực thi: sau mốc §2.

---

## 0. Câu hỏi, kỳ vọng trước, và điều KHÔNG hỏi

**Câu hỏi:** ba đặc trưng sổ lệnh tại cuối mỗi phút (`imb_top1`, `imb_top5`, `ofi`) có dự báo được thay đổi giá VN30F trong 1, 5, 15 phút tiếp theo không, và nếu có thì **mức dịch chuyển có lớn hơn chi phí thực thi thật** không?

**Không hỏi:** có xây được chiến lược không. Kết quả dương chỉ mở đường tới bước kế (backtest đủ chi phí, §6), không phải kết luận.

**Kỳ vọng trước của Claude: nhiều khả năng âm hoặc "có thông tin nhưng không đủ trả phí".** Lý do cụ thể, không chung chung:
- Mất cân bằng sổ lệnh và order flow là loại tín hiệu **tồn tại ở thang giây**. Lưới 1 phút và độ trễ nhận tin trung vị 12 giây (đợt 79) làm phần lớn thông tin đã bị hấp thụ khi ta kịp hành động.
- Chi phí khứ hồi ≈ 0,49 điểm + spread ≈ 0,2 điểm ≈ **0,69 điểm**. Biên độ VN30F trong 5 phút thường cùng cỡ đó, nên đòi hỏi tín hiệu rất sạch.
- Năm phép đo âm trước đều dùng dữ liệu nến. Chưa có bằng chứng nào cho thấy dữ liệu sổ lệnh khác đi, chỉ có lý do để thử.

Brief vẫn đáng làm vì dữ liệu này là **thứ duy nhất ta có mà thị trường không bán sẵn**, và đã thu gần một tuần. **Kết quả âm là kết quả hợp lệ.**

Đây là **giả thuyết 1/3 của tháng 10/2026** (mục F của spec).

---

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy dữ liệu

### 1.1 Dữ liệu
- Nguồn: file `data/orderbook/<mã>/<ngày>.jsonl.gz` của máy ghi, dựng bảng 1 phút bằng `scripts/build_orderbook_features.py` (đợt 93): gộp theo `trading_time`, QUOTE cuối phút, khung 09:00–11:29 và 13:00–14:29 (**240 phút/phiên**, loại ATC).
- **Mã hợp đồng đổi theo tháng.** Mỗi file mang mã hợp đồng tháng gần nhất của ngày đó. Phiên nào trong ngày chuyển hợp đồng (sau ngày đáo hạn thứ Năm thứ ba) phải dùng đúng mã ghi trong file; **không nối chéo hai hợp đồng trong một mục tiêu `fwd`**. Mục tiêu chỉ tính trong cùng phiên nên điều kiện này tự thỏa; chỉ cần báo mã của từng phiên.
- Phút thiếu QUOTE → hàng đặc trưng là `None`, **loại khỏi mẫu**, báo tỷ lệ loại. Không nội suy.

### 1.2 Chia IS / niêm phong theo thời gian (chốt ngay bây giờ)
- **IS:** các phiên từ 25/09/2026 tới hết **30/11/2026**. Dự kiến khoảng 47 phiên (đếm chính xác bằng `check_orderbook_daily`; con số này là ước tính, chưa kiểm).
- **Tập niêm phong:** mọi phiên từ **01/12/2026**. **Không đọc, không dựng bảng, không tính gì** cho tới khi §5 cho phép. Mở đúng một lần cho đúng một cặp, ghi `docs/holdout-unlock-log.md`.
- Dữ liệu 25/09 từng được dùng ở đợt 93 chỉ để kiểm khả thi đường ống, **không tính tương quan**. Nên cả IS chưa bị nhìn tín hiệu.
- Điều kiện chạy phép đo IS: **≥ 40 phiên hợp lệ** trong IS (phiên hợp lệ = đủ ≥ 90% phút có QUOTE, theo báo cáo chất lượng của đợt 93). Thiếu thì dừng, không chạy.
- Điều kiện mở tập niêm phong: **≥ 30 phiên hợp lệ** từ 01/12 (mốc dự kiến giữa tháng 01/2027).

### 1.3 Đặc trưng (3) và mục tiêu (3) = 9 cặp, cố định
Đặc trưng, đúng định nghĩa đợt 93 (đơn vị điểm, `imb` ∈ [−1, 1]): `imb_top1`, `imb_top5`, `ofi`.

Mục tiêu: thay đổi giá **thực thi được**, tính theo điểm, trong cùng phiên, với độ trễ một phút:
- Tín hiệu tại cuối phút `t`. **Vào lệnh ở cuối phút `t+1`** (giả định ta mất một phút để nhận tin, quyết định và khớp; bảo thủ so với độ trễ trung vị 12 giây).
- Giá vào: mua = `ask` = `mid_close + spread/2` của phút `t+1`; bán = `bid` = `mid_close − spread/2` của phút `t+1`.
- Giá ra sau `h` phút: đóng ngược chiều bằng `bid`/`ask` của phút `t+1+h`. `h ∈ {1, 5, 15}` → `fwd_1`, `fwd_5`, `fwd_15`.
- Mục tiêu theo hướng mua (`+`) là `bid(t+1+h) − ask(t+1)`; hướng bán là `bid(t+1) − ask(t+1+h)`. **Spread đã nằm trong mục tiêu**, nên ngưỡng §1.5 chỉ cộng phí, **không cộng spread lần hai**.
- `t+1+h` vượt khung phiên → hàng đó bị loại (không đi qua đêm).

### 1.4 Phép kiểm định thống kê
- Thống kê: Spearman giữa đặc trưng và `mid_close(t+1+h) − mid_close(t+1)` (thay đổi mid cùng độ trễ; dùng cho kiểm định tương quan vì hướng mua/bán chưa xác định ở cột này).
- Hiệu chỉnh đa so sánh: **một lần** `run_block_permutation_test` cho cả 9 cặp, hoán vị theo **khối = 1 phiên**, 1.000 hoán vị, `seed = 42`, lấy ngưỡng P95 của max|rho|. Không cộng thêm Bonferroni.
- Chốt an toàn rò rỉ: chạy kiểm tra biến đối chứng như đợt 98/85 (`check_control_variable`); **trượt thì dừng, không in kết quả**. Nếu hàm đó không áp dụng cho dữ liệu 1 phút, agent phải **dừng và báo**, không tự thay thế bằng phép kiểm khác.
- Tự tương quan: mục tiêu `fwd_5`, `fwd_15` chồng lấn trên lưới 1 phút. Vì vậy khối hoán vị là một phiên (không hoán vị từng hàng), và số lệnh độc lập tính theo §1.5, không tính bằng số hàng.

### 1.5 Ngưỡng kinh tế (điều kiện thứ hai, độc lập)
Với mỗi cặp: **sự kiện** = các phút mà `|đặc trưng|` ≥ phân vị 90 của `|đặc trưng|` **tính trên IS** (cố định cho cả IS lẫn tập niêm phong, không tính lại). Hướng = dấu của đặc trưng (dấu dương → mua).

- `m` = trung bình mục tiêu §1.3 theo hướng của sự kiện, trên các sự kiện **đã chọn độc lập** (§1.6).
- Chi phí (điểm), phí+thuế thôi: `(derivative_side_cost(P, 1, opening=True) + derivative_side_cost(P, 1, opening=False)) / DERIVATIVE_CONTRACT_MULTIPLIER`, với `P` = trung vị `mid_close` của IS. Dùng hàm của `trading/derivative_position.py`, không viết lại số 0,49.
- **ĐÁNG KỂ** khi cả ba: (i) `|rho|` vượt ngưỡng P95 §1.4; (ii) `m` ≥ **1,5 × chi phí** (hurdle alpha của spec mục B); (iii) đủ mẫu §1.6.

### 1.6 Mẫu tối thiểu
- Sự kiện độc lập = chọn tham lam theo thời gian, mỗi sự kiện chiếm `1 + h` phút kể từ lúc vào; bỏ sự kiện trùng vị thế đang giữ. **Đếm sau khi bỏ chồng lấn**, theo từng cặp.
- Dưới **100 sự kiện độc lập** ở IS → nhãn **THIẾU SỨC MẠNH**, không kết luận âm hay dương cho cặp đó (spec mục C).
- Báo thêm số sự kiện từng phía (mua/bán). Dưới 30 một phía → ghi rõ.

### 1.7 Kỷ luật chạy
**Chạy phép đo thật đúng một lần.** Nếu lỗi code buộc chạy lại, báo cả hai lần và nói lỗi gì. Cấm: thêm đặc trưng, đổi `h`, đổi phân vị 90, đổi độ trễ, thử biến thể, đổi khối hoán vị. Mọi ý tưởng mới là giả thuyết mới, tính vào ngân sách F.

---

## 2. Mốc thời gian (sự thật, không phải hy vọng)

| Việc | Điều kiện | Dự kiến |
|---|---|---|
| Chạy phép đo IS | ≥ 40 phiên hợp lệ **và** ngày > 30/11/2026 (IS đã đóng) | đầu tháng 12/2026 |
| Mở tập niêm phong | Cặp ĐÁNG KỂ ở IS **và** ≥ 30 phiên hợp lệ từ 01/12 | giữa tháng 01/2027 |

**Không có kết quả nào trước tháng 12.** Trong thời gian chờ, việc duy nhất chạy là thu dữ liệu và giám sát chất lượng (các công cụ nghiệm thu hiện có). Không ai được "xem thử một chút" bảng IS.

Giả định chưa kiểm: máy ghi chạy liên tục tới hết 30/11 không mất phiên. Mỗi phiên mất là mất vĩnh viễn, và nếu IS dưới 40 phiên hợp lệ thì phải lùi mốc, **không hạ ngưỡng**.

---

## 3. Phạm vi cho agent thực thi (khi tới mốc)
- **Được thêm:** `scripts/screen_vn30f_orderbook.py`, `tests/test_screen_vn30f_orderbook.py`.
- **Được import, không sửa:** `scripts/build_orderbook_features.py`, `scripts/screen_vn30f_intraday.py`, `trading/derivative_position.py`, các công cụ hoán vị/rò rỉ hiện có.
- **Không sửa:** `trading/`, máy ghi, công cụ nghiệm thu, mọi file khác. Phát hiện vấn đề ngoài phạm vi → báo cáo, không tự sửa.
- Trước khi viết: GitNexus `context` cho các hàm dùng lại; sau khi viết: `detect_changes`, dán kết quả. Không commit, không push.

## 4. Kiểm chứng (TDD, test trước, thấy đỏ rồi mới viết code)
Test trên phiên dựng tay, không đọc file thật.
1. **Độ trễ một phút:** tín hiệu tại `t`, vào tại `t+1`: dựng chuỗi mid/spread, mục tiêu mua `h=1` đúng bằng `bid(t+2) − ask(t+1)` tính tay.
2. **Spread không bị đếm hai lần:** với spread 0 thì mục tiêu bằng chênh lệch mid; với spread 0,2 thì mua-rồi-bán giảm đúng 0,2 điểm so với chênh lệch mid.
3. **Bất biến theo tương lai:** sửa mọi phút sau `t` thì đặc trưng và sự kiện tại các phút ≤ `t` không đổi. Riêng ngưỡng phân vị 90 chỉ tính từ IS: test rằng thêm phiên ngoài IS vào dữ liệu **không** làm đổi ngưỡng.
4. **Không vượt phiên:** `t+1+h` vượt phút cuối phiên → hàng bị loại, không lấy phiên sau.
5. **Chọn sự kiện độc lập:** hai tín hiệu liền nhau với `h=5` chỉ đếm một; kết quả đếm đúng số tính tay.
6. **Hướng sự kiện:** đặc trưng âm và giá giảm → đóng góp dương vào `m`.
7. **Cổng mẫu:** IS dưới 40 phiên hợp lệ → script **dừng, không in rho**. Cặp dưới 100 sự kiện độc lập → nhãn THIẾU SỨC MẠNH, không nhãn âm/dương.
8. **Niêm phong:** script từ chối đọc phiên ≥ 01/12/2026 trừ khi có cờ mở niêm phong tường minh, và cờ đó ghi một dòng vào `docs/holdout-unlock-log.md`.
9. **Kiểm thử phá hoại** (sao lưu ra ngoài repo; cấm `git checkout/restore/stash`): bỏ độ trễ một phút → test 1 đỏ; tính ngưỡng phân vị trên toàn bộ dữ liệu → test 3 đỏ; cộng spread hai lần → test 2 đỏ. Báo tên test đỏ từng bước.

```
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 5. Quy tắc đọc kết quả
- Không cặp nào ĐÁNG KỂ → ghi **"Đặc trưng sổ lệnh 1 phút: KHÔNG có lợi thế sau chi phí trên VN30F IS"**, thêm một phép đo âm vào chuỗi đã có. Đóng hướng, không mở tập niêm phong.
- Có cặp qua thống kê nhưng `m` < 1,5 × chi phí → ghi **"có thông tin nhưng không đủ trả phí"**. Không làm tròn thành "có tín hiệu".
- Có cặp ĐÁNG KỂ → chưa phải kết luận. Mở tập niêm phong **một lần cho đúng cặp đó** (cần p < 0,05 một phía, lặp lại cả điều kiện kinh tế). Qua mới sang §6.
- Ghi kết quả (cả âm) vào sổ giả thuyết tháng 10.

## 6. Bước kế nếu qua cả IS và tập niêm phong (chưa làm, chưa giao)
Backtest đủ chi phí theo thang E của spec: khớp ở nến sau, spread, **MDD backtest ≤ 4,7%**, lãi ròng ≥ 9%/năm quy trên vốn rủi ro (chỉ kết luận khi cửa sổ ≥ 12 tháng hoặc có kiểm định thống kê), rồi paper forward ≥ 50 lệnh hoặc ≥ 3 tháng.
Lưu ý: với dữ liệu chỉ có từ 25/09/2026, **cửa sổ ≥ 12 tháng chưa thể có trước tháng 10/2027**. Nên hurdle 9%/năm trước đó chỉ có thể đạt bằng kiểm định thống kê, không bằng con số quy năm.

## 7. Giới hạn đã biết của thiết kế
- Lưới 1 phút và độ trễ 1 phút bỏ qua toàn bộ tín hiệu thang giây. Nếu có tín hiệu thật ở thang giây thì brief này **không thấy**, và cũng không giao dịch được với hạ tầng hiện tại. Đo thang giây là giả thuyết khác, tính vào ngân sách.
- Bảng chi phí (phí, thuế TNCN) **chưa đối chiếu với bảng kê thật**. Chi phí sai lệch đổi ngưỡng ĐÁNG KỂ. Khi chủ dự án gửi bảng kê, đối chiếu **trước** khi chạy phép đo thật, và nếu mô hình phí đổi thì ghi vào nhật ký trước khi chạy (không phải sau).
- Một IS ≈ 47 phiên, 9 cặp: sức mạnh thống kê vừa phải. Hiệu ứng nhỏ cỡ 0,1 điểm gần như không phân biệt được với 0, nên THIẾU SỨC MẠNH là kết cục có thật, không phải trường hợp hiếm.
